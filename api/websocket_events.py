"""
WebSocket Event Broadcasting
============================

Utilities for broadcasting WebSocket events from the API layer.

This module provides functions for publishing real-time events to connected
WebSocket clients, including:
- agent_run_started: When a run begins (Feature #61)
- agent_acceptance_update: Validator results after acceptance gate evaluation

These events complement the existing WebSocket infrastructure in server/websocket.py
by providing a way for the HarnessKernel and validators to publish events.

The events follow the naming conventions from the app spec:
- agent_spec_created: When a new spec is registered
- agent_run_started: When a run begins
- agent_event_logged: For significant events during execution
- agent_acceptance_update: When validators run with per-validator results

Usage:
    ```python
    from api.websocket_events import broadcast_run_started, broadcast_acceptance_update

    # When AgentRun starts (Feature #61)
    await broadcast_run_started(
        project_name="my-project",
        run_id="abc-123-...",
        spec_id="def-456-...",
        display_name="Implement Feature X",
        icon="🔧",
        started_at=datetime.now(timezone.utc),
    )

    # After running acceptance validators
    results = evaluate_acceptance_spec(validators, context, gate_mode, run)

    # Broadcast the results
    await broadcast_acceptance_update(
        project_name="my-project",
        run_id="abc-123-...",
        final_verdict="passed",
        validator_results=[
            ValidatorResultPayload(
                index=0,
                type="file_exists",
                passed=True,
                message="File exists: /path/to/file",
            ),
            ...
        ]
    )
    ```
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from api.validators import ValidatorResult

# Module logger
_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Data Classes for WebSocket Message Payloads
# =============================================================================

@dataclass
class RunStartedPayload:
    """
    Payload for agent_run_started WebSocket message.

    Feature #61: WebSocket agent_run_started Event

    Attributes:
        run_id: UUID of the AgentRun
        spec_id: UUID of the AgentSpec being executed
        display_name: Human-readable name of the spec
        icon: Emoji or icon name for the spec
        started_at: When the run began execution
        timestamp: When this message was created
    """
    run_id: str
    spec_id: str
    display_name: str
    icon: Optional[str] = None
    started_at: Optional[datetime] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = _utc_now()

    def to_message(self) -> dict[str, Any]:
        """
        Convert to WebSocket message format.

        Returns:
            Dict with message type and payload following Feature #61 spec:
            - type: "agent_run_started"
            - run_id: UUID of the run
            - spec_id: UUID of the spec
            - display_name: Human-readable spec name
            - icon: Spec icon (emoji or name)
            - started_at: ISO timestamp when run started
            - timestamp: ISO timestamp when message was created
        """
        return {
            "type": "agent_run_started",
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "display_name": self.display_name,
            "icon": self.icon,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class ValidatorResultPayload:
    """
    Payload for a single validator result in the agent_acceptance_update message.

    Attributes:
        index: Position of the validator in the acceptance spec (0-indexed)
        type: Validator type (e.g., "file_exists", "test_pass", "forbidden_patterns")
        passed: Whether this validator passed
        message: Human-readable result message
        score: Optional numeric score (0.0-1.0) for weighted gates
        details: Optional additional details
    """
    index: int
    type: str
    passed: bool
    message: str
    score: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
            "type": self.type,
            "passed": self.passed,
            "message": self.message,
            "score": self.score,
            "details": self.details,
        }


@dataclass
class AcceptanceUpdatePayload:
    """
    Payload for agent_acceptance_update WebSocket message.

    Feature #63: WebSocket agent_acceptance_update Event
    Feature #160: Standardized canonical format (Record<string, AcceptanceValidatorResult>)

    Attributes:
        run_id: UUID of the AgentRun
        final_verdict: Overall result ("passed", "failed", "error", or None)
        validator_results: List of per-validator results
        gate_mode: The gate mode used ("all_pass", "any_pass", "weighted")
        timestamp: When the acceptance check was performed
    """
    run_id: str
    final_verdict: Optional[str]
    validator_results: List[ValidatorResultPayload]
    gate_mode: str = "all_pass"
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = _utc_now()

    def _build_acceptance_results_record(self) -> dict[str, dict[str, Any]]:
        """
        Build canonical Record<string, AcceptanceValidatorResult> from validator results.

        Feature #160: Both API and WebSocket now emit the same canonical format,
        keyed by validator type string.

        Returns:
            Dict keyed by validator type, values are AcceptanceValidatorResult dicts.
        """
        record: dict[str, dict[str, Any]] = {}
        for r in self.validator_results:
            key = r.type
            # Handle duplicate types by appending index
            if key in record:
                key = f"{r.type}_{r.index}"
            record[key] = {
                "passed": r.passed,
                "message": r.message,
                "score": r.score,
                "details": r.details,
                "index": r.index,
                "required": False,  # Not available in ValidatorResultPayload
                "weight": 1.0,     # Not available in ValidatorResultPayload
            }
        return record

    def to_message(self) -> dict[str, Any]:
        """
        Convert to WebSocket message format.

        Feature #160: Emits acceptance_results as Record<string, AcceptanceValidatorResult>
        matching the same canonical format used by the REST API GET /api/agent-runs/:id.

        Returns:
            Dict with message type and payload:
            - type: "agent_acceptance_update"
            - run_id: UUID of the run
            - final_verdict: Overall result
            - acceptance_results: Record<string, AcceptanceValidatorResult> (canonical format)
            - validator_results: Array of per-validator results (kept for backward compat)
            - gate_mode: Gate mode used
            - format_version: Version of the payload format (for future extensibility)
            - timestamp: ISO timestamp
        """
        return {
            "type": "agent_acceptance_update",
            "run_id": self.run_id,
            "final_verdict": self.final_verdict,
            "acceptance_results": self._build_acceptance_results_record(),
            "validator_results": [r.to_dict() for r in self.validator_results],
            "gate_mode": self.gate_mode,
            "format_version": 2,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# =============================================================================
# WebSocket Broadcasting Functions
# =============================================================================

def _get_connection_manager():
    """
    Get the WebSocket connection manager from server.websocket.

    Returns the global ConnectionManager instance, or None if not available.
    This handles the case where the server module may not be started.
    """
    try:
        from server.websocket import manager
        return manager
    except ImportError:
        _logger.debug("server.websocket not available - WebSocket broadcasting disabled")
        return None


# =============================================================================
# Feature #61: agent_run_started Broadcasting
# =============================================================================

async def broadcast_run_started(
    project_name: str,
    run_id: str,
    spec_id: str,
    display_name: str,
    icon: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> bool:
    """
    Broadcast agent_run_started WebSocket message to all connected clients.

    Feature #61: WebSocket agent_run_started Event

    This function publishes a message when an AgentRun status changes to running,
    containing the run_id, spec_id, display_name, icon, and started_at timestamp.

    Args:
        project_name: Name of the project for routing the message
        run_id: UUID of the AgentRun
        spec_id: UUID of the AgentSpec being executed
        display_name: Human-readable name of the spec
        icon: Emoji or icon name for the spec (optional)
        started_at: When the run started execution (optional, defaults to now)

    Returns:
        True if broadcast was attempted, False if WebSocket manager not available

    Example:
        >>> await broadcast_run_started(
        ...     project_name="my-project",
        ...     run_id="abc-123-...",
        ...     spec_id="def-456-...",
        ...     display_name="Implement User Auth",
        ...     icon="🔐",
        ...     started_at=run.started_at,
        ... )
    """
    manager = _get_connection_manager()
    if manager is None:
        _logger.debug("WebSocket manager not available, skipping run_started broadcast")
        return False

    # Set default started_at if not provided
    if started_at is None:
        started_at = _utc_now()

    # Build the message payload
    payload = RunStartedPayload(
        run_id=run_id,
        spec_id=spec_id,
        display_name=display_name,
        icon=icon,
        started_at=started_at,
    )

    message = payload.to_message()

    _logger.info(
        "Broadcasting agent_run_started for run %s: spec=%s, display_name=%s",
        run_id, spec_id, display_name
    )

    # Broadcast to all connections for this project
    try:
        await manager.broadcast_to_project(project_name, message)
        return True
    except Exception as e:
        _logger.warning(f"Failed to broadcast run_started: {e}")
        return False


def broadcast_run_started_sync(
    project_name: str,
    run_id: str,
    spec_id: str,
    display_name: str,
    icon: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> bool:
    """
    Synchronous wrapper for broadcast_run_started.

    Use this when calling from synchronous code (e.g., the HarnessKernel).
    Creates a new event loop if one isn't running, or schedules on the
    existing loop.

    Args:
        Same as broadcast_run_started

    Returns:
        True if broadcast was scheduled, False if WebSocket manager not available
    """
    manager = _get_connection_manager()
    if manager is None:
        return False

    try:
        # Check if we're in an async context
        loop = asyncio.get_running_loop()
        # Schedule the coroutine to run
        asyncio.create_task(broadcast_run_started(
            project_name=project_name,
            run_id=run_id,
            spec_id=spec_id,
            display_name=display_name,
            icon=icon,
            started_at=started_at,
        ))
        return True
    except RuntimeError:
        # No running event loop - create one
        try:
            asyncio.run(broadcast_run_started(
                project_name=project_name,
                run_id=run_id,
                spec_id=spec_id,
                display_name=display_name,
                icon=icon,
                started_at=started_at,
            ))
            return True
        except Exception as e:
            _logger.warning(f"Failed to broadcast run_started synchronously: {e}")
            return False


async def broadcast_acceptance_update(
    project_name: str,
    run_id: str,
    final_verdict: Optional[str],
    validator_results: List["ValidatorResult | ValidatorResultPayload | dict"],
    gate_mode: str = "all_pass",
) -> bool:
    """
    Broadcast agent_acceptance_update WebSocket message to all connected clients.

    Feature #63: WebSocket agent_acceptance_update Event

    This function publishes a message after acceptance gate evaluation,
    containing the run_id, final_verdict, and per-validator results.

    Args:
        project_name: Name of the project for routing the message
        run_id: UUID of the AgentRun
        final_verdict: Overall result ("passed", "failed", "error", or None)
        validator_results: List of validator results. Can be:
            - ValidatorResult from api.validators
            - ValidatorResultPayload dataclass
            - Dict with index, type, passed, message keys
        gate_mode: The gate mode used ("all_pass", "any_pass", "weighted")

    Returns:
        True if broadcast was attempted, False if WebSocket manager not available

    Example:
        >>> from api.validators import evaluate_acceptance_spec
        >>> passed, results = evaluate_acceptance_spec(validators, context, "all_pass", run)
        >>> await broadcast_acceptance_update(
        ...     project_name="my-project",
        ...     run_id=run.id,
        ...     final_verdict="passed" if passed else "failed",
        ...     validator_results=results,
        ...     gate_mode="all_pass",
        ... )
    """
    manager = _get_connection_manager()
    if manager is None:
        _logger.debug("WebSocket manager not available, skipping acceptance update broadcast")
        return False

    # Convert validator results to ValidatorResultPayload format
    payloads = []
    for idx, result in enumerate(validator_results):
        if isinstance(result, ValidatorResultPayload):
            # Already in the right format
            payloads.append(result)
        elif isinstance(result, dict):
            # Convert dict to payload
            payloads.append(ValidatorResultPayload(
                index=result.get("index", idx),
                type=result.get("type", result.get("validator_type", "unknown")),
                passed=result.get("passed", False),
                message=result.get("message", ""),
                score=result.get("score", 1.0 if result.get("passed", False) else 0.0),
                details=result.get("details", {}),
            ))
        else:
            # Assume it's a ValidatorResult from api.validators
            # Use hasattr to check for the expected attributes
            if hasattr(result, "passed") and hasattr(result, "message"):
                payloads.append(ValidatorResultPayload(
                    index=idx,
                    type=getattr(result, "validator_type", "unknown"),
                    passed=result.passed,
                    message=result.message,
                    score=getattr(result, "score", 1.0 if result.passed else 0.0),
                    details=getattr(result, "details", {}),
                ))
            else:
                _logger.warning(f"Unknown validator result type at index {idx}: {type(result)}")
                continue

    # Build the message payload
    payload = AcceptanceUpdatePayload(
        run_id=run_id,
        final_verdict=final_verdict,
        validator_results=payloads,
        gate_mode=gate_mode,
    )

    message = payload.to_message()

    _logger.info(
        "Broadcasting agent_acceptance_update for run %s: verdict=%s, validators=%d",
        run_id, final_verdict, len(payloads)
    )

    # Broadcast to all connections for this project
    try:
        await manager.broadcast_to_project(project_name, message)
        return True
    except Exception as e:
        _logger.warning(f"Failed to broadcast acceptance update: {e}")
        return False


def broadcast_acceptance_update_sync(
    project_name: str,
    run_id: str,
    final_verdict: Optional[str],
    validator_results: List["ValidatorResult | ValidatorResultPayload | dict"],
    gate_mode: str = "all_pass",
) -> bool:
    """
    Synchronous wrapper for broadcast_acceptance_update.

    Use this when calling from synchronous code (e.g., the HarnessKernel).
    Creates a new event loop if one isn't running, or schedules on the
    existing loop.

    Args:
        Same as broadcast_acceptance_update

    Returns:
        True if broadcast was scheduled, False if WebSocket manager not available
    """
    manager = _get_connection_manager()
    if manager is None:
        return False

    try:
        # Check if we're in an async context
        loop = asyncio.get_running_loop()
        # Schedule the coroutine to run
        asyncio.create_task(broadcast_acceptance_update(
            project_name=project_name,
            run_id=run_id,
            final_verdict=final_verdict,
            validator_results=validator_results,
            gate_mode=gate_mode,
        ))
        return True
    except RuntimeError:
        # No running event loop - create one
        try:
            asyncio.run(broadcast_acceptance_update(
                project_name=project_name,
                run_id=run_id,
                final_verdict=final_verdict,
                validator_results=validator_results,
                gate_mode=gate_mode,
            ))
            return True
        except Exception as e:
            _logger.warning(f"Failed to broadcast acceptance update synchronously: {e}")
            return False


def create_validator_result_payload(
    index: int,
    validator_result: "ValidatorResult",
) -> ValidatorResultPayload:
    """
    Create a ValidatorResultPayload from a ValidatorResult.

    Helper function to convert ValidatorResult from api.validators
    into the WebSocket message format.

    Args:
        index: Position in the validator list (0-indexed)
        validator_result: ValidatorResult from evaluate_validator

    Returns:
        ValidatorResultPayload ready for broadcasting
    """
    return ValidatorResultPayload(
        index=index,
        type=validator_result.validator_type,
        passed=validator_result.passed,
        message=validator_result.message,
        score=validator_result.score,
        details=validator_result.details,
    )


def build_acceptance_update_from_results(
    run_id: str,
    passed: bool,
    results: List["ValidatorResult"],
    gate_mode: str = "all_pass",
) -> AcceptanceUpdatePayload:
    """
    Build an AcceptanceUpdatePayload from evaluate_acceptance_spec output.

    Helper function to convert the output of evaluate_acceptance_spec
    into a ready-to-broadcast payload.

    Args:
        run_id: UUID of the AgentRun
        passed: Overall pass/fail from evaluate_acceptance_spec
        results: List of ValidatorResult from evaluate_acceptance_spec
        gate_mode: Gate mode used ("all_pass", "any_pass", "weighted")

    Returns:
        AcceptanceUpdatePayload ready for broadcasting
    """
    validator_payloads = [
        create_validator_result_payload(idx, result)
        for idx, result in enumerate(results)
    ]

    return AcceptanceUpdatePayload(
        run_id=run_id,
        final_verdict="passed" if passed else "failed",
        validator_results=validator_payloads,
        gate_mode=gate_mode,
    )


# =============================================================================
# Feature #60: agent_spec_created Broadcasting
# =============================================================================

@dataclass
class AgentSpecCreatedPayload:
    """
    Payload for agent_spec_created WebSocket message.

    Feature #60: WebSocket agent_spec_created Event

    Attributes:
        spec_id: UUID of the newly created AgentSpec
        name: Machine-readable name of the spec
        display_name: Human-readable display name
        icon: Emoji or icon identifier (optional)
        task_type: Type of task (coding, testing, etc.)
        timestamp: When the spec was created
    """
    spec_id: str
    name: str
    display_name: str
    icon: Optional[str]
    task_type: str
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = _utc_now()

    def to_message(self) -> dict[str, Any]:
        """
        Convert to WebSocket message format.

        Returns:
            Dict with message type and payload following Feature #60 spec:
            - type: "agent_spec_created"
            - spec_id: UUID of the spec
            - name: Machine-readable name
            - display_name: Human-readable name
            - icon: Emoji or icon identifier
            - task_type: Type of task
        """
        return {
            "type": "agent_spec_created",
            "spec_id": self.spec_id,
            "name": self.name,
            "display_name": self.display_name,
            "icon": self.icon,
            "task_type": self.task_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


async def broadcast_agent_spec_created(
    project_name: str,
    spec_id: str,
    name: str,
    display_name: str,
    icon: Optional[str],
    task_type: str,
) -> bool:
    """
    Broadcast agent_spec_created WebSocket message to all connected clients.

    Feature #60: WebSocket agent_spec_created Event

    This function publishes a message when a new AgentSpec is registered,
    containing the spec_id, name, display_name, icon, and task_type.

    Args:
        project_name: Name of the project for routing the message
        spec_id: UUID of the newly created AgentSpec
        name: Machine-readable name of the spec
        display_name: Human-readable display name
        icon: Emoji or icon identifier (optional)
        task_type: Type of task (coding, testing, etc.)

    Returns:
        True if broadcast was attempted, False if WebSocket manager not available

    Example:
        >>> await broadcast_agent_spec_created(
        ...     project_name="my-project",
        ...     spec_id="abc-123-...",
        ...     name="feature-auth-login-impl",
        ...     display_name="Implement Login Feature",
        ...     icon="🔐",
        ...     task_type="coding",
        ... )
    """
    manager = _get_connection_manager()
    if manager is None:
        _logger.debug("WebSocket manager not available, skipping agent_spec_created broadcast")
        return False

    # Build the message payload
    payload = AgentSpecCreatedPayload(
        spec_id=spec_id,
        name=name,
        display_name=display_name,
        icon=icon,
        task_type=task_type,
    )

    message = payload.to_message()

    _logger.info(
        "Broadcasting agent_spec_created for spec %s: name=%s, display_name=%s, task_type=%s",
        spec_id, name, display_name, task_type
    )

    # Broadcast to all connections for this project
    # Feature #60 Step 4: Broadcast to all connected clients
    # Feature #60 Step 5: Handle WebSocket errors gracefully
    try:
        await manager.broadcast_to_project(project_name, message)
        return True
    except Exception as e:
        _logger.warning(f"Failed to broadcast agent_spec_created: {e}")
        return False


def broadcast_agent_spec_created_sync(
    project_name: str,
    spec_id: str,
    name: str,
    display_name: str,
    icon: Optional[str],
    task_type: str,
) -> bool:
    """
    Synchronous wrapper for broadcast_agent_spec_created.

    Use this when calling from synchronous code (e.g., API routes).
    Creates a new event loop if one isn't running, or schedules on the
    existing loop.

    Args:
        Same as broadcast_agent_spec_created

    Returns:
        True if broadcast was scheduled, False if WebSocket manager not available
    """
    manager = _get_connection_manager()
    if manager is None:
        return False

    try:
        # Check if we're in an async context
        loop = asyncio.get_running_loop()
        # Schedule the coroutine to run
        asyncio.create_task(broadcast_agent_spec_created(
            project_name=project_name,
            spec_id=spec_id,
            name=name,
            display_name=display_name,
            icon=icon,
            task_type=task_type,
        ))
        return True
    except RuntimeError:
        # No running event loop - create one
        try:
            asyncio.run(broadcast_agent_spec_created(
                project_name=project_name,
                spec_id=spec_id,
                name=name,
                display_name=display_name,
                icon=icon,
                task_type=task_type,
            ))
            return True
        except Exception as e:
            _logger.warning(f"Failed to broadcast agent_spec_created synchronously: {e}")
            return False
