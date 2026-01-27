"""
Test suite for Feature #73: Error Display in Agent Card

This test suite verifies the ErrorDisplay component implementation
in DynamicAgentCard.tsx through code inspection and unit tests.

Feature Requirements:
1. Check run.status === failed or timeout
2. Display error icon in card
3. Show truncated error message (first 100 chars)
4. Add View Details link to open inspector
5. Style with error colors
"""

import re
from pathlib import Path


class TestFeature73ErrorDisplay:
    """Test suite for Error Display in Agent Card (Feature #73)"""

    @classmethod
    def setup_class(cls):
        """Load the DynamicAgentCard.tsx file for inspection"""
        component_path = Path(__file__).parent.parent / "ui" / "src" / "components" / "DynamicAgentCard.tsx"
        cls.component_code = component_path.read_text()

    # =========================================================================
    # Step 1: Check run.status === failed or timeout
    # =========================================================================

    def test_step1_checks_failed_status(self):
        """ErrorDisplay checks for status === 'failed'"""
        assert "status === 'failed'" in self.component_code, \
            "Should check for failed status"

    def test_step1_checks_timeout_status(self):
        """ErrorDisplay checks for status === 'timeout'"""
        assert "status === 'timeout'" in self.component_code, \
            "Should check for timeout status"

    def test_step1_error_status_condition(self):
        """ErrorDisplay has combined error status condition"""
        # Check for the condition that combines both statuses
        assert "const isErrorStatus = status === 'failed' || status === 'timeout'" in self.component_code, \
            "Should have combined error status check"

    def test_step1_returns_null_for_non_error_status(self):
        """ErrorDisplay returns null when status is not error"""
        assert "if (!isErrorStatus) return null" in self.component_code, \
            "Should return null for non-error statuses"

    # =========================================================================
    # Step 2: Display error icon in card
    # =========================================================================

    def test_step2_imports_alert_circle_icon(self):
        """ErrorDisplay imports AlertCircle icon for failed status"""
        assert "AlertCircle" in self.component_code, \
            "Should import AlertCircle icon"

    def test_step2_imports_timer_icon(self):
        """ErrorDisplay imports Timer icon for timeout status"""
        assert "Timer" in self.component_code, \
            "Should import Timer icon"

    def test_step2_uses_appropriate_icon_for_timeout(self):
        """ErrorDisplay uses Timer icon for timeout status"""
        assert "const ErrorIcon = isTimeout ? Timer : AlertCircle" in self.component_code, \
            "Should select Timer icon for timeout, AlertCircle for failed"

    def test_step2_renders_error_icon(self):
        """ErrorDisplay renders the selected icon"""
        assert "<ErrorIcon" in self.component_code, \
            "Should render ErrorIcon component"

    # =========================================================================
    # Step 3: Show truncated error message (first 100 chars)
    # =========================================================================

    def test_step3_truncate_error_function_exists(self):
        """truncateError function is defined"""
        assert "function truncateError" in self.component_code, \
            "Should have truncateError function"

    def test_step3_truncate_max_length_default_100(self):
        """truncateError defaults to 100 characters"""
        assert "maxLength: number = 100" in self.component_code, \
            "Should default to 100 character max length"

    def test_step3_truncate_adds_ellipsis(self):
        """truncateError adds ellipsis when truncating"""
        assert "error.slice(0, maxLength) + '...'" in self.component_code, \
            "Should add ellipsis when truncating"

    def test_step3_truncate_returns_truncated_and_flag(self):
        """truncateError returns both truncated text and wasLong flag"""
        assert "{ truncated: string; wasLong: boolean }" in self.component_code, \
            "Should return object with truncated and wasLong properties"

    def test_step3_uses_truncate_function(self):
        """ErrorDisplay uses truncateError to truncate messages"""
        assert "truncateError(errorMessage)" in self.component_code, \
            "Should call truncateError with error message"

    def test_step3_shows_truncated_message(self):
        """ErrorDisplay renders the truncated message"""
        assert "{truncated}" in self.component_code, \
            "Should render truncated message"

    def test_step3_shows_full_message_on_hover(self):
        """ErrorDisplay shows full message in title when truncated"""
        assert "title={wasLong ? errorMessage : undefined}" in self.component_code, \
            "Should show full message in title when truncated"

    # =========================================================================
    # Step 4: Add View Details link to open inspector
    # =========================================================================

    def test_step4_imports_external_link_icon(self):
        """ErrorDisplay imports ExternalLink icon"""
        assert "ExternalLink" in self.component_code, \
            "Should import ExternalLink icon"

    def test_step4_has_view_details_button(self):
        """ErrorDisplay has View Details button"""
        assert "View Details" in self.component_code, \
            "Should have 'View Details' text"

    def test_step4_view_details_has_onclick(self):
        """View Details button has onClick handler"""
        assert "onClick={handleViewDetails}" in self.component_code, \
            "Should have handleViewDetails onClick"

    def test_step4_handle_view_details_calls_onclick_prop(self):
        """handleViewDetails calls the onClick prop"""
        assert "onClick?.()" in self.component_code, \
            "Should call onClick prop to open inspector"

    def test_step4_stop_propagation(self):
        """handleViewDetails stops event propagation"""
        assert "e.stopPropagation()" in self.component_code, \
            "Should stop propagation to prevent card click"

    def test_step4_has_aria_label(self):
        """View Details button has accessibility label"""
        assert 'aria-label="View error details in inspector"' in self.component_code, \
            "Should have aria-label for accessibility"

    def test_step4_has_test_id(self):
        """View Details button has test ID"""
        assert 'data-testid="view-details-link"' in self.component_code, \
            "Should have data-testid for testing"

    # =========================================================================
    # Step 5: Style with error colors
    # =========================================================================

    def test_step5_uses_failed_colors_for_failed_status(self):
        """ErrorDisplay uses failed colors for failed status"""
        assert "var(--color-status-failed-bg)" in self.component_code, \
            "Should use failed background color"
        assert "var(--color-status-failed-text)" in self.component_code, \
            "Should use failed text color"

    def test_step5_uses_timeout_colors_for_timeout_status(self):
        """ErrorDisplay uses timeout colors for timeout status"""
        assert "var(--color-status-timeout-bg)" in self.component_code, \
            "Should use timeout background color"
        assert "var(--color-status-timeout-text)" in self.component_code, \
            "Should use timeout text color"

    def test_step5_conditional_color_based_on_status(self):
        """ErrorDisplay conditionally applies colors based on status"""
        assert "isTimeout ? 'bg-[var(--color-status-timeout-bg)]' : 'bg-[var(--color-status-failed-bg)]'" in self.component_code, \
            "Should conditionally apply background color"
        assert "isTimeout ? 'text-[var(--color-status-timeout-text)]' : 'text-[var(--color-status-failed-text)]'" in self.component_code, \
            "Should conditionally apply text color"

    def test_step5_has_rounded_corners(self):
        """ErrorDisplay has rounded corners"""
        assert "rounded" in self.component_code and "mt-2 p-2" in self.component_code, \
            "Should have rounded corners and padding"

    # =========================================================================
    # Additional Integration Tests
    # =========================================================================

    def test_error_display_component_exported(self):
        """ErrorDisplay component is exported"""
        assert "export { getStatusIcon, getStatusLabel, StatusBadge, ValidatorStatusIndicators, ErrorDisplay, truncateError }" in self.component_code, \
            "Should export ErrorDisplay component"

    def test_error_display_used_in_dynamic_agent_card(self):
        """ErrorDisplay is used in DynamicAgentCard"""
        assert "<ErrorDisplay status={status} error={run.error} onClick={onClick} />" in self.component_code, \
            "Should use ErrorDisplay in DynamicAgentCard"

    def test_error_display_receives_status_prop(self):
        """ErrorDisplay receives status prop"""
        assert "status: AgentRunStatus" in self.component_code, \
            "Should have status prop of type AgentRunStatus"

    def test_error_display_receives_error_prop(self):
        """ErrorDisplay receives error prop"""
        assert "error: string | null" in self.component_code, \
            "Should have error prop that can be null"

    def test_error_display_receives_onclick_prop(self):
        """ErrorDisplay receives optional onClick prop"""
        assert "onClick?: () => void" in self.component_code, \
            "Should have optional onClick prop"

    def test_default_timeout_message(self):
        """ErrorDisplay shows default message for timeout without error"""
        assert "Execution timed out" in self.component_code, \
            "Should show default timeout message"

    def test_default_failed_message(self):
        """ErrorDisplay shows default message for failed without error"""
        assert "Unknown error" in self.component_code, \
            "Should show default error message"

    def test_error_display_has_test_id(self):
        """ErrorDisplay has test ID for main container"""
        assert 'data-testid="error-display"' in self.component_code, \
            "Should have data-testid on main container"


class TestTruncateErrorFunction:
    """Test the truncateError function logic"""

    @classmethod
    def setup_class(cls):
        """Load the DynamicAgentCard.tsx file for inspection"""
        component_path = Path(__file__).parent.parent / "ui" / "src" / "components" / "DynamicAgentCard.tsx"
        cls.component_code = component_path.read_text()

    def test_short_message_not_truncated(self):
        """Short messages should not be truncated"""
        # Check the logic: if (error.length <= maxLength)
        assert "if (error.length <= maxLength)" in self.component_code, \
            "Should check if message is short enough"
        assert "return { truncated: error, wasLong: false }" in self.component_code, \
            "Should return original message with wasLong: false for short messages"

    def test_long_message_truncated_with_ellipsis(self):
        """Long messages should be truncated with ellipsis"""
        assert "return { truncated: error.slice(0, maxLength) + '...', wasLong: true }" in self.component_code, \
            "Should return truncated message with ellipsis and wasLong: true"


class TestErrorDisplayProps:
    """Test ErrorDisplay props interface"""

    @classmethod
    def setup_class(cls):
        """Load the DynamicAgentCard.tsx file for inspection"""
        component_path = Path(__file__).parent.parent / "ui" / "src" / "components" / "DynamicAgentCard.tsx"
        cls.component_code = component_path.read_text()

    def test_interface_exists(self):
        """ErrorDisplayProps interface is defined"""
        assert "interface ErrorDisplayProps" in self.component_code, \
            "Should have ErrorDisplayProps interface"

    def test_status_prop_required(self):
        """status prop is required"""
        # status: AgentRunStatus (no ?)
        assert re.search(r"status:\s*AgentRunStatus[^?]", self.component_code), \
            "status prop should be required"

    def test_error_prop_nullable(self):
        """error prop accepts null"""
        assert "error: string | null" in self.component_code, \
            "error prop should accept string or null"

    def test_onclick_prop_optional(self):
        """onClick prop is optional"""
        assert "onClick?: () => void" in self.component_code, \
            "onClick prop should be optional"


def run_verification():
    """Run verification and print results"""
    import sys

    print("=" * 60)
    print("Feature #73: Error Display in Agent Card - Verification")
    print("=" * 60)
    print()

    # Load component code
    component_path = Path(__file__).parent.parent / "ui" / "src" / "components" / "DynamicAgentCard.tsx"
    if not component_path.exists():
        print(f"[FAIL] Component file not found: {component_path}")
        return False

    component_code = component_path.read_text()

    steps = [
        {
            "name": "Step 1: Check run.status === failed or timeout",
            "checks": [
                ("Failed status check", "status === 'failed'" in component_code),
                ("Timeout status check", "status === 'timeout'" in component_code),
                ("Combined check", "const isErrorStatus = status === 'failed' || status === 'timeout'" in component_code),
                ("Returns null for non-error", "if (!isErrorStatus) return null" in component_code),
            ]
        },
        {
            "name": "Step 2: Display error icon in card",
            "checks": [
                ("AlertCircle imported", "AlertCircle" in component_code),
                ("Timer imported", "Timer" in component_code),
                ("Icon selection logic", "const ErrorIcon = isTimeout ? Timer : AlertCircle" in component_code),
                ("Icon rendered", "<ErrorIcon" in component_code),
            ]
        },
        {
            "name": "Step 3: Show truncated error message (first 100 chars)",
            "checks": [
                ("truncateError function", "function truncateError" in component_code),
                ("100 char default", "maxLength: number = 100" in component_code),
                ("Ellipsis added", "error.slice(0, maxLength) + '...'" in component_code),
                ("Return type correct", "{ truncated: string; wasLong: boolean }" in component_code),
                ("Function used", "truncateError(errorMessage)" in component_code),
            ]
        },
        {
            "name": "Step 4: Add View Details link to open inspector",
            "checks": [
                ("ExternalLink imported", "ExternalLink" in component_code),
                ("View Details text", "View Details" in component_code),
                ("handleViewDetails handler", "onClick={handleViewDetails}" in component_code),
                ("Stop propagation", "e.stopPropagation()" in component_code),
                ("Aria label", 'aria-label="View error details in inspector"' in component_code),
            ]
        },
        {
            "name": "Step 5: Style with error colors",
            "checks": [
                ("Failed background", "var(--color-status-failed-bg)" in component_code),
                ("Failed text", "var(--color-status-failed-text)" in component_code),
                ("Timeout background", "var(--color-status-timeout-bg)" in component_code),
                ("Timeout text", "var(--color-status-timeout-text)" in component_code),
                ("Conditional bg color", "isTimeout ? 'bg-[var(--color-status-timeout-bg)]'" in component_code),
            ]
        }
    ]

    all_passed = True
    for step in steps:
        print(f"\n{step['name']}")
        print("-" * len(step['name']))
        step_passed = True
        for check_name, passed in step['checks']:
            status = "[PASS]" if passed else "[FAIL]"
            print(f"  {status} {check_name}")
            if not passed:
                step_passed = False
                all_passed = False
        if step_passed:
            print(f"  --> Step PASSED")
        else:
            print(f"  --> Step FAILED")

    print()
    print("=" * 60)
    if all_passed:
        print("OVERALL RESULT: ALL STEPS PASSED")
    else:
        print("OVERALL RESULT: SOME STEPS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    import sys
    success = run_verification()
    sys.exit(0 if success else 1)
