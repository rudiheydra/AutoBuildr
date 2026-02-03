"""
Tests for Feature #213: Playwright MCP available for E2E test agents
=====================================================================

This test module validates all aspects of Feature #213:
1. Playwright MCP server configurable in settings
2. Test-runner agents for E2E include Playwright tools
3. MCP connection established when agent starts
4. Playwright actions available: navigate, click, fill, assert
5. Configuration gated by project settings

Test Structure:
- TestStep1PlaywrightConfig: Playwright MCP server configurable in settings
- TestStep2E2EAgentTools: Test-runner agents for E2E include Playwright tools
- TestStep3McpConnection: MCP connection established when agent starts
- TestStep4PlaywrightActions: Playwright actions available
- TestStep5ConfigurationGating: Configuration gated by project settings
- TestDataClasses: Data class functionality
- TestApiPackageExports: API package exports
- TestFeature213VerificationSteps: Comprehensive acceptance tests
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from api.playwright_mcp_config import (
    # Enums
    PlaywrightMode,
    PlaywrightToolSet,
    # Data classes
    PlaywrightMcpConfig,
    PlaywrightAgentConfigResult,
    McpConnectionResult,
    # Configuration functions
    get_playwright_config,
    is_playwright_enabled,
    enable_playwright,
    disable_playwright,
    # Tool selection functions
    get_playwright_tools,
    configure_playwright_for_agent,
    add_playwright_tools_to_spec,
    is_e2e_agent,
    # MCP connection functions
    get_mcp_server_config,
    verify_mcp_connection,
    ensure_playwright_in_settings,
    # Agent integration functions
    get_e2e_agent_tools,
    should_include_playwright_tools,
    # Cache functions
    get_cached_playwright_config,
    reset_playwright_config_cache,
    # Constants
    PLAYWRIGHT_TOOLS,
    CORE_PLAYWRIGHT_TOOLS,
    EXTENDED_PLAYWRIGHT_TOOLS,
    PLAYWRIGHT_TOOL_SETS,
    SUPPORTED_BROWSERS,
    DEFAULT_BROWSER,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_VIEWPORT,
    DEFAULT_PLAYWRIGHT_MCP_CONFIG,
    HEADFUL_PLAYWRIGHT_MCP_CONFIG,
    SETTINGS_PLAYWRIGHT_SECTION,
    MIN_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
)


# =============================================================================
# Test Step 1: Playwright MCP server configurable in settings
# =============================================================================

class TestStep1PlaywrightConfig:
    """Test Playwright MCP server configuration in settings."""

    def test_get_playwright_config_empty_settings(self):
        """Test getting config with no settings returns disabled config."""
        config = get_playwright_config(None)
        assert config.enabled is False
        assert config.headless is True
        assert config.browser == DEFAULT_BROWSER

    def test_get_playwright_config_enabled(self):
        """Test getting config with Playwright enabled."""
        settings = {
            "playwright": {
                "enabled": True,
                "headless": True,
                "browser": "chromium",
            }
        }
        config = get_playwright_config(settings)
        assert config.enabled is True
        assert config.headless is True
        assert config.browser == "chromium"

    def test_get_playwright_config_from_mcp_servers(self):
        """Test config is enabled when playwright is in mcpServers."""
        settings = {
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["@anthropic/mcp-server-playwright"],
                }
            }
        }
        config = get_playwright_config(settings)
        assert config.enabled is True

    def test_enable_playwright_updates_settings(self):
        """Test enable_playwright adds configuration to settings."""
        settings: dict = {}
        updated = enable_playwright(settings, headless=True, browser="chromium")

        assert "playwright" in updated
        assert updated["playwright"]["enabled"] is True
        assert updated["playwright"]["headless"] is True
        assert updated["playwright"]["browser"] == "chromium"
        assert "mcpServers" in updated
        assert "playwright" in updated["mcpServers"]

    def test_disable_playwright_removes_config(self):
        """Test disable_playwright removes configuration."""
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": {"command": "npx"}},
        }
        updated = disable_playwright(settings)

        assert updated["playwright"]["enabled"] is False
        assert "playwright" not in updated["mcpServers"]

    def test_config_with_all_options(self):
        """Test configuration with all options specified."""
        settings = {
            "playwright": {
                "enabled": True,
                "headless": False,
                "browser": "firefox",
                "timeout": 60000,
                "viewport": {"width": 1920, "height": 1080},
                "tool_set": "full",
            }
        }
        config = get_playwright_config(settings)

        assert config.enabled is True
        assert config.headless is False
        assert config.browser == "firefox"
        assert config.timeout_ms == 60000
        assert config.viewport["width"] == 1920
        assert config.viewport["height"] == 1080
        assert config.tool_set == "full"

    def test_config_validates_browser(self):
        """Test configuration validates browser name."""
        config = PlaywrightMcpConfig(
            enabled=True,
            browser="invalid_browser",
        )
        # Should default to chromium
        assert config.browser == DEFAULT_BROWSER

    def test_config_validates_timeout(self):
        """Test configuration validates timeout bounds."""
        # Too low
        config = PlaywrightMcpConfig(enabled=True, timeout_ms=1000)
        assert config.timeout_ms == MIN_TIMEOUT_MS

        # Too high
        config = PlaywrightMcpConfig(enabled=True, timeout_ms=999999)
        assert config.timeout_ms == MAX_TIMEOUT_MS


# =============================================================================
# Test Step 2: Test-runner agents for E2E include Playwright tools
# =============================================================================

class TestStep2E2EAgentTools:
    """Test E2E agent tool provisioning."""

    def test_is_e2e_agent_by_name(self):
        """Test E2E agent detection by name."""
        assert is_e2e_agent(agent_name="e2e-tester") is True
        assert is_e2e_agent(agent_name="e2e_testing_agent") is True
        assert is_e2e_agent(agent_name="browser-automation") is True
        assert is_e2e_agent(agent_name="playwright-agent") is True
        assert is_e2e_agent(agent_name="ui-testing-agent") is True
        assert is_e2e_agent(agent_name="regular-coder") is False

    def test_is_e2e_agent_by_capability(self):
        """Test E2E agent detection by capability."""
        assert is_e2e_agent(capability="e2e_testing") is True
        assert is_e2e_agent(capability="browser_automation") is True
        assert is_e2e_agent(capability="ui-testing") is True
        assert is_e2e_agent(capability="coding") is False

    def test_is_e2e_agent_by_task_type(self):
        """Test E2E agent detection by task type."""
        assert is_e2e_agent(task_type="e2e") is True
        assert is_e2e_agent(task_type="e2e_testing") is True
        assert is_e2e_agent(task_type="browser_testing") is True
        assert is_e2e_agent(task_type="coding") is False

    def test_get_e2e_agent_tools_enabled(self):
        """Test E2E agent tools when Playwright is enabled."""
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        tools = get_e2e_agent_tools(settings)

        # Should include base test tools
        assert "Read" in tools
        assert "Glob" in tools
        assert "Bash" in tools

        # Should include Playwright tools
        assert "mcp__playwright__browser_navigate" in tools
        assert "mcp__playwright__browser_click" in tools

    def test_get_e2e_agent_tools_disabled(self):
        """Test E2E agent tools when Playwright is disabled."""
        settings = {"playwright": {"enabled": False}}
        tools = get_e2e_agent_tools(settings)

        # Should include base test tools
        assert "Read" in tools

        # Should NOT include Playwright tools
        assert "mcp__playwright__browser_navigate" not in tools

    def test_configure_playwright_for_agent_success(self):
        """Test successful agent configuration."""
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        result = configure_playwright_for_agent("e2e-agent", settings)

        assert result.success is True
        assert len(result.tools_added) > 0
        assert "mcp__playwright__browser_navigate" in result.tools_added

    def test_configure_playwright_for_agent_disabled(self):
        """Test agent configuration when Playwright is disabled."""
        settings = {"playwright": {"enabled": False}}
        result = configure_playwright_for_agent("e2e-agent", settings)

        assert result.success is False
        assert "not enabled" in result.error.lower()

    def test_add_playwright_tools_to_spec(self):
        """Test adding Playwright tools to spec dictionary."""
        spec = {
            "name": "e2e-test-agent",
            "tool_policy": {
                "allowed_tools": ["Read", "Write"],
            },
        }
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        updated = add_playwright_tools_to_spec(spec, settings)

        assert "mcp__playwright__browser_navigate" in updated["tool_policy"]["allowed_tools"]
        assert "Read" in updated["tool_policy"]["allowed_tools"]

    def test_should_include_playwright_tools(self):
        """Test should_include_playwright_tools function."""
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }

        # E2E agent with Playwright enabled
        assert should_include_playwright_tools(
            agent_name="e2e-tester",
            project_settings=settings,
        ) is True

        # Non-E2E agent with Playwright enabled
        assert should_include_playwright_tools(
            agent_name="coder-agent",
            project_settings=settings,
        ) is False

        # E2E agent with Playwright disabled
        assert should_include_playwright_tools(
            agent_name="e2e-tester",
            project_settings={"playwright": {"enabled": False}},
        ) is False


# =============================================================================
# Test Step 3: MCP connection established when agent starts
# =============================================================================

class TestStep3McpConnection:
    """Test MCP connection establishment."""

    def test_get_mcp_server_config_default(self):
        """Test getting default MCP server config."""
        config = get_mcp_server_config(None, headless=True)

        assert config["command"] == "npx"
        assert "@anthropic/mcp-server-playwright" in config["args"]
        assert "--headless" in config["args"]

    def test_get_mcp_server_config_headful(self):
        """Test getting headful MCP server config."""
        config = get_mcp_server_config(None, headless=False)

        assert config["command"] == "npx"
        assert "--headless" not in config["args"]

    def test_get_mcp_server_config_from_settings(self):
        """Test getting MCP server config from settings."""
        settings = {
            "mcpServers": {
                "playwright": {
                    "command": "custom-command",
                    "args": ["custom-args"],
                }
            }
        }
        config = get_mcp_server_config(settings)

        assert config["command"] == "custom-command"
        assert config["args"] == ["custom-args"]

    def test_verify_mcp_connection_enabled(self):
        """Test MCP connection verification when enabled."""
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        result = verify_mcp_connection(settings)

        assert result.connected is True
        assert result.server_name == "playwright"
        assert len(result.tools_available) > 0

    def test_verify_mcp_connection_disabled(self):
        """Test MCP connection verification when disabled."""
        result = verify_mcp_connection({"playwright": {"enabled": False}})

        assert result.connected is False
        assert "not enabled" in result.error.lower()

    def test_verify_mcp_connection_with_default_config(self):
        """Test MCP connection verification uses default config when missing."""
        settings = {
            "playwright": {"enabled": True},
            # No mcpServers section - will use default config
        }
        result = verify_mcp_connection(settings)

        # Should succeed because default config is used
        assert result.connected is True
        assert result.server_name == "playwright"
        assert len(result.tools_available) > 0

    def test_ensure_playwright_in_settings(self):
        """Test ensuring Playwright is in settings file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # Create initial settings file
            import json
            settings_path = claude_dir / "settings.local.json"
            settings_path.write_text(json.dumps({"permissions": {"allow": []}}))

            # Ensure Playwright is configured
            result = ensure_playwright_in_settings(project_dir, headless=True)

            assert result is True

            # Verify settings were updated
            updated_settings = json.loads(settings_path.read_text())
            assert "mcpServers" in updated_settings
            assert "playwright" in updated_settings["mcpServers"]


# =============================================================================
# Test Step 4: Playwright actions available
# =============================================================================

class TestStep4PlaywrightActions:
    """Test Playwright action availability."""

    def test_core_playwright_tools_include_navigate(self):
        """Test core tools include navigate action."""
        assert "mcp__playwright__browser_navigate" in CORE_PLAYWRIGHT_TOOLS

    def test_core_playwright_tools_include_click(self):
        """Test core tools include click action."""
        assert "mcp__playwright__browser_click" in CORE_PLAYWRIGHT_TOOLS

    def test_core_playwright_tools_include_fill(self):
        """Test core tools include fill actions."""
        assert "mcp__playwright__browser_fill_form" in CORE_PLAYWRIGHT_TOOLS
        assert "mcp__playwright__browser_type" in CORE_PLAYWRIGHT_TOOLS

    def test_core_playwright_tools_include_assert(self):
        """Test core tools include assert actions (snapshot, screenshot)."""
        assert "mcp__playwright__browser_snapshot" in CORE_PLAYWRIGHT_TOOLS
        assert "mcp__playwright__browser_take_screenshot" in CORE_PLAYWRIGHT_TOOLS
        assert "mcp__playwright__browser_console_messages" in CORE_PLAYWRIGHT_TOOLS

    def test_get_playwright_tools_core(self):
        """Test getting core tool set."""
        tools = get_playwright_tools(tool_set="core")
        assert tools == CORE_PLAYWRIGHT_TOOLS
        assert len(tools) == len(CORE_PLAYWRIGHT_TOOLS)

    def test_get_playwright_tools_extended(self):
        """Test getting extended tool set."""
        tools = get_playwright_tools(tool_set="extended")
        # Extended includes core
        for core_tool in CORE_PLAYWRIGHT_TOOLS:
            assert core_tool in tools
        # And additional tools
        assert "mcp__playwright__browser_hover" in tools

    def test_get_playwright_tools_full(self):
        """Test getting full tool set."""
        tools = get_playwright_tools(tool_set="full")
        assert tools == PLAYWRIGHT_TOOLS
        assert len(tools) == len(PLAYWRIGHT_TOOLS)

    def test_playwright_tool_sets_defined(self):
        """Test all tool sets are defined."""
        assert "core" in PLAYWRIGHT_TOOL_SETS
        assert "extended" in PLAYWRIGHT_TOOL_SETS
        assert "full" in PLAYWRIGHT_TOOL_SETS


# =============================================================================
# Test Step 5: Configuration gated by project settings
# =============================================================================

class TestStep5ConfigurationGating:
    """Test configuration gating by project settings."""

    def test_is_playwright_enabled_false_by_default(self):
        """Test Playwright is disabled by default."""
        assert is_playwright_enabled(None) is False
        assert is_playwright_enabled({}) is False

    def test_is_playwright_enabled_true_when_configured(self):
        """Test Playwright is enabled when configured."""
        settings = {"playwright": {"enabled": True}}
        assert is_playwright_enabled(settings) is True

    def test_is_playwright_enabled_from_mcp_servers(self):
        """Test Playwright is enabled when in mcpServers."""
        settings = {"mcpServers": {"playwright": {}}}
        assert is_playwright_enabled(settings) is True

    def test_tools_not_added_when_disabled(self):
        """Test tools are not added when Playwright is disabled."""
        spec = {"name": "test", "tool_policy": {"allowed_tools": ["Read"]}}
        settings = {"playwright": {"enabled": False}}

        updated = add_playwright_tools_to_spec(spec, settings)
        assert "mcp__playwright__browser_navigate" not in updated["tool_policy"]["allowed_tools"]

    def test_tools_added_when_enabled(self):
        """Test tools are added when Playwright is enabled."""
        spec = {"name": "test", "tool_policy": {"allowed_tools": ["Read"]}}
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }

        updated = add_playwright_tools_to_spec(spec, settings)
        assert "mcp__playwright__browser_navigate" in updated["tool_policy"]["allowed_tools"]

    def test_e2e_agent_respects_settings(self):
        """Test E2E agent respects project settings."""
        # With Playwright enabled
        enabled_settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        result = configure_playwright_for_agent("e2e-agent", enabled_settings)
        assert result.success is True

        # With Playwright disabled
        disabled_settings = {"playwright": {"enabled": False}}
        result = configure_playwright_for_agent("e2e-agent", disabled_settings)
        assert result.success is False


# =============================================================================
# Test Data Classes
# =============================================================================

class TestDataClasses:
    """Test data class functionality."""

    def test_playwright_mcp_config_defaults(self):
        """Test PlaywrightMcpConfig default values."""
        config = PlaywrightMcpConfig()
        assert config.enabled is False
        assert config.headless is True
        assert config.browser == DEFAULT_BROWSER
        assert config.timeout_ms == DEFAULT_TIMEOUT_MS
        assert config.viewport == DEFAULT_VIEWPORT
        assert config.tool_set == "extended"

    def test_playwright_mcp_config_to_dict(self):
        """Test PlaywrightMcpConfig serialization."""
        config = PlaywrightMcpConfig(enabled=True, browser="firefox")
        data = config.to_dict()

        assert data["enabled"] is True
        assert data["browser"] == "firefox"
        assert "mcp_server_config" in data

    def test_playwright_mcp_config_from_dict(self):
        """Test PlaywrightMcpConfig deserialization."""
        data = {"enabled": True, "browser": "webkit", "timeout_ms": 45000}
        config = PlaywrightMcpConfig.from_dict(data)

        assert config.enabled is True
        assert config.browser == "webkit"
        assert config.timeout_ms == 45000

    def test_playwright_agent_config_result_success(self):
        """Test PlaywrightAgentConfigResult success case."""
        result = PlaywrightAgentConfigResult(
            success=True,
            tools_added=["browser_navigate", "browser_click"],
        )
        assert result.success is True
        assert len(result.tools_added) == 2
        assert result.error is None

    def test_playwright_agent_config_result_to_dict(self):
        """Test PlaywrightAgentConfigResult serialization."""
        result = PlaywrightAgentConfigResult(success=True)
        data = result.to_dict()

        assert data["success"] is True
        assert "tools_added" in data

    def test_mcp_connection_result_connected(self):
        """Test McpConnectionResult connected case."""
        result = McpConnectionResult(
            connected=True,
            tools_available=CORE_PLAYWRIGHT_TOOLS,
        )
        assert result.connected is True
        assert len(result.tools_available) > 0

    def test_mcp_connection_result_to_dict(self):
        """Test McpConnectionResult serialization."""
        result = McpConnectionResult(connected=False, error="Test error")
        data = result.to_dict()

        assert data["connected"] is False
        assert data["error"] == "Test error"


# =============================================================================
# Test API Package Exports
# =============================================================================

class TestApiPackageExports:
    """Test that all Feature #213 components are exported from api package."""

    def test_enums_exported(self):
        """Test enums are exported."""
        from api import PlaywrightMode, PlaywrightToolSet
        assert PlaywrightMode.HEADLESS.value == "headless"
        assert PlaywrightToolSet.CORE.value == "core"

    def test_data_classes_exported(self):
        """Test data classes are exported."""
        from api import (
            PlaywrightMcpConfig,
            PlaywrightAgentConfigResult,
            McpConnectionResult,
        )
        config = PlaywrightMcpConfig()
        assert config is not None

    def test_configuration_functions_exported(self):
        """Test configuration functions are exported."""
        from api import (
            get_playwright_config,
            is_playwright_enabled,
            enable_playwright,
            disable_playwright,
        )
        assert callable(get_playwright_config)
        assert callable(is_playwright_enabled)

    def test_tool_selection_functions_exported(self):
        """Test tool selection functions are exported."""
        from api import (
            get_playwright_tools,
            configure_playwright_for_agent,
            add_playwright_tools_to_spec,
            is_e2e_agent,
        )
        assert callable(get_playwright_tools)
        assert callable(is_e2e_agent)

    def test_mcp_functions_exported(self):
        """Test MCP functions are exported."""
        from api import (
            get_mcp_server_config,
            verify_mcp_connection,
            ensure_playwright_in_settings,
        )
        assert callable(get_mcp_server_config)
        assert callable(verify_mcp_connection)

    def test_constants_exported(self):
        """Test constants are exported."""
        from api import (
            PLAYWRIGHT_TOOLS,
            CORE_PLAYWRIGHT_TOOLS,
            EXTENDED_PLAYWRIGHT_TOOLS,
            PLAYWRIGHT_TOOL_SETS,
            SUPPORTED_BROWSERS,
            DEFAULT_BROWSER,
            DEFAULT_PLAYWRIGHT_MCP_CONFIG,
        )
        assert len(PLAYWRIGHT_TOOLS) > 0
        assert DEFAULT_BROWSER == "chromium"


# =============================================================================
# Test Feature #213 Verification Steps (Comprehensive)
# =============================================================================

class TestFeature213VerificationSteps:
    """Comprehensive tests for Feature #213 verification steps."""

    def test_step1_playwright_mcp_server_configurable_in_settings(self):
        """
        Feature #213 Step 1: Playwright MCP server configurable in settings.

        Verifies that:
        - Playwright can be configured via project settings
        - Configuration includes server command and args
        - Settings are properly parsed and validated
        """
        # Test configuration from settings
        settings = {
            "playwright": {
                "enabled": True,
                "headless": True,
                "browser": "chromium",
            },
            "mcpServers": {
                "playwright": {
                    "command": "npx",
                    "args": ["@anthropic/mcp-server-playwright", "--headless"],
                }
            }
        }
        config = get_playwright_config(settings)

        assert config.enabled is True, "Playwright should be enabled"
        assert config.headless is True, "Headless mode should be True"
        assert config.browser == "chromium", "Browser should be chromium"
        assert config.mcp_server_config["command"] == "npx"

    def test_step2_test_runner_agents_for_e2e_include_playwright_tools(self):
        """
        Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.

        Verifies that:
        - E2E agents are correctly identified
        - Playwright tools are added to E2E agents
        - Non-E2E agents don't get Playwright tools
        """
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }

        # E2E agent detection
        assert is_e2e_agent(agent_name="e2e-tester") is True
        assert is_e2e_agent(capability="browser_automation") is True
        assert is_e2e_agent(agent_name="regular-coder") is False

        # E2E agent tools include Playwright
        tools = get_e2e_agent_tools(settings)
        assert "mcp__playwright__browser_navigate" in tools
        assert "mcp__playwright__browser_click" in tools

        # should_include_playwright_tools respects both E2E detection and settings
        assert should_include_playwright_tools(
            agent_name="e2e-tester",
            project_settings=settings,
        ) is True
        assert should_include_playwright_tools(
            agent_name="coder",
            project_settings=settings,
        ) is False

    def test_step3_mcp_connection_established_when_agent_starts(self):
        """
        Feature #213 Step 3: MCP connection established when agent starts.

        Verifies that:
        - MCP server configuration is correct
        - Connection verification passes with valid config
        - Settings file can be updated with Playwright MCP
        """
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }

        # Get MCP server config
        mcp_config = get_mcp_server_config(settings)
        assert mcp_config["command"] == "npx"
        assert "@anthropic/mcp-server-playwright" in mcp_config["args"]

        # Verify connection
        result = verify_mcp_connection(settings)
        assert result.connected is True
        assert result.server_name == "playwright"
        assert len(result.tools_available) > 0

    def test_step4_playwright_actions_available(self):
        """
        Feature #213 Step 4: Playwright actions available: navigate, click, fill, assert.

        Verifies that all required Playwright actions are available:
        - navigate: browser_navigate
        - click: browser_click
        - fill: browser_fill_form, browser_type
        - assert: browser_snapshot, browser_take_screenshot, browser_console_messages
        """
        tools = get_playwright_tools(tool_set="core")

        # Navigate action
        assert "mcp__playwright__browser_navigate" in tools, "Navigate action required"

        # Click action
        assert "mcp__playwright__browser_click" in tools, "Click action required"

        # Fill actions
        assert "mcp__playwright__browser_fill_form" in tools, "Fill form action required"
        assert "mcp__playwright__browser_type" in tools, "Type action required"

        # Assert actions (observation tools)
        assert "mcp__playwright__browser_snapshot" in tools, "Snapshot action required"
        assert "mcp__playwright__browser_take_screenshot" in tools, "Screenshot action required"
        assert "mcp__playwright__browser_console_messages" in tools, "Console messages required"

    def test_step5_configuration_gated_by_project_settings(self):
        """
        Feature #213 Step 5: Configuration gated by project settings.

        Verifies that:
        - Playwright is disabled by default
        - Tools are only available when explicitly enabled
        - Agents respect the configuration gating
        """
        # Playwright is disabled by default
        assert is_playwright_enabled(None) is False
        assert is_playwright_enabled({}) is False

        # Tools are only available when enabled
        disabled_spec = {"name": "test", "tool_policy": {"allowed_tools": []}}
        disabled_settings = {"playwright": {"enabled": False}}
        updated = add_playwright_tools_to_spec(disabled_spec.copy(), disabled_settings)
        assert "mcp__playwright__browser_navigate" not in updated["tool_policy"]["allowed_tools"]

        # With enabled settings
        enabled_settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        enabled_spec = {"name": "test", "tool_policy": {"allowed_tools": []}}
        updated = add_playwright_tools_to_spec(enabled_spec, enabled_settings)
        assert "mcp__playwright__browser_navigate" in updated["tool_policy"]["allowed_tools"]

        # Agents respect configuration
        result = configure_playwright_for_agent("e2e-agent", disabled_settings)
        assert result.success is False

        result = configure_playwright_for_agent("e2e-agent", enabled_settings)
        assert result.success is True


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_browser_defaults_to_chromium(self):
        """Test invalid browser name defaults to chromium."""
        config = PlaywrightMcpConfig(browser="safari")  # Not supported
        assert config.browser == DEFAULT_BROWSER

    def test_viewport_validation(self):
        """Test viewport dimension validation."""
        # Too small
        config = PlaywrightMcpConfig(viewport={"width": 100, "height": 100})
        assert config.viewport["width"] >= 320
        assert config.viewport["height"] >= 240

        # Too large
        config = PlaywrightMcpConfig(viewport={"width": 10000, "height": 10000})
        assert config.viewport["width"] <= 3840
        assert config.viewport["height"] <= 2160

    def test_invalid_tool_set_defaults(self):
        """Test invalid tool set defaults to extended."""
        config = PlaywrightMcpConfig(tool_set="invalid")
        assert config.tool_set == "extended"

    def test_empty_spec_tool_policy(self):
        """Test adding tools to spec without tool_policy."""
        spec = {"name": "test"}
        settings = {
            "playwright": {"enabled": True},
            "mcpServers": {"playwright": DEFAULT_PLAYWRIGHT_MCP_CONFIG},
        }
        updated = add_playwright_tools_to_spec(spec, settings)

        assert "tool_policy" in updated
        assert "allowed_tools" in updated["tool_policy"]
        assert "mcp__playwright__browser_navigate" in updated["tool_policy"]["allowed_tools"]

    def test_cache_functions(self):
        """Test cache functions work correctly."""
        reset_playwright_config_cache()

        config1 = get_cached_playwright_config({"playwright": {"enabled": True}})
        assert config1.enabled is True

        # Cache should be updated
        reset_playwright_config_cache()
        config2 = get_cached_playwright_config(None)
        assert config2.enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
