#!/usr/bin/env python3
"""
Feature #53 Verification Script
================================

Verifies: Display Name and Icon Derivation

Description: Derive display_name and icon from AgentSpec objective and task_type
for human-friendly presentation.

Steps to verify:
1. Extract first sentence of objective as display_name base
2. Truncate to max 100 chars with ellipsis if needed
3. Map task_type to icon: coding->hammer, testing->flask, etc.
4. Allow icon override in spec context
5. Select mascot name from existing pool if needed
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.display_derivation import (
    DEFAULT_ICON,
    DISPLAY_NAME_MAX_LENGTH,
    MASCOT_POOL,
    TASK_TYPE_ICONS,
    derive_display_name,
    derive_display_properties,
    derive_icon,
    derive_mascot_name,
    extract_first_sentence,
    truncate_with_ellipsis,
)


def print_result(step: int, name: str, passed: bool, details: str = ""):
    """Print a test result."""
    status = "PASS" if passed else "FAIL"
    print(f"Step {step}: {name} - {status}")
    if details:
        print(f"  Details: {details}")


def verify_step1():
    """Step 1: Extract first sentence of objective as display_name base."""
    print("\n=== Step 1: Extract first sentence of objective as display_name base ===")

    test_cases = [
        # (input, expected_output)
        ("Implement login. Add logout.", "Implement login."),
        ("Build feature! Test it.", "Build feature!"),
        ("Is this working? Yes.", "Is this working?"),
        ("Line one\nLine two", "Line one"),
        ("No punctuation here", "No punctuation here"),
    ]

    all_passed = True
    for input_text, expected in test_cases:
        result = extract_first_sentence(input_text)
        passed = result == expected
        all_passed = all_passed and passed
        if not passed:
            print(f"  FAIL: '{input_text[:30]}...' -> expected '{expected}', got '{result}'")

    print_result(1, "Extract first sentence", all_passed, f"{len(test_cases)} test cases")
    return all_passed


def verify_step2():
    """Step 2: Truncate to max 100 chars with ellipsis if needed."""
    print("\n=== Step 2: Truncate to max 100 chars with ellipsis if needed ===")

    # Test that default max length is 100
    assert DISPLAY_NAME_MAX_LENGTH == 100, f"Expected max length 100, got {DISPLAY_NAME_MAX_LENGTH}"

    test_cases = [
        # (input, max_length, check_function)
        ("Short text", 100, lambda r: r == "Short text"),
        ("A" * 100, 100, lambda r: r == "A" * 100),
        ("A" * 150, 100, lambda r: len(r) == 100 and r.endswith("...")),
        ("Hello World", 8, lambda r: r == "Hello..."),
    ]

    all_passed = True
    for input_text, max_len, check in test_cases:
        result = truncate_with_ellipsis(input_text, max_len)
        passed = check(result)
        all_passed = all_passed and passed
        if not passed:
            print(f"  FAIL: truncate('{input_text[:30]}...', {max_len}) -> '{result}'")

    # Test derive_display_name integrates both functions
    long_objective = "A" * 200 + ". More text here."
    result = derive_display_name(long_objective)
    passed = len(result) == 100 and result.endswith("...")
    all_passed = all_passed and passed

    print_result(2, "Truncate with ellipsis", all_passed, f"{len(test_cases) + 1} test cases")
    return all_passed


def verify_step3():
    """Step 3: Map task_type to icon: coding->hammer, testing->flask, etc."""
    print("\n=== Step 3: Map task_type to icon ===")

    expected_mappings = {
        "coding": "hammer",
        "testing": "flask",
        "refactoring": "recycle",
        "documentation": "book",
        "audit": "shield",
        "custom": "gear",
    }

    all_passed = True
    for task_type, expected_icon in expected_mappings.items():
        result = derive_icon(task_type)
        passed = result == expected_icon
        all_passed = all_passed and passed
        if passed:
            print(f"  {task_type} -> {result}")
        else:
            print(f"  FAIL: {task_type} -> expected '{expected_icon}', got '{result}'")

    # Test unknown type returns default
    result = derive_icon("unknown_type")
    passed = result == DEFAULT_ICON
    all_passed = all_passed and passed
    print(f"  unknown_type -> {result} (default)")

    # Test case insensitivity
    result = derive_icon("CODING")
    passed = result == "hammer"
    all_passed = all_passed and passed
    print(f"  CODING (uppercase) -> {result}")

    print_result(3, "Map task_type to icon", all_passed, f"6 task types + edge cases")
    return all_passed


def verify_step4():
    """Step 4: Allow icon override in spec context."""
    print("\n=== Step 4: Allow icon override in spec context ===")

    test_cases = [
        # (task_type, context, expected_icon, description)
        ("coding", {"icon": "wrench"}, "wrench", "context override"),
        ("coding", {"icon": ""}, "hammer", "empty string ignored"),
        ("coding", {"icon": None}, "hammer", "None ignored"),
        ("coding", None, "hammer", "None context"),
        ("coding", {}, "hammer", "empty context"),
        ("coding", {"other": "value"}, "hammer", "no icon key"),
    ]

    all_passed = True
    for task_type, context, expected, desc in test_cases:
        result = derive_icon(task_type, context=context)
        passed = result == expected
        all_passed = all_passed and passed
        if passed:
            print(f"  {desc}: {result}")
        else:
            print(f"  FAIL ({desc}): expected '{expected}', got '{result}'")

    print_result(4, "Allow icon override in context", all_passed, f"{len(test_cases)} test cases")
    return all_passed


def verify_step5():
    """Step 5: Select mascot name from existing pool if needed."""
    print("\n=== Step 5: Select mascot name from existing pool ===")

    # Verify pool exists and has expected size
    assert len(MASCOT_POOL) == 20, f"Expected 20 mascots, got {len(MASCOT_POOL)}"
    print(f"  Mascot pool: {MASCOT_POOL}")

    test_cases = [
        # (args, check_function, description)
        ({"feature_id": 0}, lambda r: r == MASCOT_POOL[0], "feature_id=0 -> first mascot"),
        ({"feature_id": 5}, lambda r: r == MASCOT_POOL[5], "feature_id=5 -> sixth mascot"),
        ({"feature_id": 20}, lambda r: r == MASCOT_POOL[0], "feature_id=20 -> wraps to first"),
        ({}, lambda r: r == MASCOT_POOL[0], "no args -> first mascot fallback"),
        ({"context": {"mascot": "Custom"}}, lambda r: r == "Custom", "context override"),
    ]

    all_passed = True
    for kwargs, check, desc in test_cases:
        result = derive_mascot_name(**kwargs)
        passed = check(result)
        all_passed = all_passed and passed
        if passed:
            print(f"  {desc}: {result}")
        else:
            print(f"  FAIL ({desc}): got '{result}'")

    # Test spec_id determinism
    spec_id = "test-spec-123"
    result1 = derive_mascot_name(spec_id=spec_id)
    result2 = derive_mascot_name(spec_id=spec_id)
    passed = result1 == result2 and result1 in MASCOT_POOL
    all_passed = all_passed and passed
    print(f"  spec_id determinism: {result1} (same on repeated calls)")

    print_result(5, "Select mascot from pool", all_passed, f"{len(test_cases) + 1} test cases")
    return all_passed


def verify_combined_derivation():
    """Test the combined derive_display_properties function."""
    print("\n=== Combined Derivation Test ===")

    result = derive_display_properties(
        objective="Implement user login with OAuth2. Add password reset functionality.",
        task_type="coding",
        feature_id=42,
        context=None
    )

    all_passed = True

    # Check display_name
    expected_display_name = "Implement user login with OAuth2."
    passed = result["display_name"] == expected_display_name
    all_passed = all_passed and passed
    print(f"  display_name: '{result['display_name']}' - {'PASS' if passed else 'FAIL'}")

    # Check icon
    expected_icon = "hammer"
    passed = result["icon"] == expected_icon
    all_passed = all_passed and passed
    print(f"  icon: '{result['icon']}' - {'PASS' if passed else 'FAIL'}")

    # Check mascot_name
    expected_mascot = MASCOT_POOL[42 % len(MASCOT_POOL)]
    passed = result["mascot_name"] == expected_mascot
    all_passed = all_passed and passed
    print(f"  mascot_name: '{result['mascot_name']}' - {'PASS' if passed else 'FAIL'}")

    print_result(6, "Combined derivation", all_passed)
    return all_passed


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #53: Display Name and Icon Derivation")
    print("=" * 60)

    results = [
        ("Step 1: Extract first sentence", verify_step1()),
        ("Step 2: Truncate with ellipsis", verify_step2()),
        ("Step 3: Map task_type to icon", verify_step3()),
        ("Step 4: Allow icon override in context", verify_step4()),
        ("Step 5: Select mascot from pool", verify_step5()),
        ("Combined: derive_display_properties", verify_combined_derivation()),
    ]

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        all_passed = all_passed and passed

    print("\n" + "=" * 60)
    if all_passed:
        print("FEATURE #53: ALL VERIFICATION STEPS PASSED")
    else:
        print("FEATURE #53: SOME VERIFICATION STEPS FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
