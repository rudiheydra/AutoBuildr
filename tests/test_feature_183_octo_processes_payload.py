"""
Test Feature #183: Octo processes OctoRequestPayload and returns AgentSpecs
============================================================================

This test suite verifies that Octo correctly processes structured request payloads
from Maestro and returns validated AgentSpec objects via the DSPy pipeline.

Feature Steps:
1. Octo receives OctoRequestPayload with project context
2. Octo invokes DSPy pipeline with payload
3. DSPy reasons about required agents based on capabilities
4. Octo returns list of AgentSpec objects
5. Each AgentSpec is complete and valid
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

from api.octo import (
    Octo,
    OctoRequestPayload,
    OctoResponse,
    get_octo,
    reset_octo,
)
from api.agentspec_models import (
    AgentSpec,
    AcceptanceSpec,
    TASK_TYPES,
    generate_uuid,
)
from api.spec_builder import (
    SpecBuilder,
    BuildResult,
)
from api.spec_validator import (
    validate_spec,
    SpecValidationResult,
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
def sample_payload():
    """Create a sample OctoRequestPayload for testing."""
    return OctoRequestPayload(
        project_context={
            "name": "TestApp",
            "tech_stack": ["python", "react", "fastapi"],
            "app_spec_summary": "A full-stack web application for task management",
            "directory_structure": ["src/", "tests/", "api/"],
        },
        required_capabilities=["e2e_testing", "api_testing"],
        existing_agents=["coder", "test-runner"],
        constraints={
            "max_agents": 3,
            "model": "sonnet",
        },
        source_feature_ids=[1, 2, 3],
    )


@pytest.fixture
def sample_agent_spec():
    """Create a sample AgentSpec for testing."""
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
        acceptance_spec=AcceptanceSpec(
            validators=[],
        ),
    )
    return mock_builder


# =============================================================================
# Step 1: Octo receives OctoRequestPayload with project context
# =============================================================================

class TestStep1PayloadReceiving:
    """Test that Octo correctly receives and processes OctoRequestPayload."""

    def test_octo_receives_valid_payload(self, mock_spec_builder, sample_payload):
        """Octo should accept a valid OctoRequestPayload."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        # Should not fail due to payload issues
        assert response.request_id == sample_payload.request_id

    def test_octo_extracts_project_context(self, mock_spec_builder, sample_payload):
        """Octo should extract and use project context from payload."""
        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(sample_payload)

        # Verify SpecBuilder was called with context from payload
        assert mock_spec_builder.build.called
        call_kwargs = mock_spec_builder.build.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context", {})
        assert context["project_context"] == sample_payload.project_context

    def test_octo_validates_payload_structure(self):
        """Octo should validate the payload structure before processing."""
        invalid_payload = OctoRequestPayload(
            project_context="not a dict",  # Should be dict
            required_capabilities=[],  # Should be non-empty
        )

        octo = Octo()
        response = octo.generate_specs(invalid_payload)

        assert response.success is False
        assert response.error_type == "validation_error"
        assert len(response.validation_errors) > 0

    def test_octo_handles_empty_capabilities(self):
        """Octo should reject payload with empty required_capabilities."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=[],  # Empty
        )

        octo = Octo()
        response = octo.generate_specs(payload)

        assert response.success is False
        assert "required_capabilities cannot be empty" in str(response.validation_errors)

    def test_octo_accepts_payload_with_minimal_context(self, mock_spec_builder):
        """Octo should accept payload with minimal but valid context."""
        minimal_payload = OctoRequestPayload(
            project_context={"name": "MinimalApp"},
            required_capabilities=["coding"],
        )

        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(minimal_payload)

        # Should process without validation errors
        assert response.error_type != "validation_error"

    def test_payload_request_id_preserved(self, mock_spec_builder, sample_payload):
        """Octo should preserve the request_id in the response."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        assert response.request_id == sample_payload.request_id


# =============================================================================
# Step 2: Octo invokes DSPy pipeline with payload
# =============================================================================

class TestStep2DSPyInvocation:
    """Test that Octo correctly invokes the DSPy pipeline (via SpecBuilder)."""

    def test_octo_calls_spec_builder(self, mock_spec_builder, sample_payload):
        """Octo should call SpecBuilder.build() for each capability."""
        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(sample_payload)

        # Should be called once per capability (2 capabilities)
        assert mock_spec_builder.build.call_count == 2

    def test_octo_passes_task_description(self, mock_spec_builder, sample_payload):
        """Octo should generate appropriate task descriptions for each capability."""
        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(sample_payload)

        # Get all call arguments
        calls = mock_spec_builder.build.call_args_list

        # First capability: e2e_testing
        task_desc_1 = calls[0].kwargs.get("task_description") or calls[0][0][0]
        assert "e2e" in task_desc_1.lower() or "end-to-end" in task_desc_1.lower()

        # Second capability: api_testing
        task_desc_2 = calls[1].kwargs.get("task_description") or calls[1][0][0]
        assert "api" in task_desc_2.lower()

    def test_octo_infers_task_type_from_capability(self, mock_spec_builder, sample_payload):
        """Octo should infer the correct task_type from capability name."""
        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(sample_payload)

        calls = mock_spec_builder.build.call_args_list

        # Both capabilities are testing-related
        for call in calls:
            task_type = call.kwargs.get("task_type") or call[0][1]
            assert task_type == "testing"

    def test_octo_passes_context_to_builder(self, mock_spec_builder, sample_payload):
        """Octo should pass context including project_context to SpecBuilder."""
        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(sample_payload)

        call_kwargs = mock_spec_builder.build.call_args
        context = call_kwargs.kwargs.get("context") or call_kwargs[1].get("context", {})

        assert "capability" in context
        assert "project_context" in context
        assert "octo_request_id" in context
        assert context["project_context"]["name"] == "TestApp"

    def test_octo_handles_spec_builder_failure(self, sample_payload):
        """Octo should handle SpecBuilder failures gracefully."""
        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=False,
            error="DSPy execution failed",
            error_type="execution",
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        # Should report failure but not crash
        assert response.success is False
        assert "No valid specs generated" in response.error

    def test_octo_handles_spec_builder_exception(self, sample_payload):
        """Octo should handle exceptions from SpecBuilder."""
        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.side_effect = Exception("Unexpected error")

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        # Should capture exception in warnings
        assert any("Exception" in w for w in response.warnings)


# =============================================================================
# Step 3: DSPy reasons about required agents based on capabilities
# =============================================================================

class TestStep3CapabilityReasoning:
    """Test that Octo/DSPy reasons about required agents based on capabilities."""

    def test_octo_maps_capability_to_task_type(self, mock_spec_builder):
        """Octo should map capabilities to appropriate task types."""
        octo = Octo(spec_builder=mock_spec_builder)

        # Test various capability to task_type mappings
        test_cases = [
            ("e2e_testing", "testing"),
            ("api_testing", "testing"),
            ("unit_testing", "testing"),
            ("documentation", "documentation"),
            ("security_audit", "audit"),
            ("refactoring", "refactoring"),
            ("code_review", "audit"),
            ("deployment", "coding"),  # Default to coding
        ]

        for capability, expected_type in test_cases:
            result = octo._infer_task_type(capability)
            assert result == expected_type, f"Expected {expected_type} for {capability}, got {result}"

    def test_octo_skips_covered_capabilities(self, mock_spec_builder):
        """Octo should skip capabilities already covered by existing agents."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["coding", "testing", "e2e_testing"],
            existing_agents=["coder", "test-runner"],  # These cover coding and testing
        )

        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(payload)

        # Only e2e_testing should trigger spec generation
        # (coding covered by "coder", testing covered by "test-runner")
        calls = mock_spec_builder.build.call_args_list
        assert len(calls) == 1

        # Check warnings mention skipped capabilities
        assert any("covered by existing agent" in w for w in response.warnings)

    def test_octo_builds_rich_task_descriptions(self, mock_spec_builder):
        """Octo should build rich task descriptions with project context."""
        payload = OctoRequestPayload(
            project_context={
                "name": "MyProject",
                "tech_stack": ["python", "django", "react"],
            },
            required_capabilities=["ui_testing"],
        )

        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(payload)

        call_args = mock_spec_builder.build.call_args
        task_desc = call_args.kwargs.get("task_description") or call_args[0][0]

        # Should include project name and tech stack
        assert "MyProject" in task_desc
        assert "python" in task_desc.lower() or "django" in task_desc.lower() or "react" in task_desc.lower()

    def test_octo_handles_unknown_capability(self, mock_spec_builder):
        """Octo should handle unknown capabilities with sensible defaults."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["unknown_capability"],
        )

        octo = Octo(spec_builder=mock_spec_builder)
        octo.generate_specs(payload)

        call_args = mock_spec_builder.build.call_args
        task_type = call_args.kwargs.get("task_type") or call_args[0][1]

        # Should default to "coding" for unknown capabilities
        assert task_type == "coding"


# =============================================================================
# Step 4: Octo returns list of AgentSpec objects
# =============================================================================

class TestStep4ReturnAgentSpecs:
    """Test that Octo returns a list of AgentSpec objects."""

    def test_octo_returns_octo_response(self, mock_spec_builder, sample_payload):
        """Octo should return an OctoResponse object."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        assert isinstance(response, OctoResponse)

    def test_octo_response_contains_agent_specs(self, mock_spec_builder, sample_payload, sample_agent_spec):
        """OctoResponse should contain generated AgentSpecs."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        assert response.success is True
        assert len(response.agent_specs) > 0
        assert all(isinstance(spec, AgentSpec) for spec in response.agent_specs)

    def test_octo_returns_multiple_specs(self, sample_payload):
        """Octo should return multiple specs for multiple capabilities."""
        spec1 = AgentSpec(
            id=generate_uuid(),
            name="e2e-agent",
            display_name="E2E Agent",
            icon="test-tube",
            spec_version="v1",
            objective="E2E testing",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": ["Read", "Write", "Bash"]},
            max_turns=50,
            timeout_seconds=1800,
        )
        spec2 = AgentSpec(
            id=generate_uuid(),
            name="api-agent",
            display_name="API Agent",
            icon="api",
            spec_version="v1",
            objective="API testing",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": ["Read", "WebFetch", "Bash"]},
            max_turns=50,
            timeout_seconds=1800,
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.side_effect = [
            BuildResult(success=True, agent_spec=spec1),
            BuildResult(success=True, agent_spec=spec2),
        ]

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        assert response.success is True
        assert len(response.agent_specs) == 2

    def test_octo_response_success_flag(self, mock_spec_builder, sample_payload):
        """OctoResponse should set success=True when specs are generated."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        assert response.success is True

    def test_octo_response_failure_flag(self, sample_payload):
        """OctoResponse should set success=False when no specs are generated."""
        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=False,
            error="Failed to generate spec",
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        assert response.success is False
        assert response.error is not None

    def test_octo_response_includes_warnings(self, mock_spec_builder, sample_payload):
        """OctoResponse should include any warnings from the generation process."""
        # Set up payload with a capability covered by existing agent
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing", "e2e_testing"],
            existing_agents=["test-runner"],
        )

        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(payload)

        # Should have a warning about skipped capability
        assert any("covered by existing agent" in w for w in response.warnings)

    def test_octo_response_to_dict(self, mock_spec_builder, sample_payload):
        """OctoResponse should serialize to dictionary correctly."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        response_dict = response.to_dict()

        assert "success" in response_dict
        assert "agent_specs" in response_dict
        assert "error" in response_dict
        assert "warnings" in response_dict
        assert "request_id" in response_dict


# =============================================================================
# Step 5: Each AgentSpec is complete and valid
# =============================================================================

class TestStep5SpecValidation:
    """Test that each generated AgentSpec is complete and valid."""

    def test_octo_validates_each_spec(self, sample_payload):
        """Octo should validate each generated spec against the schema."""
        valid_spec = AgentSpec(
            id=generate_uuid(),
            name="valid-agent",
            display_name="Valid Agent",
            icon="check",
            spec_version="v1",
            objective="Do something valid",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": ["Read", "Write"]},
            max_turns=50,
            timeout_seconds=1800,
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=valid_spec,
        )

        octo = Octo(spec_builder=mock_builder)

        with patch("api.octo.validate_spec") as mock_validate:
            mock_validate.return_value = SpecValidationResult(is_valid=True, errors=[])
            response = octo.generate_specs(sample_payload)

            # validate_spec should be called for each generated spec
            assert mock_validate.called

    def test_octo_rejects_invalid_specs(self, sample_payload):
        """Octo should reject specs that fail validation."""
        invalid_spec = AgentSpec(
            id=generate_uuid(),
            name="invalid-agent",
            display_name="Invalid Agent",
            icon="x",
            spec_version="v1",
            objective="",  # Empty objective might fail validation
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": []},
            max_turns=50,
            timeout_seconds=1800,
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=invalid_spec,
        )

        octo = Octo(spec_builder=mock_builder)

        with patch("api.octo.validate_spec") as mock_validate:
            mock_validate.return_value = SpecValidationResult(
                is_valid=False,
                errors=["objective cannot be empty"],
            )
            response = octo.generate_specs(sample_payload)

            # Should have warnings about validation failure
            assert any("validation" in w.lower() for w in response.warnings)

    def test_generated_spec_has_required_fields(self, mock_spec_builder, sample_payload, sample_agent_spec):
        """Generated specs should have all required fields."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        for spec in response.agent_specs:
            # Required fields based on AgentSpec schema
            assert spec.id is not None
            assert spec.name is not None and len(spec.name) > 0
            assert spec.display_name is not None
            assert spec.spec_version is not None
            assert spec.objective is not None
            assert spec.task_type is not None
            assert spec.task_type in TASK_TYPES
            assert spec.tool_policy is not None
            assert spec.max_turns is not None and spec.max_turns > 0
            assert spec.timeout_seconds is not None and spec.timeout_seconds > 0

    def test_generated_spec_tool_policy_valid(self, mock_spec_builder, sample_payload, sample_agent_spec):
        """Generated specs should have valid tool_policy structure."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        for spec in response.agent_specs:
            policy = spec.tool_policy
            assert isinstance(policy, dict)
            assert "policy_version" in policy
            assert "allowed_tools" in policy
            assert isinstance(policy["allowed_tools"], list)

    def test_spec_passes_validate_spec(self, mock_spec_builder, sample_payload, sample_agent_spec):
        """Generated specs should pass the validate_spec function."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        for spec in response.agent_specs:
            # Actually validate (not mocked)
            result = validate_spec(spec)
            assert result.is_valid, f"Spec validation failed: {result.errors}"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the complete Octo workflow."""

    def test_end_to_end_spec_generation(self, mock_spec_builder, sample_payload, sample_agent_spec):
        """Test complete flow from payload to validated specs."""
        octo = Octo(spec_builder=mock_spec_builder)
        response = octo.generate_specs(sample_payload)

        # Verify complete flow
        assert response.success is True
        assert len(response.agent_specs) > 0
        assert response.request_id == sample_payload.request_id

        # Each spec should be valid
        for spec in response.agent_specs:
            assert spec.id is not None
            assert spec.name is not None
            assert spec.task_type in TASK_TYPES

    def test_singleton_get_octo(self):
        """Test get_octo returns singleton instance."""
        octo1 = get_octo()
        octo2 = get_octo()

        assert octo1 is octo2

    def test_singleton_reset_octo(self):
        """Test reset_octo clears singleton."""
        octo1 = get_octo()
        reset_octo()
        octo2 = get_octo()

        assert octo1 is not octo2

    def test_octo_with_api_key(self):
        """Test Octo can be initialized with API key."""
        # This tests the initialization path, actual API calls are mocked
        octo = Octo(api_key="test-key")
        assert octo._api_key == "test-key"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_octo_handles_all_capabilities_skipped(self):
        """Octo should handle case where all capabilities are already covered."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["coding", "testing"],
            existing_agents=["coder", "test-runner"],
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(payload)

        # No specs generated because all are covered
        assert response.success is False
        assert "No valid specs generated" in response.error
        assert mock_builder.build.call_count == 0

    def test_octo_handles_partial_success(self, sample_agent_spec):
        """Octo should return partial results when some capabilities fail."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["e2e_testing", "api_testing"],
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.side_effect = [
            BuildResult(success=True, agent_spec=sample_agent_spec),
            BuildResult(success=False, error="Failed"),
        ]

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(payload)

        # Should still succeed with partial results
        assert response.success is True
        assert len(response.agent_specs) == 1
        assert len(response.warnings) > 0

    def test_octo_handles_invalid_project_context_type(self):
        """Octo should reject invalid project_context type."""
        payload = OctoRequestPayload(
            project_context=["not", "a", "dict"],  # Invalid type
            required_capabilities=["testing"],
        )

        octo = Octo()
        response = octo.generate_specs(payload)

        assert response.success is False
        assert "project_context must be a dictionary" in str(response.validation_errors)

    def test_octo_handles_invalid_capabilities_type(self):
        """Octo should reject invalid required_capabilities type."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities="not a list",  # Invalid type
        )

        octo = Octo()
        response = octo.generate_specs(payload)

        assert response.success is False
        assert "required_capabilities must be a list" in str(response.validation_errors)

    def test_octo_handles_whitespace_capability(self):
        """Octo should reject whitespace-only capability names."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["   ", "valid_capability"],
        )

        octo = Octo()
        response = octo.generate_specs(payload)

        assert response.success is False
        assert "must be a non-empty string" in str(response.validation_errors)


# =============================================================================
# OctoRequestPayload Tests
# =============================================================================

class TestOctoRequestPayload:
    """Test OctoRequestPayload data class."""

    def test_payload_to_dict(self, sample_payload):
        """OctoRequestPayload should serialize to dictionary."""
        payload_dict = sample_payload.to_dict()

        assert "project_context" in payload_dict
        assert "required_capabilities" in payload_dict
        assert "existing_agents" in payload_dict
        assert "constraints" in payload_dict
        assert "source_feature_ids" in payload_dict
        assert "request_id" in payload_dict

    def test_payload_from_dict(self, sample_payload):
        """OctoRequestPayload should deserialize from dictionary."""
        payload_dict = sample_payload.to_dict()
        restored = OctoRequestPayload.from_dict(payload_dict)

        assert restored.project_context == sample_payload.project_context
        assert restored.required_capabilities == sample_payload.required_capabilities
        assert restored.existing_agents == sample_payload.existing_agents
        assert restored.constraints == sample_payload.constraints

    def test_payload_generates_request_id(self):
        """OctoRequestPayload should generate a request_id if not provided."""
        payload = OctoRequestPayload(
            project_context={"name": "Test"},
            required_capabilities=["testing"],
        )

        assert payload.request_id is not None
        assert len(payload.request_id) > 0

    def test_payload_validate_success(self, sample_payload):
        """Valid payload should pass validation."""
        errors = sample_payload.validate()
        assert len(errors) == 0

    def test_payload_validate_errors(self):
        """Invalid payload should return validation errors."""
        payload = OctoRequestPayload(
            project_context="invalid",
            required_capabilities=[],
        )

        errors = payload.validate()
        assert len(errors) > 0


# =============================================================================
# OctoResponse Tests
# =============================================================================

class TestOctoResponse:
    """Test OctoResponse data class."""

    def test_response_to_dict_success(self, sample_agent_spec):
        """Successful OctoResponse should serialize correctly."""
        response = OctoResponse(
            success=True,
            agent_specs=[sample_agent_spec],
            request_id="test-123",
        )

        response_dict = response.to_dict()

        assert response_dict["success"] is True
        assert len(response_dict["agent_specs"]) == 1
        assert response_dict["request_id"] == "test-123"

    def test_response_to_dict_failure(self):
        """Failed OctoResponse should serialize correctly."""
        response = OctoResponse(
            success=False,
            error="Something went wrong",
            error_type="test_error",
            validation_errors=["Error 1", "Error 2"],
            request_id="test-456",
        )

        response_dict = response.to_dict()

        assert response_dict["success"] is False
        assert response_dict["error"] == "Something went wrong"
        assert response_dict["error_type"] == "test_error"
        assert len(response_dict["validation_errors"]) == 2

    def test_response_with_warnings(self, sample_agent_spec):
        """OctoResponse should include warnings."""
        response = OctoResponse(
            success=True,
            agent_specs=[sample_agent_spec],
            warnings=["Warning 1", "Warning 2"],
        )

        assert len(response.warnings) == 2
        assert response.to_dict()["warnings"] == ["Warning 1", "Warning 2"]
