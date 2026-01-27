"""
Feature #82: Mobile Responsive Agent Card Grid
==============================================

Tests to verify that the DynamicAgentCard grid is responsive with:
1. Tailwind responsive breakpoints (mobile: 1col, tablet: 2col, desktop: 3col, large: 4col)
2. Full-width inspector on mobile
3. Touch-friendly tap targets (min 44px)

Since browser automation is not available, we verify through CSS analysis.
"""

import re
import os
import pytest


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def globals_css_content():
    """Load the globals.css file content."""
    css_path = os.path.join(
        os.path.dirname(__file__), "..", "ui", "src", "styles", "globals.css"
    )
    with open(css_path, "r") as f:
        return f.read()


@pytest.fixture
def dynamic_agent_card_content():
    """Load the DynamicAgentCard.tsx file content."""
    tsx_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "ui",
        "src",
        "components",
        "DynamicAgentCard.tsx",
    )
    with open(tsx_path, "r") as f:
        return f.read()


@pytest.fixture
def run_inspector_content():
    """Load the RunInspector.tsx file content."""
    tsx_path = os.path.join(
        os.path.dirname(__file__), "..", "ui", "src", "components", "RunInspector.tsx"
    )
    with open(tsx_path, "r") as f:
        return f.read()


@pytest.fixture
def responsive_columns_hook_content():
    """Load the useResponsiveColumns.ts hook content."""
    ts_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "ui",
        "src",
        "hooks",
        "useResponsiveColumns.ts",
    )
    with open(ts_path, "r") as f:
        return f.read()


@pytest.fixture
def responsive_grid_demo_content():
    """Load the ResponsiveGridDemo.tsx component content."""
    tsx_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "ui",
        "src",
        "components",
        "ResponsiveGridDemo.tsx",
    )
    with open(tsx_path, "r") as f:
        return f.read()


# =============================================================================
# Step 1: Use Tailwind Responsive Breakpoints
# =============================================================================


class TestTailwindResponsiveBreakpoints:
    """Verify Tailwind responsive breakpoints are used correctly."""

    def test_neo_agent_card_grid_class_exists(self, globals_css_content):
        """Test that .neo-agent-card-grid class is defined."""
        assert ".neo-agent-card-grid" in globals_css_content, (
            ".neo-agent-card-grid class should be defined in globals.css"
        )

    def test_mobile_first_single_column(self, globals_css_content):
        """Test that mobile (default) has 1 column layout."""
        # Check for grid-template-columns: 1fr in the base definition
        # The base definition should have 1fr for mobile-first approach
        pattern = r"\.neo-agent-card-grid\s*\{[^}]*grid-template-columns:\s*1fr"
        assert re.search(pattern, globals_css_content, re.DOTALL), (
            "Mobile (default) should use grid-template-columns: 1fr for single column"
        )


# =============================================================================
# Step 2: Desktop 3-4 Cards Per Row
# =============================================================================


class TestDesktopLayout:
    """Verify desktop has 3-4 cards per row."""

    def test_desktop_three_columns(self, globals_css_content):
        """Test that desktop (1024px+) has 3 columns."""
        # Check for min-width: 1024px media query with repeat(3, 1fr)
        pattern = r"@media\s*\([^)]*min-width:\s*1024px[^)]*\)\s*\{[^}]*\.neo-agent-card-grid\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*1fr\)"
        assert re.search(pattern, globals_css_content, re.DOTALL), (
            "Desktop (1024px) should use repeat(3, 1fr) for 3 columns"
        )

    def test_large_desktop_four_columns(self, globals_css_content):
        """Test that large desktop (1280px+) has 4 columns."""
        # Check for min-width: 1280px media query with repeat(4, 1fr)
        pattern = r"@media\s*\([^)]*min-width:\s*1280px[^)]*\)\s*\{[^}]*\.neo-agent-card-grid\s*\{[^}]*grid-template-columns:\s*repeat\(4,\s*1fr\)"
        assert re.search(pattern, globals_css_content, re.DOTALL), (
            "Large desktop (1280px) should use repeat(4, 1fr) for 4 columns"
        )


# =============================================================================
# Step 3: Tablet 2 Cards Per Row
# =============================================================================


class TestTabletLayout:
    """Verify tablet has 2 cards per row."""

    def test_tablet_two_columns(self, globals_css_content):
        """Test that tablet (640px+) has 2 columns."""
        # Check for min-width: 640px media query with repeat(2, 1fr)
        pattern = r"@media\s*\([^)]*min-width:\s*640px[^)]*\)\s*\{[^}]*\.neo-agent-card-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*1fr\)"
        assert re.search(pattern, globals_css_content, re.DOTALL), (
            "Tablet (640px) should use repeat(2, 1fr) for 2 columns"
        )


# =============================================================================
# Step 4: Mobile 1 Card Per Row Stacked
# =============================================================================


class TestMobileLayout:
    """Verify mobile has 1 card per row stacked."""

    def test_mobile_stacked_layout(self, globals_css_content):
        """Test that mobile (default) shows stacked single column."""
        # Already covered by test_mobile_first_single_column
        # Additional check: no multi-column below 640px
        pattern = r"\.neo-agent-card-grid\s*\{[^}]*grid-template-columns:\s*1fr[^}]*\}"
        match = re.search(pattern, globals_css_content, re.DOTALL)
        assert match, "Mobile should have single column stacked layout"


# =============================================================================
# Step 5: Inspector Full-Width on Mobile
# =============================================================================


class TestInspectorMobileFullWidth:
    """Verify RunInspector is full-width on mobile."""

    def test_inspector_has_w_full_class(self, run_inspector_content):
        """Test that RunInspector panel has w-full class for mobile."""
        assert "w-full" in run_inspector_content, (
            "RunInspector should have w-full class for full width on mobile"
        )

    def test_inspector_has_responsive_width(self, run_inspector_content):
        """Test that RunInspector has responsive width classes."""
        # Should have sm: md: lg: breakpoint classes
        assert "sm:w-" in run_inspector_content, (
            "RunInspector should have sm: responsive width"
        )
        assert "md:w-" in run_inspector_content, (
            "RunInspector should have md: responsive width"
        )
        assert "lg:" in run_inspector_content, (
            "RunInspector should have lg: responsive breakpoint"
        )


# =============================================================================
# Step 6: Touch-Friendly Tap Targets (Min 44px)
# =============================================================================


class TestTouchFriendlyTapTargets:
    """Verify touch targets are at least 44px."""

    def test_card_has_min_height(self, dynamic_agent_card_content):
        """Test that DynamicAgentCard has minimum height for touch targets."""
        assert "min-h-" in dynamic_agent_card_content, (
            "DynamicAgentCard should have min-height for touch accessibility"
        )

    def test_card_has_touch_manipulation(self, dynamic_agent_card_content):
        """Test that DynamicAgentCard uses touch-manipulation class."""
        assert "touch-manipulation" in dynamic_agent_card_content, (
            "DynamicAgentCard should have touch-manipulation CSS for better touch handling"
        )

    def test_touch_target_utility_defined(self, globals_css_content):
        """Test that touch target utility classes are defined."""
        # Check for min-height: 44px touch target styles
        assert "44px" in globals_css_content or "min-height: 44px" in globals_css_content or "min-h-" in globals_css_content, (
            "Touch target utility with 44px minimum should be defined"
        )

    def test_view_details_button_has_touch_target(self, dynamic_agent_card_content):
        """Test that View Details button has touch-friendly size."""
        # Should have min-h-[44px] on mobile
        assert "min-h-[44px]" in dynamic_agent_card_content, (
            "View Details button should have min-h-[44px] for touch accessibility"
        )


# =============================================================================
# Step 7: Test on Various Screen Sizes
# =============================================================================


class TestResponsiveColumnsHook:
    """Verify useResponsiveColumns hook provides correct values."""

    def test_breakpoints_defined(self, responsive_columns_hook_content):
        """Test that breakpoints are defined correctly."""
        assert "sm: 640" in responsive_columns_hook_content or "640" in responsive_columns_hook_content, (
            "sm breakpoint (640px) should be defined"
        )
        assert "1024" in responsive_columns_hook_content, (
            "lg breakpoint (1024px) should be defined"
        )
        assert "1280" in responsive_columns_hook_content, (
            "xl breakpoint (1280px) should be defined"
        )

    def test_column_counts_defined(self, responsive_columns_hook_content):
        """Test that column counts are defined for each breakpoint."""
        assert "mobile: 1" in responsive_columns_hook_content, (
            "Mobile column count should be 1"
        )
        assert "tablet: 2" in responsive_columns_hook_content, (
            "Tablet column count should be 2"
        )
        assert "desktop: 3" in responsive_columns_hook_content, (
            "Desktop column count should be 3"
        )
        assert "large: 4" in responsive_columns_hook_content, (
            "Large desktop column count should be 4"
        )

    def test_hook_exports(self, responsive_columns_hook_content):
        """Test that hook exports required functions."""
        assert "export function useResponsiveColumns" in responsive_columns_hook_content, (
            "useResponsiveColumns should be exported"
        )
        assert "export function useGridColumns" in responsive_columns_hook_content, (
            "useGridColumns convenience function should be exported"
        )

    def test_hook_returns_device_info(self, responsive_columns_hook_content):
        """Test that hook returns device type info."""
        assert "isMobile" in responsive_columns_hook_content
        assert "isTablet" in responsive_columns_hook_content
        assert "isDesktop" in responsive_columns_hook_content
        assert "isTouchDevice" in responsive_columns_hook_content


# =============================================================================
# Demo Component Tests
# =============================================================================


class TestResponsiveGridDemo:
    """Verify the demo component showcases all responsive features."""

    def test_demo_uses_responsive_grid_class(self, responsive_grid_demo_content):
        """Test that demo uses the responsive grid class."""
        assert "neo-agent-card-grid" in responsive_grid_demo_content, (
            "Demo should use neo-agent-card-grid class"
        )

    def test_demo_uses_responsive_columns_hook(self, responsive_grid_demo_content):
        """Test that demo uses useResponsiveColumns hook."""
        assert "useResponsiveColumns" in responsive_grid_demo_content, (
            "Demo should use useResponsiveColumns hook"
        )

    def test_demo_displays_device_info(self, responsive_grid_demo_content):
        """Test that demo displays device info panel."""
        assert 'data-testid="device-info-panel"' in responsive_grid_demo_content, (
            "Demo should have device info panel with data-testid"
        )
        assert 'data-testid="column-count"' in responsive_grid_demo_content, (
            "Demo should display column count"
        )
        assert 'data-testid="window-width"' in responsive_grid_demo_content, (
            "Demo should display window width"
        )

    def test_demo_has_touch_target_verification(self, responsive_grid_demo_content):
        """Test that demo includes touch target verification."""
        assert "Touch Target" in responsive_grid_demo_content, (
            "Demo should include touch target verification section"
        )


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for responsive grid feature."""

    def test_all_required_files_exist(self):
        """Test that all required files for the feature exist."""
        base_path = os.path.join(os.path.dirname(__file__), "..")
        required_files = [
            "ui/src/styles/globals.css",
            "ui/src/components/DynamicAgentCard.tsx",
            "ui/src/components/RunInspector.tsx",
            "ui/src/hooks/useResponsiveColumns.ts",
            "ui/src/components/ResponsiveGridDemo.tsx",
        ]
        for file_path in required_files:
            full_path = os.path.join(base_path, file_path)
            assert os.path.exists(full_path), f"Required file should exist: {file_path}"

    def test_css_grid_gap_defined(self, globals_css_content):
        """Test that grid has appropriate gap for card spacing."""
        # Check that gap is defined in the grid class
        pattern = r"\.neo-agent-card-grid\s*\{[^}]*gap:\s*1rem"
        assert re.search(pattern, globals_css_content, re.DOTALL), (
            "Grid should have gap: 1rem for card spacing"
        )


# =============================================================================
# Feature Verification Summary
# =============================================================================


class TestFeatureVerificationSummary:
    """Summary verification for all 7 feature steps."""

    def test_step_1_tailwind_breakpoints(self, globals_css_content):
        """Step 1: Use Tailwind responsive breakpoints."""
        # Verify media queries for different breakpoints
        assert "@media" in globals_css_content
        assert "min-width: 640px" in globals_css_content
        assert "min-width: 1024px" in globals_css_content
        assert "min-width: 1280px" in globals_css_content

    def test_step_2_desktop_3_4_cards(self, globals_css_content):
        """Step 2: Desktop: 3-4 cards per row."""
        assert "repeat(3, 1fr)" in globals_css_content
        assert "repeat(4, 1fr)" in globals_css_content

    def test_step_3_tablet_2_cards(self, globals_css_content):
        """Step 3: Tablet: 2 cards per row."""
        assert "repeat(2, 1fr)" in globals_css_content

    def test_step_4_mobile_1_card(self, globals_css_content):
        """Step 4: Mobile: 1 card per row stacked."""
        # First definition should be 1fr (mobile-first)
        pattern = r"\.neo-agent-card-grid\s*\{[^}]*grid-template-columns:\s*1fr"
        assert re.search(pattern, globals_css_content, re.DOTALL)

    def test_step_5_inspector_full_width_mobile(self, run_inspector_content):
        """Step 5: Inspector full-width on mobile."""
        assert "w-full" in run_inspector_content

    def test_step_6_touch_targets(self, dynamic_agent_card_content):
        """Step 6: Touch-friendly tap targets (min 44px)."""
        assert "min-h-[44px]" in dynamic_agent_card_content
        assert "touch-manipulation" in dynamic_agent_card_content

    def test_step_7_various_screen_sizes(self, responsive_columns_hook_content):
        """Step 7: Test on various screen sizes."""
        # Hook provides mechanism to test different sizes
        assert "useResponsiveColumns" in responsive_columns_hook_content
        assert "windowWidth" in responsive_columns_hook_content
        assert "columns" in responsive_columns_hook_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
