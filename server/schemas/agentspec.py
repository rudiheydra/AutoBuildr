"""
AgentSpec Pydantic Schemas
==========================

Request/Response schemas for AgentSpec API endpoints.

These schemas provide:
- Input validation for API requests
- Response serialization
- OpenAPI documentation

Mirrors the SQLAlchemy models in api/agentspec_models.py
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Constants (must match api/agentspec_models.py)
# =============================================================================

TASK_TYPES = Literal["coding", "testing", "refactoring", "documentation", "audit", "custom"]
RUN_STATUSES = Literal["pending", "running", "paused", "completed", "failed", "timeout"]
VERDICTS = Literal["passed", "failed", "partial"]
GATE_MODES = Literal["all_pass", "any_pass", "weighted"]
RETRY_POLICIES = Literal["none", "fixed", "exponential"]
EVENT_TYPES = Literal[
    "started", "tool_call", "tool_result", "turn_complete",
    "acceptance_check", "completed", "failed", "paused", "resumed"
]
ARTIFACT_TYPES = Literal["file_change", "test_result", "log", "metric", "snapshot"]
VALIDATOR_TYPES = Literal["test_pass", "file_exists", "lint_clean", "forbidden_output", "custom"]


# =============================================================================
# Nested Schemas
# =============================================================================

class ToolPolicy(BaseModel):
    """Tool policy defining what an agent can use."""

    policy_version: str = Field(default="v1", description="Policy version for forward compatibility")
    allowed_tools: list[str] = Field(
        ...,
        min_length=1,
        description="List of MCP tool names the agent can use"
    )
    forbidden_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns to block in tool arguments"
    )
    tool_hints: dict[str, str] = Field(
        default_factory=dict,
        description="Optional hints for tool usage"
    )


class Validator(BaseModel):
    """Single validator definition for AcceptanceSpec."""

    type: VALIDATOR_TYPES = Field(..., description="Validator type")
    config: dict[str, Any] = Field(..., description="Type-specific configuration")
    weight: float = Field(default=1.0, ge=0.0, le=10.0, description="Weight for weighted scoring")
    required: bool = Field(default=False, description="Must pass regardless of gate_mode")

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: dict[str, Any], info) -> dict[str, Any]:
        """Validate config based on validator type."""
        # Type-specific validation can be added here
        return v


# =============================================================================
# AgentSpec Schemas
# =============================================================================

class AgentSpecCreate(BaseModel):
    """Request schema for creating an AgentSpec."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$',
        description="Machine-friendly name (lowercase, hyphens allowed)"
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-friendly display name"
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Emoji or icon identifier"
    )

    objective: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Clear goal statement"
    )
    task_type: TASK_TYPES = Field(..., description="Type of task")
    context: dict[str, Any] | None = Field(
        default=None,
        description="Task-specific context"
    )

    tool_policy: ToolPolicy = Field(..., description="Tool access policy")
    max_turns: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Max API round-trips"
    )
    timeout_seconds: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="Wall-clock timeout in seconds"
    )

    parent_spec_id: str | None = Field(
        default=None,
        description="Parent spec ID for sub-agent spawning (future)"
    )
    source_feature_id: int | None = Field(
        default=None,
        description="Linked Feature ID"
    )
    priority: int = Field(
        default=500,
        ge=1,
        le=9999,
        description="Execution priority (lower = higher priority)"
    )
    tags: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Tags for filtering"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "feature-auth-login-impl",
                "display_name": "Implement Login Feature",
                "icon": "key",
                "objective": "Implement user login functionality with email/password authentication",
                "task_type": "coding",
                "context": {"feature_id": 5, "files": ["src/auth/login.ts"]},
                "tool_policy": {
                    "policy_version": "v1",
                    "allowed_tools": ["feature_get_by_id", "feature_mark_passing"],
                    "forbidden_patterns": ["rm -rf"],
                    "tool_hints": {}
                },
                "max_turns": 50,
                "timeout_seconds": 1800,
                "source_feature_id": 5,
                "priority": 100,
                "tags": ["auth", "critical"]
            }
        }


class AgentSpecUpdate(BaseModel):
    """Request schema for updating an AgentSpec.

    All fields are optional - only provided fields will be updated.

    Example:
        {
            "display_name": "Updated Feature Name",
            "max_turns": 100,
            "tags": ["updated", "priority"]
        }
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$',
        description="Machine-friendly name (lowercase, hyphens allowed)"
    )
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Human-friendly display name"
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Emoji or icon identifier"
    )

    objective: str | None = Field(
        default=None,
        min_length=10,
        max_length=5000,
        description="Clear goal statement"
    )
    task_type: TASK_TYPES | None = Field(default=None, description="Type of task")
    context: dict[str, Any] | None = Field(
        default=None,
        description="Task-specific context"
    )

    tool_policy: ToolPolicy | None = Field(default=None, description="Tool access policy")
    max_turns: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Max API round-trips"
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=60,
        le=7200,
        description="Wall-clock timeout in seconds"
    )

    parent_spec_id: str | None = Field(
        default=None,
        description="Parent spec ID for sub-agent spawning (future)"
    )
    source_feature_id: int | None = Field(
        default=None,
        description="Linked Feature ID"
    )
    priority: int | None = Field(
        default=None,
        ge=1,
        le=9999,
        description="Execution priority (lower = higher priority)"
    )
    tags: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Tags for filtering"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "display_name": "Updated Feature Name",
                "max_turns": 100,
                "priority": 50,
                "tags": ["updated", "priority"]
            }
        }


class AgentSpecResponse(BaseModel):
    """Response schema for an AgentSpec."""

    id: str
    name: str
    display_name: str
    icon: str | None
    spec_version: str

    objective: str
    task_type: str
    context: dict[str, Any] | None

    tool_policy: dict[str, Any]
    max_turns: int
    timeout_seconds: int

    parent_spec_id: str | None
    source_feature_id: int | None
    created_at: datetime
    priority: int
    tags: list[str]

    class Config:
        from_attributes = True


class AgentSpecSummary(BaseModel):
    """Lightweight summary for list views."""

    id: str
    name: str
    display_name: str
    icon: str | None
    task_type: str
    priority: int
    created_at: datetime
    source_feature_id: int | None

    # Run stats (computed)
    total_runs: int = 0
    passing_runs: int = 0
    latest_run_status: str | None = None

    class Config:
        from_attributes = True


# =============================================================================
# AcceptanceSpec Schemas
# =============================================================================

class AcceptanceSpecCreate(BaseModel):
    """Request schema for creating an AcceptanceSpec."""

    validators: list[Validator] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Validation checks to run"
    )
    gate_mode: GATE_MODES = Field(
        default="all_pass",
        description="How validators combine to determine success"
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum score for weighted mode"
    )
    retry_policy: RETRY_POLICIES = Field(
        default="none",
        description="Behavior on failure"
    )
    max_retries: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Max retry attempts"
    )
    fallback_spec_id: str | None = Field(
        default=None,
        description="Alternative spec if all retries fail"
    )

    @field_validator("min_score")
    @classmethod
    def validate_min_score(cls, v: float | None, info) -> float | None:
        """min_score required for weighted mode."""
        # This would need access to gate_mode which requires model_validator
        # Keeping simple for now
        return v


class AcceptanceSpecResponse(BaseModel):
    """Response schema for an AcceptanceSpec."""

    id: str
    agent_spec_id: str
    validators: list[dict[str, Any]]
    gate_mode: str
    min_score: float | None
    retry_policy: str
    max_retries: int
    fallback_spec_id: str | None

    class Config:
        from_attributes = True


# =============================================================================
# AgentRun Schemas
# =============================================================================

class AgentRunResponse(BaseModel):
    """Response schema for an AgentRun."""

    id: str
    agent_spec_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    turns_used: int
    tokens_in: int
    tokens_out: int
    final_verdict: str | None
    acceptance_results: list[dict[str, Any]] | None
    error: str | None
    retry_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class AgentRunSummary(BaseModel):
    """Run summary with spec info for UI display."""

    run: AgentRunResponse
    spec: AgentSpecResponse | None
    event_count: int
    artifact_count: int


class RunStatusUpdate(BaseModel):
    """Request schema for updating run status."""

    status: Literal["paused", "running"] = Field(
        ...,
        description="New status (only paused/running transitions allowed via API)"
    )


# =============================================================================
# Artifact Schemas
# =============================================================================

class ArtifactCreate(BaseModel):
    """Request schema for creating an artifact."""

    artifact_type: ARTIFACT_TYPES = Field(..., description="Type of artifact")
    content: str = Field(..., description="Content as string (base64 for binary)")
    path: str | None = Field(default=None, description="Source path for file artifacts")
    metadata: dict[str, Any] | None = Field(default=None, description="Type-specific metadata")


class ArtifactResponse(BaseModel):
    """Response schema for an artifact."""

    id: str
    run_id: str
    artifact_type: str
    path: str | None
    content_ref: str | None
    content_hash: str | None
    size_bytes: int | None
    created_at: datetime
    metadata: dict[str, Any] | None

    # Content included for small artifacts
    content_inline: str | None = None

    class Config:
        from_attributes = True


# =============================================================================
# AgentEvent Schemas
# =============================================================================

class EventCreate(BaseModel):
    """Request schema for creating an event."""

    event_type: EVENT_TYPES = Field(..., description="Type of event")
    payload: dict[str, Any] | None = Field(default=None, description="Event-specific data")
    tool_name: str | None = Field(default=None, description="Tool name for tool events")


class AgentEventResponse(BaseModel):
    """Response schema for an AgentEvent."""

    id: int
    run_id: str
    event_type: str
    timestamp: datetime
    sequence: int
    payload: dict[str, Any] | None
    payload_truncated: int | None
    artifact_ref: str | None
    tool_name: str | None

    class Config:
        from_attributes = True


# =============================================================================
# List Response Schemas
# =============================================================================

class AgentSpecListResponse(BaseModel):
    """Response for listing AgentSpecs."""

    specs: list[AgentSpecSummary]
    total: int
    offset: int
    limit: int


class AgentRunListResponse(BaseModel):
    """Response for listing AgentRuns."""

    runs: list[AgentRunResponse]
    total: int
    offset: int
    limit: int


class ArtifactListResponse(BaseModel):
    """Response for listing artifacts."""

    artifacts: list[ArtifactResponse]
    total: int


class EventListResponse(BaseModel):
    """Response for listing events."""

    events: list[AgentEventResponse]
    total: int
    has_more: bool = False
