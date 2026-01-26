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

__all__ = [
    "Feature",
    "create_database",
    "get_database_path",
    # Prompt builder exports
    "build_system_prompt",
    "extract_tool_hints",
    "format_tool_hints_as_markdown",
    "inject_tool_hints_into_prompt",
]
