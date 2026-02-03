"""
Octo Output Schemas - JSON Schema Validation for Octo Outputs
=============================================================

Feature #188: Octo outputs are strictly typed and schema-validated

This module provides JSON Schema definitions and validation functions to ensure
all Octo outputs are strictly typed and validated before being returned to Maestro.

Schemas Defined:
- AGENT_SPEC_SCHEMA: JSON Schema for AgentSpec objects
- TEST_CONTRACT_SCHEMA: JSON Schema for TestContract objects
- OCTO_RESPONSE_SCHEMA: JSON Schema for OctoResponse objects

Validation Functions:
- validate_agent_spec_schema(): Validate an AgentSpec dict against schema
- validate_test_contract_schema(): Validate a TestContract dict against schema
- validate_octo_response(): Validate complete OctoResponse before returning

Exceptions:
- OctoSchemaValidationError: Raised when schema validation fails
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

@dataclass
class SchemaValidationError:
    """
    A single schema validation error.

    Attributes:
        path: JSON path to the invalid field (e.g., "tool_policy.allowed_tools[0]")
        message: Human-readable error message
        code: Machine-readable error code
        schema_path: Path in the schema that failed
        value: The invalid value (optional, for debugging)
    """
    path: str
    message: str
    code: str
    schema_path: str | None = None
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "path": self.path,
            "message": self.message,
            "code": self.code,
        }
        if self.schema_path:
            result["schema_path"] = self.schema_path
        if self.value is not None:
            # Truncate long values for readability
            str_value = str(self.value)
            result["value"] = str_value[:100] if len(str_value) > 100 else str_value
        return result


@dataclass
class SchemaValidationResult:
    """
    Result of validating data against a JSON schema.

    Attributes:
        is_valid: True if the data passed all schema validations
        errors: List of validation errors (empty if valid)
        schema_name: Name of the schema used for validation
    """
    is_valid: bool
    errors: list[SchemaValidationError] = field(default_factory=list)
    schema_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "schema_name": self.schema_name,
            "error_count": len(self.errors),
        }

    @property
    def error_messages(self) -> list[str]:
        """Get list of error messages."""
        return [f"{e.path}: {e.message}" for e in self.errors]

    @property
    def first_error(self) -> SchemaValidationError | None:
        """Get the first validation error, if any."""
        return self.errors[0] if self.errors else None


class OctoSchemaValidationError(Exception):
    """
    Exception raised when Octo output schema validation fails.

    This exception prevents invalid outputs from propagating to the Materializer.

    Attributes:
        result: The SchemaValidationResult with error details
        output_type: Type of output that failed validation (AgentSpec, TestContract, etc.)
    """

    def __init__(self, result: SchemaValidationResult, output_type: str = "output"):
        self.result = result
        self.output_type = output_type

        # Build a summary message
        if result.errors:
            error_summary = "; ".join(result.error_messages[:5])
            if len(result.errors) > 5:
                error_summary += f" (and {len(result.errors) - 5} more errors)"
            message = f"Octo {output_type} schema validation failed: {error_summary}"
        else:
            message = f"Octo {output_type} schema validation failed"

        super().__init__(message)


# =============================================================================
# Schema Constants
# =============================================================================

# Valid task types (must match api/agentspec_models.py TASK_TYPES)
VALID_TASK_TYPES = frozenset(["coding", "testing", "refactoring", "documentation", "audit", "custom"])

# Valid test types (must match api/octo.py TEST_TYPES)
VALID_TEST_TYPES = frozenset([
    "unit", "integration", "e2e", "api", "performance", "security", "smoke", "regression"
])

# Valid gate modes (must match api/agentspec_models.py GATE_MODE)
VALID_GATE_MODES = frozenset(["all_pass", "any_pass", "weighted"])

# Valid assertion operators
VALID_ASSERTION_OPERATORS = frozenset([
    "eq", "ne", "gt", "lt", "ge", "le", "contains", "matches", "exists"
])

# Name pattern (lowercase, hyphens allowed)
NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$')

# Budget constraints
MIN_MAX_TURNS = 1
MAX_MAX_TURNS = 500
MIN_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 7200

# TestContract priority range
MIN_PRIORITY = 1
MAX_PRIORITY = 4


# =============================================================================
# AgentSpec JSON Schema Definition
# =============================================================================

AGENT_SPEC_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://autobuildr.dev/schemas/agent-spec.json",
    "title": "AgentSpec",
    "description": "Schema for AgentSpec objects generated by Octo",
    "type": "object",
    "required": ["name", "display_name", "objective", "task_type", "tool_policy"],
    "properties": {
        "id": {
            "type": "string",
            "format": "uuid",
            "description": "Unique identifier for the AgentSpec"
        },
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "pattern": r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$",
            "description": "Machine-friendly name (lowercase, hyphens allowed)"
        },
        "display_name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 255,
            "description": "Human-friendly display name"
        },
        "icon": {
            "type": ["string", "null"],
            "maxLength": 50,
            "description": "Emoji or icon identifier"
        },
        "spec_version": {
            "type": "string",
            "default": "v1",
            "description": "Version string for forward compatibility"
        },
        "objective": {
            "type": "string",
            "minLength": 10,
            "maxLength": 5000,
            "description": "Clear goal statement for the agent"
        },
        "task_type": {
            "type": "string",
            "enum": list(VALID_TASK_TYPES),
            "description": "Type of task the agent performs"
        },
        "context": {
            "type": ["object", "null"],
            "description": "Task-specific context (feature_id, file_paths, etc.)"
        },
        "tool_policy": {
            "type": "object",
            "required": ["allowed_tools"],
            "properties": {
                "policy_version": {
                    "type": "string",
                    "default": "v1"
                },
                "allowed_tools": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "string",
                        "minLength": 1
                    },
                    "description": "List of MCP tool names the agent can use"
                },
                "forbidden_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Regex patterns to block in tool arguments"
                },
                "tool_hints": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Hints for tool usage"
                }
            },
            "description": "Tool access policy for the agent"
        },
        "max_turns": {
            "type": "integer",
            "minimum": MIN_MAX_TURNS,
            "maximum": MAX_MAX_TURNS,
            "default": 50,
            "description": "Maximum API round-trips"
        },
        "timeout_seconds": {
            "type": "integer",
            "minimum": MIN_TIMEOUT_SECONDS,
            "maximum": MAX_TIMEOUT_SECONDS,
            "default": 1800,
            "description": "Maximum execution time in seconds"
        },
        "priority": {
            "type": "integer",
            "minimum": 1,
            "maximum": 9999,
            "default": 500,
            "description": "Execution priority (lower = higher priority)"
        },
        "tags": {
            "type": ["array", "null"],
            "maxItems": 20,
            "items": {"type": "string"},
            "description": "Tags for categorization"
        }
    }
}


# =============================================================================
# TestContract JSON Schema Definition
# =============================================================================

TEST_CONTRACT_ASSERTION_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://autobuildr.dev/schemas/test-contract-assertion.json",
    "title": "TestContractAssertion",
    "description": "Schema for a single assertion within a TestContract",
    "type": "object",
    "required": ["description", "target", "expected"],
    "properties": {
        "description": {
            "type": "string",
            "minLength": 1,
            "description": "Human-readable description of the assertion"
        },
        "target": {
            "type": "string",
            "minLength": 1,
            "description": "What is being tested (e.g., 'response.status_code')"
        },
        "expected": {
            "description": "Expected value or condition"
        },
        "operator": {
            "type": "string",
            "enum": list(VALID_ASSERTION_OPERATORS),
            "default": "eq",
            "description": "Comparison operator"
        }
    }
}


TEST_CONTRACT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://autobuildr.dev/schemas/test-contract.json",
    "title": "TestContract",
    "description": "Schema for TestContract objects generated by Octo",
    "type": "object",
    "required": ["agent_name", "test_type"],
    "properties": {
        "contract_id": {
            "type": "string",
            "format": "uuid",
            "description": "Unique identifier for the TestContract"
        },
        "agent_name": {
            "type": "string",
            "minLength": 1,
            "description": "Name of the agent this contract is linked to"
        },
        "test_type": {
            "type": "string",
            "enum": list(VALID_TEST_TYPES),
            "description": "Type of testing"
        },
        "assertions": {
            "type": "array",
            "items": TEST_CONTRACT_ASSERTION_SCHEMA,
            "description": "List of assertions that must hold true"
        },
        "pass_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Conditions that determine test success"
        },
        "fail_criteria": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Conditions that indicate test failure"
        },
        "description": {
            "type": "string",
            "description": "Human-readable description of what is being tested"
        },
        "priority": {
            "type": "integer",
            "minimum": MIN_PRIORITY,
            "maximum": MAX_PRIORITY,
            "default": 3,
            "description": "Priority level (1=critical, 2=high, 3=medium, 4=low)"
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tags for categorization"
        }
    },
    "allOf": [
        {
            "anyOf": [
                {
                    "properties": {"assertions": {"minItems": 1}}
                },
                {
                    "properties": {"pass_criteria": {"minItems": 1}}
                }
            ]
        }
    ]
}


# =============================================================================
# Validation Functions
# =============================================================================

def _validate_string_field(
    value: Any,
    field_name: str,
    path: str,
    errors: list[SchemaValidationError],
    *,
    min_length: int | None = None,
    max_length: int | None = None,
    pattern: re.Pattern | None = None,
    enum_values: frozenset[str] | None = None,
) -> bool:
    """
    Validate a string field against constraints.

    Returns True if valid, False otherwise.
    """
    if value is None:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Required field '{field_name}' is missing",
            code="required_field_missing",
        ))
        return False

    if not isinstance(value, str):
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be a string, got {type(value).__name__}",
            code="invalid_type",
            value=type(value).__name__,
        ))
        return False

    if min_length is not None and len(value) < min_length:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be at least {min_length} characters, got {len(value)}",
            code="min_length",
            value=len(value),
        ))
        return False

    if max_length is not None and len(value) > max_length:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be at most {max_length} characters, got {len(value)}",
            code="max_length",
            value=len(value),
        ))
        return False

    if pattern is not None and not pattern.match(value):
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' does not match required pattern",
            code="pattern_mismatch",
            value=value,
        ))
        return False

    if enum_values is not None and value not in enum_values:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be one of {sorted(enum_values)}, got '{value}'",
            code="invalid_enum",
            value=value,
        ))
        return False

    return True


def _validate_integer_field(
    value: Any,
    field_name: str,
    path: str,
    errors: list[SchemaValidationError],
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> bool:
    """
    Validate an integer field against constraints.

    Returns True if valid, False otherwise.
    """
    if value is None:
        return True  # Optional field

    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be an integer, got {type(value).__name__}",
            code="invalid_type",
            value=type(value).__name__,
        ))
        return False

    if minimum is not None and value < minimum:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be at least {minimum}, got {value}",
            code="min_value",
            value=value,
        ))
        return False

    if maximum is not None and value > maximum:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be at most {maximum}, got {value}",
            code="max_value",
            value=value,
        ))
        return False

    return True


def _validate_array_field(
    value: Any,
    field_name: str,
    path: str,
    errors: list[SchemaValidationError],
    *,
    min_items: int | None = None,
    max_items: int | None = None,
    item_type: type | None = None,
) -> bool:
    """
    Validate an array field against constraints.

    Returns True if valid, False otherwise.
    """
    if value is None:
        return True  # Optional field

    if not isinstance(value, list):
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must be an array, got {type(value).__name__}",
            code="invalid_type",
            value=type(value).__name__,
        ))
        return False

    if min_items is not None and len(value) < min_items:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must have at least {min_items} items, got {len(value)}",
            code="min_items",
            value=len(value),
        ))
        return False

    if max_items is not None and len(value) > max_items:
        errors.append(SchemaValidationError(
            path=path,
            message=f"Field '{field_name}' must have at most {max_items} items, got {len(value)}",
            code="max_items",
            value=len(value),
        ))
        return False

    if item_type is not None:
        for i, item in enumerate(value):
            if not isinstance(item, item_type):
                errors.append(SchemaValidationError(
                    path=f"{path}[{i}]",
                    message=f"Item at index {i} must be {item_type.__name__}, got {type(item).__name__}",
                    code="invalid_item_type",
                    value=type(item).__name__,
                ))

    return True


def validate_agent_spec_schema(data: dict[str, Any]) -> SchemaValidationResult:
    """
    Validate an AgentSpec dictionary against the JSON schema.

    This function performs comprehensive validation of all AgentSpec fields
    to ensure the output is strictly typed and valid before being returned
    to Maestro or the Materializer.

    Feature #188, Step 1: Define AgentSpec JSON schema with required fields

    Args:
        data: Dictionary representation of an AgentSpec

    Returns:
        SchemaValidationResult with is_valid flag and any errors
    """
    errors: list[SchemaValidationError] = []

    if not isinstance(data, dict):
        return SchemaValidationResult(
            is_valid=False,
            errors=[SchemaValidationError(
                path="$",
                message="AgentSpec must be a dictionary",
                code="invalid_type",
                value=type(data).__name__,
            )],
            schema_name="AgentSpec",
        )

    # Required fields
    _validate_string_field(
        data.get("name"),
        "name",
        "name",
        errors,
        min_length=1,
        max_length=100,
        pattern=NAME_PATTERN,
    )

    _validate_string_field(
        data.get("display_name"),
        "display_name",
        "display_name",
        errors,
        min_length=1,
        max_length=255,
    )

    _validate_string_field(
        data.get("objective"),
        "objective",
        "objective",
        errors,
        min_length=10,
        max_length=5000,
    )

    _validate_string_field(
        data.get("task_type"),
        "task_type",
        "task_type",
        errors,
        enum_values=VALID_TASK_TYPES,
    )

    # Tool policy validation (required and complex)
    tool_policy = data.get("tool_policy")
    if tool_policy is None:
        errors.append(SchemaValidationError(
            path="tool_policy",
            message="Required field 'tool_policy' is missing",
            code="required_field_missing",
        ))
    elif not isinstance(tool_policy, dict):
        errors.append(SchemaValidationError(
            path="tool_policy",
            message="Field 'tool_policy' must be an object",
            code="invalid_type",
            value=type(tool_policy).__name__,
        ))
    else:
        # Validate allowed_tools
        allowed_tools = tool_policy.get("allowed_tools")
        if allowed_tools is None:
            errors.append(SchemaValidationError(
                path="tool_policy.allowed_tools",
                message="Required field 'allowed_tools' is missing from tool_policy",
                code="required_field_missing",
            ))
        elif not isinstance(allowed_tools, list):
            errors.append(SchemaValidationError(
                path="tool_policy.allowed_tools",
                message="Field 'allowed_tools' must be an array",
                code="invalid_type",
                value=type(allowed_tools).__name__,
            ))
        elif len(allowed_tools) == 0:
            errors.append(SchemaValidationError(
                path="tool_policy.allowed_tools",
                message="Field 'allowed_tools' must have at least 1 item",
                code="min_items",
                value=0,
            ))
        else:
            for i, tool in enumerate(allowed_tools):
                if not isinstance(tool, str) or not tool.strip():
                    errors.append(SchemaValidationError(
                        path=f"tool_policy.allowed_tools[{i}]",
                        message=f"Tool at index {i} must be a non-empty string",
                        code="invalid_item",
                        value=tool,
                    ))

        # Validate forbidden_patterns (optional)
        forbidden_patterns = tool_policy.get("forbidden_patterns")
        if forbidden_patterns is not None:
            _validate_array_field(
                forbidden_patterns,
                "forbidden_patterns",
                "tool_policy.forbidden_patterns",
                errors,
                item_type=str,
            )
            # Validate regex patterns
            if isinstance(forbidden_patterns, list):
                for i, pattern in enumerate(forbidden_patterns):
                    if isinstance(pattern, str):
                        try:
                            re.compile(pattern)
                        except re.error as e:
                            errors.append(SchemaValidationError(
                                path=f"tool_policy.forbidden_patterns[{i}]",
                                message=f"Invalid regex pattern: {e}",
                                code="invalid_regex",
                                value=pattern,
                            ))

        # Validate tool_hints (optional)
        tool_hints = tool_policy.get("tool_hints")
        if tool_hints is not None and not isinstance(tool_hints, dict):
            errors.append(SchemaValidationError(
                path="tool_policy.tool_hints",
                message="Field 'tool_hints' must be an object",
                code="invalid_type",
                value=type(tool_hints).__name__,
            ))

    # Optional fields with constraints
    _validate_integer_field(
        data.get("max_turns"),
        "max_turns",
        "max_turns",
        errors,
        minimum=MIN_MAX_TURNS,
        maximum=MAX_MAX_TURNS,
    )

    _validate_integer_field(
        data.get("timeout_seconds"),
        "timeout_seconds",
        "timeout_seconds",
        errors,
        minimum=MIN_TIMEOUT_SECONDS,
        maximum=MAX_TIMEOUT_SECONDS,
    )

    _validate_integer_field(
        data.get("priority"),
        "priority",
        "priority",
        errors,
        minimum=1,
        maximum=9999,
    )

    _validate_array_field(
        data.get("tags"),
        "tags",
        "tags",
        errors,
        max_items=20,
        item_type=str,
    )

    # Context must be dict or null
    context = data.get("context")
    if context is not None and not isinstance(context, dict):
        errors.append(SchemaValidationError(
            path="context",
            message="Field 'context' must be an object or null",
            code="invalid_type",
            value=type(context).__name__,
        ))

    is_valid = len(errors) == 0

    if is_valid:
        _logger.debug("AgentSpec schema validation passed for: %s", data.get("name"))
    else:
        _logger.warning(
            "AgentSpec schema validation failed: %d errors, first=%s",
            len(errors),
            errors[0].message if errors else None,
        )

    return SchemaValidationResult(
        is_valid=is_valid,
        errors=errors,
        schema_name="AgentSpec",
    )


def validate_test_contract_schema(data: dict[str, Any]) -> SchemaValidationResult:
    """
    Validate a TestContract dictionary against the JSON schema.

    Feature #188, Step 2: Define TestContract JSON schema

    Args:
        data: Dictionary representation of a TestContract

    Returns:
        SchemaValidationResult with is_valid flag and any errors
    """
    errors: list[SchemaValidationError] = []

    if not isinstance(data, dict):
        return SchemaValidationResult(
            is_valid=False,
            errors=[SchemaValidationError(
                path="$",
                message="TestContract must be a dictionary",
                code="invalid_type",
                value=type(data).__name__,
            )],
            schema_name="TestContract",
        )

    # Required fields
    _validate_string_field(
        data.get("agent_name"),
        "agent_name",
        "agent_name",
        errors,
        min_length=1,
    )

    _validate_string_field(
        data.get("test_type"),
        "test_type",
        "test_type",
        errors,
        enum_values=VALID_TEST_TYPES,
    )

    # At least one of assertions or pass_criteria required
    assertions = data.get("assertions", [])
    pass_criteria = data.get("pass_criteria", [])

    if not assertions and not pass_criteria:
        errors.append(SchemaValidationError(
            path="$",
            message="TestContract must have either assertions or pass_criteria",
            code="missing_required_oneOf",
        ))

    # Validate assertions array
    if assertions:
        if not isinstance(assertions, list):
            errors.append(SchemaValidationError(
                path="assertions",
                message="Field 'assertions' must be an array",
                code="invalid_type",
                value=type(assertions).__name__,
            ))
        else:
            for i, assertion in enumerate(assertions):
                _validate_assertion(assertion, f"assertions[{i}]", errors)

    # Validate pass_criteria
    _validate_array_field(
        pass_criteria,
        "pass_criteria",
        "pass_criteria",
        errors,
        item_type=str,
    )

    # Validate fail_criteria (optional)
    _validate_array_field(
        data.get("fail_criteria"),
        "fail_criteria",
        "fail_criteria",
        errors,
        item_type=str,
    )

    # Validate priority
    _validate_integer_field(
        data.get("priority"),
        "priority",
        "priority",
        errors,
        minimum=MIN_PRIORITY,
        maximum=MAX_PRIORITY,
    )

    # Validate tags
    _validate_array_field(
        data.get("tags"),
        "tags",
        "tags",
        errors,
        item_type=str,
    )

    is_valid = len(errors) == 0

    if is_valid:
        _logger.debug("TestContract schema validation passed for agent: %s", data.get("agent_name"))
    else:
        _logger.warning(
            "TestContract schema validation failed: %d errors, first=%s",
            len(errors),
            errors[0].message if errors else None,
        )

    return SchemaValidationResult(
        is_valid=is_valid,
        errors=errors,
        schema_name="TestContract",
    )


def _validate_assertion(
    assertion: Any,
    path: str,
    errors: list[SchemaValidationError],
) -> None:
    """Validate a single TestContractAssertion."""
    if not isinstance(assertion, dict):
        errors.append(SchemaValidationError(
            path=path,
            message="Assertion must be an object",
            code="invalid_type",
            value=type(assertion).__name__,
        ))
        return

    _validate_string_field(
        assertion.get("description"),
        "description",
        f"{path}.description",
        errors,
        min_length=1,
    )

    _validate_string_field(
        assertion.get("target"),
        "target",
        f"{path}.target",
        errors,
        min_length=1,
    )

    if "expected" not in assertion:
        errors.append(SchemaValidationError(
            path=f"{path}.expected",
            message="Required field 'expected' is missing from assertion",
            code="required_field_missing",
        ))

    # Validate operator if present
    operator = assertion.get("operator")
    if operator is not None:
        _validate_string_field(
            operator,
            "operator",
            f"{path}.operator",
            errors,
            enum_values=VALID_ASSERTION_OPERATORS,
        )


def validate_agent_spec_schema_or_raise(data: dict[str, Any]) -> SchemaValidationResult:
    """
    Validate an AgentSpec and raise OctoSchemaValidationError if invalid.

    Feature #188, Step 4: Schema validation errors raise exceptions with details

    Args:
        data: Dictionary representation of an AgentSpec

    Returns:
        SchemaValidationResult if valid

    Raises:
        OctoSchemaValidationError: If schema validation fails
    """
    result = validate_agent_spec_schema(data)

    if not result.is_valid:
        raise OctoSchemaValidationError(result, "AgentSpec")

    return result


def validate_test_contract_schema_or_raise(data: dict[str, Any]) -> SchemaValidationResult:
    """
    Validate a TestContract and raise OctoSchemaValidationError if invalid.

    Feature #188, Step 4: Schema validation errors raise exceptions with details

    Args:
        data: Dictionary representation of a TestContract

    Returns:
        SchemaValidationResult if valid

    Raises:
        OctoSchemaValidationError: If schema validation fails
    """
    result = validate_test_contract_schema(data)

    if not result.is_valid:
        raise OctoSchemaValidationError(result, "TestContract")

    return result


def validate_octo_outputs(
    agent_specs: list[dict[str, Any]],
    test_contracts: list[dict[str, Any]] | None = None,
    *,
    raise_on_error: bool = True,
) -> tuple[list[SchemaValidationResult], list[SchemaValidationResult]]:
    """
    Validate all Octo outputs before returning to Maestro.

    Feature #188, Step 3: Octo validates output against schemas before returning
    Feature #188, Step 5: Invalid outputs never propagate to Materializer

    This function validates all AgentSpecs and TestContracts generated by Octo
    to ensure they conform to their respective schemas.

    Args:
        agent_specs: List of AgentSpec dictionaries to validate
        test_contracts: Optional list of TestContract dictionaries to validate
        raise_on_error: If True, raises OctoSchemaValidationError on first invalid output

    Returns:
        Tuple of (spec_results, contract_results) - lists of validation results

    Raises:
        OctoSchemaValidationError: If raise_on_error=True and any output is invalid
    """
    spec_results: list[SchemaValidationResult] = []
    contract_results: list[SchemaValidationResult] = []

    # Validate all AgentSpecs
    for i, spec_data in enumerate(agent_specs):
        result = validate_agent_spec_schema(spec_data)
        spec_results.append(result)

        if not result.is_valid and raise_on_error:
            _logger.error(
                "AgentSpec[%d] failed schema validation: %s",
                i,
                result.error_messages[:3],
            )
            raise OctoSchemaValidationError(result, f"AgentSpec[{i}]")

    # Validate all TestContracts
    if test_contracts:
        for i, contract_data in enumerate(test_contracts):
            result = validate_test_contract_schema(contract_data)
            contract_results.append(result)

            if not result.is_valid and raise_on_error:
                _logger.error(
                    "TestContract[%d] failed schema validation: %s",
                    i,
                    result.error_messages[:3],
                )
                raise OctoSchemaValidationError(result, f"TestContract[{i}]")

    return spec_results, contract_results


def get_schema(schema_name: str) -> dict[str, Any]:
    """
    Get a schema definition by name.

    Args:
        schema_name: Name of the schema ("AgentSpec", "TestContract", "TestContractAssertion")

    Returns:
        The schema dictionary

    Raises:
        ValueError: If schema_name is not recognized
    """
    schemas = {
        "AgentSpec": AGENT_SPEC_SCHEMA,
        "TestContract": TEST_CONTRACT_SCHEMA,
        "TestContractAssertion": TEST_CONTRACT_ASSERTION_SCHEMA,
    }

    if schema_name not in schemas:
        raise ValueError(f"Unknown schema: {schema_name}. Valid schemas: {list(schemas.keys())}")

    return schemas[schema_name]
