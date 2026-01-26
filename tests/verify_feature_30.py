#!/usr/bin/env python3
"""
Verification script for Feature #30: AgentEvent Recording Service
===================================================================

This script verifies all 9 steps of the feature implementation.

Steps:
1. Create EventRecorder class with record(run_id, event_type, payload) method
2. Maintain sequence counter per run (start at 1)
3. Check payload size against EVENT_PAYLOAD_MAX_SIZE (4096 chars)
4. If payload exceeds limit, create Artifact and set artifact_ref
5. Truncate payload and set payload_truncated to original size
6. Set timestamp to current UTC time
7. Create AgentEvent record with all fields
8. Commit immediately for durability
9. Return created event ID
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_header(title: str):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_step(step_num: int, description: str):
    """Print a step header."""
    print(f"\n[Step {step_num}] {description}")
    print("-" * 50)


def print_check(name: str, passed: bool, details: str = ""):
    """Print a check result."""
    status = "PASS" if passed else "FAIL"
    icon = "[+]" if passed else "[-]"
    print(f"  {icon} {name}: {status}")
    if details:
        print(f"      {details}")
    return passed


def verify_step1():
    """Step 1: Create EventRecorder class with record(run_id, event_type, payload) method."""
    print_step(1, "EventRecorder class with record(run_id, event_type, payload) method")

    passed = True

    # Check class exists
    try:
        from api.event_recorder import EventRecorder
        passed &= print_check("EventRecorder class exists", True)
    except ImportError as e:
        passed &= print_check("EventRecorder class exists", False, str(e))
        return passed

    # Check record method exists
    passed &= print_check("record method exists", hasattr(EventRecorder, "record"))

    # Check record method signature
    import inspect
    sig = inspect.signature(EventRecorder.record)
    params = list(sig.parameters.keys())
    passed &= print_check("run_id parameter", "run_id" in params)
    passed &= print_check("event_type parameter", "event_type" in params)
    passed &= print_check("payload parameter", "payload" in params)

    return passed


def verify_step2():
    """Step 2: Maintain sequence counter per run (start at 1)."""
    print_step(2, "Sequence counter per run (start at 1)")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        passed = True

        try:
            # Create spec and run
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)

            # Record first event
            event_id1 = recorder.record(run.id, "started")
            event1 = session.query(AgentEvent).filter(AgentEvent.id == event_id1).first()
            passed &= print_check(
                "First event sequence is 1",
                event1.sequence == 1,
                f"Actual: {event1.sequence}"
            )

            # Record second event
            event_id2 = recorder.record(run.id, "tool_call", payload={"tool": "test"})
            event2 = session.query(AgentEvent).filter(AgentEvent.id == event_id2).first()
            passed &= print_check(
                "Second event sequence is 2",
                event2.sequence == 2,
                f"Actual: {event2.sequence}"
            )

        finally:
            session.close()
            engine.dispose()

    return passed


def verify_step3():
    """Step 3: Check payload size against EVENT_PAYLOAD_MAX_SIZE (4096 chars)."""
    print_step(3, "Payload size check against EVENT_PAYLOAD_MAX_SIZE (4096 chars)")

    passed = True

    from api.agentspec_models import EVENT_PAYLOAD_MAX_SIZE
    passed &= print_check(
        "EVENT_PAYLOAD_MAX_SIZE is 4096",
        EVENT_PAYLOAD_MAX_SIZE == 4096,
        f"Actual: {EVENT_PAYLOAD_MAX_SIZE}"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)

            # Small payload - no truncation
            small_payload = {"msg": "a" * 100}
            event_id1 = recorder.record(run.id, "started", payload=small_payload)
            event1 = session.query(AgentEvent).filter(AgentEvent.id == event_id1).first()
            passed &= print_check(
                "Small payload not truncated",
                event1.payload_truncated is None,
                f"payload_truncated: {event1.payload_truncated}"
            )

            # Large payload - truncation
            large_payload = {"msg": "b" * 5000}
            event_id2 = recorder.record(run.id, "tool_call", payload=large_payload)
            event2 = session.query(AgentEvent).filter(AgentEvent.id == event_id2).first()
            passed &= print_check(
                "Large payload truncated",
                event2.payload_truncated is not None,
                f"payload_truncated: {event2.payload_truncated}"
            )

        finally:
            session.close()
            engine.dispose()

    return passed


def verify_step4():
    """Step 4: If payload exceeds limit, create Artifact and set artifact_ref."""
    print_step(4, "Large payload creates Artifact with artifact_ref")

    passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, Artifact, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)

            # Large payload - should create artifact
            large_payload = {"data": "x" * 5000}
            event_id = recorder.record(run.id, "tool_result", payload=large_payload)
            event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

            passed &= print_check(
                "artifact_ref is set",
                event.artifact_ref is not None,
                f"artifact_ref: {event.artifact_ref}"
            )

            if event.artifact_ref:
                artifact = session.query(Artifact).filter(
                    Artifact.id == event.artifact_ref
                ).first()
                passed &= print_check(
                    "Artifact exists in database",
                    artifact is not None,
                    f"artifact_id: {artifact.id if artifact else None}"
                )
                if artifact:
                    passed &= print_check(
                        "Artifact type is 'log'",
                        artifact.artifact_type == "log",
                        f"Actual: {artifact.artifact_type}"
                    )

        finally:
            session.close()
            engine.dispose()

    return passed


def verify_step5():
    """Step 5: Truncate payload and set payload_truncated to original size."""
    print_step(5, "Truncate payload and set payload_truncated to original size")

    passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)

            # Create large payload
            large_data = "x" * 5000
            large_payload = {"data": large_data}
            original_size = len(json.dumps(large_payload))

            event_id = recorder.record(run.id, "tool_result", payload=large_payload)
            event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

            passed &= print_check(
                "payload_truncated equals original size",
                event.payload_truncated == original_size,
                f"Expected: {original_size}, Actual: {event.payload_truncated}"
            )

            passed &= print_check(
                "Truncated payload has _truncated flag",
                event.payload.get("_truncated") is True,
                f"_truncated: {event.payload.get('_truncated')}"
            )

            passed &= print_check(
                "Truncated payload has _original_size",
                event.payload.get("_original_size") == original_size,
                f"_original_size: {event.payload.get('_original_size')}"
            )

        finally:
            session.close()
            engine.dispose()

    return passed


def verify_step6():
    """Step 6: Set timestamp to current UTC time."""
    print_step(6, "Timestamp set to current UTC time")

    passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)

            before = datetime.now(timezone.utc)
            event_id = recorder.record(run.id, "started")
            after = datetime.now(timezone.utc)

            event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

            passed &= print_check(
                "Timestamp is not None",
                event.timestamp is not None,
                f"timestamp: {event.timestamp}"
            )

            if event.timestamp:
                ts = event.timestamp.replace(tzinfo=timezone.utc)
                passed &= print_check(
                    "Timestamp is between before and after",
                    before <= ts <= after,
                    f"before: {before}, timestamp: {ts}, after: {after}"
                )

        finally:
            session.close()
            engine.dispose()

    return passed


def verify_step7():
    """Step 7: Create AgentEvent record with all fields."""
    print_step(7, "AgentEvent record with all fields")

    passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)

            payload = {"args": "test"}
            event_id = recorder.record(
                run.id,
                "tool_call",
                payload=payload,
                tool_name="bash"
            )

            event = session.query(AgentEvent).filter(AgentEvent.id == event_id).first()

            passed &= print_check("id is set", event.id is not None, f"id: {event.id}")
            passed &= print_check("run_id matches", event.run_id == run.id)
            passed &= print_check("event_type is 'tool_call'", event.event_type == "tool_call")
            passed &= print_check("sequence >= 1", event.sequence >= 1, f"sequence: {event.sequence}")
            passed &= print_check("timestamp is set", event.timestamp is not None)
            passed &= print_check("payload is set", event.payload is not None)
            passed &= print_check("tool_name is 'bash'", event.tool_name == "bash")

        finally:
            session.close()
            engine.dispose()

    return passed


def verify_step8():
    """Step 8: Commit immediately for durability."""
    print_step(8, "Commit immediately for durability")

    passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        # Session 1: Create spec and run
        session1 = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session1.add(spec)
            session1.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session1.add(run)
            session1.commit()
            run_id = run.id
        finally:
            session1.close()

        # Session 2: Record event
        session2 = SessionLocal()
        try:
            recorder = EventRecorder(session2, project_dir)
            event_id = recorder.record(run_id, "started")
        finally:
            session2.close()

        # Session 3: Verify event persisted
        session3 = SessionLocal()
        try:
            event = session3.query(AgentEvent).filter(
                AgentEvent.id == event_id
            ).first()
            passed &= print_check(
                "Event persisted in new session",
                event is not None,
                f"event_id: {event_id}"
            )
        finally:
            session3.close()
            engine.dispose()

    return passed


def verify_step9():
    """Step 9: Return created event ID."""
    print_step(9, "Return created event ID")

    passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        from api.database import create_database, set_session_maker
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, generate_uuid
        from api.event_recorder import EventRecorder, clear_recorder_cache

        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        clear_recorder_cache()

        session = SessionLocal()
        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name="test-spec",
                display_name="Test",
                objective="Test",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            recorder = EventRecorder(session, project_dir)
            result = recorder.record(run.id, "started", payload={"test": True})

            passed &= print_check(
                "Return value is integer",
                isinstance(result, int),
                f"type: {type(result).__name__}"
            )
            passed &= print_check(
                "Return value is positive",
                result > 0,
                f"value: {result}"
            )

            # Use returned ID to retrieve event
            event = session.query(AgentEvent).filter(AgentEvent.id == result).first()
            passed &= print_check(
                "Returned ID can retrieve event",
                event is not None,
                f"event.id: {event.id if event else None}"
            )

        finally:
            session.close()
            engine.dispose()

    return passed


def main():
    """Run all verification steps."""
    print_header("Feature #30: AgentEvent Recording Service Verification")

    all_passed = True

    all_passed &= verify_step1()
    all_passed &= verify_step2()
    all_passed &= verify_step3()
    all_passed &= verify_step4()
    all_passed &= verify_step5()
    all_passed &= verify_step6()
    all_passed &= verify_step7()
    all_passed &= verify_step8()
    all_passed &= verify_step9()

    # Summary
    print_header("VERIFICATION SUMMARY")
    if all_passed:
        print("All verification steps PASSED!")
        print("\nFeature #30 is ready to be marked as passing.")
        return 0
    else:
        print("Some verification steps FAILED.")
        print("\nPlease fix the failing steps before marking as passing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
