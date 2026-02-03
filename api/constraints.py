"""
Constraint Satisfaction for AgentSpec Generation
=================================================

This module provides constraint definitions and validation for Octo's
AgentSpec generation. It ensures generated specs meet project requirements
such as tool availability, model limits, and sandbox restrictions.

Feature #185: Octo DSPy module with constraint satisfaction

Key components:
- ConstraintDefinition: Base class for all constraint types
- ToolAvailabilityConstraint: Ensures specs only use available tools
- ModelLimitConstraint: Enforces budget limits (max_turns, timeout)
- SandboxConstraint: Restricts file/directory access
- ConstraintValidator: Validates AgentSpecs against constraints
- ConstraintViolation: Records individual constraint violations

Usage:
    from api.constraints import (
        ConstraintValidator,
        ToolAvailabilityConstraint,
        ModelLimitConstraint,
        SandboxConstraint,
    )

    # Create constraints from OctoRequestPayload
    constraints = [
        ToolAvailabilityConstraint(available_tools=["Read", "Write", "Bash"]),
        ModelLimitConstraint(max_turns_limit=100, timeout_limit=3600),
        SandboxConstraint(allowed_directories=["/home/user/project"]),
    ]

    # Validate a spec
    validator = ConstraintValidator(constraints)
    result = validator.validate(agent_spec)

    if not result.is_valid:
        for violation in result.violations:
            print(f"{violation.constraint_type}: {violation.message}")
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

# Module logger
_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Constants
# =============================================================================

# Default budget limits
DEFAULT_MAX_TURNS_LIMIT = 500
DEFAULT_TIMEOUT_LIMIT = 7200  # 2 hours

# Model-specific limits
MODEL_LIMITS: dict[str, dict[str, int]] = {
    "sonnet": {
        "max_turns": 500,
        "timeout_seconds": 7200,
    },
    "opus": {
        "max_turns": 300,  # Opus is more expensive, so lower default
        "timeout_seconds": 7200,
    },
    "haiku": {
        "max_turns": 500,  # Haiku is fast, can do more turns
        "timeout_seconds": 3600,
    },
}

# Standard available tools (from tool_policy.py TOOL_SETS)
STANDARD_TOOLS: frozenset[str] = frozenset({
    # Feature management
    "feature_get_by_id",
    "feature_get_summary",
    "feature_get_stats",
    "feature_claim_and_get",
    "feature_mark_in_progress",
    "feature_mark_passing",
    "feature_mark_failing",
    "feature_skip",
    "feature_clear_in_progress",
    "feature_get_ready",
    "feature_get_blocked",
    "feature_get_graph",
    # File operations
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    # Execution
    "Bash",
    # Browser automation
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_evaluate",
    # Web research
    "WebFetch",
    "WebSearch",
    # Claude Code built-ins
    "TodoRead",
    "TodoWrite",
})


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ConstraintViolation:
    """
    Records a single constraint violation.

    Attributes:
        constraint_type: Type of constraint violated (e.g., "tool_availability")
        field: The AgentSpec field that violated the constraint
        message: Human-readable description of the violation
        value: The invalid value that caused the violation
        suggested_fix: Optional suggestion for how to fix the violation
        timestamp: When the violation was detected
    """
    constraint_type: str
    field: str
    message: str
    value: Any = None
    suggested_fix: str | None = None
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "constraint_type": self.constraint_type,
            "field": self.field,
            "message": self.message,
            "value": str(self.value)[:200] if self.value is not None else None,
            "suggested_fix": self.suggested_fix,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConstraintValidationResult:
    """
    Result of validating an AgentSpec against constraints.

    Attributes:
        is_valid: True if no violations found
        violations: List of constraint violations
        corrected_spec: Optional corrected spec if auto-correction was applied
        spec_id: ID of the spec that was validated
        spec_name: Name of the spec that was validated
    """
    is_valid: bool
    violations: list[ConstraintViolation] = field(default_factory=list)
    corrected_spec: "AgentSpec | None" = None
    spec_id: str | None = None
    spec_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_valid": self.is_valid,
            "violations": [v.to_dict() for v in self.violations],
            "has_corrected_spec": self.corrected_spec is not None,
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "violation_count": len(self.violations),
        }

    @property
    def violation_messages(self) -> list[str]:
        """Get list of violation messages."""
        return [v.message for v in self.violations]


# =============================================================================
# Constraint Definitions
# =============================================================================

class ConstraintDefinition(ABC):
    """
    Base class for constraint definitions.

    Feature #185, Step 1: Define constraints

    All constraint types inherit from this base class and implement:
    - validate(): Check if a spec meets the constraint
    - correct(): Optionally auto-correct violations
    """

    @property
    @abstractmethod
    def constraint_type(self) -> str:
        """Return the constraint type identifier."""
        pass

    @abstractmethod
    def validate(self, spec: "AgentSpec") -> list[ConstraintViolation]:
        """
        Validate an AgentSpec against this constraint.

        Args:
            spec: The AgentSpec to validate

        Returns:
            List of violations (empty if spec is valid)
        """
        pass

    def correct(self, spec: "AgentSpec") -> "AgentSpec | None":
        """
        Attempt to auto-correct constraint violations.

        By default, returns None (no correction possible).
        Subclasses can override to provide auto-correction.

        Args:
            spec: The AgentSpec to correct

        Returns:
            Corrected spec or None if correction not possible
        """
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert constraint to dictionary for serialization."""
        return {
            "type": self.constraint_type,
        }


@dataclass
class ToolAvailabilityConstraint(ConstraintDefinition):
    """
    Constraint ensuring specs only use available tools.

    Feature #185, Step 1: tool availability constraint

    This constraint:
    - Checks that all tools in tool_policy.allowed_tools are available
    - Can auto-correct by removing unavailable tools
    - Warns if minimum required tools are missing
    """
    available_tools: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)

    @property
    def constraint_type(self) -> str:
        return "tool_availability"

    def __post_init__(self):
        """Convert available_tools to a set for efficient lookup."""
        self._available_set = frozenset(self.available_tools) if self.available_tools else STANDARD_TOOLS
        self._required_set = frozenset(self.required_tools)

    def validate(self, spec: "AgentSpec") -> list[ConstraintViolation]:
        """Check that all tools in the spec are available."""
        violations: list[ConstraintViolation] = []

        tool_policy = getattr(spec, "tool_policy", None)
        if not tool_policy or not isinstance(tool_policy, dict):
            return violations

        allowed_tools = tool_policy.get("allowed_tools", [])
        if not isinstance(allowed_tools, list):
            return violations

        # Check for unavailable tools
        unavailable = []
        for tool in allowed_tools:
            if tool not in self._available_set:
                unavailable.append(tool)

        if unavailable:
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="tool_policy.allowed_tools",
                message=f"Spec uses unavailable tools: {unavailable}",
                value=unavailable,
                suggested_fix=f"Remove unavailable tools or add them to available_tools list",
            ))
            _logger.warning(
                "Tool availability constraint violation: spec=%s, unavailable=%s",
                getattr(spec, "name", "unknown"),
                unavailable,
            )

        # Check for missing required tools
        spec_tools = frozenset(allowed_tools)
        missing_required = self._required_set - spec_tools

        if missing_required:
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="tool_policy.allowed_tools",
                message=f"Spec is missing required tools: {list(missing_required)}",
                value=list(missing_required),
                suggested_fix=f"Add required tools: {list(missing_required)}",
            ))
            _logger.warning(
                "Tool availability constraint violation: spec=%s, missing_required=%s",
                getattr(spec, "name", "unknown"),
                list(missing_required),
            )

        return violations

    def correct(self, spec: "AgentSpec") -> "AgentSpec | None":
        """
        Auto-correct by removing unavailable tools and adding required tools.

        Returns a new spec with corrected tool_policy, or None if the spec
        doesn't have a valid tool_policy.
        """
        tool_policy = getattr(spec, "tool_policy", None)
        if not tool_policy or not isinstance(tool_policy, dict):
            return None

        allowed_tools = tool_policy.get("allowed_tools", [])
        if not isinstance(allowed_tools, list):
            return None

        # Filter to only available tools
        filtered_tools = [t for t in allowed_tools if t in self._available_set]

        # Add required tools if missing
        for required in self._required_set:
            if required not in filtered_tools and required in self._available_set:
                filtered_tools.append(required)

        if not filtered_tools:
            # Can't have empty allowed_tools
            return None

        # Create corrected tool_policy
        corrected_policy = tool_policy.copy()
        corrected_policy["allowed_tools"] = filtered_tools

        # Create new spec with corrected policy
        # Note: We create a shallow copy with updated tool_policy
        corrected = _shallow_copy_spec(spec)
        corrected.tool_policy = corrected_policy

        _logger.info(
            "Auto-corrected tool availability: spec=%s, original=%d tools, corrected=%d tools",
            getattr(spec, "name", "unknown"),
            len(allowed_tools),
            len(filtered_tools),
        )

        return corrected

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type,
            "available_tools_count": len(self.available_tools) if self.available_tools else len(STANDARD_TOOLS),
            "required_tools": self.required_tools,
        }


@dataclass
class ModelLimitConstraint(ConstraintDefinition):
    """
    Constraint enforcing budget limits based on model.

    Feature #185, Step 1: model limits constraint

    This constraint:
    - Enforces max_turns limit (default: 500)
    - Enforces timeout_seconds limit (default: 7200)
    - Can use model-specific limits from MODEL_LIMITS
    - Can auto-correct by capping values to limits
    """
    max_turns_limit: int = DEFAULT_MAX_TURNS_LIMIT
    timeout_limit: int = DEFAULT_TIMEOUT_LIMIT
    model: str | None = None

    @property
    def constraint_type(self) -> str:
        return "model_limits"

    def __post_init__(self):
        """Apply model-specific limits if a model is specified."""
        if self.model and self.model in MODEL_LIMITS:
            model_limits = MODEL_LIMITS[self.model]
            # Only override if not explicitly set
            if self.max_turns_limit == DEFAULT_MAX_TURNS_LIMIT:
                self.max_turns_limit = model_limits.get("max_turns", DEFAULT_MAX_TURNS_LIMIT)
            if self.timeout_limit == DEFAULT_TIMEOUT_LIMIT:
                self.timeout_limit = model_limits.get("timeout_seconds", DEFAULT_TIMEOUT_LIMIT)

    def validate(self, spec: "AgentSpec") -> list[ConstraintViolation]:
        """Check that spec budget values are within limits."""
        violations: list[ConstraintViolation] = []

        # Check max_turns
        max_turns = getattr(spec, "max_turns", None)
        if max_turns is not None and max_turns > self.max_turns_limit:
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="max_turns",
                message=f"max_turns ({max_turns}) exceeds limit ({self.max_turns_limit})",
                value=max_turns,
                suggested_fix=f"Reduce max_turns to {self.max_turns_limit} or less",
            ))
            _logger.warning(
                "Model limit constraint violation: spec=%s, max_turns=%d > limit=%d",
                getattr(spec, "name", "unknown"),
                max_turns,
                self.max_turns_limit,
            )

        # Check timeout_seconds
        timeout = getattr(spec, "timeout_seconds", None)
        if timeout is not None and timeout > self.timeout_limit:
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="timeout_seconds",
                message=f"timeout_seconds ({timeout}) exceeds limit ({self.timeout_limit})",
                value=timeout,
                suggested_fix=f"Reduce timeout_seconds to {self.timeout_limit} or less",
            ))
            _logger.warning(
                "Model limit constraint violation: spec=%s, timeout=%d > limit=%d",
                getattr(spec, "name", "unknown"),
                timeout,
                self.timeout_limit,
            )

        return violations

    def correct(self, spec: "AgentSpec") -> "AgentSpec | None":
        """
        Auto-correct by capping budget values to limits.
        """
        max_turns = getattr(spec, "max_turns", None)
        timeout = getattr(spec, "timeout_seconds", None)

        needs_correction = False
        corrected_max_turns = max_turns
        corrected_timeout = timeout

        if max_turns is not None and max_turns > self.max_turns_limit:
            corrected_max_turns = self.max_turns_limit
            needs_correction = True

        if timeout is not None and timeout > self.timeout_limit:
            corrected_timeout = self.timeout_limit
            needs_correction = True

        if not needs_correction:
            return None

        corrected = _shallow_copy_spec(spec)
        if corrected_max_turns is not None:
            corrected.max_turns = corrected_max_turns
        if corrected_timeout is not None:
            corrected.timeout_seconds = corrected_timeout

        _logger.info(
            "Auto-corrected model limits: spec=%s, max_turns=%s->%s, timeout=%s->%s",
            getattr(spec, "name", "unknown"),
            max_turns,
            corrected_max_turns,
            timeout,
            corrected_timeout,
        )

        return corrected

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type,
            "max_turns_limit": self.max_turns_limit,
            "timeout_limit": self.timeout_limit,
            "model": self.model,
        }


@dataclass
class SandboxConstraint(ConstraintDefinition):
    """
    Constraint restricting file/directory access.

    Feature #185, Step 1: sandbox restrictions constraint

    This constraint:
    - Validates allowed_directories in tool_policy
    - Ensures specs respect sandbox boundaries
    - Prevents path traversal or access outside allowed directories
    """
    allowed_directories: list[str] = field(default_factory=list)
    enforce_sandbox: bool = True

    @property
    def constraint_type(self) -> str:
        return "sandbox"

    def validate(self, spec: "AgentSpec") -> list[ConstraintViolation]:
        """Check that spec respects sandbox restrictions."""
        violations: list[ConstraintViolation] = []

        if not self.enforce_sandbox:
            return violations

        if not self.allowed_directories:
            # No sandbox restriction defined - allow all
            return violations

        tool_policy = getattr(spec, "tool_policy", None)
        if not tool_policy or not isinstance(tool_policy, dict):
            return violations

        spec_directories = tool_policy.get("allowed_directories", [])
        if not spec_directories:
            # Spec doesn't specify directories - this could be a violation
            # if we require explicit sandbox boundaries
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="tool_policy.allowed_directories",
                message="Spec does not specify allowed_directories but sandbox is enforced",
                value=None,
                suggested_fix=f"Add allowed_directories: {self.allowed_directories}",
            ))
            _logger.warning(
                "Sandbox constraint violation: spec=%s missing allowed_directories",
                getattr(spec, "name", "unknown"),
            )
            return violations

        # Check each spec directory is within allowed directories
        for spec_dir in spec_directories:
            if not self._is_path_allowed(spec_dir):
                violations.append(ConstraintViolation(
                    constraint_type=self.constraint_type,
                    field="tool_policy.allowed_directories",
                    message=f"Directory '{spec_dir}' is outside allowed sandbox",
                    value=spec_dir,
                    suggested_fix=f"Remove directory or use one of: {self.allowed_directories}",
                ))
                _logger.warning(
                    "Sandbox constraint violation: spec=%s, dir=%s not in allowed=%s",
                    getattr(spec, "name", "unknown"),
                    spec_dir,
                    self.allowed_directories,
                )

        return violations

    def _is_path_allowed(self, path: str) -> bool:
        """Check if a path is within allowed directories."""
        from pathlib import Path

        try:
            check_path = Path(path).resolve()
        except (ValueError, OSError):
            return False

        for allowed in self.allowed_directories:
            try:
                allowed_path = Path(allowed).resolve()
                # Check if check_path is within allowed_path
                if check_path == allowed_path:
                    return True
                try:
                    check_path.relative_to(allowed_path)
                    return True
                except ValueError:
                    continue
            except (ValueError, OSError):
                continue

        return False

    def correct(self, spec: "AgentSpec") -> "AgentSpec | None":
        """
        Auto-correct by setting allowed_directories to sandbox boundaries.
        """
        if not self.enforce_sandbox or not self.allowed_directories:
            return None

        tool_policy = getattr(spec, "tool_policy", None)
        if not tool_policy or not isinstance(tool_policy, dict):
            return None

        # Set allowed_directories to our sandbox
        corrected_policy = tool_policy.copy()
        corrected_policy["allowed_directories"] = list(self.allowed_directories)

        corrected = _shallow_copy_spec(spec)
        corrected.tool_policy = corrected_policy

        _logger.info(
            "Auto-corrected sandbox: spec=%s, set allowed_directories=%s",
            getattr(spec, "name", "unknown"),
            self.allowed_directories,
        )

        return corrected

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type,
            "allowed_directories": self.allowed_directories,
            "enforce_sandbox": self.enforce_sandbox,
        }


@dataclass
class ForbiddenPatternConstraint(ConstraintDefinition):
    """
    Constraint ensuring spec includes required forbidden patterns.

    This constraint ensures security patterns are enforced by checking
    that the spec's forbidden_patterns includes baseline security patterns.
    """
    required_patterns: list[str] = field(default_factory=list)

    @property
    def constraint_type(self) -> str:
        return "forbidden_patterns"

    def validate(self, spec: "AgentSpec") -> list[ConstraintViolation]:
        """Check that spec includes required forbidden patterns."""
        violations: list[ConstraintViolation] = []

        if not self.required_patterns:
            return violations

        tool_policy = getattr(spec, "tool_policy", None)
        if not tool_policy or not isinstance(tool_policy, dict):
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="tool_policy",
                message="Spec missing tool_policy for forbidden pattern check",
                value=None,
                suggested_fix="Add tool_policy with forbidden_patterns",
            ))
            return violations

        spec_patterns = set(tool_policy.get("forbidden_patterns", []))

        missing_patterns = []
        for pattern in self.required_patterns:
            if pattern not in spec_patterns:
                missing_patterns.append(pattern)

        if missing_patterns:
            violations.append(ConstraintViolation(
                constraint_type=self.constraint_type,
                field="tool_policy.forbidden_patterns",
                message=f"Spec missing {len(missing_patterns)} required forbidden patterns",
                value=missing_patterns[:5],  # Show first 5
                suggested_fix="Add required security patterns to forbidden_patterns",
            ))
            _logger.warning(
                "Forbidden pattern constraint violation: spec=%s, missing=%d patterns",
                getattr(spec, "name", "unknown"),
                len(missing_patterns),
            )

        return violations

    def correct(self, spec: "AgentSpec") -> "AgentSpec | None":
        """Auto-correct by adding required patterns."""
        if not self.required_patterns:
            return None

        tool_policy = getattr(spec, "tool_policy", None)
        if not tool_policy or not isinstance(tool_policy, dict):
            return None

        existing = set(tool_policy.get("forbidden_patterns", []))
        combined = list(existing | set(self.required_patterns))

        if len(combined) == len(existing):
            # Nothing to add
            return None

        corrected_policy = tool_policy.copy()
        corrected_policy["forbidden_patterns"] = combined

        corrected = _shallow_copy_spec(spec)
        corrected.tool_policy = corrected_policy

        _logger.info(
            "Auto-corrected forbidden patterns: spec=%s, added %d patterns",
            getattr(spec, "name", "unknown"),
            len(combined) - len(existing),
        )

        return corrected

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.constraint_type,
            "required_patterns_count": len(self.required_patterns),
        }


# =============================================================================
# Constraint Validator
# =============================================================================

class ConstraintValidator:
    """
    Validates AgentSpecs against a set of constraints.

    Feature #185, Step 2: DSPy module validates specs against constraints

    This class:
    - Accepts a list of ConstraintDefinition objects
    - Validates specs against all constraints
    - Optionally auto-corrects violations
    - Logs all violations for debugging
    """

    def __init__(
        self,
        constraints: list[ConstraintDefinition] | None = None,
        *,
        auto_correct: bool = True,
        reject_on_uncorrectable: bool = True,
    ):
        """
        Initialize the validator.

        Args:
            constraints: List of constraints to validate against
            auto_correct: If True, attempt to auto-correct violations
            reject_on_uncorrectable: If True, mark specs invalid if correction fails
        """
        self._constraints = constraints or []
        self._auto_correct = auto_correct
        self._reject_on_uncorrectable = reject_on_uncorrectable

        _logger.info(
            "ConstraintValidator initialized with %d constraints (auto_correct=%s)",
            len(self._constraints),
            auto_correct,
        )

    @property
    def constraints(self) -> list[ConstraintDefinition]:
        """Get the list of constraints."""
        return self._constraints

    def add_constraint(self, constraint: ConstraintDefinition) -> None:
        """Add a constraint to the validator."""
        self._constraints.append(constraint)
        _logger.debug("Added constraint: %s", constraint.constraint_type)

    def validate(
        self,
        spec: "AgentSpec",
        *,
        auto_correct: bool | None = None,
    ) -> ConstraintValidationResult:
        """
        Validate an AgentSpec against all constraints.

        Feature #185, Step 2 & 3: Validate and optionally correct specs

        Args:
            spec: The AgentSpec to validate
            auto_correct: Override instance auto_correct setting

        Returns:
            ConstraintValidationResult with violations and optional corrected spec
        """
        should_correct = auto_correct if auto_correct is not None else self._auto_correct

        spec_id = getattr(spec, "id", None)
        spec_name = getattr(spec, "name", None)

        _logger.debug(
            "Validating spec: id=%s, name=%s, constraints=%d",
            spec_id,
            spec_name,
            len(self._constraints),
        )

        all_violations: list[ConstraintViolation] = []
        corrected_spec = spec

        for constraint in self._constraints:
            # Validate against this constraint
            violations = constraint.validate(corrected_spec)

            if violations:
                _logger.debug(
                    "Constraint %s found %d violations for spec %s",
                    constraint.constraint_type,
                    len(violations),
                    spec_name,
                )

                if should_correct:
                    # Attempt to correct
                    corrected = constraint.correct(corrected_spec)

                    if corrected is not None:
                        # Re-validate after correction
                        remaining = constraint.validate(corrected)

                        if not remaining:
                            # Correction successful
                            corrected_spec = corrected
                            _logger.info(
                                "Auto-corrected %d violations for constraint %s",
                                len(violations),
                                constraint.constraint_type,
                            )
                        else:
                            # Partial correction
                            corrected_spec = corrected
                            all_violations.extend(remaining)
                            _logger.warning(
                                "Partial correction for constraint %s: %d remaining violations",
                                constraint.constraint_type,
                                len(remaining),
                            )
                    else:
                        # No correction available
                        all_violations.extend(violations)
                        _logger.warning(
                            "No auto-correction available for constraint %s",
                            constraint.constraint_type,
                        )
                else:
                    all_violations.extend(violations)

        # Determine if spec is valid
        is_valid = len(all_violations) == 0

        # If correction was applied, include the corrected spec
        has_corrected = corrected_spec is not spec

        if all_violations:
            _logger.warning(
                "Spec %s has %d constraint violations (corrected=%s)",
                spec_name,
                len(all_violations),
                has_corrected,
            )
            # Feature #185, Step 4: Log constraint violations for debugging
            for violation in all_violations:
                _logger.debug(
                    "Violation: constraint=%s, field=%s, message=%s",
                    violation.constraint_type,
                    violation.field,
                    violation.message,
                )
        else:
            _logger.debug(
                "Spec %s passed all constraint validation (corrected=%s)",
                spec_name,
                has_corrected,
            )

        return ConstraintValidationResult(
            is_valid=is_valid,
            violations=all_violations,
            corrected_spec=corrected_spec if has_corrected else None,
            spec_id=spec_id,
            spec_name=spec_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert validator configuration to dictionary."""
        return {
            "constraints": [c.to_dict() for c in self._constraints],
            "auto_correct": self._auto_correct,
            "reject_on_uncorrectable": self._reject_on_uncorrectable,
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_constraints_from_payload(
    constraints_dict: dict[str, Any] | None,
    project_context: dict[str, Any] | None = None,
) -> list[ConstraintDefinition]:
    """
    Create constraint objects from an OctoRequestPayload's constraints dict.

    Args:
        constraints_dict: The constraints dict from OctoRequestPayload
        project_context: Optional project context for additional constraints

    Returns:
        List of ConstraintDefinition objects
    """
    constraints: list[ConstraintDefinition] = []

    if not constraints_dict:
        constraints_dict = {}

    # Tool availability constraint
    available_tools = constraints_dict.get("available_tools")
    required_tools = constraints_dict.get("required_tools")

    if available_tools or required_tools:
        constraints.append(ToolAvailabilityConstraint(
            available_tools=available_tools or [],
            required_tools=required_tools or [],
        ))
    else:
        # Default tool availability with standard tools
        constraints.append(ToolAvailabilityConstraint())

    # Model limit constraint
    model = constraints_dict.get("model")
    max_turns = constraints_dict.get("max_turns_limit")
    timeout = constraints_dict.get("timeout_limit")

    constraints.append(ModelLimitConstraint(
        max_turns_limit=max_turns or DEFAULT_MAX_TURNS_LIMIT,
        timeout_limit=timeout or DEFAULT_TIMEOUT_LIMIT,
        model=model,
    ))

    # Sandbox constraint
    allowed_dirs = constraints_dict.get("allowed_directories")
    enforce_sandbox = constraints_dict.get("enforce_sandbox", False)

    if allowed_dirs or enforce_sandbox:
        # If project_context has a working directory, use that
        if project_context and not allowed_dirs:
            cwd = project_context.get("working_directory") or project_context.get("cwd")
            if cwd:
                allowed_dirs = [cwd]

        constraints.append(SandboxConstraint(
            allowed_directories=allowed_dirs or [],
            enforce_sandbox=enforce_sandbox,
        ))

    # Forbidden pattern constraint
    required_patterns = constraints_dict.get("required_forbidden_patterns")
    if required_patterns:
        constraints.append(ForbiddenPatternConstraint(
            required_patterns=required_patterns,
        ))

    _logger.info(
        "Created %d constraints from payload",
        len(constraints),
    )

    return constraints


def create_default_constraints(
    model: str | None = None,
    working_directory: str | None = None,
) -> list[ConstraintDefinition]:
    """
    Create a default set of constraints for Octo.

    Args:
        model: Optional model name for model-specific limits
        working_directory: Optional working directory for sandbox

    Returns:
        List of default ConstraintDefinition objects
    """
    constraints: list[ConstraintDefinition] = [
        # Default tool availability - allow standard tools
        ToolAvailabilityConstraint(),
        # Default model limits
        ModelLimitConstraint(model=model),
    ]

    if working_directory:
        constraints.append(SandboxConstraint(
            allowed_directories=[working_directory],
            enforce_sandbox=True,
        ))

    return constraints


# =============================================================================
# Helper Functions
# =============================================================================

def _shallow_copy_spec(spec: "AgentSpec") -> "AgentSpec":
    """
    Create a shallow copy of an AgentSpec for modification.

    This creates a new object with the same attributes, allowing
    modification without affecting the original spec.
    """
    from api.agentspec_models import AgentSpec

    # Get all attributes from the original spec
    attrs = {}
    for attr in [
        "id", "name", "display_name", "icon", "spec_version",
        "objective", "task_type", "context", "tool_policy",
        "max_turns", "timeout_seconds", "source_feature_id",
        "tags", "priority", "created_at", "updated_at",
    ]:
        value = getattr(spec, attr, None)
        if value is not None:
            # Copy mutable values
            if isinstance(value, dict):
                value = value.copy()
            elif isinstance(value, list):
                value = value.copy()
            attrs[attr] = value

    # Create new spec with copied attributes
    return AgentSpec(**attrs)
