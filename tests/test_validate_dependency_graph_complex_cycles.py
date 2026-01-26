"""
Tests for validate_dependency_graph() - Feature #88: Complex Cycle Detection

This test file verifies that the validate_dependency_graph() function correctly
detects complex cycles (A -> B -> C -> A) in the dependency graph and returns
the full cycle path for user review. It also verifies that missing dependencies
to non-existent features are detected alongside cycles.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.dependency_resolver import validate_dependency_graph, ValidationResult


class TestComplexCycleDetection:
    """Test Feature #88: Complex cycle detection (A -> B -> C -> A)"""

    def test_complex_cycle_three_features(self):
        """
        Feature #88 Steps 1-5: Create A (id=1) with deps=[2], B (id=2) with deps=[3],
        C (id=3) with deps=[1]. Call validate_dependency_graph() and verify cycle detected.
        """
        # Step 1: Create feature A (id=1) with dependencies=[2]
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}

        # Step 2: Create feature B (id=2) with dependencies=[3]
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}

        # Step 3: Create feature C (id=3) with dependencies=[1]
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        # Step 4: Call validate_dependency_graph() with all three features
        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        # Verify the result is a ValidationResult
        assert isinstance(result, dict)
        assert "is_valid" in result
        assert "cycles" in result
        assert "issues" in result

        # The graph should be invalid due to the cycle
        assert result["is_valid"] is False

        # Step 5: Verify the result includes the complete cycle path [1, 2, 3]
        assert len(result["cycles"]) > 0, "Expected at least one cycle to be detected"

        # Check that the cycle contains all three features 1, 2, and 3
        cycle = result["cycles"][0]
        assert 1 in cycle, "Cycle should contain feature 1"
        assert 2 in cycle, "Cycle should contain feature 2"
        assert 3 in cycle, "Cycle should contain feature 3"
        assert len(cycle) == 3, f"Complex cycle should have 3 features, got {len(cycle)}"

    def test_cycle_path_order(self):
        """
        Verify that the cycle path is returned in a consistent order.
        The implementation normalizes cycles starting from the smallest ID.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        cycle = result["cycles"][0]
        # Normalized cycles start from the smallest ID
        assert cycle[0] == 1, f"Normalized cycle should start with 1, got {cycle[0]}"
        assert cycle == [1, 2, 3], f"Expected cycle [1, 2, 3], got {cycle}"

    def test_complex_cycle_four_features(self):
        """
        Test even longer cycle: A -> B -> C -> D -> A
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [4]}
        feature_d = {"id": 4, "name": "Feature D", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c, feature_d])

        assert result["is_valid"] is False
        assert len(result["cycles"]) > 0

        cycle = result["cycles"][0]
        assert len(cycle) == 4, f"Four-feature cycle should have 4 features, got {len(cycle)}"
        assert set(cycle) == {1, 2, 3, 4}, "Cycle should contain features 1, 2, 3, 4"

    def test_complex_cycle_five_features(self):
        """
        Test even longer cycle: A -> B -> C -> D -> E -> A
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [4]}
        feature_d = {"id": 4, "name": "Feature D", "dependencies": [5]}
        feature_e = {"id": 5, "name": "Feature E", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c, feature_d, feature_e])

        assert result["is_valid"] is False
        assert len(result["cycles"]) > 0

        cycle = result["cycles"][0]
        assert len(cycle) == 5, f"Five-feature cycle should have 5 features, got {len(cycle)}"
        assert set(cycle) == {1, 2, 3, 4, 5}, "Cycle should contain features 1, 2, 3, 4, 5"

    def test_cycle_issue_requires_user_action(self):
        """
        Verify that cycle issues are NOT auto-fixable (requires user action).
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        # Find cycle issues
        cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]
        assert len(cycle_issues) == 3, "Expected 3 cycle issues (one per feature)"

        # Verify auto_fixable is False (which means requires_user_action=True)
        for issue in cycle_issues:
            assert issue["auto_fixable"] is False, \
                "Cycle issues should NOT be auto-fixable (requires user action)"

    def test_cycle_issue_details_contain_full_path(self):
        """
        Verify that cycle issues contain the full cycle_path in details.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        # Find cycle issues
        cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]

        for issue in cycle_issues:
            assert "details" in issue
            assert "cycle_path" in issue["details"], \
                "Cycle issue should include cycle_path in details"
            cycle_path = issue["details"]["cycle_path"]
            # All cycle issues should contain the same full path
            assert set(cycle_path) == {1, 2, 3}, \
                f"Cycle path should contain all 3 features, got {cycle_path}"

    def test_all_features_in_cycle_get_issues(self):
        """
        Verify that each feature in the cycle gets its own issue entry.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]
        cycle_feature_ids = {issue["feature_id"] for issue in cycle_issues}

        assert cycle_feature_ids == {1, 2, 3}, \
            f"All features in cycle should have issues, got {cycle_feature_ids}"

    def test_summary_mentions_cycle_with_user_action(self):
        """
        Verify that the summary mentions cycles require user action.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        assert "cycle" in result["summary"].lower(), \
            f"Summary should mention 'cycle', got: {result['summary']}"
        assert "user action" in result["summary"].lower(), \
            f"Summary should mention 'user action', got: {result['summary']}"


class TestMissingDependenciesWithCycles:
    """Feature #88 Step 6: Verify missing dependencies are also detected."""

    def test_missing_dependency_detected_with_cycle(self):
        """
        Step 6: Verify missing dependencies to non-existent features are also detected
        when there's also a cycle in the graph.
        """
        # Create a complex cycle AND a missing dependency
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2, 99]}  # 99 doesn't exist
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        # Verify cycle is detected
        assert result["is_valid"] is False
        assert len(result["cycles"]) > 0

        # Verify missing dependency is also detected
        assert 1 in result["missing_targets"], "Feature 1 should have missing targets"
        assert 99 in result["missing_targets"][1], "Missing target 99 should be detected"

    def test_missing_dependency_issue_is_auto_fixable(self):
        """
        Verify that missing dependency issues are auto-fixable (unlike cycles).
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2, 99]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        missing_issues = [i for i in result["issues"] if i["issue_type"] == "missing_target"]
        assert len(missing_issues) > 0, "Expected missing_target issues"

        for issue in missing_issues:
            assert issue["auto_fixable"] is True, \
                "Missing target issues should be auto-fixable"

    def test_multiple_missing_dependencies(self):
        """
        Test detection of multiple missing dependencies alongside a cycle.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2, 88, 99]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        # Verify both missing targets detected
        assert 88 in result["missing_targets"][1]
        assert 99 in result["missing_targets"][1]

    def test_summary_includes_both_cycle_and_missing(self):
        """
        Verify summary mentions both cycles and missing targets.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2, 99]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        assert "cycle" in result["summary"].lower()
        assert "missing" in result["summary"].lower()


class TestMultipleCycles:
    """Test detection of multiple separate cycles in the same graph."""

    def test_two_separate_cycles(self):
        """
        Test detection of two independent cycles in the same graph.
        """
        # Cycle 1: A -> B -> A
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}

        # Cycle 2: C -> D -> E -> C (independent)
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [4]}
        feature_d = {"id": 4, "name": "Feature D", "dependencies": [5]}
        feature_e = {"id": 5, "name": "Feature E", "dependencies": [3]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c, feature_d, feature_e])

        assert result["is_valid"] is False
        assert len(result["cycles"]) == 2, f"Expected 2 cycles, got {len(result['cycles'])}"

        # Extract all cycle members
        all_cycle_members = set()
        for cycle in result["cycles"]:
            all_cycle_members.update(cycle)

        assert all_cycle_members == {1, 2, 3, 4, 5}, \
            f"All features should be in cycles, got {all_cycle_members}"

    def test_overlapping_cycles_detection(self):
        """
        Test a more complex graph with overlapping cycles.
        Graph: A -> B -> C -> A (cycle 1)
               B -> D -> B (cycle 2, overlaps with B)
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3, 4]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}
        feature_d = {"id": 4, "name": "Feature D", "dependencies": [2]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c, feature_d])

        assert result["is_valid"] is False
        # Should detect at least 2 cycles
        assert len(result["cycles"]) >= 2, f"Expected at least 2 cycles, got {len(result['cycles'])}"


class TestComplexCycleEdgeCases:
    """Test edge cases for complex cycle detection."""

    def test_cycle_with_extra_features(self):
        """
        Test that features outside the cycle are not included in cycle path.
        """
        # A -> B -> C -> A (cycle)
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        # D depends on A but is not part of the cycle
        feature_d = {"id": 4, "name": "Feature D", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c, feature_d])

        assert result["is_valid"] is False
        cycle = result["cycles"][0]

        # D should not be in the cycle
        assert 4 not in cycle, "Feature D should not be in the cycle path"
        assert len(cycle) == 3

    def test_cycle_preserves_all_cycle_members(self):
        """
        Ensure that when reporting cycle issues, all members are accounted for.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        cycle_issues = [i for i in result["issues"] if i["issue_type"] == "cycle"]

        # Each feature in the cycle should have exactly one issue
        feature_ids_with_issues = [issue["feature_id"] for issue in cycle_issues]
        assert sorted(feature_ids_with_issues) == [1, 2, 3]


class TestValidationResultStructureForComplexCycles:
    """Test that ValidationResult has correct structure for complex cycles."""

    def test_result_has_all_required_fields(self):
        """
        Verify that ValidationResult contains all required fields.
        """
        feature_a = {"id": 1, "name": "A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        required_fields = ["is_valid", "self_references", "cycles", "missing_targets", "issues", "summary"]
        for field in required_fields:
            assert field in result, f"ValidationResult missing required field: {field}"

    def test_cycles_is_list_of_lists(self):
        """
        Verify that cycles field is a list of lists (cycle paths).
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        assert isinstance(result["cycles"], list)
        for cycle in result["cycles"]:
            assert isinstance(cycle, list), "Each cycle should be a list of feature IDs"
            for fid in cycle:
                assert isinstance(fid, int), "Cycle should contain integer feature IDs"

    def test_issue_structure(self):
        """
        Verify the structure of DependencyIssue objects.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        for issue in result["issues"]:
            assert "feature_id" in issue, "Issue missing feature_id"
            assert "issue_type" in issue, "Issue missing issue_type"
            assert "details" in issue, "Issue missing details"
            assert "auto_fixable" in issue, "Issue missing auto_fixable"
            assert isinstance(issue["feature_id"], int)
            assert isinstance(issue["issue_type"], str)
            assert isinstance(issue["details"], dict)
            assert isinstance(issue["auto_fixable"], bool)


def run_feature_88_verification():
    """
    Run the verification steps from Feature #88 and print results.
    """
    print("=" * 60)
    print("Feature #88: Complex Cycle Detection Verification")
    print("=" * 60)

    all_steps_passed = True

    # Step 1: Create feature A (id=1) with dependencies=[2]
    print("\nStep 1: Create feature A (id=1) with dependencies=[2]")
    feature_a = {"id": 1, "name": "Feature A", "dependencies": [2]}
    print(f"  Created: {feature_a}")
    print("  PASS")

    # Step 2: Create feature B (id=2) with dependencies=[3]
    print("\nStep 2: Create feature B (id=2) with dependencies=[3]")
    feature_b = {"id": 2, "name": "Feature B", "dependencies": [3]}
    print(f"  Created: {feature_b}")
    print("  PASS")

    # Step 3: Create feature C (id=3) with dependencies=[1]
    print("\nStep 3: Create feature C (id=3) with dependencies=[1]")
    feature_c = {"id": 3, "name": "Feature C", "dependencies": [1]}
    print(f"  Created: {feature_c}")
    print("  PASS")

    # Step 4: Call validate_dependency_graph() with all three features
    print("\nStep 4: Call validate_dependency_graph() with all three features")
    result = validate_dependency_graph([feature_a, feature_b, feature_c])
    print(f"  Result keys: {list(result.keys())}")
    print("  PASS")

    # Step 5: Verify the result includes the complete cycle path [1, 2, 3]
    print("\nStep 5: Verify the result includes the complete cycle path [1, 2, 3]")
    cycles = result["cycles"]
    print(f"  cycles = {cycles}")
    if cycles and len(cycles) > 0:
        cycle = cycles[0]
        if 1 in cycle and 2 in cycle and 3 in cycle and len(cycle) == 3:
            print("  PASS: Cycle contains all three features [1, 2, 3]")
        else:
            print(f"  FAIL: Cycle does not contain all three features: {cycle}")
            all_steps_passed = False
    else:
        print("  FAIL: No cycles detected")
        all_steps_passed = False

    # Step 6: Verify missing dependencies to non-existent features are also detected
    print("\nStep 6: Verify missing dependencies to non-existent features are also detected")
    # Create a new test case with both cycle and missing dependency
    feature_a_with_missing = {"id": 1, "name": "Feature A", "dependencies": [2, 99]}
    result_with_missing = validate_dependency_graph([feature_a_with_missing, feature_b, feature_c])

    if 1 in result_with_missing["missing_targets"] and 99 in result_with_missing["missing_targets"][1]:
        print(f"  missing_targets = {result_with_missing['missing_targets']}")
        print("  PASS: Missing dependency 99 detected for feature 1")
    else:
        print(f"  FAIL: Missing dependency not detected: {result_with_missing['missing_targets']}")
        all_steps_passed = False

    # Summary
    print("\n" + "=" * 60)
    print("Full ValidationResult (from Step 5):")
    print("-" * 60)
    print(f"  is_valid: {result['is_valid']}")
    print(f"  self_references: {result['self_references']}")
    print(f"  cycles: {result['cycles']}")
    print(f"  missing_targets: {result['missing_targets']}")
    print(f"  issues count: {len(result['issues'])}")
    print(f"  summary: {result['summary']}")
    print("=" * 60)

    # Final verdict
    if all_steps_passed:
        print("\n" + "=" * 60)
        print("ALL VERIFICATION STEPS PASSED")
        print("=" * 60)
        return True
    else:
        print("\n" + "=" * 60)
        print("SOME VERIFICATION STEPS FAILED")
        print("=" * 60)
        return False


if __name__ == "__main__":
    import pytest

    # First run the verification script
    print("\nRunning Feature #88 Verification Script...")
    passed = run_feature_88_verification()

    print("\n\nRunning pytest tests...")
    exit_code = pytest.main([__file__, "-v"])

    if passed and exit_code == 0:
        print("\n" + "=" * 60)
        print("Feature #88 FULLY VERIFIED - All tests pass")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Feature #88 VERIFICATION INCOMPLETE")
        print("=" * 60)
