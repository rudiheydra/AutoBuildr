"""
Error Recovery Module
=====================

Error recovery logic for HarnessKernel with retry logic and graceful failure handling.

Feature #76: HarnessKernel Error Recovery

This module provides:
- Exception classes for different API error types
- Error classification for Anthropic SDK exceptions
- Exponential backoff calculation with jitter
- Retry policy evaluation
- Failed event recording with error details

Usage:
    from api.error_recovery import (
        classify_anthropic_error,
        calculate_backoff_delay,
        should_retry_error,
        record_error_event,
    )

    try:
        response = claude.complete(...)
    except Exception as e:
        recovery_error = classify_anthropic_error(e)
        if should_retry_error(recovery_error, retry_attempt, max_retries, retry_policy):
            delay = calculate_backoff_delay(retry_attempt, recovery_error.retry_after)
            time.sleep(delay)
            # retry...
        else:
            record_error_event(db, run_id, sequence, recovery_error)
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from api.agentspec_models import AgentEvent, AgentRun


# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Retry backoff settings
RETRY_INITIAL_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 60.0
RETRY_EXPONENTIAL_BASE = 2.0
RETRY_JITTER_FACTOR = 0.1

# Retryable error types - these errors may succeed on retry
RETRYABLE_ERROR_TYPES = frozenset({
    "rate_limit",       # 429 Too Many Requests
    "internal_server",  # 500+ Server errors
    "connection",       # Network connectivity issues
    "timeout",          # Request timeout
})

# Non-retryable errors - these errors will not be retried
NON_RETRYABLE_ERROR_TYPES = frozenset({
    "authentication",   # 401 Invalid API key
    "permission",       # 403 Permission denied
    "bad_request",      # 400 Invalid request
    "not_found",        # 404 Resource not found
    "unknown",          # Unknown/unhandled errors
})


# =============================================================================
# Import Anthropic SDK error types
# =============================================================================

try:
    import anthropic
    from anthropic import (
        APIConnectionError as AnthropicConnectionError,
        APIError as AnthropicAPIError,
        APIStatusError as AnthropicStatusError,
        APITimeoutError as AnthropicTimeoutError,
        RateLimitError as AnthropicRateLimitError,
        InternalServerError as AnthropicInternalServerError,
        AuthenticationError as AnthropicAuthError,
        BadRequestError as AnthropicBadRequestError,
    )
    ANTHROPIC_AVAILABLE = True
except ImportError:
    # Anthropic SDK not installed - create placeholder classes
    ANTHROPIC_AVAILABLE = False
    AnthropicConnectionError = type("AnthropicConnectionError", (Exception,), {})
    AnthropicAPIError = type("AnthropicAPIError", (Exception,), {})
    AnthropicStatusError = type("AnthropicStatusError", (Exception,), {})
    AnthropicTimeoutError = type("AnthropicTimeoutError", (Exception,), {})
    AnthropicRateLimitError = type("AnthropicRateLimitError", (Exception,), {})
    AnthropicInternalServerError = type("AnthropicInternalServerError", (Exception,), {})
    AnthropicAuthError = type("AnthropicAuthError", (Exception,), {})
    AnthropicBadRequestError = type("AnthropicBadRequestError", (Exception,), {})


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Error Recovery Exceptions (Feature #76)
# =============================================================================

class APIRecoveryError(Exception):
    """
    Base exception for API error recovery.

    Feature #76: HarnessKernel Error Recovery

    This exception wraps API errors with additional context for
    error recovery and retry logic.
    """

    def __init__(
        self,
        error_type: str,
        message: str,
        original_error: Exception | None = None,
        is_retryable: bool = False,
        retry_after: float | None = None,
    ):
        self.error_type = error_type
        self.original_error = original_error
        self.is_retryable = is_retryable
        self.retry_after = retry_after  # Suggested wait time before retry

        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event payload."""
        return {
            "error_type": self.error_type,
            "message": str(self),
            "is_retryable": self.is_retryable,
            "retry_after": self.retry_after,
            "original_error": str(self.original_error) if self.original_error else None,
        }


class RateLimitRecoveryError(APIRecoveryError):
    """
    Raised when Claude API rate limit is hit.

    Feature #76, Step 2: Catch RateLimitError and retry with backoff

    This error is always retryable. The retry_after field indicates
    how long to wait before retrying (if provided by the API).
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        original_error: Exception | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(
            error_type="rate_limit",
            message=message,
            original_error=original_error,
            is_retryable=True,
            retry_after=retry_after,
        )


class InternalServerRecoveryError(APIRecoveryError):
    """
    Raised when Claude API returns internal server error (5xx).

    Feature #76: Internal server errors are retryable.
    """

    def __init__(
        self,
        message: str = "Internal server error",
        original_error: Exception | None = None,
    ):
        super().__init__(
            error_type="internal_server",
            message=message,
            original_error=original_error,
            is_retryable=True,
        )


class ConnectionRecoveryError(APIRecoveryError):
    """
    Raised when connection to Claude API fails.

    Feature #76: Connection errors are retryable.
    """

    def __init__(
        self,
        message: str = "Connection failed",
        original_error: Exception | None = None,
    ):
        super().__init__(
            error_type="connection",
            message=message,
            original_error=original_error,
            is_retryable=True,
        )


class TimeoutRecoveryError(APIRecoveryError):
    """
    Raised when Claude API request times out.

    Feature #76: Timeout errors are retryable.
    """

    def __init__(
        self,
        message: str = "Request timed out",
        original_error: Exception | None = None,
    ):
        super().__init__(
            error_type="timeout",
            message=message,
            original_error=original_error,
            is_retryable=True,
        )


class AuthenticationRecoveryError(APIRecoveryError):
    """
    Raised when Claude API authentication fails.

    Feature #76: Authentication errors are NOT retryable.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        original_error: Exception | None = None,
    ):
        super().__init__(
            error_type="authentication",
            message=message,
            original_error=original_error,
            is_retryable=False,
        )


class BadRequestRecoveryError(APIRecoveryError):
    """
    Raised when Claude API rejects the request as invalid.

    Feature #76: Bad request errors are NOT retryable.
    """

    def __init__(
        self,
        message: str = "Bad request",
        original_error: Exception | None = None,
    ):
        super().__init__(
            error_type="bad_request",
            message=message,
            original_error=original_error,
            is_retryable=False,
        )


class ToolExecutionRecoveryError(APIRecoveryError):
    """
    Raised when a tool execution fails.

    Feature #76, Step 4: Catch tool execution exceptions

    Tool execution errors may or may not be retryable depending
    on the specific error.
    """

    def __init__(
        self,
        tool_name: str,
        message: str = "Tool execution failed",
        original_error: Exception | None = None,
        is_retryable: bool = False,
    ):
        self.tool_name = tool_name
        super().__init__(
            error_type="tool_execution",
            message=f"Tool '{tool_name}': {message}",
            original_error=original_error,
            is_retryable=is_retryable,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event payload."""
        d = super().to_dict()
        d["tool_name"] = self.tool_name
        return d


# =============================================================================
# Error Classification (Feature #76, Steps 1-4)
# =============================================================================

def classify_anthropic_error(error: Exception) -> APIRecoveryError:
    """
    Classify an Anthropic SDK exception into an APIRecoveryError.

    Feature #76, Steps 1-4: Wrap Claude API calls and classify errors

    Args:
        error: The exception from the Anthropic SDK

    Returns:
        An appropriate APIRecoveryError subclass
    """
    # Check for rate limit error
    if isinstance(error, AnthropicRateLimitError):
        retry_after = None
        # Try to extract retry-after header if available
        if hasattr(error, 'response') and error.response is not None:
            if hasattr(error.response, 'headers'):
                retry_after_str = error.response.headers.get('retry-after')
                if retry_after_str:
                    try:
                        retry_after = float(retry_after_str)
                    except ValueError:
                        pass
        return RateLimitRecoveryError(
            message=str(error),
            original_error=error,
            retry_after=retry_after,
        )

    # Check for internal server error
    if isinstance(error, AnthropicInternalServerError):
        return InternalServerRecoveryError(
            message=str(error),
            original_error=error,
        )

    # Check for connection error
    if isinstance(error, AnthropicConnectionError):
        return ConnectionRecoveryError(
            message=str(error),
            original_error=error,
        )

    # Check for timeout error
    if isinstance(error, AnthropicTimeoutError):
        return TimeoutRecoveryError(
            message=str(error),
            original_error=error,
        )

    # Check for authentication error
    if isinstance(error, AnthropicAuthError):
        return AuthenticationRecoveryError(
            message=str(error),
            original_error=error,
        )

    # Check for bad request error
    if isinstance(error, AnthropicBadRequestError):
        return BadRequestRecoveryError(
            message=str(error),
            original_error=error,
        )

    # Check for generic API status error
    if isinstance(error, AnthropicStatusError):
        status_code = getattr(error, 'status_code', None)
        if status_code:
            if status_code == 429:
                return RateLimitRecoveryError(
                    message=str(error),
                    original_error=error,
                )
            elif status_code >= 500:
                return InternalServerRecoveryError(
                    message=str(error),
                    original_error=error,
                )
            elif status_code == 401:
                return AuthenticationRecoveryError(
                    message=str(error),
                    original_error=error,
                )
            elif status_code == 400:
                return BadRequestRecoveryError(
                    message=str(error),
                    original_error=error,
                )

    # Check for generic API error
    if isinstance(error, AnthropicAPIError):
        return APIRecoveryError(
            error_type="api_error",
            message=str(error),
            original_error=error,
            is_retryable=False,
        )

    # Unknown error - wrap as non-retryable
    return APIRecoveryError(
        error_type="unknown",
        message=str(error),
        original_error=error,
        is_retryable=False,
    )


def classify_tool_error(
    tool_name: str,
    error: Exception,
) -> ToolExecutionRecoveryError:
    """
    Classify a tool execution exception.

    Feature #76, Step 4: Catch tool execution exceptions

    Args:
        tool_name: Name of the tool that failed
        error: The exception from tool execution

    Returns:
        A ToolExecutionRecoveryError
    """
    # Determine if the error is retryable based on type
    is_retryable = False

    # Network-related errors in tools are often retryable
    error_str = str(error).lower()
    if any(keyword in error_str for keyword in ['timeout', 'connection', 'network']):
        is_retryable = True

    return ToolExecutionRecoveryError(
        tool_name=tool_name,
        message=str(error),
        original_error=error,
        is_retryable=is_retryable,
    )


# =============================================================================
# Backoff Calculation (Feature #76, Step 2)
# =============================================================================

def calculate_backoff_delay(
    retry_attempt: int,
    initial_delay: float = RETRY_INITIAL_DELAY_SECONDS,
    max_delay: float = RETRY_MAX_DELAY_SECONDS,
    exponential_base: float = RETRY_EXPONENTIAL_BASE,
    jitter_factor: float = RETRY_JITTER_FACTOR,
    retry_after: float | None = None,
) -> float:
    """
    Calculate backoff delay for retry with exponential backoff and jitter.

    Feature #76, Step 2: Retry with backoff

    Args:
        retry_attempt: The current retry attempt (0-indexed)
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter_factor: Factor for random jitter (0-1)
        retry_after: Optional server-specified delay

    Returns:
        Delay in seconds before the next retry
    """
    # If server specified retry-after, use it
    if retry_after is not None and retry_after > 0:
        return min(retry_after, max_delay)

    # Calculate exponential backoff
    delay = initial_delay * (exponential_base ** retry_attempt)
    delay = min(delay, max_delay)

    # Add jitter to prevent thundering herd
    jitter = delay * jitter_factor * random.random()
    delay += jitter

    return delay


# =============================================================================
# Retry Policy Evaluation (Feature #76, Step 6)
# =============================================================================

def should_retry_error(
    error: APIRecoveryError,
    retry_attempt: int,
    max_retries: int,
    retry_policy: str,
) -> bool:
    """
    Determine if an error should be retried based on policy.

    Feature #76, Step 6: Check retry_policy and max_retries

    Args:
        error: The APIRecoveryError to check
        retry_attempt: Current retry attempt (0-indexed)
        max_retries: Maximum allowed retries
        retry_policy: The retry policy ("none", "fixed", "exponential")

    Returns:
        True if the error should be retried, False otherwise
    """
    # Check if retry policy allows retries
    if retry_policy == "none":
        return False

    # Check if error is retryable
    if not error.is_retryable:
        return False

    # Check if we have retries remaining
    if retry_attempt >= max_retries:
        return False

    return True


def get_retry_policy_from_spec(spec: Any) -> tuple[str, int]:
    """
    Extract retry_policy and max_retries from an AgentSpec.

    Feature #76, Step 6: Check retry_policy and max_retries

    Args:
        spec: AgentSpec with acceptance_spec containing retry config

    Returns:
        Tuple of (retry_policy, max_retries)
    """
    # Default values
    retry_policy = "none"
    max_retries = 0

    # Check if spec has acceptance_spec with retry settings
    if hasattr(spec, 'acceptance_spec') and spec.acceptance_spec is not None:
        acceptance_spec = spec.acceptance_spec
        retry_policy = getattr(acceptance_spec, 'retry_policy', 'none') or 'none'
        max_retries = getattr(acceptance_spec, 'max_retries', 0) or 0

    return retry_policy, max_retries


# =============================================================================
# Event Recording (Feature #76, Step 5)
# =============================================================================

def create_error_event_payload(
    error: APIRecoveryError,
    retry_attempt: int = 0,
    max_retries: int = 0,
    will_retry: bool = False,
) -> dict[str, Any]:
    """
    Create an event payload for error recording.

    Feature #76, Step 5: Record failed event with error details

    Args:
        error: The APIRecoveryError to record
        retry_attempt: Current retry attempt
        max_retries: Maximum retries allowed
        will_retry: Whether the operation will be retried

    Returns:
        Dict suitable for AgentEvent payload
    """
    return {
        "error": error.to_dict(),
        "retry_attempt": retry_attempt,
        "max_retries": max_retries,
        "will_retry": will_retry,
        "timestamp": _utc_now().isoformat(),
    }


def record_error_event(
    db: "Session",
    run_id: str,
    sequence: int,
    error: APIRecoveryError,
    retry_attempt: int = 0,
    max_retries: int = 0,
    will_retry: bool = False,
) -> "AgentEvent":
    """
    Record a failed event with error details.

    Feature #76, Step 5: Record failed event with error details

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        error: The APIRecoveryError to record
        retry_attempt: Current retry attempt
        max_retries: Maximum retries allowed
        will_retry: Whether the operation will be retried

    Returns:
        The created AgentEvent
    """
    from api.agentspec_models import AgentEvent

    payload = create_error_event_payload(
        error=error,
        retry_attempt=retry_attempt,
        max_retries=max_retries,
        will_retry=will_retry,
    )

    event = AgentEvent(
        run_id=run_id,
        sequence=sequence,
        event_type="failed",
        timestamp=_utc_now(),
        payload=payload,
    )

    db.add(event)
    _logger.error(
        "Recorded error event for run %s: type=%s, retryable=%s, will_retry=%s",
        run_id, error.error_type, error.is_retryable, will_retry
    )
    return event


def record_retry_event(
    db: "Session",
    run_id: str,
    sequence: int,
    error: APIRecoveryError,
    retry_attempt: int,
    delay_seconds: float,
) -> "AgentEvent":
    """
    Record a retry event when retrying after an error.

    Feature #76, Step 7: If retries available, increment retry_count and retry

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        error: The APIRecoveryError that triggered the retry
        retry_attempt: The retry attempt number (1-indexed after increment)
        delay_seconds: How long the delay was before retry

    Returns:
        The created AgentEvent
    """
    from api.agentspec_models import AgentEvent

    payload = {
        "error": error.to_dict(),
        "retry_attempt": retry_attempt,
        "delay_seconds": delay_seconds,
        "timestamp": _utc_now().isoformat(),
    }

    # Use a custom event type for retries
    # Note: This could be added to EVENT_TYPES in agentspec_models.py
    event = AgentEvent(
        run_id=run_id,
        sequence=sequence,
        event_type="failed",  # Use failed type with retry info in payload
        timestamp=_utc_now(),
        payload=payload,
    )

    db.add(event)
    _logger.info(
        "Recorded retry event for run %s: attempt=%d, delay=%.2fs, error_type=%s",
        run_id, retry_attempt, delay_seconds, error.error_type
    )
    return event


# =============================================================================
# Run Update Helpers (Feature #76, Steps 7-8)
# =============================================================================

def increment_retry_count(
    run: "AgentRun",
) -> int:
    """
    Increment the retry_count on an AgentRun.

    Feature #76, Step 7: If retries available, increment retry_count and retry

    Args:
        run: The AgentRun to update

    Returns:
        The new retry_count value
    """
    run.retry_count = (run.retry_count or 0) + 1
    _logger.info("Incremented retry_count for run %s to %d", run.id, run.retry_count)
    return run.retry_count


def finalize_run_on_error(
    run: "AgentRun",
    error: APIRecoveryError,
) -> None:
    """
    Finalize an AgentRun with failed status after all retries exhausted.

    Feature #76, Step 8: If no retries, set status to failed and finalize

    Args:
        run: The AgentRun to finalize
        error: The final error that caused failure
    """
    error_message = f"{error.error_type}: {str(error)}"
    run.fail(error_message=error_message)
    _logger.error(
        "Finalized run %s as failed: %s (after %d retries)",
        run.id, error.error_type, run.retry_count
    )


# =============================================================================
# High-Level Error Recovery (Feature #76)
# =============================================================================

@dataclass
class ErrorRecoveryResult:
    """
    Result of error recovery attempt.

    Contains information about whether to retry and what happened.
    """
    should_retry: bool
    delay_seconds: float = 0.0
    error: APIRecoveryError | None = None
    retry_attempt: int = 0
    final_error_message: str | None = None


def handle_api_error(
    error: Exception,
    run: "AgentRun",
    spec: Any,
    db: "Session",
    event_sequence: int,
) -> ErrorRecoveryResult:
    """
    Handle an API error with full recovery logic.

    Feature #76: Complete error recovery flow

    This function:
    1. Wraps the error in try/except (Step 1)
    2. Classifies the error (Steps 2-4)
    3. Records a failed event (Step 5)
    4. Checks retry policy (Step 6)
    5. If retries available, returns retry info (Step 7)
    6. If no retries, finalizes the run (Step 8)

    Args:
        error: The exception that occurred
        run: The AgentRun being executed
        spec: The AgentSpec with retry configuration
        db: Database session
        event_sequence: Current event sequence number

    Returns:
        ErrorRecoveryResult indicating whether to retry
    """
    # Step 1: Classify the error
    recovery_error = classify_anthropic_error(error)

    # Get retry policy from spec
    retry_policy, max_retries = get_retry_policy_from_spec(spec)

    # Current retry attempt (0-indexed)
    current_attempt = run.retry_count or 0

    # Step 6: Check if we should retry
    should_retry = should_retry_error(
        error=recovery_error,
        retry_attempt=current_attempt,
        max_retries=max_retries,
        retry_policy=retry_policy,
    )

    # Step 5: Record error event
    record_error_event(
        db=db,
        run_id=run.id,
        sequence=event_sequence,
        error=recovery_error,
        retry_attempt=current_attempt,
        max_retries=max_retries,
        will_retry=should_retry,
    )

    if should_retry:
        # Step 7: Calculate delay and prepare for retry
        delay = calculate_backoff_delay(
            retry_attempt=current_attempt,
            retry_after=recovery_error.retry_after,
        )

        # Increment retry count
        increment_retry_count(run)
        db.commit()

        _logger.info(
            "Will retry run %s: attempt=%d/%d, delay=%.2fs, error_type=%s",
            run.id, current_attempt + 1, max_retries, delay, recovery_error.error_type
        )

        return ErrorRecoveryResult(
            should_retry=True,
            delay_seconds=delay,
            error=recovery_error,
            retry_attempt=current_attempt + 1,
        )
    else:
        # Step 8: Finalize run as failed
        finalize_run_on_error(run, recovery_error)
        db.commit()

        return ErrorRecoveryResult(
            should_retry=False,
            error=recovery_error,
            retry_attempt=current_attempt,
            final_error_message=f"{recovery_error.error_type}: {str(recovery_error)}",
        )


def handle_tool_error(
    tool_name: str,
    error: Exception,
    run: "AgentRun",
    spec: Any,
    db: "Session",
    event_sequence: int,
) -> ErrorRecoveryResult:
    """
    Handle a tool execution error with recovery logic.

    Feature #76, Step 4: Catch tool execution exceptions

    Args:
        tool_name: Name of the tool that failed
        error: The exception that occurred
        run: The AgentRun being executed
        spec: The AgentSpec with retry configuration
        db: Database session
        event_sequence: Current event sequence number

    Returns:
        ErrorRecoveryResult indicating whether to retry
    """
    # Classify the tool error
    recovery_error = classify_tool_error(tool_name, error)

    # Get retry policy from spec
    retry_policy, max_retries = get_retry_policy_from_spec(spec)

    # Current retry attempt
    current_attempt = run.retry_count or 0

    # Check if we should retry
    should_retry = should_retry_error(
        error=recovery_error,
        retry_attempt=current_attempt,
        max_retries=max_retries,
        retry_policy=retry_policy,
    )

    # Record error event
    record_error_event(
        db=db,
        run_id=run.id,
        sequence=event_sequence,
        error=recovery_error,
        retry_attempt=current_attempt,
        max_retries=max_retries,
        will_retry=should_retry,
    )

    if should_retry:
        delay = calculate_backoff_delay(retry_attempt=current_attempt)
        increment_retry_count(run)
        db.commit()

        return ErrorRecoveryResult(
            should_retry=True,
            delay_seconds=delay,
            error=recovery_error,
            retry_attempt=current_attempt + 1,
        )
    else:
        finalize_run_on_error(run, recovery_error)
        db.commit()

        return ErrorRecoveryResult(
            should_retry=False,
            error=recovery_error,
            retry_attempt=current_attempt,
            final_error_message=f"{recovery_error.error_type}: {str(recovery_error)}",
        )
