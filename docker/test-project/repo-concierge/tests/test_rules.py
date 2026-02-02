"""Rule detection tests."""

import re

from repo_concierge.models import Rule
from repo_concierge.rules import (
    BUILT_IN_RULES,
    RULES_BY_ID,
    get_all_rules,
    get_rule_by_id,
)


# ---- Registry Tests ----

def test_registry_has_at_least_12_rules():
    """The rule registry should contain at least 12 built-in rules."""
    assert len(BUILT_IN_RULES) >= 12


def test_shell_rules_exist():
    """SHELL-001 through SHELL-006 must all be present in the registry."""
    for i in range(1, 7):
        rule_id = f"SHELL-00{i}"
        assert rule_id in RULES_BY_ID, f"Missing rule: {rule_id}"


def test_secret_rules_exist():
    """SECRET-001 through SECRET-005 must all be present in the registry."""
    for i in range(1, 6):
        rule_id = f"SECRET-00{i}"
        assert rule_id in RULES_BY_ID, f"Missing rule: {rule_id}"


def test_policy_rules_exist():
    """POLICY-001 through POLICY-004 must all be present in the registry."""
    for i in range(1, 5):
        rule_id = f"POLICY-00{i}"
        assert rule_id in RULES_BY_ID, f"Missing rule: {rule_id}"


def test_all_rules_have_required_fields():
    """Each rule must have all required fields: id, name, pattern, severity, description, recommendation."""
    required_fields = ["id", "name", "pattern", "severity", "description", "recommendation"]
    for rule in BUILT_IN_RULES:
        for field_name in required_fields:
            value = getattr(rule, field_name)
            assert value is not None, f"Rule {rule.id} has None for field '{field_name}'"
            # id, name, severity, description, recommendation must be non-empty strings
            if field_name != "pattern":
                assert isinstance(value, str) and len(value) > 0, (
                    f"Rule {rule.id} field '{field_name}' must be a non-empty string, got: {value!r}"
                )


def test_all_rules_are_rule_instances():
    """All entries in BUILT_IN_RULES should be Rule dataclass instances."""
    for rule in BUILT_IN_RULES:
        assert isinstance(rule, Rule), f"Expected Rule instance, got {type(rule)}"


def test_get_all_rules_returns_copy():
    """get_all_rules() should return a copy, not the original list."""
    rules = get_all_rules()
    assert rules == BUILT_IN_RULES
    assert rules is not BUILT_IN_RULES


def test_get_rule_by_id_valid():
    """get_rule_by_id should return the correct rule for a valid ID."""
    rule = get_rule_by_id("SHELL-001")
    assert rule.id == "SHELL-001"
    assert rule.name == "Dangerous rm -rf"


def test_get_rule_by_id_invalid():
    """get_rule_by_id should raise KeyError for an invalid ID."""
    try:
        get_rule_by_id("NONEXISTENT-999")
        assert False, "Expected KeyError"
    except KeyError:
        pass


def test_severity_values_are_valid():
    """All rules should have a severity of HIGH, MEDIUM, or LOW."""
    valid_severities = {"HIGH", "MEDIUM", "LOW"}
    for rule in BUILT_IN_RULES:
        assert rule.severity in valid_severities, (
            f"Rule {rule.id} has invalid severity: {rule.severity}"
        )


def test_rule_ids_are_unique():
    """All rule IDs should be unique."""
    ids = [rule.id for rule in BUILT_IN_RULES]
    assert len(ids) == len(set(ids)), f"Duplicate rule IDs found: {ids}"


def test_rule_patterns_are_valid_regex():
    """All rule patterns should be valid regex (or empty for pass-through rules)."""
    for rule in BUILT_IN_RULES:
        try:
            re.compile(rule.pattern)
        except re.error as e:
            assert False, f"Rule {rule.id} has invalid regex pattern: {e}"
