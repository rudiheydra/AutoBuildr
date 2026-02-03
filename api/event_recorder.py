"""
Event Recorder Service
======================

Immutable event recording service for agent execution audit trails.

The EventRecorder creates AgentEvent records with:
- Sequential ordering within each run (sequence numbers start at 1)
- Automatic payload size management (4KB limit, larger payloads go to artifacts)
- Immediate commit for durability
- Full traceability of all agent actions

This service is the foundation of the immutable audit trail principle.

Usage:
    from api.event_recorder import EventRecorder, get_event_recorder

    # Option 1: Use global instance (for most cases)
    recorder = get_event_recorder(session, project_dir)
    event_id = recorder.record(run_id, "tool_call", payload={"tool": "bash", "args": "ls"})

    # Option 2: Create local instance
    recorder = EventRecorder(session, project_dir)
    event_id = recorder.record(run_id, "started", payload={"message": "Run started"})
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.agentspec_models import (
    AgentEvent,
    Artifact,
    EVENT_PAYLOAD_MAX_SIZE,
    EVENT_TYPES,
    generate_uuid,
)

# Configure logging
_logger = logging.getLogger(__name__)

# Global instance cache (keyed by session id for proper session handling)
_recorder_cache: dict[int, "EventRecorder"] = {}


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def _compute_hash(content: bytes) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()


class EventRecorder:
    """
    Immutable event recording service for agent runs.

    Creates AgentEvent records with sequential ordering and automatic
    payload size management. Events are committed immediately for durability.

    Attributes:
        session: SQLAlchemy database session
        project_dir: Project directory for artifact storage
        _sequence_cache: In-memory cache of sequence numbers per run
    """

    def __init__(
        self,
        session: Session,
        project_dir: str | Path | None = None,
    ):
        """
        Initialize the EventRecorder.

        Args:
            session: SQLAlchemy session for database operations
            project_dir: Project root directory for storing large payloads
                        as artifacts. If None, large payloads will be
                        truncated without artifact storage.
        """
        self.session = session
        self.project_dir = Path(project_dir) if project_dir else None
        self._sequence_cache: dict[str, int] = {}

        _logger.debug(
            "EventRecorder initialized: project_dir=%s",
            self.project_dir
        )

    def _get_next_sequence(self, run_id: str) -> int:
        """
        Get the next sequence number for events in a run.

        Uses an in-memory cache with database fallback for efficiency.
        Sequence numbers start at 1.

        Args:
            run_id: The run ID to get sequence for

        Returns:
            Next sequence number (1 for first event)
        """
        # Check cache first
        if run_id in self._sequence_cache:
            self._sequence_cache[run_id] += 1
            return self._sequence_cache[run_id]

        # Query database for current max sequence
        from sqlalchemy import desc

        result = (
            self.session.query(AgentEvent.sequence)
            .filter(AgentEvent.run_id == run_id)
            .order_by(desc(AgentEvent.sequence))
            .first()
        )

        next_seq = (result[0] + 1) if result else 1
        self._sequence_cache[run_id] = next_seq
        return next_seq

    def _truncate_payload(
        self,
        payload: dict[str, Any],
        original_size: int,
    ) -> dict[str, Any]:
        """
        Create a truncated summary of a large payload.

        Args:
            payload: Original payload dictionary
            original_size: Original payload size in characters

        Returns:
            Truncated payload with metadata about truncation
        """
        summary = {
            "_truncated": True,
            "_original_size": original_size,
        }

        # Include first-level keys with truncated values
        for key, value in payload.items():
            value_str = json.dumps(value)
            if len(value_str) > 200:
                summary[key] = f"<truncated: {len(value_str)} chars>"
            else:
                summary[key] = value

        return summary

    def _store_large_payload(
        self,
        run_id: str,
        event_type: str,
        sequence: int,
        payload_str: str,
    ) -> Artifact | None:
        """
        Store a large payload as an artifact.

        Args:
            run_id: Run ID
            event_type: Event type for metadata
            sequence: Event sequence for metadata
            payload_str: JSON string of the payload

        Returns:
            Created Artifact or None if project_dir not set
        """
        if not self.project_dir:
            _logger.warning(
                "Large payload for run %s event %d not stored: no project_dir",
                run_id,
                sequence
            )
            return None

        # Create artifact for the full payload
        content_bytes = payload_str.encode("utf-8")
        content_hash = _compute_hash(content_bytes)
        size_bytes = len(content_bytes)

        # Create storage directory
        artifacts_dir = self.project_dir / ".autobuildr" / "artifacts" / run_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        storage_path = artifacts_dir / f"{content_hash}.blob"

        # Write content if not already exists (content-addressable)
        if not storage_path.exists():
            storage_path.write_bytes(content_bytes)
            _logger.debug("Artifact content written to: %s", storage_path)

        # Create artifact record
        artifact = Artifact(
            id=generate_uuid(),
            run_id=run_id,
            artifact_type="log",
            content_hash=content_hash,
            size_bytes=size_bytes,
            content_ref=str(storage_path.relative_to(self.project_dir)),
            artifact_metadata={
                "event_sequence": sequence,
                "event_type": event_type,
                "content_type": "application/json",
            },
        )

        self.session.add(artifact)
        self.session.flush()

        _logger.debug(
            "Artifact created for large payload: id=%s, size=%d",
            artifact.id,
            size_bytes
        )

        return artifact

    def record(
        self,
        run_id: str,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
        tool_name: str | None = None,
    ) -> int:
        """
        Record an immutable agent event.

        This is the main entry point for event recording. It:
        1. Assigns a sequential sequence number (starting at 1)
        2. Checks payload size against EVENT_PAYLOAD_MAX_SIZE (4096 chars)
        3. If payload exceeds limit, creates an Artifact and sets artifact_ref
        4. Truncates the payload and sets payload_truncated to original size
        5. Sets timestamp to current UTC time
        6. Creates AgentEvent record with all fields
        7. Commits immediately for durability
        8. Returns the created event ID

        Args:
            run_id: UUID of the AgentRun this event belongs to
            event_type: Type of event (started, tool_call, tool_result,
                       turn_complete, acceptance_check, completed, failed,
                       paused, resumed)
            payload: Event-specific data as a dictionary. Large payloads
                    (>4096 chars when serialized) will be truncated with
                    full content stored as an artifact.
            tool_name: For tool_call and tool_result events, the tool name.
                      Stored denormalized for query efficiency.

        Returns:
            The database ID of the created event (integer)

        Raises:
            ValueError: If event_type is not a valid event type

        Example:
            >>> recorder = EventRecorder(session, "/path/to/project")
            >>> event_id = recorder.record(
            ...     run_id="abc-123",
            ...     event_type="tool_call",
            ...     payload={"tool": "bash", "args": "ls -la"},
            ...     tool_name="bash"
            ... )
        """
        # Validate event type
        if event_type not in EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type '{event_type}'. "
                f"Must be one of: {', '.join(EVENT_TYPES)}"
            )

        # Get next sequence number (starts at 1)
        sequence = self._get_next_sequence(run_id)

        # Create event with current UTC timestamp
        event = AgentEvent(
            run_id=run_id,
            event_type=event_type,
            sequence=sequence,
            timestamp=_utc_now(),
            tool_name=tool_name,
        )

        # Handle payload
        if payload is not None:
            payload_str = json.dumps(payload)
            payload_size = len(payload_str)

            if payload_size <= EVENT_PAYLOAD_MAX_SIZE:
                # Payload fits within limit
                event.payload = payload
                _logger.debug(
                    "Event %d: payload size %d within limit",
                    sequence,
                    payload_size
                )
            else:
                # Payload exceeds limit - truncate and store as artifact
                _logger.info(
                    "Event %d: payload size %d exceeds limit %d, truncating",
                    sequence,
                    payload_size,
                    EVENT_PAYLOAD_MAX_SIZE
                )

                # Set truncation info
                event.payload_truncated = payload_size

                # Create truncated summary
                event.payload = self._truncate_payload(payload, payload_size)

                # Store full payload as artifact
                artifact = self._store_large_payload(
                    run_id,
                    event_type,
                    sequence,
                    payload_str
                )
                if artifact:
                    event.artifact_ref = artifact.id

        # Add event to session
        self.session.add(event)

        # Commit immediately for durability
        self.session.commit()

        _logger.debug(
            "Event recorded: run=%s, type=%s, seq=%d, id=%d",
            run_id,
            event_type,
            sequence,
            event.id
        )

        return event.id

    def record_started(
        self,
        run_id: str,
        *,
        objective: str | None = None,
        spec_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> int:
        """
        Convenience method to record a 'started' event.

        Args:
            run_id: Run ID
            objective: Objective being executed
            spec_id: AgentSpec ID
            extra: Additional payload data

        Returns:
            Event ID
        """
        payload = {}
        if objective:
            payload["objective"] = objective
        if spec_id:
            payload["spec_id"] = spec_id
        if extra:
            payload.update(extra)

        return self.record(run_id, "started", payload=payload or None)

    def record_tool_call(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> int:
        """
        Convenience method to record a 'tool_call' event.

        Args:
            run_id: Run ID
            tool_name: Name of the tool being called
            arguments: Tool arguments

        Returns:
            Event ID
        """
        payload = {"tool": tool_name}
        if arguments:
            payload["arguments"] = arguments

        return self.record(
            run_id,
            "tool_call",
            payload=payload,
            tool_name=tool_name,
        )

    def record_tool_result(
        self,
        run_id: str,
        tool_name: str,
        result: Any,
        *,
        success: bool = True,
        error: str | None = None,
    ) -> int:
        """
        Convenience method to record a 'tool_result' event.

        Args:
            run_id: Run ID
            tool_name: Name of the tool
            result: Tool result data
            success: Whether the tool call succeeded
            error: Error message if failed

        Returns:
            Event ID
        """
        payload = {
            "tool": tool_name,
            "success": success,
        }
        if result is not None:
            payload["result"] = result
        if error:
            payload["error"] = error

        return self.record(
            run_id,
            "tool_result",
            payload=payload,
            tool_name=tool_name,
        )

    def record_turn_complete(
        self,
        run_id: str,
        turn_number: int,
        *,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
    ) -> int:
        """
        Convenience method to record a 'turn_complete' event.

        Args:
            run_id: Run ID
            turn_number: Completed turn number
            tokens_in: Input tokens used in this turn
            tokens_out: Output tokens used in this turn

        Returns:
            Event ID
        """
        payload = {"turn": turn_number}
        if tokens_in is not None:
            payload["tokens_in"] = tokens_in
        if tokens_out is not None:
            payload["tokens_out"] = tokens_out

        return self.record(run_id, "turn_complete", payload=payload)

    def record_acceptance_check(
        self,
        run_id: str,
        validators: list[dict[str, Any]],
        *,
        verdict: str | None = None,
        gate_mode: str | None = None,
    ) -> int:
        """
        Convenience method to record an 'acceptance_check' event.

        Args:
            run_id: Run ID
            validators: List of validator results
            verdict: Overall verdict (passed, failed, error)
            gate_mode: Gate mode used (all_pass, any_pass, weighted)

        Returns:
            Event ID
        """
        payload = {"validators": validators}
        if verdict:
            payload["verdict"] = verdict
        if gate_mode:
            payload["gate_mode"] = gate_mode

        return self.record(run_id, "acceptance_check", payload=payload)

    def record_completed(
        self,
        run_id: str,
        *,
        verdict: str | None = None,
        turns_used: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
    ) -> int:
        """
        Convenience method to record a 'completed' event.

        Args:
            run_id: Run ID
            verdict: Final verdict
            turns_used: Total turns used
            tokens_in: Total input tokens
            tokens_out: Total output tokens

        Returns:
            Event ID
        """
        payload = {}
        if verdict:
            payload["verdict"] = verdict
        if turns_used is not None:
            payload["turns_used"] = turns_used
        if tokens_in is not None:
            payload["tokens_in"] = tokens_in
        if tokens_out is not None:
            payload["tokens_out"] = tokens_out

        return self.record(run_id, "completed", payload=payload or None)

    def record_failed(
        self,
        run_id: str,
        error: str,
        *,
        error_type: str | None = None,
        traceback: str | None = None,
    ) -> int:
        """
        Convenience method to record a 'failed' event.

        Args:
            run_id: Run ID
            error: Error message
            error_type: Type of error (e.g., "RuntimeError", "TimeoutError")
            traceback: Full traceback string

        Returns:
            Event ID
        """
        payload = {"error": error}
        if error_type:
            payload["error_type"] = error_type
        if traceback:
            payload["traceback"] = traceback

        return self.record(run_id, "failed", payload=payload)

    def record_paused(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        turns_used: int | None = None,
    ) -> int:
        """
        Convenience method to record a 'paused' event.

        Args:
            run_id: Run ID
            reason: Reason for pause
            turns_used: Turns used before pause

        Returns:
            Event ID
        """
        payload = {}
        if reason:
            payload["reason"] = reason
        if turns_used is not None:
            payload["turns_used"] = turns_used

        return self.record(run_id, "paused", payload=payload or None)

    def record_resumed(
        self,
        run_id: str,
        *,
        previous_status: str | None = None,
        turns_used: int | None = None,
    ) -> int:
        """
        Convenience method to record a 'resumed' event.

        Args:
            run_id: Run ID
            previous_status: Status before resume
            turns_used: Turns used before resume

        Returns:
            Event ID
        """
        payload = {}
        if previous_status:
            payload["previous_status"] = previous_status
        if turns_used is not None:
            payload["turns_used"] = turns_used

        return self.record(run_id, "resumed", payload=payload or None)

    def record_agent_planned(
        self,
        run_id: str,
        agent_name: str,
        *,
        display_name: str | None = None,
        task_type: str | None = None,
        capabilities: list[str] | None = None,
        rationale: str | None = None,
    ) -> int:
        """
        Convenience method to record an 'agent_planned' event.

        Feature #176/221: Maestro agent planning audit event.

        Args:
            run_id: Run ID
            agent_name: Name of the planned agent
            display_name: Human-friendly display name
            task_type: Task type (coding, testing, etc.)
            capabilities: List of capabilities the agent provides
            rationale: Explanation for why this agent was planned

        Returns:
            Event ID
        """
        payload = {"agent_name": agent_name}
        if display_name:
            payload["display_name"] = display_name
        if task_type:
            payload["task_type"] = task_type
        if capabilities:
            payload["capabilities"] = capabilities
        if rationale:
            payload["rationale"] = rationale

        return self.record(run_id, "agent_planned", payload=payload)

    def record_octo_failure(
        self,
        run_id: str,
        error: str,
        *,
        error_type: str | None = None,
        required_capabilities: list[str] | None = None,
        fallback_agents: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> int:
        """
        Convenience method to record an 'octo_failure' event.

        Feature #180: Maestro handles Octo failures gracefully.
        Records the failure details and fallback action for audit trail.

        Args:
            run_id: Run ID
            error: Error message describing the failure
            error_type: Type of error (e.g., "connection", "timeout", "validation")
            required_capabilities: Capabilities that were requested from Octo
            fallback_agents: List of agents being used as fallback
            context: Additional context about the failure

        Returns:
            Event ID
        """
        payload = {"error": error}
        if error_type:
            payload["error_type"] = error_type
        if required_capabilities:
            payload["required_capabilities"] = required_capabilities
        if fallback_agents:
            payload["fallback_agents"] = fallback_agents
        if context:
            payload["context"] = context

        return self.record(run_id, "octo_failure", payload=payload)

    def record_agent_materialized(
        self,
        run_id: str,
        agent_name: str,
        file_path: str,
        spec_hash: str,
        *,
        spec_id: str | None = None,
        display_name: str | None = None,
        task_type: str | None = None,
    ) -> int:
        """
        Convenience method to record an 'agent_materialized' event.

        Feature #195: Materializer records agent file creation for audit trail.
        Records details of the materialized agent file including name, path, and content hash.

        Args:
            run_id: Run ID
            agent_name: Name of the agent that was materialized
            file_path: Path to the created agent file
            spec_hash: SHA256 hash of the generated content (for determinism verification)
            spec_id: Optional ID of the AgentSpec that was materialized
            display_name: Optional human-readable display name
            task_type: Optional task type of the agent

        Returns:
            Event ID
        """
        payload = {
            "agent_name": agent_name,
            "file_path": file_path,
            "spec_hash": spec_hash,
        }
        if spec_id:
            payload["spec_id"] = spec_id
        if display_name:
            payload["display_name"] = display_name
        if task_type:
            payload["task_type"] = task_type

        return self.record(run_id, "agent_materialized", payload=payload)

    def clear_sequence_cache(self, run_id: str | None = None) -> None:
        """
        Clear the sequence number cache.

        Useful for testing or when the database may have been modified
        externally.

        Args:
            run_id: Clear cache for specific run only, or all if None
        """
        if run_id:
            self._sequence_cache.pop(run_id, None)
        else:
            self._sequence_cache.clear()


def get_event_recorder(
    session: Session,
    project_dir: str | Path | None = None,
) -> EventRecorder:
    """
    Get or create an EventRecorder instance.

    This function provides a convenient way to get an EventRecorder
    that is cached per session for efficiency.

    Args:
        session: SQLAlchemy session
        project_dir: Project directory for artifact storage

    Returns:
        EventRecorder instance
    """
    session_id = id(session)

    if session_id not in _recorder_cache:
        _recorder_cache[session_id] = EventRecorder(session, project_dir)
    else:
        # Update project_dir if different
        recorder = _recorder_cache[session_id]
        if project_dir:
            recorder.project_dir = Path(project_dir)

    return _recorder_cache[session_id]


def clear_recorder_cache() -> None:
    """
    Clear the global EventRecorder cache.

    Useful for testing or when sessions are being cleaned up.
    """
    _recorder_cache.clear()
