"""
Orphaned Run Cleanup Service
============================

On server startup, cleans up orphaned AgentRuns that were stuck
in running/pending status from a previous server instance.

Runs can become orphaned when:
- Server crashed during execution
- Server was forcefully terminated
- Process was killed without graceful shutdown

This service identifies stale runs and marks them as failed with
the 'orphaned_on_restart' error message, ensuring the system
state is consistent after restart.

Usage:
    from api.orphaned_run_cleanup import cleanup_orphaned_runs, CleanupResult

    # In server startup:
    result = cleanup_orphaned_runs(session, project_dir="/path/to/project")
    print(f"Cleaned {result.cleaned_count} orphaned runs")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.agentspec_models import AgentRun, AgentSpec
from api.event_recorder import EventRecorder

# Configure logging
_logger = logging.getLogger(__name__)

# Error message for orphaned runs
ORPHANED_ERROR_MESSAGE = "orphaned_on_restart"

# Default timeout for runs without a spec (fallback)
DEFAULT_ORPHAN_TIMEOUT_SECONDS = 3600  # 1 hour


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


@dataclass
class OrphanedRunInfo:
    """Information about a single orphaned run that was cleaned up."""

    run_id: str
    spec_id: str | None
    spec_name: str | None
    original_status: str
    started_at: datetime | None
    age_seconds: float | None
    timeout_seconds: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "original_status": self.original_status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "age_seconds": self.age_seconds,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class CleanupResult:
    """Result of the orphaned run cleanup operation."""

    # Total runs found in running/pending status
    total_found: int = 0

    # Number of runs actually cleaned (marked as failed)
    cleaned_count: int = 0

    # Number of runs skipped (not stale yet)
    skipped_count: int = 0

    # Details of each cleaned run
    cleaned_runs: list[OrphanedRunInfo] = field(default_factory=list)

    # Any errors encountered during cleanup
    errors: list[str] = field(default_factory=list)

    # Timestamp when cleanup was performed
    cleanup_timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "total_found": self.total_found,
            "cleaned_count": self.cleaned_count,
            "skipped_count": self.skipped_count,
            "cleaned_runs": [r.to_dict() for r in self.cleaned_runs],
            "errors": self.errors,
            "cleanup_timestamp": self.cleanup_timestamp.isoformat(),
        }


def get_orphaned_runs(session: Session) -> list[AgentRun]:
    """
    Query all runs that are in running or pending status.

    These runs may be orphaned from a previous server instance.

    Args:
        session: SQLAlchemy database session

    Returns:
        List of AgentRun objects in running or pending status
    """
    orphaned_statuses = ("running", "pending")

    runs = (
        session.query(AgentRun)
        .filter(AgentRun.status.in_(orphaned_statuses))
        .all()
    )

    _logger.debug(
        "Found %d runs in %s status",
        len(runs),
        "/".join(orphaned_statuses)
    )

    return runs


def is_run_stale(
    run: AgentRun,
    spec: AgentSpec | None,
    current_time: datetime | None = None,
) -> tuple[bool, float | None, int]:
    """
    Check if a run is stale (older than its timeout).

    A run is considered stale if:
    - It has a started_at timestamp that is older than its spec's timeout_seconds
    - OR if pending without started_at, it's considered stale (should have started)

    Args:
        run: The AgentRun to check
        spec: The associated AgentSpec (may be None if spec was deleted)
        current_time: Current time (defaults to UTC now)

    Returns:
        Tuple of (is_stale, age_seconds, timeout_seconds)
        - is_stale: True if the run should be cleaned up
        - age_seconds: Age of the run in seconds (None if no started_at)
        - timeout_seconds: The timeout that was used for comparison
    """
    if current_time is None:
        current_time = _utc_now()

    # Get timeout from spec or use default
    timeout_seconds = (
        spec.timeout_seconds if spec else DEFAULT_ORPHAN_TIMEOUT_SECONDS
    )

    # If run has no started_at and is pending, it's orphaned
    if run.started_at is None:
        if run.status == "pending":
            # Pending runs without started_at are considered stale
            # (they should have either started or been cleaned up)
            _logger.debug(
                "Run %s is pending without started_at, considered stale",
                run.id
            )
            return True, None, timeout_seconds
        else:
            # Running without started_at is an inconsistent state
            _logger.warning(
                "Run %s is %s without started_at, marking as stale",
                run.id,
                run.status
            )
            return True, None, timeout_seconds

    # Ensure both timestamps are timezone-aware for comparison
    started_at = run.started_at
    if started_at.tzinfo is None:
        # Assume UTC if no timezone info
        started_at = started_at.replace(tzinfo=timezone.utc)

    # Calculate age
    age = current_time - started_at
    age_seconds = age.total_seconds()

    # Check if older than timeout
    is_stale = age_seconds > timeout_seconds

    _logger.debug(
        "Run %s age: %.1fs, timeout: %ds, stale: %s",
        run.id,
        age_seconds,
        timeout_seconds,
        is_stale
    )

    return is_stale, age_seconds, timeout_seconds


def cleanup_single_run(
    session: Session,
    run: AgentRun,
    spec: AgentSpec | None,
    event_recorder: EventRecorder | None = None,
) -> OrphanedRunInfo:
    """
    Clean up a single orphaned run by marking it as failed.

    Args:
        session: SQLAlchemy database session
        run: The orphaned AgentRun to clean up
        spec: The associated AgentSpec (may be None)
        event_recorder: Optional EventRecorder for recording events

    Returns:
        OrphanedRunInfo with details about the cleanup
    """
    # Capture original state for logging
    original_status = run.status
    started_at = run.started_at

    # Get age and timeout info
    _, age_seconds, timeout_seconds = is_run_stale(run, spec)

    # Mark run as failed with orphaned error message
    run.status = "failed"
    run.error = ORPHANED_ERROR_MESSAGE
    run.completed_at = _utc_now()

    _logger.info(
        "Marking orphaned run %s as failed: "
        "was %s, started_at=%s, spec=%s",
        run.id,
        original_status,
        started_at.isoformat() if started_at else "None",
        spec.name if spec else "None"
    )

    # Record failed event if we have a recorder
    if event_recorder:
        try:
            event_recorder.record_failed(
                run_id=run.id,
                error=ORPHANED_ERROR_MESSAGE,
                error_type="OrphanedRunError",
            )
        except Exception as e:
            _logger.warning(
                "Failed to record event for orphaned run %s: %s",
                run.id,
                e
            )

    # Create info object
    info = OrphanedRunInfo(
        run_id=run.id,
        spec_id=spec.id if spec else None,
        spec_name=spec.name if spec else None,
        original_status=original_status,
        started_at=started_at,
        age_seconds=age_seconds,
        timeout_seconds=timeout_seconds,
    )

    return info


def cleanup_orphaned_runs(
    session: Session,
    project_dir: str | Path | None = None,
    *,
    force_cleanup_all: bool = False,
) -> CleanupResult:
    """
    Clean up all orphaned runs stuck in running/pending status.

    This should be called during server startup to ensure consistent state.

    Args:
        session: SQLAlchemy database session
        project_dir: Project directory for artifact storage (for event recording)
        force_cleanup_all: If True, clean up ALL running/pending runs
                          regardless of age. Use with caution.

    Returns:
        CleanupResult with details about the cleanup operation

    Example:
        >>> from api.database import create_database
        >>> from api.orphaned_run_cleanup import cleanup_orphaned_runs
        >>>
        >>> engine, SessionLocal = create_database(project_dir)
        >>> with SessionLocal() as session:
        ...     result = cleanup_orphaned_runs(session, project_dir)
        ...     print(f"Cleaned {result.cleaned_count} orphaned runs")
    """
    result = CleanupResult()
    current_time = _utc_now()

    _logger.info("Starting orphaned run cleanup at %s", current_time.isoformat())

    # Create event recorder if project_dir provided
    event_recorder = None
    if project_dir:
        event_recorder = EventRecorder(session, project_dir)

    try:
        # Step 1: Query runs where status in (running, pending)
        orphaned_runs = get_orphaned_runs(session)
        result.total_found = len(orphaned_runs)

        if result.total_found == 0:
            _logger.info("No orphaned runs found")
            return result

        _logger.info(
            "Found %d potential orphaned runs to process",
            result.total_found
        )

        # Step 2-5: Process each run
        for run in orphaned_runs:
            try:
                # Get associated spec (may be None if deleted)
                spec = (
                    session.query(AgentSpec)
                    .filter(AgentSpec.id == run.agent_spec_id)
                    .first()
                )

                # Check if run is stale
                is_stale, _, _ = is_run_stale(run, spec, current_time)

                if not is_stale and not force_cleanup_all:
                    # Run is not stale yet, skip it
                    _logger.debug(
                        "Skipping run %s: not stale yet",
                        run.id
                    )
                    result.skipped_count += 1
                    continue

                # Clean up the run
                info = cleanup_single_run(
                    session, run, spec, event_recorder
                )
                result.cleaned_runs.append(info)
                result.cleaned_count += 1

            except Exception as e:
                error_msg = f"Error cleaning run {run.id}: {e}"
                _logger.error(error_msg)
                result.errors.append(error_msg)

        # Commit all changes
        session.commit()

        # Step 6: Log cleanup summary
        _logger.info(
            "Orphaned run cleanup complete: "
            "found=%d, cleaned=%d, skipped=%d, errors=%d",
            result.total_found,
            result.cleaned_count,
            result.skipped_count,
            len(result.errors)
        )

        if result.cleaned_count > 0:
            _logger.info(
                "Cleaned orphaned runs: %s",
                ", ".join(info.run_id for info in result.cleaned_runs)
            )

    except Exception as e:
        error_msg = f"Unexpected error during cleanup: {e}"
        _logger.error(error_msg)
        result.errors.append(error_msg)
        # Rollback on error
        session.rollback()

    return result


def get_orphan_statistics(session: Session) -> dict[str, Any]:
    """
    Get statistics about potential orphaned runs.

    Useful for monitoring and diagnostics without actually cleaning up.

    Args:
        session: SQLAlchemy database session

    Returns:
        Dictionary with orphan statistics
    """
    from sqlalchemy import func

    stats = {
        "running_count": 0,
        "pending_count": 0,
        "total_orphaned": 0,
        "oldest_running": None,
        "oldest_pending": None,
    }

    # Count by status
    running_count = (
        session.query(func.count(AgentRun.id))
        .filter(AgentRun.status == "running")
        .scalar()
    )
    pending_count = (
        session.query(func.count(AgentRun.id))
        .filter(AgentRun.status == "pending")
        .scalar()
    )

    stats["running_count"] = running_count or 0
    stats["pending_count"] = pending_count or 0
    stats["total_orphaned"] = stats["running_count"] + stats["pending_count"]

    # Find oldest running run
    oldest_running = (
        session.query(AgentRun.started_at)
        .filter(AgentRun.status == "running")
        .filter(AgentRun.started_at.isnot(None))
        .order_by(AgentRun.started_at.asc())
        .first()
    )
    if oldest_running and oldest_running[0]:
        stats["oldest_running"] = oldest_running[0].isoformat()

    # Find oldest pending run
    oldest_pending = (
        session.query(AgentRun.created_at)
        .filter(AgentRun.status == "pending")
        .order_by(AgentRun.created_at.asc())
        .first()
    )
    if oldest_pending and oldest_pending[0]:
        stats["oldest_pending"] = oldest_pending[0].isoformat()

    return stats
