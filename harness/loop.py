import re
import sys
import time
import multiprocessing
from pathlib import Path
from crewai import Crew
from pydantic import ValidationError

from config import HarnessConfig
from agents import make_agents, context_percent
from tasks import make_tasks, make_clarifier_task, make_preflight_mapper_task
from ui import agent_spinner, print_over_spinner
from vault import (
    next_unchecked_feature,
    check_off_feature,
    append_log,
    write_vault_file,
    read_vault_slice,
)

MAX_RETRIES = 2


class HarnessError(Exception):
    pass


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _sanitize_slug(slug: str) -> str:
    """Allow only alphanumerics and hyphens to prevent path traversal via slug."""
    sanitized = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    if not sanitized:
        raise HarnessError(f"Invalid slug: {slug!r}")
    return sanitized


def validate_vault(vault_path: str):
    root = Path(vault_path).resolve()
    for d in ["raw/assets", "map", "entities", "decisions", "pending", "research"]:
        (root / d).mkdir(parents=True, exist_ok=True)


def _clarifications_done(vault_path: str) -> bool:
    p = Path(vault_path) / "raw" / "clarifications.md"
    return p.exists() and "status: needs-answers" not in p.read_text()


def _clarifications_need_answers(vault_path: str) -> bool:
    p = Path(vault_path) / "raw" / "clarifications.md"
    return p.exists() and "status: needs-answers" in p.read_text()


def _write_answers(vault_path: str, answers: list[str]) -> None:
    p = Path(vault_path) / "raw" / "clarifications.md"
    text = p.read_text()
    answers_block = "## Answers\n\n" + "\n".join(
        f"{i + 1}. {a}" for i, a in enumerate(answers)
    ) + "\n"
    text = re.sub(r"## Answers\n\n\(to be filled in by the user\)", answers_block, text)
    text = text.replace("status: needs-answers", "status: answered")
    p.write_text(text)


def _read_specs(specs_dir: str) -> str:
    """Read all spec files and return their contents concatenated with headers."""
    safe_dir = Path(specs_dir).resolve()
    parts = []
    for f in sorted(safe_dir.rglob("*")):
        if f.is_file() and f.suffix in (".md", ".txt", ".rst", ".yaml", ".yml", ".json"):
            rel = f.relative_to(safe_dir)
            try:
                parts.append(f"### {rel}\n{f.read_text()}")
            except (OSError, UnicodeDecodeError):
                pass
    return "\n\n".join(parts) if parts else "(no spec files found)"


def _write_clarifications(vault_path: str, questions: list[str]) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    lines = [f"---", f"status: needs-answers", f"updated: {ts}", f"---", "",
             "# Spec Clarifications", "", "## Questions", ""]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines += ["", "## Answers", "", "(to be filled in by the user)", ""]
    write_vault_file(vault_path, "raw/clarifications.md", "\n".join(lines))


def _write_clarifications_clean(vault_path: str) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    content = f"---\nstatus: complete\nupdated: {ts}\n---\n\nNo ambiguities found — specs are ready.\n"
    write_vault_file(vault_path, "raw/clarifications.md", content)


def _vault_mapped(vault_path: str) -> bool:
    return (Path(vault_path) / "map" / "structure.md").exists()


def _project_has_source(project_root: str, specs_dir: str) -> bool:
    """Return True if there are non-spec source files in the project."""
    root = Path(project_root).resolve()
    specs = Path(specs_dir).resolve()
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        # Skip hidden dirs, specs dir, and common non-source dirs
        parts = f.parts
        if any(p.startswith(".") for p in parts[len(root.parts):]):
            continue
        try:
            f.relative_to(specs)
            continue  # inside specs dir
        except ValueError:
            pass
        if f.suffix in (".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
                        ".java", ".rb", ".cs", ".cpp", ".c", ".php", ".kt"):
            return True
    return False


def run_preflight_mapper(agents: dict, config: HarnessConfig) -> int:
    """Map the existing codebase into the vault before any other agent runs."""
    if not config.force_remap and _vault_mapped(config.vault_path):
        if config.verbose:
            print("[mapper] pre-flight skipped — map/structure.md already exists")
        return 0

    if not _project_has_source(config.project_root, config.specs_dir):
        if config.verbose:
            print("[mapper] pre-flight skipped — no source files found")
        return 0

    preflight_tasks = {"mapper": make_preflight_mapper_task(agents, config)}
    try:
        with agent_spinner("mapper", config.verbose, model=config.model_for("mapper"),
                           trace=config.trace, vault_path=config.vault_path,
                           slug="__preflight__") as stats:
            result = run_with_retry(agents, preflight_tasks, "mapper", config, "__preflight__",
                                    pause_event=stats.get("pause_event"))
            stats["usage"] = getattr(result, "token_usage", None)
            stats["ctx_pct"] = context_percent(config.model_for("mapper"), stats["usage"])
        append_log(config.vault_path, "mapper", "__preflight__", "Pre-flight map complete.")
    except HarnessError as e:
        print(f"wiki4llm: pre-flight mapper failed: {e}")
        return 1
    return 0


def run_spec_clarifier(agents: dict, config: HarnessConfig) -> int:
    """One-time pre-flight: harness reads specs, LLM surfaces questions, user answers, harness writes vault."""
    if _clarifications_done(config.vault_path):
        if config.verbose:
            print("[clarifier] skipped — raw/clarifications.md already complete")
        return 0

    specs_content = _read_specs(config.specs_dir)
    clarifier_task = make_clarifier_task(agents, config, specs_content)

    try:
        with agent_spinner("clarifier", config.verbose, model=config.model_for("clarifier"),
                           trace=config.trace, vault_path=config.vault_path, slug="__clarify__") as stats:
            result = run_with_retry(agents, {"clarifier": clarifier_task}, "clarifier", config,
                                    "__clarify__", pause_event=stats.get("pause_event"))
            stats["usage"] = getattr(result, "token_usage", None)
            stats["ctx_pct"] = context_percent(config.model_for("clarifier"), stats["usage"])
    except HarnessError as e:
        print(f"wiki4llm: clarifier failed: {e}")
        return 1

    raw_output = getattr(result, "raw", "").strip()

    if not raw_output or "NO_QUESTIONS" in raw_output:
        _write_clarifications_clean(config.vault_path)
        append_log(config.vault_path, "clarifier", "__clarify__", "Specs reviewed — no ambiguities found.")
        return 0

    # Parse numbered questions from LLM output
    questions = [
        line.strip() for line in raw_output.splitlines()
        if re.match(r"^\d+[.)]", line.strip())
    ]
    if not questions:
        _write_clarifications_clean(config.vault_path)
        append_log(config.vault_path, "clarifier", "__clarify__", "Specs reviewed — no questions parsed.")
        return 0

    _write_clarifications(config.vault_path, questions)

    # Present questions to the user
    print("\n" + "─" * 60)
    print("wiki4llm: The Clarifier found ambiguities in your specs.")
    print("Answer each question (press Enter to skip and let agents infer):")
    print("─" * 60 + "\n")

    answers = []
    for q in questions:
        print(f"  {q}")
        answer = input("  > ").strip()
        answers.append(answer if answer else "(no answer — agents should infer from context)")
        print()

    _write_answers(config.vault_path, answers)
    append_log(config.vault_path, "clarifier", "__clarify__",
               f"Specs reviewed. {len(questions)} question(s) answered by user. See raw/clarifications.md.")
    print("wiki4llm: Answers recorded. Continuing...\n")
    return 0


def _unused_scaffold_stub():
    for fname, content in [
        ("index.md", "# Index\n\n"),
        ("log.md", "# Log\n\n"),
        ("overview.md", "# Overview\n\n"),
        ("pending/plan.md", "# Feature Plan\n\n"),
        ("pending/questions.md", "# Pending Questions\n\n"),
    ]:
        p = root / fname
        if not p.exists():
            p.write_text(content)


def validate_specs(specs_dir: str):
    safe_dir = Path(specs_dir).resolve()
    files = [f for f in safe_dir.glob("**/*") if f.is_file()]
    if not files:
        raise HarnessError(f"Specs directory '{safe_dir.name}' is missing or empty.")


def _list_to_str(raw_list: list) -> str:
    """Flatten a list of tool-call objects (e.g. GLM) into a plain string."""
    parts = []
    for item in raw_list:
        fn = getattr(item, "function", None)
        if fn is not None:
            parts.append(str(getattr(fn, "arguments", fn)))
        else:
            parts.append(str(item))
    return " ".join(parts)


_EMPTY_RESPONSE_PHRASES = (
    "invalid response from llm call - none or empty",
    "none or empty",
    "litellm.exceptions.apierror",
)


def _is_empty_response(exc: Exception) -> bool:
    return any(p in str(exc).lower() for p in _EMPTY_RESPONSE_PHRASES)


# Wall-clock timeout for a single agent task (seconds).
# Covers hung streaming calls that never raise — the HTTP-level LLM timeout
# only fires on response *start*, not on a stalled mid-stream completion.
_AGENT_WALL_TIMEOUT = 120  # 2 min default; override via config.agent_timeout


def _run_agent(agents: dict, tasks: dict, agent_name: str, verbose: bool = False):
    crew = Crew(agents=[agents[agent_name]], tasks=[tasks[agent_name]], verbose=verbose)
    try:
        return crew.kickoff()
    except ValidationError as exc:
        # Some models (e.g. GLM) return a list of tool-call objects as the raw
        # output instead of a string, causing TaskOutput.raw validation to fail.
        for err in exc.errors():
            if err.get("loc") == ("raw",) and isinstance(err.get("input"), list):
                coerced = _list_to_str(err["input"])
                from crewai.tasks.task_output import TaskOutput
                return TaskOutput(
                    description=tasks[agent_name].description,
                    raw=coerced,
                    agent=agents[agent_name].role,
                )
        raise


def _run_agent_worker(agents: dict, tasks: dict, agent_name: str, result_queue: multiprocessing.Queue,
                      verbose: bool = False):
    try:
        result = _run_agent(agents, tasks, agent_name, verbose)
        result_queue.put(("ok", result))
    except (RuntimeError, ValueError, TypeError, OSError) as e:
        result_queue.put(("err", e))


def _run_agent_with_timeout(agents: dict, tasks: dict, agent_name: str, timeout: int,
                             verbose: bool = False):
    q: multiprocessing.Queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=_run_agent_worker, args=(agents, tasks, agent_name, q, verbose))
    p.start()
    # Read the result BEFORE joining. If the result is large, the child blocks
    # on the pipe write until the parent drains it — p.join() first would deadlock.
    try:
        status, value = q.get(timeout=timeout)
    except multiprocessing.queues.Empty:
        # Timed out waiting for a result — kill the child and retry.
        if p.is_alive():
            p.kill()
        p.join()
        raise TimeoutError(
            f"{agent_name} exceeded wall-clock timeout ({timeout}s) — "
            "hung streaming call killed. Will retry."
        )
    p.join()
    if status == "err":
        raise value
    return value


# Ollama cloud models (minimax-m2, GLM5.1, etc.) occasionally return empty
# responses or hang mid-stream. Both are transient — a short wait + retry recovers them.
_STALL_MAX_RETRIES = 5
_STALL_BACKOFF = 5  # seconds between stall retries


def run_with_retry(agents: dict, tasks: dict, agent_name: str, config: HarnessConfig, slug: str,
                   pause_event=None):
    wall_timeout = getattr(config, "agent_timeout", _AGENT_WALL_TIMEOUT)
    stall_attempts = 0
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _run_agent_with_timeout(agents, tasks, agent_name, wall_timeout, verbose=config.verbose)
        except (RuntimeError, ValueError, TypeError, OSError, TimeoutError) as e:
            is_stall = _is_empty_response(e) or isinstance(e, TimeoutError)
            if is_stall and stall_attempts < _STALL_MAX_RETRIES:
                stall_attempts += 1
                kind = "timeout" if isinstance(e, TimeoutError) else "empty response"
                warn = f"  ⚠ [{agent_name}] {kind} — self-healing, retry {stall_attempts}/{_STALL_MAX_RETRIES} in {_STALL_BACKOFF}s..."
                if pause_event is not None:
                    print_over_spinner(pause_event, warn)
                else:
                    sys.stdout.write(f"\r{warn}\n")
                    sys.stdout.flush()
                append_log(config.vault_path, agent_name, slug,
                           f"[WARN] {kind} (attempt {stall_attempts}/{_STALL_MAX_RETRIES}). Self-healing retry scheduled.")
                time.sleep(_STALL_BACKOFF)
                continue
            if attempt == MAX_RETRIES:
                append_log(config.vault_path, agent_name, slug,
                           f"[ERROR] Failed after {MAX_RETRIES} retries: {e}")
                _safe_vault_path(config.vault_path, "pending", "questions.md")
                write_vault_file(config.vault_path, "pending/questions.md",
                                 f"\n## {slug} — [ERROR]\n{e}\n", append=True)
                raise HarnessError(f"{agent_name} failed: {e}")
            time.sleep(2 ** attempt)


def _safe_vault_path(vault_path: str, *parts: str) -> Path:
    """Resolve a path inside the vault and raise if it escapes the root."""
    root = Path(vault_path).resolve()
    full = (root / Path(*parts)).resolve()
    if not full.is_relative_to(root):
        raise HarnessError(f"Path traversal blocked: {Path(*parts)}")
    return full


def _decision_valid(vault_path: str, slug: str) -> bool:
    p = _safe_vault_path(vault_path, "decisions", f"{slug}.md")
    return p.exists() and "## Chosen:" in p.read_text()


def _research_done(vault_path: str, slug: str) -> bool:
    p = _safe_vault_path(vault_path, "research", f"{slug}.md")
    return p.exists() and "## Findings" in p.read_text()


def _questions_has_entry(vault_path: str, slug: str) -> bool:
    p = _safe_vault_path(vault_path, "pending", "questions.md")
    return p.exists() and f"## {slug}" in p.read_text()


def _verifier_passed(vault_path: str, slug: str) -> bool:
    p = _safe_vault_path(vault_path, "pending", f"verify-{slug}.md")
    return p.exists() and bool(re.search(r"\bPASSED\b", p.read_text()))


def _verifier_failed(vault_path: str, slug: str) -> bool:
    p = _safe_vault_path(vault_path, "pending", f"verify-{slug}.md")
    return p.exists() and "status: FAILED" in p.read_text()


def _clear_verifier(vault_path: str, slug: str):
    p = _safe_vault_path(vault_path, "pending", f"verify-{slug}.md")
    if p.exists():
        p.unlink()


def _feature_checked_off(plan_path: Path, slug: str) -> bool:
    if not plan_path.exists():
        return False
    text = plan_path.read_text()
    return bool(re.search(rf"- \[x\] [^\n]*{re.escape(slug)}", text))


def _open_questions(vault_path: str, slug: str) -> list:
    p = _safe_vault_path(vault_path, "pending", "questions.md")
    if not p.exists():
        return []
    lines = p.read_text().splitlines()
    in_section = False
    questions = []
    for line in lines:
        if line.startswith(f"## {slug}"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            if line.startswith("- [ ]"):
                questions.append(line[6:].strip())
    return questions


def pause_for_human(config: HarnessConfig, slug: str, description: str):
    questions = _open_questions(config.vault_path, slug)
    if not questions:
        return
    print(f'\n[wiki4llm] Feature "{description}" — Builder has questions:\n')
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")
    print("\nEnter answer(s), or press Enter to let the Mapper resolve with best-guess:")
    response = input("> ").strip()
    if response:
        write_vault_file(config.vault_path, "pending/questions.md",
                         f"\n### {slug} — human answer\n{response}\n", append=True)


def run_loop(config: HarnessConfig) -> int:
    try:
        validate_vault(config.vault_path)
        validate_specs(config.specs_dir)
    except HarnessError as e:
        print(f"wiki4llm: {e}")
        return 1

    plan_path = _safe_vault_path(config.vault_path, "pending", "plan.md")
    agents = make_agents(config)

    # Pre-flight mapper — runs once if vault isn't mapped and source files exist
    if not config.dry_run:
        rc = run_preflight_mapper(agents, config)
        if rc != 0:
            return rc

    # Spec clarifier — runs once before the Planner, skipped if --skip-clarify or already done
    if not config.skip_clarify and not config.dry_run:
        rc = run_spec_clarifier(agents, config)
        if rc != 0:
            return rc

    plan_text_lines = plan_path.read_text().splitlines() if plan_path.exists() else []
    plan_has_any_feature = any(re.match(r"- \[.\]", line) for line in plan_text_lines)
    plan_needs_init = not plan_path.exists() or not plan_has_any_feature
    if plan_needs_init:
        planner_tasks = make_tasks(agents, config, ("__init__", "Initialize project plan"))
        try:
            with agent_spinner("planner", config.verbose, model=config.model_for("planner"),
                               trace=config.trace, vault_path=config.vault_path, slug="__init__") as stats:
                result = run_with_retry(agents, planner_tasks, "planner", config, "__init__",
                                        pause_event=stats.get("pause_event"))
                stats["usage"] = getattr(result, "token_usage", None)
                stats["ctx_pct"] = context_percent(config.model_for("planner"), stats["usage"])
            append_log(config.vault_path, "planner", "__init__", "Plan initialized from specs.")
        except HarnessError as e:
            print(f"wiki4llm: {e}")
            return 1
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

    while True:
        feature = next_unchecked_feature(str(plan_path))
        if feature is None:
            print("wiki4llm: All features complete.")
            return 0

        if config.max_features is not None and features_completed >= config.max_features:
            print(f"wiki4llm: Reached --max-features limit ({config.max_features}).")
            return 0

        slug, description = feature
        slug = _sanitize_slug(slug)
        # Ensure raw/<slug>/ exists for TECH.md
        (Path(config.vault_path) / "raw" / slug).mkdir(parents=True, exist_ok=True)
        tasks = make_tasks(agents, config, (slug, description))

        try:
            # Research (optional, runs before Refiner)
            if config.research.enabled and not _research_done(config.vault_path, slug):
                with agent_spinner("research", config.verbose, model=config.model_for("research"),
                                   trace=config.trace, vault_path=config.vault_path, slug=slug) as stats:
                    result = run_with_retry(agents, tasks, "research", config, slug,
                                            pause_event=stats.get("pause_event"))
                    stats["usage"] = getattr(result, "token_usage", None)
                    stats["ctx_pct"] = context_percent(config.model_for("research"), stats["usage"])
                append_log(config.vault_path, "research", slug,
                           f"Research complete ({config.research.type}). See research/{slug}.md.")

            # Refiner
            use_refiner = (
                not config.no_refine
                and "[no-refine]" not in description
                and not _decision_valid(config.vault_path, slug)
            )
            if use_refiner:
                with agent_spinner("refiner", config.verbose, model=config.model_for("refiner"),
                                   trace=config.trace, vault_path=config.vault_path, slug=slug) as stats:
                    result = run_with_retry(agents, tasks, "refiner", config, slug,
                                            pause_event=stats.get("pause_event"))
                    stats["usage"] = getattr(result, "token_usage", None)
                    stats["ctx_pct"] = context_percent(config.model_for("refiner"), stats["usage"])
                append_log(config.vault_path, "refiner", slug,
                           f"Evaluated 3 approaches. See decisions/{slug}.md.")

            # Architect
            if not _safe_vault_path(config.vault_path, "pending", f"plan-{slug}.md").exists():
                with agent_spinner("architect", config.verbose, model=config.model_for("architect"),
                                   trace=config.trace, vault_path=config.vault_path, slug=slug) as stats:
                    result = run_with_retry(agents, tasks, "architect", config, slug,
                                            pause_event=stats.get("pause_event"))
                    stats["usage"] = getattr(result, "token_usage", None)
                    stats["ctx_pct"] = context_percent(config.model_for("architect"), stats["usage"])
                append_log(config.vault_path, "architect", slug,
                           f"Implementation plan written to pending/plan-{slug}.md.")

            # Builder -> Verifier loop
            def _clear_builder_entry(vault_path: str, slug: str):
                """Remove the builder's questions entry so it re-runs on retry."""
                p = _safe_vault_path(vault_path, "pending", "questions.md")
                if not p.exists():
                    return
                text = p.read_text()
                # Remove the section headed by ## <slug> up to the next ## or EOF
                text = re.sub(
                    rf"(?m)^## {re.escape(slug)}[^\n]*\n.*?(?=^## |\Z)",
                    "",
                    text,
                    flags=re.DOTALL,
                )
                p.write_text(text)

            for verify_attempt in range(config.verifier_retries + 1):
                if not _verifier_passed(config.vault_path, slug):
                    if verify_attempt > 0:
                        # Clear both verifier result and builder's questions entry
                        # so the builder re-runs against the failure hints.
                        _clear_verifier(config.vault_path, slug)
                        _clear_builder_entry(config.vault_path, slug)
                    if not _questions_has_entry(config.vault_path, slug):
                        with agent_spinner("builder", config.verbose, model=config.model_for("builder"),
                                           trace=config.trace, vault_path=config.vault_path, slug=slug) as stats:
                            result = run_with_retry(agents, tasks, "builder", config, slug,
                                                    pause_event=stats.get("pause_event"))
                            stats["usage"] = getattr(result, "token_usage", None)
                            stats["ctx_pct"] = context_percent(config.model_for("builder"), stats["usage"])
                        append_log(config.vault_path, "builder", slug,
                                   f"Feature implemented and committed (attempt {verify_attempt + 1}).")

                if config.no_verify or _verifier_passed(config.vault_path, slug):
                    break

                if verify_attempt == config.verifier_retries:
                    append_log(config.vault_path, "verifier", slug,
                               f"[WARN] Tests still failing after {config.verifier_retries} retries. Continuing.")
                    break

                with agent_spinner("verifier", config.verbose, model=config.model_for("verifier"),
                                   trace=config.trace, vault_path=config.vault_path, slug=slug) as stats:
                    result = run_with_retry(agents, tasks, "verifier", config, slug,
                                            pause_event=stats.get("pause_event"))
                    stats["usage"] = getattr(result, "token_usage", None)
                    stats["ctx_pct"] = context_percent(config.model_for("verifier"), stats["usage"])
                append_log(config.vault_path, "verifier", slug,
                           f"Tests run. See pending/verify-{slug}.md.")

                if _verifier_passed(config.vault_path, slug):
                    break

            # Human checkpoint
            if config.interactive:
                pause_for_human(config, slug, description)

            # Mapper
            if not _feature_checked_off(plan_path, slug):
                with agent_spinner("mapper", config.verbose, model=config.model_for("mapper"),
                                   trace=config.trace, vault_path=config.vault_path, slug=slug) as stats:
                    result = run_with_retry(agents, tasks, "mapper", config, slug,
                                            pause_event=stats.get("pause_event"))
                    stats["usage"] = getattr(result, "token_usage", None)
                    stats["ctx_pct"] = context_percent(config.model_for("mapper"), stats["usage"])
                # Force check-off regardless of whether the agent wrote it —
                # the harness owns idempotency, not the LLM.
                if not _feature_checked_off(plan_path, slug):
                    check_off_feature(str(plan_path), slug)
                append_log(config.vault_path, "mapper", slug,
                           f"Vault updated. Feature {slug} marked complete.")

        except HarnessError as e:
            print(f"wiki4llm: {e}")
            return 1

        features_completed += 1
