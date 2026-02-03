"""
Feature #204: Scaffolding respects .gitignore patterns

This test suite verifies that the scaffolding module correctly manages .gitignore
patterns for Claude Code generated files.

Feature Steps:
1. Check if .gitignore exists
2. Add .claude/agents/generated/ to .gitignore if not present
3. Keep .claude/agents/manual/ tracked
4. Keep CLAUDE.md tracked
5. Preserve existing .gitignore content
"""
import tempfile
from pathlib import Path

import pytest

from api.scaffolding import (
    # Feature #204 exports
    GitignoreUpdateResult,
    gitignore_exists,
    update_gitignore,
    ensure_gitignore_patterns,
    verify_gitignore_patterns,
    scaffold_with_gitignore,
    # Constants
    GITIGNORE_FILE,
    GITIGNORE_GENERATED_PATTERNS,
    GITIGNORE_TRACKED_PATTERNS,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_project_with_gitignore(temp_project_dir):
    """Create a temporary project with an existing .gitignore."""
    gitignore_path = temp_project_dir / ".gitignore"
    gitignore_path.write_text("# Existing content\nnode_modules/\n*.pyc\n")
    return temp_project_dir


# =============================================================================
# Test Step 1: Check if .gitignore exists
# =============================================================================

class TestStep1GitignoreExists:
    """Test Step 1: Check if .gitignore exists."""

    def test_gitignore_exists_returns_false_when_missing(self, temp_project_dir):
        """.gitignore existence check returns False when file is missing."""
        assert gitignore_exists(temp_project_dir) is False

    def test_gitignore_exists_returns_true_when_present(self, temp_project_with_gitignore):
        """.gitignore existence check returns True when file exists."""
        assert gitignore_exists(temp_project_with_gitignore) is True

    def test_gitignore_constant_is_correct(self):
        """GITIGNORE_FILE constant has correct value."""
        assert GITIGNORE_FILE == ".gitignore"

    def test_update_gitignore_reports_existed_status(self, temp_project_with_gitignore):
        """update_gitignore reports whether .gitignore existed."""
        result = update_gitignore(temp_project_with_gitignore)
        assert result.existed is True

    def test_update_gitignore_reports_not_existed(self, temp_project_dir):
        """update_gitignore reports when .gitignore didn't exist."""
        result = update_gitignore(temp_project_dir)
        assert result.existed is False


# =============================================================================
# Test Step 2: Add .claude/agents/generated/ to .gitignore if not present
# =============================================================================

class TestStep2AddGeneratedPattern:
    """Test Step 2: Add .claude/agents/generated/ to .gitignore if not present."""

    def test_adds_generated_pattern_when_missing(self, temp_project_dir):
        """.claude/agents/generated/ is added when not in .gitignore."""
        result = update_gitignore(temp_project_dir)

        assert result.error is None
        assert ".claude/agents/generated/" in result.patterns_added

        # Verify it's actually in the file
        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content

    def test_does_not_add_if_already_present(self, temp_project_dir):
        """Pattern is not added if already present in .gitignore."""
        # Pre-create .gitignore with the pattern
        gitignore_path = temp_project_dir / ".gitignore"
        gitignore_path.write_text(".claude/agents/generated/\n")

        result = update_gitignore(temp_project_dir)

        assert ".claude/agents/generated/" in result.patterns_already_present
        assert ".claude/agents/generated/" not in result.patterns_added

    def test_handles_pattern_without_trailing_slash(self, temp_project_dir):
        """Detects pattern even without trailing slash."""
        gitignore_path = temp_project_dir / ".gitignore"
        gitignore_path.write_text(".claude/agents/generated\n")  # No trailing slash

        result = update_gitignore(temp_project_dir)

        # Should recognize as already present
        assert ".claude/agents/generated/" in result.patterns_already_present

    def test_creates_gitignore_if_missing(self, temp_project_dir):
        """.gitignore is created if it doesn't exist."""
        assert not (temp_project_dir / ".gitignore").exists()

        result = update_gitignore(temp_project_dir)

        assert result.created is True
        assert (temp_project_dir / ".gitignore").exists()

    def test_respects_create_if_missing_flag(self, temp_project_dir):
        """Does not create .gitignore when create_if_missing=False."""
        result = update_gitignore(temp_project_dir, create_if_missing=False)

        assert result.error is not None
        assert ".gitignore does not exist" in result.error
        assert not (temp_project_dir / ".gitignore").exists()

    def test_generated_patterns_constant(self):
        """GITIGNORE_GENERATED_PATTERNS contains expected pattern."""
        assert ".claude/agents/generated/" in GITIGNORE_GENERATED_PATTERNS


# =============================================================================
# Test Step 3: Keep .claude/agents/manual/ tracked
# =============================================================================

class TestStep3ManualDirectoryTracked:
    """Test Step 3: Keep .claude/agents/manual/ tracked."""

    def test_manual_directory_not_in_generated_patterns(self):
        """.claude/agents/manual/ is not in GITIGNORE_GENERATED_PATTERNS."""
        assert ".claude/agents/manual/" not in GITIGNORE_GENERATED_PATTERNS

    def test_manual_directory_in_tracked_patterns(self):
        """.claude/agents/manual/ is in GITIGNORE_TRACKED_PATTERNS."""
        assert ".claude/agents/manual/" in GITIGNORE_TRACKED_PATTERNS

    def test_update_gitignore_does_not_add_manual_directory(self, temp_project_dir):
        """update_gitignore does not add .claude/agents/manual/ to .gitignore."""
        result = update_gitignore(temp_project_dir)

        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/manual/" not in content

    def test_custom_patterns_skips_tracked_patterns(self, temp_project_dir):
        """Custom patterns that are in TRACKED_PATTERNS are skipped."""
        # Try to add a tracked pattern
        result = update_gitignore(
            temp_project_dir,
            patterns=[".claude/agents/manual/"],
        )

        # Should not be added
        assert ".claude/agents/manual/" not in result.patterns_added


# =============================================================================
# Test Step 4: Keep CLAUDE.md tracked
# =============================================================================

class TestStep4ClaudeMdTracked:
    """Test Step 4: Keep CLAUDE.md tracked."""

    def test_claude_md_not_in_generated_patterns(self):
        """CLAUDE.md is not in GITIGNORE_GENERATED_PATTERNS."""
        assert "CLAUDE.md" not in GITIGNORE_GENERATED_PATTERNS

    def test_claude_md_in_tracked_patterns(self):
        """CLAUDE.md is in GITIGNORE_TRACKED_PATTERNS."""
        assert "CLAUDE.md" in GITIGNORE_TRACKED_PATTERNS

    def test_update_gitignore_does_not_add_claude_md(self, temp_project_dir):
        """update_gitignore does not add CLAUDE.md to .gitignore."""
        result = update_gitignore(temp_project_dir)

        content = (temp_project_dir / ".gitignore").read_text()
        assert "CLAUDE.md" not in content

    def test_custom_patterns_skips_claude_md(self, temp_project_dir):
        """Custom patterns that include CLAUDE.md are skipped."""
        result = update_gitignore(
            temp_project_dir,
            patterns=["CLAUDE.md"],
        )

        # Should not be added
        assert "CLAUDE.md" not in result.patterns_added


# =============================================================================
# Test Step 5: Preserve existing .gitignore content
# =============================================================================

class TestStep5PreserveExistingContent:
    """Test Step 5: Preserve existing .gitignore content."""

    def test_preserves_existing_patterns(self, temp_project_dir):
        """Existing patterns in .gitignore are preserved."""
        gitignore_path = temp_project_dir / ".gitignore"
        original_content = "# My project\nnode_modules/\n*.pyc\nbuild/\n"
        gitignore_path.write_text(original_content)

        result = update_gitignore(temp_project_dir)

        content = gitignore_path.read_text()
        assert "node_modules/" in content
        assert "*.pyc" in content
        assert "build/" in content

    def test_preserves_comments(self, temp_project_dir):
        """Comments in .gitignore are preserved."""
        gitignore_path = temp_project_dir / ".gitignore"
        gitignore_path.write_text("# Important comment\nnode_modules/\n")

        update_gitignore(temp_project_dir)

        content = gitignore_path.read_text()
        assert "# Important comment" in content

    def test_preserves_empty_lines(self, temp_project_dir):
        """Empty lines in .gitignore are preserved."""
        gitignore_path = temp_project_dir / ".gitignore"
        original = "node_modules/\n\nbuild/\n"
        gitignore_path.write_text(original)

        update_gitignore(temp_project_dir)

        content = gitignore_path.read_text()
        # Original content should be preserved at the start
        assert content.startswith(original) or original.rstrip() in content

    def test_result_contains_original_content(self, temp_project_dir):
        """GitignoreUpdateResult contains original content."""
        gitignore_path = temp_project_dir / ".gitignore"
        original = "existing_pattern/\n"
        gitignore_path.write_text(original)

        result = update_gitignore(temp_project_dir)

        assert result.original_content == original

    def test_adds_header_comment(self, temp_project_dir):
        """Header comment is added before new patterns."""
        result = update_gitignore(temp_project_dir, add_header_comment=True)

        content = (temp_project_dir / ".gitignore").read_text()
        assert "# Claude Code generated files" in content

    def test_no_header_comment_when_disabled(self, temp_project_dir):
        """No header comment when add_header_comment=False."""
        result = update_gitignore(temp_project_dir, add_header_comment=False)

        content = (temp_project_dir / ".gitignore").read_text()
        assert "# Claude Code generated files" not in content


# =============================================================================
# Test GitignoreUpdateResult dataclass
# =============================================================================

class TestGitignoreUpdateResult:
    """Test GitignoreUpdateResult dataclass."""

    def test_result_has_path(self, temp_project_dir):
        """Result contains the path to .gitignore."""
        result = update_gitignore(temp_project_dir)
        assert result.path == temp_project_dir / ".gitignore"

    def test_result_to_dict(self, temp_project_dir):
        """Result can be converted to dictionary."""
        result = update_gitignore(temp_project_dir)
        d = result.to_dict()

        assert "path" in d
        assert "existed" in d
        assert "created" in d
        assert "modified" in d
        assert "patterns_added" in d
        assert "patterns_already_present" in d
        assert "error" in d

    def test_result_modified_vs_created(self, temp_project_dir):
        """Result correctly reports modified vs created."""
        # First call creates
        result1 = update_gitignore(temp_project_dir)
        assert result1.created is True
        assert result1.modified is False

        # Add a new pattern to trigger modification
        result2 = update_gitignore(
            temp_project_dir,
            patterns=["custom_pattern/"],
        )
        # Should modify existing, not create new
        assert result2.created is False
        assert result2.modified is True


# =============================================================================
# Test verify_gitignore_patterns
# =============================================================================

class TestVerifyGitignorePatterns:
    """Test verify_gitignore_patterns function."""

    def test_returns_all_false_when_no_gitignore(self, temp_project_dir):
        """All patterns False when .gitignore doesn't exist."""
        result = verify_gitignore_patterns(temp_project_dir)

        for pattern in GITIGNORE_GENERATED_PATTERNS:
            assert result[pattern] is False

    def test_returns_true_for_present_patterns(self, temp_project_dir):
        """Returns True for patterns that are present."""
        gitignore_path = temp_project_dir / ".gitignore"
        gitignore_path.write_text(".claude/agents/generated/\n")

        result = verify_gitignore_patterns(temp_project_dir)

        assert result[".claude/agents/generated/"] is True


# =============================================================================
# Test ensure_gitignore_patterns
# =============================================================================

class TestEnsureGitignorePatterns:
    """Test ensure_gitignore_patterns convenience function."""

    def test_creates_gitignore_with_patterns(self, temp_project_dir):
        """Creates .gitignore with standard patterns."""
        result = ensure_gitignore_patterns(temp_project_dir)

        assert result.error is None
        assert (temp_project_dir / ".gitignore").exists()

        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content

    def test_preserves_existing_and_adds_missing(self, temp_project_with_gitignore):
        """Preserves existing content and adds missing patterns."""
        result = ensure_gitignore_patterns(temp_project_with_gitignore)

        content = (temp_project_with_gitignore / ".gitignore").read_text()
        # Original content preserved
        assert "node_modules/" in content
        assert "*.pyc" in content
        # New pattern added
        assert ".claude/agents/generated/" in content


# =============================================================================
# Test scaffold_with_gitignore
# =============================================================================

class TestScaffoldWithGitignore:
    """Test scaffold_with_gitignore function."""

    def test_creates_all_components(self, temp_project_dir):
        """Creates .claude structure, CLAUDE.md, and updates .gitignore."""
        scaffold_result, claude_md_result, gitignore_result = scaffold_with_gitignore(
            temp_project_dir
        )

        # .claude directory created
        assert scaffold_result.success is True
        assert (temp_project_dir / ".claude").is_dir()

        # CLAUDE.md created
        assert claude_md_result is not None
        assert (temp_project_dir / "CLAUDE.md").exists()

        # .gitignore updated
        assert gitignore_result is not None
        assert gitignore_result.error is None
        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content

    def test_can_skip_gitignore_update(self, temp_project_dir):
        """Can skip .gitignore update with flag."""
        scaffold_result, claude_md_result, gitignore_result = scaffold_with_gitignore(
            temp_project_dir,
            update_gitignore_file=False,
        )

        assert gitignore_result is None
        assert not (temp_project_dir / ".gitignore").exists()

    def test_can_skip_claude_md(self, temp_project_dir):
        """Can skip CLAUDE.md with flag."""
        scaffold_result, claude_md_result, gitignore_result = scaffold_with_gitignore(
            temp_project_dir,
            include_claude_md=False,
        )

        assert claude_md_result is None
        # But .gitignore should still be updated
        assert gitignore_result is not None


# =============================================================================
# Test Integration: Full scaffolding workflow
# =============================================================================

class TestIntegration:
    """Integration tests for the full scaffolding + gitignore workflow."""

    def test_full_scaffolding_workflow(self, temp_project_dir):
        """Complete scaffolding creates proper structure with gitignore."""
        # Run full scaffolding
        scaffold_result, claude_md_result, gitignore_result = scaffold_with_gitignore(
            temp_project_dir
        )

        # Verify .claude structure
        assert (temp_project_dir / ".claude").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "manual").is_dir()

        # Verify CLAUDE.md
        assert (temp_project_dir / "CLAUDE.md").exists()

        # Verify .gitignore
        gitignore_content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in gitignore_content
        # Should NOT contain tracked patterns
        assert ".claude/agents/manual/" not in gitignore_content
        assert "CLAUDE.md" not in gitignore_content

    def test_idempotent_gitignore_update(self, temp_project_dir):
        """Running update_gitignore multiple times is safe."""
        # First run
        result1 = ensure_gitignore_patterns(temp_project_dir)
        content1 = (temp_project_dir / ".gitignore").read_text()

        # Second run
        result2 = ensure_gitignore_patterns(temp_project_dir)
        content2 = (temp_project_dir / ".gitignore").read_text()

        # Pattern should only appear once
        assert content1 == content2
        assert content1.count(".claude/agents/generated/") == 1


# =============================================================================
# Test Feature #204 Verification Steps
# =============================================================================

class TestFeature204VerificationSteps:
    """
    Verify all 5 steps of Feature #204.

    Feature: Scaffolding respects .gitignore patterns
    Steps:
    1. Check if .gitignore exists
    2. Add .claude/agents/generated/ to .gitignore if not present
    3. Keep .claude/agents/manual/ tracked
    4. Keep CLAUDE.md tracked
    5. Preserve existing .gitignore content
    """

    def test_step1_check_gitignore_exists(self, temp_project_dir):
        """Step 1: Check if .gitignore exists."""
        # Before creating
        assert gitignore_exists(temp_project_dir) is False

        # Create it
        (temp_project_dir / ".gitignore").write_text("")

        # After creating
        assert gitignore_exists(temp_project_dir) is True

    def test_step2_add_generated_pattern(self, temp_project_dir):
        """Step 2: Add .claude/agents/generated/ to .gitignore if not present."""
        result = update_gitignore(temp_project_dir)

        assert ".claude/agents/generated/" in result.patterns_added
        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content

    def test_step3_keep_manual_tracked(self, temp_project_dir):
        """Step 3: Keep .claude/agents/manual/ tracked."""
        result = update_gitignore(temp_project_dir)

        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/manual/" not in content
        # Verify it's in the tracked set
        assert ".claude/agents/manual/" in GITIGNORE_TRACKED_PATTERNS

    def test_step4_keep_claude_md_tracked(self, temp_project_dir):
        """Step 4: Keep CLAUDE.md tracked."""
        result = update_gitignore(temp_project_dir)

        content = (temp_project_dir / ".gitignore").read_text()
        assert "CLAUDE.md" not in content
        # Verify it's in the tracked set
        assert "CLAUDE.md" in GITIGNORE_TRACKED_PATTERNS

    def test_step5_preserve_existing_content(self, temp_project_dir):
        """Step 5: Preserve existing .gitignore content."""
        gitignore_path = temp_project_dir / ".gitignore"
        original_content = """# Project specific ignores
node_modules/
*.pyc
build/
.env
"""
        gitignore_path.write_text(original_content)

        result = update_gitignore(temp_project_dir)

        final_content = gitignore_path.read_text()
        # All original patterns preserved
        assert "node_modules/" in final_content
        assert "*.pyc" in final_content
        assert "build/" in final_content
        assert ".env" in final_content
        assert "# Project specific ignores" in final_content


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_empty_gitignore(self, temp_project_dir):
        """Handles empty .gitignore file."""
        (temp_project_dir / ".gitignore").write_text("")

        result = update_gitignore(temp_project_dir)

        assert result.error is None
        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content

    def test_handles_gitignore_no_trailing_newline(self, temp_project_dir):
        """Handles .gitignore without trailing newline."""
        (temp_project_dir / ".gitignore").write_text("node_modules/")  # No newline

        result = update_gitignore(temp_project_dir)

        content = (temp_project_dir / ".gitignore").read_text()
        # Should have proper line separation
        assert "node_modules/\n" in content

    def test_handles_whitespace_only_lines(self, temp_project_dir):
        """Handles .gitignore with whitespace-only lines."""
        (temp_project_dir / ".gitignore").write_text("node_modules/\n   \n*.pyc\n")

        result = update_gitignore(temp_project_dir)

        assert result.error is None
        content = (temp_project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content

    def test_custom_patterns_can_be_added(self, temp_project_dir):
        """Custom patterns can be added."""
        result = update_gitignore(
            temp_project_dir,
            patterns=["custom_dir/", "*.log"],
        )

        content = (temp_project_dir / ".gitignore").read_text()
        assert "custom_dir/" in content
        assert "*.log" in content


# =============================================================================
# Test API Package Exports
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #204 exports are available from api package."""

    def test_gitignore_update_result_exported(self):
        """GitignoreUpdateResult is exported from api package."""
        from api import GitignoreUpdateResult
        assert GitignoreUpdateResult is not None

    def test_gitignore_exists_exported(self):
        """gitignore_exists is exported from api package."""
        from api import gitignore_exists
        assert callable(gitignore_exists)

    def test_update_gitignore_exported(self):
        """update_gitignore is exported from api package."""
        from api import update_gitignore
        assert callable(update_gitignore)

    def test_ensure_gitignore_patterns_exported(self):
        """ensure_gitignore_patterns is exported from api package."""
        from api import ensure_gitignore_patterns
        assert callable(ensure_gitignore_patterns)

    def test_verify_gitignore_patterns_exported(self):
        """verify_gitignore_patterns is exported from api package."""
        from api import verify_gitignore_patterns
        assert callable(verify_gitignore_patterns)

    def test_scaffold_with_gitignore_exported(self):
        """scaffold_with_gitignore is exported from api package."""
        from api import scaffold_with_gitignore
        assert callable(scaffold_with_gitignore)

    def test_constants_exported(self):
        """Constants are exported from api package."""
        from api import (
            GITIGNORE_FILE,
            GITIGNORE_GENERATED_PATTERNS,
            GITIGNORE_TRACKED_PATTERNS,
        )
        assert GITIGNORE_FILE == ".gitignore"
        assert ".claude/agents/generated/" in GITIGNORE_GENERATED_PATTERNS
        assert ".claude/agents/manual/" in GITIGNORE_TRACKED_PATTERNS
