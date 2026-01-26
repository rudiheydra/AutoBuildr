"""
Feature #13: GET /api/agent-specs/:id Get Single AgentSpec
==========================================================

Tests for GET /api/projects/{project_name}/agent-specs/{spec_id} endpoint.

Verification Steps:
1. Define FastAPI route GET /api/agent-specs/{spec_id}
2. Validate spec_id is valid UUID format
3. Query AgentSpec by id with eager load of acceptance_spec relationship
4. Return 404 with message if not found
5. Return AgentSpecResponse with nested AcceptanceSpec
"""

import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestFeature13GetAgentSpec:
    """Test suite for Feature #13: GET /api/agent-specs/:id endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        # Import here to ensure path is set
        from server.routers.agent_specs import router, get_agent_spec, _is_valid_uuid
        from api.agentspec_models import AgentSpec, AcceptanceSpec
        from api.database import Base, create_database
        from server.schemas.agentspec import AgentSpecWithAcceptanceResponse, AcceptanceSpecResponse

        self.router = router
        self.get_agent_spec = get_agent_spec
        self._is_valid_uuid = _is_valid_uuid
        self.AgentSpec = AgentSpec
        self.AcceptanceSpec = AcceptanceSpec
        self.Base = Base
        self.create_database = create_database
        self.AgentSpecWithAcceptanceResponse = AgentSpecWithAcceptanceResponse
        self.AcceptanceSpecResponse = AcceptanceSpecResponse

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
            objective="Test objective for the agent",
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

    def _create_test_acceptance_spec(self, agent_spec_id: str) -> "AcceptanceSpec":
        """Create a test AcceptanceSpec linked to an AgentSpec."""
        acceptance = self.AcceptanceSpec(
            id=str(uuid.uuid4()),
            agent_spec_id=agent_spec_id,
            validators=[
                {"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": True}
            ],
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )
        self.session.add(acceptance)
        self.session.commit()
        return acceptance


class TestStep1FastAPIRouteDefinition(TestFeature13GetAgentSpec):
    """Step 1: Define FastAPI route GET /api/agent-specs/{spec_id}"""

    def test_route_exists_in_router(self):
        """Verify GET /{spec_id} route is registered in the router."""
        routes = [route for route in self.router.routes]
        get_spec_routes = [
            r for r in routes
            if hasattr(r, 'methods') and 'GET' in r.methods and '{spec_id}' in r.path
        ]
        assert len(get_spec_routes) == 1, "Should have exactly one GET /{spec_id} route"

    def test_route_has_correct_path(self):
        """Verify route path matches expected pattern."""
        routes = [r for r in self.router.routes if hasattr(r, 'path')]
        paths = [r.path for r in routes]
        # The router uses full path with project_name prefix
        assert any("{spec_id}" in path for path in paths), "Route path should contain {spec_id}"

    def test_route_uses_correct_response_model(self):
        """Verify route uses AgentSpecWithAcceptanceResponse model."""
        # Find GET route that contains {spec_id} but not /execute
        routes = [
            r for r in self.router.routes
            if hasattr(r, 'path') and '{spec_id}' in r.path and '/execute' not in r.path
            and hasattr(r, 'methods') and 'GET' in r.methods
        ]
        assert len(routes) == 1, f"Expected 1 GET route with {{spec_id}}, found {len(routes)}"
        route = routes[0]
        assert route.response_model == self.AgentSpecWithAcceptanceResponse


class TestStep2UUIDValidation(TestFeature13GetAgentSpec):
    """Step 2: Validate spec_id is valid UUID format"""

    def test_is_valid_uuid_accepts_valid_uuid(self):
        """Verify valid UUID is accepted."""
        valid_uuid = str(uuid.uuid4())
        assert self._is_valid_uuid(valid_uuid) is True

    def test_is_valid_uuid_rejects_invalid_uuid(self):
        """Verify invalid UUID is rejected."""
        assert self._is_valid_uuid("not-a-uuid") is False
        assert self._is_valid_uuid("12345") is False
        assert self._is_valid_uuid("") is False

    def test_is_valid_uuid_rejects_partial_uuid(self):
        """Verify partial UUID is rejected."""
        partial = str(uuid.uuid4())[:8]
        assert self._is_valid_uuid(partial) is False

    @pytest.mark.asyncio
    async def test_endpoint_returns_400_for_invalid_uuid(self):
        """Verify endpoint returns HTTP 400 for invalid UUID format."""
        from fastapi import HTTPException
        from unittest.mock import patch

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.get_agent_spec("test-project", "not-a-valid-uuid")
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 400
                    assert "Invalid UUID format" in e.detail


class TestStep3EagerLoadAcceptanceSpec(TestFeature13GetAgentSpec):
    """Step 3: Query AgentSpec by id with eager load of acceptance_spec relationship"""

    def test_agentspec_has_acceptance_spec_relationship(self):
        """Verify AgentSpec model has acceptance_spec relationship."""
        assert hasattr(self.AgentSpec, 'acceptance_spec'), "AgentSpec should have acceptance_spec relationship"

    @pytest.mark.asyncio
    async def test_endpoint_loads_acceptance_spec_relationship(self):
        """Verify endpoint eager loads acceptance_spec when present."""
        # Create test data
        spec = self._create_test_spec()
        acceptance = self._create_test_acceptance_spec(spec.id)

        from unittest.mock import patch

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.get_agent_spec("test-project", spec.id)

                assert result.acceptance_spec is not None, "acceptance_spec should be loaded"
                assert result.acceptance_spec.id == acceptance.id

    @pytest.mark.asyncio
    async def test_endpoint_handles_spec_without_acceptance(self):
        """Verify endpoint handles AgentSpec without AcceptanceSpec."""
        spec = self._create_test_spec()

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.get_agent_spec("test-project", spec.id)

                assert result.acceptance_spec is None, "acceptance_spec should be None when not present"


class TestStep4Return404IfNotFound(TestFeature13GetAgentSpec):
    """Step 4: Return 404 with message if not found"""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_spec(self):
        """Verify endpoint returns HTTP 404 for non-existent spec_id."""
        from fastapi import HTTPException

        nonexistent_id = str(uuid.uuid4())

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.get_agent_spec("test-project", nonexistent_id)
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 404
                    assert nonexistent_id in e.detail

    @pytest.mark.asyncio
    async def test_404_message_includes_spec_id(self):
        """Verify 404 error message includes the spec_id."""
        from fastapi import HTTPException

        nonexistent_id = str(uuid.uuid4())

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.get_agent_spec("test-project", nonexistent_id)
                except HTTPException as e:
                    assert "not found" in e.detail.lower()
                    assert nonexistent_id in e.detail


class TestStep5ResponseWithNestedAcceptanceSpec(TestFeature13GetAgentSpec):
    """Step 5: Return AgentSpecResponse with nested AcceptanceSpec"""

    @pytest.mark.asyncio
    async def test_response_includes_all_spec_fields(self):
        """Verify response includes all required AgentSpec fields."""
        spec = self._create_test_spec()

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.get_agent_spec("test-project", spec.id)

                # Verify all required fields are present
                assert result.id == spec.id
                assert result.name == spec.name
                assert result.display_name == spec.display_name
                assert result.icon == spec.icon
                assert result.spec_version == spec.spec_version
                assert result.objective == spec.objective
                assert result.task_type == spec.task_type
                assert result.context == spec.context
                assert result.tool_policy == spec.tool_policy
                assert result.max_turns == spec.max_turns
                assert result.timeout_seconds == spec.timeout_seconds
                assert result.priority == spec.priority
                assert result.tags == spec.tags

    @pytest.mark.asyncio
    async def test_response_includes_nested_acceptance_spec(self):
        """Verify response includes nested AcceptanceSpec with all fields."""
        spec = self._create_test_spec()
        acceptance = self._create_test_acceptance_spec(spec.id)

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.get_agent_spec("test-project", spec.id)

                assert result.acceptance_spec is not None
                assert result.acceptance_spec.id == acceptance.id
                assert result.acceptance_spec.agent_spec_id == spec.id
                assert result.acceptance_spec.validators == acceptance.validators
                assert result.acceptance_spec.gate_mode == acceptance.gate_mode
                assert result.acceptance_spec.retry_policy == acceptance.retry_policy
                assert result.acceptance_spec.max_retries == acceptance.max_retries

    @pytest.mark.asyncio
    async def test_response_model_is_correct_type(self):
        """Verify response is AgentSpecWithAcceptanceResponse type."""
        spec = self._create_test_spec()

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.get_agent_spec("test-project", spec.id)

                assert isinstance(result, self.AgentSpecWithAcceptanceResponse)


class TestEdgeCases(TestFeature13GetAgentSpec):
    """Test edge cases for the GET endpoint."""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_project(self):
        """Verify endpoint returns 404 for non-existent project."""
        from fastapi import HTTPException

        with patch('server.routers.agent_specs._get_project_path', side_effect=Exception("Not found")):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.get_agent_spec("nonexistent-project", str(uuid.uuid4()))
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 404
                    assert "not found" in e.detail.lower()

    @pytest.mark.asyncio
    async def test_handles_spec_with_null_optional_fields(self):
        """Verify endpoint handles AgentSpec with null optional fields."""
        spec_id = str(uuid.uuid4())
        spec = self.AgentSpec(
            id=spec_id,
            name="minimal-spec",
            display_name="Minimal Spec",
            icon=None,  # Optional field
            spec_version="v1",
            objective="Minimal objective text",
            task_type="coding",
            context=None,  # Optional field
            tool_policy={"policy_version": "v1", "allowed_tools": ["test"], "forbidden_patterns": [], "tool_hints": {}},
            max_turns=50,
            timeout_seconds=1800,
            parent_spec_id=None,  # Optional field
            source_feature_id=None,  # Optional field
            priority=500,
            tags=[],
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(spec)
        self.session.commit()

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.get_agent_spec("test-project", spec_id)

                assert result.id == spec_id
                assert result.icon is None
                assert result.context is None
                assert result.parent_spec_id is None
                assert result.source_feature_id is None


class TestSchemaDefinitions:
    """Tests for schema definitions."""

    def test_agentspec_with_acceptance_response_exists(self):
        """Verify AgentSpecWithAcceptanceResponse schema exists."""
        from server.schemas.agentspec import AgentSpecWithAcceptanceResponse
        assert AgentSpecWithAcceptanceResponse is not None

    def test_agentspec_with_acceptance_response_has_acceptance_spec_field(self):
        """Verify schema has acceptance_spec field."""
        from server.schemas.agentspec import AgentSpecWithAcceptanceResponse
        fields = AgentSpecWithAcceptanceResponse.model_fields
        assert 'acceptance_spec' in fields

    def test_acceptance_spec_field_is_optional(self):
        """Verify acceptance_spec field allows None."""
        from server.schemas.agentspec import AgentSpecWithAcceptanceResponse, AcceptanceSpecResponse
        from datetime import datetime

        # Create instance without acceptance_spec
        response = AgentSpecWithAcceptanceResponse(
            id="test-id",
            name="test-name",
            display_name="Test Name",
            icon=None,
            spec_version="v1",
            objective="Test objective",
            task_type="coding",
            context=None,
            tool_policy={"policy_version": "v1", "allowed_tools": ["test"], "forbidden_patterns": [], "tool_hints": {}},
            max_turns=50,
            timeout_seconds=1800,
            parent_spec_id=None,
            source_feature_id=None,
            created_at=datetime.now(timezone.utc),
            priority=100,
            tags=[],
            acceptance_spec=None,  # Should be allowed
        )
        assert response.acceptance_spec is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
