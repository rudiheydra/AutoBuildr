#!/usr/bin/env python3
"""
Verification script for Feature #36: StaticSpecAdapter for Legacy Initializer

This script verifies all 10 steps of the feature:
1. Create StaticSpecAdapter class
2. Define create_initializer_spec() method
3. Load initializer prompt from prompts/ directory
4. Set objective from prompt template
5. Set task_type to custom
6. Configure tool_policy with feature creation tools only
7. Set max_turns appropriate for initialization
8. Set timeout_seconds for long spec parsing
9. Create AcceptanceSpec with feature_count validator
10. Return static AgentSpec
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_step(step_num: int, description: str, passed: bool):
    """Print step result."""
    status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
    print(f"  Step {step_num}: {description} - {status}")


def verify_step_1():
    """Step 1: Create StaticSpecAdapter class."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter

        # Verify it's a class
        assert isinstance(StaticSpecAdapter, type), "StaticSpecAdapter should be a class"

        # Verify it can be instantiated
        adapter = StaticSpecAdapter()
        assert adapter is not None, "Should be able to instantiate StaticSpecAdapter"

        # Verify it has the expected attributes
        assert hasattr(adapter, 'prompts_dir'), "Should have prompts_dir property"
        assert hasattr(adapter, 'registry'), "Should have registry property"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_2():
    """Step 2: Define create_initializer_spec() method."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter

        adapter = StaticSpecAdapter()

        # Verify method exists
        assert hasattr(adapter, 'create_initializer_spec'), "Should have create_initializer_spec method"
        assert callable(adapter.create_initializer_spec), "create_initializer_spec should be callable"

        # Verify method signature (can be called with various arguments)
        spec = adapter.create_initializer_spec()
        assert spec is not None, "Should return a spec"

        spec2 = adapter.create_initializer_spec(project_name="TestProject")
        assert spec2 is not None, "Should accept project_name argument"

        spec3 = adapter.create_initializer_spec(feature_count=100)
        assert spec3 is not None, "Should accept feature_count argument"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_3():
    """Step 3: Load initializer prompt from prompts/ directory."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter

        adapter = StaticSpecAdapter()

        # Verify prompts directory exists
        assert adapter.prompts_dir.exists(), f"Prompts dir should exist: {adapter.prompts_dir}"

        # Verify initializer prompt file exists
        initializer_prompt_path = adapter.prompts_dir / "initializer_prompt.md"
        assert initializer_prompt_path.exists(), f"Initializer prompt should exist: {initializer_prompt_path}"

        # Verify the adapter can load the prompt
        spec = adapter.create_initializer_spec()

        # Objective should contain content from the initializer prompt
        assert len(spec.objective) > 100, "Objective should contain substantial prompt content"
        assert "INITIALIZER" in spec.objective or "initializer" in spec.objective.lower(), \
            "Objective should contain initializer-related content"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_4():
    """Step 4: Set objective from prompt template."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec(project_name="TestApp")

        # Verify objective is set
        assert spec.objective is not None, "Objective should be set"
        assert len(spec.objective) > 0, "Objective should not be empty"

        # Verify objective contains expected content from the prompt
        # (checking for content that should be in initializer_prompt.md)
        objective_lower = spec.objective.lower()
        expected_keywords = ["feature", "create", "agent"]
        found_keywords = [kw for kw in expected_keywords if kw in objective_lower]
        assert len(found_keywords) >= 2, f"Objective should contain prompt content, found: {found_keywords}"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_5():
    """Step 5: Set task_type to custom."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec()

        # Verify task_type is "custom"
        assert spec.task_type == "custom", f"Expected task_type 'custom', got '{spec.task_type}'"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_6():
    """Step 6: Configure tool_policy with feature creation tools only."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter, INITIALIZER_TOOLS

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec()

        # Verify tool_policy exists and is a dict
        assert spec.tool_policy is not None, "tool_policy should be set"
        assert isinstance(spec.tool_policy, dict), "tool_policy should be a dict"

        # Verify policy version
        assert spec.tool_policy.get("policy_version") == "v1", "Should have policy_version v1"

        # Verify allowed_tools
        allowed_tools = spec.tool_policy.get("allowed_tools", [])
        assert isinstance(allowed_tools, list), "allowed_tools should be a list"

        # Should include feature creation tools
        feature_tools = ["feature_create", "feature_create_bulk", "feature_get_stats"]
        for tool in feature_tools:
            assert tool in allowed_tools, f"Should include {tool} in allowed_tools"

        # Verify forbidden_patterns exist
        forbidden = spec.tool_policy.get("forbidden_patterns", [])
        assert isinstance(forbidden, list), "forbidden_patterns should be a list"
        assert len(forbidden) > 0, "Should have some forbidden patterns for security"

        # Verify tool_hints exist
        hints = spec.tool_policy.get("tool_hints", {})
        assert isinstance(hints, dict), "tool_hints should be a dict"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_7():
    """Step 7: Set max_turns appropriate for initialization."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter, DEFAULT_BUDGETS

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec()

        # Verify max_turns is set
        assert spec.max_turns is not None, "max_turns should be set"
        assert isinstance(spec.max_turns, int), "max_turns should be an integer"

        # Verify it's appropriate for initialization (should be higher than coding/testing)
        expected = DEFAULT_BUDGETS["initializer"]["max_turns"]
        assert spec.max_turns == expected, f"Expected max_turns {expected}, got {spec.max_turns}"

        # Initialization should have generous turn budget (at least 50)
        assert spec.max_turns >= 50, f"max_turns should be >= 50 for initialization, got {spec.max_turns}"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_8():
    """Step 8: Set timeout_seconds for long spec parsing."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter, DEFAULT_BUDGETS

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec()

        # Verify timeout_seconds is set
        assert spec.timeout_seconds is not None, "timeout_seconds should be set"
        assert isinstance(spec.timeout_seconds, int), "timeout_seconds should be an integer"

        # Verify it's appropriate for initialization (should be generous)
        expected = DEFAULT_BUDGETS["initializer"]["timeout_seconds"]
        assert spec.timeout_seconds == expected, f"Expected timeout {expected}, got {spec.timeout_seconds}"

        # Initialization should have generous timeout (at least 30 minutes)
        assert spec.timeout_seconds >= 1800, f"timeout should be >= 1800s, got {spec.timeout_seconds}"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_9():
    """Step 9: Create AcceptanceSpec with feature_count validator."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec(feature_count=85)

        # Verify acceptance_spec exists
        assert spec.acceptance_spec is not None, "acceptance_spec should be created"

        acceptance = spec.acceptance_spec

        # Verify it has validators
        assert acceptance.validators is not None, "validators should be set"
        assert isinstance(acceptance.validators, list), "validators should be a list"
        assert len(acceptance.validators) > 0, "Should have at least one validator"

        # Find the feature_count validator
        feature_count_validator = None
        for v in acceptance.validators:
            config = v.get("config", {})
            if config.get("check_type") == "feature_count" or config.get("name") == "feature_count":
                feature_count_validator = v
                break

        assert feature_count_validator is not None, "Should have a feature_count validator"

        # Verify the expected count
        config = feature_count_validator.get("config", {})
        assert config.get("expected_count") == 85, f"Expected count should be 85, got {config.get('expected_count')}"

        # Verify it's required
        assert feature_count_validator.get("required") == True, "feature_count validator should be required"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def verify_step_10():
    """Step 10: Return static AgentSpec."""
    try:
        from api.static_spec_adapter import StaticSpecAdapter
        from api.agentspec_models import AgentSpec

        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec(project_name="TestProject", feature_count=100)

        # Verify it's an AgentSpec instance
        assert isinstance(spec, AgentSpec), f"Should return AgentSpec, got {type(spec)}"

        # Verify all required fields are set
        assert spec.id is not None, "id should be set"
        assert spec.name is not None, "name should be set"
        assert spec.display_name is not None, "display_name should be set"
        assert spec.objective is not None, "objective should be set"
        assert spec.task_type is not None, "task_type should be set"
        assert spec.tool_policy is not None, "tool_policy should be set"
        assert spec.max_turns is not None, "max_turns should be set"
        assert spec.timeout_seconds is not None, "timeout_seconds should be set"

        # Verify context is set with agent_type
        assert spec.context is not None, "context should be set"
        assert spec.context.get("agent_type") == "initializer", "context should indicate initializer"

        # Verify spec can be serialized to dict
        spec_dict = spec.to_dict()
        assert isinstance(spec_dict, dict), "to_dict() should return a dict"

        # Verify tags indicate legacy adapter
        assert "legacy" in (spec.tags or []) or "initializer" in (spec.tags or []), \
            "Should have appropriate tags"

        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False


def main():
    """Run all verification steps."""
    print("\n" + "=" * 70)
    print("Feature #36: StaticSpecAdapter for Legacy Initializer - Verification")
    print("=" * 70 + "\n")

    steps = [
        (1, "Create StaticSpecAdapter class", verify_step_1),
        (2, "Define create_initializer_spec() method", verify_step_2),
        (3, "Load initializer prompt from prompts/ directory", verify_step_3),
        (4, "Set objective from prompt template", verify_step_4),
        (5, "Set task_type to custom", verify_step_5),
        (6, "Configure tool_policy with feature creation tools only", verify_step_6),
        (7, "Set max_turns appropriate for initialization", verify_step_7),
        (8, "Set timeout_seconds for long spec parsing", verify_step_8),
        (9, "Create AcceptanceSpec with feature_count validator", verify_step_9),
        (10, "Return static AgentSpec", verify_step_10),
    ]

    results = []
    for step_num, description, verify_func in steps:
        passed = verify_func()
        print_step(step_num, description, passed)
        results.append(passed)

    # Summary
    passed_count = sum(results)
    total_count = len(results)

    print("\n" + "-" * 70)
    if passed_count == total_count:
        print(f"\033[92mAll {total_count} verification steps PASSED!\033[0m")
        return 0
    else:
        print(f"\033[91m{passed_count}/{total_count} verification steps passed\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
