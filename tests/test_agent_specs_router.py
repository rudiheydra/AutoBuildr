#!/usr/bin/env python3
"""Test script for agent_specs router."""

import sys
from pathlib import Path

# Add root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

# Check router prefix
from server.routers.agent_specs import router

print(f"Router prefix: {router.prefix}")
print(f"Router tags: {router.tags}")
print(f"Routes:")
for route in router.routes:
    print(f"  {route.methods} {route.path}")
