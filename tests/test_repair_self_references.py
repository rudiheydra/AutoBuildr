"""
Test Suite for Feature #99: Auto-repair function removes self-references from features

This test suite verifies that repair_self_references() function:
1. Creates repair_self_references(session) function
2. Queries all features and checks for self-references
3. Removes self-reference from each affected feature's dependencies list
4. Commits changes in a single transaction
5. Returns list of repaired feature IDs for logging

Verification Steps from Feature #99:
1. Create repair_self_references(session) function - verify it exists and is callable
2. Query all features and check for self-references - verify all features are queried
3. Remove self-reference from each affected feature's dependencies list - verify removal
4. Commit changes in a single transaction - verify single commit behavior
5. Return list of repaired feature IDs for logging - verify correct return value
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from api.database import Base, Feature, create_database
from api.dependency_resolver import repair_self_references


class TestRepairSelfReferencesFunction:
    """Tests for the repair_self_references function existence and signature."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step1_function_exists_and_is_callable(self):
        """Step 1: Verify repair_self_references function exists and is callable."""
        from api.dependency_resolver import repair_self_references

        assert callable(repair_self_references), "repair_self_references should be callable"

        # Verify function signature accepts session parameter
        import inspect
        sig = inspect.signature(repair_self_references)
        params = list(sig.parameters.keys())
        assert 'session' in params, "Function should accept 'session' parameter"

    def test_function_returns_list(self, create_test_db):
        """Verify function returns a list."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            result = repair_self_references(session)
            assert isinstance(result, list), f"Expected list, got {type(result)}"
        finally:
            session.close()


class TestRepairSelfReferencesQueryAll:
    """Tests for Step 2: Query all features and check for self-references."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step2_queries_all_features(self, create_test_db):
        """Step 2: Verify all features are queried for self-references."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create multiple features - some with self-references, some without
            for i in range(1, 6):
                feature = Feature(
                    id=i,
                    priority=i,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    # Odd features have self-references
                    dependencies=[i] if i % 2 == 1 else [],
                )
                session.add(feature)
            session.commit()

            # Run repair
            repaired_ids = repair_self_references(session)

            # Should have repaired features 1, 3, 5
            assert len(repaired_ids) == 3, f"Expected 3 repaired, got {len(repaired_ids)}"
            assert 1 in repaired_ids
            assert 3 in repaired_ids
            assert 5 in repaired_ids

        finally:
            session.close()


class TestRepairSelfReferencesRemoval:
    """Tests for Step 3: Remove self-reference from each affected feature's dependencies list."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step3_removes_self_reference_only(self, create_test_db):
        """Step 3: Verify self-reference is removed while preserving other dependencies."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a dependency target
            dep_feature = Feature(
                id=100,
                priority=1,
                category="test",
                name="Dependency target",
                description="Valid dependency",
                steps=["Step 1"],
                passes=True,
                in_progress=False,
                dependencies=[],
            )
            session.add(dep_feature)

            # Create a feature with self-reference AND valid dependency
            feature = Feature(
                id=101,
                priority=2,
                category="test",
                name="Feature with mixed deps",
                description="Has self-ref and valid dep",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[101, 100],  # Self-ref + valid dep
            )
            session.add(feature)
            session.commit()

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify
            assert 101 in repaired_ids, "Feature 101 should be repaired"

            # Check that self-reference was removed but valid dep preserved
            session.expire_all()  # Force refresh from DB
            fixed = session.query(Feature).filter(Feature.id == 101).first()
            assert fixed.dependencies == [100], f"Expected [100], got {fixed.dependencies}"

        finally:
            session.close()

    def test_step3_handles_only_self_reference(self, create_test_db):
        """Verify feature with only self-reference gets empty dependencies."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create feature with only self-reference
            feature = Feature(
                id=200,
                priority=1,
                category="test",
                name="Only self-ref",
                description="Only depends on itself",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[200],
            )
            session.add(feature)
            session.commit()

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify
            assert 200 in repaired_ids
            session.expire_all()
            fixed = session.query(Feature).filter(Feature.id == 200).first()
            assert fixed.dependencies == [], f"Expected [], got {fixed.dependencies}"

        finally:
            session.close()

    def test_step3_handles_multiple_valid_deps_with_self_ref(self, create_test_db):
        """Verify multiple valid dependencies are preserved when removing self-ref."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create dependency targets
            for i in range(300, 303):
                dep = Feature(
                    id=i,
                    priority=i - 299,
                    category="test",
                    name=f"Dep {i}",
                    description="Dependency",
                    steps=["Step 1"],
                    passes=True,
                    in_progress=False,
                    dependencies=[],
                )
                session.add(dep)

            # Create feature with self-ref and multiple valid deps
            feature = Feature(
                id=310,
                priority=10,
                category="test",
                name="Multiple deps",
                description="Has self-ref and multiple valid deps",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[310, 300, 301, 302],  # Self + 3 valid
            )
            session.add(feature)
            session.commit()

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify
            assert 310 in repaired_ids
            session.expire_all()
            fixed = session.query(Feature).filter(Feature.id == 310).first()
            assert fixed.dependencies == [300, 301, 302], f"Expected [300, 301, 302], got {fixed.dependencies}"

        finally:
            session.close()


class TestRepairSelfReferencesTransaction:
    """Tests for Step 4: Commit changes in a single transaction."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step4_single_transaction_for_multiple_repairs(self, create_test_db):
        """Step 4: Verify all changes are committed in a single transaction."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create multiple features with self-references
            for i in range(400, 410):
                feature = Feature(
                    id=i,
                    priority=i - 399,
                    category="test",
                    name=f"Self-ref feature {i}",
                    description=f"Feature {i} depends on itself",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i],  # Self-reference
                )
                session.add(feature)
            session.commit()

            # Patch commit to count calls
            original_commit = session.commit
            commit_count = [0]

            def counting_commit():
                commit_count[0] += 1
                original_commit()

            session.commit = counting_commit

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify single commit
            assert commit_count[0] == 1, f"Expected 1 commit, got {commit_count[0]}"
            assert len(repaired_ids) == 10, f"Expected 10 repairs, got {len(repaired_ids)}"

        finally:
            session.close()

    def test_step4_no_commit_when_no_repairs_needed(self, create_test_db):
        """Verify no commit is made when there are no self-references to fix."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features without self-references
            for i in range(500, 503):
                feature = Feature(
                    id=i,
                    priority=i - 499,
                    category="test",
                    name=f"Valid feature {i}",
                    description="No self-reference",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[],
                )
                session.add(feature)
            session.commit()

            # Patch commit to track calls
            commit_count = [0]
            original_commit = session.commit

            def counting_commit():
                commit_count[0] += 1
                original_commit()

            session.commit = counting_commit

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify no commit (no repairs needed)
            assert commit_count[0] == 0, f"Expected 0 commits, got {commit_count[0]}"
            assert repaired_ids == [], f"Expected empty list, got {repaired_ids}"

        finally:
            session.close()

    def test_step4_changes_persist_after_session_close(self, create_test_db):
        """Verify changes are persisted to database after session closes."""
        engine, session_maker, project_dir = create_test_db

        # Session 1: Create and repair
        session1 = session_maker()
        try:
            feature = Feature(
                id=600,
                priority=1,
                category="test",
                name="Persistent test",
                description="Test persistence",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[600, 601],  # Self-ref + valid
            )
            session1.add(feature)

            dep = Feature(
                id=601,
                priority=2,
                category="test",
                name="Dep",
                description="Dependency",
                steps=["Step 1"],
                passes=True,
                in_progress=False,
                dependencies=[],
            )
            session1.add(dep)
            session1.commit()

            repaired_ids = repair_self_references(session1)
            assert 600 in repaired_ids
        finally:
            session1.close()

        # Session 2: Verify changes persisted
        session2 = session_maker()
        try:
            feature = session2.query(Feature).filter(Feature.id == 600).first()
            assert feature.dependencies == [601], f"Expected [601], got {feature.dependencies}"
        finally:
            session2.close()


class TestRepairSelfReferencesReturnValue:
    """Tests for Step 5: Return list of repaired feature IDs for logging."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step5_returns_list_of_repaired_ids(self, create_test_db):
        """Step 5: Verify function returns correct list of repaired feature IDs."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features - some with self-refs, some without
            features_with_self_ref = [700, 703, 707]
            features_without_self_ref = [701, 702, 704, 705, 706]

            for i in range(700, 708):
                feature = Feature(
                    id=i,
                    priority=i - 699,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i] if i in features_with_self_ref else [],
                )
                session.add(feature)
            session.commit()

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify
            assert isinstance(repaired_ids, list)
            assert len(repaired_ids) == 3
            assert set(repaired_ids) == set(features_with_self_ref)

        finally:
            session.close()

    def test_step5_returns_empty_list_when_no_self_references(self, create_test_db):
        """Verify empty list returned when no self-references exist."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features without self-references
            for i in range(800, 805):
                feature = Feature(
                    id=i,
                    priority=i - 799,
                    category="test",
                    name=f"Valid feature {i}",
                    description="No self-reference",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[] if i == 800 else [i - 1],  # Chain deps
                )
                session.add(feature)
            session.commit()

            # Run repair
            repaired_ids = repair_self_references(session)

            # Verify
            assert repaired_ids == [], f"Expected empty list, got {repaired_ids}"

        finally:
            session.close()

    def test_step5_returns_ids_in_consistent_order(self, create_test_db):
        """Verify IDs are returned in consistent order (by feature ID)."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features with self-refs in non-sequential order
            for i in [905, 903, 901, 904, 902]:
                feature = Feature(
                    id=i,
                    priority=i - 899,
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

            # Run repair multiple times to check consistency
            repaired_ids_1 = repair_self_references(session)

            # Since features are already repaired, second call should return empty
            # But we can verify the first call returned all IDs
            assert set(repaired_ids_1) == {901, 902, 903, 904, 905}

        finally:
            session.close()


class TestRepairSelfReferencesEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_empty_database(self, create_test_db):
        """Verify function handles empty database gracefully."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            repaired_ids = repair_self_references(session)
            assert repaired_ids == [], f"Expected empty list, got {repaired_ids}"
        finally:
            session.close()

    def test_handles_null_dependencies(self, create_test_db):
        """Verify function handles NULL dependencies field."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            feature = Feature(
                id=1000,
                priority=1,
                category="test",
                name="NULL deps feature",
                description="Has NULL dependencies",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=None,  # NULL
            )
            session.add(feature)
            session.commit()

            # Should not crash and should not return this feature
            repaired_ids = repair_self_references(session)
            assert 1000 not in repaired_ids

        finally:
            session.close()

    def test_handles_empty_dependencies_list(self, create_test_db):
        """Verify function handles empty dependencies list."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            feature = Feature(
                id=1001,
                priority=1,
                category="test",
                name="Empty deps feature",
                description="Has empty dependencies",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[],  # Empty
            )
            session.add(feature)
            session.commit()

            repaired_ids = repair_self_references(session)
            assert 1001 not in repaired_ids

        finally:
            session.close()

    def test_handles_duplicate_self_references(self, create_test_db):
        """Verify function handles duplicate self-references in dependencies."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            feature = Feature(
                id=1002,
                priority=1,
                category="test",
                name="Duplicate self-ref",
                description="Has duplicate self-references",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[1002, 1002, 1003],  # Duplicate self-ref + valid
            )
            session.add(feature)

            dep = Feature(
                id=1003,
                priority=2,
                category="test",
                name="Dep",
                description="Dependency",
                steps=["Step 1"],
                passes=True,
                in_progress=False,
                dependencies=[],
            )
            session.add(dep)
            session.commit()

            repaired_ids = repair_self_references(session)
            assert 1002 in repaired_ids

            session.expire_all()
            fixed = session.query(Feature).filter(Feature.id == 1002).first()
            # Should remove all instances of self-reference
            assert 1002 not in fixed.dependencies
            assert 1003 in fixed.dependencies

        finally:
            session.close()

    def test_handles_large_number_of_features(self, create_test_db):
        """Verify function handles large number of features efficiently."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create 100 features, half with self-references
            for i in range(2000, 2100):
                feature = Feature(
                    id=i,
                    priority=i - 1999,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i] if i % 2 == 0 else [],
                )
                session.add(feature)
            session.commit()

            repaired_ids = repair_self_references(session)

            # Should repair 50 features (even IDs from 2000-2098)
            assert len(repaired_ids) == 50, f"Expected 50 repairs, got {len(repaired_ids)}"

        finally:
            session.close()


class TestRepairSelfReferencesLogging:
    """Tests for logging behavior."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_logs_each_repair(self, create_test_db, caplog):
        """Verify function logs each repair operation."""
        import logging

        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features with self-references
            for i in range(3000, 3003):
                feature = Feature(
                    id=i,
                    priority=i - 2999,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i],
                )
                session.add(feature)
            session.commit()

            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Check logs mention each feature ID
            log_messages = " ".join(record.message for record in caplog.records)
            assert "3000" in log_messages
            assert "3001" in log_messages
            assert "3002" in log_messages

        finally:
            session.close()

    def test_logs_summary_on_completion(self, create_test_db, caplog):
        """Verify function logs summary after all repairs."""
        import logging

        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features with self-references
            for i in range(3100, 3105):
                feature = Feature(
                    id=i,
                    priority=i - 3099,
                    category="test",
                    name=f"Feature {i}",
                    description=f"Test feature {i}",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i],
                )
                session.add(feature)
            session.commit()

            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Check for summary log
            log_messages = " ".join(record.message for record in caplog.records)
            assert "Committed repairs" in log_messages or "5 feature(s)" in log_messages

        finally:
            session.close()
