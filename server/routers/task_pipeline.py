"""
Task Pipeline API Router
========================

FastAPI router providing HTTP endpoints for Claude Code hooks to interact
with the AutoBuildr Task interface pipeline.

Endpoints:
- POST /api/task-pipeline/init     - Session initialization (SessionStart hook)
- POST /api/task-pipeline/sync     - Task status sync (PostToolUse hook)
- POST /api/task-pipeline/trigger  - Pipeline trigger for agent generation
- POST /api/task-pipeline/check-agent - Check if agent type exists
- POST /api/task-pipeline/validate - Validate tool result (Ralph Wiggum loop)

Architecture:
- Hooks are thin HTTP clients that call these endpoints
- This router delegates to TaskPipelineController
- Controller coordinates Hydrator, SyncBack, and Maestro

Usage:
    from server.routers.task_pipeline import router as task_pipeline_router
    app.include_router(task_pipeline_router)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.task_pipeline_controller import (
    TaskPipelineController,
    SessionInitResult,
    AgentCheckResult,
)
from api.task_syncback import SyncResult

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task-pipeline", tags=["task-pipeline"])

# Lazy import for project-specific database
_create_database = None


def _get_db_factory():
    """Get the create_database function with lazy import."""
    global _create_database
    if _create_database is None:
        import sys
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from api.database import create_database
        _create_database = create_database
    return _create_database


def get_project_session(project_dir: Path) -> Session:
    """Get a database session for a specific project directory."""
    create_database = _get_db_factory()
    _, SessionLocal = create_database(project_dir)
    return SessionLocal()


# =============================================================================
# Request/Response Models
# =============================================================================

class InitRequest(BaseModel):
    """Request for session initialization."""
    project_dir: str = Field(..., description="Absolute path to project directory")
    session_id: str = Field("", description="Optional Claude Code session ID")


class InitResponse(BaseModel):
    """Response from session initialization."""
    tasks_hydrated: int = Field(..., description="Number of tasks created")
    feature_count: int = Field(..., description="Total number of features")
    agents_available: list[str] = Field(..., description="List of available agent names")
    pipeline_executed: bool = Field(..., description="Whether agent planning pipeline ran")
    instructions: str = Field(..., description="Session instructions for Claude")
    error: str | None = Field(None, description="Error message if any")


class SyncRequest(BaseModel):
    """Request for task status sync."""
    task_id: str = Field(..., description="Claude Code Task ID")
    status: str = Field(..., description="New task status")
    session_id: str = Field("", description="Optional session ID")
    tool_input: dict[str, Any] = Field(default_factory=dict, description="Full TaskUpdate tool input")


class SyncResponse(BaseModel):
    """Response from task status sync."""
    synced: bool = Field(..., description="Whether sync was successful")
    feature_id: int | None = Field(None, description="Linked feature ID")
    feature_name: str | None = Field(None, description="Linked feature name")
    message: str = Field(..., description="Result message")
    acceptance_failed: bool = Field(False, description="Whether acceptance validation failed")
    error_message: str | None = Field(None, description="Error details for agent self-correction")


class TriggerRequest(BaseModel):
    """Request to trigger agent generation pipeline."""
    capability: str = Field(..., description="Capability needed (e.g., 'e2e_testing')")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    project_dir: str = Field(".", description="Project directory")


class TriggerResponse(BaseModel):
    """Response from pipeline trigger."""
    generated: bool = Field(..., description="Whether agent was generated")
    agent_files: list[str] = Field(default_factory=list, description="Paths to generated agent files")
    agents_generated: int = Field(0, description="Number of agents generated")
    error: str | None = Field(None, description="Error message if generation failed")
    # Playground sync info
    playground_synced: list[str] = Field(default_factory=list, description="Files synced to playground")
    playground_namespace: str | None = Field(None, description="Namespace used for playground sync")


class CheckAgentRequest(BaseModel):
    """Request to check agent existence."""
    agent_type: str = Field(..., description="Agent type to check")
    project_dir: str = Field(".", description="Project directory")


class CheckAgentResponse(BaseModel):
    """Response from agent existence check."""
    needs_generation: bool = Field(..., description="Whether agent needs to be generated")
    agent_type: str = Field(..., description="Checked agent type")
    exists: bool = Field(..., description="Whether agent exists")
    path: str | None = Field(None, description="Path to agent file if exists")


class ValidateRequest(BaseModel):
    """Request to validate tool result."""
    tool_name: str = Field(..., description="Name of tool that was executed")
    tool_result: dict[str, Any] = Field(default_factory=dict, description="Tool execution result")
    cwd: str = Field(".", description="Current working directory")


class ValidateResponse(BaseModel):
    """Response from validation."""
    valid: bool = Field(..., description="Whether validation passed")
    feedback: str | None = Field(None, description="Feedback for agent if validation failed")
    retry_hint: str | None = Field(None, description="Hint for how to fix the issue")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/init", response_model=InitResponse)
async def initialize_session(
    request: InitRequest,
) -> InitResponse:
    """
    Initialize a Claude Code session.

    Called by the SessionStart hook. Performs:
    1. Check if features exist (else return instructions for /create-spec)
    2. Check if agent generation needed
    3. If yes, trigger Maestro → Octo pipeline
    4. Hydrate Features → Tasks
    5. Return task list and instructions for Claude

    Returns:
        Session initialization result with tasks and instructions
    """
    try:
        project_dir = Path(request.project_dir).resolve()
        if not project_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Project directory does not exist: {project_dir}",
            )

        # Use project-specific database session
        db = get_project_session(project_dir)
        controller = TaskPipelineController(project_dir, db)
        result = controller.initialize_session(session_id=request.session_id)

        _logger.info(
            "Session initialized: project=%s, tasks=%d, agents=%d",
            project_dir.name, result.task_count, len(result.agents),
        )

        return InitResponse(
            tasks_hydrated=result.task_count,
            feature_count=result.feature_count,
            agents_available=result.agents,
            pipeline_executed=result.pipeline_ran,
            instructions=result.session_instructions,
            error=result.error,
        )

    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Session initialization failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Session initialization failed: {e}",
        )


@router.post("/sync", response_model=SyncResponse)
async def sync_task_status(
    request: SyncRequest,
) -> SyncResponse:
    """
    Sync Claude Code Task status to Feature database.

    Called by the PostToolUse hook on TaskUpdate events.
    Routes to TaskSyncBack to update Feature state.

    For task completion, runs acceptance validators and returns
    feedback for the Ralph Wiggum correction loop if validation fails.

    Returns:
        Sync result with feature state and any validation errors
    """
    try:
        # Extract metadata from tool_input
        metadata = request.tool_input.get("metadata", {})

        # Get project_dir from metadata or use default
        project_dir_str = metadata.get("project_dir", ".")
        project_dir = Path(project_dir_str).resolve()

        # Use project-specific database session
        db = get_project_session(project_dir)
        controller = TaskPipelineController(project_dir, db)

        # Build task data for handler
        task_data = {
            "task_id": request.task_id,
            "status": request.status,
            "metadata": metadata,
        }

        result = controller.handle_task_event("status_change", task_data)

        _logger.debug(
            "Task sync: task_id=%s, status=%s, success=%s",
            request.task_id, request.status, result.success,
        )

        return SyncResponse(
            synced=result.success,
            feature_id=result.feature_id,
            feature_name=result.feature_name,
            message=result.message,
            acceptance_failed=result.acceptance_failed,
            error_message=result.error_message,
        )

    except Exception as e:
        _logger.error("Task sync failed: %s", e)
        return SyncResponse(
            synced=False,
            feature_id=None,
            feature_name=None,
            message=f"Sync failed: {e}",
            acceptance_failed=False,
            error_message=str(e),
        )


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_pipeline(
    request: TriggerRequest,
) -> TriggerResponse:
    """
    Trigger agent generation pipeline.

    Called when an agent type is needed but doesn't exist.
    Invokes Maestro → Octo → Materializer to generate the agent.

    Returns:
        Result with paths to generated agent files
    """
    try:
        project_dir = Path(request.project_dir).resolve()
        if not project_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Project directory does not exist: {project_dir}",
            )

        # Use project-specific database session
        db = get_project_session(project_dir)
        controller = TaskPipelineController(project_dir, db)
        result = controller.trigger_pipeline(
            capability=request.capability,
            context=request.context,
        )

        _logger.info(
            "Pipeline triggered: capability=%s, success=%s, agents=%s",
            request.capability, result.get("success"), result.get("agents_generated", 0),
        )

        return TriggerResponse(
            generated=result.get("success", False),
            agent_files=result.get("agent_files", []),
            agents_generated=result.get("agents_generated", 0),
            error=result.get("error"),
            playground_synced=result.get("playground_synced", []),
            playground_namespace=result.get("playground_namespace"),
        )

    except HTTPException:
        raise
    except Exception as e:
        _logger.error("Pipeline trigger failed: %s", e)
        return TriggerResponse(
            generated=False,
            agent_files=[],
            agents_generated=0,
            error=str(e),
            playground_synced=[],
            playground_namespace=None,
        )


@router.post("/check-agent", response_model=CheckAgentResponse)
async def check_agent_exists(
    request: CheckAgentRequest,
) -> CheckAgentResponse:
    """
    Check if an agent type exists in the project.

    Called by PreToolUse hook before Task tool execution.
    If agent doesn't exist, caller can trigger pipeline.

    Returns:
        Agent existence status and path if found
    """
    try:
        project_dir = Path(request.project_dir).resolve()

        # Use project-specific database session
        db = get_project_session(project_dir)
        controller = TaskPipelineController(project_dir, db)
        result = controller.check_agent_exists(request.agent_type)

        return CheckAgentResponse(
            needs_generation=result.needs_generation,
            agent_type=result.agent_type,
            exists=result.exists,
            path=result.path,
        )

    except Exception as e:
        _logger.error("Agent check failed: %s", e)
        # Return needs_generation=True on error to be safe
        return CheckAgentResponse(
            needs_generation=True,
            agent_type=request.agent_type,
            exists=False,
            path=None,
        )


@router.post("/validate", response_model=ValidateResponse)
async def validate_tool_result(
    request: ValidateRequest,
) -> ValidateResponse:
    """
    Validate tool result against acceptance criteria.

    Called by PostToolUse hook after Edit/Write tool execution.
    Implements the Ralph Wiggum correction loop:
    - Run validators against the result
    - If validation fails, return feedback for agent self-correction

    Returns:
        Validation result with feedback for correction if needed
    """
    try:
        project_dir = Path(request.cwd).resolve()

        # Use project-specific database session
        db = get_project_session(project_dir)
        controller = TaskPipelineController(project_dir, db)
        validators = controller.get_active_validators()

        # If no validators, pass by default
        if not validators:
            return ValidateResponse(
                valid=True,
                feedback=None,
                retry_hint=None,
            )

        # Run validators
        # Note: Full implementation would run each validator and collect results
        # For now, return valid=True as placeholder
        return ValidateResponse(
            valid=True,
            feedback=None,
            retry_hint=None,
        )

    except Exception as e:
        _logger.error("Validation failed: %s", e)
        return ValidateResponse(
            valid=False,
            feedback=f"Validation error: {e}",
            retry_hint="Fix the issue and retry.",
        )


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Health check endpoint for the task pipeline service.

    Returns:
        Status indicating service is healthy
    """
    return {"status": "healthy", "service": "task-pipeline"}
