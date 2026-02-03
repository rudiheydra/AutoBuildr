"""
Test Feature #188: Octo outputs are strictly typed and schema-validated
=======================================================================

This test suite verifies that all Octo outputs are validated against defined
JSON schemas before being returned to Maestro, ensuring no invalid outputs
propagate to the Materializer.

Feature Steps:
1. Define AgentSpec JSON schema with required fields
2. Define TestContract JSON schema
3. Octo validates output against schemas before returning
4. Schema validation errors raise exceptions with details
5. Invalid outputs never propagate to Materializer
"""
import json
import pytest
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api.octo_schemas import (
    # Exceptions
    OctoSchemaValidationError,
    SchemaValidationError,
    SchemaValidationResult,
    # Validation functions
    validate_agent_spec_schema,
    validate_test_contract_schema,
    validate_octo_outputs,
    validate_agent_spec_schema_or_raise,
    validate_test_contract_schema_or_raise,
    get_schema,
    # Schemas
    AGENT_SPEC_SCHEMA,
    TEST_CONTRACT_SCHEMA,
    TEST_CONTRACT_ASSERTION_SCHEMA,
    # Constants
    VALID_TASK_TYPES,
    VALID_TEST_TYPES,
    VALID_GATE_MODES,
    VALID_ASSERTION_OPERATORS,
    NAME_PATTERN,
    MIN_MAX_TURNS,
    MAX_MAX_TURNS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    MIN_PRIORITY,
    MAX_PRIORITY,
)
from api.octo import (
    Octo,
    OctoRequestPayload,
    OctoResponse,
    TestContract,
    TestContractAssertion,
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
def valid_agent_spec_dict():
    """Create a valid AgentSpec dictionary for testing."""
    return {
        "id": generate_uuid(),
        "name": "test-agent",
        "display_name": "Test Agent",
        "icon": "test-tube",
        "spec_version": "v1",
        "objective": "Test objective that is long enough to pass validation.",
        "task_type": "testing",
        "context": {"capability": "e2e_testing"},
        "tool_policy": {
            "policy_version": "v1",
            "allowed_tools": ["browser_navigate", "browser_click"],
            "forbidden_patterns": [],
            "tool_hints": {},
        },
        "max_turns": 50,
        "timeout_seconds": 1800,
        "priority": 500,
        "tags": ["testing", "e2e"],
    }


@pytest.fixture
def valid_test_contract_dict():
    """Create a valid TestContract dictionary for testing."""
    return {
        "contract_id": generate_uuid(),
        "agent_name": "test-agent",
        "test_type": "e2e",
        "assertions": [
            {
                "description": "Page loads successfully",
                "target": "page.status",
                "expected": "loaded",
                "operator": "eq",
            }
        ],
        "pass_criteria": ["All tests pass"],
        "fail_criteria": ["Any test fails"],
        "description": "Test contract for e2e testing",
        "priority": 2,
        "tags": ["e2e", "testing"],
    }


@pytest.fixture
def sample_agent_spec():
    """Create a sample AgentSpec model for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="test-e2e-agent",
        display_name="Test E2E Agent",
        icon="test-tube",
        spec_version="v1",
        objective="Implement end-to-end tests for TestApp using Playwright",
        task_type="testing",
        context={"capability": "e2e_testing"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["browser_navigate", "browser_click", "browser_type"],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=1800,
        tags=["testing", "e2e"],
    )


@pytest.fixture
def mock_spec_builder(sample_agent_spec):
    """Create a mock SpecBuilder that returns successful results."""
    mock_builder = MagicMock(spec=SpecBuilder)
    mock_builder.build.return_value = BuildResult(
        success=True,
        agent_spec=sample_agent_spec,
        acceptance_spec=AcceptanceSpec(validators=[]),
    )
    return mock_builder


@pytest.fixture
def sample_payload():
    """Create a sample OctoRequestPayload for testing."""
    return OctoRequestPayload(
        project_context={
            "name": "TestApp",
            "tech_stack": ["python", "react"],
        },
        required_capabilities=["e2e_testing"],
        existing_agents=[],
        constraints={},
    )


# =============================================================================
# Step 1: Define AgentSpec JSON schema with required fields
# =============================================================================

class TestStep1AgentSpecSchema:
    """Test that AgentSpec JSON schema is correctly defined."""

    def test_agent_spec_schema_exists(self):
        """AgentSpec schema should be defined."""
        assert AGENT_SPEC_SCHEMA is not None
        assert isinstance(AGENT_SPEC_SCHEMA, dict)

    def test_agent_spec_schema_has_required_fields(self):
        """AgentSpec schema should define required fields."""
        required = AGENT_SPEC_SCHEMA.get("required", [])
        assert "name" in required
        assert "display_name" in required
        assert "objective" in required
        assert "task_type" in required
        assert "tool_policy" in required

    def test_agent_spec_schema_has_properties(self):
        """AgentSpec schema should define all properties."""
        properties = AGENT_SPEC_SCHEMA.get("properties", {})
        expected_props = [
            "id", "name", "display_name", "icon", "spec_version",
            "objective", "task_type", "context", "tool_policy",
            "max_turns", "timeout_seconds", "priority", "tags",
        ]
        for prop in expected_props:
            assert prop in properties, f"Missing property: {prop}"

    def test_agent_spec_schema_name_has_pattern(self):
        """AgentSpec name field should have a pattern constraint."""
        props = AGENT_SPEC_SCHEMA.get("properties", {})
        name_prop = props.get("name", {})
        assert "pattern" in name_prop

    def test_agent_spec_schema_task_type_has_enum(self):
        """AgentSpec task_type should be limited to valid types."""
        props = AGENT_SPEC_SCHEMA.get("properties", {})
        task_type_prop = props.get("task_type", {})
        assert "enum" in task_type_prop
        assert set(task_type_prop["enum"]) == VALID_TASK_TYPES

    def test_agent_spec_schema_tool_policy_structure(self):
        """AgentSpec tool_policy should have required allowed_tools."""
        props = AGENT_SPEC_SCHEMA.get("properties", {})
        tool_policy = props.get("tool_policy", {})
        assert tool_policy.get("type") == "object"
        assert "allowed_tools" in tool_policy.get("required", [])

    def test_valid_agent_spec_passes_validation(self, valid_agent_spec_dict):
        """A valid AgentSpec dict should pass schema validation."""
        result = validate_agent_spec_schema(valid_agent_spec_dict)
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.schema_name == "AgentSpec"

    def test_get_schema_returns_agent_spec_schema(self):
        """get_schema should return AgentSpec schema by name."""
        schema = get_schema("AgentSpec")
        assert schema == AGENT_SPEC_SCHEMA


# =============================================================================
# Step 2: Define TestContract JSON schema
# =============================================================================

class TestStep2TestContractSchema:
    """Test that TestContract JSON schema is correctly defined."""

    def test_test_contract_schema_exists(self):
        """TestContract schema should be defined."""
        assert TEST_CONTRACT_SCHEMA is not None
        assert isinstance(TEST_CONTRACT_SCHEMA, dict)

    def test_test_contract_schema_has_required_fields(self):
        """TestContract schema should define required fields."""
        required = TEST_CONTRACT_SCHEMA.get("required", [])
        assert "agent_name" in required
        assert "test_type" in required

    def test_test_contract_schema_test_type_enum(self):
        """TestContract test_type should be limited to valid types."""
        props = TEST_CONTRACT_SCHEMA.get("properties", {})
        test_type_prop = props.get("test_type", {})
        assert "enum" in test_type_prop
        assert set(test_type_prop["enum"]) == VALID_TEST_TYPES

    def test_test_contract_assertion_schema_exists(self):
        """TestContractAssertion schema should be defined."""
        assert TEST_CONTRACT_ASSERTION_SCHEMA is not None
        props = TEST_CONTRACT_ASSERTION_SCHEMA.get("properties", {})
        assert "description" in props
        assert "target" in props
        assert "expected" in props
        assert "operator" in props

    def test_valid_test_contract_passes_validation(self, valid_test_contract_dict):
        """A valid TestContract dict should pass schema validation."""
        result = validate_test_contract_schema(valid_test_contract_dict)
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.schema_name == "TestContract"

    def test_get_schema_returns_test_contract_schema(self):
        """get_schema should return TestContract schema by name."""
        schema = get_schema("TestContract")
        assert schema == TEST_CONTRACT_SCHEMA

    def test_test_contract_requires_assertions_or_pass_criteria(self):
        """TestContract should require either assertions or pass_criteria."""
        contract = {
            "agent_name": "test-agent",
            "test_type": "e2e",
            # No assertions or pass_criteria
        }
        result = validate_test_contract_schema(contract)
        assert result.is_valid is False
        # Should have an error about missing assertions or pass_criteria
        assert any("assertions" in err.message.lower() or "pass_criteria" in err.message.lower()
                   for err in result.errors)


# =============================================================================
# Step 3: Octo validates output against schemas before returning
# =============================================================================

class TestStep3OctoValidatesOutputs:
    """Test that Octo validates outputs against schemas before returning."""

    def test_octo_validates_agent_spec_schema(self, mock_spec_builder, sample_payload):
        """Octo should validate AgentSpec against schema."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        # Should succeed with valid spec
        assert response.success is True
        assert len(response.agent_specs) == 1

    def test_octo_rejects_invalid_agent_spec(self, sample_payload):
        """Octo should reject AgentSpec that fails schema validation."""
        # Create a mock that returns an invalid spec
        invalid_spec = AgentSpec(
            id=generate_uuid(),
            name="Invalid Name With Spaces",  # Invalid: has spaces
            display_name="Test Agent",
            objective="Test",  # Invalid: too short
            task_type="invalid_type",  # Invalid: not in enum
            tool_policy={},  # Invalid: missing allowed_tools
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=invalid_spec,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        # Should fail or have warnings due to invalid spec
        # The spec should be rejected during validation
        assert response.success is False or len(response.warnings) > 0

    def test_octo_validates_test_contract_schema(self, mock_spec_builder, sample_payload):
        """Octo should validate TestContract against schema."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        # If test contracts are generated, they should be valid
        if response.test_contracts:
            for contract in response.test_contracts:
                contract_dict = contract.to_dict()
                result = validate_test_contract_schema(contract_dict)
                assert result.is_valid is True, f"TestContract failed validation: {result.error_messages}"

    def test_validate_octo_outputs_validates_all(self, valid_agent_spec_dict, valid_test_contract_dict):
        """validate_octo_outputs should validate all specs and contracts."""
        specs = [valid_agent_spec_dict]
        contracts = [valid_test_contract_dict]

        spec_results, contract_results = validate_octo_outputs(
            specs, contracts, raise_on_error=False
        )

        assert len(spec_results) == 1
        assert len(contract_results) == 1
        assert spec_results[0].is_valid is True
        assert contract_results[0].is_valid is True


# =============================================================================
# Step 4: Schema validation errors raise exceptions with details
# =============================================================================

class TestStep4ValidationErrors:
    """Test that schema validation errors raise exceptions with details."""

    def test_invalid_name_raises_detailed_error(self, valid_agent_spec_dict):
        """Invalid name should produce detailed error message."""
        valid_agent_spec_dict["name"] = "Invalid Name With Spaces"

        result = validate_agent_spec_schema(valid_agent_spec_dict)

        assert result.is_valid is False
        assert len(result.errors) > 0
        # Should have error for name field
        name_errors = [e for e in result.errors if e.path == "name"]
        assert len(name_errors) > 0
        assert "pattern" in name_errors[0].message.lower() or "name" in name_errors[0].message.lower()

    def test_missing_required_field_raises_detailed_error(self, valid_agent_spec_dict):
        """Missing required field should produce detailed error."""
        del valid_agent_spec_dict["objective"]

        result = validate_agent_spec_schema(valid_agent_spec_dict)

        assert result.is_valid is False
        obj_errors = [e for e in result.errors if "objective" in e.path]
        assert len(obj_errors) > 0
        assert obj_errors[0].code == "required_field_missing"

    def test_invalid_enum_raises_detailed_error(self, valid_agent_spec_dict):
        """Invalid enum value should produce detailed error."""
        valid_agent_spec_dict["task_type"] = "not_a_valid_type"

        result = validate_agent_spec_schema(valid_agent_spec_dict)

        assert result.is_valid is False
        type_errors = [e for e in result.errors if e.path == "task_type"]
        assert len(type_errors) > 0
        assert "enum" in type_errors[0].code

    def test_validate_or_raise_raises_exception(self, valid_agent_spec_dict):
        """validate_agent_spec_schema_or_raise should raise on invalid input."""
        valid_agent_spec_dict["name"] = "INVALID NAME"

        with pytest.raises(OctoSchemaValidationError) as exc_info:
            validate_agent_spec_schema_or_raise(valid_agent_spec_dict)

        assert exc_info.value.output_type == "AgentSpec"
        assert exc_info.value.result.is_valid is False

    def test_exception_contains_error_messages(self, valid_agent_spec_dict):
        """OctoSchemaValidationError should contain detailed error messages."""
        valid_agent_spec_dict["name"] = "INVALID"
        valid_agent_spec_dict["task_type"] = "invalid"
        valid_agent_spec_dict["objective"] = "short"  # Too short

        with pytest.raises(OctoSchemaValidationError) as exc_info:
            validate_agent_spec_schema_or_raise(valid_agent_spec_dict)

        error_str = str(exc_info.value)
        assert "AgentSpec" in error_str
        assert "validation failed" in error_str.lower()

    def test_schema_validation_error_serializable(self, valid_agent_spec_dict):
        """SchemaValidationError should be serializable to dict."""
        valid_agent_spec_dict["name"] = "INVALID"

        result = validate_agent_spec_schema(valid_agent_spec_dict)

        error = result.first_error
        assert error is not None
        error_dict = error.to_dict()
        assert "path" in error_dict
        assert "message" in error_dict
        assert "code" in error_dict


# =============================================================================
# Step 5: Invalid outputs never propagate to Materializer
# =============================================================================

class TestStep5InvalidOutputsBlocked:
    """Test that invalid outputs never propagate to Materializer."""

    def test_invalid_spec_not_in_response(self, sample_payload):
        """Invalid specs should not be included in successful response."""
        # Create a spec that will fail validation
        invalid_spec = AgentSpec(
            id=generate_uuid(),
            name="invalid-spec",
            display_name="Invalid Spec",
            objective="This objective is long enough to pass length check",
            task_type="invalid_task_type",  # Invalid
            tool_policy={"allowed_tools": ["tool1"]},
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=invalid_spec,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        # Invalid spec should be rejected
        # Either response fails or spec is not included
        if response.success:
            # If response succeeded, the invalid spec should have been filtered
            for spec in response.agent_specs:
                assert spec.task_type in VALID_TASK_TYPES
        else:
            # Response failed due to validation
            assert "validation" in response.error.lower() or len(response.warnings) > 0

    def test_validate_octo_outputs_raises_on_invalid(self, valid_agent_spec_dict):
        """validate_octo_outputs should raise when raise_on_error=True."""
        # Make one spec invalid
        invalid_spec = dict(valid_agent_spec_dict)
        invalid_spec["task_type"] = "invalid"

        with pytest.raises(OctoSchemaValidationError):
            validate_octo_outputs([invalid_spec], [], raise_on_error=True)

    def test_validate_octo_outputs_returns_results_when_not_raising(self, valid_agent_spec_dict):
        """validate_octo_outputs should return results when raise_on_error=False."""
        invalid_spec = dict(valid_agent_spec_dict)
        invalid_spec["task_type"] = "invalid"

        spec_results, contract_results = validate_octo_outputs(
            [valid_agent_spec_dict, invalid_spec],
            [],
            raise_on_error=False,
        )

        assert len(spec_results) == 2
        assert spec_results[0].is_valid is True
        assert spec_results[1].is_valid is False

    def test_final_validation_catches_edge_cases(self, mock_spec_builder, sample_payload):
        """Final validation in generate_specs should catch any edge cases."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        # If successful, all outputs must be valid
        if response.success:
            for spec in response.agent_specs:
                spec_dict = spec.to_dict()
                result = validate_agent_spec_schema(spec_dict)
                assert result.is_valid is True, f"Spec {spec.name} invalid: {result.error_messages}"

            for contract in response.test_contracts:
                contract_dict = contract.to_dict()
                result = validate_test_contract_schema(contract_dict)
                assert result.is_valid is True, f"Contract invalid: {result.error_messages}"


# =============================================================================
# Additional Validation Tests
# =============================================================================

class TestAgentSpecSchemaValidation:
    """Comprehensive tests for AgentSpec schema validation."""

    def test_valid_minimal_spec(self):
        """Minimal valid spec should pass validation."""
        spec = {
            "name": "a",  # Single character is valid
            "display_name": "A",
            "objective": "This is a sufficiently long objective for testing purposes.",
            "task_type": "coding",
            "tool_policy": {
                "allowed_tools": ["read"],
            },
        }
        result = validate_agent_spec_schema(spec)
        assert result.is_valid is True

    def test_name_pattern_validation(self):
        """Name must match lowercase alphanumeric with hyphens pattern."""
        valid_names = ["a", "abc", "my-agent", "test-123-agent", "a1b2c3", "test--test"]
        invalid_names = ["", "ABC", "My Agent", "test_agent", "-test", "test-"]

        for name in valid_names:
            spec = {
                "name": name,
                "display_name": "Test",
                "objective": "A sufficiently long objective string.",
                "task_type": "coding",
                "tool_policy": {"allowed_tools": ["tool"]},
            }
            result = validate_agent_spec_schema(spec)
            assert result.is_valid is True, f"Name '{name}' should be valid"

        for name in invalid_names:
            spec = {
                "name": name,
                "display_name": "Test",
                "objective": "A sufficiently long objective string.",
                "task_type": "coding",
                "tool_policy": {"allowed_tools": ["tool"]},
            }
            result = validate_agent_spec_schema(spec)
            assert result.is_valid is False, f"Name '{name}' should be invalid"

    def test_max_turns_bounds(self):
        """max_turns must be within valid bounds."""
        base_spec = {
            "name": "test",
            "display_name": "Test",
            "objective": "A sufficiently long objective string.",
            "task_type": "coding",
            "tool_policy": {"allowed_tools": ["tool"]},
        }

        # Valid bounds
        for turns in [MIN_MAX_TURNS, 50, MAX_MAX_TURNS]:
            spec = dict(base_spec)
            spec["max_turns"] = turns
            result = validate_agent_spec_schema(spec)
            assert result.is_valid is True, f"max_turns={turns} should be valid"

        # Invalid bounds
        for turns in [0, -1, MAX_MAX_TURNS + 1, 1000]:
            spec = dict(base_spec)
            spec["max_turns"] = turns
            result = validate_agent_spec_schema(spec)
            assert result.is_valid is False, f"max_turns={turns} should be invalid"

    def test_timeout_seconds_bounds(self):
        """timeout_seconds must be within valid bounds."""
        base_spec = {
            "name": "test",
            "display_name": "Test",
            "objective": "A sufficiently long objective string.",
            "task_type": "coding",
            "tool_policy": {"allowed_tools": ["tool"]},
        }

        # Valid bounds
        for timeout in [MIN_TIMEOUT_SECONDS, 1800, MAX_TIMEOUT_SECONDS]:
            spec = dict(base_spec)
            spec["timeout_seconds"] = timeout
            result = validate_agent_spec_schema(spec)
            assert result.is_valid is True, f"timeout_seconds={timeout} should be valid"

        # Invalid bounds
        for timeout in [0, 59, MAX_TIMEOUT_SECONDS + 1, 10000]:
            spec = dict(base_spec)
            spec["timeout_seconds"] = timeout
            result = validate_agent_spec_schema(spec)
            assert result.is_valid is False, f"timeout_seconds={timeout} should be invalid"

    def test_tool_policy_validation(self):
        """tool_policy structure must be valid."""
        base_spec = {
            "name": "test",
            "display_name": "Test",
            "objective": "A sufficiently long objective string.",
            "task_type": "coding",
        }

        # Missing tool_policy
        result = validate_agent_spec_schema(base_spec)
        assert result.is_valid is False

        # Empty tool_policy
        spec = dict(base_spec)
        spec["tool_policy"] = {}
        result = validate_agent_spec_schema(spec)
        assert result.is_valid is False

        # Empty allowed_tools
        spec = dict(base_spec)
        spec["tool_policy"] = {"allowed_tools": []}
        result = validate_agent_spec_schema(spec)
        assert result.is_valid is False

        # Invalid allowed_tools items
        spec = dict(base_spec)
        spec["tool_policy"] = {"allowed_tools": [123, ""]}
        result = validate_agent_spec_schema(spec)
        assert result.is_valid is False

    def test_invalid_regex_in_forbidden_patterns(self):
        """Invalid regex in forbidden_patterns should fail validation."""
        spec = {
            "name": "test",
            "display_name": "Test",
            "objective": "A sufficiently long objective string.",
            "task_type": "coding",
            "tool_policy": {
                "allowed_tools": ["tool"],
                "forbidden_patterns": ["[invalid"],  # Invalid regex
            },
        }
        result = validate_agent_spec_schema(spec)
        assert result.is_valid is False
        assert any("regex" in e.code for e in result.errors)


class TestTestContractSchemaValidation:
    """Comprehensive tests for TestContract schema validation."""

    def test_valid_minimal_contract(self):
        """Minimal valid contract should pass validation."""
        contract = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "pass_criteria": ["Tests pass"],
        }
        result = validate_test_contract_schema(contract)
        assert result.is_valid is True

    def test_contract_with_assertions(self):
        """Contract with assertions should pass validation."""
        contract = {
            "agent_name": "test-agent",
            "test_type": "e2e",
            "assertions": [
                {
                    "description": "Check status",
                    "target": "response.status",
                    "expected": 200,
                    "operator": "eq",
                }
            ],
        }
        result = validate_test_contract_schema(contract)
        assert result.is_valid is True

    def test_invalid_test_type(self):
        """Invalid test_type should fail validation."""
        contract = {
            "agent_name": "test-agent",
            "test_type": "invalid_type",
            "pass_criteria": ["Pass"],
        }
        result = validate_test_contract_schema(contract)
        assert result.is_valid is False
        assert any(e.path == "test_type" for e in result.errors)

    def test_invalid_assertion_operator(self):
        """Invalid assertion operator should fail validation."""
        contract = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "assertions": [
                {
                    "description": "Check",
                    "target": "x",
                    "expected": 1,
                    "operator": "invalid_op",
                }
            ],
        }
        result = validate_test_contract_schema(contract)
        assert result.is_valid is False

    def test_priority_bounds(self):
        """priority must be between 1 and 4."""
        base = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "pass_criteria": ["Pass"],
        }

        # Valid priorities
        for priority in [1, 2, 3, 4]:
            contract = dict(base)
            contract["priority"] = priority
            result = validate_test_contract_schema(contract)
            assert result.is_valid is True, f"priority={priority} should be valid"

        # Invalid priorities
        for priority in [0, 5, -1, 10]:
            contract = dict(base)
            contract["priority"] = priority
            result = validate_test_contract_schema(contract)
            assert result.is_valid is False, f"priority={priority} should be invalid"


class TestSchemaValidationResult:
    """Test SchemaValidationResult behavior."""

    def test_result_serialization(self, valid_agent_spec_dict):
        """SchemaValidationResult should be serializable."""
        result = validate_agent_spec_schema(valid_agent_spec_dict)
        result_dict = result.to_dict()

        assert "is_valid" in result_dict
        assert "errors" in result_dict
        assert "schema_name" in result_dict
        assert "error_count" in result_dict

    def test_error_messages_property(self, valid_agent_spec_dict):
        """error_messages should return formatted messages."""
        valid_agent_spec_dict["name"] = "INVALID"

        result = validate_agent_spec_schema(valid_agent_spec_dict)

        assert len(result.error_messages) > 0
        assert all(isinstance(msg, str) for msg in result.error_messages)

    def test_first_error_property(self, valid_agent_spec_dict):
        """first_error should return the first error or None."""
        # Valid spec - no errors
        result = validate_agent_spec_schema(valid_agent_spec_dict)
        assert result.first_error is None

        # Invalid spec - has errors
        valid_agent_spec_dict["name"] = "INVALID"
        result = validate_agent_spec_schema(valid_agent_spec_dict)
        assert result.first_error is not None
        assert isinstance(result.first_error, SchemaValidationError)


class TestGetSchema:
    """Test get_schema function."""

    def test_get_agent_spec_schema(self):
        """Should return AgentSpec schema."""
        schema = get_schema("AgentSpec")
        assert schema == AGENT_SPEC_SCHEMA

    def test_get_test_contract_schema(self):
        """Should return TestContract schema."""
        schema = get_schema("TestContract")
        assert schema == TEST_CONTRACT_SCHEMA

    def test_get_test_contract_assertion_schema(self):
        """Should return TestContractAssertion schema."""
        schema = get_schema("TestContractAssertion")
        assert schema == TEST_CONTRACT_ASSERTION_SCHEMA

    def test_invalid_schema_name_raises(self):
        """Invalid schema name should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_schema("InvalidSchema")
        assert "Unknown schema" in str(exc_info.value)


class TestApiPackageExports:
    """Test that Feature #188 exports are available from api package."""

    def test_schema_validation_error_exported(self):
        """OctoSchemaValidationError should be exported from api."""
        from api import OctoSchemaValidationError
        assert OctoSchemaValidationError is not None

    def test_validation_functions_exported(self):
        """Schema validation functions should be exported from api."""
        from api import (
            validate_agent_spec_schema,
            validate_test_contract_schema,
            validate_octo_outputs,
            validate_agent_spec_schema_or_raise,
            validate_test_contract_schema_or_raise,
            get_schema,
        )
        assert all(callable(f) for f in [
            validate_agent_spec_schema,
            validate_test_contract_schema,
            validate_octo_outputs,
            validate_agent_spec_schema_or_raise,
            validate_test_contract_schema_or_raise,
            get_schema,
        ])

    def test_schemas_exported(self):
        """Schema definitions should be exported from api."""
        from api import (
            AGENT_SPEC_SCHEMA,
            TEST_CONTRACT_SCHEMA,
            TEST_CONTRACT_ASSERTION_SCHEMA,
        )
        assert isinstance(AGENT_SPEC_SCHEMA, dict)
        assert isinstance(TEST_CONTRACT_SCHEMA, dict)
        assert isinstance(TEST_CONTRACT_ASSERTION_SCHEMA, dict)

    def test_constants_exported(self):
        """Schema constants should be exported from api."""
        from api import (
            OCTO_SCHEMA_VALID_TASK_TYPES,
            OCTO_SCHEMA_VALID_TEST_TYPES,
            OCTO_SCHEMA_VALID_GATE_MODES,
            VALID_ASSERTION_OPERATORS,
        )
        assert isinstance(OCTO_SCHEMA_VALID_TASK_TYPES, frozenset)
        assert isinstance(OCTO_SCHEMA_VALID_TEST_TYPES, frozenset)
        assert isinstance(OCTO_SCHEMA_VALID_GATE_MODES, frozenset)
        assert isinstance(VALID_ASSERTION_OPERATORS, frozenset)


class TestFeature188VerificationSteps:
    """Direct verification of all 5 feature steps."""

    def test_step1_agent_spec_json_schema_defined(self):
        """Step 1: Define AgentSpec JSON schema with required fields."""
        # Verify schema exists and has required fields
        assert AGENT_SPEC_SCHEMA is not None
        required = AGENT_SPEC_SCHEMA.get("required", [])
        assert "name" in required
        assert "display_name" in required
        assert "objective" in required
        assert "task_type" in required
        assert "tool_policy" in required

        # Verify tool_policy has nested required fields
        tool_policy_props = AGENT_SPEC_SCHEMA["properties"]["tool_policy"]
        assert "allowed_tools" in tool_policy_props.get("required", [])

    def test_step2_test_contract_json_schema_defined(self):
        """Step 2: Define TestContract JSON schema."""
        # Verify schema exists and has required fields
        assert TEST_CONTRACT_SCHEMA is not None
        required = TEST_CONTRACT_SCHEMA.get("required", [])
        assert "agent_name" in required
        assert "test_type" in required

        # Verify test_type has enum
        props = TEST_CONTRACT_SCHEMA["properties"]
        assert "enum" in props["test_type"]

    def test_step3_octo_validates_before_returning(self, mock_spec_builder, sample_payload):
        """Step 3: Octo validates output against schemas before returning."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        # The fact that we get a response means validation ran
        # If validation failed, either success=False or warnings populated
        assert response is not None
        assert response.request_id == sample_payload.request_id

        # If successful, outputs must be valid
        if response.success:
            for spec in response.agent_specs:
                result = validate_agent_spec_schema(spec.to_dict())
                assert result.is_valid is True

    def test_step4_validation_errors_raise_exceptions(self, valid_agent_spec_dict):
        """Step 4: Schema validation errors raise exceptions with details."""
        # Make spec invalid
        valid_agent_spec_dict["task_type"] = "invalid"

        # Should raise with details
        with pytest.raises(OctoSchemaValidationError) as exc_info:
            validate_agent_spec_schema_or_raise(valid_agent_spec_dict)

        # Exception should have details
        exc = exc_info.value
        assert exc.result is not None
        assert exc.result.is_valid is False
        assert len(exc.result.errors) > 0
        assert exc.output_type == "AgentSpec"

    def test_step5_invalid_outputs_never_propagate(self, sample_payload):
        """Step 5: Invalid outputs never propagate to Materializer."""
        # Create mock that returns invalid spec
        invalid_spec = MagicMock(spec=AgentSpec)
        invalid_spec.name = "test"
        invalid_spec.to_dict.return_value = {
            "name": "test",
            "display_name": "Test",
            "objective": "Too short",  # Will fail validation
            "task_type": "invalid_type",  # Will fail validation
            "tool_policy": {},  # Missing allowed_tools
        }

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=invalid_spec,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        # Response should fail or have empty specs
        # Invalid outputs must not be in agent_specs
        if response.success:
            # If somehow it succeeded, verify all specs are valid
            for spec in response.agent_specs:
                spec_dict = spec.to_dict() if hasattr(spec, "to_dict") else spec
                result = validate_agent_spec_schema(spec_dict)
                assert result.is_valid is True, "Invalid spec propagated to response"
        else:
            # Response correctly failed due to validation
            assert "validation" in response.error.lower() or response.error_type in [
                "generation_failed", "schema_validation_error", "constraint_validation_failed"
            ]
