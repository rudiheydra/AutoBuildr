"""
Unit Tests for Task Hydrator
============================

Tests for the TaskHydrator class that converts Features to Claude Code Tasks.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.task_hydrator import (
    TaskHydrator,
    TaskCreatePayload,
    HydrationResult,
)


class TestTaskCreatePayload:
    """Tests for TaskCreatePayload dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        payload = TaskCreatePayload(
            subject="Implement: Login flow",
            description="Test description",
            activeForm="Implementing login flow",
            metadata={"feature_id": 1},
        )

        result = payload.to_dict()

        assert result["subject"] == "Implement: Login flow"
        assert result["description"] == "Test description"
        assert result["activeForm"] == "Implementing login flow"
        assert result["metadata"]["feature_id"] == 1

    def test_default_metadata(self):
        """Test default empty metadata."""
        payload = TaskCreatePayload(
            subject="Test",
            description="Desc",
            activeForm="Testing",
        )

        assert payload.metadata == {}


class TestHydrationResult:
    """Tests for HydrationResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        task = TaskCreatePayload(
            subject="Test",
            description="Desc",
            activeForm="Testing",
            metadata={"feature_id": 1},
        )
        result = HydrationResult(
            tasks=[task],
            task_count=1,
            feature_count=5,
            dependency_map={1: [0]},
        )

        output = result.to_dict()

        assert output["task_count"] == 1
        assert output["feature_count"] == 5
        assert len(output["tasks"]) == 1
        assert output["dependency_map"]["1"] == [0]


class TestTaskHydrator:
    """Tests for TaskHydrator class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock SQLAlchemy session."""
        return MagicMock()

    @pytest.fixture
    def mock_feature(self):
        """Create a mock Feature object."""
        feature = MagicMock()
        feature.id = 1
        feature.name = "Login Flow"
        feature.category = "Authentication"
        feature.description = "Implement user login"
        feature.steps = ["Step 1", "Step 2"]
        feature.priority = 10
        feature.passes = False
        feature.in_progress = False
        feature.get_dependencies_safe.return_value = []
        return feature

    @pytest.fixture
    def hydrator(self, mock_session, tmp_path):
        """Create a TaskHydrator instance."""
        return TaskHydrator(tmp_path, mock_session)

    def test_hydrate_creates_tasks_for_pending_features(
        self, hydrator, mock_session, mock_feature
    ):
        """3 pending features → 3 Task payloads."""
        features = [mock_feature]
        for i in range(2):
            f = MagicMock()
            f.id = i + 2
            f.name = f"Feature {i + 2}"
            f.category = "Test"
            f.description = f"Description {i + 2}"
            f.steps = []
            f.priority = 20
            f.passes = False
            f.in_progress = False
            f.get_dependencies_safe.return_value = []
            features.append(f)

        mock_session.query.return_value.all.return_value = features

        result = hydrator.hydrate()

        assert result.task_count == 3
        assert result.feature_count == 3
        assert len(result.tasks) == 3

    def test_hydrate_excludes_passing_features(
        self, hydrator, mock_session, mock_feature
    ):
        """Passing features not hydrated."""
        passing_feature = MagicMock()
        passing_feature.id = 2
        passing_feature.name = "Passing Feature"
        passing_feature.passes = True
        passing_feature.in_progress = False
        passing_feature.get_dependencies_safe.return_value = []

        mock_session.query.return_value.all.return_value = [
            mock_feature,
            passing_feature,
        ]

        result = hydrator.hydrate()

        assert result.task_count == 1
        assert result.feature_count == 2

    def test_hydrate_excludes_in_progress_features(
        self, hydrator, mock_session, mock_feature
    ):
        """In-progress features not hydrated."""
        in_progress_feature = MagicMock()
        in_progress_feature.id = 2
        in_progress_feature.name = "In Progress Feature"
        in_progress_feature.passes = False
        in_progress_feature.in_progress = True
        in_progress_feature.get_dependencies_safe.return_value = []

        mock_session.query.return_value.all.return_value = [
            mock_feature,
            in_progress_feature,
        ]

        result = hydrator.hydrate()

        assert result.task_count == 1

    def test_dependency_mapping(self, hydrator, mock_session):
        """Feature.dependencies → Task.blockedBy."""
        # Feature 1 has no dependencies
        feature1 = MagicMock()
        feature1.id = 1
        feature1.name = "Feature 1"
        feature1.category = "Test"
        feature1.description = "Desc 1"
        feature1.steps = []
        feature1.priority = 10
        feature1.passes = False
        feature1.in_progress = False
        feature1.get_dependencies_safe.return_value = []

        # Feature 2 depends on Feature 1
        feature2 = MagicMock()
        feature2.id = 2
        feature2.name = "Feature 2"
        feature2.category = "Test"
        feature2.description = "Desc 2"
        feature2.steps = []
        feature2.priority = 20
        feature2.passes = False
        feature2.in_progress = False
        feature2.get_dependencies_safe.return_value = [1]

        mock_session.query.return_value.all.return_value = [feature1, feature2]

        result = hydrator.hydrate()

        assert result.task_count == 2
        # Feature 2 (index 1) should be blocked by Feature 1 (index 0)
        assert 2 in result.dependency_map
        assert 0 in result.dependency_map[2]

    def test_dependency_skips_passing_blockers(self, hydrator, mock_session):
        """Dependencies on passing features are not mapped."""
        # Feature 1 is passing
        feature1 = MagicMock()
        feature1.id = 1
        feature1.name = "Feature 1"
        feature1.passes = True
        feature1.in_progress = False
        feature1.get_dependencies_safe.return_value = []

        # Feature 2 depends on Feature 1
        feature2 = MagicMock()
        feature2.id = 2
        feature2.name = "Feature 2"
        feature2.category = "Test"
        feature2.description = "Desc 2"
        feature2.steps = []
        feature2.priority = 20
        feature2.passes = False
        feature2.in_progress = False
        feature2.get_dependencies_safe.return_value = [1]

        mock_session.query.return_value.all.return_value = [feature1, feature2]

        result = hydrator.hydrate()

        assert result.task_count == 1
        # Feature 2 should NOT have blockers (Feature 1 already passes)
        assert 2 not in result.dependency_map

    def test_hydrate_with_limit(self, hydrator, mock_session):
        """Limit parameter caps number of tasks."""
        features = []
        for i in range(10):
            f = MagicMock()
            f.id = i + 1
            f.name = f"Feature {i + 1}"
            f.category = "Test"
            f.description = f"Desc {i + 1}"
            f.steps = []
            f.priority = i
            f.passes = False
            f.in_progress = False
            f.get_dependencies_safe.return_value = []
            features.append(f)

        mock_session.query.return_value.all.return_value = features

        result = hydrator.hydrate(limit=3)

        assert result.task_count == 3
        assert result.feature_count == 10

    def test_to_active_form_conversions(self, hydrator):
        """Test present continuous conversions."""
        assert hydrator._to_active_form("Add login") == "Adding login"
        assert hydrator._to_active_form("Create user") == "Creating user"
        assert hydrator._to_active_form("Implement feature") == "Implementing feature"
        assert hydrator._to_active_form("Fix bug") == "Fixing bug"
        assert hydrator._to_active_form("Update config") == "Updating config"
        assert hydrator._to_active_form("Remove old code") == "Removing old code"
        # Default case
        assert hydrator._to_active_form("Login flow") == "Implementing Login flow"

    def test_get_hydration_instructions_no_tasks(self, hydrator):
        """Instructions when no tasks to hydrate."""
        result = HydrationResult(
            tasks=[],
            task_count=0,
            feature_count=5,
            dependency_map={},
        )

        instructions = hydrator.get_hydration_instructions(result)

        assert "All features are passing" in instructions

    def test_get_hydration_instructions_with_tasks(self, hydrator):
        """Instructions when tasks exist."""
        task = TaskCreatePayload(
            subject="Implement: Login",
            description="Test",
            activeForm="Implementing Login",
            metadata={"feature_id": 1},
        )
        result = HydrationResult(
            tasks=[task],
            task_count=1,
            feature_count=5,
            dependency_map={},
        )

        instructions = hydrator.get_hydration_instructions(result)

        assert "1 tasks" in instructions
        assert "Implement: Login" in instructions
        assert "TaskList" in instructions
