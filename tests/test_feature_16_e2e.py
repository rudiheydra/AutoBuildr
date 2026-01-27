#!/usr/bin/env python
"""
End-to-end test for Feature #16: POST /api/agent-specs/:id/execute

This test creates a proper test environment with a temporary database
and verifies the execute endpoint works correctly.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

# Set environment for testing
os.environ["AUTOBUILDR_ALLOW_REMOTE"] = "1"


def test_execute_endpoint_e2e():
    """Full end-to-end test of the execute endpoint."""
    print("\n" + "=" * 60)
    print("Feature #16 E2E Test: POST /api/agent-specs/:id/execute")
    print("=" * 60 + "\n")

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Create a temporary directory for the test database
    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a test database
        db_path = tmpdir_path / "features.db"
        engine = create_engine(f"sqlite:///{db_path}")

        # Import models after path setup
        from api.database import Base
        from api.agentspec_models import AgentSpec, AgentRun, AcceptanceSpec

        # Create all tables
        Base.metadata.create_all(engine)

        # Create a session
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        # Create a test AgentSpec
        spec_id = str(uuid.uuid4())
        test_spec = AgentSpec(
            id=spec_id,
            name="test-execute-spec",
            display_name="Test Execute Spec",
            icon="test",
            spec_version="v1",
            objective="Test the execute endpoint",
            task_type="testing",
            context=None,
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["test_tool"],
                "forbidden_patterns": [],
                "tool_hints": {}
            },
            max_turns=10,
            timeout_seconds=300,
            created_at=datetime.now(timezone.utc),
            priority=100,
            tags=["test"]
        )
        session.add(test_spec)
        session.commit()
        session.refresh(test_spec)

        print(f"[1] Created test AgentSpec: {spec_id}")

        # Now we need to test the execute endpoint
        # We'll use the router directly with mocked dependencies

        from server.routers.agent_specs import (
            execute_agent_spec,
            _utc_now,
            _generate_uuid,
            get_db_session,
        )

        # Mock the project path lookup to return our temp directory
        with patch("server.routers.agent_specs._get_project_path") as mock_path:
            mock_path.return_value = tmpdir_path

            # Mock get_db_session to use our session
            from contextlib import contextmanager

            @contextmanager
            def mock_db_session(project_dir):
                test_session = SessionLocal()
                try:
                    yield test_session
                finally:
                    test_session.close()

            with patch("server.routers.agent_specs.get_db_session", mock_db_session):
                # Run the async endpoint
                async def run_test():
                    result = await execute_agent_spec(
                        project_name="test-project",
                        spec_id=spec_id
                    )
                    return result

                # Execute
                result = asyncio.run(run_test())

                print(f"[2] Execute endpoint returned: {type(result).__name__}")

                # Verify the response
                assert result.status == "pending", f"Expected status 'pending', got '{result.status}'"
                print(f"    - status: {result.status} ✓")

                assert result.agent_spec_id == spec_id, f"Expected agent_spec_id '{spec_id}', got '{result.agent_spec_id}'"
                print(f"    - agent_spec_id: {result.agent_spec_id[:8]}... ✓")

                assert result.id is not None, "Run ID should not be None"
                print(f"    - run_id: {result.id[:8]}... ✓")

                assert result.turns_used == 0, f"Expected turns_used=0, got {result.turns_used}"
                print(f"    - turns_used: {result.turns_used} ✓")

                assert result.created_at is not None, "created_at should not be None"
                print(f"    - created_at: {result.created_at} ✓")

                # Verify the run was persisted to database
                verify_session = SessionLocal()
                persisted_run = verify_session.query(AgentRun).filter(AgentRun.id == result.id).first()
                verify_session.close()

                assert persisted_run is not None, "Run should be persisted to database"
                print(f"[3] Verified run persisted to database ✓")

                # Note: The background task may have already transitioned the status
                # to "running" by the time we check. Both "pending" and "running" are
                # valid states at this point.
                assert persisted_run.status in ["pending", "running"], f"Persisted status should be 'pending' or 'running', got '{persisted_run.status}'"
                print(f"    - persisted status: {persisted_run.status} ✓")

        session.close()

        print("\n" + "=" * 60)
        print("All E2E tests PASSED!")
        print("=" * 60 + "\n")

        return True


def test_404_for_missing_spec():
    """Test that 404 is returned for non-existent spec."""
    print("\n" + "=" * 60)
    print("Feature #16 404 Test: Non-existent spec")
    print("=" * 60 + "\n")

    from fastapi import HTTPException
    from tempfile import TemporaryDirectory
    from unittest.mock import patch

    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from api.database import Base
        from api.agentspec_models import AgentSpec

        db_path = tmpdir_path / "features.db"
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)

        from server.routers.agent_specs import execute_agent_spec
        from contextlib import contextmanager

        @contextmanager
        def mock_db_session(project_dir):
            test_session = SessionLocal()
            try:
                yield test_session
            finally:
                test_session.close()

        with patch("server.routers.agent_specs._get_project_path") as mock_path:
            mock_path.return_value = tmpdir_path

            with patch("server.routers.agent_specs.get_db_session", mock_db_session):
                fake_spec_id = str(uuid.uuid4())

                async def run_404_test():
                    try:
                        await execute_agent_spec(
                            project_name="test-project",
                            spec_id=fake_spec_id
                        )
                        return False  # Should not reach here
                    except HTTPException as e:
                        return e.status_code == 404

                result = asyncio.run(run_404_test())
                assert result, "Should return 404 for non-existent spec"

        print("[1] Correctly returns 404 for non-existent spec ✓")
        print("\n" + "=" * 60)
        print("404 test PASSED!")
        print("=" * 60 + "\n")

        return True


if __name__ == "__main__":
    try:
        test_execute_endpoint_e2e()
        test_404_for_missing_spec()
        print("\n✅ All Feature #16 tests passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
