"""
Feature #72: Agent Thinking State Animation
Tests for animated thinking indicator in DynamicAgentCard showing current activity state.

Feature Steps:
1. Define thinking states: thinking, coding, testing, validating
2. Add animated indicator to card header
3. Pulse animation while waiting for response
4. Update state based on latest event type
5. tool_call -> working (coding)
6. turn_complete -> thinking
7. acceptance_check -> validating
"""

import pytest
import subprocess
import re


class TestThinkingStateType:
    """Test that ThinkingState type is properly defined in types.ts"""

    def test_thinking_state_type_exists(self):
        """Step 1: ThinkingState type should be defined with all required states"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/lib/types.ts', 'r') as f:
            content = f.read()

        # Check ThinkingState type exists
        assert "export type ThinkingState" in content, "ThinkingState type should be exported"

        # Check all states are defined
        assert "'idle'" in content, "ThinkingState should include 'idle'"
        assert "'thinking'" in content, "ThinkingState should include 'thinking'"
        assert "'coding'" in content, "ThinkingState should include 'coding'"
        assert "'testing'" in content, "ThinkingState should include 'testing'"
        assert "'validating'" in content, "ThinkingState should include 'validating'"

    def test_thinking_state_has_correct_values(self):
        """Verify ThinkingState has exactly the expected values"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/lib/types.ts', 'r') as f:
            content = f.read()

        # Match the type definition
        match = re.search(r"export type ThinkingState = (.+)", content)
        assert match, "ThinkingState type definition should be found"

        type_def = match.group(1)
        # Should contain all 5 states
        for state in ['idle', 'thinking', 'coding', 'testing', 'validating']:
            assert f"'{state}'" in type_def, f"ThinkingState should include '{state}'"


class TestThinkingStateIndicatorComponent:
    """Test the ThinkingStateIndicator component in DynamicAgentCard.tsx"""

    def test_thinking_state_indicator_component_exists(self):
        """Step 2: ThinkingStateIndicator component should exist"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "ThinkingStateIndicator" in content, "ThinkingStateIndicator component should exist"
        assert "export function ThinkingStateIndicator" in content, "ThinkingStateIndicator should be exported"

    def test_indicator_has_accessibility_attributes(self):
        """Indicator should have proper accessibility attributes"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        # Check for accessibility attributes
        assert 'role="status"' in content, "Indicator should have role=status"
        assert 'aria-live="polite"' in content, "Indicator should have aria-live=polite"
        assert 'aria-label={label}' in content, "Indicator should have aria-label"

    def test_indicator_has_testid(self):
        """Indicator should have data-testid for testing"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert 'data-testid="thinking-state-indicator"' in content, "Indicator should have data-testid"
        assert 'data-thinking-state={state}' in content, "Indicator should expose state via data attribute"

    def test_indicator_returns_null_when_idle(self):
        """Indicator should return null when state is idle"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "if (state === 'idle')" in content, "Should check for idle state"
        assert "return null" in content, "Should return null for idle state"


class TestPulseAnimation:
    """Test pulse animation for thinking state"""

    def test_pulse_animation_class_exists(self):
        """Step 3: Pulse animation should be applied to the label"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert 'animate-pulse' in content, "animate-pulse class should be used"

    def test_thinking_state_animations_defined_in_css(self):
        """Animation classes should be defined in CSS"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/styles/globals.css', 'r') as f:
            content = f.read()

        # Check for animation keyframes
        assert '@keyframes thinking' in content, "thinking keyframes should be defined"
        assert '@keyframes working' in content, "working keyframes should be defined"
        assert '@keyframes testing' in content, "testing keyframes should be defined"

        # Check for animation utility classes
        assert '.animate-thinking' in content, "animate-thinking class should be defined"
        assert '.animate-working' in content, "animate-working class should be defined"
        assert '.animate-testing' in content, "animate-testing class should be defined"


class TestDeriveThinkingStateFunction:
    """Test the deriveThinkingState function mapping event types to states"""

    def test_derive_thinking_state_function_exists(self):
        """Step 4: deriveThinkingState function should exist"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "export function deriveThinkingState" in content, "deriveThinkingState should be exported"

    def test_returns_idle_when_not_running(self):
        """Should return 'idle' when status is not 'running'"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        # Check for status check
        assert "if (status !== 'running')" in content, "Should check if status is running"
        assert "return 'idle'" in content, "Should return 'idle' when not running"

    def test_returns_thinking_when_no_event(self):
        """Should return 'thinking' when no event type is provided"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "if (!latestEventType)" in content, "Should check for null/undefined event type"


class TestEventTypeMapping:
    """Test event type to thinking state mappings"""

    def test_tool_call_maps_to_coding(self):
        """Step 5: tool_call event should map to 'coding' state"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "case 'tool_call':" in content, "Should handle tool_call event"
        assert "return 'coding'" in content, "tool_call should return 'coding'"

    def test_tool_result_maps_to_coding(self):
        """tool_result event should also map to 'coding' state"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "case 'tool_result':" in content, "Should handle tool_result event"

    def test_turn_complete_maps_to_thinking(self):
        """Step 6: turn_complete event should map to 'thinking' state"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "case 'turn_complete':" in content, "Should handle turn_complete event"
        assert "return 'thinking'" in content, "turn_complete should return 'thinking'"

    def test_started_maps_to_thinking(self):
        """started event should map to 'thinking' state"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "case 'started':" in content, "Should handle started event"

    def test_acceptance_check_maps_to_validating(self):
        """Step 7: acceptance_check event should map to 'validating' state"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "case 'acceptance_check':" in content, "Should handle acceptance_check event"
        assert "return 'validating'" in content, "acceptance_check should return 'validating'"


class TestThinkingStateLabels:
    """Test that thinking state labels are properly defined"""

    def test_get_thinking_state_label_function_exists(self):
        """getThinkingStateLabel function should exist"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "getThinkingStateLabel" in content, "getThinkingStateLabel function should exist"

    def test_thinking_label(self):
        """'thinking' state should have 'Thinking...' label"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "'Thinking...'" in content, "Should have 'Thinking...' label"

    def test_coding_label(self):
        """'coding' state should have 'Coding...' label"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "'Coding...'" in content, "Should have 'Coding...' label"

    def test_testing_label(self):
        """'testing' state should have 'Testing...' label"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "'Testing...'" in content, "Should have 'Testing...' label"

    def test_validating_label(self):
        """'validating' state should have 'Validating...' label"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "'Validating...'" in content, "Should have 'Validating...' label"


class TestThinkingStateIcons:
    """Test that thinking state icons are properly mapped"""

    def test_icons_imported(self):
        """Required icons should be imported"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "Brain" in content, "Brain icon should be imported"
        assert "Code" in content, "Code icon should be imported"
        assert "TestTube" in content, "TestTube icon should be imported"
        assert "Shield" in content, "Shield icon should be imported"

    def test_get_thinking_state_icon_function_exists(self):
        """getThinkingStateIcon function should exist"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "getThinkingStateIcon" in content, "getThinkingStateIcon function should exist"

    def test_icon_mapping(self):
        """Icons should be properly mapped to states"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "return Brain" in content, "thinking state should return Brain icon"
        assert "return Code" in content, "coding state should return Code icon"
        assert "return TestTube" in content, "testing state should return TestTube icon"
        assert "return Shield" in content, "validating state should return Shield icon"


class TestThinkingStateAnimationClasses:
    """Test that animation classes are properly mapped"""

    def test_get_thinking_state_animation_function_exists(self):
        """getThinkingStateAnimation function should exist"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "getThinkingStateAnimation" in content, "getThinkingStateAnimation function should exist"

    def test_animation_class_mapping(self):
        """Animation classes should be properly mapped to states"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "'animate-thinking'" in content, "thinking state should have animate-thinking class"
        assert "'animate-working'" in content, "coding state should have animate-working class"
        assert "'animate-testing'" in content, "testing state should have animate-testing class"
        assert "'animate-pulse-neo'" in content, "validating state should have animate-pulse-neo class"


class TestDynamicAgentCardIntegration:
    """Test integration of ThinkingStateIndicator in DynamicAgentCard"""

    def test_card_accepts_latest_event_type_prop(self):
        """DynamicAgentCard should accept latestEventType prop"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "latestEventType?: AgentEventType" in content, "Should have latestEventType prop"

    def test_card_uses_derive_thinking_state(self):
        """Card should use deriveThinkingState to get current state"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "deriveThinkingState(latestEventType, status)" in content, "Should call deriveThinkingState"

    def test_card_renders_thinking_state_indicator(self):
        """Card should render ThinkingStateIndicator component"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "<ThinkingStateIndicator state={thinkingState}" in content, "Should render ThinkingStateIndicator"

    def test_indicator_in_header_section(self):
        """Indicator should be in the header/status section"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        # Check that StatusBadge and ThinkingStateIndicator are together
        assert "<StatusBadge" in content and "<ThinkingStateIndicator" in content, "Both components should be rendered"


class TestExports:
    """Test that necessary functions and components are exported"""

    def test_exports(self):
        """Key functions and components should be exported"""
        with open('/home/rudih/workspace/AutoBuildr/ui/src/components/DynamicAgentCard.tsx', 'r') as f:
            content = f.read()

        assert "export function deriveThinkingState" in content, "deriveThinkingState should be exported"
        assert "export function ThinkingStateIndicator" in content, "ThinkingStateIndicator should be exported"


class TestTypeScriptCompilation:
    """Test that the code compiles without TypeScript errors"""

    def test_frontend_builds_successfully(self):
        """Frontend should build without TypeScript errors"""
        result = subprocess.run(
            ['npm', 'run', 'build', '--prefix', '/home/rudih/workspace/AutoBuildr/ui'],
            capture_output=True,
            text=True,
            timeout=120
        )

        # Check for successful build
        assert result.returncode == 0, f"Build failed with output:\n{result.stdout}\n{result.stderr}"
        assert "built in" in result.stdout or "built in" in result.stderr, "Build should complete successfully"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
