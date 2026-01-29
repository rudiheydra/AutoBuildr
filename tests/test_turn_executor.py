"""
Turn Executor Bridge Tests
===========================

Tests for Feature #126: Turn executor bridge connects HarnessKernel to Claude SDK

Verification Steps:
1. Locate the turn executor implementation (api/turn_executor.py)
2. Verify it accepts the correct signature expected by HarnessKernel.execute(turn_executor=...)
3. Verify it creates or reuses a Claude SDK client to send prompts
4. Verify it returns (completed, turn_data, tool_events, tokens_in, tokens_out) tuple
5. Verify it handles Claude SDK errors (network, rate limit, invalid response) without raising
6. Verify tool_events contain tool_name, arguments, and result for each tool call
"""

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.agentspec_models import (
    AcceptanceSpec,
    AgentEvent,
    AgentRun,
    AgentSpec,
    generate_uuid,
)
from api.database import Base, Feature
from api.harness_kernel import HarnessKernel
from api.turn_executor import (
    ClaudeSDKTurnExecutor,
    TurnResult,
    ToolEvent,
    create_turn_executor,
    DEFAULT_MODEL,
    MAX_ERROR_RETRIES,
    _is_rate_limit_error,
    _is_retryable_error,
    _get_retry_after,
    _calculate_backoff,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLAlchemy session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_spec(db_session):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec-turn-executor",
        display_name="Test Turn Executor",
        spec_version="v1",
        objective="Implement a hello world function in Python",
        task_type="coding",
        context={"project_dir": "/tmp/test", "language": "python"},
        tool_policy={"allowed_tools": ["Read", "Write", "Bash"]},
        max_turns=10,
        timeout_seconds=300,
        source_feature_id=1,
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_spec.id,
        status="running",
        turns_used=0,
        tokens_in=0,
        tokens_out=0,
        retry_count=0,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    return run


def _make_mock_response(
    text: str = "Hello! Here's the implementation.",
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 50,
    tool_use_blocks: list[dict] | None = None,
):
    """Create a mock Claude API response."""
    response = MagicMock()
    response.stop_reason = stop_reason
    response.model = "claude-sonnet-4-20250514"

    # Build content blocks
    content_blocks = []

    # Text block
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    content_blocks.append(text_block)

    # Tool use blocks
    if tool_use_blocks:
        for tool in tool_use_blocks:
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.name = tool.get("name", "Read")
            tool_block.input = tool.get("input", {})
            tool_block.id = tool.get("id", f"tool_{generate_uuid()[:8]}")
            content_blocks.append(tool_block)

    response.content = content_blocks

    # Usage
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    response.usage = usage

    return response


def _make_executor_with_mock_client(
    mock_response=None,
    side_effect=None,
    **executor_kwargs,
):
    """
    Create a ClaudeSDKTurnExecutor with a mocked Anthropic client.

    Bypasses the real `_get_or_create_client` by injecting a mock client directly.
    """
    executor = ClaudeSDKTurnExecutor(api_key="test-key", **executor_kwargs)

    mock_client = MagicMock()
    if side_effect is not None:
        mock_client.messages.create.side_effect = side_effect
    elif mock_response is not None:
        mock_client.messages.create.return_value = mock_response
    else:
        mock_client.messages.create.return_value = _make_mock_response()

    # Inject mock client directly
    executor._client = mock_client

    return executor, mock_client


# =============================================================================
# Step 1: Locate the turn executor implementation
# =============================================================================

class TestTurnExecutorExists:
    """Verify the turn executor module exists and is importable."""

    def test_module_importable(self):
        """Turn executor module can be imported."""
        from api import turn_executor
        assert turn_executor is not None

    def test_class_exists(self):
        """ClaudeSDKTurnExecutor class exists."""
        assert ClaudeSDKTurnExecutor is not None

    def test_factory_function_exists(self):
        """create_turn_executor factory function exists."""
        assert callable(create_turn_executor)

    def test_tool_event_class_exists(self):
        """ToolEvent data class exists."""
        assert ToolEvent is not None

    def test_turn_result_class_exists(self):
        """TurnResult data class exists."""
        assert TurnResult is not None


# =============================================================================
# Step 2: Verify correct signature for HarnessKernel.execute(turn_executor=...)
# =============================================================================

class TestTurnExecutorSignature:
    """Verify the turn executor accepts the correct signature."""

    def test_is_callable(self):
        """ClaudeSDKTurnExecutor instances are callable."""
        executor = ClaudeSDKTurnExecutor(api_key="test-key")
        assert callable(executor)

    def test_call_signature_accepts_run_and_spec(self, sample_run, sample_spec):
        """Executor __call__ accepts (run: AgentRun, spec: AgentSpec) args."""
        executor, _ = _make_executor_with_mock_client()
        # Should not raise TypeError
        result = executor(sample_run, sample_spec)
        assert result is not None

    def test_return_type_is_5_tuple(self, sample_run, sample_spec):
        """Executor returns a 5-element tuple."""
        executor, _ = _make_executor_with_mock_client()
        result = executor(sample_run, sample_spec)

        assert isinstance(result, tuple)
        assert len(result) == 5

    def test_return_tuple_types(self, sample_run, sample_spec):
        """Return tuple has correct types: (bool, dict, list, int, int)."""
        executor, _ = _make_executor_with_mock_client()
        completed, turn_data, tool_events, tokens_in, tokens_out = executor(sample_run, sample_spec)

        assert isinstance(completed, bool)
        assert isinstance(turn_data, dict)
        assert isinstance(tool_events, list)
        assert isinstance(tokens_in, int)
        assert isinstance(tokens_out, int)

    def test_compatible_with_harness_kernel_execute(self, db_session, sample_spec):
        """Executor can be passed to HarnessKernel.execute(turn_executor=...)."""
        # Simulate a single-turn completion
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                text="Done!",
                stop_reason="end_turn",
                input_tokens=50,
                output_tokens=30,
            ),
        )

        kernel = HarnessKernel(db_session)

        # This should work without errors
        run = kernel.execute(sample_spec, turn_executor=executor)

        assert run is not None
        assert run.status in ("completed", "failed", "timeout")
        assert run.turns_used >= 1

    def test_factory_creates_correct_type(self):
        """create_turn_executor returns a ClaudeSDKTurnExecutor."""
        executor = create_turn_executor(api_key="test-key")
        assert isinstance(executor, ClaudeSDKTurnExecutor)
        assert callable(executor)


# =============================================================================
# Step 3: Verify it creates or reuses a Claude SDK client
# =============================================================================

class TestClaudeSDKClientManagement:
    """Verify the executor creates or reuses the Claude SDK client."""

    def test_client_lazily_created(self):
        """Client is NOT created until first call."""
        executor = ClaudeSDKTurnExecutor(api_key="test-key")
        # Client should not be created yet
        assert executor._client is None

    def test_client_created_on_first_call(self, sample_run, sample_spec):
        """Client is created on first execution (via _get_or_create_client)."""
        executor, mock_client = _make_executor_with_mock_client()
        # Client was injected, so it should be set
        assert executor._client is not None

        # Execute to verify it uses the client
        executor(sample_run, sample_spec)
        mock_client.messages.create.assert_called_once()

    def test_client_reused_on_subsequent_calls(self, sample_run, sample_spec):
        """Client is reused across multiple calls."""
        executor, mock_client = _make_executor_with_mock_client()

        # Two calls
        executor(sample_run, sample_spec)
        executor.reset()  # Reset conversation but keep client
        executor(sample_run, sample_spec)

        # Client should still be the same object (reused)
        assert executor._client is mock_client
        # Should have been called twice (once per turn)
        assert mock_client.messages.create.call_count == 2

    def test_api_key_from_env(self):
        """Client uses ANTHROPIC_API_KEY from environment."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-test-key-xyz"}):
            executor = ClaudeSDKTurnExecutor()
            assert executor.api_key == "env-test-key-xyz"

    def test_api_key_from_constructor(self):
        """Explicit api_key overrides environment variable."""
        executor = ClaudeSDKTurnExecutor(api_key="my-custom-key")
        assert executor.api_key == "my-custom-key"

    def test_client_reused_after_reset(self, sample_run, sample_spec):
        """reset() clears messages but keeps the client."""
        executor, mock_client = _make_executor_with_mock_client()

        executor(sample_run, sample_spec)
        client_before = executor._client

        executor.reset()
        assert executor._messages == []
        assert executor._client is client_before  # Client NOT cleared


# =============================================================================
# Step 4: Verify return tuple structure
# =============================================================================

class TestReturnTuple:
    """Verify the return tuple (completed, turn_data, tool_events, tokens_in, tokens_out)."""

    def test_completed_true_on_end_turn(self, sample_run, sample_spec):
        """completed=True when stop_reason is 'end_turn'."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(stop_reason="end_turn"),
        )
        completed, _, _, _, _ = executor(sample_run, sample_spec)
        assert completed is True

    def test_completed_false_on_tool_use(self, sample_run, sample_spec):
        """completed=False when stop_reason is 'tool_use'."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                stop_reason="tool_use",
                tool_use_blocks=[{"name": "Read", "input": {"path": "/test.py"}}],
            ),
        )
        completed, _, _, _, _ = executor(sample_run, sample_spec)
        assert completed is False

    def test_turn_data_contains_response_text(self, sample_run, sample_spec):
        """turn_data dict contains response_text key."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(text="Here is the code"),
        )
        _, turn_data, _, _, _ = executor(sample_run, sample_spec)

        assert "response_text" in turn_data
        assert "Here is the code" in turn_data["response_text"]

    def test_turn_data_contains_stop_reason(self, sample_run, sample_spec):
        """turn_data dict contains stop_reason."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(stop_reason="end_turn"),
        )
        _, turn_data, _, _, _ = executor(sample_run, sample_spec)
        assert turn_data["stop_reason"] == "end_turn"

    def test_tokens_in_from_usage(self, sample_run, sample_spec):
        """tokens_in reflects the input token count from the API response."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(input_tokens=250, output_tokens=75),
        )
        _, _, _, tokens_in, tokens_out = executor(sample_run, sample_spec)
        assert tokens_in == 250
        assert tokens_out == 75

    def test_tokens_default_to_zero_on_missing_usage(self, sample_run, sample_spec):
        """tokens_in and tokens_out default to 0 if usage is None."""
        response = _make_mock_response()
        response.usage = None  # No usage info
        executor, _ = _make_executor_with_mock_client(mock_response=response)
        _, _, _, tokens_in, tokens_out = executor(sample_run, sample_spec)
        assert tokens_in == 0
        assert tokens_out == 0

    def test_turn_result_as_tuple(self):
        """TurnResult.as_tuple() returns correct tuple format."""
        result = TurnResult(
            completed=True,
            turn_data={"key": "value"},
            tool_events=[{"tool_name": "Read"}],
            tokens_in=100,
            tokens_out=50,
        )

        t = result.as_tuple()
        assert t == (True, {"key": "value"}, [{"tool_name": "Read"}], 100, 50)
        assert len(t) == 5

    def test_turn_data_contains_tool_count(self, sample_run, sample_spec):
        """turn_data dict contains tool_count."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                stop_reason="tool_use",
                tool_use_blocks=[
                    {"name": "Read", "input": {"path": "/a.py"}},
                    {"name": "Write", "input": {"path": "/b.py", "content": "x"}},
                ],
            ),
        )
        _, turn_data, _, _, _ = executor(sample_run, sample_spec)
        assert "tool_count" in turn_data
        assert turn_data["tool_count"] == 2


# =============================================================================
# Step 5: Verify error handling
# =============================================================================

class TestErrorHandling:
    """Verify Claude SDK errors are handled gracefully."""

    def test_rate_limit_error_no_crash(self, sample_run, sample_spec):
        """Rate limit error is caught and returned as error turn data."""
        rate_error = type("RateLimitError", (Exception,), {"status_code": 429})()
        executor, _ = _make_executor_with_mock_client(
            side_effect=rate_error,
            max_error_retries=0,
        )
        # Should NOT raise - returns error data instead
        completed, turn_data, tool_events, tokens_in, tokens_out = executor(sample_run, sample_spec)

        assert completed is True  # Error signals completion
        assert turn_data.get("error") is True
        assert "error_type" in turn_data
        assert tokens_in == 0
        assert tokens_out == 0

    def test_network_error_no_crash(self, sample_run, sample_spec):
        """Network/connection error is caught gracefully."""
        executor, _ = _make_executor_with_mock_client(
            side_effect=ConnectionError("Network unreachable"),
            max_error_retries=0,
        )
        completed, turn_data, tool_events, tokens_in, tokens_out = executor(sample_run, sample_spec)

        assert completed is True
        assert turn_data.get("error") is True
        assert "ConnectionError" in turn_data["error_type"]

    def test_invalid_response_error_no_crash(self, sample_run, sample_spec):
        """Invalid response (None content) is handled gracefully."""
        bad_response = MagicMock()
        bad_response.content = None
        bad_response.stop_reason = "end_turn"
        bad_response.usage = None
        bad_response.model = "test"
        executor, _ = _make_executor_with_mock_client(mock_response=bad_response)

        # Should not crash
        completed, turn_data, tool_events, tokens_in, tokens_out = executor(sample_run, sample_spec)
        assert isinstance(completed, bool)
        assert isinstance(turn_data, dict)

    def test_authentication_error_no_crash(self, sample_run, sample_spec):
        """Authentication error is caught and does not crash kernel loop."""
        auth_error = type("AuthenticationError", (Exception,), {"status_code": 401})()
        executor, _ = _make_executor_with_mock_client(
            side_effect=auth_error,
            max_error_retries=0,
        )
        completed, turn_data, tool_events, tokens_in, tokens_out = executor(sample_run, sample_spec)

        assert completed is True
        assert turn_data.get("error") is True

    def test_missing_api_key_no_crash(self, sample_run, sample_spec):
        """Missing API key is caught and returned as error."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove all env vars that might have the key
            for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"]:
                os.environ.pop(key, None)

            executor = ClaudeSDKTurnExecutor(api_key=None)
            completed, turn_data, tool_events, tokens_in, tokens_out = executor(sample_run, sample_spec)

            assert completed is True
            assert turn_data.get("error") is True

    def test_retry_on_rate_limit(self, sample_run, sample_spec):
        """Rate limit errors trigger retries before succeeding."""
        rate_error = type("RateLimitError", (Exception,), {"status_code": 429})()
        # First call fails, second succeeds
        executor, mock_client = _make_executor_with_mock_client(
            side_effect=[rate_error, _make_mock_response(text="Success after retry")],
            max_error_retries=2,
        )

        completed, turn_data, _, _, _ = executor(sample_run, sample_spec)

        # Should succeed after retry
        assert "error" not in turn_data or turn_data.get("error") is not True
        assert mock_client.messages.create.call_count == 2

    def test_error_data_contains_error_message(self, sample_run, sample_spec):
        """Error turn data includes error_message field."""
        executor, _ = _make_executor_with_mock_client(
            side_effect=ValueError("Test error message"),
            max_error_retries=0,
        )
        completed, turn_data, _, _, _ = executor(sample_run, sample_spec)

        assert "error_message" in turn_data
        assert "Test error message" in turn_data["error_message"]

    def test_kernel_handles_executor_error_gracefully(self, db_session, sample_spec):
        """HarnessKernel handles executor errors without crashing."""
        executor, _ = _make_executor_with_mock_client(
            side_effect=RuntimeError("Catastrophic failure"),
            max_error_retries=0,
        )
        kernel = HarnessKernel(db_session)

        # Should complete without raising
        run = kernel.execute(sample_spec, turn_executor=executor)
        assert run is not None
        assert run.status in ("completed", "failed", "timeout")

    def test_timeout_error_no_crash(self, sample_run, sample_spec):
        """Timeout error is caught and returned as error turn data."""
        timeout_error = type("TimeoutError", (Exception,), {})()
        executor, _ = _make_executor_with_mock_client(
            side_effect=timeout_error,
            max_error_retries=0,
        )
        completed, turn_data, _, _, _ = executor(sample_run, sample_spec)

        assert completed is True
        assert turn_data.get("error") is True

    def test_all_retries_exhausted_returns_error(self, sample_run, sample_spec):
        """When all retries are exhausted, returns error data."""
        rate_error = type("RateLimitError", (Exception,), {"status_code": 429})()
        # All calls fail
        executor, mock_client = _make_executor_with_mock_client(
            side_effect=rate_error,
            max_error_retries=2,
        )
        completed, turn_data, _, _, _ = executor(sample_run, sample_spec)

        assert completed is True
        assert turn_data.get("error") is True
        # Should have retried max_error_retries + 1 times
        assert mock_client.messages.create.call_count == 3  # 0, 1, 2 = 3 attempts


# =============================================================================
# Step 6: Verify tool_events structure
# =============================================================================

class TestToolEvents:
    """Verify tool_events contain tool_name, arguments, and result."""

    def test_tool_events_from_tool_use_response(self, sample_run, sample_spec):
        """Tool use blocks in response produce tool_events."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                stop_reason="tool_use",
                tool_use_blocks=[
                    {"name": "Read", "input": {"file_path": "/test.py"}, "id": "tool_123"},
                ],
            ),
        )
        _, _, tool_events, _, _ = executor(sample_run, sample_spec)

        assert len(tool_events) == 1
        event = tool_events[0]
        assert "tool_name" in event
        assert event["tool_name"] == "Read"
        assert "arguments" in event
        assert event["arguments"]["file_path"] == "/test.py"
        assert "result" in event

    def test_multiple_tool_events(self, sample_run, sample_spec):
        """Multiple tool use blocks produce multiple tool events."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                stop_reason="tool_use",
                tool_use_blocks=[
                    {"name": "Read", "input": {"file_path": "/a.py"}, "id": "t1"},
                    {"name": "Write", "input": {"file_path": "/b.py", "content": "x"}, "id": "t2"},
                    {"name": "Bash", "input": {"command": "ls"}, "id": "t3"},
                ],
            ),
        )
        _, _, tool_events, _, _ = executor(sample_run, sample_spec)

        assert len(tool_events) == 3
        assert tool_events[0]["tool_name"] == "Read"
        assert tool_events[1]["tool_name"] == "Write"
        assert tool_events[2]["tool_name"] == "Bash"

    def test_tool_event_has_required_keys(self, sample_run, sample_spec):
        """Each tool event has tool_name, arguments, and result keys."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                stop_reason="tool_use",
                tool_use_blocks=[
                    {"name": "Grep", "input": {"pattern": "TODO"}, "id": "t_grep"},
                ],
            ),
        )
        _, _, tool_events, _, _ = executor(sample_run, sample_spec)

        event = tool_events[0]
        assert "tool_name" in event, "Missing tool_name key"
        assert "arguments" in event, "Missing arguments key"
        assert "result" in event, "Missing result key"

    def test_empty_tool_events_on_text_only_response(self, sample_run, sample_spec):
        """Text-only response produces empty tool_events list."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                text="Just text, no tools",
                stop_reason="end_turn",
            ),
        )
        _, _, tool_events, _, _ = executor(sample_run, sample_spec)

        assert tool_events == []

    def test_tool_event_to_dict(self):
        """ToolEvent.to_dict() produces correct dict."""
        event = ToolEvent(
            tool_name="Read",
            arguments={"file_path": "/test.py"},
            result="file contents",
            is_error=False,
        )

        d = event.to_dict()
        assert d["tool_name"] == "Read"
        assert d["arguments"]["file_path"] == "/test.py"
        assert d["result"] == "file contents"
        assert d["is_error"] is False

    def test_tool_event_empty_arguments(self, sample_run, sample_spec):
        """Tool events handle empty/None arguments gracefully."""
        # Create a tool block with None input
        response = _make_mock_response(
            stop_reason="tool_use",
            tool_use_blocks=[{"name": "custom_tool", "input": None, "id": "t_custom"}],
        )
        # Override the input to None on the tool block
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                block.input = None

        executor, _ = _make_executor_with_mock_client(mock_response=response)
        _, _, tool_events, _, _ = executor(sample_run, sample_spec)

        assert len(tool_events) == 1
        assert tool_events[0]["arguments"] == {}  # Should default to empty dict


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Test helper functions for error classification."""

    def test_is_rate_limit_error_by_name(self):
        """Detect rate limit error by class name."""
        error = type("RateLimitError", (Exception,), {})()
        assert _is_rate_limit_error(error) is True

    def test_is_rate_limit_error_by_status(self):
        """Detect rate limit error by status code 429."""
        error = type("SomeError", (Exception,), {"status_code": 429})()
        assert _is_rate_limit_error(error) is True

    def test_is_not_rate_limit_error(self):
        """Regular errors are not rate limit errors."""
        error = ValueError("test")
        assert _is_rate_limit_error(error) is False

    def test_is_retryable_error_rate_limit(self):
        """Rate limit errors are retryable."""
        error = type("RateLimitError", (Exception,), {"status_code": 429})()
        assert _is_retryable_error(error) is True

    def test_is_retryable_error_server_error(self):
        """Server errors (5xx) are retryable."""
        error = type("ServerError", (Exception,), {"status_code": 500})()
        assert _is_retryable_error(error) is True

    def test_is_retryable_error_timeout(self):
        """Timeout errors are retryable."""
        error = type("TimeoutError", (Exception,), {})()
        assert _is_retryable_error(error) is True

    def test_is_retryable_error_connection(self):
        """Connection errors are retryable."""
        error = type("ConnectionError", (Exception,), {})()
        assert _is_retryable_error(error) is True

    def test_is_not_retryable_error(self):
        """Value errors are not retryable."""
        error = ValueError("bad value")
        assert _is_retryable_error(error) is False

    def test_calculate_backoff_exponential(self):
        """Backoff delay increases exponentially."""
        d0 = _calculate_backoff(0)
        d1 = _calculate_backoff(1)
        d2 = _calculate_backoff(2)
        # Allow for jitter
        assert d1 > d0 * 0.8
        assert d2 > d1 * 0.8

    def test_calculate_backoff_respects_retry_after(self):
        """Backoff uses retry-after when provided."""
        delay = _calculate_backoff(0, retry_after=5.0)
        assert delay == 5.0

    def test_calculate_backoff_max_limit(self):
        """Backoff does not exceed MAX_RETRY_DELAY."""
        delay = _calculate_backoff(100)  # Very high attempt number
        assert delay <= 30.0 * 1.15  # Allow 15% jitter above max

    def test_get_retry_after_from_response(self):
        """Extract retry-after from response headers."""
        error = MagicMock()
        error.response.headers = {"retry-after": "2.5"}
        assert _get_retry_after(error) == 2.5

    def test_get_retry_after_none_when_missing(self):
        """Return None when retry-after header is missing."""
        error = MagicMock()
        error.response = None
        assert _get_retry_after(error) is None


# =============================================================================
# Conversation State Management
# =============================================================================

class TestConversationState:
    """Test conversation state management across turns."""

    def test_reset_clears_messages(self):
        """reset() clears conversation messages."""
        executor = ClaudeSDKTurnExecutor(api_key="test-key")
        executor._messages.append({"role": "user", "content": "test"})
        executor._system_prompt = "test prompt"

        executor.reset()

        assert executor._messages == []
        assert executor._system_prompt is None

    def test_system_prompt_built_from_spec(self, sample_run, sample_spec):
        """System prompt is built from spec objective and context."""
        executor, _ = _make_executor_with_mock_client()
        executor(sample_run, sample_spec)

        assert executor._system_prompt is not None
        assert "hello world" in executor._system_prompt.lower() or "Implement" in executor._system_prompt

    def test_messages_accumulated_across_turns(self, sample_run, sample_spec):
        """Messages accumulate across multiple turn calls."""
        # First turn: tool use (not completed), Second: end
        executor, _ = _make_executor_with_mock_client(
            side_effect=[
                _make_mock_response(
                    stop_reason="tool_use",
                    tool_use_blocks=[{"name": "Read", "input": {"path": "/a.py"}, "id": "t1"}],
                ),
                _make_mock_response(
                    stop_reason="end_turn",
                    text="Done!",
                ),
            ],
        )

        # First turn
        executor(sample_run, sample_spec)
        msgs_after_first = len(executor._messages)
        assert msgs_after_first > 0

        # Second turn
        executor(sample_run, sample_spec)
        msgs_after_second = len(executor._messages)
        assert msgs_after_second > msgs_after_first


# =============================================================================
# Integration: End-to-end with HarnessKernel
# =============================================================================

class TestKernelIntegration:
    """Test turn executor integration with HarnessKernel."""

    def test_single_turn_execution(self, db_session, sample_spec):
        """Single-turn execution through kernel completes successfully."""
        executor, _ = _make_executor_with_mock_client(
            mock_response=_make_mock_response(
                text="Task complete!",
                stop_reason="end_turn",
                input_tokens=100,
                output_tokens=50,
            ),
        )

        kernel = HarnessKernel(db_session)
        run = kernel.execute(sample_spec, turn_executor=executor)

        assert run.status == "completed"
        assert run.turns_used == 1
        assert run.tokens_in >= 100
        assert run.tokens_out >= 50

    def test_multi_turn_execution(self, db_session):
        """Multi-turn execution (tool use followed by completion)."""
        # Create spec with enough budget
        spec = AgentSpec(
            id=generate_uuid(),
            name="test-multi-turn",
            display_name="Multi Turn Test",
            spec_version="v1",
            objective="Read a file and summarize it",
            task_type="coding",
            tool_policy={"allowed_tools": ["Read", "Write", "Bash"]},
            max_turns=5,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        # Turn 1: Tool use (Read file)
        # Turn 2: Complete with summary
        executor, _ = _make_executor_with_mock_client(
            side_effect=[
                _make_mock_response(
                    stop_reason="tool_use",
                    text="Let me read the file.",
                    tool_use_blocks=[{"name": "Read", "input": {"file_path": "/test.py"}, "id": "t1"}],
                    input_tokens=80,
                    output_tokens=40,
                ),
                _make_mock_response(
                    stop_reason="end_turn",
                    text="The file contains a hello world function.",
                    input_tokens=120,
                    output_tokens=60,
                ),
            ],
        )

        kernel = HarnessKernel(db_session)
        run = kernel.execute(spec, turn_executor=executor)

        assert run.status == "completed"
        assert run.turns_used == 2
        assert run.tokens_in >= 200  # 80 + 120
        assert run.tokens_out >= 100  # 40 + 60

    def test_error_during_execution_fails_gracefully(self, db_session, sample_spec):
        """Errors during execution result in a completed run with error data."""
        executor, _ = _make_executor_with_mock_client(
            side_effect=RuntimeError("API is down"),
            max_error_retries=0,
        )

        kernel = HarnessKernel(db_session)
        run = kernel.execute(sample_spec, turn_executor=executor)

        # Run should complete (executor returns completed=True on error)
        assert run is not None
        assert run.status in ("completed", "failed", "timeout")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
