#!/usr/bin/env python3
"""
API Integration Test for Feature #19: GET /api/agent-runs/:id/events

This script tests the actual API endpoint by:
1. Creating test data in the database
2. Calling the API endpoint
3. Verifying the response
"""

import sys
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone
from uuid import uuid4

import requests

from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
)
from api.database import create_database, set_session_maker


def setup_test_data():
    """Create test data for API testing."""
    # Use the project's database
    engine, SessionLocal = create_database(project_root)
    set_session_maker(SessionLocal)
    session = SessionLocal()

    # Check for existing test data - clean it up first
    existing_spec = session.query(AgentSpec).filter(AgentSpec.name == "test-events-api").first()
    if existing_spec:
        session.delete(existing_spec)
        session.commit()

    # Create test AgentSpec
    spec_id = str(uuid4())
    spec = AgentSpec(
        id=spec_id,
        name="test-events-api",
        display_name="Test Events API",
        objective="Test objective for API verification",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": ["test"]},
        max_turns=50,
        timeout_seconds=1800,
    )
    session.add(spec)
    session.flush()

    # Create test AgentRun
    run_id = str(uuid4())
    run = AgentRun(
        id=run_id,
        agent_spec_id=spec_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()

    # Create test events with different types
    event_types = [
        ("started", None),
        ("tool_call", "feature_get_by_id"),
        ("tool_result", "feature_get_by_id"),
        ("tool_call", "feature_mark_passing"),
        ("tool_result", "feature_mark_passing"),
        ("turn_complete", None),
        ("tool_call", "bash"),
        ("tool_result", "bash"),
        ("acceptance_check", None),
        ("completed", None),
    ]

    for i, (event_type, tool_name) in enumerate(event_types, start=1):
        event = AgentEvent(
            run_id=run_id,
            event_type=event_type,
            sequence=i,
            tool_name=tool_name,
            payload={"test": f"data_{i}", "event_type": event_type},
            timestamp=datetime.now(timezone.utc),
        )
        session.add(event)
    session.flush()
    session.commit()

    print(f"Created test data:")
    print(f"  - AgentSpec ID: {spec_id}")
    print(f"  - AgentRun ID: {run_id}")
    print(f"  - Events created: 10")

    session.close()
    return run_id


def test_basic_endpoint(run_id: str) -> bool:
    """Test basic endpoint call."""
    print("\n=== Test 1: Basic endpoint call ===")
    url = f"http://localhost:8888/api/agent-runs/{run_id}/events"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"  FAIL: Got status {response.status_code}")
        print(f"  Response: {response.text}")
        return False

    data = response.json()
    assert "events" in data, "Missing 'events' field"
    assert "total" in data, "Missing 'total' field"
    assert "run_id" in data, "Missing 'run_id' field"
    assert "has_more" in data, "Missing 'has_more' field"
    assert data["run_id"] == run_id, f"Wrong run_id: {data['run_id']}"
    assert data["total"] == 10, f"Expected 10 events, got {data['total']}"
    assert len(data["events"]) == 10, f"Expected 10 events in response, got {len(data['events'])}"

    # Check events are ordered by sequence
    sequences = [e["sequence"] for e in data["events"]]
    assert sequences == list(range(1, 11)), f"Events not ordered: {sequences}"

    print("  - Response status: 200 OK")
    print("  - Response has all required fields: PASS")
    print("  - Total events: 10")
    print("  - Events ordered by sequence: PASS")
    print("  TEST 1: PASS")
    return True


def test_event_type_filter(run_id: str) -> bool:
    """Test event_type filter."""
    print("\n=== Test 2: Filter by event_type ===")
    url = f"http://localhost:8888/api/agent-runs/{run_id}/events"
    response = requests.get(url, params={"event_type": "tool_call"})

    if response.status_code != 200:
        print(f"  FAIL: Got status {response.status_code}")
        return False

    data = response.json()
    assert data["total"] == 3, f"Expected 3 tool_call events, got {data['total']}"
    for e in data["events"]:
        assert e["event_type"] == "tool_call", f"Wrong event type: {e['event_type']}"

    print("  - Filter by tool_call: 3 events returned")
    print("  - All events have correct type: PASS")
    print("  TEST 2: PASS")
    return True


def test_pagination(run_id: str) -> bool:
    """Test pagination with limit and offset."""
    print("\n=== Test 3: Pagination ===")
    url = f"http://localhost:8888/api/agent-runs/{run_id}/events"

    # Test limit
    response = requests.get(url, params={"limit": 3})
    data = response.json()
    assert len(data["events"]) == 3, f"Expected 3 events with limit=3, got {len(data['events'])}"
    assert data["has_more"] is True, "has_more should be True"
    assert data["start_sequence"] == 1, f"start_sequence should be 1, got {data['start_sequence']}"
    assert data["end_sequence"] == 3, f"end_sequence should be 3, got {data['end_sequence']}"
    print("  - Limit=3: 3 events returned, has_more=True")

    # Test offset
    response = requests.get(url, params={"limit": 3, "offset": 3})
    data = response.json()
    assert len(data["events"]) == 3, f"Expected 3 events with offset=3, got {len(data['events'])}"
    assert data["start_sequence"] == 4, f"start_sequence should be 4, got {data['start_sequence']}"
    print("  - Offset=3, limit=3: events 4-6 returned")

    # Test last page
    response = requests.get(url, params={"limit": 3, "offset": 9})
    data = response.json()
    assert len(data["events"]) == 1, f"Expected 1 event on last page, got {len(data['events'])}"
    assert data["has_more"] is False, "has_more should be False on last page"
    print("  - Last page: 1 event, has_more=False")

    print("  TEST 3: PASS")
    return True


def test_invalid_run_id() -> bool:
    """Test 404 for invalid run_id."""
    print("\n=== Test 4: Invalid run_id ===")
    url = f"http://localhost:8888/api/agent-runs/nonexistent-run-id/events"
    response = requests.get(url)

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    print("  - Invalid run_id returns 404: PASS")
    print("  TEST 4: PASS")
    return True


def test_invalid_event_type(run_id: str) -> bool:
    """Test 400 for invalid event_type."""
    print("\n=== Test 5: Invalid event_type ===")
    url = f"http://localhost:8888/api/agent-runs/{run_id}/events"
    response = requests.get(url, params={"event_type": "invalid_type"})

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    print("  - Invalid event_type returns 400: PASS")
    print("  TEST 5: PASS")
    return True


def cleanup_test_data():
    """Remove test data."""
    engine, SessionLocal = create_database(project_root)
    session = SessionLocal()

    spec = session.query(AgentSpec).filter(AgentSpec.name == "test-events-api").first()
    if spec:
        session.delete(spec)
        session.commit()
        print("\nTest data cleaned up.")

    session.close()


def main():
    """Run all API tests."""
    print("=" * 60)
    print("Feature #19: API Integration Test")
    print("GET /api/agent-runs/:id/events")
    print("=" * 60)

    try:
        run_id = setup_test_data()
    except Exception as e:
        print(f"Failed to setup test data: {e}")
        return False

    all_passed = True

    try:
        all_passed &= test_basic_endpoint(run_id)
        all_passed &= test_event_type_filter(run_id)
        all_passed &= test_pagination(run_id)
        all_passed &= test_invalid_run_id()
        all_passed &= test_invalid_event_type(run_id)
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    finally:
        cleanup_test_data()

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL API TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
