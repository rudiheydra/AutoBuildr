"""
Pydantic Schemas Package
========================

Organized schemas for the AutoBuildr API.
"""

# Import legacy schemas from parent schemas.py file
# These are still used by existing routers (agent.py, etc.)
import sys
from pathlib import Path

# Import from the schemas.py file (not this package)
_server_dir = Path(__file__).parent.parent
_schemas_file = _server_dir / "schemas.py"
if _schemas_file.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("legacy_schemas", _schemas_file)
    _legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_legacy)

    # Re-export commonly used legacy schemas
    AgentActionResponse = _legacy.AgentActionResponse
    AgentStartRequest = _legacy.AgentStartRequest
    AgentStatus = _legacy.AgentStatus
    SetupStatus = _legacy.SetupStatus
    # Feature schemas
    FeatureResponse = _legacy.FeatureResponse
    FeatureListResponse = _legacy.FeatureListResponse
    FeatureBulkCreateResponse = _legacy.FeatureBulkCreateResponse
    DependencyGraphResponse = _legacy.DependencyGraphResponse
    # Directory/path schemas
    DirectoryListResponse = _legacy.DirectoryListResponse
    PathValidationResponse = _legacy.PathValidationResponse
    CreateDirectoryRequest = _legacy.CreateDirectoryRequest
    # Settings schemas
    SettingsResponse = _legacy.SettingsResponse
    ModelsResponse = _legacy.ModelsResponse
    # DevServer schemas
    DevServerStartRequest = _legacy.DevServerStartRequest
    DevServerStatus = _legacy.DevServerStatus
    DevServerActionResponse = _legacy.DevServerActionResponse
    DevServerConfigResponse = _legacy.DevServerConfigResponse
    WSDevServerStatusMessage = _legacy.WSDevServerStatusMessage
    # Schedule schemas
    ScheduleResponse = _legacy.ScheduleResponse
    ScheduleListResponse = _legacy.ScheduleListResponse
    NextRunResponse = _legacy.NextRunResponse
    # WebSocket schemas
    WSAgentStatusMessage = _legacy.WSAgentStatusMessage
    # Additional Feature schemas
    FeatureCreate = _legacy.FeatureCreate
    FeatureUpdate = _legacy.FeatureUpdate
    FeatureBulkCreate = _legacy.FeatureBulkCreate
    DependencyGraphNode = _legacy.DependencyGraphNode
    DependencyUpdate = _legacy.DependencyUpdate
    # Additional Settings schemas
    ModelInfo = _legacy.ModelInfo
    SettingsUpdate = _legacy.SettingsUpdate
    # Additional DevServer schemas
    DevServerConfigUpdate = _legacy.DevServerConfigUpdate
    # Additional Schedule schemas
    ScheduleCreate = _legacy.ScheduleCreate
    ScheduleUpdate = _legacy.ScheduleUpdate
    # Additional Project schemas
    ProjectCreate = _legacy.ProjectCreate
    ProjectDetail = _legacy.ProjectDetail
    ProjectPrompts = _legacy.ProjectPrompts
    ProjectPromptsUpdate = _legacy.ProjectPromptsUpdate
    ProjectStats = _legacy.ProjectStats
    ProjectSummary = _legacy.ProjectSummary
    # Feature #203: Scaffolding schemas
    ScaffoldRequest = _legacy.ScaffoldRequest
    ScaffoldResponse = _legacy.ScaffoldResponse
    DirectoryStatusResponse = _legacy.DirectoryStatusResponse
    ClaudeMdStatusResponse = _legacy.ClaudeMdStatusResponse
    # Additional Filesystem schemas
    DirectoryEntry = _legacy.DirectoryEntry
    DriveInfo = _legacy.DriveInfo
    # Spec creation schemas
    ImageAttachment = _legacy.ImageAttachment
    # Constants
    AGENT_MASCOTS = _legacy.AGENT_MASCOTS

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
    AgentSpecUpdate,
    ArtifactCreate,
    EventCreate,
    RunStatusUpdate,
    # Response schemas
    AcceptanceSpecResponse,
    AgentEventListResponse,
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
    # Legacy schemas (from schemas.py)
    "AgentActionResponse",
    "AgentStartRequest",
    "AgentStatus",
    "SetupStatus",
    # Feature schemas
    "FeatureResponse",
    "FeatureListResponse",
    "FeatureBulkCreateResponse",
    "DependencyGraphResponse",
    "FeatureCreate",
    "FeatureUpdate",
    "FeatureBulkCreate",
    "DependencyGraphNode",
    "DependencyUpdate",
    # Directory/path schemas
    "DirectoryListResponse",
    "PathValidationResponse",
    "CreateDirectoryRequest",
    "DirectoryEntry",
    "DriveInfo",
    # Settings schemas
    "SettingsResponse",
    "ModelsResponse",
    "ModelInfo",
    "SettingsUpdate",
    # DevServer schemas
    "DevServerStartRequest",
    "DevServerStatus",
    "DevServerActionResponse",
    "DevServerConfigResponse",
    "DevServerConfigUpdate",
    "WSDevServerStatusMessage",
    # Schedule schemas
    "ScheduleResponse",
    "ScheduleListResponse",
    "NextRunResponse",
    "ScheduleCreate",
    "ScheduleUpdate",
    # Project schemas
    "ProjectCreate",
    "ProjectDetail",
    "ProjectPrompts",
    "ProjectPromptsUpdate",
    "ProjectStats",
    "ProjectSummary",
    # Feature #203: Scaffolding schemas
    "ScaffoldRequest",
    "ScaffoldResponse",
    "DirectoryStatusResponse",
    "ClaudeMdStatusResponse",
    # Spec creation schemas
    "ImageAttachment",
    # WebSocket schemas
    "WSAgentStatusMessage",
    # Constants
    "AGENT_MASCOTS",
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
    "AgentSpecUpdate",
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
    "AgentEventListResponse",
    # Nested schemas
    "ToolPolicy",
    "Validator",
]
