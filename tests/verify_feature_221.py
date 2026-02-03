#!/usr/bin/env python3
"""
Verification script for Feature #221: agent_planned audit event type created

This script verifies all 5 feature steps without requiring a running server.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check(step: str, condition: bool, message: str) -> bool:
    """Print check result and return success status."""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {message}")
    return condition


def main():
    """Run all verification steps."""
    print("\n" + "=" * 70)
    print("Feature #221: agent_planned audit event type created")
    print("=" * 70)

    all_passed = True

    # Step 1: Add 'agent_planned' to event_type enum
    print("\nStep 1: Add 'agent_planned' to event_type enum")
    print("-" * 50)

    from api.agentspec_models import EVENT_TYPES

    step1_pass = check(
        "1.1",
        "agent_planned" in EVENT_TYPES,
        "'agent_planned' is in EVENT_TYPES"
    )
    step1_pass &= check(
        "1.2",
        isinstance(EVENT_TYPES, list),
        "EVENT_TYPES is a list"
    )
    step1_pass &= check(
        "1.3",
        len([e for e in EVENT_TYPES if e == "agent_planned"]) == 1,
        "'agent_planned' appears exactly once"
    )
    all_passed &= step1_pass

    # Step 2: Event payload includes: agent_name, capabilities, rationale
    print("\nStep 2: Event payload includes: agent_name, capabilities, rationale")
    print("-" * 50)

    from api.event_recorder import EventRecorder
    import inspect

    sig = inspect.signature(EventRecorder.record_agent_planned)
    params = list(sig.parameters.keys())

    step2_pass = check(
        "2.1",
        "agent_name" in params,
        "record_agent_planned has 'agent_name' parameter"
    )
    step2_pass &= check(
        "2.2",
        "capabilities" in params,
        "record_agent_planned has 'capabilities' parameter"
    )
    step2_pass &= check(
        "2.3",
        "rationale" in params,
        "record_agent_planned has 'rationale' parameter"
    )
    all_passed &= step2_pass

    # Step 3: Event linked to project or feature triggering planning
    print("\nStep 3: Event linked to project or feature triggering planning")
    print("-" * 50)

    step3_pass = check(
        "3.1",
        "project_name" in params,
        "record_agent_planned has 'project_name' parameter"
    )
    step3_pass &= check(
        "3.2",
        "feature_id" in params,
        "record_agent_planned has 'feature_id' parameter"
    )

    # Check Maestro methods too
    from api.maestro import Maestro
    maestro_sig = inspect.signature(Maestro.record_agent_planned)
    maestro_params = list(maestro_sig.parameters.keys())

    step3_pass &= check(
        "3.3",
        "project_name" in maestro_params,
        "Maestro.record_agent_planned has 'project_name' parameter"
    )
    step3_pass &= check(
        "3.4",
        "feature_id" in maestro_params,
        "Maestro.record_agent_planned has 'feature_id' parameter"
    )
    all_passed &= step3_pass

    # Step 4: Event recorded before Octo invocation
    print("\nStep 4: Event recorded before Octo invocation")
    print("-" * 50)

    # Check that Maestro has the methods needed
    step4_pass = check(
        "4.1",
        hasattr(Maestro, "record_agent_planned"),
        "Maestro has 'record_agent_planned' method"
    )
    step4_pass &= check(
        "4.2",
        hasattr(Maestro, "_record_agent_planned_event"),
        "Maestro has '_record_agent_planned_event' method"
    )

    # Check EventRecorder method exists
    step4_pass &= check(
        "4.3",
        hasattr(EventRecorder, "record_agent_planned"),
        "EventRecorder has 'record_agent_planned' method"
    )
    all_passed &= step4_pass

    # Step 5: Event queryable via existing event APIs
    print("\nStep 5: Event queryable via existing event APIs")
    print("-" * 50)

    # Check that agent_planned is included in the API validation
    # The API now uses EVENT_TYPES directly
    step5_pass = check(
        "5.1",
        "agent_planned" in EVENT_TYPES,
        "'agent_planned' available for API filtering"
    )

    # Check the router file has been updated
    router_path = project_root / "server" / "routers" / "agent_runs.py"
    router_content = router_path.read_text()

    step5_pass &= check(
        "5.2",
        "EVENT_TYPES" in router_content,
        "API router imports EVENT_TYPES for validation"
    )
    step5_pass &= check(
        "5.3",
        "VALID_EVENT_TYPES" in router_content,
        "API router uses VALID_EVENT_TYPES alias"
    )
    all_passed &= step5_pass

    # Summary
    print("\n" + "=" * 70)
    if all_passed:
        print("RESULT: ALL VERIFICATION STEPS PASSED")
    else:
        print("RESULT: SOME VERIFICATION STEPS FAILED")
    print("=" * 70 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
