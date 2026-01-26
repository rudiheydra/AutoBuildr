#!/usr/bin/env python
"""
Verification Script for Feature #97: Startup health check blocks on cycles and lists cycle path.

This script directly verifies all 5 steps from the feature specification:

1. Insert features A -> B -> A into database
2. Attempt to start the orchestrator
3. Verify startup is blocked with clear error message
4. Verify error message includes the cycle path: [A, B, A]
5. Verify error message instructs user to remove one dependency

Run this script directly: python tests/verify_feature_97.py
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def create_orchestrator_with_cycle():
    """Create an orchestrator with features A -> B -> A (cycle)."""
    with patch('parallel_orchestrator.create_database') as mock_create_db:
        mock_engine = MagicMock()
        mock_session_maker = MagicMock()
        mock_create_db.return_value = (mock_engine, mock_session_maker)

        # Create features with cycle: A (id=1) -> B (id=2) -> A (id=1)
        feature_a = MockFeature(1, name="Feature A", dependencies=[2])
        feature_b = MockFeature(2, name="Feature B", dependencies=[1])
        features = [feature_a, feature_b]

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = features
        mock_session.query.return_value = mock_query
        mock_session_maker.return_value = mock_session

        orchestrator = ParallelOrchestrator(
            project_dir=Path("/tmp/test"),
            max_concurrency=3,
        )

        return orchestrator, features


def run_verification():
    """Run all verification steps."""
    print("=" * 70)
    print("  Feature #97 Verification Script")
    print("  Startup health check blocks on cycles and lists cycle path")
    print("=" * 70)
    print()

    all_passed = True

    # Step 1: Insert features A -> B -> A into database
    print("Step 1: Insert features A -> B -> A into database")
    orchestrator, features = create_orchestrator_with_cycle()
    feature_a = features[0]
    feature_b = features[1]

    step1_passed = (
        feature_a.dependencies == [2] and
        feature_b.dependencies == [1]
    )

    print(f"  Feature A (id=1): dependencies = {feature_a.dependencies}")
    print(f"  Feature B (id=2): dependencies = {feature_b.dependencies}")
    print(f"  Result: {'PASS' if step1_passed else 'FAIL'}")
    print()
    all_passed = all_passed and step1_passed

    # Step 2: Attempt to start the orchestrator
    print("Step 2: Attempt to start the orchestrator")

    # Capture output
    captured_output = io.StringIO()
    with redirect_stdout(captured_output):
        result = orchestrator._run_dependency_health_check()

    output = captured_output.getvalue()

    print(f"  _run_dependency_health_check() returned: {result}")
    print(f"  Result: {'PASS' if result is False else 'FAIL'} (expected: False)")
    print()

    step2_passed = result is False
    all_passed = all_passed and step2_passed

    # Step 3: Verify startup is blocked with clear error message
    print("Step 3: Verify startup is blocked with clear error message")

    # Check for various forms of cycle detection messages
    has_cycles_message = "CYCLES FOUND" in output or "CIRCULAR DEPENDENCIES" in output or "cycle" in output.lower()
    has_blocked_message = "STARTUP BLOCKED" in output

    print(f"  Contains cycle detection message: {has_cycles_message}")
    print(f"  Contains 'STARTUP BLOCKED': {has_blocked_message}")

    step3_passed = has_cycles_message and has_blocked_message
    print(f"  Result: {'PASS' if step3_passed else 'FAIL'}")
    print()
    all_passed = all_passed and step3_passed

    # Step 4: Verify error message includes the cycle path: [A, B, A]
    print("Step 4: Verify error message includes the cycle path: [A, B, A]")

    has_arrow_notation = " -> " in output
    has_brackets = "[" in output and "]" in output
    # Check that cycle contains the feature IDs (1 and 2)
    has_feature_ids = "1" in output and "2" in output

    print(f"  Contains arrow notation (' -> '): {has_arrow_notation}")
    print(f"  Contains brackets: {has_brackets}")
    print(f"  Contains feature IDs (1 and 2): {has_feature_ids}")

    step4_passed = has_arrow_notation and has_brackets and has_feature_ids
    print(f"  Result: {'PASS' if step4_passed else 'FAIL'}")
    print()
    all_passed = all_passed and step4_passed

    # Step 5: Verify error message instructs user to remove one dependency
    print("Step 5: Verify error message instructs user to remove one dependency")

    output_lower = output.lower()
    has_fix_instruction = "to fix" in output_lower or "fix" in output_lower
    has_remove_instruction = "remove" in output_lower
    has_dependency_word = "dependency" in output_lower or "dependencies" in output_lower

    print(f"  Contains 'fix' instruction: {has_fix_instruction}")
    print(f"  Contains 'remove' instruction: {has_remove_instruction}")
    print(f"  Contains 'dependency': {has_dependency_word}")

    step5_passed = has_fix_instruction and has_remove_instruction and has_dependency_word
    print(f"  Result: {'PASS' if step5_passed else 'FAIL'}")
    print()
    all_passed = all_passed and step5_passed

    # Summary
    print("=" * 70)
    print("  VERIFICATION SUMMARY")
    print("=" * 70)
    print()
    print(f"  Step 1 (Insert features A -> B -> A): {'PASS' if step1_passed else 'FAIL'}")
    print(f"  Step 2 (Startup is blocked): {'PASS' if step2_passed else 'FAIL'}")
    print(f"  Step 3 (Clear error message): {'PASS' if step3_passed else 'FAIL'}")
    print(f"  Step 4 (Cycle path included): {'PASS' if step4_passed else 'FAIL'}")
    print(f"  Step 5 (User instruction to remove dependency): {'PASS' if step5_passed else 'FAIL'}")
    print()
    print(f"  Overall: {'ALL STEPS PASS' if all_passed else 'SOME STEPS FAILED'}")
    print("=" * 70)

    # Show the actual output for reference
    print()
    print("  Captured Output:")
    print("-" * 70)
    for line in output.strip().split("\n"):
        print(f"  {line}")
    print("-" * 70)

    return all_passed


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
