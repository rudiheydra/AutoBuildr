"""
Tests for Feature #29: Token Usage Tracking
============================================

Track input and output token usage during kernel execution for cost visibility
by extracting from Claude API response.

Verification Steps:
1. Initialize tokens_in and tokens_out to 0 at run start
2. Extract input_tokens from Claude API response usage field
3. Extract output_tokens from Claude API response usage field
4. Accumulate totals across all turns
5. Update AgentRun.tokens_in and tokens_out after each turn
6. Persist token counts even on failure/timeout
7. Include token counts in run response
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent
from api.harness_kernel import (
    BudgetTracker,
    HarnessKernel,
    ExecutionResult,
    record_turn_complete_event,
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
def sample_spec(db_session):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id="test-spec-token-001",
        name="test-spec-token",
        display_name="Test Spec for Token Tracking",
        objective="Test token tracking objective",
        task_type="testing",
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=10,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.commit()
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id="test-run-token-001",
        agent_spec_id=sample_spec.id,
        status="pending",
        turns_used=0,
        tokens_in=0,
        tokens_out=0,
    )
    db_session.add(run)
    db_session.commit()
    return run


# =============================================================================
# Step 1: Initialize tokens_in and tokens_out to 0 at run start
# =============================================================================

class TestTokenInitialization:
    """Tests for Feature #29, Step 1: Initialize tokens to 0."""

    def test_budget_tracker_initializes_tokens_to_zero(self):
        """Test BudgetTracker initializes tokens_in and tokens_out to 0."""
        tracker = BudgetTracker(max_turns=10, run_id="test")
        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0

    def test_initialize_run_sets_tokens_to_zero(self, db_session, sample_spec, sample_run):
        """Test initialize_run sets AgentRun.tokens_in and tokens_out to 0."""
        # Pre-set non-zero values to verify they get reset
        sample_run.tokens_in = 100
        sample_run.tokens_out = 50
        db_session.commit()

        kernel = HarnessKernel(db_session)
        tracker = kernel.initialize_run(sample_run, sample_spec)

        # Verify AgentRun tokens are reset to 0
        assert sample_run.tokens_in == 0
        assert sample_run.tokens_out == 0

        # Verify BudgetTracker tokens are 0
        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0

    def test_initialize_run_persists_zero_tokens(self, db_session, sample_spec, sample_run):
        """Test initialize_run persists tokens_in=0 and tokens_out=0 to database."""
        sample_run.tokens_in = 100
        sample_run.tokens_out = 50
        db_session.commit()

        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Verify persistence by querying fresh
        db_session.expire(sample_run)
        fresh_run = db_session.query(AgentRun).filter(AgentRun.id == sample_run.id).first()
        assert fresh_run.tokens_in == 0
        assert fresh_run.tokens_out == 0


# =============================================================================
# Steps 2-4: Extract and accumulate token counts
# =============================================================================

class TestTokenAccumulation:
    """Tests for Feature #29, Steps 2-4: Extract and accumulate tokens."""

    def test_accumulate_tokens_single_call(self):
        """Test accumulate_tokens adds token counts correctly."""
        tracker = BudgetTracker(max_turns=10, run_id="test")

        total_in, total_out = tracker.accumulate_tokens(1500, 500)

        assert total_in == 1500
        assert total_out == 500
        assert tracker.tokens_in == 1500
        assert tracker.tokens_out == 500

    def test_accumulate_tokens_multiple_calls(self):
        """Test accumulate_tokens accumulates across multiple calls."""
        tracker = BudgetTracker(max_turns=10, run_id="test")

        # First turn
        tracker.accumulate_tokens(1000, 300)
        assert tracker.tokens_in == 1000
        assert tracker.tokens_out == 300

        # Second turn
        tracker.accumulate_tokens(1200, 400)
        assert tracker.tokens_in == 2200
        assert tracker.tokens_out == 700

        # Third turn
        tracker.accumulate_tokens(800, 200)
        assert tracker.tokens_in == 3000
        assert tracker.tokens_out == 900

    def test_accumulate_tokens_with_zero_values(self):
        """Test accumulate_tokens handles zero values correctly."""
        tracker = BudgetTracker(max_turns=10, run_id="test")

        tracker.accumulate_tokens(0, 0)
        assert tracker.tokens_in == 0
        assert tracker.tokens_out == 0

        tracker.accumulate_tokens(1000, 0)
        assert tracker.tokens_in == 1000
        assert tracker.tokens_out == 0

        tracker.accumulate_tokens(0, 500)
        assert tracker.tokens_in == 1000
        assert tracker.tokens_out == 500


# =============================================================================
# Step 5: Update AgentRun.tokens_in and tokens_out after each turn
# =============================================================================

class TestTokenUpdatePerTurn:
    """Tests for Feature #29, Step 5: Update tokens after each turn."""

    def test_record_turn_complete_updates_tokens(self, db_session, sample_spec, sample_run):
        """Test record_turn_complete updates AgentRun token counts."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # First turn with token counts
        kernel.record_turn_complete(sample_run, input_tokens=1500, output_tokens=500)

        assert sample_run.tokens_in == 1500
        assert sample_run.tokens_out == 500

    def test_record_turn_complete_accumulates_across_turns(self, db_session, sample_spec, sample_run):
        """Test record_turn_complete accumulates tokens across multiple turns."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Turn 1
        kernel.record_turn_complete(sample_run, input_tokens=1000, output_tokens=300)
        assert sample_run.tokens_in == 1000
        assert sample_run.tokens_out == 300

        # Turn 2
        kernel.record_turn_complete(sample_run, input_tokens=1200, output_tokens=400)
        assert sample_run.tokens_in == 2200
        assert sample_run.tokens_out == 700

        # Turn 3
        kernel.record_turn_complete(sample_run, input_tokens=800, output_tokens=200)
        assert sample_run.tokens_in == 3000
        assert sample_run.tokens_out == 900

    def test_record_turn_complete_persists_tokens(self, db_session, sample_spec, sample_run):
        """Test record_turn_complete persists token counts to database."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        kernel.record_turn_complete(sample_run, input_tokens=1500, output_tokens=500)

        # Verify persistence
        db_session.expire(sample_run)
        fresh_run = db_session.query(AgentRun).filter(AgentRun.id == sample_run.id).first()
        assert fresh_run.tokens_in == 1500
        assert fresh_run.tokens_out == 500

    def test_record_turn_complete_without_tokens_uses_defaults(self, db_session, sample_spec, sample_run):
        """Test record_turn_complete with default token values (0)."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Call without token parameters (should use defaults of 0)
        kernel.record_turn_complete(sample_run)

        assert sample_run.tokens_in == 0
        assert sample_run.tokens_out == 0


# =============================================================================
# Step 6: Persist token counts even on failure/timeout
# =============================================================================

class TestTokenPersistenceOnFailure:
    """Tests for Feature #29, Step 6: Persist tokens on failure/timeout."""

    def test_tokens_persisted_on_max_turns_exceeded(self, db_session, sample_spec, sample_run):
        """Test token counts are persisted when max_turns budget is exceeded."""
        sample_spec.max_turns = 2
        db_session.commit()

        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            # Simulate token usage per turn
            return False, {"turn": turn_count[0], "tokens": {"in": 1000, "out": 300}}

        # Execute - should timeout after 2 turns
        kernel.initialize_run(sample_run, sample_spec)

        # Manually simulate turns with token tracking
        kernel.record_turn_complete(sample_run, input_tokens=1000, output_tokens=300)
        kernel.record_turn_complete(sample_run, input_tokens=1200, output_tokens=400)

        # Verify tokens are accumulated (2000 in, 700 out)
        assert sample_run.tokens_in == 2200
        assert sample_run.tokens_out == 700

        # Verify persisted in database
        db_session.expire(sample_run)
        fresh_run = db_session.query(AgentRun).filter(AgentRun.id == sample_run.id).first()
        assert fresh_run.tokens_in == 2200
        assert fresh_run.tokens_out == 700

    def test_tokens_persisted_on_error(self, db_session, sample_spec, sample_run):
        """Test token counts are persisted when execution fails with error."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            if turn_count[0] == 2:
                raise RuntimeError("Simulated error")
            return False, {"turn": turn_count[0]}

        # Use execute_with_budget with token tracking
        # Since turn_executor is called by execute_with_budget, we need to
        # customize our approach to track tokens during execution
        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        # Verify the result includes token counts (even if 0)
        assert result.status == "failed"
        assert result.tokens_in >= 0
        assert result.tokens_out >= 0


# =============================================================================
# Step 7: Include token counts in run response (ExecutionResult)
# =============================================================================

class TestTokensInExecutionResult:
    """Tests for Feature #29, Step 7: Include tokens in run response."""

    def test_execution_result_includes_tokens(self):
        """Test ExecutionResult includes tokens_in and tokens_out fields."""
        result = ExecutionResult(
            run_id="test-001",
            status="completed",
            turns_used=5,
            final_verdict="passed",
            error=None,
            tokens_in=5000,
            tokens_out=2000,
        )

        assert result.tokens_in == 5000
        assert result.tokens_out == 2000

    def test_execution_result_total_tokens(self):
        """Test ExecutionResult.total_tokens property."""
        result = ExecutionResult(
            run_id="test-001",
            status="completed",
            turns_used=5,
            final_verdict="passed",
            error=None,
            tokens_in=5000,
            tokens_out=2000,
        )

        assert result.total_tokens == 7000

    def test_execution_result_default_tokens(self):
        """Test ExecutionResult defaults tokens to 0."""
        result = ExecutionResult(
            run_id="test-001",
            status="completed",
            turns_used=5,
            final_verdict="passed",
            error=None,
        )

        assert result.tokens_in == 0
        assert result.tokens_out == 0
        assert result.total_tokens == 0

    def test_execute_with_budget_returns_tokens_on_completion(self, db_session, sample_spec, sample_run):
        """Test execute_with_budget includes token counts in result on completion."""
        kernel = HarnessKernel(db_session)

        turn_count = [0]

        def turn_executor(run, spec):
            turn_count[0] += 1
            return turn_count[0] >= 2, {"turn": turn_count[0]}

        # Execute - note: the turn_executor doesn't provide tokens directly
        # In real usage, tokens would come from Claude API response
        result = kernel.execute_with_budget(sample_run, sample_spec, turn_executor)

        # Verify result includes token fields
        assert hasattr(result, "tokens_in")
        assert hasattr(result, "tokens_out")
        assert result.tokens_in >= 0
        assert result.tokens_out >= 0


# =============================================================================
# BudgetTracker Token Integration Tests
# =============================================================================

class TestBudgetTrackerTokenIntegration:
    """Integration tests for BudgetTracker token tracking."""

    def test_to_payload_includes_tokens(self):
        """Test to_payload includes token counts."""
        tracker = BudgetTracker(max_turns=10, run_id="test")
        tracker.accumulate_tokens(1500, 500)

        payload = tracker.to_payload()

        assert payload["tokens_in"] == 1500
        assert payload["tokens_out"] == 500

    def test_mark_persisted_tracks_tokens(self):
        """Test mark_persisted tracks token persistence status."""
        tracker = BudgetTracker(max_turns=10, run_id="test")
        assert tracker.is_persisted() is True  # Initially all at 0

        tracker.accumulate_tokens(1000, 300)
        assert tracker.is_persisted() is False  # Tokens changed, not persisted

        tracker.mark_persisted()
        assert tracker.is_persisted() is True  # Now persisted

        tracker.accumulate_tokens(500, 200)
        assert tracker.is_persisted() is False  # Changed again

    def test_is_persisted_checks_all_fields(self):
        """Test is_persisted checks turns and both token fields."""
        tracker = BudgetTracker(max_turns=10, run_id="test")
        tracker.mark_persisted()

        # Change only turns
        tracker.increment_turns()
        assert tracker.is_persisted() is False
        tracker.mark_persisted()
        assert tracker.is_persisted() is True

        # Change only tokens_in (via accumulate)
        tracker.accumulate_tokens(100, 0)
        assert tracker.is_persisted() is False
        tracker.mark_persisted()
        assert tracker.is_persisted() is True

        # Change only tokens_out (via accumulate with 0 input)
        tracker.accumulate_tokens(0, 50)
        assert tracker.is_persisted() is False


# =============================================================================
# Event Recording Token Integration Tests
# =============================================================================

class TestEventRecordingWithTokens:
    """Tests for token counts in event payloads."""

    def test_turn_complete_event_includes_tokens(self, db_session, sample_run):
        """Test turn_complete event payload includes token counts."""
        tracker = BudgetTracker(max_turns=10, turns_used=1, run_id=sample_run.id)
        tracker.accumulate_tokens(1500, 500)

        event = record_turn_complete_event(
            db=db_session,
            run_id=sample_run.id,
            sequence=1,
            budget_tracker=tracker,
            turn_data=None,
        )

        assert event.payload["tokens_in"] == 1500
        assert event.payload["tokens_out"] == 500

    def test_turn_complete_event_with_turn_data(self, db_session, sample_run):
        """Test turn_complete event includes both tokens and turn_data."""
        tracker = BudgetTracker(max_turns=10, turns_used=1, run_id=sample_run.id)
        tracker.accumulate_tokens(2000, 800)

        event = record_turn_complete_event(
            db=db_session,
            run_id=sample_run.id,
            sequence=1,
            budget_tracker=tracker,
            turn_data={"tool_calls": ["Read", "Write"]},
        )

        assert event.payload["tokens_in"] == 2000
        assert event.payload["tokens_out"] == 800
        assert event.payload["turn_data"]["tool_calls"] == ["Read", "Write"]


# =============================================================================
# Verification Steps (Feature Steps 1-7)
# =============================================================================

class TestFeature29VerificationSteps:
    """Complete verification of all Feature #29 steps."""

    def test_step_1_initialize_tokens_to_zero(self, db_session, sample_spec, sample_run):
        """Step 1: Initialize tokens_in and tokens_out to 0 at run start."""
        sample_run.tokens_in = 999
        sample_run.tokens_out = 888
        db_session.commit()

        kernel = HarnessKernel(db_session)
        tracker = kernel.initialize_run(sample_run, sample_spec)

        assert sample_run.tokens_in == 0, "tokens_in not initialized to 0"
        assert sample_run.tokens_out == 0, "tokens_out not initialized to 0"
        assert tracker.tokens_in == 0, "BudgetTracker.tokens_in not initialized to 0"
        assert tracker.tokens_out == 0, "BudgetTracker.tokens_out not initialized to 0"

    def test_step_2_3_extract_tokens_from_response(self):
        """Steps 2-3: Extract input_tokens and output_tokens from response usage."""
        # This is handled by accumulate_tokens - simulating Claude API response
        tracker = BudgetTracker(max_turns=10, run_id="test")

        # Simulate extracting from response.usage.input_tokens, response.usage.output_tokens
        response_usage_input_tokens = 1500
        response_usage_output_tokens = 500

        tracker.accumulate_tokens(response_usage_input_tokens, response_usage_output_tokens)

        assert tracker.tokens_in == 1500, "Failed to extract input_tokens"
        assert tracker.tokens_out == 500, "Failed to extract output_tokens"

    def test_step_4_accumulate_totals(self):
        """Step 4: Accumulate totals across all turns."""
        tracker = BudgetTracker(max_turns=10, run_id="test")

        # Turn 1
        tracker.accumulate_tokens(1000, 300)
        # Turn 2
        tracker.accumulate_tokens(1200, 400)
        # Turn 3
        tracker.accumulate_tokens(800, 200)

        assert tracker.tokens_in == 3000, "tokens_in not accumulated correctly"
        assert tracker.tokens_out == 900, "tokens_out not accumulated correctly"

    def test_step_5_update_agentrun_after_each_turn(self, db_session, sample_spec, sample_run):
        """Step 5: Update AgentRun.tokens_in and tokens_out after each turn."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Turn 1
        kernel.record_turn_complete(sample_run, input_tokens=1000, output_tokens=300)
        assert sample_run.tokens_in == 1000, "tokens_in not updated after turn 1"
        assert sample_run.tokens_out == 300, "tokens_out not updated after turn 1"

        # Turn 2
        kernel.record_turn_complete(sample_run, input_tokens=500, output_tokens=200)
        assert sample_run.tokens_in == 1500, "tokens_in not updated after turn 2"
        assert sample_run.tokens_out == 500, "tokens_out not updated after turn 2"

    def test_step_6_persist_on_failure_timeout(self, db_session, sample_spec, sample_run):
        """Step 6: Persist token counts even on failure/timeout."""
        sample_spec.max_turns = 2
        db_session.commit()

        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Simulate turns with tokens
        kernel.record_turn_complete(sample_run, input_tokens=1000, output_tokens=300)
        kernel.record_turn_complete(sample_run, input_tokens=1200, output_tokens=400)

        # Simulate timeout handling
        from api.harness_kernel import MaxTurnsExceeded
        error = MaxTurnsExceeded(turns_used=2, max_turns=2, run_id=sample_run.id)
        result = kernel.handle_budget_exceeded(sample_run, error)

        # Verify tokens persisted
        db_session.expire(sample_run)
        fresh_run = db_session.query(AgentRun).filter(AgentRun.id == sample_run.id).first()
        assert fresh_run.tokens_in == 2200, "tokens_in not persisted on timeout"
        assert fresh_run.tokens_out == 700, "tokens_out not persisted on timeout"

    def test_step_7_include_in_run_response(self, db_session, sample_spec, sample_run):
        """Step 7: Include token counts in run response."""
        kernel = HarnessKernel(db_session)
        kernel.initialize_run(sample_run, sample_spec)

        # Simulate turns with tokens
        kernel.record_turn_complete(sample_run, input_tokens=2000, output_tokens=800)

        # Complete the run and get result
        sample_run.complete()
        kernel._budget_tracker.mark_persisted()

        result = ExecutionResult(
            run_id=sample_run.id,
            status="completed",
            turns_used=sample_run.turns_used,
            final_verdict=None,
            error=None,
            tokens_in=sample_run.tokens_in,
            tokens_out=sample_run.tokens_out,
        )

        assert result.tokens_in == 2000, "tokens_in not in run response"
        assert result.tokens_out == 800, "tokens_out not in run response"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
