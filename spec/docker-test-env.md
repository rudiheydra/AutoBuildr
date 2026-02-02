# Specification: Dockerized Test Environment

**Project:** AutoBuildr
**Date:** 2026-01-30
**Status:** Approved

---

## Overview

A reproducible, dockerized test environment that runs AutoBuildr and builds the `repo-concierge` project as a test subject. Orchestrated by a Makefile with lifecycle targets: build, start, load test project, trigger agent execution, view logs, stop, and full cleanup.

## Architecture

```
+---------------------------------------------------+
|  Docker Container (autobuildr-test)                |
|                                                    |
|  Python 3.11 + pre-built React UI                  |
|  +---------+  +------------------+                 |
|  | FastAPI |--| SQLite (per-proj)|                 |
|  | :8888   |  +------------------+                 |
|  +---------+                                       |
|       |                                            |
|  /test-projects/repo-concierge/  (cloned at build) |
|  /home/autobuildr/.autobuildr/   (named volume)    |
+---------------------------------------------------+
       |
  Host port ${AUTOBUILDR_PORT:-8888}
```

- **Single container** — SQLite is file-based, no separate DB service
- **docker-compose** — declarative env/volume management, extensible to add services later
- **Multi-stage Dockerfile** — Node 20 build stage (frontend), Python 3.11 runtime stage
- **Named volume** for `~/.autobuildr/` registry persistence

## Test Project

**repo-concierge** — a Python CLI security scanner (85 features). Sourced by:

1. **Primary:** Git clone from GitHub at Docker build time via `REPO_URL` build arg
2. **Fallback:** Local rsync snapshot into `docker/test-project/repo-concierge/` for offline/dev use

The Dockerfile accepts a `REPO_URL` build arg. If provided, it clones the repo. If not, it copies the local snapshot directory.

## Prerequisites

- Docker Engine 20.10+ with Compose V2 (`docker compose`)
- `ANTHROPIC_API_KEY` set in environment or `docker/.env`
- (For snapshot mode) `rsync` and local copy of repo-concierge at `~/workspace/repo-concierge/`
- (For git clone mode) Public GitHub repo URL or token for private repo

---

## File Layout

```
AutoBuildr/
  .dockerignore                          # Build context filtering
  Makefile                               # Lifecycle orchestration
  spec/
    docker-test-env.md                   # This specification
  docker/
    Dockerfile                           # Multi-stage build
    docker-compose.yml                   # Service definition
    .env.example                         # API key template
    scripts/
      entrypoint.sh                      # Container startup modes
      healthcheck.sh                     # Docker HEALTHCHECK probe
      wait-for-ready.sh                  # Poll until server healthy
      load-test-project.sh               # Register project via REST API
      run-build.sh                       # Trigger agent execution via CLI
    test-project/                        # (git-ignored) local snapshot fallback
      repo-concierge/
```

---

## File Specifications

### 1. `.dockerignore` (repo root)

Purpose: Keep Docker build context small (~5MB instead of ~200MB).

Exclude:
- `.git`, `__pycache__`, `*.pyc`, `venv/`, `.venv/`, `*.egg-info`, `.pytest_cache`, `.mypy_cache`
- `ui/node_modules/`, `ui/dist/` (rebuilt in Docker)
- `*.db`, `*.db-shm`, `*.db-wal` (start clean)
- `docker/.env`, `docker/test-project/`
- `.vscode/`, `.idea/`, `*.log`, `claude-progress.txt`
- `generations/`, `automaker/`, `temp/`, `logs/`, `node_modules/`, `.browser-profiles/`
- `.DS_Store`, `Thumbs.db`

### 2. `docker/Dockerfile`

Multi-stage build:

**Stage 1: `frontend-builder`**
- Base: `node:20-slim`
- Workdir: `/build/ui`
- Copy `ui/package.json` + `ui/package-lock.json` first (layer cache)
- `npm ci --silent`
- Copy full `ui/` source
- `npm run build` -> output at `/build/ui/dist/`

**Stage 2: `runtime`**
- Base: `python:3.11-slim`
- Install system deps: `git`, `curl`, `procps`
- Create non-root `autobuildr` user
- Copy and install `requirements.txt` (cached layer)
- Copy application source: root `*.py`, `api/`, `server/`, `prompts/`, `mcp_server/`, `.claude/`
- Copy frontend from Stage 1: `ui/dist/`
- **Test project acquisition** (build args):
  - `ARG REPO_URL=""` — if set, `git clone $REPO_URL /test-projects/repo-concierge`
  - If not set, `COPY docker/test-project/repo-concierge/ /test-projects/repo-concierge/` (local snapshot fallback)
- Copy `docker/scripts/` -> `/docker-scripts/`, `chmod +x`
- Create runtime directories: `/home/autobuildr/.autobuildr`
- `chown -R autobuildr:autobuildr /app /test-projects /home/autobuildr`
- ENV defaults: `AUTOBUILDR_ALLOW_REMOTE=1`, `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`
- EXPOSE 8888
- USER autobuildr
- HEALTHCHECK: `--interval=10s --timeout=5s --start-period=30s --retries=3` -> `/docker-scripts/healthcheck.sh`
- ENTRYPOINT: `/docker-scripts/entrypoint.sh`
- CMD: `serve`

### 3. `docker/docker-compose.yml`

```yaml
services:
  autobuildr:
    build:
      context: ..
      dockerfile: docker/Dockerfile
      args:
        REPO_URL: ${REPO_URL:-}
    container_name: autobuildr-test
    ports:
      - "${AUTOBUILDR_PORT:-8888}:8888"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AUTOBUILDR_ALLOW_REMOTE=1
      - AUTOBUILDR_TEST_PROJECT_PATH=/test-projects/repo-concierge
      - AUTOBUILDR_TEST_PROJECT_NAME=repo-concierge
    env_file:
      - path: .env
        required: false
    volumes:
      - autobuildr-data:/home/autobuildr/.autobuildr
      # Uncomment for live host files during development:
      # - ../../repo-concierge:/test-projects/repo-concierge
    restart: "no"

volumes:
  autobuildr-data:
    name: autobuildr-test-data
```

### 4. `docker/.env.example`

```
# Copy to .env and fill in your API key
ANTHROPIC_API_KEY=sk-ant-your-key-here
# AUTOBUILDR_PORT=8888
# REPO_URL=https://github.com/youruser/repo-concierge.git
```

### 5. `docker/scripts/entrypoint.sh`

Validates `ANTHROPIC_API_KEY` is set (exits with clear error message and setup instructions if missing).

Accepts command argument:

| Command | Behavior |
|---------|----------|
| `serve` (default) | `exec python -m uvicorn server.main:app --host 0.0.0.0 --port 8888` |
| `load-project` | Wait for healthy server, run `load-test-project.sh` |
| `build-project` | Wait for healthy, load project, run `run-build.sh` |
| `full` | Start server in background, wait healthy, load project, print ready message, wait on server PID |
| `*` (anything else) | `exec "$@"` passthrough |

### 6. `docker/scripts/healthcheck.sh`

```bash
curl -sf http://localhost:8888/api/health || exit 1
```

Hits the existing `GET /api/health` endpoint (`server/main.py:213`).

### 7. `docker/scripts/wait-for-ready.sh`

- Polls `GET http://localhost:8888/api/health` every 2 seconds
- Max wait: 60 seconds
- Prints elapsed time on success
- Exits 1 with error on timeout

### 8. `docker/scripts/load-test-project.sh`

- Reads `AUTOBUILDR_TEST_PROJECT_NAME` (default: `repo-concierge`) and `AUTOBUILDR_TEST_PROJECT_PATH` (default: `/test-projects/repo-concierge`)
- Checks if already registered: `GET /api/projects/{name}` (HTTP 200 = skip)
- If not registered: `POST /api/projects` with JSON `{"name": "$NAME", "path": "$PATH"}`
  - Matches `ProjectCreate` schema (`server/schemas.py:27-31`): name (str, 1-50 alphanum+hyphen+underscore), path (str, absolute)
- Prints registration result

### 9. `docker/scripts/run-build.sh`

Triggers agent execution on the loaded test project via the CLI orchestrator:

```bash
cd /app
python autonomous_agent_demo.py \
  --project-dir /test-projects/repo-concierge \
  --spec \
  --max-iterations 1
```

Key flags:
- `--project-dir` — path to registered project
- `--spec` — enables spec-driven execution (Feature -> AgentSpec -> HarnessKernel)
- `--max-iterations 1` — run one agent session (prevents infinite loop in CI)

Future TODO: Also support triggering via `POST /api/agent-specs/:id/execute` once the execute endpoint is wired up (currently a placeholder at `server/routers/agent_specs.py:667`).

---

## Makefile Specification

Location: repo root (`/home/rudih/workspace/AutoBuildr/Makefile`)

### Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPOSE_FILE` | `docker/docker-compose.yml` | Compose file path |
| `COMPOSE_PROJECT` | `autobuildr-test` | Compose project name |
| `CONTAINER_NAME` | `autobuildr-test` | Container name |
| `PORT` | `8888` | Host port mapping |
| `TEST_PROJECT_SRC` | `$(HOME)/workspace/repo-concierge` | Source for local snapshot |
| `TEST_PROJECT_DEST` | `docker/test-project/repo-concierge` | Snapshot destination |

### Targets

| Target | Description | Dependencies | Actions |
|--------|-------------|--------------|---------|
| `help` | Show available targets | none | Self-documenting via `##` comments |
| `build` | Build Docker image | `_check-snapshot` | `docker compose build` |
| `up` | Start environment | `_check-key`, `_check-snapshot` | `docker compose up -d`, wait healthy, print URL |
| `load` | Register test project | `_check-running` | `docker exec` -> `load-test-project.sh` |
| `build-project` | Trigger agent execution | `_check-running` | `docker exec` -> `run-build.sh` |
| `logs` | Follow container logs | none | `docker compose logs -f` |
| `status` | Health + project report | none | Container state, health check, project list |
| `shell` | Interactive debug shell | `_check-running` | `docker exec -it ... /bin/bash` |
| `down` | Stop (preserve data) | none | `docker compose down` |
| `clean` | Full teardown | none | `docker compose down -v --rmi local --remove-orphans`, rm snapshot |
| `snapshot` | Create local snapshot | none | `rsync` from host, excluding `.git`, `__pycache__`, `*.db*`, `venv`, `claude-progress.txt` |
| `test-env` | One-command lifecycle | `snapshot`, `build`, `up`, `load`, `status` | End-to-end setup and verification |

### Internal Targets (prefixed `_`)

| Target | Purpose |
|--------|---------|
| `_check-key` | Validates `ANTHROPIC_API_KEY` in env or `docker/.env` |
| `_check-running` | Validates container is running |
| `_check-snapshot` | Auto-runs `snapshot` if dest dir missing |
| `_wait-healthy` | Polls health endpoint for 60s with progress dots |

---

## Developer Workflow

### First time setup
```bash
# Option A: Set API key in environment
export ANTHROPIC_API_KEY=sk-ant-...
make test-env

# Option B: Use .env file
cp docker/.env.example docker/.env
# Edit docker/.env with your key
make test-env

# Option C: With GitHub repo URL
export ANTHROPIC_API_KEY=sk-ant-...
REPO_URL=https://github.com/user/repo-concierge.git make test-env
```

### Daily use
```bash
make up                  # Start the environment
make load                # Register test project (idempotent)
make build-project       # Trigger agent execution
make logs                # Watch server output
make shell               # Debug inside container
make status              # Check health + projects
make down                # Stop when done
```

### After code changes
```bash
make build && make up    # Rebuild image and restart
```

### Full cleanup
```bash
make clean               # Removes containers, volumes, images, snapshot
```

---

## Cleanup Details

| Target | Containers | Volumes | Images | Snapshot | Host Files |
|--------|-----------|---------|--------|----------|------------|
| `make down` | Removed | Preserved | Preserved | Preserved | Untouched |
| `make clean` | Removed | Removed | Removed (local) | Removed | Untouched |

`make clean` executes:
1. `docker compose down -v --rmi local --remove-orphans`
2. `rm -rf docker/test-project/repo-concierge`

No host-side project files are ever modified.

---

## Health Checking

Three layers:

1. **Docker HEALTHCHECK** — runs every 10s, marks container healthy/unhealthy for `docker ps`
2. **Makefile `_wait-healthy`** — polls after `make up`, provides user feedback, dumps logs on timeout
3. **Container `wait-for-ready.sh`** — used by entrypoint for internal lifecycle commands

All hit `GET /api/health` -> `{"status": "healthy"}` (200 OK).

---

## Secrets Handling

`ANTHROPIC_API_KEY` flows through (priority order):
1. Shell environment: `export ANTHROPIC_API_KEY=...`
2. `docker/.env` file (git-ignored)
3. docker-compose environment directive (passthrough)

Safety:
- `docker/.env` is git-ignored (`.gitignore` pattern `.env` at line 129 + explicit `docker/.env`)
- `.dockerignore` excludes `docker/.env`
- Makefile never echoes the key value
- Entrypoint validates key presence at startup

---

## .gitignore Additions

```
# Docker test environment
docker/test-project/
docker/.env
```

---

## Verification Checklist

1. `make test-env` completes without errors
2. `make status` shows container healthy and `repo-concierge` in project list
3. `http://localhost:8888` loads the AutoBuildr UI in browser
4. `make shell` -> `ls /test-projects/repo-concierge/` shows project files
5. `make build-project` triggers agent execution on repo-concierge
6. `make down` stops the container cleanly
7. `make clean` removes everything (`docker ps -a`, `docker volume ls`, `docker images` all clean)
8. Without API key: `make up` fails with clear setup instructions
9. After code change: `make build` is fast (Docker layer caching works)
10. `make snapshot` creates clean copy without `.git`, `__pycache__`, `*.db` artifacts
