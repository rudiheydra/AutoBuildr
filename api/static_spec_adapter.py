"""
Static Spec Adapter Module
==========================

Wraps existing hard-coded agents (initializer, coding, testing) as static AgentSpecs
to enable kernel execution with legacy prompts.

This module provides backward compatibility by allowing the new HarnessKernel
to execute the existing agent types while preserving their original behavior.

The adapter:
- Loads prompts from the prompts/ directory
- Creates AgentSpec objects with appropriate tool policies
- Configures acceptance criteria for each agent type
- Maintains lineage to source features for traceability

Usage:
    ```python
    from api.static_spec_adapter import StaticSpecAdapter

    adapter = StaticSpecAdapter()

    # Create spec for initializer agent
    spec = adapter.create_initializer_spec(project_name="MyApp")

    # Create spec for coding agent
    spec = adapter.create_coding_spec(feature_id=42)

    # Create spec for testing agent
    spec = adapter.create_testing_spec(feature_id=42)
    ```
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from api.agentspec_models import (
    VALIDATOR_TYPES,
    AcceptanceSpec,
    AgentSpec,
    create_tool_policy,
    create_validator,
    generate_uuid,
)
from api.template_registry import (
    Template,
    TemplateRegistry,
    get_template_registry,
)

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Tool sets for different agent types
INITIALIZER_TOOLS = [
    # Feature management tools
    "feature_create",
    "feature_create_bulk",
    "feature_get_stats",
    "feature_get_by_id",
    "feature_add_dependency",
    "feature_set_dependencies",
    # File operations for project setup
    "Read",
    "Write",
    "Glob",
    "Grep",
    # Git initialization
    "Bash",
]

CODING_TOOLS = [
    # Feature management
    "feature_get_by_id",
    "feature_mark_in_progress",
    "feature_mark_passing",
    "feature_mark_failing",
    "feature_skip",
    "feature_clear_in_progress",
    "feature_get_stats",
    # Code editing
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    # Browser automation
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_console_messages",
    "browser_network_requests",
    # Execution
    "Bash",
    # Web research
    "WebFetch",
    "WebSearch",
]

TESTING_TOOLS = [
    # Feature management
    "feature_get_by_id",
    "feature_mark_passing",
    "feature_mark_failing",
    "feature_get_stats",
    # Read-only code access
    "Read",
    "Glob",
    "Grep",
    # Browser automation for testing
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_fill_form",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_console_messages",
    "browser_network_requests",
    "browser_evaluate",
    # Execution for running tests
    "Bash",
]

# Forbidden patterns for security
FORBIDDEN_PATTERNS = [
    r"rm\s+-rf\s+/",  # Dangerous recursive delete
    r"DROP\s+TABLE",  # SQL injection
    r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",  # Mass delete
    r"chmod\s+777",  # Overly permissive
    r">(>)?.*\/etc\/",  # Writing to system dirs
    r"curl.*\|\s*sh",  # Pipe to shell
    r"wget.*\|\s*sh",  # Pipe to shell
]

# Default budgets by agent type
DEFAULT_BUDGETS = {
    "initializer": {
        "max_turns": 100,  # Initialization can be lengthy
        "timeout_seconds": 3600,  # 1 hour for complex specs
    },
    "coding": {
        "max_turns": 150,  # Feature implementation
        "timeout_seconds": 1800,  # 30 minutes
    },
    "testing": {
        "max_turns": 50,  # Testing is typically shorter
        "timeout_seconds": 900,  # 15 minutes
    },
}


# =============================================================================
# StaticSpecAdapter Class
# =============================================================================

class StaticSpecAdapter:
    """
    Adapter that wraps legacy hard-coded agents as static AgentSpecs.

    This enables backward compatibility with the new HarnessKernel while
    preserving the original behavior of initializer, coding, and testing agents.

    Attributes:
        prompts_dir: Path to the prompts directory
        registry: TemplateRegistry instance for loading templates
    """

    def __init__(
        self,
        prompts_dir: str | Path | None = None,
        registry: TemplateRegistry | None = None,
    ):
        """
        Initialize the adapter.

        Args:
            prompts_dir: Path to prompts directory. Defaults to ./prompts
            registry: Optional TemplateRegistry instance. If not provided,
                     creates one using the prompts_dir.
        """
        if prompts_dir is None:
            # Default to prompts/ in project root
            prompts_dir = Path(__file__).parent.parent / "prompts"

        self._prompts_dir = Path(prompts_dir).resolve()

        if registry is not None:
            self._registry = registry
        else:
            self._registry = TemplateRegistry(
                self._prompts_dir,
                auto_scan=True,
                cache_enabled=True,
            )

    @property
    def prompts_dir(self) -> Path:
        """Get the prompts directory path."""
        return self._prompts_dir

    @property
    def registry(self) -> TemplateRegistry:
        """Get the template registry."""
        return self._registry

    def _load_prompt(self, name: str) -> Template:
        """
        Load a prompt template by name.

        Args:
            name: Template name (e.g., "initializer", "coding", "testing")

        Returns:
            Loaded Template object

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        # Try exact name first, then with _prompt suffix
        template = self._registry.get_template(name=name, use_fallback=False)

        if template is None:
            # Try with _prompt suffix
            template = self._registry.get_template(name=f"{name}_prompt", use_fallback=False)

        if template is None:
            # Try direct file path
            for suffix in ["", "_prompt"]:
                path = self._prompts_dir / f"{name}{suffix}.md"
                if path.exists():
                    return self._registry.get_template_by_path(path)

            raise FileNotFoundError(
                f"Template not found: {name} (searched in {self._prompts_dir})"
            )

        return template

    def create_initializer_spec(
        self,
        project_name: str | None = None,
        feature_count: int = 85,
        *,
        spec_id: str | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> AgentSpec:
        """
        Create an AgentSpec for the initializer agent.

        The initializer agent:
        - Reads app_spec.txt to understand project requirements
        - Creates features in the database using feature_create_bulk
        - Sets up init.sh for environment initialization
        - Creates initial project structure

        Args:
            project_name: Optional project name for display
            feature_count: Expected number of features to create (for validation)
            spec_id: Optional spec ID (generates UUID if not provided)
            extra_context: Additional context to include

        Returns:
            AgentSpec configured for initializer execution
        """
        # Load the initializer prompt template
        template = self._load_prompt("initializer")

        # Build objective from template
        objective = template.content

        # Interpolate any variables
        variables = {
            "project_name": project_name or "AutoBuildr",
            "feature_count": feature_count,
        }

        if extra_context:
            variables.update(extra_context)

        objective = self._registry.interpolate(template, variables)

        # Create tool policy
        tool_policy = create_tool_policy(
            allowed_tools=INITIALIZER_TOOLS,
            forbidden_patterns=FORBIDDEN_PATTERNS,
            tool_hints={
                "feature_create_bulk": (
                    "Use this to create all features at once. "
                    "Features must match the spec's feature_count."
                ),
                "feature_get_stats": (
                    "Call after creating features to verify the correct count was created."
                ),
                "Bash": (
                    "Use for git operations and creating init.sh. "
                    "Avoid destructive commands."
                ),
            },
        )

        # Create context
        context = {
            "agent_type": "initializer",
            "project_name": project_name or "AutoBuildr",
            "expected_feature_count": feature_count,
            "prompts_dir": str(self._prompts_dir),
        }

        if extra_context:
            context.update(extra_context)

        # Get budget from defaults
        budget = DEFAULT_BUDGETS["initializer"]

        # Create the AgentSpec
        spec = AgentSpec(
            id=spec_id or generate_uuid(),
            name=f"initializer-{project_name or 'default'}".lower().replace(" ", "-"),
            display_name=f"Initializer Agent ({project_name or 'Project Setup'})",
            icon="rocket",
            spec_version="v1",
            objective=objective,
            task_type="custom",  # Initializer is a custom task type
            context=context,
            tool_policy=tool_policy,
            max_turns=budget["max_turns"],
            timeout_seconds=budget["timeout_seconds"],
            tags=["initializer", "setup", "legacy"],
        )

        # Create acceptance spec with feature_count validator
        acceptance = self._create_initializer_acceptance_spec(
            spec.id,
            feature_count=feature_count,
        )

        # Link acceptance spec to agent spec
        spec.acceptance_spec = acceptance

        _logger.info(
            "Created initializer spec: %s (expecting %d features)",
            spec.name,
            feature_count,
        )

        return spec

    def _create_initializer_acceptance_spec(
        self,
        agent_spec_id: str,
        feature_count: int,
    ) -> AcceptanceSpec:
        """
        Create an AcceptanceSpec for the initializer agent.

        Validators:
        - feature_count: Verify correct number of features created
        - file_exists: Verify init.sh was created

        Args:
            agent_spec_id: ID of the parent AgentSpec
            feature_count: Expected number of features

        Returns:
            AcceptanceSpec with appropriate validators
        """
        validators = [
            # Custom validator for feature count
            create_validator(
                validator_type="custom",
                config={
                    "name": "feature_count",
                    "description": f"Verify {feature_count} features were created",
                    "check_type": "feature_count",
                    "expected_count": feature_count,
                    "tolerance": 0,  # Exact match required
                },
                weight=1.0,
                required=True,  # Must pass
            ),
            # Verify init.sh was created
            create_validator(
                validator_type="file_exists",
                config={
                    "path": "init.sh",
                    "description": "Environment initialization script must exist",
                },
                weight=0.5,
                required=False,  # Nice to have
            ),
        ]

        return AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=agent_spec_id,
            validators=validators,
            gate_mode="all_pass",  # All required validators must pass
            retry_policy="none",
            max_retries=0,
        )

    def create_coding_spec(
        self,
        feature_id: int,
        feature_name: str | None = None,
        feature_description: str | None = None,
        *,
        spec_id: str | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> AgentSpec:
        """
        Create an AgentSpec for the coding agent.

        The coding agent:
        - Implements features based on their descriptions
        - Writes code, tests, and documentation
        - Verifies implementation using browser automation
        - Marks features as passing after verification

        Args:
            feature_id: ID of the feature to implement
            feature_name: Optional human-readable feature name
            feature_description: Optional feature description
            spec_id: Optional spec ID
            extra_context: Additional context to include

        Returns:
            AgentSpec configured for coding execution
        """
        # Load the coding prompt template
        template = self._load_prompt("coding")

        # Build objective
        objective = template.content

        # Interpolate variables
        variables = {
            "feature_id": feature_id,
            "feature_name": feature_name or f"Feature #{feature_id}",
        }

        if extra_context:
            variables.update(extra_context)

        objective = self._registry.interpolate(template, variables)

        # Create tool policy
        # Note: Bash commands are validated by security.py ALLOWED_COMMANDS allowlist
        # which permits only development-related commands (ls, cat, npm, git, etc.)
        # Forbidden patterns below catch dangerous operations the allowlist might miss
        tool_policy = create_tool_policy(
            allowed_tools=CODING_TOOLS,
            forbidden_patterns=FORBIDDEN_PATTERNS,
            tool_hints={
                "feature_mark_passing": (
                    "ONLY call after thorough verification with browser automation. "
                    "Take screenshots to prove the feature works."
                ),
                "browser_snapshot": (
                    "Use this to capture page state for verification. "
                    "Better than screenshots for automation."
                ),
                "Edit": (
                    "Prefer editing existing files over creating new ones. "
                    "Always read files before editing."
                ),
                "Bash": (
                    "Bash commands are restricted by security allowlist (security.py). "
                    "Only development commands like npm, git, pytest are permitted. "
                    "Dangerous commands (sudo, rm -rf /, etc.) are blocked."
                ),
            },
        )

        # Create context
        context = {
            "agent_type": "coding",
            "feature_id": feature_id,
            "feature_name": feature_name,
            "feature_description": feature_description,
        }

        if extra_context:
            context.update(extra_context)

        # Get budget
        budget = DEFAULT_BUDGETS["coding"]

        # Create the AgentSpec
        spec = AgentSpec(
            id=spec_id or generate_uuid(),
            name=f"coding-feature-{feature_id}",
            display_name=f"Coding: {feature_name or f'Feature #{feature_id}'}",
            icon="code",
            spec_version="v1",
            objective=objective,
            task_type="coding",
            context=context,
            tool_policy=tool_policy,
            max_turns=budget["max_turns"],
            timeout_seconds=budget["timeout_seconds"],
            source_feature_id=feature_id,  # Link to source feature
            tags=["coding", "implementation", "legacy"],
        )

        # Create acceptance spec
        acceptance = self._create_coding_acceptance_spec(
            spec.id,
            feature_id=feature_id,
        )

        spec.acceptance_spec = acceptance

        _logger.info(
            "Created coding spec: %s for feature %d",
            spec.name,
            feature_id,
        )

        return spec

    def _create_coding_acceptance_spec(
        self,
        agent_spec_id: str,
        feature_id: int,
    ) -> AcceptanceSpec:
        """
        Create an AcceptanceSpec for the coding agent.

        Validators:
        - test_pass: Run tests to verify implementation works
        - lint_clean: Run linter to ensure code quality
        - feature_passing: Verify the feature was marked as passing
        - no_console_errors: Verify no JavaScript console errors

        Args:
            agent_spec_id: ID of the parent AgentSpec
            feature_id: ID of the feature being implemented

        Returns:
            AcceptanceSpec with appropriate validators
        """
        validators = [
            # Run test command to verify implementation
            create_validator(
                validator_type="test_pass",
                config={
                    "command": "pytest tests/ -v --tb=short || npm test || echo 'No test runner found'",
                    "description": "Run automated tests to verify implementation",
                    "timeout_seconds": 300,  # 5 minute timeout for tests
                    "expected_exit_code": 0,
                },
                weight=1.0,
                required=False,  # Not required - project may not have tests yet
            ),
            # Run linter to check code quality
            create_validator(
                validator_type="lint_clean",
                config={
                    "command": "npm run lint 2>/dev/null || ruff check . 2>/dev/null || echo 'No linter configured'",
                    "description": "Run linter to ensure code quality",
                    "timeout_seconds": 120,  # 2 minute timeout for linting
                },
                weight=0.5,
                required=False,  # Not required - project may not have linting set up
            ),
            # Feature must be marked as passing
            create_validator(
                validator_type="custom",
                config={
                    "name": "feature_passing",
                    "description": "Feature must be marked as passing",
                    "check_type": "feature_status",
                    "feature_id": feature_id,
                    "expected_status": "passing",
                },
                weight=1.0,
                required=True,  # This is the core requirement
            ),
            # No console errors during verification
            create_validator(
                validator_type="forbidden_patterns",
                config={
                    "patterns": [
                        r"ERROR",
                        r"Uncaught.*Error",
                        r"TypeError",
                        r"ReferenceError",
                    ],
                    "context": "browser_console",
                    "description": "No JavaScript errors in console",
                },
                weight=0.5,
                required=False,
            ),
        ]

        return AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=agent_spec_id,
            validators=validators,
            gate_mode="all_pass",
            retry_policy="fixed",
            max_retries=2,  # Allow retries for transient failures
        )

    def create_testing_spec(
        self,
        feature_id: int,
        feature_name: str | None = None,
        feature_steps: list[str] | None = None,
        *,
        spec_id: str | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> AgentSpec:
        """
        Create an AgentSpec for the testing agent.

        The testing agent:
        - Verifies that implemented features work correctly
        - Uses browser automation to test UI interactions
        - Reports regression failures
        - Updates feature status based on test results

        Args:
            feature_id: ID of the feature to test
            feature_name: Optional human-readable feature name
            feature_steps: Optional list of verification steps from feature definition
            spec_id: Optional spec ID
            extra_context: Additional context

        Returns:
            AgentSpec configured for testing execution
        """
        # Load the testing prompt template
        template = self._load_prompt("testing")

        objective = template.content

        # Format feature steps as test criteria if provided
        steps_text = ""
        if feature_steps:
            steps_list = "\n".join(f"- {step}" for step in feature_steps)
            steps_text = f"\n\n## Test Criteria\n\nVerify the following steps:\n{steps_list}"

        # Interpolate variables
        variables = {
            "feature_id": feature_id,
            "feature_name": feature_name or f"Feature #{feature_id}",
            "feature_steps": steps_text,
            "test_criteria": steps_text,  # Alias for template flexibility
        }

        if extra_context:
            variables.update(extra_context)

        objective = self._registry.interpolate(template, variables)

        # Append test criteria to objective if not already interpolated
        if feature_steps and steps_text not in objective:
            objective += steps_text

        # Create tool policy (more restrictive than coding)
        tool_policy = create_tool_policy(
            allowed_tools=TESTING_TOOLS,
            forbidden_patterns=FORBIDDEN_PATTERNS,
            tool_hints={
                "feature_mark_failing": (
                    "Use this to report regressions found during testing."
                ),
                "browser_snapshot": (
                    "Capture page state before and after interactions to verify behavior."
                ),
                "Bash": (
                    "Use for running test commands only. Do not modify code."
                ),
            },
        )

        # Create context
        context = {
            "agent_type": "testing",
            "feature_id": feature_id,
            "feature_name": feature_name,
            "feature_steps": feature_steps or [],
            "test_mode": True,
        }

        if extra_context:
            context.update(extra_context)

        # Get budget
        budget = DEFAULT_BUDGETS["testing"]

        # Create the AgentSpec
        spec = AgentSpec(
            id=spec_id or generate_uuid(),
            name=f"testing-feature-{feature_id}",
            display_name=f"Testing: {feature_name or f'Feature #{feature_id}'}",
            icon="test-tube",
            spec_version="v1",
            objective=objective,
            task_type="testing",
            context=context,
            tool_policy=tool_policy,
            max_turns=budget["max_turns"],
            timeout_seconds=budget["timeout_seconds"],
            source_feature_id=feature_id,
            tags=["testing", "verification", "legacy"],
        )

        # Create acceptance spec with feature steps
        acceptance = self._create_testing_acceptance_spec(
            spec.id, feature_id, feature_steps
        )
        spec.acceptance_spec = acceptance

        _logger.info(
            "Created testing spec: %s for feature %d",
            spec.name,
            feature_id,
        )

        return spec

    def _create_testing_acceptance_spec(
        self,
        agent_spec_id: str,
        feature_id: int,
        feature_steps: list[str] | None = None,
    ) -> AcceptanceSpec:
        """
        Create an AcceptanceSpec for the testing agent.

        Generates test_pass validators from feature steps to ensure each
        verification step is properly tested.

        Args:
            agent_spec_id: ID of the parent AgentSpec
            feature_id: ID of the feature being tested
            feature_steps: Optional list of verification steps to convert to validators

        Returns:
            AcceptanceSpec with test-specific validators
        """
        validators = [
            # Tests must complete (either passing or failing is valid)
            create_validator(
                validator_type="custom",
                config={
                    "name": "test_complete",
                    "description": "Testing must complete with a result",
                    "check_type": "test_completion",
                    "feature_id": feature_id,
                },
                weight=1.0,
                required=True,
            ),
        ]

        # Generate test_pass validators from feature steps
        if feature_steps:
            for i, step in enumerate(feature_steps, start=1):
                # Create a test_pass validator for each feature step
                validators.append(
                    create_validator(
                        validator_type="test_pass",
                        config={
                            "name": f"step_{i}",
                            "description": step,
                            "step_number": i,
                            "feature_id": feature_id,
                            # Test command can be customized per step if needed
                            "command": None,  # No automatic command - manual verification
                            "expected_exit_code": 0,
                        },
                        weight=1.0 / max(len(feature_steps), 1),  # Equal weight per step
                        required=False,  # Individual steps are not required
                    )
                )

        return AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=agent_spec_id,
            validators=validators,
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )


# =============================================================================
# Module-level Convenience Functions
# =============================================================================

_default_adapter: StaticSpecAdapter | None = None


def get_static_spec_adapter(prompts_dir: str | Path | None = None) -> StaticSpecAdapter:
    """
    Get or create the default StaticSpecAdapter.

    Args:
        prompts_dir: Path to prompts directory (only used on first call)

    Returns:
        The default StaticSpecAdapter instance
    """
    global _default_adapter

    if _default_adapter is None:
        _default_adapter = StaticSpecAdapter(prompts_dir)

    return _default_adapter


def reset_static_spec_adapter() -> None:
    """Reset the default adapter (for testing)."""
    global _default_adapter
    _default_adapter = None
