"""
Harness Kernel
==============

Agent-agnostic execution kernel for running AgentSpecs.

The HarnessKernel is the core execution primitive in AutoBuildr. It:
- Executes any AgentSpec without knowledge of task semantics
- Enforces execution budgets (max_turns, timeout_seconds)
- Records all actions as immutable AgentEvents
- Runs acceptance validators to determine success
- Returns finalized AgentRun with verdict

Key Design Principles:
- Agent-Agnostic: Only understands objective, tools, budget, acceptance criteria
- Flat Execution: No runtime sub-agent spawning in v1
- Immutable Audit Trail: Every action recorded as AgentEvent
- Least-Privilege Tools: ToolPolicy restricts available tools
- Deterministic Verification: Only deterministic validators in v1

This module implements:
- Feature #25: HarnessKernel.execute() Core Execution Loop
- Feature #27: Max Turns Budget Enforcement
- Feature #28: Timeout Seconds Enforcement
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, AcceptanceSpec


# Setup logger
_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Budget Enforcement
# =============================================================================

class BudgetExceeded(Exception):
    """
    Raised when an execution budget is exceeded.

    This exception indicates the kernel should terminate gracefully
    with a timeout status.
    """

    def __init__(
        self,
        budget_type: str,
        current_value: int,
        max_value: int,
        run_id: str,
        message: str | None = None,
    ):
        self.budget_type = budget_type
        self.current_value = current_value
        self.max_value = max_value
        self.run_id = run_id

        if message is None:
            message = (
                f"Budget exceeded for run {run_id}: "
                f"{budget_type}={current_value} >= max={max_value}"
            )

        super().__init__(message)


class MaxTurnsExceeded(BudgetExceeded):
    """
    Raised when max_turns budget is exhausted.

    Attributes:
        turns_used: Number of turns that were used
        max_turns: Maximum allowed turns from spec
        run_id: ID of the AgentRun that exceeded budget
    """

    def __init__(
        self,
        turns_used: int,
        max_turns: int,
        run_id: str,
    ):
        super().__init__(
            budget_type="max_turns",
            current_value=turns_used,
            max_value=max_turns,
            run_id=run_id,
            message=f"max_turns_exceeded: {turns_used} turns used, max {max_turns} allowed",
        )
        self.turns_used = turns_used
        self.max_turns = max_turns


class TimeoutSecondsExceeded(BudgetExceeded):
    """
    Raised when timeout_seconds wall-clock limit is exceeded.

    Attributes:
        elapsed_seconds: Number of seconds that have elapsed
        timeout_seconds: Maximum allowed seconds from spec
        run_id: ID of the AgentRun that exceeded timeout
    """

    def __init__(
        self,
        elapsed_seconds: float,
        timeout_seconds: int,
        run_id: str,
    ):
        super().__init__(
            budget_type="timeout_seconds",
            current_value=int(elapsed_seconds),
            max_value=timeout_seconds,
            run_id=run_id,
            message=f"timeout_exceeded: {elapsed_seconds:.1f}s elapsed, max {timeout_seconds}s allowed",
        )
        self.elapsed_seconds = elapsed_seconds
        self.timeout_seconds = timeout_seconds


# =============================================================================
# Budget Tracker
# =============================================================================

@dataclass
class BudgetTracker:
    """
    Tracks execution budget consumption during a run.

    This class provides methods to:
    - Track turns used
    - Track elapsed wall-clock time (timeout_seconds)
    - Track token usage (tokens_in, tokens_out) for cost visibility
    - Check if budget allows another turn
    - Record budget status in event payloads

    Thread-safety: This class is NOT thread-safe. Each kernel execution
    should have its own BudgetTracker instance.
    """

    max_turns: int
    timeout_seconds: int = 1800  # 30 minute default
    turns_used: int = 0
    run_id: str = ""
    started_at: datetime | None = None

    # Token tracking for cost visibility (Feature #29)
    tokens_in: int = 0
    tokens_out: int = 0

    # Internal tracking for persistence verification
    _last_persisted_turns: int = field(default=0, repr=False)
    _last_persisted_tokens_in: int = field(default=0, repr=False)
    _last_persisted_tokens_out: int = field(default=0, repr=False)

    def __post_init__(self):
        """Validate initial state."""
        if self.max_turns < 1:
            raise ValueError(f"max_turns must be >= 1, got {self.max_turns}")
        if self.turns_used < 0:
            raise ValueError(f"turns_used must be >= 0, got {self.turns_used}")
        if self.timeout_seconds < 1:
            raise ValueError(f"timeout_seconds must be >= 1, got {self.timeout_seconds}")

    @property
    def remaining_turns(self) -> int:
        """Number of turns remaining before budget exhaustion."""
        return max(0, self.max_turns - self.turns_used)

    @property
    def is_exhausted(self) -> bool:
        """True if the turn budget is exhausted."""
        return self.turns_used >= self.max_turns

    def can_execute_turn(self) -> bool:
        """
        Check if another turn can be executed within budget.

        Returns:
            True if turns_used < max_turns, False otherwise
        """
        return self.turns_used < self.max_turns

    def increment_turns(self) -> int:
        """
        Increment turns_used after a Claude API response.

        This should be called AFTER receiving a response from Claude,
        indicating one turn has been consumed.

        Returns:
            The new turns_used value

        Note:
            Does NOT check budget - call can_execute_turn() first.
        """
        self.turns_used += 1
        _logger.debug(
            "Turn consumed for run %s: %d/%d",
            self.run_id, self.turns_used, self.max_turns
        )
        return self.turns_used

    def accumulate_tokens(self, input_tokens: int, output_tokens: int) -> tuple[int, int]:
        """
        Accumulate token counts from a Claude API response.

        This should be called AFTER each Claude API response to track
        cumulative token usage for cost visibility (Feature #29).

        Args:
            input_tokens: Number of input tokens from Claude API response usage field
            output_tokens: Number of output tokens from Claude API response usage field

        Returns:
            Tuple of (total_tokens_in, total_tokens_out) after accumulation
        """
        self.tokens_in += input_tokens
        self.tokens_out += output_tokens
        _logger.debug(
            "Tokens accumulated for run %s: in=%d (+%d), out=%d (+%d)",
            self.run_id, self.tokens_in, input_tokens, self.tokens_out, output_tokens
        )
        return self.tokens_in, self.tokens_out

    def check_budget_or_raise(self) -> None:
        """
        Check budget and raise MaxTurnsExceeded if exhausted.

        Call this BEFORE each turn to ensure budget allows execution.

        Raises:
            MaxTurnsExceeded: If turns_used >= max_turns
        """
        if not self.can_execute_turn():
            raise MaxTurnsExceeded(
                turns_used=self.turns_used,
                max_turns=self.max_turns,
                run_id=self.run_id,
            )

    @property
    def elapsed_seconds(self) -> float:
        """
        Compute elapsed wall-clock seconds since run started.

        Returns:
            Number of seconds elapsed since started_at, or 0.0 if not started
        """
        if self.started_at is None:
            return 0.0
        now = _utc_now()
        delta = now - self.started_at
        return delta.total_seconds()

    @property
    def remaining_seconds(self) -> float:
        """
        Number of seconds remaining before timeout.

        Returns:
            Seconds remaining until timeout, or 0.0 if timed out
        """
        return max(0.0, self.timeout_seconds - self.elapsed_seconds)

    @property
    def is_timed_out(self) -> bool:
        """
        True if the wall-clock timeout has been exceeded.

        Returns:
            True if elapsed_seconds >= timeout_seconds
        """
        return self.elapsed_seconds >= self.timeout_seconds

    def can_continue_within_timeout(self) -> bool:
        """
        Check if execution can continue within timeout limit.

        Returns:
            True if elapsed_seconds < timeout_seconds, False otherwise
        """
        return self.elapsed_seconds < self.timeout_seconds

    def check_timeout_or_raise(self) -> None:
        """
        Check timeout and raise TimeoutSecondsExceeded if exceeded.

        Call this BEFORE each turn to ensure timeout allows execution.
        Uses started_at timestamp comparison.

        Raises:
            TimeoutSecondsExceeded: If elapsed_seconds >= timeout_seconds
        """
        if not self.can_continue_within_timeout():
            raise TimeoutSecondsExceeded(
                elapsed_seconds=self.elapsed_seconds,
                timeout_seconds=self.timeout_seconds,
                run_id=self.run_id,
            )

    def check_all_budgets_or_raise(self) -> None:
        """
        Check both max_turns and timeout_seconds budgets.

        Call this BEFORE each turn to ensure all budgets allow execution.

        Raises:
            MaxTurnsExceeded: If turns_used >= max_turns
            TimeoutSecondsExceeded: If elapsed_seconds >= timeout_seconds
        """
        # Check timeout first (more likely to be hit during long-running operations)
        self.check_timeout_or_raise()
        # Then check turns
        self.check_budget_or_raise()

    def mark_persisted(self) -> None:
        """
        Mark the current turns_used and token counts as persisted to database.

        Call this after successfully committing the AgentRun to database.
        Used to verify persistence in tests.
        """
        self._last_persisted_turns = self.turns_used
        self._last_persisted_tokens_in = self.tokens_in
        self._last_persisted_tokens_out = self.tokens_out

    def is_persisted(self) -> bool:
        """
        Check if current turns_used and token counts have been persisted.

        Returns:
            True if all current values match last persisted values
        """
        return (
            self._last_persisted_turns == self.turns_used and
            self._last_persisted_tokens_in == self.tokens_in and
            self._last_persisted_tokens_out == self.tokens_out
        )

    def to_payload(self) -> dict[str, Any]:
        """
        Convert budget state to event payload dict.

        Returns:
            Dict suitable for AgentEvent payload, including token counts (Feature #29)
        """
        return {
            "turns_used": self.turns_used,
            "max_turns": self.max_turns,
            "remaining_turns": self.remaining_turns,
            "is_exhausted": self.is_exhausted,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "timeout_seconds": self.timeout_seconds,
            "remaining_seconds": round(self.remaining_seconds, 2),
            "is_timed_out": self.is_timed_out,
            # Token tracking (Feature #29)
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


# =============================================================================
# Event Recording
# =============================================================================

def create_timeout_event(
    run_id: str,
    sequence: int,
    budget_tracker: BudgetTracker,
    reason: str = "max_turns_exceeded",
) -> dict[str, Any]:
    """
    Create a timeout event payload for budget exhaustion.

    Args:
        run_id: ID of the AgentRun
        sequence: Event sequence number
        budget_tracker: Budget state at timeout
        reason: Reason for timeout (default: max_turns_exceeded)

    Returns:
        Dict with event data for AgentEvent creation

    Example:
        >>> tracker = BudgetTracker(max_turns=10, turns_used=10, run_id="abc")
        >>> event = create_timeout_event("abc", 5, tracker)
        >>> event["event_type"]
        'timeout'
        >>> event["payload"]["reason"]
        'max_turns_exceeded'
    """
    return {
        "run_id": run_id,
        "sequence": sequence,
        "event_type": "timeout",
        "timestamp": _utc_now(),
        "payload": {
            "reason": reason,
            **budget_tracker.to_payload(),
        },
        "tool_name": None,
    }


def record_turn_complete_event(
    db: Session,
    run_id: str,
    sequence: int,
    budget_tracker: BudgetTracker,
    turn_data: dict[str, Any] | None = None,
) -> "AgentEvent":
    """
    Record a turn_complete event with budget information.

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        budget_tracker: Current budget state
        turn_data: Additional turn data (tool calls, etc.)

    Returns:
        The created AgentEvent
    """
    from api.agentspec_models import AgentEvent

    payload = {
        "turn_number": budget_tracker.turns_used,
        **budget_tracker.to_payload(),
    }

    if turn_data:
        payload["turn_data"] = turn_data

    event = AgentEvent(
        run_id=run_id,
        sequence=sequence,
        event_type="turn_complete",
        timestamp=_utc_now(),
        payload=payload,
    )

    db.add(event)
    return event


def record_timeout_event(
    db: Session,
    run_id: str,
    sequence: int,
    budget_tracker: BudgetTracker,
    reason: str = "max_turns_exceeded",
) -> "AgentEvent":
    """
    Record a timeout event when budget is exceeded.

    Args:
        db: Database session
        run_id: ID of the AgentRun
        sequence: Event sequence number
        budget_tracker: Budget state at timeout
        reason: Reason for timeout

    Returns:
        The created AgentEvent
    """
    from api.agentspec_models import AgentEvent

    event_data = create_timeout_event(run_id, sequence, budget_tracker, reason)

    event = AgentEvent(
        run_id=event_data["run_id"],
        sequence=event_data["sequence"],
        event_type=event_data["event_type"],
        timestamp=event_data["timestamp"],
        payload=event_data["payload"],
        tool_name=event_data["tool_name"],
    )

    db.add(event)
    return event


# =============================================================================
# HarnessKernel
# =============================================================================

@dataclass
class ExecutionResult:
    """
    Result of a HarnessKernel execution.

    Contains the final state after execution completes,
    whether successfully, via failure, or via timeout.
    """

    run_id: str
    status: str  # completed, failed, timeout
    turns_used: int
    final_verdict: Optional[str]  # passed, failed, partial
    error: Optional[str]
    # Token tracking for cost visibility (Feature #29, Step 7)
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def is_success(self) -> bool:
        """True if execution completed with passed verdict."""
        return self.status == "completed" and self.final_verdict == "passed"

    @property
    def is_timeout(self) -> bool:
        """True if execution timed out."""
        return self.status == "timeout"

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed (input + output)."""
        return self.tokens_in + self.tokens_out


class HarnessKernel:
    """
    Agent-agnostic execution kernel for running AgentSpecs.

    The kernel orchestrates execution of an AgentSpec:
    1. Initialize AgentRun with status=running, turns_used=0
    2. Build system prompt from spec.objective + spec.context
    3. Execute turns via Claude SDK, enforcing max_turns and timeout_seconds budgets
    4. Record events for each tool call and turn
    5. Run acceptance validators when agent signals completion
    6. Finalize run with verdict and status

    Budget Enforcement (Feature #27 - max_turns):
    - Initialize turns_used to 0 at run start
    - Increment turns_used after each Claude API response
    - Check turns_used < spec.max_turns before each turn
    - When budget exhausted: status=timeout, error="max_turns_exceeded"
    - Record timeout event with turns_used in payload
    - Persist turns_used after each turn

    Timeout Enforcement (Feature #28 - timeout_seconds):
    - Record started_at timestamp at run begin
    - Compute elapsed_seconds = now - started_at before each turn
    - Check elapsed_seconds < spec.timeout_seconds
    - When timeout reached: status=timeout, error="timeout_exceeded"
    - Record timeout event with elapsed_seconds in payload
    - Ensure partial work is committed before termination
    - Handle long-running tool calls that exceed timeout

    Usage:
        kernel = HarnessKernel(db_session)
        result = kernel.execute(spec, run)
    """

    def __init__(self, db: Session):
        """
        Initialize the HarnessKernel.

        Args:
            db: SQLAlchemy database session for persistence
        """
        self.db = db
        self._budget_tracker: Optional[BudgetTracker] = None
        self._event_sequence: int = 0

    def initialize_run(self, run: "AgentRun", spec: "AgentSpec") -> BudgetTracker:
        """
        Initialize an AgentRun for execution.

        Sets up:
        - turns_used = 0
        - status = running
        - started_at = now (Feature #28, Step 1)
        - Budget tracker with spec.max_turns and spec.timeout_seconds

        Args:
            run: The AgentRun to initialize
            spec: The AgentSpec being executed

        Returns:
            BudgetTracker configured for this run

        Raises:
            InvalidStateTransition: If run cannot transition to running
        """
        # Initialize turns_used to 0 (Step 1 of Feature #27)
        run.turns_used = 0

        # Initialize tokens_in and tokens_out to 0 at run start (Feature #29, Step 1)
        run.tokens_in = 0
        run.tokens_out = 0

        # Transition to running (handles started_at timestamp)
        # Feature #28, Step 1: Record started_at timestamp at run begin
        run.start()

        # Create budget tracker with both max_turns and timeout_seconds
        # Feature #28: Include started_at for elapsed_seconds calculation
        # Feature #29: Initialize token tracking to 0
        self._budget_tracker = BudgetTracker(
            max_turns=spec.max_turns,
            timeout_seconds=spec.timeout_seconds,
            turns_used=0,
            run_id=run.id,
            started_at=run.started_at,  # Use the timestamp from run.start()
            tokens_in=0,  # Feature #29: Initialize token tracking
            tokens_out=0,
        )

        # Reset event sequence
        self._event_sequence = 0

        # Persist initial state
        self.db.commit()
        self._budget_tracker.mark_persisted()

        _logger.info(
            "Initialized run %s: max_turns=%d, timeout_seconds=%d, status=%s",
            run.id, spec.max_turns, spec.timeout_seconds, run.status
        )

        # Record started event
        self._record_started_event(run.id)

        return self._budget_tracker

    def _record_started_event(self, run_id: str) -> None:
        """Record the started event for a run."""
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1
        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="started",
            timestamp=_utc_now(),
            payload={"status": "running"},
        )
        self.db.add(event)
        self.db.commit()

    def check_budget_before_turn(self, run: "AgentRun") -> None:
        """
        Check if budget allows another turn.

        Call this BEFORE making a Claude API call.

        Args:
            run: The AgentRun to check

        Raises:
            MaxTurnsExceeded: If turns_used >= max_turns
            TimeoutSecondsExceeded: If elapsed_seconds >= timeout_seconds
        """
        if self._budget_tracker is None:
            raise RuntimeError("Budget tracker not initialized. Call initialize_run first.")

        # Feature #28, Step 2 & 3: Compute elapsed_seconds and check < spec.timeout_seconds
        # Feature #27, Step 3: Check turns_used < spec.max_turns before each turn
        # check_all_budgets_or_raise checks timeout first, then turns
        self._budget_tracker.check_all_budgets_or_raise()

    def record_turn_complete(
        self,
        run: "AgentRun",
        turn_data: dict[str, Any] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> int:
        """
        Record a completed turn and increment counter.

        Call this AFTER receiving a Claude API response.

        Args:
            run: The AgentRun to update
            turn_data: Optional data about the turn (tool calls, etc.)
            input_tokens: Number of input tokens from Claude API response usage field (Feature #29)
            output_tokens: Number of output tokens from Claude API response usage field (Feature #29)

        Returns:
            The new turns_used value

        Persistence:
            This method commits to ensure turns_used and token counts are persisted
            after each turn (Step 8 of Feature #27, Feature #29).
        """
        if self._budget_tracker is None:
            raise RuntimeError("Budget tracker not initialized. Call initialize_run first.")

        # Step 2 of Feature #27: Increment turns_used after each Claude API response
        new_turns = self._budget_tracker.increment_turns()

        # Feature #29, Steps 2-4: Extract and accumulate token counts from Claude API response
        self._budget_tracker.accumulate_tokens(input_tokens, output_tokens)

        # Update the AgentRun model
        run.turns_used = new_turns

        # Feature #29, Step 5: Update AgentRun.tokens_in and tokens_out after each turn
        run.tokens_in = self._budget_tracker.tokens_in
        run.tokens_out = self._budget_tracker.tokens_out

        # Record turn_complete event
        self._event_sequence += 1
        record_turn_complete_event(
            db=self.db,
            run_id=run.id,
            sequence=self._event_sequence,
            budget_tracker=self._budget_tracker,
            turn_data=turn_data,
        )

        # Step 8 of Feature #27: Persist turns_used after each turn
        # Feature #29, Step 5: Persist token counts after each turn
        self.db.commit()
        self._budget_tracker.mark_persisted()

        _logger.debug(
            "Turn complete for run %s: turns=%d/%d, tokens_in=%d, tokens_out=%d",
            run.id, run.turns_used, self._budget_tracker.max_turns,
            run.tokens_in, run.tokens_out
        )

        return new_turns

    def handle_budget_exceeded(
        self,
        run: "AgentRun",
        error: MaxTurnsExceeded,
    ) -> ExecutionResult:
        """
        Handle max_turns budget exhaustion gracefully.

        Steps 4-7 of Feature #27:
        - Set status to timeout
        - Set error message to max_turns_exceeded
        - Record timeout event with turns_used in payload
        - Ensure partial work is committed

        Args:
            run: The AgentRun that exceeded budget
            error: The MaxTurnsExceeded exception

        Returns:
            ExecutionResult with timeout status
        """
        if self._budget_tracker is None:
            raise RuntimeError("Budget tracker not initialized")

        _logger.warning(
            "Budget exceeded for run %s: %s",
            run.id, str(error)
        )

        # Feature #29, Step 6: Persist token counts even on failure/timeout
        run.tokens_in = self._budget_tracker.tokens_in
        run.tokens_out = self._budget_tracker.tokens_out

        # Step 6: Record timeout event with turns_used in payload
        self._event_sequence += 1
        record_timeout_event(
            db=self.db,
            run_id=run.id,
            sequence=self._event_sequence,
            budget_tracker=self._budget_tracker,
            reason="max_turns_exceeded",
        )

        # Step 4 & 5: Set status to timeout with error message
        run.timeout(error_message="max_turns_exceeded")

        # Step 7: Ensure partial work is committed before termination
        # Feature #29: Token counts are now included in the commit
        self.db.commit()

        return ExecutionResult(
            run_id=run.id,
            status="timeout",
            turns_used=run.turns_used,
            final_verdict=None,
            error="max_turns_exceeded",
            # Feature #29, Step 7: Include token counts in run response
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
        )

    def handle_timeout_exceeded(
        self,
        run: "AgentRun",
        error: TimeoutSecondsExceeded,
    ) -> ExecutionResult:
        """
        Handle timeout_seconds wall-clock limit exceeded gracefully.

        Steps 4-7 of Feature #28:
        - Set status to timeout
        - Set error message to timeout_exceeded
        - Record timeout event with elapsed_seconds in payload
        - Ensure partial work is committed before termination
        - Handle long-running tool calls that exceed timeout

        Args:
            run: The AgentRun that exceeded timeout
            error: The TimeoutSecondsExceeded exception

        Returns:
            ExecutionResult with timeout status
        """
        if self._budget_tracker is None:
            raise RuntimeError("Budget tracker not initialized")

        _logger.warning(
            "Timeout exceeded for run %s: %s",
            run.id, str(error)
        )

        # Feature #29, Step 6: Persist token counts even on failure/timeout
        run.tokens_in = self._budget_tracker.tokens_in
        run.tokens_out = self._budget_tracker.tokens_out

        # Feature #28, Step 6: Record timeout event with elapsed_seconds in payload
        self._event_sequence += 1
        record_timeout_event(
            db=self.db,
            run_id=run.id,
            sequence=self._event_sequence,
            budget_tracker=self._budget_tracker,
            reason="timeout_exceeded",  # Feature #28, Step 5: Set error message
        )

        # Feature #28, Step 4: Set status to timeout with error message
        run.timeout(error_message="timeout_exceeded")

        # Feature #28, Step 7: Ensure partial work is committed before termination
        # Feature #29: Token counts are now included in the commit
        self.db.commit()

        return ExecutionResult(
            run_id=run.id,
            status="timeout",
            turns_used=run.turns_used,
            final_verdict=None,
            error="timeout_exceeded",
            # Feature #29, Step 7: Include token counts in run response
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
        )

    def execute_with_budget(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
        turn_executor: callable,
    ) -> ExecutionResult:
        """
        Execute turns with budget enforcement.

        This is the main execution loop that enforces max_turns and timeout_seconds budgets.

        Args:
            run: The AgentRun to execute
            spec: The AgentSpec with budget limits
            turn_executor: Callable that executes one turn
                Should return (completed: bool, turn_data: dict)
                completed=True signals the agent wants to stop

        Returns:
            ExecutionResult with final status

        Example:
            def my_turn_executor(run, spec):
                # Call Claude API
                response = claude.complete(...)
                # Check if agent wants to complete
                completed = response.stop_reason == "end_turn"
                return completed, {"response": response}

            result = kernel.execute_with_budget(run, spec, my_turn_executor)

        Budget Enforcement:
            - Feature #27: max_turns budget enforced before each turn
            - Feature #28: timeout_seconds wall-clock limit enforced before each turn
            - Long-running tool calls may exceed timeout; checked after turn completes
        """
        # Initialize run and budget tracker
        self.initialize_run(run, spec)

        try:
            while True:
                # Check budget before turn (both max_turns and timeout_seconds)
                try:
                    self.check_budget_before_turn(run)
                except MaxTurnsExceeded as e:
                    return self.handle_budget_exceeded(run, e)
                except TimeoutSecondsExceeded as e:
                    # Feature #28: Handle timeout before turn
                    return self.handle_timeout_exceeded(run, e)

                # Execute one turn
                # Feature #28, Step 8: Long-running tool calls may exceed timeout
                # Timeout is checked before each turn; if a tool call exceeds timeout,
                # it will be caught on the next iteration of the loop
                completed, turn_data = turn_executor(run, spec)

                # Record turn completion and increment counter
                self.record_turn_complete(run, turn_data)

                # Feature #28: Check timeout after turn in case tool call exceeded limit
                # This handles long-running tool calls that exceed timeout during execution
                try:
                    self._budget_tracker.check_timeout_or_raise()
                except TimeoutSecondsExceeded as e:
                    return self.handle_timeout_exceeded(run, e)

                # Check if agent signaled completion
                if completed:
                    break

            # Normal completion
            run.complete()
            # Feature #29, Step 6: Ensure token counts are persisted on completion
            run.tokens_in = self._budget_tracker.tokens_in
            run.tokens_out = self._budget_tracker.tokens_out
            self.db.commit()

            return ExecutionResult(
                run_id=run.id,
                status="completed",
                turns_used=run.turns_used,
                final_verdict=run.final_verdict,
                error=None,
                # Feature #29, Step 7: Include token counts in run response
                tokens_in=run.tokens_in,
                tokens_out=run.tokens_out,
            )

        except MaxTurnsExceeded as e:
            return self.handle_budget_exceeded(run, e)
        except TimeoutSecondsExceeded as e:
            # Feature #28: Handle timeout exception from anywhere in execution
            return self.handle_timeout_exceeded(run, e)
        except Exception as e:
            # Handle unexpected errors
            _logger.exception("Execution error for run %s: %s", run.id, e)
            # Feature #29, Step 6: Persist token counts even on failure
            if self._budget_tracker is not None:
                run.tokens_in = self._budget_tracker.tokens_in
                run.tokens_out = self._budget_tracker.tokens_out
            run.fail(error_message=str(e))
            self.db.commit()

            return ExecutionResult(
                run_id=run.id,
                status="failed",
                turns_used=run.turns_used,
                final_verdict=None,
                error=str(e),
                # Feature #29, Step 7: Include token counts in run response
                tokens_in=run.tokens_in,
                tokens_out=run.tokens_out,
            )

    # =========================================================================
    # Feature #25: Core execute(spec) Method
    # =========================================================================

    def _record_tool_call_event(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
    ) -> "AgentEvent":
        """
        Record a tool_call event for each tool invocation.

        Feature #25, Step 8: Record tool_call event for each tool invocation

        Args:
            run_id: ID of the AgentRun
            tool_name: Name of the tool being called
            arguments: Tool arguments dict

        Returns:
            The created AgentEvent
        """
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1

        # Cap payload size at 4KB as per EVENT_PAYLOAD_MAX_SIZE
        payload = {
            "tool": tool_name,
            "arguments": arguments or {},
        }

        # Serialize to check size
        payload_str = json.dumps(payload, default=str)
        payload_truncated = None
        if len(payload_str) > 4096:
            payload_truncated = len(payload_str)
            # Truncate the arguments
            payload["arguments"] = {"_truncated": True, "_original_size": len(payload_str)}

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="tool_call",
            timestamp=_utc_now(),
            payload=payload,
            payload_truncated=payload_truncated,
            tool_name=tool_name,
        )

        self.db.add(event)
        _logger.debug("Recorded tool_call event: run=%s, tool=%s, seq=%d", run_id, tool_name, self._event_sequence)
        return event

    def _record_tool_result_event(
        self,
        run_id: str,
        tool_name: str,
        result: Any,
        is_error: bool = False,
    ) -> "AgentEvent":
        """
        Record a tool_result event for each tool response.

        Feature #25, Step 9: Record tool_result event for each tool response

        Args:
            run_id: ID of the AgentRun
            tool_name: Name of the tool
            result: Tool execution result
            is_error: Whether the result is an error

        Returns:
            The created AgentEvent
        """
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1

        payload = {
            "tool": tool_name,
            "is_error": is_error,
        }

        # Handle result - may be string, dict, or other
        if isinstance(result, str):
            payload["result"] = result
        elif isinstance(result, dict):
            payload["result"] = result
        else:
            payload["result"] = str(result)

        # Cap payload size at 4KB
        payload_str = json.dumps(payload, default=str)
        payload_truncated = None
        if len(payload_str) > 4096:
            payload_truncated = len(payload_str)
            # Store reference to artifact instead of truncating inline
            payload["result"] = {"_truncated": True, "_original_size": len(payload_str)}

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="tool_result",
            timestamp=_utc_now(),
            payload=payload,
            payload_truncated=payload_truncated,
            tool_name=tool_name,
        )

        self.db.add(event)
        _logger.debug("Recorded tool_result event: run=%s, tool=%s, seq=%d", run_id, tool_name, self._event_sequence)
        return event

    def _record_acceptance_check_event(
        self,
        run_id: str,
        results: list[dict[str, Any]],
        final_verdict: str,
        gate_mode: str,
    ) -> "AgentEvent":
        """
        Record an acceptance_check event with validation results.

        Feature #25, Steps 13-14: Record acceptance_check event with results

        Args:
            run_id: ID of the AgentRun
            results: List of validator results
            final_verdict: The determined verdict (passed/failed/partial)
            gate_mode: The gate mode used (all_pass/any_pass/weighted)

        Returns:
            The created AgentEvent
        """
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1

        payload = {
            "final_verdict": final_verdict,
            "gate_mode": gate_mode,
            "validator_count": len(results),
            "results": results,
        }

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="acceptance_check",
            timestamp=_utc_now(),
            payload=payload,
        )

        self.db.add(event)
        _logger.info(
            "Recorded acceptance_check event: run=%s, verdict=%s, validators=%d",
            run_id, final_verdict, len(results)
        )
        return event

    def _record_completed_event(self, run_id: str, verdict: str | None) -> "AgentEvent":
        """
        Record a completed event on successful finish.

        Feature #25, Step 17: Record completed event

        Args:
            run_id: ID of the AgentRun
            verdict: Final verdict (passed/failed/partial or None)

        Returns:
            The created AgentEvent
        """
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="completed",
            timestamp=_utc_now(),
            payload={
                "final_verdict": verdict,
                "message": "Execution completed successfully",
            },
        )

        self.db.add(event)
        _logger.info("Recorded completed event: run=%s, verdict=%s", run_id, verdict)
        return event

    def _record_failed_event(self, run_id: str, error_message: str) -> "AgentEvent":
        """
        Record a failed event on error.

        Args:
            run_id: ID of the AgentRun
            error_message: Error description

        Returns:
            The created AgentEvent
        """
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="failed",
            timestamp=_utc_now(),
            payload={
                "error": error_message,
            },
        )

        self.db.add(event)
        _logger.error("Recorded failed event: run=%s, error=%s", run_id, error_message)
        return event

    def _run_acceptance_validators(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
        context: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Run AcceptanceSpec validators after execution.

        Feature #25, Steps 14-16:
        - Step 14: Run AcceptanceSpec validators after execution
        - Step 15: Record acceptance_check event with results
        - Step 16: Determine final_verdict from validator results

        Args:
            run: The completed AgentRun
            spec: The AgentSpec with acceptance_spec
            context: Runtime context for validators

        Returns:
            Tuple of (final_verdict, validator_results)
        """
        from api.validators import evaluate_acceptance_spec

        # Get acceptance spec if linked
        acceptance_spec = spec.acceptance_spec
        if acceptance_spec is None:
            # No acceptance spec - default to passed
            _logger.info("No AcceptanceSpec linked to spec %s, defaulting to passed", spec.id)
            return "passed", []

        # Get validator definitions and gate mode
        validators = acceptance_spec.validators or []
        gate_mode = acceptance_spec.gate_mode or "all_pass"

        if not validators:
            # No validators defined - default to passed
            _logger.info("AcceptanceSpec has no validators, defaulting to passed")
            return "passed", []

        # Run validators
        _logger.info(
            "Running %d validators for run %s with gate_mode=%s",
            len(validators), run.id, gate_mode
        )

        passed, results = evaluate_acceptance_spec(
            validators=validators,
            context=context,
            gate_mode=gate_mode,
            run=run,
        )

        # Convert results to dicts for storage
        results_dicts = [r.to_dict() for r in results]

        # Determine verdict
        if passed:
            final_verdict = "passed"
        else:
            # Check if any validators passed (partial)
            any_passed = any(r.passed for r in results)
            final_verdict = "partial" if any_passed else "failed"

        _logger.info(
            "Acceptance validation complete: verdict=%s, passed=%d/%d",
            final_verdict, sum(1 for r in results if r.passed), len(results)
        )

        return final_verdict, results_dicts

    def _create_run_for_spec(self, spec: "AgentSpec") -> "AgentRun":
        """
        Create a new AgentRun record for a spec.

        Feature #25, Step 2: Create AgentRun record with status=running at execution start

        Args:
            spec: The AgentSpec to execute

        Returns:
            The created AgentRun with status=pending
        """
        from api.agentspec_models import AgentRun

        run = AgentRun(
            id=str(uuid.uuid4()),
            agent_spec_id=spec.id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
            created_at=_utc_now(),
        )

        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        _logger.info("Created AgentRun %s for spec %s", run.id, spec.id)
        return run

    def execute(
        self,
        spec: "AgentSpec",
        turn_executor: Callable[["AgentRun", "AgentSpec"], tuple[bool, dict[str, Any], list[dict], int, int]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> "AgentRun":
        """
        Execute an AgentSpec and return the finalized AgentRun.

        This is the core execution method that implements the full lifecycle:
        1. Create AgentRun record with status=running
        2. Record started AgentEvent with sequence=1
        3. Build system prompt from spec.objective and spec.context
        4. Configure tools based on spec.tool_policy
        5. Enter execution loop calling turn_executor
        6. Record tool_call and tool_result events for each invocation
        7. Record turn_complete event after each API turn
        8. Check max_turns and timeout_seconds budgets
        9. Handle graceful termination on budget exhaustion
        10. Run AcceptanceSpec validators after execution
        11. Record acceptance_check event with results
        12. Determine final_verdict from validator results
        13. Update AgentRun with completed status and verdict
        14. Return finalized AgentRun

        Feature #25: HarnessKernel.execute() Core Execution Loop

        Args:
            spec: The AgentSpec to execute
            turn_executor: Optional callback that executes one turn.
                Should return (completed: bool, turn_data: dict, tool_events: list, input_tokens: int, output_tokens: int)
                - completed: True when agent signals completion
                - turn_data: Data about the turn
                - tool_events: List of {tool_name, arguments, result, is_error} for recording
                - input_tokens: Input tokens from this turn
                - output_tokens: Output tokens from this turn

                If None, execution completes immediately after initialization (useful for testing).

            context: Optional runtime context for validators. Should include:
                - project_dir: Base project directory
                - feature_id: Linked feature ID (if any)
                - Additional context from spec.context

        Returns:
            The finalized AgentRun with:
            - status: completed, failed, or timeout
            - final_verdict: passed, failed, partial, or None
            - turns_used: Number of turns executed
            - tokens_in, tokens_out: Token usage
            - acceptance_results: Validator results
            - error: Error message if failed

        Example:
            # Simple execution without Claude (for testing)
            kernel = HarnessKernel(db_session)
            run = kernel.execute(spec)

            # With custom turn executor
            def my_executor(run, spec):
                # Your Claude API logic here
                completed = True
                turn_data = {"response": "..."}
                tool_events = [{"tool_name": "Read", "arguments": {"path": "/file"}, "result": "content"}]
                return completed, turn_data, tool_events, 100, 50

            run = kernel.execute(spec, turn_executor=my_executor)
        """
        # Step 1: Create AgentRun record (status=pending initially)
        run = self._create_run_for_spec(spec)

        # Build context for validators
        validator_context = context or {}
        if spec.context:
            validator_context.update(spec.context)
        if spec.source_feature_id:
            validator_context["feature_id"] = spec.source_feature_id

        try:
            # Step 2: Initialize run (sets status=running, starts budget tracker)
            self.initialize_run(run, spec)

            # If no turn executor provided, complete immediately
            # This is useful for testing the infrastructure
            if turn_executor is None:
                _logger.info("No turn executor provided, completing immediately")
                run.complete()
                self.db.commit()

                # Run acceptance validators
                final_verdict, acceptance_results = self._run_acceptance_validators(
                    run, spec, validator_context
                )

                # Record acceptance check event
                acceptance_spec = spec.acceptance_spec
                gate_mode = acceptance_spec.gate_mode if acceptance_spec else "all_pass"
                self._record_acceptance_check_event(
                    run.id, acceptance_results, final_verdict, gate_mode
                )

                # Update run with verdict
                run.final_verdict = final_verdict
                run.acceptance_results = acceptance_results

                # Record completed event
                self._record_completed_event(run.id, final_verdict)

                self.db.commit()
                return run

            # Step 5-11: Execution loop
            while True:
                # Check budget before turn
                try:
                    self.check_budget_before_turn(run)
                except MaxTurnsExceeded as e:
                    self.handle_budget_exceeded(run, e)
                    return run
                except TimeoutSecondsExceeded as e:
                    self.handle_timeout_exceeded(run, e)
                    return run

                # Execute one turn
                try:
                    completed, turn_data, tool_events, input_tokens, output_tokens = turn_executor(run, spec)
                except Exception as e:
                    _logger.error("Turn executor error: %s", e)
                    self._record_failed_event(run.id, str(e))
                    run.fail(error_message=str(e))
                    self.db.commit()
                    return run

                # Record tool events (tool_call and tool_result pairs)
                for event in tool_events:
                    tool_name = event.get("tool_name", "unknown")
                    arguments = event.get("arguments")
                    result = event.get("result")
                    is_error = event.get("is_error", False)

                    self._record_tool_call_event(run.id, tool_name, arguments)
                    self._record_tool_result_event(run.id, tool_name, result, is_error)

                # Record turn completion with token counts
                self.record_turn_complete(run, turn_data, input_tokens, output_tokens)

                # Check timeout after turn
                try:
                    self._budget_tracker.check_timeout_or_raise()
                except TimeoutSecondsExceeded as e:
                    self.handle_timeout_exceeded(run, e)
                    return run

                # Check if agent signaled completion
                if completed:
                    break

            # Step 12-14: Run acceptance validators
            final_verdict, acceptance_results = self._run_acceptance_validators(
                run, spec, validator_context
            )

            # Step 15: Record acceptance check event
            acceptance_spec = spec.acceptance_spec
            gate_mode = acceptance_spec.gate_mode if acceptance_spec else "all_pass"
            self._record_acceptance_check_event(
                run.id, acceptance_results, final_verdict, gate_mode
            )

            # Step 16: Update run with verdict and results
            run.final_verdict = final_verdict
            run.acceptance_results = acceptance_results

            # Step 17: Complete the run
            run.complete()
            self._record_completed_event(run.id, final_verdict)
            self.db.commit()

            _logger.info(
                "Execution completed: run=%s, verdict=%s, turns=%d",
                run.id, final_verdict, run.turns_used
            )

            # Step 18: Return finalized AgentRun
            return run

        except MaxTurnsExceeded as e:
            self.handle_budget_exceeded(run, e)
            return run
        except TimeoutSecondsExceeded as e:
            self.handle_timeout_exceeded(run, e)
            return run
        except Exception as e:
            _logger.exception("Execution error for run %s: %s", run.id, e)
            self._record_failed_event(run.id, str(e))

            # Ensure token counts are persisted
            if self._budget_tracker is not None:
                run.tokens_in = self._budget_tracker.tokens_in
                run.tokens_out = self._budget_tracker.tokens_out

            run.fail(error_message=str(e))
            self.db.commit()
            return run
