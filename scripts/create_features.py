#!/usr/bin/env python3
"""
Feature Initializer Script for AutoBuildr
==========================================

Creates 85 features based on the app_spec.txt specification.
Features are organized by implementation phases with proper dependencies.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.database import Feature, Base

# Project directory
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Initialize database directly (avoiding the migration that imports broken models)
db_path = PROJECT_DIR / "features.db"
db_url = f"sqlite:///{db_path.as_posix()}"
engine = create_engine(db_url, connect_args={"check_same_thread": False, "timeout": 30})
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 85 Features for AutoBuildr
FEATURES = [
    # ============================================================================
    # FOUNDATION TIER (0-9) - NO DEPENDENCIES
    # These establish core database schema and fundamental models
    # ============================================================================
    {
        "category": "G. State & Persistence",
        "name": "AgentSpec SQLite Table Schema",
        "description": "Create the agent_specs table with all required columns: id (UUID), name, display_name, icon, spec_version, objective, task_type, context (JSON), tool_policy (JSON), max_turns, timeout_seconds, parent_spec_id, source_feature_id, priority, tags, created_at. Include proper indexes.",
        "steps": [
            "Verify SQLite database file exists at project root",
            "Query PRAGMA table_info(agent_specs) and confirm all columns exist with correct types",
            "Verify id column is VARCHAR(36) primary key",
            "Verify name column is VARCHAR(100) NOT NULL",
            "Verify display_name column is VARCHAR(255) NOT NULL",
            "Verify icon column is VARCHAR(50) nullable",
            "Verify spec_version column is VARCHAR(20) NOT NULL with default v1",
            "Verify objective column is TEXT NOT NULL",
            "Verify task_type column is VARCHAR(50) NOT NULL",
            "Verify context column stores valid JSON",
            "Verify tool_policy column stores valid JSON NOT NULL",
            "Verify max_turns column is INTEGER with CHECK constraint 1-500",
            "Verify timeout_seconds column is INTEGER with CHECK constraint 60-7200",
            "Query sqlite_master for indexes ix_agentspec_source_feature, ix_agentspec_task_type, ix_agentspec_created"
        ]
    },
    {
        "category": "G. State & Persistence",
        "name": "AcceptanceSpec SQLite Table Schema",
        "description": "Create the acceptance_specs table with columns: id (UUID), agent_spec_id (FK unique), validators (JSON array), gate_mode enum, min_score float, retry_policy enum, max_retries int, fallback_spec_id FK.",
        "steps": [
            "Query PRAGMA table_info(acceptance_specs)",
            "Verify id column is VARCHAR(36) primary key",
            "Verify agent_spec_id is VARCHAR(36) NOT NULL UNIQUE",
            "Verify agent_spec_id foreign key references agent_specs.id ON DELETE CASCADE",
            "Verify validators column stores JSON array",
            "Verify gate_mode column is VARCHAR(20) with default all_pass",
            "Verify min_score column is FLOAT nullable",
            "Verify retry_policy column is VARCHAR(20) with default none",
            "Verify max_retries column is INTEGER with default 0",
            "Verify fallback_spec_id foreign key references agent_specs.id nullable"
        ]
    },
    {
        "category": "G. State & Persistence",
        "name": "AgentRun SQLite Table Schema",
        "description": "Create the agent_runs table tracking execution instances: id (UUID), agent_spec_id (FK), status enum, started_at, completed_at, turns_used, tokens_in, tokens_out, final_verdict enum, acceptance_results JSON, error text, retry_count.",
        "steps": [
            "Query PRAGMA table_info(agent_runs)",
            "Verify id column is VARCHAR(36) primary key",
            "Verify agent_spec_id foreign key references agent_specs.id ON DELETE CASCADE",
            "Verify status column is VARCHAR(20) with default pending",
            "Verify started_at and completed_at columns are TIMESTAMP nullable",
            "Verify turns_used, tokens_in, tokens_out columns are INTEGER with CHECK >= 0",
            "Verify final_verdict column is VARCHAR(20) nullable",
            "Verify acceptance_results stores valid JSON",
            "Verify error column is TEXT nullable",
            "Verify retry_count column is INTEGER with CHECK >= 0",
            "Query sqlite_master for indexes ix_agentrun_spec, ix_agentrun_status"
        ]
    },
    {
        "category": "G. State & Persistence",
        "name": "Artifact SQLite Table Schema",
        "description": "Create the artifacts table for persisted outputs: id (UUID), run_id (FK), artifact_type enum, path, content_ref, content_inline (<=4KB), content_hash (SHA256), size_bytes, metadata JSON.",
        "steps": [
            "Query PRAGMA table_info(artifacts)",
            "Verify id column is VARCHAR(36) primary key",
            "Verify run_id foreign key references agent_runs.id ON DELETE CASCADE",
            "Verify artifact_type column is VARCHAR(50) NOT NULL",
            "Verify path column is VARCHAR(500) nullable",
            "Verify content_ref column is VARCHAR(255) nullable for file paths",
            "Verify content_inline column is TEXT nullable",
            "Verify content_hash column is VARCHAR(64) nullable for SHA256",
            "Verify size_bytes column is INTEGER nullable",
            "Verify metadata column stores valid JSON",
            "Query sqlite_master for indexes ix_artifact_run, ix_artifact_type, ix_artifact_hash"
        ]
    },
    {
        "category": "G. State & Persistence",
        "name": "AgentEvent SQLite Table Schema",
        "description": "Create the agent_events table for immutable audit trail: id (INTEGER autoincrement), run_id (FK), sequence, event_type enum, timestamp, payload (JSON capped at 4KB), artifact_ref, tool_name.",
        "steps": [
            "Query PRAGMA table_info(agent_events)",
            "Verify id column is INTEGER PRIMARY KEY AUTOINCREMENT",
            "Verify run_id foreign key references agent_runs.id ON DELETE CASCADE",
            "Verify sequence column is INTEGER NOT NULL",
            "Verify event_type column is VARCHAR(50) NOT NULL",
            "Verify timestamp column is TIMESTAMP NOT NULL",
            "Verify payload column stores JSON nullable",
            "Verify artifact_ref column is VARCHAR(36) nullable",
            "Verify tool_name column is VARCHAR(100) nullable",
            "Query sqlite_master for indexes ix_event_run_sequence, ix_event_timestamp"
        ]
    },
    {
        "category": "G. State & Persistence",
        "name": "Database Migration Preserves Existing Features",
        "description": "Verify the database migration that adds AgentSpec tables is additive and non-destructive. The existing features table must remain unchanged with all data intact.",
        "steps": [
            "Create a test features.db with sample Feature records",
            "Run the migration function _migrate_add_agentspec_tables",
            "Verify all original Feature records still exist with unchanged data",
            "Verify features table schema is unmodified",
            "Run migration again and verify idempotency (no errors, no duplicates)",
            "Verify new tables are created only if they do not exist"
        ]
    },
    {
        "category": "M. Form Validation",
        "name": "AgentSpec Pydantic Request/Response Schemas",
        "description": "Create Pydantic models for AgentSpec CRUD operations: AgentSpecCreate, AgentSpecUpdate, AgentSpecResponse. Validate all field constraints.",
        "steps": [
            "Define AgentSpecCreate with required fields: name, display_name, objective, task_type, tool_policy",
            "Add optional fields: icon, context, max_turns, timeout_seconds, parent_spec_id, source_feature_id, priority, tags",
            "Define Field validators for task_type in allowed values",
            "Define Field validators for max_turns range 1-500",
            "Define Field validators for timeout_seconds range 60-7200",
            "Define tool_policy structure validator ensuring policy_version and allowed_tools",
            "Define AgentSpecUpdate with all fields optional",
            "Define AgentSpecResponse matching database model to_dict output",
            "Add docstrings with JSON schema examples"
        ]
    },
    {
        "category": "M. Form Validation",
        "name": "AcceptanceSpec Pydantic Schemas",
        "description": "Create Pydantic models for AcceptanceSpec: AcceptanceSpecCreate, AcceptanceSpecResponse. Validate validators array structure, gate_mode enum, retry_policy enum.",
        "steps": [
            "Define ValidatorConfig model with type, config dict, weight, required fields",
            "Define AcceptanceSpecCreate with validators array, gate_mode, min_score, retry_policy, max_retries",
            "Add Field validator for gate_mode in [all_pass, any_pass, weighted]",
            "Add Field validator for retry_policy in [none, fixed, exponential]",
            "Add Field validator for min_score range 0.0-1.0 when gate_mode is weighted",
            "Define AcceptanceSpecResponse matching database model output"
        ]
    },
    {
        "category": "M. Form Validation",
        "name": "AgentRun Pydantic Response Schema",
        "description": "Create Pydantic models for AgentRun responses: AgentRunResponse, AgentRunListResponse. Include status enum validation.",
        "steps": [
            "Define AgentRunResponse with all AgentRun fields",
            "Add Field validator for status in [pending, running, paused, completed, failed, timeout]",
            "Add Field validator for final_verdict in [passed, failed, error] or None",
            "Define AgentRunListResponse for paginated lists",
            "Include computed fields for duration_seconds when both timestamps present"
        ]
    },
    {
        "category": "M. Form Validation",
        "name": "Artifact and AgentEvent Pydantic Schemas",
        "description": "Create Pydantic models for Artifact and AgentEvent responses. Validate artifact_type and event_type enums.",
        "steps": [
            "Define ArtifactResponse with all Artifact fields",
            "Add Field validator for artifact_type in [file_change, test_result, log, metric, snapshot]",
            "Define has_inline_content computed property",
            "Define AgentEventResponse with all AgentEvent fields",
            "Add Field validator for event_type in valid event types",
            "Define AgentEventListResponse for timeline queries"
        ]
    },

    # ============================================================================
    # API TIER (10-24) - Depend on foundation schemas
    # ============================================================================
    {
        "category": "F. UI-Backend Integration",
        "name": "POST /api/agent-specs Create AgentSpec Endpoint",
        "description": "Implement POST /api/agent-specs endpoint to create new AgentSpec records with validation and UUID generation.",
        "steps": [
            "Define FastAPI route POST /api/agent-specs with AgentSpecCreate body",
            "Validate request body against Pydantic schema",
            "Generate UUID for new spec id",
            "Set spec_version default to v1",
            "Set created_at to current UTC timestamp",
            "Create AgentSpec SQLAlchemy model instance",
            "Add to session and commit transaction",
            "Return AgentSpecResponse with status 201",
            "Return 422 for validation errors with field details",
            "Return 400 for database constraint violations"
        ],
        "depends_on_indices": [0, 6]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/agent-specs List AgentSpecs Endpoint",
        "description": "Implement GET /api/agent-specs endpoint with filtering by task_type, source_feature_id, tags and pagination support.",
        "steps": [
            "Define FastAPI route GET /api/agent-specs",
            "Add query parameters: task_type, source_feature_id, tags, limit (default 50), offset",
            "Build SQLAlchemy query with conditional filters",
            "Filter by task_type if provided",
            "Filter by source_feature_id if provided",
            "Filter by tags using JSON contains if provided",
            "Apply pagination with limit and offset",
            "Execute count query for total",
            "Return list of AgentSpecResponse with total count header"
        ],
        "depends_on_indices": [0, 6]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/agent-specs/:id Get Single AgentSpec",
        "description": "Implement GET /api/agent-specs/:id endpoint to retrieve a single AgentSpec by UUID with linked AcceptanceSpec.",
        "steps": [
            "Define FastAPI route GET /api/agent-specs/{spec_id}",
            "Validate spec_id is valid UUID format",
            "Query AgentSpec by id with eager load of acceptance_spec relationship",
            "Return 404 with message if not found",
            "Return AgentSpecResponse with nested AcceptanceSpec"
        ],
        "depends_on_indices": [0, 1, 6]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "PUT /api/agent-specs/:id Update AgentSpec",
        "description": "Implement PUT /api/agent-specs/:id endpoint to update an existing AgentSpec with partial updates.",
        "steps": [
            "Define FastAPI route PUT /api/agent-specs/{spec_id} with AgentSpecUpdate body",
            "Query existing AgentSpec by id",
            "Return 404 if not found",
            "Update only fields that are provided (not None)",
            "Validate updated max_turns and timeout_seconds against constraints",
            "Commit transaction",
            "Return updated AgentSpecResponse"
        ],
        "depends_on_indices": [0, 6]
    },
    {
        "category": "J. Data Cleanup & Cascade",
        "name": "DELETE /api/agent-specs/:id Cascade Delete",
        "description": "Implement DELETE /api/agent-specs/:id endpoint with proper cascade behavior to delete AcceptanceSpec, AgentRuns, Artifacts, and Events.",
        "steps": [
            "Define FastAPI route DELETE /api/agent-specs/{spec_id}",
            "Query AgentSpec by id",
            "Return 404 if not found",
            "Verify ON DELETE CASCADE is configured in foreign keys",
            "Delete the AgentSpec record",
            "Commit transaction",
            "Verify AcceptanceSpec is deleted",
            "Verify all AgentRuns are deleted",
            "Verify all Artifacts for those runs are deleted",
            "Verify all AgentEvents for those runs are deleted",
            "Return 204 No Content"
        ],
        "depends_on_indices": [0, 1, 2, 3, 4]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "POST /api/agent-specs/:id/execute Trigger Execution",
        "description": "Implement POST /api/agent-specs/:id/execute endpoint to trigger HarnessKernel execution and create AgentRun.",
        "steps": [
            "Define FastAPI route POST /api/agent-specs/{spec_id}/execute",
            "Query AgentSpec by id and verify exists",
            "Return 404 if spec not found",
            "Create new AgentRun with status=pending",
            "Set created_at to current UTC timestamp",
            "Commit run record to database",
            "Queue execution task (async background)",
            "Return AgentRunResponse with status 202 Accepted"
        ],
        "depends_on_indices": [0, 2, 8]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/agent-runs List Runs Endpoint",
        "description": "Implement GET /api/agent-runs endpoint with filtering by agent_spec_id and status with pagination.",
        "steps": [
            "Define FastAPI route GET /api/agent-runs",
            "Add query parameters: agent_spec_id, status, limit, offset",
            "Build query with conditional filters",
            "Filter by agent_spec_id if provided",
            "Filter by status if provided",
            "Order by created_at descending",
            "Apply pagination",
            "Return AgentRunListResponse with total count"
        ],
        "depends_on_indices": [2, 8]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/agent-runs/:id Get Run Details",
        "description": "Implement GET /api/agent-runs/:id endpoint to retrieve full run details with spec info.",
        "steps": [
            "Define FastAPI route GET /api/agent-runs/{run_id}",
            "Query AgentRun by id with eager load of agent_spec",
            "Return 404 if not found",
            "Include spec display_name and icon in response",
            "Return AgentRunResponse with nested spec summary"
        ],
        "depends_on_indices": [2, 8]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/agent-runs/:id/events Event Timeline",
        "description": "Implement GET /api/agent-runs/:id/events endpoint to retrieve ordered event timeline with filtering.",
        "steps": [
            "Define FastAPI route GET /api/agent-runs/{run_id}/events",
            "Add query parameters: event_type filter, limit, offset",
            "Query AgentEvents by run_id ordered by sequence",
            "Filter by event_type if provided",
            "Apply pagination for large event streams",
            "Return AgentEventListResponse"
        ],
        "depends_on_indices": [4, 9]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/agent-runs/:id/artifacts List Artifacts",
        "description": "Implement GET /api/agent-runs/:id/artifacts endpoint to list artifacts without inline content for performance.",
        "steps": [
            "Define FastAPI route GET /api/agent-runs/{run_id}/artifacts",
            "Add query parameter: artifact_type filter",
            "Query Artifacts by run_id",
            "Filter by artifact_type if provided",
            "Exclude content_inline from list response for performance",
            "Return list of ArtifactResponse without content"
        ],
        "depends_on_indices": [3, 9]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "GET /api/artifacts/:id/content Download Content",
        "description": "Implement GET /api/artifacts/:id/content endpoint to download artifact content either inline or from file.",
        "steps": [
            "Define FastAPI route GET /api/artifacts/{artifact_id}/content",
            "Query Artifact by id",
            "Return 404 if not found",
            "If content_inline is set, return it as response body",
            "If content_ref is set, verify file exists",
            "Stream file content with appropriate Content-Type",
            "Set Content-Disposition header for download",
            "Handle missing file gracefully with 404"
        ],
        "depends_on_indices": [3, 9]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "POST /api/agent-runs/:id/pause Pause Agent",
        "description": "Implement POST /api/agent-runs/:id/pause endpoint to pause a running agent with proper validation.",
        "steps": [
            "Define FastAPI route POST /api/agent-runs/{run_id}/pause",
            "Query AgentRun by id",
            "Return 404 if not found",
            "Return 409 Conflict if status is not running",
            "Update status to paused",
            "Record paused AgentEvent",
            "Commit transaction",
            "Signal kernel to pause",
            "Return updated AgentRunResponse"
        ],
        "depends_on_indices": [2, 4, 8]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "POST /api/agent-runs/:id/resume Resume Agent",
        "description": "Implement POST /api/agent-runs/:id/resume endpoint to resume a paused agent.",
        "steps": [
            "Define FastAPI route POST /api/agent-runs/{run_id}/resume",
            "Query AgentRun by id",
            "Return 404 if not found",
            "Return 409 Conflict if status is not paused",
            "Update status to running",
            "Record resumed AgentEvent",
            "Commit transaction",
            "Signal kernel to resume",
            "Return updated AgentRunResponse"
        ],
        "depends_on_indices": [2, 4, 8]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "POST /api/agent-runs/:id/cancel Cancel Agent",
        "description": "Implement POST /api/agent-runs/:id/cancel endpoint to cancel a running or paused agent.",
        "steps": [
            "Define FastAPI route POST /api/agent-runs/{run_id}/cancel",
            "Query AgentRun by id",
            "Return 404 if not found",
            "Return 409 if status is already completed, failed, or timeout",
            "Update status to failed",
            "Set error to user_cancelled",
            "Set completed_at to current timestamp",
            "Record failed event with cancellation reason",
            "Signal kernel to abort",
            "Return updated AgentRunResponse"
        ],
        "depends_on_indices": [2, 4, 8]
    },

    # ============================================================================
    # KERNEL TIER (25-39) - Core execution engine
    # ============================================================================
    {
        "category": "D. Workflow Completeness",
        "name": "HarnessKernel.execute() Core Execution Loop",
        "description": "Implement the core HarnessKernel.execute(spec) method that accepts an AgentSpec and returns an AgentRun with full lifecycle management.",
        "steps": [
            "Create HarnessKernel class with execute(spec: AgentSpec) -> AgentRun method",
            "Create AgentRun record with status=running at execution start",
            "Record started AgentEvent with sequence=1",
            "Build system prompt from spec.objective and spec.context",
            "Initialize Claude SDK client with configured model",
            "Configure tools based on spec.tool_policy",
            "Enter execution loop calling Claude API",
            "Record tool_call event for each tool invocation",
            "Record tool_result event for each tool response",
            "Record turn_complete event after each API turn",
            "Check max_turns budget after each turn",
            "Check timeout_seconds wall-clock limit",
            "Handle graceful termination on budget exhaustion",
            "Run AcceptanceSpec validators after execution",
            "Record acceptance_check event with results",
            "Determine final_verdict from validator results",
            "Update AgentRun with completed status and verdict",
            "Return finalized AgentRun"
        ],
        "depends_on_indices": [0, 1, 2, 4, 15]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "AgentRun Status Transition State Machine",
        "description": "Implement and enforce valid status transitions for AgentRun: pending -> running -> completed/failed/timeout.",
        "steps": [
            "Define valid state transitions as adjacency map",
            "pending can transition to running only",
            "running can transition to paused, completed, failed, timeout",
            "paused can transition to running, failed (cancel)",
            "completed, failed, timeout are terminal states",
            "Implement transition validation in AgentRun model",
            "Raise InvalidStateTransition exception for invalid transitions",
            "Log all state transitions with timestamps",
            "Verify transitions are atomic (within transaction)"
        ],
        "depends_on_indices": [2]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Max Turns Budget Enforcement",
        "description": "Enforce max_turns budget during kernel execution. Increment turns_used after each Claude API call and terminate gracefully when exhausted.",
        "steps": [
            "Initialize turns_used to 0 at run start",
            "Increment turns_used after each Claude API response",
            "Check turns_used < spec.max_turns before each turn",
            "When budget reached, set status to timeout",
            "Set error message to max_turns_exceeded",
            "Record timeout event with turns_used in payload",
            "Ensure partial work is committed before termination",
            "Verify turns_used is persisted after each turn"
        ],
        "depends_on_indices": [2, 25]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Timeout Seconds Wall-Clock Enforcement",
        "description": "Enforce timeout_seconds wall-clock limit during kernel execution using started_at timestamp comparison.",
        "steps": [
            "Record started_at timestamp at run begin",
            "Compute elapsed_seconds = now - started_at before each turn",
            "Check elapsed_seconds < spec.timeout_seconds",
            "When timeout reached, set status to timeout",
            "Set error message to timeout_exceeded",
            "Record timeout event with elapsed_seconds in payload",
            "Ensure partial work is committed before termination",
            "Handle long-running tool calls that exceed timeout"
        ],
        "depends_on_indices": [2, 25]
    },
    {
        "category": "T. Performance",
        "name": "Token Usage Tracking",
        "description": "Track input and output token usage during kernel execution for cost visibility by extracting from Claude API response.",
        "steps": [
            "Initialize tokens_in and tokens_out to 0 at run start",
            "Extract input_tokens from Claude API response usage field",
            "Extract output_tokens from Claude API response usage field",
            "Accumulate totals across all turns",
            "Update AgentRun.tokens_in and tokens_out after each turn",
            "Persist token counts even on failure/timeout",
            "Include token counts in run response"
        ],
        "depends_on_indices": [2, 25]
    },
    {
        "category": "G. State & Persistence",
        "name": "AgentEvent Recording Service",
        "description": "Implement event recording service that creates immutable AgentEvent records with sequential ordering and 4KB payload cap.",
        "steps": [
            "Create EventRecorder class with record(run_id, event_type, payload) method",
            "Maintain sequence counter per run (start at 1)",
            "Check payload size against EVENT_PAYLOAD_MAX_SIZE (4096 chars)",
            "If payload exceeds limit, create Artifact and set artifact_ref",
            "Truncate payload and set payload_truncated to original size",
            "Set timestamp to current UTC time",
            "Create AgentEvent record with all fields",
            "Commit immediately for durability",
            "Return created event ID"
        ],
        "depends_on_indices": [3, 4]
    },
    {
        "category": "G. State & Persistence",
        "name": "Artifact Storage with Content-Addressing",
        "description": "Implement artifact storage service with SHA256 content-addressing, storing small content inline and large content in files.",
        "steps": [
            "Create ArtifactStorage class with store(run_id, type, content, path) method",
            "Compute SHA256 hash of content",
            "Check content size against ARTIFACT_INLINE_MAX_SIZE (4096 bytes)",
            "If small, store in content_inline field",
            "If large, write to file: .autobuildr/artifacts/{run_id}/{hash}.blob",
            "Create parent directories if needed",
            "Set content_ref to file path",
            "Set size_bytes to content length",
            "Check for existing artifact with same hash (deduplication)",
            "Return Artifact record"
        ],
        "depends_on_indices": [3]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "test_pass Acceptance Validator",
        "description": "Implement test_pass validator that runs a shell command and checks exit code for acceptance testing.",
        "steps": [
            "Create TestPassValidator class implementing Validator interface",
            "Extract command from validator config",
            "Extract expected_exit_code (default 0)",
            "Extract timeout_seconds (default 60)",
            "Execute command via subprocess with timeout",
            "Capture stdout and stderr",
            "Compare exit code to expected",
            "Return ValidatorResult with passed boolean",
            "Include command output in result message",
            "Handle timeout as failure",
            "Handle command not found as failure"
        ],
        "depends_on_indices": [1, 25]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "file_exists Acceptance Validator",
        "description": "Implement file_exists validator that verifies a file path exists with variable interpolation support.",
        "steps": [
            "Create FileExistsValidator class implementing Validator interface",
            "Extract path from validator config",
            "Interpolate variables in path (e.g., {project_dir})",
            "Extract should_exist (default true)",
            "Check if path exists using Path.exists()",
            "Return passed = exists == should_exist",
            "Include file path in result message"
        ],
        "depends_on_indices": [1, 25]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "forbidden_patterns Acceptance Validator",
        "description": "Implement forbidden_patterns validator that ensures agent output does not contain forbidden regex patterns.",
        "steps": [
            "Create ForbiddenPatternsValidator class",
            "Extract patterns array from validator config",
            "Compile patterns as regex",
            "Query all tool_result events for the run",
            "Check each payload against all patterns",
            "If any match found, return passed = false",
            "Include matched pattern and context in result",
            "Return passed = true if no matches"
        ],
        "depends_on_indices": [1, 4, 25]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "Acceptance Gate Orchestration",
        "description": "Implement acceptance gate orchestration that runs all validators and determines final verdict based on gate_mode (all_pass, any_pass).",
        "steps": [
            "Create AcceptanceGate class with evaluate(run, acceptance_spec) method",
            "Iterate through validators array",
            "Instantiate appropriate validator class for each type",
            "Execute validator and collect ValidatorResult",
            "Check required flag - required validators must always pass",
            "For all_pass mode: verdict = passed if all passed",
            "For any_pass mode: verdict = passed if any passed",
            "Build acceptance_results array with per-validator outcomes",
            "Set AgentRun.final_verdict based on gate result",
            "Store acceptance_results JSON in AgentRun",
            "Return overall verdict"
        ],
        "depends_on_indices": [1, 32, 33, 34]
    },
    {
        "category": "K. Default & Reset",
        "name": "StaticSpecAdapter for Legacy Initializer",
        "description": "Wrap the existing initializer agent as a static AgentSpec to enable kernel execution with legacy prompts.",
        "steps": [
            "Create StaticSpecAdapter class",
            "Define create_initializer_spec() method",
            "Load initializer prompt from prompts/ directory",
            "Set objective from prompt template",
            "Set task_type to custom",
            "Configure tool_policy with feature creation tools only",
            "Set max_turns appropriate for initialization",
            "Set timeout_seconds for long spec parsing",
            "Create AcceptanceSpec with feature_count validator",
            "Return static AgentSpec"
        ],
        "depends_on_indices": [0, 1, 6]
    },
    {
        "category": "K. Default & Reset",
        "name": "StaticSpecAdapter for Legacy Coding Agent",
        "description": "Wrap the existing coding agent as a static AgentSpec with security-restricted tool_policy.",
        "steps": [
            "Define create_coding_spec(feature_id) method",
            "Load coding agent prompt from prompts/",
            "Interpolate feature details into objective",
            "Set task_type to coding",
            "Configure tool_policy with code editing tools",
            "Include allowed bash commands from security.py allowlist",
            "Set forbidden_patterns for dangerous operations",
            "Set max_turns appropriate for implementation",
            "Create AcceptanceSpec with test_pass and lint_clean validators",
            "Link source_feature_id to feature",
            "Return static AgentSpec"
        ],
        "depends_on_indices": [0, 1, 6]
    },
    {
        "category": "K. Default & Reset",
        "name": "StaticSpecAdapter for Legacy Testing Agent",
        "description": "Wrap the existing testing agent as a static AgentSpec with read-only tool_policy.",
        "steps": [
            "Define create_testing_spec(feature_id) method",
            "Load testing agent prompt from prompts/",
            "Interpolate feature steps as test criteria",
            "Set task_type to testing",
            "Configure tool_policy with test execution tools",
            "Restrict to read-only file access",
            "Set max_turns appropriate for testing",
            "Create AcceptanceSpec based on feature steps",
            "Generate test_pass validators from feature steps",
            "Link source_feature_id to feature",
            "Return static AgentSpec"
        ],
        "depends_on_indices": [0, 1, 6]
    },
    {
        "category": "K. Default & Reset",
        "name": "AUTOBUILDR_USE_KERNEL Migration Flag",
        "description": "Implement migration flag logic to choose between legacy agent execution and new HarnessKernel based on environment variable.",
        "steps": [
            "Read AUTOBUILDR_USE_KERNEL from environment",
            "Default to false for backwards compatibility",
            "When false, use existing agent execution path",
            "When true, compile Feature -> AgentSpec -> HarnessKernel",
            "Wrap kernel execution in try/except",
            "On kernel error, log warning and fallback to legacy",
            "Report which path was used in response"
        ],
        "depends_on_indices": [25, 36, 37, 38]
    },

    # ============================================================================
    # SECURITY TIER (40-49) - Tool policy enforcement
    # ============================================================================
    {
        "category": "A. Security & Access Control",
        "name": "ToolPolicy Allowed Tools Filtering",
        "description": "Implement tool filtering based on spec.tool_policy.allowed_tools whitelist.",
        "steps": [
            "Extract allowed_tools from spec.tool_policy",
            "If None or empty, allow all available tools",
            "If list provided, filter tools to only include those in list",
            "Log which tools are available to agent",
            "Verify filtered tools are valid MCP tool names",
            "Return filtered tool definitions to Claude SDK"
        ],
        "depends_on_indices": [0, 25]
    },
    {
        "category": "A. Security & Access Control",
        "name": "ToolPolicy Forbidden Patterns Enforcement",
        "description": "Validate tool arguments against forbidden_patterns regex before execution to block dangerous operations.",
        "steps": [
            "Extract forbidden_patterns from spec.tool_policy",
            "Compile patterns as regex at spec load time",
            "Before each tool call, serialize arguments to string",
            "Check arguments against all forbidden patterns",
            "If pattern matches, block tool call",
            "Record tool_call event with blocked=true and pattern matched",
            "Return error to agent explaining blocked operation",
            "Continue execution (do not abort run)"
        ],
        "depends_on_indices": [0, 25, 30]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Directory Sandbox Restriction",
        "description": "Restrict file operations to allowed_directories in tool_policy with path traversal protection.",
        "steps": [
            "Extract allowed_directories from spec.tool_policy",
            "Resolve all allowed paths to absolute paths",
            "For file operation tools, extract target path from arguments",
            "Resolve target path to absolute",
            "Check if target is under any allowed directory",
            "Block path traversal attempts (..)",
            "If target is symlink, resolve and validate final target",
            "Record violation in event log",
            "Return permission denied error to agent"
        ],
        "depends_on_indices": [0, 25, 41]
    },
    {
        "category": "N. Feedback & Notification",
        "name": "Tool Hints System Prompt Injection",
        "description": "Inject tool_hints from tool_policy into system prompt to guide agent tool usage.",
        "steps": [
            "Extract tool_hints dict from spec.tool_policy",
            "Format hints as markdown guidelines",
            "Append to system prompt in dedicated section",
            "Example: ## Tool Usage Guidelines - feature_mark_passing: Call only after verification"
        ],
        "depends_on_indices": [0, 25]
    },
    {
        "category": "G. State & Persistence",
        "name": "Policy Violation Event Logging",
        "description": "Log all tool policy violations as AgentEvents with violation type and blocked operation details.",
        "steps": [
            "Define policy_violation event type",
            "When tool blocked by allowed_tools, record event",
            "When tool blocked by forbidden_patterns, record pattern matched",
            "When file operation blocked by sandbox, record attempted path",
            "Include agent turn number in event for context",
            "Aggregate violation count in run metadata"
        ],
        "depends_on_indices": [4, 30, 40, 41, 42]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "ToolProvider Interface Definition",
        "description": "Define the ToolProvider interface for external tool sources with capability negotiation.",
        "steps": [
            "Define ToolProvider abstract base class",
            "Define list_tools() -> list[ToolDefinition] method",
            "Define execute_tool(name, args) -> ToolResult method",
            "Define get_capabilities() -> ProviderCapabilities method",
            "Define authenticate(credentials) method stub for future OAuth",
            "Create LocalToolProvider implementing interface for MCP tools",
            "Create ToolProviderRegistry for managing multiple providers"
        ],
        "depends_on_indices": [25]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Symlink Target Validation",
        "description": "When validating file paths in sandbox, resolve symlinks and validate final target is within allowed directories.",
        "steps": [
            "Check if path is symlink using Path.is_symlink()",
            "Resolve symlink to final target using Path.resolve()",
            "Validate resolved target against allowed_directories",
            "Handle broken symlinks gracefully",
            "Log symlink resolution in debug output"
        ],
        "depends_on_indices": [42]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Forbidden Tools Explicit Blocking",
        "description": "Support forbidden_tools blacklist for explicit blocking in addition to allowed_tools whitelist.",
        "steps": [
            "Extract forbidden_tools from spec.tool_policy",
            "After filtering by allowed_tools, also remove forbidden_tools",
            "Block any tool call to forbidden tool",
            "Record policy violation event",
            "Return clear error message to agent"
        ],
        "depends_on_indices": [40, 44]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Path Traversal Attack Detection",
        "description": "Detect and block path traversal attempts including .., URL-encoded sequences, and null bytes.",
        "steps": [
            "Check for .. sequences in raw path string",
            "Check for URL-encoded traversal %2e%2e",
            "Check for null bytes that could truncate paths",
            "Normalize path and compare to original",
            "Block if normalized differs (indicates traversal attempt)",
            "Log detailed violation info for security audit"
        ],
        "depends_on_indices": [42]
    },
    {
        "category": "E. Error Handling",
        "name": "Graceful Budget Exhaustion Handling",
        "description": "When max_turns or timeout is reached, handle gracefully by saving partial work and running validators on partial results.",
        "steps": [
            "Detect budget exhaustion before next turn",
            "Set status to timeout (not failed)",
            "Record timeout event with resource that was exhausted",
            "Commit any uncommitted database changes",
            "Run acceptance validators on partial state",
            "Store partial acceptance_results",
            "Determine verdict based on partial results",
            "Return AgentRun with timeout status and partial results"
        ],
        "depends_on_indices": [27, 28, 35]
    },

    # ============================================================================
    # DSPY SPECBUILDER TIER (50-59)
    # ============================================================================
    {
        "category": "F. UI-Backend Integration",
        "name": "DSPy SpecGenerationSignature Definition",
        "description": "Define DSPy signature for task -> AgentSpec compilation with chain-of-thought reasoning.",
        "steps": [
            "Import dspy library",
            "Define SpecGenerationSignature(dspy.Signature)",
            "Define input fields: task_description, task_type, project_context",
            "Define output fields: objective, context_json, tool_policy_json, max_turns, timeout_seconds, validators_json",
            "Add docstring with field descriptions",
            "Add chain-of-thought reasoning field"
        ],
        "depends_on_indices": [6, 7]
    },
    {
        "category": "G. State & Persistence",
        "name": "Skill Template Registry",
        "description": "Implement template registry that loads skill templates from prompts/ directory with interpolation support.",
        "steps": [
            "Create TemplateRegistry class",
            "Scan prompts/ directory for template files",
            "Parse template metadata (task_type, required_tools, etc.)",
            "Index templates by task_type",
            "Implement get_template(task_type) -> Template",
            "Implement interpolate(template, variables) -> str",
            "Cache compiled templates for performance",
            "Handle missing template gracefully with fallback"
        ],
        "depends_on_indices": [6]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "Feature to AgentSpec Compiler",
        "description": "Convert a Feature database record into an AgentSpec with derived tool_policy and acceptance validators.",
        "steps": [
            "Create FeatureCompiler class with compile(feature) -> AgentSpec method",
            "Generate spec name from feature: feature-{id}-{slug}",
            "Generate display_name from feature name",
            "Set objective from feature description",
            "Determine task_type from feature category",
            "Derive tool_policy based on category conventions",
            "Create acceptance validators from feature steps",
            "Set source_feature_id for traceability",
            "Set priority from feature priority",
            "Return complete AgentSpec ready for execution"
        ],
        "depends_on_indices": [0, 1, 6, 7, 50, 51]
    },
    {
        "category": "N. Feedback & Notification",
        "name": "Display Name and Icon Derivation",
        "description": "Derive display_name and icon from AgentSpec objective and task_type for human-friendly presentation.",
        "steps": [
            "Extract first sentence of objective as display_name base",
            "Truncate to max 100 chars with ellipsis if needed",
            "Map task_type to icon: coding->hammer, testing->flask, etc.",
            "Allow icon override in spec context",
            "Select mascot name from existing pool if needed"
        ],
        "depends_on_indices": [6]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "DSPy Module Execution for Spec Generation",
        "description": "Execute DSPy module to generate AgentSpec from task description with output validation.",
        "steps": [
            "Create SpecBuilder class wrapping DSPy module",
            "Initialize DSPy with Claude backend",
            "Implement build(task_desc, task_type, context) method",
            "Execute DSPy signature with inputs",
            "Parse JSON output fields",
            "Validate tool_policy structure",
            "Validate validators structure",
            "Create AgentSpec and AcceptanceSpec from output",
            "Handle DSPy execution errors gracefully"
        ],
        "depends_on_indices": [50, 51, 52]
    },
    {
        "category": "D. Workflow Completeness",
        "name": "Validator Generation from Feature Steps",
        "description": "Generate AcceptanceSpec validators from feature verification steps by parsing step text.",
        "steps": [
            "Analyze each feature step for validator hints",
            "If step contains run/execute, create test_pass validator",
            "If step mentions file/path, create file_exists validator",
            "If step mentions should not/must not, create forbidden_patterns",
            "Extract command or path from step text",
            "Set appropriate timeout for test_pass validators",
            "Return array of validator configs"
        ],
        "depends_on_indices": [1, 7, 52]
    },
    {
        "category": "L. Search & Filter Edge Cases",
        "name": "Task Type Detection from Description",
        "description": "Detect appropriate task_type from task description text using keyword matching heuristics.",
        "steps": [
            "Define keyword sets for each task_type",
            "coding: implement, create, build, add feature",
            "testing: test, verify, check, validate",
            "refactoring: refactor, clean up, optimize, simplify",
            "documentation: document, readme, comments",
            "audit: review, security, vulnerability",
            "Score description against each keyword set",
            "Return highest scoring task_type",
            "Default to custom if no clear match"
        ],
        "depends_on_indices": [50]
    },
    {
        "category": "A. Security & Access Control",
        "name": "Tool Policy Derivation from Task Type",
        "description": "Derive appropriate tool_policy based on task_type with standard tool sets and forbidden patterns.",
        "steps": [
            "Define tool sets for each task_type",
            "coding: file edit, bash (restricted), feature tools",
            "testing: file read, bash (test commands), feature tools",
            "documentation: file write, read-only access",
            "audit: read-only everything",
            "Add standard forbidden_patterns for all types",
            "Add task-specific forbidden_patterns",
            "Return complete tool_policy structure"
        ],
        "depends_on_indices": [0, 6, 56]
    },
    {
        "category": "T. Performance",
        "name": "Budget Derivation from Task Complexity",
        "description": "Derive appropriate max_turns and timeout_seconds based on task complexity estimation.",
        "steps": [
            "Define base budgets per task_type",
            "coding: max_turns=50, timeout=1800",
            "testing: max_turns=30, timeout=600",
            "Adjust based on description length",
            "Adjust based on number of acceptance steps",
            "Apply minimum and maximum bounds",
            "Return budget dict with max_turns and timeout_seconds"
        ],
        "depends_on_indices": [6, 56]
    },
    {
        "category": "M. Form Validation",
        "name": "Unique Spec Name Generation",
        "description": "Generate unique, URL-safe spec names from objectives with collision handling.",
        "steps": [
            "Extract keywords from objective",
            "Generate slug from keywords",
            "Prepend task_type prefix",
            "Add timestamp or sequence for uniqueness",
            "Validate against existing spec names",
            "If collision, append numeric suffix",
            "Limit to 100 chars",
            "Return unique spec name"
        ],
        "depends_on_indices": [0, 6]
    },

    # ============================================================================
    # UI WEBSOCKET TIER (60-64)
    # ============================================================================
    {
        "category": "F. UI-Backend Integration",
        "name": "WebSocket agent_spec_created Event",
        "description": "Broadcast WebSocket message when new AgentSpec is registered for UI card creation.",
        "steps": [
            "After AgentSpec creation, publish WebSocket message",
            "Message type: agent_spec_created",
            "Payload includes: spec_id, name, display_name, icon, task_type",
            "Broadcast to all connected clients",
            "Handle WebSocket errors gracefully"
        ],
        "depends_on_indices": [10]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "WebSocket agent_run_started Event",
        "description": "Broadcast WebSocket message when AgentRun begins for real-time UI updates.",
        "steps": [
            "When AgentRun status changes to running, publish message",
            "Message type: agent_run_started",
            "Payload: run_id, spec_id, display_name, icon, started_at",
            "Broadcast to all connected clients"
        ],
        "depends_on_indices": [15, 60]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "WebSocket agent_event_logged Event",
        "description": "Broadcast WebSocket message for significant events to enable real-time progress tracking.",
        "steps": [
            "Filter events to only broadcast significant types",
            "tool_call, turn_complete, acceptance_check",
            "Message type: agent_event_logged",
            "Payload: run_id, event_type, sequence, tool_name (if applicable)",
            "Throttle to max 10 events/second per run"
        ],
        "depends_on_indices": [30, 61]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "WebSocket agent_acceptance_update Event",
        "description": "Broadcast WebSocket message when validators run with per-validator results.",
        "steps": [
            "After acceptance gate evaluation, publish message",
            "Message type: agent_acceptance_update",
            "Payload: run_id, final_verdict, validator_results array",
            "Each validator result: index, type, passed, message"
        ],
        "depends_on_indices": [35, 62]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "DynamicAgentCard React Component",
        "description": "Create DynamicAgentCard component rendering from AgentSpec + AgentRun data with status and progress display.",
        "steps": [
            "Create DynamicAgentCard.tsx component",
            "Props: spec (AgentSpec), run (AgentRun | null)",
            "Display spec.display_name as card title",
            "Display spec.icon as card icon",
            "If run exists, show status with color coding",
            "Show turns_used / max_turns progress bar",
            "Show validator status indicators",
            "Add click handler to open Run Inspector",
            "Style with Tailwind neobrutalism tokens",
            "Make responsive for mobile"
        ],
        "depends_on_indices": [11, 17]
    },

    # ============================================================================
    # UI COMPONENTS TIER (65-74)
    # ============================================================================
    {
        "category": "O. Responsive & Layout",
        "name": "AgentRun Status Color Coding",
        "description": "Define and apply color coding for AgentRun status with accessibility considerations.",
        "steps": [
            "Define status color map in design tokens",
            "pending: text-gray-500, bg-gray-100",
            "running: text-blue-500, bg-blue-100 with pulse animation",
            "paused: text-yellow-500, bg-yellow-100",
            "completed: text-green-500, bg-green-100",
            "failed: text-red-500, bg-red-100",
            "timeout: text-orange-500, bg-orange-100",
            "Apply to status badge in DynamicAgentCard",
            "Apply to progress bar fill color"
        ],
        "depends_on_indices": [64]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Turns Progress Bar Component",
        "description": "Create reusable progress bar component showing turns_used / max_turns with animation.",
        "steps": [
            "Create TurnsProgressBar.tsx component",
            "Props: used (number), max (number)",
            "Calculate percentage = (used / max) * 100",
            "Cap at 100% for display",
            "Animate width transition on update",
            "Show tooltip with exact values on hover",
            "Use status-appropriate color",
            "Handle max=0 edge case"
        ],
        "depends_on_indices": [64]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Run Inspector Slide-Out Panel",
        "description": "Create Run Inspector slide-out panel with event timeline, artifacts, and acceptance results tabs.",
        "steps": [
            "Create RunInspector.tsx component",
            "Props: runId (string), onClose (function)",
            "Fetch run details via GET /api/agent-runs/:id",
            "Slide in from right with animation",
            "Show run header with spec info and status",
            "Tabs for Timeline, Artifacts, Acceptance",
            "Close on Escape key or overlay click",
            "Responsive width for mobile"
        ],
        "depends_on_indices": [17, 18, 19, 64]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Event Timeline Component",
        "description": "Create Event Timeline component with vertical timeline, expandable event details, and type filtering.",
        "steps": [
            "Create EventTimeline.tsx component",
            "Props: runId (string)",
            "Fetch events via GET /api/agent-runs/:id/events",
            "Render as vertical timeline with timestamps",
            "Different icons for event types",
            "Expandable cards for payload details",
            "Add filter dropdown by event_type",
            "Load more button for pagination",
            "Auto-scroll to latest on update"
        ],
        "depends_on_indices": [18, 67]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Artifact List Component",
        "description": "Create Artifact List component with type filtering, preview, and download functionality.",
        "steps": [
            "Create ArtifactList.tsx component",
            "Props: runId (string)",
            "Fetch artifacts via GET /api/agent-runs/:id/artifacts",
            "Filter dropdown by artifact_type",
            "Show artifact metadata: type, path, size",
            "Preview button for inline content",
            "Download button linking to /api/artifacts/:id/content",
            "Handle empty state gracefully"
        ],
        "depends_on_indices": [19, 20, 67]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Acceptance Results Display Component",
        "description": "Create component displaying acceptance gate results with per-validator pass/fail indicators.",
        "steps": [
            "Create AcceptanceResults.tsx component",
            "Props: acceptanceResults (array), verdict (string)",
            "Display overall verdict with color and icon",
            "List each validator with name and pass/fail badge",
            "Show validator message on expand",
            "Highlight required validators",
            "Show retry count if > 0"
        ],
        "depends_on_indices": [17, 67]
    },
    {
        "category": "F. UI-Backend Integration",
        "name": "Real-time Card Updates via WebSocket",
        "description": "Connect DynamicAgentCard to WebSocket for real-time status, progress, and event updates.",
        "steps": [
            "Create useAgentRunUpdates hook",
            "Subscribe to run-specific WebSocket channel",
            "Handle agent_run_started message",
            "Handle agent_event_logged message to update turns_used",
            "Handle agent_acceptance_update message",
            "Update component state on message",
            "Unsubscribe on unmount",
            "Handle reconnection gracefully"
        ],
        "depends_on_indices": [61, 62, 63, 64]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Agent Thinking State Animation",
        "description": "Add animated thinking indicator to DynamicAgentCard showing current activity state.",
        "steps": [
            "Define thinking states: thinking, coding, testing, validating",
            "Add animated indicator to card header",
            "Pulse animation while waiting for response",
            "Update state based on latest event type",
            "tool_call -> working",
            "turn_complete -> thinking",
            "acceptance_check -> validating"
        ],
        "depends_on_indices": [64, 71]
    },
    {
        "category": "E. Error Handling",
        "name": "Error Display in Agent Card",
        "description": "Display error information in DynamicAgentCard when run fails with link to full details.",
        "steps": [
            "Check run.status === failed or timeout",
            "Display error icon in card",
            "Show truncated error message (first 100 chars)",
            "Add View Details link to open inspector",
            "Style with error colors"
        ],
        "depends_on_indices": [64, 67]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Validator Type Icons",
        "description": "Define and display icons for different validator types in acceptance results.",
        "steps": [
            "Define icon map for validator types",
            "test_pass: terminal icon",
            "file_exists: file icon",
            "lint_clean: code icon",
            "forbidden_patterns: shield icon",
            "custom: gear icon",
            "Use in AcceptanceResults component",
            "Use in validator status indicators on card"
        ],
        "depends_on_indices": [70]
    },

    # ============================================================================
    # ERROR HANDLING & ROBUSTNESS TIER (75-79)
    # ============================================================================
    {
        "category": "E. Error Handling",
        "name": "Standardized API Error Responses",
        "description": "Implement consistent error response format across all API endpoints with proper HTTP status codes.",
        "steps": [
            "Define ErrorResponse Pydantic model",
            "Fields: error_code (string), message (string), details (dict optional)",
            "Create exception handlers for common errors",
            "ValidationError -> 422 with field details",
            "NotFoundError -> 404",
            "ConflictError -> 409",
            "DatabaseError -> 500",
            "Apply handlers globally via FastAPI exception_handler"
        ],
        "depends_on_indices": [10, 11, 12, 13]
    },
    {
        "category": "E. Error Handling",
        "name": "HarnessKernel Error Recovery",
        "description": "Implement error recovery in HarnessKernel with retry logic and graceful failure handling.",
        "steps": [
            "Wrap Claude API calls in try/except",
            "Catch RateLimitError and retry with backoff",
            "Catch APIError and record in run.error",
            "Catch tool execution exceptions",
            "Record failed event with error details",
            "Check retry_policy and max_retries",
            "If retries available, increment retry_count and retry",
            "If no retries, set status to failed and finalize"
        ],
        "depends_on_indices": [25, 26]
    },
    {
        "category": "R. Concurrency & Race Conditions",
        "name": "Database Transaction Safety",
        "description": "Ensure database operations in kernel are transaction-safe with proper locking.",
        "steps": [
            "Use SQLAlchemy session per-run",
            "Commit after each event record for durability",
            "Handle IntegrityError from concurrent inserts",
            "Use SELECT FOR UPDATE when modifying run status",
            "Rollback on exception and record error",
            "Close session in finally block"
        ],
        "depends_on_indices": [25, 30]
    },
    {
        "category": "E. Error Handling",
        "name": "Invalid AgentSpec Graceful Handling",
        "description": "Handle invalid or malformed AgentSpecs gracefully with clear validation error responses.",
        "steps": [
            "Validate AgentSpec before kernel execution",
            "Check required fields are present",
            "Validate tool_policy structure",
            "Validate budget values within constraints",
            "If invalid, return error without creating run",
            "Include validation error details in response"
        ],
        "depends_on_indices": [6, 25]
    },
    {
        "category": "J. Data Cleanup & Cascade",
        "name": "Orphaned Run Cleanup on Startup",
        "description": "On server startup, clean up orphaned runs stuck in running/pending status.",
        "steps": [
            "On startup, query runs where status in (running, pending)",
            "Check if run started_at is older than max timeout",
            "For stale runs, set status to failed",
            "Set error to orphaned_on_restart",
            "Record failed event",
            "Log cleanup actions"
        ],
        "depends_on_indices": [2, 26]
    },

    # ============================================================================
    # ACCESSIBILITY & RESPONSIVE TIER (80-84)
    # ============================================================================
    {
        "category": "P. Accessibility",
        "name": "Keyboard Navigation for Agent Cards",
        "description": "Implement keyboard navigation for DynamicAgentCard grid with focus management.",
        "steps": [
            "Add tabindex to DynamicAgentCard",
            "Handle Enter/Space to open inspector",
            "Handle Escape to close inspector",
            "Arrow keys to navigate card grid",
            "Focus visible indicator",
            "Screen reader announcements for status changes"
        ],
        "depends_on_indices": [64, 67]
    },
    {
        "category": "P. Accessibility",
        "name": "ARIA Labels for Dynamic Components",
        "description": "Add appropriate ARIA labels and roles for screen reader compatibility.",
        "steps": [
            "Add role=button to clickable cards",
            "Add aria-label with spec name and status",
            "Add aria-live=polite to status updates",
            "Add aria-describedby for progress bar",
            "Label inspector close button",
            "Add aria-expanded for expandable events"
        ],
        "depends_on_indices": [64, 67, 68]
    },
    {
        "category": "O. Responsive & Layout",
        "name": "Mobile Responsive Agent Card Grid",
        "description": "Make DynamicAgentCard grid responsive for mobile with stacked layout and touch targets.",
        "steps": [
            "Use Tailwind responsive breakpoints",
            "Desktop: 3-4 cards per row",
            "Tablet: 2 cards per row",
            "Mobile: 1 card per row stacked",
            "Inspector full-width on mobile",
            "Touch-friendly tap targets (min 44px)",
            "Test on various screen sizes"
        ],
        "depends_on_indices": [64, 67]
    },
    {
        "category": "P. Accessibility",
        "name": "High Contrast Mode Support",
        "description": "Support high contrast mode with WCAG-compliant colors and fallback indicators.",
        "steps": [
            "Check all status colors against WCAG contrast requirements",
            "Add pattern/icon fallbacks in addition to color",
            "Test with Windows High Contrast mode",
            "Add prefers-contrast media query support",
            "Ensure focus indicators are visible"
        ],
        "depends_on_indices": [65, 64]
    },
    {
        "category": "N. Feedback & Notification",
        "name": "Loading State Indicators",
        "description": "Add loading state indicators throughout UI with skeleton loaders and optimistic updates.",
        "steps": [
            "Create skeleton loader for DynamicAgentCard",
            "Show skeleton while fetching spec/run data",
            "Add spinner to action buttons (pause, cancel)",
            "Optimistic update on action, revert on error",
            "Loading indicator in Run Inspector",
            "Loading state for event timeline pagination"
        ],
        "depends_on_indices": [64, 67, 68]
    }
]

def main():
    """Create all features in the database."""
    session = SessionLocal()

    try:
        # Check if features already exist
        existing_count = session.query(Feature).count()
        if existing_count > 0:
            print(f"Database already has {existing_count} features. Skipping creation.")
            return

        # Get the starting priority
        max_priority_result = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
        start_priority = (max_priority_result[0] + 1) if max_priority_result else 1

        # Create all features
        created_features = []
        for i, feature_data in enumerate(FEATURES):
            db_feature = Feature(
                priority=start_priority + i,
                category=feature_data["category"],
                name=feature_data["name"],
                description=feature_data["description"],
                steps=feature_data["steps"],
                passes=False,
                in_progress=False,
            )
            session.add(db_feature)
            created_features.append(db_feature)

        # Flush to get IDs assigned
        session.flush()

        # Resolve index-based dependencies to actual IDs
        deps_count = 0
        for i, feature_data in enumerate(FEATURES):
            indices = feature_data.get("depends_on_indices", [])
            if indices:
                dep_ids = [created_features[idx].id for idx in indices]
                created_features[i].dependencies = sorted(dep_ids)
                deps_count += 1

        session.commit()

        print(f"Successfully created {len(created_features)} features")
        print(f"Features with dependencies: {deps_count}")

        # Print category distribution
        categories = {}
        for f in FEATURES:
            cat = f["category"]
            categories[cat] = categories.get(cat, 0) + 1

        print("\nCategory Distribution:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")

    except Exception as e:
        session.rollback()
        print(f"Error creating features: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
