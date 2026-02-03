"""
Test Framework Support for Test-Runner Agent (Feature #208)
===========================================================

Test-runner agent supports multiple test frameworks.

This module provides functionality to:
1. Detect test framework from project configuration
2. Generate appropriate test commands per framework
3. Parse framework-specific result output
4. Configure framework preference in project settings

Supported Frameworks:
- Python: pytest, unittest
- JavaScript/TypeScript: jest, vitest, mocha
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Supported test frameworks
class TestFramework(str, Enum):
    """Supported test frameworks."""
    # Python frameworks
    PYTEST = "pytest"
    UNITTEST = "unittest"
    # JavaScript frameworks
    JEST = "jest"
    VITEST = "vitest"
    MOCHA = "mocha"
    # Unknown/auto-detect
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


# Framework detection marker files
FRAMEWORK_MARKERS: dict[TestFramework, list[str]] = {
    TestFramework.PYTEST: [
        "pytest.ini",
        "pyproject.toml",  # Check for [tool.pytest] section
        "setup.cfg",       # Check for [tool:pytest] section
        "conftest.py",
    ],
    TestFramework.UNITTEST: [
        # Python stdlib unittest (detect by test file naming)
    ],
    TestFramework.JEST: [
        "jest.config.js",
        "jest.config.ts",
        "jest.config.mjs",
        "jest.config.cjs",
        "jest.config.json",
    ],
    TestFramework.VITEST: [
        "vitest.config.ts",
        "vitest.config.js",
        "vitest.config.mts",
        "vitest.config.mjs",
    ],
    TestFramework.MOCHA: [
        ".mocharc.js",
        ".mocharc.json",
        ".mocharc.yaml",
        ".mocharc.yml",
        ".mocharc.cjs",
        ".mocharc.mjs",
    ],
}

# Framework language mapping
FRAMEWORK_LANGUAGES: dict[TestFramework, str] = {
    TestFramework.PYTEST: "python",
    TestFramework.UNITTEST: "python",
    TestFramework.JEST: "javascript",
    TestFramework.VITEST: "javascript",
    TestFramework.MOCHA: "javascript",
    TestFramework.UNKNOWN: "unknown",
}

# Default test commands per framework
DEFAULT_TEST_COMMANDS: dict[TestFramework, str] = {
    TestFramework.PYTEST: "pytest",
    TestFramework.UNITTEST: "python -m unittest discover",
    TestFramework.JEST: "npx jest",
    TestFramework.VITEST: "npx vitest run",
    TestFramework.MOCHA: "npx mocha",
}

# Common test command options
TEST_COMMAND_OPTIONS: dict[TestFramework, dict[str, str]] = {
    TestFramework.PYTEST: {
        "verbose": "-v",
        "very_verbose": "-vv",
        "coverage": "--cov",
        "failfast": "-x",
        "collect_only": "--collect-only",
        "markers": "-m",
        "keyword": "-k",
        "parallel": "-n auto",  # pytest-xdist
        "output_format": "--tb=short",
    },
    TestFramework.UNITTEST: {
        "verbose": "-v",
        "failfast": "-f",
        "buffer": "-b",
        "pattern": "-p",
    },
    TestFramework.JEST: {
        "verbose": "--verbose",
        "coverage": "--coverage",
        "failfast": "--bail",
        "watch": "--watch",
        "testNamePattern": "-t",
        "testPathPattern": "--testPathPattern",
        "parallel": "--maxWorkers=auto",
        "output_format": "--reporters=default",
    },
    TestFramework.VITEST: {
        "verbose": "--reporter=verbose",
        "coverage": "--coverage",
        "failfast": "--bail",
        "watch": "--watch",
        "filter": "--filter",
        "parallel": "--poolOptions.threads.maxThreads=auto",
        "output_format": "--reporter=basic",
    },
    TestFramework.MOCHA: {
        "verbose": "--reporter=spec",
        "failfast": "--bail",
        "watch": "--watch",
        "grep": "--grep",
        "parallel": "--parallel",
        "output_format": "--reporter=spec",
    },
}

# Settings key for framework preference
SETTINGS_FRAMEWORK_KEY = "test_framework"
SETTINGS_TEST_SECTION = "testing"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TestFrameworkDetectionResult:
    """
    Result of detecting test framework from project configuration.

    Feature #208 Step 1: Framework detected from project configuration.

    Attributes:
        framework: Detected or configured test framework
        confidence: Detection confidence (0.0 to 1.0)
        detected_from: Source of detection (config file, package.json, etc.)
        markers_found: List of marker files/sections found
        language: Programming language for the framework
        is_from_settings: True if framework was set via project settings
    """
    framework: TestFramework
    confidence: float
    detected_from: str
    markers_found: list[str] = field(default_factory=list)
    language: str = "unknown"
    is_from_settings: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "framework": str(self.framework),
            "confidence": self.confidence,
            "detected_from": self.detected_from,
            "markers_found": self.markers_found,
            "language": self.language,
            "is_from_settings": self.is_from_settings,
        }


@dataclass
class TestCommand:
    """
    Test command configuration for a specific framework.

    Feature #208 Step 2: Appropriate test commands generated per framework.

    Attributes:
        framework: Test framework this command is for
        command: Base test command
        args: Additional command arguments
        env: Environment variables to set
        working_directory: Working directory for test execution
        timeout_seconds: Command timeout in seconds
    """
    framework: TestFramework
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    working_directory: str | None = None
    timeout_seconds: int = 300

    def to_full_command(self) -> str:
        """Get the full command string with arguments."""
        parts = [self.command] + self.args
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "framework": str(self.framework),
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "working_directory": self.working_directory,
            "timeout_seconds": self.timeout_seconds,
            "full_command": self.to_full_command(),
        }


@dataclass
class TestResult:
    """
    Parsed test result from framework output.

    Feature #208 Step 3: Result parsing handles framework-specific output.

    Attributes:
        framework: Test framework that produced this result
        total: Total number of tests
        passed: Number of passed tests
        failed: Number of failed tests
        skipped: Number of skipped tests
        errors: Number of error tests
        duration_seconds: Total test duration
        exit_code: Process exit code
        raw_output: Raw output from test command
        failed_tests: List of failed test names/descriptions
        coverage_percent: Code coverage percentage (if available)
        success: Overall test success (all tests passed)
    """
    framework: TestFramework
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    exit_code: int = 0
    raw_output: str = ""
    failed_tests: list[str] = field(default_factory=list)
    coverage_percent: float | None = None
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "framework": str(self.framework),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "failed_tests": self.failed_tests,
            "coverage_percent": self.coverage_percent,
            "success": self.success,
        }


@dataclass
class FrameworkPreference:
    """
    Framework preference configuration for project settings.

    Feature #208 Step 4: Framework preference configurable in project settings.

    Attributes:
        framework: Preferred test framework
        custom_command: Custom test command (overrides default)
        custom_args: Custom command arguments
        env_vars: Additional environment variables
        timeout_seconds: Custom timeout
    """
    framework: TestFramework
    custom_command: str | None = None
    custom_args: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 300

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "framework": str(self.framework),
            "custom_command": self.custom_command,
            "custom_args": self.custom_args,
            "env_vars": self.env_vars,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrameworkPreference":
        """Create from dictionary."""
        framework_str = data.get("framework", "unknown")
        try:
            framework = TestFramework(framework_str)
        except ValueError:
            framework = TestFramework.UNKNOWN

        return cls(
            framework=framework,
            custom_command=data.get("custom_command"),
            custom_args=data.get("custom_args", []),
            env_vars=data.get("env_vars", {}),
            timeout_seconds=data.get("timeout_seconds", 300),
        )


# =============================================================================
# Framework Detection (Feature #208 Step 1)
# =============================================================================

def detect_framework(
    project_dir: Path | str,
    settings: dict[str, Any] | None = None,
) -> TestFrameworkDetectionResult:
    """
    Detect test framework from project configuration.

    Feature #208 Step 1: Framework detected from project configuration.

    Detection priority:
    1. Framework preference in project settings
    2. Framework-specific config files (jest.config.js, pytest.ini, etc.)
    3. Package.json devDependencies
    4. pyproject.toml/requirements.txt
    5. Test file patterns

    Args:
        project_dir: Path to project directory
        settings: Optional project settings dict

    Returns:
        TestFrameworkDetectionResult with detected framework and confidence
    """
    project_dir = Path(project_dir).resolve()

    # Step 1: Check project settings for explicit preference
    if settings:
        preference = get_framework_preference(settings)
        if preference and preference.framework != TestFramework.UNKNOWN:
            _logger.info(
                "Framework '%s' set via project settings",
                preference.framework
            )
            return TestFrameworkDetectionResult(
                framework=preference.framework,
                confidence=1.0,
                detected_from="project_settings",
                markers_found=[SETTINGS_FRAMEWORK_KEY],
                language=FRAMEWORK_LANGUAGES.get(preference.framework, "unknown"),
                is_from_settings=True,
            )

    # Step 2: Check for framework-specific config files
    result = _detect_from_config_files(project_dir)
    if result.confidence > 0.7:
        return result

    # Step 3: Check package.json for JS frameworks
    js_result = _detect_from_package_json(project_dir)
    if js_result.confidence > result.confidence:
        result = js_result

    # Step 4: Check pyproject.toml/requirements.txt for Python frameworks
    py_result = _detect_from_python_config(project_dir)
    if py_result.confidence > result.confidence:
        result = py_result

    # Step 5: Fallback to test file pattern detection
    if result.confidence < 0.5:
        pattern_result = _detect_from_test_patterns(project_dir)
        if pattern_result.confidence > result.confidence:
            result = pattern_result

    return result


def _detect_from_config_files(project_dir: Path) -> TestFrameworkDetectionResult:
    """Detect framework from config files."""
    best_result = TestFrameworkDetectionResult(
        framework=TestFramework.UNKNOWN,
        confidence=0.0,
        detected_from="none",
    )

    for framework, markers in FRAMEWORK_MARKERS.items():
        found_markers = []
        for marker in markers:
            marker_path = project_dir / marker
            if marker_path.exists():
                found_markers.append(marker)

        if found_markers:
            confidence = min(0.9, 0.6 + 0.15 * len(found_markers))
            if confidence > best_result.confidence:
                best_result = TestFrameworkDetectionResult(
                    framework=framework,
                    confidence=confidence,
                    detected_from=f"config_file:{found_markers[0]}",
                    markers_found=found_markers,
                    language=FRAMEWORK_LANGUAGES.get(framework, "unknown"),
                )

    return best_result


def _detect_from_package_json(project_dir: Path) -> TestFrameworkDetectionResult:
    """Detect JS/TS framework from package.json."""
    package_json_path = project_dir / "package.json"

    if not package_json_path.exists():
        return TestFrameworkDetectionResult(
            framework=TestFramework.UNKNOWN,
            confidence=0.0,
            detected_from="none",
        )

    try:
        content = package_json_path.read_text(encoding="utf-8")
        package_data = json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        _logger.warning("Failed to parse package.json: %s", e)
        return TestFrameworkDetectionResult(
            framework=TestFramework.UNKNOWN,
            confidence=0.0,
            detected_from="none",
        )

    # Check devDependencies and dependencies
    deps: dict[str, str] = {}
    deps.update(package_data.get("devDependencies", {}))
    deps.update(package_data.get("dependencies", {}))

    framework_map = {
        "vitest": TestFramework.VITEST,
        "jest": TestFramework.JEST,
        "@jest/core": TestFramework.JEST,
        "mocha": TestFramework.MOCHA,
    }

    # Check for frameworks in order of specificity
    for pkg_name, framework in framework_map.items():
        if pkg_name in deps:
            return TestFrameworkDetectionResult(
                framework=framework,
                confidence=0.85,
                detected_from=f"package.json:{pkg_name}",
                markers_found=[pkg_name],
                language="javascript",
            )

    # Check scripts for test commands
    scripts = package_data.get("scripts", {})
    test_script = scripts.get("test", "")

    if "vitest" in test_script:
        return TestFrameworkDetectionResult(
            framework=TestFramework.VITEST,
            confidence=0.8,
            detected_from="package.json:scripts.test",
            markers_found=["scripts.test"],
            language="javascript",
        )
    elif "jest" in test_script:
        return TestFrameworkDetectionResult(
            framework=TestFramework.JEST,
            confidence=0.8,
            detected_from="package.json:scripts.test",
            markers_found=["scripts.test"],
            language="javascript",
        )
    elif "mocha" in test_script:
        return TestFrameworkDetectionResult(
            framework=TestFramework.MOCHA,
            confidence=0.8,
            detected_from="package.json:scripts.test",
            markers_found=["scripts.test"],
            language="javascript",
        )

    return TestFrameworkDetectionResult(
        framework=TestFramework.UNKNOWN,
        confidence=0.0,
        detected_from="package.json",
    )


def _detect_from_python_config(project_dir: Path) -> TestFrameworkDetectionResult:
    """Detect Python framework from pyproject.toml or requirements.txt."""
    # Check pyproject.toml
    pyproject_path = project_dir / "pyproject.toml"
    if pyproject_path.exists():
        try:
            content = pyproject_path.read_text(encoding="utf-8")
            if "[tool.pytest" in content or "pytest" in content.lower():
                return TestFrameworkDetectionResult(
                    framework=TestFramework.PYTEST,
                    confidence=0.85,
                    detected_from="pyproject.toml:pytest",
                    markers_found=["pyproject.toml"],
                    language="python",
                )
        except IOError:
            pass

    # Check requirements.txt
    for req_file in ["requirements.txt", "requirements-dev.txt", "requirements-test.txt"]:
        req_path = project_dir / req_file
        if req_path.exists():
            try:
                content = req_path.read_text(encoding="utf-8").lower()
                if "pytest" in content:
                    return TestFrameworkDetectionResult(
                        framework=TestFramework.PYTEST,
                        confidence=0.8,
                        detected_from=f"{req_file}:pytest",
                        markers_found=[req_file],
                        language="python",
                    )
            except IOError:
                pass

    return TestFrameworkDetectionResult(
        framework=TestFramework.UNKNOWN,
        confidence=0.0,
        detected_from="none",
    )


def _detect_from_test_patterns(project_dir: Path) -> TestFrameworkDetectionResult:
    """Detect framework from test file naming patterns."""
    # Look for test files
    python_tests = list(project_dir.glob("**/test_*.py")) + list(project_dir.glob("**/*_test.py"))
    js_tests = list(project_dir.glob("**/*.test.js")) + list(project_dir.glob("**/*.spec.js"))
    ts_tests = list(project_dir.glob("**/*.test.ts")) + list(project_dir.glob("**/*.spec.ts"))

    if python_tests:
        # Python test files found - check for pytest vs unittest
        for test_file in python_tests[:10]:  # Sample up to 10 files
            try:
                content = test_file.read_text(encoding="utf-8")
                if "import pytest" in content or "@pytest" in content:
                    return TestFrameworkDetectionResult(
                        framework=TestFramework.PYTEST,
                        confidence=0.7,
                        detected_from="test_file_pattern:pytest_imports",
                        markers_found=[str(test_file.relative_to(project_dir))],
                        language="python",
                    )
                elif "import unittest" in content or "class.*Test.*unittest" in content:
                    return TestFrameworkDetectionResult(
                        framework=TestFramework.UNITTEST,
                        confidence=0.7,
                        detected_from="test_file_pattern:unittest_imports",
                        markers_found=[str(test_file.relative_to(project_dir))],
                        language="python",
                    )
            except IOError:
                continue

        # Default to pytest for Python projects
        return TestFrameworkDetectionResult(
            framework=TestFramework.PYTEST,
            confidence=0.5,
            detected_from="test_file_pattern:python_default",
            markers_found=["test_*.py"],
            language="python",
        )

    if js_tests or ts_tests:
        # JavaScript/TypeScript test files found
        return TestFrameworkDetectionResult(
            framework=TestFramework.JEST,  # Jest is most common
            confidence=0.4,
            detected_from="test_file_pattern:js_default",
            markers_found=["*.test.js" if js_tests else "*.test.ts"],
            language="javascript",
        )

    return TestFrameworkDetectionResult(
        framework=TestFramework.UNKNOWN,
        confidence=0.0,
        detected_from="none",
    )


# =============================================================================
# Test Command Generation (Feature #208 Step 2)
# =============================================================================

def generate_test_command(
    framework: TestFramework,
    project_dir: Path | str | None = None,
    test_path: str | None = None,
    options: dict[str, Any] | None = None,
    preference: FrameworkPreference | None = None,
) -> TestCommand:
    """
    Generate appropriate test command for the framework.

    Feature #208 Step 2: Appropriate test commands generated per framework.

    Args:
        framework: Test framework to generate command for
        project_dir: Project directory (for working_directory)
        test_path: Specific test file or directory to run
        options: Additional options (verbose, coverage, failfast, etc.)
        preference: Framework preference with custom settings

    Returns:
        TestCommand with full command configuration

    Examples:
        >>> cmd = generate_test_command(TestFramework.PYTEST, options={"verbose": True})
        >>> cmd.to_full_command()
        'pytest -v'

        >>> cmd = generate_test_command(TestFramework.JEST, test_path="src/tests/")
        >>> cmd.to_full_command()
        'npx jest src/tests/'
    """
    options = options or {}

    # Use custom command from preference if available
    if preference and preference.custom_command:
        base_command = preference.custom_command
    else:
        base_command = DEFAULT_TEST_COMMANDS.get(framework, "")

    if not base_command:
        raise ValueError(f"No test command available for framework: {framework}")

    args: list[str] = []
    env: dict[str, str] = {}

    # Add framework-specific options
    framework_options = TEST_COMMAND_OPTIONS.get(framework, {})
    for option_name, option_value in options.items():
        if option_name in framework_options:
            if isinstance(option_value, bool):
                if option_value:
                    args.append(framework_options[option_name])
            else:
                args.append(f"{framework_options[option_name]}={option_value}")

    # Add custom args from preference
    if preference and preference.custom_args:
        args.extend(preference.custom_args)

    # Add test path if specified
    if test_path:
        args.append(test_path)

    # Set environment variables
    if preference and preference.env_vars:
        env.update(preference.env_vars)

    # Framework-specific environment
    if framework == TestFramework.PYTEST:
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    elif framework in (TestFramework.JEST, TestFramework.VITEST):
        env.setdefault("NODE_ENV", "test")

    working_dir = str(Path(project_dir).resolve()) if project_dir else None
    timeout = preference.timeout_seconds if preference else 300

    return TestCommand(
        framework=framework,
        command=base_command,
        args=args,
        env=env,
        working_directory=working_dir,
        timeout_seconds=timeout,
    )


def get_available_options(framework: TestFramework) -> dict[str, str]:
    """
    Get available command options for a framework.

    Args:
        framework: Test framework

    Returns:
        Dictionary of option names to their command-line flags
    """
    return dict(TEST_COMMAND_OPTIONS.get(framework, {}))


# =============================================================================
# Result Parsing (Feature #208 Step 3)
# =============================================================================

def parse_test_output(
    framework: TestFramework,
    output: str,
    exit_code: int = 0,
) -> TestResult:
    """
    Parse test output into structured result.

    Feature #208 Step 3: Result parsing handles framework-specific output.

    Args:
        framework: Test framework that produced the output
        output: Raw test output string
        exit_code: Process exit code

    Returns:
        TestResult with parsed test statistics
    """
    parsers = {
        TestFramework.PYTEST: _parse_pytest_output,
        TestFramework.UNITTEST: _parse_unittest_output,
        TestFramework.JEST: _parse_jest_output,
        TestFramework.VITEST: _parse_vitest_output,
        TestFramework.MOCHA: _parse_mocha_output,
    }

    parser = parsers.get(framework, _parse_generic_output)
    result = parser(output, exit_code)
    result.framework = framework
    result.raw_output = output
    result.exit_code = exit_code

    return result


def _parse_pytest_output(output: str, exit_code: int) -> TestResult:
    """Parse pytest output."""
    result = TestResult(framework=TestFramework.PYTEST)

    # Match summary line: "====== 5 passed, 2 failed, 1 skipped in 1.23s ======"
    summary_pattern = r"=+\s*(.*?)\s*in\s*([\d.]+)s?\s*=+"
    match = re.search(summary_pattern, output)

    if match:
        summary = match.group(1)
        result.duration_seconds = float(match.group(2))

        # Parse counts
        passed = re.search(r"(\d+)\s+passed", summary)
        failed = re.search(r"(\d+)\s+failed", summary)
        skipped = re.search(r"(\d+)\s+skipped", summary)
        errors = re.search(r"(\d+)\s+error", summary)

        if passed:
            result.passed = int(passed.group(1))
        if failed:
            result.failed = int(failed.group(1))
        if skipped:
            result.skipped = int(skipped.group(1))
        if errors:
            result.errors = int(errors.group(1))

    result.total = result.passed + result.failed + result.skipped + result.errors

    # Extract failed test names
    failed_pattern = r"FAILED\s+([\w/:._-]+)"
    result.failed_tests = re.findall(failed_pattern, output)

    # Check for coverage
    coverage_pattern = r"TOTAL\s+\d+\s+\d+\s+(\d+)%"
    coverage_match = re.search(coverage_pattern, output)
    if coverage_match:
        result.coverage_percent = float(coverage_match.group(1))

    result.success = exit_code == 0 and result.failed == 0 and result.errors == 0
    return result


def _parse_unittest_output(output: str, exit_code: int) -> TestResult:
    """Parse unittest output."""
    result = TestResult(framework=TestFramework.UNITTEST)

    # Match: "Ran 5 tests in 0.123s"
    ran_pattern = r"Ran\s+(\d+)\s+tests?\s+in\s+([\d.]+)s"
    ran_match = re.search(ran_pattern, output)

    if ran_match:
        result.total = int(ran_match.group(1))
        result.duration_seconds = float(ran_match.group(2))

    # Match: "OK" or "FAILED (failures=2, errors=1)"
    if "OK" in output and "FAILED" not in output:
        result.passed = result.total
        result.success = True
    else:
        failures = re.search(r"failures=(\d+)", output)
        errors = re.search(r"errors=(\d+)", output)
        skipped = re.search(r"skipped=(\d+)", output)

        if failures:
            result.failed = int(failures.group(1))
        if errors:
            result.errors = int(errors.group(1))
        if skipped:
            result.skipped = int(skipped.group(1))

        result.passed = result.total - result.failed - result.errors - result.skipped

    # Extract failed test names
    failed_pattern = r"FAIL:\s+([\w.]+)"
    result.failed_tests = re.findall(failed_pattern, output)

    result.success = exit_code == 0 and result.failed == 0 and result.errors == 0
    return result


def _parse_jest_output(output: str, exit_code: int) -> TestResult:
    """Parse Jest output."""
    result = TestResult(framework=TestFramework.JEST)

    # Match: "Tests: 2 failed, 3 passed, 5 total"
    tests_pattern = r"Tests:\s+(.*?total)"
    tests_match = re.search(tests_pattern, output)

    if tests_match:
        summary = tests_match.group(1)
        passed = re.search(r"(\d+)\s+passed", summary)
        failed = re.search(r"(\d+)\s+failed", summary)
        skipped = re.search(r"(\d+)\s+skipped", summary)
        total = re.search(r"(\d+)\s+total", summary)

        if passed:
            result.passed = int(passed.group(1))
        if failed:
            result.failed = int(failed.group(1))
        if skipped:
            result.skipped = int(skipped.group(1))
        if total:
            result.total = int(total.group(1))

    # Match: "Time: 1.234s"
    time_pattern = r"Time:\s*([\d.]+)\s*s"
    time_match = re.search(time_pattern, output)
    if time_match:
        result.duration_seconds = float(time_match.group(1))

    # Extract failed test names
    failed_pattern = r"✕\s+(.+?)(?:\s*\(\d+\s*ms\))?"
    result.failed_tests = re.findall(failed_pattern, output)

    # Check for coverage
    coverage_pattern = r"All files\s*\|\s*([\d.]+)"
    coverage_match = re.search(coverage_pattern, output)
    if coverage_match:
        result.coverage_percent = float(coverage_match.group(1))

    result.success = exit_code == 0 and result.failed == 0
    return result


def _parse_vitest_output(output: str, exit_code: int) -> TestResult:
    """Parse Vitest output."""
    result = TestResult(framework=TestFramework.VITEST)

    # Match: "Test Files  2 passed | 1 failed (3)"
    files_pattern = r"Test Files\s+(.*?)\s*\(\d+\)"
    files_match = re.search(files_pattern, output)

    # Match: "Tests  10 passed | 2 failed (12)"
    tests_pattern = r"Tests\s+(.*?)\s*\(\d+\)"
    tests_match = re.search(tests_pattern, output)

    if tests_match:
        summary = tests_match.group(1)
        passed = re.search(r"(\d+)\s+passed", summary)
        failed = re.search(r"(\d+)\s+failed", summary)
        skipped = re.search(r"(\d+)\s+skipped", summary)

        if passed:
            result.passed = int(passed.group(1))
        if failed:
            result.failed = int(failed.group(1))
        if skipped:
            result.skipped = int(skipped.group(1))

    result.total = result.passed + result.failed + result.skipped

    # Match: "Duration  1.23s"
    duration_pattern = r"Duration\s+([\d.]+)\s*s"
    duration_match = re.search(duration_pattern, output)
    if duration_match:
        result.duration_seconds = float(duration_match.group(1))

    # Extract failed test names
    failed_pattern = r"❌\s+(.+)"
    result.failed_tests = re.findall(failed_pattern, output)

    result.success = exit_code == 0 and result.failed == 0
    return result


def _parse_mocha_output(output: str, exit_code: int) -> TestResult:
    """Parse Mocha output."""
    result = TestResult(framework=TestFramework.MOCHA)

    # Match: "5 passing (123ms)"
    passing_pattern = r"(\d+)\s+passing\s*\(([^)]+)\)"
    passing_match = re.search(passing_pattern, output)

    if passing_match:
        result.passed = int(passing_match.group(1))
        duration_str = passing_match.group(2)
        # Parse duration (could be "123ms" or "1s" or "1m")
        if "ms" in duration_str:
            result.duration_seconds = float(duration_str.replace("ms", "")) / 1000
        elif "m" in duration_str:
            result.duration_seconds = float(duration_str.replace("m", "")) * 60
        else:
            result.duration_seconds = float(duration_str.replace("s", ""))

    # Match: "2 failing"
    failing_pattern = r"(\d+)\s+failing"
    failing_match = re.search(failing_pattern, output)
    if failing_match:
        result.failed = int(failing_match.group(1))

    # Match: "1 pending"
    pending_pattern = r"(\d+)\s+pending"
    pending_match = re.search(pending_pattern, output)
    if pending_match:
        result.skipped = int(pending_match.group(1))

    result.total = result.passed + result.failed + result.skipped

    # Extract failed test names
    failed_pattern = r"\d+\)\s+(.+?):"
    result.failed_tests = re.findall(failed_pattern, output)

    result.success = exit_code == 0 and result.failed == 0
    return result


def _parse_generic_output(output: str, exit_code: int) -> TestResult:
    """Generic output parser for unknown frameworks."""
    result = TestResult(framework=TestFramework.UNKNOWN)
    result.success = exit_code == 0
    return result


# =============================================================================
# Framework Preference in Settings (Feature #208 Step 4)
# =============================================================================

def get_framework_preference(settings: dict[str, Any]) -> FrameworkPreference | None:
    """
    Get framework preference from project settings.

    Feature #208 Step 4: Framework preference configurable in project settings.

    Args:
        settings: Project settings dictionary

    Returns:
        FrameworkPreference if configured, None otherwise
    """
    # Check for testing section
    testing_config = settings.get(SETTINGS_TEST_SECTION, {})

    # Check for direct framework key
    framework_str = testing_config.get(SETTINGS_FRAMEWORK_KEY)
    if not framework_str:
        framework_str = settings.get(SETTINGS_FRAMEWORK_KEY)

    if not framework_str:
        return None

    try:
        framework = TestFramework(framework_str)
    except ValueError:
        _logger.warning("Invalid framework in settings: %s", framework_str)
        return None

    return FrameworkPreference(
        framework=framework,
        custom_command=testing_config.get("custom_command"),
        custom_args=testing_config.get("custom_args", []),
        env_vars=testing_config.get("env_vars", {}),
        timeout_seconds=testing_config.get("timeout_seconds", 300),
    )


def set_framework_preference(
    settings: dict[str, Any],
    preference: FrameworkPreference,
) -> dict[str, Any]:
    """
    Set framework preference in project settings.

    Feature #208 Step 4: Framework preference configurable in project settings.

    Args:
        settings: Project settings dictionary
        preference: Framework preference to set

    Returns:
        Updated settings dictionary
    """
    settings = dict(settings)  # Don't modify original

    # Ensure testing section exists
    if SETTINGS_TEST_SECTION not in settings:
        settings[SETTINGS_TEST_SECTION] = {}

    testing_config = settings[SETTINGS_TEST_SECTION]
    testing_config[SETTINGS_FRAMEWORK_KEY] = str(preference.framework)

    if preference.custom_command:
        testing_config["custom_command"] = preference.custom_command
    if preference.custom_args:
        testing_config["custom_args"] = preference.custom_args
    if preference.env_vars:
        testing_config["env_vars"] = preference.env_vars
    if preference.timeout_seconds != 300:
        testing_config["timeout_seconds"] = preference.timeout_seconds

    return settings


def get_supported_frameworks() -> list[TestFramework]:
    """Get list of supported test frameworks."""
    return [f for f in TestFramework if f != TestFramework.UNKNOWN]


def get_framework_info(framework: TestFramework) -> dict[str, Any]:
    """
    Get information about a test framework.

    Args:
        framework: Test framework

    Returns:
        Dictionary with framework information
    """
    return {
        "name": str(framework),
        "language": FRAMEWORK_LANGUAGES.get(framework, "unknown"),
        "default_command": DEFAULT_TEST_COMMANDS.get(framework, ""),
        "config_files": FRAMEWORK_MARKERS.get(framework, []),
        "available_options": list(TEST_COMMAND_OPTIONS.get(framework, {}).keys()),
    }
