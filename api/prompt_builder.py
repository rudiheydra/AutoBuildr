"""
Prompt Builder
==============

Functions for building system prompts for AgentSpec execution.

This module handles the construction of system prompts from AgentSpec fields,
including:
- Objective statement
- Context data
- Tool usage guidelines from tool_policy.tool_hints

The HarnessKernel uses these functions to build the system prompt before
passing it to the Claude SDK.
"""

from typing import Any


def extract_tool_hints(tool_policy: dict[str, Any] | None) -> dict[str, str]:
    """
    Extract tool_hints from a tool_policy dictionary.

    The tool_policy structure is:
    {
        "policy_version": "v1",
        "allowed_tools": ["tool1", "tool2", ...],
        "forbidden_patterns": ["pattern1", ...],
        "tool_hints": {"tool_name": "hint text", ...}
    }

    Args:
        tool_policy: The tool_policy JSON from an AgentSpec, or None

    Returns:
        Dictionary mapping tool names to hint strings.
        Returns empty dict if tool_policy is None or has no tool_hints.

    Examples:
        >>> extract_tool_hints(None)
        {}
        >>> extract_tool_hints({"policy_version": "v1"})
        {}
        >>> extract_tool_hints({"tool_hints": {"Read": "Use for files only"}})
        {'Read': 'Use for files only'}
    """
    if tool_policy is None:
        return {}

    if not isinstance(tool_policy, dict):
        return {}

    tool_hints = tool_policy.get("tool_hints")

    if tool_hints is None:
        return {}

    if not isinstance(tool_hints, dict):
        return {}

    # Filter to only string keys and string values
    return {
        str(key): str(value)
        for key, value in tool_hints.items()
        if key is not None and value is not None
    }


def format_tool_hints_as_markdown(tool_hints: dict[str, str]) -> str:
    """
    Format tool hints as a markdown guidelines section.

    Produces a formatted markdown block suitable for injection into
    a system prompt.

    Args:
        tool_hints: Dictionary mapping tool names to hint strings

    Returns:
        Formatted markdown string, or empty string if no hints.

    Examples:
        >>> format_tool_hints_as_markdown({})
        ''
        >>> format_tool_hints_as_markdown({"Read": "Use for files only"})
        '## Tool Usage Guidelines\\n\\n- **Read**: Use for files only'
    """
    if not tool_hints:
        return ""

    lines = ["## Tool Usage Guidelines", ""]

    for tool_name, hint in sorted(tool_hints.items()):
        # Escape any markdown special characters in the hint
        # but keep the structure simple for readability
        lines.append(f"- **{tool_name}**: {hint}")

    return "\n".join(lines)


def build_system_prompt(
    objective: str,
    *,
    context: dict[str, Any] | None = None,
    tool_policy: dict[str, Any] | None = None,
    task_type: str | None = None,
    include_tool_hints: bool = True,
) -> str:
    """
    Build a complete system prompt from AgentSpec fields.

    Combines the objective, optional context summary, and tool usage
    guidelines into a coherent system prompt.

    Args:
        objective: The agent's objective statement (required)
        context: Optional task-specific context dictionary
        tool_policy: Optional tool policy including tool_hints
        task_type: Optional task type (coding, testing, etc.)
        include_tool_hints: Whether to include tool hints section (default True)

    Returns:
        Complete system prompt string

    Example:
        >>> prompt = build_system_prompt(
        ...     "Implement user authentication",
        ...     tool_policy={
        ...         "tool_hints": {
        ...             "feature_mark_passing": "Call only after verification"
        ...         }
        ...     }
        ... )
        >>> "Implement user authentication" in prompt
        True
        >>> "Tool Usage Guidelines" in prompt
        True
    """
    sections = []

    # Add objective as the main instruction
    sections.append("# Objective")
    sections.append("")
    sections.append(objective.strip())

    # Add task type context if provided
    if task_type:
        sections.append("")
        sections.append(f"**Task Type:** {task_type}")

    # Add context section if provided and non-empty
    if context:
        context_lines = _format_context(context)
        if context_lines:
            sections.append("")
            sections.append("## Context")
            sections.append("")
            sections.append(context_lines)

    # Add tool hints section if requested and available
    if include_tool_hints and tool_policy:
        hints = extract_tool_hints(tool_policy)
        hints_markdown = format_tool_hints_as_markdown(hints)
        if hints_markdown:
            sections.append("")
            sections.append(hints_markdown)

    return "\n".join(sections)


def _format_context(context: dict[str, Any]) -> str:
    """
    Format context dictionary as readable text.

    Args:
        context: Context dictionary from AgentSpec

    Returns:
        Formatted context string
    """
    if not context:
        return ""

    lines = []

    for key, value in context.items():
        if value is None:
            continue

        # Format the key nicely
        display_key = key.replace("_", " ").title()

        # Format the value based on type
        if isinstance(value, list):
            if value:
                lines.append(f"**{display_key}:**")
                for item in value:
                    lines.append(f"  - {item}")
        elif isinstance(value, dict):
            # Skip nested dicts for now, too complex for system prompt
            continue
        else:
            lines.append(f"**{display_key}:** {value}")

    return "\n".join(lines)


def inject_tool_hints_into_prompt(
    base_prompt: str,
    tool_policy: dict[str, Any] | None,
) -> str:
    """
    Inject tool hints section into an existing system prompt.

    This function is useful when you have a pre-existing prompt template
    and want to add tool hints without rebuilding the entire prompt.

    The tool hints section is appended at the end of the prompt.

    Args:
        base_prompt: The existing system prompt
        tool_policy: Tool policy containing tool_hints

    Returns:
        Modified prompt with tool hints appended

    Example:
        >>> prompt = inject_tool_hints_into_prompt(
        ...     "You are a coding assistant.",
        ...     {"tool_hints": {"Bash": "Avoid destructive commands"}}
        ... )
        >>> "Tool Usage Guidelines" in prompt
        True
        >>> "Bash" in prompt
        True
    """
    if not tool_policy:
        return base_prompt

    hints = extract_tool_hints(tool_policy)
    hints_markdown = format_tool_hints_as_markdown(hints)

    if not hints_markdown:
        return base_prompt

    # Append the hints section with proper spacing
    return f"{base_prompt.rstrip()}\n\n{hints_markdown}"
