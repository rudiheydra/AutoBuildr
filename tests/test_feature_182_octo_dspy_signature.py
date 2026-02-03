"""
Test Suite for Feature #182: Octo DSPy signature for AgentSpec generation
=========================================================================

This test suite verifies the DSPy signature for Octo agent generation from
project context and capabilities.

Feature #182 Requirements:
1. Create SpecGenerationSignature with typed inputs: project_context, capabilities_needed, constraints
2. Define typed outputs: agent_name, role, tools, skills, model, responsibilities, acceptance_contract
3. Include chain-of-thought reasoning field for auditability
4. Signature validates output against AgentSpec schema
"""

import json
import pytest
import re
from typing import get_type_hints
from unittest.mock import MagicMock, patch


# =============================================================================
# Step 1: Create signature with typed inputs
# =============================================================================

class TestStep1TypedInputs:
    """Test that OctoSpecGenerationSignature has typed inputs for project_context, capabilities_needed, constraints."""

    def test_signature_class_exists(self):
        """Step 1: OctoSpecGenerationSignature class exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature
        assert OctoSpecGenerationSignature is not None

    def test_signature_inherits_from_dspy_signature(self):
        """Step 1: OctoSpecGenerationSignature inherits from dspy.Signature."""
        import dspy
        from api.dspy_signatures import OctoSpecGenerationSignature
        assert issubclass(OctoSpecGenerationSignature, dspy.Signature)

    def test_project_context_input_field(self):
        """Step 1: project_context input field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        input_fields = OctoSpecGenerationSignature.input_fields
        assert "project_context" in input_fields

    def test_capabilities_needed_input_field(self):
        """Step 1: capabilities_needed input field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        input_fields = OctoSpecGenerationSignature.input_fields
        assert "capabilities_needed" in input_fields

    def test_constraints_input_field(self):
        """Step 1: constraints input field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        input_fields = OctoSpecGenerationSignature.input_fields
        assert "constraints" in input_fields

    def test_input_fields_are_string_type(self):
        """Step 1: All input fields have string type (for JSON strings)."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        fields = OctoSpecGenerationSignature.model_fields

        for field_name in ["project_context", "capabilities_needed", "constraints"]:
            assert field_name in fields
            field = fields[field_name]
            assert field.annotation == str or str(field.annotation) == "str"

    def test_all_input_fields_present(self):
        """Step 1: Exactly 3 input fields are defined."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        input_fields = OctoSpecGenerationSignature.input_fields
        assert len(input_fields) == 3
        assert set(input_fields.keys()) == {"project_context", "capabilities_needed", "constraints"}


# =============================================================================
# Step 2: Define typed outputs
# =============================================================================

class TestStep2TypedOutputs:
    """Test that typed outputs are defined: agent_name, role, tools, skills, model, responsibilities, acceptance_contract."""

    def test_agent_name_output_field(self):
        """Step 2: agent_name output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "agent_name" in output_fields

    def test_role_output_field(self):
        """Step 2: role output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "role" in output_fields

    def test_tools_json_output_field(self):
        """Step 2: tools_json output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "tools_json" in output_fields

    def test_skills_json_output_field(self):
        """Step 2: skills_json output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "skills_json" in output_fields

    def test_model_output_field(self):
        """Step 2: model output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "model" in output_fields

    def test_responsibilities_json_output_field(self):
        """Step 2: responsibilities_json output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "responsibilities_json" in output_fields

    def test_acceptance_contract_json_output_field(self):
        """Step 2: acceptance_contract_json output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "acceptance_contract_json" in output_fields

    def test_all_required_output_fields_present(self):
        """Step 2: All 8 required output fields are defined (including reasoning)."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields

        required = [
            "reasoning",
            "agent_name",
            "role",
            "tools_json",
            "skills_json",
            "model",
            "responsibilities_json",
            "acceptance_contract_json",
        ]

        for field in required:
            assert field in output_fields, f"Missing output field: {field}"


# =============================================================================
# Step 3: Chain-of-thought reasoning field for auditability
# =============================================================================

class TestStep3ChainOfThoughtReasoning:
    """Test that chain-of-thought reasoning field is present for auditability."""

    def test_reasoning_field_exists(self):
        """Step 3: reasoning output field exists."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        assert "reasoning" in output_fields

    def test_reasoning_is_string_type(self):
        """Step 3: reasoning has string type."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        fields = OctoSpecGenerationSignature.model_fields
        field = fields["reasoning"]
        assert field.annotation == str or "str" in str(field.annotation)

    def test_reasoning_has_description(self):
        """Step 3: reasoning field has a description mentioning auditability."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields
        reasoning_field = output_fields["reasoning"]

        desc = None
        if hasattr(reasoning_field, "json_schema_extra") and reasoning_field.json_schema_extra:
            desc = reasoning_field.json_schema_extra.get("desc") or reasoning_field.json_schema_extra.get("description")

        assert desc is not None
        # Check it mentions reasoning/chain-of-thought/auditability
        assert any(term in desc.lower() for term in ["chain", "reason", "audit", "thinking", "thought"])

    def test_chain_of_thought_module_works(self):
        """Step 3: ChainOfThought module works with signature."""
        import dspy
        from api.dspy_signatures import OctoSpecGenerationSignature

        cot = dspy.ChainOfThought(OctoSpecGenerationSignature)
        assert cot is not None
        assert hasattr(cot, "predict") or hasattr(cot, "signature") or hasattr(cot, "extended_signature")


# =============================================================================
# Step 4: Schema validation for outputs
# =============================================================================

class TestStep4SchemaValidation:
    """Test that signature validates output against AgentSpec schema."""

    def test_validate_octo_spec_output_function_exists(self):
        """Step 4: validate_octo_spec_output function exists."""
        from api.dspy_signatures import validate_octo_spec_output
        assert callable(validate_octo_spec_output)

    def test_validate_returns_dict_with_errors_and_warnings(self):
        """Step 4: validate_octo_spec_output returns dict with errors and warnings."""
        from api.dspy_signatures import validate_octo_spec_output

        # Create valid mock result
        mock_result = MagicMock()
        mock_result.reasoning = "Test reasoning"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Test agent role"
        mock_result.tools_json = '["tool1", "tool2"]'
        mock_result.skills_json = '["skill1"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp1"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": [{"type": "test_pass", "config": {}}]}'

        result = validate_octo_spec_output(mock_result)

        assert isinstance(result, dict)
        assert "errors" in result
        assert "warnings" in result
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)

    def test_validation_detects_invalid_agent_name_format(self):
        """Step 4: Validation detects invalid agent_name format."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "INVALID NAME!!"  # Invalid: uppercase and special chars
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("agent_name" in e for e in result["errors"])

    def test_validation_detects_invalid_model(self):
        """Step 4: Validation detects invalid model value."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "gpt-4"  # Invalid: must be sonnet/opus/haiku
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("model" in e for e in result["errors"])

    def test_validation_detects_invalid_gate_mode(self):
        """Step 4: Validation detects invalid gate_mode in acceptance contract."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "invalid_mode", "validators": []}'  # Invalid gate_mode

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("gate_mode" in e for e in result["errors"])

    def test_validation_detects_invalid_validator_type(self):
        """Step 4: Validation detects invalid validator type."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": [{"type": "invalid_type", "config": {}}]}'

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("validators" in e and "type" in e for e in result["errors"])

    def test_validation_detects_invalid_json(self):
        """Step 4: Validation detects invalid JSON in tools_json."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = "not valid json"  # Invalid JSON
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("tools_json" in e and "JSON" in e for e in result["errors"])

    def test_validation_warns_on_empty_validators(self):
        """Step 4: Validation warns when validators array is empty."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'  # Empty validators

        result = validate_octo_spec_output(mock_result)

        # This should be a warning, not error
        assert any("validators" in w for w in result["warnings"])


# =============================================================================
# Utility Functions Tests
# =============================================================================

class TestUtilityFunctions:
    """Test utility functions for Octo signature."""

    def test_get_octo_spec_generator_exists(self):
        """get_octo_spec_generator function exists."""
        from api.dspy_signatures import get_octo_spec_generator
        assert callable(get_octo_spec_generator)

    def test_get_octo_spec_generator_returns_module(self):
        """get_octo_spec_generator returns a DSPy module."""
        from api.dspy_signatures import get_octo_spec_generator

        generator = get_octo_spec_generator()
        assert generator is not None

    def test_get_octo_spec_generator_with_chain_of_thought_true(self):
        """get_octo_spec_generator with chain of thought returns ChainOfThought."""
        import dspy
        from api.dspy_signatures import get_octo_spec_generator

        generator = get_octo_spec_generator(use_chain_of_thought=True)
        assert isinstance(generator, dspy.ChainOfThought)

    def test_get_octo_spec_generator_with_chain_of_thought_false(self):
        """get_octo_spec_generator without chain of thought returns Predict."""
        import dspy
        from api.dspy_signatures import get_octo_spec_generator

        generator = get_octo_spec_generator(use_chain_of_thought=False)
        assert isinstance(generator, dspy.Predict)

    def test_convert_octo_output_to_agent_spec_dict_exists(self):
        """convert_octo_output_to_agent_spec_dict function exists."""
        from api.dspy_signatures import convert_octo_output_to_agent_spec_dict
        assert callable(convert_octo_output_to_agent_spec_dict)

    def test_convert_produces_valid_spec_dict(self):
        """convert_octo_output_to_agent_spec_dict produces valid spec dictionary."""
        from api.dspy_signatures import convert_octo_output_to_agent_spec_dict

        mock_result = MagicMock()
        mock_result.reasoning = "Test reasoning"
        mock_result.agent_name = "playwright-e2e-tester"
        mock_result.role = "E2E testing agent"
        mock_result.tools_json = '["mcp__playwright__browser_navigate"]'
        mock_result.skills_json = '["e2e_testing", "browser_automation"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["Execute tests", "Capture screenshots"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": [{"type": "test_pass", "config": {"command": "pytest"}}]}'

        spec_dict = convert_octo_output_to_agent_spec_dict(mock_result)

        # Check all required fields
        assert "name" in spec_dict
        assert spec_dict["name"] == "playwright-e2e-tester"
        assert "display_name" in spec_dict
        assert "objective" in spec_dict
        assert "tool_policy" in spec_dict
        assert "acceptance_spec" in spec_dict
        assert "tags" in spec_dict

    def test_convert_derives_icon_from_skills(self):
        """convert_octo_output_to_agent_spec_dict derives icon from skills."""
        from api.dspy_signatures import convert_octo_output_to_agent_spec_dict

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Test agent"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["browser_automation", "e2e_testing"]'  # Should get browser icon
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["test"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        spec_dict = convert_octo_output_to_agent_spec_dict(mock_result)

        assert "icon" in spec_dict
        # Browser-related skills should get browser icon
        assert spec_dict["icon"] in ["🌐", "🧪"]


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Test constants defined for Octo signature."""

    def test_valid_agent_models_exists(self):
        """VALID_AGENT_MODELS constant exists."""
        from api.dspy_signatures import VALID_AGENT_MODELS
        assert VALID_AGENT_MODELS is not None

    def test_valid_agent_models_contains_expected_values(self):
        """VALID_AGENT_MODELS contains sonnet, opus, haiku."""
        from api.dspy_signatures import VALID_AGENT_MODELS

        expected = {"sonnet", "opus", "haiku"}
        assert expected == set(VALID_AGENT_MODELS)

    def test_valid_gate_modes_exists(self):
        """VALID_GATE_MODES constant exists."""
        from api.dspy_signatures import VALID_GATE_MODES
        assert VALID_GATE_MODES is not None

    def test_valid_gate_modes_contains_expected_values(self):
        """VALID_GATE_MODES contains all_pass, any_pass, weighted."""
        from api.dspy_signatures import VALID_GATE_MODES

        expected = {"all_pass", "any_pass", "weighted"}
        assert expected == set(VALID_GATE_MODES)

    def test_valid_octo_validator_types_exists(self):
        """VALID_OCTO_VALIDATOR_TYPES constant exists."""
        from api.dspy_signatures import VALID_OCTO_VALIDATOR_TYPES
        assert VALID_OCTO_VALIDATOR_TYPES is not None

    def test_valid_octo_validator_types_contains_expected_values(self):
        """VALID_OCTO_VALIDATOR_TYPES contains all validator types."""
        from api.dspy_signatures import VALID_OCTO_VALIDATOR_TYPES

        expected = {"test_pass", "file_exists", "lint_clean", "forbidden_patterns", "custom"}
        assert expected == set(VALID_OCTO_VALIDATOR_TYPES)


# =============================================================================
# API Package Integration Tests
# =============================================================================

class TestApiPackageIntegration:
    """Test integration with the api package."""

    def test_signature_exported_from_api_package(self):
        """OctoSpecGenerationSignature is exported from api package."""
        from api import OctoSpecGenerationSignature
        assert OctoSpecGenerationSignature is not None

    def test_get_octo_spec_generator_exported_from_api_package(self):
        """get_octo_spec_generator is exported from api package."""
        from api import get_octo_spec_generator
        assert callable(get_octo_spec_generator)

    def test_validate_octo_spec_output_exported_from_api_package(self):
        """validate_octo_spec_output is exported from api package."""
        from api import validate_octo_spec_output
        assert callable(validate_octo_spec_output)

    def test_convert_octo_output_exported_from_api_package(self):
        """convert_octo_output_to_agent_spec_dict is exported from api package."""
        from api import convert_octo_output_to_agent_spec_dict
        assert callable(convert_octo_output_to_agent_spec_dict)

    def test_valid_agent_models_exported_from_api_package(self):
        """VALID_AGENT_MODELS is exported from api package."""
        from api import VALID_AGENT_MODELS
        assert VALID_AGENT_MODELS is not None

    def test_valid_gate_modes_exported_from_api_package(self):
        """VALID_GATE_MODES is exported from api package."""
        from api import VALID_GATE_MODES
        assert VALID_GATE_MODES is not None

    def test_valid_octo_validator_types_exported_from_api_package(self):
        """VALID_OCTO_VALIDATOR_TYPES is exported from api package."""
        from api import VALID_OCTO_VALIDATOR_TYPES
        assert VALID_OCTO_VALIDATOR_TYPES is not None


# =============================================================================
# Docstring Tests
# =============================================================================

class TestDocstrings:
    """Test that docstrings and field descriptions are present."""

    def test_signature_has_docstring(self):
        """Signature class has a docstring."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        assert OctoSpecGenerationSignature.__doc__ is not None
        assert len(OctoSpecGenerationSignature.__doc__) > 500  # Substantial docstring

    def test_docstring_describes_purpose(self):
        """Docstring describes Octo agent generation purpose."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        docstring = OctoSpecGenerationSignature.__doc__
        assert "Octo" in docstring or "agent" in docstring.lower()
        assert "AgentSpec" in docstring or "spec" in docstring.lower()

    def test_docstring_describes_input_fields(self):
        """Docstring describes input fields."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        docstring = OctoSpecGenerationSignature.__doc__
        assert "project_context" in docstring
        assert "capabilities_needed" in docstring
        assert "constraints" in docstring

    def test_docstring_describes_output_fields(self):
        """Docstring describes output fields."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        docstring = OctoSpecGenerationSignature.__doc__
        assert "agent_name" in docstring
        assert "role" in docstring
        assert "tools" in docstring.lower()

    def test_docstring_includes_example(self):
        """Docstring includes usage example."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        docstring = OctoSpecGenerationSignature.__doc__
        assert "Example" in docstring or ">>>" in docstring


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_agent_name_max_length_validation(self):
        """Validation rejects agent_name > 100 characters."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "a" * 101  # Too long
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("100" in e or "length" in e.lower() for e in result["errors"])

    def test_empty_tools_list_produces_warning(self):
        """Empty tools list produces a warning."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '[]'  # Empty
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result = validate_octo_spec_output(mock_result)

        assert any("tools" in w.lower() for w in result["warnings"])

    def test_weighted_mode_without_min_score_produces_warning(self):
        """Weighted gate_mode without min_score produces warning."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "weighted", "validators": []}'  # Missing min_score

        result = validate_octo_spec_output(mock_result)

        assert any("min_score" in w for w in result["warnings"])

    def test_invalid_min_score_range_produces_error(self):
        """min_score outside 0-1 range produces error."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Test"
        mock_result.agent_name = "test-agent"
        mock_result.role = "Role"
        mock_result.tools_json = '["tool"]'
        mock_result.skills_json = '["skill"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["resp"]'
        mock_result.acceptance_contract_json = '{"gate_mode": "weighted", "validators": [], "min_score": 1.5}'  # Invalid

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("min_score" in e for e in result["errors"])

    def test_valid_result_produces_no_errors(self):
        """Completely valid result produces no errors."""
        from api.dspy_signatures import validate_octo_spec_output

        mock_result = MagicMock()
        mock_result.reasoning = "Comprehensive reasoning about agent design"
        mock_result.agent_name = "playwright-e2e-tester"
        mock_result.role = "End-to-end UI testing agent using Playwright"
        mock_result.tools_json = '["mcp__playwright__browser_navigate", "mcp__playwright__browser_click"]'
        mock_result.skills_json = '["e2e_testing", "browser_automation", "visual_regression"]'
        mock_result.model = "sonnet"
        mock_result.responsibilities_json = '["Execute E2E test scenarios", "Capture screenshots"]'
        mock_result.acceptance_contract_json = json.dumps({
            "gate_mode": "all_pass",
            "validators": [
                {"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": True}
            ]
        })

        result = validate_octo_spec_output(mock_result)

        assert len(result["errors"]) == 0, f"Unexpected errors: {result['errors']}"


# =============================================================================
# Feature Verification Steps (Summary)
# =============================================================================

class TestFeature182VerificationSteps:
    """
    Test each verification step from the feature definition.

    Feature #182: Octo DSPy signature for AgentSpec generation
    Steps:
    1. Create SpecGenerationSignature with typed inputs: project_context, capabilities_needed, constraints
    2. Define typed outputs: agent_name, role, tools, skills, model, responsibilities, acceptance_contract
    3. Include chain-of-thought reasoning field for auditability
    4. Signature validates output against AgentSpec schema
    """

    def test_step_1_typed_inputs(self):
        """
        Step 1: Create SpecGenerationSignature with typed inputs.

        Verify inputs: project_context, capabilities_needed, constraints are defined.
        """
        from api.dspy_signatures import OctoSpecGenerationSignature

        input_fields = OctoSpecGenerationSignature.input_fields

        assert "project_context" in input_fields
        assert "capabilities_needed" in input_fields
        assert "constraints" in input_fields
        assert len(input_fields) == 3

    def test_step_2_typed_outputs(self):
        """
        Step 2: Define typed outputs for agent generation.

        Verify outputs: agent_name, role, tools_json, skills_json, model,
        responsibilities_json, acceptance_contract_json are defined.
        """
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields

        required = [
            "agent_name",
            "role",
            "tools_json",
            "skills_json",
            "model",
            "responsibilities_json",
            "acceptance_contract_json",
        ]

        for field in required:
            assert field in output_fields, f"Missing output field: {field}"

    def test_step_3_chain_of_thought_reasoning(self):
        """
        Step 3: Include chain-of-thought reasoning field for auditability.

        Verify reasoning field exists and has description about auditability.
        """
        import dspy
        from api.dspy_signatures import OctoSpecGenerationSignature

        output_fields = OctoSpecGenerationSignature.output_fields

        # Reasoning field exists
        assert "reasoning" in output_fields

        # Works with ChainOfThought module
        cot = dspy.ChainOfThought(OctoSpecGenerationSignature)
        assert cot is not None

    def test_step_4_schema_validation(self):
        """
        Step 4: Signature validates output against AgentSpec schema.

        Verify validation function detects invalid values for:
        - agent_name format (lowercase, hyphens, <= 100 chars)
        - model (must be sonnet/opus/haiku)
        - gate_mode (must be all_pass/any_pass/weighted)
        - validator types (must be valid types)
        """
        from api.dspy_signatures import validate_octo_spec_output

        # Test agent_name validation
        mock1 = MagicMock()
        mock1.reasoning = "Test"
        mock1.agent_name = "INVALID!"
        mock1.role = "Role"
        mock1.tools_json = '["tool"]'
        mock1.skills_json = '["skill"]'
        mock1.model = "sonnet"
        mock1.responsibilities_json = '["resp"]'
        mock1.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result1 = validate_octo_spec_output(mock1)
        assert any("agent_name" in e for e in result1["errors"])

        # Test model validation
        mock2 = MagicMock()
        mock2.reasoning = "Test"
        mock2.agent_name = "test-agent"
        mock2.role = "Role"
        mock2.tools_json = '["tool"]'
        mock2.skills_json = '["skill"]'
        mock2.model = "gpt-4"  # Invalid
        mock2.responsibilities_json = '["resp"]'
        mock2.acceptance_contract_json = '{"gate_mode": "all_pass", "validators": []}'

        result2 = validate_octo_spec_output(mock2)
        assert any("model" in e for e in result2["errors"])

        # Test gate_mode validation
        mock3 = MagicMock()
        mock3.reasoning = "Test"
        mock3.agent_name = "test-agent"
        mock3.role = "Role"
        mock3.tools_json = '["tool"]'
        mock3.skills_json = '["skill"]'
        mock3.model = "sonnet"
        mock3.responsibilities_json = '["resp"]'
        mock3.acceptance_contract_json = '{"gate_mode": "invalid", "validators": []}'

        result3 = validate_octo_spec_output(mock3)
        assert any("gate_mode" in e for e in result3["errors"])


# =============================================================================
# DSPy Module Integration Tests
# =============================================================================

class TestDspyModuleIntegration:
    """Test that signature works with DSPy modules."""

    def test_predict_module_creation(self):
        """Signature can be used with dspy.Predict."""
        import dspy
        from api.dspy_signatures import OctoSpecGenerationSignature

        predictor = dspy.Predict(OctoSpecGenerationSignature)
        assert predictor is not None

    def test_chain_of_thought_module_creation(self):
        """Signature can be used with dspy.ChainOfThought."""
        import dspy
        from api.dspy_signatures import OctoSpecGenerationSignature

        cot = dspy.ChainOfThought(OctoSpecGenerationSignature)
        assert cot is not None

    def test_signature_field_count(self):
        """Signature has correct number of input and output fields."""
        from api.dspy_signatures import OctoSpecGenerationSignature

        input_fields = OctoSpecGenerationSignature.input_fields
        output_fields = OctoSpecGenerationSignature.output_fields

        # 3 inputs: project_context, capabilities_needed, constraints
        assert len(input_fields) == 3

        # 8 outputs: reasoning + 7 agent definition fields
        assert len(output_fields) == 8


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
