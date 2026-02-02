# =============================================================================
# AutoBuildr Test Environment
# Multi-stage build: Node 20 (frontend) + Python 3.11 (runtime)
# =============================================================================

# =============================================================================
# Stage 1: Frontend Build
# =============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /build/ui

# Copy package files first for layer caching
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --silent

# Copy source and build
COPY ui/ ./
RUN npm run build
# Output: /build/ui/dist/

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.11-slim AS runtime

# System dependencies needed at runtime
#   git: for agent git operations on test project
#   curl: for healthcheck
#   procps: for ps command (used by security hooks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl procps rsync \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js + Claude Code CLI for SDK session executor
# Copy node from the frontend-builder stage (already has Node 20)
COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-builder /usr/local/bin/npx /usr/local/bin/npx
COPY --from=frontend-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    npm install -g @anthropic-ai/claude-code && \
    rm -rf /root/.npm

# Non-root user
RUN useradd -m -s /bin/bash autobuildr

WORKDIR /app

# Python dependencies (cached layer - only reruns on requirements.txt change)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY *.py ./
COPY api/ ./api/
COPY server/ ./server/
COPY prompts/ ./prompts/
COPY mcp_server/ ./mcp_server/

# Copy .claude directory if it exists (agent definitions, commands, skills)
COPY .claude/ ./.claude/

# Pre-built frontend from Stage 1
COPY --from=frontend-builder /build/ui/dist/ ./ui/dist/

# Test project acquisition
# Option 1: REPO_URL set -> git clone from GitHub
# Option 2: REPO_URL empty -> use local snapshot from docker/test-project/
# The snapshot is always COPYed to a staging dir; the RUN step picks the right source.
COPY docker/test-project/ /tmp/test-project-snapshot/
ARG REPO_URL=""
RUN mkdir -p /test-projects && \
    if [ -n "$REPO_URL" ]; then \
        echo "Cloning test project from: $REPO_URL" && \
        git clone "$REPO_URL" /test-projects/repo-concierge && \
        rm -rf /tmp/test-project-snapshot; \
    else \
        echo "Using local snapshot for test project" && \
        mv /tmp/test-project-snapshot/repo-concierge /test-projects/repo-concierge 2>/dev/null || \
        mkdir -p /test-projects/repo-concierge && \
        rm -rf /tmp/test-project-snapshot; \
    fi

# Entrypoint and helper scripts
COPY docker/scripts/ /docker-scripts/
RUN chmod +x /docker-scripts/*.sh

# Runtime directories
RUN mkdir -p /home/autobuildr/.autobuildr /home/autobuildr/.claude && \
    chown -R autobuildr:autobuildr /app /test-projects /home/autobuildr/.autobuildr /home/autobuildr/.claude

# Environment defaults
ENV AUTOBUILDR_ALLOW_REMOTE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8888

USER autobuildr

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD /docker-scripts/healthcheck.sh

ENTRYPOINT ["/docker-scripts/entrypoint.sh"]
CMD ["serve"]
