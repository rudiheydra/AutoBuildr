"""
Task Hydrator
=============

Converts persistent Features into session-scoped Claude Code Tasks.

This implements the hydration pattern from the Task Interface design:
- Features are the persistent source of truth (Layer 3 state)
- Tasks are ephemeral session-scoped work items (Layer 2 state)
- Hydration bridges persistent → session at SessionStart

The hydrator:
1. Queries non-passing Features from the database
2. Creates TaskCreate payloads matching Claude Code's Task interface
3. Maps Feature dependencies to Task blockedBy relationships
4. Links Tasks to Features via metadata.feature_id for sync-back

Usage:
    from api.task_hydrator import TaskHydrator

    hydrator = TaskHydrator(project_dir, session)
    tasks = hydrator.hydrate()
    # Returns list of TaskCreatePayload dicts ready for Claude Code
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.database import Feature

_logger = logging.getLogger(__name__)


@dataclass
class TaskCreatePayload:
    """
    Payload for creating a Claude Code Task.

    Matches the TaskCreate tool interface in Claude Code.
    """
    subject: str
    description: str
    activeForm: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "subject": self.subject,
            "description": self.description,
            "activeForm": self.activeForm,
            "metadata": self.metadata,
        }


@dataclass
class HydrationResult:
    """Result of task hydration."""
    tasks: list[TaskCreatePayload]
    task_count: int
    feature_count: int
    dependency_map: dict[int, list[int]]  # feature_id -> list of blocker task indices

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tasks": [t.to_dict() for t in self.tasks],
            "task_count": self.task_count,
            "feature_count": self.feature_count,
            "dependency_map": {str(k): v for k, v in self.dependency_map.items()},
        }


class TaskHydrator:
    """
    Convert persistent Features into session-scoped Claude Code Tasks.

    Implements the "Tasks are the stack, Specs are the heap" principle:
    - Features persist across sessions (the heap/specification)
    - Tasks are session-scoped work items (the stack/runtime)

    At session start, non-passing Features are hydrated into Tasks.
    Task completion triggers sync-back to Feature.passes.
    """

    def __init__(self, project_dir: Path, session: Session):
        """
        Initialize the TaskHydrator.

        Args:
            project_dir: Root project directory
            session: SQLAlchemy session for database access
        """
        self.project_dir = Path(project_dir).resolve()
        self.session = session

    def hydrate(self, limit: int | None = None) -> HydrationResult:
        """
        Hydrate non-passing Features into Task payloads.

        Creates TaskCreatePayload for each Feature that:
        - Has passes = False
        - Is not currently in_progress

        Tasks are ordered by priority (lowest first) and ID.
        Dependencies are mapped to blockedBy relationships.

        Args:
            limit: Maximum number of tasks to hydrate (None = all)

        Returns:
            HydrationResult with tasks and metadata
        """
        # Query all features
        all_features = self.session.query(Feature).all()
        total_count = len(all_features)

        # Build lookup maps
        passing_ids = {f.id for f in all_features if f.passes}
        feature_by_id = {f.id: f for f in all_features}

        # Find features ready for work
        pending_features = []
        for f in all_features:
            if f.passes:
                continue
            if f.in_progress:
                continue
            pending_features.append(f)

        # Sort by priority (low = high priority) then ID
        pending_features.sort(key=lambda f: (f.priority, f.id))

        # Apply limit if specified
        if limit is not None:
            pending_features = pending_features[:limit]

        # Build task payloads
        tasks: list[TaskCreatePayload] = []
        feature_id_to_task_index: dict[int, int] = {}
        dependency_map: dict[int, list[int]] = {}

        for idx, feature in enumerate(pending_features):
            task = self._create_task_payload(feature)
            tasks.append(task)
            feature_id_to_task_index[feature.id] = idx

        # Resolve dependencies to blockedBy indices
        for feature in pending_features:
            deps = feature.get_dependencies_safe()
            if not deps:
                continue

            task_idx = feature_id_to_task_index[feature.id]
            blockers = []

            for dep_id in deps:
                # Skip if dependency already passes
                if dep_id in passing_ids:
                    continue
                # Map to task index if that feature is also being hydrated
                if dep_id in feature_id_to_task_index:
                    blockers.append(feature_id_to_task_index[dep_id])

            if blockers:
                dependency_map[feature.id] = blockers

        _logger.info(
            "Hydrated %d tasks from %d pending features (total: %d)",
            len(tasks), len(pending_features), total_count,
        )

        return HydrationResult(
            tasks=tasks,
            task_count=len(tasks),
            feature_count=total_count,
            dependency_map=dependency_map,
        )

    def _create_task_payload(self, feature: Feature) -> TaskCreatePayload:
        """
        Create a TaskCreatePayload from a Feature.

        The task payload includes:
        - subject: Feature name (imperative form)
        - description: Full feature details with steps
        - activeForm: Present continuous for spinner display
        - metadata: Links back to feature_id for sync-back
        """
        # Build description from feature details
        steps = feature.steps if isinstance(feature.steps, list) else []
        steps_text = "\n".join(f"- {step}" for step in steps) if steps else "(no steps)"

        description = (
            f"**Category:** {feature.category}\n\n"
            f"**Description:**\n{feature.description}\n\n"
            f"**Steps:**\n{steps_text}"
        )

        # Convert to present continuous for activeForm
        # "Implement login flow" -> "Implementing login flow"
        active_form = self._to_active_form(feature.name)

        return TaskCreatePayload(
            subject=f"Implement: {feature.name}",
            description=description,
            activeForm=active_form,
            metadata={
                "feature_id": feature.id,
                "feature_category": feature.category,
                "feature_priority": feature.priority,
            },
        )

    def _to_active_form(self, name: str) -> str:
        """
        Convert an imperative name to present continuous form.

        Examples:
            "Login flow" -> "Implementing login flow"
            "Add user authentication" -> "Adding user authentication"
        """
        name_lower = name.lower()

        # Common verb prefixes to convert
        verb_mappings = {
            "add ": "Adding ",
            "create ": "Creating ",
            "implement ": "Implementing ",
            "build ": "Building ",
            "fix ": "Fixing ",
            "update ": "Updating ",
            "remove ": "Removing ",
            "delete ": "Deleting ",
            "refactor ": "Refactoring ",
            "test ": "Testing ",
            "write ": "Writing ",
            "setup ": "Setting up ",
            "set up ": "Setting up ",
            "configure ": "Configuring ",
        }

        for prefix, replacement in verb_mappings.items():
            if name_lower.startswith(prefix):
                return replacement + name[len(prefix):]

        # Default: prepend "Implementing"
        return f"Implementing {name}"

    def get_hydration_instructions(self, result: HydrationResult) -> str:
        """
        Generate session instructions for Claude based on hydration result.

        Returns a markdown string to inject into the session context.
        """
        if result.task_count == 0:
            return (
                "## AutoBuildr Session\n\n"
                "All features are passing! No pending work.\n\n"
                "Use `/create-spec` to add new features, or `/feature-stats` to see status."
            )

        # Build task list summary
        task_list = "\n".join(
            f"{idx + 1}. {task.subject}"
            for idx, task in enumerate(result.tasks[:10])
        )

        if result.task_count > 10:
            task_list += f"\n... and {result.task_count - 10} more"

        return (
            f"## AutoBuildr Session\n\n"
            f"**{result.task_count} tasks** hydrated from {result.feature_count} features.\n\n"
            f"### Pending Tasks\n\n{task_list}\n\n"
            f"Use `TaskList` to see all tasks, or start with the first unblocked task.\n\n"
            f"When you complete a task, mark it as `completed` via `TaskUpdate`. "
            f"This will automatically update the feature status."
        )
