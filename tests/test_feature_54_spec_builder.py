"""
Tests for Feature #54: DSPy Module Execution for Spec Generation

This module tests the SpecBuilder class that wraps DSPy for generating
AgentSpecs from task descriptions.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Import the module under test
from api.spec_builder import (
    # Exceptions
    SpecBuilderError,
    DSPyInitializationError,
    DSPyExecutionError,
    OutputValidationError,
    ToolPolicyValidationError,
    ValidatorsValidationError,
    # Data classes
    BuildResult,
    ParsedOutput,
    # Validation functions
    validate_tool_policy,
    validate_validators,
    parse_json_field,
    coerce_integer,
    # Main class
    SpecBuilder,
    # Module-level functions
    get_spec_builder,
    reset_spec_builder,
    # Constants
    DEFAULT_MODEL,
    AVAILABLE_MODELS,
    MIN_MAX_TURNS,
    MAX_MAX_TURNS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    TOOL_POLICY_REQUIRED_FIELDS,
)
from api.agentspec_models import AgentSpec, AcceptanceSpec


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_api_key():
    """Provide a mock API key for testing."""
    return "test-api-key-12345"


@pytest.fixture
def mock_env_api_key(mock_api_key):
    """Set up environment with mock API key."""
    original = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = mock_api_key
    yield mock_api_key
    if original:
        os.environ["ANTHROPIC_API_KEY"] = original
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture
def valid_tool_policy():
    """Return a valid tool_policy structure."""
    return {
        "policy_version": "v1",
        "allowed_tools": ["Read", "Write", "Edit", "Bash"],
        "forbidden_patterns": ["rm -rf", "DROP TABLE"],
        "tool_hints": {
            "Edit": "Always read files before editing",
        },
    }


@pytest.fixture
def valid_validators():
    """Return a valid validators array."""
    return [
        {
            "type": "test_pass",
            "config": {"command": "pytest tests/"},
            "weight": 0.5,
            "required": False,
        },
        {
            "type": "file_exists",
            "config": {"path": "src/main.py"},
            "weight": 0.5,
            "required": True,
        },
    ]


@pytest.fixture
def mock_dspy_result(valid_tool_policy, valid_validators):
    """Create a mock DSPy Prediction result."""
    mock_result = MagicMock()
    mock_result.reasoning = "This task requires implementing authentication..."
    mock_result.objective = "Implement secure user authentication with OAuth2."
    mock_result.context_json = json.dumps({
        "target_files": ["src/auth.py"],
        "feature_id": 42,
    })
    mock_result.tool_policy_json = json.dumps(valid_tool_policy)
    mock_result.max_turns = 100
    mock_result.timeout_seconds = 1800
    mock_result.validators_json = json.dumps(valid_validators)
    return mock_result


# =============================================================================
# Test: validate_tool_policy
# =============================================================================

class TestValidateToolPolicy:
    """Tests for validate_tool_policy function."""

    def test_valid_policy(self, valid_tool_policy):
        """Test validation of valid tool policy."""
        errors = validate_tool_policy(valid_tool_policy)
        assert errors == []

    def test_minimal_valid_policy(self):
        """Test minimal valid policy with only required fields."""
        policy = {"allowed_tools": ["Read"]}
        errors = validate_tool_policy(policy)
        assert errors == []

    def test_missing_allowed_tools(self):
        """Test error when allowed_tools is missing."""
        policy = {"forbidden_patterns": []}
        errors = validate_tool_policy(policy)
        assert any("allowed_tools" in e for e in errors)

    def test_allowed_tools_not_array(self):
        """Test error when allowed_tools is not an array."""
        policy = {"allowed_tools": "Read"}
        errors = validate_tool_policy(policy)
        assert any("must be an array" in e for e in errors)

    def test_allowed_tools_with_non_string(self):
        """Test error when allowed_tools contains non-string."""
        policy = {"allowed_tools": ["Read", 123, "Write"]}
        errors = validate_tool_policy(policy)
        assert any("must be a string" in e for e in errors)

    def test_allowed_tools_with_empty_string(self):
        """Test error when allowed_tools contains empty string."""
        policy = {"allowed_tools": ["Read", "", "Write"]}
        errors = validate_tool_policy(policy)
        assert any("cannot be empty" in e for e in errors)

    def test_forbidden_patterns_not_array(self):
        """Test error when forbidden_patterns is not an array."""
        policy = {"allowed_tools": ["Read"], "forbidden_patterns": "bad"}
        errors = validate_tool_policy(policy)
        assert any("forbidden_patterns must be an array" in e for e in errors)

    def test_forbidden_patterns_invalid_regex(self):
        """Test error when forbidden_patterns contains invalid regex."""
        policy = {"allowed_tools": ["Read"], "forbidden_patterns": ["[invalid"]}
        errors = validate_tool_policy(policy)
        assert any("not a valid regex" in e for e in errors)

    def test_tool_hints_not_object(self):
        """Test error when tool_hints is not an object."""
        policy = {"allowed_tools": ["Read"], "tool_hints": ["bad"]}
        errors = validate_tool_policy(policy)
        assert any("tool_hints must be an object" in e for e in errors)

    def test_tool_hints_non_string_value(self):
        """Test error when tool_hints has non-string value."""
        policy = {"allowed_tools": ["Read"], "tool_hints": {"Read": 123}}
        errors = validate_tool_policy(policy)
        assert any("must be a string" in e for e in errors)

    def test_invalid_policy_version(self):
        """Test error when policy_version is not v1."""
        policy = {"allowed_tools": ["Read"], "policy_version": "v2"}
        errors = validate_tool_policy(policy)
        assert any("policy_version must be 'v1'" in e for e in errors)


# =============================================================================
# Test: validate_validators
# =============================================================================

class TestValidateValidators:
    """Tests for validate_validators function."""

    def test_valid_validators(self, valid_validators):
        """Test validation of valid validators array."""
        errors = validate_validators(valid_validators)
        assert errors == []

    def test_empty_validators_array(self):
        """Test empty validators array is valid."""
        errors = validate_validators([])
        assert errors == []

    def test_validators_not_array(self):
        """Test error when validators is not an array."""
        errors = validate_validators({"type": "test_pass"})
        assert any("must be an array" in e for e in errors)

    def test_validator_not_object(self):
        """Test error when validator is not an object."""
        errors = validate_validators(["not an object"])
        assert any("must be an object" in e for e in errors)

    def test_validator_missing_type(self):
        """Test error when validator is missing type."""
        errors = validate_validators([{"config": {}}])
        assert any("missing required field: type" in e for e in errors)

    def test_validator_invalid_type(self):
        """Test error when validator has invalid type."""
        errors = validate_validators([{"type": "invalid_type"}])
        assert any("must be one of" in e for e in errors)

    def test_validator_type_not_string(self):
        """Test error when validator type is not a string."""
        errors = validate_validators([{"type": 123}])
        assert any("type must be a string" in e for e in errors)

    def test_validator_config_not_object(self):
        """Test error when validator config is not an object."""
        errors = validate_validators([{"type": "test_pass", "config": "bad"}])
        assert any("config must be an object" in e for e in errors)

    def test_validator_weight_not_number(self):
        """Test error when validator weight is not a number."""
        errors = validate_validators([{"type": "test_pass", "weight": "bad"}])
        assert any("weight must be a number" in e for e in errors)

    def test_validator_weight_out_of_range(self):
        """Test error when validator weight is out of range."""
        errors = validate_validators([{"type": "test_pass", "weight": 2.0}])
        assert any("weight must be between 0 and 1" in e for e in errors)

    def test_validator_required_not_boolean(self):
        """Test error when validator required is not a boolean."""
        errors = validate_validators([{"type": "test_pass", "required": "yes"}])
        assert any("required must be a boolean" in e for e in errors)


# =============================================================================
# Test: parse_json_field
# =============================================================================

class TestParseJsonField:
    """Tests for parse_json_field function."""

    def test_valid_json_object(self):
        """Test parsing valid JSON object."""
        value, error = parse_json_field("test", '{"key": "value"}')
        assert error is None
        assert value == {"key": "value"}

    def test_valid_json_array(self):
        """Test parsing valid JSON array."""
        value, error = parse_json_field("test", '[1, 2, 3]')
        assert error is None
        assert value == [1, 2, 3]

    def test_empty_string(self):
        """Test error on empty string."""
        value, error = parse_json_field("test", "")
        assert error is not None
        assert "empty" in error

    def test_json_in_code_block(self):
        """Test parsing JSON from markdown code block."""
        value, error = parse_json_field(
            "test",
            '```json\n{"key": "value"}\n```'
        )
        assert error is None
        assert value == {"key": "value"}

    def test_json_in_generic_code_block(self):
        """Test parsing JSON from generic code block."""
        value, error = parse_json_field(
            "test",
            '```\n{"key": "value"}\n```'
        )
        assert error is None
        assert value == {"key": "value"}

    def test_json_with_surrounding_text(self):
        """Test parsing JSON embedded in text."""
        value, error = parse_json_field(
            "test",
            'Here is the output: {"key": "value"} and more text'
        )
        assert error is None
        assert value == {"key": "value"}

    def test_invalid_json(self):
        """Test error on invalid JSON."""
        value, error = parse_json_field("test", '{invalid}')
        assert error is not None
        assert "could not be parsed" in error or "invalid JSON" in error


# =============================================================================
# Test: coerce_integer
# =============================================================================

class TestCoerceInteger:
    """Tests for coerce_integer function."""

    def test_integer_value(self):
        """Test coercing integer value."""
        value, error = coerce_integer("test", 50, 1, 100)
        assert error is None
        assert value == 50

    def test_float_value(self):
        """Test coercing float value to integer."""
        value, error = coerce_integer("test", 50.7, 1, 100)
        assert error is None
        assert value == 50

    def test_string_value(self):
        """Test coercing string value to integer."""
        value, error = coerce_integer("test", "50", 1, 100)
        assert error is None
        assert value == 50

    def test_clamp_to_minimum(self):
        """Test clamping value to minimum."""
        value, error = coerce_integer("test", 0, 10, 100)
        assert error is None
        assert value == 10

    def test_clamp_to_maximum(self):
        """Test clamping value to maximum."""
        value, error = coerce_integer("test", 200, 10, 100)
        assert error is None
        assert value == 100

    def test_invalid_string(self):
        """Test error on invalid string."""
        value, error = coerce_integer("test", "invalid", 1, 100)
        assert error is not None
        assert "must be an integer" in error


# =============================================================================
# Test: BuildResult
# =============================================================================

class TestBuildResult:
    """Tests for BuildResult dataclass."""

    def test_success_result(self):
        """Test successful build result."""
        spec = MagicMock(spec=AgentSpec)
        acceptance = MagicMock(spec=AcceptanceSpec)

        result = BuildResult(
            success=True,
            agent_spec=spec,
            acceptance_spec=acceptance,
        )

        assert result.success is True
        assert result.agent_spec == spec
        assert result.acceptance_spec == acceptance
        assert result.error is None
        assert result.validation_errors == []

    def test_failure_result(self):
        """Test failed build result."""
        result = BuildResult(
            success=False,
            error="Something went wrong",
            error_type="execution",
            validation_errors=["error 1", "error 2"],
        )

        assert result.success is False
        assert result.agent_spec is None
        assert result.error == "Something went wrong"
        assert len(result.validation_errors) == 2


# =============================================================================
# Test: SpecBuilder Initialization
# =============================================================================

class TestSpecBuilderInitialization:
    """Tests for SpecBuilder initialization."""

    def test_default_model(self):
        """Test default model is set correctly."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch('api.spec_builder.dspy.LM'):
                with patch('api.spec_builder.dspy.configure'):
                    with patch('api.spec_builder.dspy.ChainOfThought'):
                        builder = SpecBuilder(auto_initialize=False)
                        assert builder.model == DEFAULT_MODEL

    def test_custom_model(self):
        """Test custom model can be specified."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            builder = SpecBuilder(
                model="anthropic/claude-3-haiku-20240307",
                auto_initialize=False
            )
            assert builder.model == "anthropic/claude-3-haiku-20240307"

    def test_is_initialized_false_initially(self):
        """Test builder is not initialized initially when auto_initialize=False."""
        builder = SpecBuilder(api_key="test-key", auto_initialize=False)
        assert builder.is_initialized is False

    def test_initialization_without_api_key_fails(self):
        """Test initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear any existing key
            os.environ.pop("ANTHROPIC_API_KEY", None)

            with pytest.raises(DSPyInitializationError) as exc_info:
                SpecBuilder(api_key=None, auto_initialize=True)

            assert "API key not found" in str(exc_info.value)


# =============================================================================
# Test: SpecBuilder.build() Input Validation
# =============================================================================

class TestSpecBuilderInputValidation:
    """Tests for SpecBuilder.build() input validation."""

    @pytest.fixture
    def builder(self):
        """Create a builder with mocked DSPy."""
        return SpecBuilder(api_key="test-key", auto_initialize=False)

    def test_empty_task_description(self, builder):
        """Test error on empty task description."""
        result = builder.build(
            task_description="",
            task_type="coding",
        )
        assert result.success is False
        assert "task_description cannot be empty" in result.error
        assert result.error_type == "input_validation"

    def test_whitespace_task_description(self, builder):
        """Test error on whitespace-only task description."""
        result = builder.build(
            task_description="   ",
            task_type="coding",
        )
        assert result.success is False
        assert "task_description cannot be empty" in result.error

    def test_invalid_task_type(self, builder):
        """Test error on invalid task type."""
        result = builder.build(
            task_description="Do something",
            task_type="invalid_type",
        )
        assert result.success is False
        assert "task_type must be one of" in result.error
        assert result.error_type == "input_validation"

    def test_task_type_case_insensitive(self, builder):
        """Test task type is case insensitive."""
        # Should lowercase the task type - verify it passes validation
        # and fails at a later stage (execution), proving it was accepted
        with patch.object(builder, '_initialize_dspy'):
            builder._initialized = True
            with patch.object(builder, '_execute_dspy', side_effect=DSPyExecutionError("test")):
                result = builder.build(
                    task_description="Do something",
                    task_type="CODING",
                )
                # Should get past input validation and fail at execution
                assert result.error_type == "execution"

    def test_non_serializable_context(self, builder):
        """Test error on non-JSON-serializable context."""
        result = builder.build(
            task_description="Do something",
            task_type="coding",
            context={"func": lambda x: x},  # Not serializable
        )
        assert result.success is False
        assert "JSON-serializable" in result.error
        assert result.error_type == "input_validation"


# =============================================================================
# Test: SpecBuilder.build() with Mocked DSPy
# =============================================================================

class TestSpecBuilderBuild:
    """Tests for SpecBuilder.build() with mocked DSPy."""

    @pytest.fixture
    def builder_with_mocked_dspy(self, mock_dspy_result):
        """Create a builder with fully mocked DSPy."""
        builder = SpecBuilder(api_key="test-key", auto_initialize=False)

        # Set up the builder as initialized with a mocked module
        builder._initialized = True
        builder._dspy_module = MagicMock(return_value=mock_dspy_result)
        yield builder

    def test_successful_build(self, builder_with_mocked_dspy, mock_dspy_result):
        """Test successful spec generation."""
        result = builder_with_mocked_dspy.build(
            task_description="Implement user authentication",
            task_type="coding",
            context={"project_name": "TestApp"},
        )

        assert result.success is True
        assert result.agent_spec is not None
        assert result.acceptance_spec is not None
        assert result.error is None
        assert result.validation_errors == []

    def test_generated_spec_has_correct_task_type(self, builder_with_mocked_dspy):
        """Test generated spec has correct task type."""
        result = builder_with_mocked_dspy.build(
            task_description="Test the application",
            task_type="testing",
        )

        assert result.success is True
        assert result.agent_spec.task_type == "testing"

    def test_generated_spec_has_objective(self, builder_with_mocked_dspy):
        """Test generated spec has objective from DSPy output."""
        result = builder_with_mocked_dspy.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is True
        assert "OAuth2" in result.agent_spec.objective

    def test_generated_spec_has_tool_policy(self, builder_with_mocked_dspy, valid_tool_policy):
        """Test generated spec has tool policy from DSPy output."""
        result = builder_with_mocked_dspy.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is True
        assert result.agent_spec.tool_policy["allowed_tools"] == valid_tool_policy["allowed_tools"]

    def test_generated_acceptance_spec_has_validators(self, builder_with_mocked_dspy):
        """Test generated acceptance spec has validators."""
        result = builder_with_mocked_dspy.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is True
        assert len(result.acceptance_spec.validators) == 2

    def test_source_feature_id_linked(self, builder_with_mocked_dspy):
        """Test source_feature_id is linked when provided."""
        result = builder_with_mocked_dspy.build(
            task_description="Do something",
            task_type="coding",
            source_feature_id=42,
        )

        assert result.success is True
        assert result.agent_spec.source_feature_id == 42

    def test_custom_spec_id(self, builder_with_mocked_dspy):
        """Test custom spec_id is used when provided."""
        custom_id = "custom-spec-id-12345"
        result = builder_with_mocked_dspy.build(
            task_description="Do something",
            task_type="coding",
            spec_id=custom_id,
        )

        assert result.success is True
        assert result.agent_spec.id == custom_id

    def test_raw_output_included(self, builder_with_mocked_dspy):
        """Test raw DSPy output is included in result."""
        result = builder_with_mocked_dspy.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is True
        assert result.raw_output is not None
        assert "objective" in result.raw_output


# =============================================================================
# Test: SpecBuilder Error Handling
# =============================================================================

class TestSpecBuilderErrorHandling:
    """Tests for SpecBuilder error handling."""

    def test_dspy_execution_error(self):
        """Test handling of DSPy execution errors."""
        builder = SpecBuilder(api_key="test-key", auto_initialize=False)
        builder._initialized = True
        builder._dspy_module = MagicMock(side_effect=RuntimeError("DSPy failed"))

        result = builder.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is False
        assert result.error_type == "execution"
        assert "DSPy execution failed" in result.error

    def test_invalid_tool_policy_output(self):
        """Test handling of invalid tool_policy from DSPy."""
        builder = SpecBuilder(api_key="test-key", auto_initialize=False)
        builder._initialized = True

        mock_result = MagicMock()
        mock_result.reasoning = "reasoning"
        mock_result.objective = "objective"
        mock_result.context_json = "{}"
        mock_result.tool_policy_json = '{"invalid": true}'  # Missing allowed_tools
        mock_result.max_turns = 100
        mock_result.timeout_seconds = 1800
        mock_result.validators_json = "[]"

        builder._dspy_module = MagicMock(return_value=mock_result)

        result = builder.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is False
        # The validate_spec_output function catches the tool_policy error first
        # because it validates before parsing
        assert result.error_type in ("tool_policy_validation", "output_validation")
        # Verify the error mentions allowed_tools
        assert any("allowed_tools" in e for e in result.validation_errors)

    def test_invalid_validators_output(self):
        """Test handling of invalid validators from DSPy."""
        builder = SpecBuilder(api_key="test-key", auto_initialize=False)
        builder._initialized = True

        mock_result = MagicMock()
        mock_result.reasoning = "reasoning"
        mock_result.objective = "objective"
        mock_result.context_json = "{}"
        mock_result.tool_policy_json = '{"allowed_tools": ["Read"]}'
        mock_result.max_turns = 100
        mock_result.timeout_seconds = 1800
        mock_result.validators_json = '[{"type": "invalid_type"}]'

        builder._dspy_module = MagicMock(return_value=mock_result)

        result = builder.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is False
        assert result.error_type == "validators_validation"

    def test_unparseable_json_output(self):
        """Test handling of unparseable JSON from DSPy."""
        builder = SpecBuilder(api_key="test-key", auto_initialize=False)
        builder._initialized = True

        mock_result = MagicMock()
        mock_result.reasoning = "reasoning"
        mock_result.objective = "objective"
        mock_result.context_json = "not json at all {{{"
        mock_result.tool_policy_json = "not json at all {{{"
        mock_result.max_turns = 100
        mock_result.timeout_seconds = 1800
        mock_result.validators_json = "not json at all {{{"

        builder._dspy_module = MagicMock(return_value=mock_result)

        result = builder.build(
            task_description="Do something",
            task_type="coding",
        )

        assert result.success is False
        # validate_spec_output catches JSON errors before _parse_output
        assert result.error_type in ("parse_error", "output_validation")
        # Should have errors about JSON parsing
        assert len(result.validation_errors) > 0


# =============================================================================
# Test: Module-level Functions
# =============================================================================

class TestModuleLevelFunctions:
    """Tests for module-level functions."""

    def test_get_spec_builder_singleton(self):
        """Test get_spec_builder returns singleton."""
        reset_spec_builder()

        builder1 = get_spec_builder(api_key="test-key")
        builder2 = get_spec_builder()

        assert builder1 is builder2

    def test_get_spec_builder_force_new(self):
        """Test get_spec_builder with force_new."""
        reset_spec_builder()

        builder1 = get_spec_builder(api_key="test-key")
        builder2 = get_spec_builder(force_new=True, api_key="test-key")

        assert builder1 is not builder2

    def test_reset_spec_builder(self):
        """Test reset_spec_builder clears singleton."""
        reset_spec_builder()

        builder1 = get_spec_builder(api_key="test-key")
        reset_spec_builder()
        builder2 = get_spec_builder(api_key="test-key")

        assert builder1 is not builder2


# =============================================================================
# Test: Constants
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_default_model_is_valid(self):
        """Test DEFAULT_MODEL is in AVAILABLE_MODELS."""
        assert DEFAULT_MODEL in AVAILABLE_MODELS

    def test_budget_bounds(self):
        """Test budget bounds are sensible."""
        assert MIN_MAX_TURNS >= 1
        assert MAX_MAX_TURNS >= MIN_MAX_TURNS
        assert MIN_TIMEOUT_SECONDS >= 60
        assert MAX_TIMEOUT_SECONDS >= MIN_TIMEOUT_SECONDS

    def test_tool_policy_required_fields(self):
        """Test required fields set is correct."""
        assert "allowed_tools" in TOOL_POLICY_REQUIRED_FIELDS


# =============================================================================
# Test: Exceptions
# =============================================================================

class TestExceptions:
    """Tests for custom exceptions."""

    def test_spec_builder_error_base(self):
        """Test SpecBuilderError is base exception."""
        assert issubclass(DSPyInitializationError, SpecBuilderError)
        assert issubclass(DSPyExecutionError, SpecBuilderError)
        assert issubclass(OutputValidationError, SpecBuilderError)

    def test_dspy_initialization_error_preserves_original(self):
        """Test DSPyInitializationError preserves original error."""
        original = ValueError("original error")
        error = DSPyInitializationError("wrapper", original_error=original)
        assert error.original_error == original

    def test_output_validation_error_has_errors_list(self):
        """Test OutputValidationError has validation errors list."""
        error = OutputValidationError("failed", validation_errors=["e1", "e2"])
        assert error.validation_errors == ["e1", "e2"]

    def test_tool_policy_validation_error_is_output_validation(self):
        """Test ToolPolicyValidationError inherits from OutputValidationError."""
        assert issubclass(ToolPolicyValidationError, OutputValidationError)

    def test_validators_validation_error_is_output_validation(self):
        """Test ValidatorsValidationError inherits from OutputValidationError."""
        assert issubclass(ValidatorsValidationError, OutputValidationError)
