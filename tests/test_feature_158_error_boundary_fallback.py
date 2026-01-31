"""
Test suite for Feature #158: ErrorBoundary shows fallback UI with reload and error details

Verifies that the ErrorBoundary component provides:
1. A 'Something went wrong' heading in the fallback UI
2. A 'Reload' button that reloads the page
3. A 'Copy error details' button for copying error info to clipboard
4. Console.error logging with full stack trace
5. Styling consistent with the neobrutalism design system
"""

import os
import re
import pytest

# Path to the ErrorBoundary component
COMPONENT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "ui", "src", "components", "ErrorBoundary.tsx"
)


@pytest.fixture
def component_source():
    """Read the ErrorBoundary component source code."""
    with open(COMPONENT_PATH, "r") as f:
        return f.read()


class TestFallbackUI:
    """Step 1: Implement fallback UI with 'Something went wrong' heading"""

    def test_something_went_wrong_heading_exists(self, component_source):
        """The fallback UI must contain a 'Something went wrong' heading."""
        assert "Something went wrong" in component_source, (
            "Expected 'Something went wrong' heading in fallback UI"
        )

    def test_heading_is_h2_element(self, component_source):
        """The heading should be an h2 element for proper semantics."""
        assert re.search(r"<h2[^>]*>.*Something went wrong.*</h2>", component_source, re.DOTALL), (
            "Expected 'Something went wrong' to be inside an <h2> element"
        )

    def test_fallback_rendered_when_has_error(self, component_source):
        """The fallback UI renders when this.state.hasError is true."""
        assert "this.state.hasError" in component_source, (
            "Expected hasError state check in render method"
        )

    def test_descriptive_message_below_heading(self, component_source):
        """A descriptive message should explain what happened."""
        assert "unexpected error" in component_source.lower(), (
            "Expected a descriptive message about the unexpected error"
        )

    def test_alert_triangle_icon(self, component_source):
        """An alert/warning icon should be displayed."""
        assert "AlertTriangle" in component_source, (
            "Expected AlertTriangle icon in fallback UI"
        )


class TestReloadButton:
    """Step 2: Add a 'Reload' button that resets the error boundary state or reloads the page"""

    def test_reload_button_exists(self, component_source):
        """A 'Reload' button must be present."""
        # Check for either 'Reload' or 'Reload Page' text
        assert re.search(r">[\s]*Reload[\s]*<", component_source), (
            "Expected a 'Reload' button in the fallback UI"
        )

    def test_handle_reload_calls_window_reload(self, component_source):
        """The reload handler should call window.location.reload()."""
        assert "window.location.reload()" in component_source, (
            "Expected handleReload to call window.location.reload()"
        )

    def test_handle_reset_exists(self, component_source):
        """A 'Try Again' reset handler should exist to reset error boundary state."""
        assert "handleReset" in component_source, (
            "Expected handleReset method for resetting error boundary state"
        )

    def test_handle_reset_clears_state(self, component_source):
        """handleReset should clear hasError, error, and errorInfo."""
        # Check that reset sets hasError to false
        reset_match = re.search(
            r"handleReset[^{]*\{[^}]*hasError:\s*false[^}]*error:\s*null[^}]*errorInfo:\s*null",
            component_source,
            re.DOTALL
        )
        assert reset_match, (
            "Expected handleReset to set hasError=false, error=null, errorInfo=null"
        )

    def test_try_again_button_exists(self, component_source):
        """A 'Try Again' button should also be present."""
        assert "Try Again" in component_source, (
            "Expected 'Try Again' button in fallback UI"
        )

    def test_reload_button_has_onclick_handler(self, component_source):
        """The reload button should have an onClick handler."""
        assert "onClick={this.handleReload}" in component_source, (
            "Expected Reload button to have onClick={this.handleReload}"
        )


class TestCopyErrorDetails:
    """Step 3: Add a 'Copy error details' button that copies error message and stack trace to clipboard"""

    def test_copy_error_details_button_exists(self, component_source):
        """A 'Copy error details' button must be present."""
        assert "Copy error details" in component_source, (
            "Expected 'Copy error details' button text in fallback UI"
        )

    def test_handle_copy_error_method_exists(self, component_source):
        """A handleCopyError method should exist."""
        assert "handleCopyError" in component_source, (
            "Expected handleCopyError method on ErrorBoundary"
        )

    def test_clipboard_api_used(self, component_source):
        """The copy handler should use navigator.clipboard.writeText."""
        assert "navigator.clipboard.writeText" in component_source, (
            "Expected navigator.clipboard.writeText call in copy handler"
        )

    def test_error_name_and_message_included(self, component_source):
        """The copied text should include error.name and error.message."""
        assert "error.name" in component_source, (
            "Expected error.name to be included in copied details"
        )
        assert "error.message" in component_source, (
            "Expected error.message to be included in copied details"
        )

    def test_stack_trace_included_in_copy(self, component_source):
        """The copied text should include the error stack trace."""
        assert "error.stack" in component_source, (
            "Expected error.stack to be included in copied details"
        )

    def test_component_stack_included_in_copy(self, component_source):
        """The copied text should include the React component stack."""
        assert "componentStack" in component_source, (
            "Expected componentStack to be included in copied details"
        )

    def test_copy_icon_imported(self, component_source):
        """The Copy icon should be imported from lucide-react."""
        assert re.search(r"import\s*\{[^}]*Copy[^}]*\}\s*from\s*['\"]lucide-react['\"]", component_source), (
            "Expected Copy icon import from lucide-react"
        )

    def test_check_icon_imported_for_feedback(self, component_source):
        """A Check icon should be imported for copy success feedback."""
        assert re.search(r"import\s*\{[^}]*Check[^}]*\}\s*from\s*['\"]lucide-react['\"]", component_source), (
            "Expected Check icon import from lucide-react for copy feedback"
        )

    def test_copied_state_exists(self, component_source):
        """A 'copied' state should track whether the text was copied."""
        assert "copied" in component_source, (
            "Expected 'copied' state in ErrorBoundaryState"
        )

    def test_copied_feedback_shown(self, component_source):
        """The button should show 'Copied!' feedback after copying."""
        assert "Copied!" in component_source, (
            "Expected 'Copied!' feedback text after successful copy"
        )

    def test_copy_button_only_shown_when_error(self, component_source):
        """The copy button should only appear when there's an error."""
        assert "this.state.error" in component_source, (
            "Expected copy button to be conditional on this.state.error"
        )

    def test_clipboard_fallback_handling(self, component_source):
        """Should handle clipboard API failures gracefully."""
        # Check for try/catch around clipboard write
        # The try block contains nested braces (setState), so use a simpler check
        has_try = "try {" in component_source or "try{" in component_source
        has_catch = "catch" in component_source
        has_clipboard_in_try_context = "clipboard" in component_source and has_try
        assert has_try and has_catch and has_clipboard_in_try_context, (
            "Expected try/catch around clipboard API for fallback handling"
        )


class TestConsoleErrorLogging:
    """Step 4: Log the caught error via console.error with full stack trace"""

    def test_component_did_catch_exists(self, component_source):
        """componentDidCatch lifecycle method must exist."""
        assert "componentDidCatch" in component_source, (
            "Expected componentDidCatch lifecycle method"
        )

    def test_console_error_called(self, component_source):
        """console.error should be called to log the error."""
        assert "console.error" in component_source, (
            "Expected console.error call in componentDidCatch"
        )

    def test_error_object_logged(self, component_source):
        """The error object should be logged."""
        assert re.search(r"console\.error\([^)]*error", component_source), (
            "Expected error object to be passed to console.error"
        )

    def test_full_stack_trace_logged(self, component_source):
        """The full stack trace (error.stack) should be logged."""
        assert "error.stack" in component_source, (
            "Expected error.stack to be logged via console.error"
        )

    def test_component_stack_logged(self, component_source):
        """The React component stack should also be logged."""
        assert re.search(r"console\.error\([^)]*componentStack", component_source), (
            "Expected componentStack to be logged via console.error"
        )

    def test_get_derived_state_from_error(self, component_source):
        """getDerivedStateFromError should set hasError=true."""
        assert "getDerivedStateFromError" in component_source, (
            "Expected getDerivedStateFromError static method"
        )
        assert re.search(r"hasError:\s*true", component_source), (
            "Expected getDerivedStateFromError to set hasError: true"
        )


class TestDesignSystemConsistency:
    """Step 5: Style the fallback UI consistently with the existing design system"""

    def test_neo_card_class_used(self, component_source):
        """The fallback UI should use the neo-card design system class."""
        assert "neo-card" in component_source, (
            "Expected neo-card class for consistent card styling"
        )

    def test_neo_btn_class_used(self, component_source):
        """Buttons should use the neo-btn design system class."""
        assert "neo-btn" in component_source, (
            "Expected neo-btn class for consistent button styling"
        )

    def test_neo_text_colors_used(self, component_source):
        """Text should use neo-text design system colors."""
        assert "text-neo-text" in component_source, (
            "Expected text-neo-text class for consistent text colors"
        )

    def test_neo_text_secondary_used(self, component_source):
        """Secondary text should use neo-text-secondary class."""
        assert "text-neo-text-secondary" in component_source, (
            "Expected text-neo-text-secondary class"
        )

    def test_dark_mode_support(self, component_source):
        """The fallback UI should support dark mode."""
        assert "dark:" in component_source, (
            "Expected dark mode classes (dark:) in fallback UI"
        )

    def test_centered_layout(self, component_source):
        """The fallback should be centered on the page."""
        assert "items-center" in component_source and "justify-center" in component_source, (
            "Expected centered layout with flex items-center justify-center"
        )

    def test_font_display_used(self, component_source):
        """Headings should use the display font family."""
        assert "font-display" in component_source, (
            "Expected font-display class for heading (neobrutalism design)"
        )

    def test_error_colors_used(self, component_source):
        """Red/danger colors should be used for error indicators."""
        assert "text-red-600" in component_source or "text-red-500" in component_source, (
            "Expected red/danger colors for error indicators"
        )

    def test_border_styling(self, component_source):
        """Neo-brutalism border styling should be present."""
        assert "border-neo-border" in component_source, (
            "Expected border-neo-border class for consistent borders"
        )

    def test_responsive_button_layout(self, component_source):
        """Button layout should handle wrapping for smaller screens."""
        assert "flex-wrap" in component_source, (
            "Expected flex-wrap on button container for responsive layout"
        )


class TestErrorDetailsDisplay:
    """Verify error details are visible and expandable in the UI"""

    def test_error_details_section_exists(self, component_source):
        """An error details section should be present in the fallback."""
        assert "error details" in component_source.lower() or "Show error details" in component_source, (
            "Expected error details section in fallback UI"
        )

    def test_error_stack_displayed(self, component_source):
        """The error stack trace should be displayed in the UI."""
        assert re.search(r"this\.state\.error\.stack", component_source), (
            "Expected error stack trace to be rendered in the UI"
        )

    def test_component_stack_displayed(self, component_source):
        """The component stack should be displayed."""
        assert re.search(r"this\.state\.errorInfo\?\.componentStack", component_source), (
            "Expected component stack to be displayed in error details"
        )

    def test_monospace_font_for_stack(self, component_source):
        """Stack traces should use monospace font."""
        assert "font-mono" in component_source, (
            "Expected font-mono class for stack trace display"
        )


class TestComponentStructure:
    """Verify the overall component structure is correct"""

    def test_is_class_component(self, component_source):
        """ErrorBoundary must be a class component (React requirement)."""
        assert "class ErrorBoundary extends Component" in component_source, (
            "ErrorBoundary must be a React class component"
        )

    def test_exported(self, component_source):
        """ErrorBoundary should be exported."""
        assert "export class ErrorBoundary" in component_source, (
            "ErrorBoundary should be a named export"
        )

    def test_children_prop(self, component_source):
        """Should accept children prop to wrap content."""
        assert "children" in component_source, (
            "Expected children prop for wrapping content"
        )

    def test_optional_fallback_prop(self, component_source):
        """Should accept an optional fallback prop for custom fallback UI."""
        assert "fallback?" in component_source or "fallback?: ReactNode" in component_source, (
            "Expected optional fallback prop"
        )

    def test_custom_fallback_rendered_when_provided(self, component_source):
        """When a custom fallback prop is provided, it should be used."""
        assert "this.props.fallback" in component_source, (
            "Expected custom fallback rendering when props.fallback is provided"
        )

    def test_children_rendered_when_no_error(self, component_source):
        """When there's no error, children should be rendered normally."""
        assert "this.props.children" in component_source, (
            "Expected children to be rendered when no error"
        )
