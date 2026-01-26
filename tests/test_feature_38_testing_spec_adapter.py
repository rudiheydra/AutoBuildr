#!/usr/bin/env python3
"""
Feature #38: StaticSpecAdapter for Legacy Testing Agent
========================================================

Tests to verify that the StaticSpecAdapter properly wraps the existing
testing agent as a static AgentSpec with read-only tool_policy.

Verification Steps:
1. Define create_testing_spec(feature_id) method
2. Load testing agent prompt from prompts/
3. Interpolate feature steps as test criteria
4. Set task_type to testing
5. Configure tool_policy with test execution tools
6. Restrict to read-only file access
7. Set max_turns appropriate for testing
8. Create AcceptanceSpec based on feature steps
9. Generate test_pass validators from feature steps
10. Link source_feature_id to feature
11. Return static AgentSpec
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.static_spec_adapter import (
    StaticSpecAdapter,
    TESTING_TOOLS,
    FORBIDDEN_PATTERNS,
    DEFAULT_BUDGETS,
    get_static_spec_adapter,
    reset_static_spec_adapter,
)
from api.agentspec_models import AgentSpec, AcceptanceSpec


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def adapter():
    """Create a StaticSpecAdapter instance."""
    return StaticSpecAdapter()


@pytest.fixture(autouse=True)
def reset_adapter():
    """Reset the default adapter before each test."""
    reset_static_spec_adapter()
    yield
    reset_static_spec_adapter()


@pytest.fixture
def sample_feature_steps():
    """Sample feature steps for testing."""
    return [
        "Navigate to login page",
        "Enter valid username and password",
        "Click submit button",
        "Verify redirect to dashboard",
        "Check user profile displays correctly",
    ]


# =============================================================================
# Step 1: Define create_testing_spec(feature_id) method
# =============================================================================

class TestStep1DefineCreateTestingSpec:
    """Tests for Step 1: Define create_testing_spec(feature_id) method."""

    def test_method_exists(self, adapter):
        """Test that create_testing_spec method exists."""
        assert hasattr(adapter, 'create_testing_spec')
        assert callable(adapter.create_testing_spec)

    def test_method_accepts_feature_id(self, adapter):
        """Test that method accepts feature_id parameter."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec is not None

    def test_method_signature_includes_feature_steps(self, adapter):
        """Test that method signature includes feature_steps parameter."""
        import inspect
        sig = inspect.signature(adapter.create_testing_spec)
        param_names = list(sig.parameters.keys())
        assert 'feature_id' in param_names
        assert 'feature_steps' in param_names

    def test_returns_agent_spec(self, adapter):
        """Test that method returns an AgentSpec."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert isinstance(spec, AgentSpec)


# =============================================================================
# Step 2: Load testing agent prompt from prompts/
# =============================================================================

class TestStep2LoadTestingPrompt:
    """Tests for Step 2: Load testing agent prompt from prompts/."""

    def test_prompt_file_exists(self, adapter):
        """Test that testing_prompt.md exists in prompts directory."""
        prompts_dir = adapter.prompts_dir
        testing_prompt_path = prompts_dir / "testing_prompt.md"
        assert testing_prompt_path.exists(), f"Testing prompt not found at {testing_prompt_path}"

    def test_objective_loaded_from_template(self, adapter):
        """Test that objective is loaded from testing_prompt.md."""
        spec = adapter.create_testing_spec(feature_id=42)

        # Read the template to compare
        testing_prompt_path = adapter.prompts_dir / "testing_prompt.md"
        template_content = testing_prompt_path.read_text()

        # Objective should contain some content from the template
        assert len(spec.objective) > 100
        # Should reference testing-related concepts
        assert "test" in spec.objective.lower() or "verify" in spec.objective.lower()

    def test_template_registry_used(self, adapter):
        """Test that TemplateRegistry is used for loading."""
        assert adapter.registry is not None
        # Should be able to get the testing template
        template = adapter._load_prompt("testing")
        assert template is not None
        assert len(template.content) > 0


# =============================================================================
# Step 3: Interpolate feature steps as test criteria
# =============================================================================

class TestStep3InterpolateFeatureSteps:
    """Tests for Step 3: Interpolate feature steps as test criteria."""

    def test_feature_steps_included_in_objective(self, adapter, sample_feature_steps):
        """Test that feature steps are included in objective."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        # Steps should be in the objective
        for step in sample_feature_steps:
            assert step in spec.objective, f"Step '{step}' not found in objective"

    def test_feature_steps_formatted_as_list(self, adapter, sample_feature_steps):
        """Test that feature steps are formatted as a bulleted list."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        # Should have "Test Criteria" section
        assert "Test Criteria" in spec.objective

    def test_feature_steps_in_context(self, adapter, sample_feature_steps):
        """Test that feature steps are stored in context."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        assert spec.context.get("feature_steps") == sample_feature_steps

    def test_empty_steps_handled(self, adapter):
        """Test that empty feature steps are handled gracefully."""
        spec = adapter.create_testing_spec(feature_id=42, feature_steps=[])
        assert spec is not None
        assert spec.context.get("feature_steps") == []

    def test_none_steps_handled(self, adapter):
        """Test that None feature steps are handled gracefully."""
        spec = adapter.create_testing_spec(feature_id=42, feature_steps=None)
        assert spec is not None
        assert spec.context.get("feature_steps") == []

    def test_feature_id_interpolated(self, adapter):
        """Test that feature_id is interpolated in variables."""
        spec = adapter.create_testing_spec(feature_id=99)
        # Feature ID should be in the context
        assert spec.context.get("feature_id") == 99


# =============================================================================
# Step 4: Set task_type to testing
# =============================================================================

class TestStep4SetTaskTypeToTesting:
    """Tests for Step 4: Set task_type to testing."""

    def test_task_type_is_testing(self, adapter):
        """Test that task_type is set to 'testing'."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.task_type == "testing"

    def test_task_type_not_coding(self, adapter):
        """Test that task_type is not 'coding'."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.task_type != "coding"


# =============================================================================
# Step 5: Configure tool_policy with test execution tools
# =============================================================================

class TestStep5ConfigureToolPolicy:
    """Tests for Step 5: Configure tool_policy with test execution tools."""

    def test_tool_policy_has_correct_structure(self, adapter):
        """Test that tool_policy has the correct structure."""
        spec = adapter.create_testing_spec(feature_id=42)

        policy = spec.tool_policy
        assert "policy_version" in policy
        assert "allowed_tools" in policy
        assert "forbidden_patterns" in policy
        assert "tool_hints" in policy

    def test_has_browser_automation_tools(self, adapter):
        """Test that testing tools include browser automation."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        # Browser tools for testing UI
        assert "browser_navigate" in allowed
        assert "browser_click" in allowed
        assert "browser_type" in allowed
        assert "browser_snapshot" in allowed
        assert "browser_take_screenshot" in allowed

    def test_has_feature_tools(self, adapter):
        """Test that testing tools include feature management."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "feature_get_by_id" in allowed
        assert "feature_mark_passing" in allowed
        assert "feature_mark_failing" in allowed

    def test_has_bash_for_test_execution(self, adapter):
        """Test that Bash tool is allowed for running tests."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "Bash" in allowed

    def test_forbidden_patterns_set(self, adapter):
        """Test that forbidden patterns are set for security."""
        spec = adapter.create_testing_spec(feature_id=42)

        forbidden = spec.tool_policy["forbidden_patterns"]
        assert len(forbidden) > 0
        # Should block dangerous operations
        patterns_str = " ".join(forbidden)
        assert "rm" in patterns_str.lower() or "delete" in patterns_str.lower()


# =============================================================================
# Step 6: Restrict to read-only file access
# =============================================================================

class TestStep6RestrictToReadOnly:
    """Tests for Step 6: Restrict to read-only file access."""

    def test_no_write_tool(self, adapter):
        """Test that Write tool is not allowed (read-only)."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "Write" not in allowed

    def test_no_edit_tool(self, adapter):
        """Test that Edit tool is not allowed (read-only)."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "Edit" not in allowed

    def test_has_read_tool(self, adapter):
        """Test that Read tool is allowed (read-only access)."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "Read" in allowed

    def test_has_glob_tool(self, adapter):
        """Test that Glob tool is allowed (for finding files)."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "Glob" in allowed

    def test_has_grep_tool(self, adapter):
        """Test that Grep tool is allowed (for searching)."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "Grep" in allowed

    def test_testing_tools_subset_of_coding_tools(self, adapter):
        """Test that testing tools don't include write capabilities."""
        # Testing tools should be more restrictive
        testing_tools = set(TESTING_TOOLS)
        write_tools = {"Write", "Edit", "NotebookEdit"}

        assert not testing_tools.intersection(write_tools), \
            f"Testing tools should not include write tools: {testing_tools.intersection(write_tools)}"


# =============================================================================
# Step 7: Set max_turns appropriate for testing
# =============================================================================

class TestStep7SetMaxTurns:
    """Tests for Step 7: Set max_turns appropriate for testing."""

    def test_max_turns_set(self, adapter):
        """Test that max_turns is set."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.max_turns > 0

    def test_max_turns_from_default_budgets(self, adapter):
        """Test that max_turns matches default budgets."""
        spec = adapter.create_testing_spec(feature_id=42)
        expected = DEFAULT_BUDGETS["testing"]["max_turns"]
        assert spec.max_turns == expected

    def test_testing_max_turns_less_than_coding(self, adapter):
        """Test that testing max_turns is less than coding max_turns."""
        testing_budget = DEFAULT_BUDGETS["testing"]["max_turns"]
        coding_budget = DEFAULT_BUDGETS["coding"]["max_turns"]

        assert testing_budget < coding_budget, \
            f"Testing budget ({testing_budget}) should be less than coding ({coding_budget})"

    def test_timeout_seconds_set(self, adapter):
        """Test that timeout_seconds is set."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.timeout_seconds > 0
        expected = DEFAULT_BUDGETS["testing"]["timeout_seconds"]
        assert spec.timeout_seconds == expected


# =============================================================================
# Step 8: Create AcceptanceSpec based on feature steps
# =============================================================================

class TestStep8CreateAcceptanceSpec:
    """Tests for Step 8: Create AcceptanceSpec based on feature steps."""

    def test_acceptance_spec_created(self, adapter):
        """Test that AcceptanceSpec is created."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.acceptance_spec is not None
        assert isinstance(spec.acceptance_spec, AcceptanceSpec)

    def test_acceptance_spec_linked(self, adapter):
        """Test that AcceptanceSpec is properly linked."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.acceptance_spec.agent_spec_id == spec.id

    def test_acceptance_spec_has_validators(self, adapter):
        """Test that AcceptanceSpec has validators."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert len(spec.acceptance_spec.validators) > 0

    def test_acceptance_spec_validators_increase_with_steps(self, adapter, sample_feature_steps):
        """Test that validators increase when feature steps provided."""
        spec_without_steps = adapter.create_testing_spec(feature_id=42)
        spec_with_steps = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        # Should have more validators with steps
        assert len(spec_with_steps.acceptance_spec.validators) > \
               len(spec_without_steps.acceptance_spec.validators)

    def test_gate_mode_is_all_pass(self, adapter):
        """Test that gate_mode is all_pass."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.acceptance_spec.gate_mode == "all_pass"


# =============================================================================
# Step 9: Generate test_pass validators from feature steps
# =============================================================================

class TestStep9GenerateTestPassValidators:
    """Tests for Step 9: Generate test_pass validators from feature steps."""

    def test_test_pass_validators_created(self, adapter, sample_feature_steps):
        """Test that test_pass validators are created for feature steps."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        validators = spec.acceptance_spec.validators
        test_pass_validators = [v for v in validators if v["type"] == "test_pass"]

        # Should have one test_pass validator per step
        assert len(test_pass_validators) == len(sample_feature_steps)

    def test_validator_descriptions_match_steps(self, adapter, sample_feature_steps):
        """Test that validator descriptions match feature steps."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        validators = spec.acceptance_spec.validators
        test_pass_validators = [v for v in validators if v["type"] == "test_pass"]

        # Each step should be represented
        for step in sample_feature_steps:
            found = any(
                v["config"].get("description") == step
                for v in test_pass_validators
            )
            assert found, f"Step '{step}' not found in validators"

    def test_validators_have_step_numbers(self, adapter, sample_feature_steps):
        """Test that validators have step numbers."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        validators = spec.acceptance_spec.validators
        test_pass_validators = [v for v in validators if v["type"] == "test_pass"]

        step_numbers = [v["config"].get("step_number") for v in test_pass_validators]
        assert list(range(1, len(sample_feature_steps) + 1)) == sorted(step_numbers)

    def test_validators_have_feature_id(self, adapter, sample_feature_steps):
        """Test that validators include feature_id."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        validators = spec.acceptance_spec.validators
        test_pass_validators = [v for v in validators if v["type"] == "test_pass"]

        for v in test_pass_validators:
            assert v["config"].get("feature_id") == 42

    def test_custom_test_complete_validator_present(self, adapter):
        """Test that custom test_complete validator is always present."""
        spec = adapter.create_testing_spec(feature_id=42)

        validators = spec.acceptance_spec.validators
        custom_validators = [v for v in validators if v["type"] == "custom"]

        # Should have at least one custom validator for test completion
        assert len(custom_validators) >= 1

        test_complete = next(
            (v for v in custom_validators if v["config"].get("check_type") == "test_completion"),
            None
        )
        assert test_complete is not None

    def test_validator_weights_distributed(self, adapter, sample_feature_steps):
        """Test that validator weights are distributed among steps."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        validators = spec.acceptance_spec.validators
        test_pass_validators = [v for v in validators if v["type"] == "test_pass"]

        # Each step should have equal weight
        expected_weight = 1.0 / len(sample_feature_steps)
        for v in test_pass_validators:
            assert abs(v["weight"] - expected_weight) < 0.01


# =============================================================================
# Step 10: Link source_feature_id to feature
# =============================================================================

class TestStep10LinkSourceFeatureId:
    """Tests for Step 10: Link source_feature_id to feature."""

    def test_source_feature_id_linked(self, adapter):
        """Test that source_feature_id is linked to feature."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.source_feature_id == 42

    def test_different_feature_ids_linked_correctly(self, adapter):
        """Test that different feature IDs are linked correctly."""
        spec1 = adapter.create_testing_spec(feature_id=1)
        spec2 = adapter.create_testing_spec(feature_id=100)

        assert spec1.source_feature_id == 1
        assert spec2.source_feature_id == 100


# =============================================================================
# Step 11: Return static AgentSpec
# =============================================================================

class TestStep11ReturnStaticAgentSpec:
    """Tests for Step 11: Return static AgentSpec."""

    def test_returns_agent_spec(self, adapter):
        """Test that method returns an AgentSpec."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert isinstance(spec, AgentSpec)

    def test_spec_is_complete(self, adapter):
        """Test that returned spec has all required fields."""
        spec = adapter.create_testing_spec(feature_id=42)

        # Required fields
        assert spec.id is not None
        assert spec.name is not None
        assert spec.display_name is not None
        assert spec.objective is not None
        assert spec.task_type is not None
        assert spec.tool_policy is not None
        assert spec.max_turns is not None
        assert spec.timeout_seconds is not None
        assert spec.acceptance_spec is not None

    def test_spec_can_be_serialized(self, adapter):
        """Test that spec can be serialized to dict."""
        spec = adapter.create_testing_spec(feature_id=42)

        spec_dict = spec.to_dict()
        assert isinstance(spec_dict, dict)
        assert spec_dict["task_type"] == "testing"
        assert spec_dict["source_feature_id"] == 42

    def test_spec_has_unique_id(self, adapter):
        """Test that each spec has a unique ID."""
        spec1 = adapter.create_testing_spec(feature_id=42)
        spec2 = adapter.create_testing_spec(feature_id=42)

        assert spec1.id != spec2.id

    def test_spec_name_includes_feature_id(self, adapter):
        """Test that spec name includes feature ID."""
        spec = adapter.create_testing_spec(feature_id=123)
        assert "123" in spec.name

    def test_display_name_includes_testing(self, adapter):
        """Test that display name indicates testing."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert "Testing" in spec.display_name

    def test_icon_is_test_tube(self, adapter):
        """Test that icon is set to test-tube."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.icon == "test-tube"

    def test_tags_include_testing(self, adapter):
        """Test that tags include testing."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert "testing" in spec.tags

    def test_tags_include_legacy(self, adapter):
        """Test that tags include legacy."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert "legacy" in spec.tags


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for StaticSpecAdapter testing spec."""

    def test_full_workflow(self, adapter, sample_feature_steps):
        """Test complete workflow from feature to spec."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_name="User Authentication",
            feature_steps=sample_feature_steps
        )

        # Verify complete spec
        assert spec.task_type == "testing"
        assert spec.source_feature_id == 42
        assert "User Authentication" in spec.display_name

        # Verify read-only tools
        allowed = spec.tool_policy["allowed_tools"]
        assert "Read" in allowed
        assert "Write" not in allowed

        # Verify steps in objective
        for step in sample_feature_steps:
            assert step in spec.objective

        # Verify validators
        validators = spec.acceptance_spec.validators
        assert len(validators) == len(sample_feature_steps) + 1  # +1 for test_complete

    def test_spec_serialization_roundtrip(self, adapter, sample_feature_steps):
        """Test that spec can be serialized and data is preserved."""
        spec = adapter.create_testing_spec(
            feature_id=42,
            feature_steps=sample_feature_steps
        )

        spec_dict = spec.to_dict()
        acceptance_dict = spec.acceptance_spec.to_dict()

        # Verify key data preserved
        assert spec_dict["task_type"] == "testing"
        assert spec_dict["source_feature_id"] == 42
        assert spec_dict["context"]["feature_steps"] == sample_feature_steps

        # Verify validators preserved
        assert len(acceptance_dict["validators"]) == len(sample_feature_steps) + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
