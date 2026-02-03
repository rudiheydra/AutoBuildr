"""
FastAPI Main Application
========================

Main entry point for the Autonomous Coding UI server.
Provides REST API, WebSocket, and static file serving.
"""

import asyncio
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Fix for Windows subprocess support in asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import (
    agent_router,
    agent_runs_router,
    agent_specs_router,
    artifacts_router,
    assistant_chat_router,
    devserver_router,
    expand_project_router,
    features_router,
    filesystem_router,
    planning_decisions_router,
    projects_router,
    schedules_router,
    settings_router,
    spec_builder_router,
    spec_creation_router,
    terminal_router,
)
from .schemas import SetupStatus
from .services.assistant_chat_session import cleanup_all_sessions as cleanup_assistant_sessions
from .services.dev_server_manager import (
    cleanup_all_devservers,
    cleanup_orphaned_devserver_locks,
)
from .services.expand_chat_session import cleanup_all_expand_sessions
from .services.process_manager import cleanup_all_managers, cleanup_orphaned_locks
from .services.scheduler_service import cleanup_scheduler, get_scheduler
from .services.terminal_manager import cleanup_all_terminals
from .websocket import project_websocket
from .exceptions import register_exception_handlers

# Paths
ROOT_DIR = Path(__file__).parent.parent
UI_DIST_DIR = ROOT_DIR / "ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    import logging
    _logger = logging.getLogger(__name__)

    # Startup - clean up orphaned lock files from previous runs
    cleanup_orphaned_locks()
    cleanup_orphaned_devserver_locks()

    # Initialize the global database session maker for AgentRun/AgentSpec endpoints.
    # Use the project directory (where harness_kernel writes) rather than ROOT_DIR
    # so that the agent-runs API reads from the same DB as the execution engine.
    from api.database import create_database, set_session_maker
    db_dir = Path(os.environ.get("AUTOBUILDR_TEST_PROJECT_PATH", str(ROOT_DIR)))
    _logger.info("Global session maker DB dir: %s", db_dir)
    _, session_maker = create_database(db_dir)
    set_session_maker(session_maker)

    # Feature #79: Clean up orphaned AgentRuns from previous server instance
    # This must happen after database initialization
    from api.orphaned_run_cleanup import cleanup_orphaned_runs
    try:
        with session_maker() as session:
            result = cleanup_orphaned_runs(session, project_dir=db_dir)
            if result.cleaned_count > 0:
                _logger.info(
                    "Cleaned %d orphaned AgentRuns on startup",
                    result.cleaned_count
                )
            if result.errors:
                _logger.warning(
                    "Errors during orphaned run cleanup: %s",
                    result.errors
                )
    except Exception as e:
        _logger.error("Failed to clean up orphaned runs: %s", e)
        # Don't fail startup on cleanup errors

    # Start the scheduler service
    scheduler = get_scheduler()
    await scheduler.start()

    yield

    # Shutdown - cleanup scheduler first to stop triggering new starts
    await cleanup_scheduler()
    # Then cleanup all running agents, sessions, terminals, and dev servers
    await cleanup_all_managers()
    await cleanup_assistant_sessions()
    await cleanup_all_expand_sessions()
    await cleanup_all_terminals()
    await cleanup_all_devservers()


# Create FastAPI app
app = FastAPI(
    title="Autonomous Coding UI",
    description="Web UI for the Autonomous Coding Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# ============================================================================
# Exception Handlers (Feature #75: Standardized API Error Responses)
# ============================================================================

# Register global exception handlers for consistent error responses
# This ensures all API errors follow the same format:
# {"error_code": "ERROR_TYPE", "message": "Human-readable message", "details": {...}}
register_exception_handlers(app)

# Check if remote access is enabled via environment variable
# Set by start_ui.py when --host is not 127.0.0.1
ALLOW_REMOTE = os.environ.get("AUTOBUILDR_ALLOW_REMOTE", "").lower() in ("1", "true", "yes")

# CORS - allow all origins when remote access is enabled, otherwise localhost only
if ALLOW_REMOTE:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins for remote access
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",      # Vite dev server
            "http://127.0.0.1:5173",
            "http://localhost:8888",      # Production
            "http://127.0.0.1:8888",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ============================================================================
# Security Middleware
# ============================================================================

if not ALLOW_REMOTE:
    @app.middleware("http")
    async def require_localhost(request: Request, call_next):
        """Only allow requests from localhost (disabled when AUTOBUILDR_ALLOW_REMOTE=1)."""
        client_host = request.client.host if request.client else None

        # Allow localhost connections
        if client_host not in ("127.0.0.1", "::1", "localhost", None):
            raise HTTPException(status_code=403, detail="Localhost access only")

        return await call_next(request)


# ============================================================================
# Include Routers
# ============================================================================

app.include_router(projects_router)
app.include_router(features_router)
app.include_router(agent_router)
app.include_router(agent_runs_router)
app.include_router(agent_specs_router)
app.include_router(artifacts_router)
app.include_router(schedules_router)
app.include_router(devserver_router)
app.include_router(spec_builder_router)
app.include_router(spec_creation_router)
app.include_router(expand_project_router)
app.include_router(filesystem_router)
app.include_router(assistant_chat_router)
app.include_router(settings_router)
app.include_router(terminal_router)
app.include_router(planning_decisions_router)  # Feature #179


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws/projects/{project_name}")
async def websocket_endpoint(websocket: WebSocket, project_name: str):
    """WebSocket endpoint for real-time project updates."""
    await project_websocket(websocket, project_name)


# ============================================================================
# Setup & Health Endpoints
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/setup/status", response_model=SetupStatus)
async def setup_status():
    """Check system setup status."""
    # Check for Claude CLI
    claude_cli = shutil.which("claude") is not None

    # Check for CLI configuration directory
    # Note: CLI no longer stores credentials in ~/.claude/.credentials.json
    # The existence of ~/.claude indicates the CLI has been configured
    claude_dir = Path.home() / ".claude"
    has_claude_config = claude_dir.exists() and claude_dir.is_dir()

    # If GLM mode is configured via .env, we have alternative credentials
    glm_configured = bool(os.getenv("ANTHROPIC_BASE_URL") and os.getenv("ANTHROPIC_AUTH_TOKEN"))
    credentials = has_claude_config or glm_configured

    # Check for Node.js and npm
    node = shutil.which("node") is not None
    npm = shutil.which("npm") is not None

    return SetupStatus(
        claude_cli=claude_cli,
        credentials=credentials,
        node=node,
        npm=npm,
    )


# ============================================================================
# Static File Serving (Production)
# ============================================================================

# Serve React build files if they exist
if UI_DIST_DIR.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=UI_DIST_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        """Serve the React app index.html."""
        return FileResponse(UI_DIST_DIR / "index.html")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """
        Serve static files or fall back to index.html for SPA routing.
        """
        # Check if the path is an API route (shouldn't hit this due to router ordering)
        if path.startswith("api/") or path.startswith("ws/"):
            raise HTTPException(status_code=404)

        # Try to serve the file directly
        file_path = UI_DIST_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Fall back to index.html for SPA routing
        return FileResponse(UI_DIST_DIR / "index.html")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="127.0.0.1",  # Localhost only for security
        port=8888,
        reload=True,
    )
