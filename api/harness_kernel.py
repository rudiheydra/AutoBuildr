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

This module implements Feature #27: Max Turns Budget Enforcement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from api.agentspec_models import AgentEvent, AgentRun, AgentSpec


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


# =============================================================================
# Budget Tracker
# =============================================================================

@dataclass
class BudgetTracker:
    """
    Tracks execution budget consumption during a run.

    This class provides methods to:
    - Track turns used
    - Check if budget allows another turn
    - Record budget status in event payloads

    Thread-safety: This class is NOT thread-safe. Each kernel execution
    should have its own BudgetTracker instance.
    """

    max_turns: int
    turns_used: int = 0
    run_id: str = ""

    # Internal tracking for persistence verification
    _last_persisted_turns: int = field(default=0, repr=False)

    def __post_init__(self):
        """Validate initial state."""
        if self.max_turns < 1:
            raise ValueError(f"max_turns must be >= 1, got {self.max_turns}")
        if self.turns_used < 0:
            raise ValueError(f"turns_used must be >= 0, got {self.turns_used}")

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

    def mark_persisted(self) -> None:
        """
        Mark the current turns_used as persisted to database.

        Call this after successfully committing the AgentRun to database.
        Used to verify persistence in tests.
        """
        self._last_persisted_turns = self.turns_used

    def is_persisted(self) -> bool:
        """
        Check if current turns_used has been persisted.

        Returns:
            True if current value matches last persisted value
        """
        return self._last_persisted_turns == self.turns_used

    def to_payload(self) -> dict[str, Any]:
        """
        Convert budget state to event payload dict.

        Returns:
            Dict suitable for AgentEvent payload
        """
        return {
            "turns_used": self.turns_used,
            "max_turns": self.max_turns,
            "remaining_turns": self.remaining_turns,
            "is_exhausted": self.is_exhausted,
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

    @property
    def is_success(self) -> bool:
        """True if execution completed with passed verdict."""
        return self.status == "completed" and self.final_verdict == "passed"

    @property
    def is_timeout(self) -> bool:
        """True if execution timed out."""
        return self.status == "timeout"


class HarnessKernel:
    """
    Agent-agnostic execution kernel for running AgentSpecs.

    The kernel orchestrates execution of an AgentSpec:
    1. Initialize AgentRun with status=running, turns_used=0
    2. Build system prompt from spec.objective + spec.context
    3. Execute turns via Claude SDK, enforcing max_turns budget
    4. Record events for each tool call and turn
    5. Run acceptance validators when agent signals completion
    6. Finalize run with verdict and status

    Budget Enforcement (Feature #27):
    - Initialize turns_used to 0 at run start
    - Increment turns_used after each Claude API response
    - Check turns_used < spec.max_turns before each turn
    - When budget exhausted: status=timeout, error="max_turns_exceeded"
    - Record timeout event with turns_used in payload
    - Persist turns_used after each turn

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
        - started_at = now
        - Budget tracker with spec.max_turns

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

        # Transition to running (handles started_at timestamp)
        run.start()

        # Create budget tracker
        self._budget_tracker = BudgetTracker(
            max_turns=spec.max_turns,
            turns_used=0,
            run_id=run.id,
        )

        # Reset event sequence
        self._event_sequence = 0

        # Persist initial state
        self.db.commit()
        self._budget_tracker.mark_persisted()

        _logger.info(
            "Initialized run %s: max_turns=%d, status=%s",
            run.id, spec.max_turns, run.status
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
        """
        if self._budget_tracker is None:
            raise RuntimeError("Budget tracker not initialized. Call initialize_run first.")

        # Step 3 of Feature #27: Check turns_used < spec.max_turns before each turn
        self._budget_tracker.check_budget_or_raise()

    def record_turn_complete(
        self,
        run: "AgentRun",
        turn_data: dict[str, Any] | None = None,
    ) -> int:
        """
        Record a completed turn and increment counter.

        Call this AFTER receiving a Claude API response.

        Args:
            run: The AgentRun to update
            turn_data: Optional data about the turn (tool calls, etc.)

        Returns:
            The new turns_used value

        Persistence:
            This method commits to ensure turns_used is persisted
            after each turn (Step 8 of Feature #27).
        """
        if self._budget_tracker is None:
            raise RuntimeError("Budget tracker not initialized. Call initialize_run first.")

        # Step 2 of Feature #27: Increment turns_used after each Claude API response
        new_turns = self._budget_tracker.increment_turns()

        # Update the AgentRun model
        run.turns_used = new_turns

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
        self.db.commit()
        self._budget_tracker.mark_persisted()

        _logger.debug(
            "Turn complete for run %s: turns=%d/%d",
            run.id, run.turns_used, self._budget_tracker.max_turns
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
        self.db.commit()

        return ExecutionResult(
            run_id=run.id,
            status="timeout",
            turns_used=run.turns_used,
            final_verdict=None,
            error="max_turns_exceeded",
        )

    def execute_with_budget(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
        turn_executor: callable,
    ) -> ExecutionResult:
        """
        Execute turns with budget enforcement.

        This is the main execution loop that enforces max_turns budget.

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
        """
        # Initialize run and budget tracker
        self.initialize_run(run, spec)

        try:
            while True:
                # Check budget before turn
                try:
                    self.check_budget_before_turn(run)
                except MaxTurnsExceeded as e:
                    return self.handle_budget_exceeded(run, e)

                # Execute one turn
                completed, turn_data = turn_executor(run, spec)

                # Record turn completion and increment counter
                self.record_turn_complete(run, turn_data)

                # Check if agent signaled completion
                if completed:
                    break

            # Normal completion
            run.complete()
            self.db.commit()

            return ExecutionResult(
                run_id=run.id,
                status="completed",
                turns_used=run.turns_used,
                final_verdict=run.final_verdict,
                error=None,
            )

        except MaxTurnsExceeded as e:
            return self.handle_budget_exceeded(run, e)
        except Exception as e:
            # Handle unexpected errors
            _logger.exception("Execution error for run %s: %s", run.id, e)
            run.fail(error_message=str(e))
            self.db.commit()

            return ExecutionResult(
                run_id=run.id,
                status="failed",
                turns_used=run.turns_used,
                final_verdict=None,
                error=str(e),
            )
