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
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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
    """Request schema for creating an AcceptanceSpec.

    Validates all field constraints including:
    - validators array structure (each with type, config dict, weight, required fields)
    - gate_mode enum validation (all_pass, any_pass, weighted)
    - retry_policy enum validation (none, fixed, exponential)
    - min_score required when gate_mode is 'weighted' (must be in range 0.0-1.0)

    Example:
        {
            "validators": [
                {
                    "type": "test_pass",
                    "config": {"command": "pytest tests/"},
                    "weight": 1.0,
                    "required": true
                }
            ],
            "gate_mode": "all_pass",
            "retry_policy": "fixed",
            "max_retries": 3
        }
    """

    validators: list[Validator] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Validation checks to run. Each validator must have type, config dict, and optionally weight (0.0-10.0) and required (bool) fields."
    )
    gate_mode: GATE_MODES = Field(
        default="all_pass",
        description="How validators combine to determine success. Must be one of: all_pass, any_pass, weighted"
    )
    min_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum score for weighted mode (0.0-1.0). Required when gate_mode is 'weighted'."
    )
    retry_policy: RETRY_POLICIES = Field(
        default="none",
        description="Behavior on failure. Must be one of: none, fixed, exponential"
    )
    max_retries: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Max retry attempts (0-10)"
    )
    fallback_spec_id: str | None = Field(
        default=None,
        description="Alternative spec ID if all retries fail"
    )

    @field_validator("gate_mode")
    @classmethod
    def validate_gate_mode_enum(cls, v: str) -> str:
        """Validate gate_mode is one of the allowed enum values.

        Args:
            v: The gate_mode string to validate

        Returns:
            The validated gate_mode

        Raises:
            ValueError: If gate_mode is not one of [all_pass, any_pass, weighted]
        """
        allowed = ["all_pass", "any_pass", "weighted"]
        if v not in allowed:
            raise ValueError(f"gate_mode must be one of {allowed}, got '{v}'")
        return v

    @field_validator("retry_policy")
    @classmethod
    def validate_retry_policy_enum(cls, v: str) -> str:
        """Validate retry_policy is one of the allowed enum values.

        Args:
            v: The retry_policy string to validate

        Returns:
            The validated retry_policy

        Raises:
            ValueError: If retry_policy is not one of [none, fixed, exponential]
        """
        allowed = ["none", "fixed", "exponential"]
        if v not in allowed:
            raise ValueError(f"retry_policy must be one of {allowed}, got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_min_score_for_weighted_mode(self) -> "AcceptanceSpecCreate":
        """Validate that min_score is provided when gate_mode is 'weighted'.

        For weighted gate mode, a minimum score threshold is required to
        determine if the agent run passed or failed. The score is calculated
        from the weighted sum of validator results.

        Returns:
            The validated model instance

        Raises:
            ValueError: If gate_mode is 'weighted' but min_score is not provided
        """
        if self.gate_mode == "weighted":
            if self.min_score is None:
                raise ValueError(
                    "min_score is required when gate_mode is 'weighted'. "
                    "Please provide a value between 0.0 and 1.0."
                )
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "validators": [
                    {
                        "type": "test_pass",
                        "config": {"command": "pytest tests/"},
                        "weight": 1.0,
                        "required": True
                    },
                    {
                        "type": "file_exists",
                        "config": {"path": "src/feature.ts"},
                        "weight": 0.5,
                        "required": False
                    }
                ],
                "gate_mode": "all_pass",
                "retry_policy": "fixed",
                "max_retries": 3
            }
        }


class AcceptanceSpecResponse(BaseModel):
    """Response schema for an AcceptanceSpec.

    This schema matches the database model output from AcceptanceSpec.to_dict().
    It represents the verification gate configuration for an AgentSpec.

    Example:
        {
            "id": "abc12345-6789-def0-1234-567890abcdef",
            "agent_spec_id": "spec12345-6789-def0-1234-567890abcdef",
            "validators": [
                {"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": true}
            ],
            "gate_mode": "all_pass",
            "min_score": null,
            "retry_policy": "fixed",
            "max_retries": 3,
            "fallback_spec_id": null
        }
    """

    id: str = Field(..., description="Unique identifier for this AcceptanceSpec")
    agent_spec_id: str = Field(..., description="ID of the linked AgentSpec (unique relationship)")
    validators: list[dict[str, Any]] = Field(
        ...,
        description="Array of validator configurations, each with type, config, weight, and required fields"
    )
    gate_mode: str = Field(
        ...,
        description="How validators combine: all_pass, any_pass, or weighted"
    )
    min_score: float | None = Field(
        default=None,
        description="Minimum score threshold for weighted mode (0.0-1.0)"
    )
    retry_policy: str = Field(
        ...,
        description="Retry behavior on failure: none, fixed, or exponential"
    )
    max_retries: int = Field(
        ...,
        description="Maximum retry attempts (0-10)"
    )
    fallback_spec_id: str | None = Field(
        default=None,
        description="Alternative AgentSpec ID to execute if all retries fail"
    )

    @field_validator("gate_mode", mode="before")
    @classmethod
    def validate_response_gate_mode(cls, v: str) -> str:
        """Validate gate_mode in response matches allowed values."""
        allowed = ["all_pass", "any_pass", "weighted"]
        if v not in allowed:
            raise ValueError(f"gate_mode must be one of {allowed}, got '{v}'")
        return v

    @field_validator("retry_policy", mode="before")
    @classmethod
    def validate_response_retry_policy(cls, v: str) -> str:
        """Validate retry_policy in response matches allowed values."""
        allowed = ["none", "fixed", "exponential"]
        if v not in allowed:
            raise ValueError(f"retry_policy must be one of {allowed}, got '{v}'")
        return v

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "abc12345-6789-def0-1234-567890abcdef",
                "agent_spec_id": "spec12345-6789-def0-1234-567890abcdef",
                "validators": [
                    {"type": "test_pass", "config": {"command": "pytest tests/"}, "weight": 1.0, "required": True}
                ],
                "gate_mode": "all_pass",
                "min_score": None,
                "retry_policy": "fixed",
                "max_retries": 3,
                "fallback_spec_id": None
            }
        }


# =============================================================================
# AgentRun Schemas
# =============================================================================

class AgentRunResponse(BaseModel):
    """Response schema for an AgentRun.

    Includes status and verdict validation, plus computed duration_seconds
    when both started_at and completed_at are present.
    """

    id: str
    agent_spec_id: str
    status: RUN_STATUSES = Field(
        ...,
        description="Current run status"
    )
    started_at: datetime | None
    completed_at: datetime | None
    turns_used: int
    tokens_in: int
    tokens_out: int
    final_verdict: VERDICTS | None = Field(
        default=None,
        description="Final acceptance verdict"
    )
    acceptance_results: list[dict[str, Any]] | None
    error: str | None
    retry_count: int
    created_at: datetime

    # Computed field for duration
    duration_seconds: float | None = Field(
        default=None,
        description="Duration in seconds (computed from timestamps)"
    )

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of the allowed values."""
        allowed = ["pending", "running", "paused", "completed", "failed", "timeout"]
        if v not in allowed:
            raise ValueError(f"status must be one of {allowed}, got '{v}'")
        return v

    @field_validator("final_verdict", mode="before")
    @classmethod
    def validate_final_verdict(cls, v: str | None) -> str | None:
        """Validate final_verdict is one of the allowed values or None."""
        if v is None:
            return v
        allowed = ["passed", "failed", "partial"]
        if v not in allowed:
            raise ValueError(f"final_verdict must be one of {allowed} or None, got '{v}'")
        return v

    def __init__(self, **data):
        """Compute duration_seconds from timestamps if both present."""
        # Compute duration before calling super().__init__
        started = data.get("started_at")
        completed = data.get("completed_at")

        if started is not None and completed is not None:
            # Both timestamps present - compute duration
            if isinstance(started, str):
                from datetime import datetime as dt
                started = dt.fromisoformat(started.replace("Z", "+00:00"))
            if isinstance(completed, str):
                from datetime import datetime as dt
                completed = dt.fromisoformat(completed.replace("Z", "+00:00"))

            duration = (completed - started).total_seconds()
            data["duration_seconds"] = duration

        super().__init__(**data)

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


class ArtifactListItemResponse(BaseModel):
    """Response schema for an artifact in list views (excludes content_inline for performance).

    This schema is optimized for listing artifacts without transferring potentially
    large inline content. Use GET /api/artifacts/:id to fetch full content.

    Example:
        {
            "id": "abc123-...",
            "run_id": "def456-...",
            "artifact_type": "test_result",
            "path": "/path/to/test/output.log",
            "content_ref": ".autobuildr/artifacts/abc123/sha256.blob",
            "content_hash": "abc123def456...",
            "size_bytes": 1024,
            "created_at": "2024-01-27T12:00:00Z",
            "metadata": {"test_suite": "unit", "passed": true},
            "has_inline_content": true
        }
    """

    id: str
    run_id: str
    artifact_type: ARTIFACT_TYPES = Field(
        ...,
        description="Type of artifact: file_change, test_result, log, metric, or snapshot"
    )
    path: str | None = Field(
        default=None,
        description="Source path for file artifacts"
    )
    content_ref: str | None = Field(
        default=None,
        description="Path to content file for large artifacts (>4KB)"
    )
    content_hash: str | None = Field(
        default=None,
        description="SHA256 hash of content for integrity and deduplication"
    )
    size_bytes: int | None = Field(
        default=None,
        description="Size of artifact content in bytes"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when artifact was created"
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Type-specific metadata (e.g., test results, diff stats)"
    )

    # Indicates if content is available inline (without the actual content)
    has_inline_content: bool = Field(
        default=False,
        description="True if content_inline is available (fetch via GET /api/artifacts/:id)"
    )

    @field_validator("artifact_type", mode="before")
    @classmethod
    def validate_artifact_type(cls, v: str) -> str:
        """Validate artifact_type is one of the allowed values."""
        allowed = ["file_change", "test_result", "log", "metric", "snapshot"]
        if v not in allowed:
            raise ValueError(f"artifact_type must be one of {allowed}, got '{v}'")
        return v

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "abc12345-6789-def0-1234-567890abcdef",
                "run_id": "run12345-6789-def0-1234-567890abcdef",
                "artifact_type": "test_result",
                "path": "/tmp/test_output.log",
                "content_ref": None,
                "content_hash": "sha256:abc123def456...",
                "size_bytes": 256,
                "created_at": "2024-01-27T12:00:00Z",
                "metadata": {"test_suite": "unit", "passed": True, "duration_ms": 1234},
                "has_inline_content": True,
            }
        }


class ArtifactResponse(BaseModel):
    """Response schema for an artifact (full details including content).

    Represents the output from an agent run, such as file changes, test results,
    logs, metrics, or snapshots.

    Example:
        {
            "id": "abc123-...",
            "run_id": "def456-...",
            "artifact_type": "test_result",
            "path": "/path/to/test/output.log",
            "content_ref": ".autobuildr/artifacts/abc123/sha256.blob",
            "content_hash": "abc123def456...",
            "size_bytes": 1024,
            "created_at": "2024-01-27T12:00:00Z",
            "metadata": {"test_suite": "unit", "passed": true},
            "content_inline": null,
            "has_inline_content": false
        }
    """

    id: str
    run_id: str
    artifact_type: ARTIFACT_TYPES = Field(
        ...,
        description="Type of artifact: file_change, test_result, log, metric, or snapshot"
    )
    path: str | None = Field(
        default=None,
        description="Source path for file artifacts"
    )
    content_ref: str | None = Field(
        default=None,
        description="Path to content file for large artifacts (>4KB)"
    )
    content_hash: str | None = Field(
        default=None,
        description="SHA256 hash of content for integrity and deduplication"
    )
    size_bytes: int | None = Field(
        default=None,
        description="Size of artifact content in bytes"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when artifact was created"
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Type-specific metadata (e.g., test results, diff stats)"
    )

    # Content included for small artifacts
    content_inline: str | None = Field(
        default=None,
        description="Inline content for small artifacts (<=4KB)"
    )

    @field_validator("artifact_type", mode="before")
    @classmethod
    def validate_artifact_type(cls, v: str) -> str:
        """Validate artifact_type is one of the allowed values.

        Args:
            v: The artifact type string to validate

        Returns:
            The validated artifact type

        Raises:
            ValueError: If artifact_type is not one of the allowed values
        """
        allowed = ["file_change", "test_result", "log", "metric", "snapshot"]
        if v not in allowed:
            raise ValueError(f"artifact_type must be one of {allowed}, got '{v}'")
        return v

    @property
    def has_inline_content(self) -> bool:
        """Check if this artifact has inline content.

        Returns True if content_inline is not None and not empty.
        This is useful for determining whether to fetch content from
        content_ref or use the inline content directly.

        Returns:
            True if inline content is available, False otherwise
        """
        return self.content_inline is not None and len(self.content_inline) > 0

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "abc12345-6789-def0-1234-567890abcdef",
                "run_id": "run12345-6789-def0-1234-567890abcdef",
                "artifact_type": "test_result",
                "path": "/tmp/test_output.log",
                "content_ref": None,
                "content_hash": "sha256:abc123def456...",
                "size_bytes": 256,
                "created_at": "2024-01-27T12:00:00Z",
                "metadata": {"test_suite": "unit", "passed": True, "duration_ms": 1234},
                "content_inline": "Test passed: 10/10 assertions",
            }
        }


# =============================================================================
# AgentEvent Schemas
# =============================================================================

class EventCreate(BaseModel):
    """Request schema for creating an event."""

    event_type: EVENT_TYPES = Field(..., description="Type of event")
    payload: dict[str, Any] | None = Field(default=None, description="Event-specific data")
    tool_name: str | None = Field(default=None, description="Tool name for tool events")


class AgentEventResponse(BaseModel):
    """Response schema for an AgentEvent.

    Represents an immutable audit trail entry from an agent run. Events capture
    every significant action: tool calls, results, acceptance checks, and state
    transitions.

    Event types:
        - started: Run began execution
        - tool_call: Agent invoked a tool
        - tool_result: Tool returned a result
        - turn_complete: One API round-trip finished
        - acceptance_check: Verification gate was evaluated
        - completed: Run finished successfully
        - failed: Run failed with error
        - paused: Run was paused
        - resumed: Run was resumed from paused state

    Example:
        {
            "id": 42,
            "run_id": "abc123-...",
            "event_type": "tool_call",
            "timestamp": "2024-01-27T12:00:00Z",
            "sequence": 5,
            "payload": {"tool": "feature_get_by_id", "args": {"feature_id": 10}},
            "payload_truncated": null,
            "artifact_ref": null,
            "tool_name": "feature_get_by_id"
        }
    """

    id: int = Field(..., description="Sequential event ID (auto-incremented)")
    run_id: str = Field(..., description="ID of the parent AgentRun")
    event_type: EVENT_TYPES = Field(
        ...,
        description="Type of event: started, tool_call, tool_result, turn_complete, acceptance_check, completed, failed, paused, or resumed"
    )
    timestamp: datetime = Field(..., description="When the event occurred")
    sequence: int = Field(
        ...,
        ge=1,
        description="Ordering within the run, starts at 1"
    )
    payload: dict[str, Any] | None = Field(
        default=None,
        description="Event-specific data (capped at 4KB, larger content uses artifact_ref)"
    )
    payload_truncated: int | None = Field(
        default=None,
        description="Original payload size if truncated (indicates content was externalized)"
    )
    artifact_ref: str | None = Field(
        default=None,
        description="Artifact ID if payload was externalized due to size"
    )
    tool_name: str | None = Field(
        default=None,
        description="Tool name for tool_call/tool_result events (denormalized for queries)"
    )

    @field_validator("event_type", mode="before")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        """Validate event_type is one of the allowed values.

        Args:
            v: The event type string to validate

        Returns:
            The validated event type

        Raises:
            ValueError: If event_type is not one of the allowed values
        """
        allowed = [
            "started", "tool_call", "tool_result", "turn_complete",
            "acceptance_check", "completed", "failed", "paused", "resumed"
        ]
        if v not in allowed:
            raise ValueError(f"event_type must be one of {allowed}, got '{v}'")
        return v

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 42,
                "run_id": "abc12345-6789-def0-1234-567890abcdef",
                "event_type": "tool_call",
                "timestamp": "2024-01-27T12:00:00Z",
                "sequence": 5,
                "payload": {"tool": "feature_get_by_id", "args": {"feature_id": 10}},
                "payload_truncated": None,
                "artifact_ref": None,
                "tool_name": "feature_get_by_id"
            }
        }


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
    """Response for listing artifacts (excludes content_inline for performance).

    This schema uses ArtifactListItemResponse which omits inline content.
    Use GET /api/artifacts/:id to fetch full artifact details with content.

    Example:
        {
            "artifacts": [...],
            "total": 10,
            "run_id": "abc123-..."
        }
    """

    artifacts: list[ArtifactListItemResponse] = Field(
        ...,
        description="List of artifacts without inline content"
    )
    total: int = Field(..., ge=0, description="Total number of artifacts for this run")
    run_id: str = Field(..., description="ID of the AgentRun these artifacts belong to")


class EventListResponse(BaseModel):
    """Response for listing events."""

    events: list[AgentEventResponse]
    total: int
    has_more: bool = False


class AgentEventListResponse(BaseModel):
    """Response schema for timeline queries of AgentEvents.

    Provides a paginated list of events with metadata useful for displaying
    an event timeline in the Run Inspector UI. Events are ordered by sequence
    number within a run.

    This schema is optimized for timeline display, including:
    - Total event count for progress indication
    - Start/end sequence numbers for navigation
    - Optional run metadata for context

    Example:
        {
            "events": [...],
            "total": 150,
            "run_id": "abc123-...",
            "start_sequence": 1,
            "end_sequence": 50,
            "has_more": true
        }
    """

    events: list[AgentEventResponse] = Field(
        ...,
        description="List of events in sequence order"
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of events for this run"
    )
    run_id: str = Field(
        ...,
        description="ID of the AgentRun these events belong to"
    )
    start_sequence: int | None = Field(
        default=None,
        ge=1,
        description="Sequence number of first event in this response"
    )
    end_sequence: int | None = Field(
        default=None,
        ge=1,
        description="Sequence number of last event in this response"
    )
    has_more: bool = Field(
        default=False,
        description="True if there are more events beyond end_sequence"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {
                        "id": 1,
                        "run_id": "abc12345-6789-def0-1234-567890abcdef",
                        "event_type": "started",
                        "timestamp": "2024-01-27T12:00:00Z",
                        "sequence": 1,
                        "payload": {"objective": "Implement feature X"},
                        "payload_truncated": None,
                        "artifact_ref": None,
                        "tool_name": None
                    }
                ],
                "total": 150,
                "run_id": "abc12345-6789-def0-1234-567890abcdef",
                "start_sequence": 1,
                "end_sequence": 50,
                "has_more": True
            }
        }
