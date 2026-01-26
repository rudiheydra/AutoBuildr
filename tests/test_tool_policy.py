"""
Tests for ToolPolicy Forbidden Patterns Enforcement (Feature #41)

These tests verify:
1. Pattern extraction from tool_policy
2. Regex compilation at spec load time
3. Argument serialization
4. Pattern matching against arguments
5. Blocked tool call event recording
6. Error message generation
7. Integration with ToolPolicyEnforcer class
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from api.tool_policy import (
    CompiledPattern,
    PatternCompilationError,
    ToolCallBlocked,
    ToolPolicyEnforcer,
    ToolPolicyError,
    check_arguments_against_patterns,
    compile_forbidden_patterns,
    create_enforcer_for_run,
    extract_forbidden_patterns,
    record_blocked_tool_call_event,
    serialize_tool_arguments,
)


# =============================================================================
# Step 1: Extract forbidden_patterns from spec.tool_policy
# =============================================================================

class TestExtractForbiddenPatterns:
    """Tests for extract_forbidden_patterns function."""

    def test_extract_from_valid_policy(self):
        """Extract patterns from a valid tool_policy dict."""
        policy = {
            "policy_version": "v1",
            "allowed_tools": ["feature_mark_passing"],
            "forbidden_patterns": ["rm -rf", "DROP TABLE", "DELETE FROM"],
        }
        result = extract_forbidden_patterns(policy)
        assert result == ["rm -rf", "DROP TABLE", "DELETE FROM"]

    def test_extract_from_none_policy(self):
        """Handle None tool_policy gracefully."""
        result = extract_forbidden_patterns(None)
        assert result == []

    def test_extract_from_empty_policy(self):
        """Handle empty dict gracefully."""
        result = extract_forbidden_patterns({})
        assert result == []

    def test_extract_missing_key(self):
        """Handle missing forbidden_patterns key."""
        policy = {"allowed_tools": ["some_tool"]}
        result = extract_forbidden_patterns(policy)
        assert result == []

    def test_extract_none_patterns(self):
        """Handle None forbidden_patterns value."""
        policy = {"forbidden_patterns": None}
        result = extract_forbidden_patterns(policy)
        assert result == []

    def test_extract_empty_list(self):
        """Handle empty forbidden_patterns list."""
        policy = {"forbidden_patterns": []}
        result = extract_forbidden_patterns(policy)
        assert result == []

    def test_extract_non_list_patterns_returns_empty(self):
        """Non-list forbidden_patterns should return empty with warning."""
        policy = {"forbidden_patterns": "not a list"}
        result = extract_forbidden_patterns(policy)
        assert result == []


# =============================================================================
# Step 2: Compile patterns as regex at spec load time
# =============================================================================

class TestCompileForbiddenPatterns:
    """Tests for compile_forbidden_patterns function."""

    def test_compile_valid_patterns(self):
        """Compile a list of valid regex patterns."""
        patterns = ["rm -rf", "DROP TABLE", r"\bpassword\b"]
        compiled = compile_forbidden_patterns(patterns)
        assert len(compiled) == 3
        assert all(isinstance(p, CompiledPattern) for p in compiled)
        assert compiled[0].original == "rm -rf"

    def test_compile_empty_list(self):
        """Handle empty pattern list."""
        result = compile_forbidden_patterns([])
        assert result == []

    def test_compile_none(self):
        """Handle None input."""
        result = compile_forbidden_patterns(None)
        assert result == []

    def test_compile_with_regex_features(self):
        """Compile patterns with regex special characters."""
        patterns = [r".*secret.*", r"api[_-]?key", r"\d{16}"]
        compiled = compile_forbidden_patterns(patterns)
        assert len(compiled) == 3
        # Verify they actually work as regex
        assert compiled[0].regex.search("my_secret_key") is not None
        assert compiled[1].regex.search("api_key") is not None
        assert compiled[2].regex.search("1234567890123456") is not None

    def test_compile_invalid_pattern_non_strict(self):
        """Invalid patterns are skipped in non-strict mode."""
        patterns = ["valid", "[invalid(regex", "also_valid"]
        compiled = compile_forbidden_patterns(patterns, strict=False)
        assert len(compiled) == 2  # Invalid one skipped
        assert compiled[0].original == "valid"
        assert compiled[1].original == "also_valid"

    def test_compile_invalid_pattern_strict(self):
        """Invalid patterns raise error in strict mode."""
        patterns = ["valid", "[invalid(regex"]
        with pytest.raises(PatternCompilationError) as exc_info:
            compile_forbidden_patterns(patterns, strict=True)
        assert "[invalid(regex" in str(exc_info.value)

    def test_compile_skips_empty_patterns(self):
        """Empty or whitespace-only patterns are skipped."""
        patterns = ["valid", "", "   ", "also_valid"]
        compiled = compile_forbidden_patterns(patterns)
        assert len(compiled) == 2

    def test_compile_skips_non_string_patterns(self):
        """Non-string patterns are skipped with warning."""
        patterns = ["valid", 123, None, "also_valid"]
        compiled = compile_forbidden_patterns(patterns)
        assert len(compiled) == 2

    def test_compile_case_insensitive(self):
        """Patterns should match case-insensitively."""
        compiled = compile_forbidden_patterns(["DROP TABLE"])
        assert compiled[0].regex.search("drop table users") is not None
        assert compiled[0].regex.search("DROP TABLE users") is not None


# =============================================================================
# Step 3: Serialize arguments to string before checking
# =============================================================================

class TestSerializeToolArguments:
    """Tests for serialize_tool_arguments function."""

    def test_serialize_simple_dict(self):
        """Serialize a simple dict of arguments."""
        args = {"command": "ls -la", "timeout": 30}
        result = serialize_tool_arguments(args)
        # JSON output with sorted keys
        assert '"command": "ls -la"' in result
        assert '"timeout": 30' in result

    def test_serialize_none_returns_empty(self):
        """None arguments return empty string."""
        result = serialize_tool_arguments(None)
        assert result == ""

    def test_serialize_empty_dict(self):
        """Empty dict serializes to '{}'."""
        result = serialize_tool_arguments({})
        assert result == "{}"

    def test_serialize_nested_dict(self):
        """Handle nested structures."""
        args = {
            "config": {
                "user": "admin",
                "password": "secret123"
            },
            "options": ["a", "b"]
        }
        result = serialize_tool_arguments(args)
        assert "admin" in result
        assert "secret123" in result
        assert '["a", "b"]' in result

    def test_serialize_various_types(self):
        """Handle various value types."""
        args = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
        }
        result = serialize_tool_arguments(args)
        # Verify JSON formatting
        parsed = json.loads(result)
        assert parsed["string"] == "hello"
        assert parsed["number"] == 42
        assert parsed["null"] is None

    def test_serialize_non_dict_returns_str(self):
        """Non-dict input returns str() representation."""
        result = serialize_tool_arguments("just a string")  # type: ignore
        assert result == "just a string"


# =============================================================================
# Step 4: Check arguments against all forbidden patterns
# =============================================================================

class TestCheckArgumentsAgainstPatterns:
    """Tests for check_arguments_against_patterns function."""

    def test_match_found(self):
        """Pattern match is detected."""
        patterns = compile_forbidden_patterns(["rm -rf", "DROP TABLE"])
        serialized = '{"command": "rm -rf /home/user"}'
        result = check_arguments_against_patterns(serialized, patterns)
        assert result is not None
        assert result.original == "rm -rf"

    def test_no_match(self):
        """No match returns None."""
        patterns = compile_forbidden_patterns(["rm -rf", "DROP TABLE"])
        serialized = '{"command": "ls -la"}'
        result = check_arguments_against_patterns(serialized, patterns)
        assert result is None

    def test_empty_args(self):
        """Empty args string returns None."""
        patterns = compile_forbidden_patterns(["dangerous"])
        result = check_arguments_against_patterns("", patterns)
        assert result is None

    def test_empty_patterns(self):
        """Empty patterns list returns None."""
        result = check_arguments_against_patterns('{"cmd": "anything"}', [])
        assert result is None

    def test_first_match_wins(self):
        """Returns the first matching pattern."""
        patterns = compile_forbidden_patterns(["aaa", "bbb", "ccc"])
        serialized = '{"value": "bbb aaa"}'
        result = check_arguments_against_patterns(serialized, patterns)
        # "aaa" comes first in pattern list
        assert result.original == "aaa"

    def test_regex_pattern_match(self):
        """Complex regex patterns work correctly."""
        patterns = compile_forbidden_patterns([r"\bpassword\s*="])
        serialized = '{"query": "SELECT * WHERE password = \'abc\'"}'
        result = check_arguments_against_patterns(serialized, patterns)
        assert result is not None


# =============================================================================
# Step 5: Block tool call if pattern matches
# =============================================================================

class TestToolCallBlocked:
    """Tests for ToolCallBlocked exception."""

    def test_exception_properties(self):
        """Exception has correct properties."""
        exc = ToolCallBlocked(
            tool_name="dangerous_tool",
            pattern_matched="rm -rf",
            arguments={"cmd": "rm -rf /"}
        )
        assert exc.tool_name == "dangerous_tool"
        assert exc.pattern_matched == "rm -rf"
        assert exc.arguments == {"cmd": "rm -rf /"}

    def test_exception_message(self):
        """Exception has descriptive message."""
        exc = ToolCallBlocked(
            tool_name="bash",
            pattern_matched="DROP TABLE",
            arguments={"sql": "DROP TABLE users"}
        )
        assert "bash" in str(exc)
        assert "DROP TABLE" in str(exc)

    def test_custom_message(self):
        """Custom message overrides default."""
        exc = ToolCallBlocked(
            tool_name="tool",
            pattern_matched="pattern",
            arguments={},
            message="Custom error message"
        )
        assert str(exc) == "Custom error message"


# =============================================================================
# Step 6: Record tool_call event with blocked=true
# =============================================================================

class TestRecordBlockedToolCallEvent:
    """Tests for record_blocked_tool_call_event function."""

    def test_record_event(self):
        """Event is recorded with correct fields."""
        mock_db = MagicMock()

        event = record_blocked_tool_call_event(
            db=mock_db,
            run_id="run-123",
            sequence=5,
            tool_name="dangerous_bash",
            arguments={"command": "rm -rf /"},
            pattern_matched="rm -rf",
        )

        # Verify event was added to session
        mock_db.add.assert_called_once()

        # Verify event properties
        assert event.run_id == "run-123"
        assert event.sequence == 5
        assert event.event_type == "tool_call"
        assert event.tool_name == "dangerous_bash"

        # Verify payload
        assert event.payload["blocked"] is True
        assert event.payload["pattern_matched"] == "rm -rf"
        assert event.payload["tool"] == "dangerous_bash"
        assert event.payload["args"]["command"] == "rm -rf /"

    def test_event_has_timestamp(self):
        """Event has a timestamp."""
        mock_db = MagicMock()

        event = record_blocked_tool_call_event(
            db=mock_db,
            run_id="run-123",
            sequence=1,
            tool_name="tool",
            arguments={},
            pattern_matched="pattern",
        )

        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)


# =============================================================================
# Step 7: Return error to agent explaining blocked operation
# =============================================================================

class TestGetBlockedErrorMessage:
    """Tests for error message generation."""

    def test_error_message_content(self):
        """Error message explains what happened."""
        enforcer = ToolPolicyEnforcer(spec_id="test", forbidden_patterns=[])
        message = enforcer.get_blocked_error_message("bash", "rm -rf")

        assert "bash" in message
        assert "rm -rf" in message
        assert "blocked" in message.lower()
        assert "security" in message.lower() or "policy" in message.lower()


# =============================================================================
# Step 8: Continue execution (do not abort run)
# =============================================================================

class TestContinueExecution:
    """Tests verifying that blocked calls don't abort the run."""

    def test_validate_raises_exception_not_abort(self):
        """Blocked calls raise exception, don't abort execution."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["safe_tool"],
                "forbidden_patterns": ["dangerous"],
            }
        )

        # First call is blocked
        with pytest.raises(ToolCallBlocked):
            enforcer.validate_tool_call("safe_tool", {"cmd": "dangerous"})

        # But we can still make other calls (execution continues)
        enforcer.validate_tool_call("safe_tool", {"cmd": "safe_operation"})

    def test_check_method_returns_tuple(self):
        """check_tool_call returns tuple without raising."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["tool"],
                "forbidden_patterns": ["blocked"],
            }
        )

        # Blocked call returns (False, pattern, error)
        allowed, pattern, error = enforcer.check_tool_call("tool", {"x": "blocked"})
        assert allowed is False
        assert pattern is not None
        assert error is not None

        # Allowed call returns (True, None, None)
        allowed, pattern, error = enforcer.check_tool_call("tool", {"x": "allowed"})
        assert allowed is True
        assert pattern is None
        assert error is None


# =============================================================================
# ToolPolicyEnforcer Integration Tests
# =============================================================================

class TestToolPolicyEnforcer:
    """Integration tests for ToolPolicyEnforcer."""

    def test_from_spec(self):
        """Create enforcer from AgentSpec-like object."""
        mock_spec = MagicMock()
        mock_spec.id = "spec-123"
        mock_spec.tool_policy = {
            "allowed_tools": ["tool1", "tool2"],
            "forbidden_patterns": ["pattern1", "pattern2"],
        }

        enforcer = ToolPolicyEnforcer.from_spec(mock_spec)

        assert enforcer.spec_id == "spec-123"
        assert enforcer.allowed_tools == ["tool1", "tool2"]
        assert len(enforcer.forbidden_patterns) == 2

    def test_from_tool_policy_dict(self):
        """Create enforcer from tool_policy dict."""
        policy = {
            "allowed_tools": ["read", "write"],
            "forbidden_patterns": ["rm -rf", "DROP TABLE"],
        }

        enforcer = ToolPolicyEnforcer.from_tool_policy("test-spec", policy)

        assert enforcer.spec_id == "test-spec"
        assert enforcer.allowed_tools == ["read", "write"]
        assert len(enforcer.forbidden_patterns) == 2

    def test_validate_tool_call_allowed(self):
        """Allowed tool call passes validation."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["safe_tool"],
                "forbidden_patterns": ["dangerous"],
            }
        )

        # Should not raise
        enforcer.validate_tool_call("safe_tool", {"cmd": "safe_command"})

    def test_validate_tool_call_blocked_by_pattern(self):
        """Tool call blocked by forbidden pattern."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["bash"],
                "forbidden_patterns": ["rm -rf"],
            }
        )

        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("bash", {"command": "rm -rf /home"})

        assert exc_info.value.pattern_matched == "rm -rf"

    def test_validate_tool_call_blocked_by_not_allowed(self):
        """Tool call blocked when not in allowed_tools."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["tool1", "tool2"],
                "forbidden_patterns": [],
            }
        )

        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("unauthorized_tool", {})

        assert "not_in_allowed_tools" in exc_info.value.pattern_matched

    def test_validate_with_none_allowed_tools(self):
        """When allowed_tools is None, all tools are allowed."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "forbidden_patterns": ["dangerous"],
            }
        )

        # Any tool should be allowed
        enforcer.validate_tool_call("any_tool_name", {"safe": "args"})

    def test_properties(self):
        """Test property accessors."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "forbidden_patterns": ["p1", "p2", "p3"],
            }
        )

        assert enforcer.has_forbidden_patterns is True
        assert enforcer.pattern_count == 3

    def test_to_dict(self):
        """Test serialization to dict."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-123",
            tool_policy={
                "allowed_tools": ["tool1"],
                "forbidden_patterns": ["pattern1", "pattern2"],
            }
        )

        d = enforcer.to_dict()
        assert d["spec_id"] == "test-123"
        assert d["pattern_count"] == 2
        assert d["patterns"] == ["pattern1", "pattern2"]
        assert d["allowed_tools"] == ["tool1"]


# =============================================================================
# Real-world Scenario Tests
# =============================================================================

class TestRealWorldScenarios:
    """Tests with realistic forbidden patterns."""

    def test_block_dangerous_shell_commands(self):
        """Block dangerous shell commands."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "forbidden_patterns": [
                    r"rm\s+-rf",
                    r"rm\s+--recursive",
                    r"chmod\s+777",
                    r">\s*/dev/",
                ]
            }
        )

        dangerous_commands = [
            {"command": "rm -rf /"},
            {"command": "rm  -rf /home"},  # Extra space
            {"command": "rm --recursive --force /"},
            {"command": "chmod 777 /etc/passwd"},
            {"command": "echo '' > /dev/sda"},
        ]

        for args in dangerous_commands:
            with pytest.raises(ToolCallBlocked):
                enforcer.validate_tool_call("bash", args)

    def test_block_sql_injection_patterns(self):
        """Block SQL injection patterns."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "forbidden_patterns": [
                    r"DROP\s+TABLE",
                    r"DELETE\s+FROM\s+\w+\s*;",
                    r"--\"",  # SQL comment before closing quote (in JSON)
                    r";\s*DROP",
                ]
            }
        )

        dangerous_queries = [
            {"query": "DROP TABLE users"},
            {"query": "DELETE FROM users;"},
            {"query": "SELECT * FROM users --"},  # Ends with -- before " in JSON
            {"query": "SELECT 1; DROP TABLE users"},
        ]

        for args in dangerous_queries:
            with pytest.raises(ToolCallBlocked):
                enforcer.validate_tool_call("database", args)

    def test_block_credential_exposure(self):
        """Block patterns that might expose credentials."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "forbidden_patterns": [
                    r"api[_-]?key\s*=",
                    r"password\s*=",
                    r"secret\s*=",
                    r"token\s*=",
                ]
            }
        )

        dangerous_args = [
            {"content": "api_key = 'sk-abc123'"},
            {"content": "password = hunter2"},
            {"content": "SECRET= mysecrect"},
            {"content": "token='Bearer xxx'"},
        ]

        for args in dangerous_args:
            with pytest.raises(ToolCallBlocked):
                enforcer.validate_tool_call("write_file", args)

    def test_allow_safe_operations(self):
        """Safe operations should pass."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "forbidden_patterns": [
                    r"rm\s+-rf",
                    r"DROP\s+TABLE",
                ]
            }
        )

        safe_commands = [
            {"command": "ls -la"},
            {"command": "cat /etc/hostname"},
            {"command": "git status"},
            {"query": "SELECT * FROM users WHERE id = 1"},
            {"content": "Normal file content"},
        ]

        for args in safe_commands:
            # Should not raise
            enforcer.validate_tool_call("tool", args)


# =============================================================================
# create_enforcer_for_run Tests
# =============================================================================

class TestCreateEnforcerForRun:
    """Tests for the HarnessKernel integration function."""

    def test_create_enforcer(self):
        """Create enforcer for a run."""
        mock_spec = MagicMock()
        mock_spec.id = "run-spec-123"
        mock_spec.tool_policy = {
            "forbidden_patterns": ["test_pattern"],
        }

        enforcer = create_enforcer_for_run(mock_spec)

        assert enforcer.spec_id == "run-spec-123"
        assert enforcer.pattern_count == 1

    def test_create_enforcer_strict_mode(self):
        """Create enforcer in strict mode."""
        mock_spec = MagicMock()
        mock_spec.id = "spec"
        mock_spec.tool_policy = {
            "forbidden_patterns": ["[invalid"],
        }

        with pytest.raises(PatternCompilationError):
            create_enforcer_for_run(mock_spec, strict=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
