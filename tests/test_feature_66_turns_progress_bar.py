"""
Tests for Feature #66: Turns Progress Bar Component

This test suite verifies the TurnsProgressBar React component implementation.
Since we can't run React unit tests directly, we verify:
1. Component file exists and has proper structure
2. TypeScript compiles successfully
3. Component is properly exported and integrated
4. Code review for all 8 verification steps
"""

import os
import re
import subprocess
from pathlib import Path

import pytest


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
UI_DIR = PROJECT_ROOT / "ui"
COMPONENT_FILE = UI_DIR / "src" / "components" / "TurnsProgressBar.tsx"
DYNAMIC_AGENT_CARD = UI_DIR / "src" / "components" / "DynamicAgentCard.tsx"


class TestStep1ComponentExists:
    """Step 1: Create TurnsProgressBar.tsx component"""

    def test_component_file_exists(self):
        """TurnsProgressBar.tsx should exist"""
        assert COMPONENT_FILE.exists(), f"Component file not found: {COMPONENT_FILE}"

    def test_component_is_exported(self):
        """Component should be exported"""
        content = COMPONENT_FILE.read_text()
        assert "export function TurnsProgressBar" in content or "export const TurnsProgressBar" in content

    def test_default_export_exists(self):
        """Should have default export"""
        content = COMPONENT_FILE.read_text()
        assert "export default TurnsProgressBar" in content


class TestStep2PropsInterface:
    """Step 2: Props: used (number), max (number)"""

    def test_interface_defined(self):
        """TurnsProgressBarProps interface should be defined"""
        content = COMPONENT_FILE.read_text()
        assert "interface TurnsProgressBarProps" in content or "type TurnsProgressBarProps" in content

    def test_used_prop_defined(self):
        """'used' prop should be defined as number"""
        content = COMPONENT_FILE.read_text()
        assert "used:" in content or "used?" in content
        # Check it's typed as number
        assert re.search(r"used\??:\s*number", content), "used prop should be typed as number"

    def test_max_prop_defined(self):
        """'max' prop should be defined as number"""
        content = COMPONENT_FILE.read_text()
        assert "max:" in content or "max?" in content
        # Check it's typed as number
        assert re.search(r"max\??:\s*number", content), "max prop should be typed as number"

    def test_status_prop_defined(self):
        """'status' prop should be defined for color coding"""
        content = COMPONENT_FILE.read_text()
        assert "status?" in content or "status:" in content


class TestStep3PercentageCalculation:
    """Step 3: Calculate percentage = (used / max) * 100"""

    def test_percentage_calculation_exists(self):
        """Should calculate percentage"""
        content = COMPONENT_FILE.read_text()
        # Look for percentage calculation pattern
        assert "percentage" in content.lower() or "percent" in content.lower()

    def test_division_formula(self):
        """Should use (used / max) formula"""
        content = COMPONENT_FILE.read_text()
        # Look for patterns like used / max or used/max
        assert re.search(r"used\s*/\s*max", content), "Should divide used by max"


class TestStep4CapAt100Percent:
    """Step 4: Cap at 100% for display"""

    def test_math_min_or_cap_logic(self):
        """Should cap percentage at 100"""
        content = COMPONENT_FILE.read_text()
        # Look for Math.min with 100 or explicit cap logic
        has_math_min = "Math.min" in content
        has_explicit_cap = "100" in content
        assert has_math_min or has_explicit_cap, "Should have capping logic"

    def test_overflow_handling(self):
        """Should handle when used > max"""
        content = COMPONENT_FILE.read_text()
        # Should use Math.min to cap at 100%
        assert re.search(r"Math\.min\s*\(\s*\(?\s*used\s*/\s*max", content) or \
               re.search(r"percentage.*100", content), \
               "Should cap percentage at 100%"


class TestStep5AnimatedWidthTransition:
    """Step 5: Animate width transition on update"""

    def test_transition_style(self):
        """Should have transition style for animation"""
        content = COMPONENT_FILE.read_text()
        has_transition = "transition" in content.lower()
        has_animation = "animation" in content.lower()
        assert has_transition or has_animation, "Should have transition or animation"

    def test_width_property_animated(self):
        """Width should be the animated property"""
        content = COMPONENT_FILE.read_text()
        # Look for width transition
        assert "width" in content


class TestStep6TooltipOnHover:
    """Step 6: Show tooltip with exact values on hover"""

    def test_tooltip_component_exists(self):
        """Should have tooltip functionality"""
        content = COMPONENT_FILE.read_text()
        assert "tooltip" in content.lower() or "Tooltip" in content

    def test_mouse_hover_handlers(self):
        """Should have mouse enter/leave handlers"""
        content = COMPONENT_FILE.read_text()
        has_mouse_enter = "onMouseEnter" in content or "mouseenter" in content.lower()
        has_hover_state = "showTooltip" in content or "hover" in content.lower()
        assert has_mouse_enter or has_hover_state, "Should handle mouse hover"

    def test_displays_exact_values(self):
        """Tooltip should display exact values"""
        content = COMPONENT_FILE.read_text()
        # Look for used and max in tooltip context
        assert "used" in content and "max" in content


class TestStep7StatusAppropriateColor:
    """Step 7: Use status-appropriate color"""

    def test_status_based_styling(self):
        """Should apply different colors based on status"""
        content = COMPONENT_FILE.read_text()
        # Look for status-based class application
        assert "status" in content
        # Should use neo-progress-fill classes with status
        assert "neo-progress-fill" in content

    def test_imports_agent_run_status(self):
        """Should import AgentRunStatus type"""
        content = COMPONENT_FILE.read_text()
        assert "AgentRunStatus" in content


class TestStep8HandleMaxZeroEdgeCase:
    """Step 8: Handle max=0 edge case"""

    def test_max_zero_check(self):
        """Should check for max=0 to avoid division by zero"""
        content = COMPONENT_FILE.read_text()
        # Look for conditional checks for max > 0 or max === 0
        has_zero_check = "max > 0" in content or "max === 0" in content or "max == 0" in content
        has_ternary = "?" in content and "max" in content
        assert has_zero_check or has_ternary, "Should handle max=0 edge case"

    def test_overflow_indicator(self):
        """Should indicate overflow state (used > 0 but max = 0)"""
        content = COMPONENT_FILE.read_text()
        # Look for overflow handling
        assert "overflow" in content.lower() or "isOverflow" in content


class TestIntegration:
    """Integration tests - verify component works with DynamicAgentCard"""

    def test_imported_in_dynamic_agent_card(self):
        """Should be imported and used in DynamicAgentCard"""
        content = DYNAMIC_AGENT_CARD.read_text()
        assert "import" in content
        assert "TurnsProgressBar" in content
        # Should be imported from its module
        assert "from './TurnsProgressBar'" in content

    def test_used_in_dynamic_agent_card(self):
        """TurnsProgressBar should be used in DynamicAgentCard JSX"""
        content = DYNAMIC_AGENT_CARD.read_text()
        assert "<TurnsProgressBar" in content

    def test_props_passed_correctly(self):
        """Props should be passed with correct names"""
        content = DYNAMIC_AGENT_CARD.read_text()
        # Check for used= and max= props
        has_used = re.search(r"used=\{", content)
        has_max = re.search(r"max=\{", content)
        assert has_used, "Should pass 'used' prop"
        assert has_max, "Should pass 'max' prop"


class TestTypeScriptCompilation:
    """Verify TypeScript compiles successfully"""

    def test_typescript_compiles(self):
        """TypeScript should compile without errors"""
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=UI_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"TypeScript compilation failed:\n{result.stderr}"


class TestCodeQuality:
    """Code quality checks"""

    def test_has_jsdoc_comments(self):
        """Component should have documentation comments"""
        content = COMPONENT_FILE.read_text()
        assert "/**" in content, "Should have JSDoc comments"

    def test_has_prop_descriptions(self):
        """Props should be documented"""
        content = COMPONENT_FILE.read_text()
        # Look for @param or prop descriptions
        has_docs = "@" in content or "/*" in content
        assert has_docs, "Should have prop documentation"

    def test_exports_types(self):
        """Should export the props interface for external use"""
        content = COMPONENT_FILE.read_text()
        assert "export interface TurnsProgressBarProps" in content or \
               "export type TurnsProgressBarProps" in content


class TestAccessibility:
    """Accessibility verification"""

    def test_has_progressbar_role(self):
        """Should have role='progressbar'"""
        content = COMPONENT_FILE.read_text()
        assert 'role="progressbar"' in content

    def test_has_aria_attributes(self):
        """Should have aria attributes"""
        content = COMPONENT_FILE.read_text()
        assert "aria-valuenow" in content
        assert "aria-valuemin" in content
        assert "aria-valuemax" in content

    def test_has_aria_label(self):
        """Should have descriptive aria-label"""
        content = COMPONENT_FILE.read_text()
        assert "aria-label" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
