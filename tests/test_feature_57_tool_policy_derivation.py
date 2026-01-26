"""
Tests for Tool Policy Derivation from Task Type (Feature #57)

These tests verify the complete implementation of Feature #57:
1. Define tool sets for each task_type
2. coding: file edit, bash (restricted), feature tools
3. testing: file read, bash (test commands), feature tools
4. documentation: file write, read-only access
5. audit: read-only everything
6. Add standard forbidden_patterns for all types
7. Add task-specific forbidden_patterns
8. Return complete tool_policy structure

Each verification step from the feature description is tested explicitly.
"""

import pytest

from api.tool_policy import (
    STANDARD_FORBIDDEN_PATTERNS,
    TASK_SPECIFIC_FORBIDDEN_PATTERNS,
    TASK_TOOL_HINTS,
    TOOL_SETS,
    derive_tool_policy,
    get_combined_forbidden_patterns,
    get_standard_forbidden_patterns,
    get_supported_task_types,
    get_task_forbidden_patterns,
    get_tool_hints,
    get_tool_set,
)


# =============================================================================
# Step 1: Define tool sets for each task_type
# =============================================================================

class TestStep1DefineToolSetsForEachTaskType:
    """Verify that tool sets are defined for each task type."""

    def test_tool_sets_dict_exists(self):
        """TOOL_SETS dictionary is defined."""
        assert isinstance(TOOL_SETS, dict)
        assert len(TOOL_SETS) > 0

    def test_tool_sets_has_coding(self):
        """coding task_type has a tool set."""
        assert "coding" in TOOL_SETS
        assert isinstance(TOOL_SETS["coding"], list)
        assert len(TOOL_SETS["coding"]) > 0

    def test_tool_sets_has_testing(self):
        """testing task_type has a tool set."""
        assert "testing" in TOOL_SETS
        assert isinstance(TOOL_SETS["testing"], list)
        assert len(TOOL_SETS["testing"]) > 0

    def test_tool_sets_has_documentation(self):
        """documentation task_type has a tool set."""
        assert "documentation" in TOOL_SETS
        assert isinstance(TOOL_SETS["documentation"], list)
        assert len(TOOL_SETS["documentation"]) > 0

    def test_tool_sets_has_audit(self):
        """audit task_type has a tool set."""
        assert "audit" in TOOL_SETS
        assert isinstance(TOOL_SETS["audit"], list)
        assert len(TOOL_SETS["audit"]) > 0

    def test_tool_sets_has_refactoring(self):
        """refactoring task_type has a tool set."""
        assert "refactoring" in TOOL_SETS
        assert isinstance(TOOL_SETS["refactoring"], list)

    def test_tool_sets_has_custom(self):
        """custom task_type has a tool set (fallback)."""
        assert "custom" in TOOL_SETS
        assert isinstance(TOOL_SETS["custom"], list)

    def test_get_supported_task_types_returns_all(self):
        """get_supported_task_types() returns all defined task types."""
        supported = get_supported_task_types()
        assert "coding" in supported
        assert "testing" in supported
        assert "documentation" in supported
        assert "audit" in supported
        assert "refactoring" in supported
        assert "custom" in supported


# =============================================================================
# Step 2: coding: file edit, bash (restricted), feature tools
# =============================================================================

class TestStep2CodingTaskType:
    """Verify coding task_type has file edit, bash, and feature tools."""

    def test_coding_has_file_edit_tools(self):
        """coding has file editing tools (Read, Write, Edit)."""
        tools = get_tool_set("coding")
        assert "Read" in tools
        assert "Write" in tools
        assert "Edit" in tools
        assert "Glob" in tools
        assert "Grep" in tools

    def test_coding_has_bash_tool(self):
        """coding has bash tool (restricted by security.py)."""
        tools = get_tool_set("coding")
        assert "Bash" in tools

    def test_coding_has_feature_tools(self):
        """coding has feature management tools."""
        tools = get_tool_set("coding")
        assert "feature_get_by_id" in tools
        assert "feature_mark_passing" in tools
        assert "feature_mark_failing" in tools
        assert "feature_mark_in_progress" in tools
        assert "feature_skip" in tools
        assert "feature_get_stats" in tools

    def test_coding_has_browser_tools(self):
        """coding has browser automation tools for verification."""
        tools = get_tool_set("coding")
        assert "browser_navigate" in tools
        assert "browser_click" in tools
        assert "browser_type" in tools
        assert "browser_snapshot" in tools
        assert "browser_take_screenshot" in tools

    def test_coding_has_web_research_tools(self):
        """coding has web research tools."""
        tools = get_tool_set("coding")
        assert "WebFetch" in tools
        assert "WebSearch" in tools


# =============================================================================
# Step 3: testing: file read, bash (test commands), feature tools
# =============================================================================

class TestStep3TestingTaskType:
    """Verify testing task_type has file read, bash (test commands), feature tools."""

    def test_testing_has_file_read_tools(self):
        """testing has file read tools (Read, Glob, Grep)."""
        tools = get_tool_set("testing")
        assert "Read" in tools
        assert "Glob" in tools
        assert "Grep" in tools

    def test_testing_does_not_have_write_edit(self):
        """testing should NOT have Write or Edit tools (read-only)."""
        tools = get_tool_set("testing")
        assert "Write" not in tools
        assert "Edit" not in tools

    def test_testing_has_bash_tool(self):
        """testing has bash tool for running tests."""
        tools = get_tool_set("testing")
        assert "Bash" in tools

    def test_testing_has_feature_tools(self):
        """testing has feature management tools (status updates)."""
        tools = get_tool_set("testing")
        assert "feature_get_by_id" in tools
        assert "feature_mark_passing" in tools
        assert "feature_mark_failing" in tools
        assert "feature_get_stats" in tools

    def test_testing_has_browser_tools(self):
        """testing has browser automation tools for verification."""
        tools = get_tool_set("testing")
        assert "browser_navigate" in tools
        assert "browser_click" in tools
        assert "browser_snapshot" in tools
        assert "browser_evaluate" in tools


# =============================================================================
# Step 4: documentation: file write, read-only access
# =============================================================================

class TestStep4DocumentationTaskType:
    """Verify documentation task_type has file write and read-only access."""

    def test_documentation_has_write_tool(self):
        """documentation has Write tool for creating docs."""
        tools = get_tool_set("documentation")
        assert "Write" in tools

    def test_documentation_has_read_tools(self):
        """documentation has read-only code access."""
        tools = get_tool_set("documentation")
        assert "Read" in tools
        assert "Glob" in tools
        assert "Grep" in tools

    def test_documentation_does_not_have_edit_tool(self):
        """documentation should NOT have Edit tool (write new, don't modify code)."""
        tools = get_tool_set("documentation")
        # Note: Edit is for modifying existing files, Write is for creating new ones
        # Documentation might need Edit for doc files, but this tests the feature spec
        assert "Edit" not in tools

    def test_documentation_does_not_have_bash(self):
        """documentation should NOT have bash tool (no execution)."""
        tools = get_tool_set("documentation")
        assert "Bash" not in tools

    def test_documentation_has_web_research_tools(self):
        """documentation has web research tools."""
        tools = get_tool_set("documentation")
        assert "WebFetch" in tools
        assert "WebSearch" in tools


# =============================================================================
# Step 5: audit: read-only everything
# =============================================================================

class TestStep5AuditTaskType:
    """Verify audit task_type has read-only everything."""

    def test_audit_has_read_tools(self):
        """audit has read-only file access."""
        tools = get_tool_set("audit")
        assert "Read" in tools
        assert "Glob" in tools
        assert "Grep" in tools

    def test_audit_does_not_have_write_edit(self):
        """audit should NOT have Write or Edit tools."""
        tools = get_tool_set("audit")
        assert "Write" not in tools
        assert "Edit" not in tools

    def test_audit_does_not_have_bash(self):
        """audit should NOT have Bash tool."""
        tools = get_tool_set("audit")
        assert "Bash" not in tools

    def test_audit_has_read_only_feature_tools(self):
        """audit has read-only feature tools."""
        tools = get_tool_set("audit")
        assert "feature_get_by_id" in tools
        assert "feature_get_stats" in tools
        assert "feature_get_ready" in tools
        assert "feature_get_blocked" in tools
        assert "feature_get_graph" in tools

    def test_audit_does_not_have_feature_mutation_tools(self):
        """audit should NOT have feature mutation tools."""
        tools = get_tool_set("audit")
        assert "feature_mark_passing" not in tools
        assert "feature_mark_failing" not in tools
        assert "feature_skip" not in tools
        assert "feature_create" not in tools

    def test_audit_has_browser_inspection_tools(self):
        """audit has browser tools for inspection only."""
        tools = get_tool_set("audit")
        assert "browser_navigate" in tools
        assert "browser_snapshot" in tools
        assert "browser_take_screenshot" in tools
        assert "browser_console_messages" in tools

    def test_audit_does_not_have_browser_interaction_tools(self):
        """audit should NOT have browser interaction tools."""
        tools = get_tool_set("audit")
        # Click and type allow modification/interaction
        assert "browser_click" not in tools
        assert "browser_type" not in tools


# =============================================================================
# Step 6: Add standard forbidden_patterns for all types
# =============================================================================

class TestStep6StandardForbiddenPatterns:
    """Verify standard forbidden_patterns are defined for all types."""

    def test_standard_forbidden_patterns_exist(self):
        """STANDARD_FORBIDDEN_PATTERNS list exists and is not empty."""
        assert isinstance(STANDARD_FORBIDDEN_PATTERNS, list)
        assert len(STANDARD_FORBIDDEN_PATTERNS) > 0

    def test_standard_patterns_block_rm_rf(self):
        """Standard patterns block rm -rf /."""
        patterns = get_standard_forbidden_patterns()
        # Check that a pattern matches rm -rf /
        pattern_str = " ".join(patterns)
        assert "rm" in pattern_str
        assert "rf" in pattern_str

    def test_standard_patterns_block_drop_table(self):
        """Standard patterns block DROP TABLE."""
        patterns = get_standard_forbidden_patterns()
        pattern_str = " ".join(patterns)
        assert "DROP" in pattern_str
        assert "TABLE" in pattern_str

    def test_standard_patterns_block_chmod_777(self):
        """Standard patterns block chmod 777."""
        patterns = get_standard_forbidden_patterns()
        pattern_str = " ".join(patterns)
        assert "chmod" in pattern_str
        assert "777" in pattern_str

    def test_standard_patterns_block_sudo(self):
        """Standard patterns block sudo."""
        patterns = get_standard_forbidden_patterns()
        pattern_str = " ".join(patterns)
        assert "sudo" in pattern_str

    def test_standard_patterns_block_pipe_to_shell(self):
        """Standard patterns block piping to shell (curl | sh)."""
        patterns = get_standard_forbidden_patterns()
        pattern_str = " ".join(patterns)
        assert "curl" in pattern_str
        assert "wget" in pattern_str
        assert "sh" in pattern_str

    def test_standard_patterns_applied_to_all_task_types(self):
        """Standard patterns are included in all task types."""
        for task_type in get_supported_task_types():
            policy = derive_tool_policy(task_type)
            # All standard patterns should be in the policy
            standard = get_standard_forbidden_patterns()
            for pattern in standard:
                assert pattern in policy["forbidden_patterns"], \
                    f"Standard pattern '{pattern}' missing from {task_type}"


# =============================================================================
# Step 7: Add task-specific forbidden_patterns
# =============================================================================

class TestStep7TaskSpecificForbiddenPatterns:
    """Verify task-specific forbidden_patterns are defined."""

    def test_task_specific_patterns_dict_exists(self):
        """TASK_SPECIFIC_FORBIDDEN_PATTERNS dictionary exists."""
        assert isinstance(TASK_SPECIFIC_FORBIDDEN_PATTERNS, dict)

    def test_coding_specific_patterns(self):
        """coding has task-specific patterns."""
        patterns = get_task_forbidden_patterns("coding")
        assert isinstance(patterns, list)
        # Coding shouldn't delete databases
        pattern_str = " ".join(patterns)
        assert "DROP" in pattern_str or "db" in pattern_str.lower()

    def test_testing_specific_patterns_block_modifications(self):
        """testing has patterns blocking modifications."""
        patterns = get_task_forbidden_patterns("testing")
        pattern_str = " ".join(patterns)
        # Testing should block Write and Edit
        assert "Write" in pattern_str
        assert "Edit" in pattern_str
        # Testing should block rm, mv, cp
        assert "rm" in pattern_str
        assert "mv" in pattern_str or "cp" in pattern_str
        # Testing should block git push/commit
        assert "git" in pattern_str

    def test_refactoring_specific_patterns(self):
        """refactoring has patterns blocking feature status changes."""
        patterns = get_task_forbidden_patterns("refactoring")
        pattern_str = " ".join(patterns)
        assert "feature_mark" in pattern_str

    def test_documentation_specific_patterns(self):
        """documentation has patterns blocking code modifications."""
        patterns = get_task_forbidden_patterns("documentation")
        pattern_str = " ".join(patterns)
        # Shouldn't modify code files
        assert "Edit" in pattern_str or "py" in pattern_str

    def test_audit_specific_patterns_very_restrictive(self):
        """audit has extensive patterns blocking all modifications."""
        patterns = get_task_forbidden_patterns("audit")
        pattern_str = " ".join(patterns)
        # Should block all write operations
        assert "Write" in pattern_str
        assert "Edit" in pattern_str
        assert "Bash" in pattern_str
        assert "feature_mark" in pattern_str

    def test_get_combined_forbidden_patterns(self):
        """get_combined_forbidden_patterns returns standard + task-specific."""
        combined = get_combined_forbidden_patterns("testing")
        standard = get_standard_forbidden_patterns()
        specific = get_task_forbidden_patterns("testing")

        # Combined should include all standard patterns
        for pattern in standard:
            assert pattern in combined

        # Combined should include all specific patterns
        for pattern in specific:
            assert pattern in combined


# =============================================================================
# Step 8: Return complete tool_policy structure
# =============================================================================

class TestStep8ReturnCompleteToolPolicyStructure:
    """Verify derive_tool_policy returns complete tool_policy structure."""

    def test_derive_tool_policy_returns_dict(self):
        """derive_tool_policy returns a dictionary."""
        policy = derive_tool_policy("coding")
        assert isinstance(policy, dict)

    def test_policy_has_policy_version(self):
        """Policy includes policy_version field."""
        policy = derive_tool_policy("coding")
        assert "policy_version" in policy
        assert policy["policy_version"] == "v1"

    def test_policy_has_allowed_tools(self):
        """Policy includes allowed_tools list."""
        policy = derive_tool_policy("coding")
        assert "allowed_tools" in policy
        assert isinstance(policy["allowed_tools"], list)
        assert len(policy["allowed_tools"]) > 0

    def test_policy_has_forbidden_patterns(self):
        """Policy includes forbidden_patterns list."""
        policy = derive_tool_policy("coding")
        assert "forbidden_patterns" in policy
        assert isinstance(policy["forbidden_patterns"], list)
        assert len(policy["forbidden_patterns"]) > 0

    def test_policy_has_tool_hints(self):
        """Policy includes tool_hints dictionary."""
        policy = derive_tool_policy("coding")
        assert "tool_hints" in policy
        assert isinstance(policy["tool_hints"], dict)

    def test_policy_has_task_type(self):
        """Policy includes task_type for reference."""
        policy = derive_tool_policy("coding")
        assert "task_type" in policy
        assert policy["task_type"] == "coding"

    def test_policy_supports_allowed_directories(self):
        """Policy supports optional allowed_directories."""
        policy = derive_tool_policy(
            "coding",
            allowed_directories=["/home/user/project", "/tmp"]
        )
        assert "allowed_directories" in policy
        assert policy["allowed_directories"] == ["/home/user/project", "/tmp"]

    def test_policy_supports_additional_tools(self):
        """Policy supports adding additional tools."""
        policy = derive_tool_policy(
            "testing",
            additional_tools=["custom_tool", "another_tool"]
        )
        assert "custom_tool" in policy["allowed_tools"]
        assert "another_tool" in policy["allowed_tools"]

    def test_policy_supports_additional_forbidden_patterns(self):
        """Policy supports adding additional forbidden patterns."""
        policy = derive_tool_policy(
            "coding",
            additional_forbidden_patterns=["custom_pattern", "another_pattern"]
        )
        assert "custom_pattern" in policy["forbidden_patterns"]
        assert "another_pattern" in policy["forbidden_patterns"]

    def test_policy_supports_additional_tool_hints(self):
        """Policy supports adding additional tool hints."""
        policy = derive_tool_policy(
            "coding",
            additional_tool_hints={"custom_tool": "Custom hint"}
        )
        assert "custom_tool" in policy["tool_hints"]
        assert policy["tool_hints"]["custom_tool"] == "Custom hint"

    def test_policy_no_duplicate_patterns(self):
        """Policy has no duplicate forbidden patterns."""
        policy = derive_tool_policy(
            "coding",
            additional_forbidden_patterns=[STANDARD_FORBIDDEN_PATTERNS[0]]  # Add duplicate
        )
        # Count occurrences of first standard pattern
        count = policy["forbidden_patterns"].count(STANDARD_FORBIDDEN_PATTERNS[0])
        assert count == 1, "Duplicate pattern found"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the complete feature."""

    def test_coding_policy_complete(self):
        """coding policy is complete and valid."""
        policy = derive_tool_policy("coding")

        # Has all required fields
        assert "policy_version" in policy
        assert "allowed_tools" in policy
        assert "forbidden_patterns" in policy
        assert "tool_hints" in policy
        assert "task_type" in policy

        # Allowed tools include expected coding tools
        assert "Read" in policy["allowed_tools"]
        assert "Write" in policy["allowed_tools"]
        assert "Edit" in policy["allowed_tools"]
        assert "Bash" in policy["allowed_tools"]
        assert "feature_mark_passing" in policy["allowed_tools"]

        # Forbidden patterns include standard security patterns
        assert any("rm" in p for p in policy["forbidden_patterns"])
        assert any("DROP" in p for p in policy["forbidden_patterns"])

    def test_testing_policy_complete(self):
        """testing policy is complete and valid."""
        policy = derive_tool_policy("testing")

        # Has read access but not write/edit
        assert "Read" in policy["allowed_tools"]
        assert "Bash" in policy["allowed_tools"]
        assert "Write" not in policy["allowed_tools"]
        assert "Edit" not in policy["allowed_tools"]

        # Has task-specific patterns blocking modifications
        assert any("Write" in p for p in policy["forbidden_patterns"])
        assert any("Edit" in p for p in policy["forbidden_patterns"])

    def test_audit_policy_very_restrictive(self):
        """audit policy is very restrictive (read-only)."""
        policy = derive_tool_policy("audit")

        # Only has read tools
        assert "Read" in policy["allowed_tools"]
        assert "Glob" in policy["allowed_tools"]
        assert "Grep" in policy["allowed_tools"]

        # No write, edit, or bash
        assert "Write" not in policy["allowed_tools"]
        assert "Edit" not in policy["allowed_tools"]
        assert "Bash" not in policy["allowed_tools"]

        # Many forbidden patterns
        assert len(policy["forbidden_patterns"]) > len(STANDARD_FORBIDDEN_PATTERNS)

    def test_unknown_task_type_falls_back_to_custom(self):
        """Unknown task types fall back to custom."""
        policy = derive_tool_policy("unknown_type")
        assert policy["task_type"] == "custom"

    def test_case_insensitive_task_type(self):
        """Task type matching is case-insensitive."""
        policy1 = derive_tool_policy("CODING")
        policy2 = derive_tool_policy("Coding")
        policy3 = derive_tool_policy("coding")

        assert policy1["task_type"] == "coding"
        assert policy2["task_type"] == "coding"
        assert policy3["task_type"] == "coding"

    def test_task_type_whitespace_handling(self):
        """Task type handles leading/trailing whitespace."""
        policy = derive_tool_policy("  coding  ")
        assert policy["task_type"] == "coding"


# =============================================================================
# Tool Hints Tests
# =============================================================================

class TestToolHints:
    """Tests for tool hints functionality."""

    def test_coding_hints_exist(self):
        """coding has tool hints."""
        hints = get_tool_hints("coding")
        assert isinstance(hints, dict)
        assert len(hints) > 0

    def test_coding_hints_for_feature_mark_passing(self):
        """coding has hint for feature_mark_passing."""
        hints = get_tool_hints("coding")
        assert "feature_mark_passing" in hints
        assert "verification" in hints["feature_mark_passing"].lower()

    def test_testing_hints_exist(self):
        """testing has tool hints."""
        hints = get_tool_hints("testing")
        assert isinstance(hints, dict)
        assert len(hints) > 0

    def test_hints_are_copies_not_references(self):
        """get_tool_hints returns copies, not references."""
        hints1 = get_tool_hints("coding")
        hints2 = get_tool_hints("coding")

        # Modify hints1
        hints1["test_key"] = "test_value"

        # hints2 should not be affected
        assert "test_key" not in hints2


# =============================================================================
# Helper Functions Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_tool_set_returns_copy(self):
        """get_tool_set returns a copy, not reference."""
        tools1 = get_tool_set("coding")
        tools2 = get_tool_set("coding")

        # Modify tools1
        tools1.append("test_tool")

        # tools2 should not be affected
        assert "test_tool" not in tools2

    def test_get_standard_forbidden_patterns_returns_copy(self):
        """get_standard_forbidden_patterns returns a copy."""
        patterns1 = get_standard_forbidden_patterns()
        patterns2 = get_standard_forbidden_patterns()

        # Modify patterns1
        patterns1.append("test_pattern")

        # patterns2 should not be affected
        assert "test_pattern" not in patterns2

    def test_get_task_forbidden_patterns_returns_copy(self):
        """get_task_forbidden_patterns returns a copy."""
        patterns1 = get_task_forbidden_patterns("coding")
        patterns2 = get_task_forbidden_patterns("coding")

        # Modify patterns1
        patterns1.append("test_pattern")

        # patterns2 should not be affected
        assert "test_pattern" not in patterns2

    def test_get_task_forbidden_patterns_empty_for_custom(self):
        """custom task type has no additional forbidden patterns."""
        patterns = get_task_forbidden_patterns("custom")
        assert patterns == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
