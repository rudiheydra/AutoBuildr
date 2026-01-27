"""
Test Suite for Feature #76: HarnessKernel Error Recovery
=========================================================

Tests for error recovery in HarnessKernel with retry logic and graceful failure handling.

Feature Steps:
1. Wrap Claude API calls in try/except
2. Catch RateLimitError and retry with backoff
3. Catch APIError and record in run.error
4. Catch tool execution exceptions
5. Record failed event with error details
6. Check retry_policy and max_retries
7. If retries available, increment retry_count and retry
8. If no retries, set status to failed and finalize
"""

import pytest
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from typing import Any

# Import the module under test
from api.error_recovery import (
    # Constants
    RETRY_INITIAL_DELAY_SECONDS,
    RETRY_MAX_DELAY_SECONDS,
    RETRY_EXPONENTIAL_BASE,
    RETRY_JITTER_FACTOR,
    RETRYABLE_ERROR_TYPES,
    NON_RETRYABLE_ERROR_TYPES,
    # Exception classes
    APIRecoveryError,
    RateLimitRecoveryError,
    InternalServerRecoveryError,
    ConnectionRecoveryError,
    TimeoutRecoveryError,
    AuthenticationRecoveryError,
    BadRequestRecoveryError,
    ToolExecutionRecoveryError,
    # Helper functions
    classify_anthropic_error,
    classify_tool_error,
    calculate_backoff_delay,
    should_retry_error,
    get_retry_policy_from_spec,
    create_error_event_payload,
    record_error_event,
    record_retry_event,
    increment_retry_count,
    finalize_run_on_error,
    handle_api_error,
    handle_tool_error,
    ErrorRecoveryResult,
    # Anthropic error types
    ANTHROPIC_AVAILABLE,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    return db


@pytest.fixture
def mock_run():
    """Create a mock AgentRun."""
    run = MagicMock()
    run.id = str(uuid.uuid4())
    run.retry_count = 0
    run.fail = MagicMock()
    return run


@pytest.fixture
def mock_spec_no_retry():
    """Create a mock AgentSpec with no retry policy."""
    spec = MagicMock()
    spec.acceptance_spec = MagicMock()
    spec.acceptance_spec.retry_policy = "none"
    spec.acceptance_spec.max_retries = 0
    return spec


@pytest.fixture
def mock_spec_with_retry():
    """Create a mock AgentSpec with retry policy."""
    spec = MagicMock()
    spec.acceptance_spec = MagicMock()
    spec.acceptance_spec.retry_policy = "exponential"
    spec.acceptance_spec.max_retries = 3
    return spec


# =============================================================================
# Test Exception Classes
# =============================================================================

class TestAPIRecoveryError:
    """Tests for APIRecoveryError base class."""

    def test_creates_with_all_attributes(self):
        """Test creating an APIRecoveryError with all attributes."""
        error = APIRecoveryError(
            error_type="test_error",
            message="Test error message",
            original_error=ValueError("original"),
            is_retryable=True,
            retry_after=5.0,
        )

        assert error.error_type == "test_error"
        assert str(error) == "Test error message"
        assert error.is_retryable is True
        assert error.retry_after == 5.0
        assert isinstance(error.original_error, ValueError)

    def test_to_dict(self):
        """Test converting error to dictionary."""
        error = APIRecoveryError(
            error_type="test",
            message="test message",
            is_retryable=True,
            retry_after=10.0,
        )

        d = error.to_dict()

        assert d["error_type"] == "test"
        assert d["message"] == "test message"
        assert d["is_retryable"] is True
        assert d["retry_after"] == 10.0


class TestRateLimitRecoveryError:
    """Tests for RateLimitRecoveryError."""

    def test_is_retryable(self):
        """Test that rate limit errors are always retryable."""
        error = RateLimitRecoveryError()
        assert error.is_retryable is True
        assert error.error_type == "rate_limit"

    def test_includes_retry_after(self):
        """Test that retry_after is preserved."""
        error = RateLimitRecoveryError(retry_after=30.0)
        assert error.retry_after == 30.0


class TestInternalServerRecoveryError:
    """Tests for InternalServerRecoveryError."""

    def test_is_retryable(self):
        """Test that internal server errors are retryable."""
        error = InternalServerRecoveryError()
        assert error.is_retryable is True
        assert error.error_type == "internal_server"


class TestConnectionRecoveryError:
    """Tests for ConnectionRecoveryError."""

    def test_is_retryable(self):
        """Test that connection errors are retryable."""
        error = ConnectionRecoveryError()
        assert error.is_retryable is True
        assert error.error_type == "connection"


class TestTimeoutRecoveryError:
    """Tests for TimeoutRecoveryError."""

    def test_is_retryable(self):
        """Test that timeout errors are retryable."""
        error = TimeoutRecoveryError()
        assert error.is_retryable is True
        assert error.error_type == "timeout"


class TestAuthenticationRecoveryError:
    """Tests for AuthenticationRecoveryError."""

    def test_not_retryable(self):
        """Test that authentication errors are NOT retryable."""
        error = AuthenticationRecoveryError()
        assert error.is_retryable is False
        assert error.error_type == "authentication"


class TestBadRequestRecoveryError:
    """Tests for BadRequestRecoveryError."""

    def test_not_retryable(self):
        """Test that bad request errors are NOT retryable."""
        error = BadRequestRecoveryError()
        assert error.is_retryable is False
        assert error.error_type == "bad_request"


class TestToolExecutionRecoveryError:
    """Tests for ToolExecutionRecoveryError."""

    def test_includes_tool_name(self):
        """Test that tool name is included."""
        error = ToolExecutionRecoveryError(tool_name="my_tool")
        assert error.tool_name == "my_tool"
        assert error.error_type == "tool_execution"
        assert "my_tool" in str(error)

    def test_to_dict_includes_tool_name(self):
        """Test that to_dict includes tool_name."""
        error = ToolExecutionRecoveryError(tool_name="Read")
        d = error.to_dict()
        assert d["tool_name"] == "Read"


# =============================================================================
# Test Error Classification (Feature #76, Steps 1-4)
# =============================================================================

class TestClassifyAnthropicError:
    """Tests for classify_anthropic_error function."""

    @pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
    def test_classifies_rate_limit_error(self):
        """Step 2: Test classification of RateLimitError."""
        from anthropic import RateLimitError

        # Create a mock rate limit error
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"retry-after": "30"}

        original = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"type": "rate_limit_error"}},
        )

        result = classify_anthropic_error(original)

        assert isinstance(result, RateLimitRecoveryError)
        assert result.is_retryable is True

    def test_classifies_unknown_error(self):
        """Test classification of unknown error types."""
        error = ValueError("Unknown error")
        result = classify_anthropic_error(error)

        assert isinstance(result, APIRecoveryError)
        assert result.error_type == "unknown"
        assert result.is_retryable is False


class TestClassifyToolError:
    """Tests for classify_tool_error function."""

    def test_classifies_basic_tool_error(self):
        """Step 4: Test classification of tool execution error."""
        error = RuntimeError("Tool failed")
        result = classify_tool_error("my_tool", error)

        assert isinstance(result, ToolExecutionRecoveryError)
        assert result.tool_name == "my_tool"

    def test_timeout_error_is_retryable(self):
        """Test that timeout-related tool errors are retryable."""
        error = RuntimeError("Connection timeout occurred")
        result = classify_tool_error("api_call", error)

        assert result.is_retryable is True

    def test_network_error_is_retryable(self):
        """Test that network-related tool errors are retryable."""
        error = RuntimeError("Network connection failed")
        result = classify_tool_error("fetch", error)

        assert result.is_retryable is True


# =============================================================================
# Test Backoff Calculation (Feature #76, Step 2)
# =============================================================================

class TestCalculateBackoffDelay:
    """Tests for calculate_backoff_delay function."""

    def test_first_retry_uses_initial_delay(self):
        """Test that first retry uses approximately initial delay."""
        delay = calculate_backoff_delay(retry_attempt=0, jitter_factor=0)
        assert delay == RETRY_INITIAL_DELAY_SECONDS

    def test_exponential_growth(self):
        """Test that delay grows exponentially."""
        delay0 = calculate_backoff_delay(retry_attempt=0, jitter_factor=0)
        delay1 = calculate_backoff_delay(retry_attempt=1, jitter_factor=0)
        delay2 = calculate_backoff_delay(retry_attempt=2, jitter_factor=0)

        assert delay1 == delay0 * RETRY_EXPONENTIAL_BASE
        assert delay2 == delay1 * RETRY_EXPONENTIAL_BASE

    def test_respects_max_delay(self):
        """Test that delay never exceeds max_delay."""
        delay = calculate_backoff_delay(retry_attempt=100, jitter_factor=0)
        assert delay <= RETRY_MAX_DELAY_SECONDS

    def test_uses_retry_after_when_provided(self):
        """Test that retry_after from server is respected."""
        delay = calculate_backoff_delay(retry_attempt=0, retry_after=25.0)
        assert delay == 25.0

    def test_retry_after_respects_max_delay(self):
        """Test that retry_after is capped by max_delay."""
        delay = calculate_backoff_delay(
            retry_attempt=0,
            retry_after=1000.0,
            max_delay=60.0,
        )
        assert delay == 60.0

    def test_jitter_adds_randomness(self):
        """Test that jitter adds random variation."""
        delays = [calculate_backoff_delay(retry_attempt=0, jitter_factor=0.5) for _ in range(10)]
        # Should have some variation
        assert len(set(delays)) > 1


# =============================================================================
# Test Retry Policy Evaluation (Feature #76, Step 6)
# =============================================================================

class TestShouldRetryError:
    """Tests for should_retry_error function."""

    def test_no_retry_with_none_policy(self):
        """Test that 'none' policy never retries."""
        error = RateLimitRecoveryError()
        should_retry = should_retry_error(
            error=error,
            retry_attempt=0,
            max_retries=5,
            retry_policy="none",
        )
        assert should_retry is False

    def test_no_retry_for_non_retryable_error(self):
        """Test that non-retryable errors are not retried."""
        error = AuthenticationRecoveryError()
        should_retry = should_retry_error(
            error=error,
            retry_attempt=0,
            max_retries=5,
            retry_policy="exponential",
        )
        assert should_retry is False

    def test_no_retry_when_max_retries_reached(self):
        """Test that retries stop when max_retries reached."""
        error = RateLimitRecoveryError()
        should_retry = should_retry_error(
            error=error,
            retry_attempt=5,  # Already at max
            max_retries=5,
            retry_policy="exponential",
        )
        assert should_retry is False

    def test_retry_when_conditions_met(self):
        """Test that retry happens when all conditions are met."""
        error = RateLimitRecoveryError()
        should_retry = should_retry_error(
            error=error,
            retry_attempt=2,
            max_retries=5,
            retry_policy="exponential",
        )
        assert should_retry is True

    def test_fixed_policy_allows_retry(self):
        """Test that 'fixed' policy allows retries."""
        error = InternalServerRecoveryError()
        should_retry = should_retry_error(
            error=error,
            retry_attempt=0,
            max_retries=2,
            retry_policy="fixed",
        )
        assert should_retry is True


class TestGetRetryPolicyFromSpec:
    """Tests for get_retry_policy_from_spec function."""

    def test_extracts_retry_policy(self, mock_spec_with_retry):
        """Test extracting retry policy from spec."""
        policy, max_retries = get_retry_policy_from_spec(mock_spec_with_retry)
        assert policy == "exponential"
        assert max_retries == 3

    def test_defaults_when_no_acceptance_spec(self):
        """Test defaults when spec has no acceptance_spec."""
        spec = MagicMock()
        spec.acceptance_spec = None

        policy, max_retries = get_retry_policy_from_spec(spec)
        assert policy == "none"
        assert max_retries == 0

    def test_defaults_for_missing_fields(self):
        """Test defaults when acceptance_spec has missing fields."""
        spec = MagicMock()
        spec.acceptance_spec = MagicMock()
        spec.acceptance_spec.retry_policy = None
        spec.acceptance_spec.max_retries = None

        policy, max_retries = get_retry_policy_from_spec(spec)
        assert policy == "none"
        assert max_retries == 0


# =============================================================================
# Test Event Recording (Feature #76, Step 5)
# =============================================================================

class TestCreateErrorEventPayload:
    """Tests for create_error_event_payload function."""

    def test_creates_complete_payload(self):
        """Test creating a complete error event payload."""
        error = RateLimitRecoveryError()
        payload = create_error_event_payload(
            error=error,
            retry_attempt=1,
            max_retries=3,
            will_retry=True,
        )

        assert "error" in payload
        assert payload["retry_attempt"] == 1
        assert payload["max_retries"] == 3
        assert payload["will_retry"] is True
        assert "timestamp" in payload


class TestRecordErrorEvent:
    """Tests for record_error_event function."""

    def test_records_error_event(self, mock_db):
        """Step 5: Test recording failed event with error details."""
        error = RateLimitRecoveryError()

        with patch('api.agentspec_models.AgentEvent') as MockEvent:
            event_instance = MagicMock()
            MockEvent.return_value = event_instance

            result = record_error_event(
                db=mock_db,
                run_id="test-run-id",
                sequence=1,
                error=error,
                retry_attempt=0,
                max_retries=3,
                will_retry=True,
            )

            mock_db.add.assert_called_once()
            assert MockEvent.called


# =============================================================================
# Test Run Update Helpers (Feature #76, Steps 7-8)
# =============================================================================

class TestIncrementRetryCount:
    """Tests for increment_retry_count function."""

    def test_increments_from_zero(self, mock_run):
        """Step 7: Test incrementing retry count from zero."""
        mock_run.retry_count = 0
        result = increment_retry_count(mock_run)

        assert result == 1
        assert mock_run.retry_count == 1

    def test_increments_from_existing(self, mock_run):
        """Test incrementing existing retry count."""
        mock_run.retry_count = 2
        result = increment_retry_count(mock_run)

        assert result == 3
        assert mock_run.retry_count == 3

    def test_handles_none_retry_count(self, mock_run):
        """Test handling None retry count."""
        mock_run.retry_count = None
        result = increment_retry_count(mock_run)

        assert result == 1
        assert mock_run.retry_count == 1


class TestFinalizeRunOnError:
    """Tests for finalize_run_on_error function."""

    def test_calls_fail_with_error_message(self, mock_run):
        """Step 8: Test finalizing run with proper error message."""
        error = RateLimitRecoveryError(message="Rate limit hit")
        finalize_run_on_error(mock_run, error)

        mock_run.fail.assert_called_once()
        call_args = mock_run.fail.call_args
        assert "rate_limit" in call_args[1]["error_message"]


# =============================================================================
# Test High-Level Error Recovery (Feature #76, Complete Flow)
# =============================================================================

class TestHandleApiError:
    """Tests for handle_api_error function."""

    def test_returns_retry_for_retryable_error(self, mock_db, mock_run, mock_spec_with_retry):
        """Test that retryable errors return retry result."""
        with patch('api.error_recovery.classify_anthropic_error') as mock_classify:
            mock_classify.return_value = RateLimitRecoveryError()

            with patch('api.error_recovery.record_error_event'):
                result = handle_api_error(
                    error=Exception("Rate limit"),
                    run=mock_run,
                    spec=mock_spec_with_retry,
                    db=mock_db,
                    event_sequence=1,
                )

                assert result.should_retry is True
                assert result.delay_seconds > 0
                assert result.retry_attempt == 1

    def test_no_retry_for_non_retryable_error(self, mock_db, mock_run, mock_spec_with_retry):
        """Test that non-retryable errors don't retry."""
        with patch('api.error_recovery.classify_anthropic_error') as mock_classify:
            mock_classify.return_value = AuthenticationRecoveryError()

            with patch('api.error_recovery.record_error_event'):
                result = handle_api_error(
                    error=Exception("Auth failed"),
                    run=mock_run,
                    spec=mock_spec_with_retry,
                    db=mock_db,
                    event_sequence=1,
                )

                assert result.should_retry is False
                assert result.final_error_message is not None

    def test_no_retry_with_none_policy(self, mock_db, mock_run, mock_spec_no_retry):
        """Test that 'none' policy prevents retries."""
        with patch('api.error_recovery.classify_anthropic_error') as mock_classify:
            mock_classify.return_value = RateLimitRecoveryError()

            with patch('api.error_recovery.record_error_event'):
                result = handle_api_error(
                    error=Exception("Rate limit"),
                    run=mock_run,
                    spec=mock_spec_no_retry,
                    db=mock_db,
                    event_sequence=1,
                )

                assert result.should_retry is False


class TestHandleToolError:
    """Tests for handle_tool_error function."""

    def test_handles_tool_error(self, mock_db, mock_run, mock_spec_with_retry):
        """Step 4: Test handling tool execution exceptions."""
        with patch('api.error_recovery.record_error_event'):
            result = handle_tool_error(
                tool_name="Read",
                error=RuntimeError("File not found"),
                run=mock_run,
                spec=mock_spec_with_retry,
                db=mock_db,
                event_sequence=1,
            )

            assert isinstance(result, ErrorRecoveryResult)
            assert result.error is not None
            assert result.error.tool_name == "Read"


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_retryable_error_types(self):
        """Test retryable error types are defined."""
        assert "rate_limit" in RETRYABLE_ERROR_TYPES
        assert "internal_server" in RETRYABLE_ERROR_TYPES
        assert "connection" in RETRYABLE_ERROR_TYPES
        assert "timeout" in RETRYABLE_ERROR_TYPES

    def test_non_retryable_error_types(self):
        """Test non-retryable error types are defined."""
        assert "authentication" in NON_RETRYABLE_ERROR_TYPES
        assert "bad_request" in NON_RETRYABLE_ERROR_TYPES
        assert "unknown" in NON_RETRYABLE_ERROR_TYPES

    def test_backoff_constants(self):
        """Test backoff constants are sensible."""
        assert RETRY_INITIAL_DELAY_SECONDS > 0
        assert RETRY_MAX_DELAY_SECONDS > RETRY_INITIAL_DELAY_SECONDS
        assert RETRY_EXPONENTIAL_BASE > 1
        assert 0 <= RETRY_JITTER_FACTOR <= 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestErrorRecoveryIntegration:
    """Integration tests for error recovery flow."""

    def test_complete_retry_flow(self, mock_db, mock_run, mock_spec_with_retry):
        """Test complete retry flow for a retryable error."""
        # Simulate 3 retries before exhaustion
        with patch('api.error_recovery.classify_anthropic_error') as mock_classify:
            mock_classify.return_value = RateLimitRecoveryError()

            with patch('api.error_recovery.record_error_event'):
                # First attempt
                result1 = handle_api_error(
                    error=Exception("Rate limit"),
                    run=mock_run,
                    spec=mock_spec_with_retry,
                    db=mock_db,
                    event_sequence=1,
                )
                assert result1.should_retry is True
                assert mock_run.retry_count == 1

                # Second attempt
                result2 = handle_api_error(
                    error=Exception("Rate limit"),
                    run=mock_run,
                    spec=mock_spec_with_retry,
                    db=mock_db,
                    event_sequence=2,
                )
                assert result2.should_retry is True
                assert mock_run.retry_count == 2

                # Third attempt
                result3 = handle_api_error(
                    error=Exception("Rate limit"),
                    run=mock_run,
                    spec=mock_spec_with_retry,
                    db=mock_db,
                    event_sequence=3,
                )
                assert result3.should_retry is True
                assert mock_run.retry_count == 3

                # Fourth attempt - should fail (max_retries=3)
                result4 = handle_api_error(
                    error=Exception("Rate limit"),
                    run=mock_run,
                    spec=mock_spec_with_retry,
                    db=mock_db,
                    event_sequence=4,
                )
                assert result4.should_retry is False
                mock_run.fail.assert_called_once()


# =============================================================================
# Run all tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
