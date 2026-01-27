"""
Task Type Detection from Description
=====================================

Feature #56: Detect appropriate task_type from task description text
using keyword matching heuristics.

This module provides automatic task type detection based on analyzing
the text of task descriptions. It supports the six standard task types:
- coding: Implementation tasks (new features, bug fixes, builds)
- testing: Test creation and verification tasks
- refactoring: Code restructuring without behavior change
- documentation: Documentation creation/updates
- audit: Code review and security analysis
- custom: Tasks that don't fit other categories (default fallback)

Example usage:
    ```python
    from api.task_type_detector import detect_task_type

    # Detect task type from description
    task_type = detect_task_type("Implement user authentication with OAuth2")
    # Returns: "coding"

    # Get detailed scores
    result = detect_task_type_detailed("Write tests for the login module")
    print(result.detected_type)  # "testing"
    print(result.scores)  # {"testing": 3, "coding": 0, ...}
    ```
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants - Keyword Sets for Each Task Type
# =============================================================================

# Keywords for coding tasks (implementation, creation, building)
# Note: Generic words like "write", "module", "code" are avoided to reduce false positives
CODING_KEYWORDS: frozenset[str] = frozenset([
    # Core verbs - specific to coding (standalone add for UI tasks)
    "implement",
    "create",
    "build",
    "develop",
    "construct",
    "add",  # Restored for "add pagination", "add button", etc.
    # Feature-related phrases (more specific)
    "add feature",
    "new feature",
    "add functionality",
    "add capability",
    "feature",
    "functionality",
    "capability",
    # UI elements (coding tasks)
    "button",
    "form",
    "page",
    "modal",
    "component",
    "widget",
    "menu",
    "navigation",
    "dashboard",
    "pagination",
    # Component creation
    "add component",
    "create component",
    "add service",
    "create service",
    "add endpoint",
    "create endpoint",
    # Action words
    "integrate",
    "connect",
    "setup",
    "configure",
    "initialize",
    "scaffold",
    "generate",
    # Fix-related (still coding)
    "fix",
    "patch",
    "repair",
    "bugfix",
    "hotfix",
    "fix bug",
    "bug fix",
    # Enhancement
    "enhance",
    "extend",
    "expand",
    "upgrade",
    # Programming concepts - more specific
    "add class",
    "create class",
    "add function",
    "create function",
    "add method",
    "create method",
    "add handler",
    "create handler",
    "add controller",
    "create controller",
    "add model",
    "create model",
    "database migration",
])

# Keywords for testing tasks (verification, validation)
# High-weight phrases for better discrimination
TESTING_KEYWORDS: frozenset[str] = frozenset([
    # Core phrases - highly specific
    "write test",
    "write tests",
    "add test",
    "add tests",
    "create test",
    "create tests",
    # Core verbs in testing context
    "test",
    "tests",
    "testing",
    "verify",
    "validate",
    # Test types
    "unittest",
    "unit test",
    "unit tests",
    "integration test",
    "integration tests",
    "e2e",
    "end-to-end",
    "regression",
    "regression test",
    "acceptance test",
    "smoke test",
    "sanity test",
    # Testing concepts
    "coverage",
    "test coverage",
    "assertion",
    "assertions",
    "mock",
    "mocking",
    "stub",
    "fixture",
    "fixtures",
    "testcase",
    "test case",
    "test cases",
    "test suite",
    # Tools/frameworks
    "pytest",
    "jest",
    "mocha",
    "vitest",
    "cypress",
    "playwright",
    "selenium",
    # Outcomes
    "passing",
    "failing",
    "expect",
    "should",
])

# Keywords for refactoring tasks (restructuring without changing behavior)
# Strong keywords that indicate code restructuring
REFACTORING_KEYWORDS: frozenset[str] = frozenset([
    # Core verbs - highly specific to refactoring
    "refactor",
    "refactoring",
    "restructure",
    "reorganize",
    "rearrange",
    "rewrite",
    "redesign",
    # Optimization
    "optimize",
    "optimization",
    "simplify",
    "streamline",
    "consolidate",
    "modularize",
    # Clean up - specific phrases (high weight for refactoring)
    "clean up",
    "cleanup",
    "clean code",
    "clean the code",
    "clean up the",
    "tidy up",
    "tidy",
    "polish",
    "improve readability",
    # Removal / Deduplication
    "remove duplication",
    "remove duplicate",
    "duplicate code",
    "code duplication",
    "duplication",
    "deduplicate",
    "eliminate redundancy",
    "reduce complexity",
    "dry",
    # Structural changes
    "extract method",
    "extract function",
    "extract class",
    "inline",
    "move method",
    "rename",
    "split",
    "merge",
    "combine",
    # Technical debt
    "technical debt",
    "tech debt",
    "legacy code",
    "legacy",
    "modernize",
    "update patterns",
    "code smell",
])

# Keywords for documentation tasks (writing docs)
# Note: "documentation" word is a strong signal - appears multiple times for emphasis
DOCUMENTATION_KEYWORDS: frozenset[str] = frozenset([
    # Core verbs - strong signals
    "document",
    "documentation",
    "documenting",
    "doc",
    "docs",
    "describe",
    "explain",
    "illustrate",
    # Strong documentation phrases
    "write documentation",
    "create documentation",
    "update documentation",
    "reference documentation",
    "api reference",
    # Document types
    "readme",
    "changelog",
    "release notes",
    "api docs",
    "api documentation",
    "guide",
    "tutorial",
    "manual",
    "handbook",
    "wiki",
    "specification",
    # Code documentation
    "comment",
    "comments",
    "docstring",
    "docstrings",
    "jsdoc",
    "typedoc",
    "pydoc",
    "annotation",
    "annotate",
    # Content
    "examples",
    "sample",
    "usage",
    "instructions",
    "overview",
    "summary",
    # Documentation actions
    "write documentation",
    "update readme",
    "add comments",
])

# Keywords for audit tasks (review, security analysis)
AUDIT_KEYWORDS: frozenset[str] = frozenset([
    # Core verbs
    "audit",
    "review",
    "analyze",
    "examine",
    "inspect",
    "assess",
    "evaluate",
    # Security
    "security",
    "vulnerability",
    "vulnerabilities",
    "exploit",
    "attack",
    "penetration",
    "pen test",
    "threat",
    "risk",
    "cve",
    # Quality
    "code review",
    "code quality",
    "quality check",
    "lint",
    "linter",
    "static analysis",
    "code smell",
    # Compliance
    "compliance",
    "standard",
    "best practice",
    "best practices",
    "guideline",
    "policy",
    # Performance
    "performance",
    "profiling",
    "benchmark",
    "bottleneck",
    # Issues
    "issue",
    "problem",
    "flaw",
    "weakness",
    "finding",
])

# All keyword sets organized by task type
TASK_TYPE_KEYWORDS: dict[str, frozenset[str]] = {
    "coding": CODING_KEYWORDS,
    "testing": TESTING_KEYWORDS,
    "refactoring": REFACTORING_KEYWORDS,
    "documentation": DOCUMENTATION_KEYWORDS,
    "audit": AUDIT_KEYWORDS,
}

# Valid task types (must match api/agentspec_models.py)
VALID_TASK_TYPES: frozenset[str] = frozenset([
    "coding",
    "testing",
    "refactoring",
    "documentation",
    "audit",
    "custom",
])

# Minimum score threshold to avoid "custom" fallback
# If the highest score is below this, return "custom"
MIN_SCORE_THRESHOLD: int = 1

# Tie-breaker priority (when multiple task types have the same score)
# Earlier in the list = higher priority
TIE_BREAKER_PRIORITY: list[str] = [
    "coding",
    "testing",
    "refactoring",
    "documentation",
    "audit",
]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TaskTypeDetectionResult:
    """
    Result of task type detection with detailed scoring information.

    Attributes:
        detected_type: The detected task type (one of VALID_TASK_TYPES)
        scores: Dictionary mapping each task type to its match score
        matched_keywords: Keywords that contributed to the winning type
        confidence: Confidence level ("high", "medium", "low")
        is_default: True if no clear match was found (defaulted to "custom")
        description_length: Length of the analyzed description
    """
    detected_type: str
    scores: dict[str, int] = field(default_factory=dict)
    matched_keywords: list[str] = field(default_factory=list)
    confidence: str = "medium"
    is_default: bool = False
    description_length: int = 0


# =============================================================================
# Core Detection Functions
# =============================================================================

def normalize_description(description: str) -> str:
    """
    Normalize a task description for keyword matching.

    Converts to lowercase, normalizes whitespace, and handles hyphenation.

    Args:
        description: The raw task description

    Returns:
        Normalized description string
    """
    if not description:
        return ""

    # Convert to lowercase
    text = description.lower()

    # Normalize whitespace (collapse multiple spaces, remove leading/trailing)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def score_task_type(description: str, keywords: frozenset[str]) -> tuple[int, list[str]]:
    """
    Score how well a description matches a set of keywords.

    Uses substring matching to find keywords within the description.
    Each keyword found adds 1 to the score.

    Args:
        description: Normalized task description
        keywords: Set of keywords to match against

    Returns:
        Tuple of (score, list of matched keywords)
    """
    score = 0
    matched = []

    if not description:
        return 0, []

    for keyword in keywords:
        # Check if keyword appears as a word (not part of another word)
        # Use word boundary matching for single words, substring for phrases
        if ' ' in keyword:
            # For phrases, use simple substring matching
            if keyword in description:
                score += 1
                matched.append(keyword)
        else:
            # For single words, use word boundary matching
            # This avoids matching "test" in "contest" or "implement" in "implementation"
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, description):
                score += 1
                matched.append(keyword)

    return score, matched


def calculate_confidence(
    scores: dict[str, int],
    winning_score: int,
    is_default: bool
) -> str:
    """
    Calculate confidence level based on scores.

    Args:
        scores: All task type scores
        winning_score: The score of the winning type
        is_default: Whether the result defaulted to "custom"

    Returns:
        Confidence level: "high", "medium", or "low"
    """
    if is_default:
        return "low"

    # Get second highest score
    sorted_scores = sorted(scores.values(), reverse=True)
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0

    # Calculate margin
    margin = winning_score - second_best

    if winning_score >= 3 and margin >= 2:
        return "high"
    elif winning_score >= 2 and margin >= 1:
        return "medium"
    else:
        return "low"


def detect_task_type(description: str) -> str:
    """
    Detect the most appropriate task type from a task description.

    This is the simple interface that just returns the detected type.
    For detailed scoring information, use detect_task_type_detailed().

    Args:
        description: Natural language task description

    Returns:
        One of: "coding", "testing", "refactoring", "documentation", "audit", "custom"

    Example:
        >>> detect_task_type("Implement user authentication")
        "coding"
        >>> detect_task_type("Write tests for the login module")
        "testing"
        >>> detect_task_type("Clean up the database module")
        "refactoring"
    """
    result = detect_task_type_detailed(description)
    return result.detected_type


def detect_task_type_detailed(description: str) -> TaskTypeDetectionResult:
    """
    Detect task type with detailed scoring information.

    Analyzes the description against all keyword sets and returns
    comprehensive results including scores and confidence.

    Args:
        description: Natural language task description

    Returns:
        TaskTypeDetectionResult with full details

    Example:
        >>> result = detect_task_type_detailed("Implement user auth with tests")
        >>> print(result.detected_type)  # "coding"
        >>> print(result.scores)  # {"coding": 2, "testing": 1, ...}
        >>> print(result.confidence)  # "medium"
    """
    # Handle empty/None description
    if not description or not description.strip():
        _logger.debug("Empty description, defaulting to 'custom'")
        return TaskTypeDetectionResult(
            detected_type="custom",
            scores={t: 0 for t in TASK_TYPE_KEYWORDS},
            matched_keywords=[],
            confidence="low",
            is_default=True,
            description_length=0,
        )

    # Normalize the description
    normalized = normalize_description(description)
    description_length = len(normalized)

    _logger.debug("Detecting task type for: %r", normalized[:100])

    # Score against each task type
    scores: dict[str, int] = {}
    all_matches: dict[str, list[str]] = {}

    for task_type, keywords in TASK_TYPE_KEYWORDS.items():
        score, matched = score_task_type(normalized, keywords)
        scores[task_type] = score
        all_matches[task_type] = matched
        _logger.debug("  %s: score=%d, matches=%s", task_type, score, matched)

    # Find the highest scoring type
    max_score = max(scores.values())

    # Check if we have a clear winner above threshold
    if max_score < MIN_SCORE_THRESHOLD:
        _logger.debug("No score above threshold (%d), defaulting to 'custom'", MIN_SCORE_THRESHOLD)
        return TaskTypeDetectionResult(
            detected_type="custom",
            scores=scores,
            matched_keywords=[],
            confidence="low",
            is_default=True,
            description_length=description_length,
        )

    # Find all types with the max score (potential tie)
    max_types = [t for t, s in scores.items() if s == max_score]

    # Use tie-breaker if needed
    if len(max_types) > 1:
        _logger.debug("Tie between %s, using priority", max_types)
        for priority_type in TIE_BREAKER_PRIORITY:
            if priority_type in max_types:
                detected_type = priority_type
                break
        else:
            # Fallback (shouldn't happen given our priority list)
            detected_type = max_types[0]
    else:
        detected_type = max_types[0]

    # Calculate confidence
    confidence = calculate_confidence(scores, max_score, is_default=False)

    _logger.info(
        "Detected task type: %s (score=%d, confidence=%s)",
        detected_type, max_score, confidence
    )

    return TaskTypeDetectionResult(
        detected_type=detected_type,
        scores=scores,
        matched_keywords=all_matches[detected_type],
        confidence=confidence,
        is_default=False,
        description_length=description_length,
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_keywords_for_type(task_type: str) -> frozenset[str]:
    """
    Get the keyword set for a specific task type.

    Args:
        task_type: One of the valid task types

    Returns:
        Frozenset of keywords for that type

    Raises:
        ValueError: If task_type is not valid or has no keywords (e.g., "custom")
    """
    if task_type not in VALID_TASK_TYPES:
        raise ValueError(f"Invalid task type: {task_type}. Must be one of {sorted(VALID_TASK_TYPES)}")

    if task_type == "custom":
        raise ValueError("'custom' task type has no associated keywords")

    return TASK_TYPE_KEYWORDS[task_type]


def get_all_keyword_sets() -> dict[str, frozenset[str]]:
    """
    Get all keyword sets for all task types.

    Returns:
        Dictionary mapping task types to their keyword sets
    """
    return dict(TASK_TYPE_KEYWORDS)


def get_valid_task_types() -> frozenset[str]:
    """
    Get the set of valid task types.

    Returns:
        Frozenset of valid task type strings
    """
    return VALID_TASK_TYPES


def is_valid_task_type(task_type: str) -> bool:
    """
    Check if a string is a valid task type.

    Args:
        task_type: String to check

    Returns:
        True if valid, False otherwise
    """
    return task_type in VALID_TASK_TYPES


def explain_detection(description: str) -> str:
    """
    Get a human-readable explanation of the detection result.

    Args:
        description: Task description to analyze

    Returns:
        Multi-line string explaining the detection
    """
    result = detect_task_type_detailed(description)

    lines = [
        f"Task Type Detection Analysis",
        f"============================",
        f"Description: {description[:100]}{'...' if len(description) > 100 else ''}",
        f"",
        f"Detected Type: {result.detected_type.upper()}",
        f"Confidence: {result.confidence}",
        f"Is Default: {result.is_default}",
        f"",
        f"Scores by Type:",
    ]

    # Sort scores descending
    sorted_scores = sorted(result.scores.items(), key=lambda x: x[1], reverse=True)
    for task_type, score in sorted_scores:
        marker = " <--" if task_type == result.detected_type else ""
        lines.append(f"  {task_type}: {score}{marker}")

    if result.matched_keywords:
        lines.append("")
        lines.append(f"Matched Keywords for '{result.detected_type}':")
        for kw in result.matched_keywords:
            lines.append(f"  - {kw}")

    return "\n".join(lines)
