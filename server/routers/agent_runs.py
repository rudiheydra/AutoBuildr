"""
Agent Runs Router
=================

API endpoints for AgentRun management and event timeline queries.

Implements:
- GET /api/agent-runs/:id - Get run details with spec info
- GET /api/agent-runs/:id/events - Event timeline with filtering
- GET /api/agent-runs/:id/artifacts - List artifacts without inline content
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from api.agentspec_crud import get_agent_run, get_agent_spec, get_event_count, get_events, list_artifacts
from api.agentspec_models import AgentEvent, Artifact, AgentRun as AgentRunModel
from api.database import get_db
from server.schemas.agentspec import (
    AgentEventListResponse,
    AgentEventResponse,
    AgentRunResponse,
    AgentRunSummary,
    AgentSpecResponse,
    ArtifactListItemResponse,
    ArtifactListResponse,
)


router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


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

    # Build AgentRunResponse from the run
    run_dict = run.to_dict()
    run_response = AgentRunResponse(
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
