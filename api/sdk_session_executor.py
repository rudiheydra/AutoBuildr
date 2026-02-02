"""
SDK Session Executor
====================

Session-level executor using ClaudeSDKClient (Claude Agent SDK).

Unlike the raw Messages API turn executor (turn_executor.py) which executes
one API round-trip per call, this executor runs the entire Claude Code CLI
session as one call. The agent gets full tool access (Read, Write, Bash,
MCP, etc.) while the caller retains spec compilation, DB persistence, and
acceptance validation.

Usage:
    from api.sdk_session_executor import ClaudeAgentSDKSessionExecutor

    executor = ClaudeAgentSDKSessionExecutor(project_dir=Path("/my/project"))

    # Pass as callable to HarnessKernel (same interface as ClaudeSDKTurnExecutor)
    kernel = HarnessKernel(db)
    run = kernel.execute(spec, turn_executor=executor)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from api.turn_executor import TurnResult

if TYPE_CHECKING:
    from api.agentspec_models import AgentRun, AgentSpec

_logger = logging.getLogger(__name__)

# Default session timeout (seconds)
DEFAULT_TIMEOUT_SECONDS = 600

# Default max turns for SDK session
DEFAULT_MAX_TURNS = 1000

# Environment variables to pass through to Claude CLI for API configuration
# (mirrors client.py:31-38)
API_ENV_VARS = [
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "API_TIMEOUT_MS",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
]


class ClaudeAgentSDKSessionExecutor:
    """
    Session executor that runs an entire Claude Code CLI session as one call.

    Bridges sync HarnessKernel -> async Claude Agent SDK by running the
    complete session inside asyncio.run() (with ThreadPoolExecutor fallback
    for existing event loops).

    The __call__ signature matches ClaudeSDKTurnExecutor so it's a drop-in
    replacement for HarnessKernel.execute(turn_executor=...).

    Args:
        project_dir: Root project directory (cwd for Claude CLI)
        model: Claude model to use (defaults from env or claude-sonnet-4-20250514)
        yolo_mode: If True, skip Playwright MCP server
    """

    def __init__(
        self,
        project_dir: Path,
        model: str | None = None,
        yolo_mode: bool = False,
    ):
        self.project_dir = Path(project_dir).resolve()
        self.model = model or os.getenv(
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "claude-sonnet-4-20250514",
        )
        self.yolo_mode = yolo_mode

    def __call__(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
    ) -> tuple[bool, dict[str, Any], list[dict[str, Any]], int, int]:
        """
        Execute the full session. Returns completed=True since the entire
        session runs in one call (no multi-turn kernel loop needed).

        Bridges sync -> async via asyncio.run() with ThreadPoolExecutor
        fallback for existing event loops.
        """
        try:
            # Try asyncio.run() first (works when no event loop is running)
            try:
                result = asyncio.run(self._execute_session(run, spec))
            except RuntimeError:
                # Event loop already running — use thread pool fallback
                _logger.debug("Existing event loop detected, using thread pool")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._execute_session(run, spec),
                    )
                    result = future.result()

            return result.as_tuple()

        except Exception as e:
            _logger.error(
                "SDK session executor error for run %s: %s: %s",
                run.id, type(e).__name__, str(e)[:500],
            )
            return TurnResult(
                completed=True,
                turn_data={
                    "error": True,
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:1000],
                    "response_text": "",
                },
                tool_events=[],
                tokens_in=0,
                tokens_out=0,
            ).as_tuple()

    async def _execute_session(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
    ) -> TurnResult:
        """
        Run the full Claude Code CLI session with timeout guard.
        """
        timeout = spec.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        try:
            return await asyncio.wait_for(
                self._run_session(run, spec),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            _logger.error(
                "SDK session timed out after %ds for run %s",
                timeout, run.id,
            )
            return TurnResult(
                completed=True,
                turn_data={
                    "error": True,
                    "error_type": "TimeoutError",
                    "error_message": f"SDK session exceeded {timeout}s timeout",
                    "response_text": "",
                },
            )

    async def _run_session(
        self,
        run: "AgentRun",
        spec: "AgentSpec",
    ) -> TurnResult:
        """
        Core session logic: build options, connect client, stream response.
        """
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        options = self._build_options(spec)

        # Build prompt from spec objective + context
        prompt = self._build_prompt(spec)

        response_text = ""
        tool_events: list[dict[str, Any]] = []
        tokens_in = 0
        tokens_out = 0

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
                msg_type = type(msg).__name__

                if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                    for block in msg.content:
                        block_type = type(block).__name__

                        if block_type == "TextBlock" and hasattr(block, "text"):
                            response_text += block.text

                        elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                            tool_events.append({
                                "tool_name": getattr(block, "name", "unknown"),
                                "arguments": getattr(block, "input", {}),
                                "result": None,
                                "is_error": False,
                                "tool_use_id": getattr(block, "id", None),
                            })

                elif msg_type == "UserMessage" and hasattr(msg, "content"):
                    for block in msg.content:
                        block_type = type(block).__name__

                        if block_type == "ToolResultBlock":
                            result_content = getattr(block, "content", "")
                            is_error = getattr(block, "is_error", False)
                            tool_use_id = getattr(block, "tool_use_id", None)

                            # Update matching tool event with result
                            for te in reversed(tool_events):
                                if te.get("tool_use_id") == tool_use_id:
                                    te["result"] = str(result_content)[:2000]
                                    te["is_error"] = is_error
                                    break

                elif msg_type == "ResultMessage":
                    # Extract session-level token totals if available
                    usage = getattr(msg, "usage", None)
                    if usage:
                        tokens_in = getattr(usage, "input_tokens", 0) or 0
                        tokens_out = getattr(usage, "output_tokens", 0) or 0

        return TurnResult(
            completed=True,
            turn_data={
                "response_text": response_text[:4000],
                "num_tools": len(tool_events),
                "executor": "claude_sdk_session",
            },
            tool_events=tool_events,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _build_prompt(self, spec: "AgentSpec") -> str:
        """Build the user prompt from spec objective and context."""
        parts = []

        if spec.objective:
            parts.append(spec.objective)

        if spec.context and isinstance(spec.context, dict):
            context_str = "\n".join(
                f"{k}: {v}" for k, v in spec.context.items()
                if v is not None
            )
            if context_str:
                parts.append(f"\nContext:\n{context_str}")

        return "\n\n".join(parts) if parts else "Complete the assigned task."

    def _build_options(self, spec: "AgentSpec") -> Any:
        """
        Build ClaudeAgentOptions from spec + project configuration.

        Reuses patterns from client.py (MCP servers, security settings,
        environment passthrough, hooks).
        """
        from claude_agent_sdk import ClaudeAgentOptions
        from claude_agent_sdk.types import HookMatcher

        from security import bash_security_hook

        project_dir = self.project_dir

        # --- System prompt ---
        system_prompt = spec.objective or "Complete the assigned task."
        if spec.context and isinstance(spec.context, dict):
            context_str = "\n".join(
                f"{k}: {v}" for k, v in spec.context.items()
                if v is not None
            )
            if context_str:
                system_prompt += f"\n\nContext:\n{context_str}"

        # --- Allowed tools ---
        allowed_tools = self._resolve_allowed_tools(spec)

        # --- MCP servers (mirrors client.py:216-248) ---
        mcp_servers = {
            "features": {
                "command": sys.executable,
                "args": ["-m", "mcp_server.feature_mcp"],
                "env": {
                    "PROJECT_DIR": str(project_dir),
                    "PYTHONPATH": str(Path(__file__).parent.parent.resolve()),
                },
            },
        }
        if not self.yolo_mode:
            playwright_args = ["@playwright/mcp@latest", "--viewport-size", "1280x720"]
            # Always headless in automated execution
            playwright_args.append("--headless")
            mcp_servers["playwright"] = {
                "command": "npx",
                "args": playwright_args,
            }

        # --- Security settings (mirrors client.py:179-197) ---
        security_settings = {
            "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
            "permissions": {
                "defaultMode": "acceptEdits",
                "allow": [
                    "Read(./**)", "Write(./**)", "Edit(./**)",
                    "Glob(./**)", "Grep(./**)", "Bash(*)",
                    "WebFetch", "WebSearch",
                ],
            },
        }

        project_dir.mkdir(parents=True, exist_ok=True)
        settings_file = project_dir / ".claude_settings.json"
        settings_file.write_text(json.dumps(security_settings, indent=2), encoding="utf-8")

        # --- Environment passthrough (mirrors client.py:250-270) ---
        sdk_env: dict[str, str] = {}
        for var in API_ENV_VARS:
            value = os.getenv(var)
            if value:
                sdk_env[var] = value

        # Detect alternative API for beta flag decision
        base_url = sdk_env.get("ANTHROPIC_BASE_URL", "")
        is_alternative_api = bool(base_url)

        # --- CLI path ---
        cli_path = shutil.which("claude")

        # --- Bash security hook (mirrors client.py:272-278) ---
        async def bash_hook_with_context(input_data, tool_use_id=None, context=None):
            if context is None:
                context = {}
            context["project_dir"] = str(project_dir)
            return await bash_security_hook(input_data, tool_use_id, context)

        # --- Build options ---
        return ClaudeAgentOptions(
            model=self.model,
            cli_path=cli_path,
            system_prompt=system_prompt,
            setting_sources=["project"],
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher="Bash", hooks=[bash_hook_with_context]),
                ],
            },
            max_turns=spec.max_turns or DEFAULT_MAX_TURNS,
            cwd=str(project_dir),
            settings=str(settings_file.resolve()),
            env=sdk_env,
            permission_mode="bypassPermissions",
            betas=[] if is_alternative_api else ["context-1m-2025-08-07"],
        )

    def _resolve_allowed_tools(self, spec: "AgentSpec") -> list[str]:
        """
        Map spec tool_policy.allowed_tools to SDK tool names.

        Rules:
        - Built-in tools (Read, Write, Bash, etc.) pass through as-is
        - Tools already prefixed with 'mcp__' pass through as-is
        - Unprefixed feature tools get 'mcp__features__' prefix
        """
        builtin_tools = {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebFetch", "WebSearch"}

        raw_tools: list[str] = []
        if spec.tool_policy and isinstance(spec.tool_policy, dict):
            raw_tools = spec.tool_policy.get("allowed_tools", [])

        if not raw_tools:
            # Default: all built-ins + feature tools
            from client import BUILTIN_TOOLS, FEATURE_MCP_TOOLS
            return [*BUILTIN_TOOLS, *FEATURE_MCP_TOOLS]

        resolved = []
        for tool in raw_tools:
            if tool in builtin_tools:
                resolved.append(tool)
            elif tool.startswith("mcp__"):
                resolved.append(tool)
            else:
                # Assume it's a feature tool — add prefix
                resolved.append(f"mcp__features__{tool}")

        return resolved
