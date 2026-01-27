#!/usr/bin/env python3
"""Check OpenAPI spec for agent-runs endpoint."""
import json

with open('/tmp/openapi.json') as f:
    d = json.load(f)

paths = list(d['paths'].keys())
print("All paths with 'agent' in name:")
for p in paths:
    if 'agent' in p.lower():
        print(f"  {p}")

print("\nAll paths:")
for p in sorted(paths):
    print(f"  {p}")
