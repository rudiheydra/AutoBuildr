#!/usr/bin/env python3
"""
Standalone verification script for Feature #212: Test results persisted as artifacts.

This script verifies all 5 feature steps without requiring pytest.

Run with: python tests/verify_feature_212.py
"""
import json
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.test_result_artifact import (
    ARTIFACT_TYPE_TEST_RESULT,
    TestResultArtifactMetadata,
    build_test_result_metadata,
    serialize_test_result,
    deserialize_test_result,
    store_test_result_artifact,
    retrieve_test_result_from_artifact,
    get_test_summary_from_artifact,
    METADATA_KEY_PASS_COUNT,
    METADATA_KEY_FAIL_COUNT,
    METADATA_KEY_HAS_OUTPUT_LOG,
)
from api.test_runner import TestExecutionResult, TestFailure
from api.agentspec_models import ARTIFACT_TYPES, EVENT_TYPES


def verify_step1_test_output_captured() -> tuple[bool, str]:
    """Step 1: Test output captured as artifact."""
    try:
        # Create result with output
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=100,
            passed_tests=95,
            failed_tests=5,
            stdout="Collected 100 items\n95 passed, 5 failed",
            stderr="Warning: deprecated feature",
            command="pytest tests/ -v",
        )

        # Serialize
        content = serialize_test_result(result)

        # Verify valid JSON
        parsed = json.loads(content)

        # Verify output is captured
        if "stdout" not in parsed:
            return False, "stdout not in serialized content"
        if "stderr" not in parsed:
            return False, "stderr not in serialized content"
        if "95 passed" not in parsed["stdout"]:
            return False, "stdout content not preserved"

        # Verify deserialization
        restored = deserialize_test_result(content)
        if restored.stdout != result.stdout:
            return False, "stdout not restored correctly"

        return True, "Test output captured and serialized correctly"
    except Exception as e:
        return False, f"Exception: {e}"


def verify_step2_artifact_type_test_result() -> tuple[bool, str]:
    """Step 2: Artifact type: test_result."""
    try:
        # Check constant
        if ARTIFACT_TYPE_TEST_RESULT != "test_result":
            return False, f"ARTIFACT_TYPE_TEST_RESULT is '{ARTIFACT_TYPE_TEST_RESULT}', expected 'test_result'"

        # Check in valid types
        if "test_result" not in ARTIFACT_TYPES:
            return False, "'test_result' not in ARTIFACT_TYPES"

        return True, "Artifact type 'test_result' is defined and valid"
    except Exception as e:
        return False, f"Exception: {e}"


def verify_step3_includes_pass_fail_output() -> tuple[bool, str]:
    """Step 3: Includes: pass count, fail count, output log."""
    try:
        # Create result with failures
        failures = [
            TestFailure(test_name="test_one", message="assertion failed"),
            TestFailure(test_name="test_two", message="error occurred"),
        ]
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            stdout="Test output log here",
            failures=failures,
        )

        metadata = build_test_result_metadata(result)

        # Check pass count
        if metadata.pass_count != 8:
            return False, f"pass_count is {metadata.pass_count}, expected 8"

        # Check fail count
        if metadata.fail_count != 2:
            return False, f"fail_count is {metadata.fail_count}, expected 2"

        # Check output log indicator
        if not metadata.has_output_log:
            return False, "has_output_log should be True"

        # Check failure summary
        if len(metadata.failure_summary) != 2:
            return False, f"failure_summary has {len(metadata.failure_summary)} items, expected 2"

        # Verify to_dict contains all required fields
        d = metadata.to_dict()
        required_keys = [METADATA_KEY_PASS_COUNT, METADATA_KEY_FAIL_COUNT, METADATA_KEY_HAS_OUTPUT_LOG]
        for key in required_keys:
            if key not in d:
                return False, f"Metadata missing key: {key}"

        return True, "Metadata includes pass_count=8, fail_count=2, has_output_log=True"
    except Exception as e:
        return False, f"Exception: {e}"


def verify_step4_artifact_linked_to_agent_run() -> tuple[bool, str]:
    """Step 4: Artifact linked to AgentRun."""
    try:
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "art-123"
        mock_artifact.run_id = "run-456"
        mock_artifact.content_hash = "hash"
        mock_artifact.size_bytes = 100
        mock_artifact.content_inline = "x"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(passed=True, exit_code=0)

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-456",
            result=result,
        )

        # Verify run_id was passed
        call_kwargs = mock_storage.store.call_args.kwargs
        if call_kwargs.get("run_id") != "run-456":
            return False, f"run_id not passed correctly, got {call_kwargs.get('run_id')}"

        return True, "Artifact linked to AgentRun via run_id='run-456'"
    except Exception as e:
        return False, f"Exception: {e}"


def verify_step5_large_outputs_stored_by_content_hash() -> tuple[bool, str]:
    """Step 5: Large outputs stored by content hash."""
    try:
        from api.artifact_storage import ArtifactStorage
        from api.agentspec_models import Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create in-memory database
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)

            with Session(engine) as session:
                storage = ArtifactStorage(tmpdir)

                # Create result with large output
                large_output = "x" * 50000  # 50KB
                result = TestExecutionResult(
                    passed=True,
                    exit_code=0,
                    stdout=large_output,
                )

                artifact = store_test_result_artifact(
                    session=session,
                    storage=storage,
                    run_id="run-large",
                    result=result,
                )
                session.commit()

                # Verify content_hash exists
                if not artifact.content_hash:
                    return False, "content_hash is empty"

                # Verify hash is SHA256 format (64 hex chars)
                if len(artifact.content_hash) != 64:
                    return False, f"content_hash length is {len(artifact.content_hash)}, expected 64"

                # Verify large content stored in file
                if artifact.content_inline is not None and len(artifact.content_inline) > 4096:
                    return False, "Large content stored inline instead of file"

                return True, f"Large output stored with hash={artifact.content_hash[:16]}..."
    except Exception as e:
        return False, f"Exception: {e}"


def verify_event_type_registered() -> tuple[bool, str]:
    """Bonus: Verify test_result_artifact_created event type is registered."""
    try:
        if "test_result_artifact_created" not in EVENT_TYPES:
            return False, "'test_result_artifact_created' not in EVENT_TYPES"
        return True, "Event type 'test_result_artifact_created' is registered"
    except Exception as e:
        return False, f"Exception: {e}"


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #212: Test results persisted as artifacts")
    print("=" * 70)
    print()

    steps = [
        ("Step 1: Test output captured as artifact", verify_step1_test_output_captured),
        ("Step 2: Artifact type: test_result", verify_step2_artifact_type_test_result),
        ("Step 3: Includes pass count, fail count, output log", verify_step3_includes_pass_fail_output),
        ("Step 4: Artifact linked to AgentRun", verify_step4_artifact_linked_to_agent_run),
        ("Step 5: Large outputs stored by content hash", verify_step5_large_outputs_stored_by_content_hash),
        ("Bonus: Event type registered", verify_event_type_registered),
    ]

    all_passed = True
    for name, verify_func in steps:
        passed, message = verify_func()
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        print(f"       {message}")
        print()
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("All verification steps PASSED!")
        return 0
    else:
        print("Some verification steps FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
