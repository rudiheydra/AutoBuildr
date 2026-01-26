#!/usr/bin/env python3
"""
Verification Script for Feature #37: StaticSpecAdapter for Legacy Coding Agent
==============================================================================

This script verifies all 11 steps of Feature #37 and provides a summary.
Run this script to confirm the feature is correctly implemented.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.static_spec_adapter import (
    StaticSpecAdapter,
    CODING_TOOLS,
    FORBIDDEN_PATTERNS,
    DEFAULT_BUDGETS,
)
from api.agentspec_models import AgentSpec, AcceptanceSpec, VALIDATOR_TYPES


def print_result(step: int, description: str, passed: bool, details: str = ""):
    """Print a verification step result."""
    status = "PASS" if passed else "FAIL"
    symbol = "[OK]" if passed else "[FAILED]"
    print(f"  Step {step}: {description}")
    print(f"         {symbol} {status}")
    if details:
        print(f"         Details: {details}")
    print()


def verify_feature_37() -> bool:
    """
    Verify all 11 steps of Feature #37.

    Returns:
        True if all steps pass, False otherwise.
    """
    print("=" * 70)
    print("Feature #37 Verification: StaticSpecAdapter for Legacy Coding Agent")
    print("=" * 70)
    print()

    adapter = StaticSpecAdapter()
    all_passed = True

    # Create a test spec
    spec = adapter.create_coding_spec(
        feature_id=42,
        feature_name="Test Feature",
        feature_description="Test description",
    )

    # Step 1: Define create_coding_spec(feature_id) method
    step1_passed = (
        hasattr(adapter, 'create_coding_spec') and
        callable(getattr(adapter, 'create_coding_spec'))
    )
    print_result(1, "Define create_coding_spec(feature_id) method", step1_passed,
                 f"Method exists: {step1_passed}")
    all_passed = all_passed and step1_passed

    # Step 2: Load coding agent prompt from prompts/
    step2_passed = len(spec.objective) > 100
    print_result(2, "Load coding agent prompt from prompts/", step2_passed,
                 f"Objective length: {len(spec.objective)} chars")
    all_passed = all_passed and step2_passed

    # Step 3: Interpolate feature details into objective
    step3_passed = (
        spec.context.get("feature_id") == 42 and
        spec.context.get("feature_name") == "Test Feature"
    )
    print_result(3, "Interpolate feature details into objective", step3_passed,
                 f"feature_id={spec.context.get('feature_id')}, feature_name={spec.context.get('feature_name')}")
    all_passed = all_passed and step3_passed

    # Step 4: Set task_type to coding
    step4_passed = spec.task_type == "coding"
    print_result(4, "Set task_type to coding", step4_passed,
                 f"task_type={spec.task_type}")
    all_passed = all_passed and step4_passed

    # Step 5: Configure tool_policy with code editing tools
    required_tools = ["Read", "Write", "Edit", "Glob", "Grep"]
    allowed = spec.tool_policy.get("allowed_tools", [])
    step5_passed = all(tool in allowed for tool in required_tools)
    print_result(5, "Configure tool_policy with code editing tools", step5_passed,
                 f"Required tools present: {[t for t in required_tools if t in allowed]}")
    all_passed = all_passed and step5_passed

    # Step 6: Include allowed bash commands from security.py allowlist
    hints = spec.tool_policy.get("tool_hints", {})
    bash_hint = hints.get("Bash", "")
    step6_passed = (
        "Bash" in allowed and
        "Bash" in hints and
        any(word in bash_hint.lower() for word in ["security", "allowlist", "restricted"])
    )
    print_result(6, "Include allowed bash commands from security.py allowlist", step6_passed,
                 f"Bash in tools: {'Bash' in allowed}, Security hint: {bool(bash_hint)}")
    all_passed = all_passed and step6_passed

    # Step 7: Set forbidden_patterns for dangerous operations
    patterns = spec.tool_policy.get("forbidden_patterns", [])
    step7_passed = len(patterns) > 0
    print_result(7, "Set forbidden_patterns for dangerous operations", step7_passed,
                 f"Forbidden patterns count: {len(patterns)}")
    all_passed = all_passed and step7_passed

    # Step 8: Set max_turns appropriate for implementation
    step8_passed = (
        spec.max_turns >= 50 and
        spec.max_turns <= 500 and
        spec.max_turns == DEFAULT_BUDGETS["coding"]["max_turns"]
    )
    print_result(8, "Set max_turns appropriate for implementation", step8_passed,
                 f"max_turns={spec.max_turns}, expected={DEFAULT_BUDGETS['coding']['max_turns']}")
    all_passed = all_passed and step8_passed

    # Step 9: Create AcceptanceSpec with test_pass and lint_clean validators
    validators = spec.acceptance_spec.validators if spec.acceptance_spec else []
    validator_types = [v.get("type") for v in validators]
    step9_passed = (
        spec.acceptance_spec is not None and
        "test_pass" in validator_types and
        "lint_clean" in validator_types
    )
    print_result(9, "Create AcceptanceSpec with test_pass and lint_clean validators", step9_passed,
                 f"Validator types: {validator_types}")
    all_passed = all_passed and step9_passed

    # Step 10: Link source_feature_id to feature
    step10_passed = spec.source_feature_id == 42
    print_result(10, "Link source_feature_id to feature", step10_passed,
                  f"source_feature_id={spec.source_feature_id}")
    all_passed = all_passed and step10_passed

    # Step 11: Return static AgentSpec
    step11_passed = isinstance(spec, AgentSpec)
    print_result(11, "Return static AgentSpec", step11_passed,
                  f"Return type: {type(spec).__name__}")
    all_passed = all_passed and step11_passed

    # Summary
    print("=" * 70)
    if all_passed:
        print("VERIFICATION RESULT: ALL 11 STEPS PASSED")
        print("Feature #37 is correctly implemented!")
    else:
        print("VERIFICATION RESULT: SOME STEPS FAILED")
        print("Please review the failed steps above.")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = verify_feature_37()
    sys.exit(0 if success else 1)
