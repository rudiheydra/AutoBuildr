"""
Turn Executor Bridge
====================

Bridges HarnessKernel to the Claude SDK by implementing a turn_executor
callable that can be passed to HarnessKernel.execute().

Feature #126: Turn executor bridge connects HarnessKernel to Claude SDK

The turn executor:
- Receives the spec's objective and context from HarnessKernel
- Creates a ClaudeSDKClient (or reuses one) to send prompts
- Processes the Claude response (text, tool_use blocks)
- Returns (completed, turn_data, tool_events, tokens_in, tokens_out)
- Handles Claude SDK errors gracefully without crashing the kernel loop

Usage:
    from api.turn_executor import ClaudeSDKTurnExecutor, create_turn_executor

    # Create an executor
    executor = ClaudeSDKTurnExecutor(
        model="claude-sonnet-4-20250514",
        project_dir=Path("/my/project"),
    )

    # Use with HarnessKernel
    kernel = HarnessKernel(db_session)
    run = kernel.execute(spec, turn_executor=executor)

    # Or use the factory function for convenience
    turn_executor = create_turn_executor(model="claude-sonnet-4-20250514")
    run = kernel.execute(spec, turn_executor=turn_executor)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from api.agentspec_models import AgentRun, AgentSpec

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default model to use for Claude SDK
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Maximum number of retries for transient errors
MAX_ERROR_RETRIES = 3

# Initial retry delay (seconds) for exponential backoff
INITIAL_RETRY_DELAY = 1.0

# Maximum retry delay (seconds)
MAX_RETRY_DELAY = 30.0


# =============================================================================
# Error Classification Helpers
# =============================================================================

def _is_rate_limit_error(error: Exception) -> bool:
    """Check if an error is a rate limit error (429)."""
    error_str = str(type(error).__name__).lower()
    if "ratelimit" in error_str:
        return True
    # Check for status code attribute
    status = getattr(error, "status_code", None)
    if status == 429:
        return True
    return False


def _is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable (transient network/server issues)."""
    error_type = type(error).__name__.lower()
    retryable_patterns = [
        "ratelimit", "timeout", "connection",
        "internalserver", "overloaded",
    ]
    if any(p in error_type for p in retryable_patterns):
        return True
    # Check for status codes 429, 500+, 503, 529
    status = getattr(error, "status_code", None)
    if status is not None and (status == 429 or status >= 500):
        return True
    return False


def _get_retry_after(error: Exception) -> float | None:
    """Extract retry-after header value if available."""
    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers:
            retry_after = headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass
    return None


def _calculate_backoff(attempt: int, retry_after: float | None = None) -> float:
    """Calculate exponential backoff delay with jitter."""
    if retry_after is not None and retry_after > 0:
        return retry_after

    delay = INITIAL_RETRY_DELAY * (2 ** attempt)
    delay = min(delay, MAX_RETRY_DELAY)
    # Add small jitter (±10%)
    import random
    jitter = delay * 0.1 * (2 * random.random() - 1)
    return max(0.1, delay + jitter)


# =============================================================================
# Turn Data Structures
# =============================================================================

@dataclass
class ToolEvent:
    """
    Represents a single tool invocation during a turn.

    Each tool event captures the tool_name, arguments, and result
    for recording as AgentEvents in the HarnessKernel.
    """
    tool_name: str
    arguments: dict[str, Any] | None = None
    result: Any = None
    is_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for HarnessKernel event recording."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments or {},
            "result": self.result,
            "is_error": self.is_error,
        }


@dataclass
class TurnResult:
    """
    Result of executing a single turn via the Claude SDK.

    This captures everything HarnessKernel needs to record the turn.
    """
    completed: bool = False
    turn_data: dict[str, Any] = field(default_factory=dict)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0

    def as_tuple(self) -> tuple[bool, dict[str, Any], list[dict[str, Any]], int, int]:
        """Convert to the tuple format expected by HarnessKernel.execute()."""
        return (
            self.completed,
            self.turn_data,
            self.tool_events,
            self.tokens_in,
            self.tokens_out,
        )


# =============================================================================
# Claude SDK Turn Executor
# =============================================================================

class ClaudeSDKTurnExecutor:
    """
    Turn executor that bridges HarnessKernel.execute() to the Claude SDK.

    Feature #126: Turn executor bridge connects HarnessKernel to Claude SDK

    This class implements the turn_executor callable interface expected by
    HarnessKernel.execute(turn_executor=...). It:

    1. Creates or reuses a Claude SDK client (Anthropic Messages API)
    2. Builds the prompt from spec objective/context
    3. Sends the prompt to Claude and processes the response
    4. Extracts tool_use blocks as tool_events
    5. Returns the (completed, turn_data, tool_events, tokens_in, tokens_out) tuple
    6. Handles Claude SDK errors gracefully (rate limits, network, invalid response)

    The executor maintains conversation history across turns within a single
    execution, allowing multi-turn tool-use interactions.

    Args:
        model: Claude model to use (default: claude-sonnet-4-20250514)
        api_key: Optional Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        max_tokens: Maximum tokens for each response
        project_dir: Optional project directory for client configuration
        max_error_retries: Maximum retries for transient errors

    Usage:
        executor = ClaudeSDKTurnExecutor(model="claude-sonnet-4-20250514")
        # Pass as callable to HarnessKernel
        kernel = HarnessKernel(db)
        run = kernel.execute(spec, turn_executor=executor)
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        max_tokens: int = 4096,
        project_dir: Path | None = None,
        max_error_retries: int = MAX_ERROR_RETRIES,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        self.project_dir = project_dir
        self.max_error_retries = max_error_retries

        # Client is lazily created on first call
        self._client: Any = None

        # Conversation history for multi-turn execution
        self._messages: list[dict[str, Any]] = []
        self._system_prompt: str | None = None

        _logger.info(
            "ClaudeSDKTurnExecutor initialized: model=%s, max_tokens=%d, retries=%d",
            self.model, self.max_tokens, self.max_error_retries,
        )

    def _get_or_create_client(self) -> Any:
        """
        Create or reuse an Anthropic client.

        Lazily creates the client on first call. Subsequent calls
        reuse the same client instance.

        Returns:
            An Anthropic client instance

        Raises:
            ImportError: If the anthropic package is not installed
            ValueError: If no API key is available
        """
        if self._client is not None:
            return self._client

        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for ClaudeSDKTurnExecutor. "
                "Install it with: pip install anthropic"
            )

        if not self.api_key:
            raise ValueError(
                "No Anthropic API key available. Set ANTHROPIC_API_KEY "
                "environment variable or pass api_key to constructor."
            )

        # Check for custom base URL (e.g., for GLM or alternative APIs)
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if base_url:
            kwargs["base_url"] = base_url
            _logger.info("Using custom API base URL: %s", base_url)

        self._client = anthropic.Anthropic(**kwargs)
        _logger.info("Created Anthropic client for model %s", self.model)
        return self._client

    def _build_system_prompt(self, spec: "AgentSpec") -> str:
        """
        Build the system prompt from the AgentSpec.

        Combines the spec's objective and context into a system prompt
        suitable for the Claude Messages API.

        Args:
            spec: The AgentSpec being executed

        Returns:
            The system prompt string
        """
        parts = []

        # Add objective
        if spec.objective:
            parts.append(spec.objective)

        # Add context
        if spec.context and isinstance(spec.context, dict):
            context_str = "\n".join(
                f"{k}: {v}" for k, v in spec.context.items()
                if v is not None
            )
            if context_str:
                parts.append(f"\nContext:\n{context_str}")

        return "\n\n".join(parts) if parts else "Complete the assigned task."

    def _extract_tool_events(self, response: Any) -> list[dict[str, Any]]:
        """
        Extract tool events from a Claude API response.

        Processes content blocks to find tool_use blocks and extracts
        tool_name, arguments (input), and any available results.

        Args:
            response: The Claude API response object

        Returns:
            List of tool event dicts with tool_name, arguments, result keys
        """
        tool_events = []

        if not hasattr(response, "content") or response.content is None:
            return tool_events

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "tool_use":
                tool_name = getattr(block, "name", "unknown")
                arguments = getattr(block, "input", None)
                tool_id = getattr(block, "id", None)

                tool_events.append({
                    "tool_name": tool_name,
                    "arguments": arguments if isinstance(arguments, dict) else {},
                    "result": None,  # Result is provided by tool execution, not the model
                    "is_error": False,
                    "tool_use_id": tool_id,
                })

        return tool_events

    def _extract_token_usage(self, response: Any) -> tuple[int, int]:
        """
        Extract token usage from a Claude API response.

        Args:
            response: The Claude API response object

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0, 0

        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        return input_tokens, output_tokens

    def _is_completed(self, response: Any) -> bool:
        """
        Check if the agent has signaled completion.

        The agent is considered complete when:
        - stop_reason is "end_turn" (normal completion)
        - stop_reason is "stop_sequence" (custom stop)
        - stop_reason is NOT "tool_use" (tool use means more turns needed)

        Args:
            response: The Claude API response object

        Returns:
            True if the agent has completed, False if more turns needed
        """
        stop_reason = getattr(response, "stop_reason", None)

        # Tool use means the agent wants to use tools - not completed yet
        if stop_reason == "tool_use":
            return False

        # "end_turn" or any other reason means completion
        return True

    def _extract_text_content(self, response: Any) -> str:
        """
        Extract text content from a Claude API response.

        Args:
            response: The Claude API response object

        Returns:
            Combined text content from text blocks
        """
        if not hasattr(response, "content") or response.content is None:
            return ""

        texts = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "")
                if text:
                    texts.append(text)

        return "\n".join(texts)

    def _send_message(
        self,
        client: Any,
        messages: list[dict[str, Any]],
        system: str,
    ) -> Any:
        """
        Send a message to the Claude API with retry logic.

        Handles transient errors (rate limits, timeouts, server errors)
        with exponential backoff retries.

        Args:
            client: The Anthropic client
            messages: Conversation messages
            system: System prompt

        Returns:
            The Claude API response

        Raises:
            Exception: If all retries are exhausted or a non-retryable error occurs
        """
        last_error = None

        for attempt in range(self.max_error_retries + 1):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=messages,
                )
                return response

            except Exception as e:
                last_error = e
                error_name = type(e).__name__

                if _is_retryable_error(e) and attempt < self.max_error_retries:
                    retry_after = _get_retry_after(e)
                    delay = _calculate_backoff(attempt, retry_after)

                    _logger.warning(
                        "Retryable error on attempt %d/%d (%s): %s. "
                        "Retrying in %.1fs...",
                        attempt + 1,
                        self.max_error_retries + 1,
                        error_name,
                        str(e)[:200],
                        delay,
                    )
                    time.sleep(delay)
                    continue

                # Non-retryable error or retries exhausted
                _logger.error(
                    "Claude SDK error (attempt %d/%d, %s): %s",
                    attempt + 1,
                    self.max_error_retries + 1,
                    error_name,
                    str(e)[:500],
                )
                raise

        # Should not reach here, but just in case
        raise last_error  # type: ignore[misc]

    def __call__(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
    ) -> tuple[bool, dict[str, Any], list[dict[str, Any]], int, int]:
        """
        Execute one turn via the Claude SDK.

        This is the callable interface expected by HarnessKernel.execute().

        Args:
            run: The current AgentRun
            spec: The AgentSpec being executed

        Returns:
            Tuple of (completed, turn_data, tool_events, tokens_in, tokens_out):
            - completed: True if agent signals completion (stop_reason != "tool_use")
            - turn_data: Dict with response text and metadata
            - tool_events: List of tool event dicts with tool_name, arguments, result
            - tokens_in: Input tokens consumed this turn
            - tokens_out: Output tokens consumed this turn

        Error Handling:
            Claude SDK errors are caught and returned as error turn data
            rather than raising unhandled exceptions. This ensures the
            kernel loop continues gracefully:
            - Rate limit errors: Retried with backoff, then returned as error
            - Network errors: Retried with backoff, then returned as error
            - Invalid response: Returned as error turn data
            - Authentication errors: Returned as error (not retryable)
        """
        try:
            return self._execute_turn(run, spec)
        except Exception as e:
            # Catch ALL errors and return as error turn data
            # This ensures the kernel loop never crashes due to SDK errors
            _logger.error(
                "Turn executor error for run %s: %s: %s",
                run.id, type(e).__name__, str(e)[:500],
            )

            error_data = {
                "error": True,
                "error_type": type(e).__name__,
                "error_message": str(e)[:1000],
                "response_text": "",
            }

            # Return completed=True on non-retryable errors to stop the loop
            # The kernel will finalize the run based on the error data
            return TurnResult(
                completed=True,
                turn_data=error_data,
                tool_events=[],
                tokens_in=0,
                tokens_out=0,
            ).as_tuple()

    def _execute_turn(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
    ) -> tuple[bool, dict[str, Any], list[dict[str, Any]], int, int]:
        """
        Internal implementation of a single turn execution.

        Separated from __call__ to allow __call__ to wrap with error handling.

        Args:
            run: The current AgentRun
            spec: The AgentSpec being executed

        Returns:
            Tuple of (completed, turn_data, tool_events, tokens_in, tokens_out)
        """
        # Lazily create or reuse client
        client = self._get_or_create_client()

        # Build system prompt on first turn
        if self._system_prompt is None:
            self._system_prompt = self._build_system_prompt(spec)

        # If no messages yet, start conversation
        if not self._messages:
            # Initial user message with the task objective
            initial_message = spec.objective or "Complete the assigned task."
            self._messages.append({
                "role": "user",
                "content": initial_message,
            })

        # Send message to Claude
        response = self._send_message(
            client=client,
            messages=self._messages,
            system=self._system_prompt,
        )

        # Extract response data
        text_content = self._extract_text_content(response)
        tool_events = self._extract_tool_events(response)
        tokens_in, tokens_out = self._extract_token_usage(response)
        completed = self._is_completed(response)

        # Build turn data
        turn_data = {
            "response_text": text_content[:2000],  # Cap for storage
            "stop_reason": getattr(response, "stop_reason", None),
            "tool_count": len(tool_events),
            "model": getattr(response, "model", self.model),
        }

        # Add assistant response to conversation history
        # Convert response content blocks to serializable format
        assistant_content = []
        if hasattr(response, "content") and response.content:
            for block in response.content:
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    assistant_content.append({
                        "type": "text",
                        "text": getattr(block, "text", ""),
                    })
                elif block_type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": getattr(block, "id", ""),
                        "name": getattr(block, "name", ""),
                        "input": getattr(block, "input", {}),
                    })

        self._messages.append({
            "role": "assistant",
            "content": assistant_content or text_content,
        })

        # If there were tool_use blocks and not completed,
        # we need to add tool results placeholder for next turn
        if tool_events and not completed:
            tool_results = []
            for event in tool_events:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": event.get("tool_use_id", ""),
                    "content": str(event.get("result", "Tool execution handled by kernel")),
                })
            self._messages.append({
                "role": "user",
                "content": tool_results,
            })

        _logger.info(
            "Turn executed: run=%s, completed=%s, tools=%d, tokens_in=%d, tokens_out=%d",
            run.id, completed, len(tool_events), tokens_in, tokens_out,
        )

        return TurnResult(
            completed=completed,
            turn_data=turn_data,
            tool_events=tool_events,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        ).as_tuple()

    def reset(self) -> None:
        """
        Reset conversation state for a new execution.

        Call this between separate spec executions to clear
        conversation history while reusing the client connection.
        """
        self._messages.clear()
        self._system_prompt = None
        _logger.debug("Turn executor conversation state reset")


# =============================================================================
# Factory Function
# =============================================================================

def create_turn_executor(
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_tokens: int = 4096,
    project_dir: Path | None = None,
    max_error_retries: int = MAX_ERROR_RETRIES,
) -> ClaudeSDKTurnExecutor:
    """
    Create a turn executor that bridges HarnessKernel to the Claude SDK.

    This is a convenience factory function that creates a
    ClaudeSDKTurnExecutor instance.

    Args:
        model: Claude model to use
        api_key: Optional Anthropic API key
        max_tokens: Maximum tokens per response
        project_dir: Optional project directory
        max_error_retries: Maximum retries for transient errors

    Returns:
        A ClaudeSDKTurnExecutor instance ready to be passed
        to HarnessKernel.execute(turn_executor=...)

    Example:
        executor = create_turn_executor(model="claude-sonnet-4-20250514")
        kernel = HarnessKernel(db)
        run = kernel.execute(spec, turn_executor=executor)
    """
    return ClaudeSDKTurnExecutor(
        model=model,
        api_key=api_key,
        max_tokens=max_tokens,
        project_dir=project_dir,
        max_error_retries=max_error_retries,
    )


# Alias for clarity when distinguishing from SDK session executor
RawMessagesTurnExecutor = ClaudeSDKTurnExecutor
