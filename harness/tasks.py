from crewai import Task
from pathlib import Path

_RESEARCH_TYPE_PROMPTS = {
    "ux": (
        "Focus on UI/UX trends, design patterns, component conventions, accessibility standards, "
        "and user interaction models relevant to this feature."
    ),
    "web": (
        "Focus on current web standards, browser compatibility, relevant libraries/frameworks, "
        "and recent ecosystem developments relevant to this feature."
    ),
    "accessibility": (
        "Focus on WCAG guidelines, ARIA patterns, screen reader compatibility, "
        "and inclusive design practices relevant to this feature."
    ),
    "performance": (
        "Focus on performance bottlenecks, optimization techniques, benchmarking approaches, "
        "and runtime cost tradeoffs relevant to this feature."
    ),
    "competitor": (
        "Focus on how competing products or open-source projects implement similar features: "
        "their approaches, tradeoffs, and lessons learned."
    ),
    "security": (
        "Focus on known attack vectors, OWASP guidelines, secure coding patterns, "
        "and threat models relevant to this feature."
    ),
}


def make_clarifier_task(agents: dict, config, specs_dir: str) -> Task:
    safe_dir = Path(specs_dir).resolve()
    return Task(
        description=(
            f"You are doing a one-time pre-flight pass over the project specs before any code is written.\n\n"
            f"1. Read every spec file under '{safe_dir}/' using run_shell_command "
            f"(e.g. `find '{safe_dir}' -type f` then `cat <file>` for each).\n"
            f"2. Also read raw/clarifications.md from the vault using vault_read if it exists — "
            f"it may contain answers from a previous run.\n\n"
            f"Identify ambiguities that would force a CrewAI agent to guess. Focus on:\n"
            f"- Missing behavior: what should happen in edge cases the spec doesn't address?\n"
            f"- Conflicting requirements: two specs that contradict each other\n"
            f"- Undefined terms: jargon or references that aren't explained\n"
            f"- Missing constraints: performance targets, auth requirements, data limits not stated\n"
            f"- Scope gaps: features implied but never described\n\n"
            f"For each ambiguity, write a single, specific question a developer could answer in one sentence.\n"
            f"Limit to the 10 most blocking questions — skip anything that can be reasonably inferred.\n\n"
            f"Write your findings to raw/clarifications.md in this exact format:\n\n"
            f"---\nstatus: needs-answers\nupdated: <ISO 8601>\n---\n\n"
            f"# Spec Clarifications\n\n"
            f"## Questions\n\n"
            f"1. **[spec file or feature area]** Question text?\n"
            f"   - Context: one sentence explaining why this matters\n\n"
            f"2. ...\n\n"
            f"## Answers\n\n"
            f"(to be filled in by the user)\n\n"
            f"## Enriched Notes\n\n"
            f"(to be filled in after answers are provided)\n\n"
            f"If the specs are unambiguous and complete, write raw/clarifications.md with "
            f"`status: complete` and a single line: 'No ambiguities found — specs are ready.'"
        ),
        expected_output="raw/clarifications.md written with questions or a clean bill of health.",
        agent=agents["clarifier"],
    )


def make_tasks(agents: dict, config, feature: tuple) -> dict:
    slug, description = feature

    # Build research context line used by refiner + architect
    research_context = (
        f"Read the research findings at research/{slug}.md using vault_read and incorporate them. "
        if config.research.enabled else ""
    )

    research_task = None
    if config.research.enabled:
        type_prompt = _RESEARCH_TYPE_PROMPTS.get(config.research.type, "")
        sub_prompt = f"\n\nAdditional focus: {config.research.prompt}" if config.research.prompt else ""
        research_task = Task(
            description=(
                f"Feature to research: {description} (slug: {slug})\n\n"
                f"{type_prompt}{sub_prompt}\n\n"
                f"Read vault context using vault_read: overview.md, map/structure.md.\n"
                f"Use web_search to gather 3-5 relevant findings. For each finding:\n"
                f"- Source or search query used\n"
                f"- Key insight (2-4 sentences)\n"
                f"- Relevance to this feature (1 sentence)\n\n"
                f"Write output to research/{slug}.md:\n\n"
                f"---\ntags: [research]\nfeature: {slug}\ntype: {config.research.type}\nupdated: <ISO 8601>\n---\n\n"
                f"# Research: <Feature Name>\n\n"
                f"## Findings\n\n"
                f"### 1. <Finding title>\n"
                f"**Source**: <query or URL>\n"
                f"<insight>\n"
                f"**Relevance**: <one sentence>\n\n"
                f"...\n\n"
                f"## Recommendations\n\n"
                f"- Concrete, actionable suggestions for the Refiner and Architect based on findings"
            ),
            expected_output=f"research/{slug}.md written with findings and recommendations.",
            agent=agents["research"],
        )

    planner_task = Task(
        description=(
            f"Read all files in the specs directory at '{Path(config.specs_dir).resolve()}/' using run_shell_command "
            f"(e.g. `ls '{Path(config.specs_dir).resolve()}'` then `cat '<absolute_path>/<file>'` for each). "
            f"Also read raw/clarifications.md from the vault using vault_read — incorporate any answers there "
            f"into the feature descriptions and acceptance criteria. "
            f"Read the existing plan at pending/plan.md using vault_read. "
            f"Merge the specs into a complete, ordered feature checklist without overwriting completed items. "
            f"Write the result to pending/plan.md using this format:\n\n"
            f"- [ ] slug: Feature description\n"
            f"  Acceptance criteria:\n"
            f"  1. <numbered, testable invariant — observable behavior, not implementation detail>\n"
            f"  2. ...\n\n"
            f"Each feature must have at least 2 and no more than 8 acceptance criteria. "
            f"Write criteria as user-observable invariants (what must be true, not how to implement it). "
            f"Also write overview.md with a high-level project summary. "
            f"Copy spec files to raw/ using run_shell_command."
        ),
        expected_output="pending/plan.md written with feature checklist and numbered acceptance criteria. overview.md written.",
        agent=agents["planner"],
    )

    refiner_task = Task(
        description=(
            f"Feature to evaluate: {description} (slug: {slug})\n\n"
            f"Read these vault files using vault_read: overview.md, map/structure.md, map/dependencies.md, "
            f"pending/plan.md (to review the acceptance criteria for this feature), "
            f"and any relevant files in entities/. {research_context}\n\n"
            f"Generate exactly 3 distinct implementation approaches. For each:\n"
            f"- Name (2-4 words)\n"
            f"- Description (3-5 sentences)\n"
            f"- Scores 1-5: Simplicity, Completeness, Risk (5=low risk), Fit\n\n"
            f"Select the highest total score (prefer simpler on tie). "
            f"Write output to decisions/{slug}.md:\n\n"
            f"---\ntags: [decision]\nfeature: {slug}\nupdated: <ISO 8601>\nchosen: <1|2|3>\n---\n\n"
            f"# Decision: <Feature Name>\n\n"
            f"## Approach 1 — <name>\n...\n**Score**: Simplicity: X/5 | ...\n\n"
            f"## Chosen: Approach N\n**Rationale**: ...\n\n"
            f"Do not write any code. Only write decisions/{slug}.md."
        ),
        expected_output=f"decisions/{slug}.md written with 3 scored approaches and ## Chosen: section.",
        agent=agents["refiner"],
    )

    architect_task = Task(
        description=(
            f"Feature to plan: {description} (slug: {slug})\n\n"
            f"Read these vault files using vault_read: "
            + (f"decisions/{slug}.md, " if not config.no_refine else "pending/plan.md, ")
            + f"map/structure.md, map/entrypoints.md, pending/plan.md (for acceptance criteria), "
            f"and any relevant files in entities/. {research_context}\n\n"
            f"Produce a concrete, file-level implementation plan. Do not write any code.\n\n"
            f"Write to BOTH of these locations:\n\n"
            f"1. pending/plan-{slug}.md (used by the Builder)\n"
            f"2. raw/{slug}/TECH.md (the living spec — will be updated by the Mapper if implementation deviates)\n\n"
            f"Both files must use this structure:\n\n"
            f"---\ntags: [tech-spec]\nfeature: {slug}\nupdated: <ISO 8601>\n---\n\n"
            f"# TECH: <Feature Name>\n\n"
            f"## Context\n"
            f"What's being built and how the current system works in the area being changed. "
            f"Reference the acceptance criteria from pending/plan.md by number (e.g. 'Criterion 3 requires...').\n\n"
            f"## Files to create\n- path — purpose\n\n"
            f"## Files to modify\n- path — what changes\n\n"
            f"## Interfaces\n```\nfunction signatures / API shapes\n```\n\n"
            f"## Edge cases\n- ...\n\n"
            f"## Acceptance criteria mapping\n"
            f"For each criterion from pending/plan.md, state the concrete test or verification step that proves it:\n"
            f"- Criterion 1: <how it will be verified>\n"
            f"- Criterion 2: ...\n\n"
            f"## Deviations\n"
            f"(left blank — Mapper fills this in after implementation if the build diverged from this plan)"
        ),
        expected_output=f"pending/plan-{slug}.md and raw/{slug}/TECH.md written with file-level implementation plan.",
        agent=agents["architect"],
    )

    builder_task = Task(
        description=(
            f"Feature to implement: {description} (slug: {slug})\n\n"
            f"Read these vault files using vault_read: pending/plan-{slug}.md and decisions/{slug}.md.\n\n"
            f"Implement the feature exactly as planned. Write code to the project (outside the vault). "
            f"All shell commands must be fully non-interactive (no prompts). "
            f"For scaffolding tools, pass flags that suppress prompts "
            f"(e.g. `npm create vite@latest myapp -- --template react`, `npx create-react-app myapp --yes`, "
            f"`npm init -y`, `git init --quiet`). Never run a command that waits for stdin. "
            f"Make a git commit when done using run_shell_command.\n"
            f"Log any ambiguities or deviations from the plan to pending/questions.md:\n\n"
            f"## {slug} — <ISO 8601>\n\n"
            f"- [ ] Question or decision made\n"
            f"- [ ] Deviation: <what changed from the plan and why>\n\n"
            f"If no questions or deviations, write: (no open questions)\n"
            f"You MUST make a git commit. If nothing changed, explain why in pending/questions.md."
        ),
        expected_output=f"Feature implemented, git commit made, pending/questions.md updated.",
        agent=agents["builder"],
    )

    verifier_task = Task(
        description=(
            f"Feature just built: {description} (slug: {slug})\n\n"
            f"First, read pending/plan-{slug}.md using vault_read to get the acceptance criteria mapping. "
            f"You will reference these criteria by number in your failure report.\n\n"
            f"Run ALL applicable quality checks for this project type using run_shell_command. "
            f"Collect every failure before writing the report — do not stop at the first failure.\n\n"
            f"**TypeScript / JavaScript** (package.json present):\n"
            f"  1. Type-check: `npx tsc --noEmit` (or `npm run typecheck` if that script exists)\n"
            f"  2. Lint: `npm run lint` if the script exists, else `npx eslint . --ext .ts,.tsx,.js,.jsx`\n"
            f"  3. Tests: `npm test`\n\n"
            f"**Python** (pyproject.toml / setup.cfg / pytest.ini present):\n"
            f"  1. Type-check: `python -m mypy .` if mypy is installed\n"
            f"  2. Lint: `python -m ruff check .` if ruff is installed, else `python -m flake8 .`\n"
            f"  3. Tests: `python -m pytest`\n\n"
            f"**Rust** (Cargo.toml present):\n"
            f"  1. Type-check + lint: `cargo clippy -- -D warnings`\n"
            f"  2. Tests: `cargo test`\n\n"
            f"**Go** (go.mod present):\n"
            f"  1. Vet: `go vet ./...`\n"
            f"  2. Tests: `go test ./...`\n\n"
            f"**Fallback** (none of the above): check for a Makefile and run `make test` or `make check`.\n\n"
            f"After running all checks:\n"
            f"- If every check passed, write a single line to pending/verify-{slug}.md: PASSED and stop.\n"
            f"- If any check failed, write a structured failure report to pending/verify-{slug}.md:\n\n"
            f"---\nstatus: FAILED\nfeature: {slug}\n---\n\n"
            f"## Failures\n\n"
            f"For each failure (group by check type: typecheck / lint / test):\n"
            f"- Check type and command run\n"
            f"- Error or test name\n"
            f"- Error message (trimmed)\n"
            f"- Likely cause (1 sentence)\n"
            f"- **Criterion impact**: which acceptance criterion from pending/plan-{slug}.md this failure affects "
            f"(e.g. 'Criterion 2 — user sees error on empty input — UNMET'). "
            f"Write 'No criterion mapped' if the failure is a build/lint issue unrelated to behavior.\n\n"
            f"## Fix hints\n\n"
            f"- Concrete, file-level suggestions for the Builder to address each failure\n\n"
            f"Also append the failure summary to pending/questions.md under:\n"
            f"## {slug} — verify-fail — <ISO 8601>\n"
            f"so the Builder can read it on retry."
        ),
        expected_output=f"pending/verify-{slug}.md written with PASSED or structured failure report.",
        agent=agents["verifier"],
    )

    mapper_task = Task(
        description=(
            f"Feature just built: {description} (slug: {slug})\n\n"
            f"Read these vault files using vault_read: pending/questions.md, pending/plan.md, "
            f"pending/plan-{slug}.md, raw/{slug}/TECH.md, index.md.\n\n"
            f"1. Run `git diff HEAD~1` using run_shell_command to see what was built.\n"
            f"2. Update or create entity pages in entities/ for any new modules/classes/services.\n"
            f"3. Update map/structure.md, map/dependencies.md, map/entrypoints.md as needed.\n"
            f"4. Update index.md to list any new vault pages.\n"
            f"5. Append a summary entry to log.md.\n"
            f"6. Resolve open questions in pending/questions.md (replace - [ ] with - [x]).\n"
            f"7. Mark the feature complete in pending/plan.md: change `- [ ] {slug}:` to `- [x] {slug}:`.\n"
            f"8. **Update raw/{slug}/TECH.md**: compare the git diff against the plan in raw/{slug}/TECH.md. "
            f"If the implementation deviated from the plan (different files touched, different interfaces, "
            f"different approach), fill in the ## Deviations section with:\n"
            f"   - What changed from the plan\n"
            f"   - Why (from pending/questions.md if recorded, otherwise infer from the diff)\n"
            f"   - Updated file list or interface signatures if they changed\n"
            f"   Also update the `updated` frontmatter field to the current ISO 8601 timestamp.\n"
            f"   If the implementation matched the plan exactly, write: 'Implementation matched plan — no deviations.'\n\n"
            f"Vault health checks (write [HEALTH] warnings to log.md if any fail, do not block):\n"
            f"- Every page in index.md exists on disk\n"
            f"- log.md has an entry for {slug}\n"
            f"- {slug} is checked off in pending/plan.md\n"
            f"- raw/{slug}/TECH.md has a non-empty ## Deviations section"
        ),
        expected_output=f"Vault updated, raw/{slug}/TECH.md deviations filled, feature {slug} checked off in pending/plan.md, log.md appended.",
        agent=agents["mapper"],
    )

    tasks = {
        "planner": planner_task,
        "refiner": refiner_task,
        "architect": architect_task,
        "builder": builder_task,
        "verifier": verifier_task,
        "mapper": mapper_task,
    }
    if research_task:
        tasks["research"] = research_task
    return tasks
