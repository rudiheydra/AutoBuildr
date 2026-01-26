"""
API Package
============

Database models and utilities for feature management.
"""

from api.database import Feature, create_database, get_database_path
from api.dependency_resolver import (
    DependencyIssue,
    DependencyResult,
    ValidationResult,
    validate_dependency_graph,
    validate_dependencies,
    resolve_dependencies,
    would_create_circular_dependency,
    are_dependencies_satisfied,
    get_blocking_dependencies,
    get_ready_features,
    get_blocked_features,
    build_graph_data,
    compute_scheduling_scores,
)
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
from api.tool_policy import (
    CompiledPattern,
    PatternCompilationError,
    ToolCallBlocked,
    ToolPolicyEnforcer,
    ToolPolicyError,
    check_arguments_against_patterns,
    compile_forbidden_patterns,
    create_enforcer_for_run,
    extract_forbidden_patterns,
    record_blocked_tool_call_event,
    serialize_tool_arguments,
)
from api.display_derivation import (
    derive_display_name,
    derive_display_properties,
    derive_icon,
    derive_mascot_name,
    extract_first_sentence,
    get_mascot_pool,
    get_task_type_icons,
    truncate_with_ellipsis,
    DISPLAY_NAME_MAX_LENGTH,
    MASCOT_POOL,
    TASK_TYPE_ICONS,
    DEFAULT_ICON,
)

__all__ = [
    "Feature",
    "create_database",
    "get_database_path",
    # Dependency resolver exports
    "DependencyIssue",
    "DependencyResult",
    "ValidationResult",
    "validate_dependency_graph",
    "validate_dependencies",
    "resolve_dependencies",
    "would_create_circular_dependency",
    "are_dependencies_satisfied",
    "get_blocking_dependencies",
    "get_ready_features",
    "get_blocked_features",
    "build_graph_data",
    "compute_scheduling_scores",
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
    # Tool policy exports
    "CompiledPattern",
    "PatternCompilationError",
    "ToolCallBlocked",
    "ToolPolicyEnforcer",
    "ToolPolicyError",
    "check_arguments_against_patterns",
    "compile_forbidden_patterns",
    "create_enforcer_for_run",
    "extract_forbidden_patterns",
    "record_blocked_tool_call_event",
    "serialize_tool_arguments",
    # Display derivation exports
    "derive_display_name",
    "derive_display_properties",
    "derive_icon",
    "derive_mascot_name",
    "extract_first_sentence",
    "get_mascot_pool",
    "get_task_type_icons",
    "truncate_with_ellipsis",
    "DISPLAY_NAME_MAX_LENGTH",
    "MASCOT_POOL",
    "TASK_TYPE_ICONS",
    "DEFAULT_ICON",
]
