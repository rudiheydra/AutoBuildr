#!/usr/bin/env python3
"""
Playground Sync Hook: Sync agents to agent-playground for testing.

This hook can be called:
1. After session-start when agents are generated
2. After tool execution that creates agent files
3. Manually via CLI

Environment:
    AGENT_PLAYGROUND_PATH: Path to agent-playground directory
    AGENT_PLAYGROUND_API_URL: Playground API URL (default: http://localhost:8100)
    AGENT_PLAYGROUND_NAMESPACE: Namespace prefix (default: project name)

Hook Protocol:
    - Reads JSON from stdin with:
        - agent_files: List of agent file paths to sync
        - project_dir: Project directory for namespace
    - Outputs JSON to stdout with sync status
    - Exit code 0 = success
"""
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Configuration
PLAYGROUND_API_URL = os.environ.get("AGENT_PLAYGROUND_API_URL", "http://localhost:8100")
PLAYGROUND_PATH = os.environ.get("AGENT_PLAYGROUND_PATH")


def find_playground_path(project_dir: Path) -> Path | None:
    """Find the agent-playground directory."""
    if PLAYGROUND_PATH:
        return Path(PLAYGROUND_PATH)

    # Check common locations
    locations = [
        project_dir.parent / "agent-playground",
        Path.home() / "workspace" / "agent-playground",
        Path("/home/rudih/workspace/agent-playground"),
    ]

    for loc in locations:
        if loc.exists() and (loc / "agents").exists():
            return loc

    return None


def sync_agent_file(
    agent_file: Path,
    playground_path: Path,
    namespace: str,
) -> dict:
    """Sync a single agent file to the playground."""
    try:
        agents_dir = playground_path / "agents"
        dest_name = f"{namespace}--{agent_file.name}"
        dest_path = agents_dir / dest_name

        shutil.copy2(agent_file, dest_path)

        return {
            "success": True,
            "source": str(agent_file),
            "dest": str(dest_path),
        }
    except Exception as e:
        return {
            "success": False,
            "source": str(agent_file),
            "error": str(e),
        }


def import_via_api(synced_files: list[str]) -> dict:
    """Call playground API to import synced agents."""
    try:
        # Trigger import scan
        req = urllib.request.Request(
            f"{PLAYGROUND_API_URL}/api/pipelines/import",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
            return {
                "api_called": True,
                "imported": result.get("imported", 0),
            }
    except urllib.error.URLError as e:
        return {
            "api_called": False,
            "error": str(e),
        }
    except Exception as e:
        return {
            "api_called": False,
            "error": str(e),
        }


def main():
    """Main entry point for playground-sync hook."""
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        hook_input = {}

    # Get input parameters
    agent_files = hook_input.get("agent_files", [])
    project_dir = Path(hook_input.get("project_dir", hook_input.get("cwd", os.getcwd())))
    namespace = hook_input.get("namespace") or os.environ.get(
        "AGENT_PLAYGROUND_NAMESPACE",
        project_dir.name
    )

    # Find playground
    playground_path = find_playground_path(project_dir)

    if not playground_path:
        output = {
            "success": False,
            "error": "Playground not found. Set AGENT_PLAYGROUND_PATH.",
            "synced": [],
        }
        print(json.dumps(output))
        sys.exit(0)

    if not agent_files:
        # Auto-discover agent files from project
        generated_dir = project_dir / ".claude" / "agents" / "generated"
        if generated_dir.exists():
            agent_files = [str(f) for f in generated_dir.glob("*.md")]

    if not agent_files:
        output = {
            "success": True,
            "message": "No agent files to sync",
            "synced": [],
        }
        print(json.dumps(output))
        sys.exit(0)

    # Sync each file
    synced = []
    errors = []

    for agent_file in agent_files:
        result = sync_agent_file(Path(agent_file), playground_path, namespace)
        if result["success"]:
            synced.append(result["dest"])
        else:
            errors.append(result.get("error", "Unknown error"))

    # Call API for immediate import
    api_result = {}
    if synced:
        api_result = import_via_api(synced)

    output = {
        "success": len(synced) > 0,
        "synced": synced,
        "namespace": namespace,
        "playground_path": str(playground_path),
        "api_import": api_result,
        "errors": errors if errors else None,
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
