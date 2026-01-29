"""
Tests for Feature #140: LintCleanValidator Implementation
==========================================================

Feature: Implement LintCleanValidator class or remove from VALIDATOR_TYPES.
The spec lists lint_clean as an optional validator and VALIDATOR_TYPES includes it,
but no LintCleanValidator class existed. This implements the validator.

Steps:
1. Check if 'lint_clean' is listed in VALIDATOR_TYPES in agentspec_models.py
2. Create a LintCleanValidator class in validators.py following the same pattern
3. The validator should accept a linter command in its config, run it, and check for zero errors
4. Register the validator in the validator registry so it can be resolved by name
5. Verify the validator works with a sample linter command (e.g., 'flake8' or 'eslint')
6. Verify the validator correctly reports pass/fail based on linter output

Tests cover all verification steps with comprehensive edge cases.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.validators import (
    LintCleanValidator,
    Validator,
    ValidatorResult,
    VALIDATOR_REGISTRY,
    get_validator,
    evaluate_validator,
)
from api.agentspec_models import VALIDATOR_TYPES


# =============================================================================
# Step 1: 'lint_clean' is listed in VALIDATOR_TYPES
# =============================================================================

class TestStep1LintCleanInValidatorTypes:
    """Test that 'lint_clean' is listed in VALIDATOR_TYPES."""

    def test_lint_clean_in_validator_types(self):
        """'lint_clean' is present in the VALIDATOR_TYPES constant."""
        assert "lint_clean" in VALIDATOR_TYPES

    def test_validator_types_is_list(self):
        """VALIDATOR_TYPES is a list."""
        assert isinstance(VALIDATOR_TYPES, list)


# =============================================================================
# Step 2: LintCleanValidator class follows the same pattern as existing validators
# =============================================================================

class TestStep2LintCleanValidatorClass:
    """Test that LintCleanValidator properly implements Validator interface."""

    def test_class_exists(self):
        """LintCleanValidator class exists."""
        assert LintCleanValidator is not None

    def test_is_subclass_of_validator(self):
        """LintCleanValidator is a subclass of Validator."""
        assert issubclass(LintCleanValidator, Validator)

    def test_has_validator_type_attribute(self):
        """LintCleanValidator has validator_type attribute set to 'lint_clean'."""
        validator = LintCleanValidator()
        assert hasattr(validator, "validator_type")
        assert validator.validator_type == "lint_clean"

    def test_has_evaluate_method(self):
        """LintCleanValidator has evaluate method."""
        validator = LintCleanValidator()
        assert hasattr(validator, "evaluate")
        assert callable(validator.evaluate)

    def test_evaluate_returns_validator_result(self):
        """evaluate() returns a ValidatorResult instance."""
        validator = LintCleanValidator()
        config = {"command": "echo clean"}
        context = {}
        result = validator.evaluate(config, context)
        assert isinstance(result, ValidatorResult)

    def test_has_interpolate_path_method(self):
        """LintCleanValidator inherits interpolate_path from Validator base."""
        validator = LintCleanValidator()
        assert hasattr(validator, "interpolate_path")
        assert callable(validator.interpolate_path)


# =============================================================================
# Step 3: Validator accepts linter command, runs it, checks for zero errors
# =============================================================================

class TestStep3LinterCommandExecution:
    """Test that LintCleanValidator accepts a command, runs it, and checks for errors."""

    def test_clean_lint_passes(self):
        """A command that exits with 0 passes the lint check."""
        validator = LintCleanValidator()
        config = {"command": "echo clean"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.score == 1.0
        assert result.validator_type == "lint_clean"
        assert "Lint clean" in result.message

    def test_dirty_lint_fails(self):
        """A command that exits with non-zero fails the lint check."""
        validator = LintCleanValidator()
        config = {"command": "exit 1"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert result.score == 0.0
        assert result.validator_type == "lint_clean"
        assert "Lint failed" in result.message

    def test_missing_command_fails(self):
        """Missing 'command' in config returns failure."""
        validator = LintCleanValidator()
        config = {}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "missing required 'command' field" in result.message

    def test_empty_command_fails(self):
        """Empty 'command' in config returns failure."""
        validator = LintCleanValidator()
        config = {"command": ""}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "missing required 'command' field" in result.message

    def test_command_with_output(self):
        """Command output is captured in result details."""
        validator = LintCleanValidator()
        config = {"command": "echo 'lint warning: unused variable'"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert "lint warning" in result.details["stdout"]

    def test_failed_command_with_stderr(self):
        """stderr is captured when command fails."""
        validator = LintCleanValidator()
        config = {"command": "echo 'error: syntax error' >&2; exit 1"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "syntax error" in result.details["stderr"]

    def test_issue_count_in_details(self):
        """The number of lint issues is reported in details."""
        validator = LintCleanValidator()
        # Command outputs 3 lines (3 lint issues)
        config = {"command": "printf 'error1\\nerror2\\nerror3'"}
        result = validator.evaluate(config, {})
        assert result.passed is True  # exit code 0
        assert result.details["issue_count"] == 3

    def test_issue_count_zero_for_no_output(self):
        """Issue count is 0 when command produces no output."""
        validator = LintCleanValidator()
        config = {"command": "true"}  # produces no output
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.details["issue_count"] == 0

    def test_variable_interpolation_in_command(self):
        """Variables in command template are interpolated from context."""
        validator = LintCleanValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"command": "ls {project_dir}"}
            context = {"project_dir": tmpdir}
            result = validator.evaluate(config, context)
            assert result.passed is True
            assert result.details["interpolated_command"] == f"ls {tmpdir}"

    def test_custom_expected_exit_code(self):
        """Custom expected_exit_code allows non-zero codes to pass."""
        validator = LintCleanValidator()
        config = {"command": "exit 2", "expected_exit_code": 2}
        result = validator.evaluate(config, {})
        assert result.passed is True

    def test_invalid_expected_exit_code_string(self):
        """Invalid expected_exit_code string returns failure."""
        validator = LintCleanValidator()
        config = {"command": "echo ok", "expected_exit_code": "not_a_number"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "Invalid expected_exit_code" in result.message

    def test_timeout_handling(self):
        """Command that exceeds timeout returns failure."""
        validator = LintCleanValidator()
        config = {
            "command": "sleep 10",
            "timeout_seconds": 1,
        }
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "timed out" in result.message
        assert result.details["error"] == "timeout"

    def test_working_directory(self):
        """Working directory is used for command execution."""
        validator = LintCleanValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"command": "pwd", "working_directory": tmpdir}
            result = validator.evaluate(config, {})
            assert result.passed is True
            assert tmpdir in result.details["stdout"]

    def test_working_directory_from_context(self):
        """project_dir from context is used as default working directory."""
        validator = LintCleanValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"command": "pwd"}
            context = {"project_dir": tmpdir}
            result = validator.evaluate(config, context)
            assert result.passed is True
            assert tmpdir in result.details["stdout"]

    def test_description_in_message(self):
        """Description is appended to the result message."""
        validator = LintCleanValidator()
        config = {
            "command": "echo ok",
            "description": "Python code must pass linting",
        }
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert "Python code must pass linting" in result.message

    def test_error_pattern_counting(self):
        """Custom error_pattern counts matching lines."""
        validator = LintCleanValidator()
        config = {
            "command": "printf 'ERROR: bad1\\nWARN: ok\\nERROR: bad2\\nINFO: fine'",
            "error_pattern": "^ERROR:",
        }
        result = validator.evaluate(config, {})
        assert result.passed is True  # exit code 0
        assert result.details["issue_count"] == 2

    def test_invalid_error_pattern(self):
        """Invalid error_pattern regex returns failure."""
        validator = LintCleanValidator()
        config = {
            "command": "echo ok",
            "error_pattern": "[invalid",
        }
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "Invalid error_pattern regex" in result.message

    def test_command_not_found_failure(self):
        """Non-existent command returns failure with appropriate message."""
        validator = LintCleanValidator()
        # Use a command that definitely doesn't exist
        config = {"command": "/nonexistent/command_xyz_12345"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        # May be handled as OSError or non-zero exit code depending on shell
        assert result.score == 0.0


# =============================================================================
# Step 4: Validator is registered in the validator registry
# =============================================================================

class TestStep4ValidatorRegistry:
    """Test that LintCleanValidator is registered in the validator registry."""

    def test_lint_clean_in_registry(self):
        """'lint_clean' key exists in VALIDATOR_REGISTRY."""
        assert "lint_clean" in VALIDATOR_REGISTRY

    def test_registry_maps_to_correct_class(self):
        """VALIDATOR_REGISTRY['lint_clean'] maps to LintCleanValidator."""
        assert VALIDATOR_REGISTRY["lint_clean"] is LintCleanValidator

    def test_get_validator_returns_lint_clean(self):
        """get_validator('lint_clean') returns a LintCleanValidator instance."""
        validator = get_validator("lint_clean")
        assert validator is not None
        assert isinstance(validator, LintCleanValidator)
        assert validator.validator_type == "lint_clean"

    def test_evaluate_validator_with_lint_clean(self):
        """evaluate_validator() works with lint_clean type."""
        validator_def = {
            "type": "lint_clean",
            "config": {"command": "echo clean"},
            "weight": 1.0,
            "required": False,
        }
        result = evaluate_validator(validator_def, {})
        assert isinstance(result, ValidatorResult)
        assert result.passed is True
        assert result.validator_type == "lint_clean"


# =============================================================================
# Step 5: Verify validator works with a sample linter command
# =============================================================================

class TestStep5SampleLinterCommands:
    """Test with realistic linter command scenarios."""

    def test_echo_simulated_clean_lint(self):
        """Simulated clean lint output (exit 0, no output) passes."""
        validator = LintCleanValidator()
        config = {"command": "true"}  # exit code 0, no output
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.details["actual_exit_code"] == 0
        assert result.details["issue_count"] == 0

    def test_echo_simulated_lint_errors(self):
        """Simulated lint with errors (exit 1, error output) fails."""
        validator = LintCleanValidator()
        config = {
            "command": "echo 'src/main.py:10:5: E303 too many blank lines (3)' && exit 1"
        }
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert result.details["actual_exit_code"] == 1
        assert result.details["issue_count"] >= 1

    def test_ruff_style_output(self):
        """Simulated ruff-style linter output."""
        validator = LintCleanValidator()
        # Simulate ruff finding 2 errors
        config = {
            "command": (
                "printf 'api/validators.py:10:1: E302 expected 2 blank lines, got 1\\n"
                "api/validators.py:25:5: F841 local variable x is assigned but never used' && exit 1"
            )
        }
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert result.details["issue_count"] >= 2

    def test_clean_ruff_style_output(self):
        """Simulated clean ruff-style output (no issues found)."""
        validator = LintCleanValidator()
        # Simulate ruff finding no errors (exit 0, no output)
        config = {"command": "true"}
        result = validator.evaluate(config, {})
        assert result.passed is True

    def test_with_project_dir_interpolation(self):
        """Linter command with project_dir variable interpolation."""
        validator = LintCleanValidator()
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "command": "echo 'linting {project_dir}'",
                "description": "Lint the project",
            }
            context = {"project_dir": tmpdir}
            result = validator.evaluate(config, context)
            assert result.passed is True
            assert tmpdir in result.details["interpolated_command"]


# =============================================================================
# Step 6: Verify the validator correctly reports pass/fail
# =============================================================================

class TestStep6PassFailReporting:
    """Test that the validator correctly reports pass/fail status."""

    def test_pass_result_structure(self):
        """Passing result has correct structure."""
        validator = LintCleanValidator()
        config = {"command": "true"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.score == 1.0
        assert result.validator_type == "lint_clean"
        assert isinstance(result.message, str)
        assert isinstance(result.details, dict)
        assert "actual_exit_code" in result.details
        assert "issue_count" in result.details

    def test_fail_result_structure(self):
        """Failing result has correct structure."""
        validator = LintCleanValidator()
        config = {"command": "exit 1"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert result.score == 0.0
        assert result.validator_type == "lint_clean"
        assert "Lint failed" in result.message
        assert result.details["actual_exit_code"] == 1

    def test_to_dict_serialization(self):
        """ValidatorResult.to_dict() works for lint_clean results."""
        validator = LintCleanValidator()
        config = {"command": "echo ok"}
        result = validator.evaluate(config, {})
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["passed"] is True
        assert d["validator_type"] == "lint_clean"
        assert "score" in d
        assert "message" in d
        assert "details" in d

    def test_multiple_evaluations_independent(self):
        """Multiple evaluations produce independent results."""
        validator = LintCleanValidator()
        result1 = validator.evaluate({"command": "true"}, {})
        result2 = validator.evaluate({"command": "exit 1"}, {})
        result3 = validator.evaluate({"command": "echo clean"}, {})

        assert result1.passed is True
        assert result2.passed is False
        assert result3.passed is True

    def test_details_contain_all_expected_fields(self):
        """Details dict contains all expected fields for successful execution."""
        validator = LintCleanValidator()
        config = {
            "command": "echo lint_output",
            "timeout_seconds": 30,
        }
        result = validator.evaluate(config, {})
        details = result.details

        assert "command_template" in details
        assert "interpolated_command" in details
        assert "expected_exit_code" in details
        assert "actual_exit_code" in details
        assert "timeout_seconds" in details
        assert "working_directory" in details
        assert "issue_count" in details
        assert "stdout" in details
        assert "stderr" in details

    def test_timeout_seconds_default(self):
        """Default timeout is 120 seconds for LintCleanValidator."""
        validator = LintCleanValidator()
        config = {"command": "echo ok"}
        result = validator.evaluate(config, {})
        assert result.details["timeout_seconds"] == 120

    def test_timeout_seconds_custom(self):
        """Custom timeout is respected."""
        validator = LintCleanValidator()
        config = {"command": "echo ok", "timeout_seconds": 60}
        result = validator.evaluate(config, {})
        assert result.details["timeout_seconds"] == 60

    def test_timeout_seconds_clamped(self):
        """Timeout is clamped between 1 and 3600 seconds."""
        validator = LintCleanValidator()

        # Test lower bound
        config = {"command": "echo ok", "timeout_seconds": 0}
        result = validator.evaluate(config, {})
        assert result.details["timeout_seconds"] == 1

        # Test upper bound
        config = {"command": "echo ok", "timeout_seconds": 99999}
        result = validator.evaluate(config, {})
        assert result.details["timeout_seconds"] == 3600


# =============================================================================
# Integration: Test via the api module exports
# =============================================================================

class TestIntegrationApiExports:
    """Test that LintCleanValidator is properly exported from the api package."""

    def test_import_from_api(self):
        """LintCleanValidator can be imported from api package."""
        from api import LintCleanValidator as LC
        assert LC is LintCleanValidator

    def test_import_from_api_validators(self):
        """LintCleanValidator can be imported from api.validators."""
        from api.validators import LintCleanValidator as LC
        assert LC is not None

    def test_registry_accessible_from_api(self):
        """VALIDATOR_REGISTRY from api includes lint_clean."""
        from api import VALIDATOR_REGISTRY as registry
        assert "lint_clean" in registry


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases for LintCleanValidator."""

    def test_count_lint_issues_private_method(self):
        """_count_lint_issues correctly counts issues."""
        validator = LintCleanValidator()

        # No output
        assert validator._count_lint_issues("", None) == 0
        assert validator._count_lint_issues("   ", None) == 0

        # With output lines
        assert validator._count_lint_issues("error1\nerror2", None) == 2
        assert validator._count_lint_issues("error1\n\nerror2\n", None) == 2

    def test_count_lint_issues_with_pattern(self):
        """_count_lint_issues with error_pattern filters correctly."""
        import re
        validator = LintCleanValidator()
        pattern = re.compile(r"^ERROR:")

        output = "ERROR: bad\nWARN: ok\nERROR: bad2\nINFO: fine"
        assert validator._count_lint_issues(output, pattern) == 2

    def test_string_timeout_seconds(self):
        """String timeout_seconds is converted to int."""
        validator = LintCleanValidator()
        config = {"command": "echo ok", "timeout_seconds": "30"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.details["timeout_seconds"] == 30

    def test_invalid_string_timeout_seconds(self):
        """Invalid string timeout_seconds falls back to default 120."""
        validator = LintCleanValidator()
        config = {"command": "echo ok", "timeout_seconds": "invalid"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.details["timeout_seconds"] == 120

    def test_string_expected_exit_code(self):
        """String expected_exit_code is converted to int."""
        validator = LintCleanValidator()
        config = {"command": "exit 2", "expected_exit_code": "2"}
        result = validator.evaluate(config, {})
        assert result.passed is True

    def test_large_output_truncation(self):
        """Large output is truncated to prevent memory issues."""
        validator = LintCleanValidator()
        # Generate output > 4096 chars
        config = {"command": "python3 -c \"print('x' * 5000)\""}
        result = validator.evaluate(config, {})
        assert result.passed is True
        # Output should be truncated
        stdout = result.details["stdout"]
        assert len(stdout) <= 4200  # ~4096 + truncation prefix
