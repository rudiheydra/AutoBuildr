"""
Tests for Feature #148: Consolidate display derivation logic into single module.

Verifies that:
1. display_derivation.py is the single source of truth for display_name, icon, mascot
2. spec_builder.py delegates to display_derivation (no inline logic)
3. feature_compiler.py imports from display_derivation (no duplicate constants)
4. Icon values are consistent across all code paths
5. AgentSpecs created via any path get correct display_name, icon, and mascot values
"""
from __future__ import annotations

import ast
import inspect
import re

import pytest

# Import from the canonical source
from api.display_derivation import (
    DEFAULT_ICON,
    TASK_TYPE_ICONS,
    derive_display_name,
    derive_display_properties,
    derive_icon,
    derive_mascot_name,
)


# =============================================================================
# Step 1: Identify display derivation logic in all three modules
# =============================================================================

class TestStep1IdentifyLogic:
    """Verify that display derivation logic exists in display_derivation.py."""

    def test_display_derivation_has_derive_display_name(self):
        """display_derivation.py exports derive_display_name."""
        assert callable(derive_display_name)

    def test_display_derivation_has_derive_icon(self):
        """display_derivation.py exports derive_icon."""
        assert callable(derive_icon)

    def test_display_derivation_has_derive_mascot_name(self):
        """display_derivation.py exports derive_mascot_name."""
        assert callable(derive_mascot_name)

    def test_display_derivation_has_combined_function(self):
        """display_derivation.py exports derive_display_properties."""
        assert callable(derive_display_properties)

    def test_display_derivation_has_task_type_icons(self):
        """display_derivation.py exports TASK_TYPE_ICONS constant."""
        assert isinstance(TASK_TYPE_ICONS, dict)
        assert len(TASK_TYPE_ICONS) == 6

    def test_display_derivation_has_default_icon(self):
        """display_derivation.py exports DEFAULT_ICON constant."""
        assert isinstance(DEFAULT_ICON, str)
        assert DEFAULT_ICON == "gear"


# =============================================================================
# Step 2: Determine canonical implementation
# =============================================================================

class TestStep2CanonicalImplementation:
    """Verify display_derivation.py has the most complete implementation."""

    def test_all_task_types_have_icons(self):
        """All expected task types are mapped."""
        expected_types = {"coding", "testing", "refactoring", "documentation", "audit", "custom"}
        assert set(TASK_TYPE_ICONS.keys()) == expected_types

    def test_derive_display_name_handles_sentences(self):
        """derive_display_name extracts first sentence."""
        result = derive_display_name("First sentence. Second sentence.")
        assert result == "First sentence."

    def test_derive_display_name_handles_truncation(self):
        """derive_display_name truncates long names."""
        long_text = "A" * 200
        result = derive_display_name(long_text)
        assert len(result) <= 100
        assert result.endswith("...")

    def test_derive_display_name_handles_empty(self):
        """derive_display_name handles empty input."""
        assert derive_display_name("") == ""
        assert derive_display_name(None) == ""  # type: ignore

    def test_derive_icon_handles_context_override(self):
        """derive_icon supports context override."""
        result = derive_icon("coding", context={"icon": "custom-icon"})
        assert result == "custom-icon"

    def test_derive_mascot_name_has_deterministic_selection(self):
        """derive_mascot_name selects deterministically."""
        result1 = derive_mascot_name(feature_id=42)
        result2 = derive_mascot_name(feature_id=42)
        assert result1 == result2


# =============================================================================
# Step 3: Consolidation - display_derivation.py is single source of truth
# =============================================================================

class TestStep3Consolidation:
    """Verify display_derivation.py is the single source of truth."""

    def test_feature_compiler_imports_from_display_derivation(self):
        """feature_compiler.py imports TASK_TYPE_ICONS from display_derivation."""
        import api.feature_compiler as fc
        # The TASK_TYPE_ICONS in feature_compiler should be the same object
        # as the one in display_derivation (imported, not duplicated)
        assert fc.TASK_TYPE_ICONS is TASK_TYPE_ICONS

    def test_feature_compiler_imports_default_icon(self):
        """feature_compiler.py imports DEFAULT_ICON from display_derivation."""
        import api.feature_compiler as fc
        assert fc.DEFAULT_ICON is DEFAULT_ICON

    def test_feature_compiler_no_local_icon_definition(self):
        """feature_compiler.py does NOT define its own TASK_TYPE_ICONS dict literal."""
        import api.feature_compiler
        source = inspect.getsource(api.feature_compiler)
        # Should not have a dict literal assignment for TASK_TYPE_ICONS
        # It should import from display_derivation instead
        # Look for patterns like TASK_TYPE_ICONS: dict... = { or TASK_TYPE_ICONS = {
        # But NOT in comments or docstrings
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            # Skip comments and import lines
            if stripped.startswith("#") or stripped.startswith("from ") or stripped.startswith("import "):
                continue
            # Check for local definition (assignment with dict literal)
            if re.match(r'^TASK_TYPE_ICONS\s*[:=].*\{', stripped):
                pytest.fail(
                    f"feature_compiler.py has local TASK_TYPE_ICONS definition: {stripped}"
                )


# =============================================================================
# Step 4: spec_builder.py imports from display_derivation
# =============================================================================

class TestStep4SpecBuilderImports:
    """Verify spec_builder.py delegates to display_derivation."""

    def test_spec_builder_imports_derive_display_name(self):
        """spec_builder.py imports derive_display_name from display_derivation."""
        import api.spec_builder
        source = inspect.getsource(api.spec_builder)
        assert "from api.display_derivation import" in source
        assert "derive_display_name" in source

    def test_spec_builder_imports_derive_icon(self):
        """spec_builder.py imports derive_icon from display_derivation."""
        import api.spec_builder
        source = inspect.getsource(api.spec_builder)
        assert "derive_icon" in source

    def test_spec_builder_no_local_icon_dict(self):
        """spec_builder._derive_icon does not contain a local icon dict literal."""
        from api.spec_builder import SpecBuilder
        source = inspect.getsource(SpecBuilder._derive_icon)
        # Should NOT contain a dictionary literal with icon mappings
        assert '"code"' not in source or "derive_icon" in source
        # Should delegate to display_derivation.derive_icon
        assert "derive_icon" in source

    def test_spec_builder_derive_display_name_delegates(self):
        """spec_builder._derive_display_name delegates to display_derivation."""
        from api.spec_builder import SpecBuilder
        source = inspect.getsource(SpecBuilder._derive_display_name)
        # Should delegate to display_derivation.derive_display_name
        assert "derive_display_name" in source


# =============================================================================
# Step 5: feature_compiler.py imports from display_derivation
# =============================================================================

class TestStep5FeatureCompilerImports:
    """Verify feature_compiler.py imports from display_derivation."""

    def test_feature_compiler_source_imports_display_derivation(self):
        """feature_compiler.py has import statement from display_derivation."""
        import api.feature_compiler
        source = inspect.getsource(api.feature_compiler)
        assert "from api.display_derivation import" in source

    def test_feature_compiler_uses_imported_icons(self):
        """FeatureCompiler.compile uses TASK_TYPE_ICONS from display_derivation."""
        from api.feature_compiler import FeatureCompiler
        compiler = FeatureCompiler()
        # The default_icon should be DEFAULT_ICON from display_derivation
        assert compiler._default_icon == DEFAULT_ICON


# =============================================================================
# Step 6: Icon values are consistent across all code paths
# =============================================================================

class TestStep6IconConsistency:
    """Verify icon values are consistent across all modules."""

    def test_coding_icon_consistent(self):
        """'coding' maps to 'code' everywhere."""
        assert TASK_TYPE_ICONS["coding"] == "code"
        assert derive_icon("coding") == "code"

    def test_testing_icon_consistent(self):
        """'testing' maps to 'test-tube' everywhere."""
        assert TASK_TYPE_ICONS["testing"] == "test-tube"
        assert derive_icon("testing") == "test-tube"

    def test_refactoring_icon_consistent(self):
        """'refactoring' maps to 'wrench' everywhere."""
        assert TASK_TYPE_ICONS["refactoring"] == "wrench"
        assert derive_icon("refactoring") == "wrench"

    def test_documentation_icon_consistent(self):
        """'documentation' maps to 'book' everywhere."""
        assert TASK_TYPE_ICONS["documentation"] == "book"
        assert derive_icon("documentation") == "book"

    def test_audit_icon_consistent(self):
        """'audit' maps to 'shield' everywhere."""
        assert TASK_TYPE_ICONS["audit"] == "shield"
        assert derive_icon("audit") == "shield"

    def test_custom_icon_consistent(self):
        """'custom' maps to 'gear' everywhere."""
        assert TASK_TYPE_ICONS["custom"] == "gear"
        assert derive_icon("custom") == "gear"

    def test_feature_compiler_icons_match_display_derivation(self):
        """feature_compiler TASK_TYPE_ICONS matches display_derivation."""
        import api.feature_compiler as fc
        assert fc.TASK_TYPE_ICONS == TASK_TYPE_ICONS

    def test_all_icons_consistent_with_static_adapter(self):
        """Icons match static_spec_adapter conventions (code, test-tube)."""
        # These are the values used by static_spec_adapter.py
        assert derive_icon("coding") == "code"
        assert derive_icon("testing") == "test-tube"


# =============================================================================
# Step 7: AgentSpecs created via any path get correct values
# =============================================================================

class TestStep7AgentSpecValues:
    """Verify AgentSpecs created via any path get correct display values."""

    def test_feature_compiler_produces_correct_icon(self):
        """FeatureCompiler produces correct icon for coding feature."""
        from unittest.mock import MagicMock
        from api.feature_compiler import FeatureCompiler

        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 1
        feature.name = "Test Feature"
        feature.description = "Test description"
        feature.category = "A. Database"
        feature.steps = ["Step 1"]
        feature.priority = 1

        spec = compiler.compile(feature)
        assert spec.icon == "code"  # coding -> code

    def test_feature_compiler_produces_correct_icon_for_testing(self):
        """FeatureCompiler produces correct icon for testing feature."""
        from unittest.mock import MagicMock
        from api.feature_compiler import FeatureCompiler

        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 2
        feature.name = "Test Feature"
        feature.description = "Test description"
        feature.category = "B. Testing"
        feature.steps = ["Step 1"]
        feature.priority = 2

        spec = compiler.compile(feature)
        assert spec.icon == "test-tube"  # testing -> test-tube

    def test_feature_compiler_produces_correct_icon_for_docs(self):
        """FeatureCompiler produces correct icon for documentation feature."""
        from unittest.mock import MagicMock
        from api.feature_compiler import FeatureCompiler

        compiler = FeatureCompiler()
        feature = MagicMock()
        feature.id = 3
        feature.name = "Doc Feature"
        feature.description = "Documentation"
        feature.category = "Documentation"
        feature.steps = ["Step 1"]
        feature.priority = 3

        spec = compiler.compile(feature)
        assert spec.icon == "book"  # documentation -> book

    def test_derive_display_properties_returns_consistent_icon(self):
        """derive_display_properties returns consistent icon values."""
        result = derive_display_properties(
            objective="Implement login.",
            task_type="coding",
            feature_id=1,
        )
        assert result["icon"] == "code"
        assert result["display_name"] == "Implement login."
        assert result["mascot_name"] != ""

    def test_spec_builder_derive_methods_consistent(self):
        """SpecBuilder private methods produce consistent results."""
        from api.spec_builder import SpecBuilder

        builder = SpecBuilder.__new__(SpecBuilder)
        # Test _derive_icon
        assert builder._derive_icon("coding") == "code"
        assert builder._derive_icon("testing") == "test-tube"
        assert builder._derive_icon("refactoring") == "wrench"

        # Test _derive_display_name
        display = builder._derive_display_name(
            "Implement auth. Add validation.",
            "fallback text"
        )
        assert display == "Implement auth."
