"""
Playwright MCP Configuration for E2E Test Agents (Feature #213)
===============================================================

This module provides configuration and management for Playwright MCP server
integration with E2E test agents. It handles:

1. Playwright MCP server configuration in project settings
2. E2E test-runner agent tool provisioning
3. MCP connection establishment when agent starts
4. Playwright action availability (navigate, click, fill, assert)
5. Configuration gating by project settings

Feature #213: Playwright MCP available for E2E test agents

Usage:
    from api.playwright_mcp_config import (
        PlaywrightMcpConfig,
        get_playwright_config,
        is_playwright_enabled,
        get_playwright_tools,
        configure_playwright_for_agent,
    )

    # Check if Playwright is enabled
    if is_playwright_enabled(project_settings):
        config = get_playwright_config(project_settings)
        tools = get_playwright_tools(config)

    # Configure an agent for E2E testing
    result = configure_playwright_for_agent(
        agent_name="e2e-tester-agent",
        project_settings=settings,
    )
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants (Feature #213 Step 1)
# =============================================================================

# Feature #213 Step 1: Playwright MCP server configurable in settings

# Settings key paths
SETTINGS_PLAYWRIGHT_SECTION = "playwright"
SETTINGS_MCP_SECTION = "mcpServers"
SETTINGS_ENABLED_KEY = "enabled"
SETTINGS_HEADLESS_KEY = "headless"
SETTINGS_BROWSER_KEY = "browser"
SETTINGS_TIMEOUT_KEY = "timeout"
SETTINGS_VIEWPORT_KEY = "viewport"

# Default Playwright MCP server configuration
DEFAULT_PLAYWRIGHT_MCP_CONFIG: dict[str, Any] = {
    "command": "npx",
    "args": ["@anthropic/mcp-server-playwright", "--headless"],
    "env": {},
}

# Headful mode configuration (for debugging)
HEADFUL_PLAYWRIGHT_MCP_CONFIG: dict[str, Any] = {
    "command": "npx",
    "args": ["@anthropic/mcp-server-playwright"],
    "env": {},
}

# Supported browsers
SUPPORTED_BROWSERS = ["chromium", "firefox", "webkit"]
DEFAULT_BROWSER = "chromium"

# Default timeout in milliseconds
DEFAULT_TIMEOUT_MS = 30000
MIN_TIMEOUT_MS = 5000
MAX_TIMEOUT_MS = 300000

# Default viewport dimensions
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
MIN_VIEWPORT_WIDTH = 320
MIN_VIEWPORT_HEIGHT = 240
MAX_VIEWPORT_WIDTH = 3840
MAX_VIEWPORT_HEIGHT = 2160

# Feature #213 Step 4: Playwright actions available: navigate, click, fill, assert
# All available Playwright MCP tools
PLAYWRIGHT_TOOLS: list[str] = [
    # Navigation
    "mcp__playwright__browser_navigate",
    "mcp__playwright__browser_navigate_back",
    # Interaction - Feature #213 Step 4: click, fill
    "mcp__playwright__browser_click",
    "mcp__playwright__browser_type",
    "mcp__playwright__browser_fill_form",
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_drag",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_press_key",
    "mcp__playwright__browser_file_upload",
    # Observation/Assert - Feature #213 Step 4: assert
    "mcp__playwright__browser_snapshot",
    "mcp__playwright__browser_take_screenshot",
    "mcp__playwright__browser_console_messages",
    "mcp__playwright__browser_network_requests",
    # Utility
    "mcp__playwright__browser_wait_for",
    "mcp__playwright__browser_evaluate",
    "mcp__playwright__browser_handle_dialog",
    "mcp__playwright__browser_resize",
    "mcp__playwright__browser_tabs",
    "mcp__playwright__browser_close",
    "mcp__playwright__browser_install",
    "mcp__playwright__browser_run_code",
]

# Core Playwright tools for basic E2E testing
# Feature #213 Step 4: navigate, click, fill, assert
CORE_PLAYWRIGHT_TOOLS: list[str] = [
    "mcp__playwright__browser_navigate",       # navigate
    "mcp__playwright__browser_click",          # click
    "mcp__playwright__browser_fill_form",      # fill
    "mcp__playwright__browser_type",           # fill (text input)
    "mcp__playwright__browser_snapshot",       # assert (accessibility)
    "mcp__playwright__browser_take_screenshot", # assert (visual)
    "mcp__playwright__browser_console_messages", # assert (errors)
]

# Extended Playwright tools for advanced testing
EXTENDED_PLAYWRIGHT_TOOLS: list[str] = [
    # Additional interaction
    "mcp__playwright__browser_hover",
    "mcp__playwright__browser_select_option",
    "mcp__playwright__browser_press_key",
    # Navigation
    "mcp__playwright__browser_navigate_back",
    # Utilities
    "mcp__playwright__browser_wait_for",
    "mcp__playwright__browser_network_requests",
]

# Tool sets for different use cases
PLAYWRIGHT_TOOL_SETS: dict[str, list[str]] = {
    "core": CORE_PLAYWRIGHT_TOOLS,
    "extended": CORE_PLAYWRIGHT_TOOLS + EXTENDED_PLAYWRIGHT_TOOLS,
    "full": PLAYWRIGHT_TOOLS,
}


# =============================================================================
# Enums
# =============================================================================

class PlaywrightMode(str, Enum):
    """Mode for Playwright execution."""
    HEADLESS = "headless"
    HEADFUL = "headful"


class PlaywrightToolSet(str, Enum):
    """Predefined tool sets for Playwright."""
    CORE = "core"
    EXTENDED = "extended"
    FULL = "full"


# =============================================================================
# Data Classes (Feature #213 Step 1 & 5)
# =============================================================================

@dataclass
class PlaywrightMcpConfig:
    """
    Configuration for Playwright MCP server.

    Feature #213 Step 1: Playwright MCP server configurable in settings.
    Feature #213 Step 5: Configuration gated by project settings.

    Attributes:
        enabled: Whether Playwright MCP is enabled for this project
        headless: Whether to run in headless mode (default True)
        browser: Browser to use (chromium, firefox, webkit)
        timeout_ms: Default timeout for Playwright operations
        viewport: Default viewport dimensions
        tool_set: Which tool set to use (core, extended, full)
        mcp_server_config: Configuration for the MCP server process
    """
    enabled: bool = False
    headless: bool = True
    browser: str = DEFAULT_BROWSER
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    viewport: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_VIEWPORT))
    tool_set: str = "extended"
    mcp_server_config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and set defaults after initialization."""
        # Validate browser
        if self.browser not in SUPPORTED_BROWSERS:
            _logger.warning(
                "Invalid browser '%s', defaulting to '%s'",
                self.browser, DEFAULT_BROWSER
            )
            self.browser = DEFAULT_BROWSER

        # Validate timeout
        if self.timeout_ms < MIN_TIMEOUT_MS:
            self.timeout_ms = MIN_TIMEOUT_MS
        elif self.timeout_ms > MAX_TIMEOUT_MS:
            self.timeout_ms = MAX_TIMEOUT_MS

        # Validate viewport
        if not self.viewport:
            self.viewport = dict(DEFAULT_VIEWPORT)
        else:
            if self.viewport.get("width", 0) < MIN_VIEWPORT_WIDTH:
                self.viewport["width"] = MIN_VIEWPORT_WIDTH
            elif self.viewport.get("width", 0) > MAX_VIEWPORT_WIDTH:
                self.viewport["width"] = MAX_VIEWPORT_WIDTH

            if self.viewport.get("height", 0) < MIN_VIEWPORT_HEIGHT:
                self.viewport["height"] = MIN_VIEWPORT_HEIGHT
            elif self.viewport.get("height", 0) > MAX_VIEWPORT_HEIGHT:
                self.viewport["height"] = MAX_VIEWPORT_HEIGHT

        # Validate tool set
        if self.tool_set not in PLAYWRIGHT_TOOL_SETS:
            self.tool_set = "extended"

        # Set default MCP server config if not provided
        if not self.mcp_server_config:
            self.mcp_server_config = (
                dict(DEFAULT_PLAYWRIGHT_MCP_CONFIG) if self.headless
                else dict(HEADFUL_PLAYWRIGHT_MCP_CONFIG)
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "headless": self.headless,
            "browser": self.browser,
            "timeout_ms": self.timeout_ms,
            "viewport": self.viewport,
            "tool_set": self.tool_set,
            "mcp_server_config": self.mcp_server_config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaywrightMcpConfig":
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            headless=data.get("headless", True),
            browser=data.get("browser", DEFAULT_BROWSER),
            timeout_ms=data.get("timeout_ms", DEFAULT_TIMEOUT_MS),
            viewport=data.get("viewport", dict(DEFAULT_VIEWPORT)),
            tool_set=data.get("tool_set", "extended"),
            mcp_server_config=data.get("mcp_server_config", {}),
        )


@dataclass
class PlaywrightAgentConfigResult:
    """
    Result of configuring an agent for Playwright.

    Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.

    Attributes:
        success: Whether configuration succeeded
        tools_added: List of Playwright tools added to the agent
        mcp_server_name: Name of the MCP server in settings
        settings_updated: Whether project settings were updated
        error: Error message if failed
    """
    success: bool
    tools_added: list[str] = field(default_factory=list)
    mcp_server_name: str = "playwright"
    settings_updated: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "tools_added": self.tools_added,
            "mcp_server_name": self.mcp_server_name,
            "settings_updated": self.settings_updated,
            "error": self.error,
        }


@dataclass
class McpConnectionResult:
    """
    Result of MCP connection establishment.

    Feature #213 Step 3: MCP connection established when agent starts.

    Attributes:
        connected: Whether connection was established
        server_name: Name of the MCP server
        tools_available: Tools available from the server
        server_version: Version of the MCP server
        error: Error message if connection failed
    """
    connected: bool
    server_name: str = "playwright"
    tools_available: list[str] = field(default_factory=list)
    server_version: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "connected": self.connected,
            "server_name": self.server_name,
            "tools_available": self.tools_available,
            "server_version": self.server_version,
            "error": self.error,
        }


# =============================================================================
# Configuration Functions (Feature #213 Step 1 & 5)
# =============================================================================

def get_playwright_config(
    project_settings: dict[str, Any] | None = None,
) -> PlaywrightMcpConfig:
    """
    Get Playwright configuration from project settings.

    Feature #213 Step 1: Playwright MCP server configurable in settings.
    Feature #213 Step 5: Configuration gated by project settings.

    Args:
        project_settings: Project settings dictionary

    Returns:
        PlaywrightMcpConfig with settings or defaults
    """
    if not project_settings:
        return PlaywrightMcpConfig(enabled=False)

    # Check for playwright section in settings
    playwright_section = project_settings.get(SETTINGS_PLAYWRIGHT_SECTION, {})

    # Check if Playwright is explicitly enabled
    enabled = playwright_section.get(SETTINGS_ENABLED_KEY, False)

    # Also check mcpServers for playwright server
    mcp_servers = project_settings.get(SETTINGS_MCP_SECTION, {})
    if "playwright" in mcp_servers:
        enabled = True

    config = PlaywrightMcpConfig(
        enabled=enabled,
        headless=playwright_section.get(SETTINGS_HEADLESS_KEY, True),
        browser=playwright_section.get(SETTINGS_BROWSER_KEY, DEFAULT_BROWSER),
        timeout_ms=playwright_section.get(SETTINGS_TIMEOUT_KEY, DEFAULT_TIMEOUT_MS),
        viewport=playwright_section.get(SETTINGS_VIEWPORT_KEY, dict(DEFAULT_VIEWPORT)),
        tool_set=playwright_section.get("tool_set", "extended"),
        mcp_server_config=mcp_servers.get("playwright", {}),
    )

    return config


def is_playwright_enabled(
    project_settings: dict[str, Any] | None = None,
) -> bool:
    """
    Check if Playwright MCP is enabled in project settings.

    Feature #213 Step 5: Configuration gated by project settings.

    Args:
        project_settings: Project settings dictionary

    Returns:
        True if Playwright is enabled
    """
    config = get_playwright_config(project_settings)
    return config.enabled


def enable_playwright(
    project_settings: dict[str, Any],
    headless: bool = True,
    browser: str = DEFAULT_BROWSER,
) -> dict[str, Any]:
    """
    Enable Playwright in project settings.

    Feature #213 Step 1: Playwright MCP server configurable in settings.

    Args:
        project_settings: Project settings dictionary (modified in place)
        headless: Whether to run in headless mode
        browser: Browser to use

    Returns:
        Updated project settings
    """
    # Ensure playwright section exists
    if SETTINGS_PLAYWRIGHT_SECTION not in project_settings:
        project_settings[SETTINGS_PLAYWRIGHT_SECTION] = {}

    playwright_section = project_settings[SETTINGS_PLAYWRIGHT_SECTION]
    playwright_section[SETTINGS_ENABLED_KEY] = True
    playwright_section[SETTINGS_HEADLESS_KEY] = headless
    playwright_section[SETTINGS_BROWSER_KEY] = browser

    # Ensure mcpServers section exists with playwright server
    if SETTINGS_MCP_SECTION not in project_settings:
        project_settings[SETTINGS_MCP_SECTION] = {}

    mcp_server_config = (
        dict(DEFAULT_PLAYWRIGHT_MCP_CONFIG) if headless
        else dict(HEADFUL_PLAYWRIGHT_MCP_CONFIG)
    )
    project_settings[SETTINGS_MCP_SECTION]["playwright"] = mcp_server_config

    _logger.info(
        "Enabled Playwright MCP: headless=%s, browser=%s",
        headless, browser
    )

    return project_settings


def disable_playwright(project_settings: dict[str, Any]) -> dict[str, Any]:
    """
    Disable Playwright in project settings.

    Args:
        project_settings: Project settings dictionary (modified in place)

    Returns:
        Updated project settings
    """
    if SETTINGS_PLAYWRIGHT_SECTION in project_settings:
        project_settings[SETTINGS_PLAYWRIGHT_SECTION][SETTINGS_ENABLED_KEY] = False

    if SETTINGS_MCP_SECTION in project_settings:
        project_settings[SETTINGS_MCP_SECTION].pop("playwright", None)

    _logger.info("Disabled Playwright MCP")
    return project_settings


# =============================================================================
# Tool Selection Functions (Feature #213 Step 2 & 4)
# =============================================================================

def get_playwright_tools(
    config: PlaywrightMcpConfig | None = None,
    tool_set: str | None = None,
) -> list[str]:
    """
    Get Playwright tools based on configuration.

    Feature #213 Step 4: Playwright actions available: navigate, click, fill, assert.

    Args:
        config: Playwright configuration (optional)
        tool_set: Tool set to use ("core", "extended", "full")

    Returns:
        List of Playwright tool names
    """
    # Determine which tool set to use
    if tool_set:
        selected_set = tool_set
    elif config:
        selected_set = config.tool_set
    else:
        selected_set = "extended"

    return list(PLAYWRIGHT_TOOL_SETS.get(selected_set, CORE_PLAYWRIGHT_TOOLS))


def configure_playwright_for_agent(
    agent_name: str,
    project_settings: dict[str, Any] | None = None,
    tool_set: str = "extended",
) -> PlaywrightAgentConfigResult:
    """
    Configure an agent for Playwright E2E testing.

    Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.

    Args:
        agent_name: Name of the agent
        project_settings: Project settings dictionary
        tool_set: Tool set to use ("core", "extended", "full")

    Returns:
        PlaywrightAgentConfigResult with configuration status
    """
    # Check if Playwright is enabled
    if not is_playwright_enabled(project_settings):
        return PlaywrightAgentConfigResult(
            success=False,
            error="Playwright is not enabled in project settings",
        )

    # Get Playwright configuration
    config = get_playwright_config(project_settings)

    # Get tools for this agent
    tools = get_playwright_tools(config, tool_set)

    _logger.info(
        "Configured agent '%s' with %d Playwright tools",
        agent_name, len(tools)
    )

    return PlaywrightAgentConfigResult(
        success=True,
        tools_added=tools,
        mcp_server_name="playwright",
        settings_updated=False,
    )


def add_playwright_tools_to_spec(
    spec_dict: dict[str, Any],
    project_settings: dict[str, Any] | None = None,
    tool_set: str = "extended",
) -> dict[str, Any]:
    """
    Add Playwright tools to an AgentSpec dictionary.

    Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.

    Args:
        spec_dict: AgentSpec as dictionary (modified in place)
        project_settings: Project settings dictionary
        tool_set: Tool set to use

    Returns:
        Updated spec dictionary
    """
    if not is_playwright_enabled(project_settings):
        _logger.debug("Playwright not enabled, skipping tool addition")
        return spec_dict

    config = get_playwright_config(project_settings)
    tools = get_playwright_tools(config, tool_set)

    # Ensure tool_policy exists
    if "tool_policy" not in spec_dict:
        spec_dict["tool_policy"] = {}

    tool_policy = spec_dict["tool_policy"]

    # Ensure allowed_tools exists and is a list
    if "allowed_tools" not in tool_policy:
        tool_policy["allowed_tools"] = []

    allowed_tools = tool_policy["allowed_tools"]
    if isinstance(allowed_tools, list):
        # Add Playwright tools that aren't already present
        for tool in tools:
            if tool not in allowed_tools:
                allowed_tools.append(tool)

    _logger.debug(
        "Added %d Playwright tools to spec '%s'",
        len(tools), spec_dict.get("name", "unknown")
    )

    return spec_dict


def is_e2e_agent(
    agent_name: str | None = None,
    capability: str | None = None,
    task_type: str | None = None,
) -> bool:
    """
    Determine if an agent is an E2E testing agent.

    Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.

    Args:
        agent_name: Agent name
        capability: Agent capability
        task_type: Task type

    Returns:
        True if the agent is an E2E testing agent
    """
    e2e_keywords = [
        "e2e", "end-to-end", "browser", "ui_testing", "ui-testing",
        "playwright", "frontend_testing", "web_testing",
    ]

    # Check agent name
    if agent_name:
        name_lower = agent_name.lower().replace("-", "_")
        if any(kw.replace("-", "_") in name_lower for kw in e2e_keywords):
            return True

    # Check capability
    if capability:
        cap_lower = capability.lower().replace("-", "_")
        if any(kw.replace("-", "_") in cap_lower for kw in e2e_keywords):
            return True

    # Check task type
    if task_type:
        if task_type.lower() in ["e2e", "e2e_testing", "browser_testing"]:
            return True

    return False


# =============================================================================
# MCP Connection Functions (Feature #213 Step 3)
# =============================================================================

def get_mcp_server_config(
    project_settings: dict[str, Any] | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """
    Get MCP server configuration for Playwright.

    Feature #213 Step 3: MCP connection established when agent starts.

    Args:
        project_settings: Project settings dictionary
        headless: Whether to run in headless mode

    Returns:
        MCP server configuration dictionary
    """
    if project_settings:
        mcp_servers = project_settings.get(SETTINGS_MCP_SECTION, {})
        if "playwright" in mcp_servers:
            return dict(mcp_servers["playwright"])

    # Return default configuration
    return (
        dict(DEFAULT_PLAYWRIGHT_MCP_CONFIG) if headless
        else dict(HEADFUL_PLAYWRIGHT_MCP_CONFIG)
    )


def verify_mcp_connection(
    project_settings: dict[str, Any] | None = None,
) -> McpConnectionResult:
    """
    Verify that Playwright MCP connection can be established.

    Feature #213 Step 3: MCP connection established when agent starts.

    This is a pre-flight check to ensure the MCP server is properly configured.
    The actual connection is established by Claude Code when the agent starts.

    Args:
        project_settings: Project settings dictionary

    Returns:
        McpConnectionResult with connection status
    """
    if not is_playwright_enabled(project_settings):
        return McpConnectionResult(
            connected=False,
            error="Playwright is not enabled in project settings",
        )

    config = get_playwright_config(project_settings)

    # Check for required MCP server configuration
    mcp_config = config.mcp_server_config
    if not mcp_config:
        return McpConnectionResult(
            connected=False,
            error="MCP server configuration is missing",
        )

    if "command" not in mcp_config:
        return McpConnectionResult(
            connected=False,
            error="MCP server 'command' is not specified",
        )

    # Get available tools
    tools = get_playwright_tools(config)

    # Configuration looks valid
    return McpConnectionResult(
        connected=True,
        server_name="playwright",
        tools_available=tools,
        server_version=None,  # Version determined at runtime
    )


def ensure_playwright_in_settings(
    project_dir: Path | str,
    headless: bool = True,
) -> bool:
    """
    Ensure Playwright MCP is configured in settings.local.json.

    Feature #213 Step 3: MCP connection established when agent starts.

    This function ensures the settings file has the Playwright MCP server
    configured so that Claude Code can establish the connection.

    Args:
        project_dir: Project directory path
        headless: Whether to run in headless mode

    Returns:
        True if settings were updated or already configured
    """
    from api.settings_manager import SettingsManager

    manager = SettingsManager(project_dir)
    settings = manager.load_settings()

    # Check if playwright is already configured
    mcp_servers = settings.get("mcpServers", {})
    if "playwright" in mcp_servers:
        _logger.debug("Playwright MCP already configured in settings")
        return True

    # Add playwright server configuration
    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    mcp_config = (
        dict(DEFAULT_PLAYWRIGHT_MCP_CONFIG) if headless
        else dict(HEADFUL_PLAYWRIGHT_MCP_CONFIG)
    )
    settings["mcpServers"]["playwright"] = mcp_config

    # Write updated settings
    result = manager.update_settings(
        tools=["mcp__playwright__browser_navigate"]  # Trigger playwright detection
    )

    if result.success:
        _logger.info("Added Playwright MCP to settings.local.json")
        return True

    _logger.error("Failed to update settings: %s", result.error)
    return False


# =============================================================================
# Agent Archetype Integration (Feature #213 Step 2)
# =============================================================================

def get_e2e_agent_tools(
    project_settings: dict[str, Any] | None = None,
) -> list[str]:
    """
    Get the complete tool list for an E2E testing agent.

    Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.

    Combines standard test-runner tools with Playwright tools.

    Args:
        project_settings: Project settings dictionary

    Returns:
        List of tool names for E2E testing
    """
    # Base tools for test-runner (from archetypes.py e2e-tester)
    base_tools = [
        "Read", "Glob", "Grep", "Bash",
        "feature_get_by_id", "feature_mark_passing", "feature_mark_failing",
    ]

    # Add Playwright tools if enabled
    if is_playwright_enabled(project_settings):
        config = get_playwright_config(project_settings)
        playwright_tools = get_playwright_tools(config)
        base_tools.extend(playwright_tools)

    return base_tools


def should_include_playwright_tools(
    agent_name: str | None = None,
    capability: str | None = None,
    task_type: str | None = None,
    project_settings: dict[str, Any] | None = None,
) -> bool:
    """
    Determine if Playwright tools should be included for an agent.

    Feature #213 Step 2: Test-runner agents for E2E include Playwright tools.
    Feature #213 Step 5: Configuration gated by project settings.

    Args:
        agent_name: Agent name
        capability: Agent capability
        task_type: Task type
        project_settings: Project settings dictionary

    Returns:
        True if Playwright tools should be included
    """
    # First check if it's an E2E agent
    if not is_e2e_agent(agent_name, capability, task_type):
        return False

    # Then check if Playwright is enabled in settings
    return is_playwright_enabled(project_settings)


# =============================================================================
# Module-level convenience functions
# =============================================================================

_cached_config: PlaywrightMcpConfig | None = None


def get_cached_playwright_config(
    project_settings: dict[str, Any] | None = None,
) -> PlaywrightMcpConfig:
    """
    Get cached Playwright configuration.

    Args:
        project_settings: Project settings dictionary

    Returns:
        PlaywrightMcpConfig (cached if settings unchanged)
    """
    global _cached_config
    if _cached_config is None or project_settings is not None:
        _cached_config = get_playwright_config(project_settings)
    return _cached_config


def reset_playwright_config_cache() -> None:
    """Reset the cached Playwright configuration."""
    global _cached_config
    _cached_config = None
