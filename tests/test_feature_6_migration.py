#!/usr/bin/env python3
"""
Feature #6 Unit Tests
=====================

Comprehensive tests for Database Migration Preserves Existing Features.

Tests verify that the _migrate_add_agentspec_tables migration is:
1. Additive (creates new tables)
2. Non-destructive (existing features table unchanged)
3. Idempotent (can be run multiple times safely)
"""

import json
import pytest
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.database import (
    Base,
    Feature,
    _migrate_add_agentspec_tables,
)


@pytest.fixture
def temp_db_dir():
    """Create a temporary directory for test database."""
    test_dir = Path(tempfile.mkdtemp(prefix="feature6_pytest_"))
    yield test_dir
    try:
        shutil.rmtree(test_dir)
    except Exception:
        pass


@pytest.fixture
def test_engine(temp_db_dir):
    """Create a test database engine with features table only."""
    db_path = temp_db_dir / "test_features.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Create only the Feature table (simulating pre-migration state)
    Feature.__table__.create(bind=engine, checkfirst=True)

    yield engine
    engine.dispose()


@pytest.fixture
def session_maker(test_engine):
    """Create a session maker for the test database."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def populated_db(test_engine, session_maker):
    """Create a database with sample feature records."""
    session = session_maker()

    sample_features = []
    for i in range(1, 6):
        feature = Feature(
            priority=i * 10,
            category=f"Category_{i}",
            name=f"Test Feature {i}",
            description=f"Description for feature {i}",
            steps=[f"Step {j}" for j in range(1, 4)],
            passes=i % 2 == 0,
            in_progress=i == 3,
            dependencies=[1, 2] if i > 2 else None,
        )
        session.add(feature)
        sample_features.append(feature)

    session.commit()

    # Capture IDs and data
    feature_data = []
    for feature in sample_features:
        feature_data.append({
            "id": feature.id,
            "priority": feature.priority,
            "category": feature.category,
            "name": feature.name,
            "description": feature.description,
            "steps": feature.steps,
            "passes": feature.passes,
            "in_progress": feature.in_progress,
            "dependencies": feature.dependencies,
        })

    session.close()

    return test_engine, session_maker, feature_data


class TestMigrationCreatesNewTables:
    """Tests for Step 1 & 6: Migration creates new tables."""

    def test_migration_creates_agent_specs_table(self, test_engine):
        """Migration creates agent_specs table."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "agent_specs" in tables

    def test_migration_creates_acceptance_specs_table(self, test_engine):
        """Migration creates acceptance_specs table."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "acceptance_specs" in tables

    def test_migration_creates_agent_runs_table(self, test_engine):
        """Migration creates agent_runs table."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "agent_runs" in tables

    def test_migration_creates_artifacts_table(self, test_engine):
        """Migration creates artifacts table."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "artifacts" in tables

    def test_migration_creates_agent_events_table(self, test_engine):
        """Migration creates agent_events table."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "agent_events" in tables

    def test_migration_creates_all_expected_tables(self, test_engine):
        """Migration creates all 5 expected tables."""
        inspector = inspect(test_engine)
        original_tables = set(inspector.get_table_names())

        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        new_tables = set(inspector.get_table_names()) - original_tables

        expected_tables = {
            "agent_specs",
            "acceptance_specs",
            "agent_runs",
            "artifacts",
            "agent_events",
        }
        assert new_tables == expected_tables


class TestMigrationPreservesFeatures:
    """Tests for Step 3: Migration preserves existing feature records."""

    def test_migration_preserves_feature_count(self, populated_db):
        """Migration does not change the number of features."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        count = session.query(Feature).count()
        session.close()

        assert count == len(original_features)

    def test_migration_preserves_feature_ids(self, populated_db):
        """Migration preserves all feature IDs."""
        engine, SessionMaker, original_features = populated_db
        original_ids = {f["id"] for f in original_features}

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        db_ids = {f.id for f in session.query(Feature).all()}
        session.close()

        assert db_ids == original_ids

    def test_migration_preserves_feature_priority(self, populated_db):
        """Migration preserves feature priority values."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.priority == original["priority"]
        session.close()

    def test_migration_preserves_feature_category(self, populated_db):
        """Migration preserves feature category values."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.category == original["category"]
        session.close()

    def test_migration_preserves_feature_name(self, populated_db):
        """Migration preserves feature name values."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.name == original["name"]
        session.close()

    def test_migration_preserves_feature_description(self, populated_db):
        """Migration preserves feature description values."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.description == original["description"]
        session.close()

    def test_migration_preserves_feature_steps(self, populated_db):
        """Migration preserves feature steps (JSON array)."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.steps == original["steps"]
        session.close()

    def test_migration_preserves_feature_passes_flag(self, populated_db):
        """Migration preserves feature passes flag."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.passes == original["passes"]
        session.close()

    def test_migration_preserves_feature_in_progress_flag(self, populated_db):
        """Migration preserves feature in_progress flag."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature.in_progress == original["in_progress"]
        session.close()

    def test_migration_preserves_feature_dependencies(self, populated_db):
        """Migration preserves feature dependencies (JSON)."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            # Handle None/empty list comparison
            original_deps = original["dependencies"] or []
            current_deps = feature.dependencies or []
            assert current_deps == original_deps
        session.close()


class TestMigrationPreservesSchema:
    """Tests for Step 4: Migration does not modify features table schema."""

    def test_migration_preserves_column_count(self, test_engine):
        """Migration does not add or remove columns from features table."""
        inspector = inspect(test_engine)
        original_columns = len(inspector.get_columns("features"))

        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        new_columns = len(inspector.get_columns("features"))
        assert new_columns == original_columns

    def test_migration_preserves_column_names(self, test_engine):
        """Migration preserves all column names in features table."""
        inspector = inspect(test_engine)
        original_column_names = {col["name"] for col in inspector.get_columns("features")}

        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        new_column_names = {col["name"] for col in inspector.get_columns("features")}
        assert new_column_names == original_column_names

    def test_migration_preserves_index_count(self, test_engine):
        """Migration does not add or remove indexes from features table."""
        inspector = inspect(test_engine)
        original_indexes = len(inspector.get_indexes("features"))

        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        new_indexes = len(inspector.get_indexes("features"))
        assert new_indexes == original_indexes


class TestMigrationIdempotency:
    """Tests for Step 5: Migration is idempotent."""

    def test_migration_can_run_twice_without_error(self, test_engine):
        """Migration can be run twice without raising errors."""
        _migrate_add_agentspec_tables(test_engine)
        _migrate_add_agentspec_tables(test_engine)  # Should not raise

    def test_migration_can_run_three_times_without_error(self, test_engine):
        """Migration can be run three times without raising errors."""
        _migrate_add_agentspec_tables(test_engine)
        _migrate_add_agentspec_tables(test_engine)
        _migrate_add_agentspec_tables(test_engine)  # Should not raise

    def test_idempotent_migration_preserves_feature_data(self, populated_db):
        """Running migration twice preserves all feature data."""
        engine, SessionMaker, original_features = populated_db

        _migrate_add_agentspec_tables(engine)
        _migrate_add_agentspec_tables(engine)

        session = SessionMaker()
        for original in original_features:
            feature = session.get(Feature, original["id"])
            assert feature is not None
            assert feature.name == original["name"]
            assert feature.description == original["description"]
            assert feature.priority == original["priority"]
        session.close()

    def test_idempotent_migration_maintains_table_count(self, test_engine):
        """Running migration twice creates same number of tables."""
        _migrate_add_agentspec_tables(test_engine)
        inspector = inspect(test_engine)
        tables_after_first = len(inspector.get_table_names())

        _migrate_add_agentspec_tables(test_engine)
        inspector = inspect(test_engine)
        tables_after_second = len(inspector.get_table_names())

        assert tables_after_first == tables_after_second


class TestMigrationWithSpecialData:
    """Tests for edge cases with special data."""

    def test_migration_preserves_unicode_in_description(self, test_engine, session_maker):
        """Migration preserves Unicode characters in descriptions."""
        session = session_maker()
        feature = Feature(
            priority=1,
            category="Test",
            name="Unicode Test",
            description="Description with unicode: \u00fc\u00f6\u00e4 \u4e2d\u6587 \u65e5\u672c\u8a9e \U0001f600",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
        )
        session.add(feature)
        session.commit()
        feature_id = feature.id
        original_description = feature.description
        session.close()

        _migrate_add_agentspec_tables(test_engine)

        session = session_maker()
        feature = session.get(Feature, feature_id)
        assert feature.description == original_description
        session.close()

    def test_migration_preserves_special_chars_in_steps(self, test_engine, session_maker):
        """Migration preserves special characters in steps JSON."""
        session = session_maker()
        special_steps = ["Step with <html> & special chars", "Step with \"quotes\"", "Step with 'apostrophe'"]
        feature = Feature(
            priority=1,
            category="Test",
            name="Special Chars Test",
            description="Test",
            steps=special_steps,
            passes=False,
            in_progress=False,
        )
        session.add(feature)
        session.commit()
        feature_id = feature.id
        session.close()

        _migrate_add_agentspec_tables(test_engine)

        session = session_maker()
        feature = session.get(Feature, feature_id)
        assert feature.steps == special_steps
        session.close()

    def test_migration_preserves_null_dependencies(self, test_engine, session_maker):
        """Migration preserves NULL dependencies."""
        session = session_maker()
        feature = Feature(
            priority=1,
            category="Test",
            name="Null Dependencies Test",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=None,
        )
        session.add(feature)
        session.commit()
        feature_id = feature.id
        session.close()

        _migrate_add_agentspec_tables(test_engine)

        session = session_maker()
        feature = session.get(Feature, feature_id)
        assert feature.dependencies is None
        session.close()

    def test_migration_preserves_empty_list_dependencies(self, test_engine, session_maker):
        """Migration preserves empty list dependencies."""
        session = session_maker()
        feature = Feature(
            priority=1,
            category="Test",
            name="Empty Dependencies Test",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=[],
        )
        session.add(feature)
        session.commit()
        feature_id = feature.id
        session.close()

        _migrate_add_agentspec_tables(test_engine)

        session = session_maker()
        feature = session.get(Feature, feature_id)
        assert feature.dependencies == []
        session.close()

    def test_migration_preserves_long_description(self, test_engine, session_maker):
        """Migration preserves very long descriptions."""
        session = session_maker()
        long_description = "A" * 10000  # 10KB description
        feature = Feature(
            priority=1,
            category="Test",
            name="Long Description Test",
            description=long_description,
            steps=["Step 1"],
            passes=False,
            in_progress=False,
        )
        session.add(feature)
        session.commit()
        feature_id = feature.id
        session.close()

        _migrate_add_agentspec_tables(test_engine)

        session = session_maker()
        feature = session.get(Feature, feature_id)
        assert feature.description == long_description
        session.close()


class TestNewTablesHaveCorrectStructure:
    """Tests to verify new tables have the expected structure."""

    def test_agent_specs_table_has_id_column(self, test_engine):
        """agent_specs table has id primary key column."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_specs")}
        assert "id" in columns

    def test_agent_specs_table_has_name_column(self, test_engine):
        """agent_specs table has name column."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_specs")}
        assert "name" in columns

    def test_agent_specs_table_has_source_feature_id_column(self, test_engine):
        """agent_specs table has source_feature_id for linking to features."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_specs")}
        assert "source_feature_id" in columns

    def test_agent_runs_table_has_agent_spec_id_column(self, test_engine):
        """agent_runs table has agent_spec_id for linking to agent_specs."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_runs")}
        assert "agent_spec_id" in columns

    def test_artifacts_table_has_run_id_column(self, test_engine):
        """artifacts table has run_id for linking to agent_runs."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("artifacts")}
        assert "run_id" in columns

    def test_agent_events_table_has_run_id_column(self, test_engine):
        """agent_events table has run_id for linking to agent_runs."""
        _migrate_add_agentspec_tables(test_engine)

        inspector = inspect(test_engine)
        columns = {col["name"] for col in inspector.get_columns("agent_events")}
        assert "run_id" in columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
