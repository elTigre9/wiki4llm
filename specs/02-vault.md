# Vault

The vault is a directory of plain markdown files at `.wiki/` inside the project root
(or at `~/.wiki4llm/vaults/<project-name>/` if `vault.external: true`).

---

## Directory structure

```
.wiki/
  index.md              # catalog of all pages + one-line summaries
  log.md                # append-only operation log
  overview.md           # high-level project summary
  raw/                  # unedited copies of spec files
    assets/             # images, PDFs, media
  map/
    structure.md        # directory tree + file roles
    dependencies.md     # key deps, versions, relationships
    entrypoints.md      # main entry files and their purpose
  entities/
    <ComponentName>.md  # one page per major module/class/service
  decisions/
    <slug>.md           # ADR-style pages written by the Refiner
  pending/
    plan.md             # feature checklist (Run Mode)
    plan-<slug>.md      # per-feature implementation plan (Architect output)
    questions.md        # grey area queue (Builder output)
```

---

## Page frontmatter

Every vault page written by an agent must include:

```yaml
---
tags: [entity]          # one of: entity, map, decision, overview, pending, log
updated: <ISO 8601>
---
```

---

## `src/vault.ts` — scaffold and preamble

### scaffoldVault(vaultPath, projectName)

Creates the vault directory structure if it does not exist:

```
.wiki/
  index.md      (empty catalog header)
  log.md        (empty log header)
  raw/
  map/
  entities/
  decisions/
  pending/
```

If `vault.git: true`, runs `git init` inside the vault directory.

### buildVaultPreamble(vaultPath): string

Returns a markdown block injected at the top of every slash-command prompt. Built from:

1. Last 5 lines of `log.md`
2. All `- [[Page]]: summary` lines from `index.md` (capped at 40)
3. Output of `git diff --stat HEAD` run inside the vault directory

Format:

```
<!-- VAULT STATE PREAMBLE -->
## Current Vault State

### Recent log entries (last 5)
<log tail>

### Index snapshot
<index lines>

### Uncommitted changes since last vault commit
<git diff --stat>
<!-- END VAULT STATE PREAMBLE -->
```

If git is not available or the vault has no commits yet, the diff section reads
`(git not available or no commits yet)`.

---

## Vault location

- **Default**: `.wiki/` co-located inside the project root
- **External** (`vault.external: true`): `~/.wiki4llm/vaults/<project-name>/`

The external option is useful when multiple projects share a vault, or when the project
directory is ephemeral (e.g., a Docker container).
