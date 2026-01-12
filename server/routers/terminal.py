"""
Terminal Router
===============

WebSocket endpoint for interactive terminal I/O with PTY support.
Provides real-time bidirectional communication with terminal sessions.
"""

import asyncio
import base64
import json
import logging
import re
import sys
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.terminal_manager import get_terminal_session

# Add project root to path for registry import
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import get_project_path as registry_get_project_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


class TerminalCloseCode:
    """WebSocket close codes for terminal endpoint."""

    INVALID_PROJECT_NAME = 4000
    PROJECT_NOT_FOUND = 4004
    FAILED_TO_START = 4500


def _get_project_path(project_name: str) -> Path | None:
    """Get project path from registry."""
    return registry_get_project_path(project_name)


def validate_project_name(name: str) -> bool:
    """
    Validate project name to prevent path traversal attacks.

    Allows only alphanumeric characters, underscores, and hyphens.
    Maximum length of 50 characters.

    Args:
        name: The project name to validate

    Returns:
        True if valid, False otherwise
    """
    return bool(re.match(r"^[a-zA-Z0-9_-]{1,50}$", name))


@router.websocket("/ws/{project_name}")
async def terminal_websocket(websocket: WebSocket, project_name: str) -> None:
    """
    WebSocket endpoint for interactive terminal I/O.

    Message protocol:

    Client -> Server:
    - {"type": "input", "data": "<base64-encoded-bytes>"} - Keyboard input
    - {"type": "resize", "cols": 80, "rows": 24} - Terminal resize
    - {"type": "ping"} - Keep-alive ping

    Server -> Client:
    - {"type": "output", "data": "<base64-encoded-bytes>"} - PTY output
    - {"type": "exit", "code": 0} - Shell process exited
    - {"type": "pong"} - Keep-alive response
    - {"type": "error", "message": "..."} - Error message
    """
    # Validate project name
    if not validate_project_name(project_name):
        await websocket.close(
            code=TerminalCloseCode.INVALID_PROJECT_NAME, reason="Invalid project name"
        )
        return

    # Look up project directory from registry
    project_dir = _get_project_path(project_name)
    if not project_dir:
        await websocket.close(
            code=TerminalCloseCode.PROJECT_NOT_FOUND,
            reason="Project not found in registry",
        )
        return

    if not project_dir.exists():
        await websocket.close(
            code=TerminalCloseCode.PROJECT_NOT_FOUND,
            reason="Project directory not found",
        )
        return

    await websocket.accept()

    # Get or create terminal session for this project
    session = get_terminal_session(project_name, project_dir)

    # Queue for output data to send to client
    output_queue: asyncio.Queue[bytes] = asyncio.Queue()

    # Callback to receive terminal output and queue it for sending
    def on_output(data: bytes) -> None:
        """Queue terminal output for async sending to WebSocket."""
        try:
            output_queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning(f"Output queue full for {project_name}, dropping data")

    # Register the output callback
    session.add_output_callback(on_output)

    # Start the terminal session if not already active
    if not session.is_active:
        started = await session.start()
        if not started:
            session.remove_output_callback(on_output)
            try:
                await websocket.send_json(
                    {"type": "error", "message": "Failed to start terminal session"}
                )
            except Exception:
                pass
            await websocket.close(
                code=TerminalCloseCode.FAILED_TO_START, reason="Failed to start terminal"
            )
            return

    # Task to send queued output to WebSocket
    async def send_output_task() -> None:
        """Continuously send queued output to the WebSocket client."""
        try:
            while True:
                # Wait for output data
                data = await output_queue.get()

                # Encode as base64 and send
                encoded = base64.b64encode(data).decode("ascii")
                await websocket.send_json({"type": "output", "data": encoded})

        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.warning(f"Error sending output for {project_name}: {e}")
            raise

    # Task to monitor if the terminal session exits
    async def monitor_exit_task() -> None:
        """Monitor the terminal session and notify client on exit."""
        try:
            while session.is_active:
                await asyncio.sleep(0.5)

            # Session ended - send exit message
            # Note: We don't have access to actual exit code from PTY
            await websocket.send_json({"type": "exit", "code": 0})

        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            raise
        except Exception as e:
            logger.warning(f"Error in exit monitor for {project_name}: {e}")

    # Start background tasks
    output_task = asyncio.create_task(send_output_task())
    exit_task = asyncio.create_task(monitor_exit_task())

    try:
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "input":
                    # Decode base64 input and write to PTY
                    encoded_data = message.get("data", "")
                    # Add size limit to prevent DoS
                    if len(encoded_data) > 65536:  # 64KB limit for base64 encoded data
                        await websocket.send_json({"type": "error", "message": "Input too large"})
                        continue
                    if encoded_data:
                        try:
                            decoded = base64.b64decode(encoded_data)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to decode base64 input: {e}")
                            await websocket.send_json(
                                {"type": "error", "message": "Invalid base64 data"}
                            )
                            continue

                        try:
                            session.write(decoded)
                        except Exception as e:
                            logger.warning(f"Failed to write to terminal: {e}")
                            await websocket.send_json(
                                {"type": "error", "message": "Failed to write to terminal"}
                            )

                elif msg_type == "resize":
                    # Resize the terminal
                    cols = message.get("cols", 80)
                    rows = message.get("rows", 24)

                    # Validate dimensions
                    if isinstance(cols, int) and isinstance(rows, int):
                        cols = max(10, min(500, cols))
                        rows = max(5, min(200, rows))
                        session.resize(cols, rows)
                    else:
                        await websocket.send_json({"type": "error", "message": "Invalid resize dimensions"})

                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        logger.info(f"Terminal WebSocket disconnected for {project_name}")

    except Exception as e:
        logger.exception(f"Terminal WebSocket error for {project_name}")
        try:
            await websocket.send_json({"type": "error", "message": f"Server error: {str(e)}"})
        except Exception:
            pass

    finally:
        # Cancel background tasks
        output_task.cancel()
        exit_task.cancel()

        try:
            await output_task
        except asyncio.CancelledError:
            pass

        try:
            await exit_task
        except asyncio.CancelledError:
            pass

        # Remove the output callback
        session.remove_output_callback(on_output)

        # Only stop session if no other clients are connected
        with session._callbacks_lock:
            remaining_callbacks = len(session._output_callbacks)

        if remaining_callbacks == 0:
            await session.stop()
            logger.info(f"Terminal session stopped for {project_name} (last client disconnected)")
        else:
            logger.info(
                f"Client disconnected from {project_name}, {remaining_callbacks} clients remaining"
            )
