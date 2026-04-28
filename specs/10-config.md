# Config

---

## `.wiki4llm.json` — full schema

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
    "ignore": ["node_modules", "dist", ".git", ".wiki"],
    "specsDir": "specs"
  },
  "slashCommands": {
    "mode": "context",
    "tool": "claude"
  },
  "crewai": {
    "model": {
      "default": "ollama/qwen2.5-coder:32b",
      "agents": {
        "planner":   "ollama/qwen2.5-coder:32b",
        "refiner":   "ollama/qwen2.5-coder:32b",
        "architect": "ollama/qwen2.5-coder:32b",
        "builder":   "ollama/qwen2.5-coder:32b",
        "mapper":    "ollama/qwen2.5-coder:32b"
      }
    },
    "maxFeatures": null,
    "interactive": false,
    "pythonPath": "python3",
    "harnessScript": "harness/main.py"
  }
}
```

The `slashCommands` block is present only when Context or Harness mode is selected.
The `crewai` block is present only when Run Mode is selected.
Both can coexist if the user has run `init` multiple times with different modes.

---

## Field reference

### `vault`

| Field | Type | Default | Description |
|---|---|---|---|
| `path` | string | `"./.wiki"` | Vault directory, relative to project root |
| `name` | string | project dir name | Used for external vault path |
| `git` | boolean | `true` | Run `git init` in vault; commit after each agent |
| `sync` | boolean | `false` | Pull before read, push after commit (requires remote) |
| `external` | boolean | `false` | If true, vault lives at `~/.wiki4llm/vaults/<name>/` |

### `project`

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | project dir name | Project identifier |
| `ignore` | string[] | see above | Directories to skip during codebase mapping |
| `specsDir` | string | `"specs"` | Where spec files live for Run Mode |

### `slashCommands`

| Field | Type | Values | Description |
|---|---|---|---|
| `mode` | string | `"context"`, `"harness"` | Which slash-command set was generated |
| `tool` | string | `"claude"`, `"opencode"` | Which LLM CLI tool the commands were generated for |

### `crewai`

| Field | Type | Default | Description |
|---|---|---|---|
| `model.default` | string | `"ollama/qwen2.5-coder:32b"` | Fallback model for all agents |
| `model.agents.<name>` | string | inherits default | Per-agent model override |
| `maxFeatures` | number \| null | `null` | Stop after N features; null = run to completion |
| `interactive` | boolean | `false` | Pause at human checkpoints |
| `pythonPath` | string | `"python3"` | Python interpreter path |
| `harnessScript` | string | `"harness/main.py"` | Path to Python harness, relative to project root |

---

## `wiki4llm run` CLI flags

```
wiki4llm run [options]

  --specs <dir>        Specs directory (default: project.specsDir or "specs")
  --model <string>     Override default model for all agents
  --max-features <n>   Stop after N features
  --interactive        Pause at human checkpoints
  --no-refine          Skip the Refiner agent
  --dry-run            Print the plan without executing agents
  --verbose            Stream agent output to stdout
  -h, --help
```

CLI flags override `.wiki4llm.json`, which overrides built-in defaults.

---

## Environment variables

Never stored in config files. Set in the shell before running `wiki4llm run`.

| Variable | Backend |
|---|---|
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | OpenAI (and llama.cpp local servers) |
| `GEMINI_API_KEY` | Gemini |
| `OPENAI_BASE_URL` | llama.cpp / any OpenAI-compatible local server |
| `OLLAMA_HOST` | Ollama (default: `http://localhost:11434`) |
