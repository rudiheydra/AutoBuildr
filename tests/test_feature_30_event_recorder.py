#!/usr/bin/env python3
"""
Test Suite for Feature #30: AgentEvent Recording Service
=========================================================

Tests the EventRecorder class and its methods for creating immutable
AgentEvent records with sequential ordering and payload size management.
"""

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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
from api.event_recorder import (
    EventRecorder,
    get_event_recorder,
    clear_recorder_cache,
)


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
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": []},
    )
    db_session.add(spec)
    db_session.commit()  # Commit to release lock
    return spec


@pytest.fixture
def test_run(db_session, test_spec):
    """Create a test AgentRun."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=test_spec.id,
        status="running",
    )
    db_session.add(run)
    db_session.commit()  # Commit to release lock
    return run


class TestEventRecorderClass:
    """Tests for EventRecorder class structure."""

    def test_class_exists(self):
        """Verify EventRecorder class exists."""
        from api.event_recorder import EventRecorder
        assert EventRecorder is not None

    def test_has_record_method(self):
        """Verify record(run_id, event_type, payload) method exists."""
        assert hasattr(EventRecorder, "record")

    def test_record_method_signature(self, db_session, project_dir):
        """Verify record method has correct signature."""
        import inspect
        recorder = EventRecorder(db_session, project_dir)
        sig = inspect.signature(recorder.record)
        params = list(sig.parameters.keys())
        assert "run_id" in params
        assert "event_type" in params
        assert "payload" in params


class TestSequenceCounter:
    """Tests for sequence counter per run."""

    def test_first_event_sequence_is_1(self, db_session, project_dir, test_run):
        """Verify first event in a run has sequence 1."""
        recorder = EventRecorder(db_session, project_dir)
        event_id = recorder.record(test_run.id, "started")

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == event_id
        ).first()
        assert event.sequence == 1

    def test_sequence_increments(self, db_session, project_dir, test_run):
        """Verify sequence increments for each event."""
        recorder = EventRecorder(db_session, project_dir)

        event_id1 = recorder.record(test_run.id, "started")
        event_id2 = recorder.record(test_run.id, "tool_call", payload={"tool": "test"})
        event_id3 = recorder.record(test_run.id, "turn_complete", payload={"turn": 1})

        event1 = db_session.query(AgentEvent).filter(AgentEvent.id == event_id1).first()
        event2 = db_session.query(AgentEvent).filter(AgentEvent.id == event_id2).first()
        event3 = db_session.query(AgentEvent).filter(AgentEvent.id == event_id3).first()

        assert event1.sequence == 1
        assert event2.sequence == 2
        assert event3.sequence == 3

    def test_independent_sequence_per_run(self, db_session, project_dir, test_spec):
        """Verify each run has independent sequence numbers."""
        # Create two runs
        run1 = AgentRun(id=generate_uuid(), agent_spec_id=test_spec.id, status="running")
        run2 = AgentRun(id=generate_uuid(), agent_spec_id=test_spec.id, status="running")
        db_session.add_all([run1, run2])
        db_session.flush()

        recorder = EventRecorder(db_session, project_dir)

        # Record events interleaved
        event1_run1 = recorder.record(run1.id, "started")
        event1_run2 = recorder.record(run2.id, "started")
        event2_run1 = recorder.record(run1.id, "tool_call", payload={"tool": "a"})
        event2_run2 = recorder.record(run2.id, "tool_call", payload={"tool": "b"})

        e1r1 = db_session.query(AgentEvent).filter(AgentEvent.id == event1_run1).first()
        e1r2 = db_session.query(AgentEvent).filter(AgentEvent.id == event1_run2).first()
        e2r1 = db_session.query(AgentEvent).filter(AgentEvent.id == event2_run1).first()
        e2r2 = db_session.query(AgentEvent).filter(AgentEvent.id == event2_run2).first()

        assert e1r1.sequence == 1
        assert e1r2.sequence == 1  # Independent sequence
        assert e2r1.sequence == 2
        assert e2r2.sequence == 2  # Independent sequence


class TestPayloadSizeLimit:
    """Tests for payload size checking."""

    def test_small_payload_stored_directly(self, db_session, project_dir, test_run):
        """Verify payloads under limit are stored directly."""
        recorder = EventRecorder(db_session, project_dir)

        small_payload = {"message": "Hello, world!"}
        event_id = recorder.record(test_run.id, "started", payload=small_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload == small_payload
        assert event.payload_truncated is None
        assert event.artifact_ref is None

    def test_large_payload_triggers_truncation(self, db_session, project_dir, test_run):
        """Verify payloads exceeding 4096 chars are truncated."""
        recorder = EventRecorder(db_session, project_dir)

        # Create payload larger than EVENT_PAYLOAD_MAX_SIZE (4096)
        large_payload = {"data": "x" * 5000}
        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload_truncated is not None
        assert event.payload_truncated > EVENT_PAYLOAD_MAX_SIZE

    def test_payload_truncated_field_has_original_size(self, db_session, project_dir, test_run):
        """Verify payload_truncated is set to original size."""
        recorder = EventRecorder(db_session, project_dir)

        large_data = "x" * 5000
        large_payload = {"data": large_data}
        original_size = len(json.dumps(large_payload))

        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload_truncated == original_size


class TestArtifactCreation:
    """Tests for artifact creation for large payloads."""

    def test_large_payload_creates_artifact(self, db_session, project_dir, test_run):
        """Verify large payloads create an artifact."""
        recorder = EventRecorder(db_session, project_dir)

        large_payload = {"data": "x" * 5000}
        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.artifact_ref is not None

        # Verify artifact exists
        artifact = db_session.query(Artifact).filter(
            Artifact.id == event.artifact_ref
        ).first()
        assert artifact is not None
        assert artifact.artifact_type == "log"

    def test_artifact_contains_full_payload(self, db_session, project_dir, test_run):
        """Verify artifact contains the full original payload."""
        recorder = EventRecorder(db_session, project_dir)

        large_payload = {"data": "x" * 5000, "key": "value"}
        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        artifact = db_session.query(Artifact).filter(
            Artifact.id == event.artifact_ref
        ).first()

        # Check file exists and contains full payload
        storage_path = project_dir / artifact.content_ref
        assert storage_path.exists()
        content = json.loads(storage_path.read_text())
        assert content == large_payload

    def test_truncated_payload_summary(self, db_session, project_dir, test_run):
        """Verify truncated payload contains summary with metadata."""
        recorder = EventRecorder(db_session, project_dir)

        large_payload = {"long_field": "x" * 5000, "short_field": "hello"}
        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload.get("_truncated") is True
        assert event.payload.get("_original_size") is not None
        assert event.payload.get("short_field") == "hello"
        assert "<truncated:" in event.payload.get("long_field", "")


class TestTimestamp:
    """Tests for timestamp handling."""

    def test_timestamp_set_to_utc(self, db_session, project_dir, test_run):
        """Verify timestamp is set to current UTC time."""
        recorder = EventRecorder(db_session, project_dir)

        before = datetime.now(timezone.utc)
        event_id = recorder.record(test_run.id, "started")
        after = datetime.now(timezone.utc)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.timestamp is not None
        # Timestamp should be between before and after
        assert before <= event.timestamp.replace(tzinfo=timezone.utc) <= after


class TestEventRecordCreation:
    """Tests for AgentEvent record creation."""

    def test_all_fields_populated(self, db_session, project_dir, test_run):
        """Verify all AgentEvent fields are correctly populated."""
        recorder = EventRecorder(db_session, project_dir)

        payload = {"message": "test"}
        event_id = recorder.record(
            test_run.id,
            "tool_call",
            payload=payload,
            tool_name="bash"
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        assert event.run_id == test_run.id
        assert event.event_type == "tool_call"
        assert event.sequence >= 1
        assert event.timestamp is not None
        assert event.payload == payload
        assert event.tool_name == "bash"

    def test_event_type_validation(self, db_session, project_dir, test_run):
        """Verify invalid event types are rejected."""
        recorder = EventRecorder(db_session, project_dir)

        with pytest.raises(ValueError) as exc_info:
            recorder.record(test_run.id, "invalid_type")

        assert "invalid_type" in str(exc_info.value)


class TestCommitBehavior:
    """Tests for immediate commit for durability."""

    def test_event_committed_immediately(self, test_db, test_spec):
        """Verify event is committed immediately after record()."""
        project_dir, SessionLocal = test_db

        # Create a fresh run in a new session that we fully control
        session1 = SessionLocal()
        try:
            run = AgentRun(id=generate_uuid(), agent_spec_id=test_spec.id, status="running")
            session1.add(run)
            session1.commit()  # Commit the run first
            run_id = run.id
        finally:
            session1.close()

        # Now record an event in a new session
        session2 = SessionLocal()
        try:
            recorder = EventRecorder(session2, project_dir)
            event_id = recorder.record(run_id, "started")
        finally:
            session2.close()

        # Create a third session to verify persistence
        session3 = SessionLocal()
        try:
            event = session3.query(AgentEvent).filter(
                AgentEvent.id == event_id
            ).first()
            assert event is not None, "Event should be committed to database"
        finally:
            session3.close()


class TestReturnValue:
    """Tests for return value (event ID)."""

    def test_returns_event_id(self, db_session, project_dir, test_run):
        """Verify record() returns the event ID."""
        recorder = EventRecorder(db_session, project_dir)

        result = recorder.record(test_run.id, "started")

        assert isinstance(result, int)
        assert result > 0

    def test_returned_id_can_retrieve_event(self, db_session, project_dir, test_run):
        """Verify returned ID can be used to retrieve the event."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record(test_run.id, "started", payload={"test": True})

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.event_type == "started"


class TestConvenienceMethods:
    """Tests for convenience methods."""

    def test_record_started(self, db_session, project_dir, test_run):
        """Test record_started convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_started(
            test_run.id,
            objective="Test objective",
            spec_id="spec-123"
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "started"
        assert event.payload.get("objective") == "Test objective"
        assert event.payload.get("spec_id") == "spec-123"

    def test_record_tool_call(self, db_session, project_dir, test_run):
        """Test record_tool_call convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_tool_call(
            test_run.id,
            tool_name="bash",
            arguments={"command": "ls -la"}
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "tool_call"
        assert event.tool_name == "bash"
        assert event.payload.get("tool") == "bash"
        assert event.payload.get("arguments", {}).get("command") == "ls -la"

    def test_record_tool_result(self, db_session, project_dir, test_run):
        """Test record_tool_result convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_tool_result(
            test_run.id,
            tool_name="bash",
            result={"output": "file1 file2"},
            success=True
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "tool_result"
        assert event.payload.get("success") is True
        assert event.payload.get("result", {}).get("output") == "file1 file2"

    def test_record_turn_complete(self, db_session, project_dir, test_run):
        """Test record_turn_complete convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_turn_complete(
            test_run.id,
            turn_number=5,
            tokens_in=100,
            tokens_out=50
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "turn_complete"
        assert event.payload.get("turn") == 5
        assert event.payload.get("tokens_in") == 100
        assert event.payload.get("tokens_out") == 50

    def test_record_acceptance_check(self, db_session, project_dir, test_run):
        """Test record_acceptance_check convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        validators = [
            {"index": 0, "type": "file_exists", "passed": True},
            {"index": 1, "type": "test_pass", "passed": False}
        ]
        event_id = recorder.record_acceptance_check(
            test_run.id,
            validators=validators,
            verdict="failed",
            gate_mode="all_pass"
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "acceptance_check"
        assert event.payload.get("verdict") == "failed"
        assert len(event.payload.get("validators", [])) == 2

    def test_record_completed(self, db_session, project_dir, test_run):
        """Test record_completed convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_completed(
            test_run.id,
            verdict="passed",
            turns_used=10,
            tokens_in=1000,
            tokens_out=500
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "completed"
        assert event.payload.get("verdict") == "passed"
        assert event.payload.get("turns_used") == 10

    def test_record_failed(self, db_session, project_dir, test_run):
        """Test record_failed convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_failed(
            test_run.id,
            error="Something went wrong",
            error_type="RuntimeError"
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "failed"
        assert event.payload.get("error") == "Something went wrong"
        assert event.payload.get("error_type") == "RuntimeError"

    def test_record_paused(self, db_session, project_dir, test_run):
        """Test record_paused convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_paused(
            test_run.id,
            reason="User requested",
            turns_used=5
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "paused"
        assert event.payload.get("reason") == "User requested"

    def test_record_resumed(self, db_session, project_dir, test_run):
        """Test record_resumed convenience method."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record_resumed(
            test_run.id,
            previous_status="paused",
            turns_used=5
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.event_type == "resumed"
        assert event.payload.get("previous_status") == "paused"


class TestGlobalRecorderCache:
    """Tests for get_event_recorder and cache management."""

    def test_get_event_recorder_returns_instance(self, db_session, project_dir):
        """Verify get_event_recorder returns an EventRecorder."""
        clear_recorder_cache()
        recorder = get_event_recorder(db_session, project_dir)
        assert isinstance(recorder, EventRecorder)

    def test_get_event_recorder_caches_instance(self, db_session, project_dir):
        """Verify get_event_recorder returns same instance for same session."""
        clear_recorder_cache()
        recorder1 = get_event_recorder(db_session, project_dir)
        recorder2 = get_event_recorder(db_session, project_dir)
        assert recorder1 is recorder2

    def test_clear_recorder_cache(self, db_session, project_dir):
        """Verify clear_recorder_cache clears the cache."""
        recorder1 = get_event_recorder(db_session, project_dir)
        clear_recorder_cache()
        recorder2 = get_event_recorder(db_session, project_dir)
        assert recorder1 is not recorder2


class TestSequenceCacheManagement:
    """Tests for sequence cache management."""

    def test_clear_sequence_cache_for_run(self, db_session, project_dir, test_run):
        """Verify clear_sequence_cache clears cache for specific run."""
        recorder = EventRecorder(db_session, project_dir)

        # Record event to populate cache
        recorder.record(test_run.id, "started")
        assert test_run.id in recorder._sequence_cache

        # Clear specific run
        recorder.clear_sequence_cache(test_run.id)
        assert test_run.id not in recorder._sequence_cache

    def test_clear_sequence_cache_all(self, db_session, project_dir, test_spec):
        """Verify clear_sequence_cache(None) clears all cache."""
        run1 = AgentRun(id=generate_uuid(), agent_spec_id=test_spec.id, status="running")
        run2 = AgentRun(id=generate_uuid(), agent_spec_id=test_spec.id, status="running")
        db_session.add_all([run1, run2])
        db_session.flush()

        recorder = EventRecorder(db_session, project_dir)

        # Record events to populate cache
        recorder.record(run1.id, "started")
        recorder.record(run2.id, "started")
        assert len(recorder._sequence_cache) == 2

        # Clear all
        recorder.clear_sequence_cache()
        assert len(recorder._sequence_cache) == 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_payload(self, db_session, project_dir, test_run):
        """Test recording event with empty payload."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record(test_run.id, "started", payload={})

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload == {}

    def test_none_payload(self, db_session, project_dir, test_run):
        """Test recording event with None payload."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record(test_run.id, "started", payload=None)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload is None

    def test_no_project_dir_large_payload(self, db_session, test_run):
        """Test large payload without project_dir logs warning but doesn't fail."""
        recorder = EventRecorder(db_session, project_dir=None)

        large_payload = {"data": "x" * 5000}
        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload_truncated is not None
        assert event.artifact_ref is None  # No artifact without project_dir


class TestFeatureVerificationSteps:
    """Test all 9 verification steps from the feature specification."""

    def test_step1_eventrecorder_class_with_record_method(self, db_session, project_dir):
        """Step 1: Create EventRecorder class with record(run_id, event_type, payload) method."""
        recorder = EventRecorder(db_session, project_dir)
        assert hasattr(recorder, "record")
        assert callable(recorder.record)

    def test_step2_sequence_counter_starts_at_1(self, db_session, project_dir, test_run):
        """Step 2: Maintain sequence counter per run (start at 1)."""
        recorder = EventRecorder(db_session, project_dir)
        event_id = recorder.record(test_run.id, "started")

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.sequence == 1

    def test_step3_check_payload_size_limit(self, db_session, project_dir, test_run):
        """Step 3: Check payload size against EVENT_PAYLOAD_MAX_SIZE (4096 chars)."""
        assert EVENT_PAYLOAD_MAX_SIZE == 4096

        recorder = EventRecorder(db_session, project_dir)

        # Small payload - no truncation
        small_payload = {"msg": "a" * 100}
        event_id1 = recorder.record(test_run.id, "started", payload=small_payload)
        event1 = db_session.query(AgentEvent).filter(AgentEvent.id == event_id1).first()
        assert event1.payload_truncated is None

        # Large payload - truncation
        large_payload = {"msg": "b" * 5000}
        event_id2 = recorder.record(test_run.id, "tool_call", payload=large_payload)
        event2 = db_session.query(AgentEvent).filter(AgentEvent.id == event_id2).first()
        assert event2.payload_truncated is not None

    def test_step4_large_payload_creates_artifact(self, db_session, project_dir, test_run):
        """Step 4: If payload exceeds limit, create Artifact and set artifact_ref."""
        recorder = EventRecorder(db_session, project_dir)

        large_payload = {"data": "x" * 5000}
        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.artifact_ref is not None

        artifact = db_session.query(Artifact).filter(
            Artifact.id == event.artifact_ref
        ).first()
        assert artifact is not None

    def test_step5_truncate_payload_set_original_size(self, db_session, project_dir, test_run):
        """Step 5: Truncate payload and set payload_truncated to original size."""
        recorder = EventRecorder(db_session, project_dir)

        large_data = "x" * 5000
        large_payload = {"data": large_data}
        original_size = len(json.dumps(large_payload))

        event_id = recorder.record(test_run.id, "tool_result", payload=large_payload)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload_truncated == original_size
        assert event.payload.get("_truncated") is True

    def test_step6_timestamp_set_to_utc(self, db_session, project_dir, test_run):
        """Step 6: Set timestamp to current UTC time."""
        recorder = EventRecorder(db_session, project_dir)

        before = datetime.now(timezone.utc)
        event_id = recorder.record(test_run.id, "started")
        after = datetime.now(timezone.utc)

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        ts = event.timestamp.replace(tzinfo=timezone.utc)
        assert before <= ts <= after

    def test_step7_create_agentevent_with_all_fields(self, db_session, project_dir, test_run):
        """Step 7: Create AgentEvent record with all fields."""
        recorder = EventRecorder(db_session, project_dir)

        event_id = recorder.record(
            test_run.id,
            "tool_call",
            payload={"args": "test"},
            tool_name="bash"
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # Check all fields are set
        assert event.id is not None
        assert event.run_id == test_run.id
        assert event.event_type == "tool_call"
        assert event.sequence >= 1
        assert event.timestamp is not None
        assert event.payload is not None
        assert event.tool_name == "bash"

    def test_step8_commit_immediately(self, test_db, test_spec):
        """Step 8: Commit immediately for durability."""
        project_dir, SessionLocal = test_db

        # Create a fresh run in a new session that we fully control
        session1 = SessionLocal()
        try:
            run = AgentRun(id=generate_uuid(), agent_spec_id=test_spec.id, status="running")
            session1.add(run)
            session1.commit()  # Commit the run first
            run_id = run.id
        finally:
            session1.close()

        # Now record an event in a new session
        session2 = SessionLocal()
        try:
            recorder = EventRecorder(session2, project_dir)
            event_id = recorder.record(run_id, "started")
        finally:
            session2.close()

        # Create a fresh session to verify persistence
        fresh_session = SessionLocal()
        try:
            event = fresh_session.query(AgentEvent).filter(
                AgentEvent.id == event_id
            ).first()
            assert event is not None, "Event should be committed to database"
        finally:
            fresh_session.close()

    def test_step9_return_event_id(self, db_session, project_dir, test_run):
        """Step 9: Return created event ID."""
        recorder = EventRecorder(db_session, project_dir)

        result = recorder.record(test_run.id, "started")

        assert isinstance(result, int), "Should return integer event ID"
        assert result > 0, "Event ID should be positive"

        # Verify we can use it to retrieve the event
        event = db_session.query(AgentEvent).filter(AgentEvent.id == result).first()
        assert event is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
