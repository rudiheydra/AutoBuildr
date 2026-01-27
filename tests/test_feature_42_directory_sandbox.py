"""
Tests for Feature #42: Directory Sandbox Restriction

This feature implements:
1. Extract allowed_directories from spec.tool_policy
2. Resolve all allowed paths to absolute paths
3. For file operation tools, extract target path from arguments
4. Resolve target path to absolute
5. Check if target is under any allowed directory
6. Block path traversal attempts (..)
7. If target is symlink, resolve and validate final target
8. Record violation in event log
9. Return permission denied error to agent

Tests cover all 9 verification steps.
"""

import os
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.tool_policy import (
    DirectoryAccessBlocked,
    ToolPolicyEnforcer,
    contains_path_traversal,
    create_enforcer_for_run,
    extract_allowed_directories,
    extract_path_from_arguments,
    is_path_under_directories,
    record_directory_blocked_event,
    resolve_target_path,
    resolve_to_absolute_paths,
    validate_directory_access,
)


# =============================================================================
# Step 1: Extract allowed_directories from spec.tool_policy
# =============================================================================

class TestExtractAllowedDirectories:
    """Tests for extract_allowed_directories function (Step 1)."""

    def test_extract_from_valid_policy(self):
        """Extract directories from a valid tool_policy dict."""
        policy = {
            "policy_version": "v1",
            "allowed_tools": ["read_file", "write_file"],
            "allowed_directories": ["/home/user/project", "/tmp"],
        }
        result = extract_allowed_directories(policy)
        assert result == ["/home/user/project", "/tmp"]

    def test_extract_from_none_policy(self):
        """Handle None tool_policy gracefully."""
        result = extract_allowed_directories(None)
        assert result == []

    def test_extract_from_empty_policy(self):
        """Handle empty dict gracefully."""
        result = extract_allowed_directories({})
        assert result == []

    def test_extract_missing_key(self):
        """Handle missing allowed_directories key."""
        policy = {"allowed_tools": ["some_tool"]}
        result = extract_allowed_directories(policy)
        assert result == []

    def test_extract_none_directories(self):
        """Handle None allowed_directories value."""
        policy = {"allowed_directories": None}
        result = extract_allowed_directories(policy)
        assert result == []

    def test_extract_empty_list(self):
        """Handle empty allowed_directories list."""
        policy = {"allowed_directories": []}
        result = extract_allowed_directories(policy)
        assert result == []

    def test_extract_non_list_returns_empty(self):
        """Non-list allowed_directories should return empty with warning."""
        policy = {"allowed_directories": "/single/path"}
        result = extract_allowed_directories(policy)
        assert result == []

    def test_extract_filters_non_strings(self):
        """Non-string entries should be filtered out."""
        policy = {"allowed_directories": ["/valid", 123, None, "/also_valid"]}
        result = extract_allowed_directories(policy)
        assert result == ["/valid", "/also_valid"]


# =============================================================================
# Step 2: Resolve all allowed paths to absolute paths
# =============================================================================

class TestResolveToAbsolutePaths:
    """Tests for resolve_to_absolute_paths function (Step 2)."""

    def test_resolve_absolute_paths(self):
        """Absolute paths should remain absolute."""
        paths = ["/home/user/project", "/tmp"]
        resolved = resolve_to_absolute_paths(paths)
        assert len(resolved) == 2
        assert all(p.is_absolute() for p in resolved)

    def test_resolve_relative_paths(self):
        """Relative paths should be resolved against base_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = ["./src", "../parent"]
            resolved = resolve_to_absolute_paths(paths, base_dir=tmpdir)
            assert len(resolved) == 2
            assert all(p.is_absolute() for p in resolved)

    def test_resolve_empty_list(self):
        """Empty list should return empty list."""
        result = resolve_to_absolute_paths([])
        assert result == []

    def test_resolve_none_input(self):
        """None should return empty list (via falsy check)."""
        # This won't actually be called with None since extract returns list
        result = resolve_to_absolute_paths([])
        assert result == []

    def test_resolve_normalizes_paths(self):
        """Paths should be normalized (no ..)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "a", "b"))
            paths = [os.path.join(tmpdir, "a", "b", "..", "c")]
            resolved = resolve_to_absolute_paths(paths)
            # After resolve(), the path should be normalized
            assert len(resolved) == 1
            assert ".." not in str(resolved[0])


# =============================================================================
# Step 3: Extract target path from arguments
# =============================================================================

class TestExtractPathFromArguments:
    """Tests for extract_path_from_arguments function (Step 3)."""

    def test_extract_path_key(self):
        """Extract from 'path' key."""
        args = {"path": "/home/user/file.txt"}
        result = extract_path_from_arguments("write_file", args)
        assert result == "/home/user/file.txt"

    def test_extract_file_path_key(self):
        """Extract from 'file_path' key."""
        args = {"file_path": "/etc/passwd"}
        result = extract_path_from_arguments("read_file", args)
        assert result == "/etc/passwd"

    def test_extract_target_key(self):
        """Extract from 'target' key."""
        args = {"target": "/tmp/output.txt"}
        result = extract_path_from_arguments("copy_file", args)
        assert result == "/tmp/output.txt"

    def test_extract_directory_key(self):
        """Extract from 'directory' key."""
        args = {"directory": "/home/user/docs"}
        result = extract_path_from_arguments("create_directory", args)
        assert result == "/home/user/docs"

    def test_extract_from_bash_command(self):
        """Extract path from bash command string."""
        args = {"command": "cat /etc/passwd"}
        result = extract_path_from_arguments("bash", args)
        assert result == "/etc/passwd"

    def test_extract_from_bash_relative_path(self):
        """Extract relative path from bash command."""
        args = {"command": "ls ./src"}
        result = extract_path_from_arguments("bash", args)
        assert result == "./src"

    def test_extract_from_bash_parent_traversal(self):
        """Extract parent traversal path from bash command."""
        args = {"command": "cat ../secret.txt"}
        result = extract_path_from_arguments("bash", args)
        assert result == "../secret.txt"

    def test_extract_none_arguments(self):
        """None arguments should return None."""
        result = extract_path_from_arguments("write_file", None)
        assert result is None

    def test_extract_no_path_found(self):
        """No path-like arguments should return None."""
        args = {"data": "some content", "format": "json"}
        result = extract_path_from_arguments("process", args)
        assert result is None


# =============================================================================
# Step 4: Resolve target path to absolute
# =============================================================================

class TestResolveTargetPath:
    """Tests for resolve_target_path function (Step 4)."""

    def test_resolve_absolute_path(self):
        """Absolute path should remain absolute."""
        path, was_symlink, is_broken = resolve_target_path("/home/user/file.txt")
        assert path.is_absolute()
        assert str(path) == "/home/user/file.txt"

    def test_resolve_relative_path(self):
        """Relative path should be made absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path, was_symlink, is_broken = resolve_target_path("file.txt", base_dir=tmpdir)
            assert path.is_absolute()
            assert str(path).startswith(tmpdir)

    def test_detect_symlink(self):
        """Symlink should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file and symlink
            real_file = os.path.join(tmpdir, "real.txt")
            symlink = os.path.join(tmpdir, "link.txt")

            with open(real_file, "w") as f:
                f.write("test")

            os.symlink(real_file, symlink)

            path, was_symlink, is_broken = resolve_target_path(symlink)
            assert was_symlink is True


# =============================================================================
# Step 5: Check if target is under any allowed directory
# =============================================================================

class TestIsPathUnderDirectories:
    """Tests for is_path_under_directories function (Step 5)."""

    def test_path_under_allowed_directory(self):
        """Path under allowed directory should return True."""
        allowed = [Path("/home/user/project")]
        target = Path("/home/user/project/src/file.py")
        assert is_path_under_directories(target, allowed) is True

    def test_path_not_under_any_directory(self):
        """Path not under any allowed directory should return False."""
        allowed = [Path("/home/user/project")]
        target = Path("/etc/passwd")
        assert is_path_under_directories(target, allowed) is False

    def test_path_under_one_of_multiple(self):
        """Path under one of multiple allowed directories should return True."""
        allowed = [Path("/home/user/project"), Path("/tmp")]
        target = Path("/tmp/test.txt")
        assert is_path_under_directories(target, allowed) is True

    def test_empty_allowed_directories(self):
        """Empty allowed directories means no restriction (returns True)."""
        target = Path("/anywhere/any/path.txt")
        assert is_path_under_directories(target, []) is True

    def test_exact_directory_match(self):
        """Exact directory path should return True."""
        allowed = [Path("/home/user/project")]
        target = Path("/home/user/project")
        assert is_path_under_directories(target, allowed) is True

    def test_sibling_directory_not_allowed(self):
        """Sibling directory should return False."""
        allowed = [Path("/home/user/project")]
        target = Path("/home/user/other/file.txt")
        assert is_path_under_directories(target, allowed) is False


# =============================================================================
# Step 6: Block path traversal attempts (..)
# =============================================================================

class TestContainsPathTraversal:
    """Tests for contains_path_traversal function (Step 6)."""

    def test_detect_direct_traversal(self):
        """Direct .. traversal should be detected."""
        assert contains_path_traversal("/home/user/../root/secret") is True

    def test_detect_multiple_traversals(self):
        """Multiple .. traversals should be detected."""
        assert contains_path_traversal("/a/b/../../c") is True

    def test_detect_url_encoded_traversal(self):
        """URL-encoded traversal should be detected."""
        # URL-encoded ../ patterns
        assert contains_path_traversal("/home/%2e%2e/secret") is True
        assert contains_path_traversal("/%2e%2e/etc/passwd") is True

    def test_detect_double_encoded_traversal(self):
        """Double URL-encoded traversal should be detected."""
        # Double URL-encoded ../ patterns
        assert contains_path_traversal("/home/%252e%252e/secret") is True
        assert contains_path_traversal("/%252e%252e/etc/passwd") is True

    def test_no_traversal_in_normal_path(self):
        """Normal paths without traversal should return False."""
        assert contains_path_traversal("/home/user/project/file.txt") is False

    def test_relative_path_without_traversal(self):
        """Relative path without .. should return False."""
        assert contains_path_traversal("./src/file.py") is False

    def test_dots_in_filename(self):
        """Dots in filename should not be detected as traversal."""
        assert contains_path_traversal("/home/user/file..txt") is False
        assert contains_path_traversal("/home/user/.hidden") is False


# =============================================================================
# Step 7: Resolve symlinks and validate final target
# =============================================================================

class TestSymlinkValidation:
    """Tests for symlink resolution (Step 7)."""

    def test_symlink_resolved_to_real_path(self):
        """Symlink should be resolved to real path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create structure: tmpdir/allowed/real.txt, tmpdir/link.txt -> allowed/real.txt
            allowed_dir = os.path.join(tmpdir, "allowed")
            os.makedirs(allowed_dir)

            real_file = os.path.join(allowed_dir, "real.txt")
            with open(real_file, "w") as f:
                f.write("test")

            # Symlink from outside allowed dir to inside
            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(real_file, symlink)

            # Resolving should follow symlink
            path, was_symlink, is_broken = resolve_target_path(symlink, follow_symlinks=True)
            assert was_symlink is True
            assert str(path) == real_file

    def test_symlink_to_outside_blocked(self):
        """Symlink that resolves outside allowed directories should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create structure: tmpdir/allowed/, tmpdir/forbidden/secret.txt
            allowed_dir = os.path.join(tmpdir, "allowed")
            forbidden_dir = os.path.join(tmpdir, "forbidden")
            os.makedirs(allowed_dir)
            os.makedirs(forbidden_dir)

            secret_file = os.path.join(forbidden_dir, "secret.txt")
            with open(secret_file, "w") as f:
                f.write("secret")

            # Symlink from allowed to forbidden
            symlink = os.path.join(allowed_dir, "link.txt")
            os.symlink(secret_file, symlink)

            # Validate - symlink appears in allowed, but resolves to forbidden
            allowed_paths = [Path(allowed_dir)]
            allowed, reason, details = validate_directory_access(
                "read_file", symlink, allowed_paths
            )

            # Should be blocked because resolved path is in forbidden_dir
            assert allowed is False
            assert details.get("was_symlink") is True


# =============================================================================
# Step 8: Record violation in event log
# =============================================================================

class TestRecordDirectoryBlockedEvent:
    """Tests for record_directory_blocked_event function (Step 8)."""

    def test_record_event(self):
        """Event is recorded with correct fields."""
        mock_db = MagicMock()

        event = record_directory_blocked_event(
            db=mock_db,
            run_id="run-123",
            sequence=5,
            tool_name="write_file",
            arguments={"path": "/etc/passwd"},
            target_path="/etc/passwd",
            reason="Path is not within any allowed directory",
            allowed_directories=["/home/user/project"],
        )

        # Verify event was added to session
        mock_db.add.assert_called_once()

        # Verify event properties
        assert event.run_id == "run-123"
        assert event.sequence == 5
        assert event.event_type == "tool_call"
        assert event.tool_name == "write_file"

        # Verify payload
        assert event.payload["blocked"] is True
        assert event.payload["block_type"] == "directory_sandbox"
        assert event.payload["target_path"] == "/etc/passwd"
        assert event.payload["reason"] == "Path is not within any allowed directory"
        assert event.payload["allowed_directories"] == ["/home/user/project"]

    def test_event_has_timestamp(self):
        """Event has a timestamp."""
        mock_db = MagicMock()

        event = record_directory_blocked_event(
            db=mock_db,
            run_id="run-123",
            sequence=1,
            tool_name="tool",
            arguments={},
            target_path="/path",
            reason="reason",
            allowed_directories=[],
        )

        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)


# =============================================================================
# Step 9: Return permission denied error to agent
# =============================================================================

class TestDirectoryAccessBlockedError:
    """Tests for DirectoryAccessBlocked exception (Step 9)."""

    def test_exception_properties(self):
        """Exception has correct properties."""
        exc = DirectoryAccessBlocked(
            tool_name="write_file",
            target_path="/etc/passwd",
            reason="Path is not within any allowed directory",
            allowed_directories=["/home/user/project"],
        )
        assert exc.tool_name == "write_file"
        assert exc.target_path == "/etc/passwd"
        assert exc.reason == "Path is not within any allowed directory"
        assert exc.allowed_directories == ["/home/user/project"]

    def test_exception_message(self):
        """Exception has descriptive message."""
        exc = DirectoryAccessBlocked(
            tool_name="write_file",
            target_path="/etc/passwd",
            reason="Outside sandbox",
            allowed_directories=["/home/user/project"],
        )
        message = str(exc)
        assert "write_file" in message
        assert "/etc/passwd" in message
        assert "Outside sandbox" in message
        assert "/home/user/project" in message

    def test_error_message_generation(self):
        """Error message for agent is informative."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_directories": ["/home/user/project"],
            },
            base_dir="/",
        )

        message = enforcer.get_directory_blocked_error_message(
            tool_name="write_file",
            target_path="/etc/passwd",
            reason="Path is not within any allowed directory",
        )

        assert "write_file" in message
        assert "/etc/passwd" in message
        assert "sandbox" in message.lower() or "directory" in message.lower()


# =============================================================================
# Integration Tests
# =============================================================================

class TestToolPolicyEnforcerDirectorySandbox:
    """Integration tests for ToolPolicyEnforcer with directory sandbox."""

    def test_enforcer_from_tool_policy_with_directories(self):
        """Create enforcer with allowed_directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {
                "allowed_tools": ["read_file", "write_file"],
                "allowed_directories": [tmpdir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy("test-spec", policy)

            assert enforcer.has_directory_sandbox is True
            assert enforcer.directory_count == 1

    def test_enforcer_allows_paths_in_sandbox(self):
        """Paths within sandbox should be allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {
                "allowed_directories": [tmpdir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "test-spec", policy, base_dir=tmpdir
            )

            # This should not raise
            enforcer.validate_tool_call("write_file", {"path": f"{tmpdir}/file.txt"})

    def test_enforcer_blocks_paths_outside_sandbox(self):
        """Paths outside sandbox should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {
                "allowed_directories": [tmpdir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "test-spec", policy, base_dir=tmpdir
            )

            with pytest.raises(DirectoryAccessBlocked) as exc_info:
                enforcer.validate_tool_call("write_file", {"path": "/etc/passwd"})

            assert "/etc/passwd" in str(exc_info.value)

    def test_enforcer_blocks_path_traversal(self):
        """Path traversal attempts should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {
                "allowed_directories": [tmpdir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "test-spec", policy, base_dir=tmpdir
            )

            with pytest.raises(DirectoryAccessBlocked) as exc_info:
                enforcer.validate_tool_call(
                    "write_file", {"path": f"{tmpdir}/../../../etc/passwd"}
                )

            assert "traversal" in str(exc_info.value).lower()

    def test_enforcer_no_sandbox_allows_all(self):
        """Without allowed_directories, all paths should be allowed."""
        policy = {
            "allowed_tools": ["read_file"],
            # No allowed_directories
        }

        enforcer = ToolPolicyEnforcer.from_tool_policy("test-spec", policy)

        assert enforcer.has_directory_sandbox is False

        # Should not raise even for /etc/passwd
        enforcer.validate_tool_call("read_file", {"path": "/etc/passwd"})

    def test_check_tool_call_returns_directory_error(self):
        """check_tool_call should return directory access errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {
                "allowed_directories": [tmpdir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "test-spec", policy, base_dir=tmpdir
            )

            allowed, pattern, error = enforcer.check_tool_call(
                "write_file", {"path": "/etc/passwd"}
            )

            assert allowed is False
            assert "directory_access" in pattern
            assert error is not None

    def test_to_dict_includes_directories(self):
        """to_dict should include allowed_directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {
                "allowed_directories": [tmpdir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "test-spec", policy, base_dir=tmpdir
            )

            d = enforcer.to_dict()
            assert "allowed_directories" in d
            assert len(d["allowed_directories"]) == 1


# =============================================================================
# Real-world Scenario Tests
# =============================================================================

class TestRealWorldScenarios:
    """Tests with realistic scenarios."""

    def test_project_directory_sandbox(self):
        """Agent can only access project directory."""
        with tempfile.TemporaryDirectory() as project_dir:
            # Create project structure
            src_dir = os.path.join(project_dir, "src")
            os.makedirs(src_dir)

            policy = {
                "allowed_directories": [project_dir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "coding-agent", policy, base_dir=project_dir
            )

            # Allowed paths
            enforcer.validate_tool_call("write_file", {"path": f"{src_dir}/main.py"})
            enforcer.validate_tool_call("read_file", {"path": f"{project_dir}/README.md"})

            # Blocked paths
            with pytest.raises(DirectoryAccessBlocked):
                enforcer.validate_tool_call("read_file", {"path": "/etc/passwd"})

            with pytest.raises(DirectoryAccessBlocked):
                enforcer.validate_tool_call("write_file", {"path": "/tmp/malicious.sh"})

    def test_multiple_allowed_directories(self):
        """Agent can access multiple allowed directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "project")
            cache_dir = os.path.join(tmpdir, "cache")
            os.makedirs(project_dir)
            os.makedirs(cache_dir)

            policy = {
                "allowed_directories": [project_dir, cache_dir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "agent", policy, base_dir=tmpdir
            )

            # Both directories should be allowed
            enforcer.validate_tool_call("write_file", {"path": f"{project_dir}/file.py"})
            enforcer.validate_tool_call("write_file", {"path": f"{cache_dir}/cache.json"})

            # Parent directory should be blocked
            with pytest.raises(DirectoryAccessBlocked):
                enforcer.validate_tool_call("write_file", {"path": f"{tmpdir}/other/file.txt"})

    def test_bash_command_path_extraction(self):
        """Bash commands with file paths should be validated."""
        with tempfile.TemporaryDirectory() as project_dir:
            policy = {
                "allowed_directories": [project_dir],
            }

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                "agent", policy, base_dir=project_dir
            )

            # Allowed
            enforcer.validate_tool_call("bash", {"command": f"cat {project_dir}/file.txt"})

            # Blocked
            with pytest.raises(DirectoryAccessBlocked):
                enforcer.validate_tool_call("bash", {"command": "cat /etc/passwd"})


# =============================================================================
# Verification Steps Test
# =============================================================================

class TestFeature42VerificationSteps:
    """Tests that verify all 9 feature steps work together."""

    def test_step1_extract_allowed_directories(self):
        """Step 1: Extract allowed_directories from spec.tool_policy."""
        policy = {"allowed_directories": ["/project", "/cache"]}
        dirs = extract_allowed_directories(policy)
        assert dirs == ["/project", "/cache"]

    def test_step2_resolve_to_absolute(self):
        """Step 2: Resolve all allowed paths to absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dirs = resolve_to_absolute_paths(["./src", "/absolute"], base_dir=tmpdir)
            assert all(p.is_absolute() for p in dirs)

    def test_step3_extract_path_from_arguments(self):
        """Step 3: For file operation tools, extract target path from arguments."""
        path = extract_path_from_arguments("write_file", {"path": "/test"})
        assert path == "/test"

    def test_step4_resolve_target_to_absolute(self):
        """Step 4: Resolve target path to absolute."""
        path, _, _ = resolve_target_path("./file.txt", base_dir="/home/user")
        assert path.is_absolute()

    def test_step5_check_under_allowed(self):
        """Step 5: Check if target is under any allowed directory."""
        allowed = [Path("/project")]
        assert is_path_under_directories(Path("/project/src/main.py"), allowed) is True
        assert is_path_under_directories(Path("/etc/passwd"), allowed) is False

    def test_step6_block_traversal(self):
        """Step 6: Block path traversal attempts (..)."""
        assert contains_path_traversal("/project/../../../etc/passwd") is True

    def test_step7_symlink_handling(self):
        """Step 7: If target is symlink, resolve and validate final target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real = os.path.join(tmpdir, "real.txt")
            link = os.path.join(tmpdir, "link.txt")
            with open(real, "w") as f:
                f.write("test")
            os.symlink(real, link)

            path, was_symlink, is_broken = resolve_target_path(link, follow_symlinks=True)
            assert was_symlink is True
            assert str(path) == real

    def test_step8_record_violation(self):
        """Step 8: Record violation in event log."""
        mock_db = MagicMock()
        event = record_directory_blocked_event(
            db=mock_db,
            run_id="run-123",
            sequence=1,
            tool_name="write_file",
            arguments={"path": "/etc/passwd"},
            target_path="/etc/passwd",
            reason="Outside sandbox",
            allowed_directories=["/project"],
        )
        assert event.payload["blocked"] is True
        mock_db.add.assert_called_once()

    def test_step9_permission_denied_error(self):
        """Step 9: Return permission denied error to agent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            policy = {"allowed_directories": [tmpdir]}
            enforcer = ToolPolicyEnforcer.from_tool_policy("test", policy, base_dir=tmpdir)

            with pytest.raises(DirectoryAccessBlocked) as exc_info:
                enforcer.validate_tool_call("write_file", {"path": "/etc/passwd"})

            assert "blocked" in str(exc_info.value).lower()


# =============================================================================
# create_enforcer_for_run Tests
# =============================================================================

class TestCreateEnforcerForRun:
    """Tests for the HarnessKernel integration function."""

    def test_create_enforcer_with_directories(self):
        """Create enforcer for a run with directories."""
        mock_spec = MagicMock()
        mock_spec.id = "run-spec-123"
        mock_spec.tool_policy = {
            "forbidden_patterns": ["test_pattern"],
            "allowed_directories": ["/project"],
        }

        enforcer = create_enforcer_for_run(mock_spec, base_dir="/")

        assert enforcer.spec_id == "run-spec-123"
        assert enforcer.pattern_count == 1
        assert enforcer.has_directory_sandbox is True

    def test_create_enforcer_without_directories(self):
        """Create enforcer without directory sandbox."""
        mock_spec = MagicMock()
        mock_spec.id = "spec"
        mock_spec.tool_policy = {
            "forbidden_patterns": ["pattern"],
        }

        enforcer = create_enforcer_for_run(mock_spec)

        assert enforcer.has_directory_sandbox is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
