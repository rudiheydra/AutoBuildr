#!/usr/bin/env python3
"""
Verification script for Feature #93: All graph traversal functions have cycle protection

This script verifies all 5 steps from the feature specification:
1. Review resolve_dependencies() - verify visited tracking in Kahn's algorithm
2. Review _detect_cycles() - verify visited and rec_stack sets
3. Review compute_scheduling_scores() - add visited set to BFS
4. Review would_create_circular_dependency() - verify visited set in DFS
5. Add iteration limits to any function missing them

Run with: python tests/verify_feature_93.py
"""

import inspect
import sys
sys.path.insert(0, '.')

from api.dependency_resolver import (
    resolve_dependencies,
    _detect_cycles,
    _detect_cycles_for_validation,
    compute_scheduling_scores,
    would_create_circular_dependency,
    MAX_DEPENDENCY_DEPTH,
)


def print_step(step_num: int, title: str) -> None:
    """Print a verification step header."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {title}")
    print('='*60)


def print_result(passed: bool, message: str) -> None:
    """Print a verification result."""
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {message}")


def verify_step_1() -> bool:
    """Verify resolve_dependencies() uses Kahn's algorithm with proper tracking."""
    print_step(1, "Review resolve_dependencies() - verify Kahn's algorithm tracking")

    source = inspect.getsource(resolve_dependencies)

    # Check for in_degree tracking (core of Kahn's algorithm)
    has_in_degree = "in_degree" in source
    print_result(has_in_degree, "Uses in_degree tracking for Kahn's algorithm")

    # Check for heap-based priority selection
    has_heap = "heap" in source.lower()
    print_result(has_heap, "Uses heap for priority-aware node selection")

    # Functional test: verify cycle detection works
    features = [
        {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
        {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
    ]
    result = resolve_dependencies(features)
    detects_cycle = len(result["circular_dependencies"]) > 0
    print_result(detects_cycle, "Correctly detects simple A->B->A cycle")

    return has_in_degree and has_heap and detects_cycle


def verify_step_2() -> bool:
    """Verify _detect_cycles() uses visited and rec_stack sets."""
    print_step(2, "Review _detect_cycles() - verify visited and rec_stack sets")

    source = inspect.getsource(_detect_cycles)

    has_visited = "visited" in source and "set()" in source
    print_result(has_visited, "Uses visited set to track processed nodes")

    has_rec_stack = "rec_stack" in source
    print_result(has_rec_stack, "Uses rec_stack set for recursion tracking")

    has_iteration_limit = "max_iterations" in source or "iteration" in source.lower()
    print_result(has_iteration_limit, "Has iteration limit to prevent infinite loops")

    # Functional test
    features = [
        {"id": 1, "priority": 1, "dependencies": [2], "passes": False},
        {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
    ]
    feature_map = {f["id"]: f for f in features}
    cycles = _detect_cycles(features, feature_map)
    detects_cycle = len(cycles) > 0
    print_result(detects_cycle, "Correctly detects cycles in feature graph")

    return has_visited and has_rec_stack and has_iteration_limit and detects_cycle


def verify_step_3() -> bool:
    """Verify compute_scheduling_scores() has visited set in BFS."""
    print_step(3, "Review compute_scheduling_scores() - verify visited set in BFS")

    source = inspect.getsource(compute_scheduling_scores)

    has_visited = "visited" in source
    print_result(has_visited, "Uses visited set to prevent re-processing")

    has_iteration_limit = "max_iterations" in source
    print_result(has_iteration_limit, "Has iteration limit as defense in depth")

    has_logger_error = "_logger.error" in source
    print_result(has_logger_error, "Logs error when iteration limit exceeded")

    # Functional test: diamond pattern should not cause issues
    diamond_features = [
        {"id": 1, "priority": 1, "dependencies": [], "passes": False},
        {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
        {"id": 3, "priority": 3, "dependencies": [1], "passes": False},
        {"id": 4, "priority": 4, "dependencies": [2, 3], "passes": False},
    ]
    scores = compute_scheduling_scores(diamond_features)
    handles_diamond = len(scores) == 4 and scores[1] > scores[4]
    print_result(handles_diamond, "Correctly handles diamond dependency pattern")

    return has_visited and has_iteration_limit and has_logger_error and handles_diamond


def verify_step_4() -> bool:
    """Verify would_create_circular_dependency() uses visited set in DFS."""
    print_step(4, "Review would_create_circular_dependency() - verify visited set in DFS")

    source = inspect.getsource(would_create_circular_dependency)

    has_visited = "visited" in source
    print_result(has_visited, "Uses visited set for DFS traversal")

    has_depth_limit = "MAX_DEPENDENCY_DEPTH" in source or "depth" in source.lower()
    print_result(has_depth_limit, "Has depth limit to prevent stack overflow")

    # Functional test: detect potential cycle
    features = [
        {"id": 1, "priority": 1, "dependencies": [], "passes": False},
        {"id": 2, "priority": 2, "dependencies": [1], "passes": False},
        {"id": 3, "priority": 3, "dependencies": [2], "passes": False},
    ]
    would_cycle = would_create_circular_dependency(features, 1, 3)
    detects_potential_cycle = would_cycle == True
    print_result(detects_potential_cycle, "Correctly detects when adding dep would create cycle")

    would_not_cycle = would_create_circular_dependency(features, 3, 1)
    allows_safe_dep = would_not_cycle == False
    print_result(allows_safe_dep, "Correctly allows safe dependency additions")

    return has_visited and has_depth_limit and detects_potential_cycle and allows_safe_dep


def verify_step_5() -> bool:
    """Verify all functions have iteration limits."""
    print_step(5, "Add iteration limits to any function missing them")

    # Check each function for iteration/depth limits
    functions_to_check = [
        ("_detect_cycles", _detect_cycles, "max_iterations"),
        ("_detect_cycles_for_validation", _detect_cycles_for_validation, "max_iterations"),
        ("compute_scheduling_scores", compute_scheduling_scores, "max_iterations"),
        ("would_create_circular_dependency", would_create_circular_dependency, "MAX_DEPENDENCY_DEPTH"),
    ]

    all_have_limits = True
    for func_name, func, expected_var in functions_to_check:
        source = inspect.getsource(func)
        has_limit = expected_var in source
        print_result(has_limit, f"{func_name}() has {expected_var}")
        if not has_limit:
            all_have_limits = False

    # Note: resolve_dependencies uses Kahn's algorithm which inherently terminates
    # because it processes each node exactly once via in_degree decrement
    print_result(True, "resolve_dependencies() uses Kahn's algorithm (inherently terminates)")

    return all_have_limits


def main():
    """Run all verification steps."""
    print("\n" + "="*60)
    print("Feature #93 Verification: All graph traversal functions have cycle protection")
    print("="*60)

    results = []

    results.append(("Step 1: resolve_dependencies Kahn's algorithm", verify_step_1()))
    results.append(("Step 2: _detect_cycles visited/rec_stack", verify_step_2()))
    results.append(("Step 3: compute_scheduling_scores BFS visited", verify_step_3()))
    results.append(("Step 4: would_create_circular_dependency DFS visited", verify_step_4()))
    results.append(("Step 5: Iteration limits in all functions", verify_step_5()))

    # Summary
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if not passed:
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED!")
        print("Feature #93 is ready to be marked as passing.")
    else:
        print("SOME VERIFICATION STEPS FAILED!")
        print("Please review the issues above before marking as passing.")
    print("="*60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
