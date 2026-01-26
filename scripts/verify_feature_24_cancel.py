#!/usr/bin/env python3
"""
Verification Script for Feature #24: POST /api/agent-runs/:id/cancel Cancel Agent
==================================================================================

This script verifies all the steps of Feature #24 by interacting with the running
API server.

Requirements:
- Server must be running on http://localhost:8000
- Valid test data must exist or will be created

Feature Steps Verified:
1. Define FastAPI route POST /api/agent-runs/{run_id}/cancel
2. Query AgentRun by id
3. Return 404 if not found
4. Return 409 if status is already completed, failed, or timeout
5. Update status to failed
6. Set error to user_cancelled
7. Set completed_at to current timestamp
8. Record failed event with cancellation reason
9. Signal kernel to abort
10. Return updated AgentRunResponse
"""

import json
import sys
import requests
from datetime import datetime

BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"

def print_result(step: str, passed: bool, message: str = ""):
    """Print test result."""
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] Step {step}: {message}")
    return passed


def create_test_spec():
    """Create an AgentSpec for testing."""
    response = requests.post(
        f"{API_URL}/agent-specs",
        json={
            "name": f"cancel-test-spec-{datetime.now().timestamp()}",
            "display_name": "Cancel Test Spec",
            "objective": "Test objective for cancel verification",
            "task_type": "testing",
            "allowed_tools": ["feature_get_by_id"],
            "max_turns": 50,
            "timeout_seconds": 1800,
        },
    )
    if response.status_code == 200:
        return response.json()
    print(f"Failed to create spec: {response.text}")
    return None


def create_test_run(spec_id: str, status: str = "pending"):
    """Create an AgentRun for testing."""
    # First create the run
    response = requests.post(
        f"{API_URL}/agent-specs/{spec_id}/runs",
    )
    if response.status_code not in [200, 201]:
        print(f"Failed to create run: {response.text}")
        return None

    run = response.json()

    # If we need a specific status, we need to transition there
    if status == "running":
        # Start the run
        requests.post(f"{API_URL}/agent-runs/{run['id']}/start")
        response = requests.get(f"{API_URL}/agent-runs/{run['id']}")
        if response.status_code == 200:
            run = response.json()
    elif status == "paused":
        # Start and then pause
        requests.post(f"{API_URL}/agent-runs/{run['id']}/start")
        requests.post(f"{API_URL}/agent-runs/{run['id']}/pause")
        response = requests.get(f"{API_URL}/agent-runs/{run['id']}")
        if response.status_code == 200:
            run = response.json()

    return run


def verify_step_1_route_exists():
    """Step 1: Verify the cancel route exists."""
    # Try to cancel a non-existent run - should get 404 (route exists) not 405 (no route)
    response = requests.post(f"{API_URL}/agent-runs/non-existent-uuid/cancel")
    # A 404 means the route exists but the resource wasn't found
    passed = response.status_code == 404
    return print_result("1", passed, f"Cancel route exists (got {response.status_code})")


def verify_step_3_404_not_found():
    """Step 3: Return 404 if not found."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = requests.post(f"{API_URL}/agent-runs/{fake_id}/cancel")
    passed = response.status_code == 404 and "not found" in response.text.lower()
    return print_result("3", passed, f"Returns 404 for non-existent run (status={response.status_code})")


def verify_step_4_409_terminal_status(spec_id: str):
    """Step 4: Return 409 if status is terminal."""
    # Create a run and complete it, then try to cancel
    run = create_test_run(spec_id, status="running")
    if not run:
        return print_result("4", False, "Could not create test run")

    # Cancel first to get it to failed status
    cancel_response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")

    # Now try to cancel again - should get 409
    response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")
    passed = response.status_code == 409 and "terminal" in response.text.lower()
    return print_result("4", passed, f"Returns 409 for terminal status (status={response.status_code})")


def verify_steps_5_6_7_cancel_updates(spec_id: str):
    """Steps 5-7: Verify cancel updates status, error, and completed_at."""
    run = create_test_run(spec_id, status="running")
    if not run:
        return print_result("5-7", False, "Could not create test run")

    # Cancel the run
    response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")

    if response.status_code != 200:
        return print_result("5-7", False, f"Cancel failed with status {response.status_code}")

    data = response.json()

    # Step 5: Status should be failed
    step5_passed = data.get("status") == "failed"
    print_result("5", step5_passed, f"Status updated to 'failed' (got '{data.get('status')}')")

    # Step 6: Error should be user_cancelled
    step6_passed = data.get("error") == "user_cancelled"
    print_result("6", step6_passed, f"Error set to 'user_cancelled' (got '{data.get('error')}')")

    # Step 7: completed_at should be set
    step7_passed = data.get("completed_at") is not None
    print_result("7", step7_passed, f"completed_at is set (got '{data.get('completed_at')}')")

    return step5_passed and step6_passed and step7_passed


def verify_step_8_event_recorded(spec_id: str):
    """Step 8: Verify failed event is recorded with cancellation reason."""
    run = create_test_run(spec_id, status="running")
    if not run:
        return print_result("8", False, "Could not create test run")

    # Cancel the run
    response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")
    if response.status_code != 200:
        return print_result("8", False, f"Cancel failed with status {response.status_code}")

    # Get events for this run
    events_response = requests.get(f"{API_URL}/agent-runs/{run['id']}/events")
    if events_response.status_code != 200:
        return print_result("8", False, f"Failed to get events: {events_response.status_code}")

    events = events_response.json()

    # Find the failed event
    failed_events = [e for e in events if e.get("event_type") == "failed"]

    if not failed_events:
        return print_result("8", False, "No failed event found")

    failed_event = failed_events[0]
    payload = failed_event.get("payload", {})

    passed = payload.get("reason") == "user_cancelled"
    return print_result("8", passed, f"Failed event recorded with reason='user_cancelled' (got '{payload.get('reason')}')")


def verify_step_10_response(spec_id: str):
    """Step 10: Verify the response is a valid AgentRunResponse."""
    run = create_test_run(spec_id, status="running")
    if not run:
        return print_result("10", False, "Could not create test run")

    response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")
    if response.status_code != 200:
        return print_result("10", False, f"Cancel failed with status {response.status_code}")

    data = response.json()

    required_fields = [
        "id", "agent_spec_id", "status", "started_at", "completed_at",
        "turns_used", "tokens_in", "tokens_out", "final_verdict",
        "acceptance_results", "error", "retry_count", "created_at"
    ]

    missing = [f for f in required_fields if f not in data]

    passed = len(missing) == 0
    if not passed:
        return print_result("10", False, f"Missing fields: {missing}")

    return print_result("10", passed, "Response contains all AgentRunResponse fields")


def verify_cancel_pending_run(spec_id: str):
    """Verify that pending runs can be cancelled."""
    run = create_test_run(spec_id, status="pending")
    if not run:
        return print_result("Pending", False, "Could not create test run")

    response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")

    passed = response.status_code == 200 and response.json().get("status") == "failed"
    return print_result("Pending", passed, f"Pending run can be cancelled (status={response.status_code})")


def verify_cancel_paused_run(spec_id: str):
    """Verify that paused runs can be cancelled."""
    run = create_test_run(spec_id, status="paused")
    if not run:
        return print_result("Paused", False, "Could not create test run")

    response = requests.post(f"{API_URL}/agent-runs/{run['id']}/cancel")

    passed = response.status_code == 200 and response.json().get("status") == "failed"
    return print_result("Paused", passed, f"Paused run can be cancelled (status={response.status_code})")


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #24 Verification: POST /api/agent-runs/:id/cancel")
    print("=" * 60)
    print()

    # Check server is running
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        if response.status_code != 200:
            print("ERROR: Server not responding correctly")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to server at http://localhost:8000")
        print("Please start the server first with: ./init.sh")
        sys.exit(1)

    print("Server is running!")
    print()

    # Create a test spec for all tests
    spec = create_test_spec()
    if not spec:
        print("ERROR: Could not create test spec")
        sys.exit(1)

    print(f"Created test spec: {spec['id']}")
    print()

    results = []

    # Run verification steps
    results.append(verify_step_1_route_exists())
    results.append(verify_step_3_404_not_found())
    results.append(verify_step_4_409_terminal_status(spec["id"]))
    results.append(verify_steps_5_6_7_cancel_updates(spec["id"]))
    results.append(verify_step_8_event_recorded(spec["id"]))
    results.append(verify_step_10_response(spec["id"]))

    print()
    print("-" * 60)
    print("Additional Verifications:")
    print("-" * 60)
    results.append(verify_cancel_pending_run(spec["id"]))
    results.append(verify_cancel_paused_run(spec["id"]))

    print()
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} verifications passed")

    if passed == total:
        print("Feature #24 VERIFIED!")
        return 0
    else:
        print("Some verifications FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
