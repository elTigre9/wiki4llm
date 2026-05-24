// Golden-output prompt tests for non-tool agents.
// Run with: baml-cli test --from baml_src
//
// Tool-using agents (BuildFeature, VerifyBuild, MapAndIndex) are tested via
// integration rather than golden outputs since they require a live project.

test ClarifySpecs_clean_specs {
    functions [ClarifySpecs]
    args {
        specs_content #"
            ### overview.md
            # My Project
            A CLI tool that converts markdown to HTML.
            ## Requirements
            - Input: a markdown file path via --input flag
            - Output: HTML written to stdout
            - Supports --title flag to override the HTML <title>
            - Exit code 0 on success, 1 on errors
            ## Constraints
            - No external network calls
            - Must work on Node.js 18+
        "#
    }
}

test ClarifySpecs_ambiguous_specs {
    functions [ClarifySpecs]
    args {
        specs_content #"
            ### overview.md
            # My App
            Build a dashboard for users. It should be fast and secure.
            Use the database. Support file uploads. Include auth.
        "#
    }
}

test PlanFeatures_minimal_specs {
    functions [PlanFeatures]
    args {
        specs_content #"
            ### 00-overview.md
            # Todo CLI
            A command-line todo list manager.
            ## Features
            - Add a todo item with a title
            - List all todo items
            - Mark a todo as done by ID
            - Delete a todo by ID
            - Data persists to a JSON file at ~/.todos.json
            ## Constraints
            - Node.js 18+, TypeScript
            - No external dependencies
        "#
        clarifications "(no clarifications yet)"
        existing_plan "(no existing plan)"
    }
}

test RefineApproaches_simple_feature {
    functions [RefineApproaches]
    args {
        feature_name "JSON persistence layer"
        slug "json-persistence"
        vault_overview "# Todo CLI\nA CLI tool for managing todos."
        vault_structure "# Structure\n- src/index.ts: entry\n- src/commands/: command handlers"
        vault_deps "# Dependencies\n- Node.js 18+\n- TypeScript 5.x"
        acceptance_criteria #"
            1. Todos persist to ~/.todos.json between sessions
            2. File is created on first write if it doesn't exist
            3. Corrupt JSON file is replaced with empty list (no crash)
            4. Write operations are atomic (write to temp, then rename)
        "#
    }
}

test ArchitectFeature_simple {
    functions [ArchitectFeature]
    args {
        feature_name "CLI argument parser"
        slug "cli-parser"
        vault_structure "# Structure\n- src/index.ts: entry point\n- src/cli.ts: argument definitions"
        vault_entrypoints "# Entrypoints\n- src/index.ts: parses argv, dispatches to commands"
        acceptance_criteria #"
            1. --input flag accepts a file path
            2. --title flag is optional, defaults to "Untitled"
            3. Unknown flags print usage and exit 1
            4. Missing required --input prints error and exit 1
        "#
    }
}
