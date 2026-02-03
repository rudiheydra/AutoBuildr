"""
Agent Materializer - Convert AgentSpec to Claude Code Markdown
================================================================

Feature #192: Agent Materializer converts AgentSpec to Claude Code markdown

The Agent Materializer takes AgentSpec objects and renders them as Claude Code-compatible
markdown files. These files follow the Claude Code agent file conventions:

1. YAML frontmatter with: name, description, model, optional color
2. Markdown body with comprehensive agent instructions

The output is deterministic: given the same AgentSpec input, the materializer
will always produce the identical output (timestamps are not included in
generated content to ensure determinism).

Claude Code Agent File Convention Reference:
- .claude/agents/*.md format
- YAML frontmatter delimited by ---
- Frontmatter fields: name (required), description (required), model (required), color (optional)
- Body: Markdown instructions for the agent
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default output directory relative to project root (Claude Code convention)
DEFAULT_OUTPUT_DIR = ".claude/agents/generated"

# Valid models for Claude Code agents
VALID_MODELS = frozenset({"sonnet", "opus", "haiku"})

# Default model if not specified
DEFAULT_MODEL = "sonnet"

# Task type to color mapping for visual distinction in UI
TASK_TYPE_COLORS: dict[str, str] = {
    "coding": "blue",
    "testing": "green",
    "refactoring": "purple",
    "documentation": "cyan",
    "audit": "red",
    "custom": "gray",
}

# Default color if task type not in mapping
DEFAULT_COLOR = "orange"

# Maximum length for description in frontmatter (Claude Code convention)
DESCRIPTION_MAX_LENGTH = 2000


# =============================================================================
# Data Classes
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
        content_hash: SHA256 hash of the generated content (for determinism verification)
    """
    spec_id: str
    spec_name: str
    success: bool
    file_path: Path | None = None
    error: str | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "spec_id": self.spec_id,
            "spec_name": self.spec_name,
            "success": self.success,
            "file_path": str(self.file_path) if self.file_path else None,
            "error": self.error,
            "content_hash": self.content_hash,
        }


@dataclass
class BatchMaterializationResult:
    """
    Result of materializing multiple AgentSpecs.

    Attributes:
        total: Total number of specs processed
        succeeded: Number of successful materializations
        failed: Number of failed materializations
        results: Individual results for each spec
        all_succeeded: True if all specs were successfully materialized
    """
    total: int
    succeeded: int
    failed: int
    results: list[MaterializationResult] = field(default_factory=list)

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
            "results": [r.to_dict() for r in self.results],
        }


# =============================================================================
# Agent Materializer Class
# =============================================================================

class AgentMaterializer:
    """
    Materializes AgentSpecs into Claude Code-compatible markdown files.

    The materializer creates markdown files with:
    - YAML frontmatter: name, description, model, color
    - Markdown body: Agent instructions including objective, tools, and guidance

    Output is deterministic: same input produces identical output.
    """

    def __init__(
        self,
        project_dir: Path | str,
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
        self._output_dir = output_dir or DEFAULT_OUTPUT_DIR

        _logger.info(
            "AgentMaterializer initialized: project_dir=%s, output_dir=%s",
            self.project_dir, self._output_dir,
        )

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

    # -------------------------------------------------------------------------
    # Core Materialization Methods
    # -------------------------------------------------------------------------

    def materialize(self, spec: "AgentSpec") -> MaterializationResult:
        """
        Materialize a single AgentSpec to a Claude Code markdown file.

        Creates a markdown file with:
        - YAML frontmatter (name, description, model, color)
        - Markdown body with agent instructions

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

            # Build Claude Code-compatible content
            content = self.render_claude_code_markdown(spec)

            # Compute content hash for determinism verification
            import hashlib
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            # Write the file
            filepath.write_text(content, encoding="utf-8")

            _logger.info(
                "Materialized AgentSpec '%s' to %s (hash: %s)",
                spec.name, filepath, content_hash[:16],
            )

            return MaterializationResult(
                spec_id=spec.id,
                spec_name=spec.name,
                success=True,
                file_path=filepath,
                content_hash=content_hash,
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

    def materialize_batch(self, specs: list["AgentSpec"]) -> BatchMaterializationResult:
        """
        Materialize multiple AgentSpecs.

        Args:
            specs: List of AgentSpecs to materialize

        Returns:
            BatchMaterializationResult with individual results
        """
        results = []
        succeeded = 0
        failed = 0

        for spec in specs:
            result = self.materialize(spec)
            results.append(result)
            if result.success:
                succeeded += 1
            else:
                failed += 1

        return BatchMaterializationResult(
            total=len(specs),
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    # -------------------------------------------------------------------------
    # Claude Code Markdown Rendering
    # -------------------------------------------------------------------------

    def render_claude_code_markdown(self, spec: "AgentSpec") -> str:
        """
        Render an AgentSpec as Claude Code-compatible markdown.

        Output follows Claude Code agent file conventions:
        - YAML frontmatter with: name, description, model, color
        - Markdown body with agent instructions

        This method is deterministic: same input produces identical output.

        Args:
            spec: The AgentSpec to render

        Returns:
            Claude Code-compatible markdown string
        """
        lines = []

        # Build YAML frontmatter
        frontmatter = self._build_frontmatter(spec)
        lines.append("---")
        for key, value in frontmatter.items():
            if isinstance(value, str) and ("\n" in value or '"' in value):
                # Multi-line or quoted strings need proper YAML escaping
                escaped = self._escape_yaml_string(value)
                lines.append(f"{key}: {escaped}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        lines.append("")

        # Build markdown body with agent instructions
        body = self._build_instructions_body(spec)
        lines.append(body)

        return "\n".join(lines)

    def _build_frontmatter(self, spec: "AgentSpec") -> dict[str, Any]:
        """
        Build the YAML frontmatter for Claude Code agent file.

        Required fields:
        - name: Agent identifier (from spec.name)
        - description: Agent description with usage examples
        - model: Claude model to use (sonnet/opus/haiku)

        Optional fields:
        - color: UI color for visual distinction

        Args:
            spec: The AgentSpec to extract frontmatter from

        Returns:
            Dictionary of frontmatter key-value pairs (ordered)
        """
        # Extract model from context or use default
        model = self._extract_model(spec)

        # Build description with objective and context
        description = self._build_description(spec)

        # Determine color based on task type
        color = TASK_TYPE_COLORS.get(spec.task_type, DEFAULT_COLOR)

        # Return ordered frontmatter
        return {
            "name": spec.name,
            "description": description,
            "model": model,
            "color": color,
        }

    def _extract_model(self, spec: "AgentSpec") -> str:
        """
        Extract model from AgentSpec context or use default.

        Args:
            spec: The AgentSpec

        Returns:
            Model string (sonnet/opus/haiku)
        """
        if spec.context and isinstance(spec.context, dict):
            model = spec.context.get("model")
            if model and model.lower() in VALID_MODELS:
                return model.lower()

        return DEFAULT_MODEL

    def _build_description(self, spec: "AgentSpec") -> str:
        """
        Build the description field for frontmatter.

        Combines display_name, objective, and task type into a
        Claude Code-compatible description with usage examples.

        Args:
            spec: The AgentSpec

        Returns:
            Description string (properly escaped for YAML)
        """
        parts = []

        # Main description
        if spec.display_name:
            parts.append(f"Agent: {spec.display_name}")

        # Task type context
        parts.append(f"Task Type: {spec.task_type}")

        # Objective
        if spec.objective:
            objective_text = spec.objective[:500]  # Truncate for frontmatter
            parts.append(f"Objective: {objective_text}")

        # Example usage (Claude Code convention)
        parts.append("")
        parts.append("Example usage:")
        parts.append("<example>")
        parts.append(f'user: "Execute {spec.display_name or spec.name}"')
        parts.append(f'assistant: "I\'ll use the {spec.name} agent to accomplish this task."')
        parts.append("<Task tool invocation>")
        parts.append("</example>")

        description = "\\n".join(parts)

        # Enforce max length
        if len(description) > DESCRIPTION_MAX_LENGTH:
            description = description[:DESCRIPTION_MAX_LENGTH - 3] + "..."

        return description

    def _build_instructions_body(self, spec: "AgentSpec") -> str:
        """
        Build the markdown body with agent instructions.

        This includes:
        - Agent role and identity
        - Objective and goals
        - Tool policy (allowed tools, restrictions)
        - Execution guidelines
        - Context information

        Args:
            spec: The AgentSpec

        Returns:
            Markdown body string
        """
        sections = []

        # Agent role introduction
        sections.append(self._build_role_section(spec))

        # Objective section
        sections.append(self._build_objective_section(spec))

        # Tool policy section
        sections.append(self._build_tool_policy_section(spec))

        # Execution guidelines
        sections.append(self._build_guidelines_section(spec))

        # Context section (if available)
        if spec.context:
            sections.append(self._build_context_section(spec))

        # Acceptance criteria (if available)
        if spec.acceptance_spec:
            sections.append(self._build_acceptance_section(spec))

        return "\n\n".join(filter(None, sections))

    def _build_role_section(self, spec: "AgentSpec") -> str:
        """Build the agent role/identity section."""
        display_name = spec.display_name or spec.name
        task_type = spec.task_type

        role_descriptions = {
            "coding": "You are a skilled software developer focused on writing high-quality, maintainable code.",
            "testing": "You are a thorough test engineer focused on ensuring software quality through comprehensive testing.",
            "refactoring": "You are an experienced software architect focused on improving code structure and maintainability.",
            "documentation": "You are a technical writer focused on creating clear, accurate documentation.",
            "audit": "You are a security auditor focused on identifying vulnerabilities and ensuring compliance.",
            "custom": "You are a specialized agent tailored for specific tasks.",
        }

        role = role_descriptions.get(task_type, role_descriptions["custom"])

        return f"""You are **{display_name}**.

{role}

Your agent identifier is `{spec.name}` and you operate as a `{task_type}` agent."""

    def _build_objective_section(self, spec: "AgentSpec") -> str:
        """Build the objective section."""
        objective = spec.objective or "(No specific objective defined)"

        return f"""## Your Objective

{objective}

Focus on achieving this objective while following the guidelines and constraints defined below."""

    def _build_tool_policy_section(self, spec: "AgentSpec") -> str:
        """Build the tool policy section."""
        lines = ["## Tool Policy"]
        lines.append("")

        if spec.tool_policy and isinstance(spec.tool_policy, dict):
            allowed_tools = spec.tool_policy.get("allowed_tools", [])
            forbidden_patterns = spec.tool_policy.get("forbidden_patterns", [])
            tool_hints = spec.tool_policy.get("tool_hints", {})

            # Allowed tools
            if allowed_tools:
                lines.append(f"### Allowed Tools ({len(allowed_tools)} available)")
                lines.append("")
                lines.append("You have access to the following tools:")
                lines.append("")
                for tool in sorted(allowed_tools)[:30]:  # Cap display at 30
                    lines.append(f"- `{tool}`")
                if len(allowed_tools) > 30:
                    lines.append(f"- ... and {len(allowed_tools) - 30} more tools")
                lines.append("")

            # Forbidden patterns
            if forbidden_patterns:
                lines.append("### Restrictions")
                lines.append("")
                lines.append("The following patterns are **forbidden** and must not appear in your commands or outputs:")
                lines.append("")
                for pattern in forbidden_patterns[:10]:
                    lines.append(f"- `{pattern}`")
                if len(forbidden_patterns) > 10:
                    lines.append(f"- ... and {len(forbidden_patterns) - 10} more patterns")
                lines.append("")

            # Tool hints
            if tool_hints:
                lines.append("### Tool Usage Hints")
                lines.append("")
                for tool_name, hint in list(tool_hints.items())[:10]:
                    hint_text = hint[:200] if len(hint) > 200 else hint
                    lines.append(f"- **{tool_name}**: {hint_text}")
                lines.append("")
        else:
            lines.append("No specific tool policy defined. Use tools responsibly.")
            lines.append("")

        return "\n".join(lines)

    def _build_guidelines_section(self, spec: "AgentSpec") -> str:
        """Build execution guidelines section."""
        lines = ["## Execution Guidelines"]
        lines.append("")

        # Budget constraints
        lines.append("### Budget Constraints")
        lines.append("")
        lines.append(f"- **Maximum Turns**: {spec.max_turns}")
        lines.append(f"- **Timeout**: {spec.timeout_seconds} seconds")
        lines.append("")

        # Task-specific guidelines based on task type
        guidelines = self._get_task_type_guidelines(spec.task_type)
        if guidelines:
            lines.append("### Best Practices")
            lines.append("")
            for guideline in guidelines:
                lines.append(f"- {guideline}")
            lines.append("")

        return "\n".join(lines)

    def _get_task_type_guidelines(self, task_type: str) -> list[str]:
        """Get task-type-specific guidelines."""
        guidelines_map = {
            "coding": [
                "Write clean, maintainable code following project conventions",
                "Include appropriate comments and documentation",
                "Handle errors gracefully",
                "Follow security best practices",
                "Run lint and type checks before completing",
            ],
            "testing": [
                "Write comprehensive test cases covering edge cases",
                "Ensure tests are deterministic and repeatable",
                "Use meaningful test names that describe behavior",
                "Verify both positive and negative scenarios",
                "Report test results clearly",
            ],
            "refactoring": [
                "Maintain existing functionality while improving structure",
                "Make incremental changes that can be reviewed",
                "Update tests to reflect refactored code",
                "Document significant architectural decisions",
                "Verify no regressions are introduced",
            ],
            "documentation": [
                "Write clear, concise documentation",
                "Include code examples where appropriate",
                "Keep documentation up-to-date with code changes",
                "Use consistent formatting and terminology",
                "Consider the target audience's technical level",
            ],
            "audit": [
                "Follow security best practices and standards",
                "Document all findings with severity levels",
                "Provide actionable remediation recommendations",
                "Never execute potentially harmful code",
                "Report sensitive findings appropriately",
            ],
        }
        return guidelines_map.get(task_type, [])

    def _build_context_section(self, spec: "AgentSpec") -> str:
        """Build context section from spec context."""
        if not spec.context:
            return ""

        lines = ["## Additional Context"]
        lines.append("")
        lines.append("```json")
        # Pretty print JSON for readability
        lines.append(json.dumps(spec.context, indent=2, sort_keys=True))
        lines.append("```")

        return "\n".join(lines)

    def _build_acceptance_section(self, spec: "AgentSpec") -> str:
        """Build acceptance criteria section."""
        if not spec.acceptance_spec:
            return ""

        lines = ["## Acceptance Criteria"]
        lines.append("")

        acc = spec.acceptance_spec
        lines.append(f"**Gate Mode**: {acc.gate_mode}")
        if acc.min_score is not None:
            lines.append(f"**Minimum Score**: {acc.min_score}")
        lines.append(f"**Retry Policy**: {acc.retry_policy}")
        lines.append(f"**Max Retries**: {acc.max_retries}")
        lines.append("")

        validators = acc.validators or []
        if validators:
            lines.append("### Validators")
            lines.append("")
            for i, v in enumerate(validators, start=1):
                v_type = v.get("type", "unknown")
                v_config = v.get("config", {})
                v_weight = v.get("weight", 1.0)
                v_required = v.get("required", False)

                required_flag = " **(required)**" if v_required else ""
                lines.append(f"{i}. `{v_type}` (weight: {v_weight}){required_flag}")

                # Show config details
                if v_config:
                    for key, val in list(v_config.items())[:3]:
                        val_str = str(val)[:100]
                        lines.append(f"   - {key}: {val_str}")
            lines.append("")

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def _escape_yaml_string(self, value: str) -> str:
        """
        Escape a string for YAML frontmatter.

        Args:
            value: String to escape

        Returns:
            Properly escaped YAML string
        """
        # Use double quotes and escape internal quotes/newlines
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    def verify_exists(self, spec: "AgentSpec") -> bool:
        """
        Verify that an agent file exists for the given spec.

        Args:
            spec: The AgentSpec to check

        Returns:
            True if the agent file exists, False otherwise
        """
        filepath = self.output_path / f"{spec.name}.md"
        return filepath.exists()

    def verify_all(self, specs: list["AgentSpec"]) -> dict[str, bool]:
        """
        Verify that agent files exist for all given specs.

        Args:
            specs: List of AgentSpecs to verify

        Returns:
            Dictionary mapping spec_id to existence status
        """
        return {spec.id: self.verify_exists(spec) for spec in specs}

    def get_file_path(self, spec: "AgentSpec") -> Path:
        """
        Get the expected file path for an AgentSpec.

        Args:
            spec: The AgentSpec

        Returns:
            Expected file path
        """
        return self.output_path / f"{spec.name}.md"


# =============================================================================
# Module-level Functions
# =============================================================================

def render_agentspec_to_markdown(spec: "AgentSpec") -> str:
    """
    Render an AgentSpec to Claude Code-compatible markdown string.

    This is a convenience function that doesn't require instantiating
    a full AgentMaterializer.

    Args:
        spec: The AgentSpec to render

    Returns:
        Claude Code-compatible markdown string
    """
    # Use a temporary materializer just for rendering
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))
        return materializer.render_claude_code_markdown(spec)


def verify_determinism(spec: "AgentSpec", iterations: int = 3) -> bool:
    """
    Verify that materializer output is deterministic.

    Renders the same spec multiple times and verifies all outputs are identical.

    Args:
        spec: The AgentSpec to test
        iterations: Number of times to render (default 3)

    Returns:
        True if all renders produced identical output, False otherwise
    """
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        outputs = []
        for _ in range(iterations):
            output = materializer.render_claude_code_markdown(spec)
            outputs.append(output)

        # Check all outputs are identical
        return len(set(outputs)) == 1
