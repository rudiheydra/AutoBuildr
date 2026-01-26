"""
Tests for validate_dependency_graph() - Feature #89: Missing Dependency Target Detection

This test file verifies that the validate_dependency_graph() function correctly
detects when a feature depends on a non-existent feature ID and returns the
missing_targets dict with the appropriate structure.

Verification Steps from Feature #89:
1. Create feature A (id=1) with dependencies=[999] (non-existent)
2. Call validate_dependency_graph() with this feature
3. Verify the result includes missing_targets dict with {1: [999]}
4. Verify the function returns structured ValidationResult with all issue types
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.dependency_resolver import validate_dependency_graph, ValidationResult


class TestMissingDependencyTargetDetection:
    """Test Feature #89: Missing dependency target detection."""

    def test_step1_create_feature_with_nonexistent_dependency(self):
        """
        Step 1: Create feature A (id=1) with dependencies=[999] (non-existent).
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}

        # Verify feature is created correctly
        assert feature_a["id"] == 1
        assert feature_a["dependencies"] == [999]
        assert 999 in feature_a["dependencies"]

    def test_step2_call_validate_dependency_graph(self):
        """
        Step 2: Call validate_dependency_graph() with this feature.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}

        result = validate_dependency_graph([feature_a])

        # Verify result is a ValidationResult dict with all required fields
        assert isinstance(result, dict)
        assert "is_valid" in result
        assert "self_references" in result
        assert "cycles" in result
        assert "missing_targets" in result
        assert "issues" in result
        assert "summary" in result

    def test_step3_verify_missing_targets_dict(self):
        """
        Step 3: Verify the result includes missing_targets dict with {1: [999]}.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}

        result = validate_dependency_graph([feature_a])

        # Verify missing_targets contains the expected mapping
        assert result["missing_targets"] == {1: [999]}
        assert 1 in result["missing_targets"]
        assert 999 in result["missing_targets"][1]
        assert result["is_valid"] is False

    def test_step4_verify_structured_validation_result(self):
        """
        Step 4: Verify the function returns structured ValidationResult with all issue types.
        """
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}

        result = validate_dependency_graph([feature_a])

        # Find the missing_target issue
        missing_target_issues = [
            issue for issue in result["issues"]
            if issue["issue_type"] == "missing_target" and issue["feature_id"] == 1
        ]

        assert len(missing_target_issues) == 1
        issue = missing_target_issues[0]

        # Verify issue structure
        assert issue["feature_id"] == 1
        assert issue["issue_type"] == "missing_target"
        assert "details" in issue
        assert "message" in issue["details"]
        assert "missing_id" in issue["details"]
        assert issue["details"]["missing_id"] == 999
        assert issue["auto_fixable"] is True


class TestMultipleMissingTargets:
    """Test missing target detection with multiple features and dependencies."""

    def test_multiple_missing_targets_single_feature(self):
        """Test detection of multiple missing targets in a single feature."""
        feature = {"id": 1, "name": "Feature", "dependencies": [998, 999, 1000]}

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is False
        assert 1 in result["missing_targets"]
        assert set(result["missing_targets"][1]) == {998, 999, 1000}

        # Check each missing target has an issue
        missing_issues = [
            i for i in result["issues"] if i["issue_type"] == "missing_target"
        ]
        assert len(missing_issues) == 3

    def test_multiple_features_with_missing_targets(self):
        """Test detection of missing targets in multiple features."""
        feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [888]}

        result = validate_dependency_graph([feature_a, feature_b])

        assert result["is_valid"] is False
        assert result["missing_targets"] == {1: [999], 2: [888]}

    def test_mixed_valid_and_missing_dependencies(self):
        """Test feature with both valid and missing dependencies."""
        feature_a = {"id": 1, "name": "Feature A", "dependencies": []}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1, 999]}  # 1 is valid, 999 is missing

        result = validate_dependency_graph([feature_a, feature_b])

        assert result["is_valid"] is False
        assert result["missing_targets"] == {2: [999]}
        assert 1 not in result["missing_targets"]

    def test_no_missing_targets_when_all_exist(self):
        """Test that valid dependencies don't create false positives."""
        feature_a = {"id": 1, "name": "Feature A", "dependencies": []}
        feature_b = {"id": 2, "name": "Feature B", "dependencies": [1]}
        feature_c = {"id": 3, "name": "Feature C", "dependencies": [1, 2]}

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        assert result["is_valid"] is True
        assert result["missing_targets"] == {}


class TestMissingTargetIssueDetails:
    """Test the structure and content of missing target issues."""

    def test_issue_contains_feature_id(self):
        """Test that issue includes the correct feature_id."""
        feature = {"id": 42, "name": "Test", "dependencies": [999]}

        result = validate_dependency_graph([feature])

        issue = result["issues"][0]
        assert issue["feature_id"] == 42

    def test_issue_contains_missing_id_in_details(self):
        """Test that issue includes the missing dependency ID in details."""
        feature = {"id": 1, "name": "Test", "dependencies": [777]}

        result = validate_dependency_graph([feature])

        issue = result["issues"][0]
        assert issue["details"]["missing_id"] == 777

    def test_issue_contains_descriptive_message(self):
        """Test that issue includes a helpful message in details."""
        feature = {"id": 1, "name": "Test", "dependencies": [999]}

        result = validate_dependency_graph([feature])

        issue = result["issues"][0]
        assert "1" in issue["details"]["message"]
        assert "999" in issue["details"]["message"]
        assert "non-existent" in issue["details"]["message"].lower() or "missing" in issue["details"]["message"].lower()

    def test_missing_target_is_auto_fixable(self):
        """Test that missing target issues are marked as auto-fixable."""
        feature = {"id": 1, "name": "Test", "dependencies": [999]}

        result = validate_dependency_graph([feature])

        missing_issues = [i for i in result["issues"] if i["issue_type"] == "missing_target"]
        assert len(missing_issues) > 0
        for issue in missing_issues:
            assert issue["auto_fixable"] is True

    def test_summary_mentions_missing_targets(self):
        """Test that summary message mentions missing targets."""
        feature = {"id": 1, "name": "Test", "dependencies": [999]}

        result = validate_dependency_graph([feature])

        assert "missing" in result["summary"].lower()
        assert "1" in result["summary"]  # Count of missing targets


class TestMissingTargetEdgeCases:
    """Edge case tests for missing target detection."""

    def test_empty_features_list(self):
        """Test with empty features list."""
        result = validate_dependency_graph([])

        assert result["is_valid"] is True
        assert result["missing_targets"] == {}

    def test_feature_with_no_dependencies_key(self):
        """Test feature without dependencies key."""
        feature = {"id": 1, "name": "Test"}  # No "dependencies" key

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is True
        assert result["missing_targets"] == {}

    def test_feature_with_none_dependencies(self):
        """Test feature with None dependencies."""
        feature = {"id": 1, "name": "Test", "dependencies": None}

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is True
        assert result["missing_targets"] == {}

    def test_feature_with_empty_dependencies(self):
        """Test feature with empty dependencies list."""
        feature = {"id": 1, "name": "Test", "dependencies": []}

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is True
        assert result["missing_targets"] == {}

    def test_single_feature_depending_on_negative_id(self):
        """Test feature depending on negative ID (non-existent)."""
        feature = {"id": 1, "name": "Test", "dependencies": [-1]}

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is False
        assert result["missing_targets"] == {1: [-1]}


class TestMixedIssueTypes:
    """Test combinations of missing targets with other issue types."""

    def test_missing_target_and_self_reference(self):
        """Test feature with both missing target and self-reference."""
        feature = {"id": 1, "name": "Test", "dependencies": [1, 999]}  # 1 is self-ref, 999 is missing

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is False
        assert 1 in result["self_references"]
        assert result["missing_targets"] == {1: [999]}

        # Check both issue types exist
        issue_types = {i["issue_type"] for i in result["issues"]}
        assert "self_reference" in issue_types
        assert "missing_target" in issue_types

    def test_missing_target_and_cycle(self):
        """Test graph with both missing targets and cycles."""
        # A -> B -> A creates a cycle
        # A also depends on 999 (missing)
        feature_a = {"id": 1, "name": "A", "dependencies": [2, 999]}
        feature_b = {"id": 2, "name": "B", "dependencies": [1]}

        result = validate_dependency_graph([feature_a, feature_b])

        assert result["is_valid"] is False
        assert result["missing_targets"] == {1: [999]}
        assert len(result["cycles"]) > 0

        # Check both issue types exist
        issue_types = {i["issue_type"] for i in result["issues"]}
        assert "cycle" in issue_types
        assert "missing_target" in issue_types

    def test_all_three_issue_types(self):
        """Test graph with self-reference, cycle, and missing target."""
        # Feature A: self-reference
        feature_a = {"id": 1, "name": "A", "dependencies": [1]}
        # Features B and C: cycle
        feature_b = {"id": 2, "name": "B", "dependencies": [3]}
        feature_c = {"id": 3, "name": "C", "dependencies": [2, 999]}  # 999 is missing

        result = validate_dependency_graph([feature_a, feature_b, feature_c])

        assert result["is_valid"] is False
        assert 1 in result["self_references"]
        assert len(result["cycles"]) > 0
        assert result["missing_targets"] == {3: [999]}

        # Check all three issue types exist
        issue_types = {i["issue_type"] for i in result["issues"]}
        assert "self_reference" in issue_types
        assert "cycle" in issue_types
        assert "missing_target" in issue_types


def run_feature_89_verification():
    """
    Run the verification steps from Feature #89 and print results.
    """
    print("=" * 60)
    print("Feature #89: Missing Dependency Target Detection Verification")
    print("=" * 60)

    all_passed = True

    # Step 1: Create feature A (id=1) with dependencies=[999] (non-existent)
    print("\nStep 1: Create feature A (id=1) with dependencies=[999] (non-existent)")
    feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}
    print(f"  Created: {feature_a}")
    print("  PASS: Feature created with non-existent dependency")

    # Step 2: Call validate_dependency_graph() with this feature
    print("\nStep 2: Call validate_dependency_graph() with this feature")
    result = validate_dependency_graph([feature_a])
    print(f"  Result keys: {list(result.keys())}")
    if all(k in result for k in ["is_valid", "missing_targets", "issues", "summary"]):
        print("  PASS: validate_dependency_graph() returns ValidationResult with all required fields")
    else:
        print("  FAIL: ValidationResult missing required fields")
        all_passed = False

    # Step 3: Verify the result includes missing_targets dict with {1: [999]}
    print("\nStep 3: Verify the result includes missing_targets dict with {1: [999]}")
    missing_targets = result["missing_targets"]
    print(f"  missing_targets = {missing_targets}")
    if missing_targets == {1: [999]}:
        print("  PASS: missing_targets correctly identifies {1: [999]}")
    else:
        print(f"  FAIL: Expected {{1: [999]}}, got {missing_targets}")
        all_passed = False

    # Step 4: Verify structured ValidationResult with all issue types
    print("\nStep 4: Verify the function returns structured ValidationResult with all issue types")
    missing_target_issues = [
        i for i in result["issues"]
        if i["issue_type"] == "missing_target" and i["feature_id"] == 1
    ]
    if len(missing_target_issues) == 1:
        issue = missing_target_issues[0]
        print(f"  Issue found: {issue}")
        if (issue["feature_id"] == 1 and
            issue["issue_type"] == "missing_target" and
            "details" in issue and
            issue["details"].get("missing_id") == 999 and
            issue["auto_fixable"] is True):
            print("  PASS: Issue has correct structure with feature_id, issue_type, details, and auto_fixable")
        else:
            print("  FAIL: Issue structure is incorrect")
            all_passed = False
    else:
        print(f"  FAIL: Expected 1 missing_target issue, found {len(missing_target_issues)}")
        all_passed = False

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

    if all_passed:
        print("\nALL VERIFICATION STEPS PASSED")
        return True
    else:
        print("\nSOME VERIFICATION STEPS FAILED")
        return False


if __name__ == "__main__":
    import pytest

    # First run the verification script
    print("\nRunning Feature #89 Verification Script...")
    passed = run_feature_89_verification()

    print("\n\nRunning pytest tests...")
    exit_code = pytest.main([__file__, "-v"])

    if passed and exit_code == 0:
        print("\n" + "=" * 60)
        print("Feature #89 FULLY VERIFIED - All tests pass")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Feature #89 VERIFICATION INCOMPLETE")
        print("=" * 60)
