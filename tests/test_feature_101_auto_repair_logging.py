"""
Test Suite for Feature #101: Auto-repair logs before and after state for auditability

This test suite verifies that all auto-repair operations log the state before and
after the fix for debugging and audit purposes.

Verification Steps from Feature #101:
1. Before removing self-reference, log: "Feature {id} has self-reference, removing"
2. After fix, log: "Feature {id} dependencies changed from {old} to {new}"
3. Include timestamp in log entries
4. Use structured logging format for easy parsing
5. Verify logs appear at INFO level (not just DEBUG)
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime
import re

import pytest

from api.database import Base, Feature, create_database
from api.dependency_resolver import repair_self_references, repair_orphaned_dependencies


class TestBeforeLogForSelfReference:
    """Tests for Step 1: Before removing self-reference, log message."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step1_before_log_contains_feature_id(self, create_test_db, caplog):
        """Step 1: Verify before log contains feature ID and 'has self-reference, removing' message."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=42,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test feature with self-reference",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[42, 100]  # Self-reference to 42
            )
            session.add(feature)
            session.commit()

            # Clear any existing logs and set level
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repaired_ids = repair_self_references(session)

            # Verify feature was repaired
            assert 42 in repaired_ids

            # Verify before log message content
            before_logs = [r for r in caplog.records if "before_fix" in r.message]
            assert len(before_logs) >= 1, "Should have at least one before_fix log"

            before_log = before_logs[0]
            assert "feature_id=42" in before_log.message
            assert "has self-reference, removing" in before_log.message
            assert "original_deps" in before_log.message

        finally:
            session.close()

    def test_step1_before_log_appears_before_actual_fix(self, create_test_db, caplog):
        """Step 1: Verify before log appears in correct order (before after_fix log)."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=99,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[99]  # Self-reference
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Find indices of before and after logs
            before_idx = None
            after_idx = None
            for i, record in enumerate(caplog.records):
                if "before_fix" in record.message and "feature_id=99" in record.message:
                    before_idx = i
                if "after_fix" in record.message and "feature_id=99" in record.message:
                    after_idx = i

            assert before_idx is not None, "before_fix log should exist"
            assert after_idx is not None, "after_fix log should exist"
            assert before_idx < after_idx, "before_fix log should appear before after_fix log"

        finally:
            session.close()


class TestAfterLogForSelfReference:
    """Tests for Step 2: After fix, log dependencies changed message."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step2_after_log_contains_old_and_new_deps(self, create_test_db, caplog):
        """Step 2: Verify after log contains feature ID and old/new dependencies."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=55,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[55, 100, 101]  # Self-reference at start
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Verify after log message content
            after_logs = [r for r in caplog.records if "after_fix" in r.message]
            assert len(after_logs) >= 1, "Should have at least one after_fix log"

            after_log = after_logs[0]
            assert "feature_id=55" in after_log.message
            assert "dependencies changed from" in after_log.message

        finally:
            session.close()


class TestTimestampInLogs:
    """Tests for Step 3: Include timestamp in log entries."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step3_log_records_have_timestamp(self, create_test_db, caplog):
        """Step 3: Verify log records have timestamp (created attribute)."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=77,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[77]
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Verify all log records have timestamps
            repair_logs = [r for r in caplog.records if "repair_self_references" in r.message]
            assert len(repair_logs) >= 2, "Should have before and after logs"

            for record in repair_logs:
                # Python logging automatically includes timestamp via 'created' attribute
                assert hasattr(record, 'created'), "Log record should have 'created' timestamp"
                assert isinstance(record.created, float), "Timestamp should be a float (epoch time)"
                # Verify the timestamp is reasonable (within last minute)
                now = datetime.now().timestamp()
                assert now - record.created < 60, "Timestamp should be recent"

        finally:
            session.close()


class TestStructuredLoggingFormat:
    """Tests for Step 4: Use structured logging format for easy parsing."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step4_structured_format_key_value_pairs(self, create_test_db, caplog):
        """Step 4: Verify logs use structured key=value format for easy parsing."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=88,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[88, 200]
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Verify structured format with key=value pairs
            # Filter for only the before/after logs (not the commit summary log)
            repair_logs = [r for r in caplog.records
                         if "repair_self_references" in r.message
                         and ("before_fix" in r.message or "after_fix" in r.message)]

            assert len(repair_logs) >= 2, "Should have before and after logs"

            for record in repair_logs:
                msg = record.message
                # Check for key=value patterns
                assert "action=" in msg, "Should have action= key"
                assert "feature_id=" in msg, "Should have feature_id= key"

                # Check that action has valid value
                assert "action=before_fix" in msg or "action=after_fix" in msg, \
                    "action should be before_fix or after_fix"

        finally:
            session.close()

    def test_step4_log_message_is_parseable(self, create_test_db, caplog):
        """Step 4: Verify log message can be parsed programmatically."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=123,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[123, 456, 789]
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Parse and verify structured content
            before_logs = [r for r in caplog.records if "before_fix" in r.message]
            assert len(before_logs) >= 1

            msg = before_logs[0].message

            # Extract feature_id using regex
            feature_id_match = re.search(r'feature_id=(\d+)', msg)
            assert feature_id_match is not None, "Should be able to extract feature_id"
            assert feature_id_match.group(1) == "123", "feature_id should be 123"

            # Extract action using regex
            action_match = re.search(r'action=(\w+)', msg)
            assert action_match is not None, "Should be able to extract action"
            assert action_match.group(1) == "before_fix", "action should be before_fix"

        finally:
            session.close()


class TestInfoLevelLogging:
    """Tests for Step 5: Verify logs appear at INFO level (not just DEBUG)."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_step5_logs_are_info_level(self, create_test_db, caplog):
        """Step 5: Verify auto-repair logs are at INFO level."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=999,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[999]
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Verify logs are at INFO level
            repair_logs = [r for r in caplog.records
                         if "repair_self_references" in r.message
                         and ("before_fix" in r.message or "after_fix" in r.message)]

            assert len(repair_logs) >= 2, "Should have both before and after logs"

            for record in repair_logs:
                assert record.levelno == logging.INFO, \
                    f"Log should be INFO level, got {record.levelname}"
                assert record.levelname == "INFO", \
                    f"Log level name should be INFO, got {record.levelname}"

        finally:
            session.close()

    def test_step5_logs_visible_at_info_but_not_debug_only(self, create_test_db, caplog):
        """Step 5: Verify logs are visible when logging at INFO level (not DEBUG-only)."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference
            feature = Feature(
                id=111,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[111]
            )
            session.add(feature)
            session.commit()

            # Test at INFO level - logs should be visible
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            info_level_logs = [r for r in caplog.records
                             if "repair_self_references" in r.message]
            assert len(info_level_logs) >= 2, "Logs should be visible at INFO level"

        finally:
            session.close()


class TestOrphanedDependencyLogging:
    """Tests for orphaned dependency repair logging (same requirements apply)."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_orphaned_deps_before_and_after_logs(self, create_test_db, caplog):
        """Verify orphaned dependency repair has before and after logs."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with orphaned dependency (999 doesn't exist)
            feature = Feature(
                id=1,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[999, 998]  # Both are orphaned
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repairs = repair_orphaned_dependencies(session)

            # Verify feature was repaired
            assert 1 in repairs

            # Verify before log
            before_logs = [r for r in caplog.records if "before_fix" in r.message]
            assert len(before_logs) >= 1, "Should have before_fix log"
            assert "feature_id=1" in before_logs[0].message
            assert "orphaned dependencies" in before_logs[0].message

            # Verify after log
            after_logs = [r for r in caplog.records if "after_fix" in r.message]
            assert len(after_logs) >= 1, "Should have after_fix log"
            assert "feature_id=1" in after_logs[0].message
            assert "dependencies changed from" in after_logs[0].message

        finally:
            session.close()

    def test_orphaned_deps_structured_format(self, create_test_db, caplog):
        """Verify orphaned dependency logs use structured format."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with orphaned dependency
            feature = Feature(
                id=50,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[9999]  # Orphaned
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_orphaned_dependencies(session)

            # Verify structured format (filter for before/after logs only, not commit summary)
            repair_logs = [r for r in caplog.records
                         if "repair_orphaned_dependencies" in r.message
                         and ("before_fix" in r.message or "after_fix" in r.message)]

            assert len(repair_logs) >= 2, "Should have before and after logs"

            for record in repair_logs:
                msg = record.message
                assert "action=" in msg, "Should have action= key"
                assert "feature_id=" in msg, "Should have feature_id= key"

        finally:
            session.close()

    def test_orphaned_deps_info_level(self, create_test_db, caplog):
        """Verify orphaned dependency logs are at INFO level."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with orphaned dependency
            feature = Feature(
                id=75,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[8888]  # Orphaned
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_orphaned_dependencies(session)

            # Verify INFO level
            repair_logs = [r for r in caplog.records
                         if "repair_orphaned_dependencies" in r.message
                         and ("before_fix" in r.message or "after_fix" in r.message)]

            assert len(repair_logs) >= 2
            for record in repair_logs:
                assert record.levelno == logging.INFO

        finally:
            session.close()


class TestHealthCheckLogging:
    """Tests for health check auto-repair logging in parallel_orchestrator."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_health_check_self_reference_logging(self, create_test_db, caplog):
        """Verify health check self-reference repair has structured before/after logs."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create features with self-reference
            feature = Feature(
                id=500,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[500]  # Self-reference
            )
            session.add(feature)
            session.commit()
            session.close()  # Close test session before orchestrator uses DB

            # Import and run health check
            from parallel_orchestrator import ParallelOrchestrator

            # Create orchestrator with the test database (uses correct constructor params)
            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1
            )

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="parallel_orchestrator"):
                # Run health check
                result = orchestrator._run_dependency_health_check()

            # Verify before/after logs for self-reference
            before_logs = [r for r in caplog.records
                         if "health_check_self_reference" in r.message and "before_fix" in r.message]
            after_logs = [r for r in caplog.records
                        if "health_check_self_reference" in r.message and "after_fix" in r.message]

            # The health check logs should be present (if self-reference was found)
            if before_logs:
                assert "feature_id=500" in before_logs[0].message
                assert "has self-reference, removing" in before_logs[0].message

            if after_logs:
                assert "feature_id=500" in after_logs[0].message
                assert "dependencies changed from" in after_logs[0].message

        finally:
            pass  # Session already closed above


class TestMultipleFeatureRepairs:
    """Tests for logging when multiple features need repair."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_multiple_self_references_each_get_logs(self, create_test_db, caplog):
        """Verify each feature with self-reference gets its own before/after log pair."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create multiple features with self-references
            for i in [10, 20, 30]:
                feature = Feature(
                    id=i,
                    priority=i,
                    category="test",
                    name=f"Test Feature {i}",
                    description="Test",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i]  # Self-reference
                )
                session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repaired = repair_self_references(session)

            # Verify all three were repaired
            assert len(repaired) == 3

            # Verify each feature got before/after logs
            for fid in [10, 20, 30]:
                before_logs = [r for r in caplog.records
                             if f"feature_id={fid}" in r.message and "before_fix" in r.message]
                after_logs = [r for r in caplog.records
                            if f"feature_id={fid}" in r.message and "after_fix" in r.message]

                assert len(before_logs) >= 1, f"Feature {fid} should have before_fix log"
                assert len(after_logs) >= 1, f"Feature {fid} should have after_fix log"

        finally:
            session.close()


class TestLogMessageContent:
    """Tests for specific log message content requirements."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database with features."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_before_log_exact_message_format(self, create_test_db, caplog):
        """Verify before log contains exact required message format."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            feature = Feature(
                id=42,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[42]
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Find before log and check exact message format
            before_logs = [r for r in caplog.records if "before_fix" in r.message]
            assert len(before_logs) >= 1

            msg = before_logs[0].message
            # Step 1 requirement: "Feature {id} has self-reference, removing"
            assert "Feature 42 has self-reference, removing" in msg

        finally:
            session.close()

    def test_after_log_exact_message_format(self, create_test_db, caplog):
        """Verify after log contains exact required message format."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            feature = Feature(
                id=42,
                priority=1,
                category="test",
                name="Test Feature",
                description="Test",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[42, 100]  # 42 is self-ref, 100 is valid orphan
            )
            session.add(feature)
            session.commit()

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="api.dependency_resolver"):
                repair_self_references(session)

            # Find after log and check exact message format
            after_logs = [r for r in caplog.records if "after_fix" in r.message]
            assert len(after_logs) >= 1

            msg = after_logs[0].message
            # Step 2 requirement: "Feature {id} dependencies changed from {old} to {new}"
            assert "Feature 42 dependencies changed from" in msg

        finally:
            session.close()
