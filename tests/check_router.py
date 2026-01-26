#!/usr/bin/env python3
"""Check if router can be imported."""
import sys
sys.path.insert(0, '.')

try:
    from server.routers import agent_runs_router
    print("Router imported successfully")
    print("Prefix:", agent_runs_router.prefix)
    print("Routes:")
    for route in agent_runs_router.routes:
        print(f"  {route.methods} {route.path}")
except Exception as e:
    print(f"Error importing router: {e}")
    import traceback
    traceback.print_exc()
