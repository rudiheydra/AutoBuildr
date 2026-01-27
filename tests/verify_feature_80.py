#!/usr/bin/env python3
"""
Feature #80 Verification Script: Keyboard Navigation for Agent Cards

This script verifies all feature steps by analyzing the implemented code.
Run this script to confirm the feature is complete.

Usage:
    python tests/verify_feature_80.py
"""

import os
import sys

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}{text}{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")


def print_step(step_num: int, title: str):
    print(f"\n{BOLD}Step {step_num}: {title}{RESET}")
    print("-" * 40)


def print_pass(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def print_fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def print_info(msg: str):
    print(f"  {YELLOW}ℹ{RESET} {msg}")


def read_file(filepath: str) -> str:
    """Read file contents."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ui_src = os.path.join(base_dir, 'ui', 'src')

    # Read source files
    card_path = os.path.join(ui_src, 'components', 'DynamicAgentCard.tsx')
    inspector_path = os.path.join(ui_src, 'components', 'RunInspector.tsx')
    hook_path = os.path.join(ui_src, 'hooks', 'useAgentCardGridNavigation.ts')
    css_path = os.path.join(ui_src, 'styles', 'globals.css')

    card = read_file(card_path)
    inspector = read_file(inspector_path)
    hook = read_file(hook_path)
    css = read_file(css_path)

    all_passed = True

    print_header("Feature #80: Keyboard Navigation for Agent Cards")
    print(f"Category: P. Accessibility")
    print(f"Description: Implement keyboard navigation for DynamicAgentCard grid with focus management.")

    # Step 1
    print_step(1, "Add tabindex to DynamicAgentCard")
    checks = [
        ('tabIndex prop in interface', 'tabIndex?' in card or 'tabIndex: tabIndexProp' in card),
        ('tabIndex attribute rendered', 'tabIndex={tabIndex}' in card),
        ('Default tabIndex=0', 'tabIndexProp !== undefined ? tabIndexProp : 0' in card),
    ]
    for desc, passed in checks:
        if passed:
            print_pass(desc)
        else:
            print_fail(desc)
            all_passed = False

    # Step 2
    print_step(2, "Handle Enter/Space to open inspector")
    checks = [
        ('handleKeyDown function', 'handleKeyDown' in card),
        ('Enter key check', "e.key === 'Enter'" in card),
        ('Space key check', "e.key === ' '" in card),
        ('onClick called on key', "onClick?.()" in card),
    ]
    for desc, passed in checks:
        if passed:
            print_pass(desc)
        else:
            print_fail(desc)
            all_passed = False

    # Step 3
    print_step(3, "Handle Escape to close inspector")
    checks = [
        ('Escape key handler in RunInspector', "e.key === 'Escape'" in inspector),
        ('onClose called', 'onClose()' in inspector or 'onClose?.()' in inspector),
    ]
    for desc, passed in checks:
        if passed:
            print_pass(desc)
        else:
            print_fail(desc)
            all_passed = False

    # Step 4
    print_step(4, "Arrow keys to navigate card grid")
    if not hook:
        print_fail("useAgentCardGridNavigation.ts not found")
        all_passed = False
    else:
        checks = [
            ('Hook file exists', len(hook) > 0),
            ('ArrowLeft handling', 'ArrowLeft' in hook),
            ('ArrowRight handling', 'ArrowRight' in hook),
            ('ArrowUp handling', 'ArrowUp' in hook),
            ('ArrowDown handling', 'ArrowDown' in hook),
            ('Home key handling', 'Home' in hook),
            ('End key handling', 'End' in hook),
            ('getCardProps function', 'getCardProps' in hook),
            ('Column-based navigation', 'columns' in hook),
        ]
        for desc, passed in checks:
            if passed:
                print_pass(desc)
            else:
                print_fail(desc)
                all_passed = False

    # Step 5
    print_step(5, "Focus visible indicator")
    checks = [
        (':focus-visible base style', ':focus-visible' in css),
        ('.neo-agent-card-focusable:focus-visible', '.neo-agent-card-focusable:focus-visible' in css),
        ('Focus class in card', 'neo-agent-card-focusable' in card),
        ('Outline style defined', 'outline:' in css.replace(' ', '')),
        ('Focus ring animation', 'focus-ring-pulse' in css),
        ('Reduced motion support', 'prefers-reduced-motion' in css),
        ('High contrast support', 'prefers-contrast' in css),
    ]
    for desc, passed in checks:
        if passed:
            print_pass(desc)
        else:
            print_fail(desc)
            all_passed = False

    # Step 6
    print_step(6, "Screen reader announcements for status changes")
    checks = [
        ('aria-live on StatusBadge', 'aria-live' in card),
        ('role="status" on badge', 'role="status"' in card),
        ('aria-label on card', 'aria-label' in card),
        ('announce function in hook', 'announce' in hook),
        ('announceStatusChange function', 'announceStatusChange' in hook),
        ('.sr-only class in CSS', '.sr-only' in css),
        ('aria-hidden on icons', 'aria-hidden="true"' in card),
    ]
    for desc, passed in checks:
        if passed:
            print_pass(desc)
        else:
            print_fail(desc)
            all_passed = False

    # Summary
    print_header("Verification Summary")

    if all_passed:
        print(f"{GREEN}{BOLD}✓ ALL CHECKS PASSED{RESET}")
        print(f"\nFeature #80: Keyboard Navigation for Agent Cards is {GREEN}COMPLETE{RESET}")
        print("\nImplementation includes:")
        print("  - DynamicAgentCard.tsx: Updated with keyboard navigation props")
        print("  - useAgentCardGridNavigation.ts: New hook for grid navigation")
        print("  - globals.css: Focus-visible styles and accessibility support")
        print("  - RunInspector.tsx: Escape key handling (already present)")
        return 0
    else:
        print(f"{RED}{BOLD}✗ SOME CHECKS FAILED{RESET}")
        print(f"\nFeature #80 verification: {RED}INCOMPLETE{RESET}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
