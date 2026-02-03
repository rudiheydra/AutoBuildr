#!/usr/bin/env python3
"""
Verification script for Feature #198: Agent Materializer generates settings.local.json when needed

This script verifies all 5 feature steps work correctly in the actual AutoBuildr project.
"""
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.settings_manager import (
    SettingsManager,
    check_settings_exist,
    ensure_settings_for_agents,
    detect_required_mcp_servers,
    DEFAULT_SETTINGS_PERMISSIONS,
)
from api.agentspec_models import AgentSpec, generate_uuid


def create_test_spec_with_mcp_tools():
    """Create a test AgentSpec with MCP tools."""
    return AgentSpec(
        id=generate_uuid(),
        name="verification-agent",
        display_name="Verification Agent",
        icon="check",
        spec_version="v1",
        objective="Agent for verifying Feature #198",
        task_type="testing",
        context={},
        tool_policy={
            "allowed_tools": [
                "Read",
                "Write",
                "mcp__features__feature_get_stats",
                "mcp__playwright__browser_click",
            ],
        },
        max_turns=10,
        timeout_seconds=60,
        source_feature_id=198,
        priority=1,
        tags=["verification"],
    )


def verify_step1(project_dir: Path) -> tuple[bool, str]:
    """Step 1: Check if .claude/settings.local.json exists."""
    try:
        manager = SettingsManager(project_dir)

        # Test the check functionality
        exists_before = manager.settings_exist()

        # Create if needed
        if not exists_before:
            manager.create_default_settings()

        exists_after = manager.settings_exist()

        if exists_after:
            return True, f"settings_exist() works correctly (before={exists_before}, after={exists_after})"
        else:
            return False, "settings_exist() returned False after creation"
    except Exception as e:
        return False, f"Error: {e}"


def verify_step2(project_dir: Path) -> tuple[bool, str]:
    """Step 2: If missing, create with default permissions."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manager = SettingsManager(tmp_path)

            # Create settings
            result = manager.create_default_settings()

            if not result.success:
                return False, f"create_default_settings() failed: {result.error}"

            if not result.created:
                return False, "created flag not set"

            # Check permissions
            st = manager.settings_path.stat()
            mode = stat.S_IMODE(st.st_mode)

            if mode != DEFAULT_SETTINGS_PERMISSIONS:
                return False, f"Wrong permissions: expected {oct(DEFAULT_SETTINGS_PERMISSIONS)}, got {oct(mode)}"

            return True, f"Created with permissions {oct(mode)} (0o644)"
    except Exception as e:
        return False, f"Error: {e}"


def verify_step3(project_dir: Path) -> tuple[bool, str]:
    """Step 3: Include MCP server configuration if agents require it."""
    try:
        spec = create_test_spec_with_mcp_tools()
        servers = detect_required_mcp_servers(specs=[spec])

        expected = {"features", "playwright"}
        if servers != expected:
            return False, f"Wrong servers detected: expected {expected}, got {servers}"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            manager = SettingsManager(tmp_path)
            result = manager.update_settings(specs=[spec])

            if not result.success:
                return False, f"update_settings() failed: {result.error}"

            settings = manager.load_settings()
            if "mcpServers" not in settings:
                return False, "mcpServers not in settings"

            for server in expected:
                if server not in settings["mcpServers"]:
                    return False, f"Server {server} not configured"

            return True, f"MCP servers configured: {list(settings['mcpServers'].keys())}"
    except Exception as e:
        return False, f"Error: {e}"


def verify_step4(project_dir: Path) -> tuple[bool, str]:
    """Step 4: Preserve existing settings when updating."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create existing settings
            claude_dir = tmp_path / ".claude"
            claude_dir.mkdir(parents=True)
            settings_path = claude_dir / "settings.local.json"

            existing = {
                "permissions": {"allow": ["Bash(git:*)"]},
                "customKey": "customValue"
            }
            settings_path.write_text(json.dumps(existing, indent=2))

            # Update with new requirements
            spec = create_test_spec_with_mcp_tools()
            manager = SettingsManager(tmp_path)
            result = manager.update_settings(specs=[spec])

            if not result.success:
                return False, f"update_settings() failed: {result.error}"

            # Check preservation
            updated = manager.load_settings()

            if "customKey" not in updated:
                return False, "customKey was not preserved"

            if updated["customKey"] != "customValue":
                return False, f"customKey value changed: {updated['customKey']}"

            if "Bash(git:*)" not in updated.get("permissions", {}).get("allow", []):
                return False, "Existing permission was not preserved"

            return True, "Existing settings preserved and new settings added"
    except Exception as e:
        return False, f"Error: {e}"


def verify_step5(project_dir: Path) -> tuple[bool, str]:
    """Step 5: Settings enable agent execution via Claude CLI."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            spec = create_test_spec_with_mcp_tools()

            # Full workflow
            result = ensure_settings_for_agents(tmp_path, specs=[spec])

            if not result.success:
                return False, f"ensure_settings_for_agents() failed: {result.error}"

            # Verify structure is valid for Claude CLI
            manager = SettingsManager(tmp_path)
            settings = manager.load_settings()

            # Required structure
            if "permissions" not in settings:
                return False, "Missing permissions key"

            if "allow" not in settings["permissions"]:
                return False, "Missing permissions.allow key"

            if not isinstance(settings["permissions"]["allow"], list):
                return False, "permissions.allow is not a list"

            # MCP servers
            if "mcpServers" not in settings:
                return False, "Missing mcpServers key"

            for server, config in settings["mcpServers"].items():
                if "command" not in config:
                    return False, f"Server {server} missing command"
                if "args" not in config:
                    return False, f"Server {server} missing args"

            return True, "Settings valid for Claude CLI execution"
    except Exception as e:
        return False, f"Error: {e}"


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #198: Agent Materializer generates settings.local.json when needed")
    print("=" * 70)
    print()

    project_dir = Path(__file__).parent.parent

    steps = [
        ("Step 1: Check if .claude/settings.local.json exists", verify_step1),
        ("Step 2: If missing, create with default permissions", verify_step2),
        ("Step 3: Include MCP server configuration if agents require it", verify_step3),
        ("Step 4: Preserve existing settings when updating", verify_step4),
        ("Step 5: Settings enable agent execution via Claude CLI", verify_step5),
    ]

    results = []
    for name, verify_func in steps:
        print(f"Verifying: {name}")
        passed, message = verify_func(project_dir)
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {message}")
        results.append((name, passed, message))
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, p, _ in results if p)
    total = len(results)

    for name, p, _ in results:
        status = "PASS" if p else "FAIL"
        print(f"  [{status}] {name}")

    print()
    print(f"Total: {passed}/{total} steps passed")

    if passed == total:
        print("\nAll verification steps PASSED!")
        return 0
    else:
        print("\nSome verification steps FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
