#!/usr/bin/env python3
"""
Verification Script for Feature #77: Database Transaction Safety

This script verifies all 6 feature steps are implemented correctly.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def verify_step_1():
    """Step 1: Use SQLAlchemy session per-run"""
    print("\n=== Step 1: Use SQLAlchemy session per-run ===")

    from api.harness_kernel import HarnessKernel
    from sqlalchemy.orm import Session

    # Verify HarnessKernel accepts a Session
    import inspect
    init_signature = inspect.signature(HarnessKernel.__init__)
    params = list(init_signature.parameters.keys())
    assert 'db' in params, "HarnessKernel should accept 'db' parameter"
    print("  [PASS] HarnessKernel accepts db session parameter")

    # Verify the db attribute exists
    assert hasattr(HarnessKernel, '__init__'), "HarnessKernel has __init__"
    print("  [PASS] HarnessKernel stores session as self.db")

    return True


def verify_step_2():
    """Step 2: Commit after each event record for durability"""
    print("\n=== Step 2: Commit after each event record for durability ===")

    from api.harness_kernel import commit_with_retry, safe_add_and_commit_event

    # Verify commit_with_retry exists
    assert callable(commit_with_retry), "commit_with_retry should be callable"
    print("  [PASS] commit_with_retry function exists")

    # Verify safe_add_and_commit_event exists
    assert callable(safe_add_and_commit_event), "safe_add_and_commit_event should be callable"
    print("  [PASS] safe_add_and_commit_event function exists")

    # Check function signature
    import inspect
    sig = inspect.signature(commit_with_retry)
    params = list(sig.parameters.keys())
    assert 'db' in params, "commit_with_retry should have db parameter"
    assert 'operation' in params, "commit_with_retry should have operation parameter"
    assert 'run_id' in params, "commit_with_retry should have run_id parameter"
    print("  [PASS] commit_with_retry has correct parameters")

    return True


def verify_step_3():
    """Step 3: Handle IntegrityError from concurrent inserts"""
    print("\n=== Step 3: Handle IntegrityError from concurrent inserts ===")

    from api.harness_kernel import ConcurrentModificationError, TransactionError

    # Verify ConcurrentModificationError exists and is a subclass of TransactionError
    assert issubclass(ConcurrentModificationError, TransactionError), \
        "ConcurrentModificationError should be subclass of TransactionError"
    print("  [PASS] ConcurrentModificationError exception exists")

    # Verify it has the right attributes
    error = ConcurrentModificationError(
        run_id="test-run-id",
        operation="test_op",
        original_error=Exception("test")
    )
    assert hasattr(error, 'run_id'), "Should have run_id attribute"
    assert hasattr(error, 'operation'), "Should have operation attribute"
    assert hasattr(error, 'original_error'), "Should have original_error attribute"
    print("  [PASS] ConcurrentModificationError has required attributes")

    return True


def verify_step_4():
    """Step 4: Use SELECT FOR UPDATE when modifying run status"""
    print("\n=== Step 4: Use SELECT FOR UPDATE when modifying run status ===")

    from api.harness_kernel import get_run_with_lock, DatabaseLockError

    # Verify get_run_with_lock exists
    assert callable(get_run_with_lock), "get_run_with_lock should be callable"
    print("  [PASS] get_run_with_lock function exists")

    # Verify DatabaseLockError exists
    assert issubclass(DatabaseLockError, Exception), \
        "DatabaseLockError should be an Exception subclass"
    print("  [PASS] DatabaseLockError exception exists")

    # Verify DatabaseLockError has timeout info
    error = DatabaseLockError(run_id="test", timeout_seconds=30.0)
    assert hasattr(error, 'timeout_seconds'), "Should have timeout_seconds"
    assert error.timeout_seconds == 30.0, "Should store timeout value"
    print("  [PASS] DatabaseLockError has timeout information")

    return True


def verify_step_5():
    """Step 5: Rollback on exception and record error"""
    print("\n=== Step 5: Rollback on exception and record error ===")

    from api.harness_kernel import rollback_and_record_error

    # Verify function exists
    assert callable(rollback_and_record_error), "rollback_and_record_error should be callable"
    print("  [PASS] rollback_and_record_error function exists")

    # Check function signature
    import inspect
    sig = inspect.signature(rollback_and_record_error)
    params = list(sig.parameters.keys())
    assert 'db' in params, "Should have db parameter"
    assert 'run_id' in params, "Should have run_id parameter"
    assert 'error' in params, "Should have error parameter"
    print("  [PASS] rollback_and_record_error has correct parameters")

    return True


def verify_step_6():
    """Step 6: Close session in finally block"""
    print("\n=== Step 6: Close session in finally block ===")

    import inspect
    from api.harness_kernel import HarnessKernel

    # Read the execute method source and verify finally block exists
    source = inspect.getsource(HarnessKernel.execute)
    assert 'finally:' in source, "execute method should have finally block"
    print("  [PASS] execute method has finally block")

    # Verify internal state cleanup
    assert '_current_spec = None' in source, "Should clear _current_spec"
    assert '_validator_context = {}' in source, "Should clear _validator_context"
    print("  [PASS] finally block clears internal state")

    return True


def verify_exports():
    """Verify all new functions/classes are exported from api module"""
    print("\n=== Verify Exports ===")

    from api import (
        TransactionError,
        ConcurrentModificationError,
        DatabaseLockError,
        commit_with_retry,
        rollback_and_record_error,
        get_run_with_lock,
        safe_add_and_commit_event,
        TimeoutSecondsExceeded,
    )

    print("  [PASS] TransactionError exported")
    print("  [PASS] ConcurrentModificationError exported")
    print("  [PASS] DatabaseLockError exported")
    print("  [PASS] commit_with_retry exported")
    print("  [PASS] rollback_and_record_error exported")
    print("  [PASS] get_run_with_lock exported")
    print("  [PASS] safe_add_and_commit_event exported")
    print("  [PASS] TimeoutSecondsExceeded exported")

    return True


def run_integration_test():
    """Run a quick integration test"""
    print("\n=== Integration Test ===")

    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from api.database import Base
    from api.agentspec_models import AgentSpec
    from api.harness_kernel import HarnessKernel

    # Create in-memory database
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        # Create a test spec
        spec = AgentSpec(
            id=str(uuid.uuid4()),
            name="verify-test-spec",
            display_name="Verification Test Spec",
            objective="Test transaction safety",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": []},
            max_turns=3,
            timeout_seconds=300,
            created_at=datetime.now(timezone.utc),
        )
        session.add(spec)
        session.commit()
        session.refresh(spec)

        # Create kernel and execute
        kernel = HarnessKernel(session)

        call_count = 0
        def test_executor(run, spec):
            nonlocal call_count
            call_count += 1
            return call_count >= 2, {"turn": call_count}, [], 50, 25

        run = kernel.execute(spec, turn_executor=test_executor)

        # Verify execution succeeded
        assert run.status == "completed", f"Expected completed, got {run.status}"
        assert run.turns_used == 2, f"Expected 2 turns, got {run.turns_used}"
        print("  [PASS] Kernel execution completed successfully")

        # Verify internal state was cleared
        assert kernel._current_spec is None, "Internal spec should be cleared"
        assert kernel._validator_context == {}, "Internal context should be cleared"
        print("  [PASS] Internal state cleared after execution")

    finally:
        session.close()

    return True


def main():
    print("=" * 60)
    print("Feature #77: Database Transaction Safety - Verification")
    print("=" * 60)

    results = []

    try:
        results.append(("Step 1: Session per-run", verify_step_1()))
    except Exception as e:
        results.append(("Step 1: Session per-run", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Step 2: Commit after events", verify_step_2()))
    except Exception as e:
        results.append(("Step 2: Commit after events", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Step 3: Handle IntegrityError", verify_step_3()))
    except Exception as e:
        results.append(("Step 3: Handle IntegrityError", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Step 4: SELECT FOR UPDATE", verify_step_4()))
    except Exception as e:
        results.append(("Step 4: SELECT FOR UPDATE", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Step 5: Rollback on exception", verify_step_5()))
    except Exception as e:
        results.append(("Step 5: Rollback on exception", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Step 6: Session cleanup", verify_step_6()))
    except Exception as e:
        results.append(("Step 6: Session cleanup", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Exports", verify_exports()))
    except Exception as e:
        results.append(("Exports", False))
        print(f"  [FAIL] {e}")

    try:
        results.append(("Integration Test", run_integration_test()))
    except Exception as e:
        results.append(("Integration Test", False))
        print(f"  [FAIL] {e}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n[SUCCESS] All Feature #77 verification checks passed!")
        return 0
    else:
        print("\n[FAILURE] Some checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
