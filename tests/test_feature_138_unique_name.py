"""
Test Feature #138: UNIQUE constraint on agent_specs.name column
===============================================================

Verifies that:
1. The AgentSpec.name column has unique=True in the model definition
2. Attempting to create two AgentSpecs with the same name raises IntegrityError
3. The API returns a meaningful error message on duplicate name conflicts
4. The migration adds a unique index to existing databases
"""

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError


def _generate_uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# Step 1: Verify the model definition has unique=True
# =============================================================================

class TestModelDefinition:
    """Verify the AgentSpec.name column has unique=True."""

    def test_name_column_has_unique_constraint(self):
        """The name column on AgentSpec should have unique=True."""
        from api.agentspec_models import AgentSpec

        name_col = AgentSpec.__table__.columns["name"]
        assert name_col.unique is True, (
            f"AgentSpec.name column should have unique=True, got unique={name_col.unique}"
        )

    def test_name_column_is_not_nullable(self):
        """The name column should also be NOT NULL."""
        from api.agentspec_models import AgentSpec

        name_col = AgentSpec.__table__.columns["name"]
        assert name_col.nullable is False, "AgentSpec.name should be NOT NULL"


# =============================================================================
# Step 2: Verify database enforces uniqueness
# =============================================================================

class TestDatabaseUniqueness:
    """Verify the database enforces the unique constraint on name."""

    def test_create_two_specs_same_name_raises_integrity_error(self):
        """Creating two AgentSpecs with the same name should raise IntegrityError."""
        from api.agentspec_models import AgentSpec, create_tool_policy
        from api.database import create_database

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            engine, SessionLocal = create_database(project_dir)
            session = SessionLocal()

            try:
                # Create first spec with a unique name
                spec1 = AgentSpec(
                    id=_generate_uuid(),
                    name="duplicate-test-name",
                    display_name="First Spec",
                    spec_version="v1",
                    objective="Test objective 1",
                    task_type="coding",
                    tool_policy=create_tool_policy(["tool1"]),
                    max_turns=50,
                    timeout_seconds=1800,
                    priority=500,
                    created_at=_utc_now(),
                )
                session.add(spec1)
                session.commit()

                # Create second spec with THE SAME name
                spec2 = AgentSpec(
                    id=_generate_uuid(),
                    name="duplicate-test-name",  # Same name!
                    display_name="Second Spec",
                    spec_version="v1",
                    objective="Test objective 2",
                    task_type="testing",
                    tool_policy=create_tool_policy(["tool2"]),
                    max_turns=50,
                    timeout_seconds=1800,
                    priority=500,
                    created_at=_utc_now(),
                )
                session.add(spec2)

                # This should raise IntegrityError
                with pytest.raises(IntegrityError) as exc_info:
                    session.commit()

                # Verify it's specifically about the unique constraint
                error_msg = str(exc_info.value)
                assert "UNIQUE constraint failed" in error_msg or "unique" in error_msg.lower(), (
                    f"Expected UNIQUE constraint error, got: {error_msg}"
                )

            finally:
                session.close()
                engine.dispose()

    def test_different_names_succeed(self):
        """Creating two AgentSpecs with different names should succeed."""
        from api.agentspec_models import AgentSpec, create_tool_policy
        from api.database import create_database

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            engine, SessionLocal = create_database(project_dir)
            session = SessionLocal()

            try:
                spec1 = AgentSpec(
                    id=_generate_uuid(),
                    name="unique-name-alpha",
                    display_name="First Spec",
                    spec_version="v1",
                    objective="Test objective 1",
                    task_type="coding",
                    tool_policy=create_tool_policy(["tool1"]),
                    max_turns=50,
                    timeout_seconds=1800,
                    priority=500,
                    created_at=_utc_now(),
                )
                session.add(spec1)
                session.commit()

                spec2 = AgentSpec(
                    id=_generate_uuid(),
                    name="unique-name-beta",  # Different name
                    display_name="Second Spec",
                    spec_version="v1",
                    objective="Test objective 2",
                    task_type="testing",
                    tool_policy=create_tool_policy(["tool2"]),
                    max_turns=50,
                    timeout_seconds=1800,
                    priority=500,
                    created_at=_utc_now(),
                )
                session.add(spec2)
                session.commit()  # Should succeed

                # Verify both exist
                count = session.query(AgentSpec).count()
                assert count == 2, f"Expected 2 specs, got {count}"

            finally:
                session.close()
                engine.dispose()

    def test_crud_create_agent_spec_duplicate_name(self):
        """The CRUD function create_agent_spec should fail on duplicate names."""
        from api.agentspec_crud import create_agent_spec
        from api.database import create_database

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            engine, SessionLocal = create_database(project_dir)
            session = SessionLocal()

            try:
                # Create first spec via CRUD
                spec1 = create_agent_spec(
                    session,
                    name="crud-dup-test",
                    display_name="First via CRUD",
                    objective="Test objective",
                    task_type="coding",
                    allowed_tools=["tool1"],
                )
                session.commit()

                # Try to create second with same name - this should raise
                # IntegrityError during the flush() inside create_agent_spec
                with pytest.raises(IntegrityError):
                    create_agent_spec(
                        session,
                        name="crud-dup-test",  # Same name!
                        display_name="Second via CRUD",
                        objective="Test objective 2",
                        task_type="testing",
                        allowed_tools=["tool2"],
                    )

            finally:
                session.close()
                engine.dispose()


# =============================================================================
# Step 3: Verify API returns meaningful error on duplicate
# =============================================================================

class TestAPIErrorResponse:
    """Verify the API endpoint returns proper error on duplicate name."""

    def test_api_router_handles_duplicate_name_error(self):
        """
        The create_agent_spec route in agent_specs.py already handles IntegrityError
        and checks for 'UNIQUE constraint failed' + 'name' in the error message.
        Verify the error handling code path exists.
        """
        import inspect as py_inspect
        from server.routers.agent_specs import create_agent_spec as api_create

        # Get the source code of the create function
        source = py_inspect.getsource(api_create)

        # Verify the IntegrityError handling is present
        assert "IntegrityError" in source, "API should catch IntegrityError"
        assert "UNIQUE constraint failed" in source, "API should check for UNIQUE constraint"
        assert "duplicate name" in source, "API should return 'duplicate name' error message"
        assert "HTTP_400_BAD_REQUEST" in source, "API should return 400 status"

    def test_update_router_handles_duplicate_name_error(self):
        """
        The update_agent_spec route should also handle duplicate name on update.
        """
        import inspect as py_inspect
        from server.routers.agent_specs import update_agent_spec as api_update

        source = py_inspect.getsource(api_update)

        # Verify the IntegrityError handling is present for updates too
        assert "IntegrityError" in source, "Update API should catch IntegrityError"
        assert "UNIQUE constraint failed" in source, "Update API should check for UNIQUE constraint"
        assert "duplicate name" in source, "Update API should return 'duplicate name' message"


# =============================================================================
# Step 4: Verify migration adds unique index to existing databases
# =============================================================================

class TestMigration:
    """Verify the migration adds a unique index on agent_specs.name."""

    def test_migration_creates_unique_index(self):
        """After create_database, agent_specs.name should have a unique index."""
        from api.database import create_database

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            engine, SessionLocal = create_database(project_dir)

            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(engine)

            # Check for unique index on name column
            indexes = inspector.get_indexes("agent_specs")
            unique_constraints = inspector.get_unique_constraints("agent_specs")

            has_unique_name = False

            # Check indexes
            for idx in indexes:
                if idx.get("unique") and "name" in idx.get("column_names", []):
                    has_unique_name = True
                    break

            # Check unique constraints
            if not has_unique_name:
                for uc in unique_constraints:
                    if "name" in uc.get("column_names", []):
                        has_unique_name = True
                        break

            assert has_unique_name, (
                f"agent_specs.name should have a unique index/constraint. "
                f"Indexes: {indexes}, Unique constraints: {unique_constraints}"
            )

            engine.dispose()

    def test_migration_is_idempotent(self):
        """Running create_database multiple times should not fail."""
        from api.database import create_database

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # First call
            engine1, _ = create_database(project_dir)
            engine1.dispose()

            # Second call - should not fail
            engine2, _ = create_database(project_dir)
            engine2.dispose()

            # Third call - should not fail
            engine3, SessionLocal3 = create_database(project_dir)

            # Verify constraint still works
            from api.agentspec_models import AgentSpec, create_tool_policy
            session = SessionLocal3()

            try:
                spec = AgentSpec(
                    id=_generate_uuid(),
                    name="idempotent-test",
                    display_name="Test",
                    spec_version="v1",
                    objective="Test",
                    task_type="coding",
                    tool_policy=create_tool_policy(["tool1"]),
                    max_turns=50,
                    timeout_seconds=1800,
                    priority=500,
                    created_at=_utc_now(),
                )
                session.add(spec)
                session.commit()

                # Duplicate should still fail
                spec2 = AgentSpec(
                    id=_generate_uuid(),
                    name="idempotent-test",
                    display_name="Test 2",
                    spec_version="v1",
                    objective="Test 2",
                    task_type="testing",
                    tool_policy=create_tool_policy(["tool2"]),
                    max_turns=50,
                    timeout_seconds=1800,
                    priority=500,
                    created_at=_utc_now(),
                )
                session.add(spec2)

                with pytest.raises(IntegrityError):
                    session.commit()
            finally:
                session.close()
                engine3.dispose()
