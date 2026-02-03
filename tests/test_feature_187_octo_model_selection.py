"""
Tests for Feature #187: Octo selects appropriate model for each agent

This feature ensures that Octo determines the appropriate Claude model
(sonnet, opus, haiku) based on agent complexity and cost considerations.

Feature Steps:
1. Simple/fast agents default to haiku
2. Complex reasoning agents use opus
3. Standard coding agents use sonnet
4. Model selection configurable via project settings
5. Model included in AgentSpec output
"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from api.octo import (
    # Constants
    VALID_MODELS,
    DEFAULT_MODEL,
    HAIKU_CAPABILITIES,
    OPUS_CAPABILITIES,
    TASK_TYPE_MODEL_DEFAULTS,
    COMPLEXITY_INDICATORS,
    # Functions
    select_model_for_capability,
    validate_model,
    get_model_characteristics,
    # Classes
    Octo,
    OctoRequestPayload,
    OctoResponse,
)


# =============================================================================
# Test Step 1: Simple/fast agents default to haiku
# =============================================================================

class TestStep1HaikuDefaultsForSimple:
    """Test that simple/fast agents default to haiku model."""

    def test_documentation_capability_selects_haiku(self):
        """Documentation is a simple capability that should use haiku."""
        model = select_model_for_capability(
            capability="documentation",
            task_type="documentation",
        )
        assert model == "haiku"

    def test_readme_capability_selects_haiku(self):
        """README generation is simple and should use haiku."""
        model = select_model_for_capability(
            capability="readme",
            task_type="documentation",
        )
        assert model == "haiku"

    def test_changelog_capability_selects_haiku(self):
        """Changelog generation is simple and should use haiku."""
        model = select_model_for_capability(
            capability="changelog",
            task_type="documentation",
        )
        assert model == "haiku"

    def test_lint_capability_selects_haiku(self):
        """Linting is a simple task that should use haiku."""
        model = select_model_for_capability(
            capability="lint",
            task_type="audit",
        )
        assert model == "haiku"

    def test_format_capability_selects_haiku(self):
        """Code formatting is simple and should use haiku."""
        model = select_model_for_capability(
            capability="format",
            task_type="coding",
        )
        assert model == "haiku"

    def test_smoke_testing_selects_haiku(self):
        """Smoke testing is a quick check that should use haiku."""
        model = select_model_for_capability(
            capability="smoke_testing",
            task_type="testing",
        )
        assert model == "haiku"

    def test_health_check_selects_haiku(self):
        """Health checks are simple and should use haiku."""
        model = select_model_for_capability(
            capability="health_check",
            task_type="testing",
        )
        assert model == "haiku"

    def test_simple_keyword_triggers_haiku(self):
        """Capability with 'simple' keyword should use haiku."""
        model = select_model_for_capability(
            capability="simple_validation",
            task_type="coding",
        )
        assert model == "haiku"

    def test_quick_keyword_triggers_haiku(self):
        """Capability with 'quick' keyword should use haiku."""
        model = select_model_for_capability(
            capability="quick_test",
            task_type="testing",
        )
        assert model == "haiku"

    def test_fast_keyword_triggers_haiku(self):
        """Capability with 'fast' keyword should use haiku."""
        model = select_model_for_capability(
            capability="fast_audit",
            task_type="audit",
        )
        assert model == "haiku"


# =============================================================================
# Test Step 2: Complex reasoning agents use opus
# =============================================================================

class TestStep2OpusForComplex:
    """Test that complex reasoning agents use opus model."""

    def test_security_audit_selects_opus(self):
        """Security audit is complex and should use opus."""
        model = select_model_for_capability(
            capability="security_audit",
            task_type="audit",
        )
        assert model == "opus"

    def test_vulnerability_analysis_selects_opus(self):
        """Vulnerability analysis is complex and should use opus."""
        model = select_model_for_capability(
            capability="vulnerability_analysis",
            task_type="audit",
        )
        assert model == "opus"

    def test_architecture_design_selects_opus(self):
        """Architecture design requires complex reasoning - opus."""
        model = select_model_for_capability(
            capability="architecture_design",
            task_type="coding",
        )
        assert model == "opus"

    def test_system_design_selects_opus(self):
        """System design is complex and should use opus."""
        model = select_model_for_capability(
            capability="system_design",
            task_type="coding",
        )
        assert model == "opus"

    def test_performance_optimization_selects_opus(self):
        """Performance optimization requires deep analysis - opus."""
        model = select_model_for_capability(
            capability="performance_optimization",
            task_type="refactoring",
        )
        assert model == "opus"

    def test_complex_refactoring_selects_opus(self):
        """Complex refactoring should use opus."""
        model = select_model_for_capability(
            capability="complex_refactoring",
            task_type="refactoring",
        )
        assert model == "opus"

    def test_root_cause_analysis_selects_opus(self):
        """Root cause analysis is complex and should use opus."""
        model = select_model_for_capability(
            capability="root_cause_analysis",
            task_type="audit",
        )
        assert model == "opus"

    def test_distributed_systems_selects_opus(self):
        """Distributed systems work is complex - opus."""
        model = select_model_for_capability(
            capability="distributed_systems",
            task_type="coding",
        )
        assert model == "opus"

    def test_complex_keyword_triggers_opus(self):
        """Capability with 'complex' keyword should use opus."""
        model = select_model_for_capability(
            capability="complex_validation",
            task_type="coding",
        )
        assert model == "opus"

    def test_advanced_keyword_triggers_opus(self):
        """Capability with 'advanced' keyword should use opus."""
        model = select_model_for_capability(
            capability="advanced_testing",
            task_type="testing",
        )
        assert model == "opus"

    def test_comprehensive_keyword_triggers_opus(self):
        """Capability with 'comprehensive' keyword should use opus."""
        model = select_model_for_capability(
            capability="comprehensive_audit",
            task_type="audit",
        )
        assert model == "opus"


# =============================================================================
# Test Step 3: Standard coding agents use sonnet
# =============================================================================

class TestStep3SonnetForCoding:
    """Test that standard coding agents use sonnet model."""

    def test_generic_coding_capability_selects_sonnet(self):
        """Generic coding capability should use sonnet."""
        model = select_model_for_capability(
            capability="feature_implementation",
            task_type="coding",
        )
        assert model == "sonnet"

    def test_testing_capability_selects_sonnet(self):
        """Standard testing should use sonnet."""
        model = select_model_for_capability(
            capability="e2e_testing",
            task_type="testing",
        )
        assert model == "sonnet"

    def test_api_implementation_selects_sonnet(self):
        """API implementation is standard coding - sonnet."""
        model = select_model_for_capability(
            capability="api_implementation",
            task_type="coding",
        )
        assert model == "sonnet"

    def test_ui_development_selects_sonnet(self):
        """UI development is standard coding - sonnet."""
        model = select_model_for_capability(
            capability="ui_development",
            task_type="coding",
        )
        assert model == "sonnet"

    def test_standard_refactoring_selects_sonnet(self):
        """Standard refactoring should use sonnet."""
        model = select_model_for_capability(
            capability="refactoring",
            task_type="refactoring",
        )
        assert model == "sonnet"

    def test_unknown_capability_defaults_to_sonnet(self):
        """Unknown capabilities should default to sonnet."""
        model = select_model_for_capability(
            capability="some_random_capability",
            task_type="coding",
        )
        assert model == "sonnet"

    def test_coding_task_type_default(self):
        """Coding task type defaults to sonnet."""
        assert TASK_TYPE_MODEL_DEFAULTS.get("coding") == "sonnet"

    def test_testing_task_type_default(self):
        """Testing task type defaults to sonnet."""
        assert TASK_TYPE_MODEL_DEFAULTS.get("testing") == "sonnet"


# =============================================================================
# Test Step 4: Model selection configurable via project settings
# =============================================================================

class TestStep4ProjectSettingsOverride:
    """Test that model selection is configurable via project settings."""

    def test_project_settings_model_overrides_default(self):
        """Project settings 'model' key should override default."""
        model = select_model_for_capability(
            capability="documentation",  # Would normally be haiku
            task_type="documentation",
            project_settings={"model": "opus"},
        )
        assert model == "opus"

    def test_project_settings_default_model_key(self):
        """Project settings 'default_model' key should work."""
        model = select_model_for_capability(
            capability="coding",
            task_type="coding",
            project_settings={"default_model": "haiku"},
        )
        assert model == "haiku"

    def test_project_settings_model_preference_key(self):
        """Project settings 'model_preference' key should work."""
        model = select_model_for_capability(
            capability="testing",
            task_type="testing",
            project_settings={"model_preference": "opus"},
        )
        assert model == "opus"

    def test_project_settings_agent_model_key(self):
        """Project settings 'agent_model' key should work."""
        model = select_model_for_capability(
            capability="audit",
            task_type="audit",
            project_settings={"agent_model": "haiku"},
        )
        assert model == "haiku"

    def test_constraints_model_preference_override(self):
        """Constraints model_preference should override task type default."""
        model = select_model_for_capability(
            capability="api_testing",
            task_type="testing",
            constraints={"model_preference": "opus"},
        )
        assert model == "opus"

    def test_project_settings_takes_priority_over_constraints(self):
        """Project settings should take priority over constraints."""
        model = select_model_for_capability(
            capability="coding",
            task_type="coding",
            constraints={"model_preference": "haiku"},
            project_settings={"model": "opus"},
        )
        assert model == "opus"

    def test_invalid_project_settings_model_ignored(self):
        """Invalid model in project settings should be ignored."""
        model = select_model_for_capability(
            capability="documentation",  # Would be haiku
            task_type="documentation",
            project_settings={"model": "invalid_model"},
        )
        assert model == "haiku"

    def test_case_insensitive_model_names(self):
        """Model names should be case insensitive."""
        model = select_model_for_capability(
            capability="coding",
            task_type="coding",
            project_settings={"model": "OPUS"},
        )
        assert model == "opus"


# =============================================================================
# Test Step 5: Model included in AgentSpec output
# =============================================================================

class TestStep5ModelInAgentSpec:
    """Test that model is included in AgentSpec output."""

    @pytest.fixture
    def mock_spec_builder(self):
        """Create a mock SpecBuilder for testing."""
        builder = Mock()

        # Create a mock AgentSpec with realistic attributes
        mock_spec = Mock()
        mock_spec.name = "test-spec"
        mock_spec.task_type = "coding"
        mock_spec.objective = "Test objective"
        mock_spec.context = {}  # Mutable dict
        mock_spec.max_turns = 100
        mock_spec.timeout_seconds = 1800
        mock_spec.tool_policy = {
            "allowed_tools": ["Read", "Write"],
            "forbidden_patterns": [],
        }
        mock_spec.id = "test-id"

        # Create a mock BuildResult
        mock_result = Mock()
        mock_result.success = True
        mock_result.agent_spec = mock_spec

        builder.build.return_value = mock_result

        return builder

    def test_inject_model_into_spec_stores_model(self, mock_spec_builder):
        """Test that _inject_model_into_spec stores the model in context."""
        octo = Octo(spec_builder=mock_spec_builder)

        mock_spec = Mock()
        mock_spec.name = "test-spec"
        mock_spec.context = {}

        octo._inject_model_into_spec(mock_spec, "opus")

        assert mock_spec.context["model"] == "opus"

    def test_inject_model_stores_characteristics(self, mock_spec_builder):
        """Test that _inject_model_into_spec stores model characteristics."""
        octo = Octo(spec_builder=mock_spec_builder)

        mock_spec = Mock()
        mock_spec.name = "test-spec"
        mock_spec.context = {}

        octo._inject_model_into_spec(mock_spec, "opus")

        assert "model_characteristics" in mock_spec.context
        assert mock_spec.context["model_characteristics"]["complexity"] == "high"
        assert mock_spec.context["model_characteristics"]["cost"] == "high"

    def test_inject_model_creates_context_if_none(self, mock_spec_builder):
        """Test that _inject_model_into_spec creates context if None."""
        octo = Octo(spec_builder=mock_spec_builder)

        mock_spec = Mock()
        mock_spec.name = "test-spec"
        mock_spec.context = None

        octo._inject_model_into_spec(mock_spec, "sonnet")

        assert mock_spec.context == {
            "model": "sonnet",
            "model_characteristics": {
                "complexity": "medium",
                "cost": "medium",
                "speed": "balanced",
            },
        }

    def test_model_passed_in_build_context(self, mock_spec_builder):
        """Test that the selected model is passed in the build context."""
        octo = Octo(spec_builder=mock_spec_builder)

        # Create a payload
        payload = OctoRequestPayload(
            project_context={"name": "TestProject"},
            required_capabilities=["security_audit"],
        )

        # Mock _validate_spec to return valid
        with patch.object(octo, '_validate_spec') as mock_validate:
            mock_validate.return_value = Mock(is_valid=True, errors=[])

            octo.generate_specs(payload)

            # Check that build was called with model in context
            call_args = mock_spec_builder.build.call_args
            assert "model" in call_args.kwargs["context"]
            # security_audit should select opus
            assert call_args.kwargs["context"]["model"] == "opus"


# =============================================================================
# Test Constants and Utility Functions
# =============================================================================

class TestConstants:
    """Test constants are correctly defined."""

    def test_valid_models_contains_all_models(self):
        """VALID_MODELS should contain sonnet, opus, haiku."""
        assert "sonnet" in VALID_MODELS
        assert "opus" in VALID_MODELS
        assert "haiku" in VALID_MODELS
        assert len(VALID_MODELS) == 3

    def test_default_model_is_sonnet(self):
        """Default model should be sonnet."""
        assert DEFAULT_MODEL == "sonnet"

    def test_haiku_capabilities_are_simple(self):
        """HAIKU_CAPABILITIES should contain simple task types."""
        assert "documentation" in HAIKU_CAPABILITIES
        assert "smoke_testing" in HAIKU_CAPABILITIES
        assert "lint" in HAIKU_CAPABILITIES

    def test_opus_capabilities_are_complex(self):
        """OPUS_CAPABILITIES should contain complex task types."""
        assert "security_audit" in OPUS_CAPABILITIES
        assert "architecture_design" in OPUS_CAPABILITIES
        assert "performance_optimization" in OPUS_CAPABILITIES

    def test_task_type_model_defaults_complete(self):
        """Task type model defaults should be complete."""
        assert "coding" in TASK_TYPE_MODEL_DEFAULTS
        assert "testing" in TASK_TYPE_MODEL_DEFAULTS
        assert "documentation" in TASK_TYPE_MODEL_DEFAULTS
        assert "audit" in TASK_TYPE_MODEL_DEFAULTS
        assert "refactoring" in TASK_TYPE_MODEL_DEFAULTS


class TestValidateModel:
    """Test the validate_model function."""

    def test_valid_sonnet(self):
        """sonnet should be valid."""
        is_valid, result = validate_model("sonnet")
        assert is_valid
        assert result == "sonnet"

    def test_valid_opus(self):
        """opus should be valid."""
        is_valid, result = validate_model("opus")
        assert is_valid
        assert result == "opus"

    def test_valid_haiku(self):
        """haiku should be valid."""
        is_valid, result = validate_model("haiku")
        assert is_valid
        assert result == "haiku"

    def test_case_insensitive(self):
        """Model validation should be case insensitive."""
        is_valid, result = validate_model("SONNET")
        assert is_valid
        assert result == "sonnet"

    def test_invalid_model(self):
        """Invalid model should return False."""
        is_valid, result = validate_model("gpt-4")
        assert not is_valid
        assert "Invalid model" in result

    def test_empty_model(self):
        """Empty model should return False."""
        is_valid, result = validate_model("")
        assert not is_valid
        assert "cannot be empty" in result


class TestGetModelCharacteristics:
    """Test the get_model_characteristics function."""

    def test_haiku_characteristics(self):
        """Haiku should have low complexity/cost and fast speed."""
        chars = get_model_characteristics("haiku")
        assert chars["name"] == "haiku"
        assert chars["complexity"] == "low"
        assert chars["cost"] == "low"
        assert chars["speed"] == "fast"

    def test_sonnet_characteristics(self):
        """Sonnet should have medium complexity/cost and balanced speed."""
        chars = get_model_characteristics("sonnet")
        assert chars["name"] == "sonnet"
        assert chars["complexity"] == "medium"
        assert chars["cost"] == "medium"
        assert chars["speed"] == "balanced"

    def test_opus_characteristics(self):
        """Opus should have high complexity/cost and slower speed."""
        chars = get_model_characteristics("opus")
        assert chars["name"] == "opus"
        assert chars["complexity"] == "high"
        assert chars["cost"] == "high"
        assert chars["speed"] == "slower"

    def test_has_recommended_budgets(self):
        """Each model should have recommended budgets."""
        for model in ["haiku", "sonnet", "opus"]:
            chars = get_model_characteristics(model)
            assert "recommended_max_turns" in chars
            assert "recommended_timeout_seconds" in chars

    def test_has_use_cases(self):
        """Each model should have use cases."""
        for model in ["haiku", "sonnet", "opus"]:
            chars = get_model_characteristics(model)
            assert "use_cases" in chars
            assert len(chars["use_cases"]) > 0

    def test_unknown_model_defaults_to_sonnet(self):
        """Unknown model should return sonnet characteristics."""
        chars = get_model_characteristics("unknown")
        assert chars["name"] == "sonnet"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for model selection in Octo."""

    @pytest.fixture
    def mock_spec_builder(self):
        """Create a mock SpecBuilder for integration testing."""
        builder = Mock()

        def create_mock_spec(task_description, task_type, context):
            mock_spec = Mock()
            mock_spec.name = f"test-{task_type}"
            mock_spec.task_type = task_type
            mock_spec.objective = task_description
            mock_spec.context = {}
            # Add realistic attributes for constraint validation
            mock_spec.max_turns = 100
            mock_spec.timeout_seconds = 1800
            mock_spec.tool_policy = {
                "allowed_tools": ["Read", "Write"],
                "forbidden_patterns": [],
            }
            mock_spec.id = "test-id"

            mock_result = Mock()
            mock_result.success = True
            mock_result.agent_spec = mock_spec

            return mock_result

        builder.build.side_effect = create_mock_spec
        return builder

    def test_generate_specs_selects_correct_models(self, mock_spec_builder):
        """Test that generate_specs selects correct models for different capabilities."""
        octo = Octo(spec_builder=mock_spec_builder)

        # Create a payload with mixed capabilities
        payload = OctoRequestPayload(
            project_context={"name": "TestProject"},
            required_capabilities=["security_audit", "documentation", "coding"],
        )

        with patch.object(octo, '_validate_spec') as mock_validate:
            mock_validate.return_value = Mock(is_valid=True, errors=[])

            response = octo.generate_specs(payload)

            # Check that build was called with correct models
            calls = mock_spec_builder.build.call_args_list

            # First call should be for security_audit -> opus
            assert calls[0].kwargs["context"]["model"] == "opus"
            # Second call should be for documentation -> haiku
            assert calls[1].kwargs["context"]["model"] == "haiku"
            # Third call should be for coding -> sonnet
            assert calls[2].kwargs["context"]["model"] == "sonnet"

    def test_project_settings_override_in_generate_specs(self, mock_spec_builder):
        """Test that project settings override model selection in generate_specs."""
        octo = Octo(spec_builder=mock_spec_builder)

        # Create a payload with project settings
        payload = OctoRequestPayload(
            project_context={
                "name": "TestProject",
                "settings": {"model": "opus"},  # Override all to opus
            },
            required_capabilities=["documentation"],  # Would normally be haiku
        )

        with patch.object(octo, '_validate_spec') as mock_validate:
            mock_validate.return_value = Mock(is_valid=True, errors=[])

            octo.generate_specs(payload)

            # Check that documentation used opus due to override
            call_args = mock_spec_builder.build.call_args
            assert call_args.kwargs["context"]["model"] == "opus"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases for model selection."""

    def test_empty_capability_uses_task_type_default(self):
        """Empty capability should use task type default."""
        model = select_model_for_capability(
            capability="",
            task_type="coding",
        )
        assert model == "sonnet"

    def test_none_constraints_handled(self):
        """None constraints should be handled gracefully."""
        model = select_model_for_capability(
            capability="coding",
            task_type="coding",
            constraints=None,
        )
        assert model == "sonnet"

    def test_none_project_settings_handled(self):
        """None project settings should be handled gracefully."""
        model = select_model_for_capability(
            capability="coding",
            task_type="coding",
            project_settings=None,
        )
        assert model == "sonnet"

    def test_capability_with_underscores(self):
        """Capability with underscores should be normalized."""
        model = select_model_for_capability(
            capability="security_audit",
            task_type="audit",
        )
        assert model == "opus"

    def test_capability_with_hyphens(self):
        """Capability with hyphens should be normalized."""
        model = select_model_for_capability(
            capability="security-audit",
            task_type="audit",
        )
        assert model == "opus"

    def test_capability_with_spaces(self):
        """Capability with spaces should be normalized."""
        model = select_model_for_capability(
            capability="security audit",
            task_type="audit",
        )
        assert model == "opus"

    def test_mixed_case_capability(self):
        """Mixed case capability should work."""
        model = select_model_for_capability(
            capability="Security_Audit",
            task_type="audit",
        )
        assert model == "opus"


# =============================================================================
# Regression Tests
# =============================================================================

class TestRegressions:
    """Regression tests to prevent feature breakage."""

    def test_existing_octo_functionality_preserved(self):
        """Ensure existing Octo functionality still works."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["coding"],
        )

        # Validate should work
        errors = payload.validate()
        assert len(errors) == 0

    def test_octo_response_structure_unchanged(self):
        """Ensure OctoResponse structure is unchanged."""
        response = OctoResponse(
            success=True,
            agent_specs=[],
            warnings=["test warning"],
            request_id="test-id",
        )

        result_dict = response.to_dict()
        assert "success" in result_dict
        assert "agent_specs" in result_dict
        assert "warnings" in result_dict
        assert "request_id" in result_dict

    def test_api_package_exports(self):
        """Test that new exports are available from api package."""
        from api import (
            OCTO_VALID_MODELS,
            OCTO_DEFAULT_MODEL,
            HAIKU_CAPABILITIES,
            OPUS_CAPABILITIES,
            select_model_for_capability,
            validate_model,
            get_model_characteristics,
        )

        assert OCTO_VALID_MODELS is not None
        assert OCTO_DEFAULT_MODEL == "sonnet"
        assert callable(select_model_for_capability)
        assert callable(validate_model)
        assert callable(get_model_characteristics)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
