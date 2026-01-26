"""
Validators Module
=================

Acceptance validators for verifying agent run completion.

This module implements the validator interface from the app spec:
- Validator interface with evaluate(run, context) -> ValidatorResult
- file_exists validator: verify file path exists
- test_pass validator: run command, check exit code
- forbidden_patterns validator: ensure output doesn't contain patterns
- lint_clean validator (optional): run linter, check for errors

Validators are deterministic checks that verify agent work without
relying on LLM judgment. They form the acceptance gates that must
pass before an agent run is considered complete.

Usage:
    ```python
    from api.validators import FileExistsValidator, ValidatorResult

    # Create validator with config
    validator = FileExistsValidator()

    # Evaluate against a run
    config = {"path": "{project_dir}/init.sh"}
    context = {"project_dir": "/path/to/project"}
    result = validator.evaluate(config, context)

    if result.passed:
        print("File exists!")
    else:
        print(f"Failed: {result.message}")
    ```
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from api.agentspec_models import AgentRun

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# ValidatorResult Dataclass
# =============================================================================

@dataclass
class ValidatorResult:
    """
    Result of a validator evaluation.

    Attributes:
        passed: Whether the validation passed
        message: Human-readable description of the result
        score: Optional numeric score (0.0-1.0) for weighted gates
        details: Optional additional details for debugging
        validator_type: The type of validator that produced this result
    """
    passed: bool
    message: str
    score: float = 1.0  # Default to 1.0 for binary pass/fail
    details: dict[str, Any] = field(default_factory=dict)
    validator_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "message": self.message,
            "score": self.score,
            "details": self.details,
            "validator_type": self.validator_type,
        }


# =============================================================================
# Base Validator Interface
# =============================================================================

class Validator(ABC):
    """
    Abstract base class for acceptance validators.

    Validators are deterministic checks that verify agent work. They
    receive configuration (from the validator definition) and context
    (runtime information like project paths, run data) and return a
    ValidatorResult.

    Subclasses must implement the evaluate() method.

    The validator interface supports:
    - Variable interpolation in paths (e.g., {project_dir})
    - Configuration-based customization
    - Detailed result messages for debugging
    """

    # Validator type identifier (set in subclasses)
    validator_type: str = "base"

    @abstractmethod
    def evaluate(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
        run: "AgentRun | None" = None,
    ) -> ValidatorResult:
        """
        Evaluate the validator against the current state.

        Args:
            config: Validator configuration from the acceptance spec.
                   Contains type-specific settings like paths, patterns, etc.
            context: Runtime context with variable values for interpolation.
                    Common keys: project_dir, feature_id, run_id
            run: Optional AgentRun instance for validators that need run data.

        Returns:
            ValidatorResult with passed status and message.
        """
        pass

    def interpolate_path(self, path: str, context: dict[str, Any]) -> str:
        """
        Interpolate variables in a path string.

        Variables are specified as {variable_name} and are replaced
        with values from the context dictionary.

        Args:
            path: Path string with optional {variable} placeholders
            context: Dictionary of variable values

        Returns:
            Path with variables replaced

        Example:
            >>> validator.interpolate_path("{project_dir}/init.sh", {"project_dir": "/app"})
            '/app/init.sh'
        """
        result = path

        # Find all {variable} patterns
        pattern = re.compile(r'\{(\w+)\}')

        for match in pattern.finditer(path):
            var_name = match.group(1)
            if var_name in context:
                var_value = str(context[var_name])
                result = result.replace(f"{{{var_name}}}", var_value)
            else:
                _logger.warning(
                    "Variable '%s' not found in context for path interpolation",
                    var_name
                )

        return result


# =============================================================================
# FileExistsValidator
# =============================================================================

class FileExistsValidator(Validator):
    """
    Validator that checks if a file or directory exists.

    This validator verifies that a specified path exists (or doesn't exist,
    if should_exist is False). Supports variable interpolation in paths.

    Config Options:
        path (str, required): The file path to check. Supports variable
            interpolation like {project_dir}, {feature_id}.
        should_exist (bool, optional): If True (default), validates that the
            path exists. If False, validates that the path does NOT exist.
        description (str, optional): Human-readable description of the check.

    Context Variables:
        project_dir: Base project directory for relative paths
        Any other variables used in the path template

    Example Config:
        {
            "path": "{project_dir}/init.sh",
            "should_exist": true,
            "description": "Environment initialization script must exist"
        }
    """

    validator_type: str = "file_exists"

    def evaluate(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
        run: "AgentRun | None" = None,
    ) -> ValidatorResult:
        """
        Check if the specified path exists.

        Args:
            config: Validator configuration containing:
                - path (required): Path to check, with optional {variables}
                - should_exist (optional, default True): Expected existence state
                - description (optional): Human-readable check description
            context: Runtime context with variable values for interpolation
            run: Optional AgentRun (not used by this validator)

        Returns:
            ValidatorResult indicating whether the path existence matches
            the should_exist expectation.
        """
        # Step 2: Extract path from validator config
        path_template = config.get("path")

        if not path_template:
            return ValidatorResult(
                passed=False,
                message="Validator config missing required 'path' field",
                score=0.0,
                details={"config": config},
                validator_type=self.validator_type,
            )

        # Step 3: Interpolate variables in path
        interpolated_path = self.interpolate_path(path_template, context)

        # Step 4: Extract should_exist (default true)
        should_exist = config.get("should_exist", True)

        # Normalize should_exist to boolean
        if isinstance(should_exist, str):
            should_exist = should_exist.lower() in ("true", "1", "yes")

        # Step 5: Check if path exists using Path.exists()
        path_obj = Path(interpolated_path)

        # Handle relative paths by resolving against project_dir if provided
        if not path_obj.is_absolute() and "project_dir" in context:
            path_obj = Path(context["project_dir"]) / path_obj

        file_exists = path_obj.exists()

        # Step 6: Return passed = exists == should_exist
        passed = file_exists == should_exist

        # Calculate score (1.0 for pass, 0.0 for fail)
        score = 1.0 if passed else 0.0

        # Step 7: Include file path in result message
        description = config.get("description", "")

        if passed:
            if should_exist:
                message = f"File exists: {interpolated_path}"
            else:
                message = f"File correctly does not exist: {interpolated_path}"
        else:
            if should_exist:
                message = f"File does not exist: {interpolated_path}"
            else:
                message = f"File unexpectedly exists: {interpolated_path}"

        # Append description if provided
        if description:
            message = f"{message} ({description})"

        _logger.debug(
            "FileExistsValidator: path=%s, should_exist=%s, exists=%s, passed=%s",
            interpolated_path, should_exist, file_exists, passed
        )

        return ValidatorResult(
            passed=passed,
            message=message,
            score=score,
            details={
                "path_template": path_template,
                "interpolated_path": interpolated_path,
                "resolved_path": str(path_obj.resolve()) if path_obj.exists() else str(path_obj),
                "should_exist": should_exist,
                "file_exists": file_exists,
                "is_file": path_obj.is_file() if file_exists else None,
                "is_directory": path_obj.is_dir() if file_exists else None,
            },
            validator_type=self.validator_type,
        )


# =============================================================================
# ForbiddenPatternsValidator
# =============================================================================

class ForbiddenPatternsValidator(Validator):
    """
    Validator that ensures agent output does not contain forbidden regex patterns.

    This validator checks all tool_result events from an agent run against a list
    of forbidden regex patterns. If any pattern matches any payload, the validation
    fails.

    Config Options:
        patterns (list[str], required): List of regex patterns to check against.
            Each pattern will be compiled as a Python regex.
        case_sensitive (bool, optional): If True (default), patterns are case-sensitive.
            If False, patterns are matched case-insensitively.
        description (str, optional): Human-readable description of the check.

    Context Variables:
        Not used by this validator.

    Example Config:
        {
            "patterns": ["rm -rf /", "DROP TABLE", "password\\s*=\\s*['\"].*['\"]"],
            "case_sensitive": true,
            "description": "Check for dangerous commands and credential leaks"
        }
    """

    validator_type: str = "forbidden_patterns"

    def evaluate(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
        run: "AgentRun | None" = None,
    ) -> ValidatorResult:
        """
        Check if any tool_result event payloads contain forbidden patterns.

        Args:
            config: Validator configuration containing:
                - patterns (required): List of regex patterns to check
                - case_sensitive (optional, default True): Whether patterns are case-sensitive
                - description (optional): Human-readable check description
            context: Runtime context (not used by this validator)
            run: AgentRun instance to check events from (required)

        Returns:
            ValidatorResult indicating whether any forbidden patterns were found.
        """
        # Step 2: Extract patterns array from validator config
        patterns = config.get("patterns")

        if not patterns:
            return ValidatorResult(
                passed=False,
                message="Validator config missing required 'patterns' field",
                score=0.0,
                details={"config": config},
                validator_type=self.validator_type,
            )

        if not isinstance(patterns, list):
            return ValidatorResult(
                passed=False,
                message="Validator config 'patterns' must be a list",
                score=0.0,
                details={"config": config, "patterns_type": type(patterns).__name__},
                validator_type=self.validator_type,
            )

        if len(patterns) == 0:
            return ValidatorResult(
                passed=True,
                message="No forbidden patterns specified, validation passes",
                score=1.0,
                details={"patterns_count": 0},
                validator_type=self.validator_type,
            )

        # Check if run is provided (required for this validator)
        if run is None:
            return ValidatorResult(
                passed=False,
                message="ForbiddenPatternsValidator requires an AgentRun instance",
                score=0.0,
                details={"config": config},
                validator_type=self.validator_type,
            )

        # Step 3: Compile patterns as regex
        case_sensitive = config.get("case_sensitive", True)
        regex_flags = 0 if case_sensitive else re.IGNORECASE

        compiled_patterns: list[tuple[str, re.Pattern]] = []
        compilation_errors: list[str] = []

        for pattern_str in patterns:
            try:
                compiled = re.compile(pattern_str, regex_flags)
                compiled_patterns.append((pattern_str, compiled))
            except re.error as e:
                compilation_errors.append(f"Pattern '{pattern_str}': {e}")

        if compilation_errors:
            return ValidatorResult(
                passed=False,
                message=f"Failed to compile {len(compilation_errors)} regex pattern(s)",
                score=0.0,
                details={
                    "compilation_errors": compilation_errors,
                    "config": config,
                },
                validator_type=self.validator_type,
            )

        # Step 4: Query all tool_result events for the run
        # The run.events relationship is already loaded by SQLAlchemy
        tool_result_events = [
            event for event in run.events
            if event.event_type == "tool_result"
        ]

        _logger.debug(
            "ForbiddenPatternsValidator: checking %d tool_result events against %d patterns",
            len(tool_result_events), len(compiled_patterns)
        )

        # Step 5: Check each payload against all patterns
        matches_found: list[dict[str, Any]] = []

        for event in tool_result_events:
            payload = event.payload

            if payload is None:
                continue

            # Convert payload to searchable string
            # Handle both string and dict payloads
            if isinstance(payload, str):
                payload_text = payload
            elif isinstance(payload, dict):
                # Convert dict to string for pattern matching
                # Include all values in the search
                payload_text = _dict_to_searchable_text(payload)
            else:
                payload_text = str(payload)

            # Step 5 (cont): Check against all patterns
            for pattern_str, compiled_pattern in compiled_patterns:
                match = compiled_pattern.search(payload_text)
                if match:
                    # Step 7: Include matched pattern and context in result
                    matches_found.append({
                        "event_id": event.id,
                        "event_sequence": event.sequence,
                        "tool_name": event.tool_name,
                        "pattern": pattern_str,
                        "matched_text": match.group(),
                        "match_start": match.start(),
                        "match_end": match.end(),
                        # Include some context around the match
                        "context": _get_match_context(payload_text, match, context_chars=50),
                    })

        # Step 6 & 8: Return result
        description = config.get("description", "")

        if matches_found:
            # Step 6: If any match found, return passed = false
            message = f"Found {len(matches_found)} forbidden pattern match(es)"
            if description:
                message = f"{message} ({description})"

            _logger.info(
                "ForbiddenPatternsValidator: FAILED - found %d matches in run %s",
                len(matches_found), run.id
            )

            return ValidatorResult(
                passed=False,
                message=message,
                score=0.0,
                details={
                    "matches": matches_found,
                    "patterns_checked": patterns,
                    "events_checked": len(tool_result_events),
                },
                validator_type=self.validator_type,
            )
        else:
            # Step 8: Return passed = true if no matches
            message = f"No forbidden patterns found in {len(tool_result_events)} tool_result event(s)"
            if description:
                message = f"{message} ({description})"

            _logger.debug(
                "ForbiddenPatternsValidator: PASSED - no matches in run %s",
                run.id
            )

            return ValidatorResult(
                passed=True,
                message=message,
                score=1.0,
                details={
                    "patterns_checked": patterns,
                    "events_checked": len(tool_result_events),
                },
                validator_type=self.validator_type,
            )


def _dict_to_searchable_text(d: dict, prefix: str = "") -> str:
    """
    Convert a dictionary to a searchable text string.

    Recursively traverses the dictionary and concatenates all string values.
    """
    parts = []
    for key, value in d.items():
        key_path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            parts.append(_dict_to_searchable_text(value, key_path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    parts.append(_dict_to_searchable_text(item, f"{key_path}[{i}]"))
                else:
                    parts.append(str(item))
        else:
            parts.append(str(value))
    return "\n".join(parts)


def _get_match_context(text: str, match: re.Match, context_chars: int = 50) -> str:
    """
    Get context around a regex match.

    Returns a substring with `context_chars` characters before and after the match.
    """
    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)

    context = text[start:end]

    # Add ellipsis if truncated
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."

    return context


# =============================================================================
# Validator Registry
# =============================================================================

# Registry of available validator types
VALIDATOR_REGISTRY: dict[str, type[Validator]] = {
    "file_exists": FileExistsValidator,
    "forbidden_patterns": ForbiddenPatternsValidator,
}


def get_validator(validator_type: str) -> Validator | None:
    """
    Get a validator instance by type.

    Args:
        validator_type: The validator type string (e.g., "file_exists")

    Returns:
        Validator instance or None if type not found
    """
    validator_class = VALIDATOR_REGISTRY.get(validator_type)
    if validator_class is None:
        _logger.warning("Unknown validator type: %s", validator_type)
        return None
    return validator_class()


def evaluate_validator(
    validator_def: dict[str, Any],
    context: dict[str, Any],
    run: "AgentRun | None" = None,
) -> ValidatorResult:
    """
    Evaluate a validator definition from an AcceptanceSpec.

    This is a convenience function that extracts the validator type,
    gets the appropriate validator instance, and runs the evaluation.

    Args:
        validator_def: Validator definition from AcceptanceSpec.validators
            Must contain "type" and "config" keys.
        context: Runtime context for variable interpolation
        run: Optional AgentRun instance

    Returns:
        ValidatorResult from the evaluation

    Example:
        >>> validator_def = {
        ...     "type": "file_exists",
        ...     "config": {"path": "/app/init.sh"},
        ...     "weight": 1.0,
        ...     "required": True
        ... }
        >>> result = evaluate_validator(validator_def, {})
    """
    validator_type = validator_def.get("type")
    config = validator_def.get("config", {})

    if not validator_type:
        return ValidatorResult(
            passed=False,
            message="Validator definition missing 'type' field",
            score=0.0,
            details={"validator_def": validator_def},
            validator_type="unknown",
        )

    validator = get_validator(validator_type)

    if validator is None:
        return ValidatorResult(
            passed=False,
            message=f"Unknown validator type: {validator_type}",
            score=0.0,
            details={"validator_def": validator_def},
            validator_type=validator_type,
        )

    return validator.evaluate(config, context, run)


def evaluate_acceptance_spec(
    validators: list[dict[str, Any]],
    context: dict[str, Any],
    gate_mode: str = "all_pass",
    run: "AgentRun | None" = None,
) -> tuple[bool, list[ValidatorResult]]:
    """
    Evaluate all validators in an acceptance spec.

    Args:
        validators: List of validator definitions from AcceptanceSpec
        context: Runtime context for variable interpolation
        gate_mode: How to combine results ("all_pass", "any_pass", "weighted")
        run: Optional AgentRun instance

    Returns:
        Tuple of (overall_passed, list of ValidatorResults)
    """
    results = []
    required_passed = True

    for validator_def in validators:
        result = evaluate_validator(validator_def, context, run)
        results.append(result)

        # Check if this was a required validator that failed
        is_required = validator_def.get("required", False)
        if is_required and not result.passed:
            required_passed = False

    # Determine overall pass based on gate mode
    if not required_passed:
        # Required validators must always pass
        overall_passed = False
    elif gate_mode == "all_pass":
        overall_passed = all(r.passed for r in results)
    elif gate_mode == "any_pass":
        overall_passed = any(r.passed for r in results)
    else:  # weighted or unknown
        overall_passed = all(r.passed for r in results)

    return overall_passed, results
