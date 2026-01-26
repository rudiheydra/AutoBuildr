"""
WebSocket Event Broadcasting
============================

Utilities for broadcasting WebSocket events from the API layer.

This module provides functions for publishing real-time events to connected
WebSocket clients, including:
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
    from api.websocket_events import broadcast_acceptance_update

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

    def to_message(self) -> dict[str, Any]:
        """
        Convert to WebSocket message format.

        Returns:
            Dict with message type and payload following Feature #63 spec:
            - type: "agent_acceptance_update"
            - run_id: UUID of the run
            - final_verdict: Overall result
            - validator_results: Array of per-validator results
            - Each validator result: index, type, passed, message
        """
        return {
            "type": "agent_acceptance_update",
            "run_id": self.run_id,
            "final_verdict": self.final_verdict,
            "validator_results": [r.to_dict() for r in self.validator_results],
            "gate_mode": self.gate_mode,
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
