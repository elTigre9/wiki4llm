# wiki4llm — Project Overview

## What is being built

`wiki4llm` is a CLI tool that gives LLM coding agents a persistent, structured knowledge
base (a "vault") that compounds across sessions. Instead of re-deriving codebase context
on every run, agents read from and write to a shared vault of markdown files — so each
session starts with full context of everything built before it.

---

## Three modes

Mode is chosen at `wiki4llm init` time and baked into the project config.

### Context Mode
You drive the loop. Slash-command files are generated for your LLM CLI tool (Claude Code,
OpenCode). You type commands like `/wiki-map`, `/wiki-build`, `/wiki-advise` inside your
LLM tool. Best for day-to-day interactive work.

### Harness Mode
Same slash-command files as Context Mode, but structured as a two-phase loop:
Phase 1 (Architect + Builder) and Phase 2 (Mapper + Lint). You manually open a new
context window between phases. Semi-autonomous — you still press go each time.

### Run Mode
Fully autonomous. No LLM CLI tool involved. You drop spec files into `specs/`, run
`wiki4llm run` in your terminal, and a BAML agent loop runs until every feature in
the plan is complete. No further input required unless `--interactive` is passed.
This is the "set it and forget it" mode.

**Run Mode is what these specs describe how to build.**

---

## Tech stack

- **Node.js + TypeScript** — the `wiki4llm` CLI binary
  - `commander` for argument parsing
  - Compiles to `dist/`, linked globally via `npm link`
- **Python + BAML** — the Run Mode harness (`harness/`)
  - `baml-py>=0.222.0` for agent orchestration with typed structured outputs
  - BAML with client-defined providers for model-agnostic LLM calls
  - Lives alongside the Node project; Node shells out to it
- **Vault** — plain markdown files at `.wiki/` inside the project
- **Git** — vault is version-controlled; Builder commits code changes

---

## Repository layout (to be created from scratch)

```
wiki4llm/
  src/
    cli.ts                  # entry point; registers all commands
    config.ts               # WikiConfig type + load/save helpers
    vault.ts                # vault scaffold + preamble builder
    commands/
      init.ts               # `wiki4llm init` — mode selection, slash-command generation, vault scaffold
      run.ts                # `wiki4llm run` — validates deps, shells out to harness/main.py
    templates/
      claude/               # slash-command templates for Claude Code
      opencode/             # slash-command templates for OpenCode
  harness/
    main.py                 # entry point; parses args, runs the loop
    baml_loop.py            # BAML orchestration loop with typed structured outputs
    baml_agents.py          # BAML agent implementations
    tools.py                # tool definitions (framework-agnostic)
    tool_dispatch.py        # tool dispatcher for agents
    loop_helpers.py         # shared helpers for loop orchestration
    vault.py                # vault read/write helpers
    config.py               # config loading + validation
    baml_src/               # BAML source files
      agents.baml           # type schemas for all agent outputs
      clients.baml          # LLM client definitions
      tests.baml            # golden-output prompt tests
    baml_client/            # generated BAML client code
    requirements.txt        # baml-py>=0.222.0
  specs/                    # this folder — read by the Planner agent at runtime
  package.json
  tsconfig.json
  .wiki4llm.json            # written by `wiki4llm init`
```

---

## Spec files (read these in order before writing any code)

1. `00-overview.md` — this file
2. `01-project-bootstrap.md` — full project structure, package.json, tsconfig, build setup
3. `02-vault.md` — vault structure, scaffold logic, preamble builder
4. `03-init-command.md` — `wiki4llm init`: mode selection, slash-command generation
5. `04-run-command.md` — `wiki4llm run`: Node launcher + Python harness entry point
6. `05-agents.md` — the 8 BAML agents and their roles
7. `06-loop.md` — orchestration loop, idempotency, error handling
8. `07-vault-contract.md` — what each agent reads and writes
9. `08-llm-backends.md` — BAML client definitions, per-agent model routing
10. `09-refinement.md` — the Refiner agent's multi-candidate scoring system
11. `10-config.md` — full config schema, CLI flags, environment variables
12. `11-slash-commands.md` — slash-command file formats and prompt bodies
13. `12-implementation-guide.md` — implementation order and gotchas
14. `13-review-enhance.md` — post-loop Review/Enhance mode

---

## Future work

- **Post-loop Review/Enhance mode** (see `13-review-enhance.md`): After the agent loop completes all features, optionally run a review pass (audits vault consistency, surfaces gaps) or enhance pass (improves code that passed tests but is rough). Toggle via config; deferred until BAML migration is stable.
