#!/usr/bin/env python
"""Test that the agent_specs router can be imported."""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

try:
    from server.routers.agent_specs import router, execute_agent_spec
    print("Import successful!")
    print(f"Router prefix: {router.prefix}")
    print(f"Execute endpoint found: {execute_agent_spec.__name__}")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
