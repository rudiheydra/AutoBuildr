"""
Unique Spec Name Generation
============================

Generate unique, URL-safe spec names from objectives with collision handling.

This module provides utilities for generating machine-friendly spec names from
AgentSpec objectives and task types. The generated names are:
- URL-safe (lowercase, hyphens allowed, no special characters)
- Unique (collision detection and numeric suffix appending)
- Limited to 100 characters
- Prefixed with task type for categorization

Usage:
    from api.spec_name_generator import generate_unique_spec_name, generate_spec_name

    # Generate without collision check (for testing)
    name = generate_spec_name("Implement user authentication", "coding")
    # Returns: "coding-implement-user-authentication-1706345600"

    # Generate with collision check (for production)
    name = generate_unique_spec_name(
        session=db_session,
        objective="Implement user authentication",
        task_type="coding"
    )
    # Returns: "coding-implement-user-authentication-1706345600"
    # Or if collision: "coding-implement-user-authentication-1706345600-1"
"""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Setup logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Maximum length for spec name
SPEC_NAME_MAX_LENGTH = 100

# Minimum length for keyword slugs (before prefix and timestamp)
MIN_KEYWORD_SLUG_LENGTH = 3

# Stop words to filter out when extracting keywords
STOP_WORDS = frozenset({
    # Articles
    "a", "an", "the",
    # Prepositions
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    # Conjunctions
    "and", "or", "but", "nor", "so", "yet",
    # Pronouns
    "i", "you", "he", "she", "it", "we", "they", "this", "that", "these", "those",
    # Common verbs that are too generic
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "must", "shall",
    # Other common words
    "can", "need", "needs", "please", "also", "just", "only",
})

# Characters allowed in spec name (besides alphanumeric)
ALLOWED_SPECIAL_CHARS = "-"

# Regex pattern for valid spec name
# Must start and end with alphanumeric, can contain hyphens in between
SPEC_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$')


# =============================================================================
# Keyword Extraction
# =============================================================================

def extract_keywords(objective: str, max_keywords: int = 6) -> list[str]:
    """
    Extract meaningful keywords from an objective string.

    Process:
    1. Convert to lowercase
    2. Remove special characters (keep alphanumeric and spaces)
    3. Split into words
    4. Filter out stop words
    5. Keep first N keywords (most significant ones typically at beginning)

    Args:
        objective: The objective text to extract keywords from
        max_keywords: Maximum number of keywords to return (default 6)

    Returns:
        List of lowercase keywords, limited to max_keywords.
        Empty list if objective is None or contains no valid keywords.

    Examples:
        >>> extract_keywords("Implement user authentication with OAuth2")
        ['implement', 'user', 'authentication', 'oauth2']
        >>> extract_keywords("Fix the login bug in the authentication module")
        ['fix', 'login', 'bug', 'authentication', 'module']
    """
    if not objective:
        return []

    # Convert to lowercase
    text = objective.lower()

    # Remove special characters, keep alphanumeric and spaces
    text = re.sub(r'[^a-z0-9\s]', ' ', text)

    # Split into words
    words = text.split()

    # Filter out stop words and very short words
    keywords = [
        word for word in words
        if word not in STOP_WORDS and len(word) >= 2
    ]

    # Return first N keywords
    return keywords[:max_keywords]


# =============================================================================
# Slug Generation
# =============================================================================

def generate_slug(keywords: list[str], max_length: int = 50) -> str:
    """
    Generate a URL-safe slug from keywords.

    Args:
        keywords: List of keywords to join
        max_length: Maximum length for the slug (default 50)

    Returns:
        Hyphen-joined, lowercase slug of keywords.
        Returns "spec" if no keywords provided.

    Examples:
        >>> generate_slug(['implement', 'user', 'authentication'])
        'implement-user-authentication'
        >>> generate_slug([])
        'spec'
    """
    if not keywords:
        return "spec"

    # Join keywords with hyphens
    slug = "-".join(keywords)

    # Truncate if too long, but try to break at word boundary
    if len(slug) > max_length:
        # Find last hyphen before max_length
        truncated = slug[:max_length]
        last_hyphen = truncated.rfind('-')
        if last_hyphen > MIN_KEYWORD_SLUG_LENGTH:
            slug = truncated[:last_hyphen]
        else:
            slug = truncated

    return slug


def normalize_slug(text: str) -> str:
    """
    Normalize a string to a valid slug format.

    Args:
        text: Text to normalize

    Returns:
        Normalized slug (lowercase, only alphanumeric and hyphens,
        no leading/trailing/consecutive hyphens).

    Examples:
        >>> normalize_slug("Hello World!")
        'hello-world'
        >>> normalize_slug("test--multiple---hyphens")
        'test-multiple-hyphens'
    """
    if not text:
        return ""

    # Convert to lowercase
    slug = text.lower()

    # Replace non-alphanumeric with hyphens
    slug = re.sub(r'[^a-z0-9]', '-', slug)

    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)

    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    return slug


# =============================================================================
# Timestamp/Sequence Generation
# =============================================================================

def generate_timestamp_suffix() -> str:
    """
    Generate a timestamp suffix for uniqueness.

    Returns:
        Unix timestamp as string.

    Examples:
        >>> len(generate_timestamp_suffix())
        10  # Unix timestamp is 10 digits
    """
    return str(int(time.time()))


def generate_sequence_suffix(base_name: str, existing_names: set[str]) -> int:
    """
    Find the next available sequence number for a base name.

    Checks for existing names with numeric suffixes and returns
    the next available number.

    Args:
        base_name: The base name without sequence suffix
        existing_names: Set of existing spec names

    Returns:
        Next available sequence number (1, 2, 3, ...)

    Examples:
        >>> generate_sequence_suffix("my-spec", {"my-spec", "my-spec-1"})
        2
        >>> generate_sequence_suffix("my-spec", set())
        1
    """
    sequence = 1
    pattern = re.compile(rf'^{re.escape(base_name)}-(\d+)$')

    for name in existing_names:
        match = pattern.match(name)
        if match:
            existing_seq = int(match.group(1))
            sequence = max(sequence, existing_seq + 1)

    return sequence


# =============================================================================
# Spec Name Generation
# =============================================================================

def generate_spec_name(
    objective: str,
    task_type: str,
    *,
    timestamp: str | None = None,
    max_length: int = SPEC_NAME_MAX_LENGTH,
) -> str:
    """
    Generate a spec name from objective and task type.

    Process:
    1. Extract keywords from objective
    2. Generate slug from keywords
    3. Prepend task_type prefix
    4. Add timestamp for uniqueness
    5. Limit to max_length chars

    Args:
        objective: The objective text
        task_type: The task type (coding, testing, etc.)
        timestamp: Optional timestamp override (defaults to current time)
        max_length: Maximum name length (default 100)

    Returns:
        A URL-safe spec name in format: {task_type}-{keywords}-{timestamp}

    Examples:
        >>> generate_spec_name("Implement login", "coding")
        'coding-implement-login-1706345600'
    """
    # Extract keywords
    keywords = extract_keywords(objective)

    # Generate slug (leave room for prefix, timestamp, and hyphens)
    # Format: {task_type}-{slug}-{timestamp}
    # Reserve: len(task_type) + 1 (hyphen) + 1 (hyphen) + 10 (timestamp)
    task_prefix = normalize_slug(task_type) or "custom"
    ts = timestamp or generate_timestamp_suffix()

    reserved_length = len(task_prefix) + 1 + 1 + len(ts)
    slug_max_length = max_length - reserved_length

    if slug_max_length < MIN_KEYWORD_SLUG_LENGTH:
        slug_max_length = MIN_KEYWORD_SLUG_LENGTH

    slug = generate_slug(keywords, max_length=slug_max_length)

    # Combine parts
    name = f"{task_prefix}-{slug}-{ts}"

    # Final truncation if still too long
    if len(name) > max_length:
        name = name[:max_length]
        # Ensure doesn't end with hyphen
        name = name.rstrip('-')

    return name


def validate_spec_name(name: str) -> bool:
    """
    Validate that a spec name matches the required format.

    Args:
        name: The spec name to validate

    Returns:
        True if valid, False otherwise.

    Examples:
        >>> validate_spec_name("coding-implement-login-123")
        True
        >>> validate_spec_name("INVALID_NAME!")
        False
    """
    if not name:
        return False

    if len(name) > SPEC_NAME_MAX_LENGTH:
        return False

    return bool(SPEC_NAME_PATTERN.match(name))


# =============================================================================
# Collision Detection and Unique Name Generation
# =============================================================================

def check_name_exists(session: "Session", name: str) -> bool:
    """
    Check if a spec name already exists in the database.

    Args:
        session: SQLAlchemy session
        name: Spec name to check

    Returns:
        True if name exists, False otherwise.
    """
    from api.agentspec_models import AgentSpec

    exists = session.query(AgentSpec).filter(AgentSpec.name == name).first()
    return exists is not None


def get_existing_names_with_prefix(session: "Session", prefix: str) -> set[str]:
    """
    Get all existing spec names that start with a given prefix.

    Args:
        session: SQLAlchemy session
        prefix: Name prefix to search for

    Returns:
        Set of existing spec names with the prefix.
    """
    from api.agentspec_models import AgentSpec

    specs = session.query(AgentSpec.name).filter(
        AgentSpec.name.like(f"{prefix}%")
    ).all()

    return {spec.name for spec in specs}


def generate_unique_spec_name(
    session: "Session",
    objective: str,
    task_type: str,
    *,
    max_retries: int = 100,
    max_length: int = SPEC_NAME_MAX_LENGTH,
) -> str:
    """
    Generate a unique spec name with collision handling.

    Process:
    1. Generate base name from objective and task type
    2. Check if name exists in database
    3. If collision, append numeric suffix (-1, -2, etc.)
    4. Repeat until unique name found or max_retries reached

    Args:
        session: SQLAlchemy session for checking existing names
        objective: The objective text
        task_type: The task type (coding, testing, etc.)
        max_retries: Maximum collision resolution attempts (default 100)
        max_length: Maximum name length (default 100)

    Returns:
        A unique, URL-safe spec name.

    Raises:
        ValueError: If unable to generate unique name within max_retries.

    Examples:
        >>> generate_unique_spec_name(session, "Implement login", "coding")
        'coding-implement-login-1706345600'

        # If above exists:
        >>> generate_unique_spec_name(session, "Implement login", "coding")
        'coding-implement-login-1706345600-1'
    """
    # Generate initial name
    base_name = generate_spec_name(objective, task_type, max_length=max_length)

    # Check if unique
    if not check_name_exists(session, base_name):
        _logger.debug(f"Generated unique spec name: {base_name}")
        return base_name

    # Name exists - need to handle collision
    _logger.info(f"Spec name collision detected: {base_name}")

    # Get all existing names with same prefix for efficient suffix calculation
    existing_names = get_existing_names_with_prefix(session, base_name)
    existing_names.add(base_name)  # Include the base name

    # Find next available sequence
    sequence = generate_sequence_suffix(base_name, existing_names)

    for attempt in range(max_retries):
        # Generate name with sequence suffix
        suffix = f"-{sequence}"

        # Check if suffix fits within max_length
        if len(base_name) + len(suffix) > max_length:
            # Need to truncate base name to fit suffix
            truncated_base = base_name[:max_length - len(suffix)]
            truncated_base = truncated_base.rstrip('-')
            candidate_name = f"{truncated_base}{suffix}"
        else:
            candidate_name = f"{base_name}{suffix}"

        # Validate format
        if not validate_spec_name(candidate_name):
            _logger.warning(f"Generated invalid spec name: {candidate_name}")
            sequence += 1
            continue

        # Check if unique
        if not check_name_exists(session, candidate_name):
            _logger.debug(f"Generated unique spec name with suffix: {candidate_name}")
            return candidate_name

        # Still collision, try next sequence
        sequence += 1
        existing_names.add(candidate_name)

    # Exhausted retries
    raise ValueError(
        f"Unable to generate unique spec name after {max_retries} attempts. "
        f"Base name: {base_name}"
    )


# =============================================================================
# Convenience Functions
# =============================================================================

def generate_spec_name_for_feature(
    session: "Session",
    feature_id: int,
    feature_name: str,
    feature_category: str,
    task_type: str = "coding",
) -> str:
    """
    Generate a unique spec name for a Feature.

    Convenience function that constructs an objective from feature details
    and generates a unique spec name.

    Args:
        session: SQLAlchemy session
        feature_id: Feature ID
        feature_name: Feature name
        feature_category: Feature category
        task_type: Task type (defaults to "coding")

    Returns:
        A unique spec name incorporating feature details.

    Examples:
        >>> generate_spec_name_for_feature(session, 42, "User Login", "Authentication")
        'coding-user-login-authentication-1706345600'
    """
    # Construct objective from feature details
    objective = f"{feature_name} {feature_category}"

    return generate_unique_spec_name(
        session=session,
        objective=objective,
        task_type=task_type,
    )
