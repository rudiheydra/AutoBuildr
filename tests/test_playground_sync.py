"""
Tests for PlaygroundSync module.

Tests the automatic synchronization of generated agents to agent-playground.
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from api.playground_sync import PlaygroundSync, SyncResult, sync_to_playground


class TestPlaygroundSync:
    """Tests for PlaygroundSync class."""

    def test_init_with_explicit_path(self, tmp_path: Path):
        """Test initialization with explicit playground path."""
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        sync = PlaygroundSync(
            project_dir=tmp_path / "project",
            playground_path=playground,
        )

        assert sync.playground_path == playground
        assert sync.agents_dir == playground / "agents"
        assert sync.is_available()

    def test_init_with_env_var(self, tmp_path: Path):
        """Test initialization with environment variable."""
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        with patch.dict(os.environ, {"AGENT_PLAYGROUND_PATH": str(playground)}):
            sync = PlaygroundSync(project_dir=tmp_path / "project")
            assert sync.playground_path == playground

    def test_init_without_playground(self, tmp_path: Path):
        """Test initialization when playground is not available."""
        # Remove common location env vars
        with patch.dict(os.environ, {"AGENT_PLAYGROUND_PATH": ""}, clear=False):
            sync = PlaygroundSync(
                project_dir=tmp_path / "nonexistent",
                playground_path=None,
            )
            # Will search common locations, likely not find any
            # The test just verifies it doesn't crash

    def test_namespace_from_project_name(self, tmp_path: Path):
        """Test namespace defaults to project directory name."""
        project = tmp_path / "my-test-project"
        project.mkdir()

        sync = PlaygroundSync(project_dir=project)
        assert sync.namespace == "my-test-project"

    def test_namespace_from_env_var(self, tmp_path: Path):
        """Test namespace from environment variable."""
        with patch.dict(os.environ, {"AGENT_PLAYGROUND_NAMESPACE": "custom-namespace"}):
            sync = PlaygroundSync(project_dir=tmp_path)
            assert sync.namespace == "custom-namespace"

    def test_namespace_explicit(self, tmp_path: Path):
        """Test explicit namespace parameter."""
        sync = PlaygroundSync(
            project_dir=tmp_path,
            namespace="explicit-namespace",
        )
        assert sync.namespace == "explicit-namespace"

    def test_sync_agents_empty_list(self, tmp_path: Path):
        """Test syncing empty agent list."""
        sync = PlaygroundSync(project_dir=tmp_path)
        result = sync.sync_agents([])

        assert result.success is True
        assert result.synced_files == []
        assert result.error is None

    def test_sync_agents_playground_unavailable(self, tmp_path: Path):
        """Test syncing when playground is not available."""
        project = tmp_path / "project"
        project.mkdir()
        agent_file = project / "agent.md"
        agent_file.write_text("# Test Agent")

        sync = PlaygroundSync(
            project_dir=project,
            playground_path=tmp_path / "nonexistent",
        )

        result = sync.sync_agents([str(agent_file)])

        assert result.success is False
        assert "not available" in result.error.lower()

    def test_sync_agents_success(self, tmp_path: Path):
        """Test successful agent sync."""
        # Setup playground
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        # Setup project with agent
        project = tmp_path / "my-project"
        project.mkdir()
        agent_file = project / "test-agent.md"
        agent_file.write_text("---\nname: Test Agent\n---\n# Test Agent")

        sync = PlaygroundSync(
            project_dir=project,
            playground_path=playground,
            auto_import=False,  # Disable API call
        )

        result = sync.sync_agents([str(agent_file)])

        assert result.success is True
        assert len(result.synced_files) == 1
        assert result.namespace == "my-project"

        # Check file was copied with namespace prefix
        dest_file = playground / "agents" / "my-project--test-agent.md"
        assert dest_file.exists()
        assert "Test Agent" in dest_file.read_text()

    def test_sync_agents_multiple_files(self, tmp_path: Path):
        """Test syncing multiple agent files."""
        # Setup playground
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        # Setup project with multiple agents
        project = tmp_path / "project"
        project.mkdir()
        agent1 = project / "agent1.md"
        agent1.write_text("# Agent 1")
        agent2 = project / "agent2.md"
        agent2.write_text("# Agent 2")

        sync = PlaygroundSync(
            project_dir=project,
            playground_path=playground,
            auto_import=False,
        )

        result = sync.sync_agents([str(agent1), str(agent2)])

        assert result.success is True
        assert len(result.synced_files) == 2

    def test_sync_agents_file_not_found(self, tmp_path: Path):
        """Test syncing with non-existent file."""
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        sync = PlaygroundSync(
            project_dir=tmp_path,
            playground_path=playground,
            auto_import=False,
        )

        result = sync.sync_agents(["/nonexistent/agent.md"])

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_cleanup_namespace(self, tmp_path: Path):
        """Test cleanup of namespace agents."""
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        agents_dir = playground / "agents"
        agents_dir.mkdir()

        # Create some files
        (agents_dir / "my-project--agent1.md").write_text("# Agent 1")
        (agents_dir / "my-project--agent2.md").write_text("# Agent 2")
        (agents_dir / "other-project--agent.md").write_text("# Other")

        sync = PlaygroundSync(
            project_dir=tmp_path / "my-project",
            playground_path=playground,
            namespace="my-project",
        )

        removed = sync.cleanup_namespace()

        assert removed == 2
        assert not (agents_dir / "my-project--agent1.md").exists()
        assert not (agents_dir / "my-project--agent2.md").exists()
        # Other project's agent should remain
        assert (agents_dir / "other-project--agent.md").exists()


class TestSyncToPlaygroundFunction:
    """Tests for the sync_to_playground convenience function."""

    def test_sync_to_playground_basic(self, tmp_path: Path):
        """Test convenience function."""
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        project = tmp_path / "project"
        project.mkdir()
        agent = project / "agent.md"
        agent.write_text("# Agent")

        result = sync_to_playground(
            project_dir=project,
            agent_files=[str(agent)],
            playground_path=playground,
            auto_import=False,
        )

        assert result.success is True
        assert len(result.synced_files) == 1


class TestPlaygroundSyncAPI:
    """Tests for API import functionality."""

    def test_api_import_disabled(self, tmp_path: Path):
        """Test that API import can be disabled."""
        playground = tmp_path / "agent-playground"
        playground.mkdir()
        (playground / "agents").mkdir()

        sync = PlaygroundSync(
            project_dir=tmp_path,
            playground_path=playground,
            auto_import=False,
        )

        assert sync.auto_import is False

    def test_api_import_env_var(self, tmp_path: Path):
        """Test API import controlled by env var."""
        with patch.dict(os.environ, {"AGENT_PLAYGROUND_AUTO_IMPORT": "false"}):
            sync = PlaygroundSync(project_dir=tmp_path)
            assert sync.auto_import is False

        with patch.dict(os.environ, {"AGENT_PLAYGROUND_AUTO_IMPORT": "true"}):
            sync = PlaygroundSync(project_dir=tmp_path)
            assert sync.auto_import is True
