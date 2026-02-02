#!/bin/bash
# Wait for the AutoBuildr server to become healthy
set -e

MAX_WAIT=60
ELAPSED=0

echo "Waiting for AutoBuildr server..."
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -sf http://localhost:8888/api/health > /dev/null 2>&1; then
        echo "Server ready (${ELAPSED}s)"
        exit 0
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

echo "ERROR: Server did not become ready within ${MAX_WAIT}s"
exit 1
