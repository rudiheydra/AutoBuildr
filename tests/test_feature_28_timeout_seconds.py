"""
Tests for Feature #28: Timeout Seconds Wall-Clock Enforcement
==============================================================

Comprehensive tests for timeout_seconds wall-clock limit enforcement
during kernel execution using started_at timestamp comparison.

Feature Verification Steps:
1. Record started_at timestamp at run begin
2. Compute elapsed_seconds = now - started_at before each turn
3. Check elapsed_seconds < spec.timeout_seconds
4. When timeout reached, set status to timeout
5. Set error message to timeout_exceeded
6. Record timeout event with elapsed_seconds in payload
7. Ensure partial work is committed before termination
8. Handle long-running tool calls that exceed timeout
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
)
from api.harness_kernel import (
    BudgetTracker,
    TimeoutSecondsExceeded,
    MaxTurnsExceeded,
    HarnessKernel,
    ExecutionResult,
    create_timeout_event,
    record_timeout_event,
    _utc_now,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_spec(db_session):
    """Create a sample AgentSpec with timeout_seconds set."""
    spec = AgentSpec(
        id="test-spec-timeout",
        name="test-spec-timeout",
        display_name="Test Spec with Timeout",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=100,  # High max_turns so timeout is the limiting factor
        timeout_seconds=60,  # 60 seconds timeout (minimum allowed by constraint)
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id="test-run-timeout",
        agent_spec_id=sample_spec.id,
        status="pending",
        turns_used=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


# =============================================================================
# TimeoutSecondsExceeded Exception Tests
# =============================================================================

class TestTimeoutSecondsExceeded:
    """Tests for TimeoutSecondsExceeded exception class."""

    def test_exception_attributes(self):
        """Test exception has correct attributes."""
        exc = TimeoutSecondsExceeded(
            elapsed_seconds=65.5,
            timeout_seconds=60,
            run_id="test-run-001",
        )
        assert exc.elapsed_seconds == 65.5
        assert exc.timeout_seconds == 60
        assert exc.run_id == "test-run-001"
        assert exc.budget_type == "timeout_seconds"

    def test_exception_message(self):
        """Test exception message format."""
        exc = TimeoutSecondsExceeded(
            elapsed_seconds=125.7,
            timeout_seconds=120,
            run_id="test-run",
        )
        assert "timeout_exceeded" in str(exc)
        assert "125.7" in str(exc)
        assert "120" in str(exc)

    def test_inherits_from_budget_exceeded(self):
        """Test TimeoutSecondsExceeded inherits from BudgetExceeded."""
        from api.harness_kernel import BudgetExceeded
        exc = TimeoutSecondsExceeded(
            elapsed_seconds=10,
            timeout_seconds=5,
            run_id="test",
        )
        assert isinstance(exc, BudgetExceeded)


# =============================================================================
# BudgetTracker Timeout Tests
# =============================================================================

class TestBudgetTrackerTimeout:
    """Tests for BudgetTracker timeout tracking (Feature #28, Steps 2-3)."""

    def test_init_with_timeout_seconds(self):
        """Step 1: Test BudgetTracker initializes with timeout_seconds."""
        tracker = BudgetTracker(
            max_turns=50,
            timeout_seconds=300,
            turns_used=0,
            run_id="test-run",
        )
        assert tracker.timeout_seconds == 300

    def test_init_invalid_timeout_seconds(self):
        """Test initialization fails with timeout_seconds < 1."""
        with pytest.raises(ValueError, match="timeout_seconds must be >= 1"):
            BudgetTracker(max_turns=10, timeout_seconds=0)

    def test_elapsed_seconds_without_started_at(self):
        """Step 2: Test elapsed_seconds returns 0 when not started."""
        tracker = BudgetTracker(max_turns=10, timeout_seconds=60)
        assert tracker.elapsed_seconds == 0.0

    def test_elapsed_seconds_with_started_at(self):
        """Step 2: Test elapsed_seconds computes correctly from started_at."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        # Should be approximately 30 seconds (allow some tolerance)
        assert 29.5 < tracker.elapsed_seconds < 31.5

    def test_remaining_seconds(self):
        """Test remaining_seconds property."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        # Should be approximately 50 seconds remaining
        assert 48.5 < tracker.remaining_seconds < 51.5

    def test_remaining_seconds_at_timeout(self):
        """Test remaining_seconds doesn't go negative."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        assert tracker.remaining_seconds == 0.0

    def test_is_timed_out_false(self):
        """Step 3: Test is_timed_out returns False when within timeout."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        assert tracker.is_timed_out is False

    def test_is_timed_out_true(self):
        """Step 3: Test is_timed_out returns True when timeout exceeded."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        assert tracker.is_timed_out is True

    def test_can_continue_within_timeout_true(self):
        """Test can_continue_within_timeout returns True when time available."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        assert tracker.can_continue_within_timeout() is True

    def test_can_continue_within_timeout_false(self):
        """Test can_continue_within_timeout returns False when timed out."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
        )
        assert tracker.can_continue_within_timeout() is False

    def test_check_timeout_or_raise_success(self):
        """Test check_timeout_or_raise succeeds when within timeout."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
            run_id="test-run",
        )
        tracker.check_timeout_or_raise()  # Should not raise

    def test_check_timeout_or_raise_failure(self):
        """Test check_timeout_or_raise raises when timeout exceeded."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            started_at=past_time,
            run_id="test-run",
        )
        with pytest.raises(TimeoutSecondsExceeded) as exc_info:
            tracker.check_timeout_or_raise()

        assert exc_info.value.timeout_seconds == 60
        assert exc_info.value.elapsed_seconds >= 100
        assert exc_info.value.run_id == "test-run"

    def test_check_all_budgets_or_raise_timeout_first(self):
        """Test check_all_budgets_or_raise checks timeout before turns."""
        # Both limits exceeded, but timeout should be raised first
        past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            turns_used=15,  # Also exceeds max_turns
            started_at=past_time,
            run_id="test-run",
        )
        # Should raise TimeoutSecondsExceeded, not MaxTurnsExceeded
        with pytest.raises(TimeoutSecondsExceeded):
            tracker.check_all_budgets_or_raise()

    def test_to_payload_includes_timeout_fields(self):
        """Test to_payload includes elapsed_seconds and timeout fields."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            turns_used=5,
            started_at=past_time,
        )
        payload = tracker.to_payload()

        assert "elapsed_seconds" in payload
        assert "timeout_seconds" in payload
        assert "remaining_seconds" in payload
        assert "is_timed_out" in payload
        assert payload["timeout_seconds"] == 60
        assert payload["is_timed_out"] is False
        assert 29 < payload["elapsed_seconds"] < 32


# =============================================================================
# HarnessKernel Timeout Tests
# =============================================================================

class TestHarnessKernelTimeout:
    """Tests for HarnessKernel timeout enforcement (Feature #28, Steps 1-7)."""

    def test_initialize_run_records_started_at(self, db_session, sample_spec, sample_run):
        """Step 1: Test initialize_run records started_at timestamp."""
        kernel = HarnessKernel(db_session)

        tracker = kernel.initialize_run(sample_run, sample_spec)

        # Check run has started_at
        assert sample_run.started_at is not None
        assert isinstance(sample_run.started_at, datetime)

        # Check tracker has started_at
        assert tracker.started_at is not None
        # Compare timestamps allowing for timezone differences
        # Both should represent the same moment in time
        run_ts = sample_run.started_at.replace(tzinfo=timezone.utc) if sample_run.started_at.tzinfo is None else sample_run.started_at
        tracker_ts = tracker.started_at.replace(tzinfo=timezone.utc) if tracker.started_at.tzinfo is None else tracker.started_at
        assert abs((run_ts - tracker_ts).total_seconds()) < 1  # Within 1 second

    def test_initialize_run_includes_timeout_seconds(self, db_session, sample_spec, sample_run):
        """Test initialize_run creates tracker with correct timeout_seconds."""
        kernel = HarnessKernel(db_session)

        tracker = kernel.initialize_run(sample_run, sample_spec)

        assert tracker.timeout_seconds == sample_spec.timeout_seconds

    def test_check_budget_before_turn_raises_timeout(self, db_session, sample_spec, sample_run):
        """Step 3: Test check_budget_before_turn raises TimeoutSecondsExceeded."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Simulate time passing by modifying started_at
        past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
        kernel._budget_tracker.started_at = past_time

        with pytest.raises(TimeoutSecondsExceeded):
            kernel.check_budget_before_turn(sample_run)

    def test_handle_timeout_exceeded_sets_status(self, db_session, sample_spec, sample_run):
        """Step 4: Test handle_timeout_exceeded sets status to timeout."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        result = kernel.handle_timeout_exceeded(sample_run, error)

        assert result.status == "timeout"
        assert sample_run.status == "timeout"

    def test_handle_timeout_exceeded_sets_error_message(self, db_session, sample_spec, sample_run):
        """Step 5: Test handle_timeout_exceeded sets error to timeout_exceeded."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        result = kernel.handle_timeout_exceeded(sample_run, error)

        assert result.error == "timeout_exceeded"
        assert sample_run.error == "timeout_exceeded"

    def test_handle_timeout_exceeded_records_event(self, db_session, sample_spec, sample_run):
        """Step 6: Test handle_timeout_exceeded records timeout event with elapsed_seconds."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Simulate some elapsed time
        past_time = datetime.now(timezone.utc) - timedelta(seconds=65)
        kernel._budget_tracker.started_at = past_time

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        kernel.handle_timeout_exceeded(sample_run, error)

        # Check timeout event was recorded
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id,
            AgentEvent.event_type == "timeout"
        ).all()

        assert len(events) == 1
        assert events[0].payload["reason"] == "timeout_exceeded"
        assert "elapsed_seconds" in events[0].payload
        assert events[0].payload["elapsed_seconds"] >= 60

    def test_handle_timeout_exceeded_commits_partial_work(self, db_session, sample_spec, sample_run):
        """Step 7: Test handle_timeout_exceeded commits partial work."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Record some turns first
        kernel.record_turn_complete(sample_run, {"tool": "Read"})
        kernel.record_turn_complete(sample_run, {"tool": "Write"})

        assert sample_run.turns_used == 2

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        kernel.handle_timeout_exceeded(sample_run, error)

        # Verify by querying fresh
        db_session.expire(sample_run)
        fresh_run = db_session.query(AgentRun).filter(
            AgentRun.id == sample_run.id
        ).first()

        # Partial work should be committed
        assert fresh_run.turns_used == 2
        assert fresh_run.status == "timeout"
        assert fresh_run.completed_at is not None


# =============================================================================
# Integration Tests - execute_with_budget Timeout
# =============================================================================

class TestExecuteWithBudgetTimeout:
    """Integration tests for execute_with_budget timeout handling."""

    def test_timeout_before_turn(self, db_session, sample_spec, sample_run):
        """Test timeout is caught before turn execution."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            # Simulate time passing during first turn
            if turn_count[0] == 1:
                # After first turn, simulate timeout
                kernel._budget_tracker.started_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=100)
                )
            return turn_count[0] >= 10, {"turn": turn_count[0]}

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        assert result.status == "timeout"
        assert result.error == "timeout_exceeded"
        # Should have executed some turns before timeout
        assert result.turns_used >= 1

    def test_timeout_after_long_running_tool_call(self, db_session, sample_spec, sample_run):
        """Step 8: Test handling long-running tool calls that exceed timeout."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            # Simulate a long-running tool call that exceeds timeout
            if turn_count[0] == 2:
                # After tool call completes, we've exceeded timeout
                kernel._budget_tracker.started_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=100)
                )
            return False, {"tool_call": f"tool_{turn_count[0]}"}

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        assert result.status == "timeout"
        assert result.error == "timeout_exceeded"

    def test_timeout_records_all_events(self, db_session, sample_spec, sample_run):
        """Test all events are recorded before timeout."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            if turn_count[0] == 3:
                # Timeout after 3 turns
                kernel._budget_tracker.started_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=100)
                )
            return False, {"turn": turn_count[0]}

        kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id
        ).order_by(AgentEvent.sequence).all()

        # Should have: started, turn_complete x3, timeout
        event_types = [e.event_type for e in events]
        assert "started" in event_types
        assert event_types.count("turn_complete") == 3
        assert "timeout" in event_types

    def test_completes_normally_within_timeout(self, db_session, sample_spec, sample_run):
        """Test execution completes normally when within timeout."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            # Complete after 3 turns, well within timeout
            return turn_count[0] >= 3, {"turn": turn_count[0]}

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        assert result.status == "completed"
        assert result.error is None
        assert result.turns_used == 3


# =============================================================================
# Event Recording Tests
# =============================================================================

class TestTimeoutEventRecording:
    """Tests for timeout event recording."""

    def test_create_timeout_event_with_elapsed_seconds(self):
        """Test create_timeout_event includes elapsed_seconds."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=65)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            turns_used=5,
            run_id="test-run",
            started_at=past_time,
        )

        event = create_timeout_event(
            run_id="test-run",
            sequence=10,
            budget_tracker=tracker,
            reason="timeout_exceeded",
        )

        assert event["event_type"] == "timeout"
        assert event["payload"]["reason"] == "timeout_exceeded"
        assert "elapsed_seconds" in event["payload"]
        assert event["payload"]["elapsed_seconds"] >= 60
        assert event["payload"]["timeout_seconds"] == 60
        assert event["payload"]["is_timed_out"] is True

    def test_record_timeout_event_persists(self, db_session, sample_run):
        """Test record_timeout_event persists event to database."""
        past_time = datetime.now(timezone.utc) - timedelta(seconds=65)
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=60,
            turns_used=5,
            run_id=sample_run.id,
            started_at=past_time,
        )

        event = record_timeout_event(
            db=db_session,
            run_id=sample_run.id,
            sequence=10,
            budget_tracker=tracker,
            reason="timeout_exceeded",
        )
        db_session.commit()

        # Verify event was persisted
        saved_event = db_session.query(AgentEvent).filter(
            AgentEvent.id == event.id
        ).first()

        assert saved_event is not None
        assert saved_event.event_type == "timeout"
        assert saved_event.payload["reason"] == "timeout_exceeded"


# =============================================================================
# Feature Verification Steps (Comprehensive)
# =============================================================================

class TestFeature28VerificationSteps:
    """
    Comprehensive verification of all Feature #28 steps.

    These tests directly verify each requirement from the feature specification.
    """

    def test_step_1_record_started_at_timestamp(self, db_session, sample_spec, sample_run):
        """
        Step 1: Record started_at timestamp at run begin.

        Verifies that when a run is initialized:
        - run.started_at is set
        - budget_tracker.started_at is set
        - Both timestamps match
        """
        kernel = HarnessKernel(db_session)

        assert sample_run.started_at is None  # Before initialization

        tracker = kernel.initialize_run(sample_run, sample_spec)

        # Verify started_at is recorded
        assert sample_run.started_at is not None
        assert tracker.started_at is not None
        # Compare timestamps allowing for timezone differences
        run_ts = sample_run.started_at.replace(tzinfo=timezone.utc) if sample_run.started_at.tzinfo is None else sample_run.started_at
        tracker_ts = tracker.started_at.replace(tzinfo=timezone.utc) if tracker.started_at.tzinfo is None else tracker.started_at
        assert abs((run_ts - tracker_ts).total_seconds()) < 1  # Within 1 second

    def test_step_2_compute_elapsed_seconds(self, db_session, sample_spec, sample_run):
        """
        Step 2: Compute elapsed_seconds = now - started_at before each turn.

        Verifies that elapsed_seconds is computed correctly from started_at.
        """
        kernel = HarnessKernel(db_session)
        tracker = kernel.initialize_run(sample_run, sample_spec)

        # Immediately after init, elapsed should be very small
        assert tracker.elapsed_seconds < 1.0

        # Simulate time passing
        past_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        tracker.started_at = past_time

        # Now elapsed should be approximately 30 seconds
        assert 29 < tracker.elapsed_seconds < 32

    def test_step_3_check_elapsed_less_than_timeout(self, db_session, sample_spec, sample_run):
        """
        Step 3: Check elapsed_seconds < spec.timeout_seconds.

        Verifies that the timeout check correctly compares elapsed vs timeout.
        """
        kernel = HarnessKernel(db_session)
        tracker = kernel.initialize_run(sample_run, sample_spec)

        # Within timeout - should not raise (sample_spec.timeout_seconds is 60)
        tracker.started_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        tracker.check_timeout_or_raise()  # Should pass

        # Exceed timeout - should raise (more than 60 seconds)
        tracker.started_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        with pytest.raises(TimeoutSecondsExceeded):
            tracker.check_timeout_or_raise()

    def test_step_4_set_status_to_timeout(self, db_session, sample_spec, sample_run):
        """
        Step 4: When timeout reached, set status to timeout.

        Verifies that run.status transitions to 'timeout'.
        """
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        kernel.handle_timeout_exceeded(sample_run, error)

        assert sample_run.status == "timeout"

    def test_step_5_set_error_message_timeout_exceeded(self, db_session, sample_spec, sample_run):
        """
        Step 5: Set error message to timeout_exceeded.

        Verifies that run.error is set to 'timeout_exceeded'.
        """
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        result = kernel.handle_timeout_exceeded(sample_run, error)

        assert sample_run.error == "timeout_exceeded"
        assert result.error == "timeout_exceeded"

    def test_step_6_record_timeout_event_with_elapsed_seconds(self, db_session, sample_spec, sample_run):
        """
        Step 6: Record timeout event with elapsed_seconds in payload.

        Verifies that a timeout event is recorded with elapsed_seconds.
        """
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Set elapsed time
        kernel._budget_tracker.started_at = (
            datetime.now(timezone.utc) - timedelta(seconds=65)
        )

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        kernel.handle_timeout_exceeded(sample_run, error)

        # Verify timeout event
        timeout_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id,
            AgentEvent.event_type == "timeout"
        ).all()

        assert len(timeout_events) == 1
        payload = timeout_events[0].payload
        assert "elapsed_seconds" in payload
        assert payload["elapsed_seconds"] >= 60
        assert "timeout_seconds" in payload

    def test_step_7_ensure_partial_work_committed(self, db_session, sample_spec, sample_run):
        """
        Step 7: Ensure partial work is committed before termination.

        Verifies that work done before timeout is persisted.
        """
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Do some work
        kernel.record_turn_complete(sample_run, {"action": "step1"})
        kernel.record_turn_complete(sample_run, {"action": "step2"})

        assert sample_run.turns_used == 2

        error = TimeoutSecondsExceeded(
            elapsed_seconds=65.0,
            timeout_seconds=60,
            run_id=sample_run.id,
        )

        kernel.handle_timeout_exceeded(sample_run, error)

        # Verify partial work is committed by re-querying
        db_session.expire_all()
        fresh_run = db_session.query(AgentRun).filter(
            AgentRun.id == sample_run.id
        ).first()

        assert fresh_run.turns_used == 2
        assert fresh_run.status == "timeout"

        # Verify events are committed
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id
        ).all()
        assert len(events) >= 3  # started + 2 turn_complete + timeout

    def test_step_8_handle_long_running_tool_calls(self, db_session, sample_spec, sample_run):
        """
        Step 8: Handle long-running tool calls that exceed timeout.

        Verifies that if a tool call takes longer than timeout,
        the timeout is detected after the turn completes.
        """
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            # Simulate a long-running tool call on turn 2
            # The tool call "takes" so long that it exceeds timeout
            if turn_count[0] == 2:
                # After this tool call completes, we've exceeded timeout
                kernel._budget_tracker.started_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=100)
                )
            # Never complete naturally
            return False, {"tool_call": f"tool_{turn_count[0]}"}

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        # The execution should timeout after the long tool call
        assert result.status == "timeout"
        assert result.error == "timeout_exceeded"
        # At least 2 turns should have executed (the long one completes before timeout is checked)
        assert result.turns_used >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
