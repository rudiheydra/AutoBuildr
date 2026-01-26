#!/usr/bin/env python3
"""
Test Suite for Feature #37: StaticSpecAdapter for Legacy Coding Agent
=====================================================================

This test suite verifies all 11 steps specified in Feature #37:

1. Define create_coding_spec(feature_id) method
2. Load coding agent prompt from prompts/
3. Interpolate feature details into objective
4. Set task_type to coding
5. Configure tool_policy with code editing tools
6. Include allowed bash commands from security.py allowlist
7. Set forbidden_patterns for dangerous operations
8. Set max_turns appropriate for implementation
9. Create AcceptanceSpec with test_pass and lint_clean validators
10. Link source_feature_id to feature
11. Return static AgentSpec
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.static_spec_adapter import (
    StaticSpecAdapter,
    CODING_TOOLS,
    FORBIDDEN_PATTERNS,
    DEFAULT_BUDGETS,
    get_static_spec_adapter,
    reset_static_spec_adapter,
)
from api.agentspec_models import (
    AgentSpec,
    AcceptanceSpec,
    VALIDATOR_TYPES,
)


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


# =============================================================================
# Step 1: Define create_coding_spec(feature_id) method
# =============================================================================

class TestStep1CreateCodingSpecMethod:
    """Tests for Step 1: Define create_coding_spec(feature_id) method."""

    def test_method_exists(self, adapter):
        """Test that create_coding_spec method exists."""
        assert hasattr(adapter, 'create_coding_spec')
        assert callable(getattr(adapter, 'create_coding_spec'))

    def test_method_requires_feature_id(self, adapter):
        """Test that feature_id is required parameter."""
        with pytest.raises(TypeError):
            adapter.create_coding_spec()  # Should fail without feature_id

    def test_method_accepts_feature_id(self, adapter):
        """Test that method accepts feature_id parameter."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec is not None

    def test_method_returns_agent_spec(self, adapter):
        """Test that method returns an AgentSpec instance."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert isinstance(spec, AgentSpec)

    def test_method_accepts_optional_parameters(self, adapter):
        """Test that method accepts optional parameters."""
        spec = adapter.create_coding_spec(
            feature_id=42,
            feature_name="Test Feature",
            feature_description="Test description",
            spec_id="custom-spec-id",
            extra_context={"custom_key": "custom_value"},
        )
        assert spec is not None
        assert spec.id == "custom-spec-id"
        assert spec.context["custom_key"] == "custom_value"


# =============================================================================
# Step 2: Load coding agent prompt from prompts/
# =============================================================================

class TestStep2LoadCodingPrompt:
    """Tests for Step 2: Load coding agent prompt from prompts/."""

    def test_objective_loaded_from_template(self, adapter):
        """Test that objective is loaded from template file."""
        spec = adapter.create_coding_spec(feature_id=42)
        # Should contain content from coding_prompt.md
        assert len(spec.objective) > 100

    def test_objective_contains_coding_instructions(self, adapter):
        """Test that objective contains coding-related instructions."""
        spec = adapter.create_coding_spec(feature_id=42)
        objective_lower = spec.objective.lower()
        # Should contain coding-related keywords
        assert any(keyword in objective_lower for keyword in [
            'coding', 'implement', 'feature', 'verify', 'browser'
        ])

    def test_prompts_dir_points_to_prompts_folder(self, adapter):
        """Test that prompts_dir points to prompts/ folder."""
        assert adapter.prompts_dir.exists()
        assert adapter.prompts_dir.name == "prompts" or (adapter.prompts_dir / "coding_prompt.md").exists()


# =============================================================================
# Step 3: Interpolate feature details into objective
# =============================================================================

class TestStep3InterpolateFeatureDetails:
    """Tests for Step 3: Interpolate feature details into objective."""

    def test_feature_id_in_context(self, adapter):
        """Test that feature_id is available in context."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.context["feature_id"] == 42

    def test_feature_name_in_context(self, adapter):
        """Test that feature_name is in context when provided."""
        spec = adapter.create_coding_spec(
            feature_id=42,
            feature_name="User Authentication"
        )
        assert spec.context["feature_name"] == "User Authentication"

    def test_feature_description_in_context(self, adapter):
        """Test that feature_description is in context when provided."""
        spec = adapter.create_coding_spec(
            feature_id=42,
            feature_description="Implement user login with JWT"
        )
        assert spec.context["feature_description"] == "Implement user login with JWT"

    def test_default_feature_name_used(self, adapter):
        """Test that default feature name is used when not provided."""
        spec = adapter.create_coding_spec(feature_id=42)
        # Display name should include feature ID
        assert "42" in spec.display_name


# =============================================================================
# Step 4: Set task_type to coding
# =============================================================================

class TestStep4TaskTypeCoding:
    """Tests for Step 4: Set task_type to coding."""

    def test_task_type_is_coding(self, adapter):
        """Test that task_type is set to 'coding'."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.task_type == "coding"

    def test_task_type_not_other_values(self, adapter):
        """Test that task_type is specifically 'coding', not other values."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.task_type != "testing"
        assert spec.task_type != "custom"
        assert spec.task_type != "refactoring"


# =============================================================================
# Step 5: Configure tool_policy with code editing tools
# =============================================================================

class TestStep5ToolPolicyCodeEditing:
    """Tests for Step 5: Configure tool_policy with code editing tools."""

    def test_tool_policy_has_correct_structure(self, adapter):
        """Test that tool_policy has correct structure."""
        spec = adapter.create_coding_spec(feature_id=42)
        policy = spec.tool_policy

        assert "policy_version" in policy
        assert "allowed_tools" in policy
        assert "forbidden_patterns" in policy
        assert "tool_hints" in policy

    def test_has_read_tool(self, adapter):
        """Test that Read tool is allowed."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert "Read" in spec.tool_policy["allowed_tools"]

    def test_has_write_tool(self, adapter):
        """Test that Write tool is allowed."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert "Write" in spec.tool_policy["allowed_tools"]

    def test_has_edit_tool(self, adapter):
        """Test that Edit tool is allowed."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert "Edit" in spec.tool_policy["allowed_tools"]

    def test_has_glob_tool(self, adapter):
        """Test that Glob tool is allowed."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert "Glob" in spec.tool_policy["allowed_tools"]

    def test_has_grep_tool(self, adapter):
        """Test that Grep tool is allowed."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert "Grep" in spec.tool_policy["allowed_tools"]

    def test_has_browser_tools(self, adapter):
        """Test that browser automation tools are included."""
        spec = adapter.create_coding_spec(feature_id=42)
        allowed = spec.tool_policy["allowed_tools"]

        assert "browser_navigate" in allowed
        assert "browser_click" in allowed
        assert "browser_snapshot" in allowed
        assert "browser_take_screenshot" in allowed


# =============================================================================
# Step 6: Include allowed bash commands from security.py allowlist
# =============================================================================

class TestStep6SecurityAllowlist:
    """Tests for Step 6: Include allowed bash commands from security.py allowlist."""

    def test_bash_tool_is_allowed(self, adapter):
        """Test that Bash tool is included in allowed tools."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert "Bash" in spec.tool_policy["allowed_tools"]

    def test_bash_tool_has_security_hint(self, adapter):
        """Test that Bash tool has security-related hint."""
        spec = adapter.create_coding_spec(feature_id=42)
        hints = spec.tool_policy.get("tool_hints", {})

        assert "Bash" in hints
        hint_text = hints["Bash"].lower()
        # Should mention security restrictions
        assert any(word in hint_text for word in ["security", "allowlist", "restricted", "blocked"])

    def test_tool_hints_mention_allowed_commands(self, adapter):
        """Test that tool hints mention allowed commands like npm, git."""
        spec = adapter.create_coding_spec(feature_id=42)
        hints = spec.tool_policy.get("tool_hints", {})

        bash_hint = hints.get("Bash", "").lower()
        # Should mention common development commands
        assert any(cmd in bash_hint for cmd in ["npm", "git", "pytest", "development"])


# =============================================================================
# Step 7: Set forbidden_patterns for dangerous operations
# =============================================================================

class TestStep7ForbiddenPatterns:
    """Tests for Step 7: Set forbidden_patterns for dangerous operations."""

    def test_forbidden_patterns_exist(self, adapter):
        """Test that forbidden_patterns are set."""
        spec = adapter.create_coding_spec(feature_id=42)
        patterns = spec.tool_policy["forbidden_patterns"]

        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_blocks_rm_rf_root(self, adapter):
        """Test that rm -rf / is blocked."""
        spec = adapter.create_coding_spec(feature_id=42)
        patterns = spec.tool_policy["forbidden_patterns"]
        patterns_str = " ".join(patterns)

        # Should have pattern blocking recursive delete
        assert "rm" in patterns_str.lower() or "delete" in patterns_str.lower()

    def test_blocks_sql_injection(self, adapter):
        """Test that SQL injection patterns are blocked."""
        spec = adapter.create_coding_spec(feature_id=42)
        patterns = spec.tool_policy["forbidden_patterns"]
        patterns_str = " ".join(patterns)

        assert "DROP" in patterns_str or "TABLE" in patterns_str

    def test_blocks_dangerous_shell_patterns(self, adapter):
        """Test that dangerous shell patterns are blocked."""
        spec = adapter.create_coding_spec(feature_id=42)
        patterns = spec.tool_policy["forbidden_patterns"]
        patterns_str = " ".join(patterns)

        # Should block curl|sh style attacks
        assert "sh" in patterns_str or "pipe" in patterns_str.lower() or "|" in patterns_str


# =============================================================================
# Step 8: Set max_turns appropriate for implementation
# =============================================================================

class TestStep8MaxTurns:
    """Tests for Step 8: Set max_turns appropriate for implementation."""

    def test_max_turns_is_set(self, adapter):
        """Test that max_turns is set."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.max_turns is not None
        assert spec.max_turns > 0

    def test_max_turns_appropriate_for_coding(self, adapter):
        """Test that max_turns is appropriate for implementation work."""
        spec = adapter.create_coding_spec(feature_id=42)
        # Coding should have enough turns for implementation
        # DEFAULT_BUDGETS["coding"]["max_turns"] = 150
        assert spec.max_turns >= 50  # Minimum reasonable for implementation
        assert spec.max_turns <= 500  # Maximum allowed by schema

    def test_max_turns_uses_default_budget(self, adapter):
        """Test that max_turns uses the default coding budget."""
        spec = adapter.create_coding_spec(feature_id=42)
        expected = DEFAULT_BUDGETS["coding"]["max_turns"]
        assert spec.max_turns == expected

    def test_timeout_seconds_is_set(self, adapter):
        """Test that timeout_seconds is also set."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.timeout_seconds is not None
        assert spec.timeout_seconds >= 60  # Minimum per schema
        assert spec.timeout_seconds <= 7200  # Maximum per schema


# =============================================================================
# Step 9: Create AcceptanceSpec with test_pass and lint_clean validators
# =============================================================================

class TestStep9AcceptanceSpecValidators:
    """Tests for Step 9: Create AcceptanceSpec with test_pass and lint_clean validators."""

    def test_acceptance_spec_exists(self, adapter):
        """Test that AcceptanceSpec is created and linked."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.acceptance_spec is not None
        assert isinstance(spec.acceptance_spec, AcceptanceSpec)

    def test_acceptance_spec_linked_to_agent_spec(self, adapter):
        """Test that AcceptanceSpec is properly linked."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.acceptance_spec.agent_spec_id == spec.id

    def test_has_test_pass_validator(self, adapter):
        """Test that test_pass validator is included."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        test_pass_validators = [v for v in validators if v["type"] == "test_pass"]
        assert len(test_pass_validators) >= 1

    def test_test_pass_has_command(self, adapter):
        """Test that test_pass validator has a command configured."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        test_pass = next((v for v in validators if v["type"] == "test_pass"), None)
        assert test_pass is not None
        assert "command" in test_pass["config"]
        assert len(test_pass["config"]["command"]) > 0

    def test_has_lint_clean_validator(self, adapter):
        """Test that lint_clean validator is included."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        lint_validators = [v for v in validators if v["type"] == "lint_clean"]
        assert len(lint_validators) >= 1

    def test_lint_clean_has_command(self, adapter):
        """Test that lint_clean validator has a command configured."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        lint_clean = next((v for v in validators if v["type"] == "lint_clean"), None)
        assert lint_clean is not None
        assert "command" in lint_clean["config"]
        assert len(lint_clean["config"]["command"]) > 0

    def test_validators_have_valid_types(self, adapter):
        """Test that all validators have valid types."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        for validator in validators:
            assert validator["type"] in VALIDATOR_TYPES

    def test_has_feature_passing_validator(self, adapter):
        """Test that feature_passing custom validator is still included."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        feature_validators = [
            v for v in validators
            if v["type"] == "custom" and v["config"].get("name") == "feature_passing"
        ]
        assert len(feature_validators) >= 1

    def test_feature_passing_validator_is_required(self, adapter):
        """Test that feature_passing validator is marked as required."""
        spec = adapter.create_coding_spec(feature_id=42)
        validators = spec.acceptance_spec.validators

        feature_validator = next(
            (v for v in validators if v.get("config", {}).get("name") == "feature_passing"),
            None
        )
        assert feature_validator is not None
        assert feature_validator.get("required") == True


# =============================================================================
# Step 10: Link source_feature_id to feature
# =============================================================================

class TestStep10SourceFeatureId:
    """Tests for Step 10: Link source_feature_id to feature."""

    def test_source_feature_id_is_set(self, adapter):
        """Test that source_feature_id is set."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.source_feature_id is not None

    def test_source_feature_id_matches_input(self, adapter):
        """Test that source_feature_id matches the input feature_id."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.source_feature_id == 42

    def test_source_feature_id_different_values(self, adapter):
        """Test with different feature_id values."""
        spec1 = adapter.create_coding_spec(feature_id=1)
        spec2 = adapter.create_coding_spec(feature_id=100)
        spec3 = adapter.create_coding_spec(feature_id=999)

        assert spec1.source_feature_id == 1
        assert spec2.source_feature_id == 100
        assert spec3.source_feature_id == 999


# =============================================================================
# Step 11: Return static AgentSpec
# =============================================================================

class TestStep11ReturnAgentSpec:
    """Tests for Step 11: Return static AgentSpec."""

    def test_returns_agent_spec(self, adapter):
        """Test that method returns AgentSpec."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert isinstance(spec, AgentSpec)

    def test_spec_has_unique_id(self, adapter):
        """Test that each spec has a unique ID."""
        spec1 = adapter.create_coding_spec(feature_id=42)
        spec2 = adapter.create_coding_spec(feature_id=42)

        assert spec1.id != spec2.id

    def test_spec_can_be_serialized(self, adapter):
        """Test that spec can be serialized to dict."""
        spec = adapter.create_coding_spec(feature_id=42)
        spec_dict = spec.to_dict()

        assert isinstance(spec_dict, dict)
        assert "id" in spec_dict
        assert "name" in spec_dict
        assert "task_type" in spec_dict
        assert "objective" in spec_dict

    def test_spec_has_icon(self, adapter):
        """Test that spec has icon for UI display."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.icon is not None
        assert spec.icon == "code"

    def test_spec_has_display_name(self, adapter):
        """Test that spec has display_name for UI."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.display_name is not None
        assert len(spec.display_name) > 0

    def test_spec_has_name(self, adapter):
        """Test that spec has machine-readable name."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.name is not None
        assert "coding" in spec.name.lower()
        assert "42" in spec.name

    def test_spec_has_tags(self, adapter):
        """Test that spec has tags for categorization."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.tags is not None
        assert isinstance(spec.tags, list)
        assert "coding" in spec.tags or "legacy" in spec.tags


# =============================================================================
# Integration Tests
# =============================================================================

class TestCodingSpecIntegration:
    """Integration tests for the complete coding spec creation flow."""

    def test_complete_spec_workflow(self, adapter):
        """Test the complete workflow of creating a coding spec."""
        # Create spec with all optional parameters
        spec = adapter.create_coding_spec(
            feature_id=42,
            feature_name="User Authentication",
            feature_description="Implement login with JWT tokens",
            extra_context={"priority": "high"},
        )

        # Verify all 11 steps
        # 1. Method returns result
        assert spec is not None

        # 2. Objective from template
        assert len(spec.objective) > 100

        # 3. Feature details interpolated
        assert spec.context["feature_name"] == "User Authentication"

        # 4. task_type is coding
        assert spec.task_type == "coding"

        # 5. Code editing tools
        assert "Edit" in spec.tool_policy["allowed_tools"]

        # 6. Security hints
        assert "Bash" in spec.tool_policy["tool_hints"]

        # 7. Forbidden patterns
        assert len(spec.tool_policy["forbidden_patterns"]) > 0

        # 8. Appropriate max_turns
        assert spec.max_turns >= 50

        # 9. test_pass and lint_clean validators
        validator_types = [v["type"] for v in spec.acceptance_spec.validators]
        assert "test_pass" in validator_types
        assert "lint_clean" in validator_types

        # 10. source_feature_id linked
        assert spec.source_feature_id == 42

        # 11. Returns AgentSpec
        assert isinstance(spec, AgentSpec)

    def test_spec_matches_security_constants(self, adapter):
        """Test that spec uses the module-level security constants."""
        spec = adapter.create_coding_spec(feature_id=42)

        # Verify tools match CODING_TOOLS constant
        for tool in CODING_TOOLS:
            assert tool in spec.tool_policy["allowed_tools"]

        # Verify forbidden patterns match FORBIDDEN_PATTERNS constant
        for pattern in FORBIDDEN_PATTERNS:
            assert pattern in spec.tool_policy["forbidden_patterns"]


# =============================================================================
# Verification Script Entry Point
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
