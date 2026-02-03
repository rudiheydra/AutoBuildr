"""
Test Runner Module
==================

Implements test execution and result reporting for the test-runner agent.

Feature #207: Test-runner agent executes tests and reports results

This module provides:
- TestRunner class: Invokes test framework via Bash, captures output and exit code
- TestResult dataclass: Structured test results with pass/fail status
- TestExecutionResult: Aggregated results from a test run
- Result parsing to identify individual test failures
- tests_executed audit event recording

The TestRunner is the core execution engine used by the test-runner agent to:
1. Execute tests via subprocess (pytest, unittest, jest, etc.)
2. Capture stdout, stderr, and exit code
3. Parse results to identify failures
4. Report structured results back to the harness
5. Record tests_executed audit events

Usage:
    from api.test_runner import TestRunner, TestResult

    # Create test runner
    runner = TestRunner()

    # Execute tests
    result = runner.run(
        command="pytest tests/ -v",
        working_directory="/path/to/project",
        timeout_seconds=300,
    )

    if result.passed:
        print(f"All {result.total_tests} tests passed!")
    else:
        print(f"Failed: {result.failures_count} / {result.total_tests}")
        for failure in result.failures:
            print(f"  - {failure.test_name}: {failure.message}")
"""
from __future__ import annotations

import logging
import re
import subprocess
import shlex
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from api.event_recorder import EventRecorder

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes for Test Results (Feature #207 Step 3)
# =============================================================================

@dataclass
class TestFailure:
    """
    Represents a single test failure.

    Attributes:
        test_name: Fully qualified name of the failed test
        test_file: File containing the test (if identifiable)
        test_class: Test class name (if applicable)
        test_method: Test method name
        message: Error message or failure description
        traceback: Full traceback (if available)
        line_number: Line number where failure occurred (if identifiable)
        failure_type: Type of failure (assertion, error, timeout, etc.)
    """
    test_name: str
    message: str
    test_file: str | None = None
    test_class: str | None = None
    test_method: str | None = None
    traceback: str | None = None
    line_number: int | None = None
    failure_type: str = "assertion"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_name": self.test_name,
            "message": self.message,
            "test_file": self.test_file,
            "test_class": self.test_class,
            "test_method": self.test_method,
            "traceback": self.traceback,
            "line_number": self.line_number,
            "failure_type": self.failure_type,
        }


@dataclass
class TestExecutionResult:
    """
    Result of a test execution run.

    Feature #207: Test-runner executes tests and reports pass/fail status.

    Attributes:
        passed: True if all tests passed (exit code matches expected)
        exit_code: Process exit code from test framework
        expected_exit_code: Expected exit code (default 0)
        total_tests: Total number of tests discovered/run
        passed_tests: Number of tests that passed
        failed_tests: Number of tests that failed
        skipped_tests: Number of tests that were skipped
        error_tests: Number of tests that errored
        failures: List of individual test failures with details
        stdout: Raw stdout output from test command
        stderr: Raw stderr output from test command
        command: Command that was executed
        working_directory: Working directory for execution
        timeout_seconds: Timeout used for execution
        duration_seconds: How long the execution took
        framework: Detected test framework (pytest, unittest, jest, etc.)
        framework_version: Version of test framework (if detectable)
        timestamp: When the test run started
    """
    passed: bool
    exit_code: int | None
    expected_exit_code: int = 0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    error_tests: int = 0
    failures: list[TestFailure] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    command: str = ""
    working_directory: str | None = None
    timeout_seconds: int = 300
    duration_seconds: float = 0.0
    framework: str | None = None
    framework_version: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: str | None = None

    @property
    def failures_count(self) -> int:
        """Total count of failed tests."""
        return self.failed_tests

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_tests == 0:
            return 100.0
        return (self.passed_tests / self.total_tests) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "exit_code": self.exit_code,
            "expected_exit_code": self.expected_exit_code,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "error_tests": self.error_tests,
            "failures": [f.to_dict() for f in self.failures],
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": self.command,
            "working_directory": self.working_directory,
            "timeout_seconds": self.timeout_seconds,
            "duration_seconds": self.duration_seconds,
            "framework": self.framework,
            "framework_version": self.framework_version,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "error_message": self.error_message,
            "success_rate": self.success_rate,
        }


# =============================================================================
# Result Parsers (Feature #207 Step 3)
# =============================================================================

class PytestResultParser:
    """
    Parser for pytest output to extract test results.

    Parses pytest verbose output to identify:
    - Total tests run
    - Passed, failed, skipped, error counts
    - Individual failure details
    """

    # Pattern to match pytest summary line: "== 5 passed, 2 failed, 1 skipped =="
    SUMMARY_PATTERN = re.compile(
        r"=+\s*"
        r"(?:(?P<failed>\d+)\s+failed)?\s*,?\s*"
        r"(?:(?P<passed>\d+)\s+passed)?\s*,?\s*"
        r"(?:(?P<skipped>\d+)\s+skipped)?\s*,?\s*"
        r"(?:(?P<deselected>\d+)\s+deselected)?\s*,?\s*"
        r"(?:(?P<error>\d+)\s+error)?\s*,?\s*"
        r"(?:(?P<warning>\d+)\s+warnings?)?\s*",
        re.IGNORECASE
    )

    # Alternative simple patterns
    PASSED_PATTERN = re.compile(r"(\d+)\s+passed", re.IGNORECASE)
    FAILED_PATTERN = re.compile(r"(\d+)\s+failed", re.IGNORECASE)
    SKIPPED_PATTERN = re.compile(r"(\d+)\s+skipped", re.IGNORECASE)
    ERROR_PATTERN = re.compile(r"(\d+)\s+errors?", re.IGNORECASE)

    # Pattern to match individual test result lines
    # e.g., "tests/test_foo.py::TestClass::test_method PASSED"
    TEST_LINE_PATTERN = re.compile(
        r"^(?P<file>[\w/._-]+\.py)::(?:(?P<class>[\w_]+)::)?(?P<method>[\w_]+)\s+(?P<status>PASSED|FAILED|SKIPPED|ERROR)",
        re.MULTILINE
    )

    # Pattern to match failure headers
    # e.g., "FAILED tests/test_foo.py::TestClass::test_method - AssertionError"
    FAILURE_HEADER_PATTERN = re.compile(
        r"^FAILED\s+(?P<file>[\w/._-]+\.py)::(?:(?P<class>[\w_]+)::)?(?P<method>[\w_]+)\s*-?\s*(?P<message>.*)?$",
        re.MULTILINE
    )

    # Pattern for short test summary
    SHORT_SUMMARY_PATTERN = re.compile(
        r"^FAILED\s+(?P<test_path>\S+)\s+-\s+(?P<message>.*)$",
        re.MULTILINE
    )

    def parse(self, stdout: str, stderr: str, exit_code: int) -> dict[str, Any]:
        """
        Parse pytest output to extract structured results.

        Args:
            stdout: stdout from pytest execution
            stderr: stderr from pytest execution
            exit_code: Exit code from pytest

        Returns:
            Dictionary with parsed test results
        """
        combined_output = stdout + "\n" + stderr
        results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "failures": [],
            "framework": "pytest",
            "framework_version": self._detect_version(combined_output),
        }

        # Try to parse summary counts
        passed_match = self.PASSED_PATTERN.search(combined_output)
        failed_match = self.FAILED_PATTERN.search(combined_output)
        skipped_match = self.SKIPPED_PATTERN.search(combined_output)
        error_match = self.ERROR_PATTERN.search(combined_output)

        if passed_match:
            results["passed_tests"] = int(passed_match.group(1))
        if failed_match:
            results["failed_tests"] = int(failed_match.group(1))
        if skipped_match:
            results["skipped_tests"] = int(skipped_match.group(1))
        if error_match:
            results["error_tests"] = int(error_match.group(1))

        results["total_tests"] = (
            results["passed_tests"]
            + results["failed_tests"]
            + results["skipped_tests"]
            + results["error_tests"]
        )

        # Parse individual failure details from short test summary
        failures = self._parse_failures(combined_output)
        results["failures"] = failures

        return results

    def _detect_version(self, output: str) -> str | None:
        """Detect pytest version from output."""
        # Pattern: "pytest-7.4.0" or "platform linux -- Python 3.11.0, pytest-7.4.0"
        match = re.search(r"pytest-(\d+\.\d+\.\d+)", output)
        if match:
            return match.group(1)
        return None

    def _parse_failures(self, output: str) -> list[TestFailure]:
        """Parse individual test failures from pytest output."""
        failures = []

        # Try to find short test summary section
        for match in self.SHORT_SUMMARY_PATTERN.finditer(output):
            test_path = match.group("test_path")
            message = match.group("message")

            # Parse test path (file::class::method or file::method)
            parts = test_path.split("::")
            test_file = parts[0] if len(parts) > 0 else None
            test_class = parts[1] if len(parts) > 2 else None
            test_method = parts[-1] if len(parts) > 1 else None

            failure = TestFailure(
                test_name=test_path,
                message=message or "Test failed",
                test_file=test_file,
                test_class=test_class,
                test_method=test_method,
                failure_type="assertion" if "assert" in message.lower() else "error",
            )
            failures.append(failure)

        # Also check FAILURE_HEADER_PATTERN as backup
        if not failures:
            for match in self.FAILURE_HEADER_PATTERN.finditer(output):
                test_file = match.group("file")
                test_class = match.group("class")
                test_method = match.group("method")
                message = match.group("message") or "Test failed"

                test_name = f"{test_file}::{test_class}::{test_method}" if test_class else f"{test_file}::{test_method}"

                failure = TestFailure(
                    test_name=test_name,
                    message=message,
                    test_file=test_file,
                    test_class=test_class,
                    test_method=test_method,
                )
                failures.append(failure)

        return failures


class UnittestResultParser:
    """
    Parser for Python unittest output to extract test results.

    Parses unittest verbose output to identify:
    - Total tests run
    - Passed, failed, error, skipped counts
    - Individual failure details
    """

    # Pattern to match unittest summary: "Ran 10 tests in 0.5s"
    RAN_PATTERN = re.compile(r"Ran\s+(\d+)\s+tests?\s+in\s+([\d.]+)s", re.IGNORECASE)

    # Pattern to match OK status
    OK_PATTERN = re.compile(r"^OK\s*(\(.*\))?$", re.MULTILINE | re.IGNORECASE)

    # Pattern to match FAILED status
    FAILED_STATUS_PATTERN = re.compile(
        r"^FAILED\s*\((?:failures=(?P<failures>\d+))?\s*,?\s*(?:errors=(?P<errors>\d+))?\)",
        re.MULTILINE | re.IGNORECASE
    )

    # Pattern to match test failure header
    # e.g., "FAIL: test_method (test_module.TestClass)"
    FAIL_HEADER_PATTERN = re.compile(
        r"^(?P<type>FAIL|ERROR):\s+(?P<method>\w+)\s+\((?P<module>[\w.]+)\.(?P<class>\w+)\)",
        re.MULTILINE
    )

    def parse(self, stdout: str, stderr: str, exit_code: int) -> dict[str, Any]:
        """
        Parse unittest output to extract structured results.

        Args:
            stdout: stdout from unittest execution
            stderr: stderr from unittest execution
            exit_code: Exit code from unittest

        Returns:
            Dictionary with parsed test results
        """
        combined_output = stdout + "\n" + stderr
        results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "failures": [],
            "framework": "unittest",
            "framework_version": None,
        }

        # Parse "Ran X tests in Y.Ys"
        ran_match = self.RAN_PATTERN.search(combined_output)
        if ran_match:
            results["total_tests"] = int(ran_match.group(1))

        # Check for OK status
        if self.OK_PATTERN.search(combined_output):
            results["passed_tests"] = results["total_tests"]
        else:
            # Check for FAILED status
            failed_match = self.FAILED_STATUS_PATTERN.search(combined_output)
            if failed_match:
                failures = int(failed_match.group("failures") or 0)
                errors = int(failed_match.group("errors") or 0)
                results["failed_tests"] = failures
                results["error_tests"] = errors
                results["passed_tests"] = (
                    results["total_tests"] - failures - errors
                )

        # Parse individual failures
        failures = self._parse_failures(combined_output)
        results["failures"] = failures

        return results

    def _parse_failures(self, output: str) -> list[TestFailure]:
        """Parse individual test failures from unittest output."""
        failures = []

        for match in self.FAIL_HEADER_PATTERN.finditer(output):
            failure_type = match.group("type").lower()
            method = match.group("method")
            module = match.group("module")
            test_class = match.group("class")

            test_name = f"{module}.{test_class}.{method}"

            failure = TestFailure(
                test_name=test_name,
                message=f"{failure_type}: {test_name}",
                test_class=test_class,
                test_method=method,
                failure_type="error" if failure_type == "error" else "assertion",
            )
            failures.append(failure)

        return failures


class JestResultParser:
    """Parser for Jest (JavaScript) test output."""

    # Pattern to match Jest summary
    # e.g., "Tests:       1 failed, 5 passed, 6 total"
    TESTS_PATTERN = re.compile(
        r"Tests:\s+(?:(\d+)\s+failed,\s+)?(?:(\d+)\s+skipped,\s+)?(?:(\d+)\s+passed,\s+)?(\d+)\s+total",
        re.IGNORECASE
    )

    # Pattern for individual test failure
    FAIL_PATTERN = re.compile(
        r"FAIL\s+(\S+)",
        re.MULTILINE
    )

    def parse(self, stdout: str, stderr: str, exit_code: int) -> dict[str, Any]:
        """Parse Jest output."""
        combined_output = stdout + "\n" + stderr
        results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "failures": [],
            "framework": "jest",
            "framework_version": None,
        }

        tests_match = self.TESTS_PATTERN.search(combined_output)
        if tests_match:
            results["failed_tests"] = int(tests_match.group(1) or 0)
            results["skipped_tests"] = int(tests_match.group(2) or 0)
            results["passed_tests"] = int(tests_match.group(3) or 0)
            results["total_tests"] = int(tests_match.group(4) or 0)

        # Parse failed file paths
        for match in self.FAIL_PATTERN.finditer(combined_output):
            test_file = match.group(1)
            failure = TestFailure(
                test_name=test_file,
                message="Test file failed",
                test_file=test_file,
            )
            results["failures"].append(failure)

        return results


# =============================================================================
# Test Runner Class (Feature #207 Steps 1-4)
# =============================================================================

class TestRunner:
    """
    Test execution engine for the test-runner agent.

    Feature #207: Test-runner agent executes tests and reports results

    This class implements:
    - Step 1: Test-runner invokes test framework via Bash
    - Step 2: Captures test output and exit code
    - Step 3: Parses results to identify failures
    - Step 4: Reports structured results back to harness

    The TestRunner is framework-agnostic and can execute any test command.
    It uses specialized parsers to extract structured results from common
    frameworks (pytest, unittest, jest).

    Usage:
        runner = TestRunner()
        result = runner.run("pytest tests/ -v")

        if result.passed:
            print("All tests passed!")
        else:
            for failure in result.failures:
                print(f"FAILED: {failure.test_name}")
    """

    # Mapping of framework detection patterns to parsers
    FRAMEWORK_PARSERS: dict[str, type] = {
        "pytest": PytestResultParser,
        "unittest": UnittestResultParser,
        "jest": JestResultParser,
    }

    # Keywords in command to detect framework
    FRAMEWORK_KEYWORDS: dict[str, str] = {
        "pytest": "pytest",
        "py.test": "pytest",
        "python -m pytest": "pytest",
        "unittest": "unittest",
        "python -m unittest": "unittest",
        "jest": "jest",
        "npm test": "jest",  # Common alias
        "npx jest": "jest",
    }

    def __init__(
        self,
        default_timeout: int = 300,
        max_output_size: int = 32768,
    ):
        """
        Initialize the TestRunner.

        Args:
            default_timeout: Default timeout for test execution in seconds
            max_output_size: Maximum output size to capture (bytes)
        """
        self.default_timeout = default_timeout
        self.max_output_size = max_output_size
        self._logger = logging.getLogger(__name__)

    def run(
        self,
        command: str,
        working_directory: str | Path | None = None,
        timeout_seconds: int | None = None,
        expected_exit_code: int = 0,
        env: dict[str, str] | None = None,
    ) -> TestExecutionResult:
        """
        Execute tests and return structured results.

        Feature #207 Step 1: Test-runner invokes test framework via Bash
        Feature #207 Step 2: Captures test output and exit code

        Args:
            command: Test command to execute (e.g., "pytest tests/ -v")
            working_directory: Working directory for command execution
            timeout_seconds: Timeout in seconds (uses default if not specified)
            expected_exit_code: Expected exit code for "passed" status (default 0)
            env: Additional environment variables

        Returns:
            TestExecutionResult with all execution details
        """
        timeout = timeout_seconds or self.default_timeout
        cwd = str(working_directory) if working_directory else None
        start_time = datetime.now(timezone.utc)

        self._logger.info(
            "TestRunner.run: command='%s', cwd='%s', timeout=%ds",
            command, cwd, timeout
        )

        try:
            # Step 1: Invoke test framework via Bash (subprocess)
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )

            # Step 2: Capture test output and exit code
            stdout = self._truncate_output(result.stdout)
            stderr = self._truncate_output(result.stderr)
            exit_code = result.returncode
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            self._logger.info(
                "Test execution complete: exit_code=%d, duration=%.2fs",
                exit_code, duration
            )

            # Step 3: Parse results to identify failures
            parsed = self._parse_results(command, stdout, stderr, exit_code)

            # Step 4: Build structured result
            return TestExecutionResult(
                passed=exit_code == expected_exit_code,
                exit_code=exit_code,
                expected_exit_code=expected_exit_code,
                total_tests=parsed.get("total_tests", 0),
                passed_tests=parsed.get("passed_tests", 0),
                failed_tests=parsed.get("failed_tests", 0),
                skipped_tests=parsed.get("skipped_tests", 0),
                error_tests=parsed.get("error_tests", 0),
                failures=parsed.get("failures", []),
                stdout=stdout,
                stderr=stderr,
                command=command,
                working_directory=cwd,
                timeout_seconds=timeout,
                duration_seconds=duration,
                framework=parsed.get("framework"),
                framework_version=parsed.get("framework_version"),
                timestamp=start_time,
            )

        except subprocess.TimeoutExpired as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            stdout = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""

            self._logger.warning(
                "Test execution timed out after %ds", timeout
            )

            return TestExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                stdout=self._truncate_output(stdout),
                stderr=self._truncate_output(stderr),
                command=command,
                working_directory=cwd,
                timeout_seconds=timeout,
                duration_seconds=duration,
                timestamp=start_time,
                error_message=f"Test execution timed out after {timeout} seconds",
            )

        except FileNotFoundError as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            self._logger.error(
                "Command not found: %s", e.filename or command
            )

            return TestExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                stdout="",
                stderr=str(e),
                command=command,
                working_directory=cwd,
                timeout_seconds=timeout,
                duration_seconds=duration,
                timestamp=start_time,
                error_message=f"Command not found: {e.filename or command}",
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            self._logger.exception(
                "Unexpected error during test execution"
            )

            return TestExecutionResult(
                passed=False,
                exit_code=None,
                expected_exit_code=expected_exit_code,
                stdout="",
                stderr=str(e),
                command=command,
                working_directory=cwd,
                timeout_seconds=timeout,
                duration_seconds=duration,
                timestamp=start_time,
                error_message=f"Unexpected error: {e}",
            )

    def _truncate_output(self, output: str) -> str:
        """Truncate output if it exceeds max size."""
        if len(output) > self.max_output_size:
            return "...(truncated)...\n" + output[-self.max_output_size:]
        return output

    def _detect_framework(self, command: str) -> str | None:
        """
        Detect the test framework from the command.

        Args:
            command: Test command

        Returns:
            Framework name or None if unknown
        """
        command_lower = command.lower()

        for keyword, framework in self.FRAMEWORK_KEYWORDS.items():
            if keyword in command_lower:
                return framework

        return None

    def _parse_results(
        self,
        command: str,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> dict[str, Any]:
        """
        Parse test output to extract structured results.

        Feature #207 Step 3: Parses results to identify failures

        Args:
            command: Test command that was executed
            stdout: Command stdout
            stderr: Command stderr
            exit_code: Command exit code

        Returns:
            Dictionary with parsed test results
        """
        # Detect framework
        framework = self._detect_framework(command)

        # Get appropriate parser
        parser_class = self.FRAMEWORK_PARSERS.get(framework) if framework else None

        if parser_class:
            try:
                parser = parser_class()
                return parser.parse(stdout, stderr, exit_code)
            except Exception as e:
                self._logger.warning(
                    "Failed to parse %s output: %s",
                    framework, e
                )

        # Fallback: basic parsing based on exit code
        return self._basic_parse(stdout, stderr, exit_code, framework)

    def _basic_parse(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        framework: str | None,
    ) -> dict[str, Any]:
        """
        Basic fallback parsing when no specialized parser is available.

        Uses exit code and simple pattern matching for common test outputs.
        """
        passed = exit_code == 0
        combined = stdout + "\n" + stderr

        # Try to extract counts from common patterns
        total = 0
        passed_count = 0
        failed_count = 0

        # Common pattern: "X passed, Y failed"
        passed_match = re.search(r"(\d+)\s+passed", combined, re.IGNORECASE)
        failed_match = re.search(r"(\d+)\s+failed", combined, re.IGNORECASE)

        if passed_match:
            passed_count = int(passed_match.group(1))
        if failed_match:
            failed_count = int(failed_match.group(1))

        total = passed_count + failed_count

        return {
            "total_tests": total,
            "passed_tests": passed_count,
            "failed_tests": failed_count,
            "skipped_tests": 0,
            "error_tests": 0,
            "failures": [],
            "framework": framework,
            "framework_version": None,
        }


# =============================================================================
# Audit Event Recording (Feature #207 Step 5)
# =============================================================================

def record_tests_executed(
    recorder: "EventRecorder",
    run_id: str,
    result: TestExecutionResult,
    *,
    agent_name: str | None = None,
    spec_id: str | None = None,
    test_target: str | None = None,
) -> int:
    """
    Record a tests_executed audit event.

    Feature #207 Step 5: tests_executed audit event recorded

    This function records the test execution details to the audit trail
    for traceability and debugging.

    Args:
        recorder: EventRecorder instance
        run_id: Run ID for the event
        result: TestExecutionResult from test execution
        agent_name: Name of the test-runner agent
        spec_id: ID of the AgentSpec being tested
        test_target: What was being tested (e.g., "feature-123")

    Returns:
        Event ID
    """
    payload = {
        "passed": result.passed,
        "exit_code": result.exit_code,
        "total_tests": result.total_tests,
        "passed_tests": result.passed_tests,
        "failed_tests": result.failed_tests,
        "skipped_tests": result.skipped_tests,
        "error_tests": result.error_tests,
        "command": result.command,
        "duration_seconds": result.duration_seconds,
        "framework": result.framework,
    }

    if agent_name:
        payload["agent_name"] = agent_name
    if spec_id:
        payload["spec_id"] = spec_id
    if test_target:
        payload["test_target"] = test_target
    if result.error_message:
        payload["error_message"] = result.error_message

    # Include truncated failure details (keep payload small)
    if result.failures:
        failure_summaries = [
            {"test_name": f.test_name, "message": f.message[:200]}
            for f in result.failures[:10]  # Max 10 failures in event
        ]
        payload["failures"] = failure_summaries

    return recorder.record(run_id, "tests_executed", payload=payload)


# =============================================================================
# Convenience Functions
# =============================================================================

def run_tests(
    command: str,
    working_directory: str | Path | None = None,
    timeout_seconds: int = 300,
    expected_exit_code: int = 0,
) -> TestExecutionResult:
    """
    Convenience function to run tests.

    Creates a TestRunner instance and executes the command.

    Args:
        command: Test command to execute
        working_directory: Working directory for execution
        timeout_seconds: Timeout in seconds
        expected_exit_code: Expected exit code for success

    Returns:
        TestExecutionResult with execution details
    """
    runner = TestRunner(default_timeout=timeout_seconds)
    return runner.run(
        command=command,
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
        expected_exit_code=expected_exit_code,
    )
