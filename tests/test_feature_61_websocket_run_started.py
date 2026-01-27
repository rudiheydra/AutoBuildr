"""
Feature #61: WebSocket agent_run_started Event
==============================================

Tests for broadcasting WebSocket message when AgentRun begins for real-time UI updates.

Feature Steps:
1. When AgentRun status changes to running, publish message
2. Message type: agent_run_started
3. Payload: run_id, spec_id, display_name, icon, started_at
4. Broadcast to all connected clients
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from api.websocket_events import (
    RunStartedPayload,
    broadcast_run_started,
    broadcast_run_started_sync,
)


# =============================================================================
# Test RunStartedPayload Data Class
# =============================================================================

class TestRunStartedPayload:
    """Test the RunStartedPayload data class."""

    def test_payload_creation(self):
        """Test basic payload creation with all fields."""
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
            icon="🔧",
            started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )

        assert payload.run_id == "run-123"
        assert payload.spec_id == "spec-456"
        assert payload.display_name == "Test Feature"
        assert payload.icon == "🔧"
        assert payload.started_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert payload.timestamp is not None  # Auto-set

    def test_payload_with_optional_fields(self):
        """Test payload with optional fields omitted."""
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
        )

        assert payload.run_id == "run-123"
        assert payload.spec_id == "spec-456"
        assert payload.display_name == "Test Feature"
        assert payload.icon is None  # Default
        assert payload.started_at is None  # Default
        assert payload.timestamp is not None  # Auto-set in __post_init__

    def test_to_message_format(self):
        """Step 2: Message type should be 'agent_run_started'."""
        started_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Implement Auth",
            icon="🔐",
            started_at=started_at,
        )

        message = payload.to_message()

        # Step 2: Message type: agent_run_started
        assert message["type"] == "agent_run_started"

        # Step 3: Payload: run_id, spec_id, display_name, icon, started_at
        assert message["run_id"] == "run-123"
        assert message["spec_id"] == "spec-456"
        assert message["display_name"] == "Implement Auth"
        assert message["icon"] == "🔐"
        assert message["started_at"] == started_at.isoformat()
        assert message["timestamp"] is not None

    def test_to_message_with_null_icon(self):
        """Test message format when icon is None."""
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
            icon=None,
        )

        message = payload.to_message()

        assert message["icon"] is None

    def test_to_message_with_null_started_at(self):
        """Test message format when started_at is None."""
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
            started_at=None,
        )

        message = payload.to_message()

        assert message["started_at"] is None

    def test_timestamp_auto_set(self):
        """Test that timestamp is automatically set on creation."""
        before = datetime.now(timezone.utc)
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
        )
        after = datetime.now(timezone.utc)

        assert before <= payload.timestamp <= after


# =============================================================================
# Test broadcast_run_started Function
# =============================================================================

class TestBroadcastRunStarted:
    """Test the broadcast_run_started async function."""

    @pytest.mark.asyncio
    async def test_broadcast_with_manager_unavailable(self):
        """Test broadcast returns False when WebSocket manager is unavailable."""
        with patch("api.websocket_events._get_connection_manager", return_value=None):
            result = await broadcast_run_started(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_with_manager_available(self):
        """Step 4: Broadcast to all connected clients."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_run_started(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
                icon="🔧",
            )

        assert result is True
        mock_manager.broadcast_to_project.assert_called_once()

        # Verify the message content
        call_args = mock_manager.broadcast_to_project.call_args
        project_name, message = call_args[0]

        assert project_name == "test-project"
        assert message["type"] == "agent_run_started"
        assert message["run_id"] == "run-123"
        assert message["spec_id"] == "spec-456"
        assert message["display_name"] == "Test Feature"
        assert message["icon"] == "🔧"

    @pytest.mark.asyncio
    async def test_broadcast_sets_default_started_at(self):
        """Test that started_at defaults to now if not provided."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        before = datetime.now(timezone.utc)

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_run_started(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        after = datetime.now(timezone.utc)

        # Verify started_at was set
        call_args = mock_manager.broadcast_to_project.call_args
        _, message = call_args[0]
        started_at_str = message["started_at"]
        started_at = datetime.fromisoformat(started_at_str)

        assert before <= started_at <= after

    @pytest.mark.asyncio
    async def test_broadcast_handles_exception(self):
        """Test broadcast returns False when broadcasting fails."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(side_effect=Exception("Network error"))

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_run_started(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast_message_structure(self):
        """Verify complete message structure matches Feature #61 spec."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        started_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_run_started(
                project_name="my-project",
                run_id="abc-123-def",
                spec_id="xyz-789-uvw",
                display_name="Implement User Authentication",
                icon="🔐",
                started_at=started_at,
            )

        call_args = mock_manager.broadcast_to_project.call_args
        _, message = call_args[0]

        # Verify all expected fields are present
        expected_fields = {"type", "run_id", "spec_id", "display_name", "icon", "started_at", "timestamp"}
        assert set(message.keys()) == expected_fields

        # Verify field values
        assert message["type"] == "agent_run_started"
        assert message["run_id"] == "abc-123-def"
        assert message["spec_id"] == "xyz-789-uvw"
        assert message["display_name"] == "Implement User Authentication"
        assert message["icon"] == "🔐"
        assert message["started_at"] == "2024-01-01T12:00:00+00:00"


# =============================================================================
# Test broadcast_run_started_sync Function
# =============================================================================

class TestBroadcastRunStartedSync:
    """Test the synchronous wrapper for broadcast_run_started."""

    def test_sync_broadcast_with_manager_unavailable(self):
        """Test sync broadcast returns False when manager unavailable."""
        with patch("api.websocket_events._get_connection_manager", return_value=None):
            result = broadcast_run_started_sync(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        assert result is False

    def test_sync_broadcast_creates_event_loop(self):
        """Test sync broadcast creates event loop when needed."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = broadcast_run_started_sync(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        assert result is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestRunStartedIntegration:
    """Integration tests for the agent_run_started event."""

    @pytest.mark.asyncio
    async def test_message_is_json_serializable(self):
        """Verify the message can be serialized to JSON."""
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
            icon="🔧",
            started_at=datetime.now(timezone.utc),
        )

        message = payload.to_message()

        # Should not raise
        json_str = json.dumps(message)
        parsed = json.loads(json_str)

        assert parsed["type"] == "agent_run_started"
        assert parsed["run_id"] == "run-123"

    @pytest.mark.asyncio
    async def test_multiple_broadcasts_independent(self):
        """Test multiple broadcasts are independent."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_run_started(
                project_name="project-1",
                run_id="run-1",
                spec_id="spec-1",
                display_name="Feature 1",
            )
            await broadcast_run_started(
                project_name="project-2",
                run_id="run-2",
                spec_id="spec-2",
                display_name="Feature 2",
            )

        assert mock_manager.broadcast_to_project.call_count == 2

        # Verify different project names
        calls = mock_manager.broadcast_to_project.call_args_list
        assert calls[0][0][0] == "project-1"
        assert calls[1][0][0] == "project-2"


# =============================================================================
# Feature Step Verification Tests
# =============================================================================

class TestFeatureStepVerification:
    """Verify each feature step from the specification."""

    @pytest.mark.asyncio
    async def test_step_1_run_status_changes_to_running(self):
        """
        Step 1: When AgentRun status changes to running, publish message.

        The broadcast function is designed to be called when run transitions to running.
        We verify the function can be called successfully.
        """
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_run_started(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        assert result is True
        mock_manager.broadcast_to_project.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_2_message_type_agent_run_started(self):
        """
        Step 2: Message type: agent_run_started.

        Verify the message type field is exactly "agent_run_started".
        """
        payload = RunStartedPayload(
            run_id="run-123",
            spec_id="spec-456",
            display_name="Test Feature",
        )

        message = payload.to_message()

        assert message["type"] == "agent_run_started"

    @pytest.mark.asyncio
    async def test_step_3_payload_contains_required_fields(self):
        """
        Step 3: Payload: run_id, spec_id, display_name, icon, started_at.

        Verify all required fields are present in the payload.
        """
        started_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        payload = RunStartedPayload(
            run_id="abc-123",
            spec_id="def-456",
            display_name="Implement Feature X",
            icon="🚀",
            started_at=started_at,
        )

        message = payload.to_message()

        # All required fields from Feature #61 spec
        assert "run_id" in message
        assert "spec_id" in message
        assert "display_name" in message
        assert "icon" in message
        assert "started_at" in message

        # Verify field values
        assert message["run_id"] == "abc-123"
        assert message["spec_id"] == "def-456"
        assert message["display_name"] == "Implement Feature X"
        assert message["icon"] == "🚀"
        assert message["started_at"] == "2024-01-01T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_step_4_broadcast_to_all_connected_clients(self):
        """
        Step 4: Broadcast to all connected clients.

        Verify broadcast_to_project is called with the correct project name.
        """
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock()

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_run_started(
                project_name="my-awesome-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
            )

        mock_manager.broadcast_to_project.assert_called_once()
        project_name = mock_manager.broadcast_to_project.call_args[0][0]
        assert project_name == "my-awesome-project"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
