import fs from "fs";
import path from "path";
import { execSync } from "child_process";

export function scaffoldVault(vaultPath: string, initGit: boolean): void {
  const dirs = ["raw/assets", "map", "entities", "decisions", "pending"];
  for (const d of dirs) fs.mkdirSync(path.join(vaultPath, d), { recursive: true });

  const now = new Date().toISOString();
  const frontmatter = (tag: string) => `---\ntags: [${tag}]\nupdated: ${now}\nsources: 0\n---\n\n`;

  writeIfMissing(path.join(vaultPath, "index.md"), frontmatter("overview") + "# Index\n\n");
  writeIfMissing(path.join(vaultPath, "log.md"), "# Log\n\n");
  writeIfMissing(path.join(vaultPath, "overview.md"), frontmatter("overview") + "# Overview\n\n");
  writeIfMissing(path.join(vaultPath, "pending", "questions.md"), frontmatter("pending") + "# Pending Questions\n\n");

  if (initGit) {
    try {
      execSync("git init", { cwd: vaultPath, stdio: "pipe" });
      execSync('git add . && git commit -m "wiki4llm: init"', { cwd: vaultPath, stdio: "pipe" });
    } catch { /* already a git repo or no git */ }
  }
}

function writeIfMissing(filePath: string, content: string): void {
  if (!fs.existsSync(filePath)) fs.writeFileSync(filePath, content, "utf8");
}

export function appendLog(vaultPath: string, entry: string): void {
  const logPath = path.join(vaultPath, "log.md");
  const line = `\n## [${new Date().toISOString()}] ${entry}\n`;
  fs.appendFileSync(logPath, line, "utf8");
}

export function commitVault(vaultPath: string, message: string): void {
  try {
    execSync(`git add . && git commit -m "wiki4llm: ${message}"`, { cwd: vaultPath, stdio: "pipe" });
  } catch { /* nothing to commit */ }
}

export function syncPull(vaultPath: string): void {
  try {
    execSync("git pull --rebase", { cwd: vaultPath, stdio: "pipe" });
  } catch (e: any) {
    console.warn("wiki4llm: git pull failed —", e.message);
  }
}

export function syncPush(vaultPath: string): void {
  try {
    execSync("git push", { cwd: vaultPath, stdio: "pipe" });
  } catch {
    try {
      execSync("git pull --rebase && git push", { cwd: vaultPath, stdio: "pipe" });
    } catch (e: any) {
      console.error("wiki4llm: push conflict — resolve manually.", e.message);
    }
  }
}

export function detectObsidian(): string | null {
  for (const bin of ["obsidian-cli", "obsidian"]) {
    try { execSync(`which ${bin}`, { stdio: "pipe" }); return bin; } catch { /* not found */ }
  }
  return null;
}

export function getLastMapCommit(vaultPath: string): string | null {
  const logPath = path.join(vaultPath, "log.md");
  if (!fs.existsSync(logPath)) return null;
  const content = fs.readFileSync(logPath, "utf8");
  const match = content.match(/commit:([a-f0-9]{7,40})/g);
  return match ? match[match.length - 1].replace("commit:", "") : null;
}
