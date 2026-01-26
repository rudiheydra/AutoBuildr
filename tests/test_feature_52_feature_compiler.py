"""
Feature #52: Feature to AgentSpec Compiler Tests
=================================================

Comprehensive tests for the FeatureCompiler class that converts Feature
database records into AgentSpecs with derived tool_policy and acceptance
validators.

Verification Steps:
1. Create FeatureCompiler class with compile(feature) -> AgentSpec method
2. Generate spec name from feature: feature-{id}-{slug}
3. Generate display_name from feature name
4. Set objective from feature description
5. Determine task_type from feature category
6. Derive tool_policy based on category conventions
7. Create acceptance validators from feature steps
8. Set source_feature_id for traceability
9. Set priority from feature priority
10. Return complete AgentSpec ready for execution
"""
import pytest
from unittest.mock import MagicMock

from api.feature_compiler import (
    CATEGORY_TO_TASK_TYPE,
    DEFAULT_ICON,
    FeatureCompiler,
    TASK_TYPE_ICONS,
    compile_feature,
    extract_task_type_from_category,
    get_budget_for_task_type,
    get_feature_compiler,
    get_tools_for_task_type,
    reset_feature_compiler,
    slugify,
)
from api.agentspec_models import (
    AcceptanceSpec,
    AgentSpec,
    TASK_TYPES,
)
from api.static_spec_adapter import (
    CODING_TOOLS,
    TESTING_TOOLS,
    FORBIDDEN_PATTERNS,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_feature():
    """Create a mock Feature for testing."""
    feature = MagicMock()
    feature.id = 42
    feature.priority = 10
    feature.category = "A. Database"
    feature.name = "Create User Table Schema"
    feature.description = "Implement the users table with proper columns and constraints."
    feature.steps = [
        "Define User SQLAlchemy model",
        "Add id, email, password_hash columns",
        "Create migration script",
    ]
    feature.passes = False
    feature.in_progress = False
    feature.dependencies = [1, 2]
    return feature


@pytest.fixture
def mock_feature_testing():
    """Create a mock Feature for testing-type tasks."""
    feature = MagicMock()
    feature.id = 100
    feature.priority = 50
    feature.category = "B. Testing"
    feature.name = "Unit Tests for Auth Module"
    feature.description = "Write comprehensive unit tests for authentication."
    feature.steps = [
        "Test login with valid credentials",
        "Test login with invalid password",
        "Test password reset flow",
    ]
    feature.passes = False
    feature.in_progress = False
    feature.dependencies = []
    return feature


@pytest.fixture
def mock_feature_ui():
    """Create a mock Feature for UI-type tasks."""
    feature = MagicMock()
    feature.id = 75
    feature.priority = 25
    feature.category = "F. UI-Backend Integration"
    feature.name = "Dashboard Page Component"
    feature.description = "Create the main dashboard page with metrics."
    feature.steps = [
        "Create DashboardPage component",
        "Add metrics widgets",
        "Connect to API endpoints",
    ]
    feature.passes = False
    feature.in_progress = False
    feature.dependencies = [50, 51]
    return feature


@pytest.fixture
def compiler():
    """Create a FeatureCompiler instance."""
    return FeatureCompiler()


@pytest.fixture(autouse=True)
def reset_compiler_singleton():
    """Reset the compiler singleton before and after each test."""
    reset_feature_compiler()
    yield
    reset_feature_compiler()


# =============================================================================
# Step 1: FeatureCompiler class with compile() method
# =============================================================================

class TestStep1CompilerClass:
    """Tests for Step 1: Create FeatureCompiler class with compile() method."""

    def test_compiler_class_exists(self):
        """FeatureCompiler class exists and can be instantiated."""
        compiler = FeatureCompiler()
        assert compiler is not None

    def test_compile_method_exists(self, compiler):
        """compile() method exists on FeatureCompiler."""
        assert hasattr(compiler, 'compile')
        assert callable(compiler.compile)

    def test_compile_returns_agentspec(self, compiler, mock_feature):
        """compile() returns an AgentSpec instance."""
        result = compiler.compile(mock_feature)
        assert isinstance(result, AgentSpec)

    def test_compile_with_custom_spec_id(self, compiler, mock_feature):
        """compile() accepts optional spec_id parameter."""
        custom_id = "custom-test-id-12345"
        result = compiler.compile(mock_feature, spec_id=custom_id)
        assert result.id == custom_id

    def test_compile_generates_uuid_when_no_id(self, compiler, mock_feature):
        """compile() generates UUID when no spec_id provided."""
        result = compiler.compile(mock_feature)
        assert result.id is not None
        assert len(result.id) == 36  # UUID format


# =============================================================================
# Step 2: Generate spec name from feature
# =============================================================================

class TestStep2SpecNameGeneration:
    """Tests for Step 2: Generate spec name from feature."""

    def test_spec_name_format(self, compiler, mock_feature):
        """Spec name follows format: feature-{id}-{slug}."""
        result = compiler.compile(mock_feature)
        assert result.name.startswith("feature-42-")

    def test_spec_name_includes_slug(self, compiler, mock_feature):
        """Spec name includes slugified feature name."""
        result = compiler.compile(mock_feature)
        # "Create User Table Schema" -> "create-user-table-schema"
        assert "create-user-table-schema" in result.name

    def test_slugify_lowercase(self):
        """slugify() converts to lowercase."""
        assert slugify("Hello World") == "hello-world"

    def test_slugify_replaces_special_chars(self):
        """slugify() replaces special characters with hyphens."""
        assert slugify("Hello! World?") == "hello-world"
        assert slugify("Test_Name") == "test-name"

    def test_slugify_trims_hyphens(self):
        """slugify() removes leading/trailing hyphens."""
        assert slugify("  Hello World  ") == "hello-world"
        assert slugify("---test---") == "test"

    def test_slugify_max_length(self):
        """slugify() respects max_length parameter."""
        long_name = "a" * 100
        result = slugify(long_name, max_length=20)
        assert len(result) <= 20


# =============================================================================
# Step 3: Generate display_name from feature name
# =============================================================================

class TestStep3DisplayNameGeneration:
    """Tests for Step 3: Generate display_name from feature name."""

    def test_display_name_is_feature_name(self, compiler, mock_feature):
        """display_name is set to feature name."""
        result = compiler.compile(mock_feature)
        assert result.display_name == mock_feature.name

    def test_display_name_preserved_with_special_chars(self, compiler, mock_feature):
        """display_name preserves original feature name with special chars."""
        mock_feature.name = "User Authentication (OAuth2)"
        result = compiler.compile(mock_feature)
        assert result.display_name == "User Authentication (OAuth2)"


# =============================================================================
# Step 4: Set objective from feature description
# =============================================================================

class TestStep4ObjectiveFromDescription:
    """Tests for Step 4: Set objective from feature description."""

    def test_objective_contains_description(self, compiler, mock_feature):
        """objective contains the feature description."""
        result = compiler.compile(mock_feature)
        assert mock_feature.description in result.objective

    def test_objective_contains_feature_name(self, compiler, mock_feature):
        """objective contains the feature name."""
        result = compiler.compile(mock_feature)
        assert mock_feature.name in result.objective

    def test_objective_contains_steps(self, compiler, mock_feature):
        """objective contains the feature steps."""
        result = compiler.compile(mock_feature)
        for step in mock_feature.steps:
            assert step in result.objective

    def test_objective_format(self, compiler, mock_feature):
        """objective follows expected format with sections."""
        result = compiler.compile(mock_feature)
        assert "## Objective:" in result.objective
        assert "## Verification Steps" in result.objective


# =============================================================================
# Step 5: Determine task_type from feature category
# =============================================================================

class TestStep5TaskTypeFromCategory:
    """Tests for Step 5: Determine task_type from feature category."""

    def test_database_category_maps_to_coding(self, compiler, mock_feature):
        """Database category maps to coding task_type."""
        mock_feature.category = "A. Database"
        result = compiler.compile(mock_feature)
        assert result.task_type == "coding"

    def test_testing_category_maps_to_testing(self, compiler, mock_feature_testing):
        """Testing category maps to testing task_type."""
        result = compiler.compile(mock_feature_testing)
        assert result.task_type == "testing"

    def test_ui_category_maps_to_coding(self, compiler, mock_feature_ui):
        """UI category maps to coding task_type."""
        result = compiler.compile(mock_feature_ui)
        assert result.task_type == "coding"

    def test_extract_task_type_removes_prefix(self):
        """extract_task_type_from_category() removes letter prefixes."""
        assert extract_task_type_from_category("A. Database") == "coding"
        assert extract_task_type_from_category("B. Testing") == "testing"
        assert extract_task_type_from_category("Z. Documentation") == "documentation"

    def test_extract_task_type_case_insensitive(self):
        """extract_task_type_from_category() is case insensitive."""
        assert extract_task_type_from_category("DATABASE") == "coding"
        assert extract_task_type_from_category("testing") == "testing"
        assert extract_task_type_from_category("DOCUMENTATION") == "documentation"

    def test_extract_task_type_defaults_to_coding(self):
        """Unknown categories default to coding."""
        assert extract_task_type_from_category("Unknown Category") == "coding"
        assert extract_task_type_from_category("X. Random Stuff") == "coding"

    def test_category_mappings_comprehensive(self):
        """Test various category mappings."""
        test_cases = [
            ("API", "coding"),
            ("Endpoint", "coding"),
            ("Backend", "coding"),
            ("Frontend", "coding"),
            ("Component", "coding"),
            ("Test", "testing"),
            ("Verification", "testing"),
            ("QA", "testing"),
            ("Docs", "documentation"),
            ("README", "documentation"),
            ("Refactor", "refactoring"),
            ("Cleanup", "refactoring"),
            ("Audit", "audit"),
            ("Security", "audit"),
            ("Workflow", "coding"),
            ("Feature", "coding"),
        ]
        for category, expected_type in test_cases:
            result = extract_task_type_from_category(category)
            assert result == expected_type, f"Expected {category} -> {expected_type}, got {result}"


# =============================================================================
# Step 6: Derive tool_policy based on category conventions
# =============================================================================

class TestStep6ToolPolicyDerivation:
    """Tests for Step 6: Derive tool_policy based on category conventions."""

    def test_tool_policy_is_dict(self, compiler, mock_feature):
        """tool_policy is a dictionary."""
        result = compiler.compile(mock_feature)
        assert isinstance(result.tool_policy, dict)

    def test_tool_policy_has_required_keys(self, compiler, mock_feature):
        """tool_policy contains required keys."""
        result = compiler.compile(mock_feature)
        assert "policy_version" in result.tool_policy
        assert "allowed_tools" in result.tool_policy
        assert "forbidden_patterns" in result.tool_policy

    def test_coding_tools_for_coding_task(self, compiler, mock_feature):
        """Coding task_type gets coding tools."""
        result = compiler.compile(mock_feature)
        allowed = result.tool_policy["allowed_tools"]
        # Check for essential coding tools
        assert "Read" in allowed
        assert "Write" in allowed
        assert "Edit" in allowed

    def test_testing_tools_for_testing_task(self, compiler, mock_feature_testing):
        """Testing task_type gets testing tools."""
        result = compiler.compile(mock_feature_testing)
        allowed = result.tool_policy["allowed_tools"]
        # Testing tools should not include Write/Edit
        assert "Read" in allowed
        # But should have browser tools
        assert "browser_navigate" in allowed or "Bash" in allowed

    def test_forbidden_patterns_present(self, compiler, mock_feature):
        """tool_policy includes forbidden patterns for security."""
        result = compiler.compile(mock_feature)
        patterns = result.tool_policy["forbidden_patterns"]
        assert len(patterns) > 0
        # Check for common dangerous patterns
        assert any("rm" in p for p in patterns)

    def test_get_tools_for_task_type(self):
        """get_tools_for_task_type() returns appropriate tools."""
        coding_tools = get_tools_for_task_type("coding")
        testing_tools = get_tools_for_task_type("testing")

        assert "Edit" in coding_tools
        assert len(coding_tools) > 0
        assert len(testing_tools) > 0


# =============================================================================
# Step 7: Create acceptance validators from feature steps
# =============================================================================

class TestStep7AcceptanceValidatorsFromSteps:
    """Tests for Step 7: Create acceptance validators from feature steps."""

    def test_acceptance_spec_created(self, compiler, mock_feature):
        """AcceptanceSpec is created and linked."""
        result = compiler.compile(mock_feature)
        assert result.acceptance_spec is not None
        assert isinstance(result.acceptance_spec, AcceptanceSpec)

    def test_acceptance_spec_linked_to_spec(self, compiler, mock_feature):
        """AcceptanceSpec is linked to AgentSpec."""
        result = compiler.compile(mock_feature)
        assert result.acceptance_spec.agent_spec_id == result.id

    def test_validators_from_steps(self, compiler, mock_feature):
        """Validators created from feature steps."""
        result = compiler.compile(mock_feature)
        validators = result.acceptance_spec.validators
        # Should have one validator per step + feature_passing validator
        assert len(validators) == len(mock_feature.steps) + 1

    def test_step_validators_have_descriptions(self, compiler, mock_feature):
        """Step validators contain step descriptions."""
        result = compiler.compile(mock_feature)
        validators = result.acceptance_spec.validators

        # Find step validators
        step_validators = [v for v in validators if v.get("config", {}).get("name", "").startswith("step_")]

        for i, step in enumerate(mock_feature.steps):
            validator = step_validators[i]
            assert validator["config"]["description"] == step

    def test_feature_passing_validator_included(self, compiler, mock_feature):
        """Feature passing validator is included and required."""
        result = compiler.compile(mock_feature)
        validators = result.acceptance_spec.validators

        feature_validator = None
        for v in validators:
            if v.get("config", {}).get("name") == "feature_passing":
                feature_validator = v
                break

        assert feature_validator is not None
        assert feature_validator["required"] is True
        assert feature_validator["config"]["feature_id"] == mock_feature.id

    def test_gate_mode_is_all_pass(self, compiler, mock_feature):
        """Default gate_mode is all_pass."""
        result = compiler.compile(mock_feature)
        assert result.acceptance_spec.gate_mode == "all_pass"


# =============================================================================
# Step 8: Set source_feature_id for traceability
# =============================================================================

class TestStep8SourceFeatureIdTraceability:
    """Tests for Step 8: Set source_feature_id for traceability."""

    def test_source_feature_id_set(self, compiler, mock_feature):
        """source_feature_id is set to feature.id."""
        result = compiler.compile(mock_feature)
        assert result.source_feature_id == mock_feature.id

    def test_source_feature_id_for_different_features(self, compiler, mock_feature, mock_feature_testing):
        """source_feature_id correctly tracks different features."""
        result1 = compiler.compile(mock_feature)
        result2 = compiler.compile(mock_feature_testing)

        assert result1.source_feature_id == 42
        assert result2.source_feature_id == 100


# =============================================================================
# Step 9: Set priority from feature priority
# =============================================================================

class TestStep9PriorityFromFeature:
    """Tests for Step 9: Set priority from feature priority."""

    def test_priority_set_from_feature(self, compiler, mock_feature):
        """priority is set from feature.priority."""
        result = compiler.compile(mock_feature)
        assert result.priority == mock_feature.priority

    def test_priority_various_values(self, compiler, mock_feature):
        """priority works with various values."""
        for priority in [1, 50, 100, 999]:
            mock_feature.priority = priority
            result = compiler.compile(mock_feature)
            assert result.priority == priority


# =============================================================================
# Step 10: Return complete AgentSpec
# =============================================================================

class TestStep10CompleteAgentSpec:
    """Tests for Step 10: Return complete AgentSpec ready for execution."""

    def test_spec_has_all_required_fields(self, compiler, mock_feature):
        """AgentSpec has all required fields populated."""
        result = compiler.compile(mock_feature)

        # Identity fields
        assert result.id is not None
        assert result.name is not None
        assert result.display_name is not None

        # Execution fields
        assert result.objective is not None
        assert result.task_type is not None
        assert result.tool_policy is not None
        assert result.max_turns > 0
        assert result.timeout_seconds > 0

        # Traceability fields
        assert result.source_feature_id is not None
        assert result.priority is not None

        # Acceptance
        assert result.acceptance_spec is not None

    def test_spec_has_context(self, compiler, mock_feature):
        """AgentSpec has context with feature info."""
        result = compiler.compile(mock_feature)
        assert result.context is not None
        assert result.context["feature_id"] == mock_feature.id
        assert result.context["feature_name"] == mock_feature.name

    def test_spec_has_tags(self, compiler, mock_feature):
        """AgentSpec has relevant tags."""
        result = compiler.compile(mock_feature)
        assert result.tags is not None
        assert len(result.tags) > 0
        assert f"feature-{mock_feature.id}" in result.tags

    def test_spec_icon_set(self, compiler, mock_feature):
        """AgentSpec has icon based on task type."""
        result = compiler.compile(mock_feature)
        assert result.icon is not None
        assert result.icon == "code"  # coding task type

    def test_spec_icon_for_testing(self, compiler, mock_feature_testing):
        """Testing task type gets test-tube icon."""
        result = compiler.compile(mock_feature_testing)
        assert result.icon == "test-tube"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the complete compilation flow."""

    def test_compile_feature_convenience_function(self, mock_feature):
        """compile_feature() convenience function works."""
        result = compile_feature(mock_feature)
        assert isinstance(result, AgentSpec)
        assert result.source_feature_id == mock_feature.id

    def test_get_feature_compiler_singleton(self):
        """get_feature_compiler() returns singleton instance."""
        compiler1 = get_feature_compiler()
        compiler2 = get_feature_compiler()
        assert compiler1 is compiler2

    def test_reset_feature_compiler(self):
        """reset_feature_compiler() clears singleton."""
        compiler1 = get_feature_compiler()
        reset_feature_compiler()
        compiler2 = get_feature_compiler()
        assert compiler1 is not compiler2

    def test_multiple_features_compiled(self, compiler, mock_feature, mock_feature_testing, mock_feature_ui):
        """Multiple features compile successfully."""
        specs = [
            compiler.compile(mock_feature),
            compiler.compile(mock_feature_testing),
            compiler.compile(mock_feature_ui),
        ]

        # All should be valid
        for spec in specs:
            assert isinstance(spec, AgentSpec)

        # All should have unique IDs
        ids = [spec.id for spec in specs]
        assert len(set(ids)) == 3

        # Different task types based on category
        assert specs[0].task_type == "coding"
        assert specs[1].task_type == "testing"
        assert specs[2].task_type == "coding"

    def test_feature_with_no_steps(self, compiler, mock_feature):
        """Features with no steps still compile."""
        mock_feature.steps = []
        result = compiler.compile(mock_feature)
        assert result is not None
        # Should still have feature_passing validator
        assert len(result.acceptance_spec.validators) == 1

    def test_feature_with_none_steps(self, compiler, mock_feature):
        """Features with None steps still compile."""
        mock_feature.steps = None
        result = compiler.compile(mock_feature)
        assert result is not None
        assert len(result.acceptance_spec.validators) == 1


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_feature_with_special_chars_in_name(self, compiler, mock_feature):
        """Features with special characters in name."""
        mock_feature.name = "User's Authentication (v2.0) - OAuth/SAML"
        result = compiler.compile(mock_feature)
        assert "feature-42-" in result.name
        # Slug should be sanitized
        assert "/" not in result.name
        assert "'" not in result.name

    def test_feature_with_very_long_name(self, compiler, mock_feature):
        """Features with very long names get truncated slug."""
        mock_feature.name = "A" * 200
        result = compiler.compile(mock_feature)
        # Name should still be reasonable length
        assert len(result.name) < 100

    def test_feature_with_empty_description(self, compiler, mock_feature):
        """Features with empty description."""
        mock_feature.description = ""
        result = compiler.compile(mock_feature)
        assert result is not None
        assert result.objective is not None

    def test_feature_with_unicode_name(self, compiler, mock_feature):
        """Features with unicode characters."""
        mock_feature.name = "Authentication 认证 System"
        result = compiler.compile(mock_feature)
        assert result is not None
        assert result.display_name == mock_feature.name

    def test_get_budget_for_task_type(self):
        """get_budget_for_task_type() returns appropriate budgets."""
        coding_budget = get_budget_for_task_type("coding")
        testing_budget = get_budget_for_task_type("testing")

        assert coding_budget["max_turns"] > testing_budget["max_turns"]
        assert "timeout_seconds" in coding_budget
        assert "timeout_seconds" in testing_budget


# =============================================================================
# Verification Script Style Tests
# =============================================================================

class TestFeature52VerificationSteps:
    """Tests that directly verify each step of Feature #52."""

    def test_step1_feature_compiler_class_with_compile_method(self):
        """Step 1: Create FeatureCompiler class with compile(feature) -> AgentSpec method."""
        # FeatureCompiler class exists
        assert FeatureCompiler is not None

        # compile method exists and is callable
        compiler = FeatureCompiler()
        assert hasattr(compiler, 'compile')
        assert callable(compiler.compile)

        # Compile returns AgentSpec
        feature = MagicMock()
        feature.id = 1
        feature.priority = 1
        feature.category = "Test"
        feature.name = "Test Feature"
        feature.description = "Test description"
        feature.steps = ["Step 1"]

        result = compiler.compile(feature)
        assert isinstance(result, AgentSpec)

    def test_step2_generate_spec_name(self):
        """Step 2: Generate spec name from feature: feature-{id}-{slug}."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 123
        feature.priority = 1
        feature.category = "Test"
        feature.name = "My Test Feature"
        feature.description = "Description"
        feature.steps = []

        result = compiler.compile(feature)
        assert result.name == "feature-123-my-test-feature"

    def test_step3_generate_display_name(self):
        """Step 3: Generate display_name from feature name."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 1
        feature.priority = 1
        feature.category = "Test"
        feature.name = "User Authentication Module"
        feature.description = "Description"
        feature.steps = []

        result = compiler.compile(feature)
        assert result.display_name == "User Authentication Module"

    def test_step4_set_objective_from_description(self):
        """Step 4: Set objective from feature description."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 1
        feature.priority = 1
        feature.category = "Test"
        feature.name = "Test Feature"
        feature.description = "This is the feature description that explains what to implement."
        feature.steps = ["Step A", "Step B"]

        result = compiler.compile(feature)
        assert feature.description in result.objective
        assert "Step A" in result.objective
        assert "Step B" in result.objective

    def test_step5_determine_task_type_from_category(self):
        """Step 5: Determine task_type from feature category."""
        compiler = FeatureCompiler()

        test_cases = [
            ("A. Database", "coding"),
            ("B. Testing", "testing"),
            ("C. Documentation", "documentation"),
            ("D. Refactoring", "refactoring"),
            ("E. Security Audit", "audit"),
            ("F. UI Integration", "coding"),
        ]

        for category, expected_type in test_cases:
            feature = MagicMock()
            feature.id = 1
            feature.priority = 1
            feature.category = category
            feature.name = "Test"
            feature.description = "Test"
            feature.steps = []

            result = compiler.compile(feature)
            assert result.task_type == expected_type, f"Category '{category}' should map to '{expected_type}', got '{result.task_type}'"

    def test_step6_derive_tool_policy_from_category(self):
        """Step 6: Derive tool_policy based on category conventions."""
        compiler = FeatureCompiler()

        # Coding category
        feature = MagicMock()
        feature.id = 1
        feature.priority = 1
        feature.category = "A. API"
        feature.name = "Test"
        feature.description = "Test"
        feature.steps = []

        result = compiler.compile(feature)
        assert "allowed_tools" in result.tool_policy
        assert "forbidden_patterns" in result.tool_policy
        assert "Edit" in result.tool_policy["allowed_tools"]

        # Testing category
        feature.category = "B. Testing"
        result = compiler.compile(feature)
        # Testing tools are more restrictive
        assert "allowed_tools" in result.tool_policy

    def test_step7_create_acceptance_validators_from_steps(self):
        """Step 7: Create acceptance validators from feature steps."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 42
        feature.priority = 1
        feature.category = "Test"
        feature.name = "Test"
        feature.description = "Test"
        feature.steps = ["Verify login works", "Check error handling", "Test edge cases"]

        result = compiler.compile(feature)
        validators = result.acceptance_spec.validators

        # Should have 3 step validators + 1 feature_passing validator
        assert len(validators) == 4

        # Check step validators
        step_validators = [v for v in validators if v["config"].get("name", "").startswith("step_")]
        assert len(step_validators) == 3
        assert step_validators[0]["config"]["description"] == "Verify login works"
        assert step_validators[1]["config"]["description"] == "Check error handling"
        assert step_validators[2]["config"]["description"] == "Test edge cases"

    def test_step8_set_source_feature_id(self):
        """Step 8: Set source_feature_id for traceability."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 999
        feature.priority = 1
        feature.category = "Test"
        feature.name = "Test"
        feature.description = "Test"
        feature.steps = []

        result = compiler.compile(feature)
        assert result.source_feature_id == 999

    def test_step9_set_priority_from_feature(self):
        """Step 9: Set priority from feature priority."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 1
        feature.priority = 42
        feature.category = "Test"
        feature.name = "Test"
        feature.description = "Test"
        feature.steps = []

        result = compiler.compile(feature)
        assert result.priority == 42

    def test_step10_return_complete_agentspec(self):
        """Step 10: Return complete AgentSpec ready for execution."""
        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 52
        feature.priority = 52
        feature.category = "D. Workflow Completeness"
        feature.name = "Feature to AgentSpec Compiler"
        feature.description = "Convert Feature to AgentSpec."
        feature.steps = ["Step 1", "Step 2"]

        result = compiler.compile(feature)

        # Verify all essential fields are populated
        assert result.id is not None
        assert result.name == "feature-52-feature-to-agentspec-compiler"
        assert result.display_name == "Feature to AgentSpec Compiler"
        assert result.task_type == "coding"
        assert result.objective is not None
        assert "Convert Feature to AgentSpec" in result.objective
        assert result.tool_policy is not None
        assert result.max_turns > 0
        assert result.timeout_seconds > 0
        assert result.source_feature_id == 52
        assert result.priority == 52
        assert result.acceptance_spec is not None
        assert result.context is not None
        assert result.tags is not None
