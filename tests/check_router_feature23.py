#!/usr/bin/env python3
"""Check if agent_runs router is properly configured."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from server.routers import agent_runs_router
    print(f"Router imported successfully")
    print(f"Router prefix: {agent_runs_router.prefix}")
    print(f"Router tags: {agent_runs_router.tags}")
    print(f"Number of routes: {len(agent_runs_router.routes)}")

    for route in agent_runs_router.routes:
        print(f"  - {route.methods} {route.path}")
except Exception as e:
    print(f"Error importing router: {e}")
    import traceback
    traceback.print_exc()
