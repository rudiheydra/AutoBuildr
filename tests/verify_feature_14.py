#!/usr/bin/env python3
"""
Feature #14 Verification Script
===============================

Verifies: PUT /api/agent-specs/:id Update AgentSpec

This script validates all 7 verification steps for Feature #14.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def verify_step_1():
    """Step 1: Define FastAPI route PUT /api/agent-specs/{spec_id} with AgentSpecUpdate body"""
    from server.routers.agent_specs import router
    from server.schemas.agentspec import AgentSpecResponse, AgentSpecUpdate

    # Check route exists
    routes = [r for r in router.routes if hasattr(r, 'methods') and 'PUT' in r.methods and '{spec_id}' in r.path]
    assert len(routes) == 1, "Should have exactly one PUT /{spec_id} route"

    # Check response model
    route = routes[0]
    assert route.response_model == AgentSpecResponse, "Route should use AgentSpecResponse"

    # Check AgentSpecUpdate schema exists and has correct fields
    fields = AgentSpecUpdate.model_fields
    required_fields = ['name', 'display_name', 'icon', 'objective', 'task_type',
                       'context', 'tool_policy', 'max_turns', 'timeout_seconds',
                       'parent_spec_id', 'source_feature_id', 'priority', 'tags']
    for field in required_fields:
        assert field in fields, f"AgentSpecUpdate should have {field} field"

    print("✓ Step 1: FastAPI route PUT /api/agent-specs/{spec_id} defined with AgentSpecUpdate body")
    return True


def verify_step_2():
    """Step 2: Query existing AgentSpec by id"""
    # Verified by the route implementation that queries spec by id
    from server.routers.agent_specs import update_agent_spec
    import inspect

    # Check that the function queries by spec_id
    source = inspect.getsource(update_agent_spec)
    assert 'AgentSpecModel.id == spec_id' in source or 'filter' in source, \
        "Function should query by spec_id"

    print("✓ Step 2: Route queries existing AgentSpec by id")
    return True


def verify_step_3():
    """Step 3: Return 404 if not found"""
    from server.routers.agent_specs import update_agent_spec
    import inspect

    source = inspect.getsource(update_agent_spec)
    assert '404' in source and 'not found' in source.lower(), \
        "Function should return 404 when spec not found"

    print("✓ Step 3: Returns 404 if AgentSpec not found")
    return True


def verify_step_4():
    """Step 4: Update only fields that are provided (not None)"""
    from server.routers.agent_specs import update_agent_spec
    import inspect

    source = inspect.getsource(update_agent_spec)
    assert 'exclude_unset=True' in source, \
        "Should use exclude_unset=True for partial updates"
    assert 'if value is not None' in source, \
        "Should only update non-None values"

    print("✓ Step 4: Updates only fields that are provided (not None)")
    return True


def verify_step_5():
    """Step 5: Validate updated max_turns and timeout_seconds against constraints"""
    from server.schemas.agentspec import AgentSpecUpdate
    from pydantic import ValidationError

    # Test max_turns validation
    try:
        AgentSpecUpdate(max_turns=0)
        assert False, "Should reject max_turns < 1"
    except ValidationError:
        pass

    try:
        AgentSpecUpdate(max_turns=501)
        assert False, "Should reject max_turns > 500"
    except ValidationError:
        pass

    # Test timeout_seconds validation
    try:
        AgentSpecUpdate(timeout_seconds=59)
        assert False, "Should reject timeout_seconds < 60"
    except ValidationError:
        pass

    try:
        AgentSpecUpdate(timeout_seconds=7201)
        assert False, "Should reject timeout_seconds > 7200"
    except ValidationError:
        pass

    # Test valid values work
    update = AgentSpecUpdate(max_turns=100, timeout_seconds=3600)
    assert update.max_turns == 100
    assert update.timeout_seconds == 3600

    print("✓ Step 5: Validates max_turns (1-500) and timeout_seconds (60-7200) constraints")
    return True


def verify_step_6():
    """Step 6: Commit transaction"""
    from server.routers.agent_specs import update_agent_spec
    import inspect

    source = inspect.getsource(update_agent_spec)
    assert 'db.commit()' in source, "Should commit transaction"
    assert 'db.refresh(spec)' in source, "Should refresh spec after commit"

    print("✓ Step 6: Commits transaction to database")
    return True


def verify_step_7():
    """Step 7: Return updated AgentSpecResponse"""
    from server.routers.agent_specs import router
    from server.schemas.agentspec import AgentSpecResponse

    # Find PUT route
    routes = [r for r in router.routes if hasattr(r, 'methods') and 'PUT' in r.methods and '{spec_id}' in r.path]
    assert len(routes) == 1
    route = routes[0]

    assert route.response_model == AgentSpecResponse, \
        "Route should return AgentSpecResponse"

    # Verify AgentSpecResponse has all required fields
    fields = AgentSpecResponse.model_fields
    required_fields = ['id', 'name', 'display_name', 'icon', 'spec_version',
                       'objective', 'task_type', 'context', 'tool_policy',
                       'max_turns', 'timeout_seconds', 'parent_spec_id',
                       'source_feature_id', 'created_at', 'priority', 'tags']
    for field in required_fields:
        assert field in fields, f"AgentSpecResponse should have {field} field"

    print("✓ Step 7: Returns updated AgentSpecResponse")
    return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #14: PUT /api/agent-specs/:id Update AgentSpec")
    print("=" * 60)
    print()

    all_passed = True

    steps = [
        ("Step 1: FastAPI route definition", verify_step_1),
        ("Step 2: Query existing AgentSpec", verify_step_2),
        ("Step 3: Return 404 if not found", verify_step_3),
        ("Step 4: Partial update (only provided fields)", verify_step_4),
        ("Step 5: Validate constraints", verify_step_5),
        ("Step 6: Commit transaction", verify_step_6),
        ("Step 7: Return AgentSpecResponse", verify_step_7),
    ]

    for step_name, verify_func in steps:
        try:
            verify_func()
        except AssertionError as e:
            print(f"✗ {step_name}: FAILED - {e}")
            all_passed = False
        except Exception as e:
            print(f"✗ {step_name}: ERROR - {e}")
            all_passed = False

    print()
    print("=" * 60)
    if all_passed:
        print("RESULT: All verification steps PASSED")
        print("Feature #14 is ready to be marked as passing")
    else:
        print("RESULT: Some verification steps FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
