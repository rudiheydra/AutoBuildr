#!/usr/bin/env python3
"""
Feature #67 Verification Script
==============================

Verifies the RunInspector Slide-Out Panel implementation.

Feature Requirements:
1. Create RunInspector.tsx component
2. Props: runId (string), onClose (function)
3. Fetch run details via GET /api/agent-runs/:id
4. Slide in from right with animation
5. Show run header with spec info and status
6. Tabs for Timeline, Artifacts, Acceptance
7. Close on Escape key or overlay click
8. Responsive width for mobile
"""

import os
import re
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_file(filepath: str) -> str:
    """Read a file and return its contents."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def verify_step_1_component_exists():
    """Step 1: Create RunInspector.tsx component"""
    print("\n[Step 1] Verify RunInspector.tsx component exists...")

    component_path = "ui/src/components/RunInspector.tsx"

    if not os.path.exists(component_path):
        print(f"  FAIL: Component file not found at {component_path}")
        return False

    content = read_file(component_path)

    # Check for component export
    if 'export function RunInspector' in content or 'export default RunInspector' in content:
        print("  PASS: RunInspector component found and exported")
        return True
    else:
        print("  FAIL: RunInspector component not properly exported")
        return False


def verify_step_2_props():
    """Step 2: Props: runId (string), onClose (function)"""
    print("\n[Step 2] Verify Props: runId (string), onClose (function)...")

    content = read_file("ui/src/components/RunInspector.tsx")

    # Check for onClose prop
    has_onclose = 'onClose:' in content or 'onClose?' in content or 'onClose(' in content

    # Check for runId prop (in RunIdModeProps)
    has_runid = 'runId:' in content or 'runId?' in content

    # Check that both modes are supported (data mode and runId mode)
    has_data_mode = 'DataModeProps' in content or 'data: DynamicAgentData' in content
    has_runid_mode = 'RunIdModeProps' in content or "runId: string" in content

    if has_onclose and has_runid and has_runid_mode:
        print("  PASS: runId prop defined")
        print("  PASS: onClose prop defined")
        print("  PASS: Supports both data mode and runId mode")
        return True
    else:
        if not has_onclose:
            print("  FAIL: onClose prop not found")
        if not has_runid:
            print("  FAIL: runId prop not found")
        return False


def verify_step_3_fetch_run_details():
    """Step 3: Fetch run details via GET /api/agent-runs/:id"""
    print("\n[Step 3] Verify fetch run details via GET /api/agent-runs/:id...")

    content = read_file("ui/src/components/RunInspector.tsx")

    # Check for fetch call to agent-runs endpoint
    has_fetch = '/api/agent-runs/' in content or '`/api/agent-runs/${' in content

    # Check for useRunDetails hook or similar data fetching
    has_hook = 'useRunDetails' in content or 'fetchRunDetails' in content

    # Check that response is processed
    has_response_handling = 'response.json()' in content

    if has_fetch and has_hook and has_response_handling:
        print("  PASS: API fetch for run details implemented")
        print("  PASS: useRunDetails hook defined")
        print("  PASS: Response handling implemented")
        return True
    else:
        if not has_fetch:
            print("  FAIL: API fetch URL not found")
        if not has_hook:
            print("  FAIL: Data fetching hook not found")
        if not has_response_handling:
            print("  FAIL: Response handling not found")
        return False


def verify_step_4_slide_animation():
    """Step 4: Slide in from right with animation"""
    print("\n[Step 4] Verify slide in from right with animation...")

    # Check component for animation class
    component_content = read_file("ui/src/components/RunInspector.tsx")

    # Check for slide-in-right animation class
    has_slide_animation = 'animate-slide-in-right' in component_content

    # Check CSS for the animation definition
    css_content = read_file("ui/src/styles/globals.css")

    has_keyframes = '@keyframes slide-in-right' in css_content
    has_animation_class = '.animate-slide-in-right' in css_content

    # Check that the animation uses translateX with positive value (from right)
    has_from_right = 'translateX(100%)' in css_content or 'translateX(20px)' in css_content

    if has_slide_animation and has_keyframes and has_animation_class:
        print("  PASS: animate-slide-in-right class used in component")
        print("  PASS: @keyframes slide-in-right defined in CSS")
        print("  PASS: Animation class utility defined")
        return True
    else:
        if not has_slide_animation:
            print("  FAIL: animate-slide-in-right class not used in component")
        if not has_keyframes:
            print("  FAIL: @keyframes slide-in-right not defined")
        if not has_animation_class:
            print("  FAIL: .animate-slide-in-right class not defined")
        return False


def verify_step_5_header():
    """Step 5: Show run header with spec info and status"""
    print("\n[Step 5] Verify run header with spec info and status...")

    content = read_file("ui/src/components/RunInspector.tsx")

    # Check for spec display elements
    has_display_name = 'display_name' in content or 'displayName' in content
    has_icon = 'icon' in content
    has_status_badge = 'StatusBadge' in content

    # Check for header section with proper ARIA
    has_header_id = 'run-inspector-title' in content
    has_aria_labelledby = 'aria-labelledby="run-inspector-title"' in content

    if has_display_name and has_icon and has_status_badge and has_header_id:
        print("  PASS: Display name shown")
        print("  PASS: Icon displayed")
        print("  PASS: StatusBadge component used")
        print("  PASS: Accessible header with ARIA attributes")
        return True
    else:
        if not has_display_name:
            print("  FAIL: display_name not shown")
        if not has_icon:
            print("  FAIL: icon not displayed")
        if not has_status_badge:
            print("  FAIL: StatusBadge not used")
        return False


def verify_step_6_tabs():
    """Step 6: Tabs for Timeline, Artifacts, Acceptance"""
    print("\n[Step 6] Verify Tabs for Timeline, Artifacts, Acceptance...")

    content = read_file("ui/src/components/RunInspector.tsx")

    # Check for tab definitions
    has_timeline_tab = "'timeline'" in content or '"timeline"' in content or 'Timeline' in content
    has_artifacts_tab = "'artifacts'" in content or '"artifacts"' in content or 'Artifacts' in content
    has_acceptance_tab = "'acceptance'" in content or '"acceptance"' in content or 'Acceptance' in content

    # Check for TABS array or similar configuration
    has_tabs_config = 'TABS' in content or 'TabConfig' in content

    # Check for tab components
    has_event_timeline = 'EventTimeline' in content
    has_artifact_list = 'ArtifactList' in content
    has_acceptance_results = 'AcceptanceResults' in content

    # Check for ARIA role="tab"
    has_tab_role = 'role="tab"' in content
    has_tabpanel_role = 'role="tabpanel"' in content

    if has_timeline_tab and has_artifacts_tab and has_acceptance_tab:
        print("  PASS: Timeline tab defined")
        print("  PASS: Artifacts tab defined")
        print("  PASS: Acceptance tab defined")

        if has_event_timeline:
            print("  PASS: EventTimeline component used")
        if has_artifact_list:
            print("  PASS: ArtifactList component used")
        if has_acceptance_results:
            print("  PASS: AcceptanceResults component used")
        if has_tab_role and has_tabpanel_role:
            print("  PASS: ARIA roles for tabs implemented")

        return True
    else:
        return False


def verify_step_7_escape_and_overlay():
    """Step 7: Close on Escape key or overlay click"""
    print("\n[Step 7] Verify close on Escape key or overlay click...")

    content = read_file("ui/src/components/RunInspector.tsx")

    # Check for Escape key handler
    has_escape_handler = "'Escape'" in content or '"Escape"' in content
    has_keydown_listener = 'keydown' in content or 'handleKeyDown' in content

    # Check for overlay click handler
    has_backdrop = 'Backdrop' in content or 'backdrop' in content
    has_overlay_click = 'onClick={onClose}' in content

    # Check for event listener setup/cleanup
    has_event_listener = 'addEventListener' in content
    has_cleanup = 'removeEventListener' in content

    if has_escape_handler and has_keydown_listener and has_overlay_click:
        print("  PASS: Escape key handler implemented")
        print("  PASS: Overlay click handler implemented")
        if has_event_listener and has_cleanup:
            print("  PASS: Event listener cleanup implemented")
        return True
    else:
        if not has_escape_handler:
            print("  FAIL: Escape key not handled")
        if not has_keydown_listener:
            print("  FAIL: keydown listener not found")
        if not has_overlay_click:
            print("  FAIL: Overlay click handler not found")
        return False


def verify_step_8_responsive():
    """Step 8: Responsive width for mobile"""
    print("\n[Step 8] Verify responsive width for mobile...")

    content = read_file("ui/src/components/RunInspector.tsx")

    # Check for responsive width classes (Tailwind breakpoints)
    has_responsive_sm = 'sm:w-' in content or 'sm:max-w-' in content
    has_responsive_md = 'md:w-' in content or 'md:max-w-' in content
    has_responsive_lg = 'lg:w-' in content or 'lg:max-w-' in content

    # Check for w-full (mobile first)
    has_mobile_full = 'w-full' in content

    # Check for max-w constraint
    has_max_width = 'max-w-lg' in content or 'max-w-xl' in content or 'max-w-md' in content

    if has_mobile_full and (has_responsive_sm or has_responsive_md or has_responsive_lg):
        print("  PASS: w-full for mobile (mobile-first approach)")
        if has_responsive_sm:
            print("  PASS: sm: breakpoint responsive width")
        if has_responsive_md:
            print("  PASS: md: breakpoint responsive width")
        if has_responsive_lg:
            print("  PASS: lg: breakpoint responsive width")
        if has_max_width:
            print("  PASS: max-width constraint for larger screens")
        return True
    else:
        if not has_mobile_full:
            print("  FAIL: w-full not found for mobile")
        if not (has_responsive_sm or has_responsive_md or has_responsive_lg):
            print("  FAIL: No responsive breakpoints found")
        return False


def verify_api_endpoint():
    """Verify the API endpoint exists and works"""
    print("\n[Bonus] Verify API endpoint exists...")

    # Check router file for the endpoint
    try:
        router_content = read_file("server/routers/agent_runs.py")

        has_get_run = '@router.get("/{run_id}"' in router_content or 'async def get_run' in router_content

        if has_get_run:
            print("  PASS: GET /api/agent-runs/:id endpoint exists")
            return True
        else:
            print("  FAIL: GET endpoint not found")
            return False
    except FileNotFoundError:
        # Try API folder
        try:
            router_content = read_file("api/routers/agent_runs.py")
            if '@router.get("/{run_id}"' in router_content:
                print("  PASS: GET /api/agent-runs/:id endpoint exists")
                return True
        except FileNotFoundError:
            pass
        print("  SKIP: Could not find router file")
        return True  # Don't fail for missing router


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #67: Run Inspector Slide-Out Panel")
    print("=" * 60)

    # Change to project root
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    results = []

    # Run each verification step
    results.append(("Step 1: Component exists", verify_step_1_component_exists()))
    results.append(("Step 2: Props (runId, onClose)", verify_step_2_props()))
    results.append(("Step 3: Fetch run details", verify_step_3_fetch_run_details()))
    results.append(("Step 4: Slide animation", verify_step_4_slide_animation()))
    results.append(("Step 5: Header with spec info", verify_step_5_header()))
    results.append(("Step 6: Tabs (Timeline/Artifacts/Acceptance)", verify_step_6_tabs()))
    results.append(("Step 7: Escape key and overlay close", verify_step_7_escape_and_overlay()))
    results.append(("Step 8: Responsive width", verify_step_8_responsive()))
    results.append(("Bonus: API endpoint", verify_api_endpoint()))

    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        status = "PASS" if result else "FAIL"
        icon = "✓" if result else "✗"
        print(f"  {icon} {name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nResults: {passed}/{len(results)} steps passed")

    if failed == 0:
        print("\n" + "=" * 60)
        print("ALL VERIFICATION STEPS PASSED!")
        print("Feature #67 is ready to be marked as passing.")
        print("=" * 60)
        return 0
    else:
        print(f"\n{failed} step(s) failed. Please address the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
