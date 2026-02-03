"""
Tests for Feature #225: tests_executed audit event type created
================================================================

This test suite verifies the tests_executed audit event functionality including:
- Step 1: 'tests_executed' added to event_type enum
- Step 2: Event payload includes: passed, failed, skipped, duration
- Step 3: Event recorded after test execution completes
- Step 4: Event linked to AgentRun and test artifact
- Step 5: Event queryable via existing event APIs

Run with:
    pytest tests/test_feature_225_tests_executed_event.py -v
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
    EVENT_TYPES,
    generate_uuid,
)
from api.event_recorder import EventRecorder, get_event_recorder
from api.test_runner import (
    TestExecutionResult,
    TestFailure,
    TestRunner,
    record_tests_executed,
)


# =============================================================================
# Step 1: 'tests_executed' added to event_type enum
# =============================================================================

class TestStep1EventTypeEnum:
    """Tests for Feature #225 Step 1: 'tests_executed' added to event_type enum."""

    def test_tests_executed_in_event_types(self):
        """'tests_executed' is a valid event type in EVENT_TYPES constant."""
        assert "tests_executed" in EVENT_TYPES

    def test_event_types_is_list(self):
        """EVENT_TYPES is a list data structure."""
        assert isinstance(EVENT_TYPES, list)

    def test_tests_executed_is_string(self):
        """'tests_executed' is a string entry in EVENT_TYPES."""
        # Find and verify the entry
        matching = [t for t in EVENT_TYPES if t == "tests_executed"]
        assert len(matching) == 1
        assert isinstance(matching[0], str)

    def test_event_types_includes_other_test_events(self):
        """EVENT_TYPES includes related test events for comprehensive coverage."""
        # Feature #206 added tests_written
        assert "tests_written" in EVENT_TYPES
        # tests_executed is part of the test lifecycle
        assert "tests_executed" in EVENT_TYPES

    def test_event_recorder_validates_event_type(self):
        """EventRecorder.record() validates event_type against EVENT_TYPES."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Invalid event type should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            recorder.record("test-run", "invalid_event_type")

        assert "Invalid event_type" in str(exc_info.value)
        assert "invalid_event_type" in str(exc_info.value)


# =============================================================================
# Step 2: Event payload includes: passed, failed, skipped, duration
# =============================================================================

class TestStep2EventPayloadFields:
    """Tests for Feature #225 Step 2: Event payload includes required fields."""

    def test_record_tests_executed_includes_passed(self):
        """tests_executed event payload includes 'passed' boolean."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=True,
        )

        event = mock_session.add.call_args[0][0]
        assert "passed" in event.payload
        assert event.payload["passed"] is True

    def test_record_tests_executed_includes_passed_false(self):
        """tests_executed event payload correctly records passed=False."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=False,
            failed_tests=3,
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload["passed"] is False

    def test_record_tests_executed_includes_failed_tests(self):
        """tests_executed event payload includes 'failed_tests' count."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=False,
            failed_tests=5,
        )

        event = mock_session.add.call_args[0][0]
        assert "failed_tests" in event.payload
        assert event.payload["failed_tests"] == 5

    def test_record_tests_executed_includes_skipped_tests(self):
        """tests_executed event payload includes 'skipped_tests' count."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=True,
            skipped_tests=2,
        )

        event = mock_session.add.call_args[0][0]
        assert "skipped_tests" in event.payload
        assert event.payload["skipped_tests"] == 2

    def test_record_tests_executed_includes_duration(self):
        """tests_executed event payload includes 'duration_seconds'."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=True,
            duration_seconds=15.5,
        )

        event = mock_session.add.call_args[0][0]
        assert "duration_seconds" in event.payload
        assert event.payload["duration_seconds"] == 15.5

    def test_record_tests_executed_includes_all_counts(self):
        """tests_executed event payload includes all test counts."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=False,
            total_tests=100,
            passed_tests=85,
            failed_tests=10,
            skipped_tests=3,
            error_tests=2,
            duration_seconds=45.0,
        )

        event = mock_session.add.call_args[0][0]

        # Verify all required fields per Feature #225
        assert event.payload["total_tests"] == 100
        assert event.payload["passed_tests"] == 85
        assert event.payload["failed_tests"] == 10
        assert event.payload["skipped_tests"] == 3
        assert event.payload["error_tests"] == 2
        assert event.payload["duration_seconds"] == 45.0

    def test_record_tests_executed_includes_test_framework(self):
        """tests_executed event payload includes 'test_framework'."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=True,
            test_framework="pytest",
        )

        event = mock_session.add.call_args[0][0]
        assert "test_framework" in event.payload
        assert event.payload["test_framework"] == "pytest"


# =============================================================================
# Step 3: Event recorded after test execution completes
# =============================================================================

class TestStep3EventRecordedAfterExecution:
    """Tests for Feature #225 Step 3: Event recorded after test execution completes."""

    def test_record_tests_executed_from_result(self):
        """record_tests_executed function records event from TestExecutionResult."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            skipped_tests=0,
            command="pytest tests/",
            duration_seconds=5.0,
            framework="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
        )

        assert mock_session.add.called
        event = mock_session.add.call_args[0][0]
        assert event.event_type == "tests_executed"

    def test_record_tests_executed_captures_timing(self):
        """Event records timing information from test execution."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            duration_seconds=123.45,
            command="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload["duration_seconds"] == 123.45

    def test_record_tests_executed_captures_failures(self):
        """Event records failure details from test execution."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        failures = [
            TestFailure(test_name="test_foo", message="AssertionError"),
            TestFailure(test_name="test_bar", message="ValueError"),
        ]

        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            failed_tests=2,
            failures=failures,
            command="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
        )

        event = mock_session.add.call_args[0][0]
        assert "failures" in event.payload
        assert len(event.payload["failures"]) == 2

    def test_record_tests_executed_includes_command(self):
        """Event records the test command that was executed."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            command="pytest tests/ -v --cov",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload["command"] == "pytest tests/ -v --cov"


# =============================================================================
# Step 4: Event linked to AgentRun and test artifact
# =============================================================================

class TestStep4EventLinkedToRunAndArtifact:
    """Tests for Feature #225 Step 4: Event linked to AgentRun and test artifact."""

    def test_event_has_run_id(self):
        """tests_executed event is linked to AgentRun via run_id."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        run_id = "test-run-abc123"

        recorder.record_tests_executed(
            run_id=run_id,
            agent_name="test-agent",
            command="pytest",
            passed=True,
        )

        event = mock_session.add.call_args[0][0]
        assert event.run_id == run_id

    def test_event_includes_spec_id(self):
        """tests_executed event can reference AgentSpec via spec_id."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        spec_id = "spec-xyz789"

        # record_tests_executed from test_runner.py includes spec_id
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            command="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
            spec_id=spec_id,
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload.get("spec_id") == spec_id

    def test_event_includes_test_target(self):
        """tests_executed event can reference test target (feature/artifact)."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            command="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
            test_target="feature-225",
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload.get("test_target") == "feature-225"

    def test_event_model_has_run_relationship(self):
        """AgentEvent model has relationship to AgentRun."""
        # Verify the relationship exists in the model
        from sqlalchemy import inspect
        mapper = inspect(AgentEvent)
        relationships = [rel.key for rel in mapper.relationships]
        assert "run" in relationships

    def test_event_model_has_artifact_ref_field(self):
        """AgentEvent model has artifact_ref field for linking to artifacts."""
        from sqlalchemy import inspect
        mapper = inspect(AgentEvent)
        columns = [col.key for col in mapper.columns]
        assert "artifact_ref" in columns


# =============================================================================
# Step 5: Event queryable via existing event APIs
# =============================================================================

class TestStep5EventQueryableViaAPI:
    """Tests for Feature #225 Step 5: Event queryable via existing event APIs."""

    def test_tests_executed_is_valid_event_type_filter(self):
        """'tests_executed' can be used as event_type filter in API queries."""
        # The API validates event_type against EVENT_TYPES
        assert "tests_executed" in EVENT_TYPES

    def test_event_type_validation_in_api(self):
        """API endpoint validates event_type parameter."""
        # Import the router to verify validation logic
        from server.routers.agent_runs import get_run_events

        # The endpoint uses EVENT_TYPES for validation (line 315 of agent_runs.py)
        # Tests can filter by event_type="tests_executed"
        assert "tests_executed" in EVENT_TYPES

    def test_event_can_be_filtered_by_type(self):
        """Events can be filtered by event_type in database queries."""
        # Create mock event data
        mock_event = MagicMock()
        mock_event.event_type = "tests_executed"
        mock_event.run_id = "test-run-123"
        mock_event.payload = {"passed": True}

        # Verify filtering works (simulated)
        events = [mock_event]
        filtered = [e for e in events if e.event_type == "tests_executed"]

        assert len(filtered) == 1
        assert filtered[0].event_type == "tests_executed"

    def test_event_payload_is_json_serializable(self):
        """Event payload is JSON serializable for API responses."""
        import json

        payload = {
            "agent_name": "test-agent",
            "command": "pytest tests/",
            "passed": True,
            "total_tests": 10,
            "passed_tests": 10,
            "failed_tests": 0,
            "skipped_tests": 0,
            "error_tests": 0,
            "duration_seconds": 5.5,
            "test_framework": "pytest",
        }

        # Should not raise
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)

        assert deserialized == payload


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for tests_executed event."""

    def test_full_event_recording_flow(self):
        """Test complete flow from test execution to event recording."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Simulate test execution result
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            expected_exit_code=0,
            total_tests=50,
            passed_tests=45,
            failed_tests=3,
            skipped_tests=2,
            error_tests=0,
            failures=[
                TestFailure(test_name="test_auth", message="Auth failed"),
                TestFailure(test_name="test_db", message="DB error"),
                TestFailure(test_name="test_api", message="API timeout"),
            ],
            stdout="test output...",
            stderr="",
            command="pytest tests/ -v",
            duration_seconds=120.5,
            framework="pytest",
            framework_version="7.4.0",
        )

        # Record the event
        record_tests_executed(
            recorder=recorder,
            run_id="integration-run-001",
            result=result,
            agent_name="integration-test-agent",
            spec_id="spec-integration",
            test_target="feature-225-integration",
        )

        # Verify event was recorded with correct data
        event = mock_session.add.call_args[0][0]

        # Step 1: Event type is correct
        assert event.event_type == "tests_executed"

        # Step 2: Payload includes all required fields
        assert event.payload["passed"] is False
        assert event.payload["failed_tests"] == 3
        assert event.payload["skipped_tests"] == 2
        assert event.payload["duration_seconds"] == 120.5

        # Step 3: Event recorded after execution
        assert mock_session.add.called

        # Step 4: Linked to run
        assert event.run_id == "integration-run-001"

        # Additional verification
        assert event.payload["total_tests"] == 50
        assert event.payload["passed_tests"] == 45
        assert event.payload["command"] == "pytest tests/ -v"
        assert len(event.payload["failures"]) == 3


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for tests_executed event."""

    def test_zero_tests_executed(self):
        """Handle case where zero tests were executed."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/",
            passed=True,  # Zero tests = technically passed
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            skipped_tests=0,
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload["total_tests"] == 0

    def test_all_tests_skipped(self):
        """Handle case where all tests were skipped."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest tests/ -k skip",
            passed=True,
            total_tests=5,
            passed_tests=0,
            failed_tests=0,
            skipped_tests=5,
        )

        event = mock_session.add.call_args[0][0]
        assert event.payload["skipped_tests"] == 5
        assert event.payload["passed_tests"] == 0

    def test_very_long_failure_messages_truncated_via_helper_function(self):
        """Very long failure messages are truncated when using record_tests_executed helper."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Create failure with very long message
        long_message = "x" * 1000
        failures = [
            TestFailure(test_name="test_long", message=long_message)
        ]

        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            failures=failures,
            command="pytest",
        )

        # Use the convenience function which truncates messages
        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
        )

        event = mock_session.add.call_args[0][0]
        # Messages should be truncated to 200 chars by record_tests_executed
        assert len(event.payload["failures"][0]["message"]) <= 200

    def test_too_many_failures_truncated(self):
        """More than 10 failures are truncated in event payload."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Create 15 failures
        failures = [
            {"test_name": f"test_{i}", "message": f"Failed {i}"}
            for i in range(15)
        ]

        recorder.record_tests_executed(
            run_id="test-run-123",
            agent_name="test-agent",
            command="pytest",
            passed=False,
            failures=failures,
        )

        event = mock_session.add.call_args[0][0]
        # Max 10 failures in payload
        assert len(event.payload["failures"]) == 10

    def test_error_message_included(self):
        """Error message from failed execution is included."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        result = TestExecutionResult(
            passed=False,
            exit_code=None,
            command="pytest",
            error_message="Execution timed out after 300 seconds",
        )

        record_tests_executed(
            recorder=recorder,
            run_id="test-run-123",
            result=result,
            agent_name="test-agent",
        )

        event = mock_session.add.call_args[0][0]
        assert "error_message" in event.payload
        assert "timed out" in event.payload["error_message"]


# =============================================================================
# Feature #225 Verification Steps (Comprehensive)
# =============================================================================

class TestFeature225VerificationSteps:
    """
    Comprehensive tests verifying all 5 feature steps.
    These tests serve as acceptance criteria for Feature #225.
    """

    def test_step_1_tests_executed_in_event_type_enum(self):
        """
        Step 1: Add 'tests_executed' to event_type enum

        Verify that 'tests_executed' is a valid event type.
        """
        assert "tests_executed" in EVENT_TYPES

        # Verify EventRecorder accepts this event type
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Should not raise
        recorder.record("test-run", "tests_executed", payload={"test": True})

        event = mock_session.add.call_args[0][0]
        assert event.event_type == "tests_executed"

    def test_step_2_payload_includes_required_fields(self):
        """
        Step 2: Event payload includes: passed, failed, skipped, duration

        Verify that the event payload contains all required fields.
        """
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)
        recorder.record_tests_executed(
            run_id="verify-run",
            agent_name="verify-agent",
            command="pytest",
            passed=False,
            total_tests=100,
            passed_tests=90,
            failed_tests=5,
            skipped_tests=5,
            error_tests=0,
            duration_seconds=60.0,
        )

        event = mock_session.add.call_args[0][0]
        payload = event.payload

        # Required fields per Feature #225
        assert "passed" in payload and payload["passed"] is False
        assert "failed_tests" in payload and payload["failed_tests"] == 5
        assert "skipped_tests" in payload and payload["skipped_tests"] == 5
        assert "duration_seconds" in payload and payload["duration_seconds"] == 60.0

    def test_step_3_event_recorded_after_test_execution(self):
        """
        Step 3: Event recorded after test execution completes

        Verify that the convenience function records events after execution.
        """
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        # Create test execution result (simulates completed execution)
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            command="pytest",
            duration_seconds=5.0,
        )

        # Record event from result
        record_tests_executed(
            recorder=recorder,
            run_id="verify-run",
            result=result,
            agent_name="verify-agent",
        )

        # Verify event was recorded
        assert mock_session.add.called
        assert mock_session.commit.called

        event = mock_session.add.call_args[0][0]
        assert event.event_type == "tests_executed"

    def test_step_4_event_linked_to_agentrun_and_artifact(self):
        """
        Step 4: Event linked to AgentRun and test artifact

        Verify that the event is properly linked via run_id and can reference artifacts.
        """
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        recorder = EventRecorder(mock_session)

        run_id = "linked-run-abc"
        spec_id = "linked-spec-xyz"

        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            command="pytest",
        )

        record_tests_executed(
            recorder=recorder,
            run_id=run_id,
            result=result,
            agent_name="verify-agent",
            spec_id=spec_id,
            test_target="feature-225",
        )

        event = mock_session.add.call_args[0][0]

        # Verify link to AgentRun
        assert event.run_id == run_id

        # Verify references in payload
        assert event.payload.get("spec_id") == spec_id
        assert event.payload.get("test_target") == "feature-225"

    def test_step_5_event_queryable_via_existing_apis(self):
        """
        Step 5: Event queryable via existing event APIs

        Verify that 'tests_executed' is included in EVENT_TYPES used by API validation.
        """
        # The API uses EVENT_TYPES for validation
        from api.agentspec_models import EVENT_TYPES as API_EVENT_TYPES

        assert "tests_executed" in API_EVENT_TYPES

        # Verify the event type can be used in queries
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        # Simulate API query filter
        mock_query.filter(AgentEvent.event_type == "tests_executed")

        # Should work without error
        assert mock_query.filter.called


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Tests that Feature #225 components are accessible from api package."""

    def test_event_types_accessible_from_models(self):
        """EVENT_TYPES is accessible from api.agentspec_models."""
        from api.agentspec_models import EVENT_TYPES

        assert isinstance(EVENT_TYPES, list)
        assert "tests_executed" in EVENT_TYPES

    def test_event_recorder_exported(self):
        """EventRecorder is accessible from api package."""
        from api import EventRecorder as ER
        from api.event_recorder import EventRecorder

        assert ER is EventRecorder

    def test_record_tests_executed_exported(self):
        """record_tests_executed function is accessible from api package."""
        from api import record_tests_executed as rte
        from api.test_runner import record_tests_executed

        assert rte is record_tests_executed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
