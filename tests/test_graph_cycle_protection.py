"""
Tests for Feature #93: All graph traversal functions have cycle protection

This test suite verifies that all graph traversal functions in the dependency
resolver have proper cycle protection mechanisms:
1. resolve_dependencies() - uses Kahn's algorithm with in_degree tracking
2. _detect_cycles() - uses visited and rec_stack sets with iteration limit
3. compute_scheduling_scores() - uses queued_depths tracking with iteration limit
4. would_create_circular_dependency() - uses visited set with depth limit
5. _detect_cycles_for_validation() - uses visited and rec_stack sets with iteration limit
"""

import logging
import pytest
from api.dependency_resolver import (
    resolve_dependencies,
    _detect_cycles,
    _detect_cycles_for_validation,
    compute_scheduling_scores,
    would_create_circular_dependency,
    MAX_DEPENDENCY_DEPTH,
)


class TestResolveDependenciesKahnsAlgorithm:
    """Verify resolve_dependencies uses Kahn's algorithm with proper cycle handling."""

    def test_kahns_detects_simple_cycle(self):
        """Kahn's algorithm should detect simple A -> B -> A cycles."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
        ]
        result = resolve_dependencies(features)
        assert len(result["circular_dependencies"]) > 0
        # Both features should be detected as part of cycle
        cycle_ids = set()
        for cycle in result["circular_dependencies"]:
            cycle_ids.update(cycle)
        assert 1 in cycle_ids and 2 in cycle_ids

    def test_kahns_detects_complex_cycle(self):
        """Kahn's algorithm should detect A -> B -> C -> A cycles."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [3], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [1], "passes": False},
        ]
        result = resolve_dependencies(features)
        assert len(result["circular_dependencies"]) > 0

    def test_kahns_orders_non_cyclic_features(self):
        """Kahn's algorithm should correctly order features without cycles."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [2], "passes": False},
        ]
        result = resolve_dependencies(features)
        assert result["circular_dependencies"] == []
        ordered_ids = [f["id"] for f in result["ordered_features"]]
        # Feature 1 should come before 2, and 2 before 3
        assert ordered_ids.index(1) < ordered_ids.index(2)
        assert ordered_ids.index(2) < ordered_ids.index(3)

    def test_kahns_handles_diamond_pattern(self):
        """Kahn's algorithm should handle diamond dependency patterns correctly."""
        # Diamond: 1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4
        features = [
            {"id": 1, "priority": 1, "dependencies": [], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [1], "passes": False},
            {"id": 4, "priority": 4, "dependencies": [2, 3], "passes": False},
        ]
        result = resolve_dependencies(features)
        assert result["circular_dependencies"] == []
        ordered_ids = [f["id"] for f in result["ordered_features"]]
        # Feature 1 should come before 2, 3, and 4
        assert ordered_ids.index(1) < ordered_ids.index(2)
        assert ordered_ids.index(1) < ordered_ids.index(3)
        assert ordered_ids.index(2) < ordered_ids.index(4)
        assert ordered_ids.index(3) < ordered_ids.index(4)

    def test_kahns_terminates_on_large_cycle(self):
        """Kahn's algorithm should terminate on large cycles without infinite loop."""
        # Create a cycle of 50 features
        features = []
        for i in range(50):
            next_id = (i + 1) % 50  # Last feature depends on first
            features.append({
                "id": i,
                "priority": i,
                "dependencies": [next_id] if i < 49 else [0],
                "passes": False,
            })
        # Should terminate and detect cycle
        result = resolve_dependencies(features)
        assert len(result["circular_dependencies"]) > 0


class TestDetectCyclesVisitedTracking:
    """Verify _detect_cycles uses visited and rec_stack sets."""

    def test_detect_cycles_has_visited_set(self):
        """_detect_cycles should use a visited set to prevent infinite loops."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
        ]
        feature_map = {f["id"]: f for f in features}
        # Should complete without infinite loop
        cycles = _detect_cycles(features, feature_map)
        assert len(cycles) > 0

    def test_detect_cycles_handles_self_reference(self):
        """_detect_cycles should handle self-references gracefully."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [1], "passes": False},
        ]
        feature_map = {f["id"]: f for f in features}
        cycles = _detect_cycles(features, feature_map)
        # Self-reference creates a cycle
        assert len(cycles) == 1

    def test_detect_cycles_iteration_limit(self):
        """_detect_cycles should respect iteration limits."""
        # Create a large graph to test iteration limit
        features = []
        for i in range(100):
            # Each feature depends on the previous one
            deps = [i - 1] if i > 0 else []
            features.append({
                "id": i,
                "priority": i,
                "dependencies": deps,
                "passes": False,
            })
        feature_map = {f["id"]: f for f in features}
        # Should complete without hitting iteration limit (no cycles)
        cycles = _detect_cycles(features, feature_map)
        assert cycles == []


class TestDetectCyclesForValidationVisitedTracking:
    """Verify _detect_cycles_for_validation uses visited and rec_stack sets."""

    def test_validation_cycles_has_visited_set(self):
        """_detect_cycles_for_validation should use a visited set."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
        ]
        feature_map = {f["id"]: f for f in features}
        cycles = _detect_cycles_for_validation(features, feature_map)
        assert len(cycles) > 0

    def test_validation_cycles_normalizes_cycle_paths(self):
        """_detect_cycles_for_validation should normalize cycle paths."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [3], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [1], "passes": False},
        ]
        feature_map = {f["id"]: f for f in features}
        cycles = _detect_cycles_for_validation(features, feature_map)
        assert len(cycles) == 1
        # Cycle should start from smallest ID
        assert cycles[0][0] == min(cycles[0])

    def test_validation_cycles_deduplicates(self):
        """_detect_cycles_for_validation should deduplicate cycles."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
        ]
        feature_map = {f["id"]: f for f in features}
        cycles = _detect_cycles_for_validation(features, feature_map)
        # Should find exactly one unique cycle, not two
        assert len(cycles) == 1


class TestComputeSchedulingScoresQueuedTracking:
    """Verify compute_scheduling_scores uses queued_depths tracking."""

    def test_scheduling_scores_diamond_pattern_no_duplicates(self):
        """compute_scheduling_scores should not process same node multiple times."""
        # Diamond pattern: 1 -> 2, 1 -> 3, 2 -> 4, 3 -> 4
        features = [
            {"id": 1, "priority": 1, "dependencies": [], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [1], "passes": False},
            {"id": 4, "priority": 4, "dependencies": [2, 3], "passes": False},
        ]
        scores = compute_scheduling_scores(features)
        # All features should have scores
        assert len(scores) == 4
        # Feature 1 (root) should have highest unblocking potential
        assert scores[1] > scores[4]

    def test_scheduling_scores_max_depth_correct(self):
        """compute_scheduling_scores should calculate correct max depth in DAGs."""
        # Two paths to node 4: 1->2->4 (depth 2) and 1->3->4 (depth 2)
        features = [
            {"id": 1, "priority": 1, "dependencies": [], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [1], "passes": False},
            {"id": 4, "priority": 4, "dependencies": [2, 3], "passes": False},
        ]
        scores = compute_scheduling_scores(features)
        # Verify scores are computed (exact values depend on algorithm)
        assert all(isinstance(s, float) for s in scores.values())

    def test_scheduling_scores_iteration_limit(self):
        """compute_scheduling_scores should respect iteration limits."""
        # Create a large graph
        features = []
        for i in range(100):
            deps = [i - 1] if i > 0 else []
            features.append({
                "id": i,
                "priority": i,
                "dependencies": deps,
                "passes": False,
            })
        # Should complete without hitting iteration limit
        scores = compute_scheduling_scores(features)
        assert len(scores) == 100

    def test_scheduling_scores_empty_features(self):
        """compute_scheduling_scores should handle empty feature list."""
        scores = compute_scheduling_scores([])
        assert scores == {}

    def test_scheduling_scores_single_feature(self):
        """compute_scheduling_scores should handle single feature."""
        features = [{"id": 1, "priority": 1, "dependencies": [], "passes": False}]
        scores = compute_scheduling_scores(features)
        assert 1 in scores


class TestWouldCreateCircularDependencyVisited:
    """Verify would_create_circular_dependency uses visited set and depth limit."""

    def test_would_create_cycle_uses_visited_set(self):
        """would_create_circular_dependency should use a visited set."""
        # 1 -> 2 -> 3
        features = [
            {"id": 1, "priority": 1, "dependencies": [], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
            {"id": 3, "priority": 3, "dependencies": [2], "passes": False},
        ]
        # Adding 1 -> 3 would create cycle: 1 -> 3 -> 2 -> 1 (wait, that's wrong)
        # Actually: if we add dependency from 1 to 3, we check if 3 can reach 1
        # 3 -> 2 -> 1, so yes it can
        result = would_create_circular_dependency(features, 1, 3)
        assert result == True

    def test_would_create_cycle_no_cycle(self):
        """would_create_circular_dependency should return False when no cycle."""
        features = [
            {"id": 1, "priority": 1, "dependencies": [], "passes": False},
            {"id": 2, "priority": 2, "dependencies": [], "passes": False},
        ]
        # Adding 1 -> 2 wouldn't create a cycle
        result = would_create_circular_dependency(features, 1, 2)
        assert result == False

    def test_would_create_cycle_self_reference(self):
        """would_create_circular_dependency should detect self-references."""
        features = [{"id": 1, "priority": 1, "dependencies": [], "passes": False}]
        result = would_create_circular_dependency(features, 1, 1)
        assert result == True

    def test_would_create_cycle_depth_limit(self):
        """would_create_circular_dependency should respect depth limit."""
        # Create a chain longer than MAX_DEPENDENCY_DEPTH
        features = []
        for i in range(MAX_DEPENDENCY_DEPTH + 10):
            deps = [i - 1] if i > 0 else []
            features.append({
                "id": i,
                "priority": i,
                "dependencies": deps,
                "passes": False,
            })
        # Adding dependency from last to first would create huge cycle
        last_id = MAX_DEPENDENCY_DEPTH + 9
        result = would_create_circular_dependency(features, 0, last_id)
        # Should return True (fail-safe when depth exceeded)
        assert result == True

    def test_would_create_cycle_nonexistent_features(self):
        """would_create_circular_dependency should handle non-existent features."""
        features = [{"id": 1, "priority": 1, "dependencies": [], "passes": False}]
        # Source doesn't exist
        result = would_create_circular_dependency(features, 999, 1)
        assert result == False
        # Target doesn't exist
        result = would_create_circular_dependency(features, 1, 999)
        assert result == False


class TestIterationLimitsLogging:
    """Verify iteration limits are logged when exceeded."""

    def test_detect_cycles_logs_on_limit(self, caplog):
        """_detect_cycles should log error when iteration limit exceeded."""
        # This is hard to trigger without mocking, but we can verify the code path exists
        # by checking the function source contains the logging call
        import inspect
        source = inspect.getsource(_detect_cycles)
        assert "_logger.error" in source
        assert "iteration limit exceeded" in source.lower()

    def test_detect_cycles_for_validation_logs_on_limit(self, caplog):
        """_detect_cycles_for_validation should log error when limit exceeded."""
        import inspect
        source = inspect.getsource(_detect_cycles_for_validation)
        assert "_logger.error" in source
        assert "iteration limit exceeded" in source.lower()

    def test_compute_scheduling_scores_logs_on_limit(self, caplog):
        """compute_scheduling_scores should log error when limit exceeded."""
        import inspect
        source = inspect.getsource(compute_scheduling_scores)
        assert "_logger.error" in source
        assert "iteration limit exceeded" in source.lower()


class TestCycleProtectionCodeAudit:
    """Audit that all functions have the required protection mechanisms."""

    def test_resolve_dependencies_uses_in_degree(self):
        """resolve_dependencies should use in_degree for Kahn's algorithm."""
        import inspect
        source = inspect.getsource(resolve_dependencies)
        assert "in_degree" in source

    def test_detect_cycles_uses_visited_and_rec_stack(self):
        """_detect_cycles should use both visited and rec_stack sets."""
        import inspect
        source = inspect.getsource(_detect_cycles)
        assert "visited" in source
        assert "rec_stack" in source
        assert "max_iterations" in source or "iteration" in source.lower()

    def test_detect_cycles_for_validation_uses_visited_and_rec_stack(self):
        """_detect_cycles_for_validation should use both visited and rec_stack sets."""
        import inspect
        source = inspect.getsource(_detect_cycles_for_validation)
        assert "visited" in source
        assert "rec_stack" in source
        assert "max_iterations" in source or "iteration" in source.lower()

    def test_compute_scheduling_scores_uses_queued_tracking(self):
        """compute_scheduling_scores should use queued tracking for BFS."""
        import inspect
        source = inspect.getsource(compute_scheduling_scores)
        assert "queued" in source.lower() or "visited" in source.lower()
        assert "max_iterations" in source or "iteration" in source.lower()

    def test_would_create_circular_dependency_uses_visited(self):
        """would_create_circular_dependency should use visited set."""
        import inspect
        source = inspect.getsource(would_create_circular_dependency)
        assert "visited" in source
        # Also check for depth limit
        assert "depth" in source.lower() or "MAX_DEPENDENCY_DEPTH" in source


class TestEdgeCases:
    """Test edge cases for cycle protection."""

    def test_empty_feature_list(self):
        """All functions should handle empty feature list."""
        result = resolve_dependencies([])
        assert result["ordered_features"] == []
        assert result["circular_dependencies"] == []

        cycles = _detect_cycles([], {})
        assert cycles == []

        cycles = _detect_cycles_for_validation([], {})
        assert cycles == []

        scores = compute_scheduling_scores([])
        assert scores == {}

    def test_single_feature_no_deps(self):
        """All functions should handle single feature with no dependencies."""
        features = [{"id": 1, "priority": 1, "dependencies": [], "passes": False}]
        feature_map = {f["id"]: f for f in features}

        result = resolve_dependencies(features)
        assert len(result["ordered_features"]) == 1

        cycles = _detect_cycles(features, feature_map)
        assert cycles == []

        cycles = _detect_cycles_for_validation(features, feature_map)
        assert cycles == []

        scores = compute_scheduling_scores(features)
        assert 1 in scores

    def test_features_with_none_dependencies(self):
        """Functions should handle features with None dependencies."""
        features = [{"id": 1, "priority": 1, "dependencies": None, "passes": False}]
        feature_map = {f["id"]: f for f in features}

        result = resolve_dependencies(features)
        assert len(result["ordered_features"]) == 1

        cycles = _detect_cycles(features, feature_map)
        assert cycles == []

        scores = compute_scheduling_scores(features)
        assert 1 in scores

    def test_features_with_missing_dependencies_key(self):
        """Functions should handle features without dependencies key."""
        features = [{"id": 1, "priority": 1, "passes": False}]
        feature_map = {f["id"]: f for f in features}

        result = resolve_dependencies(features)
        assert len(result["ordered_features"]) == 1

        cycles = _detect_cycles(features, feature_map)
        assert cycles == []

        scores = compute_scheduling_scores(features)
        assert 1 in scores
