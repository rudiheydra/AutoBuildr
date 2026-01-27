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


@dataclass
class PathTraversalResult:
    """
    Result of path traversal attack detection.

    Feature #48: Path Traversal Attack Detection

    Provides detailed information about the detection for security audit logging.
    """

    detected: bool  # True if attack detected
    attack_type: str | None = None  # Type of attack (e.g., "dotdot", "url_encoded", "null_byte")
    matched_pattern: str | None = None  # The specific pattern that matched
    original_path: str = ""  # Original path string
    normalized_path: str | None = None  # Normalized path (if computed)
    details: dict[str, Any] = field(default_factory=dict)  # Additional audit info

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.detected


def contains_null_byte(path_str: str) -> tuple[bool, int | None]:
    """
    Check if a path contains null bytes that could truncate paths.

    Feature #48, Step 3: Check for null bytes that could truncate paths

    Null bytes (\\x00) can be used to truncate file paths in some systems,
    potentially bypassing security checks.

    Args:
        path_str: Path string to check

    Returns:
        Tuple of (contains_null: bool, position: int | None)

    Example:
        >>> contains_null_byte("/etc/passwd\\x00.txt")
        (True, 11)
        >>> contains_null_byte("/etc/passwd")
        (False, None)
    """
    try:
        position = path_str.index('\x00')
        return True, position
    except ValueError:
        pass

    # Also check for URL-encoded null bytes
    path_lower = path_str.lower()
    null_byte_patterns = [
        "%00",  # URL-encoded null
        "%2500",  # Double URL-encoded null
        "\\0",  # Backslash-escaped null
        "\\x00",  # Hex-escaped null (literal string, not actual byte)
    ]

    for pattern in null_byte_patterns:
        if pattern in path_lower:
            return True, path_lower.index(pattern)

    return False, None


def normalize_path_for_comparison(path_str: str) -> str:
    """
    Normalize a path for comparison to detect traversal attempts.

    Feature #48, Step 4: Normalize path and compare to original

    This function normalizes the path without resolving symlinks,
    so we can compare it to the original to detect traversal attempts.

    Args:
        path_str: Path string to normalize

    Returns:
        Normalized path string

    Example:
        >>> normalize_path_for_comparison("/home/user/../root/secret")
        '/root/secret'
        >>> normalize_path_for_comparison("/home/user/./file.txt")
        '/home/user/file.txt'
    """
    # Use os.path.normpath for consistent normalization
    # This removes redundant separators and collapses .. sequences
    return os.path.normpath(path_str)


def path_differs_after_normalization(path_str: str) -> tuple[bool, str]:
    """
    Check if path normalization changes the path structure.

    Feature #48, Step 5: Block if normalized differs (indicates traversal attempt)

    A difference after normalization can indicate:
    - Path traversal via ..
    - Current directory references via .
    - Redundant separators that might bypass filters

    Args:
        path_str: Path string to check

    Returns:
        Tuple of (differs: bool, normalized: str)

    Example:
        >>> path_differs_after_normalization("/home/user/../root")
        (True, '/home/root')
        >>> path_differs_after_normalization("/home/user/file.txt")
        (False, '/home/user/file.txt')
    """
    normalized = normalize_path_for_comparison(path_str)

    # Compare ignoring trailing slashes
    original_clean = path_str.rstrip("/\\")
    normalized_clean = normalized.rstrip("/\\")

    differs = original_clean != normalized_clean
    return differs, normalized


def detect_path_traversal_attack(path_str: str) -> PathTraversalResult:
    """
    Comprehensive path traversal attack detection.

    Feature #48: Path Traversal Attack Detection

    This function implements all 6 verification steps:
    1. Check for .. sequences in raw path string
    2. Check for URL-encoded traversal %2e%2e
    3. Check for null bytes that could truncate paths
    4. Normalize path and compare to original
    5. Block if normalized differs (indicates traversal attempt)
    6. Log detailed violation info for security audit

    Args:
        path_str: Path string to check for attack patterns

    Returns:
        PathTraversalResult with detection details for security audit

    Example:
        >>> result = detect_path_traversal_attack("/home/user/../root/secret")
        >>> result.detected
        True
        >>> result.attack_type
        'dotdot_traversal'

        >>> result = detect_path_traversal_attack("/etc/passwd%00.txt")
        >>> result.detected
        True
        >>> result.attack_type
        'null_byte'
    """
    result = PathTraversalResult(
        detected=False,
        original_path=path_str,
        details={
            "checks_performed": [],
            "timestamp": _utc_now().isoformat(),
        },
    )

    # Step 1: Check for .. sequences in raw path string
    result.details["checks_performed"].append("dotdot_sequence")
    path = Path(path_str)
    for part in path.parts:
        if part == "..":
            result.detected = True
            result.attack_type = "dotdot_traversal"
            result.matched_pattern = ".."
            result.details["component"] = part
            _logger.warning(
                "Feature #48: Path traversal detected (dotdot): %s",
                path_str
            )
            return result

    # Step 2: Check for URL-encoded traversal patterns (%2e%2e)
    result.details["checks_performed"].append("url_encoded_traversal")
    path_lower = path_str.lower()

    # Comprehensive list of URL-encoded traversal patterns
    encoded_traversal_patterns = {
        # Standard URL encoding
        "%2e%2e/": "url_encoded_dotdot_slash",
        "/%2e%2e": "url_encoded_slash_dotdot",
        "%2e%2e%2f": "url_encoded_dotdot_and_slash",
        "%2e%2e%5c": "url_encoded_dotdot_and_backslash",
        # Double URL encoding
        "%252e%252e/": "double_encoded_dotdot_slash",
        "/%252e%252e": "double_encoded_slash_dotdot",
        "%252e%252e%252f": "double_encoded_dotdot_and_slash",
        # Unicode overlong encoding (IIS vulnerabilities)
        "..%c0%af": "unicode_overlong_slash",
        "..%c1%9c": "unicode_overlong_backslash_variant",
        "..%c0%2f": "unicode_overlong_slash_variant",
        "..%c1%1c": "unicode_overlong_another_variant",
        # Mixed encoding
        "..%2f": "dotdot_encoded_slash",
        "..%5c": "dotdot_encoded_backslash",
        "%2e./": "partial_encoded_traversal",
        ".%2e/": "partial_encoded_traversal_2",
        # Triple encoding (rare but possible)
        "%25252e%25252e": "triple_encoded_dotdot",
    }

    for pattern, attack_name in encoded_traversal_patterns.items():
        if pattern in path_lower:
            result.detected = True
            result.attack_type = "url_encoded_traversal"
            result.matched_pattern = pattern
            result.details["encoding_type"] = attack_name
            _logger.warning(
                "Feature #48: URL-encoded path traversal detected: %s (pattern: %s)",
                path_str, pattern
            )
            return result

    # Step 3: Check for null bytes that could truncate paths
    result.details["checks_performed"].append("null_byte")
    has_null, null_position = contains_null_byte(path_str)
    if has_null:
        result.detected = True
        result.attack_type = "null_byte"
        result.matched_pattern = "\\x00"
        result.details["null_position"] = null_position
        # Extract what would be the "effective" path after truncation
        if null_position is not None:
            result.details["effective_path"] = path_str[:null_position]
        _logger.warning(
            "Feature #48: Null byte path truncation detected at position %s: %s",
            null_position, repr(path_str)
        )
        return result

    # Step 4 & 5: Normalize path and compare to original
    result.details["checks_performed"].append("normalization_comparison")
    differs, normalized = path_differs_after_normalization(path_str)
    result.normalized_path = normalized

    if differs:
        # Check if the difference is due to traversal (not just ./current dir)
        # Only flag as attack if the normalized path is "higher" in the tree
        # or if the original contained .. sequences that got collapsed
        original_parts = Path(path_str).parts
        normalized_parts = Path(normalized).parts

        # Detect if normalization collapsed a .. (attack) vs just removed ./
        contains_dotdot_like = (
            ".." in path_str or
            "%2e%2e" in path_lower or
            # Check if it looks like a traversal attempt that got normalized away
            len(normalized_parts) < len(original_parts)
        )

        if contains_dotdot_like:
            result.detected = True
            result.attack_type = "normalized_traversal"
            result.matched_pattern = f"normalization_diff"
            result.details["original"] = path_str
            result.details["normalized"] = normalized
            result.details["original_parts"] = list(original_parts)
            result.details["normalized_parts"] = list(normalized_parts)
            _logger.warning(
                "Feature #48: Path traversal detected via normalization: '%s' -> '%s'",
                path_str, normalized
            )
            return result

    # Check for boundary cases
    result.details["checks_performed"].append("boundary_cases")
    if path_str.startswith("..") and len(path_str) > 2 and path_str[2] in "/\\":
        result.detected = True
        result.attack_type = "dotdot_traversal"
        result.matched_pattern = "../ (start)"
        _logger.warning(
            "Feature #48: Path traversal detected (start with ../): %s",
            path_str
        )
        return result

    if path_str.endswith("/..") or path_str.endswith("\\.."):
        result.detected = True
        result.attack_type = "dotdot_traversal"
        result.matched_pattern = ".. (end)"
        _logger.warning(
            "Feature #48: Path traversal detected (ends with /..): %s",
            path_str
        )
        return result

    # No attack detected
    result.details["result"] = "clean"
    return result


def contains_path_traversal(path_str: str) -> bool:
    """
    Check if a path string contains path traversal attempts.

    Feature #42, Step 6: Block path traversal attempts (..)
    Feature #48: Path Traversal Attack Detection (enhanced)

    This is a convenience wrapper around detect_path_traversal_attack()
    that returns a simple boolean for backward compatibility.

    For detailed security audit information, use detect_path_traversal_attack()
    directly.

    Args:
        path_str: Path string to check

    Returns:
        True if path contains traversal attack patterns, False otherwise

    Example:
        >>> contains_path_traversal("/home/user/../root/secret")
        True
        >>> contains_path_traversal("/home/user/project/file.txt")
        False
        >>> contains_path_traversal("/home/user/file..txt")  # Not a traversal
        False
        >>> contains_path_traversal("/etc/passwd%00.txt")  # Null byte attack
        True
    """
    result = detect_path_traversal_attack(path_str)
    return result.detected


class BrokenSymlinkError(ToolPolicyError):
    """
    Raised when a symlink target cannot be resolved.

    Feature #46: Symlink Target Validation
    Handles broken symlinks gracefully.
    """

    def __init__(
        self,
        symlink_path: str,
        target_path: str | None = None,
        message: str | None = None,
    ):
        self.symlink_path = symlink_path
        self.target_path = target_path

        if message is None:
            if target_path:
                message = (
                    f"Broken symlink: '{symlink_path}' -> '{target_path}' "
                    f"(target does not exist)"
                )
            else:
                message = f"Broken symlink: '{symlink_path}' (cannot read target)"

        super().__init__(message)


def is_broken_symlink(path: Path) -> bool:
    """
    Check if a path is a broken symlink.

    Feature #46, Step 4: Handle broken symlinks gracefully

    A broken symlink is a symlink whose target does not exist.

    Args:
        path: Path to check

    Returns:
        True if path is a symlink that points to a non-existent target

    Example:
        >>> is_broken_symlink(Path("/path/to/broken_link"))
        True
        >>> is_broken_symlink(Path("/path/to/working_link"))
        False
    """
    try:
        # is_symlink() returns True if path is a symlink (regardless of target)
        if not path.is_symlink():
            return False

        # exists() follows symlinks, so it returns False for broken symlinks
        # For a symlink, exists() checks if the TARGET exists
        return not path.exists()

    except OSError as e:
        _logger.debug(
            "OSError checking symlink status for %s: %s",
            path, e
        )
        return False


def get_symlink_target(path: Path) -> str | None:
    """
    Get the target of a symlink without resolving the full chain.

    Feature #46, Step 5: Log symlink resolution in debug output

    Args:
        path: Symlink path

    Returns:
        The immediate target path as string, or None if not a symlink or error

    Example:
        >>> get_symlink_target(Path("/path/to/link"))
        '../target/file.txt'
    """
    try:
        if path.is_symlink():
            return str(path.readlink())
    except OSError as e:
        _logger.debug(
            "Failed to read symlink target for %s: %s",
            path, e
        )
    return None


def resolve_target_path(
    path_str: str,
    base_dir: str | None = None,
    *,
    follow_symlinks: bool = True,
) -> tuple[Path, bool, bool]:
    """
    Resolve a target path to absolute form, optionally following symlinks.

    Feature #42, Steps 4 & 7:
    - Step 4: Resolve target path to absolute
    - Step 7: If target is symlink, resolve and validate final target

    Feature #46: Symlink Target Validation
    - Step 1: Check if path is symlink using Path.is_symlink()
    - Step 2: Resolve symlink to final target using Path.resolve()
    - Step 4: Handle broken symlinks gracefully
    - Step 5: Log symlink resolution in debug output

    Args:
        path_str: Target path string
        base_dir: Base directory for relative paths
        follow_symlinks: Whether to resolve symlinks to their targets

    Returns:
        Tuple of (resolved_path, was_symlink, is_broken)
        - resolved_path: The resolved absolute path
        - was_symlink: True if original path was a symlink
        - is_broken: True if symlink is broken (target doesn't exist)

    Raises:
        BrokenSymlinkError: When follow_symlinks=True and symlink is broken

    Example:
        >>> resolve_target_path("./file.txt", "/home/user")
        (PosixPath('/home/user/file.txt'), False, False)
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    target = Path(path_str)

    # Make absolute if relative
    if not target.is_absolute():
        target = base / target

    was_symlink = False
    is_broken = False

    if follow_symlinks:
        # Feature #46, Step 1: Check if path is symlink using Path.is_symlink()
        try:
            was_symlink = target.is_symlink()
        except OSError as e:
            _logger.debug(
                "OSError checking is_symlink for %s: %s",
                target, e
            )

        if was_symlink:
            # Feature #46, Step 5: Log symlink resolution in debug output
            symlink_target = get_symlink_target(target)
            _logger.debug(
                "Feature #46: Path is symlink: %s -> %s",
                target, symlink_target or "(unknown)"
            )

            # Feature #46, Step 4: Handle broken symlinks gracefully
            is_broken = is_broken_symlink(target)
            if is_broken:
                _logger.debug(
                    "Feature #46: Broken symlink detected: %s -> %s (target does not exist)",
                    target, symlink_target or "(unknown)"
                )
                # We don't raise here - let caller decide how to handle
                # resolve() on a broken symlink will still return a path

        # Feature #46, Step 2: Resolve symlink to final target using Path.resolve()
        # resolve() normalizes the path AND follows symlinks
        try:
            resolved = target.resolve()
        except RuntimeError as e:
            # Handle symlink loops (circular references like link -> link)
            # Python raises RuntimeError("Symlink loop from ...") for these
            if "symlink loop" in str(e).lower():
                _logger.debug(
                    "Feature #46: Symlink loop detected: %s -> %s (treating as broken)",
                    target, str(e)
                )
                is_broken = True
                # Return the original target path (normalized but not resolved)
                resolved = Path(os.path.normpath(target.absolute()))
            else:
                raise

        if was_symlink:
            _logger.debug(
                "Feature #46: Symlink resolved: %s -> %s (was_symlink=%s, is_broken=%s)",
                path_str, resolved, was_symlink, is_broken
            )
    else:
        # Just normalize without following symlinks
        # Use absolute() + normpath pattern
        resolved = Path(os.path.normpath(target.absolute()))

    return resolved, was_symlink, is_broken


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
    *,
    allow_broken_symlinks: bool = False,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    Validate that a file operation target is within allowed directories.

    Feature #42: Combined validation including all security checks.
    Feature #46: Symlink Target Validation

    This function performs:
    1. Path traversal detection
    2. Path resolution to absolute
    3. Symlink resolution and validation (Feature #46)
    4. Broken symlink detection (Feature #46)
    5. Directory containment check

    Args:
        tool_name: Name of the tool making the access
        target_path_str: Target path string from tool arguments
        allowed_directories: List of resolved allowed directory paths
        base_dir: Base directory for resolving relative paths
        allow_broken_symlinks: If False (default), broken symlinks are blocked.
            If True, broken symlinks are allowed but logged.

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

    # Feature #48: Enhanced path traversal attack detection with security audit logging
    # Step 6: Log detailed violation info for security audit
    traversal_result = detect_path_traversal_attack(target_path_str)
    if traversal_result.detected:
        # Feature #48, Step 6: Include detailed security audit information
        details["traversal_detected"] = True
        details["attack_type"] = traversal_result.attack_type
        details["matched_pattern"] = traversal_result.matched_pattern
        details["normalized_path"] = traversal_result.normalized_path
        details["security_audit"] = traversal_result.details

        # Construct detailed reason message for logging
        reason_parts = ["Path contains security risk"]
        if traversal_result.attack_type == "dotdot_traversal":
            reason_parts.append("directory traversal (..) detected")
        elif traversal_result.attack_type == "url_encoded_traversal":
            reason_parts.append(f"URL-encoded traversal ({traversal_result.matched_pattern}) detected")
        elif traversal_result.attack_type == "null_byte":
            reason_parts.append("null byte path truncation detected")
        elif traversal_result.attack_type == "normalized_traversal":
            reason_parts.append("path normalization reveals traversal attempt")

        _logger.warning(
            "Feature #48: Security audit - Path traversal attack blocked. "
            "Tool: %s, Path: %s, Attack Type: %s, Pattern: %s, Details: %s",
            tool_name,
            target_path_str,
            traversal_result.attack_type,
            traversal_result.matched_pattern,
            traversal_result.details,
        )

        return (
            False,
            ": ".join(reason_parts),
            details,
        )

    # Steps 4 & 7: Resolve to absolute and handle symlinks
    # Feature #46: Symlink Target Validation - all 5 steps
    try:
        # Feature #46, Steps 1-2: Check symlink and resolve to final target
        resolved_path, was_symlink, is_broken = resolve_target_path(
            target_path_str,
            base_dir=base_dir,
            follow_symlinks=True,  # Step 7: resolve symlinks
        )
        details["resolved_path"] = str(resolved_path)
        details["was_symlink"] = was_symlink
        details["is_broken_symlink"] = is_broken

        # Feature #46, Step 5: Log symlink resolution in debug output
        if was_symlink:
            _logger.debug(
                "Feature #46: Symlink detected and resolved: %s -> %s "
                "(is_broken=%s)",
                target_path_str, resolved_path, is_broken
            )

        # Feature #46, Step 4: Handle broken symlinks gracefully
        if is_broken:
            _logger.warning(
                "Feature #46: Broken symlink detected: %s "
                "(resolved to non-existent target: %s)",
                target_path_str, resolved_path
            )
            if not allow_broken_symlinks:
                details["broken_symlink_blocked"] = True
                return (
                    False,
                    f"Broken symlink: '{target_path_str}' points to non-existent target",
                    details,
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


# =============================================================================
# Budget Derivation (Feature #58: Budget Derivation from Task Complexity)
# =============================================================================

# Base budgets per task_type (as specified in Feature #58)
BASE_BUDGETS: dict[str, dict[str, int]] = {
    "coding": {
        "max_turns": 50,
        "timeout_seconds": 1800,  # 30 minutes
    },
    "testing": {
        "max_turns": 30,
        "timeout_seconds": 600,  # 10 minutes
    },
    "documentation": {
        "max_turns": 25,
        "timeout_seconds": 900,  # 15 minutes
    },
    "refactoring": {
        "max_turns": 40,
        "timeout_seconds": 1200,  # 20 minutes
    },
    "audit": {
        "max_turns": 20,
        "timeout_seconds": 600,  # 10 minutes
    },
    "custom": {
        "max_turns": 30,
        "timeout_seconds": 900,  # 15 minutes (default)
    },
}

# Minimum bounds for budgets (safety floor)
MIN_BUDGET: dict[str, int] = {
    "max_turns": 5,  # At least 5 turns for any task
    "timeout_seconds": 60,  # At least 1 minute
}

# Maximum bounds for budgets (safety ceiling)
MAX_BUDGET: dict[str, int] = {
    "max_turns": 200,  # No task should need more than 200 turns
    "timeout_seconds": 7200,  # 2 hours maximum
}

# Adjustment factors
DESCRIPTION_LENGTH_THRESHOLDS: list[tuple[int, float]] = [
    # (character_threshold, multiplier)
    # Longer descriptions typically indicate more complex tasks
    (500, 1.0),    # Short: base budget
    (1000, 1.2),   # Medium: 20% increase
    (2000, 1.4),   # Long: 40% increase
    (5000, 1.6),   # Very long: 60% increase
]

STEPS_COUNT_THRESHOLDS: list[tuple[int, float]] = [
    # (step_count_threshold, multiplier)
    # More steps typically require more turns
    (3, 1.0),      # Simple: base budget
    (5, 1.15),     # Medium: 15% increase
    (10, 1.3),     # Complex: 30% increase
    (20, 1.5),     # Very complex: 50% increase
]


@dataclass
class BudgetResult:
    """
    Result of budget derivation calculation.

    Contains the derived budget values and metadata about the derivation.
    """
    max_turns: int
    timeout_seconds: int
    task_type: str
    base_max_turns: int
    base_timeout_seconds: int
    description_multiplier: float
    steps_multiplier: float
    description_length: int
    steps_count: int
    adjustments_applied: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization or API response."""
        return {
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
            "task_type": self.task_type,
            "base_max_turns": self.base_max_turns,
            "base_timeout_seconds": self.base_timeout_seconds,
            "description_multiplier": self.description_multiplier,
            "steps_multiplier": self.steps_multiplier,
            "description_length": self.description_length,
            "steps_count": self.steps_count,
            "adjustments_applied": self.adjustments_applied,
        }


def _get_description_multiplier(description_length: int) -> float:
    """
    Calculate the multiplier based on description length.

    Args:
        description_length: Number of characters in the description

    Returns:
        Multiplier value (>= 1.0)
    """
    multiplier = 1.0
    for threshold, mult in DESCRIPTION_LENGTH_THRESHOLDS:
        if description_length >= threshold:
            multiplier = mult
        else:
            break
    return multiplier


def _get_steps_multiplier(steps_count: int) -> float:
    """
    Calculate the multiplier based on number of acceptance steps.

    Args:
        steps_count: Number of acceptance/verification steps

    Returns:
        Multiplier value (>= 1.0)
    """
    multiplier = 1.0
    for threshold, mult in STEPS_COUNT_THRESHOLDS:
        if steps_count >= threshold:
            multiplier = mult
        else:
            break
    return multiplier


def _apply_bounds(value: int, min_val: int, max_val: int) -> int:
    """
    Apply minimum and maximum bounds to a value.

    Args:
        value: The value to bound
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Bounded value
    """
    return max(min_val, min(value, max_val))


def derive_budget(
    task_type: str,
    *,
    description: str | None = None,
    steps: list[str] | None = None,
    description_length: int | None = None,
    steps_count: int | None = None,
) -> dict[str, int]:
    """
    Derive appropriate max_turns and timeout_seconds based on task complexity.

    Feature #58: Budget Derivation from Task Complexity

    This function calculates execution budgets based on:
    1. Base budgets per task_type
    2. Adjustment for description length (longer = more complex)
    3. Adjustment for number of acceptance steps
    4. Minimum and maximum bounds for safety

    Args:
        task_type: The task type (coding, testing, refactoring, documentation, audit, custom)
        description: Optional task description (used to calculate length)
        steps: Optional list of acceptance/verification steps
        description_length: Optional explicit description length (overrides description)
        steps_count: Optional explicit step count (overrides steps)

    Returns:
        Dictionary with 'max_turns' and 'timeout_seconds' keys

    Example:
        >>> budget = derive_budget("coding")
        >>> budget["max_turns"]
        50
        >>> budget["timeout_seconds"]
        1800

        >>> budget = derive_budget("coding", description="A" * 2000, steps=["Step 1"] * 10)
        >>> budget["max_turns"] > 50  # Increased due to complexity
        True

        >>> budget = derive_budget("testing")
        >>> budget["max_turns"]
        30
        >>> budget["timeout_seconds"]
        600
    """
    # Normalize task type
    task_type_lower = task_type.lower().strip() if task_type else "custom"

    # Fall back to custom for unknown task types
    if task_type_lower not in BASE_BUDGETS:
        _logger.warning(
            "Unknown task_type '%s' for budget derivation, using 'custom'",
            task_type
        )
        task_type_lower = "custom"

    # Step 1: Get base budgets
    base = BASE_BUDGETS[task_type_lower]
    base_max_turns = base["max_turns"]
    base_timeout = base["timeout_seconds"]

    # Step 2: Calculate description length multiplier
    if description_length is not None:
        desc_len = description_length
    elif description is not None:
        desc_len = len(description)
    else:
        desc_len = 0

    desc_multiplier = _get_description_multiplier(desc_len)

    # Step 3: Calculate steps count multiplier
    if steps_count is not None:
        step_cnt = steps_count
    elif steps is not None:
        step_cnt = len(steps)
    else:
        step_cnt = 0

    steps_multiplier = _get_steps_multiplier(step_cnt)

    # Step 4: Apply multipliers (combined effect)
    # Use the average of multipliers to avoid exponential growth
    combined_multiplier = (desc_multiplier + steps_multiplier) / 2

    # If both are 1.0, combined should be 1.0
    if desc_multiplier == 1.0 and steps_multiplier == 1.0:
        combined_multiplier = 1.0

    adjusted_max_turns = int(base_max_turns * combined_multiplier)
    adjusted_timeout = int(base_timeout * combined_multiplier)

    # Step 5: Apply bounds
    final_max_turns = _apply_bounds(
        adjusted_max_turns,
        MIN_BUDGET["max_turns"],
        MAX_BUDGET["max_turns"]
    )
    final_timeout = _apply_bounds(
        adjusted_timeout,
        MIN_BUDGET["timeout_seconds"],
        MAX_BUDGET["timeout_seconds"]
    )

    _logger.debug(
        "Derived budget for task_type '%s': max_turns=%d (base=%d), timeout=%d (base=%d), "
        "desc_len=%d, steps=%d, desc_mult=%.2f, steps_mult=%.2f",
        task_type_lower,
        final_max_turns,
        base_max_turns,
        final_timeout,
        base_timeout,
        desc_len,
        step_cnt,
        desc_multiplier,
        steps_multiplier,
    )

    return {
        "max_turns": final_max_turns,
        "timeout_seconds": final_timeout,
    }


def derive_budget_detailed(
    task_type: str,
    *,
    description: str | None = None,
    steps: list[str] | None = None,
    description_length: int | None = None,
    steps_count: int | None = None,
) -> BudgetResult:
    """
    Derive budget with detailed derivation information.

    Similar to derive_budget but returns a BudgetResult with full metadata
    about how the budget was calculated. Useful for debugging and transparency.

    Args:
        task_type: The task type
        description: Optional task description
        steps: Optional list of acceptance steps
        description_length: Optional explicit description length
        steps_count: Optional explicit step count

    Returns:
        BudgetResult with budget values and derivation metadata

    Example:
        >>> result = derive_budget_detailed("coding", description="Complex task...")
        >>> result.max_turns
        50
        >>> result.description_multiplier
        1.0
        >>> result.adjustments_applied
        ['base_budget_coding']
    """
    # Normalize task type
    task_type_lower = task_type.lower().strip() if task_type else "custom"

    # Fall back to custom for unknown task types
    if task_type_lower not in BASE_BUDGETS:
        task_type_lower = "custom"

    # Get base budgets
    base = BASE_BUDGETS[task_type_lower]
    base_max_turns = base["max_turns"]
    base_timeout = base["timeout_seconds"]

    # Calculate description length
    if description_length is not None:
        desc_len = description_length
    elif description is not None:
        desc_len = len(description)
    else:
        desc_len = 0

    # Calculate steps count
    if steps_count is not None:
        step_cnt = steps_count
    elif steps is not None:
        step_cnt = len(steps)
    else:
        step_cnt = 0

    # Get multipliers
    desc_multiplier = _get_description_multiplier(desc_len)
    steps_multiplier = _get_steps_multiplier(step_cnt)

    # Track adjustments
    adjustments: list[str] = [f"base_budget_{task_type_lower}"]

    if desc_multiplier > 1.0:
        adjustments.append(f"description_length_adjustment_{desc_multiplier:.2f}x")
    if steps_multiplier > 1.0:
        adjustments.append(f"steps_count_adjustment_{steps_multiplier:.2f}x")

    # Calculate combined multiplier
    combined_multiplier = (desc_multiplier + steps_multiplier) / 2
    if desc_multiplier == 1.0 and steps_multiplier == 1.0:
        combined_multiplier = 1.0

    # Calculate adjusted values
    adjusted_max_turns = int(base_max_turns * combined_multiplier)
    adjusted_timeout = int(base_timeout * combined_multiplier)

    # Apply bounds
    final_max_turns = _apply_bounds(
        adjusted_max_turns,
        MIN_BUDGET["max_turns"],
        MAX_BUDGET["max_turns"]
    )
    final_timeout = _apply_bounds(
        adjusted_timeout,
        MIN_BUDGET["timeout_seconds"],
        MAX_BUDGET["timeout_seconds"]
    )

    # Track bound adjustments
    if final_max_turns != adjusted_max_turns:
        if final_max_turns == MIN_BUDGET["max_turns"]:
            adjustments.append("min_turns_bound_applied")
        else:
            adjustments.append("max_turns_bound_applied")

    if final_timeout != adjusted_timeout:
        if final_timeout == MIN_BUDGET["timeout_seconds"]:
            adjustments.append("min_timeout_bound_applied")
        else:
            adjustments.append("max_timeout_bound_applied")

    return BudgetResult(
        max_turns=final_max_turns,
        timeout_seconds=final_timeout,
        task_type=task_type_lower,
        base_max_turns=base_max_turns,
        base_timeout_seconds=base_timeout,
        description_multiplier=desc_multiplier,
        steps_multiplier=steps_multiplier,
        description_length=desc_len,
        steps_count=step_cnt,
        adjustments_applied=adjustments,
    )


def get_base_budget(task_type: str) -> dict[str, int]:
    """
    Get the base budget for a task type without any adjustments.

    Args:
        task_type: The task type

    Returns:
        Dictionary with 'max_turns' and 'timeout_seconds' keys

    Example:
        >>> get_base_budget("coding")
        {'max_turns': 50, 'timeout_seconds': 1800}
    """
    task_type_lower = task_type.lower().strip() if task_type else "custom"

    if task_type_lower not in BASE_BUDGETS:
        task_type_lower = "custom"

    return dict(BASE_BUDGETS[task_type_lower])


def get_budget_bounds() -> dict[str, dict[str, int]]:
    """
    Get the minimum and maximum budget bounds.

    Returns:
        Dictionary with 'min' and 'max' keys, each containing budget limits

    Example:
        >>> bounds = get_budget_bounds()
        >>> bounds["min"]["max_turns"]
        5
        >>> bounds["max"]["timeout_seconds"]
        7200
    """
    return {
        "min": dict(MIN_BUDGET),
        "max": dict(MAX_BUDGET),
    }


def get_all_base_budgets() -> dict[str, dict[str, int]]:
    """
    Get all base budgets for all task types.

    Returns:
        Dictionary mapping task_type to base budget

    Example:
        >>> budgets = get_all_base_budgets()
        >>> budgets["coding"]["max_turns"]
        50
    """
    return {k: dict(v) for k, v in BASE_BUDGETS.items()}


# =============================================================================
# Tool Filtering (Feature #40: ToolPolicy Allowed Tools Filtering)
# =============================================================================

@dataclass
class ToolDefinition:
    """
    Represents a tool definition for the Claude SDK.

    This is a lightweight representation of tool information
    that can be used for filtering and validation.
    """
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "metadata": self.metadata,
        }


@dataclass
class ToolFilterResult:
    """
    Result of filtering tools based on ToolPolicy.

    Contains the filtered tools and information about what was filtered.
    """
    filtered_tools: list[ToolDefinition]
    allowed_count: int
    total_count: int
    filtered_out: list[str]  # Names of tools that were filtered out
    invalid_tools: list[str]  # Tools in allowed_tools that don't exist
    mode: str  # "whitelist" or "all_allowed"

    @property
    def all_allowed(self) -> bool:
        """True if all tools were allowed (no filtering applied)."""
        return self.mode == "all_allowed"

    @property
    def has_invalid_tools(self) -> bool:
        """True if some tools in allowed_tools don't exist in available tools."""
        return len(self.invalid_tools) > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "allowed_count": self.allowed_count,
            "total_count": self.total_count,
            "filtered_out": self.filtered_out,
            "invalid_tools": self.invalid_tools,
            "mode": self.mode,
            "all_allowed": self.all_allowed,
            "has_invalid_tools": self.has_invalid_tools,
        }


def extract_allowed_tools(tool_policy: dict[str, Any] | None) -> list[str] | None:
    """
    Extract allowed_tools from a tool_policy dict.

    Feature #40, Step 1: Extract allowed_tools from spec.tool_policy

    Handles various edge cases:
    - None tool_policy -> None (all tools allowed)
    - Missing allowed_tools key -> None (all tools allowed)
    - Empty list -> None (all tools allowed)
    - None value -> None (all tools allowed)
    - Non-list values (with warning) -> None

    Args:
        tool_policy: Tool policy dictionary from AgentSpec

    Returns:
        List of tool name strings, or None if all tools should be allowed

    Example:
        >>> policy = {
        ...     "policy_version": "v1",
        ...     "allowed_tools": ["Read", "Write", "Edit"]
        ... }
        >>> extract_allowed_tools(policy)
        ['Read', 'Write', 'Edit']

        >>> extract_allowed_tools(None)  # All allowed
        None

        >>> extract_allowed_tools({"allowed_tools": []})  # All allowed
        None
    """
    if tool_policy is None:
        return None

    allowed = tool_policy.get("allowed_tools")

    if allowed is None:
        return None

    if not isinstance(allowed, list):
        _logger.warning(
            "allowed_tools is not a list: %r (type: %s), treating as None (all allowed)",
            allowed, type(allowed).__name__
        )
        return None

    # Filter to only valid string entries
    valid_tools = []
    for tool in allowed:
        if isinstance(tool, str):
            stripped = tool.strip()
            if stripped:
                valid_tools.append(stripped)
        else:
            _logger.warning(
                "Skipping non-string tool in allowed_tools: %r (type: %s)",
                tool, type(tool).__name__
            )

    # Feature #40, Step 2: If None or empty, allow all available tools
    if not valid_tools:
        return None

    return valid_tools


def validate_tool_names(
    tool_names: list[str],
    available_tools: list[str],
) -> tuple[list[str], list[str]]:
    """
    Validate that tool names exist in the available tools set.

    Feature #40, Step 5: Verify filtered tools are valid MCP tool names

    Args:
        tool_names: List of tool names to validate
        available_tools: List of available tool names

    Returns:
        Tuple of (valid_tools, invalid_tools)
        - valid_tools: Tool names that exist in available_tools
        - invalid_tools: Tool names that don't exist

    Example:
        >>> available = ["Read", "Write", "Bash"]
        >>> validate_tool_names(["Read", "Write", "InvalidTool"], available)
        (['Read', 'Write'], ['InvalidTool'])
    """
    available_set = set(available_tools)
    valid = []
    invalid = []

    for name in tool_names:
        if name in available_set:
            valid.append(name)
        else:
            invalid.append(name)

    return valid, invalid


def filter_tools(
    available_tools: list[ToolDefinition] | list[dict[str, Any]],
    allowed_tools: list[str] | None,
    *,
    spec_id: str | None = None,
) -> ToolFilterResult:
    """
    Filter tools based on allowed_tools whitelist.

    Feature #40: ToolPolicy Allowed Tools Filtering

    This function implements the core filtering logic:
    - Step 2: If None or empty, allow all available tools
    - Step 3: If list provided, filter tools to only include those in list
    - Step 4: Log which tools are available to agent
    - Step 5: Verify filtered tools are valid MCP tool names
    - Step 6: Return filtered tool definitions to Claude SDK

    Args:
        available_tools: List of available tool definitions (ToolDefinition or dicts)
        allowed_tools: List of allowed tool names, or None to allow all
        spec_id: Optional spec ID for logging context

    Returns:
        ToolFilterResult with filtered tools and filtering metadata

    Example:
        >>> tools = [
        ...     ToolDefinition(name="Read", description="Read file"),
        ...     ToolDefinition(name="Write", description="Write file"),
        ...     ToolDefinition(name="Bash", description="Run command"),
        ... ]
        >>> result = filter_tools(tools, ["Read", "Write"])
        >>> len(result.filtered_tools)
        2
        >>> result.filtered_out
        ['Bash']

        >>> result = filter_tools(tools, None)  # All allowed
        >>> len(result.filtered_tools)
        3
        >>> result.mode
        'all_allowed'
    """
    # Normalize input to ToolDefinition objects
    normalized_tools: list[ToolDefinition] = []
    for tool in available_tools:
        if isinstance(tool, ToolDefinition):
            normalized_tools.append(tool)
        elif isinstance(tool, dict):
            normalized_tools.append(ToolDefinition(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                input_schema=tool.get("input_schema", {}),
                metadata=tool.get("metadata", {}),
            ))
        else:
            _logger.warning("Skipping invalid tool definition: %r", tool)

    # Get available tool names for validation
    available_names = [t.name for t in normalized_tools]
    total_count = len(normalized_tools)

    # Step 2: If None or empty, allow all available tools
    if not allowed_tools:
        # Feature #40, Step 4: Log which tools are available
        _logger.info(
            "All %d tools allowed for spec %s: %s",
            total_count,
            spec_id or "unknown",
            ", ".join(sorted(available_names))
        )

        return ToolFilterResult(
            filtered_tools=normalized_tools,
            allowed_count=total_count,
            total_count=total_count,
            filtered_out=[],
            invalid_tools=[],
            mode="all_allowed",
        )

    # Step 5: Verify filtered tools are valid MCP tool names
    valid_names, invalid_names = validate_tool_names(allowed_tools, available_names)

    if invalid_names:
        _logger.warning(
            "Some allowed_tools are not valid for spec %s: %s",
            spec_id or "unknown",
            ", ".join(invalid_names)
        )

    # Step 3: Filter tools to only include those in allowed_tools list
    allowed_set = set(valid_names)
    filtered: list[ToolDefinition] = []
    filtered_out: list[str] = []

    for tool in normalized_tools:
        if tool.name in allowed_set:
            filtered.append(tool)
        else:
            filtered_out.append(tool.name)

    # Step 4: Log which tools are available to agent
    allowed_count = len(filtered)
    _logger.info(
        "Filtered tools for spec %s: %d/%d allowed (%s)",
        spec_id or "unknown",
        allowed_count,
        total_count,
        ", ".join(sorted(t.name for t in filtered))
    )

    if filtered_out:
        _logger.debug(
            "Tools filtered out for spec %s: %s",
            spec_id or "unknown",
            ", ".join(sorted(filtered_out))
        )

    # Step 6: Return filtered tool definitions
    return ToolFilterResult(
        filtered_tools=filtered,
        allowed_count=allowed_count,
        total_count=total_count,
        filtered_out=filtered_out,
        invalid_tools=invalid_names,
        mode="whitelist",
    )


def filter_tools_for_spec(
    spec: "AgentSpec",
    available_tools: list[ToolDefinition] | list[dict[str, Any]],
) -> ToolFilterResult:
    """
    Filter tools for a specific AgentSpec.

    Convenience function that extracts allowed_tools from the spec
    and calls filter_tools.

    Args:
        spec: The AgentSpec with tool_policy
        available_tools: List of available tool definitions

    Returns:
        ToolFilterResult with filtered tools

    Example:
        # In HarnessKernel.execute():
        from api.tool_policy import filter_tools_for_spec

        result = filter_tools_for_spec(spec, all_available_tools)
        filtered_tool_defs = result.filtered_tools
    """
    tool_policy = spec.tool_policy or {}
    allowed_tools = extract_allowed_tools(tool_policy)

    return filter_tools(
        available_tools=available_tools,
        allowed_tools=allowed_tools,
        spec_id=spec.id,
    )


def get_filtered_tool_names(
    tool_policy: dict[str, Any] | None,
    available_tool_names: list[str],
    *,
    spec_id: str | None = None,
) -> tuple[list[str], list[str]]:
    """
    Get filtered tool names based on tool_policy.

    This is a lightweight version of filter_tools that works with
    just tool names, without needing full tool definitions.

    Args:
        tool_policy: Tool policy dict with allowed_tools
        available_tool_names: List of all available tool names
        spec_id: Optional spec ID for logging

    Returns:
        Tuple of (filtered_names, filtered_out_names)

    Example:
        >>> available = ["Read", "Write", "Bash", "Edit"]
        >>> policy = {"allowed_tools": ["Read", "Edit"]}
        >>> filtered, out = get_filtered_tool_names(policy, available)
        >>> filtered
        ['Read', 'Edit']
        >>> out
        ['Bash', 'Write']
    """
    allowed_tools = extract_allowed_tools(tool_policy)

    if not allowed_tools:
        # All allowed
        _logger.info(
            "All %d tools allowed for spec %s",
            len(available_tool_names),
            spec_id or "unknown"
        )
        return list(available_tool_names), []

    # Validate and filter
    valid_names, invalid_names = validate_tool_names(allowed_tools, available_tool_names)

    if invalid_names:
        _logger.warning(
            "Invalid tool names in allowed_tools for spec %s: %s",
            spec_id or "unknown",
            ", ".join(invalid_names)
        )

    # Get filtered out names
    allowed_set = set(valid_names)
    filtered_out = [name for name in available_tool_names if name not in allowed_set]

    _logger.info(
        "Tool filtering for spec %s: %d allowed, %d filtered out",
        spec_id or "unknown",
        len(valid_names),
        len(filtered_out)
    )

    return valid_names, filtered_out


# =============================================================================
# Feature #44: Policy Violation Event Logging
# =============================================================================

# Violation types - categorizes the type of policy violation
VIOLATION_TYPES = [
    "allowed_tools",        # Tool not in allowed_tools list
    "forbidden_patterns",   # Arguments matched a forbidden pattern
    "directory_sandbox",    # File path outside allowed directories
]


@dataclass
class PolicyViolation:
    """
    Represents a policy violation that occurred during agent execution.

    This dataclass captures all relevant information about a policy violation
    for event logging and aggregation.

    Attributes:
        violation_type: Category of violation (allowed_tools, forbidden_patterns, directory_sandbox)
        tool_name: Name of the tool that triggered the violation
        turn_number: Agent turn number when the violation occurred
        details: Dictionary containing violation-specific details
        message: Human-readable description of the violation
        blocked_operation: Description of what operation was blocked
    """
    violation_type: str
    tool_name: str
    turn_number: int
    details: dict[str, Any]
    message: str
    blocked_operation: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "violation_type": self.violation_type,
            "tool_name": self.tool_name,
            "turn_number": self.turn_number,
            "details": self.details,
            "message": self.message,
            "blocked_operation": self.blocked_operation,
        }


@dataclass
class ViolationAggregation:
    """
    Aggregated violation counts for a run.

    This is stored in run metadata to provide a summary of all violations
    without needing to query events.

    Attributes:
        total_count: Total number of violations
        by_type: Count per violation type
        by_tool: Count per tool name
        last_turn: Turn number of the most recent violation
    """
    total_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_tool: dict[str, int] = field(default_factory=dict)
    last_turn: int = 0

    def add_violation(
        self,
        violation_type: str,
        tool_name: str,
        turn_number: int,
    ) -> None:
        """
        Update aggregation with a new violation.

        Args:
            violation_type: Type of the violation
            tool_name: Name of the tool
            turn_number: Turn number when violation occurred
        """
        self.total_count += 1

        # Update by_type count
        self.by_type[violation_type] = self.by_type.get(violation_type, 0) + 1

        # Update by_tool count
        self.by_tool[tool_name] = self.by_tool.get(tool_name, 0) + 1

        # Track latest turn
        if turn_number > self.last_turn:
            self.last_turn = turn_number

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_count": self.total_count,
            "by_type": self.by_type,
            "by_tool": self.by_tool,
            "last_turn": self.last_turn,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ViolationAggregation":
        """Create ViolationAggregation from dictionary."""
        if not data:
            return cls()

        return cls(
            total_count=data.get("total_count", 0),
            by_type=data.get("by_type", {}),
            by_tool=data.get("by_tool", {}),
            last_turn=data.get("last_turn", 0),
        )


def create_allowed_tools_violation(
    tool_name: str,
    turn_number: int,
    allowed_tools: list[str] | None,
    arguments: dict[str, Any] | None = None,
) -> PolicyViolation:
    """
    Create a PolicyViolation for an allowed_tools violation.

    Feature #44, Step 2: When tool blocked by allowed_tools, record event.

    Args:
        tool_name: Name of the tool that was blocked
        turn_number: Agent turn number when violation occurred
        allowed_tools: List of allowed tools (for context in details)
        arguments: Tool arguments that were blocked

    Returns:
        PolicyViolation instance ready for logging

    Example:
        >>> violation = create_allowed_tools_violation(
        ...     "rm", turn_number=5, allowed_tools=["Read", "Write"]
        ... )
        >>> violation.violation_type
        'allowed_tools'
    """
    # Limit allowed_tools list in details to avoid huge payloads
    allowed_preview = (allowed_tools[:10] + ["..."]) if allowed_tools and len(allowed_tools) > 10 else allowed_tools

    details = {
        "blocked_tool": tool_name,
        "allowed_tools": allowed_preview,
        "allowed_tools_count": len(allowed_tools) if allowed_tools else 0,
    }

    # Include truncated arguments if provided
    if arguments:
        args_str = json.dumps(arguments, default=str)
        if len(args_str) > 500:
            details["arguments_preview"] = args_str[:500] + "..."
        else:
            details["arguments"] = arguments

    return PolicyViolation(
        violation_type="allowed_tools",
        tool_name=tool_name,
        turn_number=turn_number,
        details=details,
        message=f"Tool '{tool_name}' is not in the allowed_tools whitelist",
        blocked_operation=f"Call to tool '{tool_name}'",
    )


def create_forbidden_patterns_violation(
    tool_name: str,
    turn_number: int,
    pattern_matched: str,
    arguments: dict[str, Any] | None = None,
) -> PolicyViolation:
    """
    Create a PolicyViolation for a forbidden_patterns violation.

    Feature #44, Step 3: When tool blocked by forbidden_patterns, record pattern matched.

    Args:
        tool_name: Name of the tool that was blocked
        turn_number: Agent turn number when violation occurred
        pattern_matched: The regex pattern that matched
        arguments: Tool arguments that matched the pattern

    Returns:
        PolicyViolation instance ready for logging

    Example:
        >>> violation = create_forbidden_patterns_violation(
        ...     "Bash", turn_number=10, pattern_matched="rm -rf"
        ... )
        >>> violation.details["pattern_matched"]
        'rm -rf'
    """
    details = {
        "blocked_tool": tool_name,
        "pattern_matched": pattern_matched,
    }

    # Include truncated arguments if provided
    if arguments:
        args_str = json.dumps(arguments, default=str)
        if len(args_str) > 500:
            details["arguments_preview"] = args_str[:500] + "..."
        else:
            details["arguments"] = arguments

    return PolicyViolation(
        violation_type="forbidden_patterns",
        tool_name=tool_name,
        turn_number=turn_number,
        details=details,
        message=f"Tool '{tool_name}' arguments match forbidden pattern: '{pattern_matched}'",
        blocked_operation=f"Call to tool '{tool_name}' with pattern-matching arguments",
    )


def create_directory_sandbox_violation(
    tool_name: str,
    turn_number: int,
    attempted_path: str,
    reason: str,
    allowed_directories: list[str],
    was_symlink: bool = False,
) -> PolicyViolation:
    """
    Create a PolicyViolation for a directory sandbox violation.

    Feature #44, Step 4: When file operation blocked by sandbox, record attempted path.

    Args:
        tool_name: Name of the tool that was blocked
        turn_number: Agent turn number when violation occurred
        attempted_path: The path that was blocked
        reason: Reason for blocking (e.g., "path traversal", "outside sandbox")
        allowed_directories: List of allowed directories for context
        was_symlink: Whether the path was a symlink

    Returns:
        PolicyViolation instance ready for logging

    Example:
        >>> violation = create_directory_sandbox_violation(
        ...     "write_file", turn_number=15,
        ...     attempted_path="/etc/passwd",
        ...     reason="Path is not within any allowed directory",
        ...     allowed_directories=["/home/user/project"]
        ... )
        >>> violation.details["attempted_path"]
        '/etc/passwd'
    """
    # Limit allowed_directories list in details
    dirs_preview = (allowed_directories[:5] + ["..."]) if len(allowed_directories) > 5 else allowed_directories

    details = {
        "blocked_tool": tool_name,
        "attempted_path": attempted_path,
        "reason": reason,
        "allowed_directories": dirs_preview,
        "allowed_directories_count": len(allowed_directories),
        "was_symlink": was_symlink,
    }

    return PolicyViolation(
        violation_type="directory_sandbox",
        tool_name=tool_name,
        turn_number=turn_number,
        details=details,
        message=f"Tool '{tool_name}' blocked: {reason}",
        blocked_operation=f"File operation on path '{attempted_path}'",
    )


def record_policy_violation_event(
    db: "Session",
    run_id: str,
    sequence: int,
    violation: PolicyViolation,
) -> "AgentEvent":
    """
    Record a policy_violation event for a run.

    Feature #44: Log all tool policy violations as AgentEvents with
    violation type and blocked operation details.

    The event payload includes:
    - violation_type: Category of violation
    - tool_name: Tool that triggered the violation
    - turn_number: Agent turn number for context (Step 5)
    - blocked_operation: What was blocked
    - message: Human-readable explanation
    - details: Violation-specific details

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        violation: PolicyViolation instance with all details

    Returns:
        The created AgentEvent

    Example:
        >>> violation = create_forbidden_patterns_violation("Bash", 5, "rm -rf")
        >>> event = record_policy_violation_event(db, run_id, 10, violation)
        >>> event.event_type
        'policy_violation'
    """
    from api.agentspec_models import AgentEvent

    # Build payload with all violation details
    payload = {
        "violation_type": violation.violation_type,
        "tool": violation.tool_name,
        "turn_number": violation.turn_number,  # Feature #44, Step 5
        "blocked_operation": violation.blocked_operation,
        "message": violation.message,
        "details": violation.details,
    }

    event = AgentEvent(
        run_id=run_id,
        sequence=sequence,
        event_type="policy_violation",
        timestamp=_utc_now(),
        payload=payload,
        tool_name=violation.tool_name,
    )

    db.add(event)
    # Note: Caller should commit the session

    _logger.info(
        "Recorded policy_violation event: run=%s, type=%s, tool=%s, turn=%d",
        run_id,
        violation.violation_type,
        violation.tool_name,
        violation.turn_number,
    )

    return event


def record_allowed_tools_violation(
    db: "Session",
    run_id: str,
    sequence: int,
    tool_name: str,
    turn_number: int,
    allowed_tools: list[str] | None,
    arguments: dict[str, Any] | None = None,
) -> "AgentEvent":
    """
    Convenience function to record an allowed_tools violation event.

    Feature #44, Step 2: When tool blocked by allowed_tools, record event.

    Args:
        db: Database session
        run_id: Run ID
        sequence: Event sequence number
        tool_name: Name of blocked tool
        turn_number: Agent turn number
        allowed_tools: List of allowed tools
        arguments: Tool arguments that were blocked

    Returns:
        The created AgentEvent
    """
    violation = create_allowed_tools_violation(
        tool_name=tool_name,
        turn_number=turn_number,
        allowed_tools=allowed_tools,
        arguments=arguments,
    )
    return record_policy_violation_event(db, run_id, sequence, violation)


def record_forbidden_patterns_violation(
    db: "Session",
    run_id: str,
    sequence: int,
    tool_name: str,
    turn_number: int,
    pattern_matched: str,
    arguments: dict[str, Any] | None = None,
) -> "AgentEvent":
    """
    Convenience function to record a forbidden_patterns violation event.

    Feature #44, Step 3: When tool blocked by forbidden_patterns, record pattern matched.

    Args:
        db: Database session
        run_id: Run ID
        sequence: Event sequence number
        tool_name: Name of blocked tool
        turn_number: Agent turn number
        pattern_matched: The pattern that matched
        arguments: Tool arguments that matched

    Returns:
        The created AgentEvent
    """
    violation = create_forbidden_patterns_violation(
        tool_name=tool_name,
        turn_number=turn_number,
        pattern_matched=pattern_matched,
        arguments=arguments,
    )
    return record_policy_violation_event(db, run_id, sequence, violation)


def record_directory_sandbox_violation(
    db: "Session",
    run_id: str,
    sequence: int,
    tool_name: str,
    turn_number: int,
    attempted_path: str,
    reason: str,
    allowed_directories: list[str],
    was_symlink: bool = False,
) -> "AgentEvent":
    """
    Convenience function to record a directory_sandbox violation event.

    Feature #44, Step 4: When file operation blocked by sandbox, record attempted path.

    Args:
        db: Database session
        run_id: Run ID
        sequence: Event sequence number
        tool_name: Name of blocked tool
        turn_number: Agent turn number
        attempted_path: The path that was blocked
        reason: Reason for blocking
        allowed_directories: List of allowed directories
        was_symlink: Whether the path was a symlink

    Returns:
        The created AgentEvent
    """
    violation = create_directory_sandbox_violation(
        tool_name=tool_name,
        turn_number=turn_number,
        attempted_path=attempted_path,
        reason=reason,
        allowed_directories=allowed_directories,
        was_symlink=was_symlink,
    )
    return record_policy_violation_event(db, run_id, sequence, violation)


def get_violation_aggregation(
    db: "Session",
    run_id: str,
) -> ViolationAggregation:
    """
    Compute violation aggregation from events for a run.

    Feature #44, Step 6: Aggregate violation count in run metadata.

    This function queries all policy_violation events for a run and
    computes aggregated statistics.

    Args:
        db: Database session
        run_id: Run ID to aggregate violations for

    Returns:
        ViolationAggregation with counts and statistics

    Example:
        >>> aggregation = get_violation_aggregation(db, run_id)
        >>> print(f"Total violations: {aggregation.total_count}")
        >>> print(f"By type: {aggregation.by_type}")
    """
    from api.agentspec_models import AgentEvent

    # Query all policy_violation events for this run
    events = (
        db.query(AgentEvent)
        .filter(AgentEvent.run_id == run_id)
        .filter(AgentEvent.event_type == "policy_violation")
        .all()
    )

    aggregation = ViolationAggregation()

    for event in events:
        if event.payload:
            violation_type = event.payload.get("violation_type", "unknown")
            tool_name = event.payload.get("tool", event.tool_name or "unknown")
            turn_number = event.payload.get("turn_number", 0)

            aggregation.add_violation(violation_type, tool_name, turn_number)

    _logger.debug(
        "Computed violation aggregation for run %s: total=%d, by_type=%s",
        run_id,
        aggregation.total_count,
        aggregation.by_type,
    )

    return aggregation


def update_run_violation_metadata(
    db: "Session",
    run_id: str,
    violation: PolicyViolation,
) -> dict[str, Any]:
    """
    Update the run's metadata with incremental violation aggregation.

    Feature #44, Step 6: Aggregate violation count in run metadata.

    This function updates the AgentRun's acceptance_results field to include
    violation aggregation data. It's called each time a violation is recorded.

    Args:
        db: Database session
        run_id: Run ID to update
        violation: The new violation to add to aggregation

    Returns:
        Updated aggregation dictionary

    Note:
        The aggregation is stored in a "violation_aggregation" key within
        the run's metadata/acceptance_results for easy access.
    """
    from api.agentspec_models import AgentRun

    # Get the run
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()

    if not run:
        _logger.warning("Cannot update violation metadata: run %s not found", run_id)
        return {}

    # Get or initialize acceptance_results
    if run.acceptance_results is None:
        run.acceptance_results = {}

    # Extract existing aggregation or create new one
    existing_data = run.acceptance_results.get("violation_aggregation", {})
    aggregation = ViolationAggregation.from_dict(existing_data)

    # Add the new violation
    aggregation.add_violation(
        violation.violation_type,
        violation.tool_name,
        violation.turn_number,
    )

    # Update the run's metadata
    # Need to create a new dict to trigger SQLAlchemy change detection
    updated_results = dict(run.acceptance_results)
    updated_results["violation_aggregation"] = aggregation.to_dict()
    run.acceptance_results = updated_results

    # Note: Caller should commit the session

    _logger.debug(
        "Updated run %s violation metadata: total=%d",
        run_id,
        aggregation.total_count,
    )

    return aggregation.to_dict()


def record_and_aggregate_violation(
    db: "Session",
    run_id: str,
    sequence: int,
    violation: PolicyViolation,
) -> tuple["AgentEvent", dict[str, Any]]:
    """
    Record a violation event and update run aggregation in one operation.

    This is the main entry point for logging policy violations during execution.
    It combines event recording with metadata aggregation for convenience.

    Args:
        db: Database session
        run_id: Run ID
        sequence: Event sequence number
        violation: PolicyViolation instance

    Returns:
        Tuple of (created event, updated aggregation dict)

    Example:
        >>> violation = create_forbidden_patterns_violation("Bash", 5, "rm -rf")
        >>> event, aggregation = record_and_aggregate_violation(db, run_id, 10, violation)
        >>> print(f"Event ID: {event.id}, Total violations: {aggregation['total_count']}")
    """
    # Record the event
    event = record_policy_violation_event(db, run_id, sequence, violation)

    # Update aggregation
    aggregation = update_run_violation_metadata(db, run_id, violation)

    return event, aggregation
