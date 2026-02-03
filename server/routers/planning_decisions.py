"""
Planning Decisions Router
=========================

API endpoints for agent-planning decisions.

Feature #179: Maestro persists agent-planning decisions to database

Implements:
- GET /api/projects/{project_name}/planning-decisions - List decisions for project
- GET /api/projects/{project_name}/planning-decisions/:id - Get single decision
- POST /api/projects/{project_name}/planning-decisions - Create (evaluate + persist)
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

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


router = APIRouter(
    prefix="/api/projects/{project_name}/planning-decisions",
    tags=["planning-decisions"]
)


# =============================================================================
# Response Models
# =============================================================================

class CapabilityRequirementResponse(BaseModel):
    """A detected capability requirement."""
    capability: str
    source: str
    keywords_matched: list[str]
    confidence: str


class PlanningDecisionResponse(BaseModel):
    """Response model for an agent-planning decision."""
    id: str
    project_name: str
    requires_agent_planning: bool
    justification: str
    required_capabilities: list[dict[str, Any]]
    existing_capabilities: list[str]
    recommended_agent_types: list[str]
    project_context_snapshot: Optional[dict[str, Any]] = None
    triggering_feature_ids: Optional[list[int]] = None
    created_at: Optional[datetime] = None


class PlanningDecisionListResponse(BaseModel):
    """Response for listing planning decisions."""
    decisions: list[PlanningDecisionResponse]
    total: int


class EvaluateRequest(BaseModel):
    """Request to evaluate and persist a planning decision."""
    tech_stack: list[str] = Field(
        default_factory=list,
        description="List of technologies used in the project"
    )
    features: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of feature dictionaries to analyze"
    )
    existing_agents: Optional[list[str]] = Field(
        default=None,
        description="Currently available agents (defaults to coding + testing)"
    )
    triggering_feature_ids: Optional[list[int]] = Field(
        default=None,
        description="Feature IDs that triggered this evaluation"
    )


class EvaluateResponse(BaseModel):
    """Response for evaluate + persist endpoint."""
    success: bool
    decision_id: Optional[str] = None
    decision: Optional[PlanningDecisionResponse] = None
    error: Optional[str] = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    response_model=PlanningDecisionListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_planning_decisions(
    project_name: str,
    limit: int = Query(default=20, ge=1, le=100, description="Max decisions to return"),
    offset: int = Query(default=0, ge=0, description="Number of decisions to skip"),
    requires_planning: Optional[bool] = Query(
        default=None,
        description="Filter by requires_agent_planning flag"
    ),
) -> PlanningDecisionListResponse:
    """
    List agent-planning decisions for a project.

    Returns decisions ordered by created_at (most recent first).

    Args:
        project_name: Name of the project
        limit: Maximum number of decisions to return
        offset: Number of decisions to skip
        requires_planning: Optional filter by requires_agent_planning flag

    Returns:
        PlanningDecisionListResponse with decisions list and total count
    """
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    from api.agentspec_models import AgentPlanningDecisionRecord

    with get_db_session(project_dir) as session:
        # Build query
        query = session.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.project_name == project_name
        )

        # Apply optional filter
        if requires_planning is not None:
            query = query.filter(
                AgentPlanningDecisionRecord.requires_agent_planning == requires_planning
            )

        # Get total count
        total = query.count()

        # Order by created_at (most recent first) and apply pagination
        decisions = (
            query
            .order_by(AgentPlanningDecisionRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return PlanningDecisionListResponse(
            decisions=[
                PlanningDecisionResponse(**d.to_dict())
                for d in decisions
            ],
            total=total,
        )


@router.get(
    "/{decision_id}",
    response_model=PlanningDecisionResponse,
    status_code=status.HTTP_200_OK,
)
async def get_planning_decision(
    project_name: str,
    decision_id: str,
) -> PlanningDecisionResponse:
    """
    Get a single agent-planning decision by ID.

    Args:
        project_name: Name of the project
        decision_id: UUID of the decision

    Returns:
        PlanningDecisionResponse with the decision details
    """
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    from api.agentspec_models import AgentPlanningDecisionRecord

    with get_db_session(project_dir) as session:
        decision = session.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.id == decision_id,
            AgentPlanningDecisionRecord.project_name == project_name,
        ).first()

        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Decision '{decision_id}' not found"
            )

        return PlanningDecisionResponse(**decision.to_dict())


@router.post(
    "",
    response_model=EvaluateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_and_persist_decision(
    project_name: str,
    request: EvaluateRequest,
) -> EvaluateResponse:
    """
    Evaluate project context and persist the planning decision.

    This endpoint:
    1. Creates a ProjectContext from the request
    2. Evaluates whether agent-planning is required
    3. Persists the decision to the database
    4. Returns the created decision

    Args:
        project_name: Name of the project
        request: EvaluateRequest with tech_stack, features, etc.

    Returns:
        EvaluateResponse with success status and the created decision
    """
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    from api.maestro import (
        ProjectContext,
        get_maestro,
        DEFAULT_AGENTS,
    )

    # Build project context
    context = ProjectContext(
        project_name=project_name,
        project_dir=project_dir,
        tech_stack=request.tech_stack,
        features=request.features,
        existing_agents=request.existing_agents or list(DEFAULT_AGENTS),
    )

    with get_db_session(project_dir) as session:
        maestro = get_maestro()

        # Evaluate and persist
        decision, persist_result = maestro.evaluate_and_persist(
            context=context,
            session=session,
            triggering_feature_ids=request.triggering_feature_ids,
        )

        if not persist_result.success:
            return EvaluateResponse(
                success=False,
                error=persist_result.error,
            )

        return EvaluateResponse(
            success=True,
            decision_id=persist_result.decision_id,
            decision=PlanningDecisionResponse(**persist_result.record.to_dict()),
        )


@router.get(
    "/stats/summary",
    status_code=status.HTTP_200_OK,
)
async def get_planning_decisions_stats(
    project_name: str,
) -> dict[str, Any]:
    """
    Get statistics about planning decisions for a project.

    Returns counts of decisions requiring/not requiring agent planning.

    Args:
        project_name: Name of the project

    Returns:
        Dictionary with decision statistics
    """
    validate_project_name(project_name)
    try:
        project_dir = _get_project_path(project_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    from api.agentspec_models import AgentPlanningDecisionRecord
    from sqlalchemy import func

    with get_db_session(project_dir) as session:
        # Get total count
        total = session.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.project_name == project_name
        ).count()

        # Get count requiring planning
        requires_planning = session.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.project_name == project_name,
            AgentPlanningDecisionRecord.requires_agent_planning == True,
        ).count()

        # Get most recent decision
        latest = (
            session.query(AgentPlanningDecisionRecord)
            .filter(AgentPlanningDecisionRecord.project_name == project_name)
            .order_by(AgentPlanningDecisionRecord.created_at.desc())
            .first()
        )

        return {
            "project_name": project_name,
            "total_decisions": total,
            "decisions_requiring_planning": requires_planning,
            "decisions_not_requiring_planning": total - requires_planning,
            "latest_decision_id": latest.id if latest else None,
            "latest_decision_at": latest.created_at.isoformat() if latest else None,
        }
