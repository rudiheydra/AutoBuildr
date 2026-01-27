"""
Test Feature #80: Keyboard Navigation for Agent Cards

Verifies that the DynamicAgentCard component and related code implements
keyboard navigation with focus management for accessibility.

Test Steps:
1. Add tabindex to DynamicAgentCard
2. Handle Enter/Space to open inspector
3. Handle Escape to close inspector (already in RunInspector)
4. Arrow keys to navigate card grid (via useAgentCardGridNavigation hook)
5. Focus visible indicator (CSS styles)
6. Screen reader announcements for status changes
"""

import os
import re
import json
import pytest


# ============================================================================
# Test Setup
# ============================================================================

UI_SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'ui', 'src')
COMPONENTS_DIR = os.path.join(UI_SRC_DIR, 'components')
HOOKS_DIR = os.path.join(UI_SRC_DIR, 'hooks')
STYLES_DIR = os.path.join(UI_SRC_DIR, 'styles')


def read_file(filepath: str) -> str:
    """Read file contents, returning empty string if not found."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""


# ============================================================================
# Step 1: Add tabindex to DynamicAgentCard
# ============================================================================

class TestStep1TabIndex:
    """Verify tabindex is added to DynamicAgentCard."""

    @pytest.fixture
    def card_content(self):
        return read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))

    def test_tabindex_prop_defined(self, card_content):
        """DynamicAgentCard should accept tabIndex prop."""
        assert 'tabIndex?' in card_content or "tabIndex: tabIndexProp" in card_content, \
            "DynamicAgentCard should accept tabIndex prop"

    def test_tabindex_attribute_in_render(self, card_content):
        """DynamicAgentCard should render tabIndex attribute."""
        assert 'tabIndex={tabIndex}' in card_content, \
            "DynamicAgentCard should render tabIndex on the element"

    def test_default_tabindex(self, card_content):
        """DynamicAgentCard should default tabIndex to 0 if not provided."""
        assert "tabIndexProp !== undefined ? tabIndexProp : 0" in card_content, \
            "Should default to tabIndex 0 when not provided"


# ============================================================================
# Step 2: Handle Enter/Space to open inspector
# ============================================================================

class TestStep2EnterSpace:
    """Verify Enter/Space key handling to open inspector."""

    @pytest.fixture
    def card_content(self):
        return read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))

    def test_keydown_handler_defined(self, card_content):
        """DynamicAgentCard should have a keyDown handler."""
        assert 'handleKeyDown' in card_content or 'onKeyDown' in card_content, \
            "Should have keyboard event handler"

    def test_enter_key_handling(self, card_content):
        """Should handle Enter key to trigger onClick."""
        assert "e.key === 'Enter'" in card_content, \
            "Should check for Enter key"

    def test_space_key_handling(self, card_content):
        """Should handle Space key to trigger onClick."""
        assert "e.key === ' '" in card_content, \
            "Should check for Space key"

    def test_onclick_called_on_key(self, card_content):
        """Should call onClick when Enter/Space pressed."""
        # Check that onClick is called in the key handler
        assert 'onClick?.()' in card_content, \
            "Should call onClick when key is pressed"


# ============================================================================
# Step 3: Handle Escape to close inspector
# ============================================================================

class TestStep3Escape:
    """Verify Escape key handling to close inspector."""

    @pytest.fixture
    def inspector_content(self):
        return read_file(os.path.join(COMPONENTS_DIR, 'RunInspector.tsx'))

    def test_escape_key_handler(self, inspector_content):
        """RunInspector should handle Escape key."""
        assert "e.key === 'Escape'" in inspector_content, \
            "RunInspector should listen for Escape key"

    def test_escape_calls_close(self, inspector_content):
        """Escape should call onClose."""
        # Check that the Escape handler calls onClose
        assert 'onClose()' in inspector_content or 'onClose?.()' in inspector_content, \
            "Escape should call onClose"


# ============================================================================
# Step 4: Arrow keys to navigate card grid
# ============================================================================

class TestStep4ArrowKeys:
    """Verify arrow key navigation via useAgentCardGridNavigation hook."""

    @pytest.fixture
    def hook_content(self):
        return read_file(os.path.join(HOOKS_DIR, 'useAgentCardGridNavigation.ts'))

    def test_hook_file_exists(self, hook_content):
        """useAgentCardGridNavigation hook file should exist."""
        assert len(hook_content) > 0, \
            "useAgentCardGridNavigation.ts should exist"

    def test_arrow_left_handling(self, hook_content):
        """Should handle ArrowLeft key."""
        assert 'ArrowLeft' in hook_content, \
            "Should handle ArrowLeft key"

    def test_arrow_right_handling(self, hook_content):
        """Should handle ArrowRight key."""
        assert 'ArrowRight' in hook_content, \
            "Should handle ArrowRight key"

    def test_arrow_up_handling(self, hook_content):
        """Should handle ArrowUp key."""
        assert 'ArrowUp' in hook_content, \
            "Should handle ArrowUp key"

    def test_arrow_down_handling(self, hook_content):
        """Should handle ArrowDown key."""
        assert 'ArrowDown' in hook_content, \
            "Should handle ArrowDown key"

    def test_home_key_handling(self, hook_content):
        """Should handle Home key to go to first card."""
        assert 'Home' in hook_content, \
            "Should handle Home key"

    def test_end_key_handling(self, hook_content):
        """Should handle End key to go to last card."""
        assert 'End' in hook_content, \
            "Should handle End key"

    def test_get_card_props_function(self, hook_content):
        """Should export getCardProps function."""
        assert 'getCardProps' in hook_content, \
            "Should have getCardProps function"

    def test_column_based_navigation(self, hook_content):
        """Should calculate navigation based on columns."""
        assert 'columns' in hook_content, \
            "Should support column-based navigation"


# ============================================================================
# Step 5: Focus visible indicator
# ============================================================================

class TestStep5FocusVisible:
    """Verify focus visible CSS styles."""

    @pytest.fixture
    def css_content(self):
        return read_file(os.path.join(STYLES_DIR, 'globals.css'))

    @pytest.fixture
    def card_content(self):
        return read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))

    def test_focus_visible_base_style(self, css_content):
        """Should have base :focus-visible style."""
        assert ':focus-visible' in css_content, \
            "Should have :focus-visible CSS rule"

    def test_agent_card_focus_class(self, css_content):
        """Should have agent card specific focus class."""
        assert '.neo-agent-card-focusable:focus-visible' in css_content, \
            "Should have .neo-agent-card-focusable:focus-visible rule"

    def test_focus_class_applied_to_card(self, card_content):
        """DynamicAgentCard should use neo-agent-card-focusable class."""
        assert 'neo-agent-card-focusable' in card_content, \
            "Card should use neo-agent-card-focusable class"

    def test_focus_outline_defined(self, css_content):
        """Should define outline for focus state."""
        assert 'outline:' in css_content or 'outline:' in css_content.replace(' ', ''), \
            "Should define outline style for focus"

    def test_focus_animation_defined(self, css_content):
        """Should have focus ring animation."""
        assert 'focus-ring-pulse' in css_content, \
            "Should have focus-ring-pulse animation"

    def test_reduced_motion_support(self, css_content):
        """Should support prefers-reduced-motion."""
        assert 'prefers-reduced-motion' in css_content, \
            "Should support reduced motion preference"

    def test_high_contrast_support(self, css_content):
        """Should support high contrast mode."""
        assert 'prefers-contrast' in css_content, \
            "Should support high contrast mode"


# ============================================================================
# Step 6: Screen reader announcements for status changes
# ============================================================================

class TestStep6ScreenReaderAnnouncements:
    """Verify screen reader announcements."""

    @pytest.fixture
    def card_content(self):
        return read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))

    @pytest.fixture
    def hook_content(self):
        return read_file(os.path.join(HOOKS_DIR, 'useAgentCardGridNavigation.ts'))

    @pytest.fixture
    def css_content(self):
        return read_file(os.path.join(STYLES_DIR, 'globals.css'))

    def test_status_badge_aria_live(self, card_content):
        """StatusBadge should have aria-live for announcements."""
        assert 'aria-live' in card_content, \
            "StatusBadge should have aria-live attribute"

    def test_status_badge_role(self, card_content):
        """StatusBadge should have role=status."""
        assert 'role="status"' in card_content, \
            "StatusBadge should have role=status"

    def test_aria_label_on_card(self, card_content):
        """Card should have aria-label for screen readers."""
        assert 'aria-label' in card_content, \
            "Card should have aria-label"

    def test_announce_function_in_hook(self, hook_content):
        """Hook should have announce function."""
        assert 'announce' in hook_content, \
            "Hook should have announce function"

    def test_announce_status_change_function(self, hook_content):
        """Hook should have announceStatusChange function."""
        assert 'announceStatusChange' in hook_content, \
            "Hook should have announceStatusChange function"

    def test_sr_only_class_defined(self, css_content):
        """Should have sr-only class for screen reader text."""
        assert '.sr-only' in css_content, \
            "Should have .sr-only class defined"

    def test_aria_hidden_on_icons(self, card_content):
        """Icons should have aria-hidden=true."""
        assert 'aria-hidden="true"' in card_content or "aria-hidden='true'" in card_content, \
            "Icons should have aria-hidden"


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for keyboard navigation feature."""

    @pytest.fixture
    def card_content(self):
        return read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))

    @pytest.fixture
    def hook_content(self):
        return read_file(os.path.join(HOOKS_DIR, 'useAgentCardGridNavigation.ts'))

    def test_card_accepts_navigation_props(self, card_content):
        """DynamicAgentCard should accept props from navigation hook."""
        props_to_check = [
            'tabIndex',
            'aria-selected',
            'data-card-index',
            'onKeyDown',
            'onFocus',
            'cardRef',
        ]
        for prop in props_to_check:
            assert prop in card_content, f"Card should accept {prop} prop"

    def test_card_role_is_gridcell(self, card_content):
        """Card should have role=gridcell for ARIA grid pattern."""
        assert 'role="gridcell"' in card_content, \
            "Card should have role=gridcell"

    def test_hook_exports_result_type(self, hook_content):
        """Hook should export GridNavigationResult type."""
        assert 'GridNavigationResult' in hook_content, \
            "Hook should define GridNavigationResult type"

    def test_hook_exports_card_props_type(self, hook_content):
        """Hook should export CardNavigationProps type."""
        assert 'CardNavigationProps' in hook_content, \
            "Hook should define CardNavigationProps type"

    def test_roving_tabindex_pattern(self, hook_content):
        """Hook should implement roving tabindex pattern."""
        # Roving tabindex: first card or focused card gets tabIndex 0, others get -1
        assert 'tabIndex:' in hook_content, \
            "Hook should set tabIndex"
        assert '-1' in hook_content or '= -1' in hook_content, \
            "Should use tabIndex -1 for non-focused cards"


# ============================================================================
# Feature Step Verification
# ============================================================================

class TestFeatureSteps:
    """Direct verification of all feature steps."""

    def test_step_1_tabindex(self):
        """Step 1: Add tabindex to DynamicAgentCard."""
        content = read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))
        assert 'tabIndex={tabIndex}' in content
        assert 'tabIndex?: number' in content or 'tabIndex: tabIndexProp' in content

    def test_step_2_enter_space(self):
        """Step 2: Handle Enter/Space to open inspector."""
        content = read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))
        assert "e.key === 'Enter'" in content
        assert "e.key === ' '" in content

    def test_step_3_escape(self):
        """Step 3: Handle Escape to close inspector."""
        content = read_file(os.path.join(COMPONENTS_DIR, 'RunInspector.tsx'))
        assert "e.key === 'Escape'" in content

    def test_step_4_arrow_keys(self):
        """Step 4: Arrow keys to navigate card grid."""
        content = read_file(os.path.join(HOOKS_DIR, 'useAgentCardGridNavigation.ts'))
        assert 'ArrowLeft' in content
        assert 'ArrowRight' in content
        assert 'ArrowUp' in content
        assert 'ArrowDown' in content

    def test_step_5_focus_visible(self):
        """Step 5: Focus visible indicator."""
        css = read_file(os.path.join(STYLES_DIR, 'globals.css'))
        card = read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))
        assert '.neo-agent-card-focusable:focus-visible' in css
        assert 'neo-agent-card-focusable' in card

    def test_step_6_screen_reader(self):
        """Step 6: Screen reader announcements for status changes."""
        card = read_file(os.path.join(COMPONENTS_DIR, 'DynamicAgentCard.tsx'))
        hook = read_file(os.path.join(HOOKS_DIR, 'useAgentCardGridNavigation.ts'))
        assert 'aria-live' in card
        assert 'announceStatusChange' in hook


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
