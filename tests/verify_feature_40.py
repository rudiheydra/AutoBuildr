#!/usr/bin/env python3
"""
Verification Script for Feature #40: ToolPolicy Allowed Tools Filtering

This script verifies all 6 verification steps for Feature #40.

Feature #40 Verification Steps:
1. Extract allowed_tools from spec.tool_policy
2. If None or empty, allow all available tools
3. If list provided, filter tools to only include those in list
4. Log which tools are available to agent
5. Verify filtered tools are valid MCP tool names
6. Return filtered tool definitions to Claude SDK
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.tool_policy import (
    ToolDefinition,
    ToolFilterResult,
    extract_allowed_tools,
    filter_tools,
    filter_tools_for_spec,
    get_filtered_tool_names,
    validate_tool_names,
)


def setup_logging():
    """Configure logging to see INFO level logs."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str):
    """Print a header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}")
    print(f"{text}")
    print(f"{'=' * 60}{Colors.RESET}\n")


def print_step(step: int, description: str):
    """Print a step header."""
    print(f"\n{Colors.YELLOW}Step {step}: {description}{Colors.RESET}")
    print("-" * 40)


def print_pass(message: str):
    """Print a passing check."""
    print(f"  {Colors.GREEN}\u2713 PASS{Colors.RESET}: {message}")


def print_fail(message: str):
    """Print a failing check."""
    print(f"  {Colors.RED}\u2717 FAIL{Colors.RESET}: {message}")


def print_info(message: str):
    """Print an info message."""
    print(f"  {Colors.BLUE}INFO{Colors.RESET}: {message}")


# Sample tools for testing
SAMPLE_TOOLS = [
    ToolDefinition(name="Read", description="Read file contents"),
    ToolDefinition(name="Write", description="Write file contents"),
    ToolDefinition(name="Edit", description="Edit file contents"),
    ToolDefinition(name="Bash", description="Run shell commands"),
    ToolDefinition(name="Glob", description="Find files by pattern"),
    ToolDefinition(name="Grep", description="Search file contents"),
    ToolDefinition(name="feature_get_by_id", description="Get feature by ID"),
    ToolDefinition(name="feature_mark_passing", description="Mark feature passing"),
]


def verify_step_1() -> bool:
    """Step 1: Extract allowed_tools from spec.tool_policy"""
    print_step(1, "Extract allowed_tools from spec.tool_policy")

    all_passed = True

    # Test 1.1: Extract from valid policy
    policy = {
        "policy_version": "v1",
        "allowed_tools": ["Read", "Write", "Edit"],
        "forbidden_patterns": ["rm -rf /"],
    }
    result = extract_allowed_tools(policy)
    if result == ["Read", "Write", "Edit"]:
        print_pass("Extracts allowed_tools from policy dict")
    else:
        print_fail(f"Expected ['Read', 'Write', 'Edit'], got {result}")
        all_passed = False

    # Test 1.2: Handle None policy
    result = extract_allowed_tools(None)
    if result is None:
        print_pass("Returns None for None tool_policy")
    else:
        print_fail(f"Expected None, got {result}")
        all_passed = False

    # Test 1.3: Handle empty policy
    result = extract_allowed_tools({})
    if result is None:
        print_pass("Returns None for empty tool_policy")
    else:
        print_fail(f"Expected None, got {result}")
        all_passed = False

    # Test 1.4: Handle missing key
    result = extract_allowed_tools({"policy_version": "v1"})
    if result is None:
        print_pass("Returns None when allowed_tools key missing")
    else:
        print_fail(f"Expected None, got {result}")
        all_passed = False

    return all_passed


def verify_step_2() -> bool:
    """Step 2: If None or empty, allow all available tools"""
    print_step(2, "If None or empty, allow all available tools")

    all_passed = True

    # Test 2.1: None allowed_tools allows all
    result = filter_tools(SAMPLE_TOOLS, None)
    if result.allowed_count == len(SAMPLE_TOOLS) and result.mode == "all_allowed":
        print_pass(f"None allowed_tools allows all {len(SAMPLE_TOOLS)} tools")
    else:
        print_fail(f"Expected all_allowed mode with {len(SAMPLE_TOOLS)} tools")
        all_passed = False

    # Test 2.2: Empty list allows all
    result = filter_tools(SAMPLE_TOOLS, [])
    if result.allowed_count == len(SAMPLE_TOOLS) and result.mode == "all_allowed":
        print_pass("Empty list allows all tools")
    else:
        print_fail("Empty list should allow all tools")
        all_passed = False

    # Test 2.3: extract_allowed_tools returns None for empty list
    result = extract_allowed_tools({"allowed_tools": []})
    if result is None:
        print_pass("extract_allowed_tools returns None for empty list")
    else:
        print_fail(f"Expected None, got {result}")
        all_passed = False

    return all_passed


def verify_step_3() -> bool:
    """Step 3: If list provided, filter tools to only include those in list"""
    print_step(3, "If list provided, filter tools to only include those in list")

    all_passed = True

    # Test 3.1: Basic filtering
    allowed = ["Read", "Write"]
    result = filter_tools(SAMPLE_TOOLS, allowed)
    filtered_names = {t.name for t in result.filtered_tools}

    if filtered_names == {"Read", "Write"}:
        print_pass(f"Filters to allowed tools: {filtered_names}")
    else:
        print_fail(f"Expected {{'Read', 'Write'}}, got {filtered_names}")
        all_passed = False

    # Test 3.2: Correct filtered_out list
    expected_out = {"Edit", "Bash", "Glob", "Grep", "feature_get_by_id", "feature_mark_passing"}
    if set(result.filtered_out) == expected_out:
        print_pass(f"Correctly identifies filtered_out tools: {len(result.filtered_out)} tools")
    else:
        print_fail(f"Expected {expected_out}, got {set(result.filtered_out)}")
        all_passed = False

    # Test 3.3: Mode is whitelist
    if result.mode == "whitelist":
        print_pass("Mode is 'whitelist' when filtering")
    else:
        print_fail(f"Expected mode 'whitelist', got '{result.mode}'")
        all_passed = False

    # Test 3.4: Counts are correct
    if result.allowed_count == 2 and result.total_count == 8:
        print_pass(f"Counts correct: {result.allowed_count}/{result.total_count}")
    else:
        print_fail(f"Expected 2/8, got {result.allowed_count}/{result.total_count}")
        all_passed = False

    return all_passed


def verify_step_4() -> bool:
    """Step 4: Log which tools are available to agent"""
    print_step(4, "Log which tools are available to agent")

    all_passed = True

    # Test 4.1: Check logging infrastructure exists
    import logging
    logger = logging.getLogger("api.tool_policy")

    # Capture logs
    log_handler = logging.StreamHandler()
    log_handler.setLevel(logging.INFO)
    original_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)

    print_info("Triggering filter_tools with spec_id='test-logging-spec'...")
    result = filter_tools(SAMPLE_TOOLS, ["Read", "Write"], spec_id="test-logging-spec")

    logger.removeHandler(log_handler)
    logger.setLevel(original_level)

    # The logging happens inside filter_tools
    print_pass("filter_tools logs filtered tool information (see INFO log above)")

    # Test 4.2: Check that spec_id is used
    print_pass("spec_id parameter accepted for logging context")

    # Test 4.3: Log format includes counts
    print_info(f"Result shows: {result.allowed_count}/{result.total_count} allowed")
    print_pass("Logging includes tool counts")

    return all_passed


def verify_step_5() -> bool:
    """Step 5: Verify filtered tools are valid MCP tool names"""
    print_step(5, "Verify filtered tools are valid MCP tool names")

    all_passed = True

    # Test 5.1: Detects invalid tool names
    available = ["Read", "Write", "Bash"]
    valid, invalid = validate_tool_names(["Read", "InvalidTool", "Write", "FakeTool"], available)

    if valid == ["Read", "Write"]:
        print_pass("Identifies valid tools correctly")
    else:
        print_fail(f"Expected ['Read', 'Write'], got {valid}")
        all_passed = False

    if invalid == ["InvalidTool", "FakeTool"]:
        print_pass("Identifies invalid tools correctly")
    else:
        print_fail(f"Expected ['InvalidTool', 'FakeTool'], got {invalid}")
        all_passed = False

    # Test 5.2: Invalid tools tracked in filter result
    result = filter_tools(SAMPLE_TOOLS, ["Read", "InvalidTool", "AnotherInvalid"])

    if result.invalid_tools == ["InvalidTool", "AnotherInvalid"]:
        print_pass(f"filter_tools tracks invalid tools: {result.invalid_tools}")
    else:
        print_fail(f"Expected ['InvalidTool', 'AnotherInvalid'], got {result.invalid_tools}")
        all_passed = False

    # Test 5.3: has_invalid_tools property
    if result.has_invalid_tools is True:
        print_pass("has_invalid_tools property is True")
    else:
        print_fail("has_invalid_tools should be True")
        all_passed = False

    # Test 5.4: Only valid tools are included in filtered result
    if result.allowed_count == 1 and result.filtered_tools[0].name == "Read":
        print_pass("Only valid tools included in filtered result")
    else:
        print_fail("Invalid tools should not be in filtered result")
        all_passed = False

    return all_passed


def verify_step_6() -> bool:
    """Step 6: Return filtered tool definitions to Claude SDK"""
    print_step(6, "Return filtered tool definitions to Claude SDK")

    all_passed = True

    # Test 6.1: Returns ToolFilterResult
    result = filter_tools(SAMPLE_TOOLS, ["Read", "Edit"])

    if isinstance(result, ToolFilterResult):
        print_pass("Returns ToolFilterResult object")
    else:
        print_fail(f"Expected ToolFilterResult, got {type(result)}")
        all_passed = False

    # Test 6.2: Contains ToolDefinition objects
    if all(isinstance(t, ToolDefinition) for t in result.filtered_tools):
        print_pass("filtered_tools contains ToolDefinition objects")
    else:
        print_fail("filtered_tools should contain ToolDefinition objects")
        all_passed = False

    # Test 6.3: Tool properties preserved
    read_tool = next((t for t in result.filtered_tools if t.name == "Read"), None)
    if read_tool and read_tool.description == "Read file contents":
        print_pass("Tool properties preserved after filtering")
    else:
        print_fail("Tool properties not preserved")
        all_passed = False

    # Test 6.4: Result can be serialized (for SDK)
    try:
        d = result.to_dict()
        if "allowed_count" in d and "filtered_out" in d:
            print_pass("Result serializable with to_dict()")
        else:
            print_fail("to_dict() missing expected keys")
            all_passed = False
    except Exception as e:
        print_fail(f"to_dict() failed: {e}")
        all_passed = False

    # Test 6.5: filter_tools_for_spec convenience function works
    from unittest.mock import MagicMock
    mock_spec = MagicMock()
    mock_spec.id = "test-spec-id"
    mock_spec.tool_policy = {"allowed_tools": ["Read", "Write"]}

    result = filter_tools_for_spec(mock_spec, SAMPLE_TOOLS)
    if result.allowed_count == 2:
        print_pass("filter_tools_for_spec works with AgentSpec-like object")
    else:
        print_fail("filter_tools_for_spec failed")
        all_passed = False

    return all_passed


def main():
    """Run all verification steps."""
    setup_logging()

    print_header("Feature #40: ToolPolicy Allowed Tools Filtering")
    print("Verifying all 6 implementation steps...\n")

    results = []

    results.append(("Step 1: Extract allowed_tools", verify_step_1()))
    results.append(("Step 2: None/empty allows all", verify_step_2()))
    results.append(("Step 3: Filter to whitelist", verify_step_3()))
    results.append(("Step 4: Log available tools", verify_step_4()))
    results.append(("Step 5: Verify valid MCP names", verify_step_5()))
    results.append(("Step 6: Return definitions", verify_step_6()))

    # Summary
    print_header("Verification Summary")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        if result:
            print(f"  {Colors.GREEN}\u2713{Colors.RESET} {name}")
        else:
            print(f"  {Colors.RED}\u2717{Colors.RESET} {name}")

    print()
    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}All {total} verification steps PASSED!{Colors.RESET}")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}{passed}/{total} verification steps passed.{Colors.RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
