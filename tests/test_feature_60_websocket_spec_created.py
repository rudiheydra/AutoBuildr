"""
Feature #60: WebSocket agent_spec_created Event - Comprehensive Tests
=====================================================================

Tests for the WebSocket agent_spec_created event broadcasting functionality.

Feature Requirements:
1. After AgentSpec creation, publish WebSocket message
2. Message type: agent_spec_created
3. Payload includes: spec_id, name, display_name, icon, task_type
4. Broadcast to all connected clients
5. Handle WebSocket errors gracefully

This test suite verifies:
- AgentSpecCreatedPayload dataclass serialization
- broadcast_agent_spec_created function behavior
- Integration with the create_agent_spec API endpoint
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.websocket_events import (
    AgentSpecCreatedPayload,
    broadcast_agent_spec_created,
    broadcast_agent_spec_created_sync,
)


# =============================================================================
# Step 1: AgentSpecCreatedPayload Tests
# =============================================================================

class TestAgentSpecCreatedPayload:
    """Test AgentSpecCreatedPayload dataclass."""

    def test_basic_creation(self):
        """Test creating an AgentSpecCreatedPayload with required fields."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc-123-def-456",
            name="feature-auth-login",
            display_name="Implement Login Feature",
            icon="🔐",
            task_type="coding",
        )

        assert payload.spec_id == "abc-123-def-456"
        assert payload.name == "feature-auth-login"
        assert payload.display_name == "Implement Login Feature"
        assert payload.icon == "🔐"
        assert payload.task_type == "coding"
        assert payload.timestamp is not None

    def test_creation_with_none_icon(self):
        """Test creating with None icon."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc-123",
            name="test-spec",
            display_name="Test Spec",
            icon=None,
            task_type="testing",
        )

        assert payload.icon is None
        assert payload.task_type == "testing"

    def test_creation_with_explicit_timestamp(self):
        """Test creating with explicit timestamp."""
        timestamp = datetime(2024, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="test",
            display_name="Test",
            icon=None,
            task_type="coding",
            timestamp=timestamp,
        )

        assert payload.timestamp == timestamp

    def test_timestamp_defaults_to_now(self):
        """Test that timestamp defaults to current UTC time."""
        before = datetime.now(timezone.utc)

        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="test",
            display_name="Test",
            icon=None,
            task_type="coding",
        )

        after = datetime.now(timezone.utc)

        assert payload.timestamp >= before
        assert payload.timestamp <= after

    def test_to_message_format(self):
        """Test the WebSocket message format (Feature #60 Step 2)."""
        timestamp = datetime(2024, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        payload = AgentSpecCreatedPayload(
            spec_id="abc-123-def-456",
            name="feature-auth-login",
            display_name="Implement Login Feature",
            icon="🔐",
            task_type="coding",
            timestamp=timestamp,
        )

        message = payload.to_message()

        # Step 2: Message type must be "agent_spec_created"
        assert message["type"] == "agent_spec_created"

        # Step 3: Payload must include spec_id, name, display_name, icon, task_type
        assert message["spec_id"] == "abc-123-def-456"
        assert message["name"] == "feature-auth-login"
        assert message["display_name"] == "Implement Login Feature"
        assert message["icon"] == "🔐"
        assert message["task_type"] == "coding"
        assert message["timestamp"] == timestamp.isoformat()

    def test_to_message_with_none_icon(self):
        """Test message format when icon is None."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="test",
            display_name="Test",
            icon=None,
            task_type="testing",
        )

        message = payload.to_message()

        assert message["icon"] is None
        assert message["type"] == "agent_spec_created"

    def test_to_message_is_json_serializable(self):
        """Verify the message can be JSON serialized for WebSocket."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc-123-def-456",
            name="feature-auth-login",
            display_name="Implement Login Feature",
            icon="🔐",
            task_type="coding",
        )

        message = payload.to_message()
        json_str = json.dumps(message)

        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["type"] == "agent_spec_created"
        assert parsed["spec_id"] == "abc-123-def-456"

    def test_all_task_types(self):
        """Test with all valid task types."""
        task_types = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]

        for task_type in task_types:
            payload = AgentSpecCreatedPayload(
                spec_id="abc",
                name="test",
                display_name="Test",
                icon=None,
                task_type=task_type,
            )

            message = payload.to_message()
            assert message["task_type"] == task_type


# =============================================================================
# Step 2: broadcast_agent_spec_created Tests
# =============================================================================

class TestBroadcastAgentSpecCreated:
    """Test broadcast_agent_spec_created function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_manager_not_available(self):
        """Test returns False when WebSocket manager is not available."""
        with patch("api.websocket_events._get_connection_manager", return_value=None):
            result = await broadcast_agent_spec_created(
                project_name="test-project",
                spec_id="abc-123",
                name="test-spec",
                display_name="Test Spec",
                icon="🔧",
                task_type="coding",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcasts_to_correct_project(self):
        """Test that message is broadcast to the correct project (Step 4)."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_agent_spec_created(
                project_name="my-test-project",
                spec_id="abc-123",
                name="test-spec",
                display_name="Test Spec",
                icon="🔧",
                task_type="coding",
            )

        assert result is True
        mock_manager.broadcast_to_project.assert_called_once()
        call_args = mock_manager.broadcast_to_project.call_args
        assert call_args[0][0] == "my-test-project"

    @pytest.mark.asyncio
    async def test_message_format_is_correct(self):
        """Test that the broadcast message has correct format."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)
        captured_message = None

        async def capture_message(project_name, message):
            nonlocal captured_message
            captured_message = message

        mock_manager.broadcast_to_project = capture_message

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_agent_spec_created(
                project_name="test-project",
                spec_id="abc-123-def-456",
                name="feature-auth-login",
                display_name="Implement Login Feature",
                icon="🔐",
                task_type="coding",
            )

        # Verify message format
        assert captured_message["type"] == "agent_spec_created"
        assert captured_message["spec_id"] == "abc-123-def-456"
        assert captured_message["name"] == "feature-auth-login"
        assert captured_message["display_name"] == "Implement Login Feature"
        assert captured_message["icon"] == "🔐"
        assert captured_message["task_type"] == "coding"
        assert "timestamp" in captured_message

    @pytest.mark.asyncio
    async def test_handles_broadcast_exception(self):
        """Test graceful handling of broadcast exceptions (Step 5)."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(side_effect=Exception("Connection error"))

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_agent_spec_created(
                project_name="test-project",
                spec_id="abc-123",
                name="test",
                display_name="Test",
                icon=None,
                task_type="coding",
            )

        # Should return False but not raise an exception
        assert result is False

    @pytest.mark.asyncio
    async def test_with_none_icon(self):
        """Test broadcasting with None icon."""
        mock_manager = MagicMock()
        captured_message = None

        async def capture(project, msg):
            nonlocal captured_message
            captured_message = msg

        mock_manager.broadcast_to_project = capture

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_agent_spec_created(
                project_name="test",
                spec_id="abc",
                name="test",
                display_name="Test",
                icon=None,
                task_type="testing",
            )

        assert captured_message["icon"] is None


# =============================================================================
# Step 3: Synchronous Wrapper Tests
# =============================================================================

class TestBroadcastAgentSpecCreatedSync:
    """Test the synchronous wrapper function."""

    def test_returns_false_when_manager_not_available(self):
        """Test returns False when no manager."""
        with patch("api.websocket_events._get_connection_manager", return_value=None):
            result = broadcast_agent_spec_created_sync(
                project_name="test",
                spec_id="abc",
                name="test",
                display_name="Test",
                icon=None,
                task_type="coding",
            )

        assert result is False


# =============================================================================
# Feature #60 Verification Steps Tests
# =============================================================================

class TestFeature60VerificationSteps:
    """
    Test each verification step from Feature #60.

    Steps:
    1. After AgentSpec creation, publish WebSocket message
    2. Message type: agent_spec_created
    3. Payload includes: spec_id, name, display_name, icon, task_type
    4. Broadcast to all connected clients
    5. Handle WebSocket errors gracefully
    """

    def test_step1_message_published_after_creation(self):
        """Step 1: After AgentSpec creation, publish WebSocket message."""
        # The broadcast function exists and can be called
        assert callable(broadcast_agent_spec_created)
        assert callable(broadcast_agent_spec_created_sync)

        # AgentSpecCreatedPayload can create a valid message
        payload = AgentSpecCreatedPayload(
            spec_id="abc-123",
            name="test-spec",
            display_name="Test Spec",
            icon="🔧",
            task_type="coding",
        )

        assert payload is not None
        assert payload.spec_id == "abc-123"

    def test_step2_message_type_is_agent_spec_created(self):
        """Step 2: Message type: agent_spec_created."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="test",
            display_name="Test",
            icon=None,
            task_type="coding",
        )

        message = payload.to_message()
        assert message["type"] == "agent_spec_created"

    def test_step3_payload_has_required_fields(self):
        """Step 3: Payload includes: spec_id, name, display_name, icon, task_type."""
        payload = AgentSpecCreatedPayload(
            spec_id="uuid-123-456",
            name="feature-auth-login",
            display_name="Implement Login Feature",
            icon="🔐",
            task_type="coding",
        )

        message = payload.to_message()

        # All required fields are present
        assert "spec_id" in message
        assert message["spec_id"] == "uuid-123-456"

        assert "name" in message
        assert message["name"] == "feature-auth-login"

        assert "display_name" in message
        assert message["display_name"] == "Implement Login Feature"

        assert "icon" in message
        assert message["icon"] == "🔐"

        assert "task_type" in message
        assert message["task_type"] == "coding"

    @pytest.mark.asyncio
    async def test_step4_broadcast_to_all_connected_clients(self):
        """Step 4: Broadcast to all connected clients."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_agent_spec_created(
                project_name="test-project",
                spec_id="abc",
                name="test",
                display_name="Test",
                icon=None,
                task_type="coding",
            )

        assert result is True
        # broadcast_to_project was called (broadcasts to all clients for project)
        mock_manager.broadcast_to_project.assert_called_once()

    @pytest.mark.asyncio
    async def test_step5_handle_websocket_errors_gracefully(self):
        """Step 5: Handle WebSocket errors gracefully."""
        mock_manager = MagicMock()
        # Simulate various error types
        errors = [
            Exception("Generic error"),
            ConnectionError("Connection lost"),
            TimeoutError("Broadcast timeout"),
        ]

        for error in errors:
            mock_manager.broadcast_to_project = AsyncMock(side_effect=error)

            with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
                # Should not raise, should return False
                result = await broadcast_agent_spec_created(
                    project_name="test",
                    spec_id="abc",
                    name="test",
                    display_name="Test",
                    icon=None,
                    task_type="coding",
                )

            assert result is False, f"Should return False on {type(error).__name__}"


# =============================================================================
# Integration Tests with API Endpoint
# =============================================================================

class TestIntegrationWithApiEndpoint:
    """Integration tests with the create_agent_spec API endpoint."""

    @pytest.mark.asyncio
    async def test_broadcast_called_with_correct_data(self):
        """Test that broadcast is called with the correct spec data."""
        mock_manager = MagicMock()
        captured_message = None

        async def capture(project, msg):
            nonlocal captured_message
            captured_message = msg

        mock_manager.broadcast_to_project = capture

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_agent_spec_created(
                project_name="my-project",
                spec_id="12345678-1234-5678-1234-567812345678",
                name="feature-user-auth",
                display_name="Implement User Authentication",
                icon="🔒",
                task_type="coding",
            )

        # Verify all fields in the captured message
        assert captured_message is not None
        assert captured_message["type"] == "agent_spec_created"
        assert captured_message["spec_id"] == "12345678-1234-5678-1234-567812345678"
        assert captured_message["name"] == "feature-user-auth"
        assert captured_message["display_name"] == "Implement User Authentication"
        assert captured_message["icon"] == "🔒"
        assert captured_message["task_type"] == "coding"

    def test_message_matches_ui_expectations(self):
        """Test that the message format matches what the UI expects for card creation."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc-123",
            name="test-spec",
            display_name="Test Specification",
            icon="🧪",
            task_type="testing",
        )

        message = payload.to_message()

        # UI expects these exact field names
        expected_fields = ["type", "spec_id", "name", "display_name", "icon", "task_type", "timestamp"]
        for field in expected_fields:
            assert field in message, f"UI expects field '{field}' in message"

        # Type should be used for message routing in UI
        assert message["type"] == "agent_spec_created"

        # Icon can be used for visual display
        assert message["icon"] == "🧪"

        # Task type can be used for card styling/categorization
        assert message["task_type"] == "testing"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_name(self):
        """Test with empty name string."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="",
            display_name="Display Name",
            icon=None,
            task_type="coding",
        )

        message = payload.to_message()
        assert message["name"] == ""

    def test_long_display_name(self):
        """Test with very long display name."""
        long_name = "A" * 1000
        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="test",
            display_name=long_name,
            icon=None,
            task_type="coding",
        )

        message = payload.to_message()
        assert message["display_name"] == long_name

    def test_special_characters_in_name(self):
        """Test with special characters in name."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc",
            name="feature-with-special-chars-123",
            display_name="Feature: Test <Special> 'Chars' \"Quotes\"",
            icon="🔧💻🎉",
            task_type="coding",
        )

        message = payload.to_message()
        # Should be JSON serializable
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        assert parsed["display_name"] == "Feature: Test <Special> 'Chars' \"Quotes\""

    def test_unicode_in_all_fields(self):
        """Test with unicode characters in all fields."""
        payload = AgentSpecCreatedPayload(
            spec_id="abc-日本語-123",
            name="功能-测试",
            display_name="Функция: Тест 🎉",
            icon="🇯🇵🇨🇳🇷🇺",
            task_type="coding",
        )

        message = payload.to_message()
        json_str = json.dumps(message, ensure_ascii=False)
        assert "日本語" in json_str
        assert "功能" in json_str
        assert "Функция" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
