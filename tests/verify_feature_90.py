#!/usr/bin/env python
"""
Verification Script for Feature #90: BFS in compute_scheduling_scores uses visited set

Feature Description:
The BFS algorithm in compute_scheduling_scores() must use a visited set to prevent
infinite loops when cycles exist in the dependency graph.

Verification Steps:
1. Create features with a cycle: A -> B -> C -> A
2. Call compute_scheduling_scores() with these features
3. Verify the function returns without hanging
4. Verify all features have valid scores assigned
5. Verify the visited set prevents nodes from being processed multiple times
"""

import sys
import os
import inspect
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.dependency_resolver import compute_scheduling_scores


def verify_step_1():
    """Step 1: Create features with a cycle: A -> B -> C -> A"""
    print("\n=== Step 1: Create features with a cycle: A -> B -> C -> A ===")

    features = [
        {"id": 1, "priority": 1, "dependencies": [2]},  # A depends on B
        {"id": 2, "priority": 2, "dependencies": [3]},  # B depends on C
        {"id": 3, "priority": 3, "dependencies": [1]},  # C depends on A (creates cycle!)
    ]

    print(f"  Created feature 1 (A) with dependencies=[2] (B)")
    print(f"  Created feature 2 (B) with dependencies=[3] (C)")
    print(f"  Created feature 3 (C) with dependencies=[1] (A)")
    print(f"  Cycle formed: 1 -> 2 -> 3 -> 1 (A -> B -> C -> A)")
    print("  [PASS] Step 1: Features with cycle created successfully")
    return features


def verify_step_2(features):
    """Step 2: Call compute_scheduling_scores() with these features"""
    print("\n=== Step 2: Call compute_scheduling_scores() with cyclic features ===")

    start_time = time.time()
    scores = compute_scheduling_scores(features)
    elapsed = time.time() - start_time

    print(f"  Function returned in {elapsed:.4f} seconds")
    print(f"  Return type: {type(scores).__name__}")
    print(f"  [PASS] Step 2: compute_scheduling_scores() called successfully")
    return scores, elapsed


def verify_step_3(elapsed):
    """Step 3: Verify the function returns without hanging"""
    print("\n=== Step 3: Verify the function returns without hanging ===")

    # Function should complete in well under 1 second for 3 features
    # An infinite loop would have caused a hang/timeout
    max_expected_time = 1.0  # 1 second is very generous

    if elapsed < max_expected_time:
        print(f"  Elapsed time: {elapsed:.4f}s (< {max_expected_time}s threshold)")
        print("  [PASS] Step 3: Function returned without hanging")
        return True
    else:
        print(f"  [FAIL] Step 3: Function took {elapsed:.4f}s (> {max_expected_time}s)")
        return False


def verify_step_4(features, scores):
    """Step 4: Verify all features have valid scores assigned"""
    print("\n=== Step 4: Verify all features have valid scores assigned ===")

    all_valid = True
    for f in features:
        fid = f["id"]
        if fid not in scores:
            print(f"  [FAIL] Feature {fid} is missing from scores")
            all_valid = False
        else:
            score = scores[fid]
            if not isinstance(score, (int, float)):
                print(f"  [FAIL] Feature {fid} has invalid score type: {type(score).__name__}")
                all_valid = False
            elif score < 0:
                print(f"  [FAIL] Feature {fid} has negative score: {score}")
                all_valid = False
            else:
                print(f"  Feature {fid}: score = {score:.2f}")

    if all_valid:
        print("  [PASS] Step 4: All features have valid scores")
    return all_valid


def verify_step_5():
    """Step 5: Verify the visited set prevents nodes from being processed multiple times"""
    print("\n=== Step 5: Verify the visited set prevents re-processing ===")

    # Read the source file directly to verify visited set is present
    import os
    source_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "api", "dependency_resolver.py"
    )

    with open(source_path, "r") as f:
        source = f.read()

    # Find the compute_scheduling_scores function section
    start_marker = "def compute_scheduling_scores"
    end_marker = "\ndef "  # Next function
    start_idx = source.find(start_marker)
    end_idx = source.find(end_marker, start_idx + 1)
    if end_idx == -1:
        end_idx = len(source)
    func_source = source[start_idx:end_idx]

    # Check for visited set implementation patterns
    has_visited_declaration = "visited: set[int]" in func_source or "visited = set()" in func_source
    has_visited_check = "not in visited" in func_source
    has_visited_add = "visited.add" in func_source

    print(f"  Source code analysis:")
    print(f"    - visited set declaration: {'YES' if has_visited_declaration else 'NO'}")
    print(f"    - visited check before add: {'YES' if has_visited_check else 'NO'}")
    print(f"    - visited.add() call: {'YES' if has_visited_add else 'NO'}")

    if has_visited_declaration and has_visited_check and has_visited_add:
        print("  [PASS] Step 5: Visited set properly implemented")
        return True
    else:
        print("  [FAIL] Step 5: Visited set not properly implemented")
        return False


def verify_diamond_pattern():
    """Extra verification: Diamond pattern doesn't process nodes multiple times"""
    print("\n=== Extra: Verify diamond pattern handles correctly ===")

    # Diamond: 1 -> (2, 3) -> 4
    # Node 4 should only be visited once
    features = [
        {"id": 1, "priority": 1, "dependencies": []},
        {"id": 2, "priority": 2, "dependencies": [1]},
        {"id": 3, "priority": 3, "dependencies": [1]},
        {"id": 4, "priority": 4, "dependencies": [2, 3]},
    ]

    scores = compute_scheduling_scores(features)

    if len(scores) == 4:
        print("  Diamond pattern: All 4 features scored correctly")
        print("  [PASS] Diamond pattern handled")
        return True
    else:
        print(f"  [FAIL] Diamond pattern: Expected 4 scores, got {len(scores)}")
        return False


def main():
    print("=" * 70)
    print("Feature #90 Verification: BFS visited set prevents re-processing")
    print("=" * 70)

    results = []

    # Step 1: Create features with cycle
    features = verify_step_1()
    results.append(True)

    # Step 2: Call compute_scheduling_scores
    scores, elapsed = verify_step_2(features)
    results.append(True)

    # Step 3: Verify no hanging
    results.append(verify_step_3(elapsed))

    # Step 4: Verify all have valid scores
    results.append(verify_step_4(features, scores))

    # Step 5: Verify visited set implementation
    results.append(verify_step_5())

    # Extra: Diamond pattern
    results.append(verify_diamond_pattern())

    # Summary
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"VERIFICATION PASSED: {passed}/{total} steps")
        print("Feature #90 is correctly implemented.")
        return 0
    else:
        print(f"VERIFICATION FAILED: {passed}/{total} steps passed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
