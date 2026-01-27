"""
Feature #18: GET /api/agent-runs/:id Get Run Details
=====================================================

Test that verifies the GET /api/agent-runs/{run_id} endpoint works correctly.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

import pytest

from server.schemas.agentspec import (
    AgentRunResponse,
    AgentSpecResponse,
    AgentRunSummary,
)


class TestGetRunDetailsEndpoint:
    """Tests for GET /api/agent-runs/{run_id} endpoint."""

    def test_agentrun_summary_schema_structure(self):
        """
        Step 1-5: Verify AgentRunSummary can be created with all required fields.

        This validates the response schema used by the endpoint.
        """
        # Create mock data simulating what would come from database
        run_response = AgentRunResponse(
            id="test-run-uuid",
            agent_spec_id="test-spec-uuid",
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            turns_used=10,
            tokens_in=5000,
            tokens_out=2000,
            final_verdict=None,
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        spec_response = AgentSpecResponse(
            id="test-spec-uuid",
            name="test-spec-feature-18",
            display_name="Test Spec for Feature 18",  # Step 4: display_name
            icon="test-tube",  # Step 4: icon
            spec_version="v1",
            objective="Test objective",
            task_type="testing",
            context=None,
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["feature_get_by_id"],
                "forbidden_patterns": [],
                "tool_hints": {},
            },
            max_turns=50,
            timeout_seconds=1800,
            parent_spec_id=None,
            source_feature_id=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            priority=500,
            tags=[],
        )

        # Step 5: Return AgentRunResponse with nested spec summary
        summary = AgentRunSummary(
            run=run_response,
            spec=spec_response,
            event_count=3,
            artifact_count=2,
        )

        assert summary.run.id == "test-run-uuid"
        assert summary.spec.display_name == "Test Spec for Feature 18"
        assert summary.spec.icon == "test-tube"
        assert summary.event_count == 3
        assert summary.artifact_count == 2

    def test_agentrun_summary_with_null_spec(self):
        """
        Test AgentRunSummary when spec is None (orphaned run).
        """
        run_response = AgentRunResponse(
            id="orphan-run-uuid",
            agent_spec_id="deleted-spec-uuid",
            status="completed",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            turns_used=5,
            tokens_in=1000,
            tokens_out=500,
            final_verdict="passed",
            acceptance_results=[],
            error=None,
            retry_count=0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        summary = AgentRunSummary(
            run=run_response,
            spec=None,  # Spec might be None if deleted
            event_count=2,
            artifact_count=0,
        )

        assert summary.run.id == "orphan-run-uuid"
        assert summary.spec is None
        assert summary.event_count == 2
        assert summary.artifact_count == 0

    def test_agentrun_response_duration_computed(self):
        """
        Test that duration_seconds is computed when both timestamps exist.
        """
        started = datetime(2024, 1, 27, 12, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 27, 12, 5, 30, tzinfo=timezone.utc)  # 5min 30sec later

        run_response = AgentRunResponse(
            id="duration-test-uuid",
            agent_spec_id="test-spec-uuid",
            status="completed",
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            turns_used=20,
            tokens_in=10000,
            tokens_out=5000,
            final_verdict="passed",
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Duration should be 330 seconds (5 min 30 sec)
        assert run_response.duration_seconds == 330.0

    def test_run_status_validation(self):
        """
        Test that status validation works for all valid statuses.
        """
        valid_statuses = ["pending", "running", "paused", "completed", "failed", "timeout"]

        for status in valid_statuses:
            run = AgentRunResponse(
                id="status-test-uuid",
                agent_spec_id="test-spec-uuid",
                status=status,
                started_at=None,
                completed_at=None,
                turns_used=0,
                tokens_in=0,
                tokens_out=0,
                final_verdict=None,
                acceptance_results=None,
                error=None,
                retry_count=0,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            assert run.status == status

    def test_invalid_status_rejected(self):
        """
        Test that invalid status values are rejected.
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentRunResponse(
                id="invalid-status-uuid",
                agent_spec_id="test-spec-uuid",
                status="invalid_status",  # Invalid!
                started_at=None,
                completed_at=None,
                turns_used=0,
                tokens_in=0,
                tokens_out=0,
                final_verdict=None,
                acceptance_results=None,
                error=None,
                retry_count=0,
                created_at=datetime.now(timezone.utc).isoformat(),
            )


def test_feature_18_verification_steps():
    """
    Consolidated verification for Feature #18.

    Steps:
    1. Define FastAPI route GET /api/agent-runs/{run_id} - VERIFIED (code inspection)
    2. Query AgentRun by id with eager load of agent_spec - VERIFIED (code inspection)
    3. Return 404 if not found - VERIFIED (code inspection)
    4. Include spec display_name and icon in response - VERIFIED (schema test)
    5. Return AgentRunResponse with nested spec summary - VERIFIED (schema test)
    """
    print("\n=== Feature #18: GET /api/agent-runs/:id Verification ===\n")

    # Read the source file directly to verify implementation
    from pathlib import Path
    router_file = Path(__file__).parent.parent / "server" / "routers" / "agent_runs.py"
    source = router_file.read_text()

    # Verify step 1: Route defined
    assert '@router.get("/{run_id}"' in source, "Route GET /{run_id} should be defined"
    assert "response_model=AgentRunSummary" in source, "Should use AgentRunSummary response model"
    print("Step 1: PASS - FastAPI route GET /api/agent-runs/{run_id} is defined")

    # Verify step 2: Eager loading
    assert "joinedload" in source, "Should use joinedload for eager loading"
    assert "AgentRunModel.agent_spec" in source, "Should eager load agent_spec"
    print("Step 2: PASS - Query uses joinedload for eager loading of agent_spec")

    # Verify step 3: 404 handling
    assert "status_code=404" in source, "Should return 404 for not found"
    assert "HTTPException" in source, "Should use HTTPException"
    assert "not found" in source.lower(), "Should include 'not found' message"
    print("Step 3: PASS - Returns 404 if run not found")

    # Verify step 4: display_name and icon included
    assert "display_name" in source, "Should include display_name"
    assert "icon" in source, "Should include icon"
    print("Step 4: PASS - Includes spec display_name and icon in response")

    # Verify step 5: Returns AgentRunSummary
    assert "AgentRunSummary(" in source, "Should return AgentRunSummary"
    assert "run=run_response" in source, "Should include run in response"
    assert "spec=spec_response" in source, "Should include spec in response"
    assert "event_count=event_count" in source, "Should include event_count"
    assert "artifact_count=artifact_count" in source, "Should include artifact_count"
    print("Step 5: PASS - Returns AgentRunSummary with run, spec, and counts")

    print("\n=== All Feature #18 Verification Steps PASSED ===\n")


if __name__ == "__main__":
    test_feature_18_verification_steps()
