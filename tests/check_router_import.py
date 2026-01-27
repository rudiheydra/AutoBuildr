#!/usr/bin/env python3
"""Check if the agent_runs router can be imported."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from server.routers.agent_runs import router
    print("Router imported successfully")
    print("Routes:")
    for route in router.routes:
        print(f"  {route.methods} {route.path}")
except Exception as e:
    print(f"Import error: {e}")
    import traceback
    traceback.print_exc()
