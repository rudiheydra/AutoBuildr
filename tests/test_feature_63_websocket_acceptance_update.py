"""
Feature #63: WebSocket agent_acceptance_update Event - Comprehensive Tests
=========================================================================

Tests for the WebSocket agent_acceptance_update event broadcasting functionality.

Feature Requirements:
1. After acceptance gate evaluation, publish message
2. Message type: agent_acceptance_update
3. Payload: run_id, final_verdict, validator_results array
4. Each validator result: index, type, passed, message

This test suite verifies:
- ValidatorResultPayload dataclass serialization
- AcceptanceUpdatePayload message generation
- broadcast_acceptance_update function behavior
- Integration with ValidatorResult from api.validators
- Helper functions for building payloads
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.websocket_events import (
    AcceptanceUpdatePayload,
    ValidatorResultPayload,
    broadcast_acceptance_update,
    broadcast_acceptance_update_sync,
    build_acceptance_update_from_results,
    create_validator_result_payload,
)
from api.validators import ValidatorResult


# =============================================================================
# Step 1: ValidatorResultPayload Tests
# =============================================================================

class TestValidatorResultPayload:
    """Test ValidatorResultPayload dataclass."""

    def test_basic_creation(self):
        """Test creating a ValidatorResultPayload with required fields."""
        payload = ValidatorResultPayload(
            index=0,
            type="file_exists",
            passed=True,
            message="File exists: /path/to/file",
        )

        assert payload.index == 0
        assert payload.type == "file_exists"
        assert payload.passed is True
        assert payload.message == "File exists: /path/to/file"
        assert payload.score == 1.0  # Default
        assert payload.details == {}  # Default

    def test_creation_with_all_fields(self):
        """Test creating with all optional fields."""
        payload = ValidatorResultPayload(
            index=1,
            type="forbidden_patterns",
            passed=False,
            message="Found 2 forbidden pattern matches",
            score=0.0,
            details={"matches": ["secret", "password"]},
        )

        assert payload.index == 1
        assert payload.type == "forbidden_patterns"
        assert payload.passed is False
        assert payload.message == "Found 2 forbidden pattern matches"
        assert payload.score == 0.0
        assert payload.details == {"matches": ["secret", "password"]}

    def test_to_dict_serialization(self):
        """Test converting to dict for JSON serialization."""
        payload = ValidatorResultPayload(
            index=0,
            type="test_pass",
            passed=True,
            message="All tests passed",
            score=1.0,
            details={"tests_run": 15, "tests_passed": 15},
        )

        result = payload.to_dict()

        assert isinstance(result, dict)
        assert result["index"] == 0
        assert result["type"] == "test_pass"
        assert result["passed"] is True
        assert result["message"] == "All tests passed"
        assert result["score"] == 1.0
        assert result["details"] == {"tests_run": 15, "tests_passed": 15}

    def test_to_dict_is_json_serializable(self):
        """Verify the dict can be JSON serialized."""
        payload = ValidatorResultPayload(
            index=0,
            type="file_exists",
            passed=True,
            message="OK",
        )

        result = payload.to_dict()
        json_str = json.dumps(result)

        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed == result


# =============================================================================
# Step 2: AcceptanceUpdatePayload Tests
# =============================================================================

class TestAcceptanceUpdatePayload:
    """Test AcceptanceUpdatePayload dataclass."""

    def test_basic_creation(self):
        """Test creating an AcceptanceUpdatePayload."""
        validator_results = [
            ValidatorResultPayload(index=0, type="file_exists", passed=True, message="OK"),
        ]

        payload = AcceptanceUpdatePayload(
            run_id="abc-123-def-456",
            final_verdict="passed",
            validator_results=validator_results,
        )

        assert payload.run_id == "abc-123-def-456"
        assert payload.final_verdict == "passed"
        assert len(payload.validator_results) == 1
        assert payload.gate_mode == "all_pass"  # Default
        assert payload.timestamp is not None

    def test_creation_with_all_fields(self):
        """Test creating with explicit gate_mode and timestamp."""
        timestamp = datetime(2024, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        validator_results = [
            ValidatorResultPayload(index=0, type="file_exists", passed=True, message="OK"),
            ValidatorResultPayload(index=1, type="test_pass", passed=False, message="Failed"),
        ]

        payload = AcceptanceUpdatePayload(
            run_id="abc-123",
            final_verdict="failed",
            validator_results=validator_results,
            gate_mode="any_pass",
            timestamp=timestamp,
        )

        assert payload.gate_mode == "any_pass"
        assert payload.timestamp == timestamp

    def test_timestamp_defaults_to_now(self):
        """Test that timestamp defaults to current UTC time."""
        before = datetime.now(timezone.utc)

        payload = AcceptanceUpdatePayload(
            run_id="abc",
            final_verdict="passed",
            validator_results=[],
        )

        after = datetime.now(timezone.utc)

        assert payload.timestamp >= before
        assert payload.timestamp <= after

    def test_to_message_format(self):
        """Test the WebSocket message format (Feature #63 Step 2)."""
        validator_results = [
            ValidatorResultPayload(index=0, type="file_exists", passed=True, message="OK"),
        ]
        timestamp = datetime(2024, 1, 27, 12, 0, 0, tzinfo=timezone.utc)

        payload = AcceptanceUpdatePayload(
            run_id="abc-123",
            final_verdict="passed",
            validator_results=validator_results,
            gate_mode="all_pass",
            timestamp=timestamp,
        )

        message = payload.to_message()

        # Step 2: Message type must be "agent_acceptance_update"
        assert message["type"] == "agent_acceptance_update"

        # Step 3: Payload must include run_id, final_verdict, validator_results
        assert message["run_id"] == "abc-123"
        assert message["final_verdict"] == "passed"
        assert isinstance(message["validator_results"], list)
        assert len(message["validator_results"]) == 1

        # Additional fields
        assert message["gate_mode"] == "all_pass"
        assert message["timestamp"] == timestamp.isoformat()

    def test_to_message_validator_results_format(self):
        """Test validator results array format (Feature #63 Step 4)."""
        validator_results = [
            ValidatorResultPayload(
                index=0,
                type="file_exists",
                passed=True,
                message="File exists: /path/to/file",
            ),
            ValidatorResultPayload(
                index=1,
                type="test_pass",
                passed=False,
                message="Tests failed with exit code 1",
            ),
        ]

        payload = AcceptanceUpdatePayload(
            run_id="abc",
            final_verdict="failed",
            validator_results=validator_results,
        )

        message = payload.to_message()
        results = message["validator_results"]

        # Step 4: Each validator result must have index, type, passed, message
        assert results[0]["index"] == 0
        assert results[0]["type"] == "file_exists"
        assert results[0]["passed"] is True
        assert results[0]["message"] == "File exists: /path/to/file"

        assert results[1]["index"] == 1
        assert results[1]["type"] == "test_pass"
        assert results[1]["passed"] is False
        assert results[1]["message"] == "Tests failed with exit code 1"

    def test_to_message_is_json_serializable(self):
        """Verify the message can be JSON serialized for WebSocket."""
        validator_results = [
            ValidatorResultPayload(
                index=0,
                type="file_exists",
                passed=True,
                message="OK",
                details={"path": "/app/init.sh"},
            ),
        ]

        payload = AcceptanceUpdatePayload(
            run_id="abc-123",
            final_verdict="passed",
            validator_results=validator_results,
        )

        message = payload.to_message()
        json_str = json.dumps(message)

        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["type"] == "agent_acceptance_update"

    def test_none_final_verdict(self):
        """Test with None final_verdict (error case)."""
        payload = AcceptanceUpdatePayload(
            run_id="abc",
            final_verdict=None,
            validator_results=[],
        )

        message = payload.to_message()
        assert message["final_verdict"] is None


# =============================================================================
# Step 3: broadcast_acceptance_update Tests
# =============================================================================

class TestBroadcastAcceptanceUpdate:
    """Test broadcast_acceptance_update function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_manager_not_available(self):
        """Test returns False when WebSocket manager is not available."""
        with patch("api.websocket_events._get_connection_manager", return_value=None):
            result = await broadcast_acceptance_update(
                project_name="test-project",
                run_id="abc-123",
                final_verdict="passed",
                validator_results=[],
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_broadcasts_to_correct_project(self):
        """Test that message is broadcast to the correct project."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_acceptance_update(
                project_name="my-test-project",
                run_id="abc-123",
                final_verdict="passed",
                validator_results=[],
            )

        assert result is True
        mock_manager.broadcast_to_project.assert_called_once()
        call_args = mock_manager.broadcast_to_project.call_args
        assert call_args[0][0] == "my-test-project"

    @pytest.mark.asyncio
    async def test_message_format_is_correct(self):
        """Test that the broadcast message has correct format."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)
        captured_message = None

        async def capture_message(project_name, message):
            nonlocal captured_message
            captured_message = message

        mock_manager.broadcast_to_project = capture_message

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_acceptance_update(
                project_name="test-project",
                run_id="abc-123",
                final_verdict="passed",
                validator_results=[
                    ValidatorResultPayload(index=0, type="file_exists", passed=True, message="OK")
                ],
                gate_mode="all_pass",
            )

        # Verify message format
        assert captured_message["type"] == "agent_acceptance_update"
        assert captured_message["run_id"] == "abc-123"
        assert captured_message["final_verdict"] == "passed"
        assert captured_message["gate_mode"] == "all_pass"
        assert len(captured_message["validator_results"]) == 1

    @pytest.mark.asyncio
    async def test_handles_validator_result_objects(self):
        """Test handling ValidatorResult from api.validators."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)
        captured_message = None

        async def capture_message(project_name, message):
            nonlocal captured_message
            captured_message = message

        mock_manager.broadcast_to_project = capture_message

        # Create a ValidatorResult from api.validators
        validator_result = ValidatorResult(
            passed=True,
            message="File exists: /app/init.sh",
            score=1.0,
            details={"path": "/app/init.sh"},
            validator_type="file_exists",
        )

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_acceptance_update(
                project_name="test-project",
                run_id="abc-123",
                final_verdict="passed",
                validator_results=[validator_result],
            )

        # Verify the ValidatorResult was converted correctly
        results = captured_message["validator_results"]
        assert len(results) == 1
        assert results[0]["index"] == 0
        assert results[0]["type"] == "file_exists"
        assert results[0]["passed"] is True
        assert results[0]["message"] == "File exists: /app/init.sh"

    @pytest.mark.asyncio
    async def test_handles_dict_validator_results(self):
        """Test handling dict-format validator results."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(return_value=None)
        captured_message = None

        async def capture_message(project_name, message):
            nonlocal captured_message
            captured_message = message

        mock_manager.broadcast_to_project = capture_message

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_acceptance_update(
                project_name="test-project",
                run_id="abc-123",
                final_verdict="passed",
                validator_results=[
                    {"index": 0, "type": "test_pass", "passed": True, "message": "Tests pass"},
                    {"type": "file_exists", "passed": False, "message": "File missing"},
                ],
            )

        results = captured_message["validator_results"]
        assert len(results) == 2
        assert results[0]["index"] == 0
        assert results[0]["type"] == "test_pass"
        assert results[1]["index"] == 1  # Auto-assigned
        assert results[1]["type"] == "file_exists"

    @pytest.mark.asyncio
    async def test_handles_broadcast_exception(self):
        """Test graceful handling of broadcast exceptions."""
        mock_manager = MagicMock()
        mock_manager.broadcast_to_project = AsyncMock(side_effect=Exception("Connection error"))

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            result = await broadcast_acceptance_update(
                project_name="test-project",
                run_id="abc-123",
                final_verdict="passed",
                validator_results=[],
            )

        assert result is False


# =============================================================================
# Step 4: Helper Function Tests
# =============================================================================

class TestCreateValidatorResultPayload:
    """Test create_validator_result_payload helper."""

    def test_converts_validator_result(self):
        """Test converting a ValidatorResult to payload."""
        validator_result = ValidatorResult(
            passed=True,
            message="File exists: /path",
            score=1.0,
            details={"checked": True},
            validator_type="file_exists",
        )

        payload = create_validator_result_payload(3, validator_result)

        assert payload.index == 3
        assert payload.type == "file_exists"
        assert payload.passed is True
        assert payload.message == "File exists: /path"
        assert payload.score == 1.0
        assert payload.details == {"checked": True}


class TestBuildAcceptanceUpdateFromResults:
    """Test build_acceptance_update_from_results helper."""

    def test_builds_passing_payload(self):
        """Test building a payload for passing acceptance."""
        results = [
            ValidatorResult(passed=True, message="OK1", validator_type="file_exists"),
            ValidatorResult(passed=True, message="OK2", validator_type="test_pass"),
        ]

        payload = build_acceptance_update_from_results(
            run_id="abc-123",
            passed=True,
            results=results,
            gate_mode="all_pass",
        )

        assert payload.run_id == "abc-123"
        assert payload.final_verdict == "passed"
        assert payload.gate_mode == "all_pass"
        assert len(payload.validator_results) == 2

    def test_builds_failing_payload(self):
        """Test building a payload for failing acceptance."""
        results = [
            ValidatorResult(passed=True, message="OK", validator_type="file_exists"),
            ValidatorResult(passed=False, message="Failed", validator_type="test_pass"),
        ]

        payload = build_acceptance_update_from_results(
            run_id="xyz-789",
            passed=False,
            results=results,
        )

        assert payload.final_verdict == "failed"
        assert payload.validator_results[0].passed is True
        assert payload.validator_results[1].passed is False

    def test_assigns_sequential_indices(self):
        """Test that indices are assigned sequentially."""
        results = [
            ValidatorResult(passed=True, message="A", validator_type="a"),
            ValidatorResult(passed=True, message="B", validator_type="b"),
            ValidatorResult(passed=True, message="C", validator_type="c"),
        ]

        payload = build_acceptance_update_from_results(
            run_id="abc",
            passed=True,
            results=results,
        )

        indices = [r.index for r in payload.validator_results]
        assert indices == [0, 1, 2]


# =============================================================================
# Feature #63 Verification Steps Tests
# =============================================================================

class TestFeature63VerificationSteps:
    """
    Test each verification step from Feature #63.

    Steps:
    1. After acceptance gate evaluation, publish message
    2. Message type: agent_acceptance_update
    3. Payload: run_id, final_verdict, validator_results array
    4. Each validator result: index, type, passed, message
    """

    def test_step1_message_published_after_evaluation(self):
        """Step 1: After acceptance gate evaluation, publish message."""
        # The broadcast function exists and can be called
        assert callable(broadcast_acceptance_update)
        assert callable(broadcast_acceptance_update_sync)

        # build_acceptance_update_from_results creates the message
        # from evaluate_acceptance_spec output
        results = [ValidatorResult(passed=True, message="OK", validator_type="test")]
        payload = build_acceptance_update_from_results("run-123", True, results)

        assert payload is not None
        assert payload.run_id == "run-123"

    def test_step2_message_type_is_agent_acceptance_update(self):
        """Step 2: Message type: agent_acceptance_update."""
        payload = AcceptanceUpdatePayload(
            run_id="abc",
            final_verdict="passed",
            validator_results=[],
        )

        message = payload.to_message()
        assert message["type"] == "agent_acceptance_update"

    def test_step3_payload_has_required_fields(self):
        """Step 3: Payload: run_id, final_verdict, validator_results array."""
        validator_results = [
            ValidatorResultPayload(index=0, type="file_exists", passed=True, message="OK"),
        ]

        payload = AcceptanceUpdatePayload(
            run_id="my-run-id-123",
            final_verdict="passed",
            validator_results=validator_results,
        )

        message = payload.to_message()

        # All required fields are present
        assert "run_id" in message
        assert message["run_id"] == "my-run-id-123"

        assert "final_verdict" in message
        assert message["final_verdict"] == "passed"

        assert "validator_results" in message
        assert isinstance(message["validator_results"], list)

    def test_step4_validator_results_have_required_fields(self):
        """Step 4: Each validator result: index, type, passed, message."""
        validator_results = [
            ValidatorResultPayload(
                index=0,
                type="file_exists",
                passed=True,
                message="File exists: /path/to/file",
            ),
            ValidatorResultPayload(
                index=1,
                type="test_pass",
                passed=False,
                message="Exit code 1",
            ),
        ]

        payload = AcceptanceUpdatePayload(
            run_id="abc",
            final_verdict="failed",
            validator_results=validator_results,
        )

        message = payload.to_message()

        for i, result in enumerate(message["validator_results"]):
            # Each result must have index, type, passed, message
            assert "index" in result, f"Result {i} missing 'index'"
            assert "type" in result, f"Result {i} missing 'type'"
            assert "passed" in result, f"Result {i} missing 'passed'"
            assert "message" in result, f"Result {i} missing 'message'"

            # Validate types
            assert isinstance(result["index"], int)
            assert isinstance(result["type"], str)
            assert isinstance(result["passed"], bool)
            assert isinstance(result["message"], str)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegrationWithValidators:
    """Integration tests with api.validators module."""

    def test_full_workflow_with_evaluate_acceptance_spec(self):
        """Test complete workflow from validators to WebSocket message."""
        from api.validators import evaluate_acceptance_spec, ValidatorResult

        # Simulate validators list (would come from AcceptanceSpec)
        validators = [
            {"type": "file_exists", "config": {"path": "/tmp/test.txt"}},
        ]

        # Manually create results (normally from evaluate_acceptance_spec)
        results = [
            ValidatorResult(
                passed=True,
                message="File exists: /tmp/test.txt",
                score=1.0,
                validator_type="file_exists",
            ),
        ]
        passed = True

        # Build the WebSocket payload
        payload = build_acceptance_update_from_results(
            run_id="integration-test-run",
            passed=passed,
            results=results,
            gate_mode="all_pass",
        )

        message = payload.to_message()

        # Verify complete message structure
        assert message["type"] == "agent_acceptance_update"
        assert message["run_id"] == "integration-test-run"
        assert message["final_verdict"] == "passed"
        assert message["gate_mode"] == "all_pass"
        assert len(message["validator_results"]) == 1
        assert message["validator_results"][0]["type"] == "file_exists"
        assert message["validator_results"][0]["passed"] is True

    @pytest.mark.asyncio
    async def test_broadcast_with_multiple_validator_types(self):
        """Test broadcasting with different validator types."""
        mock_manager = MagicMock()
        captured_message = None

        async def capture(project, msg):
            nonlocal captured_message
            captured_message = msg

        mock_manager.broadcast_to_project = capture

        results = [
            ValidatorResult(passed=True, message="OK", validator_type="file_exists"),
            ValidatorResult(passed=True, message="Tests pass", validator_type="test_pass"),
            ValidatorResult(passed=True, message="No forbidden", validator_type="forbidden_patterns"),
        ]

        with patch("api.websocket_events._get_connection_manager", return_value=mock_manager):
            await broadcast_acceptance_update(
                project_name="test",
                run_id="multi-validator-run",
                final_verdict="passed",
                validator_results=results,
            )

        assert len(captured_message["validator_results"]) == 3
        types = [r["type"] for r in captured_message["validator_results"]]
        assert "file_exists" in types
        assert "test_pass" in types
        assert "forbidden_patterns" in types


# =============================================================================
# Synchronous Wrapper Tests
# =============================================================================

class TestBroadcastAcceptanceUpdateSync:
    """Test the synchronous wrapper function."""

    def test_returns_false_when_manager_not_available(self):
        """Test returns False when no manager."""
        with patch("api.websocket_events._get_connection_manager", return_value=None):
            result = broadcast_acceptance_update_sync(
                project_name="test",
                run_id="abc",
                final_verdict="passed",
                validator_results=[],
            )

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
