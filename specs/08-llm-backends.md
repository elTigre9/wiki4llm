# LLM Backends

The harness uses LiteLLM (bundled with CrewAI) for all model calls. Model strings are
passed directly to `crewai.LLM(model=...)` — no adapter code per backend.

---

## Supported backends

### Ollama (local)

Format: `ollama/<model>`

Examples: `ollama/qwen2.5-coder:32b`, `ollama/deepseek-coder-v2:16b`, `ollama/codestral:22b`

Requirements:
- Ollama running: `ollama serve`
- Model pulled: `ollama pull qwen2.5-coder:32b`
- Optional: `OLLAMA_HOST=http://localhost:11434` (this is the default)

---

### llama.cpp / OpenAI-compatible local server

Format: `openai/<any-name>` (name is arbitrary)

Requirements:
- Server running with OpenAI-compatible API (llama.cpp `--server`, vllm, LM Studio)
- `OPENAI_BASE_URL=http://localhost:8080/v1`
- `OPENAI_API_KEY=dummy` (LiteLLM requires this even for local servers; value ignored)

---

### Claude (Anthropic)

Format: `anthropic/<model>`

Examples: `anthropic/claude-sonnet-4-5`, `anthropic/claude-haiku-3-5`

Requirements: `ANTHROPIC_API_KEY` in environment

---

### OpenAI

Format: `openai/<model>`

Examples: `openai/gpt-4o`, `openai/gpt-4o-mini`

Requirements: `OPENAI_API_KEY` in environment. Do not set `OPENAI_BASE_URL`.

---

### Gemini

Format: `gemini/<model>`

Examples: `gemini/gemini-1.5-pro`, `gemini/gemini-2.0-flash`

Requirements: `GEMINI_API_KEY` in environment

---

## Per-agent model config

Each agent can use a different model. Useful for mixing a fast local model for
Planner/Mapper with a stronger model for Refiner/Architect/Builder.

```json
{
  "crewai": {
    "model": {
      "default": "ollama/qwen2.5-coder:32b",
      "agents": {
        "planner":   "ollama/qwen2.5-coder:7b",
        "refiner":   "anthropic/claude-haiku-3-5",
        "architect": "anthropic/claude-haiku-3-5",
        "builder":   "ollama/qwen2.5-coder:32b",
        "mapper":    "ollama/qwen2.5-coder:7b"
      }
    }
  }
}
```

---

## Model instantiation

```python
from crewai import LLM

def make_llm(model_string: str) -> LLM:
    return LLM(model=model_string)
```

LiteLLM routes based on the model string prefix and environment variables.
No conditional logic per backend is needed.

---

## Context window guidance

The harness injects only each agent's vault slice, not the full vault.

| Agent | Typical input | Notes |
|---|---|---|
| Planner | 2k–20k tokens | Scales with spec file size |
| Refiner | 4k–12k tokens | Vault slice + feature description |
| Architect | 4k–10k tokens | Decision doc + entity pages |
| Builder | 8k–30k tokens | Plan + source files to modify |
| Mapper | 6k–15k tokens | Git diff + vault pages to update |

For local models with small context windows, keep entity pages concise and run
`/wiki-lint` periodically to prune stale pages.
