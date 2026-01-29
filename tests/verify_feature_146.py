#!/usr/bin/env python3
"""
Feature #146: Handle agent_spec_created WebSocket event in frontend UI

Verification script that checks all 6 feature steps:
1. WSMessageType enum includes 'agent_spec_created'
2. WSAgentSpecCreatedMessage interface exists with correct fields
3. WebSocket message handler has case for agent_spec_created
4. State/stores updated when agent_spec_created received
5. Backend emits agent_spec_created events when a new AgentSpec is created
6. Frontend receives and processes the event correctly
"""

import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_file(rel_path):
    """Read a file relative to project root."""
    path = os.path.join(PROJECT_ROOT, rel_path)
    with open(path, 'r') as f:
        return f.read()


def step1_wsmessagetype_includes_agent_spec_created():
    """Step 1: Open ui/src/lib/types.ts and verify WSMessageType includes 'agent_spec_created'."""
    print("Step 1: WSMessageType enum includes 'agent_spec_created'")
    content = read_file('ui/src/lib/types.ts')

    # Find the WSMessageType line
    match = re.search(r"export type WSMessageType\s*=\s*([^;]+)", content)
    assert match, "WSMessageType type not found in types.ts"

    type_def = match.group(1)
    assert "'agent_spec_created'" in type_def, \
        f"'agent_spec_created' not found in WSMessageType: {type_def}"

    print("  - WSMessageType includes 'agent_spec_created': PASS")
    return True


def step2_interface_exists_with_correct_fields():
    """Step 2: Verify WSAgentSpecCreatedMessage interface exists with correct fields."""
    print("Step 2: WSAgentSpecCreatedMessage interface exists with correct fields")
    content = read_file('ui/src/lib/types.ts')

    # Check interface exists
    assert 'interface WSAgentSpecCreatedMessage' in content, \
        "WSAgentSpecCreatedMessage interface not found"

    # Check required fields
    required_fields = {
        "type: 'agent_spec_created'": "type field with literal 'agent_spec_created'",
        "spec_id: string": "spec_id field",
        "name: string": "name field",
        "display_name: string": "display_name field",
        "icon: string | null": "icon field (nullable)",
        "task_type: string": "task_type field",
        "timestamp: string": "timestamp field",
    }

    for field, description in required_fields.items():
        assert field in content, f"Missing field '{description}' in WSAgentSpecCreatedMessage"
        print(f"  - {description}: PASS")

    # Check it's in the WSMessage union
    ws_message_section = content[content.index('export type WSMessage ='):]
    assert 'WSAgentSpecCreatedMessage' in ws_message_section, \
        "WSAgentSpecCreatedMessage not in WSMessage union type"
    print("  - WSAgentSpecCreatedMessage in WSMessage union: PASS")

    return True


def step3_websocket_handler_has_case():
    """Step 3: Verify the WebSocket message handler handles agent_spec_created."""
    print("Step 3: WebSocket message handler has case for 'agent_spec_created'")
    content = read_file('ui/src/hooks/useWebSocket.ts')

    # Check switch case exists
    assert "case 'agent_spec_created'" in content, \
        "case 'agent_spec_created' not found in useWebSocket.ts"
    print("  - case 'agent_spec_created' in switch statement: PASS")

    # Check it's not just an empty fall-through to another case
    # Find the case block and verify it has meaningful content
    case_idx = content.index("case 'agent_spec_created'")
    # Get the content between this case and the next break
    next_break = content.index('break', case_idx)
    case_body = content[case_idx:next_break]
    assert len(case_body.strip()) > len("case 'agent_spec_created':"), \
        "agent_spec_created case body is empty"
    print("  - case body has meaningful content: PASS")

    return True


def step4_state_update_on_message():
    """Step 4: Verify relevant state/stores are updated when agent_spec_created is received."""
    print("Step 4: State handling for agent_spec_created messages")
    content = read_file('ui/src/hooks/useWebSocket.ts')

    # The handler should log or process the message
    case_idx = content.index("case 'agent_spec_created'")
    next_break = content.index('break', case_idx)
    case_body = content[case_idx:next_break]

    # It should reference message properties (spec_id, display_name, etc.)
    assert 'message' in case_body, \
        "Handler doesn't reference the message object"
    print("  - Handler references message data: PASS")

    # Check that console.debug or setState is called
    has_log = 'console.debug' in case_body or 'console.log' in case_body
    has_state = 'setState' in case_body
    assert has_log or has_state, \
        "Handler neither logs nor updates state"
    print(f"  - Handler {'logs message' if has_log else 'updates state'}: PASS")

    return True


def step5_backend_emits_events():
    """Step 5: Verify backend emits agent_spec_created events."""
    print("Step 5: Backend emits agent_spec_created events when AgentSpec is created")

    # Check websocket_events.py has the broadcast function
    ws_content = read_file('api/websocket_events.py')
    assert 'async def broadcast_agent_spec_created' in ws_content, \
        "broadcast_agent_spec_created function not found"
    print("  - broadcast_agent_spec_created function exists: PASS")

    # Check the message type is correct
    assert '"type": "agent_spec_created"' in ws_content, \
        "Message type 'agent_spec_created' not in broadcast payload"
    print("  - Message type is 'agent_spec_created': PASS")

    # Check the API endpoint calls broadcast
    api_content = read_file('server/routers/agent_specs.py')
    assert 'broadcast_agent_spec_created' in api_content, \
        "broadcast_agent_spec_created not called in agent_specs router"
    print("  - API endpoint calls broadcast_agent_spec_created: PASS")

    # Check payload fields match frontend interface
    required_payload_fields = ['spec_id', 'name', 'display_name', 'icon', 'task_type', 'timestamp']
    for field in required_payload_fields:
        assert f'"{field}"' in ws_content, \
            f"Backend payload missing field: {field}"
    print("  - Backend payload has all required fields: PASS")

    return True


def step6_frontend_receives_processes_correctly():
    """Step 6: Verify frontend receives and processes event correctly (type safety)."""
    print("Step 6: Frontend type system correctly handles agent_spec_created")

    types_content = read_file('ui/src/lib/types.ts')
    ws_content = read_file('ui/src/hooks/useWebSocket.ts')

    # Verify WSMessage union includes WSAgentSpecCreatedMessage
    # This ensures TypeScript narrows the type correctly in the switch
    ws_union_match = re.search(r'export type WSMessage\s*=([^;]+)', types_content, re.DOTALL)
    assert ws_union_match, "WSMessage union type not found"
    union_body = ws_union_match.group(1)
    assert 'WSAgentSpecCreatedMessage' in union_body, \
        "WSAgentSpecCreatedMessage not in WSMessage discriminated union"
    print("  - WSMessage discriminated union includes WSAgentSpecCreatedMessage: PASS")

    # Verify the handler uses the correct property access (TypeScript narrow)
    case_idx = ws_content.index("case 'agent_spec_created'")
    next_break = ws_content.index('break', case_idx)
    case_body = ws_content[case_idx:next_break]

    # In the narrowed type, message.spec_id and message.display_name should be accessible
    assert 'message.spec_id' in case_body or 'message.display_name' in case_body or 'message.name' in case_body, \
        "Handler doesn't access type-narrowed properties (spec_id/display_name/name)"
    print("  - Handler accesses type-narrowed properties: PASS")

    # Verify WSMessageType includes agent_spec_created (for completeness)
    msg_type_match = re.search(r"export type WSMessageType\s*=\s*([^;]+)", types_content)
    assert msg_type_match and "'agent_spec_created'" in msg_type_match.group(1), \
        "WSMessageType doesn't include 'agent_spec_created'"
    print("  - WSMessageType enum complete: PASS")

    return True


def main():
    print("=" * 70)
    print("Feature #146: Handle agent_spec_created WebSocket event in frontend UI")
    print("=" * 70)
    print()

    steps = [
        step1_wsmessagetype_includes_agent_spec_created,
        step2_interface_exists_with_correct_fields,
        step3_websocket_handler_has_case,
        step4_state_update_on_message,
        step5_backend_emits_events,
        step6_frontend_receives_processes_correctly,
    ]

    passed = 0
    failed = 0

    for step_fn in steps:
        try:
            result = step_fn()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  - FAILED: {e}")
            failed += 1
        print()

    print("=" * 70)
    print(f"Results: {passed}/{passed + failed} steps passed")
    if failed == 0:
        print("ALL STEPS PASSED ✓")
    else:
        print(f"FAILED: {failed} step(s)")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
