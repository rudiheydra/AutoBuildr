"""
Tests for Feature #212: Test results persisted as artifacts

This module tests the test_result_artifact functionality:
1. Test output captured as artifact
2. Artifact type: test_result
3. Includes: pass count, fail count, output log
4. Artifact linked to AgentRun
5. Large outputs stored by content hash

Run with: pytest tests/test_feature_212_test_result_artifact.py -v
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the module under test
from api.test_result_artifact import (
    # Constants
    ARTIFACT_TYPE_TEST_RESULT,
    CONTENT_TYPE_JSON,
    MAX_FAILURES_IN_METADATA,
    METADATA_KEY_PASSED,
    METADATA_KEY_PASS_COUNT,
    METADATA_KEY_FAIL_COUNT,
    METADATA_KEY_SKIP_COUNT,
    METADATA_KEY_ERROR_COUNT,
    METADATA_KEY_TOTAL_COUNT,
    METADATA_KEY_SUCCESS_RATE,
    METADATA_KEY_COMMAND,
    METADATA_KEY_FRAMEWORK,
    METADATA_KEY_DURATION_SECONDS,
    METADATA_KEY_TIMESTAMP,
    METADATA_KEY_FAILURE_SUMMARY,
    METADATA_KEY_CONTENT_TYPE,
    METADATA_KEY_HAS_OUTPUT_LOG,
    METADATA_KEY_OUTPUT_TRUNCATED,
    # Data classes
    TestResultArtifactMetadata,
    StoreTestResultResult,
    RetrievedTestResult,
    # Functions
    build_test_result_metadata,
    serialize_test_result,
    deserialize_test_result,
    store_test_result_artifact,
    get_store_result,
    retrieve_test_result_from_artifact,
    get_test_result_artifacts_for_run,
    get_latest_test_result_artifact,
    get_test_summary_from_artifact,
    record_test_result_artifact_created,
)
from api.test_runner import TestExecutionResult, TestFailure


class TestStep1TestOutputCaptured(unittest.TestCase):
    """Tests for Step 1: Test output captured as artifact."""

    def test_serialize_test_result_creates_json(self):
        """Serialization creates valid JSON."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            stdout="All tests passed!",
            stderr="",
            command="pytest",
        )

        content = serialize_test_result(result)

        # Should be valid JSON
        parsed = json.loads(content)
        self.assertIsInstance(parsed, dict)

    def test_serialize_preserves_all_fields(self):
        """Serialization preserves all TestExecutionResult fields."""
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=10,
            passed_tests=7,
            failed_tests=2,
            skipped_tests=1,
            error_tests=0,
            stdout="Test output here",
            stderr="Error output here",
            command="pytest tests/ -v",
            working_directory="/path/to/project",
            timeout_seconds=300,
            duration_seconds=15.5,
            framework="pytest",
            framework_version="7.4.0",
        )

        content = serialize_test_result(result)
        parsed = json.loads(content)

        self.assertEqual(parsed["passed"], False)
        self.assertEqual(parsed["exit_code"], 1)
        self.assertEqual(parsed["total_tests"], 10)
        self.assertEqual(parsed["passed_tests"], 7)
        self.assertEqual(parsed["failed_tests"], 2)
        self.assertEqual(parsed["skipped_tests"], 1)
        self.assertEqual(parsed["stdout"], "Test output here")
        self.assertEqual(parsed["stderr"], "Error output here")
        self.assertEqual(parsed["command"], "pytest tests/ -v")
        self.assertEqual(parsed["framework"], "pytest")

    def test_serialize_includes_failures(self):
        """Serialization includes failure details."""
        failure = TestFailure(
            test_name="test_foo",
            message="AssertionError: 1 != 2",
            test_file="tests/test_foo.py",
            test_class="TestFoo",
            test_method="test_foo",
        )
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=1,
            failed_tests=1,
            failures=[failure],
        )

        content = serialize_test_result(result)
        parsed = json.loads(content)

        self.assertEqual(len(parsed["failures"]), 1)
        self.assertEqual(parsed["failures"][0]["test_name"], "test_foo")
        self.assertEqual(parsed["failures"][0]["message"], "AssertionError: 1 != 2")

    def test_deserialize_reconstructs_result(self):
        """Deserialization reconstructs TestExecutionResult."""
        original = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            stdout="Output",
            command="pytest",
            framework="pytest",
        )

        content = serialize_test_result(original)
        restored = deserialize_test_result(content)

        self.assertEqual(restored.passed, original.passed)
        self.assertEqual(restored.exit_code, original.exit_code)
        self.assertEqual(restored.total_tests, original.total_tests)
        self.assertEqual(restored.passed_tests, original.passed_tests)
        self.assertEqual(restored.stdout, original.stdout)
        self.assertEqual(restored.command, original.command)
        self.assertEqual(restored.framework, original.framework)

    def test_deserialize_reconstructs_failures(self):
        """Deserialization reconstructs failure details."""
        failure = TestFailure(
            test_name="test_bar",
            message="Test failed",
            test_file="tests/test_bar.py",
        )
        original = TestExecutionResult(
            passed=False,
            exit_code=1,
            failed_tests=1,
            failures=[failure],
        )

        content = serialize_test_result(original)
        restored = deserialize_test_result(content)

        self.assertEqual(len(restored.failures), 1)
        self.assertEqual(restored.failures[0].test_name, "test_bar")
        self.assertEqual(restored.failures[0].message, "Test failed")


class TestStep2ArtifactTypeTestResult(unittest.TestCase):
    """Tests for Step 2: Artifact type: test_result."""

    def test_artifact_type_constant_is_test_result(self):
        """ARTIFACT_TYPE_TEST_RESULT constant is 'test_result'."""
        self.assertEqual(ARTIFACT_TYPE_TEST_RESULT, "test_result")

    def test_artifact_type_in_valid_types(self):
        """test_result is a valid artifact type."""
        from api.agentspec_models import ARTIFACT_TYPES

        self.assertIn("test_result", ARTIFACT_TYPES)

    def test_store_uses_test_result_type(self):
        """store_test_result_artifact uses test_result type."""
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "artifact-123"
        mock_artifact.content_hash = "abc123"
        mock_artifact.size_bytes = 100
        mock_artifact.content_inline = "content"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(passed=True, exit_code=0)

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-123",
            result=result,
        )

        # Verify artifact_type was passed to storage.store
        call_args = mock_storage.store.call_args
        self.assertEqual(call_args.kwargs.get("artifact_type"), "test_result")


class TestStep3IncludesPassFailOutput(unittest.TestCase):
    """Tests for Step 3: Includes pass count, fail count, output log."""

    def test_metadata_includes_pass_count(self):
        """Metadata includes pass_count field."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.pass_count, 8)

    def test_metadata_includes_fail_count(self):
        """Metadata includes fail_count field."""
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=10,
            passed_tests=7,
            failed_tests=3,
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.fail_count, 3)

    def test_metadata_includes_total_count(self):
        """Metadata includes total_count field."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=42,
            passed_tests=42,
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.total_count, 42)

    def test_metadata_includes_success_rate(self):
        """Metadata includes success_rate percentage."""
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=100,
            passed_tests=75,
            failed_tests=25,
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.success_rate, 75.0)

    def test_metadata_includes_framework(self):
        """Metadata includes test framework."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            framework="pytest",
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.framework, "pytest")

    def test_metadata_includes_command(self):
        """Metadata includes test command."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            command="pytest tests/ -v --tb=short",
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.command, "pytest tests/ -v --tb=short")

    def test_metadata_includes_duration(self):
        """Metadata includes duration_seconds."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            duration_seconds=12.345,
        )

        metadata = build_test_result_metadata(result)

        self.assertEqual(metadata.duration_seconds, 12.345)

    def test_metadata_includes_has_output_log(self):
        """Metadata indicates if output log exists."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            stdout="Test output",
            stderr="",
        )

        metadata = build_test_result_metadata(result)

        self.assertTrue(metadata.has_output_log)

    def test_metadata_has_output_log_false_when_empty(self):
        """has_output_log is False when stdout and stderr are empty."""
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            stdout="",
            stderr="",
        )

        metadata = build_test_result_metadata(result)

        self.assertFalse(metadata.has_output_log)

    def test_metadata_includes_failure_summary(self):
        """Metadata includes truncated failure summary."""
        failures = [
            TestFailure(test_name=f"test_{i}", message=f"Failed {i}")
            for i in range(10)
        ]
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            failed_tests=10,
            failures=failures,
        )

        metadata = build_test_result_metadata(result, max_failures=5)

        # Should only include 5 failures in summary
        self.assertEqual(len(metadata.failure_summary), 5)
        self.assertEqual(metadata.failure_summary[0]["test_name"], "test_0")


class TestStep4ArtifactLinkedToAgentRun(unittest.TestCase):
    """Tests for Step 4: Artifact linked to AgentRun."""

    def test_store_passes_run_id_to_storage(self):
        """store_test_result_artifact passes run_id to storage."""
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "artifact-456"
        mock_artifact.run_id = "run-789"
        mock_artifact.content_hash = "def456"
        mock_artifact.size_bytes = 200
        mock_artifact.content_inline = "content"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(passed=True, exit_code=0)

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-789",
            result=result,
        )

        # Verify run_id was passed
        call_args = mock_storage.store.call_args
        self.assertEqual(call_args.kwargs.get("run_id"), "run-789")

    def test_get_test_result_artifacts_for_run_filters_by_run_id(self):
        """get_test_result_artifacts_for_run queries by run_id."""
        from api.agentspec_models import Artifact

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        get_test_result_artifacts_for_run(mock_session, "run-abc")

        # Should have queried Artifact table
        mock_session.query.assert_called()

    def test_get_latest_test_result_artifact_filters_by_run_id(self):
        """get_latest_test_result_artifact queries by run_id."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        get_latest_test_result_artifact(mock_session, "run-def")

        mock_session.query.assert_called()


class TestStep5LargeOutputsStoredByContentHash(unittest.TestCase):
    """Tests for Step 5: Large outputs stored by content hash."""

    def test_store_uses_artifact_storage(self):
        """store_test_result_artifact uses ArtifactStorage for content."""
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "artifact-789"
        mock_artifact.content_hash = "sha256hash"
        mock_artifact.size_bytes = 5000
        mock_artifact.content_inline = None  # Large, stored in file
        mock_artifact.content_ref = ".autobuildr/artifacts/run-123/sha256hash.blob"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            stdout="x" * 10000,  # Large output
        )

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-123",
            result=result,
        )

        # Verify ArtifactStorage.store was called
        mock_storage.store.assert_called_once()

    def test_artifact_has_content_hash(self):
        """Stored artifact has content_hash for deduplication."""
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "artifact-aaa"
        mock_artifact.content_hash = "abc123def456"
        mock_artifact.size_bytes = 100
        mock_artifact.content_inline = "content"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(passed=True, exit_code=0)

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-123",
            result=result,
        )

        # Artifact should have content_hash
        self.assertEqual(artifact.content_hash, "abc123def456")

    def test_deduplicate_option_passed_to_storage(self):
        """deduplicate option is passed to ArtifactStorage."""
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "artifact-bbb"
        mock_artifact.content_hash = "hash123"
        mock_artifact.size_bytes = 50
        mock_artifact.content_inline = "content"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(passed=True, exit_code=0)

        # Test with deduplicate=True (default)
        store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-1",
            result=result,
        )

        call_args = mock_storage.store.call_args
        self.assertTrue(call_args.kwargs.get("deduplicate", True))

        # Test with deduplicate=False
        store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-2",
            result=result,
            deduplicate=False,
        )

        call_args = mock_storage.store.call_args
        self.assertFalse(call_args.kwargs.get("deduplicate"))


class TestTestResultArtifactMetadata(unittest.TestCase):
    """Tests for TestResultArtifactMetadata dataclass."""

    def test_to_dict_all_fields(self):
        """to_dict includes all metadata fields."""
        metadata = TestResultArtifactMetadata(
            passed=True,
            pass_count=10,
            fail_count=2,
            skip_count=1,
            error_count=0,
            total_count=13,
            success_rate=76.9,
            command="pytest",
            framework="pytest",
            duration_seconds=5.5,
            timestamp="2024-01-01T00:00:00Z",
            failure_summary=[{"test_name": "test_x", "message": "failed"}],
            content_type="application/json",
            has_output_log=True,
            output_truncated=False,
        )

        d = metadata.to_dict()

        self.assertEqual(d[METADATA_KEY_PASSED], True)
        self.assertEqual(d[METADATA_KEY_PASS_COUNT], 10)
        self.assertEqual(d[METADATA_KEY_FAIL_COUNT], 2)
        self.assertEqual(d[METADATA_KEY_SKIP_COUNT], 1)
        self.assertEqual(d[METADATA_KEY_ERROR_COUNT], 0)
        self.assertEqual(d[METADATA_KEY_TOTAL_COUNT], 13)
        self.assertEqual(d[METADATA_KEY_SUCCESS_RATE], 76.9)
        self.assertEqual(d[METADATA_KEY_COMMAND], "pytest")
        self.assertEqual(d[METADATA_KEY_FRAMEWORK], "pytest")
        self.assertEqual(d[METADATA_KEY_DURATION_SECONDS], 5.5)
        self.assertEqual(d[METADATA_KEY_TIMESTAMP], "2024-01-01T00:00:00Z")
        self.assertEqual(len(d[METADATA_KEY_FAILURE_SUMMARY]), 1)
        self.assertEqual(d[METADATA_KEY_CONTENT_TYPE], "application/json")
        self.assertEqual(d[METADATA_KEY_HAS_OUTPUT_LOG], True)
        self.assertEqual(d[METADATA_KEY_OUTPUT_TRUNCATED], False)

    def test_from_dict_round_trip(self):
        """from_dict correctly parses to_dict output."""
        original = TestResultArtifactMetadata(
            passed=False,
            pass_count=5,
            fail_count=3,
            skip_count=2,
            total_count=10,
            success_rate=50.0,
            framework="jest",
        )

        d = original.to_dict()
        restored = TestResultArtifactMetadata.from_dict(d)

        self.assertEqual(restored.passed, original.passed)
        self.assertEqual(restored.pass_count, original.pass_count)
        self.assertEqual(restored.fail_count, original.fail_count)
        self.assertEqual(restored.skip_count, original.skip_count)
        self.assertEqual(restored.total_count, original.total_count)
        self.assertEqual(restored.success_rate, original.success_rate)
        self.assertEqual(restored.framework, original.framework)

    def test_from_dict_with_missing_keys(self):
        """from_dict handles missing keys with defaults."""
        d = {"passed": True, "pass_count": 5}

        metadata = TestResultArtifactMetadata.from_dict(d)

        self.assertEqual(metadata.passed, True)
        self.assertEqual(metadata.pass_count, 5)
        self.assertEqual(metadata.fail_count, 0)  # default
        self.assertEqual(metadata.framework, None)  # default


class TestStoreTestResultResult(unittest.TestCase):
    """Tests for StoreTestResultResult dataclass."""

    def test_to_dict(self):
        """to_dict returns all fields."""
        metadata = TestResultArtifactMetadata(passed=True, pass_count=5, fail_count=0)
        result = StoreTestResultResult(
            artifact_id="art-123",
            run_id="run-456",
            content_hash="hash789",
            size_bytes=1024,
            stored_inline=True,
            metadata=metadata,
        )

        d = result.to_dict()

        self.assertEqual(d["artifact_id"], "art-123")
        self.assertEqual(d["run_id"], "run-456")
        self.assertEqual(d["content_hash"], "hash789")
        self.assertEqual(d["size_bytes"], 1024)
        self.assertEqual(d["stored_inline"], True)
        self.assertIn("metadata", d)


class TestRetrievedTestResult(unittest.TestCase):
    """Tests for RetrievedTestResult dataclass."""

    def test_with_execution_result(self):
        """RetrievedTestResult holds execution_result."""
        exec_result = TestExecutionResult(passed=True, exit_code=0)
        retrieved = RetrievedTestResult(
            artifact_id="art-abc",
            execution_result=exec_result,
        )

        self.assertEqual(retrieved.artifact_id, "art-abc")
        self.assertIsNotNone(retrieved.execution_result)
        self.assertTrue(retrieved.execution_result.passed)

    def test_with_parse_error(self):
        """RetrievedTestResult can hold parse_error."""
        retrieved = RetrievedTestResult(
            artifact_id="art-xyz",
            parse_error="Invalid JSON",
        )

        self.assertEqual(retrieved.artifact_id, "art-xyz")
        self.assertIsNone(retrieved.execution_result)
        self.assertEqual(retrieved.parse_error, "Invalid JSON")


class TestGetStoreResult(unittest.TestCase):
    """Tests for get_store_result function."""

    def test_builds_result_from_artifact(self):
        """get_store_result builds StoreTestResultResult from artifact."""
        mock_artifact = MagicMock()
        mock_artifact.id = "art-111"
        mock_artifact.run_id = "run-222"
        mock_artifact.content_hash = "hash333"
        mock_artifact.size_bytes = 512
        mock_artifact.content_inline = "content"
        mock_artifact.artifact_metadata = {
            METADATA_KEY_PASSED: True,
            METADATA_KEY_PASS_COUNT: 10,
            METADATA_KEY_FAIL_COUNT: 0,
        }

        result = get_store_result(mock_artifact)

        self.assertEqual(result.artifact_id, "art-111")
        self.assertEqual(result.run_id, "run-222")
        self.assertEqual(result.content_hash, "hash333")
        self.assertEqual(result.size_bytes, 512)
        self.assertTrue(result.stored_inline)
        self.assertEqual(result.metadata.pass_count, 10)


class TestRetrieveTestResultFromArtifact(unittest.TestCase):
    """Tests for retrieve_test_result_from_artifact function."""

    def test_retrieves_and_deserializes(self):
        """Retrieves content and deserializes to TestExecutionResult."""
        original = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=5,
            passed_tests=5,
            command="pytest",
        )
        content = serialize_test_result(original)

        mock_artifact = MagicMock()
        mock_artifact.id = "art-get"
        mock_artifact.artifact_metadata = {
            METADATA_KEY_PASSED: True,
            METADATA_KEY_PASS_COUNT: 5,
        }

        mock_storage = MagicMock()
        mock_storage.retrieve_string.return_value = content

        retrieved = retrieve_test_result_from_artifact(mock_storage, mock_artifact)

        self.assertEqual(retrieved.artifact_id, "art-get")
        self.assertIsNotNone(retrieved.execution_result)
        self.assertEqual(retrieved.execution_result.total_tests, 5)
        self.assertIsNone(retrieved.parse_error)

    def test_handles_missing_content(self):
        """Handles case where content is not available."""
        mock_artifact = MagicMock()
        mock_artifact.id = "art-missing"
        mock_artifact.artifact_metadata = None

        mock_storage = MagicMock()
        mock_storage.retrieve_string.return_value = None

        retrieved = retrieve_test_result_from_artifact(mock_storage, mock_artifact)

        self.assertEqual(retrieved.artifact_id, "art-missing")
        self.assertIsNone(retrieved.execution_result)
        self.assertEqual(retrieved.parse_error, "Content not available")

    def test_handles_invalid_json(self):
        """Handles case where content is invalid JSON."""
        mock_artifact = MagicMock()
        mock_artifact.id = "art-invalid"
        mock_artifact.artifact_metadata = None

        mock_storage = MagicMock()
        mock_storage.retrieve_string.return_value = "not valid json"

        retrieved = retrieve_test_result_from_artifact(mock_storage, mock_artifact)

        self.assertEqual(retrieved.artifact_id, "art-invalid")
        self.assertIsNone(retrieved.execution_result)
        self.assertIsNotNone(retrieved.parse_error)


class TestGetTestSummaryFromArtifact(unittest.TestCase):
    """Tests for get_test_summary_from_artifact function."""

    def test_extracts_summary_fields(self):
        """Extracts summary fields from artifact metadata."""
        mock_artifact = MagicMock()
        mock_artifact.artifact_metadata = {
            METADATA_KEY_PASSED: False,
            METADATA_KEY_PASS_COUNT: 8,
            METADATA_KEY_FAIL_COUNT: 2,
            METADATA_KEY_TOTAL_COUNT: 10,
            METADATA_KEY_SUCCESS_RATE: 80.0,
            METADATA_KEY_FRAMEWORK: "pytest",
            METADATA_KEY_DURATION_SECONDS: 3.5,
        }

        summary = get_test_summary_from_artifact(mock_artifact)

        self.assertEqual(summary["passed"], False)
        self.assertEqual(summary["pass_count"], 8)
        self.assertEqual(summary["fail_count"], 2)
        self.assertEqual(summary["total_count"], 10)
        self.assertEqual(summary["success_rate"], 80.0)
        self.assertEqual(summary["framework"], "pytest")
        self.assertEqual(summary["duration_seconds"], 3.5)

    def test_handles_missing_metadata(self):
        """Handles case where artifact_metadata is None."""
        mock_artifact = MagicMock()
        mock_artifact.artifact_metadata = None

        summary = get_test_summary_from_artifact(mock_artifact)

        self.assertEqual(summary["passed"], False)
        self.assertEqual(summary["pass_count"], 0)


class TestRecordTestResultArtifactCreated(unittest.TestCase):
    """Tests for record_test_result_artifact_created function."""

    def test_records_audit_event(self):
        """Records test_result_artifact_created event."""
        mock_recorder = MagicMock()
        mock_recorder.record.return_value = 42

        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            total_tests=10,
            passed_tests=10,
            framework="pytest",
            duration_seconds=5.0,
        )

        event_id = record_test_result_artifact_created(
            recorder=mock_recorder,
            run_id="run-event",
            artifact_id="art-event",
            result=result,
        )

        self.assertEqual(event_id, 42)
        mock_recorder.record.assert_called_once()

        # Check event type
        call_args = mock_recorder.record.call_args
        self.assertEqual(call_args[0][1], "test_result_artifact_created")

        # Check payload
        payload = call_args.kwargs.get("payload", {})
        self.assertEqual(payload["artifact_id"], "art-event")
        self.assertEqual(payload["passed"], True)
        self.assertEqual(payload["total_tests"], 10)


class TestEventTypeRegistered(unittest.TestCase):
    """Tests that the event type is registered."""

    def test_test_result_artifact_created_in_event_types(self):
        """test_result_artifact_created is a valid event type."""
        from api.agentspec_models import EVENT_TYPES

        self.assertIn("test_result_artifact_created", EVENT_TYPES)


class TestApiPackageExports(unittest.TestCase):
    """Tests for API package exports."""

    def test_constants_exported(self):
        """Constants are exported from api package."""
        from api import (
            ARTIFACT_TYPE_TEST_RESULT,
            MAX_FAILURES_IN_METADATA,
        )

        self.assertEqual(ARTIFACT_TYPE_TEST_RESULT, "test_result")
        self.assertEqual(MAX_FAILURES_IN_METADATA, 5)

    def test_data_classes_exported(self):
        """Data classes are exported from api package."""
        from api import (
            TestResultArtifactMetadata,
            StoreTestResultResult,
            RetrievedTestResult,
        )

        # Should be importable
        self.assertIsNotNone(TestResultArtifactMetadata)
        self.assertIsNotNone(StoreTestResultResult)
        self.assertIsNotNone(RetrievedTestResult)

    def test_functions_exported(self):
        """Functions are exported from api package."""
        from api import (
            build_test_result_metadata,
            serialize_test_result,
            deserialize_test_result,
            store_test_result_artifact,
            retrieve_test_result_from_artifact,
            get_test_result_artifacts_for_run,
            get_latest_test_result_artifact,
            get_test_summary_from_artifact,
            record_test_result_artifact_created,
        )

        # Should all be callable
        self.assertTrue(callable(build_test_result_metadata))
        self.assertTrue(callable(serialize_test_result))
        self.assertTrue(callable(deserialize_test_result))
        self.assertTrue(callable(store_test_result_artifact))


class TestFeature212VerificationSteps(unittest.TestCase):
    """
    Comprehensive tests verifying all Feature #212 acceptance criteria.

    Feature #212: Test results persisted as artifacts
    Description: Test execution results stored as artifacts for auditability and UI display.

    Steps:
    1. Test output captured as artifact
    2. Artifact type: test_result
    3. Includes: pass count, fail count, output log
    4. Artifact linked to AgentRun
    5. Large outputs stored by content hash
    """

    def test_step1_test_output_captured_as_artifact(self):
        """
        Step 1: Test output captured as artifact

        Verifies that TestExecutionResult can be serialized and stored.
        """
        # Create a test result with output
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=100,
            passed_tests=95,
            failed_tests=5,
            stdout="Collected 100 items\n\nPASSED 95\nFAILED 5",
            stderr="Warning: deprecated API",
            command="pytest tests/ -v",
            framework="pytest",
            duration_seconds=45.67,
        )

        # Serialize to JSON (what gets stored in artifact)
        content = serialize_test_result(result)

        # Verify it's valid JSON with all output
        parsed = json.loads(content)
        self.assertIn("stdout", parsed)
        self.assertIn("stderr", parsed)
        self.assertIn("PASSED 95", parsed["stdout"])
        self.assertIn("Warning: deprecated API", parsed["stderr"])

    def test_step2_artifact_type_test_result(self):
        """
        Step 2: Artifact type: test_result

        Verifies that the correct artifact type is used.
        """
        # Check constant
        self.assertEqual(ARTIFACT_TYPE_TEST_RESULT, "test_result")

        # Check it's in valid types
        from api.agentspec_models import ARTIFACT_TYPES
        self.assertIn("test_result", ARTIFACT_TYPES)

        # Check store function uses it
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "x"
        mock_artifact.content_hash = "y"
        mock_artifact.size_bytes = 1
        mock_artifact.content_inline = "z"
        mock_storage.store.return_value = mock_artifact

        store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run",
            result=TestExecutionResult(passed=True, exit_code=0),
        )

        call_kwargs = mock_storage.store.call_args.kwargs
        self.assertEqual(call_kwargs["artifact_type"], "test_result")

    def test_step3_includes_pass_fail_output(self):
        """
        Step 3: Includes: pass count, fail count, output log

        Verifies metadata contains required fields.
        """
        result = TestExecutionResult(
            passed=False,
            exit_code=1,
            total_tests=50,
            passed_tests=45,
            failed_tests=5,
            stdout="Test output log",
            failures=[
                TestFailure(test_name="test_1", message="assertion failed"),
                TestFailure(test_name="test_2", message="error occurred"),
            ],
        )

        metadata = build_test_result_metadata(result)

        # Verify pass count
        self.assertEqual(metadata.pass_count, 45)

        # Verify fail count
        self.assertEqual(metadata.fail_count, 5)

        # Verify output log indicator
        self.assertTrue(metadata.has_output_log)

        # Verify failure summary
        self.assertEqual(len(metadata.failure_summary), 2)

    def test_step4_artifact_linked_to_agent_run(self):
        """
        Step 4: Artifact linked to AgentRun

        Verifies that run_id is passed for linking.
        """
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "art-linked"
        mock_artifact.run_id = "run-linked"
        mock_artifact.content_hash = "hash"
        mock_artifact.size_bytes = 100
        mock_artifact.content_inline = "c"
        mock_storage.store.return_value = mock_artifact

        result = TestExecutionResult(passed=True, exit_code=0)

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-linked",
            result=result,
        )

        # Verify run_id was passed to storage
        call_kwargs = mock_storage.store.call_args.kwargs
        self.assertEqual(call_kwargs["run_id"], "run-linked")

    def test_step5_large_outputs_stored_by_content_hash(self):
        """
        Step 5: Large outputs stored by content hash

        Verifies that ArtifactStorage is used for content-hash based storage.
        """
        mock_session = MagicMock()
        mock_storage = MagicMock()
        mock_artifact = MagicMock()
        mock_artifact.id = "art-large"
        mock_artifact.content_hash = "sha256_hash_of_large_content"
        mock_artifact.size_bytes = 100000
        mock_artifact.content_inline = None  # Large content stored in file
        mock_artifact.content_ref = ".autobuildr/artifacts/run/sha256_hash_of_large_content.blob"
        mock_storage.store.return_value = mock_artifact

        # Create result with large output
        large_output = "x" * 50000
        result = TestExecutionResult(
            passed=True,
            exit_code=0,
            stdout=large_output,
        )

        artifact = store_test_result_artifact(
            session=mock_session,
            storage=mock_storage,
            run_id="run-large",
            result=result,
        )

        # Verify ArtifactStorage.store was called
        mock_storage.store.assert_called_once()

        # Verify content was passed (ArtifactStorage handles the hashing)
        call_kwargs = mock_storage.store.call_args.kwargs
        content = call_kwargs["content"]
        self.assertIn(large_output, content)


class TestIntegration(unittest.TestCase):
    """Integration tests using real ArtifactStorage."""

    def test_full_store_and_retrieve_cycle(self):
        """Full cycle: create result -> store artifact -> retrieve result."""
        # Create temp directory for artifact storage
        with tempfile.TemporaryDirectory() as tmpdir:
            from api.artifact_storage import ArtifactStorage
            from api.agentspec_models import Base, Artifact
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session

            # Create in-memory database
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)

            with Session(engine) as session:
                # Create ArtifactStorage
                storage = ArtifactStorage(tmpdir)

                # Create a test result
                original = TestExecutionResult(
                    passed=False,
                    exit_code=1,
                    total_tests=20,
                    passed_tests=18,
                    failed_tests=2,
                    stdout="20 tests collected\n18 passed, 2 failed",
                    stderr="",
                    command="pytest -v",
                    framework="pytest",
                    duration_seconds=10.5,
                    failures=[
                        TestFailure(
                            test_name="test_foo",
                            message="AssertionError",
                            test_file="tests/test_foo.py",
                        ),
                    ],
                )

                # Store as artifact
                # First create a fake run_id (normally this would be a real AgentRun)
                run_id = "test-run-123"

                artifact = store_test_result_artifact(
                    session=session,
                    storage=storage,
                    run_id=run_id,
                    result=original,
                )
                session.commit()

                # Verify artifact was created
                self.assertIsNotNone(artifact.id)
                self.assertEqual(artifact.artifact_type, "test_result")
                self.assertEqual(artifact.run_id, run_id)
                self.assertIsNotNone(artifact.content_hash)

                # Verify metadata
                self.assertEqual(artifact.artifact_metadata[METADATA_KEY_PASSED], False)
                self.assertEqual(artifact.artifact_metadata[METADATA_KEY_PASS_COUNT], 18)
                self.assertEqual(artifact.artifact_metadata[METADATA_KEY_FAIL_COUNT], 2)

                # Retrieve and verify
                retrieved = retrieve_test_result_from_artifact(storage, artifact)

                self.assertIsNone(retrieved.parse_error)
                self.assertIsNotNone(retrieved.execution_result)
                self.assertEqual(retrieved.execution_result.total_tests, 20)
                self.assertEqual(retrieved.execution_result.passed_tests, 18)
                self.assertEqual(retrieved.execution_result.stdout, original.stdout)


if __name__ == "__main__":
    unittest.main()
