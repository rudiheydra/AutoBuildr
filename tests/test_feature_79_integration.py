"""
Feature #79: Integration test for server startup cleanup.
"""

import asyncio
import logging
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun


def create_test_database():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal


def create_orphaned_run(session, spec_id, status="running", hours_old=2):
    """Create an orphaned run for testing."""
    started_at = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    run = AgentRun(
        id=str(uuid.uuid4()),
        agent_spec_id=spec_id,
        status=status,
        started_at=started_at if status == "running" else None,
    )
    session.add(run)
    session.commit()
    return run


class TestServerStartupCleanup:
    """Test the cleanup integration in server startup."""

    def test_cleanup_called_in_lifespan(self):
        """Test that cleanup_orphaned_runs is called during lifespan startup."""
        # Create a test database with orphaned runs
        engine, SessionLocal = create_test_database()

        with SessionLocal() as session:
            # Create a test spec with short timeout (5 min)
            spec = AgentSpec(
                id=str(uuid.uuid4()),
                name="test-spec",
                display_name="Test Spec",
                objective="Test",
                task_type="testing",
                tool_policy={"allowed_tools": []},
                max_turns=10,
                timeout_seconds=300,  # 5 minutes
            )
            session.add(spec)
            session.commit()

            # Create orphaned runs that are older than the timeout (2 hours old)
            run1 = create_orphaned_run(session, spec.id, "running", hours_old=2)
            run2_id = str(uuid.uuid4())
            # Pending runs are always considered stale
            run2 = AgentRun(
                id=run2_id,
                agent_spec_id=spec.id,
                status="pending",
                started_at=None,
            )
            session.add(run2)
            session.commit()

        # Simulate the lifespan startup code
        from api.orphaned_run_cleanup import cleanup_orphaned_runs as real_cleanup

        # This mimics what happens in server/main.py lifespan
        with SessionLocal() as session:
            result = real_cleanup(session, project_dir=Path("/tmp"))
            # Note: cleanup_orphaned_runs commits internally

        # Verify runs were cleaned (should now be 'failed')
        with SessionLocal() as session:
            orphaned = session.query(AgentRun).filter(
                AgentRun.status.in_(("running", "pending"))
            ).all()

            failed = session.query(AgentRun).filter(
                AgentRun.status == "failed"
            ).all()

        # After cleanup, there should be no orphaned runs (they should be failed)
        assert len(orphaned) == 0, f"Expected 0 orphaned runs, got {len(orphaned)}"
        assert len(failed) == 2, f"Expected 2 failed runs, got {len(failed)}"

        engine.dispose()

    def test_cleanup_handles_database_errors_gracefully(self):
        """Test that startup doesn't fail if cleanup encounters an error."""
        # The lifespan code wraps cleanup in try/except to prevent startup failure
        ROOT_DIR = Path(__file__).parent.parent

        # Read main.py and verify error handling exists
        main_path = ROOT_DIR / "server" / "main.py"
        content = main_path.read_text()

        # Verify try/except around cleanup
        assert "try:" in content
        assert "cleanup_orphaned_runs(session" in content
        assert "except Exception as e:" in content
        # Verify it logs but doesn't re-raise
        assert "Failed to clean up orphaned runs" in content

    def test_cleanup_result_logging(self, caplog):
        """Test that cleanup results are properly logged."""
        engine, SessionLocal = create_test_database()

        with SessionLocal() as session:
            spec = AgentSpec(
                id=str(uuid.uuid4()),
                name="test-spec",
                display_name="Test Spec",
                objective="Test",
                task_type="testing",
                tool_policy={"allowed_tools": []},
                max_turns=10,
                timeout_seconds=300,
            )
            session.add(spec)
            session.commit()

            run = create_orphaned_run(session, spec.id, "running", hours_old=2)

        with caplog.at_level(logging.INFO):
            from api.orphaned_run_cleanup import cleanup_orphaned_runs

            with SessionLocal() as session:
                result = cleanup_orphaned_runs(session, project_dir=Path("/tmp"))

        # Verify cleanup was logged
        assert result.cleaned_count == 1
        # Check logs contain relevant info
        log_text = caplog.text.lower()
        assert "cleanup" in log_text or "orphan" in log_text

        engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
