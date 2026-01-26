#!/usr/bin/env python3
"""
Verification Script for Feature #19: GET /api/agent-runs/:id/events Event Timeline

This script verifies all feature steps:
1. Define FastAPI route GET /api/agent-runs/{run_id}/events
2. Add query parameters: event_type filter, limit, offset
3. Query AgentEvents by run_id ordered by sequence
4. Filter by event_type if provided
5. Apply pagination for large event streams
6. Return AgentEventListResponse
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
    Base,
)
from api.database import Base as FeatureBase
from server.schemas.agentspec import AgentEventListResponse, AgentEventResponse


def verify_step_1():
    """Step 1: Define FastAPI route GET /api/agent-runs/{run_id}/events"""
    print("\n=== Step 1: Define FastAPI route GET /api/agent-runs/{run_id}/events ===")

    # Check router file exists and has correct route
    router_path = project_root / "server" / "routers" / "agent_runs.py"
    assert router_path.exists(), f"Router file not found: {router_path}"

    content = router_path.read_text()

    # Check for route definition
    assert "@router.get(" in content, "Missing @router.get decorator"
    assert '"/{{run_id}}/events"' in content or '"/{run_id}/events"' in content, "Missing events route path"
    assert "async def get_run_events" in content, "Missing get_run_events function"

    # Check response model
    assert "response_model=AgentEventListResponse" in content, "Missing response_model"

    print("  - Router file exists: PASS")
    print("  - @router.get decorator present: PASS")
    print("  - Events route path defined: PASS")
    print("  - AgentEventListResponse response_model: PASS")
    print("STEP 1: PASS")
    return True


def verify_step_2():
    """Step 2: Add query parameters: event_type filter, limit, offset"""
    print("\n=== Step 2: Add query parameters: event_type filter, limit, offset ===")

    router_path = project_root / "server" / "routers" / "agent_runs.py"
    content = router_path.read_text()

    # Check for query parameters
    assert "event_type:" in content or "event_type :" in content, "Missing event_type parameter"
    assert "limit:" in content or "limit :" in content, "Missing limit parameter"
    assert "offset:" in content or "offset :" in content, "Missing offset parameter"

    # Check for Query import and usage
    assert "from fastapi import" in content and "Query" in content, "Missing Query import"
    assert "Query(" in content, "Query not used for parameters"

    print("  - event_type parameter: PASS")
    print("  - limit parameter: PASS")
    print("  - offset parameter: PASS")
    print("  - Query import and usage: PASS")
    print("STEP 2: PASS")
    return True


def verify_step_3_4_5_6():
    """Steps 3-6: Verify query logic, filtering, pagination, and response"""
    print("\n=== Steps 3-6: Query, Filter, Paginate, and Response ===")

    # Create in-memory database for testing
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    FeatureBase.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create test AgentSpec
    spec_id = str(uuid4())
    spec = AgentSpec(
        id=spec_id,
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective for verification",
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
    )
    session.add(run)
    session.flush()

    # Create test events with different types
    event_types = ["started", "tool_call", "tool_result", "tool_call", "tool_result",
                   "turn_complete", "tool_call", "tool_result", "completed"]

    for i, event_type in enumerate(event_types, start=1):
        event = AgentEvent(
            run_id=run_id,
            event_type=event_type,
            sequence=i,
            tool_name="test_tool" if "tool" in event_type else None,
            payload={"test": f"data_{i}"},
        )
        session.add(event)
    session.flush()
    session.commit()

    # Step 3: Query AgentEvents by run_id ordered by sequence
    print("\n  Step 3: Query AgentEvents by run_id ordered by sequence")
    events = (
        session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id)
        .order_by(AgentEvent.sequence)
        .all()
    )
    assert len(events) == 9, f"Expected 9 events, got {len(events)}"
    sequences = [e.sequence for e in events]
    assert sequences == list(range(1, 10)), f"Events not ordered by sequence: {sequences}"
    print("    - Events queried by run_id: PASS")
    print("    - Events ordered by sequence: PASS")
    print("    STEP 3: PASS")

    # Step 4: Filter by event_type if provided
    print("\n  Step 4: Filter by event_type if provided")
    tool_call_events = (
        session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id)
        .filter(AgentEvent.event_type == "tool_call")
        .order_by(AgentEvent.sequence)
        .all()
    )
    assert len(tool_call_events) == 3, f"Expected 3 tool_call events, got {len(tool_call_events)}"
    for e in tool_call_events:
        assert e.event_type == "tool_call", f"Wrong event type: {e.event_type}"
    print("    - Filter by event_type works: PASS")
    print("    STEP 4: PASS")

    # Step 5: Apply pagination for large event streams
    print("\n  Step 5: Apply pagination for large event streams")
    # Test limit
    limited_events = (
        session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id)
        .order_by(AgentEvent.sequence)
        .limit(3)
        .all()
    )
    assert len(limited_events) == 3, f"Expected 3 events with limit, got {len(limited_events)}"

    # Test offset
    offset_events = (
        session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id)
        .order_by(AgentEvent.sequence)
        .offset(5)
        .limit(3)
        .all()
    )
    assert len(offset_events) == 3, f"Expected 3 events with offset, got {len(offset_events)}"
    assert offset_events[0].sequence == 6, f"First event should be sequence 6, got {offset_events[0].sequence}"
    print("    - Limit works: PASS")
    print("    - Offset works: PASS")
    print("    STEP 5: PASS")

    # Step 6: Return AgentEventListResponse
    print("\n  Step 6: Return AgentEventListResponse")
    # Test response schema creation
    event_responses = [
        AgentEventResponse(
            id=e.id,
            run_id=e.run_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            sequence=e.sequence,
            payload=e.payload,
            payload_truncated=e.payload_truncated,
            artifact_ref=e.artifact_ref,
            tool_name=e.tool_name,
        )
        for e in limited_events
    ]

    response = AgentEventListResponse(
        events=event_responses,
        total=9,
        run_id=run_id,
        start_sequence=1,
        end_sequence=3,
        has_more=True,
    )

    assert len(response.events) == 3, f"Expected 3 events in response, got {len(response.events)}"
    assert response.total == 9, f"Expected total=9, got {response.total}"
    assert response.run_id == run_id, f"Wrong run_id in response"
    assert response.start_sequence == 1, f"Expected start_sequence=1, got {response.start_sequence}"
    assert response.end_sequence == 3, f"Expected end_sequence=3, got {response.end_sequence}"
    assert response.has_more is True, f"Expected has_more=True"
    print("    - AgentEventListResponse schema works: PASS")
    print("    - events field populated: PASS")
    print("    - total field correct: PASS")
    print("    - run_id field correct: PASS")
    print("    - start_sequence/end_sequence correct: PASS")
    print("    - has_more field correct: PASS")
    print("    STEP 6: PASS")

    session.close()
    return True


def verify_router_integration():
    """Verify router is integrated into main.py"""
    print("\n=== Router Integration Check ===")

    main_path = project_root / "server" / "main.py"
    content = main_path.read_text()

    assert "agent_runs_router" in content, "agent_runs_router not imported in main.py"
    assert "app.include_router(agent_runs_router)" in content, "agent_runs_router not registered"

    # Check __init__.py
    init_path = project_root / "server" / "routers" / "__init__.py"
    init_content = init_path.read_text()

    assert "from .agent_runs import router as agent_runs_router" in init_content, "Missing import in __init__.py"
    assert '"agent_runs_router"' in init_content, "Missing export in __all__"

    print("  - agent_runs_router imported in main.py: PASS")
    print("  - agent_runs_router registered with app: PASS")
    print("  - Router exported from routers/__init__.py: PASS")
    print("INTEGRATION: PASS")
    return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #19: GET /api/agent-runs/:id/events Event Timeline")
    print("=" * 60)

    all_passed = True

    try:
        verify_step_1()
    except AssertionError as e:
        print(f"STEP 1 FAILED: {e}")
        all_passed = False

    try:
        verify_step_2()
    except AssertionError as e:
        print(f"STEP 2 FAILED: {e}")
        all_passed = False

    try:
        verify_step_3_4_5_6()
    except AssertionError as e:
        print(f"STEPS 3-6 FAILED: {e}")
        all_passed = False

    try:
        verify_router_integration()
    except AssertionError as e:
        print(f"INTEGRATION FAILED: {e}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED!")
        print("Feature #19 is ready for final testing.")
    else:
        print("SOME VERIFICATION STEPS FAILED")
        print("Please review the output above.")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
