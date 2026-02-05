"""
API Endpoint Tests for Task Pipeline
=====================================

Tests for the FastAPI task pipeline endpoints.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from server.routers.task_pipeline import router
from api.database import get_db


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def app(mock_db):
    """Create a test FastAPI app with the task pipeline router."""
    app = FastAPI()
    app.include_router(router)

    # Override the get_db dependency
    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestInitEndpoint:
    """Tests for POST /api/task-pipeline/init."""

    def test_init_success(self, client, mock_db, tmp_path):
        """Successful session initialization."""
        # Create project directory
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / ".claude" / "agents").mkdir(parents=True)

        # Configure mock
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.all.return_value = []

        response = client.post(
            "/api/task-pipeline/init",
            json={
                "project_dir": str(project_dir),
                "session_id": "test-session",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "tasks_hydrated" in data
        assert "instructions" in data
        assert data["tasks_hydrated"] == 0

    def test_init_with_features(self, client, mock_db, tmp_path):
        """Session init with existing features."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / ".claude" / "agents").mkdir(parents=True)

        # Mock feature
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.category = "Test"
        feature.description = "Test description"
        feature.steps = ["Step 1"]
        feature.priority = 10
        feature.passes = False
        feature.in_progress = False
        feature.get_dependencies_safe.return_value = []

        mock_db.query.return_value.count.return_value = 1
        mock_db.query.return_value.all.return_value = [feature]

        response = client.post(
            "/api/task-pipeline/init",
            json={
                "project_dir": str(project_dir),
                "session_id": "test-session",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tasks_hydrated"] == 1
        assert data["feature_count"] == 1

    def test_init_invalid_project(self, client, mock_db):
        """Invalid project directory returns error."""
        response = client.post(
            "/api/task-pipeline/init",
            json={
                "project_dir": "/nonexistent/path/that/does/not/exist",
                "session_id": "test-session",
            },
        )

        assert response.status_code == 400


class TestSyncEndpoint:
    """Tests for POST /api/task-pipeline/sync."""

    def test_sync_status_change(self, client, mock_db, tmp_path):
        """Sync task status change."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Mock feature lookup
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.in_progress = False
        mock_db.query.return_value.filter.return_value.first.return_value = feature

        response = client.post(
            "/api/task-pipeline/sync",
            json={
                "task_id": "task-123",
                "status": "in_progress",
                "session_id": "test-session",
                "tool_input": {
                    "taskId": "task-123",
                    "status": "in_progress",
                    "metadata": {"feature_id": 1, "project_dir": str(project_dir)},
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["synced"] is True

    def test_sync_missing_feature(self, client, mock_db, tmp_path):
        """Sync with missing feature returns error."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        mock_db.query.return_value.filter.return_value.first.return_value = None

        response = client.post(
            "/api/task-pipeline/sync",
            json={
                "task_id": "task-123",
                "status": "in_progress",
                "session_id": "test-session",
                "tool_input": {
                    "taskId": "task-123",
                    "status": "in_progress",
                    "metadata": {"feature_id": 999, "project_dir": str(project_dir)},
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["synced"] is False


class TestCheckAgentEndpoint:
    """Tests for POST /api/task-pipeline/check-agent."""

    def test_check_existing_agent(self, client, mock_db, tmp_path):
        """Check that existing agent is found."""
        project_dir = tmp_path / "test-project"
        agents_dir = project_dir / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "coder.md").write_text("# Coder")

        response = client.post(
            "/api/task-pipeline/check-agent",
            json={
                "agent_type": "coder",
                "project_dir": str(project_dir),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["needs_generation"] is False

    def test_check_missing_agent(self, client, mock_db, tmp_path):
        """Check that missing agent is flagged."""
        project_dir = tmp_path / "test-project"
        agents_dir = project_dir / ".claude" / "agents"
        agents_dir.mkdir(parents=True)

        response = client.post(
            "/api/task-pipeline/check-agent",
            json={
                "agent_type": "nonexistent",
                "project_dir": str(project_dir),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["needs_generation"] is True

    def test_check_generated_agent(self, client, mock_db, tmp_path):
        """Check that generated agents are found."""
        project_dir = tmp_path / "test-project"
        agents_dir = project_dir / ".claude" / "agents"
        generated_dir = agents_dir / "generated"
        generated_dir.mkdir(parents=True)
        (generated_dir / "custom-agent.md").write_text("# Custom Agent")

        response = client.post(
            "/api/task-pipeline/check-agent",
            json={
                "agent_type": "custom-agent",
                "project_dir": str(project_dir),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["needs_generation"] is False


class TestValidateEndpoint:
    """Tests for POST /api/task-pipeline/validate."""

    def test_validate_no_validators(self, client, mock_db, tmp_path):
        """Validation passes when no validators configured."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        response = client.post(
            "/api/task-pipeline/validate",
            json={
                "tool_name": "Edit",
                "tool_result": {"success": True},
                "cwd": str(project_dir),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_write_tool(self, client, mock_db, tmp_path):
        """Validate Write tool result."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        response = client.post(
            "/api/task-pipeline/validate",
            json={
                "tool_name": "Write",
                "tool_result": {"file_path": "/test/file.py", "success": True},
                "cwd": str(project_dir),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


class TestTriggerEndpoint:
    """Tests for POST /api/task-pipeline/trigger."""

    def test_trigger_invalid_project(self, client, mock_db):
        """Trigger with invalid project returns error."""
        response = client.post(
            "/api/task-pipeline/trigger",
            json={
                "capability": "e2e_testing",
                "context": {},
                "project_dir": "/nonexistent/path",
            },
        )

        assert response.status_code == 400


class TestHealthEndpoint:
    """Tests for GET /api/task-pipeline/health."""

    def test_health_check(self, client):
        """Health endpoint returns healthy status."""
        response = client.get("/api/task-pipeline/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "task-pipeline"
