# `wiki4llm init` Command

`init` is the only setup step the user runs. It detects their LLM CLI tool, asks which
mode they want, generates the appropriate files, and scaffolds the vault.

---

## Flow

```
wiki4llm init
  1. Detect LLM CLI tool on PATH
  2. Prompt: choose mode (Context / Harness / Run)
  3. Prompt: confirm project name (default: current directory name)
  4. Generate slash-command files (Context and Harness modes only)
  5. Scaffold vault at .wiki/
  6. Write .wiki4llm.json
  7. Update .gitignore
  8. Print summary
```

---

## Step 1 — LLM CLI tool detection

Check PATH for known tools in this order:

| Tool | Detection | Generated path |
|---|---|---|
| Claude Code | `which claude` | `.claude/commands/` |
| OpenCode | `which opencode` | `.opencode/commands/` |

If neither is found, prompt the user to choose one and generate files anyway.

For Run Mode, no LLM CLI tool is needed — skip detection and skip slash-command
generation entirely.

---

## Step 2 — Mode selection prompt

```
? Which mode do you want?
  ❯ Context Mode   — slash-commands in your LLM tool; you drive the loop
    Harness Mode   — slash-commands with a two-phase loop; semi-autonomous
    Run Mode       — autonomous BAML agent loop; set it and forget it
```

---

## Step 3 — Slash-command generation (Context and Harness modes)

Generate one markdown file per command into the tool's command directory.

### Context Mode commands

| File | Slash-command |
|---|---|
| `wiki-map.md` | `/wiki-map [--ask]` |
| `wiki-bootstrap.md` | `/wiki-bootstrap` |
| `wiki-advise.md` | `/wiki-advise` |
| `wiki-build.md` | `/wiki-build [--feature "..."] [--ask]` |
| `wiki-update.md` | `/wiki-update [--ask]` |
| `wiki-lint.md` | `/wiki-lint` |

### Harness Mode commands

| File | Slash-command |
|---|---|
| `wiki-bootstrap.md` | `/wiki-bootstrap` |
| `wiki-run.md` | `/wiki-run [--no-block]` |
| `wiki-run-continue.md` | `/wiki-run --continue [--no-block]` |

### Slash-command file format

**Claude Code** (`.claude/commands/<name>.md`):

```markdown
---
description: <one-line description>
argument-hint: "<flags>"
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
---
<vault state preamble injected here>

<command prompt body>
```

**OpenCode** (`.opencode/commands/<name>.md`):

```markdown
---
description: <one-line description>
---
<vault state preamble injected here>

<command prompt body>
```

The vault state preamble is built by `buildVaultPreamble(vaultPath)` from `src/vault.ts`
and prepended to every generated command file at generation time.

See `11-slash-commands.md` for the prompt body of each command.

---

## Step 4 — Run Mode init

When Run Mode is selected:
- No slash-command files are generated
- Vault is scaffolded as normal
- `.wiki4llm.json` is written with a `crewai` block (see `10-config.md`)
- A `specs/` directory is created if it does not exist, with a `README.md`:

```markdown
# Specs

Drop your spec files here. Run `wiki4llm run` when ready.

The Planner agent will read everything in this directory and build a feature checklist.
```

- `harness/requirements.txt` is copied into the project root if not already present
- Print setup instructions:

```
wiki4llm: Run Mode initialized.

Next steps:
  1. Add spec files to specs/
  2. Install Python deps: pip install -r harness/requirements.txt
  3. Run: wiki4llm run --model ollama/qwen2.5-coder:32b
```

---

## Step 5 — `.wiki4llm.json`

Written by `saveConfig()` from `src/config.ts`. See `10-config.md` for the full schema.

---

## Step 6 — `.gitignore` update

Append to `.gitignore` (create if missing), skipping lines already present:

```
# wiki4llm
.claude/commands/
.opencode/commands/
dist/
```

The vault (`.wiki/`) is NOT gitignored.

---

## Re-running init

Re-running `wiki4llm init` on an existing project:
- Regenerates slash-command files in place (overwrites)
- Does NOT overwrite `.wiki/` vault contents
- Does NOT overwrite `.wiki4llm.json` — merges new fields only
- Allows switching modes (e.g., Context → Run)
