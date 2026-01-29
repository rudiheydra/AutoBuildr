"""
Spec Builder Router
===================

REST endpoints for the DSPy SpecBuilder pipeline and TemplateRegistry.

Feature #135: Create Spec Builder API router with compile and templates endpoints.

Endpoints:
- POST /api/spec-builder/compile - Compile a task description into an AgentSpec
- GET /api/spec-builder/templates - List available templates from the TemplateRegistry
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/spec-builder", tags=["spec-builder"])

# Root directory (project root)
ROOT_DIR = Path(__file__).parent.parent.parent


# ============================================================================
# Request / Response Models
# ============================================================================


class CompileRequest(BaseModel):
    """Request body for the compile endpoint."""

    task_description: str = Field(
        ...,
        min_length=1,
        description="Natural language description of the task to compile into an AgentSpec",
    )
    task_type: str = Field(
        default="coding",
        description="Type of task: coding, testing, refactoring, documentation, audit, or custom",
    )
    project_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional project context (project name, file paths, etc.)",
    )


class ValidatorResponse(BaseModel):
    """A single validator in the compiled spec."""

    type: str
    config: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0
    required: bool = False


class AcceptanceSpecResponse(BaseModel):
    """Acceptance spec within the compiled result."""

    id: str
    agent_spec_id: str
    validators: list[dict[str, Any]] = Field(default_factory=list)
    gate_mode: str = "all_pass"
    retry_policy: str = "none"
    max_retries: int = 0


class AgentSpecResponse(BaseModel):
    """AgentSpec within the compiled result."""

    id: str
    name: str
    display_name: str
    icon: str
    spec_version: str
    objective: str
    task_type: str
    context: dict[str, Any] = Field(default_factory=dict)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
    max_turns: int
    timeout_seconds: int
    source_feature_id: int | None = None
    tags: list[str] = Field(default_factory=list)


class CompileResponse(BaseModel):
    """Response from the compile endpoint."""

    success: bool
    agent_spec: AgentSpecResponse | None = None
    acceptance_spec: AcceptanceSpecResponse | None = None
    error: str | None = None
    error_type: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TemplateMetadataResponse(BaseModel):
    """Metadata for a single template."""

    task_type: str | None = None
    required_tools: list[str] = Field(default_factory=list)
    default_max_turns: int | None = None
    default_timeout_seconds: int | None = None
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    variables: list[str] = Field(default_factory=list)


class TemplateResponse(BaseModel):
    """A single template in the templates list."""

    name: str
    path: str
    content_hash: str
    loaded_at: str
    metadata: TemplateMetadataResponse


class TemplatesListResponse(BaseModel):
    """Response from the templates endpoint."""

    templates: list[TemplateResponse]
    count: int


# ============================================================================
# Helper Functions
# ============================================================================


def _spec_to_response(spec: Any) -> AgentSpecResponse:
    """Convert an AgentSpec dataclass/model to a response model."""
    return AgentSpecResponse(
        id=spec.id,
        name=spec.name,
        display_name=spec.display_name,
        icon=spec.icon,
        spec_version=spec.spec_version,
        objective=spec.objective,
        task_type=spec.task_type,
        context=spec.context if isinstance(spec.context, dict) else {},
        tool_policy=spec.tool_policy if isinstance(spec.tool_policy, dict) else {},
        max_turns=spec.max_turns,
        timeout_seconds=spec.timeout_seconds,
        source_feature_id=getattr(spec, "source_feature_id", None),
        tags=spec.tags if isinstance(spec.tags, list) else [],
    )


def _acceptance_to_response(acceptance: Any) -> AcceptanceSpecResponse:
    """Convert an AcceptanceSpec dataclass/model to a response model."""
    # Normalize validators to list of dicts
    validators_list = []
    if hasattr(acceptance, "validators") and acceptance.validators:
        for v in acceptance.validators:
            if isinstance(v, dict):
                validators_list.append(v)
            else:
                # Dataclass or similar — convert to dict
                validators_list.append(
                    {
                        "type": getattr(v, "type", "custom"),
                        "config": getattr(v, "config", {}),
                        "weight": getattr(v, "weight", 1.0),
                        "required": getattr(v, "required", False),
                    }
                )

    return AcceptanceSpecResponse(
        id=acceptance.id,
        agent_spec_id=acceptance.agent_spec_id,
        validators=validators_list,
        gate_mode=getattr(acceptance, "gate_mode", "all_pass"),
        retry_policy=getattr(acceptance, "retry_policy", "none"),
        max_retries=getattr(acceptance, "max_retries", 0),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/compile", response_model=CompileResponse)
async def compile_spec(request: CompileRequest):
    """
    Compile a task description into an AgentSpec using the DSPy pipeline.

    Accepts a natural language task description, task type, and optional project
    context. Returns a fully formed AgentSpec and AcceptanceSpec, or error details
    if compilation fails.

    The DSPy pipeline:
    1. Detects task type and derives execution budgets
    2. Generates a unique spec name
    3. Creates acceptance validators from the task description
    4. Assembles the final AgentSpec via SpecBuilder.build()
    """
    try:
        from api.spec_builder import get_spec_builder, SpecBuilderError

        builder = get_spec_builder()
        result = builder.build(
            task_description=request.task_description,
            task_type=request.task_type,
            context=request.project_context,
        )

        if result.success and result.agent_spec and result.acceptance_spec:
            return CompileResponse(
                success=True,
                agent_spec=_spec_to_response(result.agent_spec),
                acceptance_spec=_acceptance_to_response(result.acceptance_spec),
                warnings=result.warnings,
            )
        else:
            return CompileResponse(
                success=False,
                error=result.error,
                error_type=result.error_type,
                validation_errors=result.validation_errors,
                warnings=result.warnings,
            )

    except SpecBuilderError as e:
        logger.exception("SpecBuilder error during compile")
        return CompileResponse(
            success=False,
            error=str(e),
            error_type="spec_builder_error",
        )
    except Exception as e:
        logger.exception("Unexpected error during spec compilation")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during spec compilation: {str(e)}",
        )


@router.get("/templates", response_model=TemplatesListResponse)
async def list_templates():
    """
    List available templates from the TemplateRegistry.

    Returns all templates found in the prompts/ directory, including their
    metadata (task_type, required_tools, default budgets, etc.).
    """
    try:
        from api.template_registry import get_template_registry

        prompts_dir = ROOT_DIR / "prompts"
        registry = get_template_registry(prompts_dir)

        raw_templates = registry.list_templates()

        templates = []
        for t in raw_templates:
            metadata_dict = t.get("metadata", {})
            metadata = TemplateMetadataResponse(
                task_type=metadata_dict.get("task_type"),
                required_tools=metadata_dict.get("required_tools", []),
                default_max_turns=metadata_dict.get("default_max_turns"),
                default_timeout_seconds=metadata_dict.get("default_timeout_seconds"),
                name=metadata_dict.get("name"),
                description=metadata_dict.get("description"),
                icon=metadata_dict.get("icon"),
                variables=metadata_dict.get("variables", []),
            )
            templates.append(
                TemplateResponse(
                    name=t.get("name", "unknown"),
                    path=t.get("path", ""),
                    content_hash=t.get("content_hash", ""),
                    loaded_at=t.get("loaded_at", ""),
                    metadata=metadata,
                )
            )

        return TemplatesListResponse(
            templates=templates,
            count=len(templates),
        )

    except Exception as e:
        logger.exception("Error listing templates")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list templates: {str(e)}",
        )
