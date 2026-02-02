#!/bin/bash
set -e

# =============================================================================
# AutoBuildr Docker Entrypoint
# =============================================================================

# Validate authentication: API key OR OAuth credentials (Claude Max)
CREDS_FILE="$HOME/.claude/.credentials.json"
if [ -z "$ANTHROPIC_API_KEY" ] && [ ! -f "$CREDS_FILE" ]; then
    echo "ERROR: No authentication configured."
    echo ""
    echo "Option 1 - Claude Max (OAuth):"
    echo "  Run 'claude login' on the host, then mount credentials via docker-compose."
    echo "  The credentials file should be at: $CREDS_FILE"
    echo ""
    echo "Option 2 - API key:"
    echo "  1. Create docker/.env with: ANTHROPIC_API_KEY=sk-ant-..."
    echo "  2. Export in shell:          export ANTHROPIC_API_KEY=sk-ant-..."
    echo ""
    exit 1
elif [ -f "$CREDS_FILE" ]; then
    echo "[AUTH] Using OAuth credentials (Claude Max)"
elif [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "[AUTH] Using API key"
fi

case "${1:-serve}" in
    serve)
        echo "Starting AutoBuildr server on port 8888..."
        exec python -m uvicorn server.main:app --host 0.0.0.0 --port 8888
        ;;

    load-project)
        echo "Loading test project..."
        /docker-scripts/wait-for-ready.sh
        /docker-scripts/load-test-project.sh
        ;;

    build-project)
        echo "Building test project..."
        /docker-scripts/wait-for-ready.sh
        /docker-scripts/load-test-project.sh
        /docker-scripts/run-build.sh
        ;;

    full)
        echo "Running full lifecycle: serve + load + build..."

        # Start server in background
        python -m uvicorn server.main:app --host 0.0.0.0 --port 8888 &
        SERVER_PID=$!

        # Wait for server to be ready
        /docker-scripts/wait-for-ready.sh

        # Load test project
        /docker-scripts/load-test-project.sh

        echo ""
        echo "============================================="
        echo "  AutoBuildr is ready with test project loaded."
        echo "  UI: http://localhost:${AUTOBUILDR_PORT:-8888}"
        echo "============================================="
        echo ""

        # Keep running (wait for server process)
        wait $SERVER_PID
        ;;

    *)
        exec "$@"
        ;;
esac
