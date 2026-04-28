import fs from "fs";
import path from "path";
import { execSync } from "child_process";

/** Read last N lines of a file without loading the whole thing. */
function tail(filePath: string, lines = 5): string {
  if (!fs.existsSync(filePath)) return "";
  const content = fs.readFileSync(filePath, "utf8");
  return content.split("\n").slice(-lines).join("\n").trim();
}

/** Parse index.md into a compact list of "- [[Page]]: summary" lines. */
function parseIndex(indexPath: string): string {
  if (!fs.existsSync(indexPath)) return "(index not yet generated)";
  const content = fs.readFileSync(indexPath, "utf8");
  // Extract lines that look like list items with wikilinks
  const lines = content
    .split("\n")
    .filter((l) => l.match(/^\s*[-*]\s+\[\[/))
    .slice(0, 40); // cap at 40 entries to keep preamble lean
  return lines.length ? lines.join("\n") : content.slice(0, 800);
}

/** Get git diff --stat since last vault commit (best-effort). */
function gitDiffStat(vaultPath: string): string {
  try {
    const result = execSync("git diff --stat HEAD", { cwd: vaultPath, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] });
    return result.trim() || "(no uncommitted changes)";
  } catch {
    return "(git not available or no commits yet)";
  }
}

export function buildVaultPreamble(vaultPath: string): string {
  const logTail = tail(path.join(vaultPath, "log.md"), 5);
  const indexSummary = parseIndex(path.join(vaultPath, "index.md"));
  const diffStat = gitDiffStat(vaultPath);

  return `<!-- VAULT STATE PREAMBLE (injected by wiki4llm) -->
## Current Vault State

### Recent log entries (last 5)
${logTail || "(log is empty)"}

### Index snapshot
${indexSummary}

### Uncommitted changes since last vault commit
${diffStat}
<!-- END VAULT STATE PREAMBLE -->

`;
}
