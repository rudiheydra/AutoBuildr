#!/usr/bin/env python3
"""
Verification Script for Feature #47: Forbidden Tools Explicit Blocking
=======================================================================

This script verifies all 5 feature steps as described in the feature specification:

1. Extract forbidden_tools from spec.tool_policy
2. After filtering by allowed_tools, also remove forbidden_tools
3. Block any tool call to forbidden tool
4. Record policy violation event
5. Return clear error message to agent

Run with: python -m tests.verify_feature_47
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    generate_uuid,
)
from api.tool_policy import (
    ForbiddenToolBlocked,
    extract_forbidden_tools,
    create_forbidden_tools_violation,
    record_forbidden_tools_violation,
    ToolPolicyEnforcer,
    ToolCallBlocked,
    VIOLATION_TYPES,
)


def print_step(step_num: int, description: str) -> None:
    """Print a step header."""
    print(f"\n{'=' * 70}")
    print(f"Step {step_num}: {description}")
    print('=' * 70)


def print_check(description: str, passed: bool) -> None:
    """Print a check result."""
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    print(f"  {symbol} {description} - {status}")


def main() -> int:
    """Run all verification steps."""
    print("\n" + "=" * 70)
    print("Feature #47: Forbidden Tools Explicit Blocking - Verification")
    print("=" * 70)

    all_passed = True
    checks = []

    # ==========================================================================
    # Step 1: Extract forbidden_tools from spec.tool_policy
    # ==========================================================================
    print_step(1, "Extract forbidden_tools from spec.tool_policy")

    # Test basic extraction
    policy1 = {
        "allowed_tools": ["Read", "Write"],
        "forbidden_tools": ["Bash", "shell", "exec"],
    }
    result1 = extract_forbidden_tools(policy1)
    check1 = result1 == ["Bash", "shell", "exec"]
    print_check("Extract from valid policy returns correct list", check1)
    checks.append(check1)

    # Test None policy
    result2 = extract_forbidden_tools(None)
    check2 = result2 == []
    print_check("None policy returns empty list", check2)
    checks.append(check2)

    # Test missing key
    result3 = extract_forbidden_tools({"allowed_tools": ["Read"]})
    check3 = result3 == []
    print_check("Missing forbidden_tools key returns empty list", check3)
    checks.append(check3)

    # Test empty list
    result4 = extract_forbidden_tools({"forbidden_tools": []})
    check4 = result4 == []
    print_check("Empty forbidden_tools returns empty list", check4)
    checks.append(check4)

    # Test filtering non-strings
    result5 = extract_forbidden_tools({"forbidden_tools": ["Bash", 123, None, "shell"]})
    check5 = result5 == ["Bash", "shell"]
    print_check("Non-string entries are filtered out", check5)
    checks.append(check5)

    # ==========================================================================
    # Step 2: After filtering by allowed_tools, also remove forbidden_tools
    # ==========================================================================
    print_step(2, "After filtering by allowed_tools, also remove forbidden_tools")

    # Tool in both allowed and forbidden should be blocked
    enforcer1 = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={
            "allowed_tools": ["Read", "Write", "Bash"],  # Bash allowed
            "forbidden_tools": ["Bash"],  # But also forbidden
        },
    )

    # Read should work
    try:
        enforcer1.validate_tool_call("Read", {"path": "/test.txt"})
        check6 = True
    except Exception:
        check6 = False
    print_check("Allowed and not forbidden tool passes", check6)
    checks.append(check6)

    # Bash should be blocked (forbidden takes precedence)
    try:
        enforcer1.validate_tool_call("Bash", {"command": "ls"})
        check7 = False  # Should have raised
    except ForbiddenToolBlocked:
        check7 = True
    except Exception:
        check7 = False
    print_check("Forbidden tool blocked even if in allowed_tools", check7)
    checks.append(check7)

    # ==========================================================================
    # Step 3: Block any tool call to forbidden tool
    # ==========================================================================
    print_step(3, "Block any tool call to forbidden tool")

    enforcer2 = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={"forbidden_tools": ["dangerous_tool", "unsafe_tool"]},
    )

    # Test blocking
    try:
        enforcer2.validate_tool_call("dangerous_tool", {"arg": "value"})
        check8 = False
    except ForbiddenToolBlocked as e:
        check8 = e.tool_name == "dangerous_tool"
    except Exception:
        check8 = False
    print_check("ForbiddenToolBlocked raised for forbidden tool", check8)
    checks.append(check8)

    # Test multiple forbidden tools
    blocked_count = 0
    for tool in ["dangerous_tool", "unsafe_tool"]:
        try:
            enforcer2.validate_tool_call(tool, {})
        except ForbiddenToolBlocked:
            blocked_count += 1
    check9 = blocked_count == 2
    print_check("All forbidden tools are blocked", check9)
    checks.append(check9)

    # Test non-forbidden tool passes
    try:
        enforcer2.validate_tool_call("safe_tool", {})
        check10 = True
    except Exception:
        check10 = False
    print_check("Non-forbidden tool passes validation", check10)
    checks.append(check10)

    # ==========================================================================
    # Step 4: Record policy violation event
    # ==========================================================================
    print_step(4, "Record policy violation event")

    # Check violation type is in list
    check11 = "forbidden_tools" in VIOLATION_TYPES
    print_check("'forbidden_tools' in VIOLATION_TYPES", check11)
    checks.append(check11)

    # Create violation object
    violation = create_forbidden_tools_violation(
        tool_name="Bash",
        turn_number=5,
        forbidden_tools=["Bash", "shell"],
    )
    check12 = violation.violation_type == "forbidden_tools"
    print_check("PolicyViolation has correct violation_type", check12)
    checks.append(check12)

    check13 = violation.tool_name == "Bash"
    print_check("PolicyViolation has correct tool_name", check13)
    checks.append(check13)

    check14 = violation.turn_number == 5
    print_check("PolicyViolation has correct turn_number", check14)
    checks.append(check14)

    check15 = violation.details["blocked_tool"] == "Bash"
    print_check("PolicyViolation details include blocked_tool", check15)
    checks.append(check15)

    # Test database recording
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec",
        display_name="Test",
        objective="Test",
        task_type="coding",
        tool_policy={"forbidden_tools": ["Bash"]},
        max_turns=50,
        timeout_seconds=1800,
    )
    session.add(spec)
    session.commit()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="running",
        turns_used=5,
    )
    session.add(run)
    session.commit()

    event = record_forbidden_tools_violation(
        db=session,
        run_id=run.id,
        sequence=1,
        tool_name="Bash",
        turn_number=5,
        forbidden_tools=["Bash"],
    )
    session.commit()

    check16 = event.event_type == "policy_violation"
    print_check("Event recorded with event_type='policy_violation'", check16)
    checks.append(check16)

    check17 = event.payload["violation_type"] == "forbidden_tools"
    print_check("Event payload has correct violation_type", check17)
    checks.append(check17)

    session.close()

    # ==========================================================================
    # Step 5: Return clear error message to agent
    # ==========================================================================
    print_step(5, "Return clear error message to agent")

    enforcer3 = ToolPolicyEnforcer.from_tool_policy(
        spec_id="test",
        tool_policy={"forbidden_tools": ["Bash"]},
    )

    try:
        enforcer3.validate_tool_call("Bash", {"command": "ls"})
        exception_message = None
    except ForbiddenToolBlocked as e:
        exception_message = str(e)

    check18 = exception_message is not None and "Bash" in exception_message
    print_check("Exception message mentions tool name", check18)
    checks.append(check18)

    check19 = exception_message is not None and (
        "blocked" in exception_message.lower() or "forbidden" in exception_message.lower()
    )
    print_check("Exception message indicates blocking", check19)
    checks.append(check19)

    # Test error message method
    error_msg = enforcer3.get_forbidden_tool_error_message("Bash")
    check20 = "Bash" in error_msg and "blocked" in error_msg.lower()
    print_check("get_forbidden_tool_error_message returns clear message", check20)
    checks.append(check20)

    # Test check_tool_call returns error
    allowed, pattern, error = enforcer3.check_tool_call("Bash", {})
    check21 = not allowed and pattern == "[forbidden_tool]" and error is not None
    print_check("check_tool_call returns error without raising", check21)
    checks.append(check21)

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(checks)
    total = len(checks)
    all_passed = all(checks)

    print(f"\nChecks passed: {passed}/{total}")
    print(f"Overall status: {'PASS' if all_passed else 'FAIL'}")

    if all_passed:
        print("\n✓ Feature #47: Forbidden Tools Explicit Blocking - VERIFIED")
    else:
        print("\n✗ Feature #47: Forbidden Tools Explicit Blocking - FAILED")
        print("\nFailed checks:")
        check_names = [
            "Extract from valid policy",
            "None policy returns empty",
            "Missing key returns empty",
            "Empty list returns empty",
            "Non-strings filtered",
            "Allowed non-forbidden passes",
            "Forbidden overrides allowed",
            "ForbiddenToolBlocked raised",
            "All forbidden blocked",
            "Non-forbidden passes",
            "VIOLATION_TYPES includes forbidden_tools",
            "Violation type correct",
            "Tool name correct",
            "Turn number correct",
            "Details include blocked_tool",
            "Event type correct",
            "Payload violation_type correct",
            "Message mentions tool",
            "Message indicates blocking",
            "Error message method works",
            "check_tool_call returns error",
        ]
        for i, (check, name) in enumerate(zip(checks, check_names), 1):
            if not check:
                print(f"  - Check {i}: {name}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
