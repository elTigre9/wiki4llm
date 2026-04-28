# Vault Handoff Contract

Each agent has a strict read/write contract. Agents must not read files outside their
contract (keeps context lean) and must not write files outside their contract (prevents
clobbering).

---

## Planner

| | Files |
|---|---|
| Reads | `specs/**/*`, `pending/plan.md` (if exists) |
| Writes | `pending/plan.md`, `overview.md`, `raw/**` |

**`pending/plan.md` format**:
```markdown
# Feature Plan

- [ ] add-jwt-auth: Add JWT authentication to the API
- [ ] user-dashboard: Build the user dashboard page
- [x] project-scaffold: Initial project structure (completed)
```

The `slug:` prefix on each line is required — it links the feature to its vault files.

---

## Refiner

| | Files |
|---|---|
| Reads | `pending/plan.md`, `overview.md`, `map/structure.md`, `map/dependencies.md`, relevant `entities/*.md` |
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
**Score**: Simplicity: 4/5 | Completeness: 3/5 | Risk: 4/5 | Fit: 5/5 | **Total: 16/20**

## Approach 2 — <name>
<description>
**Score**: Simplicity: 3/5 | Completeness: 5/5 | Risk: 4/5 | Fit: 5/5 | **Total: 17/20**

## Approach 3 — <name>
<description>
**Score**: Simplicity: 2/5 | Completeness: 5/5 | Risk: 3/5 | Fit: 3/5 | **Total: 13/20**

## Chosen: Approach 2
**Rationale**: <why>

## Risks
- <risk>

## Open questions
- <question>
```

---

## Architect

| | Files |
|---|---|
| Reads | `decisions/<slug>.md` (or `pending/plan.md` if `--no-refine`), `map/structure.md`, `map/entrypoints.md`, relevant `entities/*.md` |
| Writes | `pending/plan-<slug>.md` |

**`pending/plan-<slug>.md` format**:
```markdown
---
tags: [pending]
feature: <slug>
updated: <ISO 8601>
---

# Implementation Plan: <Feature Name>

## Files to create
- `src/auth/jwt.ts` — JWT signing and verification

## Files to modify
- `src/server.ts` — register auth middleware

## Interfaces
\`\`\`typescript
function signToken(payload: TokenPayload): string
function verifyToken(token: string): TokenPayload | null
\`\`\`

## Edge cases
- Expired token → 401
- Missing header → 401

## Acceptance criteria
- [ ] POST /auth/token returns a signed JWT
- [ ] Protected routes reject invalid tokens
```

---

## Builder

| | Files |
|---|---|
| Reads | `pending/plan-<slug>.md`, `decisions/<slug>.md`, project source files |
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

---

## Mapper

| | Files |
|---|---|
| Reads | `git diff HEAD~1`, `pending/questions.md`, `pending/plan.md`, `pending/plan-<slug>.md`, vault pages referencing the feature |
| Writes | `entities/*.md`, `map/structure.md`, `map/dependencies.md`, `map/entrypoints.md`, `index.md`, `log.md`, `pending/questions.md` (resolved), `pending/plan.md` (checked off) |

The Mapper is the **only** agent that checks off items in `pending/plan.md`.

---

## Vault health rules (enforced by Mapper after every run)

1. Every page listed in `index.md` exists on disk
2. Every `[[wikilink]]` resolves to an existing vault page
3. `log.md` has an entry for the current feature
4. The current feature is checked off in `pending/plan.md`
5. `pending/questions.md` has no unresolved `- [ ]` items from prior features

Failures write a `[HEALTH]` warning to `log.md` but do not block the loop.
