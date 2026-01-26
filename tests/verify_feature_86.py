#!/usr/bin/env python3
"""
Verification script for Feature #86: validate_dependency_graph detects self-references

This script verifies all 4 steps required by the feature specification.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    print("=" * 60)
    print("Feature #86: validate_dependency_graph detects self-references")
    print("=" * 60)
    print()

    # Test imports
    print("Testing imports from api module...")
    from api import validate_dependency_graph, ValidationResult, DependencyIssue
    print("  Import successful!")
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
        print(f"        Result keys: {list(result.keys())}")
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
        print(f"        Issue details: {self_ref_issues[0]}")
    else:
        print(f"  FAIL: Issue not found or auto_fixable is not True")
        all_passed = False
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED")
        print()
        print("Summary of result:")
        print(f"  is_valid: {result['is_valid']}")
        print(f"  self_references: {result['self_references']}")
        print(f"  cycles: {result['cycles']}")
        print(f"  missing_targets: {result['missing_targets']}")
        print(f"  summary: {result['summary']}")
    else:
        print("SOME VERIFICATION STEPS FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
