#!/usr/bin/env python3
"""
Verification Script for Feature #205: Test-runner agent archetype defined
========================================================================

This script verifies all 5 feature steps are implemented correctly.

Feature Steps:
1. Test-runner archetype includes tools: Bash, Read, Write, Glob, Grep
2. Default skills: pytest, unittest, test discovery
3. Responsibilities: write tests, run tests, report results
4. Model: sonnet (balanced speed/capability)
5. Archetype used by Octo when test execution needed

Run with:
    python tests/verify_feature_205.py
"""
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_status(step: int, name: str, passed: bool, details: str = "") -> None:
    """Print step verification status."""
    status = "PASS" if passed else "FAIL"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"  Step {step}: {name} - {color}{status}{reset}")
    if details:
        print(f"    {details}")


def verify_step_1() -> bool:
    """Step 1: Test-runner archetype includes tools: Bash, Read, Write, Glob, Grep"""
    from api.archetypes import get_archetype

    archetype = get_archetype("test-runner")
    if archetype is None:
        return False

    required_tools = {"Bash", "Read", "Write", "Glob", "Grep"}
    actual_tools = set(archetype.default_tools)
    missing_tools = required_tools - actual_tools

    passed = len(missing_tools) == 0
    if passed:
        details = f"All required tools present: {', '.join(sorted(required_tools))}"
    else:
        details = f"Missing tools: {', '.join(sorted(missing_tools))}"
    print_status(1, "Required tools: Bash, Read, Write, Glob, Grep", passed, details)
    return passed


def verify_step_2() -> bool:
    """Step 2: Default skills: pytest, unittest, test discovery"""
    from api.archetypes import get_archetype

    archetype = get_archetype("test-runner")
    if archetype is None:
        return False

    required_skills = {"pytest", "unittest", "test discovery"}
    actual_skills = set(archetype.default_skills)
    missing_skills = required_skills - actual_skills

    passed = len(missing_skills) == 0
    if passed:
        details = f"All required skills present: {', '.join(sorted(required_skills))}"
    else:
        details = f"Missing skills: {', '.join(sorted(missing_skills))}"
    print_status(2, "Default skills: pytest, unittest, test discovery", passed, details)
    return passed


def verify_step_3() -> bool:
    """Step 3: Responsibilities: write tests, run tests, report results"""
    from api.archetypes import get_archetype

    archetype = get_archetype("test-runner")
    if archetype is None:
        return False

    responsibilities_text = " ".join(r.lower() for r in archetype.responsibilities)

    has_write_tests = "write" in responsibilities_text and "test" in responsibilities_text
    has_run_tests = "run" in responsibilities_text and "test" in responsibilities_text
    has_report_results = "report" in responsibilities_text

    passed = has_write_tests and has_run_tests and has_report_results
    missing = []
    if not has_write_tests:
        missing.append("write tests")
    if not has_run_tests:
        missing.append("run tests")
    if not has_report_results:
        missing.append("report results")

    if passed:
        details = "All responsibilities: write tests, run tests, report results"
    else:
        details = f"Missing responsibilities: {', '.join(missing)}"
    print_status(3, "Responsibilities: write tests, run tests, report results", passed, details)
    return passed


def verify_step_4() -> bool:
    """Step 4: Model: sonnet (balanced speed/capability)"""
    from api.archetypes import get_archetype

    archetype = get_archetype("test-runner")
    if archetype is None:
        return False

    passed = archetype.recommended_model == "sonnet"
    details = f"Model: {archetype.recommended_model}"
    print_status(4, "Model: sonnet", passed, details)
    return passed


def verify_step_5() -> bool:
    """Step 5: Archetype used by Octo when test execution needed"""
    from api.archetypes import (
        map_capability_to_archetype,
        get_archetype_for_task_type,
        archetype_exists,
    )

    # Test 1: 'testing' capability maps to test-runner
    result = map_capability_to_archetype("testing")
    maps_correctly = result.archetype_name == "test-runner" and not result.is_custom_needed

    # Test 2: task type 'testing' returns test-runner
    archetype = get_archetype_for_task_type("testing")
    task_type_correct = archetype is not None and archetype.name == "test-runner"

    # Test 3: archetype exists in catalog
    exists = archetype_exists("test-runner")

    passed = maps_correctly and task_type_correct and exists
    checks = []
    checks.append(f"testing->test-runner: {'OK' if maps_correctly else 'FAIL'}")
    checks.append(f"task_type->test-runner: {'OK' if task_type_correct else 'FAIL'}")
    checks.append(f"archetype_exists: {'OK' if exists else 'FAIL'}")
    details = ", ".join(checks)
    print_status(5, "Archetype used by Octo for test execution", passed, details)
    return passed


def main() -> int:
    """Run all verification steps."""
    print("\n" + "=" * 70)
    print("Feature #205: Test-runner agent archetype defined")
    print("=" * 70)
    print()

    results = []
    results.append(verify_step_1())
    results.append(verify_step_2())
    results.append(verify_step_3())
    results.append(verify_step_4())
    results.append(verify_step_5())

    print()
    passed_count = sum(results)
    total_count = len(results)
    all_passed = all(results)

    if all_passed:
        print(f"\033[92mAll {total_count}/{total_count} verification steps PASSED\033[0m")
    else:
        print(f"\033[91m{passed_count}/{total_count} verification steps passed\033[0m")

    print("=" * 70)
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
