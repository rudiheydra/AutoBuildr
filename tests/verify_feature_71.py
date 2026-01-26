#!/usr/bin/env python3
"""
Feature #71: Real-time Card Updates via WebSocket
=================================================

Verification script that tests all 8 steps of the feature:
1. Create useAgentRunUpdates hook
2. Subscribe to run-specific WebSocket channel
3. Handle agent_run_started message
4. Handle agent_event_logged message to update turns_used
5. Handle agent_acceptance_update message
6. Update component state on message
7. Unsubscribe on unmount
8. Handle reconnection gracefully

This verification script checks:
- Hook file exists with correct structure
- Types are defined correctly
- All message handlers are implemented
- Reconnection logic with exponential backoff
- Unmount cleanup pattern
"""

import os
import re
import sys
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def check(name: str, condition: bool, details: str = "") -> bool:
    """Print a check result and return success status."""
    status = f"{GREEN}PASS{RESET}" if condition else f"{RED}FAIL{RESET}"
    print(f"  [{status}] {name}")
    if details and not condition:
        print(f"         {YELLOW}{details}{RESET}")
    return condition

def main():
    """Run all verification steps."""
    print(f"\n{BOLD}Feature #71: Real-time Card Updates via WebSocket{RESET}")
    print("=" * 60)

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    ui_src = project_root / "ui" / "src"
    hooks_dir = ui_src / "hooks"

    all_passed = True

    # =========================================================================
    # Step 1: Create useAgentRunUpdates hook
    # =========================================================================
    print(f"\n{BOLD}Step 1: Create useAgentRunUpdates hook{RESET}")

    hook_file = hooks_dir / "useAgentRunUpdates.ts"
    passed = check("Hook file exists", hook_file.exists())
    all_passed &= passed

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for main hook function
        passed = check(
            "useAgentRunUpdates function exported",
            "export function useAgentRunUpdates" in hook_content
        )
        all_passed &= passed

        # Check for options interface
        passed = check(
            "UseAgentRunUpdatesOptions interface defined",
            "interface UseAgentRunUpdatesOptions" in hook_content or
            "export interface UseAgentRunUpdatesOptions" in hook_content
        )
        all_passed &= passed

        # Check for return type interface
        passed = check(
            "UseAgentRunUpdatesReturn interface defined",
            "UseAgentRunUpdatesReturn" in hook_content
        )
        all_passed &= passed

        # Check for state interface
        passed = check(
            "AgentRunUpdateState interface defined",
            "AgentRunUpdateState" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 2: Subscribe to run-specific WebSocket channel
    # =========================================================================
    print(f"\n{BOLD}Step 2: Subscribe to run-specific WebSocket channel{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check WebSocket creation
        passed = check(
            "WebSocket connection created",
            "new WebSocket" in hook_content
        )
        all_passed &= passed

        # Check for project-based WebSocket URL
        passed = check(
            "WebSocket URL includes project name",
            "/ws/projects/" in hook_content
        )
        all_passed &= passed

        # Check for runId filtering
        passed = check(
            "Messages filtered by runId",
            "shouldProcessMessage" in hook_content or
            "runId === " in hook_content or
            "message.run_id" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 3: Handle agent_run_started message
    # =========================================================================
    print(f"\n{BOLD}Step 3: Handle agent_run_started message{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for handler function
        passed = check(
            "handleRunStarted function defined",
            "handleRunStarted" in hook_content
        )
        all_passed &= passed

        # Check message type handling
        passed = check(
            "agent_run_started case handled",
            "'agent_run_started'" in hook_content or
            '"agent_run_started"' in hook_content
        )
        all_passed &= passed

        # Check status update to running
        passed = check(
            "Status updated to 'running' on start",
            "status: 'running'" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 4: Handle agent_event_logged message to update turns_used
    # =========================================================================
    print(f"\n{BOLD}Step 4: Handle agent_event_logged message to update turns_used{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for handler function
        passed = check(
            "handleEventLogged function defined",
            "handleEventLogged" in hook_content
        )
        all_passed &= passed

        # Check message type handling
        passed = check(
            "agent_event_logged case handled",
            "'agent_event_logged'" in hook_content or
            '"agent_event_logged"' in hook_content
        )
        all_passed &= passed

        # Check turns_used update
        passed = check(
            "turnsUsed updated on turn_complete",
            "turnsUsed" in hook_content and "turn_complete" in hook_content
        )
        all_passed &= passed

        # Check lastEvent tracking
        passed = check(
            "lastEvent state tracked",
            "lastEvent" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 5: Handle agent_acceptance_update message
    # =========================================================================
    print(f"\n{BOLD}Step 5: Handle agent_acceptance_update message{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for handler function
        passed = check(
            "handleAcceptanceUpdate function defined",
            "handleAcceptanceUpdate" in hook_content
        )
        all_passed &= passed

        # Check message type handling
        passed = check(
            "agent_acceptance_update case handled",
            "'agent_acceptance_update'" in hook_content or
            '"agent_acceptance_update"' in hook_content
        )
        all_passed &= passed

        # Check acceptance results update
        passed = check(
            "acceptanceResults state updated",
            "acceptanceResults" in hook_content
        )
        all_passed &= passed

        # Check final verdict update
        passed = check(
            "finalVerdict state updated",
            "finalVerdict" in hook_content and "final_verdict" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 6: Update component state on message
    # =========================================================================
    print(f"\n{BOLD}Step 6: Update component state on message{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for useState
        passed = check(
            "useState hook used for state management",
            "useState" in hook_content
        )
        all_passed &= passed

        # Check for setState updates
        passed = check(
            "setState used to update state",
            "setState" in hook_content
        )
        all_passed &= passed

        # Check for state spread pattern
        passed = check(
            "State spread pattern used (...prev)",
            "...prev" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 7: Unsubscribe on unmount
    # =========================================================================
    print(f"\n{BOLD}Step 7: Unsubscribe on unmount{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for useEffect cleanup
        passed = check(
            "useEffect used for lifecycle management",
            "useEffect" in hook_content
        )
        all_passed &= passed

        # Check for cleanup return function
        passed = check(
            "Cleanup function returned from useEffect",
            "return () =>" in hook_content
        )
        all_passed &= passed

        # Check for WebSocket close on cleanup
        passed = check(
            "WebSocket closed on cleanup",
            ".close()" in hook_content
        )
        all_passed &= passed

        # Check for mounted ref pattern
        passed = check(
            "mountedRef used to prevent updates after unmount",
            "mountedRef" in hook_content
        )
        all_passed &= passed

        # Check for interval cleanup
        passed = check(
            "clearInterval called on cleanup (ping interval)",
            "clearInterval" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Step 8: Handle reconnection gracefully
    # =========================================================================
    print(f"\n{BOLD}Step 8: Handle reconnection gracefully{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        # Check for reconnection logic
        passed = check(
            "Reconnection logic implemented",
            "reconnect" in hook_content.lower()
        )
        all_passed &= passed

        # Check for exponential backoff delays
        passed = check(
            "Exponential backoff delays defined",
            "RECONNECT_DELAYS" in hook_content or
            "1000, 2000, 4000" in hook_content or
            "backoff" in hook_content.lower()
        )
        all_passed &= passed

        # Check for reconnect attempt tracking
        passed = check(
            "Reconnect attempts tracked",
            "reconnectAttempt" in hook_content
        )
        all_passed &= passed

        # Check for isReconnecting state
        passed = check(
            "isReconnecting state exposed",
            "isReconnecting" in hook_content
        )
        all_passed &= passed

        # Check for timeout cleanup
        passed = check(
            "Reconnect timeout cleared on cleanup",
            "clearTimeout" in hook_content and "reconnect" in hook_content.lower()
        )
        all_passed &= passed

    # =========================================================================
    # Additional Checks: Types and Integration
    # =========================================================================
    print(f"\n{BOLD}Additional: Types and Integration{RESET}")

    types_file = ui_src / "lib" / "types.ts"
    if types_file.exists():
        types_content = types_file.read_text()

        passed = check(
            "WSAgentRunStartedMessage type defined",
            "WSAgentRunStartedMessage" in types_content
        )
        all_passed &= passed

        passed = check(
            "WSAgentEventLoggedMessage type defined",
            "WSAgentEventLoggedMessage" in types_content
        )
        all_passed &= passed

        passed = check(
            "WSAgentAcceptanceUpdateMessage type defined",
            "WSAgentAcceptanceUpdateMessage" in types_content
        )
        all_passed &= passed

        passed = check(
            "WSValidatorResult type defined",
            "WSValidatorResult" in types_content
        )
        all_passed &= passed
    else:
        passed = check("Types file exists", False)
        all_passed &= passed

    # Check WebSocket hook integration
    websocket_file = hooks_dir / "useWebSocket.ts"
    if websocket_file.exists():
        ws_content = websocket_file.read_text()

        passed = check(
            "useWebSocket recognizes agent run message types",
            "agent_run_started" in ws_content or
            "agent_event_logged" in ws_content or
            "agent_acceptance_update" in ws_content
        )
        all_passed &= passed

    # =========================================================================
    # Check for Multiple Runs Support
    # =========================================================================
    print(f"\n{BOLD}Additional: Multiple Runs Support{RESET}")

    if hook_file.exists():
        hook_content = hook_file.read_text()

        passed = check(
            "useMultipleAgentRunUpdates hook exported",
            "export function useMultipleAgentRunUpdates" in hook_content
        )
        all_passed &= passed

        passed = check(
            "Map used for multiple run state management",
            "Map<string" in hook_content or "new Map" in hook_content
        )
        all_passed &= passed

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 60)
    if all_passed:
        print(f"{GREEN}{BOLD}ALL VERIFICATION STEPS PASSED{RESET}")
        print(f"\nFeature #71: Real-time Card Updates via WebSocket is complete!")
        return 0
    else:
        print(f"{RED}{BOLD}SOME VERIFICATION STEPS FAILED{RESET}")
        print(f"\nPlease review the failed checks above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
