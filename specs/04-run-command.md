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
  model?: string;
  maxFeatures?: number;
  interactive?: boolean;
  noRefine?: boolean;
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

  const pythonPath = config.crewai.pythonPath ?? "python3";
  const harnessScript = path.resolve(config.crewai.harnessScript ?? "harness/main.py");

  checkPythonDeps(pythonPath, harnessScript);

  // Merge config with CLI flags and write to a temp file
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

  const check = spawnSync(pythonPath, ["-c", "import crewai"], { stdio: "pipe" });
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
      ...(opts.model && { model: { ...config.crewai.model, default: opts.model } }),
      ...(opts.maxFeatures !== undefined && { maxFeatures: opts.maxFeatures }),
      ...(opts.interactive !== undefined && { interactive: opts.interactive }),
    },
    _run: {
      specsDir: opts.specs ?? config.project.specsDir ?? "specs",
      noRefine: opts.noRefine ?? false,
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
from loop import run_loop
from config import HarnessConfig

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to merged config JSON")
    args = parser.parse_args()

    with open(args.config) as f:
        raw = json.load(f)

    config = HarnessConfig.from_dict(raw)

    print(f"\nwiki4llm Run Mode")
    print(f"  Vault:   {config.vault_path}")
    print(f"  Specs:   {config.specs_dir}")
    print(f"  Model:   {config.default_model}")
    print(f"  Agents:  planner={config.model_for('planner')}  "
          f"refiner={config.model_for('refiner')}  "
          f"builder={config.model_for('builder')}\n")

    sys.exit(run_loop(config))

if __name__ == "__main__":
    main()
```

---

## `harness/config.py`

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class HarnessConfig:
    vault_path: str
    specs_dir: str
    default_model: str
    agent_models: dict
    max_features: Optional[int]
    interactive: bool
    no_refine: bool
    dry_run: bool
    verbose: bool
    project_root: str

    def model_for(self, agent: str) -> str:
        return self.agent_models.get(agent, self.default_model)

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
            dry_run=run_cfg.get("dryRun", False),
            verbose=run_cfg.get("verbose", False),
            project_root=".",
        )
```
