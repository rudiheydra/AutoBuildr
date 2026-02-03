"""
Octo Service - Agent Generator
==============================

Octo is a DSPy-based service that generates AgentSpecs from structured request payloads.
It receives OctoRequestPayload from Maestro and returns one or more validated AgentSpecs.

Feature #176: Maestro delegates to Octo for agent generation
Feature #182: Octo DSPy signature for AgentSpec generation
Feature #183: Octo processes OctoRequestPayload and returns AgentSpecs
Feature #188: Octo outputs are strictly typed and schema-validated

This module provides:
- OctoRequestPayload: Structured input containing project context, required capabilities, and constraints
- OctoResponse: Response containing generated AgentSpecs and any errors
- Octo: Service class that invokes DSPy pipeline to generate AgentSpecs

Usage:
    from api.octo import Octo, OctoRequestPayload

    # Create Octo service
    octo = Octo(api_key="sk-...")

    # Build request payload
    payload = OctoRequestPayload(
        project_context={"name": "MyApp", "tech_stack": ["React", "Python"]},
        required_capabilities=["ui_testing", "api_testing"],
        existing_agents=["coder", "test-runner"],
        constraints={"max_agents": 3}
    )

    # Generate AgentSpecs
    response = octo.generate_specs(payload)
    if response.success:
        for spec in response.agent_specs:
            print(f"Generated: {spec.name}")
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from api.agentspec_models import (
    AcceptanceSpec,
    AgentSpec,
    TASK_TYPES,
    generate_uuid,
)
from api.spec_builder import (
    SpecBuilder,
    BuildResult,
    get_spec_builder,
)
from api.spec_validator import (
    validate_spec,
    SpecValidationResult,
)
from api.display_derivation import derive_display_name, derive_icon

_logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Schemas
# =============================================================================

@dataclass
class OctoRequestPayload:
    """
    Structured request payload for Octo agent generation.

    Contains all context Octo needs to generate appropriate AgentSpecs:
    - project_context: Discovery artifacts, tech stack, app spec summary
    - required_capabilities: List of capabilities needed (e.g., "e2e_testing", "api_testing")
    - existing_agents: Names of agents already available (to avoid duplication)
    - constraints: Limits like max_agents, model restrictions, tool restrictions

    Feature #175: Maestro produces structured Octo request payload
    """
    project_context: dict[str, Any]
    required_capabilities: list[str]
    existing_agents: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    # Optional metadata for traceability
    source_feature_ids: list[int] = field(default_factory=list)
    request_id: str = field(default_factory=generate_uuid)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_context": self.project_context,
            "required_capabilities": self.required_capabilities,
            "existing_agents": self.existing_agents,
            "constraints": self.constraints,
            "source_feature_ids": self.source_feature_ids,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OctoRequestPayload":
        """Create from dictionary."""
        return cls(
            project_context=data.get("project_context", {}),
            required_capabilities=data.get("required_capabilities", []),
            existing_agents=data.get("existing_agents", []),
            constraints=data.get("constraints", {}),
            source_feature_ids=data.get("source_feature_ids", []),
            request_id=data.get("request_id", generate_uuid()),
        )

    def validate(self) -> list[str]:
        """
        Validate the payload structure.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # project_context is required and must be dict
        if not isinstance(self.project_context, dict):
            errors.append("project_context must be a dictionary")

        # required_capabilities must be non-empty list
        if not isinstance(self.required_capabilities, list):
            errors.append("required_capabilities must be a list")
        elif len(self.required_capabilities) == 0:
            errors.append("required_capabilities cannot be empty")
        else:
            for i, cap in enumerate(self.required_capabilities):
                if not isinstance(cap, str) or not cap.strip():
                    errors.append(f"required_capabilities[{i}] must be a non-empty string")

        # existing_agents must be list of strings
        if not isinstance(self.existing_agents, list):
            errors.append("existing_agents must be a list")
        else:
            for i, agent in enumerate(self.existing_agents):
                if not isinstance(agent, str):
                    errors.append(f"existing_agents[{i}] must be a string")

        # constraints must be dict
        if not isinstance(self.constraints, dict):
            errors.append("constraints must be a dictionary")

        return errors


@dataclass
class OctoResponse:
    """
    Response from Octo containing generated AgentSpecs.

    Feature #188: Octo outputs are strictly typed and schema-validated
    """
    success: bool
    agent_specs: list[AgentSpec] = field(default_factory=list)
    error: str | None = None
    error_type: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "agent_specs": [spec.to_dict() for spec in self.agent_specs],
            "error": self.error,
            "error_type": self.error_type,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "request_id": self.request_id,
        }


# =============================================================================
# Octo Service Class
# =============================================================================

class Octo:
    """
    Octo service for generating AgentSpecs from structured request payloads.

    Octo uses DSPy (via SpecBuilder) to generate AgentSpecs based on:
    - Project context (tech stack, features, environment)
    - Required capabilities (what the agents need to do)
    - Existing agents (to avoid duplication)
    - Constraints (budget limits, model preferences)

    Each generated AgentSpec is validated against the schema before being
    returned to Maestro.

    Feature #176: Maestro delegates to Octo for agent generation
    Feature #183: Octo processes OctoRequestPayload and returns AgentSpecs
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        spec_builder: SpecBuilder | None = None,
    ):
        """
        Initialize Octo service.

        Args:
            api_key: Anthropic API key (uses environment if not provided)
            spec_builder: Optional SpecBuilder instance (creates new if not provided)
        """
        self._api_key = api_key

        # Use provided builder or get/create singleton
        if spec_builder is not None:
            self._builder = spec_builder
        else:
            self._builder = get_spec_builder(
                api_key=api_key,
                force_new=api_key is not None,
            )

        _logger.info("Octo service initialized")

    def generate_specs(
        self,
        payload: OctoRequestPayload,
    ) -> OctoResponse:
        """
        Generate AgentSpecs from the request payload.

        This is the main entry point for Octo. It:
        1. Validates the payload structure
        2. Maps required capabilities to task descriptions
        3. Invokes DSPy SpecBuilder for each capability
        4. Validates each generated AgentSpec against schema
        5. Returns all valid specs in the response

        Args:
            payload: OctoRequestPayload containing context and requirements

        Returns:
            OctoResponse with generated specs or error information
        """
        # Step 1: Validate payload
        validation_errors = payload.validate()
        if validation_errors:
            _logger.warning("Invalid OctoRequestPayload: %s", validation_errors)
            return OctoResponse(
                success=False,
                error="Invalid request payload",
                error_type="validation_error",
                validation_errors=validation_errors,
                request_id=payload.request_id,
            )

        _logger.info(
            "Octo processing request: %d capabilities, %d existing agents",
            len(payload.required_capabilities),
            len(payload.existing_agents),
        )

        # Step 2: Generate specs for each capability
        generated_specs: list[AgentSpec] = []
        warnings: list[str] = []

        for capability in payload.required_capabilities:
            # Skip if an agent with similar capability already exists
            if self._capability_covered(capability, payload.existing_agents):
                warnings.append(f"Capability '{capability}' covered by existing agent")
                continue

            # Build task description from capability
            task_desc = self._build_task_description(capability, payload)
            task_type = self._infer_task_type(capability)

            # Invoke SpecBuilder
            _logger.info("Generating spec for capability: %s (task_type=%s)", capability, task_type)

            try:
                result: BuildResult = self._builder.build(
                    task_description=task_desc,
                    task_type=task_type,
                    context={
                        "capability": capability,
                        "project_context": payload.project_context,
                        "octo_request_id": payload.request_id,
                    },
                )

                if result.success and result.agent_spec:
                    # Validate generated spec against schema
                    validation_result = self._validate_spec(result.agent_spec)

                    if validation_result.is_valid:
                        generated_specs.append(result.agent_spec)
                        _logger.info(
                            "Generated valid spec: %s (task_type=%s)",
                            result.agent_spec.name,
                            result.agent_spec.task_type,
                        )
                    else:
                        warnings.append(
                            f"Spec for '{capability}' failed validation: {validation_result.errors}"
                        )
                        _logger.warning(
                            "Spec validation failed for %s: %s",
                            capability,
                            validation_result.errors,
                        )
                else:
                    warnings.append(
                        f"Failed to generate spec for '{capability}': {result.error}"
                    )
                    _logger.warning(
                        "SpecBuilder failed for %s: %s",
                        capability,
                        result.error,
                    )

            except Exception as e:
                warnings.append(f"Exception generating spec for '{capability}': {e}")
                _logger.exception("Exception during spec generation for %s", capability)

        # Step 3: Check if any specs were generated
        if not generated_specs:
            return OctoResponse(
                success=False,
                error="No valid specs generated",
                error_type="generation_failed",
                warnings=warnings,
                request_id=payload.request_id,
            )

        _logger.info(
            "Octo generated %d specs for request %s",
            len(generated_specs),
            payload.request_id,
        )

        return OctoResponse(
            success=True,
            agent_specs=generated_specs,
            warnings=warnings,
            request_id=payload.request_id,
        )

    def _capability_covered(
        self,
        capability: str,
        existing_agents: list[str],
    ) -> bool:
        """
        Check if a capability is already covered by existing agents.

        Uses simple string matching for now. Can be made smarter with
        capability-to-agent mapping.
        """
        capability_lower = capability.lower()

        for agent in existing_agents:
            agent_lower = agent.lower()
            # Check for substring matches
            if capability_lower in agent_lower or agent_lower in capability_lower:
                return True
            # Check common mappings
            if (capability_lower == "coding" and "coder" in agent_lower):
                return True
            if (capability_lower == "testing" and "test" in agent_lower):
                return True

        return False

    def _build_task_description(
        self,
        capability: str,
        payload: OctoRequestPayload,
    ) -> str:
        """
        Build a natural language task description for DSPy from capability.
        """
        project_name = payload.project_context.get("name", "the project")
        tech_stack = payload.project_context.get("tech_stack", [])
        tech_str = ", ".join(tech_stack) if tech_stack else "various technologies"

        # Map common capabilities to descriptions
        capability_descriptions = {
            "ui_testing": f"Implement end-to-end UI testing for {project_name} using browser automation.",
            "api_testing": f"Implement API integration tests for {project_name}'s backend endpoints.",
            "e2e_testing": f"Implement comprehensive end-to-end tests for {project_name}.",
            "unit_testing": f"Implement unit tests for {project_name} components.",
            "documentation": f"Generate and maintain documentation for {project_name}.",
            "security_audit": f"Perform security audit and vulnerability scanning for {project_name}.",
            "code_review": f"Review code changes and enforce quality standards for {project_name}.",
            "refactoring": f"Identify and implement refactoring opportunities in {project_name}.",
            "deployment": f"Handle deployment and release processes for {project_name}.",
            "monitoring": f"Set up monitoring and alerting for {project_name}.",
        }

        base_desc = capability_descriptions.get(
            capability.lower(),
            f"Implement {capability} functionality for {project_name}."
        )

        return f"{base_desc} The project uses {tech_str}."

    def _infer_task_type(self, capability: str) -> str:
        """
        Infer task_type from capability name.
        """
        capability_lower = capability.lower()

        # Testing-related capabilities
        if any(kw in capability_lower for kw in ["test", "qa", "e2e", "integration"]):
            return "testing"

        # Documentation capabilities
        if any(kw in capability_lower for kw in ["doc", "readme", "wiki"]):
            return "documentation"

        # Audit/security capabilities
        if any(kw in capability_lower for kw in ["audit", "security", "scan", "review"]):
            return "audit"

        # Refactoring capabilities
        if any(kw in capability_lower for kw in ["refactor", "cleanup", "optimize"]):
            return "refactoring"

        # Default to coding
        return "coding"

    def _validate_spec(self, spec: AgentSpec) -> SpecValidationResult:
        """
        Validate an AgentSpec against the schema.

        Feature #188: Octo outputs are strictly typed and schema-validated
        """
        return validate_spec(spec)


# =============================================================================
# Module-level convenience functions
# =============================================================================

_default_octo: Octo | None = None


def get_octo(api_key: str | None = None) -> Octo:
    """
    Get or create the default Octo instance.

    Args:
        api_key: Optional API key override

    Returns:
        Octo service instance
    """
    global _default_octo

    if _default_octo is None or api_key is not None:
        _default_octo = Octo(api_key=api_key)

    return _default_octo


def reset_octo() -> None:
    """Reset the default Octo instance (for testing)."""
    global _default_octo
    _default_octo = None
