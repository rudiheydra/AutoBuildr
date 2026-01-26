#!/usr/bin/env python3
"""
Verification Script for Feature #41: ToolPolicy Forbidden Patterns Enforcement

This script verifies all 8 implementation steps of the feature:
1. Extract forbidden_patterns from spec.tool_policy
2. Compile patterns as regex at spec load time
3. Before each tool call, serialize arguments to string
4. Check arguments against all forbidden patterns
5. If pattern matches, block tool call
6. Record tool_call event with blocked=true and pattern matched
7. Return error to agent explaining blocked operation
8. Continue execution (do not abort run)

Run this script to verify the feature implementation:
    python tests/verify_feature_41.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.tool_policy import (
    CompiledPattern,
    PatternCompilationError,
    ToolCallBlocked,
    ToolPolicyEnforcer,
    check_arguments_against_patterns,
    compile_forbidden_patterns,
    create_enforcer_for_run,
    extract_forbidden_patterns,
    record_blocked_tool_call_event,
    serialize_tool_arguments,
)


def print_step(step_num: int, description: str):
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print('='*60)


def print_result(passed: bool, message: str):
    """Print a test result."""
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {message}")
    return passed


def verify_step_1():
    """Step 1: Extract forbidden_patterns from spec.tool_policy"""
    print_step(1, "Extract forbidden_patterns from spec.tool_policy")

    all_passed = True

    # Test 1: Valid policy
    policy = {
        "policy_version": "v1",
        "allowed_tools": ["feature_mark_passing"],
        "forbidden_patterns": ["rm -rf", "DROP TABLE"],
    }
    result = extract_forbidden_patterns(policy)
    passed = result == ["rm -rf", "DROP TABLE"]
    all_passed &= print_result(passed, f"Extract from valid policy: {result}")

    # Test 2: None policy
    result = extract_forbidden_patterns(None)
    passed = result == []
    all_passed &= print_result(passed, f"Handle None policy: {result}")

    # Test 3: Empty policy
    result = extract_forbidden_patterns({})
    passed = result == []
    all_passed &= print_result(passed, f"Handle empty policy: {result}")

    # Test 4: Missing key
    result = extract_forbidden_patterns({"allowed_tools": ["x"]})
    passed = result == []
    all_passed &= print_result(passed, f"Handle missing key: {result}")

    return all_passed


def verify_step_2():
    """Step 2: Compile patterns as regex at spec load time"""
    print_step(2, "Compile patterns as regex at spec load time")

    all_passed = True

    # Test 1: Compile valid patterns
    patterns = ["rm -rf", "DROP TABLE", r"\bpassword\b"]
    compiled = compile_forbidden_patterns(patterns)
    passed = len(compiled) == 3 and all(isinstance(p, CompiledPattern) for p in compiled)
    all_passed &= print_result(passed, f"Compile {len(patterns)} patterns: {len(compiled)} compiled")

    # Test 2: Case insensitive matching
    compiled = compile_forbidden_patterns(["DROP TABLE"])
    match_upper = compiled[0].regex.search("DROP TABLE users")
    match_lower = compiled[0].regex.search("drop table users")
    passed = match_upper is not None and match_lower is not None
    all_passed &= print_result(passed, "Case insensitive matching works")

    # Test 3: Invalid pattern in non-strict mode is skipped
    compiled = compile_forbidden_patterns(["valid", "[invalid("], strict=False)
    passed = len(compiled) == 1
    all_passed &= print_result(passed, f"Skip invalid pattern in non-strict mode: {len(compiled)} compiled")

    # Test 4: Invalid pattern in strict mode raises error
    try:
        compile_forbidden_patterns(["[invalid("], strict=True)
        passed = False
    except PatternCompilationError:
        passed = True
    all_passed &= print_result(passed, "Raise error for invalid pattern in strict mode")

    return all_passed


def verify_step_3():
    """Step 3: Before each tool call, serialize arguments to string"""
    print_step(3, "Serialize arguments to string")

    all_passed = True

    # Test 1: Simple dict
    args = {"command": "ls -la", "timeout": 30}
    result = serialize_tool_arguments(args)
    passed = '"command"' in result and '"ls -la"' in result
    all_passed &= print_result(passed, f"Serialize simple dict")

    # Test 2: Nested structures
    args = {"config": {"user": "admin"}, "options": ["a", "b"]}
    result = serialize_tool_arguments(args)
    passed = "admin" in result and '["a", "b"]' in result
    all_passed &= print_result(passed, "Serialize nested structures")

    # Test 3: None returns empty
    result = serialize_tool_arguments(None)
    passed = result == ""
    all_passed &= print_result(passed, f"None returns empty: '{result}'")

    # Test 4: JSON format for easy regex matching
    args = {"query": "SELECT * FROM users"}
    result = serialize_tool_arguments(args)
    try:
        parsed = json.loads(result)
        passed = parsed["query"] == "SELECT * FROM users"
    except json.JSONDecodeError:
        passed = False
    all_passed &= print_result(passed, "Valid JSON format for regex matching")

    return all_passed


def verify_step_4():
    """Step 4: Check arguments against all forbidden patterns"""
    print_step(4, "Check arguments against all forbidden patterns")

    all_passed = True

    # Test 1: Match found
    patterns = compile_forbidden_patterns(["rm -rf", "DROP TABLE"])
    serialized = '{"command": "rm -rf /home/user"}'
    result = check_arguments_against_patterns(serialized, patterns)
    passed = result is not None and result.original == "rm -rf"
    all_passed &= print_result(passed, f"Pattern match found: {result.original if result else None}")

    # Test 2: No match
    serialized = '{"command": "ls -la"}'
    result = check_arguments_against_patterns(serialized, patterns)
    passed = result is None
    all_passed &= print_result(passed, "No match for safe command")

    # Test 3: First match returned
    patterns = compile_forbidden_patterns(["aaa", "bbb", "ccc"])
    serialized = '{"value": "bbb then aaa"}'
    result = check_arguments_against_patterns(serialized, patterns)
    # aaa comes first in pattern list, even though bbb appears first in string
    passed = result is not None and result.original == "aaa"
    all_passed &= print_result(passed, f"First pattern in list that matches: {result.original if result else None}")

    return all_passed


def verify_step_5():
    """Step 5: If pattern matches, block tool call"""
    print_step(5, "Block tool call if pattern matches")

    all_passed = True

    # Test 1: Block by pattern
    enforcer = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={
            "allowed_tools": ["bash"],
            "forbidden_patterns": ["rm -rf"],
        }
    )

    try:
        enforcer.validate_tool_call("bash", {"command": "rm -rf /home"})
        passed = False
        error = None
    except ToolCallBlocked as e:
        passed = True
        error = e

    all_passed &= print_result(passed, f"Tool call blocked by pattern: {error.pattern_matched if error else 'N/A'}")

    # Test 2: Block by not in allowed_tools
    enforcer = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={
            "allowed_tools": ["tool1", "tool2"],
            "forbidden_patterns": [],
        }
    )

    try:
        enforcer.validate_tool_call("unauthorized", {})
        passed = False
    except ToolCallBlocked as e:
        passed = "not_in_allowed_tools" in e.pattern_matched

    all_passed &= print_result(passed, "Tool call blocked when not in allowed_tools")

    # Test 3: Safe call passes
    enforcer = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={
            "allowed_tools": ["safe_tool"],
            "forbidden_patterns": ["dangerous"],
        }
    )

    try:
        enforcer.validate_tool_call("safe_tool", {"cmd": "safe_operation"})
        passed = True
    except ToolCallBlocked:
        passed = False

    all_passed &= print_result(passed, "Safe tool call passes validation")

    return all_passed


def verify_step_6():
    """Step 6: Record tool_call event with blocked=true and pattern matched"""
    print_step(6, "Record blocked tool_call event")

    all_passed = True

    # Create mock database session
    mock_db = MagicMock()

    # Record event
    event = record_blocked_tool_call_event(
        db=mock_db,
        run_id="run-12345",
        sequence=5,
        tool_name="dangerous_bash",
        arguments={"command": "rm -rf /"},
        pattern_matched="rm -rf",
    )

    # Verify event was added to session
    passed = mock_db.add.called
    all_passed &= print_result(passed, "Event added to database session")

    # Verify event fields
    passed = event.run_id == "run-12345"
    all_passed &= print_result(passed, f"Event run_id: {event.run_id}")

    passed = event.sequence == 5
    all_passed &= print_result(passed, f"Event sequence: {event.sequence}")

    passed = event.event_type == "tool_call"
    all_passed &= print_result(passed, f"Event type: {event.event_type}")

    passed = event.tool_name == "dangerous_bash"
    all_passed &= print_result(passed, f"Event tool_name: {event.tool_name}")

    # Verify payload
    passed = event.payload.get("blocked") is True
    all_passed &= print_result(passed, f"Payload blocked=true: {event.payload.get('blocked')}")

    passed = event.payload.get("pattern_matched") == "rm -rf"
    all_passed &= print_result(passed, f"Payload pattern_matched: {event.payload.get('pattern_matched')}")

    passed = event.timestamp is not None
    all_passed &= print_result(passed, f"Event has timestamp: {event.timestamp}")

    return all_passed


def verify_step_7():
    """Step 7: Return error to agent explaining blocked operation"""
    print_step(7, "Return error message to agent")

    all_passed = True

    enforcer = ToolPolicyEnforcer(spec_id="test", forbidden_patterns=[])

    # Get error message
    message = enforcer.get_blocked_error_message("bash", "rm -rf")

    # Verify message content
    passed = "bash" in message
    all_passed &= print_result(passed, f"Message mentions tool name: 'bash'")

    passed = "rm -rf" in message
    all_passed &= print_result(passed, f"Message mentions pattern: 'rm -rf'")

    passed = "blocked" in message.lower()
    all_passed &= print_result(passed, "Message explains blocking")

    # Verify ToolCallBlocked exception message
    exc = ToolCallBlocked(
        tool_name="dangerous",
        pattern_matched="pattern",
        arguments={}
    )
    passed = "dangerous" in str(exc) and "pattern" in str(exc)
    all_passed &= print_result(passed, "ToolCallBlocked exception has descriptive message")

    print(f"\n  Sample error message:\n  {message}")

    return all_passed


def verify_step_8():
    """Step 8: Continue execution (do not abort run)"""
    print_step(8, "Continue execution after blocked call")

    all_passed = True

    enforcer = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={
            "allowed_tools": ["tool"],
            "forbidden_patterns": ["blocked_pattern"],
        }
    )

    # First call - blocked
    try:
        enforcer.validate_tool_call("tool", {"cmd": "blocked_pattern here"})
        first_blocked = False
    except ToolCallBlocked:
        first_blocked = True

    all_passed &= print_result(first_blocked, "First call blocked as expected")

    # Second call - should still work (execution continues)
    try:
        enforcer.validate_tool_call("tool", {"cmd": "safe_command"})
        second_passed = True
    except ToolCallBlocked:
        second_passed = False

    all_passed &= print_result(second_passed, "Second call passes - execution continues")

    # Third call - blocked again
    try:
        enforcer.validate_tool_call("tool", {"cmd": "another blocked_pattern"})
        third_blocked = False
    except ToolCallBlocked:
        third_blocked = True

    all_passed &= print_result(third_blocked, "Third call blocked again")

    # Fourth call - should still work
    try:
        enforcer.validate_tool_call("tool", {"cmd": "another safe command"})
        fourth_passed = True
    except ToolCallBlocked:
        fourth_passed = False

    all_passed &= print_result(fourth_passed, "Fourth call passes - enforcer still functional")

    # Test check_tool_call method (no exceptions)
    allowed, pattern, error = enforcer.check_tool_call("tool", {"cmd": "blocked_pattern"})
    passed = allowed is False and pattern is not None
    all_passed &= print_result(passed, "check_tool_call() returns tuple without raising")

    allowed, pattern, error = enforcer.check_tool_call("tool", {"cmd": "safe"})
    passed = allowed is True and pattern is None and error is None
    all_passed &= print_result(passed, "check_tool_call() returns (True, None, None) for allowed")

    return all_passed


def verify_integration():
    """Integration test with realistic scenarios."""
    print_step(9, "Integration: Real-world scenarios")

    all_passed = True

    # Create a realistic enforcer
    mock_spec = MagicMock()
    mock_spec.id = "coding-agent-spec-123"
    mock_spec.tool_policy = {
        "policy_version": "v1",
        "allowed_tools": [
            "Read", "Write", "Edit", "Glob", "Grep", "Bash",
            "feature_mark_passing", "feature_get_by_id"
        ],
        "forbidden_patterns": [
            r"rm\s+-rf",
            r"rm\s+--recursive",
            r"DROP\s+TABLE",
            r"DELETE\s+FROM",
            r"chmod\s+777",
            r">\s*/dev/",
        ],
        "tool_hints": {
            "feature_mark_passing": "Call only after verification"
        }
    }

    enforcer = create_enforcer_for_run(mock_spec)

    passed = enforcer.spec_id == "coding-agent-spec-123"
    all_passed &= print_result(passed, f"Created enforcer for spec: {enforcer.spec_id}")

    passed = enforcer.pattern_count == 6
    all_passed &= print_result(passed, f"Compiled {enforcer.pattern_count} patterns")

    # Test dangerous commands blocked
    dangerous = [
        ("Bash", {"command": "rm -rf /home"}),
        ("Bash", {"command": "rm --recursive --force /tmp"}),
        ("Bash", {"command": "chmod 777 /etc/passwd"}),
    ]

    for tool, args in dangerous:
        try:
            enforcer.validate_tool_call(tool, args)
            passed = False
        except ToolCallBlocked:
            passed = True
        all_passed &= print_result(passed, f"Blocked: {tool} with {args}")

    # Test safe commands allowed
    safe = [
        ("Bash", {"command": "ls -la"}),
        ("Bash", {"command": "git status"}),
        ("Read", {"file_path": "/home/user/code.py"}),
        ("feature_mark_passing", {"feature_id": 42}),
    ]

    for tool, args in safe:
        try:
            enforcer.validate_tool_call(tool, args)
            passed = True
        except ToolCallBlocked as e:
            passed = False
            print(f"    Unexpected block: {e}")
        all_passed &= print_result(passed, f"Allowed: {tool}")

    return all_passed


def main():
    """Run all verification steps."""
    print("="*60)
    print("Feature #41: ToolPolicy Forbidden Patterns Enforcement")
    print("Verification Script")
    print("="*60)

    results = []

    results.append(("Step 1: Extract forbidden_patterns", verify_step_1()))
    results.append(("Step 2: Compile patterns as regex", verify_step_2()))
    results.append(("Step 3: Serialize arguments", verify_step_3()))
    results.append(("Step 4: Check against patterns", verify_step_4()))
    results.append(("Step 5: Block matching calls", verify_step_5()))
    results.append(("Step 6: Record blocked events", verify_step_6()))
    results.append(("Step 7: Return error message", verify_step_7()))
    results.append(("Step 8: Continue execution", verify_step_8()))
    results.append(("Integration tests", verify_integration()))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        all_passed &= passed

    print("\n" + "="*60)
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED")
        print("="*60)
        return 0
    else:
        print("SOME VERIFICATION STEPS FAILED")
        print("="*60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
