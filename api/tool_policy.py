"""
Tool Policy Enforcement
=======================

Implements ToolPolicy enforcement for the HarnessKernel.

This module provides:
- Extraction of forbidden_patterns from spec.tool_policy
- Regex compilation at spec load time for efficiency
- Tool argument validation against forbidden patterns
- Event recording for blocked tool calls

Feature #41: ToolPolicy Forbidden Patterns Enforcement

Key Design Principles:
- Fail-safe: If pattern extraction fails, allow the tool call with a warning
- Continue execution: Blocked calls don't abort the run, just return an error
- Comprehensive logging: All policy decisions are recorded as events
- Efficient: Patterns are compiled once and cached per spec
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from api.agentspec_models import AgentEvent, AgentSpec


# Setup logger
_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Exceptions
# =============================================================================

class ToolPolicyError(Exception):
    """Base exception for tool policy errors."""
    pass


class PatternCompilationError(ToolPolicyError):
    """Raised when a forbidden pattern fails to compile as regex."""

    def __init__(
        self,
        pattern: str,
        error: str,
        message: str | None = None,
    ):
        self.pattern = pattern
        self.compile_error = error

        if message is None:
            message = f"Failed to compile forbidden pattern '{pattern}': {error}"

        super().__init__(message)


class ToolCallBlocked(ToolPolicyError):
    """
    Raised when a tool call is blocked by forbidden patterns.

    This exception provides information for:
    - Recording blocked tool_call events
    - Returning explanatory errors to the agent
    """

    def __init__(
        self,
        tool_name: str,
        pattern_matched: str,
        arguments: dict[str, Any],
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.pattern_matched = pattern_matched
        self.arguments = arguments

        if message is None:
            message = (
                f"Tool call '{tool_name}' blocked: "
                f"arguments match forbidden pattern '{pattern_matched}'"
            )

        super().__init__(message)


# =============================================================================
# Pattern Compilation
# =============================================================================

@dataclass
class CompiledPattern:
    """A compiled forbidden pattern with metadata."""

    original: str  # Original pattern string
    regex: re.Pattern  # Compiled regex
    description: str | None = None  # Optional human-readable description


def compile_forbidden_patterns(
    patterns: list[str] | None,
    *,
    strict: bool = False,
) -> list[CompiledPattern]:
    """
    Compile forbidden patterns as regex at spec load time.

    This function should be called once when an AgentSpec is loaded,
    not on every tool call.

    Args:
        patterns: List of regex pattern strings (may be None or empty)
        strict: If True, raise PatternCompilationError on invalid patterns.
                If False (default), log warning and skip invalid patterns.

    Returns:
        List of CompiledPattern objects ready for matching

    Raises:
        PatternCompilationError: If strict=True and a pattern is invalid

    Example:
        >>> patterns = ["rm -rf", "DROP TABLE", r"\\bpassword\\b"]
        >>> compiled = compile_forbidden_patterns(patterns)
        >>> len(compiled)
        3
    """
    if not patterns:
        return []

    compiled: list[CompiledPattern] = []

    for pattern in patterns:
        if not isinstance(pattern, str):
            _logger.warning(
                "Skipping non-string forbidden pattern: %r (type: %s)",
                pattern, type(pattern).__name__
            )
            continue

        if not pattern.strip():
            _logger.warning("Skipping empty forbidden pattern")
            continue

        try:
            # Compile with IGNORECASE for more robust matching
            regex = re.compile(pattern, re.IGNORECASE)
            compiled.append(CompiledPattern(
                original=pattern,
                regex=regex,
            ))
            _logger.debug("Compiled forbidden pattern: %s", pattern)

        except re.error as e:
            error_msg = str(e)
            if strict:
                raise PatternCompilationError(pattern, error_msg)
            else:
                _logger.warning(
                    "Invalid regex pattern '%s': %s (skipping)",
                    pattern, error_msg
                )

    return compiled


def extract_forbidden_patterns(tool_policy: dict[str, Any] | None) -> list[str]:
    """
    Extract forbidden_patterns from a tool_policy dict.

    Handles various edge cases:
    - None tool_policy
    - Missing forbidden_patterns key
    - Empty list
    - Non-list values (with warning)

    Args:
        tool_policy: Tool policy dictionary from AgentSpec

    Returns:
        List of pattern strings (may be empty)

    Example:
        >>> policy = {
        ...     "policy_version": "v1",
        ...     "allowed_tools": ["feature_mark_passing"],
        ...     "forbidden_patterns": ["rm -rf", "DROP TABLE"]
        ... }
        >>> extract_forbidden_patterns(policy)
        ['rm -rf', 'DROP TABLE']
    """
    if tool_policy is None:
        return []

    patterns = tool_policy.get("forbidden_patterns")

    if patterns is None:
        return []

    if not isinstance(patterns, list):
        _logger.warning(
            "forbidden_patterns is not a list: %r (type: %s), treating as empty",
            patterns, type(patterns).__name__
        )
        return []

    return patterns


# =============================================================================
# Argument Serialization
# =============================================================================

def serialize_tool_arguments(
    arguments: dict[str, Any] | None,
    *,
    max_depth: int = 10,
) -> str:
    """
    Serialize tool arguments to a string for pattern matching.

    This function converts the arguments dict to a searchable string
    that can be checked against forbidden patterns. It handles:
    - Nested dicts and lists
    - Various value types (str, int, bool, None)
    - Circular references (via max_depth)

    Args:
        arguments: Tool arguments dict (may be None)
        max_depth: Maximum recursion depth for nested structures

    Returns:
        String representation of arguments suitable for regex matching

    Example:
        >>> args = {"command": "rm -rf /", "force": True}
        >>> serialize_tool_arguments(args)
        '{"command": "rm -rf /", "force": true}'
    """
    if arguments is None:
        return ""

    if not isinstance(arguments, dict):
        _logger.warning(
            "Tool arguments is not a dict: %r (type: %s)",
            arguments, type(arguments).__name__
        )
        return str(arguments)

    try:
        # JSON serialization provides consistent, searchable format
        return json.dumps(arguments, default=str, sort_keys=True)
    except (TypeError, ValueError) as e:
        _logger.warning(
            "Failed to serialize tool arguments as JSON: %s. Using str() fallback.",
            e
        )
        return str(arguments)


# =============================================================================
# Pattern Matching
# =============================================================================

def check_arguments_against_patterns(
    serialized_args: str,
    compiled_patterns: list[CompiledPattern],
) -> CompiledPattern | None:
    """
    Check serialized arguments against all forbidden patterns.

    Args:
        serialized_args: Serialized tool arguments string
        compiled_patterns: List of compiled forbidden patterns

    Returns:
        The first matching pattern, or None if no patterns match

    Example:
        >>> patterns = compile_forbidden_patterns(["rm -rf", "DROP TABLE"])
        >>> check_arguments_against_patterns('{"cmd": "rm -rf /home"}', patterns)
        CompiledPattern(original='rm -rf', ...)
    """
    if not serialized_args:
        return None

    if not compiled_patterns:
        return None

    for pattern in compiled_patterns:
        if pattern.regex.search(serialized_args):
            _logger.warning(
                "Forbidden pattern '%s' matched in arguments: %s",
                pattern.original, serialized_args[:200]
            )
            return pattern

    return None


# =============================================================================
# Event Recording
# =============================================================================

def record_blocked_tool_call_event(
    db: "Session",
    run_id: str,
    sequence: int,
    tool_name: str,
    arguments: dict[str, Any],
    pattern_matched: str,
) -> "AgentEvent":
    """
    Record a tool_call event with blocked=true and pattern matched.

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        tool_name: Name of the blocked tool
        arguments: Original tool arguments
        pattern_matched: The forbidden pattern that matched

    Returns:
        The created AgentEvent
    """
    from api.agentspec_models import AgentEvent

    # Prepare payload with blocked status
    payload = {
        "tool": tool_name,
        "args": arguments,
        "blocked": True,
        "pattern_matched": pattern_matched,
        "reason": f"Arguments match forbidden pattern: {pattern_matched}",
    }

    event = AgentEvent(
        run_id=run_id,
        sequence=sequence,
        event_type="tool_call",
        timestamp=_utc_now(),
        payload=payload,
        tool_name=tool_name,
    )

    db.add(event)
    # Note: Caller should commit the session

    _logger.info(
        "Recorded blocked tool_call event: run=%s, tool=%s, pattern=%s",
        run_id, tool_name, pattern_matched
    )

    return event


# =============================================================================
# ToolPolicyEnforcer
# =============================================================================

@dataclass
class ToolPolicyEnforcer:
    """
    Enforces tool policy restrictions during agent execution.

    This class is instantiated once per AgentSpec and cached for
    efficient enforcement during the run.

    Usage:
        # At spec load time
        enforcer = ToolPolicyEnforcer.from_spec(spec)

        # Before each tool call
        try:
            enforcer.validate_tool_call(tool_name, arguments)
        except ToolCallBlocked as e:
            # Record event and return error to agent
            record_blocked_tool_call_event(...)
            return error_message

    Attributes:
        spec_id: ID of the AgentSpec this enforcer belongs to
        forbidden_patterns: List of compiled forbidden patterns
        allowed_tools: List of allowed tool names (may be None for all)
        strict_mode: If True, fail on pattern compilation errors
    """

    spec_id: str
    forbidden_patterns: list[CompiledPattern] = field(default_factory=list)
    allowed_tools: list[str] | None = None  # None means all tools allowed
    strict_mode: bool = False

    @classmethod
    def from_spec(
        cls,
        spec: "AgentSpec",
        *,
        strict: bool = False,
    ) -> "ToolPolicyEnforcer":
        """
        Create a ToolPolicyEnforcer from an AgentSpec.

        Extracts tool_policy and compiles forbidden_patterns.

        Args:
            spec: The AgentSpec to create enforcer for
            strict: If True, raise on pattern compilation errors

        Returns:
            Configured ToolPolicyEnforcer

        Raises:
            PatternCompilationError: If strict=True and patterns are invalid
        """
        tool_policy = spec.tool_policy or {}

        # Step 1: Extract forbidden_patterns from spec.tool_policy
        patterns = extract_forbidden_patterns(tool_policy)

        # Step 2: Compile patterns as regex at spec load time
        compiled = compile_forbidden_patterns(patterns, strict=strict)

        # Extract allowed_tools
        allowed = tool_policy.get("allowed_tools")
        if allowed is not None and not isinstance(allowed, list):
            _logger.warning(
                "allowed_tools is not a list: %r, treating as None (all allowed)",
                allowed
            )
            allowed = None

        _logger.info(
            "Created ToolPolicyEnforcer for spec %s: %d forbidden patterns, "
            "%s allowed tools",
            spec.id,
            len(compiled),
            "all" if allowed is None else len(allowed)
        )

        return cls(
            spec_id=spec.id,
            forbidden_patterns=compiled,
            allowed_tools=allowed,
            strict_mode=strict,
        )

    @classmethod
    def from_tool_policy(
        cls,
        spec_id: str,
        tool_policy: dict[str, Any] | None,
        *,
        strict: bool = False,
    ) -> "ToolPolicyEnforcer":
        """
        Create a ToolPolicyEnforcer from a tool_policy dict.

        Useful when you don't have the full AgentSpec object.

        Args:
            spec_id: ID to associate with this enforcer
            tool_policy: Tool policy dictionary
            strict: If True, raise on pattern compilation errors

        Returns:
            Configured ToolPolicyEnforcer
        """
        tool_policy = tool_policy or {}

        patterns = extract_forbidden_patterns(tool_policy)
        compiled = compile_forbidden_patterns(patterns, strict=strict)

        allowed = tool_policy.get("allowed_tools")
        if allowed is not None and not isinstance(allowed, list):
            allowed = None

        return cls(
            spec_id=spec_id,
            forbidden_patterns=compiled,
            allowed_tools=allowed,
            strict_mode=strict,
        )

    def validate_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> None:
        """
        Validate a tool call against the policy.

        This method checks:
        1. Tool is in allowed_tools list (if specified)
        2. Arguments don't match any forbidden_patterns

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments dict

        Raises:
            ToolCallBlocked: If the tool call violates the policy
        """
        # Check allowed tools (if specified)
        if self.allowed_tools is not None:
            if tool_name not in self.allowed_tools:
                raise ToolCallBlocked(
                    tool_name=tool_name,
                    pattern_matched="[not_in_allowed_tools]",
                    arguments=arguments or {},
                    message=f"Tool '{tool_name}' is not in allowed_tools list",
                )

        # Step 3: Before each tool call, serialize arguments to string
        serialized = serialize_tool_arguments(arguments)

        # Step 4 & 5: Check arguments against all forbidden patterns
        matched = check_arguments_against_patterns(serialized, self.forbidden_patterns)

        if matched is not None:
            # Step 5: If pattern matches, block tool call
            raise ToolCallBlocked(
                tool_name=tool_name,
                pattern_matched=matched.original,
                arguments=arguments or {},
            )

    def check_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> tuple[bool, str | None, str | None]:
        """
        Check a tool call without raising exceptions.

        Returns a tuple of (allowed, pattern_matched, error_message).
        This is useful when you want to handle blocked calls inline.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments dict

        Returns:
            Tuple of (allowed: bool, pattern: str | None, error: str | None)

        Example:
            >>> enforcer = ToolPolicyEnforcer(...)
            >>> allowed, pattern, error = enforcer.check_tool_call("bash", {"cmd": "rm -rf /"})
            >>> if not allowed:
            ...     print(f"Blocked: {error}")
        """
        try:
            self.validate_tool_call(tool_name, arguments)
            return (True, None, None)
        except ToolCallBlocked as e:
            return (False, e.pattern_matched, str(e))

    def get_blocked_error_message(
        self,
        tool_name: str,
        pattern_matched: str,
    ) -> str:
        """
        Generate an error message for blocked tool calls.

        This message is returned to the agent to explain why the
        tool call was blocked.

        Args:
            tool_name: Name of the blocked tool
            pattern_matched: The pattern that matched

        Returns:
            Human-readable error message for the agent

        Step 7: Return error to agent explaining blocked operation
        """
        return (
            f"Tool call '{tool_name}' was blocked by security policy. "
            f"The arguments match a forbidden pattern: '{pattern_matched}'. "
            f"Please modify your request to avoid dangerous operations."
        )

    @property
    def has_forbidden_patterns(self) -> bool:
        """True if any forbidden patterns are configured."""
        return len(self.forbidden_patterns) > 0

    @property
    def pattern_count(self) -> int:
        """Number of compiled forbidden patterns."""
        return len(self.forbidden_patterns)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization/logging."""
        return {
            "spec_id": self.spec_id,
            "pattern_count": len(self.forbidden_patterns),
            "patterns": [p.original for p in self.forbidden_patterns],
            "allowed_tools": self.allowed_tools,
            "strict_mode": self.strict_mode,
        }


# =============================================================================
# Integration with HarnessKernel
# =============================================================================

def create_enforcer_for_run(
    spec: "AgentSpec",
    *,
    strict: bool = False,
) -> ToolPolicyEnforcer:
    """
    Create a ToolPolicyEnforcer for a kernel execution run.

    This is the main entry point for HarnessKernel integration.

    Args:
        spec: The AgentSpec being executed
        strict: If True, fail on pattern compilation errors

    Returns:
        Configured ToolPolicyEnforcer

    Example:
        # In HarnessKernel.execute():
        enforcer = create_enforcer_for_run(spec)

        # Before each tool call:
        try:
            enforcer.validate_tool_call(tool_name, arguments)
        except ToolCallBlocked as e:
            record_blocked_tool_call_event(db, run_id, seq, ...)
            return e.message
    """
    return ToolPolicyEnforcer.from_spec(spec, strict=strict)
