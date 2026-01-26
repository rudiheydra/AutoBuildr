"""
Tests for validate_dependency_graph() function.

Tests Feature #86: Core validate_dependency_graph function detects self-references

Verification Steps:
1. Create a test feature with id=1 and dependencies=[1] (self-reference)
2. Call validate_dependency_graph() with this feature
3. Verify the result includes self_references list containing feature id 1
4. Verify the error type is marked as auto_fixable=True
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.dependency_resolver import validate_dependency_graph, ValidationResult


class TestValidateDependencyGraphSelfReferences:
    """Tests for self-reference detection in validate_dependency_graph()."""

    def test_step1_create_feature_with_self_reference(self):
        """Step 1: Create a test feature with id=1 and dependencies=[1]."""
        # Create the test feature with self-reference
        feature = {
            "id": 1,
            "name": "Test Feature",
            "dependencies": [1],  # Self-reference!
        }

        # Verify we can create and access the feature
        assert feature["id"] == 1
        assert feature["dependencies"] == [1]
        assert feature["id"] in feature["dependencies"]

    def test_step2_call_validate_dependency_graph(self):
        """Step 2: Call validate_dependency_graph() with this feature."""
        feature = {
            "id": 1,
            "name": "Test Feature",
            "dependencies": [1],
        }

        # Call validate_dependency_graph
        result = validate_dependency_graph([feature])

        # Verify result is a ValidationResult dict
        assert isinstance(result, dict)
        assert "is_valid" in result
        assert "self_references" in result
        assert "cycles" in result
        assert "missing_targets" in result
        assert "issues" in result
        assert "summary" in result

    def test_step3_verify_self_references_list_contains_feature_id_1(self):
        """Step 3: Verify the result includes self_references list containing feature id 1."""
        feature = {
            "id": 1,
            "name": "Test Feature",
            "dependencies": [1],
        }

        result = validate_dependency_graph([feature])

        # Verify self_references contains feature id 1
        assert 1 in result["self_references"]
        assert len(result["self_references"]) == 1
        assert result["is_valid"] is False

    def test_step4_verify_error_type_is_auto_fixable_true(self):
        """Step 4: Verify the error type is marked as auto_fixable=True."""
        feature = {
            "id": 1,
            "name": "Test Feature",
            "dependencies": [1],
        }

        result = validate_dependency_graph([feature])

        # Find the issue for feature 1
        self_ref_issues = [
            issue for issue in result["issues"]
            if issue["issue_type"] == "self_reference" and issue["feature_id"] == 1
        ]

        assert len(self_ref_issues) == 1
        issue = self_ref_issues[0]
        assert issue["auto_fixable"] is True
        assert issue["feature_id"] == 1
        assert issue["issue_type"] == "self_reference"


class TestValidateDependencyGraphMultipleFeatures:
    """Tests for validate_dependency_graph() with multiple features."""

    def test_multiple_self_references(self):
        """Test detection of multiple self-references in different features."""
        features = [
            {"id": 1, "name": "Feature 1", "dependencies": [1]},  # Self-ref
            {"id": 2, "name": "Feature 2", "dependencies": [2]},  # Self-ref
            {"id": 3, "name": "Feature 3", "dependencies": []},   # No self-ref
        ]

        result = validate_dependency_graph(features)

        assert result["is_valid"] is False
        assert set(result["self_references"]) == {1, 2}
        assert 3 not in result["self_references"]

        # Check each self-reference issue is auto-fixable
        self_ref_issues = [
            i for i in result["issues"] if i["issue_type"] == "self_reference"
        ]
        assert len(self_ref_issues) == 2
        for issue in self_ref_issues:
            assert issue["auto_fixable"] is True

    def test_healthy_graph_no_issues(self):
        """Test that a healthy graph returns is_valid=True."""
        features = [
            {"id": 1, "name": "Feature 1", "dependencies": []},
            {"id": 2, "name": "Feature 2", "dependencies": [1]},
            {"id": 3, "name": "Feature 3", "dependencies": [1, 2]},
        ]

        result = validate_dependency_graph(features)

        assert result["is_valid"] is True
        assert result["self_references"] == []
        assert result["cycles"] == []
        assert result["missing_targets"] == {}
        assert result["issues"] == []
        assert result["summary"] == "Dependency graph is healthy"

    def test_self_reference_among_valid_dependencies(self):
        """Test that self-reference is detected even with valid dependencies."""
        features = [
            {"id": 1, "name": "Feature 1", "dependencies": []},
            {"id": 2, "name": "Feature 2", "dependencies": [1, 2]},  # Self-ref + valid
        ]

        result = validate_dependency_graph(features)

        assert result["is_valid"] is False
        assert 2 in result["self_references"]
        assert 1 not in result["self_references"]


class TestValidateDependencyGraphIssueDetails:
    """Tests for issue details in validate_dependency_graph()."""

    def test_issue_has_feature_id(self):
        """Test that issue includes correct feature_id."""
        feature = {"id": 42, "name": "Test", "dependencies": [42]}

        result = validate_dependency_graph([feature])

        issue = result["issues"][0]
        assert issue["feature_id"] == 42

    def test_issue_has_message_in_details(self):
        """Test that issue includes helpful message in details."""
        feature = {"id": 1, "name": "Test", "dependencies": [1]}

        result = validate_dependency_graph([feature])

        issue = result["issues"][0]
        assert "message" in issue["details"]
        assert "1" in issue["details"]["message"]

    def test_summary_includes_self_reference_count(self):
        """Test that summary message includes self-reference count."""
        features = [
            {"id": 1, "name": "F1", "dependencies": [1]},
            {"id": 2, "name": "F2", "dependencies": [2]},
            {"id": 3, "name": "F3", "dependencies": [3]},
        ]

        result = validate_dependency_graph(features)

        assert "3 self-reference(s)" in result["summary"]
        assert "auto-fixable" in result["summary"]


class TestValidateDependencyGraphEdgeCases:
    """Edge case tests for validate_dependency_graph()."""

    def test_empty_features_list(self):
        """Test with empty features list."""
        result = validate_dependency_graph([])

        assert result["is_valid"] is True
        assert result["self_references"] == []
        assert result["issues"] == []

    def test_feature_with_no_dependencies_key(self):
        """Test feature without dependencies key."""
        feature = {"id": 1, "name": "Test"}  # No "dependencies" key

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is True
        assert result["self_references"] == []

    def test_feature_with_none_dependencies(self):
        """Test feature with None dependencies."""
        feature = {"id": 1, "name": "Test", "dependencies": None}

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is True
        assert result["self_references"] == []

    def test_feature_with_empty_dependencies(self):
        """Test feature with empty dependencies list."""
        feature = {"id": 1, "name": "Test", "dependencies": []}

        result = validate_dependency_graph([feature])

        assert result["is_valid"] is True
        assert result["self_references"] == []


def run_verification_steps():
    """Run all verification steps for Feature #86 and report results."""
    print("=" * 60)
    print("Feature #86: validate_dependency_graph detects self-references")
    print("=" * 60)
    print()

    all_passed = True

    # Step 1: Create a test feature with id=1 and dependencies=[1]
    print("Step 1: Create a test feature with id=1 and dependencies=[1]")
    feature = {"id": 1, "name": "Test Feature", "dependencies": [1]}
    if feature["id"] == 1 and feature["dependencies"] == [1]:
        print("  PASS: Feature created with self-reference")
    else:
        print("  FAIL: Feature not created correctly")
        all_passed = False
    print()

    # Step 2: Call validate_dependency_graph() with this feature
    print("Step 2: Call validate_dependency_graph() with this feature")
    result = validate_dependency_graph([feature])
    if isinstance(result, dict) and "self_references" in result:
        print("  PASS: validate_dependency_graph() returns ValidationResult")
    else:
        print("  FAIL: validate_dependency_graph() did not return expected result")
        all_passed = False
    print()

    # Step 3: Verify self_references list contains feature id 1
    print("Step 3: Verify self_references list contains feature id 1")
    if 1 in result["self_references"]:
        print(f"  PASS: self_references = {result['self_references']}")
    else:
        print(f"  FAIL: self_references = {result['self_references']}, expected [1]")
        all_passed = False
    print()

    # Step 4: Verify the error type is marked as auto_fixable=True
    print("Step 4: Verify the error type is marked as auto_fixable=True")
    self_ref_issues = [
        i for i in result["issues"]
        if i["issue_type"] == "self_reference" and i["feature_id"] == 1
    ]
    if self_ref_issues and self_ref_issues[0]["auto_fixable"] is True:
        print(f"  PASS: auto_fixable = {self_ref_issues[0]['auto_fixable']}")
    else:
        print(f"  FAIL: Issue not found or auto_fixable is not True")
        all_passed = False
    print()

    print("=" * 60)
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED")
    else:
        print("SOME VERIFICATION STEPS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    # Run verification steps first
    success = run_verification_steps()

    # Then run all pytest tests
    import pytest
    exit_code = pytest.main([__file__, "-v", "--tb=short"])

    sys.exit(0 if success and exit_code == 0 else 1)
