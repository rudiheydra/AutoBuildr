"""
Tests for Feature #147: Make artifacts.content_hash and size_bytes NOT NULL
==========================================================================

Verifies that content_hash and size_bytes columns are NOT NULL in the Artifact
model, Pydantic schemas mark them as required, and the CRUD layer always provides
values. Also tests the database migration for existing NULL rows.
"""

import hashlib
import uuid

import pytest
from sqlalchemy import Column, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from api.agentspec_models import (
    AgentRun,
    AgentSpec,
    Artifact,
    create_tool_policy,
    generate_uuid,
)
from api.database import Base, _migrate_artifact_not_null_content_hash_size


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_engine(tmp_path):
    """Create a fresh in-memory database with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    # Also create agentspec tables
    from api.agentspec_models import AcceptanceSpec, AgentEvent
    from api.database import Feature
    # Create all tables
    AgentSpec.__table__.create(bind=engine, checkfirst=True)
    AcceptanceSpec.__table__.create(bind=engine, checkfirst=True)
    AgentRun.__table__.create(bind=engine, checkfirst=True)
    Artifact.__table__.create(bind=engine, checkfirst=True)
    AgentEvent.__table__.create(bind=engine, checkfirst=True)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session."""
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_spec(db_session):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id=generate_uuid(),
        name=f"test-spec-{uuid.uuid4().hex[:8]}",
        display_name="Test Spec",
        objective="Test objective",
        task_type="coding",
        tool_policy=create_tool_policy(["read_file"]),
        max_turns=10,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.flush()
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_spec.id,
        status="running",
    )
    db_session.add(run)
    db_session.flush()
    return run


# =============================================================================
# Step 1 & 2: Model Definition Tests - content_hash and size_bytes NOT NULL
# =============================================================================


class TestModelDefinition:
    """Verify SQLAlchemy model has nullable=False for content_hash and size_bytes."""

    def test_content_hash_not_nullable(self):
        """content_hash column should have nullable=False."""
        col = Artifact.__table__.columns["content_hash"]
        assert col.nullable is False, (
            f"content_hash column should be nullable=False, got nullable={col.nullable}"
        )

    def test_size_bytes_not_nullable(self):
        """size_bytes column should have nullable=False."""
        col = Artifact.__table__.columns["size_bytes"]
        assert col.nullable is False, (
            f"size_bytes column should be nullable=False, got nullable={col.nullable}"
        )

    def test_content_hash_is_string_64(self):
        """content_hash column should be String(64) for SHA256."""
        col = Artifact.__table__.columns["content_hash"]
        assert isinstance(col.type, type(Column("x", type_=col.type).type))
        # Check it's a string type
        assert hasattr(col.type, "length")
        assert col.type.length == 64

    def test_size_bytes_is_integer(self):
        """size_bytes column should be Integer."""
        col = Artifact.__table__.columns["size_bytes"]
        from sqlalchemy import Integer
        assert isinstance(col.type, Integer)


# =============================================================================
# Step 3: Database Enforcement Tests
# =============================================================================


class TestDatabaseEnforcement:
    """Verify database rejects NULL content_hash and size_bytes."""

    def test_artifact_with_both_fields_succeeds(self, db_session, sample_run):
        """Creating an artifact with both fields set should succeed."""
        content = b"test content"
        content_hash = hashlib.sha256(content).hexdigest()

        artifact = Artifact(
            id=generate_uuid(),
            run_id=sample_run.id,
            artifact_type="log",
            content_hash=content_hash,
            size_bytes=len(content),
        )
        db_session.add(artifact)
        db_session.flush()

        assert artifact.content_hash == content_hash
        assert artifact.size_bytes == len(content)

    def test_artifact_without_content_hash_rejected(self, db_session, sample_run):
        """Creating an artifact without content_hash should raise IntegrityError."""
        artifact = Artifact(
            id=generate_uuid(),
            run_id=sample_run.id,
            artifact_type="log",
            content_hash=None,  # Explicitly NULL
            size_bytes=100,
        )
        db_session.add(artifact)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_artifact_without_size_bytes_rejected(self, db_session, sample_run):
        """Creating an artifact without size_bytes should raise IntegrityError."""
        artifact = Artifact(
            id=generate_uuid(),
            run_id=sample_run.id,
            artifact_type="log",
            content_hash="a" * 64,
            size_bytes=None,  # Explicitly NULL
        )
        db_session.add(artifact)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


# =============================================================================
# Step 4: Pydantic Schema Tests
# =============================================================================


class TestPydanticSchemas:
    """Verify Pydantic schemas mark content_hash and size_bytes as required."""

    def test_artifact_list_item_response_content_hash_required(self):
        """ArtifactListItemResponse should require content_hash."""
        from server.schemas.agentspec import ArtifactListItemResponse
        schema = ArtifactListItemResponse.model_json_schema()
        required = schema.get("required", [])
        assert "content_hash" in required, (
            f"content_hash should be in required fields, got: {required}"
        )

    def test_artifact_list_item_response_size_bytes_required(self):
        """ArtifactListItemResponse should require size_bytes."""
        from server.schemas.agentspec import ArtifactListItemResponse
        schema = ArtifactListItemResponse.model_json_schema()
        required = schema.get("required", [])
        assert "size_bytes" in required, (
            f"size_bytes should be in required fields, got: {required}"
        )

    def test_artifact_response_content_hash_required(self):
        """ArtifactResponse should require content_hash."""
        from server.schemas.agentspec import ArtifactResponse
        schema = ArtifactResponse.model_json_schema()
        required = schema.get("required", [])
        assert "content_hash" in required, (
            f"content_hash should be in required fields, got: {required}"
        )

    def test_artifact_response_size_bytes_required(self):
        """ArtifactResponse should require size_bytes."""
        from server.schemas.agentspec import ArtifactResponse
        schema = ArtifactResponse.model_json_schema()
        required = schema.get("required", [])
        assert "size_bytes" in required, (
            f"size_bytes should be in required fields, got: {required}"
        )

    def test_artifact_list_item_content_hash_not_nullable_in_schema(self):
        """content_hash in ArtifactListItemResponse should not accept None."""
        from pydantic import ValidationError
        from server.schemas.agentspec import ArtifactListItemResponse
        from datetime import datetime, timezone

        with pytest.raises(ValidationError):
            ArtifactListItemResponse(
                id="test-id",
                run_id="test-run-id",
                artifact_type="log",
                content_hash=None,  # Should fail
                size_bytes=100,
                created_at=datetime.now(timezone.utc),
            )

    def test_artifact_list_item_size_bytes_not_nullable_in_schema(self):
        """size_bytes in ArtifactListItemResponse should not accept None."""
        from pydantic import ValidationError
        from server.schemas.agentspec import ArtifactListItemResponse
        from datetime import datetime, timezone

        with pytest.raises(ValidationError):
            ArtifactListItemResponse(
                id="test-id",
                run_id="test-run-id",
                artifact_type="log",
                content_hash="a" * 64,
                size_bytes=None,  # Should fail
                created_at=datetime.now(timezone.utc),
            )


# =============================================================================
# Step 5: CRUD Layer Tests
# =============================================================================


class TestCRUDLayer:
    """Verify CRUD layer always provides content_hash and size_bytes."""

    def test_create_artifact_sets_content_hash(self, db_session, sample_run, tmp_path):
        """create_artifact() always sets content_hash."""
        from api.agentspec_crud import create_artifact

        artifact = create_artifact(
            db_session,
            run_id=sample_run.id,
            artifact_type="log",
            content="Hello, world!",
            project_dir=tmp_path,
        )

        assert artifact.content_hash is not None
        assert len(artifact.content_hash) == 64
        expected_hash = hashlib.sha256(b"Hello, world!").hexdigest()
        assert artifact.content_hash == expected_hash

    def test_create_artifact_sets_size_bytes(self, db_session, sample_run, tmp_path):
        """create_artifact() always sets size_bytes."""
        from api.agentspec_crud import create_artifact

        content = "Hello, world!"
        artifact = create_artifact(
            db_session,
            run_id=sample_run.id,
            artifact_type="log",
            content=content,
            project_dir=tmp_path,
        )

        assert artifact.size_bytes is not None
        assert artifact.size_bytes == len(content.encode("utf-8"))

    def test_create_artifact_persists_to_db(self, db_session, sample_run, tmp_path):
        """Verify artifact with content_hash and size_bytes persists to DB."""
        from api.agentspec_crud import create_artifact

        artifact = create_artifact(
            db_session,
            run_id=sample_run.id,
            artifact_type="test_result",
            content="Test output: PASSED",
            project_dir=tmp_path,
        )
        db_session.commit()

        # Re-query from DB
        queried = db_session.query(Artifact).filter(Artifact.id == artifact.id).first()
        assert queried is not None
        assert queried.content_hash is not None
        assert queried.size_bytes is not None
        assert len(queried.content_hash) == 64
        assert queried.size_bytes > 0


# =============================================================================
# Step 6: Migration Tests
# =============================================================================


class TestMigration:
    """Verify migration handles existing NULL values."""

    def test_migration_fixes_null_content_hash(self, tmp_path):
        """Migration should set default content_hash for NULL rows."""
        # Create a DB with the old schema (nullable content_hash)
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            # Create a minimal artifacts table with nullable columns (old schema)
            conn.execute(text("""
                CREATE TABLE artifacts (
                    id VARCHAR(36) PRIMARY KEY,
                    run_id VARCHAR(36) NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    path VARCHAR(500),
                    content_ref VARCHAR(255),
                    content_inline TEXT,
                    content_hash VARCHAR(64),
                    size_bytes INTEGER,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    artifact_metadata TEXT
                )
            """))
            # Insert a row with NULL content_hash
            conn.execute(text("""
                INSERT INTO artifacts (id, run_id, artifact_type, content_hash, size_bytes, created_at)
                VALUES ('test-id', 'test-run', 'log', NULL, 100, CURRENT_TIMESTAMP)
            """))
            conn.commit()

        # Run migration
        _migrate_artifact_not_null_content_hash_size(engine)

        # Verify NULL was fixed
        with engine.connect() as conn:
            result = conn.execute(text("SELECT content_hash FROM artifacts WHERE id='test-id'"))
            row = result.fetchone()
            assert row[0] is not None
            # Should be the SHA256 of empty string
            assert row[0] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_migration_fixes_null_size_bytes(self, tmp_path):
        """Migration should set default size_bytes for NULL rows."""
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE artifacts (
                    id VARCHAR(36) PRIMARY KEY,
                    run_id VARCHAR(36) NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    path VARCHAR(500),
                    content_ref VARCHAR(255),
                    content_inline TEXT,
                    content_hash VARCHAR(64),
                    size_bytes INTEGER,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    artifact_metadata TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO artifacts (id, run_id, artifact_type, content_hash, size_bytes, created_at)
                VALUES ('test-id', 'test-run', 'log', 'abc123', NULL, CURRENT_TIMESTAMP)
            """))
            conn.commit()

        _migrate_artifact_not_null_content_hash_size(engine)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT size_bytes FROM artifacts WHERE id='test-id'"))
            row = result.fetchone()
            assert row[0] is not None
            assert row[0] == 0

    def test_migration_preserves_existing_values(self, tmp_path):
        """Migration should not overwrite existing non-NULL values."""
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE artifacts (
                    id VARCHAR(36) PRIMARY KEY,
                    run_id VARCHAR(36) NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    path VARCHAR(500),
                    content_ref VARCHAR(255),
                    content_inline TEXT,
                    content_hash VARCHAR(64),
                    size_bytes INTEGER,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    artifact_metadata TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO artifacts (id, run_id, artifact_type, content_hash, size_bytes, created_at)
                VALUES ('test-id', 'test-run', 'log', 'existing_hash_value_padded_to_64_chars_with_zeros_0000000000000', 42, CURRENT_TIMESTAMP)
            """))
            conn.commit()

        _migrate_artifact_not_null_content_hash_size(engine)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT content_hash, size_bytes FROM artifacts WHERE id='test-id'"))
            row = result.fetchone()
            assert row[0] == "existing_hash_value_padded_to_64_chars_with_zeros_0000000000000"
            assert row[1] == 42

    def test_migration_idempotent(self, tmp_path):
        """Migration should be safe to run multiple times."""
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE artifacts (
                    id VARCHAR(36) PRIMARY KEY,
                    run_id VARCHAR(36) NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    path VARCHAR(500),
                    content_ref VARCHAR(255),
                    content_inline TEXT,
                    content_hash VARCHAR(64),
                    size_bytes INTEGER,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    artifact_metadata TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO artifacts (id, run_id, artifact_type, content_hash, size_bytes, created_at)
                VALUES ('test-id', 'test-run', 'log', NULL, NULL, CURRENT_TIMESTAMP)
            """))
            conn.commit()

        # Run migration twice
        _migrate_artifact_not_null_content_hash_size(engine)
        _migrate_artifact_not_null_content_hash_size(engine)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT content_hash, size_bytes FROM artifacts WHERE id='test-id'"))
            row = result.fetchone()
            assert row[0] is not None
            assert row[1] is not None

    def test_migration_skips_when_no_artifacts_table(self):
        """Migration should skip gracefully when artifacts table doesn't exist."""
        engine = create_engine("sqlite:///:memory:")
        # Don't create any tables
        _migrate_artifact_not_null_content_hash_size(engine)  # Should not raise
