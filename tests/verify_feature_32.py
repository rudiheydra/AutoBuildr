#!/usr/bin/env python3
"""
Verification script for Feature #32: test_pass Acceptance Validator

This script verifies all 11 steps of Feature #32:
1. Create TestPassValidator class implementing Validator interface
2. Extract command from validator config
3. Extract expected_exit_code (default 0)
4. Extract timeout_seconds (default 60)
5. Execute command via subprocess with timeout
6. Capture stdout and stderr
7. Compare exit code to expected
8. Return ValidatorResult with passed boolean
9. Include command output in result message
10. Handle timeout as failure
11. Handle command not found as failure
"""

import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_result(step: int, description: str, passed: bool, details: str = ""):
    """Print formatted verification result."""
    status = "PASS" if passed else "FAIL"
    marker = "+" if passed else "-"
    print(f"[{marker}] Step {step}: {description} - {status}")
    if details:
        for line in details.split("\n"):
            print(f"    {line}")


def verify_all_steps():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #32: test_pass Acceptance Validator - Verification")
    print("=" * 70)
    print()

    results = []

    # Step 1: Create TestPassValidator class implementing Validator interface
    try:
        from api.validators import (
            TestPassValidator,
            Validator,
            ValidatorResult,
            VALIDATOR_REGISTRY,
            get_validator,
        )

        checks = []

        # Check class exists
        checks.append(TestPassValidator is not None)

        # Check is subclass of Validator
        checks.append(issubclass(TestPassValidator, Validator))

        # Check has validator_type attribute
        validator = TestPassValidator()
        checks.append(hasattr(validator, "validator_type"))
        checks.append(validator.validator_type == "test_pass")

        # Check has evaluate method
        checks.append(hasattr(validator, "evaluate"))
        checks.append(callable(validator.evaluate))

        # Check registered in VALIDATOR_REGISTRY
        checks.append("test_pass" in VALIDATOR_REGISTRY)
        checks.append(VALIDATOR_REGISTRY.get("test_pass") == TestPassValidator)

        # Check get_validator returns instance
        instance = get_validator("test_pass")
        checks.append(isinstance(instance, TestPassValidator))

        passed = all(checks)
        results.append(passed)
        print_result(
            1,
            "Create TestPassValidator class implementing Validator interface",
            passed,
            f"Class exists: {checks[0]}, Subclass of Validator: {checks[1]}, "
            f"validator_type='test_pass': {checks[3]}, Registered: {checks[6]}"
        )
    except Exception as e:
        results.append(False)
        print_result(1, "Create TestPassValidator class implementing Validator interface", False, f"Error: {e}")

    # Step 2: Extract command from validator config
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Missing command should fail
        result1 = validator.evaluate({}, {})
        checks1 = result1.passed is False and "command" in result1.message.lower()

        # Valid command should be extracted
        result2 = validator.evaluate({"command": "echo test"}, {})
        checks2 = "echo test" in result2.details.get("interpolated_command", "")

        # Variable interpolation
        result3 = validator.evaluate({"command": "echo {msg}"}, {"msg": "hello"})
        checks3 = "echo hello" in result3.details.get("interpolated_command", "")

        passed = checks1 and checks2 and checks3
        results.append(passed)
        print_result(
            2,
            "Extract command from validator config",
            passed,
            f"Missing command fails: {checks1}, Valid command extracted: {checks2}, "
            f"Variable interpolation: {checks3}"
        )
    except Exception as e:
        results.append(False)
        print_result(2, "Extract command from validator config", False, f"Error: {e}")

    # Step 3: Extract expected_exit_code (default 0)
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Default should be 0
        result1 = validator.evaluate({"command": "exit 0"}, {})
        checks1 = result1.details.get("expected_exit_code") == 0

        # Custom exit code
        result2 = validator.evaluate({"command": "exit 5", "expected_exit_code": 5}, {})
        checks2 = result2.details.get("expected_exit_code") == 5 and result2.passed is True

        # String exit code
        result3 = validator.evaluate({"command": "exit 3", "expected_exit_code": "3"}, {})
        checks3 = result3.details.get("expected_exit_code") == 3 and result3.passed is True

        passed = checks1 and checks2 and checks3
        results.append(passed)
        print_result(
            3,
            "Extract expected_exit_code (default 0)",
            passed,
            f"Default is 0: {checks1}, Custom exit code works: {checks2}, "
            f"String exit code works: {checks3}"
        )
    except Exception as e:
        results.append(False)
        print_result(3, "Extract expected_exit_code (default 0)", False, f"Error: {e}")

    # Step 4: Extract timeout_seconds (default 60)
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Default should be 60
        result1 = validator.evaluate({"command": "echo test"}, {})
        checks1 = result1.details.get("timeout_seconds") == 60

        # Custom timeout
        result2 = validator.evaluate({"command": "echo test", "timeout_seconds": 30}, {})
        checks2 = result2.details.get("timeout_seconds") == 30

        # String timeout
        result3 = validator.evaluate({"command": "echo test", "timeout_seconds": "45"}, {})
        checks3 = result3.details.get("timeout_seconds") == 45

        passed = checks1 and checks2 and checks3
        results.append(passed)
        print_result(
            4,
            "Extract timeout_seconds (default 60)",
            passed,
            f"Default is 60: {checks1}, Custom timeout works: {checks2}, "
            f"String timeout works: {checks3}"
        )
    except Exception as e:
        results.append(False)
        print_result(4, "Extract timeout_seconds (default 60)", False, f"Error: {e}")

    # Step 5: Execute command via subprocess with timeout
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Simple command execution
        result1 = validator.evaluate({"command": "echo subprocess_test"}, {})
        checks1 = result1.passed is True and "subprocess_test" in result1.details.get("stdout", "")

        # Command with pipes
        result2 = validator.evaluate({"command": "echo 'hello' | grep hello"}, {})
        checks2 = result2.passed is True

        # Command with working directory
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test")
            result3 = validator.evaluate({"command": "ls test.txt", "working_directory": tmpdir}, {})
            checks3 = result3.passed is True

        passed = checks1 and checks2 and checks3
        results.append(passed)
        print_result(
            5,
            "Execute command via subprocess with timeout",
            passed,
            f"Simple command: {checks1}, Pipes work: {checks2}, "
            f"Working directory: {checks3}"
        )
    except Exception as e:
        results.append(False)
        print_result(5, "Execute command via subprocess with timeout", False, f"Error: {e}")

    # Step 6: Capture stdout and stderr
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Capture stdout
        result1 = validator.evaluate({"command": "echo 'stdout_output'"}, {})
        checks1 = "stdout_output" in result1.details.get("stdout", "")

        # Capture stderr
        result2 = validator.evaluate({"command": "echo 'stderr_output' >&2"}, {})
        checks2 = "stderr_output" in result2.details.get("stderr", "")

        passed = checks1 and checks2
        results.append(passed)
        print_result(
            6,
            "Capture stdout and stderr",
            passed,
            f"stdout captured: {checks1}, stderr captured: {checks2}"
        )
    except Exception as e:
        results.append(False)
        print_result(6, "Capture stdout and stderr", False, f"Error: {e}")

    # Step 7: Compare exit code to expected
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Exit 0 passes by default
        result1 = validator.evaluate({"command": "exit 0"}, {})
        checks1 = result1.passed is True and result1.details.get("actual_exit_code") == 0

        # Exit 1 fails by default
        result2 = validator.evaluate({"command": "exit 1"}, {})
        checks2 = result2.passed is False and result2.details.get("actual_exit_code") == 1

        # Exit 5 passes when expected is 5
        result3 = validator.evaluate({"command": "exit 5", "expected_exit_code": 5}, {})
        checks3 = result3.passed is True and result3.details.get("actual_exit_code") == 5

        passed = checks1 and checks2 and checks3
        results.append(passed)
        print_result(
            7,
            "Compare exit code to expected",
            passed,
            f"Exit 0 passes: {checks1}, Exit 1 fails: {checks2}, "
            f"Custom expected works: {checks3}"
        )
    except Exception as e:
        results.append(False)
        print_result(7, "Compare exit code to expected", False, f"Error: {e}")

    # Step 8: Return ValidatorResult with passed boolean
    try:
        from api.validators import TestPassValidator, ValidatorResult

        validator = TestPassValidator()

        result = validator.evaluate({"command": "echo test"}, {})

        checks = []
        checks.append(isinstance(result, ValidatorResult))
        checks.append(isinstance(result.passed, bool))
        checks.append(isinstance(result.message, str))
        checks.append(result.score in (0.0, 1.0))
        checks.append(result.validator_type == "test_pass")

        passed = all(checks)
        results.append(passed)
        print_result(
            8,
            "Return ValidatorResult with passed boolean",
            passed,
            f"Is ValidatorResult: {checks[0]}, passed is bool: {checks[1]}, "
            f"Has message: {checks[2]}, Score valid: {checks[3]}, "
            f"validator_type correct: {checks[4]}"
        )
    except Exception as e:
        results.append(False)
        print_result(8, "Return ValidatorResult with passed boolean", False, f"Error: {e}")

    # Step 9: Include command output in result message
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        # Check stdout in details
        result1 = validator.evaluate({"command": "echo 'unique_output_xyz'"}, {})
        checks1 = "unique_output_xyz" in result1.details.get("stdout", "")

        # Check stderr in details
        result2 = validator.evaluate({"command": "echo 'error_xyz' >&2"}, {})
        checks2 = "error_xyz" in result2.details.get("stderr", "")

        # Check message includes exit code
        result3 = validator.evaluate({"command": "exit 7", "expected_exit_code": 0}, {})
        checks3 = "7" in result3.message

        # Check description included
        result4 = validator.evaluate({"command": "echo test", "description": "Test desc"}, {})
        checks4 = "Test desc" in result4.message

        passed = checks1 and checks2 and checks3 and checks4
        results.append(passed)
        print_result(
            9,
            "Include command output in result message",
            passed,
            f"stdout in details: {checks1}, stderr in details: {checks2}, "
            f"Exit code in message: {checks3}, Description included: {checks4}"
        )
    except Exception as e:
        results.append(False)
        print_result(9, "Include command output in result message", False, f"Error: {e}")

    # Step 10: Handle timeout as failure
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        result = validator.evaluate({"command": "sleep 5", "timeout_seconds": 1}, {})

        checks = []
        checks.append(result.passed is False)
        checks.append("timed out" in result.message.lower() or "timeout" in result.message.lower())
        checks.append(result.details.get("error") == "timeout")
        checks.append(result.score == 0.0)

        passed = all(checks)
        results.append(passed)
        print_result(
            10,
            "Handle timeout as failure",
            passed,
            f"passed=False: {checks[0]}, Message mentions timeout: {checks[1]}, "
            f"error='timeout': {checks[2]}, score=0.0: {checks[3]}"
        )
    except Exception as e:
        results.append(False)
        print_result(10, "Handle timeout as failure", False, f"Error: {e}")

    # Step 11: Handle command not found as failure
    try:
        from api.validators import TestPassValidator

        validator = TestPassValidator()

        result = validator.evaluate({"command": "nonexistent_command_xyz12345"}, {})

        checks = []
        checks.append(result.passed is False)
        checks.append(result.score == 0.0)
        # On shell=True, command not found returns exit code 127
        checks.append(
            result.details.get("actual_exit_code") == 127 or
            result.details.get("error") == "command_not_found"
        )

        passed = all(checks)
        results.append(passed)
        print_result(
            11,
            "Handle command not found as failure",
            passed,
            f"passed=False: {checks[0]}, score=0.0: {checks[1]}, "
            f"Indicates command not found: {checks[2]}"
        )
    except Exception as e:
        results.append(False)
        print_result(11, "Handle command not found as failure", False, f"Error: {e}")

    # Summary
    print()
    print("=" * 70)
    passed_count = sum(results)
    total_count = len(results)
    print(f"Results: {passed_count}/{total_count} verification steps passed")
    print("=" * 70)

    return all(results)


if __name__ == "__main__":
    success = verify_all_steps()
    sys.exit(0 if success else 1)
