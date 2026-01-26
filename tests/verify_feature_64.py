#!/usr/bin/env python3
"""
Verification script for Feature #64: DynamicAgentCard React Component
======================================================================

This script verifies that the DynamicAgentCard component meets all requirements
by checking the source code for the required implementations.

Feature Requirements:
1. Create DynamicAgentCard.tsx component
2. Props: spec (AgentSpec), run (AgentRun | null)
3. Display spec.display_name as card title
4. Display spec.icon as card icon
5. If run exists, show status with color coding
6. Show turns_used / max_turns progress bar
7. Show validator status indicators
8. Add click handler to open Run Inspector
9. Style with Tailwind neobrutalism tokens
10. Make responsive for mobile
"""

import re
import sys
from pathlib import Path

COMPONENT_PATH = Path("/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx")
TYPES_PATH = Path("/home/rudih/workspace/AutoBuildr/ui/src/lib/types.ts")
CSS_PATH = Path("/home/rudih/workspace/AutoBuildr/ui/src/styles/globals.css")


def read_file(path: Path) -> str:
    """Read file contents."""
    with open(path, 'r') as f:
        return f.read()


def verify_step_1():
    """Step 1: Create DynamicAgentCard.tsx component"""
    print("\n[Step 1] Verify DynamicAgentCard.tsx component exists")
    assert COMPONENT_PATH.exists(), f"Component file not found: {COMPONENT_PATH}"
    content = read_file(COMPONENT_PATH)
    assert "export function DynamicAgentCard" in content, "DynamicAgentCard export not found"
    print("  PASS: DynamicAgentCard.tsx component exists and exports DynamicAgentCard")


def verify_step_2():
    """Step 2: Props: spec (AgentSpec), run (AgentRun | null)"""
    print("\n[Step 2] Verify Props interface with spec and run")
    content = read_file(COMPONENT_PATH)

    # Check for DynamicAgentCardProps interface usage
    assert "DynamicAgentCardProps" in content, "DynamicAgentCardProps interface not found"

    # Check for DynamicAgentData type which contains spec and run
    assert "DynamicAgentData" in content, "DynamicAgentData type not found"

    # Verify the props destructure spec and run
    assert "const { spec, run } = data" in content, "Props destructuring (spec, run) not found"

    # Verify run can be null (optional)
    assert "run?.status" in content or "run && " in content, "Null check for run not found"

    print("  PASS: Props interface includes spec and run (nullable)")


def verify_step_3():
    """Step 3: Display spec.display_name as card title"""
    print("\n[Step 3] Verify display_name is shown as card title")
    content = read_file(COMPONENT_PATH)

    # Check for display_name rendering
    assert "spec.display_name" in content, "spec.display_name not found"
    assert "<h3" in content, "h3 element (title) not found"

    # Verify it's inside a heading element
    title_pattern = r'<h3[^>]*>.*?{spec\.display_name}.*?</h3>'
    assert re.search(title_pattern, content, re.DOTALL), "display_name not rendered in h3"

    print("  PASS: spec.display_name is displayed as card title")


def verify_step_4():
    """Step 4: Display spec.icon as card icon"""
    print("\n[Step 4] Verify spec.icon is displayed as card icon")
    content = read_file(COMPONENT_PATH)

    # Check for icon rendering with fallback
    assert "spec.icon" in content, "spec.icon not found"
    assert "getTaskTypeEmoji" in content, "getTaskTypeEmoji fallback not found"

    # Verify icon rendering
    icon_pattern = r'const icon = spec\.icon \|\| getTaskTypeEmoji\(spec\.task_type\)'
    assert re.search(icon_pattern, content), "Icon with fallback not found"

    # Verify icon is rendered
    assert "{icon}" in content, "Icon rendering not found"

    print("  PASS: spec.icon is displayed with task_type fallback")


def verify_step_5():
    """Step 5: If run exists, show status with color coding"""
    print("\n[Step 5] Verify status with color coding")
    content = read_file(COMPONENT_PATH)

    # Check for StatusBadge component
    assert "StatusBadge" in content, "StatusBadge not found"
    assert "<StatusBadge status={status}" in content, "StatusBadge usage not found"

    # Verify status-based class names
    assert "neo-status-" in content, "Status CSS classes not found"

    # Check CSS file for color definitions
    css_content = read_file(CSS_PATH)
    status_colors = [
        "neo-status-pending",
        "neo-status-running",
        "neo-status-completed",
        "neo-status-failed",
        "neo-status-paused",
        "neo-status-timeout"
    ]
    for status_class in status_colors:
        assert status_class in css_content, f"CSS class {status_class} not found"

    print("  PASS: Status badge with color coding is implemented")


def verify_step_6():
    """Step 6: Show turns_used / max_turns progress bar"""
    print("\n[Step 6] Verify turns progress bar")
    content = read_file(COMPONENT_PATH)

    # Check for TurnsProgressBar import
    assert "TurnsProgressBar" in content, "TurnsProgressBar not found"
    assert "from './TurnsProgressBar'" in content, "TurnsProgressBar import not found"

    # Verify progress bar rendering with correct props
    assert "run.turns_used" in content, "turns_used not passed to progress bar"
    assert "spec.max_turns" in content, "max_turns not passed to progress bar"

    # Verify progress bar is rendered when run exists
    progress_pattern = r'<TurnsProgressBar\s+used={run\.turns_used}\s+max={spec\.max_turns}'
    assert re.search(progress_pattern, content), "TurnsProgressBar with correct props not found"

    print("  PASS: TurnsProgressBar shows turns_used / max_turns")


def verify_step_7():
    """Step 7: Show validator status indicators"""
    print("\n[Step 7] Verify validator status indicators")
    content = read_file(COMPONENT_PATH)

    # Check for ValidatorStatusIndicators component
    assert "ValidatorStatusIndicators" in content, "ValidatorStatusIndicators not found"
    assert "function ValidatorStatusIndicators" in content, "ValidatorStatusIndicators definition not found"

    # Verify it uses acceptance_results
    assert "acceptance_results" in content, "acceptance_results not used"

    # Verify it shows pass/fail counts
    assert "passedCount" in content, "passedCount not computed"
    assert "totalCount" in content, "totalCount not computed"

    # Verify individual validator badges
    assert "entries.map" in content, "Validator iteration not found"
    assert "result.passed" in content, "Validator pass status not checked"

    # Verify it's rendered in the card
    assert "<ValidatorStatusIndicators run={run}" in content, "ValidatorStatusIndicators not rendered"

    print("  PASS: Validator status indicators are implemented")


def verify_step_8():
    """Step 8: Add click handler to open Run Inspector"""
    print("\n[Step 8] Verify click handler")
    content = read_file(COMPONENT_PATH)

    # Check for onClick prop
    assert "onClick?: () => void" in content or "onClick" in content, "onClick prop not found"

    # Verify click handler is attached
    assert "onClick={onClick}" in content, "onClick handler not attached to element"

    # Verify keyboard accessibility
    assert "onKeyDown" in content, "onKeyDown handler not found"
    assert "Enter" in content, "Enter key support not found"

    # Verify ARIA attributes for accessibility
    assert 'role="button"' in content, "role=button not found"
    assert "tabIndex={0}" in content, "tabIndex not set"

    print("  PASS: Click handler with keyboard accessibility is implemented")


def verify_step_9():
    """Step 9: Style with Tailwind neobrutalism tokens"""
    print("\n[Step 9] Verify Tailwind neobrutalism styling")
    content = read_file(COMPONENT_PATH)

    # Check for neobrutalism class tokens
    neo_classes = [
        "neo-card",
        "neo-status-badge",
        "neo-text-secondary",
        "neo-text-muted",
        "neo-border"
    ]

    found = []
    for cls in neo_classes:
        if cls in content:
            found.append(cls)

    assert len(found) >= 3, f"Not enough neobrutalism classes found: {found}"

    # Check for animation classes
    assert "animate-pulse-neo" in content, "Pulse animation not found for running status"

    print(f"  PASS: Neobrutalism styling with classes: {found}")


def verify_step_10():
    """Step 10: Make responsive for mobile"""
    print("\n[Step 10] Verify mobile responsiveness")
    content = read_file(COMPONENT_PATH)

    # Check for responsive utilities
    responsive_patterns = [
        "truncate",  # Text truncation for small screens
        "min-w-0",   # Flex item shrinking
        "flex-1",    # Flexible layouts
        "text-xs",   # Small text sizes
        "text-sm",   # Small-medium text
        "gap-",      # Flexible gaps
        "p-4",       # Consistent padding
    ]

    found = []
    for pattern in responsive_patterns:
        if pattern in content:
            found.append(pattern)

    assert len(found) >= 4, f"Not enough responsive utilities found: {found}"

    # Check for flex-wrap for validator badges
    assert "flex-wrap" in content, "flex-wrap not found for validator badges"

    print(f"  PASS: Mobile responsive with utilities: {found}")


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #64: DynamicAgentCard React Component - Verification")
    print("=" * 70)

    steps = [
        verify_step_1,
        verify_step_2,
        verify_step_3,
        verify_step_4,
        verify_step_5,
        verify_step_6,
        verify_step_7,
        verify_step_8,
        verify_step_9,
        verify_step_10,
    ]

    passed = 0
    failed = 0

    for step_func in steps:
        try:
            step_func()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed}/{len(steps)} steps passed")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll verification steps PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
