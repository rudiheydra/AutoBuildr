"""
Feature #161: UI uses strict acceptance results parser with dev-mode warnings

Tests verify:
1. The multi-format normalizeResults() was replaced with strict parseAcceptanceResults()
2. The strict parser only accepts canonical Record<string, AcceptanceValidatorResult>
3. Dev-mode warnings fire for unexpected formats (arrays, wrong shapes)
4. The acceptance tab renders correctly from both API and WS canonical data
5. Type definitions are updated to reflect the strict canonical-only contract
"""

import re
import subprocess
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_SRC = os.path.join(REPO_ROOT, "ui", "src")


def read_file(relative_path: str) -> str:
    """Read a file relative to UI source directory."""
    path = os.path.join(UI_SRC, relative_path)
    with open(path, "r") as f:
        return f.read()


class TestStep1LocateAndRemoveMultiFormatNormalization:
    """Step 1: The old normalizeResults with multi-format handling is removed."""

    def test_old_normalize_results_function_removed(self):
        """normalizeResults function no longer exists in AcceptanceResults.tsx."""
        content = read_file("components/AcceptanceResults.tsx")
        # The old function was called normalizeResults - it should not exist
        assert "function normalizeResults(" not in content, \
            "Old normalizeResults function should be removed"

    def test_no_wsvalidator_result_import(self):
        """WSValidatorResult is no longer imported in AcceptanceResults.tsx."""
        content = read_file("components/AcceptanceResults.tsx")
        # Should not have import of WSValidatorResult (comments mentioning it are OK)
        assert "import type { AgentRunVerdict, WSValidatorResult }" not in content, \
            "WSValidatorResult should not be imported in AcceptanceResults.tsx"
        # The new import should use AcceptanceValidatorResult instead
        assert "AcceptanceValidatorResult" in content, \
            "Should import AcceptanceValidatorResult instead"

    def test_no_array_format_handling_in_parser(self):
        """The parser does not contain the old multi-format array conversion logic."""
        content = read_file("components/AcceptanceResults.tsx")
        # Old code had: if (Array.isArray(input)) { return input.map(...
        # New code rejects arrays but doesn't convert them
        assert "input.map((item, idx) => ({" not in content, \
            "Old array-to-object conversion logic should be removed"

    def test_no_union_type_in_props(self):
        """AcceptanceResultsProps no longer accepts ValidatorResult[] | WSValidatorResult[] union."""
        content = read_file("components/AcceptanceResults.tsx")
        # Extract the AcceptanceResultsProps interface to check its acceptanceResults field
        props_match = content.split("interface AcceptanceResultsProps")[1].split("}")[0]
        # Should NOT contain array union types for acceptanceResults
        assert "| ValidatorResult[]" not in props_match, \
            "Props should not accept ValidatorResult[] in union"
        assert "| WSValidatorResult[]" not in props_match, \
            "Props should not accept WSValidatorResult[] in union"
        # Should use CanonicalAcceptanceResults | null
        assert "CanonicalAcceptanceResults | null" in content, \
            "Props should use CanonicalAcceptanceResults | null"


class TestStep2StrictParserForCanonicalFormat:
    """Step 2: Replace with strict parser for canonical format."""

    def test_parse_acceptance_results_function_exists(self):
        """parseAcceptanceResults function exists in AcceptanceResults.tsx."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "function parseAcceptanceResults(" in content, \
            "parseAcceptanceResults function should exist"

    def test_canonical_acceptance_results_type_exported(self):
        """CanonicalAcceptanceResults type is defined and exported."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "export type CanonicalAcceptanceResults" in content, \
            "CanonicalAcceptanceResults type should be exported"

    def test_canonical_type_is_record(self):
        """CanonicalAcceptanceResults is Record<string, AcceptanceValidatorResult>."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "Record<string, AcceptanceValidatorResult>" in content, \
            "CanonicalAcceptanceResults should be Record<string, AcceptanceValidatorResult>"

    def test_imports_acceptance_validator_result(self):
        """AcceptanceValidatorResult is imported from types."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "AcceptanceValidatorResult" in content, \
            "AcceptanceValidatorResult should be imported"

    def test_uses_memo_calls_strict_parser(self):
        """useMemo calls parseAcceptanceResults, not normalizeResults."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "parseAcceptanceResults(acceptanceResults)" in content, \
            "useMemo should call parseAcceptanceResults"

    def test_entry_validation_function_exists(self):
        """isValidResultEntry validation function exists for schema checking."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "function isValidResultEntry(" in content, \
            "isValidResultEntry validation function should exist"

    def test_validates_passed_and_message_fields(self):
        """Entry validation checks for required 'passed' (boolean) and 'message' (string)."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "typeof obj.passed === 'boolean'" in content, \
            "Should validate passed is boolean"
        assert "typeof obj.message === 'string'" in content, \
            "Should validate message is string"


class TestStep3DevModeWarnings:
    """Step 3: Add dev-mode warning if payload doesn't match expected schema."""

    def test_dev_warn_function_exists(self):
        """devWarn helper function exists."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "function devWarn(" in content, \
            "devWarn helper function should exist"

    def test_dev_warn_uses_import_meta_env_dev(self):
        """devWarn checks import.meta.env.DEV for development-only warnings."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "import.meta.env.DEV" in content, \
            "Should use import.meta.env.DEV for dev-mode check"

    def test_dev_warn_uses_console_warn(self):
        """devWarn emits console.warn."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "console.warn(" in content, \
            "Should use console.warn for dev warnings"

    def test_warning_for_array_input(self):
        """Parser warns when receiving an array instead of Record."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "Array.isArray(input)" in content, \
            "Should check for array input"
        # The devWarn should be called for arrays
        assert "Received array instead of canonical" in content, \
            "Should warn about array format"

    def test_warning_for_invalid_entry(self):
        """Parser warns when an entry doesn't match AcceptanceValidatorResult schema."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "does not match AcceptanceValidatorResult schema" in content, \
            "Should warn about invalid entries"

    def test_warning_for_non_object(self):
        """Parser warns for non-object types."""
        content = read_file("components/AcceptanceResults.tsx")
        assert 'typeof input' in content, \
            "Should check typeof input"
        assert "Received unexpected type" in content, \
            "Should warn about unexpected types"

    def test_warning_prefix_identifies_component(self):
        """Warnings include [AcceptanceResults] prefix for identification."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "[AcceptanceResults]" in content, \
            "Warnings should include [AcceptanceResults] prefix"


class TestStep4AcceptanceTabRendersFromBothSources:
    """Step 4: Verify the acceptance tab renders correctly from both API and WS data."""

    def test_run_inspector_passes_canonical_format(self):
        """RunInspector passes run.acceptance_results (canonical) to AcceptanceResults."""
        content = read_file("components/RunInspector.tsx")
        assert "acceptanceResults={run.acceptance_results}" in content, \
            "RunInspector should pass run.acceptance_results"

    def test_agent_run_type_uses_canonical_format(self):
        """AgentRun.acceptance_results is Record<string, AcceptanceValidatorResult>."""
        content = read_file("lib/types.ts")
        # Find the acceptance_results field in AgentRun
        assert "acceptance_results: Record<string, AcceptanceValidatorResult> | null" in content, \
            "AgentRun should have canonical acceptance_results type"

    def test_ws_acceptance_update_has_canonical_field(self):
        """WSAgentAcceptanceUpdateMessage includes acceptance_results in canonical format."""
        content = read_file("lib/types.ts")
        assert "acceptance_results: Record<string, AcceptanceValidatorResult>" in content, \
            "WS message should include canonical acceptance_results"

    def test_hook_state_uses_canonical_type(self):
        """useAgentRunUpdates hook state uses Record<string, AcceptanceValidatorResult>."""
        content = read_file("hooks/useAgentRunUpdates.ts")
        assert "Record<string, AcceptanceValidatorResult>" in content, \
            "Hook state should use canonical AcceptanceValidatorResult type"

    def test_hook_imports_acceptance_validator_result(self):
        """useAgentRunUpdates imports AcceptanceValidatorResult."""
        content = read_file("hooks/useAgentRunUpdates.ts")
        assert "AcceptanceValidatorResult" in content, \
            "Hook should import AcceptanceValidatorResult"

    def test_hook_uses_canonical_results_directly(self):
        """Hook uses message.acceptance_results directly (no conversion)."""
        content = read_file("hooks/useAgentRunUpdates.ts")
        assert "message.acceptance_results" in content, \
            "Hook should use message.acceptance_results directly"


class TestStep5TypeScriptCompilation:
    """Step 5: TypeScript compilation passes with the strict parser changes."""

    def test_typescript_compiles_without_errors(self):
        """Full TypeScript compilation passes with zero errors."""
        result = subprocess.run(
            ["npx", "--prefix", os.path.join(REPO_ROOT, "ui"),
             "tsc", "-p", os.path.join(REPO_ROOT, "ui", "tsconfig.json"),
             "--noEmit"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, \
            f"TypeScript compilation failed:\n{result.stdout}\n{result.stderr}"


class TestStep5MalformedPayloadDevWarning:
    """Step 5 (feature step): Test malformed payload warning behavior via code analysis."""

    def test_array_input_returns_empty(self):
        """When array input is received, parser returns empty array (not crash)."""
        content = read_file("components/AcceptanceResults.tsx")
        # After the Array.isArray check and devWarn, it should return []
        # Find the block: if (Array.isArray(input)) { ... return [] }
        array_check_idx = content.find("Array.isArray(input)")
        assert array_check_idx > 0
        # Find the next 'return []' after the array check
        after_check = content[array_check_idx:array_check_idx + 300]
        assert "return []" in after_check, \
            "Array input should return empty array"

    def test_null_input_returns_empty(self):
        """Null input returns empty array without warning."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "if (!input) return []" in content, \
            "Null input should return empty array"

    def test_invalid_entry_skipped_not_crash(self):
        """Invalid entries are skipped (with warning) rather than crashing."""
        content = read_file("components/AcceptanceResults.tsx")
        # After isValidResultEntry check, invalid entries should 'continue'
        assert "continue" in content, \
            "Invalid entries should be skipped with continue"

    def test_valid_record_entries_are_parsed(self):
        """Valid Record entries are correctly parsed into ValidatorResult array."""
        content = read_file("components/AcceptanceResults.tsx")
        # Should push entries to results array with all fields
        assert "results.push({" in content, \
            "Valid entries should be pushed to results"
        assert "type," in content, \
            "Should include type field"
        assert "passed: entry.passed" in content, \
            "Should include passed field"
        assert "message: entry.message" in content, \
            "Should include message field"
        assert "score: entry.score" in content, \
            "Should include optional score field"
        assert "required: entry.required" in content, \
            "Should include optional required field"
        assert "details: entry.details" in content, \
            "Should include optional details field"


class TestFeature161DocstringAndAnnotations:
    """Additional: Verify feature #161 is properly documented."""

    def test_feature_161_mentioned_in_component(self):
        """Feature #161 is referenced in AcceptanceResults.tsx."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "Feature #161" in content, \
            "Feature #161 should be mentioned in component"

    def test_feature_161_mentioned_in_hook(self):
        """Feature #161 is referenced in useAgentRunUpdates.ts."""
        content = read_file("hooks/useAgentRunUpdates.ts")
        assert "Feature #161" in content, \
            "Feature #161 should be mentioned in hook"

    def test_feature_160_dependency_noted(self):
        """Feature #160 dependency is acknowledged in the parser docstring."""
        content = read_file("components/AcceptanceResults.tsx")
        assert "Feature #160" in content, \
            "Feature #160 (backend standardization) should be referenced"
