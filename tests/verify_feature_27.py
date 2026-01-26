#!/usr/bin/env python3
"""
Feature #27 Verification Script
===============================

Verifies: Max Turns Budget Enforcement

Feature Description:
Enforce max_turns budget during kernel execution. Increment turns_used after
each Claude API call and terminate gracefully when exhausted.

Verification Steps:
1. Initialize turns_used to 0 at run start
2. Increment turns_used after each Claude API response
3. Check turns_used < spec.max_turns before each turn
4. When budget reached, set status to timeout
5. Set error message to max_turns_exceeded
6. Record timeout event with turns_used in payload
7. Ensure partial work is committed before termination
8. Verify turns_used is persisted after each turn
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent
from api.harness_kernel import (
    HarnessKernel,
    BudgetTracker,
    MaxTurnsExceeded,
)


def create_test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def create_test_spec(db_session, max_turns=5):
    """Create a test AgentSpec."""
    spec = AgentSpec(
        id="verify-spec-001",
        name="verify-spec",
        display_name="Verification Spec",
        objective="Test max_turns enforcement",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=max_turns,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.commit()
    return spec


def create_test_run(db_session, spec):
    """Create a test AgentRun."""
    run = AgentRun(
        id="verify-run-001",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


def step_1_initialize_turns_to_zero():
    """Step 1: Initialize turns_used to 0 at run start."""
    print("\n[Step 1] Initialize turns_used to 0 at run start")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=10)

    # Create run with non-zero turns_used to test reset
    run = AgentRun(
        id="step1-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=5,  # Pre-set to 5 to verify reset
    )
    db.add(run)
    db.commit()

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    assert run.turns_used == 0, f"Expected turns_used=0, got {run.turns_used}"
    assert run.status == "running", f"Expected status=running, got {run.status}"

    print("  - PASS: turns_used initialized to 0 at run start")
    print("  - PASS: status transitioned to running")
    return True


def step_2_increment_after_api_response():
    """Step 2: Increment turns_used after each Claude API response."""
    print("\n[Step 2] Increment turns_used after each Claude API response")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=10)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    # Simulate 3 turns
    for i in range(1, 4):
        new_turns = kernel.record_turn_complete(run, {"turn": i})
        assert new_turns == i, f"Expected turns_used={i} after turn, got {new_turns}"

    assert run.turns_used == 3, f"Expected turns_used=3 after 3 turns, got {run.turns_used}"

    print("  - PASS: turns_used incremented after each turn")
    print("  - PASS: turns_used=3 after 3 turns")
    return True


def step_3_check_budget_before_turn():
    """Step 3: Check turns_used < spec.max_turns before each turn."""
    print("\n[Step 3] Check turns_used < spec.max_turns before each turn")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=3)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    # Check passes when budget available
    kernel.check_budget_before_turn(run)  # turns=0, should pass
    kernel.record_turn_complete(run)

    kernel.check_budget_before_turn(run)  # turns=1, should pass
    kernel.record_turn_complete(run)

    kernel.check_budget_before_turn(run)  # turns=2, should pass
    kernel.record_turn_complete(run)

    # Now at limit (turns=3, max=3)
    try:
        kernel.check_budget_before_turn(run)
        assert False, "Expected MaxTurnsExceeded exception"
    except MaxTurnsExceeded as e:
        assert e.turns_used == 3, f"Expected turns_used=3, got {e.turns_used}"
        assert e.max_turns == 3, f"Expected max_turns=3, got {e.max_turns}"

    print("  - PASS: Budget check passes when turns < max_turns")
    print("  - PASS: MaxTurnsExceeded raised when turns >= max_turns")
    return True


def step_4_timeout_status_on_budget_exceeded():
    """Step 4: When budget reached, set status to timeout."""
    print("\n[Step 4] When budget reached, set status to timeout")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=2)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)

    def turn_executor(run, spec):
        return False, {}  # Never completes

    result = kernel.execute_with_budget(run, spec, turn_executor)

    assert result.status == "timeout", f"Expected status=timeout, got {result.status}"
    assert run.status == "timeout", f"Expected run.status=timeout, got {run.status}"

    print("  - PASS: Status set to timeout when budget exceeded")
    return True


def step_5_error_message_max_turns_exceeded():
    """Step 5: Set error message to max_turns_exceeded."""
    print("\n[Step 5] Set error message to max_turns_exceeded")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=2)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)

    def turn_executor(run, spec):
        return False, {}

    result = kernel.execute_with_budget(run, spec, turn_executor)

    assert result.error == "max_turns_exceeded", f"Expected error='max_turns_exceeded', got {result.error}"
    assert run.error == "max_turns_exceeded", f"Expected run.error='max_turns_exceeded', got {run.error}"

    print("  - PASS: Error message set to max_turns_exceeded")
    return True


def step_6_timeout_event_with_turns():
    """Step 6: Record timeout event with turns_used in payload."""
    print("\n[Step 6] Record timeout event with turns_used in payload")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=3)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)

    def turn_executor(run, spec):
        return False, {}

    kernel.execute_with_budget(run, spec, turn_executor)

    # Check for timeout event
    events = db.query(AgentEvent).filter(
        AgentEvent.run_id == run.id,
        AgentEvent.event_type == "timeout",
    ).all()

    assert len(events) == 1, f"Expected 1 timeout event, got {len(events)}"

    payload = events[0].payload
    assert payload["reason"] == "max_turns_exceeded", f"Expected reason='max_turns_exceeded', got {payload.get('reason')}"
    assert payload["turns_used"] == 3, f"Expected turns_used=3 in payload, got {payload.get('turns_used')}"
    assert payload["max_turns"] == 3, f"Expected max_turns=3 in payload, got {payload.get('max_turns')}"

    print("  - PASS: Timeout event recorded")
    print("  - PASS: Payload contains reason='max_turns_exceeded'")
    print("  - PASS: Payload contains turns_used and max_turns")
    return True


def step_7_partial_work_committed():
    """Step 7: Ensure partial work is committed before termination."""
    print("\n[Step 7] Ensure partial work is committed before termination")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=3)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)

    def turn_executor(run, spec):
        return False, {"work": "partial"}

    kernel.execute_with_budget(run, spec, turn_executor)

    # Verify events are persisted
    events = db.query(AgentEvent).filter(AgentEvent.run_id == run.id).all()

    # Should have: started, 3x turn_complete, timeout
    assert len(events) >= 4, f"Expected >= 4 events, got {len(events)}"

    event_types = [e.event_type for e in events]
    assert "started" in event_types, "Missing 'started' event"
    assert event_types.count("turn_complete") == 3, "Expected 3 turn_complete events"
    assert "timeout" in event_types, "Missing 'timeout' event"

    print("  - PASS: All events committed to database")
    print("  - PASS: Turn events preserved despite timeout")
    return True


def step_8_turns_persisted_after_each():
    """Step 8: Verify turns_used is persisted after each turn."""
    print("\n[Step 8] Verify turns_used is persisted after each turn")

    db = create_test_db()
    spec = create_test_spec(db, max_turns=5)
    run = create_test_run(db, spec)

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    for expected_turns in range(1, 4):
        kernel.record_turn_complete(run)

        # Expire the object to force a fresh load from DB
        db.expire(run)
        fresh_run = db.query(AgentRun).filter(AgentRun.id == run.id).first()

        assert fresh_run.turns_used == expected_turns, (
            f"After turn {expected_turns}, expected turns_used={expected_turns}, "
            f"got {fresh_run.turns_used}"
        )

    print("  - PASS: turns_used persisted after each turn (verified by re-query)")
    return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #27: Max Turns Budget Enforcement - Verification")
    print("=" * 60)

    steps = [
        ("Step 1", step_1_initialize_turns_to_zero),
        ("Step 2", step_2_increment_after_api_response),
        ("Step 3", step_3_check_budget_before_turn),
        ("Step 4", step_4_timeout_status_on_budget_exceeded),
        ("Step 5", step_5_error_message_max_turns_exceeded),
        ("Step 6", step_6_timeout_event_with_turns),
        ("Step 7", step_7_partial_work_committed),
        ("Step 8", step_8_turns_persisted_after_each),
    ]

    results = []
    for name, func in steps:
        try:
            result = func()
            results.append((name, result, None))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"  - FAIL: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, error in results:
        status = "PASS" if success else "FAIL"
        print(f"  [{status}] {name}")
        if error:
            print(f"         Error: {error}")

    print(f"\nResult: {passed}/{total} steps passed")

    if passed == total:
        print("\n*** FEATURE #27 VERIFICATION PASSED ***")
        return 0
    else:
        print("\n*** FEATURE #27 VERIFICATION FAILED ***")
        return 1


if __name__ == "__main__":
    sys.exit(main())
