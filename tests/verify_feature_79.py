#!/usr/bin/env python3
"""
Feature #79 Verification Script
================================

Verifies all 6 feature steps for "Orphaned Run Cleanup on Startup".

Feature Description:
On server startup, clean up orphaned runs stuck in running/pending status.

Feature Steps:
1. On startup, query runs where status in (running, pending)
2. Check if run started_at is older than max timeout
3. For stale runs, set status to failed
4. Set error to orphaned_on_restart
5. Record failed event
6. Log cleanup actions

Usage:
    python tests/verify_feature_79.py
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
)
from api.orphaned_run_cleanup import (
    ORPHANED_ERROR_MESSAGE,
    DEFAULT_ORPHAN_TIMEOUT_SECONDS,
    CleanupResult,
    OrphanedRunInfo,
    get_orphaned_runs,
    is_run_stale,
    cleanup_single_run,
    cleanup_orphaned_runs,
    get_orphan_statistics,
)
from api.event_recorder import EventRecorder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_test_database():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal


def create_test_spec(session, timeout_seconds=300):
    """Create a test AgentSpec."""
    spec = AgentSpec(
        id=str(uuid.uuid4()),
        name=f"test-spec-{uuid.uuid4().hex[:8]}",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=10,
        timeout_seconds=timeout_seconds,
    )
    session.add(spec)
    session.commit()
    return spec


def create_test_run(session, spec, status="running", started_at=None):
    """Create a test AgentRun."""
    run = AgentRun(
        id=str(uuid.uuid4()),
        agent_spec_id=spec.id,
        status=status,
        started_at=started_at,
    )
    session.add(run)
    session.commit()
    return run


class VerificationStep:
    """Represents a verification step with pass/fail status."""

    def __init__(self, step_num: int, description: str):
        self.step_num = step_num
        self.description = description
        self.passed = False
        self.message = ""

    def verify(self, condition: bool, message: str = ""):
        """Verify the step condition."""
        self.passed = condition
        self.message = message if message else ("PASS" if condition else "FAIL")
        return self.passed

    def __str__(self):
        status = "[PASS]" if self.passed else "[FAIL]"
        return f"Step {self.step_num}: {status} {self.description}\n         {self.message}"


def verify_all_steps():
    """Verify all 6 feature steps."""
    steps = []
    all_passed = True

    engine, SessionLocal = create_test_database()

    # =========================================================================
    # Step 1: On startup, query runs where status in (running, pending)
    # =========================================================================
    step1 = VerificationStep(1, "Query runs where status in (running, pending)")

    try:
        with SessionLocal() as session:
            spec = create_test_spec(session)
            now = datetime.now(timezone.utc)

            # Create various runs
            running_run = create_test_run(session, spec, "running", now - timedelta(hours=1))
            pending_run = create_test_run(session, spec, "pending", None)
            completed_run = create_test_run(session, spec, "completed", now - timedelta(hours=1))
            failed_run = create_test_run(session, spec, "failed", now - timedelta(hours=1))

            # Query orphaned runs
            orphaned = get_orphaned_runs(session)
            orphaned_ids = {r.id for r in orphaned}

            # Verify running and pending are found, completed and failed are not
            running_found = running_run.id in orphaned_ids
            pending_found = pending_run.id in orphaned_ids
            completed_excluded = completed_run.id not in orphaned_ids
            failed_excluded = failed_run.id not in orphaned_ids

            step1.verify(
                running_found and pending_found and completed_excluded and failed_excluded,
                f"Found running: {running_found}, Found pending: {pending_found}, "
                f"Excluded completed: {completed_excluded}, Excluded failed: {failed_excluded}"
            )
    except Exception as e:
        step1.verify(False, f"Exception: {e}")

    steps.append(step1)
    all_passed = all_passed and step1.passed

    # =========================================================================
    # Step 2: Check if run started_at is older than max timeout
    # =========================================================================
    step2 = VerificationStep(2, "Check if run started_at is older than max timeout")

    try:
        with SessionLocal() as session:
            spec = create_test_spec(session, timeout_seconds=300)  # 5 minutes
            now = datetime.now(timezone.utc)

            # Create stale and fresh runs
            stale_run = create_test_run(session, spec, "running", now - timedelta(seconds=400))
            fresh_run = create_test_run(session, spec, "running", now - timedelta(seconds=100))

            # Check staleness
            stale_is_stale, stale_age, stale_timeout = is_run_stale(stale_run, spec)
            fresh_is_stale, fresh_age, fresh_timeout = is_run_stale(fresh_run, spec)

            step2.verify(
                stale_is_stale and not fresh_is_stale,
                f"Stale run (400s old, 300s timeout) is_stale={stale_is_stale}, "
                f"Fresh run (100s old, 300s timeout) is_stale={fresh_is_stale}"
            )
    except Exception as e:
        step2.verify(False, f"Exception: {e}")

    steps.append(step2)
    all_passed = all_passed and step2.passed

    # =========================================================================
    # Step 3: For stale runs, set status to failed
    # =========================================================================
    step3 = VerificationStep(3, "For stale runs, set status to failed")

    try:
        with SessionLocal() as session:
            spec = create_test_spec(session, timeout_seconds=300)
            now = datetime.now(timezone.utc)

            # Create a stale run
            stale_run = create_test_run(session, spec, "running", now - timedelta(seconds=400))
            original_status = stale_run.status

            # Clean it up
            info = cleanup_single_run(session, stale_run, spec)
            session.commit()

            step3.verify(
                original_status == "running" and stale_run.status == "failed",
                f"Original status: {original_status}, After cleanup: {stale_run.status}"
            )
    except Exception as e:
        step3.verify(False, f"Exception: {e}")

    steps.append(step3)
    all_passed = all_passed and step3.passed

    # =========================================================================
    # Step 4: Set error to orphaned_on_restart
    # =========================================================================
    step4 = VerificationStep(4, "Set error to orphaned_on_restart")

    try:
        with SessionLocal() as session:
            spec = create_test_spec(session, timeout_seconds=300)
            now = datetime.now(timezone.utc)

            # Create and clean up a stale run
            stale_run = create_test_run(session, spec, "running", now - timedelta(seconds=400))
            cleanup_single_run(session, stale_run, spec)
            session.commit()

            step4.verify(
                stale_run.error == ORPHANED_ERROR_MESSAGE,
                f"Error field: '{stale_run.error}', Expected: '{ORPHANED_ERROR_MESSAGE}'"
            )
    except Exception as e:
        step4.verify(False, f"Exception: {e}")

    steps.append(step4)
    all_passed = all_passed and step4.passed

    # =========================================================================
    # Step 5: Record failed event
    # =========================================================================
    step5 = VerificationStep(5, "Record failed event")

    try:
        # Create a temporary directory for artifacts
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_dir = Path(tmp_dir)
            (project_dir / ".autobuildr" / "artifacts").mkdir(parents=True)

            with SessionLocal() as session:
                spec = create_test_spec(session, timeout_seconds=300)
                now = datetime.now(timezone.utc)

                # Create a stale run
                stale_run = create_test_run(session, spec, "running", now - timedelta(seconds=400))

                # Create event recorder and clean up
                recorder = EventRecorder(session, project_dir)
                cleanup_single_run(session, stale_run, spec, recorder)
                session.commit()

                # Check for failed event
                failed_events = (
                    session.query(AgentEvent)
                    .filter(
                        AgentEvent.run_id == stale_run.id,
                        AgentEvent.event_type == "failed"
                    )
                    .all()
                )

                has_failed_event = len(failed_events) == 1
                has_correct_error = False
                if has_failed_event:
                    payload = failed_events[0].payload or {}
                    has_correct_error = payload.get("error") == ORPHANED_ERROR_MESSAGE

                step5.verify(
                    has_failed_event and has_correct_error,
                    f"Failed event recorded: {has_failed_event}, "
                    f"Correct error in payload: {has_correct_error}"
                )
    except Exception as e:
        step5.verify(False, f"Exception: {e}")

    steps.append(step5)
    all_passed = all_passed and step5.passed

    # =========================================================================
    # Step 6: Log cleanup actions
    # =========================================================================
    step6 = VerificationStep(6, "Log cleanup actions")

    try:
        import io

        # Set up log capture
        log_buffer = io.StringIO()
        handler = logging.StreamHandler(log_buffer)
        handler.setLevel(logging.INFO)
        cleanup_logger = logging.getLogger("api.orphaned_run_cleanup")
        cleanup_logger.addHandler(handler)
        cleanup_logger.setLevel(logging.INFO)

        with SessionLocal() as session:
            spec = create_test_spec(session, timeout_seconds=300)
            now = datetime.now(timezone.utc)

            # Create a stale run
            stale_run = create_test_run(session, spec, "running", now - timedelta(seconds=400))

            # Run cleanup
            result = cleanup_orphaned_runs(session)

        # Get log content
        log_content = log_buffer.getvalue().lower()
        cleanup_logger.removeHandler(handler)

        has_cleanup_log = "cleanup" in log_content or "orphan" in log_content

        step6.verify(
            has_cleanup_log,
            f"Cleanup logged: {has_cleanup_log}, "
            f"Log contains: {'cleanup/orphan messages' if has_cleanup_log else 'no relevant messages'}"
        )
    except Exception as e:
        step6.verify(False, f"Exception: {e}")

    steps.append(step6)
    all_passed = all_passed and step6.passed

    # =========================================================================
    # Additional: Verify server startup integration
    # =========================================================================
    step7 = VerificationStep(7, "Cleanup is called during server startup (in main.py)")

    try:
        main_path = project_root / "server" / "main.py"
        content = main_path.read_text()

        has_import = "from api.orphaned_run_cleanup import cleanup_orphaned_runs" in content
        has_call = "cleanup_orphaned_runs(session" in content

        step7.verify(
            has_import and has_call,
            f"Import present: {has_import}, Function call present: {has_call}"
        )
    except Exception as e:
        step7.verify(False, f"Exception: {e}")

    steps.append(step7)
    all_passed = all_passed and step7.passed

    # =========================================================================
    # Print results
    # =========================================================================
    print("\n" + "=" * 70)
    print("Feature #79: Orphaned Run Cleanup on Startup - Verification Results")
    print("=" * 70 + "\n")

    for step in steps:
        print(step)
        print()

    print("=" * 70)
    passed_count = sum(1 for s in steps if s.passed)
    total_count = len(steps)
    print(f"RESULT: {passed_count}/{total_count} steps passed")

    if all_passed:
        print("STATUS: ALL VERIFICATION STEPS PASSED")
    else:
        print("STATUS: SOME STEPS FAILED")

    print("=" * 70 + "\n")

    # Cleanup
    engine.dispose()

    return all_passed


if __name__ == "__main__":
    success = verify_all_steps()
    sys.exit(0 if success else 1)
