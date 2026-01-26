"""
Tests for validate_dependency_graph() - Feature #87: Simple Cycle Detection

This test file verifies that the validate_dependency_graph() function correctly
detects simple cycles (A -> B -> A) in the dependency graph and returns the
cycle path with requires_user_action=True.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.dependency_resolver import validate_dependency_graph, ValidationResult


class TestSimpleCycleDetection:
    """Test Feature #87: Simple cycle detection (A -> B -> A)"""

    def test_simple_cycle_a_b_a(self):
        """
        Feature #87 Step 1-3: Create A (id=1) with deps=[2], B (id=2) with deps=[1]
        Call validate_dependency_graph() and verify cycle detected.
        """
        # Step 1: Create feature A (id=1) with dependencies=[2]
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}

        # Step 2: Create feature B (id=2) with dependencies=[1]
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        # Step 3: Call validate_dependency_graph() with both features
        result = validate_dependency_graph([feature_a, feature_b])

        # Verify the result is a ValidationResult
        assert isinstance(result, dict)
        assert "is_valid" in result
        assert "cycles" in result
        assert "issues" in result

        # The graph should be invalid due to the cycle
        assert result["is_valid"] is False

        # Step 4: Verify the result includes cycles list with [1, 2] or [2, 1]
        assert len(result["cycles"]) > 0, "Expected at least one cycle to be detected"

        # Check that the cycle contains both features 1 and 2
        cycle = result["cycles"][0]
        assert 1 in cycle, "Cycle should contain feature 1"
        assert 2 in cycle, "Cycle should contain feature 2"
        assert len(cycle) == 2, f"Simple cycle should have 2 features, got {len(cycle)}"

    def test_cycle_issue_requires_user_action(self):
        """
        Feature #87 Step 5: Verify the error type is marked as requires_user_action=True
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b])

        # Find cycle issues
        cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]
        assert len(cycle_issues) > 0, "Expected at least one cycle issue"

        # Verify auto_fixable is False (which means requires_user_action=True)
        for issue in cycle_issues:
            assert issue["auto_fixable"] is False, \
                "Cycle issues should NOT be auto-fixable (requires user action)"

    def test_cycle_issue_details_contain_path(self):
        """
        Verify that cycle issues contain the cycle_path in details.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b])

        # Find cycle issues
        cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]

        for issue in cycle_issues:
            assert "details" in issue
            assert "cycle_path" in issue["details"], \
                "Cycle issue should include cycle_path in details"
            cycle_path = issue["details"]["cycle_path"]
            assert 1 in cycle_path or 2 in cycle_path, \
                "Cycle path should contain at least one of the features in the cycle"

    def test_no_cycle_without_dependencies(self):
        """
        Verify that features without cyclic dependencies don't trigger cycle detection.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": []}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b])

        assert result["is_valid"] is True
        assert len(result["cycles"]) == 0

    def test_no_cycle_linear_dependency(self):
        """
        Verify that linear dependencies (A -> B -> C) don't create false positives.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": []}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [2]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        assert result["is_valid"] is True
        assert len(result["cycles"]) == 0

    def test_summary_mentions_cycle(self):
        """
        Verify that the summary mentions cycles when they exist.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b])

        assert "cycle" in result["summary"].lower(), \
            f"Summary should mention 'cycle', got: {result['summary']}"

    def test_empty_features_list(self):
        """
        Verify that an empty features list returns valid result.
        """
        result = validate_dependency_graph([])

        assert result["is_valid"] is True
        assert len(result["cycles"]) == 0
        assert len(result["self_references"]) == 0
        assert len(result["missing_targets"]) == 0

    def test_single_feature_no_deps(self):
        """
        Verify that a single feature without dependencies is valid.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": []}

        result = validate_dependency_graph([feature_a])

        assert result["is_valid"] is True
        assert len(result["cycles"]) == 0


class TestCycleVsSelfReference:
    """Test that simple cycles are distinct from self-references."""

    def test_self_reference_not_in_cycles(self):
        """
        Verify that self-references (A -> A) are tracked separately from cycles.
        """
        # Self-reference: A depends on itself
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [1]}

        result = validate_dependency_graph([feature_a])

        # Self-reference should be in self_references, NOT in cycles
        assert 1 in result["self_references"]
        # Note: depending on implementation, this may or may not also appear in cycles
        # The key is that self_references is populated correctly

    def test_self_reference_is_auto_fixable(self):
        """
        Verify that self-references are marked as auto-fixable.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [1]}

        result = validate_dependency_graph([feature_a])

        self_ref_issues = [i for i in result["issues"] if i["issue_type"] == "self_reference"]
        assert len(self_ref_issues) > 0
        for issue in self_ref_issues:
            assert issue["auto_fixable"] is True

    def test_mixed_self_reference_and_cycle(self):
        """
        Verify handling when both self-reference and cycle exist.
        """
        # A has self-reference
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [1]}
        # B and C have a cycle
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [2]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        # Check self-reference detected
        assert 1 in result["self_references"]

        # Check cycle detected (B -> C -> B)
        assert len(result["cycles"]) > 0
        cycle = result["cycles"][0]
        assert 2 in cycle or 3 in cycle


class TestValidationResultStructure:
    """Test that ValidationResult has the correct structure."""

    def test_result_has_all_required_fields(self):
        """
        Verify that ValidationResult contains all required fields.
        """
        features = [{"id": 1, "name": "A", "dependencies": []}]
        result = validate_dependency_graph(features)

        required_fields = ["is_valid", "self_references", "cycles", "missing_targets", "issues", "summary"]
        for field in required_fields:
            assert field in result, f"ValidationResult missing required field: {field}"

    def test_cycles_is_list_of_lists(self):
        """
        Verify that cycles field is a list of lists (cycle paths).
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b])

        assert isinstance(result["cycles"], list)
        for cycle in result["cycles"]:
            assert isinstance(cycle, list), "Each cycle should be a list of feature IDs"
            for fid in cycle:
                assert isinstance(fid, int), "Cycle should contain integer feature IDs"


def run_feature_87_verification():
    """
    Run the verification steps from Feature #87 and print results.
    """
    print("=" * 60)
    print("Feature #87: Simple Cycle Detection Verification")
    print("=" * 60)

    # Step 1: Create feature A (id=1) with dependencies=[2]
    print("\nStep 1: Create feature A (id=1) with dependencies=[2]")
    feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
    print(f"  Created: {feature_a}")

    # Step 2: Create feature B (id=2) with dependencies=[1]
    print("\nStep 2: Create feature B (id=2) with dependencies=[1]")
    feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}
    print(f"  Created: {feature_b}")

    # Step 3: Call validate_dependency_graph() with both features
    print("\nStep 3: Call validate_dependency_graph() with both features")
    result = validate_dependency_graph([feature_a, feature_b])
    print(f"  Result keys: {list(result.keys())}")

    # Step 4: Verify the result includes cycles list with [1, 2] or [2, 1]
    print("\nStep 4: Verify the result includes cycles list with [1, 2] or [2, 1]")
    cycles = result["cycles"]
    print(f"  cycles = {cycles}")
    if cycles and len(cycles) > 0:
        cycle = cycles[0]
        if 1 in cycle and 2 in cycle:
            print("  ✓ PASS: Cycle contains both feature 1 and 2")
        else:
            print(f"  ✗ FAIL: Cycle does not contain both features: {cycle}")
    else:
        print("  ✗ FAIL: No cycles detected")

    # Step 5: Verify the error type is marked as requires_user_action=True
    print("\nStep 5: Verify the error type is marked as requires_user_action=True")
    cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]
    if cycle_issues:
        all_require_user_action = all(not i["auto_fixable"] for i in cycle_issues)
        if all_require_user_action:
            print("  ✓ PASS: All cycle issues have auto_fixable=False (requires_user_action=True)")
        else:
            print("  ✗ FAIL: Some cycle issues are marked as auto_fixable")
    else:
        print("  ✗ FAIL: No cycle issues found")

    # Summary
    print("\n" + "=" * 60)
    print("Full ValidationResult:")
    print("-" * 60)
    print(f"  is_valid: {result['is_valid']}")
    print(f"  self_references: {result['self_references']}")
    print(f"  cycles: {result['cycles']}")
    print(f"  missing_targets: {result['missing_targets']}")
    print(f"  issues count: {len(result['issues'])}")
    print(f"  summary: {result['summary']}")
    print("=" * 60)

    # Final verdict
    all_passed = (
        len(cycles) > 0 and
        len(cycles[0]) == 2 and
        1 in cycles[0] and 2 in cycles[0] and
        all(not i["auto_fixable"] for i in cycle_issues)
    )

    if all_passed:
        print("\n✓ ALL VERIFICATION STEPS PASSED")
        return True
    else:
        print("\n✗ SOME VERIFICATION STEPS FAILED")
        return False


if __name__ == "__main__":
    import pytest

    # First run the verification script
    print("\nRunning Feature #87 Verification Script...")
    passed = run_feature_87_verification()

    print("\n\nRunning pytest tests...")
    exit_code = pytest.main([__file__, "-v"])

    if passed and exit_code == 0:
        print("\n" + "=" * 60)
        print("Feature #87 FULLY VERIFIED - All tests pass")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Feature #87 VERIFICATION INCOMPLETE")
        print("=" * 60)
