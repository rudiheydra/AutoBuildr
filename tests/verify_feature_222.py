#!/usr/bin/env python3
"""
Verification script for Feature #222: agent_materialized audit event type created

This script verifies all 5 steps of the feature are correctly implemented:
1. Add 'agent_materialized' to event_type enum
2. Event payload includes: agent_name, file_path, spec_hash
3. Event recorded after successful file write
4. Event linked to AgentSpec
5. Event queryable via existing event APIs

Run: python tests/verify_feature_222.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.agent_materializer import AgentMaterializer, MaterializationAuditInfo
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent, EVENT_TYPES, generate_uuid
from api.database import Base
from api.event_recorder import EventRecorder, get_event_recorder, clear_recorder_cache


def create_test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def create_test_spec():
    """Create test AgentSpec."""
    return AgentSpec(
        id=generate_uuid(),
        name="verify-feature-222-agent",
        display_name="Verify Feature 222 Agent",
        icon="check",
        spec_version="v1",
        objective="Verify feature 222 implementation",
        task_type="testing",
        context={"model": "sonnet"},
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=50,
        timeout_seconds=900,
        source_feature_id=222,
    )


def create_test_run(session, spec):
    """Create test AgentRun."""
    session.add(spec)
    session.flush()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="running",
    )
    session.add(run)
    session.commit()
    return run


def step1_event_type_enum():
    """Step 1: Add 'agent_materialized' to event_type enum."""
    print("\n--- Step 1: Add 'agent_materialized' to event_type enum ---")

    # Check 1: agent_materialized in EVENT_TYPES
    assert "agent_materialized" in EVENT_TYPES, "agent_materialized NOT in EVENT_TYPES"
    print(f"  ✓ 'agent_materialized' is in EVENT_TYPES (at index {EVENT_TYPES.index('agent_materialized')})")

    # Check 2: EventRecorder has convenience method
    assert hasattr(EventRecorder, "record_agent_materialized"), "EventRecorder missing record_agent_materialized"
    print("  ✓ EventRecorder has record_agent_materialized method")

    # Check 3: EventRecorder accepts the event type
    session = create_test_db()
    clear_recorder_cache()
    spec = create_test_spec()
    run = create_test_run(session, spec)

    recorder = get_event_recorder(session, "/tmp")
    event_id = recorder.record(
        run_id=run.id,
        event_type="agent_materialized",
        payload={"test": True},
    )
    assert event_id is not None and isinstance(event_id, int), "EventRecorder rejected agent_materialized"
    print(f"  ✓ EventRecorder accepts 'agent_materialized' event type (event_id={event_id})")

    session.close()
    clear_recorder_cache()
    print("  STEP 1: PASS")
    return True


def step2_event_payload():
    """Step 2: Event payload includes: agent_name, file_path, spec_hash."""
    print("\n--- Step 2: Event payload includes: agent_name, file_path, spec_hash ---")

    session = create_test_db()
    clear_recorder_cache()
    spec = create_test_spec()
    run = create_test_run(session, spec)

    recorder = get_event_recorder(session, "/tmp")

    # Record event with all required fields
    event_id = recorder.record_agent_materialized(
        run_id=run.id,
        agent_name="test-agent-222",
        file_path="/path/to/agent.md",
        spec_hash="a" * 64,
    )

    event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

    # Verify all required fields present
    assert "agent_name" in event.payload, "Missing agent_name in payload"
    print(f"  ✓ Payload contains 'agent_name': {event.payload['agent_name']}")

    assert "file_path" in event.payload, "Missing file_path in payload"
    print(f"  ✓ Payload contains 'file_path': {event.payload['file_path']}")

    assert "spec_hash" in event.payload, "Missing spec_hash in payload"
    print(f"  ✓ Payload contains 'spec_hash': {event.payload['spec_hash'][:16]}...")

    # Verify values are correct
    assert event.payload["agent_name"] == "test-agent-222"
    assert event.payload["file_path"] == "/path/to/agent.md"
    assert event.payload["spec_hash"] == "a" * 64

    session.close()
    clear_recorder_cache()
    print("  STEP 2: PASS")
    return True


def step3_event_after_file_write():
    """Step 3: Event recorded after successful file write."""
    print("\n--- Step 3: Event recorded after successful file write ---")

    session = create_test_db()
    clear_recorder_cache()
    spec = create_test_spec()
    run = create_test_run(session, spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        # Materialize with audit
        result = materializer.materialize_with_audit(
            spec=spec,
            session=session,
            run_id=run.id,
        )

        # Verify file was written
        assert result.success, f"Materialization failed: {result.error}"
        assert result.file_path.exists(), "File was not created"
        print(f"  ✓ File written successfully: {result.file_path.name}")

        # Verify event was recorded
        assert result.audit_info is not None, "No audit_info returned"
        assert result.audit_info.recorded, "Audit event not recorded"
        assert result.audit_info.event_id is not None, "No event_id"
        print(f"  ✓ Audit event recorded: event_id={result.audit_info.event_id}")

        # Verify file content matches spec_hash
        file_content = result.file_path.read_text(encoding="utf-8")
        computed_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()
        assert result.content_hash == computed_hash, "Content hash mismatch"
        print(f"  ✓ Content hash verified: {computed_hash[:16]}...")

    session.close()
    clear_recorder_cache()
    print("  STEP 3: PASS")
    return True


def step4_event_linked_to_spec():
    """Step 4: Event linked to AgentSpec."""
    print("\n--- Step 4: Event linked to AgentSpec ---")

    session = create_test_db()
    clear_recorder_cache()
    spec = create_test_spec()
    run = create_test_run(session, spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        result = materializer.materialize_with_audit(
            spec=spec,
            session=session,
            run_id=run.id,
        )

        # Get the event
        event = session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        # Verify spec_id is in payload
        assert "spec_id" in event.payload, "spec_id not in payload"
        assert event.payload["spec_id"] == spec.id, "spec_id doesn't match"
        print(f"  ✓ Event contains spec_id: {spec.id[:16]}...")

        # Verify we can query spec from event
        queried_spec = session.query(AgentSpec).filter(
            AgentSpec.id == event.payload["spec_id"]
        ).first()
        assert queried_spec is not None, "Could not query spec from event"
        assert queried_spec.name == spec.name, "Queried spec name doesn't match"
        print(f"  ✓ Can query AgentSpec from event: {queried_spec.name}")

        # Verify agent_name matches
        assert event.payload["agent_name"] == spec.name, "agent_name doesn't match spec.name"
        print(f"  ✓ agent_name matches spec.name: {spec.name}")

    session.close()
    clear_recorder_cache()
    print("  STEP 4: PASS")
    return True


def step5_event_queryable():
    """Step 5: Event queryable via existing event APIs."""
    print("\n--- Step 5: Event queryable via existing event APIs ---")

    session = create_test_db()
    clear_recorder_cache()
    spec = create_test_spec()
    run = create_test_run(session, spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        result = materializer.materialize_with_audit(
            spec=spec,
            session=session,
            run_id=run.id,
        )

        # Query by run_id
        events_by_run = session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id
        ).all()
        assert len(events_by_run) >= 1, "No events found for run_id"
        print(f"  ✓ Events queryable by run_id: {len(events_by_run)} event(s)")

        # Filter by event_type
        materialized_events = session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "agent_materialized",
        ).all()
        assert len(materialized_events) >= 1, "No agent_materialized events found"
        print(f"  ✓ Events filterable by event_type='agent_materialized': {len(materialized_events)} event(s)")

        # Verify event is in agent_events table
        event = materialized_events[0]
        assert event.__tablename__ == "agent_events", "Event not in agent_events table"
        print(f"  ✓ Event persisted to 'agent_events' table")

        # Verify sequence number exists
        assert event.sequence >= 1, "Event missing sequence number"
        print(f"  ✓ Event has sequence number: {event.sequence}")

        # Verify timestamp exists
        assert event.timestamp is not None, "Event missing timestamp"
        print(f"  ✓ Event has timestamp: {event.timestamp}")

    session.close()
    clear_recorder_cache()
    print("  STEP 5: PASS")
    return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #222: agent_materialized audit event type created")
    print("=" * 60)

    results = []

    try:
        results.append(("Step 1: Event type enum", step1_event_type_enum()))
    except Exception as e:
        print(f"  STEP 1: FAIL - {e}")
        results.append(("Step 1: Event type enum", False))

    try:
        results.append(("Step 2: Event payload", step2_event_payload()))
    except Exception as e:
        print(f"  STEP 2: FAIL - {e}")
        results.append(("Step 2: Event payload", False))

    try:
        results.append(("Step 3: Event after file write", step3_event_after_file_write()))
    except Exception as e:
        print(f"  STEP 3: FAIL - {e}")
        results.append(("Step 3: Event after file write", False))

    try:
        results.append(("Step 4: Event linked to spec", step4_event_linked_to_spec()))
    except Exception as e:
        print(f"  STEP 4: FAIL - {e}")
        results.append(("Step 4: Event linked to spec", False))

    try:
        results.append(("Step 5: Event queryable", step5_event_queryable()))
    except Exception as e:
        print(f"  STEP 5: FAIL - {e}")
        results.append(("Step 5: Event queryable", False))

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for step_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {step_name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("OVERALL RESULT: ALL STEPS PASS ✓")
        print("Feature #222 is correctly implemented.")
    else:
        print("OVERALL RESULT: SOME STEPS FAILED ✗")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
