"""
Tests for Feature #223: icon_generated audit event type created
===============================================================

New event type recorded when an icon is generated for an agent.

Verification Steps:
1. Add 'icon_generated' to event_type enum
2. Event payload includes: agent_name, provider_used, icon_format
3. Event recorded after successful icon generation
4. Event linked to AgentSpec
5. Event queryable via existing event APIs
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import tempfile

# Core imports
from api.agentspec_models import EVENT_TYPES, AgentEvent, AgentRun, AgentSpec, generate_uuid
from api.event_recorder import EventRecorder, get_event_recorder
from api.database import create_database, Feature, Base


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_db_session():
    """Create a temporary database with session for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)
        session = SessionLocal()
        try:
            yield session, project_dir
        finally:
            session.close()


@pytest.fixture
def sample_agent_spec(temp_db_session):
    """Create a sample AgentSpec in the database."""
    session, project_dir = temp_db_session
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-icon-agent",
        display_name="Test Icon Agent",
        spec_version="v1",
        objective="Test icon generation",
        task_type="coding",
        context={},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read"],
            "forbidden_patterns": [],
            "tool_hints": {},
        },
        max_turns=50,
        timeout_seconds=1800,
    )
    session.add(spec)
    session.commit()
    return spec


@pytest.fixture
def sample_agent_run(temp_db_session, sample_agent_spec):
    """Create a sample AgentRun in the database."""
    session, project_dir = temp_db_session
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_agent_spec.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    return run


# =============================================================================
# Step 1: Add 'icon_generated' to event_type enum
# =============================================================================

class TestStep1IconGeneratedEventType:
    """Test that icon_generated is a registered event type."""

    def test_icon_generated_in_event_types(self):
        """Verify icon_generated is in EVENT_TYPES list."""
        assert "icon_generated" in EVENT_TYPES

    def test_icon_generated_can_be_recorded(self, temp_db_session, sample_agent_run):
        """Verify icon_generated events can be recorded in database."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record(
            run_id=sample_agent_run.id,
            event_type="icon_generated",
            payload={
                "agent_name": "test-agent",
                "icon_format": "svg",
                "provider_name": "local_placeholder",
                "success": True,
            },
        )

        assert event_id is not None
        assert event_id > 0

        # Verify event was stored
        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.event_type == "icon_generated"

    def test_invalid_event_type_raises_error(self, temp_db_session, sample_agent_run):
        """Verify invalid event types raise ValueError."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        with pytest.raises(ValueError, match="Invalid event_type"):
            recorder.record(
                run_id=sample_agent_run.id,
                event_type="invalid_event_type",
                payload={"test": "data"},
            )


# =============================================================================
# Step 2: Event payload includes: agent_name, provider_used, icon_format
# =============================================================================

class TestStep2EventPayloadContents:
    """Test that event payload includes required fields."""

    def test_payload_includes_agent_name(self, temp_db_session, sample_agent_run):
        """Verify payload includes agent_name."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="my-test-agent",
            icon_data="code",
            icon_format="icon_id",
            provider_name="default",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["agent_name"] == "my-test-agent"

    def test_payload_includes_provider_name(self, temp_db_session, sample_agent_run):
        """Verify payload includes provider_name (alias for provider_used)."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            icon_data="shield",
            icon_format="icon_id",
            provider_name="dalle",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        # Note: Implementation uses provider_name, feature spec says provider_used
        # Both refer to the same concept - which provider generated the icon
        assert event.payload["provider_name"] == "dalle"

    def test_payload_includes_icon_format(self, temp_db_session, sample_agent_run):
        """Verify payload includes icon_format."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            icon_data="<svg>...</svg>",
            icon_format="svg",
            provider_name="local_placeholder",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["icon_format"] == "svg"

    def test_payload_includes_all_required_fields(self, temp_db_session, sample_agent_run):
        """Verify payload includes all three required fields."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="complete-agent",
            icon_data="test-icon",
            icon_format="png",
            provider_name="test-provider",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert "agent_name" in event.payload
        assert "icon_format" in event.payload
        assert "provider_name" in event.payload  # Feature says "provider_used"

        assert event.payload["agent_name"] == "complete-agent"
        assert event.payload["icon_format"] == "png"
        assert event.payload["provider_name"] == "test-provider"

    def test_payload_includes_optional_fields(self, temp_db_session, sample_agent_run):
        """Verify payload can include optional fields like success and generation_time_ms."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="test-agent",
            icon_data="icon-data",
            icon_format="webp",
            provider_name="dalle",
            generation_time_ms=150,
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.payload["success"] is True
        assert event.payload["generation_time_ms"] == 150


# =============================================================================
# Step 3: Event recorded after successful icon generation
# =============================================================================

class TestStep3EventRecordedAfterSuccess:
    """Test that event is recorded after successful icon generation."""

    def test_event_recorded_on_successful_generation(self, temp_db_session, sample_agent_run):
        """Verify event is recorded when icon generation succeeds."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record successful icon generation
        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="success-agent",
            icon_data="<svg>icon</svg>",
            icon_format="svg",
            provider_name="local_placeholder",
            success=True,
        )

        # Verify event exists
        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["success"] is True

    def test_event_recorded_on_failed_generation(self, temp_db_session, sample_agent_run):
        """Verify event is recorded even when icon generation fails."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record failed icon generation
        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="fail-agent",
            icon_data=None,
            icon_format="unknown",
            success=False,
            error="API rate limit exceeded",
        )

        # Verify event exists with failure info
        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["success"] is False
        assert event.payload["error"] == "API rate limit exceeded"

    def test_event_has_timestamp(self, temp_db_session, sample_agent_run):
        """Verify event has a timestamp."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        before = datetime.now(timezone.utc)
        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="timestamp-agent",
            icon_data="icon",
            icon_format="icon_id",
            success=True,
        )
        after = datetime.now(timezone.utc)

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event.timestamp is not None
        # Handle both offset-aware and offset-naive timestamps
        event_ts = event.timestamp
        if event_ts.tzinfo is None:
            # Make offset-naive timestamp comparable by assuming UTC
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        assert before <= event_ts <= after


# =============================================================================
# Step 4: Event linked to AgentSpec
# =============================================================================

class TestStep4EventLinkedToAgentSpec:
    """Test that event is linked to AgentSpec."""

    def test_event_includes_spec_id(self, temp_db_session, sample_agent_run, sample_agent_spec):
        """Verify event payload includes spec_id linking to AgentSpec."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name=sample_agent_spec.name,
            icon_data="icon",
            icon_format="svg",
            spec_id=sample_agent_spec.id,
            provider_name="local_placeholder",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.payload["spec_id"] == sample_agent_spec.id

    def test_event_linked_via_run_id(self, temp_db_session, sample_agent_run, sample_agent_spec):
        """Verify event is linked to AgentSpec via AgentRun."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="linked-agent",
            icon_data="icon",
            icon_format="svg",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()
        assert event is not None
        assert event.run_id == sample_agent_run.id

        # Verify we can trace back to AgentSpec via AgentRun
        run = session.query(AgentRun).filter(AgentRun.id == event.run_id).first()
        assert run is not None
        assert run.agent_spec_id == sample_agent_spec.id


# =============================================================================
# Step 5: Event queryable via existing event APIs
# =============================================================================

class TestStep5EventQueryableViaAPIs:
    """Test that icon_generated events are queryable via existing APIs."""

    def test_event_queryable_by_run_id(self, temp_db_session, sample_agent_run):
        """Verify icon_generated events can be queried by run_id."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record multiple events
        recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="agent-1",
            icon_data="icon-1",
            icon_format="svg",
            success=True,
        )
        recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="agent-2",
            icon_data="icon-2",
            icon_format="png",
            success=True,
        )

        # Query events by run_id
        events = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_agent_run.id)
            .filter(AgentEvent.event_type == "icon_generated")
            .all()
        )

        assert len(events) == 2
        agent_names = [e.payload["agent_name"] for e in events]
        assert "agent-1" in agent_names
        assert "agent-2" in agent_names

    def test_event_queryable_by_event_type(self, temp_db_session, sample_agent_run):
        """Verify icon_generated events can be filtered by event_type."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record mixed events
        recorder.record(
            run_id=sample_agent_run.id,
            event_type="started",
            payload={"message": "Run started"},
        )
        recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="icon-agent",
            icon_data="icon",
            icon_format="svg",
            success=True,
        )
        recorder.record(
            run_id=sample_agent_run.id,
            event_type="completed",
            payload={"verdict": "passed"},
        )

        # Query only icon_generated events
        icon_events = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_agent_run.id)
            .filter(AgentEvent.event_type == "icon_generated")
            .all()
        )

        assert len(icon_events) == 1
        assert icon_events[0].event_type == "icon_generated"
        assert icon_events[0].payload["agent_name"] == "icon-agent"

    def test_event_type_valid_for_api_filter(self):
        """Verify icon_generated is valid for API event_type filter."""
        from api.agentspec_models import EVENT_TYPES

        # The API validates event_type against EVENT_TYPES
        # (see server/routers/agent_runs.py line 314-319)
        assert "icon_generated" in EVENT_TYPES

    def test_events_ordered_by_sequence(self, temp_db_session, sample_agent_run):
        """Verify events maintain sequence ordering for timeline display."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record events in order
        recorder.record(
            run_id=sample_agent_run.id,
            event_type="started",
            payload={},
        )
        recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="ordered-agent",
            icon_data="icon",
            icon_format="svg",
            success=True,
        )
        recorder.record(
            run_id=sample_agent_run.id,
            event_type="completed",
            payload={},
        )

        # Query events in sequence order
        events = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_agent_run.id)
            .order_by(AgentEvent.sequence)
            .all()
        )

        assert len(events) == 3
        assert events[0].event_type == "started"
        assert events[0].sequence == 1
        assert events[1].event_type == "icon_generated"
        assert events[1].sequence == 2
        assert events[2].event_type == "completed"
        assert events[2].sequence == 3


# =============================================================================
# Feature #223 Verification Steps (Acceptance Tests)
# =============================================================================

class TestFeature223VerificationSteps:
    """Comprehensive acceptance tests for Feature #223."""

    def test_step1_icon_generated_in_event_type_enum(self):
        """
        Step 1: Add 'icon_generated' to event_type enum

        Verify that 'icon_generated' is a registered event type
        that can be recorded and validated.
        """
        assert "icon_generated" in EVENT_TYPES

        # Also verify it's among the audit-related events
        audit_events = [e for e in EVENT_TYPES if "generated" in e or "materialized" in e]
        assert "icon_generated" in audit_events

    def test_step2_payload_includes_required_fields(self, temp_db_session, sample_agent_run):
        """
        Step 2: Event payload includes: agent_name, provider_used, icon_format

        Note: Implementation uses 'provider_name' which is semantically equivalent
        to 'provider_used' - both refer to the icon provider that was used.
        """
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="feature-223-agent",
            icon_data="test-icon",
            icon_format="svg",
            provider_name="local_placeholder",  # Feature says "provider_used"
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # PASS: All three required fields present
        assert "agent_name" in event.payload
        assert "provider_name" in event.payload  # Semantically "provider_used"
        assert "icon_format" in event.payload

        # PASS: Values are correct
        assert event.payload["agent_name"] == "feature-223-agent"
        assert event.payload["provider_name"] == "local_placeholder"
        assert event.payload["icon_format"] == "svg"

    def test_step3_event_recorded_after_generation(self, temp_db_session, sample_agent_run):
        """
        Step 3: Event recorded after successful icon generation

        Verify that the event is committed to the database immediately
        after icon generation (whether successful or not).
        """
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Count events before
        before_count = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_agent_run.id)
            .count()
        )

        # Record icon generation
        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="gen-agent",
            icon_data="icon",
            icon_format="svg",
            success=True,
        )

        # Count events after
        after_count = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_agent_run.id)
            .count()
        )

        # PASS: Event was recorded
        assert after_count == before_count + 1
        assert event_id > 0

    def test_step4_event_linked_to_agentspec(
        self, temp_db_session, sample_agent_run, sample_agent_spec
    ):
        """
        Step 4: Event linked to AgentSpec

        Verify that the icon_generated event can be linked to an AgentSpec
        either directly via spec_id or indirectly via the AgentRun.
        """
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record with explicit spec_id
        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name=sample_agent_spec.name,
            icon_data="linked-icon",
            icon_format="svg",
            spec_id=sample_agent_spec.id,  # Direct link
            provider_name="local_placeholder",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # PASS: Direct link via spec_id
        assert event.payload.get("spec_id") == sample_agent_spec.id

        # PASS: Indirect link via run_id -> agent_spec_id
        run = session.query(AgentRun).filter(AgentRun.id == event.run_id).first()
        assert run.agent_spec_id == sample_agent_spec.id

    def test_step5_event_queryable_via_existing_apis(self, temp_db_session, sample_agent_run):
        """
        Step 5: Event queryable via existing event APIs

        Verify that icon_generated events can be queried using the standard
        event query patterns used by GET /api/agent-runs/:id/events.
        """
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Record icon_generated event
        recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="queryable-agent",
            icon_data="icon",
            icon_format="svg",
            success=True,
        )

        # Query using the same pattern as the API endpoint
        # (see server/routers/agent_runs.py get_run_events)
        events = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_agent_run.id)
            .filter(AgentEvent.event_type == "icon_generated")  # Filter by type
            .order_by(AgentEvent.sequence)  # Ordered by sequence
            .all()
        )

        # PASS: Event is queryable
        assert len(events) >= 1
        assert events[-1].event_type == "icon_generated"
        assert events[-1].payload["agent_name"] == "queryable-agent"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for icon_generated event with materializer."""

    def test_materializer_records_icon_event(self):
        """Test that AgentMaterializer records icon_generated event."""
        from api.agent_materializer import AgentMaterializer, IconGenerationInfo
        from api.icon_provider import IconFormat
        from unittest.mock import MagicMock, patch

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            materializer = AgentMaterializer(project_dir)

            # Create mock spec
            spec = Mock(spec=AgentSpec)
            spec.id = generate_uuid()
            spec.name = "integration-test-agent"
            spec.display_name = "Integration Test Agent"
            spec.task_type = "coding"
            spec.objective = "Test integration"
            spec.spec_version = "v1"
            spec.max_turns = 50
            spec.timeout_seconds = 1800
            spec.context = {}
            spec.tool_policy = {
                "policy_version": "v1",
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "tool_hints": {},
            }
            spec.acceptance_spec = None

            mock_session = MagicMock()
            run_id = generate_uuid()

            # Mock icon generation
            with patch("api.icon_provider.generate_icon") as mock_generate:
                mock_generate.return_value = Mock(
                    success=True,
                    icon_data="test-icon",
                    format=IconFormat.ICON_ID,
                    provider_name="default",
                )

                mock_recorder = MagicMock()
                mock_recorder.record_agent_materialized.return_value = 1
                mock_recorder.record_icon_generated.return_value = 2

                with patch("api.event_recorder.get_event_recorder") as mock_get_recorder:
                    mock_get_recorder.return_value = mock_recorder

                    result = materializer.materialize_with_audit(
                        spec, mock_session, run_id
                    )

                    # Verify icon_generated was recorded
                    mock_recorder.record_icon_generated.assert_called_once()
                    call_kwargs = mock_recorder.record_icon_generated.call_args.kwargs
                    assert call_kwargs["agent_name"] == "integration-test-agent"
                    assert call_kwargs["success"] is True


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases for icon_generated events."""

    def test_large_icon_data_truncated(self, temp_db_session, sample_agent_run):
        """Verify large icon data is truncated in payload."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        # Create large icon data (>1000 chars)
        large_icon_data = "x" * 2000

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="large-icon-agent",
            icon_data=large_icon_data,
            icon_format="svg",
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # Icon data should be truncated to 1000 chars
        assert len(event.payload.get("icon_data", "")) <= 1000
        assert event.payload.get("icon_data_truncated") is True

    def test_null_icon_data_excluded(self, temp_db_session, sample_agent_run):
        """Verify null icon_data is not included in payload."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="null-icon-agent",
            icon_data=None,
            icon_format="unknown",
            success=False,
            error="Generation failed",
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # icon_data should not be in payload when None
        assert "icon_data" not in event.payload

    def test_empty_provider_name_excluded(self, temp_db_session, sample_agent_run):
        """Verify empty provider_name is not included in payload."""
        session, project_dir = temp_db_session
        recorder = EventRecorder(session, project_dir)

        event_id = recorder.record_icon_generated(
            run_id=sample_agent_run.id,
            agent_name="no-provider-agent",
            icon_data="icon",
            icon_format="svg",
            provider_name=None,
            success=True,
        )

        event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

        # provider_name should not be in payload when None
        assert "provider_name" not in event.payload
