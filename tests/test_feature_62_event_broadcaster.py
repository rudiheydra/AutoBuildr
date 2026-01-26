"""
Feature #62: WebSocket agent_event_logged Event Tests
=====================================================

Comprehensive test suite for the agent event broadcaster feature.

Tests cover:
1. Filter events to only broadcast significant types (tool_call, turn_complete, acceptance_check)
2. Message type: agent_event_logged
3. Payload: run_id, event_type, sequence, tool_name (if applicable)
4. Throttle to max 10 events/second per run
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.event_broadcaster import (
    SIGNIFICANT_EVENT_TYPES,
    MAX_EVENTS_PER_SECOND,
    THROTTLE_WINDOW_SECONDS,
    EventThrottler,
    AgentEventBroadcaster,
    get_event_broadcaster,
    cleanup_event_broadcasters,
    broadcast_agent_event_sync,
)


# =============================================================================
# Step 1: Filter events to only broadcast significant types
# =============================================================================

class TestStep1FilterSignificantEvents:
    """Test that only significant event types are broadcast."""

    def test_significant_event_types_defined(self):
        """Verify the set of significant event types is correctly defined."""
        assert SIGNIFICANT_EVENT_TYPES == frozenset({
            "tool_call",
            "turn_complete",
            "acceptance_check",
        })

    def test_tool_call_is_significant(self):
        """tool_call events should be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("tool_call") is True

    def test_turn_complete_is_significant(self):
        """turn_complete events should be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("turn_complete") is True

    def test_acceptance_check_is_significant(self):
        """acceptance_check events should be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("acceptance_check") is True

    def test_started_is_not_significant(self):
        """started events should NOT be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("started") is False

    def test_tool_result_is_not_significant(self):
        """tool_result events should NOT be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("tool_result") is False

    def test_completed_is_not_significant(self):
        """completed events should NOT be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("completed") is False

    def test_failed_is_not_significant(self):
        """failed events should NOT be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("failed") is False

    def test_paused_is_not_significant(self):
        """paused events should NOT be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("paused") is False

    def test_resumed_is_not_significant(self):
        """resumed events should NOT be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._is_significant_event("resumed") is False

    @pytest.mark.asyncio
    async def test_broadcast_filters_non_significant_events(self):
        """Non-significant events should not be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # Try to broadcast a non-significant event
        result = await broadcaster.broadcast_event(
            run_id="test-run-id",
            event_type="started",
            sequence=1
        )

        assert result is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_allows_significant_events(self):
        """Significant events should be broadcast."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        result = await broadcaster.broadcast_event(
            run_id="test-run-id",
            event_type="tool_call",
            sequence=1,
            tool_name="Read"
        )

        assert result is True
        callback.assert_called_once()


# =============================================================================
# Steps 2-3: Message type and payload format
# =============================================================================

class TestStep2And3MessageFormat:
    """Test message type: agent_event_logged and payload format."""

    def test_message_type_is_agent_event_logged(self):
        """Message type should be 'agent_event_logged'."""
        broadcaster = AgentEventBroadcaster("test-project")
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="tool_call",
            sequence=1
        )
        assert message["type"] == "agent_event_logged"

    def test_payload_contains_run_id(self):
        """Payload should contain run_id."""
        broadcaster = AgentEventBroadcaster("test-project")
        message = broadcaster._create_event_message(
            run_id="abc-123-def",
            event_type="tool_call",
            sequence=1
        )
        assert message["run_id"] == "abc-123-def"

    def test_payload_contains_event_type(self):
        """Payload should contain event_type."""
        broadcaster = AgentEventBroadcaster("test-project")
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="turn_complete",
            sequence=1
        )
        assert message["event_type"] == "turn_complete"

    def test_payload_contains_sequence(self):
        """Payload should contain sequence number."""
        broadcaster = AgentEventBroadcaster("test-project")
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="tool_call",
            sequence=42
        )
        assert message["sequence"] == 42

    def test_payload_contains_timestamp(self):
        """Payload should contain timestamp."""
        broadcaster = AgentEventBroadcaster("test-project")
        test_time = datetime(2026, 1, 27, 12, 30, 45)
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="tool_call",
            sequence=1,
            timestamp=test_time
        )
        assert message["timestamp"] == "2026-01-27T12:30:45"

    def test_payload_contains_tool_name_when_provided(self):
        """Payload should contain tool_name when provided."""
        broadcaster = AgentEventBroadcaster("test-project")
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="tool_call",
            sequence=1,
            tool_name="Read"
        )
        assert message["tool_name"] == "Read"

    def test_payload_omits_tool_name_when_none(self):
        """Payload should NOT contain tool_name when not provided."""
        broadcaster = AgentEventBroadcaster("test-project")
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="turn_complete",
            sequence=1,
            tool_name=None
        )
        assert "tool_name" not in message

    def test_default_timestamp_used_when_none(self):
        """When no timestamp provided, current time is used."""
        broadcaster = AgentEventBroadcaster("test-project")
        before = datetime.now()
        message = broadcaster._create_event_message(
            run_id="test-run-id",
            event_type="tool_call",
            sequence=1
        )
        after = datetime.now()

        msg_time = datetime.fromisoformat(message["timestamp"])
        assert before <= msg_time <= after

    @pytest.mark.asyncio
    async def test_broadcast_sends_correct_payload(self):
        """Verify the full payload structure sent to callback."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        test_time = datetime(2026, 1, 27, 12, 30, 45)
        await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="tool_call",
            sequence=5,
            tool_name="Bash",
            timestamp=test_time
        )

        callback.assert_called_once()
        message = callback.call_args[0][0]

        assert message == {
            "type": "agent_event_logged",
            "run_id": "run-123",
            "event_type": "tool_call",
            "sequence": 5,
            "tool_name": "Bash",
            "timestamp": "2026-01-27T12:30:45"
        }


# =============================================================================
# Step 4: tool_name included if applicable
# =============================================================================

class TestStep4ToolNameIfApplicable:
    """Test that tool_name is included only when applicable."""

    @pytest.mark.asyncio
    async def test_tool_call_includes_tool_name(self):
        """tool_call events should include tool_name."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="tool_call",
            sequence=1,
            tool_name="Glob"
        )

        message = callback.call_args[0][0]
        assert "tool_name" in message
        assert message["tool_name"] == "Glob"

    @pytest.mark.asyncio
    async def test_turn_complete_without_tool_name(self):
        """turn_complete events typically don't have tool_name."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="turn_complete",
            sequence=1
        )

        message = callback.call_args[0][0]
        assert "tool_name" not in message

    @pytest.mark.asyncio
    async def test_acceptance_check_without_tool_name(self):
        """acceptance_check events don't have tool_name."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="acceptance_check",
            sequence=1
        )

        message = callback.call_args[0][0]
        assert "tool_name" not in message


# =============================================================================
# Step 5: Throttle to max 10 events/second per run
# =============================================================================

class TestStep5Throttling:
    """Test throttling to max 10 events/second per run."""

    def test_throttle_constants_defined(self):
        """Verify throttle configuration constants."""
        assert MAX_EVENTS_PER_SECOND == 10
        assert THROTTLE_WINDOW_SECONDS == 1.0

    @pytest.mark.asyncio
    async def test_first_event_not_throttled(self):
        """First event for a run should not be throttled."""
        throttler = EventThrottler()
        result = await throttler.should_throttle("run-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_10_events_allowed_per_second(self):
        """Should allow up to 10 events per second."""
        throttler = EventThrottler(max_events_per_second=10)

        for i in range(10):
            result = await throttler.should_throttle("run-123")
            assert result is False, f"Event {i+1} should not be throttled"

    @pytest.mark.asyncio
    async def test_11th_event_throttled(self):
        """11th event in same second should be throttled."""
        throttler = EventThrottler(max_events_per_second=10)

        # Fire 10 events (all should pass)
        for _ in range(10):
            await throttler.should_throttle("run-123")

        # 11th event should be throttled
        result = await throttler.should_throttle("run-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_different_runs_throttled_independently(self):
        """Each run_id has its own throttle counter."""
        throttler = EventThrottler(max_events_per_second=2)

        # Fire 2 events for run-1 (limit reached)
        await throttler.should_throttle("run-1")
        await throttler.should_throttle("run-1")

        # 3rd event for run-1 should be throttled
        result = await throttler.should_throttle("run-1")
        assert result is True

        # But run-2 should still be allowed
        result = await throttler.should_throttle("run-2")
        assert result is False

    @pytest.mark.asyncio
    async def test_throttle_resets_after_window(self):
        """Throttle should reset after the time window passes."""
        throttler = EventThrottler(max_events_per_second=2, window_seconds=0.1)

        # Fire 2 events (limit reached)
        await throttler.should_throttle("run-123")
        await throttler.should_throttle("run-123")

        # 3rd event should be throttled
        result = await throttler.should_throttle("run-123")
        assert result is True

        # Wait for window to pass
        await asyncio.sleep(0.15)

        # Now should be allowed again
        result = await throttler.should_throttle("run-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_run_removes_throttle_state(self):
        """Clearing a run should remove its throttle state."""
        throttler = EventThrottler(max_events_per_second=2)

        # Hit the limit
        await throttler.should_throttle("run-123")
        await throttler.should_throttle("run-123")
        result = await throttler.should_throttle("run-123")
        assert result is True

        # Clear the run
        await throttler.clear_run("run-123")

        # Should be able to send again immediately
        result = await throttler.should_throttle("run-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_reset_clears_all_state(self):
        """Reset should clear all throttle state."""
        throttler = EventThrottler(max_events_per_second=1)

        # Hit limits for multiple runs
        await throttler.should_throttle("run-1")
        await throttler.should_throttle("run-2")

        # Reset
        await throttler.reset()

        # Both should be allowed again
        result1 = await throttler.should_throttle("run-1")
        result2 = await throttler.should_throttle("run-2")
        assert result1 is False
        assert result2 is False


class TestThrottlingIntegration:
    """Test throttling integration with broadcaster."""

    @pytest.mark.asyncio
    async def test_broadcaster_respects_throttle(self):
        """Broadcaster should respect throttle limits."""
        broadcaster = AgentEventBroadcaster("test-project")
        # Override throttler with a low limit for testing
        broadcaster._throttler = EventThrottler(max_events_per_second=2)

        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # First 2 events should pass
        result1 = await broadcaster.broadcast_event("run-1", "tool_call", 1, "Read")
        result2 = await broadcaster.broadcast_event("run-1", "tool_call", 2, "Write")
        assert result1 is True
        assert result2 is True
        assert callback.call_count == 2

        # 3rd event should be throttled
        result3 = await broadcaster.broadcast_event("run-1", "tool_call", 3, "Bash")
        assert result3 is False
        assert callback.call_count == 2  # Still 2

    @pytest.mark.asyncio
    async def test_clear_run_on_completion(self):
        """Broadcaster clear_run should reset throttle for that run."""
        broadcaster = AgentEventBroadcaster("test-project")
        broadcaster._throttler = EventThrottler(max_events_per_second=1)
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # Hit the limit
        await broadcaster.broadcast_event("run-1", "tool_call", 1, "Read")
        result = await broadcaster.broadcast_event("run-1", "tool_call", 2, "Write")
        assert result is False

        # Clear the run (simulating completion)
        await broadcaster.clear_run("run-1")

        # Should be able to broadcast again
        result = await broadcaster.broadcast_event("run-1", "tool_call", 3, "Bash")
        assert result is True


# =============================================================================
# AgentEventBroadcaster class tests
# =============================================================================

class TestAgentEventBroadcaster:
    """Test AgentEventBroadcaster class."""

    def test_init_stores_project_name(self):
        """Broadcaster should store project name."""
        broadcaster = AgentEventBroadcaster("my-project")
        assert broadcaster.project_name == "my-project"

    def test_callback_not_set_by_default(self):
        """Broadcast callback should be None by default."""
        broadcaster = AgentEventBroadcaster("test-project")
        assert broadcaster._broadcast_callback is None

    def test_set_broadcast_callback(self):
        """Should be able to set broadcast callback."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = MagicMock()
        broadcaster.set_broadcast_callback(callback)
        assert broadcaster._broadcast_callback == callback

    @pytest.mark.asyncio
    async def test_no_broadcast_without_callback(self):
        """Should return False when no callback is set."""
        broadcaster = AgentEventBroadcaster("test-project")

        result = await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="tool_call",
            sequence=1,
            tool_name="Read"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_sync_callback(self):
        """Should handle synchronous callbacks."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = MagicMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="tool_call",
            sequence=1,
            tool_name="Read"
        )

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_async_callback(self):
        """Should handle async callbacks."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="tool_call",
            sequence=1,
            tool_name="Read"
        )

        callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_callback_exception(self):
        """Should handle exceptions from callback gracefully."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock(side_effect=Exception("Connection closed"))
        broadcaster.set_broadcast_callback(callback)

        # Should not raise, just return False
        result = await broadcaster.broadcast_event(
            run_id="run-123",
            event_type="tool_call",
            sequence=1,
            tool_name="Read"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_from_event_model(self):
        """Test broadcasting from an AgentEvent model."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # Create a mock event model
        event = MagicMock()
        event.run_id = "run-123"
        event.event_type = "tool_call"
        event.sequence = 5
        event.tool_name = "Grep"
        event.timestamp = datetime(2026, 1, 27, 10, 0, 0)

        result = await broadcaster.broadcast_from_event_model(event)

        assert result is True
        message = callback.call_args[0][0]
        assert message["run_id"] == "run-123"
        assert message["event_type"] == "tool_call"
        assert message["sequence"] == 5
        assert message["tool_name"] == "Grep"


# =============================================================================
# Global broadcaster management tests
# =============================================================================

class TestGlobalBroadcasterManagement:
    """Test global broadcaster instance management."""

    @pytest.mark.asyncio
    async def test_get_event_broadcaster_creates_new(self):
        """get_event_broadcaster should create new instance for new project."""
        await cleanup_event_broadcasters()

        broadcaster = await get_event_broadcaster("project-1")
        assert broadcaster is not None
        assert broadcaster.project_name == "project-1"

    @pytest.mark.asyncio
    async def test_get_event_broadcaster_returns_same(self):
        """get_event_broadcaster should return same instance for same project."""
        await cleanup_event_broadcasters()

        broadcaster1 = await get_event_broadcaster("project-1")
        broadcaster2 = await get_event_broadcaster("project-1")
        assert broadcaster1 is broadcaster2

    @pytest.mark.asyncio
    async def test_get_event_broadcaster_different_projects(self):
        """Different projects should get different broadcasters."""
        await cleanup_event_broadcasters()

        broadcaster1 = await get_event_broadcaster("project-1")
        broadcaster2 = await get_event_broadcaster("project-2")
        assert broadcaster1 is not broadcaster2

    @pytest.mark.asyncio
    async def test_cleanup_event_broadcasters(self):
        """cleanup_event_broadcasters should clear all instances."""
        await cleanup_event_broadcasters()

        # Create some broadcasters
        b1 = await get_event_broadcaster("project-1")
        b2 = await get_event_broadcaster("project-2")

        # Cleanup
        await cleanup_event_broadcasters()

        # New calls should return new instances
        b1_new = await get_event_broadcaster("project-1")
        assert b1 is not b1_new


# =============================================================================
# Feature verification steps integration test
# =============================================================================

class TestFeature62VerificationSteps:
    """Verify all feature steps from the feature definition."""

    @pytest.mark.asyncio
    async def test_step1_filter_events_to_significant_types(self):
        """Step 1: Filter events to only broadcast significant types."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # Significant events should broadcast
        for event_type in ["tool_call", "turn_complete", "acceptance_check"]:
            callback.reset_mock()
            result = await broadcaster.broadcast_event("run-1", event_type, 1)
            assert result is True, f"{event_type} should be broadcast"

        # Non-significant events should not broadcast
        for event_type in ["started", "tool_result", "completed", "failed", "paused", "resumed"]:
            callback.reset_mock()
            result = await broadcaster.broadcast_event("run-1", event_type, 1)
            assert result is False, f"{event_type} should NOT be broadcast"

    @pytest.mark.asyncio
    async def test_step2_message_type_agent_event_logged(self):
        """Step 2: Message type: agent_event_logged."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event("run-1", "tool_call", 1, "Read")

        message = callback.call_args[0][0]
        assert message["type"] == "agent_event_logged"

    @pytest.mark.asyncio
    async def test_step3_payload_run_id_event_type_sequence(self):
        """Step 3: Payload: run_id, event_type, sequence."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        await broadcaster.broadcast_event(
            run_id="run-abc-123",
            event_type="turn_complete",
            sequence=42
        )

        message = callback.call_args[0][0]
        assert message["run_id"] == "run-abc-123"
        assert message["event_type"] == "turn_complete"
        assert message["sequence"] == 42

    @pytest.mark.asyncio
    async def test_step4_tool_name_if_applicable(self):
        """Step 4: Payload includes tool_name (if applicable)."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # With tool_name
        await broadcaster.broadcast_event("run-1", "tool_call", 1, tool_name="Bash")
        message = callback.call_args[0][0]
        assert message["tool_name"] == "Bash"

        # Without tool_name
        callback.reset_mock()
        await broadcaster.broadcast_event("run-1", "turn_complete", 2)
        message = callback.call_args[0][0]
        assert "tool_name" not in message

    @pytest.mark.asyncio
    async def test_step5_throttle_max_10_per_second(self):
        """Step 5: Throttle to max 10 events/second per run."""
        broadcaster = AgentEventBroadcaster("test-project")
        callback = AsyncMock()
        broadcaster.set_broadcast_callback(callback)

        # Send 10 events (all should succeed)
        for i in range(10):
            result = await broadcaster.broadcast_event(
                run_id="run-1",
                event_type="tool_call",
                sequence=i + 1,
                tool_name=f"Tool{i}"
            )
            assert result is True, f"Event {i+1} should not be throttled"

        assert callback.call_count == 10

        # 11th event should be throttled
        result = await broadcaster.broadcast_event(
            run_id="run-1",
            event_type="tool_call",
            sequence=11,
            tool_name="Tool11"
        )
        assert result is False  # Throttled
        assert callback.call_count == 10  # Still 10
