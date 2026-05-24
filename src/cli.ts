#!/usr/bin/env node
import { Command } from "commander";
import { wikiInit } from "./commands/init";
import { wikiRun } from "./commands/run";
import { wikiInstallDeps } from "./commands/install-deps";

const program = new Command();
program
  .name("wiki4llm")
  .description("Install wiki slash-commands into your LLM CLI tool")
  .version("0.1.0");

program
  .command("init")
  .description("Detect LLM tool, choose mode, generate slash-command files, scaffold vault")
  .action(() => wikiInit());

program
  .command("install-deps")
  .description("Install Python dependencies for Run Mode")
  .action(() => wikiInstallDeps());

program
  .description("Run the autonomous BAML agent loop (Run Mode only)")
  .option("--specs <dir>", "Specs directory", "specs")
  .option("--max-features <n>", "Stop after N features", parseInt)
  .option("--interactive", "Pause at human checkpoints")
  .option("--no-refine", "Skip the Refiner agent")
  .option("--no-verify", "Skip the Verifier agent")
  .option("--skip-clarify", "Skip the one-time spec clarification pass")
  .option("--force-remap", "Re-run the pre-flight mapper even if map/structure.md already exists")
  .option("--research <type>", "Enable Research agent (ux|web|accessibility|performance|competitor|security)")
  .option("--dry-run", "Print the plan without executing agents")
  .option("--verbose", "Stream agent output to stdout")
  .option("--trace", "Print a heartbeat line every 60s while an agent is thinking")
  .option("--maturity <mode>", "Override project maturity: prototype or stable")
  .action((opts) => wikiRun(opts));

program.parse();
