# =============================================================================
# AutoBuildr Docker Environment
# =============================================================================
#
# Two modes:
#
#   TEST  (default)  Isolated snapshot volume, raw_messages executor.
#                    Safe for experimentation — real code is never touched.
#
#   PROD             Mounts the real repo-concierge directory,
#                    claude_sdk executor (full Claude Code CLI sessions).
#                    Changes made by agents are written to your real repo.
#
# Quick start:
#   make test-env        Full test lifecycle  (snapshot → build → up → load)
#   make prod-env        Full prod lifecycle  (build → up → load)
#   make switch-test     Restart into test mode
#   make switch-prod     Restart into prod mode
#
# Other targets:
#   make build           Build the Docker image
#   make up              Start (uses docker/.env settings)
#   make up-test         Start in test mode
#   make up-prod         Start in prod mode
#   make load            Register the test project
#   make build-project   Trigger agent execution
#   make verify-spec-path Assert spec-driven path was executed
#   make logs            Follow container logs
#   make status          Check health, mode, and project status
#   make shell           Open a shell in the container
#   make down            Stop (preserve data)
#   make clean           Stop and remove all artifacts
#
# Configuration:
#   ANTHROPIC_API_KEY    Required. Set via environment or docker/.env
#   PORT                 Host port (default: 8888)
#   PROD_PROJECT_DIR     Real repo path for prod mode
#   REPO_URL             GitHub repo URL for test project (optional)
#

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COMPOSE_FILE    := docker/docker-compose.yml
COMPOSE_PROJECT := autobuildr-test
CONTAINER_NAME  := autobuildr-test
PORT            ?= 8888

# Test project source (on host, for snapshot)
TEST_PROJECT_SRC  ?= $(HOME)/workspace/repo-concierge
TEST_PROJECT_DEST := docker/test-project/repo-concierge

# Production project directory (real repo mounted into container)
PROD_PROJECT_DIR  ?= $(HOME)/workspace/repo-concierge

# Compose command
DC := docker compose -f $(COMPOSE_FILE) -p $(COMPOSE_PROJECT)

# Mode-specific compose commands (env vars override .env file)
DC_TEST := PROJECT_DIR= AUTOBUILDR_EXECUTOR=raw_messages $(DC)
DC_PROD := PROJECT_DIR=$(PROD_PROJECT_DIR) AUTOBUILDR_EXECUTOR=claude_sdk $(DC)

# =============================================================================
# Primary Targets
# =============================================================================

.PHONY: help
help: ## Show available targets
	@echo "AutoBuildr Docker Test Environment"
	@echo "=================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

.PHONY: test-env
test-env: snapshot build up-test load status ## Full test lifecycle: snapshot, build, start (test), load
	@echo ""
	@echo "========================================="
	@echo "  TEST environment is ready"
	@echo "  UI: http://localhost:$(PORT)"
	@echo "========================================="

.PHONY: prod-env
prod-env: build up-prod load status ## Full prod lifecycle: build, start (prod), load
	@echo ""
	@echo "========================================="
	@echo "  PROD environment is ready"
	@echo "  UI: http://localhost:$(PORT)"
	@echo "  Repo: $(PROD_PROJECT_DIR)"
	@echo "========================================="

.PHONY: switch-test
switch-test: down up-test load ## Switch to TEST mode (restart with snapshot volume)

.PHONY: switch-prod
switch-prod: down up-prod load ## Switch to PROD mode (restart with real repo)

.PHONY: build
build: _check-snapshot ## Build the Docker image
	$(DC) build

.PHONY: up
up: _check-auth _check-snapshot ## Start with docker/.env settings
	$(DC) up -d
	@echo ""
	@echo "AutoBuildr starting..."
	@$(MAKE) --no-print-directory _wait-healthy
	@echo ""
	@echo "AutoBuildr running at: http://localhost:$(PORT)"

.PHONY: up-test
up-test: _check-auth _check-snapshot ## Start in TEST mode (snapshot volume, raw_messages)
	$(DC_TEST) up -d
	@echo ""
	@echo "AutoBuildr starting [TEST mode]..."
	@$(MAKE) --no-print-directory _wait-healthy
	@echo ""
	@echo "[TEST] http://localhost:$(PORT)  executor=raw_messages  volume=snapshot"

.PHONY: up-prod
up-prod: _check-auth _check-prod-dir ## Start in PROD mode (real repo, claude_sdk)
	$(DC_PROD) up -d
	@echo ""
	@echo "AutoBuildr starting [PROD mode]..."
	@$(MAKE) --no-print-directory _wait-healthy
	@echo ""
	@echo "[PROD] http://localhost:$(PORT)  executor=claude_sdk  repo=$(PROD_PROJECT_DIR)"

.PHONY: load
load: _check-running ## Register the test project
	docker exec $(CONTAINER_NAME) /docker-scripts/load-test-project.sh

.PHONY: build-project
build-project: _check-running ## Trigger agent execution on test project
	docker exec $(CONTAINER_NAME) /docker-scripts/run-build.sh

.PHONY: verify-spec-path
verify-spec-path: _check-running ## Assert spec-driven path was executed (agent_specs/runs/events non-empty)
	@docker exec $(CONTAINER_NAME) python3 /app/scripts/verify_spec_path.py

.PHONY: logs
logs: ## Follow container logs
	$(DC) logs -f

.PHONY: status
status: ## Check environment health, mode, and project status
	@echo "=== Container ==="
	@$(DC) ps 2>/dev/null || echo "  Not running"
	@echo ""
	@echo "=== Mode ==="
	@EXEC=$$(docker exec $(CONTAINER_NAME) printenv AUTOBUILDR_EXECUTOR 2>/dev/null); \
	if [ -z "$$EXEC" ]; then \
		echo "  (container not running)"; \
	elif [ "$$EXEC" = "claude_sdk" ]; then \
		echo "  PROD  (executor=claude_sdk, real repo mounted)"; \
	else \
		echo "  TEST  (executor=$$EXEC, snapshot volume)"; \
	fi
	@echo ""
	@echo "=== Health ==="
	@curl -sf http://localhost:$(PORT)/api/health 2>/dev/null \
		&& echo "  Server: HEALTHY" \
		|| echo "  Server: NOT RUNNING"
	@echo ""
	@echo "=== Projects ==="
	@curl -sf http://localhost:$(PORT)/api/projects 2>/dev/null \
		| python3 -m json.tool 2>/dev/null \
		|| echo "  (server not reachable)"

.PHONY: shell
shell: _check-running ## Open a shell in the running container
	docker exec -it $(CONTAINER_NAME) /bin/bash

.PHONY: down
down: ## Stop the environment (preserve data)
	$(DC) down

.PHONY: clean
clean: ## Stop and remove all artifacts (containers, volumes, images)
	$(DC) down -v --rmi local --remove-orphans 2>/dev/null || true
	@echo "Removing test project snapshot..."
	rm -rf $(TEST_PROJECT_DEST)
	@echo "Clean complete."

# =============================================================================
# Snapshot Management
# =============================================================================

.PHONY: snapshot
snapshot: ## Create a clean repo-concierge snapshot for Docker build
	@if [ ! -d "$(TEST_PROJECT_SRC)" ]; then \
		echo "NOTE: Source not found at $(TEST_PROJECT_SRC)"; \
		echo "Skipping snapshot (will use REPO_URL git clone if set)."; \
		mkdir -p $(TEST_PROJECT_DEST); \
		exit 0; \
	fi
	@echo "Creating snapshot of repo-concierge..."
	@mkdir -p $(TEST_PROJECT_DEST)
	rsync -a --delete \
		--exclude='.git' \
		--exclude='__pycache__' \
		--exclude='*.pyc' \
		--exclude='*.egg-info' \
		--exclude='.pytest_cache' \
		--exclude='venv' \
		--exclude='.venv' \
		--exclude='features.db' \
		--exclude='features.db-shm' \
		--exclude='features.db-wal' \
		--exclude='assistant.db' \
		--exclude='claude-progress.txt' \
		$(TEST_PROJECT_SRC)/ $(TEST_PROJECT_DEST)/
	@echo "Snapshot: $(TEST_PROJECT_DEST) ($$(du -sh $(TEST_PROJECT_DEST) | cut -f1))"

# =============================================================================
# Internal Targets
# =============================================================================

.PHONY: _check-auth
_check-auth:
	@CREDS="$$HOME/.claude/.credentials.json"; \
	HAS_KEY=false; \
	if [ -n "$$ANTHROPIC_API_KEY" ]; then HAS_KEY=true; fi; \
	if grep -q '^ANTHROPIC_API_KEY=sk-' docker/.env 2>/dev/null; then HAS_KEY=true; fi; \
	if [ "$$HAS_KEY" = "false" ] && [ ! -f "$$CREDS" ]; then \
		echo "ERROR: No authentication configured."; \
		echo ""; \
		echo "Options:"; \
		echo "  1. Claude Max: run 'claude login' on host (credentials auto-mounted)"; \
		echo "  2. API key:    export ANTHROPIC_API_KEY=sk-ant-..."; \
		echo "  3. API key:    add to docker/.env"; \
		echo ""; \
		exit 1; \
	fi

.PHONY: _check-running
_check-running:
	@docker inspect $(CONTAINER_NAME) > /dev/null 2>&1 || \
		(echo "ERROR: Container '$(CONTAINER_NAME)' is not running. Run 'make up' first." && exit 1)

.PHONY: _check-snapshot
_check-snapshot:
	@if [ ! -d "$(TEST_PROJECT_DEST)" ]; then \
		echo "Snapshot not found. Creating..."; \
		$(MAKE) --no-print-directory snapshot; \
	fi

.PHONY: _check-prod-dir
_check-prod-dir:
	@if [ ! -d "$(PROD_PROJECT_DIR)" ]; then \
		echo "ERROR: Production repo not found at $(PROD_PROJECT_DIR)"; \
		echo ""; \
		echo "Set PROD_PROJECT_DIR to your real repo path:"; \
		echo "  make up-prod PROD_PROJECT_DIR=/path/to/repo-concierge"; \
		echo ""; \
		exit 1; \
	fi

.PHONY: _wait-healthy
_wait-healthy:
	@elapsed=0; \
	while [ $$elapsed -lt 60 ]; do \
		if curl -sf http://localhost:$(PORT)/api/health > /dev/null 2>&1; then \
			echo "  Server healthy ($${elapsed}s)"; \
			exit 0; \
		fi; \
		sleep 2; \
		elapsed=$$((elapsed + 2)); \
		printf "."; \
	done; \
	echo ""; \
	echo "ERROR: Server not healthy within 60s"; \
	$(DC) logs --tail=30; \
	exit 1
