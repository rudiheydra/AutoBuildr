#!/usr/bin/env python3
"""
Verification Script for Feature #55: Validator Generation from Feature Steps

This script verifies all 7 feature steps are correctly implemented.

Feature #55 Verification Steps:
1. Analyze each feature step for validator hints
2. If step contains run/execute, create test_pass validator
3. If step mentions file/path, create file_exists validator
4. If step mentions should not/must not, create forbidden_patterns
5. Extract command or path from step text
6. Set appropriate timeout for test_pass validators
7. Return array of validator configs
"""
import sys
import importlib.util
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct import from the module file to avoid dspy dependency
validator_generator_path = project_root / "api" / "validator_generator.py"
spec = importlib.util.spec_from_file_location("validator_generator", validator_generator_path)
validator_generator = importlib.util.module_from_spec(spec)
sys.modules["validator_generator"] = validator_generator
spec.loader.exec_module(validator_generator)

ValidatorGenerator = validator_generator.ValidatorGenerator
ValidatorConfig = validator_generator.ValidatorConfig
generate_validators_from_steps = validator_generator.generate_validators_from_steps
analyze_step = validator_generator.analyze_step
COMMAND_TIMEOUTS = validator_generator.COMMAND_TIMEOUTS
DEFAULT_TIMEOUT = validator_generator.DEFAULT_TIMEOUT


def print_result(step_num: int, description: str, passed: bool, details: str = ""):
    """Print a verification result."""
    status = "PASS" if passed else "FAIL"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    print(f"  Step {step_num}: {color}[{status}]{reset} {description}")
    if details:
        print(f"           {details}")


def verify_step_1():
    """Step 1: Analyze each feature step for validator hints"""
    print("\nStep 1: Analyze each feature step for validator hints")

    passed = True

    # Test that analyze_step returns analysis info
    result = analyze_step("Run pytest tests/ to verify")
    if not isinstance(result, dict):
        passed = False
        print_result(1, "analyze_step returns dict", False)
    elif "has_execute_keywords" not in result:
        passed = False
        print_result(1, "has_execute_keywords in result", False)
    elif "has_file_keywords" not in result:
        passed = False
        print_result(1, "has_file_keywords in result", False)
    elif "has_forbidden_keywords" not in result:
        passed = False
        print_result(1, "has_forbidden_keywords in result", False)
    else:
        print_result(1, "Analyze step returns validator hints", True,
                    f"execute={result['has_execute_keywords']}, file={result['has_file_keywords']}, forbidden={result['has_forbidden_keywords']}")

    return passed


def verify_step_2():
    """Step 2: If step contains run/execute, create test_pass validator"""
    print("\nStep 2: If step contains run/execute, create test_pass validator")

    passed = True

    # Test run keyword
    validators = generate_validators_from_steps(["Run pytest tests/ to verify"])
    test_pass = [v for v in validators if v["type"] == "test_pass"]
    if len(test_pass) < 1:
        passed = False
        print_result(2, "Run keyword creates test_pass", False)
    else:
        print_result(2, "Run keyword creates test_pass", True, f"command={test_pass[0]['config'].get('command')}")

    # Test execute keyword
    validators = generate_validators_from_steps(["Execute `npm run build` to compile"])
    test_pass = [v for v in validators if v["type"] == "test_pass"]
    if len(test_pass) < 1:
        passed = False
        print_result(2, "Execute keyword creates test_pass", False)
    else:
        print_result(2, "Execute keyword creates test_pass", True, f"command={test_pass[0]['config'].get('command')}")

    return passed


def verify_step_3():
    """Step 3: If step mentions file/path, create file_exists validator"""
    print("\nStep 3: If step mentions file/path, create file_exists validator")

    passed = True

    # Test file keyword
    validators = generate_validators_from_steps(["File config.json should exist"])
    file_exists = [v for v in validators if v["type"] == "file_exists"]
    if len(file_exists) < 1:
        passed = False
        print_result(3, "File keyword creates file_exists", False)
    else:
        print_result(3, "File keyword creates file_exists", True, f"path={file_exists[0]['config'].get('path')}")

    # Test path with extension
    validators = generate_validators_from_steps(["Verify api/models.py exists"])
    file_exists = [v for v in validators if v["type"] == "file_exists"]
    if len(file_exists) < 1:
        passed = False
        print_result(3, "Path with extension creates file_exists", False)
    else:
        print_result(3, "Path with extension creates file_exists", True, f"path={file_exists[0]['config'].get('path')}")

    return passed


def verify_step_4():
    """Step 4: If step mentions should not/must not, create forbidden_patterns"""
    print("\nStep 4: If step mentions should not/must not, create forbidden_patterns")

    passed = True

    # Test should not
    validators = generate_validators_from_steps(["Output should not contain passwords"])
    forbidden = [v for v in validators if v["type"] == "forbidden_patterns"]
    if len(forbidden) < 1:
        passed = False
        print_result(4, "should not creates forbidden_patterns", False)
    else:
        print_result(4, "should not creates forbidden_patterns", True, f"patterns={forbidden[0]['config'].get('patterns')}")

    # Test must not
    validators = generate_validators_from_steps(["Code must not include secrets"])
    forbidden = [v for v in validators if v["type"] == "forbidden_patterns"]
    if len(forbidden) < 1:
        passed = False
        print_result(4, "must not creates forbidden_patterns", False)
    else:
        print_result(4, "must not creates forbidden_patterns", True, f"patterns={forbidden[0]['config'].get('patterns')}")

    # Test that "should not exist" goes to file_exists, not forbidden_patterns
    validators = generate_validators_from_steps(["File temp.log should not exist"])
    file_exists = [v for v in validators if v["type"] == "file_exists"]
    if len(file_exists) < 1:
        passed = False
        print_result(4, "should not exist creates file_exists", False)
    else:
        should_exist = file_exists[0]['config'].get('should_exist')
        print_result(4, "should not exist creates file_exists", should_exist == False, f"should_exist={should_exist}")
        if should_exist != False:
            passed = False

    return passed


def verify_step_5():
    """Step 5: Extract command or path from step text"""
    print("\nStep 5: Extract command or path from step text")

    passed = True

    # Test command extraction from backticks
    validators = generate_validators_from_steps(["Run `pytest tests/ -v` to verify"])
    test_pass = [v for v in validators if v["type"] == "test_pass"]
    if len(test_pass) < 1:
        passed = False
        print_result(5, "Extract command from backticks", False)
    else:
        cmd = test_pass[0]['config'].get('command')
        if cmd == "pytest tests/ -v":
            print_result(5, "Extract command from backticks", True, f"command='{cmd}'")
        else:
            passed = False
            print_result(5, "Extract command from backticks", False, f"got '{cmd}', expected 'pytest tests/ -v'")

    # Test path extraction
    validators = generate_validators_from_steps(["Verify src/config.json exists"])
    file_exists = [v for v in validators if v["type"] == "file_exists"]
    if len(file_exists) < 1:
        passed = False
        print_result(5, "Extract path from step", False)
    else:
        path = file_exists[0]['config'].get('path')
        if path == "src/config.json":
            print_result(5, "Extract path from step", True, f"path='{path}'")
        else:
            passed = False
            print_result(5, "Extract path from step", False, f"got '{path}', expected 'src/config.json'")

    return passed


def verify_step_6():
    """Step 6: Set appropriate timeout for test_pass validators"""
    print("\nStep 6: Set appropriate timeout for test_pass validators")

    passed = True

    # Test pytest timeout
    validators = generate_validators_from_steps(["Run pytest tests/ to verify"])
    test_pass = [v for v in validators if v["type"] == "test_pass"]
    if len(test_pass) < 1:
        passed = False
        print_result(6, "pytest timeout set correctly", False)
    else:
        timeout = test_pass[0]['config'].get('timeout_seconds')
        expected = COMMAND_TIMEOUTS.get("pytest", DEFAULT_TIMEOUT)
        if timeout == expected:
            print_result(6, "pytest timeout set correctly", True, f"timeout={timeout}s")
        else:
            passed = False
            print_result(6, "pytest timeout set correctly", False, f"got {timeout}s, expected {expected}s")

    # Test build timeout
    validators = generate_validators_from_steps(["Run `npm run build` to compile"])
    test_pass = [v for v in validators if v["type"] == "test_pass"]
    if len(test_pass) < 1:
        passed = False
        print_result(6, "build timeout set correctly", False)
    else:
        timeout = test_pass[0]['config'].get('timeout_seconds')
        expected = COMMAND_TIMEOUTS.get("build", DEFAULT_TIMEOUT)
        if timeout == expected:
            print_result(6, "build timeout set correctly", True, f"timeout={timeout}s")
        else:
            passed = False
            print_result(6, "build timeout set correctly", False, f"got {timeout}s, expected {expected}s")

    return passed


def verify_step_7():
    """Step 7: Return array of validator configs"""
    print("\nStep 7: Return array of validator configs")

    passed = True

    # Test that output is array
    result = generate_validators_from_steps(["Run pytest tests/"])
    if not isinstance(result, list):
        passed = False
        print_result(7, "Returns array", False, f"got {type(result).__name__}")
    else:
        print_result(7, "Returns array", True, f"length={len(result)}")

    # Test validator config structure
    if len(result) > 0:
        config = result[0]
        has_type = "type" in config
        has_config = "config" in config
        has_weight = "weight" in config
        has_required = "required" in config

        if all([has_type, has_config, has_weight, has_required]):
            print_result(7, "Validator config has required fields", True,
                        f"type={config.get('type')}, weight={config.get('weight')}, required={config.get('required')}")
        else:
            passed = False
            print_result(7, "Validator config has required fields", False,
                        f"type={has_type}, config={has_config}, weight={has_weight}, required={has_required}")
    else:
        passed = False
        print_result(7, "Validator config structure", False, "no validators generated")

    return passed


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #55: Validator Generation from Feature Steps")
    print("=" * 70)

    results = []

    results.append(("Step 1: Analyze each feature step for validator hints", verify_step_1()))
    results.append(("Step 2: If step contains run/execute, create test_pass validator", verify_step_2()))
    results.append(("Step 3: If step mentions file/path, create file_exists validator", verify_step_3()))
    results.append(("Step 4: If step mentions should not/must not, create forbidden_patterns", verify_step_4()))
    results.append(("Step 5: Extract command or path from step text", verify_step_5()))
    results.append(("Step 6: Set appropriate timeout for test_pass validators", verify_step_6()))
    results.append(("Step 7: Return array of validator configs", verify_step_7()))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for name, passed in results:
        status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
        print(f"  [{status}] {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("\033[92mAll verification steps PASSED!\033[0m")
        print("Feature #55 is ready to be marked as passing.")
        return 0
    else:
        print("\033[91mSome verification steps FAILED.\033[0m")
        print("Please review and fix the failing steps.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
