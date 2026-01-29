"""
Tests for Feature #149: Integrate TemplateRegistry into DSPy SpecBuilder pipeline

Verifies that the SpecBuilder queries the TemplateRegistry for a matching
template based on task_type and includes template content as additional context
in the DSPy compilation input. Tests cover:

1. SpecBuilder accepts a TemplateRegistry instance
2. Template is queried by task_type during build()
3. Template content is included as additional project_context in DSPy input
4. Variable interpolation resolves context values in template content
5. Builds without a registry still work (backward compatibility)
6. Builds with a template produce richer context than without
"""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from api.spec_builder import (
    BuildResult,
    SpecBuilder,
    get_spec_builder,
    reset_spec_builder,
)
from api.template_registry import (
    Template,
    TemplateMetadata,
    TemplateRegistry,
    get_template_registry,
    reset_template_registry,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_prediction(
    *,
    objective: str = "Implement the feature as described.",
    tool_policy: dict | None = None,
    validators: list | None = None,
    max_turns: int = 100,
    timeout_seconds: int = 1800,
    reasoning: str = "Analysis of the task...",
    context_json: dict | None = None,
):
    """Create a mock DSPy Prediction object with sensible defaults."""
    if tool_policy is None:
        tool_policy = {
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Edit"],
        }
    if validators is None:
        validators = [{"type": "test_pass", "config": {"command": "pytest"}}]
    if context_json is None:
        context_json = {"target_files": ["src/main.py"]}

    mock = MagicMock()
    mock.reasoning = reasoning
    mock.objective = objective
    mock.context_json = json.dumps(context_json)
    mock.tool_policy_json = json.dumps(tool_policy)
    mock.max_turns = max_turns
    mock.timeout_seconds = timeout_seconds
    mock.validators_json = json.dumps(validators)
    return mock


def _create_builder_with_mock_dspy(
    *,
    registry: TemplateRegistry | None = None,
    prediction: MagicMock | None = None,
) -> SpecBuilder:
    """Create a SpecBuilder with mocked DSPy internals."""
    builder = SpecBuilder(
        api_key="test-key-12345",
        auto_initialize=False,
        registry=registry,
    )
    # Manually mark as initialized and set up a mock module
    builder._initialized = True
    builder._dspy_module = MagicMock(
        return_value=prediction or _make_mock_prediction()
    )
    return builder


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_api_key():
    """Provide a mock API key."""
    return "test-api-key-feature-149"


@pytest.fixture
def mock_env_api_key(mock_api_key):
    """Set up environment with mock API key."""
    original = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = mock_api_key
    yield mock_api_key
    if original:
        os.environ["ANTHROPIC_API_KEY"] = original
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture
def temp_prompts_dir(tmp_path):
    """Create a temporary prompts directory with test templates."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()

    # Create a coding template with YAML front matter
    (prompts / "coding_prompt.md").write_text(textwrap.dedent("""\
        ---
        task_type: coding
        required_tools:
          - Read
          - Write
          - Edit
          - Bash
        default_max_turns: 100
        default_timeout_seconds: 3600
        ---
        ## CODING AGENT INSTRUCTIONS

        You are a coding agent working on project {{project_name}}.
        Feature ID: {{feature_id}}

        Follow test-driven development. Build the feature end-to-end.
    """))

    # Create a testing template
    (prompts / "testing_prompt.md").write_text(textwrap.dedent("""\
        ---
        task_type: testing
        required_tools:
          - Read
          - Grep
          - Bash
        default_max_turns: 75
        default_timeout_seconds: 1200
        ---
        ## TESTING AGENT INSTRUCTIONS

        You are a testing agent. Run regression tests for {{project_name}}.
    """))

    # Create an audit template (no variables, no default budgets)
    (prompts / "audit_prompt.md").write_text(textwrap.dedent("""\
        ---
        task_type: audit
        required_tools:
          - Read
          - Grep
        ---
        ## AUDIT AGENT INSTRUCTIONS

        Perform a read-only security audit of the codebase.
    """))

    return prompts


@pytest.fixture
def registry(temp_prompts_dir):
    """Create a TemplateRegistry from the temp prompts directory."""
    return TemplateRegistry(temp_prompts_dir, auto_scan=True, cache_enabled=True)


# =============================================================================
# Test Step 1: Locate the SpecBuilder/DSPy pipeline module
# =============================================================================

class TestStep1LocateSpecBuilder:
    """Verify SpecBuilder module can be imported and has expected structure."""

    def test_spec_builder_importable(self):
        """SpecBuilder class is importable from api.spec_builder."""
        from api.spec_builder import SpecBuilder
        assert SpecBuilder is not None

    def test_spec_builder_has_build_method(self):
        """SpecBuilder has a build() method."""
        assert hasattr(SpecBuilder, "build")
        assert callable(getattr(SpecBuilder, "build"))

    def test_spec_builder_has_registry_param(self):
        """SpecBuilder.__init__ accepts a registry parameter (Feature #149)."""
        import inspect
        sig = inspect.signature(SpecBuilder.__init__)
        assert "registry" in sig.parameters

    def test_spec_builder_has_registry_property(self):
        """SpecBuilder has a registry property (Feature #149)."""
        builder = SpecBuilder(
            api_key="test-key",
            auto_initialize=False,
            registry=None,
        )
        assert hasattr(builder, "registry")
        assert builder.registry is None


# =============================================================================
# Test Step 2: Locate the TemplateRegistry module
# =============================================================================

class TestStep2LocateTemplateRegistry:
    """Verify TemplateRegistry module can be imported and used."""

    def test_template_registry_importable(self):
        """TemplateRegistry class is importable from api.template_registry."""
        from api.template_registry import TemplateRegistry
        assert TemplateRegistry is not None

    def test_template_registry_get_template(self, registry):
        """TemplateRegistry.get_template(task_type=...) works."""
        template = registry.get_template(task_type="coding")
        assert template is not None
        assert template.metadata.task_type == "coding"

    def test_template_registry_interpolate(self, registry):
        """TemplateRegistry.interpolate() substitutes variables."""
        template = registry.get_template(task_type="coding")
        result = registry.interpolate(
            template,
            {"project_name": "TestApp", "feature_id": 42},
        )
        assert "TestApp" in result
        assert "42" in result

    def test_template_registry_returns_none_for_unknown_task_type(self, registry):
        """get_template returns None for unknown task_type."""
        result = registry.get_template(task_type="unknown_type_xyz")
        assert result is None


# =============================================================================
# Test Step 3: SpecBuilder queries TemplateRegistry for matching template
# =============================================================================

class TestStep3SpecBuilderQueriesRegistry:
    """Verify SpecBuilder queries TemplateRegistry by task_type."""

    def test_builder_stores_registry(self, registry):
        """SpecBuilder stores the registry reference."""
        builder = SpecBuilder(
            api_key="test-key",
            auto_initialize=False,
            registry=registry,
        )
        assert builder.registry is registry

    def test_builder_registry_setter(self, registry):
        """SpecBuilder.registry can be set after construction."""
        builder = SpecBuilder(
            api_key="test-key",
            auto_initialize=False,
        )
        assert builder.registry is None
        builder.registry = registry
        assert builder.registry is registry

    def test_build_queries_registry_for_coding(self, registry):
        """build() with task_type='coding' queries registry for coding template."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        result = builder.build(
            task_description="Add user authentication",
            task_type="coding",
            context={"project_name": "MyApp", "feature_id": 42},
        )
        assert result.success

        # Verify DSPy was called with context containing template_context
        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        assert "template_context" in project_context

    def test_build_queries_registry_for_testing(self, registry):
        """build() with task_type='testing' queries registry for testing template."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        result = builder.build(
            task_description="Run regression tests",
            task_type="testing",
            context={"project_name": "TestApp"},
        )
        assert result.success

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        assert "template_context" in project_context
        tc = project_context["template_context"]
        assert tc["template_task_type"] == "testing"

    def test_build_no_template_for_unknown_type(self, registry):
        """build() with task_type that has no template still succeeds."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        result = builder.build(
            task_description="Refactor module",
            task_type="refactoring",
            context={},
        )
        assert result.success

        # Verify no template_context in DSPy input
        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        assert "template_context" not in project_context


# =============================================================================
# Test Step 4: Template content included as additional context in DSPy input
# =============================================================================

class TestStep4TemplateContentInContext:
    """Verify template content is properly included in DSPy compilation input."""

    def test_template_content_present_in_context(self, registry):
        """Template content string appears in the project_context."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Add feature",
            task_type="coding",
            context={"project_name": "MyApp"},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]

        # Template content should include the coding prompt text
        assert "CODING AGENT INSTRUCTIONS" in tc["template_content"]

    def test_template_tools_in_context(self, registry):
        """Template required_tools metadata is included."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Write code",
            task_type="coding",
            context={},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]

        assert "template_tools" in tc
        assert "Read" in tc["template_tools"]
        assert "Write" in tc["template_tools"]

    def test_template_defaults_in_context(self, registry):
        """Template default budget values are included."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Write code",
            task_type="coding",
            context={},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]

        assert "template_defaults" in tc
        assert tc["template_defaults"]["max_turns"] == 100
        assert tc["template_defaults"]["timeout_seconds"] == 3600

    def test_template_task_type_in_context(self, registry):
        """Template's declared task_type is included in context."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Audit the codebase",
            task_type="audit",
            context={},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]

        assert tc["template_task_type"] == "audit"

    def test_audit_template_no_defaults(self, registry):
        """Audit template has no default budgets - template_defaults absent."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Audit the codebase",
            task_type="audit",
            context={},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]

        # Audit template doesn't define default budgets
        assert "template_defaults" not in tc

    def test_original_context_preserved(self, registry):
        """Original context fields are preserved alongside template_context."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Add feature",
            task_type="coding",
            context={"project_name": "MyApp", "feature_id": 42},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)

        # Original context preserved
        assert project_context["project_name"] == "MyApp"
        assert project_context["feature_id"] == 42
        # Template context also present
        assert "template_context" in project_context


# =============================================================================
# Test Step 5: Template variable interpolation works correctly
# =============================================================================

class TestStep5TemplateInterpolation:
    """Verify template variable interpolation resolves context values."""

    def test_variables_interpolated_from_context(self, registry):
        """Variables like {{project_name}} are resolved from context dict."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Add feature",
            task_type="coding",
            context={"project_name": "SuperApp", "feature_id": 99},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]
        content = tc["template_content"]

        # Variables should be resolved
        assert "SuperApp" in content
        assert "99" in content
        # Original placeholder should NOT be present
        assert "{{project_name}}" not in content
        assert "{{feature_id}}" not in content

    def test_missing_variables_left_as_is(self, registry):
        """Missing variables are left as-is (non-strict mode)."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Add feature",
            task_type="coding",
            context={},  # No project_name or feature_id
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]
        content = tc["template_content"]

        # Unreplaced variables should still appear (non-strict interpolation)
        assert "{{project_name}}" in content or "{project_name}" in content

    def test_testing_template_variables(self, registry):
        """Testing template variables are interpolated correctly."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Run tests",
            task_type="testing",
            context={"project_name": "TestProject"},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)
        tc = project_context["template_context"]
        content = tc["template_content"]

        assert "TestProject" in content
        assert "TESTING AGENT" in content


# =============================================================================
# Test Step 6: Compiling with vs. without template produces different output
# =============================================================================

class TestStep6WithVsWithoutTemplate:
    """Verify compiling with a template produces richer output than without."""

    def test_without_registry_no_template_context(self):
        """Build without registry produces no template_context in DSPy input."""
        builder = _create_builder_with_mock_dspy(registry=None)

        builder.build(
            task_description="Add feature",
            task_type="coding",
            context={"project_name": "App"},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)

        assert "template_context" not in project_context

    def test_with_registry_has_template_context(self, registry):
        """Build with registry produces template_context in DSPy input."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        builder.build(
            task_description="Add feature",
            task_type="coding",
            context={"project_name": "App"},
        )

        call_args = builder._dspy_module.call_args
        project_context_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
        project_context = json.loads(project_context_json)

        assert "template_context" in project_context
        tc = project_context["template_context"]
        assert "template_content" in tc
        assert len(tc["template_content"]) > 0

    def test_context_json_longer_with_template(self, registry):
        """context_json string is longer when template is included."""
        builder_no_tpl = _create_builder_with_mock_dspy(registry=None)
        builder_with_tpl = _create_builder_with_mock_dspy(registry=registry)

        ctx = {"project_name": "App"}

        builder_no_tpl.build(
            task_description="Add feature",
            task_type="coding",
            context=dict(ctx),
        )
        builder_with_tpl.build(
            task_description="Add feature",
            task_type="coding",
            context=dict(ctx),
        )

        call_no = builder_no_tpl._dspy_module.call_args
        json_no = call_no.kwargs.get("project_context") or call_no[1].get("project_context")

        call_with = builder_with_tpl._dspy_module.call_args
        json_with = call_with.kwargs.get("project_context") or call_with[1].get("project_context")

        # With template should produce strictly more context
        assert len(json_with) > len(json_no)

    def test_build_still_succeeds_without_registry(self):
        """Backward compatibility: build succeeds with registry=None."""
        builder = _create_builder_with_mock_dspy(registry=None)

        result = builder.build(
            task_description="Write docs",
            task_type="documentation",
            context={},
        )
        assert result.success
        assert result.agent_spec is not None

    def test_build_succeeds_when_registry_has_no_match(self, registry):
        """Build succeeds even when registry has no template for task_type."""
        builder = _create_builder_with_mock_dspy(registry=registry)

        # 'custom' has no template in our test registry
        result = builder.build(
            task_description="Do something custom",
            task_type="custom",
            context={},
        )
        assert result.success
        assert result.agent_spec is not None

    def test_get_spec_builder_accepts_registry(self, registry, mock_env_api_key):
        """get_spec_builder() accepts a registry parameter (Feature #149)."""
        reset_spec_builder()
        try:
            builder = get_spec_builder(registry=registry, force_new=True)
            assert builder.registry is registry
        finally:
            reset_spec_builder()


# =============================================================================
# Test: _get_template_context internal method
# =============================================================================

class TestGetTemplateContext:
    """Unit tests for the _get_template_context helper method."""

    def test_returns_none_without_registry(self):
        """Returns None when registry is not configured."""
        builder = SpecBuilder(
            api_key="test",
            auto_initialize=False,
            registry=None,
        )
        result = builder._get_template_context("coding", {"project_name": "X"})
        assert result is None

    def test_returns_none_for_unknown_task_type(self, registry):
        """Returns None when no template matches task_type."""
        builder = SpecBuilder(
            api_key="test",
            auto_initialize=False,
            registry=registry,
        )
        result = builder._get_template_context("custom", {})
        assert result is None

    def test_returns_context_for_coding(self, registry):
        """Returns template context dict for coding task_type."""
        builder = SpecBuilder(
            api_key="test",
            auto_initialize=False,
            registry=registry,
        )
        result = builder._get_template_context(
            "coding", {"project_name": "MyApp", "feature_id": 1}
        )
        assert result is not None
        assert "template_content" in result
        assert "CODING AGENT" in result["template_content"]
        assert result["template_task_type"] == "coding"
        assert "template_tools" in result
        assert "template_defaults" in result

    def test_interpolation_in_context(self, registry):
        """Variables in template are interpolated with context values."""
        builder = SpecBuilder(
            api_key="test",
            auto_initialize=False,
            registry=registry,
        )
        result = builder._get_template_context(
            "coding", {"project_name": "HelloWorld", "feature_id": 777}
        )
        assert "HelloWorld" in result["template_content"]
        assert "777" in result["template_content"]

    def test_handles_interpolation_error_gracefully(self, registry):
        """If interpolation fails, raw content is used."""
        builder = SpecBuilder(
            api_key="test",
            auto_initialize=False,
            registry=registry,
        )

        # Mock registry.interpolate to raise an exception
        original_interpolate = registry.interpolate
        def failing_interpolate(*args, **kwargs):
            raise RuntimeError("Interpolation boom!")

        registry.interpolate = failing_interpolate
        try:
            result = builder._get_template_context("coding", {})
            # Should still return context with raw (uninterpolated) content
            assert result is not None
            assert "template_content" in result
            assert "CODING AGENT" in result["template_content"]
        finally:
            registry.interpolate = original_interpolate


# =============================================================================
# Test: Integration with real prompts directory
# =============================================================================

class TestRealPromptsIntegration:
    """Integration test using the real prompts/ directory."""

    def test_real_registry_loads_templates(self):
        """Real TemplateRegistry loads templates from project prompts/ dir."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        if not prompts_dir.exists():
            pytest.skip("prompts/ directory not found")

        registry = TemplateRegistry(prompts_dir, auto_scan=True)
        task_types = registry.list_task_types()
        assert len(task_types) > 0
        assert "coding" in task_types or "testing" in task_types

    def test_real_builder_with_registry(self):
        """SpecBuilder with real TemplateRegistry can be constructed."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        if not prompts_dir.exists():
            pytest.skip("prompts/ directory not found")

        registry = TemplateRegistry(prompts_dir, auto_scan=True)
        builder = SpecBuilder(
            api_key="test-key",
            auto_initialize=False,
            registry=registry,
        )
        assert builder.registry is registry

        # Test _get_template_context with real templates
        result = builder._get_template_context("coding", {"project_name": "RealApp"})
        assert result is not None
        assert "template_content" in result
        assert len(result["template_content"]) > 100  # Real templates are substantial

    def test_real_builder_coding_template_context(self):
        """Real coding template produces substantial context."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        if not prompts_dir.exists():
            pytest.skip("prompts/ directory not found")

        registry = TemplateRegistry(prompts_dir, auto_scan=True)
        builder = SpecBuilder(
            api_key="test-key",
            auto_initialize=False,
            registry=registry,
        )

        ctx = builder._get_template_context("coding", {})
        if ctx is None:
            pytest.skip("No coding template found in real prompts/")

        # Real coding template should have meaningful content
        assert len(ctx["template_content"]) > 500
        assert ctx["template_task_type"] == "coding"
