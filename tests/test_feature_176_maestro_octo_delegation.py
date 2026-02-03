"""
Test Feature #176: Maestro delegates to Octo for agent generation
==================================================================

Tests the integration between Maestro and Octo:
1. Maestro calls Octo service/agent with OctoRequestPayload
2. Maestro awaits Octo's response containing AgentSpecs
3. Maestro validates returned AgentSpecs against schema
4. Maestro records agent_planned audit event for each spec
"""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base, Feature
from api.agentspec_models import (
    AgentSpec,
    AcceptanceSpec,
    AgentRun,
    AgentEvent,
    EVENT_TYPES,
    generate_uuid,
)
from api.maestro import (
    Maestro,
    AgentPlanningDecision,
    CapabilityRequirement,
    ProjectContext,
    OctoDelegationResult,
    get_maestro,
    reset_maestro,
)
from api.octo import (
    Octo,
    OctoRequestPayload,
    OctoResponse,
    get_octo,
    reset_octo,
)
from api.spec_validator import SpecValidationResult
from api.event_recorder import EventRecorder, get_event_recorder, clear_recorder_cache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_agent_spec():
    """Create a sample AgentSpec for testing."""
    spec_id = generate_uuid()
    spec = AgentSpec(
        id=spec_id,
        name="test-playwright-e2e",
        display_name="Test Playwright E2E",
        icon="test-tube",
        spec_version="v1",
        objective="Implement E2E tests using Playwright",
        task_type="testing",
        context={"capability": "e2e_testing"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["browser_navigate", "browser_click"],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=1800,
        tags=["testing", "playwright"],
    )
    return spec


@pytest.fixture
def sample_decision():
    """Create a sample AgentPlanningDecision for testing."""
    return AgentPlanningDecision(
        requires_agent_planning=True,
        required_capabilities=[
            CapabilityRequirement(
                capability="playwright",
                source="tech_stack",
                keywords_matched=["playwright", "e2e test"],
                confidence="high",
            )
        ],
        existing_capabilities=["coding", "testing"],
        justification="Agent-planning required: 1 specialized capabilities detected",
        recommended_agent_types=["playwright_e2e"],
    )


@pytest.fixture
def sample_project_context():
    """Create a sample ProjectContext for testing."""
    return ProjectContext(
        project_name="test-project",
        tech_stack=["python", "playwright", "react"],
        features=[
            {"name": "E2E Login Test", "description": "E2E test for login flow"},
        ],
        existing_agents=["coding", "testing"],
    )


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances before each test."""
    reset_maestro()
    reset_octo()
    clear_recorder_cache()
    yield
    reset_maestro()
    reset_octo()
    clear_recorder_cache()


# =============================================================================
# Test: agent_planned event type exists
# =============================================================================

def test_agent_planned_event_type_exists():
    """Verify that 'agent_planned' is in EVENT_TYPES."""
    assert "agent_planned" in EVENT_TYPES, (
        "agent_planned event type must be in EVENT_TYPES for Feature #176/221"
    )


# =============================================================================
# Test: OctoRequestPayload
# =============================================================================

def test_octo_request_payload_creation():
    """Test OctoRequestPayload can be created with required fields."""
    payload = OctoRequestPayload(
        project_context={"name": "test-project", "tech_stack": ["python"]},
        required_capabilities=["e2e_testing"],
        existing_agents=["coder", "tester"],
        constraints={"max_agents": 3},
    )

    assert payload.project_context["name"] == "test-project"
    assert payload.required_capabilities == ["e2e_testing"]
    assert payload.existing_agents == ["coder", "tester"]
    assert payload.constraints["max_agents"] == 3
    assert payload.request_id is not None


def test_octo_request_payload_validation_success():
    """Test OctoRequestPayload validation passes for valid payload."""
    payload = OctoRequestPayload(
        project_context={"name": "test"},
        required_capabilities=["capability_1"],
    )
    errors = payload.validate()
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_octo_request_payload_validation_empty_capabilities():
    """Test OctoRequestPayload validation fails for empty capabilities."""
    payload = OctoRequestPayload(
        project_context={"name": "test"},
        required_capabilities=[],  # Empty
    )
    errors = payload.validate()
    assert len(errors) > 0
    assert any("empty" in e.lower() for e in errors)


def test_octo_request_payload_to_dict():
    """Test OctoRequestPayload serialization."""
    payload = OctoRequestPayload(
        project_context={"name": "test"},
        required_capabilities=["cap1"],
        source_feature_ids=[1, 2],
    )
    d = payload.to_dict()
    assert "project_context" in d
    assert "required_capabilities" in d
    assert d["source_feature_ids"] == [1, 2]


# =============================================================================
# Test: OctoResponse
# =============================================================================

def test_octo_response_success():
    """Test OctoResponse for successful generation."""
    response = OctoResponse(
        success=True,
        agent_specs=[MagicMock(to_dict=lambda: {"name": "test"})],
        request_id="test-123",
    )
    assert response.success is True
    assert len(response.agent_specs) == 1


def test_octo_response_failure():
    """Test OctoResponse for failed generation."""
    response = OctoResponse(
        success=False,
        error="DSPy execution failed",
        error_type="execution",
    )
    assert response.success is False
    assert response.error == "DSPy execution failed"


# =============================================================================
# Test: Octo Service
# =============================================================================

def test_octo_capability_covered():
    """Test Octo._capability_covered detects existing coverage."""
    octo = Octo()

    # Direct match
    assert octo._capability_covered("coding", ["coder"]) is True

    # Partial match
    assert octo._capability_covered("testing", ["test-runner"]) is True

    # No match
    assert octo._capability_covered("playwright", ["coder", "tester"]) is False


def test_octo_infer_task_type():
    """Test Octo._infer_task_type maps capabilities to task types."""
    octo = Octo()

    assert octo._infer_task_type("e2e_testing") == "testing"
    assert octo._infer_task_type("ui_testing") == "testing"
    assert octo._infer_task_type("documentation") == "documentation"
    assert octo._infer_task_type("security_audit") == "audit"
    assert octo._infer_task_type("refactoring") == "refactoring"
    assert octo._infer_task_type("unknown") == "coding"  # Default


def test_octo_build_task_description():
    """Test Octo._build_task_description generates sensible descriptions."""
    octo = Octo()

    payload = OctoRequestPayload(
        project_context={"name": "MyApp", "tech_stack": ["python", "react"]},
        required_capabilities=["ui_testing"],
    )

    desc = octo._build_task_description("ui_testing", payload)
    assert "MyApp" in desc
    assert "python, react" in desc


# =============================================================================
# Test: Maestro delegate_to_octo
# =============================================================================

def test_maestro_delegate_to_octo_success(in_memory_db, sample_decision, sample_agent_spec):
    """Test Maestro.delegate_to_octo returns valid specs on success."""
    maestro = get_maestro()

    # Mock Octo to return a successful response
    mock_response = OctoResponse(
        success=True,
        agent_specs=[sample_agent_spec],
        request_id="test-request",
    )

    with patch("api.octo.get_octo") as mock_get_octo:
        mock_octo = MagicMock()
        mock_octo.generate_specs.return_value = mock_response
        mock_get_octo.return_value = mock_octo

        result = maestro.delegate_to_octo(
            sample_decision,
            in_memory_db,
            project_dir="/tmp/test",
        )

    assert result.success is True
    assert len(result.agent_specs) == 1
    assert result.agent_specs[0].name == "test-playwright-e2e"
    assert result.error is None


def test_maestro_delegate_to_octo_failure(in_memory_db, sample_decision):
    """Test Maestro.delegate_to_octo handles Octo failures."""
    maestro = get_maestro()

    # Mock Octo to return a failure
    mock_response = OctoResponse(
        success=False,
        error="DSPy execution failed",
        error_type="execution",
    )

    with patch("api.octo.get_octo") as mock_get_octo:
        mock_octo = MagicMock()
        mock_octo.generate_specs.return_value = mock_response
        mock_get_octo.return_value = mock_octo

        result = maestro.delegate_to_octo(
            sample_decision,
            in_memory_db,
        )

    assert result.success is False
    assert result.error == "DSPy execution failed"


def test_maestro_delegate_to_octo_exception(in_memory_db, sample_decision):
    """Test Maestro.delegate_to_octo handles exceptions gracefully."""
    maestro = get_maestro()

    with patch("api.octo.get_octo") as mock_get_octo:
        mock_octo = MagicMock()
        mock_octo.generate_specs.side_effect = Exception("Connection failed")
        mock_get_octo.return_value = mock_octo

        result = maestro.delegate_to_octo(
            sample_decision,
            in_memory_db,
        )

    assert result.success is False
    assert "Octo invocation failed" in result.error


# =============================================================================
# Test: Maestro records agent_planned events
# =============================================================================

def test_maestro_records_agent_planned_event(in_memory_db, sample_decision, sample_agent_spec):
    """Test Maestro.delegate_to_octo records agent_planned events for each spec."""
    maestro = get_maestro()

    # Create a run to associate events with
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    # Mock Octo response
    mock_response = OctoResponse(
        success=True,
        agent_specs=[sample_agent_spec],
        request_id="test-request",
    )

    with patch("api.octo.get_octo") as mock_get_octo:
        mock_octo = MagicMock()
        mock_octo.generate_specs.return_value = mock_response
        mock_get_octo.return_value = mock_octo

        result = maestro.delegate_to_octo(
            sample_decision,
            in_memory_db,
            project_dir="/tmp/test",
            run_id=run.id,
        )

    assert result.success is True
    assert len(result.event_ids) == 1, "Should record one agent_planned event"

    # Verify the event was recorded in the database
    events = in_memory_db.query(AgentEvent).filter(
        AgentEvent.run_id == run.id,
        AgentEvent.event_type == "agent_planned",
    ).all()

    assert len(events) == 1
    assert events[0].payload["agent_name"] == "test-playwright-e2e"


def test_maestro_record_agent_planned_public_method(in_memory_db, sample_agent_spec):
    """Test Maestro.record_agent_planned public method."""
    maestro = get_maestro()

    # Create a run
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    event_id = maestro.record_agent_planned(
        in_memory_db,
        run.id,
        sample_agent_spec,
        rationale="Custom rationale for testing",
        capabilities=["e2e_testing", "browser_automation"],
    )

    assert event_id is not None

    # Verify the event
    event = in_memory_db.query(AgentEvent).filter(
        AgentEvent.id == event_id,
    ).first()

    assert event is not None
    assert event.event_type == "agent_planned"
    assert event.payload["rationale"] == "Custom rationale for testing"
    assert event.payload["capabilities"] == ["e2e_testing", "browser_automation"]


# =============================================================================
# Test: EventRecorder.record_agent_planned
# =============================================================================

def test_event_recorder_record_agent_planned(in_memory_db):
    """Test EventRecorder.record_agent_planned convenience method."""
    # Create a run
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    recorder = get_event_recorder(in_memory_db, "/tmp/test")

    event_id = recorder.record_agent_planned(
        run.id,
        agent_name="test-agent",
        display_name="Test Agent",
        task_type="testing",
        capabilities=["cap1", "cap2"],
        rationale="Testing the event recording",
    )

    assert event_id is not None

    # Verify the event
    event = in_memory_db.query(AgentEvent).filter(
        AgentEvent.id == event_id,
    ).first()

    assert event is not None
    assert event.event_type == "agent_planned"
    assert event.payload["agent_name"] == "test-agent"
    assert event.payload["display_name"] == "Test Agent"
    assert event.payload["task_type"] == "testing"
    assert event.payload["capabilities"] == ["cap1", "cap2"]
    assert event.payload["rationale"] == "Testing the event recording"


# =============================================================================
# Test: Schema Validation
# =============================================================================

def test_maestro_validates_returned_specs(in_memory_db, sample_decision):
    """Test Maestro.delegate_to_octo validates AgentSpecs against schema."""
    maestro = get_maestro()

    # Create an invalid spec (missing required fields)
    invalid_spec = AgentSpec(
        id=generate_uuid(),
        name="",  # Invalid: empty name
        display_name="",  # Invalid: empty display_name
        objective="",  # Invalid: empty objective
        task_type="invalid_type",  # Invalid: not in TASK_TYPES
        tool_policy={},  # Invalid: missing required fields
        max_turns=50,
        timeout_seconds=1800,
    )

    mock_response = OctoResponse(
        success=True,
        agent_specs=[invalid_spec],
        request_id="test-request",
    )

    with patch("api.octo.get_octo") as mock_get_octo:
        mock_octo = MagicMock()
        mock_octo.generate_specs.return_value = mock_response
        mock_get_octo.return_value = mock_octo

        result = maestro.delegate_to_octo(
            sample_decision,
            in_memory_db,
        )

    # Should fail validation - no valid specs
    assert result.success is False or len(result.agent_specs) == 0
    assert len(result.warnings) > 0, "Should have validation warnings"


# =============================================================================
# Test: OctoDelegationResult
# =============================================================================

def test_octo_delegation_result_to_dict(sample_agent_spec):
    """Test OctoDelegationResult.to_dict serialization."""
    result = OctoDelegationResult(
        success=True,
        agent_specs=[sample_agent_spec],
        validation_results=[SpecValidationResult(is_valid=True, errors=[])],
        event_ids=[1, 2, 3],
        warnings=["Warning 1"],
    )

    d = result.to_dict()
    assert d["success"] is True
    assert len(d["agent_specs"]) == 1
    assert d["event_ids"] == [1, 2, 3]
    assert d["warnings"] == ["Warning 1"]


# =============================================================================
# Test: Full Integration (End-to-End)
# =============================================================================

def test_feature_176_e2e_workflow(in_memory_db, sample_project_context, sample_agent_spec):
    """
    End-to-end test for Feature #176:
    1. Maestro evaluates project and decides agent planning is needed
    2. Maestro delegates to Octo with OctoRequestPayload
    3. Octo returns AgentSpecs
    4. Maestro validates specs and records agent_planned events
    """
    maestro = get_maestro()

    # Step 1: Evaluate project
    decision = maestro.evaluate(sample_project_context)

    # Should detect playwright capability requirement
    assert decision.requires_agent_planning is True
    assert any(
        req.capability == "playwright"
        for req in decision.required_capabilities
    )

    # Step 2-4: Delegate to Octo (mocked)
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    mock_response = OctoResponse(
        success=True,
        agent_specs=[sample_agent_spec],
        request_id="test-request",
    )

    with patch("api.octo.get_octo") as mock_get_octo:
        mock_octo = MagicMock()
        mock_octo.generate_specs.return_value = mock_response
        mock_get_octo.return_value = mock_octo

        result = maestro.delegate_to_octo(
            decision,
            in_memory_db,
            project_dir="/tmp/test",
            run_id=run.id,
        )

    # Verify the full workflow succeeded
    assert result.success is True, f"Delegation failed: {result.error}"
    assert len(result.agent_specs) == 1
    assert len(result.event_ids) == 1

    # Verify event was recorded
    event = in_memory_db.query(AgentEvent).filter(
        AgentEvent.event_type == "agent_planned"
    ).first()
    assert event is not None
    assert event.payload["agent_name"] == sample_agent_spec.name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
