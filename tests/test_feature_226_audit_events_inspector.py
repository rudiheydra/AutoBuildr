"""
Test Feature #226: Audit events visible in run inspector

This test verifies that all audit event types are properly configured
in the EventTimeline component for the Run Inspector.

Feature Steps:
1. Run Inspector fetches all event types including new ones
2. New events rendered with appropriate icons and labels
3. Event details expandable to show payload
4. Events filterable by type in inspector
"""

import pytest
import re
from pathlib import Path

# Path to the codebase
PROJECT_ROOT = Path(__file__).parent.parent
UI_SRC = PROJECT_ROOT / "ui" / "src"
API_PATH = PROJECT_ROOT / "api"


class TestStep1RunInspectorFetchesAllEventTypes:
    """Step 1: Run Inspector fetches all event types including new ones"""

    def test_types_ts_has_all_backend_event_types(self):
        """AgentEventType TypeScript union includes all backend EVENT_TYPES"""
        # Read backend EVENT_TYPES
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Read frontend types
        types_ts = (UI_SRC / "lib" / "types.ts").read_text()

        # Extract AgentEventType from the file
        agent_event_type_match = re.search(
            r"export type AgentEventType =\s*\n((?:\s*\|[^\n]+\n)+)",
            types_ts
        )
        assert agent_event_type_match, "AgentEventType type not found in types.ts"

        frontend_types = re.findall(r"'([a-z_]+)'", agent_event_type_match.group(1))

        # Verify all backend types are in frontend
        for event_type in backend_types:
            assert event_type in frontend_types, (
                f"Backend event type '{event_type}' missing from AgentEventType"
            )

        # Count should match
        assert len(frontend_types) == len(backend_types), (
            f"Frontend has {len(frontend_types)} types, backend has {len(backend_types)}"
        )

    def test_event_timeline_has_all_event_types_config(self):
        """EVENT_TYPE_CONFIG has entries for all event types"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Read backend EVENT_TYPES
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Check each event type has a config entry
        for event_type in backend_types:
            assert f"{event_type}:" in event_timeline or f"'{event_type}':" in event_timeline, (
                f"Event type '{event_type}' missing from EVENT_TYPE_CONFIG"
            )


class TestStep2NewEventsRenderedWithIconsAndLabels:
    """Step 2: New events rendered with appropriate icons and labels"""

    def test_all_event_types_have_icons(self):
        """Each event type config has an icon property"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Read backend EVENT_TYPES
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Extract EVENT_TYPE_CONFIG section
        config_match = re.search(
            r"const EVENT_TYPE_CONFIG.*?= \{(.*?)\n\}",
            event_timeline,
            re.DOTALL
        )
        assert config_match, "EVENT_TYPE_CONFIG not found"
        config_text = config_match.group(1)

        for event_type in backend_types:
            # Find this event type's config block
            type_pattern = rf"{event_type}:\s*\{{\s*icon:"
            assert re.search(type_pattern, config_text), (
                f"Event type '{event_type}' missing icon in config"
            )

    def test_all_event_types_have_labels(self):
        """Each event type config has a label property"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Read backend EVENT_TYPES
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Extract EVENT_TYPE_CONFIG section
        config_match = re.search(
            r"const EVENT_TYPE_CONFIG.*?= \{(.*?)\n\}",
            event_timeline,
            re.DOTALL
        )
        config_text = config_match.group(1)

        for event_type in backend_types:
            # Find this event type's config block
            type_pattern = rf"{event_type}:.*?label:"
            assert re.search(type_pattern, config_text, re.DOTALL), (
                f"Event type '{event_type}' missing label in config"
            )

    def test_all_event_types_have_colors(self):
        """Each event type config has color and bgColor properties"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Read backend EVENT_TYPES
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        for event_type in backend_types:
            # Each should have color property
            assert f"{event_type}:" in event_timeline
            # Get the config block for this event type
            pattern = rf"{event_type}:.*?color:.*?bgColor:"
            assert re.search(pattern, event_timeline, re.DOTALL), (
                f"Event type '{event_type}' missing color/bgColor in config"
            )

    def test_lucide_icons_imported(self):
        """Required Lucide icons are imported for new event types"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # New icons needed for new event types
        required_icons = [
            "ShieldAlert",      # policy_violation
            "Cog",              # sdk_session_started/completed
            "Target",           # agent_planned
            "Bot",              # octo_failure
            "FileCode",         # agent_materialized
            "TestTube",         # tests_written, tests_executed
            "Archive",          # test_result_artifact_created
            "Container",        # sandbox_tests_executed
            "Palette",          # icon_generated
        ]

        for icon in required_icons:
            assert icon in event_timeline, (
                f"Lucide icon '{icon}' not imported in EventTimeline.tsx"
            )


class TestStep3EventDetailsExpandable:
    """Step 3: Event details expandable to show payload"""

    def test_event_card_has_expand_toggle(self):
        """EventCard component has expand/collapse functionality"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Check for expand state management
        assert "isExpanded" in event_timeline, "Missing isExpanded state"
        assert "onToggle" in event_timeline, "Missing onToggle handler"

        # Check for ChevronDown/ChevronUp icons for expand indicator
        assert "ChevronDown" in event_timeline, "Missing ChevronDown icon"
        assert "ChevronUp" in event_timeline, "Missing ChevronUp icon"

    def test_payload_displayed_when_expanded(self):
        """Payload JSON is displayed when event is expanded"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Check for payload formatting function
        assert "formatPayload" in event_timeline, "Missing formatPayload function"

        # Check payload is conditionally rendered based on isExpanded
        assert "isExpanded && event.payload" in event_timeline or \
               "{isExpanded && event.payload" in event_timeline, \
               "Payload not conditionally rendered based on expand state"


class TestStep4EventsFilterableByType:
    """Step 4: Events filterable by type in inspector"""

    def test_all_event_types_in_filter_dropdown(self):
        """ALL_EVENT_TYPES array includes all backend event types"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Read backend EVENT_TYPES
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Extract ALL_EVENT_TYPES array
        all_types_match = re.search(
            r"const ALL_EVENT_TYPES.*?= \[(.*?)\]",
            event_timeline,
            re.DOTALL
        )
        assert all_types_match, "ALL_EVENT_TYPES not found"
        all_types_text = all_types_match.group(1)

        frontend_types = re.findall(r"'([a-z_]+)'", all_types_text)

        for event_type in backend_types:
            assert event_type in frontend_types, (
                f"Event type '{event_type}' missing from ALL_EVENT_TYPES filter dropdown"
            )

    def test_filter_dropdown_component_exists(self):
        """FilterDropdown component exists and handles filter changes"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Check FilterDropdown exists
        assert "FilterDropdown" in event_timeline, "FilterDropdown component missing"

        # Check it receives onChange callback
        assert "onChange" in event_timeline, "Missing onChange handler for filter"

        # Check filter state
        assert "filterType" in event_timeline or "selectedType" in event_timeline, \
            "Missing filter state"


class TestFeature226VerificationSteps:
    """Comprehensive tests for all Feature #226 verification steps"""

    def test_step_1_run_inspector_fetches_all_event_types(self):
        """Step 1: Run Inspector fetches all event types including new ones"""
        # The API endpoint /api/agent-runs/:id/events uses event_type filter
        # which is validated against EVENT_TYPES. Frontend must support all.

        types_ts = (UI_SRC / "lib" / "types.ts").read_text()
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()

        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Check types.ts
        for event_type in backend_types:
            assert f"'{event_type}'" in types_ts, (
                f"Type '{event_type}' missing from AgentEventType"
            )

        # Check EventTimeline handles all types
        for event_type in backend_types:
            assert event_type in event_timeline, (
                f"Event type '{event_type}' not handled in EventTimeline"
            )

    def test_step_2_events_rendered_with_icons_and_labels(self):
        """Step 2: New events rendered with appropriate icons and labels"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()

        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # New event types added after the original 10
        new_event_types = [
            "policy_violation",
            "sdk_session_started",
            "sdk_session_completed",
            "agent_planned",
            "octo_failure",
            "agent_materialized",
            "tests_written",
            "tests_executed",
            "test_result_artifact_created",
            "sandbox_tests_executed",
            "icon_generated",
        ]

        for event_type in new_event_types:
            # Must have icon
            assert f"{event_type}:" in event_timeline and "icon:" in event_timeline
            # Must have label
            assert "label:" in event_timeline

    def test_step_3_event_details_expandable(self):
        """Step 3: Event details expandable to show payload"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Expandable functionality
        assert "expandedEventId" in event_timeline, "Missing expand state"
        assert "toggleEventExpansion" in event_timeline, "Missing toggle function"
        assert "isExpanded" in event_timeline, "Missing isExpanded prop"

        # Payload display
        assert "formatPayload" in event_timeline, "Missing payload formatter"
        assert "JSON.stringify" in event_timeline, "Missing JSON serialization"

    def test_step_4_events_filterable_by_type(self):
        """Step 4: Events filterable by type in inspector"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()

        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Filter dropdown exists
        assert "FilterDropdown" in event_timeline

        # ALL_EVENT_TYPES contains all backend types
        all_types_match = re.search(
            r"const ALL_EVENT_TYPES.*?= \[(.*?)\]",
            event_timeline,
            re.DOTALL
        )
        all_types_text = all_types_match.group(1)

        for event_type in backend_types:
            assert f"'{event_type}'" in all_types_text, (
                f"Filter dropdown missing '{event_type}'"
            )


class TestNewEventTypeConfigs:
    """Test specific configuration for each new event type"""

    @pytest.mark.parametrize("event_type,expected_label", [
        ("policy_violation", "Policy Violation"),
        ("sdk_session_started", "SDK Started"),
        ("sdk_session_completed", "SDK Completed"),
        ("agent_planned", "Agent Planned"),
        ("octo_failure", "Octo Failure"),
        ("agent_materialized", "Agent Materialized"),
        ("tests_written", "Tests Written"),
        ("tests_executed", "Tests Executed"),
        ("test_result_artifact_created", "Test Artifact"),
        ("sandbox_tests_executed", "Sandbox Tests"),
        ("icon_generated", "Icon Generated"),
    ])
    def test_new_event_type_has_correct_label(self, event_type, expected_label):
        """Each new event type has a human-readable label"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Find the config for this event type
        pattern = rf"{event_type}:.*?label:\s*['\"]([^'\"]+)['\"]"
        match = re.search(pattern, event_timeline, re.DOTALL)

        assert match, f"Label not found for {event_type}"
        actual_label = match.group(1)
        assert actual_label == expected_label, (
            f"Expected label '{expected_label}' for {event_type}, got '{actual_label}'"
        )

    @pytest.mark.parametrize("event_type,expected_icon", [
        ("policy_violation", "ShieldAlert"),
        ("sdk_session_started", "Cog"),
        ("sdk_session_completed", "Cog"),
        ("agent_planned", "Target"),
        ("octo_failure", "Bot"),
        ("agent_materialized", "FileCode"),
        ("tests_written", "TestTube"),
        ("tests_executed", "TestTube"),
        ("test_result_artifact_created", "Archive"),
        ("sandbox_tests_executed", "Container"),
        ("icon_generated", "Palette"),
    ])
    def test_new_event_type_has_correct_icon(self, event_type, expected_icon):
        """Each new event type uses an appropriate icon"""
        event_timeline = (UI_SRC / "components" / "EventTimeline.tsx").read_text()

        # Find the config for this event type
        pattern = rf"{event_type}:.*?icon:\s*(\w+)"
        match = re.search(pattern, event_timeline, re.DOTALL)

        assert match, f"Icon not found for {event_type}"
        actual_icon = match.group(1)
        assert actual_icon == expected_icon, (
            f"Expected icon '{expected_icon}' for {event_type}, got '{actual_icon}'"
        )


class TestEventTypeCountSync:
    """Verify event type counts match between frontend and backend"""

    def test_frontend_backend_event_type_count_match(self):
        """Frontend and backend have the same number of event types"""
        types_ts = (UI_SRC / "lib" / "types.ts").read_text()
        agentspec_models = (API_PATH / "agentspec_models.py").read_text()

        # Count backend types
        backend_types = re.findall(r'"([a-z_]+)"',
            agentspec_models.split("EVENT_TYPES = [")[1].split("]")[0])

        # Count frontend types
        agent_event_type_match = re.search(
            r"export type AgentEventType =\s*\n((?:\s*\|[^\n]+\n)+)",
            types_ts
        )
        frontend_types = re.findall(r"'([a-z_]+)'", agent_event_type_match.group(1))

        assert len(frontend_types) == len(backend_types), (
            f"Type count mismatch: frontend={len(frontend_types)}, backend={len(backend_types)}"
        )

        # Should be 21 types total as of Feature #226
        assert len(backend_types) == 21, f"Expected 21 event types, got {len(backend_types)}"
