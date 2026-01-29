#!/usr/bin/env python3
"""
Feature #8 Verification Script: AcceptanceSpec Pydantic Schemas
===============================================================

This script verifies all acceptance criteria for Feature #8:
1. ValidatorConfig model with type, config dict, weight, required fields
2. AcceptanceSpecCreate with validators array, gate_mode, min_score, retry_policy, max_retries
3. Field validator for gate_mode in [all_pass, any_pass, weighted]
4. Field validator for retry_policy in [none, fixed, exponential]
5. Field validator for min_score range 0.0-1.0 when gate_mode is weighted
6. AcceptanceSpecResponse matching database model output

Run with: python tests/verify_feature_8.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pydantic import ValidationError

# Import schemas
from server.schemas.agentspec import (
    Validator,
    AcceptanceSpecCreate,
    AcceptanceSpecResponse,
    GATE_MODES,
    RETRY_POLICIES,
    VALIDATOR_TYPES,
)


def test_step(step_num: int, description: str):
    """Decorator-like function to print test step info."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print('='*60)


def verify_step_1_validator_config():
    """Step 1: Define ValidatorConfig model with type, config dict, weight, required fields"""
    test_step(1, "ValidatorConfig model with type, config dict, weight, required fields")

    # Test valid validator
    validator = Validator(
        type="test_pass",
        config={"command": "pytest tests/"},
        weight=1.5,
        required=True
    )

    assert validator.type == "test_pass", "type field should be set"
    assert validator.config == {"command": "pytest tests/"}, "config dict should be set"
    assert validator.weight == 1.5, "weight should be 1.5"
    assert validator.required is True, "required should be True"
    print("  [PASS] Valid validator created with all fields")

    # Test defaults
    validator_defaults = Validator(
        type="file_exists",
        config={"path": "/tmp/test.txt"}
    )
    assert validator_defaults.weight == 1.0, "Default weight should be 1.0"
    assert validator_defaults.required is False, "Default required should be False"
    print("  [PASS] Validator defaults work correctly")

    # Test weight bounds
    try:
        Validator(type="test_pass", config={}, weight=-1.0)
        print("  [FAIL] Should reject negative weight")
        return False
    except ValidationError:
        print("  [PASS] Rejects weight below 0.0")

    try:
        Validator(type="test_pass", config={}, weight=15.0)
        print("  [FAIL] Should reject weight above 10.0")
        return False
    except ValidationError:
        print("  [PASS] Rejects weight above 10.0")

    # Test invalid validator type
    try:
        Validator(type="invalid_type", config={})
        print("  [FAIL] Should reject invalid validator type")
        return False
    except ValidationError:
        print("  [PASS] Rejects invalid validator type")

    # Test all valid validator types
    for vtype in ["test_pass", "file_exists", "lint_clean", "forbidden_patterns", "custom"]:
        v = Validator(type=vtype, config={})
        assert v.type == vtype
    print(f"  [PASS] All validator types work: {list(VALIDATOR_TYPES.__args__)}")

    print("\n  STEP 1 RESULT: PASS")
    return True


def verify_step_2_acceptancespec_create():
    """Step 2: Define AcceptanceSpecCreate with all required fields"""
    test_step(2, "AcceptanceSpecCreate with validators array, gate_mode, min_score, retry_policy, max_retries")

    # Test valid creation
    spec = AcceptanceSpecCreate(
        validators=[
            Validator(type="test_pass", config={"command": "pytest"}),
            Validator(type="file_exists", config={"path": "/tmp/out.txt"})
        ],
        gate_mode="all_pass",
        min_score=None,
        retry_policy="fixed",
        max_retries=3
    )

    assert len(spec.validators) == 2, "Should have 2 validators"
    assert spec.gate_mode == "all_pass"
    assert spec.min_score is None
    assert spec.retry_policy == "fixed"
    assert spec.max_retries == 3
    print("  [PASS] AcceptanceSpecCreate with all fields")

    # Test defaults
    spec_defaults = AcceptanceSpecCreate(
        validators=[Validator(type="test_pass", config={})]
    )
    assert spec_defaults.gate_mode == "all_pass", "Default gate_mode should be all_pass"
    assert spec_defaults.retry_policy == "none", "Default retry_policy should be none"
    assert spec_defaults.max_retries == 0, "Default max_retries should be 0"
    assert spec_defaults.fallback_spec_id is None
    print("  [PASS] Default values work correctly")

    # Test validators array bounds
    try:
        AcceptanceSpecCreate(validators=[])
        print("  [FAIL] Should reject empty validators array")
        return False
    except ValidationError:
        print("  [PASS] Rejects empty validators array (min_length=1)")

    # Test max_retries bounds
    try:
        AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            max_retries=100
        )
        print("  [FAIL] Should reject max_retries > 10")
        return False
    except ValidationError:
        print("  [PASS] Rejects max_retries > 10")

    print("\n  STEP 2 RESULT: PASS")
    return True


def verify_step_3_gate_mode_validator():
    """Step 3: Add Field validator for gate_mode in [all_pass, any_pass, weighted]"""
    test_step(3, "Field validator for gate_mode in [all_pass, any_pass, weighted]")

    # Test all valid gate modes
    for mode in ["all_pass", "any_pass", "weighted"]:
        kwargs = {
            "validators": [Validator(type="test_pass", config={})],
            "gate_mode": mode
        }
        if mode == "weighted":
            kwargs["min_score"] = 0.5

        spec = AcceptanceSpecCreate(**kwargs)
        assert spec.gate_mode == mode
        print(f"  [PASS] gate_mode='{mode}' accepted")

    # Test invalid gate mode
    try:
        AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            gate_mode="invalid_mode"
        )
        print("  [FAIL] Should reject invalid gate_mode")
        return False
    except ValidationError as e:
        error_msg = str(e)
        assert "gate_mode" in error_msg.lower() or "all_pass" in error_msg.lower()
        print("  [PASS] Rejects invalid gate_mode 'invalid_mode'")

    print("\n  STEP 3 RESULT: PASS")
    return True


def verify_step_4_retry_policy_validator():
    """Step 4: Add Field validator for retry_policy in [none, fixed, exponential]"""
    test_step(4, "Field validator for retry_policy in [none, fixed, exponential]")

    # Test all valid retry policies
    for policy in ["none", "fixed", "exponential"]:
        spec = AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            retry_policy=policy
        )
        assert spec.retry_policy == policy
        print(f"  [PASS] retry_policy='{policy}' accepted")

    # Test invalid retry policy
    try:
        AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            retry_policy="invalid_policy"
        )
        print("  [FAIL] Should reject invalid retry_policy")
        return False
    except ValidationError as e:
        error_msg = str(e)
        assert "retry_policy" in error_msg.lower() or "none" in error_msg.lower()
        print("  [PASS] Rejects invalid retry_policy 'invalid_policy'")

    print("\n  STEP 4 RESULT: PASS")
    return True


def verify_step_5_min_score_weighted_validation():
    """Step 5: Add Field validator for min_score range 0.0-1.0 when gate_mode is weighted"""
    test_step(5, "Field validator for min_score range 0.0-1.0 when gate_mode is weighted")

    # Test weighted mode requires min_score
    try:
        AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            gate_mode="weighted",
            min_score=None  # Missing min_score for weighted mode
        )
        print("  [FAIL] Should require min_score when gate_mode is 'weighted'")
        return False
    except ValidationError as e:
        error_msg = str(e)
        assert "min_score" in error_msg.lower() and "weighted" in error_msg.lower()
        print("  [PASS] Requires min_score when gate_mode is 'weighted'")

    # Test weighted mode with valid min_score
    spec = AcceptanceSpecCreate(
        validators=[Validator(type="test_pass", config={})],
        gate_mode="weighted",
        min_score=0.75
    )
    assert spec.min_score == 0.75
    print("  [PASS] Accepts weighted mode with min_score=0.75")

    # Test min_score range validation (0.0-1.0)
    for score in [0.0, 0.5, 1.0]:
        spec = AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            gate_mode="weighted",
            min_score=score
        )
        assert spec.min_score == score
        print(f"  [PASS] min_score={score} accepted (within 0.0-1.0)")

    # Test min_score below 0.0
    try:
        AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            gate_mode="weighted",
            min_score=-0.1
        )
        print("  [FAIL] Should reject min_score < 0.0")
        return False
    except ValidationError:
        print("  [PASS] Rejects min_score=-0.1 (below 0.0)")

    # Test min_score above 1.0
    try:
        AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            gate_mode="weighted",
            min_score=1.5
        )
        print("  [FAIL] Should reject min_score > 1.0")
        return False
    except ValidationError:
        print("  [PASS] Rejects min_score=1.5 (above 1.0)")

    # Test non-weighted modes don't require min_score
    for mode in ["all_pass", "any_pass"]:
        spec = AcceptanceSpecCreate(
            validators=[Validator(type="test_pass", config={})],
            gate_mode=mode,
            min_score=None
        )
        assert spec.min_score is None
        print(f"  [PASS] gate_mode='{mode}' doesn't require min_score")

    print("\n  STEP 5 RESULT: PASS")
    return True


def verify_step_6_acceptancespec_response():
    """Step 6: Define AcceptanceSpecResponse matching database model output"""
    test_step(6, "AcceptanceSpecResponse matching database model output")

    # Simulate database model to_dict() output
    db_output = {
        "id": "abc12345-6789-def0-1234-567890abcdef",
        "agent_spec_id": "spec12345-6789-def0-1234-567890abcdef",
        "validators": [
            {"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": True}
        ],
        "gate_mode": "all_pass",
        "min_score": None,
        "retry_policy": "fixed",
        "max_retries": 3,
        "fallback_spec_id": None
    }

    # Create response from db output
    response = AcceptanceSpecResponse(**db_output)

    assert response.id == db_output["id"]
    assert response.agent_spec_id == db_output["agent_spec_id"]
    assert response.validators == db_output["validators"]
    assert response.gate_mode == db_output["gate_mode"]
    assert response.min_score == db_output["min_score"]
    assert response.retry_policy == db_output["retry_policy"]
    assert response.max_retries == db_output["max_retries"]
    assert response.fallback_spec_id == db_output["fallback_spec_id"]
    print("  [PASS] AcceptanceSpecResponse matches database model output")

    # Test with weighted mode and min_score
    db_output_weighted = {
        "id": "weighted-123",
        "agent_spec_id": "spec-456",
        "validators": [
            {"type": "file_exists", "config": {"path": "/tmp/out"}, "weight": 2.0, "required": False}
        ],
        "gate_mode": "weighted",
        "min_score": 0.8,
        "retry_policy": "exponential",
        "max_retries": 5,
        "fallback_spec_id": "fallback-789"
    }

    response_weighted = AcceptanceSpecResponse(**db_output_weighted)
    assert response_weighted.gate_mode == "weighted"
    assert response_weighted.min_score == 0.8
    assert response_weighted.retry_policy == "exponential"
    assert response_weighted.fallback_spec_id == "fallback-789"
    print("  [PASS] AcceptanceSpecResponse handles weighted mode with all fields")

    # Test response validates gate_mode
    try:
        AcceptanceSpecResponse(
            id="test",
            agent_spec_id="spec",
            validators=[],
            gate_mode="invalid_mode",
            retry_policy="none",
            max_retries=0
        )
        print("  [FAIL] Response should validate gate_mode")
        return False
    except ValidationError:
        print("  [PASS] Response validates gate_mode enum")

    # Test response validates retry_policy
    try:
        AcceptanceSpecResponse(
            id="test",
            agent_spec_id="spec",
            validators=[],
            gate_mode="all_pass",
            retry_policy="invalid_policy",
            max_retries=0
        )
        print("  [FAIL] Response should validate retry_policy")
        return False
    except ValidationError:
        print("  [PASS] Response validates retry_policy enum")

    print("\n  STEP 6 RESULT: PASS")
    return True


def main():
    """Run all verification steps."""
    print("="*60)
    print("Feature #8 Verification: AcceptanceSpec Pydantic Schemas")
    print("="*60)

    results = []

    # Run all verification steps
    results.append(("Step 1", verify_step_1_validator_config()))
    results.append(("Step 2", verify_step_2_acceptancespec_create()))
    results.append(("Step 3", verify_step_3_gate_mode_validator()))
    results.append(("Step 4", verify_step_4_retry_policy_validator()))
    results.append(("Step 5", verify_step_5_min_score_weighted_validation()))
    results.append(("Step 6", verify_step_6_acceptancespec_response()))

    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)

    all_passed = True
    for step_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {step_name}: {status}")
        if not passed:
            all_passed = False

    print("-"*60)
    if all_passed:
        print("OVERALL RESULT: ALL STEPS PASSED")
        print("Feature #8 verification complete!")
        return 0
    else:
        print("OVERALL RESULT: SOME STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
