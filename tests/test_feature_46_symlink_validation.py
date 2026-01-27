"""
Test Suite: Feature #46 - Symlink Target Validation
====================================================

Category: A. Security & Access Control

Description: When validating file paths in sandbox, resolve symlinks and
validate final target is within allowed directories.

Feature Steps:
1. Check if path is symlink using Path.is_symlink()
2. Resolve symlink to final target using Path.resolve()
3. Validate resolved target against allowed_directories
4. Handle broken symlinks gracefully
5. Log symlink resolution in debug output

This test suite verifies all 5 feature steps are correctly implemented.
"""

import os
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the functions under test
from api.tool_policy import (
    BrokenSymlinkError,
    DirectoryAccessBlocked,
    is_broken_symlink,
    get_symlink_target,
    resolve_target_path,
    validate_directory_access,
    ToolPolicyEnforcer,
)


# =============================================================================
# Step 1: Check if path is symlink using Path.is_symlink()
# =============================================================================

class TestStep1IsSymlink:
    """Feature #46, Step 1: Check if path is symlink using Path.is_symlink()"""

    def test_regular_file_not_symlink(self):
        """Regular file should not be detected as symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            regular_file = os.path.join(tmpdir, "regular.txt")
            with open(regular_file, "w") as f:
                f.write("test content")

            resolved, was_symlink, is_broken = resolve_target_path(regular_file)
            assert was_symlink is False
            assert is_broken is False

    def test_symlink_is_detected(self):
        """Symlink should be detected using is_symlink()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target file
            target_file = os.path.join(tmpdir, "target.txt")
            with open(target_file, "w") as f:
                f.write("target content")

            # Create symlink
            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target_file, symlink)

            resolved, was_symlink, is_broken = resolve_target_path(symlink)
            assert was_symlink is True
            assert is_broken is False

    def test_directory_symlink_is_detected(self):
        """Directory symlink should also be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target directory
            target_dir = os.path.join(tmpdir, "target_dir")
            os.makedirs(target_dir)

            # Create symlink to directory
            symlink = os.path.join(tmpdir, "link_dir")
            os.symlink(target_dir, symlink)

            resolved, was_symlink, is_broken = resolve_target_path(symlink)
            assert was_symlink is True
            assert is_broken is False

    def test_non_existent_path_not_symlink(self):
        """Non-existent path should not be detected as symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")

            # This should not raise, but return was_symlink=False
            resolved, was_symlink, is_broken = resolve_target_path(non_existent)
            assert was_symlink is False


# =============================================================================
# Step 2: Resolve symlink to final target using Path.resolve()
# =============================================================================

class TestStep2ResolveSymlink:
    """Feature #46, Step 2: Resolve symlink to final target using Path.resolve()"""

    def test_symlink_resolved_to_target(self):
        """Symlink should be resolved to its target path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target file
            target_file = os.path.join(tmpdir, "target.txt")
            with open(target_file, "w") as f:
                f.write("target content")

            # Create symlink
            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target_file, symlink)

            resolved, was_symlink, is_broken = resolve_target_path(symlink)

            # Should resolve to the actual target path
            assert str(resolved) == target_file
            assert was_symlink is True

    def test_chained_symlinks_resolved(self):
        """Chain of symlinks should be resolved to final target."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target file
            target_file = os.path.join(tmpdir, "target.txt")
            with open(target_file, "w") as f:
                f.write("target content")

            # Create chain: link3 -> link2 -> link1 -> target
            link1 = os.path.join(tmpdir, "link1.txt")
            link2 = os.path.join(tmpdir, "link2.txt")
            link3 = os.path.join(tmpdir, "link3.txt")

            os.symlink(target_file, link1)
            os.symlink(link1, link2)
            os.symlink(link2, link3)

            resolved, was_symlink, is_broken = resolve_target_path(link3)

            # Should resolve to the actual target path (not intermediate links)
            assert str(resolved) == target_file
            assert was_symlink is True

    def test_relative_symlink_resolved(self):
        """Relative symlink should be resolved correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create subdirectory structure
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)

            # Create target file
            target_file = os.path.join(tmpdir, "target.txt")
            with open(target_file, "w") as f:
                f.write("target content")

            # Create relative symlink from subdir to parent's file
            symlink = os.path.join(subdir, "link.txt")
            os.symlink("../target.txt", symlink)

            resolved, was_symlink, is_broken = resolve_target_path(symlink)

            # Should resolve to the actual target path
            assert str(resolved) == target_file
            assert was_symlink is True


# =============================================================================
# Step 3: Validate resolved target against allowed_directories
# =============================================================================

class TestStep3ValidateAgainstAllowedDirectories:
    """Feature #46, Step 3: Validate resolved target against allowed_directories"""

    def test_symlink_to_allowed_directory_permitted(self):
        """Symlink that resolves to allowed directory should be permitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create allowed directory and target
            allowed_dir = os.path.join(tmpdir, "allowed")
            os.makedirs(allowed_dir)
            target_file = os.path.join(allowed_dir, "target.txt")
            with open(target_file, "w") as f:
                f.write("allowed content")

            # Create symlink in tmpdir pointing to allowed dir
            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target_file, symlink)

            # Validate - allowed because resolved path is in allowed_dir
            allowed_paths = [Path(allowed_dir)]
            allowed, reason, details = validate_directory_access(
                "read_file", symlink, allowed_paths
            )

            assert allowed is True
            assert reason is None
            assert details.get("was_symlink") is True
            assert str(details.get("resolved_path")) == target_file

    def test_symlink_to_forbidden_directory_blocked(self):
        """Symlink that resolves outside allowed directories should be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create allowed and forbidden directories
            allowed_dir = os.path.join(tmpdir, "allowed")
            forbidden_dir = os.path.join(tmpdir, "forbidden")
            os.makedirs(allowed_dir)
            os.makedirs(forbidden_dir)

            # Create target in forbidden directory
            target_file = os.path.join(forbidden_dir, "secret.txt")
            with open(target_file, "w") as f:
                f.write("secret content")

            # Create symlink in allowed directory pointing to forbidden
            symlink = os.path.join(allowed_dir, "link.txt")
            os.symlink(target_file, symlink)

            # Validate - should be blocked because resolved path is in forbidden_dir
            allowed_paths = [Path(allowed_dir)]
            allowed, reason, details = validate_directory_access(
                "read_file", symlink, allowed_paths
            )

            assert allowed is False
            assert "not within any allowed directory" in reason
            assert details.get("was_symlink") is True

    def test_symlink_resolved_path_validated_not_symlink_path(self):
        """Validation should check resolved path, not the symlink location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directories
            allowed_dir = os.path.join(tmpdir, "allowed")
            other_dir = os.path.join(tmpdir, "other")
            os.makedirs(allowed_dir)
            os.makedirs(other_dir)

            # Create target in 'other' directory
            target_file = os.path.join(other_dir, "file.txt")
            with open(target_file, "w") as f:
                f.write("content")

            # Create symlink in allowed directory pointing to other
            symlink = os.path.join(allowed_dir, "link.txt")
            os.symlink(target_file, symlink)

            # Even though symlink is in allowed_dir, target is not
            allowed_paths = [Path(allowed_dir)]
            allowed, reason, details = validate_directory_access(
                "read_file", symlink, allowed_paths
            )

            # Should be blocked because the RESOLVED path is not in allowed
            assert allowed is False


# =============================================================================
# Step 4: Handle broken symlinks gracefully
# =============================================================================

class TestStep4HandleBrokenSymlinks:
    """Feature #46, Step 4: Handle broken symlinks gracefully"""

    def test_is_broken_symlink_detects_broken(self):
        """is_broken_symlink() should return True for broken symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create symlink to non-existent target
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            assert is_broken_symlink(Path(broken_link)) is True

    def test_is_broken_symlink_detects_working(self):
        """is_broken_symlink() should return False for working symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target and symlink
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            working_link = os.path.join(tmpdir, "working.txt")
            os.symlink(target, working_link)

            assert is_broken_symlink(Path(working_link)) is False

    def test_is_broken_symlink_regular_file(self):
        """is_broken_symlink() should return False for regular files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            regular_file = os.path.join(tmpdir, "regular.txt")
            with open(regular_file, "w") as f:
                f.write("content")

            assert is_broken_symlink(Path(regular_file)) is False

    def test_is_broken_symlink_non_existent(self):
        """is_broken_symlink() should return False for non-existent paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            assert is_broken_symlink(Path(non_existent)) is False

    def test_resolve_target_path_broken_symlink_returns_is_broken_true(self):
        """resolve_target_path() should return is_broken=True for broken symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            resolved, was_symlink, is_broken = resolve_target_path(broken_link)

            assert was_symlink is True
            assert is_broken is True
            # resolve() still returns a path (the would-be target)

    def test_validate_directory_access_broken_symlink_blocked_by_default(self):
        """Broken symlinks should be blocked by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_dir = tmpdir
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            allowed_paths = [Path(allowed_dir)]
            allowed, reason, details = validate_directory_access(
                "read_file", broken_link, allowed_paths
            )

            assert allowed is False
            assert "broken symlink" in reason.lower()
            assert details.get("is_broken_symlink") is True
            assert details.get("broken_symlink_blocked") is True

    def test_validate_directory_access_broken_symlink_allowed_when_configured(self):
        """Broken symlinks can be allowed when allow_broken_symlinks=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_dir = tmpdir
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            allowed_paths = [Path(allowed_dir)]
            allowed, reason, details = validate_directory_access(
                "read_file", broken_link, allowed_paths,
                allow_broken_symlinks=True  # Allow broken symlinks
            )

            # Should be allowed because allow_broken_symlinks=True
            assert allowed is True
            assert details.get("is_broken_symlink") is True
            assert details.get("broken_symlink_blocked") is not True

    def test_broken_symlink_chain_handled(self):
        """Chain with broken intermediate link should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a chain where intermediate is broken
            # link2 -> link1 -> non_existent
            non_existent = os.path.join(tmpdir, "non_existent.txt")
            link1 = os.path.join(tmpdir, "link1.txt")
            link2 = os.path.join(tmpdir, "link2.txt")

            os.symlink(non_existent, link1)  # Broken link
            os.symlink(link1, link2)  # Points to broken link

            resolved, was_symlink, is_broken = resolve_target_path(link2)

            assert was_symlink is True
            assert is_broken is True

    def test_broken_symlink_error_class_exists(self):
        """BrokenSymlinkError exception class should exist and work."""
        error = BrokenSymlinkError("/path/to/link", "/path/to/target")
        assert error.symlink_path == "/path/to/link"
        assert error.target_path == "/path/to/target"
        assert "broken symlink" in str(error).lower()

    def test_broken_symlink_error_without_target(self):
        """BrokenSymlinkError should work without target path."""
        error = BrokenSymlinkError("/path/to/link")
        assert error.symlink_path == "/path/to/link"
        assert error.target_path is None


# =============================================================================
# Step 5: Log symlink resolution in debug output
# =============================================================================

class TestStep5DebugLogging:
    """Feature #46, Step 5: Log symlink resolution in debug output"""

    def test_symlink_detection_logged(self, caplog):
        """Symlink detection should be logged at DEBUG level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target, symlink)

            with caplog.at_level(logging.DEBUG, logger="api.tool_policy"):
                resolve_target_path(symlink)

            # Check for symlink logging
            log_messages = [r.message for r in caplog.records]
            symlink_logs = [m for m in log_messages if "symlink" in m.lower()]
            assert len(symlink_logs) > 0, "Should log symlink detection"

    def test_broken_symlink_logged_as_warning(self, caplog):
        """Broken symlink should be logged at WARNING level in validate_directory_access."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            with caplog.at_level(logging.WARNING, logger="api.tool_policy"):
                validate_directory_access(
                    "read_file", broken_link, [Path(tmpdir)]
                )

            # Check for broken symlink warning
            log_messages = [r.message for r in caplog.records]
            broken_logs = [m for m in log_messages if "broken" in m.lower()]
            assert len(broken_logs) > 0, "Should log broken symlink warning"

    def test_symlink_resolution_details_logged(self, caplog):
        """Symlink resolution details should be logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target, symlink)

            with caplog.at_level(logging.DEBUG, logger="api.tool_policy"):
                validate_directory_access(
                    "read_file", symlink, [Path(tmpdir)]
                )

            # Check for detailed resolution logging
            log_messages = [r.message for r in caplog.records]
            resolved_logs = [m for m in log_messages if "resolved" in m.lower()]
            assert len(resolved_logs) > 0, "Should log symlink resolution"


# =============================================================================
# Integration Tests: ToolPolicyEnforcer with Symlinks
# =============================================================================

class TestToolPolicyEnforcerSymlinkIntegration:
    """Integration tests for ToolPolicyEnforcer with symlink validation."""

    def test_enforcer_blocks_symlink_to_forbidden_path(self):
        """Enforcer should block symlink that resolves outside sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup directories
            allowed_dir = os.path.join(tmpdir, "allowed")
            forbidden_dir = os.path.join(tmpdir, "forbidden")
            os.makedirs(allowed_dir)
            os.makedirs(forbidden_dir)

            # Create target in forbidden
            target = os.path.join(forbidden_dir, "secret.txt")
            with open(target, "w") as f:
                f.write("secret")

            # Create symlink in allowed pointing to forbidden
            symlink = os.path.join(allowed_dir, "link.txt")
            os.symlink(target, symlink)

            # Create enforcer with sandbox
            enforcer = ToolPolicyEnforcer.from_tool_policy(
                spec_id="test-spec",
                tool_policy={
                    "allowed_directories": [allowed_dir]
                }
            )

            # Should raise DirectoryAccessBlocked
            with pytest.raises(DirectoryAccessBlocked) as exc_info:
                enforcer.validate_tool_call("read_file", {"path": symlink})

            assert "not within allowed directories" in str(exc_info.value)

    def test_enforcer_allows_symlink_within_sandbox(self):
        """Enforcer should allow symlink that stays within sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target in same directory
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target, symlink)

            # Create enforcer with sandbox
            enforcer = ToolPolicyEnforcer.from_tool_policy(
                spec_id="test-spec",
                tool_policy={
                    "allowed_directories": [tmpdir]
                }
            )

            # Should not raise
            enforcer.validate_tool_call("read_file", {"path": symlink})

    def test_enforcer_blocks_broken_symlink(self):
        """Enforcer should block broken symlinks by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            enforcer = ToolPolicyEnforcer.from_tool_policy(
                spec_id="test-spec",
                tool_policy={
                    "allowed_directories": [tmpdir]
                }
            )

            with pytest.raises(DirectoryAccessBlocked) as exc_info:
                enforcer.validate_tool_call("read_file", {"path": broken_link})

            assert "broken symlink" in str(exc_info.value).lower()


# =============================================================================
# get_symlink_target() Tests
# =============================================================================

class TestGetSymlinkTarget:
    """Tests for get_symlink_target() helper function."""

    def test_get_target_of_symlink(self):
        """Should return the target of a symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink(target, symlink)

            result = get_symlink_target(Path(symlink))
            assert result == target

    def test_get_target_of_relative_symlink(self):
        """Should return relative target for relative symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            symlink = os.path.join(tmpdir, "link.txt")
            os.symlink("target.txt", symlink)  # Relative symlink

            result = get_symlink_target(Path(symlink))
            assert result == "target.txt"

    def test_get_target_regular_file_returns_none(self):
        """Should return None for regular file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            regular = os.path.join(tmpdir, "regular.txt")
            with open(regular, "w") as f:
                f.write("content")

            result = get_symlink_target(Path(regular))
            assert result is None

    def test_get_target_non_existent_returns_none(self):
        """Should return None for non-existent path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            result = get_symlink_target(Path(non_existent))
            assert result is None

    def test_get_target_broken_symlink_returns_target(self):
        """Should return target even for broken symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_link = os.path.join(tmpdir, "broken.txt")
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")
            os.symlink(non_existent, broken_link)

            result = get_symlink_target(Path(broken_link))
            # Should return the target path even though it doesn't exist
            assert result == non_existent


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for symlink validation."""

    def test_symlink_to_root_directory(self):
        """Symlink to root should be handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create symlink pointing to /tmp (always exists on Unix)
            symlink = os.path.join(tmpdir, "link_to_tmp")
            os.symlink("/tmp", symlink)

            # Sandbox only allows tmpdir
            allowed_paths = [Path(tmpdir)]
            allowed, reason, details = validate_directory_access(
                "read_file", symlink, allowed_paths
            )

            # Should be blocked - resolves to /tmp which is not in allowed
            assert allowed is False

    def test_self_referencing_symlink(self):
        """Self-referencing symlink should be handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create self-referencing symlink (link -> link)
            self_link = os.path.join(tmpdir, "self.txt")
            os.symlink(self_link, self_link)

            # This should not crash
            allowed_paths = [Path(tmpdir)]
            allowed, reason, details = validate_directory_access(
                "read_file", self_link, allowed_paths
            )

            # Should be detected as broken or error
            # The behavior depends on the OS - usually resolve() loops forever
            # so we use strict=False which returns the path anyway
            # The is_broken detection should catch this as a broken symlink
            assert details.get("is_broken_symlink") is True

    def test_symlink_with_special_characters_in_name(self):
        """Symlink with special characters should be handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            # Create symlink with spaces and special chars
            symlink = os.path.join(tmpdir, "my link (1).txt")
            os.symlink(target, symlink)

            resolved, was_symlink, is_broken = resolve_target_path(symlink)

            assert was_symlink is True
            assert is_broken is False
            assert str(resolved) == target

    def test_deeply_nested_symlink_chain(self):
        """Deeply nested symlink chain should be resolved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create target
            target = os.path.join(tmpdir, "target.txt")
            with open(target, "w") as f:
                f.write("content")

            # Create deep chain: link10 -> link9 -> ... -> link1 -> target
            prev = target
            for i in range(1, 11):
                link = os.path.join(tmpdir, f"link{i}.txt")
                os.symlink(prev, link)
                prev = link

            resolved, was_symlink, is_broken = resolve_target_path(prev)

            assert was_symlink is True
            assert is_broken is False
            assert str(resolved) == target


# =============================================================================
# Regression Tests
# =============================================================================

class TestRegressions:
    """Regression tests to ensure existing functionality still works."""

    def test_regular_file_access_still_works(self):
        """Regular file access should still work after symlink changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            regular = os.path.join(tmpdir, "regular.txt")
            with open(regular, "w") as f:
                f.write("content")

            allowed_paths = [Path(tmpdir)]
            allowed, reason, details = validate_directory_access(
                "read_file", regular, allowed_paths
            )

            assert allowed is True
            assert reason is None
            assert details.get("was_symlink") is False
            assert details.get("is_broken_symlink") is False

    def test_path_traversal_still_blocked(self):
        """Path traversal should still be blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_paths = [Path(tmpdir)]
            allowed, reason, details = validate_directory_access(
                "read_file", "../../../etc/passwd", allowed_paths, base_dir=tmpdir
            )

            assert allowed is False
            assert "traversal" in reason.lower()

    def test_non_existent_file_still_validated(self):
        """Non-existent file should still be validated against sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent = os.path.join(tmpdir, "does_not_exist.txt")

            allowed_paths = [Path(tmpdir)]
            allowed, reason, details = validate_directory_access(
                "read_file", non_existent, allowed_paths
            )

            # Should be allowed (path is within sandbox even if doesn't exist)
            assert allowed is True

    def test_resolve_target_path_returns_tuple(self):
        """resolve_target_path should return a 3-tuple now (not 2-tuple)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            with open(file_path, "w") as f:
                f.write("content")

            result = resolve_target_path(file_path)

            # Should be a 3-tuple: (path, was_symlink, is_broken)
            assert isinstance(result, tuple)
            assert len(result) == 3

            resolved, was_symlink, is_broken = result
            assert isinstance(resolved, Path)
            assert isinstance(was_symlink, bool)
            assert isinstance(is_broken, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
