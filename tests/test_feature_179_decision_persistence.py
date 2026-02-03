"""
Feature #179: Maestro persists agent-planning decisions to database

This test suite verifies:
1. AgentPlanningDecisionRecord model/table creation
2. Storing decision rationale, required capabilities, and timestamp
3. Linking decision to project and triggering feature(s)
4. Decision retrievable via API for UI display
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database with all tables."""
    from api.database import Base
    from api.agentspec_models import AgentPlanningDecisionRecord

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def sample_decision():
    """Create a sample AgentPlanningDecision."""
    from api.maestro import (
        AgentPlanningDecision,
        CapabilityRequirement,
    )

    return AgentPlanningDecision(
        requires_agent_planning=True,
        required_capabilities=[
            CapabilityRequirement(
                capability="playwright",
                source="feature_123",
                keywords_matched=["e2e test", "browser automation"],
                confidence="high",
            ),
            CapabilityRequirement(
                capability="react",
                source="tech_stack",
                keywords_matched=["react"],
                confidence="medium",
            ),
        ],
        existing_capabilities=["coding", "testing"],
        justification="Agent-planning required: 2 specialized capabilities detected.",
        recommended_agent_types=["playwright_e2e", "react_specialist"],
    )


@pytest.fixture
def sample_context():
    """Create a sample ProjectContext."""
    from api.maestro import ProjectContext

    return ProjectContext(
        project_name="test-project",
        project_dir=Path("/test/project"),
        tech_stack=["python", "react", "playwright"],
        features=[
            {"id": 123, "name": "E2E tests", "description": "Browser automation tests"},
            {"id": 124, "name": "Dashboard", "description": "React dashboard component"},
        ],
        existing_agents=["coding", "testing"],
    )


# =============================================================================
# Step 1: AgentPlanningDecisionRecord model/table creation
# =============================================================================

class TestStep1ModelTable:
    """Test AgentPlanningDecisionRecord model and table creation."""

    def test_model_class_exists(self):
        """AgentPlanningDecisionRecord model class exists."""
        from api.agentspec_models import AgentPlanningDecisionRecord

        assert AgentPlanningDecisionRecord is not None
        assert hasattr(AgentPlanningDecisionRecord, '__tablename__')
        assert AgentPlanningDecisionRecord.__tablename__ == "agent_planning_decisions"

    def test_model_has_required_columns(self):
        """Model has all required columns."""
        from api.agentspec_models import AgentPlanningDecisionRecord

        # Check required columns
        columns = [c.name for c in AgentPlanningDecisionRecord.__table__.columns]

        expected_columns = [
            "id",
            "project_name",
            "requires_agent_planning",
            "justification",
            "required_capabilities",
            "existing_capabilities",
            "recommended_agent_types",
            "project_context_snapshot",
            "triggering_feature_ids",
            "created_at",
        ]

        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"

    def test_table_created_in_database(self, in_memory_db):
        """Table is created in the database."""
        inspector = inspect(in_memory_db.get_bind())
        tables = inspector.get_table_names()

        assert "agent_planning_decisions" in tables

    def test_table_has_indexes(self, in_memory_db):
        """Table has appropriate indexes."""
        inspector = inspect(in_memory_db.get_bind())
        indexes = inspector.get_indexes("agent_planning_decisions")

        index_names = [idx["name"] for idx in indexes]

        # Check for expected indexes
        assert any("project" in name for name in index_names), "Missing project index"
        assert any("created" in name for name in index_names), "Missing created_at index"

    def test_model_to_dict_method(self, in_memory_db):
        """Model has to_dict() method for serialization."""
        from api.agentspec_models import AgentPlanningDecisionRecord, generate_uuid

        record = AgentPlanningDecisionRecord(
            id=generate_uuid(),
            project_name="test-project",
            requires_agent_planning=True,
            justification="Test justification",
            required_capabilities=[{"capability": "playwright"}],
            existing_capabilities=["coding"],
            recommended_agent_types=["playwright_e2e"],
        )

        result = record.to_dict()

        assert isinstance(result, dict)
        assert result["project_name"] == "test-project"
        assert result["requires_agent_planning"] == True
        assert result["justification"] == "Test justification"
        assert "id" in result
        assert "created_at" in result


# =============================================================================
# Step 2: Storing decision rationale, required capabilities, and timestamp
# =============================================================================

class TestStep2StoreDecision:
    """Test storing decision data in the database."""

    def test_persist_decision_creates_record(self, in_memory_db, sample_decision):
        """persist_decision creates a database record."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.success == True
        assert result.decision_id is not None
        assert result.record is not None

    def test_stored_decision_has_correct_project_name(self, in_memory_db, sample_decision):
        """Stored decision has correct project_name."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="my-test-project",
            session=in_memory_db,
        )

        assert result.record.project_name == "my-test-project"

    def test_stored_decision_has_correct_requires_planning_flag(self, in_memory_db, sample_decision):
        """Stored decision has correct requires_agent_planning flag."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.record.requires_agent_planning == True

    def test_stored_decision_has_justification(self, in_memory_db, sample_decision):
        """Stored decision contains justification text."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.record.justification is not None
        assert "2 specialized capabilities" in result.record.justification

    def test_stored_decision_has_required_capabilities_as_json(self, in_memory_db, sample_decision):
        """Required capabilities stored as JSON array."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        caps = result.record.required_capabilities
        assert isinstance(caps, list)
        assert len(caps) == 2
        assert caps[0]["capability"] == "playwright"
        assert caps[1]["capability"] == "react"

    def test_stored_decision_has_timestamp(self, in_memory_db, sample_decision):
        """Stored decision has created_at timestamp."""
        from api.maestro import Maestro

        maestro = Maestro()
        before = datetime.now(timezone.utc)

        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        after = datetime.now(timezone.utc)

        assert result.record.created_at is not None
        # Timestamp should be between before and after (with some tolerance)
        # SQLAlchemy may strip tzinfo, so we compare without it
        created = result.record.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        assert before <= created <= after

    def test_stored_decision_has_existing_capabilities(self, in_memory_db, sample_decision):
        """Stored decision has existing_capabilities list."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.record.existing_capabilities == ["coding", "testing"]

    def test_stored_decision_has_recommended_agent_types(self, in_memory_db, sample_decision):
        """Stored decision has recommended_agent_types list."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.record.recommended_agent_types == ["playwright_e2e", "react_specialist"]


# =============================================================================
# Step 3: Linking decision to project and triggering feature(s)
# =============================================================================

class TestStep3LinkToProjectAndFeatures:
    """Test linking decision to project and features."""

    def test_decision_linked_to_project(self, in_memory_db, sample_decision):
        """Decision is linked to the correct project."""
        from api.maestro import Maestro
        from api.agentspec_models import AgentPlanningDecisionRecord

        maestro = Maestro()
        maestro.persist_decision(
            decision=sample_decision,
            project_name="linked-project",
            session=in_memory_db,
        )

        # Query back
        record = in_memory_db.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.project_name == "linked-project"
        ).first()

        assert record is not None
        assert record.project_name == "linked-project"

    def test_decision_stores_triggering_feature_ids(self, in_memory_db, sample_decision):
        """Decision stores triggering_feature_ids."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
            triggering_feature_ids=[123, 124, 125],
        )

        assert result.record.triggering_feature_ids == [123, 124, 125]

    def test_decision_stores_project_context_snapshot(self, in_memory_db, sample_decision, sample_context):
        """Decision stores project_context_snapshot."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
            project_context=sample_context,
        )

        snapshot = result.record.project_context_snapshot
        assert snapshot is not None
        assert snapshot["project_name"] == "test-project"
        assert snapshot["tech_stack"] == ["python", "react", "playwright"]

    def test_multiple_decisions_for_same_project(self, in_memory_db, sample_decision):
        """Multiple decisions can exist for the same project."""
        from api.maestro import Maestro, AgentPlanningDecision
        from api.agentspec_models import AgentPlanningDecisionRecord

        maestro = Maestro()

        # Create first decision
        maestro.persist_decision(
            decision=sample_decision,
            project_name="shared-project",
            session=in_memory_db,
        )

        # Create second decision (different)
        decision2 = AgentPlanningDecision(
            requires_agent_planning=False,
            justification="No new agents required",
        )
        maestro.persist_decision(
            decision=decision2,
            project_name="shared-project",
            session=in_memory_db,
        )

        # Both should exist
        count = in_memory_db.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.project_name == "shared-project"
        ).count()

        assert count == 2

    def test_evaluate_and_persist_convenience_method(self, in_memory_db, sample_context):
        """evaluate_and_persist combines evaluate + persist."""
        from api.maestro import Maestro

        maestro = Maestro()
        decision, persist_result = maestro.evaluate_and_persist(
            context=sample_context,
            session=in_memory_db,
            triggering_feature_ids=[123, 124],
        )

        assert decision is not None
        assert persist_result.success == True
        assert persist_result.record.triggering_feature_ids == [123, 124]


# =============================================================================
# Step 4: Decision retrievable via API for UI display
# =============================================================================

class TestStep4APIRetrieval:
    """Test API endpoints for retrieving decisions."""

    def test_planning_decisions_router_exists(self):
        """Planning decisions router exists."""
        from server.routers.planning_decisions import router

        assert router is not None
        assert router.prefix == "/api/projects/{project_name}/planning-decisions"

    def test_list_endpoint_exists(self):
        """List endpoint exists."""
        from server.routers.planning_decisions import list_planning_decisions

        assert list_planning_decisions is not None

    def test_get_by_id_endpoint_exists(self):
        """Get by ID endpoint exists."""
        from server.routers.planning_decisions import get_planning_decision

        assert get_planning_decision is not None

    def test_evaluate_endpoint_exists(self):
        """Evaluate + persist endpoint exists."""
        from server.routers.planning_decisions import evaluate_and_persist_decision

        assert evaluate_and_persist_decision is not None

    def test_stats_endpoint_exists(self):
        """Stats endpoint exists."""
        from server.routers.planning_decisions import get_planning_decisions_stats

        assert get_planning_decisions_stats is not None

    def test_response_models_defined(self):
        """Response models are defined."""
        from server.routers.planning_decisions import (
            PlanningDecisionResponse,
            PlanningDecisionListResponse,
            EvaluateRequest,
            EvaluateResponse,
        )

        assert PlanningDecisionResponse is not None
        assert PlanningDecisionListResponse is not None
        assert EvaluateRequest is not None
        assert EvaluateResponse is not None

    def test_planning_decision_response_has_required_fields(self):
        """PlanningDecisionResponse has required fields."""
        from server.routers.planning_decisions import PlanningDecisionResponse

        fields = PlanningDecisionResponse.model_fields.keys()

        required = [
            "id",
            "project_name",
            "requires_agent_planning",
            "justification",
            "required_capabilities",
            "existing_capabilities",
            "recommended_agent_types",
        ]

        for field in required:
            assert field in fields, f"Missing field: {field}"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full workflow."""

    def test_full_workflow_evaluate_persist_retrieve(self, in_memory_db):
        """Full workflow: evaluate -> persist -> retrieve."""
        from api.maestro import Maestro, ProjectContext
        from api.agentspec_models import AgentPlanningDecisionRecord

        # Step 1: Create context with capabilities that require planning
        context = ProjectContext(
            project_name="integration-test-project",
            tech_stack=["python", "playwright", "docker"],
            features=[
                {"id": 1, "name": "E2E Login Test", "description": "Browser automation test for login"},
            ],
            existing_agents=["coding", "testing"],
        )

        maestro = Maestro()

        # Step 2: Evaluate and persist
        decision, persist_result = maestro.evaluate_and_persist(
            context=context,
            session=in_memory_db,
            triggering_feature_ids=[1],
        )

        assert persist_result.success == True

        # Step 3: Retrieve from database
        record = in_memory_db.query(AgentPlanningDecisionRecord).filter(
            AgentPlanningDecisionRecord.id == persist_result.decision_id
        ).first()

        assert record is not None
        assert record.project_name == "integration-test-project"
        assert record.triggering_feature_ids == [1]

        # Step 4: Verify record matches decision
        assert record.requires_agent_planning == decision.requires_agent_planning
        assert record.justification == decision.justification

    def test_decision_not_requiring_planning_persists_correctly(self, in_memory_db):
        """Decision that doesn't require planning is persisted correctly."""
        from api.maestro import Maestro, ProjectContext

        # Context with no special requirements
        context = ProjectContext(
            project_name="simple-project",
            tech_stack=["python"],
            features=[
                {"id": 1, "name": "Add function", "description": "Simple function"},
            ],
            existing_agents=["coding", "testing"],
        )

        maestro = Maestro()
        decision, persist_result = maestro.evaluate_and_persist(
            context=context,
            session=in_memory_db,
        )

        assert persist_result.success == True
        assert persist_result.record.requires_agent_planning == False
        assert len(persist_result.record.required_capabilities) == 0

    def test_persist_decision_result_to_dict(self, in_memory_db, sample_decision):
        """PersistDecisionResult.to_dict() works correctly."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="test-project",
            session=in_memory_db,
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["success"] == True
        assert result_dict["decision_id"] is not None
        assert result_dict["record"] is not None
        assert result_dict["error"] is None


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_persist_empty_decision(self, in_memory_db):
        """Persisting minimal decision works."""
        from api.maestro import Maestro, AgentPlanningDecision

        minimal_decision = AgentPlanningDecision(
            requires_agent_planning=False,
            justification="No planning required",
        )

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=minimal_decision,
            project_name="minimal-project",
            session=in_memory_db,
        )

        assert result.success == True
        assert result.record.required_capabilities == []
        assert result.record.existing_capabilities == []

    def test_persist_decision_with_unicode_project_name(self, in_memory_db, sample_decision):
        """Persisting decision with unicode in project name works."""
        from api.maestro import Maestro

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=sample_decision,
            project_name="projekt-über-test",
            session=in_memory_db,
        )

        assert result.success == True
        assert result.record.project_name == "projekt-über-test"

    def test_persist_decision_with_long_justification(self, in_memory_db):
        """Persisting decision with long justification works."""
        from api.maestro import Maestro, AgentPlanningDecision

        long_justification = "A" * 10000  # 10K chars

        decision = AgentPlanningDecision(
            requires_agent_planning=True,
            justification=long_justification,
        )

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.success == True
        assert len(result.record.justification) == 10000

    def test_persist_decision_with_many_capabilities(self, in_memory_db):
        """Persisting decision with many capabilities works."""
        from api.maestro import Maestro, AgentPlanningDecision, CapabilityRequirement

        many_caps = [
            CapabilityRequirement(
                capability=f"cap_{i}",
                source=f"feature_{i}",
                keywords_matched=[f"keyword_{i}"],
            )
            for i in range(50)  # 50 capabilities
        ]

        decision = AgentPlanningDecision(
            requires_agent_planning=True,
            required_capabilities=many_caps,
            justification="Many capabilities",
        )

        maestro = Maestro()
        result = maestro.persist_decision(
            decision=decision,
            project_name="test-project",
            session=in_memory_db,
        )

        assert result.success == True
        assert len(result.record.required_capabilities) == 50


# =============================================================================
# Migration Tests
# =============================================================================

class TestMigration:
    """Test database migration for the new table."""

    def test_migration_function_exists(self):
        """Migration function exists in database.py."""
        from api.database import _migrate_add_agent_planning_decisions_table

        assert _migrate_add_agent_planning_decisions_table is not None

    def test_migration_creates_table_if_not_exists(self):
        """Migration creates table if it doesn't exist."""
        from api.database import _migrate_add_agent_planning_decisions_table, Base
        from api.agentspec_models import AgentPlanningDecisionRecord

        # Create engine without the table
        engine = create_engine("sqlite:///:memory:", echo=False)

        # Create only base Feature table (not agentspec tables)
        from api.database import Feature
        Feature.__table__.create(bind=engine)

        # Run migration
        _migrate_add_agent_planning_decisions_table(engine)

        # Check table exists
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agent_planning_decisions" in tables

        engine.dispose()

    def test_migration_is_idempotent(self):
        """Running migration twice doesn't cause errors."""
        from api.database import _migrate_add_agent_planning_decisions_table, Base
        from api.agentspec_models import AgentPlanningDecisionRecord

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)

        # Run migration twice
        _migrate_add_agent_planning_decisions_table(engine)
        _migrate_add_agent_planning_decisions_table(engine)  # Should not raise

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agent_planning_decisions" in tables

        engine.dispose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
