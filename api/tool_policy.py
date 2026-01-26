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
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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


class DirectoryAccessBlocked(ToolPolicyError):
    """
    Raised when a file operation targets a path outside allowed_directories.

    This exception is raised for:
    - Paths outside the sandbox directories
    - Path traversal attempts (..)
    - Symlinks that resolve outside allowed directories

    Feature #42: Directory Sandbox Restriction
    """

    def __init__(
        self,
        tool_name: str,
        target_path: str,
        reason: str,
        allowed_directories: list[str],
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.target_path = target_path
        self.reason = reason
        self.allowed_directories = allowed_directories

        if message is None:
            dirs_str = ", ".join(allowed_directories[:3])  # Show first 3 for brevity
            if len(allowed_directories) > 3:
                dirs_str += f" (and {len(allowed_directories) - 3} more)"
            message = (
                f"Tool call '{tool_name}' blocked: "
                f"path '{target_path}' is not within allowed directories. "
                f"Reason: {reason}. "
                f"Allowed directories: [{dirs_str}]"
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
# Directory Sandbox (Feature #42)
# =============================================================================

# File operation tools that require path validation
FILE_OPERATION_TOOLS = frozenset({
    "read_file", "write_file", "edit_file", "delete_file",
    "create_file", "create_directory", "delete_directory",
    "copy_file", "move_file", "rename_file",
    # Common tool names from various tool providers
    "bash", "shell", "exec", "execute",
    "file_read", "file_write", "file_edit", "file_delete",
})

# Argument keys that typically contain file paths
PATH_ARGUMENT_KEYS = frozenset({
    "path", "file_path", "filepath", "file", "filename",
    "target", "target_path", "destination", "dest",
    "source", "source_path", "src",
    "directory", "dir", "folder",
    "cwd", "working_directory",
})


def extract_allowed_directories(tool_policy: dict[str, Any] | None) -> list[str]:
    """
    Extract allowed_directories from a tool_policy dict.

    Feature #42, Step 1: Extract allowed_directories from spec.tool_policy

    Handles various edge cases:
    - None tool_policy
    - Missing allowed_directories key (returns empty = no restriction)
    - Empty list (returns empty = no restriction)
    - Non-list values (with warning)

    Args:
        tool_policy: Tool policy dictionary from AgentSpec

    Returns:
        List of directory path strings (may be empty)
        Empty list means no sandbox restriction (all directories allowed)

    Example:
        >>> policy = {
        ...     "allowed_directories": ["/home/user/project", "/tmp"]
        ... }
        >>> extract_allowed_directories(policy)
        ['/home/user/project', '/tmp']
    """
    if tool_policy is None:
        return []

    directories = tool_policy.get("allowed_directories")

    if directories is None:
        return []

    if not isinstance(directories, list):
        _logger.warning(
            "allowed_directories is not a list: %r (type: %s), treating as empty",
            directories, type(directories).__name__
        )
        return []

    # Filter out non-string entries
    valid_dirs = []
    for d in directories:
        if isinstance(d, str):
            valid_dirs.append(d)
        else:
            _logger.warning(
                "Skipping non-string allowed_directory: %r (type: %s)",
                d, type(d).__name__
            )

    return valid_dirs


def resolve_to_absolute_paths(
    directories: list[str],
    base_dir: str | None = None,
) -> list[Path]:
    """
    Resolve all allowed directories to absolute paths.

    Feature #42, Step 2: Resolve all allowed paths to absolute paths

    Args:
        directories: List of directory paths (may be relative)
        base_dir: Base directory for resolving relative paths (default: cwd)

    Returns:
        List of resolved absolute Path objects

    Example:
        >>> resolve_to_absolute_paths(["./src", "/absolute/path"])
        [PosixPath('/current/working/dir/src'), PosixPath('/absolute/path')]
    """
    if not directories:
        return []

    base = Path(base_dir) if base_dir else Path.cwd()
    resolved: list[Path] = []

    for dir_str in directories:
        try:
            dir_path = Path(dir_str)

            # If relative, resolve against base_dir
            if not dir_path.is_absolute():
                dir_path = base / dir_path

            # Resolve to absolute, normalized path (no ..)
            resolved_path = dir_path.resolve()
            resolved.append(resolved_path)

            _logger.debug(
                "Resolved allowed directory: %s -> %s",
                dir_str, resolved_path
            )

        except (ValueError, OSError) as e:
            _logger.warning(
                "Failed to resolve allowed directory '%s': %s",
                dir_str, e
            )

    return resolved


def extract_path_from_arguments(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> str | None:
    """
    Extract target file/directory path from tool arguments.

    Feature #42, Step 3: For file operation tools, extract target path from arguments

    Checks common path argument keys and tool-specific patterns.

    Args:
        tool_name: Name of the tool being called
        arguments: Tool arguments dict

    Returns:
        Extracted path string, or None if not found

    Example:
        >>> extract_path_from_arguments("write_file", {"path": "/etc/passwd"})
        '/etc/passwd'
    """
    if arguments is None:
        return None

    # Check common path argument keys
    for key in PATH_ARGUMENT_KEYS:
        if key in arguments:
            value = arguments[key]
            if isinstance(value, str):
                return value

    # For bash/shell commands, try to extract paths from command string
    if tool_name.lower() in ("bash", "shell", "exec", "execute"):
        command = arguments.get("command") or arguments.get("cmd")
        if isinstance(command, str):
            # Extract first file path-like argument
            # This is a heuristic - may not catch all cases
            import shlex
            try:
                parts = shlex.split(command)
                for part in parts:
                    if part.startswith("/") or part.startswith("./") or part.startswith("../"):
                        return part
            except ValueError:
                pass  # Invalid shell syntax, can't parse

    return None


def contains_path_traversal(path_str: str) -> bool:
    """
    Check if a path string contains path traversal attempts.

    Feature #42, Step 6: Block path traversal attempts (..)

    Args:
        path_str: Path string to check

    Returns:
        True if path contains '..' traversal, False otherwise

    Example:
        >>> contains_path_traversal("/home/user/../root/secret")
        True
        >>> contains_path_traversal("/home/user/project/file.txt")
        False
        >>> contains_path_traversal("/home/user/file..txt")  # Not a traversal
        False
    """
    # Check each part of the path for actual ".." traversal component
    path = Path(path_str)
    for part in path.parts:
        if part == "..":
            return True

    # Check for URL-encoded traversal patterns
    # These need to be checked in context (as path separators)
    path_lower = path_str.lower()

    # URL-encoded patterns that indicate traversal
    encoded_traversal_patterns = [
        "%2e%2e/",      # URL-encoded ../
        "/%2e%2e",      # /.. URL-encoded
        "%252e%252e/",  # Double URL-encoded ../
        "/%252e%252e",  # Double URL-encoded /..
        "..%c0%af",     # Unicode overlong encoding of /
        "..%c1%9c",     # Unicode overlong encoding variant
        "..%2f",        # ../ with URL-encoded /
        "..%5c",        # ..\ with URL-encoded \
    ]

    for pattern in encoded_traversal_patterns:
        if pattern in path_lower:
            return True

    # Check for standalone ".." at start or end (boundary cases)
    # This catches "../" at start or "/.." at end
    if path_str.startswith("..") and len(path_str) > 2 and path_str[2] in "/\\":
        return True
    if path_str.endswith("/..") or path_str.endswith("\\.."):
        return True

    return False


def resolve_target_path(
    path_str: str,
    base_dir: str | None = None,
    *,
    follow_symlinks: bool = True,
) -> tuple[Path, bool]:
    """
    Resolve a target path to absolute form, optionally following symlinks.

    Feature #42, Steps 4 & 7:
    - Step 4: Resolve target path to absolute
    - Step 7: If target is symlink, resolve and validate final target

    Args:
        path_str: Target path string
        base_dir: Base directory for relative paths
        follow_symlinks: Whether to resolve symlinks to their targets

    Returns:
        Tuple of (resolved_path, was_symlink)

    Example:
        >>> resolve_target_path("./file.txt", "/home/user")
        (PosixPath('/home/user/file.txt'), False)
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    target = Path(path_str)

    # Make absolute if relative
    if not target.is_absolute():
        target = base / target

    was_symlink = False

    if follow_symlinks:
        # Check if it's a symlink before resolving
        try:
            was_symlink = target.is_symlink()
        except OSError:
            pass  # Path doesn't exist or other error

        # resolve() normalizes the path AND follows symlinks
        resolved = target.resolve()
    else:
        # Just normalize without following symlinks
        # Use absolute() + normpath pattern
        resolved = Path(os.path.normpath(target.absolute()))

    return resolved, was_symlink


def is_path_under_directories(
    target_path: Path,
    allowed_directories: list[Path],
) -> bool:
    """
    Check if a target path is under any of the allowed directories.

    Feature #42, Step 5: Check if target is under any allowed directory

    Args:
        target_path: Resolved absolute path to check
        allowed_directories: List of resolved allowed directory paths

    Returns:
        True if target is under any allowed directory, False otherwise

    Example:
        >>> allowed = [Path("/home/user/project")]
        >>> is_path_under_directories(Path("/home/user/project/src/file.py"), allowed)
        True
        >>> is_path_under_directories(Path("/etc/passwd"), allowed)
        False
    """
    if not allowed_directories:
        # Empty list means no restriction
        return True

    for allowed_dir in allowed_directories:
        try:
            # Try to compute relative path
            # If successful without '..' at start, target is under allowed_dir
            relative = target_path.relative_to(allowed_dir)
            # relative_to raises ValueError if not a subpath
            return True
        except ValueError:
            continue

    return False


def validate_directory_access(
    tool_name: str,
    target_path_str: str,
    allowed_directories: list[Path],
    base_dir: str | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    Validate that a file operation target is within allowed directories.

    Feature #42: Combined validation including all security checks.

    This function performs:
    1. Path traversal detection
    2. Path resolution to absolute
    3. Symlink resolution and validation
    4. Directory containment check

    Args:
        tool_name: Name of the tool making the access
        target_path_str: Target path string from tool arguments
        allowed_directories: List of resolved allowed directory paths
        base_dir: Base directory for resolving relative paths

    Returns:
        Tuple of (allowed: bool, reason: str | None, details: dict)
        - allowed: True if access is permitted
        - reason: Explanation if blocked (None if allowed)
        - details: Additional information for logging

    Example:
        >>> allowed_dirs = [Path("/home/user/project")]
        >>> validate_directory_access("write_file", "/home/user/project/file.txt", allowed_dirs)
        (True, None, {...})
        >>> validate_directory_access("write_file", "/etc/passwd", allowed_dirs)
        (False, 'Path is not within any allowed directory', {...})
    """
    details: dict[str, Any] = {
        "original_path": target_path_str,
        "tool": tool_name,
    }

    # Step 6: Block path traversal attempts
    if contains_path_traversal(target_path_str):
        details["traversal_detected"] = True
        return (
            False,
            "Path contains directory traversal (..) which is not allowed",
            details,
        )

    # Steps 4 & 7: Resolve to absolute and handle symlinks
    try:
        resolved_path, was_symlink = resolve_target_path(
            target_path_str,
            base_dir=base_dir,
            follow_symlinks=True,  # Step 7: resolve symlinks
        )
        details["resolved_path"] = str(resolved_path)
        details["was_symlink"] = was_symlink

        if was_symlink:
            _logger.debug(
                "Symlink detected: %s -> %s",
                target_path_str, resolved_path
            )

    except (ValueError, OSError) as e:
        details["resolution_error"] = str(e)
        return (
            False,
            f"Failed to resolve path: {e}",
            details,
        )

    # Step 5: Check if under allowed directories
    if not is_path_under_directories(resolved_path, allowed_directories):
        details["allowed_directories"] = [str(d) for d in allowed_directories]
        return (
            False,
            "Path is not within any allowed directory",
            details,
        )

    # Access allowed
    return (True, None, details)


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
    allowed_directories: list[Path] = field(default_factory=list)  # Feature #42: Sandbox
    base_dir: str | None = None  # Base directory for relative path resolution
    strict_mode: bool = False

    @classmethod
    def from_spec(
        cls,
        spec: "AgentSpec",
        *,
        strict: bool = False,
        base_dir: str | None = None,
    ) -> "ToolPolicyEnforcer":
        """
        Create a ToolPolicyEnforcer from an AgentSpec.

        Extracts tool_policy and compiles forbidden_patterns.
        Feature #42: Also extracts and resolves allowed_directories for sandbox.

        Args:
            spec: The AgentSpec to create enforcer for
            strict: If True, raise on pattern compilation errors
            base_dir: Base directory for resolving relative paths

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

        # Feature #42, Steps 1-2: Extract and resolve allowed_directories
        allowed_dirs_raw = extract_allowed_directories(tool_policy)
        allowed_dirs_resolved = resolve_to_absolute_paths(allowed_dirs_raw, base_dir)

        _logger.info(
            "Created ToolPolicyEnforcer for spec %s: %d forbidden patterns, "
            "%s allowed tools, %d allowed directories",
            spec.id,
            len(compiled),
            "all" if allowed is None else len(allowed),
            len(allowed_dirs_resolved),
        )

        return cls(
            spec_id=spec.id,
            forbidden_patterns=compiled,
            allowed_tools=allowed,
            allowed_directories=allowed_dirs_resolved,
            base_dir=base_dir,
            strict_mode=strict,
        )

    @classmethod
    def from_tool_policy(
        cls,
        spec_id: str,
        tool_policy: dict[str, Any] | None,
        *,
        strict: bool = False,
        base_dir: str | None = None,
    ) -> "ToolPolicyEnforcer":
        """
        Create a ToolPolicyEnforcer from a tool_policy dict.

        Useful when you don't have the full AgentSpec object.
        Feature #42: Also extracts and resolves allowed_directories.

        Args:
            spec_id: ID to associate with this enforcer
            tool_policy: Tool policy dictionary
            strict: If True, raise on pattern compilation errors
            base_dir: Base directory for resolving relative paths

        Returns:
            Configured ToolPolicyEnforcer
        """
        tool_policy = tool_policy or {}

        patterns = extract_forbidden_patterns(tool_policy)
        compiled = compile_forbidden_patterns(patterns, strict=strict)

        allowed = tool_policy.get("allowed_tools")
        if allowed is not None and not isinstance(allowed, list):
            allowed = None

        # Feature #42: Extract and resolve allowed_directories
        allowed_dirs_raw = extract_allowed_directories(tool_policy)
        allowed_dirs_resolved = resolve_to_absolute_paths(allowed_dirs_raw, base_dir)

        return cls(
            spec_id=spec_id,
            forbidden_patterns=compiled,
            allowed_tools=allowed,
            allowed_directories=allowed_dirs_resolved,
            base_dir=base_dir,
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
        3. Feature #42: File paths are within allowed_directories (if specified)

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments dict

        Raises:
            ToolCallBlocked: If the tool call violates forbidden patterns
            DirectoryAccessBlocked: If the tool accesses paths outside sandbox
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

        # Feature #42: Directory sandbox validation
        # Only check if allowed_directories is configured (non-empty)
        if self.allowed_directories:
            self._validate_directory_access(tool_name, arguments)

    def _validate_directory_access(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> None:
        """
        Validate that file paths in tool arguments are within allowed directories.

        Feature #42: Directory Sandbox Restriction

        Steps 3-9:
        - Step 3: Extract target path from arguments
        - Step 4: Resolve target path to absolute
        - Step 5: Check if target is under any allowed directory
        - Step 6: Block path traversal attempts (..)
        - Step 7: If target is symlink, resolve and validate final target
        - Step 8: Record violation in event log (done by caller)
        - Step 9: Return permission denied error to agent

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments dict

        Raises:
            DirectoryAccessBlocked: If path is outside allowed directories
        """
        # Step 3: Extract target path from arguments
        target_path = extract_path_from_arguments(tool_name, arguments)

        if target_path is None:
            # No path found in arguments - allow (tool may not use files)
            return

        # Steps 4-7: Validate directory access
        allowed, reason, details = validate_directory_access(
            tool_name=tool_name,
            target_path_str=target_path,
            allowed_directories=self.allowed_directories,
            base_dir=self.base_dir,
        )

        if not allowed:
            # Step 9: Return permission denied error
            _logger.warning(
                "Directory access blocked for spec %s: tool=%s, path=%s, reason=%s",
                self.spec_id, tool_name, target_path, reason
            )
            raise DirectoryAccessBlocked(
                tool_name=tool_name,
                target_path=target_path,
                reason=reason or "Unknown reason",
                allowed_directories=[str(d) for d in self.allowed_directories],
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
        except DirectoryAccessBlocked as e:
            return (False, f"[directory_access:{e.reason}]", str(e))

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

    @property
    def has_directory_sandbox(self) -> bool:
        """True if directory sandbox is configured (Feature #42)."""
        return len(self.allowed_directories) > 0

    @property
    def directory_count(self) -> int:
        """Number of allowed directories in sandbox (Feature #42)."""
        return len(self.allowed_directories)

    def get_directory_blocked_error_message(
        self,
        tool_name: str,
        target_path: str,
        reason: str,
    ) -> str:
        """
        Generate an error message for directory access violations.

        Feature #42, Step 9: Return permission denied error to agent.

        Args:
            tool_name: Name of the blocked tool
            target_path: The path that was blocked
            reason: Reason for blocking

        Returns:
            Human-readable error message for the agent
        """
        dirs_str = ", ".join(str(d) for d in self.allowed_directories[:3])
        if len(self.allowed_directories) > 3:
            dirs_str += f" (and {len(self.allowed_directories) - 3} more)"

        return (
            f"Tool call '{tool_name}' was blocked by directory sandbox policy. "
            f"The path '{target_path}' is not within allowed directories. "
            f"Reason: {reason}. "
            f"Allowed directories: [{dirs_str}]. "
            f"Please use paths within the allowed directories."
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization/logging."""
        return {
            "spec_id": self.spec_id,
            "pattern_count": len(self.forbidden_patterns),
            "patterns": [p.original for p in self.forbidden_patterns],
            "allowed_tools": self.allowed_tools,
            "allowed_directories": [str(d) for d in self.allowed_directories],
            "base_dir": self.base_dir,
            "strict_mode": self.strict_mode,
        }


# =============================================================================
# Integration with HarnessKernel
# =============================================================================

def record_directory_blocked_event(
    db: "Session",
    run_id: str,
    sequence: int,
    tool_name: str,
    arguments: dict[str, Any],
    target_path: str,
    reason: str,
    allowed_directories: list[str],
) -> "AgentEvent":
    """
    Record a tool_call event for directory access violation.

    Feature #42, Step 8: Record violation in event log.

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        tool_name: Name of the blocked tool
        arguments: Original tool arguments
        target_path: The path that was blocked
        reason: Reason for blocking
        allowed_directories: List of allowed directory paths

    Returns:
        The created AgentEvent
    """
    from api.agentspec_models import AgentEvent

    # Prepare payload with blocked status and directory details
    payload = {
        "tool": tool_name,
        "args": arguments,
        "blocked": True,
        "block_type": "directory_sandbox",
        "target_path": target_path,
        "reason": reason,
        "allowed_directories": allowed_directories,
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
        "Recorded directory-blocked tool_call event: run=%s, tool=%s, path=%s, reason=%s",
        run_id, tool_name, target_path, reason
    )

    return event


def create_enforcer_for_run(
    spec: "AgentSpec",
    *,
    strict: bool = False,
    base_dir: str | None = None,
) -> ToolPolicyEnforcer:
    """
    Create a ToolPolicyEnforcer for a kernel execution run.

    This is the main entry point for HarnessKernel integration.
    Feature #42: Now includes directory sandbox configuration.

    Args:
        spec: The AgentSpec being executed
        strict: If True, fail on pattern compilation errors
        base_dir: Base directory for resolving relative paths in allowed_directories

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
        except DirectoryAccessBlocked as e:
            record_directory_blocked_event(db, run_id, seq, ...)
            return e.message
    """
    return ToolPolicyEnforcer.from_spec(spec, strict=strict, base_dir=base_dir)


# =============================================================================
# Tool Policy Derivation from Task Type (Feature #57)
# =============================================================================

# Tool sets by task type - defines what tools are available for each agent type
TOOL_SETS: dict[str, list[str]] = {
    # coding: file edit, bash (restricted), feature tools
    "coding": [
        # Feature management tools
        "feature_get_by_id",
        "feature_mark_in_progress",
        "feature_mark_passing",
        "feature_mark_failing",
        "feature_skip",
        "feature_clear_in_progress",
        "feature_get_stats",
        # Code editing tools
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        # Browser automation for testing
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_console_messages",
        "browser_network_requests",
        # Execution (restricted by security.py)
        "Bash",
        # Web research
        "WebFetch",
        "WebSearch",
    ],
    # testing: file read, bash (test commands), feature tools
    "testing": [
        # Feature management tools
        "feature_get_by_id",
        "feature_mark_passing",
        "feature_mark_failing",
        "feature_get_stats",
        # Read-only code access
        "Read",
        "Glob",
        "Grep",
        # Browser automation for testing
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_console_messages",
        "browser_network_requests",
        "browser_evaluate",
        # Execution for running tests (restricted)
        "Bash",
    ],
    # refactoring: file edit, bash (restricted), analysis tools
    "refactoring": [
        # Code editing tools
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        # Execution for linting, testing
        "Bash",
        # Feature management (read-only status updates)
        "feature_get_by_id",
        "feature_get_stats",
    ],
    # documentation: file write, read-only code access
    "documentation": [
        # File operations for documentation
        "Read",
        "Write",
        "Glob",
        "Grep",
        # Feature management (read-only)
        "feature_get_by_id",
        "feature_get_stats",
        # Web research for documentation
        "WebFetch",
        "WebSearch",
    ],
    # audit: read-only everything - no modifications allowed
    "audit": [
        # Read-only file access
        "Read",
        "Glob",
        "Grep",
        # Feature management (read-only)
        "feature_get_by_id",
        "feature_get_stats",
        "feature_get_ready",
        "feature_get_blocked",
        "feature_get_graph",
        # Browser for inspection only
        "browser_navigate",
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_console_messages",
        "browser_network_requests",
    ],
    # custom: minimal default set
    "custom": [
        "Read",
        "Glob",
        "Grep",
        "feature_get_by_id",
        "feature_get_stats",
    ],
}

# Standard forbidden patterns applied to ALL task types for baseline security
STANDARD_FORBIDDEN_PATTERNS: list[str] = [
    r"rm\s+-rf\s+/",                    # Dangerous recursive delete from root
    r"rm\s+--recursive\s+--force\s+/",  # Verbose form of rm -rf /
    r"DROP\s+TABLE",                    # SQL injection - drop table
    r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1", # Mass delete SQL injection
    r"TRUNCATE\s+TABLE",                # SQL injection - truncate
    r"chmod\s+777",                     # Overly permissive file permissions
    r">(>)?.*\/etc\/",                  # Writing to system directories
    r"curl.*\|\s*sh",                   # Pipe curl to shell (dangerous)
    r"wget.*\|\s*sh",                   # Pipe wget to shell (dangerous)
    r"eval\s*\(.*\$",                   # Shell eval with variable (injection risk)
    r"sudo\s+",                         # Privilege escalation
    r":\(\)\{:\|:&\};:",                # Fork bomb
    r"mkfs\.",                          # Filesystem formatting
    r"dd\s+if=.*of=/dev/",              # Direct disk write
]

# Task-specific forbidden patterns - additional restrictions per task type
TASK_SPECIFIC_FORBIDDEN_PATTERNS: dict[str, list[str]] = {
    "coding": [
        # Coding agents shouldn't delete databases or critical files
        r"DROP\s+DATABASE",
        r"rm\s+.*\.db$",       # Don't delete database files
        r"rm\s+.*\.sqlite$",   # Don't delete SQLite files
    ],
    "testing": [
        # Testing agents should be read-only - no destructive operations
        r"Write\s+",            # Block Write tool calls in testing
        r"Edit\s+",             # Block Edit tool calls in testing
        r"rm\s+",               # Block all remove commands
        r"mv\s+",               # Block move commands (could overwrite)
        r"cp\s+",               # Block copy (could fill disk)
        r"git\s+push",          # Don't push during testing
        r"git\s+commit",        # Don't commit during testing
        r"npm\s+publish",       # Don't publish during testing
    ],
    "refactoring": [
        # Refactoring should not change feature status
        r"feature_mark_passing",
        r"feature_mark_failing",
    ],
    "documentation": [
        # Documentation agents shouldn't modify code
        r"Edit\s+.*\.(py|js|ts|tsx|jsx|java|go|rs|c|cpp|h)$",
        r"git\s+push",          # Don't push
        r"npm\s+publish",       # Don't publish
    ],
    "audit": [
        # Audit agents are strictly read-only - block all modifications
        r"Write\s+",
        r"Edit\s+",
        r"Bash\s+",             # No bash execution
        r"rm\s+",
        r"mv\s+",
        r"cp\s+",
        r"git\s+(commit|push|merge|rebase)",
        r"npm\s+(install|publish|run)",
        r"pip\s+install",
        r"feature_mark_",      # No status changes
        r"feature_skip",
        r"feature_create",
    ],
    "custom": [],  # No additional restrictions for custom
}

# Tool hints by task type - guidance for using tools appropriately
TASK_TOOL_HINTS: dict[str, dict[str, str]] = {
    "coding": {
        "feature_mark_passing": (
            "ONLY call after thorough verification with browser automation. "
            "Take screenshots to prove the feature works."
        ),
        "Edit": (
            "Prefer editing existing files over creating new ones. "
            "Always read files before editing."
        ),
        "Bash": (
            "Bash commands are restricted by security allowlist. "
            "Only development commands (npm, git, pytest) are permitted."
        ),
    },
    "testing": {
        "feature_mark_failing": (
            "Use this to report regressions found during testing."
        ),
        "browser_snapshot": (
            "Capture page state before and after interactions to verify behavior."
        ),
        "Bash": (
            "Use for running test commands only. Do not modify code."
        ),
    },
    "refactoring": {
        "Edit": (
            "Make incremental changes. Run tests after each refactoring step."
        ),
        "Bash": (
            "Run linters and tests to verify refactoring doesn't break code."
        ),
    },
    "documentation": {
        "Write": (
            "Create documentation files (.md, .rst, .txt). "
            "Do not modify source code files."
        ),
        "WebFetch": (
            "Use to research API documentation and best practices."
        ),
    },
    "audit": {
        "Read": (
            "Review code for security issues, bugs, and best practices."
        ),
        "browser_snapshot": (
            "Capture application state for audit reports."
        ),
    },
    "custom": {},
}


def derive_tool_policy(
    task_type: str,
    *,
    allowed_directories: list[str] | None = None,
    additional_tools: list[str] | None = None,
    additional_forbidden_patterns: list[str] | None = None,
    additional_tool_hints: dict[str, str] | None = None,
    policy_version: str = "v1",
) -> dict[str, Any]:
    """
    Derive appropriate tool_policy based on task_type.

    Feature #57: Tool Policy Derivation from Task Type

    This function generates a complete tool_policy structure with:
    - Allowed tools appropriate for the task type
    - Standard forbidden patterns (security baseline)
    - Task-specific forbidden patterns
    - Tool hints for proper usage

    Args:
        task_type: The task type (coding, testing, refactoring, documentation, audit, custom)
        allowed_directories: Optional list of directories the agent can access
        additional_tools: Additional tools to add to the default set
        additional_forbidden_patterns: Additional patterns to block
        additional_tool_hints: Additional hints to add
        policy_version: Version string for forward compatibility

    Returns:
        Complete tool_policy dictionary ready for AgentSpec.tool_policy

    Raises:
        ValueError: If task_type is not recognized

    Example:
        >>> policy = derive_tool_policy("coding")
        >>> policy["allowed_tools"]  # Contains coding-specific tools
        ['feature_get_by_id', 'Read', 'Write', 'Edit', ...]
        >>> "rm -rf /" in str(policy["forbidden_patterns"])  # Blocked
        True

        >>> policy = derive_tool_policy("audit")
        >>> "Bash" in policy["allowed_tools"]  # Audit has no Bash
        False
    """
    # Normalize task type
    task_type_lower = task_type.lower().strip() if task_type else "custom"

    # Validate task type - fall back to custom if unknown
    if task_type_lower not in TOOL_SETS:
        _logger.warning(
            "Unknown task_type '%s', falling back to 'custom'",
            task_type
        )
        task_type_lower = "custom"

    # Get allowed tools for this task type
    allowed_tools = list(TOOL_SETS[task_type_lower])

    # Add additional tools if provided
    if additional_tools:
        for tool in additional_tools:
            if tool not in allowed_tools:
                allowed_tools.append(tool)

    # Build forbidden patterns: standard + task-specific + additional
    forbidden_patterns = list(STANDARD_FORBIDDEN_PATTERNS)

    # Add task-specific patterns
    task_patterns = TASK_SPECIFIC_FORBIDDEN_PATTERNS.get(task_type_lower, [])
    forbidden_patterns.extend(task_patterns)

    # Add additional patterns if provided
    if additional_forbidden_patterns:
        forbidden_patterns.extend(additional_forbidden_patterns)

    # Remove duplicates while preserving order
    seen_patterns: set[str] = set()
    unique_patterns: list[str] = []
    for pattern in forbidden_patterns:
        if pattern not in seen_patterns:
            seen_patterns.add(pattern)
            unique_patterns.append(pattern)
    forbidden_patterns = unique_patterns

    # Get tool hints for this task type
    tool_hints = dict(TASK_TOOL_HINTS.get(task_type_lower, {}))

    # Add additional hints if provided
    if additional_tool_hints:
        tool_hints.update(additional_tool_hints)

    # Build the complete tool_policy structure
    tool_policy: dict[str, Any] = {
        "policy_version": policy_version,
        "allowed_tools": allowed_tools,
        "forbidden_patterns": forbidden_patterns,
        "tool_hints": tool_hints,
        "task_type": task_type_lower,  # Include task type for reference
    }

    # Add allowed_directories if specified
    if allowed_directories:
        tool_policy["allowed_directories"] = allowed_directories

    _logger.debug(
        "Derived tool_policy for task_type '%s': %d tools, %d patterns, %d hints",
        task_type_lower,
        len(allowed_tools),
        len(forbidden_patterns),
        len(tool_hints),
    )

    return tool_policy


def get_tool_set(task_type: str) -> list[str]:
    """
    Get the allowed tool set for a task type.

    Args:
        task_type: The task type

    Returns:
        List of allowed tool names (copy, not reference)

    Example:
        >>> tools = get_tool_set("testing")
        >>> "Read" in tools
        True
        >>> "Write" in tools  # Testing doesn't allow Write
        False
    """
    task_type_lower = task_type.lower().strip() if task_type else "custom"

    if task_type_lower not in TOOL_SETS:
        task_type_lower = "custom"

    return list(TOOL_SETS[task_type_lower])


def get_standard_forbidden_patterns() -> list[str]:
    """
    Get the standard forbidden patterns applied to all task types.

    Returns:
        List of pattern strings (copy, not reference)
    """
    return list(STANDARD_FORBIDDEN_PATTERNS)


def get_task_forbidden_patterns(task_type: str) -> list[str]:
    """
    Get task-specific forbidden patterns for a task type.

    Args:
        task_type: The task type

    Returns:
        List of pattern strings (copy, not reference)
    """
    task_type_lower = task_type.lower().strip() if task_type else "custom"
    return list(TASK_SPECIFIC_FORBIDDEN_PATTERNS.get(task_type_lower, []))


def get_combined_forbidden_patterns(task_type: str) -> list[str]:
    """
    Get all forbidden patterns for a task type (standard + task-specific).

    Args:
        task_type: The task type

    Returns:
        Combined list of pattern strings
    """
    patterns = get_standard_forbidden_patterns()
    patterns.extend(get_task_forbidden_patterns(task_type))
    return patterns


def get_tool_hints(task_type: str) -> dict[str, str]:
    """
    Get tool hints for a task type.

    Args:
        task_type: The task type

    Returns:
        Dictionary of tool_name -> hint string (copy, not reference)
    """
    task_type_lower = task_type.lower().strip() if task_type else "custom"
    return dict(TASK_TOOL_HINTS.get(task_type_lower, {}))


def get_supported_task_types() -> list[str]:
    """
    Get list of all supported task types.

    Returns:
        List of supported task type strings
    """
    return list(TOOL_SETS.keys())
