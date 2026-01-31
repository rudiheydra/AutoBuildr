#!/usr/bin/env python3
"""
Verification script for Feature #160: Standardize acceptance results to canonical format.

Tests all 5 feature steps:
1. Identify where the API returns acceptance results
2. Identify where the WebSocket emits acceptance results
3. Align both to use Record<string, AcceptanceValidatorResult>
4. Add format_version field to WS payload
5. Verify both API and WS return identical structures
"""

import sys
import json

results = []

def check(step, description, passed, detail=""):
    results.append((step, description, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"  Step {step}: {description} - {status}")
    if detail:
        print(f"    Detail: {detail}")

print("=" * 70)
print("Feature #160: Standardize acceptance results to canonical format")
print("=" * 70)
print()

# Step 1: Verify API endpoint uses canonical format
print("Step 1: API returns acceptance results in canonical Record format")
try:
    from server.routers.agent_runs import _build_run_response

    run_dict = {
        "id": "run-123",
        "agent_spec_id": "spec-456",
        "status": "completed",
        "started_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:01:00+00:00",
        "turns_used": 5,
        "tokens_in": 1000,
        "tokens_out": 500,
        "final_verdict": "passed",
        "acceptance_results": [
            {"index": 0, "type": "test_pass", "passed": True, "message": "All tests pass",
             "score": 1.0, "required": True, "weight": 1.0, "details": {}},
            {"index": 1, "type": "file_exists", "passed": False, "message": "File missing",
             "score": 0.0, "required": False, "weight": 1.0, "details": {"path": "/foo"}},
        ],
        "error": None,
        "retry_count": 0,
        "created_at": "2024-01-01T00:00:00+00:00",
    }

    response = _build_run_response(run_dict)
    ar = response.acceptance_results

    assert isinstance(ar, dict), f"Expected dict, got {type(ar)}"
    assert "test_pass" in ar, f"Missing key 'test_pass', got keys: {list(ar.keys())}"
    assert "file_exists" in ar, f"Missing key 'file_exists'"
    assert ar["test_pass"]["passed"] is True
    assert ar["test_pass"]["message"] == "All tests pass"
    assert ar["file_exists"]["passed"] is False
    check(1, "API returns Record<string, AcceptanceValidatorResult>", True,
          f"Keys: {list(ar.keys())}")
except Exception as e:
    check(1, "API returns Record<string, AcceptanceValidatorResult>", False, str(e))

print()

# Step 2: Verify WebSocket emits acceptance results in canonical format
print("Step 2: WebSocket emits acceptance results in canonical Record format")
try:
    from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

    payload = AcceptanceUpdatePayload(
        run_id="run-123",
        final_verdict="passed",
        validator_results=[
            ValidatorResultPayload(
                index=0, type="test_pass", passed=True,
                message="All tests pass", score=1.0, details={},
            ),
            ValidatorResultPayload(
                index=1, type="file_exists", passed=False,
                message="File missing", score=0.0, details={"path": "/foo"},
            ),
        ],
        gate_mode="all_pass",
    )

    message = payload.to_message()

    assert "acceptance_results" in message, "Missing 'acceptance_results' in WS message"
    ar = message["acceptance_results"]
    assert isinstance(ar, dict), f"Expected dict, got {type(ar)}"
    assert "test_pass" in ar, f"Missing key 'test_pass'"
    assert "file_exists" in ar, f"Missing key 'file_exists'"
    assert ar["test_pass"]["passed"] is True
    assert ar["file_exists"]["passed"] is False
    check(2, "WebSocket emits Record<string, AcceptanceValidatorResult>", True,
          f"Keys: {list(ar.keys())}")
except Exception as e:
    check(2, "WebSocket emits Record<string, AcceptanceValidatorResult>", False, str(e))

print()

# Step 3: Verify both use the same canonical format
print("Step 3: Both API and WS return identical structures")
try:
    from api.validators import normalize_acceptance_results_to_record
    from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

    # Common test data
    validators = [
        {"index": 0, "type": "test_pass", "passed": True, "message": "OK",
         "score": 1.0, "required": True, "weight": 1.0, "details": {}},
        {"index": 1, "type": "forbidden_patterns", "passed": True, "message": "Clean",
         "score": 1.0, "required": False, "weight": 1.0, "details": {}},
    ]

    # API path
    api_result = normalize_acceptance_results_to_record(validators)

    # WS path
    ws_payload = AcceptanceUpdatePayload(
        run_id="test",
        final_verdict="passed",
        validator_results=[
            ValidatorResultPayload(
                index=v["index"], type=v["type"], passed=v["passed"],
                message=v["message"], score=v["score"], details=v["details"],
            )
            for v in validators
        ],
        gate_mode="all_pass",
    )
    ws_message = ws_payload.to_message()
    ws_result = ws_message["acceptance_results"]

    # Check key match
    assert set(api_result.keys()) == set(ws_result.keys()), \
        f"Key mismatch: API={set(api_result.keys())} vs WS={set(ws_result.keys())}"

    # Check value match for core fields
    for key in api_result:
        assert api_result[key]["passed"] == ws_result[key]["passed"]
        assert api_result[key]["message"] == ws_result[key]["message"]
        assert api_result[key]["score"] == ws_result[key]["score"]
        assert api_result[key]["index"] == ws_result[key]["index"]

    check(3, "Both API and WS return identical structures", True,
          f"Both have keys: {list(api_result.keys())}, core fields match")
except Exception as e:
    check(3, "Both API and WS return identical structures", False, str(e))

print()

# Step 4: Verify format_version field in WS payload
print("Step 4: WS payload includes format_version field")
try:
    from api.websocket_events import AcceptanceUpdatePayload

    payload = AcceptanceUpdatePayload(
        run_id="run-123",
        final_verdict="passed",
        validator_results=[],
        gate_mode="all_pass",
    )

    message = payload.to_message()

    assert "format_version" in message, "Missing 'format_version' in WS message"
    assert message["format_version"] == 2, f"Expected format_version=2, got {message['format_version']}"
    check(4, "WS payload includes format_version=2", True)
except Exception as e:
    check(4, "WS payload includes format_version=2", False, str(e))

print()

# Step 5: Verify backward compatibility (validator_results array still present)
print("Step 5: WS still includes validator_results array for backward compat")
try:
    from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

    payload = AcceptanceUpdatePayload(
        run_id="run-123",
        final_verdict="passed",
        validator_results=[
            ValidatorResultPayload(
                index=0, type="test_pass", passed=True,
                message="OK", score=1.0, details={},
            ),
        ],
        gate_mode="all_pass",
    )

    message = payload.to_message()

    assert "validator_results" in message, "Missing 'validator_results' backward compat"
    assert isinstance(message["validator_results"], list), "validator_results should be list"
    assert len(message["validator_results"]) == 1
    assert message["validator_results"][0]["type"] == "test_pass"
    check(5, "WS backward compat: validator_results array present", True)
except Exception as e:
    check(5, "WS backward compat: validator_results array present", False, str(e))

print()

# Summary
print("=" * 70)
passed = sum(1 for _, _, p, _ in results if p)
total = len(results)
print(f"Results: {passed}/{total} steps PASSED")
print("=" * 70)

if passed < total:
    sys.exit(1)
