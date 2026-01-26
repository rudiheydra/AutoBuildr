#!/usr/bin/env python3
"""
Feature #10 Verification Script
================================

Artifact and AgentEvent Pydantic Schemas

This script verifies all 6 steps of Feature #10:
1. ArtifactResponse with all Artifact fields
2. Field validator for artifact_type enum
3. has_inline_content computed property
4. AgentEventResponse with all AgentEvent fields
5. Field validator for event_type enum
6. AgentEventListResponse for timeline queries
"""
from __future__ import annotations

import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, '/home/rudih/workspace/AutoBuildr')


def check(name: str, condition: bool, detail: str = "") -> bool:
    """Print check result and return condition."""
    status = "PASS" if condition else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return condition


def step_1_artifact_response_fields() -> bool:
    """Step 1: Define ArtifactResponse with all Artifact fields."""
    print("\n=== Step 1: ArtifactResponse with all Artifact fields ===")
    from server.schemas.agentspec import ArtifactResponse

    # Check that all fields are defined
    fields = ArtifactResponse.model_fields
    required_fields = [
        'id', 'run_id', 'artifact_type', 'path', 'content_ref',
        'content_hash', 'size_bytes', 'created_at', 'metadata', 'content_inline'
    ]

    all_pass = True
    for field in required_fields:
        if field in fields:
            all_pass = check(f"Field '{field}' exists", True) and all_pass
        else:
            all_pass = check(f"Field '{field}' exists", False, f"Missing field: {field}") and all_pass

    # Test creating a valid ArtifactResponse
    try:
        artifact = ArtifactResponse(
            id="test-uuid-123",
            run_id="run-uuid-456",
            artifact_type="test_result",
            path="/tmp/test.log",
            content_ref=None,
            content_hash="sha256:abc123",
            size_bytes=256,
            created_at=datetime.now(),
            metadata={"test": True},
            content_inline="test content"
        )
        all_pass = check("Can create ArtifactResponse with all fields", True) and all_pass
    except Exception as e:
        all_pass = check("Can create ArtifactResponse with all fields", False, str(e)) and all_pass

    return all_pass


def step_2_artifact_type_validator() -> bool:
    """Step 2: Field validator for artifact_type enum."""
    print("\n=== Step 2: artifact_type field validator ===")
    from server.schemas.agentspec import ArtifactResponse
    from pydantic import ValidationError

    valid_types = ["file_change", "test_result", "log", "metric", "snapshot"]
    all_pass = True

    # Test each valid type
    for atype in valid_types:
        try:
            artifact = ArtifactResponse(
                id="test-uuid",
                run_id="run-uuid",
                artifact_type=atype,
                created_at=datetime.now()
            )
            all_pass = check(f"Valid artifact_type '{atype}'", True) and all_pass
        except Exception as e:
            all_pass = check(f"Valid artifact_type '{atype}'", False, str(e)) and all_pass

    # Test invalid type
    try:
        artifact = ArtifactResponse(
            id="test-uuid",
            run_id="run-uuid",
            artifact_type="invalid_type",
            created_at=datetime.now()
        )
        all_pass = check("Invalid artifact_type rejected", False, "Should have raised error") and all_pass
    except ValidationError as e:
        all_pass = check("Invalid artifact_type rejected", True, "ValidationError raised") and all_pass
    except Exception as e:
        all_pass = check("Invalid artifact_type rejected", False, f"Wrong exception: {type(e)}") and all_pass

    return all_pass


def step_3_has_inline_content_property() -> bool:
    """Step 3: has_inline_content computed property."""
    print("\n=== Step 3: has_inline_content computed property ===")
    from server.schemas.agentspec import ArtifactResponse

    all_pass = True

    # Test with inline content
    artifact_with_content = ArtifactResponse(
        id="test-uuid",
        run_id="run-uuid",
        artifact_type="log",
        created_at=datetime.now(),
        content_inline="This is inline content"
    )
    all_pass = check(
        "has_inline_content=True when content present",
        artifact_with_content.has_inline_content == True
    ) and all_pass

    # Test without inline content
    artifact_no_content = ArtifactResponse(
        id="test-uuid",
        run_id="run-uuid",
        artifact_type="log",
        created_at=datetime.now(),
        content_inline=None
    )
    all_pass = check(
        "has_inline_content=False when content is None",
        artifact_no_content.has_inline_content == False
    ) and all_pass

    # Test with empty string
    artifact_empty = ArtifactResponse(
        id="test-uuid",
        run_id="run-uuid",
        artifact_type="log",
        created_at=datetime.now(),
        content_inline=""
    )
    all_pass = check(
        "has_inline_content=False when content is empty string",
        artifact_empty.has_inline_content == False
    ) and all_pass

    return all_pass


def step_4_agent_event_response_fields() -> bool:
    """Step 4: Define AgentEventResponse with all AgentEvent fields."""
    print("\n=== Step 4: AgentEventResponse with all AgentEvent fields ===")
    from server.schemas.agentspec import AgentEventResponse

    # Check that all fields are defined
    fields = AgentEventResponse.model_fields
    required_fields = [
        'id', 'run_id', 'event_type', 'timestamp', 'sequence',
        'payload', 'payload_truncated', 'artifact_ref', 'tool_name'
    ]

    all_pass = True
    for field in required_fields:
        if field in fields:
            all_pass = check(f"Field '{field}' exists", True) and all_pass
        else:
            all_pass = check(f"Field '{field}' exists", False, f"Missing field: {field}") and all_pass

    # Test creating a valid AgentEventResponse
    try:
        event = AgentEventResponse(
            id=1,
            run_id="run-uuid-123",
            event_type="tool_call",
            timestamp=datetime.now(),
            sequence=1,
            payload={"tool": "test_tool", "args": {}},
            payload_truncated=None,
            artifact_ref=None,
            tool_name="test_tool"
        )
        all_pass = check("Can create AgentEventResponse with all fields", True) and all_pass
    except Exception as e:
        all_pass = check("Can create AgentEventResponse with all fields", False, str(e)) and all_pass

    return all_pass


def step_5_event_type_validator() -> bool:
    """Step 5: Field validator for event_type enum."""
    print("\n=== Step 5: event_type field validator ===")
    from server.schemas.agentspec import AgentEventResponse
    from pydantic import ValidationError

    valid_types = [
        "started", "tool_call", "tool_result", "turn_complete",
        "acceptance_check", "completed", "failed", "paused", "resumed"
    ]
    all_pass = True

    # Test each valid type
    for etype in valid_types:
        try:
            event = AgentEventResponse(
                id=1,
                run_id="run-uuid",
                event_type=etype,
                timestamp=datetime.now(),
                sequence=1
            )
            all_pass = check(f"Valid event_type '{etype}'", True) and all_pass
        except Exception as e:
            all_pass = check(f"Valid event_type '{etype}'", False, str(e)) and all_pass

    # Test invalid type
    try:
        event = AgentEventResponse(
            id=1,
            run_id="run-uuid",
            event_type="invalid_type",
            timestamp=datetime.now(),
            sequence=1
        )
        all_pass = check("Invalid event_type rejected", False, "Should have raised error") and all_pass
    except ValidationError as e:
        all_pass = check("Invalid event_type rejected", True, "ValidationError raised") and all_pass
    except Exception as e:
        all_pass = check("Invalid event_type rejected", False, f"Wrong exception: {type(e)}") and all_pass

    return all_pass


def step_6_agent_event_list_response() -> bool:
    """Step 6: AgentEventListResponse for timeline queries."""
    print("\n=== Step 6: AgentEventListResponse for timeline queries ===")
    from server.schemas.agentspec import AgentEventListResponse, AgentEventResponse

    all_pass = True

    # Check that the class exists and has the expected fields
    fields = AgentEventListResponse.model_fields
    required_fields = ['events', 'total', 'run_id', 'start_sequence', 'end_sequence', 'has_more']

    for field in required_fields:
        if field in fields:
            all_pass = check(f"Field '{field}' exists", True) and all_pass
        else:
            all_pass = check(f"Field '{field}' exists", False, f"Missing field: {field}") and all_pass

    # Test creating a valid AgentEventListResponse
    try:
        events = [
            AgentEventResponse(
                id=1,
                run_id="run-uuid-123",
                event_type="started",
                timestamp=datetime.now(),
                sequence=1,
                payload={"objective": "Test"},
                payload_truncated=None,
                artifact_ref=None,
                tool_name=None
            ),
            AgentEventResponse(
                id=2,
                run_id="run-uuid-123",
                event_type="tool_call",
                timestamp=datetime.now(),
                sequence=2,
                payload={"tool": "test"},
                payload_truncated=None,
                artifact_ref=None,
                tool_name="test_tool"
            )
        ]

        timeline = AgentEventListResponse(
            events=events,
            total=100,
            run_id="run-uuid-123",
            start_sequence=1,
            end_sequence=2,
            has_more=True
        )
        all_pass = check("Can create AgentEventListResponse for timeline", True) and all_pass
        all_pass = check("events field contains AgentEventResponse list", len(timeline.events) == 2) and all_pass
        all_pass = check("total field is int", timeline.total == 100) and all_pass
        all_pass = check("run_id field is str", timeline.run_id == "run-uuid-123") and all_pass
        all_pass = check("start_sequence field is int", timeline.start_sequence == 1) and all_pass
        all_pass = check("end_sequence field is int", timeline.end_sequence == 2) and all_pass
        all_pass = check("has_more field is bool", timeline.has_more == True) and all_pass
    except Exception as e:
        all_pass = check("Can create AgentEventListResponse for timeline", False, str(e)) and all_pass

    # Verify it's exported from the package
    try:
        from server.schemas import AgentEventListResponse as ExportedClass
        all_pass = check("AgentEventListResponse exported from server.schemas", True) and all_pass
    except ImportError as e:
        all_pass = check("AgentEventListResponse exported from server.schemas", False, str(e)) and all_pass

    return all_pass


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #10 Verification: Artifact and AgentEvent Pydantic Schemas")
    print("=" * 60)

    results = []

    # Run each step
    results.append(("Step 1: ArtifactResponse fields", step_1_artifact_response_fields()))
    results.append(("Step 2: artifact_type validator", step_2_artifact_type_validator()))
    results.append(("Step 3: has_inline_content property", step_3_has_inline_content_property()))
    results.append(("Step 4: AgentEventResponse fields", step_4_agent_event_response_fields()))
    results.append(("Step 5: event_type validator", step_5_event_type_validator()))
    results.append(("Step 6: AgentEventListResponse", step_6_agent_event_list_response()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED")
        print("Feature #10 is ready to be marked as passing.")
        return 0
    else:
        print("SOME VERIFICATION STEPS FAILED")
        print("Please fix the failing steps before marking the feature as passing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
