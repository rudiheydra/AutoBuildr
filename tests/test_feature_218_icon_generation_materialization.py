"""
Tests for Feature #218: Icon generation triggered during agent materialization
================================================================================

When an agent is materialized, icon generation is triggered automatically.

Test Strategy:
1. Materializer calls IconProvider.generate_icon()
2. Icon generated based on agent name and role
3. Icon stored alongside agent metadata
4. icon_generated audit event recorded
5. Failure does not block materialization
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Core imports
from api.agentspec_models import AgentSpec, EVENT_TYPES, generate_uuid
from api.agent_materializer import (
    AgentMaterializer,
    IconGenerationInfo,
    MaterializationResult,
)

# Path to patch - the generate_icon function is imported inside _generate_icon_for_spec
# from api.icon_provider, so we patch it there
GENERATE_ICON_PATCH = "api.icon_provider.generate_icon"


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_spec():
    """Create a sample AgentSpec for testing."""
    spec = Mock(spec=AgentSpec)
    spec.id = generate_uuid()
    spec.name = "test-agent-impl"
    spec.display_name = "Test Agent Implementation"
    spec.task_type = "coding"
    spec.objective = "Implement a test feature"
    spec.spec_version = "v1"
    spec.max_turns = 50
    spec.timeout_seconds = 1800
    spec.context = {"model": "sonnet"}
    spec.tool_policy = {
        "policy_version": "v1",
        "allowed_tools": ["Read", "Write", "Edit"],
        "forbidden_patterns": [],
        "tool_hints": {},
    }
    spec.acceptance_spec = None
    return spec


@pytest.fixture
def materializer(temp_project_dir):
    """Create an AgentMaterializer instance."""
    return AgentMaterializer(temp_project_dir)


# =============================================================================
# Step 1: Materializer calls IconProvider.generate_icon()
# =============================================================================

class TestStep1MaterializerCallsIconProvider:
    """Test that the materializer calls IconProvider.generate_icon() during materialization."""

    def test_materialize_calls_generate_icon(self, materializer, sample_spec):
        """Test that materialize() calls generate_icon()."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)

            assert result.success is True
            mock_generate.assert_called_once()

    def test_materialize_calls_generate_icon_with_correct_args(
        self, materializer, sample_spec
    ):
        """Test that generate_icon is called with agent_name and role."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            mock_generate.assert_called_with(
                agent_name="test-agent-impl",
                role="coder",  # Derived from task_type="coding"
                tone="professional",
            )

    def test_generate_icon_called_after_file_write(self, materializer, sample_spec):
        """Test that icon generation happens after successful file write."""
        call_order = []

        original_write = Path.write_text

        def track_write(self, content, *args, **kwargs):
            call_order.append("file_write")
            return original_write(self, content, *args, **kwargs)

        def track_generate(*args, **kwargs):
            call_order.append("icon_generate")
            return Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

        with patch.object(Path, "write_text", track_write):
            with patch(GENERATE_ICON_PATCH, track_generate):
                result = materializer.materialize(sample_spec)

        assert result.success is True
        assert call_order == ["file_write", "icon_generate"]


# =============================================================================
# Step 2: Icon generated based on agent name and role
# =============================================================================

class TestStep2IconGeneratedBasedOnNameAndRole:
    """Test that icon is generated based on agent name and derived role."""

    def test_coding_task_type_maps_to_coder_role(self, materializer, sample_spec):
        """Test that task_type='coding' maps to role='coder'."""
        sample_spec.task_type = "coding"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["role"] == "coder"

    def test_testing_task_type_maps_to_tester_role(self, materializer, sample_spec):
        """Test that task_type='testing' maps to role='tester'."""
        sample_spec.task_type = "testing"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="test",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["role"] == "tester"

    def test_audit_task_type_maps_to_auditor_role(self, materializer, sample_spec):
        """Test that task_type='audit' maps to role='auditor'."""
        sample_spec.task_type = "audit"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="shield",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["role"] == "auditor"

    def test_documentation_task_type_maps_to_documenter_role(
        self, materializer, sample_spec
    ):
        """Test that task_type='documentation' maps to role='documenter'."""
        sample_spec.task_type = "documentation"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="file-text",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["role"] == "documenter"

    def test_refactoring_task_type_maps_to_refactorer_role(
        self, materializer, sample_spec
    ):
        """Test that task_type='refactoring' maps to role='refactorer'."""
        sample_spec.task_type = "refactoring"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="wrench",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["role"] == "refactorer"

    def test_custom_task_type_defaults_to_coder_role(self, materializer, sample_spec):
        """Test that task_type='custom' defaults to role='coder'."""
        sample_spec.task_type = "custom"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="gear",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["role"] == "coder"

    def test_agent_name_passed_correctly(self, materializer, sample_spec):
        """Test that the agent name is passed correctly to generate_icon."""
        sample_spec.name = "my-custom-agent"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args
            assert kwargs["agent_name"] == "my-custom-agent"


# =============================================================================
# Step 3: Icon stored alongside agent metadata
# =============================================================================

class TestStep3IconStoredAlongsideMetadata:
    """Test that icon is stored alongside agent metadata (in MaterializationResult)."""

    def test_icon_info_included_in_result(self, materializer, sample_spec):
        """Test that MaterializationResult includes icon_info."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)

            assert result.icon_info is not None
            assert isinstance(result.icon_info, IconGenerationInfo)

    def test_icon_info_contains_icon_data(self, materializer, sample_spec):
        """Test that icon_info contains the generated icon data."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="test-icon-data",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)

            assert result.icon_info.icon_data == "test-icon-data"
            assert result.icon_info.success is True

    def test_icon_info_contains_format(self, materializer, sample_spec):
        """Test that icon_info contains the icon format."""
        from api.icon_provider import IconFormat

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=IconFormat.SVG,  # Use actual enum
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)

            assert result.icon_info.icon_format == "svg"

    def test_icon_info_contains_provider_name(self, materializer, sample_spec):
        """Test that icon_info contains the provider name."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="dalle",
            )

            result = materializer.materialize(sample_spec)

            assert result.icon_info.provider_name == "dalle"

    def test_icon_info_to_dict_serialization(self, materializer, sample_spec):
        """Test that IconGenerationInfo can be serialized to dict."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)
            icon_dict = result.icon_info.to_dict()

            assert "success" in icon_dict
            assert "icon_data" in icon_dict
            assert "icon_format" in icon_dict
            assert "provider_name" in icon_dict
            assert icon_dict["success"] is True

    def test_result_to_dict_includes_icon_info(self, materializer, sample_spec):
        """Test that MaterializationResult.to_dict() includes icon_info."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)
            result_dict = result.to_dict()

            assert "icon_info" in result_dict
            assert result_dict["icon_info"] is not None


# =============================================================================
# Step 4: icon_generated audit event recorded
# =============================================================================

class TestStep4IconGeneratedAuditEvent:
    """Test that icon_generated audit event is recorded."""

    def test_icon_generated_in_event_types(self):
        """Test that icon_generated is a registered event type."""
        assert "icon_generated" in EVENT_TYPES

    def test_materialize_with_audit_records_icon_event(
        self, materializer, sample_spec, temp_project_dir
    ):
        """Test that materialize_with_audit records icon_generated event."""
        from unittest.mock import MagicMock
        from api.icon_provider import IconFormat

        mock_session = MagicMock()
        run_id = generate_uuid()

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=IconFormat.ICON_ID,
                provider_name="default",
            )

            mock_recorder_instance = MagicMock()
            mock_recorder_instance.record_agent_materialized.return_value = 1
            mock_recorder_instance.record_icon_generated.return_value = 2

            with patch("api.event_recorder.get_event_recorder") as mock_get_recorder:
                mock_get_recorder.return_value = mock_recorder_instance

                result = materializer.materialize_with_audit(
                    sample_spec, mock_session, run_id
                )

                # Verify icon_generated event was recorded
                mock_recorder_instance.record_icon_generated.assert_called_once()

    def test_icon_event_includes_correct_payload(
        self, materializer, sample_spec, temp_project_dir
    ):
        """Test that icon_generated event includes correct payload fields."""
        from unittest.mock import MagicMock
        from api.icon_provider import IconFormat

        mock_session = MagicMock()
        run_id = generate_uuid()

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="test-icon",
                format=IconFormat.ICON_ID,
                provider_name="test-provider",
            )

            mock_recorder_instance = MagicMock()
            mock_recorder_instance.record_agent_materialized.return_value = 1
            mock_recorder_instance.record_icon_generated.return_value = 2

            with patch("api.event_recorder.get_event_recorder") as mock_get_recorder:
                mock_get_recorder.return_value = mock_recorder_instance

                materializer.materialize_with_audit(
                    sample_spec, mock_session, run_id
                )

                call_args = mock_recorder_instance.record_icon_generated.call_args
                assert call_args is not None
                _, kwargs = call_args

                assert kwargs["agent_name"] == sample_spec.name
                assert kwargs["spec_id"] == sample_spec.id
                assert kwargs["success"] is True
                assert kwargs["icon_format"] == "icon_id"

    def test_icon_info_audit_recorded_flag_set(
        self, materializer, sample_spec, temp_project_dir
    ):
        """Test that icon_info.audit_recorded is set after recording."""
        from unittest.mock import MagicMock
        from api.icon_provider import IconFormat

        mock_session = MagicMock()
        run_id = generate_uuid()

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=IconFormat.ICON_ID,
                provider_name="default",
            )

            mock_recorder_instance = MagicMock()
            mock_recorder_instance.record_agent_materialized.return_value = 1
            mock_recorder_instance.record_icon_generated.return_value = 2

            with patch("api.event_recorder.get_event_recorder") as mock_get_recorder:
                mock_get_recorder.return_value = mock_recorder_instance

                result = materializer.materialize_with_audit(
                    sample_spec, mock_session, run_id
                )

                # Verify audit_recorded flag is set
                assert result.icon_info.audit_recorded is True
                assert result.icon_info.event_id == 2


# =============================================================================
# Step 5: Failure does not block materialization
# =============================================================================

class TestStep5FailureDoesNotBlockMaterialization:
    """Test that icon generation failure does not block materialization."""

    def test_materialization_succeeds_when_icon_fails(self, materializer, sample_spec):
        """Test that materialization succeeds even when icon generation fails."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=False,
                icon_data=None,
                format=Mock(value="icon_id"),
                provider_name="default",
                error="Icon generation failed",
            )

            result = materializer.materialize(sample_spec)

            assert result.success is True
            assert result.file_path is not None
            assert result.file_path.exists()

    def test_materialization_succeeds_when_icon_raises_exception(
        self, materializer, sample_spec
    ):
        """Test that materialization succeeds when icon generation raises exception."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.side_effect = Exception("Icon provider crashed")

            result = materializer.materialize(sample_spec)

            assert result.success is True
            assert result.file_path is not None

    def test_icon_info_contains_error_on_failure(self, materializer, sample_spec):
        """Test that icon_info contains error message on failure."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=False,
                icon_data=None,
                format=Mock(value="icon_id"),
                provider_name="default",
                error="API rate limit exceeded",
            )

            result = materializer.materialize(sample_spec)

            assert result.icon_info is not None
            assert result.icon_info.success is False
            assert "rate limit" in result.icon_info.error.lower()

    def test_icon_info_contains_error_on_exception(self, materializer, sample_spec):
        """Test that icon_info contains error when exception is raised."""
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.side_effect = RuntimeError("Connection timeout")

            result = materializer.materialize(sample_spec)

            assert result.icon_info is not None
            assert result.icon_info.success is False
            assert "error" in result.icon_info.error.lower()

    def test_materialization_file_created_before_icon_failure(
        self, materializer, sample_spec
    ):
        """Test that agent file is created before icon generation is attempted."""
        file_exists_before_icon = []

        def check_and_fail(*args, **kwargs):
            file_exists_before_icon.append(
                (materializer.output_path / f"{sample_spec.name}.md").exists()
            )
            raise Exception("Icon generation failed")

        with patch(GENERATE_ICON_PATCH, check_and_fail):
            result = materializer.materialize(sample_spec)

        assert result.success is True
        assert file_exists_before_icon == [True]  # File existed before icon generation


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for icon generation during materialization."""

    def test_full_materialization_flow(self, temp_project_dir, sample_spec):
        """Test complete materialization flow with real icon generation."""
        materializer = AgentMaterializer(temp_project_dir)

        # Don't mock - use real IconProvider (DefaultIconProvider)
        result = materializer.materialize(sample_spec)

        # Verify materialization succeeded
        assert result.success is True
        assert result.file_path is not None
        assert result.file_path.exists()

        # Verify icon was generated
        assert result.icon_info is not None
        # May or may not succeed depending on provider availability
        if result.icon_info.success:
            assert result.icon_info.icon_data is not None

    def test_materialization_result_serializable(self, materializer, sample_spec):
        """Test that full MaterializationResult can be JSON serialized."""
        import json

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)
            result_dict = result.to_dict()

            # Should be JSON serializable
            json_str = json.dumps(result_dict)
            assert json_str is not None

            # Should round-trip
            parsed = json.loads(json_str)
            assert parsed["success"] is True
            assert parsed["icon_info"]["success"] is True


# =============================================================================
# IconGenerationInfo Data Class Tests
# =============================================================================

class TestIconGenerationInfo:
    """Test IconGenerationInfo dataclass."""

    def test_default_values(self):
        """Test default values for IconGenerationInfo."""
        info = IconGenerationInfo()

        assert info.success is False
        assert info.icon_data is None
        assert info.icon_format is None
        assert info.provider_name is None
        assert info.generation_time_ms == 0
        assert info.event_id is None
        assert info.audit_recorded is False
        assert info.error is None

    def test_successful_info(self):
        """Test IconGenerationInfo with successful generation."""
        info = IconGenerationInfo(
            success=True,
            icon_data="code-icon",
            icon_format="icon_id",
            provider_name="default",
            generation_time_ms=42,
        )

        assert info.success is True
        assert info.icon_data == "code-icon"
        assert info.icon_format == "icon_id"
        assert info.provider_name == "default"
        assert info.generation_time_ms == 42

    def test_failed_info(self):
        """Test IconGenerationInfo with failed generation."""
        info = IconGenerationInfo(
            success=False,
            error="API key not configured",
            generation_time_ms=100,
        )

        assert info.success is False
        assert info.error == "API key not configured"
        assert info.generation_time_ms == 100

    def test_to_dict(self):
        """Test IconGenerationInfo.to_dict() method."""
        info = IconGenerationInfo(
            success=True,
            icon_data="test-data",
            icon_format="svg",
            provider_name="dalle",
            generation_time_ms=500,
            event_id=42,
            audit_recorded=True,
        )

        d = info.to_dict()

        assert d["success"] is True
        assert d["icon_data"] == "test-data"
        assert d["icon_format"] == "svg"
        assert d["provider_name"] == "dalle"
        assert d["generation_time_ms"] == 500
        assert d["event_id"] == 42
        assert d["audit_recorded"] is True


# =============================================================================
# EventRecorder Tests
# =============================================================================

class TestEventRecorderIconGenerated:
    """Test EventRecorder.record_icon_generated() method."""

    def test_record_icon_generated_method_exists(self):
        """Test that record_icon_generated method exists on EventRecorder."""
        from api.event_recorder import EventRecorder

        assert hasattr(EventRecorder, "record_icon_generated")

    def test_record_icon_generated_creates_event(self):
        """Test that record_icon_generated creates an event record."""
        from api.event_recorder import EventRecorder
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        recorder = EventRecorder(mock_session)

        # Mock the record method to track calls
        with patch.object(recorder, "record", return_value=42) as mock_record:
            event_id = recorder.record_icon_generated(
                run_id="test-run-id",
                agent_name="test-agent",
                icon_data="code",
                icon_format="icon_id",
                spec_id="spec-123",
                provider_name="default",
                generation_time_ms=100,
                success=True,
            )

            assert event_id == 42
            mock_record.assert_called_once()
            call_args = mock_record.call_args
            assert call_args[0][0] == "test-run-id"
            assert call_args[0][1] == "icon_generated"

    def test_record_icon_generated_payload_contents(self):
        """Test that record_icon_generated includes correct payload fields."""
        from api.event_recorder import EventRecorder
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        recorder = EventRecorder(mock_session)

        with patch.object(recorder, "record", return_value=1) as mock_record:
            recorder.record_icon_generated(
                run_id="run-123",
                agent_name="my-agent",
                icon_data="shield",
                icon_format="icon_id",
                spec_id="spec-456",
                provider_name="dalle",
                generation_time_ms=250,
                success=True,
            )

            _, kwargs = mock_record.call_args
            payload = kwargs["payload"]

            assert payload["agent_name"] == "my-agent"
            assert payload["icon_format"] == "icon_id"
            assert payload["icon_data"] == "shield"
            assert payload["spec_id"] == "spec-456"
            assert payload["provider_name"] == "dalle"
            assert payload["generation_time_ms"] == 250
            assert payload["success"] is True

    def test_record_icon_generated_handles_failure(self):
        """Test that record_icon_generated handles failure case."""
        from api.event_recorder import EventRecorder
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        recorder = EventRecorder(mock_session)

        with patch.object(recorder, "record", return_value=1) as mock_record:
            recorder.record_icon_generated(
                run_id="run-123",
                agent_name="my-agent",
                icon_data=None,
                icon_format="unknown",
                success=False,
                error="API timeout",
            )

            _, kwargs = mock_record.call_args
            payload = kwargs["payload"]

            assert payload["success"] is False
            assert payload["error"] == "API timeout"
            assert "icon_data" not in payload  # None values excluded


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #218 components are exported from api package."""

    def test_icon_generation_info_exported(self):
        """Test that IconGenerationInfo is exported from api package."""
        from api import IconGenerationInfo

        assert IconGenerationInfo is not None

    def test_event_types_includes_icon_generated(self):
        """Test that EVENT_TYPES includes icon_generated."""
        from api.agentspec_models import EVENT_TYPES

        assert "icon_generated" in EVENT_TYPES


# =============================================================================
# Feature #218 Verification Steps (Acceptance Tests)
# =============================================================================

class TestFeature218VerificationSteps:
    """Comprehensive tests for each Feature #218 verification step."""

    def test_step1_materializer_calls_icon_provider(
        self, materializer, sample_spec
    ):
        """
        Step 1: Materializer calls IconProvider.generate_icon()

        Verify that the AgentMaterializer invokes the IconProvider
        during the materialization process.
        """
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            result = materializer.materialize(sample_spec)

            # PASS: generate_icon was called
            mock_generate.assert_called_once()
            assert result.success is True

    def test_step2_icon_based_on_name_and_role(
        self, materializer, sample_spec
    ):
        """
        Step 2: Icon generated based on agent name and role

        Verify that the icon generation uses the agent's name and
        a role derived from the task_type.
        """
        sample_spec.name = "auth-feature-impl"
        sample_spec.task_type = "coding"

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="code",
                format=Mock(value="icon_id"),
                provider_name="default",
            )

            materializer.materialize(sample_spec)

            _, kwargs = mock_generate.call_args

            # PASS: Correct agent name and role
            assert kwargs["agent_name"] == "auth-feature-impl"
            assert kwargs["role"] == "coder"

    def test_step3_icon_stored_alongside_metadata(
        self, materializer, sample_spec
    ):
        """
        Step 3: Icon stored alongside agent metadata

        Verify that the generated icon information is stored in
        the MaterializationResult alongside other agent metadata.
        """
        from api.icon_provider import IconFormat

        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.return_value = Mock(
                success=True,
                icon_data="custom-icon",
                format=IconFormat.SVG,  # Use actual enum
                provider_name="dalle",
            )

            result = materializer.materialize(sample_spec)

            # PASS: Icon info stored in result
            assert result.icon_info is not None
            assert result.icon_info.success is True
            assert result.icon_info.icon_data == "custom-icon"
            assert result.icon_info.icon_format == "svg"
            assert result.icon_info.provider_name == "dalle"

    def test_step4_icon_generated_audit_event(self):
        """
        Step 4: icon_generated audit event recorded

        Verify that when icon generation occurs, an 'icon_generated'
        audit event is recorded in the event log.
        """
        # Verify event type is registered
        assert "icon_generated" in EVENT_TYPES

        # Verify EventRecorder has the method
        from api.event_recorder import EventRecorder

        assert hasattr(EventRecorder, "record_icon_generated")

        # Verify the method can be called
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        recorder = EventRecorder(mock_session)

        with patch.object(recorder, "record", return_value=1) as mock_record:
            event_id = recorder.record_icon_generated(
                run_id="test-run",
                agent_name="test-agent",
                icon_data="code",
                icon_format="icon_id",
                success=True,
            )

            # PASS: Event recorded with correct type
            assert event_id == 1
            call_args = mock_record.call_args
            assert call_args[0][1] == "icon_generated"

    def test_step5_failure_does_not_block_materialization(
        self, materializer, sample_spec
    ):
        """
        Step 5: Failure does not block materialization

        Verify that if icon generation fails (returns error or throws
        exception), the agent file is still created successfully.
        """
        # Test with exception
        with patch(GENERATE_ICON_PATCH) as mock_generate:
            mock_generate.side_effect = Exception("Provider unavailable")

            result = materializer.materialize(sample_spec)

            # PASS: Materialization succeeded despite icon failure
            assert result.success is True
            assert result.file_path.exists()
            assert result.icon_info.success is False
            assert "error" in result.icon_info.error.lower()
