"""
Tests for Feature #24: POST /api/agent-runs/:id/cancel Cancel Agent
====================================================================

This test suite verifies the implementation of the cancel endpoint for agent runs.

Feature Requirements:
1. Define FastAPI route POST /api/agent-runs/{run_id}/cancel
2. Query AgentRun by id
3. Return 404 if not found
4. Return 409 if status is already completed, failed, or timeout
5. Update status to failed
6. Set error to user_cancelled
7. Set completed_at to current timestamp
8. Record failed event with cancellation reason
9. Signal kernel to abort
10. Return updated AgentRunResponse
"""

import os
import sys
from pathlib import Path

# Add project root to path and allow remote access for test client
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ["AUTOCODER_ALLOW_REMOTE"] = "1"

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Import the models and database
from api.agentspec_models import (
    AgentSpec,
    AcceptanceSpec,
    AgentRun,
    AgentEvent,
    Base,
    generate_uuid,
)
from api.agentspec_crud import (
    create_agent_spec,
    create_agent_run,
    get_agent_run,
    get_events,
)
from api.database import get_db, create_database, set_session_maker


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
def test_client():
    """Create a test client for the FastAPI app."""
    from server.main import app
    return TestClient(app)


@pytest.fixture
def sample_agent_spec(db_session):
    """Create a sample AgentSpec for testing."""
    spec = create_agent_spec(
        db_session,
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective for cancel testing",
        task_type="coding",
        allowed_tools=["feature_get_by_id"],
        max_turns=50,
        timeout_seconds=1800,
    )
    db_session.commit()
    return spec


@pytest.fixture
def sample_pending_run(db_session, sample_agent_spec):
    """Create a sample AgentRun in pending status."""
    run = create_agent_run(db_session, sample_agent_spec.id)
    # Default status is 'pending'
    db_session.commit()
    return run


@pytest.fixture
def sample_running_run(db_session, sample_agent_spec):
    """Create a sample AgentRun in running status."""
    run = create_agent_run(db_session, sample_agent_spec.id)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    run.turns_used = 5
    run.tokens_in = 1000
    run.tokens_out = 500
    db_session.commit()
    return run


@pytest.fixture
def sample_paused_run(db_session, sample_agent_spec):
    """Create a sample AgentRun in paused status."""
    run = create_agent_run(db_session, sample_agent_spec.id)
    run.status = "paused"
    run.started_at = datetime.now(timezone.utc)
    run.turns_used = 3
    run.tokens_in = 800
    run.tokens_out = 400
    db_session.commit()
    return run


@pytest.fixture
def sample_completed_run(db_session, sample_agent_spec):
    """Create a sample AgentRun in completed status."""
    run = create_agent_run(db_session, sample_agent_spec.id)
    run.status = "completed"
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.final_verdict = "passed"
    db_session.commit()
    return run


@pytest.fixture
def sample_failed_run(db_session, sample_agent_spec):
    """Create a sample AgentRun in failed status."""
    run = create_agent_run(db_session, sample_agent_spec.id)
    run.status = "failed"
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.final_verdict = "failed"
    run.error = "Some error"
    db_session.commit()
    return run


@pytest.fixture
def sample_timeout_run(db_session, sample_agent_spec):
    """Create a sample AgentRun in timeout status."""
    run = create_agent_run(db_session, sample_agent_spec.id)
    run.status = "timeout"
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = datetime.now(timezone.utc)
    run.final_verdict = "failed"
    run.error = "Execution timeout exceeded"
    db_session.commit()
    return run


# =============================================================================
# Step 1: FastAPI Route Definition Tests
# =============================================================================

class TestCancelRouteExists:
    """Tests that the cancel route is properly defined."""

    def test_cancel_route_exists(self, test_client, db_session):
        """Verify the cancel route is registered."""
        # Use a non-existent ID - should return 404, not 405 (method not allowed)
        response = test_client.post("/api/agent-runs/non-existent-id/cancel")
        assert response.status_code == 404  # Not 405 (method not allowed)

    def test_cancel_route_accepts_post(self, test_client, db_session):
        """Verify the cancel route only accepts POST method."""
        # Other methods should return 404 or 405
        # (404 means no route for that method at that path, 405 means route exists but wrong method)
        response = test_client.get("/api/agent-runs/some-id/cancel")
        assert response.status_code in [404, 405]  # No GET route defined for cancel

        response = test_client.put("/api/agent-runs/some-id/cancel")
        assert response.status_code in [404, 405]  # No PUT route defined for cancel

        response = test_client.delete("/api/agent-runs/some-id/cancel")
        assert response.status_code in [404, 405]  # No DELETE route defined for cancel


# =============================================================================
# Step 2 & 3: Query AgentRun and Return 404 Tests
# =============================================================================

class TestCancelNotFound:
    """Tests for 404 responses when AgentRun is not found."""

    def test_cancel_returns_404_for_nonexistent_run(self, test_client, db_session):
        """Verify 404 is returned when AgentRun doesn't exist."""
        fake_id = generate_uuid()
        response = test_client.post(f"/api/agent-runs/{fake_id}/cancel")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_cancel_404_includes_run_id_in_message(self, test_client, db_session):
        """Verify the 404 error message includes the requested run ID."""
        fake_id = generate_uuid()
        response = test_client.post(f"/api/agent-runs/{fake_id}/cancel")

        assert response.status_code == 404
        assert fake_id in response.json()["detail"]


# =============================================================================
# Step 4: Return 409 for Terminal Status Tests
# =============================================================================

class TestCancelConflict:
    """Tests for 409 responses when run is in terminal status."""

    def test_cancel_returns_409_for_completed_run(self, test_client, sample_completed_run):
        """Verify 409 is returned for completed runs."""
        response = test_client.post(f"/api/agent-runs/{sample_completed_run.id}/cancel")

        assert response.status_code == 409
        assert "completed" in response.json()["detail"].lower()
        assert "terminal" in response.json()["detail"].lower()

    def test_cancel_returns_409_for_failed_run(self, test_client, sample_failed_run):
        """Verify 409 is returned for already failed runs."""
        response = test_client.post(f"/api/agent-runs/{sample_failed_run.id}/cancel")

        assert response.status_code == 409
        assert "failed" in response.json()["detail"].lower()
        assert "terminal" in response.json()["detail"].lower()

    def test_cancel_returns_409_for_timeout_run(self, test_client, sample_timeout_run):
        """Verify 409 is returned for timed out runs."""
        response = test_client.post(f"/api/agent-runs/{sample_timeout_run.id}/cancel")

        assert response.status_code == 409
        assert "timeout" in response.json()["detail"].lower()
        assert "terminal" in response.json()["detail"].lower()


# =============================================================================
# Step 5, 6, 7: Status Update Tests
# =============================================================================

class TestCancelStatusUpdate:
    """Tests for status update to failed with user_cancelled error."""

    def test_cancel_running_updates_status_to_failed(self, test_client, sample_running_run, db_session):
        """Verify running run status is updated to failed."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

        # Verify in database
        db_session.refresh(sample_running_run)
        assert sample_running_run.status == "failed"

    def test_cancel_paused_updates_status_to_failed(self, test_client, sample_paused_run, db_session):
        """Verify paused run status is updated to failed."""
        response = test_client.post(f"/api/agent-runs/{sample_paused_run.id}/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

        # Verify in database
        db_session.refresh(sample_paused_run)
        assert sample_paused_run.status == "failed"

    def test_cancel_pending_updates_status_to_failed(self, test_client, sample_pending_run, db_session):
        """Verify pending run status is updated to failed."""
        response = test_client.post(f"/api/agent-runs/{sample_pending_run.id}/cancel")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"

        # Verify in database
        db_session.refresh(sample_pending_run)
        assert sample_pending_run.status == "failed"

    def test_cancel_sets_error_to_user_cancelled(self, test_client, sample_running_run, db_session):
        """Verify error is set to user_cancelled."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        assert response.json()["error"] == "user_cancelled"

        # Verify in database
        db_session.refresh(sample_running_run)
        assert sample_running_run.error == "user_cancelled"

    def test_cancel_sets_completed_at_timestamp(self, test_client, sample_running_run, db_session):
        """Verify completed_at is set to current timestamp."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        assert response.json()["completed_at"] is not None

        # Verify in database
        db_session.refresh(sample_running_run)
        assert sample_running_run.completed_at is not None


# =============================================================================
# Step 8: Record Failed Event Tests
# =============================================================================

class TestCancelEventRecording:
    """Tests for failed event recording with cancellation reason."""

    def test_cancel_records_failed_event(self, test_client, sample_running_run, db_session):
        """Verify a failed event is recorded."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200

        # Query events for this run
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_running_run.id
        ).all()

        assert len(events) >= 1
        failed_events = [e for e in events if e.event_type == "failed"]
        assert len(failed_events) == 1

    def test_cancel_event_includes_cancellation_reason(self, test_client, sample_running_run, db_session):
        """Verify the failed event includes the cancellation reason."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200

        # Query the failed event
        failed_event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_running_run.id,
            AgentEvent.event_type == "failed"
        ).first()

        assert failed_event is not None
        assert failed_event.payload is not None
        assert failed_event.payload.get("reason") == "user_cancelled"

    def test_cancel_event_includes_previous_status(self, test_client, sample_running_run, db_session):
        """Verify the failed event includes the previous status."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200

        # Query the failed event
        failed_event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_running_run.id,
            AgentEvent.event_type == "failed"
        ).first()

        assert failed_event is not None
        assert failed_event.payload is not None
        assert failed_event.payload.get("previous_status") == "running"

    def test_cancel_paused_event_shows_paused_as_previous(self, test_client, sample_paused_run, db_session):
        """Verify the failed event shows 'paused' as previous status when cancelling paused run."""
        response = test_client.post(f"/api/agent-runs/{sample_paused_run.id}/cancel")

        assert response.status_code == 200

        # Query the failed event
        failed_event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_paused_run.id,
            AgentEvent.event_type == "failed"
        ).first()

        assert failed_event is not None
        assert failed_event.payload.get("previous_status") == "paused"

    def test_cancel_event_includes_metrics(self, test_client, sample_running_run, db_session):
        """Verify the failed event includes current metrics."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200

        # Query the failed event
        failed_event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_running_run.id,
            AgentEvent.event_type == "failed"
        ).first()

        assert failed_event is not None
        payload = failed_event.payload
        assert "turns_used" in payload
        assert "tokens_in" in payload
        assert "tokens_out" in payload


# =============================================================================
# Step 9: Signal Kernel to Abort Tests
# =============================================================================

class TestCancelKernelSignal:
    """Tests for kernel abort signaling via event broadcaster."""

    def test_cancel_signals_kernel_via_broadcaster(self, test_client, sample_running_run, db_session):
        """Verify the cancel endpoint signals the kernel via event broadcaster."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

            assert response.status_code == 200

            # Verify broadcaster was called
            mock_broadcast.assert_called_once()
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs["run_id"] == sample_running_run.id
            assert call_kwargs["event_type"] == "failed"

    def test_cancel_works_without_broadcaster(self, test_client, sample_running_run, db_session):
        """Verify cancel works even when broadcaster raises an exception."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync", side_effect=Exception("Broadcast failed")):
            response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

            assert response.status_code == 200
            assert response.json()["status"] == "failed"

            # Verify database was still updated
            db_session.refresh(sample_running_run)
            assert sample_running_run.status == "failed"


# =============================================================================
# Step 10: Return AgentRunResponse Tests
# =============================================================================

class TestCancelResponse:
    """Tests for the returned AgentRunResponse."""

    def test_cancel_returns_agent_run_response(self, test_client, sample_running_run):
        """Verify the response is a valid AgentRunResponse."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        data = response.json()

        # Check all required fields are present
        required_fields = [
            "id", "agent_spec_id", "status", "started_at", "completed_at",
            "turns_used", "tokens_in", "tokens_out", "final_verdict",
            "acceptance_results", "error", "retry_count", "created_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_cancel_returns_updated_values(self, test_client, sample_running_run):
        """Verify the response contains the updated values."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == sample_running_run.id
        assert data["status"] == "failed"
        assert data["error"] == "user_cancelled"
        assert data["completed_at"] is not None

    def test_cancel_preserves_existing_metrics(self, test_client, sample_running_run):
        """Verify existing metrics are preserved in the response."""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        data = response.json()

        # Check that metrics from the running run are preserved
        assert data["turns_used"] == 5
        assert data["tokens_in"] == 1000
        assert data["tokens_out"] == 500


# =============================================================================
# Integration Tests
# =============================================================================

class TestCancelIntegration:
    """Integration tests for the cancel endpoint."""

    def test_cancel_is_idempotent_returns_409_on_second_call(self, test_client, sample_running_run):
        """Verify calling cancel twice returns 409 on the second call."""
        # First call should succeed
        response1 = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")
        assert response1.status_code == 200
        assert response1.json()["status"] == "failed"

        # Second call should return 409 (already in terminal state)
        response2 = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")
        assert response2.status_code == 409
        assert "terminal" in response2.json()["detail"].lower()

    def test_cancel_all_cancellable_statuses(self, test_client, db_session, sample_agent_spec):
        """Verify all cancellable statuses can be cancelled."""
        cancellable_statuses = ["pending", "running", "paused"]

        for status in cancellable_statuses:
            # Create a run with this status
            run = AgentRun(
                id=generate_uuid(),
                agent_spec_id=sample_agent_spec.id,
                status=status,
            )
            if status != "pending":
                run.started_at = datetime.now(timezone.utc)
            db_session.add(run)
            db_session.commit()

            # Cancel it
            response = test_client.post(f"/api/agent-runs/{run.id}/cancel")

            assert response.status_code == 200, f"Failed to cancel {status} run"
            assert response.json()["status"] == "failed"
            assert response.json()["error"] == "user_cancelled"

    def test_cancel_no_terminal_statuses_can_be_cancelled(self, test_client, db_session, sample_agent_spec):
        """Verify no terminal status can be cancelled."""
        terminal_statuses = ["completed", "failed", "timeout"]

        for status in terminal_statuses:
            # Create a run with this status
            run = AgentRun(
                id=generate_uuid(),
                agent_spec_id=sample_agent_spec.id,
                status=status,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db_session.add(run)
            db_session.commit()

            # Try to cancel it
            response = test_client.post(f"/api/agent-runs/{run.id}/cancel")

            assert response.status_code == 409, f"Should not be able to cancel {status} run"


# =============================================================================
# Feature Verification Steps Tests
# =============================================================================

class TestFeature24VerificationSteps:
    """Tests aligned directly with Feature #24 verification steps."""

    def test_step_1_fastapi_route_defined(self):
        """Step 1: Define FastAPI route POST /api/agent-runs/{run_id}/cancel"""
        from server.routers.agent_runs import router

        # Check that the route exists (routes have the prefix included in their full path)
        routes = [route.path for route in router.routes]
        # The cancel route path should be /{run_id}/cancel (without prefix) or /api/agent-runs/{run_id}/cancel (with prefix)
        assert any("cancel" in route for route in routes), f"Cancel route not found in routes: {routes}"

        # Check it's a POST method
        found_cancel_route = False
        for route in router.routes:
            if "cancel" in route.path:
                assert "POST" in route.methods, f"Cancel route should be POST, got {route.methods}"
                found_cancel_route = True
                break
        assert found_cancel_route, "Cancel route not found"

    def test_step_2_query_agent_run_by_id(self, test_client, sample_running_run):
        """Step 2: Query AgentRun by id"""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")
        # If we get a 200 or specific error, the query worked
        assert response.status_code in [200, 409, 404]

    def test_step_3_return_404_if_not_found(self, test_client, db_session):
        """Step 3: Return 404 if not found"""
        fake_id = generate_uuid()
        response = test_client.post(f"/api/agent-runs/{fake_id}/cancel")
        assert response.status_code == 404

    def test_step_4_return_409_if_terminal_status(self, test_client, sample_completed_run):
        """Step 4: Return 409 if status is already completed, failed, or timeout"""
        response = test_client.post(f"/api/agent-runs/{sample_completed_run.id}/cancel")
        assert response.status_code == 409

    def test_step_5_update_status_to_failed(self, test_client, sample_running_run, db_session):
        """Step 5: Update status to failed"""
        test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")
        db_session.refresh(sample_running_run)
        assert sample_running_run.status == "failed"

    def test_step_6_set_error_to_user_cancelled(self, test_client, sample_running_run, db_session):
        """Step 6: Set error to user_cancelled"""
        test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")
        db_session.refresh(sample_running_run)
        assert sample_running_run.error == "user_cancelled"

    def test_step_7_set_completed_at_timestamp(self, test_client, sample_running_run, db_session):
        """Step 7: Set completed_at to current timestamp"""
        test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")
        db_session.refresh(sample_running_run)
        assert sample_running_run.completed_at is not None

    def test_step_8_record_failed_event(self, test_client, sample_running_run, db_session):
        """Step 8: Record failed event with cancellation reason"""
        test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        failed_event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_running_run.id,
            AgentEvent.event_type == "failed"
        ).first()

        assert failed_event is not None
        assert failed_event.payload.get("reason") == "user_cancelled"

    def test_step_9_signal_kernel_to_abort(self, test_client, sample_running_run, db_session):
        """Step 9: Signal kernel to abort"""
        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

            # Verify broadcaster was used to signal abort
            mock_broadcast.assert_called_once()

    def test_step_10_return_updated_agent_run_response(self, test_client, sample_running_run):
        """Step 10: Return updated AgentRunResponse"""
        response = test_client.post(f"/api/agent-runs/{sample_running_run.id}/cancel")

        assert response.status_code == 200
        data = response.json()

        # Verify it's a proper AgentRunResponse with updated values
        assert data["id"] == sample_running_run.id
        assert data["status"] == "failed"
        assert data["error"] == "user_cancelled"
        assert data["completed_at"] is not None
