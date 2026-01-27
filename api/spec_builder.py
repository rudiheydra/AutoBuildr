"""
DSPy SpecBuilder Module
=======================

This module provides the SpecBuilder class that wraps DSPy module for
generating AgentSpecs from task descriptions.

Feature #54: DSPy Module Execution for Spec Generation

The SpecBuilder:
1. Wraps DSPy module with the SpecGenerationSignature
2. Initializes DSPy with Claude backend
3. Executes the signature with task inputs
4. Parses and validates JSON output fields
5. Creates AgentSpec and AcceptanceSpec from validated output
6. Handles errors gracefully with detailed error information

Example usage:
    ```python
    from api.spec_builder import SpecBuilder, get_spec_builder

    # Using the singleton builder
    builder = get_spec_builder()
    result = builder.build(
        task_description="Implement user authentication with OAuth2",
        task_type="coding",
        context={"project_name": "MyApp", "feature_id": 42}
    )

    if result.success:
        spec = result.agent_spec
        acceptance = result.acceptance_spec
    else:
        print(f"Error: {result.error}")
    ```
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any

import dspy

from api.agentspec_models import (
    AcceptanceSpec,
    AgentSpec,
    GATE_MODE,
    RETRY_POLICY,
    TASK_TYPES,
    VALIDATOR_TYPES,
    create_tool_policy,
    create_validator,
    generate_uuid,
)
from api.dspy_signatures import (
    DEFAULT_BUDGETS,
    SpecGenerationSignature,
    VALID_TASK_TYPES,
    validate_spec_output,
)
from api.spec_name_generator import generate_spec_name

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Environment variable for Anthropic API key
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"

# Default model to use
DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

# Model options
AVAILABLE_MODELS = [
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-3-5-sonnet-20241022",
    "anthropic/claude-3-haiku-20240307",
]

# Minimum / Maximum budget values
MIN_MAX_TURNS = 1
MAX_MAX_TURNS = 500
MIN_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 7200

# Required fields in tool_policy
TOOL_POLICY_REQUIRED_FIELDS = {"allowed_tools"}

# Required fields in validator objects
VALIDATOR_REQUIRED_FIELDS = {"type"}


# =============================================================================
# Exceptions
# =============================================================================

class SpecBuilderError(Exception):
    """Base exception for SpecBuilder errors."""
    pass


class DSPyInitializationError(SpecBuilderError):
    """Raised when DSPy fails to initialize."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


class DSPyExecutionError(SpecBuilderError):
    """Raised when DSPy execution fails."""

    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message)


class OutputValidationError(SpecBuilderError):
    """Raised when DSPy output validation fails."""

    def __init__(self, message: str, validation_errors: list[str] | None = None):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class ToolPolicyValidationError(OutputValidationError):
    """Raised when tool_policy structure is invalid."""
    pass


class ValidatorsValidationError(OutputValidationError):
    """Raised when validators structure is invalid."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BuildResult:
    """
    Result of a spec build operation.

    Attributes:
        success: Whether the build succeeded
        agent_spec: The generated AgentSpec (if successful)
        acceptance_spec: The generated AcceptanceSpec (if successful)
        error: Error message (if failed)
        error_type: Type of error (if failed)
        validation_errors: List of validation errors (if any)
        warnings: List of warnings (non-fatal issues)
        raw_output: Raw DSPy output (for debugging)
    """
    success: bool
    agent_spec: AgentSpec | None = None
    acceptance_spec: AcceptanceSpec | None = None
    error: str | None = None
    error_type: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_output: dict[str, Any] | None = None


@dataclass
class ParsedOutput:
    """
    Parsed and validated output from DSPy execution.

    Intermediate representation before creating AgentSpec.
    """
    reasoning: str
    objective: str
    context: dict[str, Any]
    tool_policy: dict[str, Any]
    max_turns: int
    timeout_seconds: int
    validators: list[dict[str, Any]]


# =============================================================================
# Validation Functions
# =============================================================================

def validate_tool_policy(policy: dict[str, Any]) -> list[str]:
    """
    Validate the structure of a tool_policy dictionary.

    Args:
        policy: The tool_policy dictionary to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Check required fields
    for field_name in TOOL_POLICY_REQUIRED_FIELDS:
        if field_name not in policy:
            errors.append(f"tool_policy missing required field: {field_name}")

    # Validate allowed_tools
    allowed_tools = policy.get("allowed_tools")
    if allowed_tools is not None:
        if not isinstance(allowed_tools, list):
            errors.append("tool_policy.allowed_tools must be an array")
        else:
            for i, tool in enumerate(allowed_tools):
                if not isinstance(tool, str):
                    errors.append(f"tool_policy.allowed_tools[{i}] must be a string")
                elif not tool.strip():
                    errors.append(f"tool_policy.allowed_tools[{i}] cannot be empty")

    # Validate forbidden_patterns (optional)
    forbidden_patterns = policy.get("forbidden_patterns")
    if forbidden_patterns is not None:
        if not isinstance(forbidden_patterns, list):
            errors.append("tool_policy.forbidden_patterns must be an array")
        else:
            for i, pattern in enumerate(forbidden_patterns):
                if not isinstance(pattern, str):
                    errors.append(f"tool_policy.forbidden_patterns[{i}] must be a string")
                else:
                    # Try to compile as regex
                    try:
                        re.compile(pattern)
                    except re.error as e:
                        errors.append(
                            f"tool_policy.forbidden_patterns[{i}] is not a valid regex: {e}"
                        )

    # Validate tool_hints (optional)
    tool_hints = policy.get("tool_hints")
    if tool_hints is not None:
        if not isinstance(tool_hints, dict):
            errors.append("tool_policy.tool_hints must be an object")
        else:
            for key, value in tool_hints.items():
                if not isinstance(key, str):
                    errors.append(f"tool_policy.tool_hints key must be string, got: {type(key)}")
                if not isinstance(value, str):
                    errors.append(f"tool_policy.tool_hints[{key}] must be a string")

    # Validate policy_version (optional but should be v1)
    policy_version = policy.get("policy_version")
    if policy_version is not None and policy_version != "v1":
        errors.append(f"tool_policy.policy_version must be 'v1', got: {policy_version}")

    return errors


def validate_validators(validators: list[dict[str, Any]]) -> list[str]:
    """
    Validate the structure of a validators array.

    Args:
        validators: The validators array to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    if not isinstance(validators, list):
        errors.append("validators must be an array")
        return errors

    for i, validator in enumerate(validators):
        prefix = f"validators[{i}]"

        if not isinstance(validator, dict):
            errors.append(f"{prefix} must be an object")
            continue

        # Check required fields
        for field_name in VALIDATOR_REQUIRED_FIELDS:
            if field_name not in validator:
                errors.append(f"{prefix} missing required field: {field_name}")

        # Validate type
        validator_type = validator.get("type")
        if validator_type is not None:
            if not isinstance(validator_type, str):
                errors.append(f"{prefix}.type must be a string")
            elif validator_type not in VALIDATOR_TYPES:
                errors.append(
                    f"{prefix}.type must be one of {VALIDATOR_TYPES}, got: {validator_type}"
                )

        # Validate config (optional but should be dict)
        config = validator.get("config")
        if config is not None and not isinstance(config, dict):
            errors.append(f"{prefix}.config must be an object")

        # Validate weight (optional, should be float 0-1)
        weight = validator.get("weight")
        if weight is not None:
            if not isinstance(weight, (int, float)):
                errors.append(f"{prefix}.weight must be a number")
            elif weight < 0 or weight > 1:
                errors.append(f"{prefix}.weight must be between 0 and 1")

        # Validate required (optional, should be bool)
        required = validator.get("required")
        if required is not None and not isinstance(required, bool):
            errors.append(f"{prefix}.required must be a boolean")

    return errors


def parse_json_field(field_name: str, value: str) -> tuple[Any, str | None]:
    """
    Parse a JSON string field, handling both raw JSON and markdown-wrapped JSON.

    Args:
        field_name: Name of the field (for error messages)
        value: The JSON string to parse

    Returns:
        Tuple of (parsed_value, error_message)
        error_message is None if parsing succeeded
    """
    if not value:
        return None, f"{field_name} is empty"

    # Strip whitespace
    value = value.strip()

    # Try direct parse first
    try:
        return json.loads(value), None
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code block
    # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
    patterns = [
        r'```json\s*\n([\s\S]*?)\n```',
        r'```\s*\n([\s\S]*?)\n```',
        r'`([\s\S]*?)`',
    ]

    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            try:
                return json.loads(match.group(1)), None
            except json.JSONDecodeError:
                continue

    # Final attempt: find JSON-like content between { } or [ ]
    json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', value)
    if json_match:
        try:
            return json.loads(json_match.group(1)), None
        except json.JSONDecodeError as e:
            return None, f"{field_name} contains invalid JSON: {e}"

    return None, f"{field_name} could not be parsed as JSON"


def coerce_integer(field_name: str, value: Any, min_val: int, max_val: int) -> tuple[int, str | None]:
    """
    Coerce a value to an integer within bounds.

    Args:
        field_name: Name of the field (for error messages)
        value: The value to coerce
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Tuple of (integer_value, error_message)
        error_message is None if coercion succeeded
    """
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            return 0, f"{field_name} must be an integer, got: {value}"
    else:
        return 0, f"{field_name} must be an integer, got type: {type(value)}"

    # Clamp to bounds
    if result < min_val:
        result = min_val
    elif result > max_val:
        result = max_val

    return result, None


# =============================================================================
# SpecBuilder Class
# =============================================================================

class SpecBuilder:
    """
    Wrapper around DSPy module for generating AgentSpecs from task descriptions.

    The SpecBuilder encapsulates:
    - DSPy initialization with Claude backend
    - Execution of the SpecGenerationSignature
    - Parsing and validation of JSON outputs
    - Creation of AgentSpec and AcceptanceSpec objects
    - Error handling and recovery

    Thread-safe for concurrent build operations.

    Example:
        ```python
        builder = SpecBuilder()
        result = builder.build(
            task_description="Add user authentication",
            task_type="coding",
            context={"project_name": "MyApp"}
        )
        if result.success:
            print(f"Created spec: {result.agent_spec.name}")
        ```
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        use_chain_of_thought: bool = True,
        auto_initialize: bool = True,
    ):
        """
        Initialize the SpecBuilder.

        Args:
            model: Model to use (default: anthropic/claude-sonnet)
            api_key: Anthropic API key (default: from environment)
            use_chain_of_thought: If True, use ChainOfThought module
            auto_initialize: If True, initialize DSPy on construction

        Raises:
            DSPyInitializationError: If auto_initialize=True and initialization fails
        """
        self._model = model or DEFAULT_MODEL
        self._api_key = api_key or os.environ.get(ANTHROPIC_API_KEY_ENV)
        self._use_chain_of_thought = use_chain_of_thought

        # Thread safety
        self._lock = threading.RLock()

        # State
        self._initialized = False
        self._dspy_module: dspy.Module | None = None
        self._lm: dspy.LM | None = None

        if auto_initialize:
            self._initialize_dspy()

    @property
    def is_initialized(self) -> bool:
        """Check if DSPy has been initialized."""
        return self._initialized

    @property
    def model(self) -> str:
        """Get the model being used."""
        return self._model

    def _initialize_dspy(self) -> None:
        """
        Initialize DSPy with Claude backend.

        Raises:
            DSPyInitializationError: If initialization fails
        """
        with self._lock:
            if self._initialized:
                return

            if not self._api_key:
                raise DSPyInitializationError(
                    f"Anthropic API key not found. Set {ANTHROPIC_API_KEY_ENV} environment variable."
                )

            try:
                # Create language model
                self._lm = dspy.LM(
                    self._model,
                    api_key=self._api_key,
                )

                # Configure DSPy
                dspy.configure(lm=self._lm)

                # Create the module
                if self._use_chain_of_thought:
                    self._dspy_module = dspy.ChainOfThought(SpecGenerationSignature)
                else:
                    self._dspy_module = dspy.Predict(SpecGenerationSignature)

                self._initialized = True
                _logger.info("SpecBuilder initialized with model: %s", self._model)

            except Exception as e:
                self._initialized = False
                raise DSPyInitializationError(
                    f"Failed to initialize DSPy: {e}",
                    original_error=e
                ) from e

    def build(
        self,
        task_description: str,
        task_type: str,
        context: dict[str, Any] | None = None,
        *,
        spec_id: str | None = None,
        source_feature_id: int | None = None,
    ) -> BuildResult:
        """
        Build an AgentSpec from a task description.

        This is the main entry point for spec generation. It:
        1. Validates inputs
        2. Executes DSPy signature
        3. Parses JSON output fields
        4. Validates tool_policy and validators structures
        5. Creates AgentSpec and AcceptanceSpec
        6. Returns a BuildResult with success/error info

        Args:
            task_description: Natural language description of the task
            task_type: Type of task (coding, testing, documentation, etc.)
            context: Optional context dictionary (project info, file paths, etc.)
            spec_id: Optional ID for the spec (generates UUID if not provided)
            source_feature_id: Optional feature ID this spec is derived from

        Returns:
            BuildResult containing the generated spec or error information
        """
        warnings: list[str] = []

        # Step 1: Validate inputs
        if not task_description or not task_description.strip():
            return BuildResult(
                success=False,
                error="task_description cannot be empty",
                error_type="input_validation",
            )

        task_type = task_type.lower()
        if task_type not in VALID_TASK_TYPES:
            return BuildResult(
                success=False,
                error=f"task_type must be one of {sorted(VALID_TASK_TYPES)}, got: {task_type}",
                error_type="input_validation",
            )

        # Serialize context to JSON
        context = context or {}
        try:
            context_json = json.dumps(context)
        except (TypeError, ValueError) as e:
            return BuildResult(
                success=False,
                error=f"context must be JSON-serializable: {e}",
                error_type="input_validation",
            )

        # Step 2: Ensure DSPy is initialized
        try:
            self._initialize_dspy()
        except DSPyInitializationError as e:
            return BuildResult(
                success=False,
                error=str(e),
                error_type="initialization",
            )

        # Step 3: Execute DSPy signature
        try:
            result = self._execute_dspy(task_description, task_type, context_json)
        except DSPyExecutionError as e:
            return BuildResult(
                success=False,
                error=str(e),
                error_type="execution",
            )

        # Step 4: Validate basic output structure
        validation = validate_spec_output(result)
        if validation["errors"]:
            return BuildResult(
                success=False,
                error="DSPy output validation failed",
                error_type="output_validation",
                validation_errors=validation["errors"],
                warnings=validation["warnings"],
                raw_output=self._result_to_dict(result),
            )
        warnings.extend(validation["warnings"])

        # Step 5: Parse JSON output fields
        try:
            parsed = self._parse_output(result)
        except OutputValidationError as e:
            return BuildResult(
                success=False,
                error=str(e),
                error_type="parse_error",
                validation_errors=e.validation_errors,
                warnings=warnings,
                raw_output=self._result_to_dict(result),
            )

        # Step 6: Validate tool_policy structure
        policy_errors = validate_tool_policy(parsed.tool_policy)
        if policy_errors:
            return BuildResult(
                success=False,
                error="Invalid tool_policy structure",
                error_type="tool_policy_validation",
                validation_errors=policy_errors,
                warnings=warnings,
                raw_output=self._result_to_dict(result),
            )

        # Step 7: Validate validators structure
        validator_errors = validate_validators(parsed.validators)
        if validator_errors:
            return BuildResult(
                success=False,
                error="Invalid validators structure",
                error_type="validators_validation",
                validation_errors=validator_errors,
                warnings=warnings,
                raw_output=self._result_to_dict(result),
            )

        # Step 8: Create AgentSpec and AcceptanceSpec
        try:
            agent_spec, acceptance_spec = self._create_specs(
                parsed,
                task_type=task_type,
                task_description=task_description,
                spec_id=spec_id,
                source_feature_id=source_feature_id,
            )
        except Exception as e:
            _logger.exception("Failed to create specs from parsed output")
            return BuildResult(
                success=False,
                error=f"Failed to create specs: {e}",
                error_type="spec_creation",
                warnings=warnings,
                raw_output=self._result_to_dict(result),
            )

        return BuildResult(
            success=True,
            agent_spec=agent_spec,
            acceptance_spec=acceptance_spec,
            warnings=warnings,
            raw_output=self._result_to_dict(result),
        )

    def _execute_dspy(
        self,
        task_description: str,
        task_type: str,
        context_json: str,
    ) -> dspy.Prediction:
        """
        Execute the DSPy module with inputs.

        Args:
            task_description: Task description
            task_type: Task type
            context_json: Serialized context

        Returns:
            DSPy Prediction result

        Raises:
            DSPyExecutionError: If execution fails
        """
        with self._lock:
            if not self._initialized or self._dspy_module is None:
                raise DSPyExecutionError("SpecBuilder not initialized")

            try:
                result = self._dspy_module(
                    task_description=task_description,
                    task_type=task_type,
                    project_context=context_json,
                )
                return result
            except Exception as e:
                _logger.exception("DSPy execution failed")
                raise DSPyExecutionError(
                    f"DSPy execution failed: {e}",
                    original_error=e
                ) from e

    def _parse_output(self, result: dspy.Prediction) -> ParsedOutput:
        """
        Parse JSON output fields from DSPy result.

        Args:
            result: DSPy Prediction result

        Returns:
            ParsedOutput with all fields parsed

        Raises:
            OutputValidationError: If parsing fails
        """
        errors: list[str] = []

        # Parse context_json
        context, err = parse_json_field("context_json", result.context_json)
        if err:
            errors.append(err)
            context = {}

        # Parse tool_policy_json
        tool_policy, err = parse_json_field("tool_policy_json", result.tool_policy_json)
        if err:
            errors.append(err)
            tool_policy = {}

        # Parse validators_json
        validators, err = parse_json_field("validators_json", result.validators_json)
        if err:
            errors.append(err)
            validators = []

        # Parse max_turns
        max_turns, err = coerce_integer(
            "max_turns",
            result.max_turns,
            MIN_MAX_TURNS,
            MAX_MAX_TURNS,
        )
        if err:
            errors.append(err)
            max_turns = DEFAULT_BUDGETS.get("custom", {}).get("max_turns", 75)

        # Parse timeout_seconds
        timeout_seconds, err = coerce_integer(
            "timeout_seconds",
            result.timeout_seconds,
            MIN_TIMEOUT_SECONDS,
            MAX_TIMEOUT_SECONDS,
        )
        if err:
            errors.append(err)
            timeout_seconds = DEFAULT_BUDGETS.get("custom", {}).get("timeout_seconds", 1800)

        if errors:
            raise OutputValidationError(
                "Failed to parse DSPy output fields",
                validation_errors=errors,
            )

        return ParsedOutput(
            reasoning=result.reasoning or "",
            objective=result.objective or "",
            context=context,
            tool_policy=tool_policy,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
            validators=validators,
        )

    def _create_specs(
        self,
        parsed: ParsedOutput,
        *,
        task_type: str,
        task_description: str,
        spec_id: str | None,
        source_feature_id: int | None,
    ) -> tuple[AgentSpec, AcceptanceSpec]:
        """
        Create AgentSpec and AcceptanceSpec from parsed output.

        Args:
            parsed: Parsed DSPy output
            task_type: The task type
            task_description: Original task description
            spec_id: Optional spec ID
            source_feature_id: Optional source feature ID

        Returns:
            Tuple of (AgentSpec, AcceptanceSpec)
        """
        spec_id = spec_id or generate_uuid()

        # Generate spec name (without session-based collision check)
        spec_name = generate_spec_name(
            objective=parsed.objective,
            task_type=task_type,
        )

        # Derive display name from objective (first sentence or truncated)
        display_name = self._derive_display_name(parsed.objective, task_description)

        # Derive icon from task_type
        icon = self._derive_icon(task_type)

        # Ensure tool_policy has required structure
        tool_policy = self._normalize_tool_policy(parsed.tool_policy)

        # Create AgentSpec
        agent_spec = AgentSpec(
            id=spec_id,
            name=spec_name,
            display_name=display_name,
            icon=icon,
            spec_version="v1",
            objective=parsed.objective,
            task_type=task_type,
            context=parsed.context,
            tool_policy=tool_policy,
            max_turns=parsed.max_turns,
            timeout_seconds=parsed.timeout_seconds,
            source_feature_id=source_feature_id,
            tags=[task_type, "dspy-generated"],
        )

        # Create AcceptanceSpec
        acceptance_spec = self._create_acceptance_spec(
            agent_spec_id=spec_id,
            validators=parsed.validators,
            task_type=task_type,
        )

        # Link them
        agent_spec.acceptance_spec = acceptance_spec

        return agent_spec, acceptance_spec

    def _derive_display_name(self, objective: str, task_description: str) -> str:
        """Derive a display name from objective or task description."""
        # Try to use first sentence of objective
        text = objective or task_description

        # Extract first sentence
        match = re.match(r'^([^.!?]+[.!?])', text)
        if match:
            display_name = match.group(1).strip()
        else:
            display_name = text.strip()

        # Truncate if too long
        max_length = 100
        if len(display_name) > max_length:
            display_name = display_name[:max_length - 3] + "..."

        return display_name

    def _derive_icon(self, task_type: str) -> str:
        """Derive an icon from task type."""
        icons = {
            "coding": "code",
            "testing": "test-tube",
            "refactoring": "wrench",
            "documentation": "book",
            "audit": "shield",
            "custom": "gear",
        }
        return icons.get(task_type, "gear")

    def _normalize_tool_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        """Ensure tool_policy has required structure."""
        return create_tool_policy(
            allowed_tools=policy.get("allowed_tools", []),
            forbidden_patterns=policy.get("forbidden_patterns", []),
            tool_hints=policy.get("tool_hints", {}),
            policy_version=policy.get("policy_version", "v1"),
        )

    def _create_acceptance_spec(
        self,
        agent_spec_id: str,
        validators: list[dict[str, Any]],
        task_type: str,
    ) -> AcceptanceSpec:
        """Create AcceptanceSpec from validated validators."""
        # Convert raw validators to proper format
        normalized_validators = []
        for v in validators:
            normalized_validators.append(
                create_validator(
                    validator_type=v.get("type", "custom"),
                    config=v.get("config", {}),
                    weight=float(v.get("weight", 1.0)),
                    required=bool(v.get("required", False)),
                )
            )

        # Determine gate mode based on task type
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
            validators=normalized_validators,
            gate_mode=gate_mode,
            retry_policy=retry_policy,
            max_retries=max_retries,
        )

    def _result_to_dict(self, result: dspy.Prediction) -> dict[str, Any]:
        """Convert DSPy Prediction to dictionary for debugging."""
        try:
            return {
                "reasoning": getattr(result, "reasoning", None),
                "objective": getattr(result, "objective", None),
                "context_json": getattr(result, "context_json", None),
                "tool_policy_json": getattr(result, "tool_policy_json", None),
                "max_turns": getattr(result, "max_turns", None),
                "timeout_seconds": getattr(result, "timeout_seconds", None),
                "validators_json": getattr(result, "validators_json", None),
            }
        except Exception:
            return {}


# =============================================================================
# Module-level Singleton
# =============================================================================

_default_builder: SpecBuilder | None = None
_builder_lock = threading.Lock()


def get_spec_builder(
    *,
    model: str | None = None,
    api_key: str | None = None,
    force_new: bool = False,
) -> SpecBuilder:
    """
    Get or create the default SpecBuilder.

    Args:
        model: Optional model override (only used on first call)
        api_key: Optional API key override (only used on first call)
        force_new: If True, create a new builder even if one exists

    Returns:
        The default SpecBuilder instance
    """
    global _default_builder

    with _builder_lock:
        if force_new or _default_builder is None:
            _default_builder = SpecBuilder(
                model=model,
                api_key=api_key,
                auto_initialize=False,  # Lazy initialization
            )
        return _default_builder


def reset_spec_builder() -> None:
    """Reset the default spec builder (for testing)."""
    global _default_builder

    with _builder_lock:
        _default_builder = None
