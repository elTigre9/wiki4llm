# Orchestration Loop

All loop logic lives in `harness/baml_loop.py`. The entry point is `harness/main.py`,
which parses the merged config, injects API keys, and calls `run_loop_baml(config)`.

---

## Architecture

Agents fall into two categories:

### Single-shot agents (pure I/O)

Clarifier, Planner, Refiner, Architect, and Research make **one BAML function call**
and receive a typed structured output directly. No tool-calling, no multi-turn loop.

### Tool-call loop agents

Builder, Verifier, and Mapper use a **tool-call loop** (see [Tool-call loop](#tool-call-loop)
below). Their BAML functions return a union type: `ToolCall | Final`. The Python layer
deserializes the result, dispatches the tool call if `ToolCall` is received, feeds the
result back via the `history` input, and repeats until a `Final` variant is returned
or the iteration cap is hit.

### Pre-loaded vault context

Vault file contents are passed as **typed inputs** to BAML functions (e.g.,
`vault_overview: string`, `vault_structure: string`). Agents do not burn tool calls
reading vault pages — the harness pre-loads the relevant files before the call.

### Engine routing

`harness/main.py` unconditionally imports and calls `harness/baml_loop.py`. There is no
CrewAI path. The single orchestration engine is BAML.

---

## Startup sequence

```
harness/main.py
  └── run_loop_baml(config)
        ├── validate_vault(config.vault_path)
        ├── validate_specs(config.specs_dir)
        ├── if config.dry_run → print_plan(); return 0
        ├── pre-flight Mapper (once, if vault unmapped and source files exist)
        ├── Clarifier (once, if raw/clarifications.md isn't complete)
        ├── Planner (once, if pending/plan.md is missing or empty)
        └── loop per feature:
              ├── next_unchecked(plan_path)
              ├── Research (if enabled and research/<slug>.md missing)
              ├── Refiner (if not --no-refine and decisions/<slug>.md missing)
              ├── Architect (if pending/plan-<slug>.md missing)
              ├── Builder → Verifier loop (up to verifier_retries)
              ├── Human checkpoint (if --interactive and open questions exist)
              ├── Mapper (inline check-off in prototype; full BAML in stable)
              └── features_completed += 1
        ├── end-of-run batched Mapper (prototype mode only)
        └── "All features complete."; return 0
```

---

## Idempotency

Each agent checks whether its output file already exists before running:

| Agent | Skip condition |
|---|---|
| Clarifier | `raw/clarifications.md` exists and status is not `needs-answers` |
| Planner | Never skipped — always re-runs and merges into `pending/plan.md` |
| Research | `research/<slug>.md` exists |
| Refiner | `decisions/<slug>.md` exists and is valid |
| Architect | `pending/plan-<slug>.md` (and `raw/<slug>/TECH.md`) exist |
| Builder | `pending/questions.md` has an entry for `<slug>` |
| Verifier | `pending/verify-<slug>.md` exists |
| Mapper | Feature is already checked off in `pending/plan.md` |

This means a crashed harness resumes cleanly on re-run.

---

## Tool-call loop

Tool-using agents (Builder, Verifier, Mapper) follow this cycle:

```
1. Call the BAML function with the current `history` input.
2. If the return type is a ToolCall variant:
   a. Extract tool_name and args.
   b. Dispatch via ToolDispatcher (harness/tool_dispatch.py).
   c. Append {tool: name, result: output} to history_entries.
   d. Go to step 1.
3. If the return type is a Final variant:
   a. Extract the typed report (BuilderReport, VerifierReport, MapperReport).
   b. Return it to the caller.
```

The loop is capped at `_MAX_TOOL_ITERS = 25`. If exceeded, a `HarnessError` is raised.

Stalled calls (network flakiness, provider rate limiting) are retried with exponential
backoff up to `_STALL_MAX_RETRIES = 5` before an exception propagates.

BAML handles HTTP timeouts natively through its client configuration. There is no
multiprocessing wrapper, subprocess isolation, or spinner thread — each agent call
runs inline in the main Python process.

---

## Prototyping mode (`project.maturity: "prototype"`)

When the project config sets `maturity` to `"prototype"`, two optimizations kick in:

### Inline Mapper check-off

Instead of calling the BAML Mapper for every feature, the harness runs an inline
Python check-off (`_inline_mapper_checkoff`) that marks the feature complete in
`pending/plan.md` and appends a log entry. No LLM call.

At the end of the run, a single batched Mapper call (`_end_of_run_mapper`) syncs
all entities, structure, dependencies, entrypoints, index, and deviations for every
feature built in that run. The LLM receives the combined git diff, all `TECH.md`
snippets, and the full index in one pass.

### Verifier short-circuit

After the Builder commits, the harness checks `git diff HEAD~1`. If the diff
contains only documentation/config changes (no source-code files matching common
source extensions), the Verifier is skipped. In stable mode, the Verifier always
runs unless `--no-verify` is set.

---

## Feature slug

```python
import re

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
```

Used for `decisions/<slug>.md`, `pending/plan-<slug>.md`, `pending/verify-<slug>.md`,
`raw/<slug>/TECH.md`, and log entries.

---

## Termination conditions

1. `pending/plan.md` has no unchecked `- [ ]` items
2. `--max-features N` reached
3. Unrecoverable agent error after retries
4. Builder produces empty git diff (logged as warning; feature marked complete)

---

## Error handling

```python
MAX_RETRIES = 2

def run_with_retry(agent_fn, config, feature, agent_name):
    for attempt in range(MAX_RETRIES + 1):
        try:
            agent_fn(config, feature)
            return
        except Exception as e:
            if attempt == MAX_RETRIES:
                append_log(config.vault_path, agent_name, feature.slug,
                           f"[ERROR] Failed after {MAX_RETRIES} retries: {e}")
                write_vault_file(config.vault_path, "pending/questions.md",
                                  f"\n## {feature.slug} — [ERROR]\n{e}\n", append=True)
                raise HarnessError(f"{agent_name} failed: {e}")
            time.sleep(2 ** attempt)
```

On unrecoverable failure: write error to `pending/questions.md`, append to `log.md`,
exit with code 1. The feature stays unchecked so re-running retries from the Refiner.

BAML function calls additionally have their own stall retry loop (see
[Tool-call loop](#tool-call-loop)) that handles transient provider failures before
bubbling up to this retry layer.

---

## Human checkpoint (interactive mode)

```python
def pause_for_human(config, feature):
    questions = read_open_questions(config.vault_path, feature.slug)
    if not questions:
        return

    print(f"\n[wiki4llm] Feature \"{feature.description}\" — Builder has questions:\n")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q}")
    print(f"  {len(questions)+1}. [free-form answer]")
    print("\nEnter answer(s), or press Enter to let the Mapper resolve with best-guess:")

    response = input("> ").strip()
    if response:
        write_answers_to_questions(config.vault_path, feature.slug, response)
    # If empty, Mapper proceeds with best-guess (--no-block behavior for this feature)
```

---

## Dry run

When `--dry-run` is passed, the Planner still runs (to build `pending/plan.md`), then
the loop prints the feature list and exits without running any other agents:

```
wiki4llm: Dry run — features found in specs/:

  [ ] add-jwt-auth: Add JWT authentication to the API
  [ ] user-dashboard: Build the user dashboard page
  [ ] email-notifications: Send email on key events

Run without --dry-run to execute.
```

---

## Logging

Every agent completion appends to `.wiki/log.md`:

```markdown
## 2025-01-15T14:32:00Z — refiner — add-jwt-auth
Evaluated 3 approaches. Chose: stateless JWT with RS256. See decisions/add-jwt-auth.md.

## 2025-01-15T14:35:00Z — builder — add-jwt-auth
Committed: feat(auth): add JWT middleware and token issuance (3 files changed)

## 2025-01-15T14:37:00Z — mapper — add-jwt-auth
Updated: entities/AuthMiddleware.md, map/structure.md, index.md. Feature marked complete.
```

---

## `harness/vault.py` — helpers used by the loop

```python
import os, re
from pathlib import Path
from datetime import datetime, timezone

def read_vault_slice(vault_path: str, files: list[str]) -> str:
    parts = []
    for f in files:
        full = Path(vault_path) / f
        if full.exists():
            parts.append(f"### {f}\n{full.read_text()}")
    return "\n\n".join(parts)

def write_vault_file(vault_path: str, relative_path: str, content: str, append=False):
    full = Path(vault_path) / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    full.write_text(content) if not append else open(full, "a").write(content)

def next_unchecked_feature(plan_path: str):
    if not Path(plan_path).exists():
        return None
    for line in Path(plan_path).read_text().splitlines():
        m = re.match(r"- \[ \] ([a-z0-9-]+): (.+)", line)
        if m:
            return (m.group(1), m.group(2))  # (slug, description)
    return None

def check_off_feature(plan_path: str, slug: str):
    text = Path(plan_path).read_text()
    updated = re.sub(rf"- \[ \] {re.escape(slug)}:", f"- [x] {slug}:", text)
    Path(plan_path).write_text(updated)

def append_log(vault_path: str, agent: str, slug: str, message: str):
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"\n## {ts} — {agent} — {slug}\n{message}\n"
    write_vault_file(vault_path, "log.md", entry, append=True)
```
