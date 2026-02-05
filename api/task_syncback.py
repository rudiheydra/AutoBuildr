"""
Task Sync-Back
==============

Syncs Claude Code Task events back to the Feature database.

This implements the sync-back pattern from the Task Interface design:
- Task status changes map to Feature state updates
- Task completion → Feature.passes = True
- Task failure → Record error, reset in_progress

The sync-back layer ensures:
1. Feature state stays in sync with Task execution
2. Progress is persisted across sessions
3. Audit trail is maintained via AgentEvents

Usage:
    from api.task_syncback import TaskSyncBack

    syncback = TaskSyncBack(project_dir, session)
    syncback.on_task_completed(task_id, metadata)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.database import Feature
from api.agentspec_models import AgentEvent, AgentRun

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    feature_id: int | None
    feature_name: str | None
    message: str
    acceptance_failed: bool = False
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "message": self.message,
            "acceptance_failed": self.acceptance_failed,
            "error_message": self.error_message,
        }


class TaskSyncBack:
    """
    Sync Claude Code Task events back to Feature database.

    Handles the following Task lifecycle events:
    - Task started → Feature.in_progress = True
    - Task completed → Feature.passes = True, in_progress = False
    - Task failed → Feature.in_progress = False, record error

    Also supports running acceptance validators when tasks complete,
    implementing the Ralph Wiggum correction loop.
    """

    def __init__(self, project_dir: Path, session: Session):
        """
        Initialize the TaskSyncBack.

        Args:
            project_dir: Root project directory
            session: SQLAlchemy session for database access
        """
        self.project_dir = Path(project_dir).resolve()
        self.session = session

    def on_task_started(
        self,
        task_id: str,
        metadata: dict[str, Any],
    ) -> SyncResult:
        """
        Handle Task started event.

        Updates the linked Feature to in_progress = True.

        Args:
            task_id: Claude Code Task ID
            metadata: Task metadata (must contain feature_id)

        Returns:
            SyncResult indicating success/failure
        """
        feature_id = metadata.get("feature_id")
        if feature_id is None:
            return SyncResult(
                success=False,
                feature_id=None,
                feature_name=None,
                message="No feature_id in task metadata",
            )

        feature = self.session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            return SyncResult(
                success=False,
                feature_id=feature_id,
                feature_name=None,
                message=f"Feature {feature_id} not found",
            )

        # Update feature state
        feature.in_progress = True
        self.session.commit()

        _logger.info(
            "Task %s started: Feature #%d '%s' marked in_progress",
            task_id, feature.id, feature.name,
        )

        return SyncResult(
            success=True,
            feature_id=feature.id,
            feature_name=feature.name,
            message=f"Feature #{feature.id} marked in_progress",
        )

    def on_task_completed(
        self,
        task_id: str,
        metadata: dict[str, Any],
        run_validators: bool = True,
    ) -> SyncResult:
        """
        Handle Task completed event.

        Updates the linked Feature:
        - passes = True
        - in_progress = False

        Optionally runs acceptance validators first.

        Args:
            task_id: Claude Code Task ID
            metadata: Task metadata (must contain feature_id)
            run_validators: Whether to run acceptance validators first

        Returns:
            SyncResult indicating success/failure
        """
        feature_id = metadata.get("feature_id")
        if feature_id is None:
            return SyncResult(
                success=False,
                feature_id=None,
                feature_name=None,
                message="No feature_id in task metadata",
            )

        feature = self.session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            return SyncResult(
                success=False,
                feature_id=feature_id,
                feature_name=None,
                message=f"Feature {feature_id} not found",
            )

        # Run acceptance validators if enabled
        if run_validators:
            validation_result = self._run_acceptance_validators(feature)
            if not validation_result.passed:
                _logger.warning(
                    "Task %s completed but acceptance failed: %s",
                    task_id, validation_result.message,
                )
                return SyncResult(
                    success=False,
                    feature_id=feature.id,
                    feature_name=feature.name,
                    message=validation_result.message,
                    acceptance_failed=True,
                    error_message=validation_result.message,
                )

        # Update feature state
        feature.passes = True
        feature.in_progress = False
        self.session.commit()

        _logger.info(
            "Task %s completed: Feature #%d '%s' marked as passing",
            task_id, feature.id, feature.name,
        )

        return SyncResult(
            success=True,
            feature_id=feature.id,
            feature_name=feature.name,
            message=f"Feature #{feature.id} marked as passing",
        )

    def on_task_failed(
        self,
        task_id: str,
        metadata: dict[str, Any],
        error: str | None = None,
    ) -> SyncResult:
        """
        Handle Task failed event.

        Updates the linked Feature:
        - in_progress = False
        - passes remains False (unchanged)

        Records error in AgentEvent if there's an associated run.

        Args:
            task_id: Claude Code Task ID
            metadata: Task metadata (must contain feature_id)
            error: Optional error message

        Returns:
            SyncResult indicating success/failure
        """
        feature_id = metadata.get("feature_id")
        if feature_id is None:
            return SyncResult(
                success=False,
                feature_id=None,
                feature_name=None,
                message="No feature_id in task metadata",
            )

        feature = self.session.query(Feature).filter(Feature.id == feature_id).first()
        if feature is None:
            return SyncResult(
                success=False,
                feature_id=feature_id,
                feature_name=None,
                message=f"Feature {feature_id} not found",
            )

        # Update feature state
        feature.in_progress = False
        # Note: passes stays False (unchanged)

        # Record error event if we have an associated run
        run_id = metadata.get("run_id")
        if run_id and error:
            self._record_error_event(run_id, error)

        self.session.commit()

        _logger.info(
            "Task %s failed: Feature #%d '%s' reset to pending (error: %s)",
            task_id, feature.id, feature.name, error or "none",
        )

        return SyncResult(
            success=True,
            feature_id=feature.id,
            feature_name=feature.name,
            message=f"Feature #{feature.id} reset to pending",
            error_message=error,
        )

    def sync_task_status(
        self,
        task_id: str,
        status: str,
        metadata: dict[str, Any],
    ) -> SyncResult:
        """
        Route a TaskUpdate event to the appropriate handler.

        This is the main entry point for hook-based sync.

        Args:
            task_id: Claude Code Task ID
            status: New task status (pending, in_progress, completed)
            metadata: Task metadata

        Returns:
            SyncResult indicating success/failure
        """
        if status == "in_progress":
            return self.on_task_started(task_id, metadata)
        elif status == "completed":
            return self.on_task_completed(task_id, metadata)
        else:
            # For other statuses, just log
            _logger.debug(
                "Task %s status changed to '%s' (no sync action)",
                task_id, status,
            )
            return SyncResult(
                success=True,
                feature_id=metadata.get("feature_id"),
                feature_name=None,
                message=f"Status '{status}' acknowledged (no sync action)",
            )

    def _run_acceptance_validators(self, feature: Feature) -> "ValidationResult":
        """
        Run acceptance validators for a feature.

        This implements the Ralph Wiggum correction loop:
        - Run test suite after task completion
        - If fails, return error for agent self-correction

        Args:
            feature: The feature to validate

        Returns:
            ValidationResult with pass/fail and message
        """
        # Import validators module
        try:
            from api.validators import run_validators_for_feature
            return run_validators_for_feature(feature, self.project_dir)
        except ImportError:
            # Validators module not available, pass by default
            return ValidationResult(passed=True, message="Validators not available")
        except Exception as e:
            _logger.warning("Validator error for Feature #%d: %s", feature.id, e)
            return ValidationResult(passed=False, message=str(e))

    def _record_error_event(self, run_id: str, error: str) -> None:
        """
        Record an error event for an AgentRun.

        Args:
            run_id: The AgentRun ID
            error: Error message to record
        """
        try:
            # Get next sequence number for this run
            max_seq = (
                self.session.query(AgentEvent)
                .filter(AgentEvent.run_id == run_id)
                .count()
            )

            event = AgentEvent(
                run_id=run_id,
                event_type="failed",
                timestamp=_utc_now(),
                sequence=max_seq + 1,
                payload={"error": error},
            )
            self.session.add(event)
            # Don't commit here - let caller handle transaction
        except Exception as e:
            _logger.warning("Failed to record error event: %s", e)


@dataclass
class ValidationResult:
    """Result of running acceptance validators."""
    passed: bool
    message: str
    validator_results: list[dict[str, Any]] | None = None


def run_validators_for_feature(feature: Feature, project_dir: Path) -> ValidationResult:
    """
    Run acceptance validators for a feature.

    This is a placeholder implementation. The full implementation should:
    1. Look up the AcceptanceSpec for this feature
    2. Run each validator in the spec
    3. Apply gate_mode to determine pass/fail

    For now, returns passed if no acceptance spec exists.
    """
    # Import here to avoid circular imports
    try:
        from api.agentspec_models import AgentSpec, AcceptanceSpec
        from api.validators import run_validator

        # Find AgentSpec for this feature
        from api.database import create_database
        engine, SessionLocal = create_database(project_dir)
        session = SessionLocal()

        try:
            spec = (
                session.query(AgentSpec)
                .filter(AgentSpec.source_feature_id == feature.id)
                .order_by(AgentSpec.created_at.desc())
                .first()
            )

            if spec is None or spec.acceptance_spec is None:
                return ValidationResult(
                    passed=True,
                    message="No acceptance spec defined",
                )

            acceptance = spec.acceptance_spec
            validators = acceptance.validators or []

            if not validators:
                return ValidationResult(
                    passed=True,
                    message="No validators defined",
                )

            # Run each validator
            results = []
            all_passed = True
            messages = []

            for v in validators:
                try:
                    result = run_validator(v, project_dir)
                    results.append(result)
                    if not result.get("passed", False):
                        all_passed = False
                        messages.append(result.get("message", "Validator failed"))
                except Exception as e:
                    all_passed = False
                    messages.append(f"Validator error: {e}")
                    results.append({"passed": False, "message": str(e)})

            return ValidationResult(
                passed=all_passed,
                message="; ".join(messages) if messages else "All validators passed",
                validator_results=results,
            )

        finally:
            session.close()

    except ImportError:
        return ValidationResult(
            passed=True,
            message="Validators module not available",
        )
    except Exception as e:
        return ValidationResult(
            passed=False,
            message=f"Validation error: {e}",
        )
