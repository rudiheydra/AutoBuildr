#!/usr/bin/env python3
"""
Feature #63 Verification Script
================================

WebSocket agent_acceptance_update Event

This script verifies each step of Feature #63:
1. After acceptance gate evaluation, publish message
2. Message type: agent_acceptance_update
3. Payload: run_id, final_verdict, validator_results array
4. Each validator result: index, type, passed, message

Run with: python tests/verify_feature_63.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_step(step_num: int, description: str):
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {description}")
    print('='*60)


def check_pass(condition: bool, message: str):
    """Print pass/fail for a check."""
    status = "PASS" if condition else "FAIL"
    symbol = "\u2713" if condition else "\u2717"
    print(f"  [{symbol}] {status}: {message}")
    return condition


def main():
    """Run all verification steps."""
    print("Feature #63: WebSocket agent_acceptance_update Event")
    print("="*60)

    all_passed = True

    # ==========================================================================
    # Step 1: After acceptance gate evaluation, publish message
    # ==========================================================================
    print_step(1, "After acceptance gate evaluation, publish message")

    from api.websocket_events import (
        broadcast_acceptance_update,
        broadcast_acceptance_update_sync,
        build_acceptance_update_from_results,
        AcceptanceUpdatePayload,
        ValidatorResultPayload,
    )

    # Check that broadcast functions exist and are callable
    all_passed &= check_pass(
        callable(broadcast_acceptance_update),
        "broadcast_acceptance_update function exists and is callable"
    )

    all_passed &= check_pass(
        callable(broadcast_acceptance_update_sync),
        "broadcast_acceptance_update_sync function exists and is callable"
    )

    all_passed &= check_pass(
        callable(build_acceptance_update_from_results),
        "build_acceptance_update_from_results helper exists"
    )

    # Check that we can build a payload from validator results
    from api.validators import ValidatorResult

    results = [
        ValidatorResult(passed=True, message="OK", validator_type="file_exists"),
    ]

    payload = build_acceptance_update_from_results("test-run", True, results)
    all_passed &= check_pass(
        payload is not None and payload.run_id == "test-run",
        "Can build AcceptanceUpdatePayload from evaluate_acceptance_spec output"
    )

    # ==========================================================================
    # Step 2: Message type: agent_acceptance_update
    # ==========================================================================
    print_step(2, "Message type: agent_acceptance_update")

    payload = AcceptanceUpdatePayload(
        run_id="abc-123",
        final_verdict="passed",
        validator_results=[],
    )

    message = payload.to_message()

    all_passed &= check_pass(
        "type" in message,
        "Message contains 'type' field"
    )

    all_passed &= check_pass(
        message.get("type") == "agent_acceptance_update",
        f"Message type is 'agent_acceptance_update' (got: {message.get('type')})"
    )

    # ==========================================================================
    # Step 3: Payload: run_id, final_verdict, validator_results array
    # ==========================================================================
    print_step(3, "Payload: run_id, final_verdict, validator_results array")

    validator_results = [
        ValidatorResultPayload(index=0, type="file_exists", passed=True, message="OK"),
        ValidatorResultPayload(index=1, type="test_pass", passed=False, message="Failed"),
    ]

    payload = AcceptanceUpdatePayload(
        run_id="my-run-id-12345",
        final_verdict="failed",
        validator_results=validator_results,
        gate_mode="all_pass",
    )

    message = payload.to_message()

    all_passed &= check_pass(
        "run_id" in message,
        "Payload contains 'run_id' field"
    )

    all_passed &= check_pass(
        message.get("run_id") == "my-run-id-12345",
        f"run_id is correct (got: {message.get('run_id')})"
    )

    all_passed &= check_pass(
        "final_verdict" in message,
        "Payload contains 'final_verdict' field"
    )

    all_passed &= check_pass(
        message.get("final_verdict") == "failed",
        f"final_verdict is correct (got: {message.get('final_verdict')})"
    )

    all_passed &= check_pass(
        "validator_results" in message,
        "Payload contains 'validator_results' field"
    )

    all_passed &= check_pass(
        isinstance(message.get("validator_results"), list),
        "validator_results is an array"
    )

    all_passed &= check_pass(
        len(message.get("validator_results", [])) == 2,
        f"validator_results has correct length (got: {len(message.get('validator_results', []))})"
    )

    # ==========================================================================
    # Step 4: Each validator result: index, type, passed, message
    # ==========================================================================
    print_step(4, "Each validator result: index, type, passed, message")

    results = message.get("validator_results", [])

    for i, result in enumerate(results):
        all_passed &= check_pass(
            "index" in result,
            f"Result {i}: contains 'index' field"
        )
        all_passed &= check_pass(
            isinstance(result.get("index"), int),
            f"Result {i}: 'index' is integer (got: {type(result.get('index')).__name__})"
        )

        all_passed &= check_pass(
            "type" in result,
            f"Result {i}: contains 'type' field"
        )
        all_passed &= check_pass(
            isinstance(result.get("type"), str),
            f"Result {i}: 'type' is string (got: {type(result.get('type')).__name__})"
        )

        all_passed &= check_pass(
            "passed" in result,
            f"Result {i}: contains 'passed' field"
        )
        all_passed &= check_pass(
            isinstance(result.get("passed"), bool),
            f"Result {i}: 'passed' is boolean (got: {type(result.get('passed')).__name__})"
        )

        all_passed &= check_pass(
            "message" in result,
            f"Result {i}: contains 'message' field"
        )
        all_passed &= check_pass(
            isinstance(result.get("message"), str),
            f"Result {i}: 'message' is string (got: {type(result.get('message')).__name__})"
        )

    # Verify first result values
    if len(results) >= 1:
        all_passed &= check_pass(
            results[0]["index"] == 0,
            f"First result index is 0 (got: {results[0].get('index')})"
        )
        all_passed &= check_pass(
            results[0]["type"] == "file_exists",
            f"First result type is 'file_exists' (got: {results[0].get('type')})"
        )
        all_passed &= check_pass(
            results[0]["passed"] is True,
            f"First result passed is True (got: {results[0].get('passed')})"
        )

    # Verify second result values
    if len(results) >= 2:
        all_passed &= check_pass(
            results[1]["index"] == 1,
            f"Second result index is 1 (got: {results[1].get('index')})"
        )
        all_passed &= check_pass(
            results[1]["type"] == "test_pass",
            f"Second result type is 'test_pass' (got: {results[1].get('type')})"
        )
        all_passed &= check_pass(
            results[1]["passed"] is False,
            f"Second result passed is False (got: {results[1].get('passed')})"
        )

    # ==========================================================================
    # Additional Verifications
    # ==========================================================================
    print_step(5, "Additional Verifications (JSON serialization, exports)")

    import json

    # Check JSON serializability
    try:
        json_str = json.dumps(message)
        parsed = json.loads(json_str)
        all_passed &= check_pass(
            parsed["type"] == "agent_acceptance_update",
            "Message is JSON serializable and parseable"
        )
    except Exception as e:
        all_passed &= check_pass(False, f"Message JSON serialization failed: {e}")

    # Check exports from api module
    try:
        from api import (
            AcceptanceUpdatePayload,
            ValidatorResultPayload,
            broadcast_acceptance_update,
            broadcast_acceptance_update_sync,
            build_acceptance_update_from_results,
            create_validator_result_payload,
        )
        all_passed &= check_pass(True, "All functions exported from api module")
    except ImportError as e:
        all_passed &= check_pass(False, f"Import error: {e}")

    # Check integration with ValidatorResult
    from api.websocket_events import create_validator_result_payload
    from api.validators import ValidatorResult

    vr = ValidatorResult(
        passed=True,
        message="Test message",
        score=0.95,
        details={"key": "value"},
        validator_type="custom_validator",
    )

    payload = create_validator_result_payload(5, vr)
    all_passed &= check_pass(
        payload.index == 5 and payload.type == "custom_validator" and payload.passed is True,
        "create_validator_result_payload correctly converts ValidatorResult"
    )

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)

    if all_passed:
        print("\n[SUCCESS] All verification steps PASSED!")
        print("\nFeature #63: WebSocket agent_acceptance_update Event is complete.")
        return 0
    else:
        print("\n[FAILURE] Some verification steps FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
