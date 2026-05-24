# Agents

Eight BAML agents run in sequence. Each has a single responsibility, reads only its
vault slice, and writes only its designated output files before handing off.

All agents are defined as BAML functions in `harness/baml_src/agents.baml` with typed
input/output schemas (Pydantic models). The Python tool-call loop is in
`harness/baml_agents.py` and orchestration in `harness/baml_loop.py`.

---

## 1. Pre-flight Mapper

**Runs once** at harness startup, before any other agent, if the vault is unmapped and
source files exist. Skipped with `--dry-run`, `--force-remap`, or if the vault is
already mapped.

**Role**: Walks the existing project codebase and builds an initial vault map. Reads a
file listing of the project plus any manifest files (package.json, pyproject.toml,
Cargo.toml, go.mod) to identify modules, classes, services, and their structure.

**BAML function**: `PreflightMap` in `agents.baml`

**Input**: `file_listing: string`, `manifest_files: string`, `history: string`

**Output type**: `MapperReport` with `entities_updated: string[]`, `log_entry: string`,
`deviations_summary: string` (always `"Implementation matched plan — no deviations."`)

**Reads**: project file listing (`find . -type f`), manifest files

**Writes**: vault entities (via the Python harness, based on `MapperReport` fields)

**Idempotency check**: Skipped if `map/structure.md` exists in the vault.

**Done when**: Pre-flight `MapperReport` received and log entry written.

---

## 2. Clarifier

**Runs once** before the Planner, after the Pre-flight Mapper. Skipped if
`raw/clarifications.md` already has `status: complete` or `status: answered`, or with
`--skip-clarify`.

**Role**: Reads all spec files and identifies ambiguities that would force an agent to
guess. Focuses on missing behavior, conflicting requirements, undefined terms, missing
constraints, and scope gaps. If ambiguities are found, writes questions to
`raw/clarifications.md` and pauses for user answers. If specs are unambiguous, writes a
clean "no ambiguities" document and proceeds.

**BAML function**: `ClarifySpecs` in `agents.baml`

**Input**: `specs_content: string` (all spec file contents concatenated)

**Output type**: `ClarifierOutput` with `has_ambiguities: bool`, `questions:
ClarifierQuestion[]` (each has `feature: string`, `question: string`, `context: string`)

**Reads**: `specs/**/*`

**Writes**: `raw/clarifications.md` (via Python harness)

**Idempotency check**: Skipped if `raw/clarifications.md` exists and has `status:
complete` (or `status: answered`).

**Done when**: `raw/clarifications.md` is written with `status: complete`.

---

## 3. Planner

**Runs once** at harness startup, before the feature loop begins.

**Role**: Reads all files in `specs/` plus user clarifications, extracts a feature list,
and writes `pending/plan.md`. If `pending/plan.md` already exists, merges new features
in without overwriting completed ones (idempotent).

**BAML function**: `PlanFeatures` in `agents.baml`

**Input**: `specs_content: string`, `clarifications: string`, `existing_plan: string`

**Output type**: `FeaturePlan` with `features: Feature[]` (each `Feature` has `slug:
string`, `description: string`, `acceptance_criteria: string[]`)

**Reads**: `specs/**/*`, `raw/clarifications.md`, `pending/plan.md` (if exists)

**Writes**:
- `pending/plan.md` — feature checklist
- `overview.md` — high-level project summary
- `raw/` — copies of all spec files

**Idempotency check**: Skipped if `pending/plan.md` exists and already contains
at least one `- [ ]` or `- [x]` feature line.

**Done when**: `pending/plan.md` is written.

---

## 4. Research

**Runs once per feature** (optional). Controlled by `config.research.enabled`. Skipped if
research already exists for the slug.

**Role**: Gathers implementation findings about current trends, patterns, and best
practices relevant to the feature. Draws on training knowledge to surface 3–5 relevant
findings with confidence levels and actionable recommendations for the Refiner and
Architect.

**BAML function**: `ResearchFeature` in `agents.baml`

**Input**: `feature_name: string`, `slug: string`, `research_type: string`, `sub_prompt:
string?`, `vault_overview: string`, `vault_structure: string`

**Output type**: `ResearchFindings` with `findings: ResearchFinding[]` (each has `title:
string`, `insight: string`, `relevance: string`, `confidence: string`, `source_url:
string?`) and `recommendations: string[]`

**Reads**: `overview.md`, `map/structure.md`

**Writes**: `research/<slug>.md` (via Python harness)

**Idempotency check**: Skipped if `research/<slug>.md` exists.

**Done when**: `research/<slug>.md` is written.

---

## 5. Refiner

**Runs once per feature**, before the Architect. Skipped if `--no-refine` or
`[no-refine]` tag on the feature line, or if `decisions/<slug>.md` already exists and
is valid.

**Role**: Generates 3 candidate implementation approaches for the current feature.
Scores each on simplicity, completeness, risk, and fit. Writes the winning approach
and runners-up to the vault. See `09-refinement.md` for full scoring details.

**BAML function**: `RefineApproaches` in `agents.baml`

**Input**: `feature_name: string`, `slug: string`, `vault_overview: string`,
`vault_structure: string`, `vault_deps: string`, `acceptance_criteria: string`,
`research_findings: string?`

**Output type**: `Decision` with `approaches: Approach[]` (exactly 3, each has `name:
string`, `description: string`, `simplicity: int`, `completeness: int`, `risk: int`,
`fit: int`), `chosen: int` (1–3), `rationale: string`

**Reads**: `pending/plan.md`, `overview.md`, `map/structure.md`, `map/dependencies.md`,
`research/<slug>.md` (if exists), relevant `entities/*.md`

**Writes**: `decisions/<slug>.md` (via Python harness)

**Idempotency check**: Skipped if `decisions/<slug>.md` exists and is valid (contains
`## Chosen:` section and frontmatter `chosen:` in {1,2,3}).

**Done when**: `decisions/<slug>.md` is written and valid.

---

## 6. Architect

**Runs once per feature**, after the Refiner.

**Role**: Reads the Refiner's decision (or the feature description directly if
`--no-refine`) and produces a concrete, file-level implementation plan. Does not
write code.

**BAML function**: `ArchitectFeature` in `agents.baml`

**Input**: `feature_name: string`, `slug: string`, `vault_structure: string`,
`vault_entrypoints: string`, `acceptance_criteria: string`, `decision_text: string?`,
`research_findings: string?`

**Output type**: `TechPlan` with `context: string`, `files_to_create: FileSpec[]`,
`files_to_modify: FileSpec[]`, `interfaces: string`, `edge_cases: string[]`,
`criteria_mapping: CriterionMap[]` (each maps `criterion_number: int` to `verification:
string`)

**Reads**: `decisions/<slug>.md` (or `pending/plan.md` if no-refine),
`map/structure.md`, `map/entrypoints.md`, `research/<slug>.md` (if exists), relevant
`entities/*.md`

**Writes**: `pending/plan-<slug>.md` and `raw/<slug>/TECH.md` (via Python harness)

**Idempotency check**: Skipped if `pending/plan-<slug>.md` exists.

**Done when**: `pending/plan-<slug>.md` is written.

---

## 7. Builder

**Runs once per feature**, after the Architect. Tool-using agent — runs a multi-turn
tool-call loop via the Python harness.

**Role**: Reads the Architect's TechPlan and implements the feature. Writes code to the
project (outside the vault). Makes a git commit. Logs any ambiguities or deviations to a
`BuilderReport`. Uses tools: `vault_read`, `vault_write`, `run_shell_command`.

**BAML function**: `BuildFeature` in `agents.baml`

**Input**: `tech_plan: string`, `decision_text: string?`, `slug: string`,
`feature_description: string`, `history: string`

**Output type**: `BuilderStep` (BAML union of `BuilderToolCall | BuilderFinal`). The
Python tool-call loop dispatches `BuilderToolCall` until a `BuilderFinal` is received.
`BuilderReport` (the inner type) has `commit_made: bool`, `open_questions: string[]`,
`deviations: string[]`.

**Reads**: `pending/plan-<slug>.md`, `decisions/<slug>.md`, project source files
(via `vault_read` tool)

**Writes**: Project source files (via `run_shell_command`), git commit,
`pending/questions.md` (via Python harness from `BuilderReport`)

**Idempotency check**: Skipped if `pending/questions.md` already has an entry for
`<slug>`.

**Done when**: A git commit is made and `pending/questions.md` is updated.

---

## 8. Verifier

**Runs once per feature**, after the Builder (unless `--no-verify`). Tool-using agent.
In prototype mode, skipped if the git diff contains only docs/config changes.

**Role**: Runs type-check, lint, and test commands against the built feature. Reads the
TechPlan to understand acceptance criteria mapping. Returns a `VerifierReport` with
pass/fail status, structured failures, and fix hints. On failure, the Builder is re-run
(up to `verifier_retries` times). Uses tools: `vault_read`, `run_shell_command`.

**BAML function**: `VerifyBuild` in `agents.baml`

**Input**: `tech_plan: string`, `slug: string`, `history: string`

**Output type**: `VerifierStep` (BAML union of `VerifierToolCall | VerifierFinal`).
`VerifierReport` (inner type) has `status: string` (`"PASSED"` or `"FAILED"`),
`failures: Failure[]` (each has `check_type: string`, `command: string`,
`error_message: string`, `likely_cause: string`, `criterion_impact: string`),
`fix_hints: string[]`.

**Reads**: `pending/plan-<slug>.md`, `raw/<slug>/TECH.md` (for acceptance criteria
mapping), AGENTS.md (for project-specific commands)

**Writes**: `pending/verify-<slug>.md`, `pending/questions.md` (via Python harness)

**Idempotency check**: Skipped if `pending/verify-<slug>.md` exists with `"PASSED"`.

**Done when**: `pending/verify-<slug>.md` is written with `PASSED`, or retries
exhausted.

---

## 9. Mapper

**Runs once per feature**, after the Verifier. Tool-using agent. In stable mode: runs
per-feature. In prototype mode: runs inline lightweight checkoff per feature, then a
single batched pass at end of run.

**Role**: Reads the Builder's git diff and TechPlan, updates the vault to reflect what
was built, resolves open questions, and marks the feature complete. Also runs vault
health checks. Uses tools: `vault_read`, `vault_write`, `run_shell_command`.

**BAML function**: `MapAndIndex` in `agents.baml`

**Input**: `git_diff: string`, `slug: string`, `feature_description: string`,
`plan_text: string`, `tech_plan: string`, `index_text: string`, `history: string`

**Output type**: `MapperStep` (BAML union of `MapperToolCall | MapperFinal`).
`MapperReport` (inner type) has `entities_updated: string[]`, `log_entry: string`,
`deviations_summary: string`.

**Reads**: `git diff HEAD~1`, `pending/questions.md`, `pending/plan.md`,
`pending/plan-<slug>.md`, `raw/<slug>/TECH.md`, `index.md`, all vault pages
referencing the feature

**Writes**: `entities/*.md`, `map/structure.md`, `map/dependencies.md`,
`map/entrypoints.md`, `index.md`, `log.md`, `pending/questions.md` (resolved),
`pending/plan.md` (feature checked off)

**Idempotency check**: Skipped if feature is already checked off in `pending/plan.md`
(`- [x] <slug>:`).

**Done when**: Feature is checked off in `pending/plan.md` and `log.md` is updated.

---

## Execution order

```
[once]      Pre-flight Mapper → Clarifier → Planner
[per feat]  Research → Refiner → Architect → Builder → Verifier → Builder (retry) → Mapper
            (repeat until pending/plan.md is fully checked off)
[end-of-run] Batched Mapper (prototype mode only)
```

---

## Tool-call loop

Tool-using agents (Builder, Verifier, Mapper) use a BAML union return type
(`BuilderStep`, `VerifierStep`, `MapperStep`) that is either a `ToolCall` or a `Final`
report variant. The Python harness in `harness/baml_agents.py` runs a loop:

```python
for iteration in range(MAX_TOOL_ITERS):
    result = baml_fn(..., history=tool_history(entries))
    if is_tool_call(result):
        tool_result = dispatcher.dispatch(result.tool_name, result.args)
        entries.append({"tool": ..., "result": tool_result})
    else:
        return result.report
```

Non-tool agents (Clarifier, Planner, Research, Refiner, Architect, Pre-flight Mapper)
return their final structured output in a single BAML call — no loop needed.

---

## Model routing

Each agent's model is resolved in `harness/baml_agents.py` via `_client_for_agent()`,
which maps `config.model_for(agent)` to BAML client names defined in
`harness/baml_src/clients.baml`:

| Model string | BAML client |
|---|---|
| Contains `claude`, `sonnet`, or `opus` | `AnthropicSonnet` |
| Contains `ollama`, `qwen`, `minimax`, or `glm` | `OllamaLocal` |
| Everything else | `Default` |

Per-agent model overrides are configured in `.wiki4llm.json` under
`crewai.model.agents.<name>` (config key preserved for backward compatibility).
