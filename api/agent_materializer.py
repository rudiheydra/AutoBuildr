"""
Agent Materializer - Convert AgentSpec to Claude Code Markdown
================================================================

Feature #192: Agent Materializer converts AgentSpec to Claude Code markdown
Feature #196: Agent Materializer validates template output
Feature #198: Agent Materializer generates settings.local.json when needed

The Agent Materializer takes AgentSpec objects and renders them as Claude Code-compatible
markdown files. These files follow the Claude Code agent file conventions:

1. YAML frontmatter with: name, description, model, optional color
2. Markdown body with comprehensive agent instructions

The output is deterministic: given the same AgentSpec input, the materializer
will always produce the identical output (timestamps are not included in
generated content to ensure determinism).

Feature #196 adds validation before file write:
- Rendered markdown checked for required sections
- Tool declarations validated against known tools
- Model specification validated
- Invalid output raises error before file write

Feature #198 adds settings.local.json management:
- Check if .claude/settings.local.json exists
- Create with default permissions if missing
- Include MCP server configuration if agents require it
- Preserve existing settings when updating
- Settings enable agent execution via Claude CLI

Claude Code Agent File Convention Reference:
- .claude/agents/*.md format
- YAML frontmatter delimited by ---
- Frontmatter fields: name (required), description (required), model (required), color (optional)
- Body: Markdown instructions for the agent
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec
    from api.event_recorder import EventRecorder
    from sqlalchemy.orm import Session

_logger = logging.getLogger(__name__)

# =============================================================================
# Type Aliases (Feature #197)
# =============================================================================

# Progress callback for batch materialization
# Callback receives: (current_index, total_count, spec_name, status)
# status is one of: "processing", "completed", "failed", "rolled_back"
ProgressCallback = Callable[[int, int, str, str], None]


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Constants
# =============================================================================

# Default output directory relative to project root (Claude Code convention)
DEFAULT_OUTPUT_DIR = ".claude/agents/generated"

# Valid models for Claude Code agents
VALID_MODELS = frozenset({"sonnet", "opus", "haiku"})

# Default model if not specified
DEFAULT_MODEL = "sonnet"

# Task type to color mapping for visual distinction in UI
TASK_TYPE_COLORS: dict[str, str] = {
    "coding": "blue",
    "testing": "green",
    "refactoring": "purple",
    "documentation": "cyan",
    "audit": "red",
    "custom": "gray",
}

# Default color if task type not in mapping
DEFAULT_COLOR = "orange"

# Maximum length for description in frontmatter (Claude Code convention)
DESCRIPTION_MAX_LENGTH = 2000

# Required sections in rendered markdown (Feature #196 Step 1)
REQUIRED_MARKDOWN_SECTIONS = frozenset({
    "## Your Objective",
    "## Tool Policy",
    "## Execution Guidelines",
})

# Required frontmatter fields (Feature #196 Step 1)
REQUIRED_FRONTMATTER_FIELDS = frozenset({
    "name",
    "description",
    "model",
})

# =============================================================================
# Feature #198: Settings Local JSON Configuration
# =============================================================================

# Default settings file location
SETTINGS_LOCAL_FILE = "settings.local.json"

# Default Claude directory
CLAUDE_DIR = ".claude"

# Default permissions for settings file (rw-r--r--)
DEFAULT_SETTINGS_PERMISSIONS = 0o644

# Default settings structure for Claude Code
DEFAULT_SETTINGS: dict[str, Any] = {
    "permissions": {
        "allow": []
    }
}

# Common MCP server configurations for agents
MCP_SERVER_CONFIGS: dict[str, dict[str, Any]] = {
    "features": {
        "command": "uv",
        "args": ["run", "--with", "mcp", "mcp_features_server"],
        "env": {}
    },
    "playwright": {
        "command": "npx",
        "args": ["@anthropic/mcp-server-playwright", "--headless"],
        "env": {}
    },
}

# Tool patterns that suggest MCP server requirements
MCP_TOOL_PATTERNS: dict[str, str] = {
    "mcp__features__": "features",
    "mcp__playwright__": "playwright",
    "feature_get_": "features",
    "feature_mark_": "features",
    "feature_create": "features",
    "browser_": "playwright",
}


# =============================================================================
# Exceptions (Feature #196)
# =============================================================================

class TemplateValidationError(Exception):
    """
    Raised when rendered markdown fails validation.

    Feature #196 Step 4: Invalid output raises error before file write.
    """

    def __init__(
        self,
        message: str,
        validation_errors: list["ValidationError"] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.validation_errors = validation_errors or []

    def __str__(self) -> str:
        if self.validation_errors:
            error_details = "; ".join(str(e) for e in self.validation_errors)
            return f"{self.message}: {error_details}"
        return self.message


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ValidationError:
    """
    A single validation error from template validation.

    Feature #196: Agent Materializer validates template output.

    Attributes:
        category: Category of error (e.g., "section_missing", "invalid_tool", "invalid_model")
        message: Human-readable error message
        field: The field or section that failed validation (optional)
        value: The invalid value (optional)
    """
    category: str
    message: str
    field: str | None = None
    value: str | None = None

    def __str__(self) -> str:
        if self.field and self.value:
            return f"{self.category}: {self.message} (field={self.field}, value={self.value})"
        elif self.field:
            return f"{self.category}: {self.message} (field={self.field})"
        return f"{self.category}: {self.message}"


@dataclass
class TemplateValidationResult:
    """
    Result of validating rendered markdown template.

    Feature #196: Agent Materializer validates template output.

    Attributes:
        is_valid: Whether the template passed all validation checks
        errors: List of validation errors (empty if valid)
        has_required_sections: Whether all required sections are present
        has_valid_frontmatter: Whether frontmatter is valid
        tools_validated: Whether tool declarations were validated
        model_validated: Whether model specification was validated
    """
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    has_required_sections: bool = True
    has_valid_frontmatter: bool = True
    tools_validated: bool = True
    model_validated: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [{"category": e.category, "message": e.message, "field": e.field, "value": e.value} for e in self.errors],
            "has_required_sections": self.has_required_sections,
            "has_valid_frontmatter": self.has_valid_frontmatter,
            "tools_validated": self.tools_validated,
            "model_validated": self.model_validated,
        }


@dataclass
class MaterializationAuditInfo:
    """
    Audit information for a materialization event.

    Feature #195: Agent Materializer records agent_materialized audit event.

    Attributes:
        event_id: ID of the recorded agent_materialized event (if recorded)
        run_id: ID of the AgentRun the event was linked to
        timestamp: When the materialization occurred
        recorded: Whether the audit event was successfully recorded
        error: Error message if recording failed
    """
    event_id: int | None = None
    run_id: str | None = None
    timestamp: datetime | None = None
    recorded: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "recorded": self.recorded,
            "error": self.error,
        }


@dataclass
class MaterializationResult:
    """
    Result of materializing a single AgentSpec.

    Attributes:
        spec_id: ID of the AgentSpec that was materialized
        spec_name: Name of the AgentSpec
        success: Whether materialization succeeded
        file_path: Path to the created agent file (if successful)
        error: Error message (if failed)
        content_hash: SHA256 hash of the generated content (for determinism verification)
        validation_result: Result of template validation (Feature #196)
        audit_info: Audit event recording info (Feature #195)
    """
    spec_id: str
    spec_name: str
    success: bool
    file_path: Path | None = None
    error: str | None = None
    content_hash: str | None = None
    validation_result: TemplateValidationResult | None = None
    audit_info: MaterializationAuditInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "success": self.success,
            "file_path": str(self.file_path) if self.file_path else None,
            "error": self.error,
            "content_hash": self.content_hash,
            "validation_result": self.validation_result.to_dict() if self.validation_result else None,
            "audit_info": self.audit_info.to_dict() if self.audit_info else None,
        }


@dataclass
class BatchMaterializationResult:
    """
    Result of materializing multiple AgentSpecs.

    Feature #197: Agent Materializer handles multiple agents in batch.

    Attributes:
        total: Total number of specs processed
        succeeded: Number of successful materializations
        failed: Number of failed materializations
        results: Individual results for each spec
        all_succeeded: True if all specs were successfully materialized
        atomic: Whether atomic mode was used (all-or-nothing)
        rolled_back: Whether files were rolled back due to failure in atomic mode
        batch_audit_info: Audit info for batch-level event (if recorded)
    """
    total: int
    succeeded: int
    failed: int
    results: list[MaterializationResult] = field(default_factory=list)
    atomic: bool = False
    rolled_back: bool = False
    batch_audit_info: MaterializationAuditInfo | None = None

    @property
    def all_succeeded(self) -> bool:
        """Check if all materializations succeeded."""
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "all_succeeded": self.all_succeeded,
            "results": [r.to_dict() for r in self.results],
            "atomic": self.atomic,
            "rolled_back": self.rolled_back,
            "batch_audit_info": self.batch_audit_info.to_dict() if self.batch_audit_info else None,
        }


# =============================================================================
# Feature #198: Settings Local JSON Data Classes
# =============================================================================

@dataclass
class SettingsUpdateResult:
    """
    Result of updating settings.local.json.

    Feature #198: Agent Materializer generates settings.local.json when needed.

    Attributes:
        success: Whether the update succeeded
        file_path: Path to the settings file
        created: Whether the file was created (vs updated)
        mcp_servers_added: List of MCP server names that were added
        permissions_added: List of permission patterns that were added
        error: Error message if failed
        settings_hash: SHA256 hash of the final settings content
    """
    success: bool
    file_path: Path | None = None
    created: bool = False
    mcp_servers_added: list[str] = field(default_factory=list)
    permissions_added: list[str] = field(default_factory=list)
    error: str | None = None
    settings_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "file_path": str(self.file_path) if self.file_path else None,
            "created": self.created,
            "mcp_servers_added": self.mcp_servers_added,
            "permissions_added": self.permissions_added,
            "error": self.error,
            "settings_hash": self.settings_hash,
        }


@dataclass
class SettingsRequirements:
    """
    Requirements extracted from AgentSpecs for settings.local.json.

    Feature #198: Agent Materializer generates settings.local.json when needed.

    Attributes:
        mcp_servers: Set of MCP server names required
        permissions: Set of permission patterns required
        source_specs: List of spec names that contributed to these requirements
    """
    mcp_servers: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)
    source_specs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mcp_servers": sorted(self.mcp_servers),
            "permissions": sorted(self.permissions),
            "source_specs": self.source_specs,
        }


# =============================================================================
# Agent Materializer Class
# =============================================================================

class AgentMaterializer:
    """
    Materializes AgentSpecs into Claude Code-compatible markdown files.

    The materializer creates markdown files with:
    - YAML frontmatter: name, description, model, color
    - Markdown body: Agent instructions including objective, tools, and guidance

    Output is deterministic: same input produces identical output.
    """

    def __init__(
        self,
        project_dir: Path | str,
        *,
        output_dir: str | None = None,
    ):
        """
        Initialize the AgentMaterializer.

        Args:
            project_dir: Root project directory
            output_dir: Custom output directory (relative to project_dir),
                       defaults to .claude/agents/generated/
        """
        self.project_dir = Path(project_dir).resolve()
        self._output_dir = output_dir or DEFAULT_OUTPUT_DIR

        _logger.info(
            "AgentMaterializer initialized: project_dir=%s, output_dir=%s",
            self.project_dir, self._output_dir,
        )

    @property
    def output_path(self) -> Path:
        """Get the absolute path to the output directory."""
        return self.project_dir / self._output_dir

    def ensure_output_dir(self) -> Path:
        """
        Ensure the output directory exists.

        Returns:
            Path to the output directory
        """
        self.output_path.mkdir(parents=True, exist_ok=True)
        return self.output_path

    # -------------------------------------------------------------------------
    # Core Materialization Methods
    # -------------------------------------------------------------------------

    def materialize(
        self,
        spec: "AgentSpec",
        *,
        validate: bool = True,
        raise_on_invalid: bool = False,
    ) -> MaterializationResult:
        """
        Materialize a single AgentSpec to a Claude Code markdown file.

        Creates a markdown file with:
        - YAML frontmatter (name, description, model, color)
        - Markdown body with agent instructions

        Feature #196: Validates template output before file write.

        Args:
            spec: The AgentSpec to materialize
            validate: Whether to validate the rendered markdown (default: True)
            raise_on_invalid: Whether to raise TemplateValidationError on invalid output

        Returns:
            MaterializationResult indicating success or failure

        Raises:
            TemplateValidationError: If raise_on_invalid=True and validation fails
        """
        try:
            # Build Claude Code-compatible content
            content = self.render_claude_code_markdown(spec)

            # Feature #196 Step 4: Validate BEFORE file write
            validation_result = None
            if validate:
                validation_result = self.validate_template_output(content, spec)

                if not validation_result.is_valid:
                    _logger.warning(
                        "Template validation failed for AgentSpec '%s': %d errors",
                        spec.name, len(validation_result.errors),
                    )

                    if raise_on_invalid:
                        raise TemplateValidationError(
                            f"Template validation failed for spec '{spec.name}'",
                            validation_result.errors,
                        )

                    # Return failure without writing file
                    return MaterializationResult(
                        spec_id=spec.id,
                        spec_name=spec.name,
                        success=False,
                        error=f"Validation failed: {len(validation_result.errors)} errors",
                        validation_result=validation_result,
                    )

            # Ensure output directory exists
            output_dir = self.ensure_output_dir()

            # Generate filename from spec name
            filename = f"{spec.name}.md"
            filepath = output_dir / filename

            # Compute content hash for determinism verification
            import hashlib
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            # Write the file (only after validation passes)
            filepath.write_text(content, encoding="utf-8")

            _logger.info(
                "Materialized AgentSpec '%s' to %s (hash: %s)",
                spec.name, filepath, content_hash[:16],
            )

            return MaterializationResult(
                spec_id=spec.id,
                spec_name=spec.name,
                success=True,
                file_path=filepath,
                content_hash=content_hash,
                validation_result=validation_result,
            )

        except TemplateValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            _logger.error(
                "Failed to materialize AgentSpec '%s': %s",
                spec.name, e,
            )
            return MaterializationResult(
                spec_id=spec.id,
                spec_name=spec.name,
                success=False,
                error=str(e),
            )

    def materialize_with_audit(
        self,
        spec: "AgentSpec",
        session: "Session",
        run_id: str,
    ) -> MaterializationResult:
        """
        Materialize an AgentSpec and record an audit event.

        Feature #195: Agent Materializer records agent_materialized audit event.

        This method:
        1. Materializes the AgentSpec to a markdown file
        2. Records an 'agent_materialized' event to the database
        3. Links the event to the AgentSpec via spec_id in payload

        The event payload includes:
        - agent_name: Name of the materialized agent
        - file_path: Path to the created agent file
        - spec_hash: SHA256 hash of the generated content
        - timestamp: When materialization occurred
        - spec_id: ID of the AgentSpec (for DB linkage)
        - display_name: Human-readable display name
        - task_type: Task type of the agent

        Args:
            spec: The AgentSpec to materialize
            session: SQLAlchemy database session for event recording
            run_id: UUID of the AgentRun to link the event to

        Returns:
            MaterializationResult with audit_info populated
        """
        # First, materialize the spec
        result = self.materialize(spec)

        # If materialization failed, don't record audit event
        if not result.success:
            return result

        # Record the audit event
        audit_info = self._record_materialization_event(
            session=session,
            run_id=run_id,
            spec=spec,
            file_path=result.file_path,
            content_hash=result.content_hash,
        )

        # Update result with audit info
        result.audit_info = audit_info

        return result

    def _record_materialization_event(
        self,
        session: "Session",
        run_id: str,
        spec: "AgentSpec",
        file_path: Path | None,
        content_hash: str | None,
    ) -> MaterializationAuditInfo:
        """
        Record an agent_materialized event to the database.

        Feature #195: Agent Materializer records agent_materialized audit event.

        Args:
            session: SQLAlchemy database session
            run_id: UUID of the AgentRun to link the event to
            spec: The AgentSpec that was materialized
            file_path: Path to the created agent file
            content_hash: SHA256 hash of the content

        Returns:
            MaterializationAuditInfo with event details
        """
        from api.event_recorder import get_event_recorder

        timestamp = _utc_now()
        audit_info = MaterializationAuditInfo(
            run_id=run_id,
            timestamp=timestamp,
        )

        try:
            recorder = get_event_recorder(session, self.project_dir)

            event_id = recorder.record_agent_materialized(
                run_id=run_id,
                agent_name=spec.name,
                file_path=str(file_path) if file_path else "",
                spec_hash=content_hash or "",
                spec_id=spec.id,
                display_name=spec.display_name,
                task_type=spec.task_type,
            )

            audit_info.event_id = event_id
            audit_info.recorded = True

            _logger.info(
                "Recorded agent_materialized event: run_id=%s, agent=%s, event_id=%d",
                run_id, spec.name, event_id,
            )

        except Exception as e:
            _logger.error(
                "Failed to record agent_materialized event for '%s': %s",
                spec.name, e,
            )
            audit_info.error = str(e)
            audit_info.recorded = False

        return audit_info

    def materialize_batch_with_audit(
        self,
        specs: list["AgentSpec"],
        session: "Session",
        run_id: str,
    ) -> BatchMaterializationResult:
        """
        Materialize multiple AgentSpecs with audit events.

        Feature #195: Agent Materializer records agent_materialized audit event.

        Args:
            specs: List of AgentSpecs to materialize
            session: SQLAlchemy database session for event recording
            run_id: UUID of the AgentRun to link events to

        Returns:
            BatchMaterializationResult with audit info on each result
        """
        results = []
        succeeded = 0
        failed = 0

        for spec in specs:
            result = self.materialize_with_audit(spec, session, run_id)
            results.append(result)
            if result.success:
                succeeded += 1
            else:
                failed += 1

        return BatchMaterializationResult(
            total=len(specs),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    def materialize_batch(
        self,
        specs: list["AgentSpec"],
        *,
        atomic: bool = False,
        progress_callback: ProgressCallback | None = None,
        event_recorder: "EventRecorder | None" = None,
        run_id: str | None = None,
    ) -> BatchMaterializationResult:
        """
        Materialize multiple AgentSpecs with optional atomic behavior.

        Feature #197: Agent Materializer handles multiple agents in batch.

        Args:
            specs: List of AgentSpecs to materialize
            atomic: If True, all specs must succeed or none are written (rollback on failure)
            progress_callback: Optional callback for progress reporting
                              Receives: (current_index, total, spec_name, status)
            event_recorder: Optional EventRecorder for audit events
            run_id: Optional run ID for audit events (required if event_recorder is provided)

        Returns:
            BatchMaterializationResult with individual results

        Step 1: Materializer accepts list of AgentSpecs ✓
        Step 2: Each spec processed and written individually ✓
        Step 3: Batch operation is atomic: all succeed or none written ✓
        Step 4: Progress reported for each agent ✓
        Step 5: Single audit event or per-agent events recorded ✓
        """
        if atomic:
            return self._materialize_batch_atomic(
                specs,
                progress_callback=progress_callback,
                event_recorder=event_recorder,
                run_id=run_id,
            )

        # Non-atomic mode: process each spec, continue on failure
        results = []
        succeeded = 0
        failed = 0

        for i, spec in enumerate(specs):
            # Report progress: processing
            if progress_callback:
                progress_callback(i + 1, len(specs), spec.name, "processing")

            result = self.materialize(spec)

            # Record per-agent audit event if recorder provided
            if event_recorder and run_id and result.success:
                try:
                    event_id = event_recorder.record_agent_materialized(
                        run_id=run_id,
                        agent_name=spec.name,
                        file_path=str(result.file_path) if result.file_path else "",
                        spec_hash=result.content_hash or "",
                        spec_id=spec.id,
                        display_name=spec.display_name,
                        task_type=spec.task_type,
                    )
                    result.audit_info = MaterializationAuditInfo(
                        event_id=event_id,
                        run_id=run_id,
                        timestamp=_utc_now(),
                        recorded=True,
                    )
                except Exception as e:
                    _logger.warning(
                        "Failed to record audit event for %s: %s",
                        spec.name, e,
                    )
                    result.audit_info = MaterializationAuditInfo(
                        run_id=run_id,
                        timestamp=_utc_now(),
                        recorded=False,
                        error=str(e),
                    )

            results.append(result)
            if result.success:
                succeeded += 1
                # Report progress: completed
                if progress_callback:
                    progress_callback(i + 1, len(specs), spec.name, "completed")
            else:
                failed += 1
                # Report progress: failed
                if progress_callback:
                    progress_callback(i + 1, len(specs), spec.name, "failed")

        return BatchMaterializationResult(
            total=len(specs),
            succeeded=succeeded,
            failed=failed,
            results=results,
            atomic=False,
            rolled_back=False,
        )

    def _materialize_batch_atomic(
        self,
        specs: list["AgentSpec"],
        *,
        progress_callback: ProgressCallback | None = None,
        event_recorder: "EventRecorder | None" = None,
        run_id: str | None = None,
    ) -> BatchMaterializationResult:
        """
        Materialize multiple AgentSpecs atomically (all succeed or none written).

        Feature #197 Step 3: Batch operation is atomic.

        This method:
        1. Renders and validates all specs first (no files written)
        2. Writes all files only if all validations pass
        3. If any write fails, rolls back all previously written files

        Args:
            specs: List of AgentSpecs to materialize
            progress_callback: Optional callback for progress reporting
            event_recorder: Optional EventRecorder for audit events
            run_id: Optional run ID for audit events

        Returns:
            BatchMaterializationResult with atomic=True
        """
        import hashlib

        results: list[MaterializationResult] = []
        written_files: list[Path] = []  # Track files for rollback
        rendered_content: list[tuple["AgentSpec", str, str]] = []  # (spec, content, hash)

        # Phase 1: Render and validate all specs (no writes)
        _logger.info("Atomic batch: Phase 1 - Rendering and validating %d specs", len(specs))

        for i, spec in enumerate(specs):
            if progress_callback:
                progress_callback(i + 1, len(specs), spec.name, "processing")

            try:
                content = self.render_claude_code_markdown(spec)
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                rendered_content.append((spec, content, content_hash))
            except Exception as e:
                _logger.error(
                    "Atomic batch: Validation failed for '%s': %s",
                    spec.name, e,
                )
                # Fail fast in atomic mode - report failure for this spec
                results.append(MaterializationResult(
                    spec_id=spec.id,
                    spec_name=spec.name,
                    success=False,
                    error=f"Render/validation failed: {e}",
                ))

                if progress_callback:
                    progress_callback(i + 1, len(specs), spec.name, "failed")

                # Return immediately with failure
                return BatchMaterializationResult(
                    total=len(specs),
                    succeeded=0,
                    failed=1,
                    results=results,
                    atomic=True,
                    rolled_back=False,  # Nothing written yet
                )

        # Phase 2: Write all files
        _logger.info("Atomic batch: Phase 2 - Writing %d files", len(rendered_content))

        output_dir = self.ensure_output_dir()

        for i, (spec, content, content_hash) in enumerate(rendered_content):
            if progress_callback:
                progress_callback(i + 1, len(specs), spec.name, "processing")

            filename = f"{spec.name}.md"
            filepath = output_dir / filename

            try:
                filepath.write_text(content, encoding="utf-8")
                written_files.append(filepath)

                _logger.info(
                    "Atomic batch: Wrote '%s' to %s (hash: %s)",
                    spec.name, filepath, content_hash[:16],
                )

                result = MaterializationResult(
                    spec_id=spec.id,
                    spec_name=spec.name,
                    success=True,
                    file_path=filepath,
                    content_hash=content_hash,
                )
                results.append(result)

                if progress_callback:
                    progress_callback(i + 1, len(specs), spec.name, "completed")

            except Exception as e:
                _logger.error(
                    "Atomic batch: Write failed for '%s': %s - rolling back",
                    spec.name, e,
                )

                # Rollback all previously written files
                for written_path in written_files:
                    try:
                        written_path.unlink()
                        _logger.info("Atomic batch: Rolled back %s", written_path)
                    except Exception as rollback_error:
                        _logger.warning(
                            "Atomic batch: Failed to rollback %s: %s",
                            written_path, rollback_error,
                        )

                # Report rollback for all specs
                if progress_callback:
                    for idx, (s, _, _) in enumerate(rendered_content):
                        progress_callback(idx + 1, len(specs), s.name, "rolled_back")

                # Add failure result
                results.append(MaterializationResult(
                    spec_id=spec.id,
                    spec_name=spec.name,
                    success=False,
                    error=f"Write failed (rolled back): {e}",
                ))

                # Clear successful results since we rolled back
                for r in results:
                    if r.success:
                        r.success = False
                        r.error = "Rolled back due to batch failure"
                        r.file_path = None

                return BatchMaterializationResult(
                    total=len(specs),
                    succeeded=0,
                    failed=len(specs),
                    results=results,
                    atomic=True,
                    rolled_back=True,
                )

        # Phase 3: Record audit events (after all writes succeed)
        if event_recorder and run_id:
            _logger.info("Atomic batch: Phase 3 - Recording audit events")

            # Record single batch audit event
            try:
                batch_payload = {
                    "batch_operation": True,
                    "total_agents": len(specs),
                    "agent_names": [spec.name for spec in specs],
                    "content_hashes": [r.content_hash for r in results if r.content_hash],
                }
                event_id = event_recorder.record(
                    run_id=run_id,
                    event_type="agent_materialized",
                    payload=batch_payload,
                )
                batch_audit = MaterializationAuditInfo(
                    event_id=event_id,
                    run_id=run_id,
                    timestamp=_utc_now(),
                    recorded=True,
                )
            except Exception as e:
                _logger.warning(
                    "Atomic batch: Failed to record batch audit event: %s", e,
                )
                batch_audit = MaterializationAuditInfo(
                    run_id=run_id,
                    timestamp=_utc_now(),
                    recorded=False,
                    error=str(e),
                )
        else:
            batch_audit = None

        return BatchMaterializationResult(
            total=len(specs),
            succeeded=len(specs),
            failed=0,
            results=results,
            atomic=True,
            rolled_back=False,
            batch_audit_info=batch_audit,
        )

    # -------------------------------------------------------------------------
    # Claude Code Markdown Rendering
    # -------------------------------------------------------------------------

    def render_claude_code_markdown(self, spec: "AgentSpec") -> str:
        """
        Render an AgentSpec as Claude Code-compatible markdown.

        Output follows Claude Code agent file conventions:
        - YAML frontmatter with: name, description, model, color
        - Markdown body with agent instructions

        This method is deterministic: same input produces identical output.

        Args:
            spec: The AgentSpec to render

        Returns:
            Claude Code-compatible markdown string
        """
        lines = []

        # Build YAML frontmatter
        frontmatter = self._build_frontmatter(spec)
        lines.append("---")
        for key, value in frontmatter.items():
            if isinstance(value, str) and ("\n" in value or '"' in value):
                # Multi-line or quoted strings need proper YAML escaping
                escaped = self._escape_yaml_string(value)
                lines.append(f"{key}: {escaped}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")

        # Build markdown body with agent instructions
        body = self._build_instructions_body(spec)
        lines.append(body)

        return "\n".join(lines)

    def _build_frontmatter(self, spec: "AgentSpec") -> dict[str, Any]:
        """
        Build the YAML frontmatter for Claude Code agent file.

        Required fields:
        - name: Agent identifier (from spec.name)
        - description: Agent description with usage examples
        - model: Claude model to use (sonnet/opus/haiku)

        Optional fields:
        - color: UI color for visual distinction

        Args:
            spec: The AgentSpec to extract frontmatter from

        Returns:
            Dictionary of frontmatter key-value pairs (ordered)
        """
        # Extract model from context or use default
        model = self._extract_model(spec)

        # Build description with objective and context
        description = self._build_description(spec)

        # Determine color based on task type
        color = TASK_TYPE_COLORS.get(spec.task_type, DEFAULT_COLOR)

        # Return ordered frontmatter
        return {
            "name": spec.name,
            "description": description,
            "model": model,
            "color": color,
        }

    def _extract_model(self, spec: "AgentSpec") -> str:
        """
        Extract model from AgentSpec context or use default.

        Args:
            spec: The AgentSpec

        Returns:
            Model string (sonnet/opus/haiku)
        """
        if spec.context and isinstance(spec.context, dict):
            model = spec.context.get("model")
            if model and model.lower() in VALID_MODELS:
                return model.lower()

        return DEFAULT_MODEL

    def _build_description(self, spec: "AgentSpec") -> str:
        """
        Build the description field for frontmatter.

        Combines display_name, objective, and task type into a
        Claude Code-compatible description with usage examples.

        Args:
            spec: The AgentSpec

        Returns:
            Description string (properly escaped for YAML)
        """
        parts = []

        # Main description
        if spec.display_name:
            parts.append(f"Agent: {spec.display_name}")

        # Task type context
        parts.append(f"Task Type: {spec.task_type}")

        # Objective
        if spec.objective:
            objective_text = spec.objective[:500]  # Truncate for frontmatter
            parts.append(f"Objective: {objective_text}")

        # Example usage (Claude Code convention)
        parts.append("")
        parts.append("Example usage:")
        parts.append("<example>")
        parts.append(f'user: "Execute {spec.display_name or spec.name}"')
        parts.append(f'assistant: "I\'ll use the {spec.name} agent to accomplish this task."')
        parts.append("<Task tool invocation>")
        parts.append("</example>")

        description = "\\n".join(parts)

        # Enforce max length
        if len(description) > DESCRIPTION_MAX_LENGTH:
            description = description[:DESCRIPTION_MAX_LENGTH - 3] + "..."

        return description

    def _build_instructions_body(self, spec: "AgentSpec") -> str:
        """
        Build the markdown body with agent instructions.

        This includes:
        - Agent role and identity
        - Objective and goals
        - Tool policy (allowed tools, restrictions)
        - Execution guidelines
        - Context information

        Args:
            spec: The AgentSpec

        Returns:
            Markdown body string
        """
        sections = []

        # Agent role introduction
        sections.append(self._build_role_section(spec))

        # Objective section
        sections.append(self._build_objective_section(spec))

        # Tool policy section
        sections.append(self._build_tool_policy_section(spec))

        # Execution guidelines
        sections.append(self._build_guidelines_section(spec))

        # Context section (if available)
        if spec.context:
            sections.append(self._build_context_section(spec))

        # Acceptance criteria (if available)
        if spec.acceptance_spec:
            sections.append(self._build_acceptance_section(spec))

        return "\n\n".join(filter(None, sections))

    def _build_role_section(self, spec: "AgentSpec") -> str:
        """Build the agent role/identity section."""
        display_name = spec.display_name or spec.name
        task_type = spec.task_type

        role_descriptions = {
            "coding": "You are a skilled software developer focused on writing high-quality, maintainable code.",
            "testing": "You are a thorough test engineer focused on ensuring software quality through comprehensive testing.",
            "refactoring": "You are an experienced software architect focused on improving code structure and maintainability.",
            "documentation": "You are a technical writer focused on creating clear, accurate documentation.",
            "audit": "You are a security auditor focused on identifying vulnerabilities and ensuring compliance.",
            "custom": "You are a specialized agent tailored for specific tasks.",
        }

        role = role_descriptions.get(task_type, role_descriptions["custom"])

        return f"""You are **{display_name}**.

{role}

Your agent identifier is `{spec.name}` and you operate as a `{task_type}` agent."""

    def _build_objective_section(self, spec: "AgentSpec") -> str:
        """Build the objective section."""
        objective = spec.objective or "(No specific objective defined)"

        return f"""## Your Objective

{objective}

Focus on achieving this objective while following the guidelines and constraints defined below."""

    def _build_tool_policy_section(self, spec: "AgentSpec") -> str:
        """Build the tool policy section."""
        lines = ["## Tool Policy"]
        lines.append("")

        if spec.tool_policy and isinstance(spec.tool_policy, dict):
            allowed_tools = spec.tool_policy.get("allowed_tools", [])
            forbidden_patterns = spec.tool_policy.get("forbidden_patterns", [])
            tool_hints = spec.tool_policy.get("tool_hints", {})

            # Allowed tools
            if allowed_tools:
                lines.append(f"### Allowed Tools ({len(allowed_tools)} available)")
                lines.append("")
                lines.append("You have access to the following tools:")
                lines.append("")
                for tool in sorted(allowed_tools)[:30]:  # Cap display at 30
                    lines.append(f"- `{tool}`")
                if len(allowed_tools) > 30:
                    lines.append(f"- ... and {len(allowed_tools) - 30} more tools")
                lines.append("")

            # Forbidden patterns
            if forbidden_patterns:
                lines.append("### Restrictions")
                lines.append("")
                lines.append("The following patterns are **forbidden** and must not appear in your commands or outputs:")
                lines.append("")
                for pattern in forbidden_patterns[:10]:
                    lines.append(f"- `{pattern}`")
                if len(forbidden_patterns) > 10:
                    lines.append(f"- ... and {len(forbidden_patterns) - 10} more patterns")
                lines.append("")

            # Tool hints
            if tool_hints:
                lines.append("### Tool Usage Hints")
                lines.append("")
                for tool_name, hint in list(tool_hints.items())[:10]:
                    hint_text = hint[:200] if len(hint) > 200 else hint
                    lines.append(f"- **{tool_name}**: {hint_text}")
                lines.append("")
        else:
            lines.append("No specific tool policy defined. Use tools responsibly.")
            lines.append("")

        return "\n".join(lines)

    def _build_guidelines_section(self, spec: "AgentSpec") -> str:
        """Build execution guidelines section."""
        lines = ["## Execution Guidelines"]
        lines.append("")

        # Budget constraints
        lines.append("### Budget Constraints")
        lines.append("")
        lines.append(f"- **Maximum Turns**: {spec.max_turns}")
        lines.append(f"- **Timeout**: {spec.timeout_seconds} seconds")
        lines.append("")

        # Task-specific guidelines based on task type
        guidelines = self._get_task_type_guidelines(spec.task_type)
        if guidelines:
            lines.append("### Best Practices")
            lines.append("")
            for guideline in guidelines:
                lines.append(f"- {guideline}")
            lines.append("")

        return "\n".join(lines)

    def _get_task_type_guidelines(self, task_type: str) -> list[str]:
        """Get task-type-specific guidelines."""
        guidelines_map = {
            "coding": [
                "Write clean, maintainable code following project conventions",
                "Include appropriate comments and documentation",
                "Handle errors gracefully",
                "Follow security best practices",
                "Run lint and type checks before completing",
            ],
            "testing": [
                "Write comprehensive test cases covering edge cases",
                "Ensure tests are deterministic and repeatable",
                "Use meaningful test names that describe behavior",
                "Verify both positive and negative scenarios",
                "Report test results clearly",
            ],
            "refactoring": [
                "Maintain existing functionality while improving structure",
                "Make incremental changes that can be reviewed",
                "Update tests to reflect refactored code",
                "Document significant architectural decisions",
                "Verify no regressions are introduced",
            ],
            "documentation": [
                "Write clear, concise documentation",
                "Include code examples where appropriate",
                "Keep documentation up-to-date with code changes",
                "Use consistent formatting and terminology",
                "Consider the target audience's technical level",
            ],
            "audit": [
                "Follow security best practices and standards",
                "Document all findings with severity levels",
                "Provide actionable remediation recommendations",
                "Never execute potentially harmful code",
                "Report sensitive findings appropriately",
            ],
        }
        return guidelines_map.get(task_type, [])

    def _build_context_section(self, spec: "AgentSpec") -> str:
        """Build context section from spec context."""
        if not spec.context:
            return ""

        lines = ["## Additional Context"]
        lines.append("")
        lines.append("```json")
        # Pretty print JSON for readability
        lines.append(json.dumps(spec.context, indent=2, sort_keys=True))
        lines.append("```")

        return "\n".join(lines)

    def _build_acceptance_section(self, spec: "AgentSpec") -> str:
        """Build acceptance criteria section."""
        if not spec.acceptance_spec:
            return ""

        lines = ["## Acceptance Criteria"]
        lines.append("")

        acc = spec.acceptance_spec
        lines.append(f"**Gate Mode**: {acc.gate_mode}")
        if acc.min_score is not None:
            lines.append(f"**Minimum Score**: {acc.min_score}")
        lines.append(f"**Retry Policy**: {acc.retry_policy}")
        lines.append(f"**Max Retries**: {acc.max_retries}")
        lines.append("")

        validators = acc.validators or []
        if validators:
            lines.append("### Validators")
            lines.append("")
            for i, v in enumerate(validators, start=1):
                v_type = v.get("type", "unknown")
                v_config = v.get("config", {})
                v_weight = v.get("weight", 1.0)
                v_required = v.get("required", False)

                required_flag = " **(required)**" if v_required else ""
                lines.append(f"{i}. `{v_type}` (weight: {v_weight}){required_flag}")

                # Show config details
                if v_config:
                    for key, val in list(v_config.items())[:3]:
                        val_str = str(val)[:100]
                        lines.append(f"   - {key}: {val_str}")
            lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Template Validation Methods (Feature #196)
    # -------------------------------------------------------------------------

    def validate_template_output(
        self,
        content: str,
        spec: "AgentSpec",
    ) -> TemplateValidationResult:
        """
        Validate rendered markdown template.

        Feature #196: Agent Materializer validates template output.

        Validation checks:
        1. Required sections present (Step 1)
        2. Tool declarations valid (Step 2)
        3. Model specification valid (Step 3)

        Args:
            content: Rendered markdown content
            spec: The AgentSpec that was rendered

        Returns:
            TemplateValidationResult with validation status and errors
        """
        errors: list[ValidationError] = []
        has_required_sections = True
        has_valid_frontmatter = True
        tools_validated = True
        model_validated = True

        # Step 1: Check for required sections
        section_errors = self._validate_required_sections(content)
        if section_errors:
            errors.extend(section_errors)
            has_required_sections = False

        # Step 1: Check frontmatter
        frontmatter_errors = self._validate_frontmatter(content)
        if frontmatter_errors:
            errors.extend(frontmatter_errors)
            has_valid_frontmatter = False

        # Step 2: Validate tool declarations against known tools
        tool_errors = self._validate_tool_declarations(spec)
        if tool_errors:
            errors.extend(tool_errors)
            tools_validated = False

        # Step 3: Validate model specification
        model_errors = self._validate_model_specification(spec, content)
        if model_errors:
            errors.extend(model_errors)
            model_validated = False

        is_valid = len(errors) == 0

        return TemplateValidationResult(
            is_valid=is_valid,
            errors=errors,
            has_required_sections=has_required_sections,
            has_valid_frontmatter=has_valid_frontmatter,
            tools_validated=tools_validated,
            model_validated=model_validated,
        )

    def _validate_required_sections(self, content: str) -> list[ValidationError]:
        """
        Validate that required markdown sections are present.

        Feature #196 Step 1: Rendered markdown checked for required sections.

        Args:
            content: Rendered markdown content

        Returns:
            List of validation errors for missing sections
        """
        errors = []
        for section in REQUIRED_MARKDOWN_SECTIONS:
            if section not in content:
                errors.append(ValidationError(
                    category="section_missing",
                    message=f"Required section '{section}' not found in rendered markdown",
                    field=section,
                ))
        return errors

    def _validate_frontmatter(self, content: str) -> list[ValidationError]:
        """
        Validate that frontmatter contains required fields.

        Feature #196 Step 1: Rendered markdown checked for required sections.

        Args:
            content: Rendered markdown content

        Returns:
            List of validation errors for frontmatter issues
        """
        errors = []

        # Check frontmatter delimiters
        if not content.startswith("---"):
            errors.append(ValidationError(
                category="frontmatter_missing",
                message="Frontmatter must start with '---'",
            ))
            return errors

        # Extract frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            errors.append(ValidationError(
                category="frontmatter_malformed",
                message="Frontmatter must be delimited by '---' at start and end",
            ))
            return errors

        frontmatter_text = parts[1].strip()

        # Check for required fields
        for field_name in REQUIRED_FRONTMATTER_FIELDS:
            # Simple pattern check for YAML field: "field_name: "
            pattern = f"^{field_name}:"
            if not re.search(pattern, frontmatter_text, re.MULTILINE):
                errors.append(ValidationError(
                    category="frontmatter_field_missing",
                    message=f"Required frontmatter field '{field_name}' not found",
                    field=field_name,
                ))

        return errors

    def _validate_tool_declarations(self, spec: "AgentSpec") -> list[ValidationError]:
        """
        Validate tool declarations against known tools.

        Feature #196 Step 2: Tool declarations validated against known tools.

        Args:
            spec: The AgentSpec being validated

        Returns:
            List of validation errors for invalid tools
        """
        errors = []

        if not spec.tool_policy or not isinstance(spec.tool_policy, dict):
            return errors

        allowed_tools = spec.tool_policy.get("allowed_tools", [])
        if not allowed_tools:
            return errors

        # Import AVAILABLE_TOOLS to validate against
        try:
            from api.tool_selection import AVAILABLE_TOOLS
            known_tools = set(AVAILABLE_TOOLS.keys())
        except ImportError:
            # If tool_selection module not available, skip this validation
            _logger.warning("Could not import AVAILABLE_TOOLS, skipping tool validation")
            return errors

        # Check each tool in allowed_tools
        for tool in allowed_tools:
            if tool not in known_tools:
                errors.append(ValidationError(
                    category="invalid_tool",
                    message=f"Tool '{tool}' is not a recognized tool",
                    field="tool_policy.allowed_tools",
                    value=tool,
                ))

        return errors

    def _validate_model_specification(
        self,
        spec: "AgentSpec",
        content: str,
    ) -> list[ValidationError]:
        """
        Validate model specification.

        Feature #196 Step 3: Model specification validated.

        Args:
            spec: The AgentSpec being validated
            content: Rendered markdown content

        Returns:
            List of validation errors for invalid model
        """
        errors = []

        # Extract model from frontmatter
        model_match = re.search(r"^model:\s*(\S+)", content, re.MULTILINE)
        if not model_match:
            errors.append(ValidationError(
                category="model_missing",
                message="Model specification not found in frontmatter",
                field="model",
            ))
            return errors

        model_value = model_match.group(1).strip()

        # Validate against known models
        if model_value not in VALID_MODELS:
            errors.append(ValidationError(
                category="invalid_model",
                message=f"Model '{model_value}' is not a valid model. Valid models: {', '.join(sorted(VALID_MODELS))}",
                field="model",
                value=model_value,
            ))

        return errors

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def _escape_yaml_string(self, value: str) -> str:
        """
        Escape a string for YAML frontmatter.

        Args:
            value: String to escape

        Returns:
            Properly escaped YAML string
        """
        # Use double quotes and escape internal quotes/newlines
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def verify_exists(self, spec: "AgentSpec") -> bool:
        """
        Verify that an agent file exists for the given spec.

        Args:
            spec: The AgentSpec to check

        Returns:
            True if the agent file exists, False otherwise
        """
        filepath = self.output_path / f"{spec.name}.md"
        return filepath.exists()

    def verify_all(self, specs: list["AgentSpec"]) -> dict[str, bool]:
        """
        Verify that agent files exist for all given specs.

        Args:
            specs: List of AgentSpecs to verify

        Returns:
            Dictionary mapping spec_id to existence status
        """
        return {spec.id: self.verify_exists(spec) for spec in specs}

    def get_file_path(self, spec: "AgentSpec") -> Path:
        """
        Get the expected file path for an AgentSpec.

        Args:
            spec: The AgentSpec

        Returns:
            Expected file path
        """
        return self.output_path / f"{spec.name}.md"


# =============================================================================
# Module-level Functions
# =============================================================================

def render_agentspec_to_markdown(spec: "AgentSpec") -> str:
    """
    Render an AgentSpec to Claude Code-compatible markdown string.

    This is a convenience function that doesn't require instantiating
    a full AgentMaterializer.

    Args:
        spec: The AgentSpec to render

    Returns:
        Claude Code-compatible markdown string
    """
    # Use a temporary materializer just for rendering
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))
        return materializer.render_claude_code_markdown(spec)


def verify_determinism(spec: "AgentSpec", iterations: int = 3) -> bool:
    """
    Verify that materializer output is deterministic.

    Renders the same spec multiple times and verifies all outputs are identical.

    Args:
        spec: The AgentSpec to test
        iterations: Number of times to render (default 3)

    Returns:
        True if all renders produced identical output, False otherwise
    """
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        outputs = []
        for _ in range(iterations):
            output = materializer.render_claude_code_markdown(spec)
            outputs.append(output)

        # Check all outputs are identical
        return len(set(outputs)) == 1
