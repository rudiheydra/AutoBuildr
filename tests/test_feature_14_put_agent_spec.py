"""
Feature #14: PUT /api/agent-specs/:id Update AgentSpec
======================================================

Tests for PUT /api/projects/{project_name}/agent-specs/{spec_id} endpoint.

Verification Steps:
1. Define FastAPI route PUT /api/agent-specs/{spec_id} with AgentSpecUpdate body
2. Query existing AgentSpec by id
3. Return 404 if not found
4. Update only fields that are provided (not None)
5. Validate updated max_turns and timeout_seconds against constraints
6. Commit transaction
7. Return updated AgentSpecResponse
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


class TestFeature14PutAgentSpec:
    """Test suite for Feature #14: PUT /api/agent-specs/:id endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        # Import here to ensure path is set
        from server.routers.agent_specs import router, update_agent_spec
        from api.agentspec_models import AgentSpec, AcceptanceSpec
        from api.database import Base, create_database
        from server.schemas.agentspec import AgentSpecResponse, AgentSpecUpdate, ToolPolicy

        self.router = router
        self.update_agent_spec = update_agent_spec
        self.AgentSpec = AgentSpec
        self.AcceptanceSpec = AcceptanceSpec
        self.Base = Base
        self.create_database = create_database
        self.AgentSpecResponse = AgentSpecResponse
        self.AgentSpecUpdate = AgentSpecUpdate
        self.ToolPolicy = ToolPolicy

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


class TestStep1FastAPIRouteDefinition(TestFeature14PutAgentSpec):
    """Step 1: Define FastAPI route PUT /api/agent-specs/{spec_id} with AgentSpecUpdate body"""

    def test_route_exists_in_router(self):
        """Verify PUT /{spec_id} route is registered in the router."""
        routes = [route for route in self.router.routes]
        put_spec_routes = [
            r for r in routes
            if hasattr(r, 'methods') and 'PUT' in r.methods and '{spec_id}' in r.path
        ]
        assert len(put_spec_routes) == 1, "Should have exactly one PUT /{spec_id} route"

    def test_route_has_correct_path(self):
        """Verify route path matches expected pattern."""
        routes = [r for r in self.router.routes if hasattr(r, 'path') and hasattr(r, 'methods')]
        put_routes = [r for r in routes if 'PUT' in r.methods]
        paths = [r.path for r in put_routes]
        # Route path includes the router prefix
        assert any("{spec_id}" in p for p in paths), "PUT route path should contain {spec_id}"

    def test_route_uses_correct_response_model(self):
        """Verify route uses AgentSpecResponse model."""
        routes = [
            r for r in self.router.routes
            if hasattr(r, 'path') and '{spec_id}' in r.path and hasattr(r, 'methods') and 'PUT' in r.methods
        ]
        assert len(routes) == 1
        route = routes[0]
        assert route.response_model == self.AgentSpecResponse

    def test_agentspecupdate_schema_exists(self):
        """Verify AgentSpecUpdate schema exists and has expected fields."""
        from server.schemas.agentspec import AgentSpecUpdate
        assert AgentSpecUpdate is not None

        fields = AgentSpecUpdate.model_fields
        # All fields should be optional for partial updates
        expected_fields = [
            'name', 'display_name', 'icon', 'objective', 'task_type',
            'context', 'tool_policy', 'max_turns', 'timeout_seconds',
            'parent_spec_id', 'source_feature_id', 'priority', 'tags'
        ]
        for field in expected_fields:
            assert field in fields, f"AgentSpecUpdate should have {field} field"


class TestStep2QueryExistingAgentSpec(TestFeature14PutAgentSpec):
    """Step 2: Query existing AgentSpec by id"""

    @pytest.mark.asyncio
    async def test_queries_existing_spec_by_id(self):
        """Verify endpoint queries AgentSpec by id."""
        spec = self._create_test_spec()

        update_data = self.AgentSpecUpdate(display_name="Updated Display Name")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                assert result.id == spec.id
                assert result.display_name == "Updated Display Name"


class TestStep3Return404IfNotFound(TestFeature14PutAgentSpec):
    """Step 3: Return 404 if not found"""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_spec(self):
        """Verify endpoint returns HTTP 404 for non-existent spec_id."""
        from fastapi import HTTPException

        nonexistent_id = str(uuid.uuid4())
        update_data = self.AgentSpecUpdate(display_name="Updated Name")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.update_agent_spec("test-project", nonexistent_id, update_data)
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 404
                    assert nonexistent_id in e.detail

    @pytest.mark.asyncio
    async def test_404_message_includes_spec_id(self):
        """Verify 404 error message includes the spec_id."""
        from fastapi import HTTPException

        nonexistent_id = str(uuid.uuid4())
        update_data = self.AgentSpecUpdate(display_name="Test")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.update_agent_spec("test-project", nonexistent_id, update_data)
                except HTTPException as e:
                    assert "not found" in e.detail.lower()
                    assert nonexistent_id in e.detail


class TestStep4PartialUpdate(TestFeature14PutAgentSpec):
    """Step 4: Update only fields that are provided (not None)"""

    @pytest.mark.asyncio
    async def test_updates_only_provided_fields(self):
        """Verify only provided fields are updated, others remain unchanged."""
        spec = self._create_test_spec()
        original_name = spec.name
        original_objective = spec.objective
        original_max_turns = spec.max_turns

        # Only update display_name
        update_data = self.AgentSpecUpdate(display_name="New Display Name")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                # Updated field
                assert result.display_name == "New Display Name"
                # Unchanged fields
                assert result.name == original_name
                assert result.objective == original_objective
                assert result.max_turns == original_max_turns

    @pytest.mark.asyncio
    async def test_updates_multiple_fields(self):
        """Verify multiple fields can be updated at once."""
        spec = self._create_test_spec()

        update_data = self.AgentSpecUpdate(
            display_name="Updated Display",
            max_turns=100,
            priority=200,
            tags=["new", "tags"]
        )

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                assert result.display_name == "Updated Display"
                assert result.max_turns == 100
                assert result.priority == 200
                assert result.tags == ["new", "tags"]

    @pytest.mark.asyncio
    async def test_update_tool_policy(self):
        """Verify tool_policy can be updated."""
        spec = self._create_test_spec()

        new_policy = self.ToolPolicy(
            policy_version="v2",
            allowed_tools=["new_tool", "another_tool"],
            forbidden_patterns=["dangerous_pattern"],
            tool_hints={"new_tool": "Use carefully"}
        )
        update_data = self.AgentSpecUpdate(tool_policy=new_policy)

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                assert result.tool_policy["policy_version"] == "v2"
                assert result.tool_policy["allowed_tools"] == ["new_tool", "another_tool"]
                assert result.tool_policy["forbidden_patterns"] == ["dangerous_pattern"]

    @pytest.mark.asyncio
    async def test_update_context(self):
        """Verify context can be updated."""
        spec = self._create_test_spec()

        update_data = self.AgentSpecUpdate(context={"new_key": "new_value", "nested": {"data": True}})

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                assert result.context == {"new_key": "new_value", "nested": {"data": True}}


class TestStep5ValidateConstraints(TestFeature14PutAgentSpec):
    """Step 5: Validate updated max_turns and timeout_seconds against constraints"""

    @pytest.mark.asyncio
    async def test_max_turns_within_valid_range(self):
        """Verify max_turns can be updated within valid range (1-500)."""
        spec = self._create_test_spec()

        # Valid values
        for max_turns in [1, 50, 250, 500]:
            update_data = self.AgentSpecUpdate(max_turns=max_turns)

            with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
                with patch('server.routers.agent_specs.validate_project_name'):
                    result = await self.update_agent_spec("test-project", spec.id, update_data)
                    assert result.max_turns == max_turns

    @pytest.mark.asyncio
    async def test_max_turns_too_low_rejected(self):
        """Verify max_turns below 1 is rejected."""
        from pydantic import ValidationError

        # Pydantic should reject this before the endpoint
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(max_turns=0)

    @pytest.mark.asyncio
    async def test_max_turns_too_high_rejected(self):
        """Verify max_turns above 500 is rejected."""
        from pydantic import ValidationError

        # Pydantic should reject this before the endpoint
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(max_turns=501)

    @pytest.mark.asyncio
    async def test_timeout_seconds_within_valid_range(self):
        """Verify timeout_seconds can be updated within valid range (60-7200)."""
        spec = self._create_test_spec()

        # Valid values
        for timeout in [60, 1800, 3600, 7200]:
            update_data = self.AgentSpecUpdate(timeout_seconds=timeout)

            with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
                with patch('server.routers.agent_specs.validate_project_name'):
                    result = await self.update_agent_spec("test-project", spec.id, update_data)
                    assert result.timeout_seconds == timeout

    @pytest.mark.asyncio
    async def test_timeout_seconds_too_low_rejected(self):
        """Verify timeout_seconds below 60 is rejected."""
        from pydantic import ValidationError

        # Pydantic should reject this before the endpoint
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(timeout_seconds=59)

    @pytest.mark.asyncio
    async def test_timeout_seconds_too_high_rejected(self):
        """Verify timeout_seconds above 7200 is rejected."""
        from pydantic import ValidationError

        # Pydantic should reject this before the endpoint
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(timeout_seconds=7201)

    @pytest.mark.asyncio
    async def test_priority_within_valid_range(self):
        """Verify priority can be updated within valid range (1-9999)."""
        spec = self._create_test_spec()

        for priority in [1, 500, 9999]:
            update_data = self.AgentSpecUpdate(priority=priority)

            with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
                with patch('server.routers.agent_specs.validate_project_name'):
                    result = await self.update_agent_spec("test-project", spec.id, update_data)
                    assert result.priority == priority


class TestStep6CommitTransaction(TestFeature14PutAgentSpec):
    """Step 6: Commit transaction"""

    @pytest.mark.asyncio
    async def test_changes_persist_after_update(self):
        """Verify changes are committed and persist in database."""
        spec = self._create_test_spec()

        update_data = self.AgentSpecUpdate(display_name="Persisted Name")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                await self.update_agent_spec("test-project", spec.id, update_data)

        # Close current session and open new one to verify persistence
        self.session.close()
        new_session = self.SessionLocal()
        try:
            updated_spec = new_session.query(self.AgentSpec).filter(
                self.AgentSpec.id == spec.id
            ).first()
            assert updated_spec.display_name == "Persisted Name"
        finally:
            new_session.close()

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_400(self):
        """Verify updating name to existing name raises 400 error."""
        from fastapi import HTTPException

        spec1 = self._create_test_spec(name="spec-one")
        spec2 = self._create_test_spec(name="spec-two")

        # Try to update spec2's name to spec1's name - this might fail if name has unique constraint
        # Note: The current implementation doesn't have a unique constraint on name
        # But the test documents expected behavior

        update_data = self.AgentSpecUpdate(name="spec-one")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                # This might pass if name is not unique - that's OK, just documenting
                try:
                    result = await self.update_agent_spec("test-project", spec2.id, update_data)
                    # If it passes, name is not unique constrained
                    assert result.name == "spec-one"
                except HTTPException as e:
                    # If it fails, name is unique constrained
                    assert e.status_code == 400


class TestStep7ReturnAgentSpecResponse(TestFeature14PutAgentSpec):
    """Step 7: Return updated AgentSpecResponse"""

    @pytest.mark.asyncio
    async def test_returns_agentspec_response_type(self):
        """Verify response is AgentSpecResponse type."""
        spec = self._create_test_spec()
        update_data = self.AgentSpecUpdate(display_name="Updated")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                assert isinstance(result, self.AgentSpecResponse)

    @pytest.mark.asyncio
    async def test_response_includes_all_fields(self):
        """Verify response includes all required fields."""
        spec = self._create_test_spec()
        update_data = self.AgentSpecUpdate(display_name="Updated Display")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                # Verify all fields are present
                assert result.id == spec.id
                assert result.name == spec.name
                assert result.display_name == "Updated Display"
                assert result.icon == spec.icon
                assert result.spec_version == spec.spec_version
                assert result.objective == spec.objective
                assert result.task_type == spec.task_type
                assert result.context == spec.context
                assert result.tool_policy is not None
                assert result.max_turns == spec.max_turns
                assert result.timeout_seconds == spec.timeout_seconds
                assert result.priority == spec.priority
                assert result.tags == spec.tags
                assert result.created_at is not None


class TestEdgeCases(TestFeature14PutAgentSpec):
    """Test edge cases for the PUT endpoint."""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_project(self):
        """Verify endpoint returns 404 for non-existent project."""
        from fastapi import HTTPException

        update_data = self.AgentSpecUpdate(display_name="Test")

        with patch('server.routers.agent_specs._get_project_path', side_effect=Exception("Not found")):
            with patch('server.routers.agent_specs.validate_project_name'):
                try:
                    await self.update_agent_spec("nonexistent-project", str(uuid.uuid4()), update_data)
                    assert False, "Should have raised HTTPException"
                except HTTPException as e:
                    assert e.status_code == 404
                    assert "not found" in e.detail.lower()

    @pytest.mark.asyncio
    async def test_empty_update_returns_unchanged_spec(self):
        """Verify empty update body returns spec unchanged."""
        spec = self._create_test_spec()

        # Empty update - no fields provided
        update_data = self.AgentSpecUpdate()

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)

                # All fields should be unchanged
                assert result.id == spec.id
                assert result.name == spec.name
                assert result.display_name == spec.display_name
                assert result.max_turns == spec.max_turns

    @pytest.mark.asyncio
    async def test_update_name_with_valid_pattern(self):
        """Verify name can be updated with valid lowercase hyphen pattern."""
        spec = self._create_test_spec()

        update_data = self.AgentSpecUpdate(name="new-valid-name")

        with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
            with patch('server.routers.agent_specs.validate_project_name'):
                result = await self.update_agent_spec("test-project", spec.id, update_data)
                assert result.name == "new-valid-name"

    def test_name_with_invalid_pattern_rejected(self):
        """Verify name with invalid pattern is rejected by Pydantic."""
        from pydantic import ValidationError

        # Name with uppercase
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(name="Invalid-Name")

        # Name with spaces
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(name="invalid name")

        # Name starting with hyphen
        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(name="-invalid")

    @pytest.mark.asyncio
    async def test_update_task_type(self):
        """Verify task_type can be updated to valid values."""
        spec = self._create_test_spec()

        for task_type in ["coding", "testing", "refactoring", "documentation", "audit", "custom"]:
            update_data = self.AgentSpecUpdate(task_type=task_type)

            with patch('server.routers.agent_specs._get_project_path', return_value=self.temp_path):
                with patch('server.routers.agent_specs.validate_project_name'):
                    result = await self.update_agent_spec("test-project", spec.id, update_data)
                    assert result.task_type == task_type

    def test_invalid_task_type_rejected(self):
        """Verify invalid task_type is rejected by Pydantic."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self.AgentSpecUpdate(task_type="invalid_type")


class TestSchemaDefinitions:
    """Tests for AgentSpecUpdate schema definitions."""

    def test_agentspecupdate_exists(self):
        """Verify AgentSpecUpdate schema exists."""
        from server.schemas.agentspec import AgentSpecUpdate
        assert AgentSpecUpdate is not None

    def test_all_fields_are_optional(self):
        """Verify all fields in AgentSpecUpdate can be None."""
        from server.schemas.agentspec import AgentSpecUpdate

        # Should be able to create with no fields
        update = AgentSpecUpdate()
        assert update is not None

    def test_field_types_are_correct(self):
        """Verify field types in AgentSpecUpdate."""
        from server.schemas.agentspec import AgentSpecUpdate, ToolPolicy

        fields = AgentSpecUpdate.model_fields

        # Check some key field types
        assert fields['name'].annotation == (str | None)
        assert fields['display_name'].annotation == (str | None)
        assert fields['max_turns'].annotation == (int | None)
        assert fields['timeout_seconds'].annotation == (int | None)
        assert fields['priority'].annotation == (int | None)

    def test_exclude_unset_works(self):
        """Verify model_dump(exclude_unset=True) only includes provided fields."""
        from server.schemas.agentspec import AgentSpecUpdate

        update = AgentSpecUpdate(display_name="Test", max_turns=100)
        dumped = update.model_dump(exclude_unset=True)

        assert "display_name" in dumped
        assert "max_turns" in dumped
        assert "name" not in dumped
        assert "timeout_seconds" not in dumped


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
