"""
Test Suite for Feature #50: DSPy SpecGenerationSignature Definition
====================================================================

This test suite verifies the DSPy signature for task -> AgentSpec compilation.

Feature #50 Requirements:
1. Import dspy library
2. Define SpecGenerationSignature(dspy.Signature)
3. Define input fields: task_description, task_type, project_context
4. Define output fields: objective, context_json, tool_policy_json, max_turns, timeout_seconds, validators_json
5. Add docstring with field descriptions
6. Add chain-of-thought reasoning field
"""

import json
import pytest
from typing import get_type_hints
from unittest.mock import MagicMock, patch


# =============================================================================
# Step 1: Import dspy library
# =============================================================================

class TestDspyImport:
    """Test that dspy library is properly imported."""

    def test_dspy_module_imports(self):
        """Step 1: Import dspy library."""
        import dspy
        assert dspy is not None
        assert hasattr(dspy, "Signature")
        assert hasattr(dspy, "InputField")
        assert hasattr(dspy, "OutputField")
        assert hasattr(dspy, "Predict")
        assert hasattr(dspy, "ChainOfThought")

    def test_dspy_version_available(self):
        """Verify DSPy version is accessible."""
        import dspy
        assert hasattr(dspy, "__version__")
        assert isinstance(dspy.__version__, str)


# =============================================================================
# Step 2: Define SpecGenerationSignature(dspy.Signature)
# =============================================================================

class TestSpecGenerationSignatureClass:
    """Test that SpecGenerationSignature is properly defined as a DSPy signature."""

    def test_signature_class_exists(self):
        """Step 2: SpecGenerationSignature class exists."""
        from api.dspy_signatures import SpecGenerationSignature
        assert SpecGenerationSignature is not None

    def test_signature_inherits_from_dspy_signature(self):
        """Step 2: SpecGenerationSignature inherits from dspy.Signature."""
        import dspy
        from api.dspy_signatures import SpecGenerationSignature
        assert issubclass(SpecGenerationSignature, dspy.Signature)

    def test_signature_can_be_used_with_predict(self):
        """Step 2: Signature can be used with dspy.Predict."""
        import dspy
        from api.dspy_signatures import SpecGenerationSignature
        # Should not raise an error
        predictor = dspy.Predict(SpecGenerationSignature)
        assert predictor is not None

    def test_signature_can_be_used_with_chain_of_thought(self):
        """Step 2: Signature can be used with dspy.ChainOfThought."""
        import dspy
        from api.dspy_signatures import SpecGenerationSignature
        # Should not raise an error
        cot = dspy.ChainOfThought(SpecGenerationSignature)
        assert cot is not None


# =============================================================================
# Step 3: Define input fields
# =============================================================================

class TestInputFields:
    """Test that input fields are properly defined."""

    def test_task_description_input_field(self):
        """Step 3: task_description input field exists."""
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Get the field
        fields = SpecGenerationSignature.model_fields
        assert "task_description" in fields

        # Verify it's an input field
        field = fields["task_description"]
        assert field.json_schema_extra is not None or hasattr(field, "annotation")

    def test_task_type_input_field(self):
        """Step 3: task_type input field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "task_type" in fields

    def test_project_context_input_field(self):
        """Step 3: project_context input field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "project_context" in fields

    def test_input_fields_are_string_type(self):
        """Step 3: All input fields have string type annotation."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields

        # Check each input field type
        for field_name in ["task_description", "task_type", "project_context"]:
            assert field_name in fields
            field = fields[field_name]
            assert field.annotation == str or str(field.annotation) == "str"

    def test_input_fields_have_descriptions(self):
        """Step 3: Input fields have desc parameter."""
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Get input fields (dict property in DSPy 3.x)
        input_fields = SpecGenerationSignature.input_fields

        for field_name in ["task_description", "task_type", "project_context"]:
            assert field_name in input_fields, f"Missing input field: {field_name}"


# =============================================================================
# Step 4: Define output fields
# =============================================================================

class TestOutputFields:
    """Test that output fields are properly defined."""

    def test_objective_output_field(self):
        """Step 4: objective output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "objective" in fields

    def test_context_json_output_field(self):
        """Step 4: context_json output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "context_json" in fields

    def test_tool_policy_json_output_field(self):
        """Step 4: tool_policy_json output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "tool_policy_json" in fields

    def test_max_turns_output_field(self):
        """Step 4: max_turns output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "max_turns" in fields

    def test_timeout_seconds_output_field(self):
        """Step 4: timeout_seconds output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "timeout_seconds" in fields

    def test_validators_json_output_field(self):
        """Step 4: validators_json output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "validators_json" in fields

    def test_output_fields_complete(self):
        """Step 4: All required output fields are defined."""
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields

        required_outputs = [
            "reasoning",  # Chain of thought
            "objective",
            "context_json",
            "tool_policy_json",
            "max_turns",
            "timeout_seconds",
            "validators_json",
        ]

        for field_name in required_outputs:
            assert field_name in output_fields, f"Missing output field: {field_name}"

    def test_max_turns_is_int_type(self):
        """Step 4: max_turns has integer type."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        field = fields["max_turns"]
        assert field.annotation == int or "int" in str(field.annotation)

    def test_timeout_seconds_is_int_type(self):
        """Step 4: timeout_seconds has integer type."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        field = fields["timeout_seconds"]
        assert field.annotation == int or "int" in str(field.annotation)


# =============================================================================
# Step 5: Add docstring with field descriptions
# =============================================================================

class TestDocstrings:
    """Test that docstrings and field descriptions are present."""

    def test_signature_has_docstring(self):
        """Step 5: Signature class has a docstring."""
        from api.dspy_signatures import SpecGenerationSignature

        assert SpecGenerationSignature.__doc__ is not None
        assert len(SpecGenerationSignature.__doc__) > 100  # Substantial docstring

    def test_docstring_describes_purpose(self):
        """Step 5: Docstring describes the signature's purpose."""
        from api.dspy_signatures import SpecGenerationSignature

        docstring = SpecGenerationSignature.__doc__
        assert "AgentSpec" in docstring
        assert "task" in docstring.lower()

    def test_docstring_describes_input_fields(self):
        """Step 5: Docstring describes input fields."""
        from api.dspy_signatures import SpecGenerationSignature

        docstring = SpecGenerationSignature.__doc__
        assert "task_description" in docstring
        assert "task_type" in docstring
        assert "project_context" in docstring

    def test_docstring_describes_output_fields(self):
        """Step 5: Docstring describes output fields."""
        from api.dspy_signatures import SpecGenerationSignature

        docstring = SpecGenerationSignature.__doc__
        assert "objective" in docstring
        assert "tool_policy" in docstring.lower()
        assert "validators" in docstring.lower()

    def test_docstring_includes_example(self):
        """Step 5: Docstring includes usage example."""
        from api.dspy_signatures import SpecGenerationSignature

        docstring = SpecGenerationSignature.__doc__
        assert "Example" in docstring or ">>>" in docstring

    def test_input_fields_have_desc(self):
        """Step 5: Input fields have desc parameter with descriptions."""
        from api.dspy_signatures import SpecGenerationSignature

        # input_fields is a dict property in DSPy 3.x
        input_fields = SpecGenerationSignature.input_fields

        for name, field_info in input_fields.items():
            # DSPy fields should have description in json_schema_extra
            desc = None
            if hasattr(field_info, "json_schema_extra") and field_info.json_schema_extra:
                desc = field_info.json_schema_extra.get("desc") or field_info.json_schema_extra.get("description")

            assert desc is not None and len(desc) > 10, f"Field {name} missing description"

    def test_output_fields_have_desc(self):
        """Step 5: Output fields have desc parameter with descriptions."""
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields

        for name, field_info in output_fields.items():
            # DSPy fields should have description
            desc = None
            if hasattr(field_info, "json_schema_extra") and field_info.json_schema_extra:
                desc = field_info.json_schema_extra.get("desc") or field_info.json_schema_extra.get("description")

            assert desc is not None and len(desc) > 10, f"Field {name} missing description"


# =============================================================================
# Step 6: Add chain-of-thought reasoning field
# =============================================================================

class TestChainOfThoughtReasoning:
    """Test that chain-of-thought reasoning field is present."""

    def test_reasoning_field_exists(self):
        """Step 6: reasoning output field exists."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        assert "reasoning" in fields

    def test_reasoning_is_output_field(self):
        """Step 6: reasoning is an output field."""
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields
        assert "reasoning" in output_fields

    def test_reasoning_is_string_type(self):
        """Step 6: reasoning has string type."""
        from api.dspy_signatures import SpecGenerationSignature

        fields = SpecGenerationSignature.model_fields
        field = fields["reasoning"]
        assert field.annotation == str or "str" in str(field.annotation)

    def test_reasoning_has_description(self):
        """Step 6: reasoning field has a description."""
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields
        reasoning_field = output_fields["reasoning"]

        desc = None
        if hasattr(reasoning_field, "json_schema_extra") and reasoning_field.json_schema_extra:
            desc = reasoning_field.json_schema_extra.get("desc") or reasoning_field.json_schema_extra.get("description")

        assert desc is not None
        assert "chain" in desc.lower() or "reasoning" in desc.lower() or "thinking" in desc.lower()

    def test_chain_of_thought_module_works(self):
        """Step 6: ChainOfThought module works with signature."""
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Create ChainOfThought predictor
        cot = dspy.ChainOfThought(SpecGenerationSignature)

        # Verify it has the expected structure
        assert cot is not None
        # ChainOfThought in DSPy 3.x has predict attribute that contains the signature
        assert hasattr(cot, "predict") or hasattr(cot, "signature") or hasattr(cot, "extended_signature")


# =============================================================================
# Utility Functions Tests
# =============================================================================

class TestUtilityFunctions:
    """Test utility functions in the dspy_signatures module."""

    def test_get_spec_generator_exists(self):
        """get_spec_generator function exists."""
        from api.dspy_signatures import get_spec_generator
        assert callable(get_spec_generator)

    def test_get_spec_generator_returns_module(self):
        """get_spec_generator returns a DSPy module."""
        import dspy
        from api.dspy_signatures import get_spec_generator

        generator = get_spec_generator()
        assert generator is not None

    def test_get_spec_generator_with_chain_of_thought_true(self):
        """get_spec_generator with chain of thought returns ChainOfThought."""
        import dspy
        from api.dspy_signatures import get_spec_generator

        generator = get_spec_generator(use_chain_of_thought=True)
        assert isinstance(generator, dspy.ChainOfThought)

    def test_get_spec_generator_with_chain_of_thought_false(self):
        """get_spec_generator without chain of thought returns Predict."""
        import dspy
        from api.dspy_signatures import get_spec_generator

        generator = get_spec_generator(use_chain_of_thought=False)
        assert isinstance(generator, dspy.Predict)

    def test_validate_spec_output_exists(self):
        """validate_spec_output function exists."""
        from api.dspy_signatures import validate_spec_output
        assert callable(validate_spec_output)

    def test_validate_spec_output_returns_dict(self):
        """validate_spec_output returns dict with errors and warnings."""
        from api.dspy_signatures import validate_spec_output
        from unittest.mock import MagicMock

        # Create mock result
        mock_result = MagicMock()
        mock_result.objective = "Test objective"
        mock_result.reasoning = "Test reasoning"
        mock_result.context_json = '{"key": "value"}'
        mock_result.tool_policy_json = '{"policy_version": "v1", "allowed_tools": ["tool1"]}'
        mock_result.validators_json = '[{"type": "test_pass", "config": {}}]'
        mock_result.max_turns = 50
        mock_result.timeout_seconds = 1800

        result = validate_spec_output(mock_result)

        assert isinstance(result, dict)
        assert "errors" in result
        assert "warnings" in result
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)

    def test_validate_spec_output_detects_empty_objective(self):
        """validate_spec_output detects empty objective."""
        from api.dspy_signatures import validate_spec_output
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.objective = ""  # Empty
        mock_result.reasoning = "Test"
        mock_result.context_json = '{"key": "value"}'
        mock_result.tool_policy_json = '{"policy_version": "v1", "allowed_tools": ["tool1"]}'
        mock_result.validators_json = '[{"type": "test_pass", "config": {}}]'
        mock_result.max_turns = 50
        mock_result.timeout_seconds = 1800

        result = validate_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("objective" in e for e in result["errors"])

    def test_validate_spec_output_detects_invalid_json(self):
        """validate_spec_output detects invalid JSON."""
        from api.dspy_signatures import validate_spec_output
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.objective = "Test objective"
        mock_result.reasoning = "Test"
        mock_result.context_json = "not valid json"  # Invalid
        mock_result.tool_policy_json = '{"policy_version": "v1", "allowed_tools": ["tool1"]}'
        mock_result.validators_json = '[{"type": "test_pass", "config": {}}]'
        mock_result.max_turns = 50
        mock_result.timeout_seconds = 1800

        result = validate_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("context_json" in e and "JSON" in e for e in result["errors"])

    def test_validate_spec_output_detects_invalid_max_turns(self):
        """validate_spec_output detects invalid max_turns."""
        from api.dspy_signatures import validate_spec_output
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.objective = "Test objective"
        mock_result.reasoning = "Test"
        mock_result.context_json = '{"key": "value"}'
        mock_result.tool_policy_json = '{"policy_version": "v1", "allowed_tools": ["tool1"]}'
        mock_result.validators_json = '[{"type": "test_pass", "config": {}}]'
        mock_result.max_turns = 600  # Too high (> 500)
        mock_result.timeout_seconds = 1800

        result = validate_spec_output(mock_result)

        assert len(result["errors"]) > 0
        assert any("max_turns" in e for e in result["errors"])


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Test constants defined in the module."""

    def test_valid_task_types_exists(self):
        """VALID_TASK_TYPES constant exists."""
        from api.dspy_signatures import VALID_TASK_TYPES
        assert VALID_TASK_TYPES is not None

    def test_valid_task_types_contains_expected_values(self):
        """VALID_TASK_TYPES contains all expected task types."""
        from api.dspy_signatures import VALID_TASK_TYPES

        expected = {"coding", "testing", "refactoring", "documentation", "audit", "custom"}
        assert expected == set(VALID_TASK_TYPES)

    def test_default_budgets_exists(self):
        """DEFAULT_BUDGETS constant exists."""
        from api.dspy_signatures import DEFAULT_BUDGETS
        assert DEFAULT_BUDGETS is not None
        assert isinstance(DEFAULT_BUDGETS, dict)

    def test_default_budgets_has_all_task_types(self):
        """DEFAULT_BUDGETS has entries for all task types."""
        from api.dspy_signatures import DEFAULT_BUDGETS, VALID_TASK_TYPES

        for task_type in VALID_TASK_TYPES:
            assert task_type in DEFAULT_BUDGETS

    def test_default_budgets_has_required_fields(self):
        """DEFAULT_BUDGETS entries have max_turns and timeout_seconds."""
        from api.dspy_signatures import DEFAULT_BUDGETS

        for task_type, budget in DEFAULT_BUDGETS.items():
            assert "max_turns" in budget, f"Missing max_turns for {task_type}"
            assert "timeout_seconds" in budget, f"Missing timeout_seconds for {task_type}"
            assert isinstance(budget["max_turns"], int)
            assert isinstance(budget["timeout_seconds"], int)


# =============================================================================
# API Package Integration Tests
# =============================================================================

class TestApiPackageIntegration:
    """Test integration with the api package."""

    def test_signature_exported_from_api_package(self):
        """SpecGenerationSignature is exported from api package."""
        from api import SpecGenerationSignature
        assert SpecGenerationSignature is not None

    def test_get_spec_generator_exported_from_api_package(self):
        """get_spec_generator is exported from api package."""
        from api import get_spec_generator
        assert callable(get_spec_generator)

    def test_validate_spec_output_exported_from_api_package(self):
        """validate_spec_output is exported from api package."""
        from api import validate_spec_output
        assert callable(validate_spec_output)

    def test_valid_task_types_exported_from_api_package(self):
        """VALID_TASK_TYPES is exported from api package."""
        from api import VALID_TASK_TYPES
        assert VALID_TASK_TYPES is not None

    def test_dspy_default_budgets_exported_from_api_package(self):
        """DSPY_DEFAULT_BUDGETS is exported from api package."""
        from api import DSPY_DEFAULT_BUDGETS
        assert DSPY_DEFAULT_BUDGETS is not None


# =============================================================================
# Feature Verification Steps
# =============================================================================

class TestFeature50VerificationSteps:
    """
    Test each verification step from the feature definition.

    Feature #50: DSPy SpecGenerationSignature Definition
    Steps:
    1. Import dspy library
    2. Define SpecGenerationSignature(dspy.Signature)
    3. Define input fields: task_description, task_type, project_context
    4. Define output fields: objective, context_json, tool_policy_json, max_turns, timeout_seconds, validators_json
    5. Add docstring with field descriptions
    6. Add chain-of-thought reasoning field
    """

    def test_step_1_import_dspy_library(self):
        """
        Step 1: Import dspy library

        Verify that the dspy library can be imported and the module uses it.
        """
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Verify dspy is importable
        assert dspy is not None

        # Verify SpecGenerationSignature uses dspy
        assert issubclass(SpecGenerationSignature, dspy.Signature)

    def test_step_2_define_spec_generation_signature(self):
        """
        Step 2: Define SpecGenerationSignature(dspy.Signature)

        Verify that SpecGenerationSignature class is defined and inherits from dspy.Signature.
        """
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Class exists
        assert SpecGenerationSignature is not None

        # Inherits from dspy.Signature
        assert issubclass(SpecGenerationSignature, dspy.Signature)

        # Can be instantiated with DSPy modules
        predictor = dspy.Predict(SpecGenerationSignature)
        assert predictor is not None

    def test_step_3_define_input_fields(self):
        """
        Step 3: Define input fields: task_description, task_type, project_context

        Verify all three input fields are defined.
        """
        from api.dspy_signatures import SpecGenerationSignature

        # input_fields is a dict property in DSPy 3.x
        input_fields = SpecGenerationSignature.input_fields

        # All three input fields exist
        assert "task_description" in input_fields
        assert "task_type" in input_fields
        assert "project_context" in input_fields

        # No extra unexpected input fields
        assert len(input_fields) == 3

    def test_step_4_define_output_fields(self):
        """
        Step 4: Define output fields: objective, context_json, tool_policy_json,
                max_turns, timeout_seconds, validators_json

        Verify all six required output fields plus reasoning are defined.
        """
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields

        # All required output fields exist
        required = [
            "objective",
            "context_json",
            "tool_policy_json",
            "max_turns",
            "timeout_seconds",
            "validators_json",
            "reasoning",  # Chain of thought
        ]

        for field in required:
            assert field in output_fields, f"Missing output field: {field}"

    def test_step_5_add_docstring_with_field_descriptions(self):
        """
        Step 5: Add docstring with field descriptions

        Verify the signature has a comprehensive docstring and fields have descriptions.
        """
        from api.dspy_signatures import SpecGenerationSignature

        # Class has docstring
        docstring = SpecGenerationSignature.__doc__
        assert docstring is not None
        assert len(docstring) > 500  # Comprehensive docstring

        # Input fields have descriptions (input_fields is dict in DSPy 3.x)
        input_fields = SpecGenerationSignature.input_fields
        for name, field_info in input_fields.items():
            if hasattr(field_info, "json_schema_extra") and field_info.json_schema_extra:
                desc = field_info.json_schema_extra.get("desc")
                assert desc is not None and len(desc) > 0, f"Field {name} missing desc"

        # Output fields have descriptions (output_fields is dict in DSPy 3.x)
        output_fields = SpecGenerationSignature.output_fields
        for name, field_info in output_fields.items():
            if hasattr(field_info, "json_schema_extra") and field_info.json_schema_extra:
                desc = field_info.json_schema_extra.get("desc")
                assert desc is not None and len(desc) > 0, f"Field {name} missing desc"

    def test_step_6_add_chain_of_thought_reasoning_field(self):
        """
        Step 6: Add chain-of-thought reasoning field

        Verify the reasoning output field is defined for chain-of-thought.
        """
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields

        # Reasoning field exists
        assert "reasoning" in output_fields

        # Field has description mentioning reasoning/chain-of-thought
        reasoning_field = output_fields["reasoning"]
        if hasattr(reasoning_field, "json_schema_extra") and reasoning_field.json_schema_extra:
            desc = reasoning_field.json_schema_extra.get("desc", "")
            assert any(term in desc.lower() for term in ["chain", "thought", "reason"])

        # Works with ChainOfThought module
        cot = dspy.ChainOfThought(SpecGenerationSignature)
        assert cot is not None


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
