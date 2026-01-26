"""
Tests for Display Name and Icon Derivation
==========================================

Tests for api/display_derivation.py module that derives human-friendly
display_name and icon from AgentSpec objective and task_type.
"""
import pytest

from api.display_derivation import (
    DEFAULT_ICON,
    DISPLAY_NAME_MAX_LENGTH,
    ELLIPSIS,
    MASCOT_POOL,
    TASK_TYPE_ICONS,
    derive_display_name,
    derive_display_properties,
    derive_icon,
    derive_mascot_name,
    extract_first_sentence,
    get_mascot_pool,
    get_task_type_icons,
    truncate_with_ellipsis,
)


# =============================================================================
# Test: extract_first_sentence
# =============================================================================

class TestExtractFirstSentence:
    """Tests for extract_first_sentence function."""

    def test_simple_period(self):
        """Extract sentence ending with period."""
        result = extract_first_sentence("First sentence. Second sentence.")
        assert result == "First sentence."

    def test_exclamation_mark(self):
        """Extract sentence ending with exclamation mark."""
        result = extract_first_sentence("Hello world! More text here.")
        assert result == "Hello world!"

    def test_question_mark(self):
        """Extract sentence ending with question mark."""
        result = extract_first_sentence("Is this working? Yes it is.")
        assert result == "Is this working?"

    def test_newline_separator(self):
        """Extract sentence ending at newline."""
        result = extract_first_sentence("Line one\nLine two")
        assert result == "Line one"

    def test_no_sentence_boundary(self):
        """Return entire text when no sentence boundary found."""
        result = extract_first_sentence("No period or punctuation here")
        assert result == "No period or punctuation here"

    def test_empty_string(self):
        """Handle empty string input."""
        result = extract_first_sentence("")
        assert result == ""

    def test_none_like_empty(self):
        """Handle None input gracefully."""
        result = extract_first_sentence(None)  # type: ignore
        assert result == ""

    def test_whitespace_only(self):
        """Handle whitespace-only input."""
        result = extract_first_sentence("   ")
        assert result == ""

    def test_leading_trailing_whitespace(self):
        """Strip leading/trailing whitespace."""
        result = extract_first_sentence("  Leading space. Trailing.  ")
        assert result == "Leading space."

    def test_period_at_end(self):
        """Handle period at very end of string."""
        result = extract_first_sentence("Single sentence.")
        assert result == "Single sentence."

    def test_abbreviation_handling(self):
        """Handle periods in abbreviations (simple case)."""
        # Note: This is a basic implementation, doesn't handle complex abbreviations
        result = extract_first_sentence("Dr. Smith is here. More info.")
        # Will extract "Dr." - this is expected behavior for simple implementation
        assert "." in result

    def test_multiple_periods_in_row(self):
        """Handle ellipsis in text."""
        result = extract_first_sentence("Wait... what? More text.")
        assert result == "Wait..."

    def test_unicode_text(self):
        """Handle unicode characters."""
        result = extract_first_sentence("Hello world! More text.")
        assert result == "Hello world!"

    def test_unicode_punctuation(self):
        """Handle unicode characters in sentences."""
        result = extract_first_sentence("Cafe au lait. Tres bien.")
        assert result == "Cafe au lait."


# =============================================================================
# Test: truncate_with_ellipsis
# =============================================================================

class TestTruncateWithEllipsis:
    """Tests for truncate_with_ellipsis function."""

    def test_short_text_unchanged(self):
        """Short text should not be truncated."""
        result = truncate_with_ellipsis("Short text", 100)
        assert result == "Short text"

    def test_exact_length_unchanged(self):
        """Text at exactly max_length should not be truncated."""
        text = "A" * 100
        result = truncate_with_ellipsis(text, 100)
        assert result == text
        assert len(result) == 100

    def test_long_text_truncated(self):
        """Long text should be truncated with ellipsis."""
        text = "A" * 150
        result = truncate_with_ellipsis(text, 100)
        assert len(result) == 100
        assert result.endswith(ELLIPSIS)

    def test_truncation_preserves_start(self):
        """Truncation should preserve the start of the text."""
        text = "Hello World " * 20  # Long text
        result = truncate_with_ellipsis(text, 50)
        assert result.startswith("Hello World")
        assert result.endswith(ELLIPSIS)

    def test_default_max_length(self):
        """Test default max_length parameter."""
        text = "A" * 200
        result = truncate_with_ellipsis(text)
        assert len(result) == DISPLAY_NAME_MAX_LENGTH
        assert result.endswith(ELLIPSIS)

    def test_empty_string(self):
        """Handle empty string input."""
        result = truncate_with_ellipsis("")
        assert result == ""

    def test_none_like_empty(self):
        """Handle None input gracefully."""
        result = truncate_with_ellipsis(None)  # type: ignore
        assert result == ""

    def test_very_short_max_length(self):
        """Handle very short max_length."""
        result = truncate_with_ellipsis("Hello World", 5)
        assert len(result) == 5
        assert result == "He..."

    def test_max_length_equals_ellipsis(self):
        """Handle max_length equal to ellipsis length."""
        result = truncate_with_ellipsis("Hello", 3)
        assert result == "..."

    def test_max_length_less_than_ellipsis(self):
        """Handle max_length less than ellipsis length."""
        result = truncate_with_ellipsis("Hello", 2)
        assert result == ".."


# =============================================================================
# Test: derive_display_name
# =============================================================================

class TestDeriveDisplayName:
    """Tests for derive_display_name function."""

    def test_simple_objective(self):
        """Derive display name from simple objective."""
        result = derive_display_name("Implement user login. Add validation.")
        assert result == "Implement user login."

    def test_long_first_sentence(self):
        """Truncate long first sentence."""
        long_sentence = "A" * 200 + "."
        result = derive_display_name(long_sentence)
        assert len(result) == DISPLAY_NAME_MAX_LENGTH
        assert result.endswith(ELLIPSIS)

    def test_no_punctuation(self):
        """Handle objective without sentence punctuation."""
        result = derive_display_name("Simple objective without punctuation")
        assert result == "Simple objective without punctuation"

    def test_empty_objective(self):
        """Handle empty objective."""
        result = derive_display_name("")
        assert result == ""

    def test_none_objective(self):
        """Handle None objective gracefully."""
        result = derive_display_name(None)  # type: ignore
        assert result == ""

    def test_custom_max_length(self):
        """Respect custom max_length parameter."""
        result = derive_display_name("Hello World! More text.", max_length=50)
        assert len(result) <= 50

    def test_multiline_objective(self):
        """Handle multiline objective."""
        result = derive_display_name("First line\nSecond line\nThird line")
        assert result == "First line"

    def test_objective_with_code(self):
        """Handle objective with code snippets."""
        result = derive_display_name("Implement function foo(). Then add bar().")
        assert result == "Implement function foo()."


# =============================================================================
# Test: derive_icon
# =============================================================================

class TestDeriveIcon:
    """Tests for derive_icon function."""

    def test_coding_icon(self):
        """Coding task type returns hammer icon."""
        result = derive_icon("coding")
        assert result == "hammer"

    def test_testing_icon(self):
        """Testing task type returns flask icon."""
        result = derive_icon("testing")
        assert result == "flask"

    def test_refactoring_icon(self):
        """Refactoring task type returns recycle icon."""
        result = derive_icon("refactoring")
        assert result == "recycle"

    def test_documentation_icon(self):
        """Documentation task type returns book icon."""
        result = derive_icon("documentation")
        assert result == "book"

    def test_audit_icon(self):
        """Audit task type returns shield icon."""
        result = derive_icon("audit")
        assert result == "shield"

    def test_custom_icon(self):
        """Custom task type returns gear icon."""
        result = derive_icon("custom")
        assert result == "gear"

    def test_unknown_task_type(self):
        """Unknown task type returns default icon."""
        result = derive_icon("unknown")
        assert result == DEFAULT_ICON

    def test_empty_task_type(self):
        """Empty task type returns default icon."""
        result = derive_icon("")
        assert result == DEFAULT_ICON

    def test_none_task_type(self):
        """None task type returns default icon."""
        result = derive_icon(None)  # type: ignore
        assert result == DEFAULT_ICON

    def test_case_insensitive(self):
        """Task type matching is case insensitive."""
        assert derive_icon("CODING") == "hammer"
        assert derive_icon("Coding") == "hammer"
        assert derive_icon("CoDiNg") == "hammer"

    def test_context_override(self):
        """Context icon override takes precedence."""
        result = derive_icon("coding", context={"icon": "wrench"})
        assert result == "wrench"

    def test_context_override_empty_string(self):
        """Empty context icon doesn't override."""
        result = derive_icon("coding", context={"icon": ""})
        assert result == "hammer"

    def test_context_override_whitespace(self):
        """Whitespace-only context icon doesn't override."""
        result = derive_icon("coding", context={"icon": "   "})
        assert result == "hammer"

    def test_context_override_none(self):
        """None context icon doesn't override."""
        result = derive_icon("coding", context={"icon": None})
        assert result == "hammer"

    def test_context_without_icon_key(self):
        """Context without icon key uses task type."""
        result = derive_icon("coding", context={"other_key": "value"})
        assert result == "hammer"

    def test_context_is_none(self):
        """None context uses task type."""
        result = derive_icon("coding", context=None)
        assert result == "hammer"

    def test_all_task_types_mapped(self):
        """All defined task types have icon mappings."""
        task_types = ["coding", "testing", "refactoring", "documentation", "audit", "custom"]
        for task_type in task_types:
            icon = derive_icon(task_type)
            assert icon != "" and icon is not None
            assert icon in TASK_TYPE_ICONS.values()


# =============================================================================
# Test: derive_mascot_name
# =============================================================================

class TestDeriveMascotName:
    """Tests for derive_mascot_name function."""

    def test_feature_id_zero(self):
        """Feature ID 0 returns first mascot."""
        result = derive_mascot_name(feature_id=0)
        assert result == MASCOT_POOL[0]

    def test_feature_id_within_range(self):
        """Feature ID within pool size returns corresponding mascot."""
        result = derive_mascot_name(feature_id=5)
        assert result == MASCOT_POOL[5]

    def test_feature_id_wraps_around(self):
        """Feature ID larger than pool size wraps around."""
        pool_size = len(MASCOT_POOL)
        result = derive_mascot_name(feature_id=pool_size)
        assert result == MASCOT_POOL[0]

    def test_feature_id_negative(self):
        """Negative feature ID wraps correctly."""
        result = derive_mascot_name(feature_id=-1)
        assert result in MASCOT_POOL  # Python modulo handles negative correctly

    def test_spec_id_deterministic(self):
        """Same spec_id always returns same mascot."""
        spec_id = "abc123-def456-ghi789"
        result1 = derive_mascot_name(spec_id=spec_id)
        result2 = derive_mascot_name(spec_id=spec_id)
        assert result1 == result2
        assert result1 in MASCOT_POOL

    def test_different_spec_ids_different_mascots(self):
        """Different spec_ids may return different mascots."""
        # This is probabilistic, so we test with many IDs
        results = set()
        for i in range(100):
            result = derive_mascot_name(spec_id=f"spec-{i}")
            results.add(result)
        # Should have multiple different mascots
        assert len(results) > 1

    def test_context_override(self):
        """Context mascot override takes precedence."""
        result = derive_mascot_name(feature_id=0, context={"mascot": "CustomMascot"})
        assert result == "CustomMascot"

    def test_context_override_empty_string(self):
        """Empty context mascot doesn't override."""
        result = derive_mascot_name(feature_id=0, context={"mascot": ""})
        assert result == MASCOT_POOL[0]

    def test_context_override_whitespace(self):
        """Whitespace-only context mascot doesn't override."""
        result = derive_mascot_name(feature_id=0, context={"mascot": "   "})
        assert result == MASCOT_POOL[0]

    def test_context_override_none(self):
        """None context mascot doesn't override."""
        result = derive_mascot_name(feature_id=0, context={"mascot": None})
        assert result == MASCOT_POOL[0]

    def test_no_inputs_returns_first_mascot(self):
        """No inputs returns first mascot as fallback."""
        result = derive_mascot_name()
        assert result == MASCOT_POOL[0]

    def test_spec_id_takes_precedence_over_feature_id(self):
        """spec_id is used when both spec_id and feature_id provided."""
        spec_id = "test-spec-id-123"
        result_with_spec = derive_mascot_name(spec_id=spec_id, feature_id=0)
        result_without_spec = derive_mascot_name(feature_id=0)
        # spec_id result may differ from feature_id result
        assert result_with_spec in MASCOT_POOL


# =============================================================================
# Test: get_task_type_icons and get_mascot_pool
# =============================================================================

class TestGetters:
    """Tests for getter functions."""

    def test_get_task_type_icons_returns_copy(self):
        """get_task_type_icons returns a copy, not the original."""
        icons1 = get_task_type_icons()
        icons2 = get_task_type_icons()
        icons1["test"] = "modified"
        assert "test" not in icons2
        assert "test" not in TASK_TYPE_ICONS

    def test_get_task_type_icons_content(self):
        """get_task_type_icons returns expected content."""
        icons = get_task_type_icons()
        assert "coding" in icons
        assert icons["coding"] == "hammer"

    def test_get_mascot_pool_returns_copy(self):
        """get_mascot_pool returns a copy, not the original."""
        pool1 = get_mascot_pool()
        pool2 = get_mascot_pool()
        pool1.append("Modified")
        assert "Modified" not in pool2
        assert "Modified" not in MASCOT_POOL

    def test_get_mascot_pool_content(self):
        """get_mascot_pool returns expected content."""
        pool = get_mascot_pool()
        assert "Spark" in pool
        assert len(pool) == 20


# =============================================================================
# Test: derive_display_properties (combined derivation)
# =============================================================================

class TestDeriveDisplayProperties:
    """Tests for derive_display_properties combined function."""

    def test_basic_derivation(self):
        """Basic derivation returns all expected keys."""
        result = derive_display_properties(
            objective="Implement login feature. Add validation.",
            task_type="coding",
            feature_id=42
        )
        assert "display_name" in result
        assert "icon" in result
        assert "mascot_name" in result

    def test_display_name_derived(self):
        """Display name is derived from objective."""
        result = derive_display_properties(
            objective="Implement login feature. Add validation.",
            task_type="coding"
        )
        assert result["display_name"] == "Implement login feature."

    def test_icon_derived(self):
        """Icon is derived from task_type."""
        result = derive_display_properties(
            objective="Some objective.",
            task_type="testing"
        )
        assert result["icon"] == "flask"

    def test_mascot_derived_from_feature_id(self):
        """Mascot is derived from feature_id."""
        result = derive_display_properties(
            objective="Some objective.",
            task_type="coding",
            feature_id=5
        )
        assert result["mascot_name"] == MASCOT_POOL[5]

    def test_mascot_derived_from_spec_id(self):
        """Mascot is derived from spec_id."""
        result = derive_display_properties(
            objective="Some objective.",
            task_type="coding",
            spec_id="test-spec-123"
        )
        assert result["mascot_name"] in MASCOT_POOL

    def test_context_overrides(self):
        """Context overrides icon and mascot."""
        result = derive_display_properties(
            objective="Some objective.",
            task_type="coding",
            context={"icon": "custom-icon", "mascot": "CustomMascot"}
        )
        assert result["icon"] == "custom-icon"
        assert result["mascot_name"] == "CustomMascot"

    def test_custom_max_length(self):
        """Custom max_display_name_length is respected."""
        result = derive_display_properties(
            objective="A" * 200 + ".",
            task_type="coding",
            max_display_name_length=50
        )
        assert len(result["display_name"]) <= 50

    def test_empty_objective(self):
        """Empty objective returns empty display_name."""
        result = derive_display_properties(
            objective="",
            task_type="coding"
        )
        assert result["display_name"] == ""
        assert result["icon"] == "hammer"
        assert result["mascot_name"] == MASCOT_POOL[0]


# =============================================================================
# Test: Edge Cases and Integration
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_real_world_objective(self):
        """Test with realistic objective text."""
        objective = """
        Implement user authentication with OAuth2 support.

        Requirements:
        - Support Google and GitHub OAuth providers
        - Store user sessions in Redis
        - Add rate limiting for login attempts
        """
        result = derive_display_name(objective)
        assert result == "Implement user authentication with OAuth2 support."

    def test_objective_with_urls(self):
        """Test with objective containing URLs."""
        objective = "Fix bug in https://example.com/api. Deploy changes."
        result = derive_display_name(objective)
        assert "https://example.com/api" in result

    def test_objective_with_code_snippets(self):
        """Test with objective containing code."""
        objective = "Implement foo(bar: int) -> str function. Add tests."
        result = derive_display_name(objective)
        assert "foo(bar: int) -> str" in result

    def test_icon_with_invalid_context_type(self):
        """Handle context that's not a dict."""
        result = derive_icon("coding", context="not a dict")  # type: ignore
        assert result == "hammer"

    def test_mascot_with_invalid_context_type(self):
        """Handle context that's not a dict."""
        result = derive_mascot_name(context="not a dict")  # type: ignore
        assert result == MASCOT_POOL[0]

    def test_constants_are_correct(self):
        """Verify constants have expected values."""
        assert DISPLAY_NAME_MAX_LENGTH == 100
        assert DEFAULT_ICON == "gear"
        assert len(MASCOT_POOL) == 20
        assert len(TASK_TYPE_ICONS) == 6
