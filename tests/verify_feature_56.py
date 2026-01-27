#!/usr/bin/env python
"""
Feature #56 Verification Script
================================

Verify all feature steps for Task Type Detection from Description.

Feature Steps:
1. Define keyword sets for each task_type
2. coding: implement, create, build, add feature
3. testing: test, verify, check, validate
4. refactoring: refactor, clean up, optimize, simplify
5. documentation: document, readme, comments
6. audit: review, security, vulnerability
7. Score description against each keyword set
8. Return highest scoring task_type
9. Default to custom if no clear match
"""
import sys
sys.path.insert(0, '/home/rudih/workspace/AutoBuildr')

from api.task_type_detector import (
    CODING_KEYWORDS,
    TESTING_KEYWORDS,
    REFACTORING_KEYWORDS,
    DOCUMENTATION_KEYWORDS,
    AUDIT_KEYWORDS,
    TASK_TYPE_KEYWORDS,
    detect_task_type,
    detect_task_type_detailed,
    score_task_type,
    normalize_description,
)

def verify_step_1():
    """Step 1: Define keyword sets for each task_type."""
    print("\n[Step 1] Define keyword sets for each task_type")

    assert isinstance(CODING_KEYWORDS, frozenset), "CODING_KEYWORDS is not a frozenset"
    assert isinstance(TESTING_KEYWORDS, frozenset), "TESTING_KEYWORDS is not a frozenset"
    assert isinstance(REFACTORING_KEYWORDS, frozenset), "REFACTORING_KEYWORDS is not a frozenset"
    assert isinstance(DOCUMENTATION_KEYWORDS, frozenset), "DOCUMENTATION_KEYWORDS is not a frozenset"
    assert isinstance(AUDIT_KEYWORDS, frozenset), "AUDIT_KEYWORDS is not a frozenset"

    assert len(CODING_KEYWORDS) > 0, "CODING_KEYWORDS is empty"
    assert len(TESTING_KEYWORDS) > 0, "TESTING_KEYWORDS is empty"
    assert len(REFACTORING_KEYWORDS) > 0, "REFACTORING_KEYWORDS is empty"
    assert len(DOCUMENTATION_KEYWORDS) > 0, "DOCUMENTATION_KEYWORDS is empty"
    assert len(AUDIT_KEYWORDS) > 0, "AUDIT_KEYWORDS is empty"

    assert "coding" in TASK_TYPE_KEYWORDS
    assert "testing" in TASK_TYPE_KEYWORDS
    assert "refactoring" in TASK_TYPE_KEYWORDS
    assert "documentation" in TASK_TYPE_KEYWORDS
    assert "audit" in TASK_TYPE_KEYWORDS

    print("  - CODING_KEYWORDS defined with", len(CODING_KEYWORDS), "keywords")
    print("  - TESTING_KEYWORDS defined with", len(TESTING_KEYWORDS), "keywords")
    print("  - REFACTORING_KEYWORDS defined with", len(REFACTORING_KEYWORDS), "keywords")
    print("  - DOCUMENTATION_KEYWORDS defined with", len(DOCUMENTATION_KEYWORDS), "keywords")
    print("  - AUDIT_KEYWORDS defined with", len(AUDIT_KEYWORDS), "keywords")
    print("  [PASS]")
    return True

def verify_step_2():
    """Step 2: coding: implement, create, build, add feature."""
    print("\n[Step 2] coding: implement, create, build, add feature")

    coding_lower = {k.lower() for k in CODING_KEYWORDS}

    assert "implement" in coding_lower, "'implement' missing from coding keywords"
    assert "create" in coding_lower, "'create' missing from coding keywords"
    assert "build" in coding_lower, "'build' missing from coding keywords"
    assert any("feature" in k for k in coding_lower), "'feature' missing from coding keywords"

    # Verify detection works
    test_cases = [
        ("Implement user authentication", "coding"),
        ("Create a new component", "coding"),
        ("Build the dashboard", "coding"),
        ("Add a new feature", "coding"),
    ]

    for desc, expected in test_cases:
        result = detect_task_type(desc)
        assert result == expected, f"Failed for '{desc}': got {result}, expected {expected}"

    print("  - 'implement' keyword present")
    print("  - 'create' keyword present")
    print("  - 'build' keyword present")
    print("  - 'feature' keyword/phrase present")
    print("  - All test cases pass")
    print("  [PASS]")
    return True

def verify_step_3():
    """Step 3: testing: test, verify, check, validate."""
    print("\n[Step 3] testing: test, verify, check, validate")

    testing_lower = {k.lower() for k in TESTING_KEYWORDS}

    assert any("test" in k for k in testing_lower), "'test' missing from testing keywords"
    assert "verify" in testing_lower, "'verify' missing from testing keywords"
    assert "validate" in testing_lower, "'validate' missing from testing keywords"

    # Verify detection works
    test_cases = [
        ("Write tests for the module", "testing"),
        ("Verify the login flow", "testing"),
        ("Validate user input", "testing"),
    ]

    for desc, expected in test_cases:
        result = detect_task_type(desc)
        assert result == expected, f"Failed for '{desc}': got {result}, expected {expected}"

    print("  - 'test' keyword present")
    print("  - 'verify' keyword present")
    print("  - 'validate' keyword present")
    print("  - All test cases pass")
    print("  [PASS]")
    return True

def verify_step_4():
    """Step 4: refactoring: refactor, clean up, optimize, simplify."""
    print("\n[Step 4] refactoring: refactor, clean up, optimize, simplify")

    refactoring_lower = {k.lower() for k in REFACTORING_KEYWORDS}

    assert any("refactor" in k for k in refactoring_lower), "'refactor' missing"
    assert any("clean up" in k or "cleanup" in k for k in refactoring_lower), "'clean up' missing"
    assert any("optimize" in k or "optimization" in k for k in refactoring_lower), "'optimize' missing"
    assert "simplify" in refactoring_lower, "'simplify' missing"

    # Verify detection works
    test_cases = [
        ("Refactor the database layer", "refactoring"),
        ("Clean up the authentication code", "refactoring"),
        ("Optimize query performance", "refactoring"),
        ("Simplify error handling", "refactoring"),
    ]

    for desc, expected in test_cases:
        result = detect_task_type(desc)
        assert result == expected, f"Failed for '{desc}': got {result}, expected {expected}"

    print("  - 'refactor' keyword present")
    print("  - 'clean up' keyword present")
    print("  - 'optimize' keyword present")
    print("  - 'simplify' keyword present")
    print("  - All test cases pass")
    print("  [PASS]")
    return True

def verify_step_5():
    """Step 5: documentation: document, readme, comments."""
    print("\n[Step 5] documentation: document, readme, comments")

    doc_lower = {k.lower() for k in DOCUMENTATION_KEYWORDS}

    assert any("document" in k for k in doc_lower), "'document' missing"
    assert "readme" in doc_lower, "'readme' missing"
    assert any("comment" in k for k in doc_lower), "'comment' missing"

    # Verify detection works
    test_cases = [
        ("Document the API endpoints", "documentation"),
        ("Update the README", "documentation"),
        ("Add comments to the code", "documentation"),
    ]

    for desc, expected in test_cases:
        result = detect_task_type(desc)
        assert result == expected, f"Failed for '{desc}': got {result}, expected {expected}"

    print("  - 'document' keyword present")
    print("  - 'readme' keyword present")
    print("  - 'comment(s)' keyword present")
    print("  - All test cases pass")
    print("  [PASS]")
    return True

def verify_step_6():
    """Step 6: audit: review, security, vulnerability."""
    print("\n[Step 6] audit: review, security, vulnerability")

    audit_lower = {k.lower() for k in AUDIT_KEYWORDS}

    assert any("review" in k for k in audit_lower), "'review' missing"
    assert "security" in audit_lower, "'security' missing"
    assert any("vulnerabilit" in k for k in audit_lower), "'vulnerability' missing"

    # Verify detection works
    test_cases = [
        ("Review the authentication code", "audit"),
        ("Check for security issues", "audit"),
        ("Scan for vulnerabilities", "audit"),
    ]

    for desc, expected in test_cases:
        result = detect_task_type(desc)
        assert result == expected, f"Failed for '{desc}': got {result}, expected {expected}"

    print("  - 'review' keyword present")
    print("  - 'security' keyword present")
    print("  - 'vulnerability' keyword present")
    print("  - All test cases pass")
    print("  [PASS]")
    return True

def verify_step_7():
    """Step 7: Score description against each keyword set."""
    print("\n[Step 7] Score description against each keyword set")

    # Test scoring function
    description = "implement a new feature for testing"
    normalized = normalize_description(description)

    # Score against coding keywords
    coding_score, coding_matches = score_task_type(normalized, CODING_KEYWORDS)
    # Score against testing keywords
    testing_score, testing_matches = score_task_type(normalized, TESTING_KEYWORDS)

    assert coding_score >= 0, "Coding score must be non-negative"
    assert testing_score >= 0, "Testing score must be non-negative"

    # Verify detailed results include scores
    result = detect_task_type_detailed(description)
    assert "coding" in result.scores
    assert "testing" in result.scores
    assert "refactoring" in result.scores
    assert "documentation" in result.scores
    assert "audit" in result.scores

    print(f"  - Scored '{description}':")
    print(f"    coding={result.scores['coding']}, testing={result.scores['testing']}")
    print(f"    refactoring={result.scores['refactoring']}, documentation={result.scores['documentation']}")
    print(f"    audit={result.scores['audit']}")
    print("  [PASS]")
    return True

def verify_step_8():
    """Step 8: Return highest scoring task_type."""
    print("\n[Step 8] Return highest scoring task_type")

    # Test cases where one type should clearly win
    test_cases = [
        ("Implement user authentication", "coding"),
        ("Write unit tests", "testing"),
        ("Refactor the database module", "refactoring"),
        ("Document the API", "documentation"),
        ("Security audit", "audit"),
    ]

    for desc, expected in test_cases:
        result = detect_task_type_detailed(desc)
        winning_score = result.scores[expected]

        # Check that winning type has highest or tied-highest score
        max_score = max(result.scores.values())
        assert winning_score == max_score, f"'{expected}' should have highest score"

        # Check that we return the expected type
        assert result.detected_type == expected, f"Expected {expected}, got {result.detected_type}"

    print("  - Highest scoring type returned correctly for all test cases")
    print("  [PASS]")
    return True

def verify_step_9():
    """Step 9: Default to custom if no clear match."""
    print("\n[Step 9] Default to custom if no clear match")

    # Test cases that should default to custom
    test_cases = [
        "random xyz abc",
        "something unrelated",
        "",
        "   ",
    ]

    for desc in test_cases:
        result = detect_task_type(desc)
        assert result == "custom", f"Expected 'custom' for '{desc!r}', got {result}"

        result_detailed = detect_task_type_detailed(desc)
        assert result_detailed.is_default is True, f"is_default should be True for '{desc!r}'"

    print("  - Empty/whitespace descriptions return 'custom'")
    print("  - Unmatched descriptions return 'custom'")
    print("  - is_default flag is True for custom fallback")
    print("  [PASS]")
    return True

def main():
    """Run all verification steps."""
    print("="*60)
    print("Feature #56: Task Type Detection from Description")
    print("Verification Script")
    print("="*60)

    steps = [
        verify_step_1,
        verify_step_2,
        verify_step_3,
        verify_step_4,
        verify_step_5,
        verify_step_6,
        verify_step_7,
        verify_step_8,
        verify_step_9,
    ]

    passed = 0
    failed = 0

    for step_fn in steps:
        try:
            if step_fn():
                passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"Results: {passed}/{len(steps)} steps passed")
    print("="*60)

    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
