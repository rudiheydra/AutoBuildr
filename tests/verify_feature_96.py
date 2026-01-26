#!/usr/bin/env python3
"""
Standalone Verification Script for Feature #96:
Startup health check auto-fixes self-references with warning

This script verifies all 5 steps from the feature requirements:
1. Insert a feature with self-reference into database
2. Start the orchestrator
3. Verify the self-reference is automatically removed from the feature
4. Verify a WARNING level log is emitted with feature ID and action taken
5. Verify orchestrator continues to normal operation after fix

Run: python tests/verify_feature_96.py
"""

import logging
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature, create_database


def print_step(step_num: int, description: str, status: str = ""):
    """Print a formatted step."""
    icon = "" if status == "PASS" else "" if status == "FAIL" else ""
    if status:
        print(f"  Step {step_num}: {description} - {status} {icon}")
    else:
        print(f"  Step {step_num}: {description}...")


def print_header(title: str):
    """Print a formatted header."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def verify_feature_96():
    """Run verification for Feature #96."""
    print_header("Feature #96: Startup health check auto-fixes self-references")
    print()

    all_passed = True
    captured_warnings = []

    # Create temp directory for test database
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, session_maker = create_database(project_dir)

        # =========================================================================
        # Step 1: Insert a feature with self-reference into database
        # =========================================================================
        print_step(1, "Insert a feature with self-reference into database")

        session = session_maker()
        try:
            feature = Feature(
                id=999,
                priority=1,
                category="test",
                name="Self-referencing feature for verification",
                description="This feature depends on itself (invalid)",
                steps=["Step 1", "Step 2"],
                passes=False,
                in_progress=False,
                dependencies=[999],  # Self-reference!
            )
            session.add(feature)
            session.commit()

            # Verify insertion
            loaded = session.query(Feature).filter(Feature.id == 999).first()
            if loaded and loaded.dependencies == [999]:
                print_step(1, "Insert a feature with self-reference into database", "PASS")
                print(f"    - Feature #999 created with dependencies=[999]")
            else:
                print_step(1, "Insert a feature with self-reference into database", "FAIL")
                print(f"    - Failed to insert feature with self-reference")
                all_passed = False
        finally:
            session.close()

        # =========================================================================
        # Step 2 & 3: Start the orchestrator and verify self-reference is removed
        # =========================================================================
        print_step(2, "Start the orchestrator (run health check)")

        # Set up logging capture
        class WarningCaptureHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.warnings = []

            def emit(self, record):
                if record.levelno == logging.WARNING:
                    self.warnings.append(record)

        # Add handler to capture warnings
        capture_handler = WarningCaptureHandler()
        capture_handler.setLevel(logging.WARNING)

        orchestrator_logger = logging.getLogger("parallel_orchestrator")
        original_level = orchestrator_logger.level
        orchestrator_logger.setLevel(logging.WARNING)
        orchestrator_logger.addHandler(capture_handler)

        try:
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            # Run the health check (this is what happens on startup)
            result = orchestrator._run_dependency_health_check()

            if result is True:
                print_step(2, "Start the orchestrator (run health check)", "PASS")
                print(f"    - Health check completed successfully")
            else:
                print_step(2, "Start the orchestrator (run health check)", "FAIL")
                print(f"    - Health check returned {result}")
                all_passed = False

            # Copy captured warnings for step 4
            captured_warnings = capture_handler.warnings.copy()

        finally:
            orchestrator_logger.removeHandler(capture_handler)
            orchestrator_logger.setLevel(original_level)

        # =========================================================================
        # Step 3: Verify the self-reference is automatically removed
        # =========================================================================
        print_step(3, "Verify the self-reference is automatically removed")

        new_session = session_maker()
        try:
            fixed_feature = new_session.query(Feature).filter(Feature.id == 999).first()
            if fixed_feature and fixed_feature.dependencies == []:
                print_step(3, "Verify the self-reference is automatically removed", "PASS")
                print(f"    - Feature #999 dependencies changed: [999] -> []")
            else:
                deps = fixed_feature.dependencies if fixed_feature else None
                print_step(3, "Verify the self-reference is automatically removed", "FAIL")
                print(f"    - Feature #999 dependencies: {deps} (expected [])")
                all_passed = False
        finally:
            new_session.close()

        # =========================================================================
        # Step 4: Verify a WARNING level log is emitted with feature ID
        # =========================================================================
        print_step(4, "Verify a WARNING level log is emitted with feature ID")

        # Check captured warnings
        self_ref_warnings = [
            w for w in captured_warnings
            if "999" in w.getMessage() and "self-reference" in w.getMessage().lower()
        ]

        if self_ref_warnings:
            print_step(4, "Verify a WARNING level log is emitted with feature ID", "PASS")
            print(f"    - Found WARNING log: {self_ref_warnings[0].getMessage()[:80]}...")
        else:
            print_step(4, "Verify a WARNING level log is emitted with feature ID", "FAIL")
            print(f"    - No WARNING log found for feature #999")
            print(f"    - Captured warnings: {[w.getMessage() for w in captured_warnings]}")
            all_passed = False

        # =========================================================================
        # Step 5: Verify orchestrator continues to normal operation after fix
        # =========================================================================
        print_step(5, "Verify orchestrator continues to normal operation after fix")

        try:
            # The orchestrator should be able to get ready features without error
            ready = orchestrator.get_ready_features()
            if isinstance(ready, list):
                print_step(5, "Verify orchestrator continues to normal operation after fix", "PASS")
                print(f"    - get_ready_features() returned {len(ready)} features")
            else:
                print_step(5, "Verify orchestrator continues to normal operation after fix", "FAIL")
                print(f"    - get_ready_features() returned unexpected type: {type(ready)}")
                all_passed = False
        except Exception as e:
            print_step(5, "Verify orchestrator continues to normal operation after fix", "FAIL")
            print(f"    - Error: {e}")
            all_passed = False

    # =========================================================================
    # Summary
    # =========================================================================
    print()
    print("=" * 70)
    if all_passed:
        print("  RESULT: ALL 5 VERIFICATION STEPS PASSED")
    else:
        print("  RESULT: SOME VERIFICATION STEPS FAILED")
    print("=" * 70)
    print()

    return all_passed


if __name__ == "__main__":
    success = verify_feature_96()
    sys.exit(0 if success else 1)
