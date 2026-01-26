#!/usr/bin/env python3
"""
Verification script for Feature #102: Dependency health check produces clear formatted log output

This script verifies each of the 6 steps in the feature description by
simulating different scenarios and checking the output format.

Steps:
1. Create formatted log header: === DEPENDENCY HEALTH CHECK ===
2. List self-references found and auto-fixed (if any)
3. List orphaned references found and auto-removed (if any)
4. List cycles found requiring user action (if any)
5. End with summary: X issues auto-fixed, Y issues require attention
6. If no issues: Dependency graph is healthy
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockFeature:
    """Mock feature for testing."""

    def __init__(self, id: int, dependencies: list[int] = None, passes: bool = False, in_progress: bool = False):
        self.id = id
        self.dependencies = dependencies or []
        self.passes = passes
        self.in_progress = in_progress
        self.priority = id
        self.category = "test"
        self.name = f"Test Feature {id}"
        self.description = f"Test feature {id} description"
        self.steps = ["Step 1", "Step 2"]

    def to_dict(self):
        return {
            "id": self.id,
            "priority": self.priority,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "passes": self.passes,
            "in_progress": self.in_progress,
            "dependencies": self.dependencies,
        }


class MockSession:
    """Mock database session."""

    def __init__(self, features: list[MockFeature] = None):
        self.features = features or []
        self.committed = False

    def query(self, model):
        return MockQuery(self.features)

    def commit(self):
        self.committed = True

    def close(self):
        pass


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, features: list[MockFeature]):
        self.features = features

    def all(self):
        return self.features

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.features:
            return self.features[0]
        return None


def run_health_check(features: list[MockFeature], validation_result: dict):
    """Run the health check with mocked dependencies and return output."""
    from parallel_orchestrator import ParallelOrchestrator

    def mock_session():
        session = MockSession(features)
        original_query = session.query

        def patched_query(model):
            query = original_query(model)
            original_filter = query.filter

            def patched_filter(*args, **kwargs):
                # Return all features for query
                return query

            query.filter = patched_filter
            return query

        session.query = patched_query
        return session

    with patch("parallel_orchestrator.create_database") as mock_db:
        mock_engine = MagicMock()
        mock_db.return_value = (mock_engine, mock_session)

        orchestrator = ParallelOrchestrator(
            project_dir=Path("/tmp/test-project"),
            max_concurrency=1,
        )
        orchestrator._session_maker = mock_session

        with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
            mock_validate.return_value = validation_result

            output = io.StringIO()
            with redirect_stdout(output):
                result = orchestrator._run_dependency_health_check()

            return output.getvalue(), result


def verify_step_1():
    """Step 1: Create formatted log header: === DEPENDENCY HEALTH CHECK ==="""
    print("\n" + "=" * 70)
    print("STEP 1: Create formatted log header: === DEPENDENCY HEALTH CHECK ===")
    print("=" * 70)

    features = [MockFeature(1, [], True)]
    validation_result = {
        "is_valid": True,
        "self_references": [],
        "cycles": [],
        "missing_targets": {},
        "issues": [],
        "summary": "No issues",
    }

    output, result = run_health_check(features, validation_result)

    # Check for header
    has_header = "=== DEPENDENCY HEALTH CHECK ===" in output
    has_decorative = "=" * 60 in output

    print(f"\nOutput:\n{output}")
    print(f"\nResult:")
    print(f"  - Header present: {'PASS' if has_header else 'FAIL'}")
    print(f"  - Decorative equals: {'PASS' if has_decorative else 'FAIL'}")

    return has_header and has_decorative


def verify_step_2():
    """Step 2: List self-references found and auto-fixed (if any)"""
    print("\n" + "=" * 70)
    print("STEP 2: List self-references found and auto-fixed (if any)")
    print("=" * 70)

    feature1 = MockFeature(1, [1])  # Self-reference
    validation_result = {
        "is_valid": False,
        "self_references": [1],
        "cycles": [],
        "missing_targets": {},
        "issues": ["Self-reference"],
        "summary": "1 self-reference",
    }

    output, result = run_health_check([feature1], validation_result)

    # Check for self-references section
    has_section = "SELF-REFERENCES FOUND" in output
    has_auto_fix = "auto-fix" in output.lower()

    print(f"\nOutput:\n{output}")
    print(f"\nResult:")
    print(f"  - Section header present: {'PASS' if has_section else 'FAIL'}")
    print(f"  - Auto-fix message: {'PASS' if has_auto_fix else 'FAIL'}")

    return has_section and has_auto_fix


def verify_step_3():
    """Step 3: List orphaned references found and auto-removed (if any)"""
    print("\n" + "=" * 70)
    print("STEP 3: List orphaned references found and auto-removed (if any)")
    print("=" * 70)

    feature1 = MockFeature(1, [999])  # Orphaned reference
    validation_result = {
        "is_valid": False,
        "self_references": [],
        "cycles": [],
        "missing_targets": {1: [999]},
        "issues": ["Missing target"],
        "summary": "1 orphaned reference",
    }

    output, result = run_health_check([feature1], validation_result)

    # Check for orphaned references section
    has_section = "ORPHANED REFERENCES FOUND" in output
    has_auto_remove = "auto-remov" in output.lower()

    print(f"\nOutput:\n{output}")
    print(f"\nResult:")
    print(f"  - Section header present: {'PASS' if has_section else 'FAIL'}")
    print(f"  - Auto-remove message: {'PASS' if has_auto_remove else 'FAIL'}")

    return has_section and has_auto_remove


def verify_step_4():
    """Step 4: List cycles found requiring user action (if any)"""
    print("\n" + "=" * 70)
    print("STEP 4: List cycles found requiring user action (if any)")
    print("=" * 70)

    feature1 = MockFeature(1, [2])
    feature2 = MockFeature(2, [1])
    validation_result = {
        "is_valid": False,
        "self_references": [],
        "cycles": [[1, 2]],
        "missing_targets": {},
        "issues": ["Cycle detected"],
        "summary": "1 cycle",
    }

    output, result = run_health_check([feature1, feature2], validation_result)

    # Check for cycles section
    has_section = "CYCLES FOUND" in output
    has_user_action = "user action" in output.lower() or "require" in output.lower()
    blocks_startup = result is False

    print(f"\nOutput:\n{output}")
    print(f"\nResult:")
    print(f"  - Section header present: {'PASS' if has_section else 'FAIL'}")
    print(f"  - User action message: {'PASS' if has_user_action else 'FAIL'}")
    print(f"  - Blocks startup: {'PASS' if blocks_startup else 'FAIL'}")

    return has_section and has_user_action and blocks_startup


def verify_step_5():
    """Step 5: End with summary: X issues auto-fixed, Y issues require attention"""
    print("\n" + "=" * 70)
    print("STEP 5: End with summary: X issues auto-fixed, Y issues require attention")
    print("=" * 70)

    # Test 5a: Auto-fixed issues only
    print("\n5a: Testing auto-fixed issues summary...")
    feature1 = MockFeature(1, [1])  # Self-reference
    validation_result = {
        "is_valid": False,
        "self_references": [1],
        "cycles": [],
        "missing_targets": {},
        "issues": ["Self-reference"],
        "summary": "1 self-reference",
    }

    output_a, result_a = run_health_check([feature1], validation_result)
    has_summary_a = "Summary:" in output_a or "auto-fixed" in output_a.lower()
    print(f"  Output contains summary: {'PASS' if has_summary_a else 'FAIL'}")

    # Test 5b: Issues requiring attention (cycles)
    print("\n5b: Testing issues requiring attention summary...")
    feature1 = MockFeature(1, [2])
    feature2 = MockFeature(2, [1])
    validation_result = {
        "is_valid": False,
        "self_references": [],
        "cycles": [[1, 2]],
        "missing_targets": {},
        "issues": ["Cycle detected"],
        "summary": "1 cycle",
    }

    output_b, result_b = run_health_check([feature1, feature2], validation_result)
    has_attention = "require attention" in output_b.lower() or "issues require" in output_b.lower()
    print(f"  Output contains 'require attention': {'PASS' if has_attention else 'FAIL'}")

    print(f"\nOutput for 5a:\n{output_a}")
    print(f"\nOutput for 5b:\n{output_b}")

    return has_summary_a and has_attention


def verify_step_6():
    """Step 6: If no issues: Dependency graph is healthy"""
    print("\n" + "=" * 70)
    print("STEP 6: If no issues: Dependency graph is healthy")
    print("=" * 70)

    feature1 = MockFeature(1, [], True)
    feature2 = MockFeature(2, [1], True)
    validation_result = {
        "is_valid": True,
        "self_references": [],
        "cycles": [],
        "missing_targets": {},
        "issues": [],
        "summary": "No issues",
    }

    output, result = run_health_check([feature1, feature2], validation_result)

    # Check for healthy message
    has_healthy = "healthy" in output.lower()
    returns_true = result is True

    print(f"\nOutput:\n{output}")
    print(f"\nResult:")
    print(f"  - 'Healthy' message present: {'PASS' if has_healthy else 'FAIL'}")
    print(f"  - Returns True: {'PASS' if returns_true else 'FAIL'}")

    return has_healthy and returns_true


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("FEATURE #102: Dependency health check produces clear formatted log output")
    print("=" * 70)

    results = []

    results.append(("Step 1: Formatted log header", verify_step_1()))
    results.append(("Step 2: Self-references section", verify_step_2()))
    results.append(("Step 3: Orphaned references section", verify_step_3()))
    results.append(("Step 4: Cycles section", verify_step_4()))
    results.append(("Step 5: Summary line", verify_step_5()))
    results.append(("Step 6: Healthy graph message", verify_step_6()))

    # Print final summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    all_pass = True
    for step_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {step_name}: {status}")
        if not passed:
            all_pass = False

    print("\n" + "=" * 70)
    if all_pass:
        print("ALL VERIFICATION STEPS PASSED")
    else:
        print("SOME VERIFICATION STEPS FAILED")
    print("=" * 70)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
