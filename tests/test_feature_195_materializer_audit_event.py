"""
Tests for Feature #195: Agent Materializer records agent_materialized audit event

The Agent Materializer records an audit event after successfully writing an agent file.

Verification Steps:
1. Create agent_materialized event type
2. Event includes: agent_name, file_path, spec_hash, timestamp
3. Event linked to AgentSpec in database
4. Event persisted to agent_events table
"""
import hashlib
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
        name="feature-195-test-agent",
        display_name="Test Agent for Feature 195",
        icon="test",
        spec_version="v1",
        objective="Test materialization audit event recording",
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
        source_feature_id=195,
        priority=1,
        tags=["feature-195", "testing"],
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
# Step 1: Create agent_materialized event type
# =============================================================================

class TestStep1AgentMaterializedEventType:
    """Verify agent_materialized event type is defined."""

    def test_agent_materialized_in_event_types(self):
        """agent_materialized is a valid event type."""
        assert "agent_materialized" in EVENT_TYPES

    def test_event_recorder_accepts_agent_materialized(self, db_session, temp_project_dir, sample_agent_run):
        """EventRecorder accepts agent_materialized as a valid event type."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        # Should not raise
        event_id = recorder.record(
            run_id=sample_agent_run.id,
            event_type="agent_materialized",
            payload={"agent_name": "test", "file_path": "/test/path", "spec_hash": "abc123"},
        )

        assert event_id is not None
        assert isinstance(event_id, int)

    def test_event_recorder_has_convenience_method(self):
        """EventRecorder has record_agent_materialized convenience method."""
        assert hasattr(EventRecorder, "record_agent_materialized")


# =============================================================================
# Step 2: Event includes agent_name, file_path, spec_hash, timestamp
# =============================================================================

class TestStep2EventPayloadFields:
    """Verify event includes required payload fields."""

    def test_event_includes_agent_name(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes agent_name."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["agent_name"] == "test-agent"

    def test_event_includes_file_path(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes file_path."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/path/to/agent.md",
            spec_hash="def456",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["file_path"] == "/path/to/agent.md"

    def test_event_includes_spec_hash(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes spec_hash."""
        recorder = get_event_recorder(db_session, temp_project_dir)
        content_hash = "a" * 64  # SHA256 hex length

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash=content_hash,
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["spec_hash"] == content_hash

    def test_event_has_timestamp(self, db_session, temp_project_dir, sample_agent_run):
        """Event has timestamp field."""
        recorder = get_event_recorder(db_session, temp_project_dir)
        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.timestamp is not None
        # Timestamp should be a valid datetime
        assert isinstance(event.timestamp, datetime)

    def test_event_includes_optional_spec_id(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes optional spec_id."""
        spec_id = generate_uuid()
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
            spec_id=spec_id,
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["spec_id"] == spec_id

    def test_event_includes_optional_display_name(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes optional display_name."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
            display_name="Human Readable Name",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["display_name"] == "Human Readable Name"

    def test_event_includes_optional_task_type(self, db_session, temp_project_dir, sample_agent_run):
        """Event payload includes optional task_type."""
        recorder = get_event_recorder(db_session, temp_project_dir)

        event_id = recorder.record_agent_materialized(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            file_path="/test/path.md",
            spec_hash="abc123",
            task_type="coding",
        )

        event = db_session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["task_type"] == "coding"


# =============================================================================
# Step 3: Event linked to AgentSpec in database
# =============================================================================

class TestStep3EventLinkedToAgentSpec:
    """Verify event is linked to AgentSpec via spec_id in payload."""

    def test_materialize_with_audit_links_to_spec(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """materialize_with_audit creates event with spec_id in payload."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        assert result.success
        assert result.audit_info is not None
        assert result.audit_info.recorded

        # Verify event payload contains spec_id
        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()
        assert event.payload["spec_id"] == sample_agent_spec.id

    def test_event_spec_id_matches_agentspec_id(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event spec_id in payload matches the AgentSpec.id."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Look up spec by ID in payload
        spec_id_from_event = event.payload["spec_id"]
        spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == spec_id_from_event
        ).first()

        assert spec is not None
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


# =============================================================================
# Step 4: Event persisted to agent_events table
# =============================================================================

class TestStep4EventPersistedToTable:
    """Verify event is persisted to agent_events table."""

    def test_event_persisted_on_materialize_with_audit(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """materialize_with_audit persists event to database."""
        materializer = AgentMaterializer(temp_project_dir)

        # Count events before
        count_before = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id
        ).count()

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Count events after
        count_after = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id
        ).count()

        assert count_after == count_before + 1
        assert result.audit_info.recorded

    def test_event_has_correct_event_type(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Persisted event has event_type='agent_materialized'."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.event_type == "agent_materialized"

    def test_event_linked_to_run(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Persisted event is linked to correct AgentRun."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.run_id == sample_agent_run.id

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
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).all()

        assert len(events) >= 1

    def test_event_has_sequence_number(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Event has a sequence number."""
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


# =============================================================================
# MaterializationAuditInfo Tests
# =============================================================================

class TestMaterializationAuditInfo:
    """Test MaterializationAuditInfo dataclass."""

    def test_audit_info_creation(self):
        """MaterializationAuditInfo can be created."""
        audit_info = MaterializationAuditInfo(
            event_id=42,
            run_id="run-123",
            timestamp=datetime.now(timezone.utc),
            recorded=True,
        )

        assert audit_info.event_id == 42
        assert audit_info.run_id == "run-123"
        assert audit_info.recorded

    def test_audit_info_defaults(self):
        """MaterializationAuditInfo has sensible defaults."""
        audit_info = MaterializationAuditInfo()

        assert audit_info.event_id is None
        assert audit_info.run_id is None
        assert audit_info.timestamp is None
        assert audit_info.recorded is False
        assert audit_info.error is None

    def test_audit_info_to_dict(self):
        """MaterializationAuditInfo converts to dict."""
        ts = datetime.now(timezone.utc)
        audit_info = MaterializationAuditInfo(
            event_id=42,
            run_id="run-123",
            timestamp=ts,
            recorded=True,
        )

        d = audit_info.to_dict()

        assert d["event_id"] == 42
        assert d["run_id"] == "run-123"
        assert d["timestamp"] == ts.isoformat()
        assert d["recorded"] is True
        assert d["error"] is None

    def test_audit_info_with_error(self):
        """MaterializationAuditInfo can store error message."""
        audit_info = MaterializationAuditInfo(
            recorded=False,
            error="Database connection failed",
        )

        assert not audit_info.recorded
        assert audit_info.error == "Database connection failed"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for Feature #195."""

    def test_full_materialization_with_audit_flow(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Full flow: materialize spec and record audit event."""
        materializer = AgentMaterializer(temp_project_dir)

        # Materialize with audit
        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Verify result
        assert result.success
        assert result.file_path.exists()
        assert result.content_hash is not None

        # Verify audit info
        assert result.audit_info is not None
        assert result.audit_info.recorded
        assert result.audit_info.event_id is not None
        assert result.audit_info.run_id == sample_agent_run.id

        # Verify event in database
        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.event_type == "agent_materialized"
        assert event.payload["agent_name"] == sample_agent_spec.name
        assert event.payload["file_path"] == str(result.file_path)
        assert event.payload["spec_hash"] == result.content_hash
        assert event.payload["spec_id"] == sample_agent_spec.id

    def test_batch_materialization_with_audit(self, db_session, temp_project_dir, sample_agent_run):
        """Batch materialization creates audit events for each spec."""
        # Create multiple specs
        specs = []
        for i in range(3):
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"batch-test-spec-{i}",
                display_name=f"Batch Test Spec {i}",
                task_type="testing",
                objective=f"Test batch materialization {i}",
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=900,
            )
            db_session.add(spec)
            specs.append(spec)
        db_session.commit()

        # Update run's spec_id to first spec
        sample_agent_run.agent_spec_id = specs[0].id
        db_session.commit()

        materializer = AgentMaterializer(temp_project_dir)

        # Batch materialize with audit
        batch_result = materializer.materialize_batch_with_audit(
            specs=specs,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        assert batch_result.total == 3
        assert batch_result.succeeded == 3

        # Verify each result has audit info
        for result in batch_result.results:
            assert result.audit_info is not None
            assert result.audit_info.recorded

        # Verify events in database
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_agent_run.id,
            AgentEvent.event_type == "agent_materialized",
        ).all()

        assert len(events) == 3

    def test_failed_materialization_no_audit_event(self, db_session, temp_project_dir, sample_agent_run):
        """Failed materialization does not record audit event."""
        # Create spec with invalid data that will cause failure
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

        assert not result.success
        assert result.audit_info is None


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases for audit event recording."""

    def test_audit_continues_on_event_recording_failure(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Materialization succeeds even if event recording fails."""
        materializer = AgentMaterializer(temp_project_dir)

        # Mock event recorder to fail by patching within event_recorder module
        with patch('api.event_recorder.EventRecorder.record_agent_materialized') as mock_method:
            mock_method.side_effect = Exception("DB Error")

            result = materializer.materialize_with_audit(
                spec=sample_agent_spec,
                session=db_session,
                run_id=sample_agent_run.id,
            )

        # Materialization should still succeed
        assert result.success
        assert result.file_path.exists()

        # Audit info should indicate failure
        assert result.audit_info is not None
        assert not result.audit_info.recorded
        assert "DB Error" in result.audit_info.error

    def test_materialization_result_to_dict_includes_audit_info(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """MaterializationResult.to_dict includes audit_info."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        d = result.to_dict()

        assert "audit_info" in d
        assert d["audit_info"] is not None
        assert "event_id" in d["audit_info"]
        assert "run_id" in d["audit_info"]
        assert "recorded" in d["audit_info"]


# =============================================================================
# Feature Verification Steps Summary
# =============================================================================

class TestFeature195VerificationSteps:
    """
    Comprehensive tests for all 4 verification steps of Feature #195.

    These tests serve as the final verification that all requirements are met.
    """

    def test_step1_agent_materialized_event_type_exists(self):
        """Step 1: Create agent_materialized event type."""
        # agent_materialized must be a valid event type
        assert "agent_materialized" in EVENT_TYPES

        # EventRecorder must have convenience method
        assert hasattr(EventRecorder, "record_agent_materialized")

    def test_step2_event_includes_required_fields(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 2: Event includes agent_name, file_path, spec_hash, timestamp."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Check all required fields
        assert "agent_name" in event.payload
        assert "file_path" in event.payload
        assert "spec_hash" in event.payload
        assert event.timestamp is not None

    def test_step3_event_linked_to_agentspec(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 3: Event linked to AgentSpec in database."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Event payload contains spec_id that links to AgentSpec
        assert "spec_id" in event.payload
        assert event.payload["spec_id"] == sample_agent_spec.id

        # Can query spec from event payload
        spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == event.payload["spec_id"]
        ).first()
        assert spec is not None

    def test_step4_event_persisted_to_agent_events_table(
        self, db_session, temp_project_dir, sample_agent_spec, sample_agent_run
    ):
        """Step 4: Event persisted to agent_events table."""
        materializer = AgentMaterializer(temp_project_dir)

        result = materializer.materialize_with_audit(
            spec=sample_agent_spec,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Event exists in agent_events table
        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event is not None
        assert event.__tablename__ == "agent_events"
        assert event.event_type == "agent_materialized"
        assert event.run_id == sample_agent_run.id


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #195 components are exported from api package."""

    def test_materialization_audit_info_exported(self):
        """MaterializationAuditInfo is exported from api package."""
        from api import MaterializationAuditInfo

        # Should be able to instantiate
        info = MaterializationAuditInfo()
        assert info.recorded is False

    def test_agent_materializer_has_audit_methods(self):
        """AgentMaterializer has audit methods."""
        from api import AgentMaterializer

        assert hasattr(AgentMaterializer, "materialize_with_audit")
        assert hasattr(AgentMaterializer, "materialize_batch_with_audit")
        assert hasattr(AgentMaterializer, "_record_materialization_event")
