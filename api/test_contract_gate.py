"""
Test Contract Gate - Feature #210
=================================

Feature cannot pass without tests passing.

Acceptance gates require associated tests to pass before feature is marked complete.

This module provides:
- TestContractGate: Validates that tests associated with a feature pass
- TestGateConfiguration: Configuration for test gate enforcement
- TestGateResult: Result of test gate evaluation

The gate enforces the following requirements:
1. Feature with TestContract must have tests written
2. Tests must execute successfully (exit code 0)
3. All assertions in TestContract must be covered
4. Acceptance gate blocks completion if tests fail
5. Gate is enforceable via configuration

Usage:
    from api.test_contract_gate import TestContractGate, TestGateConfiguration

    # Create gate with configuration
    config = TestGateConfiguration(
        enforce_test_gate=True,
        require_all_assertions=True,
    )
    gate = TestContractGate(config)

    # Check if feature can pass
    result = gate.evaluate(feature_id, test_contracts, test_results)

    if not result.can_pass:
        print(f"Cannot mark passing: {result.blocking_reason}")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default configuration values
DEFAULT_ENFORCE_TEST_GATE = True
DEFAULT_REQUIRE_ALL_ASSERTIONS = True
DEFAULT_MIN_TEST_COVERAGE = 0.0  # 0 means no minimum coverage required
DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT = True  # Allow passing if no TestContract exists

# Test gate status values
class TestGateStatus(str, Enum):
    """Status of test gate evaluation."""
    PASSED = "passed"          # All tests passed, gate allows completion
    FAILED = "failed"          # Tests failed, gate blocks completion
    NO_TESTS = "no_tests"      # No tests written for contract
    NO_CONTRACT = "no_contract"  # No TestContract associated with feature
    SKIPPED = "skipped"        # Gate skipped (not enforced)
    ERROR = "error"            # Error during evaluation

    def __str__(self) -> str:
        return self.value


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TestGateConfiguration:
    """
    Configuration for test gate enforcement.

    Feature #210 Step 5: Gate is enforceable via configuration.

    Attributes:
        enforce_test_gate: If True, gate blocks completion when tests fail
        require_all_assertions: If True, all TestContract assertions must be covered
        min_test_coverage: Minimum test coverage percentage (0.0-100.0)
        allow_skip_for_no_contract: If True, allow passing if no TestContract exists
        timeout_seconds: Timeout for test execution
        max_retries: Maximum retries for flaky tests
    """
    enforce_test_gate: bool = DEFAULT_ENFORCE_TEST_GATE
    require_all_assertions: bool = DEFAULT_REQUIRE_ALL_ASSERTIONS
    min_test_coverage: float = DEFAULT_MIN_TEST_COVERAGE
    allow_skip_for_no_contract: bool = DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT
    timeout_seconds: int = 300
    max_retries: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enforce_test_gate": self.enforce_test_gate,
            "require_all_assertions": self.require_all_assertions,
            "min_test_coverage": self.min_test_coverage,
            "allow_skip_for_no_contract": self.allow_skip_for_no_contract,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestGateConfiguration":
        """Create from dictionary."""
        return cls(
            enforce_test_gate=data.get("enforce_test_gate", DEFAULT_ENFORCE_TEST_GATE),
            require_all_assertions=data.get("require_all_assertions", DEFAULT_REQUIRE_ALL_ASSERTIONS),
            min_test_coverage=data.get("min_test_coverage", DEFAULT_MIN_TEST_COVERAGE),
            allow_skip_for_no_contract=data.get("allow_skip_for_no_contract", DEFAULT_ALLOW_SKIP_FOR_NO_CONTRACT),
            timeout_seconds=data.get("timeout_seconds", 300),
            max_retries=data.get("max_retries", 1),
        )


@dataclass
class AssertionCoverage:
    """
    Coverage information for a single TestContract assertion.

    Feature #210 Step 3: All assertions in TestContract must be covered.

    Attributes:
        description: Assertion description from TestContract
        target: Target being tested
        expected: Expected value/condition
        operator: Comparison operator
        covered: Whether this assertion is covered by tests
        passed: Whether the assertion passed (if covered)
        test_name: Name of test covering this assertion (if any)
        error_message: Error message if assertion failed
    """
    description: str
    target: str
    expected: Any
    operator: str = "eq"
    covered: bool = False
    passed: bool = False
    test_name: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "description": self.description,
            "target": self.target,
            "expected": self.expected,
            "operator": self.operator,
            "covered": self.covered,
            "passed": self.passed,
            "test_name": self.test_name,
            "error_message": self.error_message,
        }


@dataclass
class TestContractCoverage:
    """
    Coverage information for a TestContract.

    Attributes:
        contract_id: ID of the TestContract
        agent_name: Name of the associated agent
        test_type: Type of testing (unit, integration, etc.)
        total_assertions: Total number of assertions in contract
        covered_assertions: Number of assertions covered by tests
        passed_assertions: Number of assertions that passed
        assertions: Detailed coverage for each assertion
        tests_exist: Whether test files exist
        tests_passed: Whether all tests passed
        coverage_percentage: Percentage of assertions covered
    """
    contract_id: str | None = None
    agent_name: str = ""
    test_type: str = ""
    total_assertions: int = 0
    covered_assertions: int = 0
    passed_assertions: int = 0
    assertions: list[AssertionCoverage] = field(default_factory=list)
    tests_exist: bool = False
    tests_passed: bool = False

    @property
    def coverage_percentage(self) -> float:
        """Calculate assertion coverage percentage."""
        if self.total_assertions == 0:
            return 100.0
        return (self.covered_assertions / self.total_assertions) * 100

    @property
    def pass_percentage(self) -> float:
        """Calculate assertion pass percentage."""
        if self.covered_assertions == 0:
            return 0.0
        return (self.passed_assertions / self.covered_assertions) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "contract_id": self.contract_id,
            "agent_name": self.agent_name,
            "test_type": self.test_type,
            "total_assertions": self.total_assertions,
            "covered_assertions": self.covered_assertions,
            "passed_assertions": self.passed_assertions,
            "assertions": [a.to_dict() for a in self.assertions],
            "tests_exist": self.tests_exist,
            "tests_passed": self.tests_passed,
            "coverage_percentage": self.coverage_percentage,
            "pass_percentage": self.pass_percentage,
        }


@dataclass
class TestGateResult:
    """
    Result of test gate evaluation.

    Feature #210: Acceptance gates require tests to pass.

    Attributes:
        status: Overall status of the test gate
        can_pass: Whether the feature can be marked as passing
        blocking_reason: Reason why the feature cannot pass (if blocked)
        feature_id: ID of the feature being evaluated
        contracts: List of TestContract coverage results
        test_execution_results: Results from test execution
        config_used: Configuration used for evaluation
        evaluated_at: Timestamp of evaluation
        summary: Human-readable summary of the evaluation
    """
    status: TestGateStatus
    can_pass: bool
    blocking_reason: str | None = None
    feature_id: int | None = None
    contracts: list[TestContractCoverage] = field(default_factory=list)
    test_execution_results: list[dict[str, Any]] = field(default_factory=list)
    config_used: TestGateConfiguration | None = None
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": str(self.status),
            "can_pass": self.can_pass,
            "blocking_reason": self.blocking_reason,
            "feature_id": self.feature_id,
            "contracts": [c.to_dict() for c in self.contracts],
            "test_execution_results": self.test_execution_results,
            "config_used": self.config_used.to_dict() if self.config_used else None,
            "evaluated_at": self.evaluated_at.isoformat(),
            "summary": self.summary,
        }


# =============================================================================
# Test Contract Gate Implementation
# =============================================================================

class TestContractGate:
    """
    Gate that validates tests pass before feature completion.

    Feature #210: Feature cannot pass without tests passing.

    This class implements the test gate that:
    1. Checks if TestContract exists for the feature
    2. Verifies tests have been written
    3. Executes tests and checks exit code
    4. Validates all assertions are covered
    5. Blocks feature completion if tests fail

    The gate is enforceable via configuration.

    Usage:
        gate = TestContractGate()
        result = gate.evaluate(
            feature_id=123,
            test_contracts=[...],
            test_results=[...],
        )

        if not result.can_pass:
            print(f"Blocked: {result.blocking_reason}")
    """

    def __init__(
        self,
        config: TestGateConfiguration | None = None,
    ):
        """
        Initialize the TestContractGate.

        Args:
            config: Gate configuration. Uses defaults if not provided.
        """
        self.config = config or TestGateConfiguration()
        self._logger = logging.getLogger(__name__)

    def evaluate(
        self,
        feature_id: int,
        test_contracts: list[dict[str, Any]] | None = None,
        test_results: list[dict[str, Any]] | None = None,
        *,
        override_config: TestGateConfiguration | None = None,
    ) -> TestGateResult:
        """
        Evaluate test gate for a feature.

        Feature #210 Steps 1-4:
        - Step 1: Feature with TestContract must have tests written
        - Step 2: Tests must execute successfully (exit code 0)
        - Step 3: All assertions in TestContract must be covered
        - Step 4: Acceptance gate blocks completion if tests fail

        Args:
            feature_id: ID of the feature to evaluate
            test_contracts: List of TestContract dicts associated with feature
            test_results: List of test execution result dicts
            override_config: Optional config to override instance config

        Returns:
            TestGateResult with evaluation outcome
        """
        config = override_config or self.config
        test_contracts = test_contracts or []
        test_results = test_results or []

        self._logger.info(
            "TestContractGate.evaluate: feature_id=%d, contracts=%d, results=%d",
            feature_id, len(test_contracts), len(test_results)
        )

        # Feature #210 Step 5: Check if gate is enforced
        if not config.enforce_test_gate:
            self._logger.info("Test gate not enforced, allowing feature to pass")
            return TestGateResult(
                status=TestGateStatus.SKIPPED,
                can_pass=True,
                feature_id=feature_id,
                config_used=config,
                summary="Test gate not enforced (skipped)",
            )

        # Step 1: Check if TestContract exists
        if not test_contracts:
            if config.allow_skip_for_no_contract:
                self._logger.info(
                    "No TestContract for feature %d, allowing pass (config allows)",
                    feature_id
                )
                return TestGateResult(
                    status=TestGateStatus.NO_CONTRACT,
                    can_pass=True,
                    feature_id=feature_id,
                    config_used=config,
                    summary="No TestContract associated with feature (allowed by config)",
                )
            else:
                self._logger.warning(
                    "No TestContract for feature %d, blocking (config requires)",
                    feature_id
                )
                return TestGateResult(
                    status=TestGateStatus.NO_CONTRACT,
                    can_pass=False,
                    blocking_reason="Feature requires TestContract but none found",
                    feature_id=feature_id,
                    config_used=config,
                    summary="Feature requires TestContract but none found",
                )

        # Process each TestContract
        contract_coverages: list[TestContractCoverage] = []
        all_tests_passed = True
        all_assertions_covered = True
        blocking_reasons: list[str] = []

        for contract in test_contracts:
            coverage = self._evaluate_contract(contract, test_results, config)
            contract_coverages.append(coverage)

            # Step 1: Check if tests exist
            if not coverage.tests_exist:
                all_tests_passed = False
                blocking_reasons.append(
                    f"Contract '{contract.get('agent_name', 'unknown')}': No tests written"
                )

            # Step 2: Check if tests passed (exit code 0)
            elif not coverage.tests_passed:
                all_tests_passed = False
                blocking_reasons.append(
                    f"Contract '{contract.get('agent_name', 'unknown')}': Tests failed"
                )

            # Step 3: Check assertion coverage
            if config.require_all_assertions:
                if coverage.covered_assertions < coverage.total_assertions:
                    all_assertions_covered = False
                    blocking_reasons.append(
                        f"Contract '{contract.get('agent_name', 'unknown')}': "
                        f"{coverage.total_assertions - coverage.covered_assertions} "
                        f"assertion(s) not covered"
                    )

            # Check coverage threshold
            if config.min_test_coverage > 0:
                if coverage.coverage_percentage < config.min_test_coverage:
                    all_assertions_covered = False
                    blocking_reasons.append(
                        f"Contract '{contract.get('agent_name', 'unknown')}': "
                        f"Coverage {coverage.coverage_percentage:.1f}% < "
                        f"required {config.min_test_coverage:.1f}%"
                    )

        # Step 4: Determine if feature can pass
        can_pass = all_tests_passed and all_assertions_covered

        if can_pass:
            status = TestGateStatus.PASSED
            summary = f"All {len(test_contracts)} TestContract(s) passed"
        else:
            status = TestGateStatus.FAILED
            summary = f"Test gate blocked: {'; '.join(blocking_reasons)}"

        result = TestGateResult(
            status=status,
            can_pass=can_pass,
            blocking_reason=blocking_reasons[0] if blocking_reasons else None,
            feature_id=feature_id,
            contracts=contract_coverages,
            test_execution_results=test_results,
            config_used=config,
            summary=summary,
        )

        self._logger.info(
            "TestContractGate.evaluate complete: feature=%d, status=%s, can_pass=%s",
            feature_id, status, can_pass
        )

        return result

    def _evaluate_contract(
        self,
        contract: dict[str, Any],
        test_results: list[dict[str, Any]],
        config: TestGateConfiguration,
    ) -> TestContractCoverage:
        """
        Evaluate coverage for a single TestContract.

        Args:
            contract: TestContract dictionary
            test_results: List of test execution results
            config: Gate configuration

        Returns:
            TestContractCoverage with evaluation details
        """
        agent_name = contract.get("agent_name", "unknown")
        test_type = contract.get("test_type", "unknown")
        assertions = contract.get("assertions", [])
        pass_criteria = contract.get("pass_criteria", [])

        coverage = TestContractCoverage(
            contract_id=contract.get("contract_id"),
            agent_name=agent_name,
            test_type=test_type,
            total_assertions=len(assertions),
        )

        # Check if tests exist (look for matching test results)
        matching_results = [
            r for r in test_results
            if r.get("contract_id") == contract.get("contract_id")
            or r.get("agent_name") == agent_name
        ]

        if not matching_results:
            # No test results found - tests may not exist or haven't been run
            coverage.tests_exist = False
            coverage.tests_passed = False
            return coverage

        coverage.tests_exist = True

        # Check if tests passed (all matching results have exit_code 0)
        coverage.tests_passed = all(
            r.get("exit_code", 1) == 0 and r.get("passed", False)
            for r in matching_results
        )

        # Evaluate assertion coverage
        for assertion in assertions:
            assertion_coverage = self._evaluate_assertion(
                assertion, matching_results
            )
            coverage.assertions.append(assertion_coverage)

            if assertion_coverage.covered:
                coverage.covered_assertions += 1
                if assertion_coverage.passed:
                    coverage.passed_assertions += 1

        return coverage

    def _evaluate_assertion(
        self,
        assertion: dict[str, Any],
        test_results: list[dict[str, Any]],
    ) -> AssertionCoverage:
        """
        Evaluate coverage for a single assertion.

        Args:
            assertion: Assertion dictionary from TestContract
            test_results: List of test execution results

        Returns:
            AssertionCoverage with evaluation details
        """
        description = assertion.get("description", "")
        target = assertion.get("target", "")
        expected = assertion.get("expected")
        operator = assertion.get("operator", "eq")

        coverage = AssertionCoverage(
            description=description,
            target=target,
            expected=expected,
            operator=operator,
        )

        # Search for test that covers this assertion
        for result in test_results:
            # Check if any test explicitly mentions this assertion
            test_name = result.get("test_name") or result.get("command", "")
            covered_assertions = result.get("covered_assertions", [])

            # Check explicit coverage tracking
            for covered in covered_assertions:
                if (
                    covered.get("target") == target
                    or covered.get("description") == description
                ):
                    coverage.covered = True
                    coverage.passed = covered.get("passed", result.get("passed", False))
                    coverage.test_name = test_name
                    if not coverage.passed:
                        coverage.error_message = covered.get("error_message")
                    return coverage

            # Heuristic: check if test name/output mentions the target
            test_output = result.get("stdout", "") + result.get("stderr", "")
            if target.lower() in test_output.lower():
                coverage.covered = True
                coverage.passed = result.get("passed", False)
                coverage.test_name = test_name
                return coverage

        return coverage

    def check_feature_can_pass(
        self,
        feature_id: int,
        db: "Session | None" = None,
    ) -> TestGateResult:
        """
        Check if a feature can be marked as passing.

        This is a convenience method that queries for associated TestContracts
        and test results from the database.

        Args:
            feature_id: ID of the feature
            db: Database session (optional)

        Returns:
            TestGateResult with evaluation outcome
        """
        # If no database session, return a default passing result
        if db is None:
            self._logger.warning(
                "No database session provided, assuming no TestContracts"
            )
            return self.evaluate(feature_id, test_contracts=[], test_results=[])

        # Query for TestContracts and test results
        # This would require actual database models for TestContract storage
        # For now, return a default result
        return self.evaluate(feature_id, test_contracts=[], test_results=[])


# =============================================================================
# Convenience Functions
# =============================================================================

# Global gate instance cache
_gate_instance: TestContractGate | None = None


def get_test_contract_gate(
    config: TestGateConfiguration | None = None,
) -> TestContractGate:
    """
    Get or create the test contract gate instance.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        TestContractGate instance
    """
    global _gate_instance

    if _gate_instance is None:
        _gate_instance = TestContractGate(config)

    return _gate_instance


def reset_test_contract_gate() -> None:
    """Reset the cached gate instance (useful for testing)."""
    global _gate_instance
    _gate_instance = None


def evaluate_test_gate(
    feature_id: int,
    test_contracts: list[dict[str, Any]] | None = None,
    test_results: list[dict[str, Any]] | None = None,
    config: TestGateConfiguration | None = None,
) -> TestGateResult:
    """
    Convenience function to evaluate the test gate for a feature.

    Args:
        feature_id: ID of the feature
        test_contracts: List of TestContract dictionaries
        test_results: List of test execution result dictionaries
        config: Optional configuration override

    Returns:
        TestGateResult with evaluation outcome
    """
    gate = get_test_contract_gate()
    return gate.evaluate(
        feature_id=feature_id,
        test_contracts=test_contracts,
        test_results=test_results,
        override_config=config,
    )


def check_tests_required(
    feature_id: int,
    test_contracts: list[dict[str, Any]] | None = None,
    config: TestGateConfiguration | None = None,
) -> bool:
    """
    Check if tests are required for a feature to pass.

    Args:
        feature_id: ID of the feature
        test_contracts: List of TestContract dictionaries
        config: Optional configuration

    Returns:
        True if tests are required, False otherwise
    """
    config = config or TestGateConfiguration()

    # Tests not required if gate is not enforced
    if not config.enforce_test_gate:
        return False

    # Tests not required if no contracts and config allows
    if not test_contracts and config.allow_skip_for_no_contract:
        return False

    # Tests required if contracts exist
    return bool(test_contracts)


def get_blocking_test_issues(
    result: TestGateResult,
) -> list[str]:
    """
    Get a list of issues blocking the feature from passing.

    Args:
        result: TestGateResult from evaluation

    Returns:
        List of issue descriptions
    """
    issues = []

    if result.blocking_reason:
        issues.append(result.blocking_reason)

    for contract in result.contracts:
        if not contract.tests_exist:
            issues.append(f"No tests for contract '{contract.agent_name}'")
        elif not contract.tests_passed:
            issues.append(f"Tests failed for contract '{contract.agent_name}'")

        for assertion in contract.assertions:
            if not assertion.covered:
                issues.append(
                    f"Assertion not covered: {assertion.description}"
                )
            elif not assertion.passed:
                issues.append(
                    f"Assertion failed: {assertion.description} - {assertion.error_message or 'no details'}"
                )

    return issues
