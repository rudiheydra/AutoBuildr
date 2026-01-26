"""
Test AgentRun State Machine
===========================

Verifies the state machine for AgentRun status transitions:
- Valid transitions (adjacency map)
- Invalid transitions raise InvalidStateTransition
- Terminal states block all transitions
- Timestamps updated correctly
- Error messages set on failure/timeout
- Logging occurs on transitions

Feature #26: AgentRun Status Transition State Machine
"""

import logging
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from api.agentspec_models import (
    AgentRun,
    InvalidStateTransition,
    VALID_STATE_TRANSITIONS,
    TERMINAL_STATUSES,
    RUN_STATUS,
    generate_uuid,
)


class TestValidStateTransitions:
    """Test the VALID_STATE_TRANSITIONS adjacency map."""

    def test_adjacency_map_covers_all_statuses(self):
        """All statuses should be keys in the adjacency map."""
        for status in RUN_STATUS:
            assert status in VALID_STATE_TRANSITIONS, f"Missing status: {status}"

    def test_pending_can_only_go_to_running(self):
        """pending state can only transition to running."""
        assert VALID_STATE_TRANSITIONS["pending"] == frozenset({"running"})

    def test_running_transitions(self):
        """running state can go to paused, completed, failed, or timeout."""
        expected = frozenset({"paused", "completed", "failed", "timeout"})
        assert VALID_STATE_TRANSITIONS["running"] == expected

    def test_paused_transitions(self):
        """paused state can resume (running) or be cancelled (failed)."""
        expected = frozenset({"running", "failed"})
        assert VALID_STATE_TRANSITIONS["paused"] == expected

    def test_completed_is_terminal(self):
        """completed state has no valid transitions (terminal)."""
        assert VALID_STATE_TRANSITIONS["completed"] == frozenset()

    def test_failed_is_terminal(self):
        """failed state has no valid transitions (terminal)."""
        assert VALID_STATE_TRANSITIONS["failed"] == frozenset()

    def test_timeout_is_terminal(self):
        """timeout state has no valid transitions (terminal)."""
        assert VALID_STATE_TRANSITIONS["timeout"] == frozenset()

    def test_terminal_statuses_constant(self):
        """TERMINAL_STATUSES should contain completed, failed, timeout."""
        assert TERMINAL_STATUSES == frozenset({"completed", "failed", "timeout"})


class TestInvalidStateTransitionException:
    """Test the InvalidStateTransition exception."""

    def test_exception_stores_details(self):
        """Exception should store run_id, current_state, target_state."""
        exc = InvalidStateTransition(
            run_id="test-123",
            current_state="pending",
            target_state="completed"
        )
        assert exc.run_id == "test-123"
        assert exc.current_state == "pending"
        assert exc.target_state == "completed"

    def test_exception_message_shows_valid_transitions(self):
        """Exception message should list valid transitions."""
        exc = InvalidStateTransition(
            run_id="test-123",
            current_state="pending",
            target_state="completed"
        )
        message = str(exc)
        assert "pending" in message
        assert "completed" in message
        assert "running" in message  # The valid transition from pending

    def test_exception_message_for_terminal_state(self):
        """Exception message should indicate terminal state."""
        exc = InvalidStateTransition(
            run_id="test-123",
            current_state="completed",
            target_state="running"
        )
        message = str(exc)
        assert "terminal state" in message.lower()

    def test_custom_message_overrides_default(self):
        """Custom message should override auto-generated message."""
        exc = InvalidStateTransition(
            run_id="test-123",
            current_state="pending",
            target_state="completed",
            message="Custom error message"
        )
        assert str(exc) == "Custom error message"


class TestAgentRunStateMachine:
    """Test AgentRun state machine methods."""

    def _create_run(self, status: str = "pending") -> AgentRun:
        """Create an AgentRun for testing."""
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status=status,
        )
        return run

    # --- is_terminal property ---

    def test_is_terminal_pending(self):
        """pending is not terminal."""
        run = self._create_run("pending")
        assert run.is_terminal is False

    def test_is_terminal_running(self):
        """running is not terminal."""
        run = self._create_run("running")
        assert run.is_terminal is False

    def test_is_terminal_paused(self):
        """paused is not terminal."""
        run = self._create_run("paused")
        assert run.is_terminal is False

    def test_is_terminal_completed(self):
        """completed is terminal."""
        run = self._create_run("completed")
        assert run.is_terminal is True

    def test_is_terminal_failed(self):
        """failed is terminal."""
        run = self._create_run("failed")
        assert run.is_terminal is True

    def test_is_terminal_timeout(self):
        """timeout is terminal."""
        run = self._create_run("timeout")
        assert run.is_terminal is True

    # --- can_transition_to method ---

    def test_can_transition_pending_to_running(self):
        """pending can transition to running."""
        run = self._create_run("pending")
        assert run.can_transition_to("running") is True

    def test_cannot_transition_pending_to_completed(self):
        """pending cannot transition directly to completed."""
        run = self._create_run("pending")
        assert run.can_transition_to("completed") is False

    def test_cannot_transition_pending_to_failed(self):
        """pending cannot transition directly to failed."""
        run = self._create_run("pending")
        assert run.can_transition_to("failed") is False

    def test_can_transition_running_to_paused(self):
        """running can transition to paused."""
        run = self._create_run("running")
        assert run.can_transition_to("paused") is True

    def test_can_transition_running_to_completed(self):
        """running can transition to completed."""
        run = self._create_run("running")
        assert run.can_transition_to("completed") is True

    def test_can_transition_running_to_failed(self):
        """running can transition to failed."""
        run = self._create_run("running")
        assert run.can_transition_to("failed") is True

    def test_can_transition_running_to_timeout(self):
        """running can transition to timeout."""
        run = self._create_run("running")
        assert run.can_transition_to("timeout") is True

    def test_cannot_transition_running_to_pending(self):
        """running cannot transition back to pending."""
        run = self._create_run("running")
        assert run.can_transition_to("pending") is False

    def test_can_transition_paused_to_running(self):
        """paused can transition back to running (resume)."""
        run = self._create_run("paused")
        assert run.can_transition_to("running") is True

    def test_can_transition_paused_to_failed(self):
        """paused can transition to failed (cancel)."""
        run = self._create_run("paused")
        assert run.can_transition_to("failed") is True

    def test_cannot_transition_paused_to_completed(self):
        """paused cannot transition to completed (must resume first)."""
        run = self._create_run("paused")
        assert run.can_transition_to("completed") is False

    def test_cannot_transition_from_terminal_completed(self):
        """completed is terminal - no transitions allowed."""
        run = self._create_run("completed")
        for target in RUN_STATUS:
            if target != "completed":
                assert run.can_transition_to(target) is False

    def test_cannot_transition_from_terminal_failed(self):
        """failed is terminal - no transitions allowed."""
        run = self._create_run("failed")
        for target in RUN_STATUS:
            if target != "failed":
                assert run.can_transition_to(target) is False

    def test_cannot_transition_from_terminal_timeout(self):
        """timeout is terminal - no transitions allowed."""
        run = self._create_run("timeout")
        for target in RUN_STATUS:
            if target != "timeout":
                assert run.can_transition_to(target) is False

    # --- get_valid_transitions method ---

    def test_get_valid_transitions_pending(self):
        """get_valid_transitions returns correct set for pending."""
        run = self._create_run("pending")
        assert run.get_valid_transitions() == frozenset({"running"})

    def test_get_valid_transitions_running(self):
        """get_valid_transitions returns correct set for running."""
        run = self._create_run("running")
        expected = frozenset({"paused", "completed", "failed", "timeout"})
        assert run.get_valid_transitions() == expected

    def test_get_valid_transitions_terminal(self):
        """get_valid_transitions returns empty set for terminal states."""
        for status in TERMINAL_STATUSES:
            run = self._create_run(status)
            assert run.get_valid_transitions() == frozenset()

    # --- transition_to method ---

    def test_transition_to_valid(self):
        """Valid transition should update status."""
        run = self._create_run("pending")
        run.transition_to("running")
        assert run.status == "running"

    def test_transition_to_returns_timestamp(self):
        """transition_to should return the transition timestamp."""
        run = self._create_run("pending")
        ts = run.transition_to("running")
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None  # Should be timezone-aware

    def test_transition_to_invalid_raises_exception(self):
        """Invalid transition should raise InvalidStateTransition."""
        run = self._create_run("pending")
        with pytest.raises(InvalidStateTransition) as exc_info:
            run.transition_to("completed")

        assert exc_info.value.run_id == run.id
        assert exc_info.value.current_state == "pending"
        assert exc_info.value.target_state == "completed"

    def test_transition_to_unknown_status_raises_value_error(self):
        """Unknown target status should raise ValueError."""
        run = self._create_run("pending")
        with pytest.raises(ValueError) as exc_info:
            run.transition_to("unknown_status")

        assert "Unknown status" in str(exc_info.value)
        assert "unknown_status" in str(exc_info.value)

    def test_transition_pending_to_running_sets_started_at(self):
        """Transitioning pending -> running should set started_at."""
        run = self._create_run("pending")
        assert run.started_at is None

        ts = run.transition_to("running")
        assert run.started_at == ts
        assert run.started_at is not None

    def test_transition_to_terminal_sets_completed_at(self):
        """Transitioning to terminal state should set completed_at."""
        for terminal in TERMINAL_STATUSES:
            run = self._create_run("running")
            run.started_at = datetime.now(timezone.utc)
            assert run.completed_at is None

            ts = run.transition_to(terminal)
            assert run.completed_at == ts
            assert run.completed_at is not None

    def test_transition_to_failed_with_error_message(self):
        """Transitioning to failed should set error message."""
        run = self._create_run("running")
        run.transition_to("failed", error_message="Test error")
        assert run.error == "Test error"

    def test_transition_to_timeout_with_error_message(self):
        """Transitioning to timeout should set error message."""
        run = self._create_run("running")
        run.transition_to("timeout", error_message="Exceeded 30 minutes")
        assert run.error == "Exceeded 30 minutes"

    def test_transition_to_completed_ignores_error_message(self):
        """completed transition should not set error (it's a success state)."""
        run = self._create_run("running")
        run.transition_to("completed", error_message="This should be ignored")
        assert run.error is None

    # --- Logging tests ---

    def test_transition_logs_info(self, caplog):
        """State transition should log at INFO level."""
        with caplog.at_level(logging.INFO):
            run = self._create_run("pending")
            run.transition_to("running")

        assert "status transition" in caplog.text.lower()
        assert "pending" in caplog.text
        assert "running" in caplog.text

    # --- Convenience methods ---

    def test_start_method(self):
        """start() should transition from pending to running."""
        run = self._create_run("pending")
        ts = run.start()
        assert run.status == "running"
        assert run.started_at == ts

    def test_start_method_invalid_raises_exception(self):
        """start() from non-pending state should raise exception."""
        run = self._create_run("running")
        with pytest.raises(InvalidStateTransition):
            run.start()

    def test_pause_method(self):
        """pause() should transition from running to paused."""
        run = self._create_run("running")
        run.pause()
        assert run.status == "paused"

    def test_pause_method_invalid_raises_exception(self):
        """pause() from non-running state should raise exception."""
        run = self._create_run("pending")
        with pytest.raises(InvalidStateTransition):
            run.pause()

    def test_resume_method(self):
        """resume() should transition from paused to running."""
        run = self._create_run("paused")
        run.resume()
        assert run.status == "running"

    def test_resume_method_invalid_raises_exception(self):
        """resume() from non-paused state should raise exception."""
        run = self._create_run("running")
        with pytest.raises(InvalidStateTransition):
            run.resume()

    def test_complete_method(self):
        """complete() should transition from running to completed."""
        run = self._create_run("running")
        ts = run.complete()
        assert run.status == "completed"
        assert run.completed_at == ts

    def test_complete_method_invalid_raises_exception(self):
        """complete() from non-running state should raise exception."""
        run = self._create_run("paused")
        with pytest.raises(InvalidStateTransition):
            run.complete()

    def test_fail_method(self):
        """fail() should transition to failed."""
        run = self._create_run("running")
        ts = run.fail("Error occurred")
        assert run.status == "failed"
        assert run.error == "Error occurred"
        assert run.completed_at == ts

    def test_fail_method_from_paused(self):
        """fail() can be called from paused state (cancel)."""
        run = self._create_run("paused")
        run.fail("Cancelled by user")
        assert run.status == "failed"
        assert run.error == "Cancelled by user"

    def test_timeout_method(self):
        """timeout() should transition from running to timeout."""
        run = self._create_run("running")
        ts = run.timeout()
        assert run.status == "timeout"
        assert run.completed_at == ts
        assert run.error == "Execution exceeded time or turn budget"

    def test_timeout_method_with_custom_message(self):
        """timeout() should accept custom error message."""
        run = self._create_run("running")
        run.timeout("Max turns (50) exceeded")
        assert run.error == "Max turns (50) exceeded"

    def test_timeout_method_invalid_raises_exception(self):
        """timeout() from non-running state should raise exception."""
        run = self._create_run("paused")
        with pytest.raises(InvalidStateTransition):
            run.timeout()


class TestAgentRunStateTransitionAtomic:
    """Test that state transitions work correctly in database transactions."""

    def test_transition_within_transaction(self):
        """State transitions should be safe within a transaction.

        Note: This test validates the transition method itself. Database
        transaction atomicity is ensured by the caller using the session.
        The method is designed to be called within an existing transaction.
        """
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status="pending",
        )

        # Simulate transaction flow
        run.start()
        assert run.status == "running"
        assert run.started_at is not None

        run.complete()
        assert run.status == "completed"
        assert run.completed_at is not None

        # Terminal state - should not allow further transitions
        with pytest.raises(InvalidStateTransition):
            run.start()


class TestAgentRunFullLifecycle:
    """Test full lifecycle scenarios."""

    def test_success_lifecycle(self):
        """Test a successful run lifecycle: pending -> running -> completed."""
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status="pending",
        )

        # Start
        run.start()
        assert run.status == "running"
        assert run.started_at is not None
        assert run.completed_at is None

        # Complete
        run.complete()
        assert run.status == "completed"
        assert run.completed_at is not None
        assert run.is_terminal is True

    def test_failure_lifecycle(self):
        """Test a failed run lifecycle: pending -> running -> failed."""
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status="pending",
        )

        run.start()
        run.fail("Test error")

        assert run.status == "failed"
        assert run.error == "Test error"
        assert run.completed_at is not None
        assert run.is_terminal is True

    def test_timeout_lifecycle(self):
        """Test a timeout run lifecycle: pending -> running -> timeout."""
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status="pending",
        )

        run.start()
        run.timeout("Budget exhausted")

        assert run.status == "timeout"
        assert run.error == "Budget exhausted"
        assert run.completed_at is not None
        assert run.is_terminal is True

    def test_pause_resume_lifecycle(self):
        """Test pause/resume lifecycle: pending -> running -> paused -> running -> completed."""
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status="pending",
        )

        run.start()
        assert run.status == "running"

        run.pause()
        assert run.status == "paused"
        assert run.is_terminal is False

        run.resume()
        assert run.status == "running"

        run.complete()
        assert run.status == "completed"
        assert run.is_terminal is True

    def test_pause_cancel_lifecycle(self):
        """Test cancel from paused state: pending -> running -> paused -> failed."""
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=generate_uuid(),
            status="pending",
        )

        run.start()
        run.pause()
        run.fail("Cancelled by user")

        assert run.status == "failed"
        assert run.error == "Cancelled by user"
        assert run.is_terminal is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
