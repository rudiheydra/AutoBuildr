#!/bin/bash
# Register the test project with AutoBuildr via REST API
set -e

PROJECT_NAME="${AUTOBUILDR_TEST_PROJECT_NAME:-repo-concierge}"
PROJECT_PATH="${AUTOBUILDR_TEST_PROJECT_PATH:-/test-projects/repo-concierge}"

echo "Registering test project: ${PROJECT_NAME} at ${PROJECT_PATH}"

# Check if already registered
STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    "http://localhost:8888/api/projects/${PROJECT_NAME}" 2>/dev/null || echo "000")

if [ "$STATUS" = "200" ]; then
    echo "Project '${PROJECT_NAME}' already registered. Skipping."
    exit 0
fi

# Register the project
# Matches ProjectCreate schema (server/schemas.py:27-31):
#   name: str (1-50 chars, ^[a-zA-Z0-9_-]+$)
#   path: str (absolute path)
RESPONSE=$(curl -sf -X POST http://localhost:8888/api/projects \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"${PROJECT_NAME}\", \"path\": \"${PROJECT_PATH}\"}")

echo "Project registered: ${RESPONSE}"
