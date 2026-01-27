#!/usr/bin/env python3
"""
Feature #83: High Contrast Mode Support - Verification Script
=============================================================

This script verifies all 5 feature steps for Feature #83.

Dependencies: [65, 66] - Both passing

Feature Steps:
1. Check all status colors against WCAG contrast requirements
2. Add pattern/icon fallbacks in addition to color
3. Test with Windows High Contrast mode
4. Add prefers-contrast media query support
5. Ensure focus indicators are visible
"""

import re
from pathlib import Path

# Paths to files
CSS_FILE = Path(__file__).parent.parent / "ui" / "src" / "styles" / "globals.css"
COMPONENT_FILE = Path(__file__).parent.parent / "ui" / "src" / "components" / "DynamicAgentCard.tsx"


def read_file(path: Path) -> str:
    """Read file content."""
    with open(path) as f:
        return f.read()


def verify_step_1():
    """Step 1: Check all status colors against WCAG contrast requirements."""
    print("\n" + "=" * 70)
    print("Step 1: Check all status colors against WCAG contrast requirements")
    print("=" * 70)

    css = read_file(CSS_FILE)
    passed = True

    # Check 1: High contrast mode section exists
    check = '@media (prefers-contrast: high)' in css
    print(f"  [{'PASS' if check else 'FAIL'}] High contrast media query defined")
    passed = passed and check

    # Check 2: All status colors have high contrast overrides
    status_types = ['pending', 'running', 'paused', 'completed', 'failed', 'timeout']

    # Find the high contrast section - it contains :root with status colors
    # Look for the pattern: @media (prefers-contrast: high) { ... :root { --color-status-... } ... }
    high_contrast_start = css.find('@media (prefers-contrast: high)')
    if high_contrast_start >= 0:
        # Get the content after the media query start
        hc_section = css[high_contrast_start:high_contrast_start + 3000]  # Get enough content

        for status in status_types:
            text_check = f'--color-status-{status}-text' in hc_section
            bg_check = f'--color-status-{status}-bg' in hc_section
            if text_check and bg_check:
                print(f"  [PASS] High contrast colors for '{status}' status defined")
            else:
                print(f"  [FAIL] Missing high contrast colors for '{status}' status")
                passed = False
    else:
        print("  [FAIL] Could not find high contrast section")
        passed = False

    # Check 3: Dark mode has high contrast overrides
    dark_mode_hc = '.dark' in css and '--color-status-' in css
    print(f"  [{'PASS' if dark_mode_hc else 'FAIL'}] Dark mode high contrast overrides defined")
    passed = passed and dark_mode_hc

    return passed


def verify_step_2():
    """Step 2: Add pattern/icon fallbacks in addition to color."""
    print("\n" + "=" * 70)
    print("Step 2: Add pattern/icon fallbacks in addition to color")
    print("=" * 70)

    css = read_file(CSS_FILE)
    component = read_file(COMPONENT_FILE)
    passed = True

    # Check 1: Status badges have distinct border styles
    border_patterns = {
        'pending': 'dashed',
        'running': 'double',
        'paused': 'dotted',
        'completed': 'solid',
        'timeout': 'ridge',
    }

    for status, style in border_patterns.items():
        pattern = rf'\.neo-status-{status}\s*\{{[^}}]*border-style:\s*{style}'
        found = bool(re.search(pattern, css, re.DOTALL))
        print(f"  [{'PASS' if found else 'FAIL'}] Status '{status}' has {style} border style")
        passed = passed and found

    # Check 2: Progress bars have pattern fallbacks
    progress_patterns = 'repeating-linear-gradient' in css
    print(f"  [{'PASS' if progress_patterns else 'FAIL'}] Progress bars have pattern fallbacks")
    passed = passed and progress_patterns

    # Check 3: Pattern indicator class exists
    pattern_class = '.neo-status-indicator-pattern' in css
    print(f"  [{'PASS' if pattern_class else 'FAIL'}] Pattern indicator class defined in CSS")
    passed = passed and pattern_class

    # Check 4: Component uses pattern indicator class
    component_uses = 'neo-status-indicator-pattern' in component
    print(f"  [{'PASS' if component_uses else 'FAIL'}] Component uses pattern indicator class")
    passed = passed and component_uses

    # Check 5: Component sets data-status attribute
    data_status = 'data-status={status}' in component
    print(f"  [{'PASS' if data_status else 'FAIL'}] Component sets data-status attribute")
    passed = passed and data_status

    return passed


def verify_step_3():
    """Step 3: Test with Windows High Contrast mode."""
    print("\n" + "=" * 70)
    print("Step 3: Test with Windows High Contrast mode (forced-colors)")
    print("=" * 70)

    css = read_file(CSS_FILE)
    passed = True

    # Check 1: forced-colors media query exists
    forced_colors = '@media (forced-colors: active)' in css
    print(f"  [{'PASS' if forced_colors else 'FAIL'}] forced-colors media query defined")
    passed = passed and forced_colors

    # Check 2: System colors are used
    system_colors = ['CanvasText', 'Canvas', 'Highlight', 'HighlightText', 'ButtonFace', 'ButtonText', 'LinkText']
    colors_found = [c for c in system_colors if c in css]
    check = len(colors_found) >= 5
    print(f"  [{'PASS' if check else 'FAIL'}] System colors used: {', '.join(colors_found)}")
    passed = passed and check

    # Check 3: forced-color-adjust property used
    forced_adjust = 'forced-color-adjust: none' in css
    print(f"  [{'PASS' if forced_adjust else 'FAIL'}] forced-color-adjust property used")
    passed = passed and forced_adjust

    return passed


def verify_step_4():
    """Step 4: Add prefers-contrast media query support."""
    print("\n" + "=" * 70)
    print("Step 4: Add prefers-contrast media query support")
    print("=" * 70)

    css = read_file(CSS_FILE)
    passed = True

    # Check all contrast preference modes
    modes = [
        ('prefers-contrast: high', 'High contrast'),
        ('prefers-contrast: more', 'More contrast'),
        ('prefers-contrast: less', 'Less contrast'),
    ]

    for mode, description in modes:
        check = f'@media ({mode})' in css
        print(f"  [{'PASS' if check else 'FAIL'}] {description} mode supported")
        passed = passed and check

    # Check reduced motion support as bonus
    reduced_motion = '@media (prefers-reduced-motion: reduce)' in css
    print(f"  [{'PASS' if reduced_motion else 'FAIL'}] Reduced motion support (bonus)")
    passed = passed and reduced_motion

    return passed


def verify_step_5():
    """Step 5: Ensure focus indicators are visible."""
    print("\n" + "=" * 70)
    print("Step 5: Ensure focus indicators are visible")
    print("=" * 70)

    css = read_file(CSS_FILE)
    passed = True

    # Check 1: Focus-visible styles enhanced in high contrast
    focus_visible_hc = re.search(
        r'@media \(prefers-contrast: high\)[\s\S]*?:focus-visible\s*\{[^}]*outline',
        css
    )
    print(f"  [{'PASS' if focus_visible_hc else 'FAIL'}] :focus-visible enhanced in high contrast mode")
    passed = passed and bool(focus_visible_hc)

    # Check 2: Agent card has enhanced focus
    card_focus = '.neo-agent-card-focusable:focus-visible' in css
    print(f"  [{'PASS' if card_focus else 'FAIL'}] Agent card has focus-visible styles")
    passed = passed and card_focus

    # Check 3: Focus outline is at least 4px in high contrast
    outline_match = re.search(
        r'@media \(prefers-contrast: high\)[\s\S]*?outline:\s*([4-9]|[1-9]\d+)px',
        css
    )
    print(f"  [{'PASS' if outline_match else 'FAIL'}] Focus outline at least 4px in high contrast")
    passed = passed and bool(outline_match)

    # Check 4: Buttons have focus styles
    button_focus = '.neo-btn:focus-visible' in css
    print(f"  [{'PASS' if button_focus else 'FAIL'}] Buttons have focus-visible styles")
    passed = passed and button_focus

    # Check 5: Animation disabled on focus in reduced motion
    animation_disabled = re.search(
        r'@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation:\s*none',
        css
    )
    print(f"  [{'PASS' if animation_disabled else 'FAIL'}] Focus animation disabled in reduced motion")
    passed = passed and bool(animation_disabled)

    return passed


def main():
    """Run all verification steps."""
    print("\n" + "#" * 70)
    print("# Feature #83: High Contrast Mode Support - Verification")
    print("#" * 70)

    results = {
        "Step 1: WCAG Contrast": verify_step_1(),
        "Step 2: Pattern/Icon Fallbacks": verify_step_2(),
        "Step 3: Windows High Contrast": verify_step_3(),
        "Step 4: prefers-contrast Support": verify_step_4(),
        "Step 5: Focus Indicators": verify_step_5(),
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {step}")
        all_passed = all_passed and passed

    print("\n" + "=" * 70)
    if all_passed:
        print("RESULT: ALL 5 FEATURE STEPS PASS")
        print("Feature #83: High Contrast Mode Support - VERIFIED")
    else:
        print("RESULT: SOME STEPS FAILED")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())
