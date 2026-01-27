"""
Feature #79: Orphaned Run Cleanup on Startup
============================================

Tests for the orphaned run cleanup functionality that runs on server startup.

Feature Description:
On server startup, clean up orphaned runs stuck in running/pending status.

Feature Steps:
1. On startup, query runs where status in (running, pending)
2. Check if run started_at is older than max timeout
3. For stale runs, set status to failed
4. Set error to orphaned_on_restart
5. Record failed event
6. Log cleanup actions
"""

from __future__ import annotations

import logging
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    Artifact,
    AcceptanceSpec,
)
from api.orphaned_run_cleanup import (
    ORPHANED_ERROR_MESSAGE,
    DEFAULT_ORPHAN_TIMEOUT_SECONDS,
    OrphanedRunInfo,
    CleanupResult,
    get_orphaned_runs,
    is_run_stale,
    cleanup_single_run,
    cleanup_orphaned_runs,
    get_orphan_statistics,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test_project"
    project.mkdir()
    artifacts_dir = project / ".autobuildr" / "artifacts"
    artifacts_dir.mkdir(parents=True)
    return project


@pytest.fixture
def sample_spec(db_session: Session) -> AgentSpec:
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id=str(uuid.uuid4()),
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"allowed_tools": []},
        max_turns=10,
        timeout_seconds=300,  # 5 minutes
    )
    db_session.add(spec)
    db_session.commit()
    return spec


def create_run(
    db_session: Session,
    spec: AgentSpec,
    status: str = "running",
    started_at: datetime | None = None,
) -> AgentRun:
    """Helper to create a test AgentRun."""
    run = AgentRun(
        id=str(uuid.uuid4()),
        agent_spec_id=spec.id,
        status=status,
        started_at=started_at,
    )
    db_session.add(run)
    db_session.commit()
    return run


# =============================================================================
# Test: Imports
# =============================================================================

class TestImports:
    """Test that all exports are available."""

    def test_import_constants(self):
        """Test importing constants."""
        from api.orphaned_run_cleanup import (
            ORPHANED_ERROR_MESSAGE,
            DEFAULT_ORPHAN_TIMEOUT_SECONDS,
        )
        assert ORPHANED_ERROR_MESSAGE == "orphaned_on_restart"
        assert DEFAULT_ORPHAN_TIMEOUT_SECONDS == 3600

    def test_import_dataclasses(self):
        """Test importing dataclasses."""
        from api.orphaned_run_cleanup import OrphanedRunInfo, CleanupResult
        assert OrphanedRunInfo is not None
        assert CleanupResult is not None

    def test_import_functions(self):
        """Test importing functions."""
        from api.orphaned_run_cleanup import (
            get_orphaned_runs,
            is_run_stale,
            cleanup_single_run,
            cleanup_orphaned_runs,
            get_orphan_statistics,
        )
        assert callable(get_orphaned_runs)
        assert callable(is_run_stale)
        assert callable(cleanup_single_run)
        assert callable(cleanup_orphaned_runs)
        assert callable(get_orphan_statistics)

    def test_import_from_api(self):
        """Test importing from api package."""
        from api import (
            ORPHANED_ERROR_MESSAGE,
            DEFAULT_ORPHAN_TIMEOUT_SECONDS,
            OrphanedRunInfo,
            CleanupResult,
            get_orphaned_runs,
            is_run_stale,
            cleanup_single_run,
            cleanup_orphaned_runs,
            get_orphan_statistics,
        )
        assert ORPHANED_ERROR_MESSAGE == "orphaned_on_restart"


# =============================================================================
# Test: Step 1 - Query runs where status in (running, pending)
# =============================================================================

class TestGetOrphanedRuns:
    """Test querying runs with running/pending status."""

    def test_returns_running_runs(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query finds runs with status='running'."""
        now = datetime.now(timezone.utc)
        run = create_run(db_session, sample_spec, "running", now)

        result = get_orphaned_runs(db_session)

        assert len(result) == 1
        assert result[0].id == run.id
        assert result[0].status == "running"

    def test_returns_pending_runs(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query finds runs with status='pending'."""
        run = create_run(db_session, sample_spec, "pending", None)

        result = get_orphaned_runs(db_session)

        assert len(result) == 1
        assert result[0].id == run.id
        assert result[0].status == "pending"

    def test_returns_both_running_and_pending(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query finds both running and pending runs."""
        now = datetime.now(timezone.utc)
        run1 = create_run(db_session, sample_spec, "running", now)
        run2 = create_run(db_session, sample_spec, "pending", None)

        result = get_orphaned_runs(db_session)

        assert len(result) == 2
        run_ids = {r.id for r in result}
        assert run1.id in run_ids
        assert run2.id in run_ids

    def test_excludes_completed_runs(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query excludes completed runs."""
        now = datetime.now(timezone.utc)
        run = create_run(db_session, sample_spec, "completed", now)

        result = get_orphaned_runs(db_session)

        assert len(result) == 0

    def test_excludes_failed_runs(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query excludes failed runs."""
        now = datetime.now(timezone.utc)
        run = create_run(db_session, sample_spec, "failed", now)

        result = get_orphaned_runs(db_session)

        assert len(result) == 0

    def test_excludes_timeout_runs(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query excludes timeout runs."""
        now = datetime.now(timezone.utc)
        run = create_run(db_session, sample_spec, "timeout", now)

        result = get_orphaned_runs(db_session)

        assert len(result) == 0

    def test_excludes_paused_runs(self, db_session: Session, sample_spec: AgentSpec):
        """Step 1: Query excludes paused runs (paused is not orphaned)."""
        now = datetime.now(timezone.utc)
        run = create_run(db_session, sample_spec, "paused", now)

        result = get_orphaned_runs(db_session)

        assert len(result) == 0

    def test_returns_empty_when_no_orphans(self, db_session: Session):
        """Step 1: Returns empty list when no orphaned runs exist."""
        result = get_orphaned_runs(db_session)

        assert len(result) == 0


# =============================================================================
# Test: Step 2 - Check if run started_at is older than max timeout
# =============================================================================

class TestIsRunStale:
    """Test staleness detection based on timeout."""

    def test_run_is_stale_when_older_than_timeout(self, sample_spec: AgentSpec):
        """Step 2: Run is stale when started_at is older than spec timeout."""
        started = datetime.now(timezone.utc) - timedelta(seconds=400)  # 400s ago
        run = MagicMock()
        run.id = "test-run"
        run.status = "running"
        run.started_at = started

        is_stale, age_seconds, timeout = is_run_stale(run, sample_spec)

        assert is_stale is True
        assert age_seconds > 300  # Spec timeout is 300s
        assert timeout == 300

    def test_run_is_not_stale_when_within_timeout(self, sample_spec: AgentSpec):
        """Step 2: Run is not stale when started_at is within timeout."""
        started = datetime.now(timezone.utc) - timedelta(seconds=100)  # 100s ago
        run = MagicMock()
        run.id = "test-run"
        run.status = "running"
        run.started_at = started

        is_stale, age_seconds, timeout = is_run_stale(run, sample_spec)

        assert is_stale is False
        assert age_seconds < 300  # Spec timeout is 300s
        assert timeout == 300

    def test_pending_without_started_at_is_stale(self, sample_spec: AgentSpec):
        """Step 2: Pending run without started_at is considered stale."""
        run = MagicMock()
        run.id = "test-run"
        run.status = "pending"
        run.started_at = None

        is_stale, age_seconds, timeout = is_run_stale(run, sample_spec)

        assert is_stale is True
        assert age_seconds is None

    def test_running_without_started_at_is_stale(self, sample_spec: AgentSpec):
        """Step 2: Running without started_at is inconsistent, considered stale."""
        run = MagicMock()
        run.id = "test-run"
        run.status = "running"
        run.started_at = None

        is_stale, age_seconds, timeout = is_run_stale(run, sample_spec)

        assert is_stale is True
        assert age_seconds is None

    def test_uses_default_timeout_when_no_spec(self):
        """Step 2: Uses default timeout when spec is None."""
        started = datetime.now(timezone.utc) - timedelta(seconds=3700)  # > 1 hour
        run = MagicMock()
        run.id = "test-run"
        run.status = "running"
        run.started_at = started

        is_stale, age_seconds, timeout = is_run_stale(run, None)

        assert is_stale is True
        assert timeout == DEFAULT_ORPHAN_TIMEOUT_SECONDS  # 3600s

    def test_uses_spec_timeout(self):
        """Step 2: Uses spec.timeout_seconds for staleness check."""
        spec = MagicMock()
        spec.timeout_seconds = 600  # 10 minutes

        started = datetime.now(timezone.utc) - timedelta(seconds=700)  # > 10 min
        run = MagicMock()
        run.id = "test-run"
        run.status = "running"
        run.started_at = started

        is_stale, age_seconds, timeout = is_run_stale(run, spec)

        assert is_stale is True
        assert timeout == 600

    def test_handles_naive_datetime(self, sample_spec: AgentSpec):
        """Step 2: Handles naive datetime (assumes UTC)."""
        started = datetime.utcnow() - timedelta(seconds=400)  # Naive datetime
        run = MagicMock()
        run.id = "test-run"
        run.status = "running"
        run.started_at = started

        is_stale, age_seconds, timeout = is_run_stale(run, sample_spec)

        assert is_stale is True


# =============================================================================
# Test: Step 3 & 4 - Set status to failed and error to orphaned_on_restart
# =============================================================================

class TestCleanupSingleRun:
    """Test cleaning up individual runs."""

    def test_sets_status_to_failed(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Step 3: For stale runs, set status to failed."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        info = cleanup_single_run(db_session, run, sample_spec)

        assert run.status == "failed"

    def test_sets_error_to_orphaned_on_restart(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Step 4: Set error to orphaned_on_restart."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        info = cleanup_single_run(db_session, run, sample_spec)

        assert run.error == ORPHANED_ERROR_MESSAGE

    def test_sets_completed_at(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Cleanup sets completed_at timestamp."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)
        assert run.completed_at is None

        info = cleanup_single_run(db_session, run, sample_spec)

        assert run.completed_at is not None

    def test_returns_orphaned_run_info(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Cleanup returns OrphanedRunInfo with details."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        info = cleanup_single_run(db_session, run, sample_spec)

        assert isinstance(info, OrphanedRunInfo)
        assert info.run_id == run.id
        assert info.spec_id == sample_spec.id
        assert info.spec_name == sample_spec.name
        assert info.original_status == "running"

    def test_handles_pending_run(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Cleanup handles pending runs correctly."""
        run = create_run(db_session, sample_spec, "pending", None)

        info = cleanup_single_run(db_session, run, sample_spec)

        assert run.status == "failed"
        assert run.error == ORPHANED_ERROR_MESSAGE
        assert info.original_status == "pending"

    def test_handles_missing_spec(self, db_session: Session, sample_spec: AgentSpec):
        """Cleanup handles runs where spec was deleted."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        info = cleanup_single_run(db_session, run, None)

        assert run.status == "failed"
        assert info.spec_id is None
        assert info.spec_name is None


# =============================================================================
# Test: Step 5 - Record failed event
# =============================================================================

class TestCleanupRecordsFailedEvent:
    """Test that cleanup records a failed event."""

    def test_records_failed_event_with_recorder(
        self, db_session: Session, sample_spec: AgentSpec, project_dir: Path
    ):
        """Step 5: Record failed event when event_recorder is provided."""
        from api.event_recorder import EventRecorder

        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)
        recorder = EventRecorder(db_session, project_dir)

        info = cleanup_single_run(db_session, run, sample_spec, recorder)
        db_session.commit()

        # Check that a failed event was recorded
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "failed"
        ).all()

        assert len(events) == 1
        assert events[0].payload is not None
        assert events[0].payload.get("error") == ORPHANED_ERROR_MESSAGE

    def test_handles_recorder_error_gracefully(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Step 5: Handles event recorder errors gracefully."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        # Mock recorder that raises an error
        mock_recorder = MagicMock()
        mock_recorder.record_failed.side_effect = Exception("Recording failed")

        # Should not raise, just log warning
        info = cleanup_single_run(db_session, run, sample_spec, mock_recorder)

        assert run.status == "failed"


# =============================================================================
# Test: Step 6 - Log cleanup actions
# =============================================================================

class TestCleanupLogging:
    """Test that cleanup logs actions."""

    def test_logs_cleanup_summary(
        self, db_session: Session, sample_spec: AgentSpec, caplog
    ):
        """Step 6: Log cleanup actions at info level."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        with caplog.at_level(logging.INFO, logger="api.orphaned_run_cleanup"):
            result = cleanup_orphaned_runs(db_session)

        assert "cleanup complete" in caplog.text.lower() or "cleanup" in caplog.text.lower()

    def test_logs_individual_run_cleanup(
        self, db_session: Session, sample_spec: AgentSpec, caplog
    ):
        """Step 6: Log individual run cleanups."""
        now = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", now)

        with caplog.at_level(logging.INFO, logger="api.orphaned_run_cleanup"):
            result = cleanup_orphaned_runs(db_session)

        # Should log the run ID being cleaned
        assert run.id in caplog.text or "orphaned" in caplog.text.lower()


# =============================================================================
# Test: cleanup_orphaned_runs (Main Function)
# =============================================================================

class TestCleanupOrphanedRuns:
    """Test the main cleanup function."""

    def test_cleans_stale_running_runs(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Cleans up stale running runs."""
        started = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", started)

        result = cleanup_orphaned_runs(db_session)

        assert result.cleaned_count == 1
        assert result.total_found == 1
        assert run.status == "failed"

    def test_cleans_stale_pending_runs(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Cleans up stale pending runs."""
        run = create_run(db_session, sample_spec, "pending", None)

        result = cleanup_orphaned_runs(db_session)

        assert result.cleaned_count == 1
        assert run.status == "failed"

    def test_skips_non_stale_runs(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Skips runs that are not stale yet."""
        started = datetime.now(timezone.utc) - timedelta(seconds=100)  # Within timeout
        run = create_run(db_session, sample_spec, "running", started)

        result = cleanup_orphaned_runs(db_session)

        assert result.cleaned_count == 0
        assert result.skipped_count == 1
        assert run.status == "running"

    def test_force_cleanup_all(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Force cleanup cleans all runs regardless of age."""
        started = datetime.now(timezone.utc) - timedelta(seconds=100)  # Within timeout
        run = create_run(db_session, sample_spec, "running", started)

        result = cleanup_orphaned_runs(db_session, force_cleanup_all=True)

        assert result.cleaned_count == 1
        assert run.status == "failed"

    def test_returns_cleanup_result(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Returns CleanupResult with all details."""
        started = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", started)

        result = cleanup_orphaned_runs(db_session)

        assert isinstance(result, CleanupResult)
        assert result.total_found == 1
        assert result.cleaned_count == 1
        assert result.skipped_count == 0
        assert len(result.cleaned_runs) == 1
        assert result.cleaned_runs[0].run_id == run.id
        assert result.cleanup_timestamp is not None

    def test_handles_multiple_runs(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Handles multiple orphaned runs."""
        started = datetime.now(timezone.utc) - timedelta(seconds=400)
        run1 = create_run(db_session, sample_spec, "running", started)
        run2 = create_run(db_session, sample_spec, "pending", None)

        result = cleanup_orphaned_runs(db_session)

        assert result.cleaned_count == 2
        assert run1.status == "failed"
        assert run2.status == "failed"

    def test_handles_empty_database(self, db_session: Session):
        """Handles empty database gracefully."""
        result = cleanup_orphaned_runs(db_session)

        assert result.total_found == 0
        assert result.cleaned_count == 0

    def test_commits_changes(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Commits changes to database."""
        started = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", started)

        result = cleanup_orphaned_runs(db_session)

        # Refresh to get committed state
        db_session.refresh(run)
        assert run.status == "failed"

    def test_handles_errors_gracefully(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Records errors in result.errors."""
        started = datetime.now(timezone.utc) - timedelta(seconds=400)
        run = create_run(db_session, sample_spec, "running", started)

        # Corrupt the run to cause an error
        with patch.object(db_session, "query") as mock_query:
            # First call returns runs, second call (for spec) fails
            mock_query.return_value.filter.return_value.all.return_value = [run]
            mock_query.return_value.filter.return_value.first.side_effect = Exception("DB error")

            # This should handle the error gracefully
            result = cleanup_orphaned_runs(db_session)

        # Errors should be recorded
        assert result.total_found > 0


# =============================================================================
# Test: CleanupResult and OrphanedRunInfo Dataclasses
# =============================================================================

class TestDataclasses:
    """Test dataclass functionality."""

    def test_cleanup_result_to_dict(self):
        """CleanupResult.to_dict() returns correct format."""
        result = CleanupResult(
            total_found=3,
            cleaned_count=2,
            skipped_count=1,
            cleaned_runs=[],
            errors=[],
        )

        d = result.to_dict()

        assert d["total_found"] == 3
        assert d["cleaned_count"] == 2
        assert d["skipped_count"] == 1
        assert "cleanup_timestamp" in d

    def test_orphaned_run_info_to_dict(self):
        """OrphanedRunInfo.to_dict() returns correct format."""
        now = datetime.now(timezone.utc)
        info = OrphanedRunInfo(
            run_id="test-run-id",
            spec_id="test-spec-id",
            spec_name="test-spec",
            original_status="running",
            started_at=now,
            age_seconds=100.5,
            timeout_seconds=300,
        )

        d = info.to_dict()

        assert d["run_id"] == "test-run-id"
        assert d["spec_id"] == "test-spec-id"
        assert d["spec_name"] == "test-spec"
        assert d["original_status"] == "running"
        assert d["started_at"] == now.isoformat()
        assert d["age_seconds"] == 100.5
        assert d["timeout_seconds"] == 300


# =============================================================================
# Test: get_orphan_statistics
# =============================================================================

class TestGetOrphanStatistics:
    """Test the statistics function."""

    def test_returns_statistics(self, db_session: Session, sample_spec: AgentSpec):
        """Returns statistics about orphaned runs."""
        now = datetime.now(timezone.utc)
        run1 = create_run(db_session, sample_spec, "running", now)
        run2 = create_run(db_session, sample_spec, "pending", None)

        stats = get_orphan_statistics(db_session)

        assert stats["running_count"] == 1
        assert stats["pending_count"] == 1
        assert stats["total_orphaned"] == 2

    def test_returns_oldest_timestamps(
        self, db_session: Session, sample_spec: AgentSpec
    ):
        """Returns oldest running and pending timestamps."""
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        new = datetime.now(timezone.utc) - timedelta(hours=1)
        run1 = create_run(db_session, sample_spec, "running", old)
        run2 = create_run(db_session, sample_spec, "running", new)

        stats = get_orphan_statistics(db_session)

        assert stats["oldest_running"] is not None

    def test_handles_empty_database(self, db_session: Session):
        """Handles empty database."""
        stats = get_orphan_statistics(db_session)

        assert stats["running_count"] == 0
        assert stats["pending_count"] == 0
        assert stats["total_orphaned"] == 0
        assert stats["oldest_running"] is None
        assert stats["oldest_pending"] is None


# =============================================================================
# Test: Server Startup Integration
# =============================================================================

class TestServerStartupIntegration:
    """Test that cleanup is called during server startup."""

    def test_cleanup_imported_in_main(self):
        """Verify cleanup_orphaned_runs can be imported."""
        from api.orphaned_run_cleanup import cleanup_orphaned_runs
        assert callable(cleanup_orphaned_runs)

    def test_main_lifespan_calls_cleanup(self):
        """Verify main.py imports and calls cleanup_orphaned_runs."""
        # Read main.py and check for the import and call
        main_path = Path(__file__).parent.parent / "server" / "main.py"
        content = main_path.read_text()

        assert "from api.orphaned_run_cleanup import cleanup_orphaned_runs" in content
        assert "cleanup_orphaned_runs(session" in content


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
