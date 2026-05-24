// =============================================================================
// Type schemas for all agent outputs.
// These replace the regex-based text parsing in harness/loop.py.
// =============================================================================

class ClarifierQuestion {
    feature string @description("Feature or file the question targets")
    question string @description("Single-sentence question")
    context string @description("Why this matters — 1-2 sentences")
}

class ClarifierOutput {
    has_ambiguities bool
    questions ClarifierQuestion[] @description("Up to 10 blocking questions")
}

// =============================================================================

class Feature {
    slug string @description("kebab-case, alphanumerics and hyphens only, max 40 chars")
    description string @description("One-line feature summary")
    acceptance_criteria string[] @description("2-8 user-observable invariants")
}

class FeaturePlan {
    features Feature[]
}

// =============================================================================

class Approach {
    name string @description("2-4 word approach name")
    description string @description("3-5 sentence explanation")
    simplicity int @description("1-5")
    completeness int @description("1-5")
    risk int @description("1-5, 5=lowest risk")
    fit int @description("1-5")
}

class Decision {
    approaches Approach[] @description("Exactly 3 distinct approaches")
    chosen int @description("1, 2, or 3 — highest total score, prefer simpler on tie")
    rationale string @description("Why this approach was chosen")
}

// =============================================================================

class FileSpec {
    path string
    purpose string
}

class CriterionMap {
    criterion_number int
    verification string @description("Concrete test or verification step")
}

class TechPlan {
    context string @description("What's being built and current system context")
    files_to_create FileSpec[]
    files_to_modify FileSpec[]
    interfaces string @description("Function signatures / API shapes / type definitions")
    edge_cases string[]
    criteria_mapping CriterionMap[]
}

// =============================================================================

class Failure {
    check_type string @description("typecheck | lint | test")
    command string @description("The command that was run")
    error_message string @description("Trimmed error output")
    likely_cause string @description("One-sentence diagnosis")
    criterion_impact string @description("Which criterion this affects, or 'No criterion mapped'")
}

class VerifierReport {
    status string @description("PASSED or FAILED")
    failures Failure[]
    fix_hints string[] @description("Concrete file-level suggestions")
}

// =============================================================================

class BuilderReport {
    commit_made bool
    open_questions string[] @description("Ambiguities that surfaced during implementation")
    deviations string[] @description("What changed from the plan and why")
}

class BuilderQuestionsEntry {
    slug string
    timestamp string @description("ISO 8601")
    questions string[] @description("Markdown list items with - [ ] prefix")
}

// =============================================================================

class MapperReport {
    entities_updated string[]
    log_entry string @description("One-sentence summary for log.md")
    deviations_summary string @description("Deviations section text for TECH.md, or 'Implementation matched plan — no deviations.'")
}

// =============================================================================
// Tool-call types for BAML tool loops (builder, verifier, mapper, preflight).
// Each tool-using agent returns ToolCall | FinalReport (BAML union).
// The Python loop dispatches ToolCall until it gets a FinalReport.
// =============================================================================

class ToolCall {
    tool_name string @description("vault_read | vault_write | run_shell_command | web_search")
    args map<string, string>
}

// =============================================================================
// =============================================================================
// BAML Functions — one per agent.
// Prompt content mirrors harness/tasks.py. Vault-read instructions are REMOVED
// because context is pre-loaded in Python and passed as an input parameter.
// =============================================================================
// =============================================================================

// --- Clarifier ---

function ClarifySpecs(specs_content: string) -> ClarifierOutput {
    client Default
    prompt #"
        You are doing a one-time pre-flight review of project specs before any code is written.

        Here are all the spec files:

        {{ specs_content }}

        Identify ambiguities that would force an AI agent to guess. Focus on:
        - Missing behavior: edge cases the specs don't address
        - Conflicting requirements: two specs that contradict each other
        - Undefined terms: jargon or references that aren't explained
        - Missing constraints: performance targets, auth requirements, data limits not stated
        - Scope gaps: features implied but never described

        For each ambiguity, write a single, specific question a developer could answer in one sentence.
        Limit to the 10 most blocking questions — skip anything that can be reasonably inferred.

        If the specs are unambiguous and complete, set has_ambiguities = false and questions = [].
        Otherwise, set has_ambiguities = true and provide the questions list.

        Return ONLY the structured output — no preamble, no markdown outside the specified fields.
    "#
}

// --- Planner ---

function PlanFeatures(specs_content: string, clarifications: string, existing_plan: string) -> FeaturePlan {
    client Default
    prompt #"
        Read the specs and clarifications below. You are extracting a structured feature checklist.

        SPECS:
        {{ specs_content }}

        CLARIFICATIONS (user answers — incorporate these into feature descriptions and criteria):
        {{ clarifications }}

        EXISTING PLAN (merge into this — do NOT overwrite completed [x] items):
        {{ existing_plan }}

        Produce a complete, ordered feature checklist. Each feature must have:
        - A kebab-case slug (max 40 chars, alphanumerics + hyphens only)
        - A one-line description
        - 2-8 acceptance criteria (numbered, testable, user-observable invariants — NOT implementation details)

        Order features logically: infrastructure/setup first, then core features, then polish/UX.

        Keep any EXISTING features that already have [x] (completed) — add new features AFTER them.
        Use clarifications to resolve ambiguities — don't echo questions back as features.

        Return ONLY the structured output.
    "#
}

// --- Preflight Mapper ---

function PreflightMap(file_listing: string, manifest_files: string, history: string) -> MapperReport {
    client Default
    prompt #"
        Walk the project codebase and build an initial vault map.

        FILE LISTING:
        {{ file_listing }}

        MANIFEST FILES (package.json, pyproject.toml, Cargo.toml, etc. if present):
        {{ manifest_files }}

        Produce a MapperReport with:
        - entities_updated: list of major modules/classes/services you identified (one-line name each)
        - log_entry: "Pre-flight map complete. N entities found."
        - deviations_summary: always "Implementation matched plan — no deviations." (pre-flight, nothing to deviate from)

        Return ONLY the structured output. The Python harness will write vault files based on your report.
    "#
}

// --- Research ---

class ResearchFindings {
    findings ResearchFinding[]
    recommendations string[]
}

class ResearchFinding {
    title string
    insight string @description("2-4 sentence key insight")
    relevance string @description("One-sentence relevance to this feature")
    confidence string @description("High | Medium | Low")
    source_url string? @description("If web search was used")
}

function ResearchFeature(feature_name: string, slug: string, research_type: string, sub_prompt: string?, vault_overview: string, vault_structure: string) -> ResearchFindings {
    client Default
    prompt #"
        Feature to research: {{ feature_name }} (slug: {{ slug }})
        Research type: {{ research_type }}
        {% if sub_prompt %}
        Additional focus: {{ sub_prompt }}
        {% endif %}

        VAULT OVERVIEW:
        {{ vault_overview }}

        VAULT STRUCTURE:
        {{ vault_structure }}

        Draw on your training knowledge to surface 3-5 relevant findings. For each finding:
        - Title (topic or pattern name)
        - Key insight (2-4 sentences)
        - Relevance to this feature (1 sentence)
        - Confidence: High / Medium / Low (based on how current and well-established this knowledge is)

        Also provide 2-4 concrete, actionable recommendations for the Refiner and Architect.

        Return ONLY the structured output.
    "#
}

// --- Refiner ---

function RefineApproaches(feature_name: string, slug: string, vault_overview: string, vault_structure: string, vault_deps: string, acceptance_criteria: string, research_findings: string?) -> Decision {
    client Default
    prompt #"
        Feature to evaluate: {{ feature_name }} (slug: {{ slug }})

        VAULT OVERVIEW:
        {{ vault_overview }}

        VAULT STRUCTURE:
        {{ vault_structure }}

        VAULT DEPENDENCIES:
        {{ vault_deps }}

        ACCEPTANCE CRITERIA:
        {{ acceptance_criteria }}

        {% if research_findings %}
        RESEARCH FINDINGS:
        {{ research_findings }}
        {% endif %}

        Generate exactly 3 distinct implementation approaches. For each:
        - Name (2-4 words)
        - Description (3-5 sentences)
        - Scores 1-5: Simplicity, Completeness, Risk (5=low risk), Fit

        Select the highest total score (prefer simpler on tie).
        Write a rationale explaining why this approach was chosen.

        Do not write any code. This is a design decision only.
        Return ONLY the structured output with exactly 3 approaches.
    "#
}

// --- Architect ---

function ArchitectFeature(feature_name: string, slug: string, vault_structure: string, vault_entrypoints: string, acceptance_criteria: string, decision_text: string?, research_findings: string?) -> TechPlan {
    client Default
    prompt #"
        Feature to plan: {{ feature_name }} (slug: {{ slug }})

        VAULT STRUCTURE:
        {{ vault_structure }}

        VAULT ENTRYPOINTS:
        {{ vault_entrypoints }}

        ACCEPTANCE CRITERIA (from pending/plan.md — reference these by number):
        {{ acceptance_criteria }}

        {% if decision_text %}
        DECISION (chosen approach):
        {{ decision_text }}
        {% endif %}

        {% if research_findings %}
        RESEARCH FINDINGS:
        {{ research_findings }}
        {% endif %}

        Produce a concrete, file-level implementation plan. Do NOT write any code.
        The Python harness will write this to both pending/plan-{{ slug }}.md and raw/{{ slug }}/TECH.md.

        Fill in every field:
        - context: what's being built, how the current system works in the area being changed. Reference criteria by number.
        - files_to_create: every new file path with one-line purpose
        - files_to_modify: every existing file path with what changes
        - interfaces: function signatures, type definitions, API shapes
        - edge_cases: every boundary condition you can think of
        - criteria_mapping: for EACH acceptance criterion by number, state the concrete test or verification step that proves it

        Return ONLY the structured output.
    "#
}

// --- Builder (tool-using: returns BuildStep union until done) ---

class BuilderToolCall {
    tool_name string @description("vault_read | vault_write | run_shell_command")
    args map<string, string>
}

class BuilderFinal {
    report BuilderReport
}

type BuilderStep = BuilderToolCall | BuilderFinal

function BuildFeature(tech_plan: string, decision_text: string?, slug: string, feature_description: string, history: string) -> BuilderStep {
    client Default
    prompt #"
        Feature to implement: {{ feature_description }} (slug: {{ slug }})

        IMPLEMENTATION PLAN:
        {{ tech_plan }}

        {% if decision_text %}
        DECISION:
        {{ decision_text }}
        {% endif %}

        PREVIOUS TURNS (tool calls and results from this conversation):
        {{ history }}

        You have access to tools: vault_read, vault_write, run_shell_command.

        Your job: implement the feature exactly as planned. Write code to the project.
        All shell commands must be fully non-interactive (no prompts).
        For scaffolding tools, pass flags that suppress prompts
        (e.g. `npm create vite@latest myapp -- --template react`, `npm init -y`, `git init --quiet`).
        Never run a command that waits for stdin.
        Make a git commit when done.

        Log any ambiguities or deviations from the plan — they go into the final BuilderReport.

        If you need to read a vault file, return a BuilderToolCall with tool_name "vault_read".
        If you need to write code or run a shell command, use "run_shell_command".
        If you need to write a vault file, use "vault_write".
        When implementation is complete, return a BuilderFinal with the BuilderReport.

        You MUST make a git commit. If nothing changed, explain why in deviations.
        You may make multiple tool calls before returning the final report.
    "#
}

// --- Verifier (tool-using: returns VerifierStep union until done) ---

class VerifierToolCall {
    tool_name string @description("vault_read | run_shell_command")
    args map<string, string>
}

class VerifierFinal {
    report VerifierReport
}

type VerifierStep = VerifierToolCall | VerifierFinal

function VerifyBuild(tech_plan: string, slug: string, history: string) -> VerifierStep {
    client Default
    prompt #"
        Feature just built (slug: {{ slug }}).

        IMPLEMENTATION PLAN (contains acceptance criteria mapping):
        {{ tech_plan }}

        PREVIOUS TURNS (tool calls and results from this conversation):
        {{ history }}

        You have access to tools: vault_read, run_shell_command.

        First, read the implementation plan above to understand the acceptance criteria mapping.
        You will reference criteria by number in your failure report.

        Next, run `cat AGENTS.md` using run_shell_command.
        If the file exists, use the build, test, and lint commands listed under the ## Commands section.
        If the file is absent or empty, fall back to sniffing the project type:

        **TypeScript / JavaScript** (package.json present):
          1. Type-check: `npx tsc --noEmit` (or `npm run typecheck` if that script exists)
          2. Lint: `npm run lint` if the script exists, else `npx eslint . --ext .ts,.tsx,.js,.jsx`
          3. Tests: `npm test`

        **Python** (pyproject.toml / setup.cfg / pytest.ini present):
          1. Type-check: `python -m mypy .` if mypy is installed
          2. Lint: `python -m ruff check .` if ruff is installed, else `python -m flake8 .`
          3. Tests: `python -m pytest`

        **Rust** (Cargo.toml present):
          1. Type-check + lint: `cargo clippy -- -D warnings`
          2. Tests: `cargo test`

        **Go** (go.mod present):
          1. Vet: `go vet ./...`
          2. Tests: `go test ./...`

        **Fallback** (none of the above): check for a Makefile and run `make test` or `make check`.

        Run ALL applicable quality checks. Collect every failure before writing the report.

        After running all checks:
        - If every check passed: return VerifierFinal with status "PASSED", empty failures, empty fix_hints.
        - If any check failed: return VerifierFinal with status "FAILED" and a structured failure report.

        For each failure:
        - Check type (typecheck / lint / test) and command run
        - Error message (trimmed)
        - Likely cause (1 sentence)
        - Criterion impact: which acceptance criterion this affects, or "No criterion mapped"

        Provide fix_hints: concrete, file-level suggestions for the Builder to address each failure.

        You may make multiple tool calls (run_shell_command for checks, vault_read for context)
        before returning the final VerifierFinal. Return a VerifierToolCall for each tool use.
        When done, return a VerifierFinal.
    "#
}

// --- Mapper (tool-using: returns MapperStep union until done) ---

class MapperToolCall {
    tool_name string @description("vault_read | vault_write | run_shell_command")
    args map<string, string>
}

class MapperFinal {
    report MapperReport
}

type MapperStep = MapperToolCall | MapperFinal

function MapAndIndex(git_diff: string, slug: string, feature_description: string, plan_text: string, tech_plan: string, index_text: string, history: string) -> MapperStep {
    client Default
    prompt #"
        Feature just built: {{ feature_description }} (slug: {{ slug }})

        GIT DIFF (what was built — run `git diff HEAD~1`):
        {{ git_diff }}

        IMPLEMENTATION PLAN (pending/plan-{{ slug }}.md):
        {{ plan_text }}

        TECH SPEC (raw/{{ slug }}/TECH.md):
        {{ tech_plan }}

        VAULT INDEX:
        {{ index_text }}

        PREVIOUS TURNS (tool calls and results from this conversation):
        {{ history }}

        You have access to tools: vault_read, vault_write, run_shell_command.

        You may make multiple tool calls. When done, return a MapperFinal with report.

        Your job:
        1. Update or create entity pages in entities/ for any new modules/classes/services seen in the diff.
        2. Update map/structure.md, map/dependencies.md, map/entrypoints.md as needed (read first, then write).
        3. Update index.md to list any new vault pages.
        4. Append a summary entry to log.md.
        5. Resolve open questions in pending/questions.md (replace - [ ] with - [x]).
        6. Mark the feature complete in pending/plan.md: change `- [ ] {{ slug }}:` to `- [x] {{ slug }}:`.
        7. Update raw/{{ slug }}/TECH.md deviations: compare the git diff against the plan.
           If the implementation deviated, fill in ## Deviations with what changed and why.
           If matched exactly, write: "Implementation matched plan — no deviations."

        Vault health checks (mention issues in the log entry, do not block):
        - Every page in index.md exists on disk
        - log.md has an entry for {{ slug }}
        - {{ slug }} is checked off in pending/plan.md
        - raw/{{ slug }}/TECH.md has a non-empty ## Deviations section

        When all updates are done, return a MapperFinal with:
        - entities_updated: names of entity pages created/updated
        - log_entry: one-sentence summary of what was done
        - deviations_summary: the deviations text for TECH.md (or "Implementation matched plan — no deviations.")
    "#
}
