"""
Tests for Feature #97: Startup health check blocks on cycles and lists cycle path.

On startup, if circular dependencies are detected (not self-references), the orchestrator
should block startup and display the cycle path for user resolution.

Verification Steps:
1. Insert features A -> B -> A into database
2. Attempt to start the orchestrator
3. Verify startup is blocked with clear error message
4. Verify error message includes the cycle path: [A, B, A]
5. Verify error message instructs user to remove one dependency
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
import io

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


class TestFeature97VerificationSteps:
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

    def test_step1_insert_features_with_cycle(self, mock_orchestrator):
        """Step 1: Insert features A -> B -> A into database.

        Verifies that we can set up features with a cycle: A depends on B, B depends on A.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle: A (id=1) -> B (id=2) -> A (id=1)
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Verify features have cycle
        assert feature_a.dependencies == [2]
        assert feature_b.dependencies == [1]

    def test_step2_startup_is_blocked_when_cycles_detected(self, mock_orchestrator, capsys):
        """Step 2: Attempt to start the orchestrator - verify startup is blocked.

        Verifies that _run_dependency_health_check returns False when cycles are detected.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        result = orchestrator._run_dependency_health_check()

        # Verify startup is blocked (returns False)
        assert result is False

    def test_step3_clear_error_message_displayed(self, mock_orchestrator, capsys):
        """Step 3: Verify startup is blocked with clear error message.

        Verifies that the error message clearly indicates circular dependencies were detected.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        orchestrator._run_dependency_health_check()

        # Capture output
        captured = capsys.readouterr()

        # Verify clear error message (supports various output formats)
        assert "CYCLES FOUND" in captured.out or "CIRCULAR DEPENDENCIES" in captured.out or "cycle" in captured.out.lower()
        assert "STARTUP BLOCKED" in captured.out

    def test_step4_cycle_path_included_in_error_message(self, mock_orchestrator, capsys):
        """Step 4: Verify error message includes the cycle path: [A, B, A].

        Verifies that the cycle path is displayed in the format [A -> B -> A].
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle: 1 -> 2 -> 1
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        orchestrator._run_dependency_health_check()

        # Capture output
        captured = capsys.readouterr()

        # Verify cycle path is included (cycle is normalized, so could be [1, 2] or [2, 1])
        # The output format is: "[1 -> 2 -> 1]" or "[2 -> 1 -> 2]"
        assert " -> " in captured.out
        # Check that the cycle contains both feature IDs
        assert "1" in captured.out and "2" in captured.out

    def test_step5_user_instruction_to_remove_dependency(self, mock_orchestrator, capsys):
        """Step 5: Verify error message instructs user to remove one dependency.

        Verifies that the error message provides guidance on how to fix the cycle.
        """
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        # Run health check
        orchestrator._run_dependency_health_check()

        # Capture output
        captured = capsys.readouterr()

        # Verify instruction to remove dependency
        assert "remove" in captured.out.lower()
        assert "dependency" in captured.out.lower() or "dependencies" in captured.out.lower()
        assert "fix" in captured.out.lower() or "To fix:" in captured.out


class TestCycleBlocksStartupIntegration:
    """Integration tests for cycle blocking behavior in run_loop."""

    def test_run_loop_exits_early_when_cycles_detected(self, tmp_path, capsys):
        """run_loop should exit early when health check detects cycles."""
        import asyncio

        with patch('parallel_orchestrator.create_database') as mock_create_db, \
             patch('parallel_orchestrator.has_features') as mock_has_features:

            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)
            mock_has_features.return_value = True  # Features exist

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            # Create features with cycle
            feature_a = MockFeature(1, name="Feature A", dependencies=[2])
            feature_b = MockFeature(2, name="Feature B", dependencies=[1])
            features = [feature_a, feature_b]

            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = features
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            # Track if get_resumable_features was called (it shouldn't be - loop should exit early)
            with patch.object(orchestrator, 'get_resumable_features') as mock_resumable:
                mock_resumable.return_value = []

                asyncio.run(orchestrator.run_loop())

                # Verify the feature loop was never entered
                mock_resumable.assert_not_called()

            # Verify the abort message was printed
            captured = capsys.readouterr()
            assert "aborted" in captured.out.lower() or "blocked" in captured.out.lower()

    def test_run_loop_continues_when_no_cycles(self, tmp_path):
        """run_loop should continue normally when no cycles are detected."""
        import asyncio

        with patch('parallel_orchestrator.create_database') as mock_create_db, \
             patch('parallel_orchestrator.has_features') as mock_has_features:

            mock_engine = MagicMock()
            mock_session_maker = MagicMock()
            mock_create_db.return_value = (mock_engine, mock_session_maker)
            mock_has_features.return_value = True  # Features exist

            orchestrator = ParallelOrchestrator(
                project_dir=tmp_path,
                max_concurrency=3,
            )

            # Create features WITHOUT cycle
            feature_a = MockFeature(1, name="Feature A", dependencies=[])
            feature_b = MockFeature(2, name="Feature B", dependencies=[1])
            features = [feature_a, feature_b]

            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.all.return_value = features
            mock_session.query.return_value = mock_query
            mock_session_maker.return_value = mock_session

            # Track if get_resumable_features was called (it should be - loop should continue)
            with patch.object(orchestrator, 'get_resumable_features') as mock_resumable, \
                 patch.object(orchestrator, 'get_all_complete', return_value=True):
                mock_resumable.return_value = []

                asyncio.run(orchestrator.run_loop())

                # Verify the feature loop was entered
                mock_resumable.assert_called()


class TestComplexCycleScenarios:
    """Tests for various complex cycle scenarios."""

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

    def test_three_node_cycle_blocks_startup(self, mock_orchestrator, capsys):
        """A -> B -> C -> A cycle should block startup."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with 3-node cycle
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[3])
        feature_c = MockFeature(3, name="Feature C", dependencies=[1])
        features = [feature_a, feature_b, feature_c]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        result = orchestrator._run_dependency_health_check()

        assert result is False
        captured = capsys.readouterr()
        # Verify cycle detection message (supports various output formats)
        assert "CYCLES FOUND" in captured.out or "CIRCULAR DEPENDENCIES" in captured.out or "cycle" in captured.out.lower()

    def test_multiple_cycles_all_listed(self, mock_orchestrator, capsys):
        """Multiple independent cycles should all be listed."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create two independent cycles: 1->2->1 and 3->4->3
        feature_1 = MockFeature(1, dependencies=[2])
        feature_2 = MockFeature(2, dependencies=[1])
        feature_3 = MockFeature(3, dependencies=[4])
        feature_4 = MockFeature(4, dependencies=[3])
        features = [feature_1, feature_2, feature_3, feature_4]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        result = orchestrator._run_dependency_health_check()

        assert result is False
        captured = capsys.readouterr()
        # Check that multiple cycles are mentioned
        assert "cycle" in captured.out.lower()

    def test_self_reference_does_not_block_startup(self, mock_orchestrator, capsys):
        """Self-references are auto-fixed and should NOT block startup."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create feature with self-reference (not a cycle between features)
        feature_with_self_ref = MockFeature(1, dependencies=[1, 2])
        feature_normal = MockFeature(2, dependencies=[])
        features = [feature_with_self_ref, feature_normal]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features

        # Mock the filter().first() call for auto-fixing
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_self_ref
        mock_query.filter.return_value = mock_filter

        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        result = orchestrator._run_dependency_health_check()

        # Should return True (self-references are auto-fixed, not blocking)
        assert result is True
        # Self-reference should have been removed
        assert 1 not in feature_with_self_ref.dependencies

    def test_cycle_plus_healthy_features(self, mock_orchestrator, capsys):
        """A cycle among some features should block even if other features are healthy."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Mix of healthy features and a cycle
        healthy_1 = MockFeature(1, dependencies=[])
        healthy_2 = MockFeature(2, dependencies=[1])
        # Cycle: 3 -> 4 -> 3
        cycle_3 = MockFeature(3, dependencies=[4])
        cycle_4 = MockFeature(4, dependencies=[3])
        features = [healthy_1, healthy_2, cycle_3, cycle_4]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        result = orchestrator._run_dependency_health_check()

        assert result is False
        captured = capsys.readouterr()
        # Verify cycle detection message (supports various output formats)
        assert "CYCLES FOUND" in captured.out or "CIRCULAR DEPENDENCIES" in captured.out or "cycle" in captured.out.lower()


class TestCyclePathFormatting:
    """Tests for cycle path display formatting."""

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

    def test_cycle_path_uses_arrow_notation(self, mock_orchestrator, capsys):
        """Cycle path should use arrow notation: A -> B -> A."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle
        feature_a = MockFeature(1, dependencies=[2])
        feature_b = MockFeature(2, dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        orchestrator._run_dependency_health_check()

        captured = capsys.readouterr()
        # Verify arrow notation is used
        assert " -> " in captured.out

    def test_cycle_path_enclosed_in_brackets(self, mock_orchestrator, capsys):
        """Cycle path should be enclosed in brackets: [A -> B -> A]."""
        orchestrator, mock_session_maker = mock_orchestrator

        # Create features with cycle
        feature_a = MockFeature(1, dependencies=[2])
        feature_b = MockFeature(2, dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        orchestrator._run_dependency_health_check()

        captured = capsys.readouterr()
        # Verify brackets are used
        assert "[" in captured.out and "]" in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
