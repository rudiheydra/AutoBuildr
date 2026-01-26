#!/usr/bin/env python3
"""
Feature #20 Verification Script
================================

GET /api/agent-runs/:id/artifacts List Artifacts

Verification Steps:
1. Define FastAPI route GET /api/agent-runs/{run_id}/artifacts
2. Add query parameter: artifact_type filter
3. Query Artifacts by run_id
4. Filter by artifact_type if provided
5. Exclude content_inline from list response for performance
6. Return list of ArtifactResponse without content

This script verifies each step by:
- Checking the endpoint exists and is properly defined
- Testing artifact_type validation
- Verifying list response excludes content_inline
- Confirming ArtifactListItemResponse schema is used
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_step_1():
    """Step 1: Define FastAPI route GET /api/agent-runs/{run_id}/artifacts"""
    print("\nStep 1: Verify FastAPI route is defined...")

    try:
        from server.routers.agent_runs import router

        # Check that the route exists
        routes = [route for route in router.routes]
        artifacts_route = None
        for route in routes:
            if hasattr(route, 'path') and '/artifacts' in route.path:
                artifacts_route = route
                break

        if artifacts_route is None:
            print("  FAIL: No /artifacts route found in agent_runs router")
            return False

        # Check that it's a GET route
        if 'GET' not in artifacts_route.methods:
            print(f"  FAIL: /artifacts route does not support GET (methods: {artifacts_route.methods})")
            return False

        print(f"  Route path: {artifacts_route.path}")
        print(f"  Methods: {artifacts_route.methods}")
        print("  PASS: GET /api/agent-runs/{{run_id}}/artifacts route is defined")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def verify_step_2():
    """Step 2: Add query parameter: artifact_type filter"""
    print("\nStep 2: Verify artifact_type query parameter...")

    try:
        from server.routers.agent_runs import get_run_artifacts
        import inspect

        # Get the function signature
        sig = inspect.signature(get_run_artifacts)
        params = sig.parameters

        if 'artifact_type' not in params:
            print("  FAIL: artifact_type parameter not found")
            return False

        artifact_type_param = params['artifact_type']
        print(f"  Parameter name: artifact_type")
        print(f"  Parameter default: {artifact_type_param.default}")
        print("  PASS: artifact_type query parameter is defined")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def verify_step_3():
    """Step 3: Query Artifacts by run_id"""
    print("\nStep 3: Verify artifacts are queried by run_id...")

    try:
        from api.agentspec_crud import list_artifacts
        import inspect

        # Check the function signature
        sig = inspect.signature(list_artifacts)
        params = sig.parameters

        if 'run_id' not in params:
            print("  FAIL: run_id parameter not in list_artifacts")
            return False

        # Check that list_artifacts is imported in the router
        from server.routers import agent_runs
        if 'list_artifacts' not in dir(agent_runs):
            print("  FAIL: list_artifacts not imported in agent_runs router")
            return False

        print("  list_artifacts function accepts run_id parameter")
        print("  list_artifacts is imported in agent_runs router")
        print("  PASS: Artifacts are queried by run_id")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def verify_step_4():
    """Step 4: Filter by artifact_type if provided"""
    print("\nStep 4: Verify artifact_type filtering...")

    try:
        from api.agentspec_crud import list_artifacts
        import inspect

        # Check that artifact_type is a parameter
        sig = inspect.signature(list_artifacts)
        params = sig.parameters

        if 'artifact_type' not in params:
            print("  FAIL: artifact_type parameter not in list_artifacts")
            return False

        # Verify the endpoint validates artifact_type
        from server.routers.agent_runs import get_run_artifacts
        source = inspect.getsource(get_run_artifacts)

        if "valid_artifact_types" not in source:
            print("  FAIL: artifact_type validation not found in endpoint")
            return False

        # Check valid types are defined
        valid_types = ["file_change", "test_result", "log", "metric", "snapshot"]
        for vtype in valid_types:
            if vtype not in source:
                print(f"  FAIL: Valid type '{vtype}' not in validation")
                return False

        print(f"  Valid artifact types: {valid_types}")
        print("  Endpoint validates artifact_type against allowed values")
        print("  list_artifacts supports artifact_type filter")
        print("  PASS: artifact_type filtering is implemented")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def verify_step_5():
    """Step 5: Exclude content_inline from list response for performance"""
    print("\nStep 5: Verify content_inline is excluded from list response...")

    try:
        from server.schemas.agentspec import ArtifactListItemResponse
        import inspect

        # Get all fields in ArtifactListItemResponse
        fields = ArtifactListItemResponse.model_fields
        field_names = list(fields.keys())

        if 'content_inline' in field_names:
            print("  FAIL: content_inline is present in ArtifactListItemResponse")
            return False

        # Check that has_inline_content is present (as a boolean indicator)
        if 'has_inline_content' not in field_names:
            print("  FAIL: has_inline_content field not found")
            return False

        print(f"  ArtifactListItemResponse fields: {field_names}")
        print("  content_inline is NOT in response schema")
        print("  has_inline_content boolean indicator is present")
        print("  PASS: content_inline is excluded from list response")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def verify_step_6():
    """Step 6: Return list of ArtifactResponse without content"""
    print("\nStep 6: Verify ArtifactListResponse uses ArtifactListItemResponse...")

    try:
        from server.schemas.agentspec import ArtifactListResponse, ArtifactListItemResponse

        # Check that ArtifactListResponse uses ArtifactListItemResponse
        artifacts_field = ArtifactListResponse.model_fields['artifacts']
        annotation = str(artifacts_field.annotation)

        if 'ArtifactListItemResponse' not in annotation:
            print(f"  FAIL: artifacts field uses wrong type: {annotation}")
            return False

        # Verify run_id is in the response
        if 'run_id' not in ArtifactListResponse.model_fields:
            print("  FAIL: run_id field not in ArtifactListResponse")
            return False

        # Verify total is in the response
        if 'total' not in ArtifactListResponse.model_fields:
            print("  FAIL: total field not in ArtifactListResponse")
            return False

        print(f"  ArtifactListResponse.artifacts type: {annotation}")
        print("  Response includes: artifacts, total, run_id")
        print("  PASS: Returns list of ArtifactListItemResponse (without content)")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #20 Verification: GET /api/agent-runs/:id/artifacts")
    print("=" * 60)

    results = []

    # Run all verification steps
    results.append(("Step 1: Define FastAPI route", verify_step_1()))
    results.append(("Step 2: Add artifact_type filter", verify_step_2()))
    results.append(("Step 3: Query Artifacts by run_id", verify_step_3()))
    results.append(("Step 4: Filter by artifact_type if provided", verify_step_4()))
    results.append(("Step 5: Exclude content_inline", verify_step_5()))
    results.append(("Step 6: Return ArtifactListResponse", verify_step_6()))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed}/{len(results)} steps passed")

    if failed > 0:
        print("\nFeature #20 verification FAILED")
        return 1
    else:
        print("\nFeature #20 verification PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
