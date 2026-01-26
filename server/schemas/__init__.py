"""
Pydantic Schemas Package
========================

Organized schemas for the AutoBuildr API.
"""

# Re-export agentspec schemas for convenient access
from .agentspec import (
    # Constants
    ARTIFACT_TYPES,
    EVENT_TYPES,
    GATE_MODES,
    RETRY_POLICIES,
    RUN_STATUSES,
    TASK_TYPES,
    VALIDATOR_TYPES,
    VERDICTS,
    # Request schemas
    AcceptanceSpecCreate,
    AgentSpecCreate,
    ArtifactCreate,
    EventCreate,
    RunStatusUpdate,
    # Response schemas
    AcceptanceSpecResponse,
    AgentEventResponse,
    AgentRunResponse,
    AgentRunSummary,
    AgentSpecResponse,
    AgentSpecSummary,
    ArtifactResponse,
    # Nested schemas
    ToolPolicy,
    Validator,
)

__all__ = [
    # Constants
    "TASK_TYPES",
    "RUN_STATUSES",
    "VERDICTS",
    "GATE_MODES",
    "RETRY_POLICIES",
    "EVENT_TYPES",
    "ARTIFACT_TYPES",
    "VALIDATOR_TYPES",
    # Request schemas
    "AgentSpecCreate",
    "AcceptanceSpecCreate",
    "ArtifactCreate",
    "EventCreate",
    "RunStatusUpdate",
    # Response schemas
    "AgentSpecResponse",
    "AgentSpecSummary",
    "AcceptanceSpecResponse",
    "AgentRunResponse",
    "AgentRunSummary",
    "ArtifactResponse",
    "AgentEventResponse",
    # Nested schemas
    "ToolPolicy",
    "Validator",
]
