"""
Tests for Feature #194: Agent Materializer is deterministic and idempotent

Given the same AgentSpec, Materializer always produces identical output. Re-running is safe.

Verification Steps:
1. Same AgentSpec always produces byte-identical markdown
2. Timestamps not included in output (determinism)
3. Re-materialization overwrites existing files safely
4. No side effects beyond file writes
5. Materializer can be re-run without state concerns
"""
import hashlib
import os
import re
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import json

import pytest

from api.maestro import AgentMaterializer, MaterializationResult
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
def sample_agent_spec():
    """Sample AgentSpec for testing determinism."""
    # Use a fixed ID for reproducibility in determinism tests
    spec_id = "test-spec-id-12345"
    return AgentSpec(
        id=spec_id,
        name="determinism-test-agent",
        display_name="Determinism Test Agent",
        icon="test",
        spec_version="v1",
        objective="Test agent for Feature #194 determinism testing",
        task_type="testing",
        context={
            "feature_id": 194,
            "feature_name": "Materializer Determinism",
            "test_key": "test_value",
            "nested": {"a": 1, "b": 2},
        },
        tool_policy={
            "allowed_tools": ["Read", "Write", "Edit", "Bash"],
            "forbidden_patterns": ["rm -rf", "sudo"],
            "tool_hints": {"Edit": "Always read before editing"},
        },
        max_turns=100,
        timeout_seconds=1800,
        source_feature_id=194,
        priority=1,
        tags=["feature-194", "determinism", "testing"],
    )


@pytest.fixture
def spec_with_unsorted_context():
    """AgentSpec with unsorted context keys to test key ordering."""
    return AgentSpec(
        id=generate_uuid(),
        name="unsorted-context-agent",
        display_name="Unsorted Context Agent",
        icon="test",
        spec_version="v1",
        objective="Test context key sorting",
        task_type="testing",
        context={
            "zebra": "last",
            "apple": "first",
            "mango": "middle",
        },
        tool_policy={"allowed_tools": ["Read"]},
        max_turns=50,
        timeout_seconds=600,
    )


# =============================================================================
# Step 1: Same AgentSpec always produces byte-identical markdown
# =============================================================================

class TestStep1ByteIdenticalOutput:
    """Verify same AgentSpec always produces byte-identical markdown."""

    def test_consecutive_materializations_produce_identical_content(
        self, materializer, sample_agent_spec
    ):
        """Multiple materializations produce identical content."""
        # Materialize multiple times
        results = []
        contents = []
        for _ in range(5):
            result = materializer.materialize(sample_agent_spec)
            assert result.success
            content = result.file_path.read_text()
            results.append(result)
            contents.append(content)

        # All contents should be identical
        assert len(set(contents)) == 1, "All outputs should be identical"

    def test_same_spec_produces_same_hash(self, materializer, sample_agent_spec):
        """Same AgentSpec produces same content hash."""
        result1 = materializer.materialize(sample_agent_spec)
        result2 = materializer.materialize(sample_agent_spec)

        assert result1.content_hash == result2.content_hash

    def test_different_materializer_instances_produce_same_output(
        self, temp_project_dir, sample_agent_spec
    ):
        """Different materializer instances produce identical output."""
        # Create two separate materializer instances
        materializer1 = AgentMaterializer(temp_project_dir, output_dir="output1")
        materializer2 = AgentMaterializer(temp_project_dir, output_dir="output2")

        result1 = materializer1.materialize(sample_agent_spec)
        result2 = materializer2.materialize(sample_agent_spec)

        content1 = result1.file_path.read_text()
        content2 = result2.file_path.read_text()

        assert content1 == content2, "Different instances should produce identical output"
        assert result1.content_hash == result2.content_hash

    def test_byte_level_comparison(self, materializer, sample_agent_spec):
        """Byte-level comparison confirms identical output."""
        result1 = materializer.materialize(sample_agent_spec)
        content1 = result1.file_path.read_bytes()

        result2 = materializer.materialize(sample_agent_spec)
        content2 = result2.file_path.read_bytes()

        assert content1 == content2, "Byte-level content should be identical"

    def test_hash_verification_matches_file_content(
        self, materializer, sample_agent_spec
    ):
        """Content hash matches actual file content hash."""
        result = materializer.materialize(sample_agent_spec)

        # Compute hash from file directly
        file_content = result.file_path.read_bytes()
        computed_hash = hashlib.sha256(file_content).hexdigest()

        assert result.content_hash == computed_hash

    def test_determinism_across_time_delay(self, materializer, sample_agent_spec):
        """Output is identical even with time delay between materializations."""
        result1 = materializer.materialize(sample_agent_spec)
        content1 = result1.file_path.read_text()

        # Wait a bit
        time.sleep(0.1)

        result2 = materializer.materialize(sample_agent_spec)
        content2 = result2.file_path.read_text()

        assert content1 == content2, "Time delay should not affect output"


# =============================================================================
# Step 2: Timestamps not included in output (determinism)
# =============================================================================

class TestStep2NoTimestamps:
    """Verify timestamps are not included in output."""

    def test_no_created_at_in_output(self, materializer, sample_agent_spec):
        """Output does not contain created_at timestamp."""
        result = materializer.materialize(sample_agent_spec)
        content = result.file_path.read_text()

        assert "created_at:" not in content

    def test_no_timestamp_in_output(self, materializer, sample_agent_spec):
        """Output does not contain any timestamp patterns."""
        result = materializer.materialize(sample_agent_spec)
        content = result.file_path.read_text()

        # Check for ISO timestamp pattern (e.g., 2024-01-15T10:30:00)
        iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        matches = re.findall(iso_pattern, content)

        assert len(matches) == 0, f"Found timestamp patterns: {matches}"

    def test_no_modified_at_in_output(self, materializer, sample_agent_spec):
        """Output does not contain modified_at timestamp."""
        result = materializer.materialize(sample_agent_spec)
        content = result.file_path.read_text()

        assert "modified_at:" not in content
        assert "updated_at:" not in content

    def test_no_datetime_now_in_output(self, materializer, sample_agent_spec):
        """Output does not contain datetime.now() artifacts."""
        result = materializer.materialize(sample_agent_spec)
        content = result.file_path.read_text()

        # Check for various date/time patterns
        patterns = [
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{2}/\d{2}/\d{4}",  # MM/DD/YYYY
            r"\d{2}:\d{2}:\d{2}\.\d+",  # HH:MM:SS.microseconds
        ]

        # Some patterns might legitimately appear in spec content
        # (e.g., in objective text), so we check frontmatter specifically
        frontmatter_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            for pattern in patterns:
                # Check if pattern exists in frontmatter with a field name
                timestamp_field = re.search(rf"^\w+:\s*{pattern}", frontmatter, re.MULTILINE)
                assert timestamp_field is None, \
                    f"Found timestamp-like field in frontmatter: {timestamp_field.group()}"


# =============================================================================
# Step 3: Re-materialization overwrites existing files safely
# =============================================================================

class TestStep3SafeOverwrite:
    """Verify re-materialization overwrites existing files safely."""

    def test_overwrite_produces_valid_file(self, materializer, sample_agent_spec):
        """Overwriting produces a valid, readable file."""
        # First write
        result1 = materializer.materialize(sample_agent_spec)
        assert result1.success

        # Overwrite
        result2 = materializer.materialize(sample_agent_spec)
        assert result2.success

        # File should be valid and readable
        content = result2.file_path.read_text()
        assert len(content) > 0
        assert "---" in content  # Has frontmatter

    def test_overwrite_does_not_corrupt_file(self, materializer, sample_agent_spec):
        """Overwriting does not corrupt the file."""
        # First write
        result1 = materializer.materialize(sample_agent_spec)
        original_hash = result1.content_hash

        # Overwrite multiple times
        for _ in range(10):
            result = materializer.materialize(sample_agent_spec)
            assert result.success
            assert result.content_hash == original_hash, "Hash should remain consistent"

    def test_overwrite_replaces_content_completely(self, materializer, sample_agent_spec):
        """Overwriting replaces content completely, not appending."""
        # First write with original objective
        sample_agent_spec.objective = "ORIGINAL_OBJECTIVE_MARKER"
        result1 = materializer.materialize(sample_agent_spec)

        # Get file size
        size1 = result1.file_path.stat().st_size

        # Overwrite with different objective
        sample_agent_spec.objective = "NEW_OBJECTIVE"
        result2 = materializer.materialize(sample_agent_spec)

        # Read content
        content = result2.file_path.read_text()

        # Original marker should not be present
        assert "ORIGINAL_OBJECTIVE_MARKER" not in content
        assert "NEW_OBJECTIVE" in content

        # File size should be reasonable (not doubled)
        size2 = result2.file_path.stat().st_size
        # Allow some variation but not double
        assert size2 < size1 * 2

    def test_overwrite_preserves_file_path(self, materializer, sample_agent_spec):
        """Overwriting preserves the file path."""
        result1 = materializer.materialize(sample_agent_spec)
        result2 = materializer.materialize(sample_agent_spec)

        assert result1.file_path == result2.file_path

    def test_overwrite_manually_modified_file(self, materializer, sample_agent_spec):
        """Can safely overwrite a manually modified file."""
        # First materialization
        result1 = materializer.materialize(sample_agent_spec)

        # Manually modify the file
        result1.file_path.write_text("MANUALLY MODIFIED CONTENT")

        # Re-materialize - should overwrite
        result2 = materializer.materialize(sample_agent_spec)

        content = result2.file_path.read_text()
        assert "MANUALLY MODIFIED CONTENT" not in content
        assert sample_agent_spec.display_name in content


# =============================================================================
# Step 4: No side effects beyond file writes
# =============================================================================

class TestStep4NoSideEffects:
    """Verify no side effects beyond file writes."""

    def test_no_additional_files_created(self, materializer, sample_agent_spec):
        """No additional files are created (no logs, temp files, etc.)."""
        # List files before
        materializer.ensure_output_dir()
        files_before = set(materializer.output_path.glob("**/*"))

        # Materialize
        result = materializer.materialize(sample_agent_spec)

        # List files after
        files_after = set(materializer.output_path.glob("**/*"))

        # Only the expected file should be added
        new_files = files_after - files_before
        assert len(new_files) == 1
        assert result.file_path in new_files

    def test_no_directories_created_beyond_output(self, temp_project_dir, sample_agent_spec):
        """No directories created beyond the output directory."""
        materializer = AgentMaterializer(temp_project_dir)

        # List directories before
        dirs_before = set(temp_project_dir.glob("**"))

        # Materialize
        materializer.materialize(sample_agent_spec)

        # List directories after
        dirs_after = set(temp_project_dir.glob("**"))

        # Only .claude/agents/generated directories should be added
        new_dirs = dirs_after - dirs_before
        for d in new_dirs:
            assert ".claude" in str(d), f"Unexpected directory: {d}"

    def test_no_environment_changes(self, materializer, sample_agent_spec):
        """Materialization does not change environment variables."""
        env_before = dict(os.environ)

        materializer.materialize(sample_agent_spec)

        env_after = dict(os.environ)
        assert env_before == env_after

    def test_no_state_in_result_object(self, materializer, sample_agent_spec):
        """Result object contains only expected fields."""
        result = materializer.materialize(sample_agent_spec)

        # Check result attributes
        result_dict = result.to_dict()
        expected_keys = {"spec_id", "spec_name", "success", "file_path", "error", "content_hash"}
        assert set(result_dict.keys()) == expected_keys

    def test_multiple_specs_no_cross_contamination(self, materializer):
        """Multiple specs don't contaminate each other."""
        specs = []
        for i in range(3):
            spec = AgentSpec(
                id=f"spec-{i}",
                name=f"agent-{i}",
                display_name=f"Agent {i}",
                icon="test",
                spec_version="v1",
                objective=f"Unique objective {i}",
                task_type="testing",
                context={"index": i},
                tool_policy={"allowed_tools": ["Read"]},
                max_turns=50,
                timeout_seconds=600,
            )
            specs.append(spec)

        # Materialize all
        results = [materializer.materialize(spec) for spec in specs]

        # Verify each file contains only its own data
        for i, result in enumerate(results):
            content = result.file_path.read_text()
            assert f"Unique objective {i}" in content
            # Should not contain other objectives
            for j in range(3):
                if j != i:
                    assert f"Unique objective {j}" not in content


# =============================================================================
# Step 5: Materializer can be re-run without state concerns
# =============================================================================

class TestStep5StatelessRerun:
    """Verify materializer can be re-run without state concerns."""

    def test_fresh_materializer_produces_same_output(
        self, temp_project_dir, sample_agent_spec
    ):
        """Fresh materializer instance produces same output."""
        # First instance
        mat1 = AgentMaterializer(temp_project_dir)
        result1 = mat1.materialize(sample_agent_spec)
        content1 = result1.file_path.read_text()

        # Delete the instance
        del mat1

        # Fresh instance
        mat2 = AgentMaterializer(temp_project_dir)
        result2 = mat2.materialize(sample_agent_spec)
        content2 = result2.file_path.read_text()

        assert content1 == content2

    def test_materializer_has_no_instance_state(self, temp_project_dir, sample_agent_spec):
        """Materializer doesn't accumulate instance state."""
        materializer = AgentMaterializer(temp_project_dir)

        # Materialize many specs
        for i in range(10):
            spec = AgentSpec(
                id=f"spec-{i}",
                name=f"agent-{i}",
                display_name=f"Agent {i}",
                icon="test",
                spec_version="v1",
                objective=f"Objective {i}",
                task_type="testing",
                context={},
                tool_policy={"allowed_tools": ["Read"]},
                max_turns=50,
                timeout_seconds=600,
            )
            materializer.materialize(spec)

        # Materialize original spec - should be same as if done first
        result = materializer.materialize(sample_agent_spec)

        # Create fresh materializer and compare
        fresh = AgentMaterializer(temp_project_dir, output_dir="fresh")
        fresh_result = fresh.materialize(sample_agent_spec)

        assert result.content_hash == fresh_result.content_hash

    def test_concurrent_materializations_safe(self, temp_project_dir):
        """Multiple concurrent materializations are safe."""
        import concurrent.futures

        def materialize_spec(spec_id):
            mat = AgentMaterializer(temp_project_dir, output_dir=f"output_{spec_id}")
            spec = AgentSpec(
                id=f"spec-{spec_id}",
                name=f"agent-{spec_id}",
                display_name=f"Agent {spec_id}",
                icon="test",
                spec_version="v1",
                objective="Concurrent test",
                task_type="testing",
                context={"id": spec_id},
                tool_policy={"allowed_tools": ["Read"]},
                max_turns=50,
                timeout_seconds=600,
            )
            return mat.materialize(spec)

        # Run concurrent materializations
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(materialize_spec, i) for i in range(5)]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.success for r in results)

    def test_re_run_after_error_works(self, temp_project_dir, sample_agent_spec):
        """Re-running after an error works correctly."""
        materializer = AgentMaterializer(temp_project_dir)

        # First successful run
        result1 = materializer.materialize(sample_agent_spec)
        assert result1.success
        hash1 = result1.content_hash

        # Simulate an "error" by deleting the file
        result1.file_path.unlink()

        # Re-run should work
        result2 = materializer.materialize(sample_agent_spec)
        assert result2.success
        assert result2.content_hash == hash1

    def test_context_sorting_ensures_determinism(
        self, materializer, spec_with_unsorted_context
    ):
        """Context keys are sorted for deterministic output."""
        result = materializer.materialize(spec_with_unsorted_context)
        content = result.file_path.read_text()

        # Find the context JSON block
        match = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
        assert match is not None

        json_content = match.group(1)

        # Keys should appear in sorted order in the JSON string
        apple_pos = json_content.find('"apple"')
        mango_pos = json_content.find('"mango"')
        zebra_pos = json_content.find('"zebra"')

        assert apple_pos < mango_pos < zebra_pos, "Context keys should be sorted"


# =============================================================================
# Additional Determinism Tests
# =============================================================================

class TestDeterminismWithVariations:
    """Additional tests for determinism with various spec variations."""

    def test_determinism_with_empty_context(self, materializer):
        """Deterministic output with empty context."""
        spec = AgentSpec(
            id="empty-context-spec",
            name="empty-context",
            display_name="Empty Context",
            icon="test",
            spec_version="v1",
            objective="Test",
            task_type="testing",
            context={},
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=600,
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1

    def test_determinism_with_none_values(self, materializer):
        """Deterministic output with None values."""
        spec = AgentSpec(
            id="none-values-spec",
            name="none-values",
            display_name="None Values",
            icon="test",
            spec_version="v1",
            objective=None,
            task_type="testing",
            context=None,
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=600,
            source_feature_id=None,
            priority=None,
            tags=None,
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1

    def test_determinism_with_unicode(self, materializer):
        """Deterministic output with unicode characters."""
        spec = AgentSpec(
            id="unicode-spec",
            name="unicode-agent",
            display_name="Unicode \u2713 \u2717 Agent",
            icon="test",
            spec_version="v1",
            objective="\u00e9\u00e8\u00ea Test \u65e5\u672c\u8a9e",
            task_type="testing",
            context={"emoji": "\U0001F600", "symbol": "\u2192"},
            tool_policy={"allowed_tools": ["Read"]},
            max_turns=50,
            timeout_seconds=600,
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1

    def test_determinism_with_complex_tool_policy(self, materializer):
        """Deterministic output with complex tool policy."""
        spec = AgentSpec(
            id="complex-policy-spec",
            name="complex-policy",
            display_name="Complex Policy",
            icon="test",
            spec_version="v1",
            objective="Test",
            task_type="testing",
            context={},
            tool_policy={
                "allowed_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                "forbidden_patterns": ["rm -rf", "sudo", "chmod 777"],
                "tool_hints": {
                    "Edit": "Always read first",
                    "Bash": "Use safe commands only",
                    "Write": "Backup before overwriting",
                },
            },
            max_turns=100,
            timeout_seconds=1800,
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1


# =============================================================================
# Feature #194 Verification Steps
# =============================================================================

class TestFeature194VerificationSteps:
    """Tests verifying all 5 steps for Feature #194."""

    def test_step1_byte_identical_output(self, materializer, sample_agent_spec):
        """Step 1: Same AgentSpec always produces byte-identical markdown."""
        # Materialize multiple times
        contents = []
        for _ in range(5):
            result = materializer.materialize(sample_agent_spec)
            assert result.success
            content = result.file_path.read_bytes()
            contents.append(content)

        # All bytes should be identical
        assert len(set(contents)) == 1, "All outputs must be byte-identical"

    def test_step2_no_timestamps(self, materializer, sample_agent_spec):
        """Step 2: Timestamps not included in output (determinism)."""
        result = materializer.materialize(sample_agent_spec)
        content = result.file_path.read_text()

        # No timestamp fields
        assert "created_at:" not in content
        assert "modified_at:" not in content
        assert "updated_at:" not in content
        assert "generated_at:" not in content

        # No ISO timestamp patterns in frontmatter
        frontmatter_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
            assert not re.search(iso_pattern, frontmatter), \
                "No ISO timestamps should appear in frontmatter"

    def test_step3_safe_overwrite(self, materializer, sample_agent_spec):
        """Step 3: Re-materialization overwrites existing files safely."""
        # First write
        sample_agent_spec.objective = "First version"
        result1 = materializer.materialize(sample_agent_spec)
        assert result1.success

        # Overwrite
        sample_agent_spec.objective = "Second version"
        result2 = materializer.materialize(sample_agent_spec)
        assert result2.success

        # Same path
        assert result1.file_path == result2.file_path

        # Content properly replaced
        content = result2.file_path.read_text()
        assert "Second version" in content
        assert "First version" not in content

        # Only one file exists
        files = list(materializer.output_path.glob(f"{sample_agent_spec.name}*"))
        assert len(files) == 1

    def test_step4_no_side_effects(self, temp_project_dir, sample_agent_spec):
        """Step 4: No side effects beyond file writes."""
        materializer = AgentMaterializer(temp_project_dir)

        # Count files/dirs before
        all_items_before = set(temp_project_dir.rglob("*"))

        # Materialize
        result = materializer.materialize(sample_agent_spec)

        # Count files/dirs after
        all_items_after = set(temp_project_dir.rglob("*"))

        # Only output directory structure and one file should be added
        new_items = all_items_after - all_items_before
        assert result.file_path in new_items

        # All new items should be within .claude directory
        for item in new_items:
            rel_path = item.relative_to(temp_project_dir)
            assert str(rel_path).startswith(".claude"), \
                f"Unexpected item outside .claude: {rel_path}"

    def test_step5_stateless_rerun(self, temp_project_dir, sample_agent_spec):
        """Step 5: Materializer can be re-run without state concerns."""
        # Create, use, delete materializer
        mat1 = AgentMaterializer(temp_project_dir)
        result1 = mat1.materialize(sample_agent_spec)
        hash1 = result1.content_hash
        del mat1

        # Create new instance
        mat2 = AgentMaterializer(temp_project_dir)

        # Materialize many other specs to "pollute" state
        for i in range(5):
            other_spec = AgentSpec(
                id=f"other-{i}",
                name=f"other-agent-{i}",
                display_name=f"Other Agent {i}",
                icon="test",
                spec_version="v1",
                objective=f"Other objective {i}",
                task_type="testing",
                context={},
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=600,
            )
            mat2.materialize(other_spec)

        # Re-materialize original spec
        result2 = mat2.materialize(sample_agent_spec)

        # Should produce identical output regardless of instance or prior work
        assert result2.content_hash == hash1


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for determinism and idempotence."""

    def test_full_determinism_workflow(self, temp_project_dir, sample_agent_spec):
        """Complete workflow testing all aspects of determinism."""
        # Create materializer
        mat = AgentMaterializer(temp_project_dir)

        # First materialization
        result1 = mat.materialize(sample_agent_spec)
        assert result1.success
        hash1 = result1.content_hash
        content1 = result1.file_path.read_bytes()

        # Verify no timestamps
        text_content = content1.decode("utf-8")
        assert "created_at:" not in text_content

        # Re-materialize (idempotent)
        result2 = mat.materialize(sample_agent_spec)
        assert result2.success
        assert result2.content_hash == hash1
        content2 = result2.file_path.read_bytes()
        assert content1 == content2

        # New instance (stateless)
        mat2 = AgentMaterializer(temp_project_dir, output_dir="verify")
        result3 = mat2.materialize(sample_agent_spec)
        assert result3.content_hash == hash1
        content3 = result3.file_path.read_bytes()
        assert content1 == content3

    def test_verify_determinism_helper_function(self, sample_agent_spec):
        """Test the verify_determinism helper function from agent_materializer."""
        # Import from the more complete module
        from api.agent_materializer import verify_determinism

        assert verify_determinism(sample_agent_spec, iterations=5)

    def test_render_function_determinism(self, sample_agent_spec):
        """Test render_agentspec_to_markdown for determinism."""
        from api.agent_materializer import render_agentspec_to_markdown

        outputs = [render_agentspec_to_markdown(sample_agent_spec) for _ in range(5)]
        assert len(set(outputs)) == 1


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for determinism."""

    def test_very_large_context_determinism(self, materializer):
        """Deterministic with very large context."""
        large_context = {f"key_{i}": f"value_{i}" for i in range(100)}
        spec = AgentSpec(
            id="large-context",
            name="large-context",
            display_name="Large Context",
            icon="test",
            spec_version="v1",
            objective="Test",
            task_type="testing",
            context=large_context,
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=600,
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1

    def test_special_characters_in_fields(self, materializer):
        """Deterministic with special characters."""
        spec = AgentSpec(
            id="special-chars",
            name="special-chars",
            display_name='Agent "with" <special> & chars',
            icon="test",
            spec_version="v1",
            objective="Test: *bold*, _italic_, `code`",
            task_type="testing",
            context={"key": "value\nwith\nnewlines"},
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=600,
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1

    def test_acceptance_spec_determinism(self, materializer):
        """Deterministic with acceptance spec."""
        from api.agentspec_models import AcceptanceSpec

        spec = AgentSpec(
            id="with-acceptance",
            name="with-acceptance",
            display_name="With Acceptance",
            icon="test",
            spec_version="v1",
            objective="Test",
            task_type="testing",
            context={},
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=600,
            acceptance_spec=AcceptanceSpec(
                gate_mode="all",
                validators=[
                    {"type": "file_exists", "config": {"path": "/test"}, "weight": 1.0},
                ],
                min_score=0.8,
                retry_policy="no_retry",
                max_retries=0,
            ),
        )

        hashes = set()
        for _ in range(3):
            result = materializer.materialize(spec)
            hashes.add(result.content_hash)

        assert len(hashes) == 1
