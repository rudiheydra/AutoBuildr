"""
Tests for Feature #222: agent_materialized audit event type created

Feature Description:
New event type recorded when Materializer writes an agent file.

Verification Steps:
1. Add 'agent_materialized' to event_type enum
2. Event payload includes: agent_name, file_path, spec_hash
3. Event recorded after successful file write
4. Event linked to AgentSpec
5. Event queryable via existing event APIs
"""
import hashlib
import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.agent_materializer import (
    AgentMaterializer,
    MaterializationResult,
    MaterializationAuditInfo,
    BatchMaterializationResult,
)
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    EVENT_TYPES,
    generate_uuid,
)
from api.database import Base
from api.event_recorder import EventRecorder, get_event_recorder, clear_recorder_cache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Clear recorder cache to ensure fresh state
    clear_recorder_cache()

    yield session

    session.close()
    clear_recorder_cache()


@pytest.fixture
def materializer(temp_project_dir):
    """AgentMaterializer instance with temp directory."""
    return AgentMaterializer(temp_project_dir)


@pytest.fixture
def sample_agent_spec():
    """Sample AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="feature-222-test-agent",
        display_name="Test Agent for Feature 222",
        icon="test",
        spec_version="v1",
        objective="Test agent_materialized event type",
        task_type="testing",
        context={"test": True, "model": "sonnet"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Grep"],
            "forbidden_patterns": [],
            "tool_hints": {},
        },
        max_turns=50,
        timeout_seconds=900,
        source_feature_id=222,
        priority=1,
        tags=["feature-222", "testing"],
    )


@pytest.fixture
def sample_agent_run(db_session, sample_agent_spec):
    """Sample AgentRun for linking events."""
    # Create spec first
    db_session.add(sample_agent_spec)
    db_session.flush()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_agent_spec.id,
        status="running",
    )
    db_session.add(run)
    db_session.commit()

    return run


# =============================================================================
# Step 1: Add 'agent_materialized' to event_type enum
# =============================================================================

class TestStep1EventTypeEnum:
    """Verify 'agent_materialized' is in the event_type enum."""

    def test_agent_materialized_in_event_types_list(self):
        """agent_materialized is defined in EVENT_TYPES list."""
        assert "agent_materialized" in EVENT_TYPES

    def test_agent_materialized_position_in_list(self):
        """agent_materialized is at correct position in EVENT_TYPES."""
        # Should be in the list alongside other event types
        idx = EVENT_TYPES.index("agent_materialized")
        assert idx >= 0
        # Verify it's in the expected range (after standard events, with feature events)
        assert idx > EVENT_TYPES.index("started")

    def test_event_recorder_validates_event_type(self, db_session, temp_project_dir, sample_agent_run):
        """EventRecorder accepts agent_materialized without raising ValueError."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        # Should not raise ValueError for invalid event_type
        event_id = recorder.record(
            run_id=sample_agent_run.id,
            event_type="agent_materialized",
            payload={"test": True},
        )

        assert event_id is not None
        assert isinstance(event_id, int)

    def test_event_recorder_rejects_invalid_type(self, db_session, temp_project_dir, sample_agent_run):
        """EventRecorder raises ValueError for invalid event types."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        with pytest.raises(ValueError) as excinfo:
            recorder.record(
                run_id=sample_agent_run.id,
                event_type="invalid_event_type_xyz",
                payload={},
            )

        assert "Invalid event_type" in str(excinfo.value)

    def test_event_recorder_has_convenience_method(self):
        """EventRecorder has record_agent_materialized convenience method."""
        assert hasattr(EventRecorder, "record_agent_materialized")
        assert callable(getattr(EventRecorder, "record_agent_materialized"))


# =============================================================================
# Step 2: Event payload includes agent_name, file_path, spec_hash
# =============================================================================

class TestStep2EventPayload:
    """Verify event payload includes required fields."""

    def test_payload_includes_agent_name(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes agent_name field."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="my-test-agent",
            file_path="/path/to/agent.md",
            spec_hash="abc123def456",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert "agent_name" in event.payload
        assert event.payload["agent_name"] == "my-test-agent"

    def test_payload_includes_file_path(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes file_path field."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/project/.claude/agents/generated/my-agent.md",
            spec_hash="xyz789",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert "file_path" in event.payload
        assert event.payload["file_path"] == "/project/.claude/agents/generated/my-agent.md"

    def test_payload_includes_spec_hash(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes spec_hash field."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        # Create a realistic SHA256 hash
        content_hash = hashlib.sha256(b"test content").hexdigest()

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash=content_hash,
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert "spec_hash" in event.payload
        assert event.payload["spec_hash"] == content_hash
        assert len(event.payload["spec_hash"]) == 64  # SHA256 hex length

    def test_payload_includes_all_required_fields(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes all required fields: agent_name, file_path, spec_hash."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="complete-test-agent",
            file_path="/full/path/to/agent.md",
            spec_hash="a" * 64,
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # All three required fields must be present
        required_fields = ["agent_name", "file_path", "spec_hash"]
        for field in required_fields:
            assert field in event.payload, f"Missing required field: {field}"

    def test_payload_includes_optional_spec_id(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload can include optional spec_id."""
        recorder = get_event_recorder(db_session, temp_project_dir)
        spec_id = generate_uuid()

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
            spec_id=spec_id,
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload.get("spec_id") == spec_id

    def test_payload_includes_optional_display_name(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload can include optional display_name."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
            display_name="My Test Agent",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload.get("display_name") == "My Test Agent"

    def test_payload_includes_optional_task_type(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload can include optional task_type."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
            task_type="coding",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload.get("task_type") == "coding"


# =============================================================================
# Step 3: Event recorded after successful file write
# =============================================================================

class TestStep3EventAfterFileWrite:
    """Verify event is recorded after successful file write."""

    def test_materialize_with_audit_records_event(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """materialize_with_audit records agent_materialized event."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Materialization should succeed
        assert result.success
        assert result.file_path.exists()

        # Audit event should be recorded
        assert result.audit_info is not None
        assert result.audit_info.recorded
        assert result.audit_info.event_id is not None

    def test_event_recorded_after_file_write(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event is recorded AFTER the file has been written."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # File should exist
        assert result.file_path.exists()

        # Event should reference the actual file path
        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert str(result.file_path) == event.payload["file_path"]

    def test_event_spec_hash_matches_file_content(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event spec_hash matches the actual file content hash."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Compute hash of actual file content
        file_content = result.file_path.read_text(encoding="utf-8")
        actual_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()

        # Get event and verify hash matches
        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.payload["spec_hash"] == actual_hash
        assert event.payload["spec_hash"] == result.content_hash

    def test_failed_materialization_no_event(
        self, db_session, temp_project_dir, sample_agent_run
    ):
        """Failed materialization does not record an event."""
        # Create spec with invalid data
        spec = AgentSpec(
            id=generate_uuid(),
            name="test-spec",
            display_name="Test Spec",
            task_type="testing",
            objective="Test",
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=900,
        )

        materializer = AgentMaterializer(temp_project_dir)

        # Mock materialize to fail
        with patch.object(materializer, 'materialize', return_value=MaterializationResult(
            spec_id=spec.id,
            spec_name=spec.name,
            success=False,
            error="Mock failure",
        )):
            result = materializer.materialize_with_audit(
                spec=spec,
                session=db_session,
                run_id=sample_agent_run.id,
            )

        # Materialization failed
        assert not result.success

        # No audit event recorded
        assert result.audit_info is None

    def test_event_has_timestamp(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Recorded event has a timestamp."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)


# =============================================================================
# Step 4: Event linked to AgentSpec
# =============================================================================

class TestStep4EventLinkedToSpec:
    """Verify event is linked to AgentSpec."""

    def test_event_contains_spec_id(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event payload contains spec_id linking to AgentSpec."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert "spec_id" in event.payload
        assert event.payload["spec_id"] == sample_agent_spec.id

    def test_can_query_spec_from_event(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Can query the AgentSpec from event payload."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Query spec using spec_id from event payload
        spec_id_from_event = event.payload["spec_id"]
        spec = db_session.query(AgentSpec).filter(AgentSpec.id == spec_id_from_event).first()

        assert spec is not None
        assert spec.id == sample_agent_spec.id
        assert spec.name == sample_agent_spec.name

    def test_event_agent_name_matches_spec_name(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event agent_name matches AgentSpec.name."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.payload["agent_name"] == sample_agent_spec.name

    def test_event_display_name_matches_spec(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event display_name matches AgentSpec.display_name."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.payload.get("display_name") == sample_agent_spec.display_name

    def test_event_task_type_matches_spec(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event task_type matches AgentSpec.task_type."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.payload.get("task_type") == sample_agent_spec.task_type


# =============================================================================
# Step 5: Event queryable via existing event APIs
# =============================================================================

class TestStep5EventQueryable:
    """Verify event is queryable via existing event APIs."""

    def test_event_queryable_by_run_id(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event can be queried by run_id."""
        materializer = AgentMaterializer(temp_project_dir)

        materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Query events for this run
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id
        ).all()

        # Should have at least one event
        assert len(events) >= 1

        # One should be agent_materialized
        materialized_events = [e for e in events if e.event_type == "agent_materialized"]
        assert len(materialized_events) >= 1

    def test_event_queryable_by_event_type(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event can be filtered by event_type='agent_materialized'."""
        materializer = AgentMaterializer(temp_project_dir)

        materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Query specifically for agent_materialized events
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).all()

        assert len(events) >= 1
        assert all(e.event_type == "agent_materialized" for e in events)

    def test_event_has_sequence_number(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event has a sequence number for ordering."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.sequence >= 1

    def test_events_ordered_by_sequence(
        self, db_session, temp_project_dir, sample_agent_run
    ):
        """Multiple events can be ordered by sequence."""
        # Create multiple specs
        specs = []
        for i in range(3):
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"queryable-spec-{i}",
                display_name=f"Queryable Spec {i}",
                task_type="testing",
                objective=f"Test queryability {i}",
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=900,
            )
            db_session.add(spec)
            specs.append(spec)
        db_session.commit()

        # Update run's spec_id
        sample_agent_run.agent_spec_id = specs[0].id
        db_session.commit()

        materializer = AgentMaterializer(temp_project_dir)

        # Materialize all specs
        for spec in specs:
            materializer.materialize_with_audit(
                spec=spec,
                session=db_session,
                run_id=sample_agent_run.id,
            )

        # Query events ordered by sequence
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).order_by(AgentEvent.sequence).all()

        # Events should be in sequence order
        sequences = [e.sequence for e in events]
        assert sequences == sorted(sequences)

    def test_event_in_agent_events_table(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event is persisted to agent_events table."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Verify it's in the correct table
        assert event is not None
        assert event.__tablename__ == "agent_events"

    def test_event_payload_is_json_serializable(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event payload is JSON serializable for API response."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Payload should be serializable to JSON
        json_str = json.dumps(event.payload)
        assert isinstance(json_str, str)

        # Should deserialize back to same data
        parsed = json.loads(json_str)
        assert parsed == event.payload


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for Feature #222."""

    def test_full_flow_materialize_and_query(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Full flow: materialize agent and query the event."""
        materializer = AgentMaterializer(temp_project_dir)

        # Step 1: Materialize with audit
        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Verify materialization succeeded
        assert result.success
        assert result.file_path.exists()
        assert result.content_hash is not None

        # Step 2: Query the event
        event = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).first()

        # Verify event exists with all required fields
        assert event is not None
        assert event.payload["agent_name"] == sample_agent_spec.name
        assert event.payload["file_path"] == str(result.file_path)
        assert event.payload["spec_hash"] == result.content_hash
        assert event.payload["spec_id"] == sample_agent_spec.id

    def test_batch_materialization_creates_multiple_events(
        self, db_session, temp_project_dir, sample_agent_run
    ):
        """Batch materialization creates events for each spec."""
        specs = []
        for i in range(3):
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"batch-spec-{i}",
                display_name=f"Batch Spec {i}",
                task_type="testing",
                objective=f"Test batch {i}",
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=900,
            )
            db_session.add(spec)
            specs.append(spec)
        db_session.commit()

        # Update run spec_id
        sample_agent_run.agent_spec_id = specs[0].id
        db_session.commit()

        materializer = AgentMaterializer(temp_project_dir)

        # Batch materialize
        batch_result = materializer.materialize_batch_with_audit(
            specs=specs,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        assert batch_result.total == 3
        assert batch_result.succeeded == 3

        # Query all materialized events
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).all()

        # Should have 3 events (one per spec)
        assert len(events) == 3

        # Each event should reference a different spec
        spec_ids = {e.payload["spec_id"] for e in events}
        expected_ids = {s.id for s in specs}
        assert spec_ids == expected_ids


# =============================================================================
# Feature Verification Steps Summary
# =============================================================================

class TestFeature222VerificationSteps:
    """
    Comprehensive tests for all 5 verification steps of Feature #222.

    These tests serve as the final verification that all requirements are met.
    """

    def test_step1_event_type_in_enum(self):
        """Step 1: Add 'agent_materialized' to event_type enum."""
        # Must be in EVENT_TYPES list
        assert "agent_materialized" in EVENT_TYPES

        # EventRecorder must accept this event type
        assert hasattr(EventRecorder, "record_agent_materialized")

    def test_step2_payload_includes_required_fields(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 2: Event payload includes: agent_name, file_path, spec_hash."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # All three required payload fields must be present
        assert "agent_name" in event.payload
        assert "file_path" in event.payload
        assert "spec_hash" in event.payload

    def test_step3_event_recorded_after_file_write(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 3: Event recorded after successful file write."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # File exists
        assert result.file_path.exists()

        # Event was recorded
        assert result.audit_info.recorded
        assert result.audit_info.event_id is not None

    def test_step4_event_linked_to_agentspec(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 4: Event linked to AgentSpec."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Event links to AgentSpec via spec_id in payload
        assert "spec_id" in event.payload
        assert event.payload["spec_id"] == sample_agent_spec.id

        # Can retrieve AgentSpec from event
        spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == event.payload["spec_id"]
        ).first()
        assert spec is not None
        assert spec.name == sample_agent_spec.name

    def test_step5_event_queryable_via_apis(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 5: Event queryable via existing event APIs."""
        materializer = AgentMaterializer(temp_project_dir)

        materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Query by run_id
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id
        ).all()
        assert len(events) >= 1

        # Filter by event_type
        materialized_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).all()
        assert len(materialized_events) >= 1

        # Order by sequence
        ordered_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
        ).order_by(AgentEvent.sequence).all()
        assert all(e.sequence > 0 for e in ordered_events)


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #222 components are properly exported."""

    def test_event_types_exported(self):
        """EVENT_TYPES is exported from api.agentspec_models."""
        from api.agentspec_models import EVENT_TYPES
        assert "agent_materialized" in EVENT_TYPES

    def test_event_recorder_exported(self):
        """EventRecorder with record_agent_materialized is exported."""
        from api.event_recorder import EventRecorder
        assert hasattr(EventRecorder, "record_agent_materialized")

    def test_agent_materializer_has_audit_method(self):
        """AgentMaterializer has materialize_with_audit method."""
        from api.agent_materializer import AgentMaterializer
        assert hasattr(AgentMaterializer, "materialize_with_audit")

    def test_materialization_audit_info_exported(self):
        """MaterializationAuditInfo is exported."""
        from api.agent_materializer import MaterializationAuditInfo
        info = MaterializationAuditInfo()
        assert hasattr(info, "event_id")
        assert hasattr(info, "recorded")
