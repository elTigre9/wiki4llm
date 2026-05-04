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
  refine?: boolean;
  verify?: boolean;
  skipClarify?: boolean;
  forceRemap?: boolean;
  research?: string;
  researchPrompt?: string;
  dryRun?: boolean;
  verbose?: boolean;
  trace?: boolean;
}

export function wikiRun(opts: RunOptions): void {
  const config = loadConfig();
  if (!config.crewai) {
    console.error("wiki4llm: This project is not configured for Run Mode.");
    console.error("Re-run `wiki4llm init` and select Run Mode.");
    process.exit(1);
  }

  const pythonPath = config.crewai.pythonPath ?? "python3";
  const harnessScript = path.resolve(config.crewai.harnessScript);

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

  const check = spawnSync(pythonPath, ["-c", "import crewai"], { stdio: "pipe" });
  if (check.status !== 0) {
    console.error("wiki4llm: Python harness dependencies not found.");
    console.error("Run: wiki4llm install-deps");
    process.exit(1);
  }
}

function buildMergedConfig(config: any, opts: RunOptions): object {
  return {
    ...config,
    crewai: {
      ...config.crewai,
      ...(opts.model && { model: { default: opts.model, agents: {} } }),
      ...(opts.maxFeatures !== undefined && { maxFeatures: opts.maxFeatures }),
      ...(opts.interactive !== undefined && { interactive: opts.interactive }),
    },
    _run: {
      specsDir: opts.specs ?? config.project.specsDir ?? "specs",
      noRefine: opts.refine === false,
      noVerify: opts.verify === false,
      skipClarify: opts.skipClarify ?? false,
      forceRemap: opts.forceRemap ?? false,
      dryRun: opts.dryRun ?? false,
      verbose: opts.verbose ?? false,
      trace: opts.trace ?? false,
    },
    research: opts.research
      ? { enabled: true, type: opts.research, prompt: opts.researchPrompt ?? "" }
      : (config.research ?? { enabled: false, type: "web", prompt: "" }),
  };
}
