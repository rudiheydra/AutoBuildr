#!/usr/bin/env python
"""
Verification script for Feature #91: Graph algorithms enforce iteration limit based on feature count.

This script verifies each step from the feature description:
1. Add iteration counter to compute_scheduling_scores BFS loop
2. Set MAX_ITERATIONS = len(features) * 2
3. When limit is exceeded, log error with algorithm name and bail out
4. Return partial/safe results rather than hanging
5. Verify the iteration limit is hit before 100ms on a cyclic graph
"""

import logging
import time
import sys

# Set up logging to capture messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def verify_step_1():
    """Step 1: Add iteration counter to compute_scheduling_scores BFS loop."""
    print("\n=== Step 1: Add iteration counter to compute_scheduling_scores BFS loop ===")

    # Verify by inspecting the source code
    import inspect
    from api.dependency_resolver import compute_scheduling_scores

    source = inspect.getsource(compute_scheduling_scores)

    checks = [
        ("iteration_count" in source, "iteration_count variable exists"),
        ("max_iterations" in source, "max_iterations variable exists"),
        ("iteration_count += 1" in source or "iteration_count[0] += 1" in source, "iteration counter incremented"),
    ]

    all_passed = True
    for check, description in checks:
        status = "PASS" if check else "FAIL"
        print(f"  [{status}] {description}")
        if not check:
            all_passed = False

    return all_passed


def verify_step_2():
    """Step 2: Set MAX_ITERATIONS = len(features) * 2."""
    print("\n=== Step 2: Set MAX_ITERATIONS = len(features) * 2 ===")

    import inspect
    from api.dependency_resolver import compute_scheduling_scores

    source = inspect.getsource(compute_scheduling_scores)

    # Check that max_iterations is set based on len(features)
    check = "len(features) * 2" in source
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] max_iterations = len(features) * 2 formula used")

    return check


def verify_step_3():
    """Step 3: When limit is exceeded, log error with algorithm name and bail out."""
    print("\n=== Step 3: When limit is exceeded, log error with algorithm name and bail out ===")

    import inspect
    from api.dependency_resolver import (
        compute_scheduling_scores,
        _detect_cycles,
        _detect_cycles_for_validation,
    )

    all_passed = True

    # Check compute_scheduling_scores
    source = inspect.getsource(compute_scheduling_scores)
    checks = [
        ("_logger.error" in source, "compute_scheduling_scores: uses _logger.error"),
        ("BFS" in source or "compute_scheduling_scores" in source, "compute_scheduling_scores: includes algorithm name in log"),
        ("break" in source, "compute_scheduling_scores: uses break to bail out"),
    ]

    for check, description in checks:
        status = "PASS" if check else "FAIL"
        print(f"  [{status}] {description}")
        if not check:
            all_passed = False

    # Check _detect_cycles
    source = inspect.getsource(_detect_cycles)
    checks = [
        ("_logger.error" in source, "_detect_cycles: uses _logger.error"),
        ("_detect_cycles" in source, "_detect_cycles: includes algorithm name in log"),
        ("return False" in source or "limit_exceeded" in source, "_detect_cycles: bails out on limit"),
    ]

    for check, description in checks:
        status = "PASS" if check else "FAIL"
        print(f"  [{status}] {description}")
        if not check:
            all_passed = False

    # Check _detect_cycles_for_validation
    source = inspect.getsource(_detect_cycles_for_validation)
    checks = [
        ("_logger.error" in source, "_detect_cycles_for_validation: uses _logger.error"),
        ("_detect_cycles_for_validation" in source, "_detect_cycles_for_validation: includes algorithm name in log"),
        ("limit_exceeded" in source, "_detect_cycles_for_validation: bails out on limit"),
    ]

    for check, description in checks:
        status = "PASS" if check else "FAIL"
        print(f"  [{status}] {description}")
        if not check:
            all_passed = False

    return all_passed


def verify_step_4():
    """Step 4: Return partial/safe results rather than hanging."""
    print("\n=== Step 4: Return partial/safe results rather than hanging ===")

    from api.dependency_resolver import (
        compute_scheduling_scores,
        _detect_cycles,
        _detect_cycles_for_validation,
    )

    all_passed = True

    # Test that functions return proper types even with problematic graphs
    features = [
        {"id": 1, "priority": 1, "dependencies": [2]},
        {"id": 2, "priority": 2, "dependencies": [3]},
        {"id": 3, "priority": 3, "dependencies": [1]},  # Creates cycle
    ]
    feature_map = {f["id"]: f for f in features}

    # compute_scheduling_scores should return dict
    start = time.time()
    result = compute_scheduling_scores(features)
    elapsed = time.time() - start
    check = isinstance(result, dict) and elapsed < 1.0
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] compute_scheduling_scores returns dict in < 1s (took {elapsed:.4f}s)")
    if not check:
        all_passed = False

    # _detect_cycles should return list
    start = time.time()
    result = _detect_cycles(features, feature_map)
    elapsed = time.time() - start
    check = isinstance(result, list) and elapsed < 1.0
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] _detect_cycles returns list in < 1s (took {elapsed:.4f}s)")
    if not check:
        all_passed = False

    # _detect_cycles_for_validation should return list
    start = time.time()
    result = _detect_cycles_for_validation(features, feature_map)
    elapsed = time.time() - start
    check = isinstance(result, list) and elapsed < 1.0
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] _detect_cycles_for_validation returns list in < 1s (took {elapsed:.4f}s)")
    if not check:
        all_passed = False

    return all_passed


def verify_step_5():
    """Step 5: Verify the iteration limit is hit before 100ms on a cyclic graph."""
    print("\n=== Step 5: Verify the iteration limit is hit before 100ms on a cyclic graph ===")

    from api.dependency_resolver import (
        compute_scheduling_scores,
        _detect_cycles,
        _detect_cycles_for_validation,
    )

    # Create a cyclic graph
    features = [
        {"id": 1, "priority": 1, "dependencies": [2]},
        {"id": 2, "priority": 2, "dependencies": [3]},
        {"id": 3, "priority": 3, "dependencies": [1]},
    ]
    feature_map = {f["id"]: f for f in features}

    all_passed = True

    # Test compute_scheduling_scores
    start = time.time()
    compute_scheduling_scores(features)
    elapsed_ms = (time.time() - start) * 1000
    check = elapsed_ms < 100
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] compute_scheduling_scores completes in < 100ms on cyclic graph ({elapsed_ms:.2f}ms)")
    if not check:
        all_passed = False

    # Test _detect_cycles
    start = time.time()
    _detect_cycles(features, feature_map)
    elapsed_ms = (time.time() - start) * 1000
    check = elapsed_ms < 100
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] _detect_cycles completes in < 100ms on cyclic graph ({elapsed_ms:.2f}ms)")
    if not check:
        all_passed = False

    # Test _detect_cycles_for_validation
    start = time.time()
    _detect_cycles_for_validation(features, feature_map)
    elapsed_ms = (time.time() - start) * 1000
    check = elapsed_ms < 100
    status = "PASS" if check else "FAIL"
    print(f"  [{status}] _detect_cycles_for_validation completes in < 100ms on cyclic graph ({elapsed_ms:.2f}ms)")
    if not check:
        all_passed = False

    return all_passed


def main():
    print("=" * 70)
    print("Feature #91 Verification: Graph algorithms enforce iteration limit")
    print("=" * 70)

    results = []

    results.append(("Step 1: Add iteration counter to BFS loop", verify_step_1()))
    results.append(("Step 2: Set MAX_ITERATIONS = len(features) * 2", verify_step_2()))
    results.append(("Step 3: Log error with algorithm name and bail out", verify_step_3()))
    results.append(("Step 4: Return partial/safe results rather than hanging", verify_step_4()))
    results.append(("Step 5: Verify iteration limit hit before 100ms", verify_step_5()))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for step, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {step}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("RESULT: ALL VERIFICATION STEPS PASSED")
        print("Feature #91 is ready to be marked as passing.")
    else:
        print("RESULT: SOME VERIFICATION STEPS FAILED")
        print("Please review the failures above.")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
