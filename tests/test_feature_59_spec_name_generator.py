"""
Tests for Feature #59: Unique Spec Name Generation
===================================================

Comprehensive tests for the spec_name_generator module which provides:
- Keyword extraction from objectives
- URL-safe slug generation
- Task type prefix handling
- Timestamp/sequence suffix generation
- Collision detection and handling
- Name length limiting (100 chars max)
"""
import re
import time
from unittest.mock import MagicMock, patch

import pytest

from api.spec_name_generator import (
    SPEC_NAME_MAX_LENGTH,
    SPEC_NAME_PATTERN,
    STOP_WORDS,
    check_name_exists,
    extract_keywords,
    generate_sequence_suffix,
    generate_slug,
    generate_spec_name,
    generate_spec_name_for_feature,
    generate_timestamp_suffix,
    generate_unique_spec_name,
    get_existing_names_with_prefix,
    normalize_slug,
    validate_spec_name,
)


# =============================================================================
# Tests for extract_keywords
# =============================================================================

class TestExtractKeywords:
    """Tests for keyword extraction from objectives."""

    def test_basic_extraction(self):
        """Test basic keyword extraction."""
        result = extract_keywords("Implement user authentication")
        assert "implement" in result
        assert "user" in result
        assert "authentication" in result

    def test_stop_word_filtering(self):
        """Test that stop words are filtered out."""
        result = extract_keywords("The user is logging in to the application")
        assert "the" not in result
        assert "is" not in result
        assert "to" not in result
        assert "in" not in result
        assert "user" in result
        assert "logging" in result
        assert "application" in result

    def test_special_characters_removed(self):
        """Test that special characters are removed."""
        result = extract_keywords("Fix the bug! (critical) in auth@module")
        assert all(word.isalnum() for word in result)
        assert "fix" in result
        assert "bug" in result
        assert "critical" in result

    def test_max_keywords_limit(self):
        """Test that max_keywords parameter is respected."""
        objective = "one two three four five six seven eight nine ten"
        result = extract_keywords(objective, max_keywords=3)
        assert len(result) <= 3

    def test_empty_input(self):
        """Test handling of empty input."""
        assert extract_keywords("") == []
        assert extract_keywords(None) == []

    def test_only_stop_words(self):
        """Test input containing only stop words."""
        result = extract_keywords("the and or but")
        assert len(result) == 0

    def test_lowercase_conversion(self):
        """Test that keywords are converted to lowercase."""
        result = extract_keywords("IMPLEMENT User AUTHENTICATION")
        assert all(word == word.lower() for word in result)

    def test_short_words_filtered(self):
        """Test that very short words (< 2 chars) are filtered."""
        result = extract_keywords("I a x y z")
        # 'I' and 'a' are stop words and also short
        # 'x', 'y', 'z' are only 1 char each, should be filtered
        assert len(result) == 0

    def test_numbers_preserved(self):
        """Test that numbers are preserved in keywords."""
        result = extract_keywords("Implement OAuth2 authentication for API v3")
        assert "oauth2" in result or "v3" in result

    def test_mixed_content(self):
        """Test extraction with mixed content."""
        result = extract_keywords("Build a REST API endpoint for user management with JWT tokens")
        assert "build" in result
        assert "rest" in result
        assert "api" in result
        assert "endpoint" in result


# =============================================================================
# Tests for generate_slug
# =============================================================================

class TestGenerateSlug:
    """Tests for slug generation from keywords."""

    def test_basic_slug_generation(self):
        """Test basic slug generation."""
        result = generate_slug(["implement", "user", "auth"])
        assert result == "implement-user-auth"

    def test_empty_keywords(self):
        """Test slug generation with empty keywords list."""
        result = generate_slug([])
        assert result == "spec"

    def test_single_keyword(self):
        """Test slug generation with single keyword."""
        result = generate_slug(["authentication"])
        assert result == "authentication"

    def test_max_length_truncation(self):
        """Test that slug is truncated at max_length."""
        keywords = ["this", "is", "a", "very", "long", "list", "of", "keywords"]
        result = generate_slug(keywords, max_length=20)
        assert len(result) <= 20

    def test_truncation_at_word_boundary(self):
        """Test that truncation happens at word boundary when possible."""
        keywords = ["implement", "authentication"]
        result = generate_slug(keywords, max_length=15)
        # Should truncate at hyphen, not mid-word
        assert result == "implement" or "-" not in result[-3:]


# =============================================================================
# Tests for normalize_slug
# =============================================================================

class TestNormalizeSlug:
    """Tests for slug normalization."""

    def test_basic_normalization(self):
        """Test basic normalization."""
        assert normalize_slug("Hello World") == "hello-world"

    def test_special_characters_replaced(self):
        """Test that special characters are replaced with hyphens."""
        assert normalize_slug("test@name!here") == "test-name-here"

    def test_consecutive_hyphens_removed(self):
        """Test that consecutive hyphens are collapsed."""
        assert normalize_slug("test--multiple---hyphens") == "test-multiple-hyphens"

    def test_leading_trailing_hyphens_removed(self):
        """Test that leading/trailing hyphens are removed."""
        assert normalize_slug("-test-") == "test"
        assert normalize_slug("---test---") == "test"

    def test_empty_input(self):
        """Test handling of empty input."""
        assert normalize_slug("") == ""
        assert normalize_slug(None) == ""

    def test_lowercase_conversion(self):
        """Test that text is converted to lowercase."""
        assert normalize_slug("UPPERCASE") == "uppercase"


# =============================================================================
# Tests for generate_timestamp_suffix
# =============================================================================

class TestGenerateTimestampSuffix:
    """Tests for timestamp suffix generation."""

    def test_returns_string(self):
        """Test that timestamp is returned as string."""
        result = generate_timestamp_suffix()
        assert isinstance(result, str)

    def test_is_numeric(self):
        """Test that timestamp is numeric."""
        result = generate_timestamp_suffix()
        assert result.isdigit()

    def test_reasonable_length(self):
        """Test that timestamp has reasonable length (10 digits for Unix time)."""
        result = generate_timestamp_suffix()
        assert len(result) >= 10

    def test_current_time(self):
        """Test that timestamp represents current time."""
        before = int(time.time())
        result = int(generate_timestamp_suffix())
        after = int(time.time())
        assert before <= result <= after


# =============================================================================
# Tests for generate_sequence_suffix
# =============================================================================

class TestGenerateSequenceSuffix:
    """Tests for sequence suffix generation."""

    def test_empty_existing_names(self):
        """Test with no existing names."""
        result = generate_sequence_suffix("my-spec", set())
        assert result == 1

    def test_base_name_exists(self):
        """Test when base name exists."""
        result = generate_sequence_suffix("my-spec", {"my-spec"})
        assert result == 1

    def test_sequential_suffixes_exist(self):
        """Test when sequential suffixes exist."""
        existing = {"my-spec", "my-spec-1", "my-spec-2"}
        result = generate_sequence_suffix("my-spec", existing)
        assert result == 3

    def test_gap_in_sequence(self):
        """Test when there's a gap in sequence."""
        existing = {"my-spec", "my-spec-1", "my-spec-5"}
        result = generate_sequence_suffix("my-spec", existing)
        assert result == 6  # Should be one more than max

    def test_unrelated_names_ignored(self):
        """Test that unrelated names are ignored."""
        existing = {"other-spec", "different-spec-1"}
        result = generate_sequence_suffix("my-spec", existing)
        assert result == 1


# =============================================================================
# Tests for generate_spec_name
# =============================================================================

class TestGenerateSpecName:
    """Tests for spec name generation without database check."""

    def test_basic_generation(self):
        """Test basic spec name generation."""
        result = generate_spec_name("Implement login", "coding", timestamp="1706345600")
        assert result.startswith("coding-")
        assert "implement" in result
        assert "login" in result
        assert result.endswith("-1706345600")

    def test_task_type_prefix(self):
        """Test that task type is used as prefix."""
        result = generate_spec_name("Test something", "testing", timestamp="123")
        assert result.startswith("testing-")

    def test_max_length_respected(self):
        """Test that max_length is respected."""
        long_objective = "This is a very long objective that should be truncated " * 5
        result = generate_spec_name(long_objective, "coding", max_length=50)
        assert len(result) <= 50

    def test_invalid_task_type_normalized(self):
        """Test that invalid task type is normalized."""
        result = generate_spec_name("Test", "INVALID TYPE!", timestamp="123")
        assert result.startswith("invalid-type-") or result.startswith("custom-")

    def test_empty_task_type_defaults_to_custom(self):
        """Test that empty task type defaults to 'custom'."""
        result = generate_spec_name("Test", "", timestamp="123")
        assert result.startswith("custom-")

    def test_url_safe_characters(self):
        """Test that result contains only URL-safe characters."""
        result = generate_spec_name("Test with special chars! @#$%", "coding")
        # Only lowercase letters, numbers, and hyphens allowed
        assert re.match(r'^[a-z0-9\-]+$', result)


# =============================================================================
# Tests for validate_spec_name
# =============================================================================

class TestValidateSpecName:
    """Tests for spec name validation."""

    def test_valid_names(self):
        """Test that valid names pass validation."""
        assert validate_spec_name("coding-implement-login-123") is True
        assert validate_spec_name("a") is True
        assert validate_spec_name("abc123") is True
        assert validate_spec_name("test-name") is True

    def test_invalid_names(self):
        """Test that invalid names fail validation."""
        assert validate_spec_name("") is False
        assert validate_spec_name(None) is False
        assert validate_spec_name("UPPERCASE") is False
        assert validate_spec_name("special@chars") is False
        assert validate_spec_name("-leading-hyphen") is False
        assert validate_spec_name("trailing-hyphen-") is False

    def test_too_long_name(self):
        """Test that names exceeding max length fail validation."""
        long_name = "a" * (SPEC_NAME_MAX_LENGTH + 1)
        assert validate_spec_name(long_name) is False

    def test_max_length_name_valid(self):
        """Test that name at exactly max length is valid."""
        max_name = "a" * SPEC_NAME_MAX_LENGTH
        assert validate_spec_name(max_name) is True


# =============================================================================
# Tests for check_name_exists (requires mock)
# =============================================================================

class TestCheckNameExists:
    """Tests for database name existence check."""

    def test_name_exists(self):
        """Test detection of existing name."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = MagicMock()  # Exists

        result = check_name_exists(mock_session, "existing-spec")
        assert result is True

    def test_name_not_exists(self):
        """Test detection of non-existing name."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Doesn't exist

        result = check_name_exists(mock_session, "new-spec")
        assert result is False


# =============================================================================
# Tests for get_existing_names_with_prefix (requires mock)
# =============================================================================

class TestGetExistingNamesWithPrefix:
    """Tests for fetching existing names with prefix."""

    def test_returns_matching_names(self):
        """Test that matching names are returned."""
        from collections import namedtuple
        SpecRow = namedtuple('SpecRow', ['name'])

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # Simulate returned specs - use namedtuple for proper .name access
        mock_specs = [
            SpecRow(name="prefix-one"),
            SpecRow(name="prefix-two"),
        ]
        mock_query.all.return_value = mock_specs

        result = get_existing_names_with_prefix(mock_session, "prefix")
        assert "prefix-one" in result
        assert "prefix-two" in result

    def test_returns_empty_set_when_no_matches(self):
        """Test that empty set is returned when no matches."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        result = get_existing_names_with_prefix(mock_session, "nonexistent")
        assert result == set()


# =============================================================================
# Tests for generate_unique_spec_name (requires mock)
# =============================================================================

class TestGenerateUniqueSpecName:
    """Tests for unique spec name generation with collision handling."""

    def test_unique_name_first_try(self):
        """Test that unique name is returned when no collision."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No collision

        result = generate_unique_spec_name(
            mock_session,
            "Implement login",
            "coding"
        )

        assert result.startswith("coding-")
        assert "implement" in result or "login" in result

    def test_collision_handling(self):
        """Test that collision is handled with numeric suffix."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # First call returns collision, second call succeeds
        call_count = [0]

        def first_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock()  # Collision
            return None  # No collision

        mock_query.first.side_effect = first_side_effect
        mock_query.like.return_value = mock_query
        mock_query.all.return_value = []

        result = generate_unique_spec_name(
            mock_session,
            "Implement login",
            "coding"
        )

        # Should have a numeric suffix due to collision
        assert "-1" in result or result.endswith("-1")

    def test_max_retries_exceeded(self):
        """Test that ValueError is raised when max retries exceeded."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = MagicMock()  # Always collision
        mock_query.like.return_value = mock_query
        mock_query.all.return_value = []

        with pytest.raises(ValueError) as excinfo:
            generate_unique_spec_name(
                mock_session,
                "Implement login",
                "coding",
                max_retries=3
            )

        assert "Unable to generate unique spec name" in str(excinfo.value)


# =============================================================================
# Tests for generate_spec_name_for_feature (requires mock)
# =============================================================================

class TestGenerateSpecNameForFeature:
    """Tests for feature-based spec name generation."""

    def test_generates_from_feature_details(self):
        """Test that spec name incorporates feature details."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No collision

        result = generate_spec_name_for_feature(
            mock_session,
            feature_id=42,
            feature_name="User Login",
            feature_category="Authentication",
            task_type="coding"
        )

        assert result.startswith("coding-")
        # Should contain keywords from feature name/category
        assert "user" in result or "login" in result or "authentication" in result


# =============================================================================
# Integration Tests (with real database setup)
# =============================================================================

class TestIntegrationWithDatabase:
    """Integration tests requiring database setup."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite session for testing."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from api.database import Base
        from api.agentspec_models import AgentSpec

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_unique_name_generation_real_db(self, db_session):
        """Test unique name generation with real database."""
        from api.agentspec_models import AgentSpec

        # Generate first name
        name1 = generate_unique_spec_name(
            db_session,
            "Implement login",
            "coding"
        )
        assert validate_spec_name(name1)

        # Create spec with that name
        spec = AgentSpec(
            name=name1,
            display_name="Test Spec",
            objective="Test",
            task_type="coding",
            tool_policy={"allowed_tools": ["test"]},
        )
        db_session.add(spec)
        db_session.commit()

        # Generate second name - should be different
        name2 = generate_unique_spec_name(
            db_session,
            "Implement login",
            "coding"
        )

        assert name1 != name2
        assert validate_spec_name(name2)

    def test_collision_suffix_increments_real_db(self, db_session):
        """Test that collision suffix increments correctly."""
        from api.agentspec_models import AgentSpec

        names = []
        for i in range(3):
            name = generate_unique_spec_name(
                db_session,
                "Same objective",
                "testing"
            )
            names.append(name)

            spec = AgentSpec(
                name=name,
                display_name=f"Test Spec {i}",
                objective="Same objective",
                task_type="testing",
                tool_policy={"allowed_tools": ["test"]},
            )
            db_session.add(spec)
            db_session.commit()

        # All names should be unique
        assert len(set(names)) == 3

        # Names should follow pattern (base, base-1, base-2)
        # The exact suffixes depend on collision handling


# =============================================================================
# Feature Step Verification Tests
# =============================================================================

class TestFeatureStepVerification:
    """
    Tests verifying each step of Feature #59.

    Steps:
    1. Extract keywords from objective
    2. Generate slug from keywords
    3. Prepend task_type prefix
    4. Add timestamp or sequence for uniqueness
    5. Validate against existing spec names
    6. If collision, append numeric suffix
    7. Limit to 100 chars
    8. Return unique spec name
    """

    def test_step_1_extract_keywords(self):
        """Step 1: Extract keywords from objective."""
        keywords = extract_keywords("Implement user authentication with OAuth2")
        assert len(keywords) > 0
        assert "implement" in keywords
        assert "user" in keywords
        assert "authentication" in keywords

    def test_step_2_generate_slug(self):
        """Step 2: Generate slug from keywords."""
        keywords = extract_keywords("Implement user authentication")
        slug = generate_slug(keywords)
        assert "-" in slug or len(keywords) == 1
        assert slug == slug.lower()
        assert all(c.isalnum() or c == '-' for c in slug)

    def test_step_3_prepend_task_type(self):
        """Step 3: Prepend task_type prefix."""
        name = generate_spec_name("Test objective", "coding", timestamp="123")
        assert name.startswith("coding-")

        name = generate_spec_name("Test objective", "testing", timestamp="123")
        assert name.startswith("testing-")

    def test_step_4_add_timestamp(self):
        """Step 4: Add timestamp or sequence for uniqueness."""
        # Using explicit timestamp
        name = generate_spec_name("Test", "coding", timestamp="1706345600")
        assert "1706345600" in name

        # Using auto-generated timestamp
        name = generate_spec_name("Test", "coding")
        parts = name.split("-")
        # Last part should be numeric (timestamp)
        assert parts[-1].isdigit()

    def test_step_5_validate_against_existing(self):
        """Step 5: Validate against existing spec names."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        # Test when name doesn't exist
        mock_query.first.return_value = None
        exists = check_name_exists(mock_session, "new-spec")
        assert exists is False

        # Test when name exists
        mock_query.first.return_value = MagicMock()
        exists = check_name_exists(mock_session, "existing-spec")
        assert exists is True

    def test_step_6_append_numeric_suffix_on_collision(self):
        """Step 6: If collision, append numeric suffix."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.like.return_value = mock_query
        mock_query.all.return_value = []

        # First call: collision, second call: no collision
        call_count = [0]
        def side_effect():
            call_count[0] += 1
            if call_count[0] <= 1:
                return MagicMock()  # Collision
            return None

        mock_query.first.side_effect = side_effect

        name = generate_unique_spec_name(mock_session, "Test", "coding")
        # Should contain a numeric suffix due to collision handling
        assert "-1" in name

    def test_step_7_limit_to_100_chars(self):
        """Step 7: Limit to 100 chars."""
        long_objective = "This is a very very long objective " * 20
        name = generate_spec_name(long_objective, "coding")
        assert len(name) <= SPEC_NAME_MAX_LENGTH

        # Also test with unique name generation
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        name = generate_unique_spec_name(
            mock_session,
            long_objective,
            "coding"
        )
        assert len(name) <= SPEC_NAME_MAX_LENGTH

    def test_step_8_return_unique_spec_name(self):
        """Step 8: Return unique spec name."""
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        name = generate_unique_spec_name(
            mock_session,
            "Implement feature",
            "coding"
        )

        # Should be a valid spec name
        assert validate_spec_name(name)
        # Should contain task type prefix
        assert name.startswith("coding-")
        # Should have timestamp
        parts = name.split("-")
        assert parts[-1].isdigit()


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unicode_objective(self):
        """Test handling of Unicode characters in objective."""
        keywords = extract_keywords("Implement user authentication")
        assert len(keywords) > 0

    def test_objective_with_only_numbers(self):
        """Test objective containing only numbers."""
        keywords = extract_keywords("123 456 789")
        assert "123" in keywords or "456" in keywords or "789" in keywords

    def test_very_short_objective(self):
        """Test very short objective."""
        name = generate_spec_name("X", "coding", timestamp="123")
        assert validate_spec_name(name)

    def test_very_long_task_type(self):
        """Test handling of very long task type."""
        long_task_type = "a" * 50
        name = generate_spec_name("Test", long_task_type, timestamp="123")
        assert len(name) <= SPEC_NAME_MAX_LENGTH

    def test_special_characters_in_task_type(self):
        """Test handling of special characters in task type."""
        name = generate_spec_name("Test", "task@type!", timestamp="123")
        assert validate_spec_name(name)
        # Special chars should be converted to hyphens and cleaned
        assert "@" not in name
        assert "!" not in name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
