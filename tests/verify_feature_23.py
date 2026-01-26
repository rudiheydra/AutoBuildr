#!/usr/bin/env python3
"""
Verification script for Feature #23: POST /api/agent-runs/:id/resume Resume Agent
==================================================================================

This script verifies all 9 steps of the feature implementation.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
import uuid

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


def verify_step1_route_defined():
    """Step 1: Define FastAPI route POST /api/agent-runs/{run_id}/resume."""
    print_step(1, "Define FastAPI route POST /api/agent-runs/{run_id}/resume")

    from server.routers import agent_runs_router

    passed = True

    # Check router prefix
    passed &= print_check(
        "Router prefix is /api/agent-runs",
        agent_runs_router.prefix == "/api/agent-runs",
        f"Actual: {agent_runs_router.prefix}"
    )

    # Find the resume route
    resume_route = None
    for route in agent_runs_router.routes:
        if hasattr(route, 'path') and '/resume' in route.path:
            resume_route = route
            break

    passed &= print_check(
        "Resume route exists",
        resume_route is not None,
        f"Path: {resume_route.path if resume_route else 'Not found'}"
    )

    if resume_route:
        passed &= print_check(
            "Resume route is POST method",
            "POST" in route.methods,
            f"Methods: {route.methods}"
        )

    return passed


def verify_step2_query_by_id(db_session, test_run):
    """Step 2: Query AgentRun by id."""
    print_step(2, "Query AgentRun by id")

    from api.agentspec_crud import get_agent_run

    passed = True

    # Query the run
    run = get_agent_run(db_session, test_run.id)
    passed &= print_check(
        "Run retrieved by id",
        run is not None,
        f"ID: {run.id if run else 'Not found'}"
    )

    if run:
        passed &= print_check(
            "Retrieved correct run",
            run.id == test_run.id,
            f"Expected: {test_run.id}, Got: {run.id}"
        )

    return passed


def verify_step3_404_if_not_found(db_session):
    """Step 3: Return 404 if not found."""
    print_step(3, "Return 404 if not found")

    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    passed = True

    # Test with non-existent run
    fake_id = str(uuid.uuid4())
    response = client.post(f"/api/agent-runs/{fake_id}/resume")

    passed &= print_check(
        "Returns 404 for non-existent run",
        response.status_code == 404,
        f"Status: {response.status_code}"
    )

    if response.status_code == 404:
        detail = response.json().get("detail", "")
        passed &= print_check(
            "404 message includes run id",
            fake_id in detail,
            f"Message: {detail}"
        )
        passed &= print_check(
            "404 message includes 'not found'",
            "not found" in detail.lower(),
            ""
        )

    return passed


def verify_step4_409_if_not_paused(db_session, running_run):
    """Step 4: Return 409 Conflict if status is not paused."""
    print_step(4, "Return 409 Conflict if status is not paused")

    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    passed = True

    # Test with running run
    response = client.post(f"/api/agent-runs/{running_run.id}/resume")

    passed &= print_check(
        "Returns 409 for running run",
        response.status_code == 409,
        f"Status: {response.status_code}"
    )

    if response.status_code == 409:
        detail = response.json().get("detail", "")
        passed &= print_check(
            "409 message mentions current status",
            "running" in detail.lower(),
            f"Message: {detail}"
        )
        passed &= print_check(
            "409 message mentions required status",
            "paused" in detail.lower(),
            ""
        )

    return passed


def verify_step5_update_status(db_session, paused_run):
    """Step 5: Update status to running."""
    print_step(5, "Update status to running")

    from fastapi.testclient import TestClient
    from server.main import app
    from api.agentspec_crud import get_agent_run

    client = TestClient(app)
    passed = True

    # Resume the paused run
    response = client.post(f"/api/agent-runs/{paused_run.id}/resume")

    passed &= print_check(
        "Resume request succeeds",
        response.status_code == 200,
        f"Status: {response.status_code}"
    )

    if response.status_code == 200:
        data = response.json()
        passed &= print_check(
            "Response shows 'running' status",
            data.get("status") == "running",
            f"Status: {data.get('status')}"
        )

        # Verify in database
        db_session.expire_all()
        db_run = get_agent_run(db_session, paused_run.id)
        passed &= print_check(
            "Database status is 'running'",
            db_run.status == "running",
            f"DB status: {db_run.status}"
        )

    return passed, paused_run.id


def verify_step6_record_event(db_session, run_id):
    """Step 6: Record resumed AgentEvent."""
    print_step(6, "Record resumed AgentEvent")

    from api.agentspec_crud import get_events

    passed = True

    # Check for resumed event
    events = get_events(db_session, run_id, event_type="resumed")

    passed &= print_check(
        "Resumed event exists",
        len(events) >= 1,
        f"Event count: {len(events)}"
    )

    if events:
        event = events[0]
        passed &= print_check(
            "Event type is 'resumed'",
            event.event_type == "resumed",
            f"Type: {event.event_type}"
        )

        payload = event.payload or {}
        passed &= print_check(
            "Payload has previous_status",
            payload.get("previous_status") == "paused",
            f"Previous: {payload.get('previous_status')}"
        )
        passed &= print_check(
            "Payload has new_status",
            payload.get("new_status") == "running",
            f"New: {payload.get('new_status')}"
        )
        passed &= print_check(
            "Payload has turns_used",
            "turns_used" in payload,
            f"Turns: {payload.get('turns_used')}"
        )
        passed &= print_check(
            "Event has timestamp",
            event.timestamp is not None,
            f"Timestamp: {event.timestamp}"
        )

    return passed


def verify_step7_commit_transaction(db_session, run_id):
    """Step 7: Commit transaction."""
    print_step(7, "Commit transaction")

    from api.database import SessionLocal
    from api.agentspec_models import AgentRun, AgentEvent

    passed = True

    # Use a new session to verify persistence
    new_session = SessionLocal()
    try:
        # Check run status
        db_run = new_session.query(AgentRun).filter(AgentRun.id == run_id).first()
        passed &= print_check(
            "Run status persisted in new session",
            db_run is not None and db_run.status == "running",
            f"Status: {db_run.status if db_run else 'Not found'}"
        )

        # Check event
        event = new_session.query(AgentEvent).filter(
            AgentEvent.run_id == run_id,
            AgentEvent.event_type == "resumed"
        ).first()
        passed &= print_check(
            "Event persisted in new session",
            event is not None,
            f"Event ID: {event.id if event else 'Not found'}"
        )
    finally:
        new_session.close()

    return passed


def verify_step8_signal_kernel():
    """Step 8: Signal kernel to resume."""
    print_step(8, "Signal kernel to resume")

    # Check that the code calls get_event_broadcaster and broadcasts
    from server.routers.agent_runs import resume_agent_run
    import inspect

    source = inspect.getsource(resume_agent_run)

    passed = True

    passed &= print_check(
        "Code calls get_event_broadcaster",
        "get_event_broadcaster" in source,
        ""
    )

    passed &= print_check(
        "Code calls broadcast_event",
        "broadcast_event" in source,
        ""
    )

    passed &= print_check(
        "Broadcasts 'resumed' event_type",
        'event_type="resumed"' in source or "event_type='resumed'" in source,
        ""
    )

    return passed


def verify_step9_return_response(db_session, paused_run):
    """Step 9: Return updated AgentRunResponse."""
    print_step(9, "Return updated AgentRunResponse")

    from fastapi.testclient import TestClient
    from server.main import app
    from api.agentspec_crud import create_agent_run, create_agent_spec

    client = TestClient(app)
    passed = True

    # Create a fresh paused run for this test
    spec = create_agent_spec(
        db_session,
        name="verify-step9-spec",
        display_name="Verify Step 9",
        objective="Test step 9",
        task_type="testing",
        allowed_tools=["feature_get_by_id"],
        max_turns=50,
        timeout_seconds=1800,
    )
    run = create_agent_run(db_session, spec.id)
    run.status = "paused"
    run.started_at = datetime.now(timezone.utc)
    run.turns_used = 5
    run.tokens_in = 100
    run.tokens_out = 50
    db_session.commit()

    response = client.post(f"/api/agent-runs/{run.id}/resume")

    passed &= print_check(
        "Returns 200 OK",
        response.status_code == 200,
        f"Status: {response.status_code}"
    )

    if response.status_code == 200:
        data = response.json()

        required_fields = [
            "id", "agent_spec_id", "status", "started_at", "completed_at",
            "turns_used", "tokens_in", "tokens_out", "final_verdict",
            "acceptance_results", "error", "retry_count", "created_at"
        ]

        for field in required_fields:
            passed &= print_check(
                f"Response has '{field}' field",
                field in data,
                f"Value: {data.get(field, 'MISSING')}"
            )

        passed &= print_check(
            "Response id matches request",
            data.get("id") == run.id,
            ""
        )

        passed &= print_check(
            "Response status is 'running'",
            data.get("status") == "running",
            ""
        )

    return passed


def main():
    """Run all verification steps."""
    print_header("Feature #23: POST /api/agent-runs/:id/resume Verification")

    # Setup database and test data
    from api.database import create_database, set_session_maker
    from api.agentspec_crud import create_agent_spec, create_agent_run

    engine, SessionLocal = create_database(project_root)
    set_session_maker(SessionLocal)

    db = SessionLocal()

    try:
        # Create test data
        spec = create_agent_spec(
            db,
            name="feature23-test-spec",
            display_name="Feature 23 Test",
            objective="Test objective",
            task_type="testing",
            allowed_tools=["feature_get_by_id"],
            max_turns=50,
            timeout_seconds=1800,
        )

        paused_run = create_agent_run(db, spec.id)
        paused_run.status = "paused"
        paused_run.started_at = datetime.now(timezone.utc)
        paused_run.turns_used = 5
        paused_run.tokens_in = 1000
        paused_run.tokens_out = 500

        running_run = create_agent_run(db, spec.id)
        running_run.status = "running"
        running_run.started_at = datetime.now(timezone.utc)

        db.commit()

        all_passed = True

        # Run all verification steps
        all_passed &= verify_step1_route_defined()
        all_passed &= verify_step2_query_by_id(db, paused_run)
        all_passed &= verify_step3_404_if_not_found(db)
        all_passed &= verify_step4_409_if_not_paused(db, running_run)
        step5_passed, run_id = verify_step5_update_status(db, paused_run)
        all_passed &= step5_passed
        all_passed &= verify_step6_record_event(db, run_id)
        all_passed &= verify_step7_commit_transaction(db, run_id)
        all_passed &= verify_step8_signal_kernel()
        all_passed &= verify_step9_return_response(db, paused_run)

        # Summary
        print_header("VERIFICATION SUMMARY")
        if all_passed:
            print("All verification steps PASSED!")
            print("\nFeature #23 is ready to be marked as passing.")
            return 0
        else:
            print("Some verification steps FAILED.")
            print("\nPlease fix the failing steps before marking as passing.")
            return 1

    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    sys.exit(main())
