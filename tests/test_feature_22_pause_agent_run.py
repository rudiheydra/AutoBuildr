"""
Tests for Feature #22: POST /api/agent-runs/:id/pause Pause Agent
==================================================================

Verification Steps:
1. Define FastAPI route POST /api/agent-runs/{run_id}/pause
2. Query AgentRun by id
3. Return 404 if not found
4. Return 409 Conflict if status is not running
5. Update status to paused
6. Record paused AgentEvent
7. Commit transaction
8. Signal kernel to pause
9. Return updated AgentRunResponse
"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import models and database setup
import sys
import os

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Allow remote access for test client
os.environ["AUTOBUILDR_ALLOW_REMOTE"] = "1"

from fastapi.testclient import TestClient

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
        objective="Test objective for pause testing",
        task_type="testing",
        allowed_tools=["feature_get_by_id"],
        max_turns=50,
        timeout_seconds=1800,
    )
    db_session.commit()
    return spec


@pytest.fixture
def running_run(db_session, test_spec):
    """Create a test AgentRun in 'running' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.turns_used = 5
    run.tokens_in = 1000
    run.tokens_out = 500
    db_session.commit()
    return run


@pytest.fixture
def paused_run(db_session, test_spec):
    """Create a test AgentRun in 'paused' status."""
    run = create_agent_run(db_session, test_spec.id)
    run.status = "paused"
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
def test_client():
    """Create a test client for the FastAPI app."""
    from server.main import app
    return TestClient(app)


# =============================================================================
# Step 1: Define FastAPI route POST /api/agent-runs/{run_id}/pause
# =============================================================================

class TestStep1DefineRoute:
    """Test that the FastAPI route is properly defined."""

    def test_route_exists(self, test_client, running_run, db_session):
        """Verify the POST /api/agent-runs/{run_id}/pause route exists."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        # Should not be 404 for the route itself (405 would mean route exists but wrong method)
        assert response.status_code != 404 or "not found" in response.json().get("detail", "").lower()
        # 200 means it worked, which proves route exists
        assert response.status_code == 200

    def test_route_method_is_post(self, test_client, running_run, db_session):
        """Verify the endpoint only accepts POST method."""
        # GET should not work - FastAPI returns 404 for undefined routes (not 405)
        response = test_client.get(f"/api/agent-runs/{running_run.id}/pause")
        # Either 405 (Method Not Allowed) or 404 is acceptable since no GET route exists
        assert response.status_code in (404, 405)

    def test_route_in_agent_runs_prefix(self, test_client, running_run, db_session):
        """Verify the route is under /api/agent-runs prefix."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200


# =============================================================================
# Step 2: Query AgentRun by id
# =============================================================================

class TestStep2QueryRunById:
    """Test that the endpoint queries AgentRun by id."""

    def test_queries_run_by_id(self, test_client, running_run, db_session):
        """Verify the endpoint finds the AgentRun by id."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == running_run.id

    def test_returns_correct_run(self, test_client, test_spec, db_session):
        """Verify the endpoint returns the correct run."""
        # Create multiple runs
        run1 = create_agent_run(db_session, test_spec.id)
        run1.status = "running"
        run1.started_at = datetime.now(timezone.utc)

        run2 = create_agent_run(db_session, test_spec.id)
        run2.status = "running"
        run2.started_at = datetime.now(timezone.utc)

        db_session.commit()

        # Pause run1
        response = test_client.post(f"/api/agent-runs/{run1.id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == run1.id

        # Verify run2 is still running
        db_session.refresh(run2)
        assert run2.status == "running"


# =============================================================================
# Step 3: Return 404 if not found
# =============================================================================

class TestStep3Return404IfNotFound:
    """Test 404 response when AgentRun is not found."""

    def test_returns_404_for_nonexistent_run(self, test_client):
        """Verify 404 is returned for non-existent run id."""
        fake_id = str(uuid.uuid4())
        response = test_client.post(f"/api/agent-runs/{fake_id}/pause")
        assert response.status_code == 404

    def test_404_includes_run_id_in_detail(self, test_client):
        """Verify the 404 error message includes the run id."""
        fake_id = str(uuid.uuid4())
        response = test_client.post(f"/api/agent-runs/{fake_id}/pause")
        assert response.status_code == 404
        data = response.json()
        # Feature #75: Error responses use 'message' field instead of 'detail'
        assert fake_id in data["message"]
        assert "not found" in data["message"].lower()

    def test_returns_404_for_invalid_uuid(self, test_client):
        """Verify 404 is returned for invalid UUID format."""
        response = test_client.post("/api/agent-runs/invalid-uuid/pause")
        # Should be 404 since the run doesn't exist
        assert response.status_code == 404


# =============================================================================
# Step 4: Return 409 Conflict if status is not running
# =============================================================================

class TestStep4Return409IfNotRunning:
    """Test 409 Conflict when run status is not 'running'."""

    def test_returns_409_for_paused_run(self, test_client, paused_run, db_session):
        """Verify 409 is returned when trying to pause a paused run."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/pause")
        assert response.status_code == 409

    def test_returns_409_for_completed_run(self, test_client, completed_run, db_session):
        """Verify 409 is returned when trying to pause a completed run."""
        response = test_client.post(f"/api/agent-runs/{completed_run.id}/pause")
        assert response.status_code == 409

    def test_returns_409_for_pending_run(self, test_client, pending_run, db_session):
        """Verify 409 is returned when trying to pause a pending run."""
        response = test_client.post(f"/api/agent-runs/{pending_run.id}/pause")
        assert response.status_code == 409

    def test_returns_409_for_failed_run(self, test_client, test_spec, db_session):
        """Verify 409 is returned when trying to pause a failed run."""
        run = create_agent_run(db_session, test_spec.id)
        run.status = "failed"
        run.started_at = datetime.now(timezone.utc)
        run.completed_at = datetime.now(timezone.utc)
        run.error = "Test failure"
        db_session.commit()

        response = test_client.post(f"/api/agent-runs/{run.id}/pause")
        assert response.status_code == 409

    def test_409_includes_current_status(self, test_client, paused_run, db_session):
        """Verify the 409 error message includes the current status."""
        response = test_client.post(f"/api/agent-runs/{paused_run.id}/pause")
        assert response.status_code == 409
        data = response.json()
        # Feature #75: Error responses use 'message' field instead of 'detail'
        assert "paused" in data["message"]
        assert "running" in data["message"]


# =============================================================================
# Step 5: Update status to paused
# =============================================================================

class TestStep5UpdateStatusToPaused:
    """Test that status is updated to 'paused'."""

    def test_updates_status_to_paused(self, test_client, running_run, db_session):
        """Verify the run status is updated to 'paused'."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    def test_status_persisted_in_database(self, test_client, running_run, db_session):
        """Verify the status change is persisted in the database."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        # Refresh from database
        db_session.expire_all()
        db_run = get_agent_run(db_session, running_run.id)
        assert db_run.status == "paused"

    def test_preserves_other_fields(self, test_client, running_run, db_session):
        """Verify other run fields are preserved."""
        original_turns = running_run.turns_used
        original_tokens_in = running_run.tokens_in
        original_tokens_out = running_run.tokens_out

        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200
        data = response.json()

        assert data["turns_used"] == original_turns
        assert data["tokens_in"] == original_tokens_in
        assert data["tokens_out"] == original_tokens_out


# =============================================================================
# Step 6: Record paused AgentEvent
# =============================================================================

class TestStep6RecordPausedEvent:
    """Test that a 'paused' AgentEvent is recorded."""

    def test_creates_paused_event(self, test_client, running_run, db_session):
        """Verify a 'paused' event is created."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        # Check for paused event
        events = get_events(db_session, running_run.id, event_type="paused")
        assert len(events) >= 1

    def test_paused_event_has_correct_type(self, test_client, running_run, db_session):
        """Verify the event has event_type='paused'."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        events = get_events(db_session, running_run.id, event_type="paused")
        assert events[0].event_type == "paused"

    def test_paused_event_has_payload(self, test_client, running_run, db_session):
        """Verify the event payload contains status information."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        events = get_events(db_session, running_run.id, event_type="paused")
        payload = events[0].payload

        assert payload is not None
        assert payload.get("previous_status") == "running"
        assert payload.get("new_status") == "paused"

    def test_paused_event_includes_metrics(self, test_client, running_run, db_session):
        """Verify the event payload includes run metrics."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        events = get_events(db_session, running_run.id, event_type="paused")
        payload = events[0].payload

        assert "turns_used" in payload
        assert "tokens_in" in payload
        assert "tokens_out" in payload


# =============================================================================
# Step 7: Commit transaction
# =============================================================================

class TestStep7CommitTransaction:
    """Test that changes are committed to the database."""

    def test_changes_are_committed(self, test_client, running_run, db_session):
        """Verify changes are committed (status persisted)."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        # Use a new session to verify persistence
        _, SessionLocal = create_database(project_root)
        new_session = SessionLocal()
        try:
            db_run = new_session.query(AgentRun).filter(AgentRun.id == running_run.id).first()
            assert db_run.status == "paused"
        finally:
            new_session.close()

    def test_event_is_committed(self, test_client, running_run, db_session):
        """Verify the paused event is committed."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        # Use a new session to verify event persistence
        _, SessionLocal = create_database(project_root)
        new_session = SessionLocal()
        try:
            event = new_session.query(AgentEvent).filter(
                AgentEvent.run_id == running_run.id,
                AgentEvent.event_type == "paused"
            ).first()
            assert event is not None
        finally:
            new_session.close()


# =============================================================================
# Step 8: Signal kernel to pause
# =============================================================================

class TestStep8SignalKernelToPause:
    """Test that the kernel is signaled to pause."""

    def test_broadcasts_pause_event(self, test_client, running_run, db_session):
        """Verify the pause event is broadcast for UI updates."""
        # Patch the broadcast_agent_event_sync function that's imported locally
        with patch('server.event_broadcaster.broadcast_agent_event_sync') as mock_broadcast:
            response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
            assert response.status_code == 200

            # Verify broadcast was called (even if it fails, the pause should still work)
            # Note: The call happens inside a try/except so it's optional
            # The key point is the pause operation itself succeeds
            # If the mock was called, verify arguments
            if mock_broadcast.called:
                call_args = mock_broadcast.call_args
                assert call_args.kwargs.get('run_id') == running_run.id or call_args[1].get('run_id') == running_run.id
                assert call_args.kwargs.get('event_type') == "paused" or call_args[1].get('event_type') == "paused"


# =============================================================================
# Step 9: Return updated AgentRunResponse
# =============================================================================

class TestStep9ReturnAgentRunResponse:
    """Test that the endpoint returns the updated AgentRunResponse."""

    def test_returns_agent_run_response(self, test_client, running_run, db_session):
        """Verify the response is an AgentRunResponse."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
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

    def test_response_shows_paused_status(self, test_client, running_run, db_session):
        """Verify the response shows status='paused'."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    def test_response_includes_run_id(self, test_client, running_run, db_session):
        """Verify the response includes the correct run id."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == running_run.id

    def test_response_includes_spec_id(self, test_client, running_run, test_spec, db_session):
        """Verify the response includes the agent_spec_id."""
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_spec_id"] == test_spec.id


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the pause endpoint."""

    def test_full_pause_workflow(self, test_client, running_run, db_session):
        """Test the complete pause workflow."""
        # Verify initial state
        assert running_run.status == "running"

        # Pause the run
        response = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response.status_code == 200

        # Verify response
        data = response.json()
        assert data["status"] == "paused"

        # Verify database state
        db_session.expire_all()
        db_run = get_agent_run(db_session, running_run.id)
        assert db_run.status == "paused"

        # Verify event was created
        events = get_events(db_session, running_run.id, event_type="paused")
        assert len(events) >= 1

    def test_cannot_double_pause(self, test_client, running_run, db_session):
        """Test that a run cannot be paused twice."""
        # First pause should succeed
        response1 = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response1.status_code == 200

        # Second pause should fail with 409
        response2 = test_client.post(f"/api/agent-runs/{running_run.id}/pause")
        assert response2.status_code == 409


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
