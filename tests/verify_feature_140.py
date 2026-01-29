"""Verification script for Feature #140: LintCleanValidator."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.validators import LintCleanValidator, VALIDATOR_REGISTRY, get_validator
from api.agentspec_models import VALIDATOR_TYPES, create_validator
from api import LintCleanValidator as LC

# Step 1: lint_clean in VALIDATOR_TYPES
assert "lint_clean" in VALIDATOR_TYPES
print("Step 1: lint_clean in VALIDATOR_TYPES: PASS")

# Step 2: LintCleanValidator exists and is a proper validator
v = LintCleanValidator()
assert v.validator_type == "lint_clean"
print("Step 2: LintCleanValidator type is lint_clean: PASS")

# Step 3: Can create and run with linter command
result = v.evaluate({"command": "echo clean"}, {})
assert result.passed is True
print("Step 3a: Clean lint passes: PASS -", result.message)

result2 = v.evaluate({"command": "echo error 1>&2; exit 1"}, {})
assert result2.passed is False
print("Step 3b: Dirty lint fails: PASS -", result2.message)

# Step 4: Registered in registry
assert "lint_clean" in VALIDATOR_REGISTRY
resolved = get_validator("lint_clean")
assert isinstance(resolved, LintCleanValidator)
print("Step 4: In VALIDATOR_REGISTRY and get_validator resolves: PASS")

# Step 5: Works with create_validator from agentspec_models
validator_def = create_validator("lint_clean", {"command": "true"})
assert validator_def["type"] == "lint_clean"
print("Step 5: create_validator works: PASS -", validator_def)

# Step 6: Import from api package works
assert LC is LintCleanValidator
print("Step 6: Import from api package: PASS")

print()
print("ALL STEPS VERIFIED SUCCESSFULLY")
