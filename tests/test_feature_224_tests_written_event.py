"""
Tests for Feature #224: tests_written audit event type created.

This feature ensures that a new event type 'tests_written' is properly:
1. Added to the event_type enum
2. Includes payload with: test_files, test_count, framework
3. Recorded after test files are written
4. Linked to AgentRun via run_id
5. Queryable via existing event APIs

Test Categories:
- TestStep1EventTypeEnum: Verify tests_written is in EVENT_TYPES
- TestStep2EventPayload: Verify payload includes required fields
- TestStep3EventRecording: Verify event is recorded after test files written
- TestStep4EventLinkedToRun: Verify event is linked to AgentRun
- TestStep5EventQueryable: Verify event is queryable via existing event APIs
- TestRecordTestsWrittenMethod: Test the convenience method
- TestIntegration: End-to-end integration tests
- TestFeature224VerificationSteps: Acceptance tests for all feature steps
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
    EVENT_TYPES,
    generate_uuid,
)
from api.event_recorder import EventRecorder, get_event_recorder, clear_recorder_cache
from api.test_code_writer import TestCodeWriteResult


# =============================================================================
# Helper function to create test AgentSpec with all required fields
# =============================================================================

def create_test_agent_spec(name: str = "test-agent") -> AgentSpec:
    """Create a test AgentSpec with all required fields."""
    return AgentSpec(
        id=generate_uuid(),
        name=name,
        display_name="Test Agent",
        spec_version="v1",
        objective="Test objective for feature testing",
        task_type="testing",
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Grep"],
            "forbidden_patterns": [],
        },
    )


# =============================================================================
# Shared fixtures
# =============================================================================

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from api.agentspec_models import Base

    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def run_id(temp_db):
    """Create a test AgentRun and return its ID."""
    spec = create_test_agent_spec()
    temp_db.add(spec)
    temp_db.flush()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="running",
    )
    temp_db.add(run)
    temp_db.commit()
    return run.id


@pytest.fixture
def recorder(temp_db, tmp_path):
    """Create an EventRecorder instance."""
    clear_recorder_cache()
    return EventRecorder(temp_db, tmp_path)


# =============================================================================
# Step 1: Add 'tests_written' to event_type enum
# =============================================================================

class TestStep1EventTypeEnum:
    """Verify tests_written is a valid event type in EVENT_TYPES."""

    def test_tests_written_in_event_types(self):
        """tests_written must be in EVENT_TYPES list."""
        assert "tests_written" in EVENT_TYPES

    def test_tests_written_is_string(self):
        """tests_written is a string value."""
        tests_written_type = [t for t in EVENT_TYPES if t == "tests_written"]
        assert len(tests_written_type) == 1
        assert isinstance(tests_written_type[0], str)

    def test_event_types_is_list(self):
        """EVENT_TYPES is a list."""
        assert isinstance(EVENT_TYPES, list)

    def test_tests_written_not_duplicate(self):
        """tests_written appears exactly once in EVENT_TYPES."""
        count = EVENT_TYPES.count("tests_written")
        assert count == 1


# =============================================================================
# Step 2: Event payload includes: test_files, test_count, framework
# =============================================================================

class TestStep2EventPayload:
    """Verify event payload includes required fields."""

    def test_payload_includes_test_files(self, recorder, run_id, temp_db):
        """Payload must include test_files list."""
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert "test_files" in event.payload
        assert event.payload["test_files"] == ["tests/test_example.py"]

    def test_payload_includes_test_count(self, recorder, run_id, temp_db):
        """Payload must include test_count."""
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=10,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert "test_count" in event.payload
        assert event.payload["test_count"] == 10

    def test_payload_includes_framework(self, recorder, run_id, temp_db):
        """Payload must include test_framework (framework)."""
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="jest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        # test_framework is the payload key name (maps to 'framework' in feature spec)
        assert "test_framework" in event.payload
        assert event.payload["test_framework"] == "jest"

    def test_payload_includes_all_required_fields(self, recorder, run_id, temp_db):
        """Payload includes all three required fields."""
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_a.py", "tests/test_b.py"],
            test_count=15,
            test_framework="unittest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None

        # All three required fields present
        assert "test_files" in event.payload
        assert "test_count" in event.payload
        assert "test_framework" in event.payload

        # Verify values
        assert event.payload["test_files"] == ["tests/test_a.py", "tests/test_b.py"]
        assert event.payload["test_count"] == 15
        assert event.payload["test_framework"] == "unittest"

    def test_payload_with_multiple_test_files(self, recorder, run_id, temp_db):
        """Payload supports multiple test files."""
        test_files = [
            "tests/unit/test_module1.py",
            "tests/unit/test_module2.py",
            "tests/integration/test_api.py",
        ]
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=test_files,
            test_count=25,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["test_files"] == test_files
        assert len(event.payload["test_files"]) == 3

    def test_test_count_zero_is_valid(self, recorder, run_id, temp_db):
        """test_count of 0 is valid."""
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_empty.py"],
            test_count=0,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["test_count"] == 0


# =============================================================================
# Step 3: Event recorded after test files written
# =============================================================================

class TestStep3EventRecording:
    """Verify event is recorded after test files are written."""

    def test_event_recorded_with_timestamp(self, temp_db, run_id, tmp_path):
        """Event is recorded with a timestamp."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        before_time = datetime.now(timezone.utc)
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )
        after_time = datetime.now(timezone.utc)

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.timestamp is not None

    def test_event_recorded_with_sequence_number(self, temp_db, run_id, tmp_path):
        """Event is recorded with a sequence number starting at 1."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.sequence >= 1

    def test_event_type_is_tests_written(self, temp_db, run_id, tmp_path):
        """Event type is 'tests_written'."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.event_type == "tests_written"

    def test_event_returns_valid_id(self, temp_db, run_id, tmp_path):
        """record_tests_written returns a valid event ID."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        assert event_id is not None
        assert isinstance(event_id, int)
        assert event_id > 0

    def test_event_persisted_to_database(self, temp_db, run_id, tmp_path):
        """Event is persisted to database (committed)."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        # Query with new session to verify persistence
        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None


# =============================================================================
# Step 4: Event linked to AgentRun
# =============================================================================

class TestStep4EventLinkedToRun:
    """Verify event is linked to AgentRun via run_id."""

    def test_event_has_run_id(self, temp_db, run_id, tmp_path):
        """Event has run_id field populated."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.run_id == run_id

    def test_event_linked_to_correct_run(self, temp_db, tmp_path):
        """Event is linked to the correct AgentRun."""
        # Create two runs
        spec = create_test_agent_spec()
        temp_db.add(spec)
        temp_db.flush()

        run1 = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
        run2 = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
        temp_db.add_all([run1, run2])
        temp_db.commit()

        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record event for run1
        event_id = recorder.record_tests_written(
            run_id=run1.id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.run_id == run1.id
        assert event.run_id != run2.id

    def test_can_query_events_by_run_id(self, temp_db, run_id, tmp_path):
        """Events can be queried by run_id."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record multiple events
        recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-1",
            agent_name="agent-1",
            test_files=["tests/test_1.py"],
            test_count=5,
            test_framework="pytest",
        )
        recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-2",
            agent_name="agent-2",
            test_files=["tests/test_2.py"],
            test_count=10,
            test_framework="pytest",
        )

        # Query all events for this run
        events = (
            temp_db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .filter(AgentEvent.event_type == "tests_written")
            .all()
        )
        assert len(events) == 2

    def test_event_relationship_to_run(self, temp_db, run_id, tmp_path):
        """Event has relationship to AgentRun object."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        # Access the relationship
        assert event.run is not None
        assert event.run.id == run_id


# =============================================================================
# Step 5: Event queryable via existing event APIs
# =============================================================================

class TestStep5EventQueryable:
    """Verify event is queryable via existing event APIs."""

    def test_tests_written_is_valid_event_type_filter(self):
        """tests_written can be used as event_type filter in API."""
        # The EVENT_TYPES list is used by the API to validate event_type query parameter
        assert "tests_written" in EVENT_TYPES

    def test_query_events_by_event_type(self, temp_db, run_id, tmp_path):
        """Can query events filtered by event_type='tests_written'."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record different event types
        recorder.record(run_id, "started", payload={"message": "started"})
        recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )
        recorder.record(run_id, "completed", payload={"message": "completed"})

        # Query only tests_written events
        events = (
            temp_db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .filter(AgentEvent.event_type == "tests_written")
            .all()
        )
        assert len(events) == 1
        assert events[0].event_type == "tests_written"

    def test_query_all_events_includes_tests_written(self, temp_db, run_id, tmp_path):
        """Query all events includes tests_written events."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record events
        recorder.record(run_id, "started", payload={"message": "started"})
        recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        # Query all events
        events = (
            temp_db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .order_by(AgentEvent.sequence)
            .all()
        )

        event_types = [e.event_type for e in events]
        assert "tests_written" in event_types

    def test_event_to_dict_serialization(self, temp_db, run_id, tmp_path):
        """Event can be serialized to dict for API response."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None

        # Serialize to dict
        event_dict = event.to_dict()

        # Verify dict structure
        assert "id" in event_dict
        assert "run_id" in event_dict
        assert "event_type" in event_dict
        assert "timestamp" in event_dict
        assert "sequence" in event_dict
        assert "payload" in event_dict

        # Verify event type
        assert event_dict["event_type"] == "tests_written"

        # Verify payload contains required fields
        assert "test_files" in event_dict["payload"]
        assert "test_count" in event_dict["payload"]
        assert "test_framework" in event_dict["payload"]


# =============================================================================
# Test record_tests_written convenience method
# =============================================================================

class TestRecordTestsWrittenMethod:
    """Test the record_tests_written convenience method."""

    def test_method_exists(self):
        """EventRecorder has record_tests_written method."""
        assert hasattr(EventRecorder, "record_tests_written")

    def test_method_accepts_required_parameters(self, temp_db, run_id, tmp_path):
        """Method accepts all required parameters."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Should not raise
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
        )
        assert event_id is not None

    def test_method_accepts_optional_parameters(self, temp_db, run_id, tmp_path):
        """Method accepts optional parameters."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Should not raise
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=10,
            test_type="unit",
            test_framework="pytest",
            test_directory="tests",
            assertions_count=25,
        )
        assert event_id is not None

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["test_count"] == 10
        assert event.payload["test_type"] == "unit"
        assert event.payload["test_framework"] == "pytest"
        assert event.payload["test_directory"] == "tests"
        assert event.payload["assertions_count"] == 25

    def test_method_with_test_count_none(self, temp_db, run_id, tmp_path):
        """Method handles test_count=None (omits from payload)."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-123",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=None,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        # test_count should not be in payload if None was passed
        assert "test_count" not in event.payload


# =============================================================================
# Integration tests
# =============================================================================

class TestIntegration:
    """End-to-end integration tests for tests_written event."""

    def test_complete_workflow(self, temp_db, run_id, tmp_path):
        """Test complete workflow: record event -> query -> serialize."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # 1. Record the event
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-integration-test",
            agent_name="integration-test-agent",
            test_files=["tests/test_feature.py", "tests/test_utils.py"],
            test_count=12,
            test_framework="pytest",
            test_directory="tests",
        )

        # 2. Query the event
        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.event_type == "tests_written"
        assert event.run_id == run_id

        # 3. Serialize for API response
        event_dict = event.to_dict()
        assert event_dict["event_type"] == "tests_written"
        assert event_dict["payload"]["test_files"] == ["tests/test_feature.py", "tests/test_utils.py"]
        assert event_dict["payload"]["test_count"] == 12
        assert event_dict["payload"]["test_framework"] == "pytest"

    def test_multiple_tests_written_events_in_run(self, temp_db, run_id, tmp_path):
        """Multiple tests_written events can be recorded in a single run."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record multiple events
        event_id_1 = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-1",
            agent_name="agent-1",
            test_files=["tests/test_1.py"],
            test_count=5,
            test_framework="pytest",
        )
        event_id_2 = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-2",
            agent_name="agent-2",
            test_files=["tests/test_2.py"],
            test_count=10,
            test_framework="jest",
        )

        # Query all tests_written events
        events = (
            temp_db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .filter(AgentEvent.event_type == "tests_written")
            .order_by(AgentEvent.sequence)
            .all()
        )

        assert len(events) == 2
        assert events[0].payload["contract_id"] == "contract-1"
        assert events[1].payload["contract_id"] == "contract-2"

    def test_test_code_write_result_has_test_count(self):
        """TestCodeWriteResult dataclass has test_count field."""
        result = TestCodeWriteResult(
            contract_id="contract-123",
            agent_name="test-agent",
            success=True,
            test_files=[Path("tests/test_example.py")],
            test_framework="pytest",
            test_count=10,
            assertions_count=25,
        )

        assert result.test_count == 10

        # Verify serialization
        result_dict = result.to_dict()
        assert "test_count" in result_dict
        assert result_dict["test_count"] == 10


# =============================================================================
# Feature #224 Verification Steps (Acceptance Tests)
# =============================================================================

class TestFeature224VerificationSteps:
    """Acceptance tests for all Feature #224 verification steps."""

    def test_step1_tests_written_in_event_type_enum(self):
        """Step 1: Add 'tests_written' to event_type enum."""
        assert "tests_written" in EVENT_TYPES, "tests_written must be in EVENT_TYPES"

    def test_step2_event_payload_includes_required_fields(self, temp_db, run_id, tmp_path):
        """Step 2: Event payload includes: test_files, test_count, framework."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-224",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=7,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None

        # Verify all required payload fields
        assert "test_files" in event.payload, "payload must include test_files"
        assert "test_count" in event.payload, "payload must include test_count"
        assert "test_framework" in event.payload, "payload must include test_framework (framework)"

        # Verify values
        assert event.payload["test_files"] == ["tests/test_example.py"]
        assert event.payload["test_count"] == 7
        assert event.payload["test_framework"] == "pytest"

    def test_step3_event_recorded_after_test_files_written(self, temp_db, run_id, tmp_path):
        """Step 3: Event recorded after test files written."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record the event
        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-224",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        # Verify event was recorded
        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None, "Event must be recorded"
        assert event.event_type == "tests_written", "Event type must be tests_written"
        assert event.timestamp is not None, "Event must have timestamp"
        assert event.sequence >= 1, "Event must have sequence number"

    def test_step4_event_linked_to_agent_run(self, temp_db, run_id, tmp_path):
        """Step 4: Event linked to AgentRun."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        event_id = recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-224",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )

        event = temp_db.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None

        # Verify link to AgentRun
        assert event.run_id == run_id, "Event must be linked to AgentRun via run_id"
        assert event.run is not None, "Event must have relationship to AgentRun"
        assert event.run.id == run_id, "Event.run must point to correct AgentRun"

    def test_step5_event_queryable_via_existing_event_apis(self, temp_db, run_id, tmp_path):
        """Step 5: Event queryable via existing event APIs."""
        clear_recorder_cache()
        recorder = EventRecorder(temp_db, tmp_path)

        # Record events of different types
        recorder.record(run_id, "started", payload={"message": "started"})
        recorder.record_tests_written(
            run_id=run_id,
            contract_id="contract-224",
            agent_name="test-agent",
            test_files=["tests/test_example.py"],
            test_count=5,
            test_framework="pytest",
        )
        recorder.record(run_id, "completed", payload={"message": "completed"})

        # Query by run_id (standard pattern)
        all_events = (
            temp_db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .order_by(AgentEvent.sequence)
            .all()
        )
        assert len(all_events) == 3

        # Query filtered by event_type (API pattern)
        tests_written_events = (
            temp_db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .filter(AgentEvent.event_type == "tests_written")
            .all()
        )
        assert len(tests_written_events) == 1
        assert tests_written_events[0].event_type == "tests_written"

        # Verify tests_written is valid filter value
        assert "tests_written" in EVENT_TYPES, "tests_written must be valid event_type for API filtering"
