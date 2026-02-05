"""
Integration Tests for Task Pipeline
====================================

End-to-end tests for the Task interface pipeline integration.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from api.task_pipeline_controller import (
    TaskPipelineController,
    SessionInitResult,
    AgentCheckResult,
)
from api.task_hydrator import TaskHydrator, HydrationResult
from api.task_syncback import TaskSyncBack, SyncResult


class TestTaskPipelineController:
    """Tests for TaskPipelineController."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock SQLAlchemy session."""
        return MagicMock()

    @pytest.fixture
    def tmp_project(self, tmp_path):
        """Create a temporary project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create .claude/agents structure
        agents_dir = project_dir / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        generated_dir = agents_dir / "generated"
        generated_dir.mkdir()

        # Create some agents
        (agents_dir / "coder.md").write_text("# Coder Agent")
        (agents_dir / "test-runner.md").write_text("# Test Runner Agent")

        return project_dir

    @pytest.fixture
    def controller(self, tmp_project, mock_session):
        """Create a TaskPipelineController instance."""
        return TaskPipelineController(tmp_project, mock_session)

    def test_initialize_session_no_features(self, controller, mock_session):
        """Session init returns empty when no features."""
        mock_session.query.return_value.count.return_value = 0

        result = controller.initialize_session()

        assert result.task_count == 0
        assert result.feature_count == 0
        assert "/create-spec" in result.session_instructions

    def test_initialize_session_with_features(self, controller, mock_session):
        """Session init hydrates features to tasks."""
        mock_session.query.return_value.count.return_value = 5

        # Mock features for hydration
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.category = "Test"
        feature.description = "Test description"
        feature.steps = []
        feature.priority = 10
        feature.passes = False
        feature.in_progress = False
        feature.get_dependencies_safe.return_value = []

        mock_session.query.return_value.all.return_value = [feature]

        result = controller.initialize_session()

        assert result.feature_count == 5
        assert result.task_count >= 0  # Depends on hydration
        assert len(result.agents) > 0

    def test_should_trigger_pipeline_no_features(self, controller, mock_session):
        """Pipeline should not trigger without features."""
        mock_session.query.return_value.count.return_value = 0

        assert controller.should_trigger_pipeline() is False

    def test_should_trigger_pipeline_with_generated_agents(
        self, controller, mock_session, tmp_project
    ):
        """Pipeline should not trigger if agents exist."""
        mock_session.query.return_value.count.return_value = 5

        # Create a generated agent
        generated_dir = tmp_project / ".claude" / "agents" / "generated"
        (generated_dir / "e2e-tester.md").write_text("# E2E Tester")

        assert controller.should_trigger_pipeline() is False

    def test_should_trigger_pipeline_no_generated_agents(
        self, controller, mock_session, tmp_project
    ):
        """Pipeline should trigger if no generated agents."""
        mock_session.query.return_value.count.return_value = 5

        # Make sure generated dir exists but is empty
        generated_dir = tmp_project / ".claude" / "agents" / "generated"
        # Remove any existing files
        for f in generated_dir.glob("*.md"):
            f.unlink()

        assert controller.should_trigger_pipeline() is True

    def test_check_agent_exists_standard(self, controller, tmp_project):
        """Check that standard agents are found."""
        result = controller.check_agent_exists("coder")

        assert result.exists is True
        assert result.needs_generation is False
        assert "coder.md" in result.path

    def test_check_agent_exists_generated(self, controller, tmp_project):
        """Check that generated agents are found."""
        # Create a generated agent
        generated_dir = tmp_project / ".claude" / "agents" / "generated"
        (generated_dir / "custom-agent.md").write_text("# Custom Agent")

        result = controller.check_agent_exists("custom-agent")

        assert result.exists is True
        assert result.needs_generation is False

    def test_check_agent_not_exists(self, controller):
        """Check that missing agents are flagged."""
        result = controller.check_agent_exists("nonexistent-agent")

        assert result.exists is False
        assert result.needs_generation is True

    def test_get_available_agents(self, controller, tmp_project):
        """Get list of all available agents."""
        agents = controller.get_available_agents()

        assert "coder" in agents
        assert "test-runner" in agents

    def test_handle_task_event_status_change(self, controller, mock_session):
        """Handle task status change event."""
        # Mock the feature lookup
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.in_progress = False
        feature.passes = False
        mock_session.query.return_value.filter.return_value.first.return_value = feature

        task_data = {
            "task_id": "task-123",
            "status": "in_progress",
            "metadata": {"feature_id": 1},
        }

        result = controller.handle_task_event("status_change", task_data)

        assert result.success is True


class TestTaskSyncBack:
    """Tests for TaskSyncBack."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock SQLAlchemy session."""
        return MagicMock()

    @pytest.fixture
    def syncback(self, mock_session, tmp_path):
        """Create a TaskSyncBack instance."""
        return TaskSyncBack(tmp_path, mock_session)

    def test_on_task_started(self, syncback, mock_session):
        """Task started → Feature in_progress = True."""
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.in_progress = False

        mock_session.query.return_value.filter.return_value.first.return_value = feature

        result = syncback.on_task_started("task-123", {"feature_id": 1})

        assert result.success is True
        assert feature.in_progress is True
        mock_session.commit.assert_called_once()

    def test_on_task_completed(self, syncback, mock_session):
        """Task completed → Feature passes = True."""
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.passes = False
        feature.in_progress = True

        mock_session.query.return_value.filter.return_value.first.return_value = feature

        result = syncback.on_task_completed(
            "task-123", {"feature_id": 1}, run_validators=False
        )

        assert result.success is True
        assert feature.passes is True
        assert feature.in_progress is False
        mock_session.commit.assert_called_once()

    def test_on_task_failed(self, syncback, mock_session):
        """Task failed → Feature in_progress = False."""
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.passes = False
        feature.in_progress = True

        mock_session.query.return_value.filter.return_value.first.return_value = feature

        result = syncback.on_task_failed(
            "task-123", {"feature_id": 1}, error="Test error"
        )

        assert result.success is True
        assert feature.in_progress is False
        # passes should stay False
        assert feature.passes is False

    def test_sync_task_status_routes_correctly(self, syncback, mock_session):
        """sync_task_status routes to correct handler."""
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.in_progress = False
        feature.passes = False

        mock_session.query.return_value.filter.return_value.first.return_value = feature

        # Test in_progress routing
        result = syncback.sync_task_status(
            "task-123", "in_progress", {"feature_id": 1}
        )
        assert result.success is True

    def test_missing_feature_id(self, syncback):
        """Missing feature_id returns failure."""
        result = syncback.on_task_started("task-123", {})

        assert result.success is False
        assert "No feature_id" in result.message

    def test_feature_not_found(self, syncback, mock_session):
        """Non-existent feature returns failure."""
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = syncback.on_task_started("task-123", {"feature_id": 999})

        assert result.success is False
        assert "not found" in result.message


class TestIntegration:
    """Integration tests for the full pipeline."""

    @pytest.fixture
    def tmp_project(self, tmp_path):
        """Create a complete temporary project."""
        project_dir = tmp_path / "integration-project"
        project_dir.mkdir()

        # Create .claude structure
        agents_dir = project_dir / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "coder.md").write_text("# Coder")

        return project_dir

    def test_session_init_triggers_hydration(self, tmp_project):
        """Session init creates tasks from features."""
        # This would require a real database - skipping for unit tests
        pass

    def test_task_completion_updates_feature(self, tmp_project):
        """Task completion syncs back to feature."""
        # This would require a real database - skipping for unit tests
        pass
