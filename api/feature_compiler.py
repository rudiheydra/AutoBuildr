"""
Feature Compiler Module
=======================

Converts Feature database records into AgentSpecs with derived tool_policy
and acceptance validators.

This module bridges the Feature-based backlog (test cases) with the AgentSpec-based
execution system (HarnessKernel). Each Feature can be compiled into an AgentSpec
ready for autonomous execution.

The compiler:
- Generates machine-readable spec names from features
- Derives task_type from feature category
- Creates appropriate tool_policy based on category conventions
- Converts feature steps into acceptance validators
- Maintains traceability via source_feature_id

Example:
    ```python
    from api.feature_compiler import FeatureCompiler

    compiler = FeatureCompiler()

    # Compile a feature into an AgentSpec
    feature = session.query(Feature).get(42)
    spec = compiler.compile(feature)

    # Execute via kernel
    kernel.execute(spec)
    ```
"""
from __future__ import annotations

import logging
import re
from typing import Any

from api.agentspec_models import (
    AcceptanceSpec,
    AgentSpec,
    create_tool_policy,
    create_validator,
    generate_uuid,
)
from api.database import Feature
from api.display_derivation import (
    DEFAULT_ICON,
    TASK_TYPE_ICONS,
)
from api.static_spec_adapter import (
    CODING_TOOLS,
    DEFAULT_BUDGETS,
    FORBIDDEN_PATTERNS,
    TESTING_TOOLS,
)

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Category to task_type mapping
# Categories typically come from feature organization (e.g., "A. Database", "F. UI-Backend")
CATEGORY_TO_TASK_TYPE: dict[str, str] = {
    # Database-related categories map to coding
    "database": "coding",
    "data": "coding",
    "schema": "coding",
    "migration": "coding",
    # API-related categories map to coding
    "api": "coding",
    "endpoint": "coding",
    "backend": "coding",
    "rest": "coding",
    # UI-related categories map to coding
    "ui": "coding",
    "frontend": "coding",
    "component": "coding",
    "page": "coding",
    # Testing-related categories map to testing
    "test": "testing",
    "testing": "testing",
    "verification": "testing",
    "validation": "testing",
    "qa": "testing",
    # Documentation categories
    "docs": "documentation",
    "documentation": "documentation",
    "readme": "documentation",
    # Refactoring categories
    "refactor": "refactoring",
    "refactoring": "refactoring",
    "cleanup": "refactoring",
    # Audit/security categories
    "audit": "audit",
    "security": "audit",
    "review": "audit",
    # Workflow/integration categories default to coding
    "workflow": "coding",
    "integration": "coding",
    "feature": "coding",
}

# Task type to icon mapping and default icon are imported from
# api.display_derivation (Feature #148: single source of truth)


# =============================================================================
# Helper Functions
# =============================================================================

def slugify(text: str, max_length: int = 50) -> str:
    """
    Convert text to a URL-friendly slug.

    Args:
        text: Text to slugify
        max_length: Maximum length of the slug

    Returns:
        Lowercase slug with hyphens
    """
    # Convert to lowercase
    slug = text.lower()

    # Replace non-alphanumeric with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)

    # Truncate to max_length
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')

    return slug


def extract_task_type_from_category(category: str) -> str:
    """
    Derive task_type from a feature category string.

    The category is parsed by:
    1. Removing any letter prefix (e.g., "A. Database" -> "Database")
    2. Normalizing to lowercase
    3. Checking against known category mappings
    4. Defaulting to "coding" for unknown categories

    Args:
        category: Feature category string

    Returns:
        Task type string (coding, testing, documentation, refactoring, audit, custom)
    """
    # Remove letter prefix pattern like "A. ", "B. ", etc.
    cleaned = re.sub(r'^[A-Z]\.\s*', '', category)

    # Normalize to lowercase
    cleaned_lower = cleaned.lower()

    # Check each word in the category against mappings
    words = cleaned_lower.replace('-', ' ').replace('_', ' ').split()

    for word in words:
        if word in CATEGORY_TO_TASK_TYPE:
            return CATEGORY_TO_TASK_TYPE[word]

    # Check if category contains any known keywords
    for keyword, task_type in CATEGORY_TO_TASK_TYPE.items():
        if keyword in cleaned_lower:
            return task_type

    # Default to coding
    return "coding"


def get_tools_for_task_type(task_type: str) -> list[str]:
    """
    Get the appropriate tool list for a task type.

    Args:
        task_type: The task type (coding, testing, etc.)

    Returns:
        List of allowed tool names
    """
    if task_type == "testing":
        return TESTING_TOOLS.copy()
    elif task_type in ("documentation", "audit"):
        # Read-only tools for documentation/audit
        return [
            "Read",
            "Glob",
            "Grep",
            "feature_get_by_id",
            "feature_get_stats",
            "Write",  # For docs
            "Bash",  # Limited
        ]
    else:
        # Default to coding tools
        return CODING_TOOLS.copy()


def get_budget_for_task_type(task_type: str) -> dict[str, int]:
    """
    Get the appropriate execution budget for a task type.

    Args:
        task_type: The task type

    Returns:
        Dictionary with max_turns and timeout_seconds
    """
    if task_type == "testing":
        return DEFAULT_BUDGETS.get("testing", {"max_turns": 50, "timeout_seconds": 900})
    elif task_type in ("documentation", "audit"):
        return {"max_turns": 30, "timeout_seconds": 600}
    else:
        return DEFAULT_BUDGETS.get("coding", {"max_turns": 150, "timeout_seconds": 1800})


# =============================================================================
# FeatureCompiler Class
# =============================================================================

class FeatureCompiler:
    """
    Compiles Feature records into AgentSpecs for kernel execution.

    The compiler creates fully-formed AgentSpecs from Features, including:
    - Unique machine-readable names
    - Human-readable display names
    - Task-appropriate tool policies
    - Acceptance validators from feature steps
    - Proper traceability linking

    Attributes:
        default_icon: Default icon for specs without category-specific icons
    """

    def __init__(self, *, default_icon: str = DEFAULT_ICON):
        """
        Initialize the FeatureCompiler.

        Args:
            default_icon: Default icon for specs
        """
        self._default_icon = default_icon

    def compile(self, feature: Feature, *, spec_id: str | None = None) -> AgentSpec:
        """
        Compile a Feature into an AgentSpec.

        This is the main entry point for feature compilation. It creates
        a complete AgentSpec with all necessary fields populated.

        Args:
            feature: The Feature database record to compile
            spec_id: Optional spec ID (generates UUID if not provided)

        Returns:
            AgentSpec ready for kernel execution
        """
        # Step 2: Generate spec name
        spec_name = self._generate_spec_name(feature)

        # Step 3: Generate display name
        display_name = self._generate_display_name(feature)

        # Step 4: Set objective from description
        objective = self._generate_objective(feature)

        # Step 5: Determine task_type from category
        task_type = extract_task_type_from_category(feature.category)

        # Step 6: Derive tool_policy based on category
        tool_policy = self._derive_tool_policy(feature, task_type)

        # Get icon for task type
        icon = TASK_TYPE_ICONS.get(task_type, self._default_icon)

        # Get budget for task type
        budget = get_budget_for_task_type(task_type)

        # Create the AgentSpec
        spec = AgentSpec(
            id=spec_id or generate_uuid(),
            name=spec_name,
            display_name=display_name,
            icon=icon,
            spec_version="v1",
            objective=objective,
            task_type=task_type,
            context={
                "feature_id": feature.id,
                "feature_name": feature.name,
                "feature_category": feature.category,
                "feature_steps": feature.steps or [],
            },
            tool_policy=tool_policy,
            max_turns=budget["max_turns"],
            timeout_seconds=budget["timeout_seconds"],
            # Step 8: Set source_feature_id for traceability
            source_feature_id=feature.id,
            # Step 9: Set priority from feature priority
            priority=feature.priority,
            tags=[
                f"feature-{feature.id}",
                feature.category.lower().replace(" ", "-"),
                task_type,
            ],
        )

        # Step 7: Create acceptance validators from feature steps
        acceptance_spec = self._create_acceptance_spec(feature, spec.id, task_type)
        spec.acceptance_spec = acceptance_spec

        _logger.info(
            "Compiled Feature #%d '%s' into AgentSpec '%s' (task_type=%s)",
            feature.id,
            feature.name,
            spec.name,
            task_type,
        )

        # Step 10: Return complete AgentSpec
        return spec

    def _generate_spec_name(self, feature: Feature) -> str:
        """
        Generate a machine-readable spec name from a feature.

        Format: feature-{id}-{slug}

        Args:
            feature: The feature to generate name for

        Returns:
            Machine-readable spec name
        """
        slug = slugify(feature.name)
        return f"feature-{feature.id}-{slug}"

    def _generate_display_name(self, feature: Feature) -> str:
        """
        Generate a human-readable display name from a feature.

        Args:
            feature: The feature to generate display name for

        Returns:
            Human-readable display name
        """
        return feature.name

    def _generate_objective(self, feature: Feature) -> str:
        """
        Generate the objective text from feature description.

        The objective includes:
        - The feature description
        - The verification steps as a checklist

        Args:
            feature: The feature to generate objective for

        Returns:
            Complete objective text
        """
        parts = [
            f"## Objective: {feature.name}",
            "",
            feature.description,
            "",
        ]

        # Add steps as verification criteria
        steps = feature.steps or []
        if steps:
            parts.append("## Verification Steps")
            parts.append("")
            for i, step in enumerate(steps, start=1):
                parts.append(f"{i}. {step}")

        return "\n".join(parts)

    def _derive_tool_policy(self, feature: Feature, task_type: str) -> dict[str, Any]:
        """
        Derive a tool_policy based on feature category and task type.

        Args:
            feature: The feature being compiled
            task_type: The derived task type

        Returns:
            Tool policy dictionary
        """
        # Get appropriate tools for task type
        allowed_tools = get_tools_for_task_type(task_type)

        # Create tool hints based on task type
        tool_hints: dict[str, str] = {}

        if task_type == "coding":
            tool_hints = {
                "feature_mark_passing": (
                    "ONLY call after thorough verification with browser automation. "
                    "Take screenshots to prove the feature works."
                ),
                "Edit": (
                    "Prefer editing existing files over creating new ones. "
                    "Always read files before editing."
                ),
                "Bash": (
                    "Commands are restricted by security allowlist. "
                    "Only development commands are permitted."
                ),
            }
        elif task_type == "testing":
            tool_hints = {
                "feature_mark_passing": (
                    "Call only after all verification steps pass."
                ),
                "feature_mark_failing": (
                    "Use to report regressions found during testing."
                ),
                "Bash": (
                    "Use for running test commands only. Do not modify code."
                ),
            }

        return create_tool_policy(
            allowed_tools=allowed_tools,
            forbidden_patterns=FORBIDDEN_PATTERNS.copy(),
            tool_hints=tool_hints,
        )

    def _create_acceptance_spec(
        self,
        feature: Feature,
        agent_spec_id: str,
        task_type: str,
    ) -> AcceptanceSpec:
        """
        Create an AcceptanceSpec from feature steps.

        Each feature step becomes a test_pass validator that must be
        verified during execution.

        Args:
            feature: The feature being compiled
            agent_spec_id: ID of the parent AgentSpec
            task_type: The task type for this feature

        Returns:
            AcceptanceSpec with validators from feature steps
        """
        validators = []

        # Create validators from feature steps
        steps = feature.steps or []
        if steps:
            for i, step in enumerate(steps, start=1):
                validators.append(
                    create_validator(
                        validator_type="test_pass",
                        config={
                            "name": f"step_{i}",
                            "description": step,
                            "step_number": i,
                            "feature_id": feature.id,
                            # No automatic command - manual verification
                            "command": None,
                        },
                        weight=1.0 / max(len(steps), 1),
                        required=False,
                    )
                )

        # Add feature_passing validator (the core requirement)
        validators.append(
            create_validator(
                validator_type="custom",
                config={
                    "name": "feature_passing",
                    "description": f"Feature #{feature.id} must be marked as passing",
                    "check_type": "feature_status",
                    "feature_id": feature.id,
                    "expected_status": "passing",
                },
                weight=1.0,
                required=True,
            )
        )

        # Determine gate mode and retry policy based on task type
        if task_type == "testing":
            gate_mode = "all_pass"
            retry_policy = "none"
            max_retries = 0
        else:
            gate_mode = "all_pass"
            retry_policy = "fixed"
            max_retries = 2

        return AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=agent_spec_id,
            validators=validators,
            gate_mode=gate_mode,
            retry_policy=retry_policy,
            max_retries=max_retries,
        )


# =============================================================================
# Module-level Convenience Functions
# =============================================================================

_default_compiler: FeatureCompiler | None = None


def get_feature_compiler() -> FeatureCompiler:
    """
    Get or create the default FeatureCompiler.

    Returns:
        The default FeatureCompiler instance
    """
    global _default_compiler

    if _default_compiler is None:
        _default_compiler = FeatureCompiler()

    return _default_compiler


def reset_feature_compiler() -> None:
    """Reset the default compiler (for testing)."""
    global _default_compiler
    _default_compiler = None


def compile_feature(feature: Feature, *, spec_id: str | None = None) -> AgentSpec:
    """
    Convenience function to compile a feature using the default compiler.

    Args:
        feature: The Feature to compile
        spec_id: Optional spec ID

    Returns:
        Compiled AgentSpec
    """
    compiler = get_feature_compiler()
    return compiler.compile(feature, spec_id=spec_id)
