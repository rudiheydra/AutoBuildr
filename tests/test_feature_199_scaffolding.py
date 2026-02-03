"""
Feature #199: .claude directory scaffolding creates standard structure

This test suite verifies that the scaffolding module correctly creates
the standard .claude directory structure in project repositories.

Feature Steps:
1. Create .claude/ root directory if missing
2. Create .claude/agents/generated/ subdirectory
3. Create .claude/agents/manual/ subdirectory (empty)
4. Create .claude/skills/ subdirectory (empty, Phase 2)
5. Create .claude/commands/ subdirectory (empty, Phase 2)
"""
import os
import stat
import tempfile
from pathlib import Path

import pytest

from api.scaffolding import (
    # Data classes
    DirectoryStatus,
    ScaffoldResult,
    ScaffoldPreview,
    # Main class
    ClaudeDirectoryScaffold,
    # Convenience functions
    scaffold_claude_directory,
    preview_claude_directory,
    ensure_claude_root,
    ensure_agents_generated,
    verify_claude_structure,
    is_claude_scaffolded,
    get_standard_subdirs,
    # Constants
    CLAUDE_ROOT_DIR,
    STANDARD_SUBDIRS,
    DEFAULT_DIR_PERMISSIONS,
    PHASE_1_DIRS,
    PHASE_2_DIRS,
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
def scaffolder(temp_project_dir):
    """Create a ClaudeDirectoryScaffold instance for testing."""
    return ClaudeDirectoryScaffold(temp_project_dir)


# =============================================================================
# Test Step 1: Create .claude/ root directory if missing
# =============================================================================

class TestStep1CreateClaudeRoot:
    """Test Step 1: Create .claude/ root directory if missing."""

    def test_creates_claude_root_when_missing(self, temp_project_dir):
        """Root .claude/ directory is created when it doesn't exist."""
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert (temp_project_dir / ".claude").is_dir()

    def test_root_has_correct_permissions(self, temp_project_dir):
        """Root directory has correct permissions (0755)."""
        scaffold_claude_directory(temp_project_dir)

        root_dir = temp_project_dir / ".claude"
        mode = root_dir.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_preserves_existing_root_directory(self, temp_project_dir):
        """Existing .claude/ directory is not destroyed."""
        # Pre-create the directory with a marker file
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir()
        marker_file = claude_dir / "existing_marker.txt"
        marker_file.write_text("do not delete me")

        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert marker_file.exists()
        assert marker_file.read_text() == "do not delete me"

    def test_reports_root_as_existed(self, temp_project_dir):
        """When root exists, it's reported as existed (not created)."""
        (temp_project_dir / ".claude").mkdir()

        result = scaffold_claude_directory(temp_project_dir)

        root_status = next(
            d for d in result.directories if d.relative_path == CLAUDE_ROOT_DIR
        )
        assert root_status.existed is True
        assert root_status.created is False

    def test_reports_root_as_created(self, temp_project_dir):
        """When root doesn't exist, it's reported as created."""
        result = scaffold_claude_directory(temp_project_dir)

        root_status = next(
            d for d in result.directories if d.relative_path == CLAUDE_ROOT_DIR
        )
        assert root_status.created is True
        assert root_status.existed is False


# =============================================================================
# Test Step 2: Create .claude/agents/generated/ subdirectory
# =============================================================================

class TestStep2CreateAgentsGenerated:
    """Test Step 2: Create .claude/agents/generated/ subdirectory."""

    def test_creates_agents_generated_directory(self, temp_project_dir):
        """Creates .claude/agents/generated/ directory."""
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()

    def test_agents_generated_has_correct_permissions(self, temp_project_dir):
        """agents/generated/ has correct permissions."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "agents" / "generated"
        mode = path.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_creates_intermediate_agents_directory(self, temp_project_dir):
        """Also creates the intermediate agents/ directory."""
        scaffold_claude_directory(temp_project_dir)

        assert (temp_project_dir / ".claude" / "agents").is_dir()

    def test_reports_agents_generated_status(self, temp_project_dir):
        """Status includes agents/generated directory."""
        result = scaffold_claude_directory(temp_project_dir)

        agents_generated_status = next(
            d for d in result.directories if d.relative_path == "agents/generated"
        )
        assert agents_generated_status is not None
        assert agents_generated_status.created is True

    def test_preserves_existing_generated_content(self, temp_project_dir):
        """Existing content in agents/generated/ is preserved."""
        agents_gen = temp_project_dir / ".claude" / "agents" / "generated"
        agents_gen.mkdir(parents=True)
        existing_file = agents_gen / "my-agent.md"
        existing_file.write_text("# My Agent")

        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert existing_file.exists()
        assert existing_file.read_text() == "# My Agent"


# =============================================================================
# Test Step 3: Create .claude/agents/manual/ subdirectory
# =============================================================================

class TestStep3CreateAgentsManual:
    """Test Step 3: Create .claude/agents/manual/ subdirectory (empty)."""

    def test_creates_agents_manual_directory(self, temp_project_dir):
        """Creates .claude/agents/manual/ directory."""
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert (temp_project_dir / ".claude" / "agents" / "manual").is_dir()

    def test_agents_manual_is_empty(self, temp_project_dir):
        """agents/manual/ directory is initially empty."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "agents" / "manual"
        contents = list(path.iterdir())
        assert len(contents) == 0

    def test_agents_manual_has_correct_permissions(self, temp_project_dir):
        """agents/manual/ has correct permissions."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "agents" / "manual"
        mode = path.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_reports_agents_manual_status(self, temp_project_dir):
        """Status includes agents/manual directory."""
        result = scaffold_claude_directory(temp_project_dir)

        agents_manual_status = next(
            d for d in result.directories if d.relative_path == "agents/manual"
        )
        assert agents_manual_status is not None
        assert agents_manual_status.created is True

    def test_agents_manual_is_phase_1(self, temp_project_dir):
        """agents/manual is part of Phase 1."""
        result = scaffold_claude_directory(temp_project_dir)

        agents_manual_status = next(
            d for d in result.directories if d.relative_path == "agents/manual"
        )
        assert agents_manual_status.phase == 1


# =============================================================================
# Test Step 4: Create .claude/skills/ subdirectory (Phase 2)
# =============================================================================

class TestStep4CreateSkills:
    """Test Step 4: Create .claude/skills/ subdirectory (empty, Phase 2)."""

    def test_creates_skills_directory(self, temp_project_dir):
        """Creates .claude/skills/ directory."""
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert (temp_project_dir / ".claude" / "skills").is_dir()

    def test_skills_is_empty(self, temp_project_dir):
        """skills/ directory is initially empty."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "skills"
        contents = list(path.iterdir())
        assert len(contents) == 0

    def test_skills_has_correct_permissions(self, temp_project_dir):
        """skills/ has correct permissions."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "skills"
        mode = path.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_skills_is_phase_2(self, temp_project_dir):
        """skills is part of Phase 2."""
        result = scaffold_claude_directory(temp_project_dir)

        skills_status = next(
            d for d in result.directories if d.relative_path == "skills"
        )
        assert skills_status.phase == 2

    def test_skills_excluded_when_phase2_disabled(self, temp_project_dir):
        """skills/ is not created when include_phase2=False."""
        result = scaffold_claude_directory(temp_project_dir, include_phase2=False)

        assert result.success
        assert not (temp_project_dir / ".claude" / "skills").exists()


# =============================================================================
# Test Step 5: Create .claude/commands/ subdirectory (Phase 2)
# =============================================================================

class TestStep5CreateCommands:
    """Test Step 5: Create .claude/commands/ subdirectory (empty, Phase 2)."""

    def test_creates_commands_directory(self, temp_project_dir):
        """Creates .claude/commands/ directory."""
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert (temp_project_dir / ".claude" / "commands").is_dir()

    def test_commands_is_empty(self, temp_project_dir):
        """commands/ directory is initially empty."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "commands"
        contents = list(path.iterdir())
        assert len(contents) == 0

    def test_commands_has_correct_permissions(self, temp_project_dir):
        """commands/ has correct permissions."""
        scaffold_claude_directory(temp_project_dir)

        path = temp_project_dir / ".claude" / "commands"
        mode = path.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_commands_is_phase_2(self, temp_project_dir):
        """commands is part of Phase 2."""
        result = scaffold_claude_directory(temp_project_dir)

        commands_status = next(
            d for d in result.directories if d.relative_path == "commands"
        )
        assert commands_status.phase == 2

    def test_commands_excluded_when_phase2_disabled(self, temp_project_dir):
        """commands/ is not created when include_phase2=False."""
        result = scaffold_claude_directory(temp_project_dir, include_phase2=False)

        assert result.success
        assert not (temp_project_dir / ".claude" / "commands").exists()


# =============================================================================
# Test ScaffoldResult Data Class
# =============================================================================

class TestScaffoldResult:
    """Test ScaffoldResult data class."""

    def test_success_is_true_when_all_directories_created(self, temp_project_dir):
        """success is True when all directories are created successfully."""
        result = scaffold_claude_directory(temp_project_dir)
        assert result.success is True

    def test_directories_created_count(self, temp_project_dir):
        """directories_created counts how many were newly created."""
        result = scaffold_claude_directory(temp_project_dir)
        # Should create: .claude, agents/generated, agents/manual, skills, commands
        assert result.directories_created == 5

    def test_directories_existed_count(self, temp_project_dir):
        """directories_existed counts how many already existed."""
        # Pre-create everything
        for subdir in ["", "agents/generated", "agents/manual", "skills", "commands"]:
            (temp_project_dir / ".claude" / subdir).mkdir(parents=True, exist_ok=True)

        result = scaffold_claude_directory(temp_project_dir)
        assert result.directories_existed == 5
        assert result.directories_created == 0

    def test_get_created_paths(self, temp_project_dir):
        """get_created_paths() returns paths that were created."""
        result = scaffold_claude_directory(temp_project_dir)
        created = result.get_created_paths()
        assert len(created) == 5
        assert all(isinstance(p, Path) for p in created)

    def test_get_existing_paths(self, temp_project_dir):
        """get_existing_paths() returns paths that already existed."""
        # Pre-create root
        (temp_project_dir / ".claude").mkdir()

        result = scaffold_claude_directory(temp_project_dir)
        existing = result.get_existing_paths()
        assert len(existing) == 1
        assert existing[0] == temp_project_dir / ".claude"

    def test_to_dict_serialization(self, temp_project_dir):
        """to_dict() produces valid serializable output."""
        result = scaffold_claude_directory(temp_project_dir)
        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["success"] is True
        assert isinstance(data["project_dir"], str)
        assert isinstance(data["claude_root"], str)
        assert isinstance(data["directories"], list)


# =============================================================================
# Test DirectoryStatus Data Class
# =============================================================================

class TestDirectoryStatus:
    """Test DirectoryStatus data class."""

    def test_directory_status_attributes(self, temp_project_dir):
        """DirectoryStatus has expected attributes."""
        result = scaffold_claude_directory(temp_project_dir)
        status = result.directories[0]

        assert hasattr(status, "path")
        assert hasattr(status, "relative_path")
        assert hasattr(status, "existed")
        assert hasattr(status, "created")
        assert hasattr(status, "error")
        assert hasattr(status, "phase")

    def test_directory_status_to_dict(self, temp_project_dir):
        """DirectoryStatus.to_dict() produces valid output."""
        result = scaffold_claude_directory(temp_project_dir)
        status = result.directories[0]
        data = status.to_dict()

        assert isinstance(data, dict)
        assert "path" in data
        assert "relative_path" in data
        assert "existed" in data
        assert "created" in data


# =============================================================================
# Test ScaffoldPreview
# =============================================================================

class TestScaffoldPreview:
    """Test preview functionality."""

    def test_preview_shows_directories_to_create(self, temp_project_dir):
        """Preview shows which directories would be created."""
        preview = preview_claude_directory(temp_project_dir)

        assert ".claude" in preview.to_create
        assert ".claude/agents/generated" in preview.to_create

    def test_preview_shows_existing_directories(self, temp_project_dir):
        """Preview shows which directories already exist."""
        (temp_project_dir / ".claude").mkdir()

        preview = preview_claude_directory(temp_project_dir)

        assert ".claude" in preview.already_exist
        assert ".claude/agents/generated" in preview.to_create

    def test_preview_does_not_create_anything(self, temp_project_dir):
        """Preview is a dry run - doesn't create directories."""
        preview = preview_claude_directory(temp_project_dir)

        # Nothing should have been created
        assert not (temp_project_dir / ".claude").exists()
        assert len(preview.to_create) > 0

    def test_preview_to_dict(self, temp_project_dir):
        """Preview.to_dict() produces valid output."""
        preview = preview_claude_directory(temp_project_dir)
        data = preview.to_dict()

        assert isinstance(data, dict)
        assert "to_create" in data
        assert "already_exist" in data
        assert "structure" in data


# =============================================================================
# Test ClaudeDirectoryScaffold Class
# =============================================================================

class TestClaudeDirectoryScaffold:
    """Test ClaudeDirectoryScaffold class."""

    def test_claude_root_property(self, temp_project_dir):
        """claude_root property returns correct path."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)
        assert scaffold.claude_root == temp_project_dir / ".claude"

    def test_get_subdirs_includes_all_by_default(self, temp_project_dir):
        """get_subdirs() returns all subdirectories by default."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)
        subdirs = scaffold.get_subdirs()

        assert "agents/generated" in subdirs
        assert "agents/manual" in subdirs
        assert "skills" in subdirs
        assert "commands" in subdirs

    def test_get_subdirs_excludes_phase2_when_disabled(self, temp_project_dir):
        """get_subdirs() excludes Phase 2 when disabled."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir, include_phase2=False)
        subdirs = scaffold.get_subdirs()

        assert "agents/generated" in subdirs
        assert "agents/manual" in subdirs
        assert "skills" not in subdirs
        assert "commands" not in subdirs

    def test_verify_structure_returns_status(self, temp_project_dir):
        """verify_structure() returns status of each directory."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)
        scaffold.create_structure()

        status = scaffold.verify_structure()

        assert status[".claude"] is True
        assert status[".claude/agents/generated"] is True
        assert status[".claude/agents/manual"] is True

    def test_is_scaffolded_returns_true_when_complete(self, temp_project_dir):
        """is_scaffolded() returns True when structure is complete."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)
        scaffold.create_structure()

        assert scaffold.is_scaffolded() is True

    def test_is_scaffolded_returns_false_when_incomplete(self, temp_project_dir):
        """is_scaffolded() returns False when structure is incomplete."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)

        assert scaffold.is_scaffolded() is False

    def test_ensure_root_exists_creates_only_root(self, temp_project_dir):
        """ensure_root_exists() creates only the root directory."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)
        scaffold.ensure_root_exists()

        assert (temp_project_dir / ".claude").is_dir()
        assert not (temp_project_dir / ".claude" / "agents").exists()

    def test_ensure_agents_generated_creates_path(self, temp_project_dir):
        """ensure_agents_generated() creates agents/generated directory."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)
        scaffold.ensure_agents_generated_exists()

        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()


# =============================================================================
# Test Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_scaffold_claude_directory(self, temp_project_dir):
        """scaffold_claude_directory() creates full structure."""
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        assert (temp_project_dir / ".claude").is_dir()

    def test_ensure_claude_root(self, temp_project_dir):
        """ensure_claude_root() creates only root directory."""
        status = ensure_claude_root(temp_project_dir)

        assert status.created
        assert (temp_project_dir / ".claude").is_dir()

    def test_ensure_agents_generated(self, temp_project_dir):
        """ensure_agents_generated() creates agents/generated path."""
        status = ensure_agents_generated(temp_project_dir)

        assert status.created
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()

    def test_verify_claude_structure(self, temp_project_dir):
        """verify_claude_structure() checks directory existence."""
        scaffold_claude_directory(temp_project_dir)
        status = verify_claude_structure(temp_project_dir)

        assert all(status.values())

    def test_is_claude_scaffolded(self, temp_project_dir):
        """is_claude_scaffolded() returns correct boolean."""
        assert is_claude_scaffolded(temp_project_dir) is False

        scaffold_claude_directory(temp_project_dir)

        assert is_claude_scaffolded(temp_project_dir) is True

    def test_get_standard_subdirs_all(self):
        """get_standard_subdirs() returns all subdirs by default."""
        subdirs = get_standard_subdirs()
        assert "agents/generated" in subdirs
        assert "agents/manual" in subdirs
        assert "skills" in subdirs
        assert "commands" in subdirs

    def test_get_standard_subdirs_phase1_only(self):
        """get_standard_subdirs(include_phase2=False) returns only Phase 1."""
        subdirs = get_standard_subdirs(include_phase2=False)
        assert "agents/generated" in subdirs
        assert "agents/manual" in subdirs
        assert "skills" not in subdirs
        assert "commands" not in subdirs


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    """Test module constants."""

    def test_claude_root_dir_constant(self):
        """CLAUDE_ROOT_DIR is correct."""
        assert CLAUDE_ROOT_DIR == ".claude"

    def test_standard_subdirs_constant(self):
        """STANDARD_SUBDIRS contains expected directories."""
        assert "agents/generated" in STANDARD_SUBDIRS
        assert "agents/manual" in STANDARD_SUBDIRS
        assert "skills" in STANDARD_SUBDIRS
        assert "commands" in STANDARD_SUBDIRS

    def test_default_permissions_constant(self):
        """DEFAULT_DIR_PERMISSIONS is 0755."""
        assert DEFAULT_DIR_PERMISSIONS == 0o755

    def test_phase_1_dirs_constant(self):
        """PHASE_1_DIRS contains agent directories."""
        assert "agents/generated" in PHASE_1_DIRS
        assert "agents/manual" in PHASE_1_DIRS

    def test_phase_2_dirs_constant(self):
        """PHASE_2_DIRS contains skills and commands."""
        assert "skills" in PHASE_2_DIRS
        assert "commands" in PHASE_2_DIRS


# =============================================================================
# Test Idempotency
# =============================================================================

class TestIdempotency:
    """Test that scaffolding is idempotent."""

    def test_multiple_calls_are_safe(self, temp_project_dir):
        """Multiple scaffold calls don't cause errors."""
        result1 = scaffold_claude_directory(temp_project_dir)
        result2 = scaffold_claude_directory(temp_project_dir)
        result3 = scaffold_claude_directory(temp_project_dir)

        assert result1.success
        assert result2.success
        assert result3.success

    def test_second_call_reports_existed(self, temp_project_dir):
        """Second call reports directories as existed."""
        scaffold_claude_directory(temp_project_dir)
        result2 = scaffold_claude_directory(temp_project_dir)

        assert result2.directories_existed == 5
        assert result2.directories_created == 0

    def test_preserves_file_content(self, temp_project_dir):
        """Multiple calls don't destroy file content."""
        scaffold_claude_directory(temp_project_dir)

        # Add a file
        test_file = temp_project_dir / ".claude" / "agents" / "generated" / "test.md"
        test_file.write_text("important content")

        # Run scaffold again
        scaffold_claude_directory(temp_project_dir)

        assert test_file.exists()
        assert test_file.read_text() == "important content"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_symlinks(self, temp_project_dir):
        """Scaffolding works with symlinked project directory."""
        # Create the real directory
        real_dir = temp_project_dir / "real_project"
        real_dir.mkdir()

        # Create a symlink to it
        link_dir = temp_project_dir / "linked_project"
        link_dir.symlink_to(real_dir)

        result = scaffold_claude_directory(link_dir)

        assert result.success
        assert (real_dir / ".claude").is_dir()

    def test_handles_relative_path(self, temp_project_dir):
        """Scaffolding works with relative paths."""
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(temp_project_dir)
            result = scaffold_claude_directory(".")

            assert result.success
            assert (temp_project_dir / ".claude").is_dir()
        finally:
            os.chdir(old_cwd)

    def test_custom_permissions(self, temp_project_dir):
        """Custom permissions are applied."""
        custom_perms = 0o700
        result = scaffold_claude_directory(temp_project_dir, permissions=custom_perms)

        assert result.success
        mode = (temp_project_dir / ".claude").stat().st_mode & 0o777
        assert mode == custom_perms

    def test_handles_unicode_path(self, temp_project_dir):
        """Scaffolding works with unicode characters in path."""
        unicode_dir = temp_project_dir / "projeto_"
        unicode_dir.mkdir()

        result = scaffold_claude_directory(unicode_dir)

        assert result.success
        assert (unicode_dir / ".claude").is_dir()


# =============================================================================
# Test Integration
# =============================================================================

class TestIntegration:
    """Integration tests."""

    def test_full_workflow(self, temp_project_dir):
        """Test complete scaffolding workflow."""
        # 1. Preview
        preview = preview_claude_directory(temp_project_dir)
        assert len(preview.to_create) > 0

        # 2. Scaffold
        result = scaffold_claude_directory(temp_project_dir)
        assert result.success

        # 3. Verify
        status = verify_claude_structure(temp_project_dir)
        assert all(status.values())

        # 4. Check scaffolded
        assert is_claude_scaffolded(temp_project_dir)

    def test_phase1_only_workflow(self, temp_project_dir):
        """Test Phase 1 only scaffolding workflow."""
        result = scaffold_claude_directory(temp_project_dir, include_phase2=False)

        assert result.success
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "manual").is_dir()
        assert not (temp_project_dir / ".claude" / "skills").exists()
        assert not (temp_project_dir / ".claude" / "commands").exists()

    def test_api_package_exports(self):
        """Test that exports are available from api package."""
        from api import (
            ClaudeDirectoryScaffold,
            scaffold_claude_directory,
            CLAUDE_ROOT_DIR,
        )

        assert ClaudeDirectoryScaffold is not None
        assert scaffold_claude_directory is not None
        assert CLAUDE_ROOT_DIR == ".claude"


# =============================================================================
# Test Feature #199 Verification Steps
# =============================================================================

class TestFeature199VerificationSteps:
    """
    Comprehensive tests for each Feature #199 verification step.

    These tests verify all 5 feature steps are implemented correctly.
    """

    def test_step1_create_claude_root_if_missing(self, temp_project_dir):
        """
        Step 1: Create .claude/ root directory if missing

        Verification:
        - Directory .claude/ is created when it doesn't exist
        - Directory is a valid directory (not a file)
        - Directory has correct permissions (0755)
        """
        # Pre-condition: .claude doesn't exist
        assert not (temp_project_dir / ".claude").exists()

        # Action: scaffold
        result = scaffold_claude_directory(temp_project_dir)

        # Verification
        assert result.success
        claude_dir = temp_project_dir / ".claude"
        assert claude_dir.exists()
        assert claude_dir.is_dir()
        mode = claude_dir.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_step2_create_agents_generated(self, temp_project_dir):
        """
        Step 2: Create .claude/agents/generated/ subdirectory

        Verification:
        - Directory .claude/agents/generated/ exists after scaffolding
        - Parent directory .claude/agents/ also exists
        - Directory has correct permissions (0755)
        """
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        agents_generated = temp_project_dir / ".claude" / "agents" / "generated"
        agents_dir = temp_project_dir / ".claude" / "agents"

        assert agents_generated.exists()
        assert agents_generated.is_dir()
        assert agents_dir.exists()
        assert agents_dir.is_dir()

        mode = agents_generated.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_step3_create_agents_manual(self, temp_project_dir):
        """
        Step 3: Create .claude/agents/manual/ subdirectory (empty)

        Verification:
        - Directory .claude/agents/manual/ exists after scaffolding
        - Directory is initially empty
        - Directory has correct permissions (0755)
        """
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        agents_manual = temp_project_dir / ".claude" / "agents" / "manual"

        assert agents_manual.exists()
        assert agents_manual.is_dir()
        assert len(list(agents_manual.iterdir())) == 0  # Empty

        mode = agents_manual.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

    def test_step4_create_skills_directory(self, temp_project_dir):
        """
        Step 4: Create .claude/skills/ subdirectory (empty, Phase 2)

        Verification:
        - Directory .claude/skills/ exists after scaffolding (with Phase 2)
        - Directory is initially empty
        - Directory has correct permissions (0755)
        - Directory is marked as Phase 2
        """
        result = scaffold_claude_directory(temp_project_dir, include_phase2=True)

        assert result.success
        skills_dir = temp_project_dir / ".claude" / "skills"

        assert skills_dir.exists()
        assert skills_dir.is_dir()
        assert len(list(skills_dir.iterdir())) == 0  # Empty

        mode = skills_dir.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

        # Verify Phase 2 marker
        skills_status = next(
            d for d in result.directories if d.relative_path == "skills"
        )
        assert skills_status.phase == 2

    def test_step5_create_commands_directory(self, temp_project_dir):
        """
        Step 5: Create .claude/commands/ subdirectory (empty, Phase 2)

        Verification:
        - Directory .claude/commands/ exists after scaffolding (with Phase 2)
        - Directory is initially empty
        - Directory has correct permissions (0755)
        - Directory is marked as Phase 2
        """
        result = scaffold_claude_directory(temp_project_dir, include_phase2=True)

        assert result.success
        commands_dir = temp_project_dir / ".claude" / "commands"

        assert commands_dir.exists()
        assert commands_dir.is_dir()
        assert len(list(commands_dir.iterdir())) == 0  # Empty

        mode = commands_dir.stat().st_mode & 0o777
        assert mode == DEFAULT_DIR_PERMISSIONS

        # Verify Phase 2 marker
        commands_status = next(
            d for d in result.directories if d.relative_path == "commands"
        )
        assert commands_status.phase == 2
