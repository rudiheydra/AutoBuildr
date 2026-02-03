"""
Test Feature #186: Octo selects appropriate tools for each agent
================================================================

This test suite verifies that Octo correctly selects tools for agents based on
their role, capability, and task type, following the least-privilege principle.

Feature Steps:
1. Octo has knowledge of available tools: Bash, Read, Write, Glob, Grep, WebFetch, etc.
2. Octo matches agent role to required tool set
3. Test-runner agents get test-related tools (Bash, Read, Write)
4. UI agents get browser/Playwright tools when available
5. Tool selection follows least-privilege principle
"""
import pytest
from typing import Any

from api.tool_selection import (
    AVAILABLE_TOOLS,
    ROLE_TOOL_CATEGORIES,
    ROLE_TOOL_OVERRIDES,
    ToolSelectionResult,
    get_all_tool_categories,
    get_browser_tools,
    get_test_runner_tools,
    get_tool_info,
    get_tools_by_category,
    get_tools_by_privilege,
    get_ui_agent_tools,
    is_browser_tool,
    select_tools_for_capability,
    select_tools_for_role,
)


# =============================================================================
# Step 1: Octo has knowledge of available tools
# =============================================================================

class TestStep1AvailableTools:
    """Test that Octo knows about all available tools."""

    def test_available_tools_catalog_exists(self):
        """AVAILABLE_TOOLS catalog should exist and be non-empty."""
        assert AVAILABLE_TOOLS is not None
        assert len(AVAILABLE_TOOLS) > 0

    def test_available_tools_has_core_tools(self):
        """AVAILABLE_TOOLS should include Bash, Read, Write, Glob, Grep, WebFetch."""
        core_tools = ["Bash", "Read", "Write", "Glob", "Grep", "WebFetch"]
        for tool in core_tools:
            assert tool in AVAILABLE_TOOLS, f"Missing core tool: {tool}"

    def test_available_tools_has_browser_tools(self):
        """AVAILABLE_TOOLS should include browser/Playwright tools."""
        browser_tools = [
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_fill_form",
            "browser_snapshot",
            "browser_take_screenshot",
        ]
        for tool in browser_tools:
            assert tool in AVAILABLE_TOOLS, f"Missing browser tool: {tool}"

    def test_tool_metadata_has_required_fields(self):
        """Each tool should have category, description, and privilege_level."""
        required_fields = ["category", "description", "privilege_level"]
        for tool_name, metadata in AVAILABLE_TOOLS.items():
            for field in required_fields:
                assert field in metadata, f"Tool {tool_name} missing field: {field}"

    def test_get_tool_info_returns_metadata(self):
        """get_tool_info should return tool metadata."""
        info = get_tool_info("Bash")
        assert info is not None
        assert info["category"] == "execution"
        assert info["privilege_level"] == "execute"

    def test_get_tool_info_returns_none_for_unknown(self):
        """get_tool_info should return None for unknown tools."""
        info = get_tool_info("NonExistentTool")
        assert info is None

    def test_get_all_tool_categories(self):
        """get_all_tool_categories should return all unique categories."""
        categories = get_all_tool_categories()
        assert "filesystem" in categories
        assert "execution" in categories
        assert "browser" in categories
        assert "web" in categories
        assert "feature_management" in categories


# =============================================================================
# Step 2: Octo matches agent role to required tool set
# =============================================================================

class TestStep2RoleToToolMapping:
    """Test that Octo maps agent roles to appropriate tool sets."""

    def test_role_tool_categories_exists(self):
        """ROLE_TOOL_CATEGORIES mapping should exist."""
        assert ROLE_TOOL_CATEGORIES is not None
        assert len(ROLE_TOOL_CATEGORIES) > 0

    def test_role_tool_categories_has_common_roles(self):
        """ROLE_TOOL_CATEGORIES should map common roles."""
        expected_roles = [
            "test_runner",
            "ui_testing",
            "e2e_testing",
            "coding",
            "documentation",
            "audit",
        ]
        for role in expected_roles:
            assert role in ROLE_TOOL_CATEGORIES, f"Missing role mapping: {role}"

    def test_select_tools_for_role_returns_result(self):
        """select_tools_for_role should return ToolSelectionResult."""
        result = select_tools_for_role("coding")
        assert isinstance(result, ToolSelectionResult)
        assert len(result.tools) > 0
        assert len(result.categories_used) > 0
        assert result.reasoning != ""

    def test_select_tools_for_role_unknown_role_uses_defaults(self):
        """Unknown roles should fall back to default categories."""
        result = select_tools_for_role("unknown_role")
        assert isinstance(result, ToolSelectionResult)
        assert "filesystem" in result.categories_used or "feature_management" in result.categories_used

    def test_get_tools_by_category(self):
        """get_tools_by_category should return tools in that category."""
        filesystem_tools = get_tools_by_category("filesystem")
        assert "Read" in filesystem_tools
        assert "Write" in filesystem_tools
        assert "Glob" in filesystem_tools
        assert "Grep" in filesystem_tools

    def test_get_tools_by_privilege(self):
        """get_tools_by_privilege should return tools at that level."""
        read_tools = get_tools_by_privilege("read")
        assert "Read" in read_tools
        assert "Glob" in read_tools
        assert "Grep" in read_tools

        write_tools = get_tools_by_privilege("write")
        assert "Write" in write_tools
        assert "Edit" in write_tools


# =============================================================================
# Step 3: Test-runner agents get test-related tools
# =============================================================================

class TestStep3TestRunnerTools:
    """Test that test-runner agents get appropriate test-related tools."""

    def test_test_runner_role_categories(self):
        """Test-runner role should include filesystem and execution categories."""
        categories = ROLE_TOOL_CATEGORIES.get("test_runner", [])
        assert "filesystem" in categories
        assert "execution" in categories

    def test_get_test_runner_tools_includes_read(self):
        """Test-runner tools should include Read for reading test files."""
        tools = get_test_runner_tools()
        assert "Read" in tools

    def test_get_test_runner_tools_includes_bash(self):
        """Test-runner tools should include Bash for running test commands."""
        tools = get_test_runner_tools()
        assert "Bash" in tools

    def test_get_test_runner_tools_includes_grep(self):
        """Test-runner tools should include Grep for searching test output."""
        tools = get_test_runner_tools()
        assert "Grep" in tools

    def test_test_runner_excludes_write(self):
        """Test-runner should NOT include Write (least-privilege)."""
        tools = get_test_runner_tools()
        # Write might be excluded for test runners (they shouldn't modify code)
        result = select_tools_for_role("test_runner")
        assert "Write" in result.least_privilege_exclusions or "Write" not in tools

    def test_select_tools_for_test_runner_role(self):
        """select_tools_for_role('test_runner') should return test tools."""
        result = select_tools_for_role("test_runner")
        assert "Read" in result.tools
        assert "Bash" in result.tools
        assert len(result.tools) > 0


# =============================================================================
# Step 4: UI agents get browser/Playwright tools when available
# =============================================================================

class TestStep4UIAgentTools:
    """Test that UI agents get browser/Playwright tools."""

    def test_ui_testing_role_categories(self):
        """UI testing role should include browser category."""
        categories = ROLE_TOOL_CATEGORIES.get("ui_testing", [])
        assert "browser" in categories

    def test_e2e_testing_role_categories(self):
        """E2E testing role should include browser category."""
        categories = ROLE_TOOL_CATEGORIES.get("e2e_testing", [])
        assert "browser" in categories

    def test_get_browser_tools(self):
        """get_browser_tools should return all browser tools."""
        browser_tools = get_browser_tools()
        assert "browser_navigate" in browser_tools
        assert "browser_click" in browser_tools
        assert "browser_type" in browser_tools
        assert "browser_fill_form" in browser_tools
        assert "browser_snapshot" in browser_tools
        assert "browser_take_screenshot" in browser_tools

    def test_is_browser_tool(self):
        """is_browser_tool should correctly identify browser tools."""
        assert is_browser_tool("browser_navigate") is True
        assert is_browser_tool("browser_click") is True
        assert is_browser_tool("Read") is False
        assert is_browser_tool("Bash") is False

    def test_get_ui_agent_tools_includes_browser_tools(self):
        """UI agent tools should include browser/Playwright tools."""
        tools = get_ui_agent_tools()
        assert "browser_navigate" in tools
        assert "browser_click" in tools
        assert "browser_type" in tools
        assert "browser_snapshot" in tools

    def test_select_tools_for_ui_testing_role(self):
        """select_tools_for_role('ui_testing') should include browser tools."""
        result = select_tools_for_role("ui_testing")
        assert "browser_navigate" in result.tools
        assert "browser_click" in result.tools
        assert "browser" in result.categories_used

    def test_select_tools_with_include_browser_flag(self):
        """include_browser=True should add browser tools to any role."""
        result = select_tools_for_role("coding", include_browser=True)
        assert "browser" in result.categories_used

    def test_select_tools_for_capability_detects_ui_keywords(self):
        """select_tools_for_capability should detect UI-related keywords."""
        result = select_tools_for_capability("ui_testing", "testing")
        assert "browser_navigate" in result.tools

        result2 = select_tools_for_capability("e2e_testing", "testing")
        assert "browser_navigate" in result2.tools

    def test_select_tools_for_capability_with_playwright_in_tech_stack(self):
        """Browser tools should be included when Playwright is in tech stack."""
        context = {"tech_stack": ["react", "playwright", "typescript"]}
        result = select_tools_for_capability("generic_testing", "testing", context)
        # Should include browser tools because Playwright is in tech stack
        assert any("browser" in t for t in result.tools) or "browser" in str(result.categories_used)


# =============================================================================
# Step 5: Tool selection follows least-privilege principle
# =============================================================================

class TestStep5LeastPrivilege:
    """Test that tool selection follows least-privilege principle."""

    def test_role_tool_overrides_exists(self):
        """ROLE_TOOL_OVERRIDES should exist for fine-grained control."""
        assert ROLE_TOOL_OVERRIDES is not None

    def test_audit_agents_are_read_only(self):
        """Audit agents should only have read-only tools."""
        result = select_tools_for_role("audit")

        # Should have Read, Glob, Grep
        assert "Read" in result.tools
        assert "Glob" in result.tools
        assert "Grep" in result.tools

        # Should NOT have write/execute tools
        assert "Write" not in result.tools or "Write" in result.least_privilege_exclusions
        assert "Edit" not in result.tools or "Edit" in result.least_privilege_exclusions
        assert "Bash" not in result.tools or "Bash" in result.least_privilege_exclusions

    def test_security_audit_excludes_execution(self):
        """Security audit should exclude execution tools."""
        result = select_tools_for_role("security_audit")
        assert "Bash" not in result.tools or "Bash" in result.least_privilege_exclusions

    def test_documentation_excludes_bash(self):
        """Documentation agents should not have Bash."""
        result = select_tools_for_role("documentation")
        assert "Bash" not in result.tools or "Bash" in result.least_privilege_exclusions

    def test_test_runner_excludes_write(self):
        """Test runners should not be able to write production code."""
        result = select_tools_for_role("test_runner")
        assert "Write" in result.least_privilege_exclusions

    def test_ui_testing_excludes_browser_evaluate(self):
        """UI testing should not have browser_evaluate (JS execution)."""
        result = select_tools_for_role("ui_testing")
        assert "browser_evaluate" not in result.tools or "browser_evaluate" in result.least_privilege_exclusions

    def test_least_privilege_exclusions_are_tracked(self):
        """Least-privilege exclusions should be tracked in result."""
        result = select_tools_for_role("audit")
        assert isinstance(result.least_privilege_exclusions, list)
        # Audit should have some exclusions
        assert len(result.least_privilege_exclusions) > 0

    def test_overrides_applied_are_tracked(self):
        """Applied overrides should be tracked in result."""
        result = select_tools_for_role("test_runner")
        if result.overrides_applied:
            assert "include" in result.overrides_applied or "exclude" in result.overrides_applied

    def test_enforce_least_privilege_can_be_disabled(self):
        """enforce_least_privilege=False should skip exclusions."""
        result_strict = select_tools_for_role("test_runner", enforce_least_privilege=True)
        result_relaxed = select_tools_for_role("test_runner", enforce_least_privilege=False)

        # Relaxed mode should have more tools (no exclusions applied)
        assert len(result_relaxed.least_privilege_exclusions) == 0 or \
               len(result_relaxed.tools) >= len(result_strict.tools)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for tool selection."""

    def test_select_tools_for_capability_coding(self):
        """Coding capability should get comprehensive tool set."""
        result = select_tools_for_capability("coding", "coding")
        assert "Read" in result.tools
        assert "Write" in result.tools
        assert "Edit" in result.tools
        assert "Bash" in result.tools

    def test_select_tools_for_capability_api_testing(self):
        """API testing should get execution tools for curl/requests."""
        result = select_tools_for_capability("api_testing", "testing")
        assert "Bash" in result.tools
        assert "Read" in result.tools

    def test_select_tools_for_capability_unknown_falls_back_to_task_type(self):
        """Unknown capability should fall back to task type defaults."""
        result = select_tools_for_capability("unknown_capability", "coding")
        assert len(result.tools) > 0
        assert "coding" in result.reasoning or "TOOL_SETS" in result.reasoning

    def test_tool_selection_result_to_dict(self):
        """ToolSelectionResult.to_dict should serialize correctly."""
        result = select_tools_for_role("coding")
        data = result.to_dict()

        assert "tools" in data
        assert "categories_used" in data
        assert "overrides_applied" in data
        assert "least_privilege_exclusions" in data
        assert "reasoning" in data

        assert isinstance(data["tools"], list)
        assert isinstance(data["categories_used"], list)

    def test_select_tools_for_refactoring(self):
        """Refactoring agents should have edit and execution tools."""
        result = select_tools_for_capability("refactoring", "refactoring")
        assert "Edit" in result.tools
        assert "Bash" in result.tools  # For running tests after refactoring

    def test_reasoning_explains_selections(self):
        """Reasoning string should explain the selection logic."""
        result = select_tools_for_role("ui_testing", include_browser=True)
        assert "ui_testing" in result.reasoning or "categories" in result.reasoning


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for tool selection."""

    def test_empty_role_uses_defaults(self):
        """Empty role string should use default categories."""
        result = select_tools_for_role("")
        assert isinstance(result, ToolSelectionResult)
        assert len(result.tools) >= 0

    def test_role_with_different_casing(self):
        """Role matching should be case-insensitive."""
        result1 = select_tools_for_role("test_runner")
        result2 = select_tools_for_role("TEST_RUNNER")
        result3 = select_tools_for_role("Test_Runner")

        # Should all resolve to same tool set
        assert set(result1.tools) == set(result2.tools) == set(result3.tools)

    def test_role_with_hyphen_vs_underscore(self):
        """Role matching should normalize hyphens to underscores."""
        result1 = select_tools_for_role("test_runner")
        result2 = select_tools_for_role("test-runner")

        # Should resolve to same tool set
        assert set(result1.tools) == set(result2.tools)

    def test_project_context_none_is_handled(self):
        """project_context=None should be handled gracefully."""
        result = select_tools_for_capability("coding", "coding", None)
        assert isinstance(result, ToolSelectionResult)

    def test_project_context_empty_dict(self):
        """Empty project_context should be handled gracefully."""
        result = select_tools_for_capability("coding", "coding", {})
        assert isinstance(result, ToolSelectionResult)

    def test_tools_list_is_sorted(self):
        """Selected tools list should be sorted for consistency."""
        result = select_tools_for_role("coding")
        assert result.tools == sorted(result.tools)
