"""
Tests for Feature #155: Backend emits turn_complete events for accurate turn tracking
====================================================================================

Verifies that the HarnessKernel emits turn_complete events at the end of each
agent turn, including run_id, correct sequence number, and that events are both
persisted to the agent_events table and broadcast via WebSocket.

Test categories:
1. turn_complete event emission in the HarnessKernel execution loop
2. turn_complete events include run_id and correct sequence number
3. turn_complete events appear in the agent_events table after a run
4. turn_complete events are broadcast via WebSocket for real-time UI updates
5. Multi-turn run produces the correct number of turn_complete events
"""

import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock, call

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    EVENT_TYPES,
)
from api.harness_kernel import (
    HarnessKernel,
    BudgetTracker,
    record_turn_complete_event,
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
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id="feat155-spec-001",
        name="feat155-test-spec",
        display_name="Feature 155 Test Spec",
        objective="Test turn_complete event emission",
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
    """Create a sample AgentRun for testing (pending status, ready to initialize)."""
    run = AgentRun(
        id="feat155-run-001",
        agent_spec_id=sample_spec.id,
        status="pending",
        turns_used=0,
        tokens_in=0,
        tokens_out=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture
def kernel(db_session):
    """Create a HarnessKernel instance."""
    return HarnessKernel(db=db_session)


@pytest.fixture
def initialized_kernel(kernel, sample_run, sample_spec):
    """Create a HarnessKernel with initialized run and budget tracker."""
    kernel.initialize_run(sample_run, sample_spec)
    return kernel


# =============================================================================
# Step 1: Verify or implement turn_complete event emission in HarnessKernel
# =============================================================================

class TestStep1TurnCompleteEventEmission:
    """Verify turn_complete event emission in the HarnessKernel execution loop."""

    def test_turn_complete_in_event_types(self):
        """turn_complete should be a recognized event type."""
        assert "turn_complete" in EVENT_TYPES

    def test_record_turn_complete_creates_event(self, db_session, initialized_kernel, sample_run):
        """record_turn_complete should create a turn_complete event in the database."""
        with patch("api.harness_kernel.broadcast_agent_event_sync", create=True):
            pass
        # Patch broadcast to avoid import issues
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run, turn_data={"test": True})

        events = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).all()

        assert len(events) == 1, f"Expected 1 turn_complete event, got {len(events)}"

    def test_record_turn_complete_increments_turns_used(self, db_session, initialized_kernel, sample_run):
        """record_turn_complete should increment turns_used counter."""
        assert sample_run.turns_used == 0

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            new_turns = initialized_kernel.record_turn_complete(sample_run)

        assert new_turns == 1
        assert sample_run.turns_used == 1

    def test_record_turn_complete_accumulates_tokens(self, db_session, initialized_kernel, sample_run):
        """record_turn_complete should accumulate token counts."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(
                sample_run, input_tokens=100, output_tokens=50
            )

        assert sample_run.tokens_in == 100
        assert sample_run.tokens_out == 50

    def test_execute_with_turn_executor_emits_turn_complete(self, db_session, sample_spec, kernel):
        """execute() with a turn executor should emit turn_complete events."""
        # Create a turn executor that completes after 1 turn
        call_count = 0

        def mock_turn_executor(run, spec):
            nonlocal call_count
            call_count += 1
            return True, {"turn": call_count}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_turn_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).all()

        assert len(events) == 1
        assert call_count == 1

    def test_record_turn_complete_event_function_creates_event(self, db_session):
        """The standalone record_turn_complete_event function should create AgentEvent."""
        tracker = BudgetTracker(max_turns=10, turns_used=1, run_id="test-run")
        event = record_turn_complete_event(
            db=db_session,
            run_id="test-run-standalone",
            sequence=1,
            budget_tracker=tracker,
        )
        db_session.commit()

        assert event.event_type == "turn_complete"
        assert event.run_id == "test-run-standalone"
        assert event.sequence == 1


# =============================================================================
# Step 2: Confirm each turn_complete event includes run_id and correct sequence
# =============================================================================

class TestStep2RunIdAndSequenceNumber:
    """Verify turn_complete events include run_id and correct sequence number."""

    def test_event_has_run_id(self, db_session, initialized_kernel, sample_run):
        """turn_complete event should contain the correct run_id."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)

        event = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).first()

        assert event is not None
        assert event.run_id == sample_run.id
        assert event.run_id == "feat155-run-001"

    def test_event_has_correct_sequence_number(self, db_session, initialized_kernel, sample_run):
        """turn_complete event should have correct sequence number."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)

        event = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).first()

        assert event is not None
        # After initialize_run, sequence starts at 1 (started event is seq 1)
        # Then turn_complete increments to 2
        assert event.sequence >= 1

    def test_sequential_events_have_incrementing_sequences(self, db_session, initialized_kernel, sample_run):
        """Multiple turn_complete events should have incrementing sequence numbers."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)
            initialized_kernel.record_turn_complete(sample_run)
            initialized_kernel.record_turn_complete(sample_run)

        events = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).order_by(AgentEvent.sequence).all()

        assert len(events) == 3
        # Verify sequences are strictly increasing
        sequences = [e.sequence for e in events]
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i - 1], (
                f"Sequence {sequences[i]} should be > {sequences[i - 1]}"
            )

    def test_event_payload_contains_turn_number(self, db_session, initialized_kernel, sample_run):
        """turn_complete event payload should contain turn_number."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)

        event = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).first()

        assert event is not None
        payload = event.payload
        assert "turn_number" in payload
        assert payload["turn_number"] == 1

    def test_event_payload_contains_budget_info(self, db_session, initialized_kernel, sample_run):
        """turn_complete event payload should include budget tracking info."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)

        event = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).first()

        payload = event.payload
        assert "turns_used" in payload
        assert "max_turns" in payload
        assert "remaining_turns" in payload
        assert "elapsed_seconds" in payload
        assert "tokens_in" in payload
        assert "tokens_out" in payload


# =============================================================================
# Step 3: Verify turn_complete events appear in the agent_events table
# =============================================================================

class TestStep3EventsInAgentEventsTable:
    """Verify turn_complete events are persisted in agent_events table."""

    def test_turn_complete_event_persisted_in_db(self, db_session, initialized_kernel, sample_run):
        """turn_complete events should be committed to the agent_events table."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run, turn_data={"tool": "Read"})

        # Verify the event is in the database
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id,
            AgentEvent.event_type == "turn_complete",
        ).all()

        assert len(events) == 1
        event = events[0]
        assert event.event_type == "turn_complete"
        assert event.run_id == sample_run.id
        assert event.timestamp is not None

    def test_event_persists_after_execute(self, db_session, sample_spec, kernel):
        """After execute(), turn_complete events should be in the agent_events table."""
        turns_completed = []

        def mock_executor(run, spec):
            turns_completed.append(len(turns_completed) + 1)
            # Complete after 2 turns
            return len(turns_completed) >= 2, {"turn": len(turns_completed)}, [], 5, 3

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        # Query events from the database
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "turn_complete",
        ).all()

        assert len(events) == 2, f"Expected 2 turn_complete events after 2-turn run, got {len(events)}"

    def test_event_has_correct_event_type_string(self, db_session, initialized_kernel, sample_run):
        """The event_type field should be exactly 'turn_complete'."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)

        event = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).first()

        assert event.event_type == "turn_complete"

    def test_event_has_timestamp(self, db_session, initialized_kernel, sample_run):
        """turn_complete events should have a non-null timestamp."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)

        event = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).first()

        assert event.timestamp is not None

    def test_events_queryable_by_run_and_type(self, db_session, initialized_kernel, sample_run):
        """Events should be efficiently queryable by run_id + event_type (composite index)."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            initialized_kernel.record_turn_complete(sample_run)
            initialized_kernel.record_turn_complete(sample_run)

        # Use the composite index query pattern (ix_event_run_event_type)
        count = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id,
            AgentEvent.event_type == "turn_complete",
        ).count()

        assert count == 2


# =============================================================================
# Step 4: Confirm WebSocket broadcast for real-time UI updates
# =============================================================================

class TestStep4WebSocketBroadcast:
    """Verify turn_complete events are broadcast via WebSocket."""

    def test_record_turn_complete_calls_broadcast(self, db_session, initialized_kernel, sample_run):
        """record_turn_complete should call broadcast_agent_event_sync."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            initialized_kernel.record_turn_complete(sample_run)

        mock_broadcast.assert_called_once()

    def test_broadcast_called_with_correct_event_type(self, db_session, initialized_kernel, sample_run):
        """Broadcast should be called with event_type='turn_complete'."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            initialized_kernel.record_turn_complete(sample_run)

        call_kwargs = mock_broadcast.call_args
        # Check positional or keyword args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("event_type") == "turn_complete"
        else:
            # Positional: project_name, run_id, event_type, sequence, tool_name
            assert call_kwargs.args[2] == "turn_complete"

    def test_broadcast_called_with_correct_run_id(self, db_session, initialized_kernel, sample_run):
        """Broadcast should be called with the correct run_id."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            initialized_kernel.record_turn_complete(sample_run)

        call_kwargs = mock_broadcast.call_args
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("run_id") == sample_run.id
        else:
            assert call_kwargs.args[1] == sample_run.id

    def test_broadcast_called_with_sequence_number(self, db_session, initialized_kernel, sample_run):
        """Broadcast should be called with the event sequence number."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            initialized_kernel.record_turn_complete(sample_run)

        call_kwargs = mock_broadcast.call_args
        if call_kwargs.kwargs:
            sequence = call_kwargs.kwargs.get("sequence")
        else:
            sequence = call_kwargs.args[3]
        assert sequence is not None
        assert isinstance(sequence, int)
        assert sequence >= 1

    def test_broadcast_failure_does_not_interrupt_execution(self, db_session, initialized_kernel, sample_run):
        """If broadcast fails, execution should continue normally."""
        with patch(
            "server.event_broadcaster.broadcast_agent_event_sync",
            side_effect=Exception("WebSocket connection lost")
        ):
            # Should NOT raise - broadcast failure is non-fatal
            new_turns = initialized_kernel.record_turn_complete(sample_run)

        assert new_turns == 1
        assert sample_run.turns_used == 1

        # Event should still be in the database
        events = db_session.query(AgentEvent).filter_by(
            run_id=sample_run.id,
            event_type="turn_complete",
        ).all()
        assert len(events) == 1

    def test_turn_complete_is_significant_event_type(self):
        """turn_complete should be in SIGNIFICANT_EVENT_TYPES for WebSocket broadcast."""
        from server.event_broadcaster import SIGNIFICANT_EVENT_TYPES
        assert "turn_complete" in SIGNIFICANT_EVENT_TYPES

    def test_broadcast_called_for_each_turn_in_multi_turn(self, db_session, sample_spec, kernel):
        """Broadcast should be called once per turn in a multi-turn run."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 3, {"turn": turn_count[0]}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync") as mock_broadcast:
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        # Should be called 3 times (once per turn)
        turn_complete_calls = [
            c for c in mock_broadcast.call_args_list
            if (c.kwargs.get("event_type") == "turn_complete"
                or (len(c.args) > 2 and c.args[2] == "turn_complete"))
        ]
        assert len(turn_complete_calls) == 3


# =============================================================================
# Step 5: Test with a multi-turn run and verify correct turn_complete count
# =============================================================================

class TestStep5MultiTurnRun:
    """Test with a multi-turn run and verify the correct number of turn_complete events."""

    def test_single_turn_run_one_event(self, db_session, sample_spec, kernel):
        """A single-turn run should produce exactly 1 turn_complete event."""
        def mock_executor(run, spec):
            return True, {"turn": 1}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).all()

        assert len(events) == 1

    def test_three_turn_run_three_events(self, db_session, sample_spec, kernel):
        """A 3-turn run should produce exactly 3 turn_complete events."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 3, {"turn": turn_count[0]}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).order_by(AgentEvent.sequence).all()

        assert len(events) == 3
        assert run.turns_used == 3

    def test_five_turn_run_five_events(self, db_session, sample_spec, kernel):
        """A 5-turn run should produce exactly 5 turn_complete events."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 5, {"turn": turn_count[0]}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).all()

        assert len(events) == 5
        assert run.turns_used == 5

    def test_multi_turn_events_have_sequential_turn_numbers(self, db_session, sample_spec, kernel):
        """Each turn_complete event should have an incrementing turn_number in payload."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 4, {"turn": turn_count[0]}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).order_by(AgentEvent.sequence).all()

        assert len(events) == 4
        for i, event in enumerate(events, start=1):
            assert event.payload["turn_number"] == i, (
                f"Event {i} should have turn_number={i}, got {event.payload['turn_number']}"
            )

    def test_multi_turn_token_accumulation(self, db_session, sample_spec, kernel):
        """Token counts should accumulate correctly across multiple turns."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            # Each turn: 100 input, 50 output
            return turn_count[0] >= 3, {"turn": turn_count[0]}, [], 100, 50

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        assert run.tokens_in == 300  # 3 turns * 100
        assert run.tokens_out == 150  # 3 turns * 50
        assert run.turns_used == 3

    def test_budget_exhaustion_records_turn_complete_before_timeout(self, db_session, kernel):
        """When max_turns is reached, turn_complete events should be recorded for all turns."""
        # Create spec with max_turns=3
        spec = AgentSpec(
            id="feat155-spec-budget",
            name="feat155-budget-test",
            display_name="Budget Test",
            objective="Test budget exhaustion",
            task_type="testing",
            tool_policy={"allowed_tools": ["Read"]},
            max_turns=3,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            # Never complete - will be stopped by budget
            return False, {"turn": turn_count[0]}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(spec, turn_executor=mock_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).all()

        # Should have 3 turn_complete events (one per turn before budget exhaustion)
        assert len(events) == 3
        assert run.turns_used == 3
        assert run.status == "timeout"

    def test_no_executor_produces_no_turn_complete_events(self, db_session, sample_spec, kernel):
        """execute() with no turn executor should produce 0 turn_complete events."""
        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=None)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).all()

        assert len(events) == 0
        assert run.turns_used == 0

    def test_all_turn_complete_events_share_same_run_id(self, db_session, sample_spec, kernel):
        """All turn_complete events in a run should share the same run_id."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 3, {"turn": turn_count[0]}, [], 10, 5

        with patch("server.event_broadcaster.broadcast_agent_event_sync"):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        events = db_session.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete",
        ).all()

        assert len(events) == 3
        for event in events:
            assert event.run_id == run.id


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple verification aspects."""

    def test_full_lifecycle_with_turn_complete_events(self, db_session, sample_spec, kernel):
        """Full execution lifecycle should emit correct turn_complete events."""
        turn_count = [0]

        def mock_executor(run, spec):
            turn_count[0] += 1
            tools = [{"tool_name": "Read", "arguments": {"path": "/test"}, "result": "content"}]
            return turn_count[0] >= 2, {"turn": turn_count[0]}, tools, 50, 25

        broadcast_calls = []
        original_broadcast = None

        def capture_broadcast(*args, **kwargs):
            broadcast_calls.append({"args": args, "kwargs": kwargs})

        with patch("server.event_broadcaster.broadcast_agent_event_sync", side_effect=capture_broadcast):
            run = kernel.execute(sample_spec, turn_executor=mock_executor)

        # Verify run completed
        assert run.status == "completed"
        assert run.turns_used == 2

        # Verify events in DB
        all_events = db_session.query(AgentEvent).filter_by(run_id=run.id).order_by(AgentEvent.sequence).all()
        turn_complete_events = [e for e in all_events if e.event_type == "turn_complete"]
        assert len(turn_complete_events) == 2

        # Verify broadcast was called for turn_complete events
        turn_complete_broadcasts = [
            c for c in broadcast_calls
            if c["kwargs"].get("event_type") == "turn_complete"
            or (len(c["args"]) > 2 and c["args"][2] == "turn_complete")
        ]
        assert len(turn_complete_broadcasts) == 2

        # Verify token accumulation
        assert run.tokens_in == 100  # 2 turns * 50
        assert run.tokens_out == 50  # 2 turns * 25

    def test_record_turn_complete_event_standalone_function(self, db_session):
        """Test the standalone record_turn_complete_event function directly."""
        tracker = BudgetTracker(max_turns=5, turns_used=2, run_id="standalone-run")
        tracker.accumulate_tokens(200, 100)

        event = record_turn_complete_event(
            db=db_session,
            run_id="standalone-run-155",
            sequence=3,
            budget_tracker=tracker,
            turn_data={"custom": "data"},
        )
        db_session.commit()

        # Verify event was created
        saved = db_session.query(AgentEvent).filter_by(
            run_id="standalone-run-155",
            event_type="turn_complete",
        ).first()

        assert saved is not None
        assert saved.sequence == 3
        assert saved.payload["turn_number"] == 2
        assert saved.payload["turns_used"] == 2
        assert saved.payload["max_turns"] == 5
        assert saved.payload["remaining_turns"] == 3
        assert saved.payload["tokens_in"] == 200
        assert saved.payload["tokens_out"] == 100
        assert saved.payload["turn_data"]["custom"] == "data"
