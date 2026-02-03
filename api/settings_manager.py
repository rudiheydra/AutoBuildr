"""
Settings Manager - Manage .claude/settings.local.json for Agent Execution
==========================================================================

Feature #198: Agent Materializer generates settings.local.json when needed.

This module provides functionality to:
1. Check if .claude/settings.local.json exists
2. Create with default permissions if missing
3. Include MCP server configuration if agents require it
4. Preserve existing settings when updating
5. Settings enable agent execution via Claude CLI

Claude Code Settings Reference:
- .claude/settings.local.json contains local project settings
- permissions.allow: List of allowed bash command patterns
- mcpServers: MCP server configurations for tool access
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default settings file location
SETTINGS_LOCAL_FILE = "settings.local.json"

# Default Claude directory
CLAUDE_DIR = ".claude"

# Default permissions for settings file (rw-r--r--)
DEFAULT_SETTINGS_PERMISSIONS = 0o644

# Default settings structure for Claude Code
DEFAULT_SETTINGS: dict[str, Any] = {
    "permissions": {
        "allow": []
    }
}

# Common MCP server configurations for agents
MCP_SERVER_CONFIGS: dict[str, dict[str, Any]] = {
    "features": {
        "command": "uv",
        "args": ["run", "--with", "mcp", "mcp_features_server"],
        "env": {}
    },
    "playwright": {
        "command": "npx",
        "args": ["@anthropic/mcp-server-playwright", "--headless"],
        "env": {}
    },
}

# Tool patterns that suggest MCP server requirements
MCP_TOOL_PATTERNS: dict[str, str] = {
    "mcp__features__": "features",
    "mcp__playwright__": "playwright",
    "feature_get_": "features",
    "feature_mark_": "features",
    "feature_create": "features",
    "browser_": "playwright",
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SettingsUpdateResult:
    """
    Result of updating settings.local.json.

    Feature #198: Agent Materializer generates settings.local.json when needed.

    Attributes:
        success: Whether the update succeeded
        file_path: Path to the settings file
        created: Whether the file was created (vs updated)
        mcp_servers_added: List of MCP server names that were added
        permissions_added: List of permission patterns that were added
        error: Error message if failed
        settings_hash: SHA256 hash of the final settings content
    """
    success: bool
    file_path: Path | None = None
    created: bool = False
    mcp_servers_added: list[str] = field(default_factory=list)
    permissions_added: list[str] = field(default_factory=list)
    error: str | None = None
    settings_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "file_path": str(self.file_path) if self.file_path else None,
            "created": self.created,
            "mcp_servers_added": self.mcp_servers_added,
            "permissions_added": self.permissions_added,
            "error": self.error,
            "settings_hash": self.settings_hash,
        }


@dataclass
class SettingsRequirements:
    """
    Requirements extracted from AgentSpecs for settings.local.json.

    Feature #198: Agent Materializer generates settings.local.json when needed.

    Attributes:
        mcp_servers: Set of MCP server names required
        permissions: Set of permission patterns required
        source_specs: List of spec names that contributed to these requirements
    """
    mcp_servers: set[str] = field(default_factory=set)
    permissions: set[str] = field(default_factory=set)
    source_specs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mcp_servers": sorted(self.mcp_servers),
            "permissions": sorted(self.permissions),
            "source_specs": self.source_specs,
        }


# =============================================================================
# Settings Manager Class
# =============================================================================

class SettingsManager:
    """
    Manages .claude/settings.local.json for agent execution.

    Feature #198: Agent Materializer generates settings.local.json when needed.

    This class handles:
    - Checking if settings file exists
    - Creating with default permissions if missing
    - Including MCP server configuration if agents require it
    - Preserving existing settings when updating
    - Enabling agent execution via Claude CLI
    """

    def __init__(self, project_dir: Path | str):
        """
        Initialize the SettingsManager.

        Args:
            project_dir: Root project directory
        """
        self.project_dir = Path(project_dir).resolve()
        self._claude_dir = self.project_dir / CLAUDE_DIR
        self._settings_path = self._claude_dir / SETTINGS_LOCAL_FILE

    @property
    def settings_path(self) -> Path:
        """Get the absolute path to settings.local.json."""
        return self._settings_path

    @property
    def claude_dir(self) -> Path:
        """Get the absolute path to .claude directory."""
        return self._claude_dir

    # -------------------------------------------------------------------------
    # Step 1: Check if settings file exists
    # -------------------------------------------------------------------------

    def settings_exist(self) -> bool:
        """
        Check if .claude/settings.local.json exists.

        Feature #198 Step 1: Check if .claude/settings.local.json exists.

        Returns:
            True if the settings file exists, False otherwise
        """
        return self._settings_path.exists()

    def get_settings_info(self) -> dict[str, Any]:
        """
        Get information about the current settings file.

        Returns:
            Dictionary with exists, path, permissions, size
        """
        info: dict[str, Any] = {
            "exists": self.settings_exist(),
            "path": str(self._settings_path),
            "permissions": None,
            "size": None,
        }

        if info["exists"]:
            st = self._settings_path.stat()
            info["permissions"] = oct(stat.S_IMODE(st.st_mode))
            info["size"] = st.st_size

        return info

    # -------------------------------------------------------------------------
    # Step 2: Create with default permissions if missing
    # -------------------------------------------------------------------------

    def ensure_claude_dir(self) -> Path:
        """
        Ensure the .claude directory exists.

        Returns:
            Path to the .claude directory
        """
        self._claude_dir.mkdir(parents=True, exist_ok=True)
        return self._claude_dir

    def create_default_settings(self) -> SettingsUpdateResult:
        """
        Create settings.local.json with default content and permissions.

        Feature #198 Step 2: If missing, create with default permissions.

        Returns:
            SettingsUpdateResult indicating success or failure
        """
        try:
            # Ensure .claude directory exists
            self.ensure_claude_dir()

            # Create default settings
            settings = dict(DEFAULT_SETTINGS)

            # Write the file
            content = json.dumps(settings, indent=2) + "\n"
            self._settings_path.write_text(content, encoding="utf-8")

            # Set permissions (rw-r--r--)
            os.chmod(self._settings_path, DEFAULT_SETTINGS_PERMISSIONS)

            # Compute hash
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            _logger.info(
                "Created default settings.local.json at %s (hash: %s)",
                self._settings_path, content_hash[:16],
            )

            return SettingsUpdateResult(
                success=True,
                file_path=self._settings_path,
                created=True,
                settings_hash=content_hash,
            )

        except Exception as e:
            _logger.error(
                "Failed to create settings.local.json: %s", e,
            )
            return SettingsUpdateResult(
                success=False,
                error=str(e),
            )

    # -------------------------------------------------------------------------
    # Step 3: Include MCP server configuration if agents require it
    # -------------------------------------------------------------------------

    def detect_mcp_requirements(
        self,
        specs: list["AgentSpec"] | None = None,
        tools: list[str] | None = None,
    ) -> SettingsRequirements:
        """
        Detect MCP server requirements from AgentSpecs or tool lists.

        Feature #198 Step 3: Include MCP server configuration if agents require it.

        Args:
            specs: List of AgentSpecs to analyze
            tools: List of tool names to analyze

        Returns:
            SettingsRequirements with detected MCP servers and permissions
        """
        requirements = SettingsRequirements()

        # Collect all tools from specs
        all_tools: list[str] = []
        if specs:
            for spec in specs:
                requirements.source_specs.append(spec.name)
                if spec.tool_policy and isinstance(spec.tool_policy, dict):
                    allowed_tools = spec.tool_policy.get("allowed_tools", [])
                    if isinstance(allowed_tools, list):
                        all_tools.extend(allowed_tools)

        # Add explicitly provided tools
        if tools:
            all_tools.extend(tools)

        # Detect MCP servers from tool patterns
        for tool in all_tools:
            tool_lower = tool.lower() if isinstance(tool, str) else ""
            for pattern, server_name in MCP_TOOL_PATTERNS.items():
                if pattern.lower() in tool_lower:
                    requirements.mcp_servers.add(server_name)

        return requirements

    def get_mcp_server_config(self, server_name: str) -> dict[str, Any] | None:
        """
        Get the configuration for a known MCP server.

        Args:
            server_name: Name of the MCP server

        Returns:
            Server configuration dict or None if unknown
        """
        return MCP_SERVER_CONFIGS.get(server_name)

    # -------------------------------------------------------------------------
    # Step 4: Preserve existing settings when updating
    # -------------------------------------------------------------------------

    def load_settings(self) -> dict[str, Any]:
        """
        Load existing settings from settings.local.json.

        Feature #198 Step 4: Preserve existing settings when updating.

        Returns:
            Settings dictionary (empty dict if file doesn't exist or is invalid)
        """
        if not self.settings_exist():
            return {}

        try:
            content = self._settings_path.read_text(encoding="utf-8")
            settings = json.loads(content)
            if not isinstance(settings, dict):
                _logger.warning(
                    "settings.local.json contains non-dict content, treating as empty"
                )
                return {}
            return settings
        except json.JSONDecodeError as e:
            _logger.warning(
                "Failed to parse settings.local.json: %s, treating as empty", e
            )
            return {}
        except Exception as e:
            _logger.warning(
                "Failed to read settings.local.json: %s, treating as empty", e
            )
            return {}

    def merge_settings(
        self,
        existing: dict[str, Any],
        requirements: SettingsRequirements,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """
        Merge requirements into existing settings, preserving existing values.

        Feature #198 Step 4: Preserve existing settings when updating.

        Args:
            existing: Existing settings dictionary
            requirements: New requirements to add

        Returns:
            Tuple of (merged_settings, mcp_servers_added, permissions_added)
        """
        merged = dict(existing)
        mcp_servers_added: list[str] = []
        permissions_added: list[str] = []

        # Ensure base structure exists
        if "permissions" not in merged:
            merged["permissions"] = {}
        if "allow" not in merged["permissions"]:
            merged["permissions"]["allow"] = []

        # Add MCP servers if needed
        if requirements.mcp_servers:
            if "mcpServers" not in merged:
                merged["mcpServers"] = {}

            for server_name in sorted(requirements.mcp_servers):
                if server_name not in merged["mcpServers"]:
                    config = self.get_mcp_server_config(server_name)
                    if config:
                        merged["mcpServers"][server_name] = config
                        mcp_servers_added.append(server_name)
                        _logger.info(
                            "Adding MCP server configuration: %s", server_name
                        )

        # Add permissions if needed
        existing_permissions = set(merged["permissions"]["allow"])
        for permission in sorted(requirements.permissions):
            if permission not in existing_permissions:
                merged["permissions"]["allow"].append(permission)
                permissions_added.append(permission)
                _logger.info(
                    "Adding permission: %s", permission
                )

        return merged, mcp_servers_added, permissions_added

    # -------------------------------------------------------------------------
    # Step 5: Settings enable agent execution via Claude CLI
    # -------------------------------------------------------------------------

    def update_settings(
        self,
        requirements: SettingsRequirements | None = None,
        specs: list["AgentSpec"] | None = None,
        tools: list[str] | None = None,
    ) -> SettingsUpdateResult:
        """
        Update settings.local.json with requirements from agents.

        Feature #198 Step 5: Settings enable agent execution via Claude CLI.

        This is the main entry point for updating settings. It:
        1. Checks if settings file exists
        2. Creates with defaults if missing
        3. Detects MCP requirements from specs/tools
        4. Preserves existing settings when updating
        5. Writes the updated settings

        Args:
            requirements: Pre-computed requirements (if None, computed from specs/tools)
            specs: List of AgentSpecs to analyze for requirements
            tools: List of tool names to analyze for requirements

        Returns:
            SettingsUpdateResult indicating what changed
        """
        try:
            # Detect requirements if not provided
            if requirements is None:
                requirements = self.detect_mcp_requirements(specs=specs, tools=tools)

            # Check if settings exist
            created = not self.settings_exist()

            if created:
                # Ensure .claude directory exists
                self.ensure_claude_dir()
                existing = dict(DEFAULT_SETTINGS)
            else:
                # Load existing settings
                existing = self.load_settings()

            # Merge requirements into existing settings
            merged, mcp_servers_added, permissions_added = self.merge_settings(
                existing, requirements
            )

            # Write the updated settings
            content = json.dumps(merged, indent=2, sort_keys=True) + "\n"
            self._settings_path.write_text(content, encoding="utf-8")

            # Set permissions (rw-r--r--)
            os.chmod(self._settings_path, DEFAULT_SETTINGS_PERMISSIONS)

            # Compute hash
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            _logger.info(
                "Updated settings.local.json at %s (hash: %s, created=%s, "
                "mcp_servers_added=%d, permissions_added=%d)",
                self._settings_path, content_hash[:16], created,
                len(mcp_servers_added), len(permissions_added),
            )

            return SettingsUpdateResult(
                success=True,
                file_path=self._settings_path,
                created=created,
                mcp_servers_added=mcp_servers_added,
                permissions_added=permissions_added,
                settings_hash=content_hash,
            )

        except Exception as e:
            _logger.error(
                "Failed to update settings.local.json: %s", e,
            )
            return SettingsUpdateResult(
                success=False,
                error=str(e),
            )

    def ensure_settings_for_specs(
        self,
        specs: list["AgentSpec"],
    ) -> SettingsUpdateResult:
        """
        Ensure settings.local.json exists and has MCP configuration for the given specs.

        This is a convenience method that combines detection and update.

        Args:
            specs: List of AgentSpecs that will be executed

        Returns:
            SettingsUpdateResult indicating what changed
        """
        requirements = self.detect_mcp_requirements(specs=specs)
        return self.update_settings(requirements=requirements)


# =============================================================================
# Module-level Settings Functions
# =============================================================================

def check_settings_exist(project_dir: Path | str) -> bool:
    """
    Check if .claude/settings.local.json exists in the project.

    Feature #198 Step 1: Check if .claude/settings.local.json exists.

    Args:
        project_dir: Root project directory

    Returns:
        True if settings file exists, False otherwise
    """
    manager = SettingsManager(project_dir)
    return manager.settings_exist()


def ensure_settings_for_agents(
    project_dir: Path | str,
    specs: list["AgentSpec"] | None = None,
    tools: list[str] | None = None,
) -> SettingsUpdateResult:
    """
    Ensure settings.local.json exists and is configured for agent execution.

    Feature #198: Agent Materializer generates settings.local.json when needed.

    This function:
    1. Checks if settings file exists
    2. Creates with defaults if missing
    3. Detects MCP requirements from specs/tools
    4. Updates settings while preserving existing values

    Args:
        project_dir: Root project directory
        specs: List of AgentSpecs to analyze for requirements
        tools: List of tool names to analyze for requirements

    Returns:
        SettingsUpdateResult indicating what changed
    """
    manager = SettingsManager(project_dir)
    return manager.update_settings(specs=specs, tools=tools)


def detect_required_mcp_servers(
    specs: list["AgentSpec"] | None = None,
    tools: list[str] | None = None,
) -> set[str]:
    """
    Detect which MCP servers are required for the given specs/tools.

    Feature #198 Step 3: Include MCP server configuration if agents require it.

    Args:
        specs: List of AgentSpecs to analyze
        tools: List of tool names to analyze

    Returns:
        Set of MCP server names required
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SettingsManager(tmpdir)
        requirements = manager.detect_mcp_requirements(specs=specs, tools=tools)
        return requirements.mcp_servers


def get_settings_manager(project_dir: Path | str) -> SettingsManager:
    """
    Get a SettingsManager instance for the given project directory.

    Args:
        project_dir: Root project directory

    Returns:
        SettingsManager instance
    """
    return SettingsManager(project_dir)
