import os
import re
from dataclasses import dataclass, field
from typing import Optional

_RESEARCH_TYPES = {"ux", "web", "accessibility", "performance", "competitor", "security"}

# Maps .wiki4llm.json apiKeys provider names to the env var LiteLLM expects
_PROVIDER_ENV = {
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "gemini":     "GEMINI_API_KEY",
    "groq":       "GROQ_API_KEY",
    "mistral":    "MISTRAL_API_KEY",
    "cohere":     "COHERE_API_KEY",
    "together":   "TOGETHERAI_API_KEY",
    "fireworks":  "FIREWORKS_API_KEY",
}

@dataclass
class ResearchConfig:
    enabled: bool = False
    type: str = "web"          # one of _RESEARCH_TYPES
    prompt: str = ""           # optional sub-prompt for extra focus
    tavily_api_key: str = ""   # set via apiKeys.tavily in .wiki4llm.json

    @classmethod
    def from_dict(cls, raw: dict, api_keys: dict = None) -> "ResearchConfig":
        t = raw.get("type", "web")
        if t not in _RESEARCH_TYPES:
            raise ValueError(f"research.type must be one of {sorted(_RESEARCH_TYPES)}, got '{t}'")
        tavily_raw = (api_keys or {}).get("tavily", "")
        tavily_key = os.environ.get(tavily_raw[1:], "") if tavily_raw.startswith("$") else tavily_raw
        return cls(
            enabled=raw.get("enabled", False),
            type=t,
            prompt=raw.get("prompt", ""),
            tavily_api_key=tavily_key,
        )


@dataclass
class SecurityConfig:
    level: str = "open"  # "open" | "standard" | "strict"
    shell_allow: bool = True
    shell_allowed_commands: list = field(default_factory=list)  # [] = all
    shell_blocked_patterns: list = field(default_factory=list)
    vault_allow_path_traversal: bool = True
    api_keys_require_env_refs: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "SecurityConfig":
        level = raw.get("level", "open")
        shell = raw.get("shell", {})
        vault = raw.get("vault", {})
        api = raw.get("apiKeys", {})
        return cls(
            level=level,
            shell_allow=shell.get("allow", level != "strict"),
            shell_allowed_commands=shell.get("allowedCommands", [] if level == "open" else ["git *", "npm *", "pip *", "python *", "python3 *"]),
            shell_blocked_patterns=shell.get("blockedPatterns", [] if level == "open" else [r"rm\s+-rf", r"curl\s+.*\|\s*sh", r"wget\s+.*\|\s*sh"]),
            vault_allow_path_traversal=vault.get("allowPathTraversal", level == "open"),
            api_keys_require_env_refs=api.get("requireEnvRefs", level != "open"),
        )

    def check_command(self, command: str) -> str | None:
        """Return an error string if the command is blocked, else None."""
        if not self.shell_allow:
            return "shell access is disabled (security.level=strict)"
        for pattern in self.shell_blocked_patterns:
            if re.search(pattern, command):
                return f"command blocked by security policy (matched: {pattern})"
        if self.shell_allowed_commands:
            allowed = any(
                re.match(re.escape(prefix).replace(r"\*", ".*"), command)
                for prefix in self.shell_allowed_commands
            )
            if not allowed:
                return f"command not in allowlist: {self.shell_allowed_commands}"
        return None

    def check_vault_path(self, path: str) -> str | None:
        """Return an error string if the vault path is disallowed, else None."""
        if not self.vault_allow_path_traversal and ".." in path:
            return f"path traversal blocked by security policy: {path}"
        return None



@dataclass
class HarnessConfig:
    vault_path: str
    specs_dir: str
    default_model: str
    agent_models: dict
    max_features: Optional[int]
    interactive: bool
    no_refine: bool
    no_verify: bool
    skip_clarify: bool
    force_remap: bool
    dry_run: bool
    verbose: bool
    trace: bool
    verifier_retries: int
    agent_timeout: int
    project_root: str
    api_keys: dict = field(default_factory=dict)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)

    def model_for(self, agent: str) -> str:
        return self.agent_models.get(agent, self.default_model)

    def inject_api_keys(self) -> None:
        """Set provider API keys as env vars. Values starting with '$' are treated as env var references."""
        for provider, value in self.api_keys.items():
            env_var = _PROVIDER_ENV.get(provider)
            if not env_var:
                continue
            if not value.startswith("$") and self.security.api_keys_require_env_refs:
                msg = f"wiki4llm: bare API key for '{provider}' in .wiki4llm.json. Use \"$ENV_VAR\" references."
                if self.security.level == "strict":
                    raise ValueError(msg)
                print(f"WARN: {msg}")
            resolved = os.environ.get(value[1:], "") if value.startswith("$") else value
            if resolved:
                os.environ[env_var] = resolved

    @classmethod
    def from_dict(cls, raw: dict) -> "HarnessConfig":
        crewai = raw.get("crewai", {})
        model_cfg = crewai.get("model", {})
        run_cfg = raw.get("_run", {})
        vault_cfg = raw.get("vault", {})
        project_cfg = raw.get("project", {})

        return cls(
            vault_path=vault_cfg.get("path", "./.wiki"),
            specs_dir=run_cfg.get("specsDir", project_cfg.get("specsDir", "specs")),
            default_model=model_cfg.get("default", "ollama/qwen2.5-coder:32b"),
            agent_models=model_cfg.get("agents", {}),
            max_features=crewai.get("maxFeatures"),
            interactive=crewai.get("interactive", False),
            no_refine=run_cfg.get("noRefine", False),
            no_verify=run_cfg.get("noVerify", False),
            skip_clarify=run_cfg.get("skipClarify", False),
            force_remap=run_cfg.get("forceRemap", False),
            dry_run=run_cfg.get("dryRun", False),
            verbose=run_cfg.get("verbose", False),
            trace=run_cfg.get("trace", False),
            verifier_retries=crewai.get("verifierRetries", 2),
            agent_timeout=crewai.get("agentTimeout", 120),
            project_root=".",
            api_keys=raw.get("apiKeys", {}),
            security=SecurityConfig.from_dict(raw.get("security", {})),
            research=ResearchConfig.from_dict(raw.get("research", {}), raw.get("apiKeys", {})),
        )
