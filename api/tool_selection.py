"""
Tool Selection for Agent Generation (Feature #186)
===================================================

This module provides intelligent tool selection for agents based on their role,
capability, and task type. It implements the least-privilege principle to ensure
agents only have access to the tools they need.

Feature #186: Octo selects appropriate tools for each agent

Key Features:
- AVAILABLE_TOOLS: Comprehensive catalog of all available tools with metadata
- ROLE_TOOL_CATEGORIES: Maps agent roles to required tool categories
- ROLE_TOOL_OVERRIDES: Fine-grained control for specific role/tool combinations
- select_tools_for_capability: Main entry point for tool selection

Usage:
    from api.tool_selection import (
        select_tools_for_capability,
        AVAILABLE_TOOLS,
        get_browser_tools,
    )

    # Select tools for a UI testing agent
    result = select_tools_for_capability(
        capability="ui_testing",
        task_type="testing",
    )
    print(f"Selected tools: {result.tools}")
    print(f"Reasoning: {result.reasoning}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.tool_policy import TOOL_SETS


# =============================================================================
# Available Tools Catalog (Feature #186 Step 1)
# =============================================================================

# Feature #186 Step 1: Octo has knowledge of available tools
# Comprehensive catalog of all available tools with metadata
AVAILABLE_TOOLS: dict[str, dict[str, Any]] = {
    # File system tools
    "Read": {
        "category": "filesystem",
        "description": "Read file contents from disk",
        "privilege_level": "read",
        "requires_sandbox": True,
    },
    "Write": {
        "category": "filesystem",
        "description": "Write content to files on disk",
        "privilege_level": "write",
        "requires_sandbox": True,
    },
    "Edit": {
        "category": "filesystem",
        "description": "Edit existing files with precise changes",
        "privilege_level": "write",
        "requires_sandbox": True,
    },
    "Glob": {
        "category": "filesystem",
        "description": "Find files by pattern matching",
        "privilege_level": "read",
        "requires_sandbox": True,
    },
    "Grep": {
        "category": "filesystem",
        "description": "Search file contents with regex patterns",
        "privilege_level": "read",
        "requires_sandbox": True,
    },

    # Execution tools
    "Bash": {
        "category": "execution",
        "description": "Execute shell commands",
        "privilege_level": "execute",
        "requires_sandbox": True,
    },

    # Web tools
    "WebFetch": {
        "category": "web",
        "description": "Fetch content from URLs",
        "privilege_level": "network",
        "requires_sandbox": False,
    },
    "WebSearch": {
        "category": "web",
        "description": "Search the web for information",
        "privilege_level": "network",
        "requires_sandbox": False,
    },

    # Task management tools
    "TodoRead": {
        "category": "task_management",
        "description": "Read task/todo list",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "TodoWrite": {
        "category": "task_management",
        "description": "Write/update task/todo list",
        "privilege_level": "write",
        "requires_sandbox": False,
    },

    # Feature management tools (MCP)
    "feature_get_by_id": {
        "category": "feature_management",
        "description": "Get feature details by ID",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "feature_get_summary": {
        "category": "feature_management",
        "description": "Get feature summary (minimal info)",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "feature_get_stats": {
        "category": "feature_management",
        "description": "Get feature completion statistics",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "feature_claim_and_get": {
        "category": "feature_management",
        "description": "Claim a feature and get its details",
        "privilege_level": "write",
        "requires_sandbox": False,
    },
    "feature_mark_in_progress": {
        "category": "feature_management",
        "description": "Mark feature as in-progress",
        "privilege_level": "write",
        "requires_sandbox": False,
    },
    "feature_mark_passing": {
        "category": "feature_management",
        "description": "Mark feature as passing",
        "privilege_level": "write",
        "requires_sandbox": False,
    },
    "feature_mark_failing": {
        "category": "feature_management",
        "description": "Mark feature as failing",
        "privilege_level": "write",
        "requires_sandbox": False,
    },
    "feature_skip": {
        "category": "feature_management",
        "description": "Skip a feature (move to end of queue)",
        "privilege_level": "write",
        "requires_sandbox": False,
    },
    "feature_clear_in_progress": {
        "category": "feature_management",
        "description": "Clear in-progress status",
        "privilege_level": "write",
        "requires_sandbox": False,
    },
    "feature_get_ready": {
        "category": "feature_management",
        "description": "Get features ready to start",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "feature_get_blocked": {
        "category": "feature_management",
        "description": "Get blocked features",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "feature_get_graph": {
        "category": "feature_management",
        "description": "Get dependency graph data",
        "privilege_level": "read",
        "requires_sandbox": False,
    },

    # Browser automation tools (Playwright MCP) - Feature #186 Step 4
    "browser_navigate": {
        "category": "browser",
        "description": "Navigate to a URL in browser",
        "privilege_level": "ui_interact",
        "requires_sandbox": False,
    },
    "browser_click": {
        "category": "browser",
        "description": "Click element on page",
        "privilege_level": "ui_interact",
        "requires_sandbox": False,
    },
    "browser_type": {
        "category": "browser",
        "description": "Type text into element",
        "privilege_level": "ui_interact",
        "requires_sandbox": False,
    },
    "browser_fill_form": {
        "category": "browser",
        "description": "Fill form fields",
        "privilege_level": "ui_interact",
        "requires_sandbox": False,
    },
    "browser_snapshot": {
        "category": "browser",
        "description": "Capture page accessibility snapshot",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "browser_take_screenshot": {
        "category": "browser",
        "description": "Take screenshot of page",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "browser_console_messages": {
        "category": "browser",
        "description": "Get browser console messages",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "browser_network_requests": {
        "category": "browser",
        "description": "Get network requests from browser",
        "privilege_level": "read",
        "requires_sandbox": False,
    },
    "browser_evaluate": {
        "category": "browser",
        "description": "Evaluate JavaScript in browser",
        "privilege_level": "execute",
        "requires_sandbox": False,
    },
}


# =============================================================================
# Role-to-Tool Mappings (Feature #186 Step 2)
# =============================================================================

# Feature #186 Step 2: Octo matches agent role to required tool set
# Maps agent roles/capabilities to their required tool categories
ROLE_TOOL_CATEGORIES: dict[str, list[str]] = {
    # Test runner agents get test-related tools (Feature #186 Step 3)
    "test_runner": ["filesystem", "execution", "feature_management"],
    "test-runner": ["filesystem", "execution", "feature_management"],

    # UI testing agents get browser/Playwright tools (Feature #186 Step 4)
    "ui_testing": ["filesystem", "browser", "feature_management"],
    "e2e_testing": ["filesystem", "execution", "browser", "feature_management"],
    "ui_agent": ["browser", "filesystem", "feature_management"],

    # API testing agents need execution for curl/requests
    "api_testing": ["filesystem", "execution", "feature_management"],

    # Coding agents get full file system and execution
    "coding": ["filesystem", "execution", "task_management", "web", "feature_management", "browser"],
    "coder": ["filesystem", "execution", "task_management", "web", "feature_management", "browser"],

    # Documentation agents get write access but no execution
    "documentation": ["filesystem", "web", "feature_management"],
    "docs": ["filesystem", "web", "feature_management"],

    # Audit agents are read-only (Feature #186 Step 5: least-privilege)
    "audit": ["filesystem", "browser", "feature_management"],
    "security_audit": ["filesystem", "feature_management"],

    # Refactoring agents get file editing and execution for testing
    "refactoring": ["filesystem", "execution", "feature_management"],
}


# =============================================================================
# Least-Privilege Overrides (Feature #186 Step 5)
# =============================================================================

# Feature #186 Step 5: Tool selection follows least-privilege principle
# Specific tool overrides for fine-grained control
ROLE_TOOL_OVERRIDES: dict[str, dict[str, list[str]]] = {
    # Test runners can read/execute but shouldn't write production code (least-privilege)
    "test_runner": {
        "include": ["Read", "Glob", "Grep", "Bash"],
        "exclude": ["Write", "Edit"],
    },
    "test-runner": {
        "include": ["Read", "Glob", "Grep", "Bash"],
        "exclude": ["Write", "Edit"],
    },

    # UI agents need browser tools for Playwright (Feature #186 Step 4)
    "ui_testing": {
        "include": [
            "browser_navigate", "browser_click", "browser_type", "browser_fill_form",
            "browser_snapshot", "browser_take_screenshot", "browser_console_messages",
            "browser_network_requests",
        ],
        "exclude": ["browser_evaluate"],  # No JS execution for least-privilege
    },
    "e2e_testing": {
        "include": [
            "browser_navigate", "browser_click", "browser_type", "browser_fill_form",
            "browser_snapshot", "browser_take_screenshot", "browser_console_messages",
            "browser_network_requests", "browser_evaluate", "Bash",
        ],
        "exclude": [],
    },

    # Audit agents are strictly read-only (least-privilege)
    "audit": {
        "include": [
            "Read", "Glob", "Grep",
            "browser_navigate", "browser_snapshot", "browser_take_screenshot",
            "browser_console_messages", "browser_network_requests",
        ],
        "exclude": ["Write", "Edit", "Bash", "browser_click", "browser_type", "browser_fill_form"],
    },
    "security_audit": {
        "include": ["Read", "Glob", "Grep"],
        "exclude": ["Write", "Edit", "Bash"],
    },

    # Documentation agents shouldn't execute code (least-privilege)
    "documentation": {
        "include": ["Read", "Write", "Glob", "Grep", "WebFetch", "WebSearch"],
        "exclude": ["Bash", "Edit"],  # No editing source code
    },
}


# =============================================================================
# Tool Selection Result
# =============================================================================

@dataclass
class ToolSelectionResult:
    """
    Result of tool selection for an agent.

    Feature #186: Octo selects appropriate tools for each agent.

    Attributes:
        tools: List of selected tool names
        categories_used: Categories that contributed tools
        overrides_applied: Any role-specific overrides that were applied
        least_privilege_exclusions: Tools excluded for security reasons
        reasoning: Human-readable explanation of selections
    """
    tools: list[str]
    categories_used: list[str] = field(default_factory=list)
    overrides_applied: dict[str, list[str]] = field(default_factory=dict)
    least_privilege_exclusions: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tools": self.tools,
            "categories_used": self.categories_used,
            "overrides_applied": self.overrides_applied,
            "least_privilege_exclusions": self.least_privilege_exclusions,
            "reasoning": self.reasoning,
        }


# =============================================================================
# Tool Selection Functions
# =============================================================================

def get_tools_by_category(category: str) -> list[str]:
    """
    Get all tools in a given category.

    Args:
        category: Tool category (e.g., "filesystem", "browser", "execution")

    Returns:
        List of tool names in that category
    """
    return [
        tool_name
        for tool_name, metadata in AVAILABLE_TOOLS.items()
        if metadata.get("category") == category
    ]


def get_tools_by_privilege(privilege_level: str) -> list[str]:
    """
    Get all tools at a given privilege level.

    Args:
        privilege_level: Privilege level (e.g., "read", "write", "execute")

    Returns:
        List of tool names with that privilege level
    """
    return [
        tool_name
        for tool_name, metadata in AVAILABLE_TOOLS.items()
        if metadata.get("privilege_level") == privilege_level
    ]


def select_tools_for_role(
    role: str,
    *,
    include_browser: bool = False,
    enforce_least_privilege: bool = True,
) -> ToolSelectionResult:
    """
    Select appropriate tools for an agent role.

    Feature #186 Step 2: Octo matches agent role to required tool set.
    Feature #186 Step 5: Tool selection follows least-privilege principle.

    Args:
        role: Agent role or capability (e.g., "test_runner", "ui_testing", "coding")
        include_browser: Whether to include browser/Playwright tools
        enforce_least_privilege: Whether to apply least-privilege exclusions

    Returns:
        ToolSelectionResult with selected tools and reasoning
    """
    role_lower = role.lower().replace("-", "_")

    # Step 1: Determine tool categories for this role
    categories = ROLE_TOOL_CATEGORIES.get(role_lower, ["filesystem", "feature_management"])
    categories_used = list(categories)

    # Optionally include browser tools (Feature #186 Step 4)
    if include_browser and "browser" not in categories:
        categories = list(categories) + ["browser"]
        categories_used.append("browser")

    # Step 2: Gather tools from categories
    tools: set[str] = set()
    for category in categories:
        tools.update(get_tools_by_category(category))

    # Step 3: Apply role-specific overrides
    overrides = ROLE_TOOL_OVERRIDES.get(role_lower, {})
    overrides_applied: dict[str, list[str]] = {}
    least_privilege_exclusions: list[str] = []

    if overrides:
        include_tools = overrides.get("include", [])
        exclude_tools = overrides.get("exclude", [])

        # Add any specific included tools
        if include_tools:
            tools.update(include_tools)
            overrides_applied["include"] = include_tools

        # Remove excluded tools (least-privilege enforcement)
        if exclude_tools and enforce_least_privilege:
            for tool in exclude_tools:
                if tool in tools:
                    tools.remove(tool)
                    least_privilege_exclusions.append(tool)
            overrides_applied["exclude"] = exclude_tools

    # Step 4: Build reasoning string
    reasoning_parts = [
        f"Role '{role}' mapped to categories: {', '.join(categories_used)}",
    ]
    if include_browser:
        reasoning_parts.append("Browser tools included for UI testing")
    if least_privilege_exclusions:
        reasoning_parts.append(
            f"Least-privilege exclusions: {', '.join(least_privilege_exclusions)}"
        )

    return ToolSelectionResult(
        tools=sorted(tools),
        categories_used=categories_used,
        overrides_applied=overrides_applied,
        least_privilege_exclusions=least_privilege_exclusions,
        reasoning="; ".join(reasoning_parts),
    )


def select_tools_for_capability(
    capability: str,
    task_type: str,
    project_context: dict[str, Any] | None = None,
) -> ToolSelectionResult:
    """
    Select appropriate tools based on capability and task type.

    Feature #186: Octo selects appropriate tools for each agent.

    This is the main entry point for tool selection. It combines:
    - Role-based tool selection from ROLE_TOOL_CATEGORIES
    - Task type defaults from TOOL_SETS
    - Role-specific overrides from ROLE_TOOL_OVERRIDES
    - Least-privilege enforcement

    Args:
        capability: Agent capability (e.g., "ui_testing", "api_testing", "coding")
        task_type: Task type (e.g., "testing", "coding", "audit")
        project_context: Optional project context for additional signals

    Returns:
        ToolSelectionResult with selected tools and reasoning
    """
    capability_lower = capability.lower().replace("-", "_")
    task_type_lower = task_type.lower()

    # Determine if browser tools should be included
    include_browser = any(
        kw in capability_lower
        for kw in ["ui", "e2e", "browser", "playwright", "frontend"]
    )

    # Check project context for browser availability
    if project_context:
        tech_stack = project_context.get("tech_stack", [])
        if any("playwright" in str(t).lower() for t in tech_stack):
            include_browser = True

    # First try capability-based selection
    result = select_tools_for_role(
        role=capability_lower,
        include_browser=include_browser,
        enforce_least_privilege=True,
    )

    # If capability didn't match a known role, fall back to task type
    if not result.categories_used or result.categories_used == ["filesystem", "feature_management"]:
        # Fall back to TOOL_SETS from tool_policy.py
        base_tools = TOOL_SETS.get(task_type_lower, TOOL_SETS.get("custom", []))
        result = ToolSelectionResult(
            tools=list(base_tools),
            categories_used=[task_type_lower],
            reasoning=f"Using default TOOL_SETS for task_type '{task_type_lower}'",
        )

        # Apply least-privilege exclusions based on task type
        if task_type_lower == "audit":
            exclusions = ["Write", "Edit", "Bash"]
            result.tools = [t for t in result.tools if t not in exclusions]
            result.least_privilege_exclusions = exclusions
            result.reasoning += "; Audit agents have write/execute tools excluded"

    return result


def get_tool_info(tool_name: str) -> dict[str, Any] | None:
    """
    Get metadata for a specific tool.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool metadata dict or None if not found
    """
    return AVAILABLE_TOOLS.get(tool_name)


def get_all_tool_categories() -> list[str]:
    """Get list of all tool categories."""
    categories = set()
    for metadata in AVAILABLE_TOOLS.values():
        if "category" in metadata:
            categories.add(metadata["category"])
    return sorted(categories)


def is_browser_tool(tool_name: str) -> bool:
    """Check if a tool is a browser/Playwright tool."""
    metadata = AVAILABLE_TOOLS.get(tool_name)
    return metadata is not None and metadata.get("category") == "browser"


def get_browser_tools() -> list[str]:
    """Get all browser/Playwright tools."""
    return get_tools_by_category("browser")


def get_test_runner_tools() -> list[str]:
    """
    Get tools appropriate for test-runner agents.

    Feature #186 Step 3: Test-runner agents get test-related tools.

    Returns:
        List of tool names for test runners
    """
    result = select_tools_for_role("test_runner", enforce_least_privilege=True)
    return result.tools


def get_ui_agent_tools() -> list[str]:
    """
    Get tools appropriate for UI/Playwright agents.

    Feature #186 Step 4: UI agents get browser/Playwright tools when available.

    Returns:
        List of tool names for UI agents
    """
    result = select_tools_for_role("ui_testing", include_browser=True, enforce_least_privilege=True)
    return result.tools
