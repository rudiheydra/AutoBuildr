#!/usr/bin/env python3
"""
Verification script for Feature #100: Auto-repair function removes orphaned dependency references

This script verifies each step from the feature's verification steps:
1. Create repair_orphaned_dependencies(session) function
2. Get set of all valid feature IDs
3. For each feature, filter dependencies to only valid IDs
4. Update features with orphaned refs in single transaction
5. Return dict of {feature_id: [removed_orphan_ids]} for logging
"""

import inspect
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.database import Base, Feature


def step_1_function_exists():
    """Step 1: Create repair_orphaned_dependencies(session) function"""
    print("\nStep 1: Create repair_orphaned_dependencies(session) function")
    print("-" * 60)

    try:
        from api.dependency_resolver import repair_orphaned_dependencies

        # Verify it exists
        assert repair_orphaned_dependencies is not None, "Function should exist"
        print("  ✓ Function exists")

        # Verify it's callable
        assert callable(repair_orphaned_dependencies), "Function should be callable"
        print("  ✓ Function is callable")

        # Verify signature has 'session' parameter
        sig = inspect.signature(repair_orphaned_dependencies)
        params = list(sig.parameters.keys())
        assert len(params) == 1, f"Expected 1 parameter, got {len(params)}"
        assert params[0] == "session", f"Expected 'session', got '{params[0]}'"
        print("  ✓ Function signature: repair_orphaned_dependencies(session)")

        print("\n  PASS: Step 1 verified")
        return True

    except Exception as e:
        print(f"\n  FAIL: {e}")
        return False


def step_2_gets_valid_feature_ids():
    """Step 2: Get set of all valid feature IDs"""
    print("\nStep 2: Get set of all valid feature IDs")
    print("-" * 60)

    try:
        from api.dependency_resolver import repair_orphaned_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create features with IDs 1, 2, 3
                f1 = Feature(id=1, priority=1, category="A", name="Feature 1",
                            description="Desc 1", steps=["s1"], dependencies=None)
                f2 = Feature(id=2, priority=2, category="A", name="Feature 2",
                            description="Desc 2", steps=["s2"], dependencies=None)
                f3 = Feature(id=3, priority=3, category="A", name="Feature 3",
                            description="Desc 3", steps=["s3"],
                            dependencies=[1, 999, 2, 888])  # 999, 888 don't exist

                session.add_all([f1, f2, f3])
                session.commit()
                print("  Created 3 features (IDs: 1, 2, 3)")
                print("  Feature 3 depends on: [1, 999, 2, 888]")
                print("  Valid IDs: {1, 2, 3}")
                print("  Orphan IDs: {999, 888}")

                # Run repair
                repairs = repair_orphaned_dependencies(session)

                # Verify it identified orphans correctly
                assert 3 in repairs, "Feature 3 should be in repairs"
                assert set(repairs[3]) == {999, 888}, f"Expected orphans {{999, 888}}, got {repairs[3]}"
                print(f"  ✓ Correctly identified orphans: {repairs[3]}")

                # Features 1, 2 have no orphans
                assert 1 not in repairs, "Feature 1 should not be in repairs"
                assert 2 not in repairs, "Feature 2 should not be in repairs"
                print("  ✓ Features 1, 2 correctly identified as having no orphans")

                print("\n  PASS: Step 2 verified")
                return True

            finally:
                session.close()

    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_3_filters_to_valid_deps():
    """Step 3: For each feature, filter dependencies to only valid IDs"""
    print("\nStep 3: For each feature, filter dependencies to only valid IDs")
    print("-" * 60)

    try:
        from api.dependency_resolver import repair_orphaned_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create features
                f1 = Feature(id=1, priority=1, category="A", name="Feature 1",
                            description="Desc 1", steps=["s1"], dependencies=None)
                f2 = Feature(id=2, priority=2, category="A", name="Feature 2",
                            description="Desc 2", steps=["s2"], dependencies=None)
                f3 = Feature(id=3, priority=3, category="A", name="Feature 3",
                            description="Desc 3", steps=["s3"],
                            dependencies=[1, 999, 2, 888])

                session.add_all([f1, f2, f3])
                session.commit()
                print("  Before repair:")
                print(f"    Feature 3 dependencies: [1, 999, 2, 888]")

                # Run repair
                repair_orphaned_dependencies(session)

                # Verify filtering worked
                session.refresh(f3)
                new_deps = f3.dependencies or []
                print(f"  After repair:")
                print(f"    Feature 3 dependencies: {new_deps}")

                # Should have only valid deps (1, 2)
                assert set(new_deps) == {1, 2}, f"Expected {{1, 2}}, got {set(new_deps)}"
                print("  ✓ Orphan deps removed, valid deps preserved")

                print("\n  PASS: Step 3 verified")
                return True

            finally:
                session.close()

    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_4_single_transaction():
    """Step 4: Update features with orphaned refs in single transaction"""
    print("\nStep 4: Update features with orphaned refs in single transaction")
    print("-" * 60)

    try:
        from api.dependency_resolver import repair_orphaned_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create multiple features with orphans
                f1 = Feature(id=1, priority=1, category="A", name="Feature 1",
                            description="Desc 1", steps=["s1"], dependencies=[999])
                f2 = Feature(id=2, priority=2, category="A", name="Feature 2",
                            description="Desc 2", steps=["s2"], dependencies=[888])
                f3 = Feature(id=3, priority=3, category="A", name="Feature 3",
                            description="Desc 3", steps=["s3"], dependencies=[777])

                session.add_all([f1, f2, f3])
                session.commit()
                print("  Created 3 features with orphan dependencies:")
                print("    Feature 1: [999]")
                print("    Feature 2: [888]")
                print("    Feature 3: [777]")

                # Run repair
                repairs = repair_orphaned_dependencies(session)
                print(f"  Repaired {len(repairs)} features in single call")

                # Verify all were repaired
                assert len(repairs) == 3, f"Expected 3 repairs, got {len(repairs)}"

                # Open new session to verify persistence
                session2 = SessionLocal()
                try:
                    features = session2.query(Feature).all()
                    print("  Verified in new session (persisted to database):")
                    for f in features:
                        deps = f.dependencies or []
                        print(f"    Feature {f.id}: {deps}")
                        assert deps == [], f"Feature {f.id} should have empty deps"

                    print("  ✓ All changes persisted in single transaction")
                finally:
                    session2.close()

                print("\n  PASS: Step 4 verified")
                return True

            finally:
                session.close()

    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_5_returns_dict():
    """Step 5: Return dict of {feature_id: [removed_orphan_ids]} for logging"""
    print("\nStep 5: Return dict of {feature_id: [removed_orphan_ids]} for logging")
    print("-" * 60)

    try:
        from api.dependency_resolver import repair_orphaned_dependencies

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create features with known orphan dependencies
                f1 = Feature(id=10, priority=1, category="A", name="Feature 10",
                            description="Desc 1", steps=["s1"],
                            dependencies=[100, 200, 300])  # All orphans
                f2 = Feature(id=20, priority=2, category="A", name="Feature 20",
                            description="Desc 2", steps=["s2"],
                            dependencies=[10, 400, 500])  # 10 valid, 400/500 orphans

                session.add_all([f1, f2])
                session.commit()

                # Run repair
                repairs = repair_orphaned_dependencies(session)

                # Verify return type
                assert isinstance(repairs, dict), f"Expected dict, got {type(repairs)}"
                print("  ✓ Returns dict type")

                # Verify structure
                assert 10 in repairs, "Feature 10 should be in repairs"
                assert 20 in repairs, "Feature 20 should be in repairs"
                print("  ✓ Contains repaired feature IDs as keys")

                # Verify values are lists of removed orphans
                assert isinstance(repairs[10], list), "Value should be list"
                assert isinstance(repairs[20], list), "Value should be list"
                print("  ✓ Values are lists")

                # Verify correct orphan IDs
                assert set(repairs[10]) == {100, 200, 300}, f"Expected {{100, 200, 300}}, got {repairs[10]}"
                assert set(repairs[20]) == {400, 500}, f"Expected {{400, 500}}, got {repairs[20]}"
                print(f"  ✓ Feature 10: removed orphans {repairs[10]}")
                print(f"  ✓ Feature 20: removed orphans {repairs[20]}")

                # Verify format suitable for logging
                print("\n  Example log output from repairs dict:")
                for fid, orphans in repairs.items():
                    print(f"    Feature #{fid}: removed orphan deps {orphans}")

                print("\n  PASS: Step 5 verified")
                return True

            finally:
                session.close()

    except Exception as e:
        print(f"\n  FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #100: Auto-repair function removes orphaned dependency references")
    print("=" * 70)

    results = {
        "Step 1: Create repair_orphaned_dependencies(session) function": step_1_function_exists(),
        "Step 2: Get set of all valid feature IDs": step_2_gets_valid_feature_ids(),
        "Step 3: Filter dependencies to only valid IDs": step_3_filters_to_valid_deps(),
        "Step 4: Update features in single transaction": step_4_single_transaction(),
        "Step 5: Return dict of {feature_id: [removed_orphan_ids]}": step_5_returns_dict(),
    }

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = 0
    failed = 0
    for step, result in results.items():
        status = "PASS ✓" if result else "FAIL ✗"
        print(f"  {step}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Results: {passed}/{len(results)} steps passed")

    if failed == 0:
        print("\n✓ ALL VERIFICATION STEPS PASSED")
        return 0
    else:
        print(f"\n✗ {failed} VERIFICATION STEP(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
