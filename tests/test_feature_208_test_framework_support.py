"""
Tests for Feature #208: Test-runner agent supports multiple test frameworks
===========================================================================

This test suite verifies the test framework support functionality including:
- Step 1: Framework detected from project configuration
- Step 2: Appropriate test commands generated per framework
- Step 3: Result parsing handles framework-specific output
- Step 4: Framework preference configurable in project settings

Run with:
    pytest tests/test_feature_208_test_framework_support.py -v
"""
import json
import pytest
import tempfile
from pathlib import Path

from api.test_framework import (
    # Enum
    TestFramework,
    # Data classes
    TestFrameworkDetectionResult,
    TestCommand,
    TestResult,
    FrameworkPreference,
    # Detection functions
    detect_framework,
    # Command generation functions
    generate_test_command,
    get_available_options,
    # Result parsing functions
    parse_test_output,
    # Settings functions
    get_framework_preference,
    set_framework_preference,
    get_supported_frameworks,
    get_framework_info,
    # Constants
    FRAMEWORK_MARKERS,
    FRAMEWORK_LANGUAGES,
    DEFAULT_TEST_COMMANDS,
    TEST_COMMAND_OPTIONS,
    SETTINGS_FRAMEWORK_KEY,
    SETTINGS_TEST_SECTION,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def pytest_project(temp_project_dir):
    """Create a project with pytest configuration."""
    (temp_project_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (temp_project_dir / "tests").mkdir()
    (temp_project_dir / "tests" / "test_example.py").write_text(
        "import pytest\n\ndef test_example():\n    pass\n",
        encoding="utf-8"
    )
    return temp_project_dir


@pytest.fixture
def jest_project(temp_project_dir):
    """Create a project with Jest configuration."""
    package_json = {
        "name": "test-project",
        "devDependencies": {
            "jest": "^29.0.0"
        },
        "scripts": {
            "test": "jest"
        }
    }
    (temp_project_dir / "package.json").write_text(
        json.dumps(package_json, indent=2),
        encoding="utf-8"
    )
    (temp_project_dir / "__tests__").mkdir()
    return temp_project_dir


@pytest.fixture
def vitest_project(temp_project_dir):
    """Create a project with Vitest configuration."""
    (temp_project_dir / "vitest.config.ts").write_text(
        "export default {};\n",
        encoding="utf-8"
    )
    package_json = {
        "name": "vitest-project",
        "devDependencies": {
            "vitest": "^1.0.0"
        }
    }
    (temp_project_dir / "package.json").write_text(
        json.dumps(package_json, indent=2),
        encoding="utf-8"
    )
    return temp_project_dir


@pytest.fixture
def mocha_project(temp_project_dir):
    """Create a project with Mocha configuration."""
    (temp_project_dir / ".mocharc.json").write_text(
        '{"spec": "test/**/*.js"}\n',
        encoding="utf-8"
    )
    return temp_project_dir


# =============================================================================
# Step 1: Framework detected from project configuration
# =============================================================================

class TestStep1FrameworkDetection:
    """Tests for Feature #208 Step 1: Framework detected from project configuration."""

    def test_detect_pytest_from_ini_file(self, pytest_project):
        """Detect pytest from pytest.ini file."""
        result = detect_framework(pytest_project)
        assert result.framework == TestFramework.PYTEST
        assert result.confidence >= 0.6
        assert "pytest.ini" in result.markers_found

    def test_detect_pytest_from_pyproject_toml(self, temp_project_dir):
        """Detect pytest from pyproject.toml."""
        (temp_project_dir / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\nminversion = "6.0"\n',
            encoding="utf-8"
        )
        result = detect_framework(temp_project_dir)
        assert result.framework == TestFramework.PYTEST
        assert result.confidence >= 0.7

    def test_detect_jest_from_config_file(self, temp_project_dir):
        """Detect Jest from jest.config.js."""
        (temp_project_dir / "jest.config.js").write_text(
            "module.exports = {};\n",
            encoding="utf-8"
        )
        result = detect_framework(temp_project_dir)
        assert result.framework == TestFramework.JEST
        assert result.confidence >= 0.6

    def test_detect_jest_from_package_json(self, jest_project):
        """Detect Jest from package.json devDependencies."""
        result = detect_framework(jest_project)
        assert result.framework == TestFramework.JEST
        assert result.confidence >= 0.8

    def test_detect_vitest_from_config_file(self, vitest_project):
        """Detect Vitest from vitest.config.ts."""
        result = detect_framework(vitest_project)
        assert result.framework == TestFramework.VITEST
        assert result.confidence >= 0.6

    def test_detect_mocha_from_config_file(self, mocha_project):
        """Detect Mocha from .mocharc.json."""
        result = detect_framework(mocha_project)
        assert result.framework == TestFramework.MOCHA
        assert result.confidence >= 0.6

    def test_detect_framework_from_settings(self, temp_project_dir):
        """Detect framework from project settings preference."""
        settings = {
            SETTINGS_TEST_SECTION: {
                SETTINGS_FRAMEWORK_KEY: "vitest"
            }
        }
        result = detect_framework(temp_project_dir, settings=settings)
        assert result.framework == TestFramework.VITEST
        assert result.confidence == 1.0
        assert result.is_from_settings is True

    def test_detect_unknown_framework(self, temp_project_dir):
        """Return unknown for projects with no clear framework."""
        result = detect_framework(temp_project_dir)
        assert result.framework == TestFramework.UNKNOWN
        assert result.confidence < 0.5

    def test_detect_framework_language(self, pytest_project):
        """Detection includes programming language."""
        result = detect_framework(pytest_project)
        assert result.language == "python"

    def test_detect_framework_language_javascript(self, jest_project):
        """JavaScript framework detection includes language."""
        result = detect_framework(jest_project)
        assert result.language == "javascript"


# =============================================================================
# Step 2: Appropriate test commands generated per framework
# =============================================================================

class TestStep2CommandGeneration:
    """Tests for Feature #208 Step 2: Appropriate test commands generated per framework."""

    def test_generate_pytest_command(self):
        """Generate pytest command."""
        cmd = generate_test_command(TestFramework.PYTEST)
        assert cmd.framework == TestFramework.PYTEST
        assert cmd.command == "pytest"
        assert cmd.to_full_command() == "pytest"

    def test_generate_unittest_command(self):
        """Generate unittest command."""
        cmd = generate_test_command(TestFramework.UNITTEST)
        assert cmd.framework == TestFramework.UNITTEST
        assert cmd.command == "python -m unittest discover"

    def test_generate_jest_command(self):
        """Generate Jest command."""
        cmd = generate_test_command(TestFramework.JEST)
        assert cmd.framework == TestFramework.JEST
        assert cmd.command == "npx jest"

    def test_generate_vitest_command(self):
        """Generate Vitest command."""
        cmd = generate_test_command(TestFramework.VITEST)
        assert cmd.framework == TestFramework.VITEST
        assert cmd.command == "npx vitest run"

    def test_generate_mocha_command(self):
        """Generate Mocha command."""
        cmd = generate_test_command(TestFramework.MOCHA)
        assert cmd.framework == TestFramework.MOCHA
        assert cmd.command == "npx mocha"

    def test_generate_command_with_verbose(self):
        """Generate command with verbose option."""
        cmd = generate_test_command(
            TestFramework.PYTEST,
            options={"verbose": True}
        )
        assert "-v" in cmd.args
        assert "-v" in cmd.to_full_command()

    def test_generate_command_with_coverage(self):
        """Generate command with coverage option."""
        cmd = generate_test_command(
            TestFramework.PYTEST,
            options={"coverage": True}
        )
        assert "--cov" in cmd.args

    def test_generate_command_with_failfast(self):
        """Generate command with failfast option."""
        cmd = generate_test_command(
            TestFramework.PYTEST,
            options={"failfast": True}
        )
        assert "-x" in cmd.args

    def test_generate_command_with_test_path(self):
        """Generate command with specific test path."""
        cmd = generate_test_command(
            TestFramework.PYTEST,
            test_path="tests/test_specific.py"
        )
        assert "tests/test_specific.py" in cmd.args
        assert "tests/test_specific.py" in cmd.to_full_command()

    def test_generate_command_with_custom_preference(self):
        """Generate command with custom preference."""
        preference = FrameworkPreference(
            framework=TestFramework.PYTEST,
            custom_command="python -m pytest",
            custom_args=["--strict-markers"],
            timeout_seconds=600
        )
        cmd = generate_test_command(
            TestFramework.PYTEST,
            preference=preference
        )
        assert cmd.command == "python -m pytest"
        assert "--strict-markers" in cmd.args
        assert cmd.timeout_seconds == 600

    def test_generate_jest_command_with_options(self):
        """Generate Jest command with options."""
        cmd = generate_test_command(
            TestFramework.JEST,
            options={"verbose": True, "coverage": True}
        )
        assert "--verbose" in cmd.args
        assert "--coverage" in cmd.args

    def test_generate_command_with_working_directory(self, temp_project_dir):
        """Generate command with working directory."""
        cmd = generate_test_command(
            TestFramework.PYTEST,
            project_dir=temp_project_dir
        )
        assert cmd.working_directory == str(temp_project_dir.resolve())

    def test_get_available_options(self):
        """Get available options for a framework."""
        options = get_available_options(TestFramework.PYTEST)
        assert "verbose" in options
        assert "coverage" in options
        assert "failfast" in options


# =============================================================================
# Step 3: Result parsing handles framework-specific output
# =============================================================================

class TestStep3ResultParsing:
    """Tests for Feature #208 Step 3: Result parsing handles framework-specific output."""

    def test_parse_pytest_output_success(self):
        """Parse successful pytest output."""
        output = """
============================= test session starts ==============================
collected 5 items

tests/test_example.py .....                                              [100%]

============================== 5 passed in 0.12s ===============================
"""
        result = parse_test_output(TestFramework.PYTEST, output, exit_code=0)
        assert result.framework == TestFramework.PYTEST
        assert result.total == 5
        assert result.passed == 5
        assert result.failed == 0
        assert result.success is True
        assert result.duration_seconds == 0.12

    def test_parse_pytest_output_failure(self):
        """Parse pytest output with failures."""
        output = """
============================= test session starts ==============================
collected 5 items

tests/test_example.py ..F.F                                              [100%]

FAILED tests/test_example.py::test_one
FAILED tests/test_example.py::test_two

============================== 2 failed, 3 passed in 0.34s =====================
"""
        result = parse_test_output(TestFramework.PYTEST, output, exit_code=1)
        assert result.passed == 3
        assert result.failed == 2
        assert result.success is False
        assert len(result.failed_tests) == 2
        assert "tests/test_example.py::test_one" in result.failed_tests

    def test_parse_pytest_output_with_skip(self):
        """Parse pytest output with skipped tests."""
        output = """
============================= test session starts ==============================
collected 5 items

tests/test_example.py ...s.                                              [100%]

========================= 4 passed, 1 skipped in 0.15s =========================
"""
        result = parse_test_output(TestFramework.PYTEST, output, exit_code=0)
        assert result.passed == 4
        assert result.skipped == 1
        assert result.success is True

    def test_parse_pytest_output_with_coverage(self):
        """Parse pytest output with coverage information."""
        output = """
============================= test session starts ==============================
collected 3 items

tests/test_example.py ...                                                [100%]

----------- coverage: platform linux, python 3.11.0 -----------
Name                 Stmts   Miss  Cover
----------------------------------------
src/module.py           50     10    80%
----------------------------------------
TOTAL                   50     10    80%

============================== 3 passed in 0.50s ===============================
"""
        result = parse_test_output(TestFramework.PYTEST, output, exit_code=0)
        assert result.coverage_percent == 80.0

    def test_parse_unittest_output_success(self):
        """Parse successful unittest output."""
        output = """
test_one (test_example.TestExample) ... ok
test_two (test_example.TestExample) ... ok
test_three (test_example.TestExample) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.005s

OK
"""
        result = parse_test_output(TestFramework.UNITTEST, output, exit_code=0)
        assert result.total == 3
        assert result.passed == 3
        assert result.success is True

    def test_parse_unittest_output_failure(self):
        """Parse unittest output with failures."""
        output = """
test_one (test_example.TestExample) ... ok
test_two (test_example.TestExample) ... FAIL
test_three (test_example.TestExample) ... ERROR

----------------------------------------------------------------------
Ran 3 tests in 0.010s

FAILED (failures=1, errors=1)
"""
        result = parse_test_output(TestFramework.UNITTEST, output, exit_code=1)
        assert result.total == 3
        assert result.failed == 1
        assert result.errors == 1
        assert result.passed == 1
        assert result.success is False

    def test_parse_jest_output_success(self):
        """Parse successful Jest output."""
        output = """
PASS  src/__tests__/example.test.js
  ✓ should pass test one (5 ms)
  ✓ should pass test two (3 ms)

Tests:  2 passed, 2 total
Time:   1.234s
"""
        result = parse_test_output(TestFramework.JEST, output, exit_code=0)
        assert result.passed == 2
        assert result.total == 2
        assert result.success is True
        assert result.duration_seconds == 1.234

    def test_parse_jest_output_failure(self):
        """Parse Jest output with failures."""
        output = """
FAIL  src/__tests__/example.test.js
  ✓ should pass test one (5 ms)
  ✕ should fail test two (10 ms)

Tests:  1 failed, 1 passed, 2 total
Time:   1.500s
"""
        result = parse_test_output(TestFramework.JEST, output, exit_code=1)
        assert result.passed == 1
        assert result.failed == 1
        assert result.total == 2
        assert result.success is False

    def test_parse_vitest_output_success(self):
        """Parse successful Vitest output."""
        output = """
 ✓ src/example.test.ts (2)
   ✓ should pass test one
   ✓ should pass test two

 Test Files  1 passed (1)
      Tests  2 passed (2)
   Duration  1.50s
"""
        result = parse_test_output(TestFramework.VITEST, output, exit_code=0)
        assert result.passed == 2
        assert result.success is True
        assert result.duration_seconds == 1.50

    def test_parse_vitest_output_failure(self):
        """Parse Vitest output with failures."""
        output = """
 ❌ src/example.test.ts (2)
   ✓ should pass test one
   ❌ should fail test two

 Test Files  1 failed (1)
      Tests  1 failed | 1 passed (2)
   Duration  2.00s
"""
        result = parse_test_output(TestFramework.VITEST, output, exit_code=1)
        assert result.passed == 1
        assert result.failed == 1
        assert result.success is False

    def test_parse_mocha_output_success(self):
        """Parse successful Mocha output."""
        output = """
  Example Tests
    ✓ should pass test one
    ✓ should pass test two

  2 passing (100ms)
"""
        result = parse_test_output(TestFramework.MOCHA, output, exit_code=0)
        assert result.passed == 2
        assert result.success is True
        assert result.duration_seconds == 0.1

    def test_parse_mocha_output_failure(self):
        """Parse Mocha output with failures."""
        output = """
  Example Tests
    ✓ should pass test one
    1) should fail test two

  1 passing (100ms)
  1 failing

  1) Example Tests
     should fail test two:
     AssertionError: expected 1 to equal 2
"""
        result = parse_test_output(TestFramework.MOCHA, output, exit_code=1)
        assert result.passed == 1
        assert result.failed == 1
        assert result.success is False


# =============================================================================
# Step 4: Framework preference configurable in project settings
# =============================================================================

class TestStep4SettingsPreference:
    """Tests for Feature #208 Step 4: Framework preference configurable in project settings."""

    def test_get_framework_preference_empty(self):
        """Get preference from empty settings returns None."""
        settings = {}
        preference = get_framework_preference(settings)
        assert preference is None

    def test_get_framework_preference_from_section(self):
        """Get preference from testing section."""
        settings = {
            SETTINGS_TEST_SECTION: {
                SETTINGS_FRAMEWORK_KEY: "pytest"
            }
        }
        preference = get_framework_preference(settings)
        assert preference is not None
        assert preference.framework == TestFramework.PYTEST

    def test_get_framework_preference_with_custom_command(self):
        """Get preference with custom command."""
        settings = {
            SETTINGS_TEST_SECTION: {
                SETTINGS_FRAMEWORK_KEY: "pytest",
                "custom_command": "python -m pytest",
                "custom_args": ["--strict-markers"],
                "timeout_seconds": 600
            }
        }
        preference = get_framework_preference(settings)
        assert preference is not None
        assert preference.custom_command == "python -m pytest"
        assert "--strict-markers" in preference.custom_args
        assert preference.timeout_seconds == 600

    def test_get_framework_preference_invalid_framework(self):
        """Get preference with invalid framework returns None."""
        settings = {
            SETTINGS_TEST_SECTION: {
                SETTINGS_FRAMEWORK_KEY: "invalid_framework"
            }
        }
        preference = get_framework_preference(settings)
        assert preference is None

    def test_set_framework_preference(self):
        """Set framework preference in settings."""
        settings = {}
        preference = FrameworkPreference(
            framework=TestFramework.JEST,
            custom_args=["--watchAll=false"],
            timeout_seconds=900
        )
        updated = set_framework_preference(settings, preference)

        assert SETTINGS_TEST_SECTION in updated
        assert updated[SETTINGS_TEST_SECTION][SETTINGS_FRAMEWORK_KEY] == "jest"
        assert "--watchAll=false" in updated[SETTINGS_TEST_SECTION]["custom_args"]
        assert updated[SETTINGS_TEST_SECTION]["timeout_seconds"] == 900

    def test_set_framework_preference_preserves_existing(self):
        """Set framework preference preserves other settings."""
        settings = {
            "other_key": "other_value",
            SETTINGS_TEST_SECTION: {
                "existing_setting": "existing_value"
            }
        }
        preference = FrameworkPreference(framework=TestFramework.PYTEST)
        updated = set_framework_preference(settings, preference)

        assert updated["other_key"] == "other_value"
        assert updated[SETTINGS_TEST_SECTION][SETTINGS_FRAMEWORK_KEY] == "pytest"

    def test_framework_preference_to_dict(self):
        """FrameworkPreference serializes to dict."""
        preference = FrameworkPreference(
            framework=TestFramework.VITEST,
            custom_command="npx vitest",
            custom_args=["--reporter=verbose"],
            env_vars={"NODE_ENV": "test"},
            timeout_seconds=600
        )
        data = preference.to_dict()

        assert data["framework"] == "vitest"
        assert data["custom_command"] == "npx vitest"
        assert "--reporter=verbose" in data["custom_args"]
        assert data["env_vars"]["NODE_ENV"] == "test"
        assert data["timeout_seconds"] == 600

    def test_framework_preference_from_dict(self):
        """FrameworkPreference deserializes from dict."""
        data = {
            "framework": "mocha",
            "custom_command": "npx mocha",
            "custom_args": ["--reporter=spec"],
            "env_vars": {"DEBUG": "true"},
            "timeout_seconds": 450
        }
        preference = FrameworkPreference.from_dict(data)

        assert preference.framework == TestFramework.MOCHA
        assert preference.custom_command == "npx mocha"
        assert "--reporter=spec" in preference.custom_args
        assert preference.env_vars["DEBUG"] == "true"
        assert preference.timeout_seconds == 450


# =============================================================================
# Additional Tests: Data Classes and Utilities
# =============================================================================

class TestDataClasses:
    """Tests for data classes."""

    def test_test_framework_enum_values(self):
        """TestFramework enum has expected values."""
        assert TestFramework.PYTEST.value == "pytest"
        assert TestFramework.UNITTEST.value == "unittest"
        assert TestFramework.JEST.value == "jest"
        assert TestFramework.VITEST.value == "vitest"
        assert TestFramework.MOCHA.value == "mocha"
        assert TestFramework.UNKNOWN.value == "unknown"

    def test_test_framework_string_conversion(self):
        """TestFramework converts to string."""
        assert str(TestFramework.PYTEST) == "pytest"
        assert str(TestFramework.JEST) == "jest"

    def test_test_command_to_dict(self):
        """TestCommand serializes to dict."""
        cmd = TestCommand(
            framework=TestFramework.PYTEST,
            command="pytest",
            args=["-v", "--cov"],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            working_directory="/project",
            timeout_seconds=300
        )
        data = cmd.to_dict()

        assert data["framework"] == "pytest"
        assert data["command"] == "pytest"
        assert "-v" in data["args"]
        assert "PYTHONDONTWRITEBYTECODE" in data["env"]
        assert data["full_command"] == "pytest -v --cov"

    def test_test_result_to_dict(self):
        """TestResult serializes to dict."""
        result = TestResult(
            framework=TestFramework.JEST,
            total=10,
            passed=8,
            failed=2,
            skipped=0,
            duration_seconds=5.5,
            exit_code=1,
            failed_tests=["test1", "test2"],
            coverage_percent=85.0,
            success=False
        )
        data = result.to_dict()

        assert data["framework"] == "jest"
        assert data["total"] == 10
        assert data["passed"] == 8
        assert data["failed"] == 2
        assert data["duration_seconds"] == 5.5
        assert data["coverage_percent"] == 85.0
        assert data["success"] is False

    def test_framework_detection_result_to_dict(self):
        """TestFrameworkDetectionResult serializes to dict."""
        result = TestFrameworkDetectionResult(
            framework=TestFramework.PYTEST,
            confidence=0.9,
            detected_from="pytest.ini",
            markers_found=["pytest.ini", "conftest.py"],
            language="python",
            is_from_settings=False
        )
        data = result.to_dict()

        assert data["framework"] == "pytest"
        assert data["confidence"] == 0.9
        assert data["detected_from"] == "pytest.ini"
        assert "pytest.ini" in data["markers_found"]
        assert data["language"] == "python"
        assert data["is_from_settings"] is False


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_supported_frameworks(self):
        """Get list of supported frameworks."""
        frameworks = get_supported_frameworks()
        assert TestFramework.PYTEST in frameworks
        assert TestFramework.JEST in frameworks
        assert TestFramework.VITEST in frameworks
        assert TestFramework.MOCHA in frameworks
        assert TestFramework.UNITTEST in frameworks
        assert TestFramework.UNKNOWN not in frameworks

    def test_get_framework_info(self):
        """Get framework information."""
        info = get_framework_info(TestFramework.PYTEST)

        assert info["name"] == "pytest"
        assert info["language"] == "python"
        assert info["default_command"] == "pytest"
        assert "pytest.ini" in info["config_files"]
        assert "verbose" in info["available_options"]

    def test_get_framework_info_jest(self):
        """Get Jest framework information."""
        info = get_framework_info(TestFramework.JEST)

        assert info["name"] == "jest"
        assert info["language"] == "javascript"
        assert info["default_command"] == "npx jest"
        assert "jest.config.js" in info["config_files"]


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_framework_markers_defined(self):
        """FRAMEWORK_MARKERS has entries for all frameworks."""
        assert TestFramework.PYTEST in FRAMEWORK_MARKERS
        assert TestFramework.JEST in FRAMEWORK_MARKERS
        assert TestFramework.VITEST in FRAMEWORK_MARKERS
        assert TestFramework.MOCHA in FRAMEWORK_MARKERS

    def test_framework_languages_defined(self):
        """FRAMEWORK_LANGUAGES has entries for all frameworks."""
        assert TestFramework.PYTEST in FRAMEWORK_LANGUAGES
        assert FRAMEWORK_LANGUAGES[TestFramework.PYTEST] == "python"
        assert TestFramework.JEST in FRAMEWORK_LANGUAGES
        assert FRAMEWORK_LANGUAGES[TestFramework.JEST] == "javascript"

    def test_default_test_commands_defined(self):
        """DEFAULT_TEST_COMMANDS has entries for all frameworks."""
        assert TestFramework.PYTEST in DEFAULT_TEST_COMMANDS
        assert DEFAULT_TEST_COMMANDS[TestFramework.PYTEST] == "pytest"
        assert TestFramework.JEST in DEFAULT_TEST_COMMANDS
        assert "jest" in DEFAULT_TEST_COMMANDS[TestFramework.JEST]

    def test_test_command_options_defined(self):
        """TEST_COMMAND_OPTIONS has entries for all major frameworks."""
        assert TestFramework.PYTEST in TEST_COMMAND_OPTIONS
        assert "verbose" in TEST_COMMAND_OPTIONS[TestFramework.PYTEST]
        assert TestFramework.JEST in TEST_COMMAND_OPTIONS
        assert "verbose" in TEST_COMMAND_OPTIONS[TestFramework.JEST]


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Tests that Feature #208 components are accessible from api package."""

    def test_import_test_framework_enum(self):
        """TestFramework importable from api package."""
        from api import TestFramework as TF
        assert TF.PYTEST.value == "pytest"

    def test_import_detection_result(self):
        """TestFrameworkDetectionResult importable from api package."""
        from api import TestFrameworkDetectionResult
        assert TestFrameworkDetectionResult is not None

    def test_import_test_command(self):
        """TestCommand importable from api package."""
        from api import TestCommand
        assert TestCommand is not None

    def test_import_test_result(self):
        """TestResult importable from api package."""
        from api import TestResult
        assert TestResult is not None

    def test_import_framework_preference(self):
        """FrameworkPreference importable from api package."""
        from api import FrameworkPreference
        assert FrameworkPreference is not None

    def test_import_detect_framework(self):
        """detect_framework importable from api package."""
        from api import detect_framework as df
        assert callable(df)

    def test_import_generate_test_command(self):
        """generate_test_command importable from api package."""
        from api import generate_test_command as gtc
        assert callable(gtc)

    def test_import_parse_test_output(self):
        """parse_test_output importable from api package."""
        from api import parse_test_output as pto
        assert callable(pto)

    def test_import_constants(self):
        """Constants importable from api package."""
        from api import (
            FRAMEWORK_MARKERS,
            FRAMEWORK_LANGUAGES,
            DEFAULT_TEST_COMMANDS,
            TEST_COMMAND_OPTIONS,
            SETTINGS_FRAMEWORK_KEY,
            SETTINGS_TEST_SECTION,
        )
        assert SETTINGS_FRAMEWORK_KEY == "test_framework"
        assert SETTINGS_TEST_SECTION == "testing"


# =============================================================================
# Feature #208 Verification Steps (Comprehensive)
# =============================================================================

class TestFeature208VerificationSteps:
    """
    Comprehensive tests verifying all 4 feature steps.
    These tests serve as acceptance criteria for Feature #208.
    """

    def test_step_1_framework_detected_from_project_configuration(self, pytest_project):
        """
        Step 1: Framework detected from project configuration

        Verify framework is correctly detected from various project configurations.
        """
        # Test 1: Detection from config file
        result = detect_framework(pytest_project)
        assert result.framework == TestFramework.PYTEST
        assert result.confidence >= 0.5

        # Test 2: Detection includes markers
        assert len(result.markers_found) >= 1

        # Test 3: Detection includes source information
        assert result.detected_from != "none"

        # Test 4: Detection includes language
        assert result.language in ("python", "javascript", "unknown")

    def test_step_2_appropriate_test_commands_generated(self):
        """
        Step 2: Appropriate test commands generated per framework

        Verify correct test commands are generated for each framework.
        """
        # Test all major frameworks
        frameworks = [
            (TestFramework.PYTEST, "pytest"),
            (TestFramework.UNITTEST, "python -m unittest"),
            (TestFramework.JEST, "npx jest"),
            (TestFramework.VITEST, "npx vitest"),
            (TestFramework.MOCHA, "npx mocha"),
        ]

        for framework, expected_cmd in frameworks:
            cmd = generate_test_command(framework)
            assert framework.value in cmd.to_full_command() or expected_cmd.split()[0] in cmd.command
            assert cmd.framework == framework

        # Test with options
        cmd = generate_test_command(TestFramework.PYTEST, options={"verbose": True})
        assert "-v" in cmd.to_full_command()

    def test_step_3_result_parsing_handles_framework_output(self):
        """
        Step 3: Result parsing handles framework-specific output

        Verify each framework's output is correctly parsed.
        """
        # Test pytest parsing
        pytest_output = "====== 5 passed in 0.12s ======"
        result = parse_test_output(TestFramework.PYTEST, pytest_output, 0)
        assert result.passed == 5
        assert result.success is True

        # Test Jest parsing
        jest_output = "Tests:  3 passed, 3 total\nTime:   1.5s"
        result = parse_test_output(TestFramework.JEST, jest_output, 0)
        assert result.passed == 3
        assert result.total == 3

        # Test failure detection
        pytest_failure = "====== 2 failed, 3 passed in 0.5s ======"
        result = parse_test_output(TestFramework.PYTEST, pytest_failure, 1)
        assert result.failed == 2
        assert result.passed == 3
        assert result.success is False

    def test_step_4_framework_preference_configurable(self):
        """
        Step 4: Framework preference configurable in project settings

        Verify framework preference can be set and retrieved from settings.
        """
        # Test setting preference
        settings = {}
        preference = FrameworkPreference(
            framework=TestFramework.VITEST,
            custom_command="npx vitest run",
            timeout_seconds=600
        )
        updated = set_framework_preference(settings, preference)

        # Verify setting was stored
        assert SETTINGS_TEST_SECTION in updated
        assert updated[SETTINGS_TEST_SECTION][SETTINGS_FRAMEWORK_KEY] == "vitest"

        # Verify preference can be retrieved
        retrieved = get_framework_preference(updated)
        assert retrieved is not None
        assert retrieved.framework == TestFramework.VITEST

        # Verify detection uses settings
        with tempfile.TemporaryDirectory() as tmpdir:
            result = detect_framework(tmpdir, settings=updated)
            assert result.framework == TestFramework.VITEST
            assert result.is_from_settings is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
