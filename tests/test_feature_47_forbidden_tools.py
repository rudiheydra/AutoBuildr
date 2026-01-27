"""
Tests for Feature #47: Forbidden Tools Explicit Blocking
=========================================================

This test suite verifies that:
1. Extract forbidden_tools from spec.tool_policy
2. After filtering by allowed_tools, also remove forbidden_tools
3. Block any tool call to forbidden tool
4. Record policy violation event
5. Return clear error message to agent
"""

import pytest
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import Base from database module directly to avoid api/__init__.py (which has dspy dependency)
from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    generate_uuid,
)
# Import directly from api.tool_policy to avoid dspy dependency in api/__init__.py
from api.tool_policy import (
    # Feature #47 exports
    ForbiddenToolBlocked,
    extract_forbidden_tools,
    create_forbidden_tools_violation,
    record_forbidden_tools_violation,
    # Other needed exports
    ToolPolicyEnforcer,
    ToolCallBlocked,
    PolicyViolation,
    VIOLATION_TYPES,
    record_policy_violation_event,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a database session for testing."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_spec(session):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="coding",
        tool_policy={
            "allowed_tools": ["Read", "Write", "Edit", "Bash"],
            "forbidden_tools": ["Bash", "shell", "exec"],
            "forbidden_patterns": ["rm -rf"],
        },
        max_turns=50,
        timeout_seconds=1800,
    )
    session.add(spec)
    session.commit()
    return spec


@pytest.fixture
def sample_run(session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_spec.id,
        status="running",
        turns_used=5,
        tokens_in=1000,
        tokens_out=500,
    )
    session.add(run)
    session.commit()
    return run


# =============================================================================
# Step 1: Extract forbidden_tools from spec.tool_policy
# =============================================================================

class TestExtractForbiddenTools:
    """Tests for extracting forbidden_tools from tool_policy."""

    def test_extract_from_valid_policy(self):
        """Extract forbidden_tools from a valid tool policy."""
        policy = {
            "allowed_tools": None,
            "forbidden_tools": ["Bash", "shell", "exec"],
        }
        result = extract_forbidden_tools(policy)
        assert result == ["Bash", "shell", "exec"]

    def test_extract_empty_list(self):
        """Empty forbidden_tools returns empty list."""
        policy = {"forbidden_tools": []}
        result = extract_forbidden_tools(policy)
        assert result == []

    def test_extract_none_value(self):
        """None forbidden_tools returns empty list."""
        policy = {"forbidden_tools": None}
        result = extract_forbidden_tools(policy)
        assert result == []

    def test_extract_missing_key(self):
        """Missing forbidden_tools key returns empty list."""
        policy = {"allowed_tools": ["Read"]}
        result = extract_forbidden_tools(policy)
        assert result == []

    def test_extract_none_policy(self):
        """None policy returns empty list."""
        result = extract_forbidden_tools(None)
        assert result == []

    def test_extract_non_list_value(self):
        """Non-list forbidden_tools returns empty list with warning."""
        policy = {"forbidden_tools": "Bash"}  # String instead of list
        result = extract_forbidden_tools(policy)
        assert result == []

    def test_extract_filters_non_strings(self):
        """Non-string entries in forbidden_tools are filtered out."""
        policy = {"forbidden_tools": ["Bash", 123, None, "shell", {}, "exec"]}
        result = extract_forbidden_tools(policy)
        assert result == ["Bash", "shell", "exec"]

    def test_extract_strips_whitespace(self):
        """Tool names are stripped of whitespace."""
        policy = {"forbidden_tools": ["  Bash  ", "shell ", " exec"]}
        result = extract_forbidden_tools(policy)
        assert result == ["Bash", "shell", "exec"]

    def test_extract_filters_empty_strings(self):
        """Empty strings are filtered out."""
        policy = {"forbidden_tools": ["Bash", "", "   ", "shell"]}
        result = extract_forbidden_tools(policy)
        assert result == ["Bash", "shell"]


# =============================================================================
# Step 2: After filtering by allowed_tools, also remove forbidden_tools
# =============================================================================

class TestForbiddenToolsTakesPrecedence:
    """Tests that forbidden_tools takes precedence over allowed_tools."""

    def test_forbidden_overrides_allowed(self):
        """Tool in both allowed and forbidden should be blocked."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={
                "allowed_tools": ["Read", "Write", "Bash"],  # Bash is allowed
                "forbidden_tools": ["Bash"],  # But also forbidden
            },
        )

        # Read should work (allowed, not forbidden)
        enforcer.validate_tool_call("Read", {"path": "/test.txt"})

        # Bash should be blocked (forbidden takes precedence)
        with pytest.raises(ForbiddenToolBlocked) as exc_info:
            enforcer.validate_tool_call("Bash", {"command": "ls"})

        assert exc_info.value.tool_name == "Bash"

    def test_not_in_allowed_blocked_first(self):
        """Tool not in allowed_tools blocked before forbidden check."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={
                "allowed_tools": ["Read", "Write"],
                "forbidden_tools": ["exec"],
            },
        )

        # shell is not in allowed_tools, so ToolCallBlocked is raised
        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("shell", {"command": "ls"})

        # The error message should indicate allowed_tools violation
        assert "[not_in_allowed_tools]" in exc_info.value.pattern_matched

    def test_all_allowed_but_some_forbidden(self):
        """When all tools allowed (allowed_tools=None), forbidden still blocks."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={
                "allowed_tools": None,  # All tools allowed
                "forbidden_tools": ["Bash", "shell"],
            },
        )

        # Read should work (all allowed, not forbidden)
        enforcer.validate_tool_call("Read", {"path": "/test.txt"})

        # Bash should be blocked (forbidden)
        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("Bash", {"command": "ls"})


# =============================================================================
# Step 3: Block any tool call to forbidden tool
# =============================================================================

class TestBlockForbiddenTools:
    """Tests for blocking forbidden tool calls."""

    def test_forbidden_tool_raises_exception(self):
        """Calling a forbidden tool raises ForbiddenToolBlocked."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash", "shell", "exec"]},
        )

        with pytest.raises(ForbiddenToolBlocked) as exc_info:
            enforcer.validate_tool_call("Bash", {"command": "ls"})

        assert exc_info.value.tool_name == "Bash"
        assert "Bash" in exc_info.value.forbidden_tools

    def test_multiple_forbidden_tools(self):
        """All tools in forbidden list are blocked."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash", "shell", "exec"]},
        )

        for tool in ["Bash", "shell", "exec"]:
            with pytest.raises(ForbiddenToolBlocked) as exc_info:
                enforcer.validate_tool_call(tool, {"cmd": "test"})
            assert exc_info.value.tool_name == tool

    def test_non_forbidden_tool_passes(self):
        """Tools not in forbidden list are allowed."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash", "shell"]},
        )

        # These should not raise
        enforcer.validate_tool_call("Read", {"path": "/test.txt"})
        enforcer.validate_tool_call("Write", {"path": "/test.txt", "content": "test"})
        enforcer.validate_tool_call("Edit", {"path": "/test.txt", "search": "a", "replace": "b"})

    def test_case_sensitive_blocking(self):
        """Forbidden tools are case-sensitive."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash"]},  # Capital B
        )

        # "Bash" should be blocked
        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("Bash", {"command": "ls"})

        # "bash" should NOT be blocked (different case)
        # No exception raised
        enforcer.validate_tool_call("bash", {"command": "ls"})


# =============================================================================
# Step 4: Record policy violation event
# =============================================================================

class TestRecordViolationEvent:
    """Tests for recording forbidden_tools violation events."""

    def test_violation_type_in_list(self):
        """forbidden_tools violation type is in VIOLATION_TYPES."""
        assert "forbidden_tools" in VIOLATION_TYPES

    def test_create_violation_object(self):
        """Create a PolicyViolation for forbidden_tools."""
        violation = create_forbidden_tools_violation(
            tool_name="Bash",
            turn_number=5,
            forbidden_tools=["Bash", "shell", "exec"],
        )

        assert violation.violation_type == "forbidden_tools"
        assert violation.tool_name == "Bash"
        assert violation.turn_number == 5
        assert violation.details["blocked_tool"] == "Bash"
        assert violation.details["forbidden_tools"] == ["Bash", "shell", "exec"]
        assert violation.details["forbidden_tools_count"] == 3
        assert "explicitly blocked" in violation.message

    def test_create_violation_with_arguments(self):
        """Create violation with tool arguments."""
        violation = create_forbidden_tools_violation(
            tool_name="Bash",
            turn_number=5,
            forbidden_tools=["Bash"],
            arguments={"command": "rm -rf /"},
        )

        assert violation.details["arguments"] == {"command": "rm -rf /"}

    def test_create_violation_truncates_large_arguments(self):
        """Large arguments are truncated in violation details."""
        large_args = {"command": "x" * 1000}

        violation = create_forbidden_tools_violation(
            tool_name="Bash",
            turn_number=5,
            forbidden_tools=["Bash"],
            arguments=large_args,
        )

        assert "arguments_preview" in violation.details
        assert violation.details["arguments_preview"].endswith("...")

    def test_create_violation_truncates_many_forbidden_tools(self):
        """Many forbidden tools are truncated to first 10."""
        many_tools = [f"tool_{i}" for i in range(20)]

        violation = create_forbidden_tools_violation(
            tool_name="tool_0",
            turn_number=5,
            forbidden_tools=many_tools,
        )

        assert len(violation.details["forbidden_tools"]) == 11  # 10 + "..."
        assert violation.details["forbidden_tools"][-1] == "..."
        assert violation.details["forbidden_tools_count"] == 20

    def test_record_violation_event(self, session, sample_spec, sample_run):
        """Record a forbidden_tools violation event to database."""
        event = record_forbidden_tools_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="Bash",
            turn_number=5,
            forbidden_tools=["Bash", "shell"],
            arguments={"command": "ls"},
        )
        session.commit()

        # Verify event was created
        assert event.id is not None
        assert event.run_id == sample_run.id
        assert event.sequence == 1
        assert event.event_type == "policy_violation"
        assert event.tool_name == "Bash"

        # Verify payload
        payload = event.payload
        assert payload["violation_type"] == "forbidden_tools"
        assert payload["tool"] == "Bash"
        assert payload["turn_number"] == 5
        assert "Bash" in payload["details"]["forbidden_tools"]

    def test_violation_event_queryable(self, session, sample_spec, sample_run):
        """Violation events can be queried from database."""
        record_forbidden_tools_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="Bash",
            turn_number=5,
            forbidden_tools=["Bash"],
        )
        session.commit()

        # Query events
        events = session.query(AgentEvent).filter(
            AgentEvent.run_id == sample_run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()

        assert len(events) == 1
        assert events[0].payload["violation_type"] == "forbidden_tools"


# =============================================================================
# Step 5: Return clear error message to agent
# =============================================================================

class TestClearErrorMessage:
    """Tests for clear error messages returned to agent."""

    def test_exception_message_is_clear(self):
        """ForbiddenToolBlocked exception has clear message."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash"]},
        )

        with pytest.raises(ForbiddenToolBlocked) as exc_info:
            enforcer.validate_tool_call("Bash", {"command": "ls"})

        message = str(exc_info.value)
        assert "Bash" in message
        assert "blocked" in message.lower() or "forbidden" in message.lower()

    def test_error_message_method(self):
        """ToolPolicyEnforcer has method to get error message."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash", "shell"]},
        )

        message = enforcer.get_forbidden_tool_error_message("Bash")

        assert "Bash" in message
        assert "blocked" in message.lower()
        assert "forbidden_tools" in message or "blacklist" in message.lower()
        assert "alternative" in message.lower()

    def test_check_tool_call_returns_error(self):
        """check_tool_call returns error message instead of raising."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test-spec",
            tool_policy={"forbidden_tools": ["Bash"]},
        )

        allowed, pattern, error = enforcer.check_tool_call("Bash", {"command": "ls"})

        assert allowed is False
        assert pattern == "[forbidden_tool]"
        assert error is not None
        assert "Bash" in error


# =============================================================================
# ToolPolicyEnforcer Integration Tests
# =============================================================================

class TestToolPolicyEnforcerIntegration:
    """Integration tests for ToolPolicyEnforcer with forbidden_tools."""

    def test_from_spec_extracts_forbidden_tools(self, session, sample_spec):
        """ToolPolicyEnforcer.from_spec extracts forbidden_tools."""
        enforcer = ToolPolicyEnforcer.from_spec(sample_spec)

        assert enforcer.forbidden_tools == ["Bash", "shell", "exec"]
        assert enforcer.has_forbidden_tools is True
        assert enforcer.forbidden_tools_count == 3

    def test_from_tool_policy_extracts_forbidden_tools(self):
        """ToolPolicyEnforcer.from_tool_policy extracts forbidden_tools."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["Bash", "shell"]},
        )

        assert enforcer.forbidden_tools == ["Bash", "shell"]
        assert enforcer.has_forbidden_tools is True
        assert enforcer.forbidden_tools_count == 2

    def test_empty_forbidden_tools(self):
        """Empty forbidden_tools works correctly."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": []},
        )

        assert enforcer.forbidden_tools == []
        assert enforcer.has_forbidden_tools is False
        assert enforcer.forbidden_tools_count == 0

    def test_no_forbidden_tools_key(self):
        """Missing forbidden_tools key works correctly."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"allowed_tools": ["Read"]},
        )

        assert enforcer.forbidden_tools == []
        assert enforcer.has_forbidden_tools is False

    def test_to_dict_includes_forbidden_tools(self):
        """to_dict includes forbidden_tools."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["Bash", "shell"]},
        )

        result = enforcer.to_dict()

        assert "forbidden_tools" in result
        assert result["forbidden_tools"] == ["Bash", "shell"]

    def test_combined_policy_enforcement(self):
        """Test combined policy: allowed_tools, forbidden_tools, and patterns."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["Read", "Write", "Bash"],
                "forbidden_tools": ["Bash"],
                "forbidden_patterns": ["DROP TABLE"],
            },
        )

        # Read is allowed and not forbidden - OK
        enforcer.validate_tool_call("Read", {"path": "/test.txt"})

        # Bash is allowed but forbidden - BLOCKED by forbidden_tools
        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("Bash", {"command": "ls"})

        # Edit is not allowed - BLOCKED by allowed_tools
        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("Edit", {"path": "/test.txt"})
        assert "[not_in_allowed_tools]" in exc_info.value.pattern_matched

        # Write with forbidden pattern - BLOCKED by pattern
        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("Write", {"content": "DROP TABLE users"})
        assert "DROP TABLE" in exc_info.value.pattern_matched


# =============================================================================
# ForbiddenToolBlocked Exception Tests
# =============================================================================

class TestForbiddenToolBlockedException:
    """Tests for ForbiddenToolBlocked exception class."""

    def test_exception_attributes(self):
        """Exception has correct attributes."""
        exc = ForbiddenToolBlocked(
            tool_name="Bash",
            forbidden_tools=["Bash", "shell", "exec"],
        )

        assert exc.tool_name == "Bash"
        assert exc.forbidden_tools == ["Bash", "shell", "exec"]

    def test_exception_default_message(self):
        """Exception has default message if not provided."""
        exc = ForbiddenToolBlocked(
            tool_name="Bash",
            forbidden_tools=["Bash"],
        )

        message = str(exc)
        assert "Bash" in message
        assert "blocked" in message.lower() or "forbidden" in message.lower()

    def test_exception_custom_message(self):
        """Exception can have custom message."""
        exc = ForbiddenToolBlocked(
            tool_name="Bash",
            forbidden_tools=["Bash"],
            message="Custom error message for Bash",
        )

        assert str(exc) == "Custom error message for Bash"

    def test_exception_inheritance(self):
        """ForbiddenToolBlocked inherits from ToolPolicyError."""
        from api.tool_policy import ToolPolicyError

        exc = ForbiddenToolBlocked(
            tool_name="Bash",
            forbidden_tools=["Bash"],
        )

        assert isinstance(exc, ToolPolicyError)
        assert isinstance(exc, Exception)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_none_arguments_with_forbidden_tool(self):
        """Forbidden tool with None arguments."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["Bash"]},
        )

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("Bash", None)

    def test_empty_arguments_with_forbidden_tool(self):
        """Forbidden tool with empty arguments."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["Bash"]},
        )

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("Bash", {})

    def test_unicode_tool_names(self):
        """Forbidden tools with unicode names."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["工具", "ツール"]},
        )

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("工具", {})

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("ツール", {})

        # Non-forbidden unicode tool should pass
        enforcer.validate_tool_call("도구", {})

    def test_special_characters_in_tool_names(self):
        """Forbidden tools with special characters."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["tool-name", "tool_name", "tool.name"]},
        )

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("tool-name", {})

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("tool_name", {})

        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("tool.name", {})

    def test_empty_tool_name(self):
        """Empty tool name handling."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": [""]},  # Empty string gets filtered
        )

        # Empty string in forbidden_tools is filtered, so no exception
        assert enforcer.forbidden_tools == []

    def test_very_long_forbidden_tools_list(self):
        """Very long forbidden_tools list."""
        tools = [f"tool_{i}" for i in range(1000)]

        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": tools},
        )

        assert len(enforcer.forbidden_tools) == 1000

        # Check a tool in the middle
        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("tool_500", {})

        # Check a tool at the end
        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("tool_999", {})


# =============================================================================
# Verification Script Tests
# =============================================================================

class TestFeatureVerification:
    """Tests that verify all feature steps as described."""

    def test_step1_extract_forbidden_tools(self):
        """Step 1: Extract forbidden_tools from spec.tool_policy."""
        policy = {
            "policy_version": "v1",
            "allowed_tools": None,
            "forbidden_tools": ["Bash", "shell", "exec"],
        }

        result = extract_forbidden_tools(policy)

        assert result == ["Bash", "shell", "exec"]

    def test_step2_filter_after_allowed(self):
        """Step 2: After filtering by allowed_tools, also remove forbidden_tools."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={
                "allowed_tools": ["Read", "Write", "Bash"],
                "forbidden_tools": ["Bash"],
            },
        )

        # Bash is in allowed_tools but should be blocked by forbidden_tools
        with pytest.raises(ForbiddenToolBlocked):
            enforcer.validate_tool_call("Bash", {"command": "ls"})

    def test_step3_block_forbidden_tool_call(self):
        """Step 3: Block any tool call to forbidden tool."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["dangerous_tool"]},
        )

        with pytest.raises(ForbiddenToolBlocked) as exc_info:
            enforcer.validate_tool_call("dangerous_tool", {"arg": "value"})

        assert exc_info.value.tool_name == "dangerous_tool"

    def test_step4_record_policy_violation_event(self, session, sample_spec, sample_run):
        """Step 4: Record policy violation event."""
        event = record_forbidden_tools_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="Bash",
            turn_number=10,
            forbidden_tools=["Bash", "shell"],
        )
        session.commit()

        assert event.event_type == "policy_violation"
        assert event.payload["violation_type"] == "forbidden_tools"
        assert event.payload["turn_number"] == 10

    def test_step5_clear_error_message(self):
        """Step 5: Return clear error message to agent."""
        enforcer = ToolPolicyEnforcer.from_tool_policy(
            spec_id="test",
            tool_policy={"forbidden_tools": ["Bash"]},
        )

        with pytest.raises(ForbiddenToolBlocked) as exc_info:
            enforcer.validate_tool_call("Bash", {"command": "ls"})

        message = str(exc_info.value)

        # Message should be clear and informative
        assert "Bash" in message
        assert len(message) > 20  # Not too short
        assert "blocked" in message.lower() or "forbidden" in message.lower()
