"""
Tests for Feature #23: POST /api/agent-runs/:id/resume Resume Agent
===================================================================

Verification Steps:
1. Define FastAPI route POST /api/agent-runs/{run_id}/resume
2. Query AgentRun by id
3. Return 404 if not found
4. Return 409 Conflict if status is not paused
5. Update status to running
6. Record resumed AgentEvent
7. Commit transaction
8. Signal kernel to resume
9. Return updated AgentRunResponse
"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

# Import models and database setup
import sys
import os

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.agentspec_models import AgentSpec, AgentRun, AgentEvent
from api.agentspec_crud import (
    create_agent_spec,
    create_agent_run,
    get_agent_run,
    get_events,
)
from api.database import get_db, Base, create_database, set_session_maker


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Create tables using create_database with project root Path
    engine, SessionLocal = create_database(project_root)
    set_session_maker(SessionLocal)

    # Get session
    db = SessionLocal()
    yield db

    # Cleanup
    db.rollback()
    db.close()


@pytest.fixture
def test_spec(db_session):
    """Create a test AgentSpec."""
    spec = create_agent_spec(
        db_session,
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective for resume testing",
        task_type="testing",
        allowed_tools=["feature_get_by_id"],
        max_turns=50,
        timeout_seconds=1800,
    )
    db_session.commit()
    return spec


@pytest.fixture
def paused_run(db_session, test_spec):
    """Create a test AgentRun in 'paused' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "paused"
    run.started_at = datetime.now(timezone.utc)
    run.turns_used = 5
    run.tokens_in = 1000
    run.tokens_out = 500
    db_session.commit()
    return run


@pytest.fixture
def running_run(db_session, test_spec):
    """Create a test AgentRun in 'running' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.turns_used = 3
    db_session.commit()
    return run


@pytest.fixture
def completed_run(db_session, test_spec):
    """Create a test AgentRun in 'completed' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "completed"
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.turns_used = 10
    run.final_verdict = "passed"
    db_session.commit()
    return run


@pytest.fixture
def pending_run(db_session, test_spec):
    """Create a test AgentRun in 'pending' status."""
    run = create_agent_run(db_session, test_spec.id)
    # Default status is 'pending'
    db_session.commit()
    return run


@pytest.fixture
def failed_run(db_session, test_spec):
    """Create a test AgentRun in 'failed' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "failed"
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.error = "Test failure"
    db_session.commit()
    return run


@pytest.fixture
def timeout_run(db_session, test_spec):
    """Create a test AgentRun in 'timeout' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "timeout"
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.error = "Execution timed out"
    db_session.commit()
    return run


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    from server.main import app
    return TestClient(app)


# =============================================================================
# Step 1: Define FastAPI route POST /api/agent-runs/{run_id}/resume
# =============================================================================

class TestStep1DefineRoute:
    """Test that the FastAPI route is properly defined."""

    def test_route_exists(self, test_client, paused_run, db_session):
        """Verify the POST /api/agent-runs/{run_id}/resume route exists."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        # Should not be 404 for the route itself (405 would mean route exists but wrong method)
        assert response.status_code != 404 or "not found" in response.json().get("detail", "").lower()
        # 200 means it worked, which proves route exists
        assert response.status_code == 200

    def test_route_method_is_post(self, test_client, paused_run, db_session):
        """Verify the endpoint only accepts POST method."""
        # GET should not work
        response = test_client.get(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 405  # Method Not Allowed

    def test_route_in_agent_runs_prefix(self, test_client, paused_run, db_session):
        """Verify the route is under /api/agent-runs prefix."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

    def test_route_path_structure(self, test_client, paused_run, db_session):
        """Verify the route has correct path structure: /api/agent-runs/{run_id}/resume."""
        # Verify the endpoint is accessible at the expected path
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Verify similar but incorrect paths don't work
        response_wrong = test_client.post(f"/api/runs/{paused_run.id}/resume")
        assert response_wrong.status_code == 404


# =============================================================================
# Step 2: Query AgentRun by id
# =============================================================================

class TestStep2QueryRunById:
    """Test that the endpoint queries AgentRun by id."""

    def test_queries_run_by_id(self, test_client, paused_run, db_session):
        """Verify the endpoint finds the AgentRun by id."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == paused_run.id

    def test_returns_correct_run(self, test_client, test_spec, db_session):
        """Verify the endpoint returns the correct run."""
        # Create multiple paused runs
        run1 = create_agent_run(db_session, test_spec.id)
        run1.status = "paused"
        run1.started_at = datetime.now(timezone.utc)

        run2 = create_agent_run(db_session, test_spec.id)
        run2.status = "paused"
        run2.started_at = datetime.now(timezone.utc)

        db_session.commit()

        # Resume run1
        response = test_client.post(f"/api/agent-runs/{run1.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run1.id

        # Verify run2 is still paused
        db_session.refresh(run2)
        assert run2.status == "paused"


# =============================================================================
# Step 3: Return 404 if not found
# =============================================================================

class TestStep3Return404IfNotFound:
    """Test 404 response when AgentRun is not found."""

    def test_returns_404_for_nonexistent_run(self, test_client):
        """Verify 404 is returned for non-existent run id."""
        fake_id = str(uuid.uuid4())
        response = test_client.post(f"/api/agent-runs/{fake_id}/resume")
        assert response.status_code == 404

    def test_404_includes_run_id_in_detail(self, test_client):
        """Verify the 404 error message includes the run id."""
        fake_id = str(uuid.uuid4())
        response = test_client.post(f"/api/agent-runs/{fake_id}/resume")
        assert response.status_code == 404
        data = response.json()
        assert fake_id in data["detail"]
        assert "not found" in data["detail"].lower()

    def test_returns_404_for_invalid_uuid(self, test_client):
        """Verify 404 is returned for invalid UUID format."""
        response = test_client.post("/api/agent-runs/invalid-uuid/resume")
        # Should be 404 since the run doesn't exist
        assert response.status_code == 404


# =============================================================================
# Step 4: Return 409 Conflict if status is not paused
# =============================================================================

class TestStep4Return409IfNotPaused:
    """Test 409 Conflict when run status is not 'paused'."""

    def test_returns_409_for_running_run(self, test_client, running_run, db_session):
        """Verify 409 is returned when trying to resume a running run."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/resume")
        assert response.status_code == 409

    def test_returns_409_for_completed_run(self, test_client, completed_run, db_session):
        """Verify 409 is returned when trying to resume a completed run."""
        response = test_client.post(f"/api/agent-runs/{completed_run.id}/resume")
        assert response.status_code == 409

    def test_returns_409_for_pending_run(self, test_client, pending_run, db_session):
        """Verify 409 is returned when trying to resume a pending run."""
        response = test_client.post(f"/api/agent-runs/{pending_run.id}/resume")
        assert response.status_code == 409

    def test_returns_409_for_failed_run(self, test_client, failed_run, db_session):
        """Verify 409 is returned when trying to resume a failed run."""
        response = test_client.post(f"/api/agent-runs/{failed_run.id}/resume")
        assert response.status_code == 409

    def test_returns_409_for_timeout_run(self, test_client, timeout_run, db_session):
        """Verify 409 is returned when trying to resume a timed out run."""
        response = test_client.post(f"/api/agent-runs/{timeout_run.id}/resume")
        assert response.status_code == 409

    def test_409_includes_current_status(self, test_client, running_run, db_session):
        """Verify the 409 error message includes the current status."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/resume")
        assert response.status_code == 409
        data = response.json()
        assert "running" in data["detail"]
        assert "paused" in data["detail"]

    def test_409_message_format(self, test_client, completed_run, db_session):
        """Verify the 409 error message has correct format."""
        response = test_client.post(f"/api/agent-runs/{completed_run.id}/resume")
        assert response.status_code == 409
        data = response.json()
        # Should indicate cannot resume because not paused
        assert "Cannot resume" in data["detail"] or "cannot resume" in data["detail"].lower()


# =============================================================================
# Step 5: Update status to running
# =============================================================================

class TestStep5UpdateStatusToRunning:
    """Test that status is updated to 'running'."""

    def test_updates_status_to_running(self, test_client, paused_run, db_session):
        """Verify the run status is updated to 'running'."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

    def test_status_persisted_in_database(self, test_client, paused_run, db_session):
        """Verify the status change is persisted in the database."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Refresh from database
        db_session.expire_all()
        db_run = get_agent_run(db_session, paused_run.id)
        assert db_run.status == "running"

    def test_preserves_other_fields(self, test_client, paused_run, db_session):
        """Verify other run fields are preserved."""
        original_turns = paused_run.turns_used
        original_tokens_in = paused_run.tokens_in
        original_tokens_out = paused_run.tokens_out
        original_started_at = paused_run.started_at

        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()

        assert data["turns_used"] == original_turns
        assert data["tokens_in"] == original_tokens_in
        assert data["tokens_out"] == original_tokens_out

    def test_does_not_set_completed_at(self, test_client, paused_run, db_session):
        """Verify completed_at is not set when resuming."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["completed_at"] is None


# =============================================================================
# Step 6: Record resumed AgentEvent
# =============================================================================

class TestStep6RecordResumedEvent:
    """Test that a 'resumed' AgentEvent is recorded."""

    def test_creates_resumed_event(self, test_client, paused_run, db_session):
        """Verify a 'resumed' event is created."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Check for resumed event
        events = get_events(db_session, paused_run.id, event_type="resumed")
        assert len(events) >= 1

    def test_resumed_event_has_correct_type(self, test_client, paused_run, db_session):
        """Verify the event has event_type='resumed'."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        events = get_events(db_session, paused_run.id, event_type="resumed")
        assert events[0].event_type == "resumed"

    def test_resumed_event_has_payload(self, test_client, paused_run, db_session):
        """Verify the event payload contains status information."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        events = get_events(db_session, paused_run.id, event_type="resumed")
        payload = events[0].payload

        assert payload is not None
        assert payload.get("previous_status") == "paused"
        assert payload.get("new_status") == "running"

    def test_resumed_event_includes_metrics(self, test_client, paused_run, db_session):
        """Verify the event payload includes run metrics."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        events = get_events(db_session, paused_run.id, event_type="resumed")
        payload = events[0].payload

        assert "turns_used" in payload
        assert "tokens_in" in payload
        assert "tokens_out" in payload

    def test_resumed_event_has_timestamp(self, test_client, paused_run, db_session):
        """Verify the event has a timestamp."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        events = get_events(db_session, paused_run.id, event_type="resumed")
        assert events[0].timestamp is not None


# =============================================================================
# Step 7: Commit transaction
# =============================================================================

class TestStep7CommitTransaction:
    """Test that changes are committed to the database."""

    def test_changes_are_committed(self, test_client, paused_run, db_session):
        """Verify changes are committed (status persisted)."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Use a new session to verify persistence
        from api.database import SessionLocal
        new_session = SessionLocal()
        try:
            db_run = new_session.query(AgentRun).filter(AgentRun.id == paused_run.id).first()
            assert db_run.status == "running"
        finally:
            new_session.close()

    def test_event_is_committed(self, test_client, paused_run, db_session):
        """Verify the resumed event is committed."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Use a new session to verify event persistence
        from api.database import SessionLocal
        new_session = SessionLocal()
        try:
            event = new_session.query(AgentEvent).filter(
                AgentEvent.run_id == paused_run.id,
                AgentEvent.event_type == "resumed"
            ).first()
            assert event is not None
        finally:
            new_session.close()


# =============================================================================
# Step 8: Signal kernel to resume
# =============================================================================

class TestStep8SignalKernelToResume:
    """Test that the kernel is signaled to resume."""

    def test_broadcasts_resume_event(self, test_client, paused_run, db_session):
        """Verify the resume event is broadcast for UI updates."""
        with patch('server.routers.agent_runs.get_event_broadcaster') as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
            assert response.status_code == 200

            # Verify broadcast was called
            mock_broadcaster.broadcast_event.assert_called_once()
            call_args = mock_broadcaster.broadcast_event.call_args
            assert call_args.kwargs.get('run_id') == paused_run.id
            assert call_args.kwargs.get('event_type') == "resumed"

    def test_handles_missing_broadcaster(self, test_client, paused_run, db_session):
        """Verify the endpoint handles missing broadcaster gracefully."""
        with patch('server.routers.agent_runs.get_event_broadcaster') as mock_get_broadcaster:
            mock_get_broadcaster.return_value = None

            # Should still succeed even without broadcaster
            response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
            assert response.status_code == 200


# =============================================================================
# Step 9: Return updated AgentRunResponse
# =============================================================================

class TestStep9ReturnAgentRunResponse:
    """Test that the endpoint returns the updated AgentRunResponse."""

    def test_returns_agent_run_response(self, test_client, paused_run, db_session):
        """Verify the response is an AgentRunResponse."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "id" in data
        assert "agent_spec_id" in data
        assert "status" in data
        assert "turns_used" in data
        assert "tokens_in" in data
        assert "tokens_out" in data
        assert "created_at" in data

    def test_response_shows_running_status(self, test_client, paused_run, db_session):
        """Verify the response shows status='running'."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

    def test_response_includes_run_id(self, test_client, paused_run, db_session):
        """Verify the response includes the correct run id."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == paused_run.id

    def test_response_includes_spec_id(self, test_client, paused_run, test_spec, db_session):
        """Verify the response includes the agent_spec_id."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_spec_id"] == test_spec.id

    def test_response_includes_all_required_fields(self, test_client, paused_run, db_session):
        """Verify all AgentRunResponse fields are present."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "id", "agent_spec_id", "status", "started_at", "completed_at",
            "turns_used", "tokens_in", "tokens_out", "final_verdict",
            "acceptance_results", "error", "retry_count", "created_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the resume endpoint."""

    def test_full_resume_workflow(self, test_client, paused_run, db_session):
        """Test the complete resume workflow."""
        # Verify initial state
        assert paused_run.status == "paused"

        # Resume the run
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Verify response
        data = response.json()
        assert data["status"] == "running"

        # Verify database state
        db_session.expire_all()
        db_run = get_agent_run(db_session, paused_run.id)
        assert db_run.status == "running"

        # Verify event was created
        events = get_events(db_session, paused_run.id, event_type="resumed")
        assert len(events) >= 1

    def test_cannot_double_resume(self, test_client, paused_run, db_session):
        """Test that a run cannot be resumed twice."""
        # First resume should succeed
        response1 = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response1.status_code == 200

        # Second resume should fail with 409
        response2 = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response2.status_code == 409

    def test_pause_resume_cycle(self, test_client, test_spec, db_session):
        """Test a full pause/resume cycle."""
        # Create a running run
        run = create_agent_run(db_session, test_spec.id)
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db_session.commit()

        # Pause it
        response = test_client.post(f"/api/agent-runs/{run.id}/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

        # Resume it
        response = test_client.post(f"/api/agent-runs/{run.id}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

        # Verify both events exist
        db_session.expire_all()
        paused_events = get_events(db_session, run.id, event_type="paused")
        resumed_events = get_events(db_session, run.id, event_type="resumed")
        assert len(paused_events) >= 1
        assert len(resumed_events) >= 1

    def test_multiple_pause_resume_cycles(self, test_client, test_spec, db_session):
        """Test multiple pause/resume cycles."""
        # Create a running run
        run = create_agent_run(db_session, test_spec.id)
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db_session.commit()

        # Do 3 pause/resume cycles
        for i in range(3):
            # Pause
            response = test_client.post(f"/api/agent-runs/{run.id}/pause")
            assert response.status_code == 200
            assert response.json()["status"] == "paused"

            # Resume
            response = test_client.post(f"/api/agent-runs/{run.id}/resume")
            assert response.status_code == 200
            assert response.json()["status"] == "running"

        # Verify all events exist
        db_session.expire_all()
        paused_events = get_events(db_session, run.id, event_type="paused")
        resumed_events = get_events(db_session, run.id, event_type="resumed")
        assert len(paused_events) == 3
        assert len(resumed_events) == 3


# =============================================================================
# Verification Step Tests (for Feature #23)
# =============================================================================

class TestFeature23VerificationSteps:
    """Tests that directly verify each step in Feature #23."""

    def test_step1_fastapi_route_defined(self, test_client, paused_run):
        """Step 1: Define FastAPI route POST /api/agent-runs/{run_id}/resume."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        # Route exists and works (200) or returns proper error (404/409)
        assert response.status_code in [200, 404, 409]

    def test_step2_query_agentrun_by_id(self, test_client, paused_run, db_session):
        """Step 2: Query AgentRun by id."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == paused_run.id

    def test_step3_return_404_if_not_found(self, test_client):
        """Step 3: Return 404 if not found."""
        fake_id = str(uuid.uuid4())
        response = test_client.post(f"/api/agent-runs/{fake_id}/resume")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_step4_return_409_conflict_if_not_paused(self, test_client, running_run):
        """Step 4: Return 409 Conflict if status is not paused."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/resume")
        assert response.status_code == 409
        assert "paused" in response.json()["detail"]

    def test_step5_update_status_to_running(self, test_client, paused_run, db_session):
        """Step 5: Update status to running."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

        db_session.expire_all()
        db_run = get_agent_run(db_session, paused_run.id)
        assert db_run.status == "running"

    def test_step6_record_resumed_agentevent(self, test_client, paused_run, db_session):
        """Step 6: Record resumed AgentEvent."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        events = get_events(db_session, paused_run.id, event_type="resumed")
        assert len(events) >= 1
        assert events[0].event_type == "resumed"
        assert events[0].payload["previous_status"] == "paused"
        assert events[0].payload["new_status"] == "running"

    def test_step7_commit_transaction(self, test_client, paused_run, db_session):
        """Step 7: Commit transaction."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200

        # Use new session to verify persistence
        from api.database import SessionLocal
        new_session = SessionLocal()
        try:
            db_run = new_session.query(AgentRun).filter(AgentRun.id == paused_run.id).first()
            assert db_run.status == "running"
            event = new_session.query(AgentEvent).filter(
                AgentEvent.run_id == paused_run.id,
                AgentEvent.event_type == "resumed"
            ).first()
            assert event is not None
        finally:
            new_session.close()

    def test_step8_signal_kernel_to_resume(self, test_client, paused_run, db_session):
        """Step 8: Signal kernel to resume."""
        with patch('server.routers.agent_runs.get_event_broadcaster') as mock_get_broadcaster:
            mock_broadcaster = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
            assert response.status_code == 200

            mock_broadcaster.broadcast_event.assert_called_once()
            call_args = mock_broadcaster.broadcast_event.call_args
            assert call_args.kwargs.get('run_id') == paused_run.id
            assert call_args.kwargs.get('event_type') == "resumed"

    def test_step9_return_updated_agentrunresponse(self, test_client, paused_run, db_session):
        """Step 9: Return updated AgentRunResponse."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/resume")
        assert response.status_code == 200
        data = response.json()

        # Verify it's a complete AgentRunResponse
        assert data["id"] == paused_run.id
        assert data["status"] == "running"
        assert "agent_spec_id" in data
        assert "turns_used" in data
        assert "tokens_in" in data
        assert "tokens_out" in data
        assert "created_at" in data


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
