#!/usr/bin/env python3
"""
Feature #43 Integration Test
============================

Tests that tool_hints from tool_policy are correctly injected into
system prompts when used with AgentSpec data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.prompt_builder import build_system_prompt, inject_tool_hints_into_prompt


def test_agentspec_integration():
    """Test integration with AgentSpec-like data."""
    print("Testing integration with AgentSpec model...")

    # Simulate the tool_policy structure stored in the database
    spec_tool_policy = {
        "policy_version": "v1",
        "allowed_tools": ["Read", "Glob", "Bash", "feature_mark_passing"],
        "forbidden_patterns": ["DROP TABLE"],
        "allowed_directories": ["/home/user/project"],
        "tool_hints": {
            "feature_mark_passing": "Call only after verification with screenshots",
            "Bash": "Avoid destructive commands; prefer Read tool for file access",
            "Read": "Use for reading source code files",
        },
    }

    # Test the build_system_prompt function with spec data
    objective = "Implement the user registration feature with email verification"
    task_type = "coding"

    prompt = build_system_prompt(
        objective=objective,
        context={"feature_id": 42, "source_files": ["src/auth.py", "src/email.py"]},
        tool_policy=spec_tool_policy,
        task_type=task_type,
    )

    print()
    print("Generated System Prompt:")
    print("=" * 60)
    print(prompt)
    print("=" * 60)

    # Verify all components are present
    assert "# Objective" in prompt
    assert objective in prompt
    assert f"**Task Type:** {task_type}" in prompt
    assert "## Context" in prompt
    assert "## Tool Usage Guidelines" in prompt

    # Verify tool hints
    assert "- **Bash**:" in prompt
    assert "- **Read**:" in prompt
    assert "- **feature_mark_passing**:" in prompt
    assert "Call only after verification with screenshots" in prompt

    print()
    print("[SUCCESS] AgentSpec integration test passed!")
    print("The tool_policy.tool_hints are correctly injected into the system prompt.")
    return True


def test_inject_into_existing_template():
    """Test injecting tool hints into an existing prompt template."""
    print("\nTesting inject_tool_hints_into_prompt...")

    # Simulate a template-based prompt (like from TemplateRegistry)
    template_prompt = """You are an expert coding assistant working on the AutoBuildr project.

Your task is to implement features according to the specification.

## Guidelines
- Write clean, maintainable code
- Follow existing patterns in the codebase
- Test your changes before committing"""

    tool_policy = {
        "tool_hints": {
            "feature_mark_passing": "Only mark passing after full verification",
            "Bash": "Prefer non-destructive commands",
        }
    }

    result = inject_tool_hints_into_prompt(template_prompt, tool_policy)

    print("Result after injection:")
    print("=" * 60)
    print(result)
    print("=" * 60)

    # Verify original content preserved
    assert "You are an expert coding assistant" in result
    assert "## Guidelines" in result

    # Verify hints added
    assert "## Tool Usage Guidelines" in result
    assert "feature_mark_passing" in result
    assert "Bash" in result

    print("[SUCCESS] inject_tool_hints_into_prompt works correctly!")
    return True


if __name__ == "__main__":
    all_passed = True

    try:
        test_agentspec_integration()
    except AssertionError as e:
        print(f"[FAIL] Integration test: {e}")
        all_passed = False

    try:
        test_inject_into_existing_template()
    except AssertionError as e:
        print(f"[FAIL] Injection test: {e}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL INTEGRATION TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)
