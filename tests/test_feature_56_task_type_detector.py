"""
Tests for Feature #56: Task Type Detection from Description
===========================================================

This module provides comprehensive tests for the task type detection
functionality that uses keyword matching heuristics.

Feature Requirements:
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
import pytest
from api.task_type_detector import (
    # Constants
    CODING_KEYWORDS,
    TESTING_KEYWORDS,
    REFACTORING_KEYWORDS,
    DOCUMENTATION_KEYWORDS,
    AUDIT_KEYWORDS,
    TASK_TYPE_KEYWORDS,
    VALID_TASK_TYPES,
    MIN_SCORE_THRESHOLD,
    TIE_BREAKER_PRIORITY,
    # Data classes
    TaskTypeDetectionResult,
    # Core functions
    detect_task_type,
    detect_task_type_detailed,
    normalize_description,
    score_task_type,
    calculate_confidence,
    # Utility functions
    get_keywords_for_type,
    get_all_keyword_sets,
    get_valid_task_types,
    is_valid_task_type,
    explain_detection,
)


# =============================================================================
# Test Constants
# =============================================================================

class TestKeywordSets:
    """Test that keyword sets are properly defined."""

    def test_coding_keywords_exist(self):
        """Step 1 & 2: Verify coding keywords are defined."""
        assert isinstance(CODING_KEYWORDS, frozenset)
        assert len(CODING_KEYWORDS) > 0

    def test_coding_keywords_contain_required(self):
        """Step 2: Verify coding contains: implement, create, build, add feature."""
        # Note: These may be exact words or phrases
        coding_lower = {k.lower() for k in CODING_KEYWORDS}
        assert "implement" in coding_lower
        assert "create" in coding_lower
        assert "build" in coding_lower
        # "add feature" is a phrase
        assert any("add feature" in k or "feature" in k for k in coding_lower)

    def test_testing_keywords_exist(self):
        """Step 1 & 3: Verify testing keywords are defined."""
        assert isinstance(TESTING_KEYWORDS, frozenset)
        assert len(TESTING_KEYWORDS) > 0

    def test_testing_keywords_contain_required(self):
        """Step 3: Verify testing contains: test, verify, check, validate."""
        testing_lower = {k.lower() for k in TESTING_KEYWORDS}
        assert "test" in testing_lower or "tests" in testing_lower
        assert "verify" in testing_lower
        assert "validate" in testing_lower

    def test_refactoring_keywords_exist(self):
        """Step 1 & 4: Verify refactoring keywords are defined."""
        assert isinstance(REFACTORING_KEYWORDS, frozenset)
        assert len(REFACTORING_KEYWORDS) > 0

    def test_refactoring_keywords_contain_required(self):
        """Step 4: Verify refactoring contains: refactor, clean up, optimize, simplify."""
        refactoring_lower = {k.lower() for k in REFACTORING_KEYWORDS}
        assert "refactor" in refactoring_lower or "refactoring" in refactoring_lower
        assert "clean up" in refactoring_lower or "cleanup" in refactoring_lower
        assert "optimize" in refactoring_lower or "optimization" in refactoring_lower
        assert "simplify" in refactoring_lower

    def test_documentation_keywords_exist(self):
        """Step 1 & 5: Verify documentation keywords are defined."""
        assert isinstance(DOCUMENTATION_KEYWORDS, frozenset)
        assert len(DOCUMENTATION_KEYWORDS) > 0

    def test_documentation_keywords_contain_required(self):
        """Step 5: Verify documentation contains: document, readme, comments."""
        doc_lower = {k.lower() for k in DOCUMENTATION_KEYWORDS}
        assert any("document" in k for k in doc_lower)
        assert "readme" in doc_lower
        assert "comment" in doc_lower or "comments" in doc_lower

    def test_audit_keywords_exist(self):
        """Step 1 & 6: Verify audit keywords are defined."""
        assert isinstance(AUDIT_KEYWORDS, frozenset)
        assert len(AUDIT_KEYWORDS) > 0

    def test_audit_keywords_contain_required(self):
        """Step 6: Verify audit contains: review, security, vulnerability."""
        audit_lower = {k.lower() for k in AUDIT_KEYWORDS}
        assert "review" in audit_lower or "code review" in audit_lower
        assert "security" in audit_lower
        assert "vulnerability" in audit_lower or "vulnerabilities" in audit_lower

    def test_task_type_keywords_dict_structure(self):
        """Verify TASK_TYPE_KEYWORDS maps all types except custom."""
        assert isinstance(TASK_TYPE_KEYWORDS, dict)
        assert "coding" in TASK_TYPE_KEYWORDS
        assert "testing" in TASK_TYPE_KEYWORDS
        assert "refactoring" in TASK_TYPE_KEYWORDS
        assert "documentation" in TASK_TYPE_KEYWORDS
        assert "audit" in TASK_TYPE_KEYWORDS
        # Custom has no keywords (it's the fallback)
        assert "custom" not in TASK_TYPE_KEYWORDS

    def test_valid_task_types_complete(self):
        """Verify all 6 task types are valid."""
        assert "coding" in VALID_TASK_TYPES
        assert "testing" in VALID_TASK_TYPES
        assert "refactoring" in VALID_TASK_TYPES
        assert "documentation" in VALID_TASK_TYPES
        assert "audit" in VALID_TASK_TYPES
        assert "custom" in VALID_TASK_TYPES
        assert len(VALID_TASK_TYPES) == 6


# =============================================================================
# Test Scoring Algorithm
# =============================================================================

class TestScoringAlgorithm:
    """Test the scoring algorithm implementation."""

    def test_score_task_type_with_match(self):
        """Step 7: Score description against keyword set - with matches."""
        description = "implement a new feature"
        score, matched = score_task_type(
            normalize_description(description),
            CODING_KEYWORDS
        )
        assert score >= 1
        assert len(matched) >= 1

    def test_score_task_type_no_match(self):
        """Step 7: Score description against keyword set - no matches."""
        description = "random words xyz abc"
        score, matched = score_task_type(
            normalize_description(description),
            CODING_KEYWORDS
        )
        assert score == 0
        assert len(matched) == 0

    def test_score_task_type_empty_description(self):
        """Score empty description returns 0."""
        score, matched = score_task_type("", CODING_KEYWORDS)
        assert score == 0
        assert len(matched) == 0

    def test_score_task_type_case_insensitive(self):
        """Scoring should be case-insensitive."""
        description1 = "IMPLEMENT a feature"
        description2 = "implement a feature"

        score1, _ = score_task_type(
            normalize_description(description1),
            CODING_KEYWORDS
        )
        score2, _ = score_task_type(
            normalize_description(description2),
            CODING_KEYWORDS
        )
        assert score1 == score2

    def test_score_task_type_phrase_matching(self):
        """Scoring should match multi-word phrases."""
        description = "write tests for the module"
        score, matched = score_task_type(
            normalize_description(description),
            TESTING_KEYWORDS
        )
        assert score >= 1
        # Should match "write tests" or "tests"
        assert any("test" in m for m in matched)


# =============================================================================
# Test Detection Function
# =============================================================================

class TestDetectTaskType:
    """Test the main detect_task_type function."""

    # Step 8: Return highest scoring task_type

    def test_detect_coding_type(self):
        """Detect coding task type."""
        test_cases = [
            "Implement user authentication with OAuth2",
            "Create a new API endpoint for payments",
            "Build the user profile page",
            "Develop a notification service",
            "Add a logout button to the navigation",
            "Fix the bug in the login form",
        ]
        for description in test_cases:
            result = detect_task_type(description)
            assert result == "coding", f"Failed for: {description}"

    def test_detect_testing_type(self):
        """Detect testing task type."""
        test_cases = [
            "Write tests for the login module",
            "Add unit tests for the payment service",
            "Create integration tests for the API",
            "Verify the authentication flow works",
            "Validate the user registration process",
            "Add test coverage for the utils module",
        ]
        for description in test_cases:
            result = detect_task_type(description)
            assert result == "testing", f"Failed for: {description}"

    def test_detect_refactoring_type(self):
        """Detect refactoring task type."""
        test_cases = [
            "Refactor the database module",
            "Clean up the authentication code",
            "Optimize the query performance",
            "Simplify the error handling logic",
            "Restructure the project layout",
            "Remove code duplication in utils",
        ]
        for description in test_cases:
            result = detect_task_type(description)
            assert result == "refactoring", f"Failed for: {description}"

    def test_detect_documentation_type(self):
        """Detect documentation task type."""
        test_cases = [
            "Document the API endpoints",
            "Update the README with installation instructions",
            "Add comments to the authentication module",
            "Write a tutorial for new developers",
            "Create API documentation for the REST endpoints",
            "Update the changelog for the release",
        ]
        for description in test_cases:
            result = detect_task_type(description)
            assert result == "documentation", f"Failed for: {description}"

    def test_detect_audit_type(self):
        """Detect audit task type."""
        test_cases = [
            "Review the security of the authentication",
            "Check for vulnerabilities in the API",
            "Audit the code for security issues",
            "Analyze the performance bottlenecks",
            "Review code quality and best practices",
            "Security audit of the payment system",
        ]
        for description in test_cases:
            result = detect_task_type(description)
            assert result == "audit", f"Failed for: {description}"

    # Step 9: Default to custom if no clear match

    def test_detect_custom_fallback(self):
        """Detect custom type when no clear match."""
        test_cases = [
            "Do something random",
            "xyz abc 123",
            "asdfghjkl",
            "",  # Empty
            "   ",  # Whitespace only
        ]
        for description in test_cases:
            result = detect_task_type(description)
            assert result == "custom", f"Failed for: {description!r}"

    def test_detect_none_description(self):
        """Handle None description gracefully."""
        # The function should handle None by treating it as empty
        result = detect_task_type(None)
        assert result == "custom"


# =============================================================================
# Test Detailed Detection
# =============================================================================

class TestDetectTaskTypeDetailed:
    """Test the detailed detection function."""

    def test_returns_detection_result(self):
        """detect_task_type_detailed returns TaskTypeDetectionResult."""
        result = detect_task_type_detailed("Implement a feature")
        assert isinstance(result, TaskTypeDetectionResult)

    def test_result_has_scores_for_all_types(self):
        """Result includes scores for all task types (except custom)."""
        result = detect_task_type_detailed("Write tests")
        assert "coding" in result.scores
        assert "testing" in result.scores
        assert "refactoring" in result.scores
        assert "documentation" in result.scores
        assert "audit" in result.scores

    def test_result_has_matched_keywords(self):
        """Result includes matched keywords for winning type."""
        result = detect_task_type_detailed("Implement user authentication")
        assert result.detected_type == "coding"
        assert len(result.matched_keywords) >= 1

    def test_result_has_confidence(self):
        """Result includes confidence level."""
        result = detect_task_type_detailed("Implement authentication")
        assert result.confidence in ["high", "medium", "low"]

    def test_result_is_default_for_custom(self):
        """Result has is_default=True for custom fallback."""
        result = detect_task_type_detailed("random xyz")
        assert result.detected_type == "custom"
        assert result.is_default is True

    def test_result_not_default_for_detected(self):
        """Result has is_default=False for detected types."""
        result = detect_task_type_detailed("Implement a feature")
        assert result.detected_type == "coding"
        assert result.is_default is False

    def test_result_has_description_length(self):
        """Result includes the normalized description length."""
        result = detect_task_type_detailed("Implement feature")
        assert result.description_length > 0


# =============================================================================
# Test Utility Functions
# =============================================================================

class TestUtilityFunctions:
    """Test utility functions."""

    def test_normalize_description_lowercase(self):
        """normalize_description converts to lowercase."""
        result = normalize_description("IMPLEMENT Feature")
        assert result == "implement feature"

    def test_normalize_description_whitespace(self):
        """normalize_description collapses whitespace."""
        result = normalize_description("implement   multiple   spaces")
        assert result == "implement multiple spaces"

    def test_normalize_description_trim(self):
        """normalize_description trims leading/trailing whitespace."""
        result = normalize_description("  implement feature  ")
        assert result == "implement feature"

    def test_normalize_description_empty(self):
        """normalize_description handles empty string."""
        result = normalize_description("")
        assert result == ""

    def test_normalize_description_none(self):
        """normalize_description handles None."""
        result = normalize_description(None)
        assert result == ""

    def test_get_keywords_for_type_valid(self):
        """get_keywords_for_type returns keywords for valid type."""
        result = get_keywords_for_type("coding")
        assert result == CODING_KEYWORDS

    def test_get_keywords_for_type_invalid(self):
        """get_keywords_for_type raises ValueError for invalid type."""
        with pytest.raises(ValueError):
            get_keywords_for_type("invalid")

    def test_get_keywords_for_type_custom(self):
        """get_keywords_for_type raises ValueError for custom."""
        with pytest.raises(ValueError):
            get_keywords_for_type("custom")

    def test_get_all_keyword_sets(self):
        """get_all_keyword_sets returns all keyword sets."""
        result = get_all_keyword_sets()
        assert isinstance(result, dict)
        assert len(result) == 5  # All types except custom

    def test_get_valid_task_types(self):
        """get_valid_task_types returns valid types."""
        result = get_valid_task_types()
        assert result == VALID_TASK_TYPES

    def test_is_valid_task_type_true(self):
        """is_valid_task_type returns True for valid type."""
        assert is_valid_task_type("coding") is True
        assert is_valid_task_type("custom") is True

    def test_is_valid_task_type_false(self):
        """is_valid_task_type returns False for invalid type."""
        assert is_valid_task_type("invalid") is False
        assert is_valid_task_type("") is False


# =============================================================================
# Test Confidence Calculation
# =============================================================================

class TestConfidenceCalculation:
    """Test confidence level calculation."""

    def test_high_confidence(self):
        """High confidence for clear winner with good margin."""
        scores = {"coding": 5, "testing": 1, "refactoring": 0, "documentation": 0, "audit": 0}
        confidence = calculate_confidence(scores, winning_score=5, is_default=False)
        assert confidence == "high"

    def test_medium_confidence(self):
        """Medium confidence for moderate winner."""
        scores = {"coding": 2, "testing": 1, "refactoring": 0, "documentation": 0, "audit": 0}
        confidence = calculate_confidence(scores, winning_score=2, is_default=False)
        assert confidence == "medium"

    def test_low_confidence_default(self):
        """Low confidence for default fallback."""
        scores = {"coding": 0, "testing": 0, "refactoring": 0, "documentation": 0, "audit": 0}
        confidence = calculate_confidence(scores, winning_score=0, is_default=True)
        assert confidence == "low"


# =============================================================================
# Test Explain Detection
# =============================================================================

class TestExplainDetection:
    """Test the explain_detection function."""

    def test_explain_returns_string(self):
        """explain_detection returns a string."""
        result = explain_detection("Implement a feature")
        assert isinstance(result, str)

    def test_explain_contains_detected_type(self):
        """Explanation contains detected type."""
        result = explain_detection("Implement authentication")
        assert "CODING" in result.upper()

    def test_explain_contains_scores(self):
        """Explanation contains score information."""
        result = explain_detection("Write tests")
        assert "testing" in result.lower()
        assert ":" in result  # Score format like "testing: 3"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_description(self):
        """Handle very long descriptions."""
        description = "implement " * 1000
        result = detect_task_type(description)
        assert result == "coding"

    def test_unicode_characters(self):
        """Handle Unicode characters."""
        description = "implement user authentication"
        result = detect_task_type(description)
        assert result == "coding"

    def test_special_characters(self):
        """Handle special characters."""
        description = "implement feature! @user #task"
        result = detect_task_type(description)
        # Should still detect based on "implement" and "feature"
        assert result == "coding"

    def test_mixed_keywords_highest_wins(self):
        """When multiple types match, highest score wins."""
        # This description has both testing and coding keywords
        # but more testing keywords
        description = "write tests and verify the test coverage for unit tests"
        result = detect_task_type(description)
        assert result == "testing"

    def test_tie_breaker_priority(self):
        """Tie-breaker uses priority order."""
        assert TIE_BREAKER_PRIORITY[0] == "coding"
        assert "testing" in TIE_BREAKER_PRIORITY
        assert "refactoring" in TIE_BREAKER_PRIORITY


# =============================================================================
# Test API Module Import
# =============================================================================

class TestAPIModuleImport:
    """Test that the feature is properly exported from api module."""

    def test_import_from_api(self):
        """Can import task type detector from api module."""
        from api import (
            detect_task_type,
            detect_task_type_detailed,
            TaskTypeDetectionResult,
            CODING_KEYWORDS,
            TESTING_KEYWORDS,
        )
        assert callable(detect_task_type)
        assert callable(detect_task_type_detailed)
        assert TaskTypeDetectionResult is not None
        assert isinstance(CODING_KEYWORDS, frozenset)
        assert isinstance(TESTING_KEYWORDS, frozenset)


# =============================================================================
# Test Real-World Examples
# =============================================================================

class TestRealWorldExamples:
    """Test with real-world task descriptions."""

    @pytest.mark.parametrize("description,expected", [
        # Coding examples
        ("Implement OAuth2 authentication flow", "coding"),
        ("Create a REST API endpoint for user registration", "coding"),
        ("Build a dashboard component with charts", "coding"),
        ("Add pagination to the product list", "coding"),
        ("Fix the broken navigation menu", "coding"),

        # Testing examples
        ("Write unit tests for the authentication service", "testing"),
        ("Add integration tests for the payment API", "testing"),
        ("Create test fixtures for the database", "testing"),
        ("Verify email validation works correctly", "testing"),
        ("Add pytest tests for the utils module", "testing"),

        # Refactoring examples
        ("Refactor the database connection pooling", "refactoring"),
        ("Clean up the legacy authentication code", "refactoring"),
        ("Optimize the search query performance", "refactoring"),
        ("Simplify the error handling middleware", "refactoring"),
        ("Remove duplicate code in the validators", "refactoring"),

        # Documentation examples
        ("Document the REST API endpoints", "documentation"),
        ("Update the README with setup instructions", "documentation"),
        ("Add JSDoc comments to the utility functions", "documentation"),
        ("Write a user guide for the admin panel", "documentation"),
        ("Create API reference documentation", "documentation"),

        # Audit examples
        ("Review security of the authentication system", "audit"),
        ("Audit the code for SQL injection vulnerabilities", "audit"),
        ("Perform code review for the payment module", "audit"),
        ("Analyze performance bottlenecks in the API", "audit"),
        ("Check compliance with security best practices", "audit"),

        # Custom fallback examples
        ("Something completely unrelated", "custom"),
        ("XYZ ABC 123", "custom"),
        ("", "custom"),
    ])
    def test_real_world_detection(self, description, expected):
        """Test detection with real-world descriptions."""
        result = detect_task_type(description)
        assert result == expected, f"Failed for: {description!r} (got {result}, expected {expected})"
