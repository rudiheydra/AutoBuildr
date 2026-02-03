#!/usr/bin/env python3
"""
Verification Script for Feature #227: Audit Events Support Replay and Debugging
=================================================================================

This script verifies all 4 feature steps:
1. Events include full context needed for replay
2. Large payloads stored as artifacts with references
3. Event sequence reconstructable from run_id + sequence
4. Events support debugging failed agent runs
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import create_database, set_session_maker
from api.agentspec_models import AgentRun, AgentSpec, generate_uuid
from api.event_recorder import EventRecorder
from api.event_replay import (
    get_replay_context,
    reconstruct_run_events,
    get_run_debug_context,
    verify_event_sequence_integrity,
)


def verify_step1_full_context():
    """Step 1: Events include full context needed for replay."""
    print("\n=== Step 1: Events include full context needed for replay ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        session = SessionLocal()

        try:
            # Create spec and run
            spec = AgentSpec(
                id=generate_uuid(),
                name="verify-227-spec",
                display_name="Verification Spec",
                objective="Test objective",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            # Record events with context
            recorder = EventRecorder(session, project_dir)
            recorder.record_started(run.id, objective="Complete verification task")
            recorder.record_tool_call(run.id, "bash", {"command": "ls -la", "timeout": 30})
            recorder.record_tool_result(
                run.id, "bash",
                result={"output": "file1.txt\nfile2.txt", "exit_code": 0},
                success=True,
            )

            # Verify context via replay
            context = get_replay_context(session, project_dir, run.id)
            events = list(context.get_events())

            # Check started has objective
            started = next(e for e in events if e.event_type == "started")
            assert started.full_payload.get("objective") == "Complete verification task", \
                "Started event should have objective"

            # Check tool_call has arguments
            tool_call = next(e for e in events if e.event_type == "tool_call")
            assert "command" in tool_call.full_payload.get("arguments", {}), \
                "Tool call should have arguments"

            # Check tool_result has result
            tool_result = next(e for e in events if e.event_type == "tool_result")
            assert "output" in tool_result.full_payload.get("result", {}), \
                "Tool result should have result data"

            print("PASS - All events include full context for replay")
            return True

        except Exception as e:
            print(f"FAIL - {e}")
            return False
        finally:
            session.close()
            engine.dispose()


def verify_step2_large_payloads_artifacts():
    """Step 2: Large payloads stored as artifacts with references."""
    print("\n=== Step 2: Large payloads stored as artifacts with references ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        session = SessionLocal()

        try:
            # Create spec and run
            spec = AgentSpec(
                id=generate_uuid(),
                name="verify-227-spec-2",
                display_name="Verification Spec 2",
                objective="Test objective",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="running")
            session.add(run)
            session.commit()

            # Record event with large payload (exceeds 4096 char limit)
            recorder = EventRecorder(session, project_dir)
            large_content = "x" * 6000
            recorder.record_tool_result(
                run.id, "read",
                result={"content": large_content, "path": "/large/file.txt"},
                success=True,
            )

            # Verify via replay context
            context = get_replay_context(session, project_dir, run.id)
            events = list(context.get_events())

            event = events[0]
            assert event.was_truncated is True, "Large payload should be marked as truncated"
            assert event.artifact_ref is not None, "Should have artifact reference"
            assert len(event.full_payload["result"]["content"]) == 6000, \
                "Full payload should be retrievable"

            print("PASS - Large payloads stored as artifacts with references")
            return True

        except Exception as e:
            print(f"FAIL - {e}")
            return False
        finally:
            session.close()
            engine.dispose()


def verify_step3_sequence_reconstruction():
    """Step 3: Event sequence reconstructable from run_id + sequence."""
    print("\n=== Step 3: Event sequence reconstructable from run_id + sequence ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        session = SessionLocal()

        try:
            # Create spec and run
            spec = AgentSpec(
                id=generate_uuid(),
                name="verify-227-spec-3",
                display_name="Verification Spec 3",
                objective="Test objective",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(id=generate_uuid(), agent_spec_id=spec.id, status="completed")
            session.add(run)
            session.commit()

            # Record sequence of events
            recorder = EventRecorder(session, project_dir)
            recorder.record(run.id, "started", payload={"order": 1})
            recorder.record(run.id, "tool_call", payload={"order": 2})
            recorder.record(run.id, "tool_result", payload={"order": 3})
            recorder.record(run.id, "turn_complete", payload={"order": 4})
            recorder.record(run.id, "completed", payload={"order": 5})

            # Reconstruct sequence
            events = reconstruct_run_events(session, project_dir, run.id)

            # Verify sequence starts at 1
            assert events[0]["sequence"] == 1, "Sequence should start at 1"

            # Verify sequential order
            for i, event in enumerate(events):
                assert event["sequence"] == i + 1, f"Event {i} should have sequence {i+1}"

            # Verify integrity
            integrity = verify_event_sequence_integrity(session, run.id)
            assert integrity["is_valid"] is True, "Sequence integrity should be valid"
            assert integrity["gaps"] == [], "Should have no gaps"

            print("PASS - Event sequence reconstructable from run_id + sequence")
            return True

        except Exception as e:
            print(f"FAIL - {e}")
            return False
        finally:
            session.close()
            engine.dispose()


def verify_step4_debugging_support():
    """Step 4: Events support debugging failed agent runs."""
    print("\n=== Step 4: Events support debugging failed agent runs ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)
        set_session_maker(SessionLocal)
        session = SessionLocal()

        try:
            # Create spec and failed run
            spec = AgentSpec(
                id=generate_uuid(),
                name="verify-227-spec-4",
                display_name="Verification Spec 4",
                objective="Test objective",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": []},
            )
            session.add(spec)
            session.commit()

            run = AgentRun(
                id=generate_uuid(),
                agent_spec_id=spec.id,
                status="failed",
                error="API connection failed",
                turns_used=3,
                tokens_in=1500,
                tokens_out=800,
            )
            session.add(run)
            session.commit()

            # Record events leading to failure
            recorder = EventRecorder(session, project_dir)
            recorder.record_started(run.id, objective="Call external API")
            recorder.record_tool_call(run.id, "http_request", {"url": "https://api.example.com"})
            recorder.record_tool_result(
                run.id, "http_request",
                result=None,
                success=False,
                error="Connection timeout",
            )
            recorder.record_failed(run.id, error="API connection failed")

            # Get debug context
            debug = get_run_debug_context(session, project_dir, run.id)

            assert debug is not None, "Debug context should be available for failed runs"
            assert debug.run_status == "failed", "Should show failed status"
            assert debug.failure_reason is not None, "Should have failure reason"
            assert debug.last_tool_call is not None, "Should have last tool call"
            assert debug.last_tool_call.tool_name == "http_request", "Should identify failing tool"
            assert debug.last_tool_result is not None, "Should have last tool result"
            assert debug.turns_used == 3, "Should track turns used"
            assert debug.tokens_used == 2300, "Should track tokens used (1500 + 800)"

            print("PASS - Events support debugging failed agent runs")
            return True

        except Exception as e:
            print(f"FAIL - {e}")
            return False
        finally:
            session.close()
            engine.dispose()


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #227: Audit Events Support Replay and Debugging - Verification")
    print("=" * 70)

    results = []

    # Run all steps
    results.append(("Step 1: Full context for replay", verify_step1_full_context()))
    results.append(("Step 2: Large payloads as artifacts", verify_step2_large_payloads_artifacts()))
    results.append(("Step 3: Sequence reconstruction", verify_step3_sequence_reconstruction()))
    results.append(("Step 4: Debugging support", verify_step4_debugging_support()))

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    all_passed = True
    for step_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {step_name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED!")
        print("Feature #227 is ready to be marked as passing.")
        return 0
    else:
        print("SOME VERIFICATION STEPS FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
