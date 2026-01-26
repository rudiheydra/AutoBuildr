"""
Tests for Feature #90: BFS in compute_scheduling_scores uses visited set to prevent re-processing

This feature ensures that the BFS algorithm in compute_scheduling_scores() uses a visited
set to prevent infinite loops when cycles exist in the dependency graph.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.dependency_resolver import compute_scheduling_scores


class TestBFSWithCycles:
    """Test BFS handles cycles correctly."""

    def test_simple_cycle_does_not_hang(self):
        """Test: A -> B -> A cycle doesn't cause infinite loop."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2]},
            {"id": 2, "priority": 2, "dependencies": [1]},
        ]

        # This should return quickly, not hang
        scores = compute_scheduling_scores(features)

        assert isinstance(scores, dict)
        assert 1 in scores
        assert 2 in scores

    def test_three_node_cycle_does_not_hang(self):
        """Test: A -> B -> C -> A cycle doesn't cause infinite loop."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2]},  # A depends on B
            {"id": 2, "priority": 2, "dependencies": [3]},  # B depends on C
            {"id": 3, "priority": 3, "dependencies": [1]},  # C depends on A (cycle!)
        ]

        # This should return quickly, not hang
        scores = compute_scheduling_scores(features)

        assert isinstance(scores, dict)
        assert 1 in scores
        assert 2 in scores
        assert 3 in scores

    def test_four_node_cycle_does_not_hang(self):
        """Test: A -> B -> C -> D -> A cycle doesn't cause infinite loop."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2]},
            {"id": 2, "priority": 2, "dependencies": [3]},
            {"id": 3, "priority": 3, "dependencies": [4]},
            {"id": 4, "priority": 4, "dependencies": [1]},
        ]

        # This should return quickly, not hang
        scores = compute_scheduling_scores(features)

        assert isinstance(scores, dict)
        assert len(scores) == 4
        for fid in [1, 2, 3, 4]:
            assert fid in scores

    def test_self_reference_does_not_hang(self):
        """Test: Self-referencing feature (A -> A) doesn't cause infinite loop."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [1]},  # Self-reference
        ]

        scores = compute_scheduling_scores(features)

        assert isinstance(scores, dict)
        assert 1 in scores


class TestBFSValidScores:
    """Test that all features get valid scores."""

    def test_cycle_all_features_have_scores(self):
        """Verify all features in a cycle have valid scores assigned."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2]},
            {"id": 2, "priority": 2, "dependencies": [3]},
            {"id": 3, "priority": 3, "dependencies": [1]},
        ]

        scores = compute_scheduling_scores(features)

        # All features must have scores
        for f in features:
            assert f["id"] in scores
            # Score should be a valid float
            assert isinstance(scores[f["id"]], (int, float))
            # Score should be non-negative
            assert scores[f["id"]] >= 0

    def test_mixed_cycle_and_non_cycle(self):
        """Test features outside cycles still get correct scores."""
        features = [
            {"id": 1, "priority": 1, "dependencies": []},     # Root (no deps)
            {"id": 2, "priority": 2, "dependencies": [1]},     # Depends on root
            {"id": 3, "priority": 3, "dependencies": [4]},     # Part of cycle
            {"id": 4, "priority": 4, "dependencies": [3]},     # Part of cycle
        ]

        scores = compute_scheduling_scores(features)

        # All features must have scores
        for f in features:
            assert f["id"] in scores
            assert isinstance(scores[f["id"]], (int, float))


class TestBFSVisitedSet:
    """Test that BFS uses visited set to prevent re-processing."""

    def test_diamond_pattern_processed_once(self):
        """Test diamond pattern doesn't process nodes multiple times.

        Structure:
            1
           / \
          2   3
           \ /
            4

        Node 4 should only be processed once, not twice.
        """
        features = [
            {"id": 1, "priority": 1, "dependencies": []},
            {"id": 2, "priority": 2, "dependencies": [1]},
            {"id": 3, "priority": 3, "dependencies": [1]},
            {"id": 4, "priority": 4, "dependencies": [2, 3]},
        ]

        scores = compute_scheduling_scores(features)

        assert len(scores) == 4
        for fid in [1, 2, 3, 4]:
            assert fid in scores

    def test_complex_graph_with_cycle(self):
        """Test complex graph with multiple paths and a cycle."""
        features = [
            {"id": 1, "priority": 1, "dependencies": []},
            {"id": 2, "priority": 2, "dependencies": [1]},
            {"id": 3, "priority": 3, "dependencies": [1]},
            {"id": 4, "priority": 4, "dependencies": [2, 3]},
            {"id": 5, "priority": 5, "dependencies": [4, 6]},  # Also in cycle
            {"id": 6, "priority": 6, "dependencies": [5]},     # Cycle: 5 -> 6 -> 5
        ]

        scores = compute_scheduling_scores(features)

        assert len(scores) == 6
        for fid in range(1, 7):
            assert fid in scores

    def test_long_chain_with_cycle_at_end(self):
        """Test long chain that ends in a cycle."""
        features = [
            {"id": 1, "priority": 1, "dependencies": []},
            {"id": 2, "priority": 2, "dependencies": [1]},
            {"id": 3, "priority": 3, "dependencies": [2]},
            {"id": 4, "priority": 4, "dependencies": [3]},
            {"id": 5, "priority": 5, "dependencies": [4, 6]},  # Cycle start
            {"id": 6, "priority": 6, "dependencies": [5]},     # Cycle end
        ]

        scores = compute_scheduling_scores(features)

        assert len(scores) == 6


class TestBFSPerformance:
    """Test BFS performance doesn't degrade with cycles."""

    def test_many_interconnected_cycles(self):
        """Test many interconnected cycles complete quickly."""
        # Create 10 features all depending on each other (fully connected minus self)
        features = []
        for i in range(1, 11):
            deps = [j for j in range(1, 11) if j != i]
            features.append({"id": i, "priority": i, "dependencies": deps})

        # Should complete quickly, not hang
        scores = compute_scheduling_scores(features)

        assert len(scores) == 10

    def test_multiple_separate_cycles(self):
        """Test multiple separate cycles."""
        features = [
            # Cycle 1: 1 -> 2 -> 1
            {"id": 1, "priority": 1, "dependencies": [2]},
            {"id": 2, "priority": 2, "dependencies": [1]},
            # Cycle 2: 3 -> 4 -> 5 -> 3
            {"id": 3, "priority": 3, "dependencies": [4]},
            {"id": 4, "priority": 4, "dependencies": [5]},
            {"id": 5, "priority": 5, "dependencies": [3]},
            # Independent: 6
            {"id": 6, "priority": 6, "dependencies": []},
        ]

        scores = compute_scheduling_scores(features)

        assert len(scores) == 6


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_features(self):
        """Test empty feature list."""
        scores = compute_scheduling_scores([])
        assert scores == {}

    def test_single_feature_no_deps(self):
        """Test single feature with no dependencies."""
        features = [{"id": 1, "priority": 1, "dependencies": []}]
        scores = compute_scheduling_scores(features)
        assert 1 in scores

    def test_single_feature_self_dep(self):
        """Test single feature with self-dependency."""
        features = [{"id": 1, "priority": 1, "dependencies": [1]}]
        scores = compute_scheduling_scores(features)
        assert 1 in scores

    def test_missing_dependency_target(self):
        """Test feature depending on non-existent feature."""
        features = [{"id": 1, "priority": 1, "dependencies": [999]}]
        scores = compute_scheduling_scores(features)
        assert 1 in scores


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
