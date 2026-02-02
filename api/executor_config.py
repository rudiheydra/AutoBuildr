"""
Executor Configuration
======================

Environment variable configuration and factory for choosing between
the raw Messages API turn executor and the Claude Agent SDK session executor.

Pattern follows api/migration_flag.py (env var name, truthy/falsy parsing,
convenience function).

Usage:
    from api.executor_config import get_executor_type, is_sdk_executor, create_executor_for_spec

    # Check executor type
    if is_sdk_executor():
        print("Using Claude SDK session executor")

    # Create executor for a spec
    executor = create_executor_for_spec(project_dir, spec)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

_logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

ENV_VAR_NAME = "AUTOBUILDR_EXECUTOR"

EXECUTOR_RAW_MESSAGES = "raw_messages"
EXECUTOR_CLAUDE_SDK = "claude_sdk"

VALID_VALUES = (EXECUTOR_RAW_MESSAGES, EXECUTOR_CLAUDE_SDK)

DEFAULT_EXECUTOR = EXECUTOR_RAW_MESSAGES


# =============================================================================
# Environment Variable Reading
# =============================================================================

def get_executor_type() -> str:
    """
    Read the AUTOBUILDR_EXECUTOR env var and return the executor type.

    Returns:
        One of EXECUTOR_RAW_MESSAGES or EXECUTOR_CLAUDE_SDK.
        Defaults to EXECUTOR_RAW_MESSAGES if unset or invalid.
    """
    raw = os.environ.get(ENV_VAR_NAME, "").strip().lower()

    if not raw:
        return DEFAULT_EXECUTOR

    if raw in VALID_VALUES:
        return raw

    _logger.warning(
        "Unknown value for %s: '%s'. Defaulting to '%s'. Valid values: %s",
        ENV_VAR_NAME,
        raw,
        DEFAULT_EXECUTOR,
        VALID_VALUES,
    )
    return DEFAULT_EXECUTOR


def is_sdk_executor() -> bool:
    """Check if the SDK session executor is configured."""
    return get_executor_type() == EXECUTOR_CLAUDE_SDK


# =============================================================================
# Factory
# =============================================================================

def create_executor_for_spec(
    project_dir: Path,
    spec: "AgentSpec | None" = None,
) -> Optional[Callable]:
    """
    Create the appropriate executor based on AUTOBUILDR_EXECUTOR env var.

    Args:
        project_dir: Root project directory
        spec: The AgentSpec being executed (used for context, not consumed)

    Returns:
        A callable executor, or None if no auth/executor is available.
    """
    executor_type = get_executor_type()

    if executor_type == EXECUTOR_CLAUDE_SDK:
        try:
            from api.sdk_session_executor import ClaudeAgentSDKSessionExecutor

            executor = ClaudeAgentSDKSessionExecutor(project_dir=project_dir)
            _logger.info("Created ClaudeAgentSDKSessionExecutor")
            return executor
        except Exception as e:
            _logger.error("Failed to create SDK session executor: %s", e)
            return None

    # Default: raw_messages
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        _logger.info("No ANTHROPIC_API_KEY — no raw_messages executor available")
        return None

    try:
        from api.turn_executor import create_turn_executor

        executor = create_turn_executor(
            project_dir=project_dir,
            api_key=api_key,
        )
        _logger.info("Created ClaudeSDKTurnExecutor (raw_messages)")
        return executor
    except Exception as e:
        _logger.error("Failed to create raw_messages executor: %s", e)
        return None
