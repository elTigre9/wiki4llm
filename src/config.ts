import fs from "fs";
import path from "path";

export type Mode = "context" | "harness" | "run";
export type Tool = "claude" | "opencode";

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
  agents?: Partial<Record<"planner" | "research" | "refiner" | "architect" | "builder" | "verifier" | "mapper", string>>;
}

/**
 * API keys for remote model providers. Used by Run Mode only — the Python harness
 * injects these as env vars before agents run. Context and Harness modes run inside
 * the LLM CLI tool (Claude Code, OpenCode), which manages its own auth; set keys
 * there via shell environment or the tool's own config.
 *
 * Values can be literal keys or env var references like "$OPENAI_API_KEY".
 * Supported providers: openai, anthropic, gemini, groq, mistral, cohere, together, fireworks
 */
export type ApiKeysConfig = Partial<Record<
  "openai" | "anthropic" | "gemini" | "groq" | "mistral" | "cohere" | "together" | "fireworks",
  string
>>;

export interface CrewAIConfig {
  model: CrewAIModelConfig;
  maxFeatures: number | null;
  interactive: boolean;
  verifierRetries: number;
  agentTimeout: number;
}

export interface HarnessConfig {
  maxIterations: number;
  noBlock: boolean;
  agents: string[];
}

export type SecurityLevel = "open" | "standard" | "strict";

export interface SecurityConfig {
  level: SecurityLevel;
  shell: {
    allow: boolean;
    allowedCommands: string[];  // [] = all; ["git *", "npm *"] = allowlist
    blockedPatterns: string[];  // regex strings to reject
  };
  vault: {
    allowPathTraversal: boolean;
  };
  apiKeys: {
    requireEnvRefs: boolean;  // true = warn (standard) or error (strict) on bare key strings
  };
}

export const SECURITY_PRESETS: Record<SecurityLevel, SecurityConfig> = {
  open: {
    level: "open",
    shell: { allow: true, allowedCommands: [], blockedPatterns: [] },
    vault: { allowPathTraversal: true },
    apiKeys: { requireEnvRefs: false },
  },
  standard: {
    level: "standard",
    shell: { allow: true, allowedCommands: ["git *", "npm *", "pip *", "python *", "python3 *"], blockedPatterns: ["rm\\s+-rf", "curl\\s+.*\\|\\s*sh", "wget\\s+.*\\|\\s*sh"] },
    vault: { allowPathTraversal: false },
    apiKeys: { requireEnvRefs: true },
  },
  strict: {
    level: "strict",
    shell: { allow: false, allowedCommands: [], blockedPatterns: [] },
    vault: { allowPathTraversal: false },
    apiKeys: { requireEnvRefs: true },
  },
};

export interface Config {
  mode: Mode;
  tool: Tool;
  vault: VaultConfig;
  project: ProjectConfig;
  harness: HarnessConfig;
  crewai?: CrewAIConfig;
  apiKeys?: ApiKeysConfig;
  security: SecurityConfig;
}

const DEFAULTS: Config = {
  mode: "context",
  tool: "claude",
  vault: { path: "./.wiki", name: "project", git: true, sync: false, external: false },
  project: { name: "project", ignore: ["node_modules", "dist", ".git"], specsDir: "specs" },
  harness: { maxIterations: 3, noBlock: false, agents: ["architect", "builder", "mapper", "lint"] },
  security: SECURITY_PRESETS.open,
};

export function loadConfig(cwd = process.cwd()): Config {
  const cfgPath = path.join(cwd, ".wiki4llm.json");
  if (!fs.existsSync(cfgPath)) return DEFAULTS;
  const raw = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
  const level: SecurityLevel = raw.security?.level ?? DEFAULTS.security.level;
  const preset = SECURITY_PRESETS[level] ?? SECURITY_PRESETS.open;
  return {
    mode: raw.mode ?? DEFAULTS.mode,
    tool: raw.tool ?? DEFAULTS.tool,
    vault: { ...DEFAULTS.vault, ...raw.vault },
    project: { ...DEFAULTS.project, ...raw.project },
    harness: { ...DEFAULTS.harness, ...raw.harness },
    ...(raw.crewai && { crewai: raw.crewai }),
    ...(raw.apiKeys && { apiKeys: raw.apiKeys }),
    security: {
      ...preset,
      ...raw.security,
      shell: { ...preset.shell, ...raw.security?.shell },
      vault: { ...preset.vault, ...raw.security?.vault },
      apiKeys: { ...preset.apiKeys, ...raw.security?.apiKeys },
    },
  };
}

export function resolveVaultPath(cfg: Config, cwd = process.cwd()): string {
  if (cfg.vault.external) {
    const home = process.env.HOME || process.env.USERPROFILE || "~";
    return path.join(home, ".wiki4llm", "vaults", path.basename(cfg.vault.name));
  }
  return path.resolve(cwd, cfg.vault.path);
}
