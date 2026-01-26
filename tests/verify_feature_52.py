#!/usr/bin/env python3
"""
Feature #52 Verification Script
================================

Verifies the Feature to AgentSpec Compiler implementation by testing
each of the 10 verification steps against real Feature objects.

Usage:
    python tests/verify_feature_52.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.feature_compiler import (
    CATEGORY_TO_TASK_TYPE,
    DEFAULT_ICON,
    FeatureCompiler,
    TASK_TYPE_ICONS,
    compile_feature,
    extract_task_type_from_category,
    get_budget_for_task_type,
    get_feature_compiler,
    get_tools_for_task_type,
    reset_feature_compiler,
    slugify,
)
from api.agentspec_models import AcceptanceSpec, AgentSpec


def create_test_feature():
    """Create a mock Feature object for testing."""
    class MockFeature:
        def __init__(self):
            self.id = 52
            self.priority = 52
            self.category = "D. Workflow Completeness"
            self.name = "Feature to AgentSpec Compiler"
            self.description = "Convert a Feature database record into an AgentSpec with derived tool_policy and acceptance validators."
            self.steps = [
                "Create FeatureCompiler class with compile(feature) -> AgentSpec method",
                "Generate spec name from feature: feature-{id}-{slug}",
                "Generate display_name from feature name",
                "Set objective from feature description",
                "Determine task_type from feature category",
                "Derive tool_policy based on category conventions",
                "Create acceptance validators from feature steps",
                "Set source_feature_id for traceability",
                "Set priority from feature priority",
                "Return complete AgentSpec ready for execution",
            ]
            self.passes = False
            self.in_progress = True
            self.dependencies = [1, 2, 7, 8, 51]

    return MockFeature()


def verify_step(step_num: int, description: str, passed: bool, details: str = ""):
    """Print verification result for a step."""
    status = "PASS" if passed else "FAIL"
    print(f"  Step {step_num}: {description}")
    print(f"    Status: {status}")
    if details:
        print(f"    Details: {details}")
    return passed


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #52: Feature to AgentSpec Compiler - Verification")
    print("=" * 70)
    print()

    # Create test feature
    feature = create_test_feature()
    compiler = FeatureCompiler()

    all_passed = True
    results = []

    # Step 1: Create FeatureCompiler class with compile() method
    print("Step 1: Create FeatureCompiler class with compile(feature) -> AgentSpec method")
    try:
        spec = compiler.compile(feature)
        passed = isinstance(spec, AgentSpec) and spec is not None
        details = f"compile() returned {type(spec).__name__}"
    except Exception as e:
        passed = False
        details = f"Error: {e}"
    results.append(verify_step(1, "FeatureCompiler.compile() returns AgentSpec", passed, details))
    print()

    # Step 2: Generate spec name from feature
    print("Step 2: Generate spec name from feature: feature-{id}-{slug}")
    expected_format = f"feature-{feature.id}-"
    passed = spec.name.startswith(expected_format)
    details = f"spec.name = '{spec.name}'"
    results.append(verify_step(2, "Spec name follows feature-{id}-{slug} format", passed, details))

    # Test slugify function
    slug = slugify(feature.name)
    slug_passed = slug == "feature-to-agentspec-compiler"
    results.append(verify_step(2, "slugify() produces correct slug", slug_passed, f"slug = '{slug}'"))
    print()

    # Step 3: Generate display_name from feature name
    print("Step 3: Generate display_name from feature name")
    passed = spec.display_name == feature.name
    details = f"display_name = '{spec.display_name}'"
    results.append(verify_step(3, "display_name equals feature name", passed, details))
    print()

    # Step 4: Set objective from feature description
    print("Step 4: Set objective from feature description")
    passed = feature.description in spec.objective
    details = f"Objective contains description: {passed}"
    results.append(verify_step(4, "Objective contains feature description", passed, details))

    steps_in_objective = all(step in spec.objective for step in feature.steps)
    results.append(verify_step(4, "Objective contains all feature steps", steps_in_objective, f"All {len(feature.steps)} steps present"))
    print()

    # Step 5: Determine task_type from feature category
    print("Step 5: Determine task_type from feature category")
    task_type = extract_task_type_from_category(feature.category)
    passed = task_type == "coding"  # "Workflow" maps to coding
    details = f"Category '{feature.category}' -> task_type '{task_type}'"
    results.append(verify_step(5, "task_type derived from category", passed, details))

    # Test various categories
    test_categories = [
        ("A. Database", "coding"),
        ("B. Testing", "testing"),
        ("C. Documentation", "documentation"),
    ]
    for cat, expected in test_categories:
        result = extract_task_type_from_category(cat)
        cat_passed = result == expected
        results.append(verify_step(5, f"Category '{cat}' -> '{expected}'", cat_passed, f"Got: '{result}'"))
    print()

    # Step 6: Derive tool_policy based on category conventions
    print("Step 6: Derive tool_policy based on category conventions")
    passed = isinstance(spec.tool_policy, dict)
    results.append(verify_step(6, "tool_policy is a dictionary", passed, ""))

    has_allowed_tools = "allowed_tools" in spec.tool_policy
    results.append(verify_step(6, "tool_policy has allowed_tools", has_allowed_tools, ""))

    has_forbidden_patterns = "forbidden_patterns" in spec.tool_policy
    results.append(verify_step(6, "tool_policy has forbidden_patterns", has_forbidden_patterns, ""))

    # Check coding tools are present for coding task
    allowed = spec.tool_policy.get("allowed_tools", [])
    has_edit = "Edit" in allowed
    results.append(verify_step(6, "Coding task has Edit tool", has_edit, f"Tools: {allowed[:5]}..."))
    print()

    # Step 7: Create acceptance validators from feature steps
    print("Step 7: Create acceptance validators from feature steps")
    has_acceptance = spec.acceptance_spec is not None
    results.append(verify_step(7, "AcceptanceSpec is created", has_acceptance, ""))

    if has_acceptance:
        validators = spec.acceptance_spec.validators
        expected_count = len(feature.steps) + 1  # steps + feature_passing
        passed = len(validators) == expected_count
        details = f"Expected {expected_count} validators, got {len(validators)}"
        results.append(verify_step(7, "Correct number of validators", passed, details))

        # Check for feature_passing validator
        feature_passing = any(
            v.get("config", {}).get("name") == "feature_passing"
            for v in validators
        )
        results.append(verify_step(7, "feature_passing validator included", feature_passing, ""))

        # Check gate_mode
        gate_mode_correct = spec.acceptance_spec.gate_mode == "all_pass"
        results.append(verify_step(7, "gate_mode is all_pass", gate_mode_correct, f"gate_mode = {spec.acceptance_spec.gate_mode}"))
    print()

    # Step 8: Set source_feature_id for traceability
    print("Step 8: Set source_feature_id for traceability")
    passed = spec.source_feature_id == feature.id
    details = f"source_feature_id = {spec.source_feature_id}, feature.id = {feature.id}"
    results.append(verify_step(8, "source_feature_id links to feature", passed, details))
    print()

    # Step 9: Set priority from feature priority
    print("Step 9: Set priority from feature priority")
    passed = spec.priority == feature.priority
    details = f"spec.priority = {spec.priority}, feature.priority = {feature.priority}"
    results.append(verify_step(9, "priority matches feature priority", passed, details))
    print()

    # Step 10: Return complete AgentSpec ready for execution
    print("Step 10: Return complete AgentSpec ready for execution")
    checks = {
        "id": spec.id is not None,
        "name": spec.name is not None,
        "display_name": spec.display_name is not None,
        "objective": spec.objective is not None,
        "task_type": spec.task_type in ["coding", "testing", "documentation", "refactoring", "audit", "custom"],
        "tool_policy": isinstance(spec.tool_policy, dict),
        "max_turns": spec.max_turns > 0,
        "timeout_seconds": spec.timeout_seconds > 0,
        "acceptance_spec": spec.acceptance_spec is not None,
        "context": spec.context is not None,
    }

    all_complete = all(checks.values())
    results.append(verify_step(10, "All required fields populated", all_complete, f"Checks: {sum(checks.values())}/{len(checks)}"))

    for field, passed in checks.items():
        if not passed:
            results.append(verify_step(10, f"Field '{field}' is valid", passed, ""))
    print()

    # Summary
    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    total = len(results)
    passed_count = sum(results)
    print(f"Total checks: {total}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {total - passed_count}")
    print()

    if passed_count == total:
        print("✓ ALL VERIFICATION STEPS PASSED")
        return 0
    else:
        print("✗ SOME VERIFICATION STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
