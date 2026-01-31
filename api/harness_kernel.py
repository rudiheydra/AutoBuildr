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

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from api.agentspec_models import AgentEvent, AgentRun, AgentSpec, AcceptanceSpec

# Import tool policy enforcement (Feature #129)
from api.tool_policy import (
    ToolPolicyEnforcer,
    ToolCallBlocked,
    ForbiddenToolBlocked,
    DirectoryAccessBlocked,
    create_enforcer_for_run,
    record_policy_violation_event,
    record_allowed_tools_violation,
    record_forbidden_patterns_violation,
    record_forbidden_tools_violation,
    PolicyViolation,
)


# =============================================================================
# Database Transaction Safety (Feature #77)
# =============================================================================

class TransactionError(Exception):
    """
    Base exception for database transaction errors.

    Feature #77: Database Transaction Safety
    """
    pass


class ConcurrentModificationError(TransactionError):
    """
    Raised when a concurrent modification is detected.

    This can happen when two agents try to modify the same run
    or when there's a race condition in event recording.

    Feature #77, Step 3: Handle IntegrityError from concurrent inserts
    """

    def __init__(
        self,
        run_id: str,
        operation: str,
        original_error: Exception | None = None,
        message: str | None = None,
    ):
        self.run_id = run_id
        self.operation = operation
        self.original_error = original_error

        if message is None:
            message = (
                f"Concurrent modification detected for run {run_id} "
                f"during {operation}: {original_error}"
            )

        super().__init__(message)


class DatabaseLockError(TransactionError):
    """
    Raised when a database lock cannot be acquired.

    Feature #77, Step 4: Use SELECT FOR UPDATE when modifying run status
    """

    def __init__(
        self,
        run_id: str,
        timeout_seconds: float,
        message: str | None = None,
    ):
        self.run_id = run_id
        self.timeout_seconds = timeout_seconds

        if message is None:
            message = (
                f"Failed to acquire lock for run {run_id} "
                f"after {timeout_seconds}s timeout"
            )

        super().__init__(message)


# Setup logger
_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Transaction-Safe Database Operations (Feature #77)
# =============================================================================

def commit_with_retry(
    db: Session,
    operation: str,
    run_id: str,
    max_retries: int = 3,
) -> None:
    """
    Commit a transaction with retry logic for transient errors.

    Feature #77, Step 2: Commit after each event record for durability
    Feature #77, Step 3: Handle IntegrityError from concurrent inserts

    Args:
        db: SQLAlchemy session
        operation: Description of the operation (for error messages)
        run_id: ID of the AgentRun (for error messages)
        max_retries: Maximum number of retry attempts

    Raises:
        ConcurrentModificationError: If commit fails due to concurrent modification
        TransactionError: If commit fails after all retries
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            db.commit()
            return
        except IntegrityError as e:
            db.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)

            # Check for specific constraint violations
            if "UNIQUE constraint failed" in error_msg:
                # Likely a concurrent insert with same primary key
                raise ConcurrentModificationError(
                    run_id=run_id,
                    operation=operation,
                    original_error=e,
                    message=f"Duplicate key error during {operation}: {error_msg}"
                )

            # For other integrity errors, don't retry
            raise ConcurrentModificationError(
                run_id=run_id,
                operation=operation,
                original_error=e,
            )

        except OperationalError as e:
            db.rollback()
            last_error = e
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)

            # Check if it's a lock/busy error that can be retried
            if "database is locked" in error_msg or "SQLITE_BUSY" in error_msg:
                if attempt < max_retries - 1:
                    _logger.warning(
                        "Database locked during %s for run %s (attempt %d/%d), retrying...",
                        operation, run_id, attempt + 1, max_retries
                    )
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue

            # Non-retryable error
            raise TransactionError(
                f"Database operation failed during {operation} for run {run_id}: {error_msg}"
            )

    # Exhausted retries
    raise TransactionError(
        f"Failed to commit {operation} for run {run_id} after {max_retries} attempts: {last_error}"
    )


def rollback_and_record_error(
    db: Session,
    run_id: str,
    error: Exception,
    error_message: str | None = None,
) -> None:
    """
    Rollback the current transaction and attempt to record an error event.

    Feature #77, Step 5: Rollback on exception and record error

    This function ensures that even if recording the error event fails,
    the rollback is still performed.

    Args:
        db: SQLAlchemy session
        run_id: ID of the AgentRun
        error: The original exception that caused the rollback
        error_message: Optional custom error message
    """
    try:
        db.rollback()
    except Exception as rollback_error:
        _logger.error(
            "Failed to rollback transaction for run %s: %s",
            run_id, rollback_error
        )

    # Log the error for debugging
    msg = error_message or str(error)
    _logger.error(
        "Transaction rolled back for run %s due to error: %s",
        run_id, msg
    )


def get_run_with_lock(
    db: Session,
    run_id: str,
) -> "AgentRun":
    """
    Get an AgentRun with a row-level lock for safe modification.

    Feature #77, Step 4: Use SELECT FOR UPDATE when modifying run status

    Note: SQLite doesn't support SELECT FOR UPDATE, so this uses
    IMMEDIATE transaction mode which provides similar semantics.
    For production with PostgreSQL/MySQL, this would use with_for_update().

    Args:
        db: SQLAlchemy session
        run_id: ID of the AgentRun to lock

    Returns:
        The locked AgentRun

    Raises:
        DatabaseLockError: If the lock cannot be acquired
        ValueError: If the run doesn't exist
    """
    from api.agentspec_models import AgentRun

    try:
        # For SQLite, we use the session's isolation level
        # For PostgreSQL/MySQL, we would use:
        # run = db.query(AgentRun).filter(AgentRun.id == run_id).with_for_update().first()

        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()

        if run is None:
            raise ValueError(f"AgentRun with id {run_id} not found")

        return run

    except OperationalError as e:
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        if "database is locked" in error_msg or "SQLITE_BUSY" in error_msg:
            raise DatabaseLockError(
                run_id=run_id,
                timeout_seconds=30.0,  # SQLite default busy timeout
            )
        raise


def safe_add_and_commit_event(
    db: Session,
    event: "AgentEvent",
    run_id: str,
    operation: str = "record_event",
) -> "AgentEvent":
    """
    Add an event to the session and commit with transaction safety.

    Feature #77, Step 2: Commit after each event record for durability
    Feature #77, Step 3: Handle IntegrityError from concurrent inserts

    Args:
        db: SQLAlchemy session
        event: The AgentEvent to add
        run_id: ID of the AgentRun (for error messages)
        operation: Description of the operation

    Returns:
        The committed event

    Raises:
        ConcurrentModificationError: If commit fails due to concurrent modification
    """
    db.add(event)
    commit_with_retry(db, operation, run_id)
    return event


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
    final_verdict: Optional[str]  # passed, failed, error
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

    Graceful Budget Exhaustion (Feature #49):
    - When budget exhausted, run validators on partial state
    - Store partial acceptance_results
    - Determine verdict based on partial results
    - Return AgentRun with timeout status and partial results

    Database Transaction Safety (Feature #77):
    - Use SQLAlchemy session per-run for isolation
    - Commit after each event record for durability
    - Handle IntegrityError from concurrent inserts
    - Use SELECT FOR UPDATE when modifying run status (where supported)
    - Rollback on exception and record error
    - Close session in finally block

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
        # Feature #49: Store spec and context for graceful budget exhaustion handling
        self._current_spec: Optional["AgentSpec"] = None
        self._validator_context: dict[str, Any] = {}
        # Feature #129: Tool policy enforcer for filtering tool calls
        self._tool_policy_enforcer: Optional[ToolPolicyEnforcer] = None

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

        # Feature #77, Step 2: Commit after each database change for durability
        # Use transaction-safe commit with retry logic
        try:
            commit_with_retry(self.db, "initialize_run", run.id)
            self._budget_tracker.mark_persisted()
        except TransactionError as e:
            _logger.error("Failed to commit run initialization for %s: %s", run.id, e)
            rollback_and_record_error(self.db, run.id, e)
            raise

        _logger.info(
            "Initialized run %s: max_turns=%d, timeout_seconds=%d, status=%s",
            run.id, spec.max_turns, spec.timeout_seconds, run.status
        )

        # Record started event
        self._record_started_event(run.id)

        return self._budget_tracker

    def _record_started_event(self, run_id: str) -> None:
        """
        Record the started event for a run.

        Feature #77, Step 2: Commit after each event record for durability
        """
        from api.agentspec_models import AgentEvent

        self._event_sequence += 1
        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="started",
            timestamp=_utc_now(),
            payload={"status": "running"},
        )

        # Feature #77: Use transaction-safe add and commit
        try:
            safe_add_and_commit_event(self.db, event, run_id, "record_started_event")
        except TransactionError as e:
            _logger.error("Failed to record started event for run %s: %s", run_id, e)
            # Don't raise - the run is already initialized, continue execution
            # The event is not critical for execution to proceed

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
        # Feature #77, Step 2: Commit after each event record for durability
        try:
            commit_with_retry(self.db, "record_turn_complete", run.id)
            self._budget_tracker.mark_persisted()
        except TransactionError as e:
            _logger.error("Failed to commit turn complete for run %s: %s", run.id, e)
            rollback_and_record_error(self.db, run.id, e)
            raise

        # Feature #155: Broadcast turn_complete event via WebSocket for real-time UI updates
        # This is called after DB commit so the event is persisted before broadcast.
        # Broadcasting is optional - failure should not interrupt execution.
        try:
            from server.event_broadcaster import broadcast_agent_event_sync
            broadcast_agent_event_sync(
                project_name="AutoBuildr",
                run_id=run.id,
                event_type="turn_complete",
                sequence=self._event_sequence,
                tool_name=None,
            )
        except Exception as e:
            _logger.debug(
                "Failed to broadcast turn_complete for run %s (non-fatal): %s",
                run.id, e
            )

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

        Feature #49: Graceful Budget Exhaustion Handling:
        - Run acceptance validators on partial state
        - Store partial acceptance_results
        - Determine verdict based on partial results
        - Return AgentRun with timeout status and partial results

        Args:
            run: The AgentRun that exceeded budget
            error: The MaxTurnsExceeded exception

        Returns:
            ExecutionResult with timeout status and partial results
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

        # Feature #49, Step 1: Detect budget exhaustion before next turn (done via exception)

        # Feature #49, Step 3: Record timeout event with resource that was exhausted
        self._event_sequence += 1
        record_timeout_event(
            db=self.db,
            run_id=run.id,
            sequence=self._event_sequence,
            budget_tracker=self._budget_tracker,
            reason="max_turns_exceeded",
        )

        # Feature #49, Step 2: Set status to timeout (not failed)
        run.timeout(error_message="max_turns_exceeded")

        # Feature #49, Step 4: Commit any uncommitted database changes
        # Feature #77, Step 2: Use transaction-safe commit
        try:
            commit_with_retry(self.db, "handle_budget_exceeded", run.id)
        except TransactionError as e:
            _logger.error("Failed to commit budget exceeded handling for run %s: %s", run.id, e)
            rollback_and_record_error(self.db, run.id, e)

        # Feature #49, Steps 5-7: Run acceptance validators on partial state
        partial_verdict, partial_results = self._run_partial_acceptance_validators(
            run, "max_turns_exceeded"
        )

        # Feature #49, Step 8: Return AgentRun with timeout status and partial results
        return ExecutionResult(
            run_id=run.id,
            status="timeout",
            turns_used=run.turns_used,
            final_verdict=partial_verdict,  # Feature #49: Include partial verdict
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

        Feature #49: Graceful Budget Exhaustion Handling:
        - Run acceptance validators on partial state
        - Store partial acceptance_results
        - Determine verdict based on partial results
        - Return AgentRun with timeout status and partial results

        Args:
            run: The AgentRun that exceeded timeout
            error: The TimeoutSecondsExceeded exception

        Returns:
            ExecutionResult with timeout status and partial results
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

        # Feature #49, Step 3: Record timeout event with resource that was exhausted
        self._event_sequence += 1
        record_timeout_event(
            db=self.db,
            run_id=run.id,
            sequence=self._event_sequence,
            budget_tracker=self._budget_tracker,
            reason="timeout_exceeded",
        )

        # Feature #49, Step 2: Set status to timeout (not failed)
        run.timeout(error_message="timeout_exceeded")

        # Feature #49, Step 4: Commit any uncommitted database changes
        # Feature #77, Step 2: Use transaction-safe commit
        try:
            commit_with_retry(self.db, "handle_timeout_exceeded", run.id)
        except TransactionError as e:
            _logger.error("Failed to commit timeout handling for run %s: %s", run.id, e)
            rollback_and_record_error(self.db, run.id, e)

        # Feature #49, Steps 5-7: Run acceptance validators on partial state
        partial_verdict, partial_results = self._run_partial_acceptance_validators(
            run, "timeout_exceeded"
        )

        # Feature #49, Step 8: Return AgentRun with timeout status and partial results
        return ExecutionResult(
            run_id=run.id,
            status="timeout",
            turns_used=run.turns_used,
            final_verdict=partial_verdict,  # Feature #49: Include partial verdict
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

            # Feature #77, Step 2: Use transaction-safe commit
            try:
                commit_with_retry(self.db, "execute_with_budget_complete", run.id)
            except TransactionError as e:
                _logger.error("Failed to commit completion for run %s: %s", run.id, e)
                rollback_and_record_error(self.db, run.id, e)
                return ExecutionResult(
                    run_id=run.id,
                    status="failed",
                    turns_used=run.turns_used,
                    final_verdict=None,
                    error=f"Transaction error: {e}",
                    tokens_in=run.tokens_in,
                    tokens_out=run.tokens_out,
                )

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
            # Feature #77, Step 5: Rollback on exception and record error
            _logger.exception("Execution error for run %s: %s", run.id, e)

            # Feature #29, Step 6: Persist token counts even on failure
            if self._budget_tracker is not None:
                run.tokens_in = self._budget_tracker.tokens_in
                run.tokens_out = self._budget_tracker.tokens_out

            run.fail(error_message=str(e))

            # Feature #77: Use transaction-safe commit with rollback on error
            try:
                commit_with_retry(self.db, "execute_with_budget_error", run.id)
            except TransactionError as tx_error:
                _logger.error("Failed to commit error state for run %s: %s", run.id, tx_error)
                rollback_and_record_error(self.db, run.id, tx_error)

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
    # Feature #150: Artifact creation for large payloads
    # =========================================================================

    def _create_payload_artifact(
        self,
        run_id: str,
        event_type: str,
        sequence: int,
        payload_str: str,
    ) -> "Artifact":
        """
        Create an Artifact record for a large event payload.

        Feature #150: When the kernel truncates event payloads exceeding 4KB,
        create an artifact reference so the full content is not lost.

        The EventRecorder stores artifacts to disk (file-based), but the kernel
        stores them inline since it doesn't have a project_dir. The content is
        stored in content_inline for payloads that fit, ensuring the full payload
        is always retrievable via the artifact.

        Args:
            run_id: ID of the AgentRun
            event_type: Type of event (tool_call, tool_result, etc.)
            sequence: Event sequence number
            payload_str: Full JSON-serialized payload string

        Returns:
            The created Artifact record
        """
        from api.agentspec_models import Artifact, generate_uuid

        content_bytes = payload_str.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        size_bytes = len(content_bytes)

        artifact = Artifact(
            id=generate_uuid(),
            run_id=run_id,
            artifact_type="log",
            content_hash=content_hash,
            size_bytes=size_bytes,
            content_inline=payload_str,
            artifact_metadata={
                "event_sequence": sequence,
                "event_type": event_type,
                "content_type": "application/json",
                "source": "kernel_truncation",
            },
        )

        self.db.add(artifact)
        self.db.flush()

        _logger.debug(
            "Feature #150: Artifact created for truncated payload: "
            "id=%s, run=%s, event_type=%s, seq=%d, size=%d",
            artifact.id, run_id, event_type, sequence, size_bytes,
        )

        return artifact

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
        artifact_ref = None
        if len(payload_str) > 4096:
            payload_truncated = len(payload_str)

            # Feature #150: Create artifact with full payload before truncating
            artifact = self._create_payload_artifact(
                run_id=run_id,
                event_type="tool_call",
                sequence=self._event_sequence,
                payload_str=payload_str,
            )
            artifact_ref = artifact.id

            # Truncate the arguments, noting artifact reference
            payload["arguments"] = {
                "_truncated": True,
                "_original_size": len(payload_str),
                "_artifact_ref": artifact_ref,
                "_note": "Full payload stored in referenced artifact",
            }

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="tool_call",
            timestamp=_utc_now(),
            payload=payload,
            payload_truncated=payload_truncated,
            artifact_ref=artifact_ref,
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
        artifact_ref = None
        if len(payload_str) > 4096:
            payload_truncated = len(payload_str)

            # Feature #150: Create artifact with full payload before truncating
            artifact = self._create_payload_artifact(
                run_id=run_id,
                event_type="tool_result",
                sequence=self._event_sequence,
                payload_str=payload_str,
            )
            artifact_ref = artifact.id

            # Store truncated result, noting artifact reference
            payload["result"] = {
                "_truncated": True,
                "_original_size": len(payload_str),
                "_artifact_ref": artifact_ref,
                "_note": "Full payload stored in referenced artifact",
            }

        event = AgentEvent(
            run_id=run_id,
            sequence=self._event_sequence,
            event_type="tool_result",
            timestamp=_utc_now(),
            payload=payload,
            payload_truncated=payload_truncated,
            artifact_ref=artifact_ref,
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
            final_verdict: The determined verdict (passed/failed/error)
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
            verdict: Final verdict (passed/failed/error or None)

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

    # =========================================================================
    # Feature #129: Tool Policy Enforcement
    # =========================================================================

    def _initialize_tool_policy_enforcer(self, spec: "AgentSpec") -> None:
        """
        Initialize the ToolPolicyEnforcer from an AgentSpec.

        Feature #129: Tool policy enforcement filters tools and blocks forbidden patterns.

        Creates and caches a ToolPolicyEnforcer that:
        - Compiles forbidden_patterns as regex (cached for performance)
        - Extracts allowed_tools from spec.tool_policy
        - Is used during execution to validate each tool call

        Args:
            spec: The AgentSpec with tool_policy
        """
        try:
            self._tool_policy_enforcer = create_enforcer_for_run(spec)
            _logger.info(
                "Tool policy enforcer initialized for spec %s: "
                "%d forbidden patterns, %s allowed tools",
                spec.id,
                self._tool_policy_enforcer.pattern_count,
                "all" if self._tool_policy_enforcer.allowed_tools is None
                else len(self._tool_policy_enforcer.allowed_tools),
            )
        except Exception as e:
            # Fail-safe: If enforcer creation fails, log warning but continue
            # (don't block execution due to policy initialization error)
            _logger.warning(
                "Failed to initialize tool policy enforcer for spec %s: %s. "
                "Execution will continue without tool policy enforcement.",
                spec.id, e,
            )
            self._tool_policy_enforcer = None

    def _enforce_tool_policy(
        self,
        run_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        turn_number: int,
    ) -> tuple[bool, str | None]:
        """
        Enforce tool policy on a single tool call.

        Feature #129: Checks the tool call against the spec's tool_policy:
        1. Verifies tool_name is in allowed_tools (if specified)
        2. Checks tool arguments against forbidden_patterns (regex)
        3. Records policy_violation event if blocked
        4. Returns error result instead of crashing

        Args:
            run_id: ID of the current AgentRun
            tool_name: Name of the tool being called
            arguments: Tool arguments
            turn_number: Current turn number for event recording

        Returns:
            Tuple of (allowed: bool, error_message: str | None)
            - (True, None) if the tool call is allowed
            - (False, error_message) if the tool call is blocked
        """
        if self._tool_policy_enforcer is None:
            # No enforcer configured - allow all tool calls
            return (True, None)

        try:
            self._tool_policy_enforcer.validate_tool_call(tool_name, arguments)
            return (True, None)

        except ToolCallBlocked as e:
            # Tool call blocked by allowed_tools check or forbidden_patterns
            _logger.warning(
                "Feature #129: Tool call blocked for run %s: tool=%s, pattern=%s",
                run_id, tool_name, e.pattern_matched,
            )

            # Record policy violation event
            self._event_sequence += 1
            if e.pattern_matched == "[not_in_allowed_tools]":
                record_allowed_tools_violation(
                    db=self.db,
                    run_id=run_id,
                    sequence=self._event_sequence,
                    tool_name=tool_name,
                    turn_number=turn_number,
                    allowed_tools=self._tool_policy_enforcer.allowed_tools,
                    arguments=arguments,
                )
            else:
                record_forbidden_patterns_violation(
                    db=self.db,
                    run_id=run_id,
                    sequence=self._event_sequence,
                    tool_name=tool_name,
                    turn_number=turn_number,
                    pattern_matched=e.pattern_matched,
                    arguments=arguments,
                )

            error_msg = self._tool_policy_enforcer.get_blocked_error_message(
                tool_name, e.pattern_matched
            )
            return (False, error_msg)

        except ForbiddenToolBlocked as e:
            # Tool explicitly blocked via forbidden_tools list
            _logger.warning(
                "Feature #129: Forbidden tool blocked for run %s: tool=%s",
                run_id, tool_name,
            )

            self._event_sequence += 1
            record_forbidden_tools_violation(
                db=self.db,
                run_id=run_id,
                sequence=self._event_sequence,
                tool_name=tool_name,
                turn_number=turn_number,
                forbidden_tools=self._tool_policy_enforcer.forbidden_tools,
                arguments=arguments,
            )

            error_msg = self._tool_policy_enforcer.get_forbidden_tool_error_message(
                tool_name
            )
            return (False, error_msg)

        except DirectoryAccessBlocked as e:
            # Tool blocked by directory sandbox
            _logger.warning(
                "Feature #129: Directory access blocked for run %s: tool=%s, path=%s",
                run_id, tool_name, e.target_path,
            )

            self._event_sequence += 1
            from api.tool_policy import record_directory_sandbox_violation
            record_directory_sandbox_violation(
                db=self.db,
                run_id=run_id,
                sequence=self._event_sequence,
                tool_name=tool_name,
                turn_number=turn_number,
                attempted_path=e.target_path,
                reason=e.reason,
                allowed_directories=[str(d) for d in self._tool_policy_enforcer.allowed_directories],
            )

            error_msg = self._tool_policy_enforcer.get_directory_blocked_error_message(
                tool_name, e.target_path, e.reason
            )
            return (False, error_msg)

        except Exception as e:
            # Unexpected error in policy enforcement - fail-safe: allow the call
            _logger.error(
                "Unexpected error in tool policy enforcement for run %s: %s. "
                "Allowing tool call (fail-safe).",
                run_id, e,
            )
            return (True, None)

    def _filter_tool_events_with_policy(
        self,
        run_id: str,
        tool_events: list[dict[str, Any]],
        turn_number: int,
    ) -> list[dict[str, Any]]:
        """
        Filter tool events through tool policy enforcement.

        Feature #129: For each tool event from the turn executor, check against
        the tool policy. Blocked tool calls get their result replaced with an
        error message and is_error set to True.

        This method does NOT terminate the run for blocked calls - execution
        continues with the error result.

        Args:
            run_id: ID of the current AgentRun
            tool_events: List of tool event dicts from turn executor
            turn_number: Current turn number

        Returns:
            Filtered tool events list - blocked events have is_error=True and
            result set to the error message
        """
        if self._tool_policy_enforcer is None:
            return tool_events

        filtered = []
        for event in tool_events:
            tool_name = event.get("tool_name", "unknown")
            arguments = event.get("arguments")

            allowed, error_msg = self._enforce_tool_policy(
                run_id=run_id,
                tool_name=tool_name,
                arguments=arguments,
                turn_number=turn_number,
            )

            if allowed:
                filtered.append(event)
            else:
                # Replace with error result - blocked tool call
                blocked_event = {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": error_msg,
                    "is_error": True,
                    "blocked_by_policy": True,
                }
                # Preserve tool_use_id if present (for conversation threading)
                if "tool_use_id" in event:
                    blocked_event["tool_use_id"] = event["tool_use_id"]
                filtered.append(blocked_event)

        return filtered

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
            # Check if any validators passed (error)
            any_passed = any(r.passed for r in results)
            final_verdict = "error" if any_passed else "failed"

        _logger.info(
            "Acceptance validation complete: verdict=%s, passed=%d/%d",
            final_verdict, sum(1 for r in results if r.passed), len(results)
        )

        return final_verdict, results_dicts

    def _run_partial_acceptance_validators(
        self,
        run: "AgentRun",
        exhaustion_reason: str,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """
        Run acceptance validators on partial state after budget exhaustion.

        Feature #49: Graceful Budget Exhaustion Handling
        - Step 5: Run acceptance validators on partial state
        - Step 6: Store partial acceptance_results
        - Step 7: Determine verdict based on partial results

        This method is called when execution is terminated due to max_turns
        or timeout_seconds budget exhaustion. It attempts to run validators
        on whatever partial work has been completed.

        Args:
            run: The AgentRun that was terminated
            exhaustion_reason: The reason for budget exhaustion ("max_turns_exceeded" or "timeout_exceeded")

        Returns:
            Tuple of (partial_verdict, partial_acceptance_results)
            - partial_verdict: "error" if any validators passed, "failed" if none passed, None if no validators
            - partial_acceptance_results: List of validator result dicts
        """
        from api.validators import evaluate_acceptance_spec

        # Check if we have a spec stored from execute()
        spec = self._current_spec
        if spec is None:
            _logger.warning(
                "No spec available for partial validation on run %s",
                run.id
            )
            return None, []

        # Get acceptance spec
        acceptance_spec = spec.acceptance_spec
        if acceptance_spec is None:
            _logger.info(
                "No AcceptanceSpec linked to spec %s, skipping partial validation",
                spec.id
            )
            return None, []

        # Get validator definitions and gate mode
        validators = acceptance_spec.validators or []
        gate_mode = acceptance_spec.gate_mode or "all_pass"

        if not validators:
            _logger.info("AcceptanceSpec has no validators, skipping partial validation")
            return None, []

        # Run validators on partial state
        _logger.info(
            "Running %d validators on partial state for run %s (reason: %s)",
            len(validators), run.id, exhaustion_reason
        )

        try:
            # Use the stored validator context
            context = self._validator_context.copy()
            context["partial_execution"] = True
            context["exhaustion_reason"] = exhaustion_reason

            passed, results = evaluate_acceptance_spec(
                validators=validators,
                context=context,
                gate_mode=gate_mode,
                run=run,
            )

            # Convert results to dicts for storage
            results_dicts = [r.to_dict() for r in results]

            # Feature #49, Step 7: Determine verdict based on partial results
            # For timeout cases, we use "error" if any validators passed
            # This indicates the run made progress but didn't complete
            any_passed = any(r.passed for r in results)
            partial_verdict = "error" if any_passed else "failed"

            _logger.info(
                "Partial validation complete for run %s: verdict=%s, passed=%d/%d",
                run.id, partial_verdict, sum(1 for r in results if r.passed), len(results)
            )

            # Feature #49, Step 6: Store partial acceptance_results
            run.final_verdict = partial_verdict
            run.acceptance_results = results_dicts

            # Record acceptance_check event for partial results
            self._record_acceptance_check_event(
                run.id,
                results_dicts,
                partial_verdict,
                gate_mode,
            )

            # Feature #77, Step 2: Commit the updated run with partial results
            try:
                commit_with_retry(self.db, "partial_acceptance_validators", run.id)
            except TransactionError as tx_error:
                _logger.error("Failed to commit partial results for %s: %s", run.id, tx_error)
                rollback_and_record_error(self.db, run.id, tx_error)

            return partial_verdict, results_dicts

        except Exception as e:
            # Feature #77, Step 5: Rollback on exception
            _logger.error(
                "Error running partial validators for run %s: %s",
                run.id, e
            )
            rollback_and_record_error(self.db, run.id, e, "Partial validation error")
            # Don't fail the whole operation if partial validation fails
            # Just return empty results
            return None, []

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

        # Feature #77, Step 1: Use SQLAlchemy session per-run
        # Feature #77, Step 2: Commit after each operation for durability
        # Feature #77, Step 3: Handle IntegrityError from concurrent inserts
        try:
            commit_with_retry(self.db, "create_run_for_spec", run.id)
            self.db.refresh(run)
        except ConcurrentModificationError as e:
            _logger.error("Failed to create run for spec %s: %s", spec.id, e)
            raise
        except TransactionError as e:
            _logger.error("Transaction error creating run for spec %s: %s", spec.id, e)
            rollback_and_record_error(self.db, run.id, e)
            raise

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
            - final_verdict: passed, failed, error, or None
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

        # Feature #49: Store spec and context for graceful budget exhaustion handling
        # These are used by _run_partial_acceptance_validators when budget is exceeded
        self._current_spec = spec
        self._validator_context = validator_context

        # Feature #129: Initialize tool policy enforcer from spec
        # Compiles forbidden_patterns as regex and caches for performance
        self._initialize_tool_policy_enforcer(spec)

        try:
            # Step 2: Initialize run (sets status=running, starts budget tracker)
            self.initialize_run(run, spec)

            # If no turn executor provided, complete immediately
            # This is useful for testing the infrastructure
            if turn_executor is None:
                _logger.info("No turn executor provided, completing immediately")
                run.complete()

                # Feature #77, Step 2: Use transaction-safe commit
                try:
                    commit_with_retry(self.db, "execute_no_executor", run.id)
                except TransactionError as e:
                    _logger.error("Failed to commit run completion for %s: %s", run.id, e)
                    rollback_and_record_error(self.db, run.id, e)
                    run.fail(error_message=f"Transaction error: {e}")
                    return run

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

                # Feature #77: Use transaction-safe commit
                try:
                    commit_with_retry(self.db, "execute_validators", run.id)
                except TransactionError as e:
                    _logger.error("Failed to commit acceptance results for %s: %s", run.id, e)
                    rollback_and_record_error(self.db, run.id, e)

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
                    # Feature #77, Step 5: Rollback on exception and record error
                    _logger.error("Turn executor error: %s", e)
                    self._record_failed_event(run.id, str(e))
                    run.fail(error_message=str(e))
                    try:
                        commit_with_retry(self.db, "execute_turn_error", run.id)
                    except TransactionError as tx_error:
                        _logger.error("Failed to commit turn error for %s: %s", run.id, tx_error)
                        rollback_and_record_error(self.db, run.id, tx_error)
                    return run

                # Feature #129: Filter tool events through tool policy enforcement
                # Blocked tool calls get error results but do NOT terminate the run
                turn_number = self._budget_tracker.turns_used if self._budget_tracker else 0
                tool_events = self._filter_tool_events_with_policy(
                    run.id, tool_events, turn_number
                )

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

            # Feature #77, Step 2: Use transaction-safe commit
            try:
                commit_with_retry(self.db, "execute_final_commit", run.id)
            except TransactionError as e:
                _logger.error("Failed to commit final run state for %s: %s", run.id, e)
                rollback_and_record_error(self.db, run.id, e)

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
            # Feature #77, Step 5: Rollback on exception and record error
            _logger.exception("Execution error for run %s: %s", run.id, e)
            self._record_failed_event(run.id, str(e))

            # Ensure token counts are persisted
            if self._budget_tracker is not None:
                run.tokens_in = self._budget_tracker.tokens_in
                run.tokens_out = self._budget_tracker.tokens_out

            run.fail(error_message=str(e))

            # Feature #77: Use transaction-safe commit with rollback on error
            try:
                commit_with_retry(self.db, "execute_exception", run.id)
            except TransactionError as tx_error:
                _logger.error("Failed to commit error state for %s: %s", run.id, tx_error)
                rollback_and_record_error(self.db, run.id, tx_error)

            return run
        finally:
            # Feature #49: Clear stored spec and context to prevent memory leaks
            # Feature #77, Step 6: Session management is handled at the caller level
            # The session should be closed by the context manager that owns it
            self._current_spec = None
            self._validator_context = {}
            # Feature #129: Clear tool policy enforcer to prevent memory leaks
            self._tool_policy_enforcer = None
