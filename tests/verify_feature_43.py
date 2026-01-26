#!/usr/bin/env python3
"""
Feature #43 Verification Script
================================

Tool Hints System Prompt Injection

Description: Inject tool_hints from tool_policy into system prompt to guide agent tool usage.

Verification Steps:
1. Extract tool_hints dict from spec.tool_policy
2. Format hints as markdown guidelines
3. Append to system prompt in dedicated section
4. Example: ## Tool Usage Guidelines - feature_mark_passing: Call only after verification
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.prompt_builder import (
    build_system_prompt,
    extract_tool_hints,
    format_tool_hints_as_markdown,
    inject_tool_hints_into_prompt,
)


def print_step(step: int, description: str):
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"Step {step}: {description}")
    print('='*60)


def verify_step_1():
    """Step 1: Extract tool_hints dict from spec.tool_policy"""
    print_step(1, "Extract tool_hints dict from spec.tool_policy")

    # Test case: Full tool_policy with hints
    tool_policy = {
        "policy_version": "v1",
        "allowed_tools": ["Read", "Glob", "Bash"],
        "forbidden_patterns": ["rm -rf", "DROP TABLE"],
        "tool_hints": {
            "feature_mark_passing": "Call only after verification",
            "Bash": "Avoid destructive commands like rm, mv without confirmation",
        }
    }

    hints = extract_tool_hints(tool_policy)

    print(f"Input tool_policy: {tool_policy}")
    print(f"Extracted hints: {hints}")

    # Verify
    assert isinstance(hints, dict), "Result should be a dict"
    assert len(hints) == 2, f"Expected 2 hints, got {len(hints)}"
    assert hints["feature_mark_passing"] == "Call only after verification"
    assert "Bash" in hints

    print("\n[PASS] Step 1: Successfully extracted tool_hints dict")
    return True


def verify_step_2():
    """Step 2: Format hints as markdown guidelines"""
    print_step(2, "Format hints as markdown guidelines")

    hints = {
        "feature_mark_passing": "Call only after verification",
        "Bash": "Avoid destructive commands",
    }

    markdown = format_tool_hints_as_markdown(hints)

    print(f"Input hints: {hints}")
    print(f"\nFormatted markdown:\n{markdown}")

    # Verify markdown structure
    assert markdown.startswith("## Tool Usage Guidelines"), "Should start with header"
    assert "- **Bash**:" in markdown, "Should have bullet with bold tool name"
    assert "- **feature_mark_passing**:" in markdown, "Should have second bullet"
    assert "Call only after verification" in markdown, "Should contain hint text"

    print("\n[PASS] Step 2: Successfully formatted hints as markdown guidelines")
    return True


def verify_step_3():
    """Step 3: Append to system prompt in dedicated section"""
    print_step(3, "Append to system prompt in dedicated section")

    objective = "Implement user authentication feature with OAuth support"
    tool_policy = {
        "tool_hints": {
            "feature_mark_passing": "Call only after verification",
            "Read": "Use for reading source files only",
        }
    }

    prompt = build_system_prompt(
        objective,
        tool_policy=tool_policy,
        task_type="coding",
    )

    print(f"Objective: {objective}")
    print(f"Tool policy: {tool_policy}")
    print(f"\nGenerated system prompt:\n{prompt}")

    # Verify structure
    assert "# Objective" in prompt, "Should have objective section"
    assert objective in prompt, "Should contain the objective"
    assert "## Tool Usage Guidelines" in prompt, "Should have dedicated guidelines section"
    assert "feature_mark_passing" in prompt, "Should contain tool hint"

    # Verify order: objective comes before guidelines
    objective_pos = prompt.index("# Objective")
    guidelines_pos = prompt.index("## Tool Usage Guidelines")
    assert guidelines_pos > objective_pos, "Guidelines should come after objective"

    print("\n[PASS] Step 3: Successfully appended guidelines to system prompt")
    return True


def verify_step_4():
    """Step 4: Example format verification"""
    print_step(4, "Example: ## Tool Usage Guidelines - feature_mark_passing: Call only after verification")

    tool_policy = {
        "tool_hints": {
            "feature_mark_passing": "Call only after verification"
        }
    }

    prompt = build_system_prompt("Test objective", tool_policy=tool_policy)

    print(f"Generated prompt:\n{prompt}")

    # Verify the exact format from the feature description
    assert "## Tool Usage Guidelines" in prompt
    assert "feature_mark_passing" in prompt
    assert "Call only after verification" in prompt
    assert "- **feature_mark_passing**: Call only after verification" in prompt

    print("\n[PASS] Step 4: Example format matches specification")
    return True


def verify_inject_function():
    """Additional: Test inject_tool_hints_into_prompt function"""
    print_step(5, "Bonus: inject_tool_hints_into_prompt function")

    base_prompt = """You are an expert coding assistant.

Follow best practices and write clean code.
Always test your changes before committing."""

    tool_policy = {
        "tool_hints": {
            "feature_mark_passing": "Call only after verification",
            "Bash": "Never use rm -rf or other destructive commands",
        }
    }

    result = inject_tool_hints_into_prompt(base_prompt, tool_policy)

    print(f"Base prompt:\n{base_prompt}")
    print(f"\nAfter injection:\n{result}")

    # Verify
    assert "You are an expert coding assistant." in result
    assert "## Tool Usage Guidelines" in result
    assert base_prompt.strip() in result
    assert "feature_mark_passing" in result

    print("\n[PASS] Bonus: inject_tool_hints_into_prompt works correctly")
    return True


def main():
    """Run all verification steps."""
    print("="*60)
    print("Feature #43: Tool Hints System Prompt Injection")
    print("="*60)
    print("\nDescription: Inject tool_hints from tool_policy into system")
    print("prompt to guide agent tool usage.")

    all_passed = True
    steps = [
        verify_step_1,
        verify_step_2,
        verify_step_3,
        verify_step_4,
        verify_inject_function,
    ]

    for step_func in steps:
        try:
            step_func()
        except AssertionError as e:
            print(f"\n[FAIL] {e}")
            all_passed = False
        except Exception as e:
            print(f"\n[ERROR] {e}")
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("FEATURE #43 VERIFICATION: ALL STEPS PASSED")
        print("="*60)
        return 0
    else:
        print("FEATURE #43 VERIFICATION: SOME STEPS FAILED")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
