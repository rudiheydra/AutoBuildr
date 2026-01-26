#!/usr/bin/env python3
"""
Feature #89 Verification Script
===============================

Feature: Core validate_dependency_graph function detects missing dependency targets
Category: error-handling

Description:
The validate_dependency_graph() function should detect when a feature depends on
a non-existent feature ID.

Verification Steps:
1. Create feature A (id=1) with dependencies=[999] (non-existent)
2. Call validate_dependency_graph() with this feature
3. Verify the result includes missing_targets dict with {1: [999]}
4. Verify the function returns structured ValidationResult with all issue types
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.dependency_resolver import validate_dependency_graph


def verify_feature_89():
    """Verify all steps of Feature #89."""
    print("=" * 70)
    print("Feature #89 Verification: Missing Dependency Target Detection")
    print("=" * 70)
    print()

    all_passed = True
    results = []

    # Step 1: Create feature A (id=1) with dependencies=[999] (non-existent)
    print("Step 1: Create feature A (id=1) with dependencies=[999] (non-existent)")
    print("-" * 70)
    feature_a = {"id": 1, "name": "Feature A", "dependencies": [999]}
    print(f"  Created feature: {feature_a}")

    if feature_a["id"] == 1 and feature_a["dependencies"] == [999]:
        print("  PASS: Feature created with non-existent dependency ID 999")
        results.append(("Step 1", "PASS"))
    else:
        print("  FAIL: Feature not created correctly")
        results.append(("Step 1", "FAIL"))
        all_passed = False
    print()

    # Step 2: Call validate_dependency_graph() with this feature
    print("Step 2: Call validate_dependency_graph() with this feature")
    print("-" * 70)
    result = validate_dependency_graph([feature_a])
    print(f"  Returned result keys: {list(result.keys())}")

    required_keys = ["is_valid", "self_references", "cycles", "missing_targets", "issues", "summary"]
    if all(k in result for k in required_keys):
        print(f"  PASS: ValidationResult contains all required keys")
        results.append(("Step 2", "PASS"))
    else:
        missing = [k for k in required_keys if k not in result]
        print(f"  FAIL: Missing keys: {missing}")
        results.append(("Step 2", "FAIL"))
        all_passed = False
    print()

    # Step 3: Verify the result includes missing_targets dict with {1: [999]}
    print("Step 3: Verify the result includes missing_targets dict with {1: [999]}")
    print("-" * 70)
    missing_targets = result.get("missing_targets", {})
    print(f"  missing_targets = {missing_targets}")

    if missing_targets == {1: [999]}:
        print("  PASS: missing_targets correctly contains {1: [999]}")
        results.append(("Step 3", "PASS"))
    else:
        print(f"  FAIL: Expected {{1: [999]}}, got {missing_targets}")
        results.append(("Step 3", "FAIL"))
        all_passed = False
    print()

    # Step 4: Verify structured ValidationResult with all issue types
    print("Step 4: Verify the function returns structured ValidationResult with all issue types")
    print("-" * 70)

    # Check for missing_target issue
    missing_target_issues = [
        issue for issue in result.get("issues", [])
        if issue.get("issue_type") == "missing_target" and issue.get("feature_id") == 1
    ]

    if len(missing_target_issues) == 1:
        issue = missing_target_issues[0]
        print(f"  Found missing_target issue: {issue}")

        # Verify issue structure
        checks = [
            (issue.get("feature_id") == 1, "feature_id == 1"),
            (issue.get("issue_type") == "missing_target", "issue_type == 'missing_target'"),
            ("details" in issue, "has 'details' key"),
            (issue.get("details", {}).get("missing_id") == 999, "details.missing_id == 999"),
            (issue.get("auto_fixable") is True, "auto_fixable == True"),
        ]

        all_checks_pass = True
        for check_result, check_name in checks:
            status = "PASS" if check_result else "FAIL"
            print(f"    {status}: {check_name}")
            if not check_result:
                all_checks_pass = False
                all_passed = False

        if all_checks_pass:
            results.append(("Step 4", "PASS"))
        else:
            results.append(("Step 4", "FAIL"))
    else:
        print(f"  FAIL: Expected 1 missing_target issue, found {len(missing_target_issues)}")
        results.append(("Step 4", "FAIL"))
        all_passed = False
    print()

    # Print summary
    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    for step, status in results:
        print(f"  {step}: {status}")
    print()

    print("Full ValidationResult:")
    print(f"  is_valid: {result['is_valid']}")
    print(f"  self_references: {result['self_references']}")
    print(f"  cycles: {result['cycles']}")
    print(f"  missing_targets: {result['missing_targets']}")
    print(f"  issues: {result['issues']}")
    print(f"  summary: {result['summary']}")
    print()

    if all_passed:
        print("=" * 70)
        print("FEATURE #89 VERIFICATION: ALL STEPS PASSED")
        print("=" * 70)
        return 0
    else:
        print("=" * 70)
        print("FEATURE #89 VERIFICATION: SOME STEPS FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(verify_feature_89())
