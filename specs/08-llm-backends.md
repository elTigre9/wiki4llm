# LLM Backends

The harness uses **BAML** for all model calls. BAML clients are defined in
`harness/baml_src/clients.baml` with typed LLM function contracts. Provider routing
is handled natively by the BAML runtime — no adapter code per backend.

---

## BAML client definitions

All clients live in `harness/baml_src/clients.baml`:

| Client name | Provider | Default model |
|---|---|---|
| `OllamaLocal` | `openai-generic` | `qwen2.5-coder:32b` |
| `OllamaCloud` | `openai-generic` | env `OLLAMA_CLOUD_MODEL` |
| `AnthropicSonnet` | `anthropic` | `claude-sonnet-4-5` |
| `AnthropicOpus` | `anthropic` | `claude-opus-4-5` |
| `Default` | `fallback` | `[OllamaLocal, AnthropicSonnet]` |

The `Default` client uses a fallback strategy: tries `OllamaLocal` first, then
`AnthropicSonnet`. All BAML functions use `Default` unless a per-agent override is
applied in Python.

Each client specifies its own retry policy (`exponential_backoff`, 2 retries,
500ms base delay). Timeouts are handled by the BAML HTTP layer.

---

## Supported providers

### Ollama (local)

Defined via the `OllamaLocal` client using the `openai-generic` provider pointing at
`http://localhost:11434/v1`. This covers local Ollama servers with OpenAI-compatible
endpoints.

Requirements:
- Ollama running: `ollama serve`
- Model pulled: `ollama pull qwen2.5-coder:32b`
- Default base URL: `http://localhost:11434/v1`

### Ollama (cloud / alternative)

Defined via the `OllamaCloud` client, also using `openai-generic`. Model and base URL
are driven by environment variables:

- `OLLAMA_CLOUD_URL` — the OpenAI-compatible endpoint (e.g., a cloud-hosted Ollama)
- `OLLAMA_CLOUD_MODEL` — the model name (e.g., `minimax-m2`, `glm-4.5`)
- `OLLAMA_CLOUD_API_KEY` — authentication key

### Anthropic

Two clients: `AnthropicSonnet` and `AnthropicOpus`, both using the `anthropic`
provider. Model names are hardcoded (`claude-sonnet-4-5`, `claude-opus-4-5`).

Requirements: `ANTHROPIC_API_KEY` environment variable.

---

## Per-agent model selection

`harness/baml_agents.py::_client_for_agent(config, agent)` maps the model string from
config to a BAML client name. It does this by inspecting the model string for keywords:

```python
def _client_for_agent(config, agent):
    model = config.model_for(agent).lower()

    if any(k in model for k in ("claude", "sonnet", "opus")):
        return default_client.with_options(client="AnthropicSonnet")
    if any(k in model for k in ("ollama", "qwen", "minimax", "glm")):
        return default_client.with_options(client="OllamaLocal")

    return default_client  # uses fallback chain
```

The `b.with_options(client=...)` call selects which named client from `clients.baml` to
use for the request. BAML handles provider authentication and HTTP transport.

---

## Per-agent model config

Each agent can use a different model. The config schema uses `crewai.*` keys for legacy
compatibility (the key names predate the BAML migration), but the values are consumed
by `_client_for_agent`, not by CrewAI or LiteLLM:

```json
{
  "crewai": {
    "model": {
      "default": "ollama/qwen2.5-coder:32b",
      "agents": {
        "clarifier":  "ollama/qwen2.5-coder:7b",
        "planner":    "ollama/qwen2.5-coder:7b",
        "research":   "anthropic/claude-haiku-3-5",
        "refiner":    "anthropic/claude-haiku-3-5",
        "architect":  "anthropic/claude-haiku-3-5",
        "builder":    "ollama/qwen2.5-coder:32b",
        "verifier":   "ollama/qwen2.5-coder:7b",
        "mapper":     "ollama/qwen2.5-coder:7b"
      }
    }
  }
}
```

Agents not listed fall back to `crewai.model.default`.

---

## Context window guidance

The harness injects only each agent's vault slice as typed BAML inputs, not the full
vault. The vault pre-loading step in `baml_loop.py` reads only the files listed in the
agent's read contract from the [vault contract spec](07-vault-contract.md).

| Agent | Typical input | Notes |
|---|---|---|
| Clarifier | 2k–20k tokens | Scales with spec file size |
| Planner | 2k–20k tokens | Specs + clarifications + existing plan |
| Research | 3k–8k tokens | Overview + structure + feature description |
| Refiner | 4k–12k tokens | Vault slice + feature description + criteria |
| Architect | 4k–10k tokens | Decision doc + entity pages + entrypoints |
| Builder | 8k–30k tokens | Tech plan + source files to modify |
| Verifier | 4k–10k tokens | Tech plan + test output |
| Mapper | 6k–15k tokens | Git diff + vault pages to update |

For local models with small context windows, keep entity pages concise and run
`/wiki-lint` periodically to prune stale pages.

---

## Model instantiation reference

BAML clients are instantiated by the BAML runtime based on `clients.baml` definitions.
Python code does not manually construct LLM objects — it calls BAML-generated typed
functions:

```python
from baml_client import b

# Default client (fallback OllamaLocal -> AnthropicSonnet)
result = b.PlanFeatures(specs_content=specs, clarifications=cls, existing_plan=plan)

# Per-agent override via with_options()
client = b.with_options(client="AnthropicSonnet")
result = b.ArchitectFeature(client=client, vault_structure=s, ...)
```

No conditional branching per backend is needed — BAML handles provider selection,
authentication, and transport.
