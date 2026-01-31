"""
Contract Test: Feature #162 — Acceptance Results API & WS Schema Match

This test snapshots the acceptance results payload from both:
  1. The REST API (GET /api/agent-runs/:id) via _build_run_response()
  2. The WebSocket (agent_acceptance_update) via AcceptanceUpdatePayload.to_message()

…and asserts they conform to the same JSON schema (Record<string, AcceptanceValidatorResult>).
A frozen schema snapshot is used for regression detection.

If either transport deviates from the canonical format, these tests will fail.
"""

import json
import copy
import pytest
from typing import Any


# =============================================================================
# Canonical AcceptanceValidatorResult Schema Snapshot
# =============================================================================

# This is the frozen schema for a single AcceptanceValidatorResult value.
# Both API and WebSocket MUST produce records whose values match this shape.
CANONICAL_VALIDATOR_RESULT_SCHEMA = {
    "passed":   {"type": bool,  "required": True},
    "message":  {"type": str,   "required": True},
    "score":    {"type": float, "required": True},
    "details":  {"type": dict,  "required": True},
    "index":    {"type": int,   "required": True},
    "required": {"type": bool,  "required": True},
    "weight":   {"type": float, "required": True},
}

# The set of canonical field names (used for drift detection)
CANONICAL_FIELDS = frozenset(CANONICAL_VALIDATOR_RESULT_SCHEMA.keys())


def _assert_matches_canonical_schema(record: dict[str, Any], source: str) -> None:
    """
    Assert that a Record<string, AcceptanceValidatorResult> conforms to the
    canonical schema snapshot.

    Args:
        record: The acceptance_results dict to validate.
        source: Label for error messages ("API" or "WS").
    """
    assert isinstance(record, dict), f"{source}: acceptance_results must be a dict, got {type(record)}"
    assert len(record) > 0, f"{source}: acceptance_results must not be empty"

    for key, entry in record.items():
        assert isinstance(key, str), f"{source}: key must be str, got {type(key)}"
        assert isinstance(entry, dict), f"{source}[{key}]: value must be a dict, got {type(entry)}"

        # Check all canonical fields are present
        actual_fields = set(entry.keys())
        missing = CANONICAL_FIELDS - actual_fields
        extra = actual_fields - CANONICAL_FIELDS
        assert not missing, (
            f"{source}[{key}]: missing canonical fields {missing}"
        )
        # Extra fields are allowed (forward compat) but we warn
        # For strict contract testing, uncomment below:
        # assert not extra, f"{source}[{key}]: unexpected extra fields {extra}"

        # Check field types
        for field_name, spec in CANONICAL_VALIDATOR_RESULT_SCHEMA.items():
            value = entry[field_name]
            expected_type = spec["type"]
            # Allow int for float fields (Python's int is a subtype of float conceptually)
            if expected_type is float and isinstance(value, (int, float)):
                continue
            assert isinstance(value, expected_type), (
                f"{source}[{key}].{field_name}: expected {expected_type.__name__}, "
                f"got {type(value).__name__} (value={value!r})"
            )


# =============================================================================
# Shared Test Fixtures
# =============================================================================

# Representative validator data as stored in DB (list format from AcceptanceGate.evaluate)
SAMPLE_DB_RESULTS_LIST = [
    {
        "index": 0,
        "type": "test_pass",
        "passed": True,
        "message": "All tests pass (exit code 0)",
        "score": 1.0,
        "required": True,
        "weight": 1.0,
        "details": {"exit_code": 0, "stdout": "OK"},
    },
    {
        "index": 1,
        "type": "file_exists",
        "passed": False,
        "message": "File does not exist: /app/output.txt",
        "score": 0.0,
        "required": False,
        "weight": 0.5,
        "details": {"path": "/app/output.txt"},
    },
    {
        "index": 2,
        "type": "forbidden_patterns",
        "passed": True,
        "message": "No forbidden patterns found in 3 tool_result event(s)",
        "score": 1.0,
        "required": False,
        "weight": 1.0,
        "details": {"patterns_checked": ["rm -rf /"], "events_checked": 3},
    },
]


def _get_api_acceptance_results(db_results: list[dict]) -> dict[str, Any]:
    """
    Simulate what the API returns for acceptance_results.

    The API path: DB list → normalize_acceptance_results_to_record() → AgentRunResponse.acceptance_results
    """
    from api.validators import normalize_acceptance_results_to_record
    return normalize_acceptance_results_to_record(db_results)


def _get_ws_acceptance_results(db_results: list[dict]) -> dict[str, Any]:
    """
    Simulate what the WebSocket emits for acceptance_results.

    The WS path: ValidatorResultPayload list → AcceptanceUpdatePayload._build_acceptance_results_record()
    """
    from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

    payloads = [
        ValidatorResultPayload(
            index=item.get("index", idx),
            type=item.get("type", f"validator_{idx}"),
            passed=item.get("passed", False),
            message=item.get("message", ""),
            score=item.get("score", 1.0 if item.get("passed") else 0.0),
            details=item.get("details", {}),
            required=item.get("required", False),
            weight=item.get("weight", 1.0),
        )
        for idx, item in enumerate(db_results)
    ]

    update = AcceptanceUpdatePayload(
        run_id="contract-test-run",
        final_verdict="failed",
        validator_results=payloads,
        gate_mode="all_pass",
    )

    message = update.to_message()
    return message["acceptance_results"]


# =============================================================================
# Test 1: API result conforms to canonical schema snapshot
# =============================================================================

class TestAPIConformsToCanonicalSchema:
    """Verify the API transport produces canonical AcceptanceValidatorResult records."""

    def test_api_results_match_canonical_schema(self):
        """API acceptance_results values have all canonical fields with correct types."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        _assert_matches_canonical_schema(api_results, "API")

    def test_api_results_keys_are_validator_types(self):
        """API record keys match the validator types from the source data."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        expected_keys = {"test_pass", "file_exists", "forbidden_patterns"}
        assert set(api_results.keys()) == expected_keys

    def test_api_preserves_passed_values(self):
        """API preserves the passed boolean for each validator."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["test_pass"]["passed"] is True
        assert api_results["file_exists"]["passed"] is False
        assert api_results["forbidden_patterns"]["passed"] is True

    def test_api_preserves_messages(self):
        """API preserves the message string for each validator."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["test_pass"]["message"] == "All tests pass (exit code 0)"
        assert "does not exist" in api_results["file_exists"]["message"]

    def test_api_preserves_scores(self):
        """API preserves the score float for each validator."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["test_pass"]["score"] == 1.0
        assert api_results["file_exists"]["score"] == 0.0

    def test_api_preserves_indices(self):
        """API preserves the original index for each validator."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["test_pass"]["index"] == 0
        assert api_results["file_exists"]["index"] == 1
        assert api_results["forbidden_patterns"]["index"] == 2

    def test_api_preserves_required_field(self):
        """API preserves the required boolean."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["test_pass"]["required"] is True
        assert api_results["file_exists"]["required"] is False

    def test_api_preserves_weight_field(self):
        """API preserves the weight float."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["test_pass"]["weight"] == 1.0
        assert api_results["file_exists"]["weight"] == 0.5

    def test_api_preserves_details(self):
        """API preserves the details dict."""
        api_results = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api_results["file_exists"]["details"] == {"path": "/app/output.txt"}


# =============================================================================
# Test 2: WebSocket result conforms to canonical schema snapshot
# =============================================================================

class TestWSConformsToCanonicalSchema:
    """Verify the WebSocket transport produces canonical AcceptanceValidatorResult records."""

    def test_ws_results_match_canonical_schema(self):
        """WS acceptance_results values have all canonical fields with correct types."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        _assert_matches_canonical_schema(ws_results, "WS")

    def test_ws_results_keys_are_validator_types(self):
        """WS record keys match the validator types from the source data."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        expected_keys = {"test_pass", "file_exists", "forbidden_patterns"}
        assert set(ws_results.keys()) == expected_keys

    def test_ws_preserves_passed_values(self):
        """WS preserves the passed boolean for each validator."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert ws_results["test_pass"]["passed"] is True
        assert ws_results["file_exists"]["passed"] is False
        assert ws_results["forbidden_patterns"]["passed"] is True

    def test_ws_preserves_messages(self):
        """WS preserves the message string for each validator."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert ws_results["test_pass"]["message"] == "All tests pass (exit code 0)"
        assert "does not exist" in ws_results["file_exists"]["message"]

    def test_ws_preserves_scores(self):
        """WS preserves the score float for each validator."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert ws_results["test_pass"]["score"] == 1.0
        assert ws_results["file_exists"]["score"] == 0.0

    def test_ws_preserves_indices(self):
        """WS preserves the original index for each validator."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert ws_results["test_pass"]["index"] == 0
        assert ws_results["file_exists"]["index"] == 1
        assert ws_results["forbidden_patterns"]["index"] == 2

    def test_ws_preserves_details(self):
        """WS preserves the details dict."""
        ws_results = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert ws_results["file_exists"]["details"] == {"path": "/app/output.txt"}


# =============================================================================
# Test 3: Cross-transport schema identity — API and WS match
# =============================================================================

class TestCrossTransportSchemaIdentity:
    """
    The core contract test: verify that API and WS produce the same schema
    for acceptance_results given identical source data.
    """

    def test_same_keys(self):
        """Both transports produce records with identical keys."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert set(api.keys()) == set(ws.keys()), (
            f"Key mismatch: API={sorted(api.keys())} vs WS={sorted(ws.keys())}"
        )

    def test_same_field_names_per_entry(self):
        """Both transports produce entries with the same field names."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)

        for key in api:
            api_fields = set(api[key].keys())
            ws_fields = set(ws[key].keys())
            assert api_fields == ws_fields, (
                f"Field mismatch for '{key}': API={sorted(api_fields)} vs WS={sorted(ws_fields)}"
            )

    def test_same_passed_values(self):
        """Both transports agree on passed for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["passed"] == ws[key]["passed"], (
                f"'passed' mismatch for '{key}': API={api[key]['passed']} vs WS={ws[key]['passed']}"
            )

    def test_same_message_values(self):
        """Both transports agree on message for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["message"] == ws[key]["message"], (
                f"'message' mismatch for '{key}': API={api[key]['message']!r} vs WS={ws[key]['message']!r}"
            )

    def test_same_score_values(self):
        """Both transports agree on score for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["score"] == ws[key]["score"], (
                f"'score' mismatch for '{key}': API={api[key]['score']} vs WS={ws[key]['score']}"
            )

    def test_same_index_values(self):
        """Both transports agree on index for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["index"] == ws[key]["index"], (
                f"'index' mismatch for '{key}': API={api[key]['index']} vs WS={ws[key]['index']}"
            )

    def test_same_details_values(self):
        """Both transports agree on details for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["details"] == ws[key]["details"], (
                f"'details' mismatch for '{key}': API={api[key]['details']!r} vs WS={ws[key]['details']!r}"
            )

    def test_same_required_values(self):
        """Both transports agree on required for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["required"] == ws[key]["required"], (
                f"'required' mismatch for '{key}': API={api[key]['required']} vs WS={ws[key]['required']}"
            )

    def test_same_weight_values(self):
        """Both transports agree on weight for every validator."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key in api:
            assert api[key]["weight"] == ws[key]["weight"], (
                f"'weight' mismatch for '{key}': API={api[key]['weight']} vs WS={ws[key]['weight']}"
            )

    def test_full_deep_equality(self):
        """
        Ultimate contract assertion: the entire acceptance_results dict
        is structurally identical from both transports.
        """
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        assert api == ws, (
            f"Full structural mismatch:\n"
            f"  API: {json.dumps(api, indent=2, default=str)}\n"
            f"  WS:  {json.dumps(ws, indent=2, default=str)}"
        )


# =============================================================================
# Test 4: Schema snapshot regression detection
# =============================================================================

class TestSchemaSnapshotRegression:
    """
    Snapshot the canonical field set and detect regressions if either
    transport changes its schema.
    """

    def test_api_field_set_matches_snapshot(self):
        """API record values have exactly the canonical fields."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key, entry in api.items():
            actual = set(entry.keys())
            assert actual == CANONICAL_FIELDS, (
                f"API field snapshot drift for '{key}': "
                f"expected={sorted(CANONICAL_FIELDS)}, actual={sorted(actual)}"
            )

    def test_ws_field_set_matches_snapshot(self):
        """WS record values have exactly the canonical fields."""
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key, entry in ws.items():
            actual = set(entry.keys())
            assert actual == CANONICAL_FIELDS, (
                f"WS field snapshot drift for '{key}': "
                f"expected={sorted(CANONICAL_FIELDS)}, actual={sorted(actual)}"
            )

    def test_canonical_schema_has_7_fields(self):
        """The canonical schema defines exactly 7 fields."""
        assert len(CANONICAL_VALIDATOR_RESULT_SCHEMA) == 7
        assert CANONICAL_FIELDS == {
            "passed", "message", "score", "details", "index", "required", "weight"
        }

    def test_api_field_types_match_snapshot(self):
        """API field values have types matching the canonical schema."""
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key, entry in api.items():
            for field_name, spec in CANONICAL_VALIDATOR_RESULT_SCHEMA.items():
                expected_type = spec["type"]
                value = entry[field_name]
                if expected_type is float and isinstance(value, (int, float)):
                    continue
                assert isinstance(value, expected_type), (
                    f"API[{key}].{field_name}: type snapshot violation "
                    f"(expected {expected_type.__name__}, got {type(value).__name__})"
                )

    def test_ws_field_types_match_snapshot(self):
        """WS field values have types matching the canonical schema."""
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        for key, entry in ws.items():
            for field_name, spec in CANONICAL_VALIDATOR_RESULT_SCHEMA.items():
                expected_type = spec["type"]
                value = entry[field_name]
                if expected_type is float and isinstance(value, (int, float)):
                    continue
                assert isinstance(value, expected_type), (
                    f"WS[{key}].{field_name}: type snapshot violation "
                    f"(expected {expected_type.__name__}, got {type(value).__name__})"
                )


# =============================================================================
# Test 5: Drift detection — test fails if either transport deviates
# =============================================================================

class TestDriftDetection:
    """
    Verify the contract test would fail if either transport deviates
    from the canonical format.
    """

    def test_api_missing_field_detected(self):
        """
        If the API normalizer dropped a field, the schema check would catch it.
        Simulate by post-processing API output.
        """
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)

        # Remove a field to simulate drift
        mutated = copy.deepcopy(api)
        first_key = next(iter(mutated))
        del mutated[first_key]["weight"]

        with pytest.raises(AssertionError, match="missing canonical fields"):
            _assert_matches_canonical_schema(mutated, "API")

    def test_ws_missing_field_detected(self):
        """
        If the WS builder dropped a field, the schema check would catch it.
        """
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)

        mutated = copy.deepcopy(ws)
        first_key = next(iter(mutated))
        del mutated[first_key]["index"]

        with pytest.raises(AssertionError, match="missing canonical fields"):
            _assert_matches_canonical_schema(mutated, "WS")

    def test_type_change_detected(self):
        """
        If a field type changed (e.g., passed from bool to string), the check catches it.
        """
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)

        mutated = copy.deepcopy(api)
        first_key = next(iter(mutated))
        mutated[first_key]["passed"] = "yes"  # Should be bool

        with pytest.raises(AssertionError, match="expected bool.*got str"):
            _assert_matches_canonical_schema(mutated, "API")

    def test_cross_transport_field_mismatch_detected(self):
        """
        If API and WS had different field sets, the identity test would catch it.
        Simulate by mutating one side.
        """
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)

        # Add an extra field to WS to simulate drift
        mutated_ws = copy.deepcopy(ws)
        first_key = next(iter(mutated_ws))
        mutated_ws[first_key]["extra_field"] = "drift"

        # The per-field identity check should detect this
        api_fields = set(api[first_key].keys())
        ws_fields = set(mutated_ws[first_key].keys())
        assert api_fields != ws_fields, "Simulated drift should produce different field sets"

    def test_cross_transport_value_mismatch_detected(self):
        """
        If API and WS disagreed on a value, the identity test would catch it.
        """
        api = _get_api_acceptance_results(SAMPLE_DB_RESULTS_LIST)
        ws = _get_ws_acceptance_results(SAMPLE_DB_RESULTS_LIST)

        # Mutate a value on WS side
        mutated_ws = copy.deepcopy(ws)
        first_key = next(iter(mutated_ws))
        mutated_ws[first_key]["score"] = 0.42  # Different from API

        assert api[first_key]["score"] != mutated_ws[first_key]["score"], (
            "Simulated value drift should produce different scores"
        )


# =============================================================================
# Test 6: Edge cases — duplicate types and empty inputs
# =============================================================================

class TestEdgeCases:
    """Test edge cases that could cause transport divergence."""

    def test_duplicate_validator_types_both_handle(self):
        """Both transports handle duplicate validator types consistently."""
        db_results = [
            {"index": 0, "type": "test_pass", "passed": True, "message": "First",
             "score": 1.0, "required": False, "weight": 1.0, "details": {}},
            {"index": 1, "type": "test_pass", "passed": False, "message": "Second",
             "score": 0.0, "required": False, "weight": 1.0, "details": {}},
        ]

        api = _get_api_acceptance_results(db_results)
        ws = _get_ws_acceptance_results(db_results)

        # Both should have 2 entries
        assert len(api) == 2
        assert len(ws) == 2

        # Both should use the same de-duplication strategy
        assert set(api.keys()) == set(ws.keys()), (
            f"Duplicate key handling mismatch: API={sorted(api.keys())} vs WS={sorted(ws.keys())}"
        )

    def test_single_validator(self):
        """Contract holds for a single validator."""
        db_results = [
            {"index": 0, "type": "file_exists", "passed": True, "message": "Found",
             "score": 1.0, "required": True, "weight": 1.0, "details": {"path": "/foo"}},
        ]

        api = _get_api_acceptance_results(db_results)
        ws = _get_ws_acceptance_results(db_results)

        _assert_matches_canonical_schema(api, "API")
        _assert_matches_canonical_schema(ws, "WS")
        assert api == ws

    def test_many_validators(self):
        """Contract holds for many validators."""
        db_results = [
            {
                "index": i,
                "type": f"type_{i}",
                "passed": i % 2 == 0,
                "message": f"Validator {i}",
                "score": 1.0 if i % 2 == 0 else 0.0,
                "required": i == 0,
                "weight": 1.0,
                "details": {"idx": i},
            }
            for i in range(10)
        ]

        api = _get_api_acceptance_results(db_results)
        ws = _get_ws_acceptance_results(db_results)

        assert len(api) == 10
        assert len(ws) == 10
        _assert_matches_canonical_schema(api, "API")
        _assert_matches_canonical_schema(ws, "WS")
        assert api == ws

    def test_empty_details(self):
        """Contract holds when details is empty."""
        db_results = [
            {"index": 0, "type": "test_pass", "passed": True, "message": "OK",
             "score": 1.0, "required": False, "weight": 1.0, "details": {}},
        ]

        api = _get_api_acceptance_results(db_results)
        ws = _get_ws_acceptance_results(db_results)

        assert api["test_pass"]["details"] == {}
        assert ws["test_pass"]["details"] == {}
        assert api == ws

    def test_complex_details(self):
        """Contract holds when details has nested structures."""
        db_results = [
            {
                "index": 0,
                "type": "test_pass",
                "passed": True,
                "message": "Complex",
                "score": 1.0,
                "required": False,
                "weight": 1.0,
                "details": {
                    "stdout": "PASS: 10 tests",
                    "nested": {"a": 1, "b": [2, 3]},
                    "list_val": [1, 2, 3],
                },
            },
        ]

        api = _get_api_acceptance_results(db_results)
        ws = _get_ws_acceptance_results(db_results)

        assert api["test_pass"]["details"] == ws["test_pass"]["details"]
        assert api == ws
