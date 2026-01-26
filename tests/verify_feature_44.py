#!/usr/bin/env python
"""
Verification Script for Feature #44: Policy Violation Event Logging
=====================================================================

This script verifies all 6 steps of Feature #44:
1. Define policy_violation event type
2. When tool blocked by allowed_tools, record event
3. When tool blocked by forbidden_patterns, record pattern matched
4. When file operation blocked by sandbox, record attempted path
5. Include agent turn number in event for context
6. Aggregate violation count in run metadata

Run with: python tests/verify_feature_44.py
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    EVENT_TYPES,
    generate_uuid,
)
from api.tool_policy import (
    # Feature #44 exports
    PolicyViolation,
    ViolationAggregation,
    VIOLATION_TYPES,
    create_allowed_tools_violation,
    create_directory_sandbox_violation,
    create_forbidden_patterns_violation,
    get_violation_aggregation,
    record_allowed_tools_violation,
    record_and_aggregate_violation,
    record_directory_sandbox_violation,
    record_forbidden_patterns_violation,
    record_policy_violation_event,
    update_run_violation_metadata,
)


def setup_test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def create_test_run(session):
    """Create a test spec and run."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="coding",
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=50,
        timeout_seconds=1800,
    )
    session.add(spec)
    session.commit()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="running",
        turns_used=0,
    )
    session.add(run)
    session.commit()
    return run


def verify_step1():
    """Step 1: Define policy_violation event type."""
    print("\n=== Step 1: Define policy_violation event type ===")

    checks = [
        ("'policy_violation' is in EVENT_TYPES", "policy_violation" in EVENT_TYPES),
        ("VIOLATION_TYPES has 3 types", len(VIOLATION_TYPES) == 3),
        ("'allowed_tools' is a violation type", "allowed_tools" in VIOLATION_TYPES),
        ("'forbidden_patterns' is a violation type", "forbidden_patterns" in VIOLATION_TYPES),
        ("'directory_sandbox' is a violation type", "directory_sandbox" in VIOLATION_TYPES),
    ]

    all_passed = True
    for desc, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step2():
    """Step 2: When tool blocked by allowed_tools, record event."""
    print("\n=== Step 2: Record allowed_tools violation ===")

    session = setup_test_db()
    run = create_test_run(session)

    checks = []

    # Create violation
    violation = create_allowed_tools_violation(
        tool_name="Bash",
        turn_number=5,
        allowed_tools=["Read", "Write"],
        arguments={"command": "ls"},
    )

    checks.append(("Violation type is 'allowed_tools'", violation.violation_type == "allowed_tools"))
    checks.append(("Tool name is captured", violation.tool_name == "Bash"))
    checks.append(("Turn number is captured", violation.turn_number == 5))
    checks.append(("Blocked tool in details", violation.details["blocked_tool"] == "Bash"))
    checks.append(("Allowed tools in details", "Read" in violation.details["allowed_tools"]))

    # Record event
    event = record_allowed_tools_violation(
        session, run.id, 1, "Bash", 5, ["Read", "Write"], {"command": "ls"}
    )
    session.commit()

    checks.append(("Event type is 'policy_violation'", event.event_type == "policy_violation"))
    checks.append(("Payload has violation_type", event.payload["violation_type"] == "allowed_tools"))
    checks.append(("Payload has tool", event.payload["tool"] == "Bash"))

    session.close()

    all_passed = True
    for desc, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step3():
    """Step 3: When tool blocked by forbidden_patterns, record pattern matched."""
    print("\n=== Step 3: Record forbidden_patterns violation ===")

    session = setup_test_db()
    run = create_test_run(session)

    checks = []

    # Create violation
    violation = create_forbidden_patterns_violation(
        tool_name="Bash",
        turn_number=10,
        pattern_matched="rm -rf",
        arguments={"command": "rm -rf /"},
    )

    checks.append(("Violation type is 'forbidden_patterns'", violation.violation_type == "forbidden_patterns"))
    checks.append(("Pattern is captured in details", violation.details["pattern_matched"] == "rm -rf"))
    checks.append(("Pattern is in message", "rm -rf" in violation.message))

    # Record event
    event = record_forbidden_patterns_violation(
        session, run.id, 1, "Bash", 10, "rm -rf", {"command": "rm -rf /"}
    )
    session.commit()

    checks.append(("Event payload has pattern_matched", event.payload["details"]["pattern_matched"] == "rm -rf"))
    checks.append(("Event has correct violation_type", event.payload["violation_type"] == "forbidden_patterns"))

    session.close()

    all_passed = True
    for desc, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step4():
    """Step 4: When file operation blocked by sandbox, record attempted path."""
    print("\n=== Step 4: Record directory_sandbox violation ===")

    session = setup_test_db()
    run = create_test_run(session)

    checks = []

    # Create violation
    violation = create_directory_sandbox_violation(
        tool_name="write_file",
        turn_number=15,
        attempted_path="/etc/passwd",
        reason="Path is not within any allowed directory",
        allowed_directories=["/home/user/project"],
        was_symlink=False,
    )

    checks.append(("Violation type is 'directory_sandbox'", violation.violation_type == "directory_sandbox"))
    checks.append(("Attempted path is captured", violation.details["attempted_path"] == "/etc/passwd"))
    checks.append(("Reason is captured", "allowed directory" in violation.details["reason"].lower()))
    checks.append(("Allowed directories captured", len(violation.details["allowed_directories"]) > 0))
    checks.append(("was_symlink is captured", violation.details["was_symlink"] is False))

    # Record event
    event = record_directory_sandbox_violation(
        session, run.id, 1, "write_file", 15, "/etc/passwd",
        "Path is not within any allowed directory",
        ["/home/user/project"], False
    )
    session.commit()

    checks.append(("Event has attempted_path", event.payload["details"]["attempted_path"] == "/etc/passwd"))
    checks.append(("Event has correct violation_type", event.payload["violation_type"] == "directory_sandbox"))

    session.close()

    all_passed = True
    for desc, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step5():
    """Step 5: Include agent turn number in event for context."""
    print("\n=== Step 5: Turn number in event context ===")

    session = setup_test_db()
    run = create_test_run(session)

    checks = []

    # Test turn number in each violation type
    v1 = create_allowed_tools_violation("T1", 10, ["Read"])
    e1 = record_policy_violation_event(session, run.id, 1, v1)

    v2 = create_forbidden_patterns_violation("T2", 20, "pattern")
    e2 = record_policy_violation_event(session, run.id, 2, v2)

    v3 = create_directory_sandbox_violation("T3", 30, "/path", "reason", ["/dir"])
    e3 = record_policy_violation_event(session, run.id, 3, v3)

    session.commit()

    checks.append(("Turn number in allowed_tools event", e1.payload["turn_number"] == 10))
    checks.append(("Turn number in forbidden_patterns event", e2.payload["turn_number"] == 20))
    checks.append(("Turn number in directory_sandbox event", e3.payload["turn_number"] == 30))
    checks.append(("Turn number field exists in all events",
                   all("turn_number" in e.payload for e in [e1, e2, e3])))

    session.close()

    all_passed = True
    for desc, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step6():
    """Step 6: Aggregate violation count in run metadata."""
    print("\n=== Step 6: Aggregate violation count in run metadata ===")

    session = setup_test_db()
    run = create_test_run(session)

    checks = []

    # Test ViolationAggregation class
    agg = ViolationAggregation()
    agg.add_violation("allowed_tools", "Bash", 5)
    agg.add_violation("forbidden_patterns", "Bash", 10)
    agg.add_violation("allowed_tools", "Write", 15)

    checks.append(("Aggregation counts total", agg.total_count == 3))
    checks.append(("Aggregation counts by type", agg.by_type["allowed_tools"] == 2))
    checks.append(("Aggregation counts by tool", agg.by_tool["Bash"] == 2))
    checks.append(("Aggregation tracks last turn", agg.last_turn == 15))

    # Test serialization/deserialization
    data = agg.to_dict()
    agg2 = ViolationAggregation.from_dict(data)
    checks.append(("Aggregation round-trip works", agg2.total_count == 3))

    # Test update_run_violation_metadata
    v1 = create_allowed_tools_violation("T1", 5, ["Read"])
    result1 = update_run_violation_metadata(session, run.id, v1)
    checks.append(("First violation aggregated", result1["total_count"] == 1))

    v2 = create_forbidden_patterns_violation("T2", 10, "pattern")
    result2 = update_run_violation_metadata(session, run.id, v2)
    checks.append(("Second violation aggregated", result2["total_count"] == 2))

    session.commit()

    # Verify it's in run metadata
    session.refresh(run)
    checks.append(("Aggregation in run.acceptance_results",
                   "violation_aggregation" in (run.acceptance_results or {})))
    if run.acceptance_results and "violation_aggregation" in run.acceptance_results:
        checks.append(("Run metadata has correct count",
                       run.acceptance_results["violation_aggregation"]["total_count"] == 2))

    # Test get_violation_aggregation
    record_allowed_tools_violation(session, run.id, 1, "T3", 15, ["Read"])
    session.commit()
    computed_agg = get_violation_aggregation(session, run.id)
    checks.append(("get_violation_aggregation computes from events", computed_agg.total_count == 1))

    session.close()

    all_passed = True
    for desc, passed in checks:
        status = "✓" if passed else "✗"
        print(f"  {status} {desc}")
        if not passed:
            all_passed = False

    return all_passed


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #44: Policy Violation Event Logging")
    print("=" * 60)

    results = {
        "Step 1": verify_step1(),
        "Step 2": verify_step2(),
        "Step 3": verify_step3(),
        "Step 4": verify_step4(),
        "Step 5": verify_step5(),
        "Step 6": verify_step6(),
    }

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for step, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {step}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("✓ All verification steps PASSED")
        return 0
    else:
        print("✗ Some verification steps FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
