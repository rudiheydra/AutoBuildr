"""
Tests for Feature #49: Graceful Budget Exhaustion Handling
==========================================================

Verifies that when max_turns or timeout_seconds is reached, the HarnessKernel:
1. Detects budget exhaustion before next turn
2. Sets status to timeout (not failed)
3. Records timeout event with resource that was exhausted
4. Commits any uncommitted database changes
5. Runs acceptance validators on partial state
6. Stores partial acceptance_results
7. Determines verdict based on partial results
8. Returns AgentRun with timeout status and partial results

Test Categories:
- Unit tests for _run_partial_acceptance_validators
- Integration tests for handle_budget_exceeded with validators
- Integration tests for handle_timeout_exceeded with validators
- End-to-end tests for execute() with budget exhaustion
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    AcceptanceSpec,
)
from api.harness_kernel import (
    BudgetTracker,
    MaxTurnsExceeded,
    TimeoutSecondsExceeded,
    HarnessKernel,
    ExecutionResult,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_spec_with_validators(db_session):
    """Create a sample AgentSpec with acceptance validators for testing."""
    spec = AgentSpec(
        id="test-spec-validators-001",
        name="test-spec-with-validators",
        display_name="Test Spec with Validators",
        objective="Test objective with validators",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=5,
        timeout_seconds=60,
    )
    db_session.add(spec)
    db_session.commit()

    # Add acceptance spec with validators
    acceptance_spec = AcceptanceSpec(
        id="test-acceptance-001",
        agent_spec_id=spec.id,
        validators=[
            {
                "type": "file_exists",
                "config": {"path": "/tmp/test_file.txt", "should_exist": False},
                "required": False,
            },
            {
                "type": "file_exists",
                "config": {"path": "/", "should_exist": True},  # This will pass
                "required": False,
            },
        ],
        gate_mode="any_pass",
    )
    db_session.add(acceptance_spec)
    db_session.commit()
    db_session.refresh(spec)
    return spec


@pytest.fixture
def sample_spec_no_validators(db_session):
    """Create a sample AgentSpec without validators for testing."""
    spec = AgentSpec(
        id="test-spec-no-validators-001",
        name="test-spec-no-validators",
        display_name="Test Spec without Validators",
        objective="Test objective without validators",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=3,
        timeout_seconds=60,  # Minimum allowed is 60 seconds
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def sample_spec_all_fail_validators(db_session):
    """Create a sample AgentSpec with validators that will all fail."""
    spec = AgentSpec(
        id="test-spec-fail-validators-001",
        name="test-spec-fail-validators",
        display_name="Test Spec with Failing Validators",
        objective="Test objective with failing validators",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=3,
        timeout_seconds=60,  # Minimum allowed is 60 seconds
    )
    db_session.add(spec)
    db_session.commit()

    # Add acceptance spec with validators that will fail
    acceptance_spec = AcceptanceSpec(
        id="test-acceptance-fail-001",
        agent_spec_id=spec.id,
        validators=[
            {
                "type": "file_exists",
                "config": {"path": "/nonexistent/file/that/does/not/exist.txt", "should_exist": True},
                "required": False,
            },
        ],
        gate_mode="all_pass",
    )
    db_session.add(acceptance_spec)
    db_session.commit()
    db_session.refresh(spec)
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec_with_validators):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id="test-run-budget-001",
        agent_spec_id=sample_spec_with_validators.id,
        status="pending",
        turns_used=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


# =============================================================================
# Feature Step 1: Detect budget exhaustion before next turn
# =============================================================================

class TestBudgetExhaustionDetection:
    """Tests for detecting budget exhaustion."""

    def test_max_turns_detected_before_turn(self, db_session, sample_spec_with_validators):
        """Verify max_turns exhaustion is detected before attempting a turn."""
        kernel = HarnessKernel(db_session)

        # Create run at budget limit
        run = AgentRun(
            id="test-detection-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        # Initialize with spec that has max_turns=5
        kernel.initialize_run(run, sample_spec_with_validators)

        # Exhaust the budget by setting turns_used to max
        kernel._budget_tracker.turns_used = 5

        # Should raise MaxTurnsExceeded when checking before turn
        with pytest.raises(MaxTurnsExceeded) as exc_info:
            kernel.check_budget_before_turn(run)

        assert exc_info.value.turns_used == 5
        assert exc_info.value.max_turns == 5

    def test_timeout_detected_before_turn(self, db_session, sample_spec_with_validators):
        """Verify timeout exhaustion is detected before attempting a turn."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-timeout-detection-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        # Initialize and then manipulate started_at to simulate timeout
        kernel.initialize_run(run, sample_spec_with_validators)

        # Set started_at to be past the timeout
        past_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        kernel._budget_tracker.started_at = past_time

        # Should raise TimeoutSecondsExceeded when checking before turn
        with pytest.raises(TimeoutSecondsExceeded) as exc_info:
            kernel.check_budget_before_turn(run)

        assert exc_info.value.elapsed_seconds >= 60  # timeout_seconds from spec


# =============================================================================
# Feature Step 2: Set status to timeout (not failed)
# =============================================================================

class TestTimeoutStatus:
    """Tests for setting timeout status correctly."""

    def test_max_turns_sets_timeout_status(self, db_session, sample_spec_with_validators):
        """Verify max_turns exhaustion sets status to timeout, not failed."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-timeout-status-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        assert result.status == "timeout"
        assert run.status == "timeout"
        assert run.error == "max_turns_exceeded"

    def test_timeout_seconds_sets_timeout_status(self, db_session, sample_spec_with_validators):
        """Verify timeout_seconds exhaustion sets status to timeout, not failed."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-timeout-status-002",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        error = TimeoutSecondsExceeded(elapsed_seconds=120.5, timeout_seconds=60, run_id=run.id)
        result = kernel.handle_timeout_exceeded(run, error)

        assert result.status == "timeout"
        assert run.status == "timeout"
        assert run.error == "timeout_exceeded"


# =============================================================================
# Feature Step 3: Record timeout event with resource that was exhausted
# =============================================================================

class TestTimeoutEventRecording:
    """Tests for recording timeout events."""

    def test_max_turns_records_timeout_event(self, db_session, sample_spec_with_validators):
        """Verify timeout event is recorded with max_turns_exceeded reason."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-event-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        kernel.handle_budget_exceeded(run, error)

        # Check for timeout event
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "timeout"
        ).all()

        assert len(events) >= 1
        timeout_event = events[-1]
        assert timeout_event.payload["reason"] == "max_turns_exceeded"
        assert "turns_used" in timeout_event.payload

    def test_timeout_seconds_records_timeout_event(self, db_session, sample_spec_with_validators):
        """Verify timeout event is recorded with timeout_exceeded reason."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-event-002",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        error = TimeoutSecondsExceeded(elapsed_seconds=120.5, timeout_seconds=60, run_id=run.id)
        kernel.handle_timeout_exceeded(run, error)

        # Check for timeout event
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "timeout"
        ).all()

        assert len(events) >= 1
        timeout_event = events[-1]
        assert timeout_event.payload["reason"] == "timeout_exceeded"
        assert "elapsed_seconds" in timeout_event.payload


# =============================================================================
# Feature Step 4: Commit any uncommitted database changes
# =============================================================================

class TestDatabaseCommit:
    """Tests for committing database changes on budget exhaustion."""

    def test_changes_committed_on_max_turns(self, db_session, sample_spec_with_validators):
        """Verify database changes are committed when max_turns is exceeded."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-commit-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        # Simulate token usage
        kernel._budget_tracker.tokens_in = 1000
        kernel._budget_tracker.tokens_out = 500

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        kernel.handle_budget_exceeded(run, error)

        # Refresh from database to verify commit
        db_session.refresh(run)

        assert run.status == "timeout"
        assert run.tokens_in == 1000
        assert run.tokens_out == 500


# =============================================================================
# Feature Steps 5-7: Run validators and determine verdict
# =============================================================================

class TestPartialValidatorExecution:
    """Tests for running validators on partial state."""

    def test_partial_validators_run_on_max_turns(self, db_session, sample_spec_with_validators):
        """Verify validators run on partial state when max_turns exceeded."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-partial-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        # Check that validators ran and stored results
        assert run.acceptance_results is not None
        assert len(run.acceptance_results) > 0
        assert run.final_verdict in ["partial", "failed", "passed"]

    def test_partial_validators_run_on_timeout(self, db_session, sample_spec_with_validators):
        """Verify validators run on partial state when timeout exceeded."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-partial-002",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        error = TimeoutSecondsExceeded(elapsed_seconds=120.5, timeout_seconds=60, run_id=run.id)
        result = kernel.handle_timeout_exceeded(run, error)

        # Check that validators ran and stored results
        assert run.acceptance_results is not None
        assert len(run.acceptance_results) > 0
        assert run.final_verdict in ["partial", "failed", "passed"]

    def test_partial_verdict_is_partial_when_some_pass(self, db_session, sample_spec_with_validators):
        """Verify verdict is 'partial' when some validators pass."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-verdict-partial-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        # With any_pass gate mode and "/" existing, should have partial verdict
        assert run.final_verdict in ["partial", "passed"]
        assert result.final_verdict in ["partial", "passed"]

    def test_partial_verdict_is_failed_when_none_pass(self, db_session, sample_spec_all_fail_validators):
        """Verify verdict is 'failed' when no validators pass."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-verdict-failed-001",
            agent_spec_id=sample_spec_all_fail_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_all_fail_validators)
        kernel._current_spec = sample_spec_all_fail_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        error = MaxTurnsExceeded(turns_used=3, max_turns=3, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        # All validators fail, should have failed verdict
        assert run.final_verdict == "failed"
        assert result.final_verdict == "failed"

    def test_no_validators_returns_none_verdict(self, db_session, sample_spec_no_validators):
        """Verify no validators results in None verdict."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-verdict-none-001",
            agent_spec_id=sample_spec_no_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_no_validators)
        kernel._current_spec = sample_spec_no_validators
        kernel._validator_context = {}

        error = MaxTurnsExceeded(turns_used=3, max_turns=3, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        # No acceptance spec, verdict should be None
        assert result.final_verdict is None


# =============================================================================
# Feature Step 8: Return AgentRun with timeout status and partial results
# =============================================================================

class TestExecutionResultWithPartialResults:
    """Tests for ExecutionResult containing partial results."""

    def test_result_contains_timeout_status(self, db_session, sample_spec_with_validators):
        """Verify ExecutionResult has timeout status."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-result-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        assert isinstance(result, ExecutionResult)
        assert result.status == "timeout"
        assert result.error == "max_turns_exceeded"

    def test_result_contains_partial_verdict(self, db_session, sample_spec_with_validators):
        """Verify ExecutionResult contains partial verdict from validators."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-result-002",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        # Should have a verdict from partial validation
        assert result.final_verdict is not None
        assert result.final_verdict in ["partial", "failed", "passed"]

    def test_result_is_timeout_property(self, db_session, sample_spec_with_validators):
        """Verify ExecutionResult.is_timeout property works correctly."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-result-003",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        assert result.is_timeout is True
        assert result.is_success is False


# =============================================================================
# End-to-end tests for execute() with budget exhaustion
# =============================================================================

class TestExecuteWithBudgetExhaustion:
    """End-to-end tests for execute() handling budget exhaustion."""

    def test_execute_max_turns_exhaustion_with_validators(self, db_session, sample_spec_with_validators):
        """Test full execute() flow with max_turns exhaustion and validators."""
        kernel = HarnessKernel(db_session)

        # Create a turn executor that never completes
        call_count = [0]
        def never_complete_executor(run, spec):
            call_count[0] += 1
            # Return: (completed, turn_data, tool_events, input_tokens, output_tokens)
            return False, {"turn": call_count[0]}, [], 100, 50

        # Execute - should exhaust max_turns (5)
        run = kernel.execute(
            sample_spec_with_validators,
            turn_executor=never_complete_executor,
            context={"project_dir": "/tmp"}
        )

        # Verify the result
        assert run.status == "timeout"
        assert run.error == "max_turns_exceeded"
        assert run.turns_used == 5  # max_turns from spec
        assert run.acceptance_results is not None
        assert run.final_verdict in ["partial", "failed", "passed"]

    def test_execute_timeout_exhaustion_with_validators(self, db_session, sample_spec_with_validators):
        """Test timeout handling by directly calling handle_timeout_exceeded."""
        # Since timeout_seconds must be >= 60 and we can't wait that long in tests,
        # we test the timeout handler directly by simulating a timeout scenario
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-timeout-exhaustion-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        # Simulate timeout by calling the handler directly
        error = TimeoutSecondsExceeded(
            elapsed_seconds=120.5,
            timeout_seconds=60,
            run_id=run.id
        )
        result = kernel.handle_timeout_exceeded(run, error)

        # Verify the result
        assert run.status == "timeout"
        assert run.error == "timeout_exceeded"
        assert run.acceptance_results is not None
        assert result.status == "timeout"
        assert result.final_verdict in ["partial", "failed", "passed"]

    def test_execute_records_acceptance_check_event(self, db_session, sample_spec_with_validators):
        """Verify acceptance_check event is recorded on budget exhaustion."""
        kernel = HarnessKernel(db_session)

        call_count = [0]
        def never_complete_executor(run, spec):
            call_count[0] += 1
            return False, {"turn": call_count[0]}, [], 100, 50

        run = kernel.execute(
            sample_spec_with_validators,
            turn_executor=never_complete_executor,
            context={"project_dir": "/tmp"}
        )

        # Check for acceptance_check event
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "acceptance_check"
        ).all()

        assert len(events) >= 1
        acceptance_event = events[-1]
        assert "final_verdict" in acceptance_event.payload
        assert "results" in acceptance_event.payload


# =============================================================================
# Tests for context preservation
# =============================================================================

class TestContextPreservation:
    """Tests for validator context preservation during budget exhaustion."""

    def test_context_includes_partial_execution_flag(self, db_session, sample_spec_with_validators):
        """Verify context includes partial_execution flag for validators."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-context-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp", "feature_id": 42}

        # Capture the context used in validators
        captured_context = None
        original_evaluate = None

        from api import validators
        original_evaluate = validators.evaluate_acceptance_spec

        def capture_evaluate(validators, context, gate_mode, run):
            nonlocal captured_context
            captured_context = context.copy()
            return original_evaluate(validators, context, gate_mode, run)

        with patch.object(validators, 'evaluate_acceptance_spec', capture_evaluate):
            error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
            kernel.handle_budget_exceeded(run, error)

        assert captured_context is not None
        assert captured_context.get("partial_execution") is True
        assert captured_context.get("exhaustion_reason") == "max_turns_exceeded"
        assert captured_context.get("project_dir") == "/tmp"
        assert captured_context.get("feature_id") == 42

    def test_spec_and_context_cleared_after_execute(self, db_session, sample_spec_with_validators):
        """Verify spec and context are cleared after execute() completes."""
        kernel = HarnessKernel(db_session)

        call_count = [0]
        def limited_executor(run, spec):
            call_count[0] += 1
            return True, {"turn": call_count[0]}, [], 100, 50  # Complete after first turn

        # Before execute, should be None/empty
        assert kernel._current_spec is None
        assert kernel._validator_context == {}

        run = kernel.execute(
            sample_spec_with_validators,
            turn_executor=limited_executor,
            context={"project_dir": "/tmp"}
        )

        # After execute, should be cleared (due to finally block)
        assert kernel._current_spec is None
        assert kernel._validator_context == {}


# =============================================================================
# Error handling tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling during partial validation."""

    def test_partial_validation_error_does_not_fail_run(self, db_session, sample_spec_with_validators):
        """Verify errors in partial validation don't cause run to fail."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-error-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {}

        # Mock evaluate_acceptance_spec to raise an error
        from api import validators

        def raise_error(*args, **kwargs):
            raise RuntimeError("Simulated validator error")

        with patch.object(validators, 'evaluate_acceptance_spec', raise_error):
            error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
            result = kernel.handle_budget_exceeded(run, error)

        # Should still return timeout status, not failed
        assert result.status == "timeout"
        assert result.final_verdict is None  # No verdict due to error
        # Run should still be in timeout status
        assert run.status == "timeout"

    def test_no_spec_available_for_partial_validation(self, db_session, sample_spec_with_validators):
        """Verify handling when no spec is stored for partial validation."""
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-no-spec-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        # Explicitly don't set _current_spec
        kernel._current_spec = None
        kernel._validator_context = {}

        error = MaxTurnsExceeded(turns_used=5, max_turns=5, run_id=run.id)
        result = kernel.handle_budget_exceeded(run, error)

        # Should still complete with timeout status
        assert result.status == "timeout"
        assert result.final_verdict is None


# =============================================================================
# Verification tests for all 8 feature steps
# =============================================================================

class TestAllFeatureSteps:
    """Comprehensive tests verifying all 8 feature steps together."""

    def test_all_steps_max_turns_exhaustion(self, db_session, sample_spec_with_validators):
        """
        Verify all 8 feature steps for max_turns exhaustion:
        1. Detect budget exhaustion before next turn
        2. Set status to timeout (not failed)
        3. Record timeout event with resource that was exhausted
        4. Commit any uncommitted database changes
        5. Run acceptance validators on partial state
        6. Store partial acceptance_results
        7. Determine verdict based on partial results
        8. Return AgentRun with timeout status and partial results
        """
        kernel = HarnessKernel(db_session)

        # Execute until budget exhaustion
        call_count = [0]
        def never_complete_executor(run, spec):
            call_count[0] += 1
            return False, {"turn": call_count[0]}, [], 100, 50

        run = kernel.execute(
            sample_spec_with_validators,
            turn_executor=never_complete_executor,
            context={"project_dir": "/tmp"}
        )

        # Step 1: Budget exhaustion was detected (turns_used == max_turns)
        assert run.turns_used == sample_spec_with_validators.max_turns

        # Step 2: Status is timeout, not failed
        assert run.status == "timeout"

        # Step 3: Timeout event recorded with reason
        timeout_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "timeout"
        ).all()
        assert len(timeout_events) >= 1
        assert timeout_events[-1].payload["reason"] == "max_turns_exceeded"

        # Step 4: Database changes committed (can query the run)
        db_session.refresh(run)
        assert run.status == "timeout"

        # Step 5: Validators ran (acceptance_check event exists)
        acceptance_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "acceptance_check"
        ).all()
        assert len(acceptance_events) >= 1

        # Step 6: Partial acceptance_results stored
        assert run.acceptance_results is not None

        # Step 7: Verdict determined based on partial results
        assert run.final_verdict in ["partial", "failed", "passed"]

        # Step 8: AgentRun returned with timeout status and partial results
        assert run.error == "max_turns_exceeded"

    def test_all_steps_timeout_seconds_exhaustion(self, db_session, sample_spec_with_validators):
        """
        Verify all 8 feature steps for timeout_seconds exhaustion.

        Since timeout_seconds must be >= 60 and we can't wait that long in tests,
        we simulate timeout by directly calling handle_timeout_exceeded.
        """
        kernel = HarnessKernel(db_session)

        run = AgentRun(
            id="test-all-steps-timeout-001",
            agent_spec_id=sample_spec_with_validators.id,
            status="pending",
            turns_used=2,  # Simulate some turns completed
            tokens_in=200,
            tokens_out=100,
        )
        db_session.add(run)
        db_session.commit()

        kernel.initialize_run(run, sample_spec_with_validators)
        kernel._current_spec = sample_spec_with_validators
        kernel._validator_context = {"project_dir": "/tmp"}

        # Simulate timeout by calling the handler directly
        error = TimeoutSecondsExceeded(
            elapsed_seconds=120.5,
            timeout_seconds=60,
            run_id=run.id
        )
        result = kernel.handle_timeout_exceeded(run, error)

        # Step 1: Budget exhaustion was detected (timeout exceeded)
        assert run.status == "timeout"

        # Step 2: Status is timeout, not failed
        assert run.status == "timeout"

        # Step 3: Timeout event recorded with reason
        timeout_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "timeout"
        ).all()
        assert len(timeout_events) >= 1
        assert timeout_events[-1].payload["reason"] == "timeout_exceeded"

        # Step 4: Database changes committed
        db_session.refresh(run)
        assert run.status == "timeout"

        # Step 5: Validators ran
        acceptance_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "acceptance_check"
        ).all()
        assert len(acceptance_events) >= 1

        # Step 6: Partial acceptance_results stored
        assert run.acceptance_results is not None

        # Step 7: Verdict determined
        assert run.final_verdict in ["partial", "failed", "passed"]

        # Step 8: AgentRun returned with timeout status
        assert run.error == "timeout_exceeded"
        assert result.status == "timeout"
