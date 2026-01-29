"""
Test AgentSpec Pydantic Schemas
===============================

Verifies that the AgentSpec schemas correctly validate input and match
the database model structure.
"""

import pytest
from pydantic import ValidationError

from server.schemas import (
    AgentSpecCreate,
    AgentSpecUpdate,
    AgentSpecResponse,
    ToolPolicy,
    TASK_TYPES,
)


class TestToolPolicy:
    """Test ToolPolicy schema validation."""

    def test_valid_tool_policy(self):
        """ToolPolicy with policy_version and allowed_tools should be valid."""
        policy = ToolPolicy(
            policy_version="v1",
            allowed_tools=["read", "write"],
            forbidden_patterns=["rm -rf"],
            tool_hints={"read": "Use for reading files"}
        )
        assert policy.policy_version == "v1"
        assert policy.allowed_tools == ["read", "write"]

    def test_tool_policy_requires_allowed_tools(self):
        """ToolPolicy should require at least one allowed tool."""
        with pytest.raises(ValidationError) as exc_info:
            ToolPolicy(policy_version="v1", allowed_tools=[])
        assert "min_length" in str(exc_info.value) or "List should have" in str(exc_info.value)


class TestAgentSpecCreate:
    """Test AgentSpecCreate schema validation."""

    def test_valid_spec_create(self):
        """AgentSpecCreate with all required fields should be valid."""
        spec = AgentSpecCreate(
            name="test-spec",
            display_name="Test Spec",
            objective="This is a test objective for the spec",
            task_type="coding",
            tool_policy=ToolPolicy(
                policy_version="v1",
                allowed_tools=["read", "write"]
            )
        )
        assert spec.name == "test-spec"
        assert spec.display_name == "Test Spec"
        assert spec.task_type == "coding"

    def test_spec_create_with_optional_fields(self):
        """AgentSpecCreate should accept optional fields."""
        spec = AgentSpecCreate(
            name="test-spec",
            display_name="Test Spec",
            objective="This is a test objective for the spec",
            task_type="testing",
            tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["test"]),
            icon="🔧",
            context={"key": "value"},
            max_turns=100,
            timeout_seconds=3600,
            parent_spec_id="parent-123",
            source_feature_id=42,
            priority=100,
            tags=["test", "priority"]
        )
        assert spec.icon == "🔧"
        assert spec.max_turns == 100
        assert spec.timeout_seconds == 3600
        assert spec.priority == 100
        assert spec.tags == ["test", "priority"]

    def test_task_type_validation(self):
        """task_type should only accept allowed values."""
        # Valid task types
        for task_type in ["coding", "testing", "refactoring", "documentation", "audit", "custom"]:
            spec = AgentSpecCreate(
                name="test",
                display_name="Test",
                objective="Valid objective text here",
                task_type=task_type,
                tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"])
            )
            assert spec.task_type == task_type

        # Invalid task type
        with pytest.raises(ValidationError) as exc_info:
            AgentSpecCreate(
                name="test",
                display_name="Test",
                objective="Valid objective text here",
                task_type="invalid_type",
                tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"])
            )
        assert "task_type" in str(exc_info.value).lower() or "Input should be" in str(exc_info.value)

    def test_max_turns_range_validation(self):
        """max_turns should be in range 1-500."""
        # Valid range
        spec = AgentSpecCreate(
            name="test",
            display_name="Test",
            objective="Valid objective text here",
            task_type="coding",
            tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
            max_turns=1
        )
        assert spec.max_turns == 1

        spec = AgentSpecCreate(
            name="test",
            display_name="Test",
            objective="Valid objective text here",
            task_type="coding",
            tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
            max_turns=500
        )
        assert spec.max_turns == 500

        # Below range
        with pytest.raises(ValidationError) as exc_info:
            AgentSpecCreate(
                name="test",
                display_name="Test",
                objective="Valid objective text here",
                task_type="coding",
                tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
                max_turns=0
            )
        assert "max_turns" in str(exc_info.value).lower() or "greater than" in str(exc_info.value).lower()

        # Above range
        with pytest.raises(ValidationError) as exc_info:
            AgentSpecCreate(
                name="test",
                display_name="Test",
                objective="Valid objective text here",
                task_type="coding",
                tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
                max_turns=501
            )
        assert "max_turns" in str(exc_info.value).lower() or "less than" in str(exc_info.value).lower()

    def test_timeout_seconds_range_validation(self):
        """timeout_seconds should be in range 60-7200."""
        # Valid range
        spec = AgentSpecCreate(
            name="test",
            display_name="Test",
            objective="Valid objective text here",
            task_type="coding",
            tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
            timeout_seconds=60
        )
        assert spec.timeout_seconds == 60

        spec = AgentSpecCreate(
            name="test",
            display_name="Test",
            objective="Valid objective text here",
            task_type="coding",
            tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
            timeout_seconds=7200
        )
        assert spec.timeout_seconds == 7200

        # Below range
        with pytest.raises(ValidationError) as exc_info:
            AgentSpecCreate(
                name="test",
                display_name="Test",
                objective="Valid objective text here",
                task_type="coding",
                tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
                timeout_seconds=59
            )
        assert "timeout" in str(exc_info.value).lower() or "greater than" in str(exc_info.value).lower()

        # Above range
        with pytest.raises(ValidationError) as exc_info:
            AgentSpecCreate(
                name="test",
                display_name="Test",
                objective="Valid objective text here",
                task_type="coding",
                tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["x"]),
                timeout_seconds=7201
            )
        assert "timeout" in str(exc_info.value).lower() or "less than" in str(exc_info.value).lower()


class TestAgentSpecUpdate:
    """Test AgentSpecUpdate schema validation."""

    def test_all_fields_optional(self):
        """AgentSpecUpdate should accept empty input (all fields optional)."""
        update = AgentSpecUpdate()
        assert update.name is None
        assert update.display_name is None
        assert update.objective is None

    def test_partial_update(self):
        """AgentSpecUpdate should accept partial updates."""
        update = AgentSpecUpdate(
            display_name="Updated Name",
            max_turns=100
        )
        assert update.display_name == "Updated Name"
        assert update.max_turns == 100
        assert update.name is None
        assert update.objective is None

    def test_update_with_all_fields(self):
        """AgentSpecUpdate should accept all fields."""
        update = AgentSpecUpdate(
            name="updated-spec",
            display_name="Updated Spec",
            icon="🔄",
            objective="Updated objective text here",
            task_type="testing",
            context={"updated": True},
            tool_policy=ToolPolicy(policy_version="v1", allowed_tools=["test"]),
            max_turns=200,
            timeout_seconds=3600,
            parent_spec_id="new-parent",
            source_feature_id=99,
            priority=50,
            tags=["updated"]
        )
        assert update.name == "updated-spec"
        assert update.display_name == "Updated Spec"
        assert update.max_turns == 200

    def test_update_validates_max_turns(self):
        """AgentSpecUpdate should still validate max_turns range."""
        with pytest.raises(ValidationError):
            AgentSpecUpdate(max_turns=0)

        with pytest.raises(ValidationError):
            AgentSpecUpdate(max_turns=501)

    def test_update_validates_timeout_seconds(self):
        """AgentSpecUpdate should still validate timeout_seconds range."""
        with pytest.raises(ValidationError):
            AgentSpecUpdate(timeout_seconds=59)

        with pytest.raises(ValidationError):
            AgentSpecUpdate(timeout_seconds=7201)


class TestAgentSpecResponse:
    """Test AgentSpecResponse schema."""

    def test_response_has_all_fields(self):
        """AgentSpecResponse should have all required fields."""
        from datetime import datetime

        response = AgentSpecResponse(
            id="uuid-123",
            name="test-spec",
            display_name="Test Spec",
            icon="🔧",
            spec_version="v1",
            objective="Test objective",
            task_type="coding",
            context={"key": "value"},
            tool_policy={"policy_version": "v1", "allowed_tools": ["x"]},
            max_turns=50,
            timeout_seconds=1800,
            parent_spec_id=None,
            source_feature_id=42,
            created_at=datetime.now(),
            priority=500,
            tags=["test"]
        )
        assert response.id == "uuid-123"
        assert response.name == "test-spec"
        assert response.spec_version == "v1"
        assert response.priority == 500


class TestAgentRunResponse:
    """Test AgentRunResponse schema validation."""

    def test_valid_agent_run_response(self):
        """AgentRunResponse with valid data should be accepted."""
        from datetime import datetime, timedelta
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()
        later = now + timedelta(seconds=120)

        response = AgentRunResponse(
            id="run-uuid-123",
            agent_spec_id="spec-uuid-456",
            status="completed",
            started_at=now,
            completed_at=later,
            turns_used=25,
            tokens_in=1000,
            tokens_out=500,
            final_verdict="passed",
            acceptance_results=[{"validator_index": 0, "passed": True}],
            error=None,
            retry_count=0,
            created_at=now,
        )
        assert response.id == "run-uuid-123"
        assert response.status == "completed"
        assert response.final_verdict == "passed"

    def test_status_validation_valid(self):
        """status should accept all valid values."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()

        for status in ["pending", "running", "paused", "completed", "failed", "timeout"]:
            response = AgentRunResponse(
                id="run-uuid",
                agent_spec_id="spec-uuid",
                status=status,
                started_at=None,
                completed_at=None,
                turns_used=0,
                tokens_in=0,
                tokens_out=0,
                final_verdict=None,
                acceptance_results=None,
                error=None,
                retry_count=0,
                created_at=now,
            )
            assert response.status == status

    def test_status_validation_invalid(self):
        """status should reject invalid values."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()

        with pytest.raises(ValidationError) as exc_info:
            AgentRunResponse(
                id="run-uuid",
                agent_spec_id="spec-uuid",
                status="invalid_status",
                started_at=None,
                completed_at=None,
                turns_used=0,
                tokens_in=0,
                tokens_out=0,
                final_verdict=None,
                acceptance_results=None,
                error=None,
                retry_count=0,
                created_at=now,
            )
        assert "status" in str(exc_info.value).lower() or "invalid_status" in str(exc_info.value)

    def test_final_verdict_validation_valid(self):
        """final_verdict should accept valid values and None."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()

        # Test None (allowed)
        response = AgentRunResponse(
            id="run-uuid",
            agent_spec_id="spec-uuid",
            status="running",
            started_at=None,
            completed_at=None,
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            final_verdict=None,
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=now,
        )
        assert response.final_verdict is None

        # Test valid values
        for verdict in ["passed", "failed", "error"]:
            response = AgentRunResponse(
                id="run-uuid",
                agent_spec_id="spec-uuid",
                status="completed",
                started_at=None,
                completed_at=None,
                turns_used=0,
                tokens_in=0,
                tokens_out=0,
                final_verdict=verdict,
                acceptance_results=None,
                error=None,
                retry_count=0,
                created_at=now,
            )
            assert response.final_verdict == verdict

    def test_final_verdict_validation_invalid(self):
        """final_verdict should reject invalid values."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()

        with pytest.raises(ValidationError) as exc_info:
            AgentRunResponse(
                id="run-uuid",
                agent_spec_id="spec-uuid",
                status="completed",
                started_at=None,
                completed_at=None,
                turns_used=0,
                tokens_in=0,
                tokens_out=0,
                final_verdict="invalid_verdict",
                acceptance_results=None,
                error=None,
                retry_count=0,
                created_at=now,
            )
        assert "final_verdict" in str(exc_info.value).lower() or "invalid_verdict" in str(exc_info.value)

    def test_duration_seconds_computed_when_both_timestamps_present(self):
        """duration_seconds should be computed when both timestamps are present."""
        from datetime import datetime, timedelta
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()
        later = now + timedelta(seconds=120)

        response = AgentRunResponse(
            id="run-uuid",
            agent_spec_id="spec-uuid",
            status="completed",
            started_at=now,
            completed_at=later,
            turns_used=10,
            tokens_in=500,
            tokens_out=250,
            final_verdict="passed",
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=now,
        )
        assert response.duration_seconds is not None
        assert abs(response.duration_seconds - 120.0) < 0.001

    def test_duration_seconds_none_when_started_at_missing(self):
        """duration_seconds should be None when started_at is missing."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()

        response = AgentRunResponse(
            id="run-uuid",
            agent_spec_id="spec-uuid",
            status="pending",
            started_at=None,
            completed_at=None,
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            final_verdict=None,
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=now,
        )
        assert response.duration_seconds is None

    def test_duration_seconds_none_when_completed_at_missing(self):
        """duration_seconds should be None when completed_at is missing (run still in progress)."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        now = datetime.now()

        response = AgentRunResponse(
            id="run-uuid",
            agent_spec_id="spec-uuid",
            status="running",
            started_at=now,
            completed_at=None,
            turns_used=5,
            tokens_in=250,
            tokens_out=100,
            final_verdict=None,
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=now,
        )
        assert response.duration_seconds is None

    def test_duration_seconds_from_iso_strings(self):
        """duration_seconds should compute correctly from ISO string timestamps."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse

        # Test with ISO format strings
        started_str = "2024-01-27T10:00:00"
        completed_str = "2024-01-27T10:05:00"  # 5 minutes = 300 seconds

        response = AgentRunResponse(
            id="run-uuid",
            agent_spec_id="spec-uuid",
            status="completed",
            started_at=started_str,
            completed_at=completed_str,
            turns_used=10,
            tokens_in=500,
            tokens_out=250,
            final_verdict="passed",
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=datetime.now(),
        )
        assert response.duration_seconds is not None
        assert abs(response.duration_seconds - 300.0) < 0.001


class TestAgentRunListResponse:
    """Test AgentRunListResponse schema."""

    def test_list_response_structure(self):
        """AgentRunListResponse should have required fields."""
        from datetime import datetime
        from server.schemas.agentspec import AgentRunResponse, AgentRunListResponse

        now = datetime.now()
        run = AgentRunResponse(
            id="run-uuid",
            agent_spec_id="spec-uuid",
            status="completed",
            started_at=now,
            completed_at=now,
            turns_used=10,
            tokens_in=500,
            tokens_out=250,
            final_verdict="passed",
            acceptance_results=None,
            error=None,
            retry_count=0,
            created_at=now,
        )

        list_response = AgentRunListResponse(
            runs=[run],
            total=1,
            offset=0,
            limit=10
        )

        assert len(list_response.runs) == 1
        assert list_response.total == 1
        assert list_response.offset == 0
        assert list_response.limit == 10

    def test_empty_list_response(self):
        """AgentRunListResponse should accept empty runs list."""
        from server.schemas.agentspec import AgentRunListResponse

        list_response = AgentRunListResponse(
            runs=[],
            total=0,
            offset=0,
            limit=10
        )

        assert len(list_response.runs) == 0
        assert list_response.total == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
