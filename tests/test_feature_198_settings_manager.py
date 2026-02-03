"""
Tests for Feature #198: Agent Materializer generates settings.local.json when needed

Materializer ensures required settings file exists with necessary permissions and MCP configuration.

Verification Steps:
1. Check if .claude/settings.local.json exists
2. If missing, create with default permissions
3. Include MCP server configuration if agents require it
4. Preserve existing settings when updating
5. Settings enable agent execution via Claude CLI
"""
import json
import os
import stat
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.settings_manager import (
    SettingsManager,
    SettingsUpdateResult,
    SettingsRequirements,
    check_settings_exist,
    ensure_settings_for_agents,
    detect_required_mcp_servers,
    get_settings_manager,
    SETTINGS_LOCAL_FILE,
    CLAUDE_DIR,
    DEFAULT_SETTINGS_PERMISSIONS,
    DEFAULT_SETTINGS,
    MCP_SERVER_CONFIGS,
    MCP_TOOL_PATTERNS,
)
from api.agentspec_models import AgentSpec, generate_uuid


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def settings_manager(temp_project_dir):
    """SettingsManager instance with temp directory."""
    return SettingsManager(temp_project_dir)


@pytest.fixture
def sample_agent_spec():
    """Sample AgentSpec for testing."""
    return AgentSpec(
        id=generate_uuid(),
        name="feature-198-test-agent",
        display_name="Feature 198 Test Agent",
        icon="test",
        spec_version="v1",
        objective="Test agent for Feature #198",
        task_type="coding",
        context={"feature_id": 198},
        tool_policy={
            "allowed_tools": ["Read", "Write", "Edit", "Bash"],
            "forbidden_patterns": ["rm -rf"],
        },
        max_turns=100,
        timeout_seconds=1800,
        source_feature_id=198,
        priority=1,
        tags=["feature-198", "settings", "testing"],
    )


@pytest.fixture
def spec_with_mcp_tools():
    """AgentSpec with MCP tools that require server configuration."""
    return AgentSpec(
        id=generate_uuid(),
        name="mcp-enabled-agent",
        display_name="MCP Enabled Agent",
        icon="mcp",
        spec_version="v1",
        objective="Agent that uses MCP tools",
        task_type="testing",
        context={},
        tool_policy={
            "allowed_tools": [
                "Read",
                "Write",
                "mcp__features__feature_get_stats",
                "mcp__features__feature_mark_passing",
                "mcp__playwright__browser_navigate",
                "mcp__playwright__browser_click",
            ],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=600,
        source_feature_id=None,
        priority=1,
        tags=[],
    )


@pytest.fixture
def existing_settings_file(temp_project_dir):
    """Create a project with existing settings file."""
    claude_dir = temp_project_dir / ".claude"
    claude_dir.mkdir(parents=True)
    settings_path = claude_dir / "settings.local.json"

    existing_settings = {
        "permissions": {
            "allow": [
                "Bash(git add:*)",
                "Bash(git commit:*)",
            ]
        },
        "customKey": "customValue"
    }
    settings_path.write_text(json.dumps(existing_settings, indent=2), encoding="utf-8")
    return temp_project_dir


# =============================================================================
# Step 1: Check if .claude/settings.local.json exists
# =============================================================================

class TestStep1SettingsExist:
    """Verify Step 1: Check if .claude/settings.local.json exists."""

    def test_settings_exist_returns_false_when_missing(self, settings_manager):
        """settings_exist() returns False when file doesn't exist."""
        assert settings_manager.settings_exist() is False

    def test_settings_exist_returns_true_when_present(self, existing_settings_file):
        """settings_exist() returns True when file exists."""
        manager = SettingsManager(existing_settings_file)
        assert manager.settings_exist() is True

    def test_settings_path_property(self, settings_manager, temp_project_dir):
        """settings_path property returns correct path."""
        expected = temp_project_dir / ".claude" / "settings.local.json"
        assert settings_manager.settings_path == expected

    def test_claude_dir_property(self, settings_manager, temp_project_dir):
        """claude_dir property returns correct path."""
        expected = temp_project_dir / ".claude"
        assert settings_manager.claude_dir == expected

    def test_get_settings_info_when_missing(self, settings_manager):
        """get_settings_info() returns correct info when file missing."""
        info = settings_manager.get_settings_info()
        assert info["exists"] is False
        assert info["permissions"] is None
        assert info["size"] is None

    def test_get_settings_info_when_present(self, existing_settings_file):
        """get_settings_info() returns correct info when file exists."""
        manager = SettingsManager(existing_settings_file)
        info = manager.get_settings_info()
        assert info["exists"] is True
        assert info["permissions"] is not None
        assert info["size"] is not None
        assert info["size"] > 0

    def test_check_settings_exist_module_function(self, temp_project_dir):
        """check_settings_exist() module function works correctly."""
        assert check_settings_exist(temp_project_dir) is False

        # Create settings
        manager = SettingsManager(temp_project_dir)
        manager.create_default_settings()

        assert check_settings_exist(temp_project_dir) is True


# =============================================================================
# Step 2: Create with default permissions if missing
# =============================================================================

class TestStep2CreateWithDefaults:
    """Verify Step 2: If missing, create with default permissions."""

    def test_ensure_claude_dir_creates_directory(self, settings_manager, temp_project_dir):
        """ensure_claude_dir() creates .claude directory."""
        assert not (temp_project_dir / ".claude").exists()

        result = settings_manager.ensure_claude_dir()

        assert result == temp_project_dir / ".claude"
        assert (temp_project_dir / ".claude").exists()
        assert (temp_project_dir / ".claude").is_dir()

    def test_ensure_claude_dir_idempotent(self, settings_manager, temp_project_dir):
        """ensure_claude_dir() is idempotent."""
        settings_manager.ensure_claude_dir()
        settings_manager.ensure_claude_dir()  # Second call

        assert (temp_project_dir / ".claude").exists()

    def test_create_default_settings_creates_file(self, settings_manager):
        """create_default_settings() creates settings file."""
        result = settings_manager.create_default_settings()

        assert result.success is True
        assert result.created is True
        assert result.file_path is not None
        assert result.file_path.exists()
        assert result.settings_hash is not None

    def test_create_default_settings_content(self, settings_manager):
        """create_default_settings() writes correct content."""
        settings_manager.create_default_settings()

        content = settings_manager.settings_path.read_text(encoding="utf-8")
        settings = json.loads(content)

        assert "permissions" in settings
        assert "allow" in settings["permissions"]
        assert isinstance(settings["permissions"]["allow"], list)

    def test_create_default_settings_permissions(self, settings_manager):
        """create_default_settings() sets correct file permissions."""
        settings_manager.create_default_settings()

        st = settings_manager.settings_path.stat()
        mode = stat.S_IMODE(st.st_mode)

        # Should be 0o644 (rw-r--r--)
        assert mode == DEFAULT_SETTINGS_PERMISSIONS

    def test_create_default_settings_result_structure(self, settings_manager):
        """create_default_settings() returns proper result structure."""
        result = settings_manager.create_default_settings()

        result_dict = result.to_dict()
        assert "success" in result_dict
        assert "file_path" in result_dict
        assert "created" in result_dict
        assert "settings_hash" in result_dict


# =============================================================================
# Step 3: Include MCP server configuration if agents require it
# =============================================================================

class TestStep3McpConfiguration:
    """Verify Step 3: Include MCP server configuration if agents require it."""

    def test_detect_mcp_requirements_empty(self, settings_manager):
        """detect_mcp_requirements() returns empty for no tools."""
        requirements = settings_manager.detect_mcp_requirements()

        assert len(requirements.mcp_servers) == 0
        assert len(requirements.permissions) == 0

    def test_detect_mcp_requirements_features_tools(self, settings_manager, spec_with_mcp_tools):
        """detect_mcp_requirements() detects features MCP server."""
        requirements = settings_manager.detect_mcp_requirements(specs=[spec_with_mcp_tools])

        assert "features" in requirements.mcp_servers

    def test_detect_mcp_requirements_playwright_tools(self, settings_manager, spec_with_mcp_tools):
        """detect_mcp_requirements() detects playwright MCP server."""
        requirements = settings_manager.detect_mcp_requirements(specs=[spec_with_mcp_tools])

        assert "playwright" in requirements.mcp_servers

    def test_detect_mcp_requirements_from_tool_list(self, settings_manager):
        """detect_mcp_requirements() works with tool list."""
        tools = [
            "Read",
            "feature_get_stats",
            "browser_click",
        ]
        requirements = settings_manager.detect_mcp_requirements(tools=tools)

        assert "features" in requirements.mcp_servers
        assert "playwright" in requirements.mcp_servers

    def test_detect_mcp_requirements_no_mcp_tools(self, settings_manager, sample_agent_spec):
        """detect_mcp_requirements() returns empty for regular tools."""
        requirements = settings_manager.detect_mcp_requirements(specs=[sample_agent_spec])

        assert len(requirements.mcp_servers) == 0

    def test_get_mcp_server_config_features(self, settings_manager):
        """get_mcp_server_config() returns features server config."""
        config = settings_manager.get_mcp_server_config("features")

        assert config is not None
        assert "command" in config
        assert "args" in config

    def test_get_mcp_server_config_playwright(self, settings_manager):
        """get_mcp_server_config() returns playwright server config."""
        config = settings_manager.get_mcp_server_config("playwright")

        assert config is not None
        assert "command" in config

    def test_get_mcp_server_config_unknown(self, settings_manager):
        """get_mcp_server_config() returns None for unknown server."""
        config = settings_manager.get_mcp_server_config("unknown-server")

        assert config is None

    def test_detect_required_mcp_servers_module_function(self, spec_with_mcp_tools):
        """detect_required_mcp_servers() module function works."""
        servers = detect_required_mcp_servers(specs=[spec_with_mcp_tools])

        assert "features" in servers
        assert "playwright" in servers


# =============================================================================
# Step 4: Preserve existing settings when updating
# =============================================================================

class TestStep4PreserveExisting:
    """Verify Step 4: Preserve existing settings when updating."""

    def test_load_settings_when_missing(self, settings_manager):
        """load_settings() returns empty dict when file missing."""
        settings = settings_manager.load_settings()

        assert settings == {}

    def test_load_settings_when_present(self, existing_settings_file):
        """load_settings() returns existing settings."""
        manager = SettingsManager(existing_settings_file)
        settings = manager.load_settings()

        assert "permissions" in settings
        assert "allow" in settings["permissions"]
        assert "customKey" in settings

    def test_load_settings_invalid_json(self, temp_project_dir):
        """load_settings() handles invalid JSON gracefully."""
        claude_dir = temp_project_dir / ".claude"
        claude_dir.mkdir(parents=True)
        settings_path = claude_dir / "settings.local.json"
        settings_path.write_text("not valid json", encoding="utf-8")

        manager = SettingsManager(temp_project_dir)
        settings = manager.load_settings()

        assert settings == {}

    def test_merge_settings_preserves_existing(self, settings_manager):
        """merge_settings() preserves existing settings."""
        existing = {
            "permissions": {
                "allow": ["Bash(git:*)"]
            },
            "customKey": "customValue"
        }
        requirements = SettingsRequirements()

        merged, mcp_added, perms_added = settings_manager.merge_settings(existing, requirements)

        assert "customKey" in merged
        assert merged["customKey"] == "customValue"
        assert "Bash(git:*)" in merged["permissions"]["allow"]

    def test_merge_settings_adds_mcp_servers(self, settings_manager):
        """merge_settings() adds new MCP servers."""
        existing = {"permissions": {"allow": []}}
        requirements = SettingsRequirements(mcp_servers={"features"})

        merged, mcp_added, _ = settings_manager.merge_settings(existing, requirements)

        assert "mcpServers" in merged
        assert "features" in merged["mcpServers"]
        assert "features" in mcp_added

    def test_merge_settings_no_duplicate_mcp_servers(self, settings_manager):
        """merge_settings() doesn't duplicate existing MCP servers."""
        existing = {
            "permissions": {"allow": []},
            "mcpServers": {"features": {"command": "existing"}}
        }
        requirements = SettingsRequirements(mcp_servers={"features"})

        merged, mcp_added, _ = settings_manager.merge_settings(existing, requirements)

        # Should preserve existing config
        assert merged["mcpServers"]["features"]["command"] == "existing"
        assert "features" not in mcp_added

    def test_update_settings_preserves_custom_fields(self, existing_settings_file):
        """update_settings() preserves custom fields."""
        manager = SettingsManager(existing_settings_file)

        result = manager.update_settings()

        assert result.success is True

        settings = manager.load_settings()
        assert "customKey" in settings
        assert settings["customKey"] == "customValue"


# =============================================================================
# Step 5: Settings enable agent execution via Claude CLI
# =============================================================================

class TestStep5EnableExecution:
    """Verify Step 5: Settings enable agent execution via Claude CLI."""

    def test_update_settings_creates_when_missing(self, settings_manager):
        """update_settings() creates file when missing."""
        result = settings_manager.update_settings()

        assert result.success is True
        assert result.created is True
        assert settings_manager.settings_exist()

    def test_update_settings_updates_when_present(self, existing_settings_file):
        """update_settings() updates existing file."""
        manager = SettingsManager(existing_settings_file)

        result = manager.update_settings()

        assert result.success is True
        assert result.created is False

    def test_update_settings_with_requirements(self, settings_manager, spec_with_mcp_tools):
        """update_settings() applies requirements from specs."""
        result = settings_manager.update_settings(specs=[spec_with_mcp_tools])

        assert result.success is True
        assert "features" in result.mcp_servers_added
        assert "playwright" in result.mcp_servers_added

        settings = settings_manager.load_settings()
        assert "mcpServers" in settings
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]

    def test_update_settings_result_structure(self, settings_manager):
        """update_settings() returns proper result structure."""
        result = settings_manager.update_settings()

        result_dict = result.to_dict()
        assert "success" in result_dict
        assert "created" in result_dict
        assert "mcp_servers_added" in result_dict
        assert "permissions_added" in result_dict
        assert "settings_hash" in result_dict

    def test_ensure_settings_for_specs_convenience(self, settings_manager, spec_with_mcp_tools):
        """ensure_settings_for_specs() is a convenience wrapper."""
        result = settings_manager.ensure_settings_for_specs([spec_with_mcp_tools])

        assert result.success is True
        assert "features" in result.mcp_servers_added

    def test_ensure_settings_for_agents_module_function(self, temp_project_dir, spec_with_mcp_tools):
        """ensure_settings_for_agents() module function works."""
        result = ensure_settings_for_agents(temp_project_dir, specs=[spec_with_mcp_tools])

        assert result.success is True
        assert check_settings_exist(temp_project_dir)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for settings management."""

    def test_full_workflow_new_project(self, temp_project_dir, spec_with_mcp_tools):
        """Test full workflow for a new project."""
        # Initially no settings
        assert not check_settings_exist(temp_project_dir)

        # Create settings for agent
        result = ensure_settings_for_agents(temp_project_dir, specs=[spec_with_mcp_tools])

        assert result.success is True
        assert result.created is True
        assert "features" in result.mcp_servers_added
        assert "playwright" in result.mcp_servers_added

        # Verify settings exist and are valid
        assert check_settings_exist(temp_project_dir)

        manager = SettingsManager(temp_project_dir)
        settings = manager.load_settings()

        assert "permissions" in settings
        assert "mcpServers" in settings
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]

    def test_incremental_updates(self, temp_project_dir):
        """Test incremental updates preserve previous changes."""
        manager = SettingsManager(temp_project_dir)

        # First update - add features server
        spec1 = AgentSpec(
            id=generate_uuid(),
            name="agent-1",
            display_name="Agent 1",
            icon="1",
            spec_version="v1",
            objective="First agent",
            task_type="coding",
            context={},
            tool_policy={
                "allowed_tools": ["feature_get_stats"],
            },
            max_turns=10,
            timeout_seconds=60,
            source_feature_id=None,
            priority=1,
            tags=[],
        )

        result1 = manager.update_settings(specs=[spec1])
        assert result1.success is True
        assert "features" in result1.mcp_servers_added

        # Second update - add playwright server
        spec2 = AgentSpec(
            id=generate_uuid(),
            name="agent-2",
            display_name="Agent 2",
            icon="2",
            spec_version="v1",
            objective="Second agent",
            task_type="testing",
            context={},
            tool_policy={
                "allowed_tools": ["browser_click"],
            },
            max_turns=10,
            timeout_seconds=60,
            source_feature_id=None,
            priority=1,
            tags=[],
        )

        result2 = manager.update_settings(specs=[spec2])
        assert result2.success is True
        assert "playwright" in result2.mcp_servers_added
        assert "features" not in result2.mcp_servers_added  # Already present

        # Verify both servers present
        settings = manager.load_settings()
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for settings management."""

    def test_empty_spec_list(self, settings_manager):
        """Handle empty spec list."""
        result = settings_manager.update_settings(specs=[])

        assert result.success is True
        assert len(result.mcp_servers_added) == 0

    def test_spec_with_empty_tool_policy(self, settings_manager):
        """Handle spec with empty tool policy."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="empty-policy-agent",
            display_name="Empty Policy Agent",
            icon="empty",
            spec_version="v1",
            objective="Agent with empty policy",
            task_type="coding",
            context={},
            tool_policy={},
            max_turns=10,
            timeout_seconds=60,
            source_feature_id=None,
            priority=1,
            tags=[],
        )

        result = settings_manager.update_settings(specs=[spec])
        assert result.success is True

    def test_spec_with_none_tool_policy(self, settings_manager):
        """Handle spec with None tool policy."""
        spec = AgentSpec(
            id=generate_uuid(),
            name="none-policy-agent",
            display_name="None Policy Agent",
            icon="none",
            spec_version="v1",
            objective="Agent with None policy",
            task_type="coding",
            context={},
            tool_policy=None,
            max_turns=10,
            timeout_seconds=60,
            source_feature_id=None,
            priority=1,
            tags=[],
        )

        result = settings_manager.update_settings(specs=[spec])
        assert result.success is True

    def test_get_settings_manager_function(self, temp_project_dir):
        """get_settings_manager() convenience function."""
        manager = get_settings_manager(temp_project_dir)

        assert isinstance(manager, SettingsManager)
        assert manager.project_dir == temp_project_dir.resolve()


# =============================================================================
# API Package Exports
# =============================================================================

class TestApiPackageExports:
    """Verify API package exports Feature #198 components."""

    def test_import_settings_manager(self):
        """SettingsManager importable from api package."""
        from api import SettingsManager
        assert SettingsManager is not None

    def test_import_settings_update_result(self):
        """SettingsUpdateResult importable from api package."""
        from api import SettingsUpdateResult
        assert SettingsUpdateResult is not None

    def test_import_settings_requirements(self):
        """SettingsRequirements importable from api package."""
        from api import SettingsRequirements
        assert SettingsRequirements is not None

    def test_import_check_settings_exist(self):
        """check_settings_exist() importable from api package."""
        from api import check_settings_exist
        assert callable(check_settings_exist)

    def test_import_ensure_settings_for_agents(self):
        """ensure_settings_for_agents() importable from api package."""
        from api import ensure_settings_for_agents
        assert callable(ensure_settings_for_agents)

    def test_import_constants(self):
        """Constants importable from api package."""
        from api import (
            SETTINGS_LOCAL_FILE,
            DEFAULT_SETTINGS_PERMISSIONS,
            DEFAULT_SETTINGS,
            MCP_SERVER_CONFIGS,
            MCP_TOOL_PATTERNS,
        )
        assert SETTINGS_LOCAL_FILE == "settings.local.json"
        assert DEFAULT_SETTINGS_PERMISSIONS == 0o644


# =============================================================================
# Feature #198 Verification Steps
# =============================================================================

class TestFeature198VerificationSteps:
    """Comprehensive tests verifying all 5 feature steps."""

    def test_step1_check_settings_exist(self, temp_project_dir):
        """Step 1: Check if .claude/settings.local.json exists."""
        manager = SettingsManager(temp_project_dir)

        # Initially doesn't exist
        assert manager.settings_exist() is False

        # After creation, exists
        manager.create_default_settings()
        assert manager.settings_exist() is True

    def test_step2_create_with_default_permissions(self, temp_project_dir):
        """Step 2: If missing, create with default permissions."""
        manager = SettingsManager(temp_project_dir)
        result = manager.create_default_settings()

        assert result.success is True
        assert result.created is True

        # Check permissions
        st = manager.settings_path.stat()
        mode = stat.S_IMODE(st.st_mode)
        assert mode == 0o644  # rw-r--r--

    def test_step3_include_mcp_configuration(self, temp_project_dir, spec_with_mcp_tools):
        """Step 3: Include MCP server configuration if agents require it."""
        manager = SettingsManager(temp_project_dir)
        result = manager.update_settings(specs=[spec_with_mcp_tools])

        assert result.success is True

        settings = manager.load_settings()
        assert "mcpServers" in settings
        assert "features" in settings["mcpServers"]
        assert "playwright" in settings["mcpServers"]

        # Verify config structure
        features_config = settings["mcpServers"]["features"]
        assert "command" in features_config
        assert "args" in features_config

    def test_step4_preserve_existing_settings(self, existing_settings_file, spec_with_mcp_tools):
        """Step 4: Preserve existing settings when updating."""
        manager = SettingsManager(existing_settings_file)

        # Capture original settings
        original = manager.load_settings()
        assert "customKey" in original
        assert "Bash(git add:*)" in original["permissions"]["allow"]

        # Update with new requirements
        result = manager.update_settings(specs=[spec_with_mcp_tools])
        assert result.success is True

        # Verify preservation
        updated = manager.load_settings()
        assert "customKey" in updated
        assert updated["customKey"] == "customValue"
        assert "Bash(git add:*)" in updated["permissions"]["allow"]

        # And new additions
        assert "mcpServers" in updated

    def test_step5_settings_enable_agent_execution(self, temp_project_dir, spec_with_mcp_tools):
        """Step 5: Settings enable agent execution via Claude CLI."""
        # Full workflow test
        result = ensure_settings_for_agents(temp_project_dir, specs=[spec_with_mcp_tools])

        assert result.success is True

        # Verify settings structure is valid for Claude CLI
        manager = SettingsManager(temp_project_dir)
        settings = manager.load_settings()

        # Required structure for Claude CLI
        assert "permissions" in settings
        assert "allow" in settings["permissions"]
        assert isinstance(settings["permissions"]["allow"], list)

        # MCP servers configured
        assert "mcpServers" in settings
        for server_name, config in settings["mcpServers"].items():
            assert "command" in config
            assert "args" in config
