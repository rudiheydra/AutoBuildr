"""
Test Feature #184: Octo generates TestContract alongside AgentSpec when applicable
==================================================================================

This test suite verifies that Octo correctly generates TestContract structures
for agents with testable responsibilities.

Feature Steps:
1. Octo evaluates if agent responsibilities are testable
2. For testable agents, Octo generates TestContract structure
3. TestContract includes: test_type, assertions, pass_criteria, fail_criteria
4. TestContract linked to AgentSpec via agent_name
5. TestContract is structured data, not test code
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from api.octo import (
    # Core classes
    Octo,
    OctoRequestPayload,
    OctoResponse,
    # TestContract classes
    TestContract,
    TestContractAssertion,
    TEST_TYPES,
    # Testability evaluation
    TESTABLE_CAPABILITIES,
    TESTABLE_TASK_TYPES,
    TESTABLE_OBJECTIVE_KEYWORDS,
    is_capability_testable,
    is_task_type_testable,
    is_objective_testable,
    evaluate_agent_testability,
    generate_test_contract,
    # Module functions
    get_octo,
    reset_octo,
)
from api.agentspec_models import (
    AgentSpec,
    AcceptanceSpec,
    TASK_TYPES as AGENT_TASK_TYPES,
    generate_uuid,
)
from api.spec_builder import (
    SpecBuilder,
    BuildResult,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset Octo singleton before each test."""
    reset_octo()
    yield
    reset_octo()


@pytest.fixture
def sample_payload():
    """Create a sample OctoRequestPayload for testing."""
    return OctoRequestPayload(
        project_context={
            "name": "TestApp",
            "tech_stack": ["python", "react", "fastapi"],
            "app_spec_summary": "A full-stack web application for task management",
            "directory_structure": ["src/", "tests/", "api/"],
        },
        required_capabilities=["e2e_testing", "api_testing"],
        existing_agents=["coder", "test-runner"],
        constraints={
            "max_agents": 3,
            "model": "sonnet",
        },
        source_feature_ids=[1, 2, 3],
    )


@pytest.fixture
def sample_agent_spec():
    """Create a sample AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="test-e2e-agent",
        display_name="Test E2E Agent",
        icon="test-tube",
        spec_version="v1",
        objective="Implement end-to-end tests for TestApp using Playwright",
        task_type="testing",
        context={"capability": "e2e_testing"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["browser_navigate", "browser_click", "browser_type"],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=1800,
        tags=["testing", "e2e"],
    )


@pytest.fixture
def api_agent_spec():
    """Create an API-focused AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="api-testing-agent",
        display_name="API Testing Agent",
        icon="api",
        spec_version="v1",
        objective="Implement API integration tests for backend endpoints",
        task_type="testing",
        context={"capability": "api_testing"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "WebFetch"],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=1800,
        tags=["testing", "api"],
    )


@pytest.fixture
def coding_agent_spec():
    """Create a coding-focused AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="feature-coder",
        display_name="Feature Coder",
        icon="code",
        spec_version="v1",
        objective="Implement new feature for user authentication",
        task_type="coding",
        context={"capability": "coding"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Edit", "Bash"],
            "forbidden_patterns": [],
        },
        max_turns=100,
        timeout_seconds=3600,
        tags=["coding", "feature"],
    )


@pytest.fixture
def documentation_agent_spec():
    """Create a documentation-focused AgentSpec (non-testable).

    Note: The objective must not contain testable keywords like 'api', 'implement',
    'create', 'build', 'test', etc. to truly be non-testable.
    """
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="docs-agent",
        display_name="Documentation Agent",
        icon="book",
        spec_version="v1",
        objective="Write README and changelog for the library",  # No testable keywords
        task_type="documentation",
        context={"capability": "documentation"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write"],
            "forbidden_patterns": [],
        },
        max_turns=30,
        timeout_seconds=1200,
        tags=["documentation"],
    )


@pytest.fixture
def mock_spec_builder(sample_agent_spec):
    """Create a mock SpecBuilder that returns successful results."""
    mock_builder = MagicMock(spec=SpecBuilder)
    mock_builder.build.return_value = BuildResult(
        success=True,
        agent_spec=sample_agent_spec,
        acceptance_spec=AcceptanceSpec(
            validators=[],
        ),
    )
    return mock_builder


# =============================================================================
# Step 1: Octo evaluates if agent responsibilities are testable
# =============================================================================

class TestStep1TestabilityEvaluation:
    """Test that Octo correctly evaluates whether agents are testable."""

    def test_capability_testability_check(self):
        """is_capability_testable should identify testable capabilities."""
        # Testable capabilities
        assert is_capability_testable("e2e_testing") is True
        assert is_capability_testable("api_testing") is True
        assert is_capability_testable("unit_testing") is True
        assert is_capability_testable("coding") is True
        assert is_capability_testable("refactoring") is True
        assert is_capability_testable("api_implementation") is True

        # Non-testable capabilities
        assert is_capability_testable("documentation") is False
        assert is_capability_testable("planning") is False
        assert is_capability_testable("monitoring") is False

    def test_capability_normalization(self):
        """is_capability_testable should normalize capability names."""
        # Various formats should work
        assert is_capability_testable("e2e-testing") is True
        assert is_capability_testable("E2E_TESTING") is True
        assert is_capability_testable("api testing") is True

    def test_task_type_testability_check(self):
        """is_task_type_testable should identify testable task types."""
        assert is_task_type_testable("coding") is True
        assert is_task_type_testable("testing") is True
        assert is_task_type_testable("refactoring") is True

        assert is_task_type_testable("documentation") is False
        assert is_task_type_testable("audit") is False
        assert is_task_type_testable("custom") is False

    def test_objective_testability_check(self):
        """is_objective_testable should identify testable objectives."""
        # Testable objectives
        assert is_objective_testable("Implement user authentication API") is True
        assert is_objective_testable("Create new React component") is True
        assert is_objective_testable("Build REST API endpoints") is True
        assert is_objective_testable("Test the login flow") is True
        assert is_objective_testable("Fix bug in payment processing") is True

        # Non-testable objectives
        assert is_objective_testable("Generate documentation") is False
        assert is_objective_testable("Review code changes") is False
        assert is_objective_testable("") is False
        assert is_objective_testable(None) is False  # type: ignore

    def test_evaluate_agent_testability_combined(self):
        """evaluate_agent_testability should combine all signals."""
        # Testable by capability
        is_testable, reason = evaluate_agent_testability(
            capability="e2e_testing",
            task_type="audit",  # Not testable
            objective="Generate reports",  # Not testable
        )
        assert is_testable is True
        assert "capability 'e2e_testing'" in reason

        # Testable by task type
        is_testable, reason = evaluate_agent_testability(
            capability="unknown",
            task_type="coding",
            objective="Generate reports",
        )
        assert is_testable is True
        assert "task_type 'coding'" in reason

        # Testable by objective
        is_testable, reason = evaluate_agent_testability(
            capability="unknown",
            task_type="audit",
            objective="Implement the new feature",
        )
        assert is_testable is True
        assert "objective describes testable work" in reason

        # Not testable
        is_testable, reason = evaluate_agent_testability(
            capability="documentation",
            task_type="documentation",
            objective="Generate docs",
        )
        assert is_testable is False
        assert "no testable responsibilities" in reason

    def test_testability_evaluation_all_signals(self):
        """evaluate_agent_testability with all testable signals."""
        is_testable, reason = evaluate_agent_testability(
            capability="api_testing",
            task_type="testing",
            objective="Implement API endpoint tests",
        )
        assert is_testable is True
        # Should have multiple reasons
        assert "capability" in reason
        assert "task_type" in reason
        assert "objective" in reason


# =============================================================================
# Step 2: For testable agents, Octo generates TestContract structure
# =============================================================================

class TestStep2TestContractGeneration:
    """Test that Octo generates TestContract for testable agents."""

    def test_generate_test_contract_for_testable_agent(self, sample_agent_spec):
        """generate_test_contract should create contract for testable agents."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        assert isinstance(contract, TestContract)
        assert contract.agent_name == sample_agent_spec.name

    def test_no_contract_for_non_testable_agent(self, documentation_agent_spec):
        """generate_test_contract should return None for non-testable agents."""
        contract = generate_test_contract(
            agent_spec=documentation_agent_spec,
            capability="documentation",
        )

        assert contract is None

    def test_contract_has_required_fields(self, sample_agent_spec):
        """TestContract should have all required fields."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        assert contract.contract_id is not None
        assert contract.agent_name is not None
        assert contract.test_type is not None
        assert contract.test_type in TEST_TYPES
        assert isinstance(contract.assertions, list)
        assert isinstance(contract.pass_criteria, list)
        assert isinstance(contract.fail_criteria, list)
        assert contract.priority in (1, 2, 3, 4)

    def test_contract_validation_passes(self, sample_agent_spec):
        """Generated TestContract should pass validation."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        errors = contract.validate()
        assert len(errors) == 0, f"Validation errors: {errors}"


# =============================================================================
# Step 3: TestContract includes test_type, assertions, pass/fail criteria
# =============================================================================

class TestStep3TestContractStructure:
    """Test that TestContract has correct structure and content."""

    def test_test_type_inferred_from_capability(self):
        """Test type should be inferred from capability."""
        # Create specs for different capabilities
        e2e_spec = AgentSpec(
            id=generate_uuid(),
            name="e2e-agent",
            display_name="E2E Agent",
            spec_version="v1",
            objective="E2E testing",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": []},
            max_turns=50,
            timeout_seconds=1800,
        )

        api_spec = AgentSpec(
            id=generate_uuid(),
            name="api-agent",
            display_name="API Agent",
            spec_version="v1",
            objective="API testing",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": []},
            max_turns=50,
            timeout_seconds=1800,
        )

        # E2E capability -> e2e test type
        e2e_contract = generate_test_contract(e2e_spec, "e2e_testing")
        assert e2e_contract is not None
        assert e2e_contract.test_type == "e2e"

        # API capability -> api test type
        api_contract = generate_test_contract(api_spec, "api_testing")
        assert api_contract is not None
        assert api_contract.test_type == "api"

    def test_assertions_generated_for_capability(self, api_agent_spec):
        """Assertions should be generated based on capability."""
        contract = generate_test_contract(
            agent_spec=api_agent_spec,
            capability="api_testing",
        )

        assert contract is not None
        assert len(contract.assertions) > 0

        # Should have API-specific assertions
        assertion_targets = [a.target for a in contract.assertions]
        assert any("response" in t for t in assertion_targets)

    def test_assertion_structure(self, sample_agent_spec):
        """TestContractAssertion should have correct structure."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        for assertion in contract.assertions:
            assert isinstance(assertion, TestContractAssertion)
            assert assertion.description is not None
            assert assertion.target is not None
            assert assertion.expected is not None
            assert assertion.operator in ("eq", "ne", "gt", "lt", "ge", "le", "contains", "matches", "exists")

    def test_pass_criteria_generated(self, sample_agent_spec):
        """pass_criteria should be generated for the contract."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        assert len(contract.pass_criteria) > 0
        assert all(isinstance(c, str) for c in contract.pass_criteria)

    def test_fail_criteria_generated(self, sample_agent_spec):
        """fail_criteria should be generated for the contract."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        assert len(contract.fail_criteria) > 0
        assert all(isinstance(c, str) for c in contract.fail_criteria)

    def test_priority_inferred(self):
        """Priority should be inferred from capability."""
        # Security -> critical (1)
        security_spec = AgentSpec(
            id=generate_uuid(),
            name="security-agent",
            display_name="Security Agent",
            spec_version="v1",
            objective="Security scanning",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": []},
            max_turns=50,
            timeout_seconds=1800,
        )
        security_contract = generate_test_contract(security_spec, "security_testing")
        assert security_contract is not None
        assert security_contract.priority == 1

    def test_tags_generated(self, sample_agent_spec):
        """Tags should be generated for the contract."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        assert len(contract.tags) > 0
        assert "e2e_testing" in contract.tags or "testing" in contract.tags

    def test_contract_serialization(self, sample_agent_spec):
        """TestContract should serialize to dict correctly."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        contract_dict = contract.to_dict()

        assert "contract_id" in contract_dict
        assert "agent_name" in contract_dict
        assert "test_type" in contract_dict
        assert "assertions" in contract_dict
        assert "pass_criteria" in contract_dict
        assert "fail_criteria" in contract_dict
        assert "priority" in contract_dict
        assert "tags" in contract_dict

    def test_contract_deserialization(self, sample_agent_spec):
        """TestContract should deserialize from dict correctly."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        contract_dict = contract.to_dict()

        # Deserialize
        restored = TestContract.from_dict(contract_dict)

        assert restored.agent_name == contract.agent_name
        assert restored.test_type == contract.test_type
        assert len(restored.assertions) == len(contract.assertions)
        assert restored.pass_criteria == contract.pass_criteria
        assert restored.fail_criteria == contract.fail_criteria


# =============================================================================
# Step 4: TestContract linked to AgentSpec via agent_name
# =============================================================================

class TestStep4AgentNameLinking:
    """Test that TestContract is linked to AgentSpec via agent_name."""

    def test_agent_name_matches_spec(self, sample_agent_spec):
        """TestContract.agent_name should match AgentSpec.name."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None
        assert contract.agent_name == sample_agent_spec.name

    def test_octo_generates_linked_contracts(self, sample_payload):
        """Octo should generate contracts linked to their specs."""
        spec1 = AgentSpec(
            id=generate_uuid(),
            name="e2e-test-agent",
            display_name="E2E Test Agent",
            spec_version="v1",
            objective="E2E testing",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["browser_navigate", "browser_click", "browser_type"],
                "forbidden_patterns": [],
            },
            max_turns=50,
            timeout_seconds=1800,
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=spec1,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        assert response.success is True

        # Each contract should be linked to a spec
        for contract in response.test_contracts:
            spec_names = [s.name for s in response.agent_specs]
            assert contract.agent_name in spec_names

    def test_multiple_specs_have_separate_contracts(self, sample_payload):
        """Multiple specs should have separate linked contracts."""
        spec1 = AgentSpec(
            id=generate_uuid(),
            name="e2e-test-agent",
            display_name="E2E Test Agent",
            spec_version="v1",
            objective="E2E testing",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["browser_navigate", "browser_click"],
                "forbidden_patterns": [],
            },
            max_turns=50,
            timeout_seconds=1800,
        )
        spec2 = AgentSpec(
            id=generate_uuid(),
            name="api-test-agent",
            display_name="API Test Agent",
            spec_version="v1",
            objective="API testing",
            task_type="testing",
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["Read", "Write", "WebFetch"],
                "forbidden_patterns": [],
            },
            max_turns=50,
            timeout_seconds=1800,
        )

        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.side_effect = [
            BuildResult(success=True, agent_spec=spec1),
            BuildResult(success=True, agent_spec=spec2),
        ]

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        assert response.success is True
        assert len(response.agent_specs) == 2
        assert len(response.test_contracts) == 2

        # Each contract should link to different spec
        contract_names = [c.agent_name for c in response.test_contracts]
        assert spec1.name in contract_names
        assert spec2.name in contract_names


# =============================================================================
# Step 5: TestContract is structured data, not test code
# =============================================================================

class TestStep5StructuredData:
    """Test that TestContract is structured data, not executable code."""

    def test_contract_is_data_not_code(self, sample_agent_spec):
        """TestContract should be declarative data, not code."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None

        # All fields should be primitive types or lists of primitives
        assert isinstance(contract.agent_name, str)
        assert isinstance(contract.test_type, str)
        assert isinstance(contract.description, str)
        assert isinstance(contract.priority, int)
        assert all(isinstance(t, str) for t in contract.tags)
        assert all(isinstance(c, str) for c in contract.pass_criteria)
        assert all(isinstance(c, str) for c in contract.fail_criteria)

    def test_assertions_are_declarative(self, sample_agent_spec):
        """Assertions should be declarative descriptions, not code."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None

        for assertion in contract.assertions:
            # Should be descriptive strings, not code
            assert isinstance(assertion.description, str)
            assert isinstance(assertion.target, str)
            assert isinstance(assertion.operator, str)
            # Expected can be various types but should be serializable
            json.dumps(assertion.expected)  # Should not raise

    def test_contract_is_json_serializable(self, sample_agent_spec):
        """TestContract should be fully JSON serializable."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
        )

        assert contract is not None

        # Should serialize without errors
        contract_dict = contract.to_dict()
        json_str = json.dumps(contract_dict)
        assert len(json_str) > 0

        # Should round-trip
        restored_dict = json.loads(json_str)
        assert restored_dict == contract_dict

    def test_contract_validation_errors(self):
        """TestContract validation should catch structural errors."""
        # Missing agent_name
        contract = TestContract(
            agent_name="",
            test_type="unit",
            pass_criteria=["test passes"],
        )
        errors = contract.validate()
        assert "agent_name is required" in errors

        # Invalid test_type
        contract = TestContract(
            agent_name="test-agent",
            test_type="invalid_type",
            pass_criteria=["test passes"],
        )
        errors = contract.validate()
        assert any("test_type must be one of" in e for e in errors)

        # Missing both assertions and pass_criteria
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            assertions=[],
            pass_criteria=[],
        )
        errors = contract.validate()
        assert any("assertions or pass_criteria" in e for e in errors)

        # Invalid priority
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            pass_criteria=["test passes"],
            priority=5,  # Invalid
        )
        errors = contract.validate()
        assert any("priority must be" in e for e in errors)


# =============================================================================
# OctoResponse TestContract Integration
# =============================================================================

class TestOctoResponseIntegration:
    """Test OctoResponse includes test_contracts correctly."""

    def test_response_includes_test_contracts(self, sample_payload, sample_agent_spec):
        """OctoResponse should include test_contracts field."""
        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=sample_agent_spec,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        assert hasattr(response, "test_contracts")
        assert isinstance(response.test_contracts, list)

    def test_response_to_dict_includes_contracts(self, sample_payload, sample_agent_spec):
        """OctoResponse.to_dict should include test_contracts."""
        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=sample_agent_spec,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)
        response_dict = response.to_dict()

        assert "test_contracts" in response_dict
        assert isinstance(response_dict["test_contracts"], list)

    def test_contracts_serialized_correctly(self, sample_payload, sample_agent_spec):
        """TestContracts in response should be serialized correctly."""
        mock_builder = MagicMock(spec=SpecBuilder)
        mock_builder.build.return_value = BuildResult(
            success=True,
            agent_spec=sample_agent_spec,
        )

        octo = Octo(spec_builder=mock_builder)
        response = octo.generate_specs(sample_payload)

        if response.test_contracts:
            response_dict = response.to_dict()
            for contract_dict in response_dict["test_contracts"]:
                assert "contract_id" in contract_dict
                assert "agent_name" in contract_dict
                assert "test_type" in contract_dict
                assert "assertions" in contract_dict

    def test_failed_response_has_empty_contracts(self):
        """Failed response should have empty test_contracts list."""
        invalid_payload = OctoRequestPayload(
            project_context="not a dict",  # type: ignore
            required_capabilities=[],
        )

        octo = Octo()
        response = octo.generate_specs(invalid_payload)

        assert response.success is False
        assert response.test_contracts == []


# =============================================================================
# TestContractAssertion Tests
# =============================================================================

class TestTestContractAssertion:
    """Test TestContractAssertion data class."""

    def test_assertion_creation(self):
        """TestContractAssertion should be creatable with required fields."""
        assertion = TestContractAssertion(
            description="Response status is 200",
            target="response.status_code",
            expected=200,
        )

        assert assertion.description == "Response status is 200"
        assert assertion.target == "response.status_code"
        assert assertion.expected == 200
        assert assertion.operator == "eq"  # Default

    def test_assertion_with_operator(self):
        """TestContractAssertion should accept different operators."""
        assertion = TestContractAssertion(
            description="Error count is zero",
            target="errors.count",
            expected=0,
            operator="eq",
        )
        assert assertion.operator == "eq"

        assertion = TestContractAssertion(
            description="Response contains success",
            target="response.body",
            expected="success",
            operator="contains",
        )
        assert assertion.operator == "contains"

    def test_assertion_to_dict(self):
        """TestContractAssertion.to_dict should serialize correctly."""
        assertion = TestContractAssertion(
            description="Test assertion",
            target="test.target",
            expected=True,
            operator="eq",
        )

        d = assertion.to_dict()
        assert d["description"] == "Test assertion"
        assert d["target"] == "test.target"
        assert d["expected"] is True
        assert d["operator"] == "eq"

    def test_assertion_from_dict(self):
        """TestContractAssertion.from_dict should deserialize correctly."""
        data = {
            "description": "Test assertion",
            "target": "test.target",
            "expected": 100,
            "operator": "gt",
        }

        assertion = TestContractAssertion.from_dict(data)
        assert assertion.description == "Test assertion"
        assert assertion.target == "test.target"
        assert assertion.expected == 100
        assert assertion.operator == "gt"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_capability(self, sample_agent_spec):
        """generate_test_contract should handle empty capability."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="",
        )
        # Still testable via task_type (testing) and objective
        assert contract is not None

    def test_none_project_context(self, sample_agent_spec):
        """generate_test_contract should handle None project_context."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="e2e_testing",
            project_context=None,
        )
        assert contract is not None

    def test_all_test_types_valid(self):
        """All TEST_TYPES should be valid for TestContract."""
        for test_type in TEST_TYPES:
            contract = TestContract(
                agent_name="test-agent",
                test_type=test_type,
                pass_criteria=["test passes"],
            )
            errors = contract.validate()
            assert len(errors) == 0, f"Test type {test_type} failed validation: {errors}"

    def test_testable_capabilities_coverage(self):
        """TESTABLE_CAPABILITIES should cover common testing patterns."""
        required_capabilities = {
            "e2e_testing",
            "api_testing",
            "unit_testing",
            "integration_testing",
            "coding",
            "refactoring",
        }
        assert required_capabilities.issubset(TESTABLE_CAPABILITIES)

    def test_testable_task_types_coverage(self):
        """TESTABLE_TASK_TYPES should cover primary task types."""
        assert "coding" in TESTABLE_TASK_TYPES
        assert "testing" in TESTABLE_TASK_TYPES
        assert "refactoring" in TESTABLE_TASK_TYPES

    def test_testable_keywords_coverage(self):
        """TESTABLE_OBJECTIVE_KEYWORDS should cover common action verbs."""
        required_keywords = {"implement", "create", "build", "test", "fix", "refactor"}
        assert required_keywords.issubset(set(TESTABLE_OBJECTIVE_KEYWORDS))
