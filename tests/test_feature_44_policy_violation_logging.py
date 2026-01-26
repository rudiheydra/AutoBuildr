"""
Tests for Feature #44: Policy Violation Event Logging
======================================================

This test suite verifies that:
1. policy_violation event type is defined
2. allowed_tools violations are recorded with context
3. forbidden_patterns violations record the pattern matched
4. directory_sandbox violations record the attempted path
5. Turn number is included in violation events
6. Violation counts are aggregated in run metadata
"""

import pytest
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.database import Base
from api.agentspec_models import (
    AgentSpec,
    AgentRun,
    AgentEvent,
    AcceptanceSpec,
    EVENT_TYPES,
    generate_uuid,
)
from api.tool_policy import (
    # Feature #44 exports
    PolicyViolation,
    ViolationAggregation,
    VIOLATION_TYPES,
    create_allowed_tools_violation,
    create_directory_sandbox_violation,
    create_forbidden_patterns_violation,
    get_violation_aggregation,
    record_allowed_tools_violation,
    record_and_aggregate_violation,
    record_directory_sandbox_violation,
    record_forbidden_patterns_violation,
    record_policy_violation_event,
    update_run_violation_metadata,
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
            "allowed_tools": ["Read", "Write"],
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
    )
    session.add(run)
    session.commit()
    return run


# =============================================================================
# Step 1: Define policy_violation event type
# =============================================================================

class TestPolicyViolationEventType:
    """Tests for policy_violation event type definition."""

    def test_policy_violation_in_event_types(self):
        """Verify policy_violation is in EVENT_TYPES."""
        assert "policy_violation" in EVENT_TYPES

    def test_violation_types_defined(self):
        """Verify VIOLATION_TYPES are defined."""
        assert "allowed_tools" in VIOLATION_TYPES
        assert "forbidden_patterns" in VIOLATION_TYPES
        assert "directory_sandbox" in VIOLATION_TYPES
        assert len(VIOLATION_TYPES) == 3


# =============================================================================
# Step 2: allowed_tools violation recording
# =============================================================================

class TestAllowedToolsViolation:
    """Tests for allowed_tools violation recording."""

    def test_create_allowed_tools_violation(self):
        """Test creating an allowed_tools violation."""
        violation = create_allowed_tools_violation(
            tool_name="Bash",
            turn_number=5,
            allowed_tools=["Read", "Write", "Edit"],
            arguments={"command": "ls -la"},
        )

        assert violation.violation_type == "allowed_tools"
        assert violation.tool_name == "Bash"
        assert violation.turn_number == 5
        assert violation.details["blocked_tool"] == "Bash"
        assert violation.details["allowed_tools"] == ["Read", "Write", "Edit"]
        assert violation.details["allowed_tools_count"] == 3
        assert "arguments" in violation.details
        assert "Bash" in violation.message
        assert "whitelist" in violation.message.lower()

    def test_create_allowed_tools_violation_truncates_long_list(self):
        """Test that long allowed_tools lists are truncated."""
        many_tools = [f"Tool{i}" for i in range(20)]
        violation = create_allowed_tools_violation(
            tool_name="NotAllowed",
            turn_number=3,
            allowed_tools=many_tools,
        )

        # Should be truncated to 10 + "..."
        assert len(violation.details["allowed_tools"]) == 11
        assert violation.details["allowed_tools"][-1] == "..."
        assert violation.details["allowed_tools_count"] == 20

    def test_create_allowed_tools_violation_truncates_long_args(self):
        """Test that long arguments are truncated."""
        long_args = {"data": "x" * 600}
        violation = create_allowed_tools_violation(
            tool_name="Tool",
            turn_number=1,
            allowed_tools=["Read"],
            arguments=long_args,
        )

        assert "arguments_preview" in violation.details
        assert "arguments" not in violation.details
        assert len(violation.details["arguments_preview"]) <= 510  # 500 + "..."

    def test_record_allowed_tools_violation(self, session, sample_run):
        """Test recording an allowed_tools violation event."""
        event = record_allowed_tools_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="Bash",
            turn_number=5,
            allowed_tools=["Read", "Write"],
            arguments={"cmd": "ls"},
        )
        session.commit()

        assert event.event_type == "policy_violation"
        assert event.tool_name == "Bash"
        assert event.payload["violation_type"] == "allowed_tools"
        assert event.payload["turn_number"] == 5
        assert event.payload["tool"] == "Bash"


# =============================================================================
# Step 3: forbidden_patterns violation recording
# =============================================================================

class TestForbiddenPatternsViolation:
    """Tests for forbidden_patterns violation recording."""

    def test_create_forbidden_patterns_violation(self):
        """Test creating a forbidden_patterns violation."""
        violation = create_forbidden_patterns_violation(
            tool_name="Bash",
            turn_number=10,
            pattern_matched="rm -rf",
            arguments={"command": "rm -rf /"},
        )

        assert violation.violation_type == "forbidden_patterns"
        assert violation.tool_name == "Bash"
        assert violation.turn_number == 10
        assert violation.details["pattern_matched"] == "rm -rf"
        assert violation.details["blocked_tool"] == "Bash"
        assert "rm -rf" in violation.message

    def test_record_forbidden_patterns_violation(self, session, sample_run):
        """Test recording a forbidden_patterns violation event."""
        event = record_forbidden_patterns_violation(
            db=session,
            run_id=sample_run.id,
            sequence=2,
            tool_name="Bash",
            turn_number=10,
            pattern_matched="DROP TABLE",
            arguments={"sql": "DROP TABLE users"},
        )
        session.commit()

        assert event.event_type == "policy_violation"
        assert event.payload["violation_type"] == "forbidden_patterns"
        assert event.payload["details"]["pattern_matched"] == "DROP TABLE"
        assert event.payload["turn_number"] == 10


# =============================================================================
# Step 4: directory_sandbox violation recording
# =============================================================================

class TestDirectorySandboxViolation:
    """Tests for directory_sandbox violation recording."""

    def test_create_directory_sandbox_violation(self):
        """Test creating a directory_sandbox violation."""
        violation = create_directory_sandbox_violation(
            tool_name="write_file",
            turn_number=15,
            attempted_path="/etc/passwd",
            reason="Path is not within any allowed directory",
            allowed_directories=["/home/user/project", "/tmp"],
            was_symlink=False,
        )

        assert violation.violation_type == "directory_sandbox"
        assert violation.tool_name == "write_file"
        assert violation.turn_number == 15
        assert violation.details["attempted_path"] == "/etc/passwd"
        assert violation.details["reason"] == "Path is not within any allowed directory"
        assert violation.details["allowed_directories"] == ["/home/user/project", "/tmp"]
        assert violation.details["was_symlink"] is False
        assert "/etc/passwd" in violation.blocked_operation

    def test_create_directory_sandbox_violation_with_symlink(self):
        """Test directory_sandbox violation for symlink."""
        violation = create_directory_sandbox_violation(
            tool_name="read_file",
            turn_number=20,
            attempted_path="/home/user/link",
            reason="Symlink resolves outside allowed directories",
            allowed_directories=["/home/user/project"],
            was_symlink=True,
        )

        assert violation.details["was_symlink"] is True

    def test_create_directory_sandbox_violation_truncates_dirs(self):
        """Test that many allowed_directories are truncated."""
        many_dirs = [f"/dir{i}" for i in range(10)]
        violation = create_directory_sandbox_violation(
            tool_name="write_file",
            turn_number=5,
            attempted_path="/outside",
            reason="Outside sandbox",
            allowed_directories=many_dirs,
        )

        # Should be truncated to 5 + "..."
        assert len(violation.details["allowed_directories"]) == 6
        assert violation.details["allowed_directories"][-1] == "..."
        assert violation.details["allowed_directories_count"] == 10

    def test_record_directory_sandbox_violation(self, session, sample_run):
        """Test recording a directory_sandbox violation event."""
        event = record_directory_sandbox_violation(
            db=session,
            run_id=sample_run.id,
            sequence=3,
            tool_name="write_file",
            turn_number=15,
            attempted_path="/etc/passwd",
            reason="Path not in sandbox",
            allowed_directories=["/home/project"],
            was_symlink=False,
        )
        session.commit()

        assert event.event_type == "policy_violation"
        assert event.payload["violation_type"] == "directory_sandbox"
        assert event.payload["details"]["attempted_path"] == "/etc/passwd"
        assert event.payload["turn_number"] == 15


# =============================================================================
# Step 5: Turn number context in events
# =============================================================================

class TestTurnNumberContext:
    """Tests for turn number context in violation events."""

    def test_turn_number_in_violation_payload(self, session, sample_run):
        """Verify turn_number is included in event payload."""
        violation = create_allowed_tools_violation(
            tool_name="Bash",
            turn_number=42,
            allowed_tools=["Read"],
        )
        event = record_policy_violation_event(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            violation=violation,
        )
        session.commit()

        assert event.payload["turn_number"] == 42

    def test_turn_number_in_all_violation_types(self, session, sample_run):
        """Verify turn_number is included for all violation types."""
        # Test allowed_tools
        v1 = create_allowed_tools_violation("T1", 10, ["Read"])
        e1 = record_policy_violation_event(session, sample_run.id, 1, v1)

        # Test forbidden_patterns
        v2 = create_forbidden_patterns_violation("T2", 20, "pattern")
        e2 = record_policy_violation_event(session, sample_run.id, 2, v2)

        # Test directory_sandbox
        v3 = create_directory_sandbox_violation("T3", 30, "/path", "reason", ["/dir"])
        e3 = record_policy_violation_event(session, sample_run.id, 3, v3)

        session.commit()

        assert e1.payload["turn_number"] == 10
        assert e2.payload["turn_number"] == 20
        assert e3.payload["turn_number"] == 30


# =============================================================================
# Step 6: Violation count aggregation
# =============================================================================

class TestViolationAggregation:
    """Tests for violation count aggregation in run metadata."""

    def test_violation_aggregation_class(self):
        """Test ViolationAggregation class."""
        agg = ViolationAggregation()
        assert agg.total_count == 0
        assert agg.by_type == {}
        assert agg.by_tool == {}
        assert agg.last_turn == 0

        # Add violations
        agg.add_violation("allowed_tools", "Bash", 5)
        agg.add_violation("forbidden_patterns", "Bash", 10)
        agg.add_violation("allowed_tools", "Write", 15)

        assert agg.total_count == 3
        assert agg.by_type == {"allowed_tools": 2, "forbidden_patterns": 1}
        assert agg.by_tool == {"Bash": 2, "Write": 1}
        assert agg.last_turn == 15

    def test_violation_aggregation_to_dict(self):
        """Test ViolationAggregation serialization."""
        agg = ViolationAggregation()
        agg.add_violation("allowed_tools", "Bash", 5)

        data = agg.to_dict()
        assert data["total_count"] == 1
        assert data["by_type"]["allowed_tools"] == 1
        assert data["by_tool"]["Bash"] == 1
        assert data["last_turn"] == 5

    def test_violation_aggregation_from_dict(self):
        """Test ViolationAggregation deserialization."""
        data = {
            "total_count": 5,
            "by_type": {"allowed_tools": 3, "forbidden_patterns": 2},
            "by_tool": {"Bash": 3, "Write": 2},
            "last_turn": 20,
        }

        agg = ViolationAggregation.from_dict(data)
        assert agg.total_count == 5
        assert agg.by_type == {"allowed_tools": 3, "forbidden_patterns": 2}
        assert agg.by_tool == {"Bash": 3, "Write": 2}
        assert agg.last_turn == 20

    def test_violation_aggregation_from_dict_empty(self):
        """Test ViolationAggregation from None/empty dict."""
        agg1 = ViolationAggregation.from_dict(None)
        assert agg1.total_count == 0

        agg2 = ViolationAggregation.from_dict({})
        assert agg2.total_count == 0

    def test_get_violation_aggregation(self, session, sample_run):
        """Test computing aggregation from events."""
        # Record some violations
        record_allowed_tools_violation(
            session, sample_run.id, 1, "Bash", 5, ["Read"]
        )
        record_forbidden_patterns_violation(
            session, sample_run.id, 2, "Bash", 10, "rm -rf"
        )
        record_directory_sandbox_violation(
            session, sample_run.id, 3, "write_file", 15, "/etc", "outside", ["/home"]
        )
        session.commit()

        agg = get_violation_aggregation(session, sample_run.id)

        assert agg.total_count == 3
        assert agg.by_type["allowed_tools"] == 1
        assert agg.by_type["forbidden_patterns"] == 1
        assert agg.by_type["directory_sandbox"] == 1
        assert agg.by_tool["Bash"] == 2
        assert agg.by_tool["write_file"] == 1
        assert agg.last_turn == 15

    def test_update_run_violation_metadata(self, session, sample_run):
        """Test updating run metadata with violation aggregation."""
        violation = create_allowed_tools_violation("Bash", 5, ["Read"])
        result = update_run_violation_metadata(session, sample_run.id, violation)
        session.commit()

        assert result["total_count"] == 1
        assert result["by_type"]["allowed_tools"] == 1

        # Add another violation
        violation2 = create_forbidden_patterns_violation("Bash", 10, "pattern")
        result2 = update_run_violation_metadata(session, sample_run.id, violation2)
        session.commit()

        assert result2["total_count"] == 2
        assert result2["by_type"]["allowed_tools"] == 1
        assert result2["by_type"]["forbidden_patterns"] == 1

        # Verify it's stored in the run
        session.refresh(sample_run)
        assert "violation_aggregation" in sample_run.acceptance_results
        assert sample_run.acceptance_results["violation_aggregation"]["total_count"] == 2

    def test_record_and_aggregate_violation(self, session, sample_run):
        """Test combined record and aggregate function."""
        violation = create_allowed_tools_violation("Bash", 5, ["Read"])
        event, aggregation = record_and_aggregate_violation(
            session, sample_run.id, 1, violation
        )
        session.commit()

        assert event.event_type == "policy_violation"
        assert aggregation["total_count"] == 1

        # Record another
        violation2 = create_forbidden_patterns_violation("Bash", 10, "pattern")
        event2, aggregation2 = record_and_aggregate_violation(
            session, sample_run.id, 2, violation2
        )
        session.commit()

        assert aggregation2["total_count"] == 2

    def test_update_run_violation_metadata_nonexistent_run(self, session):
        """Test updating metadata for non-existent run."""
        violation = create_allowed_tools_violation("Bash", 5, ["Read"])
        result = update_run_violation_metadata(session, "nonexistent-id", violation)

        assert result == {}


# =============================================================================
# PolicyViolation Dataclass Tests
# =============================================================================

class TestPolicyViolationDataclass:
    """Tests for PolicyViolation dataclass."""

    def test_policy_violation_to_dict(self):
        """Test PolicyViolation serialization."""
        violation = PolicyViolation(
            violation_type="allowed_tools",
            tool_name="Bash",
            turn_number=5,
            details={"key": "value"},
            message="Test message",
            blocked_operation="Call to Bash",
        )

        data = violation.to_dict()

        assert data["violation_type"] == "allowed_tools"
        assert data["tool_name"] == "Bash"
        assert data["turn_number"] == 5
        assert data["details"]["key"] == "value"
        assert data["message"] == "Test message"
        assert data["blocked_operation"] == "Call to Bash"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full violation logging workflow."""

    def test_full_violation_workflow(self, session, sample_run):
        """Test complete workflow of recording multiple violations."""
        # Record multiple violations of different types
        v1 = create_allowed_tools_violation("rm", 3, ["Read", "Write"])
        e1, agg1 = record_and_aggregate_violation(session, sample_run.id, 1, v1)

        v2 = create_forbidden_patterns_violation("Bash", 5, "DROP TABLE", {"sql": "DROP TABLE users"})
        e2, agg2 = record_and_aggregate_violation(session, sample_run.id, 2, v2)

        v3 = create_directory_sandbox_violation(
            "write_file", 7, "/etc/shadow", "Outside sandbox", ["/home/project"]
        )
        e3, agg3 = record_and_aggregate_violation(session, sample_run.id, 3, v3)

        session.commit()

        # Verify events were recorded
        events = (
            session.query(AgentEvent)
            .filter(AgentEvent.run_id == sample_run.id)
            .filter(AgentEvent.event_type == "policy_violation")
            .order_by(AgentEvent.sequence)
            .all()
        )

        assert len(events) == 3

        # Verify first event (allowed_tools)
        assert events[0].payload["violation_type"] == "allowed_tools"
        assert events[0].payload["turn_number"] == 3
        assert events[0].payload["tool"] == "rm"

        # Verify second event (forbidden_patterns)
        assert events[1].payload["violation_type"] == "forbidden_patterns"
        assert events[1].payload["turn_number"] == 5
        assert events[1].payload["details"]["pattern_matched"] == "DROP TABLE"

        # Verify third event (directory_sandbox)
        assert events[2].payload["violation_type"] == "directory_sandbox"
        assert events[2].payload["turn_number"] == 7
        assert events[2].payload["details"]["attempted_path"] == "/etc/shadow"

        # Verify aggregation in run metadata
        session.refresh(sample_run)
        agg = sample_run.acceptance_results["violation_aggregation"]

        assert agg["total_count"] == 3
        assert agg["by_type"]["allowed_tools"] == 1
        assert agg["by_type"]["forbidden_patterns"] == 1
        assert agg["by_type"]["directory_sandbox"] == 1
        assert agg["last_turn"] == 7

    def test_violations_queryable_by_event_type(self, session, sample_run):
        """Test that violation events are queryable by event_type."""
        # Record a violation
        record_allowed_tools_violation(
            session, sample_run.id, 1, "Bash", 5, ["Read"]
        )
        session.commit()

        # Query using event_type
        events = (
            session.query(AgentEvent)
            .filter(AgentEvent.event_type == "policy_violation")
            .all()
        )

        assert len(events) == 1
        assert events[0].event_type == "policy_violation"


# =============================================================================
# Feature Verification Steps
# =============================================================================

class TestFeature44VerificationSteps:
    """
    Explicit tests for each verification step in Feature #44.
    """

    def test_step1_define_policy_violation_event_type(self):
        """Step 1: Define policy_violation event type."""
        assert "policy_violation" in EVENT_TYPES
        # Verify it can be used in an AgentEvent
        event = AgentEvent(
            run_id="test",
            sequence=1,
            event_type="policy_violation",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.event_type == "policy_violation"

    def test_step2_record_allowed_tools_violation(self, session, sample_run):
        """Step 2: When tool blocked by allowed_tools, record event."""
        event = record_allowed_tools_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="forbidden_tool",
            turn_number=5,
            allowed_tools=["Read", "Write"],
            arguments={"key": "value"},
        )
        session.commit()

        assert event.event_type == "policy_violation"
        assert event.payload["violation_type"] == "allowed_tools"
        assert event.payload["tool"] == "forbidden_tool"
        assert event.tool_name == "forbidden_tool"

    def test_step3_record_forbidden_patterns_with_pattern(self, session, sample_run):
        """Step 3: When tool blocked by forbidden_patterns, record pattern matched."""
        event = record_forbidden_patterns_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="Bash",
            turn_number=10,
            pattern_matched="rm -rf /",
            arguments={"command": "rm -rf /home"},
        )
        session.commit()

        assert event.payload["violation_type"] == "forbidden_patterns"
        assert event.payload["details"]["pattern_matched"] == "rm -rf /"
        assert "rm -rf /" in event.payload["message"]

    def test_step4_record_sandbox_violation_with_path(self, session, sample_run):
        """Step 4: When file operation blocked by sandbox, record attempted path."""
        event = record_directory_sandbox_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="write_file",
            turn_number=15,
            attempted_path="/etc/passwd",
            reason="Path outside allowed directories",
            allowed_directories=["/home/project"],
            was_symlink=False,
        )
        session.commit()

        assert event.payload["violation_type"] == "directory_sandbox"
        assert event.payload["details"]["attempted_path"] == "/etc/passwd"
        assert event.payload["details"]["reason"] == "Path outside allowed directories"

    def test_step5_turn_number_in_event_context(self, session, sample_run):
        """Step 5: Include agent turn number in event for context."""
        event = record_allowed_tools_violation(
            db=session,
            run_id=sample_run.id,
            sequence=1,
            tool_name="Bash",
            turn_number=42,
            allowed_tools=["Read"],
        )
        session.commit()

        # Verify turn_number is in the payload
        assert "turn_number" in event.payload
        assert event.payload["turn_number"] == 42

    def test_step6_aggregate_violation_count_in_metadata(self, session, sample_run):
        """Step 6: Aggregate violation count in run metadata."""
        # Record multiple violations
        v1 = create_allowed_tools_violation("T1", 5, ["Read"])
        record_and_aggregate_violation(session, sample_run.id, 1, v1)

        v2 = create_forbidden_patterns_violation("T2", 10, "pattern")
        record_and_aggregate_violation(session, sample_run.id, 2, v2)

        v3 = create_allowed_tools_violation("T3", 15, ["Read"])
        record_and_aggregate_violation(session, sample_run.id, 3, v3)

        session.commit()

        # Verify aggregation in run metadata
        session.refresh(sample_run)
        assert "violation_aggregation" in sample_run.acceptance_results

        agg = sample_run.acceptance_results["violation_aggregation"]
        assert agg["total_count"] == 3
        assert agg["by_type"]["allowed_tools"] == 2
        assert agg["by_type"]["forbidden_patterns"] == 1
        assert agg["by_tool"] == {"T1": 1, "T2": 1, "T3": 1}
        assert agg["last_turn"] == 15
