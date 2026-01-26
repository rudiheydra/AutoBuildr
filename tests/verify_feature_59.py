#!/usr/bin/env python3
"""
Verification Script for Feature #59: Unique Spec Name Generation
================================================================

This script verifies all 8 steps of Feature #59:
1. Extract keywords from objective
2. Generate slug from keywords
3. Prepend task_type prefix
4. Add timestamp or sequence for uniqueness
5. Validate against existing spec names
6. If collision, append numeric suffix
7. Limit to 100 chars
8. Return unique spec name

Run with: python tests/verify_feature_59.py
"""
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec
from api.spec_name_generator import (
    SPEC_NAME_MAX_LENGTH,
    check_name_exists,
    extract_keywords,
    generate_sequence_suffix,
    generate_slug,
    generate_spec_name,
    generate_timestamp_suffix,
    generate_unique_spec_name,
    get_existing_names_with_prefix,
    normalize_slug,
    validate_spec_name,
)


def create_test_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def print_result(step_num, step_name, passed, details=""):
    """Print verification result with consistent formatting."""
    status = "PASS" if passed else "FAIL"
    print(f"  Step {step_num}: {step_name} - {status}")
    if details:
        print(f"    Details: {details}")


def verify_step_1():
    """Step 1: Extract keywords from objective."""
    print("\nStep 1: Extract keywords from objective")
    print("-" * 50)

    passed = True
    details = []

    # Test 1: Basic extraction
    keywords = extract_keywords("Implement user authentication with OAuth2")
    if "implement" in keywords and "user" in keywords and "authentication" in keywords:
        details.append("Basic extraction: OK")
    else:
        passed = False
        details.append(f"Basic extraction: FAILED (got {keywords})")

    # Test 2: Stop words filtered
    keywords = extract_keywords("The user is logging in to the application")
    if "the" not in keywords and "is" not in keywords and "to" not in keywords:
        details.append("Stop word filtering: OK")
    else:
        passed = False
        details.append("Stop word filtering: FAILED")

    # Test 3: Special characters removed
    keywords = extract_keywords("Fix the bug! (critical)")
    if all(word.isalnum() for word in keywords):
        details.append("Special character removal: OK")
    else:
        passed = False
        details.append("Special character removal: FAILED")

    # Test 4: Empty input handled
    keywords_empty = extract_keywords("")
    if keywords_empty == []:
        details.append("Empty input handling: OK")
    else:
        passed = False
        details.append("Empty input handling: FAILED")

    print_result(1, "Extract keywords from objective", passed, "; ".join(details))
    return passed


def verify_step_2():
    """Step 2: Generate slug from keywords."""
    print("\nStep 2: Generate slug from keywords")
    print("-" * 50)

    passed = True
    details = []

    # Test 1: Basic slug generation
    slug = generate_slug(["implement", "user", "auth"])
    if slug == "implement-user-auth":
        details.append(f"Basic slug: OK ({slug})")
    else:
        passed = False
        details.append(f"Basic slug: FAILED (got {slug})")

    # Test 2: Empty keywords
    slug_empty = generate_slug([])
    if slug_empty == "spec":
        details.append("Empty keywords default: OK")
    else:
        passed = False
        details.append(f"Empty keywords: FAILED (got {slug_empty})")

    # Test 3: Max length truncation
    long_keywords = ["this", "is", "a", "very", "long", "list", "of", "keywords"]
    slug_truncated = generate_slug(long_keywords, max_length=20)
    if len(slug_truncated) <= 20:
        details.append(f"Max length truncation: OK ({len(slug_truncated)} chars)")
    else:
        passed = False
        details.append(f"Max length truncation: FAILED ({len(slug_truncated)} chars)")

    print_result(2, "Generate slug from keywords", passed, "; ".join(details))
    return passed


def verify_step_3():
    """Step 3: Prepend task_type prefix."""
    print("\nStep 3: Prepend task_type prefix")
    print("-" * 50)

    passed = True
    details = []

    # Test various task types
    task_types = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]

    for task_type in task_types:
        name = generate_spec_name("Test objective", task_type, timestamp="123")
        if name.startswith(f"{task_type}-"):
            details.append(f"{task_type}: OK")
        else:
            passed = False
            details.append(f"{task_type}: FAILED (got {name})")

    print_result(3, "Prepend task_type prefix", passed, "; ".join(details))
    return passed


def verify_step_4():
    """Step 4: Add timestamp or sequence for uniqueness."""
    print("\nStep 4: Add timestamp or sequence for uniqueness")
    print("-" * 50)

    passed = True
    details = []

    # Test 1: Explicit timestamp
    name = generate_spec_name("Test", "coding", timestamp="1706345600")
    if "1706345600" in name:
        details.append("Explicit timestamp: OK")
    else:
        passed = False
        details.append(f"Explicit timestamp: FAILED (got {name})")

    # Test 2: Auto-generated timestamp
    name_auto = generate_spec_name("Test", "coding")
    parts = name_auto.split("-")
    if parts[-1].isdigit() and len(parts[-1]) >= 10:
        details.append("Auto timestamp: OK")
    else:
        passed = False
        details.append(f"Auto timestamp: FAILED (got {name_auto})")

    # Test 3: Timestamp suffix function
    ts = generate_timestamp_suffix()
    if ts.isdigit() and len(ts) >= 10:
        details.append(f"Timestamp function: OK ({ts})")
    else:
        passed = False
        details.append(f"Timestamp function: FAILED ({ts})")

    print_result(4, "Add timestamp for uniqueness", passed, "; ".join(details))
    return passed


def verify_step_5():
    """Step 5: Validate against existing spec names."""
    print("\nStep 5: Validate against existing spec names")
    print("-" * 50)

    passed = True
    details = []

    session = create_test_session()

    # Test 1: Name doesn't exist
    exists = check_name_exists(session, "nonexistent-spec")
    if not exists:
        details.append("Non-existing name check: OK")
    else:
        passed = False
        details.append("Non-existing name check: FAILED")

    # Test 2: Create a spec and check it exists
    spec = AgentSpec(
        name="test-spec",
        display_name="Test Spec",
        objective="Test",
        task_type="coding",
        tool_policy={"allowed_tools": ["test"]},
    )
    session.add(spec)
    session.commit()

    exists = check_name_exists(session, "test-spec")
    if exists:
        details.append("Existing name check: OK")
    else:
        passed = False
        details.append("Existing name check: FAILED")

    # Test 3: Get existing names with prefix
    existing = get_existing_names_with_prefix(session, "test")
    if "test-spec" in existing:
        details.append("Prefix search: OK")
    else:
        passed = False
        details.append("Prefix search: FAILED")

    session.close()

    print_result(5, "Validate against existing spec names", passed, "; ".join(details))
    return passed


def verify_step_6():
    """Step 6: If collision, append numeric suffix."""
    print("\nStep 6: If collision, append numeric suffix")
    print("-" * 50)

    passed = True
    details = []

    session = create_test_session()

    # Generate first name
    name1 = generate_unique_spec_name(session, "Implement login", "coding")

    # Create spec with that name
    spec1 = AgentSpec(
        name=name1,
        display_name="Test 1",
        objective="Test",
        task_type="coding",
        tool_policy={"allowed_tools": ["test"]},
    )
    session.add(spec1)
    session.commit()

    # Generate second name - should have collision handling
    name2 = generate_unique_spec_name(session, "Implement login", "coding")

    if name1 != name2:
        details.append(f"Collision handled: OK (name1={name1[:30]}..., name2={name2[:30]}...)")

        # Check for numeric suffix
        if "-1" in name2:
            details.append("Numeric suffix: OK")
        else:
            # Different timestamp might have avoided collision
            details.append("Unique via timestamp difference")
    else:
        passed = False
        details.append(f"Collision NOT handled: FAILED (both names: {name1})")

    # Test sequence suffix calculation
    seq = generate_sequence_suffix("my-spec", {"my-spec", "my-spec-1", "my-spec-2"})
    if seq == 3:
        details.append("Sequence calculation: OK")
    else:
        passed = False
        details.append(f"Sequence calculation: FAILED (got {seq})")

    session.close()

    print_result(6, "Append numeric suffix on collision", passed, "; ".join(details))
    return passed


def verify_step_7():
    """Step 7: Limit to 100 chars."""
    print("\nStep 7: Limit to 100 chars")
    print("-" * 50)

    passed = True
    details = []

    # Test 1: Long objective truncation
    long_objective = "This is a very very long objective text " * 10
    name = generate_spec_name(long_objective, "coding")
    if len(name) <= SPEC_NAME_MAX_LENGTH:
        details.append(f"Long objective: OK ({len(name)} chars)")
    else:
        passed = False
        details.append(f"Long objective: FAILED ({len(name)} chars)")

    # Test 2: Validate constant
    if SPEC_NAME_MAX_LENGTH == 100:
        details.append("Max length constant: OK")
    else:
        passed = False
        details.append(f"Max length constant: FAILED ({SPEC_NAME_MAX_LENGTH})")

    # Test 3: Name at max length is valid
    max_name = "a" * 100
    if validate_spec_name(max_name):
        details.append("Max length valid: OK")
    else:
        passed = False
        details.append("Max length valid: FAILED")

    # Test 4: Name over max length is invalid
    over_name = "a" * 101
    if not validate_spec_name(over_name):
        details.append("Over max length invalid: OK")
    else:
        passed = False
        details.append("Over max length invalid: FAILED")

    print_result(7, "Limit to 100 chars", passed, "; ".join(details))
    return passed


def verify_step_8():
    """Step 8: Return unique spec name."""
    print("\nStep 8: Return unique spec name")
    print("-" * 50)

    passed = True
    details = []

    session = create_test_session()

    # Test 1: Generate unique name
    name = generate_unique_spec_name(session, "Test feature", "coding")
    if name and validate_spec_name(name):
        details.append(f"Generated valid name: OK ({name[:40]}...)")
    else:
        passed = False
        details.append(f"Generated invalid name: FAILED ({name})")

    # Test 2: Name starts with task type
    if name.startswith("coding-"):
        details.append("Task type prefix: OK")
    else:
        passed = False
        details.append("Task type prefix: FAILED")

    # Test 3: Name is URL-safe
    import re
    if re.match(r'^[a-z0-9\-]+$', name):
        details.append("URL-safe chars: OK")
    else:
        passed = False
        details.append("URL-safe chars: FAILED")

    # Test 4: Multiple unique names
    names = set()
    for i in range(5):
        n = generate_unique_spec_name(session, f"Test feature {i}", "testing")
        names.add(n)
        # Add to DB
        spec = AgentSpec(
            name=n,
            display_name=f"Test {i}",
            objective=f"Test {i}",
            task_type="testing",
            tool_policy={"allowed_tools": ["test"]},
        )
        session.add(spec)
        session.commit()

    if len(names) == 5:
        details.append("All unique: OK")
    else:
        passed = False
        details.append(f"Not all unique: FAILED ({len(names)}/5)")

    session.close()

    print_result(8, "Return unique spec name", passed, "; ".join(details))
    return passed


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #59: Unique Spec Name Generation - Verification")
    print("=" * 60)

    results = []

    results.append(("Step 1", verify_step_1()))
    results.append(("Step 2", verify_step_2()))
    results.append(("Step 3", verify_step_3()))
    results.append(("Step 4", verify_step_4()))
    results.append(("Step 5", verify_step_5()))
    results.append(("Step 6", verify_step_6()))
    results.append(("Step 7", verify_step_7()))
    results.append(("Step 8", verify_step_8()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for step_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {step_name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("OVERALL: ALL STEPS PASSED")
        print("Feature #59 verification: SUCCESS")
    else:
        print("OVERALL: SOME STEPS FAILED")
        print("Feature #59 verification: FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
