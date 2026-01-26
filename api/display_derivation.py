"""
Display Name and Icon Derivation
=================================

Derives human-friendly display_name and icon from AgentSpec objective and task_type.

This module provides utilities for generating UI-friendly presentation data from
AgentSpec fields, including:
- Extracting and truncating display names from objectives
- Mapping task types to appropriate icons
- Selecting mascot names from the existing pool

Usage:
    from api.display_derivation import derive_display_name, derive_icon, derive_mascot_name

    # Derive display name from objective
    display_name = derive_display_name("Implement user login with email/password. This feature...")
    # Returns: "Implement user login with email/password"

    # Derive icon from task type
    icon = derive_icon("coding")
    # Returns: "hammer"

    # Allow context override
    icon = derive_icon("coding", context={"icon": "wrench"})
    # Returns: "wrench"

    # Get mascot name
    mascot = derive_mascot_name(feature_id=42)
    # Returns: "Octo" (or another from pool based on hash)
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


# =============================================================================
# Constants
# =============================================================================

# Maximum length for display_name (with ellipsis)
DISPLAY_NAME_MAX_LENGTH = 100

# Ellipsis suffix when truncation occurs
ELLIPSIS = "..."

# Task type to icon mapping
# Icons use common emoji/icon identifiers for UI flexibility
TASK_TYPE_ICONS: dict[str, str] = {
    "coding": "hammer",
    "testing": "flask",
    "refactoring": "recycle",
    "documentation": "book",
    "audit": "shield",
    "custom": "gear",
}

# Default icon when task type not found
DEFAULT_ICON = "gear"

# Mascot pool - same as used in server/schemas.py and ui/src/lib/types.ts
MASCOT_POOL = [
    "Spark", "Fizz", "Octo", "Hoot", "Buzz",      # Original 5
    "Pixel", "Byte", "Nova", "Chip", "Bolt",      # Tech-inspired
    "Dash", "Zap", "Gizmo", "Turbo", "Blip",      # Energetic
    "Neon", "Widget", "Zippy", "Quirk", "Flux",   # Playful
]


# =============================================================================
# Display Name Derivation
# =============================================================================

def extract_first_sentence(text: str) -> str:
    """
    Extract the first sentence from a text string.

    A sentence ends at:
    - Period followed by space or end of string
    - Exclamation mark followed by space or end of string
    - Question mark followed by space or end of string
    - Newline character

    Args:
        text: The input text to extract from

    Returns:
        The first sentence, stripped of leading/trailing whitespace.
        If no sentence boundary is found, returns the entire text.

    Examples:
        >>> extract_first_sentence("Implement login. Then add logout.")
        'Implement login.'
        >>> extract_first_sentence("Build the feature! It's important.")
        'Build the feature!'
        >>> extract_first_sentence("No period here")
        'No period here'
    """
    if not text:
        return ""

    # Clean up the text - remove leading/trailing whitespace
    text = text.strip()

    if not text:
        return ""

    # Pattern to find first sentence boundary
    # Matches: period/exclamation/question followed by space or end, or newline
    # Uses non-greedy match to get the shortest valid sentence
    pattern = r'^(.*?(?:[.!?](?:\s|$)|\n))'

    match = re.match(pattern, text, re.DOTALL)

    if match:
        sentence = match.group(1).strip()
        # Remove trailing newline if present but keep punctuation
        sentence = sentence.rstrip('\n')
        return sentence

    # No sentence boundary found - return entire text (will be truncated if needed)
    return text


def truncate_with_ellipsis(text: str, max_length: int = DISPLAY_NAME_MAX_LENGTH) -> str:
    """
    Truncate text to max_length with ellipsis if needed.

    Args:
        text: The text to truncate
        max_length: Maximum length including ellipsis (default 100)

    Returns:
        Text truncated with "..." if it exceeds max_length,
        otherwise the original text.

    Examples:
        >>> truncate_with_ellipsis("Short text", 100)
        'Short text'
        >>> truncate_with_ellipsis("A" * 150, 100)
        'AAA...AAA...'  # 97 A's + "..."
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    # Truncate and add ellipsis
    # Leave room for the ellipsis
    truncate_at = max_length - len(ELLIPSIS)

    if truncate_at <= 0:
        return ELLIPSIS[:max_length]

    return text[:truncate_at] + ELLIPSIS


def derive_display_name(
    objective: str,
    max_length: int = DISPLAY_NAME_MAX_LENGTH
) -> str:
    """
    Derive a human-friendly display_name from an AgentSpec objective.

    Process:
    1. Extract the first sentence of the objective
    2. Truncate to max_length with ellipsis if needed

    Args:
        objective: The objective text to derive from
        max_length: Maximum length for display name (default 100)

    Returns:
        A human-friendly display name derived from the objective.
        Empty string if objective is None or empty.

    Examples:
        >>> derive_display_name("Implement user authentication with OAuth2. Then add password reset.")
        'Implement user authentication with OAuth2.'
        >>> derive_display_name("A" * 200)
        'AAA...AAA...'  # Truncated to 100 chars
    """
    if not objective:
        return ""

    # Step 1: Extract first sentence
    first_sentence = extract_first_sentence(objective)

    # Step 2: Truncate if needed
    return truncate_with_ellipsis(first_sentence, max_length)


# =============================================================================
# Icon Derivation
# =============================================================================

def derive_icon(
    task_type: str,
    context: dict[str, Any] | None = None
) -> str:
    """
    Derive an icon from task_type, allowing context override.

    Icon mapping:
    - coding -> hammer
    - testing -> flask
    - refactoring -> recycle
    - documentation -> book
    - audit -> shield
    - custom -> gear (default)

    Args:
        task_type: The task type (coding, testing, etc.)
        context: Optional context dict that may contain an "icon" override

    Returns:
        The icon identifier (emoji name or icon name).
        Returns context["icon"] if present and non-empty,
        otherwise maps task_type to icon,
        otherwise returns DEFAULT_ICON.

    Examples:
        >>> derive_icon("coding")
        'hammer'
        >>> derive_icon("coding", context={"icon": "wrench"})
        'wrench'
        >>> derive_icon("unknown_type")
        'gear'
    """
    # Check for context override first
    if context and isinstance(context, dict):
        icon_override = context.get("icon")
        if icon_override and isinstance(icon_override, str) and icon_override.strip():
            return icon_override.strip()

    # Map task_type to icon
    if task_type and isinstance(task_type, str):
        normalized_type = task_type.lower().strip()
        return TASK_TYPE_ICONS.get(normalized_type, DEFAULT_ICON)

    return DEFAULT_ICON


def get_task_type_icons() -> dict[str, str]:
    """
    Get a copy of the task_type to icon mapping.

    Returns:
        Dictionary mapping task types to icons.
    """
    return TASK_TYPE_ICONS.copy()


# =============================================================================
# Mascot Name Derivation
# =============================================================================

def derive_mascot_name(
    feature_id: int | None = None,
    spec_id: str | None = None,
    context: dict[str, Any] | None = None
) -> str:
    """
    Select a mascot name from the existing pool.

    The mascot is selected deterministically based on:
    1. context["mascot"] if provided (explicit override)
    2. Hash of spec_id if provided (consistent for same spec)
    3. feature_id modulo pool size if provided
    4. First mascot in pool as fallback

    Args:
        feature_id: Optional feature ID for deterministic selection
        spec_id: Optional spec UUID for deterministic selection
        context: Optional context dict that may contain a "mascot" override

    Returns:
        A mascot name from the pool.

    Examples:
        >>> derive_mascot_name(feature_id=0)
        'Spark'
        >>> derive_mascot_name(feature_id=5)
        'Pixel'
        >>> derive_mascot_name(context={"mascot": "Custom"})
        'Custom'
    """
    # Check for context override first
    if context and isinstance(context, dict):
        mascot_override = context.get("mascot")
        if mascot_override and isinstance(mascot_override, str) and mascot_override.strip():
            return mascot_override.strip()

    pool_size = len(MASCOT_POOL)

    # Use spec_id hash if provided (most stable for reruns)
    if spec_id and isinstance(spec_id, str):
        # Use MD5 hash to get a consistent index
        hash_bytes = hashlib.md5(spec_id.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], 'big')
        return MASCOT_POOL[hash_int % pool_size]

    # Use feature_id if provided
    if feature_id is not None and isinstance(feature_id, int):
        return MASCOT_POOL[feature_id % pool_size]

    # Fallback to first mascot
    return MASCOT_POOL[0]


def get_mascot_pool() -> list[str]:
    """
    Get a copy of the mascot pool.

    Returns:
        List of mascot names.
    """
    return MASCOT_POOL.copy()


# =============================================================================
# Combined Derivation
# =============================================================================

def derive_display_properties(
    objective: str,
    task_type: str,
    context: dict[str, Any] | None = None,
    feature_id: int | None = None,
    spec_id: str | None = None,
    max_display_name_length: int = DISPLAY_NAME_MAX_LENGTH
) -> dict[str, str]:
    """
    Derive all display properties from AgentSpec fields.

    Combines derive_display_name, derive_icon, and derive_mascot_name
    into a single convenient function.

    Args:
        objective: The objective text
        task_type: The task type (coding, testing, etc.)
        context: Optional context dict with potential overrides
        feature_id: Optional feature ID for mascot selection
        spec_id: Optional spec UUID for mascot selection
        max_display_name_length: Max length for display name (default 100)

    Returns:
        Dictionary with keys:
        - display_name: Derived from objective
        - icon: Derived from task_type (with context override)
        - mascot_name: Selected from pool

    Example:
        >>> derive_display_properties(
        ...     objective="Implement login feature. Add validation.",
        ...     task_type="coding",
        ...     feature_id=42
        ... )
        {'display_name': 'Implement login feature.', 'icon': 'hammer', 'mascot_name': 'Octo'}
    """
    return {
        "display_name": derive_display_name(objective, max_display_name_length),
        "icon": derive_icon(task_type, context),
        "mascot_name": derive_mascot_name(feature_id, spec_id, context),
    }
