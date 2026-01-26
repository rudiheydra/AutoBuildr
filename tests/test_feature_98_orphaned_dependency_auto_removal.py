"""
Tests for Feature #98: Startup health check auto-removes orphaned dependency references.

Verifies that:
1. Insert a feature with dependencies=[999] where 999 does not exist
2. Start the orchestrator
3. Verify the orphaned dependency reference is removed
4. Verify a WARNING level log is emitted with details
5. Verify orchestrator continues to normal operation
"""

import pytest
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parallel_orchestrator import ParallelOrchestrator


class MockFeature:
    """Mock Feature object for testing."""

    def __init__(self, id: int, name: str = None, dependencies: list[int] = None,
                 passes: bool = False, in_progress: bool = False):
        self.id = id
        self.name = name or f"Feature {id}"
        self.dependencies = dependencies if dependencies is not None else []
        self.passes = passes
        self.in_progress = in_progress
        self.priority = id
        self.category = "test"
        self.description = f"Test feature {id}"
        self.steps = []

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "dependencies": self.dependencies,
            "passes": self.passes,
            "in_progress": self.in_progress,
            "priority": self.priority,
            "category": self.category,
            "description": self.description,
            "steps": self.steps,
        }


class TestFeature98VerificationSteps:
    """Tests corresponding to the feature verification steps."""

    @pytest.fixture
    def mock_orchestrator(self, tmp_path):
        """Create a mock orchestrator with mocked database session."""
        with patch('parallel_orchestrator.create_database') as mock_create_db:
            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            return orchestrator, mock_session_maker

    def test_step1_insert_feature_with_nonexistent_dependency(self, mock_orchestrator):
        """Step 1: Insert a feature with dependencies=[999] where 999 does not exist.

        Verifies that we can create a feature with an orphaned dependency reference.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with orphaned dependency (999 doesn't exist)
        feature_with_orphan = MockFeature(1, dependencies=[999])
        features = [feature_with_orphan]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Verify the feature has the orphaned dependency
        assert 999 in feature_with_orphan.dependencies
        assert len(features) == 1  # Only 1 feature exists

    def test_step2_start_orchestrator_health_check(self, mock_orchestrator):
        """Step 2: Start the orchestrator.

        Verifies that the health check runs on startup.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with orphaned dependency
        feature_with_orphan = MockFeature(1, dependencies=[999])
        features = [feature_with_orphan]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_orphan
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check (simulates startup)
        result = orchestrator._run_dependency_health_check()

        # Health check should complete successfully
        assert result is True

    def test_step3_orphaned_dependency_removed(self, mock_orchestrator):
        """Step 3: Verify the orphaned dependency reference is removed.

        Verifies that the orphaned dependency (999) is removed from the feature.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with orphaned dependency
        feature_with_orphan = MockFeature(1, dependencies=[999])
        features = [feature_with_orphan]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_orphan
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        orchestrator._run_dependency_health_check()

        # Verify orphaned dependency was removed
        assert 999 not in feature_with_orphan.dependencies
        assert feature_with_orphan.dependencies == []

        # Verify session.commit() was called (changes were persisted)
        mock_session.commit.assert_called()

    def test_step4_warning_log_emitted(self, mock_orchestrator, caplog):
        """Step 4: Verify a WARNING level log is emitted with details.

        Verifies that a WARNING log is emitted when orphaned dependency is removed.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with orphaned dependency
        feature_with_orphan = MockFeature(1, dependencies=[999])
        features = [feature_with_orphan]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_orphan
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Capture logs at WARNING level
        with caplog.at_level(logging.WARNING):
            orchestrator._run_dependency_health_check()

        # Verify WARNING log was emitted
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1, "Expected at least one WARNING log"

        # Verify log contains expected details
        log_message = warning_logs[0].message
        assert "orphaned" in log_message.lower() or "non-existent" in log_message.lower()
        assert "999" in log_message
        assert "Feature #1" in log_message or "feature_id" in log_message.lower()

    def test_step5_orchestrator_continues_normal_operation(self, mock_orchestrator):
        """Step 5: Verify orchestrator continues to normal operation.

        Verifies that the orchestrator returns True and can continue.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with orphaned dependency
        feature_with_orphan = MockFeature(1, dependencies=[999])
        features = [feature_with_orphan]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_orphan
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Orchestrator should continue (return True)
        assert result is True

        # Session should be properly closed
        mock_session.close.assert_called_once()


class TestMultipleOrphanedDependencies:
    """Tests for handling multiple orphaned dependencies."""

    @pytest.fixture
    def mock_orchestrator(self, tmp_path):
        """Create a mock orchestrator with mocked database session."""
        with patch('parallel_orchestrator.create_database') as mock_create_db:
            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            return orchestrator, mock_session_maker

    def test_multiple_orphaned_deps_in_one_feature(self, mock_orchestrator, caplog):
        """Multiple orphaned dependencies in one feature are all removed."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Feature with multiple orphaned dependencies
        feature = MockFeature(1, dependencies=[999, 888, 777])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature]

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            result = orchestrator._run_dependency_health_check()

        # All orphaned deps should be removed
        assert feature.dependencies == []
        assert result is True

        # WARNING should be logged
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1

    def test_orphaned_deps_in_multiple_features(self, mock_orchestrator, caplog):
        """Orphaned dependencies in multiple features are all removed."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Multiple features with orphaned dependencies
        feature1 = MockFeature(1, dependencies=[999])
        feature2 = MockFeature(2, dependencies=[888])
        features = [feature1, feature2]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Setup filter to return correct feature
        def mock_filter_side_effect(condition):
            filter_mock = MagicMock()
            # Default to feature1
            filter_mock.first.return_value = feature1
            # Try to determine which feature is being queried
            for f in features:
                try:
                    if hasattr(condition, 'right') and hasattr(condition.right, 'value'):
                        if condition.right.value == f.id:
                            filter_mock.first.return_value = f
                            return filter_mock
                except:
                    pass
            return filter_mock

        mock_query.filter.side_effect = mock_filter_side_effect
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            result = orchestrator._run_dependency_health_check()

        # Both features should have orphaned deps removed
        assert 999 not in feature1.dependencies
        assert 888 not in feature2.dependencies
        assert result is True

    def test_mix_of_valid_and_orphaned_deps(self, mock_orchestrator, caplog):
        """Valid dependencies are preserved while orphaned ones are removed."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Feature with mix of valid and orphaned dependencies
        feature1 = MockFeature(1, dependencies=[2, 999])  # 2 is valid, 999 is orphaned
        feature2 = MockFeature(2, dependencies=[])  # Valid feature
        features = [feature1, feature2]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature1
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            result = orchestrator._run_dependency_health_check()

        # Orphaned dep should be removed but valid dep preserved
        assert 999 not in feature1.dependencies
        assert 2 in feature1.dependencies
        assert result is True


class TestWarningLogDetails:
    """Tests for the WARNING log content and format."""

    @pytest.fixture
    def mock_orchestrator(self, tmp_path):
        """Create a mock orchestrator with mocked database session."""
        with patch('parallel_orchestrator.create_database') as mock_create_db:
            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            return orchestrator, mock_session_maker

    def test_warning_contains_feature_id(self, mock_orchestrator, caplog):
        """WARNING log contains the feature ID."""
        orchestrator, mock_session_maker = mock_orchestrator

        feature = MockFeature(42, dependencies=[999])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature]

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            orchestrator._run_dependency_health_check()

        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1
        assert "42" in warning_logs[0].message or "#42" in warning_logs[0].message

    def test_warning_contains_orphaned_ids(self, mock_orchestrator, caplog):
        """WARNING log contains the orphaned dependency IDs."""
        orchestrator, mock_session_maker = mock_orchestrator

        feature = MockFeature(1, dependencies=[999, 888])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature]

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            orchestrator._run_dependency_health_check()

        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1
        log_msg = warning_logs[0].message
        assert "999" in log_msg
        assert "888" in log_msg

    def test_warning_contains_original_and_new_deps(self, mock_orchestrator, caplog):
        """WARNING log contains both original and new dependency lists."""
        orchestrator, mock_session_maker = mock_orchestrator

        feature = MockFeature(1, dependencies=[2, 999])  # 2 is valid, 999 is orphaned
        feature_existing = MockFeature(2, dependencies=[])
        features = [feature, feature_existing]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            orchestrator._run_dependency_health_check()

        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1
        log_msg = warning_logs[0].message

        # Should contain original deps (mentioning 2 and 999)
        assert "original_deps" in log_msg.lower() or ("[2, 999]" in log_msg or "[999]" in log_msg)
        # Should contain new deps (just [2])
        assert "new_deps" in log_msg.lower() or "[2]" in log_msg


class TestEdgeCases:
    """Tests for edge cases in orphaned dependency handling."""

    @pytest.fixture
    def mock_orchestrator(self, tmp_path):
        """Create a mock orchestrator with mocked database session."""
        with patch('parallel_orchestrator.create_database') as mock_create_db:
            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            return orchestrator, mock_session_maker

    def test_empty_dependencies_list(self, mock_orchestrator):
        """Feature with empty dependencies doesn't cause issues."""
        orchestrator, mock_session_maker = mock_orchestrator

        feature = MockFeature(1, dependencies=[])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature]
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        result = orchestrator._run_dependency_health_check()

        assert result is True
        assert feature.dependencies == []

    def test_all_dependencies_orphaned(self, mock_orchestrator, caplog):
        """All dependencies being orphaned results in empty list."""
        orchestrator, mock_session_maker = mock_orchestrator

        feature = MockFeature(1, dependencies=[999, 888, 777])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature]

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            result = orchestrator._run_dependency_health_check()

        assert result is True
        assert feature.dependencies == []

        # WARNING should be logged
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 1

    def test_no_features_in_database(self, mock_orchestrator):
        """Empty database is handled gracefully."""
        orchestrator, mock_session_maker = mock_orchestrator

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = []  # No features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        result = orchestrator._run_dependency_health_check()

        assert result is True

    def test_orphan_combined_with_self_reference(self, mock_orchestrator, caplog):
        """Both orphaned dependency and self-reference are auto-fixed."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Feature with both self-reference and orphaned dependency
        feature = MockFeature(1, dependencies=[1, 999])  # 1 is self-ref, 999 is orphaned

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature]

        mock_filter = MagicMock()
        mock_filter.first.return_value = feature
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        with caplog.at_level(logging.WARNING):
            result = orchestrator._run_dependency_health_check()

        # Both issues should be fixed
        assert 1 not in feature.dependencies  # Self-reference removed
        assert 999 not in feature.dependencies  # Orphaned removed
        assert result is True

        # Should have WARNING logs for both issues
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_logs) >= 2  # One for self-ref, one for orphaned


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
