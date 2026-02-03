"""
Octo Service - Agent Generator
==============================

Octo is a DSPy-based service that generates AgentSpecs from structured request payloads.
It receives OctoRequestPayload from Maestro and returns one or more validated AgentSpecs.

Feature #176: Maestro delegates to Octo for agent generation
Feature #182: Octo DSPy signature for AgentSpec generation
Feature #183: Octo processes OctoRequestPayload and returns AgentSpecs
Feature #184: Octo generates TestContract alongside AgentSpec when applicable
Feature #185: Octo DSPy module with constraint satisfaction
Feature #187: Octo selects appropriate model for each agent
Feature #188: Octo outputs are strictly typed and schema-validated

This module provides:
- OctoRequestPayload: Structured input containing project context, required capabilities, and constraints
- OctoResponse: Response containing generated AgentSpecs and any errors
- TestContract: Structured test specification for testable agents
- Octo: Service class that invokes DSPy pipeline to generate AgentSpecs
- Model selection: Automatic selection of Claude model based on agent complexity
- Constraint validation: Ensures specs meet tool, model, and sandbox constraints (Feature #185)

Usage:
    from api.octo import Octo, OctoRequestPayload

    # Create Octo service
    octo = Octo(api_key="sk-...")

    # Build request payload with constraints
    payload = OctoRequestPayload(
        project_context={"name": "MyApp", "tech_stack": ["React", "Python"]},
        required_capabilities=["ui_testing", "api_testing"],
        existing_agents=["coder", "test-runner"],
        constraints={
            "max_agents": 3,
            "max_turns_limit": 100,  # Budget constraint
            "model": "sonnet",       # Model constraint
        }
    )

    # Generate AgentSpecs (constraint validation happens automatically)
    response = octo.generate_specs(payload)
    if response.success:
        for spec in response.agent_specs:
            print(f"Generated: {spec.name}")
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from api.agentspec_models import (
    AcceptanceSpec,
    AgentSpec,
    TASK_TYPES,
    generate_uuid,
)
from api.spec_builder import (
    SpecBuilder,
    BuildResult,
    get_spec_builder,
)
from api.spec_validator import (
    validate_spec,
    SpecValidationResult,
)
from api.display_derivation import derive_display_name, derive_icon
from api.octo_schemas import (
    # Exceptions
    OctoSchemaValidationError,
    SchemaValidationError,
    SchemaValidationResult,
    # Validation functions
    validate_agent_spec_schema,
    validate_test_contract_schema,
    validate_octo_outputs,
    # Constants
    AGENT_SPEC_SCHEMA,
    TEST_CONTRACT_SCHEMA,
    VALID_TASK_TYPES as SCHEMA_VALID_TASK_TYPES,
    VALID_TEST_TYPES as SCHEMA_VALID_TEST_TYPES,
)
from api.tool_policy import TOOL_SETS, derive_tool_policy
from api.constraints import (
    ConstraintValidator,
    ConstraintValidationResult,
    ConstraintViolation,
    ToolAvailabilityConstraint,
    ModelLimitConstraint,
    SandboxConstraint,
    ForbiddenPatternConstraint,
    create_constraints_from_payload,
    create_default_constraints,
)

_logger = logging.getLogger(__name__)


# =============================================================================
# Model Selection Constants (Feature #187)
# =============================================================================

# Valid Claude models for agent execution
VALID_MODELS = frozenset(["sonnet", "opus", "haiku"])

# Default model when no specific selection criteria matches
DEFAULT_MODEL = "sonnet"

# Capabilities that should use haiku (simple/fast tasks)
HAIKU_CAPABILITIES = frozenset({
    "documentation",
    "doc_generation",
    "readme",
    "wiki",
    "changelog",
    "lint",
    "format",
    "simple_audit",
    "smoke_testing",
    "health_check",
    "ping",
    "status",
    "logging",
    "metrics_collection",
    "notification",
    "alerting",
})

# Capabilities that should use opus (complex reasoning tasks)
OPUS_CAPABILITIES = frozenset({
    "architecture_design",
    "system_design",
    "complex_refactoring",
    "security_audit",
    "vulnerability_analysis",
    "performance_optimization",
    "algorithm_design",
    "data_modeling",
    "schema_design",
    "complex_debugging",
    "root_cause_analysis",
    "code_migration",
    "framework_migration",
    "multi_service_integration",
    "distributed_systems",
    "concurrency_design",
    "complex_testing",
    "test_strategy",
    "ml_pipeline",
    "data_pipeline",
})

# Task types that default to specific models
TASK_TYPE_MODEL_DEFAULTS: dict[str, str] = {
    "coding": "sonnet",
    "testing": "sonnet",
    "refactoring": "sonnet",
    "documentation": "haiku",
    "audit": "opus",
    "custom": "sonnet",
}

# Keywords in capability names that indicate complexity
COMPLEXITY_INDICATORS = {
    "complex": "opus",
    "simple": "haiku",
    "advanced": "opus",
    "basic": "haiku",
    "deep": "opus",
    "quick": "haiku",
    "comprehensive": "opus",
    "minimal": "haiku",
    "thorough": "opus",
    "fast": "haiku",
    "multi": "opus",
    "distributed": "opus",
    "concurrent": "opus",
}


# =============================================================================
# Request/Response Schemas
# =============================================================================

@dataclass
class OctoRequestPayload:
    """
    Structured request payload for Octo agent generation.

    Contains all context Octo needs to generate appropriate AgentSpecs:
    - project_context: Discovery artifacts, tech stack, app spec summary
    - required_capabilities: List of capabilities needed (e.g., "e2e_testing", "api_testing")
    - existing_agents: Names of agents already available (to avoid duplication)
    - constraints: Limits like max_agents, model restrictions, tool restrictions

    Feature #175: Maestro produces structured Octo request payload
    """
    project_context: dict[str, Any]
    required_capabilities: list[str]
    existing_agents: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    # Optional metadata for traceability
    source_feature_ids: list[int] = field(default_factory=list)
    request_id: str = field(default_factory=generate_uuid)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_context": self.project_context,
            "required_capabilities": self.required_capabilities,
            "existing_agents": self.existing_agents,
            "constraints": self.constraints,
            "source_feature_ids": self.source_feature_ids,
            "request_id": self.request_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OctoRequestPayload":
        """Create from dictionary."""
        return cls(
            project_context=data.get("project_context", {}),
            required_capabilities=data.get("required_capabilities", []),
            existing_agents=data.get("existing_agents", []),
            constraints=data.get("constraints", {}),
            source_feature_ids=data.get("source_feature_ids", []),
            request_id=data.get("request_id", generate_uuid()),
        )

    def validate(self) -> list[str]:
        """
        Validate the payload structure.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # project_context is required and must be dict
        if not isinstance(self.project_context, dict):
            errors.append("project_context must be a dictionary")

        # required_capabilities must be non-empty list
        if not isinstance(self.required_capabilities, list):
            errors.append("required_capabilities must be a list")
        elif len(self.required_capabilities) == 0:
            errors.append("required_capabilities cannot be empty")
        else:
            for i, cap in enumerate(self.required_capabilities):
                if not isinstance(cap, str) or not cap.strip():
                    errors.append(f"required_capabilities[{i}] must be a non-empty string")

        # existing_agents must be list of strings
        if not isinstance(self.existing_agents, list):
            errors.append("existing_agents must be a list")
        else:
            for i, agent in enumerate(self.existing_agents):
                if not isinstance(agent, str):
                    errors.append(f"existing_agents[{i}] must be a string")

        # constraints must be dict
        if not isinstance(self.constraints, dict):
            errors.append("constraints must be a dictionary")

        return errors


@dataclass
class OctoResponse:
    """
    Response from Octo containing generated AgentSpecs and TestContracts.

    Feature #184: Octo generates TestContract alongside AgentSpec when applicable
    Feature #185: Octo DSPy module with constraint satisfaction
    Feature #188: Octo outputs are strictly typed and schema-validated
    """
    success: bool
    agent_specs: list[AgentSpec] = field(default_factory=list)
    test_contracts: list["TestContract"] = field(default_factory=list)  # Feature #184
    constraint_violations: list[ConstraintViolation] = field(default_factory=list)  # Feature #185
    error: str | None = None
    error_type: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "agent_specs": [spec.to_dict() for spec in self.agent_specs],
            "test_contracts": [tc.to_dict() for tc in self.test_contracts],
            "constraint_violations": [cv.to_dict() for cv in self.constraint_violations],
            "error": self.error,
            "error_type": self.error_type,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "request_id": self.request_id,
        }


# =============================================================================
# TestContract - Structured Test Specification (Feature #184)
# =============================================================================

# Test types supported by TestContract
TEST_TYPES = [
    "unit",           # Unit tests for isolated components
    "integration",    # Integration tests for component interactions
    "e2e",            # End-to-end UI tests
    "api",            # API endpoint tests
    "performance",    # Performance and load tests
    "security",       # Security scanning/audit tests
    "smoke",          # Quick sanity check tests
    "regression",     # Regression tests for existing functionality
]


@dataclass
class TestContractAssertion:
    """
    A single assertion within a TestContract.

    Assertions describe what conditions must hold true for a test to pass.
    They are structured data, not executable code.

    Attributes:
        description: Human-readable description of what is being asserted
        target: What is being tested (e.g., "response.status_code", "page.title")
        expected: Expected value or condition
        operator: Comparison operator (eq, ne, gt, lt, ge, le, contains, matches)
    """
    description: str
    target: str
    expected: Any
    operator: str = "eq"  # eq, ne, gt, lt, ge, le, contains, matches, exists

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "target": self.target,
            "expected": self.expected,
            "operator": self.operator,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestContractAssertion":
        """Create from dictionary."""
        return cls(
            description=data.get("description", ""),
            target=data.get("target", ""),
            expected=data.get("expected"),
            operator=data.get("operator", "eq"),
        )


@dataclass
class TestContract:
    """
    Structured test specification for testable agent responsibilities.

    Feature #184: Octo generates TestContract alongside AgentSpec when applicable.

    TestContract specifies WHAT should be tested, not HOW to test it.
    It is structured data (not test code) that can be used by:
    - Test generation tools to create actual test code
    - Acceptance validators to verify agent output
    - Documentation to describe expected behavior

    Attributes:
        agent_name: Name of the agent this contract is linked to (matches AgentSpec.name)
        test_type: Type of testing (unit, integration, e2e, api, performance, security)
        assertions: List of assertions that must hold true
        pass_criteria: Conditions that determine test success
        fail_criteria: Conditions that indicate test failure
        description: Human-readable description of what is being tested
        priority: Priority level (1=critical, 2=high, 3=medium, 4=low)
        tags: Optional tags for categorization
    """
    agent_name: str
    test_type: str
    assertions: list[TestContractAssertion] = field(default_factory=list)
    pass_criteria: list[str] = field(default_factory=list)
    fail_criteria: list[str] = field(default_factory=list)
    description: str = ""
    priority: int = 3  # 1=critical, 2=high, 3=medium, 4=low
    tags: list[str] = field(default_factory=list)
    contract_id: str = field(default_factory=generate_uuid)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "contract_id": self.contract_id,
            "agent_name": self.agent_name,
            "test_type": self.test_type,
            "assertions": [a.to_dict() for a in self.assertions],
            "pass_criteria": self.pass_criteria,
            "fail_criteria": self.fail_criteria,
            "description": self.description,
            "priority": self.priority,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestContract":
        """Create from dictionary."""
        assertions = [
            TestContractAssertion.from_dict(a)
            for a in data.get("assertions", [])
        ]
        return cls(
            agent_name=data.get("agent_name", ""),
            test_type=data.get("test_type", "unit"),
            assertions=assertions,
            pass_criteria=data.get("pass_criteria", []),
            fail_criteria=data.get("fail_criteria", []),
            description=data.get("description", ""),
            priority=data.get("priority", 3),
            tags=data.get("tags", []),
            contract_id=data.get("contract_id", generate_uuid()),
        )

    def validate(self) -> list[str]:
        """
        Validate the TestContract structure.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        if not self.agent_name or not self.agent_name.strip():
            errors.append("agent_name is required")

        if not self.test_type:
            errors.append("test_type is required")
        elif self.test_type not in TEST_TYPES:
            errors.append(f"test_type must be one of: {', '.join(TEST_TYPES)}")

        if not self.assertions and not self.pass_criteria:
            errors.append("TestContract must have either assertions or pass_criteria")

        if self.priority not in (1, 2, 3, 4):
            errors.append("priority must be 1 (critical), 2 (high), 3 (medium), or 4 (low)")

        return errors


# =============================================================================
# Testability Evaluation (Feature #184)
# =============================================================================

# Capabilities that are inherently testable
TESTABLE_CAPABILITIES = frozenset({
    # Testing-related capabilities
    "e2e_testing",
    "api_testing",
    "ui_testing",
    "unit_testing",
    "integration_testing",
    "performance_testing",
    "security_testing",
    "load_testing",
    "smoke_testing",
    "regression_testing",
    # Coding capabilities with testable output
    "coding",
    "refactoring",
    "bug_fixing",
    "feature_implementation",
    # API-related capabilities
    "api_implementation",
    "api_design",
    "rest_api",
    "graphql",
    # Frontend capabilities
    "frontend",
    "ui_development",
    "component_development",
    # Backend capabilities
    "backend",
    "database",
    "data_processing",
})

# Task types that are testable
TESTABLE_TASK_TYPES = frozenset({
    "coding",
    "testing",
    "refactoring",
})

# Keywords in objectives that indicate testability
TESTABLE_OBJECTIVE_KEYWORDS = [
    "implement",
    "create",
    "build",
    "develop",
    "test",
    "verify",
    "validate",
    "check",
    "ensure",
    "api",
    "endpoint",
    "function",
    "component",
    "feature",
    "fix",
    "bug",
    "refactor",
]


def is_capability_testable(capability: str) -> bool:
    """
    Check if a capability is inherently testable.

    Args:
        capability: The capability name to check

    Returns:
        True if the capability has testable responsibilities
    """
    capability_lower = capability.lower().replace("-", "_").replace(" ", "_")
    return capability_lower in TESTABLE_CAPABILITIES


def is_task_type_testable(task_type: str) -> bool:
    """
    Check if a task type typically produces testable output.

    Args:
        task_type: The task type to check

    Returns:
        True if the task type is testable
    """
    return task_type in TESTABLE_TASK_TYPES


def is_objective_testable(objective: str) -> bool:
    """
    Analyze an objective string to determine if it describes testable work.

    Args:
        objective: The agent's objective description

    Returns:
        True if the objective describes testable responsibilities
    """
    if not objective:
        return False

    objective_lower = objective.lower()

    # Check for testability keywords
    return any(keyword in objective_lower for keyword in TESTABLE_OBJECTIVE_KEYWORDS)


def evaluate_agent_testability(
    capability: str,
    task_type: str,
    objective: str,
) -> tuple[bool, str]:
    """
    Evaluate whether an agent has testable responsibilities.

    Feature #184: Octo evaluates if agent responsibilities are testable.

    Combines multiple signals to determine testability:
    1. Capability name (e.g., "e2e_testing" is testable)
    2. Task type (e.g., "coding" produces testable output)
    3. Objective keywords (e.g., "implement API endpoint" is testable)

    Args:
        capability: The agent's capability
        task_type: The agent's task type
        objective: The agent's objective description

    Returns:
        Tuple of (is_testable, reason_string)
    """
    reasons = []

    # Check capability
    if is_capability_testable(capability):
        reasons.append(f"capability '{capability}' is testable")

    # Check task type
    if is_task_type_testable(task_type):
        reasons.append(f"task_type '{task_type}' produces testable output")

    # Check objective
    if is_objective_testable(objective):
        reasons.append("objective describes testable work")

    if reasons:
        return True, "; ".join(reasons)
    else:
        return False, "no testable responsibilities identified"


def generate_test_contract(
    agent_spec: AgentSpec,
    capability: str,
    project_context: dict[str, Any] | None = None,
) -> TestContract | None:
    """
    Generate a TestContract for an AgentSpec if it has testable responsibilities.

    Feature #184: For testable agents, Octo generates TestContract structure.

    Args:
        agent_spec: The AgentSpec to generate a contract for
        capability: The capability this agent was created for
        project_context: Optional project context for richer contracts

    Returns:
        TestContract if the agent is testable, None otherwise
    """
    # Step 1: Evaluate testability
    is_testable, reason = evaluate_agent_testability(
        capability=capability,
        task_type=agent_spec.task_type,
        objective=agent_spec.objective,
    )

    if not is_testable:
        _logger.debug(
            "Agent %s is not testable: %s",
            agent_spec.name,
            reason,
        )
        return None

    _logger.info(
        "Generating TestContract for agent %s: %s",
        agent_spec.name,
        reason,
    )

    # Step 2: Determine test type based on capability/task
    test_type = _infer_test_type(capability, agent_spec.task_type)

    # Step 3: Generate assertions based on capability
    assertions = _generate_assertions(capability, agent_spec, project_context)

    # Step 4: Generate pass/fail criteria
    pass_criteria, fail_criteria = _generate_criteria(capability, agent_spec)

    # Step 5: Build the TestContract
    contract = TestContract(
        agent_name=agent_spec.name,
        test_type=test_type,
        assertions=assertions,
        pass_criteria=pass_criteria,
        fail_criteria=fail_criteria,
        description=f"Test contract for {agent_spec.display_name}: verifies {capability} responsibilities",
        priority=_infer_priority(capability, agent_spec.task_type),
        tags=_generate_tags(capability, agent_spec),
    )

    return contract


def _infer_test_type(capability: str, task_type: str) -> str:
    """Infer the appropriate test type from capability and task type."""
    capability_lower = capability.lower()

    # Explicit testing capabilities
    if "e2e" in capability_lower or "ui" in capability_lower:
        return "e2e"
    if "api" in capability_lower:
        return "api"
    if "unit" in capability_lower:
        return "unit"
    if "integration" in capability_lower:
        return "integration"
    if "performance" in capability_lower or "load" in capability_lower:
        return "performance"
    if "security" in capability_lower:
        return "security"
    if "smoke" in capability_lower:
        return "smoke"
    if "regression" in capability_lower:
        return "regression"

    # Infer from task type
    if task_type == "testing":
        return "integration"
    if task_type == "coding":
        return "unit"
    if task_type == "refactoring":
        return "regression"

    return "unit"  # Default


def _generate_assertions(
    capability: str,
    agent_spec: AgentSpec,
    project_context: dict[str, Any] | None,
) -> list[TestContractAssertion]:
    """Generate assertions based on capability and context."""
    assertions = []
    capability_lower = capability.lower()

    # API-related assertions
    if "api" in capability_lower:
        assertions.extend([
            TestContractAssertion(
                description="API endpoints return successful status codes",
                target="response.status_code",
                expected=200,
                operator="eq",
            ),
            TestContractAssertion(
                description="API responses are valid JSON",
                target="response.content_type",
                expected="application/json",
                operator="contains",
            ),
        ])

    # E2E/UI assertions
    if "e2e" in capability_lower or "ui" in capability_lower:
        assertions.extend([
            TestContractAssertion(
                description="Page loads successfully",
                target="page.status",
                expected="loaded",
                operator="eq",
            ),
            TestContractAssertion(
                description="No JavaScript errors in console",
                target="console.errors.count",
                expected=0,
                operator="eq",
            ),
        ])

    # Coding/implementation assertions
    if capability_lower in ("coding", "refactoring", "feature_implementation"):
        assertions.extend([
            TestContractAssertion(
                description="Code compiles/builds without errors",
                target="build.status",
                expected="success",
                operator="eq",
            ),
            TestContractAssertion(
                description="Linting passes",
                target="lint.errors.count",
                expected=0,
                operator="eq",
            ),
        ])

    # Security assertions
    if "security" in capability_lower:
        assertions.extend([
            TestContractAssertion(
                description="No critical vulnerabilities found",
                target="vulnerabilities.critical.count",
                expected=0,
                operator="eq",
            ),
            TestContractAssertion(
                description="No high severity vulnerabilities found",
                target="vulnerabilities.high.count",
                expected=0,
                operator="eq",
            ),
        ])

    # Default assertion if none generated
    if not assertions:
        assertions.append(
            TestContractAssertion(
                description=f"Agent {agent_spec.name} completes successfully",
                target="agent.status",
                expected="completed",
                operator="eq",
            )
        )

    return assertions


def _generate_criteria(
    capability: str,
    agent_spec: AgentSpec,
) -> tuple[list[str], list[str]]:
    """Generate pass and fail criteria based on capability."""
    capability_lower = capability.lower()

    pass_criteria = []
    fail_criteria = []

    # Common pass criteria
    pass_criteria.append("Agent completes without errors")
    pass_criteria.append("All required outputs are generated")

    # Capability-specific pass criteria
    if "test" in capability_lower:
        pass_criteria.append("All tests pass")
        pass_criteria.append("Test coverage meets minimum threshold")
        fail_criteria.append("Any test fails")

    if "api" in capability_lower:
        pass_criteria.append("All API endpoints respond correctly")
        pass_criteria.append("Response times are within acceptable limits")
        fail_criteria.append("Any endpoint returns 5xx error")

    if "e2e" in capability_lower or "ui" in capability_lower:
        pass_criteria.append("All user flows complete successfully")
        pass_criteria.append("No visual regressions detected")
        fail_criteria.append("Any critical user flow fails")

    if "security" in capability_lower:
        pass_criteria.append("No critical vulnerabilities found")
        pass_criteria.append("Security scan completes successfully")
        fail_criteria.append("Critical vulnerability detected")

    if capability_lower in ("coding", "refactoring"):
        pass_criteria.append("Code compiles successfully")
        pass_criteria.append("Linting passes")
        fail_criteria.append("Build fails")
        fail_criteria.append("Linting errors detected")

    # Common fail criteria
    fail_criteria.append("Agent times out")
    fail_criteria.append("Agent crashes or raises unhandled exception")

    return pass_criteria, fail_criteria


def _infer_priority(capability: str, task_type: str) -> int:
    """Infer priority level (1=critical to 4=low)."""
    capability_lower = capability.lower()

    # Critical priority
    if "security" in capability_lower:
        return 1
    if "auth" in capability_lower:
        return 1

    # High priority
    if "api" in capability_lower:
        return 2
    if "e2e" in capability_lower:
        return 2
    if task_type == "testing":
        return 2

    # Medium priority
    if task_type == "coding":
        return 3
    if "unit" in capability_lower:
        return 3

    # Low priority
    return 4


def _generate_tags(capability: str, agent_spec: AgentSpec) -> list[str]:
    """Generate tags for the TestContract."""
    tags = []

    # Add capability as tag
    tags.append(capability.lower().replace(" ", "-"))

    # Add task type as tag
    tags.append(agent_spec.task_type)

    # Add specific tags based on capability
    capability_lower = capability.lower()
    if "api" in capability_lower:
        tags.append("api")
    if "e2e" in capability_lower or "ui" in capability_lower:
        tags.append("ui")
    if "security" in capability_lower:
        tags.append("security")
    if "performance" in capability_lower:
        tags.append("performance")

    return list(set(tags))  # Deduplicate


# =============================================================================
# Model Selection (Feature #187)
# =============================================================================

def select_model_for_capability(
    capability: str,
    task_type: str,
    constraints: dict[str, Any] | None = None,
    project_settings: dict[str, Any] | None = None,
) -> str:
    """
    Select the appropriate Claude model for an agent based on capability and complexity.

    Feature #187: Octo selects appropriate model for each agent

    Model selection follows this priority order:
    1. Project settings override (if specified)
    2. Constraints model_preference (from OctoRequestPayload)
    3. Explicit capability match (HAIKU_CAPABILITIES or OPUS_CAPABILITIES)
    4. Complexity keywords in capability name
    5. Task type defaults
    6. Default model (sonnet)

    Args:
        capability: The capability name for the agent (e.g., "e2e_testing", "security_audit")
        task_type: The task type (coding, testing, audit, etc.)
        constraints: Optional constraints dict from OctoRequestPayload
        project_settings: Optional project-level settings for model override

    Returns:
        Model name: "sonnet", "opus", or "haiku"

    Examples:
        >>> select_model_for_capability("documentation", "documentation")
        'haiku'
        >>> select_model_for_capability("security_audit", "audit")
        'opus'
        >>> select_model_for_capability("coding", "coding")
        'sonnet'
        >>> select_model_for_capability("e2e_testing", "testing", project_settings={"model": "opus"})
        'opus'
    """
    constraints = constraints or {}
    project_settings = project_settings or {}

    # Priority 1: Project settings override
    if "model" in project_settings:
        model = project_settings["model"].lower()
        if model in VALID_MODELS:
            _logger.debug(
                "Model '%s' selected from project_settings for capability '%s'",
                model, capability
            )
            return model

    # Alternative key names for project settings
    for key in ("default_model", "model_preference", "agent_model"):
        if key in project_settings:
            model = project_settings[key].lower()
            if model in VALID_MODELS:
                _logger.debug(
                    "Model '%s' selected from project_settings[%s] for capability '%s'",
                    model, key, capability
                )
                return model

    # Priority 2: Constraints model_preference
    if "model_preference" in constraints:
        model = constraints["model_preference"].lower()
        if model in VALID_MODELS:
            _logger.debug(
                "Model '%s' selected from constraints for capability '%s'",
                model, capability
            )
            return model

    # Priority 3: Explicit capability match
    capability_lower = capability.lower().replace("-", "_").replace(" ", "_")

    if capability_lower in HAIKU_CAPABILITIES:
        _logger.debug(
            "Model 'haiku' selected for simple capability '%s'",
            capability
        )
        return "haiku"

    if capability_lower in OPUS_CAPABILITIES:
        _logger.debug(
            "Model 'opus' selected for complex capability '%s'",
            capability
        )
        return "opus"

    # Priority 4: Complexity keywords in capability name
    for keyword, model in COMPLEXITY_INDICATORS.items():
        if keyword in capability_lower:
            _logger.debug(
                "Model '%s' selected due to keyword '%s' in capability '%s'",
                model, keyword, capability
            )
            return model

    # Priority 5: Task type defaults
    if task_type in TASK_TYPE_MODEL_DEFAULTS:
        model = TASK_TYPE_MODEL_DEFAULTS[task_type]
        _logger.debug(
            "Model '%s' selected from task_type default for '%s' (capability '%s')",
            model, task_type, capability
        )
        return model

    # Priority 6: Default model
    _logger.debug(
        "Default model '%s' selected for capability '%s'",
        DEFAULT_MODEL, capability
    )
    return DEFAULT_MODEL


def validate_model(model: str) -> tuple[bool, str]:
    """
    Validate that a model name is valid.

    Args:
        model: The model name to validate

    Returns:
        Tuple of (is_valid, normalized_model_or_error_message)
    """
    if not model:
        return False, "Model cannot be empty"

    model_lower = model.lower()
    if model_lower in VALID_MODELS:
        return True, model_lower

    return False, f"Invalid model '{model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"


def get_model_characteristics(model: str) -> dict[str, Any]:
    """
    Get characteristics and recommendations for a model.

    Args:
        model: The model name (sonnet, opus, haiku)

    Returns:
        Dictionary with model characteristics

    Example:
        >>> get_model_characteristics("opus")
        {'name': 'opus', 'complexity': 'high', 'cost': 'high', ...}
    """
    characteristics = {
        "haiku": {
            "name": "haiku",
            "complexity": "low",
            "cost": "low",
            "speed": "fast",
            "use_cases": [
                "Documentation generation",
                "Simple formatting",
                "Quick audits",
                "Status checks",
                "Notifications",
            ],
            "recommended_max_turns": 30,
            "recommended_timeout_seconds": 600,
        },
        "sonnet": {
            "name": "sonnet",
            "complexity": "medium",
            "cost": "medium",
            "speed": "balanced",
            "use_cases": [
                "Standard coding tasks",
                "Testing implementation",
                "Code refactoring",
                "API development",
                "Feature implementation",
            ],
            "recommended_max_turns": 100,
            "recommended_timeout_seconds": 1800,
        },
        "opus": {
            "name": "opus",
            "complexity": "high",
            "cost": "high",
            "speed": "slower",
            "use_cases": [
                "Complex architecture design",
                "Security audits",
                "Performance optimization",
                "Multi-service integration",
                "Root cause analysis",
            ],
            "recommended_max_turns": 150,
            "recommended_timeout_seconds": 3600,
        },
    }

    model_lower = model.lower()
    return characteristics.get(model_lower, characteristics["sonnet"])


# =============================================================================
# Octo Service Class
# =============================================================================

class Octo:
    """
    Octo service for generating AgentSpecs from structured request payloads.

    Octo uses DSPy (via SpecBuilder) to generate AgentSpecs based on:
    - Project context (tech stack, features, environment)
    - Required capabilities (what the agents need to do)
    - Existing agents (to avoid duplication)
    - Constraints (budget limits, model preferences)

    Each generated AgentSpec is validated against the schema before being
    returned to Maestro.

    Feature #176: Maestro delegates to Octo for agent generation
    Feature #183: Octo processes OctoRequestPayload and returns AgentSpecs
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        spec_builder: SpecBuilder | None = None,
    ):
        """
        Initialize Octo service.

        Args:
            api_key: Anthropic API key (uses environment if not provided)
            spec_builder: Optional SpecBuilder instance (creates new if not provided)
        """
        self._api_key = api_key

        # Use provided builder or get/create singleton
        if spec_builder is not None:
            self._builder = spec_builder
        else:
            self._builder = get_spec_builder(
                api_key=api_key,
                force_new=api_key is not None,
            )

        _logger.info("Octo service initialized")

    def generate_specs(
        self,
        payload: OctoRequestPayload,
    ) -> OctoResponse:
        """
        Generate AgentSpecs from the request payload.

        This is the main entry point for Octo. It:
        1. Validates the payload structure
        2. Maps required capabilities to task descriptions
        3. Invokes DSPy SpecBuilder for each capability
        4. Validates each generated AgentSpec against schema
        5. Generates TestContracts for testable agents (Feature #184)
        6. Returns all valid specs and contracts in the response

        Args:
            payload: OctoRequestPayload containing context and requirements

        Returns:
            OctoResponse with generated specs, test contracts, or error information
        """
        # Step 1: Validate payload
        validation_errors = payload.validate()
        if validation_errors:
            _logger.warning("Invalid OctoRequestPayload: %s", validation_errors)
            return OctoResponse(
                success=False,
                error="Invalid request payload",
                error_type="validation_error",
                validation_errors=validation_errors,
                request_id=payload.request_id,
            )

        _logger.info(
            "Octo processing request: %d capabilities, %d existing agents",
            len(payload.required_capabilities),
            len(payload.existing_agents),
        )

        # Step 2: Generate specs for each capability
        generated_specs: list[AgentSpec] = []
        generated_contracts: list[TestContract] = []  # Feature #184
        warnings: list[str] = []

        # Track which specs were generated for which capability (for TestContract linking)
        spec_to_capability: dict[str, str] = {}

        for capability in payload.required_capabilities:
            # Skip if an agent with similar capability already exists
            if self._capability_covered(capability, payload.existing_agents):
                warnings.append(f"Capability '{capability}' covered by existing agent")
                continue

            # Build task description from capability
            task_desc = self._build_task_description(capability, payload)
            task_type = self._infer_task_type(capability)

            # Feature #187: Select appropriate model for this agent
            project_settings = payload.project_context.get("settings", {})
            selected_model = select_model_for_capability(
                capability=capability,
                task_type=task_type,
                constraints=payload.constraints,
                project_settings=project_settings,
            )

            # Invoke SpecBuilder
            _logger.info(
                "Generating spec for capability: %s (task_type=%s, model=%s)",
                capability, task_type, selected_model
            )

            try:
                result: BuildResult = self._builder.build(
                    task_description=task_desc,
                    task_type=task_type,
                    context={
                        "capability": capability,
                        "project_context": payload.project_context,
                        "octo_request_id": payload.request_id,
                        "model": selected_model,  # Feature #187: Include selected model
                    },
                )

                if result.success and result.agent_spec:
                    # Feature #187: Inject model into AgentSpec context
                    self._inject_model_into_spec(result.agent_spec, selected_model)

                    # Validate generated spec against schema
                    validation_result = self._validate_spec(result.agent_spec)

                    if validation_result.is_valid:
                        generated_specs.append(result.agent_spec)
                        spec_to_capability[result.agent_spec.name] = capability
                        _logger.info(
                            "Generated valid spec: %s (task_type=%s, model=%s)",
                            result.agent_spec.name,
                            result.agent_spec.task_type,
                            selected_model,
                        )
                    else:
                        warnings.append(
                            f"Spec for '{capability}' failed validation: {validation_result.errors}"
                        )
                        _logger.warning(
                            "Spec validation failed for %s: %s",
                            capability,
                            validation_result.errors,
                        )
                else:
                    warnings.append(
                        f"Failed to generate spec for '{capability}': {result.error}"
                    )
                    _logger.warning(
                        "SpecBuilder failed for %s: %s",
                        capability,
                        result.error,
                    )

            except Exception as e:
                warnings.append(f"Exception generating spec for '{capability}': {e}")
                _logger.exception("Exception during spec generation for %s", capability)

        # Step 3: Check if any specs were generated
        if not generated_specs:
            return OctoResponse(
                success=False,
                error="No valid specs generated",
                error_type="generation_failed",
                warnings=warnings,
                request_id=payload.request_id,
            )

        # Step 3.5 (Feature #185): Validate specs against constraints
        all_constraint_violations: list[ConstraintViolation] = []
        validated_specs: list[AgentSpec] = []

        # Create constraint validator from payload constraints
        constraint_validator = self._create_constraint_validator(payload)

        for spec in generated_specs:
            # Validate spec against constraints
            constraint_result = constraint_validator.validate(spec, auto_correct=True)

            if constraint_result.is_valid:
                # Spec passes all constraints (possibly after correction)
                final_spec = constraint_result.corrected_spec if constraint_result.corrected_spec else spec
                validated_specs.append(final_spec)
                _logger.info(
                    "Spec %s passed constraint validation (corrected=%s)",
                    spec.name,
                    constraint_result.corrected_spec is not None,
                )
            else:
                # Spec has uncorrectable constraint violations
                all_constraint_violations.extend(constraint_result.violations)
                warnings.append(
                    f"Spec '{spec.name}' rejected due to constraint violations: "
                    f"{[v.message for v in constraint_result.violations]}"
                )
                _logger.warning(
                    "Spec %s rejected due to %d constraint violations",
                    spec.name,
                    len(constraint_result.violations),
                )
                # Feature #185 Step 4: Log constraint violations for debugging
                for violation in constraint_result.violations:
                    _logger.debug(
                        "Constraint violation: spec=%s, type=%s, field=%s, message=%s",
                        spec.name,
                        violation.constraint_type,
                        violation.field,
                        violation.message,
                    )

        # Update generated_specs to use validated/corrected specs
        generated_specs = validated_specs

        # Check if we still have valid specs after constraint validation
        if not generated_specs:
            return OctoResponse(
                success=False,
                error="All specs rejected due to constraint violations",
                error_type="constraint_validation_failed",
                constraint_violations=all_constraint_violations,
                warnings=warnings,
                request_id=payload.request_id,
            )

        # Step 4 (Feature #184): Generate TestContracts for testable agents
        # Feature #188: Validate TestContracts against schema before adding
        for spec in generated_specs:
            capability = spec_to_capability.get(spec.name, "")
            contract = generate_test_contract(
                agent_spec=spec,
                capability=capability,
                project_context=payload.project_context,
            )
            if contract:
                # Feature #188: Validate TestContract against schema
                contract_validation = self._validate_test_contract(contract)
                if contract_validation.is_valid:
                    generated_contracts.append(contract)
                    _logger.info(
                        "Generated valid TestContract for agent %s: test_type=%s, assertions=%d",
                        spec.name,
                        contract.test_type,
                        len(contract.assertions),
                    )
                else:
                    warnings.append(
                        f"TestContract for '{spec.name}' failed validation: {contract_validation.error_messages[:2]}"
                    )
                    _logger.warning(
                        "TestContract validation failed for %s: %s",
                        spec.name,
                        contract_validation.error_messages[:3],
                    )

        # Step 5 (Feature #188): Final validation - ensure no invalid outputs propagate
        # Perform final schema validation on all outputs before returning
        try:
            spec_dicts = [spec.to_dict() for spec in generated_specs]
            contract_dicts = [c.to_dict() for c in generated_contracts]

            # Validate all outputs (this will catch any edge cases)
            validate_octo_outputs(
                spec_dicts,
                contract_dicts,
                raise_on_error=True,
            )
        except OctoSchemaValidationError as e:
            _logger.error(
                "Final validation failed for Octo outputs: %s",
                str(e),
            )
            return OctoResponse(
                success=False,
                error=f"Output validation failed: {str(e)}",
                error_type="schema_validation_error",
                validation_errors=e.result.error_messages,
                warnings=warnings,
                request_id=payload.request_id,
            )

        _logger.info(
            "Octo generated %d specs and %d test contracts for request %s (all validated)",
            len(generated_specs),
            len(generated_contracts),
            payload.request_id,
        )

        return OctoResponse(
            success=True,
            agent_specs=generated_specs,
            test_contracts=generated_contracts,
            constraint_violations=all_constraint_violations,  # Feature #185: Include any violations
            warnings=warnings,
            request_id=payload.request_id,
        )

    def _capability_covered(
        self,
        capability: str,
        existing_agents: list[str],
    ) -> bool:
        """
        Check if a capability is already covered by existing agents.

        Uses simple string matching for now. Can be made smarter with
        capability-to-agent mapping.
        """
        capability_lower = capability.lower()

        for agent in existing_agents:
            agent_lower = agent.lower()
            # Check for substring matches
            if capability_lower in agent_lower or agent_lower in capability_lower:
                return True
            # Check common mappings
            if (capability_lower == "coding" and "coder" in agent_lower):
                return True
            if (capability_lower == "testing" and "test" in agent_lower):
                return True

        return False

    def _build_task_description(
        self,
        capability: str,
        payload: OctoRequestPayload,
    ) -> str:
        """
        Build a natural language task description for DSPy from capability.
        """
        project_name = payload.project_context.get("name", "the project")
        tech_stack = payload.project_context.get("tech_stack", [])
        tech_str = ", ".join(tech_stack) if tech_stack else "various technologies"

        # Map common capabilities to descriptions
        capability_descriptions = {
            "ui_testing": f"Implement end-to-end UI testing for {project_name} using browser automation.",
            "api_testing": f"Implement API integration tests for {project_name}'s backend endpoints.",
            "e2e_testing": f"Implement comprehensive end-to-end tests for {project_name}.",
            "unit_testing": f"Implement unit tests for {project_name} components.",
            "documentation": f"Generate and maintain documentation for {project_name}.",
            "security_audit": f"Perform security audit and vulnerability scanning for {project_name}.",
            "code_review": f"Review code changes and enforce quality standards for {project_name}.",
            "refactoring": f"Identify and implement refactoring opportunities in {project_name}.",
            "deployment": f"Handle deployment and release processes for {project_name}.",
            "monitoring": f"Set up monitoring and alerting for {project_name}.",
        }

        base_desc = capability_descriptions.get(
            capability.lower(),
            f"Implement {capability} functionality for {project_name}."
        )

        return f"{base_desc} The project uses {tech_str}."

    def _infer_task_type(self, capability: str) -> str:
        """
        Infer task_type from capability name.
        """
        capability_lower = capability.lower()

        # Testing-related capabilities
        if any(kw in capability_lower for kw in ["test", "qa", "e2e", "integration"]):
            return "testing"

        # Documentation capabilities
        if any(kw in capability_lower for kw in ["doc", "readme", "wiki"]):
            return "documentation"

        # Audit/security capabilities
        if any(kw in capability_lower for kw in ["audit", "security", "scan", "review"]):
            return "audit"

        # Refactoring capabilities
        if any(kw in capability_lower for kw in ["refactor", "cleanup", "optimize"]):
            return "refactoring"

        # Default to coding
        return "coding"

    def _create_constraint_validator(
        self,
        payload: OctoRequestPayload,
    ) -> ConstraintValidator:
        """
        Create a ConstraintValidator from payload constraints.

        Feature #185, Step 1: Define constraints from payload

        Args:
            payload: The OctoRequestPayload containing constraints

        Returns:
            ConstraintValidator configured with appropriate constraints
        """
        # Create constraints from payload's constraints dict
        constraints = create_constraints_from_payload(
            constraints_dict=payload.constraints,
            project_context=payload.project_context,
        )

        # Create and return validator
        validator = ConstraintValidator(
            constraints=constraints,
            auto_correct=True,  # Attempt to auto-correct violations
            reject_on_uncorrectable=True,  # Reject specs with uncorrectable violations
        )

        _logger.debug(
            "Created ConstraintValidator with %d constraints for request %s",
            len(constraints),
            payload.request_id,
        )

        return validator

    def _validate_spec(self, spec: AgentSpec) -> SpecValidationResult:
        """
        Validate an AgentSpec against multiple validation layers.

        Feature #188: Octo outputs are strictly typed and schema-validated

        This method performs two-layer validation:
        1. SpecValidationResult from spec_validator (model-level validation)
        2. SchemaValidationResult from octo_schemas (JSON schema validation)

        Both layers must pass for the spec to be considered valid.
        """
        # Layer 1: Model-level validation (from spec_validator)
        model_result = validate_spec(spec)

        if not model_result.is_valid:
            _logger.warning(
                "AgentSpec %s failed model validation: %s",
                getattr(spec, "name", "unknown"),
                model_result.error_messages[:3],
            )
            return model_result

        # Layer 2: JSON schema validation (Feature #188)
        try:
            spec_dict = spec.to_dict()
            schema_result = validate_agent_spec_schema(spec_dict)

            if not schema_result.is_valid:
                _logger.warning(
                    "AgentSpec %s failed schema validation: %s",
                    spec.name,
                    schema_result.error_messages[:3],
                )
                # Convert schema errors to model validation format
                # This ensures consistent error format for callers
                from api.spec_validator import ValidationError
                converted_errors = [
                    ValidationError(
                        field=err.path,
                        message=err.message,
                        code=err.code,
                        value=err.value,
                    )
                    for err in schema_result.errors
                ]
                return SpecValidationResult(
                    is_valid=False,
                    errors=converted_errors,
                    spec_id=spec.id,
                    spec_name=spec.name,
                )

        except Exception as e:
            _logger.exception(
                "Exception during schema validation for %s: %s",
                getattr(spec, "name", "unknown"),
                e,
            )
            from api.spec_validator import ValidationError
            return SpecValidationResult(
                is_valid=False,
                errors=[ValidationError(
                    field="$",
                    message=f"Schema validation exception: {e}",
                    code="schema_exception",
                )],
                spec_id=getattr(spec, "id", None),
                spec_name=getattr(spec, "name", None),
            )

        _logger.debug(
            "AgentSpec %s passed all validation layers",
            spec.name,
        )
        return model_result

    def _validate_test_contract(self, contract: TestContract) -> SchemaValidationResult:
        """
        Validate a TestContract against the JSON schema.

        Feature #188: Octo outputs are strictly typed and schema-validated

        Args:
            contract: The TestContract to validate

        Returns:
            SchemaValidationResult with is_valid flag and any errors
        """
        try:
            # First validate using the contract's own validate method
            internal_errors = contract.validate()
            if internal_errors:
                _logger.warning(
                    "TestContract %s failed internal validation: %s",
                    contract.agent_name,
                    internal_errors[:3],
                )
                return SchemaValidationResult(
                    is_valid=False,
                    errors=[
                        SchemaValidationError(
                            path="$",
                            message=err,
                            code="internal_validation",
                        )
                        for err in internal_errors
                    ],
                    schema_name="TestContract",
                )

            # Then validate against JSON schema
            contract_dict = contract.to_dict()
            schema_result = validate_test_contract_schema(contract_dict)

            if not schema_result.is_valid:
                _logger.warning(
                    "TestContract %s failed schema validation: %s",
                    contract.agent_name,
                    schema_result.error_messages[:3],
                )

            return schema_result

        except Exception as e:
            _logger.exception(
                "Exception during TestContract validation for %s: %s",
                getattr(contract, "agent_name", "unknown"),
                e,
            )
            return SchemaValidationResult(
                is_valid=False,
                errors=[SchemaValidationError(
                    path="$",
                    message=f"Schema validation exception: {e}",
                    code="schema_exception",
                )],
                schema_name="TestContract",
            )

    def _inject_model_into_spec(
        self,
        spec: AgentSpec,
        model: str,
    ) -> None:
        """
        Inject the selected model into the AgentSpec's context.

        Feature #187: Octo selects appropriate model for each agent

        The model is stored in the spec's context field under the key 'model'.
        This allows downstream consumers (harness, executors) to use the
        appropriate Claude model for execution.

        Args:
            spec: The AgentSpec to modify
            model: The selected model name (sonnet, opus, haiku)
        """
        # Ensure context exists
        if spec.context is None:
            spec.context = {}

        # Store model in context
        spec.context["model"] = model

        # Also store model characteristics for downstream consumers
        characteristics = get_model_characteristics(model)
        spec.context["model_characteristics"] = {
            "complexity": characteristics["complexity"],
            "cost": characteristics["cost"],
            "speed": characteristics["speed"],
        }

        _logger.debug(
            "Injected model '%s' into AgentSpec '%s' context",
            model,
            spec.name,
        )

    def _create_constraint_validator(
        self,
        payload: OctoRequestPayload,
    ) -> ConstraintValidator:
        """
        Create a ConstraintValidator from the OctoRequestPayload.

        Feature #185: Octo DSPy module with constraint satisfaction

        This method creates constraints from the payload's constraints field
        and wraps them in a ConstraintValidator for spec validation.

        Args:
            payload: The OctoRequestPayload containing constraint definitions

        Returns:
            ConstraintValidator configured for the payload's constraints
        """
        # If payload has explicit constraints, use them
        if payload.constraints:
            constraints = create_constraints_from_payload(payload.constraints)
        else:
            # Use default constraints if none specified
            constraints = create_default_constraints()

        return ConstraintValidator(constraints)


# =============================================================================
# Module-level convenience functions
# =============================================================================

_default_octo: Octo | None = None


def get_octo(api_key: str | None = None) -> Octo:
    """
    Get or create the default Octo instance.

    Args:
        api_key: Optional API key override

    Returns:
        Octo service instance
    """
    global _default_octo

    if _default_octo is None or api_key is not None:
        _default_octo = Octo(api_key=api_key)

    return _default_octo


def reset_octo() -> None:
    """Reset the default Octo instance (for testing)."""
    global _default_octo
    _default_octo = None
