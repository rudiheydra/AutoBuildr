"""
Feature #33: file_exists Acceptance Validator Tests
====================================================

This test suite verifies the file_exists validator implementation.

Feature Description:
Implement file_exists validator that verifies a file path exists
with variable interpolation support.

Verification Steps:
1. Create FileExistsValidator class implementing Validator interface
2. Extract path from validator config
3. Interpolate variables in path (e.g., {project_dir})
4. Extract should_exist (default true)
5. Check if path exists using Path.exists()
6. Return passed = exists == should_exist
7. Include file path in result message
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# =============================================================================
# Step 1: FileExistsValidator Class Implementing Validator Interface
# =============================================================================

class TestStep1ValidatorInterface:
    """Test that FileExistsValidator implements the Validator interface."""

    def test_file_exists_validator_class_exists(self):
        """FileExistsValidator class should be importable."""
        from api.validators import FileExistsValidator
        assert FileExistsValidator is not None

    def test_file_exists_validator_inherits_from_validator(self):
        """FileExistsValidator should inherit from Validator base class."""
        from api.validators import FileExistsValidator, Validator
        assert issubclass(FileExistsValidator, Validator)

    def test_file_exists_validator_has_evaluate_method(self):
        """FileExistsValidator should have an evaluate method."""
        from api.validators import FileExistsValidator
        validator = FileExistsValidator()
        assert hasattr(validator, 'evaluate')
        assert callable(validator.evaluate)

    def test_file_exists_validator_has_validator_type(self):
        """FileExistsValidator should have validator_type = 'file_exists'."""
        from api.validators import FileExistsValidator
        validator = FileExistsValidator()
        assert validator.validator_type == "file_exists"

    def test_validator_result_class_exists(self):
        """ValidatorResult class should be importable."""
        from api.validators import ValidatorResult
        assert ValidatorResult is not None

    def test_validator_result_has_required_fields(self):
        """ValidatorResult should have passed, message, score fields."""
        from api.validators import ValidatorResult
        result = ValidatorResult(passed=True, message="test")
        assert hasattr(result, 'passed')
        assert hasattr(result, 'message')
        assert hasattr(result, 'score')
        assert hasattr(result, 'details')
        assert hasattr(result, 'validator_type')


# =============================================================================
# Step 2: Extract Path from Validator Config
# =============================================================================

class TestStep2ExtractPathFromConfig:
    """Test path extraction from validator config."""

    def test_extracts_path_from_config(self):
        """Should extract 'path' key from config dictionary."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()
            config = {"path": temp_path}
            result = validator.evaluate(config, {})

            # Path should be extracted and used
            assert temp_path in result.message
        finally:
            os.unlink(temp_path)

    def test_returns_error_when_path_missing(self):
        """Should return failed result when 'path' is missing from config."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {}  # No path
        result = validator.evaluate(config, {})

        assert result.passed is False
        assert "missing" in result.message.lower()
        assert "path" in result.message.lower()

    def test_extracts_path_with_various_formats(self):
        """Should handle various path formats."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()

        # Test absolute path
        config = {"path": "/absolute/path/to/file.txt"}
        result = validator.evaluate(config, {})
        assert "/absolute/path/to/file.txt" in result.details.get("interpolated_path", "")

        # Test relative path
        config = {"path": "relative/path/to/file.txt"}
        result = validator.evaluate(config, {})
        assert "relative/path/to/file.txt" in result.details.get("interpolated_path", "")


# =============================================================================
# Step 3: Interpolate Variables in Path
# =============================================================================

class TestStep3InterpolateVariables:
    """Test variable interpolation in paths."""

    def test_interpolates_project_dir_variable(self):
        """Should replace {project_dir} with context value."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "{project_dir}/init.sh"}
        context = {"project_dir": "/home/user/myproject"}

        result = validator.evaluate(config, context)

        assert "/home/user/myproject/init.sh" in result.details.get("interpolated_path", "")

    def test_interpolates_multiple_variables(self):
        """Should replace multiple variables in path."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "{base_dir}/{subdir}/file.txt"}
        context = {"base_dir": "/app", "subdir": "src"}

        result = validator.evaluate(config, context)

        assert "/app/src/file.txt" in result.details.get("interpolated_path", "")

    def test_handles_missing_variable_gracefully(self):
        """Should handle missing context variables without crashing."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "{missing_var}/file.txt"}
        context = {}

        # Should not raise exception
        result = validator.evaluate(config, context)

        # The uninterpolated variable should remain in path
        assert "{missing_var}" in result.details.get("interpolated_path", "")

    def test_interpolates_feature_id(self):
        """Should interpolate {feature_id} variable."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/tests/feature_{feature_id}_test.py"}
        context = {"feature_id": 42}

        result = validator.evaluate(config, context)

        assert "/tests/feature_42_test.py" in result.details.get("interpolated_path", "")

    def test_interpolates_run_id(self):
        """Should interpolate {run_id} variable."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/artifacts/{run_id}/output.log"}
        context = {"run_id": "abc-123-xyz"}

        result = validator.evaluate(config, context)

        assert "/artifacts/abc-123-xyz/output.log" in result.details.get("interpolated_path", "")

    def test_path_without_variables_unchanged(self):
        """Paths without variables should remain unchanged."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/simple/path/file.txt"}
        context = {"project_dir": "/unused"}

        result = validator.evaluate(config, context)

        assert result.details.get("interpolated_path") == "/simple/path/file.txt"


# =============================================================================
# Step 4: Extract should_exist (Default True)
# =============================================================================

class TestStep4ExtractShouldExist:
    """Test extraction of should_exist config option."""

    def test_should_exist_defaults_to_true(self):
        """should_exist should default to True when not specified."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/nonexistent/file.txt"}  # No should_exist

        result = validator.evaluate(config, {})

        # Path doesn't exist, should_exist=True (default), so should fail
        assert result.details.get("should_exist") is True
        assert result.passed is False

    def test_should_exist_true_explicitly_set(self):
        """should_exist=True should work when explicitly set."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()
            config = {"path": temp_path, "should_exist": True}

            result = validator.evaluate(config, {})

            assert result.details.get("should_exist") is True
            assert result.passed is True
        finally:
            os.unlink(temp_path)

    def test_should_exist_false(self):
        """should_exist=False should validate non-existence."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/definitely/nonexistent/file.txt", "should_exist": False}

        result = validator.evaluate(config, {})

        assert result.details.get("should_exist") is False
        assert result.passed is True  # File doesn't exist and shouldn't

    def test_should_exist_string_true(self):
        """should_exist as string 'true' should be converted to boolean."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/nonexistent", "should_exist": "true"}

        result = validator.evaluate(config, {})

        assert result.details.get("should_exist") is True

    def test_should_exist_string_false(self):
        """should_exist as string 'false' should be converted to boolean."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/nonexistent", "should_exist": "false"}

        result = validator.evaluate(config, {})

        assert result.details.get("should_exist") is False


# =============================================================================
# Step 5: Check if Path Exists Using Path.exists()
# =============================================================================

class TestStep5CheckPathExists:
    """Test path existence checking."""

    def test_detects_existing_file(self):
        """Should detect that an existing file exists."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()
            config = {"path": temp_path}

            result = validator.evaluate(config, {})

            assert result.details.get("file_exists") is True
            assert result.details.get("is_file") is True
        finally:
            os.unlink(temp_path)

    def test_detects_existing_directory(self):
        """Should detect that an existing directory exists."""
        from api.validators import FileExistsValidator

        with tempfile.TemporaryDirectory() as temp_dir:
            validator = FileExistsValidator()
            config = {"path": temp_dir}

            result = validator.evaluate(config, {})

            assert result.details.get("file_exists") is True
            assert result.details.get("is_directory") is True

    def test_detects_nonexistent_path(self):
        """Should detect that a non-existent path doesn't exist."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/this/path/definitely/does/not/exist/file.txt"}

        result = validator.evaluate(config, {})

        assert result.details.get("file_exists") is False

    def test_handles_relative_path_with_project_dir(self):
        """Should resolve relative paths against project_dir."""
        from api.validators import FileExistsValidator

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a file in the temp directory
            file_path = Path(temp_dir) / "test_file.txt"
            file_path.write_text("test content")

            validator = FileExistsValidator()
            config = {"path": "test_file.txt"}  # Relative path
            context = {"project_dir": temp_dir}

            result = validator.evaluate(config, context)

            assert result.details.get("file_exists") is True


# =============================================================================
# Step 6: Return passed = exists == should_exist
# =============================================================================

class TestStep6ReturnPassedEqualsExistsEqualsShouldExist:
    """Test that passed = (exists == should_exist)."""

    def test_exists_and_should_exist_returns_pass(self):
        """When file exists and should_exist=True, should pass."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()
            config = {"path": temp_path, "should_exist": True}

            result = validator.evaluate(config, {})

            assert result.passed is True
            assert result.score == 1.0
        finally:
            os.unlink(temp_path)

    def test_exists_and_should_not_exist_returns_fail(self):
        """When file exists and should_exist=False, should fail."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()
            config = {"path": temp_path, "should_exist": False}

            result = validator.evaluate(config, {})

            assert result.passed is False
            assert result.score == 0.0
        finally:
            os.unlink(temp_path)

    def test_not_exists_and_should_exist_returns_fail(self):
        """When file doesn't exist and should_exist=True, should fail."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/nonexistent/file.txt", "should_exist": True}

        result = validator.evaluate(config, {})

        assert result.passed is False
        assert result.score == 0.0

    def test_not_exists_and_should_not_exist_returns_pass(self):
        """When file doesn't exist and should_exist=False, should pass."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/nonexistent/file.txt", "should_exist": False}

        result = validator.evaluate(config, {})

        assert result.passed is True
        assert result.score == 1.0


# =============================================================================
# Step 7: Include File Path in Result Message
# =============================================================================

class TestStep7IncludePathInMessage:
    """Test that result message includes the file path."""

    def test_message_includes_path_when_exists(self):
        """Message should include the file path when file exists."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()
            config = {"path": temp_path}

            result = validator.evaluate(config, {})

            assert temp_path in result.message
        finally:
            os.unlink(temp_path)

    def test_message_includes_path_when_not_exists(self):
        """Message should include the file path when file doesn't exist."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/path/to/missing/file.txt"}

        result = validator.evaluate(config, {})

        assert "/path/to/missing/file.txt" in result.message

    def test_message_indicates_existence_status(self):
        """Message should indicate whether file exists or not."""
        from api.validators import FileExistsValidator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator = FileExistsValidator()

            # When file exists
            config = {"path": temp_path}
            result = validator.evaluate(config, {})
            assert "exists" in result.message.lower()

            # When file doesn't exist
            config = {"path": "/nonexistent/file.txt"}
            result = validator.evaluate(config, {})
            assert "not exist" in result.message.lower() or "does not exist" in result.message.lower()
        finally:
            os.unlink(temp_path)

    def test_message_includes_description_if_provided(self):
        """Message should include description from config if provided."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {
            "path": "/some/path.txt",
            "description": "Configuration file must exist"
        }

        result = validator.evaluate(config, {})

        assert "Configuration file must exist" in result.message

    def test_message_includes_interpolated_path(self):
        """Message should include the interpolated path, not template."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "{project_dir}/init.sh"}
        context = {"project_dir": "/my/project"}

        result = validator.evaluate(config, context)

        # Should have the interpolated path, not the template
        assert "/my/project/init.sh" in result.message
        assert "{project_dir}" not in result.message


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the FileExistsValidator."""

    def test_evaluate_validator_function_works(self):
        """evaluate_validator() convenience function should work."""
        from api.validators import evaluate_validator

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validator_def = {
                "type": "file_exists",
                "config": {"path": temp_path},
                "weight": 1.0,
                "required": True,
            }

            result = evaluate_validator(validator_def, {})

            assert result.passed is True
        finally:
            os.unlink(temp_path)

    def test_validator_in_registry(self):
        """FileExistsValidator should be in the validator registry."""
        from api.validators import VALIDATOR_REGISTRY, FileExistsValidator

        assert "file_exists" in VALIDATOR_REGISTRY
        assert VALIDATOR_REGISTRY["file_exists"] == FileExistsValidator

    def test_get_validator_function(self):
        """get_validator() should return FileExistsValidator instance."""
        from api.validators import get_validator, FileExistsValidator

        validator = get_validator("file_exists")

        assert isinstance(validator, FileExistsValidator)

    def test_evaluate_acceptance_spec_with_file_exists(self):
        """evaluate_acceptance_spec() should work with file_exists validator."""
        from api.validators import evaluate_acceptance_spec

        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            validators = [
                {
                    "type": "file_exists",
                    "config": {"path": temp_path},
                    "weight": 1.0,
                    "required": True,
                }
            ]

            passed, results = evaluate_acceptance_spec(validators, {}, "all_pass")

            assert passed is True
            assert len(results) == 1
            assert results[0].passed is True
        finally:
            os.unlink(temp_path)

    def test_full_acceptance_spec_scenario(self):
        """Test a realistic acceptance spec scenario."""
        from api.validators import evaluate_acceptance_spec

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create init.sh
            init_sh = Path(temp_dir) / "init.sh"
            init_sh.write_text("#!/bin/bash\necho 'init'")

            validators = [
                {
                    "type": "file_exists",
                    "config": {
                        "path": "{project_dir}/init.sh",
                        "should_exist": True,
                        "description": "Environment initialization script"
                    },
                    "weight": 1.0,
                    "required": True,
                },
                {
                    "type": "file_exists",
                    "config": {
                        "path": "{project_dir}/node_modules",
                        "should_exist": False,
                        "description": "node_modules should not be committed"
                    },
                    "weight": 0.5,
                    "required": False,
                },
            ]

            context = {"project_dir": temp_dir}

            passed, results = evaluate_acceptance_spec(validators, context, "all_pass")

            assert passed is True
            assert len(results) == 2
            assert results[0].passed is True  # init.sh exists
            assert results[1].passed is True  # node_modules doesn't exist


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_path(self):
        """Should handle empty path string."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": ""}

        result = validator.evaluate(config, {})

        # Empty path should still work (though likely fail existence check)
        assert isinstance(result.passed, bool)

    def test_path_with_special_characters(self):
        """Should handle paths with special characters."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/path/with spaces/and-dashes/file.txt"}

        result = validator.evaluate(config, {})

        assert "/path/with spaces/and-dashes/file.txt" in result.details.get("interpolated_path", "")

    def test_symlink_handling(self):
        """Should properly check symlinks."""
        from api.validators import FileExistsValidator

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a file and a symlink to it
            file_path = Path(temp_dir) / "real_file.txt"
            file_path.write_text("content")

            symlink_path = Path(temp_dir) / "symlink.txt"
            symlink_path.symlink_to(file_path)

            validator = FileExistsValidator()

            # Symlink should exist
            config = {"path": str(symlink_path)}
            result = validator.evaluate(config, {})

            assert result.passed is True
            assert result.details.get("file_exists") is True

    def test_unicode_path(self):
        """Should handle unicode characters in path."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/path/with/\u00e9\u00e8\u00ea/file.txt"}

        result = validator.evaluate(config, {})

        # Should not crash
        assert isinstance(result.passed, bool)

    def test_result_to_dict(self):
        """ValidatorResult.to_dict() should work correctly."""
        from api.validators import FileExistsValidator

        validator = FileExistsValidator()
        config = {"path": "/some/path"}

        result = validator.evaluate(config, {})
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "passed" in result_dict
        assert "message" in result_dict
        assert "score" in result_dict
        assert "details" in result_dict
        assert "validator_type" in result_dict
        assert result_dict["validator_type"] == "file_exists"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
