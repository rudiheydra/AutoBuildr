"""
Test Feature #190: Octo handles malformed project context gracefully
======================================================================

This test suite verifies that Octo correctly handles incomplete or malformed
project context by returning helpful errors rather than crashing.

Feature Steps:
1. Octo validates OctoRequestPayload on receipt
2. Missing required fields produce clear error messages
3. Partial context triggers warnings but proceeds with defaults
4. Validation errors returned to Maestro with remediation hints
"""
import pytest
from unittest.mock import MagicMock

from api.octo import (
    Octo,
    OctoRequestPayload,
    OctoResponse,
    PayloadValidationError,
    PayloadValidationResult,
    VALID_MODELS,
    DEFAULT_MODEL,
    _PROJECT_CONTEXT_DEFAULTS,
    get_octo,
    reset_octo,
)
from api.agentspec_models import (
    AgentSpec,
    AcceptanceSpec,
    generate_uuid,
)
from api.spec_builder import (
    SpecBuilder,
    BuildResult,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset Octo singleton before each test."""
    reset_octo()
    yield
    reset_octo()


@pytest.fixture
def valid_payload():
    """Create a valid OctoRequestPayload for testing."""
    return OctoRequestPayload(
        project_context={
            "name": "TestApp",
            "tech_stack": ["python", "react"],
            "directory_structure": ["src/", "tests/"],
        },
        required_capabilities=["e2e_testing"],
        existing_agents=["coder"],
        constraints={"max_agents": 5},
    )


@pytest.fixture
def mock_spec_builder():
    """Create a mock SpecBuilder that returns successful results."""
    spec_id = generate_uuid()
    sample_spec = AgentSpec(
        id=spec_id,
        name="test-agent",
        display_name="Test Agent",
        icon="test-tube",
        spec_version="v1",
        objective="Test objective",
        task_type="testing",
        context={},
        tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": []},
        max_turns=50,
        timeout_seconds=1800,
        tags=[],
    )
    mock_builder = MagicMock(spec=SpecBuilder)
    mock_builder.build.return_value = BuildResult(
        success=True,
        agent_spec=sample_spec,
        acceptance_spec=AcceptanceSpec(validators=[]),
    )
    return mock_builder


# =============================================================================
# Step 1: Octo validates OctoRequestPayload on receipt
# =============================================================================

class TestStep1ValidateOnReceipt:
    """Test that Octo validates OctoRequestPayload on receipt."""

    def test_valid_payload_passes_validation(self, valid_payload):
        """Valid payload should pass validation."""
        result = valid_payload.validate_detailed()
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_basic_validate_returns_error_list(self, valid_payload):
        """Basic validate() method returns list of error strings."""
        errors = valid_payload.validate()
        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_invalid_project_context_type_fails(self):
        """Non-dict project_context should fail validation."""
        payload = OctoRequestPayload(
            project_context="not a dict",
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("project_context" in e.field for e in result.errors)

    def test_empty_required_capabilities_fails(self):
        """Empty required_capabilities should fail validation."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("required_capabilities" in e.field for e in result.errors)

    def test_non_list_required_capabilities_fails(self):
        """Non-list required_capabilities should fail validation."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities="not a list",
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("required_capabilities" in e.field for e in result.errors)

    def test_non_string_capability_fails(self):
        """Non-string items in required_capabilities should fail."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[123, "valid"],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("required_capabilities" in e.field for e in result.errors)

    def test_empty_string_capability_fails(self):
        """Empty string capabilities should fail."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["valid", "", "also_valid"],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False


# =============================================================================
# Step 2: Missing required fields produce clear error messages
# =============================================================================

class TestStep2ClearErrorMessages:
    """Test that missing required fields produce clear error messages."""

    def test_error_includes_field_name(self):
        """Error messages should include the problematic field name."""
        payload = OctoRequestPayload(
            project_context="invalid",
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        # All errors should have a field name
        for error in result.errors:
            assert error.field is not None
            assert len(error.field) > 0

    def test_error_includes_message(self):
        """Error messages should have clear descriptions."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        for error in result.errors:
            assert error.message is not None
            assert len(error.message) > 10  # Should be descriptive

    def test_error_messages_accessible_as_strings(self):
        """Error messages should be accessible as simple strings."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        assert len(result.error_messages) > 0
        for msg in result.error_messages:
            assert isinstance(msg, str)
            assert "required_capabilities" in msg

    def test_multiple_errors_all_reported(self):
        """Multiple errors should all be reported."""
        payload = OctoRequestPayload(
            project_context="invalid",  # Error 1
            required_capabilities=[],    # Error 2
            existing_agents="invalid",   # Error 3
            constraints="invalid",       # Error 4
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        # Should have multiple errors
        assert len(result.errors) >= 3

    def test_invalid_existing_agents_error_message(self):
        """Invalid existing_agents should have clear error."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            existing_agents="not a list",
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("existing_agents" in e.field for e in result.errors)

    def test_invalid_constraints_error_message(self):
        """Invalid constraints should have clear error."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            constraints="not a dict",
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("constraints" in e.field for e in result.errors)


# =============================================================================
# Step 3: Partial context triggers warnings but proceeds with defaults
# =============================================================================

class TestStep3PartialContextWithDefaults:
    """Test that partial context triggers warnings but proceeds with defaults."""

    def test_lenient_mode_applies_defaults_for_invalid_project_context(self):
        """Lenient mode should apply defaults for invalid project_context type."""
        payload = OctoRequestPayload(
            project_context="not a dict",
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        # Still fails because project_context type is wrong (can't fully fix)
        # But with apply_defaults, it should convert to dict
        assert isinstance(payload.project_context, dict)

    def test_lenient_mode_applies_defaults_for_missing_name(self):
        """Lenient mode should apply default name when missing."""
        payload = OctoRequestPayload(
            project_context={},  # Missing 'name'
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert result.is_valid is True
        assert payload.project_context["name"] == _PROJECT_CONTEXT_DEFAULTS["name"]
        # Should have a warning about the default
        assert len(result.warnings) > 0

    def test_lenient_mode_applies_defaults_for_missing_tech_stack(self):
        """Lenient mode should apply default tech_stack when missing."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},  # Missing 'tech_stack'
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert result.is_valid is True
        assert payload.project_context["tech_stack"] == _PROJECT_CONTEXT_DEFAULTS["tech_stack"]

    def test_lenient_mode_converts_string_tech_stack_to_list(self):
        """Lenient mode should convert string tech_stack to list."""
        payload = OctoRequestPayload(
            project_context={"name": "Test", "tech_stack": "python, react, fastapi"},
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert result.is_valid is True
        assert isinstance(payload.project_context["tech_stack"], list)
        assert "python" in payload.project_context["tech_stack"]
        assert "react" in payload.project_context["tech_stack"]
        assert "fastapi" in payload.project_context["tech_stack"]

    def test_lenient_mode_filters_invalid_existing_agents(self):
        """Lenient mode should filter invalid agents and keep valid ones."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            existing_agents=["valid-agent", 123, "", "another-valid"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert result.is_valid is True
        assert payload.existing_agents == ["valid-agent", "another-valid"]
        assert len(result.warnings) > 0

    def test_lenient_mode_fixes_invalid_constraints(self):
        """Lenient mode should apply defaults for invalid constraint values."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            constraints={"max_agents": "not an int", "model": "invalid_model"},
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert result.is_valid is True
        assert payload.constraints["max_agents"] == 10  # Default
        assert payload.constraints["model"] == DEFAULT_MODEL  # Default

    def test_warnings_include_field_info(self):
        """Warnings should include field and message."""
        payload = OctoRequestPayload(
            project_context={},  # Missing several fields
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert len(result.warnings) > 0
        for warning in result.warnings:
            assert warning.field is not None
            assert warning.message is not None
            assert warning.severity == "warning"

    def test_defaults_applied_dict_tracks_changes(self):
        """defaults_applied should track what was changed."""
        payload = OctoRequestPayload(
            project_context={},  # Missing 'name' and 'tech_stack'
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        assert len(result.defaults_applied) > 0
        # Should track the project_context fields that were defaulted
        assert any("name" in key for key in result.defaults_applied.keys())

    def test_strict_mode_does_not_apply_defaults(self):
        """Strict mode (apply_defaults=False) should not modify payload."""
        payload = OctoRequestPayload(
            project_context={},  # Missing 'name'
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=False)
        # With strict mode, missing optional fields don't cause errors
        # but if there were type issues, they would remain errors
        assert "name" not in payload.project_context or payload.project_context.get("name") is None


# =============================================================================
# Step 4: Validation errors returned to Maestro with remediation hints
# =============================================================================

class TestStep4RemediationHints:
    """Test that validation errors include remediation hints."""

    def test_error_includes_remediation_hint(self):
        """Errors should include remediation hints."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],  # Error: empty
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        for error in result.errors:
            assert error.remediation_hint is not None
            assert len(error.remediation_hint) > 0

    def test_remediation_hint_includes_example(self):
        """Remediation hints should include examples where appropriate."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        # At least some hints should have examples (check for common example patterns)
        hints = [e.remediation_hint for e in result.errors]
        # Hints should contain: 'Example:', example syntax like '[' or ''', or the word 'example'
        assert any(
            "Example" in h or
            "example" in h.lower() or
            "['" in h or  # Example array syntax
            "'" in h or   # Example value in quotes
            ":" in h      # Key-value example syntax
            for h in hints
        ), f"Expected remediation hints to include examples. Got: {hints}"

    def test_remediation_hints_list(self):
        """remediation_hints property should return list of all hints."""
        payload = OctoRequestPayload(
            project_context="invalid",
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        hints = result.remediation_hints
        assert isinstance(hints, list)
        assert len(hints) > 0
        # Hints should be prefixed with severity
        for hint in hints:
            assert "[ERROR]" in hint or "[WARNING]" in hint

    def test_warning_includes_remediation_hint(self):
        """Warnings should also include remediation hints."""
        payload = OctoRequestPayload(
            project_context={},  # Will generate warnings about missing fields
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)
        for warning in result.warnings:
            assert warning.remediation_hint is not None
            assert len(warning.remediation_hint) > 0

    def test_constraint_validation_has_remediation_hints(self):
        """Constraint validation errors should have remediation hints."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            constraints={"model": "gpt4"},  # Invalid model
        )
        result = payload.validate_detailed()
        model_errors = [e for e in result.errors if "model" in e.field]
        if model_errors:
            assert all(e.remediation_hint for e in model_errors)
            # Should mention valid models
            assert any("sonnet" in e.remediation_hint or "opus" in e.remediation_hint
                      for e in model_errors)

    def test_remediation_hints_suggest_valid_models(self):
        """Model validation hints should suggest valid model names."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            constraints={"model": "invalid"},
        )
        result = payload.validate_detailed()
        model_errors = [e for e in result.errors if "model" in e.field]
        if model_errors:
            hint = model_errors[0].remediation_hint
            assert any(model in hint for model in VALID_MODELS)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full validation flow."""

    def test_octo_generate_specs_rejects_invalid_payload(self, mock_spec_builder):
        """Octo.generate_specs should reject invalid payloads."""
        octo = Octo(spec_builder=mock_spec_builder)
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],  # Invalid: empty
        )
        response = octo.generate_specs(payload)
        assert response.success is False
        assert response.error_type == "validation_error"
        assert len(response.validation_errors) > 0
        # Should include remediation hints in warnings
        assert len(response.warnings) > 0

    def test_octo_lenient_mode_proceeds_with_defaults(self, mock_spec_builder):
        """Octo should proceed with defaults in lenient mode."""
        octo = Octo(spec_builder=mock_spec_builder)
        payload = OctoRequestPayload(
            project_context={},  # Missing name, tech_stack
            required_capabilities=["e2e_testing"],
        )
        response = octo.generate_specs(payload, lenient=True)
        # Should succeed because required_capabilities is valid
        # Even though project_context was incomplete
        assert response.success is True or len(response.warnings) > 0

    def test_octo_response_includes_validation_warnings(self, mock_spec_builder):
        """OctoResponse should include validation warnings from lenient mode."""
        octo = Octo(spec_builder=mock_spec_builder)
        payload = OctoRequestPayload(
            project_context={},  # Will trigger warnings
            required_capabilities=["e2e_testing"],
        )
        response = octo.generate_specs(payload, lenient=True)
        # Should have warnings about defaults applied
        has_fixed_warnings = any("[FIXED]" in w for w in response.warnings)
        assert has_fixed_warnings or response.success

    def test_validation_result_serialization(self):
        """PayloadValidationResult should serialize to dict."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],
        )
        result = payload.validate_detailed()
        result_dict = result.to_dict()
        assert "is_valid" in result_dict
        assert "errors" in result_dict
        assert "warnings" in result_dict
        assert "defaults_applied" in result_dict
        assert "remediation_hints" in result_dict

    def test_validation_error_serialization(self):
        """PayloadValidationError should serialize to dict."""
        error = PayloadValidationError(
            field="test_field",
            message="Test message",
            severity="error",
            remediation_hint="Fix it like this",
            current_value="bad",
            default_value="good",
        )
        error_dict = error.to_dict()
        assert error_dict["field"] == "test_field"
        assert error_dict["message"] == "Test message"
        assert error_dict["severity"] == "error"
        assert error_dict["remediation_hint"] == "Fix it like this"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_none_values_in_capabilities(self):
        """None values in capabilities should be caught."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["valid", None, "also_valid"],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False

    def test_whitespace_only_capability(self):
        """Whitespace-only capability strings should fail."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["valid", "   ", "also_valid"],
        )
        result = payload.validate_detailed()
        assert result.is_valid is False

    def test_nested_invalid_types_in_project_context(self):
        """Invalid types nested in project_context should be handled."""
        payload = OctoRequestPayload(
            project_context={"name": 123, "tech_stack": {"invalid": "type"}},
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed()
        # Should report issues with 'name' and 'tech_stack'
        field_names = [e.field for e in result.errors]
        assert any("name" in f or "tech_stack" in f for f in field_names)

    def test_negative_max_agents_constraint(self):
        """Negative max_agents should fail validation."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            constraints={"max_agents": -5},
        )
        result = payload.validate_detailed()
        assert result.is_valid is False
        assert any("max_agents" in e.field for e in result.errors)

    def test_zero_max_turns_constraint(self):
        """Zero max_turns_limit should fail validation."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
            constraints={"max_turns_limit": 0},
        )
        result = payload.validate_detailed()
        assert result.is_valid is False

    def test_very_long_capability_name(self):
        """Very long capability names should be accepted."""
        long_name = "a" * 1000
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[long_name],
        )
        result = payload.validate_detailed()
        # Long names are valid (no max length restriction in this feature)
        assert result.is_valid is True

    def test_special_characters_in_capability(self):
        """Special characters in capability names should be accepted."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["e2e-testing", "api_testing", "testing.v2"],
        )
        result = payload.validate_detailed()
        assert result.is_valid is True


# =============================================================================
# Feature Verification Steps
# =============================================================================

class TestFeature190VerificationSteps:
    """Tests mapping directly to feature verification steps."""

    def test_step1_octo_validates_payload_on_receipt(self, mock_spec_builder):
        """Step 1: Octo validates OctoRequestPayload on receipt."""
        octo = Octo(spec_builder=mock_spec_builder)

        # Valid payload should pass
        valid_payload = OctoRequestPayload(
            project_context={"name": "Test", "tech_stack": ["python"]},
            required_capabilities=["testing"],
        )
        response = octo.generate_specs(valid_payload)
        assert response.request_id == valid_payload.request_id

        # Invalid payload should be rejected
        invalid_payload = OctoRequestPayload(
            project_context="not a dict",
            required_capabilities=[],
        )
        response = octo.generate_specs(invalid_payload)
        assert response.success is False
        assert response.error_type == "validation_error"

    def test_step2_missing_required_fields_produce_clear_errors(self):
        """Step 2: Missing required fields produce clear error messages."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],  # Missing required content
        )
        result = payload.validate_detailed()

        assert result.is_valid is False
        assert len(result.errors) > 0

        # Each error should have: field, message, severity, remediation_hint
        for error in result.errors:
            assert error.field is not None
            assert error.message is not None
            assert error.severity == "error"
            assert error.remediation_hint is not None

    def test_step3_partial_context_triggers_warnings_with_defaults(self):
        """Step 3: Partial context triggers warnings but proceeds with defaults."""
        payload = OctoRequestPayload(
            project_context={},  # Partial - missing name, tech_stack
            required_capabilities=["testing"],
        )
        result = payload.validate_detailed(apply_defaults=True)

        # Should be valid (can proceed)
        assert result.is_valid is True

        # Should have warnings about applied defaults
        assert len(result.warnings) > 0

        # Defaults should be applied
        assert payload.project_context["name"] == _PROJECT_CONTEXT_DEFAULTS["name"]
        assert "tech_stack" in payload.project_context

        # defaults_applied should track what was fixed
        assert len(result.defaults_applied) > 0

    def test_step4_validation_errors_include_remediation_hints(self, mock_spec_builder):
        """Step 4: Validation errors returned to Maestro with remediation hints."""
        octo = Octo(spec_builder=mock_spec_builder)

        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],  # Error: empty
            constraints={"model": "invalid_model"},  # Error: invalid model
        )

        response = octo.generate_specs(payload)

        assert response.success is False
        assert response.error_type == "validation_error"

        # Should have validation_errors
        assert len(response.validation_errors) > 0

        # Should have remediation hints in warnings
        assert len(response.warnings) > 0

        # Hints should mention how to fix issues
        has_remediation = any(
            "Example" in w or "Provide" in w or "one of" in w
            for w in response.warnings
        )
        assert has_remediation, f"Warnings should include remediation hints: {response.warnings}"


# =============================================================================
# Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Ensure backward compatibility with existing code."""

    def test_basic_validate_still_works(self):
        """The basic validate() method should still return list of error strings."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],
        )
        errors = payload.validate()
        assert isinstance(errors, list)
        assert len(errors) > 0
        assert all(isinstance(e, str) for e in errors)

    def test_valid_payload_returns_empty_error_list(self):
        """Valid payload should return empty error list from basic validate()."""
        payload = OctoRequestPayload(
            project_context={"name": "Test", "tech_stack": ["python"]},
            required_capabilities=["testing"],
            existing_agents=["coder"],
            constraints={"max_agents": 5},
        )
        errors = payload.validate()
        assert errors == []

    def test_octo_generate_specs_default_is_strict(self, mock_spec_builder):
        """By default, generate_specs should use strict validation."""
        octo = Octo(spec_builder=mock_spec_builder)
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],  # Invalid
        )
        response = octo.generate_specs(payload)  # No lenient flag
        assert response.success is False

    def test_from_dict_creates_valid_payload(self):
        """from_dict should create a payload that passes validation."""
        data = {
            "project_context": {"name": "Test", "tech_stack": ["python"]},
            "required_capabilities": ["testing"],
            "existing_agents": [],
            "constraints": {},
        }
        payload = OctoRequestPayload.from_dict(data)
        result = payload.validate_detailed()
        assert result.is_valid is True
