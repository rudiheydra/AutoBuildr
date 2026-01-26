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
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.agentspec_models import AgentRun as AgentRunModel
from api.agentspec_models import AgentSpec as AgentSpecModel
from api.database import get_db
from server.schemas.agentspec import (
    AgentSpecCreate,
    AgentSpecListResponse,
    AgentSpecResponse,
    AgentSpecSummary,
)
from ..utils.validation import validate_project_name


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
        spec_data: AgentSpecCreate with spec configuration

    Returns:
        AgentSpecResponse with the created spec

    Raises:
        422: If validation fails (Pydantic handles this automatically)
        400: If a database constraint is violated (e.g., duplicate name)
    """
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
        priority=spec_data.priority,
        tags=spec_data.tags,
        created_at=created_at,
    )

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
                detail=f"Database constraint violation: unique constraint failed",
            )
        if "FOREIGN KEY constraint failed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database constraint violation: invalid foreign key reference",
            )
        if "CHECK constraint failed" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Database constraint violation: check constraint failed",
            )

        # Generic constraint violation
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database constraint violation: {error_msg}",
        )

    # Convert to response model
    spec_dict = db_spec.to_dict()

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
    response: Response,
    db: Session = Depends(get_db),
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
    GET /api/agent-specs?task_type=coding&limit=10&offset=0
    ```
    """
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
