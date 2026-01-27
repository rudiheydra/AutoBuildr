#!/usr/bin/env python3
"""Debug router registration in FastAPI."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Initialize database first (needed for imports)
from api.database import create_database, set_session_maker
engine, SessionLocal = create_database(project_root)
set_session_maker(SessionLocal)

# Now import the app
from server.main import app

print("=" * 60)
print("Registered Routes")
print("=" * 60)

# List all routes
for route in app.routes:
    if hasattr(route, 'path') and hasattr(route, 'methods'):
        methods = ','.join(route.methods) if route.methods else 'N/A'
        print(f"{methods:10} {route.path}")
    elif hasattr(route, 'path'):
        print(f"{'MOUNT':10} {route.path}")

# Specifically check for agent-runs routes
print("\n" + "=" * 60)
print("Agent-Runs Routes")
print("=" * 60)

agent_run_routes = [r for r in app.routes if hasattr(r, 'path') and 'agent-run' in r.path]
if agent_run_routes:
    for route in agent_run_routes:
        methods = ','.join(route.methods) if hasattr(route, 'methods') and route.methods else 'N/A'
        print(f"{methods:10} {route.path}")
else:
    print("No agent-runs routes found!")
    print("\nChecking if router import works...")
    try:
        from server.routers.agent_runs import router
        print(f"Router imported successfully with {len(router.routes)} routes")
        for r in router.routes:
            print(f"  {','.join(r.methods):10} {r.path}")
    except Exception as e:
        print(f"Router import failed: {e}")
