"""
AgentSpec Validator
===================

Validates AgentSpec objects before kernel execution.

This module provides comprehensive validation of AgentSpecs to ensure:
- Required fields are present and non-empty
- Tool policy structure is valid
- Budget values are within constraints
- Field types and formats are correct

Implements Feature #78: Invalid AgentSpec Graceful Handling

Usage:
    from api.spec_validator import validate_spec, SpecValidationError, SpecValidationResult

    # Validate a spec before execution
    result = validate_spec(spec)
    if not result.is_valid:
        # Handle validation errors
        for error in result.errors:
            print(f"{error.field}: {error.message}")

    # Or raise exception on invalid
    validate_spec_or_raise(spec)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

# Setup logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Valid task types (must match api/agentspec_models.py)
VALID_TASK_TYPES = frozenset(["coding", "testing", "refactoring", "documentation", "audit", "custom"])

# Budget constraints (must match database CHECK constraints)
MIN_MAX_TURNS = 1
MAX_MAX_TURNS = 500
MIN_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 7200

# Required fields for AgentSpec
REQUIRED_FIELDS = frozenset(["name", "display_name", "objective", "task_type", "tool_policy"])

# Tool policy required fields
TOOL_POLICY_REQUIRED_FIELDS = frozenset(["allowed_tools"])

# Name pattern (lowercase, hyphens allowed)
NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$')


# =============================================================================
# Validation Error Classes
# =============================================================================

@dataclass
class ValidationError:
    """
    A single validation error for a field.

    Attributes:
        field: Name of the field with the error
        message: Human-readable error message
        code: Machine-readable error code
        value: The invalid value (optional, for debugging)
    """
    field: str
    message: str
    code: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "field": self.field,
            "message": self.message,
            "code": self.code,
        }
        if self.value is not None:
            result["value"] = str(self.value)[:100]  # Truncate long values
        return result


@dataclass
class SpecValidationResult:
    """
    Result of validating an AgentSpec.

    Attributes:
        is_valid: True if the spec passed all validations
        errors: List of validation errors (empty if valid)
        spec_id: ID of the spec that was validated (if available)
        spec_name: Name of the spec that was validated (if available)
    """
    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    spec_id: str | None = None
    spec_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "error_count": len(self.errors),
        }

    @property
    def error_messages(self) -> list[str]:
        """Get list of error messages."""
        return [e.message for e in self.errors]

    @property
    def first_error(self) -> ValidationError | None:
        """Get the first validation error, if any."""
        return self.errors[0] if self.errors else None


class SpecValidationError(Exception):
    """
    Exception raised when AgentSpec validation fails.

    Contains the full validation result with all errors.

    Attributes:
        result: The SpecValidationResult with error details
    """

    def __init__(self, result: SpecValidationResult):
        self.result = result
        # Build a summary message from all errors
        if result.errors:
            error_summary = "; ".join(f"{e.field}: {e.message}" for e in result.errors[:5])
            if len(result.errors) > 5:
                error_summary += f" (and {len(result.errors) - 5} more errors)"
            message = f"AgentSpec validation failed: {error_summary}"
        else:
            message = "AgentSpec validation failed"
        super().__init__(message)


# =============================================================================
# Validation Functions
# =============================================================================

def _validate_required_fields(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Check that required fields are present and non-empty.

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    for field_name in REQUIRED_FIELDS:
        value = getattr(spec, field_name, None)

        if value is None:
            errors.append(ValidationError(
                field=field_name,
                message=f"Required field '{field_name}' is missing",
                code="required_field_missing",
            ))
        elif isinstance(value, str) and not value.strip():
            errors.append(ValidationError(
                field=field_name,
                message=f"Required field '{field_name}' cannot be empty",
                code="required_field_empty",
                value=value,
            ))


def _validate_name_format(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate the name field format (lowercase, hyphens allowed).

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    name = getattr(spec, "name", None)
    if name is None:
        return  # Already caught by required fields

    if not isinstance(name, str):
        errors.append(ValidationError(
            field="name",
            message="Name must be a string",
            code="invalid_type",
            value=type(name).__name__,
        ))
        return

    if len(name) > 100:
        errors.append(ValidationError(
            field="name",
            message=f"Name must be at most 100 characters, got {len(name)}",
            code="max_length_exceeded",
            value=len(name),
        ))
        return

    if not NAME_PATTERN.match(name):
        errors.append(ValidationError(
            field="name",
            message="Name must be lowercase alphanumeric with hyphens (e.g., 'my-spec-name')",
            code="invalid_format",
            value=name,
        ))


def _validate_task_type(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate the task_type field is one of the allowed values.

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    task_type = getattr(spec, "task_type", None)
    if task_type is None:
        return  # Already caught by required fields

    if not isinstance(task_type, str):
        errors.append(ValidationError(
            field="task_type",
            message="task_type must be a string",
            code="invalid_type",
            value=type(task_type).__name__,
        ))
        return

    if task_type not in VALID_TASK_TYPES:
        errors.append(ValidationError(
            field="task_type",
            message=f"task_type must be one of {sorted(VALID_TASK_TYPES)}, got '{task_type}'",
            code="invalid_enum_value",
            value=task_type,
        ))


def _validate_tool_policy_structure(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate the tool_policy structure.

    Step 3 of Feature #78: Validate tool_policy structure

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    tool_policy = getattr(spec, "tool_policy", None)

    if tool_policy is None:
        return  # Already caught by required fields

    if not isinstance(tool_policy, dict):
        errors.append(ValidationError(
            field="tool_policy",
            message="tool_policy must be a dictionary",
            code="invalid_type",
            value=type(tool_policy).__name__,
        ))
        return

    # Check for allowed_tools field
    allowed_tools = tool_policy.get("allowed_tools")
    if allowed_tools is None:
        errors.append(ValidationError(
            field="tool_policy.allowed_tools",
            message="tool_policy must contain 'allowed_tools' field",
            code="required_field_missing",
        ))
    elif not isinstance(allowed_tools, list):
        errors.append(ValidationError(
            field="tool_policy.allowed_tools",
            message="allowed_tools must be a list",
            code="invalid_type",
            value=type(allowed_tools).__name__,
        ))
    elif len(allowed_tools) == 0:
        errors.append(ValidationError(
            field="tool_policy.allowed_tools",
            message="allowed_tools must contain at least one tool",
            code="min_length",
            value=0,
        ))
    else:
        # Validate each tool name is a string
        for i, tool in enumerate(allowed_tools):
            if not isinstance(tool, str):
                errors.append(ValidationError(
                    field=f"tool_policy.allowed_tools[{i}]",
                    message=f"Tool name at index {i} must be a string, got {type(tool).__name__}",
                    code="invalid_type",
                    value=type(tool).__name__,
                ))
            elif not tool.strip():
                errors.append(ValidationError(
                    field=f"tool_policy.allowed_tools[{i}]",
                    message=f"Tool name at index {i} cannot be empty",
                    code="empty_value",
                ))

    # Validate forbidden_patterns if present
    forbidden_patterns = tool_policy.get("forbidden_patterns")
    if forbidden_patterns is not None:
        if not isinstance(forbidden_patterns, list):
            errors.append(ValidationError(
                field="tool_policy.forbidden_patterns",
                message="forbidden_patterns must be a list",
                code="invalid_type",
                value=type(forbidden_patterns).__name__,
            ))
        else:
            # Validate each pattern is a valid regex
            for i, pattern in enumerate(forbidden_patterns):
                if not isinstance(pattern, str):
                    errors.append(ValidationError(
                        field=f"tool_policy.forbidden_patterns[{i}]",
                        message=f"Pattern at index {i} must be a string",
                        code="invalid_type",
                        value=type(pattern).__name__,
                    ))
                else:
                    try:
                        re.compile(pattern)
                    except re.error as e:
                        errors.append(ValidationError(
                            field=f"tool_policy.forbidden_patterns[{i}]",
                            message=f"Invalid regex pattern at index {i}: {e}",
                            code="invalid_regex",
                            value=pattern,
                        ))

    # Validate tool_hints if present
    tool_hints = tool_policy.get("tool_hints")
    if tool_hints is not None and not isinstance(tool_hints, dict):
        errors.append(ValidationError(
            field="tool_policy.tool_hints",
            message="tool_hints must be a dictionary",
            code="invalid_type",
            value=type(tool_hints).__name__,
        ))


def _validate_budget_constraints(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate budget values are within constraints.

    Step 4 of Feature #78: Validate budget values within constraints

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    # Validate max_turns
    max_turns = getattr(spec, "max_turns", None)
    if max_turns is not None:
        if not isinstance(max_turns, int):
            errors.append(ValidationError(
                field="max_turns",
                message="max_turns must be an integer",
                code="invalid_type",
                value=type(max_turns).__name__,
            ))
        elif max_turns < MIN_MAX_TURNS:
            errors.append(ValidationError(
                field="max_turns",
                message=f"max_turns must be at least {MIN_MAX_TURNS}, got {max_turns}",
                code="min_value",
                value=max_turns,
            ))
        elif max_turns > MAX_MAX_TURNS:
            errors.append(ValidationError(
                field="max_turns",
                message=f"max_turns must be at most {MAX_MAX_TURNS}, got {max_turns}",
                code="max_value",
                value=max_turns,
            ))

    # Validate timeout_seconds
    timeout_seconds = getattr(spec, "timeout_seconds", None)
    if timeout_seconds is not None:
        if not isinstance(timeout_seconds, int):
            errors.append(ValidationError(
                field="timeout_seconds",
                message="timeout_seconds must be an integer",
                code="invalid_type",
                value=type(timeout_seconds).__name__,
            ))
        elif timeout_seconds < MIN_TIMEOUT_SECONDS:
            errors.append(ValidationError(
                field="timeout_seconds",
                message=f"timeout_seconds must be at least {MIN_TIMEOUT_SECONDS}, got {timeout_seconds}",
                code="min_value",
                value=timeout_seconds,
            ))
        elif timeout_seconds > MAX_TIMEOUT_SECONDS:
            errors.append(ValidationError(
                field="timeout_seconds",
                message=f"timeout_seconds must be at most {MAX_TIMEOUT_SECONDS}, got {timeout_seconds}",
                code="max_value",
                value=timeout_seconds,
            ))


def _validate_objective(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate the objective field has sufficient content.

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    objective = getattr(spec, "objective", None)
    if objective is None:
        return  # Already caught by required fields

    if not isinstance(objective, str):
        errors.append(ValidationError(
            field="objective",
            message="objective must be a string",
            code="invalid_type",
            value=type(objective).__name__,
        ))
        return

    if len(objective.strip()) < 10:
        errors.append(ValidationError(
            field="objective",
            message="objective must be at least 10 characters",
            code="min_length",
            value=len(objective.strip()),
        ))

    if len(objective) > 5000:
        errors.append(ValidationError(
            field="objective",
            message=f"objective must be at most 5000 characters, got {len(objective)}",
            code="max_length",
            value=len(objective),
        ))


def _validate_display_name(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate the display_name field.

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    display_name = getattr(spec, "display_name", None)
    if display_name is None:
        return  # Already caught by required fields

    if not isinstance(display_name, str):
        errors.append(ValidationError(
            field="display_name",
            message="display_name must be a string",
            code="invalid_type",
            value=type(display_name).__name__,
        ))
        return

    if len(display_name) > 255:
        errors.append(ValidationError(
            field="display_name",
            message=f"display_name must be at most 255 characters, got {len(display_name)}",
            code="max_length",
            value=len(display_name),
        ))


def _validate_optional_fields(
    spec: "AgentSpec",
    errors: list[ValidationError],
) -> None:
    """
    Validate optional fields if present.

    Args:
        spec: The AgentSpec to validate
        errors: List to append errors to
    """
    # Validate priority if present
    priority = getattr(spec, "priority", None)
    if priority is not None:
        if not isinstance(priority, int):
            errors.append(ValidationError(
                field="priority",
                message="priority must be an integer",
                code="invalid_type",
                value=type(priority).__name__,
            ))
        elif priority < 1 or priority > 9999:
            errors.append(ValidationError(
                field="priority",
                message=f"priority must be between 1 and 9999, got {priority}",
                code="out_of_range",
                value=priority,
            ))

    # Validate icon if present
    icon = getattr(spec, "icon", None)
    if icon is not None and isinstance(icon, str) and len(icon) > 50:
        errors.append(ValidationError(
            field="icon",
            message=f"icon must be at most 50 characters, got {len(icon)}",
            code="max_length",
            value=len(icon),
        ))

    # Validate context if present (should be dict or None)
    context = getattr(spec, "context", None)
    if context is not None and not isinstance(context, dict):
        errors.append(ValidationError(
            field="context",
            message="context must be a dictionary or null",
            code="invalid_type",
            value=type(context).__name__,
        ))

    # Validate tags if present (should be list of strings)
    tags = getattr(spec, "tags", None)
    if tags is not None:
        if not isinstance(tags, list):
            errors.append(ValidationError(
                field="tags",
                message="tags must be a list",
                code="invalid_type",
                value=type(tags).__name__,
            ))
        elif len(tags) > 20:
            errors.append(ValidationError(
                field="tags",
                message=f"tags must have at most 20 items, got {len(tags)}",
                code="max_length",
                value=len(tags),
            ))
        else:
            for i, tag in enumerate(tags):
                if not isinstance(tag, str):
                    errors.append(ValidationError(
                        field=f"tags[{i}]",
                        message=f"Tag at index {i} must be a string",
                        code="invalid_type",
                        value=type(tag).__name__,
                    ))


def validate_spec(spec: "AgentSpec") -> SpecValidationResult:
    """
    Validate an AgentSpec for execution.

    Performs comprehensive validation:
    1. Required fields are present
    2. Name format is valid
    3. Task type is valid
    4. Tool policy structure is valid
    5. Budget values are within constraints
    6. Optional fields are valid if present

    Feature #78 Implementation:
    - Step 1: Validate AgentSpec before kernel execution
    - Step 2: Check required fields are present
    - Step 3: Validate tool_policy structure
    - Step 4: Validate budget values within constraints
    - Step 6: Include validation error details in response

    Args:
        spec: The AgentSpec to validate

    Returns:
        SpecValidationResult with is_valid flag and any errors
    """
    errors: list[ValidationError] = []

    # Get spec identifiers for logging
    spec_id = getattr(spec, "id", None)
    spec_name = getattr(spec, "name", None)

    _logger.debug("Validating AgentSpec: id=%s, name=%s", spec_id, spec_name)

    # Step 2: Check required fields are present
    _validate_required_fields(spec, errors)

    # Validate name format
    _validate_name_format(spec, errors)

    # Validate display_name
    _validate_display_name(spec, errors)

    # Validate objective
    _validate_objective(spec, errors)

    # Validate task_type
    _validate_task_type(spec, errors)

    # Step 3: Validate tool_policy structure
    _validate_tool_policy_structure(spec, errors)

    # Step 4: Validate budget values within constraints
    _validate_budget_constraints(spec, errors)

    # Validate optional fields
    _validate_optional_fields(spec, errors)

    is_valid = len(errors) == 0

    if is_valid:
        _logger.debug("AgentSpec validation passed: id=%s", spec_id)
    else:
        _logger.warning(
            "AgentSpec validation failed: id=%s, errors=%d, first_error=%s",
            spec_id, len(errors), errors[0].message if errors else None
        )

    return SpecValidationResult(
        is_valid=is_valid,
        errors=errors,
        spec_id=spec_id,
        spec_name=spec_name,
    )


def validate_spec_or_raise(spec: "AgentSpec") -> SpecValidationResult:
    """
    Validate an AgentSpec and raise SpecValidationError if invalid.

    Feature #78, Step 5: If invalid, return error without creating run

    Args:
        spec: The AgentSpec to validate

    Returns:
        SpecValidationResult if valid

    Raises:
        SpecValidationError: If validation fails
    """
    result = validate_spec(spec)

    if not result.is_valid:
        raise SpecValidationError(result)

    return result


def validate_spec_dict(spec_dict: dict[str, Any]) -> SpecValidationResult:
    """
    Validate an AgentSpec from a dictionary.

    Useful for validating spec data before creating a model.

    Args:
        spec_dict: Dictionary with spec fields

    Returns:
        SpecValidationResult with is_valid flag and any errors
    """
    # Create a simple object with the dict fields
    class DictSpec:
        def __init__(self, data: dict[str, Any]):
            for key, value in data.items():
                setattr(self, key, value)

    spec_obj = DictSpec(spec_dict)
    return validate_spec(spec_obj)
