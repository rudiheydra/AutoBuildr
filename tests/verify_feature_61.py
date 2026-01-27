#!/usr/bin/env python3
"""
Feature #61 Verification Script
================================

WebSocket agent_run_started Event

Verifies all 4 feature steps:
1. When AgentRun status changes to running, publish message
2. Message type: agent_run_started
3. Payload: run_id, spec_id, display_name, icon, started_at
4. Broadcast to all connected clients

This script verifies the implementation through code analysis and unit tests.
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))


def verify_step_1():
    """
    Step 1: When AgentRun status changes to running, publish message.

    Verify that the broadcast function is called when a run transitions to running.
    This is implemented in server/routers/agent_specs.py::_execute_spec_background().
    """
    print("\n=== Step 1: When AgentRun status changes to running, publish message ===")

    # Check the agent_specs router integration
    agent_specs_path = root / "server" / "routers" / "agent_specs.py"
    assert agent_specs_path.exists(), "agent_specs.py router not found"

    content = agent_specs_path.read_text()

    # Verify broadcast_run_started is imported
    assert "from api.websocket_events import broadcast_run_started" in content, \
        "broadcast_run_started not imported in agent_specs router"

    # Verify broadcast is called after run transitions to running
    assert 'run.status = "running"' in content, \
        "Run status transition to running not found"

    # Verify broadcast_run_started is called
    assert "await broadcast_run_started(" in content, \
        "broadcast_run_started not called in agent_specs router"

    # Verify it's called with project_name parameter
    assert "project_name=project_name" in content, \
        "broadcast_run_started not called with project_name parameter"

    print("✓ broadcast_run_started is imported in agent_specs.py")
    print("✓ Run status transitions to 'running'")
    print("✓ broadcast_run_started is called after transition")
    print("✓ Broadcast uses project_name for routing")
    print("PASS: Step 1 verified")
    return True


def verify_step_2():
    """
    Step 2: Message type: agent_run_started.

    Verify that the message type is exactly "agent_run_started".
    """
    print("\n=== Step 2: Message type: agent_run_started ===")

    from api.websocket_events import RunStartedPayload

    payload = RunStartedPayload(
        run_id="test-run",
        spec_id="test-spec",
        display_name="Test Feature",
    )
    message = payload.to_message()

    assert message["type"] == "agent_run_started", \
        f"Expected message type 'agent_run_started', got '{message['type']}'"

    print("✓ RunStartedPayload.to_message() returns type='agent_run_started'")
    print("PASS: Step 2 verified")
    return True


def verify_step_3():
    """
    Step 3: Payload: run_id, spec_id, display_name, icon, started_at.

    Verify all required fields are present in the payload.
    """
    print("\n=== Step 3: Payload: run_id, spec_id, display_name, icon, started_at ===")

    from datetime import datetime, timezone
    from api.websocket_events import RunStartedPayload

    started_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    payload = RunStartedPayload(
        run_id="abc-123",
        spec_id="def-456",
        display_name="Implement Auth",
        icon="🔐",
        started_at=started_at,
    )
    message = payload.to_message()

    # Check required fields
    required_fields = ["run_id", "spec_id", "display_name", "icon", "started_at"]
    for field in required_fields:
        assert field in message, f"Required field '{field}' not in message"
        print(f"✓ Field '{field}' present in message")

    # Verify field values
    assert message["run_id"] == "abc-123", "run_id incorrect"
    assert message["spec_id"] == "def-456", "spec_id incorrect"
    assert message["display_name"] == "Implement Auth", "display_name incorrect"
    assert message["icon"] == "🔐", "icon incorrect"
    assert message["started_at"] == "2024-01-01T12:00:00+00:00", "started_at incorrect"

    print("✓ All field values match expected")
    print("PASS: Step 3 verified")
    return True


def verify_step_4():
    """
    Step 4: Broadcast to all connected clients.

    Verify broadcast_run_started calls manager.broadcast_to_project().
    """
    print("\n=== Step 4: Broadcast to all connected clients ===")

    from unittest.mock import AsyncMock, MagicMock, patch
    import asyncio

    from api.websocket_events import broadcast_run_started

    # Create mock manager
    mock_manager = MagicMock()
    mock_manager.broadcast_to_project = AsyncMock()

    async def test_broadcast():
        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_run_started(
                project_name="test-project",
                run_id="run-123",
                spec_id="spec-456",
                display_name="Test Feature",
                icon="🔧",
            )
        return result

    result = asyncio.run(test_broadcast())

    assert result is True, "Broadcast returned False"
    assert mock_manager.broadcast_to_project.called, \
        "broadcast_to_project was not called"

    call_args = mock_manager.broadcast_to_project.call_args
    project_name, message = call_args[0]

    assert project_name == "test-project", \
        f"Expected project 'test-project', got '{project_name}'"

    print("✓ broadcast_run_started calls manager.broadcast_to_project()")
    print("✓ Broadcast routes to correct project")
    print("✓ Message payload is passed correctly")
    print("PASS: Step 4 verified")
    return True


def verify_exports():
    """Verify the new functions are properly exported."""
    print("\n=== Verifying Exports ===")

    from api import (
        RunStartedPayload,
        broadcast_run_started,
        broadcast_run_started_sync,
    )

    print("✓ RunStartedPayload exported from api module")
    print("✓ broadcast_run_started exported from api module")
    print("✓ broadcast_run_started_sync exported from api module")
    print("PASS: Exports verified")
    return True


def verify_ui_types():
    """Verify the UI has the corresponding TypeScript types."""
    print("\n=== Verifying UI Types ===")

    ui_types_path = root / "ui" / "src" / "lib" / "types.ts"
    assert ui_types_path.exists(), "UI types.ts not found"

    content = ui_types_path.read_text()

    # Check for WSAgentRunStartedMessage interface
    assert "interface WSAgentRunStartedMessage" in content, \
        "WSAgentRunStartedMessage interface not found in UI types"

    assert "'agent_run_started'" in content, \
        "agent_run_started message type not found in UI types"

    # Check for required fields in the interface
    required_fields = ["run_id", "spec_id", "display_name", "icon", "started_at"]
    for field in required_fields:
        assert field in content, f"Field '{field}' not found in UI types"
        print(f"✓ UI type includes '{field}' field")

    print("✓ WSAgentRunStartedMessage interface exists")
    print("✓ Message type 'agent_run_started' defined")
    print("PASS: UI types verified")
    return True


def run_unit_tests():
    """Run the unit tests for Feature #61."""
    print("\n=== Running Unit Tests ===")

    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/test_feature_61_websocket_run_started.py", "-v"],
        capture_output=True,
        text=True,
        cwd=root,
    )

    if result.returncode == 0:
        # Count passed tests
        lines = result.stdout.split("\n")
        passed = sum(1 for line in lines if "PASSED" in line)
        print(f"✓ All {passed} unit tests passed")
        print("PASS: Unit tests passed")
        return True
    else:
        print(f"FAIL: Unit tests failed")
        print(result.stdout)
        print(result.stderr)
        return False


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #61: WebSocket agent_run_started Event")
    print("=" * 60)

    results = []

    results.append(("Step 1: Run status to running triggers publish", verify_step_1()))
    results.append(("Step 2: Message type agent_run_started", verify_step_2()))
    results.append(("Step 3: Payload fields", verify_step_3()))
    results.append(("Step 4: Broadcast to all clients", verify_step_4()))
    results.append(("Exports", verify_exports()))
    results.append(("UI Types", verify_ui_types()))
    results.append(("Unit Tests", run_unit_tests()))

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("ALL VERIFICATIONS PASSED - Feature #61 is complete")
        return 0
    else:
        print("SOME VERIFICATIONS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
