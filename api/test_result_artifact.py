"""
Test Result Artifact Module
===========================

Feature #212: Test results persisted as artifacts

This module provides functionality to persist test execution results as artifacts
for auditability and UI display.

Key features:
- Test output captured as artifact with type "test_result"
- Metadata includes: pass count, fail count, output log
- Artifact linked to AgentRun via run_id
- Large outputs stored by content hash using ArtifactStorage

Usage:
    from api.test_result_artifact import store_test_result_artifact
    from api.test_runner import TestRunner

    # Execute tests
    runner = TestRunner()
    result = runner.run("pytest tests/ -v")

    # Store result as artifact
    artifact = store_test_result_artifact(
        session=db_session,
        storage=artifact_storage,
        run_id="agent-run-uuid",
        result=result,
    )

    # Retrieve test result from artifact
    retrieved = retrieve_test_result_from_artifact(storage, artifact)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from api.artifact_storage import ArtifactStorage
    from api.agentspec_models import Artifact

from api.test_runner import TestExecutionResult, TestFailure

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Artifact type for test results (matches ARTIFACT_TYPES in agentspec_models.py)
ARTIFACT_TYPE_TEST_RESULT = "test_result"

# Content type for test result artifact
CONTENT_TYPE_JSON = "application/json"

# Maximum number of failure details to include in metadata
# (full details go in artifact content)
MAX_FAILURES_IN_METADATA = 5

# Keys for artifact_metadata schema
METADATA_KEY_PASSED = "passed"
METADATA_KEY_PASS_COUNT = "pass_count"
METADATA_KEY_FAIL_COUNT = "fail_count"
METADATA_KEY_SKIP_COUNT = "skip_count"
METADATA_KEY_ERROR_COUNT = "error_count"
METADATA_KEY_TOTAL_COUNT = "total_count"
METADATA_KEY_SUCCESS_RATE = "success_rate"
METADATA_KEY_COMMAND = "command"
METADATA_KEY_FRAMEWORK = "framework"
METADATA_KEY_DURATION_SECONDS = "duration_seconds"
METADATA_KEY_TIMESTAMP = "timestamp"
METADATA_KEY_FAILURE_SUMMARY = "failure_summary"
METADATA_KEY_CONTENT_TYPE = "content_type"
METADATA_KEY_HAS_OUTPUT_LOG = "has_output_log"
METADATA_KEY_OUTPUT_TRUNCATED = "output_truncated"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TestResultArtifactMetadata:
    """
    Metadata schema for test_result artifacts.

    Feature #212: Step 3 - Includes: pass count, fail count, output log

    This metadata is stored in the artifact_metadata JSON field
    and provides quick access to key test result data without
    needing to deserialize the full artifact content.

    Attributes:
        passed: Overall pass/fail status
        pass_count: Number of tests that passed
        fail_count: Number of tests that failed
        skip_count: Number of tests that were skipped
        error_count: Number of tests that errored
        total_count: Total number of tests executed
        success_rate: Pass rate as percentage (0.0-100.0)
        command: Test command that was executed
        framework: Detected test framework (pytest, unittest, jest, etc.)
        duration_seconds: How long the test execution took
        timestamp: When the test run started
        failure_summary: Truncated summary of failures (max 5)
        content_type: MIME type of artifact content
        has_output_log: Whether stdout/stderr are in content
        output_truncated: Whether output was truncated due to size
    """
    passed: bool
    pass_count: int
    fail_count: int
    skip_count: int = 0
    error_count: int = 0
    total_count: int = 0
    success_rate: float = 100.0
    command: str = ""
    framework: str | None = None
    duration_seconds: float = 0.0
    timestamp: str | None = None
    failure_summary: list[dict[str, str]] = field(default_factory=list)
    content_type: str = CONTENT_TYPE_JSON
    has_output_log: bool = True
    output_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage in artifact_metadata."""
        return {
            METADATA_KEY_PASSED: self.passed,
            METADATA_KEY_PASS_COUNT: self.pass_count,
            METADATA_KEY_FAIL_COUNT: self.fail_count,
            METADATA_KEY_SKIP_COUNT: self.skip_count,
            METADATA_KEY_ERROR_COUNT: self.error_count,
            METADATA_KEY_TOTAL_COUNT: self.total_count,
            METADATA_KEY_SUCCESS_RATE: self.success_rate,
            METADATA_KEY_COMMAND: self.command,
            METADATA_KEY_FRAMEWORK: self.framework,
            METADATA_KEY_DURATION_SECONDS: self.duration_seconds,
            METADATA_KEY_TIMESTAMP: self.timestamp,
            METADATA_KEY_FAILURE_SUMMARY: self.failure_summary,
            METADATA_KEY_CONTENT_TYPE: self.content_type,
            METADATA_KEY_HAS_OUTPUT_LOG: self.has_output_log,
            METADATA_KEY_OUTPUT_TRUNCATED: self.output_truncated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestResultArtifactMetadata":
        """Create instance from dictionary (e.g., from artifact_metadata)."""
        return cls(
            passed=data.get(METADATA_KEY_PASSED, False),
            pass_count=data.get(METADATA_KEY_PASS_COUNT, 0),
            fail_count=data.get(METADATA_KEY_FAIL_COUNT, 0),
            skip_count=data.get(METADATA_KEY_SKIP_COUNT, 0),
            error_count=data.get(METADATA_KEY_ERROR_COUNT, 0),
            total_count=data.get(METADATA_KEY_TOTAL_COUNT, 0),
            success_rate=data.get(METADATA_KEY_SUCCESS_RATE, 100.0),
            command=data.get(METADATA_KEY_COMMAND, ""),
            framework=data.get(METADATA_KEY_FRAMEWORK),
            duration_seconds=data.get(METADATA_KEY_DURATION_SECONDS, 0.0),
            timestamp=data.get(METADATA_KEY_TIMESTAMP),
            failure_summary=data.get(METADATA_KEY_FAILURE_SUMMARY, []),
            content_type=data.get(METADATA_KEY_CONTENT_TYPE, CONTENT_TYPE_JSON),
            has_output_log=data.get(METADATA_KEY_HAS_OUTPUT_LOG, True),
            output_truncated=data.get(METADATA_KEY_OUTPUT_TRUNCATED, False),
        )


@dataclass
class StoreTestResultResult:
    """
    Result of storing a test result as an artifact.

    Attributes:
        artifact_id: ID of the created artifact
        run_id: ID of the AgentRun this artifact is linked to
        content_hash: SHA256 hash of the artifact content
        size_bytes: Size of the stored content
        stored_inline: Whether content was stored inline (vs file)
        metadata: The artifact metadata that was stored
    """
    artifact_id: str
    run_id: str
    content_hash: str
    size_bytes: int
    stored_inline: bool
    metadata: TestResultArtifactMetadata

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "stored_inline": self.stored_inline,
            "metadata": self.metadata.to_dict(),
        }


@dataclass
class RetrievedTestResult:
    """
    Result of retrieving a test result from an artifact.

    Attributes:
        artifact_id: ID of the artifact
        execution_result: Reconstructed TestExecutionResult (if available)
        metadata: Artifact metadata
        raw_content: Raw content as dict (if parsing succeeded)
        parse_error: Error message if parsing failed
    """
    artifact_id: str
    execution_result: TestExecutionResult | None = None
    metadata: TestResultArtifactMetadata | None = None
    raw_content: dict[str, Any] | None = None
    parse_error: str | None = None


# =============================================================================
# Core Functions
# =============================================================================

def build_test_result_metadata(
    result: TestExecutionResult,
    *,
    max_failures: int = MAX_FAILURES_IN_METADATA,
    output_truncated: bool = False,
) -> TestResultArtifactMetadata:
    """
    Build artifact metadata from a TestExecutionResult.

    Feature #212: Step 3 - Includes: pass count, fail count, output log

    Args:
        result: Test execution result to extract metadata from
        max_failures: Maximum number of failures to include in summary
        output_truncated: Whether output was truncated before storage

    Returns:
        TestResultArtifactMetadata ready for storage
    """
    # Build failure summary (truncated list for quick access)
    failure_summary = []
    for failure in result.failures[:max_failures]:
        failure_summary.append({
            "test_name": failure.test_name,
            "message": failure.message[:100] if failure.message else "",  # Truncate message
        })

    return TestResultArtifactMetadata(
        passed=result.passed,
        pass_count=result.passed_tests,
        fail_count=result.failed_tests,
        skip_count=result.skipped_tests,
        error_count=result.error_tests,
        total_count=result.total_tests,
        success_rate=result.success_rate,
        command=result.command,
        framework=result.framework,
        duration_seconds=result.duration_seconds,
        timestamp=result.timestamp.isoformat() if result.timestamp else None,
        failure_summary=failure_summary,
        content_type=CONTENT_TYPE_JSON,
        has_output_log=bool(result.stdout or result.stderr),
        output_truncated=output_truncated,
    )


def serialize_test_result(
    result: TestExecutionResult,
) -> str:
    """
    Serialize a TestExecutionResult to JSON string for artifact storage.

    Feature #212: Step 1 - Test output captured as artifact

    Args:
        result: Test execution result to serialize

    Returns:
        JSON string containing the full test result
    """
    return json.dumps(result.to_dict(), indent=2, default=str)


def deserialize_test_result(
    content: str,
) -> TestExecutionResult:
    """
    Deserialize a TestExecutionResult from JSON string.

    Args:
        content: JSON string from artifact content

    Returns:
        Reconstructed TestExecutionResult

    Raises:
        json.JSONDecodeError: If content is not valid JSON
        KeyError: If required fields are missing
    """
    data = json.loads(content)

    # Reconstruct failures
    failures = []
    for f_data in data.get("failures", []):
        failure = TestFailure(
            test_name=f_data.get("test_name", ""),
            message=f_data.get("message", ""),
            test_file=f_data.get("test_file"),
            test_class=f_data.get("test_class"),
            test_method=f_data.get("test_method"),
            traceback=f_data.get("traceback"),
            line_number=f_data.get("line_number"),
            failure_type=f_data.get("failure_type", "assertion"),
        )
        failures.append(failure)

    # Parse timestamp
    timestamp = None
    if data.get("timestamp"):
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)

    return TestExecutionResult(
        passed=data.get("passed", False),
        exit_code=data.get("exit_code"),
        expected_exit_code=data.get("expected_exit_code", 0),
        total_tests=data.get("total_tests", 0),
        passed_tests=data.get("passed_tests", 0),
        failed_tests=data.get("failed_tests", 0),
        skipped_tests=data.get("skipped_tests", 0),
        error_tests=data.get("error_tests", 0),
        failures=failures,
        stdout=data.get("stdout", ""),
        stderr=data.get("stderr", ""),
        command=data.get("command", ""),
        working_directory=data.get("working_directory"),
        timeout_seconds=data.get("timeout_seconds", 300),
        duration_seconds=data.get("duration_seconds", 0.0),
        framework=data.get("framework"),
        framework_version=data.get("framework_version"),
        timestamp=timestamp or datetime.now(timezone.utc),
        error_message=data.get("error_message"),
    )


def store_test_result_artifact(
    session: "Session",
    storage: "ArtifactStorage",
    run_id: str,
    result: TestExecutionResult,
    *,
    path: str | None = None,
    deduplicate: bool = True,
) -> "Artifact":
    """
    Store a test execution result as an artifact.

    Feature #212: Test results persisted as artifacts

    This function:
    1. Serializes the TestExecutionResult to JSON (Step 1: Test output captured)
    2. Creates an artifact with type "test_result" (Step 2: Artifact type)
    3. Stores metadata with pass/fail counts (Step 3: Includes counts/log)
    4. Links artifact to AgentRun via run_id (Step 4: Artifact linked)
    5. Uses ArtifactStorage for content-hash storage (Step 5: Large outputs)

    Args:
        session: SQLAlchemy database session
        storage: ArtifactStorage instance for content storage
        run_id: ID of the AgentRun this result belongs to
        result: TestExecutionResult to store
        path: Optional source path for the artifact
        deduplicate: If True, return existing artifact with same hash

    Returns:
        Created (or deduplicated) Artifact record

    Example:
        >>> from api.artifact_storage import ArtifactStorage
        >>> storage = ArtifactStorage("/path/to/project")
        >>> artifact = store_test_result_artifact(
        ...     session=db_session,
        ...     storage=storage,
        ...     run_id="abc-123",
        ...     result=test_result,
        ... )
        >>> print(artifact.artifact_type)  # "test_result"
        >>> print(artifact.artifact_metadata["pass_count"])  # 42
    """
    _logger.info(
        "Storing test result artifact: run_id=%s, passed=%s, total=%d",
        run_id, result.passed, result.total_tests
    )

    # Step 1: Serialize test result to JSON
    content = serialize_test_result(result)

    # Step 3: Build metadata with pass/fail counts
    metadata = build_test_result_metadata(result)

    # Steps 2, 4, 5: Create artifact using ArtifactStorage
    # - artifact_type="test_result" (Step 2)
    # - run_id links to AgentRun (Step 4)
    # - ArtifactStorage handles content-hash storage (Step 5)
    artifact = storage.store(
        session=session,
        run_id=run_id,
        artifact_type=ARTIFACT_TYPE_TEST_RESULT,
        content=content,
        path=path,
        metadata=metadata.to_dict(),
        deduplicate=deduplicate,
    )

    _logger.info(
        "Test result artifact created: artifact_id=%s, hash=%s, size=%d bytes",
        artifact.id, artifact.content_hash, artifact.size_bytes
    )

    return artifact


def get_store_result(
    artifact: "Artifact",
) -> StoreTestResultResult:
    """
    Build a StoreTestResultResult from a stored artifact.

    Args:
        artifact: Stored artifact record

    Returns:
        StoreTestResultResult with storage details
    """
    metadata = TestResultArtifactMetadata.from_dict(
        artifact.artifact_metadata or {}
    )

    return StoreTestResultResult(
        artifact_id=artifact.id,
        run_id=artifact.run_id,
        content_hash=artifact.content_hash,
        size_bytes=artifact.size_bytes,
        stored_inline=artifact.content_inline is not None,
        metadata=metadata,
    )


def retrieve_test_result_from_artifact(
    storage: "ArtifactStorage",
    artifact: "Artifact",
) -> RetrievedTestResult:
    """
    Retrieve and deserialize a test result from an artifact.

    Args:
        storage: ArtifactStorage instance for content retrieval
        artifact: Artifact record to retrieve from

    Returns:
        RetrievedTestResult with execution result and metadata
    """
    _logger.debug("Retrieving test result from artifact: %s", artifact.id)

    # Get metadata
    metadata = None
    if artifact.artifact_metadata:
        try:
            metadata = TestResultArtifactMetadata.from_dict(artifact.artifact_metadata)
        except Exception as e:
            _logger.warning("Failed to parse artifact metadata: %s", e)

    # Retrieve content
    content = storage.retrieve_string(artifact)
    if content is None:
        return RetrievedTestResult(
            artifact_id=artifact.id,
            metadata=metadata,
            parse_error="Content not available",
        )

    # Parse content
    try:
        raw_content = json.loads(content)
        execution_result = deserialize_test_result(content)

        return RetrievedTestResult(
            artifact_id=artifact.id,
            execution_result=execution_result,
            metadata=metadata,
            raw_content=raw_content,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        _logger.warning("Failed to parse artifact content: %s", e)
        return RetrievedTestResult(
            artifact_id=artifact.id,
            metadata=metadata,
            parse_error=str(e),
        )


def get_test_result_artifacts_for_run(
    session: "Session",
    run_id: str,
) -> list["Artifact"]:
    """
    Get all test_result artifacts for a specific AgentRun.

    Args:
        session: SQLAlchemy database session
        run_id: ID of the AgentRun

    Returns:
        List of Artifact records with type "test_result"
    """
    from api.agentspec_models import Artifact

    return (
        session.query(Artifact)
        .filter(
            Artifact.run_id == run_id,
            Artifact.artifact_type == ARTIFACT_TYPE_TEST_RESULT,
        )
        .order_by(Artifact.created_at.desc())
        .all()
    )


def get_latest_test_result_artifact(
    session: "Session",
    run_id: str,
) -> "Artifact | None":
    """
    Get the most recent test_result artifact for a run.

    Args:
        session: SQLAlchemy database session
        run_id: ID of the AgentRun

    Returns:
        Most recent Artifact with type "test_result", or None
    """
    from api.agentspec_models import Artifact

    return (
        session.query(Artifact)
        .filter(
            Artifact.run_id == run_id,
            Artifact.artifact_type == ARTIFACT_TYPE_TEST_RESULT,
        )
        .order_by(Artifact.created_at.desc())
        .first()
    )


def get_test_summary_from_artifact(
    artifact: "Artifact",
) -> dict[str, Any]:
    """
    Get a summary of test results from artifact metadata.

    This provides quick access to key metrics without deserializing
    the full artifact content.

    Args:
        artifact: Artifact record with type "test_result"

    Returns:
        Dictionary with test summary:
        - passed: bool
        - pass_count: int
        - fail_count: int
        - total_count: int
        - success_rate: float
        - framework: str | None
        - duration_seconds: float
    """
    metadata = artifact.artifact_metadata or {}

    return {
        "passed": metadata.get(METADATA_KEY_PASSED, False),
        "pass_count": metadata.get(METADATA_KEY_PASS_COUNT, 0),
        "fail_count": metadata.get(METADATA_KEY_FAIL_COUNT, 0),
        "total_count": metadata.get(METADATA_KEY_TOTAL_COUNT, 0),
        "success_rate": metadata.get(METADATA_KEY_SUCCESS_RATE, 0.0),
        "framework": metadata.get(METADATA_KEY_FRAMEWORK),
        "duration_seconds": metadata.get(METADATA_KEY_DURATION_SECONDS, 0.0),
    }


# =============================================================================
# Integration with EventRecorder
# =============================================================================

def record_test_result_artifact_created(
    recorder: Any,  # EventRecorder
    run_id: str,
    artifact_id: str,
    result: TestExecutionResult,
) -> int:
    """
    Record an audit event when a test result artifact is created.

    This creates a "test_result_artifact_created" event that links
    the test execution to its stored artifact.

    Args:
        recorder: EventRecorder instance
        run_id: AgentRun ID
        artifact_id: Created artifact ID
        result: TestExecutionResult that was stored

    Returns:
        Event ID
    """
    payload = {
        "artifact_id": artifact_id,
        "passed": result.passed,
        "total_tests": result.total_tests,
        "passed_tests": result.passed_tests,
        "failed_tests": result.failed_tests,
        "framework": result.framework,
        "duration_seconds": result.duration_seconds,
    }

    return recorder.record(
        run_id,
        "test_result_artifact_created",
        payload=payload,
    )
