import { Config, Tool } from "../config";

// Frontmatter format per tool
function frontmatter(tool: Tool, name: string, description: string, hint = ""): string {
  if (tool === "claude") {
    return `---\ndescription: ${description}${hint ? `\nargument-hint: '${hint}'` : ""}\nallowed-tools:\n  - Read\n  - Write\n  - Bash\n  - Glob\n---\n\n`;
  }
  // OpenCode uses the same markdown structure
  return `---\ndescription: ${description}${hint ? `\nargument-hint: '${hint}'` : ""}\n---\n\n`;
}

function preambleInstruction(vaultPath: string): string {
  return `Before doing anything else, read the current vault state:
- Last 5 entries in \`${vaultPath}/log.md\`
- All entries in \`${vaultPath}/index.md\`
- Run \`git diff --stat HEAD\` inside \`${vaultPath}\` to see uncommitted changes

Use this context to orient yourself before executing the task below.

---

`;
}

function mapCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:map", "Map codebase into vault", "[--ask]");
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Map Codebase into Vault

## Formatting Rules (mandatory)

- **All cross-references between vault pages MUST use Obsidian wikilink syntax: \`[[PageName]]\` or \`[[folder/PageName]]\`.**
- Do NOT use markdown links (\`[text](path)\`) for internal vault references.
- Every entity page must link to at least one \`map/\` page using \`[[wikilinks]]\`.
- Every \`map/\` page must link back to relevant entity pages using \`[[wikilinks]]\`.

## Instructions

1. Walk the project directory, ignoring: ${cfg.project.ignore.join(", ")}.
2. Read key files: entry points, package manifests, config files, README.
3. Fully rewrite these vault pages (create if missing):
   - \`${vaultPath}/map/structure.md\` — directory tree with a one-line role for each file/dir; link to entity pages with \`[[wikilinks]]\`
   - \`${vaultPath}/map/dependencies.md\` — key dependencies, versions, relationships; link to entity pages with \`[[wikilinks]]\`
   - \`${vaultPath}/map/entrypoints.md\` — main entry files and their purpose; link to entity pages with \`[[wikilinks]]\`
4. Create or update one \`${vaultPath}/entities/<Name>.md\` page per major module/class/service. Each page must reference related entities and map pages using \`[[wikilinks]]\`.
5. Rewrite \`${vaultPath}/overview.md\` with a high-level summary; link to all entity pages and map pages using \`[[wikilinks]]\`.
6. Rewrite \`${vaultPath}/index.md\` — list every vault page with a one-line summary, each entry as a \`[[wikilink]]\`.
7. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] map | ${cfg.project.name} | commit:<git-hash>\`
8. Run \`git add . && git commit -m "wiki4llm: map ${cfg.project.name}"\` inside \`${vaultPath}\`.

If \`--ask\` was passed: surface any ambiguities (unclear module boundaries, missing docs, naming conflicts) as a numbered list and wait for confirmation before proceeding.
`;
}

function bootstrapCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:bootstrap", "Seed vault from spec files and scaffold a new project");
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Bootstrap Project from Spec Files

## Instructions

1. Read all files from the \`${cfg.project.specsDir}/\` directory. Error if the directory does not exist or is empty.
2. Copy each spec file into \`${vaultPath}/raw/\`.
3. Read each spec file in full.
4. Scaffold the initial project structure based on the specs.
5. Run the first build phase as described in the specs.
6. Write \`${vaultPath}/overview.md\` summarizing the project purpose and architecture.
7. Write \`${vaultPath}/map/structure.md\` with the planned directory layout.
8. Update \`${vaultPath}/index.md\` with entries for every page you create.
9. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] bootstrap | ${cfg.project.name} | commit:<git-hash>\`
10. Run \`git add . && git commit -m "wiki4llm: bootstrap ${cfg.project.name}"\` inside \`${vaultPath}\`.

After the first build completes, run \`/wiki-map\` to map the generated codebase.
`;
}

function adviseCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:advise", "Vault-aware second opinion on an idea before you build", "<idea>");
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Vault-Aware Advisory

The user's idea or question is passed as the command argument.

## Instructions

Read the vault state above, then critique the idea:

1. **Conflicts** — does this contradict existing architecture, decisions, or entity pages?
2. **Missing context** — what vault knowledge is relevant that the idea doesn't account for?
3. **Risks** — what could go wrong given the current codebase state?
4. **Refinements** — suggest concrete improvements.

This is advisory only. Do not write or modify any vault files.
`;
}

function buildCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:build", "Read vault then plan and implement a feature", '[--feature "..."] [--ask]');
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Build Feature with Vault Context

The feature description is passed via \`--feature "<description>"\`. If not provided, infer from recent log entries and user context.

## Instructions

1. Read \`${vaultPath}/index.md\` to find relevant vault pages.
2. Read \`${vaultPath}/overview.md\`, relevant \`${vaultPath}/entities/\` pages, and \`${vaultPath}/map/\` pages.
3. Plan and implement the feature.
4. Update affected \`${vaultPath}/entities/<Name>.md\` pages with \`[[wikilinks]]\`.
5. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] build | <feature> | commit:<git-hash>\`
6. Run \`git add . && git commit -m "wiki4llm: build <feature>"\` inside \`${vaultPath}\`.

If \`--ask\` was passed: ask the user clarifying questions before writing any code. Number each question.
`;
}

function updateCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:update", "Incrementally update vault from git diff since last map", "[--ask]");
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Incremental Vault Update

## Instructions

1. Read the last entry in \`${vaultPath}/log.md\` to find the prior map commit hash.
2. Run \`git diff --name-only <last-map-commit>\` in the project root to get changed files.
3. Re-read each changed file.
4. Update affected \`${vaultPath}/entities/\` pages, \`${vaultPath}/map/\` pages, \`${vaultPath}/overview.md\`, and \`${vaultPath}/index.md\`.
5. Add or update \`[[wikilinks]]\` for any new cross-references introduced by the changes.
6. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] update | <N> files | commit:<git-hash>\`
7. Run \`git add . && git commit -m "wiki4llm: update <N> files"\` inside \`${vaultPath}\`.

If \`--ask\` was passed: note any new ambiguities, contradictions, or stale claims found while updating.
`;
}

function lintCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:lint", "Health-check the vault");
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Vault Health Check (Lint)

## Instructions

1. **Orphan pages** — find pages with no inbound \`[[wikilinks]]\`. List them.
2. **Stale claims** — find pages not updated since the last \`/wiki-map\`. Flag them.
3. **Missing entity pages** — find things referenced in prose but lacking their own page. List them.
4. **Broken links** — find \`[[wikilinks]]\` pointing to non-existent pages. List them.
5. **Suggestions** — propose new questions to investigate or sources to add.
6. Fix what you can automatically (add missing links, stub missing pages).
7. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] lint | ${cfg.project.name} | commit:<git-hash>\`
8. Run \`git add . && git commit -m "wiki4llm: lint ${cfg.project.name}"\` inside \`${vaultPath}\`.
`;
}

function runCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:run", "Harness Mode — Architect + Builder phase", "[--plan <folder>] [--no-block]");
  const preamble = preambleInstruction(vaultPath);
  const specsDir = `\`<specsDir>\` (default: \`${cfg.project.specsDir}/\`, override with \`--plan <folder>\`)`;
  return `${fm}${preamble}# Task: Harness Mode — Architect + Builder

This is phase 1 of 2 in the harness loop. You are running the **Architect** and **Builder** agents in this context.

**Context is intentionally cleared between phase pairs.** The vault is the only memory that persists across contexts.

---

## Agent: Architect

### 1. Read specs

Read all files from ${specsDir}. If the directory does not exist or is empty, stop and tell the user.

### 2. Load or create the plan

Check if \`${vaultPath}/pending/plan.md\` exists.

- **If it does not exist:** Parse the spec files and decompose them into a feature list. Write \`${vaultPath}/pending/plan.md\` in this format:
  \`\`\`markdown
  # Plan
  <!-- Do not edit the feature list format — it is machine-read -->
  - [ ] <feature slug>: <one-line description>
  - [ ] <feature slug>: <one-line description>
  \`\`\`
- **If it exists:** Re-read the spec files and verify the plan is still aligned. Add any missing features as unchecked items. Do not remove or reorder existing items.

### 3. Pick the next feature

Find the first unchecked item (\`- [ ]\`) in \`${vaultPath}/pending/plan.md\`. This is the active feature.

If all items are checked, print:
> ✅ All features complete. Nothing left to build.

Then stop.

### 4. Handle grey areas

If anything about the active feature is ambiguous:

- Append structured questions to \`${vaultPath}/pending/questions.md\`:
  \`\`\`
  ## Q: <question>
  Feature: <feature slug>
  Options:
  1. <option>
  2. <option>
  3. (free-form input)
  \`\`\`
- If \`--no-block\` was NOT passed: print the questions as a numbered list and **stop**. Wait for the user to answer before continuing.
- If \`--no-block\` was passed: make a best-guess, note the assumption in the decision page, and continue.

### 5. Write the decision page

Write \`${vaultPath}/decisions/<feature-slug>.md\` with:
- Feature description
- Files and entities that will be affected
- Approach and rationale
- Any assumptions made

### 6. Commit

Append to \`${vaultPath}/log.md\`:
\`## [<timestamp>] harness:architect | <feature-slug> | commit:<git-hash>\`

Run \`git add . && git commit -m "wiki4llm: architect <feature-slug>"\` inside \`${vaultPath}\`.

---

## Agent: Builder

1. Read \`${vaultPath}/decisions/<feature-slug>.md\` written by the Architect above.
2. Read all relevant \`${vaultPath}/entities/\` and \`${vaultPath}/map/\` pages referenced in the decision.
3. Implement the feature.
4. Update affected \`${vaultPath}/entities/<Name>.md\` pages with \`[[wikilinks]]\`.
5. If you hit a grey area and \`--no-block\` was NOT passed: append to \`${vaultPath}/pending/questions.md\`, print the questions, and stop.
6. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] harness:builder | <feature-slug> | commit:<git-hash>\`
7. Run \`git add . && git commit -m "wiki4llm: builder <feature-slug>"\` inside \`${vaultPath}\`.

---

## Handoff

After Builder commits, print the following block exactly:

\`\`\`
╔══════════════════════════════════════════════════════╗
║  ✅ Phase 1 complete: Architect + Builder             ║
║  Feature: <feature-slug>                             ║
║                                                      ║
║  Next: open a NEW chat and run Phase 2               ║
║  (Mapper + Lint) to update the vault.                ║
║                                                      ║
║  Copy and run in a new chat:                         ║
║                                                      ║
║    /wiki-run --continue                              ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
\`\`\`

Do not run Mapper or Lint in this context. Stop here.
`;
}

function continueCommand(tool: Tool, cfg: Config, vaultPath: string): string {
  const fm = frontmatter(tool, "wiki:run --continue", "Harness Mode — Mapper + Lint phase", "--continue [--no-block]");
  const preamble = preambleInstruction(vaultPath);
  return `${fm}${preamble}# Task: Harness Mode — Mapper + Lint

This is phase 2 of 2 in the harness loop. You are running the **Mapper** and **Lint** agents in this context.

The vault was written by the Architect + Builder in a previous context. Your job is to update the vault to reflect what was built, then hand off to the next Architect + Builder cycle.

**Do not implement any features. Read and write vault files only.**

---

## Agent: Mapper

1. Read the last entry in \`${vaultPath}/log.md\` to identify the feature just built and its commit hash.
2. Run \`git diff --name-only <builder-commit>\` in the project root to get changed source files.
3. Re-read each changed file.
4. Update \`${vaultPath}/map/structure.md\`, \`${vaultPath}/map/dependencies.md\`, \`${vaultPath}/map/entrypoints.md\`.
5. Update \`${vaultPath}/overview.md\` and \`${vaultPath}/index.md\`.
6. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] harness:mapper | <feature-slug> | commit:<git-hash>\`
7. Run \`git add . && git commit -m "wiki4llm: mapper <feature-slug>"\` inside \`${vaultPath}\`.

---

## Agent: Lint

1. Find orphan pages, stale claims, missing entity pages, broken links.
2. Fix what you can automatically (add missing links, stub missing pages).
3. Append to \`${vaultPath}/log.md\`:
   \`## [<timestamp>] harness:lint | <feature-slug> | commit:<git-hash>\`
4. Run \`git add . && git commit -m "wiki4llm: lint <feature-slug>"\` inside \`${vaultPath}\`.

---

## Mark feature complete

In \`${vaultPath}/pending/plan.md\`, find the line for the feature just built and mark it checked:
\`- [x] <feature-slug>: <description>\`

Commit: \`git add . && git commit -m "wiki4llm: complete <feature-slug>"\` inside \`${vaultPath}\`.

---

## Handoff

Check if any unchecked items remain in \`${vaultPath}/pending/plan.md\`.

**If features remain**, print:

\`\`\`
╔══════════════════════════════════════════════════════╗
║  ✅ Phase 2 complete: Mapper + Lint                  ║
║  Feature: <feature-slug> is done.                    ║
║                                                      ║
║  Next feature is ready. Open a NEW chat and run:     ║
║                                                      ║
║    /wiki-run                                         ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
\`\`\`

**If all features are complete**, print:

\`\`\`
╔══════════════════════════════════════════════════════╗
║  🎉 All features complete!                           ║
║  The vault is up to date. Run /wiki-lint to do a     ║
║  final health check, or /wiki-advise to plan next.   ║
╚══════════════════════════════════════════════════════╝
\`\`\`
`;
}

export function commandFiles(cfg: Config, vaultPath: string): Record<string, string> {
  const { tool, mode } = cfg;

  const context: Record<string, string> = {
    "wiki-map.md": mapCommand(tool, cfg, vaultPath),
    "wiki-bootstrap.md": bootstrapCommand(tool, cfg, vaultPath),
    "wiki-advise.md": adviseCommand(tool, cfg, vaultPath),
    "wiki-build.md": buildCommand(tool, cfg, vaultPath),
    "wiki-update.md": updateCommand(tool, cfg, vaultPath),
    "wiki-lint.md": lintCommand(tool, cfg, vaultPath),
  };

  const harness: Record<string, string> = {
    "wiki-run.md": runCommand(tool, cfg, vaultPath),
    "wiki-run--continue.md": continueCommand(tool, cfg, vaultPath),
  };

  return mode === "harness" ? { ...context, ...harness } : context;
}
