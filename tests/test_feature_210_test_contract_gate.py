"""
Tests for Feature #210: Feature cannot pass without tests passing

This module tests the TestContractGate implementation which:
1. Feature with TestContract must have tests written
2. Tests must execute successfully (exit code 0)
3. All assertions in TestContract must be covered
4. Acceptance gate blocks completion if tests fail
5. Gate is enforceable via configuration
"""

import pytest
from datetime import datetime, timezone

from api.test_contract_gate import (
    TestGateStatus,
    TestGateConfiguration,
    AssertionCoverage,
    TestContractCoverage,
    TestGateResult,
    TestContractGate,
    get_test_contract_gate,
    reset_test_contract_gate,
    evaluate_test_gate,
    check_tests_required,
    get_blocking_test_issues,
    DEFAULT_ENFORCE_TEST_GATE,
    DEFAULT_REQUIRE_ALL_ASSERTIONS,
    DEFAULT_MIN_TEST_COVERAGE,
    DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_test_contract():
    """Sample TestContract for testing."""
    return {
        "contract_id": "contract-123",
        "agent_name": "feature-impl-agent",
        "test_type": "unit",
        "assertions": [
            {
                "description": "Response status code is 200",
                "target": "response.status_code",
                "expected": 200,
                "operator": "eq",
            },
            {
                "description": "Response contains user data",
                "target": "response.body.user",
                "expected": "exists",
                "operator": "exists",
            },
        ],
        "pass_criteria": [
            "All unit tests pass",
            "No exceptions raised",
        ],
    }


@pytest.fixture
def sample_test_result_passing():
    """Sample passing test result."""
    return {
        "contract_id": "contract-123",
        "agent_name": "feature-impl-agent",
        "passed": True,
        "exit_code": 0,
        "total_tests": 5,
        "passed_tests": 5,
        "failed_tests": 0,
        "stdout": "All tests passed. response.status_code verified.",
        "stderr": "",
        "covered_assertions": [
            {
                "target": "response.status_code",
                "passed": True,
            },
            {
                "target": "response.body.user",
                "passed": True,
            },
        ],
    }


@pytest.fixture
def sample_test_result_failing():
    """Sample failing test result."""
    return {
        "contract_id": "contract-123",
        "agent_name": "feature-impl-agent",
        "passed": False,
        "exit_code": 1,
        "total_tests": 5,
        "passed_tests": 3,
        "failed_tests": 2,
        "stdout": "Some tests failed",
        "stderr": "AssertionError: expected 200, got 500",
        "covered_assertions": [
            {
                "target": "response.status_code",
                "passed": False,
                "error_message": "expected 200, got 500",
            },
        ],
    }


@pytest.fixture(autouse=True)
def reset_gate_cache():
    """Reset the gate cache before each test."""
    reset_test_contract_gate()
    yield
    reset_test_contract_gate()


# =============================================================================
# TestGateStatus Tests
# =============================================================================

class TestTestGateStatus:
    """Tests for TestGateStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        assert TestGateStatus.PASSED == "passed"
        assert TestGateStatus.FAILED == "failed"
        assert TestGateStatus.NO_TESTS == "no_tests"
        assert TestGateStatus.NO_CONTRACT == "no_contract"
        assert TestGateStatus.SKIPPED == "skipped"
        assert TestGateStatus.ERROR == "error"

    def test_status_str_conversion(self):
        """Test string conversion of status values."""
        assert str(TestGateStatus.PASSED) == "passed"
        assert str(TestGateStatus.FAILED) == "failed"


# =============================================================================
# TestGateConfiguration Tests
# =============================================================================

class TestTestGateConfiguration:
    """Tests for TestGateConfiguration data class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TestGateConfiguration()
        assert config.enforce_test_gate == DEFAULT_ENFORCE_TEST_GATE
        assert config.require_all_assertions == DEFAULT_REQUIRE_ALL_ASSERTIONS
        assert config.min_test_coverage == DEFAULT_MIN_TEST_COVERAGE
        assert config.allow_skip_for_no_contract == DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT
        assert config.timeout_seconds == 300
        assert config.max_retries == 1

    def test_custom_values(self):
        """Test custom configuration values."""
        config = TestGateConfiguration(
            enforce_test_gate=False,
            require_all_assertions=False,
            min_test_coverage=80.0,
            allow_skip_for_no_contract=False,
            timeout_seconds=600,
            max_retries=3,
        )
        assert config.enforce_test_gate is False
        assert config.require_all_assertions is False
        assert config.min_test_coverage == 80.0
        assert config.allow_skip_for_no_contract is False
        assert config.timeout_seconds == 600
        assert config.max_retries == 3

    def test_to_dict(self):
        """Test configuration serialization."""
        config = TestGateConfiguration(min_test_coverage=50.0)
        data = config.to_dict()
        assert data["enforce_test_gate"] is True
        assert data["min_test_coverage"] == 50.0

    def test_from_dict(self):
        """Test configuration deserialization."""
        data = {
            "enforce_test_gate": False,
            "min_test_coverage": 75.0,
        }
        config = TestGateConfiguration.from_dict(data)
        assert config.enforce_test_gate is False
        assert config.min_test_coverage == 75.0


# =============================================================================
# AssertionCoverage Tests
# =============================================================================

class TestAssertionCoverage:
    """Tests for AssertionCoverage data class."""

    def test_default_values(self):
        """Test default assertion coverage values."""
        coverage = AssertionCoverage(
            description="Test assertion",
            target="foo.bar",
            expected=42,
        )
        assert coverage.description == "Test assertion"
        assert coverage.target == "foo.bar"
        assert coverage.expected == 42
        assert coverage.operator == "eq"
        assert coverage.covered is False
        assert coverage.passed is False
        assert coverage.test_name is None
        assert coverage.error_message is None

    def test_covered_passing_assertion(self):
        """Test covered and passing assertion."""
        coverage = AssertionCoverage(
            description="Status check",
            target="status",
            expected=200,
            covered=True,
            passed=True,
            test_name="test_status",
        )
        assert coverage.covered is True
        assert coverage.passed is True
        assert coverage.test_name == "test_status"

    def test_covered_failing_assertion(self):
        """Test covered but failing assertion."""
        coverage = AssertionCoverage(
            description="Status check",
            target="status",
            expected=200,
            covered=True,
            passed=False,
            error_message="Expected 200, got 500",
        )
        assert coverage.covered is True
        assert coverage.passed is False
        assert coverage.error_message == "Expected 200, got 500"

    def test_to_dict(self):
        """Test assertion coverage serialization."""
        coverage = AssertionCoverage(
            description="Test",
            target="x",
            expected=1,
            covered=True,
            passed=True,
        )
        data = coverage.to_dict()
        assert data["description"] == "Test"
        assert data["covered"] is True
        assert data["passed"] is True


# =============================================================================
# TestContractCoverage Tests
# =============================================================================

class TestTestContractCoverage:
    """Tests for TestContractCoverage data class."""

    def test_default_values(self):
        """Test default contract coverage values."""
        coverage = TestContractCoverage()
        assert coverage.contract_id is None
        assert coverage.agent_name == ""
        assert coverage.total_assertions == 0
        assert coverage.covered_assertions == 0
        assert coverage.passed_assertions == 0
        assert coverage.tests_exist is False
        assert coverage.tests_passed is False

    def test_coverage_percentage_no_assertions(self):
        """Test coverage percentage with no assertions."""
        coverage = TestContractCoverage(total_assertions=0)
        assert coverage.coverage_percentage == 100.0

    def test_coverage_percentage_partial(self):
        """Test coverage percentage with partial coverage."""
        coverage = TestContractCoverage(
            total_assertions=10,
            covered_assertions=5,
        )
        assert coverage.coverage_percentage == 50.0

    def test_pass_percentage(self):
        """Test pass percentage calculation."""
        coverage = TestContractCoverage(
            total_assertions=10,
            covered_assertions=8,
            passed_assertions=6,
        )
        assert coverage.pass_percentage == 75.0

    def test_pass_percentage_no_coverage(self):
        """Test pass percentage with no covered assertions."""
        coverage = TestContractCoverage(covered_assertions=0)
        assert coverage.pass_percentage == 0.0


# =============================================================================
# TestGateResult Tests
# =============================================================================

class TestTestGateResult:
    """Tests for TestGateResult data class."""

    def test_passing_result(self):
        """Test a passing result."""
        result = TestGateResult(
            status=TestGateStatus.PASSED,
            can_pass=True,
            feature_id=123,
            summary="All tests passed",
        )
        assert result.status == TestGateStatus.PASSED
        assert result.can_pass is True
        assert result.blocking_reason is None

    def test_failing_result(self):
        """Test a failing result."""
        result = TestGateResult(
            status=TestGateStatus.FAILED,
            can_pass=False,
            blocking_reason="Tests failed",
            feature_id=123,
        )
        assert result.status == TestGateStatus.FAILED
        assert result.can_pass is False
        assert result.blocking_reason == "Tests failed"

    def test_to_dict(self):
        """Test result serialization."""
        result = TestGateResult(
            status=TestGateStatus.PASSED,
            can_pass=True,
            feature_id=456,
        )
        data = result.to_dict()
        assert data["status"] == "passed"
        assert data["can_pass"] is True
        assert data["feature_id"] == 456


# =============================================================================
# TestContractGate Tests - Step 1: Tests Must Be Written
# =============================================================================

class TestStep1TestsMustBeWritten:
    """
    Feature #210 Step 1: Feature with TestContract must have tests written.
    """

    def test_no_tests_blocks_when_contract_exists(self, sample_test_contract):
        """Feature with TestContract but no tests should be blocked."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[],  # No test results = no tests
        )
        assert result.can_pass is False
        assert result.status == TestGateStatus.FAILED
        assert "No tests written" in result.summary

    def test_tests_exist_passes_step1(self, sample_test_contract, sample_test_result_passing):
        """Feature with TestContract and tests should pass step 1."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_passing],
        )
        # Tests exist, so step 1 passes
        assert result.contracts[0].tests_exist is True


# =============================================================================
# TestContractGate Tests - Step 2: Tests Must Pass
# =============================================================================

class TestStep2TestsMustPass:
    """
    Feature #210 Step 2: Tests must execute successfully (exit code 0).
    """

    def test_passing_tests_allows_completion(self, sample_test_contract, sample_test_result_passing):
        """Tests with exit code 0 should allow feature completion."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_passing],
        )
        assert result.can_pass is True
        assert result.status == TestGateStatus.PASSED
        assert result.contracts[0].tests_passed is True

    def test_failing_tests_blocks_completion(self, sample_test_contract, sample_test_result_failing):
        """Tests with non-zero exit code should block feature completion."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_failing],
        )
        assert result.can_pass is False
        assert result.status == TestGateStatus.FAILED
        assert "Tests failed" in result.summary

    def test_exit_code_zero_required(self, sample_test_contract):
        """Tests must have exit code 0 to pass."""
        test_result = {
            "contract_id": "contract-123",
            "passed": False,
            "exit_code": 1,  # Non-zero exit code
        }
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[test_result],
        )
        assert result.can_pass is False


# =============================================================================
# TestContractGate Tests - Step 3: All Assertions Must Be Covered
# =============================================================================

class TestStep3AllAssertionsCovered:
    """
    Feature #210 Step 3: All assertions in TestContract must be covered.
    """

    def test_all_assertions_covered_passes(self, sample_test_contract, sample_test_result_passing):
        """All assertions covered should allow completion."""
        gate = TestContractGate(TestGateConfiguration(require_all_assertions=True))
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_passing],
        )
        assert result.can_pass is True

    def test_partial_assertions_blocks_when_required(self, sample_test_contract):
        """Partial assertion coverage should block when require_all_assertions=True."""
        test_result = {
            "contract_id": "contract-123",
            "passed": True,
            "exit_code": 0,
            "covered_assertions": [
                {"target": "response.status_code", "passed": True},
                # Missing: response.body.user
            ],
        }
        gate = TestContractGate(TestGateConfiguration(require_all_assertions=True))
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[test_result],
        )
        assert result.can_pass is False
        assert "not covered" in result.summary

    def test_partial_assertions_allowed_when_not_required(self, sample_test_contract):
        """Partial assertion coverage should be allowed when require_all_assertions=False."""
        test_result = {
            "contract_id": "contract-123",
            "passed": True,
            "exit_code": 0,
            "covered_assertions": [
                {"target": "response.status_code", "passed": True},
            ],
        }
        gate = TestContractGate(TestGateConfiguration(require_all_assertions=False))
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[test_result],
        )
        assert result.can_pass is True


# =============================================================================
# TestContractGate Tests - Step 4: Gate Blocks Completion if Tests Fail
# =============================================================================

class TestStep4GateBlocksCompletion:
    """
    Feature #210 Step 4: Acceptance gate blocks completion if tests fail.
    """

    def test_gate_blocks_on_test_failure(self, sample_test_contract, sample_test_result_failing):
        """Gate should block completion when tests fail."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_failing],
        )
        assert result.can_pass is False
        assert result.status == TestGateStatus.FAILED
        assert result.blocking_reason is not None

    def test_gate_allows_on_test_success(self, sample_test_contract, sample_test_result_passing):
        """Gate should allow completion when tests pass."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_passing],
        )
        assert result.can_pass is True
        assert result.status == TestGateStatus.PASSED

    def test_multiple_contracts_all_must_pass(self, sample_test_result_passing, sample_test_result_failing):
        """All TestContracts must pass for feature to pass."""
        contract1 = {"contract_id": "c1", "agent_name": "agent1", "assertions": []}
        contract2 = {"contract_id": "c2", "agent_name": "agent2", "assertions": []}

        result1 = {**sample_test_result_passing, "contract_id": "c1", "agent_name": "agent1"}
        result2 = {**sample_test_result_failing, "contract_id": "c2", "agent_name": "agent2"}

        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[contract1, contract2],
            test_results=[result1, result2],
        )
        assert result.can_pass is False


# =============================================================================
# TestContractGate Tests - Step 5: Gate Enforceable via Configuration
# =============================================================================

class TestStep5GateConfigurable:
    """
    Feature #210 Step 5: Gate is enforceable via configuration.
    """

    def test_gate_disabled_allows_pass(self, sample_test_contract, sample_test_result_failing):
        """When gate is disabled, failing tests should still allow pass."""
        config = TestGateConfiguration(enforce_test_gate=False)
        gate = TestContractGate(config)
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_failing],
        )
        assert result.can_pass is True
        assert result.status == TestGateStatus.SKIPPED

    def test_gate_enabled_blocks_failures(self, sample_test_contract, sample_test_result_failing):
        """When gate is enabled, failing tests should block."""
        config = TestGateConfiguration(enforce_test_gate=True)
        gate = TestContractGate(config)
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_failing],
        )
        assert result.can_pass is False

    def test_no_contract_allowed_by_default(self):
        """No TestContract should allow pass by default."""
        config = TestGateConfiguration(allow_skip_for_no_contract=True)
        gate = TestContractGate(config)
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[],
            test_results=[],
        )
        assert result.can_pass is True
        assert result.status == TestGateStatus.NO_CONTRACT

    def test_no_contract_blocked_when_required(self):
        """No TestContract should block when contracts are required."""
        config = TestGateConfiguration(
            enforce_test_gate=True,
            allow_skip_for_no_contract=False,
        )
        gate = TestContractGate(config)
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[],
            test_results=[],
        )
        assert result.can_pass is False
        assert result.status == TestGateStatus.NO_CONTRACT

    def test_min_coverage_threshold(self, sample_test_contract):
        """Minimum coverage threshold should be enforced."""
        test_result = {
            "contract_id": "contract-123",
            "passed": True,
            "exit_code": 0,
            "covered_assertions": [
                {"target": "response.status_code", "passed": True},
                # Only 1 of 2 assertions covered = 50%
            ],
        }
        config = TestGateConfiguration(
            require_all_assertions=False,
            min_test_coverage=75.0,  # Require 75% coverage
        )
        gate = TestContractGate(config)
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[test_result],
        )
        assert result.can_pass is False
        assert "Coverage" in result.summary


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_test_contract_gate_singleton(self):
        """Test that get_test_contract_gate returns singleton."""
        gate1 = get_test_contract_gate()
        gate2 = get_test_contract_gate()
        assert gate1 is gate2

    def test_reset_test_contract_gate(self):
        """Test that reset clears the singleton."""
        gate1 = get_test_contract_gate()
        reset_test_contract_gate()
        gate2 = get_test_contract_gate()
        assert gate1 is not gate2

    def test_evaluate_test_gate(self, sample_test_contract, sample_test_result_passing):
        """Test evaluate_test_gate convenience function."""
        result = evaluate_test_gate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_passing],
        )
        assert result.can_pass is True

    def test_check_tests_required_no_gate(self):
        """Test check_tests_required when gate disabled."""
        config = TestGateConfiguration(enforce_test_gate=False)
        required = check_tests_required(
            feature_id=1,
            test_contracts=[{"agent_name": "test"}],
            config=config,
        )
        assert required is False

    def test_check_tests_required_with_contracts(self):
        """Test check_tests_required with contracts."""
        config = TestGateConfiguration(enforce_test_gate=True)
        required = check_tests_required(
            feature_id=1,
            test_contracts=[{"agent_name": "test"}],
            config=config,
        )
        assert required is True

    def test_check_tests_required_no_contracts(self):
        """Test check_tests_required without contracts."""
        config = TestGateConfiguration(
            enforce_test_gate=True,
            allow_skip_for_no_contract=True,
        )
        required = check_tests_required(
            feature_id=1,
            test_contracts=[],
            config=config,
        )
        assert required is False

    def test_get_blocking_test_issues(self, sample_test_contract, sample_test_result_failing):
        """Test get_blocking_test_issues function."""
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1,
            test_contracts=[sample_test_contract],
            test_results=[sample_test_result_failing],
        )
        issues = get_blocking_test_issues(result)
        assert len(issues) > 0


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Test that all exports are available from api package."""

    def test_enum_exports(self):
        """Test enum exports."""
        from api import TestGateStatus
        assert TestGateStatus.PASSED == "passed"

    def test_dataclass_exports(self):
        """Test dataclass exports."""
        from api import (
            TestGateConfiguration,
            AssertionCoverage,
            TestContractCoverage,
            TestGateResult,
        )
        config = TestGateConfiguration()
        assert config is not None

    def test_class_exports(self):
        """Test class exports."""
        from api import TestContractGate
        gate = TestContractGate()
        assert gate is not None

    def test_function_exports(self):
        """Test function exports."""
        from api import (
            get_test_contract_gate,
            reset_test_contract_gate,
            evaluate_test_gate,
            check_tests_required,
            get_blocking_test_issues,
        )
        gate = get_test_contract_gate()
        assert gate is not None

    def test_constant_exports(self):
        """Test constant exports."""
        from api import (
            DEFAULT_ENFORCE_TEST_GATE,
            DEFAULT_REQUIRE_ALL_ASSERTIONS,
            DEFAULT_MIN_TEST_COVERAGE,
            DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT,
        )
        assert DEFAULT_ENFORCE_TEST_GATE is True
        assert DEFAULT_REQUIRE_ALL_ASSERTIONS is True
        assert DEFAULT_MIN_TEST_COVERAGE == 0.0


# =============================================================================
# Feature #210 Verification Steps Tests
# =============================================================================

class TestFeature210VerificationSteps:
    """
    Comprehensive tests verifying each feature step is implemented correctly.
    """

    def test_step1_feature_with_testcontract_must_have_tests(self):
        """
        Step 1: Feature with TestContract must have tests written.

        Verify that:
        - A feature with TestContract requires test results
        - Missing test results block feature completion
        """
        contract = {
            "contract_id": "c1",
            "agent_name": "agent",
            "test_type": "unit",
            "assertions": [{"description": "test", "target": "x", "expected": 1}],
        }
        gate = TestContractGate()

        # No test results = blocked
        result = gate.evaluate(feature_id=1, test_contracts=[contract], test_results=[])
        assert result.can_pass is False
        assert not result.contracts[0].tests_exist

    def test_step2_tests_must_execute_successfully(self):
        """
        Step 2: Tests must execute successfully (exit code 0).

        Verify that:
        - Tests with exit_code=0 allow feature to pass
        - Tests with exit_code!=0 block feature completion
        """
        contract = {
            "contract_id": "c1",
            "agent_name": "agent",
            "assertions": [],
        }

        # Exit code 0 = passes
        result_pass = {"contract_id": "c1", "exit_code": 0, "passed": True}
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_pass]
        )
        assert result.contracts[0].tests_passed is True

        # Exit code 1 = fails
        result_fail = {"contract_id": "c1", "exit_code": 1, "passed": False}
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_fail]
        )
        assert result.contracts[0].tests_passed is False

    def test_step3_all_assertions_must_be_covered(self):
        """
        Step 3: All assertions in TestContract must be covered.

        Verify that:
        - Uncovered assertions block feature completion
        - All assertions covered allows feature to pass
        """
        contract = {
            "contract_id": "c1",
            "agent_name": "agent",
            "assertions": [
                {"description": "a1", "target": "x", "expected": 1},
                {"description": "a2", "target": "y", "expected": 2},
            ],
        }

        # Only one assertion covered = blocked
        result_partial = {
            "contract_id": "c1",
            "exit_code": 0,
            "passed": True,
            "covered_assertions": [{"target": "x", "passed": True}],
        }
        config = TestGateConfiguration(require_all_assertions=True)
        gate = TestContractGate(config)
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_partial]
        )
        assert result.can_pass is False

        # All assertions covered = passes
        result_full = {
            "contract_id": "c1",
            "exit_code": 0,
            "passed": True,
            "covered_assertions": [
                {"target": "x", "passed": True},
                {"target": "y", "passed": True},
            ],
        }
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_full]
        )
        assert result.can_pass is True

    def test_step4_acceptance_gate_blocks_if_tests_fail(self):
        """
        Step 4: Acceptance gate blocks completion if tests fail.

        Verify that:
        - Failed tests block feature completion
        - Passed tests allow feature completion
        - Blocking reason is provided
        """
        contract = {"contract_id": "c1", "agent_name": "agent", "assertions": []}

        # Tests fail = blocked
        result_fail = {"contract_id": "c1", "exit_code": 1, "passed": False}
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_fail]
        )
        assert result.can_pass is False
        assert result.blocking_reason is not None

        # Tests pass = allowed
        result_pass = {"contract_id": "c1", "exit_code": 0, "passed": True}
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_pass]
        )
        assert result.can_pass is True

    def test_step5_gate_enforceable_via_configuration(self):
        """
        Step 5: Gate is enforceable via configuration.

        Verify that:
        - enforce_test_gate=True blocks failing tests
        - enforce_test_gate=False allows failing tests
        - require_all_assertions is configurable
        - min_test_coverage is configurable
        - allow_skip_for_no_contract is configurable
        """
        contract = {"contract_id": "c1", "agent_name": "agent", "assertions": []}
        result_fail = {"contract_id": "c1", "exit_code": 1, "passed": False}

        # Enforced = blocked
        config_enforced = TestGateConfiguration(enforce_test_gate=True)
        gate = TestContractGate(config_enforced)
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_fail]
        )
        assert result.can_pass is False

        # Not enforced = allowed
        config_not_enforced = TestGateConfiguration(enforce_test_gate=False)
        gate = TestContractGate(config_not_enforced)
        result = gate.evaluate(
            feature_id=1, test_contracts=[contract], test_results=[result_fail]
        )
        assert result.can_pass is True
        assert result.status == TestGateStatus.SKIPPED

        # No contracts allowed by default
        config_allow_no_contract = TestGateConfiguration(allow_skip_for_no_contract=True)
        gate = TestContractGate(config_allow_no_contract)
        result = gate.evaluate(feature_id=1, test_contracts=[], test_results=[])
        assert result.can_pass is True

        # No contracts blocked when required
        config_require_contract = TestGateConfiguration(allow_skip_for_no_contract=False)
        gate = TestContractGate(config_require_contract)
        result = gate.evaluate(feature_id=1, test_contracts=[], test_results=[])
        assert result.can_pass is False
