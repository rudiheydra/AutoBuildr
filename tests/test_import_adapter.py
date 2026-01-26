#!/usr/bin/env python3
"""Quick test to verify StaticSpecAdapter import and usage."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import StaticSpecAdapter

print("Import successful")

adapter = StaticSpecAdapter()
spec = adapter.create_initializer_spec(project_name="TestApp", feature_count=85)

print(f"Created spec: {spec.name}")
print(f"  task_type: {spec.task_type}")
print(f"  max_turns: {spec.max_turns}")
print(f"  timeout_seconds: {spec.timeout_seconds}")
print(f"  has acceptance_spec: {spec.acceptance_spec is not None}")

# Verify acceptance spec validator
validator = next(
    v for v in spec.acceptance_spec.validators
    if v["config"].get("check_type") == "feature_count"
)
print(f"  feature_count validator expected: {validator['config']['expected_count']}")

print("\nAll checks passed!")
