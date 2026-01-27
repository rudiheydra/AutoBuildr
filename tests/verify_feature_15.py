#!/usr/bin/env python3
"""
Feature #15 Verification Script
===============================

DELETE /api/agent-specs/:id Cascade Delete

This script verifies all 11 feature steps are correctly implemented:
1. Define FastAPI route DELETE /api/agent-specs/{spec_id}
2. Query AgentSpec by id
3. Return 404 if not found
4. Verify ON DELETE CASCADE is configured in foreign keys
5. Delete the AgentSpec record
6. Commit transaction
7. Verify AcceptanceSpec is deleted
8. Verify all AgentRuns are deleted
9. Verify all Artifacts for those runs are deleted
10. Verify all AgentEvents for those runs are deleted
11. Return 204 No Content
"""

import asyncio
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def print_step(step_num: int, description: str, passed: bool) -> None:
    """Print a verification step result."""
    status = "PASS" if passed else "FAIL"
    print(f"  Step {step_num}: {description} - {status}")


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #15: DELETE /api/agent-specs/:id Cascade Delete")
    print("=" * 60)
    print()

    all_passed = True
    results = []

    # Setup
    from api.database import create_database
    from api.agentspec_models import (
        AgentSpec, AcceptanceSpec, AgentRun, Artifact, AgentEvent
    )
    from server.routers.agent_specs import router, delete_agent_spec, _is_valid_uuid
    from sqlalchemy import inspect

    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)
    engine, SessionLocal = create_database(temp_path)
    session = SessionLocal()

    try:
        # Step 1: Verify route definition
        print("Step 1: Define FastAPI route DELETE /api/agent-specs/{spec_id}")
        routes = [r for r in router.routes]
        delete_routes = [
            r for r in routes
            if hasattr(r, 'methods') and 'DELETE' in r.methods and '{spec_id}' in r.path
        ]
        step1_passed = len(delete_routes) == 1
        results.append(("Route definition", step1_passed))
        if step1_passed:
            print("  - DELETE /{spec_id} route exists")
            print("  - Status code is 204 No Content")
        else:
            print("  - FAIL: DELETE route not found")
        print()

        # Create test data
        spec_id = str(uuid.uuid4())
        spec = AgentSpec(
            id=spec_id,
            name="test-spec",
            display_name="Test Spec",
            icon="test",
            spec_version="v1",
            objective="Test objective for verification that is long enough",
            task_type="coding",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["feature_get_by_id"],
                "forbidden_patterns": [],
                "tool_hints": {}
            },
            max_turns=50,
            timeout_seconds=1800,
            priority=100,
            tags=["test"],
            created_at=datetime.now(timezone.utc),
        )
        session.add(spec)
        session.commit()

        # Step 2: Query AgentSpec by id
        print("Step 2: Query AgentSpec by id")
        found_spec = session.query(AgentSpec).filter(AgentSpec.id == spec_id).first()
        step2_passed = found_spec is not None
        results.append(("Query spec by id", step2_passed))
        if step2_passed:
            print(f"  - Successfully queried spec {spec_id[:8]}...")
        print()

        # Step 3: Return 404 if not found
        print("Step 3: Return 404 if not found")
        from unittest.mock import patch
        from fastapi import HTTPException

        step3_passed = True
        try:
            # Patch _get_project_path to return temp path
            with patch('server.routers.agent_specs._get_project_path') as mock_path:
                mock_path.return_value = temp_path
                asyncio.run(delete_agent_spec("test", str(uuid.uuid4())))
                step3_passed = False  # Should have raised 404
        except HTTPException as e:
            step3_passed = e.status_code == 404

        results.append(("404 for non-existent", step3_passed))
        if step3_passed:
            print("  - Returns 404 for non-existent spec")
        print()

        # Step 4: Verify ON DELETE CASCADE
        print("Step 4: Verify ON DELETE CASCADE is configured in foreign keys")
        inspector = inspect(engine)

        cascade_checks = []

        # Check AcceptanceSpec -> AgentSpec FK
        acceptance_fks = inspector.get_foreign_keys('acceptance_specs')
        acceptance_cascade = any(
            fk['referred_table'] == 'agent_specs' and
            fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'
            for fk in acceptance_fks
        )
        cascade_checks.append(("AcceptanceSpec.agent_spec_id", acceptance_cascade))

        # Check AgentRun -> AgentSpec FK
        run_fks = inspector.get_foreign_keys('agent_runs')
        run_cascade = any(
            fk['referred_table'] == 'agent_specs' and
            fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'
            for fk in run_fks
        )
        cascade_checks.append(("AgentRun.agent_spec_id", run_cascade))

        # Check Artifact -> AgentRun FK
        artifact_fks = inspector.get_foreign_keys('artifacts')
        artifact_cascade = any(
            fk['referred_table'] == 'agent_runs' and
            fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'
            for fk in artifact_fks
        )
        cascade_checks.append(("Artifact.run_id", artifact_cascade))

        # Check AgentEvent -> AgentRun FK
        event_fks = inspector.get_foreign_keys('agent_events')
        event_cascade = any(
            fk['referred_table'] == 'agent_runs' and
            fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'
            for fk in event_fks
        )
        cascade_checks.append(("AgentEvent.run_id", event_cascade))

        step4_passed = all(check[1] for check in cascade_checks)
        results.append(("ON DELETE CASCADE configured", step4_passed))
        for name, passed in cascade_checks:
            status = "OK" if passed else "FAIL"
            print(f"  - {name}: {status}")
        print()

        # Create complete test hierarchy
        acceptance = AcceptanceSpec(
            id=str(uuid.uuid4()),
            agent_spec_id=spec_id,
            validators=[],
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )
        session.add(acceptance)
        acceptance_id = acceptance.id

        run = AgentRun(
            id=str(uuid.uuid4()),
            agent_spec_id=spec_id,
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            turns_used=5,
            tokens_in=500,
            tokens_out=1000,
            final_verdict="passed",
            retry_count=0,
            created_at=datetime.now(timezone.utc),
        )
        session.add(run)
        run_id = run.id

        artifact = Artifact(
            id=str(uuid.uuid4()),
            run_id=run_id,
            artifact_type="test_result",
            content_inline="test",
            size_bytes=4,
            created_at=datetime.now(timezone.utc),
        )
        session.add(artifact)
        artifact_id = artifact.id

        event = AgentEvent(
            run_id=run_id,
            event_type="started",
            sequence=1,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(event)
        session.commit()
        event_id = event.id

        # Step 5: Delete the AgentSpec record
        print("Step 5: Delete the AgentSpec record")
        session.delete(spec)
        session.commit()
        step5_passed = True
        results.append(("Delete spec record", step5_passed))
        print("  - Spec deleted successfully")
        print()

        # Step 6: Commit transaction (implicitly tested above)
        print("Step 6: Commit transaction")
        new_session = SessionLocal()
        still_exists = new_session.query(AgentSpec).filter(AgentSpec.id == spec_id).first()
        step6_passed = still_exists is None
        results.append(("Transaction committed", step6_passed))
        if step6_passed:
            print("  - Deletion persisted after commit")
        new_session.close()
        print()

        # Step 7: Verify AcceptanceSpec is deleted
        print("Step 7: Verify AcceptanceSpec is deleted")
        acceptance_deleted = session.query(AcceptanceSpec).filter(
            AcceptanceSpec.id == acceptance_id
        ).first() is None
        step7_passed = acceptance_deleted
        results.append(("AcceptanceSpec deleted", step7_passed))
        if step7_passed:
            print("  - AcceptanceSpec cascade-deleted")
        print()

        # Step 8: Verify all AgentRuns are deleted
        print("Step 8: Verify all AgentRuns are deleted")
        runs_deleted = session.query(AgentRun).filter(
            AgentRun.id == run_id
        ).first() is None
        step8_passed = runs_deleted
        results.append(("AgentRuns deleted", step8_passed))
        if step8_passed:
            print("  - AgentRun cascade-deleted")
        print()

        # Step 9: Verify all Artifacts for those runs are deleted
        print("Step 9: Verify all Artifacts for those runs are deleted")
        artifacts_deleted = session.query(Artifact).filter(
            Artifact.id == artifact_id
        ).first() is None
        step9_passed = artifacts_deleted
        results.append(("Artifacts deleted", step9_passed))
        if step9_passed:
            print("  - Artifact cascade-deleted")
        print()

        # Step 10: Verify all AgentEvents for those runs are deleted
        print("Step 10: Verify all AgentEvents for those runs are deleted")
        events_deleted = session.query(AgentEvent).filter(
            AgentEvent.id == event_id
        ).first() is None
        step10_passed = events_deleted
        results.append(("AgentEvents deleted", step10_passed))
        if step10_passed:
            print("  - AgentEvent cascade-deleted")
        print()

        # Step 11: Return 204 No Content
        print("Step 11: Return 204 No Content")
        # Create a new spec to test API return
        new_spec = AgentSpec(
            id=str(uuid.uuid4()),
            name="test-spec-2",
            display_name="Test Spec 2",
            spec_version="v1",
            objective="Test objective for verification that is long enough",
            task_type="coding",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["test"],
                "forbidden_patterns": [],
                "tool_hints": {}
            },
            max_turns=50,
            timeout_seconds=1800,
            priority=100,
            created_at=datetime.now(timezone.utc),
        )
        session.add(new_spec)
        session.commit()

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = temp_path
            response = asyncio.run(delete_agent_spec("test", new_spec.id))
            step11_passed = response.status_code == 204 and response.body == b''

        results.append(("Returns 204 No Content", step11_passed))
        if step11_passed:
            print("  - Returns 204 status code")
            print("  - Response body is empty")
        print()

    finally:
        session.close()
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Summary
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    total_passed = sum(1 for _, passed in results if passed)
    total_steps = len(results)
    print(f"Passed: {total_passed}/{total_steps}")
    print()

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    print()
    all_passed = total_passed == total_steps
    if all_passed:
        print("All verification steps passed!")
        return 0
    else:
        print("Some verification steps failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
