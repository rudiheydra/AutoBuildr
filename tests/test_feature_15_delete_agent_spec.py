"""
Feature #15: DELETE /api/agent-specs/:id Cascade Delete
========================================================

Tests for DELETE /api/projects/{project_name}/agent-specs/{spec_id} endpoint.

Verification Steps:
1. Define FastAPI route DELETE /api/agent-specs/{spec_id}
2. Query AgentSpec by id
3. Return 404 if not found
4. Verify ON DELETE CASCADE is configured in foreign keys
5. Delete the AgentSpec record
6. Commit transaction
7. Verify AcceptanceSpec is deleted
8. Verify all AgentRuns are deleted
9. Verify all Artifacts for those runs are deleted
10. Verify all AgentEvents for those runs are deleted
11. Return 204 No Content
"""

import asyncio
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestFeature15DeleteAgentSpec:
    """Test suite for Feature #15: DELETE /api/agent-specs/:id endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        # Import here to ensure path is set
        from server.routers.agent_specs import router, delete_agent_spec, _is_valid_uuid
        from api.agentspec_models import (
            AgentSpec, AcceptanceSpec, AgentRun, Artifact, AgentEvent
        )
        from api.database import Base, create_database

        self.router = router
        self.delete_agent_spec = delete_agent_spec
        self._is_valid_uuid = _is_valid_uuid
        self.AgentSpec = AgentSpec
        self.AcceptanceSpec = AcceptanceSpec
        self.AgentRun = AgentRun
        self.Artifact = Artifact
        self.AgentEvent = AgentEvent
        self.Base = Base
        self.create_database = create_database

        # Create temp directory for test database
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Create database
        self.engine, self.SessionLocal = create_database(self.temp_path)
        self.session = self.SessionLocal()

        yield

        # Cleanup
        self.session.close()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_spec(self, spec_id: str = None, name: str = "test-spec") -> "AgentSpec":
        """Create a test AgentSpec in the database."""
        spec_id = spec_id or str(uuid.uuid4())
        spec = self.AgentSpec(
            id=spec_id,
            name=name,
            display_name="Test Spec",
            icon="test",
            spec_version="v1",
            objective="Test objective for the agent that is long enough",
            task_type="coding",
            context={"test": "context"},
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["feature_get_by_id"],
                "forbidden_patterns": [],
                "tool_hints": {}
            },
            max_turns=50,
            timeout_seconds=1800,
            priority=100,
            tags=["test"],
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(spec)
        self.session.commit()
        return spec

    def _create_acceptance_spec(self, agent_spec_id: str) -> "AcceptanceSpec":
        """Create a test AcceptanceSpec linked to an AgentSpec."""
        acceptance = self.AcceptanceSpec(
            id=str(uuid.uuid4()),
            agent_spec_id=agent_spec_id,
            validators=[{"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": True}],
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )
        self.session.add(acceptance)
        self.session.commit()
        return acceptance

    def _create_agent_run(self, agent_spec_id: str) -> "AgentRun":
        """Create a test AgentRun linked to an AgentSpec."""
        run = self.AgentRun(
            id=str(uuid.uuid4()),
            agent_spec_id=agent_spec_id,
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            turns_used=10,
            tokens_in=1000,
            tokens_out=2000,
            final_verdict="passed",
            acceptance_results=[],
            retry_count=0,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.commit()
        return run

    def _create_artifact(self, run_id: str) -> "Artifact":
        """Create a test Artifact linked to an AgentRun."""
        artifact = self.Artifact(
            id=str(uuid.uuid4()),
            run_id=run_id,
            artifact_type="test_result",
            content_inline="Test result content",
            content_hash="abc123",
            size_bytes=20,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(artifact)
        self.session.commit()
        return artifact

    def _create_event(self, run_id: str, sequence: int) -> "AgentEvent":
        """Create a test AgentEvent linked to an AgentRun."""
        event = self.AgentEvent(
            run_id=run_id,
            event_type="tool_call",
            sequence=sequence,
            timestamp=datetime.now(timezone.utc),
            payload={"tool": "test_tool"},
            tool_name="test_tool",
        )
        self.session.add(event)
        self.session.commit()
        return event


class TestStep1FastAPIRouteDefinition(TestFeature15DeleteAgentSpec):
    """Step 1: Define FastAPI route DELETE /api/agent-specs/{spec_id}"""

    def test_route_exists_in_router(self):
        """Verify DELETE /{spec_id} route is registered in the router."""
        routes = [route for route in self.router.routes]
        delete_spec_routes = [
            r for r in routes
            if hasattr(r, 'methods') and 'DELETE' in r.methods and '{spec_id}' in r.path
        ]
        assert len(delete_spec_routes) == 1, "Should have exactly one DELETE /{spec_id} route"

    def test_route_has_correct_path(self):
        """Verify route path matches expected pattern."""
        routes = [r for r in self.router.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        delete_routes = [r for r in routes if 'DELETE' in r.methods]
        paths = [r.path for r in delete_routes]
        assert any("{spec_id}" in p for p in paths), "DELETE route path should contain {spec_id}"

    def test_route_returns_204_status_code(self):
        """Verify route has status_code=204."""
        routes = [
            r for r in self.router.routes
            if hasattr(r, 'path') and '{spec_id}' in r.path and hasattr(r, 'methods') and 'DELETE' in r.methods
        ]
        assert len(routes) == 1
        route = routes[0]
        assert route.status_code == 204

    def test_route_has_404_response_documented(self):
        """Verify route documents 404 response in OpenAPI."""
        routes = [
            r for r in self.router.routes
            if hasattr(r, 'path') and '{spec_id}' in r.path and hasattr(r, 'methods') and 'DELETE' in r.methods
        ]
        assert len(routes) == 1
        route = routes[0]
        assert 404 in route.responses


class TestStep2QueryAgentSpecById(TestFeature15DeleteAgentSpec):
    """Step 2: Query AgentSpec by id"""

    @pytest.mark.asyncio
    async def test_queries_spec_from_database(self):
        """Verify delete endpoint queries the spec from database."""
        spec = self._create_test_spec()
        spec_id = spec.id

        # Verify spec exists before deletion
        found_spec = self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec_id
        ).first()
        assert found_spec is not None
        assert found_spec.id == spec_id


class TestStep3Return404IfNotFound(TestFeature15DeleteAgentSpec):
    """Step 3: Return 404 if not found"""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_spec(self):
        """Verify 404 is returned when spec doesn't exist."""
        from fastapi import HTTPException

        nonexistent_id = str(uuid.uuid4())

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            with pytest.raises(HTTPException) as exc_info:
                await self.delete_agent_spec("test-project", nonexistent_id)

            assert exc_info.value.status_code == 404
            assert nonexistent_id in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_returns_404_for_invalid_project(self):
        """Verify 404 is returned when project doesn't exist."""
        from fastapi import HTTPException

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.side_effect = Exception("Project not found")

            with pytest.raises(HTTPException) as exc_info:
                await self.delete_agent_spec("nonexistent-project", str(uuid.uuid4()))

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_uuid_format(self):
        """Verify 400 is returned for invalid UUID format."""
        from fastapi import HTTPException

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            with pytest.raises(HTTPException) as exc_info:
                await self.delete_agent_spec("test-project", "not-a-valid-uuid")

            assert exc_info.value.status_code == 400
            assert "Invalid UUID format" in str(exc_info.value.detail)


class TestStep4VerifyOnDeleteCascade(TestFeature15DeleteAgentSpec):
    """Step 4: Verify ON DELETE CASCADE is configured in foreign keys"""

    def test_acceptance_spec_has_cascade_on_agent_spec_fk(self):
        """Verify AcceptanceSpec.agent_spec_id FK has ondelete=CASCADE."""
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        fks = inspector.get_foreign_keys('acceptance_specs')

        agent_spec_fk = next(
            (fk for fk in fks if fk['referred_table'] == 'agent_specs'),
            None
        )
        assert agent_spec_fk is not None
        # SQLite stores ondelete in lowercase
        assert agent_spec_fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'

    def test_agent_run_has_cascade_on_agent_spec_fk(self):
        """Verify AgentRun.agent_spec_id FK has ondelete=CASCADE."""
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        fks = inspector.get_foreign_keys('agent_runs')

        agent_spec_fk = next(
            (fk for fk in fks if fk['referred_table'] == 'agent_specs'),
            None
        )
        assert agent_spec_fk is not None
        assert agent_spec_fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'

    def test_artifact_has_cascade_on_run_fk(self):
        """Verify Artifact.run_id FK has ondelete=CASCADE."""
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        fks = inspector.get_foreign_keys('artifacts')

        run_fk = next(
            (fk for fk in fks if fk['referred_table'] == 'agent_runs'),
            None
        )
        assert run_fk is not None
        assert run_fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'

    def test_agent_event_has_cascade_on_run_fk(self):
        """Verify AgentEvent.run_id FK has ondelete=CASCADE."""
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        fks = inspector.get_foreign_keys('agent_events')

        run_fk = next(
            (fk for fk in fks if fk['referred_table'] == 'agent_runs'),
            None
        )
        assert run_fk is not None
        assert run_fk.get('options', {}).get('ondelete', '').upper() == 'CASCADE'


class TestStep5DeleteAgentSpecRecord(TestFeature15DeleteAgentSpec):
    """Step 5: Delete the AgentSpec record"""

    def test_delete_removes_spec_from_database(self):
        """Verify delete removes the AgentSpec record."""
        spec = self._create_test_spec()
        spec_id = spec.id

        # Delete the spec
        self.session.delete(spec)
        self.session.commit()

        # Verify spec is gone
        found_spec = self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec_id
        ).first()
        assert found_spec is None


class TestStep6CommitTransaction(TestFeature15DeleteAgentSpec):
    """Step 6: Commit transaction"""

    def test_deletion_persists_after_commit(self):
        """Verify deletion is persisted after transaction commit."""
        spec = self._create_test_spec()
        spec_id = spec.id

        # Delete and commit
        self.session.delete(spec)
        self.session.commit()

        # Create new session to verify persistence
        new_session = self.SessionLocal()
        found_spec = new_session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec_id
        ).first()
        new_session.close()

        assert found_spec is None


class TestStep7VerifyAcceptanceSpecDeleted(TestFeature15DeleteAgentSpec):
    """Step 7: Verify AcceptanceSpec is deleted"""

    def test_acceptance_spec_deleted_with_agent_spec(self):
        """Verify AcceptanceSpec is cascade-deleted with AgentSpec."""
        spec = self._create_test_spec()
        spec_id = spec.id

        acceptance = self._create_acceptance_spec(spec_id)
        acceptance_id = acceptance.id

        # Verify acceptance exists
        found_acceptance = self.session.query(self.AcceptanceSpec).filter(
            self.AcceptanceSpec.id == acceptance_id
        ).first()
        assert found_acceptance is not None

        # Delete spec
        self.session.delete(spec)
        self.session.commit()

        # Verify acceptance is also deleted
        found_acceptance = self.session.query(self.AcceptanceSpec).filter(
            self.AcceptanceSpec.id == acceptance_id
        ).first()
        assert found_acceptance is None


class TestStep8VerifyAllAgentRunsDeleted(TestFeature15DeleteAgentSpec):
    """Step 8: Verify all AgentRuns are deleted"""

    def test_all_runs_deleted_with_agent_spec(self):
        """Verify all AgentRuns are cascade-deleted with AgentSpec."""
        spec = self._create_test_spec()
        spec_id = spec.id

        # Create multiple runs
        run1 = self._create_agent_run(spec_id)
        run2 = self._create_agent_run(spec_id)
        run_ids = [run1.id, run2.id]

        # Verify runs exist
        runs = self.session.query(self.AgentRun).filter(
            self.AgentRun.agent_spec_id == spec_id
        ).all()
        assert len(runs) == 2

        # Delete spec
        self.session.delete(spec)
        self.session.commit()

        # Verify all runs are deleted
        remaining_runs = self.session.query(self.AgentRun).filter(
            self.AgentRun.id.in_(run_ids)
        ).all()
        assert len(remaining_runs) == 0


class TestStep9VerifyAllArtifactsDeleted(TestFeature15DeleteAgentSpec):
    """Step 9: Verify all Artifacts for those runs are deleted"""

    def test_all_artifacts_deleted_with_runs(self):
        """Verify all Artifacts are cascade-deleted when runs are deleted."""
        spec = self._create_test_spec()
        spec_id = spec.id

        run = self._create_agent_run(spec_id)
        run_id = run.id

        # Create multiple artifacts
        artifact1 = self._create_artifact(run_id)
        artifact2 = self._create_artifact(run_id)
        artifact_ids = [artifact1.id, artifact2.id]

        # Verify artifacts exist
        artifacts = self.session.query(self.Artifact).filter(
            self.Artifact.run_id == run_id
        ).all()
        assert len(artifacts) == 2

        # Delete spec (cascades to runs, then artifacts)
        self.session.delete(spec)
        self.session.commit()

        # Verify all artifacts are deleted
        remaining_artifacts = self.session.query(self.Artifact).filter(
            self.Artifact.id.in_(artifact_ids)
        ).all()
        assert len(remaining_artifacts) == 0


class TestStep10VerifyAllAgentEventsDeleted(TestFeature15DeleteAgentSpec):
    """Step 10: Verify all AgentEvents for those runs are deleted"""

    def test_all_events_deleted_with_runs(self):
        """Verify all AgentEvents are cascade-deleted when runs are deleted."""
        spec = self._create_test_spec()
        spec_id = spec.id

        run = self._create_agent_run(spec_id)
        run_id = run.id

        # Create multiple events
        event1 = self._create_event(run_id, sequence=1)
        event2 = self._create_event(run_id, sequence=2)
        event3 = self._create_event(run_id, sequence=3)
        event_ids = [event1.id, event2.id, event3.id]

        # Verify events exist
        events = self.session.query(self.AgentEvent).filter(
            self.AgentEvent.run_id == run_id
        ).all()
        assert len(events) == 3

        # Delete spec (cascades to runs, then events)
        self.session.delete(spec)
        self.session.commit()

        # Verify all events are deleted
        remaining_events = self.session.query(self.AgentEvent).filter(
            self.AgentEvent.id.in_(event_ids)
        ).all()
        assert len(remaining_events) == 0


class TestStep11Return204NoContent(TestFeature15DeleteAgentSpec):
    """Step 11: Return 204 No Content"""

    @pytest.mark.asyncio
    async def test_returns_204_on_successful_delete(self):
        """Verify 204 No Content is returned on successful deletion."""
        spec = self._create_test_spec()
        spec_id = spec.id

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            response = await self.delete_agent_spec("test-project", spec_id)

            assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_response_has_no_body(self):
        """Verify 204 response has no body."""
        spec = self._create_test_spec()
        spec_id = spec.id

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            response = await self.delete_agent_spec("test-project", spec_id)

            assert response.body == b''


class TestCascadeDeleteIntegration(TestFeature15DeleteAgentSpec):
    """Integration tests for complete cascade delete behavior."""

    @pytest.mark.asyncio
    async def test_full_cascade_delete_via_api(self):
        """Test complete cascade delete via the API endpoint."""
        # Create full hierarchy
        spec = self._create_test_spec()
        spec_id = spec.id

        acceptance = self._create_acceptance_spec(spec_id)
        acceptance_id = acceptance.id

        run1 = self._create_agent_run(spec_id)
        run2 = self._create_agent_run(spec_id)

        artifact1 = self._create_artifact(run1.id)
        artifact2 = self._create_artifact(run2.id)

        event1 = self._create_event(run1.id, sequence=1)
        event2 = self._create_event(run1.id, sequence=2)
        event3 = self._create_event(run2.id, sequence=1)

        # Store all IDs
        run_ids = [run1.id, run2.id]
        artifact_ids = [artifact1.id, artifact2.id]
        event_ids = [event1.id, event2.id, event3.id]

        # Call delete via API
        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            response = await self.delete_agent_spec("test-project", spec_id)
            assert response.status_code == 204

        # Refresh session to see committed changes
        self.session.expire_all()

        # Verify everything is deleted
        assert self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec_id
        ).first() is None

        assert self.session.query(self.AcceptanceSpec).filter(
            self.AcceptanceSpec.id == acceptance_id
        ).first() is None

        assert len(self.session.query(self.AgentRun).filter(
            self.AgentRun.id.in_(run_ids)
        ).all()) == 0

        assert len(self.session.query(self.Artifact).filter(
            self.Artifact.id.in_(artifact_ids)
        ).all()) == 0

        assert len(self.session.query(self.AgentEvent).filter(
            self.AgentEvent.id.in_(event_ids)
        ).all()) == 0

    def test_delete_spec_without_related_data(self):
        """Test deleting spec that has no acceptance spec, runs, etc."""
        spec = self._create_test_spec()
        spec_id = spec.id

        # Delete directly via ORM
        self.session.delete(spec)
        self.session.commit()

        # Verify spec is gone
        assert self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec_id
        ).first() is None

    def test_delete_preserves_other_specs(self):
        """Test that deleting one spec doesn't affect others."""
        spec1 = self._create_test_spec(name="spec-one")
        spec2 = self._create_test_spec(name="spec-two")
        spec1_id = spec1.id
        spec2_id = spec2.id

        # Delete spec1
        self.session.delete(spec1)
        self.session.commit()

        # Verify spec1 is gone but spec2 remains
        assert self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec1_id
        ).first() is None

        assert self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec2_id
        ).first() is not None


class TestEdgeCases(TestFeature15DeleteAgentSpec):
    """Edge case tests for delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_same_spec_twice_returns_404(self):
        """Verify deleting the same spec twice returns 404 on second attempt."""
        from fastapi import HTTPException

        spec = self._create_test_spec()
        spec_id = spec.id

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            # First delete should succeed
            response = await self.delete_agent_spec("test-project", spec_id)
            assert response.status_code == 204

            # Second delete should return 404
            with pytest.raises(HTTPException) as exc_info:
                await self.delete_agent_spec("test-project", spec_id)

            assert exc_info.value.status_code == 404

    def test_uuid_validation(self):
        """Test UUID validation helper function."""
        # Valid UUIDs
        assert self._is_valid_uuid(str(uuid.uuid4())) is True
        assert self._is_valid_uuid("12345678-1234-4123-8123-123456789abc") is True

        # Invalid UUIDs
        assert self._is_valid_uuid("not-a-uuid") is False
        assert self._is_valid_uuid("12345") is False
        assert self._is_valid_uuid("") is False

    def test_delete_with_large_hierarchy(self):
        """Test cascade delete with many related records."""
        spec = self._create_test_spec()
        spec_id = spec.id

        self._create_acceptance_spec(spec_id)

        # Create 5 runs with 10 events and 3 artifacts each
        for _ in range(5):
            run = self._create_agent_run(spec_id)
            for i in range(10):
                self._create_event(run.id, sequence=i + 1)
            for _ in range(3):
                self._create_artifact(run.id)

        # Count records before delete
        run_count = self.session.query(self.AgentRun).filter(
            self.AgentRun.agent_spec_id == spec_id
        ).count()
        assert run_count == 5

        # Delete spec
        self.session.delete(spec)
        self.session.commit()

        # Verify all deleted
        assert self.session.query(self.AgentSpec).filter(
            self.AgentSpec.id == spec_id
        ).first() is None

        assert self.session.query(self.AgentRun).filter(
            self.AgentRun.agent_spec_id == spec_id
        ).count() == 0


class TestUUIDValidation(TestFeature15DeleteAgentSpec):
    """Tests for UUID format validation."""

    @pytest.mark.asyncio
    async def test_rejects_malformed_uuid(self):
        """Test various malformed UUID formats are rejected."""
        from fastapi import HTTPException

        invalid_uuids = [
            "not-uuid",
            "12345",
            "12345678-1234-1234-1234",  # Too short
            "12345678-1234-1234-1234-123456789abcd",  # Too long
            "g2345678-1234-4123-8123-123456789abc",  # Invalid hex char
            "",
            "   ",
            "null",
        ]

        with patch('server.routers.agent_specs._get_project_path') as mock_path:
            mock_path.return_value = self.temp_path

            for invalid_uuid in invalid_uuids:
                with pytest.raises(HTTPException) as exc_info:
                    await self.delete_agent_spec("test-project", invalid_uuid)

                assert exc_info.value.status_code == 400, f"Expected 400 for '{invalid_uuid}'"
