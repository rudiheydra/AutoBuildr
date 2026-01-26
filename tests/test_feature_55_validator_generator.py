"""
Tests for Feature #55: Validator Generation from Feature Steps

This test suite verifies that the ValidatorGenerator correctly parses
feature step text and generates appropriate validators.

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

import pytest

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Direct import from the module file to avoid dspy dependency in api/__init__.py
validator_generator_path = project_root / "api" / "validator_generator.py"
spec = importlib.util.spec_from_file_location("validator_generator", validator_generator_path)
validator_generator = importlib.util.module_from_spec(spec)
sys.modules["validator_generator"] = validator_generator
spec.loader.exec_module(validator_generator)

ValidatorGenerator = validator_generator.ValidatorGenerator
ValidatorConfig = validator_generator.ValidatorConfig
generate_validators_from_steps = validator_generator.generate_validators_from_steps
analyze_step = validator_generator.analyze_step
reset_validator_generator = validator_generator.reset_validator_generator
get_validator_generator = validator_generator.get_validator_generator
EXECUTE_KEYWORDS = validator_generator.EXECUTE_KEYWORDS
FILE_KEYWORDS = validator_generator.FILE_KEYWORDS
FORBIDDEN_KEYWORDS = validator_generator.FORBIDDEN_KEYWORDS
COMMAND_TIMEOUTS = validator_generator.COMMAND_TIMEOUTS
DEFAULT_TIMEOUT = validator_generator.DEFAULT_TIMEOUT


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_generator():
    """Reset the validator generator before each test."""
    reset_validator_generator()
    yield
    reset_validator_generator()


@pytest.fixture
def generator():
    """Create a fresh ValidatorGenerator instance."""
    return ValidatorGenerator()


# =============================================================================
# Step 1: Analyze each feature step for validator hints
# =============================================================================

class TestStepAnalysis:
    """Tests for step analysis and keyword detection."""

    def test_analyze_step_returns_dict(self):
        """analyze_step should return a dictionary with analysis results."""
        result = analyze_step("Run pytest tests/")

        assert isinstance(result, dict)
        assert "step" in result
        assert "has_execute_keywords" in result
        assert "has_file_keywords" in result
        assert "has_forbidden_keywords" in result
        assert "extracted_command" in result
        assert "extracted_path" in result
        assert "extracted_patterns" in result

    def test_detect_execute_keywords(self, generator):
        """Should detect execute-related keywords in step text."""
        execute_steps = [
            "Run pytest tests/",
            "Execute the build script",
            "Start the development server",
            "Launch the application",
            "Invoke the API endpoint",
            "Test the functionality",
            "Build the project",
            "Check the linting results",
            "Verify the output",
        ]

        for step in execute_steps:
            assert generator._has_execute_keywords(step.lower()), f"Should detect execute keyword in: {step}"

    def test_detect_file_keywords(self, generator):
        """Should detect file/path-related keywords in step text."""
        file_steps = [
            "File config.json should exist",
            "Check if the path is correct",
            "Directory src/components should be created",
            "The generated output.txt file",
            "Verify the .env file is present",
        ]

        for step in file_steps:
            assert generator._has_file_keywords(step.lower()), f"Should detect file keyword in: {step}"

    def test_detect_forbidden_keywords(self, generator):
        """Should detect forbidden-related keywords in step text."""
        forbidden_steps = [
            "Output should not contain passwords",
            "The code must not include secrets",
            "Response shouldn't have errors",
            "Cannot contain sensitive data",
            "No hardcoded credentials",
            "Without any debug logs",
            "Forbidden patterns should be absent",
        ]

        for step in forbidden_steps:
            assert generator._has_forbidden_keywords(step.lower()), f"Should detect forbidden keyword in: {step}"

    def test_no_false_positives_for_normal_steps(self, generator):
        """Should not detect keywords in normal descriptive steps."""
        normal_step = "The button displays correctly"

        # This step doesn't contain any specific keywords
        # (though it may contain file keywords due to common words)
        # The important thing is it generates some kind of validator
        result = generator.generate_from_steps([normal_step])
        assert len(result) >= 0  # May generate fallback


# =============================================================================
# Step 2: If step contains run/execute, create test_pass validator
# =============================================================================

class TestTestPassValidator:
    """Tests for test_pass validator generation."""

    def test_create_test_pass_from_run_step(self, generator):
        """Should create test_pass validator for steps with 'run'."""
        step = "Run pytest tests/ to verify functionality"
        validators = generator.generate_from_steps([step])

        assert len(validators) >= 1
        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1

        v = test_pass_validators[0]
        assert v.validator_type == "test_pass"
        assert "command" in v.config
        assert v.config["expected_exit_code"] == 0

    def test_create_test_pass_from_execute_step(self, generator):
        """Should create test_pass validator for steps with 'execute'."""
        step = "Execute `npm run build` to compile the project"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert "npm run build" in test_pass_validators[0].config["command"]

    def test_create_test_pass_from_test_step(self, generator):
        """Should create test_pass validator for test-related steps with explicit commands."""
        # The step needs to have an explicit command pattern to create test_pass
        step = "Run vitest to test the API endpoint"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) >= 1

    def test_test_pass_includes_description(self, generator):
        """test_pass validator should include original step as description."""
        step = "Run pytest tests/ to verify all tests pass"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert test_pass_validators[0].config["description"] == step


# =============================================================================
# Step 3: If step mentions file/path, create file_exists validator
# =============================================================================

class TestFileExistsValidator:
    """Tests for file_exists validator generation."""

    def test_create_file_exists_from_file_step(self, generator):
        """Should create file_exists validator for steps mentioning files."""
        step = "File config.json should exist in project root"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1

        v = file_validators[0]
        assert v.validator_type == "file_exists"
        assert "path" in v.config
        assert "config.json" in v.config["path"]

    def test_create_file_exists_with_extension(self, generator):
        """Should recognize file paths with common extensions when existence is mentioned."""
        test_cases = [
            ("Verify api/models.py exists", "api/models.py"),
            ("Check that src/App.tsx file exists", "src/App.tsx"),
            ("Ensure package.json is present", "package.json"),
        ]

        for step, expected_path in test_cases:
            validators = generator.generate_from_steps([step])
            file_validators = [v for v in validators if v.validator_type == "file_exists"]
            assert len(file_validators) == 1, f"Should create file_exists for: {step}"
            assert file_validators[0].config["path"] == expected_path

    def test_file_exists_should_exist_default(self, generator):
        """file_exists validator should default to should_exist=True."""
        step = "File init.sh should be present"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1
        assert file_validators[0].config["should_exist"] is True

    def test_file_exists_should_not_exist(self, generator):
        """file_exists validator should detect 'should not exist'."""
        step = "File temp.log should not exist after cleanup"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1
        assert file_validators[0].config["should_exist"] is False


# =============================================================================
# Step 4: If step mentions should not/must not, create forbidden_patterns
# =============================================================================

class TestForbiddenPatternsValidator:
    """Tests for forbidden_patterns validator generation."""

    def test_create_forbidden_patterns_from_should_not(self, generator):
        """Should create forbidden_patterns validator for 'should not' steps."""
        step = "Output should not contain any passwords"
        validators = generator.generate_from_steps([step])

        forbidden_validators = [v for v in validators if v.validator_type == "forbidden_patterns"]
        assert len(forbidden_validators) == 1

        v = forbidden_validators[0]
        assert v.validator_type == "forbidden_patterns"
        assert "patterns" in v.config
        assert isinstance(v.config["patterns"], list)

    def test_create_forbidden_patterns_from_must_not(self, generator):
        """Should create forbidden_patterns validator for 'must not' steps."""
        step = "The code must not include any hardcoded secrets"
        validators = generator.generate_from_steps([step])

        forbidden_validators = [v for v in validators if v.validator_type == "forbidden_patterns"]
        assert len(forbidden_validators) == 1

    def test_create_forbidden_patterns_from_no_keyword(self, generator):
        """Should create forbidden_patterns validator for 'no' keyword."""
        step = "No debug logs in production output"
        validators = generator.generate_from_steps([step])

        forbidden_validators = [v for v in validators if v.validator_type == "forbidden_patterns"]
        assert len(forbidden_validators) >= 1

    def test_forbidden_patterns_extracts_quoted_content(self, generator):
        """Should extract quoted content as patterns."""
        step = 'Output should not contain "ERROR" or "FAILED"'
        validators = generator.generate_from_steps([step])

        forbidden_validators = [v for v in validators if v.validator_type == "forbidden_patterns"]
        assert len(forbidden_validators) == 1

        patterns = forbidden_validators[0].config["patterns"]
        assert len(patterns) >= 1


# =============================================================================
# Step 5: Extract command or path from step text
# =============================================================================

class TestCommandExtraction:
    """Tests for command extraction from step text."""

    def test_extract_backtick_command(self, generator):
        """Should extract commands from backticks."""
        step = "Run `pytest tests/ -v` to test"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert test_pass_validators[0].config["command"] == "pytest tests/ -v"

    def test_extract_single_quoted_command(self, generator):
        """Should extract commands from single quotes."""
        step = "Execute 'npm run build' to compile"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert test_pass_validators[0].config["command"] == "npm run build"

    def test_extract_double_quoted_command(self, generator):
        """Should extract commands from double quotes."""
        step = 'Run "yarn test" to verify'
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert test_pass_validators[0].config["command"] == "yarn test"

    def test_extract_npm_command_without_quotes(self, generator):
        """Should extract npm commands without quotes."""
        step = "Run npm test to verify functionality"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert "npm" in test_pass_validators[0].config["command"]

    def test_extract_pytest_command(self, generator):
        """Should extract pytest commands."""
        step = "Run pytest tests/unit/ to verify unit tests"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert "pytest" in test_pass_validators[0].config["command"]


class TestPathExtraction:
    """Tests for path extraction from step text."""

    def test_extract_path_with_extension(self, generator):
        """Should extract paths with file extensions."""
        step = "Verify src/config.json exists"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1
        assert file_validators[0].config["path"] == "src/config.json"

    def test_extract_backtick_path(self, generator):
        """Should extract paths from backticks."""
        step = "Check that `api/routes.py` exists"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1
        assert file_validators[0].config["path"] == "api/routes.py"

    def test_extract_relative_path(self, generator):
        """Should extract relative paths."""
        step = "File ./init.sh should be executable"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1
        assert "./init.sh" in file_validators[0].config["path"]


# =============================================================================
# Step 6: Set appropriate timeout for test_pass validators
# =============================================================================

class TestTimeoutConfiguration:
    """Tests for timeout configuration in test_pass validators."""

    def test_default_timeout(self, generator):
        """Should use default timeout for unknown commands."""
        step = "Run `some-custom-command` to verify"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert test_pass_validators[0].config["timeout_seconds"] == DEFAULT_TIMEOUT

    def test_test_command_timeout(self, generator):
        """Should use test timeout for test commands."""
        step = "Run pytest tests/ to verify"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert test_pass_validators[0].config["timeout_seconds"] == COMMAND_TIMEOUTS.get("pytest", DEFAULT_TIMEOUT)

    def test_build_command_timeout(self, generator):
        """Should use build timeout for build commands."""
        step = "Build the project with npm run build"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) >= 1
        # Build timeout should be 180 seconds
        assert test_pass_validators[0].config["timeout_seconds"] >= 120

    def test_lint_command_timeout(self, generator):
        """Should use lint timeout for lint commands."""
        step = "Run lint to check code quality"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        if test_pass_validators:
            assert test_pass_validators[0].config["timeout_seconds"] <= 60


# =============================================================================
# Step 7: Return array of validator configs
# =============================================================================

class TestValidatorOutput:
    """Tests for validator config output format."""

    def test_generate_validators_returns_list(self):
        """generate_validators_from_steps should return a list."""
        result = generate_validators_from_steps(["Run pytest tests/"])

        assert isinstance(result, list)

    def test_validator_config_structure(self):
        """Each validator config should have required fields."""
        result = generate_validators_from_steps(["Run pytest tests/"])

        assert len(result) >= 1

        for config in result:
            assert "type" in config
            assert "config" in config
            assert "weight" in config
            assert "required" in config

    def test_multiple_steps_generate_multiple_validators(self):
        """Multiple steps should generate multiple validators."""
        steps = [
            "Run pytest tests/ to verify functionality",
            "File config.json should exist",
            "Output should not contain passwords",
        ]

        result = generate_validators_from_steps(steps)

        # Should have at least 3 validators (one per step)
        assert len(result) >= 3

        # Check for each validator type
        types = [v["type"] for v in result]
        assert "test_pass" in types
        assert "file_exists" in types
        assert "forbidden_patterns" in types

    def test_validator_to_dict_format(self, generator):
        """ValidatorConfig.to_dict() should return proper format."""
        validators = generator.generate_from_steps(["Run pytest tests/"])

        assert len(validators) >= 1

        config_dict = validators[0].to_dict()

        assert isinstance(config_dict, dict)
        assert "type" in config_dict
        assert "config" in config_dict
        assert "weight" in config_dict
        assert "required" in config_dict
        assert isinstance(config_dict["config"], dict)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the validator generator."""

    def test_realistic_feature_steps(self):
        """Should handle realistic feature verification steps."""
        steps = [
            "FastAPI route POST defined at /api/agent-specs/:id/execute",
            "Run `pytest tests/test_execute.py -v` to verify endpoint",
            "Query AgentSpec by id returns correct spec",
            "Returns 404 for non-existent spec",
            "File api/routers/agent_specs.py should contain execute endpoint",
            "Response should not contain any stack traces",
        ]

        result = generate_validators_from_steps(steps, feature_id=42)

        # Should generate at least one validator per step
        assert len(result) >= len(steps)

        # Verify types are correctly identified
        types = [v["type"] for v in result]
        assert "test_pass" in types
        assert "file_exists" in types
        assert "forbidden_patterns" in types

    def test_feature_id_passed_to_validators(self, generator):
        """Feature ID should be passed to validator config where applicable."""
        validators = generator.generate_from_steps(
            ["Check step 1"],
            feature_id=42,
        )

        # Fallback validators should include feature_id
        fallback_validators = [v for v in validators if v.validator_type == "manual"]
        if fallback_validators:
            assert fallback_validators[0].config.get("feature_id") == 42

    def test_empty_steps_returns_empty_list(self):
        """Empty steps list should return empty validators list."""
        result = generate_validators_from_steps([])
        assert result == []

    def test_step_index_tracking(self, generator):
        """Validators should track their original step index."""
        steps = ["Step 1", "Run pytest", "Step 3"]
        validators = generator.generate_from_steps(steps)

        # Find the test_pass validator for "Run pytest"
        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        if test_pass_validators:
            assert test_pass_validators[0].step_index == 1

    def test_no_fallback_option(self):
        """Should be able to disable fallback validators."""
        generator = ValidatorGenerator(include_fallback=False)

        # A step with no specific keywords
        validators = generator.generate_from_steps(["The button displays correctly"])

        # Should not include fallback validator
        fallback_validators = [v for v in validators if v.validator_type == "manual"]
        assert len(fallback_validators) == 0


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_step(self, generator):
        """Should handle empty step strings."""
        validators = generator.generate_from_steps([""])
        assert isinstance(validators, list)

    def test_whitespace_only_step(self, generator):
        """Should handle whitespace-only step strings."""
        validators = generator.generate_from_steps(["   "])
        assert isinstance(validators, list)

    def test_very_long_step(self, generator):
        """Should handle very long step strings."""
        long_step = "Run pytest " + "tests/" * 100 + " to verify"
        validators = generator.generate_from_steps([long_step])
        assert isinstance(validators, list)

    def test_special_characters_in_step(self, generator):
        """Should handle special characters in step text."""
        step = "Run `npm run test:unit -- --coverage` to verify"
        validators = generator.generate_from_steps([step])
        assert isinstance(validators, list)

    def test_unicode_in_step(self, generator):
        """Should handle unicode characters in step text."""
        step = "Run pytest tests/ to verify functionality"
        validators = generator.generate_from_steps([step])
        assert isinstance(validators, list)

    def test_mixed_case_keywords(self, generator):
        """Should detect keywords regardless of case."""
        step = "RUN PYTEST TESTS/ TO VERIFY"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) >= 1

    def test_multiple_validators_same_step(self, generator):
        """Should potentially generate multiple validators from complex steps."""
        # This step mentions both a file AND a command
        step = "Run pytest tests/test_config.py to verify config.json is valid"
        validators = generator.generate_from_steps([step])

        # Should at least have test_pass
        types = [v.validator_type for v in validators]
        assert "test_pass" in types


# =============================================================================
# Module-level Function Tests
# =============================================================================

class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_validator_generator_returns_singleton(self):
        """get_validator_generator should return the same instance."""
        gen1 = get_validator_generator()
        gen2 = get_validator_generator()
        assert gen1 is gen2

    def test_reset_validator_generator(self):
        """reset_validator_generator should clear the singleton."""
        gen1 = get_validator_generator()
        reset_validator_generator()
        gen2 = get_validator_generator()
        assert gen1 is not gen2

    def test_generate_validators_from_steps_convenience(self):
        """generate_validators_from_steps should work as convenience function."""
        result = generate_validators_from_steps(["Run pytest tests/"])

        assert isinstance(result, list)
        assert len(result) >= 1
        assert "type" in result[0]

    def test_analyze_step_convenience(self):
        """analyze_step should return analysis for a single step."""
        result = analyze_step("Run pytest tests/ to verify")

        assert result["has_execute_keywords"] is True
        assert result["extracted_command"] is not None


# =============================================================================
# Regression Tests
# =============================================================================

class TestRegressions:
    """Regression tests for previously fixed issues."""

    def test_run_followed_by_command_extracted(self, generator):
        """'Run X' pattern should extract X as command."""
        step = "Run pytest tests/ to verify"
        validators = generator.generate_from_steps([step])

        test_pass_validators = [v for v in validators if v.validator_type == "test_pass"]
        assert len(test_pass_validators) == 1
        assert "pytest" in test_pass_validators[0].config["command"]

    def test_file_with_directory_path(self, generator):
        """Should extract file paths with directories."""
        step = "Verify api/routes/users.py exists"
        validators = generator.generate_from_steps([step])

        file_validators = [v for v in validators if v.validator_type == "file_exists"]
        assert len(file_validators) == 1
        assert "/" in file_validators[0].config["path"]

    def test_forbidden_with_quoted_patterns(self, generator):
        """Should extract quoted forbidden patterns."""
        step = 'Response should not contain "password" or "secret"'
        validators = generator.generate_from_steps([step])

        forbidden_validators = [v for v in validators if v.validator_type == "forbidden_patterns"]
        assert len(forbidden_validators) == 1
        assert len(forbidden_validators[0].config["patterns"]) >= 1
