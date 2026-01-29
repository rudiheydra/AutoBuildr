"""
Tests for Feature #142: Add composite index on agent_runs(agent_spec_id, status).

Verifies:
1. The AgentRun model declares a composite Index on (agent_spec_id, status)
2. The separate single-column indexes on agent_spec_id and status are preserved
3. The composite index is actually created in the database schema
4. The migration function creates the index for existing databases (idempotent)
"""
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from api.database import Base, create_database, _migrate_add_agentrun_spec_status_index
from api.agentspec_models import AgentRun, AgentSpec, Index


# =============================================================================
# Test 1: Model definition has composite index in __table_args__
# =============================================================================

class TestModelDefinition:
    """Verify AgentRun model declares the composite index."""

    def test_composite_index_in_table_args(self):
        """AgentRun.__table_args__ should contain an Index on (agent_spec_id, status)."""
        table_args = AgentRun.__table_args__
        composite_found = False
        for arg in table_args:
            if isinstance(arg, Index):
                col_names = [col.name for col in arg.columns]
                if col_names == ["agent_spec_id", "status"]:
                    composite_found = True
                    assert arg.name == "ix_agentrun_spec_status"
                    break
        assert composite_found, (
            "AgentRun.__table_args__ must contain an Index on (agent_spec_id, status). "
            f"Found indexes: {[(type(a).__name__, getattr(a, 'name', None)) for a in table_args if isinstance(a, Index)]}"
        )

    def test_single_column_indexes_preserved(self):
        """The existing separate single-column indexes must still be present."""
        table_args = AgentRun.__table_args__
        index_names = set()
        for arg in table_args:
            if isinstance(arg, Index):
                index_names.add(arg.name)

        assert "ix_agentrun_spec" in index_names, "Single-column index ix_agentrun_spec must be preserved"
        assert "ix_agentrun_status" in index_names, "Single-column index ix_agentrun_status must be preserved"
        assert "ix_agentrun_created" in index_names, "Single-column index ix_agentrun_created must be preserved"

    def test_composite_index_column_order(self):
        """Composite index must have agent_spec_id first, then status."""
        table_args = AgentRun.__table_args__
        for arg in table_args:
            if isinstance(arg, Index) and arg.name == "ix_agentrun_spec_status":
                col_names = [col.name for col in arg.columns]
                assert col_names == ["agent_spec_id", "status"], (
                    f"Composite index columns must be ['agent_spec_id', 'status'], got {col_names}"
                )
                return
        pytest.fail("Composite index ix_agentrun_spec_status not found")


# =============================================================================
# Test 2: Database schema has the composite index
# =============================================================================

class TestDatabaseSchema:
    """Verify the composite index exists in the actual database."""

    @pytest.fixture
    def db_engine(self, tmp_path):
        """Create a fresh database with all migrations applied."""
        engine, _ = create_database(tmp_path)
        yield engine
        engine.dispose()

    def test_composite_index_created_in_db(self, db_engine):
        """The ix_agentrun_spec_status index should exist in the agent_runs table."""
        inspector = inspect(db_engine)
        indexes = inspector.get_indexes("agent_runs")
        index_map = {idx["name"]: idx for idx in indexes}

        assert "ix_agentrun_spec_status" in index_map, (
            f"Composite index ix_agentrun_spec_status not found in database. "
            f"Existing indexes: {list(index_map.keys())}"
        )

        idx = index_map["ix_agentrun_spec_status"]
        assert idx["column_names"] == ["agent_spec_id", "status"], (
            f"Index columns wrong: expected ['agent_spec_id', 'status'], got {idx['column_names']}"
        )

    def test_single_column_indexes_in_db(self, db_engine):
        """The separate single-column indexes must also exist in the database."""
        inspector = inspect(db_engine)
        indexes = inspector.get_indexes("agent_runs")
        index_names = {idx["name"] for idx in indexes}

        assert "ix_agentrun_spec" in index_names, "Single-column index ix_agentrun_spec missing from DB"
        assert "ix_agentrun_status" in index_names, "Single-column index ix_agentrun_status missing from DB"
        assert "ix_agentrun_created" in index_names, "Single-column index ix_agentrun_created missing from DB"

    def test_composite_index_used_by_query(self, db_engine):
        """Verify SQLite can use the composite index for a spec+status query."""
        with db_engine.connect() as conn:
            # Use EXPLAIN QUERY PLAN to check the query optimizer considers the index
            result = conn.execute(text(
                "EXPLAIN QUERY PLAN SELECT * FROM agent_runs "
                "WHERE agent_spec_id = 'test-id' AND status = 'running'"
            ))
            plan = " ".join(str(row) for row in result.fetchall())
            # SQLite should reference an index (either composite or single-column)
            assert "USING INDEX" in plan.upper() or "SEARCH" in plan.upper(), (
                f"Query plan does not show index usage: {plan}"
            )


# =============================================================================
# Test 3: Migration is idempotent
# =============================================================================

class TestMigration:
    """Verify the migration function works correctly."""

    def test_migration_creates_index(self, tmp_path):
        """Migration should create the composite index on existing databases."""
        # First create database (this will run all migrations including the new one)
        engine, _ = create_database(tmp_path)

        # Verify index exists
        inspector = inspect(engine)
        indexes = inspector.get_indexes("agent_runs")
        index_names = {idx["name"] for idx in indexes}
        assert "ix_agentrun_spec_status" in index_names

        engine.dispose()

    def test_migration_is_idempotent(self, tmp_path):
        """Running migration twice should not fail or create duplicates."""
        engine, _ = create_database(tmp_path)

        # Run migration again explicitly - should be a no-op
        _migrate_add_agentrun_spec_status_index(engine)

        # Verify still exactly one composite index
        inspector = inspect(engine)
        indexes = inspector.get_indexes("agent_runs")
        composite_count = sum(
            1 for idx in indexes
            if idx.get("column_names") == ["agent_spec_id", "status"]
        )
        assert composite_count == 1, (
            f"Expected exactly 1 composite index, found {composite_count}"
        )

        engine.dispose()

    def test_migration_skips_when_table_missing(self, tmp_path):
        """Migration should skip gracefully if agent_runs table doesn't exist."""
        # Create engine with only features table
        db_url = f"sqlite:///{tmp_path / 'test.db'}"
        engine = create_engine(db_url)
        Base.metadata.tables["features"].create(bind=engine, checkfirst=True)

        # Should not raise
        _migrate_add_agentrun_spec_status_index(engine)

        engine.dispose()
