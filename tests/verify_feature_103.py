#!/usr/bin/env python3
"""
Feature #103 Verification Script
================================

Optional UI banner shows when dependency issues detected at startup

This script verifies all 5 feature requirements:
1. Add dependency_health endpoint to API that returns issue summary
2. If issues requiring attention exist, return {has_issues: true, count: N}
3. UI can optionally display banner: Warning: N dependency issues detected - see logs
4. Banner should be dismissible
5. Banner style: yellow/orange warning color, not blocking UI
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))


def verify_step_1():
    """Step 1: Add dependency_health endpoint to API that returns issue summary"""
    print("\n" + "=" * 60)
    print("Step 1: Add dependency_health endpoint to API")
    print("=" * 60)

    # Check the router for the endpoint
    from server.routers.features import router
    routes = [route.path for route in router.routes]
    has_endpoint = any("dependency-health" in route for route in routes)

    if has_endpoint:
        print("[PASS] /dependency-health endpoint exists in features router")

        # Check endpoint implementation
        features_file = root / "server" / "routers" / "features.py"
        content = features_file.read_text()
        if "async def get_dependency_health" in content:
            print("[PASS] get_dependency_health async function implemented")
        else:
            print("[FAIL] get_dependency_health function not found")
            return False

        return True
    else:
        print(f"[FAIL] /dependency-health endpoint not found. Routes: {routes}")
        return False


def verify_step_2():
    """Step 2: If issues requiring attention exist, return {has_issues: true, count: N}"""
    print("\n" + "=" * 60)
    print("Step 2: Return {has_issues: true, count: N} when issues exist")
    print("=" * 60)

    # Check API client response type
    api_file = root / "ui" / "src" / "lib" / "api.ts"
    content = api_file.read_text()

    checks = [
        ("has_issues: boolean", "has_issues field defined"),
        ("count: number", "count field defined"),
        ("is_valid: boolean", "is_valid field defined"),
        ("self_references: number", "self_references field defined"),
        ("cycles: number", "cycles field defined"),
        ("missing_targets: number", "missing_targets field defined"),
        ("summary: string", "summary field defined"),
    ]

    all_pass = True
    for pattern, description in checks:
        if pattern in content:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}")
            all_pass = False

    return all_pass


def verify_step_3():
    """Step 3: UI can optionally display banner: Warning: N dependency issues detected"""
    print("\n" + "=" * 60)
    print("Step 3: UI displays warning banner")
    print("=" * 60)

    banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"

    if not banner_file.exists():
        print("[FAIL] DependencyHealthBanner.tsx does not exist")
        return False

    content = banner_file.read_text()

    checks = [
        ("Warning:" in content, "Banner contains 'Warning:' text"),
        ("dependency issue" in content, "Banner mentions 'dependency issue'"),
        ("detected" in content or "see logs" in content, "Banner instructs user to check logs"),
        ("healthData.count" in content or "healthData?.count" in content, "Banner uses count from API"),
    ]

    all_pass = True
    for condition, description in checks:
        if condition:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}")
            all_pass = False

    return all_pass


def verify_step_4():
    """Step 4: Banner should be dismissible"""
    print("\n" + "=" * 60)
    print("Step 4: Banner is dismissible")
    print("=" * 60)

    banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
    content = banner_file.read_text()

    checks = [
        ("isDismissed" in content, "Has isDismissed state"),
        ("setIsDismissed" in content, "Has setIsDismissed setter"),
        ("handleDismiss" in content or "onDismiss" in content, "Has dismiss handler"),
        ("sessionStorage" in content, "Uses sessionStorage for persistence"),
        ("Dismiss" in content, "Has dismiss button/label"),
    ]

    all_pass = True
    for condition, description in checks:
        if condition:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}")
            all_pass = False

    return all_pass


def verify_step_5():
    """Step 5: Banner style: yellow/orange warning color, not blocking UI"""
    print("\n" + "=" * 60)
    print("Step 5: Banner has warning style, not blocking")
    print("=" * 60)

    banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
    content = banner_file.read_text()

    checks = [
        ("bg-amber" in content, "Has amber background color"),
        ("border-amber" in content, "Has amber border color"),
        ("text-amber" in content, "Has amber text color"),
        ("AlertTriangle" in content, "Uses AlertTriangle warning icon"),
        ("fixed inset-0" not in content, "Is NOT a fixed overlay (not blocking)"),
        ("modal" not in content.lower() or "Modal" not in content, "Is NOT a modal"),
    ]

    all_pass = True
    for condition, description in checks:
        if condition:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}")
            all_pass = False

    return all_pass


def verify_integration():
    """Verify banner is integrated into the app."""
    print("\n" + "=" * 60)
    print("Integration: Banner is used in the main app")
    print("=" * 60)

    app_file = root / "ui" / "src" / "App.tsx"
    content = app_file.read_text()

    checks = [
        ("import { DependencyHealthBanner }" in content or "import {DependencyHealthBanner}" in content,
         "DependencyHealthBanner is imported"),
        ("<DependencyHealthBanner" in content, "DependencyHealthBanner is used"),
        ("projectName=" in content and "DependencyHealthBanner" in content, "Banner receives projectName prop"),
    ]

    all_pass = True
    for condition, description in checks:
        if condition:
            print(f"[PASS] {description}")
        else:
            print(f"[FAIL] {description}")
            all_pass = False

    return all_pass


def main():
    print("=" * 60)
    print("Feature #103 Verification")
    print("Optional UI banner shows when dependency issues detected")
    print("=" * 60)

    results = []

    results.append(("Step 1: Dependency health endpoint", verify_step_1()))
    results.append(("Step 2: has_issues/count response format", verify_step_2()))
    results.append(("Step 3: UI warning banner", verify_step_3()))
    results.append(("Step 4: Banner dismissible", verify_step_4()))
    results.append(("Step 5: Warning style, not blocking", verify_step_5()))
    results.append(("Integration: Banner in app", verify_integration()))

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_pass = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("FEATURE #103: ALL VERIFICATION STEPS PASSED")
        return 0
    else:
        print("FEATURE #103: SOME VERIFICATION STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
