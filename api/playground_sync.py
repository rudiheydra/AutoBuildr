"""
Playground Sync Module
======================

Synchronizes generated agents to the agent-playground for testing.

This module handles:
1. Copying agent .md files to the playground's agents directory
2. Namespacing agents by project name
3. Optionally calling the playground API for immediate import
4. Creating test branches for isolated testing

Configuration via environment variables:
    AGENT_PLAYGROUND_PATH: Path to agent-playground directory
    AGENT_PLAYGROUND_API_URL: Playground API URL (default: http://localhost:8100)
    AGENT_PLAYGROUND_NAMESPACE: Namespace prefix (default: project name)
    AGENT_PLAYGROUND_AUTO_IMPORT: Auto-import via API (default: true)

Usage:
    from api.playground_sync import PlaygroundSync

    sync = PlaygroundSync(project_dir)
    result = sync.sync_agents(agent_files)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a playground sync operation."""
    success: bool
    synced_files: list[str] = field(default_factory=list)
    imported_count: int = 0
    namespace: str = ""
    playground_path: str | None = None
    api_imported: bool = False
    error: str | None = None


class PlaygroundSync:
    """
    Synchronizes agents to the agent-playground for testing.

    The sync process:
    1. Copies agent .md files to playground/agents/{namespace}/
    2. If watch-agents is running, files are auto-imported
    3. Optionally calls the playground API for immediate import
    """

    def __init__(
        self,
        project_dir: Path | str,
        *,
        playground_path: Path | str | None = None,
        api_url: str | None = None,
        namespace: str | None = None,
        auto_import: bool = True,
    ):
        """
        Initialize the playground sync.

        Args:
            project_dir: Project directory (used for namespace default)
            playground_path: Path to agent-playground (default from env)
            api_url: Playground API URL (default from env)
            namespace: Namespace for agents (default: project name)
            auto_import: Whether to call API for immediate import
        """
        self.project_dir = Path(project_dir).resolve()

        # Resolve playground path
        self.playground_path = self._resolve_playground_path(playground_path)

        # API configuration
        self.api_url = api_url or os.environ.get(
            "AGENT_PLAYGROUND_API_URL",
            "http://localhost:8100"
        )

        # Namespace (project name or custom)
        self.namespace = namespace or os.environ.get(
            "AGENT_PLAYGROUND_NAMESPACE",
            self.project_dir.name
        )

        # Auto-import setting
        auto_import_env = os.environ.get("AGENT_PLAYGROUND_AUTO_IMPORT", "true")
        self.auto_import = auto_import and auto_import_env.lower() == "true"

        _logger.debug(
            "PlaygroundSync initialized: playground=%s, namespace=%s, api=%s",
            self.playground_path,
            self.namespace,
            self.api_url,
        )

    def _resolve_playground_path(self, explicit_path: Path | str | None) -> Path | None:
        """Resolve the playground path from various sources."""
        # 1. Explicit path
        if explicit_path:
            return Path(explicit_path).resolve()

        # 2. Environment variable
        env_path = os.environ.get("AGENT_PLAYGROUND_PATH")
        if env_path:
            return Path(env_path).resolve()

        # 3. Common locations relative to project
        common_locations = [
            self.project_dir.parent / "agent-playground",
            Path.home() / "workspace" / "agent-playground",
            Path("/home/rudih/workspace/agent-playground"),  # Fallback
        ]

        for location in common_locations:
            if location.exists() and (location / "agents").exists():
                return location

        return None

    @property
    def agents_dir(self) -> Path | None:
        """Get the agents directory in the playground."""
        if self.playground_path:
            return self.playground_path / "agents"
        return None

    @property
    def namespace_dir(self) -> Path | None:
        """Get the namespaced agents directory."""
        if self.agents_dir:
            return self.agents_dir / self.namespace
        return None

    def is_available(self) -> bool:
        """Check if the playground is available for syncing."""
        return self.playground_path is not None and self.playground_path.exists()

    def sync_agents(self, agent_files: list[str | Path]) -> SyncResult:
        """
        Sync agent files to the playground.

        Args:
            agent_files: List of agent .md file paths to sync

        Returns:
            SyncResult with sync status
        """
        if not agent_files:
            return SyncResult(
                success=True,
                synced_files=[],
                namespace=self.namespace,
                error=None,
            )

        if not self.is_available():
            _logger.warning("Playground not available for sync")
            return SyncResult(
                success=False,
                synced_files=[],
                namespace=self.namespace,
                error="Playground not available (set AGENT_PLAYGROUND_PATH)",
            )

        # Ensure namespace directory exists
        if self.namespace_dir:
            self.namespace_dir.mkdir(parents=True, exist_ok=True)

        synced = []
        errors = []

        for agent_file in agent_files:
            agent_path = Path(agent_file)

            if not agent_path.exists():
                errors.append(f"File not found: {agent_file}")
                continue

            try:
                # Copy to playground with namespace prefix in filename
                dest_name = f"{self.namespace}--{agent_path.name}"
                dest_path = self.agents_dir / dest_name

                shutil.copy2(agent_path, dest_path)
                synced.append(str(dest_path))

                _logger.info("Synced agent: %s -> %s", agent_path.name, dest_path)

            except Exception as e:
                errors.append(f"Failed to copy {agent_path.name}: {e}")
                _logger.error("Failed to sync %s: %s", agent_path, e)

        # Optionally call API for immediate import
        api_imported = False
        import_count = 0

        if self.auto_import and synced:
            api_result = self._import_via_api(synced)
            api_imported = api_result.get("success", False)
            import_count = api_result.get("imported", 0)

        return SyncResult(
            success=len(synced) > 0,
            synced_files=synced,
            imported_count=import_count,
            namespace=self.namespace,
            playground_path=str(self.playground_path) if self.playground_path else None,
            api_imported=api_imported,
            error="; ".join(errors) if errors else None,
        )

    def _import_via_api(self, agent_files: list[str]) -> dict[str, Any]:
        """
        Call the playground API to import agents immediately.

        Args:
            agent_files: List of agent file paths in the playground

        Returns:
            API response dict
        """
        try:
            # Call the import endpoint for each file
            imported = 0

            for agent_file in agent_files:
                payload = json.dumps({
                    "file_path": agent_file,
                    "force": True,  # Re-import even if unchanged
                }).encode("utf-8")

                req = urllib.request.Request(
                    f"{self.api_url}/api/agents/import",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        result = json.load(resp)
                        if result.get("success"):
                            imported += 1
                except urllib.error.URLError:
                    # API might not have this endpoint, try pipelines endpoint
                    pass

            # Fallback: trigger a full import scan
            if imported == 0:
                req = urllib.request.Request(
                    f"{self.api_url}/api/pipelines/import",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        result = json.load(resp)
                        imported = result.get("imported", 0)
                except urllib.error.URLError:
                    pass

            return {"success": imported > 0, "imported": imported}

        except Exception as e:
            _logger.warning("API import failed: %s", e)
            return {"success": False, "imported": 0, "error": str(e)}

    def cleanup_namespace(self) -> int:
        """
        Remove all agents for this namespace from the playground.

        Returns:
            Number of files removed
        """
        if not self.is_available() or not self.agents_dir:
            return 0

        removed = 0
        prefix = f"{self.namespace}--"

        for agent_file in self.agents_dir.glob(f"{prefix}*.md"):
            try:
                agent_file.unlink()
                removed += 1
                _logger.info("Removed: %s", agent_file.name)
            except Exception as e:
                _logger.error("Failed to remove %s: %s", agent_file, e)

        return removed


def sync_to_playground(
    project_dir: Path | str,
    agent_files: list[str | Path],
    **kwargs,
) -> SyncResult:
    """
    Convenience function to sync agents to the playground.

    Args:
        project_dir: Project directory
        agent_files: List of agent file paths
        **kwargs: Additional arguments for PlaygroundSync

    Returns:
        SyncResult with sync status
    """
    sync = PlaygroundSync(project_dir, **kwargs)
    return sync.sync_agents(agent_files)
