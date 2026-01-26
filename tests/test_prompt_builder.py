"""
Tests for Prompt Builder
========================

Comprehensive tests for the prompt_builder module, specifically
testing Feature #43: Tool Hints System Prompt Injection.

Test Coverage:
- extract_tool_hints: Extraction from tool_policy
- format_tool_hints_as_markdown: Markdown formatting
- build_system_prompt: Full prompt construction
- inject_tool_hints_into_prompt: Injection into existing prompts
"""

import pytest

from api.prompt_builder import (
    build_system_prompt,
    extract_tool_hints,
    format_tool_hints_as_markdown,
    inject_tool_hints_into_prompt,
)


class TestExtractToolHints:
    """Tests for extract_tool_hints function."""

    def test_extract_from_none(self):
        """Step 1: Extract tool_hints dict from spec.tool_policy - handles None."""
        result = extract_tool_hints(None)
        assert result == {}

    def test_extract_from_empty_dict(self):
        """Extract from empty tool_policy."""
        result = extract_tool_hints({})
        assert result == {}

    def test_extract_from_policy_without_hints(self):
        """Extract from tool_policy without tool_hints key."""
        policy = {
            "policy_version": "v1",
            "allowed_tools": ["Read", "Glob"],
            "forbidden_patterns": [],
        }
        result = extract_tool_hints(policy)
        assert result == {}

    def test_extract_from_policy_with_empty_hints(self):
        """Extract from tool_policy with empty tool_hints."""
        policy = {
            "policy_version": "v1",
            "tool_hints": {},
        }
        result = extract_tool_hints(policy)
        assert result == {}

    def test_extract_single_hint(self):
        """Extract a single tool hint."""
        policy = {
            "tool_hints": {
                "feature_mark_passing": "Call only after verification"
            }
        }
        result = extract_tool_hints(policy)
        assert result == {"feature_mark_passing": "Call only after verification"}

    def test_extract_multiple_hints(self):
        """Extract multiple tool hints."""
        policy = {
            "tool_hints": {
                "Read": "Use for reading files only",
                "Bash": "Avoid destructive commands",
                "Write": "Always backup before writing",
            }
        }
        result = extract_tool_hints(policy)
        assert len(result) == 3
        assert result["Read"] == "Use for reading files only"
        assert result["Bash"] == "Avoid destructive commands"
        assert result["Write"] == "Always backup before writing"

    def test_extract_ignores_none_values(self):
        """Ignores hints with None values."""
        policy = {
            "tool_hints": {
                "Read": "Valid hint",
                "Bash": None,
            }
        }
        result = extract_tool_hints(policy)
        assert result == {"Read": "Valid hint"}

    def test_extract_handles_non_dict_policy(self):
        """Handles non-dict tool_policy gracefully."""
        result = extract_tool_hints("not a dict")
        assert result == {}

    def test_extract_handles_non_dict_hints(self):
        """Handles non-dict tool_hints gracefully."""
        policy = {"tool_hints": "not a dict"}
        result = extract_tool_hints(policy)
        assert result == {}

    def test_extract_converts_values_to_string(self):
        """Converts non-string values to strings."""
        policy = {
            "tool_hints": {
                "Read": 123,  # Number
                "Bash": True,  # Boolean
            }
        }
        result = extract_tool_hints(policy)
        assert result["Read"] == "123"
        assert result["Bash"] == "True"


class TestFormatToolHintsAsMarkdown:
    """Tests for format_tool_hints_as_markdown function."""

    def test_format_empty_hints(self):
        """Step 2: Format hints as markdown guidelines - empty case."""
        result = format_tool_hints_as_markdown({})
        assert result == ""

    def test_format_single_hint(self):
        """Format a single tool hint as markdown."""
        hints = {"feature_mark_passing": "Call only after verification"}
        result = format_tool_hints_as_markdown(hints)

        assert "## Tool Usage Guidelines" in result
        assert "- **feature_mark_passing**: Call only after verification" in result

    def test_format_multiple_hints(self):
        """Format multiple hints with sorted order."""
        hints = {
            "Write": "Always backup",
            "Bash": "No destructive commands",
            "Read": "Files only",
        }
        result = format_tool_hints_as_markdown(hints)

        # Check header
        assert result.startswith("## Tool Usage Guidelines")

        # Check all hints present
        assert "- **Bash**: No destructive commands" in result
        assert "- **Read**: Files only" in result
        assert "- **Write**: Always backup" in result

        # Check sorted order (Bash < Read < Write)
        bash_pos = result.index("Bash")
        read_pos = result.index("Read")
        write_pos = result.index("Write")
        assert bash_pos < read_pos < write_pos

    def test_format_preserves_hint_content(self):
        """Preserves special characters in hints."""
        hints = {
            "Bash": "Avoid `rm -rf /` and similar"
        }
        result = format_tool_hints_as_markdown(hints)
        assert "Avoid `rm -rf /` and similar" in result

    def test_format_matches_example(self):
        """Step 4: Example format from feature description."""
        hints = {"feature_mark_passing": "Call only after verification"}
        result = format_tool_hints_as_markdown(hints)

        # Should match: ## Tool Usage Guidelines - feature_mark_passing: Call only after verification
        assert "## Tool Usage Guidelines" in result
        assert "feature_mark_passing" in result
        assert "Call only after verification" in result


class TestBuildSystemPrompt:
    """Tests for build_system_prompt function."""

    def test_build_with_objective_only(self):
        """Build prompt with only objective."""
        prompt = build_system_prompt("Implement user authentication")

        assert "# Objective" in prompt
        assert "Implement user authentication" in prompt

    def test_build_with_task_type(self):
        """Build prompt with task type."""
        prompt = build_system_prompt(
            "Implement login feature",
            task_type="coding"
        )

        assert "**Task Type:** coding" in prompt

    def test_build_with_context(self):
        """Build prompt with context data."""
        context = {
            "feature_id": 42,
            "file_paths": ["src/auth.py", "src/login.py"],
        }
        prompt = build_system_prompt(
            "Implement feature",
            context=context,
        )

        assert "## Context" in prompt
        assert "Feature Id" in prompt or "42" in prompt

    def test_build_with_tool_hints(self):
        """Step 3: Append to system prompt in dedicated section."""
        tool_policy = {
            "policy_version": "v1",
            "tool_hints": {
                "feature_mark_passing": "Call only after verification",
                "Bash": "Avoid destructive commands",
            }
        }
        prompt = build_system_prompt(
            "Implement feature",
            tool_policy=tool_policy,
        )

        # Check tool hints section is appended
        assert "## Tool Usage Guidelines" in prompt
        assert "feature_mark_passing" in prompt
        assert "Call only after verification" in prompt
        assert "Bash" in prompt
        assert "Avoid destructive commands" in prompt

    def test_build_without_tool_hints_when_disabled(self):
        """Can disable tool hints injection."""
        tool_policy = {
            "tool_hints": {"Read": "Hint text"}
        }
        prompt = build_system_prompt(
            "Objective",
            tool_policy=tool_policy,
            include_tool_hints=False,
        )

        assert "## Tool Usage Guidelines" not in prompt
        assert "Read" not in prompt

    def test_build_complete_prompt(self):
        """Build a complete prompt with all fields."""
        prompt = build_system_prompt(
            "Implement login feature with OAuth support",
            context={"feature_id": 42},
            tool_policy={
                "tool_hints": {
                    "feature_mark_passing": "Only after full testing"
                }
            },
            task_type="coding",
        )

        # All sections present
        assert "# Objective" in prompt
        assert "Implement login feature with OAuth support" in prompt
        assert "**Task Type:** coding" in prompt
        assert "## Context" in prompt
        assert "## Tool Usage Guidelines" in prompt
        assert "feature_mark_passing" in prompt


class TestInjectToolHintsIntoPrompt:
    """Tests for inject_tool_hints_into_prompt function."""

    def test_inject_into_simple_prompt(self):
        """Inject hints into a simple existing prompt."""
        base_prompt = "You are a coding assistant."
        tool_policy = {
            "tool_hints": {"Bash": "No destructive commands"}
        }

        result = inject_tool_hints_into_prompt(base_prompt, tool_policy)

        assert "You are a coding assistant." in result
        assert "## Tool Usage Guidelines" in result
        assert "Bash" in result

    def test_inject_preserves_original(self):
        """Original prompt content is preserved."""
        base_prompt = """You are an expert developer.

Follow best practices.
Write clean code."""

        tool_policy = {"tool_hints": {"Read": "Files only"}}

        result = inject_tool_hints_into_prompt(base_prompt, tool_policy)

        assert "You are an expert developer." in result
        assert "Follow best practices." in result
        assert "Write clean code." in result

    def test_inject_with_none_policy(self):
        """Returns unchanged prompt when policy is None."""
        base_prompt = "Original prompt"
        result = inject_tool_hints_into_prompt(base_prompt, None)
        assert result == base_prompt

    def test_inject_with_empty_hints(self):
        """Returns unchanged prompt when no hints."""
        base_prompt = "Original prompt"
        tool_policy = {"tool_hints": {}}
        result = inject_tool_hints_into_prompt(base_prompt, tool_policy)
        assert result == base_prompt

    def test_inject_adds_proper_spacing(self):
        """Hints section has proper spacing from base prompt."""
        base_prompt = "Base prompt."
        tool_policy = {"tool_hints": {"Read": "Hint"}}

        result = inject_tool_hints_into_prompt(base_prompt, tool_policy)

        # Should have blank line between base and hints
        assert "Base prompt.\n\n## Tool Usage Guidelines" in result

    def test_inject_handles_trailing_whitespace(self):
        """Handles prompts with trailing whitespace."""
        base_prompt = "Base prompt.   \n\n\n"
        tool_policy = {"tool_hints": {"Read": "Hint"}}

        result = inject_tool_hints_into_prompt(base_prompt, tool_policy)

        # Should not have excessive whitespace
        assert "Base prompt.\n\n## Tool Usage Guidelines" in result


class TestFeature43Integration:
    """Integration tests matching Feature #43 verification steps."""

    def test_step1_extract_tool_hints_dict(self):
        """Step 1: Extract tool_hints dict from spec.tool_policy."""
        # Simulating a real tool_policy from AgentSpec
        tool_policy = {
            "policy_version": "v1",
            "allowed_tools": [
                "mcp__features__feature_get_by_id",
                "mcp__features__feature_mark_passing",
                "Read",
                "Glob",
            ],
            "forbidden_patterns": ["rm -rf", "DROP TABLE"],
            "tool_hints": {
                "feature_mark_passing": "Call only after verification",
                "Bash": "Avoid using rm, mv, or other destructive commands",
            }
        }

        hints = extract_tool_hints(tool_policy)

        assert isinstance(hints, dict)
        assert len(hints) == 2
        assert hints["feature_mark_passing"] == "Call only after verification"
        assert "Bash" in hints

    def test_step2_format_hints_as_markdown_guidelines(self):
        """Step 2: Format hints as markdown guidelines."""
        hints = {
            "feature_mark_passing": "Call only after verification",
            "Bash": "Avoid destructive commands",
        }

        markdown = format_tool_hints_as_markdown(hints)

        # Should be valid markdown
        assert markdown.startswith("## Tool Usage Guidelines")
        assert "- **" in markdown  # Bullet points with bold tool names
        assert "feature_mark_passing" in markdown
        assert "Bash" in markdown

    def test_step3_append_to_system_prompt_in_dedicated_section(self):
        """Step 3: Append to system prompt in dedicated section."""
        objective = "Implement user authentication feature"
        tool_policy = {
            "tool_hints": {
                "feature_mark_passing": "Call only after verification"
            }
        }

        prompt = build_system_prompt(objective, tool_policy=tool_policy)

        # Verify dedicated section exists
        assert "## Tool Usage Guidelines" in prompt

        # Verify it comes after objective
        objective_pos = prompt.index("Implement user authentication")
        guidelines_pos = prompt.index("## Tool Usage Guidelines")
        assert guidelines_pos > objective_pos

    def test_step4_example_format(self):
        """Step 4: Example: ## Tool Usage Guidelines - feature_mark_passing: Call only after verification."""
        tool_policy = {
            "tool_hints": {
                "feature_mark_passing": "Call only after verification"
            }
        }

        prompt = build_system_prompt(
            "Test objective",
            tool_policy=tool_policy,
        )

        # Verify the expected format
        assert "## Tool Usage Guidelines" in prompt
        assert "feature_mark_passing" in prompt
        assert "Call only after verification" in prompt

        # The format should be markdown bullet with bold tool name
        assert "- **feature_mark_passing**:" in prompt


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_unicode_in_hints(self):
        """Handles unicode characters in hints."""
        hints = {
            "Translate": "Translate text to \u65e5\u672c\u8a9e (Japanese)"
        }
        result = format_tool_hints_as_markdown(hints)
        assert "\u65e5\u672c\u8a9e" in result

    def test_long_hint_text(self):
        """Handles long hint text."""
        long_hint = "A" * 1000
        hints = {"Tool": long_hint}
        result = format_tool_hints_as_markdown(hints)
        assert long_hint in result

    def test_special_characters_in_tool_name(self):
        """Handles special characters in tool names."""
        hints = {
            "mcp__features__feature_mark_passing": "Complex tool name"
        }
        result = format_tool_hints_as_markdown(hints)
        assert "mcp__features__feature_mark_passing" in result

    def test_multiline_hints(self):
        """Handles hints with newlines (should preserve)."""
        hints = {
            "Tool": "Line 1\nLine 2\nLine 3"
        }
        result = format_tool_hints_as_markdown(hints)
        assert "Line 1\nLine 2\nLine 3" in result

    def test_empty_objective_with_hints(self):
        """Builds prompt with empty objective but valid hints."""
        prompt = build_system_prompt(
            "",
            tool_policy={"tool_hints": {"Read": "Hint"}}
        )
        assert "## Tool Usage Guidelines" in prompt
