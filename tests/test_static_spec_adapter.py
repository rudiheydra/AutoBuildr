#!/usr/bin/env python3
"""
Unit tests for StaticSpecAdapter module.

Tests cover:
- StaticSpecAdapter class initialization
- create_initializer_spec() method
- create_coding_spec() method
- create_testing_spec() method
- Tool policy configuration
- AcceptanceSpec creation
- Template loading and interpolation
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
    INITIALIZER_TOOLS,
    CODING_TOOLS,
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


# =============================================================================
# StaticSpecAdapter Initialization Tests
# =============================================================================

class TestStaticSpecAdapterInit:
    """Tests for StaticSpecAdapter initialization."""

    def test_init_default(self, adapter):
        """Test default initialization."""
        assert adapter is not None
        assert adapter.prompts_dir.exists()
        assert adapter.registry is not None

    def test_init_with_custom_prompts_dir(self, tmp_path):
        """Test initialization with custom prompts directory."""
        # Create a temporary prompts directory with a template
        (tmp_path / "test_prompt.md").write_text("# Test Template\nContent here")

        adapter = StaticSpecAdapter(prompts_dir=tmp_path)
        assert adapter.prompts_dir == tmp_path

    def test_prompts_dir_property(self, adapter):
        """Test prompts_dir property returns correct path."""
        assert isinstance(adapter.prompts_dir, Path)
        assert adapter.prompts_dir.is_absolute()

    def test_registry_property(self, adapter):
        """Test registry property returns TemplateRegistry."""
        from api.template_registry import TemplateRegistry
        assert isinstance(adapter.registry, TemplateRegistry)


# =============================================================================
# create_initializer_spec Tests
# =============================================================================

class TestCreateInitializerSpec:
    """Tests for create_initializer_spec method."""

    def test_returns_agent_spec(self, adapter):
        """Test that method returns an AgentSpec."""
        spec = adapter.create_initializer_spec()
        assert isinstance(spec, AgentSpec)

    def test_default_values(self, adapter):
        """Test default values when called without arguments."""
        spec = adapter.create_initializer_spec()

        assert spec.task_type == "custom"
        assert spec.max_turns == DEFAULT_BUDGETS["initializer"]["max_turns"]
        assert spec.timeout_seconds == DEFAULT_BUDGETS["initializer"]["timeout_seconds"]
        assert "initializer" in spec.name
        assert spec.icon == "rocket"

    def test_with_project_name(self, adapter):
        """Test with custom project name."""
        spec = adapter.create_initializer_spec(project_name="MyApp")

        assert "MyApp" in spec.display_name
        assert "myapp" in spec.name.lower()
        assert spec.context["project_name"] == "MyApp"

    def test_with_feature_count(self, adapter):
        """Test with custom feature count."""
        spec = adapter.create_initializer_spec(feature_count=150)

        assert spec.context["expected_feature_count"] == 150

        # Verify acceptance spec has correct count
        validator = next(
            v for v in spec.acceptance_spec.validators
            if v["config"].get("check_type") == "feature_count"
        )
        assert validator["config"]["expected_count"] == 150

    def test_with_custom_spec_id(self, adapter):
        """Test with custom spec ID."""
        custom_id = "test-spec-id-12345"
        spec = adapter.create_initializer_spec(spec_id=custom_id)

        assert spec.id == custom_id

    def test_with_extra_context(self, adapter):
        """Test with extra context."""
        extra = {"custom_key": "custom_value", "another_key": 42}
        spec = adapter.create_initializer_spec(extra_context=extra)

        assert spec.context["custom_key"] == "custom_value"
        assert spec.context["another_key"] == 42

    def test_objective_from_template(self, adapter):
        """Test that objective is loaded from template."""
        spec = adapter.create_initializer_spec()

        # Should contain content from initializer_prompt.md
        assert len(spec.objective) > 100
        assert "INITIALIZER" in spec.objective.upper() or "feature" in spec.objective.lower()

    def test_tool_policy_structure(self, adapter):
        """Test tool policy has correct structure."""
        spec = adapter.create_initializer_spec()

        policy = spec.tool_policy
        assert policy["policy_version"] == "v1"
        assert isinstance(policy["allowed_tools"], list)
        assert isinstance(policy["forbidden_patterns"], list)
        assert isinstance(policy["tool_hints"], dict)

    def test_allowed_tools_for_initializer(self, adapter):
        """Test that initializer has correct allowed tools."""
        spec = adapter.create_initializer_spec()

        allowed = spec.tool_policy["allowed_tools"]

        # Must have feature creation tools
        assert "feature_create" in allowed
        assert "feature_create_bulk" in allowed
        assert "feature_get_stats" in allowed

        # Must have file tools for project setup
        assert "Read" in allowed
        assert "Write" in allowed
        assert "Bash" in allowed

    def test_forbidden_patterns(self, adapter):
        """Test that forbidden patterns are set."""
        spec = adapter.create_initializer_spec()

        forbidden = spec.tool_policy["forbidden_patterns"]
        assert len(forbidden) > 0

        # Should block dangerous operations
        patterns_str = " ".join(forbidden)
        assert "rm" in patterns_str.lower() or "delete" in patterns_str.lower()

    def test_acceptance_spec_created(self, adapter):
        """Test that acceptance spec is created and linked."""
        spec = adapter.create_initializer_spec()

        assert spec.acceptance_spec is not None
        assert isinstance(spec.acceptance_spec, AcceptanceSpec)
        assert spec.acceptance_spec.agent_spec_id == spec.id

    def test_acceptance_validators(self, adapter):
        """Test acceptance spec validators."""
        spec = adapter.create_initializer_spec(feature_count=85)

        validators = spec.acceptance_spec.validators
        assert len(validators) > 0

        # Should have feature_count validator
        feature_count_v = next(
            (v for v in validators if v["config"].get("check_type") == "feature_count"),
            None
        )
        assert feature_count_v is not None
        assert feature_count_v["required"] == True

    def test_tags_include_legacy(self, adapter):
        """Test that tags include legacy identifier."""
        spec = adapter.create_initializer_spec()

        assert "legacy" in spec.tags or "initializer" in spec.tags

    def test_spec_version(self, adapter):
        """Test spec version is v1."""
        spec = adapter.create_initializer_spec()

        assert spec.spec_version == "v1"


# =============================================================================
# create_coding_spec Tests
# =============================================================================

class TestCreateCodingSpec:
    """Tests for create_coding_spec method."""

    def test_returns_agent_spec(self, adapter):
        """Test that method returns an AgentSpec."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert isinstance(spec, AgentSpec)

    def test_task_type_is_coding(self, adapter):
        """Test task_type is set to coding."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.task_type == "coding"

    def test_links_to_source_feature(self, adapter):
        """Test that spec links to source feature."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.source_feature_id == 42

    def test_with_feature_name(self, adapter):
        """Test with custom feature name."""
        spec = adapter.create_coding_spec(
            feature_id=42,
            feature_name="User Authentication"
        )

        assert "User Authentication" in spec.display_name
        assert spec.context["feature_name"] == "User Authentication"

    def test_budget_values(self, adapter):
        """Test coding agent budget values."""
        spec = adapter.create_coding_spec(feature_id=42)

        assert spec.max_turns == DEFAULT_BUDGETS["coding"]["max_turns"]
        assert spec.timeout_seconds == DEFAULT_BUDGETS["coding"]["timeout_seconds"]

    def test_allowed_tools_for_coding(self, adapter):
        """Test that coding agent has correct tools."""
        spec = adapter.create_coding_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]

        # Must have editing tools
        assert "Read" in allowed
        assert "Write" in allowed
        assert "Edit" in allowed

        # Must have browser automation
        assert "browser_navigate" in allowed
        assert "browser_click" in allowed

        # Must have feature management
        assert "feature_mark_passing" in allowed
        assert "feature_mark_in_progress" in allowed

    def test_icon_is_code(self, adapter):
        """Test icon is set to code."""
        spec = adapter.create_coding_spec(feature_id=42)
        assert spec.icon == "code"

    def test_acceptance_spec_with_retry(self, adapter):
        """Test acceptance spec has retry policy."""
        spec = adapter.create_coding_spec(feature_id=42)

        assert spec.acceptance_spec.retry_policy == "fixed"
        assert spec.acceptance_spec.max_retries >= 1


# =============================================================================
# create_testing_spec Tests
# =============================================================================

class TestCreateTestingSpec:
    """Tests for create_testing_spec method."""

    def test_returns_agent_spec(self, adapter):
        """Test that method returns an AgentSpec."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert isinstance(spec, AgentSpec)

    def test_task_type_is_testing(self, adapter):
        """Test task_type is set to testing."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.task_type == "testing"

    def test_budget_is_shorter(self, adapter):
        """Test testing agent has shorter budget than coding."""
        spec = adapter.create_testing_spec(feature_id=42)

        assert spec.max_turns == DEFAULT_BUDGETS["testing"]["max_turns"]
        assert spec.max_turns < DEFAULT_BUDGETS["coding"]["max_turns"]

    def test_no_edit_tool(self, adapter):
        """Test testing agent doesn't have Edit tool (read-only)."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        # Testing should be more restrictive
        # Should not have Write tool (testing shouldn't modify code)
        assert "Write" not in allowed

    def test_has_browser_tools(self, adapter):
        """Test testing agent has browser automation tools."""
        spec = adapter.create_testing_spec(feature_id=42)

        allowed = spec.tool_policy["allowed_tools"]
        assert "browser_navigate" in allowed
        assert "browser_snapshot" in allowed

    def test_context_has_test_mode(self, adapter):
        """Test context indicates test mode."""
        spec = adapter.create_testing_spec(feature_id=42)

        assert spec.context.get("test_mode") == True

    def test_icon_is_test_tube(self, adapter):
        """Test icon is set to test-tube."""
        spec = adapter.create_testing_spec(feature_id=42)
        assert spec.icon == "test-tube"


# =============================================================================
# Module-level Functions Tests
# =============================================================================

class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_static_spec_adapter(self):
        """Test get_static_spec_adapter returns singleton."""
        adapter1 = get_static_spec_adapter()
        adapter2 = get_static_spec_adapter()

        assert adapter1 is adapter2

    def test_reset_static_spec_adapter(self):
        """Test reset clears the singleton."""
        adapter1 = get_static_spec_adapter()
        reset_static_spec_adapter()
        adapter2 = get_static_spec_adapter()

        assert adapter1 is not adapter2


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_initializer_tools_non_empty(self):
        """Test INITIALIZER_TOOLS is not empty."""
        assert len(INITIALIZER_TOOLS) > 0

    def test_coding_tools_non_empty(self):
        """Test CODING_TOOLS is not empty."""
        assert len(CODING_TOOLS) > 0

    def test_testing_tools_non_empty(self):
        """Test TESTING_TOOLS is not empty."""
        assert len(TESTING_TOOLS) > 0

    def test_forbidden_patterns_non_empty(self):
        """Test FORBIDDEN_PATTERNS is not empty."""
        assert len(FORBIDDEN_PATTERNS) > 0

    def test_default_budgets_has_all_types(self):
        """Test DEFAULT_BUDGETS has entries for all agent types."""
        assert "initializer" in DEFAULT_BUDGETS
        assert "coding" in DEFAULT_BUDGETS
        assert "testing" in DEFAULT_BUDGETS

    def test_budget_structure(self):
        """Test budget entries have required fields."""
        for agent_type, budget in DEFAULT_BUDGETS.items():
            assert "max_turns" in budget, f"{agent_type} missing max_turns"
            assert "timeout_seconds" in budget, f"{agent_type} missing timeout_seconds"
            assert budget["max_turns"] > 0
            assert budget["timeout_seconds"] > 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for StaticSpecAdapter."""

    def test_spec_can_be_serialized(self, adapter):
        """Test that created specs can be serialized to dict."""
        spec = adapter.create_initializer_spec(project_name="TestApp")

        spec_dict = spec.to_dict()
        assert isinstance(spec_dict, dict)
        assert spec_dict["name"] == spec.name
        assert spec_dict["task_type"] == spec.task_type

    def test_acceptance_spec_can_be_serialized(self, adapter):
        """Test that acceptance spec can be serialized."""
        spec = adapter.create_initializer_spec()

        acceptance_dict = spec.acceptance_spec.to_dict()
        assert isinstance(acceptance_dict, dict)
        assert acceptance_dict["agent_spec_id"] == spec.id

    def test_multiple_specs_have_unique_ids(self, adapter):
        """Test that multiple specs have unique IDs."""
        spec1 = adapter.create_initializer_spec()
        spec2 = adapter.create_initializer_spec()
        spec3 = adapter.create_coding_spec(feature_id=1)

        ids = [spec1.id, spec2.id, spec3.id]
        assert len(set(ids)) == len(ids), "All specs should have unique IDs"

    def test_all_agent_types_can_be_created(self, adapter):
        """Test that all agent types can be created."""
        initializer = adapter.create_initializer_spec()
        coding = adapter.create_coding_spec(feature_id=42)
        testing = adapter.create_testing_spec(feature_id=42)

        assert initializer.task_type == "custom"
        assert coding.task_type == "coding"
        assert testing.task_type == "testing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
