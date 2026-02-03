"""
Agent Archetypes for Octo Agent Generation (Feature #191)
=========================================================

This module defines common agent archetypes that serve as templates for agent generation.
Octo uses these archetypes to quickly generate well-configured agents for common patterns.

Feature #191: Octo uses agent archetypes for common patterns

Key Features:
- AGENT_ARCHETYPES: Catalog of predefined agent archetypes (coder, test-runner, auditor, reviewer)
- Each archetype has default tools, skills, responsibilities, and model recommendations
- map_capability_to_archetype(): Maps capabilities to matching archetypes
- customize_archetype(): Customizes an archetype based on project-specific needs
- is_custom_agent_needed(): Determines when no archetype fits

Usage:
    from api.archetypes import (
        AGENT_ARCHETYPES,
        get_archetype,
        map_capability_to_archetype,
        customize_archetype,
        create_agent_from_archetype,
    )

    # Get an archetype
    coder = get_archetype("coder")
    print(f"Default tools: {coder.default_tools}")

    # Map capability to archetype
    result = map_capability_to_archetype("e2e_testing")
    print(f"Matched: {result.archetype_name}, confidence: {result.confidence}")

    # Customize archetype for project
    customized = customize_archetype(
        archetype_name="coder",
        project_context={"tech_stack": ["React", "TypeScript"]},
    )
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)


# =============================================================================
# Archetype Data Structures (Feature #191 Step 1)
# =============================================================================

@dataclass
class AgentArchetype:
    """
    Definition of an agent archetype.

    Feature #191 Step 1: Define agent archetypes: coder, test-runner, auditor, reviewer
    Feature #191 Step 2: Each archetype has default tools, skills, and responsibilities

    An archetype serves as a template for generating agents with common configurations.
    It includes:
    - Default tools the agent should have access to
    - Skills/domains the agent specializes in
    - Responsibilities describing what the agent does
    - Model recommendation based on typical complexity
    - Task type for spec generation

    Attributes:
        name: Unique identifier for the archetype (e.g., "coder", "test-runner")
        display_name: Human-readable name for the archetype
        description: Detailed description of the archetype's purpose
        default_tools: List of tools this archetype typically needs
        default_skills: List of skills/domains this archetype specializes in
        responsibilities: List of responsibilities describing what the agent does
        recommended_model: Recommended Claude model (sonnet, opus, haiku)
        task_type: Default task type for spec generation
        icon: Emoji icon for the archetype
        capability_keywords: Keywords in capabilities that map to this archetype
        excluded_tools: Tools that should NOT be given to this archetype (least-privilege)
        max_turns: Default max_turns budget for this archetype
        timeout_seconds: Default timeout budget for this archetype
    """
    name: str
    display_name: str
    description: str
    default_tools: list[str]
    default_skills: list[str]
    responsibilities: list[str]
    recommended_model: str = "sonnet"
    task_type: str = "coding"
    icon: str = "🤖"
    capability_keywords: list[str] = field(default_factory=list)
    excluded_tools: list[str] = field(default_factory=list)
    max_turns: int = 100
    timeout_seconds: int = 1800

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "default_tools": self.default_tools,
            "default_skills": self.default_skills,
            "responsibilities": self.responsibilities,
            "recommended_model": self.recommended_model,
            "task_type": self.task_type,
            "icon": self.icon,
            "capability_keywords": self.capability_keywords,
            "excluded_tools": self.excluded_tools,
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentArchetype":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            display_name=data.get("display_name", ""),
            description=data.get("description", ""),
            default_tools=data.get("default_tools", []),
            default_skills=data.get("default_skills", []),
            responsibilities=data.get("responsibilities", []),
            recommended_model=data.get("recommended_model", "sonnet"),
            task_type=data.get("task_type", "coding"),
            icon=data.get("icon", "🤖"),
            capability_keywords=data.get("capability_keywords", []),
            excluded_tools=data.get("excluded_tools", []),
            max_turns=data.get("max_turns", 100),
            timeout_seconds=data.get("timeout_seconds", 1800),
        )


@dataclass
class ArchetypeMatchResult:
    """
    Result of mapping a capability to an archetype.

    Feature #191 Step 3: Octo recognizes when a capability maps to an archetype

    Attributes:
        archetype_name: Name of the matched archetype (None if no match)
        archetype: The matched AgentArchetype object (None if no match)
        confidence: Confidence score (0.0 to 1.0) of the match
        matched_keywords: Keywords that contributed to the match
        is_custom_needed: True if no archetype fits and custom agent is needed
        reason: Human-readable explanation of the match/non-match
    """
    archetype_name: str | None
    archetype: AgentArchetype | None
    confidence: float
    matched_keywords: list[str] = field(default_factory=list)
    is_custom_needed: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "archetype_name": self.archetype_name,
            "archetype": self.archetype.to_dict() if self.archetype else None,
            "confidence": self.confidence,
            "matched_keywords": self.matched_keywords,
            "is_custom_needed": self.is_custom_needed,
            "reason": self.reason,
        }


@dataclass
class CustomizedArchetype:
    """
    Result of customizing an archetype for a specific project.

    Feature #191 Step 4: Archetypes customized based on project-specific needs

    Attributes:
        base_archetype: The base archetype that was customized
        tools: Final list of tools after customization
        skills: Final list of skills after customization
        responsibilities: Final list of responsibilities after customization
        model: Final model selection after customization
        customizations_applied: List of customizations that were applied
    """
    base_archetype: AgentArchetype
    tools: list[str]
    skills: list[str]
    responsibilities: list[str]
    model: str
    max_turns: int
    timeout_seconds: int
    customizations_applied: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base_archetype": self.base_archetype.to_dict(),
            "tools": self.tools,
            "skills": self.skills,
            "responsibilities": self.responsibilities,
            "model": self.model,
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
            "customizations_applied": self.customizations_applied,
        }


# =============================================================================
# Agent Archetypes Catalog (Feature #191 Step 1 & 2)
# =============================================================================

# Feature #191 Step 1: Define agent archetypes: coder, test-runner, auditor, reviewer
# Feature #191 Step 2: Each archetype has default tools, skills, and responsibilities

AGENT_ARCHETYPES: dict[str, AgentArchetype] = {
    # ==========================================================================
    # CODER Archetype
    # ==========================================================================
    "coder": AgentArchetype(
        name="coder",
        display_name="Coder Agent",
        description=(
            "A full-stack coding agent capable of implementing features, fixing bugs, "
            "and refactoring code. Uses sonnet model for balanced speed and capability."
        ),
        default_tools=[
            "Read", "Write", "Edit", "Glob", "Grep", "Bash",
            "WebFetch", "WebSearch", "TodoRead", "TodoWrite",
        ],
        default_skills=[
            "full-stack development",
            "bug fixing",
            "code refactoring",
            "API implementation",
            "database operations",
            "git operations",
        ],
        responsibilities=[
            "Implement new features according to specifications",
            "Fix bugs and resolve issues in existing code",
            "Refactor code to improve quality and maintainability",
            "Write clean, documented, and tested code",
            "Follow project coding standards and best practices",
        ],
        recommended_model="sonnet",
        task_type="coding",
        icon="💻",
        capability_keywords=[
            "coding", "coder", "implement", "develop", "build", "create",
            "feature", "bug", "fix", "refactor", "api", "backend", "frontend",
            "fullstack", "full-stack", "development",
        ],
        excluded_tools=[],  # Coder gets full tool access
        max_turns=100,
        timeout_seconds=1800,
    ),

    # ==========================================================================
    # TEST-RUNNER Archetype (Feature #205)
    # ==========================================================================
    "test-runner": AgentArchetype(
        name="test-runner",
        display_name="Test Runner Agent",
        description=(
            "A testing agent specialized in writing, running and validating tests. "
            "Can write test cases, execute test suites, analyze results, and report coverage. "
            "Uses sonnet model for balanced speed and capability in test execution and analysis."
        ),
        default_tools=[
            # Feature #205 Step 1: Test-runner archetype includes tools: Bash, Read, Write, Glob, Grep
            "Bash", "Read", "Write", "Glob", "Grep",
            # Feature tracking tools for test result reporting
            "feature_get_by_id", "feature_mark_passing", "feature_mark_failing",
        ],
        default_skills=[
            # Feature #205 Step 2: Default skills: pytest, unittest, test discovery
            "pytest",
            "unittest",
            "test discovery",
            # Additional testing skills
            "test execution",
            "test analysis",
            "coverage reporting",
            "test framework usage",
            "CI/CD integration",
            "test-driven development",
        ],
        responsibilities=[
            # Feature #205 Step 3: Responsibilities: write tests, run tests, report results
            "Write test cases following project patterns and best practices",
            "Run tests and execute test suites",
            "Report test results and status",
            # Additional responsibilities
            "Analyze test failures and identify root causes",
            "Generate coverage reports",
            "Validate acceptance criteria",
            "Report test status to feature tracking system",
        ],
        # Feature #205 Step 4: Model: sonnet (balanced speed/capability)
        recommended_model="sonnet",
        task_type="testing",
        icon="🧪",
        capability_keywords=[
            "test", "testing", "test-runner", "test_runner", "qa", "quality",
            "validation", "verify", "check", "runner", "execute", "unit_test",
            "unit_testing", "integration_test", "integration_testing",
            "pytest", "unittest", "write_tests", "write_test", "tdd",
        ],
        # Note: Test-runner CAN write test files but not production code
        # Edit excluded to prevent modifying production code
        excluded_tools=["Edit"],
        max_turns=50,
        timeout_seconds=900,
    ),

    # ==========================================================================
    # AUDITOR Archetype
    # ==========================================================================
    "auditor": AgentArchetype(
        name="auditor",
        display_name="Auditor Agent",
        description=(
            "A security and code quality auditor that performs read-only analysis. "
            "Scans for vulnerabilities, code smells, and compliance issues. "
            "Uses opus model for thorough, complex analysis."
        ),
        default_tools=[
            "Read", "Glob", "Grep", "WebFetch", "WebSearch",
        ],
        default_skills=[
            "security analysis",
            "vulnerability scanning",
            "code quality assessment",
            "compliance checking",
            "static analysis",
            "dependency auditing",
        ],
        responsibilities=[
            "Scan code for security vulnerabilities",
            "Identify code quality issues and technical debt",
            "Check compliance with security standards",
            "Analyze dependencies for known vulnerabilities",
            "Generate detailed audit reports",
        ],
        recommended_model="opus",
        task_type="audit",
        icon="🔍",
        capability_keywords=[
            "audit", "auditor", "security", "vulnerability", "scan", "analyze",
            "compliance", "review", "inspect", "check", "assessment",
        ],
        excluded_tools=["Write", "Edit", "Bash"],  # Auditors are strictly read-only
        max_turns=75,
        timeout_seconds=1200,
    ),

    # ==========================================================================
    # REVIEWER Archetype
    # ==========================================================================
    "reviewer": AgentArchetype(
        name="reviewer",
        display_name="Code Reviewer Agent",
        description=(
            "A code review agent that analyzes code changes and provides feedback. "
            "Reviews pull requests, suggests improvements, and enforces standards. "
            "Uses opus model for thorough review and nuanced feedback."
        ),
        default_tools=[
            "Read", "Glob", "Grep", "Bash", "WebFetch",
        ],
        default_skills=[
            "code review",
            "pull request analysis",
            "best practices enforcement",
            "feedback generation",
            "git operations",
        ],
        responsibilities=[
            "Review code changes for quality and correctness",
            "Provide constructive feedback on pull requests",
            "Enforce coding standards and best practices",
            "Identify potential bugs and issues",
            "Suggest improvements and alternatives",
        ],
        recommended_model="opus",
        task_type="audit",
        icon="📝",
        capability_keywords=[
            "review", "reviewer", "code_review", "code-review", "pr", "pull_request",
            "feedback", "suggest", "improve", "critique", "evaluate",
        ],
        excluded_tools=["Write", "Edit"],  # Reviewers shouldn't modify code directly
        max_turns=60,
        timeout_seconds=1200,
    ),

    # ==========================================================================
    # E2E-TESTER Archetype
    # ==========================================================================
    "e2e-tester": AgentArchetype(
        name="e2e-tester",
        display_name="E2E Testing Agent",
        description=(
            "An end-to-end testing agent that uses browser automation to test UIs. "
            "Performs UI testing with Playwright, validates user workflows. "
            "Uses sonnet model for reliable test execution."
        ),
        default_tools=[
            "Read", "Glob", "Grep", "Bash",
            "browser_navigate", "browser_click", "browser_type", "browser_fill_form",
            "browser_snapshot", "browser_take_screenshot",
            "browser_console_messages", "browser_network_requests",
            "feature_get_by_id", "feature_mark_passing", "feature_mark_failing",
        ],
        default_skills=[
            "browser automation",
            "UI testing",
            "Playwright",
            "user flow validation",
            "visual regression testing",
        ],
        responsibilities=[
            "Execute end-to-end tests through the UI",
            "Validate user workflows and interactions",
            "Capture screenshots for visual verification",
            "Check browser console for errors",
            "Report test results to feature tracking",
        ],
        recommended_model="sonnet",
        task_type="testing",
        icon="🌐",
        capability_keywords=[
            "e2e", "e2e_testing", "e2e-testing", "end-to-end", "end_to_end",
            "ui_testing", "ui-testing", "browser", "playwright",
            "selenium", "ui_test", "frontend_testing", "visual", "workflow",
            "browser_testing", "web_testing",
        ],
        excluded_tools=["Write", "Edit", "browser_evaluate"],  # No code modification or JS execution
        max_turns=75,
        timeout_seconds=1800,
    ),

    # ==========================================================================
    # DOCUMENTER Archetype
    # ==========================================================================
    "documenter": AgentArchetype(
        name="documenter",
        display_name="Documentation Agent",
        description=(
            "A documentation agent that generates and maintains documentation. "
            "Creates README files, API docs, and technical guides. "
            "Uses haiku model for fast, straightforward documentation tasks."
        ),
        default_tools=[
            "Read", "Write", "Glob", "Grep", "WebFetch", "WebSearch",
        ],
        default_skills=[
            "technical writing",
            "API documentation",
            "README generation",
            "markdown formatting",
            "documentation organization",
        ],
        responsibilities=[
            "Generate and update documentation",
            "Create README files and user guides",
            "Document APIs and code interfaces",
            "Maintain documentation consistency",
            "Organize documentation structure",
        ],
        recommended_model="haiku",
        task_type="documentation",
        icon="📚",
        capability_keywords=[
            "doc", "docs", "documentation", "documenter", "readme", "wiki",
            "guide", "tutorial", "write", "technical_writing",
        ],
        excluded_tools=["Bash", "Edit"],  # Documentation shouldn't need code execution
        max_turns=30,
        timeout_seconds=600,
    ),
}


# =============================================================================
# Archetype Access Functions
# =============================================================================

def get_archetype(name: str) -> AgentArchetype | None:
    """
    Get an archetype by name.

    Args:
        name: The archetype name (e.g., "coder", "test-runner")

    Returns:
        AgentArchetype if found, None otherwise
    """
    # Normalize name (handle underscores vs hyphens)
    normalized = name.lower().replace("_", "-")
    return AGENT_ARCHETYPES.get(normalized)


def get_all_archetypes() -> list[AgentArchetype]:
    """Get all defined archetypes."""
    return list(AGENT_ARCHETYPES.values())


def get_archetype_names() -> list[str]:
    """Get names of all defined archetypes."""
    return list(AGENT_ARCHETYPES.keys())


def archetype_exists(name: str) -> bool:
    """Check if an archetype exists."""
    return get_archetype(name) is not None


# =============================================================================
# Capability-to-Archetype Mapping (Feature #191 Step 3)
# =============================================================================

# Confidence thresholds for archetype matching
HIGH_CONFIDENCE_THRESHOLD = 0.8
MEDIUM_CONFIDENCE_THRESHOLD = 0.5
LOW_CONFIDENCE_THRESHOLD = 0.3


def map_capability_to_archetype(
    capability: str,
    task_type: str | None = None,
) -> ArchetypeMatchResult:
    """
    Map a capability to the most appropriate archetype.

    Feature #191 Step 3: Octo recognizes when a capability maps to an archetype
    Feature #191 Step 5: Custom agents created when no archetype fits

    This function analyzes the capability string and matches it against known
    archetype keywords. It returns the best matching archetype along with
    confidence score and matched keywords.

    Args:
        capability: The capability to map (e.g., "e2e_testing", "security_audit")
        task_type: Optional task type hint to help with matching

    Returns:
        ArchetypeMatchResult with matched archetype or is_custom_needed=True

    Examples:
        >>> result = map_capability_to_archetype("e2e_testing")
        >>> result.archetype_name
        'e2e-tester'

        >>> result = map_capability_to_archetype("quantum_computing")
        >>> result.is_custom_needed
        True
    """
    # Handle empty or whitespace-only capability
    if not capability or not capability.strip():
        return ArchetypeMatchResult(
            archetype_name=None,
            archetype=None,
            confidence=0.0,
            matched_keywords=[],
            is_custom_needed=True,
            reason="Empty capability string requires custom agent",
        )

    capability_lower = capability.lower().replace("-", "_").replace(" ", "_")

    best_match: AgentArchetype | None = None
    best_score = 0.0
    best_keywords: list[str] = []

    # Score each archetype
    for archetype in AGENT_ARCHETYPES.values():
        score, matched_keywords = _score_archetype_match(
            capability_lower,
            archetype,
            task_type,
        )

        if score > best_score:
            best_score = score
            best_match = archetype
            best_keywords = matched_keywords

    # Determine if we have a good enough match
    if best_match and best_score >= LOW_CONFIDENCE_THRESHOLD:
        # Determine confidence level
        if best_score >= HIGH_CONFIDENCE_THRESHOLD:
            reason = f"High confidence match: '{capability}' strongly matches '{best_match.name}' archetype"
        elif best_score >= MEDIUM_CONFIDENCE_THRESHOLD:
            reason = f"Medium confidence match: '{capability}' matches '{best_match.name}' archetype"
        else:
            reason = f"Low confidence match: '{capability}' weakly matches '{best_match.name}' archetype"

        _logger.debug(
            "Capability '%s' matched archetype '%s' with confidence %.2f",
            capability, best_match.name, best_score
        )

        return ArchetypeMatchResult(
            archetype_name=best_match.name,
            archetype=best_match,
            confidence=best_score,
            matched_keywords=best_keywords,
            is_custom_needed=False,
            reason=reason,
        )

    # No archetype matched well enough - need custom agent
    # Feature #191 Step 5: Custom agents created when no archetype fits
    _logger.debug(
        "Capability '%s' did not match any archetype (best score: %.2f), custom agent needed",
        capability, best_score
    )

    return ArchetypeMatchResult(
        archetype_name=None,
        archetype=None,
        confidence=best_score,
        matched_keywords=best_keywords,
        is_custom_needed=True,
        reason=f"No archetype matched '{capability}' with sufficient confidence (best: {best_score:.2f})",
    )


def _score_archetype_match(
    capability_lower: str,
    archetype: AgentArchetype,
    task_type: str | None = None,
) -> tuple[float, list[str]]:
    """
    Calculate match score between capability and archetype.

    Scoring weights:
    - Exact capability == keyword match: 0.6 (strongest signal)
    - Archetype name in capability: 0.5
    - Capability in archetype name: 0.4
    - Keyword in capability: 0.25
    - Capability in keyword: 0.15
    - Task type match: 0.2

    Returns:
        Tuple of (score, matched_keywords)
    """
    matched_keywords: list[str] = []
    score = 0.0

    # Check for exact archetype name match (highest weight)
    archetype_name_normalized = archetype.name.lower().replace("-", "_")
    if archetype_name_normalized == capability_lower:
        # Exact match with archetype name
        score += 0.7
        matched_keywords.append(archetype.name)
    elif archetype_name_normalized in capability_lower:
        score += 0.5
        matched_keywords.append(archetype.name)
    elif capability_lower in archetype_name_normalized:
        score += 0.4
        matched_keywords.append(archetype.name)

    # Check keyword matches
    for keyword in archetype.capability_keywords:
        keyword_normalized = keyword.lower().replace("-", "_")

        # Exact match with keyword (strong signal)
        if keyword_normalized == capability_lower:
            score += 0.6
            matched_keywords.append(keyword)
        # Keyword contained in capability
        elif keyword_normalized in capability_lower:
            score += 0.25
            matched_keywords.append(keyword)
        # Capability contained in keyword
        elif capability_lower in keyword_normalized:
            score += 0.15
            matched_keywords.append(keyword)

    # Bonus for task_type match
    if task_type:
        task_type_lower = task_type.lower()
        if task_type_lower == archetype.task_type:
            score += 0.2
            matched_keywords.append(f"task_type:{task_type_lower}")

    # Cap score at 1.0
    score = min(score, 1.0)

    return score, matched_keywords


def is_custom_agent_needed(
    capability: str,
    task_type: str | None = None,
) -> bool:
    """
    Determine if a custom agent is needed for a capability.

    Feature #191 Step 5: Custom agents created when no archetype fits

    Args:
        capability: The capability to check
        task_type: Optional task type hint

    Returns:
        True if no archetype fits and custom agent is needed
    """
    result = map_capability_to_archetype(capability, task_type)
    return result.is_custom_needed


# =============================================================================
# Archetype Customization (Feature #191 Step 4)
# =============================================================================

def customize_archetype(
    archetype_name: str,
    project_context: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> CustomizedArchetype | None:
    """
    Customize an archetype based on project-specific needs.

    Feature #191 Step 4: Archetypes customized based on project-specific needs

    This function takes a base archetype and customizes it based on:
    - Project tech stack (adds relevant skills)
    - Project tools availability (enables/disables tools)
    - Project constraints (adjusts budgets, model)

    Args:
        archetype_name: Name of the base archetype
        project_context: Project context containing tech_stack, tools, etc.
        constraints: Constraints dict containing budgets, model preferences, etc.

    Returns:
        CustomizedArchetype with project-specific modifications, or None if archetype not found

    Examples:
        >>> customized = customize_archetype(
        ...     "coder",
        ...     project_context={"tech_stack": ["React", "TypeScript", "PostgreSQL"]},
        ... )
        >>> "react" in customized.skills
        True
    """
    archetype = get_archetype(archetype_name)
    if not archetype:
        _logger.warning("Archetype '%s' not found", archetype_name)
        return None

    project_context = project_context or {}
    constraints = constraints or {}

    # Start with archetype defaults
    tools = list(archetype.default_tools)
    skills = list(archetype.default_skills)
    responsibilities = list(archetype.responsibilities)
    model = archetype.recommended_model
    max_turns = archetype.max_turns
    timeout_seconds = archetype.timeout_seconds
    customizations: list[str] = []

    # ==========================================================================
    # Tech Stack Customization
    # ==========================================================================
    tech_stack = project_context.get("tech_stack", [])
    if tech_stack:
        tech_skills = _derive_skills_from_tech_stack(tech_stack)
        if tech_skills:
            skills.extend(tech_skills)
            customizations.append(f"Added skills from tech stack: {tech_skills}")

    # ==========================================================================
    # Browser Tools Customization
    # ==========================================================================
    # If Playwright is in tech stack and archetype supports it, ensure browser tools
    if any("playwright" in str(t).lower() for t in tech_stack):
        browser_tools = [
            "browser_navigate", "browser_click", "browser_type", "browser_fill_form",
            "browser_snapshot", "browser_take_screenshot",
            "browser_console_messages", "browser_network_requests",
        ]
        for tool in browser_tools:
            if tool not in tools and tool not in archetype.excluded_tools:
                tools.append(tool)
        customizations.append("Added Playwright browser tools from tech stack")

    # ==========================================================================
    # Feature Management Tools
    # ==========================================================================
    # Add feature management tools if testing-related archetype
    if archetype.task_type == "testing":
        feature_tools = [
            "feature_get_by_id", "feature_mark_passing", "feature_mark_failing",
        ]
        for tool in feature_tools:
            if tool not in tools:
                tools.append(tool)
        if feature_tools:
            customizations.append("Added feature management tools for testing")

    # ==========================================================================
    # Constraints Customization
    # ==========================================================================
    # Model override from constraints
    if "model" in constraints:
        new_model = constraints["model"].lower()
        if new_model in ("sonnet", "opus", "haiku"):
            model = new_model
            customizations.append(f"Model overridden to '{model}' from constraints")

    # Budget overrides from constraints
    if "max_turns_limit" in constraints:
        max_turns = min(max_turns, constraints["max_turns_limit"])
        customizations.append(f"max_turns capped to {max_turns} from constraints")

    if "timeout_limit" in constraints:
        timeout_seconds = min(timeout_seconds, constraints["timeout_limit"])
        customizations.append(f"timeout capped to {timeout_seconds}s from constraints")

    # ==========================================================================
    # Project Settings Customization
    # ==========================================================================
    project_settings = project_context.get("settings", {})

    # Model from project settings
    if "model" in project_settings:
        new_model = project_settings["model"].lower()
        if new_model in ("sonnet", "opus", "haiku"):
            model = new_model
            customizations.append(f"Model set to '{model}' from project settings")

    # Additional tools from project settings
    if "additional_tools" in project_settings:
        additional = project_settings["additional_tools"]
        for tool in additional:
            if tool not in tools and tool not in archetype.excluded_tools:
                tools.append(tool)
        if additional:
            customizations.append(f"Added tools from project settings: {additional}")

    # ==========================================================================
    # Apply Exclusions
    # ==========================================================================
    # Remove any excluded tools that might have been added
    tools = [t for t in tools if t not in archetype.excluded_tools]

    _logger.debug(
        "Customized archetype '%s' with %d modifications: %s",
        archetype_name, len(customizations), customizations
    )

    return CustomizedArchetype(
        base_archetype=archetype,
        tools=tools,
        skills=list(set(skills)),  # Deduplicate
        responsibilities=responsibilities,
        model=model,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
        customizations_applied=customizations,
    )


def _derive_skills_from_tech_stack(tech_stack: list[str]) -> list[str]:
    """
    Derive additional skills from the project's tech stack.

    Args:
        tech_stack: List of technologies (e.g., ["React", "TypeScript", "PostgreSQL"])

    Returns:
        List of additional skills to add
    """
    skills: list[str] = []

    tech_to_skills: dict[str, list[str]] = {
        # Frontend
        "react": ["react", "jsx", "react hooks"],
        "vue": ["vue", "vue composition api"],
        "angular": ["angular", "typescript"],
        "typescript": ["typescript", "type safety"],
        "javascript": ["javascript", "es6+"],
        "css": ["css", "styling"],
        "tailwind": ["tailwind css", "utility-first css"],
        "sass": ["sass", "scss"],

        # Backend
        "python": ["python", "pip"],
        "fastapi": ["fastapi", "async python", "pydantic"],
        "django": ["django", "django orm"],
        "flask": ["flask", "python web"],
        "node": ["node.js", "npm"],
        "express": ["express.js", "node middleware"],
        "rust": ["rust", "cargo"],
        "go": ["go", "golang"],

        # Database
        "postgresql": ["postgresql", "sql"],
        "postgres": ["postgresql", "sql"],
        "mysql": ["mysql", "sql"],
        "mongodb": ["mongodb", "nosql"],
        "redis": ["redis", "caching"],
        "sqlite": ["sqlite", "sql"],
        "sqlalchemy": ["sqlalchemy", "orm"],

        # Testing
        "pytest": ["pytest", "python testing"],
        "jest": ["jest", "javascript testing"],
        "playwright": ["playwright", "browser automation", "e2e testing"],
        "cypress": ["cypress", "e2e testing"],
        "vitest": ["vitest", "vite testing"],

        # DevOps
        "docker": ["docker", "containerization"],
        "kubernetes": ["kubernetes", "k8s", "container orchestration"],
        "aws": ["aws", "cloud"],
        "gcp": ["gcp", "google cloud"],
        "azure": ["azure", "microsoft cloud"],
    }

    for tech in tech_stack:
        tech_lower = tech.lower()
        for key, tech_skills in tech_to_skills.items():
            if key in tech_lower:
                skills.extend(tech_skills)

    return skills


# =============================================================================
# Agent Creation from Archetype
# =============================================================================

def create_agent_from_archetype(
    archetype_name: str,
    agent_name: str,
    objective: str,
    project_context: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Create an agent spec dictionary from an archetype.

    This is a helper function that creates a spec-like dictionary from an archetype.
    The actual AgentSpec creation should be done by SpecBuilder.

    Args:
        archetype_name: Name of the archetype to use
        agent_name: Unique name for the agent
        objective: The agent's objective
        project_context: Project context for customization
        constraints: Constraints for customization

    Returns:
        Dictionary with agent spec fields, or None if archetype not found
    """
    customized = customize_archetype(
        archetype_name=archetype_name,
        project_context=project_context,
        constraints=constraints,
    )

    if not customized:
        return None

    archetype = customized.base_archetype

    return {
        "name": agent_name,
        "display_name": f"{archetype.display_name} - {agent_name}",
        "objective": objective,
        "task_type": archetype.task_type,
        "model": customized.model,
        "tools": customized.tools,
        "skills": customized.skills,
        "responsibilities": customized.responsibilities,
        "max_turns": customized.max_turns,
        "timeout_seconds": customized.timeout_seconds,
        "icon": archetype.icon,
        "context": {
            "archetype": archetype.name,
            "customizations_applied": customized.customizations_applied,
        },
    }


# =============================================================================
# Utility Functions
# =============================================================================

def get_archetype_for_task_type(task_type: str) -> AgentArchetype | None:
    """
    Get the default archetype for a task type.

    Args:
        task_type: The task type (coding, testing, audit, documentation)

    Returns:
        Default archetype for the task type, or None
    """
    task_type_to_archetype: dict[str, str] = {
        "coding": "coder",
        "testing": "test-runner",
        "audit": "auditor",
        "documentation": "documenter",
        "refactoring": "coder",
    }

    archetype_name = task_type_to_archetype.get(task_type.lower())
    if archetype_name:
        return get_archetype(archetype_name)
    return None


def get_archetype_summary() -> dict[str, dict[str, Any]]:
    """
    Get a summary of all archetypes.

    Returns:
        Dictionary mapping archetype names to their summaries
    """
    return {
        name: {
            "display_name": archetype.display_name,
            "description": archetype.description[:100] + "..." if len(archetype.description) > 100 else archetype.description,
            "task_type": archetype.task_type,
            "model": archetype.recommended_model,
            "tool_count": len(archetype.default_tools),
            "icon": archetype.icon,
        }
        for name, archetype in AGENT_ARCHETYPES.items()
    }
