"""
Test AgentSpec Migration
========================

Verifies that:
1. AgentSpec tables are created correctly
2. Migration is idempotent (can be run multiple times safely)
3. Existing Feature table is not modified
4. All models can be instantiated and persisted
"""

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_migration_creates_tables():
    """Test that migration creates all AgentSpec tables."""
    from api.database import create_database

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # Check all expected tables exist
        expected_tables = [
            "features",
            "schedules",
            "schedule_overrides",
            "agent_specs",
            "acceptance_specs",
            "agent_runs",
            "artifacts",
            "agent_events",
        ]

        for table in expected_tables:
            assert table in tables, f"Table {table} not found"

        engine.dispose()


def test_migration_is_idempotent():
    """Test that running migration multiple times is safe."""
    from api.database import create_database

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Run migration first time
        engine1, SessionLocal1 = create_database(project_dir)
        engine1.dispose()

        # Run migration second time - should not fail
        engine2, SessionLocal2 = create_database(project_dir)

        from sqlalchemy import inspect
        inspector = inspect(engine2)
        tables = inspector.get_table_names()

        # All tables should still exist
        assert "agent_specs" in tables
        assert "agent_runs" in tables

        engine2.dispose()


def test_feature_table_unchanged():
    """Test that Feature table schema is not modified."""
    from api.database import create_database, Feature

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        from sqlalchemy import inspect
        inspector = inspect(engine)

        # Check Feature table columns
        columns = {col["name"] for col in inspector.get_columns("features")}
        expected_columns = {
            "id", "priority", "category", "name", "description",
            "steps", "passes", "in_progress", "dependencies"
        }

        assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

        # Verify we can still create features
        session = SessionLocal()
        try:
            feature = Feature(
                priority=1,
                category="Test",
                name="Test Feature",
                description="Test description",
                steps=["step1"],
                passes=False,
                in_progress=False,
            )
            session.add(feature)
            session.commit()

            # Verify feature was created
            fetched = session.query(Feature).first()
            assert fetched is not None
            assert fetched.name == "Test Feature"
        finally:
            session.close()

        engine.dispose()


def test_agentspec_crud_operations():
    """Test basic CRUD operations on AgentSpec models."""
    from api.database import create_database
    from api.agentspec_models import (
        AgentSpec,
        AcceptanceSpec,
        AgentRun,
        Artifact,
        AgentEvent,
        create_tool_policy,
        create_validator,
    )
    from api.agentspec_crud import (
        create_agent_spec,
        create_acceptance_spec,
        create_agent_run,
        start_run,
        create_event,
        create_artifact,
        get_agent_spec,
        get_agent_run,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        session = SessionLocal()
        try:
            # Create AgentSpec
            spec = create_agent_spec(
                session,
                name="test-spec",
                display_name="Test Spec",
                objective="Test objective for the agent",
                task_type="coding",
                allowed_tools=["feature_get_by_id", "feature_mark_passing"],
                icon="gear",
                context={"test": True},
                max_turns=25,
                timeout_seconds=900,
                priority=100,
                tags=["test"],
            )
            session.commit()

            assert spec.id is not None
            assert spec.name == "test-spec"
            assert spec.spec_version == "v1"
            assert spec.tool_policy["policy_version"] == "v1"
            assert "feature_get_by_id" in spec.tool_policy["allowed_tools"]

            # Create AcceptanceSpec
            acceptance = create_acceptance_spec(
                session,
                agent_spec_id=spec.id,
                validators=[
                    create_validator("test_pass", {"command": "npm test"}),
                    create_validator("file_exists", {"path": "src/index.ts"}),
                ],
                gate_mode="all_pass",
            )
            session.commit()

            assert acceptance.id is not None
            assert acceptance.agent_spec_id == spec.id
            assert len(acceptance.validators) == 2

            # Create AgentRun
            run = create_agent_run(session, spec.id)
            session.commit()

            assert run.id is not None
            assert run.status == "pending"
            assert run.turns_used == 0

            # Start run
            started_run = start_run(session, run.id)
            session.commit()

            assert started_run.status == "running"
            assert started_run.started_at is not None

            # Create event
            event = create_event(
                session,
                run.id,
                "started",
                payload={"message": "Run started"},
            )
            session.commit()

            assert event.id is not None
            assert event.sequence == 1
            assert event.event_type == "started"

            # Create artifact
            artifact = create_artifact(
                session,
                run.id,
                "log",
                "Test log content",
                project_dir=project_dir,
                metadata={"test": True},
            )
            session.commit()

            assert artifact.id is not None
            assert artifact.content_hash is not None
            assert artifact.content_inline == "Test log content"  # Small content stored inline

            # Verify retrieval
            fetched_spec = get_agent_spec(session, spec.id)
            assert fetched_spec is not None
            assert fetched_spec.name == "test-spec"

            fetched_run = get_agent_run(session, run.id)
            assert fetched_run is not None
            assert fetched_run.status == "running"

        finally:
            session.close()

        engine.dispose()


def test_event_sequence_deterministic():
    """Test that event sequences are deterministic per run."""
    from api.database import create_database
    from api.agentspec_crud import (
        create_agent_spec,
        create_agent_run,
        create_event,
        get_events,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        session = SessionLocal()
        try:
            spec = create_agent_spec(
                session,
                name="seq-test",
                display_name="Sequence Test",
                objective="Test event sequencing",
                task_type="testing",
                allowed_tools=["feature_get_stats"],
            )
            run = create_agent_run(session, spec.id)
            session.commit()

            # Create multiple events
            e1 = create_event(session, run.id, "started")
            e2 = create_event(session, run.id, "tool_call", tool_name="feature_get_stats")
            e3 = create_event(session, run.id, "tool_result")
            e4 = create_event(session, run.id, "completed")
            session.commit()

            # Verify sequences are 1, 2, 3, 4
            assert e1.sequence == 1
            assert e2.sequence == 2
            assert e3.sequence == 3
            assert e4.sequence == 4

            # Verify retrieval order
            events = get_events(session, run.id)
            assert len(events) == 4
            assert events[0].sequence == 1
            assert events[3].sequence == 4

        finally:
            session.close()

        engine.dispose()


def test_large_payload_truncation():
    """Test that large event payloads are truncated and stored as artifacts."""
    from api.database import create_database
    from api.agentspec_crud import (
        create_agent_spec,
        create_agent_run,
        create_event,
    )
    from api.agentspec_models import EVENT_PAYLOAD_MAX_SIZE

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        session = SessionLocal()
        try:
            spec = create_agent_spec(
                session,
                name="payload-test",
                display_name="Payload Test",
                objective="Test payload truncation",
                task_type="testing",
                allowed_tools=["feature_get_stats"],
            )
            run = create_agent_run(session, spec.id)
            session.commit()

            # Create event with large payload
            large_content = "x" * (EVENT_PAYLOAD_MAX_SIZE + 1000)
            event = create_event(
                session,
                run.id,
                "tool_result",
                payload={"output": large_content},
                project_dir=project_dir,
            )
            session.commit()

            # Verify truncation
            assert event.payload_truncated is not None
            assert event.payload_truncated > EVENT_PAYLOAD_MAX_SIZE
            assert event.artifact_ref is not None  # Full payload stored as artifact
            assert "_truncated" in event.payload

        finally:
            session.close()

        engine.dispose()


def test_artifact_content_addressable():
    """Test that duplicate artifact content uses same storage."""
    from api.database import create_database
    from api.agentspec_crud import (
        create_agent_spec,
        create_agent_run,
        create_artifact,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        session = SessionLocal()
        try:
            spec = create_agent_spec(
                session,
                name="dedup-test",
                display_name="Dedup Test",
                objective="Test content deduplication",
                task_type="testing",
                allowed_tools=["feature_get_stats"],
            )
            run = create_agent_run(session, spec.id)
            session.commit()

            # Create two artifacts with same content
            content = "Duplicate content for testing"
            a1 = create_artifact(session, run.id, "log", content, project_dir=project_dir)
            a2 = create_artifact(session, run.id, "log", content, project_dir=project_dir)
            session.commit()

            # Both should have same hash
            assert a1.content_hash == a2.content_hash

            # Both are inline (small content)
            assert a1.content_inline == content
            assert a2.content_inline == content

        finally:
            session.close()

        engine.dispose()


def test_feature_to_agentspec_link():
    """Test optional Feature -> AgentSpec linking."""
    from api.database import create_database, Feature
    from api.agentspec_crud import (
        create_agent_spec,
        get_agent_spec_by_feature,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        engine, SessionLocal = create_database(project_dir)

        session = SessionLocal()
        try:
            # Create a feature first
            feature = Feature(
                priority=1,
                category="Auth",
                name="Login Feature",
                description="Implement login",
                steps=["Create form", "Add validation"],
                passes=False,
                in_progress=False,
            )
            session.add(feature)
            session.commit()
            session.refresh(feature)

            # Create AgentSpec linked to feature
            spec = create_agent_spec(
                session,
                name="feature-login-impl",
                display_name="Implement Login Feature",
                objective="Implement the login feature",
                task_type="coding",
                allowed_tools=["feature_get_by_id", "feature_mark_passing"],
                source_feature_id=feature.id,
            )
            session.commit()

            # Verify link
            assert spec.source_feature_id == feature.id

            # Find spec by feature
            found_spec = get_agent_spec_by_feature(session, feature.id)
            assert found_spec is not None
            assert found_spec.id == spec.id

            # Feature without spec returns None
            no_spec = get_agent_spec_by_feature(session, 99999)
            assert no_spec is None

        finally:
            session.close()

        engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
