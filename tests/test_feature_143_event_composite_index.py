"""
Tests for Feature #143: Add composite index on agent_events(run_id, event_type).

Verifies:
1. The AgentEvent model has the composite index in __table_args__
2. The existing index on (run_id, sequence) is preserved
3. The migration function creates the index on existing databases
4. The index is actually created in the database schema
"""
import pytest
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from api.agentspec_models import AgentEvent, Index
from api.database import (
    Base,
    create_database,
    _migrate_add_agent_event_run_event_type_index,
)


class TestModelDefinition:
    """Verify the AgentEvent model has the composite index defined."""

    def test_table_args_contains_run_event_type_index(self):
        """Step 2: __table_args__ includes Index on (run_id, event_type)."""
        table_args = AgentEvent.__table_args__
        found = False
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "ix_event_run_event_type":
                columns = [col.name for col in arg.columns]
                assert columns == ["run_id", "event_type"], (
                    f"Expected columns ['run_id', 'event_type'], got {columns}"
                )
                found = True
                break
        assert found, (
            "Index 'ix_event_run_event_type' not found in AgentEvent.__table_args__"
        )

    def test_existing_run_sequence_index_preserved(self):
        """Step 3: Existing index on (run_id, sequence) still exists."""
        table_args = AgentEvent.__table_args__
        found = False
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "ix_event_run_sequence":
                columns = [col.name for col in arg.columns]
                assert columns == ["run_id", "sequence"], (
                    f"Expected columns ['run_id', 'sequence'], got {columns}"
                )
                found = True
                break
        assert found, (
            "Index 'ix_event_run_sequence' not found - existing index was removed!"
        )


class TestDatabaseIndex:
    """Verify the index exists in the actual database schema."""

    def _create_fresh_db(self, tmp_path: Path):
        """Create a fresh in-memory database with all tables."""
        db_url = f"sqlite:///{tmp_path / 'test_feature_143.db'}"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        return engine

    def test_index_created_on_new_database(self, tmp_path):
        """Step 4: Verify the composite index is created in the database schema."""
        engine = self._create_fresh_db(tmp_path)
        inspector = inspect(engine)

        indexes = inspector.get_indexes("agent_events")
        index_names = {idx["name"] for idx in indexes}
        assert "ix_event_run_event_type" in index_names, (
            f"Composite index ix_event_run_event_type not found in schema. "
            f"Found indexes: {index_names}"
        )

        # Verify the columns
        for idx in indexes:
            if idx["name"] == "ix_event_run_event_type":
                assert idx["column_names"] == ["run_id", "event_type"], (
                    f"Expected columns ['run_id', 'event_type'], got {idx['column_names']}"
                )

    def test_existing_indexes_preserved_in_new_database(self, tmp_path):
        """Existing indexes on agent_events are all preserved."""
        engine = self._create_fresh_db(tmp_path)
        inspector = inspect(engine)

        indexes = inspector.get_indexes("agent_events")
        index_names = {idx["name"] for idx in indexes}

        # All expected indexes should exist
        expected = {
            "ix_event_run_sequence",
            "ix_event_run_event_type",
            "ix_event_timestamp",
            "ix_event_tool",
        }
        for name in expected:
            assert name in index_names, (
                f"Expected index '{name}' not found. Found: {index_names}"
            )


class TestMigration:
    """Verify the migration function works for existing databases."""

    def test_migration_creates_index_on_existing_db(self, tmp_path):
        """Migration adds composite index to existing database without it."""
        db_url = f"sqlite:///{tmp_path / 'test_migration_143.db'}"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})

        # Create agent_events table without the new composite index
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id VARCHAR(36) NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload JSON,
                    payload_truncated INTEGER,
                    artifact_ref VARCHAR(36),
                    tool_name VARCHAR(100)
                )
            """))
            conn.execute(text(
                "CREATE INDEX ix_event_run_sequence ON agent_events (run_id, sequence)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_event_timestamp ON agent_events (timestamp)"
            ))
            conn.execute(text(
                "CREATE INDEX ix_event_tool ON agent_events (tool_name)"
            ))
            conn.commit()

        # Verify no composite index on (run_id, event_type) yet
        inspector = inspect(engine)
        indexes_before = inspector.get_indexes("agent_events")
        before_names = {idx["name"] for idx in indexes_before}
        assert "ix_event_run_event_type" not in before_names, "Index already exists before migration"

        # Run the migration
        _migrate_add_agent_event_run_event_type_index(engine)

        # Verify the composite index was created
        # Need to get a fresh inspector
        inspector = inspect(engine)
        indexes_after = inspector.get_indexes("agent_events")
        after_names = {idx["name"] for idx in indexes_after}
        assert "ix_event_run_event_type" in after_names, (
            f"Migration did not create ix_event_run_event_type. Found: {after_names}"
        )

        # Verify existing indexes are preserved
        assert "ix_event_run_sequence" in after_names, "Migration removed ix_event_run_sequence!"
        assert "ix_event_timestamp" in after_names, "Migration removed ix_event_timestamp!"
        assert "ix_event_tool" in after_names, "Migration removed ix_event_tool!"

    def test_migration_is_idempotent(self, tmp_path):
        """Running migration twice does not fail."""
        db_url = f"sqlite:///{tmp_path / 'test_idempotent_143.db'}"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})

        # Create table with the index already present
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id VARCHAR(36) NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    timestamp DATETIME NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload JSON,
                    payload_truncated INTEGER,
                    artifact_ref VARCHAR(36),
                    tool_name VARCHAR(100)
                )
            """))
            conn.execute(text(
                "CREATE INDEX ix_event_run_event_type ON agent_events (run_id, event_type)"
            ))
            conn.commit()

        # Running migration again should not fail
        _migrate_add_agent_event_run_event_type_index(engine)

        # Verify index still exists
        inspector = inspect(engine)
        indexes = inspector.get_indexes("agent_events")
        names = {idx["name"] for idx in indexes}
        assert "ix_event_run_event_type" in names

    def test_migration_skips_if_no_table(self, tmp_path):
        """Migration is a no-op if agent_events table doesn't exist."""
        db_url = f"sqlite:///{tmp_path / 'test_no_table_143.db'}"
        engine = create_engine(db_url, connect_args={"check_same_thread": False})

        # No tables at all - should not raise
        _migrate_add_agent_event_run_event_type_index(engine)


class TestCreateDatabaseIntegration:
    """Verify create_database() includes the migration."""

    def test_create_database_creates_composite_index(self, tmp_path):
        """create_database() produces agent_events table with the composite index."""
        engine, SessionLocal = create_database(tmp_path)

        inspector = inspect(engine)
        indexes = inspector.get_indexes("agent_events")
        index_map = {idx["name"]: idx["column_names"] for idx in indexes}

        # Composite index on (run_id, event_type) exists
        assert "ix_event_run_event_type" in index_map, (
            f"ix_event_run_event_type not found after create_database(). Found: {list(index_map.keys())}"
        )
        assert index_map["ix_event_run_event_type"] == ["run_id", "event_type"]

        # Existing index on (run_id, sequence) is preserved
        assert "ix_event_run_sequence" in index_map, (
            f"ix_event_run_sequence not found - existing index was removed!"
        )
        assert index_map["ix_event_run_sequence"] == ["run_id", "sequence"]
