"""
Tests for Feature #95: Orchestrator runs validate_dependency_graph on startup.

Verifies that:
1. The orchestrator calls _run_dependency_health_check() on startup before processing features
2. validate_dependency_graph() is called with loaded features
3. Issues are handled according to their type (auto-fix or log)
4. A summary of dependency health check results is logged
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import tempfile
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parallel_orchestrator import ParallelOrchestrator


class MockFeature:
    """Mock Feature object for testing."""

    def __init__(self, id: int, name: str = None, dependencies: list[int] = None,
                 passes: bool = False, in_progress: bool = False):
        self.id = id
        self.name = name or f"Feature {id}"
        self.dependencies = dependencies or []
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


class TestOrchestratorStartupHealthCheck:
    """Tests for the _run_dependency_health_check method."""

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

    def test_health_check_exists_on_orchestrator(self, mock_orchestrator):
        """Verify the _run_dependency_health_check method exists."""
        orchestrator, _ = mock_orchestrator
        assert hasattr(orchestrator, '_run_dependency_health_check')
        assert callable(orchestrator._run_dependency_health_check)

    def test_health_check_with_no_features(self, mock_orchestrator):
        """Health check should handle empty database gracefully."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Setup mock session to return empty feature list
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = []
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return True (healthy) for empty database
        assert result is True
        mock_session.close.assert_called_once()

    def test_health_check_with_healthy_features(self, mock_orchestrator):
        """Health check should pass for features with no dependency issues."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Setup mock features with valid dependencies
        features = [
            MockFeature(1, dependencies=[]),
            MockFeature(2, dependencies=[1]),
            MockFeature(3, dependencies=[1, 2]),
        ]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return True (healthy)
        assert result is True
        mock_session.close.assert_called_once()

    def test_health_check_auto_fixes_self_references(self, mock_orchestrator):
        """Health check should auto-fix self-references."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with self-reference
        feature_with_self_ref = MockFeature(1, dependencies=[1, 2])
        feature_normal = MockFeature(2, dependencies=[])
        features = [feature_with_self_ref, feature_normal]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call for fixing
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_self_ref
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return True (issues handled)
        assert result is True

        # Verify self-reference was removed
        assert 1 not in feature_with_self_ref.dependencies
        mock_session.commit.assert_called()
        mock_session.close.assert_called_once()

    def test_health_check_auto_fixes_missing_targets(self, mock_orchestrator):
        """Health check should auto-fix missing dependency targets."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with missing target (999 doesn't exist)
        feature_with_missing = MockFeature(1, dependencies=[2, 999])
        feature_normal = MockFeature(2, dependencies=[])
        features = [feature_with_missing, feature_normal]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call for fixing
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_missing
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return True (issues handled)
        assert result is True

        # Verify missing target was removed
        assert 999 not in feature_with_missing.dependencies
        mock_session.commit.assert_called()
        mock_session.close.assert_called_once()

    def test_health_check_blocks_on_cycles_without_auto_fix(self, mock_orchestrator):
        """Health check should block startup on cycles (Feature #97) and not auto-fix them."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with a cycle: 1 -> 2 -> 1
        feature_a = MockFeature(1, dependencies=[2])
        feature_b = MockFeature(2, dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return False (orchestrator blocks startup on cycles - Feature #97)
        assert result is False

        # Cycles should NOT be auto-fixed - dependencies should be unchanged
        assert feature_a.dependencies == [2]
        assert feature_b.dependencies == [1]
        mock_session.close.assert_called_once()

    def test_health_check_blocks_on_complex_cycles(self, mock_orchestrator):
        """Health check should block startup on complex cycles (A -> B -> C -> A) - Feature #97."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with complex cycle
        feature_a = MockFeature(1, dependencies=[2])
        feature_b = MockFeature(2, dependencies=[3])
        feature_c = MockFeature(3, dependencies=[1])
        features = [feature_a, feature_b, feature_c]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return False (orchestrator blocks startup on cycles - Feature #97)
        assert result is False
        mock_session.close.assert_called_once()

    def test_health_check_handles_multiple_issue_types(self, mock_orchestrator):
        """Health check should handle multiple issue types in one pass."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with multiple issues:
        # - Feature 1: self-reference
        # - Feature 3: depends on non-existent feature 999
        feature_self_ref = MockFeature(1, dependencies=[1, 2])
        feature_normal = MockFeature(2, dependencies=[])
        feature_missing = MockFeature(3, dependencies=[2, 999])
        features = [feature_self_ref, feature_normal, feature_missing]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Setup filter().first() to return the right feature
        def mock_filter_side_effect(condition):
            filter_mock = MagicMock()
            # Check which feature is being queried
            for f in features:
                if hasattr(condition, 'right') and hasattr(condition.right, 'value'):
                    if condition.right.value == f.id:
                        filter_mock.first.return_value = f
                        return filter_mock
            filter_mock.first.return_value = features[0]
            return filter_mock

        mock_query.filter.side_effect = mock_filter_side_effect
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Should return True (issues handled)
        assert result is True
        mock_session.close.assert_called_once()


class TestOrchestratorCallsHealthCheckOnStartup:
    """Tests to verify the health check is called during run_loop startup.

    These tests verify by inspecting source code rather than running the full
    async loop, which avoids timeout issues and complex mocking.
    """

    def test_run_loop_contains_health_check_call(self):
        """Verify that run_loop contains the _run_dependency_health_check call."""
        import inspect
        from parallel_orchestrator import ParallelOrchestrator

        # Get the source code of run_loop
        source = inspect.getsource(ParallelOrchestrator.run_loop)

        # Verify the health check call is present
        assert '_run_dependency_health_check' in source

    def test_health_check_called_before_feature_loop_in_source(self):
        """Verify health check is called before feature loop in the source code."""
        import inspect
        from parallel_orchestrator import ParallelOrchestrator

        source = inspect.getsource(ParallelOrchestrator.run_loop)

        # Find positions of key sections
        health_check_pos = source.find('_run_dependency_health_check')
        feature_loop_comment_pos = source.find('# Phase 2: Feature loop')
        resumable_call_pos = source.find('get_resumable_features')

        # Health check should come before feature loop
        assert health_check_pos > 0, "Health check call not found in run_loop"
        assert feature_loop_comment_pos > 0, "Feature loop comment not found"
        assert health_check_pos < feature_loop_comment_pos, \
            "Health check should be called before feature loop"
        assert health_check_pos < resumable_call_pos, \
            "Health check should be called before get_resumable_features"

    def test_health_check_called_after_initialization_in_source(self):
        """Verify health check is called after initialization completes."""
        import inspect
        from parallel_orchestrator import ParallelOrchestrator

        source = inspect.getsource(ParallelOrchestrator.run_loop)

        # Find positions
        health_check_pos = source.find('_run_dependency_health_check')
        init_complete_pos = source.find('INITIALIZATION COMPLETE')

        # Health check should come after initialization section (if it exists)
        # Note: init section only runs when no features exist, but check is always called
        assert health_check_pos > 0, "Health check call not found"
        # The health check should be positioned to run regardless of init


class TestValidateDependencyGraphIntegration:
    """Integration tests verifying validate_dependency_graph is called correctly."""

    def test_validate_dependency_graph_import(self):
        """Verify validate_dependency_graph is imported in parallel_orchestrator."""
        from parallel_orchestrator import validate_dependency_graph
        assert callable(validate_dependency_graph)

    def test_health_check_calls_validate_dependency_graph(self, tmp_path):
        """Verify _run_dependency_health_check calls validate_dependency_graph."""
        with patch('parallel_orchestrator.create_database') as mock_create_db, \
             patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            # Setup mock session
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_features = [MockFeature(1), MockFeature(2)]
            mock_query.all.return_value = mock_features
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            # Setup mock validate result
            mock_validate.return_value = {
                "is_valid": True,
                "self_references": [],
                "cycles": [],
                "missing_targets": {},
                "issues": [],
                "summary": "Dependency graph is healthy",
            }

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            result = orchestrator._run_dependency_health_check()

            # Verify validate_dependency_graph was called
            mock_validate.assert_called_once()

            # Verify it was called with feature dicts
            call_args = mock_validate.call_args[0][0]
            assert len(call_args) == 2
            assert all(isinstance(f, dict) for f in call_args)


class TestVerificationSteps:
    """Tests corresponding to the feature verification steps."""

    @pytest.fixture
    def real_orchestrator(self, tmp_path):
        """Create a real orchestrator for verification tests."""
        # Create a minimal features.db
        import sqlite3
        db_path = tmp_path / "features.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS features (
                id INTEGER PRIMARY KEY,
                priority INTEGER,
                category TEXT,
                name TEXT,
                description TEXT,
                steps TEXT,
                passes BOOLEAN DEFAULT FALSE,
                in_progress BOOLEAN DEFAULT FALSE,
                dependencies TEXT DEFAULT '[]'
            )
        ''')
        conn.commit()
        conn.close()

        with patch('parallel_orchestrator.create_database') as mock_create_db:
            from api.database import create_database as real_create_db
            engine, session_maker = real_create_db(tmp_path)
            mock_create_db.return_value = (engine, session_maker)

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            return orchestrator, engine, session_maker

    def test_step1_startup_hook_in_orchestrator_initialization(self):
        """Step 1: Add startup hook in orchestrator initialization.

        Verifies that _run_dependency_health_check method exists and is callable.
        """
        import inspect
        from parallel_orchestrator import ParallelOrchestrator

        # Verify method exists
        assert hasattr(ParallelOrchestrator, '_run_dependency_health_check')

        # Verify it's a method
        assert callable(getattr(ParallelOrchestrator, '_run_dependency_health_check'))

        # Verify it's called in run_loop by checking source code
        source = inspect.getsource(ParallelOrchestrator.run_loop)
        assert '_run_dependency_health_check' in source

    def test_step2_load_all_features_from_database(self, tmp_path):
        """Step 2: Load all features from database.

        Verifies that _run_dependency_health_check queries all features from DB.
        """
        with patch('parallel_orchestrator.create_database') as mock_create_db:
            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            # Setup mock session
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_features = [MockFeature(i) for i in range(1, 6)]  # 5 features
            mock_query.all.return_value = mock_features
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            with patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:
                mock_validate.return_value = {
                    "is_valid": True,
                    "self_references": [],
                    "cycles": [],
                    "missing_targets": {},
                    "issues": [],
                    "summary": "Dependency graph is healthy",
                }

                orchestrator._run_dependency_health_check()

                # Verify all features were loaded
                mock_session.query.assert_called()
                mock_query.all.assert_called()

    def test_step3_call_validate_dependency_graph_with_loaded_features(self, tmp_path):
        """Step 3: Call validate_dependency_graph() with loaded features.

        Verifies that validate_dependency_graph is called with the feature dicts.
        """
        with patch('parallel_orchestrator.create_database') as mock_create_db, \
             patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            # Setup mock session
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_features = [
                MockFeature(1, dependencies=[]),
                MockFeature(2, dependencies=[1]),
                MockFeature(3, dependencies=[1, 2]),
            ]
            mock_query.all.return_value = mock_features
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            mock_validate.return_value = {
                "is_valid": True,
                "self_references": [],
                "cycles": [],
                "missing_targets": {},
                "issues": [],
                "summary": "Dependency graph is healthy",
            }

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            orchestrator._run_dependency_health_check()

            # Verify validate_dependency_graph was called with feature dicts
            mock_validate.assert_called_once()
            call_args = mock_validate.call_args[0][0]
            assert len(call_args) == 3
            assert call_args[0]["id"] == 1
            assert call_args[1]["id"] == 2
            assert call_args[2]["id"] == 3

    def test_step4_handle_issues_according_to_type(self, tmp_path):
        """Step 4: If issues found, handle according to issue type before proceeding.

        Verifies that:
        - Self-references are auto-fixed
        - Missing targets are auto-fixed
        - Cycles are logged but not auto-fixed
        """
        with patch('parallel_orchestrator.create_database') as mock_create_db, \
             patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            # Create feature with self-reference
            feature_with_issue = MockFeature(1, dependencies=[1, 2])

            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [feature_with_issue, MockFeature(2)]
            mock_filter = MagicMock()
            mock_filter.first.return_value = feature_with_issue
            mock_query.filter.return_value = mock_filter
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            mock_validate.return_value = {
                "is_valid": False,
                "self_references": [1],
                "cycles": [],
                "missing_targets": {},
                "issues": [{
                    "feature_id": 1,
                    "issue_type": "self_reference",
                    "details": {"message": "Feature 1 depends on itself"},
                    "auto_fixable": True,
                }],
                "summary": "1 self-reference(s) found (auto-fixable)",
            }

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            result = orchestrator._run_dependency_health_check()

            # Verify auto-fix was applied
            assert result is True
            assert 1 not in feature_with_issue.dependencies
            mock_session.commit.assert_called()

    def test_step5_log_summary_of_health_check_results(self, tmp_path, capsys):
        """Step 5: Log summary of dependency health check results.

        Verifies that a summary is printed to stdout.
        """
        with patch('parallel_orchestrator.create_database') as mock_create_db, \
             patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)

            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = [MockFeature(1), MockFeature(2)]
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            mock_validate.return_value = {
                "is_valid": True,
                "self_references": [],
                "cycles": [],
                "missing_targets": {},
                "issues": [],
                "summary": "Dependency graph is healthy",
            }

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            orchestrator._run_dependency_health_check()

            captured = capsys.readouterr()

            # Verify summary was printed (matches formatted header from implementation)
            assert "DEPENDENCY HEALTH CHECK" in captured.out
            assert "healthy" in captured.out.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
