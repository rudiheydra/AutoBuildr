"""
Test Suite for Feature #96: Startup health check auto-fixes self-references with warning

This tests verifies that:
1. Features with self-references (A -> A) in the database are detected at startup
2. Self-references are automatically removed from the feature's dependencies
3. A WARNING level log is emitted with the feature ID and action taken
4. The orchestrator continues to normal operation after the fix

Verification Steps from Feature #96:
1. Insert a feature with self-reference into database
2. Start the orchestrator
3. Verify the self-reference is automatically removed from the feature
4. Verify a WARNING level log is emitted with feature ID and action taken
5. Verify orchestrator continues to normal operation after fix
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.database import Base, Feature, create_database


class TestSelfReferenceAutoFix:
    """Tests for automatic self-reference fixing on startup."""

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

    def test_step1_insert_feature_with_self_reference(self, create_test_db):
        """Step 1: Insert a feature with self-reference into database."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature that depends on itself (self-reference)
            feature = Feature(
                id=100,
                priority=1,
                category="test",
                name="Self-referencing feature",
                description="This feature depends on itself (invalid)",
                steps=["Step 1", "Step 2"],
                passes=False,
                in_progress=False,
                dependencies=[100],  # Self-reference!
            )
            session.add(feature)
            session.commit()

            # Verify the self-reference was inserted
            loaded = session.query(Feature).filter(Feature.id == 100).first()
            assert loaded is not None
            assert loaded.dependencies == [100], "Self-reference should be in dependencies"
        finally:
            session.close()

    def test_step2_and_step3_health_check_removes_self_reference(self, create_test_db):
        """Step 2 & 3: Start the orchestrator and verify self-reference is removed."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Insert a feature with self-reference
            feature = Feature(
                id=101,
                priority=1,
                category="test",
                name="Self-referencing feature for removal test",
                description="This feature depends on itself",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[101],  # Self-reference!
            )
            session.add(feature)
            session.commit()
            session.close()

            # Create orchestrator and run health check
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            # Run the health check
            result = orchestrator._run_dependency_health_check()
            assert result is True, "Health check should return True (fixed issues)"

            # Verify the self-reference was removed
            new_session = session_maker()
            try:
                fixed_feature = new_session.query(Feature).filter(Feature.id == 101).first()
                assert fixed_feature is not None
                assert fixed_feature.dependencies == [], (
                    f"Self-reference should be removed, got: {fixed_feature.dependencies}"
                )
            finally:
                new_session.close()

        finally:
            if not session.is_active:
                pass  # Session already closed

    def test_step4_warning_log_emitted(self, create_test_db, caplog):
        """Step 4: Verify a WARNING level log is emitted with feature ID and action taken."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Insert a feature with self-reference
            feature = Feature(
                id=102,
                priority=1,
                category="test",
                name="Feature for warning log test",
                description="Testing WARNING log emission",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[102],  # Self-reference!
            )
            session.add(feature)
            session.commit()
            session.close()

            # Create orchestrator and run health check with logging capture
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            # Enable logging capture for WARNING level
            with caplog.at_level(logging.WARNING, logger="parallel_orchestrator"):
                result = orchestrator._run_dependency_health_check()

            assert result is True, "Health check should succeed"

            # Verify WARNING log was emitted
            warning_logs = [
                record for record in caplog.records
                if record.levelno == logging.WARNING
                and "parallel_orchestrator" in record.name
            ]

            assert len(warning_logs) > 0, (
                f"Expected at least one WARNING log from parallel_orchestrator, "
                f"got {len(warning_logs)}. Logs: {[r.message for r in caplog.records]}"
            )

            # Verify log content includes feature ID and action
            log_messages = " ".join(record.message for record in warning_logs)
            assert "102" in log_messages, (
                f"WARNING log should mention feature ID 102, got: {log_messages}"
            )
            assert "self-reference" in log_messages.lower(), (
                f"WARNING log should mention 'self-reference', got: {log_messages}"
            )
            assert "auto-fix" in log_messages.lower() or "removed" in log_messages.lower(), (
                f"WARNING log should indicate the action taken, got: {log_messages}"
            )

        finally:
            pass  # Session already closed

    def test_step5_orchestrator_continues_after_fix(self, create_test_db):
        """Step 5: Verify orchestrator continues to normal operation after fix."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Insert a feature with self-reference
            feature = Feature(
                id=103,
                priority=1,
                category="test",
                name="Feature for continuation test",
                description="Testing orchestrator continues after fix",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[103],  # Self-reference!
            )
            session.add(feature)
            session.commit()
            session.close()

            # Create orchestrator
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            # Run health check
            result = orchestrator._run_dependency_health_check()
            assert result is True, "Health check should return True"

            # Verify orchestrator state is valid and can continue
            # (e.g., can call get_ready_features without errors)
            try:
                ready = orchestrator.get_ready_features()
                # Should include the fixed feature since it now has no dependencies
                assert isinstance(ready, list), "get_ready_features should return a list"
            except Exception as e:
                pytest.fail(f"Orchestrator should continue after fix, but got error: {e}")

        finally:
            pass


class TestMultipleSelfReferences:
    """Tests for multiple features with self-references."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_multiple_self_references_fixed(self, create_test_db, caplog):
        """Multiple features with self-references should all be fixed."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create multiple features with self-references
            for i in range(200, 205):
                feature = Feature(
                    id=i,
                    priority=i - 199,
                    category="test",
                    name=f"Self-ref feature {i}",
                    description=f"Feature {i} depends on itself",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[i],  # Self-reference!
                )
                session.add(feature)
            session.commit()
            session.close()

            # Run health check
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            with caplog.at_level(logging.WARNING, logger="parallel_orchestrator"):
                result = orchestrator._run_dependency_health_check()

            assert result is True

            # Verify all self-references were removed
            new_session = session_maker()
            try:
                for i in range(200, 205):
                    feature = new_session.query(Feature).filter(Feature.id == i).first()
                    assert feature.dependencies == [], (
                        f"Feature {i} should have empty dependencies, got: {feature.dependencies}"
                    )
            finally:
                new_session.close()

            # Verify multiple WARNING logs were emitted
            warning_logs = [
                record for record in caplog.records
                if record.levelno == logging.WARNING
                and "parallel_orchestrator" in record.name
            ]
            assert len(warning_logs) == 5, (
                f"Expected 5 WARNING logs (one per feature), got {len(warning_logs)}"
            )

        finally:
            pass

    def test_self_reference_with_other_dependencies_preserved(self, create_test_db):
        """Self-reference should be removed while preserving other valid dependencies."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a valid dependency target
            dep_feature = Feature(
                id=300,
                priority=1,
                category="test",
                name="Valid dependency",
                description="This is a valid dependency target",
                steps=["Step 1"],
                passes=True,  # Already passing
                in_progress=False,
                dependencies=[],
            )
            session.add(dep_feature)

            # Create a feature with self-reference AND a valid dependency
            feature = Feature(
                id=301,
                priority=2,
                category="test",
                name="Mixed dependencies feature",
                description="Has self-reference and valid dependency",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[301, 300],  # Self-ref + valid dep
            )
            session.add(feature)
            session.commit()
            session.close()

            # Run health check
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            result = orchestrator._run_dependency_health_check()
            assert result is True

            # Verify self-reference removed but valid dependency preserved
            new_session = session_maker()
            try:
                fixed_feature = new_session.query(Feature).filter(Feature.id == 301).first()
                assert fixed_feature.dependencies == [300], (
                    f"Expected [300], got: {fixed_feature.dependencies}"
                )
            finally:
                new_session.close()

        finally:
            pass


class TestWarningLogContent:
    """Tests for WARNING log message content."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_warning_log_includes_original_and_new_deps(self, create_test_db, caplog):
        """WARNING log should include both original and new dependencies."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create a feature with self-reference and other deps
            feature = Feature(
                id=400,
                priority=1,
                category="test",
                name="Feature for log content test",
                description="Testing log content",
                steps=["Step 1"],
                passes=False,
                in_progress=False,
                dependencies=[400, 401, 402],  # Self-ref + two other deps
            )
            session.add(feature)

            # Create the other dependency features so they're not "missing"
            for dep_id in [401, 402]:
                dep = Feature(
                    id=dep_id,
                    priority=1,
                    category="test",
                    name=f"Dep {dep_id}",
                    description="Dependency",
                    steps=["Step 1"],
                    passes=True,
                    in_progress=False,
                    dependencies=[],
                )
                session.add(dep)

            session.commit()
            session.close()

            # Run health check with logging
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            with caplog.at_level(logging.WARNING, logger="parallel_orchestrator"):
                orchestrator._run_dependency_health_check()

            # Find the WARNING log for feature 400
            warning_logs = [
                record for record in caplog.records
                if record.levelno == logging.WARNING
                and "parallel_orchestrator" in record.name
                and "400" in record.message
            ]

            assert len(warning_logs) == 1, f"Expected 1 warning for feature 400, got: {len(warning_logs)}"

            log_msg = warning_logs[0].message
            # Original deps should be mentioned
            assert "[400, 401, 402]" in log_msg or "400, 401, 402" in log_msg, (
                f"Log should mention original dependencies, got: {log_msg}"
            )
            # New deps should be mentioned
            assert "[401, 402]" in log_msg or "401, 402" in log_msg, (
                f"Log should mention new dependencies, got: {log_msg}"
            )

        finally:
            pass


class TestNoSelfReferences:
    """Tests for when there are no self-references."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_no_warning_when_no_self_references(self, create_test_db, caplog):
        """No WARNING log should be emitted when there are no self-references."""
        engine, session_maker, project_dir = create_test_db
        session = session_maker()

        try:
            # Create valid features without self-references
            for i in range(500, 503):
                feature = Feature(
                    id=i,
                    priority=i - 499,
                    category="test",
                    name=f"Valid feature {i}",
                    description="No self-reference",
                    steps=["Step 1"],
                    passes=False,
                    in_progress=False,
                    dependencies=[] if i == 500 else [i - 1],  # Valid chain
                )
                session.add(feature)
            session.commit()
            session.close()

            # Run health check
            from parallel_orchestrator import ParallelOrchestrator

            orchestrator = ParallelOrchestrator(
                project_dir=project_dir,
                max_concurrency=1,
            )

            with caplog.at_level(logging.WARNING, logger="parallel_orchestrator"):
                result = orchestrator._run_dependency_health_check()

            assert result is True

            # No WARNING logs about self-references
            self_ref_warnings = [
                record for record in caplog.records
                if record.levelno == logging.WARNING
                and "parallel_orchestrator" in record.name
                and "self-reference" in record.message.lower()
            ]
            assert len(self_ref_warnings) == 0, (
                f"Expected no self-reference warnings, got: {[r.message for r in self_ref_warnings]}"
            )

        finally:
            pass


class TestEmptyDatabase:
    """Tests for empty database edge case."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with a database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            yield project_dir

    @pytest.fixture
    def create_test_db(self, temp_project_dir):
        """Create a test database."""
        engine, session_maker = create_database(temp_project_dir)
        return engine, session_maker, temp_project_dir

    def test_empty_database_health_check_passes(self, create_test_db):
        """Health check should pass without errors on empty database."""
        engine, session_maker, project_dir = create_test_db

        from parallel_orchestrator import ParallelOrchestrator

        orchestrator = ParallelOrchestrator(
            project_dir=project_dir,
            max_concurrency=1,
        )

        result = orchestrator._run_dependency_health_check()
        assert result is True, "Health check should pass on empty database"
