"""
Tests for Feature #192: Agent Materializer converts AgentSpec to Claude Code markdown

The Agent Materializer takes AgentSpec objects and renders them as Claude Code-compatible
markdown files.

Verification Steps:
1. Materializer receives AgentSpec object
2. Materializer uses template to render markdown format
3. Output includes: agent name, description, tools, model, instructions
4. Markdown follows Claude Code agent file conventions
5. Output is deterministic given same input
"""
import hashlib
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.agent_materializer import (
    AgentMaterializer,
    MaterializationResult,
    BatchMaterializationResult,
    render_agentspec_to_markdown,
    verify_determinism,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_MODEL,
    DEFAULT_COLOR,
    TASK_TYPE_COLORS,
    VALID_MODELS,
    DESCRIPTION_MAX_LENGTH,
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
def sample_agent_spec():
    """Sample AgentSpec for testing."""
    spec_id = generate_uuid()
    return AgentSpec(
        id=spec_id,
        name="feature-42-user-login",
        display_name="User Login Feature",
        icon="login",
        spec_version="v1",
        objective="Implement user login functionality with OAuth2 support",
        task_type="coding",
        context={"feature_id": 42, "feature_name": "User Login", "model": "opus"},
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            "forbidden_patterns": ["rm -rf", "DROP TABLE", "format c:"],
            "tool_hints": {
                "Edit": "Always read before editing",
                "Bash": "Use with caution",
            },
        },
        max_turns=100,
        timeout_seconds=1800,
        source_feature_id=42,
        priority=1,
        tags=["feature-42", "authentication", "coding"],
    )


@pytest.fixture
def sample_spec_with_acceptance(sample_agent_spec):
    """Sample AgentSpec with AcceptanceSpec attached."""
    acceptance = AcceptanceSpec(
        id=generate_uuid(),
        agent_spec_id=sample_agent_spec.id,
        validators=[
            {"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": True},
            {"type": "file_exists", "config": {"path": "src/login.py"}, "weight": 0.5, "required": False},
        ],
        gate_mode="all_pass",
        min_score=0.8,
        retry_policy="fixed",
        max_retries=3,
    )
    sample_agent_spec.acceptance_spec = acceptance
    return sample_agent_spec


@pytest.fixture
def minimal_agent_spec():
    """Minimal AgentSpec with only required fields."""
    return AgentSpec(
        id=generate_uuid(),
        name="minimal-spec",
        display_name="Minimal Spec",
        task_type="coding",
        objective="A minimal spec",
        tool_policy={"allowed_tools": []},
        max_turns=50,
        timeout_seconds=900,
    )


@pytest.fixture
def multiple_agent_specs():
    """Multiple sample AgentSpecs for batch testing."""
    specs = []
    for i in range(3):
        spec_id = generate_uuid()
        spec = AgentSpec(
            id=spec_id,
            name=f"test-spec-{i}",
            display_name=f"Test Spec {i}",
            task_type="testing",
            objective=f"Test objective {i}",
            context={"index": i},
            tool_policy={"allowed_tools": ["Read", "Grep"]},
            max_turns=50,
            timeout_seconds=900,
        )
        specs.append(spec)
    return specs


# =============================================================================
# Step 1: Materializer receives AgentSpec object
# =============================================================================

class TestStep1ReceivesAgentSpec:
    """Verify Materializer receives AgentSpec object."""

    def test_materialize_accepts_agent_spec(self, materializer, sample_agent_spec):
        """Materializer accepts AgentSpec object."""
        result = materializer.materialize(sample_agent_spec)
        assert isinstance(result, MaterializationResult)
        assert result.spec_id == sample_agent_spec.id
        assert result.spec_name == sample_agent_spec.name

    def test_materialize_returns_success_for_valid_spec(self, materializer, sample_agent_spec):
        """Materializer returns success for valid AgentSpec."""
        result = materializer.materialize(sample_agent_spec)
        assert result.success is True
        assert result.error is None

    def test_materialize_creates_file(self, materializer, sample_agent_spec):
        """Materializer creates file on disk."""
        result = materializer.materialize(sample_agent_spec)
        assert result.file_path is not None
        assert result.file_path.exists()

    def test_materialize_batch_accepts_list(self, materializer, multiple_agent_specs):
        """Materializer batch accepts list of AgentSpecs."""
        result = materializer.materialize_batch(multiple_agent_specs)
        assert isinstance(result, BatchMaterializationResult)
        assert result.total == 3

    def test_materialize_returns_content_hash(self, materializer, sample_agent_spec):
        """Materializer returns content hash for verification."""
        result = materializer.materialize(sample_agent_spec)
        assert result.content_hash is not None
        assert len(result.content_hash) == 64  # SHA256 hex


# =============================================================================
# Step 2: Materializer uses template to render markdown format
# =============================================================================

class TestStep2UsesTemplate:
    """Verify Materializer uses template to render markdown format."""

    def test_render_returns_string(self, materializer, sample_agent_spec):
        """render_claude_code_markdown returns string."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_starts_with_frontmatter(self, materializer, sample_agent_spec):
        """Rendered markdown starts with YAML frontmatter."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert result.startswith("---")

    def test_render_has_frontmatter_delimiters(self, materializer, sample_agent_spec):
        """Rendered markdown has proper frontmatter delimiters."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        # Should have exactly two "---" lines for frontmatter
        lines = result.split("\n")
        frontmatter_delimiters = [i for i, line in enumerate(lines) if line == "---"]
        assert len(frontmatter_delimiters) >= 2

    def test_render_has_markdown_body(self, materializer, sample_agent_spec):
        """Rendered markdown has body after frontmatter."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        # Split by second "---" to get body
        parts = result.split("---", 2)
        assert len(parts) >= 3
        body = parts[2].strip()
        assert len(body) > 0

    def test_build_frontmatter_returns_dict(self, materializer, sample_agent_spec):
        """_build_frontmatter returns dictionary."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert isinstance(frontmatter, dict)

    def test_build_instructions_body_returns_string(self, materializer, sample_agent_spec):
        """_build_instructions_body returns string."""
        body = materializer._build_instructions_body(sample_agent_spec)
        assert isinstance(body, str)


# =============================================================================
# Step 3: Output includes agent name, description, tools, model, instructions
# =============================================================================

class TestStep3OutputIncludes:
    """Verify output includes: agent name, description, tools, model, instructions."""

    def test_output_includes_name(self, materializer, sample_agent_spec):
        """Output includes agent name in frontmatter."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert f"name: {sample_agent_spec.name}" in result

    def test_output_includes_description(self, materializer, sample_agent_spec):
        """Output includes description in frontmatter."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert "description:" in result
        # Description should contain task type
        assert "Task Type: coding" in result

    def test_output_includes_tools(self, materializer, sample_agent_spec):
        """Output includes tools in body."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        # Should list allowed tools
        assert "Allowed Tools" in result
        assert "`Read`" in result
        assert "`Write`" in result
        assert "`Edit`" in result

    def test_output_includes_model(self, materializer, sample_agent_spec):
        """Output includes model in frontmatter."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        # sample_agent_spec has model: opus in context
        assert "model: opus" in result

    def test_output_includes_instructions(self, materializer, sample_agent_spec):
        """Output includes instructions in body."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        # Should have objective
        assert "## Your Objective" in result
        assert sample_agent_spec.objective in result
        # Should have guidelines
        assert "## Execution Guidelines" in result

    def test_output_includes_default_model_when_not_specified(self, materializer, minimal_agent_spec):
        """Output includes default model when not specified in context."""
        result = materializer.render_claude_code_markdown(minimal_agent_spec)
        assert f"model: {DEFAULT_MODEL}" in result

    def test_output_includes_tool_hints(self, materializer, sample_agent_spec):
        """Output includes tool hints when available."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert "Tool Usage Hints" in result
        assert "**Edit**:" in result or "Edit:" in result

    def test_output_includes_forbidden_patterns(self, materializer, sample_agent_spec):
        """Output includes forbidden patterns when available."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert "Restrictions" in result
        assert "`rm -rf`" in result

    def test_output_includes_budget_constraints(self, materializer, sample_agent_spec):
        """Output includes budget constraints."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert "Budget Constraints" in result
        assert "Maximum Turns" in result
        assert str(sample_agent_spec.max_turns) in result
        assert "Timeout" in result
        assert str(sample_agent_spec.timeout_seconds) in result

    def test_output_includes_context_when_present(self, materializer, sample_agent_spec):
        """Output includes context section when context is present."""
        result = materializer.render_claude_code_markdown(sample_agent_spec)
        assert "## Additional Context" in result
        assert "```json" in result
        assert "feature_id" in result

    def test_output_includes_acceptance_criteria(self, materializer, sample_spec_with_acceptance):
        """Output includes acceptance criteria when present."""
        result = materializer.render_claude_code_markdown(sample_spec_with_acceptance)
        assert "## Acceptance Criteria" in result
        assert "Gate Mode" in result
        assert "all_pass" in result
        assert "Validators" in result


# =============================================================================
# Step 4: Markdown follows Claude Code agent file conventions
# =============================================================================

class TestStep4ClaudeCodeConventions:
    """Verify markdown follows Claude Code agent file conventions."""

    def test_frontmatter_has_required_name_field(self, materializer, sample_agent_spec):
        """Frontmatter has required 'name' field."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert "name" in frontmatter
        assert frontmatter["name"] == sample_agent_spec.name

    def test_frontmatter_has_required_description_field(self, materializer, sample_agent_spec):
        """Frontmatter has required 'description' field."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert "description" in frontmatter
        assert len(frontmatter["description"]) > 0

    def test_frontmatter_has_required_model_field(self, materializer, sample_agent_spec):
        """Frontmatter has required 'model' field."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert "model" in frontmatter
        assert frontmatter["model"] in VALID_MODELS

    def test_frontmatter_has_optional_color_field(self, materializer, sample_agent_spec):
        """Frontmatter has optional 'color' field."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert "color" in frontmatter
        assert frontmatter["color"] in TASK_TYPE_COLORS.values() or frontmatter["color"] == DEFAULT_COLOR

    def test_frontmatter_model_is_valid(self, materializer, sample_agent_spec):
        """Frontmatter model is one of: sonnet, opus, haiku."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert frontmatter["model"] in VALID_MODELS

    def test_description_includes_usage_example(self, materializer, sample_agent_spec):
        """Description includes usage example (Claude Code convention)."""
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        desc = frontmatter["description"]
        assert "example" in desc.lower() or "<example>" in desc

    def test_body_uses_markdown_headings(self, materializer, sample_agent_spec):
        """Body uses proper markdown headings."""
        body = materializer._build_instructions_body(sample_agent_spec)
        # Should have at least one ## heading
        assert "## " in body

    def test_file_extension_is_md(self, materializer, sample_agent_spec):
        """Generated file has .md extension."""
        result = materializer.materialize(sample_agent_spec)
        assert result.file_path.suffix == ".md"

    def test_output_in_correct_directory(self, materializer, sample_agent_spec, temp_project_dir):
        """File created in .claude/agents/generated/ directory."""
        result = materializer.materialize(sample_agent_spec)
        expected_dir = temp_project_dir / ".claude" / "agents" / "generated"
        assert result.file_path.parent == expected_dir

    def test_filename_matches_spec_name(self, materializer, sample_agent_spec):
        """Filename matches spec name."""
        result = materializer.materialize(sample_agent_spec)
        assert result.file_path.name == f"{sample_agent_spec.name}.md"


# =============================================================================
# Step 5: Output is deterministic given same input
# =============================================================================

class TestStep5Determinism:
    """Verify output is deterministic given same input."""

    def test_same_spec_produces_identical_output(self, materializer, sample_agent_spec):
        """Same AgentSpec produces identical markdown output."""
        output1 = materializer.render_claude_code_markdown(sample_agent_spec)
        output2 = materializer.render_claude_code_markdown(sample_agent_spec)
        assert output1 == output2

    def test_same_spec_produces_identical_hash(self, materializer, sample_agent_spec):
        """Same AgentSpec produces identical content hash."""
        result1 = materializer.materialize(sample_agent_spec)
        # Create new materializer to ensure no state
        with tempfile.TemporaryDirectory() as tmpdir:
            new_materializer = AgentMaterializer(Path(tmpdir))
            result2 = new_materializer.materialize(sample_agent_spec)
            assert result1.content_hash == result2.content_hash

    def test_verify_determinism_function(self, sample_agent_spec):
        """verify_determinism helper function works correctly."""
        result = verify_determinism(sample_agent_spec, iterations=5)
        assert result is True

    def test_multiple_renders_produce_same_output(self, materializer, sample_agent_spec):
        """Multiple renders of same spec produce identical output."""
        outputs = [materializer.render_claude_code_markdown(sample_agent_spec) for _ in range(10)]
        # All outputs should be identical
        assert len(set(outputs)) == 1

    def test_no_timestamps_in_output(self, materializer, sample_agent_spec):
        """Output does not contain timestamps that would break determinism."""
        output = materializer.render_claude_code_markdown(sample_agent_spec)
        # Check for common timestamp patterns
        import re
        # ISO format timestamp
        iso_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        matches = re.findall(iso_pattern, output)
        # If any timestamp found, it should be from the context, not auto-generated
        for match in matches:
            # Check if it's in the context JSON section
            context_json = json.dumps(sample_agent_spec.context)
            if match not in context_json:
                pytest.fail(f"Found auto-generated timestamp in output: {match}")

    def test_json_sorting_is_consistent(self, materializer, sample_agent_spec):
        """JSON in context section is sorted for determinism."""
        output = materializer.render_claude_code_markdown(sample_agent_spec)
        # Extract JSON from context section
        if "```json" in output:
            json_start = output.find("```json") + 7
            json_end = output.find("```", json_start)
            json_str = output[json_start:json_end].strip()
            # Should be valid JSON
            parsed = json.loads(json_str)
            # Re-serialize with sort_keys and compare
            reserialized = json.dumps(parsed, indent=2, sort_keys=True)
            assert json_str == reserialized


# =============================================================================
# Additional Tests: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_spec_with_no_context(self, materializer, minimal_agent_spec):
        """Handle spec with no context."""
        result = materializer.render_claude_code_markdown(minimal_agent_spec)
        # Should not have context section
        assert "## Additional Context" not in result

    def test_spec_with_empty_tool_policy(self, materializer):
        """Handle spec with empty tool policy."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="empty-policy",
            display_name="Empty Policy Spec",
            task_type="coding",
            objective="Test",
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=900,
        )
        result = materializer.render_claude_code_markdown(spec)
        assert "## Tool Policy" in result

    def test_spec_with_none_tool_policy(self, materializer):
        """Handle spec with None tool policy."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="none-policy",
            display_name="None Policy Spec",
            task_type="coding",
            objective="Test",
            tool_policy=None,
            max_turns=50,
            timeout_seconds=900,
        )
        result = materializer.render_claude_code_markdown(spec)
        assert "Tool Policy" in result or "No specific tool policy" in result

    def test_spec_with_long_objective(self, materializer):
        """Handle spec with very long objective."""
        long_objective = "Test " * 500  # Very long objective
        spec = AgentSpec(
            id=generate_uuid(),
            name="long-objective",
            display_name="Long Objective Spec",
            task_type="coding",
            objective=long_objective,
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=900,
        )
        result = materializer.render_claude_code_markdown(spec)
        # Should render without error
        assert "## Your Objective" in result

    def test_special_characters_in_name(self, materializer, temp_project_dir):
        """Handle special characters in spec name."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="feature-with-special-chars-123",
            display_name="Feature With Special Chars",
            task_type="coding",
            objective="Test",
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=900,
        )
        result = materializer.materialize(spec)
        assert result.success is True

    def test_all_task_types_have_color(self, materializer):
        """All standard task types map to a color."""
        task_types = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]
        for task_type in task_types:
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"task-{task_type}",
                display_name=f"Task {task_type}",
                task_type=task_type,
                objective="Test",
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=900,
            )
            frontmatter = materializer._build_frontmatter(spec)
            assert "color" in frontmatter

    def test_unknown_task_type_gets_default_color(self, materializer):
        """Unknown task type gets default color."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="unknown-task",
            display_name="Unknown Task",
            task_type="unknown_type",
            objective="Test",
            tool_policy={"allowed_tools": []},
            max_turns=50,
            timeout_seconds=900,
        )
        frontmatter = materializer._build_frontmatter(spec)
        assert frontmatter["color"] == DEFAULT_COLOR


# =============================================================================
# Batch Materialization Tests
# =============================================================================

class TestBatchMaterialization:
    """Test batch materialization functionality."""

    def test_batch_creates_all_files(self, materializer, multiple_agent_specs):
        """Batch materialization creates all files."""
        result = materializer.materialize_batch(multiple_agent_specs)
        assert result.succeeded == 3
        assert result.failed == 0
        for r in result.results:
            assert r.file_path.exists()

    def test_batch_result_properties(self, materializer, multiple_agent_specs):
        """BatchMaterializationResult has correct properties."""
        result = materializer.materialize_batch(multiple_agent_specs)
        assert result.total == 3
        assert result.all_succeeded is True

    def test_batch_to_dict(self, materializer, multiple_agent_specs):
        """BatchMaterializationResult serializes to dict."""
        result = materializer.materialize_batch(multiple_agent_specs)
        d = result.to_dict()
        assert "total" in d
        assert "succeeded" in d
        assert "failed" in d
        assert "results" in d
        assert "all_succeeded" in d


# =============================================================================
# Verification Tests
# =============================================================================

class TestVerification:
    """Test file verification functionality."""

    def test_verify_exists_true(self, materializer, sample_agent_spec):
        """verify_exists returns True for existing file."""
        materializer.materialize(sample_agent_spec)
        assert materializer.verify_exists(sample_agent_spec) is True

    def test_verify_exists_false(self, materializer, sample_agent_spec):
        """verify_exists returns False for non-existing file."""
        assert materializer.verify_exists(sample_agent_spec) is False

    def test_verify_all(self, materializer, multiple_agent_specs):
        """verify_all returns dict of verification status."""
        # Materialize only first spec
        materializer.materialize(multiple_agent_specs[0])

        result = materializer.verify_all(multiple_agent_specs)
        assert result[multiple_agent_specs[0].id] is True
        assert result[multiple_agent_specs[1].id] is False
        assert result[multiple_agent_specs[2].id] is False

    def test_get_file_path(self, materializer, sample_agent_spec, temp_project_dir):
        """get_file_path returns expected path."""
        expected = temp_project_dir / ".claude" / "agents" / "generated" / f"{sample_agent_spec.name}.md"
        assert materializer.get_file_path(sample_agent_spec) == expected


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_render_agentspec_to_markdown(self, sample_agent_spec):
        """render_agentspec_to_markdown function works."""
        result = render_agentspec_to_markdown(sample_agent_spec)
        assert isinstance(result, str)
        assert result.startswith("---")
        assert f"name: {sample_agent_spec.name}" in result


# =============================================================================
# Configuration Tests
# =============================================================================

class TestConfiguration:
    """Test materializer configuration."""

    def test_default_output_dir(self, temp_project_dir):
        """Default output directory is .claude/agents/generated."""
        materializer = AgentMaterializer(temp_project_dir)
        expected = temp_project_dir / ".claude" / "agents" / "generated"
        assert materializer.output_path == expected

    def test_custom_output_dir(self, temp_project_dir):
        """Custom output directory can be specified."""
        materializer = AgentMaterializer(temp_project_dir, output_dir=".custom/agents")
        expected = temp_project_dir / ".custom" / "agents"
        assert materializer.output_path == expected

    def test_ensure_output_dir_creates_directory(self, temp_project_dir):
        """ensure_output_dir creates directory if not exists."""
        materializer = AgentMaterializer(temp_project_dir)
        assert not materializer.output_path.exists()
        materializer.ensure_output_dir()
        assert materializer.output_path.exists()


# =============================================================================
# Feature Verification Steps Summary
# =============================================================================

class TestFeature192VerificationSteps:
    """
    Comprehensive tests for all 5 verification steps of Feature #192.

    These tests serve as the final verification that all requirements are met.
    """

    def test_step1_receives_agentspec_object(self, materializer, sample_agent_spec):
        """Step 1: Materializer receives AgentSpec object."""
        # Materializer should accept AgentSpec without error
        result = materializer.materialize(sample_agent_spec)
        assert result.spec_id == sample_agent_spec.id
        assert result.success is True

    def test_step2_uses_template_for_markdown(self, materializer, sample_agent_spec):
        """Step 2: Materializer uses template to render markdown format."""
        output = materializer.render_claude_code_markdown(sample_agent_spec)
        # Should have proper structure
        assert output.startswith("---")  # Frontmatter start
        assert output.count("---") >= 2  # Frontmatter delimiters
        assert "## " in output  # Markdown headings in body

    def test_step3_output_includes_required_elements(self, materializer, sample_agent_spec):
        """Step 3: Output includes agent name, description, tools, model, instructions."""
        output = materializer.render_claude_code_markdown(sample_agent_spec)

        # Agent name
        assert f"name: {sample_agent_spec.name}" in output

        # Description
        assert "description:" in output

        # Tools
        assert "Tool Policy" in output
        assert "Allowed Tools" in output

        # Model
        assert "model:" in output

        # Instructions
        assert "## Your Objective" in output
        assert "## Execution Guidelines" in output

    def test_step4_follows_claude_code_conventions(self, materializer, sample_agent_spec, temp_project_dir):
        """Step 4: Markdown follows Claude Code agent file conventions."""
        result = materializer.materialize(sample_agent_spec)

        # Check frontmatter format
        content = result.file_path.read_text()
        assert content.startswith("---")

        # Check required frontmatter fields
        frontmatter = materializer._build_frontmatter(sample_agent_spec)
        assert "name" in frontmatter
        assert "description" in frontmatter
        assert "model" in frontmatter
        assert frontmatter["model"] in VALID_MODELS

        # Check file location
        expected_dir = temp_project_dir / ".claude" / "agents" / "generated"
        assert result.file_path.parent == expected_dir

        # Check file extension
        assert result.file_path.suffix == ".md"

    def test_step5_output_is_deterministic(self, materializer, sample_agent_spec):
        """Step 5: Output is deterministic given same input."""
        # Render multiple times
        outputs = [materializer.render_claude_code_markdown(sample_agent_spec) for _ in range(5)]

        # All outputs should be identical
        assert len(set(outputs)) == 1

        # Compute hash for extra verification
        hashes = [hashlib.sha256(o.encode()).hexdigest() for o in outputs]
        assert len(set(hashes)) == 1
