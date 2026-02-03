"""
CLI-Based Spec Builder
======================

Generates AgentSpecs using the Claude CLI (claude-agent-sdk) instead of
the direct Anthropic API. This allows spec generation using a Claude
subscription rather than requiring an API key.

Usage:
    from api.cli_spec_builder import CLISpecBuilder, generate_spec_via_cli

    # Direct function call
    result = generate_spec_via_cli(
        task_description="Implement E2E tests with Playwright",
        task_type="testing",
        context={"capability": "playwright"},
    )

    # Or via class
    builder = CLISpecBuilder()
    result = builder.build(task_description, task_type, context)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_logger = logging.getLogger(__name__)


@dataclass
class CLIBuildResult:
    """Result of CLI-based spec generation."""
    success: bool
    agent_spec: Optional[Any] = None  # AgentSpec
    error: Optional[str] = None
    raw_response: Optional[str] = None


# Prompt template for generating AgentSpecs via CLI
SPEC_GENERATION_PROMPT = '''You are generating an AgentSpec for a Claude Code agent.

Task Description:
{task_description}

Task Type: {task_type}

Context:
{context}

Generate a JSON object with these exact fields:
{{
    "name": "lowercase-hyphenated-name",
    "display_name": "Human Readable Name",
    "objective": "Detailed objective describing what the agent should accomplish...",
    "task_type": "{task_type}",
    "tool_policy": {{
        "allowed_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        "forbidden_patterns": ["rm -rf /", "curl.*|.*sh"],
        "tool_hints": {{}}
    }},
    "max_turns": 50,
    "timeout_seconds": 1800,
    "tags": ["tag1", "tag2"]
}}

Rules:
1. Name should be descriptive and lowercase with hyphens (e.g., "playwright-e2e-tester")
2. Objective should be detailed (100-500 words) explaining responsibilities
3. Include appropriate tools for the task type
4. For testing tasks, include browser automation tools if needed
5. Tags should reflect the capability and task type

Respond with ONLY the JSON object, no other text.'''


def _is_cli_available() -> bool:
    """Check if Claude CLI is available."""
    return shutil.which("claude") is not None


async def _generate_via_sdk(
    prompt: str,
    *,
    max_turns: int = 5,
    timeout_seconds: int = 120,
) -> str:
    """Generate response using Claude Agent SDK."""
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

    options = ClaudeAgentOptions(
        max_turns=max_turns,
        permission_mode="bypassPermissions",
        allowed_tools=[],  # No tools needed for text generation
    )

    response_text = ""

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for msg in client.receive_response():
            msg_type = type(msg).__name__

            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    if hasattr(block, "text"):
                        response_text += block.text

    return response_text


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Event loop already running — use thread pool
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()


def _parse_spec_from_response(
    response: str,
    task_type: str,
    context: dict[str, Any],
) -> Optional[Any]:
    """Parse AgentSpec from CLI response."""
    from api.agentspec_models import AgentSpec, generate_uuid
    from api.tool_policy import create_tool_policy

    # Try to extract JSON from response
    json_match = re.search(r'\{[\s\S]*\}', response)
    if not json_match:
        _logger.warning("No JSON found in CLI response")
        return None

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        _logger.warning("Failed to parse JSON from CLI response: %s", e)
        return None

    # Build tool_policy
    tool_policy_data = data.get("tool_policy", {})
    tool_policy = create_tool_policy(
        allowed_tools=tool_policy_data.get("allowed_tools", ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]),
        forbidden_patterns=tool_policy_data.get("forbidden_patterns", []),
        tool_hints=tool_policy_data.get("tool_hints", {}),
    )

    # Create AgentSpec
    spec = AgentSpec(
        id=generate_uuid(),
        name=data.get("name", f"{task_type}-agent"),
        display_name=data.get("display_name", f"{task_type.title()} Agent"),
        objective=data.get("objective", ""),
        task_type=data.get("task_type", task_type),
        context=context,
        tool_policy=tool_policy,
        max_turns=data.get("max_turns", 50),
        timeout_seconds=data.get("timeout_seconds", 1800),
        tags=data.get("tags", [task_type]),
        source_feature_id=context.get("feature_id"),
    )

    return spec


def generate_spec_via_cli(
    task_description: str,
    task_type: str = "coding",
    context: Optional[dict[str, Any]] = None,
    *,
    timeout_seconds: int = 120,
) -> CLIBuildResult:
    """
    Generate an AgentSpec using the Claude CLI.

    This uses the user's Claude subscription via the CLI instead of
    requiring an API key.

    Args:
        task_description: Description of what the agent should do
        task_type: Type of task (coding, testing, audit, etc.)
        context: Additional context for the spec
        timeout_seconds: Timeout for CLI execution

    Returns:
        CLIBuildResult with the generated spec or error
    """
    if not _is_cli_available():
        return CLIBuildResult(
            success=False,
            error="Claude CLI not available. Install with: npm install -g @anthropic-ai/claude-code",
        )

    context = context or {}
    context_str = json.dumps(context, indent=2) if context else "{}"

    prompt = SPEC_GENERATION_PROMPT.format(
        task_description=task_description,
        task_type=task_type,
        context=context_str,
    )

    try:
        _logger.info("Generating spec via Claude CLI for task_type=%s", task_type)

        response = _run_async(
            _generate_via_sdk(
                prompt,
                max_turns=3,
                timeout_seconds=timeout_seconds,
            )
        )

        _logger.debug("CLI response: %s", response[:500] if response else "empty")

        if not response:
            return CLIBuildResult(
                success=False,
                error="Empty response from Claude CLI",
                raw_response=response,
            )

        # Parse the response into an AgentSpec
        spec = _parse_spec_from_response(response, task_type, context)

        if spec:
            _logger.info("Successfully generated spec via CLI: %s", spec.name)
            return CLIBuildResult(
                success=True,
                agent_spec=spec,
                raw_response=response,
            )
        else:
            return CLIBuildResult(
                success=False,
                error="Failed to parse AgentSpec from CLI response",
                raw_response=response,
            )

    except Exception as e:
        _logger.exception("CLI spec generation failed: %s", e)
        return CLIBuildResult(
            success=False,
            error=f"CLI execution failed: {e}",
        )


class CLISpecBuilder:
    """
    Spec builder that uses Claude CLI instead of direct API.

    Drop-in replacement for SpecBuilder when API key is not available.
    """

    def __init__(self, timeout_seconds: int = 120):
        self.timeout_seconds = timeout_seconds
        self._available = _is_cli_available()

        if not self._available:
            _logger.warning("Claude CLI not available for CLISpecBuilder")

    @property
    def is_available(self) -> bool:
        """Check if CLI is available."""
        return self._available

    def build(
        self,
        task_description: str,
        task_type: str = "coding",
        context: Optional[dict[str, Any]] = None,
        source_feature_id: Optional[int] = None,
    ) -> CLIBuildResult:
        """
        Build an AgentSpec using the Claude CLI.

        Interface matches SpecBuilder.build() for compatibility.
        """
        ctx = context or {}
        if source_feature_id:
            ctx["feature_id"] = source_feature_id

        return generate_spec_via_cli(
            task_description=task_description,
            task_type=task_type,
            context=ctx,
            timeout_seconds=self.timeout_seconds,
        )


# Singleton instance
_cli_builder: Optional[CLISpecBuilder] = None


def get_cli_spec_builder() -> CLISpecBuilder:
    """Get or create the singleton CLISpecBuilder."""
    global _cli_builder
    if _cli_builder is None:
        _cli_builder = CLISpecBuilder()
    return _cli_builder
