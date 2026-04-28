# Agents

Five CrewAI agents run in sequence. Each has a single responsibility, reads only its
vault slice, and writes only its designated output files before handing off.

All agents are defined in `harness/agents.py`.

---

## 1. Planner

**Runs once** at harness startup, before the feature loop begins.

**Role**: Reads all files in `specs/`, extracts a feature list, and writes
`pending/plan.md`. If `pending/plan.md` already exists, merges new features in without
overwriting completed ones (idempotent).

**Reads**: `specs/**/*`, `pending/plan.md` (if exists)

**Writes**:
- `pending/plan.md` — feature checklist
- `overview.md` — high-level project summary
- `raw/` — copies of all spec files

**Done when**: `pending/plan.md` is written.

---

## 2. Refiner

**Runs once per feature**, before the Architect. Skipped if `--no-refine` or
`[no-refine]` tag on the feature line.

**Role**: Generates 3 candidate implementation approaches for the current feature.
Scores each on simplicity, completeness, risk, and fit. Writes the winning approach
and runners-up to the vault. See `09-refinement.md` for full scoring details.

**Reads**: `pending/plan.md`, `overview.md`, `map/structure.md`, `map/dependencies.md`,
relevant `entities/*.md`

**Writes**: `decisions/<feature-slug>.md`

**Done when**: `decisions/<feature-slug>.md` is written and valid.

---

## 3. Architect

**Runs once per feature**, after the Refiner.

**Role**: Reads the Refiner's decision (or the feature description directly if
`--no-refine`) and produces a concrete, file-level implementation plan. Does not
write code.

**Reads**: `decisions/<feature-slug>.md` (or `pending/plan.md` if no-refine),
`map/structure.md`, `map/entrypoints.md`, relevant `entities/*.md`

**Writes**: `pending/plan-<feature-slug>.md` — step-by-step implementation plan
with files to create/modify, interfaces, edge cases, and acceptance criteria.

**Done when**: `pending/plan-<feature-slug>.md` is written.

---

## 4. Builder

**Runs once per feature**, after the Architect.

**Role**: Reads the Architect's plan and implements the feature. Writes code to the
project (outside the vault). Makes a git commit. Logs any ambiguities to
`pending/questions.md`.

**Reads**: `pending/plan-<feature-slug>.md`, `decisions/<feature-slug>.md`,
project source files as needed

**Writes**: Project source files, git commit, `pending/questions.md`

**Done when**: A git commit is made and `pending/questions.md` is updated.

---

## 5. Mapper

**Runs once per feature**, after the Builder.

**Role**: Reads the Builder's git diff, updates the vault to reflect what was built,
resolves open questions, and marks the feature complete. Also runs a vault health check.

**Reads**: `git diff HEAD~1`, `pending/questions.md`, `pending/plan.md`,
`pending/plan-<feature-slug>.md`, all vault pages referencing the feature

**Writes**: `entities/*.md`, `map/structure.md`, `map/dependencies.md`,
`map/entrypoints.md`, `index.md`, `log.md`, `pending/questions.md` (resolved),
`pending/plan.md` (feature checked off)

**Done when**: Feature is checked off in `pending/plan.md` and `log.md` is updated.

---

## Execution order

```
[once]     Planner
[per feat] Refiner → Architect → Builder → Mapper
           (repeat until pending/plan.md is fully checked off)
```

---

## `harness/agents.py`

```python
from crewai import Agent, LLM
from config import HarnessConfig

def make_agents(config: HarnessConfig) -> dict:
    def llm(name): return LLM(model=config.model_for(name))

    return {
        "planner": Agent(
            role="Project Planner",
            goal="Parse spec files and produce a complete, ordered feature checklist",
            backstory="You extract structured plans from unstructured specs.",
            llm=llm("planner"),
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "refiner": Agent(
            role="Solution Refiner",
            goal="Evaluate 3 implementation approaches and choose the best one",
            backstory="You prevent premature implementation by forcing deliberate design.",
            llm=llm("refiner"),
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "architect": Agent(
            role="Software Architect",
            goal="Produce a concrete, file-level implementation plan",
            backstory="You translate decisions into actionable engineering plans.",
            llm=llm("architect"),
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "builder": Agent(
            role="Software Builder",
            goal="Implement the feature exactly as planned and commit the changes",
            backstory="You write clean, working code that follows the plan precisely.",
            llm=llm("builder"),
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "mapper": Agent(
            role="Vault Mapper",
            goal="Update the vault to accurately reflect what was just built",
            backstory="You keep the knowledge base current so future agents start informed.",
            llm=llm("mapper"),
            allow_delegation=False,
            verbose=config.verbose,
        ),
    }
```
