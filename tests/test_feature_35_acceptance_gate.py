"""
Tests for Feature #35: Acceptance Gate Orchestration
=====================================================

This module tests the AcceptanceGate class that orchestrates validator
execution and determines final verdict based on gate_mode.

Feature #35 Steps:
1. Create AcceptanceGate class with evaluate(run, acceptance_spec) method
2. Iterate through validators array
3. Instantiate appropriate validator class for each type
4. Execute validator and collect ValidatorResult
5. Check required flag - required validators must always pass
6. For all_pass mode: verdict = passed if all passed
7. For any_pass mode: verdict = passed if any passed
8. Build acceptance_results array with per-validator outcomes
9. Set AgentRun.final_verdict based on gate result
10. Store acceptance_results JSON in AgentRun
11. Return overall verdict
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Any

from api.validators import (
    AcceptanceGate,
    GateResult,
    ValidatorResult,
    evaluate_validator,
    VALIDATOR_REGISTRY,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def acceptance_gate():
    """Create an AcceptanceGate instance for testing."""
    return AcceptanceGate()


@pytest.fixture
def mock_run():
    """Create a mock AgentRun for testing."""
    run = MagicMock()
    run.id = "test-run-123"
    run.final_verdict = None
    run.acceptance_results = None
    run.events = []  # Empty events list for forbidden_patterns validator
    return run


@pytest.fixture
def sample_acceptance_spec_all_pass():
    """Create a sample AcceptanceSpec with all_pass gate mode."""
    spec = MagicMock()
    spec.validators = [
        {
            "type": "file_exists",
            "config": {"path": "/tmp/test_file.txt"},
            "weight": 1.0,
            "required": False,
        },
        {
            "type": "file_exists",
            "config": {"path": "/tmp/another_file.txt"},
            "weight": 1.0,
            "required": False,
        },
    ]
    spec.gate_mode = "all_pass"
    return spec


@pytest.fixture
def sample_acceptance_spec_any_pass():
    """Create a sample AcceptanceSpec with any_pass gate mode."""
    spec = MagicMock()
    spec.validators = [
        {
            "type": "file_exists",
            "config": {"path": "/tmp/test_file.txt"},
            "weight": 1.0,
            "required": False,
        },
        {
            "type": "file_exists",
            "config": {"path": "/tmp/nonexistent_file.txt"},
            "weight": 1.0,
            "required": False,
        },
    ]
    spec.gate_mode = "any_pass"
    return spec


@pytest.fixture
def sample_acceptance_spec_with_required():
    """Create a sample AcceptanceSpec with a required validator."""
    spec = MagicMock()
    spec.validators = [
        {
            "type": "file_exists",
            "config": {"path": "/tmp/required_file.txt"},
            "weight": 1.0,
            "required": True,  # This validator is required
        },
        {
            "type": "file_exists",
            "config": {"path": "/tmp/optional_file.txt"},
            "weight": 1.0,
            "required": False,
        },
    ]
    spec.gate_mode = "all_pass"
    return spec


# =============================================================================
# Test AcceptanceGate Class
# =============================================================================

class TestAcceptanceGateClass:
    """Test AcceptanceGate class instantiation and basic properties."""

    def test_create_acceptance_gate(self):
        """Step 1: Create AcceptanceGate class with evaluate method."""
        gate = AcceptanceGate()
        assert gate is not None
        assert hasattr(gate, "evaluate")
        assert hasattr(gate, "evaluate_and_update_run")
        assert callable(gate.evaluate)
        assert callable(gate.evaluate_and_update_run)

    def test_acceptance_gate_has_logger(self, acceptance_gate):
        """AcceptanceGate should have a logger."""
        assert hasattr(acceptance_gate, "_logger")


# =============================================================================
# Test GateResult
# =============================================================================

class TestGateResult:
    """Test GateResult dataclass."""

    def test_gate_result_creation(self):
        """GateResult should be created with all required fields."""
        result = GateResult(
            passed=True,
            verdict="passed",
            gate_mode="all_pass",
            validator_results=[],
            acceptance_results=[],
        )
        assert result.passed is True
        assert result.verdict == "passed"
        assert result.gate_mode == "all_pass"
        assert result.validator_results == []
        assert result.acceptance_results == []
        assert result.required_failed is False
        assert result.summary == ""

    def test_gate_result_to_dict(self):
        """GateResult.to_dict() should serialize to dict."""
        result = GateResult(
            passed=True,
            verdict="passed",
            gate_mode="all_pass",
            validator_results=[ValidatorResult(passed=True, message="ok")],
            acceptance_results=[{"index": 0, "passed": True}],
            required_failed=False,
            summary="1/1 validators passed",
        )
        result_dict = result.to_dict()

        assert result_dict["passed"] is True
        assert result_dict["verdict"] == "passed"
        assert result_dict["gate_mode"] == "all_pass"
        assert result_dict["acceptance_results"] == [{"index": 0, "passed": True}]
        assert result_dict["required_failed"] is False
        assert result_dict["summary"] == "1/1 validators passed"
        assert result_dict["validators_passed"] == 1
        assert result_dict["validators_total"] == 1


# =============================================================================
# Test Evaluate Method - Empty Validators
# =============================================================================

class TestEvaluateEmptyValidators:
    """Test evaluate() with no validators."""

    def test_empty_validators_returns_passed(self, acceptance_gate, mock_run):
        """Empty validators list should default to passed."""
        spec = MagicMock()
        spec.validators = []
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.verdict == "passed"
        assert result.validator_results == []
        assert result.acceptance_results == []

    def test_none_validators_returns_passed(self, acceptance_gate, mock_run):
        """None validators should default to passed."""
        spec = MagicMock()
        spec.validators = None
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.verdict == "passed"

    def test_none_acceptance_spec_returns_passed(self, acceptance_gate, mock_run):
        """None acceptance_spec should default to passed."""
        result = acceptance_gate.evaluate(mock_run, None)

        assert result.passed is True
        assert result.verdict == "passed"


# =============================================================================
# Test Evaluate Method - all_pass Gate Mode
# =============================================================================

class TestAllPassGateMode:
    """Test all_pass gate mode behavior."""

    def test_all_validators_pass(self, acceptance_gate, mock_run, tmp_path):
        """Step 5: For all_pass mode: verdict = passed if all passed."""
        # Create temp files that will exist
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("test")
        file2.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": str(file2)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.verdict == "passed"
        assert len(result.validator_results) == 2
        assert all(r.passed for r in result.validator_results)

    def test_one_validator_fails(self, acceptance_gate, mock_run, tmp_path):
        """For all_pass mode: verdict = partial if some pass, some fail."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": "/nonexistent/file.txt"}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is False
        assert result.verdict == "partial"  # Some passed, some failed
        assert len(result.validator_results) == 2

    def test_all_validators_fail(self, acceptance_gate, mock_run):
        """For all_pass mode: verdict = failed if all fail."""
        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": "/nonexistent1.txt"}, "required": False},
            {"type": "file_exists", "config": {"path": "/nonexistent2.txt"}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is False
        assert result.verdict == "failed"


# =============================================================================
# Test Evaluate Method - any_pass Gate Mode
# =============================================================================

class TestAnyPassGateMode:
    """Test any_pass gate mode behavior."""

    def test_one_validator_passes(self, acceptance_gate, mock_run, tmp_path):
        """Step 6: For any_pass mode: verdict = passed if any passed."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": False},
        ]
        spec.gate_mode = "any_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.verdict == "passed"

    def test_all_validators_fail_any_pass(self, acceptance_gate, mock_run):
        """For any_pass mode: verdict = failed if none pass."""
        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": "/nonexistent1.txt"}, "required": False},
            {"type": "file_exists", "config": {"path": "/nonexistent2.txt"}, "required": False},
        ]
        spec.gate_mode = "any_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is False
        assert result.verdict == "failed"


# =============================================================================
# Test Required Validators
# =============================================================================

class TestRequiredValidators:
    """Test required validator enforcement."""

    def test_required_validator_fails_gate_fails(self, acceptance_gate, mock_run, tmp_path):
        """Step 4: Check required flag - required validators must always pass."""
        optional_file = tmp_path / "optional.txt"
        optional_file.write_text("test")

        spec = MagicMock()
        spec.validators = [
            # Required validator that fails
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": True},
            # Optional validator that passes
            {"type": "file_exists", "config": {"path": str(optional_file)}, "required": False},
        ]
        spec.gate_mode = "any_pass"  # Even any_pass shouldn't help

        result = acceptance_gate.evaluate(mock_run, spec)

        # Even with any_pass, required failure should fail the gate
        assert result.passed is False
        assert result.required_failed is True
        assert result.verdict == "partial"  # One passed, one failed

    def test_required_validator_passes_gate_succeeds(self, acceptance_gate, mock_run, tmp_path):
        """If required validator passes, it doesn't block gate."""
        required_file = tmp_path / "required.txt"
        required_file.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(required_file)}, "required": True},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.required_failed is False
        assert result.verdict == "passed"

    def test_multiple_required_one_fails(self, acceptance_gate, mock_run, tmp_path):
        """If any required validator fails, gate fails."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": True},
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": True},
        ]
        spec.gate_mode = "any_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is False
        assert result.required_failed is True


# =============================================================================
# Test Acceptance Results Array
# =============================================================================

class TestAcceptanceResultsArray:
    """Test acceptance_results array building."""

    def test_acceptance_results_per_validator(self, acceptance_gate, mock_run, tmp_path):
        """Step 7: Build acceptance_results array with per-validator outcomes."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {
                "type": "file_exists",
                "config": {"path": str(file1)},
                "weight": 1.5,
                "required": True,
            },
            {
                "type": "file_exists",
                "config": {"path": "/nonexistent.txt"},
                "weight": 0.5,
                "required": False,
            },
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        # Check acceptance_results array
        assert len(result.acceptance_results) == 2

        # First validator result
        ar0 = result.acceptance_results[0]
        assert ar0["index"] == 0
        assert ar0["type"] == "file_exists"
        assert ar0["passed"] is True
        assert ar0["weight"] == 1.5
        assert ar0["required"] is True
        assert "message" in ar0
        assert "score" in ar0
        assert "details" in ar0

        # Second validator result
        ar1 = result.acceptance_results[1]
        assert ar1["index"] == 1
        assert ar1["type"] == "file_exists"
        assert ar1["passed"] is False
        assert ar1["weight"] == 0.5
        assert ar1["required"] is False


# =============================================================================
# Test evaluate_and_update_run
# =============================================================================

class TestEvaluateAndUpdateRun:
    """Test evaluate_and_update_run method."""

    def test_updates_run_final_verdict(self, acceptance_gate, mock_run, tmp_path):
        """Step 9: Set AgentRun.final_verdict based on gate result."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate_and_update_run(mock_run, spec)

        assert mock_run.final_verdict == "passed"
        assert result.verdict == "passed"

    def test_updates_run_acceptance_results(self, acceptance_gate, mock_run, tmp_path):
        """Step 10: Store acceptance_results JSON in AgentRun."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate_and_update_run(mock_run, spec)

        assert mock_run.acceptance_results is not None
        assert len(mock_run.acceptance_results) == 1
        assert mock_run.acceptance_results == result.acceptance_results

    def test_returns_gate_result(self, acceptance_gate, mock_run, tmp_path):
        """Step 11: Return overall verdict."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate_and_update_run(mock_run, spec)

        assert isinstance(result, GateResult)
        assert result.passed is True
        assert result.verdict == "passed"


# =============================================================================
# Test Dict-based AcceptanceSpec
# =============================================================================

class TestDictBasedSpec:
    """Test using dict instead of model for acceptance_spec."""

    def test_dict_spec_works(self, acceptance_gate, mock_run, tmp_path):
        """AcceptanceGate should work with dict-based specs."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec_dict = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            ],
            "gate_mode": "all_pass",
        }

        result = acceptance_gate.evaluate(mock_run, spec_dict)

        assert result.passed is True
        assert result.verdict == "passed"

    def test_dict_spec_default_gate_mode(self, acceptance_gate, mock_run, tmp_path):
        """Dict spec without gate_mode defaults to all_pass."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec_dict = {
            "validators": [
                {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            ],
        }

        result = acceptance_gate.evaluate(mock_run, spec_dict)

        assert result.gate_mode == "all_pass"


# =============================================================================
# Test Summary Building
# =============================================================================

class TestSummaryBuilding:
    """Test summary string generation."""

    def test_summary_includes_counts(self, acceptance_gate, mock_run, tmp_path):
        """Summary should include pass/fail counts."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert "1/2 validators passed" in result.summary
        assert "gate_mode=all_pass" in result.summary

    def test_summary_includes_required_failed(self, acceptance_gate, mock_run):
        """Summary should note if required validator failed."""
        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": True},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert "required validator failed" in result.summary


# =============================================================================
# Test Integration with Different Validator Types
# =============================================================================

class TestValidatorTypeIntegration:
    """Test AcceptanceGate with different validator types."""

    def test_test_pass_validator(self, acceptance_gate, mock_run):
        """AcceptanceGate should work with test_pass validator."""
        spec = MagicMock()
        spec.validators = [
            {
                "type": "test_pass",
                "config": {"command": "echo hello", "expected_exit_code": 0},
                "required": False,
            },
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert len(result.validator_results) == 1
        assert result.validator_results[0].passed is True

    def test_forbidden_patterns_validator(self, acceptance_gate, mock_run):
        """AcceptanceGate should work with forbidden_patterns validator."""
        # Mock run needs events for forbidden_patterns
        mock_run.events = []

        spec = MagicMock()
        spec.validators = [
            {
                "type": "forbidden_patterns",
                "config": {"patterns": ["rm -rf /"]},
                "required": False,
            },
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        # Should pass since there are no events with forbidden patterns
        assert len(result.validator_results) == 1
        assert result.validator_results[0].passed is True


# =============================================================================
# Test Feature #35 Verification Steps
# =============================================================================

class TestFeature35VerificationSteps:
    """Explicitly test each verification step from Feature #35."""

    def test_step1_acceptance_gate_class(self):
        """Step 1: Create AcceptanceGate class with evaluate(run, acceptance_spec) method."""
        gate = AcceptanceGate()
        assert hasattr(gate, "evaluate")

        # Check method signature accepts run and acceptance_spec
        import inspect
        sig = inspect.signature(gate.evaluate)
        params = list(sig.parameters.keys())
        assert "run" in params
        assert "acceptance_spec" in params

    def test_step2_iterate_validators(self, acceptance_gate, mock_run, tmp_path):
        """Step 2: Iterate through validators array."""
        file1 = tmp_path / "f1.txt"
        file2 = tmp_path / "f2.txt"
        file3 = tmp_path / "f3.txt"
        file1.write_text("1")
        file2.write_text("2")
        file3.write_text("3")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": str(file2)}, "required": False},
            {"type": "file_exists", "config": {"path": str(file3)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        # All 3 validators should have been evaluated
        assert len(result.validator_results) == 3
        assert len(result.acceptance_results) == 3

    def test_step3_instantiate_validator_class(self, acceptance_gate, mock_run, tmp_path):
        """Step 3: Instantiate appropriate validator class for each type."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "test_pass", "config": {"command": "true"}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        # Each validator type should produce correct validator_type in result
        assert result.acceptance_results[0]["type"] == "file_exists"
        assert result.acceptance_results[1]["type"] == "test_pass"

    def test_step4_collect_validator_result(self, acceptance_gate, mock_run, tmp_path):
        """Step 4: Execute validator and collect ValidatorResult."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        # Should have ValidatorResult objects
        assert len(result.validator_results) == 1
        assert isinstance(result.validator_results[0], ValidatorResult)
        assert result.validator_results[0].passed is True
        assert result.validator_results[0].message is not None

    def test_step5_required_flag(self, acceptance_gate, mock_run, tmp_path):
        """Step 5: Check required flag - required validators must always pass."""
        optional_file = tmp_path / "optional.txt"
        optional_file.write_text("test")

        spec = MagicMock()
        spec.validators = [
            # Required fails
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": True},
            # Optional passes
            {"type": "file_exists", "config": {"path": str(optional_file)}, "required": False},
        ]
        spec.gate_mode = "any_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        # Gate should fail due to required validator
        assert result.passed is False
        assert result.required_failed is True

    def test_step6_all_pass_mode(self, acceptance_gate, mock_run, tmp_path):
        """Step 6: For all_pass mode: verdict = passed if all passed."""
        file1 = tmp_path / "f1.txt"
        file2 = tmp_path / "f2.txt"
        file1.write_text("1")
        file2.write_text("2")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": str(file2)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.verdict == "passed"

    def test_step7_any_pass_mode(self, acceptance_gate, mock_run, tmp_path):
        """Step 7: For any_pass mode: verdict = passed if any passed."""
        file1 = tmp_path / "exists.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
            {"type": "file_exists", "config": {"path": "/nonexistent.txt"}, "required": False},
        ]
        spec.gate_mode = "any_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert result.passed is True
        assert result.verdict == "passed"

    def test_step8_acceptance_results_array(self, acceptance_gate, mock_run, tmp_path):
        """Step 8: Build acceptance_results array with per-validator outcomes."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "weight": 2.0, "required": True},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        ar = result.acceptance_results[0]
        assert ar["index"] == 0
        assert ar["type"] == "file_exists"
        assert ar["passed"] is True
        assert ar["weight"] == 2.0
        assert ar["required"] is True
        assert "message" in ar
        assert "score" in ar

    def test_step9_set_final_verdict(self, acceptance_gate, mock_run, tmp_path):
        """Step 9: Set AgentRun.final_verdict based on gate result."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        acceptance_gate.evaluate_and_update_run(mock_run, spec)

        assert mock_run.final_verdict == "passed"

    def test_step10_store_acceptance_results(self, acceptance_gate, mock_run, tmp_path):
        """Step 10: Store acceptance_results JSON in AgentRun."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate_and_update_run(mock_run, spec)

        assert mock_run.acceptance_results is not None
        assert isinstance(mock_run.acceptance_results, list)
        assert len(mock_run.acceptance_results) == 1

    def test_step11_return_verdict(self, acceptance_gate, mock_run, tmp_path):
        """Step 11: Return overall verdict."""
        file1 = tmp_path / "test.txt"
        file1.write_text("test")

        spec = MagicMock()
        spec.validators = [
            {"type": "file_exists", "config": {"path": str(file1)}, "required": False},
        ]
        spec.gate_mode = "all_pass"

        result = acceptance_gate.evaluate(mock_run, spec)

        assert isinstance(result, GateResult)
        assert result.verdict == "passed"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
