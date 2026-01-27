"""
Test Feature #77: Database Transaction Safety

Tests ensure database operations in kernel are transaction-safe with proper locking.

Feature Steps:
1. Use SQLAlchemy session per-run
2. Commit after each event record for durability
3. Handle IntegrityError from concurrent inserts
4. Use SELECT FOR UPDATE when modifying run status
5. Rollback on exception and record error
6. Close session in finally block
"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, OperationalError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent, AcceptanceSpec
from api.harness_kernel import (
    HarnessKernel,
    BudgetTracker,
    MaxTurnsExceeded,
    TimeoutSecondsExceeded,
    TransactionError,
    ConcurrentModificationError,
    DatabaseLockError,
    commit_with_retry,
    rollback_and_record_error,
    get_run_with_lock,
    safe_add_and_commit_event,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_spec(test_db):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id=str(uuid.uuid4()),
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="coding",
        tool_policy={"policy_version": "v1", "allowed_tools": []},
        max_turns=10,
        timeout_seconds=300,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(spec)
    test_db.commit()
    test_db.refresh(spec)
    return spec


@pytest.fixture
def sample_run(test_db, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id=str(uuid.uuid4()),
        agent_spec_id=sample_spec.id,
        status="pending",
        turns_used=0,
        tokens_in=0,
        tokens_out=0,
        retry_count=0,
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(run)
    test_db.commit()
    test_db.refresh(run)
    return run


# =============================================================================
# Step 1: Use SQLAlchemy session per-run
# =============================================================================

class TestStep1_SessionPerRun:
    """Tests for Feature #77, Step 1: Use SQLAlchemy session per-run"""

    def test_kernel_uses_provided_session(self, test_db, sample_spec):
        """Verify kernel uses the provided SQLAlchemy session."""
        kernel = HarnessKernel(test_db)
        assert kernel.db is test_db

    def test_kernel_session_isolated(self, test_db, sample_spec):
        """Verify kernel operations use the session consistently."""
        kernel = HarnessKernel(test_db)
        run = kernel._create_run_for_spec(sample_spec)

        # The run should be in the same session
        assert run in test_db
        assert test_db.query(AgentRun).filter_by(id=run.id).first() is not None

    def test_multiple_kernels_use_separate_sessions(self, sample_spec):
        """Verify multiple kernels can use separate sessions."""
        # Create two separate database sessions
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        session1 = SessionLocal()
        session2 = SessionLocal()

        try:
            kernel1 = HarnessKernel(session1)
            kernel2 = HarnessKernel(session2)

            assert kernel1.db is session1
            assert kernel2.db is session2
            assert kernel1.db is not kernel2.db
        finally:
            session1.close()
            session2.close()


# =============================================================================
# Step 2: Commit after each event record for durability
# =============================================================================

class TestStep2_CommitAfterEachEvent:
    """Tests for Feature #77, Step 2: Commit after each event record for durability"""

    def test_commit_with_retry_success(self, test_db, sample_run):
        """Verify commit_with_retry commits successfully on first attempt."""
        sample_run.turns_used = 5
        commit_with_retry(test_db, "test_operation", sample_run.id)

        # Verify the change was persisted
        test_db.expire(sample_run)
        assert sample_run.turns_used == 5

    def test_commit_with_retry_retries_on_lock(self, test_db, sample_run):
        """Verify commit_with_retry retries on database lock error."""
        call_count = 0
        original_commit = test_db.commit

        def mock_commit():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OperationalError("statement", {}, Exception("database is locked"))
            return original_commit()

        with patch.object(test_db, 'commit', mock_commit):
            sample_run.turns_used = 10
            commit_with_retry(test_db, "test_operation", sample_run.id, max_retries=3)

        assert call_count == 2  # First failed, second succeeded

    def test_commit_with_retry_raises_on_integrity_error(self, test_db, sample_run):
        """Verify commit_with_retry raises ConcurrentModificationError on IntegrityError."""
        def mock_commit():
            raise IntegrityError("statement", {}, Exception("UNIQUE constraint failed"))

        with patch.object(test_db, 'commit', mock_commit):
            with pytest.raises(ConcurrentModificationError) as exc_info:
                commit_with_retry(test_db, "test_operation", sample_run.id)

        # Check that the exception contains relevant information
        assert exc_info.value.run_id == sample_run.id
        assert "UNIQUE constraint" in str(exc_info.value)

    def test_started_event_committed_immediately(self, test_db, sample_spec):
        """Verify started event is committed immediately after creation."""
        kernel = HarnessKernel(test_db)
        run = kernel._create_run_for_spec(sample_spec)
        kernel.initialize_run(run, sample_spec)

        # Query for the started event
        event = test_db.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="started"
        ).first()

        assert event is not None
        assert event.payload == {"status": "running"}

    def test_turn_complete_event_committed(self, test_db, sample_spec):
        """Verify turn_complete event is committed after each turn."""
        kernel = HarnessKernel(test_db)
        run = kernel._create_run_for_spec(sample_spec)
        kernel.initialize_run(run, sample_spec)
        kernel.record_turn_complete(run, {"test": "data"}, input_tokens=100, output_tokens=50)

        # Query for the turn_complete event
        event = test_db.query(AgentEvent).filter_by(
            run_id=run.id,
            event_type="turn_complete"
        ).first()

        assert event is not None
        assert event.payload["turns_used"] == 1


# =============================================================================
# Step 3: Handle IntegrityError from concurrent inserts
# =============================================================================

class TestStep3_HandleIntegrityError:
    """Tests for Feature #77, Step 3: Handle IntegrityError from concurrent inserts"""

    def test_concurrent_modification_error_has_run_id(self, sample_run):
        """Verify ConcurrentModificationError includes run_id."""
        error = ConcurrentModificationError(
            run_id=sample_run.id,
            operation="test_op",
            original_error=Exception("test")
        )
        assert error.run_id == sample_run.id
        assert error.operation == "test_op"

    def test_concurrent_modification_error_message(self, sample_run):
        """Verify ConcurrentModificationError has descriptive message."""
        error = ConcurrentModificationError(
            run_id=sample_run.id,
            operation="test_op",
            original_error=Exception("test error")
        )
        assert sample_run.id in str(error)
        assert "test_op" in str(error)

    def test_commit_with_retry_handles_unique_constraint(self, test_db, sample_run):
        """Verify unique constraint violations are handled as ConcurrentModificationError."""
        def mock_commit():
            raise IntegrityError(
                "INSERT",
                {},
                Exception("UNIQUE constraint failed: agent_runs.id")
            )

        with patch.object(test_db, 'commit', mock_commit):
            with pytest.raises(ConcurrentModificationError) as exc_info:
                commit_with_retry(test_db, "insert_run", sample_run.id)

        assert "Duplicate key error" in str(exc_info.value)

    def test_commit_with_retry_handles_foreign_key_constraint(self, test_db, sample_run):
        """Verify foreign key violations are handled as ConcurrentModificationError."""
        def mock_commit():
            raise IntegrityError(
                "INSERT",
                {},
                Exception("FOREIGN KEY constraint failed")
            )

        with patch.object(test_db, 'commit', mock_commit):
            with pytest.raises(ConcurrentModificationError) as exc_info:
                commit_with_retry(test_db, "insert_run", sample_run.id)

        assert sample_run.id in str(exc_info.value)

    def test_rollback_called_on_integrity_error(self, test_db, sample_run):
        """Verify rollback is called when IntegrityError occurs."""
        rollback_called = False
        original_rollback = test_db.rollback

        def mock_rollback():
            nonlocal rollback_called
            rollback_called = True
            return original_rollback()

        def mock_commit():
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

        with patch.object(test_db, 'commit', mock_commit):
            with patch.object(test_db, 'rollback', mock_rollback):
                with pytest.raises(ConcurrentModificationError):
                    commit_with_retry(test_db, "insert_run", sample_run.id)

        assert rollback_called


# =============================================================================
# Step 4: Use SELECT FOR UPDATE when modifying run status
# =============================================================================

class TestStep4_SelectForUpdate:
    """Tests for Feature #77, Step 4: Use SELECT FOR UPDATE when modifying run status"""

    def test_get_run_with_lock_returns_run(self, test_db, sample_run):
        """Verify get_run_with_lock returns the correct run."""
        locked_run = get_run_with_lock(test_db, sample_run.id)
        assert locked_run.id == sample_run.id

    def test_get_run_with_lock_raises_on_not_found(self, test_db):
        """Verify get_run_with_lock raises ValueError for non-existent run."""
        with pytest.raises(ValueError) as exc_info:
            get_run_with_lock(test_db, "non-existent-id")

        assert "not found" in str(exc_info.value)

    def test_get_run_with_lock_raises_database_lock_error(self, test_db, sample_run):
        """Verify get_run_with_lock raises DatabaseLockError on lock timeout."""
        def mock_query(*args, **kwargs):
            raise OperationalError("SELECT", {}, Exception("database is locked"))

        with patch.object(test_db, 'query', mock_query):
            with pytest.raises(DatabaseLockError) as exc_info:
                get_run_with_lock(test_db, sample_run.id)

        assert sample_run.id in str(exc_info.value)

    def test_database_lock_error_has_timeout(self, sample_run):
        """Verify DatabaseLockError includes timeout information."""
        error = DatabaseLockError(
            run_id=sample_run.id,
            timeout_seconds=30.0
        )
        assert error.run_id == sample_run.id
        assert error.timeout_seconds == 30.0
        assert "30" in str(error)


# =============================================================================
# Step 5: Rollback on exception and record error
# =============================================================================

class TestStep5_RollbackOnException:
    """Tests for Feature #77, Step 5: Rollback on exception and record error"""

    def test_rollback_and_record_error_calls_rollback(self, test_db, sample_run):
        """Verify rollback_and_record_error calls session rollback."""
        rollback_called = False
        original_rollback = test_db.rollback

        def mock_rollback():
            nonlocal rollback_called
            rollback_called = True
            return original_rollback()

        with patch.object(test_db, 'rollback', mock_rollback):
            rollback_and_record_error(test_db, sample_run.id, Exception("test error"))

        assert rollback_called

    def test_rollback_and_record_error_handles_rollback_failure(self, test_db, sample_run, caplog):
        """Verify rollback_and_record_error handles rollback failure gracefully."""
        def mock_rollback():
            raise Exception("Rollback failed")

        with patch.object(test_db, 'rollback', mock_rollback):
            # Should not raise even if rollback fails
            rollback_and_record_error(test_db, sample_run.id, Exception("test error"))

        # Should have logged the rollback failure
        assert any("Failed to rollback" in record.message for record in caplog.records)

    def test_kernel_execute_rollback_on_error(self, test_db, sample_spec):
        """Verify kernel execute rolls back on error."""
        kernel = HarnessKernel(test_db)

        def failing_executor(run, spec):
            raise Exception("Executor failed")

        # The execute method should handle the exception gracefully
        run = kernel.execute(sample_spec, turn_executor=failing_executor)

        # Run should be in failed state
        assert run.status == "failed"
        assert "Executor failed" in run.error


# =============================================================================
# Step 6: Close session in finally block
# =============================================================================

class TestStep6_SessionCleanup:
    """Tests for Feature #77, Step 6: Close session in finally block"""

    def test_kernel_clears_internal_state_on_completion(self, test_db, sample_spec):
        """Verify kernel clears internal state after execution."""
        kernel = HarnessKernel(test_db)
        run = kernel.execute(sample_spec)

        # Internal state should be cleared
        assert kernel._current_spec is None
        assert kernel._validator_context == {}

    def test_kernel_clears_internal_state_on_error(self, test_db, sample_spec):
        """Verify kernel clears internal state even on error."""
        kernel = HarnessKernel(test_db)

        def failing_executor(run, spec):
            raise Exception("Executor failed")

        run = kernel.execute(sample_spec, turn_executor=failing_executor)

        # Internal state should be cleared even after error
        assert kernel._current_spec is None
        assert kernel._validator_context == {}

    def test_kernel_clears_internal_state_on_timeout(self, test_db, sample_spec):
        """Verify kernel clears internal state on timeout."""
        # Create spec with low max_turns
        sample_spec.max_turns = 1
        test_db.commit()

        kernel = HarnessKernel(test_db)

        call_count = 0

        def always_incomplete_executor(run, spec):
            nonlocal call_count
            call_count += 1
            return False, {"turn": call_count}, [], 10, 5  # Never completes

        run = kernel.execute(sample_spec, turn_executor=always_incomplete_executor)

        # Internal state should be cleared
        assert kernel._current_spec is None
        assert kernel._validator_context == {}
        assert run.status == "timeout"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for Feature #77"""

    def test_full_execution_with_transaction_safety(self, test_db, sample_spec):
        """Test a full execution with all transaction safety features."""
        kernel = HarnessKernel(test_db)

        call_count = 0

        def test_executor(run, spec):
            nonlocal call_count
            call_count += 1
            return call_count >= 2, {"turn": call_count}, [], 100, 50

        run = kernel.execute(sample_spec, turn_executor=test_executor)

        # Verify run completed successfully
        assert run.status == "completed"
        assert run.turns_used == 2
        assert run.tokens_in == 200  # 2 turns * 100
        assert run.tokens_out == 100  # 2 turns * 50

        # Verify all events were recorded
        events = test_db.query(AgentEvent).filter_by(run_id=run.id).all()
        event_types = [e.event_type for e in events]
        assert "started" in event_types
        assert "turn_complete" in event_types
        assert "completed" in event_types

    def test_safe_add_and_commit_event(self, test_db, sample_run):
        """Test safe_add_and_commit_event function."""
        event = AgentEvent(
            run_id=sample_run.id,
            sequence=1,
            event_type="test",
            timestamp=datetime.now(timezone.utc),
            payload={"test": "data"},
        )

        result = safe_add_and_commit_event(test_db, event, sample_run.id, "test_op")

        assert result == event
        assert test_db.query(AgentEvent).filter_by(id=event.id).first() is not None

    def test_transaction_error_hierarchy(self):
        """Test that exception hierarchy is correct."""
        assert issubclass(ConcurrentModificationError, TransactionError)
        assert issubclass(DatabaseLockError, TransactionError)
        assert issubclass(TransactionError, Exception)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
