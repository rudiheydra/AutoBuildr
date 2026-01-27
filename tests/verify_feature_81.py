#!/usr/bin/env python3
"""
Feature #81 Verification Script: ARIA Labels for Dynamic Components
====================================================================

This script verifies all 6 feature steps for Feature #81:
1. Add role=button to clickable cards
2. Add aria-label with spec name and status
3. Add aria-live=polite to status updates
4. Add aria-describedby for progress bar
5. Label inspector close button
6. Add aria-expanded for expandable events

Each step is verified by checking the source code for required ARIA attributes.
"""

import sys
from pathlib import Path


UI_COMPONENTS_PATH = Path(__file__).parent.parent / "ui" / "src" / "components"


def check_step(step_num: int, description: str, checks: list[tuple[str, str, str]]) -> bool:
    """
    Check a step with multiple file/pattern checks.

    Args:
        step_num: Step number (1-6)
        description: Human-readable step description
        checks: List of (component_name, pattern, explanation) tuples

    Returns:
        True if all checks pass, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print('='*60)

    all_passed = True
    for component_name, pattern, explanation in checks:
        component_path = UI_COMPONENTS_PATH / component_name
        if not component_path.exists():
            print(f"  ❌ FAIL: {component_name} not found")
            all_passed = False
            continue

        content = component_path.read_text()
        if pattern in content:
            print(f"  ✅ PASS: {explanation}")
        else:
            print(f"  ❌ FAIL: {explanation}")
            print(f"           Expected pattern: {pattern}")
            all_passed = False

    return all_passed


def main():
    """Run all verification steps."""
    print("\n" + "="*60)
    print("Feature #81: ARIA Labels for Dynamic Components")
    print("="*60)
    print("\nVerifying all 6 feature steps...")

    results = []

    # Step 1: Add role=button to clickable cards
    results.append(check_step(
        1,
        "Add role=button to clickable cards",
        [
            ("DynamicAgentCard.tsx", 'role="gridcell"', "DynamicAgentCard has role='gridcell' (used in grid context)"),
            ("EventTimeline.tsx", 'role="button"', "EventCard has role='button'"),
            ("ArtifactList.tsx", "role={onClick ? 'button' : undefined}", "ArtifactCard conditionally has role='button'"),
        ]
    ))

    # Step 2: Add aria-label with spec name and status
    results.append(check_step(
        2,
        "Add aria-label with spec name and status",
        [
            ("DynamicAgentCard.tsx", 'aria-label={`${spec.display_name} - ${getStatusLabel(status)}`}',
             "DynamicAgentCard has aria-label with spec name and status"),
            ("DynamicAgentCard.tsx", 'aria-label={`Agent status:',
             "StatusBadge has aria-label with status"),
        ]
    ))

    # Step 3: Add aria-live=polite to status updates
    results.append(check_step(
        3,
        "Add aria-live=polite to status updates",
        [
            ("DynamicAgentCard.tsx", 'aria-live="polite"', "StatusBadge has aria-live='polite'"),
            ("DynamicAgentCard.tsx", 'role="status"', "StatusBadge has role='status'"),
        ]
    ))

    # Step 4: Add aria-describedby for progress bar
    results.append(check_step(
        4,
        "Add aria-describedby for progress bar",
        [
            ("TurnsProgressBar.tsx", "aria-describedby=", "Progress bar has aria-describedby"),
            ("TurnsProgressBar.tsx", "descriptionId", "Uses unique ID for description"),
            ("TurnsProgressBar.tsx", "useId", "Uses useId hook for unique IDs"),
        ]
    ))

    # Step 5: Label inspector close button
    results.append(check_step(
        5,
        "Label inspector close button",
        [
            ("RunInspector.tsx", 'aria-label="Close inspector', "Close button has aria-label"),
            ("ArtifactList.tsx", 'aria-label="Close preview modal"', "Preview modal close button has aria-label"),
        ]
    ))

    # Step 6: Add aria-expanded for expandable events
    results.append(check_step(
        6,
        "Add aria-expanded for expandable events",
        [
            ("EventTimeline.tsx", "aria-expanded={isExpanded}", "EventCard has aria-expanded"),
            ("EventTimeline.tsx", 'aria-haspopup="listbox"', "Filter dropdown has aria-haspopup"),
            ("EventTimeline.tsx", "aria-expanded={isOpen}", "Filter dropdown has aria-expanded"),
        ]
    ))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(1 for r in results if r)
    total = len(results)

    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  Step {i}: {status}")

    print(f"\n  Total: {passed}/{total} steps passed")

    if passed == total:
        print("\n✅ Feature #81: ARIA Labels for Dynamic Components - VERIFIED")
        return 0
    else:
        print(f"\n❌ Feature #81: {total - passed} step(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
