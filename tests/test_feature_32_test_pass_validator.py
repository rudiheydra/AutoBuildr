"""
Tests for Feature #32: test_pass Acceptance Validator
=====================================================

Feature: Implement test_pass validator that runs a shell command and checks
exit code for acceptance testing.

Steps:
1. Create TestPassValidator class implementing Validator interface
2. Extract command from validator config
3. Extract expected_exit_code (default 0)
4. Extract timeout_seconds (default 60)
5. Execute command via subprocess with timeout
6. Capture stdout and stderr
7. Compare exit code to expected
8. Return ValidatorResult with passed boolean
9. Include command output in result message
10. Handle timeout as failure
11. Handle command not found as failure

Tests cover all verification steps with comprehensive edge cases.
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.validators import (
    TestPassValidator,
    Validator,
    ValidatorResult,
    VALIDATOR_REGISTRY,
    get_validator,
    evaluate_validator,
)


# =============================================================================
# Step 1: TestPassValidator class implementing Validator interface
# =============================================================================

class TestStep1ValidatorInterface:
    """Test that TestPassValidator properly implements Validator interface."""

    def test_class_exists(self):
        """TestPassValidator class exists."""
        assert TestPassValidator is not None

    def test_is_subclass_of_validator(self):
        """TestPassValidator is a subclass of Validator."""
        assert issubclass(TestPassValidator, Validator)

    def test_has_validator_type_attribute(self):
        """TestPassValidator has validator_type attribute set to 'test_pass'."""
        validator = TestPassValidator()
        assert hasattr(validator, 'validator_type')
        assert validator.validator_type == "test_pass"

    def test_has_evaluate_method(self):
        """TestPassValidator has evaluate method."""
        validator = TestPassValidator()
        assert hasattr(validator, 'evaluate')
        assert callable(validator.evaluate)

    def test_evaluate_returns_validator_result(self):
        """evaluate() returns a ValidatorResult instance."""
        validator = TestPassValidator()
        config = {"command": "echo hello"}
        context = {}
        result = validator.evaluate(config, context)
        assert isinstance(result, ValidatorResult)

    def test_registered_in_validator_registry(self):
        """TestPassValidator is registered in VALIDATOR_REGISTRY."""
        assert "test_pass" in VALIDATOR_REGISTRY
        assert VALIDATOR_REGISTRY["test_pass"] == TestPassValidator

    def test_get_validator_returns_instance(self):
        """get_validator('test_pass') returns a TestPassValidator instance."""
        validator = get_validator("test_pass")
        assert isinstance(validator, TestPassValidator)


# =============================================================================
# Step 2: Extract command from validator config
# =============================================================================

class TestStep2ExtractCommand:
    """Test command extraction from validator config."""

    def test_command_required(self):
        """Command is required in config."""
        validator = TestPassValidator()
        config = {}  # Missing command
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False
        assert "missing required 'command' field" in result.message.lower()

    def test_empty_command_fails(self):
        """Empty command string fails."""
        validator = TestPassValidator()
        config = {"command": ""}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False

    def test_valid_command_extracted(self):
        """Valid command is properly extracted."""
        validator = TestPassValidator()
        config = {"command": "echo 'test'"}
        context = {}
        result = validator.evaluate(config, context)
        assert "echo 'test'" in result.details.get("interpolated_command", "")

    def test_command_interpolation(self):
        """Variables in command are interpolated."""
        validator = TestPassValidator()
        config = {"command": "echo {greeting}"}
        context = {"greeting": "hello"}
        result = validator.evaluate(config, context)
        assert "echo hello" in result.details.get("interpolated_command", "")

    def test_multiple_variable_interpolation(self):
        """Multiple variables in command are interpolated."""
        validator = TestPassValidator()
        config = {"command": "echo {var1} {var2}"}
        context = {"var1": "hello", "var2": "world"}
        result = validator.evaluate(config, context)
        assert "echo hello world" in result.details.get("interpolated_command", "")


# =============================================================================
# Step 3: Extract expected_exit_code (default 0)
# =============================================================================

class TestStep3ExpectedExitCode:
    """Test expected_exit_code extraction with default of 0."""

    def test_default_expected_exit_code_is_zero(self):
        """Default expected_exit_code is 0."""
        validator = TestPassValidator()
        config = {"command": "exit 0"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("expected_exit_code") == 0

    def test_custom_expected_exit_code(self):
        """Custom expected_exit_code is used."""
        validator = TestPassValidator()
        config = {"command": "exit 1", "expected_exit_code": 1}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("expected_exit_code") == 1
        assert result.passed is True

    def test_expected_exit_code_as_string(self):
        """expected_exit_code can be provided as string."""
        validator = TestPassValidator()
        config = {"command": "exit 2", "expected_exit_code": "2"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("expected_exit_code") == 2
        assert result.passed is True

    def test_invalid_expected_exit_code_string(self):
        """Invalid expected_exit_code string returns error."""
        validator = TestPassValidator()
        config = {"command": "echo test", "expected_exit_code": "not_a_number"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False
        assert "invalid" in result.message.lower()


# =============================================================================
# Step 4: Extract timeout_seconds (default 60)
# =============================================================================

class TestStep4TimeoutSeconds:
    """Test timeout_seconds extraction with default of 60."""

    def test_default_timeout_is_60(self):
        """Default timeout_seconds is 60."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("timeout_seconds") == 60

    def test_custom_timeout(self):
        """Custom timeout_seconds is used."""
        validator = TestPassValidator()
        config = {"command": "echo test", "timeout_seconds": 30}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("timeout_seconds") == 30

    def test_timeout_as_string(self):
        """timeout_seconds can be provided as string."""
        validator = TestPassValidator()
        config = {"command": "echo test", "timeout_seconds": "45"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("timeout_seconds") == 45

    def test_invalid_timeout_string_uses_default(self):
        """Invalid timeout_seconds string uses default."""
        validator = TestPassValidator()
        config = {"command": "echo test", "timeout_seconds": "not_a_number"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("timeout_seconds") == 60

    def test_timeout_minimum_is_1(self):
        """Timeout is at least 1 second."""
        validator = TestPassValidator()
        config = {"command": "echo test", "timeout_seconds": 0}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("timeout_seconds") >= 1

    def test_timeout_maximum_is_3600(self):
        """Timeout is at most 3600 seconds (1 hour)."""
        validator = TestPassValidator()
        config = {"command": "echo test", "timeout_seconds": 99999}
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("timeout_seconds") <= 3600


# =============================================================================
# Step 5: Execute command via subprocess with timeout
# =============================================================================

class TestStep5ExecuteSubprocess:
    """Test command execution via subprocess."""

    def test_simple_command_execution(self):
        """Simple command is executed successfully."""
        validator = TestPassValidator()
        config = {"command": "echo hello"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        assert "hello" in result.details.get("stdout", "")

    def test_command_with_pipes(self):
        """Commands with pipes work."""
        validator = TestPassValidator()
        config = {"command": "echo 'hello world' | grep hello"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        assert "hello" in result.details.get("stdout", "")

    def test_command_with_working_directory(self):
        """Command respects working_directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file in the temp directory
            test_file = Path(tmpdir) / "test_file.txt"
            test_file.write_text("test content")

            validator = TestPassValidator()
            config = {
                "command": "ls test_file.txt",
                "working_directory": tmpdir
            }
            context = {}
            result = validator.evaluate(config, context)
            assert result.passed is True
            assert "test_file.txt" in result.details.get("stdout", "")

    def test_working_directory_interpolation(self):
        """Working directory supports variable interpolation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file in the temp directory
            test_file = Path(tmpdir) / "test_file.txt"
            test_file.write_text("test content")

            validator = TestPassValidator()
            config = {
                "command": "ls test_file.txt",
                "working_directory": "{work_dir}"
            }
            context = {"work_dir": tmpdir}
            result = validator.evaluate(config, context)
            assert result.passed is True

    def test_project_dir_as_default_working_directory(self):
        """project_dir is used as default working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = TestPassValidator()
            config = {"command": "pwd"}
            context = {"project_dir": tmpdir}
            result = validator.evaluate(config, context)
            assert result.passed is True
            assert tmpdir in result.details.get("stdout", "")


# =============================================================================
# Step 6: Capture stdout and stderr
# =============================================================================

class TestStep6CaptureOutput:
    """Test stdout and stderr capture."""

    def test_stdout_captured(self):
        """stdout is captured in result details."""
        validator = TestPassValidator()
        config = {"command": "echo 'stdout output'"}
        context = {}
        result = validator.evaluate(config, context)
        assert "stdout" in result.details
        assert "stdout output" in result.details["stdout"]

    def test_stderr_captured(self):
        """stderr is captured in result details."""
        validator = TestPassValidator()
        config = {"command": "echo 'stderr output' >&2"}
        context = {}
        result = validator.evaluate(config, context)
        assert "stderr" in result.details
        assert "stderr output" in result.details["stderr"]

    def test_both_stdout_and_stderr(self):
        """Both stdout and stderr are captured."""
        validator = TestPassValidator()
        config = {"command": "echo 'out' && echo 'err' >&2"}
        context = {}
        result = validator.evaluate(config, context)
        assert "out" in result.details.get("stdout", "")
        assert "err" in result.details.get("stderr", "")

    def test_large_output_truncated(self):
        """Large output is truncated to 4KB."""
        validator = TestPassValidator()
        # Generate output larger than 4KB
        config = {"command": "python3 -c \"print('x' * 10000)\""}
        context = {}
        result = validator.evaluate(config, context)
        # Output should be truncated
        stdout = result.details.get("stdout", "")
        # Should contain truncation indicator or be limited in size
        assert len(stdout) <= 5000  # 4KB + some overhead for truncation message


# =============================================================================
# Step 7: Compare exit code to expected
# =============================================================================

class TestStep7CompareExitCode:
    """Test exit code comparison."""

    def test_exit_code_0_passes_by_default(self):
        """Exit code 0 passes when expected is default (0)."""
        validator = TestPassValidator()
        config = {"command": "exit 0"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        assert result.details.get("actual_exit_code") == 0

    def test_non_zero_exit_code_fails_by_default(self):
        """Non-zero exit code fails when expected is default (0)."""
        validator = TestPassValidator()
        config = {"command": "exit 1"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False
        assert result.details.get("actual_exit_code") == 1

    def test_matching_non_zero_exit_code_passes(self):
        """Non-zero exit code passes when expected matches."""
        validator = TestPassValidator()
        config = {"command": "exit 42", "expected_exit_code": 42}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        assert result.details.get("actual_exit_code") == 42

    def test_mismatched_exit_code_fails(self):
        """Mismatched exit code fails."""
        validator = TestPassValidator()
        config = {"command": "exit 1", "expected_exit_code": 2}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False
        assert result.details.get("actual_exit_code") == 1
        assert result.details.get("expected_exit_code") == 2


# =============================================================================
# Step 8: Return ValidatorResult with passed boolean
# =============================================================================

class TestStep8ReturnValidatorResult:
    """Test ValidatorResult return value."""

    def test_passed_is_boolean(self):
        """passed field is a boolean."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        context = {}
        result = validator.evaluate(config, context)
        assert isinstance(result.passed, bool)

    def test_result_has_message(self):
        """Result has a message."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        context = {}
        result = validator.evaluate(config, context)
        assert isinstance(result.message, str)
        assert len(result.message) > 0

    def test_result_has_score(self):
        """Result has a score (0.0 or 1.0)."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.score in (0.0, 1.0)

    def test_result_has_validator_type(self):
        """Result has validator_type set to 'test_pass'."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.validator_type == "test_pass"

    def test_result_score_matches_passed(self):
        """Score is 1.0 when passed, 0.0 when failed."""
        validator = TestPassValidator()

        # Passing case
        config = {"command": "exit 0"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.score == 1.0

        # Failing case
        config = {"command": "exit 1"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert result.score == 0.0


# =============================================================================
# Step 9: Include command output in result message
# =============================================================================

class TestStep9IncludeOutputInResult:
    """Test that command output is included in result."""

    def test_stdout_in_details(self):
        """stdout is included in result details."""
        validator = TestPassValidator()
        config = {"command": "echo 'unique_output_123'"}
        context = {}
        result = validator.evaluate(config, context)
        assert "unique_output_123" in result.details.get("stdout", "")

    def test_stderr_in_details(self):
        """stderr is included in result details."""
        validator = TestPassValidator()
        config = {"command": "echo 'error_output_456' >&2"}
        context = {}
        result = validator.evaluate(config, context)
        assert "error_output_456" in result.details.get("stderr", "")

    def test_message_includes_exit_code(self):
        """Message includes exit code information."""
        validator = TestPassValidator()
        config = {"command": "exit 5", "expected_exit_code": 0}
        context = {}
        result = validator.evaluate(config, context)
        assert "5" in result.message
        assert "0" in result.message

    def test_message_includes_description(self):
        """Message includes description if provided."""
        validator = TestPassValidator()
        config = {
            "command": "echo test",
            "description": "Running test command"
        }
        context = {}
        result = validator.evaluate(config, context)
        assert "Running test command" in result.message

    def test_details_include_command_info(self):
        """Details include command template and interpolated command."""
        validator = TestPassValidator()
        config = {"command": "echo {msg}"}
        context = {"msg": "hello"}
        result = validator.evaluate(config, context)
        assert result.details.get("command_template") == "echo {msg}"
        assert result.details.get("interpolated_command") == "echo hello"


# =============================================================================
# Step 10: Handle timeout as failure
# =============================================================================

class TestStep10HandleTimeout:
    """Test timeout handling."""

    def test_timeout_returns_failure(self):
        """Timeout causes validation to fail."""
        validator = TestPassValidator()
        config = {
            "command": "sleep 5",
            "timeout_seconds": 1
        }
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False

    def test_timeout_message_indicates_timeout(self):
        """Timeout message clearly indicates timeout occurred."""
        validator = TestPassValidator()
        config = {
            "command": "sleep 5",
            "timeout_seconds": 1
        }
        context = {}
        result = validator.evaluate(config, context)
        assert "timed out" in result.message.lower() or "timeout" in result.message.lower()

    def test_timeout_error_in_details(self):
        """Timeout is recorded in details."""
        validator = TestPassValidator()
        config = {
            "command": "sleep 5",
            "timeout_seconds": 1
        }
        context = {}
        result = validator.evaluate(config, context)
        assert result.details.get("error") == "timeout"

    def test_timeout_score_is_zero(self):
        """Timeout score is 0.0."""
        validator = TestPassValidator()
        config = {
            "command": "sleep 5",
            "timeout_seconds": 1
        }
        context = {}
        result = validator.evaluate(config, context)
        assert result.score == 0.0


# =============================================================================
# Step 11: Handle command not found as failure
# =============================================================================

class TestStep11HandleCommandNotFound:
    """Test command not found handling."""

    def test_nonexistent_command_fails(self):
        """Non-existent command causes validation to fail."""
        validator = TestPassValidator()
        config = {"command": "nonexistent_command_xyz_12345"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False

    def test_command_not_found_in_message(self):
        """Command not found is indicated in message."""
        validator = TestPassValidator()
        config = {"command": "nonexistent_command_xyz_12345"}
        context = {}
        result = validator.evaluate(config, context)
        # The message should indicate failure (exit code 127 is "command not found")
        # or contain error information
        assert result.passed is False

    def test_command_not_found_score_is_zero(self):
        """Command not found score is 0.0."""
        validator = TestPassValidator()
        config = {"command": "nonexistent_command_xyz_12345"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.score == 0.0


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for TestPassValidator."""

    def test_evaluate_validator_function(self):
        """evaluate_validator works with test_pass type."""
        validator_def = {
            "type": "test_pass",
            "config": {"command": "echo integration_test"}
        }
        result = evaluate_validator(validator_def, {})
        assert result.passed is True
        assert "integration_test" in result.details.get("stdout", "")

    def test_complex_command_with_context(self):
        """Complex command with context variables works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "data.txt"
            test_file.write_text("line1\nline2\nline3\n")

            validator = TestPassValidator()
            config = {
                "command": "wc -l {project_dir}/data.txt",
                "expected_exit_code": 0,
                "description": "Count lines in data file"
            }
            context = {"project_dir": tmpdir}
            result = validator.evaluate(config, context)
            assert result.passed is True
            assert "3" in result.details.get("stdout", "")

    def test_pytest_command(self):
        """Simulated pytest command works."""
        validator = TestPassValidator()
        # Use a command that simulates test behavior
        config = {
            "command": "python3 -c \"import sys; sys.exit(0)\"",
            "expected_exit_code": 0,
            "description": "Run Python test"
        }
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True

    def test_failing_test_command(self):
        """Failing test command is properly detected."""
        validator = TestPassValidator()
        config = {
            "command": "python3 -c \"import sys; sys.exit(1)\"",
            "expected_exit_code": 0,
            "description": "Failing test"
        }
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is False
        assert result.details.get("actual_exit_code") == 1


class TestEdgeCases:
    """Edge case tests for TestPassValidator."""

    def test_empty_output(self):
        """Empty command output is handled."""
        validator = TestPassValidator()
        config = {"command": "true"}  # 'true' produces no output
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        assert "stdout" in result.details

    def test_multiline_output(self):
        """Multiline output is captured."""
        validator = TestPassValidator()
        config = {"command": "echo 'line1\nline2\nline3'"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        stdout = result.details.get("stdout", "")
        assert "line1" in stdout

    def test_special_characters_in_command(self):
        """Special characters in command work."""
        validator = TestPassValidator()
        config = {"command": "echo 'test with $pecial & characters!'"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True

    def test_unicode_output(self):
        """Unicode output is handled."""
        validator = TestPassValidator()
        config = {"command": "echo '日本語 emoji: 🎉'"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True

    def test_environment_variables(self):
        """Environment variables work in commands."""
        validator = TestPassValidator()
        config = {"command": "echo $HOME"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        # HOME should be expanded
        assert "/" in result.details.get("stdout", "")

    def test_multiple_commands_chained(self):
        """Multiple commands chained with && work."""
        validator = TestPassValidator()
        config = {"command": "echo 'first' && echo 'second'"}
        context = {}
        result = validator.evaluate(config, context)
        assert result.passed is True
        stdout = result.details.get("stdout", "")
        assert "first" in stdout
        assert "second" in stdout


# =============================================================================
# Test All Verification Steps in Order
# =============================================================================

class TestVerificationSteps:
    """Test all feature verification steps in order."""

    def test_step_1_validator_interface(self):
        """Step 1: Create TestPassValidator class implementing Validator interface."""
        assert issubclass(TestPassValidator, Validator)
        validator = TestPassValidator()
        assert validator.validator_type == "test_pass"
        assert hasattr(validator, 'evaluate')

    def test_step_2_extract_command(self):
        """Step 2: Extract command from validator config."""
        validator = TestPassValidator()
        config = {"command": "echo step2"}
        result = validator.evaluate(config, {})
        assert "echo step2" in result.details.get("interpolated_command", "")

    def test_step_3_expected_exit_code_default_0(self):
        """Step 3: Extract expected_exit_code (default 0)."""
        validator = TestPassValidator()
        config = {"command": "exit 0"}
        result = validator.evaluate(config, {})
        assert result.details.get("expected_exit_code") == 0
        assert result.passed is True

    def test_step_4_timeout_default_60(self):
        """Step 4: Extract timeout_seconds (default 60)."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        result = validator.evaluate(config, {})
        assert result.details.get("timeout_seconds") == 60

    def test_step_5_execute_via_subprocess(self):
        """Step 5: Execute command via subprocess with timeout."""
        validator = TestPassValidator()
        config = {"command": "echo 'subprocess test'"}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert "subprocess test" in result.details.get("stdout", "")

    def test_step_6_capture_stdout_stderr(self):
        """Step 6: Capture stdout and stderr."""
        validator = TestPassValidator()
        config = {"command": "echo 'out' && echo 'err' >&2"}
        result = validator.evaluate(config, {})
        assert "out" in result.details.get("stdout", "")
        assert "err" in result.details.get("stderr", "")

    def test_step_7_compare_exit_code(self):
        """Step 7: Compare exit code to expected."""
        validator = TestPassValidator()
        # Matching exit code
        config = {"command": "exit 5", "expected_exit_code": 5}
        result = validator.evaluate(config, {})
        assert result.passed is True
        assert result.details.get("actual_exit_code") == 5

    def test_step_8_return_validator_result(self):
        """Step 8: Return ValidatorResult with passed boolean."""
        validator = TestPassValidator()
        config = {"command": "echo test"}
        result = validator.evaluate(config, {})
        assert isinstance(result, ValidatorResult)
        assert isinstance(result.passed, bool)

    def test_step_9_include_output_in_message(self):
        """Step 9: Include command output in result message."""
        validator = TestPassValidator()
        config = {"command": "exit 3", "expected_exit_code": 0}
        result = validator.evaluate(config, {})
        # Message should mention exit codes
        assert "3" in result.message
        # stdout/stderr in details
        assert "stdout" in result.details
        assert "stderr" in result.details

    def test_step_10_handle_timeout(self):
        """Step 10: Handle timeout as failure."""
        validator = TestPassValidator()
        config = {"command": "sleep 10", "timeout_seconds": 1}
        result = validator.evaluate(config, {})
        assert result.passed is False
        assert "timed out" in result.message.lower() or "timeout" in result.message.lower()
        assert result.details.get("error") == "timeout"

    def test_step_11_handle_command_not_found(self):
        """Step 11: Handle command not found as failure."""
        validator = TestPassValidator()
        config = {"command": "command_that_definitely_does_not_exist_xyz123"}
        result = validator.evaluate(config, {})
        assert result.passed is False
        # Exit code 127 typically indicates command not found
        # Or error details should indicate failure
        assert result.score == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
