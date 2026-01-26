#!/usr/bin/env python3
"""
End-to-end test for Feature #20: GET /api/agent-runs/:id/artifacts
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import requests
import uuid

BASE_URL = "http://localhost:8888"


def setup_test_data():
    """Create test data: AgentSpec, AgentRun, and Artifacts."""
    from api.database import create_database
    from api.agentspec_crud import (
        create_agent_spec,
        create_agent_run,
        create_artifact,
        start_run,
    )
    from api.agentspec_models import generate_uuid

    engine, SessionLocal = create_database(project_root)
    db = SessionLocal()

    try:
        # Create AgentSpec
        spec = create_agent_spec(
            db,
            name=f"test-spec-{uuid.uuid4().hex[:8]}",
            display_name="Test Spec for Feature 20",
            objective="Test objective for artifact endpoint",
            task_type="testing",
            allowed_tools=["test_tool"],
        )
        db.commit()

        # Create AgentRun
        run = create_agent_run(db, spec.id)
        start_run(db, run.id)
        db.commit()

        # Create some test artifacts with different types
        # Small artifact with inline content
        artifact1 = create_artifact(
            db,
            run.id,
            "test_result",
            "This is a small test result content",
            path="/test/result1.txt",
            metadata={"passed": True, "test_count": 5}
        )

        # Another artifact with different type
        artifact2 = create_artifact(
            db,
            run.id,
            "log",
            "Log content here - debugging information",
            metadata={"level": "info"}
        )

        # File change artifact
        artifact3 = create_artifact(
            db,
            run.id,
            "file_change",
            "diff --git a/test.py b/test.py\n...",
            path="/src/test.py",
            metadata={"lines_added": 10, "lines_removed": 5}
        )

        db.commit()

        print(f"Created test spec: {spec.id}")
        print(f"Created test run: {run.id}")
        print(f"Created artifacts: {artifact1.id}, {artifact2.id}, {artifact3.id}")

        return spec.id, run.id, [artifact1.id, artifact2.id, artifact3.id]

    finally:
        db.close()


def test_list_artifacts(run_id):
    """Test GET /api/agent-runs/{run_id}/artifacts"""
    print(f"\n[TEST] GET /api/agent-runs/{run_id}/artifacts")

    response = requests.get(f"{BASE_URL}/api/agent-runs/{run_id}/artifacts")

    if response.status_code != 200:
        print(f"  FAIL: Expected 200, got {response.status_code}")
        print(f"  Response: {response.text}")
        return False

    data = response.json()

    # Check response structure
    if "artifacts" not in data:
        print("  FAIL: 'artifacts' field missing")
        return False

    if "total" not in data:
        print("  FAIL: 'total' field missing")
        return False

    if "run_id" not in data:
        print("  FAIL: 'run_id' field missing")
        return False

    # Check that we have artifacts
    if len(data["artifacts"]) == 0:
        print("  FAIL: No artifacts returned")
        return False

    # Check that content_inline is NOT in the response
    for artifact in data["artifacts"]:
        if "content_inline" in artifact:
            print(f"  FAIL: content_inline found in artifact {artifact['id']}")
            return False

        # Check that has_inline_content is present
        if "has_inline_content" not in artifact:
            print(f"  FAIL: has_inline_content missing from artifact {artifact['id']}")
            return False

    print(f"  Total artifacts: {data['total']}")
    print(f"  Artifacts returned: {len(data['artifacts'])}")
    print(f"  run_id in response: {data['run_id']}")
    print("  content_inline NOT in response (as expected)")
    print("  PASS: List artifacts endpoint works correctly")
    return True


def test_filter_by_type(run_id):
    """Test filtering by artifact_type"""
    print(f"\n[TEST] GET /api/agent-runs/{run_id}/artifacts?artifact_type=test_result")

    response = requests.get(
        f"{BASE_URL}/api/agent-runs/{run_id}/artifacts",
        params={"artifact_type": "test_result"}
    )

    if response.status_code != 200:
        print(f"  FAIL: Expected 200, got {response.status_code}")
        return False

    data = response.json()

    # All returned artifacts should be test_result type
    for artifact in data["artifacts"]:
        if artifact["artifact_type"] != "test_result":
            print(f"  FAIL: Got artifact type {artifact['artifact_type']}, expected test_result")
            return False

    print(f"  Filtered artifacts: {len(data['artifacts'])}")
    print("  All artifacts are of type 'test_result'")
    print("  PASS: artifact_type filter works correctly")
    return True


def test_invalid_artifact_type(run_id):
    """Test validation of invalid artifact_type"""
    print(f"\n[TEST] GET /api/agent-runs/{run_id}/artifacts?artifact_type=invalid_type")

    response = requests.get(
        f"{BASE_URL}/api/agent-runs/{run_id}/artifacts",
        params={"artifact_type": "invalid_type"}
    )

    if response.status_code != 400:
        print(f"  FAIL: Expected 400, got {response.status_code}")
        return False

    data = response.json()
    if "detail" not in data:
        print("  FAIL: No error detail in response")
        return False

    print(f"  Error message: {data['detail']}")
    print("  PASS: Invalid artifact_type returns 400")
    return True


def test_nonexistent_run():
    """Test 404 for non-existent run"""
    fake_run_id = "nonexistent-run-id-12345"
    print(f"\n[TEST] GET /api/agent-runs/{fake_run_id}/artifacts (404 test)")

    response = requests.get(f"{BASE_URL}/api/agent-runs/{fake_run_id}/artifacts")

    if response.status_code != 404:
        print(f"  FAIL: Expected 404, got {response.status_code}")
        return False

    print("  PASS: Non-existent run returns 404")
    return True


def cleanup_test_data(spec_id):
    """Clean up test data."""
    from api.database import create_database
    from api.agentspec_crud import delete_agent_spec

    engine, SessionLocal = create_database(project_root)
    db = SessionLocal()
    try:
        delete_agent_spec(db, spec_id)
        db.commit()
        print(f"\nCleaned up test spec: {spec_id}")
    finally:
        db.close()


def main():
    """Run all e2e tests."""
    print("=" * 60)
    print("Feature #20 E2E Tests: GET /api/agent-runs/:id/artifacts")
    print("=" * 60)

    # Setup
    spec_id, run_id, artifact_ids = setup_test_data()

    results = []

    try:
        # Run tests
        results.append(("List artifacts", test_list_artifacts(run_id)))
        results.append(("Filter by artifact_type", test_filter_by_type(run_id)))
        results.append(("Invalid artifact_type (400)", test_invalid_artifact_type(run_id)))
        results.append(("Non-existent run (404)", test_nonexistent_run()))

    finally:
        # Cleanup
        cleanup_test_data(spec_id)

    # Summary
    print("\n" + "=" * 60)
    print("E2E TEST SUMMARY")
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

    print(f"\nTotal: {passed}/{len(results)} tests passed")

    if failed > 0:
        print("\nFeature #20 E2E tests FAILED")
        return 1
    else:
        print("\nFeature #20 E2E tests PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
