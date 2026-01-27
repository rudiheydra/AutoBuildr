"""
Feature #81: ARIA Labels for Dynamic Components
================================================

This test verifies that appropriate ARIA labels and roles have been added
for screen reader compatibility in the dynamic UI components.

Components verified:
- DynamicAgentCard
- EventTimeline
- RunInspector
- TurnsProgressBar
- ArtifactList
"""

import re
import os
import pytest
from pathlib import Path


# Get the UI components path
UI_COMPONENTS_PATH = Path(__file__).parent.parent / "ui" / "src" / "components"


class TestDynamicAgentCardARIA:
    """Test ARIA implementation in DynamicAgentCard component."""

    @pytest.fixture
    def component_source(self):
        """Load the DynamicAgentCard component source."""
        component_path = UI_COMPONENTS_PATH / "DynamicAgentCard.tsx"
        return component_path.read_text()

    def test_step1_clickable_cards_have_role_button(self, component_source):
        """Step 1: Add role=button to clickable cards."""
        # Check that the main card has role="gridcell" or role="button"
        assert 'role="gridcell"' in component_source or 'role="button"' in component_source, \
            "DynamicAgentCard should have role='button' or 'gridcell'"

    def test_step2_aria_label_with_spec_name_and_status(self, component_source):
        """Step 2: Add aria-label with spec name and status."""
        # Check for aria-label pattern that includes display_name and status
        assert 'aria-label={`${spec.display_name} - ${getStatusLabel(status)}`}' in component_source, \
            "DynamicAgentCard should have aria-label with spec name and status"

    def test_step3_aria_live_polite_for_status_updates(self, component_source):
        """Step 3: Add aria-live=polite to status updates."""
        # Check StatusBadge has aria-live="polite"
        assert 'aria-live="polite"' in component_source, \
            "StatusBadge should have aria-live='polite'"

    def test_status_badge_has_role_status(self, component_source):
        """StatusBadge should have role='status'."""
        assert 'role="status"' in component_source, \
            "StatusBadge should have role='status'"

    def test_icons_are_hidden_from_screen_readers(self, component_source):
        """Icons should have aria-hidden='true'."""
        # Count occurrences of aria-hidden on icons
        aria_hidden_count = component_source.count('aria-hidden="true"')
        assert aria_hidden_count >= 3, \
            f"Expected at least 3 aria-hidden='true' attributes, found {aria_hidden_count}"

    def test_thinking_state_indicator_has_accessibility(self, component_source):
        """ThinkingStateIndicator should have proper accessibility attributes."""
        assert 'role="status"' in component_source
        assert 'aria-live="polite"' in component_source
        assert 'data-testid="thinking-state-indicator"' in component_source


class TestTurnsProgressBarARIA:
    """Test ARIA implementation in TurnsProgressBar component."""

    @pytest.fixture
    def component_source(self):
        """Load the TurnsProgressBar component source."""
        component_path = UI_COMPONENTS_PATH / "TurnsProgressBar.tsx"
        return component_path.read_text()

    def test_step4_aria_describedby_for_progress_bar(self, component_source):
        """Step 4: Add aria-describedby for progress bar."""
        assert 'aria-describedby=' in component_source, \
            "TurnsProgressBar should have aria-describedby"

    def test_has_role_progressbar(self, component_source):
        """Progress bar should have role='progressbar'."""
        assert 'role="progressbar"' in component_source

    def test_has_aria_valuenow(self, component_source):
        """Progress bar should have aria-valuenow."""
        assert 'aria-valuenow={used}' in component_source

    def test_has_aria_valuemin(self, component_source):
        """Progress bar should have aria-valuemin."""
        assert 'aria-valuemin={0}' in component_source

    def test_has_aria_valuemax(self, component_source):
        """Progress bar should have aria-valuemax."""
        assert 'aria-valuemax={max}' in component_source

    def test_has_aria_label(self, component_source):
        """Progress bar should have aria-label."""
        assert 'aria-label={`${used} of ${max} turns used`}' in component_source

    def test_uses_useId_hook(self, component_source):
        """Should use useId hook for unique IDs."""
        assert 'useId' in component_source


class TestRunInspectorARIA:
    """Test ARIA implementation in RunInspector component."""

    @pytest.fixture
    def component_source(self):
        """Load the RunInspector component source."""
        component_path = UI_COMPONENTS_PATH / "RunInspector.tsx"
        return component_path.read_text()

    def test_step5_inspector_close_button_labeled(self, component_source):
        """Step 5: Label inspector close button."""
        assert 'aria-label="Close inspector' in component_source, \
            "Close button should have aria-label"

    def test_dialog_has_role(self, component_source):
        """Dialog should have role='dialog'."""
        assert 'role="dialog"' in component_source

    def test_dialog_has_aria_modal(self, component_source):
        """Dialog should have aria-modal='true'."""
        assert 'aria-modal="true"' in component_source

    def test_dialog_has_aria_labelledby(self, component_source):
        """Dialog should have aria-labelledby."""
        assert 'aria-labelledby="run-inspector-title"' in component_source

    def test_tabs_have_role_tablist(self, component_source):
        """Tab container should have role='tablist'."""
        assert 'role="tablist"' in component_source

    def test_tabs_have_role_tab(self, component_source):
        """Tabs should have role='tab'."""
        assert 'role="tab"' in component_source

    def test_tabs_have_aria_selected(self, component_source):
        """Tabs should have aria-selected."""
        assert 'aria-selected=' in component_source

    def test_tab_panels_have_role(self, component_source):
        """Tab panels should have role='tabpanel'."""
        assert 'role="tabpanel"' in component_source

    def test_tab_panels_have_aria_labelledby(self, component_source):
        """Tab panels should have aria-labelledby."""
        assert 'aria-labelledby=' in component_source


class TestEventTimelineARIA:
    """Test ARIA implementation in EventTimeline component."""

    @pytest.fixture
    def component_source(self):
        """Load the EventTimeline component source."""
        component_path = UI_COMPONENTS_PATH / "EventTimeline.tsx"
        return component_path.read_text()

    def test_step6_expandable_events_have_aria_expanded(self, component_source):
        """Step 6: Add aria-expanded for expandable events."""
        assert 'aria-expanded={isExpanded}' in component_source, \
            "EventCard should have aria-expanded"

    def test_event_cards_have_role_button(self, component_source):
        """Event cards should have role='button'."""
        assert 'role="button"' in component_source

    def test_event_cards_have_tabindex(self, component_source):
        """Event cards should have tabIndex={0}."""
        assert 'tabIndex={0}' in component_source

    def test_event_cards_have_aria_label(self, component_source):
        """Event cards should have aria-label."""
        assert 'aria-label=' in component_source

    def test_filter_dropdown_has_aria_haspopup(self, component_source):
        """Filter dropdown should have aria-haspopup."""
        assert 'aria-haspopup="listbox"' in component_source

    def test_filter_dropdown_has_aria_expanded(self, component_source):
        """Filter dropdown should have aria-expanded."""
        assert 'aria-expanded={isOpen}' in component_source

    def test_dropdown_list_has_role_listbox(self, component_source):
        """Dropdown list should have role='listbox'."""
        assert 'role="listbox"' in component_source

    def test_dropdown_options_have_role_option(self, component_source):
        """Dropdown options should have role='option'."""
        assert 'role="option"' in component_source

    def test_dropdown_options_have_aria_selected(self, component_source):
        """Dropdown options should have aria-selected."""
        assert 'aria-selected=' in component_source

    def test_refresh_button_has_aria_label(self, component_source):
        """Refresh button should have aria-label."""
        assert 'aria-label="Refresh event timeline"' in component_source

    def test_icons_are_hidden(self, component_source):
        """Icons should have aria-hidden='true'."""
        assert 'aria-hidden="true"' in component_source


class TestArtifactListARIA:
    """Test ARIA implementation in ArtifactList component."""

    @pytest.fixture
    def component_source(self):
        """Load the ArtifactList component source."""
        component_path = UI_COMPONENTS_PATH / "ArtifactList.tsx"
        return component_path.read_text()

    def test_preview_modal_has_role_dialog(self, component_source):
        """Preview modal should have role='dialog'."""
        assert 'role="dialog"' in component_source

    def test_preview_modal_has_aria_modal(self, component_source):
        """Preview modal should have aria-modal='true'."""
        assert 'aria-modal="true"' in component_source

    def test_preview_modal_close_button_labeled(self, component_source):
        """Preview modal close button should have aria-label."""
        assert 'aria-label="Close preview modal"' in component_source

    def test_filter_dropdown_has_aria_haspopup(self, component_source):
        """Filter dropdown should have aria-haspopup."""
        assert 'aria-haspopup="listbox"' in component_source

    def test_dropdown_list_has_role_listbox(self, component_source):
        """Dropdown list should have role='listbox'."""
        assert 'role="listbox"' in component_source

    def test_dropdown_options_have_role_option(self, component_source):
        """Dropdown options should have role='option'."""
        assert 'role="option"' in component_source

    def test_artifact_cards_have_aria_label_when_clickable(self, component_source):
        """Artifact cards should have aria-label when clickable."""
        # Check for conditional aria-label pattern
        assert 'aria-label={onClick ?' in component_source

    def test_refresh_button_has_aria_label(self, component_source):
        """Refresh button should have aria-label."""
        assert 'aria-label="Refresh artifacts list"' in component_source

    def test_preview_button_has_aria_label(self, component_source):
        """Preview button should have aria-label."""
        assert 'aria-label={`Preview' in component_source

    def test_download_button_has_aria_label(self, component_source):
        """Download button should have aria-label."""
        assert 'aria-label={`Download' in component_source

    def test_icons_are_hidden(self, component_source):
        """Icons should have aria-hidden='true'."""
        aria_hidden_count = component_source.count('aria-hidden="true"')
        assert aria_hidden_count >= 5, \
            f"Expected at least 5 aria-hidden='true' attributes, found {aria_hidden_count}"


class TestAllComponentsAccessibility:
    """General accessibility tests across all components."""

    def test_all_components_exist(self):
        """All required components should exist."""
        components = [
            "DynamicAgentCard.tsx",
            "EventTimeline.tsx",
            "RunInspector.tsx",
            "TurnsProgressBar.tsx",
            "ArtifactList.tsx",
        ]
        for component in components:
            component_path = UI_COMPONENTS_PATH / component
            assert component_path.exists(), f"Component {component} should exist"

    def test_no_empty_aria_labels(self):
        """There should be no empty aria-labels."""
        components = [
            "DynamicAgentCard.tsx",
            "EventTimeline.tsx",
            "RunInspector.tsx",
            "TurnsProgressBar.tsx",
            "ArtifactList.tsx",
        ]
        for component in components:
            component_path = UI_COMPONENTS_PATH / component
            content = component_path.read_text()
            assert 'aria-label=""' not in content, \
                f"Component {component} should not have empty aria-label"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
