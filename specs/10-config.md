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
    "specsDir": "specs",
    "maturity": "stable"
  },
  "slashCommands": {
    "mode": "context",
    "tool": "claude"
  },
  "engine": "baml",
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
    "verifierRetries": 2,
    "agentTimeout": 120
  },
  "research": {
    "enabled": false,
    "type": "ux",
    "prompt": ""
  },
  "apiKeys": {
    "openai":    "$OPENAI_API_KEY",
    "anthropic": "$ANTHROPIC_API_KEY"
  },
  "security": {
    "level": "open",
    "shell": { "allow": true },
    "vault": { "allowPathTraversal": true },
    "apiKeys": { "requireEnvRefs": false }
  }
}
```

The `slashCommands` block is present only when Context or Harness mode is selected.
The `crewai` block is present only when Run Mode is selected. The key is named
`crewai` for backward compatibility but consumed by the BAML engine.

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
| `maturity` | string | `"stable"` | `"prototype"` or `"stable"`. Prototype defers full Mapper to end of run and short-circuits Verifier on non-source changes |

### `slashCommands`

| Field | Type | Values | Description |
|---|---|---|---|
| `mode` | string | `"context"`, `"harness"` | Which slash-command set was generated |
| `tool` | string | `"claude"`, `"opencode"` | Which LLM CLI tool the commands were generated for |

### `engine`

| Field | Type | Default | Description |
|---|---|---|---|
| `engine` | string | `"baml"` | Agent engine. Only `"baml"` is supported (CrewAI was removed in v0.6) |

### `crewai`

The key is named `crewai` for backward compatibility with existing configs. It is consumed by the BAML engine for model routing and loop configuration.

| Field | Type | Default | Description |
|---|---|---|---|
| `model.default` | string | `"ollama/qwen2.5-coder:32b"` | Fallback model for all agents. Mapped to BAML client names automatically by `_client_for_agent()` in `harness/baml_agents.py`. |
| `model.agents.<name>` | string | inherits default | Per-agent model override. Model string is mapped to the nearest BAML client name. |
| `maxFeatures` | number \| null | `null` | Stop after N features; null = run to completion |
| `interactive` | boolean | `false` | Pause at human checkpoints after Builder |
| `verifierRetries` | number | `2` | Max Builder → Verifier retry loops per feature |
| `agentTimeout` | number | `120` | Wall-clock timeout in seconds for a single agent call |

### `research`

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | boolean | `false` | Run the Research agent before Refiner on each feature |
| `type` | string | `"ux"` | Research focus: `ux`, `web`, `accessibility`, `performance`, `competitor`, `security` |
| `prompt` | string | `""` | Optional sub-prompt for extra focus |

### `apiKeys`

API keys for remote providers. Values starting with `$` are resolved from environment variables. Supported providers: `openai`, `anthropic`, `gemini`, `groq`, `mistral`, `cohere`, `together`, `fireworks`, `tavily`.

### `security`

See the Security section in README.md.

---

## `wiki4llm run` CLI flags

```
wiki4llm run [options]

  --specs <dir>        Specs directory (default: project.specsDir or "specs")
  --max-features <n>   Stop after N features
  --interactive        Pause at human checkpoints
  --no-refine          Skip the Refiner agent
  --no-verify          Skip the Verifier agent
  --skip-clarify       Skip the one-time spec clarification pass
  --force-remap        Re-run the pre-flight mapper even if map/structure.md exists
  --research <type>    Enable Research agent (ux|web|accessibility|performance|competitor|security)
  --dry-run            Print the plan without executing agents
  --verbose            Stream agent output to stdout
  --trace              Print heartbeat lines during long agent calls
  --maturity <mode>    Override project maturity: "prototype" or "stable"
  -h, --help
```

CLI flags override `.wiki4llm.json`, which overrides built-in defaults.

---

## Environment variables

Never stored in config files. Set in the shell before running `wiki4llm run`.

| Variable | Provider |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic (Claude) |
| `OLLAMA_CLOUD_URL` | Ollama cloud endpoint (optional) |
| `OLLAMA_CLOUD_MODEL` | Ollama cloud model name (optional) |
| `OLLAMA_CLOUD_API_KEY` | Ollama cloud API key (optional) |
| `TAVILY_API_KEY` | Tavily web search (Research agent) |
