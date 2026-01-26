"""
Agent Event Broadcaster
=======================

Feature #62: WebSocket agent_event_logged Event

Broadcasts significant agent events via WebSocket for real-time progress tracking.
Implements throttling to prevent overwhelming clients (max 10 events/second per run).

Significant event types that are broadcast:
- tool_call: Agent invoked a tool
- turn_complete: One API round-trip finished
- acceptance_check: Verification gate evaluated

Other event types (started, tool_result, completed, failed, etc.) are NOT broadcast
to reduce noise - these can be retrieved via the events API if needed.
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Event types that should be broadcast via WebSocket
# These are the "significant" events for real-time progress tracking
SIGNIFICANT_EVENT_TYPES = frozenset({
    "tool_call",
    "turn_complete",
    "acceptance_check",
})

# Throttle configuration: max 10 events per second per run
MAX_EVENTS_PER_SECOND = 10
THROTTLE_WINDOW_SECONDS = 1.0


class EventThrottler:
    """
    Throttles events to max N events per second per run.

    Uses a sliding window approach to track events per run_id.
    Thread-safe for use in async context.

    Attributes:
        max_events_per_second: Maximum events allowed per second per run
        window_seconds: Time window for throttling (default 1.0 second)
    """

    def __init__(
        self,
        max_events_per_second: int = MAX_EVENTS_PER_SECOND,
        window_seconds: float = THROTTLE_WINDOW_SECONDS
    ):
        self.max_events_per_second = max_events_per_second
        self.window_seconds = window_seconds
        # run_id -> list of timestamps for events in current window
        self._event_timestamps: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def should_throttle(self, run_id: str) -> bool:
        """
        Check if an event for this run_id should be throttled.

        Args:
            run_id: The ID of the AgentRun

        Returns:
            True if the event should be dropped (throttled), False if it should pass
        """
        async with self._lock:
            now = time.monotonic()
            timestamps = self._event_timestamps[run_id]

            # Remove timestamps outside the window
            cutoff = now - self.window_seconds
            timestamps = [ts for ts in timestamps if ts > cutoff]
            self._event_timestamps[run_id] = timestamps

            # Check if we're at capacity
            if len(timestamps) >= self.max_events_per_second:
                logger.debug(
                    "Throttling event for run %s: %d events in last %ss",
                    run_id, len(timestamps), self.window_seconds
                )
                return True

            # Record this event's timestamp
            timestamps.append(now)
            return False

    async def clear_run(self, run_id: str) -> None:
        """Clear throttle state for a completed/failed run."""
        async with self._lock:
            self._event_timestamps.pop(run_id, None)

    async def reset(self) -> None:
        """Reset all throttle state."""
        async with self._lock:
            self._event_timestamps.clear()


class AgentEventBroadcaster:
    """
    Broadcasts significant agent events via WebSocket.

    This class implements Feature #62: WebSocket agent_event_logged Event.

    It:
    1. Filters events to only broadcast significant types (tool_call, turn_complete, acceptance_check)
    2. Creates agent_event_logged messages with run_id, event_type, sequence, tool_name
    3. Throttles to max 10 events/second per run
    4. Broadcasts to all connected WebSocket clients for the project

    Usage:
        broadcaster = AgentEventBroadcaster(project_name)
        broadcaster.set_broadcast_callback(websocket_broadcast_func)

        # When an event is recorded:
        await broadcaster.broadcast_event(event)
    """

    def __init__(self, project_name: str):
        """
        Initialize the broadcaster.

        Args:
            project_name: The project this broadcaster is associated with
        """
        self.project_name = project_name
        self._broadcast_callback: Optional[Callable] = None
        self._throttler = EventThrottler()
        self._lock = asyncio.Lock()

    def set_broadcast_callback(
        self,
        callback: Callable[[dict[str, Any]], Any]
    ) -> None:
        """
        Set the callback function for broadcasting messages.

        The callback should accept a dict message and broadcast it to
        WebSocket clients. It can be sync or async.

        Args:
            callback: Function to call with message dict for broadcasting
        """
        self._broadcast_callback = callback

    def _is_significant_event(self, event_type: str) -> bool:
        """
        Check if an event type is significant enough to broadcast.

        Only tool_call, turn_complete, and acceptance_check events
        are broadcast to avoid overwhelming clients.

        Args:
            event_type: The event type string

        Returns:
            True if the event should be broadcast
        """
        return event_type in SIGNIFICANT_EVENT_TYPES

    def _create_event_message(
        self,
        run_id: str,
        event_type: str,
        sequence: int,
        tool_name: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Create an agent_event_logged WebSocket message.

        Args:
            run_id: UUID of the AgentRun
            event_type: Type of event (tool_call, turn_complete, etc.)
            sequence: Event sequence number within the run
            tool_name: Name of the tool for tool_call events (optional)
            timestamp: Event timestamp (defaults to now)

        Returns:
            Dict message ready for WebSocket broadcast
        """
        if timestamp is None:
            timestamp = datetime.now()

        message = {
            "type": "agent_event_logged",
            "run_id": run_id,
            "event_type": event_type,
            "sequence": sequence,
            "timestamp": timestamp.isoformat(),
        }

        # Include tool_name only if applicable (for tool_call events)
        if tool_name is not None:
            message["tool_name"] = tool_name

        return message

    async def broadcast_event(
        self,
        run_id: str,
        event_type: str,
        sequence: int,
        tool_name: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        Broadcast an agent event via WebSocket if significant.

        This method:
        1. Checks if the event type is significant
        2. Applies throttling (max 10 events/second per run)
        3. Creates and broadcasts the message if not throttled

        Args:
            run_id: UUID of the AgentRun
            event_type: Type of event
            sequence: Event sequence number
            tool_name: Tool name for tool_call events
            timestamp: Event timestamp

        Returns:
            True if the event was broadcast, False if filtered or throttled
        """
        # Step 1: Filter events to only broadcast significant types
        if not self._is_significant_event(event_type):
            logger.debug(
                "Skipping non-significant event type '%s' for run %s",
                event_type, run_id
            )
            return False

        # Step 5: Throttle to max 10 events/second per run
        if await self._throttler.should_throttle(run_id):
            return False

        # No callback registered - skip broadcasting
        if self._broadcast_callback is None:
            logger.debug(
                "No broadcast callback registered, skipping event for run %s",
                run_id
            )
            return False

        # Steps 3-4: Create message with run_id, event_type, sequence, tool_name
        message = self._create_event_message(
            run_id=run_id,
            event_type=event_type,
            sequence=sequence,
            tool_name=tool_name,
            timestamp=timestamp,
        )

        # Broadcast the message
        try:
            result = self._broadcast_callback(message)
            # Handle both sync and async callbacks
            if asyncio.iscoroutine(result):
                await result

            logger.debug(
                "Broadcast agent_event_logged: run=%s type=%s seq=%d",
                run_id, event_type, sequence
            )
            return True
        except Exception as e:
            logger.warning(
                "Failed to broadcast event for run %s: %s",
                run_id, e
            )
            return False

    async def broadcast_from_event_model(self, event: Any) -> bool:
        """
        Broadcast an event from an AgentEvent model instance.

        Convenience method that extracts fields from the model.

        Args:
            event: AgentEvent model instance with run_id, event_type, sequence, tool_name

        Returns:
            True if broadcast, False if filtered/throttled
        """
        return await self.broadcast_event(
            run_id=event.run_id,
            event_type=event.event_type,
            sequence=event.sequence,
            tool_name=event.tool_name,
            timestamp=event.timestamp,
        )

    async def clear_run(self, run_id: str) -> None:
        """Clear throttle state when a run completes or fails."""
        await self._throttler.clear_run(run_id)

    async def reset(self) -> None:
        """Reset all state (for testing or shutdown)."""
        await self._throttler.reset()


# Global broadcaster instances per project
_broadcasters: dict[str, AgentEventBroadcaster] = {}
_broadcasters_lock = asyncio.Lock()


async def get_event_broadcaster(project_name: str) -> AgentEventBroadcaster:
    """
    Get or create an event broadcaster for a project.

    Args:
        project_name: Name of the project

    Returns:
        AgentEventBroadcaster instance for the project
    """
    async with _broadcasters_lock:
        if project_name not in _broadcasters:
            _broadcasters[project_name] = AgentEventBroadcaster(project_name)
        return _broadcasters[project_name]


async def cleanup_event_broadcasters() -> None:
    """Clean up all broadcaster instances."""
    async with _broadcasters_lock:
        for broadcaster in _broadcasters.values():
            await broadcaster.reset()
        _broadcasters.clear()


# Synchronous wrapper for use in harness kernel
def broadcast_agent_event_sync(
    project_name: str,
    run_id: str,
    event_type: str,
    sequence: int,
    tool_name: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Synchronous wrapper to broadcast an agent event.

    This is intended for use in the harness kernel which may not
    be running in an async context.

    Creates a new event loop if needed to run the broadcast.

    Args:
        project_name: Name of the project
        run_id: UUID of the AgentRun
        event_type: Type of event
        sequence: Event sequence number
        tool_name: Tool name for tool_call events
        timestamp: Event timestamp
    """
    async def _broadcast():
        broadcaster = await get_event_broadcaster(project_name)
        await broadcaster.broadcast_event(
            run_id=run_id,
            event_type=event_type,
            sequence=sequence,
            tool_name=tool_name,
            timestamp=timestamp,
        )

    try:
        # Try to get running loop
        loop = asyncio.get_running_loop()
        # Schedule the coroutine to run in the existing loop
        asyncio.create_task(_broadcast())
    except RuntimeError:
        # No running loop - create one
        asyncio.run(_broadcast())
