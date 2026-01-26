"""
Tests for repair_orphaned_dependencies() function.

This test suite verifies that repair_orphaned_dependencies() function:
1. Creates repair_orphaned_dependencies(session) function
2. Gets set of all valid feature IDs
3. For each feature, filters dependencies to only valid IDs
4. Updates features with orphaned refs in single transaction
5. Returns dict of {feature_id: [removed_orphan_ids]} for logging

Feature #100: Auto-repair function removes orphaned dependency references
"""

import inspect
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base, Feature
from api.dependency_resolver import repair_orphaned_dependencies


class TestFunctionExistsAndSignature:
    """Tests for the repair_orphaned_dependencies function existence and signature."""

    def test_function_exists(self):
        """Step 1: Verify repair_orphaned_dependencies function exists."""
        from api.dependency_resolver import repair_orphaned_dependencies

        assert repair_orphaned_dependencies is not None, "Function should exist"

    def test_function_is_callable(self):
        """Step 1: Verify repair_orphaned_dependencies is callable."""
        from api.dependency_resolver import repair_orphaned_dependencies

        assert callable(repair_orphaned_dependencies), "Function should be callable"

    def test_function_signature(self):
        """Step 1: Verify function takes session parameter."""
        sig = inspect.signature(repair_orphaned_dependencies)
        params = list(sig.parameters.keys())

        assert len(params) == 1, "Function should have 1 parameter"
        assert params[0] == "session", "Parameter should be named 'session'"

    def test_returns_dict(self):
        """Step 5: Verify function returns a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                result = repair_orphaned_dependencies(session)
                assert isinstance(result, dict), "Function should return a dict"
            finally:
                session.close()


class TestGetValidFeatureIds:
    """Tests for Step 2: Get set of all valid feature IDs."""

    def test_identifies_valid_ids(self):
        """Step 2: Verify function correctly builds set of valid feature IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create features with known IDs
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999])  # 999 doesn't exist
                f2 = Feature(id=2, priority=2, category="A", name="F2",
                            description="D2", steps=["s2"], dependencies=[1])  # 1 exists

                session.add_all([f1, f2])
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # Feature 1 should have orphan 999 removed
                assert 1 in repairs, "Feature 1 should be in repairs"
                assert repairs[1] == [999], "Feature 1 should have orphan 999 removed"

                # Feature 2 should NOT be in repairs (dep 1 is valid)
                assert 2 not in repairs, "Feature 2 should not be in repairs (valid dep)"

            finally:
                session.close()


class TestFiltersToValidDependencies:
    """Tests for Step 3: Filter dependencies to only valid IDs."""

    def test_removes_single_orphan(self):
        """Step 3: Verify single orphan dependency is removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999])

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # Verify repair happened
                assert 1 in repairs
                assert repairs[1] == [999]

                # Verify database was updated
                session.refresh(f1)
                assert f1.dependencies == [], "Orphan should be removed"

            finally:
                session.close()

    def test_removes_multiple_orphans(self):
        """Step 3: Verify multiple orphan dependencies are removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999, 888, 777])

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # Verify all orphans removed
                assert 1 in repairs
                assert set(repairs[1]) == {999, 888, 777}

                # Verify database was updated
                session.refresh(f1)
                assert f1.dependencies == [], "All orphans should be removed"

            finally:
                session.close()

    def test_preserves_valid_dependencies(self):
        """Step 3: Verify valid dependencies are preserved while orphans removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create valid target features
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=None)
                f2 = Feature(id=2, priority=2, category="A", name="F2",
                            description="D2", steps=["s2"], dependencies=None)

                # Feature 3 has mix of valid (1, 2) and orphan (999, 888)
                f3 = Feature(id=3, priority=3, category="A", name="F3",
                            description="D3", steps=["s3"], dependencies=[1, 999, 2, 888])

                session.add_all([f1, f2, f3])
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # Only feature 3 should be repaired
                assert 1 not in repairs
                assert 2 not in repairs
                assert 3 in repairs
                assert set(repairs[3]) == {999, 888}

                # Verify database: valid deps preserved
                session.refresh(f3)
                assert set(f3.dependencies) == {1, 2}, "Valid deps should be preserved"

            finally:
                session.close()


class TestSingleTransactionCommit:
    """Tests for Step 4: Updates in single transaction."""

    def test_commits_all_changes_together(self):
        """Step 4: Verify all changes committed in single transaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create multiple features with orphans
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999])
                f2 = Feature(id=2, priority=2, category="A", name="F2",
                            description="D2", steps=["s2"], dependencies=[888])
                f3 = Feature(id=3, priority=3, category="A", name="F3",
                            description="D3", steps=["s3"], dependencies=[777])

                session.add_all([f1, f2, f3])
                session.commit()

                # Repair all
                repairs = repair_orphaned_dependencies(session)

                # All three should be repaired
                assert len(repairs) == 3

                # Open new session to verify persistence
                session2 = SessionLocal()
                try:
                    features = session2.query(Feature).all()
                    for f in features:
                        assert f.dependencies == [], f"Feature {f.id} should have empty deps"
                finally:
                    session2.close()

            finally:
                session.close()

    def test_no_commit_when_no_orphans(self):
        """Step 4: Verify no commit happens when no orphans found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create features with only valid dependencies
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=None)
                f2 = Feature(id=2, priority=2, category="A", name="F2",
                            description="D2", steps=["s2"], dependencies=[1])  # valid

                session.add_all([f1, f2])
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # No repairs needed
                assert repairs == {}, "Should return empty dict when no orphans"

            finally:
                session.close()


class TestReturnDictFormat:
    """Tests for Step 5: Return dict of {feature_id: [removed_orphan_ids]}."""

    def test_returns_feature_id_to_orphans_mapping(self):
        """Step 5: Verify return value maps feature_id to list of removed orphans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=10, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999, 888])
                f2 = Feature(id=20, priority=2, category="A", name="F2",
                            description="D2", steps=["s2"], dependencies=[777])

                session.add_all([f1, f2])
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # Check dict structure
                assert 10 in repairs
                assert 20 in repairs
                assert isinstance(repairs[10], list)
                assert isinstance(repairs[20], list)
                assert set(repairs[10]) == {999, 888}
                assert repairs[20] == [777]

            finally:
                session.close()

    def test_returns_empty_dict_when_no_orphans(self):
        """Step 5: Verify returns empty dict when no orphans found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=None)

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                assert repairs == {}, "Should return empty dict"

            finally:
                session.close()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_database(self):
        """Verify function handles empty database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                repairs = repair_orphaned_dependencies(session)
                assert repairs == {}, "Should return empty dict for empty database"
            finally:
                session.close()

    def test_null_dependencies(self):
        """Verify function handles NULL dependencies correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=None)

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                assert 1 not in repairs, "NULL deps should not be repaired"

            finally:
                session.close()

    def test_empty_dependencies_list(self):
        """Verify function handles empty dependencies list correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[])

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                assert 1 not in repairs, "Empty list should not be repaired"

            finally:
                session.close()

    def test_only_valid_dependencies(self):
        """Verify function doesn't modify features with only valid deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=None)
                f2 = Feature(id=2, priority=2, category="A", name="F2",
                            description="D2", steps=["s2"], dependencies=None)
                f3 = Feature(id=3, priority=3, category="A", name="F3",
                            description="D3", steps=["s3"], dependencies=[1, 2])

                session.add_all([f1, f2, f3])
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                assert repairs == {}, "No orphans should mean no repairs"

                session.refresh(f3)
                assert f3.dependencies == [1, 2], "Valid deps should be unchanged"

            finally:
                session.close()

    def test_large_number_of_orphans(self):
        """Verify function handles many orphan dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Many orphan IDs (none exist)
                orphan_ids = list(range(1000, 1020))
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=orphan_ids)

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                assert 1 in repairs
                assert set(repairs[1]) == set(orphan_ids)

                session.refresh(f1)
                assert f1.dependencies == [], "All orphans should be removed"

            finally:
                session.close()

    def test_many_features_with_orphans(self):
        """Verify function handles many features with orphans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                # Create 50 features each with orphan deps
                features = []
                for i in range(1, 51):
                    f = Feature(id=i, priority=i, category="A", name=f"F{i}",
                               description=f"D{i}", steps=[f"s{i}"],
                               dependencies=[1000 + i])  # All orphans
                    features.append(f)

                session.add_all(features)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                assert len(repairs) == 50, "All 50 features should be repaired"

                # Verify all were cleaned
                for i in range(1, 51):
                    assert i in repairs
                    assert repairs[i] == [1000 + i]

            finally:
                session.close()

    def test_idempotent(self):
        """Verify running repair twice has same result (idempotent)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999])

                session.add(f1)
                session.commit()

                # First repair
                repairs1 = repair_orphaned_dependencies(session)
                assert len(repairs1) == 1

                # Second repair should find nothing
                repairs2 = repair_orphaned_dependencies(session)
                assert repairs2 == {}, "Second run should find no orphans"

            finally:
                session.close()


class TestLogging:
    """Tests for logging behavior."""

    def test_logs_info_on_repair(self, caplog):
        """Verify INFO log is emitted when repair occurs."""
        import logging
        caplog.set_level(logging.INFO)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=[999])

                session.add(f1)
                session.commit()

                repairs = repair_orphaned_dependencies(session)

                # Check for log message (matches updated structured logging format)
                assert any("repair_orphaned_dependencies" in r.message for r in caplog.records)
                # Check for before/after fix logs or orphaned dependencies message
                assert any("orphaned dependencies" in r.message or "action=before_fix" in r.message
                          for r in caplog.records)

            finally:
                session.close()

    def test_no_log_when_no_orphans(self, caplog):
        """Verify no INFO log when no repairs needed."""
        import logging
        caplog.set_level(logging.INFO)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.create_all(bind=engine)
            SessionLocal = sessionmaker(bind=engine)

            session = SessionLocal()
            try:
                f1 = Feature(id=1, priority=1, category="A", name="F1",
                            description="D1", steps=["s1"], dependencies=None)

                session.add(f1)
                session.commit()

                caplog.clear()
                repairs = repair_orphaned_dependencies(session)

                # Should not have "Committed repairs" log
                assert not any("Committed repairs" in r.message for r in caplog.records)

            finally:
                session.close()
