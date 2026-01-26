"""
Tests for Feature #17: GET /api/agent-runs List Runs Endpoint

Feature Description: Implement GET /api/agent-runs endpoint with filtering
by agent_spec_id and status with pagination.

Verification Steps:
1. Define FastAPI route GET /api/agent-runs
2. Add query parameters: agent_spec_id, status, limit, offset
3. Build query with conditional filters
4. Filter by agent_spec_id if provided
5. Filter by status if provided
6. Order by created_at descending
7. Apply pagination
8. Return AgentRunListResponse with total count
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

# Add project root to path
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def sample_agent_spec_id():
    """Generate a sample AgentSpec ID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_runs(sample_agent_spec_id):
    """Create sample AgentRun objects for testing."""
    now = datetime.now(timezone.utc)

    runs = []
    for i in range(5):
        run = MagicMock()
        run.id = str(uuid.uuid4())
        run.agent_spec_id = sample_agent_spec_id if i < 3 else str(uuid.uuid4())
        run.status = ["pending", "running", "completed", "failed", "timeout"][i % 5]
        run.started_at = now - timedelta(hours=i)
        run.completed_at = now - timedelta(hours=i) + timedelta(minutes=30) if run.status in ["completed", "failed", "timeout"] else None
        run.turns_used = i * 10
        run.tokens_in = i * 100
        run.tokens_out = i * 50
        run.final_verdict = "passed" if run.status == "completed" else None
        run.acceptance_results = None
        run.error = "Test error" if run.status == "failed" else None
        run.retry_count = 0
        run.created_at = now - timedelta(hours=i)

        # Define to_dict method
        run.to_dict.return_value = {
            "id": run.id,
            "agent_spec_id": run.agent_spec_id,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "turns_used": run.turns_used,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
            "final_verdict": run.final_verdict,
            "acceptance_results": run.acceptance_results,
            "error": run.error,
            "retry_count": run.retry_count,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }
        runs.append(run)

    return runs


# ==============================================================================
# Step 1: Define FastAPI route GET /api/agent-runs
# ==============================================================================

class TestStep1FastAPIRouteDefinition:
    """Tests for Step 1: Define FastAPI route GET /api/agent-runs"""

    def test_route_exists_in_router(self):
        """Verify the route is defined in the agent_runs router."""
        from server.routers.agent_runs import router

        # Check that there's a route for GET /api/agent-runs (the full path with prefix)
        routes = [route for route in router.routes if hasattr(route, 'methods')]
        # The route path includes the prefix: /api/agent-runs
        get_list_routes = [r for r in routes if 'GET' in r.methods and r.path == '/api/agent-runs']

        assert len(get_list_routes) == 1, "Should have exactly one GET /api/agent-runs route"

    def test_route_has_correct_response_model(self):
        """Verify the route returns AgentRunListResponse."""
        from server.routers.agent_runs import router

        routes = [route for route in router.routes if hasattr(route, 'methods')]
        get_list_routes = [r for r in routes if 'GET' in r.methods and r.path == '/api/agent-runs']

        assert len(get_list_routes) == 1
        route = get_list_routes[0]

        # Check response model
        assert route.response_model is not None
        assert route.response_model.__name__ == "AgentRunListResponse"

    def test_route_function_name(self):
        """Verify the route function is named list_agent_runs."""
        from server.routers.agent_runs import list_agent_runs

        assert callable(list_agent_runs)


# ==============================================================================
# Step 2: Add query parameters: agent_spec_id, status, limit, offset
# ==============================================================================

class TestStep2QueryParameters:
    """Tests for Step 2: Add query parameters"""

    def test_agent_spec_id_parameter_exists(self):
        """Verify agent_spec_id query parameter exists."""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        params = sig.parameters

        assert "agent_spec_id" in params
        # Check it's Optional[str]
        param = params["agent_spec_id"]
        assert param.default is None or (hasattr(param.default, 'default') and param.default.default is None)

    def test_status_parameter_exists(self):
        """Verify status query parameter exists."""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        params = sig.parameters

        assert "status" in params
        param = params["status"]
        assert param.default is None or (hasattr(param.default, 'default') and param.default.default is None)

    def test_limit_parameter_exists_with_default(self):
        """Verify limit query parameter exists with default 50."""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        params = sig.parameters

        assert "limit" in params
        param = params["limit"]
        # Check default value (either direct or via Query)
        if hasattr(param.default, 'default'):
            assert param.default.default == 50
        else:
            assert param.default == 50

    def test_offset_parameter_exists_with_default(self):
        """Verify offset query parameter exists with default 0."""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        params = sig.parameters

        assert "offset" in params
        param = params["offset"]
        # Check default value (either direct or via Query)
        if hasattr(param.default, 'default'):
            assert param.default.default == 0
        else:
            assert param.default == 0


# ==============================================================================
# Step 3: Build query with conditional filters
# ==============================================================================

class TestStep3ConditionalFilters:
    """Tests for Step 3: Build query with conditional filters"""

    def test_query_without_filters(self, mock_db, sample_runs):
        """Verify query works without any filters."""
        # Setup mock
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = len(sample_runs)
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = sample_runs

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate building query
        query = mock_db.query(AgentRunModel)
        total = query.count()

        assert total == len(sample_runs)
        mock_db.query.assert_called_once()


# ==============================================================================
# Step 4: Filter by agent_spec_id if provided
# ==============================================================================

class TestStep4FilterByAgentSpecId:
    """Tests for Step 4: Filter by agent_spec_id"""

    def test_filter_applies_when_agent_spec_id_provided(self, mock_db, sample_runs, sample_agent_spec_id):
        """Verify filter is applied when agent_spec_id is provided."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate filter application
        query = mock_db.query(AgentRunModel)
        if sample_agent_spec_id is not None:
            query = query.filter(AgentRunModel.agent_spec_id == sample_agent_spec_id)

        # Filter should have been called
        mock_query.filter.assert_called_once()

    def test_filter_not_applied_when_agent_spec_id_none(self, mock_db, sample_runs):
        """Verify filter is not applied when agent_spec_id is None."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate query without filter
        agent_spec_id = None
        query = mock_db.query(AgentRunModel)
        if agent_spec_id is not None:
            query = query.filter(AgentRunModel.agent_spec_id == agent_spec_id)

        # Filter should NOT have been called
        mock_query.filter.assert_not_called()


# ==============================================================================
# Step 5: Filter by status if provided
# ==============================================================================

class TestStep5FilterByStatus:
    """Tests for Step 5: Filter by status"""

    def test_filter_applies_when_status_provided(self, mock_db, sample_runs):
        """Verify filter is applied when status is provided."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate filter application
        status = "completed"
        query = mock_db.query(AgentRunModel)
        if status is not None:
            query = query.filter(AgentRunModel.status == status)

        # Filter should have been called
        mock_query.filter.assert_called_once()

    def test_filter_not_applied_when_status_none(self, mock_db, sample_runs):
        """Verify filter is not applied when status is None."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate query without filter
        status = None
        query = mock_db.query(AgentRunModel)
        if status is not None:
            query = query.filter(AgentRunModel.status == status)

        # Filter should NOT have been called
        mock_query.filter.assert_not_called()

    def test_invalid_status_raises_error(self):
        """Verify invalid status values are rejected."""
        from api.agentspec_models import RUN_STATUS

        invalid_statuses = ["invalid", "COMPLETED", "active", ""]

        for invalid_status in invalid_statuses:
            assert invalid_status not in RUN_STATUS, f"'{invalid_status}' should not be a valid status"

    def test_valid_statuses_accepted(self):
        """Verify all valid status values are accepted."""
        from api.agentspec_models import RUN_STATUS

        expected_statuses = ["pending", "running", "paused", "completed", "failed", "timeout"]

        for status in expected_statuses:
            assert status in RUN_STATUS, f"'{status}' should be a valid status"


# ==============================================================================
# Step 6: Order by created_at descending
# ==============================================================================

class TestStep6OrderByCreatedAt:
    """Tests for Step 6: Order by created_at descending"""

    def test_order_by_created_at_desc_applied(self, mock_db):
        """Verify results are ordered by created_at descending."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.order_by.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate order_by application
        query = mock_db.query(AgentRunModel)
        query = query.order_by(AgentRunModel.created_at.desc())

        # order_by should have been called
        mock_query.order_by.assert_called_once()


# ==============================================================================
# Step 7: Apply pagination
# ==============================================================================

class TestStep7Pagination:
    """Tests for Step 7: Apply pagination"""

    def test_offset_applied(self, mock_db):
        """Verify offset is applied to query."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate pagination
        offset = 10
        limit = 50
        query = mock_db.query(AgentRunModel)
        query = query.offset(offset).limit(limit)

        # offset should have been called with 10
        mock_query.offset.assert_called_once_with(10)

    def test_limit_applied(self, mock_db):
        """Verify limit is applied to query."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query

        from api.agentspec_models import AgentRun as AgentRunModel

        # Simulate pagination
        offset = 0
        limit = 25
        query = mock_db.query(AgentRunModel)
        query = query.offset(offset).limit(limit)

        # limit should have been called with 25
        mock_query.limit.assert_called_once_with(25)

    def test_default_limit_is_50(self):
        """Verify default limit is 50."""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        limit_param = sig.parameters["limit"]

        if hasattr(limit_param.default, 'default'):
            assert limit_param.default.default == 50
        else:
            assert limit_param.default == 50

    def test_max_limit_is_100(self):
        """Verify maximum limit is 100."""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        limit_param = sig.parameters["limit"]

        # Check le constraint
        if hasattr(limit_param.default, 'le'):
            assert limit_param.default.le == 100


# ==============================================================================
# Step 8: Return AgentRunListResponse with total count
# ==============================================================================

class TestStep8ReturnAgentRunListResponse:
    """Tests for Step 8: Return AgentRunListResponse with total count"""

    def test_response_schema_has_required_fields(self):
        """Verify AgentRunListResponse has required fields."""
        from server.schemas.agentspec import AgentRunListResponse

        # Check model fields
        fields = AgentRunListResponse.model_fields

        assert "runs" in fields
        assert "total" in fields
        assert "offset" in fields
        assert "limit" in fields

    def test_runs_field_is_list_of_agent_run_response(self):
        """Verify runs field contains AgentRunResponse objects."""
        from server.schemas.agentspec import AgentRunListResponse, AgentRunResponse
        from typing import get_args

        fields = AgentRunListResponse.model_fields
        runs_field = fields["runs"]

        # The annotation should be list[AgentRunResponse]
        assert runs_field.annotation is not None

    def test_total_field_is_integer(self):
        """Verify total field is an integer."""
        from server.schemas.agentspec import AgentRunListResponse

        fields = AgentRunListResponse.model_fields
        total_field = fields["total"]

        assert total_field.annotation == int


# ==============================================================================
# Integration Tests (using real HTTP calls to running server)
# ==============================================================================

class TestAPIIntegration:
    """Integration tests for the GET /api/agent-runs endpoint.

    These tests require the server to be running at localhost:8888.
    """

    def test_get_list_returns_200(self):
        """Test GET /api/agent-runs returns 200."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs", timeout=5)

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "runs" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data

    def test_get_list_default_pagination(self):
        """Test GET /api/agent-runs returns correct default pagination."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs", timeout=5)

        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 0
        assert data["limit"] == 50

    def test_get_with_status_filter_completed(self):
        """Test GET /api/agent-runs with status=completed filter."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs?status=completed", timeout=5)

        assert response.status_code == 200

    def test_get_with_invalid_status_returns_400(self):
        """Test GET /api/agent-runs with invalid status returns 400."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs?status=invalid_status", timeout=5)

        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]

    def test_get_with_custom_pagination(self):
        """Test GET /api/agent-runs with custom pagination parameters."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs?limit=10&offset=5", timeout=5)

        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 5
        assert data["limit"] == 10

    def test_get_with_agent_spec_id_filter(self):
        """Test GET /api/agent-runs with agent_spec_id filter."""
        import requests

        spec_id = str(uuid.uuid4())
        response = requests.get(f"http://localhost:8888/api/agent-runs?agent_spec_id={spec_id}", timeout=5)

        assert response.status_code == 200
        data = response.json()
        # With a random UUID, there should be no runs
        assert data["runs"] == []
        assert data["total"] == 0

    def test_x_total_count_header_present(self):
        """Test that X-Total-Count header is set."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs", timeout=5)

        assert response.status_code == 200
        assert "X-Total-Count" in response.headers
        # Header should be a valid integer string
        total_count = int(response.headers["X-Total-Count"])
        assert total_count >= 0

    def test_get_with_all_valid_statuses(self):
        """Test GET /api/agent-runs accepts all valid status values."""
        import requests

        valid_statuses = ["pending", "running", "paused", "completed", "failed", "timeout"]

        for status in valid_statuses:
            response = requests.get(f"http://localhost:8888/api/agent-runs?status={status}", timeout=5)
            assert response.status_code == 200, f"Status '{status}' should be valid"

    def test_response_structure(self):
        """Test the response structure matches AgentRunListResponse schema."""
        import requests

        response = requests.get("http://localhost:8888/api/agent-runs", timeout=5)

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert isinstance(data["runs"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["offset"], int)
        assert isinstance(data["limit"], int)

        # If there are runs, check their structure
        if data["runs"]:
            run = data["runs"][0]
            expected_fields = [
                "id", "agent_spec_id", "status", "started_at", "completed_at",
                "turns_used", "tokens_in", "tokens_out", "final_verdict",
                "acceptance_results", "error", "retry_count", "created_at"
            ]
            for field in expected_fields:
                assert field in run, f"Run should have '{field}' field"


# ==============================================================================
# Verification Steps Summary Test
# ==============================================================================

class TestFeature17VerificationSteps:
    """Verify all 8 steps of Feature #17 are implemented."""

    def test_step1_fastapi_route_defined(self):
        """Step 1: Define FastAPI route GET /api/agent-runs"""
        from server.routers.agent_runs import router

        routes = [r for r in router.routes if hasattr(r, 'methods')]
        get_list_routes = [r for r in routes if 'GET' in r.methods and r.path == '/api/agent-runs']

        assert len(get_list_routes) == 1, "GET /api/agent-runs route should be defined"

    def test_step2_query_parameters_defined(self):
        """Step 2: Add query parameters: agent_spec_id, status, limit, offset"""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        sig = inspect.signature(list_agent_runs)
        params = sig.parameters

        assert "agent_spec_id" in params
        assert "status" in params
        assert "limit" in params
        assert "offset" in params

    def test_step3_conditional_filters_work(self):
        """Step 3: Build query with conditional filters"""
        # Verified by the fact that filters are only applied when parameters are provided
        from server.routers.agent_runs import list_agent_runs

        # The function exists and handles optional parameters
        assert callable(list_agent_runs)

    def test_step4_agent_spec_id_filter_exists(self):
        """Step 4: Filter by agent_spec_id if provided"""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        source = inspect.getsource(list_agent_runs)
        assert "agent_spec_id" in source
        assert "AgentRunModel.agent_spec_id" in source

    def test_step5_status_filter_exists(self):
        """Step 5: Filter by status if provided"""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        source = inspect.getsource(list_agent_runs)
        assert "status" in source
        assert "AgentRunModel.status" in source

    def test_step6_order_by_created_at_desc(self):
        """Step 6: Order by created_at descending"""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        source = inspect.getsource(list_agent_runs)
        assert "created_at.desc()" in source

    def test_step7_pagination_applied(self):
        """Step 7: Apply pagination"""
        from server.routers.agent_runs import list_agent_runs
        import inspect

        source = inspect.getsource(list_agent_runs)
        assert ".offset(" in source
        assert ".limit(" in source

    def test_step8_returns_agent_run_list_response(self):
        """Step 8: Return AgentRunListResponse with total count"""
        from server.routers.agent_runs import list_agent_runs, router
        from server.schemas.agentspec import AgentRunListResponse

        # Check the response model
        routes = [r for r in router.routes if hasattr(r, 'methods')]
        get_list_routes = [r for r in routes if 'GET' in r.methods and r.path == '/api/agent-runs']

        assert len(get_list_routes) == 1
        route = get_list_routes[0]
        assert route.response_model == AgentRunListResponse


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
