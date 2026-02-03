"""
Event Replay and Debugging Utilities
=====================================

Feature #227: Audit events support replay and debugging.

This module provides utilities for reconstructing and debugging agent runs
from their event audit trail. It enables:

- Reconstructing complete event sequences for a run
- Retrieving full payload content from artifacts for truncated events
- Building debugging context for failed runs
- Supporting replay of agent decisions through event analysis

The audit trail is designed to be immutable and complete, enabling full
reproducibility of agent executions.

Usage:
    from api.event_replay import EventReplayContext, get_replay_context

    # Get replay context for a run
    context = get_replay_context(session, project_dir, run_id)

    # Access reconstructed events with full payloads
    for event in context.get_events():
        print(f"{event.sequence}: {event.event_type}")
        if event.full_payload:
            print(f"  Full payload: {event.full_payload}")

    # Get debugging context for failures
    if context.run.status == "failed":
        debug_info = context.get_debug_context()
        print(f"Failure reason: {debug_info.failure_reason}")
        print(f"Last tool call: {debug_info.last_tool_call}")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal

from sqlalchemy.orm import Session

from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
    Artifact,
)

# Configure logging
_logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes for Replay Context
# =============================================================================

@dataclass
class ReplayableEvent:
    """
    An event enriched with full payload for replay purposes.

    When an event's payload was truncated and stored as an artifact,
    this class provides access to both the truncated summary and
    the full original payload.

    Attributes:
        id: Event database ID
        run_id: Parent run UUID
        sequence: Event sequence within the run
        event_type: Type of event (started, tool_call, etc.)
        timestamp: When the event occurred (UTC)
        payload: Truncated or full payload (as stored in event)
        full_payload: Complete payload (from artifact if truncated)
        was_truncated: True if payload was truncated
        artifact_ref: UUID of artifact containing full payload (if any)
        tool_name: Tool name for tool_call/tool_result events
    """
    id: int
    run_id: str
    sequence: int
    event_type: str
    timestamp: datetime
    payload: dict[str, Any] | None
    full_payload: dict[str, Any] | None
    was_truncated: bool
    artifact_ref: str | None
    tool_name: str | None

    @classmethod
    def from_event(
        cls,
        event: AgentEvent,
        full_payload: dict[str, Any] | None = None,
    ) -> "ReplayableEvent":
        """
        Create a ReplayableEvent from an AgentEvent.

        Args:
            event: The AgentEvent database record
            full_payload: Optional full payload from artifact

        Returns:
            ReplayableEvent with replay context
        """
        was_truncated = event.payload_truncated is not None

        return cls(
            id=event.id,
            run_id=event.run_id,
            sequence=event.sequence,
            event_type=event.event_type,
            timestamp=event.timestamp,
            payload=event.payload,
            full_payload=full_payload if full_payload else event.payload,
            was_truncated=was_truncated,
            artifact_ref=event.artifact_ref,
            tool_name=event.tool_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "payload": self.payload,
            "full_payload": self.full_payload,
            "was_truncated": self.was_truncated,
            "artifact_ref": self.artifact_ref,
            "tool_name": self.tool_name,
        }


@dataclass
class DebugContext:
    """
    Debugging context for a failed or error agent run.

    Provides structured information for understanding what went wrong
    during an agent execution.

    Attributes:
        run_id: The run UUID
        run_status: Final status (failed, timeout, error)
        failure_reason: Human-readable failure explanation
        error_message: Raw error message from run
        last_event: The final event before failure
        last_tool_call: Last tool call event (if any)
        last_tool_result: Last tool result event (if any)
        turns_used: Number of turns consumed
        tokens_used: Total tokens (in + out)
        event_count: Total number of events
        acceptance_results: Acceptance check results (if any)
        failure_context: Additional context from failure event
    """
    run_id: str
    run_status: str
    failure_reason: str
    error_message: str | None
    last_event: ReplayableEvent | None
    last_tool_call: ReplayableEvent | None
    last_tool_result: ReplayableEvent | None
    turns_used: int
    tokens_used: int
    event_count: int
    acceptance_results: list[dict[str, Any]] | None
    failure_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "run_status": self.run_status,
            "failure_reason": self.failure_reason,
            "error_message": self.error_message,
            "last_event": self.last_event.to_dict() if self.last_event else None,
            "last_tool_call": self.last_tool_call.to_dict() if self.last_tool_call else None,
            "last_tool_result": self.last_tool_result.to_dict() if self.last_tool_result else None,
            "turns_used": self.turns_used,
            "tokens_used": self.tokens_used,
            "event_count": self.event_count,
            "acceptance_results": self.acceptance_results,
            "failure_context": self.failure_context,
        }


@dataclass
class EventTimeline:
    """
    Complete reconstructed timeline of events for a run.

    Provides access to events with full payloads and statistics
    for replay and debugging purposes.

    Attributes:
        run_id: The run UUID
        events: List of replayable events in sequence order
        total_events: Total count of events
        start_time: Timestamp of first event
        end_time: Timestamp of last event
        duration_seconds: Total duration from start to end
        tool_call_count: Number of tool_call events
        turn_count: Number of turn_complete events
        has_failure: True if run failed or timed out
    """
    run_id: str
    events: list[ReplayableEvent]
    total_events: int
    start_time: datetime | None
    end_time: datetime | None
    duration_seconds: float | None
    tool_call_count: int
    turn_count: int
    has_failure: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "events": [e.to_dict() for e in self.events],
            "total_events": self.total_events,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "tool_call_count": self.tool_call_count,
            "turn_count": self.turn_count,
            "has_failure": self.has_failure,
        }


# =============================================================================
# Event Replay Context
# =============================================================================

class EventReplayContext:
    """
    Context for replaying and debugging an agent run from its event trail.

    This class provides methods for:
    - Reconstructing the complete event sequence
    - Retrieving full payloads from artifacts
    - Building debugging context for failures
    - Iterating through events with full context

    The replay context is designed to support:
    1. Understanding what happened during a run
    2. Debugging failures and errors
    3. Replaying agent decisions for analysis
    4. Auditing agent behavior

    Usage:
        context = EventReplayContext(session, project_dir, run_id)

        # Check if run exists
        if context.run is None:
            print("Run not found")
            return

        # Get timeline
        timeline = context.get_timeline()
        print(f"Run had {timeline.tool_call_count} tool calls")

        # If failed, get debug info
        if context.run.status == "failed":
            debug = context.get_debug_context()
            print(f"Failed: {debug.failure_reason}")
    """

    def __init__(
        self,
        session: Session,
        project_dir: str | Path | None,
        run_id: str,
    ):
        """
        Initialize the replay context.

        Args:
            session: SQLAlchemy database session
            project_dir: Project directory for artifact retrieval
            run_id: UUID of the AgentRun to replay
        """
        self.session = session
        self.project_dir = Path(project_dir) if project_dir else None
        self.run_id = run_id

        # Load run and spec
        self._run: AgentRun | None = None
        self._spec: AgentSpec | None = None
        self._events: list[AgentEvent] | None = None
        self._load_run()

    def _load_run(self) -> None:
        """Load the AgentRun and its spec."""
        self._run = (
            self.session.query(AgentRun)
            .filter(AgentRun.id == self.run_id)
            .first()
        )

        if self._run:
            self._spec = (
                self.session.query(AgentSpec)
                .filter(AgentSpec.id == self._run.agent_spec_id)
                .first()
            )

    @property
    def run(self) -> AgentRun | None:
        """Get the AgentRun record."""
        return self._run

    @property
    def spec(self) -> AgentSpec | None:
        """Get the AgentSpec record."""
        return self._spec

    def _load_events(self) -> list[AgentEvent]:
        """Load all events for the run in sequence order."""
        if self._events is None:
            self._events = (
                self.session.query(AgentEvent)
                .filter(AgentEvent.run_id == self.run_id)
                .order_by(AgentEvent.sequence)
                .all()
            )
        return self._events

    def _get_artifact_content(self, artifact_id: str) -> dict[str, Any] | None:
        """
        Retrieve full content from an artifact.

        Args:
            artifact_id: UUID of the artifact

        Returns:
            Parsed JSON content or None if not available
        """
        artifact = (
            self.session.query(Artifact)
            .filter(Artifact.id == artifact_id)
            .first()
        )

        if not artifact:
            _logger.warning("Artifact %s not found", artifact_id)
            return None

        # Try inline content first
        if artifact.content_inline:
            try:
                return json.loads(artifact.content_inline)
            except json.JSONDecodeError:
                _logger.warning("Failed to parse inline content for artifact %s", artifact_id)
                return None

        # Try file-based content
        if artifact.content_ref and self.project_dir:
            content_path = self.project_dir / artifact.content_ref
            if content_path.exists():
                try:
                    return json.loads(content_path.read_text())
                except json.JSONDecodeError:
                    _logger.warning("Failed to parse file content for artifact %s", artifact_id)
                    return None

        return None

    def _enrich_event(self, event: AgentEvent) -> ReplayableEvent:
        """
        Enrich an event with full payload from artifact if needed.

        Args:
            event: The AgentEvent to enrich

        Returns:
            ReplayableEvent with full payload
        """
        full_payload = None

        if event.payload_truncated and event.artifact_ref:
            full_payload = self._get_artifact_content(event.artifact_ref)

        return ReplayableEvent.from_event(event, full_payload)

    def get_events(
        self,
        *,
        event_type: str | None = None,
        include_full_payload: bool = True,
    ) -> Iterator[ReplayableEvent]:
        """
        Iterate through events with optional filtering.

        Args:
            event_type: Filter to specific event type (e.g., "tool_call")
            include_full_payload: If True, retrieve full payloads from artifacts

        Yields:
            ReplayableEvent for each matching event
        """
        events = self._load_events()

        for event in events:
            if event_type and event.event_type != event_type:
                continue

            if include_full_payload:
                yield self._enrich_event(event)
            else:
                yield ReplayableEvent.from_event(event)

    def get_event_by_sequence(
        self,
        sequence: int,
        *,
        include_full_payload: bool = True,
    ) -> ReplayableEvent | None:
        """
        Get a specific event by its sequence number.

        Args:
            sequence: The sequence number (starts at 1)
            include_full_payload: If True, retrieve full payload from artifact

        Returns:
            ReplayableEvent or None if not found
        """
        event = (
            self.session.query(AgentEvent)
            .filter(AgentEvent.run_id == self.run_id)
            .filter(AgentEvent.sequence == sequence)
            .first()
        )

        if not event:
            return None

        if include_full_payload:
            return self._enrich_event(event)
        return ReplayableEvent.from_event(event)

    def get_timeline(self) -> EventTimeline:
        """
        Get the complete event timeline for the run.

        Returns:
            EventTimeline with all events and statistics
        """
        events = list(self.get_events(include_full_payload=True))

        tool_call_count = sum(1 for e in events if e.event_type == "tool_call")
        turn_count = sum(1 for e in events if e.event_type == "turn_complete")

        has_failure = any(
            e.event_type in ("failed", "timeout")
            for e in events
        )

        start_time = events[0].timestamp if events else None
        end_time = events[-1].timestamp if events else None

        duration_seconds = None
        if start_time and end_time:
            duration_seconds = (end_time - start_time).total_seconds()

        return EventTimeline(
            run_id=self.run_id,
            events=events,
            total_events=len(events),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_seconds,
            tool_call_count=tool_call_count,
            turn_count=turn_count,
            has_failure=has_failure,
        )

    def get_debug_context(self) -> DebugContext | None:
        """
        Get debugging context for a failed or error run.

        Returns:
            DebugContext with failure information, or None if run didn't fail
        """
        if not self._run:
            return None

        if self._run.status not in ("failed", "timeout", "error"):
            return None

        events = list(self.get_events(include_full_payload=True))

        # Find last event, last tool call, last tool result
        last_event = events[-1] if events else None
        last_tool_call = None
        last_tool_result = None

        for event in reversed(events):
            if event.event_type == "tool_call" and not last_tool_call:
                last_tool_call = event
            elif event.event_type == "tool_result" and not last_tool_result:
                last_tool_result = event
            if last_tool_call and last_tool_result:
                break

        # Build failure reason
        failure_reason = self._build_failure_reason(last_event, last_tool_result)

        # Extract failure context from failed/timeout event
        failure_context = {}
        for event in reversed(events):
            if event.event_type in ("failed", "timeout"):
                failure_context = event.full_payload or {}
                break

        return DebugContext(
            run_id=self.run_id,
            run_status=self._run.status,
            failure_reason=failure_reason,
            error_message=self._run.error,
            last_event=last_event,
            last_tool_call=last_tool_call,
            last_tool_result=last_tool_result,
            turns_used=self._run.turns_used,
            tokens_used=self._run.tokens_in + self._run.tokens_out,
            event_count=len(events),
            acceptance_results=self._run.acceptance_results,
            failure_context=failure_context,
        )

    def _build_failure_reason(
        self,
        last_event: ReplayableEvent | None,
        last_tool_result: ReplayableEvent | None,
    ) -> str:
        """Build a human-readable failure reason."""
        if not self._run:
            return "Unknown failure"

        if self._run.status == "timeout":
            return f"Execution timed out after {self._run.turns_used} turns"

        if self._run.error:
            if self._run.error == "user_cancelled":
                return "Run was cancelled by user"
            return f"Run failed with error: {self._run.error}"

        if last_tool_result and last_tool_result.full_payload:
            payload = last_tool_result.full_payload
            if not payload.get("success", True):
                tool = payload.get("tool", "unknown")
                error = payload.get("error", "unknown error")
                return f"Tool '{tool}' failed: {error}"

        if last_event:
            return f"Run ended with event: {last_event.event_type}"

        return "Run failed for unknown reason"

    def reconstruct_event_sequence(self) -> list[dict[str, Any]]:
        """
        Reconstruct the complete event sequence for replay.

        Returns a list of events with full context needed to understand
        and potentially replay the agent's decisions.

        Returns:
            List of event dictionaries with full replay context
        """
        result = []

        for event in self.get_events(include_full_payload=True):
            entry = {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "tool_name": event.tool_name,
                "payload": event.full_payload,  # Always use full payload for replay
                "was_truncated": event.was_truncated,
            }
            result.append(entry)

        return result


# =============================================================================
# Factory Functions
# =============================================================================

def get_replay_context(
    session: Session,
    project_dir: str | Path | None,
    run_id: str,
) -> EventReplayContext:
    """
    Get an EventReplayContext for a run.

    Args:
        session: SQLAlchemy database session
        project_dir: Project directory for artifact retrieval
        run_id: UUID of the AgentRun

    Returns:
        EventReplayContext for the run
    """
    return EventReplayContext(session, project_dir, run_id)


def reconstruct_run_events(
    session: Session,
    project_dir: str | Path | None,
    run_id: str,
) -> list[dict[str, Any]]:
    """
    Convenience function to reconstruct events for a run.

    Args:
        session: SQLAlchemy database session
        project_dir: Project directory for artifact retrieval
        run_id: UUID of the AgentRun

    Returns:
        List of event dictionaries with full replay context
    """
    context = get_replay_context(session, project_dir, run_id)
    return context.reconstruct_event_sequence()


def get_run_debug_context(
    session: Session,
    project_dir: str | Path | None,
    run_id: str,
) -> DebugContext | None:
    """
    Convenience function to get debug context for a failed run.

    Args:
        session: SQLAlchemy database session
        project_dir: Project directory for artifact retrieval
        run_id: UUID of the AgentRun

    Returns:
        DebugContext or None if run didn't fail
    """
    context = get_replay_context(session, project_dir, run_id)
    return context.get_debug_context()


def verify_event_sequence_integrity(
    session: Session,
    run_id: str,
) -> dict[str, Any]:
    """
    Verify the integrity of an event sequence.

    Checks that:
    - Events have sequential sequence numbers starting at 1
    - Events are properly ordered by timestamp
    - No sequence gaps exist

    Args:
        session: SQLAlchemy database session
        run_id: UUID of the AgentRun

    Returns:
        Dict with verification results:
        - is_valid: True if sequence is intact
        - total_events: Number of events
        - sequence_start: First sequence number
        - sequence_end: Last sequence number
        - gaps: List of missing sequence numbers
        - errors: List of error messages
    """
    events = (
        session.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id)
        .order_by(AgentEvent.sequence)
        .all()
    )

    if not events:
        return {
            "is_valid": True,
            "total_events": 0,
            "sequence_start": None,
            "sequence_end": None,
            "gaps": [],
            "errors": [],
        }

    errors = []
    gaps = []

    # Check sequence starts at 1
    if events[0].sequence != 1:
        errors.append(f"Sequence should start at 1, but starts at {events[0].sequence}")

    # Check for gaps
    expected_seq = 1
    for event in events:
        if event.sequence != expected_seq:
            # Found a gap
            for missing in range(expected_seq, event.sequence):
                gaps.append(missing)
            expected_seq = event.sequence + 1
        else:
            expected_seq += 1

    # Check timestamps are ordered
    prev_timestamp = None
    for event in events:
        if prev_timestamp and event.timestamp < prev_timestamp:
            errors.append(
                f"Event {event.sequence} timestamp ({event.timestamp}) "
                f"is before event {event.sequence - 1} timestamp ({prev_timestamp})"
            )
        prev_timestamp = event.timestamp

    return {
        "is_valid": len(errors) == 0 and len(gaps) == 0,
        "total_events": len(events),
        "sequence_start": events[0].sequence,
        "sequence_end": events[-1].sequence,
        "gaps": gaps,
        "errors": errors,
    }
