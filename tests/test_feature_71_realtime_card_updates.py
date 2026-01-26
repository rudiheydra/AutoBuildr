#!/usr/bin/env python3
"""
Feature #71: Real-time Card Updates via WebSocket
Unit Tests
=================================================

This test file verifies the implementation of the useAgentRunUpdates hook
for connecting DynamicAgentCard components to WebSocket for real-time updates.

Tests cover:
- Hook file structure and exports
- WebSocket message handling
- State management
- Reconnection logic
- Types and integration
"""

import os
import re
import sys
import json
from pathlib import Path
from typing import Any

import pytest

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
UI_SRC = PROJECT_ROOT / "ui" / "src"
HOOKS_DIR = UI_SRC / "hooks"
TYPES_FILE = UI_SRC / "lib" / "types.ts"


class TestHookFileStructure:
    """Tests for the useAgentRunUpdates.ts file structure."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        hook_file = HOOKS_DIR / "useAgentRunUpdates.ts"
        assert hook_file.exists(), "useAgentRunUpdates.ts file not found"
        return hook_file.read_text()

    def test_hook_file_exists(self):
        """Step 1a: Hook file exists."""
        hook_file = HOOKS_DIR / "useAgentRunUpdates.ts"
        assert hook_file.exists()

    def test_main_hook_exported(self, hook_content: str):
        """Step 1b: Main useAgentRunUpdates function is exported."""
        assert "export function useAgentRunUpdates" in hook_content

    def test_options_interface_defined(self, hook_content: str):
        """Step 1c: UseAgentRunUpdatesOptions interface is defined."""
        assert "UseAgentRunUpdatesOptions" in hook_content
        assert "projectName:" in hook_content
        assert "runId:" in hook_content

    def test_return_type_interface_defined(self, hook_content: str):
        """Step 1d: UseAgentRunUpdatesReturn interface is defined."""
        assert "UseAgentRunUpdatesReturn" in hook_content

    def test_state_interface_defined(self, hook_content: str):
        """Step 1e: AgentRunUpdateState interface is defined."""
        assert "AgentRunUpdateState" in hook_content

    def test_state_interface_has_required_fields(self, hook_content: str):
        """Step 1f: AgentRunUpdateState has all required fields."""
        required_fields = [
            "status:",
            "turnsUsed:",
            "tokensIn:",
            "tokensOut:",
            "finalVerdict:",
            "acceptanceResults:",
            "error:",
            "lastEvent:",
            "isConnected:",
            "isReconnecting:",
        ]
        for field in required_fields:
            assert field in hook_content, f"Missing field: {field}"


class TestWebSocketSubscription:
    """Tests for WebSocket subscription behavior."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_websocket_created(self, hook_content: str):
        """Step 2a: WebSocket connection is created."""
        assert "new WebSocket" in hook_content

    def test_websocket_url_includes_project(self, hook_content: str):
        """Step 2b: WebSocket URL includes project name."""
        assert "/ws/projects/" in hook_content

    def test_protocol_detection(self, hook_content: str):
        """Step 2c: Protocol detection for ws/wss."""
        assert "wss:" in hook_content or "ws:" in hook_content
        assert "window.location.protocol" in hook_content

    def test_messages_filtered_by_run_id(self, hook_content: str):
        """Step 2d: Messages are filtered by runId."""
        assert "shouldProcessMessage" in hook_content


class TestAgentRunStartedHandler:
    """Tests for agent_run_started message handling."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_handler_function_defined(self, hook_content: str):
        """Step 3a: handleRunStarted function is defined."""
        assert "handleRunStarted" in hook_content

    def test_message_type_handled(self, hook_content: str):
        """Step 3b: agent_run_started message type is handled."""
        assert "'agent_run_started'" in hook_content or '"agent_run_started"' in hook_content

    def test_status_set_to_running(self, hook_content: str):
        """Step 3c: Status is updated to 'running' on start."""
        assert "status: 'running'" in hook_content


class TestAgentEventLoggedHandler:
    """Tests for agent_event_logged message handling."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_handler_function_defined(self, hook_content: str):
        """Step 4a: handleEventLogged function is defined."""
        assert "handleEventLogged" in hook_content

    def test_message_type_handled(self, hook_content: str):
        """Step 4b: agent_event_logged message type is handled."""
        assert "'agent_event_logged'" in hook_content or '"agent_event_logged"' in hook_content

    def test_turns_used_updated_on_turn_complete(self, hook_content: str):
        """Step 4c: turnsUsed is updated on turn_complete events."""
        # Both turnsUsed and turn_complete should be referenced
        assert "turnsUsed" in hook_content
        assert "turn_complete" in hook_content

    def test_last_event_tracked(self, hook_content: str):
        """Step 4d: lastEvent state is tracked."""
        assert "lastEvent" in hook_content


class TestAgentAcceptanceUpdateHandler:
    """Tests for agent_acceptance_update message handling."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_handler_function_defined(self, hook_content: str):
        """Step 5a: handleAcceptanceUpdate function is defined."""
        assert "handleAcceptanceUpdate" in hook_content

    def test_message_type_handled(self, hook_content: str):
        """Step 5b: agent_acceptance_update message type is handled."""
        assert "'agent_acceptance_update'" in hook_content or '"agent_acceptance_update"' in hook_content

    def test_acceptance_results_updated(self, hook_content: str):
        """Step 5c: acceptanceResults state is updated."""
        assert "acceptanceResults" in hook_content

    def test_final_verdict_updated(self, hook_content: str):
        """Step 5d: finalVerdict state is updated."""
        assert "finalVerdict" in hook_content
        assert "final_verdict" in hook_content

    def test_status_updated_on_verdict(self, hook_content: str):
        """Step 5e: Status is updated based on verdict."""
        # Check for status update based on passed/failed verdict
        assert "completed" in hook_content or "'completed'" in hook_content
        assert "failed" in hook_content or "'failed'" in hook_content


class TestComponentStateUpdates:
    """Tests for component state update mechanisms."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_use_state_hook(self, hook_content: str):
        """Step 6a: useState hook is used for state management."""
        assert "useState" in hook_content

    def test_set_state_used(self, hook_content: str):
        """Step 6b: setState is used to update state."""
        assert "setState" in hook_content

    def test_state_spread_pattern(self, hook_content: str):
        """Step 6c: State spread pattern (...prev) is used."""
        assert "...prev" in hook_content

    def test_use_callback_for_handlers(self, hook_content: str):
        """Step 6d: useCallback is used for message handlers."""
        assert "useCallback" in hook_content

    def test_use_memo_for_optimization(self, hook_content: str):
        """Step 6e: useMemo is used for optimization."""
        assert "useMemo" in hook_content


class TestUnmountCleanup:
    """Tests for unmount cleanup behavior."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_use_effect_for_lifecycle(self, hook_content: str):
        """Step 7a: useEffect is used for lifecycle management."""
        assert "useEffect" in hook_content

    def test_cleanup_function_returned(self, hook_content: str):
        """Step 7b: Cleanup function is returned from useEffect."""
        assert "return () =>" in hook_content

    def test_websocket_closed_on_cleanup(self, hook_content: str):
        """Step 7c: WebSocket is closed on cleanup."""
        assert ".close()" in hook_content

    def test_mounted_ref_pattern(self, hook_content: str):
        """Step 7d: mountedRef is used to prevent updates after unmount."""
        assert "mountedRef" in hook_content

    def test_interval_cleared_on_cleanup(self, hook_content: str):
        """Step 7e: clearInterval is called on cleanup."""
        assert "clearInterval" in hook_content


class TestReconnectionLogic:
    """Tests for reconnection handling."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_reconnection_implemented(self, hook_content: str):
        """Step 8a: Reconnection logic is implemented."""
        assert "reconnect" in hook_content.lower()

    def test_exponential_backoff(self, hook_content: str):
        """Step 8b: Exponential backoff delays are defined."""
        assert "RECONNECT_DELAYS" in hook_content

    def test_reconnect_attempts_tracked(self, hook_content: str):
        """Step 8c: Reconnect attempts are tracked."""
        assert "reconnectAttempt" in hook_content

    def test_is_reconnecting_state(self, hook_content: str):
        """Step 8d: isReconnecting state is exposed."""
        assert "isReconnecting" in hook_content

    def test_timeout_cleared_on_cleanup(self, hook_content: str):
        """Step 8e: Reconnect timeout is cleared on cleanup."""
        assert "clearTimeout" in hook_content
        assert "reconnectTimeoutRef" in hook_content

    def test_max_delay_cap(self, hook_content: str):
        """Step 8f: Maximum reconnection delay is capped."""
        # Check for delay array with capped values or max calculation
        assert "30000" in hook_content or "15000" in hook_content


class TestTypeDefinitions:
    """Tests for TypeScript type definitions."""

    @pytest.fixture
    def types_content(self) -> str:
        """Load types file content."""
        assert TYPES_FILE.exists(), "types.ts file not found"
        return TYPES_FILE.read_text()

    def test_agent_run_started_message_type(self, types_content: str):
        """Additional: WSAgentRunStartedMessage type is defined."""
        assert "WSAgentRunStartedMessage" in types_content
        assert "run_id:" in types_content

    def test_agent_event_logged_message_type(self, types_content: str):
        """Additional: WSAgentEventLoggedMessage type is defined."""
        assert "WSAgentEventLoggedMessage" in types_content
        assert "event_type:" in types_content
        assert "sequence:" in types_content

    def test_agent_acceptance_update_message_type(self, types_content: str):
        """Additional: WSAgentAcceptanceUpdateMessage type is defined."""
        assert "WSAgentAcceptanceUpdateMessage" in types_content
        assert "validator_results:" in types_content

    def test_validator_result_type(self, types_content: str):
        """Additional: WSValidatorResult type is defined."""
        assert "WSValidatorResult" in types_content
        assert "passed:" in types_content
        assert "message:" in types_content


class TestMultipleRunsSupport:
    """Tests for multiple runs support."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_multiple_runs_hook_exported(self, hook_content: str):
        """Additional: useMultipleAgentRunUpdates hook is exported."""
        assert "export function useMultipleAgentRunUpdates" in hook_content

    def test_map_used_for_state(self, hook_content: str):
        """Additional: Map is used for multiple run state management."""
        assert "Map<string" in hook_content or "new Map" in hook_content


class TestWebSocketIntegration:
    """Tests for WebSocket integration with existing hooks."""

    @pytest.fixture
    def websocket_content(self) -> str:
        """Load useWebSocket.ts content."""
        ws_file = HOOKS_DIR / "useWebSocket.ts"
        assert ws_file.exists(), "useWebSocket.ts file not found"
        return ws_file.read_text()

    def test_websocket_recognizes_message_types(self, websocket_content: str):
        """Integration: useWebSocket handles agent run message types."""
        # Check that useWebSocket mentions these message types
        assert (
            "agent_run_started" in websocket_content or
            "agent_event_logged" in websocket_content or
            "agent_acceptance_update" in websocket_content
        )


class TestPingPongHeartbeat:
    """Tests for ping/pong heartbeat mechanism."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_ping_message_sent(self, hook_content: str):
        """Heartbeat: Ping messages are sent to keep connection alive."""
        assert "ping" in hook_content.lower()
        assert "30000" in hook_content or "setInterval" in hook_content

    def test_pong_message_handled(self, hook_content: str):
        """Heartbeat: Pong messages are handled."""
        assert "pong" in hook_content.lower()


class TestInitialStateFromRun:
    """Tests for initial state extraction from AgentRun."""

    @pytest.fixture
    def hook_content(self) -> str:
        """Load hook file content."""
        return (HOOKS_DIR / "useAgentRunUpdates.ts").read_text()

    def test_initial_run_parameter(self, hook_content: str):
        """Initial state: initialRun parameter is accepted."""
        assert "initialRun" in hook_content

    def test_get_initial_state_function(self, hook_content: str):
        """Initial state: getInitialState function is defined."""
        assert "getInitialState" in hook_content

    def test_initial_state_extracted(self, hook_content: str):
        """Initial state: State is extracted from initialRun."""
        # Check that fields are extracted from initialRun
        assert "initialRun.status" in hook_content or "initialRun?.status" in hook_content


# Run verification steps as a comprehensive test
class TestFeature71VerificationSteps:
    """Aggregate test that runs all verification steps."""

    def test_all_verification_steps_pass(self):
        """Run the verification script and ensure all steps pass."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tests" / "verify_feature_71.py")],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        # Check that all steps passed
        assert "ALL VERIFICATION STEPS PASSED" in result.stdout, (
            f"Verification failed:\n{result.stdout}\n{result.stderr}"
        )
