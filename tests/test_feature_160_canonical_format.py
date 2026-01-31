"""
Tests for Feature #160: Standardize acceptance results to canonical format in backend.

Verifies that:
1. normalize_acceptance_results_to_record() converts list to record format
2. API endpoints return canonical Record<string, AcceptanceValidatorResult> format
3. WebSocket payload emits canonical format with format_version field
4. Both API and WS return identical structures for the same run
"""

import pytest
from datetime import datetime, timezone


# =============================================================================
# Test 1: normalize_acceptance_results_to_record utility function
# =============================================================================

class TestNormalizeAcceptanceResultsToRecord:
    """Test the normalize_acceptance_results_to_record utility function."""

    def test_none_input(self):
        """None input returns empty dict."""
        from api.validators import normalize_acceptance_results_to_record
        assert normalize_acceptance_results_to_record(None) == {}

    def test_empty_list(self):
        """Empty list returns empty dict."""
        from api.validators import normalize_acceptance_results_to_record
        assert normalize_acceptance_results_to_record([]) == {}

    def test_empty_dict(self):
        """Empty dict returns empty dict."""
        from api.validators import normalize_acceptance_results_to_record
        assert normalize_acceptance_results_to_record({}) == {}

    def test_list_with_validator_type_key(self):
        """List with 'validator_type' key (from _run_acceptance_validators)."""
        from api.validators import normalize_acceptance_results_to_record
        result = normalize_acceptance_results_to_record([
            {"passed": True, "message": "OK", "score": 1.0, "details": {}, "validator_type": "test_pass"},
            {"passed": False, "message": "Missing", "score": 0.0, "details": {}, "validator_type": "file_exists"},
        ])
        assert "test_pass" in result
        assert result["test_pass"]["passed"] is True
        assert result["test_pass"]["message"] == "OK"
        assert result["test_pass"]["score"] == 1.0
        assert "file_exists" in result
        assert result["file_exists"]["passed"] is False
        assert result["file_exists"]["message"] == "Missing"

    def test_list_with_type_key(self):
        """List with 'type' key (from AcceptanceGate.evaluate)."""
        from api.validators import normalize_acceptance_results_to_record
        result = normalize_acceptance_results_to_record([
            {"index": 0, "type": "test_pass", "passed": True, "message": "OK",
             "score": 1.0, "required": True, "weight": 1.0, "details": {}},
            {"index": 1, "type": "file_exists", "passed": False, "message": "Missing",
             "score": 0.0, "required": False, "weight": 0.5, "details": {"path": "/foo"}},
        ])
        assert "test_pass" in result
        assert result["test_pass"]["passed"] is True
        assert result["test_pass"]["required"] is True
        assert result["test_pass"]["index"] == 0
        assert "file_exists" in result
        assert result["file_exists"]["passed"] is False
        assert result["file_exists"]["required"] is False
        assert result["file_exists"]["weight"] == 0.5
        assert result["file_exists"]["details"] == {"path": "/foo"}

    def test_already_record_format_passthrough(self):
        """Already in record format passes through unchanged."""
        from api.validators import normalize_acceptance_results_to_record
        already_record = {
            "test_pass": {"passed": True, "message": "OK"},
            "file_exists": {"passed": False, "message": "Missing"},
        }
        result = normalize_acceptance_results_to_record(already_record)
        assert result == already_record

    def test_duplicate_types_get_index_suffix(self):
        """Duplicate validator types get index-based suffix."""
        from api.validators import normalize_acceptance_results_to_record
        result = normalize_acceptance_results_to_record([
            {"type": "test_pass", "passed": True, "message": "First"},
            {"type": "test_pass", "passed": False, "message": "Second"},
        ])
        assert "test_pass" in result
        assert "test_pass_1" in result
        assert result["test_pass"]["message"] == "First"
        assert result["test_pass_1"]["message"] == "Second"

    def test_missing_type_uses_fallback(self):
        """Items without type/validator_type use fallback key."""
        from api.validators import normalize_acceptance_results_to_record
        result = normalize_acceptance_results_to_record([
            {"passed": True, "message": "OK"},
        ])
        assert "validator_0" in result
        assert result["validator_0"]["passed"] is True

    def test_canonical_record_has_all_fields(self):
        """Each entry in canonical record has all expected fields."""
        from api.validators import normalize_acceptance_results_to_record
        result = normalize_acceptance_results_to_record([
            {"type": "test_pass", "passed": True, "message": "OK"},
        ])
        entry = result["test_pass"]
        assert "passed" in entry
        assert "message" in entry
        assert "score" in entry
        assert "details" in entry
        assert "index" in entry
        assert "required" in entry
        assert "weight" in entry

    def test_defaults_for_missing_fields(self):
        """Missing fields get sensible defaults."""
        from api.validators import normalize_acceptance_results_to_record
        result = normalize_acceptance_results_to_record([
            {"type": "test_pass", "passed": True, "message": "OK"},
        ])
        entry = result["test_pass"]
        assert entry["score"] == 1.0
        assert entry["details"] == {}
        assert entry["index"] == 0
        assert entry["required"] is False
        assert entry["weight"] == 1.0


# =============================================================================
# Test 2: WebSocket AcceptanceUpdatePayload emits canonical format
# =============================================================================

class TestWebSocketCanonicalFormat:
    """Test that WebSocket payload emits canonical record format."""

    def test_to_message_has_acceptance_results_record(self):
        """to_message() includes acceptance_results as Record."""
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
                    index=1, type="file_exists", passed=True,
                    message="File exists", score=1.0, details={},
                ),
            ],
            gate_mode="all_pass",
        )

        message = payload.to_message()

        # Check acceptance_results is a Record
        assert "acceptance_results" in message
        ar = message["acceptance_results"]
        assert isinstance(ar, dict)
        assert "test_pass" in ar
        assert "file_exists" in ar
        assert ar["test_pass"]["passed"] is True
        assert ar["test_pass"]["message"] == "All tests pass"
        assert ar["file_exists"]["passed"] is True

    def test_to_message_has_validator_results_array(self):
        """to_message() still includes validator_results array for backward compat."""
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

        # validator_results still present as array
        assert "validator_results" in message
        assert isinstance(message["validator_results"], list)
        assert len(message["validator_results"]) == 1
        assert message["validator_results"][0]["type"] == "test_pass"

    def test_to_message_has_format_version(self):
        """to_message() includes format_version field."""
        from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

        payload = AcceptanceUpdatePayload(
            run_id="run-123",
            final_verdict="passed",
            validator_results=[],
            gate_mode="all_pass",
        )

        message = payload.to_message()

        assert "format_version" in message
        assert message["format_version"] == 2

    def test_to_message_type_is_correct(self):
        """to_message() type is still agent_acceptance_update."""
        from api.websocket_events import AcceptanceUpdatePayload

        payload = AcceptanceUpdatePayload(
            run_id="run-123",
            final_verdict="passed",
            validator_results=[],
            gate_mode="all_pass",
        )

        message = payload.to_message()
        assert message["type"] == "agent_acceptance_update"

    def test_acceptance_results_matches_api_format(self):
        """WS acceptance_results matches what API would return for same data."""
        from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload
        from api.validators import normalize_acceptance_results_to_record

        # Simulate the data as stored in DB (list format from AcceptanceGate)
        db_acceptance_results = [
            {"index": 0, "type": "test_pass", "passed": True, "message": "Tests pass",
             "score": 1.0, "required": True, "weight": 1.0, "details": {}},
            {"index": 1, "type": "file_exists", "passed": False, "message": "File missing",
             "score": 0.0, "required": False, "weight": 1.0, "details": {"path": "/foo"}},
        ]

        # What the API would return (normalized from DB)
        api_results = normalize_acceptance_results_to_record(db_acceptance_results)

        # What the WebSocket would emit
        ws_payload = AcceptanceUpdatePayload(
            run_id="run-123",
            final_verdict="failed",
            validator_results=[
                ValidatorResultPayload(
                    index=0, type="test_pass", passed=True,
                    message="Tests pass", score=1.0, details={},
                ),
                ValidatorResultPayload(
                    index=1, type="file_exists", passed=False,
                    message="File missing", score=0.0, details={"path": "/foo"},
                ),
            ],
            gate_mode="all_pass",
        )

        ws_message = ws_payload.to_message()
        ws_results = ws_message["acceptance_results"]

        # Both should have the same keys
        assert set(api_results.keys()) == set(ws_results.keys())

        # Both should have matching passed/message for each key
        for key in api_results:
            assert api_results[key]["passed"] == ws_results[key]["passed"], \
                f"Mismatch on '{key}' passed"
            assert api_results[key]["message"] == ws_results[key]["message"], \
                f"Mismatch on '{key}' message"
            assert api_results[key]["score"] == ws_results[key]["score"], \
                f"Mismatch on '{key}' score"
            assert api_results[key]["index"] == ws_results[key]["index"], \
                f"Mismatch on '{key}' index"

    def test_duplicate_validator_types_in_ws(self):
        """WS handles duplicate validator types correctly."""
        from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

        payload = AcceptanceUpdatePayload(
            run_id="run-123",
            final_verdict="passed",
            validator_results=[
                ValidatorResultPayload(
                    index=0, type="test_pass", passed=True,
                    message="First", score=1.0, details={},
                ),
                ValidatorResultPayload(
                    index=1, type="test_pass", passed=False,
                    message="Second", score=0.0, details={},
                ),
            ],
            gate_mode="all_pass",
        )

        message = payload.to_message()
        ar = message["acceptance_results"]
        assert "test_pass" in ar
        assert "test_pass_1" in ar


# =============================================================================
# Test 3: API endpoint uses canonical format
# =============================================================================

class TestAPICanonicalFormat:
    """Test that the API router normalizes acceptance_results."""

    def test_build_run_response_normalizes_list(self):
        """_build_run_response normalizes list to record."""
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
                {"type": "test_pass", "passed": True, "message": "OK", "score": 1.0,
                 "required": True, "weight": 1.0, "details": {}},
            ],
            "error": None,
            "retry_count": 0,
            "created_at": "2024-01-01T00:00:00+00:00",
        }

        response = _build_run_response(run_dict)

        # acceptance_results should be a dict (record format)
        assert isinstance(response.acceptance_results, dict)
        assert "test_pass" in response.acceptance_results
        assert response.acceptance_results["test_pass"]["passed"] is True

    def test_build_run_response_handles_none(self):
        """_build_run_response handles None acceptance_results."""
        from server.routers.agent_runs import _build_run_response

        run_dict = {
            "id": "run-123",
            "agent_spec_id": "spec-456",
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "turns_used": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "final_verdict": None,
            "acceptance_results": None,
            "error": None,
            "retry_count": 0,
            "created_at": "2024-01-01T00:00:00+00:00",
        }

        response = _build_run_response(run_dict)
        assert response.acceptance_results is None

    def test_build_run_response_handles_already_record(self):
        """_build_run_response passes through already-canonical records."""
        from server.routers.agent_runs import _build_run_response

        already_record = {
            "test_pass": {"passed": True, "message": "OK"},
        }

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
            "acceptance_results": already_record,
            "error": None,
            "retry_count": 0,
            "created_at": "2024-01-01T00:00:00+00:00",
        }

        response = _build_run_response(run_dict)
        assert response.acceptance_results == already_record


# =============================================================================
# Test 4: Export verification
# =============================================================================

class TestExports:
    """Test that new function is properly exported."""

    def test_normalize_exported_from_api(self):
        """normalize_acceptance_results_to_record exported from api package."""
        from api import normalize_acceptance_results_to_record
        assert callable(normalize_acceptance_results_to_record)

    def test_normalize_in_validators_module(self):
        """normalize_acceptance_results_to_record in api.validators."""
        from api.validators import normalize_acceptance_results_to_record
        assert callable(normalize_acceptance_results_to_record)


# =============================================================================
# Test 5: Integration - verify structure identity between API and WS
# =============================================================================

class TestStructureIdentity:
    """Verify API and WS return identical structures for same data."""

    def test_both_emit_record_with_same_keys(self):
        """Both API and WS emit Record<string, AcceptanceValidatorResult>."""
        from api.validators import normalize_acceptance_results_to_record
        from api.websocket_events import AcceptanceUpdatePayload, ValidatorResultPayload

        # Common test data
        validators = [
            {"index": 0, "type": "test_pass", "passed": True, "message": "OK",
             "score": 1.0, "required": True, "weight": 1.0, "details": {}},
            {"index": 1, "type": "forbidden_patterns", "passed": True, "message": "Clean",
             "score": 1.0, "required": False, "weight": 1.0, "details": {}},
        ]

        # API path: normalize list from DB
        api_result = normalize_acceptance_results_to_record(validators)

        # WS path: build from ValidatorResultPayload
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

        # Structure identity check
        assert set(api_result.keys()) == set(ws_result.keys()), \
            f"Key mismatch: API={set(api_result.keys())} vs WS={set(ws_result.keys())}"

        for key in api_result:
            # Core fields match
            assert api_result[key]["passed"] == ws_result[key]["passed"]
            assert api_result[key]["message"] == ws_result[key]["message"]
            assert api_result[key]["score"] == ws_result[key]["score"]
            assert api_result[key]["index"] == ws_result[key]["index"]
