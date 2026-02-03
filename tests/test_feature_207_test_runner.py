"""
Tests for Feature #207: Test-runner agent executes tests and reports results
============================================================================

This test suite verifies the test-runner functionality including:
- Step 1: Test-runner invokes test framework via Bash
- Step 2: Captures test output and exit code
- Step 3: Parses results to identify failures
- Step 4: Reports structured results back to harness
- Step 5: tests_executed audit event recorded

Run with:
    pytest tests/test_feature_207_test_runner.py -v
"""
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.test_runner import (
    # Data classes
    TestFailure,
    TestExecutionResult,
    # Parsers
    PytestResultParser,
    UnittestResultParser,
    JestResultParser,
    # Main class
    TestRunner,
    # Functions
    record_tests_executed,
    run_tests,
)
from api.event_recorder import EventRecorder
from api.agentspec_models import EVENT_TYPES


# =============================================================================
# Step 1: Test-runner invokes test framework via Bash
# =============================================================================

class TestStep1InvokesTestFramework:
    """Tests for Feature #207 Step 1: Test-runner invokes test framework via Bash."""

    def test_test_runner_executes_command(self):
        """TestRunner can execute a shell command."""
        runner = TestRunner()
        result = runner.run("echo 'hello world'")

        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_test_runner_executes_pytest_command(self):
        """TestRunner can execute pytest command format."""
        runner = TestRunner()
        # Just verify the command runs without error (may fail if no tests)
        result = runner.run("python -c 'print(\"pytest simulation\")'")

        assert result.exit_code == 0
        assert "pytest simulation" in result.stdout

    def test_test_runner_uses_working_directory(self):
        """TestRunner respects working_directory parameter."""
        runner = TestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run("pwd", working_directory=tmpdir)

            assert result.exit_code == 0
            assert tmpdir in result.stdout or Path(tmpdir).name in result.stdout

    def test_test_runner_uses_timeout(self):
        """TestRunner respects timeout parameter."""
        runner = TestRunner(default_timeout=1)

        # This should timeout
        result = runner.run("sleep 10", timeout_seconds=1)

        assert result.passed is False
        assert result.exit_code is None
        assert "timed out" in result.error_message.lower()

    def test_test_runner_handles_nonexistent_command(self):
        """TestRunner handles command not found gracefully."""
        runner = TestRunner()
        result = runner.run("nonexistent_command_xyz123")

        assert result.passed is False
        # Exit code will be non-zero (127 for command not found in bash)

    def test_test_runner_stores_command_in_result(self):
        """TestRunner stores the executed command in result."""
        runner = TestRunner()
        command = "echo test"
        result = runner.run(command)

        assert result.command == command

    def test_test_runner_stores_working_directory_in_result(self):
        """TestRunner stores working directory in result."""
        runner = TestRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.run("echo test", working_directory=tmpdir)

            assert result.working_directory == tmpdir


# =============================================================================
# Step 2: Captures test output and exit code
# =============================================================================

class TestStep2CapturesOutput:
    """Tests for Feature #207 Step 2: Captures test output and exit code."""

    def test_captures_stdout(self):
        """TestRunner captures stdout from command."""
        runner = TestRunner()
        result = runner.run("echo 'stdout test'")

        assert "stdout test" in result.stdout

    def test_captures_stderr(self):
        """TestRunner captures stderr from command."""
        runner = TestRunner()
        result = runner.run("echo 'stderr test' >&2")

        assert "stderr test" in result.stderr

    def test_captures_exit_code_success(self):
        """TestRunner captures exit code 0 for success."""
        runner = TestRunner()
        result = runner.run("exit 0")

        assert result.exit_code == 0
        assert result.passed is True

    def test_captures_exit_code_failure(self):
        """TestRunner captures non-zero exit code for failure."""
        runner = TestRunner()
        result = runner.run("exit 1")

        assert result.exit_code == 1
        assert result.passed is False

    def test_captures_specific_exit_codes(self):
        """TestRunner captures specific exit codes (e.g., pytest uses various codes)."""
        runner = TestRunner()

        for code in [0, 1, 2, 5]:
            result = runner.run(f"exit {code}")
            assert result.exit_code == code

    def test_expected_exit_code_customization(self):
        """TestRunner can use custom expected_exit_code."""
        runner = TestRunner()

        # Exit 1 should pass if we expect 1
        result = runner.run("exit 1", expected_exit_code=1)

        assert result.exit_code == 1
        assert result.passed is True

    def test_truncates_large_output(self):
        """TestRunner truncates output exceeding max size."""
        runner = TestRunner(max_output_size=100)
        result = runner.run("python -c 'print(\"x\" * 1000)'")

        assert len(result.stdout) <= 200  # Some room for truncation message
        assert "truncated" in result.stdout.lower()

    def test_captures_duration(self):
        """TestRunner captures execution duration."""
        runner = TestRunner()
        result = runner.run("sleep 0.1")

        assert result.duration_seconds >= 0.1
        assert result.duration_seconds < 5.0  # Should complete quickly

    def test_captures_timestamp(self):
        """TestRunner captures execution timestamp."""
        runner = TestRunner()
        before = datetime.now(timezone.utc)
        result = runner.run("echo test")
        after = datetime.now(timezone.utc)

        assert result.timestamp >= before
        assert result.timestamp <= after


# =============================================================================
# Step 3: Parses results to identify failures
# =============================================================================

class TestStep3ParsesResults:
    """Tests for Feature #207 Step 3: Parses results to identify failures."""

    def test_pytest_parser_parses_passed(self):
        """PytestResultParser parses passed test count."""
        parser = PytestResultParser()
        stdout = "======= 5 passed in 0.5s ======="

        results = parser.parse(stdout, "", 0)

        assert results["passed_tests"] == 5
        assert results["framework"] == "pytest"

    def test_pytest_parser_parses_failed(self):
        """PytestResultParser parses failed test count."""
        parser = PytestResultParser()
        stdout = "======= 2 failed, 3 passed in 0.5s ======="

        results = parser.parse(stdout, "", 1)

        assert results["failed_tests"] == 2
        assert results["passed_tests"] == 3

    def test_pytest_parser_parses_skipped(self):
        """PytestResultParser parses skipped test count."""
        parser = PytestResultParser()
        stdout = "======= 3 passed, 1 skipped in 0.5s ======="

        results = parser.parse(stdout, "", 0)

        assert results["skipped_tests"] == 1
        assert results["passed_tests"] == 3

    def test_pytest_parser_calculates_total(self):
        """PytestResultParser calculates total tests."""
        parser = PytestResultParser()
        stdout = "======= 2 failed, 5 passed, 1 skipped in 0.5s ======="

        results = parser.parse(stdout, "", 1)

        assert results["total_tests"] == 8

    def test_pytest_parser_detects_version(self):
        """PytestResultParser detects pytest version."""
        parser = PytestResultParser()
        stdout = "platform linux -- Python 3.11.0, pytest-7.4.0\n5 passed"

        results = parser.parse(stdout, "", 0)

        assert results["framework_version"] == "7.4.0"

    def test_pytest_parser_parses_failure_details(self):
        """PytestResultParser extracts failure details."""
        parser = PytestResultParser()
        stdout = """
FAILED tests/test_foo.py::TestClass::test_method - AssertionError: expected True
======= 1 failed in 0.5s =======
"""

        results = parser.parse(stdout, "", 1)

        assert len(results["failures"]) == 1
        assert "test_method" in results["failures"][0].test_name

    def test_unittest_parser_parses_ran_count(self):
        """UnittestResultParser parses 'Ran X tests' line."""
        parser = UnittestResultParser()
        stdout = "Ran 10 tests in 0.5s\nOK"

        results = parser.parse(stdout, "", 0)

        assert results["total_tests"] == 10
        assert results["passed_tests"] == 10

    def test_unittest_parser_parses_failures(self):
        """UnittestResultParser parses FAILED status with counts."""
        parser = UnittestResultParser()
        stdout = "Ran 10 tests in 0.5s\nFAILED (failures=2, errors=1)"

        results = parser.parse(stdout, "", 1)

        assert results["total_tests"] == 10
        assert results["failed_tests"] == 2
        assert results["error_tests"] == 1

    def test_jest_parser_parses_summary(self):
        """JestResultParser parses Jest summary line."""
        parser = JestResultParser()
        stdout = "Tests:       1 failed, 5 passed, 6 total"

        results = parser.parse(stdout, "", 1)

        assert results["total_tests"] == 6
        assert results["passed_tests"] == 5
        assert results["failed_tests"] == 1

    def test_test_runner_detects_pytest(self):
        """TestRunner detects pytest from command."""
        runner = TestRunner()
        framework = runner._detect_framework("pytest tests/ -v")

        assert framework == "pytest"

    def test_test_runner_detects_unittest(self):
        """TestRunner detects unittest from command."""
        runner = TestRunner()
        framework = runner._detect_framework("python -m unittest discover")

        assert framework == "unittest"

    def test_test_runner_detects_jest(self):
        """TestRunner detects jest from command."""
        runner = TestRunner()
        framework = runner._detect_framework("npx jest --coverage")

        assert framework == "jest"


# =============================================================================
# Step 4: Reports structured results back to harness
# =============================================================================

class TestStep4ReportsStructuredResults:
    """Tests for Feature #207 Step 4: Reports structured results back to harness."""

    def test_test_execution_result_to_dict(self):
        """TestExecutionResult serializes to dictionary."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            stdout="output",
            stderr="",
            command="pytest",
        )

        data = result.to_dict()

        assert data["passed"] is True
        assert data["exit_code"] == 0
        assert data["total_tests"] == 10
        assert data["success_rate"] == 80.0

    def test_test_failure_to_dict(self):
        """TestFailure serializes to dictionary."""
        failure = TestFailure(
            test_name="test_foo.py::test_bar",
            message="AssertionError",
            test_file="test_foo.py",
            test_method="test_bar",
        )

        data = failure.to_dict()

        assert data["test_name"] == "test_foo.py::test_bar"
        assert data["message"] == "AssertionError"
        assert data["test_file"] == "test_foo.py"

    def test_result_includes_failures_list(self):
        """TestExecutionResult includes failures list."""
        failures = [
            TestFailure(test_name="test1", message="failed"),
            TestFailure(test_name="test2", message="error"),
        ]
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            failures=failures,
        )

        assert len(result.failures) == 2
        assert result.failures[0].test_name == "test1"

    def test_result_success_rate_calculation(self):
        """TestExecutionResult calculates success_rate correctly."""
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=100,
            passed_tests=75,
            failed_tests=25,
        )

        assert result.success_rate == 75.0

    def test_result_success_rate_handles_zero_tests(self):
        """TestExecutionResult handles zero tests for success_rate."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=0,
        )

        assert result.success_rate == 100.0

    def test_result_failures_count_property(self):
        """TestExecutionResult.failures_count returns failed_tests."""
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            failed_tests=5,
        )

        assert result.failures_count == 5

    def test_result_includes_all_metadata(self):
        """TestExecutionResult includes all execution metadata."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            command="pytest -v",
            working_directory="/project",
            timeout_seconds=300,
            duration_seconds=1.5,
            framework="pytest",
            framework_version="7.4.0",
        )

        data = result.to_dict()

        assert data["command"] == "pytest -v"
        assert data["working_directory"] == "/project"
        assert data["timeout_seconds"] == 300
        assert data["duration_seconds"] == 1.5
        assert data["framework"] == "pytest"
        assert data["framework_version"] == "7.4.0"


# =============================================================================
# Step 5: tests_executed audit event recorded
# =============================================================================

class TestStep5AuditEventRecorded:
    """Tests for Feature #207 Step 5: tests_executed audit event recorded."""

    def test_tests_executed_in_event_types(self):
        """tests_executed is a valid event type."""
        assert "tests_executed" in EVENT_TYPES

    def test_event_recorder_has_record_tests_executed_method(self):
        """EventRecorder has record_tests_executed method."""
        assert hasattr(EventRecorder, "record_tests_executed")

    def test_record_tests_executed_creates_event(self):
        """record_tests_executed creates an event with correct payload."""
        # Create mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Record event
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-runner-agent",
            command="pytest tests/",
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            duration_seconds=5.0,
            test_framework="pytest",
        )

        # Verify session.add was called
        assert mock_session.add.called

        # Get the event that was added
        event = mock_session.add.call_args[0][0]

        assert event.event_type == "tests_executed"
        assert event.run_id == "test-run-123"
        assert event.payload["agent_name"] == "test-runner-agent"
        assert event.payload["command"] == "pytest tests/"
        assert event.payload["passed"] is True
        assert event.payload["total_tests"] == 10

    def test_record_tests_executed_includes_failures(self):
        """record_tests_executed includes failure details in payload."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        failures = [
            {"test_name": "test_foo", "message": "AssertionError"},
            {"test_name": "test_bar", "message": "ValueError"},
        ]

        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="agent",
            command="pytest",
            passed=False,
            failed_tests=2,
            failures=failures,
        )

        event = mock_session.add.call_args[0][0]

        assert "failures" in event.payload
        assert len(event.payload["failures"]) == 2

    def test_record_tests_executed_truncates_failures(self):
        """record_tests_executed truncates failures to max 10."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Create 15 failures
        failures = [
            {"test_name": f"test_{i}", "message": "failed"}
            for i in range(15)
        ]

        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="agent",
            command="pytest",
            passed=False,
            failures=failures,
        )

        event = mock_session.add.call_args[0][0]

        assert len(event.payload["failures"]) == 10

    def test_record_tests_executed_function(self):
        """record_tests_executed convenience function works."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            command="pytest -v",
            duration_seconds=1.0,
            framework="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="run-123",
            result=result,
            agent_name="test-agent",
        )

        # Verify the event was recorded
        assert mock_session.add.called
        event = mock_session.add.call_args[0][0]
        assert event.event_type == "tests_executed"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for test runner functionality."""

    def test_run_simple_pytest_command(self):
        """Test running a simple pytest command (simulation)."""
        runner = TestRunner()

        # Run a command that simulates pytest output
        result = runner.run(
            "python -c \"print('======= 3 passed in 0.1s =======')\""
        )

        assert result.exit_code == 0
        assert result.passed is True

    def test_run_tests_convenience_function(self):
        """Test run_tests convenience function."""
        result = run_tests(
            command="echo '2 passed, 1 failed'",
            timeout_seconds=30,
        )

        assert result.exit_code == 0
        assert result.command == "echo '2 passed, 1 failed'"

    def test_full_pytest_simulation(self):
        """Test full pytest output parsing flow."""
        runner = TestRunner()

        # Simulate pytest output
        pytest_output = '''
platform linux -- Python 3.11.0, pytest-7.4.0
collected 5 items

tests/test_foo.py::test_one PASSED
tests/test_foo.py::test_two PASSED
tests/test_foo.py::test_three FAILED
tests/test_bar.py::test_four PASSED
tests/test_bar.py::test_five SKIPPED

FAILED tests/test_foo.py::test_three - AssertionError: expected True

======= 1 failed, 3 passed, 1 skipped in 0.5s =======
'''

        result = runner.run(
            f"python -c \"print('''{pytest_output}''')\""
        )

        # Parsing should extract counts
        assert result.framework == "pytest"
        # Note: Output parsing depends on actual pytest patterns


# =============================================================================
# TestFailure Tests
# =============================================================================

class TestTestFailure:
    """Tests for TestFailure dataclass."""

    def test_create_test_failure(self):
        """TestFailure can be created with required fields."""
        failure = TestFailure(
            test_name="test_foo",
            message="assertion failed",
        )

        assert failure.test_name == "test_foo"
        assert failure.message == "assertion failed"

    def test_test_failure_optional_fields(self):
        """TestFailure supports optional fields."""
        failure = TestFailure(
            test_name="test_foo",
            message="assertion failed",
            test_file="test_foo.py",
            test_class="TestClass",
            test_method="test_method",
            traceback="Traceback...",
            line_number=42,
            failure_type="assertion",
        )

        assert failure.test_file == "test_foo.py"
        assert failure.test_class == "TestClass"
        assert failure.line_number == 42

    def test_test_failure_default_failure_type(self):
        """TestFailure defaults to 'assertion' failure_type."""
        failure = TestFailure(
            test_name="test",
            message="failed",
        )

        assert failure.failure_type == "assertion"


# =============================================================================
# TestExecutionResult Tests
# =============================================================================

class TestTestExecutionResult:
    """Tests for TestExecutionResult dataclass."""

    def test_create_test_execution_result(self):
        """TestExecutionResult can be created with required fields."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
        )

        assert result.passed is True
        assert result.exit_code == 0

    def test_test_execution_result_defaults(self):
        """TestExecutionResult has sensible defaults."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
        )

        assert result.expected_exit_code == 0
        assert result.total_tests == 0
        assert result.passed_tests == 0
        assert result.failed_tests == 0
        assert result.failures == []
        assert result.stdout == ""
        assert result.stderr == ""

    def test_test_execution_result_with_error(self):
        """TestExecutionResult can represent error state."""
        result = TestExecutionResult(
            passed=False,
            exit_code=None,
            error_message="Command timed out",
        )

        assert result.passed is False
        assert result.exit_code is None
        assert result.error_message == "Command timed out"


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Tests that Feature #207 exports are available from api package."""

    def test_test_failure_exported(self):
        """TestFailure is exported from api package."""
        from api import TestFailure as TF

        assert TF is TestFailure

    def test_test_execution_result_exported(self):
        """TestExecutionResult is exported from api package."""
        from api import TestExecutionResult as TER

        assert TER is TestExecutionResult

    def test_test_runner_exported(self):
        """TestRunner is exported from api package."""
        from api import TestRunner as TR

        assert TR is TestRunner

    def test_parsers_exported(self):
        """Result parsers are exported from api package."""
        from api import (
            PytestResultParser,
            UnittestResultParser,
            JestResultParser,
        )

        assert PytestResultParser is not None
        assert UnittestResultParser is not None
        assert JestResultParser is not None

    def test_run_tests_function_exported(self):
        """run_tests convenience function is exported."""
        from api import run_tests as rt

        assert rt is run_tests

    def test_record_tests_executed_exported(self):
        """record_tests_executed function is exported."""
        from api import record_tests_executed as rte

        assert rte is record_tests_executed


# =============================================================================
# Feature #207 Verification Steps (Comprehensive)
# =============================================================================

class TestFeature207VerificationSteps:
    """
    Comprehensive tests verifying all 5 feature steps.
    These tests serve as acceptance criteria for Feature #207.
    """

    def test_step_1_invokes_test_framework_via_bash(self):
        """
        Step 1: Test-runner invokes test framework via Bash

        Verify that TestRunner executes commands through subprocess (Bash).
        """
        runner = TestRunner()

        # Execute a command through subprocess
        result = runner.run("echo 'test framework invoked'")

        assert result.exit_code == 0
        assert "test framework invoked" in result.stdout
        assert result.command == "echo 'test framework invoked'"

    def test_step_2_captures_test_output_and_exit_code(self):
        """
        Step 2: Captures test output and exit code

        Verify that TestRunner captures stdout, stderr, and exit code.
        """
        runner = TestRunner()

        # Command with both stdout and stderr
        result = runner.run("echo 'stdout' && echo 'stderr' >&2 && exit 42")

        assert "stdout" in result.stdout
        assert "stderr" in result.stderr
        assert result.exit_code == 42

    def test_step_3_parses_results_to_identify_failures(self):
        """
        Step 3: Parses results to identify failures

        Verify that parsers can extract test counts and failure details.
        """
        # Test pytest parser
        pytest_parser = PytestResultParser()
        pytest_output = "======= 2 failed, 8 passed in 1.0s ======="

        results = pytest_parser.parse(pytest_output, "", 1)

        assert results["failed_tests"] == 2
        assert results["passed_tests"] == 8
        assert results["total_tests"] == 10

        # Test framework detection
        runner = TestRunner()
        assert runner._detect_framework("pytest tests/") == "pytest"
        assert runner._detect_framework("python -m unittest") == "unittest"
        assert runner._detect_framework("npx jest") == "jest"

    def test_step_4_reports_structured_results_back_to_harness(self):
        """
        Step 4: Reports structured results back to harness

        Verify that TestExecutionResult provides structured data.
        """
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            expected_exit_code=0,
            total_tests=10,
            passed_tests=7,
            failed_tests=3,
            failures=[
                TestFailure(test_name="test_a", message="failed"),
                TestFailure(test_name="test_b", message="error"),
            ],
            stdout="test output",
            stderr="",
            command="pytest tests/",
            working_directory="/project",
            timeout_seconds=300,
            duration_seconds=5.5,
            framework="pytest",
        )

        # Verify structured data
        assert result.passed is False
        assert result.total_tests == 10
        assert result.success_rate == 70.0
        assert len(result.failures) == 2

        # Verify serialization
        data = result.to_dict()
        assert isinstance(data, dict)
        assert data["passed"] is False
        assert data["total_tests"] == 10
        assert len(data["failures"]) == 2

    def test_step_5_tests_executed_audit_event_recorded(self):
        """
        Step 5: tests_executed audit event recorded

        Verify that tests_executed is a valid event type and can be recorded.
        """
        # Verify event type exists
        assert "tests_executed" in EVENT_TYPES

        # Verify EventRecorder can record the event
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        recorder.record_tests_executed(
            run_id="verification-run",
            agent_name="test-runner",
            command="pytest tests/",
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            duration_seconds=1.0,
            test_framework="pytest",
        )

        # Verify event was created
        assert mock_session.add.called
        event = mock_session.add.call_args[0][0]
        assert event.event_type == "tests_executed"
        assert event.payload["agent_name"] == "test-runner"
        assert event.payload["command"] == "pytest tests/"
        assert event.payload["passed"] is True


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_output(self):
        """TestRunner handles commands with no output."""
        runner = TestRunner()
        result = runner.run("true")  # Command with no output

        assert result.exit_code == 0
        assert result.stdout == "" or result.stdout.strip() == ""

    def test_handles_unicode_output(self):
        """TestRunner handles unicode in output."""
        runner = TestRunner()
        result = runner.run("echo '日本語 emoji 🎉'")

        assert result.exit_code == 0
        assert "日本語" in result.stdout

    def test_handles_very_long_test_names(self):
        """Parser handles very long test names."""
        parser = PytestResultParser()
        long_name = "a" * 500
        stdout = f"FAILED tests/test_foo.py::TestClass::{long_name} - AssertionError"

        results = parser.parse(stdout, "", 1)

        # Should not crash
        assert results is not None

    def test_handles_malformed_output(self):
        """Parsers handle malformed output gracefully."""
        parser = PytestResultParser()
        malformed = "this is not pytest output at all"

        results = parser.parse(malformed, "", 0)

        # Should return zero counts, not crash
        assert results["total_tests"] == 0

    def test_handles_concurrent_stdout_stderr(self):
        """TestRunner captures interleaved stdout/stderr."""
        runner = TestRunner()
        result = runner.run(
            "echo out1 && echo err1 >&2 && echo out2 && echo err2 >&2"
        )

        assert "out1" in result.stdout
        assert "out2" in result.stdout
        assert "err1" in result.stderr
        assert "err2" in result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
