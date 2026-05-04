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


def make_clarifier_task(agents: dict, config, specs_content: str) -> Task:
    return Task(
        description=(
            f"You are doing a one-time pre-flight review of project specs before any code is written.\n\n"
            f"Here are all the spec files:\n\n"
            f"{specs_content}\n\n"
            f"Identify ambiguities that would force a CrewAI agent to guess. Focus on:\n"
            f"- Missing behavior: edge cases the spec doesn't address\n"
            f"- Conflicting requirements: two specs that contradict each other\n"
            f"- Undefined terms: jargon or references that aren't explained\n"
            f"- Missing constraints: performance targets, auth requirements, data limits not stated\n"
            f"- Scope gaps: features implied but never described\n\n"
            f"For each ambiguity, write a single, specific question a developer could answer in one sentence.\n"
            f"Limit to the 10 most blocking questions — skip anything that can be reasonably inferred.\n\n"
            f"If the specs are unambiguous and complete, respond with exactly: NO_QUESTIONS\n\n"
            f"Otherwise respond with a numbered list only — no preamble, no markdown headers:\n"
            f"1. **[feature or file]** Question text? — Context: why this matters\n"
            f"2. ..."
        ),
        expected_output="A numbered list of up to 10 questions, or the single token NO_QUESTIONS.",
        agent=agents["clarifier"],
    )


def make_preflight_mapper_task(agents: dict, config) -> Task:
    return Task(
        description=(
            f"Walk the project codebase and build an initial vault map. "
            f"The project root is the current working directory. "
            f"The vault is at '{config.vault_path}'. "
            f"The specs directory is '{Path(config.specs_dir).resolve()}' — skip it.\n\n"
            f"1. Run `find . -type f` using run_shell_command to list all project files. "
            f"Skip hidden directories, node_modules, dist, build, __pycache__, and the vault directory.\n"
            f"2. Write map/structure.md: a directory tree with a one-line role description per file or directory.\n"
            f"3. Write map/dependencies.md: key dependencies, versions, and relationships "
            f"(read package.json, pyproject.toml, Cargo.toml, go.mod, or equivalent if present).\n"
            f"4. Write map/entrypoints.md: main entry files and their purpose.\n"
            f"5. For each major module, class, or service found, write a stub entity page to entities/<Name>.md "
            f"with a one-paragraph summary. Skip trivial files.\n"
            f"6. Write overview.md with a high-level summary of what the project is and does "
            f"(infer from the code if no README exists).\n"
            f"7. Update index.md to list every vault page written with a one-line summary.\n"
            f"8. Append an entry to log.md: pre-flight map complete."
        ),
        expected_output="map/structure.md, map/dependencies.md, map/entrypoints.md, overview.md, index.md written. Entity stubs created.",
        agent=agents["mapper"],
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
        has_web = bool(getattr(config.research, "tavily_api_key", ""))
        web_instruction = (
            f"Use web_search to gather 3-5 relevant findings. For each finding:\n"
            f"- The search query used\n"
            f"- Key insight (2-4 sentences)\n"
            f"- Relevance to this feature (1 sentence)\n"
            f"- Source URL"
        ) if has_web else (
            f"You do not have live web access. Draw on your training knowledge to surface 3-5 relevant findings. "
            f"For each finding:\n"
            f"- Topic or pattern name\n"
            f"- Key insight (2-4 sentences)\n"
            f"- Relevance to this feature (1 sentence)\n"
            f"- Confidence: High / Medium / Low (based on how current and well-established this knowledge is)"
        )
        research_task = Task(
            description=(
                f"Feature to research: {description} (slug: {slug})\n\n"
                f"{type_prompt}{sub_prompt}\n\n"
                f"Read vault context using vault_read: overview.md, map/structure.md.\n"
                f"{web_instruction}\n\n"
                f"Write output to research/{slug}.md:\n\n"
                f"---\ntags: [research]\nfeature: {slug}\ntype: {config.research.type}\n"
                f"web_access: {'true' if has_web else 'false'}\nupdated: <ISO 8601>\n---\n\n"
                f"# Research: <Feature Name>\n\n"
                f"## Findings\n\n"
                f"### 1. <Finding title>\n"
                f"{'**Source**: <URL>' if has_web else '**Confidence**: <High|Medium|Low>'}\n"
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
            f"with a single command: `cat '{Path(config.specs_dir).resolve()}'/*.md 2>/dev/null || find '{Path(config.specs_dir).resolve()}' -type f | xargs cat`. "
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
            f"Copy spec files to raw/ using run_shell_command: `cp -r '{Path(config.specs_dir).resolve()}'/* '{Path(config.vault_path).resolve()}/raw/'`."
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
            f"Next, run `cat AGENTS.md` using run_shell_command. "
            f"If the file exists, use the build, test, and lint commands listed under the ## Commands section. "
            f"If the file is absent or empty, fall back to sniffing the project type:\n\n"
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
            f"Run ALL applicable quality checks. "
            f"Collect every failure before writing the report — do not stop at the first failure.\n\n"
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
            f"Read these vault files using vault_read in sequence (one call each): "
            f"pending/questions.md, pending/plan.md, pending/plan-{slug}.md, raw/{slug}/TECH.md, index.md. "
            f"Then run `git diff HEAD~1` using run_shell_command to see what was built. "
            f"Do all reads before writing anything.\n\n"
            f"1. Update or create entity pages in entities/ for any new modules/classes/services.\n"
            f"2. Update map/structure.md, map/dependencies.md, map/entrypoints.md as needed.\n"
            f"3. Update index.md to list any new vault pages.\n"
            f"4. Append a summary entry to log.md.\n"
            f"5. Resolve open questions in pending/questions.md (replace - [ ] with - [x]).\n"
            f"6. Mark the feature complete in pending/plan.md: change `- [ ] {slug}:` to `- [x] {slug}:`.\n"
            f"7. Update raw/{slug}/TECH.md: compare the git diff against the plan. "
            f"If the implementation deviated (different files, interfaces, or approach), fill in ## Deviations with:\n"
            f"   - What changed from the plan\n"
            f"   - Why (from pending/questions.md if recorded, otherwise infer from the diff)\n"
            f"   - Updated file list or interface signatures if they changed\n"
            f"   Update the `updated` frontmatter field to the current ISO 8601 timestamp.\n"
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
