"""
AgentSpec CRUD Operations
=========================

Database operations for AgentSpec, AcceptanceSpec, AgentRun, Artifact, and AgentEvent.

These helpers are designed for use by:
- The harness kernel (Milestone 2)
- MCP tools (future)
- API routes (future)

All operations are session-based for flexibility in transaction management.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from api.agentspec_models import (
    ARTIFACT_INLINE_MAX_SIZE,
    EVENT_PAYLOAD_MAX_SIZE,
    AcceptanceSpec,
    AgentEvent,
    AgentRun,
    AgentSpec,
    Artifact,
    create_tool_policy,
    generate_uuid,
)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# AgentSpec CRUD
# =============================================================================

def create_agent_spec(
    session: Session,
    name: str,
    display_name: str,
    objective: str,
    task_type: str,
    allowed_tools: list[str],
    *,
    icon: str | None = None,
    context: dict[str, Any] | None = None,
    forbidden_patterns: list[str] | None = None,
    tool_hints: dict[str, str] | None = None,
    max_turns: int = 50,
    timeout_seconds: int = 1800,
    parent_spec_id: str | None = None,
    source_feature_id: int | None = None,
    spec_path: str | None = None,
    priority: int = 500,
    tags: list[str] | None = None,
    spec_version: str = "v1",
) -> AgentSpec:
    """
    Create a new AgentSpec.

    Args:
        session: SQLAlchemy session
        name: Machine-friendly name (e.g., "feature-auth-login-impl")
        display_name: Human-friendly name (e.g., "Implement Login Feature")
        objective: Clear goal statement
        task_type: One of: coding, testing, refactoring, documentation, audit, custom
        allowed_tools: List of MCP tool names the agent can use
        icon: Optional emoji or icon identifier
        context: Optional task-specific context dict
        forbidden_patterns: Optional regex patterns to block
        tool_hints: Optional hints for tool usage
        max_turns: Execution budget (API round-trips)
        timeout_seconds: Wall-clock timeout
        parent_spec_id: Parent spec ID for sub-agent spawning (future)
        source_feature_id: Linked Feature ID (optional)
        spec_path: Optional file path to the spec definition
        priority: Execution priority (lower = higher priority)
        tags: Optional tags for filtering
        spec_version: Version string for forward compatibility

    Returns:
        Created AgentSpec instance
    """
    tool_policy = create_tool_policy(
        allowed_tools=allowed_tools,
        forbidden_patterns=forbidden_patterns,
        tool_hints=tool_hints,
    )

    spec = AgentSpec(
        id=generate_uuid(),
        name=name,
        display_name=display_name,
        icon=icon,
        spec_version=spec_version,
        objective=objective,
        task_type=task_type,
        context=context,
        tool_policy=tool_policy,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
        parent_spec_id=parent_spec_id,
        source_feature_id=source_feature_id,
        spec_path=spec_path,
        priority=priority,
        tags=tags,
    )

    session.add(spec)
    session.flush()  # Get ID assigned
    return spec


def get_agent_spec(session: Session, spec_id: str) -> AgentSpec | None:
    """Get an AgentSpec by ID."""
    return session.query(AgentSpec).filter(AgentSpec.id == spec_id).first()


def get_agent_spec_by_feature(session: Session, feature_id: int) -> AgentSpec | None:
    """Get the most recent AgentSpec linked to a Feature."""
    return (
        session.query(AgentSpec)
        .filter(AgentSpec.source_feature_id == feature_id)
        .order_by(desc(AgentSpec.created_at))
        .first()
    )


def list_agent_specs(
    session: Session,
    *,
    task_type: str | None = None,
    source_feature_id: int | None = None,
    tags: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentSpec]:
    """
    List AgentSpecs with optional filters.

    Args:
        session: SQLAlchemy session
        task_type: Filter by task type
        source_feature_id: Filter by linked feature
        tags: Filter by tags (any match)
        limit: Max results
        offset: Skip first N results

    Returns:
        List of AgentSpec instances
    """
    query = session.query(AgentSpec)

    if task_type:
        query = query.filter(AgentSpec.task_type == task_type)
    if source_feature_id is not None:
        query = query.filter(AgentSpec.source_feature_id == source_feature_id)
    # Note: tag filtering requires JSON containment which varies by DB
    # For SQLite, we'd need to iterate - skip for now

    return (
        query.order_by(AgentSpec.priority, AgentSpec.created_at)
        .offset(offset)
        .limit(limit)
        .all()
    )


def delete_agent_spec(session: Session, spec_id: str) -> bool:
    """
    Delete an AgentSpec and all related data (cascades).

    Returns True if deleted, False if not found.
    """
    spec = get_agent_spec(session, spec_id)
    if spec:
        session.delete(spec)
        session.flush()
        return True
    return False


# =============================================================================
# AcceptanceSpec CRUD
# =============================================================================

def create_acceptance_spec(
    session: Session,
    agent_spec_id: str,
    validators: list[dict[str, Any]],
    *,
    gate_mode: str = "all_pass",
    min_score: float | None = None,
    retry_policy: str = "none",
    max_retries: int = 0,
    fallback_spec_id: str | None = None,
) -> AcceptanceSpec:
    """
    Create an AcceptanceSpec for an AgentSpec.

    Args:
        session: SQLAlchemy session
        agent_spec_id: ID of the AgentSpec
        validators: List of validator definitions
        gate_mode: How validators combine (all_pass, any_pass, weighted)
        min_score: Minimum score for weighted mode
        retry_policy: Behavior on failure (none, fixed, exponential)
        max_retries: Max retry attempts
        fallback_spec_id: Alternative spec if all retries fail

    Returns:
        Created AcceptanceSpec instance
    """
    acceptance = AcceptanceSpec(
        id=generate_uuid(),
        agent_spec_id=agent_spec_id,
        validators=validators,
        gate_mode=gate_mode,
        min_score=min_score,
        retry_policy=retry_policy,
        max_retries=max_retries,
        fallback_spec_id=fallback_spec_id,
    )

    session.add(acceptance)
    session.flush()
    return acceptance


def get_acceptance_spec(session: Session, agent_spec_id: str) -> AcceptanceSpec | None:
    """Get AcceptanceSpec for an AgentSpec."""
    return (
        session.query(AcceptanceSpec)
        .filter(AcceptanceSpec.agent_spec_id == agent_spec_id)
        .first()
    )


# =============================================================================
# AgentRun CRUD
# =============================================================================

def create_agent_run(session: Session, agent_spec_id: str) -> AgentRun:
    """
    Create a new AgentRun for an AgentSpec.

    The run starts in 'pending' status.
    """
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=agent_spec_id,
        status="pending",
    )

    session.add(run)
    session.flush()
    return run


def get_agent_run(session: Session, run_id: str) -> AgentRun | None:
    """Get an AgentRun by ID."""
    return session.query(AgentRun).filter(AgentRun.id == run_id).first()


def get_latest_run(session: Session, agent_spec_id: str) -> AgentRun | None:
    """Get the most recent run for an AgentSpec."""
    return (
        session.query(AgentRun)
        .filter(AgentRun.agent_spec_id == agent_spec_id)
        .order_by(desc(AgentRun.created_at))
        .first()
    )


def list_runs(
    session: Session,
    *,
    agent_spec_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentRun]:
    """List AgentRuns with optional filters."""
    query = session.query(AgentRun)

    if agent_spec_id:
        query = query.filter(AgentRun.agent_spec_id == agent_spec_id)
    if status:
        query = query.filter(AgentRun.status == status)

    return (
        query.order_by(desc(AgentRun.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )


def start_run(session: Session, run_id: str) -> AgentRun | None:
    """
    Mark a run as started.

    Updates status to 'running' and sets started_at.
    """
    run = get_agent_run(session, run_id)
    if run and run.status == "pending":
        run.status = "running"
        run.started_at = _utc_now()
        session.flush()
    return run


def complete_run(
    session: Session,
    run_id: str,
    verdict: str,
    acceptance_results: list[dict[str, Any]] | None = None,
) -> AgentRun | None:
    """
    Mark a run as completed.

    Args:
        session: SQLAlchemy session
        run_id: Run ID
        verdict: One of: passed, failed, error
        acceptance_results: List of validator results

    Returns:
        Updated AgentRun or None if not found
    """
    run = get_agent_run(session, run_id)
    if run and run.status == "running":
        run.status = "completed"
        run.completed_at = _utc_now()
        run.final_verdict = verdict
        run.acceptance_results = acceptance_results
        session.flush()
    return run


def fail_run(
    session: Session,
    run_id: str,
    error: str,
    acceptance_results: list[dict[str, Any]] | None = None,
) -> AgentRun | None:
    """Mark a run as failed with an error message."""
    run = get_agent_run(session, run_id)
    if run and run.status in ("running", "pending"):
        run.status = "failed"
        run.completed_at = _utc_now()
        run.final_verdict = "failed"
        run.error = error
        run.acceptance_results = acceptance_results
        session.flush()
    return run


def timeout_run(session: Session, run_id: str) -> AgentRun | None:
    """Mark a run as timed out."""
    run = get_agent_run(session, run_id)
    if run and run.status == "running":
        run.status = "timeout"
        run.completed_at = _utc_now()
        run.final_verdict = "failed"
        run.error = "Execution timeout exceeded"
        session.flush()
    return run


def pause_run(session: Session, run_id: str) -> AgentRun | None:
    """Pause a running run."""
    run = get_agent_run(session, run_id)
    if run and run.status == "running":
        run.status = "paused"
        session.flush()
    return run


def resume_run(session: Session, run_id: str) -> AgentRun | None:
    """Resume a paused run."""
    run = get_agent_run(session, run_id)
    if run and run.status == "paused":
        run.status = "running"
        session.flush()
    return run


def update_run_metrics(
    session: Session,
    run_id: str,
    turns_used: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
) -> AgentRun | None:
    """Update execution metrics for a run."""
    run = get_agent_run(session, run_id)
    if run:
        if turns_used is not None:
            run.turns_used = turns_used
        if tokens_in is not None:
            run.tokens_in = tokens_in
        if tokens_out is not None:
            run.tokens_out = tokens_out
        session.flush()
    return run


def increment_retry(session: Session, run_id: str) -> AgentRun | None:
    """Increment retry count and reset status for retry."""
    run = get_agent_run(session, run_id)
    if run:
        run.retry_count += 1
        run.status = "pending"
        run.started_at = None
        run.completed_at = None
        run.error = None
        session.flush()
    return run


# =============================================================================
# Artifact CRUD
# =============================================================================

def _compute_hash(content: bytes | str) -> str:
    """Compute SHA256 hash of content."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _get_artifact_storage_path(project_dir: Path, run_id: str, content_hash: str) -> Path:
    """Get the storage path for an artifact blob."""
    artifacts_dir = project_dir / ".autobuildr" / "artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir / f"{content_hash}.blob"


def create_artifact(
    session: Session,
    run_id: str,
    artifact_type: str,
    content: bytes | str,
    *,
    project_dir: Path | None = None,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """
    Create an artifact with content storage.

    Small content (<=4KB) is stored inline.
    Large content is stored in files at .autobuildr/artifacts/{run_id}/{hash}.blob

    Args:
        session: SQLAlchemy session
        run_id: Run ID
        artifact_type: One of: file_change, test_result, log, metric, snapshot
        content: Content as bytes or string
        project_dir: Project directory for file storage (required for large content)
        path: Source path for file artifacts
        metadata: Optional type-specific metadata

    Returns:
        Created Artifact instance
    """
    # Convert to bytes for size calculation and hashing
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
        content_str = content
    else:
        content_bytes = content
        content_str = None  # Will decode if needed

    content_hash = _compute_hash(content_bytes)
    size_bytes = len(content_bytes)

    artifact = Artifact(
        id=generate_uuid(),
        run_id=run_id,
        artifact_type=artifact_type,
        path=path,
        content_hash=content_hash,
        size_bytes=size_bytes,
        metadata=metadata,
    )

    # Store inline or in file based on size
    if size_bytes <= ARTIFACT_INLINE_MAX_SIZE:
        # Store inline
        if content_str is None:
            content_str = content_bytes.decode("utf-8", errors="replace")
        artifact.content_inline = content_str
    else:
        # Store in file
        if project_dir is None:
            raise ValueError("project_dir required for large artifacts")

        storage_path = _get_artifact_storage_path(project_dir, run_id, content_hash)

        # Check if already exists (content-addressable dedup)
        if not storage_path.exists():
            storage_path.write_bytes(content_bytes)

        artifact.content_ref = str(storage_path.relative_to(project_dir))

    session.add(artifact)
    session.flush()
    return artifact


def get_artifact(session: Session, artifact_id: str) -> Artifact | None:
    """Get an artifact by ID."""
    return session.query(Artifact).filter(Artifact.id == artifact_id).first()


def get_artifact_content(
    artifact: Artifact,
    project_dir: Path | None = None,
) -> bytes | None:
    """
    Retrieve artifact content.

    Args:
        artifact: Artifact instance
        project_dir: Project directory for file-based artifacts

    Returns:
        Content as bytes, or None if not available
    """
    if artifact.content_inline is not None:
        return artifact.content_inline.encode("utf-8")

    if artifact.content_ref and project_dir:
        storage_path = project_dir / artifact.content_ref
        if storage_path.exists():
            return storage_path.read_bytes()

    return None


def list_artifacts(
    session: Session,
    run_id: str,
    *,
    artifact_type: str | None = None,
) -> list[Artifact]:
    """List artifacts for a run with optional type filter."""
    query = session.query(Artifact).filter(Artifact.run_id == run_id)

    if artifact_type:
        query = query.filter(Artifact.artifact_type == artifact_type)

    return query.order_by(Artifact.created_at).all()


# =============================================================================
# AgentEvent CRUD
# =============================================================================

def _get_next_sequence(session: Session, run_id: str) -> int:
    """Get the next sequence number for events in a run."""
    result = (
        session.query(AgentEvent.sequence)
        .filter(AgentEvent.run_id == run_id)
        .order_by(desc(AgentEvent.sequence))
        .first()
    )
    return (result[0] + 1) if result else 1


def create_event(
    session: Session,
    run_id: str,
    event_type: str,
    *,
    payload: dict[str, Any] | None = None,
    tool_name: str | None = None,
    project_dir: Path | None = None,
) -> AgentEvent:
    """
    Create an audit event.

    Large payloads are truncated and stored as artifacts.

    Args:
        session: SQLAlchemy session
        run_id: Run ID
        event_type: One of EVENT_TYPES
        payload: Event-specific data
        tool_name: Tool name for tool_call/tool_result events
        project_dir: Project directory for large payload storage

    Returns:
        Created AgentEvent instance
    """
    sequence = _get_next_sequence(session, run_id)

    event = AgentEvent(
        run_id=run_id,
        event_type=event_type,
        sequence=sequence,
        tool_name=tool_name,
    )

    # Handle payload size limits
    if payload:
        payload_str = json.dumps(payload)
        if len(payload_str) <= EVENT_PAYLOAD_MAX_SIZE:
            event.payload = payload
        else:
            # Truncate and store full payload as artifact
            event.payload_truncated = len(payload_str)

            # Create summary payload
            summary = {
                "_truncated": True,
                "_original_size": len(payload_str),
            }
            # Include first-level keys with truncated values
            for key, value in payload.items():
                value_str = json.dumps(value)
                if len(value_str) > 200:
                    summary[key] = f"<truncated: {len(value_str)} chars>"
                else:
                    summary[key] = value

            event.payload = summary

            # Store full payload as artifact if project_dir provided
            if project_dir:
                artifact = create_artifact(
                    session,
                    run_id,
                    "log",
                    payload_str,
                    project_dir=project_dir,
                    metadata={"event_sequence": sequence, "event_type": event_type},
                )
                event.artifact_ref = artifact.id

    session.add(event)
    session.flush()
    return event


def get_events(
    session: Session,
    run_id: str,
    *,
    event_type: str | None = None,
    tool_name: str | None = None,
    limit: int | None = None,
    after_sequence: int | None = None,
) -> list[AgentEvent]:
    """
    Get events for a run with optional filters.

    Args:
        session: SQLAlchemy session
        run_id: Run ID
        event_type: Filter by event type
        tool_name: Filter by tool name
        limit: Max results
        after_sequence: Only events after this sequence number

    Returns:
        List of AgentEvent instances ordered by sequence
    """
    query = session.query(AgentEvent).filter(AgentEvent.run_id == run_id)

    if event_type:
        query = query.filter(AgentEvent.event_type == event_type)
    if tool_name:
        query = query.filter(AgentEvent.tool_name == tool_name)
    if after_sequence is not None:
        query = query.filter(AgentEvent.sequence > after_sequence)

    query = query.order_by(AgentEvent.sequence)

    if limit:
        query = query.limit(limit)

    return query.all()


def get_event_count(session: Session, run_id: str) -> int:
    """Get total event count for a run."""
    return session.query(AgentEvent).filter(AgentEvent.run_id == run_id).count()


# =============================================================================
# Convenience Functions
# =============================================================================

def create_spec_with_acceptance(
    session: Session,
    name: str,
    display_name: str,
    objective: str,
    task_type: str,
    allowed_tools: list[str],
    validators: list[dict[str, Any]],
    **spec_kwargs,
) -> tuple[AgentSpec, AcceptanceSpec]:
    """
    Create an AgentSpec with its AcceptanceSpec in one operation.

    Returns:
        Tuple of (AgentSpec, AcceptanceSpec)
    """
    spec = create_agent_spec(
        session,
        name=name,
        display_name=display_name,
        objective=objective,
        task_type=task_type,
        allowed_tools=allowed_tools,
        **spec_kwargs,
    )

    acceptance = create_acceptance_spec(
        session,
        agent_spec_id=spec.id,
        validators=validators,
    )

    return spec, acceptance


def get_run_summary(session: Session, run_id: str) -> dict[str, Any] | None:
    """
    Get a summary of a run including spec info and basic metrics.

    Useful for UI display.
    """
    run = get_agent_run(session, run_id)
    if not run:
        return None

    spec = get_agent_spec(session, run.agent_spec_id)
    event_count = get_event_count(session, run_id)
    artifact_count = len(list_artifacts(session, run_id))

    return {
        "run": run.to_dict(),
        "spec": spec.to_dict() if spec else None,
        "event_count": event_count,
        "artifact_count": artifact_count,
    }
