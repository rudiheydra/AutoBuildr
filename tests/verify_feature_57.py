#!/usr/bin/env python3
"""
Verification script for Feature #57: Tool Policy Derivation from Task Type

This script verifies all 8 steps from the feature description:
1. Define tool sets for each task_type
2. coding: file edit, bash (restricted), feature tools
3. testing: file read, bash (test commands), feature tools
4. documentation: file write, read-only access
5. audit: read-only everything
6. Add standard forbidden_patterns for all types
7. Add task-specific forbidden_patterns
8. Return complete tool_policy structure

Run this script to confirm the feature is correctly implemented.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.tool_policy import (
    STANDARD_FORBIDDEN_PATTERNS,
    TASK_SPECIFIC_FORBIDDEN_PATTERNS,
    TASK_TOOL_HINTS,
    TOOL_SETS,
    derive_tool_policy,
    get_combined_forbidden_patterns,
    get_standard_forbidden_patterns,
    get_supported_task_types,
    get_task_forbidden_patterns,
    get_tool_hints,
    get_tool_set,
)


def print_result(step: str, passed: bool, message: str = ""):
    """Print verification result."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {step}")
    if message and not passed:
        print(f"         {message}")


def verify_step_1():
    """Step 1: Define tool sets for each task_type"""
    print("\n=== Step 1: Define tool sets for each task_type ===")
    all_passed = True

    # Verify TOOL_SETS exists and has expected types
    print_result("TOOL_SETS is a dict", isinstance(TOOL_SETS, dict))
    all_passed &= isinstance(TOOL_SETS, dict)

    expected_types = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]
    for task_type in expected_types:
        passed = task_type in TOOL_SETS
        print_result(f"'{task_type}' task_type has tool set", passed)
        all_passed &= passed

    # Verify get_supported_task_types
    supported = get_supported_task_types()
    passed = all(t in supported for t in expected_types)
    print_result("get_supported_task_types() returns all types", passed)
    all_passed &= passed

    return all_passed


def verify_step_2():
    """Step 2: coding: file edit, bash (restricted), feature tools"""
    print("\n=== Step 2: coding: file edit, bash (restricted), feature tools ===")
    all_passed = True

    tools = get_tool_set("coding")

    # File edit tools
    file_edit_passed = all(t in tools for t in ["Read", "Write", "Edit", "Glob", "Grep"])
    print_result("coding has file edit tools (Read, Write, Edit, Glob, Grep)", file_edit_passed)
    all_passed &= file_edit_passed

    # Bash tool
    bash_passed = "Bash" in tools
    print_result("coding has Bash tool (restricted)", bash_passed)
    all_passed &= bash_passed

    # Feature tools
    feature_tools = ["feature_get_by_id", "feature_mark_passing", "feature_mark_failing",
                     "feature_mark_in_progress", "feature_skip", "feature_get_stats"]
    feature_passed = all(t in tools for t in feature_tools)
    print_result("coding has feature tools", feature_passed)
    all_passed &= feature_passed

    return all_passed


def verify_step_3():
    """Step 3: testing: file read, bash (test commands), feature tools"""
    print("\n=== Step 3: testing: file read, bash (test commands), feature tools ===")
    all_passed = True

    tools = get_tool_set("testing")

    # File read tools
    file_read_passed = all(t in tools for t in ["Read", "Glob", "Grep"])
    print_result("testing has file read tools (Read, Glob, Grep)", file_read_passed)
    all_passed &= file_read_passed

    # No write/edit
    no_write_passed = "Write" not in tools and "Edit" not in tools
    print_result("testing does NOT have Write/Edit tools", no_write_passed)
    all_passed &= no_write_passed

    # Bash tool
    bash_passed = "Bash" in tools
    print_result("testing has Bash tool (test commands)", bash_passed)
    all_passed &= bash_passed

    # Feature tools
    feature_tools = ["feature_get_by_id", "feature_mark_passing", "feature_mark_failing", "feature_get_stats"]
    feature_passed = all(t in tools for t in feature_tools)
    print_result("testing has feature tools", feature_passed)
    all_passed &= feature_passed

    return all_passed


def verify_step_4():
    """Step 4: documentation: file write, read-only access"""
    print("\n=== Step 4: documentation: file write, read-only access ===")
    all_passed = True

    tools = get_tool_set("documentation")

    # Write tool
    write_passed = "Write" in tools
    print_result("documentation has Write tool", write_passed)
    all_passed &= write_passed

    # Read-only access
    read_passed = all(t in tools for t in ["Read", "Glob", "Grep"])
    print_result("documentation has read tools (Read, Glob, Grep)", read_passed)
    all_passed &= read_passed

    # No Edit (should create new, not modify code)
    no_edit_passed = "Edit" not in tools
    print_result("documentation does NOT have Edit tool", no_edit_passed)
    all_passed &= no_edit_passed

    # No Bash
    no_bash_passed = "Bash" not in tools
    print_result("documentation does NOT have Bash tool", no_bash_passed)
    all_passed &= no_bash_passed

    return all_passed


def verify_step_5():
    """Step 5: audit: read-only everything"""
    print("\n=== Step 5: audit: read-only everything ===")
    all_passed = True

    tools = get_tool_set("audit")

    # Read-only file access
    read_passed = all(t in tools for t in ["Read", "Glob", "Grep"])
    print_result("audit has read-only file tools", read_passed)
    all_passed &= read_passed

    # No Write/Edit
    no_write_passed = "Write" not in tools and "Edit" not in tools
    print_result("audit does NOT have Write/Edit tools", no_write_passed)
    all_passed &= no_write_passed

    # No Bash
    no_bash_passed = "Bash" not in tools
    print_result("audit does NOT have Bash tool", no_bash_passed)
    all_passed &= no_bash_passed

    # Read-only feature tools
    readonly_feature_passed = (
        "feature_get_by_id" in tools and
        "feature_get_stats" in tools and
        "feature_mark_passing" not in tools and
        "feature_mark_failing" not in tools
    )
    print_result("audit has read-only feature tools", readonly_feature_passed)
    all_passed &= readonly_feature_passed

    return all_passed


def verify_step_6():
    """Step 6: Add standard forbidden_patterns for all types"""
    print("\n=== Step 6: Add standard forbidden_patterns for all types ===")
    all_passed = True

    # Standard patterns exist
    patterns_exist = len(STANDARD_FORBIDDEN_PATTERNS) > 0
    print_result("STANDARD_FORBIDDEN_PATTERNS is not empty", patterns_exist)
    all_passed &= patterns_exist

    patterns_str = " ".join(STANDARD_FORBIDDEN_PATTERNS)

    # Check for key security patterns
    has_rm_rf = "rm" in patterns_str and "rf" in patterns_str
    print_result("Standard patterns block rm -rf", has_rm_rf)
    all_passed &= has_rm_rf

    has_drop = "DROP" in patterns_str and "TABLE" in patterns_str
    print_result("Standard patterns block DROP TABLE", has_drop)
    all_passed &= has_drop

    has_sudo = "sudo" in patterns_str
    print_result("Standard patterns block sudo", has_sudo)
    all_passed &= has_sudo

    # Verify all task types include standard patterns
    for task_type in get_supported_task_types():
        policy = derive_tool_policy(task_type)
        standard = get_standard_forbidden_patterns()
        includes_all = all(p in policy["forbidden_patterns"] for p in standard)
        print_result(f"'{task_type}' policy includes all standard patterns", includes_all)
        all_passed &= includes_all

    return all_passed


def verify_step_7():
    """Step 7: Add task-specific forbidden_patterns"""
    print("\n=== Step 7: Add task-specific forbidden_patterns ===")
    all_passed = True

    # Task-specific patterns exist
    dict_exists = isinstance(TASK_SPECIFIC_FORBIDDEN_PATTERNS, dict)
    print_result("TASK_SPECIFIC_FORBIDDEN_PATTERNS is a dict", dict_exists)
    all_passed &= dict_exists

    # Testing has write/edit blocks
    testing_patterns = get_task_forbidden_patterns("testing")
    testing_str = " ".join(testing_patterns)
    testing_blocks_write = "Write" in testing_str and "Edit" in testing_str
    print_result("testing patterns block Write/Edit", testing_blocks_write)
    all_passed &= testing_blocks_write

    # Audit has extensive restrictions
    audit_patterns = get_task_forbidden_patterns("audit")
    audit_very_restrictive = len(audit_patterns) > len(testing_patterns)
    print_result("audit has more restrictions than testing", audit_very_restrictive)
    all_passed &= audit_very_restrictive

    # Combined patterns include both standard and task-specific
    combined = get_combined_forbidden_patterns("testing")
    standard = get_standard_forbidden_patterns()
    specific = get_task_forbidden_patterns("testing")
    includes_both = all(p in combined for p in standard) and all(p in combined for p in specific)
    print_result("get_combined_forbidden_patterns includes standard + task-specific", includes_both)
    all_passed &= includes_both

    return all_passed


def verify_step_8():
    """Step 8: Return complete tool_policy structure"""
    print("\n=== Step 8: Return complete tool_policy structure ===")
    all_passed = True

    policy = derive_tool_policy("coding")

    # Required fields
    has_version = "policy_version" in policy and policy["policy_version"] == "v1"
    print_result("Policy has policy_version='v1'", has_version)
    all_passed &= has_version

    has_tools = "allowed_tools" in policy and isinstance(policy["allowed_tools"], list)
    print_result("Policy has allowed_tools list", has_tools)
    all_passed &= has_tools

    has_patterns = "forbidden_patterns" in policy and isinstance(policy["forbidden_patterns"], list)
    print_result("Policy has forbidden_patterns list", has_patterns)
    all_passed &= has_patterns

    has_hints = "tool_hints" in policy and isinstance(policy["tool_hints"], dict)
    print_result("Policy has tool_hints dict", has_hints)
    all_passed &= has_hints

    has_task_type = "task_type" in policy
    print_result("Policy has task_type for reference", has_task_type)
    all_passed &= has_task_type

    # Optional features work
    policy_with_dirs = derive_tool_policy("coding", allowed_directories=["/tmp"])
    dirs_work = "allowed_directories" in policy_with_dirs
    print_result("Policy supports allowed_directories", dirs_work)
    all_passed &= dirs_work

    policy_with_extra = derive_tool_policy("coding", additional_tools=["custom_tool"])
    extra_tools_work = "custom_tool" in policy_with_extra["allowed_tools"]
    print_result("Policy supports additional_tools", extra_tools_work)
    all_passed &= extra_tools_work

    policy_with_hints = derive_tool_policy("coding", additional_tool_hints={"x": "y"})
    extra_hints_work = "x" in policy_with_hints["tool_hints"]
    print_result("Policy supports additional_tool_hints", extra_hints_work)
    all_passed &= extra_hints_work

    return all_passed


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #57: Tool Policy Derivation from Task Type")
    print("=" * 70)

    results = []

    results.append(("Step 1: Define tool sets for each task_type", verify_step_1()))
    results.append(("Step 2: coding: file edit, bash (restricted), feature tools", verify_step_2()))
    results.append(("Step 3: testing: file read, bash (test commands), feature tools", verify_step_3()))
    results.append(("Step 4: documentation: file write, read-only access", verify_step_4()))
    results.append(("Step 5: audit: read-only everything", verify_step_5()))
    results.append(("Step 6: Add standard forbidden_patterns for all types", verify_step_6()))
    results.append(("Step 7: Add task-specific forbidden_patterns", verify_step_7()))
    results.append(("Step 8: Return complete tool_policy structure", verify_step_8()))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for step_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {step_name}")
        all_passed &= passed

    print("\n" + "=" * 70)
    if all_passed:
        print("✓ ALL VERIFICATION STEPS PASSED")
        print("Feature #57: Tool Policy Derivation from Task Type is COMPLETE")
        return 0
    else:
        print("✗ SOME VERIFICATION STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
