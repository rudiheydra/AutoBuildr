#!/usr/bin/env python3
"""
Feature #69 Verification Script
===============================

Verifies the ArtifactList component implementation.

Feature: Artifact List Component
Description: Create Artifact List component with type filtering, preview, and download functionality.

Verification Steps:
1. Create ArtifactList.tsx component - CHECK FILE EXISTS
2. Props: runId (string) - CHECK COMPONENT PROPS
3. Fetch artifacts via GET /api/agent-runs/:id/artifacts - CHECK API INTEGRATION
4. Filter dropdown by artifact_type - CHECK FILTER COMPONENT
5. Show artifact metadata: type, path, size - CHECK METADATA DISPLAY
6. Preview button for inline content - CHECK PREVIEW FUNCTIONALITY
7. Download button linking to /api/artifacts/:id/content - CHECK DOWNLOAD LINK
8. Handle empty state gracefully - CHECK EMPTY STATE
"""

import os
import re
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Test results
RESULTS = []


def check(step: str, passed: bool, details: str = ""):
    """Record a verification step result."""
    status = "PASS" if passed else "FAIL"
    RESULTS.append((step, passed, details))
    print(f"  [{status}] {step}")
    if details:
        print(f"          {details}")


def verify_component_file_exists():
    """Step 1: Verify ArtifactList.tsx component exists."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    exists = component_path.exists()
    check(
        "Step 1: ArtifactList.tsx component file exists",
        exists,
        f"Path: {component_path}" if exists else "Component file not found!"
    )
    return exists


def verify_props_interface():
    """Step 2: Verify Props include runId (string)."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for ArtifactListProps interface with runId
    has_props_interface = "interface ArtifactListProps" in content
    has_runid_prop = "runId: string" in content

    check(
        "Step 2a: ArtifactListProps interface defined",
        has_props_interface,
        "Props interface found" if has_props_interface else "Missing ArtifactListProps interface"
    )
    check(
        "Step 2b: runId prop is string type",
        has_runid_prop,
        "runId: string found" if has_runid_prop else "runId prop not found or wrong type"
    )

    return has_props_interface and has_runid_prop


def verify_api_fetch():
    """Step 3: Verify artifact fetching via API."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for getRunArtifacts import and usage
    has_import = "getRunArtifacts" in content
    has_fetch_call = "getRunArtifacts(runId" in content or "getRunArtifacts(runId," in content

    check(
        "Step 3a: getRunArtifacts function imported",
        has_import,
        "getRunArtifacts imported" if has_import else "Missing getRunArtifacts import"
    )
    check(
        "Step 3b: API fetch called with runId",
        has_fetch_call,
        "getRunArtifacts(runId) call found" if has_fetch_call else "API fetch not using runId"
    )

    return has_import and has_fetch_call


def verify_filter_dropdown():
    """Step 4: Verify filter dropdown by artifact_type."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for FilterDropdown component
    has_filter_component = "FilterDropdown" in content
    has_filter_state = "filterType" in content
    has_artifact_types = all(t in content for t in ["file_change", "test_result", "log", "metric", "snapshot"])

    check(
        "Step 4a: FilterDropdown component exists",
        has_filter_component,
        "FilterDropdown found" if has_filter_component else "Missing FilterDropdown component"
    )
    check(
        "Step 4b: Filter state management",
        has_filter_state,
        "filterType state found" if has_filter_state else "Missing filter state"
    )
    check(
        "Step 4c: All artifact types supported",
        has_artifact_types,
        "All 5 artifact types found" if has_artifact_types else "Some artifact types missing"
    )

    return has_filter_component and has_filter_state and has_artifact_types


def verify_metadata_display():
    """Step 5: Verify artifact metadata display (type, path, size)."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for metadata display elements
    has_type_display = "artifact_type" in content or "artifact.artifact_type" in content
    has_path_display = "artifact.path" in content or "formatPath" in content
    has_size_display = "size_bytes" in content or "formatSize" in content

    check(
        "Step 5a: Artifact type displayed",
        has_type_display,
        "artifact_type used" if has_type_display else "Type not displayed"
    )
    check(
        "Step 5b: Artifact path displayed",
        has_path_display,
        "Path display found" if has_path_display else "Path not displayed"
    )
    check(
        "Step 5c: Artifact size displayed",
        has_size_display,
        "Size display found" if has_size_display else "Size not displayed"
    )

    return has_type_display and has_path_display and has_size_display


def verify_preview_button():
    """Step 6: Verify preview button for inline content."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for preview functionality
    has_preview_button = "Preview" in content or "onPreview" in content
    has_preview_modal = "PreviewModal" in content
    has_inline_check = "has_inline_content" in content

    check(
        "Step 6a: Preview button/handler exists",
        has_preview_button,
        "Preview functionality found" if has_preview_button else "Preview button missing"
    )
    check(
        "Step 6b: Preview modal component",
        has_preview_modal,
        "PreviewModal found" if has_preview_modal else "PreviewModal missing"
    )
    check(
        "Step 6c: Inline content check",
        has_inline_check,
        "has_inline_content check found" if has_inline_check else "Inline content check missing"
    )

    return has_preview_button and has_preview_modal and has_inline_check


def verify_download_button():
    """Step 7: Verify download button linking to content endpoint."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for download functionality
    has_download_icon = "Download" in content
    has_artifact_content_url = "getArtifactContentUrl" in content
    has_download_link = "download" in content.lower() and "href" in content.lower()

    check(
        "Step 7a: Download icon/button exists",
        has_download_icon,
        "Download icon found" if has_download_icon else "Download icon missing"
    )
    check(
        "Step 7b: getArtifactContentUrl used",
        has_artifact_content_url,
        "Content URL function used" if has_artifact_content_url else "Content URL missing"
    )
    check(
        "Step 7c: Download link with href",
        has_download_link,
        "Download link found" if has_download_link else "Download link missing"
    )

    return has_download_icon and has_artifact_content_url and has_download_link


def verify_empty_state():
    """Step 8: Verify empty state handling."""
    component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
    content = component_path.read_text()

    # Check for empty state handling
    has_empty_check = "artifacts.length === 0" in content or "artifacts.length === 0" in content
    has_empty_message = "No artifacts" in content.lower() or "neo-empty-state" in content

    check(
        "Step 8a: Empty array check",
        has_empty_check,
        "Empty array check found" if has_empty_check else "Empty array check missing"
    )
    check(
        "Step 8b: Empty state message",
        has_empty_message,
        "Empty state message found" if has_empty_message else "Empty state message missing"
    )

    return has_empty_check and has_empty_message


def verify_types_file():
    """Verify types are added to types.ts."""
    types_path = PROJECT_ROOT / "ui" / "src" / "lib" / "types.ts"
    content = types_path.read_text()

    has_artifact_type = "type ArtifactType" in content or "ArtifactType =" in content
    has_artifact_interface = "interface Artifact" in content
    has_artifact_list_response = "interface ArtifactListResponse" in content

    check(
        "Types: ArtifactType defined",
        has_artifact_type,
        "ArtifactType found in types.ts" if has_artifact_type else "ArtifactType missing from types.ts"
    )
    check(
        "Types: Artifact interface defined",
        has_artifact_interface,
        "Artifact interface found" if has_artifact_interface else "Artifact interface missing"
    )
    check(
        "Types: ArtifactListResponse defined",
        has_artifact_list_response,
        "ArtifactListResponse found" if has_artifact_list_response else "ArtifactListResponse missing"
    )

    return has_artifact_type and has_artifact_interface and has_artifact_list_response


def verify_api_file():
    """Verify API functions are added to api.ts."""
    api_path = PROJECT_ROOT / "ui" / "src" / "lib" / "api.ts"
    content = api_path.read_text()

    has_get_run_artifacts = "getRunArtifacts" in content
    has_get_artifact_content_url = "getArtifactContentUrl" in content
    has_correct_endpoint = "/agent-runs/" in content and "/artifacts" in content

    check(
        "API: getRunArtifacts function defined",
        has_get_run_artifacts,
        "getRunArtifacts found in api.ts" if has_get_run_artifacts else "getRunArtifacts missing from api.ts"
    )
    check(
        "API: getArtifactContentUrl function defined",
        has_get_artifact_content_url,
        "getArtifactContentUrl found" if has_get_artifact_content_url else "getArtifactContentUrl missing"
    )
    check(
        "API: Correct endpoint path",
        has_correct_endpoint,
        "Correct endpoint pattern" if has_correct_endpoint else "Incorrect endpoint"
    )

    return has_get_run_artifacts and has_get_artifact_content_url and has_correct_endpoint


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #69: Artifact List Component - Verification")
    print("=" * 60)
    print()

    all_passed = True

    # Step 1: Component file exists
    print("Verifying component file...")
    if not verify_component_file_exists():
        all_passed = False
        print("\nCannot continue - component file not found!")
        return False
    print()

    # Step 2: Props interface
    print("Verifying props interface...")
    if not verify_props_interface():
        all_passed = False
    print()

    # Step 3: API fetch
    print("Verifying API integration...")
    if not verify_api_fetch():
        all_passed = False
    print()

    # Step 4: Filter dropdown
    print("Verifying filter dropdown...")
    if not verify_filter_dropdown():
        all_passed = False
    print()

    # Step 5: Metadata display
    print("Verifying metadata display...")
    if not verify_metadata_display():
        all_passed = False
    print()

    # Step 6: Preview button
    print("Verifying preview functionality...")
    if not verify_preview_button():
        all_passed = False
    print()

    # Step 7: Download button
    print("Verifying download functionality...")
    if not verify_download_button():
        all_passed = False
    print()

    # Step 8: Empty state
    print("Verifying empty state handling...")
    if not verify_empty_state():
        all_passed = False
    print()

    # Additional: Types file
    print("Verifying types definitions...")
    if not verify_types_file():
        all_passed = False
    print()

    # Additional: API file
    print("Verifying API functions...")
    if not verify_api_file():
        all_passed = False
    print()

    # Summary
    print("=" * 60)
    passed_count = sum(1 for _, passed, _ in RESULTS if passed)
    total_count = len(RESULTS)
    print(f"Results: {passed_count}/{total_count} checks passed")

    if all_passed:
        print("\n*** ALL VERIFICATION STEPS PASSED ***")
    else:
        print("\n*** SOME VERIFICATION STEPS FAILED ***")
        failed = [(step, details) for step, passed, details in RESULTS if not passed]
        print("\nFailed checks:")
        for step, details in failed:
            print(f"  - {step}: {details}")

    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
