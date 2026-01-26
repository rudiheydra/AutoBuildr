#!/usr/bin/env python3
"""
Verification Script for Feature #99: Auto-repair function removes self-references from features

This script verifies all 5 steps of the feature requirements:
1. Create repair_self_references(session) function
2. Query all features and check for self-references
3. Remove self-reference from each affected feature's dependencies list
4. Commit changes in a single transaction
5. Return list of repaired feature IDs for logging

Run this script to verify the implementation:
    python tests/verify_feature_99.py
"""

import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Base, Feature, create_database
from api.dependency_resolver import repair_self_references


def test_step1_create_function():
    """Step 1: Verify repair_self_references(session) function exists."""
    print("\n" + "=" * 70)
    print("Step 1: Create repair_self_references(session) function")
    print("=" * 70)

    # Check function exists
    assert callable(repair_self_references), "Function should be callable"

    # Check function signature
    import inspect
    sig = inspect.signature(repair_self_references)
    params = list(sig.parameters.keys())
    assert 'session' in params, "Function should accept 'session' parameter"

    print("  - Function exists: YES")
    print("  - Function is callable: YES")
    print("  - Accepts 'session' parameter: YES")
    print("\n  STEP 1: PASS")
    return True


def test_step2_query_all_features():
    """Step 2: Verify function queries all features and checks for self-references."""
    print("\n" + "=" * 70)
    print("Step 2: Query all features and check for self-references")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, session_maker = create_database(project_dir)
        session = session_maker()

        try:
            # Create 10 features - 5 with self-references, 5 without
            features_created = []
            for i in range(1, 11):
                has_self_ref = i <= 5  # Features 1-5 have self-refs
                feature = Feature(
                    id=i,
                    priority=i,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i] if has_self_ref else [],
                )
                session.add(feature)
                features_created.append(i)
            session.commit()

            print(f"  - Created {len(features_created)} features")
            print(f"  - Features with self-references: 1, 2, 3, 4, 5")
            print(f"  - Features without self-references: 6, 7, 8, 9, 10")

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify all features with self-refs were found
            expected = {1, 2, 3, 4, 5}
            actual = set(repaired_ids)

            assert expected == actual, f"Expected {expected}, got {actual}"

            print(f"  - Repaired feature IDs: {repaired_ids}")
            print("  - All self-referencing features detected: YES")
            print("\n  STEP 2: PASS")
            return True

        finally:
            session.close()


def test_step3_remove_self_reference():
    """Step 3: Verify self-reference is removed from each affected feature's dependencies list."""
    print("\n" + "=" * 70)
    print("Step 3: Remove self-reference from each affected feature's dependencies list")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, session_maker = create_database(project_dir)
        session = session_maker()

        try:
            # Create a feature with self-ref + valid deps
            for i in [100, 101, 102]:
                feature = Feature(
                    id=i,
                    priority=i - 99,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=True if i < 102 else False,
                    in_progress=False,
                    dependencies=[102, 100, 101] if i == 102 else [],  # 102 has self-ref + deps
                )
                session.add(feature)
            session.commit()

            print("  - Created feature 102 with dependencies: [102, 100, 101]")
            print("    (self-reference + 2 valid dependencies)")

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify self-reference was removed
            session.expire_all()
            fixed = session.query(Feature).filter(Feature.id == 102).first()

            assert fixed.dependencies == [100, 101], f"Expected [100, 101], got {fixed.dependencies}"
            assert 102 in repaired_ids, "Feature 102 should be in repaired IDs"

            print(f"  - After repair, feature 102 dependencies: {fixed.dependencies}")
            print("  - Self-reference removed: YES")
            print("  - Valid dependencies preserved: YES")
            print("\n  STEP 3: PASS")
            return True

        finally:
            session.close()


def test_step4_single_transaction():
    """Step 4: Verify changes are committed in a single transaction."""
    print("\n" + "=" * 70)
    print("Step 4: Commit changes in a single transaction")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, session_maker = create_database(project_dir)
        session = session_maker()

        try:
            # Create multiple features with self-references
            for i in range(200, 210):
                feature = Feature(
                    id=i,
                    priority=i - 199,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i],  # Self-reference
                )
                session.add(feature)
            session.commit()

            print("  - Created 10 features (200-209) with self-references")

            # Track commit calls
            original_commit = session.commit
            commit_count = [0]

            def counting_commit():
                commit_count[0] += 1
                original_commit()

            session.commit = counting_commit

            # Run repair
            repaired_ids = repair_self_references(session)

            print(f"  - Number of features repaired: {len(repaired_ids)}")
            print(f"  - Number of commits made: {commit_count[0]}")

            assert commit_count[0] == 1, f"Expected 1 commit, got {commit_count[0]}"
            assert len(repaired_ids) == 10, f"Expected 10 repairs, got {len(repaired_ids)}"

            print("  - Single transaction used: YES")
            print("\n  STEP 4: PASS")
            return True

        finally:
            session.close()


def test_step5_return_repaired_ids():
    """Step 5: Verify function returns list of repaired feature IDs for logging."""
    print("\n" + "=" * 70)
    print("Step 5: Return list of repaired feature IDs for logging")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, session_maker = create_database(project_dir)
        session = session_maker()

        try:
            # Create mix of features
            self_ref_ids = [300, 302, 304, 306, 308]
            no_self_ref_ids = [301, 303, 305, 307, 309]

            for i in range(300, 310):
                feature = Feature(
                    id=i,
                    priority=i - 299,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i] if i in self_ref_ids else [],
                )
                session.add(feature)
            session.commit()

            print(f"  - Features with self-references: {self_ref_ids}")
            print(f"  - Features without self-references: {no_self_ref_ids}")

            # Run repair
            repaired_ids = repair_self_references(session)

            print(f"  - Returned repaired IDs: {repaired_ids}")

            # Verify return value
            assert isinstance(repaired_ids, list), f"Expected list, got {type(repaired_ids)}"
            assert set(repaired_ids) == set(self_ref_ids), f"Expected {self_ref_ids}, got {repaired_ids}"

            print("  - Return type is list: YES")
            print("  - Contains all repaired feature IDs: YES")
            print("  - Suitable for logging: YES")
            print("\n  STEP 5: PASS")
            return True

        finally:
            session.close()


def main():
    """Run all verification steps."""
    print("\n" + "=" * 70)
    print("Feature #99 Verification: Auto-repair function removes self-references")
    print("=" * 70)

    results = []

    # Run all steps
    try:
        results.append(("Step 1", test_step1_create_function()))
    except Exception as e:
        print(f"\n  STEP 1: FAIL - {e}")
        results.append(("Step 1", False))

    try:
        results.append(("Step 2", test_step2_query_all_features()))
    except Exception as e:
        print(f"\n  STEP 2: FAIL - {e}")
        results.append(("Step 2", False))

    try:
        results.append(("Step 3", test_step3_remove_self_reference()))
    except Exception as e:
        print(f"\n  STEP 3: FAIL - {e}")
        results.append(("Step 3", False))

    try:
        results.append(("Step 4", test_step4_single_transaction()))
    except Exception as e:
        print(f"\n  STEP 4: FAIL - {e}")
        results.append(("Step 4", False))

    try:
        results.append(("Step 5", test_step5_return_repaired_ids()))
    except Exception as e:
        print(f"\n  STEP 5: FAIL - {e}")
        results.append(("Step 5", False))

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for step, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {step}: {status}")

    print(f"\n  Total: {passed}/{total} steps passed")

    if passed == total:
        print("\n  FEATURE #99: ALL STEPS VERIFIED - READY TO MARK AS PASSING")
        return 0
    else:
        print("\n  FEATURE #99: VERIFICATION INCOMPLETE")
        return 1


if __name__ == "__main__":
    sys.exit(main())
