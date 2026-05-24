# Vault Handoff Contract

Each agent has a strict read/write contract. Agents must not read files outside their
contract (keeps context lean) and must not write files outside their contract (prevents
clobbering).

---

## Clarifier

| | Files |
|---|---|
| Reads | `specs/**/*` |
| Writes | `raw/clarifications.md` |

**`raw/clarifications.md` format**:

```markdown
---
status: needs-answers
updated: <ISO 8601>
---

# Spec Clarifications

## Questions

1. [feature-slug] Question text — context

## Answers

(to be filled in by the user)
```

If no ambiguities are found:

```markdown
---
status: complete
updated: <ISO 8601>
---

No ambiguities found — specs are ready.
```

The Clarifier is a single-shot BAML agent. It reads all spec files and outputs a
`ClarifierOutput` struct with `has_ambiguities: bool` and optional `questions[]`.

---

## Planner

| | Files |
|---|---|
| Reads | `specs/**/*`, `pending/plan.md` (if exists), `raw/clarifications.md` |
| Writes | `pending/plan.md`, `overview.md`, `raw/**` |

**`pending/plan.md` format**:
```markdown
# Feature Plan

- [ ] add-jwt-auth: Add JWT authentication to the API
- [ ] user-dashboard: Build the user dashboard page
- [x] project-scaffold: Initial project structure (completed)
```

The `slug:` prefix on each line is required — it links the feature to its vault files.

The Planner is a single-shot BAML agent. It receives specs content, clarifications,
and the existing plan (if any) and returns a `FeaturePlan` struct.

---

## Research

| | Files |
|---|---|
| Reads | `overview.md`, `map/structure.md`, `pending/plan.md` (feature entry) |
| Writes | `research/<slug>.md` |

**`research/<slug>.md` format**:
```markdown
---
tags: [research]
feature: <slug>
type: web | local | codebase
updated: <ISO 8601>
---

# Research: <Feature Name>

## Findings

### 1. Finding title
**Source**: <URL> | **Confidence**: <high | medium | low>
<insight>

**Relevance**: <why this matters>

## Recommendations

- <recommendation>
```

Research is a single-shot BAML agent. It runs only when `research.enabled` is `true`
and `research/<slug>.md` does not exist.

---

## Refiner

| | Files |
|---|---|
| Reads | `pending/plan.md`, `overview.md`, `map/structure.md`, `map/dependencies.md`, relevant `entities/*.md`, `research/<slug>.md` (if exists) |
| Writes | `decisions/<slug>.md` |

**`decisions/<slug>.md` format**:
```markdown
---
tags: [decision]
feature: <slug>
updated: <ISO 8601>
chosen: 2
---

# Decision: <Feature Name>

## Approach 1 — <name>
<description>
**Score**: Simplicity: 4/5 | Completeness: 3/5 | Risk: 4/5 | Fit: 5/5

## Approach 2 — <name>
<description>
**Score**: Simplicity: 3/5 | Completeness: 5/5 | Risk: 4/5 | Fit: 5/5

## Approach 3 — <name>
<description>
**Score**: Simplicity: 2/5 | Completeness: 5/5 | Risk: 3/5 | Fit: 3/5

## Chosen: Approach 2
**Rationale**: <why>

## Risks
- <risk>

## Open questions
- <question>
```

The Refiner is a single-shot BAML agent. It receives vault context (overview,
structure, dependencies, acceptance criteria, optional research findings) and
returns a `Decision` struct.

---

## Architect

| | Files |
|---|---|
| Reads | `decisions/<slug>.md` (or `pending/plan.md` if `--no-refine`), `map/structure.md`, `map/entrypoints.md`, relevant `entities/*.md`, `research/<slug>.md` (if exists) |
| Writes | `pending/plan-<slug>.md`, `raw/<slug>/TECH.md` |

**`pending/plan-<slug>.md` format**:
```markdown
---
tags: [tech-spec]
feature: <slug>
updated: <ISO 8601>
---

# TECH: <slug>

## Context
<project context>

## Files to create
- `src/auth/jwt.ts` — JWT signing and verification

## Files to modify
- `src/server.ts` — register auth middleware

## Interfaces
```
function signToken(payload: TokenPayload): string
function verifyToken(token: string): TokenPayload | null
```

## Edge cases
- Expired token -> 401
- Missing header -> 401

## Acceptance criteria mapping
- Criterion 1: Unit test for signToken round-trip
- Criterion 2: Integration test for protected route rejection

## Deviations
(left blank — Mapper fills this in after implementation)
```

`raw/<slug>/TECH.md` receives an identical copy. The Architect is a single-shot BAML
agent.

---

## Builder

| | Files |
|---|---|
| Reads | `pending/plan-<slug>.md`, `raw/<slug>/TECH.md`, `decisions/<slug>.md`, project source files |
| Writes | Project source files (outside vault), git commit, `pending/questions.md` |

**`pending/questions.md` format** (append-only):
```markdown
## add-jwt-auth — 2025-01-15T14:33:00Z

- [ ] Should token expiry default to 1h or 24h? (Builder defaulted to 1h)
- [ ] Refresh token endpoint needed? (Builder skipped for now)
```

If no questions:
```markdown
## add-jwt-auth — 2025-01-15T14:33:00Z
(no open questions)
```

The Builder **must** make a git commit. If nothing changed, it writes a note to
`pending/questions.md` explaining why and the Mapper marks the feature complete anyway.

The Builder is a **tool-call loop** BAML agent. Its BAML function returns
`BuilderToolCall | BuilderFinal`. The Python loop dispatches tool calls (file reads,
shell commands, file writes) and feeds results back via the `history` input until a
`BuilderReport` is returned.

---

## Verifier

| | Files |
|---|---|
| Reads | `pending/plan-<slug>.md`, `raw/<slug>/TECH.md`, project source files |
| Writes | `pending/verify-<slug>.md`, `pending/questions.md` (append) |

**`pending/verify-<slug>.md` format**:

On pass:
```
PASSED
```

On failure:
```markdown
---
status: FAILED
feature: <slug>
---

## Failures

- **unit** — `pytest tests/test_auth.py`
  - Error: <stderr>
  - Cause: <likely cause>
  - Criterion: 1

## Fix hints

- <suggestion>
```

The Verifier is a **tool-call loop** BAML agent. Its BAML function returns
`VerifierToolCall | VerifierFinal`. It dispatches test/lint/typecheck commands via
the tool loop and returns a `VerifierReport` with `status: PASSED | FAILED`,
failures, and fix hints.

In prototype mode, the Verifier short-circuits when `git diff HEAD~1` shows only
documentation or config changes (no source-code file modifications). See the
[06-loop.md Prototyping mode](06-loop.md#prototyping-mode-projectmaturity-prototype)
section.

---

## Mapper (pre-flight)

| | Files |
|---|---|
| Reads | File listing (`find . -type f`), package manifests (`package.json`, `pyproject.toml`, etc.) |
| Writes | `map/structure.md`, `map/entrypoints.md`, `map/dependencies.md`, `entities/*.md`, `index.md`, `log.md` |

The pre-flight Mapper runs once before the first feature loop if the vault has no
`map/structure.md` and source files exist. It is a single-shot BAML agent returning
a `MapperReport`.

---

## Mapper (per-feature, stable mode)

| | Files |
|---|---|
| Reads | `git diff HEAD~1`, `pending/questions.md`, `pending/plan.md`, `pending/plan-<slug>.md`, `raw/<slug>/TECH.md`, vault pages referencing the feature |
| Writes | `entities/*.md`, `map/structure.md`, `map/dependencies.md`, `map/entrypoints.md`, `index.md`, `log.md`, `pending/questions.md` (resolved), `pending/plan.md` (checked off) |

The Mapper is the **only** agent that checks off items in `pending/plan.md`.

The per-feature Mapper is a **tool-call loop** BAML agent. In prototype mode, this
per-feature call is replaced by an inline Python check-off (no LLM) and the full
Mapper sync runs once at end of run (see below).

---

## Mapper (end-of-run, prototype mode only)

| | Files |
|---|---|
| Reads | Combined git diff for all features, all `raw/<slug>/TECH.md` snippets, `index.md` |
| Writes | Same as per-feature Mapper: entities, structure, dependencies, entrypoints, index, log |

In prototype mode, `_inline_mapper_checkoff` marks each feature complete immediately
(no LLM call). After all features are done, `_end_of_run_mapper` calls the BAML Mapper
once with all diffs, plans, and the index batched together. This is a tool-call loop
BAML agent returning a `MapperReport`.

---

## Vault health rules (enforced by Mapper after every run)

1. Every page listed in `index.md` exists on disk
2. Every `[[wikilink]]` resolves to an existing vault page
3. `log.md` has an entry for the current feature
4. The current feature is checked off in `pending/plan.md`
5. `pending/questions.md` has no unresolved `- [ ]` items from prior features

Failures write a `[HEALTH]` warning to `log.md` but do not block the loop.
