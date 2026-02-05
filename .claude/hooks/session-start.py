#!/usr/bin/env python3
"""
SessionStart Hook: Initialize AutoBuildr Task Pipeline

This hook is called when a Claude Code session starts.
It contacts the AutoBuildr API to:
1. Hydrate Features into Claude Code Tasks
2. Check if agent generation is needed
3. Return session instructions

Environment:
    AUTOBUILDR_API_URL: Base URL for AutoBuildr API (default: http://localhost:8000)

Hook Protocol:
    - Reads JSON from stdin with session context
    - Outputs JSON to stdout for context injection
    - Exit code 0 = success
    - Exit code 2 = block with error (not used here)
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Configuration
AUTOBUILDR_API = os.environ.get("AUTOBUILDR_API_URL", "http://localhost:8000")
ENDPOINT = f"{AUTOBUILDR_API}/api/task-pipeline/init"
TIMEOUT_SECONDS = 30


def main():
    """Main entry point for session-start hook."""
    try:
        # Read hook input from stdin
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # No input or invalid JSON - use defaults
        hook_input = {}

    # Extract context
    project_dir = hook_input.get("cwd", os.getcwd())
    session_id = hook_input.get("session_id", "")

    # Build request payload
    payload = json.dumps({
        "project_dir": project_dir,
        "session_id": session_id,
    }).encode("utf-8")

    try:
        # Call AutoBuildr API
        req = urllib.request.Request(
            ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            result = json.load(resp)

            # Output result for context injection
            # Claude Code will receive this as session context
            output = {
                "tasks_hydrated": result.get("tasks_hydrated", 0),
                "agents_available": result.get("agents_available", []),
                "instructions": result.get("instructions", ""),
                "pipeline_executed": result.get("pipeline_executed", False),
            }

            print(json.dumps(output))

    except urllib.error.URLError as e:
        # Service unavailable - log but don't block session
        # Session can proceed with default behavior
        output = {
            "error": f"AutoBuildr API unavailable: {e}",
            "tasks_hydrated": 0,
            "agents_available": [],
            "instructions": (
                "## AutoBuildr Session\n\n"
                "Could not connect to AutoBuildr API. "
                "Ensure the server is running on port 8000."
            ),
        }
        print(json.dumps(output))

    except Exception as e:
        # Unexpected error - still don't block
        output = {
            "error": f"Hook error: {e}",
            "tasks_hydrated": 0,
        }
        print(json.dumps(output))

    # Always exit 0 - don't block session start on errors
    sys.exit(0)


if __name__ == "__main__":
    main()
