#!/usr/bin/env python3
"""
Feature #29 Verification Script
================================

Verifies that Token Usage Tracking is fully implemented and working.

Verification Steps:
1. Initialize tokens_in and tokens_out to 0 at run start
2. Extract input_tokens from Claude API response usage field
3. Extract output_tokens from Claude API response usage field
4. Accumulate totals across all turns
5. Update AgentRun.tokens_in and tokens_out after each turn
6. Persist token counts even on failure/timeout
7. Include token counts in run response
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun
from api.harness_kernel import (
    BudgetTracker,
    HarnessKernel,
    ExecutionResult,
    MaxTurnsExceeded,
)


def create_test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def create_test_spec(session):
    """Create a test AgentSpec."""
    spec = AgentSpec(
        id="verify-spec-001",
        name="verify-feature-29",
        display_name="Verify Feature 29",
        objective="Test token tracking",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=5,
        timeout_seconds=300,
    )
    session.add(spec)
    session.commit()
    return spec


def create_test_run(session, spec_id):
    """Create a test AgentRun."""
    run = AgentRun(
        id="verify-run-001",
        agent_spec_id=spec_id,
        status="pending",
        turns_used=0,
        tokens_in=0,
        tokens_out=0,
    )
    session.add(run)
    session.commit()
    return run


def verify_step_1():
    """Step 1: Initialize tokens_in and tokens_out to 0 at run start."""
    print("Step 1: Initialize tokens_in and tokens_out to 0 at run start")
    print("-" * 60)

    session = create_test_db()
    spec = create_test_spec(session)

    # Create run with non-zero tokens to verify they get reset
    run = AgentRun(
        id="step1-run",
        agent_spec_id=spec.id,
        status="pending",
        tokens_in=999,
        tokens_out=888,
    )
    session.add(run)
    session.commit()

    kernel = HarnessKernel(session)
    tracker = kernel.initialize_run(run, spec)

    # Verify
    assert run.tokens_in == 0, f"Expected tokens_in=0, got {run.tokens_in}"
    assert run.tokens_out == 0, f"Expected tokens_out=0, got {run.tokens_out}"
    assert tracker.tokens_in == 0, f"Expected tracker.tokens_in=0, got {tracker.tokens_in}"
    assert tracker.tokens_out == 0, f"Expected tracker.tokens_out=0, got {tracker.tokens_out}"

    print("  - AgentRun.tokens_in initialized to 0: PASS")
    print("  - AgentRun.tokens_out initialized to 0: PASS")
    print("  - BudgetTracker.tokens_in initialized to 0: PASS")
    print("  - BudgetTracker.tokens_out initialized to 0: PASS")
    print("Step 1: PASS\n")
    return True


def verify_step_2_3():
    """Steps 2-3: Extract input_tokens and output_tokens from Claude API response usage field."""
    print("Steps 2-3: Extract input_tokens and output_tokens from Claude API response")
    print("-" * 60)

    # Simulate Claude API response usage field
    class MockUsage:
        input_tokens = 1500
        output_tokens = 500

    class MockResponse:
        usage = MockUsage()

    response = MockResponse()

    # Extract tokens (as would be done from Claude API response)
    tracker = BudgetTracker(max_turns=10, run_id="test")
    tracker.accumulate_tokens(response.usage.input_tokens, response.usage.output_tokens)

    # Verify
    assert tracker.tokens_in == 1500, f"Expected tokens_in=1500, got {tracker.tokens_in}"
    assert tracker.tokens_out == 500, f"Expected tokens_out=500, got {tracker.tokens_out}"

    print("  - Extracted input_tokens from response.usage: PASS")
    print("  - Extracted output_tokens from response.usage: PASS")
    print("Steps 2-3: PASS\n")
    return True


def verify_step_4():
    """Step 4: Accumulate totals across all turns."""
    print("Step 4: Accumulate totals across all turns")
    print("-" * 60)

    tracker = BudgetTracker(max_turns=10, run_id="test")

    # Simulate 3 turns with different token counts
    turns = [
        (1000, 300),  # Turn 1
        (1200, 400),  # Turn 2
        (800, 200),   # Turn 3
    ]

    expected_total_in = 0
    expected_total_out = 0

    for i, (input_tokens, output_tokens) in enumerate(turns, 1):
        tracker.accumulate_tokens(input_tokens, output_tokens)
        expected_total_in += input_tokens
        expected_total_out += output_tokens
        print(f"  - After turn {i}: tokens_in={tracker.tokens_in}, tokens_out={tracker.tokens_out}")

    # Verify
    assert tracker.tokens_in == 3000, f"Expected tokens_in=3000, got {tracker.tokens_in}"
    assert tracker.tokens_out == 900, f"Expected tokens_out=900, got {tracker.tokens_out}"

    print("  - Accumulated tokens_in (3000): PASS")
    print("  - Accumulated tokens_out (900): PASS")
    print("Step 4: PASS\n")
    return True


def verify_step_5():
    """Step 5: Update AgentRun.tokens_in and tokens_out after each turn."""
    print("Step 5: Update AgentRun.tokens_in and tokens_out after each turn")
    print("-" * 60)

    session = create_test_db()
    spec = create_test_spec(session)
    run = create_test_run(session, spec.id)

    kernel = HarnessKernel(session)
    kernel.initialize_run(run, spec)

    # Turn 1
    kernel.record_turn_complete(run, input_tokens=1000, output_tokens=300)
    assert run.tokens_in == 1000, f"After turn 1: Expected tokens_in=1000, got {run.tokens_in}"
    assert run.tokens_out == 300, f"After turn 1: Expected tokens_out=300, got {run.tokens_out}"
    print(f"  - After turn 1: tokens_in={run.tokens_in}, tokens_out={run.tokens_out} - PASS")

    # Turn 2
    kernel.record_turn_complete(run, input_tokens=500, output_tokens=200)
    assert run.tokens_in == 1500, f"After turn 2: Expected tokens_in=1500, got {run.tokens_in}"
    assert run.tokens_out == 500, f"After turn 2: Expected tokens_out=500, got {run.tokens_out}"
    print(f"  - After turn 2: tokens_in={run.tokens_in}, tokens_out={run.tokens_out} - PASS")

    print("Step 5: PASS\n")
    return True


def verify_step_6():
    """Step 6: Persist token counts even on failure/timeout."""
    print("Step 6: Persist token counts even on failure/timeout")
    print("-" * 60)

    session = create_test_db()
    spec = create_test_spec(session)
    run = create_test_run(session, spec.id)

    kernel = HarnessKernel(session)
    kernel.initialize_run(run, spec)

    # Accumulate tokens
    kernel.record_turn_complete(run, input_tokens=1000, output_tokens=300)
    kernel.record_turn_complete(run, input_tokens=1200, output_tokens=400)

    # Simulate timeout
    error = MaxTurnsExceeded(turns_used=2, max_turns=spec.max_turns, run_id=run.id)
    result = kernel.handle_budget_exceeded(run, error)

    # Verify tokens persisted in database
    session.expire(run)
    fresh_run = session.query(AgentRun).filter(AgentRun.id == run.id).first()

    assert fresh_run.tokens_in == 2200, f"Expected tokens_in=2200 in DB, got {fresh_run.tokens_in}"
    assert fresh_run.tokens_out == 700, f"Expected tokens_out=700 in DB, got {fresh_run.tokens_out}"
    assert fresh_run.status == "timeout", f"Expected status='timeout', got {fresh_run.status}"

    print(f"  - Run status: {fresh_run.status}")
    print(f"  - Persisted tokens_in: {fresh_run.tokens_in} - PASS")
    print(f"  - Persisted tokens_out: {fresh_run.tokens_out} - PASS")
    print("Step 6: PASS\n")
    return True


def verify_step_7():
    """Step 7: Include token counts in run response."""
    print("Step 7: Include token counts in run response")
    print("-" * 60)

    # Test ExecutionResult includes tokens
    result = ExecutionResult(
        run_id="test",
        status="completed",
        turns_used=3,
        final_verdict="passed",
        error=None,
        tokens_in=3000,
        tokens_out=900,
    )

    assert result.tokens_in == 3000, f"Expected tokens_in=3000, got {result.tokens_in}"
    assert result.tokens_out == 900, f"Expected tokens_out=900, got {result.tokens_out}"
    assert result.total_tokens == 3900, f"Expected total_tokens=3900, got {result.total_tokens}"

    print(f"  - ExecutionResult.tokens_in: {result.tokens_in} - PASS")
    print(f"  - ExecutionResult.tokens_out: {result.tokens_out} - PASS")
    print(f"  - ExecutionResult.total_tokens: {result.total_tokens} - PASS")
    print("Step 7: PASS\n")
    return True


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #29: Token Usage Tracking - Verification")
    print("=" * 70)
    print()

    all_passed = True

    try:
        all_passed &= verify_step_1()
        all_passed &= verify_step_2_3()
        all_passed &= verify_step_4()
        all_passed &= verify_step_5()
        all_passed &= verify_step_6()
        all_passed &= verify_step_7()
    except AssertionError as e:
        print(f"FAILED: {e}")
        all_passed = False
    except Exception as e:
        print(f"ERROR: {e}")
        all_passed = False

    print("=" * 70)
    if all_passed:
        print("FEATURE #29 VERIFICATION: ALL STEPS PASSED")
        print("=" * 70)
        return 0
    else:
        print("FEATURE #29 VERIFICATION: SOME STEPS FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
