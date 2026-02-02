#!/bin/bash
# Trigger agent execution on the test project via CLI orchestrator
set -e

PROJECT_PATH="${AUTOBUILDR_TEST_PROJECT_PATH:-/test-projects/repo-concierge}"
MAX_ITERATIONS="${AUTOBUILDR_MAX_ITERATIONS:-1}"
FEATURES_DB="${PROJECT_PATH}/features.db"

cd /app

# Step 1: Check if features exist. If not, run the initializer first.
FEATURE_COUNT=0
if [ -f "$FEATURES_DB" ]; then
    FEATURE_COUNT=$(python -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('${FEATURES_DB}')
    count = conn.execute('SELECT COUNT(*) FROM features').fetchone()[0]
    conn.close()
    print(count)
except Exception:
    print(0)
" 2>/dev/null)
fi

if [ "$FEATURE_COUNT" -eq 0 ] 2>/dev/null; then
    echo "No features found. Running initializer (legacy mode)..."
    echo "This may take 10-20+ minutes."
    echo ""
    python autonomous_agent_demo.py \
        --project-dir "${PROJECT_PATH}" \
        --max-iterations "${MAX_ITERATIONS}"
    echo ""
    echo "Initializer complete. Checking features..."
    FEATURE_COUNT=$(python -c "
import sqlite3
conn = sqlite3.connect('${FEATURES_DB}')
count = conn.execute('SELECT COUNT(*) FROM features').fetchone()[0]
conn.close()
print(count)
" 2>/dev/null || echo 0)
    echo "Features loaded: ${FEATURE_COUNT}"
    echo ""
fi

# Step 2: Run spec-driven execution (Feature -> AgentSpec -> HarnessKernel)
echo "Starting spec-driven agent execution on: ${PROJECT_PATH}"
echo "Features: ${FEATURE_COUNT}"
echo "Max iterations: ${MAX_ITERATIONS}"
echo "Mode: spec-driven (--spec)"
echo ""

python autonomous_agent_demo.py \
    --project-dir "${PROJECT_PATH}" \
    --spec \
    --max-iterations "${MAX_ITERATIONS}"

echo ""
echo "Agent execution complete."
