"""
Tests for Feature #211: Test enforcement gate added to acceptance validators.

This test module validates:
1. Create test_enforcement validator type
2. Validator checks: tests exist, tests ran, tests passed
3. Validator can be required or optional per feature
4. Validator result included in acceptance_results
5. Failed tests block feature completion when required
"""
from __future__ import annotations

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# =============================================================================
# Test Setup and Fixtures
# =============================================================================

@pytest.fixture
def test_project_dir():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create tests directory structure
        tests_dir = Path(tmpdir) / "tests"
        tests_dir.mkdir()

        # Create test files
        (tests_dir / "test_feature_1.py").write_text("def test_example(): pass")
        (tests_dir / "test_feature_2.py").write_text("def test_another(): pass")

        yield tmpdir


@pytest.fixture
def empty_project_dir():
    """Create a temporary project directory without test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@dataclass
class MockEvent:
    """Mock AgentEvent for testing."""
    id: int
    event_type: str
    sequence: int
    payload: dict[str, Any] | None = None
    tool_name: str | None = None


@dataclass
class MockAgentRun:
    """Mock AgentRun for testing."""
    id: str = "test-run-123"
    events: list[MockEvent] = field(default_factory=list)
    turns_used: int = 5


# =============================================================================
# Step 1: Create test_enforcement validator type
# =============================================================================

class TestStep1ValidatorTypeCreated:
    """Test that test_enforcement validator type is created."""

    def test_validator_class_exists(self):
        """TestEnforcementValidator class exists."""
        from api.validators import TestEnforcementValidator
        assert TestEnforcementValidator is not None

    def test_validator_type_attribute(self):
        """Validator has correct validator_type attribute."""
        from api.validators import TestEnforcementValidator
        validator = TestEnforcementValidator()
        assert validator.validator_type == "test_enforcement"

    def test_validator_in_registry(self):
        """Validator is registered in VALIDATOR_REGISTRY."""
        from api.validators import VALIDATOR_REGISTRY, TestEnforcementValidator
        assert "test_enforcement" in VALIDATOR_REGISTRY
        assert VALIDATOR_REGISTRY["test_enforcement"] == TestEnforcementValidator

    def test_get_validator_returns_instance(self):
        """get_validator() returns TestEnforcementValidator instance."""
        from api.validators import get_validator, TestEnforcementValidator
        validator = get_validator("test_enforcement")
        assert validator is not None
        assert isinstance(validator, TestEnforcementValidator)

    def test_validator_type_in_types_list(self):
        """test_enforcement is in VALIDATOR_TYPES list."""
        from api.agentspec_models import VALIDATOR_TYPES
        assert "test_enforcement" in VALIDATOR_TYPES

    def test_validator_exported_from_api(self):
        """TestEnforcementValidator is exported from api package."""
        from api import TestEnforcementValidator
        assert TestEnforcementValidator is not None


# =============================================================================
# Step 2: Validator checks - tests exist, tests ran, tests passed
# =============================================================================

class TestStep2ValidatorChecksTestsExist:
    """Test validator checks if tests exist."""

    def test_tests_exist_passes_with_test_files(self, test_project_dir):
        """Validator passes when test files exist."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": f"{test_project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)

        assert result.passed is True
        assert result.details["enforcement_status"]["tests_exist"] is True
        assert result.details["enforcement_status"]["test_files_found"] >= 1

    def test_tests_exist_fails_without_test_files(self, empty_project_dir):
        """Validator fails when no test files exist."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": f"{empty_project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        context = {"project_dir": empty_project_dir}

        result = validator.evaluate(config, context)

        assert result.passed is False
        assert result.details["enforcement_status"]["tests_exist"] is False
        assert "No test files found" in result.message

    def test_min_tests_enforcement(self, test_project_dir):
        """Validator enforces minimum test file count."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": f"{test_project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
            "min_tests": 5,  # More than we have
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)

        assert result.passed is False
        assert "minimum required" in result.message.lower()

    def test_pattern_interpolation(self, test_project_dir):
        """Validator interpolates variables in pattern."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": "{project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)

        assert result.passed is True
        assert result.details["enforcement_status"]["tests_exist"] is True


class TestStep2ValidatorChecksTestsRan:
    """Test validator checks if tests ran."""

    def test_tests_ran_via_context(self, test_project_dir):
        """Validator detects tests ran via context test_results."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": False,
        }
        context = {
            "project_dir": test_project_dir,
            "test_results": {
                "total_tests": 10,
                "passed_tests": 8,
                "failed_tests": 2,
                "passed": False,
            },
        }

        result = validator.evaluate(config, context)

        assert result.passed is True
        assert result.details["enforcement_status"]["tests_ran"] is True
        assert result.details["enforcement_status"]["tests_total"] == 10

    def test_tests_ran_via_events(self, test_project_dir):
        """Validator detects tests ran via tests_executed events."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": False,
            "check_events": True,
        }
        context = {"project_dir": test_project_dir}

        run = MockAgentRun(
            events=[
                MockEvent(
                    id=1,
                    event_type="tests_executed",
                    sequence=1,
                    payload={
                        "total_tests": 5,
                        "passed_tests": 5,
                        "failed_tests": 0,
                        "passed": True,
                    },
                )
            ]
        )

        result = validator.evaluate(config, context, run)

        assert result.passed is True
        assert result.details["enforcement_status"]["tests_ran"] is True
        assert result.details["enforcement_status"]["test_execution_events"] == 1

    def test_tests_not_ran_fails(self, test_project_dir):
        """Validator fails when tests have not run."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        run = MockAgentRun(events=[])  # No test events

        result = validator.evaluate(config, context, run)

        assert result.passed is False
        assert result.details["enforcement_status"]["tests_ran"] is False
        assert "Tests have not been executed" in result.message


class TestStep2ValidatorChecksTestsPassed:
    """Test validator checks if tests passed."""

    def test_tests_passed_with_all_passing(self, test_project_dir):
        """Validator passes when all tests pass."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": True,
        }
        context = {
            "project_dir": test_project_dir,
            "test_results": {
                "total_tests": 10,
                "passed_tests": 10,
                "failed_tests": 0,
                "passed": True,
            },
        }

        result = validator.evaluate(config, context)

        assert result.passed is True
        assert result.details["enforcement_status"]["tests_passed"] is True

    def test_tests_failed_blocks_when_required(self, test_project_dir):
        """Validator fails when tests failed and required."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": True,
        }
        context = {
            "project_dir": test_project_dir,
            "test_results": {
                "total_tests": 10,
                "passed_tests": 8,
                "failed_tests": 2,
                "passed": False,
            },
        }

        result = validator.evaluate(config, context)

        assert result.passed is False
        assert "Tests failed" in result.message


# =============================================================================
# Step 3: Validator can be required or optional per feature
# =============================================================================

class TestStep3RequiredOrOptional:
    """Test validator can be required or optional."""

    def test_required_validator_blocks_on_failure(self, test_project_dir):
        """Required validator blocks feature completion on failure."""
        from api.validators import evaluate_validator

        validator_def = {
            "type": "test_enforcement",
            "config": {
                "test_file_pattern": "{project_dir}/tests/nonexistent_*.py",
                "require_tests_exist": True,
                "require_tests_ran": False,
                "require_tests_passed": False,
            },
            "required": True,
        }
        context = {"project_dir": test_project_dir}

        result = evaluate_validator(validator_def, context)

        assert result.passed is False

    def test_optional_validator_advisory_only(self, test_project_dir):
        """Optional validator is advisory only (still reports failure)."""
        from api.validators import evaluate_validator, AcceptanceGate

        validator_def = {
            "type": "test_enforcement",
            "config": {
                "require_tests_exist": False,
                "require_tests_ran": False,
                "require_tests_passed": False,
            },
            "required": False,
        }
        context = {"project_dir": test_project_dir}

        result = evaluate_validator(validator_def, context)

        # With all requirements disabled, should pass
        assert result.passed is True

    def test_optional_failures_dont_block_gate_any_pass(self, test_project_dir):
        """Optional validator failures don't block gate in any_pass mode."""
        from api.validators import AcceptanceGate

        # Create mock acceptance spec with one passing validator
        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "require_tests_exist": True,
                        "require_tests_ran": True,
                        "require_tests_passed": True,
                    },
                    "required": False,
                },
                {
                    "type": "custom",
                    "config": {"description": "Always passes"},
                    "required": False,
                },
            ],
            "gate_mode": "any_pass",
        }

        run = MockAgentRun()
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        # any_pass mode should pass if at least one validator passes
        assert result.passed is True

    def test_required_failures_block_gate_regardless_of_mode(self, test_project_dir):
        """Required validator failures block gate regardless of mode."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "test_file_pattern": "{project_dir}/nonexistent/test_*.py",
                        "require_tests_exist": True,
                        "require_tests_ran": False,
                        "require_tests_passed": False,
                    },
                    "required": True,  # Required!
                },
                {
                    "type": "custom",
                    "config": {"description": "Always passes"},
                    "required": False,
                },
            ],
            "gate_mode": "any_pass",
        }

        run = MockAgentRun()
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        # Required validator failure blocks even in any_pass mode
        assert result.passed is False
        assert result.required_failed is True


# =============================================================================
# Step 4: Validator result included in acceptance_results
# =============================================================================

class TestStep4ResultInAcceptanceResults:
    """Test validator result is included in acceptance_results."""

    def test_result_included_in_acceptance_gate(self, test_project_dir):
        """Validator result is included in AcceptanceGate results."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "test_file_pattern": "{project_dir}/tests/test_*.py",
                        "require_tests_exist": True,
                        "require_tests_ran": False,
                        "require_tests_passed": False,
                        "description": "Feature tests must exist",
                    },
                    "required": True,
                },
            ],
            "gate_mode": "all_pass",
        }

        run = MockAgentRun()
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        # Check acceptance_results contains test_enforcement result
        assert len(result.acceptance_results) == 1
        test_enforcement_result = result.acceptance_results[0]

        assert test_enforcement_result["type"] == "test_enforcement"
        assert "passed" in test_enforcement_result
        assert "message" in test_enforcement_result
        assert "details" in test_enforcement_result

    def test_result_contains_enforcement_status(self, test_project_dir):
        """Result contains detailed enforcement_status."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": "{project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)

        assert "enforcement_status" in result.details
        status = result.details["enforcement_status"]

        assert "tests_exist" in status
        assert "tests_ran" in status
        assert "tests_passed" in status
        assert "test_files_found" in status
        assert "tests_total" in status

    def test_result_to_dict_serializable(self, test_project_dir):
        """ValidatorResult.to_dict() is JSON serializable."""
        import json
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)
        result_dict = result.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(result_dict)
        assert json_str is not None
        assert len(json_str) > 0


# =============================================================================
# Step 5: Failed tests block feature completion when required
# =============================================================================

class TestStep5FailedTestsBlockCompletion:
    """Test that failed tests block feature completion when required."""

    def test_failed_tests_block_gate_all_pass(self, test_project_dir):
        """Failed tests block gate in all_pass mode."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "require_tests_exist": False,
                        "require_tests_ran": True,
                        "require_tests_passed": True,
                    },
                    "required": True,
                },
            ],
            "gate_mode": "all_pass",
        }

        run = MockAgentRun(
            events=[
                MockEvent(
                    id=1,
                    event_type="tests_executed",
                    sequence=1,
                    payload={
                        "total_tests": 10,
                        "passed_tests": 5,
                        "failed_tests": 5,
                        "passed": False,
                    },
                )
            ]
        )
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        assert result.passed is False
        assert result.verdict == "failed"

    def test_all_tests_passing_allows_completion(self, test_project_dir):
        """All tests passing allows feature completion."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "require_tests_exist": False,
                        "require_tests_ran": True,
                        "require_tests_passed": True,
                    },
                    "required": True,
                },
            ],
            "gate_mode": "all_pass",
        }

        run = MockAgentRun(
            events=[
                MockEvent(
                    id=1,
                    event_type="tests_executed",
                    sequence=1,
                    payload={
                        "total_tests": 10,
                        "passed_tests": 10,
                        "failed_tests": 0,
                        "passed": True,
                    },
                )
            ]
        )
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        assert result.passed is True
        assert result.verdict == "passed"

    def test_missing_tests_blocks_when_required(self, empty_project_dir):
        """Missing test files block completion when tests_exist required."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "test_file_pattern": "{project_dir}/tests/test_*.py",
                        "require_tests_exist": True,
                        "require_tests_ran": False,
                        "require_tests_passed": False,
                    },
                    "required": True,
                },
            ],
            "gate_mode": "all_pass",
        }

        run = MockAgentRun()
        context = {"project_dir": empty_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        assert result.passed is False

    def test_not_run_tests_blocks_when_required(self, test_project_dir):
        """Tests not executed blocks completion when tests_ran required."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {
                        "require_tests_exist": False,
                        "require_tests_ran": True,
                        "require_tests_passed": True,
                    },
                    "required": True,
                },
            ],
            "gate_mode": "all_pass",
        }

        run = MockAgentRun(events=[])  # No test events
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        assert result.passed is False


# =============================================================================
# Additional Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_config_uses_defaults(self, test_project_dir):
        """Empty config uses sensible defaults."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {}  # All defaults
        context = {"project_dir": test_project_dir}

        # Should not crash
        result = validator.evaluate(config, context)

        assert result is not None
        assert result.validator_type == "test_enforcement"

    def test_string_boolean_conversion(self, test_project_dir):
        """String boolean values are converted correctly."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": "true",
            "require_tests_ran": "false",
            "require_tests_passed": "yes",
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)

        # Should handle string booleans
        assert result is not None

    def test_none_run_handled(self, test_project_dir):
        """None run argument handled gracefully."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context, run=None)

        # Should fail because tests didn't run (no events to check)
        assert result.passed is False

    def test_invalid_glob_pattern_handled(self, test_project_dir):
        """Invalid glob pattern doesn't crash."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": "[invalid-glob-pattern",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        context = {"project_dir": test_project_dir}

        # Should not crash, just report no files found
        result = validator.evaluate(config, context)
        assert result is not None

    def test_score_calculation(self, test_project_dir):
        """Score is calculated based on checks passed."""
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()
        config = {
            "test_file_pattern": "{project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": True,  # Will fail
            "require_tests_passed": True,  # Will fail
        }
        context = {"project_dir": test_project_dir}

        result = validator.evaluate(config, context)

        # Only 1 of 3 checks passed (tests_exist), score = 1/3
        assert 0.0 < result.score < 1.0


class TestApiPackageExports:
    """Test API package exports."""

    def test_validator_exported_from_api(self):
        """TestEnforcementValidator is exported from api."""
        from api import TestEnforcementValidator
        assert TestEnforcementValidator is not None

    def test_validator_registry_contains_type(self):
        """VALIDATOR_REGISTRY contains test_enforcement."""
        from api import VALIDATOR_REGISTRY
        assert "test_enforcement" in VALIDATOR_REGISTRY

    def test_validator_types_contains_type(self):
        """VALIDATOR_TYPES contains test_enforcement."""
        from api.agentspec_models import VALIDATOR_TYPES
        assert "test_enforcement" in VALIDATOR_TYPES


class TestFeature211VerificationSteps:
    """Comprehensive tests for Feature #211 verification steps."""

    def test_step1_create_test_enforcement_validator_type(self):
        """
        Step 1: Create test_enforcement validator type.

        Verifies:
        - TestEnforcementValidator class exists
        - validator_type = "test_enforcement"
        - Registered in VALIDATOR_REGISTRY
        - Added to VALIDATOR_TYPES
        """
        from api.validators import TestEnforcementValidator, VALIDATOR_REGISTRY, get_validator
        from api.agentspec_models import VALIDATOR_TYPES
        from api import TestEnforcementValidator as ExportedValidator

        # Class exists
        assert TestEnforcementValidator is not None

        # Correct validator_type
        validator = TestEnforcementValidator()
        assert validator.validator_type == "test_enforcement"

        # In registry
        assert "test_enforcement" in VALIDATOR_REGISTRY
        assert get_validator("test_enforcement") is not None

        # In types list
        assert "test_enforcement" in VALIDATOR_TYPES

        # Exported from api
        assert ExportedValidator is TestEnforcementValidator

    def test_step2_validator_checks_tests_exist_ran_passed(self, test_project_dir):
        """
        Step 2: Validator checks: tests exist, tests ran, tests passed.

        Verifies:
        - Checks if test files exist via pattern
        - Checks if tests were executed via events or context
        - Checks if executed tests passed
        """
        from api.validators import TestEnforcementValidator

        validator = TestEnforcementValidator()

        # Test exists check
        config_exist = {
            "test_file_pattern": "{project_dir}/tests/test_*.py",
            "require_tests_exist": True,
            "require_tests_ran": False,
            "require_tests_passed": False,
        }
        result = validator.evaluate(config_exist, {"project_dir": test_project_dir})
        assert result.details["enforcement_status"]["tests_exist"] is True

        # Test ran check (via context)
        config_ran = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": False,
        }
        context_ran = {
            "project_dir": test_project_dir,
            "test_results": {"total_tests": 5, "passed_tests": 5, "failed_tests": 0, "passed": True},
        }
        result = validator.evaluate(config_ran, context_ran)
        assert result.details["enforcement_status"]["tests_ran"] is True

        # Test passed check
        config_passed = {
            "require_tests_exist": False,
            "require_tests_ran": True,
            "require_tests_passed": True,
        }
        context_passed = {
            "project_dir": test_project_dir,
            "test_results": {"total_tests": 5, "passed_tests": 5, "failed_tests": 0, "passed": True},
        }
        result = validator.evaluate(config_passed, context_passed)
        assert result.details["enforcement_status"]["tests_passed"] is True

    def test_step3_validator_can_be_required_or_optional(self, test_project_dir, empty_project_dir):
        """
        Step 3: Validator can be required or optional per feature.

        Verifies:
        - Validator can be marked as required (blocks gate)
        - Validator can be marked as optional (advisory only)
        """
        from api.validators import AcceptanceGate

        # Required validator blocks gate
        spec_required = {
            "validators": [{
                "type": "test_enforcement",
                "config": {
                    "test_file_pattern": "{project_dir}/tests/test_*.py",
                    "require_tests_exist": True,
                    "require_tests_ran": False,
                    "require_tests_passed": False,
                },
                "required": True,
            }],
            "gate_mode": "all_pass",
        }

        gate = AcceptanceGate()
        result = gate.evaluate(MockAgentRun(), spec_required, {"project_dir": empty_project_dir})
        assert result.passed is False
        assert result.required_failed is True

        # Optional validator doesn't block with other passing validator
        spec_optional = {
            "validators": [
                {
                    "type": "test_enforcement",
                    "config": {"require_tests_exist": True, "require_tests_ran": True, "require_tests_passed": True},
                    "required": False,
                },
                {
                    "type": "custom",
                    "config": {"description": "Pass"},
                    "required": False,
                },
            ],
            "gate_mode": "any_pass",
        }

        result = gate.evaluate(MockAgentRun(), spec_optional, {"project_dir": empty_project_dir})
        assert result.passed is True  # custom passes

    def test_step4_validator_result_in_acceptance_results(self, test_project_dir):
        """
        Step 4: Validator result included in acceptance_results.

        Verifies:
        - Result includes enforcement_status dict
        - Result is part of AcceptanceGate.acceptance_results
        """
        from api.validators import AcceptanceGate

        spec = {
            "validators": [{
                "type": "test_enforcement",
                "config": {
                    "test_file_pattern": "{project_dir}/tests/test_*.py",
                    "require_tests_exist": True,
                    "require_tests_ran": False,
                    "require_tests_passed": False,
                },
                "required": False,
            }],
            "gate_mode": "all_pass",
        }

        gate = AcceptanceGate()
        result = gate.evaluate(MockAgentRun(), spec, {"project_dir": test_project_dir})

        assert len(result.acceptance_results) == 1
        enforcement_result = result.acceptance_results[0]

        assert enforcement_result["type"] == "test_enforcement"
        assert "passed" in enforcement_result
        assert "message" in enforcement_result
        assert "details" in enforcement_result
        assert "enforcement_status" in enforcement_result["details"]

    def test_step5_failed_tests_block_completion_when_required(self, test_project_dir):
        """
        Step 5: Failed tests block feature completion when required.

        Verifies:
        - Failed tests block gate when validator is required
        - Passing tests allow gate to pass
        """
        from api.validators import AcceptanceGate

        spec = {
            "validators": [{
                "type": "test_enforcement",
                "config": {
                    "require_tests_exist": False,
                    "require_tests_ran": True,
                    "require_tests_passed": True,
                },
                "required": True,
            }],
            "gate_mode": "all_pass",
        }

        gate = AcceptanceGate()

        # Failed tests block
        run_failed = MockAgentRun(events=[
            MockEvent(id=1, event_type="tests_executed", sequence=1, payload={
                "total_tests": 10, "passed_tests": 5, "failed_tests": 5, "passed": False,
            })
        ])
        result = gate.evaluate(run_failed, spec, {"project_dir": test_project_dir})
        assert result.passed is False

        # Passing tests allow completion
        run_passed = MockAgentRun(events=[
            MockEvent(id=1, event_type="tests_executed", sequence=1, payload={
                "total_tests": 10, "passed_tests": 10, "failed_tests": 0, "passed": True,
            })
        ])
        result = gate.evaluate(run_passed, spec, {"project_dir": test_project_dir})
        assert result.passed is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for test enforcement validator."""

    def test_full_workflow_tests_exist_ran_passed(self, test_project_dir):
        """Full workflow: tests exist, ran, and passed."""
        from api.validators import AcceptanceGate

        acceptance_spec = {
            "validators": [{
                "type": "test_enforcement",
                "config": {
                    "test_file_pattern": "{project_dir}/tests/test_*.py",
                    "require_tests_exist": True,
                    "require_tests_ran": True,
                    "require_tests_passed": True,
                    "min_tests": 1,
                },
                "required": True,
            }],
            "gate_mode": "all_pass",
        }

        run = MockAgentRun(events=[
            MockEvent(id=1, event_type="tests_executed", sequence=1, payload={
                "total_tests": 5,
                "passed_tests": 5,
                "failed_tests": 0,
                "passed": True,
            })
        ])
        context = {"project_dir": test_project_dir}

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context)

        assert result.passed is True
        assert result.verdict == "passed"

        # Check detailed results
        enforcement_result = result.acceptance_results[0]
        status = enforcement_result["details"]["enforcement_status"]

        assert status["tests_exist"] is True
        assert status["tests_ran"] is True
        assert status["tests_passed"] is True

    def test_evaluate_validator_function(self, test_project_dir):
        """evaluate_validator() works with test_enforcement."""
        from api.validators import evaluate_validator

        validator_def = {
            "type": "test_enforcement",
            "config": {
                "test_file_pattern": "{project_dir}/tests/test_*.py",
                "require_tests_exist": True,
                "require_tests_ran": False,
                "require_tests_passed": False,
            },
            "required": False,
        }
        context = {"project_dir": test_project_dir}

        result = evaluate_validator(validator_def, context)

        assert result is not None
        assert result.validator_type == "test_enforcement"
        assert result.passed is True
