#!/usr/bin/env python3
"""
Feature #60 Verification Script
===============================

Verifies all 5 feature steps for WebSocket agent_spec_created Event.

Feature Requirements:
1. After AgentSpec creation, publish WebSocket message
2. Message type: agent_spec_created
3. Payload includes: spec_id, name, display_name, icon, task_type
4. Broadcast to all connected clients
5. Handle WebSocket errors gracefully
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_step1_publish_after_creation():
    """Step 1: After AgentSpec creation, publish WebSocket message."""
    print("Step 1: After AgentSpec creation, publish WebSocket message")

    # Verify the broadcast function exists and is callable
    from api.websocket_events import broadcast_agent_spec_created, broadcast_agent_spec_created_sync

    assert callable(broadcast_agent_spec_created), "broadcast_agent_spec_created must be callable"
    assert callable(broadcast_agent_spec_created_sync), "broadcast_agent_spec_created_sync must be callable"

    # Verify the API endpoint imports and calls the broadcast function
    import inspect
    from server.routers import agent_specs

    # Check that the create_agent_spec endpoint exists
    assert hasattr(agent_specs, 'create_agent_spec'), "create_agent_spec endpoint must exist"

    # Read the source to verify broadcast is called
    source = inspect.getsource(agent_specs.create_agent_spec)
    assert 'broadcast_agent_spec_created' in source, "Endpoint must call broadcast_agent_spec_created"

    print("  - broadcast_agent_spec_created function exists: PASS")
    print("  - broadcast_agent_spec_created_sync function exists: PASS")
    print("  - create_agent_spec endpoint calls broadcast: PASS")
    print("  STEP 1: PASS\n")
    return True


def verify_step2_message_type():
    """Step 2: Message type: agent_spec_created."""
    print("Step 2: Message type: agent_spec_created")

    from api.websocket_events import AgentSpecCreatedPayload

    payload = AgentSpecCreatedPayload(
        spec_id="test-id",
        name="test-spec",
        display_name="Test Spec",
        icon="🔧",
        task_type="coding",
    )

    message = payload.to_message()

    assert message["type"] == "agent_spec_created", f"Message type should be 'agent_spec_created', got '{message['type']}'"

    print(f"  - Message type is 'agent_spec_created': PASS")
    print("  STEP 2: PASS\n")
    return True


def verify_step3_payload_fields():
    """Step 3: Payload includes: spec_id, name, display_name, icon, task_type."""
    print("Step 3: Payload includes: spec_id, name, display_name, icon, task_type")

    from api.websocket_events import AgentSpecCreatedPayload

    payload = AgentSpecCreatedPayload(
        spec_id="uuid-123-456",
        name="feature-auth-login",
        display_name="Implement Login Feature",
        icon="🔐",
        task_type="coding",
    )

    message = payload.to_message()

    # Check each required field
    required_fields = [
        ("spec_id", "uuid-123-456"),
        ("name", "feature-auth-login"),
        ("display_name", "Implement Login Feature"),
        ("icon", "🔐"),
        ("task_type", "coding"),
    ]

    for field, expected_value in required_fields:
        assert field in message, f"Payload missing required field: {field}"
        assert message[field] == expected_value, f"Field '{field}' has wrong value"
        print(f"  - Payload includes '{field}': PASS")

    print("  STEP 3: PASS\n")
    return True


def verify_step4_broadcast_to_all_clients():
    """Step 4: Broadcast to all connected clients."""
    print("Step 4: Broadcast to all connected clients")

    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from api.websocket_events import broadcast_agent_spec_created

    # Mock the connection manager
    mock_manager = MagicMock()
    mock_manager.broadcast_to_project = AsyncMock(return_value=None)

    with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
        result = asyncio.run(broadcast_agent_spec_created(
            project_name="test-project",
            spec_id="abc-123",
            name="test",
            display_name="Test",
            icon=None,
            task_type="coding",
        ))

    assert result is True, "Broadcast should return True on success"
    mock_manager.broadcast_to_project.assert_called_once()

    # Verify correct project was used
    call_args = mock_manager.broadcast_to_project.call_args
    assert call_args[0][0] == "test-project", "Should broadcast to correct project"

    print("  - broadcast_agent_spec_created returns True on success: PASS")
    print("  - Calls broadcast_to_project with correct project: PASS")
    print("  STEP 4: PASS\n")
    return True


def verify_step5_handle_errors_gracefully():
    """Step 5: Handle WebSocket errors gracefully."""
    print("Step 5: Handle WebSocket errors gracefully")

    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from api.websocket_events import broadcast_agent_spec_created

    # Test with various error types
    error_types = [
        Exception("Generic error"),
        ConnectionError("Connection lost"),
        TimeoutError("Timeout"),
    ]

    for error in error_types:
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(side_effect=error)

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            # Should not raise, should return False
            result = asyncio.run(broadcast_agent_spec_created(
                project_name="test",
                spec_id="abc",
                name="test",
                display_name="Test",
                icon=None,
                task_type="coding",
            ))

        assert result is False, f"Should return False on {type(error).__name__}"
        print(f"  - Handles {type(error).__name__} gracefully: PASS")

    # Test when manager is not available
    with patch("api.websocket_events._get_connection_manager", return_value=None):
        result = asyncio.run(broadcast_agent_spec_created(
            project_name="test",
            spec_id="abc",
            name="test",
            display_name="Test",
            icon=None,
            task_type="coding",
        ))

    assert result is False, "Should return False when manager not available"
    print("  - Handles missing manager gracefully: PASS")

    print("  STEP 5: PASS\n")
    return True


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #60: WebSocket agent_spec_created Event - Verification")
    print("=" * 70)
    print()

    steps = [
        ("Step 1", verify_step1_publish_after_creation),
        ("Step 2", verify_step2_message_type),
        ("Step 3", verify_step3_payload_fields),
        ("Step 4", verify_step4_broadcast_to_all_clients),
        ("Step 5", verify_step5_handle_errors_gracefully),
    ]

    passed = 0
    failed = 0

    for step_name, verify_func in steps:
        try:
            if verify_func():
                passed += 1
            else:
                failed += 1
                print(f"  {step_name}: FAIL\n")
        except Exception as e:
            failed += 1
            print(f"  {step_name}: FAIL - {e}\n")

    print("=" * 70)
    print(f"VERIFICATION SUMMARY: {passed}/{len(steps)} steps passed")
    print("=" * 70)

    if failed == 0:
        print("\n✅ Feature #60 VERIFIED - All steps pass!")
        return 0
    else:
        print(f"\n❌ Feature #60 FAILED - {failed} step(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
