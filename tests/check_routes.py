#!/usr/bin/env python
"""Check registered routes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.main import app

print("Registered routes containing 'agent':")
for route in app.routes:
    if hasattr(route, 'path') and 'agent' in route.path.lower():
        methods = getattr(route, 'methods', set())
        print(f"  {methods} {route.path}")
