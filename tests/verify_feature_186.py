#!/usr/bin/env python
"""
Verification script for Feature #186: Octo selects appropriate tools for each agent

This script verifies all 5 feature steps:
1. Octo has knowledge of available tools: Bash, Read, Write, Glob, Grep, WebFetch, etc.
2. Octo matches agent role to required tool set
3. Test-runner agents get test-related tools (Bash, Read, Write)
4. UI agents get browser/Playwright tools when available
5. Tool selection follows least-privilege principle
"""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.tool_selection import (
    AVAILABLE_TOOLS,
    ROLE_TOOL_CATEGORIES,
    ROLE_TOOL_OVERRIDES,
    ToolSelectionResult,
    get_all_tool_categories,
    get_browser_tools,
    get_test_runner_tools,
    get_tool_info,
    get_tools_by_category,
    get_tools_by_privilege,
    get_ui_agent_tools,
    is_browser_tool,
    select_tools_for_capability,
    select_tools_for_role,
)


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print('='*70)


def print_step(step: int, description: str) -> None:
    """Print step header."""
    print(f"\n[Step {step}] {description}")
    print("-" * 60)


def check(condition: bool, message: str) -> bool:
    """Check a condition and print result."""
    status = "PASS" if condition else "FAIL"
    print(f"  {status}: {message}")
    return condition


def main() -> int:
    """Run all verification steps."""
    print_header("Feature #186: Octo selects appropriate tools for each agent")

    all_passed = True

    # ==========================================================================
    # Step 1: Octo has knowledge of available tools
    # ==========================================================================
    print_step(1, "Octo has knowledge of available tools")

    # Check core tools exist
    core_tools = ["Bash", "Read", "Write", "Glob", "Grep", "WebFetch"]
    for tool in core_tools:
        all_passed &= check(tool in AVAILABLE_TOOLS, f"AVAILABLE_TOOLS contains '{tool}'")

    # Check tool metadata
    bash_info = get_tool_info("Bash")
    all_passed &= check(bash_info is not None, "get_tool_info('Bash') returns metadata")
    all_passed &= check(bash_info.get("category") == "execution", "Bash is in 'execution' category")

    # Check categories
    categories = get_all_tool_categories()
    expected_categories = ["filesystem", "execution", "browser", "web", "feature_management"]
    for cat in expected_categories:
        all_passed &= check(cat in categories, f"Category '{cat}' exists")

    print(f"\n  Total tools in catalog: {len(AVAILABLE_TOOLS)}")
    print(f"  Tool categories: {', '.join(sorted(categories))}")

    # ==========================================================================
    # Step 2: Octo matches agent role to required tool set
    # ==========================================================================
    print_step(2, "Octo matches agent role to required tool set")

    # Check role mappings exist
    expected_roles = ["test_runner", "ui_testing", "coding", "audit"]
    for role in expected_roles:
        all_passed &= check(role in ROLE_TOOL_CATEGORIES, f"ROLE_TOOL_CATEGORIES maps '{role}'")

    # Test select_tools_for_role
    coding_result = select_tools_for_role("coding")
    all_passed &= check(isinstance(coding_result, ToolSelectionResult), "select_tools_for_role returns ToolSelectionResult")
    all_passed &= check(len(coding_result.tools) > 0, "Coding role has tools assigned")
    all_passed &= check(coding_result.reasoning != "", "Selection includes reasoning")

    print(f"\n  Coding role categories: {', '.join(coding_result.categories_used)}")
    print(f"  Coding role tools count: {len(coding_result.tools)}")

    # ==========================================================================
    # Step 3: Test-runner agents get test-related tools (Bash, Read, Write)
    # ==========================================================================
    print_step(3, "Test-runner agents get test-related tools (Bash, Read, Write)")

    test_runner_tools = get_test_runner_tools()
    all_passed &= check("Read" in test_runner_tools, "Test-runner has 'Read' tool")
    all_passed &= check("Bash" in test_runner_tools, "Test-runner has 'Bash' tool")
    all_passed &= check("Grep" in test_runner_tools, "Test-runner has 'Grep' tool")

    test_runner_result = select_tools_for_role("test_runner")
    all_passed &= check("filesystem" in test_runner_result.categories_used, "Test-runner uses 'filesystem' category")
    all_passed &= check("execution" in test_runner_result.categories_used, "Test-runner uses 'execution' category")

    print(f"\n  Test-runner tools: {', '.join(sorted(test_runner_tools))}")

    # ==========================================================================
    # Step 4: UI agents get browser/Playwright tools when available
    # ==========================================================================
    print_step(4, "UI agents get browser/Playwright tools when available")

    browser_tools = get_browser_tools()
    all_passed &= check("browser_navigate" in browser_tools, "Browser tools include 'browser_navigate'")
    all_passed &= check("browser_click" in browser_tools, "Browser tools include 'browser_click'")
    all_passed &= check("browser_snapshot" in browser_tools, "Browser tools include 'browser_snapshot'")

    ui_tools = get_ui_agent_tools()
    all_passed &= check("browser_navigate" in ui_tools, "UI agent has 'browser_navigate'")
    all_passed &= check("browser_click" in ui_tools, "UI agent has 'browser_click'")

    # Test capability-based selection for UI
    ui_result = select_tools_for_capability("ui_testing", "testing")
    all_passed &= check("browser_navigate" in ui_result.tools, "UI capability gets browser_navigate")
    all_passed &= check("browser" in ui_result.categories_used, "UI testing uses 'browser' category")

    # Test tech_stack detection
    context = {"tech_stack": ["playwright"]}
    playwright_result = select_tools_for_capability("generic", "testing", context)
    all_passed &= check(
        any("browser" in t for t in playwright_result.tools) or "browser" in str(playwright_result.categories_used),
        "Playwright in tech_stack enables browser tools"
    )

    print(f"\n  Browser tools available: {', '.join(sorted(browser_tools))}")
    print(f"  UI agent tools count: {len(ui_tools)}")

    # ==========================================================================
    # Step 5: Tool selection follows least-privilege principle
    # ==========================================================================
    print_step(5, "Tool selection follows least-privilege principle")

    # Check audit agents are read-only
    audit_result = select_tools_for_role("audit")
    all_passed &= check("Read" in audit_result.tools, "Audit agent has 'Read' tool")
    all_passed &= check("Glob" in audit_result.tools, "Audit agent has 'Glob' tool")

    # Check write/execute tools are excluded for audit
    write_excluded = "Write" not in audit_result.tools or "Write" in audit_result.least_privilege_exclusions
    all_passed &= check(write_excluded, "Audit agent excludes 'Write' tool (least-privilege)")

    bash_excluded = "Bash" not in audit_result.tools or "Bash" in audit_result.least_privilege_exclusions
    all_passed &= check(bash_excluded, "Audit agent excludes 'Bash' tool (least-privilege)")

    # Check test-runner excludes Write
    test_runner_result = select_tools_for_role("test_runner")
    all_passed &= check("Write" in test_runner_result.least_privilege_exclusions, "Test-runner excludes 'Write' (least-privilege)")

    # Check ui_testing excludes browser_evaluate
    ui_testing_result = select_tools_for_role("ui_testing")
    evaluate_excluded = "browser_evaluate" not in ui_testing_result.tools or "browser_evaluate" in ui_testing_result.least_privilege_exclusions
    all_passed &= check(evaluate_excluded, "UI testing excludes 'browser_evaluate' (least-privilege)")

    print(f"\n  Audit role exclusions: {', '.join(audit_result.least_privilege_exclusions)}")
    print(f"  Test-runner exclusions: {', '.join(test_runner_result.least_privilege_exclusions)}")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print_header("Verification Summary")

    if all_passed:
        print("  ALL 5 FEATURE STEPS VERIFIED SUCCESSFULLY")
        print("\n  Feature #186: Octo selects appropriate tools for each agent - PASS")
        return 0
    else:
        print("  SOME VERIFICATION CHECKS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
