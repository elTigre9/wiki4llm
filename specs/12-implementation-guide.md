# Implementation Guide

Read all spec files before writing any code. This file tells you what to build,
in what order, and what done looks like.

---

## What you are building

You are extending an existing `wiki4llm` project. Do not rebuild what already exists.
Read the current source files first, then add only what is missing.

---

## Read the existing source files first

Before touching anything, read these files in full:

```
src/cli.ts                   # entry point; currently registers only `init`
src/config.ts                # Config type, loadConfig(), resolveVaultPath()
src/vault.ts                 # scaffoldVault(), appendLog(), commitVault(), syncPull/Push()
src/harness.ts               # buildVaultPreamble() — vault state preamble builder
src/commands/init.ts         # full wikiInit() implementation
src/commands/templates.ts    # commandFiles() — all slash-command prompt bodies
package.json
tsconfig.json
```

Then read the spec files in order (listed below).

---

## What already exists

| File | Status | Notes |
|---|---|---|
| `src/cli.ts` | exists | registers `init` only — needs `run` added |
| `src/config.ts` | exists | has `Config`, `Mode` (`"context" \| "harness"`), `Tool`, `HarnessConfig` — needs `CrewAIConfig` and `"run"` mode added |
| `src/vault.ts` | exists | has `scaffoldVault()`, `appendLog()`, `commitVault()`, sync helpers — complete, no changes needed |
| `src/harness.ts` | exists | has `buildVaultPreamble()` — complete, no changes needed |
| `src/commands/init.ts` | exists | full implementation — needs `"run"` mode branch added |
| `src/commands/templates.ts` | exists | all Context and Harness slash-command prompts — complete, no changes needed |
| `package.json` | exists | has `commander`, `fast-glob`, TypeScript — no changes needed |
| `tsconfig.json` | exists | complete — no changes needed |
| `harness/` | exists | BAML agent loop — complete (migrated from CrewAI in v0.6) |
| `src/commands/run.ts` | exists | thin Node launcher — complete |

---

## Read order for spec files

1. `00-overview.md` — three modes, tech stack, full repo layout
2. `01-project-bootstrap.md` — package.json, tsconfig, config types *(read for reference; most already exists)*
3. `02-vault.md` — vault structure and helpers *(already implemented in `src/vault.ts`)*
4. `03-init-command.md` — `wiki4llm init` *(already implemented; only the Run Mode branch is missing)*
5. `04-run-command.md` — `wiki4llm run`: Node launcher + `harness/main.py` + `harness/config.py`
6. `05-agents.md` — 8 BAML agents and `harness/baml_src/agents.baml`
7. `06-loop.md` — BAML orchestration loop and `harness/baml_loop.py`
8. `07-vault-contract.md` — read/write contracts and file formats per agent
9. `08-llm-backends.md` — BAML client definitions, per-agent model routing
10. `09-refinement.md` — Refiner agent: 3-candidate scoring, validation, skip flags
11. `10-config.md` — full config schema, CLI flags, env vars
12. `11-slash-commands.md` — slash-command prompt bodies *(already implemented in `templates.ts`; read for reference)*

---

## Build order

### Step 1 — Extend `src/config.ts`

Add to the existing file (do not replace it):

- Add `"run"` to the `Mode` type: `export type Mode = "context" | "harness" | "run"`
- Add `CrewAIModelConfig` and `CrewAIConfig` interfaces (from `10-config.md`). Named `crewai` for backward compatibility; consumed by the BAML engine.
- Add optional `crewai?: CrewAIConfig` field to the `Config` interface
- Update `DEFAULTS` and `loadConfig()` to handle the new `crewai` field

### Step 2 — Extend `src/commands/init.ts`

Add a Run Mode branch to the existing `wikiInit()` function:

- Add `"run"` as a third option in the mode selection prompt
- When `"run"` is selected:
  - Skip tool detection and slash-command generation entirely
  - Scaffold the vault as normal
  - Create `specs/` directory with a `README.md` if it does not exist
  - Write `.wiki4llm.json` with a `crewai` block (default model: `ollama/qwen2.5-coder:32b`)
  - Print setup instructions (see `03-init-command.md`)
- Do not modify the existing `"context"` and `"harness"` branches

### Step 3 — Add `wiki4llm run` to `src/cli.ts`

Import `wikiRun` from `./commands/run` and register the `run` command with its flags
(see `04-run-command.md`). Do not modify the existing `init` command registration.

### Step 4 — Create `src/commands/run.ts`

Full implementation from `04-run-command.md`. Key points:
- Load config with existing `loadConfig()` from `src/config.ts`
- Error if `config.crewai` is missing (not Run Mode)
- Check Python deps (verify `baml_py` is importable)
- Write merged config to a temp file, shell out to `harness/main.py`, exit with its status

### Step 5 — The Python harness (already built)

The harness was migrated from CrewAI to BAML. Current files:

```
harness/
  requirements.txt     # baml-py>=0.222.0, python-dotenv>=1.0.0
  config.py            # HarnessConfig.from_dict() — spec 04
  vault.py             # vault I/O helpers — spec 06
  tools.py             # VaultWriter, VaultReader, Shell, TavilySearch
  tool_dispatch.py     # ToolDispatcher for BAML tool-call loop
  loop_helpers.py      # shared idempotency checks, path sanitization
  baml_loop.py         # BAML orchestration loop — spec 06
  baml_agents.py       # Agent implementations + tool-call loop engine — spec 05
  main.py              # entry point: load config, print summary, run loop
  baml_src/            # BAML source files
    clients.baml       # LLM client definitions
    generators.baml    # BAML generator config
    agents.baml        # Type schemas + agent functions — spec 05
    tests.baml         # golden-output prompt tests
  baml_client/         # generated BAML client code (committed)
```

---

## What NOT to change

- `src/vault.ts` — complete, do not modify
- `src/harness.ts` — complete, do not modify
- `src/commands/templates.ts` — complete, do not modify
- `package.json` — complete, do not modify
- `tsconfig.json` — complete, do not modify
- The existing `"context"` and `"harness"` branches in `init.ts`

---

## Acceptance criteria

```bash
# Build
npm run build   # must succeed with no TypeScript errors

# Init — Run Mode
mkdir test-project && cd test-project
git init
wiki4llm init
# → choose Run Mode
# → .wiki/ scaffolded
# → .wiki4llm.json written with crewai block
# → specs/ created with README.md
# → setup instructions printed

# Init — Context Mode (existing behavior must be unchanged)
wiki4llm init
# → choose Context Mode, choose claude
# → .claude/commands/ populated with slash-command files

# Dry run
cd test-project
echo "# My App\n\n## Features\n- User login\n- Dashboard" > specs/app.md
wiki4llm run --dry-run
# → shells out to harness/main.py
# → Planner runs, prints feature list, exits without building

# Full run (stable mode)
wiki4llm run --verbose
# → Clarifier → Planner → Research → Refiner → Architect → Builder → Verifier → Mapper
# → loop exits when all features checked off in pending/plan.md

# Full run (prototype mode — faster, deferred Mapper)
wiki4llm run --maturity prototype --verbose
# → same agents but per-feature check-off is inline, Mapper runs once at end
# → Verifier short-circuits on non-source changes

# Resume after crash
wiki4llm run
# → skips agents whose output files already exist (idempotency)

# BAML tests
cd harness && make baml-generate && make baml-test
# → 5 golden-output tests pass (ClarifySpecs ×2, PlanFeatures, RefineApproaches, ArchitectFeature)
```
