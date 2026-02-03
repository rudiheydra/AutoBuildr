#!/usr/bin/env python3
"""
Verification Script for Feature #208: Test-runner agent supports multiple test frameworks
========================================================================================

This script verifies all 4 feature steps for Feature #208:
1. Framework detected from project configuration
2. Appropriate test commands generated per framework
3. Result parsing handles framework-specific output
4. Framework preference configurable in project settings

Run with:
    python tests/verify_feature_208.py
"""
import json
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.test_framework import (
    TestFramework,
    TestFrameworkDetectionResult,
    TestCommand,
    TestResult,
    FrameworkPreference,
    detect_framework,
    generate_test_command,
    parse_test_output,
    get_framework_preference,
    set_framework_preference,
    get_supported_frameworks,
    get_framework_info,
    SETTINGS_FRAMEWORK_KEY,
    SETTINGS_TEST_SECTION,
)


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")


def print_step(step: int, text: str) -> None:
    """Print a step header."""
    print(f"\n--- Step {step}: {text} ---")


def print_result(success: bool, message: str) -> None:
    """Print a result with status indicator."""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"  {status}: {message}")


def verify_step_1_framework_detection() -> bool:
    """Verify Step 1: Framework detected from project configuration."""
    print_step(1, "Framework detected from project configuration")
    all_passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1.1: Detect pytest from pytest.ini
        (project_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = detect_framework(project_dir)
        passed = result.framework == TestFramework.PYTEST and result.confidence >= 0.5
        print_result(passed, f"Detect pytest from pytest.ini: {result.framework} (confidence: {result.confidence:.2f})")
        all_passed = all_passed and passed

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1.2: Detect Jest from package.json
        package_json = {
            "devDependencies": {"jest": "^29.0.0"},
            "scripts": {"test": "jest"}
        }
        (project_dir / "package.json").write_text(json.dumps(package_json), encoding="utf-8")
        result = detect_framework(project_dir)
        passed = result.framework == TestFramework.JEST and result.confidence >= 0.7
        print_result(passed, f"Detect Jest from package.json: {result.framework} (confidence: {result.confidence:.2f})")
        all_passed = all_passed and passed

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1.3: Detect Vitest from config file
        (project_dir / "vitest.config.ts").write_text("export default {}", encoding="utf-8")
        result = detect_framework(project_dir)
        passed = result.framework == TestFramework.VITEST and result.confidence >= 0.5
        print_result(passed, f"Detect Vitest from vitest.config.ts: {result.framework} (confidence: {result.confidence:.2f})")
        all_passed = all_passed and passed

    # Test 1.4: Detection includes language information
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        result = detect_framework(project_dir)
        passed = result.language == "python"
        print_result(passed, f"Detection includes language: {result.language}")
        all_passed = all_passed and passed

    # Test 1.5: Settings override detection
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        settings = {SETTINGS_TEST_SECTION: {SETTINGS_FRAMEWORK_KEY: "mocha"}}
        result = detect_framework(project_dir, settings=settings)
        passed = result.framework == TestFramework.MOCHA and result.is_from_settings
        print_result(passed, f"Settings override detection: {result.framework} (from_settings: {result.is_from_settings})")
        all_passed = all_passed and passed

    return all_passed


def verify_step_2_command_generation() -> bool:
    """Verify Step 2: Appropriate test commands generated per framework."""
    print_step(2, "Appropriate test commands generated per framework")
    all_passed = True

    # Test 2.1: Generate pytest command
    cmd = generate_test_command(TestFramework.PYTEST)
    passed = cmd.command == "pytest" and cmd.framework == TestFramework.PYTEST
    print_result(passed, f"Pytest command: {cmd.to_full_command()}")
    all_passed = all_passed and passed

    # Test 2.2: Generate Jest command
    cmd = generate_test_command(TestFramework.JEST)
    passed = cmd.command == "npx jest" and cmd.framework == TestFramework.JEST
    print_result(passed, f"Jest command: {cmd.to_full_command()}")
    all_passed = all_passed and passed

    # Test 2.3: Generate Vitest command
    cmd = generate_test_command(TestFramework.VITEST)
    passed = cmd.command == "npx vitest run" and cmd.framework == TestFramework.VITEST
    print_result(passed, f"Vitest command: {cmd.to_full_command()}")
    all_passed = all_passed and passed

    # Test 2.4: Generate command with options
    cmd = generate_test_command(TestFramework.PYTEST, options={"verbose": True, "coverage": True})
    passed = "-v" in cmd.args and "--cov" in cmd.args
    print_result(passed, f"Pytest with options: {cmd.to_full_command()}")
    all_passed = all_passed and passed

    # Test 2.5: Custom command from preference
    preference = FrameworkPreference(
        framework=TestFramework.PYTEST,
        custom_command="python -m pytest",
        custom_args=["--strict-markers"]
    )
    cmd = generate_test_command(TestFramework.PYTEST, preference=preference)
    passed = cmd.command == "python -m pytest" and "--strict-markers" in cmd.args
    print_result(passed, f"Custom command: {cmd.to_full_command()}")
    all_passed = all_passed and passed

    return all_passed


def verify_step_3_result_parsing() -> bool:
    """Verify Step 3: Result parsing handles framework-specific output."""
    print_step(3, "Result parsing handles framework-specific output")
    all_passed = True

    # Test 3.1: Parse pytest success output
    pytest_output = "============================== 5 passed in 0.12s =============================="
    result = parse_test_output(TestFramework.PYTEST, pytest_output, exit_code=0)
    passed = result.passed == 5 and result.success and result.duration_seconds == 0.12
    print_result(passed, f"Pytest success: {result.passed} passed, {result.duration_seconds}s")
    all_passed = all_passed and passed

    # Test 3.2: Parse pytest failure output
    pytest_failure = "============================== 2 failed, 3 passed in 0.34s ====================="
    result = parse_test_output(TestFramework.PYTEST, pytest_failure, exit_code=1)
    passed = result.failed == 2 and result.passed == 3 and not result.success
    print_result(passed, f"Pytest failure: {result.failed} failed, {result.passed} passed")
    all_passed = all_passed and passed

    # Test 3.3: Parse Jest output
    jest_output = "Tests:  3 passed, 3 total\nTime:   1.5s"
    result = parse_test_output(TestFramework.JEST, jest_output, exit_code=0)
    passed = result.passed == 3 and result.total == 3 and result.duration_seconds == 1.5
    print_result(passed, f"Jest success: {result.passed} passed, {result.total} total")
    all_passed = all_passed and passed

    # Test 3.4: Parse Vitest output
    vitest_output = "Tests  5 passed (5)\nDuration  2.00s"
    result = parse_test_output(TestFramework.VITEST, vitest_output, exit_code=0)
    passed = result.passed == 5 and result.duration_seconds == 2.0
    print_result(passed, f"Vitest success: {result.passed} passed, {result.duration_seconds}s")
    all_passed = all_passed and passed

    # Test 3.5: Parse Mocha output
    mocha_output = "2 passing (100ms)\n1 failing"
    result = parse_test_output(TestFramework.MOCHA, mocha_output, exit_code=1)
    passed = result.passed == 2 and result.failed == 1
    print_result(passed, f"Mocha mixed: {result.passed} passing, {result.failed} failing")
    all_passed = all_passed and passed

    return all_passed


def verify_step_4_settings_preference() -> bool:
    """Verify Step 4: Framework preference configurable in project settings."""
    print_step(4, "Framework preference configurable in project settings")
    all_passed = True

    # Test 4.1: Get preference from settings
    settings = {
        SETTINGS_TEST_SECTION: {
            SETTINGS_FRAMEWORK_KEY: "vitest",
            "custom_command": "npx vitest",
            "timeout_seconds": 600
        }
    }
    preference = get_framework_preference(settings)
    passed = preference is not None and preference.framework == TestFramework.VITEST
    print_result(passed, f"Get preference: {preference.framework if preference else 'None'}")
    all_passed = all_passed and passed

    # Test 4.2: Set preference in settings
    settings = {}
    preference = FrameworkPreference(
        framework=TestFramework.JEST,
        custom_args=["--watchAll=false"],
        timeout_seconds=900
    )
    updated = set_framework_preference(settings, preference)
    passed = updated[SETTINGS_TEST_SECTION][SETTINGS_FRAMEWORK_KEY] == "jest"
    print_result(passed, f"Set preference: {updated[SETTINGS_TEST_SECTION].get(SETTINGS_FRAMEWORK_KEY)}")
    all_passed = all_passed and passed

    # Test 4.3: Preference affects detection
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        # Create a pytest project
        (project_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        # But set preference to mocha
        settings = {SETTINGS_TEST_SECTION: {SETTINGS_FRAMEWORK_KEY: "mocha"}}
        result = detect_framework(project_dir, settings=settings)
        passed = result.framework == TestFramework.MOCHA and result.is_from_settings
        print_result(passed, f"Settings override: {result.framework} (from_settings={result.is_from_settings})")
        all_passed = all_passed and passed

    # Test 4.4: Get supported frameworks
    frameworks = get_supported_frameworks()
    passed = TestFramework.PYTEST in frameworks and TestFramework.JEST in frameworks
    print_result(passed, f"Supported frameworks: {len(frameworks)} frameworks available")
    all_passed = all_passed and passed

    # Test 4.5: Get framework info
    info = get_framework_info(TestFramework.PYTEST)
    passed = info["language"] == "python" and "verbose" in info["available_options"]
    print_result(passed, f"Framework info: {info['name']} ({info['language']})")
    all_passed = all_passed and passed

    return all_passed


def main() -> int:
    """Run all verification steps."""
    print_header("Feature #208 Verification: Test-runner supports multiple frameworks")

    results = []

    # Run all verification steps
    results.append(("Step 1: Framework Detection", verify_step_1_framework_detection()))
    results.append(("Step 2: Command Generation", verify_step_2_command_generation()))
    results.append(("Step 3: Result Parsing", verify_step_3_result_parsing()))
    results.append(("Step 4: Settings Preference", verify_step_4_settings_preference()))

    # Print summary
    print_header("Verification Summary")
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        all_passed = all_passed and passed

    print()
    if all_passed:
        print("🎉 All verification steps PASSED!")
        print("Feature #208: Test-runner agent supports multiple test frameworks - VERIFIED")
        return 0
    else:
        print("❌ Some verification steps FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
