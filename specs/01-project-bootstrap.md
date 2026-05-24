# Project Bootstrap

Build this project from scratch. This file defines the full project structure,
dependencies, and build configuration.

---

## `package.json`

```json
{
  "name": "wiki4llm",
  "version": "0.1.0",
  "description": "Persistent vault context for LLM coding agents",
  "bin": { "wiki4llm": "./dist/cli.js" },
  "main": "./dist/cli.js",
  "scripts": {
    "build": "tsc",
    "dev": "ts-node src/cli.ts",
    "prepublishOnly": "npm run build"
  },
  "dependencies": {
    "commander": "^12.0.0",
    "fast-glob": "^3.3.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/node": "^20.0.0",
    "ts-node": "^10.9.0"
  }
}
```

---

## `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "declaration": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

---

## `src/cli.ts`

Entry point. Registers all commands.

```typescript
#!/usr/bin/env node
import { Command } from "commander";
import { wikiInit } from "./commands/init";
import { wikiRun } from "./commands/run";

const program = new Command();
program
  .name("wiki4llm")
  .description("Persistent vault context for LLM coding agents")
  .version("0.1.0");

program
  .command("init")
  .description("Set up wiki4llm in the current project")
  .action(() => wikiInit());

program
  .command("run")
  .description("Run the autonomous BAML agent loop (Run Mode only)")
  .option("--specs <dir>", "Specs directory", "specs")
  .option("--max-features <n>", "Stop after N features", parseInt)
  .option("--interactive", "Pause at human checkpoints")
  .option("--no-refine", "Skip the Refiner agent")
  .option("--no-verify", "Skip the Verifier agent")
  .option("--skip-clarify", "Skip the one-time spec clarification pass")
  .option("--force-remap", "Re-run the pre-flight mapper")
  .option("--dry-run", "Print the plan without executing agents")
  .option("--verbose", "Stream agent output to stdout")
  .action((opts) => wikiRun(opts));

program.parse();
```

---

## `src/config.ts`

Config type definitions and load/save helpers.

```typescript
import fs from "fs";
import path from "path";

export interface VaultConfig {
  path: string;
  name: string;
  git: boolean;
  sync: boolean;
  external: boolean;
}

export interface ProjectConfig {
  name: string;
  ignore: string[];
  specsDir: string;
}

export interface CrewAIModelConfig {
  default: string;
  agents?: Partial<Record<"clarifier" | "planner" | "research" | "refiner" | "architect" | "builder" | "verifier" | "mapper", string>>;
}

export interface CrewAIConfig {
  model: CrewAIModelConfig;
  maxFeatures: number | null;
  interactive: boolean;
  verifierRetries: number;
  agentTimeout: number;
}

export interface SlashCommandConfig {
  mode: "context" | "harness";
  tool: "claude" | "opencode";
}

export interface WikiConfig {
  vault: VaultConfig;
  project: ProjectConfig;
  slashCommands?: SlashCommandConfig;
  crewai?: CrewAIConfig;
}

const CONFIG_FILE = ".wiki4llm.json";

export function loadConfig(cwd = process.cwd()): WikiConfig | null {
  const configPath = path.join(cwd, CONFIG_FILE);
  if (!fs.existsSync(configPath)) return null;
  return JSON.parse(fs.readFileSync(configPath, "utf8")) as WikiConfig;
}

export function saveConfig(config: WikiConfig, cwd = process.cwd()): void {
  const configPath = path.join(cwd, CONFIG_FILE);
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");
}

export function defaultConfig(name: string): WikiConfig {
  return {
    vault: { path: "./.wiki", name, git: true, sync: false, external: false },
    project: { name, ignore: ["node_modules", "dist", ".git", ".wiki"], specsDir: "specs" },
  };
}
```

---

## `harness/requirements.txt`

```
baml-py>=0.222.0
python-dotenv>=1.0.0
```

---

## `.gitignore` additions

When `wiki4llm init` runs, it appends these lines to `.gitignore` if not already present:

```
.claude/commands/
.opencode/commands/
dist/
```

The vault (`.wiki/`) is intentionally NOT gitignored — it should be committed.
