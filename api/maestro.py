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

    # -------------------------------------------------------------------------
    # Feature #175: OctoRequestPayload Construction
    # -------------------------------------------------------------------------

    def construct_octo_payload(
        self,
        decision: AgentPlanningDecision,
        context: ProjectContext,
        session: Optional[Session] = None,
    ) -> "OctoPayloadConstructionResult":
        """
        Construct a structured OctoRequestPayload from planning decision and context.

        Feature #175: Maestro produces structured Octo request payload

        This method gathers all context Octo needs to generate AgentSpecs:
        1. Gathers project discovery artifacts (app spec, README)
        2. Detects tech stack from project files
        3. Identifies execution environment (web, desktop, backend)
        4. Fetches feature backlog from database
        5. Constructs and validates OctoRequestPayload

        Args:
            decision: AgentPlanningDecision from evaluate()
            context: ProjectContext with project information
            session: Optional SQLAlchemy session for database queries

        Returns:
            OctoPayloadConstructionResult with payload or error info
        """
        from api.octo import OctoRequestPayload

        warnings: list[str] = []

        _logger.info(
            "Constructing OctoRequestPayload for project: %s",
            context.project_name,
        )

        try:
            # Step 1: Gather project discovery artifacts
            _logger.debug("Step 1: Gathering project discovery artifacts")
            discovery = self._gather_discovery_artifacts(context.project_dir)

            # Step 2: Detect tech stack from project files
            _logger.debug("Step 2: Detecting tech stack")
            tech_stack = self._detect_tech_stack_from_files(context.project_dir)
            # Merge with context tech_stack
            for tech in context.tech_stack:
                if tech not in tech_stack:
                    tech_stack.append(tech)

            # Step 3: Identify execution environment
            _logger.debug("Step 3: Identifying execution environment")
            execution_env = self._identify_execution_environment(
                tech_stack, context.project_dir
            )

            # Step 4: Fetch feature backlog if session provided
            feature_backlog: list[dict[str, Any]] = []
            total_features = 0
            passing_features = 0
            if session:
                _logger.debug("Step 4: Fetching feature backlog")
                feature_backlog, total_features, passing_features = (
                    self._fetch_feature_backlog(session, limit=20)
                )
            else:
                warnings.append("No database session - skipping feature backlog")

            # Step 5: Build project context for Octo
            project_context = {
                "name": context.project_name,
                "path": str(context.project_dir) if context.project_dir else None,
                "tech_stack": tech_stack,
                "execution_environment": execution_env,
                "app_spec_content": discovery.get("app_spec_content"),
                "app_spec_summary": discovery.get("app_spec_summary"),
                "readme_content": discovery.get("readme_content"),
                "directory_structure": discovery.get("directory_structure", []),
                "config_files": context.config_files,
                "feature_backlog": feature_backlog,
                "total_features": total_features,
                "passing_features": passing_features,
            }

            # Step 6: Build required capabilities from decision
            required_caps = [req.capability for req in decision.required_capabilities]

            # Step 7: Build constraints
            constraints = {
                "max_agents": len(required_caps),
                "existing_agent_count": len(decision.existing_capabilities),
            }

            # Step 8: Construct OctoRequestPayload
            payload = OctoRequestPayload(
                project_context=project_context,
                required_capabilities=required_caps,
                existing_agents=decision.existing_capabilities,
                constraints=constraints,
            )

            # Step 9: Validate payload
            validation_errors = payload.validate()
            if validation_errors:
                _logger.warning(
                    "Payload validation failed: %s", validation_errors
                )
                return OctoPayloadConstructionResult(
                    success=False,
                    error="Payload validation failed",
                    validation_errors=validation_errors,
                    warnings=warnings,
                )

            _logger.info(
                "OctoRequestPayload constructed: %d capabilities, env=%s",
                len(required_caps),
                execution_env,
            )

            return OctoPayloadConstructionResult(
                success=True,
                payload=payload,
                warnings=warnings,
            )

        except Exception as e:
            _logger.exception("Failed to construct OctoRequestPayload")
            return OctoPayloadConstructionResult(
                success=False,
                error=f"Failed to construct payload: {e}",
                warnings=warnings,
            )

    def _gather_discovery_artifacts(
        self,
        project_dir: Optional[Path],
    ) -> dict[str, Any]:
        """
        Gather project discovery artifacts from the project directory.

        Collects:
        - app_spec.txt content and summary
        - README content
        - Top-level directory structure

        Args:
            project_dir: Path to project root

        Returns:
            Dictionary with discovery artifacts
        """
        artifacts: dict[str, Any] = {
            "app_spec_content": None,
            "app_spec_summary": None,
            "readme_content": None,
            "directory_structure": [],
        }

        if not project_dir or not Path(project_dir).exists():
            return artifacts

        project_path = Path(project_dir)

        # Load app_spec.txt
        spec_paths = ["app_spec.txt", "app_spec.md", "spec.txt", "SPEC.md"]
        for spec_name in spec_paths:
            spec_path = project_path / spec_name
            if spec_path.exists():
                try:
                    content = spec_path.read_text(encoding="utf-8")
                    artifacts["app_spec_content"] = content
                    # Summary is first 500 chars
                    artifacts["app_spec_summary"] = (
                        content[:500] if len(content) > 500 else content
                    )
                    break
                except Exception as e:
                    _logger.warning("Failed to read %s: %s", spec_name, e)

        # Load README
        readme_paths = ["README.md", "readme.md", "README", "README.txt"]
        for readme_name in readme_paths:
            readme_path = project_path / readme_name
            if readme_path.exists():
                try:
                    content = readme_path.read_text(encoding="utf-8")
                    # Limit to 2000 chars
                    artifacts["readme_content"] = (
                        content[:2000] if len(content) > 2000 else content
                    )
                    break
                except Exception as e:
                    _logger.warning("Failed to read %s: %s", readme_name, e)

        # Get directory structure
        try:
            entries = []
            for item in sorted(project_path.iterdir()):
                if item.name.startswith('.'):
                    continue  # Skip hidden files
                if item.is_dir():
                    entries.append(f"{item.name}/")
                else:
                    entries.append(item.name)
            artifacts["directory_structure"] = entries[:50]  # Limit to 50 entries
        except Exception as e:
            _logger.warning("Failed to list directory: %s", e)

        return artifacts

    def _detect_tech_stack_from_files(
        self,
        project_dir: Optional[Path],
    ) -> list[str]:
        """
        Detect technology stack from project configuration files.

        Examines:
        - package.json (Node.js/JavaScript)
        - requirements.txt, pyproject.toml (Python)
        - go.mod (Go)
        - Cargo.toml (Rust)
        - Gemfile (Ruby)

        Args:
            project_dir: Path to project root

        Returns:
            List of detected technologies
        """
        tech_stack: list[str] = []

        if not project_dir or not Path(project_dir).exists():
            return tech_stack

        project_path = Path(project_dir)

        # Check for package.json (Node.js)
        package_json = project_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                tech_stack.append("Node.js")

                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                # Detect frameworks
                if "react" in deps:
                    tech_stack.append("React")
                if "vue" in deps:
                    tech_stack.append("Vue")
                if "angular" in deps or "@angular/core" in deps:
                    tech_stack.append("Angular")
                if "express" in deps:
                    tech_stack.append("Express")
                if "next" in deps:
                    tech_stack.append("Next.js")
                if "typescript" in deps:
                    tech_stack.append("TypeScript")

                # Detect testing
                if "jest" in deps:
                    tech_stack.append("Jest")
                if "playwright" in deps or "@playwright/test" in deps:
                    tech_stack.append("Playwright")
                if "vitest" in deps:
                    tech_stack.append("Vitest")

            except Exception as e:
                _logger.warning("Failed to parse package.json: %s", e)

        # Check for Python files
        requirements_txt = project_path / "requirements.txt"
        pyproject_toml = project_path / "pyproject.toml"

        if requirements_txt.exists() or pyproject_toml.exists():
            tech_stack.append("Python")

            # Read requirements for framework detection
            reqs_content = ""
            if requirements_txt.exists():
                try:
                    reqs_content = requirements_txt.read_text().lower()
                except Exception:
                    pass

            if "fastapi" in reqs_content:
                tech_stack.append("FastAPI")
            if "django" in reqs_content:
                tech_stack.append("Django")
            if "flask" in reqs_content:
                tech_stack.append("Flask")
            if "sqlalchemy" in reqs_content:
                tech_stack.append("SQLAlchemy")
            if "pytest" in reqs_content:
                tech_stack.append("pytest")
            if "dspy" in reqs_content:
                tech_stack.append("DSPy")

        # Check for Go
        if (project_path / "go.mod").exists():
            tech_stack.append("Go")

        # Check for Rust
        if (project_path / "Cargo.toml").exists():
            tech_stack.append("Rust")

        # Check for Ruby
        if (project_path / "Gemfile").exists():
            tech_stack.append("Ruby")

        # Check for databases
        for db_file in project_path.glob("*.db"):
            if "SQLite" not in tech_stack:
                tech_stack.append("SQLite")
            break

        return tech_stack

    def _identify_execution_environment(
        self,
        tech_stack: list[str],
        project_dir: Optional[Path],
    ) -> str:
        """
        Identify execution environment from tech stack and project structure.

        Args:
            tech_stack: Detected technology stack
            project_dir: Path to project root

        Returns:
            Execution environment: "web", "desktop", "backend", "mobile", "cli", "unknown"
        """
        tech_lower = set(t.lower() for t in tech_stack)

        # Web indicators
        web_frameworks = {"react", "vue", "angular", "next.js", "fastapi", "express", "django", "flask"}
        if tech_lower & web_frameworks:
            return "web"

        # CLI indicators
        if project_dir:
            project_path = Path(project_dir)
            cli_files = ["cli.py", "cli.ts", "__main__.py", "main.go"]
            for cli_file in cli_files:
                if (project_path / cli_file).exists():
                    return "cli"

        # Mobile indicators
        mobile_indicators = {"react native", "flutter", "ionic"}
        if tech_lower & mobile_indicators:
            return "mobile"

        # Desktop indicators
        desktop_indicators = {"electron", "tauri"}
        if tech_lower & desktop_indicators:
            return "desktop"

        # Backend default if server files exist
        if project_dir:
            project_path = Path(project_dir)
            backend_files = ["server.py", "app.py", "main.py", "server.ts", "app.ts"]
            for backend_file in backend_files:
                if (project_path / backend_file).exists():
                    return "backend"

        return "unknown"

    def _fetch_feature_backlog(
        self,
        session: Session,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """
        Fetch feature backlog from database.

        Args:
            session: SQLAlchemy session
            limit: Maximum features to return

        Returns:
            Tuple of (feature_list, total_count, passing_count)
        """
        from api.database import Feature
        from sqlalchemy import func, case

        try:
            # Get counts
            counts = session.query(
                func.count(Feature.id).label('total'),
                func.sum(case((Feature.passes == True, 1), else_=0)).label('passing')
            ).first()

            total = counts.total or 0
            passing = int(counts.passing or 0)

            # Get features ordered by priority
            features = session.query(Feature).order_by(Feature.priority).limit(limit).all()

            feature_list = []
            for f in features:
                status = "passing" if f.passes else ("in_progress" if f.in_progress else "pending")
                feature_list.append({
                    "id": f.id,
                    "name": f.name,
                    "category": f.category,
                    "status": status,
                    "dependencies": f.dependencies or [],
                })

            return feature_list, total, passing

        except Exception as e:
            _logger.warning("Failed to fetch feature backlog: %s", e)
            return [], 0, 0

    # -------------------------------------------------------------------------
    # Feature #176: Octo Delegation
    # -------------------------------------------------------------------------

    def delegate_to_octo(
        self,
        decision: AgentPlanningDecision,
        session: Session,
        project_dir: Path | str | None = None,
        *,
        run_id: str | None = None,
        context: Optional[ProjectContext] = None,
    ) -> "OctoDelegationResult":
        """
        Delegate to Octo service for AgentSpec generation.

        Feature #175: Maestro produces structured Octo request payload
        Feature #176: Maestro delegates to Octo for agent generation

        This method:
        1. Builds OctoRequestPayload from the planning decision using construct_octo_payload
        2. Calls Octo service with the payload
        3. Awaits Octo's response containing AgentSpecs
        4. Validates returned AgentSpecs against schema
        5. Records agent_planned audit event for each valid spec

        Args:
            decision: AgentPlanningDecision from evaluate()
            session: SQLAlchemy database session
            project_dir: Project directory for context
            run_id: Optional run_id for recording audit events
            context: Optional ProjectContext for full payload construction (Feature #175)

        Returns:
            OctoDelegationResult with generated specs and event IDs
        """
        # Lazy import to avoid circular dependency
        from api.octo import Octo, OctoRequestPayload, OctoResponse, get_octo

        _logger.info(
            "Delegating to Octo: %d capabilities requested",
            len(decision.required_capabilities),
        )

        # Feature #175: Use construct_octo_payload when context is provided
        if context is not None:
            _logger.info("Using construct_octo_payload with ProjectContext (Feature #175)")
            payload_result = self.construct_octo_payload(decision, context, session)

            if not payload_result.success:
                _logger.warning(
                    "Payload construction failed: %s",
                    payload_result.error,
                )
                return OctoDelegationResult(
                    success=False,
                    error=payload_result.error or "Payload construction failed",
                    warnings=payload_result.warnings + payload_result.validation_errors,
                )

            payload = payload_result.payload
        else:
            # Fallback: Build minimal OctoRequestPayload from decision (legacy behavior)
            _logger.debug("Using minimal payload construction (no ProjectContext)")
            required_caps = [req.capability for req in decision.required_capabilities]

            project_context = {
                "name": "unknown",
                "tech_stack": [],
                "execution_environment": "local",
            }

            # Enhance context if project_dir is provided
            if project_dir:
                project_path = Path(project_dir)
                project_context["name"] = project_path.name
                project_context["path"] = str(project_path)

                # Detect tech stack from files
                tech_stack = self._detect_tech_stack_from_files(project_path)
                project_context["tech_stack"] = tech_stack

                # Identify execution environment
                execution_env = self._identify_execution_environment(tech_stack, project_path)
                project_context["execution_environment"] = execution_env

                # Gather discovery artifacts
                discovery = self._gather_discovery_artifacts(project_path)
                project_context.update({
                    "app_spec_content": discovery.get("app_spec_content"),
                    "app_spec_summary": discovery.get("app_spec_summary"),
                    "readme_content": discovery.get("readme_content"),
                    "directory_structure": discovery.get("directory_structure", []),
                })

            payload = OctoRequestPayload(
                project_context=project_context,
                required_capabilities=required_caps,
                existing_agents=decision.existing_capabilities,
                constraints={},
            )

        # Step 1: Call Octo service
        try:
            octo = get_octo()
            response: OctoResponse = octo.generate_specs(payload)
        except Exception as e:
            _logger.exception("Octo invocation failed")
            return OctoDelegationResult(
                success=False,
                error=f"Octo invocation failed: {e}",
            )

        if not response.success:
            _logger.warning("Octo returned error: %s", response.error)
            return OctoDelegationResult(
                success=False,
                error=response.error,
                warnings=response.warnings,
            )

        # Step 2: Validate each returned AgentSpec
        valid_specs: list[AgentSpec] = []
        validation_results: list[SpecValidationResult] = []
        warnings: list[str] = list(response.warnings)

        for spec in response.agent_specs:
            result = validate_spec(spec)
            validation_results.append(result)

            if result.is_valid:
                valid_specs.append(spec)
            else:
                warnings.append(
                    f"Spec '{spec.name}' failed validation: {result.errors}"
                )

        # Step 3: Record agent_planned events for each valid spec
        event_ids: list[int] = []
        if run_id and session:
            event_recorder = get_event_recorder(session, project_dir)
            for spec in valid_specs:
                event_id = self._record_agent_planned_event(
                    event_recorder, run_id, spec
                )
                if event_id:
                    event_ids.append(event_id)

        _logger.info(
            "Delegation complete: %d/%d specs valid, %d events recorded",
            len(valid_specs),
            len(response.agent_specs),
            len(event_ids),
        )

        return OctoDelegationResult(
            success=len(valid_specs) > 0,
            agent_specs=valid_specs,
            validation_results=validation_results,
            event_ids=event_ids,
            warnings=warnings,
            error=None if valid_specs else "No valid specs generated",
        )

    def _record_agent_planned_event(
        self,
        event_recorder: EventRecorder,
        run_id: str,
        spec: AgentSpec,
    ) -> int | None:
        """
        Record an agent_planned audit event.

        Feature #176: Maestro records agent_planned audit event for each spec
        Feature #221: agent_planned audit event type

        Args:
            event_recorder: EventRecorder instance
            run_id: Run ID to associate event with
            spec: AgentSpec that was planned

        Returns:
            Event ID if recorded, None if failed
        """
        try:
            payload = {
                "agent_name": spec.name,
                "display_name": spec.display_name,
                "task_type": spec.task_type,
                "capabilities": spec.tags or [],
                "rationale": f"Generated by Octo for {spec.task_type} tasks",
            }

            event_id = event_recorder.record(
                run_id,
                "agent_planned",
                payload=payload,
            )

            _logger.debug(
                "Recorded agent_planned event: run=%s, spec=%s, event=%d",
                run_id,
                spec.name,
                event_id,
            )

            return event_id

        except Exception as e:
            _logger.exception("Failed to record agent_planned event")
            return None

    def record_agent_planned(
        self,
        session: Session,
        run_id: str,
        spec: AgentSpec,
        project_dir: Path | str | None = None,
        *,
        rationale: str | None = None,
        capabilities: list[str] | None = None,
    ) -> int | None:
        """
        Public method to record agent_planned event with custom rationale.

        Feature #176: Maestro records agent_planned audit event for each spec

        Args:
            session: SQLAlchemy database session
            run_id: Run ID to associate event with
            spec: AgentSpec that was planned
            project_dir: Project directory for event recorder
            rationale: Optional custom rationale
            capabilities: Optional capability list

        Returns:
            Event ID if recorded, None if failed
        """
        try:
            event_recorder = get_event_recorder(session, project_dir)

            payload = {
                "agent_name": spec.name,
                "display_name": spec.display_name,
                "task_type": spec.task_type,
                "capabilities": capabilities or spec.tags or [],
                "rationale": rationale or f"Agent planned for {spec.task_type}",
            }

            event_id = event_recorder.record(
                run_id,
                "agent_planned",
                payload=payload,
            )

            return event_id

        except Exception as e:
            _logger.exception("Failed to record agent_planned event")
            return None

    # -------------------------------------------------------------------------
    # Feature #180: Graceful Octo Failure Handling
    # -------------------------------------------------------------------------

    def delegate_to_octo_with_fallback(
        self,
        decision: AgentPlanningDecision,
        session: Session,
        project_dir: Path | str | None = None,
        *,
        run_id: str | None = None,
    ) -> "OctoDelegationWithFallbackResult":
        """
        Delegate to Octo for AgentSpec generation with graceful fallback.

        Feature #180: Maestro handles Octo failures gracefully

        This method wraps Octo invocation in error handling and provides:
        1. Error handling around Octo invocation
        2. Full context logging on failure
        3. Fallback to default/existing agents on failure
        4. Failure recorded as audit event with error details
        5. Continuation with available agents

        Args:
            decision: AgentPlanningDecision from evaluate()
            session: SQLAlchemy database session
            project_dir: Project directory for context
            run_id: Optional run_id for recording audit events

        Returns:
            OctoDelegationWithFallbackResult containing:
            - generated specs (if Octo succeeded) or empty list
            - fallback_used: True if fallback was triggered
            - available_agents: List of agents available for execution
            - event_ids: Audit event IDs (including failure event if applicable)
        """
        _logger.info(
            "Delegating to Octo with fallback: %d capabilities requested",
            len(decision.required_capabilities),
        )

        # Track fallback and events
        fallback_used = False
        failure_event_id: int | None = None
        octo_error: str | None = None
        octo_error_type: str | None = None

        # Step 1: Attempt Octo delegation (wrapped in error handling)
        try:
            delegation_result = self.delegate_to_octo(
                decision,
                session,
                project_dir=project_dir,
                run_id=run_id,
            )

            if delegation_result.success and delegation_result.agent_specs:
                # Octo succeeded - return with generated specs
                _logger.info(
                    "Octo delegation succeeded: %d specs generated",
                    len(delegation_result.agent_specs),
                )

                # Available agents = existing + newly generated
                available_agents = list(decision.existing_capabilities)
                for spec in delegation_result.agent_specs:
                    if spec.name not in available_agents:
                        available_agents.append(spec.name)

                return OctoDelegationWithFallbackResult(
                    success=True,
                    agent_specs=delegation_result.agent_specs,
                    fallback_used=False,
                    available_agents=available_agents,
                    event_ids=delegation_result.event_ids,
                    warnings=delegation_result.warnings,
                )

            # Octo returned failure response
            octo_error = delegation_result.error or "No valid specs generated"
            octo_error_type = "generation_failed"
            _logger.warning(
                "Octo delegation failed with error: %s",
                octo_error,
            )

        except Exception as e:
            # Exception during Octo invocation
            octo_error = f"Octo invocation exception: {e}"
            octo_error_type = "exception"
            _logger.exception(
                "Exception during Octo delegation: %s", e,
            )

        # Step 2: Log error with full context
        _logger.error(
            "Octo failure - falling back to default agents. "
            "Error: %s, Type: %s, Required capabilities: %s, "
            "Existing agents: %s",
            octo_error,
            octo_error_type,
            [req.capability for req in decision.required_capabilities],
            decision.existing_capabilities,
        )

        # Step 3: Fall back to default/existing agents
        fallback_used = True
        fallback_agents = list(decision.existing_capabilities)

        # Include default agents if not already present
        for default_agent in self.default_agents:
            if default_agent not in fallback_agents:
                fallback_agents.append(default_agent)

        _logger.info(
            "Falling back to agents: %s",
            fallback_agents,
        )

        # Step 4: Record failure as audit event
        if run_id and session:
            try:
                event_recorder = get_event_recorder(session, project_dir)
                failure_event_id = event_recorder.record_octo_failure(
                    run_id,
                    error=octo_error or "Unknown error",
                    error_type=octo_error_type,
                    required_capabilities=[
                        req.capability for req in decision.required_capabilities
                    ],
                    fallback_agents=fallback_agents,
                    context={
                        "decision_justification": decision.justification,
                        "recommended_agent_types": decision.recommended_agent_types,
                    },
                )
                _logger.info(
                    "Recorded octo_failure event: run=%s, event_id=%s",
                    run_id, failure_event_id,
                )
            except Exception as e:
                _logger.exception("Failed to record octo_failure event: %s", e)

        # Step 5: Return result allowing execution to continue
        event_ids = [failure_event_id] if failure_event_id else []

        return OctoDelegationWithFallbackResult(
            success=False,  # Octo failed
            agent_specs=[],  # No specs generated
            fallback_used=True,
            available_agents=fallback_agents,
            event_ids=event_ids,
            error=octo_error,
            error_type=octo_error_type,
            warnings=[f"Octo failed: {octo_error}. Using fallback agents."],
        )

    def _record_octo_failure_event(
        self,
        event_recorder: EventRecorder,
        run_id: str,
        error: str,
        error_type: str | None,
        decision: AgentPlanningDecision,
        fallback_agents: list[str],
    ) -> int | None:
        """
        Record an octo_failure audit event.

        Feature #180: Failure recorded as audit event with error details

        Args:
            event_recorder: EventRecorder instance
            run_id: Run ID to associate event with
            error: Error message
            error_type: Type of error
            decision: AgentPlanningDecision that triggered Octo call
            fallback_agents: Agents being used as fallback

        Returns:
            Event ID if recorded, None if failed
        """
        try:
            return event_recorder.record_octo_failure(
                run_id,
                error=error,
                error_type=error_type,
                required_capabilities=[
                    req.capability for req in decision.required_capabilities
                ],
                fallback_agents=fallback_agents,
                context={
                    "decision_justification": decision.justification,
                    "recommended_agent_types": decision.recommended_agent_types,
                },
            )
        except Exception as e:
            _logger.exception("Failed to record octo_failure event")
            return None

    # -------------------------------------------------------------------------
    # Feature #177: Materialization Orchestration
    # -------------------------------------------------------------------------

    def receive_specs_from_octo(
        self,
        specs: list[AgentSpec],
        *,
        validate: bool = True,
    ) -> list[AgentSpec]:
        """
        Receive and optionally validate AgentSpecs from Octo.

        Step 1 of Feature #177: Maestro receives validated AgentSpecs from Octo

        Args:
            specs: List of AgentSpecs received from Octo
            validate: Whether to validate specs against schema

        Returns:
            List of validated AgentSpecs
        """
        if not specs:
            _logger.warning("Received empty AgentSpec list from Octo")
            return []

        _logger.info("Received %d AgentSpecs from Octo", len(specs))

        if validate:
            validated = []
            for spec in specs:
                if self._validate_spec_for_materialization(spec):
                    validated.append(spec)
                else:
                    _logger.warning(
                        "AgentSpec '%s' (id=%s) failed validation, skipping",
                        getattr(spec, 'name', 'unknown'),
                        getattr(spec, 'id', 'unknown'),
                    )
            return validated

        return specs

    def _validate_spec_for_materialization(self, spec: AgentSpec) -> bool:
        """
        Validate a single AgentSpec for materialization.

        Checks:
        - Required fields are present (id, name, task_type)
        - Name is valid (alphanumeric with hyphens/underscores)

        Args:
            spec: AgentSpec to validate

        Returns:
            True if valid, False otherwise
        """
        # Check required fields
        if not getattr(spec, 'id', None):
            _logger.error("AgentSpec missing id")
            return False

        if not getattr(spec, 'name', None):
            _logger.error("AgentSpec %s missing name", spec.id)
            return False

        if not getattr(spec, 'task_type', None):
            _logger.error("AgentSpec %s missing task_type", spec.id)
            return False

        # Validate name format (alphanumeric, hyphens, underscores)
        if not re.match(r'^[a-zA-Z0-9_-]+$', spec.name):
            _logger.error(
                "AgentSpec %s has invalid name format: %s",
                spec.id, spec.name,
            )
            return False

        return True

    def invoke_materializer(
        self,
        specs: list[AgentSpec],
    ) -> list[MaterializationResult]:
        """
        Invoke the AgentMaterializer to create agent files.

        Step 2 of Feature #177: Maestro invokes Agent Materializer with AgentSpecs

        Args:
            specs: List of AgentSpecs to materialize

        Returns:
            List of MaterializationResults

        Raises:
            RuntimeError: If no materializer is configured
        """
        if not self.materializer:
            raise RuntimeError(
                "No materializer configured. Initialize Maestro with project_dir "
                "or materializer parameter to enable materialization."
            )

        _logger.info(
            "Invoking AgentMaterializer for %d specs at %s",
            len(specs), self.materializer.output_path,
        )

        results = []
        for spec in specs:
            result = self.materializer.materialize(spec)
            results.append(result)

        succeeded = sum(1 for r in results if r.success)
        _logger.info(
            "Materialization complete: %d/%d succeeded",
            succeeded, len(specs),
        )

        return results

    async def await_materialization(
        self,
        specs: list[AgentSpec],
    ) -> list[MaterializationResult]:
        """
        Async version: await materialization completion.

        Step 3 of Feature #177: Maestro awaits materialization completion

        Args:
            specs: List of AgentSpecs to materialize

        Returns:
            List of MaterializationResults
        """
        # For now, materialization is synchronous, but this provides
        # the async interface for future async file I/O
        return self.invoke_materializer(specs)

    def verify_agent_files(
        self,
        specs: list[AgentSpec],
    ) -> dict[str, bool]:
        """
        Verify agent files exist in .claude/agents/generated/.

        Step 4 of Feature #177: Maestro verifies agent files exist

        Args:
            specs: List of AgentSpecs to verify

        Returns:
            Dictionary mapping spec_id to existence status

        Raises:
            RuntimeError: If no materializer is configured
        """
        if not self.materializer:
            raise RuntimeError(
                "No materializer configured. Initialize Maestro with project_dir "
                "or materializer parameter to enable materialization."
            )

        _logger.info(
            "Verifying agent files in %s",
            self.materializer.output_path,
        )

        verification = self.materializer.verify_all(specs)

        verified_count = sum(1 for v in verification.values() if v)
        _logger.info(
            "Verification complete: %d/%d files exist",
            verified_count, len(specs),
        )

        return verification

    def orchestrate_materialization(
        self,
        specs: list[AgentSpec],
        *,
        validate: bool = True,
    ) -> OrchestrationResult:
        """
        Full orchestration flow: receive -> materialize -> verify.

        This is the main entry point for Feature #177, implementing the
        complete flow after Octo completes spec generation.

        Args:
            specs: List of AgentSpecs from Octo
            validate: Whether to validate specs before processing

        Returns:
            OrchestrationResult with complete status
        """
        _logger.info("Starting materialization orchestration for %d specs", len(specs))
        audit_events: list[str] = []

        # Step 1: Receive and validate specs from Octo
        validated_specs = self.receive_specs_from_octo(specs, validate=validate)

        if not validated_specs:
            _logger.warning("No valid specs to materialize")
            return OrchestrationResult(
                total=len(specs),
                succeeded=0,
                failed=len(specs),
                verified=False,
            )

        # Step 2 & 3: Invoke materializer
        results = self.invoke_materializer(validated_specs)

        # Step 4: Verify files exist
        verification = self.verify_agent_files(validated_specs)

        # Calculate stats
        succeeded = sum(1 for r in results if r.success)
        failed = len(results) - succeeded
        all_verified = all(verification.values()) if verification else False

        orchestration_result = OrchestrationResult(
            total=len(validated_specs),
            succeeded=succeeded,
            failed=failed,
            results=results,
            verified=all_verified,
            audit_events=audit_events,
        )

        _logger.info(
            "Materialization orchestration complete: %d/%d succeeded, verified=%s",
            succeeded, len(validated_specs), all_verified,
        )

        return orchestration_result

    # -------------------------------------------------------------------------
    # Feature #179: Decision Persistence
    # -------------------------------------------------------------------------

    def persist_decision(
        self,
        decision: AgentPlanningDecision,
        project_name: str,
        session: Session,
        *,
        project_context: ProjectContext | None = None,
        triggering_feature_ids: list[int] | None = None,
    ) -> "PersistDecisionResult":
        """
        Persist an agent-planning decision to the database.

        Feature #179: Maestro persists agent-planning decisions to database

        This method:
        1. Creates an AgentPlanningDecisionRecord from the decision
        2. Stores decision rationale, required capabilities, and timestamp
        3. Links decision to project and triggering feature(s)
        4. Commits to database for auditability

        Args:
            decision: AgentPlanningDecision to persist
            project_name: Name of the project this decision is for
            session: SQLAlchemy database session
            project_context: Optional ProjectContext for snapshot storage
            triggering_feature_ids: Optional list of feature IDs that triggered this decision

        Returns:
            PersistDecisionResult with the created record ID and success status
        """
        from api.agentspec_models import AgentPlanningDecisionRecord

        _logger.info(
            "Persisting agent-planning decision for project '%s' (requires_planning=%s)",
            project_name, decision.requires_agent_planning,
        )

        try:
            # Build the record from the decision
            record = AgentPlanningDecisionRecord(
                id=generate_uuid(),
                project_name=project_name,
                requires_agent_planning=decision.requires_agent_planning,
                justification=decision.justification,
                required_capabilities=[
                    req.to_dict() for req in decision.required_capabilities
                ],
                existing_capabilities=decision.existing_capabilities,
                recommended_agent_types=decision.recommended_agent_types,
                project_context_snapshot=(
                    project_context.to_dict() if project_context else None
                ),
                triggering_feature_ids=triggering_feature_ids,
            )

            session.add(record)
            session.commit()

            _logger.info(
                "Successfully persisted decision id=%s for project '%s'",
                record.id, project_name,
            )

            return PersistDecisionResult(
                success=True,
                decision_id=record.id,
                record=record,
            )

        except Exception as e:
            session.rollback()
            _logger.exception(
                "Failed to persist decision for project '%s': %s",
                project_name, e,
            )
            return PersistDecisionResult(
                success=False,
                error=str(e),
            )

    def evaluate_and_persist(
        self,
        context: ProjectContext,
        session: Session,
        *,
        triggering_feature_ids: list[int] | None = None,
    ) -> tuple[AgentPlanningDecision, "PersistDecisionResult"]:
        """
        Convenience method to evaluate and persist in one call.

        Feature #179: Combined evaluate + persist workflow

        Args:
            context: ProjectContext to evaluate
            session: SQLAlchemy database session
            triggering_feature_ids: Optional list of feature IDs

        Returns:
            Tuple of (decision, persist_result)
        """
        decision = self.evaluate(context)
        persist_result = self.persist_decision(
            decision=decision,
            project_name=context.project_name,
            session=session,
            project_context=context,
            triggering_feature_ids=triggering_feature_ids,
        )
        return decision, persist_result


# =============================================================================
# Feature #179: Persist Decision Result
# =============================================================================

@dataclass
class PersistDecisionResult:
    """
    Result of persisting an agent-planning decision.

    Feature #179: Maestro persists agent-planning decisions to database
    """
    success: bool
    decision_id: str | None = None
    record: Any | None = None  # AgentPlanningDecisionRecord
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "decision_id": self.decision_id,
            "record": self.record.to_dict() if self.record else None,
            "error": self.error,
        }


# =============================================================================
# Feature #175: Octo Payload Construction Result
# =============================================================================

@dataclass
class OctoPayloadConstructionResult:
    """
    Result of constructing an OctoRequestPayload.

    Feature #175: Maestro produces structured Octo request payload

    Attributes:
        success: Whether payload construction succeeded
        payload: The constructed OctoRequestPayload (if successful)
        error: Error message (if failed)
        validation_errors: List of validation errors
        warnings: List of warnings (non-fatal issues)
    """
    success: bool
    payload: Any = None  # OctoRequestPayload, using Any to avoid circular import
    error: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "payload": self.payload.to_dict() if self.payload else None,
            "error": self.error,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
        }


# =============================================================================
# Feature #176: Octo Delegation Result
# =============================================================================

@dataclass
class OctoDelegationResult:
    """
    Result of delegating to Octo for AgentSpec generation.

    Captures the outcome including generated specs, validation results,
    and audit event IDs.

    Feature #176: Maestro delegates to Octo for agent generation
    """
    success: bool
    agent_specs: list[AgentSpec] = field(default_factory=list)
    validation_results: list[SpecValidationResult] = field(default_factory=list)
    event_ids: list[int] = field(default_factory=list)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "agent_specs": [spec.to_dict() for spec in self.agent_specs],
            "validation_results": [
                r.to_dict() if hasattr(r, 'to_dict') else {"is_valid": r.is_valid, "errors": r.errors}
                for r in self.validation_results
            ],
            "event_ids": self.event_ids,
            "error": self.error,
            "warnings": self.warnings,
        }


# =============================================================================
# Feature #180: Octo Delegation With Fallback Result
# =============================================================================

@dataclass
class OctoDelegationWithFallbackResult:
    """
    Result of delegating to Octo with graceful fallback handling.

    Feature #180: Maestro handles Octo failures gracefully

    This extends OctoDelegationResult with fallback-specific fields:
    - fallback_used: Whether default agents were used as fallback
    - available_agents: List of agents available for continued execution
    - error_type: Classification of the error (if any)
    """
    success: bool
    agent_specs: list[AgentSpec] = field(default_factory=list)
    fallback_used: bool = False
    available_agents: list[str] = field(default_factory=list)
    event_ids: list[int] = field(default_factory=list)
    error: str | None = None
    error_type: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def can_continue_execution(self) -> bool:
        """
        Check if execution can continue with available agents.

        Feature #180: Feature execution continues with available agents

        Returns True if:
        - Octo succeeded and generated specs, OR
        - Fallback was triggered and agents are available
        """
        return bool(self.agent_specs) or (self.fallback_used and bool(self.available_agents))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "agent_specs": [spec.to_dict() for spec in self.agent_specs],
            "fallback_used": self.fallback_used,
            "available_agents": self.available_agents,
            "can_continue_execution": self.can_continue_execution,
            "event_ids": self.event_ids,
            "error": self.error,
            "error_type": self.error_type,
            "warnings": self.warnings,
        }


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


# =============================================================================
# Feature #181: Agent Tracking Data Classes
# =============================================================================

@dataclass
class AgentInfo:
    """
    Information about an available agent.

    Feature #181: Maestro tracks which agents are available per project

    Attributes:
        name: Machine-readable agent name (e.g., "coder", "auditor")
        display_name: Human-readable display name
        source: Where this agent was discovered ("file", "database", "default")
        source_path: Path to the agent file (if file-based)
        spec_id: Database ID (if DB-based)
        capabilities: List of capabilities this agent provides
        model: Preferred model (if specified)
    """
    name: str
    display_name: str
    source: str  # "file", "database", "default"
    source_path: Path | None = None
    spec_id: str | None = None
    capabilities: list[str] = field(default_factory=list)
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "source": self.source,
            "source_path": str(self.source_path) if self.source_path else None,
            "spec_id": self.spec_id,
            "capabilities": self.capabilities,
            "model": self.model,
        }


@dataclass
class AvailableAgentsResult:
    """
    Result of scanning for available agents.

    Feature #181: Maestro tracks which agents are available per project

    Attributes:
        agents: List of discovered agents
        file_based_count: Number of agents found in files
        db_based_count: Number of agents found in database
        default_count: Number of default agents included
        scan_paths: Paths that were scanned
        errors: Any errors encountered during scanning
    """
    agents: list[AgentInfo] = field(default_factory=list)
    file_based_count: int = 0
    db_based_count: int = 0
    default_count: int = 0
    scan_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of available agents."""
        return len(self.agents)

    @property
    def agent_names(self) -> list[str]:
        """List of agent names for quick reference."""
        return [a.name for a in self.agents]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agents": [a.to_dict() for a in self.agents],
            "file_based_count": self.file_based_count,
            "db_based_count": self.db_based_count,
            "default_count": self.default_count,
            "total_count": self.total_count,
            "agent_names": self.agent_names,
            "scan_paths": self.scan_paths,
            "errors": self.errors,
        }
