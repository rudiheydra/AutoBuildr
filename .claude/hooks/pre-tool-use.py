#!/usr/bin/env python3
"""
PreToolUse Hook: Check Agent Availability

This hook is called before a tool is executed.
For the Task tool, it checks if the requested agent type exists.
If not, it can trigger agent generation via the DSPy pipeline.

Environment:
    AUTOBUILDR_API_URL: Base URL for AutoBuildr API (default: http://localhost:8000)

Hook Protocol:
    - Reads JSON from stdin with tool context
    - Exit code 0 = allow tool execution
    - Exit code 2 = block with error
    - stdout JSON with permissionDecision for feedback
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Configuration
AUTOBUILDR_API = os.environ.get("AUTOBUILDR_API_URL", "http://localhost:8000")
TIMEOUT_SECONDS = 60  # Longer timeout for potential agent generation


def main():
    """Main entry point for pre-tool-use hook."""
    try:
        # Read hook input from stdin
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # No input or invalid JSON - allow
        sys.exit(0)

    # Only intercept Task tool calls
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Task":
        sys.exit(0)

    # Get tool input
    tool_input = hook_input.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")

    if not subagent_type:
        # No subagent_type specified - allow
        sys.exit(0)

    # Get project context
    project_dir = hook_input.get("cwd", os.getcwd())

    # Check if agent exists
    try:
        check_result = check_agent_exists(subagent_type, project_dir)

        if not check_result.get("needs_generation", False):
            # Agent exists - allow
            sys.exit(0)

        # Agent doesn't exist - trigger generation
        trigger_result = trigger_agent_generation(subagent_type, project_dir)

        if trigger_result.get("generated", False):
            # Agent was generated - allow
            sys.exit(0)

        # Generation failed - still allow (let Claude handle it)
        # We don't block, just log the error
        sys.exit(0)

    except urllib.error.URLError:
        # API unavailable - allow and let Claude handle it
        sys.exit(0)

    except Exception:
        # Unexpected error - allow
        sys.exit(0)


def check_agent_exists(agent_type: str, project_dir: str) -> dict:
    """Check if an agent type exists via API."""
    payload = json.dumps({
        "agent_type": agent_type,
        "project_dir": project_dir,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{AUTOBUILDR_API}/api/task-pipeline/check-agent",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


def trigger_agent_generation(capability: str, project_dir: str) -> dict:
    """Trigger agent generation via API."""
    payload = json.dumps({
        "capability": capability,
        "project_dir": project_dir,
        "context": {},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{AUTOBUILDR_API}/api/task-pipeline/trigger",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.load(resp)


if __name__ == "__main__":
    main()
