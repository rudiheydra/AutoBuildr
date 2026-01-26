#!/usr/bin/env python3
"""
Feature #38 Verification Script
================================

Verifies that StaticSpecAdapter for Legacy Testing Agent is fully implemented.

Run: python tests/verify_feature_38.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.static_spec_adapter import (
    StaticSpecAdapter,
    TESTING_TOOLS,
    DEFAULT_BUDGETS,
)


def check(condition: bool, message: str) -> bool:
    """Check a condition and print result."""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {message}")
    return condition


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #38: StaticSpecAdapter for Legacy Testing Agent")
    print("=" * 60)
    print()

    # Create adapter
    adapter = StaticSpecAdapter()

    # Sample feature steps
    sample_steps = [
        "Navigate to login page",
        "Enter valid credentials",
        "Click submit button",
        "Verify redirect to dashboard",
    ]

    # Create spec with and without steps
    spec_without_steps = adapter.create_testing_spec(feature_id=42)
    spec_with_steps = adapter.create_testing_spec(
        feature_id=42,
        feature_name="User Login",
        feature_steps=sample_steps
    )

    all_passed = True

    # Step 1
    print("Step 1: Define create_testing_spec(feature_id) method")
    all_passed &= check(
        hasattr(adapter, 'create_testing_spec'),
        "Method exists"
    )
    all_passed &= check(
        callable(adapter.create_testing_spec),
        "Method is callable"
    )
    print()

    # Step 2
    print("Step 2: Load testing agent prompt from prompts/")
    prompt_path = adapter.prompts_dir / "testing_prompt.md"
    all_passed &= check(
        prompt_path.exists(),
        f"testing_prompt.md exists at {prompt_path}"
    )
    all_passed &= check(
        len(spec_without_steps.objective) > 100,
        f"Objective loaded (length: {len(spec_without_steps.objective)})"
    )
    print()

    # Step 3
    print("Step 3: Interpolate feature steps as test criteria")
    for step in sample_steps:
        all_passed &= check(
            step in spec_with_steps.objective,
            f"Step '{step[:30]}...' in objective"
        )
    all_passed &= check(
        "Test Criteria" in spec_with_steps.objective,
        "Test Criteria section present"
    )
    print()

    # Step 4
    print("Step 4: Set task_type to testing")
    all_passed &= check(
        spec_without_steps.task_type == "testing",
        f"task_type is 'testing' (got: {spec_without_steps.task_type})"
    )
    print()

    # Step 5
    print("Step 5: Configure tool_policy with test execution tools")
    allowed = spec_without_steps.tool_policy["allowed_tools"]
    all_passed &= check(
        "browser_navigate" in allowed,
        "browser_navigate in allowed tools"
    )
    all_passed &= check(
        "browser_snapshot" in allowed,
        "browser_snapshot in allowed tools"
    )
    all_passed &= check(
        "feature_mark_passing" in allowed,
        "feature_mark_passing in allowed tools"
    )
    all_passed &= check(
        "Bash" in allowed,
        "Bash in allowed tools (for running tests)"
    )
    print()

    # Step 6
    print("Step 6: Restrict to read-only file access")
    all_passed &= check(
        "Write" not in allowed,
        "Write tool not in allowed tools"
    )
    all_passed &= check(
        "Edit" not in allowed,
        "Edit tool not in allowed tools"
    )
    all_passed &= check(
        "Read" in allowed,
        "Read tool in allowed tools"
    )
    all_passed &= check(
        "Glob" in allowed,
        "Glob tool in allowed tools"
    )
    print()

    # Step 7
    print("Step 7: Set max_turns appropriate for testing")
    expected_turns = DEFAULT_BUDGETS["testing"]["max_turns"]
    coding_turns = DEFAULT_BUDGETS["coding"]["max_turns"]
    all_passed &= check(
        spec_without_steps.max_turns == expected_turns,
        f"max_turns is {expected_turns} (got: {spec_without_steps.max_turns})"
    )
    all_passed &= check(
        expected_turns < coding_turns,
        f"Testing budget ({expected_turns}) < coding budget ({coding_turns})"
    )
    print()

    # Step 8
    print("Step 8: Create AcceptanceSpec based on feature steps")
    all_passed &= check(
        spec_with_steps.acceptance_spec is not None,
        "AcceptanceSpec created"
    )
    all_passed &= check(
        spec_with_steps.acceptance_spec.agent_spec_id == spec_with_steps.id,
        "AcceptanceSpec linked to AgentSpec"
    )
    validators = spec_with_steps.acceptance_spec.validators
    all_passed &= check(
        len(validators) > 1,
        f"Multiple validators ({len(validators)})"
    )
    print()

    # Step 9
    print("Step 9: Generate test_pass validators from feature steps")
    test_pass_validators = [v for v in validators if v["type"] == "test_pass"]
    all_passed &= check(
        len(test_pass_validators) == len(sample_steps),
        f"test_pass validators match steps ({len(test_pass_validators)}/{len(sample_steps)})"
    )
    for i, step in enumerate(sample_steps, 1):
        validator = next(
            (v for v in test_pass_validators if v["config"].get("step_number") == i),
            None
        )
        if validator:
            all_passed &= check(
                validator["config"]["description"] == step,
                f"Step {i} validator has correct description"
            )
    print()

    # Step 10
    print("Step 10: Link source_feature_id to feature")
    all_passed &= check(
        spec_without_steps.source_feature_id == 42,
        f"source_feature_id is 42 (got: {spec_without_steps.source_feature_id})"
    )
    print()

    # Step 11
    print("Step 11: Return static AgentSpec")
    from api.agentspec_models import AgentSpec
    all_passed &= check(
        isinstance(spec_without_steps, AgentSpec),
        "Returns AgentSpec instance"
    )
    all_passed &= check(
        spec_without_steps.id is not None,
        "AgentSpec has ID"
    )
    all_passed &= check(
        spec_without_steps.icon == "test-tube",
        f"Icon is 'test-tube' (got: {spec_without_steps.icon})"
    )
    all_passed &= check(
        "testing" in spec_without_steps.tags,
        "Tags include 'testing'"
    )
    all_passed &= check(
        "legacy" in spec_without_steps.tags,
        "Tags include 'legacy'"
    )
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("RESULT: All verification steps PASSED")
        print("Feature #38 is fully implemented and working correctly.")
    else:
        print("RESULT: Some verification steps FAILED")
        print("Please review the failed checks above.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
