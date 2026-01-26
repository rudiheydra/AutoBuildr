"""
Tests for the Template Registry Module

Verifies Feature #51: Skill Template Registry
- Create TemplateRegistry class
- Scan prompts/ directory for template files
- Parse template metadata (task_type, required_tools, etc.)
- Index templates by task_type
- Implement get_template(task_type) -> Template
- Implement interpolate(template, variables) -> str
- Cache compiled templates for performance
- Handle missing template gracefully with fallback
"""
from __future__ import annotations

import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from api.template_registry import (
    FRONT_MATTER_PATTERN,
    InterpolationError,
    Template,
    TemplateError,
    TemplateMetadata,
    TemplateNotFoundError,
    TemplateParseError,
    TemplateRegistry,
    find_variables,
    get_template_registry,
    interpolate,
    parse_front_matter,
    reset_template_registry,
    _simple_yaml_parse,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_prompts_dir():
    """Create a temporary directory with test templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()
        yield prompts_dir


@pytest.fixture
def sample_coding_template(temp_prompts_dir):
    """Create a sample coding template."""
    content = """---
task_type: coding
name: Coding Agent Template
description: Template for coding tasks
required_tools:
  - feature_get_by_id
  - feature_mark_passing
default_max_turns: 100
default_timeout_seconds: 3600
icon: code
---
## YOUR ROLE - CODING AGENT

You are working on feature {{feature_id}} for project {{project_name}}.

Your objective: {{objective}}
"""
    path = temp_prompts_dir / "coding_prompt.md"
    path.write_text(content)
    return path


@pytest.fixture
def sample_testing_template(temp_prompts_dir):
    """Create a sample testing template."""
    content = """---
task_type: testing
name: Testing Agent
required_tools:
  - browser_navigate
  - browser_click
default_max_turns: 50
---
## TESTING AGENT

Testing feature {{feature_id}}.
"""
    path = temp_prompts_dir / "testing_prompt.md"
    path.write_text(content)
    return path


@pytest.fixture
def no_frontmatter_template(temp_prompts_dir):
    """Create a template without front matter."""
    content = """## SIMPLE TEMPLATE

This template has no front matter.
Variable: {{name}}
"""
    path = temp_prompts_dir / "simple.md"
    path.write_text(content)
    return path


@pytest.fixture
def registry_with_templates(temp_prompts_dir, sample_coding_template, sample_testing_template):
    """Create a registry with preloaded templates."""
    registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
    return registry


# =============================================================================
# Test: Front Matter Parsing
# =============================================================================

class TestFrontMatterParsing:
    """Tests for YAML front matter parsing."""

    def test_parse_full_front_matter(self):
        """Test parsing template with complete front matter."""
        content = """---
task_type: coding
name: Test Template
required_tools:
  - tool_a
  - tool_b
default_max_turns: 100
---
Content here
"""
        metadata, clean_content = parse_front_matter(content)

        assert metadata.task_type == "coding"
        assert metadata.name == "Test Template"
        assert metadata.required_tools == ["tool_a", "tool_b"]
        assert metadata.default_max_turns == 100
        assert clean_content.strip() == "Content here"

    def test_parse_no_front_matter(self):
        """Test parsing template without front matter."""
        content = "Just content\nNo front matter"
        metadata, clean_content = parse_front_matter(content)

        assert metadata.task_type is None
        assert metadata.required_tools == []
        assert clean_content == content

    def test_parse_empty_front_matter(self):
        """Test parsing template with empty front matter."""
        # Note: The front matter has empty content between --- markers
        content = "---\n---\nContent\n"
        metadata, clean_content = parse_front_matter(content)

        assert metadata.task_type is None
        assert clean_content.strip() == "Content"

    def test_parse_extra_fields(self):
        """Test that unknown fields go to extra dict."""
        content = """---
task_type: coding
custom_field: custom_value
another_field: 42
---
Content
"""
        metadata, _ = parse_front_matter(content)

        assert metadata.task_type == "coding"
        assert metadata.extra.get("custom_field") == "custom_value"
        assert metadata.extra.get("another_field") == 42

    def test_simple_yaml_parser_basic_values(self):
        """Test the fallback YAML parser with basic values."""
        content = """task_type: coding
max_turns: 100
is_enabled: true
is_disabled: false
name: Test Name"""
        result = _simple_yaml_parse(content)

        assert result["task_type"] == "coding"
        assert result["max_turns"] == 100
        assert result["is_enabled"] is True
        assert result["is_disabled"] is False
        assert result["name"] == "Test Name"

    def test_simple_yaml_parser_lists(self):
        """Test the fallback YAML parser with lists."""
        content = """required_tools:
  - tool_a
  - tool_b
  - tool_c"""
        result = _simple_yaml_parse(content)

        assert result["required_tools"] == ["tool_a", "tool_b", "tool_c"]


# =============================================================================
# Test: Variable Interpolation
# =============================================================================

class TestInterpolation:
    """Tests for variable interpolation."""

    def test_interpolate_simple(self):
        """Test basic variable interpolation."""
        template = "Hello, {{name}}!"
        result = interpolate(template, {"name": "World"})
        assert result == "Hello, World!"

    def test_interpolate_multiple_variables(self):
        """Test interpolating multiple variables."""
        template = "Feature #{{id}}: {{title}}"
        result = interpolate(template, {"id": 42, "title": "Test Feature"})
        assert result == "Feature #42: Test Feature"

    def test_interpolate_missing_not_strict(self):
        """Test that missing variables are left as-is when not strict."""
        template = "Hello, {{name}}! Your ID is {{id}}."
        result = interpolate(template, {"name": "Alice"})
        assert result == "Hello, Alice! Your ID is {{id}}."

    def test_interpolate_missing_strict(self):
        """Test that missing variables raise error when strict."""
        template = "Hello, {{name}}!"
        with pytest.raises(InterpolationError) as exc_info:
            interpolate(template, {}, strict=True)
        assert exc_info.value.variable == "name"

    def test_interpolate_single_braces(self):
        """Test interpolation with single braces."""
        template = "Value: {value}"
        result = interpolate(template, {"value": 123})
        assert result == "Value: 123"

    def test_interpolate_double_braces(self):
        """Test interpolation with double braces."""
        template = "Value: {{value}}"
        result = interpolate(template, {"value": 456})
        assert result == "Value: 456"

    def test_interpolate_with_spaces(self):
        """Test interpolation handles whitespace in variable syntax."""
        template = "A: {{ name }} B: {  other  }"
        result = interpolate(template, {"name": "X", "other": "Y"})
        assert result == "A: X B: Y"

    def test_find_variables(self):
        """Test finding all variables in a template."""
        template = """
Feature: {{feature_id}}
Project: {{project_name}}
Feature again: {{feature_id}}
New var: {new_var}
"""
        variables = find_variables(template)
        assert variables == ["feature_id", "project_name", "new_var"]


# =============================================================================
# Test: TemplateRegistry Creation
# =============================================================================

class TestTemplateRegistryCreation:
    """Tests for TemplateRegistry initialization."""

    def test_create_registry(self, temp_prompts_dir):
        """Test creating a registry instance."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=False)

        assert registry.prompts_dir == temp_prompts_dir
        assert registry.list_templates() == []

    def test_create_registry_auto_scan(self, temp_prompts_dir, sample_coding_template):
        """Test that auto_scan loads templates on creation."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)

        templates = registry.list_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "coding_prompt"

    def test_create_registry_missing_dir(self):
        """Test creating registry with missing directory."""
        registry = TemplateRegistry("/nonexistent/path", auto_scan=True)
        assert registry.list_templates() == []


# =============================================================================
# Test: Template Scanning
# =============================================================================

class TestTemplateScanning:
    """Tests for scanning prompts directory."""

    def test_scan_finds_templates(self, temp_prompts_dir, sample_coding_template, sample_testing_template):
        """Test that scan finds all .md files."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=False)
        count = registry.scan()

        assert count == 2
        assert len(registry.list_templates()) == 2

    def test_scan_ignores_hidden_files(self, temp_prompts_dir):
        """Test that hidden files are ignored."""
        hidden = temp_prompts_dir / ".hidden.md"
        hidden.write_text("Hidden content")
        normal = temp_prompts_dir / "normal.md"
        normal.write_text("Normal content")

        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
        templates = registry.list_templates()

        assert len(templates) == 1
        assert templates[0]["name"] == "normal"

    def test_scan_only_md_files(self, temp_prompts_dir):
        """Test that only .md files are loaded."""
        (temp_prompts_dir / "template.md").write_text("Markdown")
        (temp_prompts_dir / "other.txt").write_text("Text file")
        (temp_prompts_dir / "config.json").write_text("{}")

        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
        assert len(registry.list_templates()) == 1


# =============================================================================
# Test: Template Indexing
# =============================================================================

class TestTemplateIndexing:
    """Tests for template indexing by task_type and name."""

    def test_index_by_task_type(self, registry_with_templates):
        """Test templates are indexed by task_type."""
        task_types = registry_with_templates.list_task_types()

        assert "coding" in task_types
        assert "testing" in task_types

    def test_index_by_name(self, registry_with_templates):
        """Test templates can be found by name."""
        template = registry_with_templates.get_template(name="coding_prompt")

        assert template is not None
        assert template.metadata.task_type == "coding"

    def test_index_by_name_without_suffix(self, registry_with_templates):
        """Test templates can be found by name without _prompt suffix."""
        template = registry_with_templates.get_template(name="coding")

        assert template is not None
        assert template.metadata.task_type == "coding"

    def test_infer_task_type_from_filename(self, temp_prompts_dir):
        """Test task_type is inferred from filename when not in metadata."""
        content = """## Coding stuff
This is a coding template without metadata.
"""
        (temp_prompts_dir / "coding_agent.md").write_text(content)

        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
        template = registry.get_template(name="coding_agent")

        assert template is not None
        assert template.metadata.task_type == "coding"


# =============================================================================
# Test: get_template()
# =============================================================================

class TestGetTemplate:
    """Tests for get_template method."""

    def test_get_template_by_task_type(self, registry_with_templates):
        """Test getting template by task_type."""
        template = registry_with_templates.get_template(task_type="coding")

        assert template is not None
        assert template.metadata.task_type == "coding"
        assert "feature_get_by_id" in template.metadata.required_tools

    def test_get_template_by_name(self, registry_with_templates):
        """Test getting template by name."""
        template = registry_with_templates.get_template(name="testing_prompt")

        assert template is not None
        assert template.metadata.task_type == "testing"

    def test_get_template_not_found_returns_none(self, registry_with_templates):
        """Test that missing template returns None when use_fallback=True."""
        template = registry_with_templates.get_template(task_type="nonexistent")
        assert template is None

    def test_get_template_not_found_raises(self, registry_with_templates):
        """Test that missing template raises when use_fallback=False."""
        with pytest.raises(TemplateNotFoundError) as exc_info:
            registry_with_templates.get_template(task_type="nonexistent", use_fallback=False)

        assert exc_info.value.identifier == "nonexistent"

    def test_get_template_by_path(self, registry_with_templates, sample_coding_template):
        """Test loading template directly by path."""
        template = registry_with_templates.get_template_by_path(sample_coding_template)

        assert template is not None
        assert template.path == sample_coding_template


# =============================================================================
# Test: interpolate() Method
# =============================================================================

class TestRegistryInterpolate:
    """Tests for registry.interpolate() method."""

    def test_interpolate_template_object(self, registry_with_templates):
        """Test interpolating a Template object."""
        template = registry_with_templates.get_template(task_type="coding")

        result = registry_with_templates.interpolate(template, {
            "feature_id": 42,
            "project_name": "TestProject",
            "objective": "Implement login",
        })

        assert "feature 42" in result
        assert "TestProject" in result
        assert "Implement login" in result

    def test_interpolate_string_content(self, registry_with_templates):
        """Test interpolating a raw string."""
        content = "Hello, {{name}}!"
        result = registry_with_templates.interpolate(content, {"name": "World"})

        assert result == "Hello, World!"


# =============================================================================
# Test: Caching
# =============================================================================

class TestTemplateCaching:
    """Tests for template caching."""

    def test_cache_returns_same_object(self, temp_prompts_dir, sample_coding_template):
        """Test that cache returns same template object."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True, cache_enabled=True)

        template1 = registry.get_template(task_type="coding")
        template2 = registry.get_template(task_type="coding")

        assert template1 is template2

    def test_cache_invalidation_on_file_change(self, temp_prompts_dir, sample_coding_template):
        """Test that cache is invalidated when file changes."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True, cache_enabled=True)

        template1 = registry.get_template(task_type="coding")
        content_hash1 = template1.content_hash

        # Modify the file (need small delay for mtime to change)
        time.sleep(0.1)
        new_content = sample_coding_template.read_text() + "\n# Modified"
        sample_coding_template.write_text(new_content)

        template2 = registry.get_template(task_type="coding")

        assert template2.content_hash != content_hash1

    def test_cache_disabled(self, temp_prompts_dir, sample_coding_template):
        """Test that cache can be disabled."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True, cache_enabled=False)

        template1 = registry.get_template(task_type="coding")
        template2 = registry.get_template(task_type="coding")

        # With cache disabled, should be different objects
        assert template1 is not template2

    def test_clear_cache(self, registry_with_templates):
        """Test clearing the cache."""
        template1 = registry_with_templates.get_template(task_type="coding")
        registry_with_templates.clear_cache()
        template2 = registry_with_templates.get_template(task_type="coding")

        assert template1 is not template2


# =============================================================================
# Test: Fallback Template
# =============================================================================

class TestFallbackTemplate:
    """Tests for fallback template functionality."""

    def test_set_fallback_template(self, registry_with_templates):
        """Test setting a fallback template."""
        coding_template = registry_with_templates.get_template(task_type="coding")
        registry_with_templates.set_fallback_template(coding_template)

        # Now requesting missing template should return fallback
        result = registry_with_templates.get_template(task_type="nonexistent")

        assert result is coding_template

    def test_disable_fallback(self, registry_with_templates):
        """Test disabling fallback."""
        coding_template = registry_with_templates.get_template(task_type="coding")
        registry_with_templates.set_fallback_template(coding_template)
        registry_with_templates.set_fallback_template(None)

        result = registry_with_templates.get_template(task_type="nonexistent")
        assert result is None


# =============================================================================
# Test: Template Metadata
# =============================================================================

class TestTemplateMetadata:
    """Tests for template metadata extraction."""

    def test_metadata_required_tools(self, registry_with_templates):
        """Test extracting required_tools from metadata."""
        template = registry_with_templates.get_template(task_type="coding")

        assert "feature_get_by_id" in template.metadata.required_tools
        assert "feature_mark_passing" in template.metadata.required_tools

    def test_metadata_default_budget(self, registry_with_templates):
        """Test extracting default budget values."""
        template = registry_with_templates.get_template(task_type="coding")

        assert template.metadata.default_max_turns == 100
        assert template.metadata.default_timeout_seconds == 3600

    def test_metadata_icon(self, registry_with_templates):
        """Test extracting icon from metadata."""
        template = registry_with_templates.get_template(task_type="coding")
        assert template.metadata.icon == "code"

    def test_auto_detect_variables(self, temp_prompts_dir, no_frontmatter_template):
        """Test that variables are auto-detected from content."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
        template = registry.get_template(name="simple")

        assert "name" in template.metadata.variables


# =============================================================================
# Test: Listing Functions
# =============================================================================

class TestListingFunctions:
    """Tests for list_templates and related functions."""

    def test_list_templates(self, registry_with_templates):
        """Test listing all templates."""
        templates = registry_with_templates.list_templates()

        assert len(templates) == 2
        names = [t["name"] for t in templates]
        assert "coding_prompt" in names
        assert "testing_prompt" in names

    def test_list_task_types(self, registry_with_templates):
        """Test listing all task types."""
        task_types = registry_with_templates.list_task_types()

        assert set(task_types) == {"coding", "testing"}

    def test_get_templates_for_task_type(self, registry_with_templates):
        """Test getting all templates for a task type."""
        templates = registry_with_templates.get_templates_for_task_type("coding")

        assert len(templates) == 1
        assert templates[0].metadata.task_type == "coding"


# =============================================================================
# Test: Refresh and Rescan
# =============================================================================

class TestRefresh:
    """Tests for refresh functionality."""

    def test_refresh_picks_up_new_files(self, temp_prompts_dir, sample_coding_template):
        """Test that refresh picks up newly added files."""
        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
        assert len(registry.list_templates()) == 1

        # Add a new template
        new_template = temp_prompts_dir / "new_template.md"
        new_template.write_text("---\ntask_type: audit\n---\nNew content")

        count = registry.refresh()

        assert count == 2
        assert len(registry.list_templates()) == 2


# =============================================================================
# Test: Template to_dict()
# =============================================================================

class TestTemplateToDict:
    """Tests for Template.to_dict() method."""

    def test_to_dict_structure(self, registry_with_templates):
        """Test that to_dict returns expected structure."""
        template = registry_with_templates.get_template(task_type="coding")
        data = template.to_dict()

        assert "path" in data
        assert "content_hash" in data
        assert "loaded_at" in data
        assert "metadata" in data

        metadata = data["metadata"]
        assert "task_type" in metadata
        assert "required_tools" in metadata
        assert "default_max_turns" in metadata


# =============================================================================
# Test: Module-level Singleton
# =============================================================================

class TestModuleSingleton:
    """Tests for module-level singleton registry."""

    def test_get_template_registry_returns_same_instance(self, temp_prompts_dir):
        """Test that get_template_registry returns singleton."""
        reset_template_registry()  # Ensure clean state

        registry1 = get_template_registry(temp_prompts_dir)
        registry2 = get_template_registry()

        assert registry1 is registry2

    def test_reset_template_registry(self, temp_prompts_dir):
        """Test that reset clears the singleton."""
        reset_template_registry()
        registry1 = get_template_registry(temp_prompts_dir)

        reset_template_registry()
        registry2 = get_template_registry(temp_prompts_dir)

        assert registry1 is not registry2


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_template_with_invalid_yaml(self, temp_prompts_dir):
        """Test handling template with invalid YAML in front matter."""
        content = """---
invalid: [yaml: syntax
---
Content
"""
        (temp_prompts_dir / "invalid.md").write_text(content)

        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)

        # Should still load, just with empty metadata
        template = registry.get_template(name="invalid")
        assert template is not None

    def test_empty_template_file(self, temp_prompts_dir):
        """Test handling empty template file."""
        (temp_prompts_dir / "empty.md").write_text("")

        registry = TemplateRegistry(temp_prompts_dir, auto_scan=True)
        template = registry.get_template(name="empty")

        assert template is not None
        assert template.content == ""

    def test_thread_safety(self, registry_with_templates):
        """Test that registry operations are thread-safe."""
        import threading
        results = []

        def get_template():
            template = registry_with_templates.get_template(task_type="coding")
            results.append(template is not None)

        threads = [threading.Thread(target=get_template) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)

    def test_get_template_by_path_not_found(self, registry_with_templates):
        """Test error when getting template by nonexistent path."""
        with pytest.raises(FileNotFoundError):
            registry_with_templates.get_template_by_path("/nonexistent/path.md")


# =============================================================================
# Test: Integration with Real Templates
# =============================================================================

class TestRealTemplates:
    """Tests using the actual prompts/ directory if available."""

    @pytest.fixture
    def real_registry(self):
        """Try to create registry with real prompts directory."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        if prompts_dir.exists():
            return TemplateRegistry(prompts_dir, auto_scan=True)
        pytest.skip("Real prompts directory not found")

    def test_real_templates_load(self, real_registry):
        """Test that real templates load successfully."""
        templates = real_registry.list_templates()
        assert len(templates) > 0

    def test_real_coding_template(self, real_registry):
        """Test that coding template exists and has expected structure."""
        template = real_registry.get_template(name="coding")
        if template:
            assert template.content
            assert "CODING" in template.content.upper()
