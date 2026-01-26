"""
Test Feature #34: forbidden_patterns Acceptance Validator
=========================================================

Tests for the ForbiddenPatternsValidator that ensures agent output
does not contain forbidden regex patterns.

Feature Steps:
1. Create ForbiddenPatternsValidator class
2. Extract patterns array from validator config
3. Compile patterns as regex
4. Query all tool_result events for the run
5. Check each payload against all patterns
6. If any match found, return passed = false
7. Include matched pattern and context in result
8. Return passed = true if no matches
"""
import re
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from api.validators import (
    ForbiddenPatternsValidator,
    ValidatorResult,
    VALIDATOR_REGISTRY,
    get_validator,
    evaluate_validator,
    _dict_to_searchable_text,
    _get_match_context,
)


# =============================================================================
# Mock Classes
# =============================================================================

@dataclass
class MockAgentEvent:
    """Mock AgentEvent for testing."""
    id: int
    event_type: str
    sequence: int
    payload: Any = None
    tool_name: str | None = None


@dataclass
class MockAgentRun:
    """Mock AgentRun for testing."""
    id: str
    events: list[MockAgentEvent] = field(default_factory=list)


# =============================================================================
# Test Step 1: Create ForbiddenPatternsValidator class
# =============================================================================

class TestStep1ForbiddenPatternsValidatorClass:
    """Test that ForbiddenPatternsValidator class exists and is properly structured."""

    def test_class_exists(self):
        """ForbiddenPatternsValidator class should exist."""
        assert ForbiddenPatternsValidator is not None

    def test_inherits_from_validator(self):
        """ForbiddenPatternsValidator should inherit from Validator."""
        from api.validators import Validator
        assert issubclass(ForbiddenPatternsValidator, Validator)

    def test_has_evaluate_method(self):
        """ForbiddenPatternsValidator should have an evaluate method."""
        validator = ForbiddenPatternsValidator()
        assert hasattr(validator, 'evaluate')
        assert callable(validator.evaluate)

    def test_validator_type_attribute(self):
        """ForbiddenPatternsValidator should have correct validator_type."""
        validator = ForbiddenPatternsValidator()
        assert validator.validator_type == "forbidden_patterns"

    def test_registered_in_validator_registry(self):
        """ForbiddenPatternsValidator should be registered in VALIDATOR_REGISTRY."""
        assert "forbidden_patterns" in VALIDATOR_REGISTRY
        assert VALIDATOR_REGISTRY["forbidden_patterns"] == ForbiddenPatternsValidator

    def test_get_validator_returns_instance(self):
        """get_validator('forbidden_patterns') should return a ForbiddenPatternsValidator."""
        validator = get_validator("forbidden_patterns")
        assert validator is not None
        assert isinstance(validator, ForbiddenPatternsValidator)


# =============================================================================
# Test Step 2: Extract patterns array from validator config
# =============================================================================

class TestStep2ExtractPatternsFromConfig:
    """Test that patterns are correctly extracted from validator config."""

    def test_missing_patterns_returns_failure(self):
        """Config without patterns should return passed=False."""
        validator = ForbiddenPatternsValidator()
        config = {}
        result = validator.evaluate(config, {})

        assert result.passed is False
        assert "missing required 'patterns' field" in result.message

    def test_none_patterns_returns_failure(self):
        """Config with patterns=None should return passed=False."""
        validator = ForbiddenPatternsValidator()
        config = {"patterns": None}
        result = validator.evaluate(config, {})

        assert result.passed is False
        assert "missing required 'patterns' field" in result.message

    def test_patterns_not_list_returns_failure(self):
        """Config with patterns not a list should return passed=False."""
        validator = ForbiddenPatternsValidator()
        config = {"patterns": "not-a-list"}
        result = validator.evaluate(config, {})

        assert result.passed is False
        assert "must be a list" in result.message

    def test_empty_patterns_list_returns_success(self):
        """Config with empty patterns list should return passed=True."""
        validator = ForbiddenPatternsValidator()
        config = {"patterns": []}
        result = validator.evaluate(config, {})

        assert result.passed is True
        assert "No forbidden patterns specified" in result.message

    def test_patterns_extracted_correctly(self):
        """Patterns should be extracted and used for checking."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123")
        config = {"patterns": ["foo", "bar"]}
        result = validator.evaluate(config, {}, run=run)

        # Should pass since no events have these patterns
        assert result.passed is True
        assert result.details.get("patterns_checked") == ["foo", "bar"]


# =============================================================================
# Test Step 3: Compile patterns as regex
# =============================================================================

class TestStep3CompilePatternsAsRegex:
    """Test that patterns are correctly compiled as regex."""

    def test_invalid_regex_returns_failure(self):
        """Invalid regex pattern should return passed=False with compilation error."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123")
        config = {"patterns": ["[invalid"]}  # Missing closing bracket
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        assert "Failed to compile" in result.message
        assert "compilation_errors" in result.details

    def test_multiple_invalid_patterns_all_reported(self):
        """All invalid patterns should be reported in compilation_errors."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123")
        config = {"patterns": ["[invalid", "(unclosed", "valid-pattern"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        errors = result.details.get("compilation_errors", [])
        # Should have 2 errors (one for each invalid pattern)
        assert len(errors) == 2

    def test_valid_regex_compiles_successfully(self):
        """Valid regex patterns should compile without errors."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123")
        config = {"patterns": [r"rm\s+-rf", r"DROP\s+TABLE", r"password\s*="]}
        result = validator.evaluate(config, {}, run=run)

        # Should pass since no events have these patterns
        assert result.passed is True

    def test_case_sensitive_default(self):
        """By default, patterns should be case-sensitive."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE users")
            ]
        )
        config = {"patterns": ["drop table"]}  # lowercase
        result = validator.evaluate(config, {}, run=run)

        # Should pass since case doesn't match
        assert result.passed is True

    def test_case_insensitive_option(self):
        """With case_sensitive=False, patterns should match case-insensitively."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE users")
            ]
        )
        config = {"patterns": ["drop table"], "case_sensitive": False}
        result = validator.evaluate(config, {}, run=run)

        # Should fail since case-insensitive match found
        assert result.passed is False


# =============================================================================
# Test Step 4: Query all tool_result events for the run
# =============================================================================

class TestStep4QueryToolResultEvents:
    """Test that tool_result events are correctly queried from the run."""

    def test_requires_run_instance(self):
        """Validator should require an AgentRun instance."""
        validator = ForbiddenPatternsValidator()
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=None)

        assert result.passed is False
        assert "requires an AgentRun instance" in result.message

    def test_only_tool_result_events_checked(self):
        """Only tool_result events should be checked, not other event types."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="started", sequence=1, payload="forbidden"),
                MockAgentEvent(id=2, event_type="tool_call", sequence=2, payload="forbidden"),
                MockAgentEvent(id=3, event_type="completed", sequence=3, payload="forbidden"),
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        # Should pass since no tool_result events (even though other events have the pattern)
        assert result.passed is True
        assert result.details.get("events_checked") == 0

    def test_multiple_tool_result_events_checked(self):
        """All tool_result events should be checked."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe content"),
                MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="more safe content"),
                MockAgentEvent(id=3, event_type="tool_result", sequence=3, payload="also safe"),
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert result.details.get("events_checked") == 3

    def test_empty_events_list_passes(self):
        """Run with no events should pass validation."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123", events=[])
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert result.details.get("events_checked") == 0


# =============================================================================
# Test Step 5: Check each payload against all patterns
# =============================================================================

class TestStep5CheckPayloadsAgainstPatterns:
    """Test that each payload is checked against all patterns."""

    def test_string_payload_checked(self):
        """String payloads should be checked for patterns."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="rm -rf /")
            ]
        )
        config = {"patterns": ["rm -rf"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False

    def test_dict_payload_checked(self):
        """Dictionary payloads should be searched recursively."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(
                    id=1,
                    event_type="tool_result",
                    sequence=1,
                    payload={"output": "rm -rf /home/user", "status": "success"}
                )
            ]
        )
        config = {"patterns": ["rm -rf"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False

    def test_nested_dict_payload_checked(self):
        """Nested dictionary payloads should be searched recursively."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(
                    id=1,
                    event_type="tool_result",
                    sequence=1,
                    payload={"result": {"nested": {"deep": "rm -rf /"}}}
                )
            ]
        )
        config = {"patterns": ["rm -rf"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False

    def test_list_in_dict_payload_checked(self):
        """Lists within dictionary payloads should be checked."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(
                    id=1,
                    event_type="tool_result",
                    sequence=1,
                    payload={"commands": ["ls", "cd /", "rm -rf /"]}
                )
            ]
        )
        config = {"patterns": ["rm -rf"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False

    def test_none_payload_skipped(self):
        """Events with None payload should be skipped."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload=None)
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True

    def test_multiple_patterns_all_checked(self):
        """All patterns should be checked against each payload."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE users")
            ]
        )
        config = {"patterns": ["rm -rf", "DROP TABLE", "DELETE FROM"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        # The second pattern should match
        matches = result.details.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["pattern"] == "DROP TABLE"


# =============================================================================
# Test Step 6: If any match found, return passed = false
# =============================================================================

class TestStep6ReturnPassedFalseOnMatch:
    """Test that validation fails when any pattern matches."""

    def test_single_match_fails(self):
        """A single match should cause validation to fail."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="password=secret123")
            ]
        )
        config = {"patterns": [r"password\s*="]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        assert result.score == 0.0

    def test_multiple_matches_fails(self):
        """Multiple matches should cause validation to fail."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="rm -rf /"),
                MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="DROP TABLE users"),
            ]
        )
        config = {"patterns": ["rm -rf", "DROP TABLE"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        matches = result.details.get("matches", [])
        assert len(matches) == 2

    def test_match_count_in_message(self):
        """The number of matches should be included in the message."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="error error error")
            ]
        )
        config = {"patterns": ["error"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        # Should find at least one match (the first occurrence)
        assert "1" in result.message or "match" in result.message.lower()


# =============================================================================
# Test Step 7: Include matched pattern and context in result
# =============================================================================

class TestStep7IncludeMatchedPatternAndContext:
    """Test that match details are included in the result."""

    def test_match_includes_event_id(self):
        """Match should include the event ID."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=42, event_type="tool_result", sequence=1, payload="forbidden content")
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        matches = result.details.get("matches", [])
        assert len(matches) == 1
        assert matches[0]["event_id"] == 42

    def test_match_includes_event_sequence(self):
        """Match should include the event sequence number."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=5, payload="forbidden content")
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        matches = result.details.get("matches", [])
        assert matches[0]["event_sequence"] == 5

    def test_match_includes_tool_name(self):
        """Match should include the tool name."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(
                    id=1,
                    event_type="tool_result",
                    sequence=1,
                    payload="forbidden content",
                    tool_name="execute_command"
                )
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        matches = result.details.get("matches", [])
        assert matches[0]["tool_name"] == "execute_command"

    def test_match_includes_pattern(self):
        """Match should include the pattern that matched."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE users")
            ]
        )
        config = {"patterns": ["DROP TABLE"]}
        result = validator.evaluate(config, {}, run=run)

        matches = result.details.get("matches", [])
        assert matches[0]["pattern"] == "DROP TABLE"

    def test_match_includes_matched_text(self):
        """Match should include the actual text that matched."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE users")
            ]
        )
        config = {"patterns": ["DROP TABLE"]}
        result = validator.evaluate(config, {}, run=run)

        matches = result.details.get("matches", [])
        assert matches[0]["matched_text"] == "DROP TABLE"

    def test_match_includes_context(self):
        """Match should include context around the match."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(
                    id=1,
                    event_type="tool_result",
                    sequence=1,
                    payload="Before text DROP TABLE users After text"
                )
            ]
        )
        config = {"patterns": ["DROP TABLE"]}
        result = validator.evaluate(config, {}, run=run)

        matches = result.details.get("matches", [])
        context = matches[0]["context"]
        # Context should include text around the match
        assert "Before text" in context
        assert "DROP TABLE" in context
        assert "users After text" in context


# =============================================================================
# Test Step 8: Return passed = true if no matches
# =============================================================================

class TestStep8ReturnPassedTrueNoMatches:
    """Test that validation passes when no patterns match."""

    def test_no_matches_passes(self):
        """No matches should result in passed=True."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe content here")
            ]
        )
        config = {"patterns": ["forbidden", "dangerous", "malicious"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert result.score == 1.0

    def test_passing_message_includes_event_count(self):
        """Passing message should include the number of events checked."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe"),
                MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="also safe"),
                MockAgentEvent(id=3, event_type="tool_result", sequence=3, payload="still safe"),
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert "3" in result.message

    def test_details_include_patterns_checked(self):
        """Details should include the list of patterns that were checked."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123", events=[])
        config = {"patterns": ["pattern1", "pattern2", "pattern3"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert result.details.get("patterns_checked") == ["pattern1", "pattern2", "pattern3"]

    def test_details_include_events_checked_count(self):
        """Details should include the number of events that were checked."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe"),
                MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="safe"),
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert result.details.get("events_checked") == 2


# =============================================================================
# Test Integration with evaluate_validator
# =============================================================================

class TestEvaluateValidatorIntegration:
    """Test integration with the evaluate_validator function."""

    def test_evaluate_validator_with_forbidden_patterns(self):
        """evaluate_validator should work with forbidden_patterns type."""
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe content")
            ]
        )
        validator_def = {
            "type": "forbidden_patterns",
            "config": {"patterns": ["dangerous"]},
        }
        result = evaluate_validator(validator_def, {}, run=run)

        assert result.passed is True
        assert result.validator_type == "forbidden_patterns"

    def test_evaluate_validator_detects_match(self):
        """evaluate_validator should detect matches."""
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="dangerous operation")
            ]
        )
        validator_def = {
            "type": "forbidden_patterns",
            "config": {"patterns": ["dangerous"]},
        }
        result = evaluate_validator(validator_def, {}, run=run)

        assert result.passed is False


# =============================================================================
# Test Description in Messages
# =============================================================================

class TestDescriptionInMessages:
    """Test that description is included in result messages."""

    def test_description_in_failure_message(self):
        """Description should be included in failure messages."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="dangerous")
            ]
        )
        config = {
            "patterns": ["dangerous"],
            "description": "Check for dangerous operations"
        }
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        assert "Check for dangerous operations" in result.message

    def test_description_in_success_message(self):
        """Description should be included in success messages."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe content")
            ]
        )
        config = {
            "patterns": ["dangerous"],
            "description": "Check for dangerous operations"
        }
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is True
        assert "Check for dangerous operations" in result.message


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Test helper functions used by the validator."""

    def test_dict_to_searchable_text_simple(self):
        """_dict_to_searchable_text should handle simple dicts."""
        result = _dict_to_searchable_text({"key": "value"})
        assert "value" in result

    def test_dict_to_searchable_text_nested(self):
        """_dict_to_searchable_text should handle nested dicts."""
        result = _dict_to_searchable_text({"outer": {"inner": "nested_value"}})
        assert "nested_value" in result

    def test_dict_to_searchable_text_with_list(self):
        """_dict_to_searchable_text should handle lists."""
        result = _dict_to_searchable_text({"items": ["item1", "item2", "item3"]})
        assert "item1" in result
        assert "item2" in result
        assert "item3" in result

    def test_get_match_context_short_text(self):
        """_get_match_context should handle short text."""
        text = "short text"
        match = re.search("text", text)
        context = _get_match_context(text, match, context_chars=50)
        assert context == "short text"  # No ellipsis needed

    def test_get_match_context_long_text(self):
        """_get_match_context should truncate long text."""
        text = "A" * 100 + "MATCH" + "B" * 100
        match = re.search("MATCH", text)
        context = _get_match_context(text, match, context_chars=10)
        assert "..." in context  # Should have ellipsis
        assert "MATCH" in context


# =============================================================================
# Test Validator Type
# =============================================================================

class TestValidatorType:
    """Test that validator_type is correctly set in results."""

    def test_validator_type_on_success(self):
        """validator_type should be 'forbidden_patterns' on success."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(id="test-run-123", events=[])
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.validator_type == "forbidden_patterns"

    def test_validator_type_on_failure(self):
        """validator_type should be 'forbidden_patterns' on failure."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="forbidden content")
            ]
        )
        config = {"patterns": ["forbidden"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.validator_type == "forbidden_patterns"

    def test_validator_type_on_config_error(self):
        """validator_type should be 'forbidden_patterns' on config error."""
        validator = ForbiddenPatternsValidator()
        config = {}
        result = validator.evaluate(config, {})

        assert result.validator_type == "forbidden_patterns"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_regex_special_characters_in_pattern(self):
        """Patterns with special regex characters should work."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="file.txt")
            ]
        )
        # Pattern with special characters - need to escape the dot
        config = {"patterns": [r"file\.txt"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False

    def test_unescaped_special_characters_as_regex(self):
        """Unescaped special characters should be treated as regex."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="file.txt")
            ]
        )
        # Unescaped dot matches any character
        config = {"patterns": ["file.txt"]}
        result = validator.evaluate(config, {}, run=run)

        # Should match because . matches any char
        assert result.passed is False

    def test_empty_string_in_patterns(self):
        """Empty string pattern should match everything."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="any content")
            ]
        )
        config = {"patterns": [""]}
        result = validator.evaluate(config, {}, run=run)

        # Empty pattern matches anywhere
        assert result.passed is False

    def test_unicode_in_payload(self):
        """Unicode content should be handled correctly."""
        validator = ForbiddenPatternsValidator()
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="Hello ")
            ]
        )
        config = {"patterns": [""]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False
        matches = result.details.get("matches", [])
        assert "" in matches[0]["matched_text"]

    def test_large_payload(self):
        """Large payloads should be handled correctly."""
        validator = ForbiddenPatternsValidator()
        large_content = "safe content " * 10000 + "FORBIDDEN" + " more content " * 10000
        run = MockAgentRun(
            id="test-run-123",
            events=[
                MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload=large_content)
            ]
        )
        config = {"patterns": ["FORBIDDEN"]}
        result = validator.evaluate(config, {}, run=run)

        assert result.passed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
