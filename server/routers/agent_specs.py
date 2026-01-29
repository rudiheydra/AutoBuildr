"""
Agent Specs Router
==================

API endpoints for AgentSpec CRUD operations.

Implements:
- POST /api/projects/{project_name}/agent-specs - Create new AgentSpec
- GET /api/projects/{project_name}/agent-specs - List AgentSpecs with filters
- GET /api/projects/{project_name}/agent-specs/:id - Get single AgentSpec
- PUT /api/projects/{project_name}/agent-specs/:id - Update AgentSpec
- DELETE /api/projects/{project_name}/agent-specs/:id - Delete AgentSpec
- POST /api/projects/{project_name}/agent-specs/:id/execute - Trigger execution
"""

import asyncio
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from api.agentspec_models import AgentRun as AgentRunModel
from api.agentspec_models import AgentSpec as AgentSpecModel
from server.schemas.agentspec import (
    AcceptanceSpecResponse,
    AgentRunResponse,
    AgentSpecCreate,
    AgentSpecListResponse,
    AgentSpecResponse,
    AgentSpecSummary,
    AgentSpecUpdate,
    AgentSpecWithAcceptanceResponse,
    SpecValidationErrorResponse,
    ValidationErrorItem,
)
from ..utils.validation import validate_project_name


# Setup logger
_logger = logging.getLogger(__name__)


# Lazy imports to avoid circular dependencies
_create_database = None


def _get_project_path(project_name: str) -> Path:
    """Get project path from registry."""
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry import get_project_path
    return get_project_path(project_name)


def _get_db_classes():
    """Lazy import of database classes."""
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


@contextmanager
def get_db_session(project_dir: Path):
    """
    Context manager for database sessions.
    Ensures session is always closed, even on exceptions.
    """
    create_database = _get_db_classes()
    _, SessionLocal = create_database(project_dir)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


router = APIRouter(prefix="/api/projects/{project_name}/agent-specs", tags=["agent-specs"])


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def _generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


@router.post(
    "",
    response_model=AgentSpecResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "description": "AgentSpec created successfully",
            "model": AgentSpecResponse,
        },
        400: {
            "description": "Database constraint violation",
            "content": {
                "application/json": {
                    "example": {"detail": "Database constraint violation: duplicate name"}
                }
            },
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "name"],
                                "msg": "String should match pattern '^[a-z0-9][a-z0-9\\-]*[a-z0-9]$|^[a-z0-9]$'",
                                "type": "string_pattern_mismatch",
                            }
                        ]
                    }
                }
            },
        },
    },
)
async def create_agent_spec(
    project_name: str,
    spec_data: AgentSpecCreate,
) -> AgentSpecResponse:
    """
    Create a new AgentSpec.

    Creates a new agent specification with the provided configuration.
    The spec will be assigned a unique UUID and the current UTC timestamp.

    Args:
        project_name: Name of the project
        spec_data: AgentSpecCreate with spec configuration

    Returns:
        AgentSpecResponse with the created spec

    Raises:
        422: If validation fails (Pydantic handles this automatically)
        400: If a database constraint is violated (e.g., duplicate name)
        404: If the project is not found
    """
    # Validate project name and get path
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    # Generate UUID for new spec
    spec_id = _generate_uuid()

    # Set defaults
    spec_version = "v1"
    created_at = _utc_now()

    # Build tool_policy dict from Pydantic model
    tool_policy_dict = spec_data.tool_policy.model_dump()

    # Create SQLAlchemy model instance
    db_spec = AgentSpecModel(
        id=spec_id,
        name=spec_data.name,
        display_name=spec_data.display_name,
        icon=spec_data.icon,
        spec_version=spec_version,
        objective=spec_data.objective,
        task_type=spec_data.task_type,
        context=spec_data.context,
        tool_policy=tool_policy_dict,
        max_turns=spec_data.max_turns,
        timeout_seconds=spec_data.timeout_seconds,
        parent_spec_id=spec_data.parent_spec_id,
        source_feature_id=spec_data.source_feature_id,
        spec_path=spec_data.spec_path,
        priority=spec_data.priority,
        tags=spec_data.tags,
        created_at=created_at,
    )

    with get_db_session(project_dir) as db:
        try:
            # Add to session and commit
            db.add(db_spec)
            db.commit()
            db.refresh(db_spec)
        except IntegrityError as e:
            db.rollback()
            # Extract useful info from the error
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)

            # Check for common constraint violations
            if "UNIQUE constraint failed" in error_msg:
                if "name" in error_msg:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Database constraint violation: duplicate name",
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Database constraint violation: unique constraint failed",
                )
            if "FOREIGN KEY constraint failed" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Database constraint violation: invalid foreign key reference",
                )
            if "CHECK constraint failed" in error_msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Database constraint violation: check constraint failed",
                )

            # Generic constraint violation
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Database constraint violation: {error_msg}",
            )

        # Convert to response model
        spec_dict = db_spec.to_dict()

    # Feature #60: Broadcast agent_spec_created WebSocket message after successful creation
    # Step 1: After AgentSpec creation, publish WebSocket message
    # Step 2: Message type is agent_spec_created
    # Step 3: Payload includes spec_id, name, display_name, icon, task_type
    # Step 4: Broadcast to all connected clients
    # Step 5: Handle WebSocket errors gracefully (done inside broadcast function)
    try:
        from api.websocket_events import broadcast_agent_spec_created
        await broadcast_agent_spec_created(
            project_name=project_name,
            spec_id=spec_dict["id"],
            name=spec_dict["name"],
            display_name=spec_dict["display_name"],
            icon=spec_dict["icon"],
            task_type=spec_dict["task_type"],
        )
    except Exception as e:
        # Log but don't fail the API request if WebSocket broadcast fails
        _logger.warning(f"Failed to broadcast agent_spec_created event: {e}")

    return AgentSpecResponse(
        id=spec_dict["id"],
        name=spec_dict["name"],
        display_name=spec_dict["display_name"],
        icon=spec_dict["icon"],
        spec_version=spec_dict["spec_version"],
        objective=spec_dict["objective"],
        task_type=spec_dict["task_type"],
        context=spec_dict["context"],
        tool_policy=spec_dict["tool_policy"],
        max_turns=spec_dict["max_turns"],
        timeout_seconds=spec_dict["timeout_seconds"],
        parent_spec_id=spec_dict["parent_spec_id"],
        source_feature_id=spec_dict["source_feature_id"],
        spec_path=spec_dict.get("spec_path"),
        created_at=spec_dict["created_at"],
        priority=spec_dict["priority"],
        tags=spec_dict["tags"],
    )


@router.get(
    "",
    response_model=AgentSpecListResponse,
    responses={
        200: {
            "description": "List of AgentSpecs with pagination",
            "model": AgentSpecListResponse,
            "headers": {
                "X-Total-Count": {
                    "description": "Total number of matching AgentSpecs",
                    "schema": {"type": "integer"},
                }
            },
        },
    },
)
async def list_agent_specs(
    project_name: str,
    response: Response,
    task_type: Optional[str] = Query(
        default=None,
        description="Filter by task type (coding, testing, refactoring, documentation, audit, custom)",
    ),
    source_feature_id: Optional[int] = Query(
        default=None,
        description="Filter by linked Feature ID",
    ),
    tags: Optional[str] = Query(
        default=None,
        description="Filter by tags (comma-separated list, matches if ANY tag is present)",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of results to return",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of results to skip (for pagination)",
    ),
) -> AgentSpecListResponse:
    """
    List AgentSpecs with optional filtering and pagination.

    Returns a paginated list of AgentSpecs with summary information including
    run statistics. Results are ordered by priority (lower = higher priority)
    then by creation date.

    ## Filters

    - **task_type**: Filter by task type (e.g., "coding", "testing")
    - **source_feature_id**: Filter by linked Feature ID
    - **tags**: Comma-separated list of tags (matches if spec contains ANY tag)

    ## Pagination

    - **limit**: Max results per page (default 50, max 100)
    - **offset**: Skip first N results

    ## Response Headers

    - **X-Total-Count**: Total number of matching specs (for building pagination UI)

    ## Example

    ```
    GET /api/projects/myproject/agent-specs?task_type=coding&limit=10&offset=0
    ```
    """
    # Validate project name and get path
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    with get_db_session(project_dir) as db:
        # Build base query
        query = db.query(AgentSpecModel)

        # Apply filters
        if task_type:
            # Validate task_type
            valid_types = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]
            if task_type not in valid_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid task_type. Must be one of: {valid_types}",
                )
            query = query.filter(AgentSpecModel.task_type == task_type)

        if source_feature_id is not None:
            query = query.filter(AgentSpecModel.source_feature_id == source_feature_id)

        if tags:
            # Parse comma-separated tags
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                # For SQLite, we need to filter using JSON functions
                # Use LIKE to check if any tag is in the JSON array
                # This is a basic implementation - for each tag, check if it appears in the JSON string
                from sqlalchemy import or_

                tag_conditions = []
                for tag in tag_list:
                    # SQLite JSON_CONTAINS workaround: check if tag appears in the JSON array
                    # Using LIKE with the tag surrounded by quotes
                    tag_conditions.append(
                        func.json_extract(AgentSpecModel.tags, "$").like(f'%"{tag}"%')
                    )
                if tag_conditions:
                    query = query.filter(or_(*tag_conditions))

        # Get total count before pagination (for header)
        total_count = query.count()

        # Apply ordering: priority (ascending), then created_at (descending)
        query = query.order_by(AgentSpecModel.priority, AgentSpecModel.created_at.desc())

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Execute query
        specs = query.all()

        # Build summary responses with run statistics
        spec_summaries = []
        for spec in specs:
            spec_dict = spec.to_dict()

            # Get run statistics for this spec
            total_runs = (
                db.query(func.count(AgentRunModel.id))
                .filter(AgentRunModel.agent_spec_id == spec.id)
                .scalar() or 0
            )
            passing_runs = (
                db.query(func.count(AgentRunModel.id))
                .filter(
                    AgentRunModel.agent_spec_id == spec.id,
                    AgentRunModel.final_verdict == "passed",
                )
                .scalar() or 0
            )

            # Get latest run status
            latest_run = (
                db.query(AgentRunModel)
                .filter(AgentRunModel.agent_spec_id == spec.id)
                .order_by(AgentRunModel.created_at.desc())
                .first()
            )
            latest_run_status = latest_run.status if latest_run else None

            spec_summaries.append(
                AgentSpecSummary(
                    id=spec_dict["id"],
                    name=spec_dict["name"],
                    display_name=spec_dict["display_name"],
                    icon=spec_dict["icon"],
                    task_type=spec_dict["task_type"],
                    priority=spec_dict["priority"],
                    created_at=spec_dict["created_at"],
                    source_feature_id=spec_dict["source_feature_id"],
                    total_runs=total_runs,
                    passing_runs=passing_runs,
                    latest_run_status=latest_run_status,
                )
            )

    # Set total count header
    response.headers["X-Total-Count"] = str(total_count)

    return AgentSpecListResponse(
        specs=spec_summaries,
        total=total_count,
        offset=offset,
        limit=limit,
    )


def _is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID format."""
    try:
        uuid.UUID(value, version=4)
        return True
    except ValueError:
        return False


@router.get(
    "/{spec_id}",
    response_model=AgentSpecWithAcceptanceResponse,
    responses={
        200: {
            "description": "AgentSpec with nested AcceptanceSpec",
            "model": AgentSpecWithAcceptanceResponse,
        },
        400: {
            "description": "Invalid UUID format",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid UUID format for spec_id: 'not-a-uuid'"}
                }
            },
        },
        404: {
            "description": "AgentSpec not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentSpec 'abc-123-...' not found"}
                }
            },
        },
    },
)
async def get_agent_spec(
    project_name: str,
    spec_id: str,
) -> AgentSpecWithAcceptanceResponse:
    """
    Get a single AgentSpec by ID with its linked AcceptanceSpec.

    Retrieves full details of an AgentSpec including:
    - Identity (name, display_name, icon)
    - Objective and task type
    - Tool policy and execution budget
    - Linked AcceptanceSpec with validators (if exists)

    Args:
        project_name: Name of the project
        spec_id: UUID of the AgentSpec to retrieve

    Returns:
        AgentSpecWithAcceptanceResponse with full spec details and nested AcceptanceSpec

    Raises:
        400: If spec_id is not a valid UUID format
        404: If the project or AgentSpec is not found
    """
    # Validate project name and get path
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    # Step 2: Validate spec_id is valid UUID format
    if not _is_valid_uuid(spec_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format for spec_id: '{spec_id}'"
        )

    with get_db_session(project_dir) as db:
        # Step 3: Query AgentSpec by id with eager load of acceptance_spec relationship
        spec = (
            db.query(AgentSpecModel)
            .options(joinedload(AgentSpecModel.acceptance_spec))
            .filter(AgentSpecModel.id == spec_id)
            .first()
        )

        # Step 4: Return 404 if not found
        if not spec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AgentSpec '{spec_id}' not found"
            )

        # Convert to dict for response building
        spec_dict = spec.to_dict()

        # Step 5: Build response with nested AcceptanceSpec
        acceptance_spec_data = None
        if spec.acceptance_spec:
            acceptance_dict = spec.acceptance_spec.to_dict()
            acceptance_spec_data = AcceptanceSpecResponse(
                id=acceptance_dict["id"],
                agent_spec_id=acceptance_dict["agent_spec_id"],
                validators=acceptance_dict["validators"],
                gate_mode=acceptance_dict["gate_mode"],
                min_score=acceptance_dict["min_score"],
                retry_policy=acceptance_dict["retry_policy"],
                max_retries=acceptance_dict["max_retries"],
                fallback_spec_id=acceptance_dict["fallback_spec_id"],
            )

    return AgentSpecWithAcceptanceResponse(
        id=spec_dict["id"],
        name=spec_dict["name"],
        display_name=spec_dict["display_name"],
        icon=spec_dict["icon"],
        spec_version=spec_dict["spec_version"],
        objective=spec_dict["objective"],
        task_type=spec_dict["task_type"],
        context=spec_dict["context"],
        tool_policy=spec_dict["tool_policy"],
        max_turns=spec_dict["max_turns"],
        timeout_seconds=spec_dict["timeout_seconds"],
        parent_spec_id=spec_dict["parent_spec_id"],
        source_feature_id=spec_dict["source_feature_id"],
        spec_path=spec_dict.get("spec_path"),
        created_at=spec_dict["created_at"],
        priority=spec_dict["priority"],
        tags=spec_dict["tags"],
        acceptance_spec=acceptance_spec_data,
    )


# =============================================================================
# Execution Task Store (in-memory for async background tasks)
# =============================================================================

# Store for tracking background execution tasks
_execution_tasks: dict[str, asyncio.Task] = {}


async def _execute_spec_background(
    project_dir: Path,
    spec_id: str,
    run_id: str,
    project_name: str,
) -> None:
    """
    Background task to execute an AgentSpec via HarnessKernel.

    Feature #136: Wire execute endpoint to actually call HarnessKernel.execute().

    This function:
    1. Transitions the pre-created AgentRun to 'running' status
    2. Broadcasts WebSocket notification (Feature #61)
    3. Invokes HarnessKernel.execute(spec) for real kernel execution
    4. Syncs results from the kernel's run back to the pre-created run
    5. Handles errors gracefully, updating run status to 'failed' on failure

    Args:
        project_dir: Path to the project directory
        spec_id: UUID of the AgentSpec to execute
        run_id: UUID of the AgentRun record to update
        project_name: Name of the project (for WebSocket broadcasting)
    """
    # Import WebSocket broadcast function for Feature #61
    from api.websocket_events import broadcast_run_started

    _logger.info(f"Starting background execution for run {run_id} (spec {spec_id})")

    try:
        with get_db_session(project_dir) as db:
            # Get the run record
            run = db.query(AgentRunModel).filter(AgentRunModel.id == run_id).first()
            if not run:
                _logger.error(f"AgentRun {run_id} not found")
                return

            # Get the spec for display_name and icon
            spec = db.query(AgentSpecModel).filter(AgentSpecModel.id == spec_id).first()
            if not spec:
                _logger.error(f"AgentSpec {spec_id} not found for run {run_id}")
                run.status = "failed"
                run.completed_at = _utc_now()
                run.error = f"AgentSpec '{spec_id}' not found"
                db.commit()
                return
            display_name = spec.display_name if spec else f"Run {run_id[:8]}"
            icon = spec.icon if spec else None

            # Transition from pending to running
            run.status = "running"
            run.started_at = _utc_now()
            db.commit()
            _logger.info(f"Run {run_id} transitioned to 'running'")

            # Feature #61: Broadcast agent_run_started WebSocket message
            # Step 1: When AgentRun status changes to running, publish message
            # Step 2: Message type: agent_run_started
            # Step 3: Payload: run_id, spec_id, display_name, icon, started_at
            # Step 4: Broadcast to all connected clients
            await broadcast_run_started(
                project_name=project_name,
                run_id=run_id,
                spec_id=spec_id,
                display_name=display_name,
                icon=icon,
                started_at=run.started_at,
            )

        # Phase 2: Execute via HarnessKernel (Feature #136)
        # Use a separate DB session for the kernel execution to ensure
        # proper transaction isolation and commit behavior
        from api.harness_kernel import HarnessKernel

        with get_db_session(project_dir) as kernel_db:
            # Load the spec in the kernel's session with acceptance_spec eagerly loaded
            kernel_spec = kernel_db.query(AgentSpecModel).options(
                joinedload(AgentSpecModel.acceptance_spec)
            ).filter(AgentSpecModel.id == spec_id).first()

            if not kernel_spec:
                raise RuntimeError(f"AgentSpec '{spec_id}' not found in kernel session")

            _logger.info(f"Invoking HarnessKernel.execute() for spec {spec_id}")

            # Create kernel and execute the spec
            # The kernel creates its own AgentRun internally and manages
            # the full execution lifecycle (turns, events, acceptance, verdict)
            kernel = HarnessKernel(db=kernel_db)
            kernel_run = kernel.execute(
                kernel_spec,
                turn_executor=None,  # No Claude SDK executor yet; completes immediately
                context={
                    "project_dir": str(project_dir),
                },
            )

            _logger.info(
                f"HarnessKernel execution completed: kernel_run={kernel_run.id}, "
                f"status={kernel_run.status}, verdict={kernel_run.final_verdict}, "
                f"turns={kernel_run.turns_used}"
            )

            # Capture kernel run results before session closes
            kernel_status = kernel_run.status
            kernel_completed_at = kernel_run.completed_at
            kernel_turns_used = kernel_run.turns_used
            kernel_tokens_in = kernel_run.tokens_in
            kernel_tokens_out = kernel_run.tokens_out
            kernel_final_verdict = kernel_run.final_verdict
            kernel_acceptance_results = kernel_run.acceptance_results
            kernel_error = kernel_run.error
            kernel_retry_count = kernel_run.retry_count

        # Phase 3: Sync kernel results back to the pre-created run
        # The endpoint returned run_id to the client, so we update that
        # record with the actual execution results from HarnessKernel
        with get_db_session(project_dir) as sync_db:
            original_run = sync_db.query(AgentRunModel).filter(
                AgentRunModel.id == run_id
            ).first()

            if original_run:
                original_run.status = kernel_status
                original_run.completed_at = kernel_completed_at or _utc_now()
                original_run.turns_used = kernel_turns_used
                original_run.tokens_in = kernel_tokens_in
                original_run.tokens_out = kernel_tokens_out
                original_run.final_verdict = kernel_final_verdict
                original_run.acceptance_results = kernel_acceptance_results
                original_run.error = kernel_error
                original_run.retry_count = kernel_retry_count
                sync_db.commit()

                _logger.info(
                    f"Synced kernel results to original run {run_id}: "
                    f"status={kernel_status}, verdict={kernel_final_verdict}"
                )
            else:
                _logger.warning(f"Original run {run_id} not found during result sync")

    except Exception as e:
        _logger.exception(f"Error executing spec {spec_id}: {e}")
        # Mark run as failed with error details
        try:
            with get_db_session(project_dir) as db:
                run = db.query(AgentRunModel).filter(AgentRunModel.id == run_id).first()
                if run:
                    run.status = "failed"
                    run.completed_at = _utc_now()
                    run.error = str(e)
                    db.commit()
        except Exception as db_error:
            _logger.exception(f"Failed to update run status: {db_error}")
    finally:
        # Clean up task reference
        if run_id in _execution_tasks:
            del _execution_tasks[run_id]


@router.post(
    "/{spec_id}/execute",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {
            "description": "Execution queued successfully",
            "model": AgentRunResponse,
        },
        400: {
            "description": "AgentSpec validation failed",
            "model": SpecValidationErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "is_valid": False,
                        "errors": [
                            {
                                "field": "tool_policy.allowed_tools",
                                "message": "allowed_tools must contain at least one tool",
                                "code": "min_length"
                            }
                        ],
                        "spec_id": "abc-123",
                        "spec_name": "invalid-spec",
                        "error_count": 1
                    }
                }
            },
        },
        404: {
            "description": "AgentSpec not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentSpec 'abc-123' not found"}
                }
            },
        },
    },
)
async def execute_agent_spec(
    project_name: str,
    spec_id: str,
) -> AgentRunResponse:
    """
    Trigger execution of an AgentSpec via the HarnessKernel.

    Feature #78: Invalid AgentSpec Graceful Handling
    - Validates the AgentSpec BEFORE creating any AgentRun
    - Returns 400 with detailed validation errors if invalid
    - Only creates AgentRun and queues execution if spec passes validation

    Creates a new AgentRun record with status=pending, then queues the
    execution as a background task. Returns immediately with 202 Accepted
    and the new AgentRun record.

    The execution will:
    1. Validate AgentSpec (Feature #78, Steps 1-4)
    2. Transition the run to 'running' status
    3. Execute the spec via HarnessKernel (Feature #136)
    4. Record events for each tool call and turn
    5. Run acceptance validators
    6. Update final status (completed/failed/timeout)

    Args:
        project_name: Name of the project
        spec_id: UUID of the AgentSpec to execute

    Returns:
        AgentRunResponse with the new run record (status will be 'pending')

    Raises:
        400: If AgentSpec validation fails (Feature #78, Steps 5-6)
        404: If the AgentSpec is not found
    """
    # Import spec validator (lazy import to avoid circular dependencies)
    from api.spec_validator import validate_spec, SpecValidationResult

    # Validate project name and get path
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    with get_db_session(project_dir) as db:
        # Step 2: Query AgentSpec by id and verify exists
        spec = db.query(AgentSpecModel).filter(AgentSpecModel.id == spec_id).first()

        # Step 3: Return 404 if spec not found
        if not spec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AgentSpec '{spec_id}' not found"
            )

        # Feature #78, Steps 1-4: Validate AgentSpec before kernel execution
        # - Step 1: Validate AgentSpec before kernel execution
        # - Step 2: Check required fields are present
        # - Step 3: Validate tool_policy structure
        # - Step 4: Validate budget values within constraints
        validation_result: SpecValidationResult = validate_spec(spec)

        # Feature #78, Step 5: If invalid, return error without creating run
        if not validation_result.is_valid:
            _logger.warning(
                "AgentSpec validation failed for spec %s: %d errors",
                spec_id,
                len(validation_result.errors)
            )

            # Feature #78, Step 6: Include validation error details in response
            error_items = [
                ValidationErrorItem(
                    field=error.field,
                    message=error.message,
                    code=error.code,
                    value=str(error.value)[:100] if error.value is not None else None
                )
                for error in validation_result.errors
            ]

            validation_response = SpecValidationErrorResponse(
                is_valid=False,
                errors=error_items,
                spec_id=validation_result.spec_id,
                spec_name=validation_result.spec_name,
                error_count=len(validation_result.errors)
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation_response.model_dump()
            )

        # Validation passed - proceed with execution
        _logger.debug("AgentSpec %s validation passed", spec_id)

        # Step 4: Create new AgentRun with status=pending
        run_id = _generate_uuid()
        # Step 5: Set created_at to current UTC timestamp
        created_at = _utc_now()

        db_run = AgentRunModel(
            id=run_id,
            agent_spec_id=spec_id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
            created_at=created_at,
        )

        # Step 6: Commit run record to database
        db.add(db_run)
        db.commit()
        db.refresh(db_run)

        # Build response from the committed record
        run_dict = db_run.to_dict()

    # Step 7: Queue execution task (async background)
    task = asyncio.create_task(
        _execute_spec_background(project_dir, spec_id, run_id, project_name)
    )
    _execution_tasks[run_id] = task

    _logger.info(f"Queued execution for spec {spec_id}, run {run_id}")

    # Step 8: Return AgentRunResponse with status 202 Accepted
    return AgentRunResponse(
        id=run_dict["id"],
        agent_spec_id=run_dict["agent_spec_id"],
        status=run_dict["status"],
        started_at=run_dict["started_at"],
        completed_at=run_dict["completed_at"],
        turns_used=run_dict["turns_used"],
        tokens_in=run_dict["tokens_in"],
        tokens_out=run_dict["tokens_out"],
        final_verdict=run_dict["final_verdict"],
        acceptance_results=run_dict["acceptance_results"],
        error=run_dict["error"],
        retry_count=run_dict["retry_count"],
        created_at=run_dict["created_at"],
    )


@router.put(
    "/{spec_id}",
    response_model=AgentSpecResponse,
    responses={
        200: {
            "description": "AgentSpec updated successfully",
            "model": AgentSpecResponse,
        },
        400: {
            "description": "Database constraint violation or validation error",
            "content": {
                "application/json": {
                    "example": {"detail": "Database constraint violation: duplicate name"}
                }
            },
        },
        404: {
            "description": "AgentSpec not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentSpec 'abc-123' not found"}
                }
            },
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "max_turns"],
                                "msg": "Input should be less than or equal to 500",
                                "type": "less_than_equal",
                            }
                        ]
                    }
                }
            },
        },
    },
)
async def update_agent_spec(
    project_name: str,
    spec_id: str,
    spec_update: AgentSpecUpdate,
) -> AgentSpecResponse:
    """
    Update an existing AgentSpec with partial updates.

    Only provided fields (not None) will be updated. All fields in the request
    body are optional - omit fields you don't want to change.

    ## Field Constraints

    - **name**: Must be lowercase with hyphens (e.g., "my-spec-name")
    - **max_turns**: Must be between 1 and 500
    - **timeout_seconds**: Must be between 60 and 7200 seconds
    - **priority**: Must be between 1 and 9999

    ## Example

    To update only the display name and max_turns:
    ```json
    {
        "display_name": "New Display Name",
        "max_turns": 100
    }
    ```

    Args:
        project_name: Name of the project
        spec_id: UUID of the AgentSpec to update
        spec_update: AgentSpecUpdate with fields to update

    Returns:
        AgentSpecResponse with the updated spec

    Raises:
        404: If the AgentSpec is not found
        400: If a database constraint is violated (e.g., duplicate name)
        422: If validation fails (Pydantic handles this automatically)
    """
    # Step 1: Validate project name and get path
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    with get_db_session(project_dir) as db:
        # Step 2: Query existing AgentSpec by id
        spec = db.query(AgentSpecModel).filter(AgentSpecModel.id == spec_id).first()

        # Step 3: Return 404 if not found
        if not spec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AgentSpec '{spec_id}' not found"
            )

        # Step 4: Update only fields that are provided (not None)
        update_data = spec_update.model_dump(exclude_unset=True)

        # Step 5: Validate updated max_turns and timeout_seconds against constraints
        # Note: Pydantic already validates these in the AgentSpecUpdate schema,
        # but we add explicit checks here for clarity and custom error messages
        if "max_turns" in update_data:
            max_turns = update_data["max_turns"]
            if max_turns is not None:
                if max_turns < 1 or max_turns > 500:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="max_turns must be between 1 and 500"
                    )

        if "timeout_seconds" in update_data:
            timeout = update_data["timeout_seconds"]
            if timeout is not None:
                if timeout < 60 or timeout > 7200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="timeout_seconds must be between 60 and 7200"
                    )

        # Handle tool_policy specially - convert Pydantic model to dict if needed
        if "tool_policy" in update_data and update_data["tool_policy"] is not None:
            tool_policy = update_data["tool_policy"]
            # Check if it's a Pydantic model or already a dict
            if hasattr(tool_policy, 'model_dump'):
                update_data["tool_policy"] = tool_policy.model_dump()
            # Otherwise it's already a dict from model_dump(exclude_unset=True)

        # Apply updates to the model
        for field, value in update_data.items():
            if value is not None:  # Only update non-None values
                setattr(spec, field, value)

        # Step 6: Commit transaction
        try:
            db.commit()
            db.refresh(spec)
        except IntegrityError as e:
            db.rollback()
            # Extract useful info from the error
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)

            # Check for common constraint violations
            if "UNIQUE constraint failed" in error_msg:
                if "name" in error_msg:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Database constraint violation: duplicate name",
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Database constraint violation: unique constraint failed",
                )

            # Generic constraint violation
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Database constraint violation: {error_msg}",
            )

        # Step 7: Return updated AgentSpecResponse
        spec_dict = spec.to_dict()

    return AgentSpecResponse(
        id=spec_dict["id"],
        name=spec_dict["name"],
        display_name=spec_dict["display_name"],
        icon=spec_dict["icon"],
        spec_version=spec_dict["spec_version"],
        objective=spec_dict["objective"],
        task_type=spec_dict["task_type"],
        context=spec_dict["context"],
        tool_policy=spec_dict["tool_policy"],
        max_turns=spec_dict["max_turns"],
        timeout_seconds=spec_dict["timeout_seconds"],
        parent_spec_id=spec_dict["parent_spec_id"],
        source_feature_id=spec_dict["source_feature_id"],
        spec_path=spec_dict.get("spec_path"),
        created_at=spec_dict["created_at"],
        priority=spec_dict["priority"],
        tags=spec_dict["tags"],
    )


@router.delete(
    "/{spec_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {
            "description": "AgentSpec deleted successfully (including cascaded AcceptanceSpec, AgentRuns, Artifacts, and Events)"
        },
        400: {
            "description": "Invalid UUID format",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid UUID format for spec_id: 'not-a-uuid'"}
                }
            },
        },
        404: {
            "description": "AgentSpec not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentSpec 'abc-123' not found"}
                }
            },
        },
    },
)
async def delete_agent_spec(
    project_name: str,
    spec_id: str,
) -> Response:
    """
    Delete an AgentSpec and all related data with cascade behavior.

    This endpoint performs a cascade delete that removes:
    - The AgentSpec record itself
    - The linked AcceptanceSpec (if exists)
    - All AgentRuns for this spec
    - All Artifacts for those runs
    - All AgentEvents for those runs

    The cascade behavior is configured via:
    - ON DELETE CASCADE foreign key constraints in the database
    - SQLAlchemy relationship cascade="all, delete-orphan" settings

    ## Important Notes

    - This operation is **permanent** and cannot be undone
    - All execution history, artifacts, and events will be lost
    - Parent-child spec relationships are preserved (children are NOT deleted)

    Args:
        project_name: Name of the project
        spec_id: UUID of the AgentSpec to delete

    Returns:
        204 No Content on successful deletion

    Raises:
        400: If spec_id is not a valid UUID format
        404: If the project or AgentSpec is not found
    """
    # Step 1: Validate project name and get path
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    # Step 2: Validate spec_id is valid UUID format
    if not _is_valid_uuid(spec_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID format for spec_id: '{spec_id}'"
        )

    with get_db_session(project_dir) as db:
        # Step 3: Query AgentSpec by id
        spec = db.query(AgentSpecModel).filter(AgentSpecModel.id == spec_id).first()

        # Step 4: Return 404 if not found
        if not spec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AgentSpec '{spec_id}' not found"
            )

        # Step 5: Delete the AgentSpec record
        # The ON DELETE CASCADE constraints and SQLAlchemy cascade="all, delete-orphan"
        # will automatically delete:
        # - AcceptanceSpec (via agent_specs.acceptance_spec relationship)
        # - AgentRuns (via agent_specs.runs relationship)
        # - Artifacts (via agent_runs.artifacts relationship / FK ondelete=CASCADE)
        # - AgentEvents (via agent_runs.events relationship / FK ondelete=CASCADE)
        db.delete(spec)

        # Step 6: Commit transaction
        db.commit()

        _logger.info(
            f"Deleted AgentSpec {spec_id} with cascade (project: {project_name})"
        )

    # Step 7: Return 204 No Content
    return Response(status_code=status.HTTP_204_NO_CONTENT)
