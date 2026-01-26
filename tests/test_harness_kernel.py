"""
Tests for HarnessKernel
=======================

Comprehensive tests for the HarnessKernel class and max_turns budget enforcement
(Feature #27).

Test categories:
1. BudgetTracker unit tests
2. Event recording tests
3. HarnessKernel initialization tests
4. Budget enforcement tests
5. Turn completion tests
6. Persistence verification tests
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    AcceptanceSpec,
    Artifact,
)
from api.harness_kernel import (
    BudgetTracker,
    BudgetExceeded,
    MaxTurnsExceeded,
    HarnessKernel,
    ExecutionResult,
    create_timeout_event,
    record_turn_complete_event,
    record_timeout_event,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with session."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Create all tables including agentspec tables
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


@pytest.fixture
def sample_spec(db_session):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id="test-spec-001",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=10,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id="test-run-001",
        agent_spec_id=sample_spec.id,
        status="pending",
        turns_used=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


# =============================================================================
# BudgetTracker Unit Tests
# =============================================================================

class TestBudgetTracker:
    """Tests for BudgetTracker class."""

    def test_init_valid_parameters(self):
        """Test initialization with valid parameters."""
        tracker = BudgetTracker(max_turns=50, turns_used=0, run_id="run-123")
        assert tracker.max_turns == 50
        assert tracker.turns_used == 0
        assert tracker.run_id == "run-123"

    def test_init_invalid_max_turns(self):
        """Test initialization fails with max_turns < 1."""
        with pytest.raises(ValueError, match="max_turns must be >= 1"):
            BudgetTracker(max_turns=0)

    def test_init_invalid_turns_used(self):
        """Test initialization fails with negative turns_used."""
        with pytest.raises(ValueError, match="turns_used must be >= 0"):
            BudgetTracker(max_turns=10, turns_used=-1)

    def test_remaining_turns_property(self):
        """Test remaining_turns calculation."""
        tracker = BudgetTracker(max_turns=10, turns_used=3)
        assert tracker.remaining_turns == 7

    def test_remaining_turns_at_limit(self):
        """Test remaining_turns when at limit."""
        tracker = BudgetTracker(max_turns=10, turns_used=10)
        assert tracker.remaining_turns == 0

    def test_remaining_turns_over_limit(self):
        """Test remaining_turns doesn't go negative."""
        tracker = BudgetTracker(max_turns=10, turns_used=15)
        assert tracker.remaining_turns == 0

    def test_is_exhausted_false(self):
        """Test is_exhausted when budget available."""
        tracker = BudgetTracker(max_turns=10, turns_used=5)
        assert tracker.is_exhausted is False

    def test_is_exhausted_true(self):
        """Test is_exhausted when budget used up."""
        tracker = BudgetTracker(max_turns=10, turns_used=10)
        assert tracker.is_exhausted is True

    def test_can_execute_turn_true(self):
        """Test can_execute_turn returns True when budget available."""
        tracker = BudgetTracker(max_turns=10, turns_used=9)
        assert tracker.can_execute_turn() is True

    def test_can_execute_turn_false(self):
        """Test can_execute_turn returns False when budget exhausted."""
        tracker = BudgetTracker(max_turns=10, turns_used=10)
        assert tracker.can_execute_turn() is False

    def test_increment_turns(self):
        """Test increment_turns increases counter."""
        tracker = BudgetTracker(max_turns=10, turns_used=3)
        result = tracker.increment_turns()
        assert result == 4
        assert tracker.turns_used == 4

    def test_check_budget_or_raise_success(self):
        """Test check_budget_or_raise succeeds when budget available."""
        tracker = BudgetTracker(max_turns=10, turns_used=5, run_id="test")
        tracker.check_budget_or_raise()  # Should not raise

    def test_check_budget_or_raise_failure(self):
        """Test check_budget_or_raise raises when budget exhausted."""
        tracker = BudgetTracker(max_turns=10, turns_used=10, run_id="test-run")
        with pytest.raises(MaxTurnsExceeded) as exc_info:
            tracker.check_budget_or_raise()

        assert exc_info.value.turns_used == 10
        assert exc_info.value.max_turns == 10
        assert exc_info.value.run_id == "test-run"
        assert "max_turns_exceeded" in str(exc_info.value)

    def test_mark_persisted_and_is_persisted(self):
        """Test persistence tracking."""
        tracker = BudgetTracker(max_turns=10, turns_used=0)
        # Initially, turns_used=0 and _last_persisted_turns=0, so is_persisted is True
        # This is expected because no turns have been used yet
        assert tracker.is_persisted() is True

        # After incrementing, it should no longer be persisted
        tracker.increment_turns()
        assert tracker.is_persisted() is False

        tracker.mark_persisted()
        assert tracker.is_persisted() is True

        tracker.increment_turns()
        assert tracker.is_persisted() is False

        tracker.mark_persisted()
        assert tracker.is_persisted() is True

    def test_to_payload(self):
        """Test to_payload returns correct dict."""
        tracker = BudgetTracker(max_turns=10, turns_used=7)
        payload = tracker.to_payload()

        # Check turns-related fields
        assert payload["turns_used"] == 7
        assert payload["max_turns"] == 10
        assert payload["remaining_turns"] == 3
        assert payload["is_exhausted"] is False

        # Check timeout-related fields (Feature #28)
        # elapsed_seconds is 0 because started_at is None
        assert payload["elapsed_seconds"] == 0.0
        assert payload["timeout_seconds"] == 1800  # default
        assert payload["remaining_seconds"] == 1800.0
        assert payload["is_timed_out"] is False


# =============================================================================
# Exception Tests
# =============================================================================

class TestExceptions:
    """Tests for budget exception classes."""

    def test_budget_exceeded_base(self):
        """Test BudgetExceeded base exception."""
        exc = BudgetExceeded(
            budget_type="test_budget",
            current_value=10,
            max_value=5,
            run_id="run-123",
        )
        assert exc.budget_type == "test_budget"
        assert exc.current_value == 10
        assert exc.max_value == 5
        assert exc.run_id == "run-123"
        assert "run-123" in str(exc)

    def test_max_turns_exceeded(self):
        """Test MaxTurnsExceeded exception."""
        exc = MaxTurnsExceeded(
            turns_used=15,
            max_turns=10,
            run_id="run-456",
        )
        assert exc.turns_used == 15
        assert exc.max_turns == 10
        assert exc.run_id == "run-456"
        assert exc.budget_type == "max_turns"
        assert "max_turns_exceeded" in str(exc)


# =============================================================================
# Event Recording Tests
# =============================================================================

class TestEventRecording:
    """Tests for event recording functions."""

    def test_create_timeout_event(self):
        """Test create_timeout_event returns correct structure."""
        tracker = BudgetTracker(max_turns=10, turns_used=10, run_id="run-001")
        event = create_timeout_event(
            run_id="run-001",
            sequence=5,
            budget_tracker=tracker,
            reason="max_turns_exceeded",
        )

        assert event["run_id"] == "run-001"
        assert event["sequence"] == 5
        assert event["event_type"] == "timeout"
        assert event["tool_name"] is None
        assert isinstance(event["timestamp"], datetime)

        payload = event["payload"]
        assert payload["reason"] == "max_turns_exceeded"
        assert payload["turns_used"] == 10
        assert payload["max_turns"] == 10
        assert payload["remaining_turns"] == 0
        assert payload["is_exhausted"] is True

    def test_record_turn_complete_event(self, db_session, sample_run):
        """Test record_turn_complete_event creates event in DB."""
        tracker = BudgetTracker(max_turns=10, turns_used=3, run_id=sample_run.id)

        event = record_turn_complete_event(
            db=db_session,
            run_id=sample_run.id,
            sequence=1,
            budget_tracker=tracker,
            turn_data={"tool_calls": ["Read", "Write"]},
        )

        assert event.run_id == sample_run.id
        assert event.sequence == 1
        assert event.event_type == "turn_complete"
        assert event.payload["turn_number"] == 3
        assert event.payload["turns_used"] == 3
        assert event.payload["turn_data"]["tool_calls"] == ["Read", "Write"]

    def test_record_timeout_event(self, db_session, sample_run):
        """Test record_timeout_event creates event in DB."""
        tracker = BudgetTracker(max_turns=10, turns_used=10, run_id=sample_run.id)

        event = record_timeout_event(
            db=db_session,
            run_id=sample_run.id,
            sequence=11,
            budget_tracker=tracker,
            reason="max_turns_exceeded",
        )

        db_session.commit()

        assert event.run_id == sample_run.id
        assert event.sequence == 11
        assert event.event_type == "timeout"
        assert event.payload["reason"] == "max_turns_exceeded"
        assert event.payload["turns_used"] == 10


# =============================================================================
# HarnessKernel Tests
# =============================================================================

class TestHarnessKernel:
    """Tests for HarnessKernel class."""

    def test_init(self, db_session):
        """Test HarnessKernel initialization."""
        kernel = HarnessKernel(db_session)
        assert kernel.db is db_session
        assert kernel._budget_tracker is None
        assert kernel._event_sequence == 0

    def test_initialize_run(self, db_session, sample_spec, sample_run):
        """Test initialize_run sets up run correctly."""
        kernel = HarnessKernel(db_session)

        tracker = kernel.initialize_run(sample_run, sample_spec)

        # Check run state
        assert sample_run.status == "running"
        assert sample_run.turns_used == 0
        assert sample_run.started_at is not None

        # Check budget tracker
        assert tracker.max_turns == 10
        assert tracker.turns_used == 0
        assert tracker.run_id == sample_run.id

        # Check started event was recorded
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id
        ).all()
        assert len(events) == 1
        assert events[0].event_type == "started"

    def test_initialize_run_resets_turns(self, db_session, sample_spec, sample_run):
        """Test initialize_run resets turns_used to 0 even if it had a value."""
        sample_run.turns_used = 5  # Pretend it had some value
        db_session.commit()

        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        assert sample_run.turns_used == 0

    def test_check_budget_before_turn_success(self, db_session, sample_spec, sample_run):
        """Test check_budget_before_turn passes when budget available."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        kernel.check_budget_before_turn(sample_run)  # Should not raise

    def test_check_budget_before_turn_raises(self, db_session, sample_spec, sample_run):
        """Test check_budget_before_turn raises when budget exhausted."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Exhaust budget
        kernel._budget_tracker.turns_used = sample_spec.max_turns

        with pytest.raises(MaxTurnsExceeded):
            kernel.check_budget_before_turn(sample_run)

    def test_check_budget_before_turn_no_init(self, db_session, sample_run):
        """Test check_budget_before_turn raises if not initialized."""
        kernel = HarnessKernel(db_session)

        with pytest.raises(RuntimeError, match="Budget tracker not initialized"):
            kernel.check_budget_before_turn(sample_run)

    def test_record_turn_complete(self, db_session, sample_spec, sample_run):
        """Test record_turn_complete updates turns and creates event."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        new_turns = kernel.record_turn_complete(
            sample_run,
            turn_data={"tool_calls": ["Read"]},
        )

        assert new_turns == 1
        assert sample_run.turns_used == 1

        # Check event was recorded
        events = db_session.query(AgentEvent).filter(
            AgentEvent.event_type == "turn_complete"
        ).all()
        assert len(events) == 1
        assert events[0].payload["turn_number"] == 1

    def test_record_turn_complete_persists(self, db_session, sample_spec, sample_run):
        """Test record_turn_complete persists turns_used to database."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        kernel.record_turn_complete(sample_run)

        # Verify persistence by querying fresh
        db_session.expire(sample_run)
        fresh_run = db_session.query(AgentRun).filter(
            AgentRun.id == sample_run.id
        ).first()
        assert fresh_run.turns_used == 1

        # Also check tracker reports persisted
        assert kernel._budget_tracker.is_persisted()

    def test_handle_budget_exceeded(self, db_session, sample_spec, sample_run):
        """Test handle_budget_exceeded sets timeout status and records event."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Simulate 10 turns being used (update both tracker and run to stay in sync)
        kernel._budget_tracker.turns_used = 10
        sample_run.turns_used = 10

        error = MaxTurnsExceeded(
            turns_used=10,
            max_turns=10,
            run_id=sample_run.id,
        )

        result = kernel.handle_budget_exceeded(sample_run, error)

        # Check result
        assert result.status == "timeout"
        assert result.turns_used == 10
        assert result.error == "max_turns_exceeded"
        assert result.is_timeout is True

        # Check run state
        assert sample_run.status == "timeout"
        assert sample_run.error == "max_turns_exceeded"
        assert sample_run.completed_at is not None

        # Check timeout event was recorded
        events = db_session.query(AgentEvent).filter(
            AgentEvent.event_type == "timeout"
        ).all()
        assert len(events) == 1
        assert events[0].payload["reason"] == "max_turns_exceeded"
        assert events[0].payload["turns_used"] == 10


# =============================================================================
# Integration Tests
# =============================================================================

class TestHarnessKernelIntegration:
    """Integration tests for HarnessKernel execution."""

    def test_execute_with_budget_completes_normally(self, db_session, sample_spec, sample_run):
        """Test execution completes normally within budget."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            # Complete after 3 turns
            return turn_count[0] >= 3, {"turn": turn_count[0]}

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        assert result.status == "completed"
        assert result.turns_used == 3
        assert result.error is None
        assert sample_run.status == "completed"

    def test_execute_with_budget_hits_limit(self, db_session, sample_spec, sample_run):
        """Test execution times out when budget exhausted."""
        # Set low max_turns
        sample_spec.max_turns = 3
        db_session.commit()

        kernel = HarnessKernel(db_session)

        def turn_executor(run, spec):
            # Never completes on its own
            return False, {"running": True}

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        assert result.status == "timeout"
        assert result.turns_used == 3
        assert result.error == "max_turns_exceeded"
        assert sample_run.status == "timeout"
        assert sample_run.error == "max_turns_exceeded"

    def test_execute_with_budget_handles_errors(self, db_session, sample_spec, sample_run):
        """Test execution handles unexpected errors gracefully."""
        kernel = HarnessKernel(db_session)

        def turn_executor(run, spec):
            raise RuntimeError("Unexpected error!")

        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        assert result.status == "failed"
        assert "Unexpected error" in result.error
        assert sample_run.status == "failed"

    def test_execute_with_budget_records_all_events(self, db_session, sample_spec, sample_run):
        """Test all events are recorded during execution."""
        sample_spec.max_turns = 5
        db_session.commit()

        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 2, {"turn": turn_count[0]}

        kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id
        ).order_by(AgentEvent.sequence).all()

        # Should have: started, turn_complete x2
        assert len(events) == 3
        assert events[0].event_type == "started"
        assert events[1].event_type == "turn_complete"
        assert events[2].event_type == "turn_complete"

    def test_execute_budget_exhaustion_records_timeout_event(
        self, db_session, sample_spec, sample_run
    ):
        """Test timeout event is recorded when budget exhausted."""
        sample_spec.max_turns = 2
        db_session.commit()

        kernel = HarnessKernel(db_session)

        def turn_executor(run, spec):
            return False, {}

        kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        events = db_session.query(AgentEvent).filter(
            AgentEvent.event_type == "timeout"
        ).all()

        assert len(events) == 1
        assert events[0].payload["reason"] == "max_turns_exceeded"
        assert events[0].payload["turns_used"] == 2
        assert events[0].payload["max_turns"] == 2


# =============================================================================
# Persistence Verification Tests
# =============================================================================

class TestPersistenceVerification:
    """Tests for Step 8: Verify turns_used is persisted after each turn."""

    def test_turns_persisted_incrementally(self, db_session, sample_spec, sample_run):
        """Test that turns_used is committed after each turn."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        for expected_turns in range(1, 4):
            kernel.record_turn_complete(sample_run)

            # Create a new session to verify persistence
            db_session.expire(sample_run)
            fresh_run = db_session.query(AgentRun).filter(
                AgentRun.id == sample_run.id
            ).first()

            assert fresh_run.turns_used == expected_turns, (
                f"Expected turns_used={expected_turns} after turn, got {fresh_run.turns_used}"
            )

    def test_budget_tracker_tracks_persistence(self, db_session, sample_spec, sample_run):
        """Test BudgetTracker tracks persistence status correctly."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        tracker = kernel._budget_tracker
        assert tracker.is_persisted() is True  # After init

        # Simulate turn without using record_turn_complete
        tracker.increment_turns()
        assert tracker.is_persisted() is False

        # Use proper method
        kernel.record_turn_complete(sample_run)
        assert tracker.is_persisted() is True


# =============================================================================
# ExecutionResult Tests
# =============================================================================

class TestExecutionResult:
    """Tests for ExecutionResult class."""

    def test_is_success_true(self):
        """Test is_success returns True for completed+passed."""
        result = ExecutionResult(
            run_id="test",
            status="completed",
            turns_used=5,
            final_verdict="passed",
            error=None,
        )
        assert result.is_success is True

    def test_is_success_false_on_failed_verdict(self):
        """Test is_success returns False when verdict is failed."""
        result = ExecutionResult(
            run_id="test",
            status="completed",
            turns_used=5,
            final_verdict="failed",
            error=None,
        )
        assert result.is_success is False

    def test_is_success_false_on_error_status(self):
        """Test is_success returns False when status is not completed."""
        result = ExecutionResult(
            run_id="test",
            status="failed",
            turns_used=5,
            final_verdict=None,
            error="Some error",
        )
        assert result.is_success is False

    def test_is_timeout_true(self):
        """Test is_timeout returns True for timeout status."""
        result = ExecutionResult(
            run_id="test",
            status="timeout",
            turns_used=10,
            final_verdict=None,
            error="max_turns_exceeded",
        )
        assert result.is_timeout is True

    def test_is_timeout_false(self):
        """Test is_timeout returns False for non-timeout status."""
        result = ExecutionResult(
            run_id="test",
            status="completed",
            turns_used=5,
            final_verdict="passed",
            error=None,
        )
        assert result.is_timeout is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
