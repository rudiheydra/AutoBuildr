"""
Tests for Feature #193: Agent Materializer writes to .claude/agents/generated/

Materializer writes agent files to the correct location in the project's .claude directory.

Verification Steps:
1. Materializer resolves project path
2. Materializer ensures .claude/agents/generated/ exists
3. Agent file written as {agent_name}.md
4. File permissions set appropriately
5. Existing file with same name is overwritten (idempotent)
"""
import os
import stat
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.maestro import AgentMaterializer, MaterializationResult
from api.agentspec_models import AgentSpec, generate_uuid


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def materializer(temp_project_dir):
    """AgentMaterializer instance with temp directory."""
    return AgentMaterializer(temp_project_dir)


@pytest.fixture
def sample_agent_spec():
    """Sample AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="feature-193-test-agent",
        display_name="Feature 193 Test Agent",
        icon="test",
        spec_version="v1",
        objective="Test agent for Feature #193",
        task_type="coding",
        context={"feature_id": 193, "feature_name": "Materializer File Writing"},
        tool_policy={
            "allowed_tools": ["Read", "Write", "Edit", "Bash"],
            "forbidden_patterns": ["rm -rf"],
            "tool_hints": {"Edit": "Always read before editing"},
        },
        max_turns=100,
        timeout_seconds=1800,
        source_feature_id=193,
        priority=1,
        tags=["feature-193", "materializer", "testing"],
    )


@pytest.fixture
def spec_with_special_name():
    """AgentSpec with hyphenated name."""
    return AgentSpec(
        id=generate_uuid(),
        name="my-custom-agent-v2",
        display_name="My Custom Agent V2",
        icon="custom",
        spec_version="v1",
        objective="Custom agent test",
        task_type="testing",
        context={},
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=50,
        timeout_seconds=600,
        source_feature_id=None,
        priority=1,
        tags=[],
    )


# =============================================================================
# Step 1: Materializer resolves project path
# =============================================================================

class TestStep1ResolvesProjectPath:
    """Verify Materializer resolves project path correctly."""

    def test_project_dir_is_resolved_to_absolute(self, temp_project_dir):
        """Project directory is resolved to absolute path."""
        materializer = AgentMaterializer(temp_project_dir)
        assert materializer.project_dir.is_absolute()

    def test_relative_path_is_resolved(self, temp_project_dir):
        """Relative paths are resolved to absolute."""
        # Create a relative path scenario
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_project_dir)
            materializer = AgentMaterializer(Path("."))
            assert materializer.project_dir.is_absolute()
            assert materializer.project_dir == temp_project_dir.resolve()
        finally:
            os.chdir(original_cwd)

    def test_symlink_path_is_resolved(self, temp_project_dir):
        """Symlinked paths are resolved."""
        symlink_path = temp_project_dir / "symlink_project"
        actual_dir = temp_project_dir / "actual_project"
        actual_dir.mkdir()

        try:
            symlink_path.symlink_to(actual_dir)
            materializer = AgentMaterializer(symlink_path)
            # The resolved path should be absolute
            assert materializer.project_dir.is_absolute()
        except OSError:
            # Skip if symlinks not supported
            pytest.skip("Symlinks not supported on this system")

    def test_output_path_is_relative_to_project_dir(self, temp_project_dir):
        """Output path is correctly relative to project directory."""
        materializer = AgentMaterializer(temp_project_dir)
        expected = temp_project_dir / ".claude" / "agents" / "generated"
        assert materializer.output_path == expected

    def test_project_dir_stored_correctly(self, temp_project_dir):
        """Project directory is stored and accessible."""
        materializer = AgentMaterializer(temp_project_dir)
        assert materializer.project_dir == temp_project_dir.resolve()


# =============================================================================
# Step 2: Materializer ensures .claude/agents/generated/ exists
# =============================================================================

class TestStep2EnsuresDirectoryExists:
    """Verify Materializer ensures .claude/agents/generated/ exists."""

    def test_creates_output_directory_if_missing(self, temp_project_dir):
        """Output directory is created if it doesn't exist."""
        materializer = AgentMaterializer(temp_project_dir)
        expected_dir = temp_project_dir / ".claude" / "agents" / "generated"

        assert not expected_dir.exists()
        materializer.ensure_output_dir()
        assert expected_dir.exists()
        assert expected_dir.is_dir()

    def test_creates_all_parent_directories(self, temp_project_dir):
        """All parent directories are created."""
        materializer = AgentMaterializer(temp_project_dir)

        # None of the parent directories exist
        assert not (temp_project_dir / ".claude").exists()
        assert not (temp_project_dir / ".claude" / "agents").exists()

        materializer.ensure_output_dir()

        assert (temp_project_dir / ".claude").exists()
        assert (temp_project_dir / ".claude" / "agents").exists()
        assert (temp_project_dir / ".claude" / "agents" / "generated").exists()

    def test_does_not_fail_if_directory_already_exists(self, temp_project_dir):
        """Creating directory when it already exists doesn't raise error."""
        materializer = AgentMaterializer(temp_project_dir)

        # Create directory manually first
        materializer.output_path.mkdir(parents=True, exist_ok=True)
        assert materializer.output_path.exists()

        # Should not raise
        result_path = materializer.ensure_output_dir()
        assert result_path == materializer.output_path

    def test_returns_output_path(self, temp_project_dir):
        """ensure_output_dir returns the output path."""
        materializer = AgentMaterializer(temp_project_dir)
        result = materializer.ensure_output_dir()
        assert result == materializer.output_path

    def test_default_output_dir_is_claude_agents_generated(self, temp_project_dir):
        """Default output directory is .claude/agents/generated/."""
        materializer = AgentMaterializer(temp_project_dir)
        assert materializer.DEFAULT_OUTPUT_DIR == ".claude/agents/generated"
        assert ".claude/agents/generated" in str(materializer.output_path)

    def test_custom_output_dir_supported(self, temp_project_dir):
        """Custom output directory can be specified."""
        materializer = AgentMaterializer(
            temp_project_dir,
            output_dir=".custom/output/agents"
        )
        expected = temp_project_dir / ".custom" / "output" / "agents"
        assert materializer.output_path == expected


# =============================================================================
# Step 3: Agent file written as {agent_name}.md
# =============================================================================

class TestStep3FileWrittenAsAgentNameMd:
    """Verify agent file is written as {agent_name}.md."""

    def test_file_named_with_spec_name(self, materializer, sample_agent_spec):
        """File is named {spec.name}.md."""
        result = materializer.materialize(sample_agent_spec)

        expected_filename = f"{sample_agent_spec.name}.md"
        assert result.file_path.name == expected_filename

    def test_file_written_in_output_directory(self, materializer, sample_agent_spec):
        """File is written in the output directory."""
        result = materializer.materialize(sample_agent_spec)

        assert result.file_path.parent == materializer.output_path

    def test_file_has_md_extension(self, materializer, sample_agent_spec):
        """File has .md extension."""
        result = materializer.materialize(sample_agent_spec)

        assert result.file_path.suffix == ".md"

    def test_hyphenated_names_work(self, materializer, spec_with_special_name):
        """Hyphenated agent names produce valid filenames."""
        result = materializer.materialize(spec_with_special_name)

        expected_filename = f"{spec_with_special_name.name}.md"
        assert result.file_path.name == expected_filename
        assert result.file_path.exists()

    def test_file_content_is_written(self, materializer, sample_agent_spec):
        """File content is written and non-empty."""
        result = materializer.materialize(sample_agent_spec)

        content = result.file_path.read_text()
        assert len(content) > 0
        assert sample_agent_spec.display_name in content

    def test_file_result_contains_correct_path(self, materializer, sample_agent_spec):
        """MaterializationResult contains correct file path."""
        result = materializer.materialize(sample_agent_spec)

        expected_path = materializer.output_path / f"{sample_agent_spec.name}.md"
        assert result.file_path == expected_path

    def test_file_result_success_when_written(self, materializer, sample_agent_spec):
        """MaterializationResult shows success=True when file written."""
        result = materializer.materialize(sample_agent_spec)

        assert result.success is True
        assert result.error is None


# =============================================================================
# Step 4: File permissions set appropriately
# =============================================================================

class TestStep4FilePermissions:
    """Verify file permissions are set appropriately."""

    def test_file_is_readable(self, materializer, sample_agent_spec):
        """Created file is readable."""
        result = materializer.materialize(sample_agent_spec)

        # Check file is readable
        assert os.access(result.file_path, os.R_OK)

    def test_file_is_writable_by_owner(self, materializer, sample_agent_spec):
        """Created file is writable by owner."""
        result = materializer.materialize(sample_agent_spec)

        # Check file is writable
        assert os.access(result.file_path, os.W_OK)

    def test_file_is_not_executable(self, materializer, sample_agent_spec):
        """Created file is not executable (it's a markdown file)."""
        result = materializer.materialize(sample_agent_spec)

        # Markdown files should not be executable
        file_stat = os.stat(result.file_path)
        is_executable = bool(file_stat.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        assert not is_executable

    def test_file_permissions_are_0644_or_similar(self, materializer, sample_agent_spec):
        """File permissions are set to reasonable defaults (0644 or similar)."""
        result = materializer.materialize(sample_agent_spec)

        file_stat = os.stat(result.file_path)
        mode = stat.S_IMODE(file_stat.st_mode)

        # Should have owner read/write at minimum
        assert mode & stat.S_IRUSR  # Owner read
        assert mode & stat.S_IWUSR  # Owner write

        # Should not have any execute bits
        assert not (mode & stat.S_IXUSR)  # No owner execute
        assert not (mode & stat.S_IXGRP)  # No group execute
        assert not (mode & stat.S_IXOTH)  # No other execute

    def test_directory_permissions_allow_traversal(self, materializer, sample_agent_spec):
        """Output directory permissions allow traversal."""
        materializer.ensure_output_dir()

        # Directory should be readable and executable (traversable)
        assert os.access(materializer.output_path, os.R_OK)
        assert os.access(materializer.output_path, os.X_OK)

    def test_file_permissions_consistent_across_multiple_writes(self, materializer, sample_agent_spec):
        """File permissions are consistent when overwriting."""
        # First write
        result1 = materializer.materialize(sample_agent_spec)
        mode1 = stat.S_IMODE(os.stat(result1.file_path).st_mode)

        # Second write (overwrite)
        result2 = materializer.materialize(sample_agent_spec)
        mode2 = stat.S_IMODE(os.stat(result2.file_path).st_mode)

        # Permissions should be the same
        assert mode1 == mode2


# =============================================================================
# Step 5: Existing file with same name is overwritten (idempotent)
# =============================================================================

class TestStep5IdempotentOverwrite:
    """Verify existing file with same name is overwritten (idempotent)."""

    def test_overwrites_existing_file(self, materializer, sample_agent_spec):
        """Existing file is overwritten."""
        # First write
        result1 = materializer.materialize(sample_agent_spec)
        content1 = result1.file_path.read_text()

        # Modify the spec slightly
        sample_agent_spec.objective = "Updated objective for testing"

        # Second write should overwrite
        result2 = materializer.materialize(sample_agent_spec)
        content2 = result2.file_path.read_text()

        # Content should be different
        assert content2 != content1
        assert "Updated objective for testing" in content2

    def test_same_file_path_after_overwrite(self, materializer, sample_agent_spec):
        """File path is the same after overwrite."""
        result1 = materializer.materialize(sample_agent_spec)
        result2 = materializer.materialize(sample_agent_spec)

        assert result1.file_path == result2.file_path

    def test_idempotent_multiple_writes(self, materializer, sample_agent_spec):
        """Multiple writes with same spec produce same result."""
        # Write same spec three times
        results = [materializer.materialize(sample_agent_spec) for _ in range(3)]

        # All should succeed
        assert all(r.success for r in results)

        # All should reference same file
        assert len(set(r.file_path for r in results)) == 1

        # Only one file should exist
        files = list(materializer.output_path.glob("*.md"))
        assert len(files) == 1

    def test_overwrite_preserves_latest_content(self, materializer, sample_agent_spec):
        """Overwrite preserves only the latest content."""
        # Write with original content
        sample_agent_spec.objective = "Original objective"
        materializer.materialize(sample_agent_spec)

        # Write with updated content
        sample_agent_spec.objective = "Updated objective"
        result = materializer.materialize(sample_agent_spec)

        content = result.file_path.read_text()
        assert "Updated objective" in content
        assert "Original objective" not in content

    def test_overwrite_does_not_create_backup(self, materializer, sample_agent_spec):
        """Overwriting does not create backup files."""
        # First write
        materializer.materialize(sample_agent_spec)

        # Second write
        materializer.materialize(sample_agent_spec)

        # Should not have any backup files
        all_files = list(materializer.output_path.glob("*"))
        assert len(all_files) == 1
        assert all_files[0].name == f"{sample_agent_spec.name}.md"

    def test_overwrite_manually_created_file(self, materializer, sample_agent_spec):
        """Can overwrite a manually created file."""
        # Manually create file with different content
        materializer.ensure_output_dir()
        manual_file = materializer.output_path / f"{sample_agent_spec.name}.md"
        manual_file.write_text("Manual content that should be overwritten")

        # Materialize should overwrite
        result = materializer.materialize(sample_agent_spec)

        content = result.file_path.read_text()
        assert "Manual content" not in content
        assert sample_agent_spec.display_name in content


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests combining all steps."""

    def test_full_materialization_workflow(self, temp_project_dir, sample_agent_spec):
        """Full workflow: resolve path, create dir, write file with permissions."""
        # Step 1: Create materializer with project path
        materializer = AgentMaterializer(temp_project_dir)
        assert materializer.project_dir.is_absolute()

        # Step 2: Ensure directory exists
        output_dir = materializer.ensure_output_dir()
        assert output_dir.exists()

        # Step 3: Materialize spec
        result = materializer.materialize(sample_agent_spec)
        assert result.success
        assert result.file_path.name == f"{sample_agent_spec.name}.md"

        # Step 4: Check permissions
        assert os.access(result.file_path, os.R_OK)
        assert os.access(result.file_path, os.W_OK)

        # Step 5: Test idempotency
        result2 = materializer.materialize(sample_agent_spec)
        assert result2.success
        assert result2.file_path == result.file_path

    def test_multiple_agents_materialization(self, temp_project_dir):
        """Multiple different agents can be materialized."""
        materializer = AgentMaterializer(temp_project_dir)

        specs = []
        for i in range(5):
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"agent-{i}",
                display_name=f"Agent {i}",
                icon="code",
                spec_version="v1",
                objective=f"Objective {i}",
                task_type="coding",
                context={},
                tool_policy={"allowed_tools": ["Read"]},
                max_turns=50,
                timeout_seconds=600,
                source_feature_id=None,
                priority=i + 1,
                tags=[],
            )
            specs.append(spec)

        # Materialize all
        results = [materializer.materialize(spec) for spec in specs]

        # All should succeed
        assert all(r.success for r in results)

        # All files should exist with correct names
        for i, spec in enumerate(specs):
            expected_file = materializer.output_path / f"{spec.name}.md"
            assert expected_file.exists()


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_very_long_agent_name(self, materializer):
        """Very long agent names are handled."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="a" * 200,  # 200 character name
            display_name="Long Name Agent",
            icon="code",
            spec_version="v1",
            objective="Test",
            task_type="coding",
            context={},
            tool_policy={"allowed_tools": ["Read"]},
            max_turns=50,
            timeout_seconds=600,
        )

        result = materializer.materialize(spec)
        assert result.success
        assert result.file_path.exists()

    def test_agent_name_with_numbers(self, materializer):
        """Agent names with numbers work correctly."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="agent-v2-2024-01",
            display_name="Agent V2 2024",
            icon="code",
            spec_version="v1",
            objective="Test",
            task_type="coding",
            context={},
            tool_policy={"allowed_tools": ["Read"]},
            max_turns=50,
            timeout_seconds=600,
        )

        result = materializer.materialize(spec)
        assert result.success
        assert result.file_path.name == "agent-v2-2024-01.md"

    def test_unicode_in_display_name(self, materializer):
        """Unicode in display name doesn't break file writing."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="unicode-test",
            display_name="Unicode Agent: \u2713 \u2717 \u2192",  # Check marks and arrow
            icon="code",
            spec_version="v1",
            objective="Test unicode handling",
            task_type="coding",
            context={},
            tool_policy={"allowed_tools": ["Read"]},
            max_turns=50,
            timeout_seconds=600,
        )

        result = materializer.materialize(spec)
        assert result.success
        content = result.file_path.read_text(encoding="utf-8")
        assert "\u2713" in content  # Check mark should be in content

    def test_empty_context(self, materializer):
        """Empty context is handled."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="empty-context",
            display_name="Empty Context Agent",
            icon="code",
            spec_version="v1",
            objective="Test",
            task_type="coding",
            context={},
            tool_policy={"allowed_tools": ["Read"]},
            max_turns=50,
            timeout_seconds=600,
        )

        result = materializer.materialize(spec)
        assert result.success

    def test_none_optional_fields(self, materializer):
        """None optional fields don't cause errors."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="minimal-spec",
            display_name="Minimal Spec",
            icon="code",
            spec_version="v1",
            objective=None,  # None objective
            task_type="coding",
            context=None,  # None context
            tool_policy={"allowed_tools": []},  # Empty tools
            max_turns=50,
            timeout_seconds=600,
            source_feature_id=None,
            priority=None,
            tags=None,
        )

        result = materializer.materialize(spec)
        assert result.success


# =============================================================================
# Feature #193 Verification Steps
# =============================================================================

class TestFeature193VerificationSteps:
    """Tests verifying all 5 steps for Feature #193."""

    def test_step1_resolves_project_path(self, temp_project_dir):
        """Step 1: Materializer resolves project path."""
        materializer = AgentMaterializer(temp_project_dir)

        # Project path should be resolved to absolute
        assert materializer.project_dir.is_absolute()
        assert materializer.project_dir == temp_project_dir.resolve()

        # Output path should be relative to project
        assert materializer.output_path.is_relative_to(materializer.project_dir)

    def test_step2_ensures_directory_exists(self, temp_project_dir):
        """Step 2: Materializer ensures .claude/agents/generated/ exists."""
        materializer = AgentMaterializer(temp_project_dir)
        expected_dir = temp_project_dir / ".claude" / "agents" / "generated"

        # Directory shouldn't exist initially
        assert not expected_dir.exists()

        # ensure_output_dir should create it
        result_dir = materializer.ensure_output_dir()

        assert expected_dir.exists()
        assert expected_dir.is_dir()
        assert result_dir == expected_dir

    def test_step3_file_written_as_agent_name_md(self, materializer, sample_agent_spec):
        """Step 3: Agent file written as {agent_name}.md."""
        result = materializer.materialize(sample_agent_spec)

        # File should be named {agent_name}.md
        expected_filename = f"{sample_agent_spec.name}.md"
        assert result.file_path.name == expected_filename

        # File should exist
        assert result.file_path.exists()

        # File should be in correct directory
        assert result.file_path.parent == materializer.output_path

    def test_step4_file_permissions_set(self, materializer, sample_agent_spec):
        """Step 4: File permissions set appropriately."""
        result = materializer.materialize(sample_agent_spec)

        # File should be readable and writable
        assert os.access(result.file_path, os.R_OK)
        assert os.access(result.file_path, os.W_OK)

        # File should NOT be executable (markdown files)
        file_stat = os.stat(result.file_path)
        mode = stat.S_IMODE(file_stat.st_mode)
        assert not (mode & stat.S_IXUSR)
        assert not (mode & stat.S_IXGRP)
        assert not (mode & stat.S_IXOTH)

    def test_step5_idempotent_overwrite(self, materializer, sample_agent_spec):
        """Step 5: Existing file with same name is overwritten (idempotent)."""
        # First write
        sample_agent_spec.objective = "First version"
        result1 = materializer.materialize(sample_agent_spec)
        content1 = result1.file_path.read_text()

        # Second write with different content
        sample_agent_spec.objective = "Second version"
        result2 = materializer.materialize(sample_agent_spec)
        content2 = result2.file_path.read_text()

        # Same file path
        assert result1.file_path == result2.file_path

        # Content updated
        assert "Second version" in content2
        assert "First version" not in content2

        # Only one file exists
        files = list(materializer.output_path.glob(f"{sample_agent_spec.name}*"))
        assert len(files) == 1
