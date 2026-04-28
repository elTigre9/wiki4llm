# wiki4llm

A setup tool that installs slash-commands into your LLM CLI of choice (OpenCode, Claude Code, etc.), giving your coding agent a persistent [Obsidian](https://obsidian.md) vault it reads from and writes to — so it always knows your codebase before it starts working.

Think of it as a replacement for RAG in agentic coding workflows: the vault is built once, kept current, and injected as context into every command — so your agent compounds knowledge across sessions instead of starting from scratch.

> Inspired by [Andrej Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and the [agentmemory](https://github.com/rohitg00/agentmemory) pattern.

---

## Contents

- [How it works](#how-it-works)
- [Three Modes](#three-modes)
- [Getting Started](#getting-started)
- [Walkthroughs](#walkthroughs)
- [Slash-Commands](#slash-commands)
- [Vault Structure](#vault-structure)
- [Security](#security)
- [Config](#config-wiki4llmjson)
- [LLM Requirements](#llm-requirements)
- [Dependencies](#dependencies)
- [Development](#development)
- [Roadmap](#roadmap)

---

## How it works

You run `wiki4llm init` once per project. It:

1. Detects which LLM CLI tool you have installed (Claude Code, OpenCode, etc.)
2. Generates slash-command files for that tool inside your project
3. Scaffolds an empty vault at `.wiki/`
4. Writes `.wiki4llm.json`

After that, Context and Harness modes run entirely inside your LLM CLI tool via slash-commands — the binary is done. Run Mode is different: `wiki4llm run` is an ongoing runtime command that drives the full build loop from the CLI, because it needs to manage context resets between agents — something a slash-command inside a single session can't do. The agent reads the vault, does the work, and writes back. The vault compounds over time.

---

## Three Modes

Mode is chosen at `init` time.

### Context Mode (default)
You drive the loop. Use slash-commands to map your codebase, get advice, build features, and keep the vault current. Best for day-to-day vibe coding.

### Harness Mode
An iterative build loop where context is intentionally cleared between phase pairs. The vault is the only memory that persists across contexts — each agent reads from it and writes back to it, so knowledge compounds without context bloat.

The loop runs in two phases per feature:

1. **[Fresh context] Architect + Builder** — reads specs, picks the next feature from the plan, designs and builds it
2. **[Fresh context] Mapper + Lint** — updates the vault to reflect what was built, marks the feature complete

Then the loop restarts with a fresh Architect + Builder context for the next feature.

Designed for local LLM setups (ollama, llama.cpp, vllm) where context window size is the primary constraint.

> **New project?** Run `/wiki-bootstrap` first to seed the vault from your `specs/` directory before starting the harness loop with `/wiki-run`.

> To switch modes after init, re-run `wiki4llm init` and select the other mode. This regenerates the slash-command files in place.

### Run Mode
Fully autonomous CrewAI harness. Run `wiki4llm run` once and it drives the entire build loop — no slash-commands, no manual phase switching. Up to six agents run in sequence per feature: Planner → [Research] → Refiner → Architect → Builder → Verifier → Mapper. Research is optional.

This mode lives in the CLI rather than inside your LLM tool for a fundamental reason: each agent needs a clean context window. A slash-command running inside OpenCode or Claude Code can't wipe its own context and restart — so control moves to the CLI, where the harness manages context resets between agents automatically.

The loop is idempotent: if it crashes mid-feature, re-running resumes from where it left off. The vault is the only persistent state.

Requires Python 3 and `wiki4llm install-deps`. Works with any LiteLLM-compatible backend (Ollama, OpenAI, Anthropic, etc.).

> To switch modes after init, re-run `wiki4llm init` and select the other mode.

---

## Walkthroughs

### Context Mode

Best for day-to-day work on an existing or new project where you want to stay in control.

**Scenario:** You're adding a new auth feature to an existing codebase.

```
# 1. Map the codebase into the vault (do this once, or after big changes)
/wiki-map

# 2. Get a second opinion before writing any code
/wiki-advise   # "Should I use JWTs or sessions for this auth flow?"

# 3. Build the feature — agent reads the vault first, then codes
/wiki-build --feature "add JWT auth to the API"

# 4. Keep the vault current after your changes
/wiki-update
```

That's the loop: map once, advise freely, build, update. Every command reads the vault first, so the agent always has context.

---

### Harness Mode

Best for local LLMs with small context windows, or when you want a disciplined feature-by-feature build loop.

**The core idea:** context is intentionally wiped between phases. The vault is the only thing that survives. Each agent reads from it and writes back to it — so knowledge compounds without the context window ever filling up.

**Scenario:** You're building a new project from a `specs/` directory using a local 27B model.

#### Step 1 — Seed the vault (once per project)

```
/wiki-bootstrap
```

The agent reads everything in `specs/`, writes `pending/plan.md` (a feature checklist), populates the vault with an overview and initial structure, then runs `/wiki-map`. After this, your vault looks like:

```
.wiki/
  pending/plan.md       # [ ] Feature A  [ ] Feature B  [ ] Feature C
  overview.md           # what the project is and does
  map/structure.md      # initial directory layout
```

#### Step 2 — Phase 1: Architect + Builder (fresh context)

```
/wiki-run
```

In a **fresh context**, the agent:
1. Reads `pending/plan.md` and picks the first unchecked feature
2. Reads the relevant vault pages (overview, structure, any related entities)
3. Designs and builds the feature
4. Writes a handoff note to `pending/questions.md` if anything is ambiguous
5. Stops — it does **not** update the vault

At this point, the code is written but the vault doesn't know about it yet.

#### Step 3 — Phase 2: Mapper + Lint (fresh context)

Open a **new context window** (new chat session), then:

```
/wiki-run --continue
```

In a **fresh context**, the agent:
1. Reads `git diff` to see what was just built
2. Updates entity pages, `map/structure.md`, and `log.md` to reflect the changes
3. Checks `pending/questions.md` and resolves or escalates grey areas
4. Marks the feature complete in `pending/plan.md`
5. Runs a vault health check (`/wiki-lint` equivalent)

The vault now knows about the feature. The context is discarded.

#### Step 4 — Repeat

Go back to Step 2. Open a fresh context, run `/wiki-run`. The agent reads the updated vault, picks the next unchecked feature, and builds it — with full knowledge of everything built so far, but zero context bloat.

```
# Full loop, visualized:

[fresh ctx] /wiki-run          # builds Feature A
[fresh ctx] /wiki-run --continue  # maps Feature A, marks done
[fresh ctx] /wiki-run          # builds Feature B  (vault knows about A)
[fresh ctx] /wiki-run --continue  # maps Feature B, marks done
...until pending/plan.md is fully checked off
```

#### The handoff contract

Phase 1 leaves behind:
- Written code (committed or staged)
- `pending/questions.md` — any grey areas or decisions the Mapper should know about

Phase 2 expects to find:
- A `git diff` it can read
- `pending/questions.md` (may be empty)

If Phase 1 didn't commit anything, Phase 2 has nothing to map. Always commit or stage before running `--continue`.

#### Common gotchas

- **The loop stalls on the same feature** — check `pending/plan.md`. If the feature isn't checked off, Phase 2 may not have run cleanly. Open the file and verify the checkbox was written.
- **Grey areas pile up** — if `pending/questions.md` keeps growing without resolution, run `/wiki-run` without `--no-block` so the agent pauses and asks you directly.
- **Vault gets stale** — if you make manual edits outside the loop, run `/wiki-map` to resync before the next `/wiki-run`.
- **Context window still fills up** — reduce vault scope with `vault.external: true` or prune with `/wiki-lint`.

---

### Run Mode

Best for when you want a fully autonomous build loop with no manual phase switching.

**The core idea:** one command drives the entire loop. Five specialist agents run in sequence per feature. The vault is the only persistent state — the loop is idempotent and resumes cleanly after a crash.

**Scenario:** You have a `specs/` directory and want to build the whole thing hands-off.

```bash
# 1. Install Python deps (once)
wiki4llm install-deps

# 2. Preview the feature plan without running agents
wiki4llm run --dry-run

# 3. Run the full loop
wiki4llm run
```

The loop runs until `pending/plan.md` is fully checked off:

```
[Planner]    reads specs/, writes pending/plan.md + overview.md
[Research]   (optional) researches trends/patterns, writes research/<slug>.md
[Refiner]    evaluates 3 approaches, writes decisions/<slug>.md
[Architect]  writes pending/plan-<slug>.md
[Builder]    implements feature, commits, writes pending/questions.md
[Verifier]   runs test suite, writes pending/verify-<slug>.md
             → if tests fail, Builder retries (up to verifierRetries times)
[Mapper]     updates vault, checks off feature in pending/plan.md
             → repeat for next feature
```

#### Useful flags

```bash
wiki4llm run --dry-run              # print feature list, don't build
wiki4llm run --no-refine            # skip Refiner (faster, less deliberate)
wiki4llm run --no-verify            # skip Verifier (no test feedback loop)
wiki4llm run --research ux          # enable Research agent (types: ux, web, accessibility, performance, competitor, security)
wiki4llm run --research web --research-prompt "focus on React 19 patterns"  # with sub-prompt
wiki4llm run --interactive          # pause after Builder for human review
wiki4llm run --max-features 1       # build one feature then stop
wiki4llm run --model openai/gpt-4o  # override model for all agents
wiki4llm run --trace                # print a heartbeat line every 60s while an agent is thinking
```

#### Token usage display

When `--verbose` is on, each agent prints a summary line after it finishes:

```
  ✓ [mapper] done (1m 24s)  [390,568 tokens (cumulative), ↑310,421 ↓80,147, peak ctx ~152.6%]
```

- **tokens (cumulative)** — total tokens summed across every LLM call the agent made during its task (tool reads, reasoning steps, writes). A single agent task typically involves many calls, so this number can exceed your model's context window limit — that's expected.
- **↑ / ↓** — cumulative prompt tokens sent vs. completion tokens received.
- **peak ctx ~%** — an estimate of context pressure, calculated as `cumulative tokens / context window size`. Because it's cumulative, values over 100% are normal and just mean the agent made more than one full context window's worth of calls. It is not a guarantee that any single call stayed within the limit.

If you need per-call context tracking (to catch actual context overflow), that requires hooking into LiteLLM's callback system — not currently implemented.

#### Per-agent model overrides

Set different models per agent in `.wiki4llm.json`:

```json
"crewai": {
  "model": {
    "default": "ollama/qwen2.5-coder:32b",
    "agents": {
      "research": "openai/gpt-4o",
      "refiner": "openai/gpt-4o",
      "builder": "ollama/qwen2.5-coder:32b",
      "verifier": "ollama/qwen2.5-coder:32b"
    }
  }
}
```

#### Idempotency

If the loop crashes mid-feature, re-run `wiki4llm run`. Each agent checks whether its output already exists before running:

| Agent | Skipped if |
|---|---|
| Planner | Never — always merges |
| Research | `research/<slug>.md` exists and contains `## Findings` |
| Refiner | `decisions/<slug>.md` exists and is valid |
| Architect | `pending/plan-<slug>.md` exists |
| Builder | `pending/questions.md` has an entry for the slug and `pending/verify-<slug>.md` is not a failure |
| Verifier | `pending/verify-<slug>.md` exists and starts with `PASSED` |
| Mapper | Feature already checked off in `pending/plan.md` |

---

## Getting Started

### Install

`wiki4llm` is not yet published to npm. Install directly from the repo:

```bash
git clone https://github.com/your-org/wiki4llm
cd wiki4llm
npm install
npm run build
npm link
```

This makes the `wiki4llm` command available globally from your local clone.

### Initialize a project

Open your project folder and run:

```bash
cd my-project
wiki4llm init
```

`init` will:
- Ask which mode you want (Context, Harness, or Run)
- Detect your LLM CLI tool and generate slash-command files for it (Context and Harness only)
- Scaffold `.wiki/` with `index.md` and `log.md`
- Write `.wiki4llm.json`
- Add the generated command directory to `.gitignore` (Context and Harness only)

### Supported LLM CLI tools

| Tool | Generated path |
|---|---|
| [Claude Code](https://claude.ai/code) | `.claude/commands/` |
| [OpenCode](https://opencode.ai) | `.opencode/commands/` |

If neither is detected, `init` will prompt you to choose and generate the files anyway.

> The generated command directories are gitignored by default — teammates run `wiki4llm init` themselves and get files generated for their own preferred tool.

### Updating wiki4llm in an existing project

Pull and rebuild the binary, then re-run `init` in your project:

```bash
# 1. Update the binary
cd wiki4llm
git pull
npm run build

# 2. Update your project
cd my-project
wiki4llm init
```

Re-running `init` regenerates slash-command files in place (Context and Harness), or refreshes the harness script path in `.wiki4llm.json` (Run Mode). Your `.wiki/` vault and all other config are preserved.

For Run Mode, also re-run `install-deps` after `init` in case Python dependencies changed:

```bash
wiki4llm install-deps
```

### Start using slash-commands

**Context Mode** — open your LLM CLI tool inside the project and run:

- **New project with a `specs/` directory?** Start with `/wiki-bootstrap` to seed the vault from your specs and scaffold the initial structure. It runs `/wiki-map` automatically at the end.
- **Existing project?** Run `/wiki-map` directly — the agent walks your codebase and writes the vault from what's already there.

From here, every subsequent command reads the vault first.

**Harness Mode**:

- **New project with a `specs/` directory?** Run `/wiki-bootstrap` to seed the vault and scaffold the initial structure. It runs `/wiki-map` automatically at the end, then start the loop with `/wiki-run`.
- **Existing project?** Run `/wiki-map` directly to build the vault from your current codebase, then start the loop with `/wiki-run`.

**Run Mode**:

1. Add spec files to `specs/`
2. Run: `wiki4llm install-deps`
3. Run: `wiki4llm run`

The harness reads your specs, builds a feature plan, and works through it autonomously.

---

## Slash-Commands

### Context Mode

| Command | Description |
|---|---|
| `/wiki-map [--ask]` | Map codebase into vault |
| `/wiki-bootstrap` | New projects only — seed vault from `specs/`, scaffold initial structure, then run `/wiki-map` |
| `/wiki-advise` | Vault-aware second opinion on an idea before you build |
| `/wiki-build [--feature "..."] [--ask]` | Read vault, then plan and implement a feature |
| `/wiki-update [--ask]` | Incrementally update vault from `git diff` since last map |
| `/wiki-lint` | Health-check the vault (orphans, stale claims, missing pages) |

### Harness Mode

| Command | Description |
|---|---|
| `/wiki-run [--plan <folder>] [--no-block]` | Phase 1: Architect + Builder — reads specs, picks next feature, builds it |
| `/wiki-run --continue [--no-block]` | Phase 2: Mapper + Lint — updates vault, marks feature complete, hands off |

### Run Mode

Run Mode uses `wiki4llm run` directly — no slash-commands.

```
wiki4llm run [options]

  --specs <dir>        Specs directory (default: "specs")
  --model <string>     Override default model for all agents
  --max-features <n>   Stop after N features
  --interactive        Pause at human checkpoints
  --no-refine          Skip the Refiner agent
  --no-verify          Skip the Verifier agent (no test feedback loop)
  --research <type>    Enable Research agent (ux|web|accessibility|performance|competitor|security)
  --research-prompt    Sub-prompt appended to the Research agent's instructions
  --dry-run            Print the plan without executing agents
  --verbose            Stream agent output to stdout; prints cumulative token
                       usage and estimated context % per agent after each task
  --trace              Print a heartbeat line every 60s while an agent is
                       thinking; also ensures stall warnings are not overwritten
```

### Slash-command flags

- `--ask` — agent asks clarifying questions before writing code or mapping
- `--feature "<description>"` — describe the feature to build
- `--plan <folder>` — override the specs directory (default: `specs/`); Harness Mode only
- `--no-block` — skip human checkpoints; agent makes best-guess on grey areas (Harness Mode)
- `--continue` — run Phase 2 (Mapper + Lint) of the harness loop in a fresh context

---

## Vault Structure

The agent owns all vault writes. You read it.

```
.wiki/
  index.md              # catalog of all pages + one-line summaries
  log.md                # append-only operation log
  overview.md           # high-level codebase summary
  raw/                  # unedited inputs: copied from specs/, notes
    assets/             # images, PDFs, media
  map/
    structure.md        # directory tree + file roles
    dependencies.md     # key deps, versions, relationships
    entrypoints.md      # main entry files and their purpose
  entities/
    <ComponentName>.md  # one page per major module/class/service
  decisions/
    <slug>.md           # ADR-style architectural decision pages
  research/
    <slug>.md           # Research agent findings (Run Mode, when research is enabled)
  pending/
    plan.md             # feature checklist derived from specs/ (Harness + Run Mode)
    questions.md        # grey area queue; Builder writes, Mapper resolves
    plan-<slug>.md      # per-feature implementation plan (Run Mode)
```

The vault is a plain git repo of markdown files. Obsidian is optional — everything works headlessly without it.

---

## Security

wiki4llm ships with three security levels. The default is `open` (no restrictions) so existing workflows are unaffected. Set a stricter level at `init` time or by editing `.wiki4llm.json`.

### Levels

| Level | Shell access | Vault path traversal | API key enforcement |
|---|---|---|---|
| `open` (default) | Unrestricted | Allowed | No check |
| `standard` | `git`, `npm`, `pip`, `python` only | Blocked | Warn on bare keys |
| `strict` | Disabled entirely | Blocked | Error on bare keys |

### Config block

```json
"security": {
  "level": "standard",
  "shell": {
    "allow": true,
    "allowedCommands": ["git *", "npm *", "pip *", "python *", "python3 *"],
    "blockedPatterns": ["rm\\s+-rf", "curl\\s+.*\\|\\s*sh"]
  },
  "vault": {
    "allowPathTraversal": false
  },
  "apiKeys": {
    "requireEnvRefs": true
  }
}
```

- `level` sets the preset. Individual sub-keys override the preset — you can mix and match.
- `shell.allowedCommands` — glob-style prefixes; empty list means all commands are allowed.
- `shell.blockedPatterns` — regex strings; matched commands are rejected before execution.
- `vault.allowPathTraversal` — when `false`, any vault path containing `..` is rejected.
- `apiKeys.requireEnvRefs` — `standard` prints a warning; `strict` exits with an error.

### Choosing a level

- **Novice / shared machine / CI** — use `standard`. Shell is limited to common dev tools, the vault can't escape its directory, and you'll be warned if you accidentally paste a raw API key.
- **Air-gapped or high-security environment** — use `strict`. The agent can read and write the vault but cannot run any shell commands. Combine with `vault.external: true` to keep the vault outside the project entirely.
- **Personal dev machine / testing** — keep `open`. Full agent autonomy, no friction.

> To change the level after init, re-run `wiki4llm init` and select a different level, or edit the `security.level` field in `.wiki4llm.json` directly.

> **Run Mode only:** security is enforced by the Python harness (`ShellTool`, `VaultWriteTool`, `VaultReadTool`). Context and Harness modes run inside your LLM CLI tool — the agent's own tool permissions (set in the slash-command frontmatter) are the primary control there.

---

## Config (`.wiki4llm.json`)

A fully populated example config with all agents and recommended options enabled is available at [`wiki4llm.example.json`](./wiki4llm.example.json) in the repo root. Copy it to your project and rename it to `.wiki4llm.json` as a starting point.

```json
{
  "vault": {
    "path": "./.wiki",
    "name": "my-project",
    "git": true,
    "sync": false,
    "external": false
  },
  "project": {
    "name": "my-project",
    "ignore": ["node_modules", "dist", ".git"],
    "specsDir": "specs"
  },
  "harness": {
    "maxIterations": 3,
    "noBlock": false,
    "agents": ["architect", "builder", "mapper", "lint"]
  },
  "crewai": {
    "model": {
      "default": "ollama/qwen2.5-coder:32b",
      "agents": {
        "planner":   "ollama/qwen2.5-coder:32b",
        "research":  "openai/gpt-4o",
        "refiner":   "openai/gpt-4o",
        "architect": "ollama/qwen2.5-coder:32b",
        "builder":   "ollama/qwen2.5-coder:32b",
        "verifier":  "ollama/qwen2.5-coder:32b",
        "mapper":    "anthropic/claude-sonnet-4-5"
      }
    },
    "maxFeatures": null,
    "interactive": false,
    "verifierRetries": 2,
    "agentTimeout": 900,
    "pythonPath": "python3",
    "harnessScript": "harness/main.py"
  },
  "research": {
    "enabled": false,
    "type": "ux",
    "prompt": ""
  },
  "apiKeys": {
    "openai":    "$OPENAI_API_KEY",
    "anthropic": "sk-ant-...",
    "gemini":    "$GEMINI_API_KEY",
    "groq":      "$GROQ_API_KEY"
  },
  "security": {
    "level": "open",
    "shell": {
      "allow": true,
      "allowedCommands": [],
      "blockedPatterns": []
    },
    "vault": {
      "allowPathTraversal": true
    },
    "apiKeys": {
      "requireEnvRefs": false
    }
  }
}
```

- `vault.external: true` — vault lives at `~/.wiki4llm/vaults/<project-name>/` instead of inside the project
- `vault.sync: true` — pull before read, push after commit (requires a git remote)
- `harness.noBlock: true` — Harness Mode skips human checkpoints globally
- `research.enabled` — set to `true` to run the Research agent before Refiner on each feature
- `research.type` — focus area: `ux`, `web`, `accessibility`, `performance`, `competitor`, or `security`
- `research.prompt` — optional sub-prompt appended to the Research agent's instructions for extra specificity
- `crewai.model.agents.<name>` — per-agent model override; unset agents fall back to `crewai.model.default`
- `crewai.interactive: true` — pause after Builder runs and prompt for answers to open questions
- `crewai.agentTimeout` — wall-clock timeout in seconds for a single agent task (default: 900). If an agent hangs beyond this limit (e.g. a stalled streaming call), it is cancelled and retried automatically. Reduce this if you're on a fast connection and want faster stall detection; increase it for very large tasks on slow hardware.
- `apiKeys.<provider>` — API key for a remote provider. Values starting with `$` are resolved from environment variables at runtime; bare strings are used directly. Supported providers: `openai`, `anthropic`, `gemini`, `groq`, `mistral`, `cohere`, `together`, `fireworks`.

> **Security:** if you store bare API keys in `.wiki4llm.json`, add it to `.gitignore`. Using `"$ENV_VAR"` references keeps secrets out of the file entirely.

> **`.env` support:** create a `.env` file in your project root with your keys (e.g. `OPENAI_API_KEY=sk-...`). The harness loads it automatically before agents run, and `wiki4llm init` adds `.env` to `.gitignore` for you. Shell environment variables take precedence over `.env` values.

> **Run Mode only:** `apiKeys` is injected by the Python harness before agents run. Context and Harness modes run inside your LLM CLI tool (Claude Code, OpenCode), which manages its own auth — set API keys there via your shell environment or the tool's own settings.

> `harness.maxIterations` is no longer used — the loop runs until all features in `pending/plan.md` are checked off.

> The `crewai` block is only present when Run Mode is selected at `init` time. The `harness` block is only used by Context and Harness modes.

---

## LLM Requirements

wiki4llm works with any LLM, but performance varies significantly by model capability. Context window size is the primary constraint — the vault is injected as context on every command.

### Context Mode

| Tier | Context Window | Parameters | Notes |
|---|---|---|---|
| Minimum | 32k tokens | 7B+ | Basic `/wiki-map` and `/wiki-build` on small codebases |
| Recommended | 128k tokens | 32B+ | Handles full vault injection + large diffs comfortably |
| Ideal | 200k+ tokens | 70B+ / frontier API | Full vault + codebase context in one pass |

### Harness Mode

Harness Mode is specifically designed for local LLMs with limited context. Each specialist agent receives only the vault slice it needs, keeping per-agent context low.

| Tier | Context Window | Parameters | Notes |
|---|---|---|---|
| Minimum | 8k tokens | 7B+ | One agent at a time, small vault slices |
| Recommended | 32k tokens | 13B–34B | Comfortable for most agent tasks |
| Ideal | 64k tokens | 34B+ | Handles complex entity pages and decision records |

### Model Specialization

Some commands benefit from specific model strengths:

| Command | Best fit |
|---|---|
| `/wiki-map` | Strong instruction-following; code-tuned models preferred |
| `/wiki-advise` | Strong reasoning; frontier models or 70B+ recommended |
| `/wiki-build` | Code generation; code-tuned models (Qwen2.5-Coder, DeepSeek-Coder, Codestral) |
| `/wiki-lint` | Analytical; any well-instruction-tuned model works |
| `/wiki-run` (Harness) | Each agent can use a different model — mix and match by task |

### Local Model Recommendations

| Use case | Model |
|---|---|
| Minimum viable (8–16 GB RAM) | `qwen2.5-coder:7b`, `deepseek-coder-v2:16b` |
| Recommended local (32–64 GB RAM) | `qwen2.5-coder:32b`, `codestral:22b` |
| High-end local (64 GB+ RAM) | `qwen2.5-coder:72b`, `deepseek-coder-v2:236b` |
| API / cloud | Claude Sonnet/Opus, GPT-4o, Gemini 1.5 Pro |

> Vault size grows over time. If your model's context window fills up, use `/wiki-lint` to prune stale pages, or enable `vault.external` to keep the vault lean.

---

## Dependencies

| Package | Purpose |
|---|---|
| [commander](https://github.com/tj/commander.js) | CLI argument parsing |
| [fast-glob](https://github.com/mrmlnc/fast-glob) | Directory walking for codebase mapping |

### Optional

| Tool | Purpose |
|---|---|
| [Obsidian](https://obsidian.md) | Browse and visualize the vault (graph view, Dataview, Marp) |
| `obsidian-cli` or `obsidian` on PATH | Headless vault open/refresh; auto-detected at runtime |
| [git](https://git-scm.com) | Vault versioning and diff-aware updates (strongly recommended) |
| [ollama](https://ollama.com) / [llama.cpp](https://github.com/ggerganov/llama.cpp) / [vllm](https://github.com/vllm-project/vllm) | Local LLM backends for Harness and Run modes |
| [Python 3](https://python.org) + [crewai](https://github.com/crewAIInc/crewAI) | Required for Run Mode (`wiki4llm install-deps`) |

---

## Development

```bash
git clone https://github.com/your-org/wiki4llm
cd wiki4llm
npm install
npm run dev -- init
```

---

## Roadmap

| Phase | Features |
|---|---|
| 1 — Core + Advise | `init` (tool detection, mode selection), `/wiki-map`, `/wiki-bootstrap`, `/wiki-advise` |
| 2 — Build & Tooling | `/wiki-build`, Obsidian CLI detection |
| 3 — Maintenance & Sync | `/wiki-update`, `/wiki-lint`, push/pull sync |
| 4 — Harness Mode | `/wiki-run`, specialist agents, grey area queue, external vault |
| 5 — Run Mode | `wiki4llm run`, CrewAI harness, Planner/Refiner/Architect/Builder/Mapper, idempotent loop |

Out of scope for v1: embedding/vector search, confidence scoring, multi-agent mesh sync, web UI.
# wiki4llm
