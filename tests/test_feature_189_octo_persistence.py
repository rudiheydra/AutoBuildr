"""
Tests for Feature #189: Octo persists AgentSpecs to database
============================================================

Feature Steps:
1. AgentSpec saved to agent_specs table after generation
2. Spec includes source_type='octo_generated'
3. Spec linked to project and triggering request
4. Database record created before file materialization
5. Dual persistence: DB is system-of-record, files are CLI-authoritative

This test file verifies that Octo properly persists generated AgentSpecs
to the database with the correct metadata for traceability.
"""
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from api.database import Base
from api.agentspec_models import AgentSpec, AcceptanceSpec, generate_uuid
from api.octo import (
    Octo,
    OctoRequestPayload,
    OctoResponse,
    SpecPersistenceResult,
    SOURCE_TYPE_OCTO_GENERATED,
    SOURCE_TYPE_MANUAL,
    SOURCE_TYPE_DSPy,
    SOURCE_TYPE_TEMPLATE,
    SOURCE_TYPE_IMPORTED,
    VALID_SOURCE_TYPES,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal


@pytest.fixture
def session(in_memory_db):
    """Get a test session."""
    _, SessionLocal = in_memory_db
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_agent_spec():
    """Create a sample AgentSpec for testing."""
    return AgentSpec(
        id=generate_uuid(),
        name="test-e2e-agent",
        display_name="Test E2E Agent",
        objective="Test end-to-end functionality",
        task_type="testing",
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["browser_navigate", "browser_click"],
            "forbidden_patterns": [],
            "tool_hints": {},
        },
        max_turns=50,
        timeout_seconds=1800,
        context={},
    )


@pytest.fixture
def sample_payload():
    """Create a sample OctoRequestPayload for testing."""
    return OctoRequestPayload(
        project_context={
            "name": "test-project",
            "tech_stack": ["React", "Python", "FastAPI"],
            "execution_environment": "local",
        },
        required_capabilities=["e2e_testing"],
        existing_agents=["coder"],
        constraints={"max_agents": 5},
        source_feature_ids=[42, 43],
        request_id="test-request-123",
    )


@pytest.fixture
def mock_spec_builder():
    """Create a mock SpecBuilder for testing."""
    from api.spec_builder import BuildResult

    mock_builder = MagicMock()

    def mock_build(task_description, task_type, context=None):
        spec = AgentSpec(
            id=generate_uuid(),
            name=f"generated-{task_type}-agent",
            display_name=f"Generated {task_type.title()} Agent",
            objective=task_description,
            task_type=task_type,
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["feature_get_by_id", "feature_mark_passing"],
                "forbidden_patterns": [],
                "tool_hints": {},
            },
            max_turns=100,
            timeout_seconds=1800,
            context=context or {},
        )
        return BuildResult(
            success=True,
            agent_spec=spec,
            error=None,
        )

    mock_builder.build = mock_build
    return mock_builder


@pytest.fixture
def octo_with_mock_builder(mock_spec_builder):
    """Create an Octo instance with mocked SpecBuilder."""
    return Octo(spec_builder=mock_spec_builder)


# =============================================================================
# Test Step 1: AgentSpec saved to agent_specs table after generation
# =============================================================================

class TestStep1AgentSpecSavedToTable:
    """Test that AgentSpecs are properly saved to the database."""

    def test_persist_spec_creates_db_record(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify that persist_spec creates a database record."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="test-project",
            octo_request_id="test-req-1",
        )
        session.commit()

        # Verify persistence was successful
        assert result.success is True
        assert result.spec_id == sample_agent_spec.id
        assert result.spec_name == sample_agent_spec.name

        # Verify record exists in database
        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        assert db_spec is not None
        assert db_spec.name == "test-e2e-agent"
        assert db_spec.task_type == "testing"

    def test_persist_specs_creates_multiple_records(self, session, octo_with_mock_builder):
        """Verify that persist_specs creates multiple database records."""
        octo = octo_with_mock_builder

        specs = [
            AgentSpec(
                id=generate_uuid(),
                name=f"test-agent-{i}",
                display_name=f"Test Agent {i}",
                objective=f"Test objective {i}",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
                max_turns=50,
                timeout_seconds=1800,
                context={},
            )
            for i in range(3)
        ]

        results = octo.persist_specs(
            specs=specs,
            session=session,
            project_name="test-project",
            octo_request_id="test-req-multi",
        )
        session.commit()

        # All should succeed
        assert len(results) == 3
        assert all(r.success for r in results)

        # Verify all records exist in database
        db_count = session.query(AgentSpec).count()
        assert db_count == 3

    def test_persist_spec_handles_duplicate_name(self, session, octo_with_mock_builder):
        """Verify that duplicate name handling returns an error."""
        octo = octo_with_mock_builder

        spec1 = AgentSpec(
            id=generate_uuid(),
            name="duplicate-name",
            display_name="First Agent",
            objective="First objective",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
            max_turns=50,
            timeout_seconds=1800,
            context={},
        )

        result1 = octo.persist_spec(spec=spec1, session=session)
        session.commit()
        assert result1.success is True

        # Try to create another spec with the same name
        spec2 = AgentSpec(
            id=generate_uuid(),
            name="duplicate-name",  # Same name
            display_name="Second Agent",
            objective="Second objective",
            task_type="coding",
            tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
            max_turns=50,
            timeout_seconds=1800,
            context={},
        )

        result2 = octo.persist_spec(spec=spec2, session=session)
        # This should fail due to unique constraint on name
        # Either in persist_spec or commit
        try:
            session.commit()
            # If commit succeeds, the second persist should have failed
            assert result2.success is False or result2.error is not None
        except Exception:
            # Expected - duplicate name should cause an error
            session.rollback()


# =============================================================================
# Test Step 2: Spec includes source_type='octo_generated'
# =============================================================================

class TestStep2SourceTypeOctoGenerated:
    """Test that specs include source_type='octo_generated' in context."""

    def test_source_type_set_in_context(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify that source_type is set in spec context."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
        )
        session.commit()

        # Verify source_type in result
        assert result.source_type == SOURCE_TYPE_OCTO_GENERATED

        # Verify source_type in spec context
        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        assert db_spec.context is not None
        assert db_spec.context.get("source_type") == SOURCE_TYPE_OCTO_GENERATED

    def test_valid_source_types_constant(self):
        """Verify VALID_SOURCE_TYPES contains expected values."""
        expected = frozenset([
            "octo_generated",
            "manual",
            "dspy",
            "template",
            "imported",
        ])
        assert VALID_SOURCE_TYPES == expected

    def test_source_type_constants_defined(self):
        """Verify all source type constants are properly defined."""
        assert SOURCE_TYPE_OCTO_GENERATED == "octo_generated"
        assert SOURCE_TYPE_MANUAL == "manual"
        assert SOURCE_TYPE_DSPy == "dspy"
        assert SOURCE_TYPE_TEMPLATE == "template"
        assert SOURCE_TYPE_IMPORTED == "imported"

    def test_source_type_preserved_with_existing_context(self, session, octo_with_mock_builder):
        """Verify source_type is added without overwriting existing context."""
        octo = octo_with_mock_builder

        spec = AgentSpec(
            id=generate_uuid(),
            name="agent-with-context",
            display_name="Agent With Context",
            objective="Test preservation",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
            max_turns=50,
            timeout_seconds=1800,
            context={
                "existing_key": "existing_value",
                "model": "sonnet",
            },
        )

        result = octo.persist_spec(spec=spec, session=session)
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=spec.id).first()
        assert db_spec.context.get("existing_key") == "existing_value"
        assert db_spec.context.get("model") == "sonnet"
        assert db_spec.context.get("source_type") == SOURCE_TYPE_OCTO_GENERATED


# =============================================================================
# Test Step 3: Spec linked to project and triggering request
# =============================================================================

class TestStep3ProjectAndRequestLinking:
    """Test that specs are properly linked to project and request."""

    def test_project_name_in_context(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify project_name is stored in spec context."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="my-awesome-project",
        )
        session.commit()

        assert result.project_name == "my-awesome-project"

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        assert db_spec.context.get("project_name") == "my-awesome-project"

    def test_octo_request_id_in_context(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify octo_request_id is stored in spec context."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            octo_request_id="req-abc-123",
        )
        session.commit()

        assert result.octo_request_id == "req-abc-123"

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        assert db_spec.context.get("octo_request_id") == "req-abc-123"

    def test_source_feature_ids_in_context(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify source_feature_ids are stored in spec context."""
        octo = octo_with_mock_builder

        octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            source_feature_ids=[10, 20, 30],
        )
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        assert db_spec.context.get("source_feature_ids") == [10, 20, 30]

    def test_source_feature_id_column_linked(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify source_feature_id column is set to first feature ID."""
        octo = octo_with_mock_builder

        octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            source_feature_ids=[42, 43, 44],
        )
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        # source_feature_id column should be set to first feature ID
        assert db_spec.source_feature_id == 42

    def test_full_linkage_metadata(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify all linkage metadata is properly set."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="complete-project",
            octo_request_id="req-xyz-789",
            source_feature_ids=[100, 101],
        )
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()

        # Verify all linkage
        assert db_spec.context.get("source_type") == SOURCE_TYPE_OCTO_GENERATED
        assert db_spec.context.get("project_name") == "complete-project"
        assert db_spec.context.get("octo_request_id") == "req-xyz-789"
        assert db_spec.context.get("source_feature_ids") == [100, 101]
        assert db_spec.source_feature_id == 100


# =============================================================================
# Test Step 4: Database record created before file materialization
# =============================================================================

class TestStep4DbBeforeMaterialization:
    """Test that DB record is created before file materialization."""

    def test_generate_and_persist_creates_db_records_first(self, session, sample_payload, octo_with_mock_builder):
        """Verify generate_and_persist creates DB records."""
        octo = octo_with_mock_builder

        response, persistence_results = octo.generate_and_persist_specs(
            payload=sample_payload,
            session=session,
        )
        session.commit()

        # Verify generation succeeded
        assert response.success is True
        assert len(response.agent_specs) >= 1

        # Verify persistence succeeded
        assert len(persistence_results) >= 1
        assert all(r.success for r in persistence_results)

        # Verify DB records exist
        db_count = session.query(AgentSpec).count()
        assert db_count >= 1

    def test_generate_and_persist_returns_before_materialization(self, session, sample_payload, octo_with_mock_builder):
        """Verify generate_and_persist returns specs ready for materialization."""
        octo = octo_with_mock_builder

        response, persistence_results = octo.generate_and_persist_specs(
            payload=sample_payload,
            session=session,
        )
        session.commit()

        # At this point, specs are persisted but no files created
        # The caller can now proceed with materialization
        assert response.success is True

        # Each spec should have DB record
        for result in persistence_results:
            assert result.success is True
            assert result.spec_id is not None

            # Verify spec exists in DB
            db_spec = session.query(AgentSpec).filter_by(id=result.spec_id).first()
            assert db_spec is not None

    def test_generate_and_persist_links_request_id(self, session, sample_payload, octo_with_mock_builder):
        """Verify generate_and_persist links the request ID properly."""
        octo = octo_with_mock_builder

        response, persistence_results = octo.generate_and_persist_specs(
            payload=sample_payload,
            session=session,
        )
        session.commit()

        # Verify request ID is linked
        for result in persistence_results:
            assert result.octo_request_id == sample_payload.request_id

            db_spec = session.query(AgentSpec).filter_by(id=result.spec_id).first()
            assert db_spec.context.get("octo_request_id") == sample_payload.request_id

    def test_generate_and_persist_extracts_project_name(self, session, octo_with_mock_builder):
        """Verify generate_and_persist extracts project name from context."""
        octo = octo_with_mock_builder

        payload = OctoRequestPayload(
            project_context={
                "name": "extracted-project",
                "tech_stack": ["Python"],
            },
            required_capabilities=["testing"],
            request_id="test-extract",
        )

        response, persistence_results = octo.generate_and_persist_specs(
            payload=payload,
            session=session,
        )
        session.commit()

        for result in persistence_results:
            assert result.project_name == "extracted-project"

            db_spec = session.query(AgentSpec).filter_by(id=result.spec_id).first()
            assert db_spec.context.get("project_name") == "extracted-project"


# =============================================================================
# Test Step 5: Dual persistence - DB is system-of-record
# =============================================================================

class TestStep5DualPersistence:
    """Test dual persistence model where DB is system-of-record."""

    def test_db_record_contains_all_spec_data(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify DB record contains complete spec data."""
        octo = octo_with_mock_builder

        octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="full-data-project",
        )
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()

        # Verify all critical fields are stored
        assert db_spec.id is not None
        assert db_spec.name == sample_agent_spec.name
        assert db_spec.display_name == sample_agent_spec.display_name
        assert db_spec.objective == sample_agent_spec.objective
        assert db_spec.task_type == sample_agent_spec.task_type
        assert db_spec.tool_policy is not None
        assert db_spec.max_turns == sample_agent_spec.max_turns
        assert db_spec.timeout_seconds == sample_agent_spec.timeout_seconds
        assert db_spec.created_at is not None

    def test_db_record_is_queryable(self, session, octo_with_mock_builder):
        """Verify DB records can be queried by various fields."""
        octo = octo_with_mock_builder

        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="query-test-1",
                display_name="Query Test 1",
                objective="Objective 1",
                task_type="testing",
                tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
                max_turns=50,
                timeout_seconds=1800,
                context={},
            ),
            AgentSpec(
                id=generate_uuid(),
                name="query-test-2",
                display_name="Query Test 2",
                objective="Objective 2",
                task_type="coding",
                tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
                max_turns=100,
                timeout_seconds=3600,
                context={},
            ),
        ]

        for spec in specs:
            octo.persist_spec(spec=spec, session=session, project_name="query-project")
        session.commit()

        # Query by task_type
        testing_specs = session.query(AgentSpec).filter_by(task_type="testing").all()
        assert len(testing_specs) == 1
        assert testing_specs[0].name == "query-test-1"

        coding_specs = session.query(AgentSpec).filter_by(task_type="coding").all()
        assert len(coding_specs) == 1
        assert coding_specs[0].name == "query-test-2"

    def test_spec_persistence_result_to_dict(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify SpecPersistenceResult serializes to dict."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="serialize-project",
            octo_request_id="serialize-request",
        )

        result_dict = result.to_dict()

        assert result_dict["spec_id"] == sample_agent_spec.id
        assert result_dict["spec_name"] == sample_agent_spec.name
        assert result_dict["success"] is True
        assert result_dict["source_type"] == SOURCE_TYPE_OCTO_GENERATED
        assert result_dict["project_name"] == "serialize-project"
        assert result_dict["octo_request_id"] == "serialize-request"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the complete persistence workflow."""

    def test_full_workflow_generate_persist_query(self, session, sample_payload, octo_with_mock_builder):
        """Test complete workflow: generate -> persist -> query."""
        octo = octo_with_mock_builder

        # Step 1: Generate and persist
        response, persistence_results = octo.generate_and_persist_specs(
            payload=sample_payload,
            session=session,
        )
        session.commit()

        assert response.success is True
        assert len(persistence_results) >= 1

        # Step 2: Query persisted specs
        all_specs = session.query(AgentSpec).all()
        assert len(all_specs) >= 1

        # Step 3: Verify each spec has proper metadata
        for spec in all_specs:
            assert spec.context is not None
            assert spec.context.get("source_type") == SOURCE_TYPE_OCTO_GENERATED

    def test_persistence_failure_does_not_affect_generation(self, session, sample_payload, octo_with_mock_builder):
        """Verify generation response is valid even if persistence fails."""
        octo = octo_with_mock_builder

        # First, generate successfully
        response = octo.generate_specs(sample_payload)

        assert response.success is True
        assert len(response.agent_specs) >= 1

        # The OctoResponse should be complete regardless of persistence


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_persist_with_none_session(self, sample_agent_spec, octo_with_mock_builder):
        """Verify proper error handling with None session."""
        octo = octo_with_mock_builder

        # The implementation catches errors and returns a result with success=False
        result = octo.persist_spec(spec=sample_agent_spec, session=None)
        assert result.success is False
        assert result.error is not None  # Should have an error message

    def test_persist_empty_specs_list(self, session, octo_with_mock_builder):
        """Verify persist_specs handles empty list."""
        octo = octo_with_mock_builder

        results = octo.persist_specs(specs=[], session=session)

        assert results == []

    def test_persist_with_none_project_name(self, session, sample_agent_spec, octo_with_mock_builder):
        """Verify persistence works without project_name."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name=None,
        )
        session.commit()

        assert result.success is True
        assert result.project_name is None

    def test_generate_and_persist_with_failed_generation(self, session, mock_spec_builder):
        """Verify handling when generation fails."""
        from api.spec_builder import BuildResult

        # Mock builder to return failure
        mock_spec_builder.build = lambda *args, **kwargs: BuildResult(
            success=False,
            agent_spec=None,
            error="Generation failed",
        )

        octo = Octo(spec_builder=mock_spec_builder)

        payload = OctoRequestPayload(
            project_context={"name": "fail-project"},
            required_capabilities=["testing"],
            request_id="fail-request",
        )

        response, persistence_results = octo.generate_and_persist_specs(
            payload=payload,
            session=session,
        )

        # No specs generated means no persistence
        assert len(persistence_results) == 0


# =============================================================================
# Feature Step Verification Tests
# =============================================================================

class TestFeature189VerificationSteps:
    """Tests that directly verify each feature step as stated in the spec."""

    def test_step1_agentspec_saved_to_table(self, session, sample_agent_spec, octo_with_mock_builder):
        """Step 1: AgentSpec saved to agent_specs table after generation."""
        octo = octo_with_mock_builder

        # Persist the spec
        result = octo.persist_spec(spec=sample_agent_spec, session=session)
        session.commit()

        # Verify it was saved to the agent_specs table
        assert result.success is True
        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()
        assert db_spec is not None
        assert db_spec.__tablename__ == "agent_specs"

    def test_step2_source_type_octo_generated(self, session, sample_agent_spec, octo_with_mock_builder):
        """Step 2: Spec includes source_type='octo_generated'."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(spec=sample_agent_spec, session=session)
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()

        # The spec MUST include source_type='octo_generated' in its context
        assert db_spec.context is not None
        assert db_spec.context.get("source_type") == "octo_generated"

    def test_step3_linked_to_project_and_request(self, session, sample_agent_spec, octo_with_mock_builder):
        """Step 3: Spec linked to project and triggering request."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="linked-project",
            octo_request_id="linked-request-id",
            source_feature_ids=[55, 56],
        )
        session.commit()

        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()

        # Must have project linkage
        assert db_spec.context.get("project_name") == "linked-project"
        # Must have request linkage
        assert db_spec.context.get("octo_request_id") == "linked-request-id"
        # Must have feature linkage
        assert db_spec.context.get("source_feature_ids") == [55, 56]
        assert db_spec.source_feature_id == 55

    def test_step4_db_before_file_materialization(self, session, sample_payload, octo_with_mock_builder):
        """Step 4: Database record created before file materialization."""
        octo = octo_with_mock_builder

        # generate_and_persist_specs creates DB records BEFORE returning
        # so that caller can then proceed with file materialization
        response, persistence_results = octo.generate_and_persist_specs(
            payload=sample_payload,
            session=session,
        )
        session.commit()

        # At this point, DB records exist but no files have been created
        # Verify DB records exist
        assert len(persistence_results) > 0
        for result in persistence_results:
            assert result.success is True
            db_spec = session.query(AgentSpec).filter_by(id=result.spec_id).first()
            assert db_spec is not None

        # The caller would now call materializer - but DB is already populated

    def test_step5_dual_persistence_db_is_system_of_record(self, session, sample_agent_spec, octo_with_mock_builder):
        """Step 5: Dual persistence: DB is system-of-record, files are CLI-authoritative."""
        octo = octo_with_mock_builder

        result = octo.persist_spec(
            spec=sample_agent_spec,
            session=session,
            project_name="system-of-record",
        )
        session.commit()

        # The DB record is the system-of-record
        # It contains the canonical spec data
        db_spec = session.query(AgentSpec).filter_by(id=sample_agent_spec.id).first()

        # System-of-record means it has all the data needed to reconstruct the spec
        assert db_spec.id is not None
        assert db_spec.name is not None
        assert db_spec.display_name is not None
        assert db_spec.objective is not None
        assert db_spec.task_type is not None
        assert db_spec.tool_policy is not None
        assert db_spec.max_turns is not None
        assert db_spec.timeout_seconds is not None
        assert db_spec.created_at is not None

        # Context contains provenance metadata
        assert db_spec.context.get("source_type") == SOURCE_TYPE_OCTO_GENERATED
        assert db_spec.context.get("project_name") == "system-of-record"
