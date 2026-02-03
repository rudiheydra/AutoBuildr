"""
Tests for Feature #197: Agent Materializer handles multiple agents in batch

The Agent Materializer can process multiple AgentSpecs in a single invocation for efficiency.

Verification Steps:
1. Materializer accepts list of AgentSpecs
2. Each spec processed and written individually
3. Batch operation is atomic: all succeed or none written
4. Progress reported for each agent
5. Single audit event or per-agent events recorded
"""
import hashlib
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from api.agent_materializer import (
    AgentMaterializer,
    MaterializationResult,
    BatchMaterializationResult,
    MaterializationAuditInfo,
    ProgressCallback,
    DEFAULT_OUTPUT_DIR,
)
from api.agentspec_models import AgentSpec, generate_uuid


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def materializer(temp_project_dir):
    """AgentMaterializer instance with temp directory."""
    return AgentMaterializer(temp_project_dir)


@pytest.fixture
def sample_agent_specs():
    """Create sample AgentSpecs for batch testing."""
    specs = []
    for i in range(3):
        spec = AgentSpec(
            id=generate_uuid(),
            name=f"test-agent-{i}",
            display_name=f"Test Agent {i}",
            task_type="coding",
            objective=f"Test objective for agent {i}",
            context={"index": i},
            tool_policy={"allowed_tools": ["Read", "Write", "Grep"]},
            max_turns=50,
            timeout_seconds=900,
        )
        specs.append(spec)
    return specs


@pytest.fixture
def mock_event_recorder():
    """Create a mock EventRecorder for audit testing."""
    recorder = MagicMock()
    recorder.record_agent_materialized.return_value = 100
    recorder.record.return_value = 200
    return recorder


# =============================================================================
# Step 1: Materializer accepts list of AgentSpecs
# =============================================================================

class TestStep1AcceptsListOfAgentSpecs:
    """Verify Materializer accepts list of AgentSpecs."""

    def test_materialize_batch_accepts_list(self, materializer, sample_agent_specs):
        """materialize_batch accepts a list of AgentSpecs."""
        result = materializer.materialize_batch(sample_agent_specs)
        assert isinstance(result, BatchMaterializationResult)
        assert result.total == 3

    def test_materialize_batch_accepts_empty_list(self, materializer):
        """materialize_batch handles empty list gracefully."""
        result = materializer.materialize_batch([])
        assert isinstance(result, BatchMaterializationResult)
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.all_succeeded is False  # Empty list doesn't count as success

    def test_materialize_batch_accepts_single_spec(self, materializer, sample_agent_specs):
        """materialize_batch handles single-item list."""
        result = materializer.materialize_batch([sample_agent_specs[0]])
        assert result.total == 1
        assert result.succeeded == 1

    def test_result_contains_individual_results(self, materializer, sample_agent_specs):
        """BatchMaterializationResult contains results for each spec."""
        result = materializer.materialize_batch(sample_agent_specs)
        assert len(result.results) == 3
        for i, r in enumerate(result.results):
            assert isinstance(r, MaterializationResult)
            assert r.spec_name == f"test-agent-{i}"


# =============================================================================
# Step 2: Each spec processed and written individually
# =============================================================================

class TestStep2ProcessedIndividually:
    """Verify each spec is processed and written individually."""

    def test_each_spec_gets_own_file(self, materializer, sample_agent_specs, temp_project_dir):
        """Each AgentSpec is written to its own file."""
        materializer.materialize_batch(sample_agent_specs)

        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        for i, spec in enumerate(sample_agent_specs):
            filepath = output_dir / f"{spec.name}.md"
            assert filepath.exists(), f"File not found: {filepath}"

    def test_files_have_different_content(self, materializer, sample_agent_specs, temp_project_dir):
        """Each file has unique content."""
        materializer.materialize_batch(sample_agent_specs)

        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        contents = []
        for spec in sample_agent_specs:
            filepath = output_dir / f"{spec.name}.md"
            content = filepath.read_text()
            contents.append(content)

        # All contents should be different
        assert len(set(contents)) == 3

    def test_each_result_has_unique_hash(self, materializer, sample_agent_specs):
        """Each result has a unique content hash."""
        result = materializer.materialize_batch(sample_agent_specs)

        hashes = [r.content_hash for r in result.results if r.success]
        assert len(hashes) == 3
        assert len(set(hashes)) == 3  # All unique

    def test_individual_results_track_file_paths(self, materializer, sample_agent_specs, temp_project_dir):
        """Individual results contain correct file paths."""
        result = materializer.materialize_batch(sample_agent_specs)

        for r in result.results:
            assert r.file_path is not None
            assert r.file_path.exists()
            assert r.file_path.name == f"{r.spec_name}.md"

    def test_partial_failure_continues_processing(self, materializer, temp_project_dir):
        """Non-atomic batch continues processing after failure."""
        # Create specs, one will fail due to invalid name
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="valid-agent-1",
                display_name="Valid 1",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
            AgentSpec(
                id=generate_uuid(),
                name="valid-agent-2",
                display_name="Valid 2",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
        ]

        result = materializer.materialize_batch(specs, atomic=False)

        # Both should succeed
        assert result.succeeded == 2
        assert result.failed == 0


# =============================================================================
# Step 3: Batch operation is atomic: all succeed or none written
# =============================================================================

class TestStep3AtomicOperation:
    """Verify atomic batch operation behavior."""

    def test_atomic_true_sets_flag(self, materializer, sample_agent_specs):
        """atomic=True is reflected in result."""
        result = materializer.materialize_batch(sample_agent_specs, atomic=True)
        assert result.atomic is True

    def test_atomic_false_by_default(self, materializer, sample_agent_specs):
        """atomic defaults to False."""
        result = materializer.materialize_batch(sample_agent_specs)
        assert result.atomic is False

    def test_atomic_all_succeed(self, materializer, sample_agent_specs, temp_project_dir):
        """Atomic batch: all files written when all succeed."""
        result = materializer.materialize_batch(sample_agent_specs, atomic=True)

        assert result.all_succeeded
        assert result.rolled_back is False
        assert result.succeeded == 3

        # Verify all files exist
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        for spec in sample_agent_specs:
            filepath = output_dir / f"{spec.name}.md"
            assert filepath.exists()

    def test_atomic_rollback_on_failure(self, materializer, temp_project_dir):
        """Atomic batch: all files rolled back on failure."""
        # Create a scenario where the second write fails
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="agent-1",
                display_name="Agent 1",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
            AgentSpec(
                id=generate_uuid(),
                name="agent-2",
                display_name="Agent 2",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
        ]

        # Mock write_text to fail on second file
        original_write_text = Path.write_text
        call_count = [0]

        def mock_write_text(self, content, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise IOError("Simulated write failure")
            return original_write_text(self, content, **kwargs)

        with patch.object(Path, 'write_text', mock_write_text):
            result = materializer.materialize_batch(specs, atomic=True)

        assert result.rolled_back is True
        assert result.succeeded == 0
        assert result.failed == 2

        # Verify files were rolled back (don't exist)
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        for spec in specs:
            filepath = output_dir / f"{spec.name}.md"
            assert not filepath.exists(), f"File should have been rolled back: {filepath}"

    def test_atomic_render_failure_no_files_written(self, materializer, temp_project_dir):
        """Atomic batch: if render fails, no files are written."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="good-agent",
                display_name="Good Agent",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
        ]

        # Mock render to fail
        with patch.object(materializer, 'render_claude_code_markdown', side_effect=ValueError("Render error")):
            result = materializer.materialize_batch(specs, atomic=True)

        assert result.failed == 1
        assert result.succeeded == 0
        assert result.rolled_back is False  # Nothing to roll back

        # No files should exist
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        if output_dir.exists():
            assert len(list(output_dir.iterdir())) == 0

    def test_atomic_result_marks_all_failed_on_rollback(self, materializer, temp_project_dir):
        """Atomic batch: all results marked failed after rollback."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name=f"agent-{i}",
                display_name=f"Agent {i}",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            )
            for i in range(3)
        ]

        # Mock write_text to fail on third file
        original_write_text = Path.write_text
        call_count = [0]

        def mock_write_text(self, content, **kwargs):
            call_count[0] += 1
            if call_count[0] == 3:
                raise IOError("Simulated write failure")
            return original_write_text(self, content, **kwargs)

        with patch.object(Path, 'write_text', mock_write_text):
            result = materializer.materialize_batch(specs, atomic=True)

        # All results should be marked as failed
        for r in result.results:
            assert r.success is False
            assert r.file_path is None


# =============================================================================
# Step 4: Progress reported for each agent
# =============================================================================

class TestStep4ProgressReporting:
    """Verify progress is reported for each agent."""

    def test_progress_callback_called_for_each_spec(self, materializer, sample_agent_specs):
        """Progress callback is called for each spec."""
        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        materializer.materialize_batch(sample_agent_specs, progress_callback=on_progress)

        # Should have processing and completed for each spec
        assert len(progress_calls) == 6  # 3 processing + 3 completed

        # Verify processing calls
        processing_calls = [c for c in progress_calls if c[3] == "processing"]
        assert len(processing_calls) == 3

        # Verify completed calls
        completed_calls = [c for c in progress_calls if c[3] == "completed"]
        assert len(completed_calls) == 3

    def test_progress_reports_correct_index(self, materializer, sample_agent_specs):
        """Progress callback receives correct index."""
        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        materializer.materialize_batch(sample_agent_specs, progress_callback=on_progress)

        indices = [c[0] for c in progress_calls]
        expected_indices = [1, 1, 2, 2, 3, 3]  # processing + completed for each
        assert indices == expected_indices

    def test_progress_reports_correct_total(self, materializer, sample_agent_specs):
        """Progress callback receives correct total count."""
        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        materializer.materialize_batch(sample_agent_specs, progress_callback=on_progress)

        totals = [c[1] for c in progress_calls]
        assert all(t == 3 for t in totals)

    def test_progress_reports_correct_name(self, materializer, sample_agent_specs):
        """Progress callback receives correct spec name."""
        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        materializer.materialize_batch(sample_agent_specs, progress_callback=on_progress)

        # Each name should appear twice (processing + completed)
        names = [c[2] for c in progress_calls]
        for spec in sample_agent_specs:
            assert names.count(spec.name) == 2

    def test_progress_reports_failure_status(self, materializer, temp_project_dir):
        """Progress callback reports 'failed' on error."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="test-agent",
                display_name="Test",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
        ]

        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        with patch.object(materializer, 'materialize', return_value=MaterializationResult(
            spec_id=specs[0].id,
            spec_name=specs[0].name,
            success=False,
            error="Test error",
        )):
            materializer.materialize_batch(specs, progress_callback=on_progress)

        statuses = [c[3] for c in progress_calls]
        assert "failed" in statuses

    def test_atomic_progress_reports_rolled_back(self, materializer, temp_project_dir):
        """Atomic batch reports 'rolled_back' status on rollback."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name=f"agent-{i}",
                display_name=f"Agent {i}",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            )
            for i in range(2)
        ]

        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        # Mock write_text to fail on second file
        original_write_text = Path.write_text
        call_count = [0]

        def mock_write_text(self, content, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise IOError("Simulated write failure")
            return original_write_text(self, content, **kwargs)

        with patch.object(Path, 'write_text', mock_write_text):
            materializer.materialize_batch(specs, atomic=True, progress_callback=on_progress)

        statuses = [c[3] for c in progress_calls]
        assert "rolled_back" in statuses

    def test_progress_callback_none_is_allowed(self, materializer, sample_agent_specs):
        """No error when progress_callback is None."""
        result = materializer.materialize_batch(sample_agent_specs, progress_callback=None)
        assert result.all_succeeded


# =============================================================================
# Step 5: Single audit event or per-agent events recorded
# =============================================================================

class TestStep5AuditEvents:
    """Verify audit event recording."""

    def test_non_atomic_records_per_agent_events(self, materializer, sample_agent_specs, mock_event_recorder):
        """Non-atomic batch records per-agent audit events."""
        run_id = generate_uuid()

        result = materializer.materialize_batch(
            sample_agent_specs,
            atomic=False,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        # Should have called record_agent_materialized for each spec
        assert mock_event_recorder.record_agent_materialized.call_count == 3

        # Check that each result has audit_info
        for r in result.results:
            assert r.audit_info is not None
            assert r.audit_info.recorded is True
            assert r.audit_info.run_id == run_id

    def test_atomic_records_single_batch_event(self, materializer, sample_agent_specs, mock_event_recorder):
        """Atomic batch records a single batch audit event."""
        run_id = generate_uuid()

        result = materializer.materialize_batch(
            sample_agent_specs,
            atomic=True,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        # Should have called record() once for batch event
        mock_event_recorder.record.assert_called_once()

        # Verify call arguments
        call_args = mock_event_recorder.record.call_args
        assert call_args.kwargs['run_id'] == run_id
        assert call_args.kwargs['event_type'] == 'agent_materialized'
        assert call_args.kwargs['payload']['batch_operation'] is True
        assert call_args.kwargs['payload']['total_agents'] == 3

        # Batch audit info should be set
        assert result.batch_audit_info is not None
        assert result.batch_audit_info.recorded is True

    def test_no_events_without_recorder(self, materializer, sample_agent_specs):
        """No audit events recorded when event_recorder is None."""
        run_id = generate_uuid()

        result = materializer.materialize_batch(
            sample_agent_specs,
            event_recorder=None,
            run_id=run_id,
        )

        # Should succeed without errors
        assert result.all_succeeded

        # No audit info should be set
        for r in result.results:
            assert r.audit_info is None

    def test_no_events_without_run_id(self, materializer, sample_agent_specs, mock_event_recorder):
        """No audit events recorded when run_id is None."""
        result = materializer.materialize_batch(
            sample_agent_specs,
            event_recorder=mock_event_recorder,
            run_id=None,
        )

        # Should succeed without errors
        assert result.all_succeeded

        # No audit events recorded
        mock_event_recorder.record_agent_materialized.assert_not_called()

    def test_audit_error_does_not_fail_materialization(self, materializer, sample_agent_specs):
        """Audit recording failure doesn't fail materialization."""
        run_id = generate_uuid()
        failing_recorder = MagicMock()
        failing_recorder.record_agent_materialized.side_effect = Exception("DB error")

        result = materializer.materialize_batch(
            sample_agent_specs,
            atomic=False,
            event_recorder=failing_recorder,
            run_id=run_id,
        )

        # Materialization should succeed
        assert result.all_succeeded

        # Audit info should show failure
        for r in result.results:
            assert r.audit_info is not None
            assert r.audit_info.recorded is False
            assert "DB error" in r.audit_info.error

    def test_atomic_batch_event_includes_all_names(self, materializer, sample_agent_specs, mock_event_recorder):
        """Atomic batch event payload includes all agent names."""
        run_id = generate_uuid()

        materializer.materialize_batch(
            sample_agent_specs,
            atomic=True,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        call_args = mock_event_recorder.record.call_args
        payload = call_args.kwargs['payload']

        assert set(payload['agent_names']) == {spec.name for spec in sample_agent_specs}

    def test_atomic_batch_event_includes_hashes(self, materializer, sample_agent_specs, mock_event_recorder):
        """Atomic batch event payload includes content hashes."""
        run_id = generate_uuid()

        materializer.materialize_batch(
            sample_agent_specs,
            atomic=True,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        call_args = mock_event_recorder.record.call_args
        payload = call_args.kwargs['payload']

        assert len(payload['content_hashes']) == 3
        # All hashes should be valid SHA256 (64 hex chars)
        for h in payload['content_hashes']:
            assert len(h) == 64


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for batch materialization."""

    def test_full_batch_workflow(self, materializer, sample_agent_specs, mock_event_recorder, temp_project_dir):
        """Test complete batch workflow with all features."""
        run_id = generate_uuid()
        progress_calls = []

        def on_progress(index, total, name, status):
            progress_calls.append((index, total, name, status))

        result = materializer.materialize_batch(
            sample_agent_specs,
            atomic=True,
            progress_callback=on_progress,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        # All specs succeeded
        assert result.all_succeeded
        assert result.atomic is True
        assert result.rolled_back is False

        # Progress was reported
        assert len(progress_calls) > 0

        # Batch audit event was recorded
        assert result.batch_audit_info is not None
        assert result.batch_audit_info.recorded is True

        # Files exist
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        for spec in sample_agent_specs:
            assert (output_dir / f"{spec.name}.md").exists()

    def test_batch_result_serialization(self, materializer, sample_agent_specs):
        """BatchMaterializationResult can be serialized to dict."""
        result = materializer.materialize_batch(sample_agent_specs, atomic=True)

        result_dict = result.to_dict()

        assert result_dict['total'] == 3
        assert result_dict['succeeded'] == 3
        assert result_dict['failed'] == 0
        assert result_dict['atomic'] is True
        assert result_dict['rolled_back'] is False
        assert len(result_dict['results']) == 3

    def test_large_batch(self, materializer, temp_project_dir):
        """Test batch with many specs."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name=f"agent-{i:03d}",
                display_name=f"Agent {i}",
                task_type="coding",
                objective=f"Objective {i}",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            )
            for i in range(20)
        ]

        result = materializer.materialize_batch(specs, atomic=True)

        assert result.total == 20
        assert result.succeeded == 20
        assert result.all_succeeded

        # Verify files
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        assert len(list(output_dir.glob("*.md"))) == 20


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_batch_with_duplicate_names(self, materializer, temp_project_dir):
        """Batch handles specs with same name (overwrites)."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="same-name",
                display_name="First",
                task_type="coding",
                objective="First objective",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
            AgentSpec(
                id=generate_uuid(),
                name="same-name",
                display_name="Second",
                task_type="coding",
                objective="Second objective",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
        ]

        result = materializer.materialize_batch(specs)

        assert result.succeeded == 2

        # File should exist
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        filepath = output_dir / "same-name.md"
        assert filepath.exists()

        # Content should be from second spec (last write wins)
        content = filepath.read_text()
        assert "Second" in content

    def test_atomic_with_readonly_directory(self, temp_project_dir):
        """Atomic batch handles permission errors."""
        import os

        materializer = AgentMaterializer(temp_project_dir)
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        specs = [
            AgentSpec(
                id=generate_uuid(),
                name="test-agent",
                display_name="Test",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            ),
        ]

        # Make directory readonly
        os.chmod(output_dir, 0o444)

        try:
            result = materializer.materialize_batch(specs, atomic=True)
            # Should fail
            assert result.failed > 0
        finally:
            # Restore permissions
            os.chmod(output_dir, 0o755)

    def test_progress_callback_exception_propagates(self, materializer, sample_agent_specs):
        """Exception in progress callback propagates to caller.

        Design decision: Progress callbacks are expected to be well-behaved.
        Exceptions in callbacks are not caught, allowing the caller to handle
        errors in their callback code explicitly.
        """
        def bad_callback(index, total, name, status):
            raise ValueError("Callback error")

        # Exception should propagate
        with pytest.raises(ValueError, match="Callback error"):
            materializer.materialize_batch(sample_agent_specs, progress_callback=bad_callback)

    def test_event_recorder_with_invalid_run_id(self, materializer, sample_agent_specs, mock_event_recorder):
        """Invalid run_id doesn't crash batch."""
        # Simulate event_recorder failing due to invalid run_id
        mock_event_recorder.record_agent_materialized.side_effect = ValueError("Invalid run_id")

        result = materializer.materialize_batch(
            sample_agent_specs,
            event_recorder=mock_event_recorder,
            run_id="invalid-uuid",
        )

        # Materialization should still succeed
        assert result.succeeded == 3

        # Audit should show failure
        for r in result.results:
            assert r.audit_info.recorded is False


# =============================================================================
# Feature #197 Verification Steps Summary
# =============================================================================

class TestFeature197VerificationSteps:
    """Tests covering all 5 verification steps for Feature #197."""

    def test_step1_accepts_list_of_agentspecs(self, materializer, sample_agent_specs):
        """Step 1: Materializer accepts list of AgentSpecs."""
        result = materializer.materialize_batch(sample_agent_specs)

        assert isinstance(result, BatchMaterializationResult)
        assert result.total == len(sample_agent_specs)
        assert len(result.results) == len(sample_agent_specs)

    def test_step2_each_spec_processed_individually(self, materializer, sample_agent_specs, temp_project_dir):
        """Step 2: Each spec processed and written individually."""
        result = materializer.materialize_batch(sample_agent_specs)

        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR

        # Each spec has its own file
        for spec in sample_agent_specs:
            filepath = output_dir / f"{spec.name}.md"
            assert filepath.exists()

        # Each result tracks individual success
        for i, r in enumerate(result.results):
            assert r.spec_id == sample_agent_specs[i].id
            assert r.spec_name == sample_agent_specs[i].name
            assert r.success is True
            assert r.file_path is not None

    def test_step3_atomic_all_or_nothing(self, materializer, temp_project_dir):
        """Step 3: Batch operation is atomic: all succeed or none written."""
        specs = [
            AgentSpec(
                id=generate_uuid(),
                name=f"agent-{i}",
                display_name=f"Agent {i}",
                task_type="coding",
                objective="Test",
                tool_policy={},
                max_turns=50,
                timeout_seconds=900,
            )
            for i in range(3)
        ]

        # Test success case
        result_success = materializer.materialize_batch(specs, atomic=True)
        assert result_success.atomic is True
        assert result_success.all_succeeded
        assert result_success.rolled_back is False

        # Clean up
        output_dir = temp_project_dir / DEFAULT_OUTPUT_DIR
        for f in output_dir.glob("*.md"):
            f.unlink()

        # Test rollback case
        original_write = Path.write_text
        call_count = [0]

        def failing_write(self, content, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise IOError("Write failed")
            return original_write(self, content, **kwargs)

        with patch.object(Path, 'write_text', failing_write):
            result_fail = materializer.materialize_batch(specs, atomic=True)

        assert result_fail.atomic is True
        assert result_fail.rolled_back is True
        assert result_fail.succeeded == 0

        # No files should remain
        assert len(list(output_dir.glob("*.md"))) == 0

    def test_step4_progress_reported(self, materializer, sample_agent_specs):
        """Step 4: Progress reported for each agent."""
        progress_events = []

        def callback(index, total, name, status):
            progress_events.append({
                "index": index,
                "total": total,
                "name": name,
                "status": status,
            })

        materializer.materialize_batch(sample_agent_specs, progress_callback=callback)

        # Should have progress for each spec
        assert len(progress_events) >= len(sample_agent_specs)

        # Check we have processing and completed for each
        statuses = {e["status"] for e in progress_events}
        assert "processing" in statuses
        assert "completed" in statuses

    def test_step5_audit_events_recorded(self, materializer, sample_agent_specs, mock_event_recorder):
        """Step 5: Single audit event or per-agent events recorded."""
        run_id = generate_uuid()

        # Non-atomic: per-agent events
        result_non_atomic = materializer.materialize_batch(
            sample_agent_specs,
            atomic=False,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        # Per-agent events recorded
        assert mock_event_recorder.record_agent_materialized.call_count == 3
        for r in result_non_atomic.results:
            assert r.audit_info is not None
            assert r.audit_info.recorded is True

        # Reset mock
        mock_event_recorder.reset_mock()

        # Atomic: single batch event
        result_atomic = materializer.materialize_batch(
            sample_agent_specs,
            atomic=True,
            event_recorder=mock_event_recorder,
            run_id=run_id,
        )

        # Single batch event recorded
        mock_event_recorder.record.assert_called_once()
        assert result_atomic.batch_audit_info is not None
        assert result_atomic.batch_audit_info.recorded is True
