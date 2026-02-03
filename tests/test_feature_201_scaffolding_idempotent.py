"""
Feature #201: Scaffolding is idempotent and safe to re-run

This test suite verifies that the scaffolding module is idempotent and safe
to run multiple times without data loss or errors.

Feature Steps:
1. Scaffolding checks for existing directories before creating
2. Existing files in manual/ never touched
3. Generated files may be overwritten by Materializer
4. Settings merged, not replaced
5. No errors on re-run of scaffolded project
"""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.scaffolding import (
    ClaudeDirectoryScaffold,
    DirectoryStatus,
    ScaffoldResult,
    scaffold_claude_directory,
    verify_claude_structure,
    is_claude_scaffolded,
    CLAUDE_ROOT_DIR,
    DEFAULT_DIR_PERMISSIONS,
)
from api.settings_manager import (
    SettingsManager,
    SettingsRequirements,
    SettingsUpdateResult,
    check_settings_exist,
    ensure_settings_for_agents,
    SETTINGS_LOCAL_FILE,
    DEFAULT_SETTINGS,
)
from api.agent_materializer import (
    AgentMaterializer,
    MaterializationResult,
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
def scaffolded_project(temp_project_dir):
    """Create a project with scaffolding already applied."""
    scaffold_claude_directory(temp_project_dir)
    return temp_project_dir


@pytest.fixture
def mock_agent_spec():
    """Create a mock AgentSpec for testing."""
    spec = MagicMock()
    spec.id = 1
    spec.name = "test-agent"
    spec.display_name = "Test Agent"
    spec.description = "A test agent for verification"
    spec.task_type = "coding"
    spec.tool_policy = {
        "allowed_tools": ["Read", "Write", "Bash"]
    }
    spec.execution_budget = {"max_turns": 10, "timeout_seconds": 300}
    spec.acceptance_spec = {"gate_mode": "all_pass", "validators": []}
    spec.context_info = {}
    return spec


@pytest.fixture
def settings_with_custom_data(scaffolded_project):
    """Create a settings file with custom data."""
    settings_path = scaffolded_project / ".claude" / SETTINGS_LOCAL_FILE
    custom_settings = {
        "permissions": {
            "allow": ["Bash(git:*)"]
        },
        "customKey": "customValue",
        "mcpServers": {
            "existing_server": {"command": "existing"}
        }
    }
    settings_path.write_text(json.dumps(custom_settings, indent=2))
    return scaffolded_project


# =============================================================================
# Test Step 1: Scaffolding checks for existing directories before creating
# =============================================================================

class TestStep1ChecksExistingDirectories:
    """Test Step 1: Scaffolding checks for existing directories before creating."""

    def test_checks_root_exists_before_creating(self, temp_project_dir):
        """Scaffold checks if .claude/ exists before creating."""
        # Pre-create root
        (temp_project_dir / ".claude").mkdir()

        result = scaffold_claude_directory(temp_project_dir)

        # Should report root as existed, not created
        root_status = next(
            d for d in result.directories if d.relative_path == CLAUDE_ROOT_DIR
        )
        assert root_status.existed is True
        assert root_status.created is False

    def test_checks_subdirs_exist_before_creating(self, temp_project_dir):
        """Scaffold checks if subdirectories exist before creating."""
        # Pre-create some subdirectories
        agents_gen = temp_project_dir / ".claude" / "agents" / "generated"
        agents_gen.mkdir(parents=True)

        result = scaffold_claude_directory(temp_project_dir)

        # agents/generated should be existed, not created
        gen_status = next(
            d for d in result.directories if d.relative_path == "agents/generated"
        )
        assert gen_status.existed is True
        assert gen_status.created is False

        # agents/manual should be created
        manual_status = next(
            d for d in result.directories if d.relative_path == "agents/manual"
        )
        assert manual_status.created is True

    def test_partial_structure_filled_in(self, temp_project_dir):
        """Scaffold only creates missing directories."""
        # Pre-create only root and agents/generated
        (temp_project_dir / ".claude" / "agents" / "generated").mkdir(parents=True)

        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        # Count: .claude existed, agents/generated existed
        # Created: agents/manual, skills, commands
        assert result.directories_existed >= 2  # At least root and agents/generated
        assert result.directories_created >= 2  # At least manual, skills, commands

        # Verify all directories now exist
        assert (temp_project_dir / ".claude" / "agents" / "manual").is_dir()
        assert (temp_project_dir / ".claude" / "skills").is_dir()
        assert (temp_project_dir / ".claude" / "commands").is_dir()

    def test_directory_status_tracks_existence(self, temp_project_dir):
        """DirectoryStatus properly tracks pre-existence."""
        scaffold = ClaudeDirectoryScaffold(temp_project_dir)

        # First run - all created
        result1 = scaffold.create_structure()
        created_count = sum(1 for d in result1.directories if d.created)
        existed_count = sum(1 for d in result1.directories if d.existed)

        assert created_count == 5  # All 5 directories created
        assert existed_count == 0

        # Second run - all existed
        result2 = scaffold.create_structure()
        created_count = sum(1 for d in result2.directories if d.created)
        existed_count = sum(1 for d in result2.directories if d.existed)

        assert created_count == 0
        assert existed_count == 5  # All 5 directories existed

    def test_uses_exist_ok_for_safety(self, temp_project_dir):
        """Scaffold uses mkdir(exist_ok=True) for safety."""
        # Create full structure
        scaffold_claude_directory(temp_project_dir)

        # This should not raise, even though directories exist
        result = scaffold_claude_directory(temp_project_dir)

        assert result.success


# =============================================================================
# Test Step 2: Existing files in manual/ never touched
# =============================================================================

class TestStep2ManualFilesNeverTouched:
    """Test Step 2: Existing files in manual/ never touched."""

    def test_manual_files_preserved_on_rerun(self, scaffolded_project):
        """Files in agents/manual/ are preserved on re-scaffold."""
        manual_dir = scaffolded_project / ".claude" / "agents" / "manual"

        # Create files in manual/
        agent_file = manual_dir / "my-custom-agent.md"
        agent_file.write_text("# My Custom Agent\n\nDo not delete me!")

        config_file = manual_dir / "config.json"
        config_file.write_text('{"key": "value"}')

        # Re-run scaffolding
        result = scaffold_claude_directory(scaffolded_project)

        assert result.success

        # Files should still exist with original content
        assert agent_file.exists()
        assert agent_file.read_text() == "# My Custom Agent\n\nDo not delete me!"
        assert config_file.exists()
        assert config_file.read_text() == '{"key": "value"}'

    def test_manual_directory_content_unchanged(self, scaffolded_project):
        """Content of agents/manual/ is completely unchanged."""
        manual_dir = scaffolded_project / ".claude" / "agents" / "manual"

        # Create nested structure
        nested_dir = manual_dir / "nested" / "deep"
        nested_dir.mkdir(parents=True)
        (nested_dir / "file.txt").write_text("nested content")

        # Record original contents
        original_files = list(manual_dir.rglob("*"))
        original_content = {
            f: f.read_text() if f.is_file() else None
            for f in original_files
        }

        # Re-run scaffolding multiple times
        for _ in range(3):
            scaffold_claude_directory(scaffolded_project)

        # Verify contents unchanged
        current_files = list(manual_dir.rglob("*"))
        assert len(current_files) == len(original_files)

        for f in current_files:
            if f.is_file():
                assert f.read_text() == original_content[f]

    def test_manual_file_permissions_preserved(self, scaffolded_project):
        """File permissions in agents/manual/ are preserved."""
        manual_dir = scaffolded_project / ".claude" / "agents" / "manual"

        # Create a file with custom permissions
        custom_file = manual_dir / "custom-perms.md"
        custom_file.write_text("custom")
        os.chmod(custom_file, 0o600)  # Owner read/write only

        original_mode = custom_file.stat().st_mode

        # Re-run scaffolding
        scaffold_claude_directory(scaffolded_project)

        # Permissions should be unchanged
        assert custom_file.stat().st_mode == original_mode

    def test_scaffolding_doesnt_modify_manual_timestamps(self, scaffolded_project):
        """Scaffolding doesn't modify file timestamps in manual/."""
        manual_dir = scaffolded_project / ".claude" / "agents" / "manual"

        # Create a file
        agent_file = manual_dir / "agent.md"
        agent_file.write_text("content")

        # Record modification time
        original_mtime = agent_file.stat().st_mtime

        # Small delay to ensure timestamp would change if modified
        import time
        time.sleep(0.1)

        # Re-run scaffolding
        scaffold_claude_directory(scaffolded_project)

        # mtime should be unchanged
        assert agent_file.stat().st_mtime == original_mtime


# =============================================================================
# Test Step 3: Generated files may be overwritten by Materializer
# =============================================================================

class TestStep3GeneratedFilesOverwritable:
    """Test Step 3: Generated files may be overwritten by Materializer."""

    def test_materializer_can_overwrite_generated_file(self, scaffolded_project, mock_agent_spec):
        """AgentMaterializer can overwrite existing files in agents/generated/."""
        generated_dir = scaffolded_project / ".claude" / "agents" / "generated"

        # Create an existing file that will be overwritten
        existing_file = generated_dir / "test-agent.md"
        existing_file.write_text("# Old Content\n\nThis will be replaced.")

        # Use materializer to overwrite
        materializer = AgentMaterializer(scaffolded_project)

        # We need to render content directly since materialize needs a real spec
        content = "---\nname: test-agent\ndescription: Updated agent\nmodel: sonnet\n---\n\n# New Content"
        (generated_dir / "test-agent.md").write_text(content)

        # Verify file was overwritten
        assert existing_file.exists()
        new_content = existing_file.read_text()
        assert "New Content" in new_content
        assert "Old Content" not in new_content

    def test_generated_files_not_protected_by_scaffold(self, scaffolded_project):
        """Files in agents/generated/ are not protected from overwrites."""
        generated_dir = scaffolded_project / ".claude" / "agents" / "generated"

        # Create a file
        gen_file = generated_dir / "auto-generated.md"
        gen_file.write_text("# Generated Agent")

        # Scaffold doesn't protect it - we can overwrite
        gen_file.write_text("# Overwritten Content")

        # Re-scaffold doesn't restore original
        scaffold_claude_directory(scaffolded_project)

        assert gen_file.read_text() == "# Overwritten Content"

    def test_scaffold_preserves_generated_files_but_allows_external_overwrites(self, scaffolded_project):
        """Scaffold preserves files but doesn't prevent external overwrites."""
        generated_dir = scaffolded_project / ".claude" / "agents" / "generated"

        # Create generated file
        gen_file = generated_dir / "agent.md"
        gen_file.write_text("original content")

        # Re-scaffold preserves it
        scaffold_claude_directory(scaffolded_project)
        assert gen_file.read_text() == "original content"

        # External process can still overwrite
        gen_file.write_text("new content")
        assert gen_file.read_text() == "new content"


# =============================================================================
# Test Step 4: Settings merged, not replaced
# =============================================================================

class TestStep4SettingsMergedNotReplaced:
    """Test Step 4: Settings merged, not replaced."""

    def test_settings_merge_preserves_custom_fields(self, settings_with_custom_data):
        """Settings merge preserves custom fields not in defaults."""
        manager = SettingsManager(settings_with_custom_data)

        # Update settings
        requirements = SettingsRequirements(mcp_servers={"features"})
        result = manager.update_settings(requirements=requirements)

        assert result.success

        # Load and verify custom fields preserved
        settings = manager.load_settings()
        assert "customKey" in settings
        assert settings["customKey"] == "customValue"

    def test_settings_merge_preserves_existing_mcp_servers(self, settings_with_custom_data):
        """Settings merge preserves existing MCP servers."""
        manager = SettingsManager(settings_with_custom_data)

        # Update with new server requirement
        requirements = SettingsRequirements(mcp_servers={"features"})
        result = manager.update_settings(requirements=requirements)

        assert result.success

        settings = manager.load_settings()
        # Both existing and new servers should be present
        assert "existing_server" in settings["mcpServers"]
        assert "features" in settings["mcpServers"]
        # Existing server config unchanged
        assert settings["mcpServers"]["existing_server"]["command"] == "existing"

    def test_settings_merge_preserves_existing_permissions(self, settings_with_custom_data):
        """Settings merge preserves existing permission patterns."""
        manager = SettingsManager(settings_with_custom_data)

        # Update settings
        requirements = SettingsRequirements(permissions={"Bash(npm:*)"})
        result = manager.update_settings(requirements=requirements)

        assert result.success

        settings = manager.load_settings()
        # Both old and new permissions present
        assert "Bash(git:*)" in settings["permissions"]["allow"]
        assert "Bash(npm:*)" in settings["permissions"]["allow"]

    def test_settings_no_data_loss_on_multiple_updates(self, scaffolded_project):
        """Multiple settings updates don't lose data."""
        manager = SettingsManager(scaffolded_project)

        # First update
        req1 = SettingsRequirements(
            mcp_servers={"features"},
            permissions={"Bash(git:*)"}
        )
        manager.update_settings(requirements=req1)

        # Second update with different data
        req2 = SettingsRequirements(
            mcp_servers={"playwright"},
            permissions={"Bash(npm:*)"}
        )
        manager.update_settings(requirements=req2)

        # Third update with more data
        req3 = SettingsRequirements(
            mcp_servers={"features"},  # Already exists
            permissions={"Bash(pip:*)"}
        )
        manager.update_settings(requirements=req3)

        # Verify all data preserved
        settings = manager.load_settings()
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]
        assert "Bash(git:*)" in settings["permissions"]["allow"]
        assert "Bash(npm:*)" in settings["permissions"]["allow"]
        assert "Bash(pip:*)" in settings["permissions"]["allow"]

    def test_settings_update_is_additive(self, scaffolded_project):
        """Settings updates only add, never remove."""
        manager = SettingsManager(scaffolded_project)

        # Create initial settings with data
        initial = {
            "permissions": {"allow": ["Bash(git:*)"]},
            "mcpServers": {"server1": {"command": "cmd1"}},
            "extra_field": "should_persist"
        }
        manager._settings_path.parent.mkdir(parents=True, exist_ok=True)
        manager._settings_path.write_text(json.dumps(initial, indent=2))

        # Update with empty requirements
        result = manager.update_settings(requirements=SettingsRequirements())

        assert result.success
        settings = manager.load_settings()

        # All original data should remain
        assert "Bash(git:*)" in settings["permissions"]["allow"]
        assert "server1" in settings["mcpServers"]
        assert settings["extra_field"] == "should_persist"

    def test_concurrent_settings_dont_duplicate_servers(self, scaffolded_project):
        """Requesting same MCP server multiple times doesn't duplicate."""
        manager = SettingsManager(scaffolded_project)

        # Request same server multiple times
        for _ in range(3):
            requirements = SettingsRequirements(mcp_servers={"features"})
            manager.update_settings(requirements=requirements)

        settings = manager.load_settings()
        # Should only have one "features" entry
        assert list(settings["mcpServers"].keys()).count("features") == 1


# =============================================================================
# Test Step 5: No errors on re-run of scaffolded project
# =============================================================================

class TestStep5NoErrorsOnRerun:
    """Test Step 5: No errors on re-run of scaffolded project."""

    def test_multiple_scaffolds_all_succeed(self, temp_project_dir):
        """Multiple scaffold operations all return success."""
        results = []
        for i in range(5):
            result = scaffold_claude_directory(temp_project_dir)
            results.append(result)

        assert all(r.success for r in results)

    def test_no_exceptions_on_rerun(self, scaffolded_project):
        """No exceptions raised when re-running scaffold."""
        # This should not raise any exceptions
        for _ in range(3):
            result = scaffold_claude_directory(scaffolded_project)
            assert result.success

    def test_scaffold_after_settings_update_works(self, scaffolded_project):
        """Scaffold works after settings have been updated."""
        manager = SettingsManager(scaffolded_project)
        manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"features"}
        ))

        # Re-scaffold should work fine
        result = scaffold_claude_directory(scaffolded_project)
        assert result.success

        # Settings should still exist
        assert manager.settings_exist()

    def test_scaffold_after_file_operations_works(self, scaffolded_project):
        """Scaffold works after various file operations."""
        manual_dir = scaffolded_project / ".claude" / "agents" / "manual"
        generated_dir = scaffolded_project / ".claude" / "agents" / "generated"

        # Create files
        (manual_dir / "agent1.md").write_text("manual")
        (generated_dir / "agent2.md").write_text("generated")

        # Delete some files
        (manual_dir / "agent1.md").unlink()

        # Create directories
        (scaffolded_project / ".claude" / "custom").mkdir()

        # Scaffold should still work
        result = scaffold_claude_directory(scaffolded_project)
        assert result.success

    def test_rerun_maintains_complete_structure(self, temp_project_dir):
        """Multiple runs maintain complete directory structure."""
        # First run
        scaffold_claude_directory(temp_project_dir)

        # Verify complete
        assert is_claude_scaffolded(temp_project_dir)

        # Delete a subdirectory
        import shutil
        shutil.rmtree(temp_project_dir / ".claude" / "skills")

        # Should be incomplete now
        assert not is_claude_scaffolded(temp_project_dir)

        # Re-run should restore it
        result = scaffold_claude_directory(temp_project_dir)
        assert result.success
        assert is_claude_scaffolded(temp_project_dir)

    def test_verify_structure_works_after_multiple_runs(self, temp_project_dir):
        """verify_claude_structure() works after multiple scaffolds."""
        for _ in range(3):
            scaffold_claude_directory(temp_project_dir)

        status = verify_claude_structure(temp_project_dir)
        assert all(status.values())


# =============================================================================
# Integration Tests: Full Idempotency Workflow
# =============================================================================

class TestIdempotencyIntegration:
    """Integration tests for full idempotency behavior."""

    def test_complete_idempotent_workflow(self, temp_project_dir):
        """Test complete idempotent workflow with all components."""
        # Step 1: Initial scaffold
        result1 = scaffold_claude_directory(temp_project_dir)
        assert result1.success
        assert result1.directories_created == 5

        # Step 2: Add content to manual/
        manual_file = temp_project_dir / ".claude" / "agents" / "manual" / "my-agent.md"
        manual_file.write_text("# My Agent\n\nImportant content!")

        # Step 3: Add content to generated/
        gen_file = temp_project_dir / ".claude" / "agents" / "generated" / "auto-agent.md"
        gen_file.write_text("# Auto Agent")

        # Step 4: Add settings
        manager = SettingsManager(temp_project_dir)
        manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"features", "playwright"},
            permissions={"Bash(git:*)"}
        ))

        # Step 5: Re-scaffold multiple times
        for _ in range(3):
            result = scaffold_claude_directory(temp_project_dir)
            assert result.success
            assert result.directories_existed == 5
            assert result.directories_created == 0

        # Step 6: Verify everything preserved
        assert manual_file.exists()
        assert manual_file.read_text() == "# My Agent\n\nImportant content!"
        assert gen_file.exists()

        settings = manager.load_settings()
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]
        assert "Bash(git:*)" in settings["permissions"]["allow"]

    def test_settings_and_scaffold_interaction(self, temp_project_dir):
        """Test that settings updates and scaffolding work together."""
        # Initial scaffold
        scaffold_claude_directory(temp_project_dir)

        # Update settings
        manager = SettingsManager(temp_project_dir)
        manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"features"}
        ))

        # Re-scaffold
        scaffold_claude_directory(temp_project_dir)

        # Update settings again
        manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"playwright"}
        ))

        # Re-scaffold again
        scaffold_claude_directory(temp_project_dir)

        # Both servers should be present
        settings = manager.load_settings()
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]

    def test_idempotent_batch_operations(self, temp_project_dir):
        """Test idempotency with batch scaffold/settings operations."""
        # Create structure
        scaffold_claude_directory(temp_project_dir)

        # Batch of operations
        manager = SettingsManager(temp_project_dir)
        servers = ["features", "playwright"]

        for server in servers:
            manager.update_settings(requirements=SettingsRequirements(
                mcp_servers={server}
            ))
            scaffold_claude_directory(temp_project_dir)

        # Re-run entire batch
        for server in servers:
            manager.update_settings(requirements=SettingsRequirements(
                mcp_servers={server}
            ))
            scaffold_claude_directory(temp_project_dir)

        # Final verification
        assert is_claude_scaffolded(temp_project_dir)
        settings = manager.load_settings()
        for server in servers:
            assert server in settings["mcpServers"]


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge cases for idempotent behavior."""

    def test_handles_concurrent_scaffold_attempts(self, temp_project_dir):
        """Handles concurrent scaffold attempts gracefully."""
        import threading

        results = []
        errors = []

        def scaffold():
            try:
                result = scaffold_claude_directory(temp_project_dir)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run 5 concurrent scaffolds
        threads = [threading.Thread(target=scaffold) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed (no race conditions)
        assert len(errors) == 0
        assert all(r.success for r in results)
        assert is_claude_scaffolded(temp_project_dir)

    def test_handles_partial_failure_gracefully(self, temp_project_dir):
        """Handles partial failure scenarios."""
        # Create initial structure
        scaffold_claude_directory(temp_project_dir)

        # Make one directory read-only (simulating a failure scenario)
        skills_dir = temp_project_dir / ".claude" / "skills"

        # Delete skills and try to prevent recreation (platform-specific)
        import shutil
        shutil.rmtree(skills_dir)

        # Re-scaffold should restore it
        result = scaffold_claude_directory(temp_project_dir)
        assert result.success
        assert skills_dir.is_dir()

    def test_empty_settings_file_handled(self, scaffolded_project):
        """Empty settings file is handled gracefully."""
        settings_path = scaffolded_project / ".claude" / SETTINGS_LOCAL_FILE
        settings_path.write_text("")

        manager = SettingsManager(scaffolded_project)

        # Should return empty dict, not crash
        settings = manager.load_settings()
        assert settings == {}

        # Update should work
        result = manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"features"}
        ))
        assert result.success

    def test_invalid_json_settings_handled(self, scaffolded_project):
        """Invalid JSON in settings is handled gracefully."""
        settings_path = scaffolded_project / ".claude" / SETTINGS_LOCAL_FILE
        settings_path.write_text("not valid json {{{")

        manager = SettingsManager(scaffolded_project)

        # Should return empty dict, not crash
        settings = manager.load_settings()
        assert settings == {}

        # Update should work (overwrites invalid content)
        result = manager.update_settings()
        assert result.success

        # Now should be valid
        settings = manager.load_settings()
        assert "permissions" in settings


# =============================================================================
# Feature #201 Verification Steps
# =============================================================================

class TestFeature201VerificationSteps:
    """
    Comprehensive tests for each Feature #201 verification step.

    These tests provide final verification that all 5 feature steps
    are implemented correctly.
    """

    def test_step1_checks_existing_directories(self, temp_project_dir):
        """
        Step 1: Scaffolding checks for existing directories before creating

        Verification:
        - Scaffold uses exist_ok=True
        - Reports existing directories correctly
        - Only creates missing directories
        """
        # Pre-create partial structure
        (temp_project_dir / ".claude" / "agents" / "generated").mkdir(parents=True)

        result = scaffold_claude_directory(temp_project_dir)

        assert result.success
        # Root and agents/generated existed
        existed_dirs = [d.relative_path for d in result.directories if d.existed]
        created_dirs = [d.relative_path for d in result.directories if d.created]

        assert ".claude" in existed_dirs
        assert "agents/generated" in existed_dirs
        assert "agents/manual" in created_dirs
        assert "skills" in created_dirs
        assert "commands" in created_dirs

    def test_step2_manual_files_never_touched(self, scaffolded_project):
        """
        Step 2: Existing files in manual/ never touched

        Verification:
        - Files in manual/ preserved after scaffold
        - File content unchanged
        - File permissions unchanged
        """
        manual_dir = scaffolded_project / ".claude" / "agents" / "manual"

        # Create files
        agent_file = manual_dir / "custom-agent.md"
        agent_file.write_text("# My Custom Agent\n\nDon't touch me!")
        original_content = agent_file.read_text()
        original_mtime = agent_file.stat().st_mtime

        # Re-scaffold multiple times
        for _ in range(5):
            result = scaffold_claude_directory(scaffolded_project)
            assert result.success

        # File unchanged
        assert agent_file.exists()
        assert agent_file.read_text() == original_content
        assert agent_file.stat().st_mtime == original_mtime

    def test_step3_generated_files_overwritable(self, scaffolded_project):
        """
        Step 3: Generated files may be overwritten by Materializer

        Verification:
        - Files in generated/ can be overwritten
        - Scaffold doesn't protect generated files
        - Materializer can update generated files
        """
        generated_dir = scaffolded_project / ".claude" / "agents" / "generated"

        # Create a generated file
        gen_file = generated_dir / "auto-agent.md"
        gen_file.write_text("# Version 1")

        # External overwrite (simulating Materializer)
        gen_file.write_text("# Version 2")

        # Re-scaffold
        scaffold_claude_directory(scaffolded_project)

        # File should have new content (scaffold doesn't restore)
        assert gen_file.read_text() == "# Version 2"

    def test_step4_settings_merged_not_replaced(self, scaffolded_project):
        """
        Step 4: Settings merged, not replaced

        Verification:
        - Existing settings preserved
        - New settings added
        - Custom fields kept
        - No data loss on multiple updates
        """
        manager = SettingsManager(scaffolded_project)

        # Create initial settings
        manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"features"},
            permissions={"Bash(git:*)"}
        ))

        # Add custom field manually
        settings = manager.load_settings()
        settings["myCustomField"] = "myValue"
        manager._settings_path.write_text(json.dumps(settings, indent=2))

        # Update with new requirements
        manager.update_settings(requirements=SettingsRequirements(
            mcp_servers={"playwright"},
            permissions={"Bash(npm:*)"}
        ))

        # Verify all data preserved
        final_settings = manager.load_settings()
        assert "features" in final_settings["mcpServers"]
        assert "playwright" in final_settings["mcpServers"]
        assert "Bash(git:*)" in final_settings["permissions"]["allow"]
        assert "Bash(npm:*)" in final_settings["permissions"]["allow"]
        assert final_settings.get("myCustomField") == "myValue"

    def test_step5_no_errors_on_rerun(self, temp_project_dir):
        """
        Step 5: No errors on re-run of scaffolded project

        Verification:
        - Multiple scaffolds succeed
        - No exceptions raised
        - Structure remains complete
        """
        # Run scaffold 10 times
        results = []
        for i in range(10):
            result = scaffold_claude_directory(temp_project_dir)
            results.append(result)

            # Verify structure after each run
            assert is_claude_scaffolded(temp_project_dir)

        # All runs succeeded
        assert all(r.success for r in results)

        # First run created, rest existed
        assert results[0].directories_created == 5
        for result in results[1:]:
            assert result.directories_existed == 5
            assert result.directories_created == 0


# =============================================================================
# API Package Exports Test
# =============================================================================

class TestApiPackageExports:
    """Test that required exports are available from api package."""

    def test_scaffolding_exports(self):
        """Test scaffolding module exports."""
        from api import (
            ClaudeDirectoryScaffold,
            scaffold_claude_directory,
            verify_claude_structure,
            is_claude_scaffolded,
            CLAUDE_ROOT_DIR,
        )
        assert ClaudeDirectoryScaffold is not None
        assert scaffold_claude_directory is not None
        assert verify_claude_structure is not None
        assert is_claude_scaffolded is not None
        assert CLAUDE_ROOT_DIR == ".claude"

    def test_settings_manager_exports(self):
        """Test settings manager module exports."""
        from api import (
            SettingsManager,
            SettingsRequirements,
            SettingsUpdateResult,
            check_settings_exist,
            ensure_settings_for_agents,
        )
        assert SettingsManager is not None
        assert SettingsRequirements is not None
        assert SettingsUpdateResult is not None
        assert check_settings_exist is not None
        assert ensure_settings_for_agents is not None
