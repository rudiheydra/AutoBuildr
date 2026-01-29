#!/usr/bin/env python3
"""
Verification Script for Feature #49: Graceful Budget Exhaustion Handling
=========================================================================

This script verifies all 8 feature steps:
1. Detect budget exhaustion before next turn
2. Set status to timeout (not failed)
3. Record timeout event with resource that was exhausted
4. Commit any uncommitted database changes
5. Run acceptance validators on partial state
6. Store partial acceptance_results
7. Determine verdict based on partial results
8. Return AgentRun with timeout status and partial results
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent, AcceptanceSpec
from api.harness_kernel import (
    HarnessKernel,
    BudgetTracker,
    MaxTurnsExceeded,
    TimeoutSecondsExceeded,
)


def create_test_database():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def create_test_spec_with_validators(session):
    """Create a test AgentSpec with acceptance validators."""
    spec = AgentSpec(
        id="verify-spec-001",
        name="verification-spec",
        display_name="Verification Spec",
        objective="Verify Feature #49",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=5,
        timeout_seconds=60,
    )
    session.add(spec)
    session.commit()

    acceptance_spec = AcceptanceSpec(
        id="verify-acceptance-001",
        agent_spec_id=spec.id,
        validators=[
            {
                "type": "file_exists",
                "config": {"path": "/", "should_exist": True},
                "required": False,
            },
            {
                "type": "file_exists",
                "config": {"path": "/nonexistent", "should_exist": True},
                "required": False,
            },
        ],
        gate_mode="any_pass",
    )
    session.add(acceptance_spec)
    session.commit()
    session.refresh(spec)
    return spec


def verify_step_1_budget_exhaustion_detection():
    """Step 1: Detect budget exhaustion before next turn."""
    print("\n=== Step 1: Detect budget exhaustion before next turn ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step1",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._budget_tracker.turns_used = 5  # Exhaust budget

    try:
        kernel.check_budget_before_turn(run)
        print("  FAIL: Should have raised MaxTurnsExceeded")
        return False
    except MaxTurnsExceeded as e:
        print(f"  PASS: Detected max_turns exhaustion (turns={e.turns_used}, max={e.max_turns})")
        return True
    except Exception as e:
        print(f"  FAIL: Unexpected exception: {e}")
        return False


def verify_step_2_timeout_status():
    """Step 2: Set status to timeout (not failed)."""
    print("\n=== Step 2: Set status to timeout (not failed) ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step2",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._current_spec = spec
    kernel._validator_context = {}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    result = kernel.handle_budget_exceeded(run, error)

    if run.status == "timeout" and result.status == "timeout":
        print(f"  PASS: Status is 'timeout' (not 'failed')")
        return True
    else:
        print(f"  FAIL: Expected status='timeout', got run.status='{run.status}', result.status='{result.status}'")
        return False


def verify_step_3_timeout_event_recorded():
    """Step 3: Record timeout event with resource that was exhausted."""
    print("\n=== Step 3: Record timeout event with resource that was exhausted ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step3",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._current_spec = spec
    kernel._validator_context = {}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    kernel.handle_budget_exceeded(run, error)

    events = session.query(AgentEvent).filter(
        AgentEvent.run_id == run.id,
        AgentEvent.event_type == "timeout"
    ).all()

    if len(events) >= 1:
        timeout_event = events[-1]
        if timeout_event.payload.get("reason") == "max_turns_exceeded":
            print(f"  PASS: Timeout event recorded with reason='max_turns_exceeded'")
            return True
        else:
            print(f"  FAIL: Timeout event has wrong reason: {timeout_event.payload}")
            return False
    else:
        print("  FAIL: No timeout event recorded")
        return False


def verify_step_4_database_committed():
    """Step 4: Commit any uncommitted database changes."""
    print("\n=== Step 4: Commit any uncommitted database changes ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step4",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
        tokens_in=0,
        tokens_out=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._budget_tracker.tokens_in = 500
    kernel._budget_tracker.tokens_out = 250
    kernel._current_spec = spec
    kernel._validator_context = {}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    kernel.handle_budget_exceeded(run, error)

    # Refresh to get latest from database
    session.refresh(run)

    if run.tokens_in == 500 and run.tokens_out == 250 and run.status == "timeout":
        print(f"  PASS: Database changes committed (tokens_in={run.tokens_in}, tokens_out={run.tokens_out})")
        return True
    else:
        print(f"  FAIL: Data not committed properly")
        return False


def verify_step_5_validators_run_on_partial_state():
    """Step 5: Run acceptance validators on partial state."""
    print("\n=== Step 5: Run acceptance validators on partial state ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step5",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._current_spec = spec
    kernel._validator_context = {"project_dir": "/tmp"}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    kernel.handle_budget_exceeded(run, error)

    # Check for acceptance_check event
    events = session.query(AgentEvent).filter(
        AgentEvent.run_id == run.id,
        AgentEvent.event_type == "acceptance_check"
    ).all()

    if len(events) >= 1:
        print(f"  PASS: Validators ran on partial state ({len(events)} acceptance_check events)")
        return True
    else:
        print("  FAIL: No acceptance_check event recorded")
        return False


def verify_step_6_partial_results_stored():
    """Step 6: Store partial acceptance_results."""
    print("\n=== Step 6: Store partial acceptance_results ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step6",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._current_spec = spec
    kernel._validator_context = {"project_dir": "/tmp"}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    kernel.handle_budget_exceeded(run, error)

    if run.acceptance_results is not None and len(run.acceptance_results) > 0:
        print(f"  PASS: Partial acceptance_results stored ({len(run.acceptance_results)} results)")
        return True
    else:
        print("  FAIL: No acceptance_results stored")
        return False


def verify_step_7_verdict_determined():
    """Step 7: Determine verdict based on partial results."""
    print("\n=== Step 7: Determine verdict based on partial results ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step7",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._current_spec = spec
    kernel._validator_context = {"project_dir": "/tmp"}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    result = kernel.handle_budget_exceeded(run, error)

    if run.final_verdict in ["error", "failed", "passed"]:
        print(f"  PASS: Verdict determined: '{run.final_verdict}'")
        return True
    else:
        print(f"  FAIL: Invalid verdict: '{run.final_verdict}'")
        return False


def verify_step_8_returns_timeout_with_partial():
    """Step 8: Return AgentRun with timeout status and partial results."""
    print("\n=== Step 8: Return AgentRun with timeout status and partial results ===")

    session = create_test_database()
    spec = create_test_spec_with_validators(session)
    kernel = HarnessKernel(session)

    run = AgentRun(
        id="verify-step8",
        agent_spec_id=spec.id,
        status="pending",
        turns_used=0,
    )
    session.add(run)
    session.commit()

    kernel.initialize_run(run, spec)
    kernel._current_spec = spec
    kernel._validator_context = {"project_dir": "/tmp"}

    error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
    result = kernel.handle_budget_exceeded(run, error)

    checks = [
        (result.status == "timeout", f"result.status is 'timeout': {result.status}"),
        (result.error == "max_turns_exceeded", f"result.error is 'max_turns_exceeded': {result.error}"),
        (result.final_verdict is not None, f"result.final_verdict is set: {result.final_verdict}"),
        (run.acceptance_results is not None, f"run.acceptance_results is set: {run.acceptance_results is not None}"),
    ]

    all_pass = True
    for check, msg in checks:
        if check:
            print(f"  PASS: {msg}")
        else:
            print(f"  FAIL: {msg}")
            all_pass = False

    return all_pass


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #49: Graceful Budget Exhaustion Handling - Verification")
    print("=" * 70)

    results = {
        "Step 1 - Detect budget exhaustion": verify_step_1_budget_exhaustion_detection(),
        "Step 2 - Set status to timeout": verify_step_2_timeout_status(),
        "Step 3 - Record timeout event": verify_step_3_timeout_event_recorded(),
        "Step 4 - Commit database changes": verify_step_4_database_committed(),
        "Step 5 - Run validators on partial state": verify_step_5_validators_run_on_partial_state(),
        "Step 6 - Store partial acceptance_results": verify_step_6_partial_results_stored(),
        "Step 7 - Determine verdict": verify_step_7_verdict_determined(),
        "Step 8 - Return with timeout and partial results": verify_step_8_returns_timeout_with_partial(),
    }

    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    all_passed = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {step}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL 8 FEATURE STEPS VERIFIED SUCCESSFULLY")
        return 0
    else:
        print("SOME FEATURE STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
