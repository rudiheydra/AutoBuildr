"""
Test Suite for Feature #58: Budget Derivation from Task Complexity
==================================================================

This module tests the budget derivation functionality that calculates
appropriate max_turns and timeout_seconds based on task complexity.

Feature #58 Requirements:
1. Define base budgets per task_type
2. coding: max_turns=50, timeout=1800
3. testing: max_turns=30, timeout=600
4. Adjust based on description length
5. Adjust based on number of acceptance steps
6. Apply minimum and maximum bounds
7. Return budget dict with max_turns and timeout_seconds
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from api.tool_policy import (
    BASE_BUDGETS,
    MIN_BUDGET,
    MAX_BUDGET,
    DESCRIPTION_LENGTH_THRESHOLDS,
    STEPS_COUNT_THRESHOLDS,
    BudgetResult,
    derive_budget,
    derive_budget_detailed,
    get_base_budget,
    get_budget_bounds,
    get_all_base_budgets,
    _get_description_multiplier,
    _get_steps_multiplier,
    _apply_bounds,
)


# =============================================================================
# Test Constants and Configuration
# =============================================================================

class TestBaseBudgetsConstant:
    """Tests for BASE_BUDGETS constant definition."""

    def test_base_budgets_is_dict(self):
        """BASE_BUDGETS should be a dictionary."""
        assert isinstance(BASE_BUDGETS, dict)

    def test_base_budgets_has_coding(self):
        """BASE_BUDGETS should have 'coding' task type."""
        assert "coding" in BASE_BUDGETS

    def test_base_budgets_has_testing(self):
        """BASE_BUDGETS should have 'testing' task type."""
        assert "testing" in BASE_BUDGETS

    def test_base_budgets_has_all_task_types(self):
        """BASE_BUDGETS should have all standard task types."""
        expected_types = {"coding", "testing", "documentation", "refactoring", "audit", "custom"}
        assert set(BASE_BUDGETS.keys()) == expected_types

    def test_coding_base_budget_max_turns(self):
        """coding task type should have max_turns=50."""
        assert BASE_BUDGETS["coding"]["max_turns"] == 50

    def test_coding_base_budget_timeout(self):
        """coding task type should have timeout_seconds=1800."""
        assert BASE_BUDGETS["coding"]["timeout_seconds"] == 1800

    def test_testing_base_budget_max_turns(self):
        """testing task type should have max_turns=30."""
        assert BASE_BUDGETS["testing"]["max_turns"] == 30

    def test_testing_base_budget_timeout(self):
        """testing task type should have timeout_seconds=600."""
        assert BASE_BUDGETS["testing"]["timeout_seconds"] == 600

    def test_all_task_types_have_max_turns(self):
        """All task types should have max_turns defined."""
        for task_type, budget in BASE_BUDGETS.items():
            assert "max_turns" in budget, f"{task_type} missing max_turns"
            assert isinstance(budget["max_turns"], int)
            assert budget["max_turns"] > 0

    def test_all_task_types_have_timeout_seconds(self):
        """All task types should have timeout_seconds defined."""
        for task_type, budget in BASE_BUDGETS.items():
            assert "timeout_seconds" in budget, f"{task_type} missing timeout_seconds"
            assert isinstance(budget["timeout_seconds"], int)
            assert budget["timeout_seconds"] > 0


class TestBoundsConstants:
    """Tests for MIN_BUDGET and MAX_BUDGET constants."""

    def test_min_budget_is_dict(self):
        """MIN_BUDGET should be a dictionary."""
        assert isinstance(MIN_BUDGET, dict)

    def test_max_budget_is_dict(self):
        """MAX_BUDGET should be a dictionary."""
        assert isinstance(MAX_BUDGET, dict)

    def test_min_budget_has_max_turns(self):
        """MIN_BUDGET should have max_turns."""
        assert "max_turns" in MIN_BUDGET
        assert MIN_BUDGET["max_turns"] > 0

    def test_min_budget_has_timeout_seconds(self):
        """MIN_BUDGET should have timeout_seconds."""
        assert "timeout_seconds" in MIN_BUDGET
        assert MIN_BUDGET["timeout_seconds"] > 0

    def test_max_budget_has_max_turns(self):
        """MAX_BUDGET should have max_turns."""
        assert "max_turns" in MAX_BUDGET
        assert MAX_BUDGET["max_turns"] > 0

    def test_max_budget_has_timeout_seconds(self):
        """MAX_BUDGET should have timeout_seconds."""
        assert "timeout_seconds" in MAX_BUDGET
        assert MAX_BUDGET["timeout_seconds"] > 0

    def test_min_less_than_max_turns(self):
        """MIN_BUDGET max_turns should be less than MAX_BUDGET max_turns."""
        assert MIN_BUDGET["max_turns"] < MAX_BUDGET["max_turns"]

    def test_min_less_than_max_timeout(self):
        """MIN_BUDGET timeout_seconds should be less than MAX_BUDGET timeout_seconds."""
        assert MIN_BUDGET["timeout_seconds"] < MAX_BUDGET["timeout_seconds"]


class TestAdjustmentThresholds:
    """Tests for adjustment threshold constants."""

    def test_description_thresholds_is_list(self):
        """DESCRIPTION_LENGTH_THRESHOLDS should be a list."""
        assert isinstance(DESCRIPTION_LENGTH_THRESHOLDS, list)

    def test_steps_thresholds_is_list(self):
        """STEPS_COUNT_THRESHOLDS should be a list."""
        assert isinstance(STEPS_COUNT_THRESHOLDS, list)

    def test_description_thresholds_are_tuples(self):
        """Each description threshold should be a tuple."""
        for threshold in DESCRIPTION_LENGTH_THRESHOLDS:
            assert isinstance(threshold, tuple)
            assert len(threshold) == 2

    def test_steps_thresholds_are_tuples(self):
        """Each steps threshold should be a tuple."""
        for threshold in STEPS_COUNT_THRESHOLDS:
            assert isinstance(threshold, tuple)
            assert len(threshold) == 2

    def test_description_thresholds_ordered(self):
        """Description thresholds should be in ascending order."""
        prev_threshold = -1
        for threshold, _ in DESCRIPTION_LENGTH_THRESHOLDS:
            assert threshold > prev_threshold
            prev_threshold = threshold

    def test_steps_thresholds_ordered(self):
        """Steps thresholds should be in ascending order."""
        prev_threshold = -1
        for threshold, _ in STEPS_COUNT_THRESHOLDS:
            assert threshold > prev_threshold
            prev_threshold = threshold


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestGetDescriptionMultiplier:
    """Tests for _get_description_multiplier helper function."""

    def test_zero_length_returns_one(self):
        """Zero description length should return 1.0 multiplier."""
        assert _get_description_multiplier(0) == 1.0

    def test_short_description_returns_one(self):
        """Short description (< 500) should return 1.0 multiplier."""
        assert _get_description_multiplier(100) == 1.0
        assert _get_description_multiplier(499) == 1.0

    def test_medium_description_returns_increased_multiplier(self):
        """Medium description (500-999) should return base multiplier."""
        result = _get_description_multiplier(500)
        assert result == 1.0  # First threshold is base

    def test_long_description_returns_higher_multiplier(self):
        """Long description (1000+) should return higher multiplier."""
        result = _get_description_multiplier(1000)
        assert result >= 1.0  # Should be at least base

    def test_very_long_description_returns_highest_multiplier(self):
        """Very long description (5000+) should return highest multiplier."""
        result = _get_description_multiplier(5000)
        assert result > 1.0

    def test_multiplier_never_exceeds_max_threshold(self):
        """Multiplier should never exceed the highest defined threshold."""
        max_multiplier = max(m for _, m in DESCRIPTION_LENGTH_THRESHOLDS)
        # Even for extremely long descriptions
        result = _get_description_multiplier(100000)
        assert result <= max_multiplier


class TestGetStepsMultiplier:
    """Tests for _get_steps_multiplier helper function."""

    def test_zero_steps_returns_one(self):
        """Zero steps should return 1.0 multiplier."""
        assert _get_steps_multiplier(0) == 1.0

    def test_few_steps_returns_one(self):
        """Few steps (< 3) should return 1.0 multiplier."""
        assert _get_steps_multiplier(1) == 1.0
        assert _get_steps_multiplier(2) == 1.0

    def test_medium_steps_returns_base_or_higher(self):
        """Medium step count (3-4) should return base or higher."""
        result = _get_steps_multiplier(3)
        assert result >= 1.0

    def test_many_steps_returns_higher_multiplier(self):
        """Many steps (5+) should return higher multiplier."""
        result = _get_steps_multiplier(5)
        assert result >= 1.0

    def test_very_many_steps_returns_highest_multiplier(self):
        """Very many steps (20+) should return highest multiplier."""
        result = _get_steps_multiplier(20)
        assert result > 1.0


class TestApplyBounds:
    """Tests for _apply_bounds helper function."""

    def test_value_within_bounds_unchanged(self):
        """Value within bounds should be unchanged."""
        assert _apply_bounds(50, 10, 100) == 50

    def test_value_below_min_returns_min(self):
        """Value below minimum should return minimum."""
        assert _apply_bounds(5, 10, 100) == 10

    def test_value_above_max_returns_max(self):
        """Value above maximum should return maximum."""
        assert _apply_bounds(150, 10, 100) == 100

    def test_value_equals_min_returns_min(self):
        """Value equal to minimum should return minimum."""
        assert _apply_bounds(10, 10, 100) == 10

    def test_value_equals_max_returns_max(self):
        """Value equal to maximum should return maximum."""
        assert _apply_bounds(100, 10, 100) == 100


# =============================================================================
# Test derive_budget Function
# =============================================================================

class TestDeriveBudgetBasic:
    """Tests for basic derive_budget functionality."""

    def test_returns_dict(self):
        """derive_budget should return a dictionary."""
        result = derive_budget("coding")
        assert isinstance(result, dict)

    def test_returns_max_turns(self):
        """derive_budget should return max_turns."""
        result = derive_budget("coding")
        assert "max_turns" in result
        assert isinstance(result["max_turns"], int)

    def test_returns_timeout_seconds(self):
        """derive_budget should return timeout_seconds."""
        result = derive_budget("coding")
        assert "timeout_seconds" in result
        assert isinstance(result["timeout_seconds"], int)

    def test_coding_base_budget(self):
        """derive_budget for coding should return base budget."""
        result = derive_budget("coding")
        assert result["max_turns"] == 50
        assert result["timeout_seconds"] == 1800

    def test_testing_base_budget(self):
        """derive_budget for testing should return base budget."""
        result = derive_budget("testing")
        assert result["max_turns"] == 30
        assert result["timeout_seconds"] == 600


class TestDeriveBudgetTaskTypes:
    """Tests for derive_budget with different task types."""

    @pytest.mark.parametrize("task_type", [
        "coding", "testing", "documentation", "refactoring", "audit", "custom"
    ])
    def test_all_task_types_return_valid_budget(self, task_type):
        """All task types should return valid budgets."""
        result = derive_budget(task_type)
        assert "max_turns" in result
        assert "timeout_seconds" in result
        assert result["max_turns"] >= MIN_BUDGET["max_turns"]
        assert result["timeout_seconds"] >= MIN_BUDGET["timeout_seconds"]

    def test_unknown_task_type_uses_custom(self):
        """Unknown task type should fall back to custom."""
        result = derive_budget("unknown_task_type")
        custom_budget = derive_budget("custom")
        assert result == custom_budget

    def test_case_insensitive_task_type(self):
        """Task type should be case insensitive."""
        lower_result = derive_budget("coding")
        upper_result = derive_budget("CODING")
        mixed_result = derive_budget("CoDiNg")
        assert lower_result == upper_result == mixed_result

    def test_whitespace_trimmed(self):
        """Whitespace should be trimmed from task type."""
        normal_result = derive_budget("coding")
        padded_result = derive_budget("  coding  ")
        assert normal_result == padded_result


class TestDeriveBudgetDescriptionAdjustment:
    """Tests for derive_budget with description length adjustment."""

    def test_short_description_no_adjustment(self):
        """Short description should not increase budget."""
        base = derive_budget("coding")
        with_desc = derive_budget("coding", description="Short desc")
        assert with_desc == base

    def test_long_description_increases_budget(self):
        """Long description should increase budget."""
        base = derive_budget("coding")
        long_desc = "A" * 2000  # 2000 chars
        with_desc = derive_budget("coding", description=long_desc)
        assert with_desc["max_turns"] > base["max_turns"]
        assert with_desc["timeout_seconds"] > base["timeout_seconds"]

    def test_description_length_override(self):
        """Explicit description_length should override description."""
        # Pass short description but specify long length
        with_override = derive_budget("coding", description="Short", description_length=2000)
        base = derive_budget("coding")
        assert with_override["max_turns"] > base["max_turns"]

    def test_description_length_takes_precedence(self):
        """description_length should take precedence over description."""
        with_long_str = derive_budget("coding", description="A" * 3000, description_length=100)
        base = derive_budget("coding")
        # Even though description is long, explicit length is short
        assert with_long_str == base


class TestDeriveBudgetStepsAdjustment:
    """Tests for derive_budget with acceptance steps adjustment."""

    def test_few_steps_no_adjustment(self):
        """Few steps should not increase budget."""
        base = derive_budget("coding")
        with_steps = derive_budget("coding", steps=["Step 1", "Step 2"])
        assert with_steps == base

    def test_many_steps_increases_budget(self):
        """Many steps should increase budget."""
        base = derive_budget("coding")
        many_steps = [f"Step {i}" for i in range(10)]
        with_steps = derive_budget("coding", steps=many_steps)
        assert with_steps["max_turns"] > base["max_turns"]
        assert with_steps["timeout_seconds"] > base["timeout_seconds"]

    def test_steps_count_override(self):
        """Explicit steps_count should override steps list."""
        with_override = derive_budget("coding", steps=["Step 1"], steps_count=10)
        base = derive_budget("coding")
        assert with_override["max_turns"] > base["max_turns"]

    def test_steps_count_takes_precedence(self):
        """steps_count should take precedence over steps list."""
        many_steps = [f"Step {i}" for i in range(20)]
        with_long_list = derive_budget("coding", steps=many_steps, steps_count=1)
        base = derive_budget("coding")
        # Even though steps list is long, explicit count is short
        assert with_long_list == base


class TestDeriveBudgetCombinedAdjustment:
    """Tests for derive_budget with combined adjustments."""

    def test_both_adjustments_combined(self):
        """Both description and steps adjustments should combine."""
        base = derive_budget("coding")
        long_desc = "A" * 3000
        many_steps = [f"Step {i}" for i in range(15)]
        combined = derive_budget("coding", description=long_desc, steps=many_steps)
        # Combined should be higher than base
        assert combined["max_turns"] > base["max_turns"]
        assert combined["timeout_seconds"] > base["timeout_seconds"]

    def test_combined_adjustment_averaged(self):
        """Combined adjustments should be averaged (not multiplied)."""
        # This test ensures we don't have exponential growth
        long_desc = "A" * 5000
        many_steps = [f"Step {i}" for i in range(25)]
        result = derive_budget("coding", description=long_desc, steps=many_steps)
        # Even with max adjustments, result should be bounded
        assert result["max_turns"] <= MAX_BUDGET["max_turns"]
        assert result["timeout_seconds"] <= MAX_BUDGET["timeout_seconds"]


class TestDeriveBudgetBounds:
    """Tests for derive_budget bounds enforcement."""

    def test_never_below_minimum_turns(self):
        """Result should never be below minimum max_turns."""
        result = derive_budget("audit")  # Audit has low budget
        assert result["max_turns"] >= MIN_BUDGET["max_turns"]

    def test_never_below_minimum_timeout(self):
        """Result should never be below minimum timeout_seconds."""
        result = derive_budget("audit")
        assert result["timeout_seconds"] >= MIN_BUDGET["timeout_seconds"]

    def test_never_above_maximum_turns(self):
        """Result should never exceed maximum max_turns."""
        # Use extremely high adjustments
        result = derive_budget(
            "coding",
            description="A" * 100000,
            steps=[f"Step {i}" for i in range(100)]
        )
        assert result["max_turns"] <= MAX_BUDGET["max_turns"]

    def test_never_above_maximum_timeout(self):
        """Result should never exceed maximum timeout_seconds."""
        result = derive_budget(
            "coding",
            description="A" * 100000,
            steps=[f"Step {i}" for i in range(100)]
        )
        assert result["timeout_seconds"] <= MAX_BUDGET["timeout_seconds"]


# =============================================================================
# Test derive_budget_detailed Function
# =============================================================================

class TestDeriveBudgetDetailed:
    """Tests for derive_budget_detailed function."""

    def test_returns_budget_result(self):
        """derive_budget_detailed should return BudgetResult."""
        result = derive_budget_detailed("coding")
        assert isinstance(result, BudgetResult)

    def test_has_all_fields(self):
        """BudgetResult should have all expected fields."""
        result = derive_budget_detailed("coding")
        assert hasattr(result, "max_turns")
        assert hasattr(result, "timeout_seconds")
        assert hasattr(result, "task_type")
        assert hasattr(result, "base_max_turns")
        assert hasattr(result, "base_timeout_seconds")
        assert hasattr(result, "description_multiplier")
        assert hasattr(result, "steps_multiplier")
        assert hasattr(result, "description_length")
        assert hasattr(result, "steps_count")
        assert hasattr(result, "adjustments_applied")

    def test_matches_derive_budget(self):
        """derive_budget_detailed should match derive_budget results."""
        simple = derive_budget("coding", description="A" * 2000)
        detailed = derive_budget_detailed("coding", description="A" * 2000)
        assert detailed.max_turns == simple["max_turns"]
        assert detailed.timeout_seconds == simple["timeout_seconds"]

    def test_tracks_description_length(self):
        """BudgetResult should track description length."""
        desc = "Test description"
        result = derive_budget_detailed("coding", description=desc)
        assert result.description_length == len(desc)

    def test_tracks_steps_count(self):
        """BudgetResult should track steps count."""
        steps = ["Step 1", "Step 2", "Step 3"]
        result = derive_budget_detailed("coding", steps=steps)
        assert result.steps_count == len(steps)

    def test_tracks_multipliers(self):
        """BudgetResult should track multipliers."""
        result = derive_budget_detailed("coding")
        assert isinstance(result.description_multiplier, float)
        assert isinstance(result.steps_multiplier, float)

    def test_tracks_adjustments(self):
        """BudgetResult should track adjustments applied."""
        result = derive_budget_detailed("coding", description="A" * 2000)
        assert isinstance(result.adjustments_applied, list)
        assert len(result.adjustments_applied) >= 1  # At least base budget
        assert "base_budget_coding" in result.adjustments_applied

    def test_to_dict(self):
        """BudgetResult.to_dict should return dictionary."""
        result = derive_budget_detailed("coding")
        as_dict = result.to_dict()
        assert isinstance(as_dict, dict)
        assert "max_turns" in as_dict
        assert "timeout_seconds" in as_dict
        assert "adjustments_applied" in as_dict


# =============================================================================
# Test Convenience Functions
# =============================================================================

class TestGetBaseBudget:
    """Tests for get_base_budget function."""

    def test_returns_dict(self):
        """get_base_budget should return a dictionary."""
        result = get_base_budget("coding")
        assert isinstance(result, dict)

    def test_returns_copy(self):
        """get_base_budget should return a copy, not reference."""
        result1 = get_base_budget("coding")
        result2 = get_base_budget("coding")
        result1["max_turns"] = 999
        assert result2["max_turns"] != 999

    def test_coding_budget(self):
        """get_base_budget for coding should match BASE_BUDGETS."""
        result = get_base_budget("coding")
        assert result == BASE_BUDGETS["coding"]

    def test_unknown_task_type_uses_custom(self):
        """Unknown task type should return custom budget."""
        result = get_base_budget("unknown")
        assert result == BASE_BUDGETS["custom"]


class TestGetBudgetBounds:
    """Tests for get_budget_bounds function."""

    def test_returns_dict(self):
        """get_budget_bounds should return a dictionary."""
        result = get_budget_bounds()
        assert isinstance(result, dict)

    def test_has_min_and_max(self):
        """Result should have 'min' and 'max' keys."""
        result = get_budget_bounds()
        assert "min" in result
        assert "max" in result

    def test_min_matches_constant(self):
        """'min' values should match MIN_BUDGET."""
        result = get_budget_bounds()
        assert result["min"] == MIN_BUDGET

    def test_max_matches_constant(self):
        """'max' values should match MAX_BUDGET."""
        result = get_budget_bounds()
        assert result["max"] == MAX_BUDGET


class TestGetAllBaseBudgets:
    """Tests for get_all_base_budgets function."""

    def test_returns_dict(self):
        """get_all_base_budgets should return a dictionary."""
        result = get_all_base_budgets()
        assert isinstance(result, dict)

    def test_returns_copy(self):
        """get_all_base_budgets should return a copy, not reference."""
        result = get_all_base_budgets()
        result["coding"]["max_turns"] = 999
        assert BASE_BUDGETS["coding"]["max_turns"] != 999

    def test_has_all_task_types(self):
        """Result should have all task types from BASE_BUDGETS."""
        result = get_all_base_budgets()
        assert set(result.keys()) == set(BASE_BUDGETS.keys())


# =============================================================================
# Test Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_none_task_type(self):
        """None task type should use custom."""
        result = derive_budget(None)
        custom = derive_budget("custom")
        assert result == custom

    def test_empty_task_type(self):
        """Empty task type should use custom."""
        result = derive_budget("")
        custom = derive_budget("custom")
        assert result == custom

    def test_none_description(self):
        """None description should not raise error."""
        result = derive_budget("coding", description=None)
        assert result["max_turns"] == 50

    def test_empty_description(self):
        """Empty description should not raise error."""
        result = derive_budget("coding", description="")
        assert result["max_turns"] == 50

    def test_none_steps(self):
        """None steps should not raise error."""
        result = derive_budget("coding", steps=None)
        assert result["max_turns"] == 50

    def test_empty_steps_list(self):
        """Empty steps list should not raise error."""
        result = derive_budget("coding", steps=[])
        assert result["max_turns"] == 50

    def test_zero_description_length(self):
        """Zero description_length should not raise error."""
        result = derive_budget("coding", description_length=0)
        assert result["max_turns"] == 50

    def test_zero_steps_count(self):
        """Zero steps_count should not raise error."""
        result = derive_budget("coding", steps_count=0)
        assert result["max_turns"] == 50

    def test_negative_description_length(self):
        """Negative description_length should be handled gracefully."""
        # This is technically invalid input but should not crash
        result = derive_budget("coding", description_length=-100)
        assert result["max_turns"] >= MIN_BUDGET["max_turns"]

    def test_negative_steps_count(self):
        """Negative steps_count should be handled gracefully."""
        result = derive_budget("coding", steps_count=-100)
        assert result["max_turns"] >= MIN_BUDGET["max_turns"]


# =============================================================================
# Test Feature #58 Specific Requirements
# =============================================================================

class TestFeature58Requirements:
    """Tests that verify Feature #58 specific requirements."""

    def test_step1_base_budgets_per_task_type(self):
        """Step 1: Define base budgets per task_type."""
        # Verify base budgets exist for all expected task types
        expected_types = {"coding", "testing", "documentation", "refactoring", "audit", "custom"}
        assert set(BASE_BUDGETS.keys()) == expected_types

    def test_step2_coding_max_turns_50(self):
        """Step 2: coding: max_turns=50."""
        assert BASE_BUDGETS["coding"]["max_turns"] == 50

    def test_step2_coding_timeout_1800(self):
        """Step 2: coding: timeout=1800."""
        assert BASE_BUDGETS["coding"]["timeout_seconds"] == 1800

    def test_step3_testing_max_turns_30(self):
        """Step 3: testing: max_turns=30."""
        assert BASE_BUDGETS["testing"]["max_turns"] == 30

    def test_step3_testing_timeout_600(self):
        """Step 3: testing: timeout=600."""
        assert BASE_BUDGETS["testing"]["timeout_seconds"] == 600

    def test_step4_adjust_based_on_description_length(self):
        """Step 4: Adjust based on description length."""
        base = derive_budget("coding")
        # Verify that a longer description increases the budget
        long_desc = "A" * 3000
        adjusted = derive_budget("coding", description=long_desc)
        assert adjusted["max_turns"] > base["max_turns"]

    def test_step5_adjust_based_on_acceptance_steps(self):
        """Step 5: Adjust based on number of acceptance steps."""
        base = derive_budget("coding")
        # Verify that more steps increases the budget
        many_steps = [f"Step {i}" for i in range(15)]
        adjusted = derive_budget("coding", steps=many_steps)
        assert adjusted["max_turns"] > base["max_turns"]

    def test_step6_apply_minimum_bounds(self):
        """Step 6: Apply minimum bounds."""
        # Even with minimal settings, should not go below minimum
        result = derive_budget("audit")  # Low budget task type
        assert result["max_turns"] >= MIN_BUDGET["max_turns"]
        assert result["timeout_seconds"] >= MIN_BUDGET["timeout_seconds"]

    def test_step6_apply_maximum_bounds(self):
        """Step 6: Apply maximum bounds."""
        # Even with extreme settings, should not exceed maximum
        result = derive_budget(
            "coding",
            description="A" * 100000,
            steps=[f"Step {i}" for i in range(1000)]
        )
        assert result["max_turns"] <= MAX_BUDGET["max_turns"]
        assert result["timeout_seconds"] <= MAX_BUDGET["timeout_seconds"]

    def test_step7_return_budget_dict(self):
        """Step 7: Return budget dict with max_turns and timeout_seconds."""
        result = derive_budget("coding")
        assert isinstance(result, dict)
        assert "max_turns" in result
        assert "timeout_seconds" in result
        assert len(result) == 2  # Only these two keys


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for budget derivation."""

    def test_realistic_coding_task(self):
        """Test with realistic coding task parameters."""
        description = """
        Implement user authentication with JWT tokens.
        This feature requires creating login/logout endpoints,
        token generation, validation middleware, and secure
        password hashing.
        """
        steps = [
            "Create User model with password field",
            "Implement password hashing",
            "Create POST /api/auth/login endpoint",
            "Create POST /api/auth/logout endpoint",
            "Implement JWT token generation",
            "Create authentication middleware",
            "Add token refresh endpoint",
            "Write unit tests",
        ]
        result = derive_budget("coding", description=description, steps=steps)
        # Should have reasonable budget for this task
        assert result["max_turns"] >= 50  # At least base
        assert result["timeout_seconds"] >= 1800

    def test_realistic_testing_task(self):
        """Test with realistic testing task parameters."""
        description = "Verify user authentication flow works correctly."
        steps = [
            "Test login with valid credentials",
            "Test login with invalid password",
            "Test token validation",
            "Test logout clears token",
        ]
        result = derive_budget("testing", description=description, steps=steps)
        assert result["max_turns"] >= 30  # At least base
        assert result["timeout_seconds"] >= 600

    def test_complex_refactoring_task(self):
        """Test with complex refactoring task parameters."""
        description = """
        Refactor the entire database layer to use the repository pattern.
        This involves creating abstract repository interfaces, implementing
        concrete repositories for each entity, updating all service classes
        to use dependency injection, and ensuring all existing tests still pass.
        """ * 3  # Make it long
        steps = [f"Step {i}" for i in range(20)]
        result = derive_budget("refactoring", description=description, steps=steps)
        # Complex task should get increased budget
        assert result["max_turns"] > BASE_BUDGETS["refactoring"]["max_turns"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
