"""BAML agent loop engine — replaces CrewAI Crew.kickoff() for tool-using agents.

Pure-Python tool-call loop: call BAML function → if ToolCall variant received,
dispatch via ToolDispatcher and call again with updated history → if Final variant
received, return the report.

Non-tool-using agents (clarifier, planner, refiner, architect, research) return
their final report directly in a single BAML call — no loop needed.
"""

from __future__ import annotations

import sys
import time
import traceback
from typing import Any

from baml_py import ClientRegistry

from baml_client import b as _default_client
from baml_client.types import (
    BuilderFinal, BuilderToolCall, BuilderStep,
    ClarifierOutput,
    Decision,
    FeaturePlan,
    MapperFinal, MapperStep,
    MapperReport,
    ResearchFindings,
    TechPlan,
    VerifierFinal, VerifierStep,
    VerifierReport,
)
from config import HarnessConfig
from loop_helpers import HarnessError
from tool_dispatch import ToolDispatcher

_MAX_TOOL_ITERS = 25

_STALL_MAX_RETRIES = 5
_STALL_BACKOFF = 5


def _client_for_agent(config: HarnessConfig, agent: str):
    """Return a BamlSyncClient configured for a specific agent's model.

    Maps config.model_for(agent) to BAML client names defined in clients.baml.
    Uses b.with_options(client=...) to switch the default client.
    """
    model = config.model_for(agent)
    model_lower = model.lower()

    if "claude" in model_lower or "sonnet" in model_lower or "opus" in model_lower:
        return _default_client.with_options(client="AnthropicSonnet")
    if "ollama" in model_lower or "qwen" in model_lower or "minimax" in model_lower or "glm" in model_lower:
        return _default_client.with_options(client="OllamaLocal")

    return _default_client


def _model_str(config: HarnessConfig, agent: str) -> str:
    return config.model_for(agent)


def _tool_history(entries: list[dict[str, str]]) -> str:
    """Serialize tool-call history for the BAML prompt's `history` input."""
    lines = []
    for i, entry in enumerate(entries):
        lines.append(f"[Turn {i + 1}]")
        if entry.get("tool"):
            lines.append(f"Tool call: {entry['tool']}")
        if entry.get("result"):
            lines.append(f"Result:    {entry['result']}")
        lines.append("")
    return "\n".join(lines) if lines else "(no previous turns)"


def _is_tool_call(result: Any) -> bool:
    """Heuristic: tool-call variants have a 'tool_name' field."""
    return hasattr(result, "tool_name")


def _extract_tool_name(result: Any) -> tuple[str, dict[str, Any]]:
    return result.tool_name, dict(getattr(result, "args", {}))


_MAP_AGENT_DISPLAY = {
    "clarifier": "Clarifier",
    "planner":   "Planner",
    "research":  "Research",
    "refiner":   "Refiner",
    "architect": "Architect",
    "builder":   "Builder",
    "verifier":  "Verifier",
    "mapper":    "Mapper",
}


def _print_header(agent_key: str, config: HarnessConfig, slug: str) -> None:
    display = _MAP_AGENT_DISPLAY.get(agent_key, agent_key.title())
    model = _model_str(config, agent_key)
    print(f"\n  [{display}] ({model}) — {slug}")


# ---------------------------------------------------------------------------
# Non-tool agents (single call → structured output)
# ---------------------------------------------------------------------------

def invoke_clarifier(specs_content: str, config: HarnessConfig) -> ClarifierOutput:
    client = _client_for_agent(config, "clarifier")
    _print_header("clarifier", config, "__clarify__")
    return client.ClarifySpecs(specs_content=specs_content)


def invoke_planner(specs_content: str, clarifications: str, existing_plan: str,
                   config: HarnessConfig) -> FeaturePlan:
    client = _client_for_agent(config, "planner")
    _print_header("planner", config, "__init__")
    return client.PlanFeatures(
        specs_content=specs_content,
        clarifications=clarifications,
        existing_plan=existing_plan,
    )


def invoke_research(feature_name: str, slug: str, research_type: str, sub_prompt: str | None,
                    vault_overview: str, vault_structure: str,
                    config: HarnessConfig) -> ResearchFindings:
    client = _client_for_agent(config, "research")
    _print_header("research", config, slug)
    return client.ResearchFeature(
        feature_name=feature_name,
        slug=slug,
        research_type=research_type,
        sub_prompt=sub_prompt,
        vault_overview=vault_overview,
        vault_structure=vault_structure,
    )


def invoke_refiner(feature_name: str, slug: str, vault_overview: str,
                   vault_structure: str, vault_deps: str,
                   acceptance_criteria: str, research_findings: str | None,
                   config: HarnessConfig) -> Decision:
    client = _client_for_agent(config, "refiner")
    _print_header("refiner", config, slug)
    return client.RefineApproaches(
        feature_name=feature_name,
        slug=slug,
        vault_overview=vault_overview,
        vault_structure=vault_structure,
        vault_deps=vault_deps,
        acceptance_criteria=acceptance_criteria,
        research_findings=research_findings,
    )


def invoke_architect(feature_name: str, slug: str, vault_structure: str,
                     vault_entrypoints: str, acceptance_criteria: str,
                     decision_text: str | None, research_findings: str | None,
                     config: HarnessConfig) -> TechPlan:
    client = _client_for_agent(config, "architect")
    _print_header("architect", config, slug)
    return client.ArchitectFeature(
        feature_name=feature_name,
        slug=slug,
        vault_structure=vault_structure,
        vault_entrypoints=vault_entrypoints,
        acceptance_criteria=acceptance_criteria,
        decision_text=decision_text,
        research_findings=research_findings,
    )


# ---------------------------------------------------------------------------
# Tool-loop agents (multi-turn: ToolCall → result → ToolCall → ... → Final)
# ---------------------------------------------------------------------------

def _tool_loop(baml_fn, initial_kwargs: dict, agent_key: str, slug: str,
               config: HarnessConfig, dispatcher: ToolDispatcher) -> Any:
    """Run a multi-turn tool-call loop until the BAML function returns a Final variant.

    baml_fn: callable(**kwargs) → ToolCall | Final union
    initial_kwargs: first-call keyword args (must include 'history' key)
    """
    history_entries: list[dict[str, str]] = []
    call_kwargs = dict(initial_kwargs)  # shallow copy — we mutate 'history' key

    for iteration in range(1, _MAX_TOOL_ITERS + 1):
        call_kwargs["history"] = _tool_history(history_entries)
        client = _client_for_agent(config, agent_key)

        for stall in range(_STALL_MAX_RETRIES + 1):
            try:
                result = baml_fn(client=client, **call_kwargs)
                break
            except Exception:
                if stall == _STALL_MAX_RETRIES:
                    raise
                msg = f"  ! [{agent_key}] stall — retry {stall + 1}/{_STALL_MAX_RETRIES}"
                sys.stdout.write(f"\r{msg}\n")
                sys.stdout.flush()
                time.sleep(_STALL_BACKOFF)

        if _is_tool_call(result):
            name, args = _extract_tool_name(result)
            tool_result = dispatcher.dispatch(name, args)
            history_entries.append({"tool": f"{name}({args})", "result": tool_result})
            if config.verbose:
                print(f"    [{agent_key}] tool call #{iteration}: {name}")
                for line in tool_result.splitlines()[:3]:
                    print(f"      {line}")
        else:
            return result.report if hasattr(result, "report") else result

    raise HarnessError(f"{agent_key} exceeded max tool iterations ({_MAX_TOOL_ITERS})")


def invoke_builder(tech_plan: str, decision_text: str | None, slug: str,
                   feature_description: str, config: HarnessConfig) -> Any:
    """Returns BuilderReport (via tool loop)."""
    _print_header("builder", config, slug)
    dispatcher = ToolDispatcher(config)

    def _call(*, client, history, **kwargs):
        return client.BuildFeature(
            tech_plan=kwargs["tech_plan"],
            decision_text=kwargs["decision_text"],
            slug=kwargs["slug"],
            feature_description=kwargs["feature_description"],
            history=history,
        )

    return _tool_loop(
        _call,
        {"tech_plan": tech_plan, "decision_text": decision_text,
         "slug": slug, "feature_description": feature_description, "history": ""},
        "builder", slug, config, dispatcher,
    )


def invoke_verifier(tech_plan: str, slug: str,
                    config: HarnessConfig) -> VerifierReport:
    """Returns VerifierReport (via tool loop)."""
    _print_header("verifier", config, slug)
    dispatcher = ToolDispatcher(config)

    def _call(*, client, history, **kwargs):
        return client.VerifyBuild(
            tech_plan=kwargs["tech_plan"],
            slug=kwargs["slug"],
            history=history,
        )

    return _tool_loop(
        _call,
        {"tech_plan": tech_plan, "slug": slug, "history": ""},
        "verifier", slug, config, dispatcher,
    )


def invoke_mapper(git_diff: str, slug: str, feature_description: str,
                  plan_text: str, tech_plan: str, index_text: str,
                  config: HarnessConfig) -> MapperReport:
    """Returns MapperReport (via tool loop)."""
    _print_header("mapper", config, slug)
    dispatcher = ToolDispatcher(config)

    def _call(*, client, history, **kwargs):
        return client.MapAndIndex(
            git_diff=kwargs["git_diff"],
            slug=kwargs["slug"],
            feature_description=kwargs["feature_description"],
            plan_text=kwargs["plan_text"],
            tech_plan=kwargs["tech_plan"],
            index_text=kwargs["index_text"],
            history=history,
        )

    return _tool_loop(
        _call,
        {"git_diff": git_diff, "slug": slug,
         "feature_description": feature_description,
         "plan_text": plan_text, "tech_plan": tech_plan,
         "index_text": index_text, "history": ""},
        "mapper", slug, config, dispatcher,
    )


def invoke_preflight_mapper(file_listing: str, manifest_files: str,
                             config: HarnessConfig) -> MapperReport:
    """Returns MapperReport for pre-flight mapping."""
    _print_header("mapper", config, "__preflight__")
    client = _client_for_agent(config, "mapper")
    return client.PreflightMap(
        file_listing=file_listing,
        manifest_files=manifest_files,
        history="(first turn — no previous history)",
    )
