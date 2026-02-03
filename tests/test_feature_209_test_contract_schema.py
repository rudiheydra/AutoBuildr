"""
Test Feature #209: TestContract schema defined and documented
==============================================================

This test suite verifies that the TestContract schema includes all required fields
and is properly documented and validated.

Feature Steps:
1. TestContract includes: test_name, test_type (unit/integration/e2e)
2. Includes: subject (what to test), assertions (expected behaviors)
3. Includes: pass_criteria, fail_criteria
4. Includes: dependencies (fixtures, mocks needed)
5. Schema documented and validated
"""
import json
import pytest
from unittest.mock import MagicMock

from api.octo import (
    # Core classes
    TestContract,
    TestContractAssertion,
    TestDependency,
    # Constants
    TEST_TYPES,
    DEPENDENCY_TYPES,
    # Functions
    generate_test_contract,
    _generate_test_name,
    _generate_subject,
    _generate_dependencies,
)
from api.octo_schemas import (
    # Schemas
    TEST_CONTRACT_SCHEMA,
    TEST_CONTRACT_ASSERTION_SCHEMA,
    TEST_DEPENDENCY_SCHEMA,
    # Validation functions
    validate_test_contract_schema,
    # Constants
    VALID_TEST_TYPES,
    VALID_DEPENDENCY_TYPES,
)
from api.agentspec_models import AgentSpec, generate_uuid


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_agent_spec():
    """Create a sample AgentSpec for testing."""
    return AgentSpec(
        id=generate_uuid(),
        name="test-api-agent",
        display_name="Test API Agent",
        icon="api",
        spec_version="v1",
        objective="Implement API endpoint tests for user authentication",
        task_type="testing",
        context={"capability": "api_testing", "feature_id": 42},
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
def e2e_agent_spec():
    """Create an E2E testing AgentSpec."""
    return AgentSpec(
        id=generate_uuid(),
        name="test-e2e-agent",
        display_name="E2E Test Agent",
        icon="browser",
        spec_version="v1",
        objective="Implement end-to-end tests for user login flow",
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
def sample_dependency():
    """Create a sample TestDependency."""
    return TestDependency(
        name="test_database",
        dependency_type="database",
        description="Test database with seed data",
        setup_hints=["Run migrations", "Load fixtures"],
        required=True,
    )


@pytest.fixture
def sample_contract(sample_agent_spec):
    """Create a sample TestContract with all fields populated."""
    return TestContract(
        agent_name=sample_agent_spec.name,
        test_type="api",
        test_name="API Authentication Tests",
        subject="User authentication API endpoints",
        assertions=[
            TestContractAssertion(
                description="Login endpoint returns 200",
                target="response.status_code",
                expected=200,
                operator="eq",
            ),
        ],
        pass_criteria=["All API endpoints return valid responses"],
        fail_criteria=["API returns 500 error"],
        dependencies=[
            TestDependency(
                name="api_server",
                dependency_type="service",
                description="Running API server",
                setup_hints=["Start development server"],
                required=True,
            ),
        ],
        description="Test contract for API authentication",
        priority=2,
        tags=["api", "auth"],
    )


# =============================================================================
# Step 1: TestContract includes test_name, test_type (unit/integration/e2e)
# =============================================================================

class TestStep1TestNameAndType:
    """Test that TestContract includes test_name and test_type fields."""

    def test_test_contract_has_test_name_field(self, sample_contract):
        """TestContract should have a test_name field."""
        assert hasattr(sample_contract, "test_name")
        assert sample_contract.test_name == "API Authentication Tests"

    def test_test_contract_has_test_type_field(self, sample_contract):
        """TestContract should have a test_type field."""
        assert hasattr(sample_contract, "test_type")
        assert sample_contract.test_type == "api"

    def test_test_type_values_include_unit_integration_e2e(self):
        """TEST_TYPES should include unit, integration, and e2e."""
        assert "unit" in TEST_TYPES
        assert "integration" in TEST_TYPES
        assert "e2e" in TEST_TYPES

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

    def test_test_name_in_to_dict(self, sample_contract):
        """test_name should be included in to_dict output."""
        contract_dict = sample_contract.to_dict()
        assert "test_name" in contract_dict
        assert contract_dict["test_name"] == "API Authentication Tests"

    def test_test_name_from_dict(self):
        """TestContract.from_dict should restore test_name."""
        data = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "test_name": "My Unit Tests",
            "pass_criteria": ["test passes"],
        }
        contract = TestContract.from_dict(data)
        assert contract.test_name == "My Unit Tests"

    def test_generate_test_name_function(self, sample_agent_spec):
        """_generate_test_name should create human-readable test names."""
        test_name = _generate_test_name("api_testing", sample_agent_spec)
        assert test_name is not None
        assert len(test_name) > 0
        assert "Api Testing" in test_name or "api testing" in test_name.lower()


# =============================================================================
# Step 2: Includes subject (what to test), assertions (expected behaviors)
# =============================================================================

class TestStep2SubjectAndAssertions:
    """Test that TestContract includes subject and assertions fields."""

    def test_test_contract_has_subject_field(self, sample_contract):
        """TestContract should have a subject field."""
        assert hasattr(sample_contract, "subject")
        assert sample_contract.subject == "User authentication API endpoints"

    def test_test_contract_has_assertions_field(self, sample_contract):
        """TestContract should have an assertions field."""
        assert hasattr(sample_contract, "assertions")
        assert len(sample_contract.assertions) > 0
        assert isinstance(sample_contract.assertions[0], TestContractAssertion)

    def test_subject_in_to_dict(self, sample_contract):
        """subject should be included in to_dict output."""
        contract_dict = sample_contract.to_dict()
        assert "subject" in contract_dict
        assert contract_dict["subject"] == "User authentication API endpoints"

    def test_subject_from_dict(self):
        """TestContract.from_dict should restore subject."""
        data = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "subject": "User login component",
            "pass_criteria": ["test passes"],
        }
        contract = TestContract.from_dict(data)
        assert contract.subject == "User login component"

    def test_assertions_describe_expected_behaviors(self, sample_contract):
        """Assertions should describe expected behaviors."""
        for assertion in sample_contract.assertions:
            assert assertion.description, "Assertion must have a description"
            assert assertion.target, "Assertion must have a target"
            assert assertion.expected is not None, "Assertion must have an expected value"

    def test_generate_subject_function_api(self, sample_agent_spec):
        """_generate_subject should generate appropriate subject for API testing."""
        subject = _generate_subject("api_testing", sample_agent_spec)
        assert subject is not None
        assert len(subject) > 0
        assert "api" in subject.lower() or "endpoint" in subject.lower()

    def test_generate_subject_function_e2e(self, e2e_agent_spec):
        """_generate_subject should generate appropriate subject for E2E testing."""
        subject = _generate_subject("e2e_testing", e2e_agent_spec)
        assert subject is not None
        assert "interface" in subject.lower() or "ui" in subject.lower() or "page" in subject.lower()


# =============================================================================
# Step 3: Includes pass_criteria, fail_criteria
# =============================================================================

class TestStep3PassFailCriteria:
    """Test that TestContract includes pass_criteria and fail_criteria."""

    def test_test_contract_has_pass_criteria(self, sample_contract):
        """TestContract should have a pass_criteria field."""
        assert hasattr(sample_contract, "pass_criteria")
        assert len(sample_contract.pass_criteria) > 0
        assert all(isinstance(c, str) for c in sample_contract.pass_criteria)

    def test_test_contract_has_fail_criteria(self, sample_contract):
        """TestContract should have a fail_criteria field."""
        assert hasattr(sample_contract, "fail_criteria")
        assert len(sample_contract.fail_criteria) > 0
        assert all(isinstance(c, str) for c in sample_contract.fail_criteria)

    def test_pass_criteria_in_to_dict(self, sample_contract):
        """pass_criteria should be included in to_dict output."""
        contract_dict = sample_contract.to_dict()
        assert "pass_criteria" in contract_dict
        assert isinstance(contract_dict["pass_criteria"], list)

    def test_fail_criteria_in_to_dict(self, sample_contract):
        """fail_criteria should be included in to_dict output."""
        contract_dict = sample_contract.to_dict()
        assert "fail_criteria" in contract_dict
        assert isinstance(contract_dict["fail_criteria"], list)

    def test_at_least_assertions_or_pass_criteria_required(self):
        """TestContract must have either assertions or pass_criteria."""
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            assertions=[],
            pass_criteria=[],
        )
        errors = contract.validate()
        assert any("assertions or pass_criteria" in e for e in errors)

    def test_pass_criteria_only_is_valid(self):
        """TestContract with only pass_criteria (no assertions) is valid."""
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            assertions=[],
            pass_criteria=["test passes"],
        )
        errors = contract.validate()
        assert len(errors) == 0


# =============================================================================
# Step 4: Includes dependencies (fixtures, mocks needed)
# =============================================================================

class TestStep4Dependencies:
    """Test that TestContract includes dependencies field."""

    def test_test_contract_has_dependencies_field(self, sample_contract):
        """TestContract should have a dependencies field."""
        assert hasattr(sample_contract, "dependencies")
        assert len(sample_contract.dependencies) > 0
        assert isinstance(sample_contract.dependencies[0], TestDependency)

    def test_dependency_has_required_fields(self, sample_dependency):
        """TestDependency should have all required fields."""
        assert sample_dependency.name == "test_database"
        assert sample_dependency.dependency_type == "database"
        assert sample_dependency.description == "Test database with seed data"
        assert "Run migrations" in sample_dependency.setup_hints
        assert sample_dependency.required is True

    def test_dependency_types_include_fixtures_mocks(self):
        """DEPENDENCY_TYPES should include fixture and mock."""
        assert "fixture" in DEPENDENCY_TYPES
        assert "mock" in DEPENDENCY_TYPES
        assert "service" in DEPENDENCY_TYPES
        assert "database" in DEPENDENCY_TYPES

    def test_dependencies_in_to_dict(self, sample_contract):
        """dependencies should be included in to_dict output."""
        contract_dict = sample_contract.to_dict()
        assert "dependencies" in contract_dict
        assert isinstance(contract_dict["dependencies"], list)
        assert len(contract_dict["dependencies"]) > 0

    def test_dependency_to_dict(self, sample_dependency):
        """TestDependency.to_dict should serialize correctly."""
        dep_dict = sample_dependency.to_dict()
        assert dep_dict["name"] == "test_database"
        assert dep_dict["dependency_type"] == "database"
        assert dep_dict["description"] == "Test database with seed data"
        assert "Run migrations" in dep_dict["setup_hints"]
        assert dep_dict["required"] is True

    def test_dependency_from_dict(self):
        """TestDependency.from_dict should restore all fields."""
        data = {
            "name": "user_fixture",
            "dependency_type": "fixture",
            "description": "User test data",
            "setup_hints": ["Create test users"],
            "required": False,
        }
        dep = TestDependency.from_dict(data)
        assert dep.name == "user_fixture"
        assert dep.dependency_type == "fixture"
        assert dep.description == "User test data"
        assert dep.setup_hints == ["Create test users"]
        assert dep.required is False

    def test_dependencies_from_dict_in_contract(self):
        """TestContract.from_dict should restore dependencies."""
        data = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "pass_criteria": ["test passes"],
            "dependencies": [
                {
                    "name": "mock_api",
                    "dependency_type": "mock",
                    "description": "Mock API server",
                    "setup_hints": [],
                    "required": True,
                },
            ],
        }
        contract = TestContract.from_dict(data)
        assert len(contract.dependencies) == 1
        assert contract.dependencies[0].name == "mock_api"
        assert contract.dependencies[0].dependency_type == "mock"

    def test_generate_dependencies_function_api(self, sample_agent_spec):
        """_generate_dependencies should generate API-specific dependencies."""
        deps = _generate_dependencies("api_testing", sample_agent_spec, None)
        assert len(deps) > 0
        dep_types = [d.dependency_type for d in deps]
        dep_names = [d.name for d in deps]
        # Should have service and database dependencies for API testing
        assert "service" in dep_types or "database" in dep_types
        assert any("server" in n or "database" in n for n in dep_names)

    def test_generate_dependencies_function_e2e(self, e2e_agent_spec):
        """_generate_dependencies should generate E2E-specific dependencies."""
        deps = _generate_dependencies("e2e_testing", e2e_agent_spec, None)
        assert len(deps) > 0
        dep_names = [d.name for d in deps]
        # Should have browser automation dependency
        assert any("browser" in n.lower() for n in dep_names)

    def test_dependency_validation_valid(self, sample_dependency):
        """Valid TestDependency should pass validation."""
        errors = sample_dependency.validate()
        assert len(errors) == 0

    def test_dependency_validation_missing_name(self):
        """TestDependency without name should fail validation."""
        dep = TestDependency(
            name="",
            dependency_type="fixture",
        )
        errors = dep.validate()
        assert any("name is required" in e for e in errors)

    def test_dependency_validation_invalid_type(self):
        """TestDependency with invalid type should fail validation."""
        dep = TestDependency(
            name="test_dep",
            dependency_type="invalid_type",
        )
        errors = dep.validate()
        assert any("dependency_type must be one of" in e for e in errors)


# =============================================================================
# Step 5: Schema documented and validated
# =============================================================================

class TestStep5SchemaDocumentedValidated:
    """Test that the schema is documented and validated."""

    def test_test_contract_schema_exists(self):
        """TEST_CONTRACT_SCHEMA should be defined."""
        assert TEST_CONTRACT_SCHEMA is not None
        assert isinstance(TEST_CONTRACT_SCHEMA, dict)

    def test_test_dependency_schema_exists(self):
        """TEST_DEPENDENCY_SCHEMA should be defined."""
        assert TEST_DEPENDENCY_SCHEMA is not None
        assert isinstance(TEST_DEPENDENCY_SCHEMA, dict)

    def test_schema_has_test_name_field(self):
        """Schema should define test_name field."""
        properties = TEST_CONTRACT_SCHEMA.get("properties", {})
        assert "test_name" in properties
        assert properties["test_name"].get("type") == "string"

    def test_schema_has_subject_field(self):
        """Schema should define subject field."""
        properties = TEST_CONTRACT_SCHEMA.get("properties", {})
        assert "subject" in properties
        assert properties["subject"].get("type") == "string"

    def test_schema_has_dependencies_field(self):
        """Schema should define dependencies field."""
        properties = TEST_CONTRACT_SCHEMA.get("properties", {})
        assert "dependencies" in properties
        assert properties["dependencies"].get("type") == "array"

    def test_dependency_schema_has_required_fields(self):
        """TEST_DEPENDENCY_SCHEMA should define required fields."""
        required = TEST_DEPENDENCY_SCHEMA.get("required", [])
        assert "name" in required
        assert "dependency_type" in required

    def test_dependency_schema_has_all_fields(self):
        """TEST_DEPENDENCY_SCHEMA should define all fields."""
        properties = TEST_DEPENDENCY_SCHEMA.get("properties", {})
        assert "name" in properties
        assert "dependency_type" in properties
        assert "description" in properties
        assert "setup_hints" in properties
        assert "required" in properties

    def test_schema_validation_passes_valid_contract(self, sample_contract):
        """validate_test_contract_schema should pass for valid contract."""
        contract_dict = sample_contract.to_dict()
        result = validate_test_contract_schema(contract_dict)
        assert result.is_valid, f"Validation errors: {result.error_messages}"

    def test_schema_validation_fails_invalid_type(self):
        """validate_test_contract_schema should fail for invalid test_type."""
        data = {
            "agent_name": "test-agent",
            "test_type": "invalid_type",
            "pass_criteria": ["test passes"],
        }
        result = validate_test_contract_schema(data)
        assert not result.is_valid
        assert any("test_type" in e.path for e in result.errors)

    def test_schema_validation_fails_invalid_dependency_type(self):
        """validate_test_contract_schema should fail for invalid dependency_type."""
        data = {
            "agent_name": "test-agent",
            "test_type": "unit",
            "pass_criteria": ["test passes"],
            "dependencies": [
                {
                    "name": "test_dep",
                    "dependency_type": "invalid_type",
                }
            ],
        }
        result = validate_test_contract_schema(data)
        assert not result.is_valid
        assert any("dependency_type" in e.message for e in result.errors)

    def test_test_contract_docstring_documents_fields(self):
        """TestContract docstring should document all required fields."""
        docstring = TestContract.__doc__
        assert docstring is not None
        # Check that key fields are documented
        assert "test_name" in docstring
        assert "test_type" in docstring
        assert "subject" in docstring
        assert "assertions" in docstring
        assert "pass_criteria" in docstring
        assert "fail_criteria" in docstring
        assert "dependencies" in docstring

    def test_test_dependency_docstring_documents_fields(self):
        """TestDependency docstring should document all fields."""
        docstring = TestDependency.__doc__
        assert docstring is not None
        assert "name" in docstring
        assert "dependency_type" in docstring
        assert "description" in docstring
        assert "setup_hints" in docstring

    def test_schema_is_json_serializable(self):
        """Schemas should be JSON serializable."""
        # These should not raise
        json.dumps(TEST_CONTRACT_SCHEMA)
        json.dumps(TEST_DEPENDENCY_SCHEMA)
        json.dumps(TEST_CONTRACT_ASSERTION_SCHEMA)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for TestContract generation."""

    def test_generate_test_contract_includes_all_fields(self, sample_agent_spec):
        """generate_test_contract should populate all new fields."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="api_testing",
        )

        assert contract is not None
        # Feature #209 fields
        assert contract.test_name, "test_name should be populated"
        assert contract.subject, "subject should be populated"
        # dependencies is optional but should be a list
        assert isinstance(contract.dependencies, list)

    def test_generated_contract_passes_validation(self, sample_agent_spec):
        """Generated TestContract should pass validation."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="api_testing",
        )

        assert contract is not None
        errors = contract.validate()
        assert len(errors) == 0, f"Validation errors: {errors}"

    def test_generated_contract_schema_validation(self, sample_agent_spec):
        """Generated TestContract should pass schema validation."""
        contract = generate_test_contract(
            agent_spec=sample_agent_spec,
            capability="api_testing",
        )

        assert contract is not None
        contract_dict = contract.to_dict()
        result = validate_test_contract_schema(contract_dict)
        assert result.is_valid, f"Schema validation errors: {result.error_messages}"

    def test_contract_round_trip_serialization(self, sample_contract):
        """TestContract should survive serialization round-trip."""
        # Serialize
        contract_dict = sample_contract.to_dict()
        json_str = json.dumps(contract_dict)

        # Deserialize
        restored_dict = json.loads(json_str)
        restored = TestContract.from_dict(restored_dict)

        # Verify all fields
        assert restored.test_name == sample_contract.test_name
        assert restored.test_type == sample_contract.test_type
        assert restored.subject == sample_contract.subject
        assert restored.agent_name == sample_contract.agent_name
        assert restored.pass_criteria == sample_contract.pass_criteria
        assert restored.fail_criteria == sample_contract.fail_criteria
        assert len(restored.assertions) == len(sample_contract.assertions)
        assert len(restored.dependencies) == len(sample_contract.dependencies)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_test_name_allowed(self):
        """Empty test_name should be allowed (optional field)."""
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            test_name="",
            pass_criteria=["test passes"],
        )
        errors = contract.validate()
        assert len(errors) == 0

    def test_empty_subject_allowed(self):
        """Empty subject should be allowed (optional field)."""
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            subject="",
            pass_criteria=["test passes"],
        )
        errors = contract.validate()
        assert len(errors) == 0

    def test_empty_dependencies_allowed(self):
        """Empty dependencies list should be allowed."""
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            pass_criteria=["test passes"],
            dependencies=[],
        )
        errors = contract.validate()
        assert len(errors) == 0

    def test_invalid_dependency_in_contract_fails_validation(self):
        """Contract with invalid dependency should fail validation."""
        contract = TestContract(
            agent_name="test-agent",
            test_type="unit",
            pass_criteria=["test passes"],
            dependencies=[
                TestDependency(
                    name="",  # Invalid: empty name
                    dependency_type="fixture",
                ),
            ],
        )
        errors = contract.validate()
        assert len(errors) > 0
        assert any("dependencies[0]" in e for e in errors)

    def test_all_dependency_types_valid(self):
        """All DEPENDENCY_TYPES should be valid for TestDependency."""
        for dep_type in DEPENDENCY_TYPES:
            dep = TestDependency(
                name="test_dep",
                dependency_type=dep_type,
            )
            errors = dep.validate()
            assert len(errors) == 0, f"Dependency type {dep_type} failed validation: {errors}"

    def test_dependency_with_project_context(self, sample_agent_spec):
        """_generate_dependencies should use project context for tech-specific deps."""
        project_context = {
            "tech_stack": ["python", "fastapi"],
        }
        deps = _generate_dependencies("api_testing", sample_agent_spec, project_context)
        dep_names = [d.name for d in deps]
        # Should have some dependencies
        assert len(deps) > 0


# =============================================================================
# Feature Verification Steps
# =============================================================================

class TestFeature209VerificationSteps:
    """Tests that verify each feature step."""

    def test_step1_test_name_and_test_type(self, sample_contract):
        """
        Step 1: TestContract includes: test_name, test_type (unit/integration/e2e)
        """
        # test_name exists and is a string
        assert isinstance(sample_contract.test_name, str)

        # test_type exists and includes unit/integration/e2e
        assert sample_contract.test_type in TEST_TYPES
        assert "unit" in TEST_TYPES
        assert "integration" in TEST_TYPES
        assert "e2e" in TEST_TYPES

    def test_step2_subject_and_assertions(self, sample_contract):
        """
        Step 2: Includes: subject (what to test), assertions (expected behaviors)
        """
        # subject exists and describes what to test
        assert isinstance(sample_contract.subject, str)

        # assertions exist and describe expected behaviors
        assert isinstance(sample_contract.assertions, list)
        for assertion in sample_contract.assertions:
            assert assertion.description  # Describes the expected behavior
            assert assertion.target  # What is being tested
            assert assertion.expected is not None  # Expected value

    def test_step3_pass_fail_criteria(self, sample_contract):
        """
        Step 3: Includes: pass_criteria, fail_criteria
        """
        # pass_criteria exists and is a list of strings
        assert isinstance(sample_contract.pass_criteria, list)
        assert all(isinstance(c, str) for c in sample_contract.pass_criteria)

        # fail_criteria exists and is a list of strings
        assert isinstance(sample_contract.fail_criteria, list)
        assert all(isinstance(c, str) for c in sample_contract.fail_criteria)

    def test_step4_dependencies(self, sample_contract):
        """
        Step 4: Includes: dependencies (fixtures, mocks needed)
        """
        # dependencies exists and is a list
        assert isinstance(sample_contract.dependencies, list)

        # Each dependency has required fields
        for dep in sample_contract.dependencies:
            assert isinstance(dep, TestDependency)
            assert dep.name  # Name of the dependency
            assert dep.dependency_type in DEPENDENCY_TYPES  # Type (fixture, mock, etc.)

        # DEPENDENCY_TYPES includes fixtures and mocks
        assert "fixture" in DEPENDENCY_TYPES
        assert "mock" in DEPENDENCY_TYPES

    def test_step5_schema_documented_and_validated(self, sample_contract):
        """
        Step 5: Schema documented and validated
        """
        # Schema is documented (has description)
        assert TEST_CONTRACT_SCHEMA.get("description")
        assert TEST_DEPENDENCY_SCHEMA.get("description")

        # TestContract docstring documents the schema
        assert TestContract.__doc__
        assert "test_name" in TestContract.__doc__
        assert "subject" in TestContract.__doc__
        assert "dependencies" in TestContract.__doc__

        # Validation works
        contract_dict = sample_contract.to_dict()
        result = validate_test_contract_schema(contract_dict)
        assert result.is_valid

        # Invalid data fails validation
        invalid_data = {"agent_name": "test"}  # Missing required fields
        result = validate_test_contract_schema(invalid_data)
        assert not result.is_valid
