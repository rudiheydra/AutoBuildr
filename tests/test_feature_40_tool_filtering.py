#!/usr/bin/env python3
"""
Tests for Feature #40: ToolPolicy Allowed Tools Filtering

This module tests the tool filtering functionality that filters tool definitions
based on spec.tool_policy.allowed_tools whitelist.

Feature #40 Verification Steps:
1. Extract allowed_tools from spec.tool_policy
2. If None or empty, allow all available tools
3. If list provided, filter tools to only include those in list
4. Log which tools are available to agent
5. Verify filtered tools are valid MCP tool names
6. Return filtered tool definitions to Claude SDK
"""

import logging
import pytest
from unittest.mock import MagicMock, patch

from api.tool_policy import (
    ToolDefinition,
    ToolFilterResult,
    extract_allowed_tools,
    filter_tools,
    filter_tools_for_spec,
    get_filtered_tool_names,
    validate_tool_names,
)


# =============================================================================
# Test Data
# =============================================================================

SAMPLE_TOOLS = [
    ToolDefinition(name="Read", description="Read file contents"),
    ToolDefinition(name="Write", description="Write file contents"),
    ToolDefinition(name="Edit", description="Edit file contents"),
    ToolDefinition(name="Bash", description="Run shell commands"),
    ToolDefinition(name="Glob", description="Find files by pattern"),
    ToolDefinition(name="Grep", description="Search file contents"),
]

SAMPLE_TOOL_NAMES = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


# =============================================================================
# Test ToolDefinition
# =============================================================================

class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_creation_with_defaults(self):
        """Test ToolDefinition creation with defaults."""
        tool = ToolDefinition(name="TestTool")
        assert tool.name == "TestTool"
        assert tool.description == ""
        assert tool.input_schema == {}
        assert tool.metadata == {}

    def test_creation_with_all_fields(self):
        """Test ToolDefinition creation with all fields."""
        tool = ToolDefinition(
            name="TestTool",
            description="A test tool",
            input_schema={"type": "object"},
            metadata={"category": "testing"},
        )
        assert tool.name == "TestTool"
        assert tool.description == "A test tool"
        assert tool.input_schema == {"type": "object"}
        assert tool.metadata == {"category": "testing"}

    def test_to_dict(self):
        """Test ToolDefinition.to_dict() method."""
        tool = ToolDefinition(
            name="TestTool",
            description="A test tool",
            input_schema={"type": "object"},
            metadata={"category": "testing"},
        )
        result = tool.to_dict()
        assert result == {
            "name": "TestTool",
            "description": "A test tool",
            "input_schema": {"type": "object"},
            "metadata": {"category": "testing"},
        }


# =============================================================================
# Test ToolFilterResult
# =============================================================================

class TestToolFilterResult:
    """Tests for ToolFilterResult dataclass."""

    def test_all_allowed_property(self):
        """Test all_allowed property."""
        result = ToolFilterResult(
            filtered_tools=SAMPLE_TOOLS,
            allowed_count=6,
            total_count=6,
            filtered_out=[],
            invalid_tools=[],
            mode="all_allowed",
        )
        assert result.all_allowed is True

        result2 = ToolFilterResult(
            filtered_tools=SAMPLE_TOOLS[:2],
            allowed_count=2,
            total_count=6,
            filtered_out=["Edit", "Bash", "Glob", "Grep"],
            invalid_tools=[],
            mode="whitelist",
        )
        assert result2.all_allowed is False

    def test_has_invalid_tools_property(self):
        """Test has_invalid_tools property."""
        result = ToolFilterResult(
            filtered_tools=SAMPLE_TOOLS[:2],
            allowed_count=2,
            total_count=6,
            filtered_out=[],
            invalid_tools=["InvalidTool"],
            mode="whitelist",
        )
        assert result.has_invalid_tools is True

        result2 = ToolFilterResult(
            filtered_tools=SAMPLE_TOOLS[:2],
            allowed_count=2,
            total_count=6,
            filtered_out=[],
            invalid_tools=[],
            mode="whitelist",
        )
        assert result2.has_invalid_tools is False

    def test_to_dict(self):
        """Test ToolFilterResult.to_dict() method."""
        result = ToolFilterResult(
            filtered_tools=SAMPLE_TOOLS[:2],
            allowed_count=2,
            total_count=6,
            filtered_out=["Bash"],
            invalid_tools=["Invalid"],
            mode="whitelist",
        )
        d = result.to_dict()
        assert d["allowed_count"] == 2
        assert d["total_count"] == 6
        assert d["filtered_out"] == ["Bash"]
        assert d["invalid_tools"] == ["Invalid"]
        assert d["mode"] == "whitelist"
        assert d["all_allowed"] is False
        assert d["has_invalid_tools"] is True


# =============================================================================
# Test extract_allowed_tools - Feature #40, Step 1
# =============================================================================

class TestExtractAllowedTools:
    """Tests for extract_allowed_tools function."""

    def test_none_tool_policy(self):
        """Test with None tool_policy returns None (all allowed)."""
        result = extract_allowed_tools(None)
        assert result is None

    def test_empty_dict(self):
        """Test with empty dict returns None (all allowed)."""
        result = extract_allowed_tools({})
        assert result is None

    def test_missing_allowed_tools_key(self):
        """Test with missing allowed_tools key returns None."""
        result = extract_allowed_tools({"policy_version": "v1"})
        assert result is None

    def test_allowed_tools_none_value(self):
        """Test with allowed_tools=None returns None."""
        result = extract_allowed_tools({"allowed_tools": None})
        assert result is None

    def test_empty_list(self):
        """Test with empty list returns None (Feature #40, Step 2)."""
        result = extract_allowed_tools({"allowed_tools": []})
        assert result is None

    def test_valid_list(self):
        """Test with valid list returns the list."""
        result = extract_allowed_tools({
            "allowed_tools": ["Read", "Write", "Edit"]
        })
        assert result == ["Read", "Write", "Edit"]

    def test_non_list_value_logs_warning(self, caplog):
        """Test non-list value logs warning and returns None."""
        with caplog.at_level(logging.WARNING):
            result = extract_allowed_tools({"allowed_tools": "Read"})
        assert result is None
        assert "allowed_tools is not a list" in caplog.text

    def test_filters_non_string_entries(self, caplog):
        """Test filters out non-string entries with warning."""
        with caplog.at_level(logging.WARNING):
            result = extract_allowed_tools({
                "allowed_tools": ["Read", 123, "Write", None, "Edit"]
            })
        assert result == ["Read", "Write", "Edit"]
        assert "Skipping non-string tool" in caplog.text

    def test_strips_whitespace(self):
        """Test strips whitespace from tool names."""
        result = extract_allowed_tools({
            "allowed_tools": [" Read ", "  Write  ", "Edit"]
        })
        assert result == ["Read", "Write", "Edit"]

    def test_filters_empty_strings(self):
        """Test filters out empty strings."""
        result = extract_allowed_tools({
            "allowed_tools": ["Read", "", "  ", "Write"]
        })
        assert result == ["Read", "Write"]

    def test_all_empty_returns_none(self):
        """Test list with only empty strings returns None."""
        result = extract_allowed_tools({
            "allowed_tools": ["", "  ", "   "]
        })
        assert result is None


# =============================================================================
# Test validate_tool_names - Feature #40, Step 5
# =============================================================================

class TestValidateToolNames:
    """Tests for validate_tool_names function."""

    def test_all_valid(self):
        """Test with all valid tool names."""
        available = ["Read", "Write", "Bash"]
        valid, invalid = validate_tool_names(["Read", "Write"], available)
        assert valid == ["Read", "Write"]
        assert invalid == []

    def test_some_invalid(self):
        """Test with some invalid tool names."""
        available = ["Read", "Write", "Bash"]
        valid, invalid = validate_tool_names(
            ["Read", "InvalidTool", "Write", "FakeTool"],
            available
        )
        assert valid == ["Read", "Write"]
        assert invalid == ["InvalidTool", "FakeTool"]

    def test_all_invalid(self):
        """Test with all invalid tool names."""
        available = ["Read", "Write", "Bash"]
        valid, invalid = validate_tool_names(
            ["InvalidTool", "FakeTool"],
            available
        )
        assert valid == []
        assert invalid == ["InvalidTool", "FakeTool"]

    def test_empty_tool_names(self):
        """Test with empty tool names list."""
        available = ["Read", "Write"]
        valid, invalid = validate_tool_names([], available)
        assert valid == []
        assert invalid == []

    def test_empty_available_tools(self):
        """Test with empty available tools list."""
        valid, invalid = validate_tool_names(["Read", "Write"], [])
        assert valid == []
        assert invalid == ["Read", "Write"]

    def test_case_sensitive(self):
        """Test that validation is case-sensitive."""
        available = ["Read", "Write"]
        valid, invalid = validate_tool_names(["read", "WRITE", "Read"], available)
        assert valid == ["Read"]
        assert invalid == ["read", "WRITE"]


# =============================================================================
# Test filter_tools - Feature #40 Core Function
# =============================================================================

class TestFilterTools:
    """Tests for filter_tools function."""

    def test_none_allowed_tools_allows_all(self):
        """Test None allowed_tools allows all tools (Step 2)."""
        result = filter_tools(SAMPLE_TOOLS, None)
        assert result.allowed_count == 6
        assert result.total_count == 6
        assert len(result.filtered_tools) == 6
        assert result.filtered_out == []
        assert result.mode == "all_allowed"
        assert result.all_allowed is True

    def test_empty_list_allowed_tools_allows_all(self):
        """Test empty allowed_tools list allows all tools (Step 2)."""
        result = filter_tools(SAMPLE_TOOLS, [])
        assert result.allowed_count == 6
        assert result.mode == "all_allowed"

    def test_whitelist_filtering(self):
        """Test whitelist filtering (Step 3)."""
        result = filter_tools(SAMPLE_TOOLS, ["Read", "Write"])
        assert result.allowed_count == 2
        assert result.total_count == 6
        assert len(result.filtered_tools) == 2
        assert {t.name for t in result.filtered_tools} == {"Read", "Write"}
        assert set(result.filtered_out) == {"Edit", "Bash", "Glob", "Grep"}
        assert result.mode == "whitelist"
        assert result.all_allowed is False

    def test_logs_available_tools(self, caplog):
        """Test logging of available tools (Step 4)."""
        with caplog.at_level(logging.INFO):
            filter_tools(SAMPLE_TOOLS, ["Read", "Write"], spec_id="test-spec-123")
        assert "Filtered tools for spec test-spec-123" in caplog.text
        assert "2/6 allowed" in caplog.text

    def test_logs_all_allowed_mode(self, caplog):
        """Test logging when all tools allowed (Step 4)."""
        with caplog.at_level(logging.INFO):
            filter_tools(SAMPLE_TOOLS, None, spec_id="test-spec-456")
        assert "All 6 tools allowed for spec test-spec-456" in caplog.text

    def test_logs_filtered_out_tools(self, caplog):
        """Test logging of filtered out tools."""
        with caplog.at_level(logging.DEBUG):
            filter_tools(SAMPLE_TOOLS, ["Read"], spec_id="test-spec-789")
        # Note: filtered_out tools are logged at DEBUG level
        # The main log at INFO level shows the count

    def test_invalid_tools_in_allowed_list(self):
        """Test handling invalid tool names in allowed_tools (Step 5)."""
        result = filter_tools(SAMPLE_TOOLS, ["Read", "InvalidTool", "FakeTool"])
        assert result.allowed_count == 1  # Only Read is valid
        assert result.invalid_tools == ["InvalidTool", "FakeTool"]
        assert result.has_invalid_tools is True

    def test_logs_invalid_tools_warning(self, caplog):
        """Test warning logged for invalid tool names."""
        with caplog.at_level(logging.WARNING):
            filter_tools(SAMPLE_TOOLS, ["Read", "InvalidTool"], spec_id="test-spec")
        assert "Some allowed_tools are not valid" in caplog.text
        assert "InvalidTool" in caplog.text

    def test_returns_tool_definitions(self):
        """Test returns filtered ToolDefinitions (Step 6)."""
        result = filter_tools(SAMPLE_TOOLS, ["Read", "Write"])
        assert all(isinstance(t, ToolDefinition) for t in result.filtered_tools)
        assert result.filtered_tools[0].name in ["Read", "Write"]
        assert result.filtered_tools[1].name in ["Read", "Write"]

    def test_accepts_dict_input(self):
        """Test accepts dict tool definitions as input."""
        dict_tools = [
            {"name": "Read", "description": "Read file"},
            {"name": "Write", "description": "Write file"},
        ]
        result = filter_tools(dict_tools, ["Read"])
        assert result.allowed_count == 1
        assert result.filtered_tools[0].name == "Read"
        assert isinstance(result.filtered_tools[0], ToolDefinition)

    def test_handles_mixed_input(self):
        """Test handles mixed ToolDefinition and dict input."""
        mixed_tools = [
            ToolDefinition(name="Read", description="Read file"),
            {"name": "Write", "description": "Write file"},
        ]
        result = filter_tools(mixed_tools, ["Read", "Write"])
        assert result.allowed_count == 2

    def test_skips_invalid_input(self, caplog):
        """Test skips invalid input in tools list."""
        invalid_tools = [
            ToolDefinition(name="Read", description="Read file"),
            "not a tool",  # Invalid
            123,  # Invalid
        ]
        with caplog.at_level(logging.WARNING):
            result = filter_tools(invalid_tools, None)
        assert result.total_count == 1  # Only valid ToolDefinition counted
        assert "Skipping invalid tool definition" in caplog.text

    def test_empty_available_tools(self):
        """Test with empty available tools list."""
        result = filter_tools([], ["Read", "Write"])
        assert result.allowed_count == 0
        assert result.total_count == 0
        assert result.invalid_tools == ["Read", "Write"]

    def test_preserves_tool_properties(self):
        """Test preserves all tool properties after filtering."""
        tools = [
            ToolDefinition(
                name="Read",
                description="Read file contents",
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                metadata={"category": "file_operations"},
            ),
        ]
        result = filter_tools(tools, ["Read"])
        filtered_tool = result.filtered_tools[0]
        assert filtered_tool.description == "Read file contents"
        assert filtered_tool.input_schema == {"type": "object", "properties": {"path": {"type": "string"}}}
        assert filtered_tool.metadata == {"category": "file_operations"}


# =============================================================================
# Test filter_tools_for_spec - Convenience Function
# =============================================================================

class TestFilterToolsForSpec:
    """Tests for filter_tools_for_spec function."""

    def test_extracts_allowed_tools_from_spec(self):
        """Test extracts allowed_tools from spec.tool_policy."""
        mock_spec = MagicMock()
        mock_spec.id = "spec-123"
        mock_spec.tool_policy = {"allowed_tools": ["Read", "Write"]}

        result = filter_tools_for_spec(mock_spec, SAMPLE_TOOLS)
        assert result.allowed_count == 2
        assert {t.name for t in result.filtered_tools} == {"Read", "Write"}

    def test_handles_none_tool_policy(self):
        """Test handles None tool_policy (all allowed)."""
        mock_spec = MagicMock()
        mock_spec.id = "spec-456"
        mock_spec.tool_policy = None

        result = filter_tools_for_spec(mock_spec, SAMPLE_TOOLS)
        assert result.allowed_count == 6
        assert result.mode == "all_allowed"

    def test_handles_empty_tool_policy(self):
        """Test handles empty tool_policy (all allowed)."""
        mock_spec = MagicMock()
        mock_spec.id = "spec-789"
        mock_spec.tool_policy = {}

        result = filter_tools_for_spec(mock_spec, SAMPLE_TOOLS)
        assert result.allowed_count == 6
        assert result.mode == "all_allowed"

    def test_uses_spec_id_for_logging(self, caplog):
        """Test uses spec.id for logging context."""
        mock_spec = MagicMock()
        mock_spec.id = "unique-spec-id"
        mock_spec.tool_policy = {"allowed_tools": ["Read"]}

        with caplog.at_level(logging.INFO):
            filter_tools_for_spec(mock_spec, SAMPLE_TOOLS)
        assert "unique-spec-id" in caplog.text


# =============================================================================
# Test get_filtered_tool_names - Lightweight Function
# =============================================================================

class TestGetFilteredToolNames:
    """Tests for get_filtered_tool_names function."""

    def test_returns_all_when_no_allowed_tools(self):
        """Test returns all tools when no allowed_tools specified."""
        filtered, out = get_filtered_tool_names(None, SAMPLE_TOOL_NAMES)
        assert set(filtered) == set(SAMPLE_TOOL_NAMES)
        assert out == []

    def test_filters_based_on_whitelist(self):
        """Test filters based on allowed_tools whitelist."""
        policy = {"allowed_tools": ["Read", "Write"]}
        filtered, out = get_filtered_tool_names(policy, SAMPLE_TOOL_NAMES)
        assert filtered == ["Read", "Write"]
        assert set(out) == {"Edit", "Bash", "Glob", "Grep"}

    def test_handles_invalid_tool_names(self, caplog):
        """Test handles invalid tool names in allowed_tools."""
        policy = {"allowed_tools": ["Read", "InvalidTool"]}
        with caplog.at_level(logging.WARNING):
            filtered, out = get_filtered_tool_names(policy, SAMPLE_TOOL_NAMES)
        assert filtered == ["Read"]
        assert "Invalid tool names in allowed_tools" in caplog.text

    def test_uses_spec_id_for_logging(self, caplog):
        """Test uses spec_id for logging."""
        policy = {"allowed_tools": ["Read"]}
        with caplog.at_level(logging.INFO):
            get_filtered_tool_names(policy, SAMPLE_TOOL_NAMES, spec_id="test-spec")
        assert "test-spec" in caplog.text


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for tool filtering with real AgentSpec-like structures."""

    def test_full_workflow_with_coding_policy(self):
        """Test full workflow with a coding task tool policy."""
        # Simulate a coding task tool policy
        tool_policy = {
            "policy_version": "v1",
            "allowed_tools": [
                "Read", "Write", "Edit", "Bash",
                "feature_get_by_id", "feature_mark_passing"
            ],
            "forbidden_patterns": ["rm -rf /"],
        }

        # Simulate available MCP tools
        available_tools = [
            ToolDefinition(name="Read", description="Read files"),
            ToolDefinition(name="Write", description="Write files"),
            ToolDefinition(name="Edit", description="Edit files"),
            ToolDefinition(name="Bash", description="Run commands"),
            ToolDefinition(name="Glob", description="Find files"),
            ToolDefinition(name="Grep", description="Search files"),
            ToolDefinition(name="WebFetch", description="Fetch web content"),
            ToolDefinition(name="feature_get_by_id", description="Get feature"),
            ToolDefinition(name="feature_mark_passing", description="Mark passing"),
        ]

        # Extract and filter
        allowed_tools = extract_allowed_tools(tool_policy)
        result = filter_tools(available_tools, allowed_tools, spec_id="coding-spec")

        # Verify
        assert result.allowed_count == 6
        assert result.total_count == 9
        filtered_names = {t.name for t in result.filtered_tools}
        assert filtered_names == {
            "Read", "Write", "Edit", "Bash",
            "feature_get_by_id", "feature_mark_passing"
        }
        assert set(result.filtered_out) == {"Glob", "Grep", "WebFetch"}
        assert result.mode == "whitelist"

    def test_full_workflow_with_testing_policy(self):
        """Test full workflow with a testing task tool policy."""
        # Testing agents typically have read-only access
        tool_policy = {
            "policy_version": "v1",
            "allowed_tools": [
                "Read", "Glob", "Grep",
                "browser_navigate", "browser_snapshot",
                "feature_get_by_id", "feature_mark_passing", "feature_mark_failing"
            ],
        }

        available_tools = [
            ToolDefinition(name="Read", description="Read files"),
            ToolDefinition(name="Write", description="Write files"),
            ToolDefinition(name="Edit", description="Edit files"),
            ToolDefinition(name="Bash", description="Run commands"),
            ToolDefinition(name="Glob", description="Find files"),
            ToolDefinition(name="Grep", description="Search files"),
            ToolDefinition(name="browser_navigate", description="Navigate browser"),
            ToolDefinition(name="browser_snapshot", description="Take snapshot"),
            ToolDefinition(name="browser_click", description="Click element"),
            ToolDefinition(name="feature_get_by_id", description="Get feature"),
            ToolDefinition(name="feature_mark_passing", description="Mark passing"),
            ToolDefinition(name="feature_mark_failing", description="Mark failing"),
        ]

        allowed_tools = extract_allowed_tools(tool_policy)
        result = filter_tools(available_tools, allowed_tools)

        # Testing agents should not have Write, Edit, Bash, browser_click
        assert "Write" not in {t.name for t in result.filtered_tools}
        assert "Edit" not in {t.name for t in result.filtered_tools}
        assert "browser_click" not in {t.name for t in result.filtered_tools}
        assert result.allowed_count == 8

    def test_full_workflow_with_audit_policy(self):
        """Test full workflow with audit task tool policy (read-only)."""
        # Audit agents are strictly read-only
        tool_policy = {
            "policy_version": "v1",
            "allowed_tools": ["Read", "Glob", "Grep"],
        }

        available_tools = [
            ToolDefinition(name="Read", description="Read files"),
            ToolDefinition(name="Write", description="Write files"),
            ToolDefinition(name="Edit", description="Edit files"),
            ToolDefinition(name="Bash", description="Run commands"),
            ToolDefinition(name="Glob", description="Find files"),
            ToolDefinition(name="Grep", description="Search files"),
        ]

        allowed_tools = extract_allowed_tools(tool_policy)
        result = filter_tools(available_tools, allowed_tools)

        # Audit should only have read-only tools
        assert result.allowed_count == 3
        filtered_names = {t.name for t in result.filtered_tools}
        assert filtered_names == {"Read", "Glob", "Grep"}
        # No destructive tools
        assert "Write" not in filtered_names
        assert "Edit" not in filtered_names
        assert "Bash" not in filtered_names


# =============================================================================
# Test Feature #40 Verification Steps Explicitly
# =============================================================================

class TestFeature40VerificationSteps:
    """Explicit tests for each Feature #40 verification step."""

    def test_step1_extract_allowed_tools(self):
        """Step 1: Extract allowed_tools from spec.tool_policy"""
        policy = {
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Edit"],
            "forbidden_patterns": ["rm -rf /"],
        }
        result = extract_allowed_tools(policy)
        assert result == ["Read", "Write", "Edit"]

    def test_step2_none_or_empty_allows_all(self):
        """Step 2: If None or empty, allow all available tools"""
        # None case
        result1 = filter_tools(SAMPLE_TOOLS, None)
        assert result1.allowed_count == len(SAMPLE_TOOLS)
        assert result1.mode == "all_allowed"

        # Empty list case
        result2 = filter_tools(SAMPLE_TOOLS, [])
        assert result2.allowed_count == len(SAMPLE_TOOLS)
        assert result2.mode == "all_allowed"

    def test_step3_filter_to_whitelist(self):
        """Step 3: If list provided, filter tools to only include those in list"""
        allowed = ["Read", "Write"]
        result = filter_tools(SAMPLE_TOOLS, allowed)

        # Only allowed tools should be present
        filtered_names = {t.name for t in result.filtered_tools}
        assert filtered_names == {"Read", "Write"}

        # Other tools should be filtered out
        assert "Bash" in result.filtered_out
        assert "Edit" in result.filtered_out

    def test_step4_log_available_tools(self, caplog):
        """Step 4: Log which tools are available to agent"""
        with caplog.at_level(logging.INFO):
            filter_tools(SAMPLE_TOOLS, ["Read", "Write"], spec_id="test-spec")

        # Should log the filtered tools
        assert "Filtered tools for spec test-spec" in caplog.text
        assert "2/6 allowed" in caplog.text

    def test_step5_verify_valid_mcp_names(self):
        """Step 5: Verify filtered tools are valid MCP tool names"""
        # Include an invalid tool name
        allowed = ["Read", "InvalidTool", "Write", "NotRealTool"]
        result = filter_tools(SAMPLE_TOOLS, allowed)

        # Should identify invalid tools
        assert result.invalid_tools == ["InvalidTool", "NotRealTool"]
        assert result.has_invalid_tools is True

        # Should only include valid tools
        assert result.allowed_count == 2
        assert {t.name for t in result.filtered_tools} == {"Read", "Write"}

    def test_step6_return_filtered_definitions(self):
        """Step 6: Return filtered tool definitions to Claude SDK"""
        allowed = ["Read", "Bash"]
        result = filter_tools(SAMPLE_TOOLS, allowed)

        # Should return ToolFilterResult with filtered ToolDefinitions
        assert isinstance(result, ToolFilterResult)
        assert all(isinstance(t, ToolDefinition) for t in result.filtered_tools)
        assert len(result.filtered_tools) == 2

        # Should preserve tool properties
        read_tool = next(t for t in result.filtered_tools if t.name == "Read")
        assert read_tool.description == "Read file contents"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
