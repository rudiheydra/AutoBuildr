#!/usr/bin/env python3
"""
Feature #62 Verification Script
================================

WebSocket agent_event_logged Event

Verifies all 5 feature steps:
1. Filter events to only broadcast significant types (tool_call, turn_complete, acceptance_check)
2. Message type: agent_event_logged
3. Payload: run_id, event_type, sequence, tool_name (if applicable)
4. Throttle to max 10 events/second per run

Run this script to verify the feature is implemented correctly.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def print_step(step_num: int, description: str):
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print('='*60)


def print_check(passed: bool, description: str):
    """Print a check result."""
    status = "PASS" if passed else "FAIL"
    symbol = "[+]" if passed else "[-]"
    print(f"  {symbol} {status}: {description}")
    return passed


async def verify_step1_filter_significant_events():
    """Step 1: Filter events to only broadcast significant types."""
    print_step(1, "Filter events to only broadcast significant types")

    from server.event_broadcaster import (
        AgentEventBroadcaster,
        SIGNIFICANT_EVENT_TYPES,
    )

    passed = True

    # Check significant types are correct
    expected = {"tool_call", "turn_complete", "acceptance_check"}
    passed &= print_check(
        SIGNIFICANT_EVENT_TYPES == expected,
        f"SIGNIFICANT_EVENT_TYPES = {expected}"
    )

    broadcaster = AgentEventBroadcaster("test-project")

    # Test significant events
    for event_type in ["tool_call", "turn_complete", "acceptance_check"]:
        is_sig = broadcaster._is_significant_event(event_type)
        passed &= print_check(
            is_sig is True,
            f"'{event_type}' is significant (returns True)"
        )

    # Test non-significant events
    for event_type in ["started", "tool_result", "completed", "failed", "paused", "resumed"]:
        is_sig = broadcaster._is_significant_event(event_type)
        passed &= print_check(
            is_sig is False,
            f"'{event_type}' is NOT significant (returns False)"
        )

    # Test filtering in broadcast
    from unittest.mock import AsyncMock

    broadcaster2 = AgentEventBroadcaster("test-project")
    callback = AsyncMock()
    broadcaster2.set_broadcast_callback(callback)

    # Non-significant event should not be broadcast
    result = await broadcaster2.broadcast_event("run-1", "started", 1)
    passed &= print_check(
        result is False and callback.call_count == 0,
        "Non-significant event 'started' not broadcast"
    )

    # Significant event should be broadcast
    result = await broadcaster2.broadcast_event("run-1", "tool_call", 1, "Read")
    passed &= print_check(
        result is True and callback.call_count == 1,
        "Significant event 'tool_call' was broadcast"
    )

    return passed


async def verify_step2_message_type():
    """Step 2: Message type: agent_event_logged."""
    print_step(2, "Message type: agent_event_logged")

    from server.event_broadcaster import AgentEventBroadcaster
    from unittest.mock import AsyncMock

    passed = True

    broadcaster = AgentEventBroadcaster("test-project")
    callback = AsyncMock()
    broadcaster.set_broadcast_callback(callback)

    await broadcaster.broadcast_event("run-1", "tool_call", 1, "Read")

    message = callback.call_args[0][0]

    passed &= print_check(
        "type" in message,
        "Message has 'type' field"
    )

    passed &= print_check(
        message["type"] == "agent_event_logged",
        f"Message type is 'agent_event_logged' (got: {message.get('type')})"
    )

    return passed


async def verify_step3_payload_format():
    """Step 3: Payload: run_id, event_type, sequence."""
    print_step(3, "Payload: run_id, event_type, sequence")

    from server.event_broadcaster import AgentEventBroadcaster
    from unittest.mock import AsyncMock

    passed = True

    broadcaster = AgentEventBroadcaster("test-project")
    callback = AsyncMock()
    broadcaster.set_broadcast_callback(callback)

    test_time = datetime(2026, 1, 27, 12, 30, 45)
    await broadcaster.broadcast_event(
        run_id="run-abc-123",
        event_type="turn_complete",
        sequence=42,
        timestamp=test_time
    )

    message = callback.call_args[0][0]

    # Check required fields
    passed &= print_check(
        "run_id" in message,
        "Payload has 'run_id' field"
    )
    passed &= print_check(
        message.get("run_id") == "run-abc-123",
        f"run_id = 'run-abc-123' (got: {message.get('run_id')})"
    )

    passed &= print_check(
        "event_type" in message,
        "Payload has 'event_type' field"
    )
    passed &= print_check(
        message.get("event_type") == "turn_complete",
        f"event_type = 'turn_complete' (got: {message.get('event_type')})"
    )

    passed &= print_check(
        "sequence" in message,
        "Payload has 'sequence' field"
    )
    passed &= print_check(
        message.get("sequence") == 42,
        f"sequence = 42 (got: {message.get('sequence')})"
    )

    passed &= print_check(
        "timestamp" in message,
        "Payload has 'timestamp' field"
    )
    passed &= print_check(
        message.get("timestamp") == "2026-01-27T12:30:45",
        f"timestamp is ISO format (got: {message.get('timestamp')})"
    )

    return passed


async def verify_step4_tool_name_if_applicable():
    """Step 4: tool_name included if applicable."""
    print_step(4, "tool_name (if applicable)")

    from server.event_broadcaster import AgentEventBroadcaster
    from unittest.mock import AsyncMock

    passed = True

    broadcaster = AgentEventBroadcaster("test-project")
    callback = AsyncMock()
    broadcaster.set_broadcast_callback(callback)

    # Test with tool_name
    await broadcaster.broadcast_event("run-1", "tool_call", 1, tool_name="Bash")
    message = callback.call_args[0][0]

    passed &= print_check(
        "tool_name" in message,
        "tool_call event includes 'tool_name' field"
    )
    passed &= print_check(
        message.get("tool_name") == "Bash",
        f"tool_name = 'Bash' (got: {message.get('tool_name')})"
    )

    # Test without tool_name
    callback.reset_mock()
    await broadcaster.broadcast_event("run-1", "turn_complete", 2)
    message = callback.call_args[0][0]

    passed &= print_check(
        "tool_name" not in message,
        "turn_complete event does NOT include 'tool_name' field"
    )

    # Test acceptance_check without tool_name
    callback.reset_mock()
    await broadcaster.broadcast_event("run-1", "acceptance_check", 3)
    message = callback.call_args[0][0]

    passed &= print_check(
        "tool_name" not in message,
        "acceptance_check event does NOT include 'tool_name' field"
    )

    return passed


async def verify_step5_throttling():
    """Step 5: Throttle to max 10 events/second per run."""
    print_step(5, "Throttle to max 10 events/second per run")

    from server.event_broadcaster import (
        AgentEventBroadcaster,
        MAX_EVENTS_PER_SECOND,
        THROTTLE_WINDOW_SECONDS,
    )
    from unittest.mock import AsyncMock

    passed = True

    # Check constants
    passed &= print_check(
        MAX_EVENTS_PER_SECOND == 10,
        f"MAX_EVENTS_PER_SECOND = 10 (got: {MAX_EVENTS_PER_SECOND})"
    )
    passed &= print_check(
        THROTTLE_WINDOW_SECONDS == 1.0,
        f"THROTTLE_WINDOW_SECONDS = 1.0 (got: {THROTTLE_WINDOW_SECONDS})"
    )

    broadcaster = AgentEventBroadcaster("test-project")
    callback = AsyncMock()
    broadcaster.set_broadcast_callback(callback)

    # Send 10 events (all should pass)
    events_passed = 0
    for i in range(10):
        result = await broadcaster.broadcast_event(
            run_id="run-1",
            event_type="tool_call",
            sequence=i + 1,
            tool_name=f"Tool{i}"
        )
        if result:
            events_passed += 1

    passed &= print_check(
        events_passed == 10,
        f"10 events allowed per second ({events_passed}/10 passed)"
    )
    passed &= print_check(
        callback.call_count == 10,
        f"Callback called 10 times (actual: {callback.call_count})"
    )

    # 11th event should be throttled
    result = await broadcaster.broadcast_event(
        run_id="run-1",
        event_type="tool_call",
        sequence=11,
        tool_name="Tool11"
    )

    passed &= print_check(
        result is False,
        "11th event was throttled (returned False)"
    )
    passed &= print_check(
        callback.call_count == 10,
        f"Callback still at 10 (actual: {callback.call_count})"
    )

    # Test different runs are independent
    result = await broadcaster.broadcast_event(
        run_id="run-2",  # Different run
        event_type="tool_call",
        sequence=1,
        tool_name="Tool1"
    )

    passed &= print_check(
        result is True,
        "Different run (run-2) not throttled by run-1's limit"
    )

    return passed


async def verify_websocket_integration():
    """Verify websocket.py imports the event broadcaster."""
    print_step(6, "WebSocket Integration Check")

    passed = True

    # Check that websocket.py imports the event broadcaster
    websocket_path = ROOT / "server" / "websocket.py"
    content = websocket_path.read_text()

    passed &= print_check(
        "from .event_broadcaster import get_event_broadcaster" in content,
        "websocket.py imports get_event_broadcaster"
    )

    passed &= print_check(
        "get_event_broadcaster" in content,
        "websocket.py uses get_event_broadcaster"
    )

    passed &= print_check(
        "set_broadcast_callback" in content,
        "websocket.py sets broadcast callback"
    )

    passed &= print_check(
        "agent_event_logged" in content or "event_broadcaster" in content,
        "websocket.py integrates event broadcasting"
    )

    return passed


async def main():
    """Run all verification steps."""
    print("Feature #62 Verification: WebSocket agent_event_logged Event")
    print("=" * 60)

    all_passed = True

    # Run verification steps
    all_passed &= await verify_step1_filter_significant_events()
    all_passed &= await verify_step2_message_type()
    all_passed &= await verify_step3_payload_format()
    all_passed &= await verify_step4_tool_name_if_applicable()
    all_passed &= await verify_step5_throttling()
    all_passed &= await verify_websocket_integration()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if all_passed:
        print("\n[+] ALL VERIFICATION STEPS PASSED")
        print("    Feature #62 is correctly implemented.")
        return 0
    else:
        print("\n[-] SOME VERIFICATION STEPS FAILED")
        print("    Please review the failures above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
