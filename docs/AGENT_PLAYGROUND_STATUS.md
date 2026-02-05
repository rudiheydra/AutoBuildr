# Agent Playground - Development Status

**Last Updated:** 2026-02-06

## Overview

The Agent Playground is a testing and iteration environment for AI agents, separate from the production AutoBuildr system. It provides a UI for configuring pipelines, executing agents, and reviewing results.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         agent-playground                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌────────────────┐    ┌─────────────────┐  │
│  │     UI       │───▶│  DSPy Backend  │───▶│ Agent Executor  │  │
│  │  (React)     │    │  (FastAPI)     │    │  (Express/TS)   │  │
│  │  port 5173   │    │  port 8100     │    │  port 8200      │  │
│  └──────────────┘    └────────────────┘    └────────┬────────┘  │
│                                                      │           │
│                                                      ▼           │
│                                              ┌──────────────┐    │
│                                              │  Claude CLI  │    │
│                                              │  (subprocess)│    │
│                                              └──────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. UI (React + Vite)
- Pipeline configuration and management
- Execution interface with SSE streaming
- Chat-style output display
- Tool call visualization

### 2. DSPy Backend (Python/FastAPI)
- Pipeline CRUD operations
- Execution orchestration
- SSE event streaming to UI
- Database persistence (SQLite)
- **NEW:** Git Worktree Sandbox integration

### 3. Agent Executor (TypeScript/Express)
- Bridges DSPy Backend to Claude CLI
- Spawns Claude CLI as subprocess
- Handles tool permissions and configuration
- Returns structured execution results

## Recent Work Completed

### Claude CLI Integration (Complete)
- Replaced placeholder responses with real Claude CLI execution
- Added `/api/execute` endpoint that spawns Claude CLI
- Supports configurable tools, max_turns, and permission modes
- Returns structured messages and tool call history

**Key Files:**
- `agent-executor/src/routes/execute.ts` - Execution endpoint
- `agent-executor/src/services/claudeExecutor.ts` - CLI subprocess management

### Git Worktree Sandbox Feature (Complete)
Agents can now operate in isolated git worktrees, preventing accidental changes to real repositories.

**Flow:**
1. Execution starts → Sandbox worktree created
2. Agent runs in sandbox directory
3. Changes captured as unified diff
4. User reviews diff → Apply or Discard

**Implementation:**
- `dspy-backend/app/services/sandbox.py` - SandboxManager class
  - `create_sandbox()` - Creates git worktree
  - `get_sandbox_diff()` - Captures changes
  - `destroy_sandbox()` - Cleanup
  - `apply_to_repo()` - Cherry-pick changes to main repo

**New API Endpoints:**
- `GET /api/executions/{id}/sandbox` - Get sandbox info and diff
- `POST /api/executions/{id}/sandbox/apply` - Apply changes to repo
- `POST /api/executions/{id}/sandbox/discard` - Discard changes
- `POST /api/executions/{id}/sandbox/refresh-diff` - Refresh diff

**Database Changes:**
- `Pipeline.repo_path` - Target repository path
- `Pipeline.use_sandbox` - Enable sandbox mode
- `Execution.sandbox_path` - Path to worktree used
- `Execution.sandbox_diff` - Captured diff text
- `Execution.sandbox_status` - `active` | `pending_review` | `applied` | `discarded`

**SSE Events Added:**
- `sandbox` - Sandbox creation status
- `sandbox_diff` - Diff data after execution

### Test Pipeline Created
A sandbox-enabled pipeline exists for testing:
- **Name:** Sandbox Agent (repo-concierge)
- **ID:** `e03b7b2b-de4e-4514-b7b2-8c323d8afa8c`
- **Repo:** `/home/rudih/workspace/AutoBuildr/docker/test-project/repo-concierge`
- **Tools:** Read, Write, Edit, Bash, Glob, Grep, WebSearch

## Verified Working

| Feature | Status | Notes |
|---------|--------|-------|
| Pipeline CRUD | ✅ | Create, read, update, delete pipelines |
| Execution streaming | ✅ | SSE events flow to UI |
| Claude CLI execution | ✅ | Real responses from Claude |
| Tool configuration | ✅ | Allowed tools passed to CLI |
| Sandbox creation | ✅ | Git worktree isolated execution |
| Diff capture | ✅ | Changes shown after execution |
| Sandbox discard | ✅ | Cleanup works correctly |
| Sandbox apply | ✅ | Cherry-pick to main repo |

## Known Limitations / TODO

### UI Components Needed
- [ ] Diff viewer component (syntax-highlighted)
- [ ] Apply/Discard buttons in execution results
- [ ] Sandbox status indicator
- [ ] Repository configuration in pipeline settings

### Backend Improvements
- [ ] Timeout handling for long-running sandbox operations
- [ ] Sandbox auto-cleanup on execution deletion
- [ ] Support for nested git repos (submodules)

### Testing
- [ ] Unit tests for sandbox service
- [ ] Integration tests for full execution flow
- [ ] E2E tests with Playwright

## Running the Environment

```bash
# Terminal 1: Start DSPy Backend
cd agent-playground/dspy-backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 2: Start Agent Executor
cd agent-playground/agent-executor
pnpm dev  # Runs on port 8200

# Terminal 3: Start UI (optional)
cd agent-playground/ui
pnpm dev  # Runs on port 5173
```

## File Changes Summary

### Modified Files
- `agent-executor/src/index.ts` - Route registration
- `agent-executor/src/routes/sessions.ts` - Session management
- `dspy-backend/app/database.py` - Schema migration support
- `dspy-backend/app/models/execution.py` - Sandbox fields
- `dspy-backend/app/models/pipeline.py` - Repo config fields
- `dspy-backend/app/routers/executions.py` - Sandbox integration
- `dspy-backend/app/schemas/pipeline.py` - API schemas

### New Files
- `agent-executor/src/routes/execute.ts` - Execution endpoint
- `agent-executor/src/services/claudeExecutor.ts` - CLI executor
- `dspy-backend/app/services/__init__.py` - Services package
- `dspy-backend/app/services/sandbox.py` - Sandbox manager

## Related Documentation

- AutoBuildr main docs: `/docs/`
- Agent Playground README: `/agent-playground/README.md`
