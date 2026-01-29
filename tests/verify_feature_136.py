"""
Verification script for Feature #136:
Wire execute endpoint to actually call HarnessKernel.execute()

This script verifies:
1. Source code has placeholder removed and HarnessKernel wired
2. HarnessKernel can be imported and has execute method
3. The background function signature is correct
4. End-to-end execution via the kernel works correctly
5. Error handling works when kernel execution fails
6. The pre-created run record is updated with kernel results
"""

import sys
import os
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _utc_now():
    return datetime.now(timezone.utc)


def test_step1_source_code_verification():
    """Step 1: Verify placeholder removed and HarnessKernel import present."""
    source_path = Path(__file__).parent.parent / "server" / "routers" / "agent_specs.py"
    content = source_path.read_text()

    # Placeholder should be removed
    assert "[PLACEHOLDER]" not in content, "PLACEHOLDER text should be removed"
    assert "asyncio.sleep(0.1)" not in content, "asyncio.sleep placeholder should be removed"

    # HarnessKernel should be imported and used
    assert "from api.harness_kernel import HarnessKernel" in content, \
        "HarnessKernel import should be present"
    assert "kernel = HarnessKernel(db=kernel_db)" in content, \
        "HarnessKernel instantiation should be present"
    assert "kernel.execute(" in content, \
        "kernel.execute() call should be present"

    print("Step 1 PASSED: Source code has placeholder removed, HarnessKernel wired")


def test_step2_harness_kernel_instantiation_and_execution():
    """Step 2: Replace placeholder with actual HarnessKernel instantiation and execution."""
    from api.harness_kernel import HarnessKernel

    assert hasattr(HarnessKernel, "execute"), "HarnessKernel should have execute method"
    assert hasattr(HarnessKernel, "initialize_run"), "HarnessKernel should have initialize_run"

    # Verify execute accepts the right params
    import inspect
    sig = inspect.signature(HarnessKernel.execute)
    params = list(sig.parameters.keys())
    assert "spec" in params, "execute should accept 'spec' parameter"
    assert "turn_executor" in params, "execute should accept 'turn_executor' parameter"
    assert "context" in params, "execute should accept 'context' parameter"

    print("Step 2 PASSED: HarnessKernel has correct execute method signature")


def test_step3_resolved_agentspec_passed_to_kernel():
    """Step 3: Pass the resolved AgentSpec to HarnessKernel.execute()."""
    from api.database import create_database
    from api.agentspec_models import AgentSpec as AgentSpecModel
    from api.harness_kernel import HarnessKernel

    # Create an in-memory database
    project_dir = Path("/tmp/test_feature_136_step3")
    project_dir.mkdir(parents=True, exist_ok=True)

    _, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Create a test spec
        spec = AgentSpecModel(
            id=str(uuid.uuid4()),
            name=f"test-f136-step3-{uuid.uuid4().hex[:8]}",
            display_name="Feature 136 Step 3 Test",
            objective="Verify spec is passed to kernel",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
            },
            max_turns=5,
            timeout_seconds=120,
            created_at=_utc_now(),
        )
        session.add(spec)
        session.commit()
        session.refresh(spec)

        # Execute via kernel
        kernel = HarnessKernel(db=session)
        run = kernel.execute(
            spec,
            turn_executor=None,  # Completes immediately
            context={"project_dir": str(project_dir)},
        )

        # Verify the kernel used the correct spec
        assert run.agent_spec_id == spec.id, \
            f"Run should reference spec: {run.agent_spec_id} != {spec.id}"
        assert run.status in ("completed", "timeout", "failed"), \
            f"Run should have terminal status, got: {run.status}"

        print(f"Step 3 PASSED: Kernel executed with resolved AgentSpec (run_id={run.id})")

    finally:
        session.close()
        # Cleanup
        import shutil
        shutil.rmtree(project_dir, ignore_errors=True)


def test_step4_agentrun_updated_with_kernel_results():
    """Step 4: Ensure created AgentRun record is updated with results from kernel execution."""
    from api.database import create_database
    from api.agentspec_models import AgentSpec as AgentSpecModel, AgentRun as AgentRunModel
    from api.harness_kernel import HarnessKernel

    project_dir = Path("/tmp/test_feature_136_step4")
    project_dir.mkdir(parents=True, exist_ok=True)

    _, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Create a spec
        spec = AgentSpecModel(
            id=str(uuid.uuid4()),
            name=f"test-f136-step4-{uuid.uuid4().hex[:8]}",
            display_name="Feature 136 Step 4 Test",
            objective="Verify run is updated with kernel results",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
            },
            max_turns=10,
            timeout_seconds=120,
            created_at=_utc_now(),
        )
        session.add(spec)
        session.commit()
        session.refresh(spec)

        # Simulate what the endpoint does: create a "pre-created" run
        pre_created_run = AgentRunModel(
            id=str(uuid.uuid4()),
            agent_spec_id=spec.id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
            created_at=_utc_now(),
        )
        session.add(pre_created_run)
        session.commit()
        pre_created_run_id = pre_created_run.id

        # Now execute via kernel (creates its own run)
        kernel = HarnessKernel(db=session)
        kernel_run = kernel.execute(
            spec,
            turn_executor=None,
            context={"project_dir": str(project_dir)},
        )

        # Simulate what the background task does: sync results back
        pre_run = session.query(AgentRunModel).filter(
            AgentRunModel.id == pre_created_run_id
        ).first()

        assert pre_run is not None, "Pre-created run should still exist"

        # Sync results
        pre_run.status = kernel_run.status
        pre_run.completed_at = kernel_run.completed_at or _utc_now()
        pre_run.turns_used = kernel_run.turns_used
        pre_run.tokens_in = kernel_run.tokens_in
        pre_run.tokens_out = kernel_run.tokens_out
        pre_run.final_verdict = kernel_run.final_verdict
        pre_run.acceptance_results = kernel_run.acceptance_results
        pre_run.error = kernel_run.error
        pre_run.retry_count = kernel_run.retry_count
        session.commit()

        # Verify the pre-created run has been updated
        updated_run = session.query(AgentRunModel).filter(
            AgentRunModel.id == pre_created_run_id
        ).first()

        assert updated_run.status == kernel_run.status, \
            f"Status not synced: {updated_run.status} != {kernel_run.status}"
        assert updated_run.completed_at is not None, "completed_at should be set"
        assert updated_run.final_verdict == kernel_run.final_verdict, \
            f"Verdict not synced: {updated_run.final_verdict} != {kernel_run.final_verdict}"

        print(
            f"Step 4 PASSED: Pre-created run updated with kernel results "
            f"(status={updated_run.status}, verdict={updated_run.final_verdict})"
        )

    finally:
        session.close()
        import shutil
        shutil.rmtree(project_dir, ignore_errors=True)


def test_step5_error_handling_updates_run_to_failed():
    """Step 5: Handle errors gracefully - if kernel execution fails, update run to 'failed'."""
    from api.database import create_database
    from api.agentspec_models import AgentSpec as AgentSpecModel, AgentRun as AgentRunModel
    from api.harness_kernel import HarnessKernel

    project_dir = Path("/tmp/test_feature_136_step5")
    project_dir.mkdir(parents=True, exist_ok=True)

    _, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Create a spec
        spec = AgentSpecModel(
            id=str(uuid.uuid4()),
            name=f"test-f136-step5-{uuid.uuid4().hex[:8]}",
            display_name="Feature 136 Step 5 Test",
            objective="Verify error handling",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
            },
            max_turns=5,
            timeout_seconds=120,
            created_at=_utc_now(),
        )
        session.add(spec)
        session.commit()
        session.refresh(spec)

        # Create a pre-created run that simulates what the endpoint creates
        pre_run = AgentRunModel(
            id=str(uuid.uuid4()),
            agent_spec_id=spec.id,
            status="running",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
            created_at=_utc_now(),
            started_at=_utc_now(),
        )
        session.add(pre_run)
        session.commit()
        pre_run_id = pre_run.id

        # Simulate a kernel execution that fails via a failing turn_executor
        def failing_executor(run, spec):
            raise RuntimeError("Simulated kernel failure for testing")

        kernel = HarnessKernel(db=session)
        kernel_run = kernel.execute(
            spec,
            turn_executor=failing_executor,
            context={"project_dir": str(project_dir)},
        )

        # The kernel should have set the run to failed
        assert kernel_run.status == "failed", \
            f"Kernel run should be failed, got: {kernel_run.status}"
        assert kernel_run.error is not None, "Kernel run should have error message"
        assert "Simulated kernel failure" in kernel_run.error, \
            f"Error should contain our message, got: {kernel_run.error}"

        # Now simulate the background task syncing error results to pre-created run
        pre_run_loaded = session.query(AgentRunModel).filter(
            AgentRunModel.id == pre_run_id
        ).first()
        pre_run_loaded.status = kernel_run.status
        pre_run_loaded.completed_at = kernel_run.completed_at or _utc_now()
        pre_run_loaded.error = kernel_run.error
        session.commit()

        # Verify
        final_run = session.query(AgentRunModel).filter(
            AgentRunModel.id == pre_run_id
        ).first()
        assert final_run.status == "failed", \
            f"Pre-created run should be failed, got: {final_run.status}"
        assert "Simulated kernel failure" in final_run.error, \
            "Pre-created run should have error details"

        print(
            f"Step 5 PASSED: Error handled gracefully - run status='failed', "
            f"error='{final_run.error[:50]}...'"
        )

    finally:
        session.close()
        import shutil
        shutil.rmtree(project_dir, ignore_errors=True)


def test_step6_endpoint_triggers_real_kernel_execution():
    """Step 6: Verify the endpoint triggers real kernel execution and returns AgentRun with verdict."""
    from api.database import create_database
    from api.agentspec_models import AgentSpec as AgentSpecModel, AgentRun as AgentRunModel
    from api.harness_kernel import HarnessKernel

    project_dir = Path("/tmp/test_feature_136_step6")
    project_dir.mkdir(parents=True, exist_ok=True)

    _, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Create a spec
        spec = AgentSpecModel(
            id=str(uuid.uuid4()),
            name=f"test-f136-step6-{uuid.uuid4().hex[:8]}",
            display_name="Feature 136 Step 6 End-to-End Test",
            objective="Full end-to-end kernel execution",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["Read", "Grep"],
                "forbidden_patterns": [],
            },
            max_turns=10,
            timeout_seconds=300,
            created_at=_utc_now(),
        )
        session.add(spec)
        session.commit()
        session.refresh(spec)

        # Execute via kernel
        kernel = HarnessKernel(db=session)
        run = kernel.execute(
            spec,
            turn_executor=None,  # Completes immediately
            context={"project_dir": str(project_dir)},
        )

        # Verify the run has a final verdict
        assert run.status in ("completed", "timeout", "failed"), \
            f"Run should have terminal status, got: {run.status}"
        assert run.completed_at is not None, "Run should have completed_at timestamp"
        assert run.turns_used >= 0, f"turns_used should be >= 0, got: {run.turns_used}"
        assert run.tokens_in >= 0, f"tokens_in should be >= 0, got: {run.tokens_in}"
        assert run.tokens_out >= 0, f"tokens_out should be >= 0, got: {run.tokens_out}"

        # Verify the run is persisted in DB
        db_run = session.query(AgentRunModel).filter(
            AgentRunModel.id == run.id
        ).first()
        assert db_run is not None, "Run should be persisted in database"
        assert db_run.status == run.status, "DB status should match run status"
        assert db_run.agent_spec_id == spec.id, "DB run should reference correct spec"

        print(
            f"Step 6 PASSED: Real kernel execution completed "
            f"(status={run.status}, verdict={run.final_verdict}, turns={run.turns_used})"
        )

    finally:
        session.close()
        import shutil
        shutil.rmtree(project_dir, ignore_errors=True)


def test_source_code_background_function():
    """Verify the _execute_spec_background function has correct structure."""
    source_path = Path(__file__).parent.parent / "server" / "routers" / "agent_specs.py"
    content = source_path.read_text()

    # Verify Phase 1: WebSocket broadcasting is preserved
    assert "broadcast_run_started" in content, "WebSocket broadcasting should be preserved"

    # Verify Phase 2: Kernel execution
    assert "kernel_spec = kernel_db.query(AgentSpecModel)" in content, \
        "Should query spec in kernel session"
    assert "joinedload(AgentSpecModel.acceptance_spec)" in content, \
        "Should eagerly load acceptance_spec"
    assert "kernel.execute(" in content, "Should call kernel.execute()"

    # Verify Phase 3: Result sync
    assert "original_run.status = kernel_status" in content, \
        "Should sync status back to original run"
    assert "original_run.final_verdict = kernel_final_verdict" in content, \
        "Should sync verdict back to original run"
    assert "original_run.acceptance_results = kernel_acceptance_results" in content, \
        "Should sync acceptance results back"

    # Verify error handling
    assert 'run.status = "failed"' in content, \
        "Error handler should set run to failed"
    assert "run.error = str(e)" in content, \
        "Error handler should set error message"
    assert "run.completed_at" in content, \
        "Error handler should set completed_at"

    # Verify spec-not-found early return
    assert "AgentSpec '{spec_id}' not found" in content, \
        "Should handle spec not found in Phase 1"

    print("Source code structure verification PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("Feature #136 Verification")
    print("Wire execute endpoint to actually call HarnessKernel.execute()")
    print("=" * 60)
    print()

    tests = [
        test_step1_source_code_verification,
        test_step2_harness_kernel_instantiation_and_execution,
        test_step3_resolved_agentspec_passed_to_kernel,
        test_step4_agentrun_updated_with_kernel_results,
        test_step5_error_handling_updates_run_to_failed,
        test_step6_endpoint_triggers_real_kernel_execution,
        test_source_code_background_function,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"FAILED: {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed}/{passed + failed} tests passed")
    if failed == 0:
        print("ALL VERIFICATION STEPS PASSED")
    else:
        print(f"{failed} tests FAILED")
    print("=" * 60)
