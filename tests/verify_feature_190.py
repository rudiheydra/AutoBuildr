#!/usr/bin/env python3
"""
Verification script for Feature #190: Octo handles malformed project context gracefully
========================================================================================

This script verifies all 4 feature steps:
1. Octo validates OctoRequestPayload on receipt
2. Missing required fields produce clear error messages
3. Partial context triggers warnings but proceeds with defaults
4. Validation errors returned to Maestro with remediation hints
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.octo import (
    Octo,
    OctoRequestPayload,
    PayloadValidationError,
    PayloadValidationResult,
    _PROJECT_CONTEXT_DEFAULTS,
    VALID_MODELS,
    DEFAULT_MODEL,
)


def print_header(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step_num: int, description: str):
    """Print a step indicator."""
    print(f"\n[Step {step_num}] {description}")
    print("-" * 50)


def verify_step1():
    """Step 1: Octo validates OctoRequestPayload on receipt."""
    print_step(1, "Octo validates OctoRequestPayload on receipt")

    # Test 1: Valid payload passes validation
    valid_payload = OctoRequestPayload(
        project_context={"name": "TestApp", "tech_stack": ["python"]},
        required_capabilities=["e2e_testing"],
    )
    result = valid_payload.validate_detailed()
    assert result.is_valid, "Valid payload should pass validation"
    print("  ✓ Valid payload passes validation")

    # Test 2: Invalid payload fails validation
    invalid_payload = OctoRequestPayload(
        project_context="not a dict",
        required_capabilities=[],
    )
    result = invalid_payload.validate_detailed()
    assert not result.is_valid, "Invalid payload should fail validation"
    assert len(result.errors) > 0, "Should have errors for invalid payload"
    print("  ✓ Invalid payload fails validation with errors")

    # Test 3: Validation happens on generate_specs
    octo = Octo()
    response = octo.generate_specs(invalid_payload)
    assert not response.success, "Octo should reject invalid payload"
    assert response.error_type == "validation_error", "Error type should be validation_error"
    print("  ✓ Octo.generate_specs validates payload on receipt")

    return True


def verify_step2():
    """Step 2: Missing required fields produce clear error messages."""
    print_step(2, "Missing required fields produce clear error messages")

    # Test various invalid payloads
    test_cases = [
        (
            OctoRequestPayload(project_context={"name": "Test"}, required_capabilities=[]),
            "required_capabilities",
            "empty required_capabilities"
        ),
        (
            OctoRequestPayload(project_context="invalid", required_capabilities=["test"]),
            "project_context",
            "invalid project_context type"
        ),
        (
            OctoRequestPayload(project_context={"name": "Test"}, required_capabilities=[123]),
            "required_capabilities",
            "non-string capability"
        ),
    ]

    for payload, expected_field, description in test_cases:
        result = payload.validate_detailed()
        assert not result.is_valid, f"Should fail validation for {description}"

        # Check that error has all required fields
        error = result.errors[0]
        assert error.field is not None, f"Error should have field name for {description}"
        assert expected_field in error.field, f"Error should mention '{expected_field}'"
        assert error.message is not None, f"Error should have message for {description}"
        assert error.severity == "error", f"Severity should be 'error'"
        assert error.remediation_hint is not None, f"Error should have remediation hint"

        print(f"  ✓ {description}: clear error message produced")
        print(f"      Field: {error.field}")
        print(f"      Message: {error.message[:60]}...")

    # Verify error_messages property works
    payload = OctoRequestPayload(project_context={"name": "Test"}, required_capabilities=[])
    result = payload.validate_detailed()
    assert len(result.error_messages) > 0, "Should have error_messages"
    assert all(isinstance(m, str) for m in result.error_messages), "Messages should be strings"
    print("  ✓ error_messages property returns list of strings")

    return True


def verify_step3():
    """Step 3: Partial context triggers warnings but proceeds with defaults."""
    print_step(3, "Partial context triggers warnings but proceeds with defaults")

    # Test 1: Missing project_context fields are defaulted
    payload = OctoRequestPayload(
        project_context={},  # Missing name, tech_stack
        required_capabilities=["testing"],
    )
    result = payload.validate_detailed(apply_defaults=True)
    assert result.is_valid, "Should be valid after applying defaults"
    assert len(result.warnings) > 0, "Should have warnings about defaults"
    assert payload.project_context["name"] == _PROJECT_CONTEXT_DEFAULTS["name"], \
        f"Name should be defaulted to {_PROJECT_CONTEXT_DEFAULTS['name']}"
    print(f"  ✓ Missing fields defaulted (name={payload.project_context['name']})")

    # Test 2: Invalid constraints are fixed
    payload = OctoRequestPayload(
        project_context={"name": "Test"},
        required_capabilities=["testing"],
        constraints={"model": "invalid_model", "max_agents": -5},
    )
    result = payload.validate_detailed(apply_defaults=True)
    assert result.is_valid, "Should be valid after fixing constraints"
    assert payload.constraints["model"] == DEFAULT_MODEL, \
        f"Model should be defaulted to {DEFAULT_MODEL}"
    assert payload.constraints["max_agents"] == 10, "max_agents should be defaulted to 10"
    print(f"  ✓ Invalid constraints fixed (model={payload.constraints['model']})")

    # Test 3: String tech_stack is converted to list
    payload = OctoRequestPayload(
        project_context={"name": "Test", "tech_stack": "python, react, fastapi"},
        required_capabilities=["testing"],
    )
    result = payload.validate_detailed(apply_defaults=True)
    assert result.is_valid, "Should be valid after conversion"
    assert isinstance(payload.project_context["tech_stack"], list), "tech_stack should be list"
    assert "python" in payload.project_context["tech_stack"], "Should contain 'python'"
    print(f"  ✓ String tech_stack converted to list: {payload.project_context['tech_stack']}")

    # Test 4: defaults_applied tracks changes
    payload = OctoRequestPayload(
        project_context={},
        required_capabilities=["testing"],
    )
    result = payload.validate_detailed(apply_defaults=True)
    assert len(result.defaults_applied) > 0, "Should track defaults applied"
    print(f"  ✓ defaults_applied tracks changes: {list(result.defaults_applied.keys())}")

    # Test 5: Warnings include field info
    for warning in result.warnings:
        assert warning.field is not None, "Warning should have field"
        assert warning.message is not None, "Warning should have message"
        assert warning.severity == "warning", "Severity should be 'warning'"
    print(f"  ✓ Warnings include field info ({len(result.warnings)} warnings)")

    return True


def verify_step4():
    """Step 4: Validation errors returned to Maestro with remediation hints."""
    print_step(4, "Validation errors returned to Maestro with remediation hints")

    # Test 1: Errors have remediation hints
    payload = OctoRequestPayload(
        project_context={"name": "Test"},
        required_capabilities=[],
    )
    result = payload.validate_detailed()
    for error in result.errors:
        assert error.remediation_hint is not None, "Error should have remediation_hint"
        assert len(error.remediation_hint) > 10, "Remediation hint should be descriptive"
    print("  ✓ All errors have remediation hints")

    # Test 2: remediation_hints property includes severity prefix
    hints = result.remediation_hints
    assert len(hints) > 0, "Should have remediation hints"
    assert all("[ERROR]" in h or "[WARNING]" in h for h in hints), \
        "Hints should be prefixed with severity"
    print(f"  ✓ remediation_hints property works: {len(hints)} hints")
    for hint in hints[:2]:
        print(f"      {hint[:60]}...")

    # Test 3: Model validation hints suggest valid models
    payload = OctoRequestPayload(
        project_context={"name": "Test"},
        required_capabilities=["testing"],
        constraints={"model": "gpt4"},
    )
    result = payload.validate_detailed()
    model_errors = [e for e in result.errors if "model" in e.field]
    if model_errors:
        hint = model_errors[0].remediation_hint
        assert any(model in hint for model in VALID_MODELS), \
            "Model hint should mention valid models"
        print(f"  ✓ Model validation hint suggests valid models")

    # Test 4: Octo response includes warnings with hints
    octo = Octo()
    payload = OctoRequestPayload(
        project_context={"name": "Test"},
        required_capabilities=[],
    )
    response = octo.generate_specs(payload)
    assert len(response.warnings) > 0, "Response should include remediation hints in warnings"
    print(f"  ✓ Octo response includes {len(response.warnings)} warnings with hints")

    # Test 5: Verify serialization works
    error = PayloadValidationError(
        field="test_field",
        message="Test message",
        severity="error",
        remediation_hint="Fix it like this",
    )
    error_dict = error.to_dict()
    assert "remediation_hint" in error_dict, "Serialized error should have remediation_hint"
    print("  ✓ PayloadValidationError serializes correctly")

    result_dict = result.to_dict()
    assert "remediation_hints" in result_dict, "Serialized result should have remediation_hints"
    print("  ✓ PayloadValidationResult serializes correctly")

    return True


def main():
    """Run all verification steps."""
    print_header("Feature #190: Octo handles malformed project context gracefully")

    results = {}

    try:
        results["Step 1"] = verify_step1()
    except Exception as e:
        print(f"\n  ✗ Step 1 FAILED: {e}")
        results["Step 1"] = False

    try:
        results["Step 2"] = verify_step2()
    except Exception as e:
        print(f"\n  ✗ Step 2 FAILED: {e}")
        results["Step 2"] = False

    try:
        results["Step 3"] = verify_step3()
    except Exception as e:
        print(f"\n  ✗ Step 3 FAILED: {e}")
        results["Step 3"] = False

    try:
        results["Step 4"] = verify_step4()
    except Exception as e:
        print(f"\n  ✗ Step 4 FAILED: {e}")
        results["Step 4"] = False

    # Summary
    print_header("VERIFICATION SUMMARY")
    all_passed = True
    for step, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {step}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  All steps PASSED! Feature #190 is working correctly.")
        return 0
    else:
        print("  Some steps FAILED. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
