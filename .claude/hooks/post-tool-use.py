#!/usr/bin/env python3
"""
PostToolUse Hook: Sync Task Status + Ralph Wiggum Correction Loop

This hook is called after a tool is executed.
It handles two main responsibilities:

1. TaskUpdate Sync-back:
   - When TaskUpdate tool is called, sync status to Feature database
   - On completion, run acceptance validators
   - If validation fails, return error for agent self-correction

2. Edit/Write Validation:
   - After code changes, run acceptance validators
   - If tests fail, return error for agent self-correction
   - Agent keeps retrying until tests pass (Ralph Wiggum loop)

Environment:
    AUTOBUILDR_API_URL: Base URL for AutoBuildr API (default: http://localhost:8000)

Hook Protocol:
    - Reads JSON from stdin with tool result context
    - Exit code 0 = allow
    - Exit code 2 = block with error (triggers self-correction)
    - stdout JSON with permissionDecision and permissionDecisionReason
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Configuration
AUTOBUILDR_API = os.environ.get("AUTOBUILDR_API_URL", "http://localhost:8000")
TIMEOUT_SECONDS = 30


def main():
    """Main entry point for post-tool-use hook."""
    try:
        # Read hook input from stdin
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # No input or invalid JSON - allow
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")

    # Handle TaskUpdate sync-back
    if tool_name == "TaskUpdate":
        handle_task_update(hook_input)
        return

    # Handle Edit/Write validation
    if tool_name in ("Edit", "Write"):
        handle_code_change(hook_input)
        return

    # Other tools - allow without intervention
    sys.exit(0)


def handle_task_update(hook_input: dict) -> None:
    """
    Handle TaskUpdate tool calls.

    Syncs task status to Feature database.
    On completion, runs acceptance validators.
    """
    tool_input = hook_input.get("tool_input", {})
    task_id = tool_input.get("taskId", "")
    new_status = tool_input.get("status", "")

    if not task_id or not new_status:
        # Missing required fields - allow
        sys.exit(0)

    # Get context
    session_id = hook_input.get("session_id", "")
    cwd = hook_input.get("cwd", os.getcwd())

    # Build sync request
    payload = json.dumps({
        "task_id": task_id,
        "status": new_status,
        "session_id": session_id,
        "tool_input": tool_input,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{AUTOBUILDR_API}/api/task-pipeline/sync",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            result = json.load(resp)

            # Check if acceptance validation failed
            if result.get("acceptance_failed", False):
                # Ralph Wiggum: Return error for self-correction
                error_msg = result.get("error_message", "Acceptance tests failed")
                print(json.dumps({
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Acceptance validation failed: {error_msg}\n\n"
                        "Please fix the implementation and try again."
                    ),
                }))
                sys.exit(2)  # Block with feedback

            # Sync successful - allow
            sys.exit(0)

    except urllib.error.URLError:
        # API unavailable - allow (best effort sync)
        sys.exit(0)

    except Exception:
        # Unexpected error - allow
        sys.exit(0)


def handle_code_change(hook_input: dict) -> None:
    """
    Handle Edit/Write tool calls.

    Runs acceptance validators after code changes.
    If validation fails, returns error for self-correction.
    """
    tool_result = hook_input.get("tool_result", {})
    cwd = hook_input.get("cwd", os.getcwd())
    tool_name = hook_input.get("tool_name", "")

    # Build validation request
    payload = json.dumps({
        "tool_name": tool_name,
        "tool_result": tool_result,
        "cwd": cwd,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{AUTOBUILDR_API}/api/task-pipeline/validate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            result = json.load(resp)

            if not result.get("valid", True):
                # Validation failed - Ralph Wiggum correction loop
                feedback = result.get("feedback", "Validation failed")
                retry_hint = result.get("retry_hint", "Please fix and retry.")

                print(json.dumps({
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{feedback}\n\n{retry_hint}"
                    ),
                }))
                sys.exit(2)  # Block with feedback

            # Validation passed - allow
            sys.exit(0)

    except urllib.error.URLError:
        # API unavailable - allow
        sys.exit(0)

    except Exception:
        # Unexpected error - allow
        sys.exit(0)


if __name__ == "__main__":
    main()
