"""
Test Feature #180: Maestro handles Octo failures gracefully
============================================================

Tests the graceful failure handling when Octo fails to generate AgentSpecs:
1. Octo invocation wrapped in error handling
2. On failure, Maestro logs error with full context
3. Maestro falls back to default/existing agents
4. Failure recorded as audit event with error details
5. Feature execution continues with available agents
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
    OctoDelegationWithFallbackResult,
    DEFAULT_AGENTS,
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
# Step 1: Verify octo_failure event type exists
# =============================================================================

def test_octo_failure_event_type_exists():
    """Verify that 'octo_failure' is in EVENT_TYPES."""
    assert "octo_failure" in EVENT_TYPES, (
        "octo_failure event type must be in EVENT_TYPES for Feature #180"
    )


# =============================================================================
# Step 2: Test Octo invocation wrapped in error handling
# =============================================================================

def test_delegate_to_octo_with_fallback_exception_handling(in_memory_db, sample_decision):
    """Test that Octo invocation is wrapped in error handling (Step 1)."""
    maestro = get_maestro()

    # Mock delegate_to_octo to raise an exception
    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Connection failed")

        # Should not raise - error handling should catch it
        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
        )

    # Verify exception was caught
    assert result.success is False
    assert "Octo invocation exception" in result.error
    assert "Connection failed" in result.error
    assert result.error_type == "exception"


def test_delegate_to_octo_with_fallback_handles_octo_failure_response(
    in_memory_db, sample_decision
):
    """Test handling when Octo returns a failure response."""
    maestro = get_maestro()

    # Mock delegate_to_octo to return failure result
    mock_result = OctoDelegationResult(
        success=False,
        error="DSPy execution failed",
        warnings=[],
    )

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.return_value = mock_result

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
        )

    assert result.success is False
    assert "DSPy execution failed" in result.error
    assert result.error_type == "generation_failed"


def test_delegate_to_octo_with_fallback_handles_empty_specs(
    in_memory_db, sample_decision
):
    """Test handling when Octo returns success but no valid specs."""
    maestro = get_maestro()

    # Mock delegate_to_octo to return success but with empty specs
    mock_result = OctoDelegationResult(
        success=True,
        agent_specs=[],  # Empty - no valid specs generated
    )

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.return_value = mock_result

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
        )

    # Should fall back since no valid specs
    assert result.success is False
    assert result.fallback_used is True


# =============================================================================
# Step 3: Test Maestro falls back to default/existing agents
# =============================================================================

def test_delegate_to_octo_with_fallback_returns_default_agents(
    in_memory_db, sample_decision
):
    """Test that Maestro falls back to default/existing agents on failure (Step 3)."""
    maestro = get_maestro()

    # Mock delegate_to_octo to raise exception
    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Connection timeout")

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
        )

    # Verify fallback was triggered
    assert result.fallback_used is True

    # Verify available_agents includes existing capabilities
    assert "coding" in result.available_agents
    assert "testing" in result.available_agents

    # Verify default agents are included
    for default_agent in DEFAULT_AGENTS:
        assert default_agent in result.available_agents


def test_delegate_to_octo_with_fallback_preserves_existing_agents(
    in_memory_db
):
    """Test that fallback preserves all existing agents."""
    # Create decision with specific existing agents
    decision = AgentPlanningDecision(
        requires_agent_planning=True,
        required_capabilities=[
            CapabilityRequirement(
                capability="playwright",
                source="tech_stack",
                keywords_matched=["playwright"],
                confidence="medium",
            )
        ],
        existing_capabilities=["custom_agent_1", "custom_agent_2"],
        justification="Test",
        recommended_agent_types=["playwright_e2e"],
    )

    maestro = get_maestro()

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Failure")

        result = maestro.delegate_to_octo_with_fallback(
            decision,
            in_memory_db,
        )

    # Verify custom agents are preserved
    assert "custom_agent_1" in result.available_agents
    assert "custom_agent_2" in result.available_agents


# =============================================================================
# Step 4: Test failure recorded as audit event
# =============================================================================

def test_delegate_to_octo_with_fallback_records_failure_event(
    in_memory_db, sample_decision
):
    """Test that failure is recorded as audit event with error details (Step 4)."""
    maestro = get_maestro()

    # Create a run to associate events with
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    # Mock delegate_to_octo to fail
    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Network error")

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
            project_dir="/tmp/test",
            run_id=run.id,
        )

    # Verify event was recorded
    assert len(result.event_ids) == 1

    # Verify the event in the database
    events = in_memory_db.query(AgentEvent).filter(
        AgentEvent.run_id == run.id,
        AgentEvent.event_type == "octo_failure",
    ).all()

    assert len(events) == 1
    event = events[0]

    # Verify event payload contains error details
    assert "Network error" in event.payload["error"]
    assert event.payload["error_type"] == "exception"
    assert event.payload["required_capabilities"] == ["playwright"]
    assert "coding" in event.payload["fallback_agents"]
    assert "testing" in event.payload["fallback_agents"]


def test_delegate_to_octo_with_fallback_records_context_in_event(
    in_memory_db, sample_decision
):
    """Test that audit event includes full context."""
    maestro = get_maestro()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("API Error")

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
            project_dir="/tmp/test",
            run_id=run.id,
        )

    event = in_memory_db.query(AgentEvent).filter(
        AgentEvent.event_type == "octo_failure"
    ).first()

    # Verify context is included
    assert "context" in event.payload
    context = event.payload["context"]
    assert "decision_justification" in context
    assert "recommended_agent_types" in context
    assert "playwright_e2e" in context["recommended_agent_types"]


# =============================================================================
# Step 5: Test feature execution continues with available agents
# =============================================================================

def test_delegate_to_octo_with_fallback_can_continue_execution(
    in_memory_db, sample_decision
):
    """Test that feature execution can continue with available agents (Step 5)."""
    maestro = get_maestro()

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Failure")

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
        )

    # Verify execution can continue
    assert result.can_continue_execution is True
    assert len(result.available_agents) > 0


def test_delegate_to_octo_with_fallback_success_path(
    in_memory_db, sample_decision, sample_agent_spec
):
    """Test the success path when Octo succeeds."""
    maestro = get_maestro()

    # Mock delegate_to_octo to succeed
    mock_result = OctoDelegationResult(
        success=True,
        agent_specs=[sample_agent_spec],
        event_ids=[1],
        warnings=[],
    )

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.return_value = mock_result

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
        )

    # Verify success path
    assert result.success is True
    assert result.fallback_used is False
    assert len(result.agent_specs) == 1
    assert result.can_continue_execution is True
    assert sample_agent_spec.name in result.available_agents


# =============================================================================
# Test OctoDelegationWithFallbackResult data class
# =============================================================================

def test_octo_delegation_with_fallback_result_to_dict(sample_agent_spec):
    """Test OctoDelegationWithFallbackResult.to_dict serialization."""
    result = OctoDelegationWithFallbackResult(
        success=False,
        agent_specs=[],
        fallback_used=True,
        available_agents=["coding", "testing"],
        event_ids=[1],
        error="Test error",
        error_type="test",
        warnings=["Warning 1"],
    )

    d = result.to_dict()
    assert d["success"] is False
    assert d["fallback_used"] is True
    assert d["available_agents"] == ["coding", "testing"]
    assert d["can_continue_execution"] is True
    assert d["error"] == "Test error"
    assert d["error_type"] == "test"


def test_octo_delegation_with_fallback_result_can_continue_true():
    """Test can_continue_execution is True when agents available."""
    result = OctoDelegationWithFallbackResult(
        success=False,
        fallback_used=True,
        available_agents=["coding"],
    )
    assert result.can_continue_execution is True


def test_octo_delegation_with_fallback_result_can_continue_true_with_specs():
    """Test can_continue_execution is True when specs generated."""
    spec = MagicMock()
    result = OctoDelegationWithFallbackResult(
        success=True,
        agent_specs=[spec],
        fallback_used=False,
    )
    assert result.can_continue_execution is True


def test_octo_delegation_with_fallback_result_can_continue_false():
    """Test can_continue_execution is False when no agents or specs."""
    result = OctoDelegationWithFallbackResult(
        success=False,
        agent_specs=[],
        fallback_used=True,
        available_agents=[],  # Empty!
    )
    assert result.can_continue_execution is False


# =============================================================================
# Test EventRecorder.record_octo_failure
# =============================================================================

def test_event_recorder_record_octo_failure(in_memory_db):
    """Test EventRecorder.record_octo_failure convenience method."""
    # Create a run
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    recorder = get_event_recorder(in_memory_db, "/tmp/test")

    event_id = recorder.record_octo_failure(
        run.id,
        error="Connection timeout",
        error_type="network",
        required_capabilities=["playwright", "cypress"],
        fallback_agents=["coding", "testing"],
        context={"extra_info": "test"},
    )

    assert event_id is not None

    # Verify the event
    event = in_memory_db.query(AgentEvent).filter(
        AgentEvent.id == event_id,
    ).first()

    assert event is not None
    assert event.event_type == "octo_failure"
    assert event.payload["error"] == "Connection timeout"
    assert event.payload["error_type"] == "network"
    assert event.payload["required_capabilities"] == ["playwright", "cypress"]
    assert event.payload["fallback_agents"] == ["coding", "testing"]
    assert event.payload["context"]["extra_info"] == "test"


# =============================================================================
# Integration Test: Full workflow
# =============================================================================

def test_feature_180_e2e_workflow(
    in_memory_db, sample_project_context, sample_decision
):
    """
    End-to-end test for Feature #180:
    1. Octo invocation is wrapped in error handling
    2. On failure, Maestro logs error with full context
    3. Maestro falls back to default/existing agents
    4. Failure recorded as audit event with error details
    5. Feature execution continues with available agents
    """
    maestro = get_maestro()

    # Create a run
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=generate_uuid(),
        status="running",
    )
    in_memory_db.add(run)
    in_memory_db.commit()

    # Mock delegate_to_octo to fail
    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Service unavailable")

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
            project_dir="/tmp/test",
            run_id=run.id,
        )

    # Step 1: Error handling caught the exception
    assert "Octo invocation exception" in result.error

    # Step 3: Fallback to default agents
    assert result.fallback_used is True
    assert "coding" in result.available_agents
    assert "testing" in result.available_agents

    # Step 4: Failure recorded as audit event
    events = in_memory_db.query(AgentEvent).filter(
        AgentEvent.event_type == "octo_failure"
    ).all()
    assert len(events) == 1
    event = events[0]
    assert "Service unavailable" in event.payload["error"]
    assert event.payload["required_capabilities"] == ["playwright"]

    # Step 5: Execution can continue
    assert result.can_continue_execution is True


def test_feature_180_no_event_without_run_id(in_memory_db, sample_decision):
    """Test that no event is recorded when run_id is not provided."""
    maestro = get_maestro()

    with patch.object(maestro, "delegate_to_octo") as mock_delegate:
        mock_delegate.side_effect = Exception("Error")

        result = maestro.delegate_to_octo_with_fallback(
            sample_decision,
            in_memory_db,
            # No run_id provided
        )

    # Should still work but no event recorded
    assert result.fallback_used is True
    assert len(result.event_ids) == 0

    # Verify no events in DB
    events = in_memory_db.query(AgentEvent).filter(
        AgentEvent.event_type == "octo_failure"
    ).all()
    assert len(events) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
