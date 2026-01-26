"""
API Package
============

Database models and utilities for feature management.
"""

from api.database import Feature, create_database, get_database_path
from api.prompt_builder import (
    build_system_prompt,
    extract_tool_hints,
    format_tool_hints_as_markdown,
    inject_tool_hints_into_prompt,
)
from api.harness_kernel import (
    BudgetExceeded,
    BudgetTracker,
    ExecutionResult,
    HarnessKernel,
    MaxTurnsExceeded,
)
from api.static_spec_adapter import (
    StaticSpecAdapter,
    get_static_spec_adapter,
    reset_static_spec_adapter,
    INITIALIZER_TOOLS,
    CODING_TOOLS,
    TESTING_TOOLS,
    DEFAULT_BUDGETS,
)

__all__ = [
    "Feature",
    "create_database",
    "get_database_path",
    # Prompt builder exports
    "build_system_prompt",
    "extract_tool_hints",
    "format_tool_hints_as_markdown",
    "inject_tool_hints_into_prompt",
    # Harness kernel exports
    "BudgetExceeded",
    "BudgetTracker",
    "ExecutionResult",
    "HarnessKernel",
    "MaxTurnsExceeded",
    # Static spec adapter exports
    "StaticSpecAdapter",
    "get_static_spec_adapter",
    "reset_static_spec_adapter",
    "INITIALIZER_TOOLS",
    "CODING_TOOLS",
    "TESTING_TOOLS",
    "DEFAULT_BUDGETS",
]
