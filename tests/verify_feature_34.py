#!/usr/bin/env python
"""
Verification Script for Feature #34: forbidden_patterns Acceptance Validator
============================================================================

This script verifies all 8 steps of the feature specification:
1. Create ForbiddenPatternsValidator class
2. Extract patterns array from validator config
3. Compile patterns as regex
4. Query all tool_result events for the run
5. Check each payload against all patterns
6. If any match found, return passed = false
7. Include matched pattern and context in result
8. Return passed = true if no matches
"""
import sys
from dataclasses import dataclass, field
from typing import Any

# Add project root to path
sys.path.insert(0, "/home/rudih/workspace/AutoBuildr")

from api.validators import (
    ForbiddenPatternsValidator,
    ValidatorResult,
    Validator,
    VALIDATOR_REGISTRY,
    get_validator,
)


@dataclass
class MockAgentEvent:
    """Mock AgentEvent for testing."""
    id: int
    event_type: str
    sequence: int
    payload: Any = None
    tool_name: str | None = None


@dataclass
class MockAgentRun:
    """Mock AgentRun for testing."""
    id: str
    events: list[MockAgentEvent] = field(default_factory=list)


def print_step(step_num: int, description: str):
    """Print a step header."""
    print(f"\n{'='*70}")
    print(f"Step {step_num}: {description}")
    print(f"{'='*70}")


def print_check(passed: bool, message: str):
    """Print a check result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {message}")
    return passed


def verify_step_1():
    """Step 1: Create ForbiddenPatternsValidator class."""
    print_step(1, "Create ForbiddenPatternsValidator class")

    all_passed = True

    # Check class exists
    all_passed &= print_check(
        ForbiddenPatternsValidator is not None,
        "ForbiddenPatternsValidator class exists"
    )

    # Check inherits from Validator
    all_passed &= print_check(
        issubclass(ForbiddenPatternsValidator, Validator),
        "ForbiddenPatternsValidator inherits from Validator"
    )

    # Check has evaluate method
    validator = ForbiddenPatternsValidator()
    all_passed &= print_check(
        hasattr(validator, 'evaluate') and callable(validator.evaluate),
        "ForbiddenPatternsValidator has evaluate() method"
    )

    # Check validator_type
    all_passed &= print_check(
        validator.validator_type == "forbidden_patterns",
        f"validator_type is 'forbidden_patterns': {validator.validator_type}"
    )

    # Check registered in VALIDATOR_REGISTRY
    all_passed &= print_check(
        "forbidden_patterns" in VALIDATOR_REGISTRY,
        "Registered in VALIDATOR_REGISTRY"
    )

    # Check get_validator returns instance
    v = get_validator("forbidden_patterns")
    all_passed &= print_check(
        isinstance(v, ForbiddenPatternsValidator),
        "get_validator('forbidden_patterns') returns ForbiddenPatternsValidator"
    )

    return all_passed


def verify_step_2():
    """Step 2: Extract patterns array from validator config."""
    print_step(2, "Extract patterns array from validator config")

    all_passed = True
    validator = ForbiddenPatternsValidator()

    # Missing patterns
    result = validator.evaluate({}, {})
    all_passed &= print_check(
        result.passed is False and "missing" in result.message.lower(),
        "Returns failure for missing patterns field"
    )

    # None patterns
    result = validator.evaluate({"patterns": None}, {})
    all_passed &= print_check(
        result.passed is False and "missing" in result.message.lower(),
        "Returns failure for patterns=None"
    )

    # patterns not a list
    result = validator.evaluate({"patterns": "string"}, {})
    all_passed &= print_check(
        result.passed is False and "must be a list" in result.message,
        "Returns failure for patterns not a list"
    )

    # Empty patterns list
    result = validator.evaluate({"patterns": []}, {})
    all_passed &= print_check(
        result.passed is True and "No forbidden patterns specified" in result.message,
        "Returns success for empty patterns list"
    )

    # Valid patterns
    run = MockAgentRun(id="test-run")
    result = validator.evaluate({"patterns": ["foo", "bar"]}, {}, run=run)
    all_passed &= print_check(
        result.details.get("patterns_checked") == ["foo", "bar"],
        "Patterns extracted correctly: ['foo', 'bar']"
    )

    return all_passed


def verify_step_3():
    """Step 3: Compile patterns as regex."""
    print_step(3, "Compile patterns as regex")

    all_passed = True
    validator = ForbiddenPatternsValidator()
    run = MockAgentRun(id="test-run")

    # Invalid regex
    result = validator.evaluate({"patterns": ["[invalid"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is False and "Failed to compile" in result.message,
        "Returns failure for invalid regex"
    )

    # Valid regex
    result = validator.evaluate({"patterns": [r"rm\s+-rf"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is True,
        r"Valid regex 'rm\s+-rf' compiles successfully"
    )

    # Case sensitivity default
    run_with_events = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE")]
    )
    result = validator.evaluate({"patterns": ["drop table"]}, {}, run=run_with_events)
    all_passed &= print_check(
        result.passed is True,  # Should not match due to case
        "Case-sensitive by default (lowercase pattern doesn't match uppercase payload)"
    )

    # Case insensitive option
    result = validator.evaluate(
        {"patterns": ["drop table"], "case_sensitive": False},
        {},
        run=run_with_events
    )
    all_passed &= print_check(
        result.passed is False,  # Should match with case_sensitive=False
        "case_sensitive=False matches regardless of case"
    )

    return all_passed


def verify_step_4():
    """Step 4: Query all tool_result events for the run."""
    print_step(4, "Query all tool_result events for the run")

    all_passed = True
    validator = ForbiddenPatternsValidator()

    # Requires run instance
    result = validator.evaluate({"patterns": ["forbidden"]}, {}, run=None)
    all_passed &= print_check(
        result.passed is False and "requires an AgentRun" in result.message,
        "Returns failure when run is None"
    )

    # Only tool_result events are checked
    run = MockAgentRun(
        id="test-run",
        events=[
            MockAgentEvent(id=1, event_type="started", sequence=1, payload="forbidden"),
            MockAgentEvent(id=2, event_type="tool_call", sequence=2, payload="forbidden"),
            MockAgentEvent(id=3, event_type="completed", sequence=3, payload="forbidden"),
        ]
    )
    result = validator.evaluate({"patterns": ["forbidden"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is True and result.details.get("events_checked") == 0,
        "Only tool_result events checked (not started/tool_call/completed)"
    )

    # Multiple tool_result events
    run = MockAgentRun(
        id="test-run",
        events=[
            MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe"),
            MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="safe"),
            MockAgentEvent(id=3, event_type="tool_result", sequence=3, payload="safe"),
        ]
    )
    result = validator.evaluate({"patterns": ["forbidden"]}, {}, run=run)
    all_passed &= print_check(
        result.details.get("events_checked") == 3,
        f"All 3 tool_result events checked: events_checked={result.details.get('events_checked')}"
    )

    return all_passed


def verify_step_5():
    """Step 5: Check each payload against all patterns."""
    print_step(5, "Check each payload against all patterns")

    all_passed = True
    validator = ForbiddenPatternsValidator()

    # String payload
    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="rm -rf /")]
    )
    result = validator.evaluate({"patterns": ["rm -rf"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is False,
        "String payload 'rm -rf /' matches pattern 'rm -rf'"
    )

    # Dict payload
    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(
            id=1, event_type="tool_result", sequence=1,
            payload={"output": "rm -rf /home", "status": "ok"}
        )]
    )
    result = validator.evaluate({"patterns": ["rm -rf"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is False,
        "Dict payload with 'rm -rf' in value matches pattern"
    )

    # Nested dict payload
    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(
            id=1, event_type="tool_result", sequence=1,
            payload={"result": {"nested": {"deep": "DROP TABLE users"}}}
        )]
    )
    result = validator.evaluate({"patterns": ["DROP TABLE"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is False,
        "Nested dict payload with 'DROP TABLE' in nested value matches"
    )

    # List in dict payload
    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(
            id=1, event_type="tool_result", sequence=1,
            payload={"commands": ["ls", "cd", "rm -rf /"]}
        )]
    )
    result = validator.evaluate({"patterns": ["rm -rf"]}, {}, run=run)
    all_passed &= print_check(
        result.passed is False,
        "List in dict payload with 'rm -rf' in list matches"
    )

    # Multiple patterns all checked
    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="DROP TABLE users")]
    )
    result = validator.evaluate({"patterns": ["rm -rf", "DROP TABLE", "DELETE FROM"]}, {}, run=run)
    matches = result.details.get("matches", [])
    all_passed &= print_check(
        result.passed is False and len(matches) == 1 and matches[0]["pattern"] == "DROP TABLE",
        "Multiple patterns checked, correct pattern matched"
    )

    return all_passed


def verify_step_6():
    """Step 6: If any match found, return passed = false."""
    print_step(6, "If any match found, return passed = false")

    all_passed = True
    validator = ForbiddenPatternsValidator()

    # Single match
    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="password=secret")]
    )
    result = validator.evaluate({"patterns": [r"password\s*="]}, {}, run=run)
    all_passed &= print_check(
        result.passed is False and result.score == 0.0,
        "Single match returns passed=False, score=0.0"
    )

    # Multiple matches
    run = MockAgentRun(
        id="test-run",
        events=[
            MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="rm -rf /"),
            MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="DROP TABLE users"),
        ]
    )
    result = validator.evaluate({"patterns": ["rm -rf", "DROP TABLE"]}, {}, run=run)
    matches = result.details.get("matches", [])
    all_passed &= print_check(
        result.passed is False and len(matches) == 2,
        f"Multiple matches returns passed=False with {len(matches)} matches"
    )

    return all_passed


def verify_step_7():
    """Step 7: Include matched pattern and context in result."""
    print_step(7, "Include matched pattern and context in result")

    all_passed = True
    validator = ForbiddenPatternsValidator()

    run = MockAgentRun(
        id="test-run",
        events=[MockAgentEvent(
            id=42, event_type="tool_result", sequence=5,
            payload="Before text DROP TABLE users After text",
            tool_name="execute_sql"
        )]
    )
    result = validator.evaluate({"patterns": ["DROP TABLE"]}, {}, run=run)

    matches = result.details.get("matches", [])
    if len(matches) > 0:
        match = matches[0]

        all_passed &= print_check(
            match.get("event_id") == 42,
            f"Match includes event_id: {match.get('event_id')}"
        )

        all_passed &= print_check(
            match.get("event_sequence") == 5,
            f"Match includes event_sequence: {match.get('event_sequence')}"
        )

        all_passed &= print_check(
            match.get("tool_name") == "execute_sql",
            f"Match includes tool_name: {match.get('tool_name')}"
        )

        all_passed &= print_check(
            match.get("pattern") == "DROP TABLE",
            f"Match includes pattern: {match.get('pattern')}"
        )

        all_passed &= print_check(
            match.get("matched_text") == "DROP TABLE",
            f"Match includes matched_text: {match.get('matched_text')}"
        )

        context = match.get("context", "")
        all_passed &= print_check(
            "Before text" in context and "DROP TABLE" in context,
            f"Match includes context: '{context[:50]}...'"
        )
    else:
        all_passed &= print_check(False, "No matches found!")

    return all_passed


def verify_step_8():
    """Step 8: Return passed = true if no matches."""
    print_step(8, "Return passed = true if no matches")

    all_passed = True
    validator = ForbiddenPatternsValidator()

    # No matches
    run = MockAgentRun(
        id="test-run",
        events=[
            MockAgentEvent(id=1, event_type="tool_result", sequence=1, payload="safe content"),
            MockAgentEvent(id=2, event_type="tool_result", sequence=2, payload="more safe content"),
        ]
    )
    result = validator.evaluate({"patterns": ["forbidden", "dangerous"]}, {}, run=run)

    all_passed &= print_check(
        result.passed is True,
        "Returns passed=True when no patterns match"
    )

    all_passed &= print_check(
        result.score == 1.0,
        f"Returns score=1.0: {result.score}"
    )

    all_passed &= print_check(
        result.details.get("events_checked") == 2,
        f"Details include events_checked: {result.details.get('events_checked')}"
    )

    all_passed &= print_check(
        result.details.get("patterns_checked") == ["forbidden", "dangerous"],
        f"Details include patterns_checked: {result.details.get('patterns_checked')}"
    )

    all_passed &= print_check(
        result.validator_type == "forbidden_patterns",
        f"Result has validator_type: {result.validator_type}"
    )

    return all_passed


def main():
    """Run all verification steps."""
    print("="*70)
    print("Feature #34: forbidden_patterns Acceptance Validator - Verification")
    print("="*70)

    all_passed = True

    all_passed &= verify_step_1()
    all_passed &= verify_step_2()
    all_passed &= verify_step_3()
    all_passed &= verify_step_4()
    all_passed &= verify_step_5()
    all_passed &= verify_step_6()
    all_passed &= verify_step_7()
    all_passed &= verify_step_8()

    print("\n" + "="*70)
    if all_passed:
        print("RESULT: ALL VERIFICATION STEPS PASSED")
        print("="*70)
        return 0
    else:
        print("RESULT: SOME VERIFICATION STEPS FAILED")
        print("="*70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
