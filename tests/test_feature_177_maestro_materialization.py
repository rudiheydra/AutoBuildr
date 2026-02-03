"""
Tests for Feature #177: Maestro orchestrates agent materialization after Octo completes

After receiving AgentSpecs from Octo, Maestro triggers the Agent Materializer to
create functional agent files.

Verification Steps:
1. Maestro receives validated AgentSpecs from Octo
2. Maestro invokes Agent Materializer with AgentSpecs and project path
3. Maestro awaits materialization completion
4. Maestro verifies agent files exist in .claude/agents/generated/
"""
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.maestro import (
    Maestro,
    AgentMaterializer,
    MaterializationResult,
    OrchestrationResult,
    reset_maestro,
)
from api.agentspec_models import AgentSpec, AcceptanceSpec, generate_uuid


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
def maestro_with_materializer(temp_project_dir):
    """Maestro instance configured for materialization."""
    reset_maestro()
    return Maestro(project_dir=temp_project_dir)


@pytest.fixture
def sample_agent_spec():
    """Sample AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="feature-42-user-login",
        display_name="User Login Feature",
        icon="login",
        spec_version="v1",
        objective="Implement user login functionality",
        task_type="coding",
        context={"feature_id": 42, "feature_name": "User Login"},
        tool_policy={
            "allowed_tools": ["Read", "Write", "Edit", "Bash"],
            "forbidden_patterns": ["rm -rf"],
            "tool_hints": {"Edit": "Always read before editing"},
        },
        max_turns=100,
        timeout_seconds=1800,
        source_feature_id=42,
        priority=1,
        tags=["feature-42", "authentication", "coding"],
    )


@pytest.fixture
def sample_agent_specs():
    """Multiple sample AgentSpecs for testing."""
    specs = []
    for i in range(3):
        spec_id = generate_uuid()
        spec = AgentSpec(
            id=spec_id,
            name=f"feature-{i+1}-test-spec-{i}",
            display_name=f"Test Spec {i}",
            icon="code",
            spec_version="v1",
            objective=f"Test objective {i}",
            task_type="coding",
            context={"feature_id": i + 1},
            tool_policy={"allowed_tools": ["Read", "Write"]},
            max_turns=50,
            timeout_seconds=900,
            source_feature_id=i + 1,
            priority=i + 1,
            tags=[f"feature-{i+1}"],
        )
        specs.append(spec)
    return specs


@pytest.fixture
def invalid_agent_spec():
    """Invalid AgentSpec (missing required fields)."""
    return AgentSpec(
        id="",  # Invalid: empty id
        name="",  # Invalid: empty name
        task_type="",  # Invalid: empty task_type
    )


@pytest.fixture
def invalid_name_spec():
    """AgentSpec with invalid name format."""
    return AgentSpec(
        id=generate_uuid(),
        name="invalid name with spaces!",  # Invalid: contains spaces and special chars
        task_type="coding",
    )


# =============================================================================
# Step 1: Maestro receives validated AgentSpecs from Octo
# =============================================================================

class TestStep1ReceiveSpecsFromOcto:
    """Verify Maestro receives validated AgentSpecs from Octo."""

    def test_receive_empty_specs_list(self, maestro_with_materializer):
        """Receiving empty specs list returns empty list."""
        result = maestro_with_materializer.receive_specs_from_octo([])
        assert result == []

    def test_receive_valid_specs(self, maestro_with_materializer, sample_agent_specs):
        """Valid specs are returned unchanged when validation passes."""
        result = maestro_with_materializer.receive_specs_from_octo(sample_agent_specs)
        assert len(result) == 3
        assert all(spec in result for spec in sample_agent_specs)

    def test_receive_specs_with_validation_disabled(self, maestro_with_materializer, invalid_agent_spec):
        """Specs are returned without validation when validate=False."""
        result = maestro_with_materializer.receive_specs_from_octo(
            [invalid_agent_spec], validate=False
        )
        assert len(result) == 1

    def test_receive_specs_filters_invalid(self, maestro_with_materializer, sample_agent_specs, invalid_agent_spec):
        """Invalid specs are filtered out during validation."""
        all_specs = sample_agent_specs + [invalid_agent_spec]
        result = maestro_with_materializer.receive_specs_from_octo(all_specs)
        assert len(result) == 3
        assert invalid_agent_spec not in result

    def test_receive_specs_validates_name_format(self, maestro_with_materializer, invalid_name_spec):
        """Specs with invalid name format are rejected."""
        result = maestro_with_materializer.receive_specs_from_octo([invalid_name_spec])
        assert len(result) == 0

    def test_validation_checks_required_fields(self, maestro_with_materializer):
        """Validation checks for id, name, and task_type."""
        # Missing id
        spec_no_id = AgentSpec(id="", name="test-spec", task_type="coding")
        result = maestro_with_materializer.receive_specs_from_octo([spec_no_id])
        assert len(result) == 0

        # Missing name
        spec_no_name = AgentSpec(id=generate_uuid(), name="", task_type="coding")
        result = maestro_with_materializer.receive_specs_from_octo([spec_no_name])
        assert len(result) == 0

        # Missing task_type
        spec_no_type = AgentSpec(id=generate_uuid(), name="test-spec", task_type="")
        result = maestro_with_materializer.receive_specs_from_octo([spec_no_type])
        assert len(result) == 0


# =============================================================================
# Step 2: Maestro invokes Agent Materializer with AgentSpecs and project path
# =============================================================================

class TestStep2InvokeMaterializer:
    """Verify Maestro invokes Agent Materializer with AgentSpecs and project path."""

    def test_invoke_materializer_creates_files(self, maestro_with_materializer, sample_agent_spec, temp_project_dir):
        """Invoking materializer creates agent files."""
        results = maestro_with_materializer.invoke_materializer([sample_agent_spec])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].file_path is not None
        assert results[0].file_path.exists()

    def test_invoke_materializer_multiple_specs(self, maestro_with_materializer, sample_agent_specs):
        """Invoking materializer with multiple specs creates multiple files."""
        results = maestro_with_materializer.invoke_materializer(sample_agent_specs)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.file_path.exists() for r in results)

    def test_invoke_materializer_returns_correct_results(self, maestro_with_materializer, sample_agent_spec):
        """Materializer returns MaterializationResult with correct spec info."""
        results = maestro_with_materializer.invoke_materializer([sample_agent_spec])

        result = results[0]
        assert result.spec_id == sample_agent_spec.id
        assert result.spec_name == sample_agent_spec.name
        assert result.error is None

    def test_invoke_materializer_without_materializer_raises_error(self, sample_agent_spec):
        """Invoking materializer without configuration raises RuntimeError."""
        reset_maestro()
        maestro = Maestro()  # No project_dir or materializer

        with pytest.raises(RuntimeError, match="No materializer configured"):
            maestro.invoke_materializer([sample_agent_spec])

    def test_materializer_creates_output_directory(self, temp_project_dir, sample_agent_spec):
        """Materializer creates output directory if it doesn't exist."""
        output_path = temp_project_dir / ".claude" / "agents" / "generated"
        assert not output_path.exists()

        materializer = AgentMaterializer(temp_project_dir)
        result = materializer.materialize(sample_agent_spec)

        assert output_path.exists()
        assert result.success

    def test_file_content_includes_frontmatter(self, materializer, sample_agent_spec):
        """Generated file includes YAML frontmatter."""
        result = materializer.materialize(sample_agent_spec)

        content = result.file_path.read_text()
        assert content.startswith("---")
        assert "name: User Login Feature" in content
        assert f"spec_id: {sample_agent_spec.id}" in content
        assert "task_type: coding" in content

    def test_file_content_includes_objective(self, materializer, sample_agent_spec):
        """Generated file includes objective section."""
        result = materializer.materialize(sample_agent_spec)

        content = result.file_path.read_text()
        assert "## Objective" in content
        assert sample_agent_spec.objective in content

    def test_file_content_includes_tool_policy(self, materializer, sample_agent_spec):
        """Generated file includes tool policy section."""
        result = materializer.materialize(sample_agent_spec)

        content = result.file_path.read_text()
        assert "## Tool Policy" in content
        assert "**Allowed Tools" in content


# =============================================================================
# Step 3: Maestro awaits materialization completion
# =============================================================================

class TestStep3AwaitMaterialization:
    """Verify Maestro awaits materialization completion."""

    @pytest.mark.asyncio
    async def test_await_materialization_returns_results(self, maestro_with_materializer, sample_agent_specs):
        """Async await_materialization returns results."""
        results = await maestro_with_materializer.await_materialization(sample_agent_specs)

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_await_materialization_creates_files(self, maestro_with_materializer, sample_agent_spec, temp_project_dir):
        """Async await_materialization creates files on disk."""
        results = await maestro_with_materializer.await_materialization([sample_agent_spec])

        assert len(results) == 1
        assert results[0].file_path.exists()


# =============================================================================
# Step 4: Maestro verifies agent files exist in .claude/agents/generated/
# =============================================================================

class TestStep4VerifyAgentFiles:
    """Verify Maestro verifies agent files exist in .claude/agents/generated/."""

    def test_verify_existing_files(self, maestro_with_materializer, sample_agent_specs):
        """Verification returns True for existing files."""
        # First materialize
        maestro_with_materializer.invoke_materializer(sample_agent_specs)

        # Then verify
        verification = maestro_with_materializer.verify_agent_files(sample_agent_specs)

        assert len(verification) == 3
        assert all(verification.values())

    def test_verify_non_existing_files(self, maestro_with_materializer, sample_agent_specs):
        """Verification returns False for non-existing files."""
        # Don't materialize, just verify
        verification = maestro_with_materializer.verify_agent_files(sample_agent_specs)

        assert len(verification) == 3
        assert not any(verification.values())

    def test_verify_partial_files(self, maestro_with_materializer, sample_agent_specs):
        """Verification correctly identifies partial materialization."""
        # Materialize only first spec
        maestro_with_materializer.invoke_materializer([sample_agent_specs[0]])

        # Verify all
        verification = maestro_with_materializer.verify_agent_files(sample_agent_specs)

        assert verification[sample_agent_specs[0].id] is True
        assert verification[sample_agent_specs[1].id] is False
        assert verification[sample_agent_specs[2].id] is False

    def test_verify_without_materializer_raises_error(self, sample_agent_specs):
        """Verifying without materializer raises RuntimeError."""
        reset_maestro()
        maestro = Maestro()  # No project_dir or materializer

        with pytest.raises(RuntimeError, match="No materializer configured"):
            maestro.verify_agent_files(sample_agent_specs)

    def test_verify_in_correct_directory(self, maestro_with_materializer, sample_agent_spec, temp_project_dir):
        """Verification checks the correct output directory."""
        expected_dir = temp_project_dir / ".claude" / "agents" / "generated"

        # Manually create file in wrong location
        wrong_dir = temp_project_dir / "wrong_location"
        wrong_dir.mkdir(parents=True)
        (wrong_dir / f"{sample_agent_spec.name}.md").write_text("wrong location")

        # Should not find it
        verification = maestro_with_materializer.verify_agent_files([sample_agent_spec])
        assert verification[sample_agent_spec.id] is False

        # Now materialize correctly
        maestro_with_materializer.invoke_materializer([sample_agent_spec])

        # Should find it
        verification = maestro_with_materializer.verify_agent_files([sample_agent_spec])
        assert verification[sample_agent_spec.id] is True


# =============================================================================
# Full Orchestration Flow
# =============================================================================

class TestOrchestrateMaterialization:
    """Test the full orchestration flow."""

    def test_orchestrate_full_flow(self, maestro_with_materializer, sample_agent_specs):
        """Full orchestration flow succeeds."""
        result = maestro_with_materializer.orchestrate_materialization(sample_agent_specs)

        assert isinstance(result, OrchestrationResult)
        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert result.verified is True
        assert result.all_succeeded is True

    def test_orchestrate_empty_specs(self, maestro_with_materializer):
        """Orchestration with empty specs returns appropriate result."""
        result = maestro_with_materializer.orchestrate_materialization([])

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.verified is False

    def test_orchestrate_with_invalid_specs(self, maestro_with_materializer, sample_agent_specs, invalid_agent_spec):
        """Orchestration filters invalid specs and processes valid ones."""
        all_specs = sample_agent_specs + [invalid_agent_spec]
        result = maestro_with_materializer.orchestrate_materialization(all_specs)

        # Invalid spec filtered out, 3 valid processed
        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0

    def test_orchestrate_all_invalid_specs(self, maestro_with_materializer, invalid_agent_spec, invalid_name_spec):
        """Orchestration with all invalid specs returns failure result."""
        result = maestro_with_materializer.orchestrate_materialization(
            [invalid_agent_spec, invalid_name_spec]
        )

        assert result.total == 2
        assert result.succeeded == 0
        assert result.failed == 2
        assert result.verified is False

    def test_orchestrate_result_serialization(self, maestro_with_materializer, sample_agent_specs):
        """OrchestrationResult can be serialized to dict."""
        result = maestro_with_materializer.orchestrate_materialization(sample_agent_specs)

        result_dict = result.to_dict()
        assert "total" in result_dict
        assert "succeeded" in result_dict
        assert "failed" in result_dict
        assert "verified" in result_dict
        assert "results" in result_dict
        assert len(result_dict["results"]) == 3


# =============================================================================
# AgentMaterializer Unit Tests
# =============================================================================

class TestAgentMaterializer:
    """Unit tests for AgentMaterializer class."""

    def test_output_path_property(self, temp_project_dir):
        """output_path returns correct path."""
        materializer = AgentMaterializer(temp_project_dir)
        expected = temp_project_dir / ".claude" / "agents" / "generated"
        assert materializer.output_path == expected

    def test_custom_output_dir(self, temp_project_dir):
        """Custom output directory is used."""
        materializer = AgentMaterializer(temp_project_dir, output_dir=".custom/agents")
        expected = temp_project_dir / ".custom" / "agents"
        assert materializer.output_path == expected

    def test_ensure_output_dir_creates_directory(self, temp_project_dir):
        """ensure_output_dir creates the directory."""
        materializer = AgentMaterializer(temp_project_dir)
        output_path = materializer.ensure_output_dir()
        assert output_path.exists()
        assert output_path.is_dir()

    def test_verify_exists_true(self, materializer, sample_agent_spec):
        """verify_exists returns True for existing file."""
        materializer.materialize(sample_agent_spec)
        assert materializer.verify_exists(sample_agent_spec) is True

    def test_verify_exists_false(self, materializer, sample_agent_spec):
        """verify_exists returns False for non-existing file."""
        assert materializer.verify_exists(sample_agent_spec) is False

    def test_verify_all(self, materializer, sample_agent_specs):
        """verify_all returns dict with verification status."""
        # Materialize first spec only
        materializer.materialize(sample_agent_specs[0])

        result = materializer.verify_all(sample_agent_specs)

        assert isinstance(result, dict)
        assert result[sample_agent_specs[0].id] is True
        assert result[sample_agent_specs[1].id] is False
        assert result[sample_agent_specs[2].id] is False


# =============================================================================
# MaterializationResult Tests
# =============================================================================

class TestMaterializationResult:
    """Unit tests for MaterializationResult dataclass."""

    def test_success_result(self, temp_project_dir):
        """Success result has correct fields."""
        file_path = temp_project_dir / "test.md"
        result = MaterializationResult(
            spec_id="test-id",
            spec_name="test-spec",
            success=True,
            file_path=file_path,
        )

        assert result.success is True
        assert result.file_path == file_path
        assert result.error is None

    def test_failure_result(self):
        """Failure result has error message."""
        result = MaterializationResult(
            spec_id="test-id",
            spec_name="test-spec",
            success=False,
            error="File write failed",
        )

        assert result.success is False
        assert result.file_path is None
        assert result.error == "File write failed"

    def test_to_dict(self, temp_project_dir):
        """to_dict returns correct dictionary."""
        file_path = temp_project_dir / "test.md"
        result = MaterializationResult(
            spec_id="test-id",
            spec_name="test-spec",
            success=True,
            file_path=file_path,
        )

        result_dict = result.to_dict()
        assert result_dict["spec_id"] == "test-id"
        assert result_dict["spec_name"] == "test-spec"
        assert result_dict["success"] is True
        assert result_dict["file_path"] == str(file_path)


# =============================================================================
# OrchestrationResult Tests
# =============================================================================

class TestOrchestrationResult:
    """Unit tests for OrchestrationResult dataclass."""

    def test_all_succeeded_true(self):
        """all_succeeded is True when no failures."""
        result = OrchestrationResult(total=3, succeeded=3, failed=0)
        assert result.all_succeeded is True

    def test_all_succeeded_false_with_failures(self):
        """all_succeeded is False when there are failures."""
        result = OrchestrationResult(total=3, succeeded=2, failed=1)
        assert result.all_succeeded is False

    def test_all_succeeded_false_when_empty(self):
        """all_succeeded is False when total is 0."""
        result = OrchestrationResult(total=0, succeeded=0, failed=0)
        assert result.all_succeeded is False

    def test_to_dict(self):
        """to_dict returns correct dictionary."""
        result = OrchestrationResult(
            total=3,
            succeeded=2,
            failed=1,
            verified=True,
            audit_events=["event-1", "event-2"],
        )

        result_dict = result.to_dict()
        assert result_dict["total"] == 3
        assert result_dict["succeeded"] == 2
        assert result_dict["failed"] == 1
        assert result_dict["verified"] is True
        assert result_dict["all_succeeded"] is False
        assert result_dict["audit_events"] == ["event-1", "event-2"]


# =============================================================================
# Maestro Configuration Tests
# =============================================================================

class TestMaestroConfiguration:
    """Test Maestro initialization and configuration."""

    def test_maestro_with_project_dir_creates_materializer(self, temp_project_dir):
        """Maestro with project_dir auto-creates materializer."""
        reset_maestro()
        maestro = Maestro(project_dir=temp_project_dir)

        assert maestro.materializer is not None
        assert isinstance(maestro.materializer, AgentMaterializer)
        assert maestro.materializer.project_dir == temp_project_dir

    def test_maestro_with_custom_materializer(self, temp_project_dir):
        """Maestro accepts custom materializer."""
        custom_materializer = AgentMaterializer(temp_project_dir, output_dir=".custom")
        reset_maestro()
        maestro = Maestro(materializer=custom_materializer)

        assert maestro.materializer is custom_materializer

    def test_maestro_without_materializer(self):
        """Maestro without project_dir has no materializer."""
        reset_maestro()
        maestro = Maestro()

        assert maestro.materializer is None

    def test_maestro_project_dir_resolved(self, temp_project_dir):
        """Maestro resolves project_dir to absolute path."""
        reset_maestro()
        # Use relative path simulation
        maestro = Maestro(project_dir=temp_project_dir)

        assert maestro.project_dir.is_absolute()
