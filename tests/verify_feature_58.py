#!/usr/bin/env python3
"""
Verification Script for Feature #58: Budget Derivation from Task Complexity
============================================================================

This script verifies all 7 steps of Feature #58:
1. Define base budgets per task_type
2. coding: max_turns=50, timeout=1800
3. testing: max_turns=30, timeout=600
4. Adjust based on description length
5. Adjust based on number of acceptance steps
6. Apply minimum and maximum bounds
7. Return budget dict with max_turns and timeout_seconds

Usage:
    python tests/verify_feature_58.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_header(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_step(step_num: int, description: str) -> None:
    """Print a step header."""
    print(f"\n--- Step {step_num}: {description} ---")


def check(condition: bool, message: str) -> bool:
    """Check a condition and print result."""
    status = "PASS" if condition else "FAIL"
    symbol = "[+]" if condition else "[-]"
    print(f"  {symbol} {message}: {status}")
    return condition


def main() -> int:
    """Run all verification steps."""
    print_header("Feature #58: Budget Derivation from Task Complexity")

    all_passed = True

    # ==========================================================================
    # Step 1: Define base budgets per task_type
    # ==========================================================================
    print_step(1, "Define base budgets per task_type")

    try:
        from api.tool_policy import BASE_BUDGETS

        all_passed &= check(
            isinstance(BASE_BUDGETS, dict),
            "BASE_BUDGETS is a dictionary"
        )

        expected_types = {"coding", "testing", "documentation", "refactoring", "audit", "custom"}
        all_passed &= check(
            set(BASE_BUDGETS.keys()) == expected_types,
            f"BASE_BUDGETS has all expected task types: {expected_types}"
        )

        for task_type in expected_types:
            all_passed &= check(
                "max_turns" in BASE_BUDGETS.get(task_type, {}),
                f"BASE_BUDGETS['{task_type}'] has max_turns"
            )
            all_passed &= check(
                "timeout_seconds" in BASE_BUDGETS.get(task_type, {}),
                f"BASE_BUDGETS['{task_type}'] has timeout_seconds"
            )
    except ImportError as e:
        all_passed = False
        print(f"  [-] Import error: {e}")

    # ==========================================================================
    # Step 2: coding: max_turns=50, timeout=1800
    # ==========================================================================
    print_step(2, "coding: max_turns=50, timeout=1800")

    try:
        all_passed &= check(
            BASE_BUDGETS["coding"]["max_turns"] == 50,
            "coding max_turns == 50"
        )
        all_passed &= check(
            BASE_BUDGETS["coding"]["timeout_seconds"] == 1800,
            "coding timeout_seconds == 1800"
        )
    except (KeyError, NameError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Step 3: testing: max_turns=30, timeout=600
    # ==========================================================================
    print_step(3, "testing: max_turns=30, timeout=600")

    try:
        all_passed &= check(
            BASE_BUDGETS["testing"]["max_turns"] == 30,
            "testing max_turns == 30"
        )
        all_passed &= check(
            BASE_BUDGETS["testing"]["timeout_seconds"] == 600,
            "testing timeout_seconds == 600"
        )
    except (KeyError, NameError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Step 4: Adjust based on description length
    # ==========================================================================
    print_step(4, "Adjust based on description length")

    try:
        from api.tool_policy import derive_budget

        # Base budget without description
        base = derive_budget("coding")

        # Short description should not change budget
        short_desc = derive_budget("coding", description="Short description")
        all_passed &= check(
            short_desc == base,
            "Short description does not increase budget"
        )

        # Long description should increase budget
        long_desc = "A" * 3000  # 3000 characters
        long_result = derive_budget("coding", description=long_desc)
        all_passed &= check(
            long_result["max_turns"] > base["max_turns"],
            f"Long description increases max_turns ({base['max_turns']} -> {long_result['max_turns']})"
        )
        all_passed &= check(
            long_result["timeout_seconds"] > base["timeout_seconds"],
            f"Long description increases timeout ({base['timeout_seconds']} -> {long_result['timeout_seconds']})"
        )

        # Verify description_length parameter works
        with_param = derive_budget("coding", description_length=3000)
        all_passed &= check(
            with_param["max_turns"] > base["max_turns"],
            "description_length parameter works correctly"
        )
    except (ImportError, KeyError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Step 5: Adjust based on number of acceptance steps
    # ==========================================================================
    print_step(5, "Adjust based on number of acceptance steps")

    try:
        # Base budget without steps
        base = derive_budget("coding")

        # Few steps should not change budget
        few_steps = derive_budget("coding", steps=["Step 1", "Step 2"])
        all_passed &= check(
            few_steps == base,
            "Few steps does not increase budget"
        )

        # Many steps should increase budget
        many_steps = [f"Step {i}" for i in range(15)]
        many_result = derive_budget("coding", steps=many_steps)
        all_passed &= check(
            many_result["max_turns"] > base["max_turns"],
            f"Many steps increases max_turns ({base['max_turns']} -> {many_result['max_turns']})"
        )
        all_passed &= check(
            many_result["timeout_seconds"] > base["timeout_seconds"],
            f"Many steps increases timeout ({base['timeout_seconds']} -> {many_result['timeout_seconds']})"
        )

        # Verify steps_count parameter works
        with_param = derive_budget("coding", steps_count=15)
        all_passed &= check(
            with_param["max_turns"] > base["max_turns"],
            "steps_count parameter works correctly"
        )
    except (ImportError, KeyError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Step 6: Apply minimum and maximum bounds
    # ==========================================================================
    print_step(6, "Apply minimum and maximum bounds")

    try:
        from api.tool_policy import MIN_BUDGET, MAX_BUDGET

        # Verify bounds exist
        all_passed &= check(
            "max_turns" in MIN_BUDGET and "timeout_seconds" in MIN_BUDGET,
            "MIN_BUDGET has max_turns and timeout_seconds"
        )
        all_passed &= check(
            "max_turns" in MAX_BUDGET and "timeout_seconds" in MAX_BUDGET,
            "MAX_BUDGET has max_turns and timeout_seconds"
        )

        # Verify minimum bounds are enforced
        result = derive_budget("audit")  # Low budget task type
        all_passed &= check(
            result["max_turns"] >= MIN_BUDGET["max_turns"],
            f"Result max_turns ({result['max_turns']}) >= MIN ({MIN_BUDGET['max_turns']})"
        )
        all_passed &= check(
            result["timeout_seconds"] >= MIN_BUDGET["timeout_seconds"],
            f"Result timeout ({result['timeout_seconds']}) >= MIN ({MIN_BUDGET['timeout_seconds']})"
        )

        # Verify maximum bounds are enforced
        extreme_result = derive_budget(
            "coding",
            description="A" * 100000,
            steps=[f"Step {i}" for i in range(1000)]
        )
        all_passed &= check(
            extreme_result["max_turns"] <= MAX_BUDGET["max_turns"],
            f"Extreme result max_turns ({extreme_result['max_turns']}) <= MAX ({MAX_BUDGET['max_turns']})"
        )
        all_passed &= check(
            extreme_result["timeout_seconds"] <= MAX_BUDGET["timeout_seconds"],
            f"Extreme result timeout ({extreme_result['timeout_seconds']}) <= MAX ({MAX_BUDGET['timeout_seconds']})"
        )
    except (ImportError, KeyError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Step 7: Return budget dict with max_turns and timeout_seconds
    # ==========================================================================
    print_step(7, "Return budget dict with max_turns and timeout_seconds")

    try:
        result = derive_budget("coding")

        all_passed &= check(
            isinstance(result, dict),
            "derive_budget returns a dict"
        )
        all_passed &= check(
            "max_turns" in result,
            "Result contains 'max_turns'"
        )
        all_passed &= check(
            "timeout_seconds" in result,
            "Result contains 'timeout_seconds'"
        )
        all_passed &= check(
            isinstance(result["max_turns"], int),
            "max_turns is an integer"
        )
        all_passed &= check(
            isinstance(result["timeout_seconds"], int),
            "timeout_seconds is an integer"
        )
        all_passed &= check(
            len(result) == 2,
            "Result has exactly 2 keys (max_turns, timeout_seconds)"
        )
    except (ImportError, KeyError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Additional Checks
    # ==========================================================================
    print_step(8, "Additional Functionality Checks")

    try:
        from api.tool_policy import (
            derive_budget_detailed,
            get_base_budget,
            get_budget_bounds,
            get_all_base_budgets,
            BudgetResult,
        )

        # Check derive_budget_detailed
        detailed = derive_budget_detailed("coding", description="Test", steps=["Step 1"])
        all_passed &= check(
            isinstance(detailed, BudgetResult),
            "derive_budget_detailed returns BudgetResult"
        )
        all_passed &= check(
            hasattr(detailed, "adjustments_applied"),
            "BudgetResult has adjustments_applied"
        )
        all_passed &= check(
            detailed.to_dict() is not None,
            "BudgetResult.to_dict() works"
        )

        # Check get_base_budget
        base = get_base_budget("coding")
        all_passed &= check(
            base == BASE_BUDGETS["coding"],
            "get_base_budget returns correct base budget"
        )

        # Check get_budget_bounds
        bounds = get_budget_bounds()
        all_passed &= check(
            "min" in bounds and "max" in bounds,
            "get_budget_bounds returns min and max"
        )

        # Check get_all_base_budgets
        all_budgets = get_all_base_budgets()
        all_passed &= check(
            set(all_budgets.keys()) == set(BASE_BUDGETS.keys()),
            "get_all_base_budgets returns all task types"
        )
    except (ImportError, AttributeError) as e:
        all_passed = False
        print(f"  [-] Error: {e}")

    # ==========================================================================
    # Check exports in api/__init__.py
    # ==========================================================================
    print_step(9, "API Exports Check")

    try:
        from api import (
            BASE_BUDGETS as api_base_budgets,
            MIN_BUDGET as api_min_budget,
            MAX_BUDGET as api_max_budget,
            BudgetResult as api_budget_result,
            derive_budget as api_derive_budget,
            derive_budget_detailed as api_derive_budget_detailed,
            get_base_budget as api_get_base_budget,
            get_budget_bounds as api_get_budget_bounds,
            get_all_base_budgets as api_get_all_base_budgets,
        )

        all_passed &= check(True, "BASE_BUDGETS exported from api")
        all_passed &= check(True, "MIN_BUDGET exported from api")
        all_passed &= check(True, "MAX_BUDGET exported from api")
        all_passed &= check(True, "BudgetResult exported from api")
        all_passed &= check(True, "derive_budget exported from api")
        all_passed &= check(True, "derive_budget_detailed exported from api")
        all_passed &= check(True, "get_base_budget exported from api")
        all_passed &= check(True, "get_budget_bounds exported from api")
        all_passed &= check(True, "get_all_base_budgets exported from api")
    except ImportError as e:
        all_passed = False
        print(f"  [-] Export missing: {e}")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print_header("Verification Summary")

    if all_passed:
        print("\n  All checks PASSED!")
        print("  Feature #58: Budget Derivation from Task Complexity - VERIFIED")
        return 0
    else:
        print("\n  Some checks FAILED!")
        print("  Please review the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
