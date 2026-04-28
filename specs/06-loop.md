# Orchestration Loop

All loop logic lives in `harness/loop.py`.

---

## Startup sequence

```
run_loop(config)
  ├── validate_vault(config.vault_path)     # scaffold if missing
  ├── validate_specs(config.specs_dir)      # error if empty
  ├── if config.dry_run → print_plan(); return 0
  ├── run_planner(config)                   # always runs; idempotent
  └── loop:
        feature = next_unchecked(plan_path)
        if feature is None → print "All features complete."; return 0
        if max_features reached → print "Reached --max-features limit."; return 0
        if not config.no_refine → run_refiner(config, feature)
        run_architect(config, feature)
        run_builder(config, feature)
        if config.interactive and questions_exist(vault_path) → pause_for_human(config, feature)
        run_mapper(config, feature)
        features_completed += 1
        continue
```

---

## Idempotency

Each agent checks whether its output file already exists before running:

| Agent | Skip condition |
|---|---|
| Planner | Never skipped — always re-runs and merges |
| Refiner | `decisions/<slug>.md` exists and is valid |
| Architect | `pending/plan-<slug>.md` exists |
| Builder | `pending/questions.md` has an entry for `<slug>` |
| Mapper | Feature is already checked off in `pending/plan.md` |

This means a crashed harness resumes cleanly on re-run.

---

## Feature slug

```python
import re

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
```

Used for `decisions/<slug>.md`, `pending/plan-<slug>.md`, and log entries.

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
