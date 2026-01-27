"""
Migration Flag Module
=====================

Implements the AUTOBUILDR_USE_KERNEL migration flag logic to choose between
legacy agent execution and the new HarnessKernel-based execution.

This module provides:
- Environment variable reading for AUTOBUILDR_USE_KERNEL
- Default to false for backwards compatibility
- Legacy execution path (existing agents)
- Kernel execution path (Feature -> AgentSpec -> HarnessKernel)
- Graceful fallback on kernel errors
- Execution path reporting

Feature #39: AUTOBUILDR_USE_KERNEL Migration Flag

Usage:
    ```python
    from api.migration_flag import (
        is_kernel_enabled,
        execute_feature,
        ExecutionPath,
    )

    # Check if kernel is enabled
    if is_kernel_enabled():
        print("Using new HarnessKernel")
    else:
        print("Using legacy agents")

    # Execute a feature using the appropriate path
    result = execute_feature(feature, db_session)
    print(f"Executed via: {result.execution_path}")
    ```
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from api.agentspec_models import AgentRun, AgentSpec
    from api.database import Feature


# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Environment variable name
ENV_VAR_NAME = "AUTOBUILDR_USE_KERNEL"

# Default value for the migration flag
DEFAULT_USE_KERNEL = False

# Truthy values for environment variable
TRUTHY_VALUES = ("1", "true", "yes", "on", "enabled")

# Falsy values for environment variable
FALSY_VALUES = ("0", "false", "no", "off", "disabled", "")


# =============================================================================
# Execution Path Enum
# =============================================================================

class ExecutionPath(str, Enum):
    """
    Enum representing which execution path was used.

    Used in response to indicate whether legacy or kernel path was used.
    """

    LEGACY = "legacy"
    KERNEL = "kernel"
    FALLBACK = "fallback"  # Kernel failed, fell back to legacy


# =============================================================================
# Execution Result
# =============================================================================

@dataclass
class FeatureExecutionResult:
    """
    Result of feature execution including path information.

    Attributes:
        success: Whether execution completed (may have failed verdict)
        execution_path: Which path was used (legacy/kernel/fallback)
        run_id: ID of the AgentRun if created
        spec_id: ID of the AgentSpec if created (kernel path only)
        status: Final run status (pending/running/completed/failed/timeout)
        final_verdict: Acceptance verdict (passed/failed/partial)
        turns_used: Number of turns consumed
        tokens_in: Input tokens consumed
        tokens_out: Output tokens consumed
        error: Error message if execution failed
        fallback_reason: Reason for fallback if execution_path is FALLBACK
        metadata: Additional execution metadata
    """

    success: bool
    execution_path: ExecutionPath
    run_id: Optional[str] = None
    spec_id: Optional[str] = None
    status: Optional[str] = None
    final_verdict: Optional[str] = None
    turns_used: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    error: Optional[str] = None
    fallback_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "success": self.success,
            "execution_path": self.execution_path.value,
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "status": self.status,
            "final_verdict": self.final_verdict,
            "turns_used": self.turns_used,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "error": self.error,
            "fallback_reason": self.fallback_reason,
            "metadata": self.metadata,
        }


# =============================================================================
# Environment Variable Reading
# =============================================================================

def get_use_kernel_env_value() -> Optional[str]:
    """
    Read the raw AUTOBUILDR_USE_KERNEL environment variable value.

    Returns:
        The raw string value, or None if not set
    """
    return os.environ.get(ENV_VAR_NAME)


def parse_use_kernel_value(value: Optional[str]) -> bool:
    """
    Parse the AUTOBUILDR_USE_KERNEL value to a boolean.

    Args:
        value: The string value from environment (can be None)

    Returns:
        True if kernel should be used, False otherwise

    The following values are considered truthy:
    - "1", "true", "yes", "on", "enabled" (case-insensitive)

    The following values are considered falsy:
    - None, "", "0", "false", "no", "off", "disabled" (case-insensitive)

    Unknown values default to False for safety.
    """
    if value is None:
        return DEFAULT_USE_KERNEL

    normalized = value.strip().lower()

    if normalized in TRUTHY_VALUES:
        return True

    if normalized in FALSY_VALUES:
        return False

    # Unknown value - log warning and default to False for safety
    _logger.warning(
        "Unknown value for %s: '%s'. Defaulting to False. "
        "Valid truthy values: %s. Valid falsy values: %s",
        ENV_VAR_NAME,
        value,
        TRUTHY_VALUES,
        FALSY_VALUES,
    )
    return DEFAULT_USE_KERNEL


def is_kernel_enabled() -> bool:
    """
    Check if the HarnessKernel execution path is enabled.

    Feature #39, Steps 1-2:
    - Step 1: Read AUTOBUILDR_USE_KERNEL from environment
    - Step 2: Default to false for backwards compatibility

    Returns:
        True if AUTOBUILDR_USE_KERNEL is set to a truthy value, False otherwise

    Example:
        >>> import os
        >>> os.environ["AUTOBUILDR_USE_KERNEL"] = "true"
        >>> is_kernel_enabled()
        True
        >>> os.environ["AUTOBUILDR_USE_KERNEL"] = "false"
        >>> is_kernel_enabled()
        False
        >>> del os.environ["AUTOBUILDR_USE_KERNEL"]
        >>> is_kernel_enabled()  # Defaults to False
        False
    """
    raw_value = get_use_kernel_env_value()
    result = parse_use_kernel_value(raw_value)

    _logger.debug(
        "%s=%s -> kernel_enabled=%s",
        ENV_VAR_NAME,
        raw_value,
        result,
    )

    return result


def set_kernel_enabled(enabled: bool) -> None:
    """
    Set the AUTOBUILDR_USE_KERNEL environment variable.

    This is primarily useful for testing.

    Args:
        enabled: Whether to enable the kernel
    """
    if enabled:
        os.environ[ENV_VAR_NAME] = "true"
    else:
        os.environ[ENV_VAR_NAME] = "false"


def clear_kernel_flag() -> None:
    """
    Remove the AUTOBUILDR_USE_KERNEL environment variable.

    This is primarily useful for testing to restore default behavior.
    """
    if ENV_VAR_NAME in os.environ:
        del os.environ[ENV_VAR_NAME]


# =============================================================================
# Legacy Execution Path
# =============================================================================

def execute_feature_legacy(
    feature: "Feature",
    db: Session,
    *,
    context: dict[str, Any] | None = None,
) -> FeatureExecutionResult:
    """
    Execute a feature using the legacy agent path.

    Feature #39, Step 3: When false, use existing agent execution path

    This path uses the original hard-coded agent implementations.
    The legacy path is simpler but less flexible than the kernel path.

    Note: In the current codebase, legacy execution is handled externally
    (by the orchestrator/CLI). This function serves as a marker for the
    legacy path and returns immediately with pending status.

    Args:
        feature: The Feature to execute
        db: Database session
        context: Optional execution context

    Returns:
        FeatureExecutionResult with execution_path=LEGACY
    """
    _logger.info(
        "Using legacy execution path for feature #%d: %s",
        feature.id,
        feature.name,
    )

    # In the legacy path, execution is handled by external systems
    # (orchestrator, CLI, etc.). We mark it as pending for legacy handling.
    return FeatureExecutionResult(
        success=True,
        execution_path=ExecutionPath.LEGACY,
        status="pending",  # Legacy path handles actual execution externally
        metadata={
            "feature_id": feature.id,
            "feature_name": feature.name,
            "message": "Queued for legacy execution",
        },
    )


# =============================================================================
# Kernel Execution Path
# =============================================================================

def execute_feature_kernel(
    feature: "Feature",
    db: Session,
    *,
    context: dict[str, Any] | None = None,
    turn_executor: Any | None = None,
) -> FeatureExecutionResult:
    """
    Execute a feature using the new HarnessKernel path.

    Feature #39, Step 4: When true, compile Feature -> AgentSpec -> HarnessKernel

    This path:
    1. Compiles the Feature into an AgentSpec using FeatureCompiler
    2. Creates an AgentRun record
    3. Executes via HarnessKernel
    4. Returns the execution result

    Args:
        feature: The Feature to execute
        db: Database session
        context: Optional execution context
        turn_executor: Optional callback for turn execution (for testing)

    Returns:
        FeatureExecutionResult with execution_path=KERNEL
    """
    from api.agentspec_models import AgentRun as AgentRunModel
    from api.agentspec_models import AgentSpec as AgentSpecModel
    from api.feature_compiler import compile_feature
    from api.harness_kernel import HarnessKernel

    _logger.info(
        "Using kernel execution path for feature #%d: %s",
        feature.id,
        feature.name,
    )

    # Step 1: Compile Feature -> AgentSpec
    spec = compile_feature(feature)

    _logger.debug(
        "Compiled feature #%d into spec %s (task_type=%s, max_turns=%d)",
        feature.id,
        spec.name,
        spec.task_type,
        spec.max_turns,
    )

    # Step 2: Persist the AgentSpec to database
    db_spec = AgentSpecModel(
        id=spec.id,
        name=spec.name,
        display_name=spec.display_name,
        icon=spec.icon,
        spec_version=spec.spec_version,
        objective=spec.objective,
        task_type=spec.task_type,
        context=spec.context,
        tool_policy=spec.tool_policy,
        max_turns=spec.max_turns,
        timeout_seconds=spec.timeout_seconds,
        source_feature_id=spec.source_feature_id,
        priority=spec.priority,
        tags=spec.tags,
    )

    # Check if spec already exists (idempotent)
    existing_spec = db.query(AgentSpecModel).filter(
        AgentSpecModel.source_feature_id == feature.id
    ).first()

    if existing_spec:
        # Use existing spec
        db_spec = existing_spec
        _logger.debug("Using existing spec %s for feature #%d", db_spec.id, feature.id)
    else:
        db.add(db_spec)
        db.flush()  # Get ID without committing
        _logger.debug("Created new spec %s for feature #%d", db_spec.id, feature.id)

    # Reload spec as proper object for kernel
    spec.id = db_spec.id

    # Step 3: Create HarnessKernel and execute
    kernel = HarnessKernel(db)

    # Execute the spec
    run = kernel.execute(spec, turn_executor=turn_executor, context=context)

    # Step 4: Return result
    return FeatureExecutionResult(
        success=run.status in ("completed",),
        execution_path=ExecutionPath.KERNEL,
        run_id=run.id,
        spec_id=spec.id,
        status=run.status,
        final_verdict=run.final_verdict,
        turns_used=run.turns_used,
        tokens_in=run.tokens_in,
        tokens_out=run.tokens_out,
        error=run.error,
        metadata={
            "feature_id": feature.id,
            "feature_name": feature.name,
            "spec_name": spec.name,
            "task_type": spec.task_type,
        },
    )


# =============================================================================
# Main Execution Function with Fallback
# =============================================================================

def execute_feature(
    feature: "Feature",
    db: Session,
    *,
    context: dict[str, Any] | None = None,
    force_legacy: bool = False,
    force_kernel: bool = False,
    turn_executor: Any | None = None,
) -> FeatureExecutionResult:
    """
    Execute a feature using the appropriate execution path.

    Feature #39 Implementation:
    - Step 1: Read AUTOBUILDR_USE_KERNEL from environment
    - Step 2: Default to false for backwards compatibility
    - Step 3: When false, use existing agent execution path
    - Step 4: When true, compile Feature -> AgentSpec -> HarnessKernel
    - Step 5: Wrap kernel execution in try/except
    - Step 6: On kernel error, log warning and fallback to legacy
    - Step 7: Report which path was used in response

    Args:
        feature: The Feature to execute
        db: Database session
        context: Optional execution context
        force_legacy: If True, always use legacy path (ignores env var)
        force_kernel: If True, always use kernel path (ignores env var)
        turn_executor: Optional callback for turn execution (kernel path only)

    Returns:
        FeatureExecutionResult with execution_path indicating which path was used

    Raises:
        ValueError: If both force_legacy and force_kernel are True
    """
    if force_legacy and force_kernel:
        raise ValueError("Cannot specify both force_legacy and force_kernel")

    # Determine which path to use
    if force_legacy:
        use_kernel = False
        _logger.debug("Forced legacy path for feature #%d", feature.id)
    elif force_kernel:
        use_kernel = True
        _logger.debug("Forced kernel path for feature #%d", feature.id)
    else:
        # Read from environment (Steps 1-2)
        use_kernel = is_kernel_enabled()
        _logger.debug(
            "Environment %s=%s for feature #%d",
            ENV_VAR_NAME,
            use_kernel,
            feature.id,
        )

    # Execute using appropriate path
    if not use_kernel:
        # Step 3: Use legacy path
        return execute_feature_legacy(feature, db, context=context)

    # Step 4: Use kernel path with fallback handling
    # Step 5: Wrap kernel execution in try/except
    try:
        result = execute_feature_kernel(
            feature,
            db,
            context=context,
            turn_executor=turn_executor,
        )

        # Step 7: Path is already reported in result.execution_path
        return result

    except Exception as kernel_error:
        # Step 6: On kernel error, log warning and fallback to legacy
        _logger.warning(
            "Kernel execution failed for feature #%d: %s. Falling back to legacy.",
            feature.id,
            str(kernel_error),
            exc_info=True,  # Include traceback in logs
        )

        # Execute via legacy path
        legacy_result = execute_feature_legacy(feature, db, context=context)

        # Update result to indicate fallback
        legacy_result.execution_path = ExecutionPath.FALLBACK
        legacy_result.fallback_reason = str(kernel_error)
        legacy_result.metadata["kernel_error"] = str(kernel_error)

        return legacy_result


# =============================================================================
# Utility Functions
# =============================================================================

def get_execution_path_string() -> str:
    """
    Get a human-readable string describing the current execution path.

    Returns:
        "kernel" if kernel is enabled, "legacy" otherwise
    """
    return "kernel" if is_kernel_enabled() else "legacy"


def get_migration_status() -> dict[str, Any]:
    """
    Get the current migration status for debugging/monitoring.

    Returns:
        Dictionary with migration status information
    """
    raw_value = get_use_kernel_env_value()
    enabled = is_kernel_enabled()

    return {
        "env_var": ENV_VAR_NAME,
        "raw_value": raw_value,
        "kernel_enabled": enabled,
        "execution_path": "kernel" if enabled else "legacy",
        "default_value": DEFAULT_USE_KERNEL,
    }
