"""
Maestro: Agent Planning Decision Engine
========================================

Feature #174: Maestro detects when new agents are needed
Feature #175: Maestro produces structured Octo request payload
Feature #176: Maestro delegates to Octo for agent generation
Feature #177: Maestro orchestrates agent materialization after Octo completes

Maestro analyzes project context and feature backlog to identify when additional
agents beyond the defaults are required. This triggers the agent-planning workflow.

Maestro's responsibilities:
1. Receive project context including tech stack, features, and execution environment
2. Evaluate whether existing agents can handle all features
3. Flag agent-planning required when specialized capabilities are needed
4. Output structured agent-planning decisions with justification
5. Produce structured OctoRequestPayload with all context for agent-spec generation
6. Orchestrate agent materialization after receiving specs from Octo

Feature #175 - OctoRequestPayload:
When agent-planning is required, Maestro produces a structured JSON payload
containing all context Octo needs to generate AgentSpecs:
- project_context: Discovery artifacts, app spec, tech stack, feature backlog
- required_capabilities: What the agent needs to be able to do
- existing_agents: Already-defined agent specs that might be reused
- constraints: Resource limits, policy restrictions, environment requirements

The payload is validated against OctoRequestPayload schema before dispatch.

Feature #177 Workflow:
1. Maestro receives validated AgentSpecs from Octo
2. Maestro invokes Agent Materializer with AgentSpecs and project path
3. Maestro awaits materialization completion
4. Maestro verifies agent files exist in .claude/agents/generated/

Default agents (always available):
- coding: General-purpose coding agent for implementation tasks
- testing: Test creation and verification agent

Specialized capabilities that require new agents:
- playwright: E2E browser automation testing
- specific framework expertise (React, Vue, FastAPI, etc.)
- database migrations (specific ORMs)
- infrastructure/DevOps tasks
- security auditing
- performance testing
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from api.agentspec_models import AgentSpec, generate_uuid
from api.event_recorder import EventRecorder, get_event_recorder
from api.spec_validator import validate_spec, SpecValidationResult

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants: Capability Detection Keywords
# =============================================================================

# Keywords that indicate specialized framework/tool requirements
SPECIALIZED_CAPABILITY_KEYWORDS: dict[str, frozenset[str]] = {
    # E2E testing capabilities
    "playwright": frozenset([
        "playwright",
        "e2e test",
        "e2e testing",
        "end-to-end test",
        "end-to-end testing",
        "browser automation",
        "browser test",
        "ui automation",
        "headless browser",
    ]),
    "cypress": frozenset([
        "cypress",
        "cypress test",
        "cypress testing",
    ]),
    "selenium": frozenset([
        "selenium",
        "webdriver",
        "selenium test",
    ]),

    # Frontend frameworks
    "react": frozenset([
        "react",
        "react component",
        "react hook",
        "redux",
        "next.js",
        "nextjs",
        "jsx",
        "tsx",
        "react native",
    ]),
    "vue": frozenset([
        "vue",
        "vuejs",
        "vue.js",
        "vue component",
        "vuex",
        "pinia",
        "nuxt",
    ]),
    "angular": frozenset([
        "angular",
        "angularjs",
        "angular component",
        "rxjs",
        "ngrx",
    ]),
    "svelte": frozenset([
        "svelte",
        "sveltekit",
        "svelte component",
    ]),

    # Backend frameworks
    "fastapi": frozenset([
        "fastapi",
        "fast api",
        "pydantic",
        "uvicorn",
    ]),
    "django": frozenset([
        "django",
        "django rest",
        "drf",
        "django model",
        "django view",
    ]),
    "flask": frozenset([
        "flask",
        "flask blueprint",
        "flask route",
    ]),
    "express": frozenset([
        "express",
        "expressjs",
        "express.js",
        "express middleware",
    ]),

    # Database/ORM
    "sqlalchemy": frozenset([
        "sqlalchemy",
        "alembic",
        "orm model",
        "database migration",
    ]),
    "prisma": frozenset([
        "prisma",
        "prisma schema",
        "prisma migrate",
    ]),
    "mongoose": frozenset([
        "mongoose",
        "mongodb",
        "mongo schema",
    ]),

    # Infrastructure/DevOps
    "docker": frozenset([
        "docker",
        "dockerfile",
        "docker compose",
        "container",
        "containerize",
    ]),
    "kubernetes": frozenset([
        "kubernetes",
        "k8s",
        "helm",
        "kubectl",
        "pod",
        "deployment yaml",
    ]),
    "terraform": frozenset([
        "terraform",
        "infrastructure as code",
        "iac",
        "tf module",
    ]),
    "aws": frozenset([
        "aws",
        "amazon web services",
        "s3",
        "ec2",
        "lambda",
        "cloudformation",
        "cdk",
    ]),

    # Security
    "security_audit": frozenset([
        "security audit",
        "penetration test",
        "pen test",
        "vulnerability scan",
        "security review",
        "owasp",
        "cve",
    ]),

    # Performance
    "performance_testing": frozenset([
        "load test",
        "stress test",
        "performance test",
        "benchmark",
        "profiling",
        "k6",
        "locust",
        "jmeter",
    ]),

    # Mobile
    "mobile": frozenset([
        "ios",
        "android",
        "react native",
        "flutter",
        "mobile app",
        "native app",
    ]),
}

# Default agents that are always available
DEFAULT_AGENTS: frozenset[str] = frozenset(["coding", "testing"])


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ProjectContext:
    """
    Project context containing tech stack, features, and execution environment.

    Attributes:
        project_name: Name of the project
        project_dir: Path to the project directory
        tech_stack: List of detected technologies (e.g., ["python", "react", "fastapi"])
        features: List of feature descriptions/names to analyze
        execution_environment: Runtime environment (e.g., "local", "docker", "ci")
        existing_agents: List of agent types already available
        config_files: List of config files found (package.json, requirements.txt, etc.)
    """
    project_name: str
    project_dir: Optional[Path] = None
    tech_stack: list[str] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)
    execution_environment: str = "local"
    existing_agents: list[str] = field(default_factory=lambda: list(DEFAULT_AGENTS))
    config_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_name": self.project_name,
            "project_dir": str(self.project_dir) if self.project_dir else None,
            "tech_stack": self.tech_stack,
            "features": self.features,
            "execution_environment": self.execution_environment,
            "existing_agents": self.existing_agents,
            "config_files": self.config_files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectContext":
        """Create from dictionary."""
        return cls(
            project_name=data.get("project_name", "unknown"),
            project_dir=Path(data["project_dir"]) if data.get("project_dir") else None,
            tech_stack=data.get("tech_stack", []),
            features=data.get("features", []),
            execution_environment=data.get("execution_environment", "local"),
            existing_agents=data.get("existing_agents", list(DEFAULT_AGENTS)),
            config_files=data.get("config_files", []),
        )


@dataclass
class CapabilityRequirement:
    """
    A detected capability requirement.

    Attributes:
        capability: The capability name (e.g., "playwright", "react")
        source: Where this requirement was detected (e.g., "feature_123", "tech_stack")
        keywords_matched: List of keywords that triggered this detection
        confidence: Detection confidence ("high", "medium", "low")
    """
    capability: str
    source: str
    keywords_matched: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "capability": self.capability,
            "source": self.source,
            "keywords_matched": self.keywords_matched,
            "confidence": self.confidence,
        }


@dataclass
class AgentPlanningDecision:
    """
    Maestro's decision about whether agent-planning is required.

    Attributes:
        requires_agent_planning: True if new agents are needed
        required_capabilities: List of capabilities that need new agents
        existing_capabilities: Capabilities covered by existing agents
        justification: Human-readable explanation of the decision
        recommended_agent_types: Suggested agent types to create
    """
    requires_agent_planning: bool
    required_capabilities: list[CapabilityRequirement] = field(default_factory=list)
    existing_capabilities: list[str] = field(default_factory=list)
    justification: str = ""
    recommended_agent_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "requires_agent_planning": self.requires_agent_planning,
            "required_capabilities": [r.to_dict() for r in self.required_capabilities],
            "existing_capabilities": self.existing_capabilities,
            "justification": self.justification,
            "recommended_agent_types": self.recommended_agent_types,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# Feature #177: Materialization Data Classes
# =============================================================================

@dataclass
class MaterializationResult:
    """
    Result of materializing a single AgentSpec.

    Attributes:
        spec_id: ID of the AgentSpec that was materialized
        spec_name: Name of the AgentSpec
        success: Whether materialization succeeded
        file_path: Path to the created agent file (if successful)
        error: Error message (if failed)
    """
    spec_id: str
    spec_name: str
    success: bool
    file_path: Path | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "success": self.success,
            "file_path": str(self.file_path) if self.file_path else None,
            "error": self.error,
        }


@dataclass
class OrchestrationResult:
    """
    Result of orchestrating materialization for multiple AgentSpecs.

    Attributes:
        total: Total number of specs processed
        succeeded: Number of successful materializations
        failed: Number of failed materializations
        results: Individual results for each spec
        verified: Whether all files were verified to exist
        audit_events: List of audit event IDs recorded
    """
    total: int
    succeeded: int
    failed: int
    results: list[MaterializationResult] = field(default_factory=list)
    verified: bool = False
    audit_events: list[str] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        """Check if all materializations succeeded."""
        return self.failed == 0 and self.total > 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "all_succeeded": self.all_succeeded,
            "verified": self.verified,
            "results": [r.to_dict() for r in self.results],
            "audit_events": self.audit_events,
        }


# =============================================================================
# Feature #177: AgentMaterializer
# =============================================================================

class AgentMaterializer:
    """
    Materializes AgentSpecs into agent files on disk.

    The materializer creates markdown files in .claude/agents/generated/
    with YAML frontmatter and structured content that describes the agent.

    These files serve as:
    - Human-readable documentation of generated agents
    - Configuration for future agent execution
    - Audit trail of agent planning decisions
    """

    # Default output directory relative to project root
    DEFAULT_OUTPUT_DIR = ".claude/agents/generated"

    def __init__(
        self,
        project_dir: Path,
        *,
        output_dir: str | None = None,
    ):
        """
        Initialize the AgentMaterializer.

        Args:
            project_dir: Root project directory
            output_dir: Custom output directory (relative to project_dir),
                       defaults to .claude/agents/generated/
        """
        self.project_dir = Path(project_dir).resolve()
        self._output_dir = output_dir or self.DEFAULT_OUTPUT_DIR

    @property
    def output_path(self) -> Path:
        """Get the absolute path to the output directory."""
        return self.project_dir / self._output_dir

    def ensure_output_dir(self) -> Path:
        """
        Ensure the output directory exists.

        Returns:
            Path to the output directory
        """
        self.output_path.mkdir(parents=True, exist_ok=True)
        return self.output_path

    def materialize(self, spec: AgentSpec) -> MaterializationResult:
        """
        Materialize a single AgentSpec to an agent file.

        Creates a markdown file with:
        - YAML frontmatter with spec metadata
        - Objective section
        - Tool policy section
        - Acceptance criteria section

        Args:
            spec: The AgentSpec to materialize

        Returns:
            MaterializationResult indicating success or failure
        """
        try:
            # Ensure output directory exists
            output_dir = self.ensure_output_dir()

            # Generate filename from spec name
            filename = f"{spec.name}.md"
            filepath = output_dir / filename

            # Build file content
            content = self._build_file_content(spec)

            # Write the file
            filepath.write_text(content, encoding="utf-8")

            _logger.info(
                "Materialized AgentSpec '%s' to %s",
                spec.name, filepath,
            )

            return MaterializationResult(
                spec_id=spec.id,
                spec_name=spec.name,
                success=True,
                file_path=filepath,
            )

        except Exception as e:
            _logger.error(
                "Failed to materialize AgentSpec '%s': %s",
                spec.name, e,
            )
            return MaterializationResult(
                spec_id=spec.id,
                spec_name=spec.name,
                success=False,
                error=str(e),
            )

    def _build_file_content(self, spec: AgentSpec) -> str:
        """
        Build the markdown content for an agent file.

        Args:
            spec: The AgentSpec to render

        Returns:
            Markdown content string
        """
        lines = []

        # YAML frontmatter
        lines.append("---")
        lines.append(f"name: {spec.display_name}")
        lines.append(f"spec_id: {spec.id}")
        lines.append(f"spec_name: {spec.name}")
        lines.append(f"task_type: {spec.task_type}")
        lines.append(f"icon: {spec.icon}")
        lines.append(f"spec_version: {spec.spec_version}")

        if spec.source_feature_id:
            lines.append(f"source_feature_id: {spec.source_feature_id}")

        lines.append(f"max_turns: {spec.max_turns}")
        lines.append(f"timeout_seconds: {spec.timeout_seconds}")
        lines.append(f"priority: {spec.priority}")

        if spec.tags:
            lines.append(f"tags: {json.dumps(spec.tags)}")

        lines.append(f"created_at: {datetime.now(timezone.utc).isoformat()}")
        lines.append("---")
        lines.append("")

        # Title
        lines.append(f"# {spec.display_name}")
        lines.append("")

        # Objective section
        lines.append("## Objective")
        lines.append("")
        lines.append(spec.objective or "(No objective specified)")
        lines.append("")

        # Tool Policy section
        lines.append("## Tool Policy")
        lines.append("")
        if spec.tool_policy and isinstance(spec.tool_policy, dict):
            allowed_tools = spec.tool_policy.get("allowed_tools", [])
            lines.append(f"**Allowed Tools ({len(allowed_tools)}):**")
            lines.append("")
            for tool in allowed_tools[:20]:  # Cap at 20 for readability
                lines.append(f"- {tool}")
            if len(allowed_tools) > 20:
                lines.append(f"- ... and {len(allowed_tools) - 20} more")
            lines.append("")

            forbidden = spec.tool_policy.get("forbidden_patterns", [])
            if forbidden:
                lines.append(f"**Forbidden Patterns ({len(forbidden)}):**")
                lines.append("")
                for pattern in forbidden[:10]:
                    lines.append(f"- `{pattern}`")
                if len(forbidden) > 10:
                    lines.append(f"- ... and {len(forbidden) - 10} more")
                lines.append("")

            hints = spec.tool_policy.get("tool_hints", {})
            if hints:
                lines.append("**Tool Hints:**")
                lines.append("")
                for tool_name, hint in list(hints.items())[:5]:
                    hint_truncated = hint[:100] + "..." if len(hint) > 100 else hint
                    lines.append(f"- **{tool_name}**: {hint_truncated}")
                lines.append("")
        else:
            lines.append("(No tool policy defined)")
            lines.append("")

        # Acceptance Criteria section
        lines.append("## Acceptance Criteria")
        lines.append("")
        if spec.acceptance_spec:
            lines.append(f"**Gate Mode:** {spec.acceptance_spec.gate_mode}")
            lines.append(f"**Retry Policy:** {spec.acceptance_spec.retry_policy}")
            lines.append(f"**Max Retries:** {spec.acceptance_spec.max_retries}")
            lines.append("")

            validators = spec.acceptance_spec.validators or []
            if validators:
                lines.append(f"**Validators ({len(validators)}):**")
                lines.append("")
                for i, v in enumerate(validators, start=1):
                    v_type = v.get("type", "unknown")
                    v_config = v.get("config", {})
                    v_name = v_config.get("name", f"validator_{i}")
                    v_desc = v_config.get("description", "")
                    lines.append(f"{i}. **{v_name}** ({v_type})")
                    if v_desc:
                        desc_truncated = v_desc[:100] if len(v_desc) > 100 else v_desc
                        lines.append(f"   - {desc_truncated}")
                lines.append("")
        else:
            lines.append("(No acceptance criteria defined)")
            lines.append("")

        # Context section (if available)
        if spec.context:
            lines.append("## Context")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(spec.context, indent=2))
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def verify_exists(self, spec: AgentSpec) -> bool:
        """
        Verify that an agent file exists for the given spec.

        Args:
            spec: The AgentSpec to check

        Returns:
            True if the agent file exists, False otherwise
        """
        filepath = self.output_path / f"{spec.name}.md"
        return filepath.exists()

    def verify_all(self, specs: list[AgentSpec]) -> dict[str, bool]:
        """
        Verify that agent files exist for all given specs.

        Args:
            specs: List of AgentSpecs to verify

        Returns:
            Dictionary mapping spec_id to existence status
        """
        return {spec.id: self.verify_exists(spec) for spec in specs}


# =============================================================================
# Maestro Class
# =============================================================================

class Maestro:
    """
    Agent Planning Decision Engine.

    Analyzes project context and feature backlog to identify when additional
    agents beyond the defaults are required. This triggers the agent-planning workflow.

    Feature #177: Also orchestrates agent materialization after Octo completes,
    delegating to AgentMaterializer and verifying results.
    """

    def __init__(
        self,
        capability_keywords: dict[str, frozenset[str]] | None = None,
        default_agents: frozenset[str] | None = None,
        *,
        # Feature #177: Materialization support
        project_dir: Path | None = None,
        materializer: AgentMaterializer | None = None,
        session: Any | None = None,
        event_callback: Callable[[dict], None] | None = None,
    ):
        """
        Initialize Maestro.

        Args:
            capability_keywords: Custom capability keywords (uses defaults if None)
            default_agents: Default agent types (uses DEFAULT_AGENTS if None)

        Keyword Args (Feature #177 - materialization support):
            project_dir: Root project directory (required for materialization)
            materializer: AgentMaterializer instance (auto-created if project_dir provided)
            session: Optional SQLAlchemy session for audit events
            event_callback: Optional callback for audit events (e.g., WebSocket broadcast)
        """
        self.capability_keywords = capability_keywords or SPECIALIZED_CAPABILITY_KEYWORDS
        self.default_agents = default_agents or DEFAULT_AGENTS

        # Feature #177: Materialization support
        self.project_dir = Path(project_dir).resolve() if project_dir else None
        self.materializer = materializer
        self.session = session
        self.event_callback = event_callback

        # Auto-create materializer if project_dir provided but no materializer
        if self.project_dir and not self.materializer:
            self.materializer = AgentMaterializer(self.project_dir)

        _logger.info(
            "Maestro initialized with %d capability types and %d default agents",
            len(self.capability_keywords),
            len(self.default_agents),
        )
        if self.materializer:
            _logger.info(
                "Maestro materialization enabled: output_path=%s",
                self.materializer.output_path,
            )

    # -------------------------------------------------------------------------
    # Text Analysis Helpers
    # -------------------------------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        """Normalize text for keyword matching."""
        if not text:
            return ""
        # Convert to lowercase and normalize whitespace
        return re.sub(r'\s+', ' ', text.lower()).strip()

    def _extract_text_from_features(self, features: list[dict[str, Any]]) -> list[tuple[str, str]]:
        """
        Extract searchable text from feature list.

        Returns list of (source_id, text) tuples.
        """
        results = []
        for feature in features:
            feature_id = feature.get("id", feature.get("name", "unknown"))
            source = f"feature_{feature_id}"

            # Collect all text fields
            texts = []
            if feature.get("name"):
                texts.append(feature["name"])
            if feature.get("description"):
                texts.append(feature["description"])
            if feature.get("steps"):
                steps = feature["steps"]
                if isinstance(steps, list):
                    texts.extend(str(s) for s in steps)
                elif isinstance(steps, str):
                    texts.append(steps)
            if feature.get("category"):
                texts.append(feature["category"])

            combined_text = " ".join(texts)
            if combined_text.strip():
                results.append((source, combined_text))

        return results

    def _match_keywords(
        self,
        text: str,
        keywords: frozenset[str],
    ) -> list[str]:
        """
        Find which keywords match in the given text.

        Returns list of matched keywords.
        """
        normalized = self._normalize_text(text)
        matched = []

        for keyword in keywords:
            # For phrases (containing spaces), use substring matching
            if ' ' in keyword:
                if keyword in normalized:
                    matched.append(keyword)
            else:
                # For single words, use word boundary matching
                pattern = r'\b' + re.escape(keyword) + r'\b'
                if re.search(pattern, normalized):
                    matched.append(keyword)

        return matched

    # -------------------------------------------------------------------------
    # Capability Detection
    # -------------------------------------------------------------------------

    def detect_capabilities_in_text(
        self,
        text: str,
        source: str = "unknown",
    ) -> list[CapabilityRequirement]:
        """
        Detect capability requirements in a piece of text.

        Args:
            text: Text to analyze
            source: Source identifier for tracking

        Returns:
            List of detected capability requirements
        """
        requirements = []

        for capability, keywords in self.capability_keywords.items():
            matched = self._match_keywords(text, keywords)
            if matched:
                # Determine confidence based on number of matches
                confidence = "high" if len(matched) >= 3 else "medium" if len(matched) >= 2 else "low"

                requirements.append(CapabilityRequirement(
                    capability=capability,
                    source=source,
                    keywords_matched=matched,
                    confidence=confidence,
                ))

                _logger.debug(
                    "Detected %s capability in %s (confidence=%s, keywords=%s)",
                    capability, source, confidence, matched,
                )

        return requirements

    def detect_capabilities_in_tech_stack(
        self,
        tech_stack: list[str],
    ) -> list[CapabilityRequirement]:
        """
        Detect capability requirements from tech stack.

        Args:
            tech_stack: List of technologies

        Returns:
            List of detected capability requirements
        """
        # Convert tech stack to searchable text
        text = " ".join(tech_stack)
        return self.detect_capabilities_in_text(text, source="tech_stack")

    def detect_capabilities_in_features(
        self,
        features: list[dict[str, Any]],
    ) -> list[CapabilityRequirement]:
        """
        Detect capability requirements from feature backlog.

        Args:
            features: List of feature dictionaries

        Returns:
            List of detected capability requirements
        """
        all_requirements = []

        for source, text in self._extract_text_from_features(features):
            requirements = self.detect_capabilities_in_text(text, source=source)
            all_requirements.extend(requirements)

        return all_requirements

    # -------------------------------------------------------------------------
    # Main Decision Logic
    # -------------------------------------------------------------------------

    def can_existing_agents_handle(
        self,
        capability: str,
        existing_agents: list[str],
    ) -> bool:
        """
        Check if existing agents can handle a capability.

        Args:
            capability: The capability to check
            existing_agents: List of available agent types

        Returns:
            True if existing agents can handle this capability
        """
        # Default agents can handle general coding and testing
        general_capabilities = {"coding", "testing", "refactoring", "documentation"}
        if capability in general_capabilities:
            return True

        # Check if we have a specialized agent for this capability
        if capability in existing_agents:
            return True

        # Map capabilities to agent types that can handle them
        capability_agent_map = {
            "playwright": ["playwright", "e2e", "browser_automation"],
            "cypress": ["cypress", "e2e", "browser_automation"],
            "selenium": ["selenium", "e2e", "browser_automation"],
            "react": ["react", "frontend", "javascript"],
            "vue": ["vue", "frontend", "javascript"],
            "angular": ["angular", "frontend", "javascript"],
            "svelte": ["svelte", "frontend", "javascript"],
            "fastapi": ["fastapi", "backend", "python"],
            "django": ["django", "backend", "python"],
            "flask": ["flask", "backend", "python"],
            "express": ["express", "backend", "javascript"],
            "sqlalchemy": ["sqlalchemy", "database", "python"],
            "prisma": ["prisma", "database", "javascript"],
            "mongoose": ["mongoose", "database", "javascript"],
            "docker": ["docker", "devops", "infrastructure"],
            "kubernetes": ["kubernetes", "devops", "infrastructure"],
            "terraform": ["terraform", "devops", "infrastructure"],
            "aws": ["aws", "cloud", "infrastructure"],
            "security_audit": ["security", "audit"],
            "performance_testing": ["performance", "load_testing"],
            "mobile": ["mobile", "react_native", "flutter"],
        }

        possible_agents = capability_agent_map.get(capability, [])
        for agent in possible_agents:
            if agent in existing_agents:
                return True

        return False

    def evaluate(self, context: ProjectContext) -> AgentPlanningDecision:
        """
        Evaluate whether agent-planning is required for the given project context.

        This is the main entry point for Maestro's decision-making.

        Args:
            context: Project context with tech stack, features, etc.

        Returns:
            AgentPlanningDecision with the evaluation result
        """
        _logger.info(
            "Maestro evaluating project: %s (features=%d, tech_stack=%d, existing_agents=%d)",
            context.project_name,
            len(context.features),
            len(context.tech_stack),
            len(context.existing_agents),
        )

        # Step 1: Detect all capability requirements
        all_requirements: list[CapabilityRequirement] = []

        # From tech stack
        tech_requirements = self.detect_capabilities_in_tech_stack(context.tech_stack)
        all_requirements.extend(tech_requirements)

        # From features
        feature_requirements = self.detect_capabilities_in_features(context.features)
        all_requirements.extend(feature_requirements)

        _logger.info("Detected %d total capability requirements", len(all_requirements))

        # Step 2: Deduplicate by capability name (keep highest confidence)
        capability_map: dict[str, CapabilityRequirement] = {}
        for req in all_requirements:
            existing = capability_map.get(req.capability)
            if existing is None:
                capability_map[req.capability] = req
            else:
                # Keep the one with more keywords matched (higher confidence)
                if len(req.keywords_matched) > len(existing.keywords_matched):
                    capability_map[req.capability] = req

        unique_requirements = list(capability_map.values())

        # Step 3: Determine which capabilities existing agents can handle
        existing_capabilities = []
        new_requirements = []

        for req in unique_requirements:
            if self.can_existing_agents_handle(req.capability, context.existing_agents):
                existing_capabilities.append(req.capability)
            else:
                new_requirements.append(req)

        _logger.info(
            "Capabilities covered by existing agents: %s",
            existing_capabilities,
        )
        _logger.info(
            "Capabilities requiring new agents: %s",
            [r.capability for r in new_requirements],
        )

        # Step 4: Build the decision
        requires_planning = len(new_requirements) > 0

        # Recommend agent types based on required capabilities
        recommended_agents = []
        for req in new_requirements:
            # Map capability to recommended agent type
            agent_type = self._recommend_agent_type(req.capability)
            if agent_type and agent_type not in recommended_agents:
                recommended_agents.append(agent_type)

        # Build justification
        if requires_planning:
            justification = self._build_justification(
                new_requirements,
                context.existing_agents,
            )
        else:
            justification = (
                f"All detected capabilities can be handled by existing agents "
                f"({', '.join(context.existing_agents)}). No new agents required."
            )

        decision = AgentPlanningDecision(
            requires_agent_planning=requires_planning,
            required_capabilities=new_requirements,
            existing_capabilities=existing_capabilities,
            justification=justification,
            recommended_agent_types=recommended_agents,
        )

        _logger.info(
            "Maestro decision: requires_agent_planning=%s, recommended_agents=%s",
            requires_planning,
            recommended_agents,
        )

        return decision

    def _recommend_agent_type(self, capability: str) -> str | None:
        """Map a capability to a recommended agent type."""
        mapping = {
            # E2E testing
            "playwright": "playwright_e2e",
            "cypress": "cypress_e2e",
            "selenium": "selenium_e2e",
            # Frontend frameworks
            "react": "react_specialist",
            "vue": "vue_specialist",
            "angular": "angular_specialist",
            "svelte": "svelte_specialist",
            # Backend frameworks
            "fastapi": "fastapi_specialist",
            "django": "django_specialist",
            "flask": "flask_specialist",
            "express": "express_specialist",
            # Database
            "sqlalchemy": "database_specialist",
            "prisma": "database_specialist",
            "mongoose": "database_specialist",
            # Infrastructure
            "docker": "devops_specialist",
            "kubernetes": "kubernetes_specialist",
            "terraform": "infrastructure_specialist",
            "aws": "cloud_specialist",
            # Security/Performance
            "security_audit": "security_auditor",
            "performance_testing": "performance_tester",
            # Mobile
            "mobile": "mobile_specialist",
        }
        return mapping.get(capability)

    def _build_justification(
        self,
        requirements: list[CapabilityRequirement],
        existing_agents: list[str],
    ) -> str:
        """Build a human-readable justification for the planning decision."""
        lines = [
            f"Agent-planning required: {len(requirements)} specialized capabilities detected that cannot be handled by existing agents ({', '.join(existing_agents)}).",
            "",
            "Required capabilities:",
        ]

        for req in requirements:
            lines.append(
                f"  - {req.capability}: detected in {req.source} "
                f"(keywords: {', '.join(req.keywords_matched[:3])}{'...' if len(req.keywords_matched) > 3 else ''})"
            )

        lines.append("")
        lines.append(
            "Recommendation: Create specialized agents for the capabilities above "
            "to ensure high-quality implementation."
        )

        return "\n".join(lines)


# =============================================================================
# Module-Level Convenience Functions
# =============================================================================

# Singleton instance
_maestro_instance: Maestro | None = None


def get_maestro() -> Maestro:
    """Get or create the singleton Maestro instance."""
    global _maestro_instance
    if _maestro_instance is None:
        _maestro_instance = Maestro()
    return _maestro_instance


def reset_maestro() -> None:
    """Reset the singleton Maestro instance (useful for testing)."""
    global _maestro_instance
    _maestro_instance = None


def evaluate_project(context: ProjectContext) -> AgentPlanningDecision:
    """
    Convenience function to evaluate a project context.

    Args:
        context: Project context to evaluate

    Returns:
        AgentPlanningDecision
    """
    return get_maestro().evaluate(context)


def detect_agent_planning_required(
    project_name: str,
    tech_stack: list[str],
    features: list[dict[str, Any]],
    existing_agents: list[str] | None = None,
) -> AgentPlanningDecision:
    """
    High-level function to detect if agent planning is required.

    Args:
        project_name: Name of the project
        tech_stack: List of technologies used
        features: List of feature dictionaries
        existing_agents: Currently available agents (defaults to coding + testing)

    Returns:
        AgentPlanningDecision with the evaluation result

    Example:
        >>> decision = detect_agent_planning_required(
        ...     project_name="my-app",
        ...     tech_stack=["python", "react", "playwright"],
        ...     features=[{"name": "E2E tests for login", "description": "..."}],
        ... )
        >>> print(decision.requires_agent_planning)  # True
        >>> print(decision.recommended_agent_types)  # ["playwright_e2e", "react_specialist"]
    """
    context = ProjectContext(
        project_name=project_name,
        tech_stack=tech_stack,
        features=features,
        existing_agents=existing_agents or list(DEFAULT_AGENTS),
    )
    return get_maestro().evaluate(context)
