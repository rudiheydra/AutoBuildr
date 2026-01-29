"""Tests for Feature #144: Make agent_events.artifact_ref a proper Foreign Key to artifacts.

Verifies that:
1. The artifact_ref column has ForeignKey('artifacts.id') in the model
2. A SQLAlchemy relationship enables easy artifact loading from events
3. Creating an event with a valid artifact_ref correctly references the artifact
4. Creating an event with artifact_ref=None still works
5. Cascade behavior: events are NOT deleted when artifacts are deleted (SET NULL)
6. Migration cleans up orphaned artifact_ref values
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session, sessionmaker

from api.agentspec_models import (
    AgentEvent,
    AgentRun,
    AgentSpec,
    Artifact,
    Base,
    generate_uuid,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:")
    # Enable FK enforcement (critical for testing FK behavior)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_spec(db_session: Session):
    """Create a sample AgentSpec for tests."""
    spec = AgentSpec(
        id=generate_uuid(),
        name=f"test-spec-{generate_uuid()[:8]}",
        display_name="Test Spec",
        objective="Test objective",
        task_type="coding",
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=10,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def sample_run(db_session: Session, sample_spec: AgentSpec):
    """Create a sample AgentRun for tests."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_spec.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture
def sample_artifact(db_session: Session, sample_run: AgentRun):
    """Create a sample Artifact for tests."""
    artifact = Artifact(
        id=generate_uuid(),
        run_id=sample_run.id,
        artifact_type="log",
        content_inline="test content",
        content_hash="a" * 64,
        size_bytes=12,
    )
    db_session.add(artifact)
    db_session.commit()
    return artifact


class TestModelDefinition:
    """Step 1-2: Verify the column definition has ForeignKey."""

    def test_artifact_ref_has_foreign_key(self):
        """artifact_ref column must have ForeignKey('artifacts.id')."""
        col = AgentEvent.__table__.c.artifact_ref
        fk_targets = {str(fk.target_fullname) for fk in col.foreign_keys}
        assert "artifacts.id" in fk_targets, (
            f"artifact_ref should reference artifacts.id, got: {fk_targets}"
        )

    def test_artifact_ref_is_nullable(self):
        """artifact_ref must remain nullable."""
        col = AgentEvent.__table__.c.artifact_ref
        assert col.nullable is True

    def test_artifact_ref_ondelete_set_null(self):
        """FK should have SET NULL on delete (don't delete events when artifacts are deleted)."""
        col = AgentEvent.__table__.c.artifact_ref
        for fk in col.foreign_keys:
            if str(fk.target_fullname) == "artifacts.id":
                assert fk.ondelete == "SET NULL", (
                    f"Expected SET NULL on delete, got: {fk.ondelete}"
                )

    def test_artifact_ref_is_string_36(self):
        """artifact_ref should be String(36) to match artifacts.id."""
        col = AgentEvent.__table__.c.artifact_ref
        assert str(col.type) == "VARCHAR(36)"


class TestRelationship:
    """Step 3: Verify SQLAlchemy relationship for easy artifact loading."""

    def test_agent_event_has_artifact_relationship(self):
        """AgentEvent should have an 'artifact' relationship."""
        assert hasattr(AgentEvent, "artifact"), (
            "AgentEvent must have an 'artifact' relationship"
        )

    def test_artifact_has_referencing_events_relationship(self):
        """Artifact should have a 'referencing_events' relationship."""
        assert hasattr(Artifact, "referencing_events"), (
            "Artifact must have a 'referencing_events' relationship"
        )

    def test_relationship_loads_artifact(self, db_session, sample_run, sample_artifact):
        """Creating event with artifact_ref should allow accessing .artifact."""
        event = AgentEvent(
            run_id=sample_run.id,
            event_type="tool_result",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
            artifact_ref=sample_artifact.id,
        )
        db_session.add(event)
        db_session.commit()

        # Refresh to load relationships
        db_session.refresh(event)
        assert event.artifact is not None
        assert event.artifact.id == sample_artifact.id
        assert event.artifact.artifact_type == "log"

    def test_reverse_relationship_loads_events(self, db_session, sample_run, sample_artifact):
        """Artifact.referencing_events should list events that reference it."""
        event1 = AgentEvent(
            run_id=sample_run.id,
            event_type="tool_result",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
            artifact_ref=sample_artifact.id,
        )
        event2 = AgentEvent(
            run_id=sample_run.id,
            event_type="completed",
            timestamp=datetime.now(timezone.utc),
            sequence=2,
            artifact_ref=sample_artifact.id,
        )
        db_session.add_all([event1, event2])
        db_session.commit()

        db_session.refresh(sample_artifact)
        assert len(sample_artifact.referencing_events) == 2
        event_ids = {e.id for e in sample_artifact.referencing_events}
        assert event1.id in event_ids
        assert event2.id in event_ids


class TestValidArtifactRef:
    """Step 4: Verify that creating an event with a valid artifact_ref works."""

    def test_event_with_valid_artifact_ref(self, db_session, sample_run, sample_artifact):
        """Event with valid artifact_ref should be persisted correctly."""
        event = AgentEvent(
            run_id=sample_run.id,
            event_type="tool_result",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
            artifact_ref=sample_artifact.id,
        )
        db_session.add(event)
        db_session.commit()

        # Query back
        loaded = db_session.query(AgentEvent).filter_by(id=event.id).one()
        assert loaded.artifact_ref == sample_artifact.id

    def test_event_to_dict_includes_artifact_ref(self, db_session, sample_run, sample_artifact):
        """to_dict() should include the artifact_ref value."""
        event = AgentEvent(
            run_id=sample_run.id,
            event_type="tool_result",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
            artifact_ref=sample_artifact.id,
        )
        db_session.add(event)
        db_session.commit()

        d = event.to_dict()
        assert d["artifact_ref"] == sample_artifact.id


class TestNullArtifactRef:
    """Step 5: Verify that creating an event with artifact_ref=None still works."""

    def test_event_with_null_artifact_ref(self, db_session, sample_run):
        """Event with artifact_ref=None should be persisted correctly."""
        event = AgentEvent(
            run_id=sample_run.id,
            event_type="started",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
            artifact_ref=None,
        )
        db_session.add(event)
        db_session.commit()

        loaded = db_session.query(AgentEvent).filter_by(id=event.id).one()
        assert loaded.artifact_ref is None

    def test_event_without_artifact_ref_defaults_none(self, db_session, sample_run):
        """Event without setting artifact_ref should default to None."""
        event = AgentEvent(
            run_id=sample_run.id,
            event_type="started",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
        )
        db_session.add(event)
        db_session.commit()

        loaded = db_session.query(AgentEvent).filter_by(id=event.id).one()
        assert loaded.artifact_ref is None
        assert loaded.artifact is None


class TestCascadeBehavior:
    """Step 6: Ensure cascade behavior - don't delete events when artifacts are deleted."""

    def test_delete_artifact_sets_event_ref_to_null(self, db_session, sample_run, sample_artifact):
        """Deleting an artifact should SET NULL on referencing events, not delete them."""
        event = AgentEvent(
            run_id=sample_run.id,
            event_type="tool_result",
            timestamp=datetime.now(timezone.utc),
            sequence=1,
            artifact_ref=sample_artifact.id,
        )
        db_session.add(event)
        db_session.commit()
        event_id = event.id

        # Delete the artifact
        db_session.delete(sample_artifact)
        db_session.commit()

        # Event should still exist but artifact_ref should be NULL
        loaded = db_session.query(AgentEvent).filter_by(id=event_id).one_or_none()
        assert loaded is not None, "Event should NOT be deleted when artifact is deleted"
        assert loaded.artifact_ref is None, "artifact_ref should be SET NULL after artifact deletion"

    def test_delete_artifact_preserves_all_referencing_events(
        self, db_session, sample_run, sample_artifact
    ):
        """Multiple events referencing the same artifact should all be preserved."""
        events = []
        for i in range(3):
            event = AgentEvent(
                run_id=sample_run.id,
                event_type="tool_result",
                timestamp=datetime.now(timezone.utc),
                sequence=i + 1,
                artifact_ref=sample_artifact.id,
            )
            db_session.add(event)
            events.append(event)
        db_session.commit()
        event_ids = [e.id for e in events]

        # Delete the artifact
        db_session.delete(sample_artifact)
        db_session.commit()

        # All events should still exist
        for eid in event_ids:
            loaded = db_session.query(AgentEvent).filter_by(id=eid).one_or_none()
            assert loaded is not None, f"Event {eid} should survive artifact deletion"
            assert loaded.artifact_ref is None


class TestForeignKeyEnforcement:
    """Additional tests: FK constraint is enforced for invalid references."""

    def test_fk_constraint_enforced_on_new_db(self):
        """On a fresh database with PRAGMA foreign_keys=ON, invalid artifact_ref should fail."""
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        try:
            # Create necessary spec and run
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"test-spec-fk-{generate_uuid()[:8]}",
                display_name="FK Test Spec",
                objective="Test FK enforcement",
                task_type="coding",
                tool_policy={"allowed_tools": ["Read"]},
                max_turns=10,
                timeout_seconds=300,
            )
            session.add(spec)
            session.commit()

            run = AgentRun(
                id=generate_uuid(),
                agent_spec_id=spec.id,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.commit()

            # Try to create event with non-existent artifact_ref
            event = AgentEvent(
                run_id=run.id,
                event_type="tool_result",
                timestamp=datetime.now(timezone.utc),
                sequence=1,
                artifact_ref="nonexistent-artifact-id",
            )
            session.add(event)

            # Should raise IntegrityError due to FK constraint
            with pytest.raises(Exception):
                session.commit()
        finally:
            session.close()
            engine.dispose()


class TestMigration:
    """Test the migration function for existing databases."""

    def test_migration_cleans_orphaned_refs(self):
        """Migration should NULL out artifact_ref values pointing to non-existent artifacts."""
        from api.database import _migrate_add_agent_event_artifact_fk

        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys=OFF"))  # Simulate old DB without FK
            conn.commit()

        # Create tables without FK enforcement
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        try:
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"test-migration-{generate_uuid()[:8]}",
                display_name="Migration Test",
                objective="Test migration",
                task_type="coding",
                tool_policy={"allowed_tools": []},
                max_turns=5,
                timeout_seconds=60,
            )
            session.add(spec)
            session.commit()

            run = AgentRun(
                id=generate_uuid(),
                agent_spec_id=spec.id,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.commit()

            # Create artifact
            artifact = Artifact(
                id=generate_uuid(),
                run_id=run.id,
                artifact_type="log",
                content_inline="valid content",
                content_hash="b" * 64,
                size_bytes=13,
            )
            session.add(artifact)
            session.commit()

            # Directly insert an event with orphaned artifact_ref (bypassing FK)
            with engine.connect() as conn:
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(text(
                    "INSERT INTO agent_events (run_id, event_type, timestamp, sequence, artifact_ref) "
                    f"VALUES ('{run.id}', 'tool_result', '2026-01-30', 1, 'orphaned-ref-id')"
                ))
                # Also insert an event with valid artifact_ref
                conn.execute(text(
                    "INSERT INTO agent_events (run_id, event_type, timestamp, sequence, artifact_ref) "
                    f"VALUES ('{run.id}', 'tool_result', '2026-01-30', 2, '{artifact.id}')"
                ))
                conn.commit()

            # Run migration
            _migrate_add_agent_event_artifact_fk(engine)

            # Verify: orphaned ref should be NULL, valid ref should remain
            session.expire_all()
            with engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT sequence, artifact_ref FROM agent_events ORDER BY sequence"
                )).fetchall()

            assert len(result) == 2
            # Orphaned ref (sequence=1) should be NULL
            assert result[0][1] is None, f"Orphaned artifact_ref should be NULL, got: {result[0][1]}"
            # Valid ref (sequence=2) should be preserved
            assert result[1][1] == artifact.id, f"Valid artifact_ref should be preserved"
        finally:
            session.close()
            engine.dispose()

    def test_migration_idempotent(self):
        """Running migration multiple times should be safe."""
        from api.database import _migrate_add_agent_event_artifact_fk

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)

        # Run migration twice - should not error
        _migrate_add_agent_event_artifact_fk(engine)
        _migrate_add_agent_event_artifact_fk(engine)

        engine.dispose()

    def test_migration_handles_missing_tables(self):
        """Migration should gracefully handle missing tables."""
        from api.database import _migrate_add_agent_event_artifact_fk

        engine = create_engine("sqlite:///:memory:")
        # Don't create any tables
        _migrate_add_agent_event_artifact_fk(engine)  # Should not error
        engine.dispose()
