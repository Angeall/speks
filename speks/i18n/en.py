"""English translation strings."""

from __future__ import annotations

STRINGS: dict[str, str] = {
    # ── CLI ──────────────────────────────────────────────────────────────
    "cli.app_help": "Speks — Interactive Functional Analysis Generator",
    "cli.dir_exists": "Directory '{name}' already exists.",
    "cli.workspace_created": "Workspace created at",
    "cli.run_hint": "Run",
    "cli.building_mkdocs": "Building site with MkDocs …",
    "cli.serving_at": "Serving at",
    "cli.stop_hint": "(Ctrl+C to stop)",
    "cli.watching": "Watching {dirs} for changes …",
    "cli.rebuilding": "Change detected, rebuilding …",
    "cli.rebuild_done": "Rebuild complete.",
    "cli.rebuild_error": "Rebuild failed: {error}",

    # ── Contract table ───────────────────────────────────────────────────
    "contract.parameter": "Parameter",
    "contract.type": "Type",
    "contract.default": "Default",
    "contract.description": "Description",
    "contract.return": "Return",
    "contract.no_params": "No parameters",
    "contract.inputs": "Inputs",
    "contract.output": "Output",

    # ── Playground ───────────────────────────────────────────────────────
    "playground.title": "Playground",
    "playground.view_source": "View source code",
    "playground.run_button": "Run rule",
    "playground.disabled_tooltip": "Only available via speks serve",
    "playground.mock_config": "Mock configuration",
    "playground.simulate_error": "Simulate error",

    # ── Playground JS (embedded in HTML) ─────────────────────────────────
    "js.invalid_json": "Error: Invalid JSON in mock configuration.",
    "js.running": "Running…",
    "js.error_prefix": "Error: ",
    "js.network_error": "Network error: ",
    "js.inputs_label": "Inputs:",
    "js.result_label": "Result:",
    "js.calls_label": "External calls (mocked):",

    # ── PlantUML ─────────────────────────────────────────────────────────
    "plantuml.alt": "PlantUML diagram",
    "plantuml.source_label": "PlantUML Source",
    "plantuml.file_not_found": "PlantUML: {arg} (file not found)",

    # ── Dependencies legend ──────────────────────────────────────────────
    "deps.entry_point": "entry point",
    "deps.internal_func": "Internal business function",
    "deps.external_svc": "External service (blackbox)",
    "deps.legend_title": "Legend",

    # ── Test cases ────────────────────────────────────────────────────────
    "tc.panel_title": "Test cases",
    "tc.no_testcases": "No test cases saved yet.",
    "tc.save": "Save as test case",
    "tc.replay": "Replay",
    "tc.replay_all": "Replay all",
    "tc.delete": "Delete",
    "tc.name_prompt": "Test case name:",
    "tc.expected_prompt": "Expected result (JSON):",
    "tc.saved": "Test case saved.",
    "tc.confirm_delete": "Delete this test case?",
    "tc.pass": "PASS",
    "tc.fail": "FAIL",
    "tc.expected": "Expected:",
    "tc.actual": "Actual:",
    "tc.summary": "{passed}/{total} passed",

    # ── Sequence diagram ─────────────────────────────────────────────────
    "sequence.title": "Sequence diagram",

    # ── Versioning ────────────────────────────────────────────────────────
    "versioning.current_version": "Current (working copy)",
    "versioning.compare_versions": "Compare versions",
    "versioning.compare_title": "Compare documentation versions",
    "versioning.from_version": "From:",
    "versioning.to_version": "To:",
    "versioning.run_compare": "Compare",
    "versioning.loading_diff": "Computing diff…",
    "versioning.diff_error": "Failed to compute diff",
    "versioning.no_changes": "No changes between these versions.",
    "cli.building_version": "Building version {sha} …",
    "cli.no_git_repo": "Not a git repository — skipping version builds.",

    # ── Server ───────────────────────────────────────────────────────────
    "server.title": "Speks Dev Server",
    "server.func_not_found": "Function '{name}' not found",
    "server.timeout": "Execution interrupted after {seconds}s (timeout)",
}
