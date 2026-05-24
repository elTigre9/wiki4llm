# `wiki4llm run` Command

`wiki4llm run` is the entry point for Run Mode. The Node layer is a thin launcher —
it validates dependencies and shells out to the Python harness. All orchestration
logic lives in Python.

---

## `src/commands/run.ts`

```typescript
import { spawnSync } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";
import { loadConfig } from "../config";

interface RunOptions {
  specs?: string;
  maxFeatures?: number;
  interactive?: boolean;
  noRefine?: boolean;
  noVerify?: boolean;
  skipClarify?: boolean;
  forceRemap?: boolean;
  dryRun?: boolean;
  verbose?: boolean;
}

export function wikiRun(opts: RunOptions): void {
  const config = loadConfig();
  if (!config) {
    console.error("wiki4llm: No .wiki4llm.json found. Run `wiki4llm init` first.");
    process.exit(1);
  }
  if (!config.crewai) {
    console.error("wiki4llm: This project is not configured for Run Mode.");
    console.error("Re-run `wiki4llm init` and select Run Mode.");
    process.exit(1);
  }

  const pythonPath = "python3";
  const harnessScript = path.resolve("harness/main.py");

  checkPythonDeps(pythonPath, harnessScript);

  const mergedConfig = buildMergedConfig(config, opts);
  const tmpConfig = path.join(os.tmpdir(), `wiki4llm-config-${Date.now()}.json`);
  fs.writeFileSync(tmpConfig, JSON.stringify(mergedConfig, null, 2));

  const result = spawnSync(pythonPath, [harnessScript, "--config", tmpConfig], {
    stdio: "inherit",
    cwd: process.cwd(),
  });

  fs.unlinkSync(tmpConfig);
  process.exit(result.status ?? 1);
}

function checkPythonDeps(pythonPath: string, harnessScript: string): void {
  if (!fs.existsSync(harnessScript)) {
    console.error(`wiki4llm: Harness script not found at ${harnessScript}`);
    console.error("Re-run `wiki4llm init` to restore it.");
    process.exit(1);
  }

  const check = spawnSync(pythonPath, ["-c", "import baml_py"], { stdio: "pipe" });
  if (check.status !== 0) {
    console.error("wiki4llm: Python harness dependencies not found.");
    console.error("Run: pip install -r harness/requirements.txt");
    process.exit(1);
  }
}

function buildMergedConfig(config: any, opts: RunOptions): object {
  return {
    ...config,
    crewai: {
      ...config.crewai,
      ...(opts.maxFeatures !== undefined && { maxFeatures: opts.maxFeatures }),
      ...(opts.interactive !== undefined && { interactive: opts.interactive }),
    },
    _run: {
      specsDir: opts.specs ?? config.project.specsDir ?? "specs",
      noRefine: opts.noRefine ?? false,
      noVerify: opts.noVerify ?? false,
      skipClarify: opts.skipClarify ?? false,
      forceRemap: opts.forceRemap ?? false,
      dryRun: opts.dryRun ?? false,
      verbose: opts.verbose ?? false,
    },
  };
}
```

---

## `harness/main.py`

Entry point for the Python harness.

```python
import argparse
import json
import sys
from pathlib import Path
from config import HarnessConfig

def _load_dotenv(config_path: str) -> None:
    try:
        from dotenv import load_dotenv
        env_file = Path(config_path).parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
    except ImportError:
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to merged config JSON")
    args = parser.parse_args()

    with open(args.config) as f:
        raw = json.load(f)

    _load_dotenv(args.config)
    config = HarnessConfig.from_dict(raw)
    config.inject_api_keys()

    print(f"\nwiki4llm Run Mode")
    print(f"  Vault:   {config.vault_path}")
    print(f"  Specs:   {config.specs_dir}")
    print(f"  Model:   {config.default_model}")
    agents = []
    if not config.skip_clarify:
        agents.append("clarifier")
    agents.append("planner")
    if config.research.enabled:
        agents.append("research")
    if not config.no_refine:
        agents.append("refiner")
    agents += ["architect", "builder"]
    if not config.no_verify:
        agents.append("verifier")
    agents.append("mapper")
    print("  Agents:  " + "  ".join(f"{a}={config.model_for(a)}" for a in agents) + "\n")

    from baml_loop import run_loop_baml
    sys.exit(run_loop_baml(config))

if __name__ == "__main__":
    main()
```

---

## `harness/config.py`

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SecurityConfig:
    level: str = "open"
    shell_allow: bool = True
    shell_allowed_commands: list = field(default_factory=list)
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
            shell_allowed_commands=shell.get("allowedCommands", []),
            shell_blocked_patterns=shell.get("blockedPatterns", []),
            vault_allow_path_traversal=vault.get("allowPathTraversal", level == "open"),
            api_keys_require_env_refs=api.get("requireEnvRefs", level != "open"),
        )

@dataclass
class ResearchConfig:
    enabled: bool = False
    type: str = "web"
    prompt: str = ""
    tavily_api_key: str = ""

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
    engine: str = "baml"
    maturity: str = "stable"
    api_keys: dict = field(default_factory=dict)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)

    def model_for(self, agent: str) -> str:
        return self.agent_models.get(agent, self.default_model)

    def inject_api_keys(self) -> None:
        import os
        _PROVIDER_ENV = {
            "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY", "cohere": "COHERE_API_KEY",
            "together": "TOGETHERAI_API_KEY", "fireworks": "FIREWORKS_API_KEY",
        }
        for provider, value in self.api_keys.items():
            env_var = _PROVIDER_ENV.get(provider)
            if not env_var:
                continue
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
            engine=raw.get("engine", "baml"),
            maturity=project_cfg.get("maturity", "stable"),
            project_root=".",
            api_keys=raw.get("apiKeys", {}),
            security=SecurityConfig.from_dict(raw.get("security", {})),
            research=ResearchConfig.from_dict(raw.get("research", {}), raw.get("apiKeys", {})),
        )
```
