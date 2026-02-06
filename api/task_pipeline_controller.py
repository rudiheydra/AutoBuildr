"""
Task Pipeline Controller
========================

Main controller integrating Claude Code's Task interface with AutoBuildr's
Maestro → Octo → Materializer pipeline.

This controller orchestrates:
1. Session initialization: Hydrate Features → Tasks, check agent generation
2. Task events: Route TaskUpdate events to sync-back
3. Pipeline triggers: Call DSPy backend when agents need generation

Architecture principles from design docs:
- "Tasks are the stack, Specs are the heap"
- Maestro orchestrates work, Octo architects workers
- DSPy reasons, Hooks enforce, Claude Code executes

Usage:
    from api.task_pipeline_controller import TaskPipelineController

    controller = TaskPipelineController(project_dir, session)
    result = controller.initialize_session()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.database import Feature
from api.task_hydrator import TaskHydrator, HydrationResult
from api.task_syncback import TaskSyncBack, SyncResult

_logger = logging.getLogger(__name__)


@dataclass
class SessionInitResult:
    """Result of session initialization."""
    task_count: int
    feature_count: int
    agents: list[str]
    pipeline_ran: bool
    session_instructions: str
    hydration_result: HydrationResult | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_count": self.task_count,
            "feature_count": self.feature_count,
            "agents": self.agents,
            "pipeline_ran": self.pipeline_ran,
            "session_instructions": self.session_instructions,
            "hydration_result": self.hydration_result.to_dict() if self.hydration_result else None,
            "error": self.error,
        }


@dataclass
class AgentCheckResult:
    """Result of checking agent existence."""
    agent_type: str
    exists: bool
    path: str | None = None
    needs_generation: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_type": self.agent_type,
            "exists": self.exists,
            "path": self.path,
            "needs_generation": self.needs_generation,
        }


@dataclass
class ValidatorConfig:
    """Configuration for an active validator."""
    type: str
    config: dict[str, Any]


class TaskPipelineController:
    """
    Main controller integrating Task interface with existing pipeline.

    Responsibilities:
    1. initialize_session(): Called at SessionStart
       - Check if features exist (else prompt for /create-spec)
       - Check if agents need generation via run_agent_planning()
       - Hydrate Features → Tasks
       - Return instructions for Claude

    2. should_trigger_pipeline(): Check when agent generation needed
       - Features exist but no generated agents → True

    3. handle_task_event(): Route TaskUpdate events to sync-back
       - Status changes → Feature state updates
       - Completion → Acceptance validation

    4. check_agent_exists(): Verify agent availability
       - Check .claude/agents/ and .claude/agents/generated/
    """

    def __init__(self, project_dir: Path, session: Session):
        """
        Initialize the TaskPipelineController.

        Args:
            project_dir: Root project directory
            session: SQLAlchemy session for database access
        """
        self.project_dir = Path(project_dir).resolve()
        self.session = session
        self.hydrator = TaskHydrator(project_dir, session)
        self.syncback = TaskSyncBack(project_dir, session)

        # Cache of discovered agents
        self._agents_cache: list[str] | None = None

    def initialize_session(self, session_id: str | None = None) -> SessionInitResult:
        """
        Initialize a Claude Code session.

        Called by SessionStart hook. Performs:
        1. Check if features exist
        2. Check if agent generation needed
        3. Trigger Maestro → Octo pipeline if needed
        4. Hydrate Features → Tasks
        5. Return session instructions

        Args:
            session_id: Optional session ID for logging

        Returns:
            SessionInitResult with task count, agents, and instructions
        """
        _logger.info(
            "Initializing session (session_id=%s, project=%s)",
            session_id, self.project_dir,
        )

        # 1. Check features exist
        feature_count = self.session.query(Feature).count()
        if feature_count == 0:
            return SessionInitResult(
                task_count=0,
                feature_count=0,
                agents=[],
                pipeline_ran=False,
                session_instructions=(
                    "## AutoBuildr Session\n\n"
                    "No features found. Use `/create-spec` to initialize the project "
                    "with an app specification and generate features."
                ),
            )

        # 2. Check if agent generation needed and run pipeline
        pipeline_ran = False
        if self.should_trigger_pipeline():
            try:
                pipeline_ran = self._run_agent_planning()
            except Exception as e:
                _logger.warning("Agent planning failed: %s", e)
                # Continue with default agents

        # 3. Discover available agents
        agents = self.get_available_agents()

        # 4. Hydrate features → tasks
        hydration_result = self.hydrator.hydrate()

        # 5. Build session instructions
        instructions = self.hydrator.get_hydration_instructions(hydration_result)

        _logger.info(
            "Session initialized: %d tasks, %d agents, pipeline_ran=%s",
            hydration_result.task_count, len(agents), pipeline_ran,
        )

        return SessionInitResult(
            task_count=hydration_result.task_count,
            feature_count=feature_count,
            agents=agents,
            pipeline_ran=pipeline_ran,
            session_instructions=instructions,
            hydration_result=hydration_result,
        )

    def should_trigger_pipeline(self) -> bool:
        """
        Determine if the Maestro → Octo pipeline should run.

        Pipeline should trigger when:
        - Features exist in database
        - No generated agents exist yet

        Returns:
            True if pipeline should run
        """
        # Check if features exist
        feature_count = self.session.query(Feature).count()
        if feature_count == 0:
            return False

        # Check if generated agents exist
        generated_dir = self.project_dir / ".claude" / "agents" / "generated"
        if not generated_dir.exists():
            return True

        generated_agents = list(generated_dir.glob("*.md"))
        if not generated_agents:
            return True

        return False

    def handle_task_event(
        self,
        event_type: str,
        task_data: dict[str, Any],
    ) -> SyncResult:
        """
        Route a Task event to the appropriate handler.

        Called by PostToolUse hook on TaskUpdate events.

        Args:
            event_type: Event type (status_change, etc.)
            task_data: Task data including task_id, status, metadata

        Returns:
            SyncResult from sync-back
        """
        task_id = task_data.get("task_id", "unknown")
        status = task_data.get("status")
        metadata = task_data.get("metadata", {})

        _logger.debug(
            "Handling task event: type=%s, task_id=%s, status=%s",
            event_type, task_id, status,
        )

        if event_type == "status_change" and status:
            return self.syncback.sync_task_status(task_id, status, metadata)

        # Unknown event type - log and return success
        return SyncResult(
            success=True,
            feature_id=metadata.get("feature_id"),
            feature_name=None,
            message=f"Event '{event_type}' acknowledged",
        )

    def check_agent_exists(self, agent_type: str) -> AgentCheckResult:
        """
        Check if an agent type exists in the project.

        Searches:
        1. .claude/agents/{agent_type}.md (standard agents)
        2. .claude/agents/generated/{agent_type}.md (generated agents)

        Args:
            agent_type: Agent type name (e.g., "coder", "e2e-tester")

        Returns:
            AgentCheckResult with existence status
        """
        agents_dir = self.project_dir / ".claude" / "agents"
        generated_dir = agents_dir / "generated"

        # Check standard agents
        standard_path = agents_dir / f"{agent_type}.md"
        if standard_path.exists():
            return AgentCheckResult(
                agent_type=agent_type,
                exists=True,
                path=str(standard_path),
                needs_generation=False,
            )

        # Check generated agents
        generated_path = generated_dir / f"{agent_type}.md"
        if generated_path.exists():
            return AgentCheckResult(
                agent_type=agent_type,
                exists=True,
                path=str(generated_path),
                needs_generation=False,
            )

        # Not found
        return AgentCheckResult(
            agent_type=agent_type,
            exists=False,
            path=None,
            needs_generation=True,
        )

    def get_available_agents(self) -> list[str]:
        """
        Get list of all available agent names.

        Returns cached result if available.

        Returns:
            List of agent names (without .md extension)
        """
        if self._agents_cache is not None:
            return self._agents_cache

        agents = []
        agents_dir = self.project_dir / ".claude" / "agents"

        if agents_dir.exists():
            # Standard agents
            for agent_file in agents_dir.glob("*.md"):
                agents.append(agent_file.stem)

            # Generated agents
            generated_dir = agents_dir / "generated"
            if generated_dir.exists():
                for agent_file in generated_dir.glob("*.md"):
                    agents.append(agent_file.stem)

        self._agents_cache = sorted(set(agents))
        return self._agents_cache

    def get_active_validators(self) -> list[ValidatorConfig]:
        """
        Get active validators for the current task.

        Used by the Ralph Wiggum correction loop to validate
        tool results after execution.

        Returns:
            List of validator configurations
        """
        # This would typically come from the current AgentSpec's AcceptanceSpec
        # For now, return empty list (no validators active)
        return []

    def trigger_pipeline(
        self,
        capability: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Trigger the Maestro → Octo → Materializer pipeline.

        Called when an agent needs to be generated on-demand.

        Args:
            capability: The capability needed (e.g., "e2e_testing")
            context: Optional context for spec generation

        Returns:
            Dict with success status and generated agent path
        """
        try:
            from api.maestro import Maestro, ProjectContext
            from api.spec_orchestrator import _detect_tech_stack

            # Build project context
            features = self.session.query(Feature).all()
            feature_dicts = [f.to_dict() for f in features]
            tech_stack = _detect_tech_stack(self.project_dir)

            project_context = ProjectContext(
                project_name=self.project_dir.name,
                project_dir=self.project_dir,
                tech_stack=tech_stack,
                features=feature_dicts,
                execution_environment="local",
            )

            # Create Maestro and evaluate
            maestro = Maestro(project_dir=self.project_dir, session=self.session)
            decision = maestro.evaluate(project_context)

            if not decision.requires_agent_planning:
                return {
                    "success": False,
                    "error": "No agent planning required",
                    "agent_file": None,
                }

            # Delegate to Octo
            result = maestro.delegate_to_octo(
                decision,
                self.session,
                project_dir=self.project_dir,
                context=project_context,
            )

            if not result.success or not result.agent_specs:
                return {
                    "success": False,
                    "error": result.error if hasattr(result, 'error') else "Octo failed",
                    "agent_file": None,
                }

            # Materialize agents
            orchestration = maestro.orchestrate_materialization(result.agent_specs)

            # Invalidate cache
            self._agents_cache = None

            return {
                "success": True,
                "error": None,
                "agents_generated": orchestration.succeeded,
                "agent_files": [str(r.file_path) for r in orchestration.results if r.success],
            }

        except Exception as e:
            _logger.error("Pipeline trigger failed: %s", e)
            return {
                "success": False,
                "error": str(e),
                "agent_file": None,
            }

    def _run_agent_planning(self) -> bool:
        """
        Run the agent planning pipeline.

        Delegates to spec_orchestrator.run_agent_planning().

        Returns:
            True if pipeline ran successfully
        """
        try:
            from api.spec_orchestrator import run_agent_planning
            return run_agent_planning(self.project_dir, self.session)
        except Exception as e:
            _logger.error("Agent planning failed: %s", e)
            return False
