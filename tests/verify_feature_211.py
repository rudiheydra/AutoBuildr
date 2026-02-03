#!/usr/bin/env python
"""
Verification script for Feature #211: Test enforcement gate added to acceptance validators.

This script verifies all 5 feature steps are implemented correctly:
1. Create test_enforcement validator type
2. Validator checks: tests exist, tests ran, tests passed
3. Validator can be required or optional per feature
4. Validator result included in acceptance_results
5. Failed tests block feature completion when required

Run with: python tests/verify_feature_211.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

# Add the project root to the path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_step(step: int, description: str):
    """Print step header."""
    print(f"\n{'='*60}")
    print(f"Step {step}: {description}")
    print('='*60)


def print_pass(message: str):
    """Print pass message."""
    print(f"  ✓ {message}")


def print_fail(message: str):
    """Print fail message."""
    print(f"  ✗ {message}")


@dataclass
class MockEvent:
    """Mock AgentEvent for testing."""
    id: int
    event_type: str
    sequence: int
    payload: dict[str, Any] | None = None


@dataclass
class MockAgentRun:
    """Mock AgentRun for testing."""
    id: str = "test-run-123"
    events: list[MockEvent] = field(default_factory=list)
    turns_used: int = 5


def verify_step1() -> bool:
    """Step 1: Create test_enforcement validator type."""
    print_step(1, "Create test_enforcement validator type")

    try:
        from api.validators import TestEnforcementValidator, VALIDATOR_REGISTRY, get_validator
        from api.agentspec_models import VALIDATOR_TYPES
        from api import TestEnforcementValidator as ExportedValidator

        # Check class exists
        if TestEnforcementValidator is None:
            print_fail("TestEnforcementValidator class not found")
            return False
        print_pass("TestEnforcementValidator class exists")

        # Check validator_type attribute
        validator = TestEnforcementValidator()
        if validator.validator_type != "test_enforcement":
            print_fail(f"validator_type is '{validator.validator_type}', expected 'test_enforcement'")
            return False
        print_pass("validator_type = 'test_enforcement'")

        # Check in registry
        if "test_enforcement" not in VALIDATOR_REGISTRY:
            print_fail("Not registered in VALIDATOR_REGISTRY")
            return False
        print_pass("Registered in VALIDATOR_REGISTRY")

        # Check get_validator works
        v = get_validator("test_enforcement")
        if v is None or not isinstance(v, TestEnforcementValidator):
            print_fail("get_validator('test_enforcement') failed")
            return False
        print_pass("get_validator() returns correct instance")

        # Check in VALIDATOR_TYPES
        if "test_enforcement" not in VALIDATOR_TYPES:
            print_fail("Not in VALIDATOR_TYPES list")
            return False
        print_pass("Added to VALIDATOR_TYPES list")

        # Check exported from api package
        if ExportedValidator is not TestEnforcementValidator:
            print_fail("Not properly exported from api package")
            return False
        print_pass("Exported from api package")

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        return False


def verify_step2() -> bool:
    """Step 2: Validator checks: tests exist, tests ran, tests passed."""
    print_step(2, "Validator checks: tests exist, tests ran, tests passed")

    try:
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()

        # Create temp directory with test files
        with tempfile.TemporaryDirectory() as tmpdir:
            tests_dir = Path(tmpdir) / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_example.py").write_text("def test_foo(): pass")

            # Test: tests exist check
            config = {
                "test_file_pattern": f"{tmpdir}/tests/test_*.py",
                "require_tests_exist": True,
                "require_tests_ran": False,
                "require_tests_passed": False,
            }
            result = validator.evaluate(config, {"project_dir": tmpdir})

            if not result.details["enforcement_status"]["tests_exist"]:
                print_fail("tests_exist check failed when files exist")
                return False
            print_pass("Checks tests_exist: True when files present")

            # Test: tests exist fails when no files
            config_no_files = {
                "test_file_pattern": f"{tmpdir}/nonexistent/test_*.py",
                "require_tests_exist": True,
                "require_tests_ran": False,
                "require_tests_passed": False,
            }
            result = validator.evaluate(config_no_files, {"project_dir": tmpdir})
            if result.details["enforcement_status"]["tests_exist"]:
                print_fail("tests_exist check passed when no files exist")
                return False
            print_pass("Checks tests_exist: False when no files")

            # Test: tests ran check (via context)
            config_ran = {
                "require_tests_exist": False,
                "require_tests_ran": True,
                "require_tests_passed": False,
            }
            context_ran = {
                "project_dir": tmpdir,
                "test_results": {
                    "total_tests": 5,
                    "passed_tests": 5,
                    "failed_tests": 0,
                    "passed": True,
                },
            }
            result = validator.evaluate(config_ran, context_ran)
            if not result.details["enforcement_status"]["tests_ran"]:
                print_fail("tests_ran check failed with test_results context")
                return False
            print_pass("Checks tests_ran: via context test_results")

            # Test: tests ran check (via events)
            config_events = {
                "require_tests_exist": False,
                "require_tests_ran": True,
                "require_tests_passed": False,
                "check_events": True,
            }
            run = MockAgentRun(events=[
                MockEvent(id=1, event_type="tests_executed", sequence=1, payload={
                    "total_tests": 5, "passed_tests": 5, "failed_tests": 0, "passed": True,
                })
            ])
            result = validator.evaluate(config_events, {"project_dir": tmpdir}, run)
            if not result.details["enforcement_status"]["tests_ran"]:
                print_fail("tests_ran check failed with events")
                return False
            print_pass("Checks tests_ran: via tests_executed events")

            # Test: tests passed check
            config_passed = {
                "require_tests_exist": False,
                "require_tests_ran": True,
                "require_tests_passed": True,
            }
            context_passed = {
                "project_dir": tmpdir,
                "test_results": {"total_tests": 5, "passed_tests": 5, "failed_tests": 0, "passed": True},
            }
            result = validator.evaluate(config_passed, context_passed)
            if not result.details["enforcement_status"]["tests_passed"]:
                print_fail("tests_passed check failed with passing tests")
                return False
            print_pass("Checks tests_passed: True when all tests pass")

            # Test: tests passed fails
            context_failed = {
                "project_dir": tmpdir,
                "test_results": {"total_tests": 5, "passed_tests": 3, "failed_tests": 2, "passed": False},
            }
            result = validator.evaluate(config_passed, context_failed)
            if result.details["enforcement_status"]["tests_passed"]:
                print_fail("tests_passed check passed when tests failed")
                return False
            print_pass("Checks tests_passed: False when tests fail")

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step3() -> bool:
    """Step 3: Validator can be required or optional per feature."""
    print_step(3, "Validator can be required or optional per feature")

    try:
        from api.validators import AcceptanceGate

        gate = AcceptanceGate()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test: Required validator blocks gate
            spec_required = {
                "validators": [{
                    "type": "test_enforcement",
                    "config": {
                        "test_file_pattern": f"{tmpdir}/tests/test_*.py",
                        "require_tests_exist": True,
                        "require_tests_ran": False,
                        "require_tests_passed": False,
                    },
                    "required": True,
                }],
                "gate_mode": "all_pass",
            }
            result = gate.evaluate(MockAgentRun(), spec_required, {"project_dir": tmpdir})
            if result.passed:
                print_fail("Required validator should block gate when failing")
                return False
            if not result.required_failed:
                print_fail("required_failed should be True")
                return False
            print_pass("Required validator blocks gate when failing")

            # Test: Optional validator with passing validator in any_pass mode
            spec_optional = {
                "validators": [
                    {
                        "type": "test_enforcement",
                        "config": {"require_tests_exist": True, "require_tests_ran": True},
                        "required": False,
                    },
                    {
                        "type": "custom",
                        "config": {"description": "Always passes"},
                        "required": False,
                    },
                ],
                "gate_mode": "any_pass",
            }
            result = gate.evaluate(MockAgentRun(), spec_optional, {"project_dir": tmpdir})
            if not result.passed:
                print_fail("Optional validator should not block gate in any_pass mode with other passing validator")
                return False
            print_pass("Optional validator is advisory only (doesn't block with passing validator)")

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step4() -> bool:
    """Step 4: Validator result included in acceptance_results."""
    print_step(4, "Validator result included in acceptance_results")

    try:
        from api.validators import AcceptanceGate, TestEnforcementValidator
        import json

        gate = AcceptanceGate()

        with tempfile.TemporaryDirectory() as tmpdir:
            tests_dir = Path(tmpdir) / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_example.py").write_text("def test_foo(): pass")

            spec = {
                "validators": [{
                    "type": "test_enforcement",
                    "config": {
                        "test_file_pattern": f"{tmpdir}/tests/test_*.py",
                        "require_tests_exist": True,
                        "require_tests_ran": False,
                        "require_tests_passed": False,
                    },
                    "required": False,
                }],
                "gate_mode": "all_pass",
            }
            result = gate.evaluate(MockAgentRun(), spec, {"project_dir": tmpdir})

            # Check acceptance_results contains the result
            if len(result.acceptance_results) != 1:
                print_fail(f"Expected 1 acceptance result, got {len(result.acceptance_results)}")
                return False
            print_pass("Result included in acceptance_results array")

            enforcement_result = result.acceptance_results[0]

            # Check type
            if enforcement_result.get("type") != "test_enforcement":
                print_fail(f"Result type is '{enforcement_result.get('type')}', expected 'test_enforcement'")
                return False
            print_pass("Result has correct type")

            # Check required fields
            for field in ["passed", "message", "details"]:
                if field not in enforcement_result:
                    print_fail(f"Missing required field: {field}")
                    return False
            print_pass("Result contains passed, message, details")

            # Check enforcement_status in details
            if "enforcement_status" not in enforcement_result.get("details", {}):
                print_fail("Missing enforcement_status in details")
                return False
            print_pass("Result contains enforcement_status in details")

            # Check JSON serializable
            validator = TestEnforcementValidator()
            config = {"require_tests_exist": True, "require_tests_ran": False, "require_tests_passed": False}
            val_result = validator.evaluate(config, {"project_dir": tmpdir})
            result_dict = val_result.to_dict()
            try:
                json.dumps(result_dict)
                print_pass("ValidatorResult.to_dict() is JSON serializable")
            except Exception as e:
                print_fail(f"Not JSON serializable: {e}")
                return False

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step5() -> bool:
    """Step 5: Failed tests block feature completion when required."""
    print_step(5, "Failed tests block feature completion when required")

    try:
        from api.validators import AcceptanceGate

        gate = AcceptanceGate()

        with tempfile.TemporaryDirectory() as tmpdir:
            spec = {
                "validators": [{
                    "type": "test_enforcement",
                    "config": {
                        "require_tests_exist": False,
                        "require_tests_ran": True,
                        "require_tests_passed": True,
                    },
                    "required": True,
                }],
                "gate_mode": "all_pass",
            }

            # Test: Failed tests block completion
            run_failed = MockAgentRun(events=[
                MockEvent(id=1, event_type="tests_executed", sequence=1, payload={
                    "total_tests": 10, "passed_tests": 5, "failed_tests": 5, "passed": False,
                })
            ])
            result = gate.evaluate(run_failed, spec, {"project_dir": tmpdir})
            if result.passed:
                print_fail("Failed tests should block gate when required")
                return False
            if result.verdict != "failed":
                print_fail(f"Verdict should be 'failed', got '{result.verdict}'")
                return False
            print_pass("Failed tests block feature completion (verdict=failed)")

            # Test: Passing tests allow completion
            run_passed = MockAgentRun(events=[
                MockEvent(id=1, event_type="tests_executed", sequence=1, payload={
                    "total_tests": 10, "passed_tests": 10, "failed_tests": 0, "passed": True,
                })
            ])
            result = gate.evaluate(run_passed, spec, {"project_dir": tmpdir})
            if not result.passed:
                print_fail("Passing tests should allow gate when required")
                return False
            if result.verdict != "passed":
                print_fail(f"Verdict should be 'passed', got '{result.verdict}'")
                return False
            print_pass("Passing tests allow feature completion (verdict=passed)")

            # Test: Missing tests block when tests_exist required
            spec_exist = {
                "validators": [{
                    "type": "test_enforcement",
                    "config": {
                        "test_file_pattern": f"{tmpdir}/tests/test_*.py",
                        "require_tests_exist": True,
                        "require_tests_ran": False,
                        "require_tests_passed": False,
                    },
                    "required": True,
                }],
                "gate_mode": "all_pass",
            }
            result = gate.evaluate(MockAgentRun(), spec_exist, {"project_dir": tmpdir})
            if result.passed:
                print_fail("Missing test files should block when tests_exist required")
                return False
            print_pass("Missing test files block when require_tests_exist=True")

            # Test: Not executed tests block when tests_ran required
            spec_ran = {
                "validators": [{
                    "type": "test_enforcement",
                    "config": {
                        "require_tests_exist": False,
                        "require_tests_ran": True,
                        "require_tests_passed": False,
                    },
                    "required": True,
                }],
                "gate_mode": "all_pass",
            }
            result = gate.evaluate(MockAgentRun(events=[]), spec_ran, {"project_dir": tmpdir})
            if result.passed:
                print_fail("Not executed tests should block when tests_ran required")
                return False
            print_pass("Not executed tests block when require_tests_ran=True")

        return True

    except Exception as e:
        print_fail(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification steps."""
    print("\n" + "="*60)
    print("Feature #211: Test enforcement gate added to acceptance validators")
    print("="*60)

    results = {
        1: verify_step1(),
        2: verify_step2(),
        3: verify_step3(),
        4: verify_step4(),
        5: verify_step5(),
    }

    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)

    all_passed = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  Step {step}: {status}")
        if not passed:
            all_passed = False

    print("-"*60)
    if all_passed:
        print("ALL STEPS PASSED - Feature #211 verified successfully!")
        return 0
    else:
        print("SOME STEPS FAILED - Feature #211 not fully verified.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
