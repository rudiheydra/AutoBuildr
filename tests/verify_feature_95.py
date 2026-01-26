#!/usr/bin/env python
"""
Feature #95 Verification Script
===============================

Verifies that the orchestrator runs validate_dependency_graph() on startup.

Verification Steps:
1. Add startup hook in orchestrator initialization
2. Load all features from database
3. Call validate_dependency_graph() with loaded features
4. If issues found, handle according to issue type before proceeding
5. Log summary of dependency health check results
"""

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_step1_startup_hook_exists():
    """Step 1: Add startup hook in orchestrator initialization."""
    print("\n=== Step 1: Verify startup hook exists ===")

    from parallel_orchestrator import ParallelOrchestrator

    # Check method exists
    assert hasattr(ParallelOrchestrator, '_run_dependency_health_check'), \
        "FAIL: _run_dependency_health_check method not found"

    assert callable(getattr(ParallelOrchestrator, '_run_dependency_health_check')), \
        "FAIL: _run_dependency_health_check is not callable"

    # Check method is called in run_loop
    source = inspect.getsource(ParallelOrchestrator.run_loop)
    assert '_run_dependency_health_check' in source, \
        "FAIL: _run_dependency_health_check not called in run_loop"

    print("  - _run_dependency_health_check method exists: PASS")
    print("  - Method is callable: PASS")
    print("  - Method is called in run_loop: PASS")
    print("Step 1: PASS")
    return True


def verify_step2_loads_features():
    """Step 2: Load all features from database."""
    print("\n=== Step 2: Verify features are loaded from database ===")

    from parallel_orchestrator import ParallelOrchestrator

    # Create mock feature
    class MockFeature:
        def __init__(self, id):
            self.id = id
            self.name = f"Feature {id}"
            self.dependencies = []
            self.passes = False
            self.in_progress = False
            self.priority = id
            self.category = "test"
            self.description = "Test"
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

    with patch('parallel_orchestrator.create_database') as mock_create_db, \
         patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

        mock_engine = MagicMock()
        mock_session_maker = MagicMock()
        mock_create_db.return_value = (mock_engine, mock_session_maker)

        # Setup mock session
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_features = [MockFeature(i) for i in range(1, 6)]
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
            project_dir=Path("/tmp/test"),
            max_concurrency=3,
        )

        orchestrator._run_dependency_health_check()

        # Verify features were queried
        assert mock_session.query.called, "FAIL: session.query() not called"
        assert mock_query.all.called, "FAIL: query.all() not called"

    print("  - session.query() called: PASS")
    print("  - query.all() called to load all features: PASS")
    print("Step 2: PASS")
    return True


def verify_step3_calls_validate_dependency_graph():
    """Step 3: Call validate_dependency_graph() with loaded features."""
    print("\n=== Step 3: Verify validate_dependency_graph is called ===")

    from parallel_orchestrator import ParallelOrchestrator

    class MockFeature:
        def __init__(self, id, deps=None):
            self.id = id
            self.name = f"Feature {id}"
            self.dependencies = deps or []
            self.passes = False
            self.in_progress = False
            self.priority = id
            self.category = "test"
            self.description = "Test"
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

    with patch('parallel_orchestrator.create_database') as mock_create_db, \
         patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

        mock_engine = MagicMock()
        mock_session_maker = MagicMock()
        mock_create_db.return_value = (mock_engine, mock_session_maker)

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_features = [
            MockFeature(1, []),
            MockFeature(2, [1]),
            MockFeature(3, [1, 2]),
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
            project_dir=Path("/tmp/test"),
            max_concurrency=3,
        )

        orchestrator._run_dependency_health_check()

        # Verify validate_dependency_graph was called with feature dicts
        assert mock_validate.called, "FAIL: validate_dependency_graph not called"
        call_args = mock_validate.call_args[0][0]
        assert len(call_args) == 3, f"FAIL: Expected 3 features, got {len(call_args)}"
        assert all(isinstance(f, dict) for f in call_args), "FAIL: Features not converted to dicts"
        assert call_args[0]["id"] == 1, "FAIL: Feature 1 not passed correctly"
        assert call_args[1]["id"] == 2, "FAIL: Feature 2 not passed correctly"
        assert call_args[2]["id"] == 3, "FAIL: Feature 3 not passed correctly"

    print("  - validate_dependency_graph() called: PASS")
    print("  - Called with feature dicts: PASS")
    print("  - All features passed to validation: PASS")
    print("Step 3: PASS")
    return True


def verify_step4_handles_issues():
    """Step 4: If issues found, handle according to issue type before proceeding."""
    print("\n=== Step 4: Verify issues are handled by type ===")

    from parallel_orchestrator import ParallelOrchestrator

    class MockFeature:
        def __init__(self, id, deps=None):
            self.id = id
            self.name = f"Feature {id}"
            self.dependencies = deps or []
            self.passes = False
            self.in_progress = False
            self.priority = id
            self.category = "test"
            self.description = "Test"
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

    # Test auto-fix for self-reference
    with patch('parallel_orchestrator.create_database') as mock_create_db, \
         patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

        mock_engine = MagicMock()
        mock_session_maker = MagicMock()
        mock_create_db.return_value = (mock_engine, mock_session_maker)

        feature_with_self_ref = MockFeature(1, [1, 2])
        feature_normal = MockFeature(2, [])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature_with_self_ref, feature_normal]
        mock_filter = MagicMock()
        mock_filter.first.return_value = feature_with_self_ref
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
            project_dir=Path("/tmp/test"),
            max_concurrency=3,
        )

        result = orchestrator._run_dependency_health_check()

        # Self-reference should be auto-fixed
        assert 1 not in feature_with_self_ref.dependencies, \
            "FAIL: Self-reference not removed"
        assert mock_session.commit.called, "FAIL: commit not called after fix"

    print("  - Self-references are auto-fixed: PASS")

    # Test cycles block startup
    with patch('parallel_orchestrator.create_database') as mock_create_db, \
         patch('parallel_orchestrator.validate_dependency_graph') as mock_validate:

        mock_engine = MagicMock()
        mock_session_maker = MagicMock()
        mock_create_db.return_value = (mock_engine, mock_session_maker)

        feature_a = MockFeature(1, [2])
        feature_b = MockFeature(2, [1])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = [feature_a, feature_b]
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        mock_validate.return_value = {
            "is_valid": False,
            "self_references": [],
            "cycles": [[1, 2]],
            "missing_targets": {},
            "issues": [{
                "feature_id": 1,
                "issue_type": "cycle",
                "details": {"cycle_path": [1, 2]},
                "auto_fixable": False,
            }],
            "summary": "1 cycle(s) found (requires user action)",
        }

        orchestrator = ParallelOrchestrator(
            project_dir=Path("/tmp/test"),
            max_concurrency=3,
        )

        result = orchestrator._run_dependency_health_check()

        # Cycles should block startup
        assert result is False, "FAIL: Cycles should block startup (return False)"
        # Dependencies should NOT be changed
        assert feature_a.dependencies == [2], "FAIL: Cycle dependencies should not be auto-fixed"
        assert feature_b.dependencies == [1], "FAIL: Cycle dependencies should not be auto-fixed"

    print("  - Cycles block startup (return False): PASS")
    print("  - Cycles are NOT auto-fixed: PASS")
    print("Step 4: PASS")
    return True


def verify_step5_logs_summary():
    """Step 5: Log summary of dependency health check results."""
    print("\n=== Step 5: Verify summary is logged ===")

    import io
    import sys
    from parallel_orchestrator import ParallelOrchestrator

    class MockFeature:
        def __init__(self, id, deps=None):
            self.id = id
            self.name = f"Feature {id}"
            self.dependencies = deps or []
            self.passes = False
            self.in_progress = False
            self.priority = id
            self.category = "test"
            self.description = "Test"
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
            project_dir=Path("/tmp/test"),
            max_concurrency=3,
        )

        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output

        orchestrator._run_dependency_health_check()

        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()

        # Verify summary is logged
        assert "Running dependency health check" in output, \
            "FAIL: Health check start message not logged"
        assert "healthy" in output.lower(), \
            "FAIL: Health check result not logged"

    print("  - Health check start message logged: PASS")
    print("  - Health check result logged: PASS")
    print("Step 5: PASS")
    return True


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("  FEATURE #95 VERIFICATION")
    print("  Orchestrator runs validate_dependency_graph on startup")
    print("=" * 70)

    all_passed = True

    try:
        all_passed &= verify_step1_startup_hook_exists()
        all_passed &= verify_step2_loads_features()
        all_passed &= verify_step3_calls_validate_dependency_graph()
        all_passed &= verify_step4_handles_issues()
        all_passed &= verify_step5_logs_summary()
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        all_passed = False
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("  ALL VERIFICATION STEPS PASSED")
        print("  Feature #95 is implemented correctly")
    else:
        print("  VERIFICATION FAILED")
        print("  Feature #95 needs fixes")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
