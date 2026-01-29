"""
Tests for Feature #150: Fix kernel payload truncation to create artifact references
===================================================================================

Verifies that the HarnessKernel creates Artifact records and sets artifact_ref
on AgentEvent when truncating payloads exceeding 4KB, instead of losing data.

Test categories:
1. _create_payload_artifact helper method
2. _record_tool_call_event with large payloads
3. _record_tool_result_event with large payloads
4. Small payloads remain unchanged (no artifact created)
5. Artifact content is retrievable
6. End-to-end integration test
"""

import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    Artifact,
    EVENT_PAYLOAD_MAX_SIZE,
)
from api.harness_kernel import HarnessKernel


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
        id="feat150-spec-001",
        name="feat150-test-spec",
        display_name="Feature 150 Test Spec",
        objective="Test kernel payload truncation artifact creation",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read", "Write", "Bash"]},
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
        id="feat150-run-001",
        agent_spec_id=sample_spec.id,
        status="running",
        turns_used=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture
def kernel(db_session):
    """Create a HarnessKernel instance."""
    return HarnessKernel(db=db_session)


def _make_large_payload_args(size_chars: int = 5000) -> dict:
    """Create arguments dict that exceeds EVENT_PAYLOAD_MAX_SIZE when serialized."""
    # The full payload includes {"tool": "...", "arguments": {...}}
    # so we need the arguments to push the total over 4096
    large_data = "x" * size_chars
    return {"file_content": large_data, "path": "/tmp/test.txt"}


def _make_large_result(size_chars: int = 5000) -> str:
    """Create a result string that exceeds EVENT_PAYLOAD_MAX_SIZE when serialized."""
    return "output_line_" * (size_chars // 12)


# =============================================================================
# Step 1: Locate the kernel code that handles event payload truncation
# =============================================================================

class TestKernelTruncationCodeExists:
    """Verify the kernel has truncation handling in the right places."""

    def test_record_tool_call_event_method_exists(self, kernel):
        """_record_tool_call_event method exists on HarnessKernel."""
        assert hasattr(kernel, '_record_tool_call_event')
        assert callable(kernel._record_tool_call_event)

    def test_record_tool_result_event_method_exists(self, kernel):
        """_record_tool_result_event method exists on HarnessKernel."""
        assert hasattr(kernel, '_record_tool_result_event')
        assert callable(kernel._record_tool_result_event)

    def test_create_payload_artifact_method_exists(self, kernel):
        """Feature #150: _create_payload_artifact helper method exists."""
        assert hasattr(kernel, '_create_payload_artifact')
        assert callable(kernel._create_payload_artifact)


# =============================================================================
# Step 2: Identify where payloads over 4KB are truncated
# =============================================================================

class TestPayloadTruncationThreshold:
    """Verify the 4KB threshold is correctly applied."""

    def test_event_payload_max_size_is_4096(self):
        """EVENT_PAYLOAD_MAX_SIZE constant equals 4096."""
        assert EVENT_PAYLOAD_MAX_SIZE == 4096

    def test_small_tool_call_not_truncated(self, kernel, db_session, sample_run):
        """Tool call with small arguments is NOT truncated."""
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Read",
            arguments={"path": "/tmp/small.txt"},
        )
        db_session.flush()

        assert event.payload_truncated is None
        assert event.artifact_ref is None
        assert event.payload["arguments"]["path"] == "/tmp/small.txt"

    def test_small_tool_result_not_truncated(self, kernel, db_session, sample_run):
        """Tool result with small content is NOT truncated."""
        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Read",
            result="Hello, world!",
        )
        db_session.flush()

        assert event.payload_truncated is None
        assert event.artifact_ref is None
        assert event.payload["result"] == "Hello, world!"

    def test_large_tool_call_is_truncated(self, kernel, db_session, sample_run):
        """Tool call with large arguments IS truncated."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        assert event.payload_truncated is not None
        assert event.payload_truncated > 4096
        assert event.payload["arguments"]["_truncated"] is True

    def test_large_tool_result_is_truncated(self, kernel, db_session, sample_run):
        """Tool result with large content IS truncated."""
        large_result = _make_large_result(5000)
        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=large_result,
        )
        db_session.flush()

        assert event.payload_truncated is not None
        assert event.payload_truncated > 4096
        assert event.payload["result"]["_truncated"] is True


# =============================================================================
# Step 3: Modify the truncation logic to create an Artifact record
# =============================================================================

class TestArtifactCreationOnTruncation:
    """Verify that Artifact records are created when payloads are truncated."""

    def test_tool_call_creates_artifact(self, kernel, db_session, sample_run):
        """Large tool_call payload creates an Artifact record."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        # Artifact should exist
        artifact = db_session.query(Artifact).filter_by(run_id=sample_run.id).first()
        assert artifact is not None
        assert artifact.artifact_type == "log"
        assert artifact.size_bytes > 0
        assert len(artifact.content_hash) == 64  # SHA256 hex digest

    def test_tool_result_creates_artifact(self, kernel, db_session, sample_run):
        """Large tool_result payload creates an Artifact record."""
        large_result = _make_large_result(5000)
        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=large_result,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).filter_by(run_id=sample_run.id).first()
        assert artifact is not None
        assert artifact.artifact_type == "log"
        assert artifact.size_bytes > 0

    def test_artifact_has_correct_run_id(self, kernel, db_session, sample_run):
        """Artifact run_id matches the event's run_id."""
        large_args = _make_large_payload_args(5000)
        kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).first()
        assert artifact.run_id == sample_run.id

    def test_artifact_has_content_hash(self, kernel, db_session, sample_run):
        """Artifact content_hash is a valid SHA256 hex digest."""
        large_args = _make_large_payload_args(5000)
        kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).first()
        assert artifact.content_hash is not None
        assert len(artifact.content_hash) == 64
        # Verify it's valid hex
        int(artifact.content_hash, 16)

    def test_artifact_metadata_includes_event_info(self, kernel, db_session, sample_run):
        """Artifact metadata includes event_sequence, event_type, source."""
        large_args = _make_large_payload_args(5000)
        kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).first()
        meta = artifact.artifact_metadata
        assert meta is not None
        assert "event_sequence" in meta
        assert meta["event_type"] == "tool_call"
        assert meta["content_type"] == "application/json"
        assert meta["source"] == "kernel_truncation"

    def test_no_artifact_for_small_payload(self, kernel, db_session, sample_run):
        """Small payloads do NOT create artifacts."""
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Read",
            arguments={"path": "/tmp/small.txt"},
        )
        db_session.flush()

        artifacts = db_session.query(Artifact).filter_by(run_id=sample_run.id).all()
        assert len(artifacts) == 0


# =============================================================================
# Step 4: Store the artifact reference on the AgentEvent
# =============================================================================

class TestArtifactRefOnEvent:
    """Verify that artifact_ref is set on the AgentEvent."""

    def test_tool_call_event_has_artifact_ref(self, kernel, db_session, sample_run):
        """Large tool_call event has artifact_ref set."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        assert event.artifact_ref is not None
        # Verify artifact_ref points to a real artifact
        artifact = db_session.query(Artifact).get(event.artifact_ref)
        assert artifact is not None

    def test_tool_result_event_has_artifact_ref(self, kernel, db_session, sample_run):
        """Large tool_result event has artifact_ref set."""
        large_result = _make_large_result(5000)
        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=large_result,
        )
        db_session.flush()

        assert event.artifact_ref is not None
        artifact = db_session.query(Artifact).get(event.artifact_ref)
        assert artifact is not None

    def test_artifact_ref_matches_artifact_id(self, kernel, db_session, sample_run):
        """event.artifact_ref exactly matches the created artifact.id."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).filter_by(run_id=sample_run.id).first()
        assert event.artifact_ref == artifact.id

    def test_small_payload_no_artifact_ref(self, kernel, db_session, sample_run):
        """Small payload event has artifact_ref = None."""
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Read",
            arguments={"path": "/small"},
        )
        db_session.flush()

        assert event.artifact_ref is None


# =============================================================================
# Step 5: Truncated payload includes note about artifact
# =============================================================================

class TestTruncatedPayloadNote:
    """Verify that truncated payloads include a note about the artifact."""

    def test_tool_call_truncated_has_artifact_ref_in_payload(self, kernel, db_session, sample_run):
        """Truncated tool_call payload includes _artifact_ref field."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        args = event.payload["arguments"]
        assert args["_truncated"] is True
        assert "_artifact_ref" in args
        assert args["_artifact_ref"] == event.artifact_ref

    def test_tool_call_truncated_has_note(self, kernel, db_session, sample_run):
        """Truncated tool_call payload includes _note about artifact."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        args = event.payload["arguments"]
        assert "_note" in args
        assert "artifact" in args["_note"].lower()

    def test_tool_result_truncated_has_artifact_ref_in_payload(self, kernel, db_session, sample_run):
        """Truncated tool_result payload includes _artifact_ref field."""
        large_result = _make_large_result(5000)
        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=large_result,
        )
        db_session.flush()

        result = event.payload["result"]
        assert result["_truncated"] is True
        assert "_artifact_ref" in result
        assert result["_artifact_ref"] == event.artifact_ref

    def test_tool_result_truncated_has_note(self, kernel, db_session, sample_run):
        """Truncated tool_result payload includes _note about artifact."""
        large_result = _make_large_result(5000)
        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=large_result,
        )
        db_session.flush()

        result = event.payload["result"]
        assert "_note" in result
        assert "artifact" in result["_note"].lower()


# =============================================================================
# Step 6: Verify full content is retrievable via the artifact
# =============================================================================

class TestArtifactContentRetrieval:
    """Verify that the full payload content is stored and retrievable."""

    def test_tool_call_full_content_in_artifact(self, kernel, db_session, sample_run):
        """Full tool_call payload is stored in artifact content_inline."""
        large_args = _make_large_payload_args(5000)
        original_payload = {
            "tool": "Write",
            "arguments": large_args,
        }
        original_json = json.dumps(original_payload, default=str)

        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).get(event.artifact_ref)
        assert artifact.content_inline is not None
        assert artifact.content_inline == original_json

    def test_tool_result_full_content_in_artifact(self, kernel, db_session, sample_run):
        """Full tool_result payload is stored in artifact content_inline."""
        large_result = _make_large_result(5000)

        event = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=large_result,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).get(event.artifact_ref)
        assert artifact.content_inline is not None

        # Parse the stored content and verify it matches
        stored_payload = json.loads(artifact.content_inline)
        assert stored_payload["tool"] == "Bash"
        assert stored_payload["result"] == large_result
        assert stored_payload["is_error"] is False

    def test_artifact_content_hash_matches(self, kernel, db_session, sample_run):
        """Artifact content_hash matches SHA256 of the stored content."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).get(event.artifact_ref)
        expected_hash = hashlib.sha256(artifact.content_inline.encode("utf-8")).hexdigest()
        assert artifact.content_hash == expected_hash

    def test_artifact_size_bytes_correct(self, kernel, db_session, sample_run):
        """Artifact size_bytes matches actual content size."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        artifact = db_session.query(Artifact).get(event.artifact_ref)
        expected_size = len(artifact.content_inline.encode("utf-8"))
        assert artifact.size_bytes == expected_size


# =============================================================================
# Step 7: End-to-end integration - multiple large events
# =============================================================================

class TestEndToEndIntegration:
    """Integration tests for the full truncation → artifact → reference flow."""

    def test_multiple_large_events_create_separate_artifacts(self, kernel, db_session, sample_run):
        """Each large event creates its own artifact."""
        # First large tool_call
        event1 = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=_make_large_payload_args(5000),
        )
        # Second large tool_result
        event2 = kernel._record_tool_result_event(
            run_id=sample_run.id,
            tool_name="Bash",
            result=_make_large_result(5000),
        )
        db_session.flush()

        artifacts = db_session.query(Artifact).filter_by(run_id=sample_run.id).all()
        assert len(artifacts) == 2

        # Each event references a different artifact
        assert event1.artifact_ref != event2.artifact_ref
        artifact_ids = {a.id for a in artifacts}
        assert event1.artifact_ref in artifact_ids
        assert event2.artifact_ref in artifact_ids

    def test_mixed_small_and_large_events(self, kernel, db_session, sample_run):
        """Mix of small and large events: only large ones create artifacts."""
        # Small event (no artifact)
        event_small = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Read",
            arguments={"path": "/small.txt"},
        )
        # Large event (creates artifact)
        event_large = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=_make_large_payload_args(5000),
        )
        db_session.flush()

        assert event_small.artifact_ref is None
        assert event_large.artifact_ref is not None

        artifacts = db_session.query(Artifact).filter_by(run_id=sample_run.id).all()
        assert len(artifacts) == 1
        assert artifacts[0].id == event_large.artifact_ref

    def test_artifact_relationship_navigable(self, kernel, db_session, sample_run):
        """Can navigate from event → artifact via relationship."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        # Refresh to load relationships
        db_session.refresh(event)

        # The event.artifact relationship should be navigable
        assert event.artifact is not None
        assert event.artifact.id == event.artifact_ref
        assert event.artifact.artifact_type == "log"

    def test_payload_truncated_field_set(self, kernel, db_session, sample_run):
        """payload_truncated is set to original size for large payloads."""
        large_args = _make_large_payload_args(5000)
        original_payload = {"tool": "Write", "arguments": large_args}
        original_size = len(json.dumps(original_payload, default=str))

        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        assert event.payload_truncated == original_size
        assert event.payload_truncated > 4096

    def test_original_size_in_truncated_payload(self, kernel, db_session, sample_run):
        """Truncated payload includes _original_size matching payload_truncated."""
        large_args = _make_large_payload_args(5000)
        event = kernel._record_tool_call_event(
            run_id=sample_run.id,
            tool_name="Write",
            arguments=large_args,
        )
        db_session.flush()

        assert event.payload["arguments"]["_original_size"] == event.payload_truncated
