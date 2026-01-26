#!/usr/bin/env python3
"""
Verification script for Feature #17: GET /api/agent-runs List Runs Endpoint
============================================================================

This script verifies that the GET /api/agent-runs endpoint meets all requirements
by checking the source code and inspecting the implementation.

Feature Requirements:
1. Define FastAPI route GET /api/agent-runs
2. Add query parameters: agent_spec_id, status, limit, offset
3. Build query with conditional filters
4. Filter by agent_spec_id if provided
5. Filter by status if provided
6. Order by created_at descending
7. Apply pagination
8. Return AgentRunListResponse with total count

Dependencies: #3 (AgentRun SQLite Table Schema), #9 (AgentRun Pydantic Response Schema)
"""

import inspect
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def read_file(path: Path) -> str:
    """Read file contents."""
    with open(path, 'r') as f:
        return f.read()


def verify_step_1():
    """Step 1: Define FastAPI route GET /api/agent-runs"""
    print("\n[Step 1] Verify FastAPI route GET /api/agent-runs is defined")

    from server.routers.agent_runs import router

    # Check that there's a route for GET /api/agent-runs
    routes = [route for route in router.routes if hasattr(route, 'methods')]
    get_list_routes = [r for r in routes if 'GET' in r.methods and r.path == '/api/agent-runs']

    assert len(get_list_routes) == 1, f"Expected exactly one GET /api/agent-runs route, found {len(get_list_routes)}"

    route = get_list_routes[0]
    assert route.response_model is not None, "Route should have a response_model"
    assert route.response_model.__name__ == "AgentRunListResponse", f"Response model should be AgentRunListResponse, got {route.response_model.__name__}"

    print("  PASS: GET /api/agent-runs route is defined with AgentRunListResponse")


def verify_step_2():
    """Step 2: Add query parameters: agent_spec_id, status, limit, offset"""
    print("\n[Step 2] Verify query parameters are defined")

    from server.routers.agent_runs import list_agent_runs

    sig = inspect.signature(list_agent_runs)
    params = sig.parameters

    # Check all required parameters exist
    required_params = ["agent_spec_id", "status", "limit", "offset"]
    for param in required_params:
        assert param in params, f"Parameter '{param}' not found"
        print(f"  - {param}: present")

    # Check defaults
    limit_param = params["limit"]
    offset_param = params["offset"]

    # Check limit default is 50
    if hasattr(limit_param.default, 'default'):
        assert limit_param.default.default == 50, f"limit default should be 50"

    # Check offset default is 0
    if hasattr(offset_param.default, 'default'):
        assert offset_param.default.default == 0, f"offset default should be 0"

    print("  PASS: All query parameters (agent_spec_id, status, limit, offset) are defined")


def verify_step_3():
    """Step 3: Build query with conditional filters"""
    print("\n[Step 3] Verify query with conditional filters")

    from server.routers.agent_runs import list_agent_runs

    source = inspect.getsource(list_agent_runs)

    # Check for conditional filter patterns
    assert "if agent_spec_id is not None" in source, "Conditional agent_spec_id filter not found"
    assert "if status is not None" in source, "Conditional status filter not found"

    print("  PASS: Query uses conditional filters for optional parameters")


def verify_step_4():
    """Step 4: Filter by agent_spec_id if provided"""
    print("\n[Step 4] Verify agent_spec_id filter")

    from server.routers.agent_runs import list_agent_runs

    source = inspect.getsource(list_agent_runs)

    assert "AgentRunModel.agent_spec_id ==" in source, "agent_spec_id filter not found"

    print("  PASS: Filters by agent_spec_id when provided")


def verify_step_5():
    """Step 5: Filter by status if provided"""
    print("\n[Step 5] Verify status filter with validation")

    from server.routers.agent_runs import list_agent_runs
    from api.agentspec_models import RUN_STATUS

    source = inspect.getsource(list_agent_runs)

    # Check filter
    assert "AgentRunModel.status ==" in source, "status filter not found"

    # Check validation
    assert "RUN_STATUS" in source, "Status validation against RUN_STATUS not found"

    # Check valid statuses
    expected_statuses = ["pending", "running", "paused", "completed", "failed", "timeout"]
    for status in expected_statuses:
        assert status in RUN_STATUS, f"'{status}' should be a valid status"

    print(f"  PASS: Filters by status with validation ({len(RUN_STATUS)} valid statuses)")


def verify_step_6():
    """Step 6: Order by created_at descending"""
    print("\n[Step 6] Verify order by created_at descending")

    from server.routers.agent_runs import list_agent_runs

    source = inspect.getsource(list_agent_runs)

    assert "order_by(" in source, "order_by not found"
    assert "created_at.desc()" in source, "created_at.desc() not found"

    print("  PASS: Results ordered by created_at descending (newest first)")


def verify_step_7():
    """Step 7: Apply pagination"""
    print("\n[Step 7] Verify pagination is applied")

    from server.routers.agent_runs import list_agent_runs

    source = inspect.getsource(list_agent_runs)

    assert ".offset(" in source, "offset() not found"
    assert ".limit(" in source, "limit() not found"

    # Check max limit constraint
    sig = inspect.signature(list_agent_runs)
    limit_param = sig.parameters["limit"]

    if hasattr(limit_param.default, 'le'):
        assert limit_param.default.le == 100, "Max limit should be 100"
        print("  - Max limit: 100")

    print("  PASS: Pagination with offset and limit is applied")


def verify_step_8():
    """Step 8: Return AgentRunListResponse with total count"""
    print("\n[Step 8] Verify AgentRunListResponse with total count")

    from server.schemas.agentspec import AgentRunListResponse

    # Check required fields
    fields = AgentRunListResponse.model_fields

    required_fields = ["runs", "total", "offset", "limit"]
    for field in required_fields:
        assert field in fields, f"Field '{field}' not found in AgentRunListResponse"
        print(f"  - {field}: present")

    # Check total is integer
    assert fields["total"].annotation == int, "total should be int"

    # Check that the router also sets X-Total-Count header
    from server.routers.agent_runs import list_agent_runs
    source = inspect.getsource(list_agent_runs)
    assert 'X-Total-Count' in source, "X-Total-Count header not set"

    print("  PASS: Returns AgentRunListResponse with total count and X-Total-Count header")


def run_all_verifications():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #17: GET /api/agent-runs List Runs Endpoint")
    print("=" * 70)

    steps = [
        verify_step_1,
        verify_step_2,
        verify_step_3,
        verify_step_4,
        verify_step_5,
        verify_step_6,
        verify_step_7,
        verify_step_8,
    ]

    passed = 0
    failed = 0

    for step in steps:
        try:
            step()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{len(steps)} steps passed")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
    else:
        print("\n*** All verification steps passed! ***")
        sys.exit(0)


if __name__ == "__main__":
    run_all_verifications()
