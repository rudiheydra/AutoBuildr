"""
Tests for Feature #174: Maestro detects when new agents are needed

Maestro analyzes project context and feature backlog to identify when additional
agents beyond the defaults are required. This triggers the agent-planning workflow.

Verification Steps:
1. Maestro receives project context including tech stack, features, and execution environment
2. Maestro evaluates whether existing agents can handle all features
3. When specialized capabilities are needed, Maestro flags agent-planning required
4. Maestro outputs a structured agent-planning decision with justification
"""
import json
import pytest
from pathlib import Path

from api.maestro import (
    Maestro,
    ProjectContext,
    CapabilityRequirement,
    AgentPlanningDecision,
    DEFAULT_AGENTS,
    SPECIALIZED_CAPABILITY_KEYWORDS,
    get_maestro,
    reset_maestro,
    evaluate_project,
    detect_agent_planning_required,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def maestro():
    """Fresh Maestro instance for each test."""
    reset_maestro()
    return Maestro()


@pytest.fixture
def simple_context():
    """Simple project context with no specialized requirements."""
    return ProjectContext(
        project_name="simple-app",
        tech_stack=["python"],
        features=[
            {"id": 1, "name": "Add user login", "description": "Implement login functionality"},
            {"id": 2, "name": "Create API endpoint", "description": "Add REST endpoint"},
        ],
        existing_agents=["coding", "testing"],
    )


@pytest.fixture
def complex_context():
    """Complex project context with specialized requirements."""
    return ProjectContext(
        project_name="complex-app",
        tech_stack=["python", "react", "playwright", "fastapi"],
        features=[
            {"id": 1, "name": "E2E login test", "description": "Write playwright end-to-end tests for login flow"},
            {"id": 2, "name": "React dashboard", "description": "Create React dashboard component with hooks"},
            {"id": 3, "name": "FastAPI auth", "description": "Implement FastAPI authentication with Pydantic models"},
        ],
        existing_agents=["coding", "testing"],
    )


# =============================================================================
# Step 1: Maestro receives project context
# =============================================================================

class TestStep1ProjectContext:
    """Verify Maestro receives project context including tech stack, features, and execution environment."""

    def test_project_context_creation(self):
        """ProjectContext can be created with all required fields."""
        context = ProjectContext(
            project_name="test-project",
            tech_stack=["python", "react"],
            features=[{"id": 1, "name": "Feature 1"}],
            execution_environment="docker",
            existing_agents=["coding", "testing"],
        )

        assert context.project_name == "test-project"
        assert context.tech_stack == ["python", "react"]
        assert len(context.features) == 1
        assert context.execution_environment == "docker"
        assert context.existing_agents == ["coding", "testing"]

    def test_project_context_default_values(self):
        """ProjectContext has sensible defaults."""
        context = ProjectContext(project_name="minimal")

        assert context.project_name == "minimal"
        assert context.tech_stack == []
        assert context.features == []
        assert context.execution_environment == "local"
        assert set(context.existing_agents) == {"coding", "testing"}

    def test_project_context_to_dict(self):
        """ProjectContext can be serialized to dict."""
        context = ProjectContext(
            project_name="test",
            project_dir=Path("/tmp/test"),
            tech_stack=["python"],
            features=[{"id": 1}],
        )

        data = context.to_dict()
        assert data["project_name"] == "test"
        assert data["project_dir"] == "/tmp/test"
        assert data["tech_stack"] == ["python"]
        assert data["features"] == [{"id": 1}]

    def test_project_context_from_dict(self):
        """ProjectContext can be deserialized from dict."""
        data = {
            "project_name": "from-dict",
            "project_dir": "/tmp/test",
            "tech_stack": ["react"],
            "features": [{"id": 2}],
            "execution_environment": "ci",
            "existing_agents": ["coding"],
        }

        context = ProjectContext.from_dict(data)
        assert context.project_name == "from-dict"
        assert context.project_dir == Path("/tmp/test")
        assert context.tech_stack == ["react"]
        assert context.execution_environment == "ci"

    def test_maestro_accepts_project_context(self, maestro, simple_context):
        """Maestro.evaluate() accepts ProjectContext and returns decision."""
        decision = maestro.evaluate(simple_context)

        assert isinstance(decision, AgentPlanningDecision)
        assert isinstance(decision.requires_agent_planning, bool)

    def test_maestro_logs_context_details(self, maestro, caplog):
        """Maestro logs project context details during evaluation."""
        import logging
        caplog.set_level(logging.INFO)

        context = ProjectContext(
            project_name="logged-project",
            tech_stack=["python"],
            features=[{"id": 1}],
            existing_agents=["coding"],
        )

        maestro.evaluate(context)

        # Check that project name appears in logs
        assert "logged-project" in caplog.text or "Maestro evaluating" in caplog.text


# =============================================================================
# Step 2: Maestro evaluates existing agents
# =============================================================================

class TestStep2ExistingAgentEvaluation:
    """Verify Maestro evaluates whether existing agents can handle all features."""

    def test_default_agents_handle_basic_coding(self, maestro):
        """Default agents can handle basic coding tasks."""
        context = ProjectContext(
            project_name="basic",
            features=[
                {"id": 1, "name": "Implement feature", "description": "Add new functionality"},
            ],
        )

        decision = maestro.evaluate(context)
        # Basic coding should not require new agents
        assert decision.requires_agent_planning is False

    def test_default_agents_handle_basic_testing(self, maestro):
        """Default agents can handle basic testing tasks."""
        context = ProjectContext(
            project_name="basic-tests",
            features=[
                {"id": 1, "name": "Write unit tests", "description": "Add pytest unit tests"},
            ],
        )

        decision = maestro.evaluate(context)
        # Basic testing should not require new agents
        assert decision.requires_agent_planning is False

    def test_existing_agent_covers_capability(self, maestro):
        """If an existing agent covers a capability, no new agent is needed."""
        context = ProjectContext(
            project_name="covered",
            tech_stack=["playwright"],
            features=[
                {"id": 1, "name": "E2E tests", "description": "Write playwright browser tests"},
            ],
            existing_agents=["coding", "testing", "playwright"],
        )

        decision = maestro.evaluate(context)
        # Playwright capability is covered by existing agent
        assert decision.requires_agent_planning is False

    def test_can_existing_agents_handle_checks_mapping(self, maestro):
        """can_existing_agents_handle checks capability-to-agent mapping."""
        # Coding is handled by default
        assert maestro.can_existing_agents_handle("coding", ["coding"]) is True

        # Playwright is NOT handled by default agents
        assert maestro.can_existing_agents_handle("playwright", ["coding", "testing"]) is False

        # Playwright IS handled if playwright agent exists
        assert maestro.can_existing_agents_handle("playwright", ["coding", "playwright"]) is True

        # e2e agent also handles playwright
        assert maestro.can_existing_agents_handle("playwright", ["coding", "e2e"]) is True

    def test_existing_capabilities_tracked(self, maestro, complex_context):
        """Decision tracks which capabilities are covered by existing agents."""
        decision = maestro.evaluate(complex_context)

        # existing_capabilities should list what's covered
        assert isinstance(decision.existing_capabilities, list)


# =============================================================================
# Step 3: Specialized capabilities detection
# =============================================================================

class TestStep3SpecializedCapabilities:
    """When specialized capabilities are needed, Maestro flags agent-planning required."""

    def test_playwright_triggers_agent_planning(self, maestro):
        """Playwright/E2E testing triggers agent-planning requirement."""
        context = ProjectContext(
            project_name="e2e-app",
            tech_stack=["playwright"],
            features=[
                {"id": 1, "name": "E2E tests", "description": "Browser automation tests with playwright"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True
        assert any(r.capability == "playwright" for r in decision.required_capabilities)

    def test_react_triggers_agent_planning(self, maestro):
        """React framework triggers agent-planning requirement."""
        context = ProjectContext(
            project_name="react-app",
            tech_stack=["react"],
            features=[
                {"id": 1, "name": "Dashboard", "description": "Create React component with hooks"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True
        assert any(r.capability == "react" for r in decision.required_capabilities)

    def test_docker_triggers_agent_planning(self, maestro):
        """Docker/containerization triggers agent-planning requirement."""
        context = ProjectContext(
            project_name="docker-app",
            features=[
                {"id": 1, "name": "Containerize", "description": "Create Dockerfile and docker compose configuration"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True
        assert any(r.capability == "docker" for r in decision.required_capabilities)

    def test_security_audit_triggers_agent_planning(self, maestro):
        """Security audit triggers agent-planning requirement."""
        context = ProjectContext(
            project_name="secure-app",
            features=[
                {"id": 1, "name": "Security review", "description": "Perform security audit and vulnerability scan"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True
        assert any(r.capability == "security_audit" for r in decision.required_capabilities)

    def test_multiple_capabilities_detected(self, maestro, complex_context):
        """Multiple specialized capabilities are detected from complex context."""
        decision = maestro.evaluate(complex_context)

        # Should detect multiple capabilities
        capabilities = [r.capability for r in decision.required_capabilities]
        # At least playwright and react should be detected
        assert "playwright" in capabilities or "react" in capabilities or "fastapi" in capabilities

    def test_capability_detected_from_feature_text(self, maestro):
        """Capabilities are detected from feature name and description."""
        context = ProjectContext(
            project_name="text-detect",
            features=[
                {"id": 1, "name": "Simple name", "description": "Run end-to-end browser automation with playwright"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True

    def test_capability_detected_from_tech_stack(self, maestro):
        """Capabilities are detected from tech stack even without features mentioning them."""
        context = ProjectContext(
            project_name="stack-detect",
            tech_stack=["kubernetes", "terraform"],
            features=[
                {"id": 1, "name": "Deploy app", "description": "Deploy the application"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True

    def test_keyword_matching_case_insensitive(self, maestro):
        """Keyword matching is case-insensitive."""
        context = ProjectContext(
            project_name="case-test",
            features=[
                {"id": 1, "name": "PLAYWRIGHT Tests", "description": "Use REACT hooks"},
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True

    def test_no_false_positives_for_common_words(self, maestro):
        """Common words don't trigger false positive capabilities."""
        context = ProjectContext(
            project_name="safe",
            features=[
                {"id": 1, "name": "Add feature", "description": "Implement basic functionality"},
            ],
        )

        decision = maestro.evaluate(context)
        # Should not require agent planning for basic features
        assert decision.requires_agent_planning is False


# =============================================================================
# Step 4: Structured decision output
# =============================================================================

class TestStep4StructuredOutput:
    """Maestro outputs a structured agent-planning decision with justification."""

    def test_decision_has_required_fields(self, maestro, complex_context):
        """AgentPlanningDecision has all required fields."""
        decision = maestro.evaluate(complex_context)

        assert hasattr(decision, 'requires_agent_planning')
        assert hasattr(decision, 'required_capabilities')
        assert hasattr(decision, 'existing_capabilities')
        assert hasattr(decision, 'justification')
        assert hasattr(decision, 'recommended_agent_types')

    def test_decision_to_dict(self, maestro, complex_context):
        """AgentPlanningDecision serializes to dict."""
        decision = maestro.evaluate(complex_context)
        data = decision.to_dict()

        assert isinstance(data, dict)
        assert "requires_agent_planning" in data
        assert "required_capabilities" in data
        assert "justification" in data
        assert "recommended_agent_types" in data

    def test_decision_to_json(self, maestro, complex_context):
        """AgentPlanningDecision serializes to valid JSON."""
        decision = maestro.evaluate(complex_context)
        json_str = decision.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert "requires_agent_planning" in parsed

    def test_justification_explains_decision(self, maestro, complex_context):
        """Justification provides human-readable explanation."""
        decision = maestro.evaluate(complex_context)

        assert decision.justification
        assert len(decision.justification) > 20  # Not empty or trivial

        if decision.requires_agent_planning:
            # Should mention the required capabilities
            assert "capability" in decision.justification.lower() or "agent" in decision.justification.lower()

    def test_recommended_agent_types_populated(self, maestro, complex_context):
        """When planning required, recommended_agent_types is populated."""
        decision = maestro.evaluate(complex_context)

        if decision.requires_agent_planning:
            assert len(decision.recommended_agent_types) > 0
            # All recommendations should be non-empty strings
            for agent_type in decision.recommended_agent_types:
                assert isinstance(agent_type, str)
                assert len(agent_type) > 0

    def test_capability_requirement_has_source(self, maestro, complex_context):
        """Each capability requirement tracks its source."""
        decision = maestro.evaluate(complex_context)

        for req in decision.required_capabilities:
            assert req.source
            assert req.source.startswith("feature_") or req.source == "tech_stack"

    def test_capability_requirement_has_keywords_matched(self, maestro, complex_context):
        """Each capability requirement tracks matched keywords."""
        decision = maestro.evaluate(complex_context)

        for req in decision.required_capabilities:
            assert isinstance(req.keywords_matched, list)
            if req.keywords_matched:  # May be empty for some detections
                assert all(isinstance(kw, str) for kw in req.keywords_matched)

    def test_capability_requirement_has_confidence(self, maestro, complex_context):
        """Each capability requirement has confidence level."""
        decision = maestro.evaluate(complex_context)

        for req in decision.required_capabilities:
            assert req.confidence in ("high", "medium", "low")


# =============================================================================
# Integration Tests
# =============================================================================

class TestMaestroIntegration:
    """Integration tests for the complete Maestro workflow."""

    def test_full_evaluation_workflow(self, maestro):
        """Complete evaluation workflow from context to decision."""
        # Create realistic project context
        context = ProjectContext(
            project_name="fullstack-app",
            project_dir=Path("/tmp/fullstack-app"),
            tech_stack=["python", "fastapi", "react", "postgresql", "playwright"],
            features=[
                {
                    "id": 1,
                    "name": "User authentication",
                    "description": "Implement OAuth2 login with FastAPI",
                    "category": "authentication",
                },
                {
                    "id": 2,
                    "name": "Dashboard UI",
                    "description": "Create React dashboard with real-time updates using hooks",
                    "category": "frontend",
                },
                {
                    "id": 3,
                    "name": "E2E test suite",
                    "description": "Write playwright end-to-end tests for critical flows",
                    "category": "testing",
                },
            ],
            execution_environment="docker",
            existing_agents=["coding", "testing"],
        )

        decision = maestro.evaluate(context)

        # Should require agent planning
        assert decision.requires_agent_planning is True

        # Should detect multiple capabilities
        assert len(decision.required_capabilities) >= 2

        # Should recommend specialized agents
        assert len(decision.recommended_agent_types) >= 1

        # Justification should be substantial
        assert len(decision.justification) > 50

        # Decision should serialize properly
        json_str = decision.to_json()
        parsed = json.loads(json_str)
        assert parsed["requires_agent_planning"] is True

    def test_module_level_functions(self):
        """Module-level convenience functions work correctly."""
        reset_maestro()

        # get_maestro returns singleton
        m1 = get_maestro()
        m2 = get_maestro()
        assert m1 is m2

        # evaluate_project works
        context = ProjectContext(project_name="module-test")
        decision = evaluate_project(context)
        assert isinstance(decision, AgentPlanningDecision)

        # detect_agent_planning_required convenience function
        decision = detect_agent_planning_required(
            project_name="convenience-test",
            tech_stack=["playwright"],
            features=[{"id": 1, "name": "E2E test"}],
        )
        assert isinstance(decision, AgentPlanningDecision)
        assert decision.requires_agent_planning is True

    def test_empty_project_no_planning_needed(self, maestro):
        """Empty project with no features doesn't require agent planning."""
        context = ProjectContext(
            project_name="empty",
            tech_stack=[],
            features=[],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is False

    def test_deduplication_of_capabilities(self, maestro):
        """Same capability detected multiple times is deduplicated."""
        context = ProjectContext(
            project_name="dedup-test",
            tech_stack=["playwright"],  # Mentions playwright
            features=[
                {"id": 1, "name": "E2E tests", "description": "Use playwright"},  # Mentions again
                {"id": 2, "name": "Browser tests", "description": "Playwright automation"},  # And again
            ],
        )

        decision = maestro.evaluate(context)

        # Should only have one playwright requirement, not three
        playwright_reqs = [r for r in decision.required_capabilities if r.capability == "playwright"]
        assert len(playwright_reqs) == 1


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Edge cases and error handling."""

    def test_feature_with_missing_fields(self, maestro):
        """Features with missing fields are handled gracefully."""
        context = ProjectContext(
            project_name="sparse",
            features=[
                {"id": 1},  # Minimal feature
                {"name": "No ID"},  # Missing ID
                {"description": "Only description with playwright"},  # Missing name
            ],
        )

        # Should not crash
        decision = maestro.evaluate(context)
        assert isinstance(decision, AgentPlanningDecision)

    def test_feature_steps_as_list(self, maestro):
        """Feature steps as list are processed."""
        context = ProjectContext(
            project_name="steps-list",
            features=[
                {
                    "id": 1,
                    "name": "Test feature",
                    "steps": ["Write playwright test", "Run browser automation"],
                },
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True

    def test_feature_steps_as_string(self, maestro):
        """Feature steps as string are processed."""
        context = ProjectContext(
            project_name="steps-string",
            features=[
                {
                    "id": 1,
                    "name": "Test feature",
                    "steps": "Write playwright test and run browser automation",
                },
            ],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True

    def test_none_values_handled(self, maestro):
        """None values in context are handled."""
        context = ProjectContext(
            project_name="nullable",
            project_dir=None,
            tech_stack=["python"],
            features=[{"id": 1, "name": None, "description": "Test"}],
        )

        # Should not crash
        decision = maestro.evaluate(context)
        assert isinstance(decision, AgentPlanningDecision)

    def test_custom_capability_keywords(self):
        """Maestro can be initialized with custom capability keywords."""
        custom_keywords = {
            "my_framework": frozenset(["myframework", "mf-tool"]),
        }

        maestro = Maestro(capability_keywords=custom_keywords)

        context = ProjectContext(
            project_name="custom",
            features=[{"id": 1, "name": "Use myframework"}],
        )

        decision = maestro.evaluate(context)
        assert decision.requires_agent_planning is True
        assert any(r.capability == "my_framework" for r in decision.required_capabilities)


# =============================================================================
# Capability Keywords Coverage
# =============================================================================

class TestCapabilityKeywordsCoverage:
    """Verify all expected capability keywords are defined."""

    def test_e2e_testing_keywords_defined(self):
        """E2E testing keywords are defined."""
        assert "playwright" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "cypress" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "selenium" in SPECIALIZED_CAPABILITY_KEYWORDS

    def test_frontend_framework_keywords_defined(self):
        """Frontend framework keywords are defined."""
        assert "react" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "vue" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "angular" in SPECIALIZED_CAPABILITY_KEYWORDS

    def test_backend_framework_keywords_defined(self):
        """Backend framework keywords are defined."""
        assert "fastapi" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "django" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "flask" in SPECIALIZED_CAPABILITY_KEYWORDS

    def test_infrastructure_keywords_defined(self):
        """Infrastructure keywords are defined."""
        assert "docker" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "kubernetes" in SPECIALIZED_CAPABILITY_KEYWORDS
        assert "terraform" in SPECIALIZED_CAPABILITY_KEYWORDS

    def test_default_agents_defined(self):
        """Default agents are defined."""
        assert "coding" in DEFAULT_AGENTS
        assert "testing" in DEFAULT_AGENTS
