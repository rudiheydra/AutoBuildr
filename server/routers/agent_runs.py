"""
Agent Runs Router
=================

API endpoints for AgentRun management and event timeline queries.

Implements:
- GET /api/agent-runs - List runs with filtering by agent_spec_id, status
- GET /api/agent-runs/:id - Get run details with spec info
- GET /api/agent-runs/:id/events - Event timeline with filtering
- GET /api/agent-runs/:id/artifacts - List artifacts without inline content
- POST /api/agent-runs/:id/pause - Pause a running agent
- POST /api/agent-runs/:id/resume - Resume a paused agent
- POST /api/agent-runs/:id/cancel - Cancel a running or paused agent
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from api.agentspec_crud import create_event, get_agent_run, get_agent_spec, get_event_count, get_events, list_artifacts, pause_run
from api.agentspec_models import AgentEvent, Artifact, AgentRun as AgentRunModel, RUN_STATUS, InvalidStateTransition
from api.database import get_db
from api.validators import normalize_acceptance_results_to_record
# Note: broadcast_agent_event_sync is imported locally where needed
from server.schemas.agentspec import (
    AgentEventListResponse,
    AgentEventResponse,
    AgentRunListResponse,
    AgentRunResponse,
    AgentRunSummary,
    AgentSpecResponse,
    ArtifactListItemResponse,
    ArtifactListResponse,
)


router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


def _build_run_response(run_dict: dict) -> AgentRunResponse:
    """
    Build an AgentRunResponse from a run dict, normalizing acceptance_results
    to canonical Record<string, AcceptanceValidatorResult> format.

    Feature #160: Standardize acceptance results to canonical format in backend.
    """
    # Normalize acceptance_results from list to record format
    raw_results = run_dict.get("acceptance_results")
    canonical_results = (
        normalize_acceptance_results_to_record(raw_results)
        if raw_results is not None
        else None
    )

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
        acceptance_results=canonical_results,
        error=run_dict["error"],
        retry_count=run_dict["retry_count"],
        created_at=run_dict["created_at"],
    )


@router.get(
    "",
    response_model=AgentRunListResponse,
    responses={
        200: {
            "description": "List of AgentRuns with pagination",
            "model": AgentRunListResponse,
            "headers": {
                "X-Total-Count": {
                    "description": "Total number of matching AgentRuns",
                    "schema": {"type": "integer"},
                }
            },
        },
        400: {
            "description": "Invalid parameter value",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid status. Must be one of: pending, running, paused, completed, failed, timeout"}
                }
            },
        },
    },
)
async def list_agent_runs(
    response: Response,
    agent_spec_id: Optional[str] = Query(
        None,
        description="Filter by AgentSpec ID (UUID)",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by run status (pending, running, paused, completed, failed, timeout)",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Maximum number of results to return (1-100)",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of results to skip for pagination",
    ),
    db: Session = Depends(get_db),
):
    """
    List AgentRuns with optional filtering and pagination.

    Returns a paginated list of AgentRuns ordered by created_at descending (newest first).
    Supports filtering by agent_spec_id and status.

    ## Filters

    - **agent_spec_id**: Filter runs by the parent AgentSpec UUID
    - **status**: Filter by run status (pending, running, paused, completed, failed, timeout)

    ## Pagination

    - **limit**: Max results per page (default 50, max 100)
    - **offset**: Skip first N results

    ## Response Headers

    - **X-Total-Count**: Total number of matching runs (for building pagination UI)

    ## Example

    ```
    GET /api/agent-runs?status=completed&limit=10&offset=0
    GET /api/agent-runs?agent_spec_id=abc12345-6789-def0-1234-567890abcdef
    ```
    """
    # Step 1: Build base query
    query = db.query(AgentRunModel)

    # Step 2: Validate and apply agent_spec_id filter if provided
    if agent_spec_id is not None:
        query = query.filter(AgentRunModel.agent_spec_id == agent_spec_id)

    # Step 3: Validate and apply status filter if provided
    if status is not None:
        if status not in RUN_STATUS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Must be one of: {', '.join(RUN_STATUS)}",
            )
        query = query.filter(AgentRunModel.status == status)

    # Step 4: Get total count before pagination (for X-Total-Count header)
    total_count = query.count()

    # Step 5: Order by created_at descending (newest first)
    query = query.order_by(AgentRunModel.created_at.desc())

    # Step 6: Apply pagination
    query = query.offset(offset).limit(limit)

    # Step 7: Execute query
    runs = query.all()

    # Step 8: Build response (Feature #160: canonical acceptance_results format)
    run_responses = []
    for run in runs:
        run_dict = run.to_dict()
        run_responses.append(_build_run_response(run_dict))

    # Step 9: Set X-Total-Count header
    response.headers["X-Total-Count"] = str(total_count)

    # Step 10: Return AgentRunListResponse with total count
    return AgentRunListResponse(
        runs=run_responses,
        total=total_count,
        offset=offset,
        limit=limit,
    )


@router.get("/{run_id}", response_model=AgentRunSummary)
async def get_run_details(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve full details of an AgentRun with spec info.

    Returns the AgentRun with its associated AgentSpec summary, including
    display_name and icon for UI display. Also includes event and artifact counts.

    Args:
        run_id: UUID of the AgentRun

    Returns:
        AgentRunSummary with run, spec, event_count, and artifact_count

    Raises:
        404: If the AgentRun is not found
    """
    # Query AgentRun with eager load of agent_spec
    run = (
        db.query(AgentRunModel)
        .options(joinedload(AgentRunModel.agent_spec))
        .filter(AgentRunModel.id == run_id)
        .first()
    )

    if not run:
        raise HTTPException(status_code=404, detail=f"AgentRun {run_id} not found")

    # Get event and artifact counts
    event_count = get_event_count(db, run_id)
    artifact_count = len(list_artifacts(db, run_id))

    # Build AgentRunResponse from the run (Feature #160: canonical acceptance_results format)
    run_dict = run.to_dict()
    run_response = _build_run_response(run_dict)

    # Build AgentSpecResponse if spec exists (includes display_name and icon)
    spec_response = None
    if run.agent_spec:
        spec_dict = run.agent_spec.to_dict()
        spec_response = AgentSpecResponse(
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
            created_at=spec_dict["created_at"],
            priority=spec_dict["priority"],
            tags=spec_dict["tags"],
        )

    return AgentRunSummary(
        run=run_response,
        spec=spec_response,
        event_count=event_count,
        artifact_count=artifact_count,
    )


@router.get("/{run_id}/events", response_model=AgentEventListResponse)
async def get_run_events(
    run_id: str,
    event_type: Optional[str] = Query(
        None,
        description="Filter events by type (started, tool_call, tool_result, turn_complete, acceptance_check, completed, failed, paused, resumed)"
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Maximum number of events to return (1-500)"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of events to skip for pagination"
    ),
    db: Session = Depends(get_db),
):
    """
    Retrieve ordered event timeline for an AgentRun.

    Returns events in sequence order with optional filtering by event_type.
    Supports pagination via limit and offset parameters.

    This endpoint is used by the Run Inspector UI to display the event timeline.

    Args:
        run_id: UUID of the AgentRun
        event_type: Optional filter for specific event types
        limit: Max events to return (default 50, max 500)
        offset: Number of events to skip (for pagination)

    Returns:
        AgentEventListResponse with events and pagination metadata

    Raises:
        404: If the AgentRun is not found
        400: If event_type is invalid
    """
    # Validate run exists
    run = get_agent_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"AgentRun {run_id} not found")

    # Validate event_type if provided
    valid_event_types = [
        "started", "tool_call", "tool_result", "turn_complete",
        "acceptance_check", "completed", "failed", "paused", "resumed"
    ]
    if event_type and event_type not in valid_event_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type '{event_type}'. Must be one of: {', '.join(valid_event_types)}"
        )

    # Get total count (for the specific filter if applied)
    if event_type:
        # Count events of this type
        total_query = (
            db.query(AgentEvent)
            .filter(AgentEvent.run_id == run_id)
            .filter(AgentEvent.event_type == event_type)
        )
        total = total_query.count()
    else:
        total = get_event_count(db, run_id)

    # Get events with pagination
    # Use raw query for offset support (get_events uses after_sequence which is different)
    query = db.query(AgentEvent).filter(AgentEvent.run_id == run_id)
    if event_type:
        query = query.filter(AgentEvent.event_type == event_type)

    events = (
        query.order_by(AgentEvent.sequence)
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Build response
    event_responses = [
        AgentEventResponse(
            id=e.id,
            run_id=e.run_id,
            event_type=e.event_type,
            timestamp=e.timestamp,
            sequence=e.sequence,
            payload=e.payload,
            payload_truncated=e.payload_truncated,
            artifact_ref=e.artifact_ref,
            tool_name=e.tool_name,
        )
        for e in events
    ]

    # Calculate start/end sequence and has_more
    start_sequence = events[0].sequence if events else None
    end_sequence = events[-1].sequence if events else None
    has_more = offset + len(events) < total

    return AgentEventListResponse(
        events=event_responses,
        total=total,
        run_id=run_id,
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        has_more=has_more,
    )


@router.get("/{run_id}/artifacts", response_model=ArtifactListResponse)
async def get_run_artifacts(
    run_id: str,
    artifact_type: Optional[str] = Query(
        None,
        description="Filter artifacts by type (file_change, test_result, log, metric, snapshot)"
    ),
    db: Session = Depends(get_db),
):
    """
    List artifacts for an AgentRun without inline content.

    Returns artifacts with metadata but excludes content_inline for performance.
    Use GET /api/artifacts/:id to retrieve full artifact content.

    This endpoint is optimized for listing artifacts in the Run Inspector UI.

    Args:
        run_id: UUID of the AgentRun
        artifact_type: Optional filter for specific artifact types

    Returns:
        ArtifactListResponse with artifacts list (without content), total count, and run_id

    Raises:
        404: If the AgentRun is not found
        400: If artifact_type is invalid
    """
    # Validate run exists
    run = get_agent_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"AgentRun {run_id} not found")

    # Validate artifact_type if provided
    valid_artifact_types = ["file_change", "test_result", "log", "metric", "snapshot"]
    if artifact_type and artifact_type not in valid_artifact_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artifact_type '{artifact_type}'. Must be one of: {', '.join(valid_artifact_types)}"
        )

    # Query artifacts with optional type filter
    artifacts = list_artifacts(db, run_id, artifact_type=artifact_type)

    # Build response list (excluding content_inline for performance)
    artifact_responses = [
        ArtifactListItemResponse(
            id=a.id,
            run_id=a.run_id,
            artifact_type=a.artifact_type,
            path=a.path,
            content_ref=a.content_ref,
            content_hash=a.content_hash,
            size_bytes=a.size_bytes,
            created_at=a.created_at,
            metadata=a.artifact_metadata,
            # Compute has_inline_content without including actual content
            has_inline_content=a.content_inline is not None and len(a.content_inline) > 0,
        )
        for a in artifacts
    ]

    return ArtifactListResponse(
        artifacts=artifact_responses,
        total=len(artifacts),
        run_id=run_id,
    )


# =============================================================================
# AgentRun Lifecycle Endpoints
# =============================================================================


@router.post(
    "/{run_id}/pause",
    response_model=AgentRunResponse,
    responses={
        200: {
            "description": "AgentRun successfully paused",
            "model": AgentRunResponse,
        },
        404: {
            "description": "AgentRun not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentRun abc123-... not found"}
                }
            },
        },
        409: {
            "description": "Conflict - run is not in running status",
            "content": {
                "application/json": {
                    "example": {"detail": "Cannot pause AgentRun abc123-...: status is 'paused', must be 'running'"}
                }
            },
        },
    },
)
async def pause_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Pause a running agent execution.

    Transitions the AgentRun from running to paused status. This allows
    the agent's execution to be temporarily halted and later resumed.

    ## State Transitions

    - Only runs in `running` status can be paused
    - Paused runs can be resumed (transition back to `running`)
    - Paused runs can be cancelled (transition to `failed`)

    ## Side Effects

    - Updates run status to `paused`
    - Records a `paused` AgentEvent in the event timeline
    - Signals the kernel to pause execution (if currently executing)
    - Broadcasts WebSocket event for UI updates

    ## Example

    ```
    POST /api/agent-runs/abc12345-6789-def0-1234-567890abcdef/pause
    ```

    ## Response

    Returns the updated AgentRunResponse with status='paused'.

    Args:
        run_id: UUID of the AgentRun to pause

    Returns:
        AgentRunResponse with updated status

    Raises:
        404: If the AgentRun is not found
        409: If the run is not in 'running' status
    """
    # Step 2: Query AgentRun by id
    run = get_agent_run(db, run_id)

    # Step 3: Return 404 if not found
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"AgentRun {run_id} not found"
        )

    # Step 4: Return 409 Conflict if status is not running
    if run.status != "running":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pause AgentRun {run_id}: status is '{run.status}', must be 'running'"
        )

    # Step 5: Update status to paused using state machine
    try:
        run.pause()  # Uses the model's state machine method
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )

    # Step 6: Record paused AgentEvent
    create_event(
        db,
        run_id=run_id,
        event_type="paused",
        payload={
            "previous_status": "running",
            "new_status": "paused",
            "turns_used": run.turns_used,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
        },
    )

    # Step 7: Commit transaction
    db.commit()

    # Step 8: Signal kernel to pause (via event broadcaster for UI updates)
    # The kernel will check for pause signals during execution
    # Note: We broadcast via sync wrapper since we may not know the project name here
    # The event has already been recorded in the database, so UI updates are optional
    try:
        from server.event_broadcaster import broadcast_agent_event_sync
        # Use a default project name for broadcasting - this is optional
        broadcast_agent_event_sync(
            project_name="AutoBuildr",  # Default project
            run_id=run_id,
            event_type="paused",
            sequence=0,  # Will be set by create_event
            tool_name=None,
        )
    except Exception:
        # Broadcasting is optional - don't fail the pause operation
        pass

    # Step 9: Return updated AgentRunResponse (Feature #160: canonical format)
    run_dict = run.to_dict()
    return _build_run_response(run_dict)


@router.post(
    "/{run_id}/resume",
    response_model=AgentRunResponse,
    responses={
        200: {
            "description": "AgentRun successfully resumed",
            "model": AgentRunResponse,
        },
        404: {
            "description": "AgentRun not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentRun abc123-... not found"}
                }
            },
        },
        409: {
            "description": "Conflict - run is not in paused status",
            "content": {
                "application/json": {
                    "example": {"detail": "Cannot resume AgentRun abc123-...: status is 'running', must be 'paused'"}
                }
            },
        },
    },
)
async def resume_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Resume a paused agent execution.

    Transitions the AgentRun from paused to running status. This allows
    a previously paused agent's execution to continue from where it left off.

    ## State Transitions

    - Only runs in `paused` status can be resumed
    - Resumed runs transition to `running` status
    - Running runs can then complete, fail, timeout, or be paused again

    ## Side Effects

    - Updates run status to `running`
    - Records a `resumed` AgentEvent in the event timeline
    - Signals the kernel to resume execution
    - Broadcasts WebSocket event for UI updates

    ## Example

    ```
    POST /api/agent-runs/abc12345-6789-def0-1234-567890abcdef/resume
    ```

    ## Response

    Returns the updated AgentRunResponse with status='running'.

    Args:
        run_id: UUID of the AgentRun to resume

    Returns:
        AgentRunResponse with updated status

    Raises:
        404: If the AgentRun is not found
        409: If the run is not in 'paused' status
    """
    # Step 2: Query AgentRun by id
    run = get_agent_run(db, run_id)

    # Step 3: Return 404 if not found
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"AgentRun {run_id} not found"
        )

    # Step 4: Return 409 Conflict if status is not paused
    if run.status != "paused":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume AgentRun {run_id}: status is '{run.status}', must be 'paused'"
        )

    # Step 5: Update status to running using state machine
    try:
        run.resume()  # Uses the model's state machine method
    except InvalidStateTransition as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )

    # Step 6: Record resumed AgentEvent
    create_event(
        db,
        run_id=run_id,
        event_type="resumed",
        payload={
            "previous_status": "paused",
            "new_status": "running",
            "turns_used": run.turns_used,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
        },
    )

    # Step 7: Commit transaction
    db.commit()

    # Step 8: Signal kernel to resume (via event broadcaster for UI updates)
    # The kernel will check for resume signals during execution
    # Note: We broadcast via sync wrapper since we may not know the project name here
    # The event has already been recorded in the database, so UI updates are optional
    try:
        from server.event_broadcaster import broadcast_agent_event_sync
        # Use a default project name for broadcasting - this is optional
        broadcast_agent_event_sync(
            project_name="AutoBuildr",  # Default project
            run_id=run_id,
            event_type="resumed",
            sequence=0,  # Will be set by create_event
            tool_name=None,
        )
    except Exception:
        # Broadcasting is optional - don't fail the resume operation
        pass

    # Step 9: Return updated AgentRunResponse (Feature #160: canonical format)
    run_dict = run.to_dict()
    return _build_run_response(run_dict)


@router.post(
    "/{run_id}/cancel",
    response_model=AgentRunResponse,
    responses={
        200: {
            "description": "AgentRun successfully cancelled",
            "model": AgentRunResponse,
        },
        404: {
            "description": "AgentRun not found",
            "content": {
                "application/json": {
                    "example": {"detail": "AgentRun abc123-... not found"}
                }
            },
        },
        409: {
            "description": "Conflict - run is in a terminal status (completed, failed, timeout)",
            "content": {
                "application/json": {
                    "example": {"detail": "Cannot cancel AgentRun abc123-...: status is 'completed', already in terminal state"}
                }
            },
        },
    },
)
async def cancel_agent_run(
    run_id: str,
    db: Session = Depends(get_db),
):
    """
    Cancel a running or paused agent execution.

    Transitions the AgentRun to failed status with error='user_cancelled'.
    This allows a user to terminate an agent's execution permanently.

    ## State Transitions

    - Runs in `pending`, `running`, or `paused` status can be cancelled
    - Cancelled runs transition to `failed` status
    - Terminal states (`completed`, `failed`, `timeout`) cannot be cancelled

    ## Side Effects

    - Updates run status to `failed`
    - Sets error to `user_cancelled`
    - Sets completed_at to current timestamp
    - Records a `failed` AgentEvent with cancellation reason
    - Signals the kernel to abort execution (if currently executing)
    - Broadcasts WebSocket event for UI updates

    ## Example

    ```
    POST /api/agent-runs/abc12345-6789-def0-1234-567890abcdef/cancel
    ```

    ## Response

    Returns the updated AgentRunResponse with status='failed' and error='user_cancelled'.

    Args:
        run_id: UUID of the AgentRun to cancel

    Returns:
        AgentRunResponse with updated status

    Raises:
        404: If the AgentRun is not found
        409: If the run is already in a terminal state (completed, failed, timeout)
    """
    # Step 2: Query AgentRun by id
    run = get_agent_run(db, run_id)

    # Step 3: Return 404 if not found
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"AgentRun {run_id} not found"
        )

    # Step 4: Return 409 if status is already completed, failed, or timeout
    terminal_statuses = {"completed", "failed", "timeout"}
    if run.status in terminal_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel AgentRun {run_id}: status is '{run.status}', already in terminal state"
        )

    # Store previous status for event payload
    previous_status = run.status

    # Step 5 & 6 & 7: Update status to failed, set error to user_cancelled, set completed_at
    # Handle pending status specially since it can't normally transition to failed
    # For running and paused, use the model's fail() method for proper state machine handling
    if run.status == "pending":
        # Direct update for pending status (can't use fail() due to state machine constraints)
        from datetime import datetime, timezone
        run.status = "failed"
        run.error = "user_cancelled"
        run.completed_at = datetime.now(timezone.utc)
    else:
        # Use the model's fail() method for proper state machine handling (running/paused)
        try:
            run.fail(error_message="user_cancelled")
        except InvalidStateTransition as e:
            raise HTTPException(
                status_code=409,
                detail=str(e)
            )

    # Step 8: Record failed event with cancellation reason
    create_event(
        db,
        run_id=run_id,
        event_type="failed",
        payload={
            "reason": "user_cancelled",
            "previous_status": previous_status,
            "new_status": "failed",
            "turns_used": run.turns_used,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
        },
    )

    # Commit transaction
    db.commit()

    # Step 9: Signal kernel to abort (via event broadcaster for UI updates)
    # The kernel will check for abort signals during execution
    # Note: We broadcast via sync wrapper since we may not know the project name here
    # The event has already been recorded in the database, so UI updates are optional
    try:
        from server.event_broadcaster import broadcast_agent_event_sync
        # Use a default project name for broadcasting - this is optional
        broadcast_agent_event_sync(
            project_name="AutoBuildr",  # Default project
            run_id=run_id,
            event_type="failed",
            sequence=0,  # Will be set by create_event
            tool_name=None,
        )
    except Exception:
        # Broadcasting is optional - don't fail the cancel operation
        pass

    # Step 10: Return updated AgentRunResponse (Feature #160: canonical format)
    run_dict = run.to_dict()
    return _build_run_response(run_dict)
