#!/usr/bin/env python3
"""
Test Suite for Feature #227: Audit Events Support Replay and Debugging
=======================================================================

Tests that audit events contain sufficient detail to understand and replay
agent decisions. This includes:

1. Events include full context needed for replay
2. Large payloads stored as artifacts with references
3. Event sequence reconstructable from run_id + sequence
4. Events support debugging failed agent runs

Feature Steps:
- Events include full context needed for replay
- Large payloads stored as artifacts with references
- Event sequence reconstructable from run_id + sequence
- Events support debugging failed agent runs
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Base, create_database, set_session_maker
from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
    Artifact,
    EVENT_PAYLOAD_MAX_SIZE,
    generate_uuid,
)
from api.event_recorder import EventRecorder
from api.event_replay import (
    ReplayableEvent,
    DebugContext,
    EventTimeline,
    EventReplayContext,
    get_replay_context,
    reconstruct_run_events,
    get_run_debug_context,
    verify_event_sequence_integrity,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def test_db():
    """Create a test database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        yield project_dir, SessionLocal
        engine.dispose()


@pytest.fixture
def db_session(test_db):
    """Create a database session for testing."""
    project_dir, SessionLocal = test_db
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def project_dir(test_db):
    """Get the project directory."""
    project_dir, _ = test_db
    return project_dir


@pytest.fixture
def test_spec(db_session):
    """Create a test AgentSpec."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec-replay",
        display_name="Test Spec for Replay",
        objective="Test objective for replay testing",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": ["bash", "read"]},
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def test_run(db_session, test_spec):
    """Create a test AgentRun in running state."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=test_spec.id,
        status="running",
    )
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture
def failed_run(db_session, test_spec):
    """Create a test AgentRun in failed state."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=test_spec.id,
        status="failed",
        error="Test failure error message",
        turns_used=5,
        tokens_in=1000,
        tokens_out=500,
    )
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture
def run_with_events(db_session, project_dir, test_spec):
    """Create a run with a complete event sequence."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=test_spec.id,
        status="completed",
        turns_used=3,
        tokens_in=500,
        tokens_out=200,
    )
    db_session.add(run)
    db_session.commit()

    # Record a sequence of events
    recorder = EventRecorder(db_session, project_dir)

    # Event 1: started
    recorder.record_started(
        run.id,
        objective="Test objective",
        spec_id=test_spec.id,
    )

    # Event 2: tool_call
    recorder.record_tool_call(
        run.id,
        tool_name="bash",
        arguments={"command": "ls -la"},
    )

    # Event 3: tool_result
    recorder.record_tool_result(
        run.id,
        tool_name="bash",
        result={"output": "file1.txt\nfile2.txt"},
        success=True,
    )

    # Event 4: turn_complete
    recorder.record_turn_complete(
        run.id,
        turn_number=1,
        tokens_in=100,
        tokens_out=50,
    )

    # Event 5: completed
    recorder.record_completed(
        run.id,
        verdict="passed",
        turns_used=1,
    )

    return run


# =============================================================================
# Step 1: Events Include Full Context Needed for Replay
# =============================================================================

class TestStep1EventsIncludeFullContext:
    """Test that events include full context needed for replay."""

    def test_started_event_has_objective(self, db_session, project_dir, test_run, test_spec):
        """Verify started events include objective context."""
        recorder = EventRecorder(db_session, project_dir)

        recorder.record_started(
            test_run.id,
            objective="Complete task X",
            spec_id=test_spec.id,
            extra={"project": "test-project"},
        )

        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events())

        assert len(events) == 1
        event = events[0]
        assert event.event_type == "started"
        assert event.full_payload["objective"] == "Complete task X"
        assert event.full_payload["spec_id"] == test_spec.id

    def test_tool_call_has_arguments(self, db_session, project_dir, test_run):
        """Verify tool_call events include full arguments."""
        recorder = EventRecorder(db_session, project_dir)

        recorder.record_tool_call(
            test_run.id,
            tool_name="bash",
            arguments={"command": "git status", "timeout": 30},
        )

        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events(event_type="tool_call"))

        assert len(events) == 1
        event = events[0]
        assert event.tool_name == "bash"
        assert event.full_payload["tool"] == "bash"
        assert event.full_payload["arguments"]["command"] == "git status"

    def test_tool_result_has_full_result(self, db_session, project_dir, test_run):
        """Verify tool_result events include full result data."""
        recorder = EventRecorder(db_session, project_dir)

        recorder.record_tool_result(
            test_run.id,
            tool_name="read",
            result={"content": "File content here", "lines": 10},
            success=True,
        )

        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events(event_type="tool_result"))

        assert len(events) == 1
        event = events[0]
        assert event.full_payload["success"] is True
        assert event.full_payload["result"]["content"] == "File content here"

    def test_failed_event_has_error_context(self, db_session, project_dir, failed_run):
        """Verify failed events include error context."""
        recorder = EventRecorder(db_session, project_dir)

        recorder.record_failed(
            failed_run.id,
            error="Connection timeout to external service",
            error_type="TimeoutError",
            traceback="File xyz.py, line 42...",
        )

        context = get_replay_context(db_session, project_dir, failed_run.id)
        events = list(context.get_events(event_type="failed"))

        assert len(events) == 1
        event = events[0]
        assert event.full_payload["error"] == "Connection timeout to external service"
        assert event.full_payload["error_type"] == "TimeoutError"
        assert "traceback" in event.full_payload


# =============================================================================
# Step 2: Large Payloads Stored as Artifacts with References
# =============================================================================

class TestStep2LargePayloadsAsArtifacts:
    """Test that large payloads are stored as artifacts with references."""

    def test_large_payload_creates_artifact(self, db_session, project_dir, test_run):
        """Verify large payloads create artifact references."""
        recorder = EventRecorder(db_session, project_dir)

        # Create payload larger than EVENT_PAYLOAD_MAX_SIZE
        large_output = "x" * 5000
        recorder.record_tool_result(
            test_run.id,
            tool_name="read",
            result={"content": large_output},
            success=True,
        )

        # Verify event has artifact_ref
        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == test_run.id
        ).first()

        assert event.payload_truncated is not None
        assert event.artifact_ref is not None

    def test_artifact_contains_full_payload(self, db_session, project_dir, test_run):
        """Verify artifact contains complete original payload."""
        recorder = EventRecorder(db_session, project_dir)

        large_data = {"content": "y" * 6000, "metadata": {"size": 6000}}
        recorder.record(test_run.id, "tool_result", payload=large_data)

        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == test_run.id
        ).first()

        # Retrieve full payload via replay context
        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events())

        assert len(events) == 1
        assert events[0].was_truncated is True
        assert events[0].full_payload["content"] == large_data["content"]
        assert events[0].full_payload["metadata"]["size"] == 6000

    def test_replay_context_retrieves_artifact_content(self, db_session, project_dir, test_run):
        """Verify replay context can retrieve content from artifact."""
        recorder = EventRecorder(db_session, project_dir)

        # Record multiple events, one with large payload
        recorder.record_started(test_run.id, objective="Test")
        recorder.record(test_run.id, "tool_result", payload={"output": "z" * 5000})

        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events())

        # First event (started) - not truncated
        assert events[0].was_truncated is False

        # Second event (tool_result) - truncated but full_payload available
        assert events[1].was_truncated is True
        assert len(events[1].full_payload["output"]) == 5000


# =============================================================================
# Step 3: Event Sequence Reconstructable from run_id + sequence
# =============================================================================

class TestStep3EventSequenceReconstruction:
    """Test that event sequence is reconstructable from run_id + sequence."""

    def test_events_ordered_by_sequence(self, db_session, project_dir, run_with_events):
        """Verify events are returned in sequence order."""
        context = get_replay_context(db_session, project_dir, run_with_events.id)
        events = list(context.get_events())

        # Should have 5 events in sequence order
        assert len(events) == 5

        sequences = [e.sequence for e in events]
        assert sequences == [1, 2, 3, 4, 5]

    def test_sequence_starts_at_1(self, db_session, project_dir, test_run):
        """Verify first event has sequence 1."""
        recorder = EventRecorder(db_session, project_dir)
        recorder.record_started(test_run.id, objective="Test")

        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == test_run.id
        ).first()

        assert event.sequence == 1

    def test_reconstruct_event_sequence_function(self, db_session, project_dir, run_with_events):
        """Verify reconstruct_run_events returns complete sequence."""
        events = reconstruct_run_events(db_session, project_dir, run_with_events.id)

        assert len(events) == 5

        # Check structure
        for event in events:
            assert "sequence" in event
            assert "event_type" in event
            assert "timestamp" in event
            assert "payload" in event

        # Check order
        assert events[0]["event_type"] == "started"
        assert events[4]["event_type"] == "completed"

    def test_get_event_by_sequence(self, db_session, project_dir, run_with_events):
        """Verify can retrieve specific event by sequence number."""
        context = get_replay_context(db_session, project_dir, run_with_events.id)

        # Get event at sequence 2 (tool_call)
        event = context.get_event_by_sequence(2)

        assert event is not None
        assert event.sequence == 2
        assert event.event_type == "tool_call"

    def test_verify_sequence_integrity(self, db_session, project_dir, run_with_events):
        """Verify sequence integrity checker works correctly."""
        result = verify_event_sequence_integrity(db_session, run_with_events.id)

        assert result["is_valid"] is True
        assert result["total_events"] == 5
        assert result["sequence_start"] == 1
        assert result["sequence_end"] == 5
        assert result["gaps"] == []
        assert result["errors"] == []

    def test_timeline_has_correct_statistics(self, db_session, project_dir, run_with_events):
        """Verify timeline includes correct statistics."""
        context = get_replay_context(db_session, project_dir, run_with_events.id)
        timeline = context.get_timeline()

        assert timeline.run_id == run_with_events.id
        assert timeline.total_events == 5
        assert timeline.tool_call_count == 1
        assert timeline.turn_count == 1
        assert timeline.has_failure is False
        assert timeline.duration_seconds is not None


# =============================================================================
# Step 4: Events Support Debugging Failed Agent Runs
# =============================================================================

class TestStep4DebugFailedRuns:
    """Test that events support debugging failed agent runs."""

    def test_debug_context_for_failed_run(self, db_session, project_dir, failed_run):
        """Verify debug context is available for failed runs."""
        recorder = EventRecorder(db_session, project_dir)

        # Record events leading to failure
        recorder.record_started(failed_run.id, objective="Test task")
        recorder.record_tool_call(failed_run.id, "bash", {"command": "risky-cmd"})
        recorder.record_tool_result(
            failed_run.id, "bash",
            result=None,
            success=False,
            error="Command failed with exit code 1",
        )
        recorder.record_failed(failed_run.id, error="Tool execution failed")

        debug = get_run_debug_context(db_session, project_dir, failed_run.id)

        assert debug is not None
        assert debug.run_id == failed_run.id
        assert debug.run_status == "failed"
        assert debug.last_tool_call is not None
        assert debug.last_tool_result is not None

    def test_debug_context_includes_failure_reason(self, db_session, project_dir, failed_run):
        """Verify debug context includes human-readable failure reason."""
        recorder = EventRecorder(db_session, project_dir)

        recorder.record_started(failed_run.id, objective="Test")
        recorder.record_failed(failed_run.id, error="Out of memory")

        debug = get_run_debug_context(db_session, project_dir, failed_run.id)

        assert debug is not None
        assert "Out of memory" in debug.failure_reason or "error" in debug.failure_reason.lower()

    def test_debug_context_has_token_usage(self, db_session, project_dir, failed_run):
        """Verify debug context includes resource usage."""
        recorder = EventRecorder(db_session, project_dir)
        recorder.record_started(failed_run.id, objective="Test")
        recorder.record_failed(failed_run.id, error="Budget exceeded")

        debug = get_run_debug_context(db_session, project_dir, failed_run.id)

        assert debug.turns_used == 5  # From fixture
        assert debug.tokens_used == 1500  # 1000 + 500 from fixture

    def test_debug_context_not_available_for_completed_run(self, db_session, project_dir, run_with_events):
        """Verify debug context returns None for successful runs."""
        debug = get_run_debug_context(db_session, project_dir, run_with_events.id)
        assert debug is None

    def test_debug_context_for_timeout_run(self, db_session, project_dir, test_spec):
        """Verify debug context works for timeout runs."""
        # Create timeout run
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=test_spec.id,
            status="timeout",
            turns_used=50,
            tokens_in=10000,
            tokens_out=5000,
        )
        db_session.add(run)
        db_session.commit()

        recorder = EventRecorder(db_session, project_dir)
        recorder.record_started(run.id, objective="Long task")
        recorder.record(run.id, "timeout", payload={"reason": "Turn limit exceeded"})

        debug = get_run_debug_context(db_session, project_dir, run.id)

        assert debug is not None
        assert debug.run_status == "timeout"
        assert "timeout" in debug.failure_reason.lower() or "50 turns" in debug.failure_reason

    def test_debug_context_has_last_events(self, db_session, project_dir, failed_run):
        """Verify debug context includes last events for diagnosis."""
        recorder = EventRecorder(db_session, project_dir)

        recorder.record_started(failed_run.id, objective="Complex task")
        recorder.record_tool_call(failed_run.id, "bash", {"command": "cmd1"})
        recorder.record_tool_result(failed_run.id, "bash", {"output": "ok"}, success=True)
        recorder.record_tool_call(failed_run.id, "write", {"path": "/tmp/test.txt"})
        recorder.record_tool_result(
            failed_run.id, "write",
            result=None,
            success=False,
            error="Permission denied",
        )
        recorder.record_failed(failed_run.id, error="Write operation failed")

        debug = get_run_debug_context(db_session, project_dir, failed_run.id)

        assert debug.last_tool_call.tool_name == "write"
        assert debug.last_tool_result.full_payload["success"] is False
        assert "Permission denied" in debug.last_tool_result.full_payload.get("error", "")


# =============================================================================
# Data Class Tests
# =============================================================================

class TestReplayableEvent:
    """Tests for ReplayableEvent data class."""

    def test_from_event_small_payload(self, db_session, project_dir, test_run):
        """Test creating ReplayableEvent from event with small payload."""
        recorder = EventRecorder(db_session, project_dir)
        recorder.record(test_run.id, "started", payload={"msg": "hello"})

        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == test_run.id
        ).first()

        replayable = ReplayableEvent.from_event(event)

        assert replayable.was_truncated is False
        assert replayable.full_payload == {"msg": "hello"}
        assert replayable.artifact_ref is None

    def test_from_event_large_payload(self, db_session, project_dir, test_run):
        """Test creating ReplayableEvent from event with large payload."""
        recorder = EventRecorder(db_session, project_dir)
        recorder.record(test_run.id, "tool_result", payload={"data": "x" * 5000})

        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == test_run.id
        ).first()

        # Without full payload
        replayable_truncated = ReplayableEvent.from_event(event)
        assert replayable_truncated.was_truncated is True
        assert replayable_truncated.artifact_ref is not None

        # With full payload from artifact
        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events())
        assert events[0].full_payload["data"] == "x" * 5000

    def test_to_dict(self, db_session, project_dir, test_run):
        """Test ReplayableEvent serialization."""
        recorder = EventRecorder(db_session, project_dir)
        recorder.record_tool_call(test_run.id, "bash", {"cmd": "ls"})

        context = get_replay_context(db_session, project_dir, test_run.id)
        event = list(context.get_events())[0]

        event_dict = event.to_dict()

        assert "id" in event_dict
        assert "run_id" in event_dict
        assert "sequence" in event_dict
        assert "event_type" in event_dict
        assert "timestamp" in event_dict
        assert "payload" in event_dict
        assert "full_payload" in event_dict
        assert "was_truncated" in event_dict


class TestDebugContext:
    """Tests for DebugContext data class."""

    def test_to_dict(self, db_session, project_dir, failed_run):
        """Test DebugContext serialization."""
        recorder = EventRecorder(db_session, project_dir)
        recorder.record_started(failed_run.id, objective="Test")
        recorder.record_failed(failed_run.id, error="Test error")

        debug = get_run_debug_context(db_session, project_dir, failed_run.id)
        debug_dict = debug.to_dict()

        assert "run_id" in debug_dict
        assert "run_status" in debug_dict
        assert "failure_reason" in debug_dict
        assert "turns_used" in debug_dict
        assert "tokens_used" in debug_dict


class TestEventTimeline:
    """Tests for EventTimeline data class."""

    def test_to_dict(self, db_session, project_dir, run_with_events):
        """Test EventTimeline serialization."""
        context = get_replay_context(db_session, project_dir, run_with_events.id)
        timeline = context.get_timeline()

        timeline_dict = timeline.to_dict()

        assert "run_id" in timeline_dict
        assert "events" in timeline_dict
        assert "total_events" in timeline_dict
        assert "duration_seconds" in timeline_dict
        assert "tool_call_count" in timeline_dict


# =============================================================================
# API Package Exports Tests
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #227 components are exported from api package."""

    def test_replayable_event_exported(self):
        """Verify ReplayableEvent is exported."""
        from api import ReplayableEvent
        assert ReplayableEvent is not None

    def test_debug_context_exported(self):
        """Verify DebugContext is exported."""
        from api import DebugContext
        assert DebugContext is not None

    def test_event_timeline_exported(self):
        """Verify EventTimeline is exported."""
        from api import EventTimeline
        assert EventTimeline is not None

    def test_event_replay_context_exported(self):
        """Verify EventReplayContext is exported."""
        from api import EventReplayContext
        assert EventReplayContext is not None

    def test_get_replay_context_exported(self):
        """Verify get_replay_context is exported."""
        from api import get_replay_context
        assert callable(get_replay_context)

    def test_reconstruct_run_events_exported(self):
        """Verify reconstruct_run_events is exported."""
        from api import reconstruct_run_events
        assert callable(reconstruct_run_events)

    def test_get_run_debug_context_exported(self):
        """Verify get_run_debug_context is exported."""
        from api import get_run_debug_context
        assert callable(get_run_debug_context)

    def test_verify_event_sequence_integrity_exported(self):
        """Verify verify_event_sequence_integrity is exported."""
        from api import verify_event_sequence_integrity
        assert callable(verify_event_sequence_integrity)


# =============================================================================
# Feature #227 Verification Steps
# =============================================================================

class TestFeature227VerificationSteps:
    """Test all 4 verification steps from the feature specification."""

    def test_step1_events_include_full_context_for_replay(self, db_session, project_dir, test_run):
        """
        Step 1: Events include full context needed for replay.

        Verify that:
        - started events have objective
        - tool_call events have arguments
        - tool_result events have full result
        - failed events have error context
        """
        recorder = EventRecorder(db_session, project_dir)

        # Record comprehensive events
        recorder.record_started(test_run.id, objective="Implement feature X")
        recorder.record_tool_call(test_run.id, "bash", {"command": "echo test"})
        recorder.record_tool_result(test_run.id, "bash", {"output": "test"}, success=True)

        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events())

        # Verify started has objective
        started = next(e for e in events if e.event_type == "started")
        assert "objective" in started.full_payload

        # Verify tool_call has arguments
        tool_call = next(e for e in events if e.event_type == "tool_call")
        assert "arguments" in tool_call.full_payload
        assert tool_call.full_payload["arguments"]["command"] == "echo test"

        # Verify tool_result has result
        tool_result = next(e for e in events if e.event_type == "tool_result")
        assert "result" in tool_result.full_payload
        assert tool_result.full_payload["success"] is True

    def test_step2_large_payloads_stored_as_artifacts(self, db_session, project_dir, test_run):
        """
        Step 2: Large payloads stored as artifacts with references.

        Verify that:
        - Payloads exceeding limit create artifacts
        - artifact_ref points to full content
        - Full payload retrievable via replay context
        """
        recorder = EventRecorder(db_session, project_dir)

        # Create large payload
        large_content = "Large output content " * 500
        recorder.record_tool_result(
            test_run.id,
            "bash",
            result={"output": large_content},
            success=True,
        )

        # Verify artifact was created
        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == test_run.id
        ).first()

        assert event.payload_truncated is not None, "Payload should be truncated"
        assert event.artifact_ref is not None, "Should have artifact reference"

        # Verify full payload retrievable
        context = get_replay_context(db_session, project_dir, test_run.id)
        replayable = list(context.get_events())[0]

        assert replayable.was_truncated is True
        assert replayable.full_payload["result"]["output"] == large_content

    def test_step3_event_sequence_reconstructable(self, db_session, project_dir, test_run):
        """
        Step 3: Event sequence reconstructable from run_id + sequence.

        Verify that:
        - Events have sequential sequence numbers
        - Events queryable by run_id
        - Sequence starts at 1
        - Order preserved in reconstruction
        """
        recorder = EventRecorder(db_session, project_dir)

        # Record ordered events
        recorder.record(test_run.id, "started", payload={"step": 1})
        recorder.record(test_run.id, "tool_call", payload={"step": 2})
        recorder.record(test_run.id, "tool_result", payload={"step": 3})
        recorder.record(test_run.id, "completed", payload={"step": 4})

        # Reconstruct sequence
        events = reconstruct_run_events(db_session, project_dir, test_run.id)

        # Verify sequence
        assert len(events) == 4
        assert events[0]["sequence"] == 1
        assert events[1]["sequence"] == 2
        assert events[2]["sequence"] == 3
        assert events[3]["sequence"] == 4

        # Verify order preserved
        assert events[0]["event_type"] == "started"
        assert events[3]["event_type"] == "completed"

        # Verify integrity check passes
        integrity = verify_event_sequence_integrity(db_session, test_run.id)
        assert integrity["is_valid"] is True

    def test_step4_events_support_debugging_failures(self, db_session, project_dir, test_spec):
        """
        Step 4: Events support debugging failed agent runs.

        Verify that:
        - Debug context available for failed runs
        - Includes last events for diagnosis
        - Includes failure reason
        - Includes resource usage (turns, tokens)
        """
        # Create failed run
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=test_spec.id,
            status="failed",
            error="API rate limit exceeded",
            turns_used=10,
            tokens_in=5000,
            tokens_out=2000,
        )
        db_session.add(run)
        db_session.commit()

        # Record events leading to failure
        recorder = EventRecorder(db_session, project_dir)
        recorder.record_started(run.id, objective="Make API calls")
        recorder.record_tool_call(run.id, "http_request", {"url": "https://api.example.com"})
        recorder.record_tool_result(
            run.id, "http_request",
            result=None,
            success=False,
            error="Rate limit exceeded",
        )
        recorder.record_failed(run.id, error="API rate limit exceeded")

        # Get debug context
        debug = get_run_debug_context(db_session, project_dir, run.id)

        assert debug is not None

        # Verify failure reason
        assert debug.failure_reason is not None
        assert len(debug.failure_reason) > 0

        # Verify last events for diagnosis
        assert debug.last_tool_call is not None
        assert debug.last_tool_call.tool_name == "http_request"

        assert debug.last_tool_result is not None
        assert debug.last_tool_result.full_payload["success"] is False

        # Verify resource usage
        assert debug.turns_used == 10
        assert debug.tokens_used == 7000  # 5000 + 2000


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_run_no_events(self, db_session, project_dir, test_run):
        """Test replay context for run with no events."""
        context = get_replay_context(db_session, project_dir, test_run.id)
        events = list(context.get_events())

        assert len(events) == 0

        timeline = context.get_timeline()
        assert timeline.total_events == 0
        assert timeline.start_time is None

    def test_nonexistent_run(self, db_session, project_dir):
        """Test replay context for non-existent run."""
        context = get_replay_context(db_session, project_dir, "nonexistent-run-id")

        assert context.run is None
        events = list(context.get_events())
        assert len(events) == 0

    def test_filter_events_by_type(self, db_session, project_dir, run_with_events):
        """Test filtering events by type."""
        context = get_replay_context(db_session, project_dir, run_with_events.id)

        tool_calls = list(context.get_events(event_type="tool_call"))
        assert len(tool_calls) == 1

        tool_results = list(context.get_events(event_type="tool_result"))
        assert len(tool_results) == 1

    def test_sequence_integrity_with_gaps(self, db_session, project_dir, test_spec):
        """Test sequence integrity detection with gaps."""
        # Create run
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=test_spec.id,
            status="running",
        )
        db_session.add(run)
        db_session.commit()

        # Manually create events with gaps (bypassing recorder)
        event1 = AgentEvent(
            run_id=run.id,
            event_type="started",
            sequence=1,
            timestamp=datetime.now(timezone.utc),
        )
        event3 = AgentEvent(
            run_id=run.id,
            event_type="completed",
            sequence=3,  # Gap - missing sequence 2
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add_all([event1, event3])
        db_session.commit()

        # Verify integrity checker detects gap
        integrity = verify_event_sequence_integrity(db_session, run.id)

        assert integrity["is_valid"] is False
        assert 2 in integrity["gaps"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
