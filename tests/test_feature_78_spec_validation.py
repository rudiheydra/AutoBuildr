"""
Tests for Feature #78: Invalid AgentSpec Graceful Handling
============================================================

Tests that invalid or malformed AgentSpecs are handled gracefully with clear
validation error responses.

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
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from api.spec_validator import (
    VALID_TASK_TYPES,
    REQUIRED_FIELDS,
    MIN_MAX_TURNS,
    MAX_MAX_TURNS,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    NAME_PATTERN,
    TOOL_POLICY_REQUIRED_FIELDS,
    ValidationError,
    SpecValidationResult,
    SpecValidationError,
    validate_spec,
    validate_spec_or_raise,
    validate_spec_dict,
    _validate_required_fields,
    _validate_name_format,
    _validate_task_type,
    _validate_tool_policy_structure,
    _validate_budget_constraints,
    _validate_objective,
    _validate_display_name,
    _validate_optional_fields,
)


# =============================================================================
# Test Fixtures
# =============================================================================

_UNSET = object()  # Sentinel to distinguish None from unset


class MockAgentSpec:
    """Mock AgentSpec for testing."""

    def __init__(
        self,
        id: str = "test-id-123",
        name: str = "test-spec",
        display_name: str = "Test Spec",
        icon: str = "gear",
        objective: str = "This is a test objective for the spec",
        task_type: str = "coding",
        context: dict = None,
        tool_policy: dict = _UNSET,
        max_turns: int = 50,
        timeout_seconds: int = 1800,
        priority: int = 500,
        tags: list = None,
    ):
        self.id = id
        self.name = name
        self.display_name = display_name
        self.icon = icon
        self.objective = objective
        self.task_type = task_type
        self.context = context
        # Use sentinel to distinguish between "not provided" and "explicitly set to None"
        if tool_policy is _UNSET:
            self.tool_policy = {
                "allowed_tools": ["feature_get_by_id"],
                "forbidden_patterns": [],
            }
        else:
            self.tool_policy = tool_policy
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.priority = priority
        self.tags = tags


def create_valid_spec(**kwargs) -> MockAgentSpec:
    """Create a valid spec with all required fields."""
    defaults = {
        "id": "abc123-456-789",
        "name": "valid-spec-name",
        "display_name": "Valid Spec Display Name",
        "objective": "This is a valid objective with at least 10 characters",
        "task_type": "coding",
        "tool_policy": {
            "allowed_tools": ["feature_get_by_id", "feature_mark_passing"],
            "forbidden_patterns": [],
        },
        "max_turns": 50,
        "timeout_seconds": 1800,
    }
    defaults.update(kwargs)
    return MockAgentSpec(**defaults)


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    """Test that constants are properly defined."""

    def test_valid_task_types(self):
        """Test VALID_TASK_TYPES contains expected values."""
        assert "coding" in VALID_TASK_TYPES
        assert "testing" in VALID_TASK_TYPES
        assert "refactoring" in VALID_TASK_TYPES
        assert "documentation" in VALID_TASK_TYPES
        assert "audit" in VALID_TASK_TYPES
        assert "custom" in VALID_TASK_TYPES
        assert len(VALID_TASK_TYPES) == 6

    def test_required_fields(self):
        """Test REQUIRED_FIELDS contains expected values."""
        assert "name" in REQUIRED_FIELDS
        assert "display_name" in REQUIRED_FIELDS
        assert "objective" in REQUIRED_FIELDS
        assert "task_type" in REQUIRED_FIELDS
        assert "tool_policy" in REQUIRED_FIELDS

    def test_budget_constraints(self):
        """Test budget constraint constants."""
        assert MIN_MAX_TURNS == 1
        assert MAX_MAX_TURNS == 500
        assert MIN_TIMEOUT_SECONDS == 60
        assert MAX_TIMEOUT_SECONDS == 7200

    def test_name_pattern(self):
        """Test NAME_PATTERN matches valid names."""
        assert NAME_PATTERN.match("a")
        assert NAME_PATTERN.match("abc")
        assert NAME_PATTERN.match("my-spec")
        assert NAME_PATTERN.match("spec-with-hyphens")
        assert NAME_PATTERN.match("a1")
        assert NAME_PATTERN.match("1a")

        # Invalid patterns
        assert not NAME_PATTERN.match("-invalid")
        assert not NAME_PATTERN.match("invalid-")
        assert not NAME_PATTERN.match("Invalid")  # uppercase
        assert not NAME_PATTERN.match("has spaces")
        assert not NAME_PATTERN.match("")


# =============================================================================
# Test ValidationError
# =============================================================================

class TestValidationError:
    """Test ValidationError dataclass."""

    def test_create_error(self):
        """Test creating a validation error."""
        error = ValidationError(
            field="test_field",
            message="Test message",
            code="test_code",
            value="test_value"
        )

        assert error.field == "test_field"
        assert error.message == "Test message"
        assert error.code == "test_code"
        assert error.value == "test_value"

    def test_to_dict(self):
        """Test ValidationError.to_dict()."""
        error = ValidationError(
            field="test_field",
            message="Test message",
            code="test_code",
            value="test_value"
        )

        result = error.to_dict()

        assert result["field"] == "test_field"
        assert result["message"] == "Test message"
        assert result["code"] == "test_code"
        assert result["value"] == "test_value"

    def test_to_dict_truncates_long_value(self):
        """Test to_dict truncates long values."""
        long_value = "x" * 200
        error = ValidationError(
            field="test_field",
            message="Test message",
            code="test_code",
            value=long_value
        )

        result = error.to_dict()

        assert len(result["value"]) == 100

    def test_to_dict_omits_none_value(self):
        """Test to_dict omits None value."""
        error = ValidationError(
            field="test_field",
            message="Test message",
            code="test_code",
        )

        result = error.to_dict()

        assert "value" not in result


# =============================================================================
# Test SpecValidationResult
# =============================================================================

class TestSpecValidationResult:
    """Test SpecValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = SpecValidationResult(
            is_valid=True,
            errors=[],
            spec_id="test-id",
            spec_name="test-name"
        )

        assert result.is_valid
        assert result.errors == []
        assert result.spec_id == "test-id"
        assert result.spec_name == "test-name"

    def test_invalid_result(self):
        """Test creating an invalid result with errors."""
        errors = [
            ValidationError(field="f1", message="m1", code="c1"),
            ValidationError(field="f2", message="m2", code="c2"),
        ]

        result = SpecValidationResult(
            is_valid=False,
            errors=errors,
            spec_id="test-id",
            spec_name="test-name"
        )

        assert not result.is_valid
        assert len(result.errors) == 2

    def test_to_dict(self):
        """Test SpecValidationResult.to_dict()."""
        errors = [
            ValidationError(field="f1", message="m1", code="c1"),
        ]

        result = SpecValidationResult(
            is_valid=False,
            errors=errors,
            spec_id="test-id",
            spec_name="test-name"
        )

        d = result.to_dict()

        assert d["is_valid"] == False
        assert len(d["errors"]) == 1
        assert d["spec_id"] == "test-id"
        assert d["spec_name"] == "test-name"
        assert d["error_count"] == 1

    def test_error_messages_property(self):
        """Test error_messages property."""
        errors = [
            ValidationError(field="f1", message="Message 1", code="c1"),
            ValidationError(field="f2", message="Message 2", code="c2"),
        ]

        result = SpecValidationResult(is_valid=False, errors=errors)

        assert result.error_messages == ["Message 1", "Message 2"]

    def test_first_error_property(self):
        """Test first_error property."""
        errors = [
            ValidationError(field="f1", message="First", code="c1"),
            ValidationError(field="f2", message="Second", code="c2"),
        ]

        result = SpecValidationResult(is_valid=False, errors=errors)

        assert result.first_error.message == "First"

    def test_first_error_none_when_no_errors(self):
        """Test first_error is None when no errors."""
        result = SpecValidationResult(is_valid=True, errors=[])

        assert result.first_error is None


# =============================================================================
# Test SpecValidationError Exception
# =============================================================================

class TestSpecValidationException:
    """Test SpecValidationError exception."""

    def test_raises_with_result(self):
        """Test exception contains result."""
        errors = [
            ValidationError(field="f1", message="Error 1", code="c1"),
        ]
        result = SpecValidationResult(is_valid=False, errors=errors)

        exc = SpecValidationError(result)

        assert exc.result == result
        assert "Error 1" in str(exc)

    def test_message_includes_multiple_errors(self):
        """Test exception message includes multiple errors."""
        errors = [
            ValidationError(field="f1", message="Error 1", code="c1"),
            ValidationError(field="f2", message="Error 2", code="c2"),
        ]
        result = SpecValidationResult(is_valid=False, errors=errors)

        exc = SpecValidationError(result)

        assert "Error 1" in str(exc)
        assert "Error 2" in str(exc)

    def test_message_truncates_many_errors(self):
        """Test exception message truncates when many errors."""
        errors = [
            ValidationError(field=f"f{i}", message=f"Error {i}", code=f"c{i}")
            for i in range(10)
        ]
        result = SpecValidationResult(is_valid=False, errors=errors)

        exc = SpecValidationError(result)

        # Should show first 5 errors and mention "and X more"
        assert "and 5 more errors" in str(exc)


# =============================================================================
# Test Step 2: Required Fields Validation
# =============================================================================

class TestRequiredFieldsValidation:
    """Test Step 2: Check required fields are present."""

    def test_valid_spec_passes(self):
        """Test valid spec with all required fields passes."""
        spec = create_valid_spec()
        errors = []

        _validate_required_fields(spec, errors)

        assert len(errors) == 0

    def test_missing_name(self):
        """Test missing name field."""
        spec = create_valid_spec(name=None)
        errors = []

        _validate_required_fields(spec, errors)

        assert any(e.field == "name" for e in errors)
        assert any(e.code == "required_field_missing" for e in errors)

    def test_empty_name(self):
        """Test empty name field."""
        spec = create_valid_spec(name="")
        errors = []

        _validate_required_fields(spec, errors)

        assert any(e.field == "name" for e in errors)
        assert any(e.code == "required_field_empty" for e in errors)

    def test_missing_display_name(self):
        """Test missing display_name field."""
        spec = create_valid_spec(display_name=None)
        errors = []

        _validate_required_fields(spec, errors)

        assert any(e.field == "display_name" for e in errors)

    def test_missing_objective(self):
        """Test missing objective field."""
        spec = create_valid_spec(objective=None)
        errors = []

        _validate_required_fields(spec, errors)

        assert any(e.field == "objective" for e in errors)

    def test_missing_task_type(self):
        """Test missing task_type field."""
        spec = create_valid_spec(task_type=None)
        errors = []

        _validate_required_fields(spec, errors)

        assert any(e.field == "task_type" for e in errors)

    def test_missing_tool_policy(self):
        """Test missing tool_policy field.

        Note: tool_policy=None triggers a "required_field_missing" error
        in _validate_required_fields because value is None.
        """
        spec = create_valid_spec(tool_policy=None)

        # Use validate_spec to verify the full flow
        result = validate_spec(spec)

        assert any(e.field == "tool_policy" and e.code == "required_field_missing" for e in result.errors)

    def test_whitespace_only_name(self):
        """Test whitespace-only name is treated as empty."""
        spec = create_valid_spec(name="   ")
        errors = []

        _validate_required_fields(spec, errors)

        assert any(e.field == "name" for e in errors)


# =============================================================================
# Test Name Format Validation
# =============================================================================

class TestNameFormatValidation:
    """Test name format validation."""

    def test_valid_name(self):
        """Test valid name passes."""
        spec = create_valid_spec(name="my-valid-name")
        errors = []

        _validate_name_format(spec, errors)

        assert len(errors) == 0

    def test_name_too_long(self):
        """Test name exceeding max length."""
        spec = create_valid_spec(name="a" * 101)
        errors = []

        _validate_name_format(spec, errors)

        assert any(e.code == "max_length_exceeded" for e in errors)

    def test_invalid_name_format(self):
        """Test invalid name format."""
        spec = create_valid_spec(name="Invalid-Name")  # uppercase
        errors = []

        _validate_name_format(spec, errors)

        assert any(e.code == "invalid_format" for e in errors)

    def test_name_with_spaces(self):
        """Test name with spaces is invalid."""
        spec = create_valid_spec(name="has spaces")
        errors = []

        _validate_name_format(spec, errors)

        assert any(e.code == "invalid_format" for e in errors)

    def test_name_starting_with_hyphen(self):
        """Test name starting with hyphen is invalid."""
        spec = create_valid_spec(name="-invalid")
        errors = []

        _validate_name_format(spec, errors)

        assert any(e.code == "invalid_format" for e in errors)


# =============================================================================
# Test Task Type Validation
# =============================================================================

class TestTaskTypeValidation:
    """Test task_type validation."""

    @pytest.mark.parametrize("task_type", ["coding", "testing", "refactoring", "documentation", "audit", "custom"])
    def test_valid_task_types(self, task_type):
        """Test all valid task types pass."""
        spec = create_valid_spec(task_type=task_type)
        errors = []

        _validate_task_type(spec, errors)

        assert len(errors) == 0

    def test_invalid_task_type(self):
        """Test invalid task type."""
        spec = create_valid_spec(task_type="invalid")
        errors = []

        _validate_task_type(spec, errors)

        assert any(e.code == "invalid_enum_value" for e in errors)

    def test_task_type_wrong_type(self):
        """Test task_type with wrong type."""
        spec = create_valid_spec(task_type=123)
        errors = []

        _validate_task_type(spec, errors)

        assert any(e.code == "invalid_type" for e in errors)


# =============================================================================
# Test Step 3: Tool Policy Structure Validation
# =============================================================================

class TestToolPolicyStructureValidation:
    """Test Step 3: Validate tool_policy structure."""

    def test_valid_tool_policy(self):
        """Test valid tool_policy passes."""
        spec = create_valid_spec(tool_policy={
            "allowed_tools": ["tool1", "tool2"],
            "forbidden_patterns": ["pattern1"],
        })
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert len(errors) == 0

    def test_tool_policy_not_dict(self):
        """Test tool_policy must be dict."""
        spec = create_valid_spec(tool_policy="not a dict")
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.field == "tool_policy" for e in errors)
        assert any(e.code == "invalid_type" for e in errors)

    def test_missing_allowed_tools(self):
        """Test missing allowed_tools field."""
        spec = create_valid_spec(tool_policy={"forbidden_patterns": []})
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.field == "tool_policy.allowed_tools" for e in errors)
        assert any(e.code == "required_field_missing" for e in errors)

    def test_allowed_tools_not_list(self):
        """Test allowed_tools must be list."""
        spec = create_valid_spec(tool_policy={"allowed_tools": "not a list"})
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.field == "tool_policy.allowed_tools" for e in errors)
        assert any(e.code == "invalid_type" for e in errors)

    def test_empty_allowed_tools(self):
        """Test empty allowed_tools list."""
        spec = create_valid_spec(tool_policy={"allowed_tools": []})
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.field == "tool_policy.allowed_tools" for e in errors)
        assert any(e.code == "min_length" for e in errors)

    def test_allowed_tools_with_non_string(self):
        """Test allowed_tools with non-string element."""
        spec = create_valid_spec(tool_policy={"allowed_tools": ["valid", 123, "also_valid"]})
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any("allowed_tools[1]" in e.field for e in errors)
        assert any(e.code == "invalid_type" for e in errors)

    def test_allowed_tools_with_empty_string(self):
        """Test allowed_tools with empty string."""
        spec = create_valid_spec(tool_policy={"allowed_tools": ["valid", ""]})
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any("allowed_tools[1]" in e.field for e in errors)
        assert any(e.code == "empty_value" for e in errors)

    def test_forbidden_patterns_not_list(self):
        """Test forbidden_patterns must be list if present."""
        spec = create_valid_spec(tool_policy={
            "allowed_tools": ["tool1"],
            "forbidden_patterns": "not a list"
        })
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.field == "tool_policy.forbidden_patterns" for e in errors)

    def test_invalid_regex_pattern(self):
        """Test invalid regex in forbidden_patterns."""
        spec = create_valid_spec(tool_policy={
            "allowed_tools": ["tool1"],
            "forbidden_patterns": ["[invalid regex"]
        })
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.code == "invalid_regex" for e in errors)

    def test_tool_hints_not_dict(self):
        """Test tool_hints must be dict if present."""
        spec = create_valid_spec(tool_policy={
            "allowed_tools": ["tool1"],
            "tool_hints": "not a dict"
        })
        errors = []

        _validate_tool_policy_structure(spec, errors)

        assert any(e.field == "tool_policy.tool_hints" for e in errors)


# =============================================================================
# Test Step 4: Budget Constraints Validation
# =============================================================================

class TestBudgetConstraintsValidation:
    """Test Step 4: Validate budget values within constraints."""

    def test_valid_budget(self):
        """Test valid budget passes."""
        spec = create_valid_spec(max_turns=50, timeout_seconds=1800)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert len(errors) == 0

    def test_max_turns_below_minimum(self):
        """Test max_turns below minimum."""
        spec = create_valid_spec(max_turns=0)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert any(e.field == "max_turns" for e in errors)
        assert any(e.code == "min_value" for e in errors)

    def test_max_turns_above_maximum(self):
        """Test max_turns above maximum."""
        spec = create_valid_spec(max_turns=501)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert any(e.field == "max_turns" for e in errors)
        assert any(e.code == "max_value" for e in errors)

    def test_max_turns_wrong_type(self):
        """Test max_turns with wrong type."""
        spec = create_valid_spec(max_turns="not an int")
        errors = []

        _validate_budget_constraints(spec, errors)

        assert any(e.field == "max_turns" for e in errors)
        assert any(e.code == "invalid_type" for e in errors)

    def test_timeout_seconds_below_minimum(self):
        """Test timeout_seconds below minimum."""
        spec = create_valid_spec(timeout_seconds=59)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert any(e.field == "timeout_seconds" for e in errors)
        assert any(e.code == "min_value" for e in errors)

    def test_timeout_seconds_above_maximum(self):
        """Test timeout_seconds above maximum."""
        spec = create_valid_spec(timeout_seconds=7201)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert any(e.field == "timeout_seconds" for e in errors)
        assert any(e.code == "max_value" for e in errors)

    def test_timeout_seconds_wrong_type(self):
        """Test timeout_seconds with wrong type."""
        spec = create_valid_spec(timeout_seconds="not an int")
        errors = []

        _validate_budget_constraints(spec, errors)

        assert any(e.field == "timeout_seconds" for e in errors)

    def test_boundary_min_values(self):
        """Test boundary minimum values."""
        spec = create_valid_spec(max_turns=1, timeout_seconds=60)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert len(errors) == 0

    def test_boundary_max_values(self):
        """Test boundary maximum values."""
        spec = create_valid_spec(max_turns=500, timeout_seconds=7200)
        errors = []

        _validate_budget_constraints(spec, errors)

        assert len(errors) == 0


# =============================================================================
# Test Objective Validation
# =============================================================================

class TestObjectiveValidation:
    """Test objective field validation."""

    def test_valid_objective(self):
        """Test valid objective passes."""
        spec = create_valid_spec(objective="A valid objective with enough characters")
        errors = []

        _validate_objective(spec, errors)

        assert len(errors) == 0

    def test_objective_too_short(self):
        """Test objective too short."""
        spec = create_valid_spec(objective="short")
        errors = []

        _validate_objective(spec, errors)

        assert any(e.field == "objective" for e in errors)
        assert any(e.code == "min_length" for e in errors)

    def test_objective_too_long(self):
        """Test objective too long."""
        spec = create_valid_spec(objective="x" * 5001)
        errors = []

        _validate_objective(spec, errors)

        assert any(e.field == "objective" for e in errors)
        assert any(e.code == "max_length" for e in errors)

    def test_objective_wrong_type(self):
        """Test objective with wrong type."""
        spec = create_valid_spec(objective=123)
        errors = []

        _validate_objective(spec, errors)

        assert any(e.field == "objective" for e in errors)
        assert any(e.code == "invalid_type" for e in errors)


# =============================================================================
# Test Display Name Validation
# =============================================================================

class TestDisplayNameValidation:
    """Test display_name field validation."""

    def test_valid_display_name(self):
        """Test valid display_name passes."""
        spec = create_valid_spec(display_name="Valid Display Name")
        errors = []

        _validate_display_name(spec, errors)

        assert len(errors) == 0

    def test_display_name_too_long(self):
        """Test display_name too long."""
        spec = create_valid_spec(display_name="x" * 256)
        errors = []

        _validate_display_name(spec, errors)

        assert any(e.field == "display_name" for e in errors)
        assert any(e.code == "max_length" for e in errors)

    def test_display_name_wrong_type(self):
        """Test display_name with wrong type."""
        spec = create_valid_spec(display_name=123)
        errors = []

        _validate_display_name(spec, errors)

        assert any(e.field == "display_name" for e in errors)


# =============================================================================
# Test Optional Fields Validation
# =============================================================================

class TestOptionalFieldsValidation:
    """Test optional fields validation."""

    def test_valid_optional_fields(self):
        """Test valid optional fields pass."""
        spec = create_valid_spec(
            priority=100,
            icon="gear",
            context={"key": "value"},
            tags=["tag1", "tag2"]
        )
        errors = []

        _validate_optional_fields(spec, errors)

        assert len(errors) == 0

    def test_priority_out_of_range(self):
        """Test priority out of range."""
        spec = create_valid_spec(priority=10000)
        errors = []

        _validate_optional_fields(spec, errors)

        assert any(e.field == "priority" for e in errors)

    def test_icon_too_long(self):
        """Test icon too long."""
        spec = create_valid_spec(icon="x" * 51)
        errors = []

        _validate_optional_fields(spec, errors)

        assert any(e.field == "icon" for e in errors)

    def test_context_not_dict(self):
        """Test context must be dict if present."""
        spec = create_valid_spec(context="not a dict")
        errors = []

        _validate_optional_fields(spec, errors)

        assert any(e.field == "context" for e in errors)

    def test_tags_not_list(self):
        """Test tags must be list if present."""
        spec = create_valid_spec(tags="not a list")
        errors = []

        _validate_optional_fields(spec, errors)

        assert any(e.field == "tags" for e in errors)

    def test_too_many_tags(self):
        """Test too many tags."""
        spec = create_valid_spec(tags=["tag"] * 21)
        errors = []

        _validate_optional_fields(spec, errors)

        assert any(e.field == "tags" for e in errors)

    def test_tags_with_non_string(self):
        """Test tags with non-string element."""
        spec = create_valid_spec(tags=["valid", 123])
        errors = []

        _validate_optional_fields(spec, errors)

        assert any("tags[1]" in e.field for e in errors)


# =============================================================================
# Test validate_spec() Main Function
# =============================================================================

class TestValidateSpec:
    """Test validate_spec() main function."""

    def test_valid_spec(self):
        """Test Step 1: Validate AgentSpec - valid spec passes."""
        spec = create_valid_spec()

        result = validate_spec(spec)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_spec_collects_all_errors(self):
        """Test invalid spec collects all validation errors."""
        spec = MockAgentSpec(
            name=None,
            display_name=None,
            objective="short",
            task_type="invalid",
            tool_policy=None,
            max_turns=0,
            timeout_seconds=10,
        )

        result = validate_spec(spec)

        assert not result.is_valid
        assert len(result.errors) > 1

    def test_result_includes_spec_id(self):
        """Test result includes spec_id."""
        spec = create_valid_spec(id="my-spec-id")

        result = validate_spec(spec)

        assert result.spec_id == "my-spec-id"

    def test_result_includes_spec_name(self):
        """Test result includes spec_name."""
        spec = create_valid_spec(name="my-spec-name")

        result = validate_spec(spec)

        assert result.spec_name == "my-spec-name"


# =============================================================================
# Test validate_spec_or_raise()
# =============================================================================

class TestValidateSpecOrRaise:
    """Test validate_spec_or_raise() function."""

    def test_valid_spec_returns_result(self):
        """Test valid spec returns result."""
        spec = create_valid_spec()

        result = validate_spec_or_raise(spec)

        assert result.is_valid

    def test_invalid_spec_raises(self):
        """Test Step 5: Invalid spec raises SpecValidationError."""
        spec = create_valid_spec(name=None, display_name=None)

        with pytest.raises(SpecValidationError) as exc_info:
            validate_spec_or_raise(spec)

        assert not exc_info.value.result.is_valid
        assert len(exc_info.value.result.errors) > 0


# =============================================================================
# Test validate_spec_dict()
# =============================================================================

class TestValidateSpecDict:
    """Test validate_spec_dict() function."""

    def test_valid_dict(self):
        """Test valid dict passes validation."""
        spec_dict = {
            "id": "test-id",
            "name": "valid-name",
            "display_name": "Valid Name",
            "objective": "Valid objective with enough characters",
            "task_type": "coding",
            "tool_policy": {
                "allowed_tools": ["tool1"],
            },
            "max_turns": 50,
            "timeout_seconds": 1800,
        }

        result = validate_spec_dict(spec_dict)

        assert result.is_valid

    def test_invalid_dict(self):
        """Test invalid dict fails validation."""
        spec_dict = {
            "name": None,
            "tool_policy": {},
        }

        result = validate_spec_dict(spec_dict)

        assert not result.is_valid


# =============================================================================
# Test Step 6: Validation Error Details
# =============================================================================

class TestValidationErrorDetails:
    """Test Step 6: Include validation error details in response."""

    def test_error_includes_field(self):
        """Test error includes field name."""
        spec = create_valid_spec(name=None)

        result = validate_spec(spec)

        error = result.first_error
        assert error.field == "name"

    def test_error_includes_message(self):
        """Test error includes human-readable message."""
        spec = create_valid_spec(max_turns=0)

        result = validate_spec(spec)

        error = next(e for e in result.errors if e.field == "max_turns")
        assert "must be at least" in error.message

    def test_error_includes_code(self):
        """Test error includes machine-readable code."""
        spec = create_valid_spec(max_turns=0)

        result = validate_spec(spec)

        error = next(e for e in result.errors if e.field == "max_turns")
        assert error.code == "min_value"

    def test_error_includes_value(self):
        """Test error includes invalid value."""
        spec = create_valid_spec(max_turns=0)

        result = validate_spec(spec)

        error = next(e for e in result.errors if e.field == "max_turns")
        assert error.value == 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for complete validation flow."""

    def test_complete_valid_spec(self):
        """Test complete valid spec passes all validations."""
        spec = MockAgentSpec(
            id="abc123-456-789",
            name="complete-valid-spec",
            display_name="Complete Valid Spec",
            icon="gear",
            objective="This is a complete valid objective with all required fields",
            task_type="coding",
            context={"feature_id": 1},
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["feature_get_by_id", "feature_mark_passing"],
                "forbidden_patterns": ["rm -rf"],
                "tool_hints": {"feature_mark_passing": "Only call after testing"},
            },
            max_turns=100,
            timeout_seconds=3600,
            priority=100,
            tags=["test", "integration"],
        )

        result = validate_spec(spec)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_multiple_validation_errors(self):
        """Test spec with multiple validation errors."""
        spec = MockAgentSpec(
            id=None,
            name="INVALID NAME",
            display_name="",
            icon=None,
            objective="short",
            task_type="invalid_type",
            context="not a dict",
            tool_policy={
                "allowed_tools": [],  # empty
            },
            max_turns=-1,
            timeout_seconds=0,
            priority=99999,
            tags="not a list",
        )

        result = validate_spec(spec)

        assert not result.is_valid
        # Should have many errors
        assert len(result.errors) >= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
