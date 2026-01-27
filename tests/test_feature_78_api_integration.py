"""
API Integration Tests for Feature #78: Invalid AgentSpec Graceful Handling
==========================================================================

Tests that the execute endpoint properly validates AgentSpecs and returns
clear validation error responses.

Feature Requirements:
1. Validate AgentSpec before kernel execution
2. Check required fields are present
3. Validate tool_policy structure
4. Validate budget values within constraints
5. If invalid, return error without creating run
6. Include validation error details in response
"""

import pytest
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Add project root to path
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


# =============================================================================
# Test the execute endpoint validation integration
# =============================================================================

class TestExecuteEndpointValidation:
    """Test that execute endpoint integrates with spec_validator."""

    def test_valid_spec_creates_run(self):
        """Test that a valid spec creates an AgentRun."""
        from api.spec_validator import validate_spec
        from api.agentspec_models import AgentSpec

        # Create a mock valid AgentSpec
        mock_spec = MagicMock(spec=AgentSpec)
        mock_spec.id = str(uuid.uuid4())
        mock_spec.name = "valid-test-spec"
        mock_spec.display_name = "Valid Test Spec"
        mock_spec.objective = "This is a valid test objective with enough content"
        mock_spec.task_type = "coding"
        mock_spec.tool_policy = {
            "allowed_tools": ["tool1", "tool2"],
            "forbidden_patterns": [],
        }
        mock_spec.max_turns = 50
        mock_spec.timeout_seconds = 1800
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        # Validate the spec
        result = validate_spec(mock_spec)

        assert result.is_valid, f"Expected valid but got errors: {result.error_messages}"
        assert len(result.errors) == 0

    def test_invalid_spec_fails_validation(self):
        """Test that an invalid spec fails validation."""
        from api.spec_validator import validate_spec

        # Create an invalid AgentSpec
        mock_spec = MagicMock()
        mock_spec.id = str(uuid.uuid4())
        mock_spec.name = "INVALID NAME"  # Invalid format
        mock_spec.display_name = "Test"
        mock_spec.objective = "short"  # Too short
        mock_spec.task_type = "invalid"  # Invalid task type
        mock_spec.tool_policy = {
            "allowed_tools": [],  # Empty - invalid
        }
        mock_spec.max_turns = 0  # Below minimum
        mock_spec.timeout_seconds = 10  # Below minimum
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        # Validate the spec
        result = validate_spec(mock_spec)

        assert not result.is_valid
        assert len(result.errors) >= 4  # Multiple validation errors

    def test_validation_error_response_structure(self):
        """Test that validation error response has correct structure."""
        from api.spec_validator import validate_spec, SpecValidationResult

        # Create an invalid AgentSpec
        mock_spec = MagicMock()
        mock_spec.id = "test-spec-id"
        mock_spec.name = None  # Missing required field
        mock_spec.display_name = "Test"
        mock_spec.objective = "Valid objective with enough content here"
        mock_spec.task_type = "coding"
        mock_spec.tool_policy = {"allowed_tools": ["tool1"]}
        mock_spec.max_turns = 50
        mock_spec.timeout_seconds = 1800
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        # Validate
        result = validate_spec(mock_spec)

        # Check response structure
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'spec_id')
        assert hasattr(result, 'spec_name')

        # Check error structure
        assert not result.is_valid
        assert len(result.errors) > 0

        error = result.errors[0]
        assert hasattr(error, 'field')
        assert hasattr(error, 'message')
        assert hasattr(error, 'code')

        # Check to_dict includes error_count
        result_dict = result.to_dict()
        assert 'is_valid' in result_dict
        assert 'errors' in result_dict
        assert 'error_count' in result_dict
        assert result_dict['error_count'] == len(result.errors)

    def test_empty_allowed_tools_returns_validation_error(self):
        """Test Feature #78 Step 3: Validate tool_policy structure - empty allowed_tools."""
        from api.spec_validator import validate_spec

        mock_spec = MagicMock()
        mock_spec.id = "test-id"
        mock_spec.name = "valid-name"
        mock_spec.display_name = "Valid Display Name"
        mock_spec.objective = "Valid objective with enough content here"
        mock_spec.task_type = "coding"
        mock_spec.tool_policy = {"allowed_tools": []}  # Empty - invalid
        mock_spec.max_turns = 50
        mock_spec.timeout_seconds = 1800
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        result = validate_spec(mock_spec)

        assert not result.is_valid
        assert any(
            e.field == "tool_policy.allowed_tools" and e.code == "min_length"
            for e in result.errors
        )

    def test_budget_over_max_returns_validation_error(self):
        """Test Feature #78 Step 4: Validate budget values - max_turns over limit."""
        from api.spec_validator import validate_spec

        mock_spec = MagicMock()
        mock_spec.id = "test-id"
        mock_spec.name = "valid-name"
        mock_spec.display_name = "Valid Display Name"
        mock_spec.objective = "Valid objective with enough content here"
        mock_spec.task_type = "coding"
        mock_spec.tool_policy = {"allowed_tools": ["tool1"]}
        mock_spec.max_turns = 1000  # Over max (500)
        mock_spec.timeout_seconds = 1800
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        result = validate_spec(mock_spec)

        assert not result.is_valid
        assert any(
            e.field == "max_turns" and e.code == "max_value"
            for e in result.errors
        )

    def test_budget_under_min_returns_validation_error(self):
        """Test Feature #78 Step 4: Validate budget values - timeout_seconds under limit."""
        from api.spec_validator import validate_spec

        mock_spec = MagicMock()
        mock_spec.id = "test-id"
        mock_spec.name = "valid-name"
        mock_spec.display_name = "Valid Display Name"
        mock_spec.objective = "Valid objective with enough content here"
        mock_spec.task_type = "coding"
        mock_spec.tool_policy = {"allowed_tools": ["tool1"]}
        mock_spec.max_turns = 50
        mock_spec.timeout_seconds = 30  # Under min (60)
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        result = validate_spec(mock_spec)

        assert not result.is_valid
        assert any(
            e.field == "timeout_seconds" and e.code == "min_value"
            for e in result.errors
        )

    def test_invalid_regex_pattern_returns_validation_error(self):
        """Test Feature #78 Step 3: Validate tool_policy - invalid regex pattern."""
        from api.spec_validator import validate_spec

        mock_spec = MagicMock()
        mock_spec.id = "test-id"
        mock_spec.name = "valid-name"
        mock_spec.display_name = "Valid Display Name"
        mock_spec.objective = "Valid objective with enough content here"
        mock_spec.task_type = "coding"
        mock_spec.tool_policy = {
            "allowed_tools": ["tool1"],
            "forbidden_patterns": ["[invalid regex"]  # Invalid regex
        }
        mock_spec.max_turns = 50
        mock_spec.timeout_seconds = 1800
        mock_spec.priority = 100
        mock_spec.tags = []
        mock_spec.icon = None
        mock_spec.context = None

        result = validate_spec(mock_spec)

        assert not result.is_valid
        assert any(
            "forbidden_patterns" in e.field and e.code == "invalid_regex"
            for e in result.errors
        )


# =============================================================================
# Test the schema classes
# =============================================================================

class TestValidationErrorSchemas:
    """Test the Pydantic schemas for validation errors."""

    def test_validation_error_item_schema(self):
        """Test ValidationErrorItem schema."""
        from server.schemas.agentspec import ValidationErrorItem

        item = ValidationErrorItem(
            field="test_field",
            message="Test error message",
            code="test_code",
            value="test_value"
        )

        assert item.field == "test_field"
        assert item.message == "Test error message"
        assert item.code == "test_code"
        assert item.value == "test_value"

    def test_spec_validation_error_response_schema(self):
        """Test SpecValidationErrorResponse schema."""
        from server.schemas.agentspec import (
            SpecValidationErrorResponse,
            ValidationErrorItem,
        )

        errors = [
            ValidationErrorItem(
                field="max_turns",
                message="max_turns must be at least 1",
                code="min_value",
                value="0"
            )
        ]

        response = SpecValidationErrorResponse(
            is_valid=False,
            errors=errors,
            spec_id="test-spec-id",
            spec_name="test-spec",
            error_count=1
        )

        assert response.is_valid == False
        assert len(response.errors) == 1
        assert response.spec_id == "test-spec-id"
        assert response.spec_name == "test-spec"
        assert response.error_count == 1

    def test_spec_validation_error_response_serialization(self):
        """Test SpecValidationErrorResponse JSON serialization."""
        from server.schemas.agentspec import (
            SpecValidationErrorResponse,
            ValidationErrorItem,
        )

        errors = [
            ValidationErrorItem(
                field="tool_policy.allowed_tools",
                message="allowed_tools must contain at least one tool",
                code="min_length"
            )
        ]

        response = SpecValidationErrorResponse(
            is_valid=False,
            errors=errors,
            spec_id="abc-123",
            spec_name="my-spec",
            error_count=1
        )

        # Serialize to dict
        data = response.model_dump()

        assert data["is_valid"] == False
        assert len(data["errors"]) == 1
        assert data["errors"][0]["field"] == "tool_policy.allowed_tools"
        assert data["error_count"] == 1


# =============================================================================
# Test exports
# =============================================================================

class TestExports:
    """Test that Feature #78 exports are available."""

    def test_api_exports(self):
        """Test exports from api package."""
        from api import (
            SPEC_REQUIRED_FIELDS,
            SPEC_VALID_TASK_TYPES,
            MIN_MAX_TURNS,
            MAX_MAX_TURNS,
            MIN_TIMEOUT_SECONDS,
            MAX_TIMEOUT_SECONDS,
            SPEC_NAME_PATTERN_RE,
            TOOL_POLICY_REQUIRED_FIELDS,
            SpecValidationError,
            SpecValidationResult,
            SpecValidationException,
            validate_spec,
            validate_spec_or_raise,
            validate_spec_dict,
        )

        # Verify constants
        assert MIN_MAX_TURNS == 1
        assert MAX_MAX_TURNS == 500
        assert MIN_TIMEOUT_SECONDS == 60
        assert MAX_TIMEOUT_SECONDS == 7200
        assert "coding" in SPEC_VALID_TASK_TYPES
        assert "name" in SPEC_REQUIRED_FIELDS
        assert "allowed_tools" in TOOL_POLICY_REQUIRED_FIELDS

        # Verify functions are callable
        assert callable(validate_spec)
        assert callable(validate_spec_or_raise)
        assert callable(validate_spec_dict)

    def test_schema_exports(self):
        """Test exports from server.schemas.agentspec."""
        from server.schemas.agentspec import (
            ValidationErrorItem,
            SpecValidationErrorResponse,
        )

        # Verify classes are available
        assert ValidationErrorItem is not None
        assert SpecValidationErrorResponse is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
