import { spawnSync } from "child_process";
import path from "path";
import fs from "fs";
import { loadConfig } from "../config";

export function wikiInstallDeps(): void {
  const config = loadConfig();
  if (!config.crewai) {
    console.error("wiki4llm: This project is not configured for Run Mode.");
    console.error("Re-run `wiki4llm init` and select Run Mode.");
    process.exit(1);
  }

  const requirementsPath = path.resolve("harness", "requirements.txt");
  if (!fs.existsSync(requirementsPath)) {
    console.error(`wiki4llm: requirements.txt not found at ${requirementsPath}`);
    process.exit(1);
  }

  const pythonPath = "python3";
  console.log(`wiki4llm: installing Python deps from ${requirementsPath}...`);
  const result = spawnSync(pythonPath, ["-m", "pip", "install", "-r", requirementsPath], { stdio: "inherit" });
  process.exit(result.status ?? 1);
}
