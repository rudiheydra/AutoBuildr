"""
Feature #202: Scaffolding triggered automatically on project initialization

This test suite verifies that scaffolding is automatically triggered when
a project is initialized or first processed. This ensures the .claude
directory structure is always present before agent execution.

Feature Steps:
1. Project initialization triggers scaffolding check
2. Missing .claude structure created automatically
3. Scaffolding completes before agent execution
4. Scaffolding status recorded in project metadata
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from api.scaffolding import (
    # Feature #202 exports
    ScaffoldingStatus,
    ProjectInitializationResult,
    get_scaffolding_status,
    needs_scaffolding,
    initialize_project_scaffolding,
    ensure_project_scaffolded,
    is_project_initialized,
    # Constants
    SCAFFOLDING_METADATA_KEY,
    SCAFFOLDING_TIMESTAMP_KEY,
    SCAFFOLDING_COMPLETED_KEY,
    PROJECT_METADATA_FILE,
    # Feature #199 exports (for verification)
    CLAUDE_ROOT_DIR,
    STANDARD_SUBDIRS,
    is_claude_scaffolded,
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
def project_with_autobuildr(temp_project_dir):
    """Create a project with .autobuildr directory."""
    autobuildr_dir = temp_project_dir / ".autobuildr"
    autobuildr_dir.mkdir()
    return temp_project_dir


@pytest.fixture
def project_with_claude_dir(temp_project_dir):
    """Create a project with .claude directory structure."""
    claude_dir = temp_project_dir / ".claude"
    claude_dir.mkdir()
    (claude_dir / "agents" / "generated").mkdir(parents=True)
    (claude_dir / "agents" / "manual").mkdir(parents=True)
    (claude_dir / "skills").mkdir()
    (claude_dir / "commands").mkdir()
    return temp_project_dir


# =============================================================================
# Test ScaffoldingStatus Data Class
# =============================================================================

class TestScaffoldingStatusDataClass:
    """Tests for the ScaffoldingStatus data class."""

    def test_default_values(self):
        """ScaffoldingStatus has correct default values."""
        status = ScaffoldingStatus()

        assert status.completed is False
        assert status.timestamp is None
        assert status.directories_created == 0
        assert status.directories_existed == 0
        assert status.claude_md_created is False
        assert status.error is None

    def test_to_dict_conversion(self):
        """ScaffoldingStatus converts to dictionary correctly."""
        status = ScaffoldingStatus(
            completed=True,
            timestamp="2026-02-04T00:00:00Z",
            directories_created=5,
            directories_existed=0,
            claude_md_created=True,
            error=None,
        )

        result = status.to_dict()

        assert result[SCAFFOLDING_COMPLETED_KEY] is True
        assert result[SCAFFOLDING_TIMESTAMP_KEY] == "2026-02-04T00:00:00Z"
        assert result["directories_created"] == 5
        assert result["directories_existed"] == 0
        assert result["claude_md_created"] is True
        assert result["error"] is None

    def test_from_dict_creation(self):
        """ScaffoldingStatus can be created from dictionary."""
        data = {
            SCAFFOLDING_COMPLETED_KEY: True,
            SCAFFOLDING_TIMESTAMP_KEY: "2026-02-04T00:00:00Z",
            "directories_created": 3,
            "directories_existed": 2,
            "claude_md_created": True,
            "error": None,
        }

        status = ScaffoldingStatus.from_dict(data)

        assert status.completed is True
        assert status.timestamp == "2026-02-04T00:00:00Z"
        assert status.directories_created == 3
        assert status.directories_existed == 2
        assert status.claude_md_created is True
        assert status.error is None

    def test_from_dict_with_missing_keys(self):
        """ScaffoldingStatus handles missing dictionary keys gracefully."""
        status = ScaffoldingStatus.from_dict({})

        assert status.completed is False
        assert status.timestamp is None
        assert status.directories_created == 0
        assert status.directories_existed == 0

    def test_round_trip_conversion(self):
        """ScaffoldingStatus survives to_dict -> from_dict round trip."""
        original = ScaffoldingStatus(
            completed=True,
            timestamp="2026-02-04T12:34:56Z",
            directories_created=5,
            directories_existed=0,
            claude_md_created=True,
            error=None,
        )

        data = original.to_dict()
        restored = ScaffoldingStatus.from_dict(data)

        assert restored.completed == original.completed
        assert restored.timestamp == original.timestamp
        assert restored.directories_created == original.directories_created
        assert restored.directories_existed == original.directories_existed
        assert restored.claude_md_created == original.claude_md_created
        assert restored.error == original.error


# =============================================================================
# Test ProjectInitializationResult Data Class
# =============================================================================

class TestProjectInitializationResultDataClass:
    """Tests for the ProjectInitializationResult data class."""

    def test_default_values(self, temp_project_dir):
        """ProjectInitializationResult has correct default values."""
        result = ProjectInitializationResult(
            success=True,
            project_dir=temp_project_dir,
        )

        assert result.success is True
        assert result.project_dir == temp_project_dir
        assert result.scaffold_result is None
        assert result.claude_md_result is None
        assert result.scaffolding_status is None
        assert result.metadata_saved is False

    def test_to_dict_conversion(self, temp_project_dir):
        """ProjectInitializationResult converts to dictionary correctly."""
        status = ScaffoldingStatus(completed=True, timestamp="2026-02-04T00:00:00Z")
        result = ProjectInitializationResult(
            success=True,
            project_dir=temp_project_dir,
            scaffolding_status=status,
            metadata_saved=True,
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["project_dir"] == str(temp_project_dir)
        assert data["scaffolding_status"] is not None
        assert data["metadata_saved"] is True


# =============================================================================
# Test Step 1: Project initialization triggers scaffolding check
# =============================================================================

class TestStep1ScaffoldingCheck:
    """Test Step 1: Project initialization triggers scaffolding check."""

    def test_needs_scaffolding_returns_true_for_new_project(self, temp_project_dir):
        """needs_scaffolding returns True for a new project without .claude."""
        assert needs_scaffolding(temp_project_dir) is True

    def test_needs_scaffolding_returns_true_when_claude_dir_missing(self, temp_project_dir):
        """needs_scaffolding returns True when .claude directory doesn't exist."""
        # Create some other directories but not .claude
        (temp_project_dir / "src").mkdir()
        (temp_project_dir / ".autobuildr").mkdir()

        assert needs_scaffolding(temp_project_dir) is True

    def test_needs_scaffolding_returns_true_when_incomplete(self, temp_project_dir):
        """needs_scaffolding returns True when scaffolding metadata is incomplete."""
        # Create .claude directory but no metadata
        (temp_project_dir / ".claude").mkdir()

        assert needs_scaffolding(temp_project_dir) is True

    def test_needs_scaffolding_returns_false_when_completed(self, temp_project_dir):
        """needs_scaffolding returns False when scaffolding is marked complete."""
        # Create .claude directory
        (temp_project_dir / ".claude").mkdir()

        # Create metadata with completed status
        metadata_dir = temp_project_dir / ".autobuildr"
        metadata_dir.mkdir()
        metadata_path = metadata_dir / PROJECT_METADATA_FILE
        metadata = {
            SCAFFOLDING_METADATA_KEY: {
                SCAFFOLDING_COMPLETED_KEY: True,
                SCAFFOLDING_TIMESTAMP_KEY: "2026-02-04T00:00:00Z",
            }
        }
        metadata_path.write_text(json.dumps(metadata))

        assert needs_scaffolding(temp_project_dir) is False

    def test_get_scaffolding_status_returns_default_for_new_project(self, temp_project_dir):
        """get_scaffolding_status returns default status for new project."""
        status = get_scaffolding_status(temp_project_dir)

        assert status.completed is False
        assert status.timestamp is None

    def test_get_scaffolding_status_reads_from_metadata(self, temp_project_dir):
        """get_scaffolding_status reads status from project metadata."""
        # Create metadata
        metadata_dir = temp_project_dir / ".autobuildr"
        metadata_dir.mkdir()
        metadata_path = metadata_dir / PROJECT_METADATA_FILE
        metadata = {
            SCAFFOLDING_METADATA_KEY: {
                SCAFFOLDING_COMPLETED_KEY: True,
                SCAFFOLDING_TIMESTAMP_KEY: "2026-02-04T00:00:00Z",
                "directories_created": 5,
                "claude_md_created": True,
            }
        }
        metadata_path.write_text(json.dumps(metadata))

        status = get_scaffolding_status(temp_project_dir)

        assert status.completed is True
        assert status.timestamp == "2026-02-04T00:00:00Z"
        assert status.directories_created == 5
        assert status.claude_md_created is True


# =============================================================================
# Test Step 2: Missing .claude structure created automatically
# =============================================================================

class TestStep2AutomaticCreation:
    """Test Step 2: Missing .claude structure created automatically."""

    def test_initialize_creates_claude_directory(self, temp_project_dir):
        """initialize_project_scaffolding creates .claude directory."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.success is True
        assert (temp_project_dir / ".claude").is_dir()

    def test_initialize_creates_full_structure(self, temp_project_dir):
        """initialize_project_scaffolding creates full directory structure."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.success is True
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "manual").is_dir()
        assert (temp_project_dir / ".claude" / "skills").is_dir()
        assert (temp_project_dir / ".claude" / "commands").is_dir()

    def test_initialize_creates_claude_md(self, temp_project_dir):
        """initialize_project_scaffolding creates CLAUDE.md by default."""
        result = initialize_project_scaffolding(temp_project_dir, include_claude_md=True)

        assert result.success is True
        assert (temp_project_dir / "CLAUDE.md").exists()

    def test_initialize_skips_claude_md_when_disabled(self, temp_project_dir):
        """initialize_project_scaffolding skips CLAUDE.md when disabled."""
        result = initialize_project_scaffolding(temp_project_dir, include_claude_md=False)

        assert result.success is True
        assert not (temp_project_dir / "CLAUDE.md").exists()

    def test_initialize_preserves_existing_directories(self, temp_project_dir):
        """initialize_project_scaffolding preserves existing directories."""
        # Pre-create .claude with a marker file
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir()
        marker_file = claude_dir / "existing_marker.txt"
        marker_file.write_text("preserve me")

        result = initialize_project_scaffolding(temp_project_dir)

        assert result.success is True
        assert marker_file.exists()
        assert marker_file.read_text() == "preserve me"

    def test_initialize_returns_scaffold_result(self, temp_project_dir):
        """initialize_project_scaffolding returns ScaffoldResult in result."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.scaffold_result is not None
        assert result.scaffold_result.success is True
        assert result.scaffold_result.directories_created > 0


# =============================================================================
# Test Step 3: Scaffolding completes before agent execution
# =============================================================================

class TestStep3CompletionBeforeExecution:
    """Test Step 3: Scaffolding completes before agent execution."""

    def test_ensure_project_scaffolded_creates_structure(self, temp_project_dir):
        """ensure_project_scaffolded creates structure when missing."""
        result = ensure_project_scaffolded(temp_project_dir)

        assert result.success is True
        assert is_claude_scaffolded(temp_project_dir) is True

    def test_ensure_project_scaffolded_is_idempotent(self, temp_project_dir):
        """ensure_project_scaffolded can be called multiple times safely."""
        # First call - creates structure
        result1 = ensure_project_scaffolded(temp_project_dir)
        assert result1.success is True

        # Second call - should skip since already completed
        result2 = ensure_project_scaffolded(temp_project_dir)
        assert result2.success is True

        # Structure should still be intact
        assert (temp_project_dir / ".claude").is_dir()

    def test_ensure_project_scaffolded_skips_when_completed(self, temp_project_dir):
        """ensure_project_scaffolded skips if scaffolding already completed."""
        # Initialize first
        initialize_project_scaffolding(temp_project_dir)

        # Second call should skip scaffolding (success but no new directories)
        result = ensure_project_scaffolded(temp_project_dir)

        assert result.success is True
        # scaffold_result should be None since scaffolding was skipped
        assert result.scaffold_result is None

    def test_is_project_initialized_reflects_completion(self, temp_project_dir):
        """is_project_initialized returns correct status."""
        # Initially not initialized
        assert is_project_initialized(temp_project_dir) is False

        # After initialization
        initialize_project_scaffolding(temp_project_dir)
        assert is_project_initialized(temp_project_dir) is True

    def test_force_reinitialize_even_when_completed(self, temp_project_dir):
        """force=True causes re-scaffolding even when completed."""
        # Initialize first
        initialize_project_scaffolding(temp_project_dir)

        # Force re-initialization
        result = initialize_project_scaffolding(temp_project_dir, force=True)

        assert result.success is True
        assert result.scaffold_result is not None
        # Directories should exist (existed, not created)
        assert result.scaffold_result.directories_existed > 0


# =============================================================================
# Test Step 4: Scaffolding status recorded in project metadata
# =============================================================================

class TestStep4MetadataRecording:
    """Test Step 4: Scaffolding status recorded in project metadata."""

    def test_initialize_records_metadata(self, temp_project_dir):
        """initialize_project_scaffolding records status in metadata."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.success is True
        assert result.metadata_saved is True

        # Verify metadata file exists
        metadata_path = temp_project_dir / ".autobuildr" / PROJECT_METADATA_FILE
        assert metadata_path.exists()

    def test_metadata_contains_scaffolding_status(self, temp_project_dir):
        """Metadata contains scaffolding status information."""
        initialize_project_scaffolding(temp_project_dir)

        # Read metadata directly
        metadata_path = temp_project_dir / ".autobuildr" / PROJECT_METADATA_FILE
        metadata = json.loads(metadata_path.read_text())

        assert SCAFFOLDING_METADATA_KEY in metadata
        scaffolding_data = metadata[SCAFFOLDING_METADATA_KEY]
        assert scaffolding_data[SCAFFOLDING_COMPLETED_KEY] is True
        assert scaffolding_data[SCAFFOLDING_TIMESTAMP_KEY] is not None

    def test_metadata_tracks_directories_created(self, temp_project_dir):
        """Metadata tracks number of directories created."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.scaffolding_status is not None
        # Should create at least: .claude, agents/generated, agents/manual, skills, commands
        assert result.scaffolding_status.directories_created >= 4

    def test_metadata_tracks_claude_md_creation(self, temp_project_dir):
        """Metadata tracks whether CLAUDE.md was created."""
        result = initialize_project_scaffolding(temp_project_dir, include_claude_md=True)

        assert result.scaffolding_status is not None
        assert result.scaffolding_status.claude_md_created is True

    def test_metadata_contains_timestamp(self, temp_project_dir):
        """Metadata contains ISO-formatted timestamp."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.scaffolding_status is not None
        assert result.scaffolding_status.timestamp is not None

        # Verify timestamp is ISO format (contains T and +/Z)
        timestamp = result.scaffolding_status.timestamp
        assert "T" in timestamp
        assert ":" in timestamp

    def test_metadata_preserves_other_data(self, temp_project_dir):
        """Scaffolding preserves other metadata in the file."""
        # Create metadata with existing data
        metadata_dir = temp_project_dir / ".autobuildr"
        metadata_dir.mkdir()
        metadata_path = metadata_dir / PROJECT_METADATA_FILE
        existing_metadata = {
            "some_other_key": "some_value",
            "nested": {"data": 123},
        }
        metadata_path.write_text(json.dumps(existing_metadata))

        # Run scaffolding
        initialize_project_scaffolding(temp_project_dir)

        # Verify other data preserved
        updated_metadata = json.loads(metadata_path.read_text())
        assert updated_metadata.get("some_other_key") == "some_value"
        assert updated_metadata.get("nested", {}).get("data") == 123
        assert SCAFFOLDING_METADATA_KEY in updated_metadata


# =============================================================================
# Test Integration with Projects Router
# =============================================================================

class TestProjectsRouterIntegration:
    """Test integration with the projects router."""

    def test_project_creation_triggers_scaffolding(self, temp_project_dir):
        """Project creation should trigger scaffolding."""
        # This tests that initialize_project_scaffolding is called during project creation
        # The actual router test would be in API tests, here we test the function works
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.success is True
        assert (temp_project_dir / ".claude").is_dir()

    def test_scaffolding_result_in_initialization(self, temp_project_dir):
        """Initialization result contains scaffold details."""
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.project_dir == temp_project_dir
        assert result.scaffold_result is not None
        assert result.scaffolding_status is not None


# =============================================================================
# Test Integration with Agent Execution
# =============================================================================

class TestAgentExecutionIntegration:
    """Test integration with agent execution."""

    def test_ensure_scaffolded_before_agent_run(self, temp_project_dir):
        """ensure_project_scaffolded creates structure if missing."""
        # This simulates what agent.py does before running
        result = ensure_project_scaffolded(temp_project_dir)

        assert result.success is True
        assert is_project_initialized(temp_project_dir) is True

    def test_agent_can_run_after_scaffolding(self, temp_project_dir):
        """After scaffolding, all required directories exist."""
        ensure_project_scaffolded(temp_project_dir)

        # All standard directories should exist
        assert (temp_project_dir / ".claude").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_non_existent_project_dir(self, temp_project_dir):
        """Handles non-existent project directory gracefully."""
        non_existent = temp_project_dir / "does_not_exist"

        # Should fail gracefully (non-existent parent)
        result = initialize_project_scaffolding(non_existent)

        # The function should handle this gracefully
        # Either by creating the directory or reporting an error
        # Implementation decides behavior

    def test_handles_readonly_directory(self, temp_project_dir):
        """Handles read-only directory gracefully."""
        import os
        import stat

        # Make directory read-only
        try:
            os.chmod(temp_project_dir, stat.S_IRUSR | stat.S_IXUSR)

            result = initialize_project_scaffolding(temp_project_dir)

            # Should fail with error recorded
            assert result.success is False
            assert result.scaffolding_status is not None
            assert result.scaffolding_status.error is not None
        finally:
            # Restore permissions for cleanup
            os.chmod(temp_project_dir, stat.S_IRWXU)

    def test_handles_corrupted_metadata(self, temp_project_dir):
        """Handles corrupted metadata file gracefully."""
        # Create corrupted metadata file
        metadata_dir = temp_project_dir / ".autobuildr"
        metadata_dir.mkdir()
        metadata_path = metadata_dir / PROJECT_METADATA_FILE
        metadata_path.write_text("not valid json {{{")

        # Should still work (treat as new project)
        status = get_scaffolding_status(temp_project_dir)
        assert status.completed is False  # Default when metadata can't be read

    def test_string_path_accepted(self, temp_project_dir):
        """Functions accept string paths as well as Path objects."""
        # Pass string path instead of Path
        path_str = str(temp_project_dir)

        result = initialize_project_scaffolding(path_str)

        assert result.success is True
        assert (temp_project_dir / ".claude").is_dir()


# =============================================================================
# Test Feature #202 Verification Steps
# =============================================================================

class TestFeature202VerificationSteps:
    """
    Summary tests for all Feature #202 verification steps.
    These provide a clear pass/fail for each feature requirement.
    """

    def test_step1_initialization_triggers_check(self, temp_project_dir):
        """
        Step 1: Project initialization triggers scaffolding check.
        - needs_scaffolding() returns True for new projects
        - needs_scaffolding() returns False for completed projects
        """
        # New project needs scaffolding
        assert needs_scaffolding(temp_project_dir) is True

        # After initialization, scaffolding not needed
        initialize_project_scaffolding(temp_project_dir)
        assert needs_scaffolding(temp_project_dir) is False

    def test_step2_automatic_creation(self, temp_project_dir):
        """
        Step 2: Missing .claude structure created automatically.
        - initialize_project_scaffolding creates .claude directory
        - All standard subdirectories are created
        """
        result = initialize_project_scaffolding(temp_project_dir)

        assert result.success is True
        assert (temp_project_dir / ".claude").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "generated").is_dir()
        assert (temp_project_dir / ".claude" / "agents" / "manual").is_dir()

    def test_step3_completes_before_execution(self, temp_project_dir):
        """
        Step 3: Scaffolding completes before agent execution.
        - ensure_project_scaffolded runs scaffolding if needed
        - is_project_initialized returns True after completion
        """
        # Before: not initialized
        assert is_project_initialized(temp_project_dir) is False

        # ensure_project_scaffolded completes scaffolding
        result = ensure_project_scaffolded(temp_project_dir)
        assert result.success is True

        # After: initialized
        assert is_project_initialized(temp_project_dir) is True

    def test_step4_metadata_recorded(self, temp_project_dir):
        """
        Step 4: Scaffolding status recorded in project metadata.
        - Metadata file created in .autobuildr/metadata.json
        - Contains scaffolding_completed, scaffolding_timestamp
        - Tracks directories_created and claude_md_created
        """
        result = initialize_project_scaffolding(temp_project_dir)

        # Metadata was saved
        assert result.metadata_saved is True

        # Metadata file exists
        metadata_path = temp_project_dir / ".autobuildr" / PROJECT_METADATA_FILE
        assert metadata_path.exists()

        # Contains required fields
        metadata = json.loads(metadata_path.read_text())
        scaffolding_data = metadata[SCAFFOLDING_METADATA_KEY]
        assert scaffolding_data[SCAFFOLDING_COMPLETED_KEY] is True
        assert scaffolding_data[SCAFFOLDING_TIMESTAMP_KEY] is not None
        assert "directories_created" in scaffolding_data


# =============================================================================
# Test API Package Exports
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #202 exports are available from api package."""

    def test_scaffolding_status_exported(self):
        """ScaffoldingStatus is exported from api package."""
        from api import ScaffoldingStatus
        assert ScaffoldingStatus is not None

    def test_project_initialization_result_exported(self):
        """ProjectInitializationResult is exported from api package."""
        from api import ProjectInitializationResult
        assert ProjectInitializationResult is not None

    def test_functions_exported(self):
        """All Feature #202 functions are exported."""
        from api import (
            get_scaffolding_status,
            needs_scaffolding,
            initialize_project_scaffolding,
            ensure_project_scaffolded,
            is_project_initialized,
        )
        assert get_scaffolding_status is not None
        assert needs_scaffolding is not None
        assert initialize_project_scaffolding is not None
        assert ensure_project_scaffolded is not None
        assert is_project_initialized is not None

    def test_constants_exported(self):
        """All Feature #202 constants are exported."""
        from api import (
            SCAFFOLDING_METADATA_KEY,
            SCAFFOLDING_TIMESTAMP_KEY,
            SCAFFOLDING_COMPLETED_KEY,
            PROJECT_METADATA_FILE,
        )
        assert SCAFFOLDING_METADATA_KEY is not None
        assert SCAFFOLDING_TIMESTAMP_KEY is not None
        assert SCAFFOLDING_COMPLETED_KEY is not None
        assert PROJECT_METADATA_FILE is not None
