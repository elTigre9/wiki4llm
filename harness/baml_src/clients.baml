// LLM client definitions for the BAML harness path.
// Add new clients here; pick one via .wiki4llm.json -> crewai.model.default
// (env var BAML_DEFAULT_CLIENT overrides at runtime, see harness/baml_loop.py).

retry_policy DefaultRetry {
    max_retries 2
    strategy {
        type exponential_backoff
        delay_ms 500
        multiplier 2.0
    }
}

// Local Ollama (OpenAI-compatible endpoint at /v1).
client<llm> OllamaLocal {
    provider openai-generic
    retry_policy DefaultRetry
    options {
        base_url "http://localhost:11434/v1"
        model "qwen2.5-coder:32b"
        api_key "ollama"
        temperature 0.2
    }
}

// Ollama cloud (e.g. minimax-m2, glm-4.5). Override OLLAMA_CLOUD_URL/MODEL via env.
client<llm> OllamaCloud {
    provider openai-generic
    retry_policy DefaultRetry
    options {
        base_url env.OLLAMA_CLOUD_URL
        model env.OLLAMA_CLOUD_MODEL
        api_key env.OLLAMA_CLOUD_API_KEY
        temperature 0.2
    }
}

// Anthropic Claude Sonnet (default).
client<llm> AnthropicSonnet {
    provider anthropic
    retry_policy DefaultRetry
    options {
        model "claude-sonnet-4-5"
        api_key env.ANTHROPIC_API_KEY
        max_tokens 8192
    }
}

// Anthropic Claude Opus (heavier reasoning agents like Refiner/Architect).
client<llm> AnthropicOpus {
    provider anthropic
    retry_policy DefaultRetry
    options {
        model "claude-opus-4-5"
        api_key env.ANTHROPIC_API_KEY
        max_tokens 8192
    }
}

// The Default client is what every BAML function uses unless overridden.
// Python overrides per-agent via ClientRegistry (see harness/baml_loop.py).
client<llm> Default {
    provider fallback
    options {
        strategy [OllamaLocal, AnthropicSonnet]
    }
}
