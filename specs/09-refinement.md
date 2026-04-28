# Refinement

The Refiner runs before the Architect on every feature. It forces deliberate evaluation
of alternatives before any code is written, and documents the reasoning in the vault so
future agents (and humans) can understand why a particular approach was chosen.

---

## Why it matters

Without refinement, the Builder picks the first plausible approach. Suboptimal choices
compound across features. With refinement, every feature gets 3 scored candidates and a
documented rationale — the vault accumulates decisions, not just code.

---

## Refiner prompt structure

The Refiner's task description is built from four sections:

**1. Vault context** (injected from vault slice):
```
Project overview: <overview.md>
Current structure: <map/structure.md>
Current dependencies: <map/dependencies.md>
Relevant entities: <entities matching feature keywords>
```

**2. Feature**:
```
Feature to implement: <description from pending/plan.md>
```

**3. Instruction**:
```
Generate exactly 3 distinct implementation approaches for this feature.
For each approach:
- Give it a name (2–4 words)
- Describe it in 3–5 sentences
- Score it on each dimension (1–5):
    Simplicity:    ease of implementation and long-term maintenance
    Completeness:  how fully it satisfies the feature requirements
    Risk:          inverse of risk (5 = low risk, 1 = high risk)
    Fit:           consistency with existing codebase and vault context

Select the approach with the highest total score. On a tie, prefer the simpler one.
Write your output to decisions/<feature-slug>.md using the format in 07-vault-contract.md.
```

**4. Constraints**:
```
- Do not write any code
- Do not modify any file other than decisions/<feature-slug>.md
- Do not reference approaches from previous features unless directly relevant
```

---

## Scoring rubric

| Dimension | 5 | 3 | 1 |
|---|---|---|---|
| Simplicity | Fits existing patterns, minimal new abstractions | Some new patterns needed | Major refactor or new paradigm |
| Completeness | Fully satisfies all requirements | Core requirements met, edge cases deferred | Significant gaps |
| Risk | Well-understood, reversible, no new external deps | Some unknowns, moderate coupling | High coupling, irreversible, new service dependency |
| Fit | Consistent with vault entities and structure | Minor inconsistencies | Contradicts existing architecture |

---

## Skipping refinement

**Per-run**: pass `--no-refine` to `wiki4llm run`. The Architect reads the feature
description directly from `pending/plan.md`.

**Per-feature**: add `[no-refine]` to the feature line in `pending/plan.md`:
```markdown
- [ ] add-config-option: Add token expiry config option [no-refine]
```

Use `--no-refine` for trivial changes (config tweaks, small bug fixes) where the
overhead of 3 candidates isn't worth it.

---

## Output validation

Before the Architect runs, the harness validates `decisions/<slug>.md`:

1. File exists
2. Contains `## Chosen:` section
3. Frontmatter has `chosen:` set to 1, 2, or 3

If validation fails, the Refiner is re-run once. If it fails again, the error is written
to `pending/questions.md` and the feature is skipped (or the harness pauses if
`--interactive`).

---

## Example output

```markdown
---
tags: [decision]
feature: add-jwt-auth
updated: 2025-01-15T14:30:00Z
chosen: 2
---

# Decision: Add JWT Auth

## Approach 1 — Session Cookies
Store session data server-side in Redis. Client receives a session cookie. Stateful —
requires shared Redis for horizontal scaling. Simple client-side handling.
**Score**: Simplicity: 3/5 | Completeness: 4/5 | Risk: 3/5 | Fit: 2/5 | **Total: 12/20**

## Approach 2 — Stateless JWT (RS256)
Issue signed JWTs with RS256. No server-side storage. Self-contained tokens scale
horizontally without shared state. Revocation requires a denylist or short expiry.
**Score**: Simplicity: 4/5 | Completeness: 4/5 | Risk: 4/5 | Fit: 5/5 | **Total: 17/20**

## Approach 3 — OAuth2 + PKCE
Full OAuth2 authorization server. Standards-compliant and extensible. Significant
implementation overhead for an internal API — overkill for current scope.
**Score**: Simplicity: 1/5 | Completeness: 5/5 | Risk: 3/5 | Fit: 2/5 | **Total: 11/20**

## Chosen: Approach 2
**Rationale**: Highest score. Fits the existing stateless API architecture. No new
infrastructure dependencies. Short expiry mitigates the lack of revocation.

## Risks
- Immediate token revocation requires a denylist
- RS256 key rotation needs a documented process

## Open questions
- Should the public key be exposed at a JWKS endpoint for future service-to-service auth?
```
