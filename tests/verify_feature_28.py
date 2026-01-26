#!/usr/bin/env python
"""
Feature #28 Verification Script
==============================

This script verifies all 8 steps of Feature #28: Timeout Seconds Wall-Clock Enforcement.

Run with: python tests/verify_feature_28.py
"""

import sys
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.insert(0, ".")

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent
from api.harness_kernel import (
    BudgetTracker,
    TimeoutSecondsExceeded,
    HarnessKernel,
    create_timeout_event,
    record_timeout_event,
)


def create_test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def verify_step_1():
    """
    Step 1: Record started_at timestamp at run begin.

    Verifies that AgentRun.started_at is set when the run starts.
    """
    print("\n" + "=" * 60)
    print("STEP 1: Record started_at timestamp at run begin")
    print("=" * 60)

    db = create_test_db()

    # Create spec and run
    spec = AgentSpec(
        id="test-spec",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=100,
        timeout_seconds=60,
    )
    db.add(spec)

    run = AgentRun(
        id="test-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db.add(run)
    db.commit()

    # Verify started_at is None before initialization
    assert run.started_at is None, "started_at should be None before initialization"
    print("  [OK] started_at is None before initialization")

    # Initialize run
    kernel = HarnessKernel(db)
    tracker = kernel.initialize_run(run, spec)

    # Verify started_at is set
    assert run.started_at is not None, "started_at should be set after initialization"
    print("  [OK] started_at is set after initialization")

    # Verify tracker has started_at
    assert tracker.started_at is not None, "tracker.started_at should be set"
    print("  [OK] tracker.started_at is set")

    print("\n  STEP 1 PASSED: started_at timestamp is recorded at run begin")
    return True


def verify_step_2():
    """
    Step 2: Compute elapsed_seconds = now - started_at before each turn.

    Verifies that elapsed_seconds is computed correctly.
    """
    print("\n" + "=" * 60)
    print("STEP 2: Compute elapsed_seconds = now - started_at before each turn")
    print("=" * 60)

    # Test with no started_at
    tracker = BudgetTracker(max_turns=10, timeout_seconds=60)
    assert tracker.elapsed_seconds == 0.0, "elapsed_seconds should be 0 without started_at"
    print("  [OK] elapsed_seconds is 0 without started_at")

    # Test with started_at set to 30 seconds ago
    past_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    tracker = BudgetTracker(
        max_turns=10,
        timeout_seconds=60,
        started_at=past_time,
    )
    elapsed = tracker.elapsed_seconds
    assert 29 < elapsed < 32, f"elapsed_seconds should be ~30, got {elapsed}"
    print(f"  [OK] elapsed_seconds is computed correctly: {elapsed:.2f}s (expected ~30s)")

    print("\n  STEP 2 PASSED: elapsed_seconds is computed correctly from started_at")
    return True


def verify_step_3():
    """
    Step 3: Check elapsed_seconds < spec.timeout_seconds.

    Verifies that timeout check raises exception when exceeded.
    """
    print("\n" + "=" * 60)
    print("STEP 3: Check elapsed_seconds < spec.timeout_seconds")
    print("=" * 60)

    # Test within timeout - should not raise
    past_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    tracker = BudgetTracker(
        max_turns=10,
        timeout_seconds=60,
        started_at=past_time,
        run_id="test-run",
    )
    try:
        tracker.check_timeout_or_raise()
        print("  [OK] No exception when within timeout (30s < 60s)")
    except TimeoutSecondsExceeded:
        raise AssertionError("Should not raise when within timeout")

    # Test exceeding timeout - should raise
    past_time = datetime.now(timezone.utc) - timedelta(seconds=100)
    tracker = BudgetTracker(
        max_turns=10,
        timeout_seconds=60,
        started_at=past_time,
        run_id="test-run",
    )
    try:
        tracker.check_timeout_or_raise()
        raise AssertionError("Should raise when timeout exceeded")
    except TimeoutSecondsExceeded as e:
        assert e.elapsed_seconds >= 60, "elapsed_seconds should be >= 60"
        assert e.timeout_seconds == 60, "timeout_seconds should be 60"
        print(f"  [OK] TimeoutSecondsExceeded raised when timeout exceeded ({e.elapsed_seconds:.1f}s >= 60s)")

    print("\n  STEP 3 PASSED: elapsed_seconds < timeout_seconds check works correctly")
    return True


def verify_step_4():
    """
    Step 4: When timeout reached, set status to timeout.

    Verifies that run.status is set to 'timeout'.
    """
    print("\n" + "=" * 60)
    print("STEP 4: When timeout reached, set status to timeout")
    print("=" * 60)

    db = create_test_db()

    spec = AgentSpec(
        id="test-spec",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=100,
        timeout_seconds=60,
    )
    db.add(spec)

    run = AgentRun(
        id="test-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db.add(run)
    db.commit()

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    assert run.status == "running", "Status should be running after initialization"
    print("  [OK] Status is 'running' after initialization")

    # Handle timeout
    error = TimeoutSecondsExceeded(
        elapsed_seconds=65.0,
        timeout_seconds=60,
        run_id=run.id,
    )
    result = kernel.handle_timeout_exceeded(run, error)

    assert run.status == "timeout", f"Status should be 'timeout', got '{run.status}'"
    assert result.status == "timeout", "Result status should be 'timeout'"
    print("  [OK] Status is 'timeout' after handle_timeout_exceeded")

    print("\n  STEP 4 PASSED: status is set to 'timeout' when timeout reached")
    return True


def verify_step_5():
    """
    Step 5: Set error message to timeout_exceeded.

    Verifies that run.error is set to 'timeout_exceeded'.
    """
    print("\n" + "=" * 60)
    print("STEP 5: Set error message to timeout_exceeded")
    print("=" * 60)

    db = create_test_db()

    spec = AgentSpec(
        id="test-spec",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=100,
        timeout_seconds=60,
    )
    db.add(spec)

    run = AgentRun(
        id="test-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db.add(run)
    db.commit()

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    error = TimeoutSecondsExceeded(
        elapsed_seconds=65.0,
        timeout_seconds=60,
        run_id=run.id,
    )
    result = kernel.handle_timeout_exceeded(run, error)

    assert run.error == "timeout_exceeded", f"Error should be 'timeout_exceeded', got '{run.error}'"
    assert result.error == "timeout_exceeded", "Result error should be 'timeout_exceeded'"
    print("  [OK] run.error is 'timeout_exceeded'")
    print("  [OK] result.error is 'timeout_exceeded'")

    print("\n  STEP 5 PASSED: error message is set to 'timeout_exceeded'")
    return True


def verify_step_6():
    """
    Step 6: Record timeout event with elapsed_seconds in payload.

    Verifies that a timeout event is recorded with elapsed_seconds.
    """
    print("\n" + "=" * 60)
    print("STEP 6: Record timeout event with elapsed_seconds in payload")
    print("=" * 60)

    db = create_test_db()

    spec = AgentSpec(
        id="test-spec",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=100,
        timeout_seconds=60,
    )
    db.add(spec)

    run = AgentRun(
        id="test-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db.add(run)
    db.commit()

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    # Set elapsed time
    kernel._budget_tracker.started_at = datetime.now(timezone.utc) - timedelta(seconds=65)

    error = TimeoutSecondsExceeded(
        elapsed_seconds=65.0,
        timeout_seconds=60,
        run_id=run.id,
    )
    kernel.handle_timeout_exceeded(run, error)

    # Check timeout event
    events = db.query(AgentEvent).filter(
        AgentEvent.run_id == run.id,
        AgentEvent.event_type == "timeout"
    ).all()

    assert len(events) == 1, f"Expected 1 timeout event, got {len(events)}"
    print("  [OK] One timeout event recorded")

    payload = events[0].payload
    assert "elapsed_seconds" in payload, "payload should contain elapsed_seconds"
    assert "timeout_seconds" in payload, "payload should contain timeout_seconds"
    assert payload["reason"] == "timeout_exceeded", "reason should be timeout_exceeded"
    print(f"  [OK] payload contains elapsed_seconds: {payload['elapsed_seconds']:.2f}")
    print(f"  [OK] payload contains timeout_seconds: {payload['timeout_seconds']}")
    print(f"  [OK] payload.reason is 'timeout_exceeded'")

    print("\n  STEP 6 PASSED: timeout event recorded with elapsed_seconds in payload")
    return True


def verify_step_7():
    """
    Step 7: Ensure partial work is committed before termination.

    Verifies that work done before timeout is persisted.
    """
    print("\n" + "=" * 60)
    print("STEP 7: Ensure partial work is committed before termination")
    print("=" * 60)

    db = create_test_db()

    spec = AgentSpec(
        id="test-spec",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=100,
        timeout_seconds=60,
    )
    db.add(spec)

    run = AgentRun(
        id="test-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db.add(run)
    db.commit()

    kernel = HarnessKernel(db)
    kernel.initialize_run(run, spec)

    # Do some work (2 turns)
    kernel.record_turn_complete(run, {"action": "step1"})
    kernel.record_turn_complete(run, {"action": "step2"})

    assert run.turns_used == 2, f"turns_used should be 2, got {run.turns_used}"
    print("  [OK] 2 turns completed before timeout")

    error = TimeoutSecondsExceeded(
        elapsed_seconds=65.0,
        timeout_seconds=60,
        run_id=run.id,
    )
    kernel.handle_timeout_exceeded(run, error)

    # Re-query to verify persistence
    db.expire_all()
    fresh_run = db.query(AgentRun).filter(AgentRun.id == run.id).first()

    assert fresh_run.turns_used == 2, f"Persisted turns_used should be 2, got {fresh_run.turns_used}"
    assert fresh_run.status == "timeout", "Persisted status should be 'timeout'"
    print("  [OK] turns_used=2 persisted to database")
    print("  [OK] status='timeout' persisted to database")

    # Check events are committed
    events = db.query(AgentEvent).filter(AgentEvent.run_id == run.id).all()
    assert len(events) >= 3, f"Expected >= 3 events, got {len(events)}"
    print(f"  [OK] {len(events)} events persisted (started + 2 turn_complete + timeout)")

    print("\n  STEP 7 PASSED: partial work is committed before termination")
    return True


def verify_step_8():
    """
    Step 8: Handle long-running tool calls that exceed timeout.

    Verifies that timeout is detected after a long-running tool call.
    """
    print("\n" + "=" * 60)
    print("STEP 8: Handle long-running tool calls that exceed timeout")
    print("=" * 60)

    db = create_test_db()

    spec = AgentSpec(
        id="test-spec",
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=100,
        timeout_seconds=60,
    )
    db.add(spec)

    run = AgentRun(
        id="test-run",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    db.add(run)
    db.commit()

    kernel = HarnessKernel(db)

    turn_count = [0]

    def turn_executor(r, s):
        turn_count[0] += 1
        # Simulate a long-running tool call on turn 2
        if turn_count[0] == 2:
            # After this "long" tool call, we've exceeded timeout
            kernel._budget_tracker.started_at = (
                datetime.now(timezone.utc) - timedelta(seconds=100)
            )
        return False, {"tool_call": f"tool_{turn_count[0]}"}

    result = kernel.execute_with_budget(run, spec, turn_executor)

    assert result.status == "timeout", f"Status should be 'timeout', got '{result.status}'"
    assert result.error == "timeout_exceeded", f"Error should be 'timeout_exceeded', got '{result.error}'"
    assert result.turns_used >= 2, f"Should have executed >= 2 turns, got {result.turns_used}"
    print(f"  [OK] Execution timed out after {result.turns_used} turns")
    print(f"  [OK] result.status is 'timeout'")
    print(f"  [OK] result.error is 'timeout_exceeded'")

    print("\n  STEP 8 PASSED: long-running tool calls that exceed timeout are handled")
    return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("FEATURE #28: Timeout Seconds Wall-Clock Enforcement")
    print("=" * 60)
    print("\nVerifying all 8 feature steps...\n")

    steps = [
        ("Step 1", verify_step_1),
        ("Step 2", verify_step_2),
        ("Step 3", verify_step_3),
        ("Step 4", verify_step_4),
        ("Step 5", verify_step_5),
        ("Step 6", verify_step_6),
        ("Step 7", verify_step_7),
        ("Step 8", verify_step_8),
    ]

    passed = 0
    failed = 0

    for name, func in steps:
        try:
            if func():
                passed += 1
        except Exception as e:
            print(f"\n  FAILED: {name}")
            print(f"  Error: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"\n  Total Steps: {len(steps)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("  ✓ ALL VERIFICATION STEPS PASSED")
        print("\n  Feature #28: Timeout Seconds Wall-Clock Enforcement is IMPLEMENTED CORRECTLY")
        return 0
    else:
        print("  ✗ SOME VERIFICATION STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
