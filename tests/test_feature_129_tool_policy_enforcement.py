"""
Tests for Feature #129: Tool policy enforcement filters tools and blocks forbidden patterns.

During kernel execution via the --spec path, the tool policy from the AgentSpec is enforced.
The turn executor or kernel must filter tool calls against spec.tool_policy.allowed_tools
(only permitted tools can be invoked) and check tool arguments against
spec.tool_policy.forbidden_patterns (regex patterns for dangerous operations like
'rm -rf /', 'DROP TABLE', 'chmod 777'). When a tool call is blocked, the kernel records a
policy violation event but does NOT crash the run — execution continues with an error
result for that tool call.

Verification Steps:
1. Verify that the turn executor or kernel checks each tool call against tool_policy.allowed_tools
2. Verify that a tool NOT in allowed_tools is blocked and returns an error to the agent
3. Verify that tool arguments are checked against tool_policy.forbidden_patterns
4. Verify that a tool call matching a forbidden pattern is blocked
5. Verify that blocked tool calls are logged as events (event_type containing policy violation info)
6. Verify that a blocked tool call does NOT terminate the run — execution continues on the next turn
7. Verify that forbidden_patterns are compiled as regex and cached for performance
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import the modules under test
from api.harness_kernel import HarnessKernel, BudgetTracker
from api.tool_policy import (
    ToolPolicyEnforcer,
    ToolCallBlocked,
    ForbiddenToolBlocked,
    compile_forbidden_patterns,
    create_enforcer_for_run,
    record_policy_violation_event,
    record_allowed_tools_violation,
    record_forbidden_patterns_violation,
    PolicyViolation,
    CompiledPattern,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    from api.agentspec_models import Base
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_spec(db_session):
    """Create a sample AgentSpec with tool_policy for testing."""
    from api.agentspec_models import AgentSpec

    spec = AgentSpec(
        id=str(uuid.uuid4()),
        name="test-tool-policy-spec",
        display_name="Test Tool Policy Spec",
        task_type="coding",
        objective="Test tool policy enforcement",
        max_turns=10,
        timeout_seconds=300,
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Glob", "Grep", "Bash"],
            "forbidden_patterns": [
                r"rm\s+-rf\s+/",
                r"DROP\s+TABLE",
                r"chmod\s+777",
            ],
        },
        context={"project_dir": "/tmp/test"},
    )

    db_session.add(spec)
    db_session.commit()
    db_session.refresh(spec)
    return spec


@pytest.fixture
def restricted_spec(db_session):
    """Create a spec with limited allowed_tools (audit-style)."""
    from api.agentspec_models import AgentSpec

    spec = AgentSpec(
        id=str(uuid.uuid4()),
        name="test-restricted-spec",
        display_name="Test Restricted Spec",
        task_type="audit",
        objective="Test restricted tool access",
        max_turns=5,
        timeout_seconds=120,
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Glob", "Grep"],
            "forbidden_patterns": [
                r"rm\s+-rf",
                r"DROP\s+TABLE",
                r"chmod\s+777",
                r"sudo\s+",
            ],
        },
        context={},
    )

    db_session.add(spec)
    db_session.commit()
    db_session.refresh(spec)
    return spec


def _make_turn_executor_with_tool_events(tool_events_per_turn, max_turns=2):
    """
    Create a mock turn executor that returns specified tool events.

    Args:
        tool_events_per_turn: List of lists of tool event dicts, one per turn.
        max_turns: Maximum turns before signaling completion.

    Returns:
        A callable that matches the turn_executor signature.
    """
    call_count = [0]

    def executor(run, spec):
        turn_idx = call_count[0]
        call_count[0] += 1

        # Get tool events for this turn
        if turn_idx < len(tool_events_per_turn):
            events = tool_events_per_turn[turn_idx]
        else:
            events = []

        # Signal completion if we've exhausted turns
        completed = call_count[0] >= max_turns or turn_idx >= len(tool_events_per_turn) - 1

        turn_data = {"response_text": f"Turn {turn_idx + 1} response"}
        return (completed, turn_data, events, 100, 50)

    return executor


# =============================================================================
# Step 1: Verify kernel checks each tool call against tool_policy.allowed_tools
# =============================================================================

class TestStep1AllowedToolsCheck:
    """Verify that the turn executor or kernel checks each tool call against
    tool_policy.allowed_tools."""

    def test_kernel_initializes_tool_policy_enforcer(self, db_session, sample_spec):
        """Kernel should create a ToolPolicyEnforcer during execute()."""
        kernel = HarnessKernel(db_session)

        # Use a single-turn executor that completes immediately
        tool_events = [
            {"tool_name": "Read", "arguments": {"path": "/tmp/test.py"}, "result": "file content"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Run should complete (allowed tool)
        assert run.status in ("completed", "running")

    def test_enforcer_created_from_spec_tool_policy(self, sample_spec):
        """ToolPolicyEnforcer should be created from spec.tool_policy."""
        enforcer = create_enforcer_for_run(sample_spec)

        assert enforcer is not None
        assert enforcer.spec_id == sample_spec.id
        assert enforcer.allowed_tools == ["Read", "Write", "Glob", "Grep", "Bash"]
        assert len(enforcer.forbidden_patterns) == 3

    def test_allowed_tool_passes_validation(self, sample_spec):
        """An allowed tool should pass validation without raising."""
        enforcer = create_enforcer_for_run(sample_spec)

        # These should not raise
        enforcer.validate_tool_call("Read", {"path": "/tmp/test.py"})
        enforcer.validate_tool_call("Write", {"path": "/tmp/output.txt", "content": "hello"})
        enforcer.validate_tool_call("Bash", {"command": "ls -la"})


# =============================================================================
# Step 2: Verify tool NOT in allowed_tools is blocked with error
# =============================================================================

class TestStep2BlockedToolReturnsError:
    """Verify that a tool NOT in allowed_tools is blocked and returns an error
    to the agent."""

    def test_tool_not_in_allowed_tools_raises(self, sample_spec):
        """A tool not in allowed_tools should raise ToolCallBlocked."""
        enforcer = create_enforcer_for_run(sample_spec)

        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("ForbiddenTool", {"arg": "value"})

        assert "not in allowed_tools" in str(exc_info.value)

    def test_kernel_blocks_tool_not_in_allowed_tools(self, db_session, restricted_spec):
        """Kernel should block tools not in allowed_tools and return error result."""
        kernel = HarnessKernel(db_session)

        # Tool event with a tool NOT in allowed_tools (Write is not in audit spec)
        tool_events = [
            {"tool_name": "Write", "arguments": {"path": "/tmp/hack.py", "content": "bad"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(restricted_spec, turn_executor=executor)

        # Run should NOT crash - should complete or be in terminal state
        assert run.status in ("completed", "failed", "timeout")

        # Check that policy violation events were recorded
        from api.agentspec_models import AgentEvent
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()

        assert len(events) >= 1
        violation_event = events[0]
        assert violation_event.payload["tool"] == "Write"

    def test_check_tool_call_returns_error_tuple(self, sample_spec):
        """check_tool_call should return (False, pattern, error) for blocked tools."""
        enforcer = create_enforcer_for_run(sample_spec)

        allowed, pattern, error = enforcer.check_tool_call("NotAllowed", {})

        assert allowed is False
        assert pattern == "[not_in_allowed_tools]"
        assert "not in allowed_tools" in error


# =============================================================================
# Step 3: Verify tool arguments checked against forbidden_patterns
# =============================================================================

class TestStep3ForbiddenPatternsCheck:
    """Verify that tool arguments are checked against tool_policy.forbidden_patterns."""

    def test_safe_arguments_pass(self, sample_spec):
        """Safe arguments should pass forbidden pattern checks."""
        enforcer = create_enforcer_for_run(sample_spec)

        # These should all pass
        enforcer.validate_tool_call("Bash", {"command": "ls -la /tmp"})
        enforcer.validate_tool_call("Bash", {"command": "python3 test.py"})
        enforcer.validate_tool_call("Read", {"path": "/tmp/safe_file.py"})

    def test_dangerous_arguments_detected(self, sample_spec):
        """Dangerous arguments matching forbidden_patterns should be detected."""
        enforcer = create_enforcer_for_run(sample_spec)

        # rm -rf / should be blocked
        with pytest.raises(ToolCallBlocked) as exc_info:
            enforcer.validate_tool_call("Bash", {"command": "rm -rf /"})

        assert exc_info.value.pattern_matched == r"rm\s+-rf\s+/"

    def test_drop_table_blocked(self, sample_spec):
        """DROP TABLE should be blocked by forbidden patterns."""
        enforcer = create_enforcer_for_run(sample_spec)

        with pytest.raises(ToolCallBlocked):
            enforcer.validate_tool_call("Bash", {"command": "mysql -e 'DROP TABLE users'"})

    def test_chmod_777_blocked(self, sample_spec):
        """chmod 777 should be blocked by forbidden patterns."""
        enforcer = create_enforcer_for_run(sample_spec)

        with pytest.raises(ToolCallBlocked):
            enforcer.validate_tool_call("Bash", {"command": "chmod 777 /etc/shadow"})


# =============================================================================
# Step 4: Verify tool call matching forbidden pattern is blocked
# =============================================================================

class TestStep4ForbiddenPatternBlocking:
    """Verify that a tool call matching a forbidden pattern is blocked."""

    def test_kernel_blocks_forbidden_pattern_tool_call(self, db_session, sample_spec):
        """Kernel should block tool calls with arguments matching forbidden patterns."""
        kernel = HarnessKernel(db_session)

        # Tool event with dangerous arguments
        tool_events = [
            {
                "tool_name": "Bash",
                "arguments": {"command": "rm -rf /important/data"},
                "result": "executed",
            },
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Run should not crash
        assert run.status in ("completed", "failed", "timeout")

        # Check tool_result events for the blocked call
        from api.agentspec_models import AgentEvent
        tool_result_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "tool_result",
        ).all()

        # The blocked tool call should have is_error=True in its result
        blocked_results = [
            e for e in tool_result_events
            if e.payload.get("is_error") is True
        ]
        assert len(blocked_results) >= 1

    def test_enforcer_filter_replaces_blocked_event(self):
        """_filter_tool_events_with_policy should replace blocked events with error events."""
        from api.agentspec_models import Base
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        kernel = HarnessKernel(session)

        # Create a simple enforcer with forbidden_patterns
        kernel._tool_policy_enforcer = ToolPolicyEnforcer(
            spec_id="test-spec",
            allowed_tools=["Read", "Bash"],
            forbidden_patterns=compile_forbidden_patterns([r"rm\s+-rf\s+/"]),
        )

        # Create a mock run_id
        run_id = str(uuid.uuid4())

        tool_events = [
            {"tool_name": "Read", "arguments": {"path": "/tmp/safe.py"}, "result": "ok"},
            {"tool_name": "Bash", "arguments": {"command": "rm -rf /"}, "result": "executed"},
        ]

        filtered = kernel._filter_tool_events_with_policy(run_id, tool_events, turn_number=1)

        # First event should pass through unchanged
        assert filtered[0]["tool_name"] == "Read"
        assert filtered[0].get("blocked_by_policy") is None or filtered[0].get("blocked_by_policy") is not True

        # Second event should be blocked
        assert filtered[1]["tool_name"] == "Bash"
        assert filtered[1]["is_error"] is True
        assert filtered[1].get("blocked_by_policy") is True
        assert "blocked" in filtered[1]["result"].lower() or "forbidden" in filtered[1]["result"].lower()

        session.close()


# =============================================================================
# Step 5: Verify blocked tool calls logged as policy_violation events
# =============================================================================

class TestStep5PolicyViolationEvents:
    """Verify that blocked tool calls are logged as events
    (event_type containing policy violation info)."""

    def test_blocked_tool_creates_policy_violation_event(self, db_session, restricted_spec):
        """Blocked tool calls should create policy_violation events in the database."""
        kernel = HarnessKernel(db_session)

        # Use a tool NOT in allowed_tools (Write not allowed for audit spec)
        tool_events = [
            {"tool_name": "Write", "arguments": {"path": "/tmp/file.py", "content": "data"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(restricted_spec, turn_executor=executor)

        # Query policy violation events
        from api.agentspec_models import AgentEvent
        violations = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()

        assert len(violations) >= 1

        violation = violations[0]
        assert violation.event_type == "policy_violation"
        assert violation.payload["tool"] == "Write"
        assert "violation_type" in violation.payload

    def test_forbidden_pattern_creates_violation_event(self, db_session, sample_spec):
        """Forbidden pattern matches should create policy_violation events."""
        kernel = HarnessKernel(db_session)

        # Use an allowed tool but with forbidden arguments
        tool_events = [
            {"tool_name": "Bash", "arguments": {"command": "DROP TABLE users"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Query policy violation events
        from api.agentspec_models import AgentEvent
        violations = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()

        assert len(violations) >= 1

        violation = violations[0]
        assert violation.payload["violation_type"] == "forbidden_patterns"
        assert "DROP" in violation.payload["details"].get("pattern_matched", "")

    def test_violation_event_has_turn_number(self, db_session, sample_spec):
        """Policy violation events should include the turn_number for context."""
        kernel = HarnessKernel(db_session)

        tool_events = [
            {"tool_name": "Bash", "arguments": {"command": "chmod 777 /etc/passwd"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(sample_spec, turn_executor=executor)

        from api.agentspec_models import AgentEvent
        violations = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()

        assert len(violations) >= 1
        # turn_number should be present in payload
        assert "turn_number" in violations[0].payload


# =============================================================================
# Step 6: Verify blocked tool call does NOT terminate the run
# =============================================================================

class TestStep6RunContinuesAfterBlock:
    """Verify that a blocked tool call does NOT terminate the run —
    execution continues on the next turn."""

    def test_run_continues_after_blocked_tool(self, db_session, sample_spec):
        """Run should continue executing after a tool call is blocked."""
        kernel = HarnessKernel(db_session)

        # Two turns: first has a blocked tool, second has a safe tool
        turn1_events = [
            {"tool_name": "Bash", "arguments": {"command": "rm -rf /"}, "result": "executed"},
        ]
        turn2_events = [
            {"tool_name": "Read", "arguments": {"path": "/tmp/safe.py"}, "result": "file content"},
        ]

        executor = _make_turn_executor_with_tool_events(
            [turn1_events, turn2_events], max_turns=2
        )

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Run should have completed (not crashed)
        assert run.status in ("completed", "failed", "timeout")

        # Both turns should have been executed
        assert run.turns_used >= 2

    def test_multiple_blocked_tools_dont_crash(self, db_session, restricted_spec):
        """Multiple blocked tool calls in sequence should not crash the run."""
        kernel = HarnessKernel(db_session)

        # Multiple turns with blocked tools
        turn1_events = [
            {"tool_name": "Write", "arguments": {"path": "/tmp/a.py"}, "result": "ok"},
            {"tool_name": "Edit", "arguments": {"path": "/tmp/b.py"}, "result": "ok"},
        ]
        turn2_events = [
            {"tool_name": "Bash", "arguments": {"command": "npm install"}, "result": "ok"},
        ]
        turn3_events = [
            {"tool_name": "Read", "arguments": {"path": "/tmp/safe.py"}, "result": "content"},
        ]

        executor = _make_turn_executor_with_tool_events(
            [turn1_events, turn2_events, turn3_events], max_turns=3
        )

        run = kernel.execute(restricted_spec, turn_executor=executor)

        # Run should not have crashed
        assert run.status in ("completed", "failed", "timeout")
        assert run.turns_used >= 2  # At least the first two turns executed

    def test_run_status_not_failed_from_policy_block(self, db_session, sample_spec):
        """A policy-blocked tool call should not set run status to 'failed'."""
        kernel = HarnessKernel(db_session)

        # One blocked tool, then completion
        tool_events = [
            {"tool_name": "Bash", "arguments": {"command": "DROP TABLE users"}, "result": "ok"},
            {"tool_name": "Read", "arguments": {"path": "/tmp/safe.py"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Run should be completed, not failed
        assert run.status == "completed"


# =============================================================================
# Step 7: Verify forbidden_patterns compiled as regex and cached for performance
# =============================================================================

class TestStep7RegexCachedPerformance:
    """Verify that forbidden_patterns are compiled as regex and cached
    for performance."""

    def test_patterns_compiled_as_regex(self):
        """Forbidden patterns should be compiled into re.Pattern objects."""
        patterns = [r"rm\s+-rf\s+/", r"DROP\s+TABLE", r"chmod\s+777"]
        compiled = compile_forbidden_patterns(patterns)

        assert len(compiled) == 3
        for cp in compiled:
            assert isinstance(cp, CompiledPattern)
            assert isinstance(cp.regex, re.Pattern)
            assert cp.original in patterns

    def test_compiled_patterns_cached_in_enforcer(self, sample_spec):
        """Enforcer should cache compiled patterns for reuse across calls."""
        enforcer = create_enforcer_for_run(sample_spec)

        # Patterns should be pre-compiled
        assert len(enforcer.forbidden_patterns) == 3
        for cp in enforcer.forbidden_patterns:
            assert isinstance(cp.regex, re.Pattern)

        # The same compiled objects should be reused across validate calls
        patterns_before = [id(cp.regex) for cp in enforcer.forbidden_patterns]

        # Call validate multiple times
        enforcer.validate_tool_call("Read", {"path": "/tmp/test"})
        enforcer.validate_tool_call("Read", {"path": "/tmp/test2"})
        enforcer.validate_tool_call("Read", {"path": "/tmp/test3"})

        patterns_after = [id(cp.regex) for cp in enforcer.forbidden_patterns]

        # Same regex objects (same memory addresses = cached)
        assert patterns_before == patterns_after

    def test_compile_once_use_many_times(self):
        """Patterns should be compiled once and used for multiple checks."""
        patterns = [r"rm\s+-rf\s+/", r"DROP\s+TABLE"]
        compiled = compile_forbidden_patterns(patterns)

        # Use each pattern to match against multiple strings
        for cp in compiled:
            # Each compiled pattern should work for matching
            assert cp.regex.search("rm -rf /") is not None or cp.regex.search("DROP TABLE users") is not None

    def test_kernel_initializes_enforcer_once_per_execute(self, db_session, sample_spec):
        """Kernel should initialize enforcer once at start of execute(), not per tool call."""
        kernel = HarnessKernel(db_session)

        # Track calls to create_enforcer_for_run
        with patch("api.harness_kernel.create_enforcer_for_run", wraps=create_enforcer_for_run) as mock_create:
            tool_events = [
                {"tool_name": "Read", "arguments": {"path": "/tmp/a"}, "result": "ok"},
            ]
            executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)
            run = kernel.execute(sample_spec, turn_executor=executor)

            # create_enforcer_for_run should have been called exactly once
            assert mock_create.call_count == 1

    def test_invalid_regex_pattern_handled_gracefully(self):
        """Invalid regex patterns should be skipped gracefully (non-strict mode)."""
        patterns = [r"rm\s+-rf\s+/", r"[invalid(regex", r"DROP\s+TABLE"]
        compiled = compile_forbidden_patterns(patterns, strict=False)

        # Invalid pattern should be skipped
        assert len(compiled) == 2
        originals = {cp.original for cp in compiled}
        assert r"rm\s+-rf\s+/" in originals
        assert r"DROP\s+TABLE" in originals
        assert r"[invalid(regex" not in originals

    def test_case_insensitive_matching(self):
        """Forbidden patterns should match case-insensitively."""
        patterns = [r"DROP\s+TABLE"]
        compiled = compile_forbidden_patterns(patterns)

        assert len(compiled) == 1
        # Should match regardless of case
        assert compiled[0].regex.search("drop table users") is not None
        assert compiled[0].regex.search("DROP TABLE users") is not None
        assert compiled[0].regex.search("Drop Table users") is not None


# =============================================================================
# Integration Test: Full Execute Loop with Policy Enforcement
# =============================================================================

class TestIntegration:
    """Full integration tests for tool policy enforcement in execute()."""

    def test_full_execute_with_mixed_tool_events(self, db_session, sample_spec):
        """Full execution with a mix of allowed, blocked-by-pattern, and safe tool calls."""
        kernel = HarnessKernel(db_session)

        # Turn 1: Safe read + dangerous bash
        turn1_events = [
            {"tool_name": "Read", "arguments": {"path": "/tmp/test.py"}, "result": "content"},
            {"tool_name": "Bash", "arguments": {"command": "rm -rf /"}, "result": "executed"},
        ]
        # Turn 2: Safe bash
        turn2_events = [
            {"tool_name": "Bash", "arguments": {"command": "ls -la"}, "result": "files"},
        ]

        executor = _make_turn_executor_with_tool_events(
            [turn1_events, turn2_events], max_turns=2
        )

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Run should complete successfully
        assert run.status in ("completed", "failed", "timeout")
        assert run.turns_used == 2

        # Should have policy violation events for the blocked call
        from api.agentspec_models import AgentEvent
        violations = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()
        assert len(violations) >= 1

        # Should also have tool_call events for the allowed calls
        tool_calls = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "tool_call",
        ).all()
        assert len(tool_calls) >= 2  # At least the allowed ones

    def test_no_tool_policy_allows_all(self, db_session):
        """When no tool_policy is set, all tools should be allowed."""
        from api.agentspec_models import AgentSpec

        spec = AgentSpec(
            id=str(uuid.uuid4()),
            name="no-policy-spec",
            display_name="No Policy Spec",
            task_type="coding",
            objective="Test no policy",
            max_turns=5,
            timeout_seconds=120,
            tool_policy={},  # Empty policy (no restrictions)
            context={},
        )
        db_session.add(spec)
        db_session.commit()
        db_session.refresh(spec)

        kernel = HarnessKernel(db_session)

        tool_events = [
            {"tool_name": "AnyTool", "arguments": {"anything": "goes"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(spec, turn_executor=executor)

        # Should complete without policy violations
        assert run.status in ("completed", "failed", "timeout")

        from api.agentspec_models import AgentEvent
        violations = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "policy_violation",
        ).all()
        assert len(violations) == 0

    def test_enforcer_cleaned_up_after_execute(self, db_session, sample_spec):
        """Tool policy enforcer should be cleaned up after execute() completes."""
        kernel = HarnessKernel(db_session)

        tool_events = [
            {"tool_name": "Read", "arguments": {"path": "/tmp/test"}, "result": "ok"},
        ]
        executor = _make_turn_executor_with_tool_events([tool_events], max_turns=1)

        run = kernel.execute(sample_spec, turn_executor=executor)

        # Enforcer should be cleaned up
        assert kernel._tool_policy_enforcer is None
