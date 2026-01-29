"""
AgentSpec Models
================

SQLAlchemy models for the AgentSpec execution system.

AgentSpec is the core execution primitive in AutoBuildr. It defines:
- What an agent should accomplish (objective)
- What tools it can use (tool_policy)
- How to verify completion (AcceptanceSpec)
- Execution budget (max_turns, timeout)

The harness kernel is agent-agnostic: it operates only on specs and run results.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

# Setup logger for state transitions
_logger = logging.getLogger(__name__)

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from api.database import Base


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


# =============================================================================
# Constants / Enums (as string constants for SQLite compatibility)
# =============================================================================

# Task types - what kind of work the agent performs
TASK_TYPES = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]

# Run status - lifecycle states for an agent run
RUN_STATUS = ["pending", "running", "paused", "completed", "failed", "timeout"]

# Verdict - final outcome after acceptance check
VERDICT = ["passed", "failed", "error"]

# Gate mode - how validators are combined to determine success
GATE_MODE = ["all_pass", "any_pass", "weighted"]

# Retry policy - behavior on failure
RETRY_POLICY = ["none", "fixed", "exponential"]

# Event types - audit trail events
EVENT_TYPES = [
    "started",
    "tool_call",
    "tool_result",
    "turn_complete",
    "acceptance_check",
    "completed",
    "failed",
    "paused",
    "resumed",
    "policy_violation",  # Feature #44: Tool policy violation logging
    "timeout",  # Feature #134: Kernel timeout event recording
]

# Artifact types - outputs from agent runs
ARTIFACT_TYPES = ["file_change", "test_result", "log", "metric", "snapshot"]

# Validator types - acceptance criteria checks
VALIDATOR_TYPES = ["test_pass", "file_exists", "lint_clean", "forbidden_patterns", "custom"]

# Payload size limit for events (chars) - larger outputs go to artifacts
EVENT_PAYLOAD_MAX_SIZE = 4096

# Inline content size limit for artifacts (bytes) - larger content goes to files
ARTIFACT_INLINE_MAX_SIZE = 4096

# Terminal run statuses - no transitions allowed from these states
TERMINAL_STATUSES = frozenset({"completed", "failed", "timeout"})

# Valid state transitions adjacency map
# Key: current state, Value: set of valid next states
VALID_STATE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running"}),  # Can only start running
    "running": frozenset({"paused", "completed", "failed", "timeout"}),  # Running can pause, complete, fail, or timeout
    "paused": frozenset({"running", "failed"}),  # Paused can resume or be cancelled (failed)
    "completed": frozenset(),  # Terminal - no transitions out
    "failed": frozenset(),  # Terminal - no transitions out
    "timeout": frozenset(),  # Terminal - no transitions out
}


# =============================================================================
# Exceptions
# =============================================================================

class InvalidStateTransition(Exception):
    """
    Raised when an invalid state transition is attempted on an AgentRun.

    This exception provides detailed information about the attempted transition
    to aid in debugging and error handling.
    """

    def __init__(
        self,
        run_id: str,
        current_state: str,
        target_state: str,
        message: str | None = None
    ):
        self.run_id = run_id
        self.current_state = current_state
        self.target_state = target_state

        if message is None:
            valid_targets = VALID_STATE_TRANSITIONS.get(current_state, frozenset())
            if valid_targets:
                valid_str = ", ".join(sorted(valid_targets))
                message = (
                    f"Invalid state transition for AgentRun {run_id}: "
                    f"'{current_state}' -> '{target_state}'. "
                    f"Valid transitions from '{current_state}': {valid_str}"
                )
            else:
                message = (
                    f"Invalid state transition for AgentRun {run_id}: "
                    f"'{current_state}' -> '{target_state}'. "
                    f"'{current_state}' is a terminal state with no valid transitions."
                )

        super().__init__(message)


# =============================================================================
# AgentSpec - The Core Execution Primitive
# =============================================================================

class AgentSpec(Base):
    """
    Declarative specification for a single agent execution.

    AgentSpec defines everything needed to execute an agent:
    - Identity (name, display_name, icon)
    - Objective (what to accomplish)
    - Constraints (allowed tools, forbidden patterns, budget)
    - Acceptance criteria (via linked AcceptanceSpec)

    The harness kernel reads AgentSpecs and executes them without
    knowing how they were generated (DSPy, templates, manual, etc.).
    """
    __tablename__ = "agent_specs"

    __table_args__ = (
        CheckConstraint('max_turns >= 1 AND max_turns <= 500', name='ck_spec_max_turns'),
        CheckConstraint('timeout_seconds >= 60 AND timeout_seconds <= 7200', name='ck_spec_timeout'),
        Index('ix_agentspec_source_feature', 'source_feature_id'),
        Index('ix_agentspec_task_type', 'task_type'),
        Index('ix_agentspec_created', 'created_at'),
    )

    # Identity
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, unique=True)  # machine-friendly (e.g., "feature-auth-login-impl")
    display_name = Column(String(255), nullable=False)  # human-friendly
    icon = Column(String(50), nullable=True)  # emoji or icon identifier (e.g., "gear", "test-tube")

    # Version for forward compatibility
    spec_version = Column(String(20), nullable=False, default="v1")

    # Objective
    objective = Column(Text, nullable=False)  # clear goal statement
    task_type = Column(String(50), nullable=False)  # coding|testing|refactoring|documentation|audit|custom
    context = Column(JSON, nullable=True)  # task-specific context (feature_id, file_paths, etc.)

    # Tool Policy (versioned JSON)
    # Structure: {
    #   "policy_version": "v1",
    #   "allowed_tools": ["feature_get_by_id", "feature_mark_passing", ...],
    #   "forbidden_patterns": ["rm -rf", "DROP TABLE", ...],
    #   "tool_hints": {"feature_mark_passing": "Call only after verification"}
    # }
    tool_policy = Column(JSON, nullable=False)

    # Execution budget
    max_turns = Column(Integer, nullable=False, default=50)  # API round-trips
    timeout_seconds = Column(Integer, nullable=False, default=1800)  # 30 min default

    # Lineage (flat for v1, fields exist for future parent/child)
    parent_spec_id = Column(String(36), ForeignKey("agent_specs.id"), nullable=True)
    source_feature_id = Column(Integer, ForeignKey("features.id", ondelete="SET NULL"), nullable=True)

    # Spec file path (nullable, for specs loaded from files)
    spec_path = Column(String(500), nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=_utc_now)
    priority = Column(Integer, nullable=False, default=500)
    tags = Column(JSON, nullable=True)  # ["auth", "critical", "v1"]

    # Relationships
    acceptance_spec = relationship(
        "AcceptanceSpec",
        back_populates="agent_spec",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="AcceptanceSpec.agent_spec_id"
    )
    runs = relationship("AgentRun", back_populates="agent_spec", cascade="all, delete-orphan")
    children = relationship("AgentSpec", backref="parent", remote_side=[id])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "icon": self.icon,
            "spec_version": self.spec_version,
            "objective": self.objective,
            "task_type": self.task_type,
            "context": self.context,
            "tool_policy": self.tool_policy,
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
            "parent_spec_id": self.parent_spec_id,
            "source_feature_id": self.source_feature_id,
            "spec_path": self.spec_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "priority": self.priority,
            "tags": self.tags or [],
        }


# =============================================================================
# AcceptanceSpec - Verification Gate Definition
# =============================================================================

class AcceptanceSpec(Base):
    """
    Defines success criteria and verification gates for an AgentSpec.

    Completion is determined by external, deterministic checks - not agent
    self-reporting. Validators can include:
    - test_pass: Run a test command and check exit code
    - file_exists: Verify a file was created
    - lint_clean: Run linter with no errors
    - forbidden_patterns: Ensure certain patterns weren't output
    - custom: User-defined validation script
    """
    __tablename__ = "acceptance_specs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_spec_id = Column(
        String(36),
        ForeignKey("agent_specs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )

    # Validators stored as JSON array
    # Each validator: {
    #   "type": "test_pass"|"file_exists"|"lint_clean"|"forbidden_patterns"|"custom",
    #   "config": {...},  # type-specific configuration
    #   "weight": 1.0,    # for weighted scoring
    #   "required": false # must pass regardless of gate_mode
    # }
    validators = Column(JSON, nullable=False, default=list)

    # Gate behavior
    gate_mode = Column(String(20), nullable=False, default="all_pass")  # all_pass|any_pass|weighted
    min_score = Column(Float, nullable=True)  # for weighted mode (0.0-1.0)

    # Retry policy
    retry_policy = Column(String(20), nullable=False, default="none")  # none|fixed|exponential
    max_retries = Column(Integer, nullable=False, default=0)
    fallback_spec_id = Column(String(36), ForeignKey("agent_specs.id"), nullable=True)

    # Relationship
    agent_spec = relationship(
        "AgentSpec",
        back_populates="acceptance_spec",
        foreign_keys=[agent_spec_id]
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "agent_spec_id": self.agent_spec_id,
            "validators": self.validators or [],
            "gate_mode": self.gate_mode,
            "min_score": self.min_score,
            "retry_policy": self.retry_policy,
            "max_retries": self.max_retries,
            "fallback_spec_id": self.fallback_spec_id,
        }


# =============================================================================
# AgentRun - Execution Instance
# =============================================================================

class AgentRun(Base):
    """
    Single execution of an AgentSpec.

    Tracks the lifecycle of one agent execution:
    - Status progression (pending -> running -> completed/failed)
    - Resource usage (turns, tokens)
    - Acceptance check results
    - Linked artifacts and events
    """
    __tablename__ = "agent_runs"

    __table_args__ = (
        CheckConstraint('turns_used >= 0', name='ck_run_turns'),
        CheckConstraint('tokens_in >= 0', name='ck_run_tokens_in'),
        CheckConstraint('tokens_out >= 0', name='ck_run_tokens_out'),
        CheckConstraint('retry_count >= 0', name='ck_run_retry'),
        Index('ix_agentrun_spec', 'agent_spec_id'),
        Index('ix_agentrun_status', 'status'),
        Index('ix_agentrun_created', 'created_at'),
        Index('ix_agentrun_spec_status', 'agent_spec_id', 'status'),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_spec_id = Column(
        String(36),
        ForeignKey("agent_specs.id", ondelete="CASCADE"),
        nullable=False
    )

    # Status
    status = Column(String(20), nullable=False, default="pending")  # pending|running|paused|completed|failed|timeout
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Execution metrics
    turns_used = Column(Integer, nullable=False, default=0)
    tokens_in = Column(Integer, nullable=False, default=0)
    tokens_out = Column(Integer, nullable=False, default=0)

    # Results
    final_verdict = Column(String(20), nullable=True)  # passed|failed|error
    # Acceptance results: [{validator_index, passed, score, message}]
    acceptance_results = Column(JSON, nullable=True)

    # Error handling
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    # Relationships
    agent_spec = relationship("AgentSpec", back_populates="runs")
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")
    events = relationship("AgentEvent", back_populates="run", cascade="all, delete-orphan", order_by="AgentEvent.sequence")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "agent_spec_id": self.agent_spec_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "turns_used": self.turns_used,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "final_verdict": self.final_verdict,
            "acceptance_results": self.acceptance_results,
            "error": self.error,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    # -------------------------------------------------------------------------
    # State Machine Methods
    # -------------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        """Check if the run is in a terminal state."""
        return self.status in TERMINAL_STATUSES

    def can_transition_to(self, target_status: str) -> bool:
        """
        Check if a transition to the target status is valid.

        Args:
            target_status: The status to transition to

        Returns:
            True if the transition is valid, False otherwise
        """
        valid_targets = VALID_STATE_TRANSITIONS.get(self.status, frozenset())
        return target_status in valid_targets

    def get_valid_transitions(self) -> frozenset[str]:
        """
        Get all valid transition targets from the current state.

        Returns:
            Set of valid target statuses
        """
        return VALID_STATE_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, target_status: str, *, error_message: str | None = None) -> datetime:
        """
        Transition the run to a new status with validation.

        This method enforces the state machine rules and updates relevant
        timestamps. It should be called within a database transaction to
        ensure atomicity.

        Args:
            target_status: The status to transition to
            error_message: Optional error message (for failed/timeout transitions)

        Returns:
            The timestamp of the transition

        Raises:
            InvalidStateTransition: If the transition is not valid
            ValueError: If target_status is not a recognized status
        """
        # Validate target status is a known status
        if target_status not in RUN_STATUS:
            raise ValueError(
                f"Unknown status '{target_status}'. "
                f"Valid statuses: {', '.join(RUN_STATUS)}"
            )

        # Check if transition is valid
        if not self.can_transition_to(target_status):
            raise InvalidStateTransition(
                run_id=self.id,
                current_state=self.status,
                target_state=target_status
            )

        # Record transition timestamp
        transition_time = _utc_now()
        old_status = self.status

        # Perform the transition
        self.status = target_status

        # Handle status-specific timestamp updates
        if target_status == "running" and old_status == "pending":
            # Starting execution - set started_at
            self.started_at = transition_time

        if target_status in TERMINAL_STATUSES:
            # Terminal state - set completed_at
            self.completed_at = transition_time

            # Set error message for failure states
            if error_message and target_status in ("failed", "timeout"):
                self.error = error_message

        # Log the transition
        _logger.info(
            "AgentRun %s: status transition '%s' -> '%s' at %s",
            self.id,
            old_status,
            target_status,
            transition_time.isoformat()
        )

        return transition_time

    def start(self) -> datetime:
        """
        Start the run (transition from pending to running).

        Returns:
            The timestamp when the run started

        Raises:
            InvalidStateTransition: If the run is not in pending state
        """
        return self.transition_to("running")

    def pause(self) -> datetime:
        """
        Pause the run (transition from running to paused).

        Returns:
            The timestamp when the run was paused

        Raises:
            InvalidStateTransition: If the run is not in running state
        """
        return self.transition_to("paused")

    def resume(self) -> datetime:
        """
        Resume the run (transition from paused to running).

        Returns:
            The timestamp when the run was resumed

        Raises:
            InvalidStateTransition: If the run is not in paused state
        """
        return self.transition_to("running")

    def complete(self) -> datetime:
        """
        Complete the run successfully (transition from running to completed).

        Returns:
            The timestamp when the run completed

        Raises:
            InvalidStateTransition: If the run is not in running state
        """
        return self.transition_to("completed")

    def fail(self, error_message: str | None = None) -> datetime:
        """
        Mark the run as failed.

        Can be called from running or paused state (for cancellation).

        Args:
            error_message: Optional error message describing the failure

        Returns:
            The timestamp when the run failed

        Raises:
            InvalidStateTransition: If the run cannot transition to failed
        """
        return self.transition_to("failed", error_message=error_message)

    def timeout(self, error_message: str | None = None) -> datetime:
        """
        Mark the run as timed out (transition from running to timeout).

        Args:
            error_message: Optional message describing the timeout

        Returns:
            The timestamp when the run timed out

        Raises:
            InvalidStateTransition: If the run is not in running state
        """
        if error_message is None:
            error_message = "Execution exceeded time or turn budget"
        return self.transition_to("timeout", error_message=error_message)


# =============================================================================
# Artifact - Persisted Output
# =============================================================================

class Artifact(Base):
    """
    Any output produced during an agent run.

    Artifacts provide full traceability:
    - file_change: Diff or snapshot of modified files
    - test_result: Test output and results
    - log: Agent output logs
    - metric: Performance or quality metrics
    - snapshot: State snapshot at a point in time

    Large content is stored in files (content-addressable by SHA256).
    Small content (<=4KB) can be stored inline for convenience.
    """
    __tablename__ = "artifacts"

    __table_args__ = (
        Index('ix_artifact_run', 'run_id'),
        Index('ix_artifact_type', 'artifact_type'),
        Index('ix_artifact_hash', 'content_hash'),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False
    )

    artifact_type = Column(String(50), nullable=False)  # file_change|test_result|log|metric|snapshot
    path = Column(String(500), nullable=True)  # for file artifacts, the source path

    # Content storage (file-based for large, inline for small)
    content_ref = Column(String(255), nullable=True)  # path to content file: .autobuildr/artifacts/{run_id}/{sha256}.blob
    content_inline = Column(Text, nullable=True)  # small content stored inline (<=4KB)
    content_hash = Column(String(64), nullable=False)  # SHA256 for dedup and integrity (Feature #147: NOT NULL)
    size_bytes = Column(Integer, nullable=False)  # Feature #147: NOT NULL - always set by CRUD layer

    created_at = Column(DateTime, nullable=False, default=_utc_now)
    artifact_metadata = Column(JSON, nullable=True)  # type-specific metadata (renamed to avoid SQLAlchemy reserved word)

    # Relationships
    run = relationship("AgentRun", back_populates="artifacts")
    referencing_events = relationship("AgentEvent", back_populates="artifact", foreign_keys="[AgentEvent.artifact_ref]")  # Feature #144

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "content_ref": self.content_ref,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.artifact_metadata,  # Keep API response key as 'metadata' for backwards compat
            # Note: content_inline not included by default to avoid large responses
        }


# =============================================================================
# AgentEvent - Audit Trail
# =============================================================================

class AgentEvent(Base):
    """
    Immutable event for full auditability.

    Events capture every significant action during a run:
    - started: Run began execution
    - tool_call: Agent called a tool
    - tool_result: Tool returned a result
    - turn_complete: One API round-trip finished
    - acceptance_check: Verification gate evaluated
    - completed: Run finished successfully
    - failed: Run failed
    - paused/resumed: Run was paused/resumed

    Large payloads are summarized; full content goes to artifacts.
    """
    __tablename__ = "agent_events"

    __table_args__ = (
        Index('ix_event_run_sequence', 'run_id', 'sequence'),
        Index('ix_event_run_event_type', 'run_id', 'event_type'),  # Feature #143: Composite index for filtering events by type within a run
        Index('ix_event_timestamp', 'timestamp'),
        Index('ix_event_tool', 'tool_name'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)  # Sequential for ordering
    run_id = Column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False
    )

    event_type = Column(String(50), nullable=False)  # started|tool_call|tool_result|turn_complete|...
    timestamp = Column(DateTime, nullable=False, default=_utc_now)
    sequence = Column(Integer, nullable=False)  # ordering within run, starts at 1

    # Payload (event-specific data as JSON, capped for DB efficiency)
    # Large payloads are truncated with artifact_ref pointing to full content
    payload = Column(JSON, nullable=True)
    payload_truncated = Column(Integer, nullable=True)  # if set, original size before truncation
    artifact_ref = Column(
        String(36),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        nullable=True
    )  # Feature #144: FK to artifacts.id; SET NULL when artifact deleted

    # For tool calls (denormalized for query efficiency)
    tool_name = Column(String(100), nullable=True)

    # Relationships
    run = relationship("AgentRun", back_populates="events")
    artifact = relationship("Artifact", back_populates="referencing_events", foreign_keys=[artifact_ref])  # Feature #144

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "sequence": self.sequence,
            "payload": self.payload,
            "payload_truncated": self.payload_truncated,
            "artifact_ref": self.artifact_ref,
            "tool_name": self.tool_name,
        }


# =============================================================================
# Helper Functions
# =============================================================================

def create_tool_policy(
    allowed_tools: list[str],
    forbidden_patterns: list[str] | None = None,
    tool_hints: dict[str, str] | None = None,
    policy_version: str = "v1"
) -> dict[str, Any]:
    """
    Create a versioned tool policy dictionary.

    Args:
        allowed_tools: List of MCP tool names the agent can use
        forbidden_patterns: Regex patterns to block in tool arguments
        tool_hints: Optional hints for tool usage
        policy_version: Version string for forward compatibility

    Returns:
        Tool policy dictionary ready for storage
    """
    return {
        "policy_version": policy_version,
        "allowed_tools": allowed_tools,
        "forbidden_patterns": forbidden_patterns or [],
        "tool_hints": tool_hints or {},
    }


def create_validator(
    validator_type: str,
    config: dict[str, Any],
    weight: float = 1.0,
    required: bool = False
) -> dict[str, Any]:
    """
    Create a validator definition for AcceptanceSpec.

    Args:
        validator_type: One of VALIDATOR_TYPES
        config: Type-specific configuration
        weight: Weight for weighted scoring (default 1.0)
        required: If True, must pass regardless of gate_mode

    Returns:
        Validator dictionary ready for storage
    """
    if validator_type not in VALIDATOR_TYPES:
        raise ValueError(f"Invalid validator type: {validator_type}. Must be one of {VALIDATOR_TYPES}")

    return {
        "type": validator_type,
        "config": config,
        "weight": weight,
        "required": required,
    }
