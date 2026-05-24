"""BAML agent loop — runs the full agentic pipeline using BAML instead of CrewAI.

Entry point: run_loop_baml(config) — mirrors run_loop() in loop.py with the same
orchestration order, vault file paths, and idempotency checks, but calls BAML
functions (single-shot for pure I/O agents, tool-loop for tool-using agents).
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from baml_agents import (
    invoke_architect,
    invoke_builder,
    invoke_clarifier,
    invoke_mapper,
    invoke_planner,
    invoke_preflight_mapper,
    invoke_refiner,
    invoke_research,
    invoke_verifier,
)
from config import HarnessConfig
from loop_helpers import (
    HarnessError,
    clear_verifier,
    decision_valid,
    feature_checked_off,
    open_questions,
    project_has_source,
    questions_has_entry,
    read_specs,
    research_done,
    safe_vault_path,
    sanitize_slug,
    vault_file_content,
    verifier_passed,
)
from vault import (
    append_log,
    check_off_feature,
    next_unchecked_feature,
    validate_vault,
    write_vault_file,
)

# BAML doesn't use CrewAI's subprocess timeout model; BAML clients have built-in
# HTTP timeouts. We still wrap single calls with a wall-clock limit as a safety net.
_WALL_TIMEOUT = 300  # 5 min — generous for long tool-call loops

# ---------------------------------------------------------------------------
# Pre-flight helpers (mirror loop.py)
# ---------------------------------------------------------------------------


def _clarifications_done(vault_path: str) -> bool:
    p = Path(vault_path) / "raw" / "clarifications.md"
    return p.exists() and "status: needs-answers" not in p.read_text()


def _write_clarifications(vault_path: str, questions: list[str]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "---", f"status: needs-answers", f"updated: {ts}", "---", "",
        "# Spec Clarifications", "", "## Questions", "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines += ["", "## Answers", "", "(to be filled in by the user)", ""]
    write_vault_file(vault_path, "raw/clarifications.md", "\n".join(lines))


def _write_clarifications_clean(vault_path: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    write_vault_file(
        vault_path, "raw/clarifications.md",
        f"---\nstatus: complete\nupdated: {ts}\n---\n\nNo ambiguities found — specs are ready.\n",
    )


def _write_answers(vault_path: str, answers: list[str]) -> None:
    p = Path(vault_path) / "raw" / "clarifications.md"
    text = p.read_text()
    answers_block = "## Answers\n\n" + "\n".join(
        f"{i + 1}. {a}" for i, a in enumerate(answers)
    ) + "\n"
    text = text.replace("status: needs-answers", "status: answered")
    text = text.replace("## Answers\n\n(to be filled in by the user)", answers_block.rstrip())
    p.write_text(text)


def _vault_mapped(vault_path: str) -> bool:
    return (Path(vault_path) / "map" / "structure.md").exists()


def _validate_specs(specs_dir: str):
    safe_dir = Path(specs_dir).resolve()
    if not any(safe_dir.glob("**/*")):
        raise HarnessError(f"Specs directory '{safe_dir.name}' is missing or empty.")


def _write_tech_plan(vault_path: str, slug: str, plan: Any) -> None:
    """Write TechPlan structured output to pending/plan-{slug}.md and raw/{slug}/TECH.md."""
    ts = datetime.now(timezone.utc).isoformat()

    # Build markdown from the structured plan
    lines = [
        "---", f"tags: [tech-spec]", f"feature: {slug}", f"updated: {ts}", "---", "",
        f"# TECH: {slug}", "",
        "## Context", "", plan.context, "",
    ]

    if plan.files_to_create:
        lines.append("## Files to create")
        for f in plan.files_to_create:
            lines.append(f"- {f.path} — {f.purpose}")
        lines.append("")

    if plan.files_to_modify:
        lines.append("## Files to modify")
        for f in plan.files_to_modify:
            lines.append(f"- {f.path} — {f.purpose}")
        lines.append("")

    lines += [
        "## Interfaces", "```", plan.interfaces, "```", "",
        "## Edge cases", "",
    ]
    for ec in plan.edge_cases:
        lines.append(f"- {ec}")
    lines.append("")

    lines += ["## Acceptance criteria mapping", ""]
    for cm in plan.criteria_mapping:
        lines.append(f"- Criterion {cm.criterion_number}: {cm.verification}")
    lines += ["", "## Deviations", "", "(left blank — Mapper fills this in after implementation)", ""]

    content = "\n".join(lines)
    write_vault_file(vault_path, f"pending/plan-{slug}.md", content)
    write_vault_file(vault_path, f"raw/{slug}/TECH.md", content)


def _write_decision(vault_path: str, slug: str, feature_name: str, decision: Any) -> None:
    """Write Decision to decisions/{slug}.md."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "---", f"tags: [decision]", f"feature: {slug}", f"updated: {ts}",
        f"chosen: {decision.chosen}", "---", "",
        f"# Decision: {feature_name}", "",
    ]
    for i, a in enumerate(decision.approaches, 1):
        lines += [
            f"## Approach {i} — {a.name}",
            "", a.description, "",
            f"**Score**: Simplicity: {a.simplicity}/5 | Completeness: {a.completeness}/5 | "
            f"Risk: {a.risk}/5 | Fit: {a.fit}/5", "",
        ]
    lines += [
        f"## Chosen: Approach {decision.chosen}",
        f"**Rationale**: {decision.rationale}", "",
    ]
    write_vault_file(vault_path, f"decisions/{slug}.md", "\n".join(lines))


def _write_research(vault_path: str, slug: str, feature_name: str,
                    research_type: str, findings: Any) -> None:
    """Write ResearchFindings to research/{slug}.md."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "---", f"tags: [research]", f"feature: {slug}", f"type: {research_type}",
        f"updated: {ts}", "---", "",
        f"# Research: {feature_name}", "",
        "## Findings", "",
    ]
    for i, f in enumerate(findings.findings, 1):
        url_line = f"**Source**: {f.source_url}" if f.source_url else f"**Confidence**: {f.confidence}"
        lines += [
            f"### {i}. {f.title}", url_line, f.insight, "",
            f"**Relevance**: {f.relevance}", "",
        ]
    if findings.recommendations:
        lines += ["## Recommendations", ""]
        for r in findings.recommendations:
            lines.append(f"- {r}")
        lines.append("")
    write_vault_file(vault_path, f"research/{slug}.md", "\n".join(lines))


def _write_verifier_report(vault_path: str, slug: str, report: Any) -> None:
    """Write VerifierReport to pending/verify-{slug}.md."""
    ts = datetime.now(timezone.utc).isoformat()
    if report.status.upper() == "PASSED":
        write_vault_file(vault_path, f"pending/verify-{slug}.md", "PASSED")
        # Also write questions entry
        write_vault_file(
            vault_path, "pending/questions.md",
            f"\n## {slug} — verify-pass — {ts}\nAll checks passed.\n",
            append=True,
        )
    else:
        lines = [
            "---", f"status: FAILED", f"feature: {slug}", "---", "",
            "## Failures", "",
        ]
        for f in report.failures:
            lines += [
                f"- **{f.check_type}** — `{f.command}`",
                f"  - Error: {f.error_message}",
                f"  - Cause: {f.likely_cause}",
                f"  - Criterion: {f.criterion_impact}",
                "",
            ]
        lines += ["## Fix hints", ""]
        for h in report.fix_hints:
            lines.append(f"- {h}")
        lines.append("")
        write_vault_file(vault_path, f"pending/verify-{slug}.md", "\n".join(lines))
        write_vault_file(
            vault_path, "pending/questions.md",
            f"\n## {slug} — verify-fail — {ts}\n" +
            "\n".join(f"- {h}" for h in report.fix_hints) + "\n",
            append=True,
        )


def _write_builder_questions(vault_path: str, slug: str, report: Any) -> None:
    """Write BuilderReport to pending/questions.md."""
    ts = datetime.now(timezone.utc).isoformat()
    lines = [f"## {slug} — {ts}", ""]
    if report.open_questions:
        for q in report.open_questions:
            lines.append(f"- [ ] {q}")
    if report.deviations:
        for d in report.deviations:
            lines.append(f"- Deviation: {d}")
    if not report.open_questions and not report.deviations:
        lines.append("(no open questions)")
    lines.append("")
    write_vault_file(vault_path, "pending/questions.md", "\n".join(lines), append=True)


def _preload_vault_context(vault_path: str, files: list[str]) -> str:
    parts = []
    for f in files:
        content = vault_file_content(vault_path, f)
        if content:
            parts.append(f"### {f}\n{content}")
    return "\n\n".join(parts) if parts else "(no vault context available)"


# ---------------------------------------------------------------------------
# Feature loop
# ---------------------------------------------------------------------------


def _feature_criteria_from_plan(plan_path: str, slug: str) -> str:
    """Extract acceptance criteria for a feature from pending/plan.md."""
    if not Path(plan_path).exists():
        return "(no plan available)"
    text = Path(plan_path).read_text()
    lines = text.splitlines()
    in_feature = False
    criteria = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"- [ ] {slug}:") or stripped.startswith(f"- [x] {slug}:"):
            in_feature = True
            continue
        if in_feature:
            if re.match(r"- \[[ x]\]", stripped):
                break
            m = re.match(r"\d+\.\s+(.+)", stripped)
            if m:
                criteria.append(m.group(1))
    return "\n".join(f"{i + 1}. {c}" for i, c in enumerate(criteria)) if criteria else "(no criteria found)"


_SOURCE_EXTENSIONS = {
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb",
    ".cs", ".cpp", ".c", ".h", ".hpp", ".php", ".kt", ".swift", ".scala",
    ".r", ".lua", ".zig", ".elm", ".ex", ".exs", ".erl", ".hs",
}


def _diff_has_source_changes(git_diff: str) -> bool:
    """Return True if the git diff includes source-code file changes (not just docs/config)."""
    import re
    # Check for diff headers that modify/create source files
    patterns = [
        r"^diff --git a/.*\.(py|ts|js|tsx|jsx|go|rs)$",
        r"^(---|\+\+\+) [ab]/.*\.(py|ts|js|tsx|jsx|go|rs)",
    ]
    for line in git_diff.splitlines():
        for pat in patterns:
            if re.search(pat, line, re.MULTILINE):
                return True
    return False


def _should_run_verifier(config: HarnessConfig, git_diff: str) -> bool:
    """Decide whether the Verifier should run.

    In prototype mode: skip if only docs/comments/config changed.
    In stable mode: always run if not explicitly disabled.
    """
    if config.no_verify:
        return False
    if config.maturity == "prototype":
        if not _diff_has_source_changes(git_diff):
            if config.verbose:
                print("  [verifier] skipped — no source changes in diff (prototype mode)")
            return False
    return True


def _inline_mapper_checkoff(config: HarnessConfig, slug: str, description: str) -> None:
    """Lightweight mapper: mark feature complete + append log. No LLM call.

    Used in prototype mode to avoid per-feature BAML Mapper overhead.
    Full Mapper runs once at end of loop.
    """
    plan_path = safe_vault_path(config.vault_path, "pending", "plan.md")
    if not feature_checked_off(plan_path, slug):
        check_off_feature(str(plan_path), slug)
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"\n## {ts} — mapper (inline) — {slug}\nFeature {slug} ({description}) checked off inline (prototype mode). Full sync deferred to end of run.\n"
    write_vault_file(config.vault_path, "log.md", entry, append=True)


def _end_of_run_mapper(config: HarnessConfig, slugs: list[str]) -> None:
    """Run a single batched Mapper pass for all features built in prototype mode.

    Reads git diff, index, and all TECH.md files; has the LLM update entities,
    structure, dependencies, entrypoints, index, and deviations in one call.
    """
    if not slugs:
        return

    try:
        git_diff = subprocess.run(
            ["git", "diff", "HEAD~" + str(max(1, len(slugs)))],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        git_diff = "(git diff unavailable)"

    index_text = vault_file_content(config.vault_path, "index.md", "(no index)")

    # Concatenate TECH plan snippets for each feature
    plan_snippets = []
    for slug in slugs:
        plan = vault_file_content(config.vault_path, f"pending/plan-{slug}.md")
        tech = vault_file_content(config.vault_path, f"raw/{slug}/TECH.md")
        if plan or tech:
            plan_snippets.append(f"### {slug}\nPlan:\n{plan}\n\nTech:\n{tech}")
    plan_text = "\n\n".join(plan_snippets) if plan_snippets else "(no plans)"

    # Build a combined description
    feature_list = ", ".join(slugs)

    result = invoke_mapper(
        git_diff, feature_list, f"Batch sync for: {feature_list}",
        plan_text, "<batched — see individual TECH.md files>",
        index_text, config,
    )
    append_log(config.vault_path, "mapper", "__end_of_run__",
               f"End-of-run Mapper sync complete. {len(slugs)} features updated. "
               f"Entities: {len(result.entities_updated)}. {result.log_entry}")
    if config.verbose:
        print(f"  [mapper] end-of-run sync complete — {len(slugs)} features, "
              f"{len(result.entities_updated)} entities")


def run_loop_baml(config: HarnessConfig) -> int:
    import re
    try:
        validate_vault(config.vault_path)
        _validate_specs(config.specs_dir)
    except HarnessError as e:
        print(f"wiki4llm: {e}")
        return 1

    plan_path = safe_vault_path(config.vault_path, "pending", "plan.md")

    # Pre-flight mapper — runs once if vault isn't mapped and source files exist
    if not config.dry_run and not config.force_remap and not _vault_mapped(config.vault_path):
        if not project_has_source(config.project_root, config.specs_dir):
            if config.verbose:
                print("[mapper] pre-flight skipped — no source files found")
        else:
            try:
                file_listing = subprocess.run(
                    ["find", ".", "-type", "f"], capture_output=True, text=True, timeout=15
                ).stdout
            except (subprocess.TimeoutExpired, FileNotFoundError):
                file_listing = "(file listing failed)"
            manifests = _preload_vault_context(
                config.vault_path,
                list(Path(".").glob("package.json"))
                + list(Path(".").glob("pyproject.toml"))
                + list(Path(".").glob("Cargo.toml"))
                + list(Path(".").glob("go.mod")),
            )
            result = invoke_preflight_mapper(file_listing, manifests, config)
            append_log(config.vault_path, "mapper", "__preflight__", "Pre-flight map complete.")
            if config.verbose:
                print(f"[mapper] pre-flight done — {len(result.entities_updated)} entities mapped")

    # Spec clarifier — runs once before the Planner
    if not config.skip_clarify and not config.dry_run:
        if _clarifications_done(config.vault_path):
            if config.verbose:
                print("[clarifier] skipped — raw/clarifications.md already complete")
        else:
            specs_content = read_specs(config.specs_dir)
            try:
                result = invoke_clarifier(specs_content, config)
            except Exception as e:
                print(f"wiki4llm: clarifier failed: {e}")
                return 1

            if not result.has_ambiguities or not result.questions:
                _write_clarifications_clean(config.vault_path)
                append_log(config.vault_path, "clarifier", "__clarify__",
                           "Specs reviewed — no ambiguities found.")
            else:
                questions = [f"**[{q.feature}]** {q.question} — {q.context}" for q in result.questions]
                _write_clarifications(config.vault_path, questions)

                print("\n" + "\u2500" * 60)
                print("wiki4llm: The Clarifier found ambiguities in your specs.")
                print("Answer each question (press Enter to skip and let agents infer):")
                print("\u2500" * 60 + "\n")

                answers = []
                for q in questions:
                    print(f"  {q}")
                    answer = input("  > ").strip()
                    answers.append(answer if answer else "(no answer — agents should infer from context)")
                    print()

                _write_answers(config.vault_path, answers)
                append_log(config.vault_path, "clarifier", "__clarify__",
                           f"Specs reviewed. {len(questions)} question(s) answered by user.")
                print("wiki4llm: Answers recorded. Continuing...\n")

    # Planner — runs if plan.md is missing or empty
    plan_text_lines = plan_path.read_text().splitlines() if plan_path.exists() else []
    plan_has_any_feature = any(re.match(r"- \[.\]", line) for line in plan_text_lines)
    if not plan_path.exists() or not plan_has_any_feature:
        specs_content = read_specs(config.specs_dir)
        clarifications = vault_file_content(config.vault_path, "raw/clarifications.md")
        existing_plan = vault_file_content(config.vault_path, "pending/plan.md", "(no existing plan)")
        try:
            result = invoke_planner(specs_content, clarifications, existing_plan, config)
        except Exception as e:
            print(f"wiki4llm: planner failed: {e}")
            return 1

        # Write plan.md from FeaturePlan
        ts = datetime.now(timezone.utc).isoformat()
        lines = [
            f"# Feature Plan", f"updated: {ts}", "",
        ]
        for f in result.features:
            lines.append(f"- [ ] {f.slug}: {f.description}")
            for i, ac in enumerate(f.acceptance_criteria, 1):
                lines.append(f"  {i}. {ac}")
            lines.append("")
        write_vault_file(config.vault_path, "pending/plan.md", "\n".join(lines))
        append_log(config.vault_path, "planner", "__init__", "Plan initialized from specs.")
    else:
        if config.verbose:
            print("[planner] skipped — plan.md already exists")

    # Verify the Planner actually produced a feature list
    if next_unchecked_feature(str(plan_path)) is None:
        print("wiki4llm: No features found in pending/plan.md — add spec files to specs/ and re-run.")
        return 1

    if config.dry_run:
        print("\nwiki4llm: Dry run — features found in specs/:\n")
        plan_text = plan_path.read_text() if plan_path.exists() else ""
        for line in plan_text.splitlines():
            m = re.match(r"- \[.\] (.+)", line)
            if m:
                print(f"  {line.strip()}")
        print("\nRun without --dry-run to execute.")
        return 0

    features_completed = 0
    deferred_mapper_slugs: list[str] = []

    while True:
        feature = next_unchecked_feature(str(plan_path))
        if feature is None:
            break

        if config.max_features is not None and features_completed >= config.max_features:
            print(f"wiki4llm: Reached --max-features limit ({config.max_features}).")
            break

        slug, description = feature
        slug = sanitize_slug(slug)

        # Ensure raw/<slug>/ exists for TECH.md
        (Path(config.vault_path) / "raw" / slug).mkdir(parents=True, exist_ok=True)

        try:
            # Research
            if config.research.enabled and not research_done(config.vault_path, slug):
                vault_overview = vault_file_content(config.vault_path, "overview.md")
                vault_structure = vault_file_content(config.vault_path, "map/structure.md")
                result = invoke_research(
                    description, slug, config.research.type,
                    config.research.prompt or None,
                    vault_overview, vault_structure, config,
                )
                _write_research(config.vault_path, slug, description,
                                config.research.type, result)
                append_log(config.vault_path, "research", slug,
                           f"Research complete ({config.research.type}). See research/{slug}.md.")

            # Refiner
            use_refiner = (
                not config.no_refine
                and "[no-refine]" not in description
                and not decision_valid(config.vault_path, slug)
            )
            if use_refiner:
                vault_overview = vault_file_content(config.vault_path, "overview.md")
                vault_structure = vault_file_content(config.vault_path, "map/structure.md")
                vault_deps = vault_file_content(config.vault_path, "map/dependencies.md")
                criteria = _feature_criteria_from_plan(str(plan_path), slug)
                research = vault_file_content(config.vault_path, f"research/{slug}.md") or None
                result = invoke_refiner(
                    description, slug, vault_overview, vault_structure,
                    vault_deps, criteria, research, config,
                )
                _write_decision(config.vault_path, slug, description, result)
                append_log(config.vault_path, "refiner", slug,
                           f"Evaluated 3 approaches. See decisions/{slug}.md.")

            # Architect
            if not safe_vault_path(config.vault_path, "pending", f"plan-{slug}.md").exists():
                vault_structure = vault_file_content(config.vault_path, "map/structure.md")
                vault_entrypoints = vault_file_content(config.vault_path, "map/entrypoints.md")
                criteria = _feature_criteria_from_plan(str(plan_path), slug)
                decision_text = (
                    vault_file_content(config.vault_path, f"decisions/{slug}.md")
                    if not config.no_refine else None
                )
                research = vault_file_content(config.vault_path, f"research/{slug}.md") or None
                result = invoke_architect(
                    description, slug, vault_structure, vault_entrypoints,
                    criteria, decision_text, research, config,
                )
                _write_tech_plan(config.vault_path, slug, result)
                append_log(config.vault_path, "architect", slug,
                           f"Implementation plan written to pending/plan-{slug}.md.")

            # Builder -> Verifier loop
            for verify_attempt in range(config.verifier_retries + 1):
                if not verifier_passed(config.vault_path, slug):
                    if verify_attempt > 0:
                        clear_verifier(config.vault_path, slug)
                    if not questions_has_entry(config.vault_path, slug):
                        tech_plan = vault_file_content(
                            config.vault_path, f"pending/plan-{slug}.md", ""
                        )
                        decision_text = vault_file_content(
                            config.vault_path, f"decisions/{slug}.md"
                        ) or None
                        result = invoke_builder(
                            tech_plan, decision_text, slug, description, config,
                        )
                        _write_builder_questions(config.vault_path, slug, result)
                        if result.commit_made or not config.verbose:
                            append_log(
                                config.vault_path, "builder", slug,
                                f"Feature implemented and committed "
                                f"(attempt {verify_attempt + 1}).",
                            )

                if config.no_verify or verifier_passed(config.vault_path, slug):
                    break

                if verify_attempt == config.verifier_retries:
                    append_log(config.vault_path, "verifier", slug,
                               f"[WARN] Tests still failing after {config.verifier_retries} retries. Continuing.")
                    break

                # Gather git diff for verifier short-circuit check
                try:
                    git_diff_latest = subprocess.run(
                        ["git", "diff", "HEAD~1"], capture_output=True, text=True, timeout=30
                    ).stdout
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    git_diff_latest = ""

                if not _should_run_verifier(config, git_diff_latest):
                    break

                tech_plan = vault_file_content(
                    config.vault_path, f"pending/plan-{slug}.md", ""
                )
                result = invoke_verifier(tech_plan, slug, config)
                _write_verifier_report(config.vault_path, slug, result)
                append_log(config.vault_path, "verifier", slug,
                           f"Tests run. See pending/verify-{slug}.md.")

                if verifier_passed(config.vault_path, slug):
                    break

            # Human checkpoint
            if config.interactive:
                questions = open_questions(config.vault_path, slug)
                if questions:
                    print(f'\n[wiki4llm] Feature "{description}" — Builder has questions:\n')
                    for i, q in enumerate(questions, 1):
                        print(f"  {i}. {q}")
                    print("\nEnter answer(s), or press Enter to let the Mapper resolve with best-guess:")
                    response = input("> ").strip()
                    if response:
                        write_vault_file(
                            config.vault_path, "pending/questions.md",
                            f"\n### {slug} — human answer\n{response}\n", append=True,
                        )

            # Mapper — inline in prototype mode, full BAML in stable mode
            if not feature_checked_off(plan_path, slug):
                if config.maturity == "prototype":
                    _inline_mapper_checkoff(config, slug, description)
                    deferred_mapper_slugs.append(slug)
                else:
                    try:
                        git_diff = subprocess.run(
                            ["git", "diff", "HEAD~1"], capture_output=True, text=True, timeout=30
                        ).stdout
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        git_diff = "(git diff unavailable)"
                    plan_text = vault_file_content(config.vault_path, f"pending/plan-{slug}.md", "")
                    tech_plan = vault_file_content(config.vault_path, f"raw/{slug}/TECH.md", "")
                    index_text = vault_file_content(config.vault_path, "index.md", "(no index)")

                    result = invoke_mapper(
                        git_diff, slug, description, plan_text, tech_plan, index_text, config,
                    )

                    if not feature_checked_off(plan_path, slug):
                        check_off_feature(str(plan_path), slug)
                    append_log(config.vault_path, "mapper", slug,
                               f"Vault updated. Feature {slug} marked complete.")

        except (HarnessError, Exception) as e:
            import traceback
            if config.verbose:
                traceback.print_exc()
            print(f"wiki4llm: {e}")
            return 1

        features_completed += 1

    # End-of-run batched Mapper for prototype mode
    if deferred_mapper_slugs:
        if config.verbose:
            print(f"\n  [mapper] running end-of-run sync for {len(deferred_mapper_slugs)} features...")
        try:
            _end_of_run_mapper(config, deferred_mapper_slugs)
        except (HarnessError, Exception) as e:
            if config.verbose:
                import traceback
                traceback.print_exc()
            print(f"wiki4llm: end-of-run mapper failed (non-fatal): {e}")

    print("wiki4llm: All features complete.")
    return 0
