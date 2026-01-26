#!/usr/bin/env python3
"""
Verification Script for Feature #35: Acceptance Gate Orchestration
===================================================================

This script verifies that the AcceptanceGate class correctly implements
all feature requirements.

Feature Steps:
1. Create AcceptanceGate class with evaluate(run, acceptance_spec) method
2. Iterate through validators array
3. Instantiate appropriate validator class for each type
4. Execute validator and collect ValidatorResult
5. Check required flag - required validators must always pass
6. For all_pass mode: verdict = passed if all passed
7. For any_pass mode: verdict = passed if any passed
8. Build acceptance_results array with per-validator outcomes
9. Set AgentRun.final_verdict based on gate result
10. Store acceptance_results JSON in AgentRun
11. Return overall verdict
"""

import sys
import tempfile
import inspect
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_result(step: int, description: str, passed: bool, details: str = ""):
    """Print verification result."""
    status = "PASS" if passed else "FAIL"
    print(f"  Step {step}: {description} - {status}")
    if details:
        print(f"    -> {details}")


def verify_step_1():
    """Step 1: Create AcceptanceGate class with evaluate(run, acceptance_spec) method."""
    from api.validators import AcceptanceGate

    # Check class exists
    if AcceptanceGate is None:
        return False, "AcceptanceGate class not found"

    # Check evaluate method exists
    gate = AcceptanceGate()
    if not hasattr(gate, "evaluate"):
        return False, "evaluate method not found"

    # Check evaluate method signature
    sig = inspect.signature(gate.evaluate)
    params = list(sig.parameters.keys())

    if "run" not in params:
        return False, f"evaluate() missing 'run' parameter, has: {params}"

    if "acceptance_spec" not in params:
        return False, f"evaluate() missing 'acceptance_spec' parameter, has: {params}"

    return True, f"AcceptanceGate class created with evaluate({', '.join(params)})"


def verify_step_2():
    """Step 2: Iterate through validators array."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "f1.txt"
        f2 = Path(tmp_dir) / "f2.txt"
        f3 = Path(tmp_dir) / "f3.txt"
        f1.write_text("1")
        f2.write_text("2")
        f3.write_text("3")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
                {"type": "file_exists", "config": {"path": str(f2)}, "required": False},
                {"type": "file_exists", "config": {"path": str(f3)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if len(result.validator_results) != 3:
            return False, f"Expected 3 validator results, got {len(result.validator_results)}"

        if len(result.acceptance_results) != 3:
            return False, f"Expected 3 acceptance results, got {len(result.acceptance_results)}"

    return True, "All 3 validators were iterated and evaluated"


def verify_step_3():
    """Step 3: Instantiate appropriate validator class for each type."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "test.txt"
        f1.write_text("test")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
                {"type": "test_pass", "config": {"command": "true"}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        result = gate.evaluate(mock_run, spec)

        # Check each validator type was used
        types_used = [ar["type"] for ar in result.acceptance_results]

        if "file_exists" not in types_used:
            return False, "file_exists validator not instantiated"

        if "test_pass" not in types_used:
            return False, "test_pass validator not instantiated"

    return True, f"Validator types instantiated: {types_used}"


def verify_step_4():
    """Step 4: Execute validator and collect ValidatorResult."""
    from api.validators import AcceptanceGate, ValidatorResult

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "test.txt"
        f1.write_text("test")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if not result.validator_results:
            return False, "No validator results collected"

        vr = result.validator_results[0]
        if not isinstance(vr, ValidatorResult):
            return False, f"Expected ValidatorResult, got {type(vr)}"

        if vr.passed is not True:
            return False, f"Expected passed=True, got {vr.passed}"

        if not vr.message:
            return False, "ValidatorResult missing message"

    return True, f"ValidatorResult collected: passed={vr.passed}, message='{vr.message[:50]}...'"


def verify_step_5():
    """Step 5: Check required flag - required validators must always pass."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        optional = Path(tmp_dir) / "optional.txt"
        optional.write_text("test")

        spec = {
            "validators": [
                # Required validator that fails
                {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": True},
                # Optional validator that passes
                {"type": "file_exists", "config": {"path": str(optional)}, "required": False},
            ],
            "gate_mode": "any_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if result.passed is True:
            return False, "Gate should fail when required validator fails"

        if result.required_failed is not True:
            return False, f"required_failed should be True, got {result.required_failed}"

    return True, "Required validator failure correctly causes gate failure"


def verify_step_6():
    """Step 6: For all_pass mode: verdict = passed if all passed."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "f1.txt"
        f2 = Path(tmp_dir) / "f2.txt"
        f1.write_text("1")
        f2.write_text("2")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
                {"type": "file_exists", "config": {"path": str(f2)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if result.passed is not True:
            return False, f"Expected passed=True, got {result.passed}"

        if result.verdict != "passed":
            return False, f"Expected verdict='passed', got '{result.verdict}'"

    return True, "all_pass mode: verdict=passed when all validators pass"


def verify_step_7():
    """Step 7: For any_pass mode: verdict = passed if any passed."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        exists = Path(tmp_dir) / "exists.txt"
        exists.write_text("test")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(exists)}, "required": False},
                {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": False},
            ],
            "gate_mode": "any_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if result.passed is not True:
            return False, f"Expected passed=True, got {result.passed}"

        if result.verdict != "passed":
            return False, f"Expected verdict='passed', got '{result.verdict}'"

    return True, "any_pass mode: verdict=passed when any validator passes"


def verify_step_8():
    """Step 8: Build acceptance_results array with per-validator outcomes."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "test.txt"
        f1.write_text("test")

        spec = {
            "validators": [
                {
                    "type": "file_exists",
                    "config": {"path": str(f1)},
                    "weight": 2.5,
                    "required": True,
                },
            ],
            "gate_mode": "all_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if not result.acceptance_results:
            return False, "No acceptance_results built"

        ar = result.acceptance_results[0]

        required_fields = ["index", "type", "passed", "message", "score", "required", "weight"]
        missing_fields = [f for f in required_fields if f not in ar]

        if missing_fields:
            return False, f"Missing fields in acceptance_results: {missing_fields}"

        if ar["index"] != 0:
            return False, f"Expected index=0, got {ar['index']}"

        if ar["type"] != "file_exists":
            return False, f"Expected type='file_exists', got '{ar['type']}'"

        if ar["weight"] != 2.5:
            return False, f"Expected weight=2.5, got {ar['weight']}"

        if ar["required"] is not True:
            return False, f"Expected required=True, got {ar['required']}"

    return True, f"acceptance_results built with all fields: {list(ar.keys())}"


def verify_step_9():
    """Step 9: Set AgentRun.final_verdict based on gate result."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.final_verdict = None
    mock_run.acceptance_results = None
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "test.txt"
        f1.write_text("test")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        gate.evaluate_and_update_run(mock_run, spec)

        if mock_run.final_verdict != "passed":
            return False, f"Expected final_verdict='passed', got '{mock_run.final_verdict}'"

    return True, f"AgentRun.final_verdict set to '{mock_run.final_verdict}'"


def verify_step_10():
    """Step 10: Store acceptance_results JSON in AgentRun."""
    from api.validators import AcceptanceGate

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.final_verdict = None
    mock_run.acceptance_results = None
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "test.txt"
        f1.write_text("test")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        gate.evaluate_and_update_run(mock_run, spec)

        if mock_run.acceptance_results is None:
            return False, "acceptance_results not stored in AgentRun"

        if not isinstance(mock_run.acceptance_results, list):
            return False, f"Expected list, got {type(mock_run.acceptance_results)}"

        if len(mock_run.acceptance_results) != 1:
            return False, f"Expected 1 result, got {len(mock_run.acceptance_results)}"

    return True, f"acceptance_results stored in AgentRun ({len(mock_run.acceptance_results)} entries)"


def verify_step_11():
    """Step 11: Return overall verdict."""
    from api.validators import AcceptanceGate, GateResult

    gate = AcceptanceGate()
    mock_run = MagicMock()
    mock_run.id = "test-run"
    mock_run.events = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        f1 = Path(tmp_dir) / "test.txt"
        f1.write_text("test")

        spec = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(f1)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        result = gate.evaluate(mock_run, spec)

        if not isinstance(result, GateResult):
            return False, f"Expected GateResult, got {type(result)}"

        if result.verdict not in ("passed", "failed", "partial"):
            return False, f"Invalid verdict: '{result.verdict}'"

    return True, f"GateResult returned with verdict='{result.verdict}'"


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #35: Acceptance Gate Orchestration")
    print("=" * 60)
    print()

    steps = [
        (1, "Create AcceptanceGate class with evaluate method", verify_step_1),
        (2, "Iterate through validators array", verify_step_2),
        (3, "Instantiate appropriate validator class for each type", verify_step_3),
        (4, "Execute validator and collect ValidatorResult", verify_step_4),
        (5, "Check required flag - required validators must always pass", verify_step_5),
        (6, "For all_pass mode: verdict = passed if all passed", verify_step_6),
        (7, "For any_pass mode: verdict = passed if any passed", verify_step_7),
        (8, "Build acceptance_results array with per-validator outcomes", verify_step_8),
        (9, "Set AgentRun.final_verdict based on gate result", verify_step_9),
        (10, "Store acceptance_results JSON in AgentRun", verify_step_10),
        (11, "Return overall verdict", verify_step_11),
    ]

    all_passed = True
    passed_count = 0

    for step_num, description, verify_func in steps:
        try:
            passed, details = verify_func()
            print_result(step_num, description, passed, details)
            if passed:
                passed_count += 1
            else:
                all_passed = False
        except Exception as e:
            print_result(step_num, description, False, f"Exception: {e}")
            all_passed = False

    print()
    print("=" * 60)
    print(f"SUMMARY: {passed_count}/{len(steps)} steps passed")
    print("=" * 60)

    if all_passed:
        print("\nAll verification steps PASSED!")
        print("Feature #35: Acceptance Gate Orchestration is COMPLETE")
        return 0
    else:
        print("\nSome verification steps FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
