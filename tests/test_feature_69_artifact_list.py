#!/usr/bin/env python3
"""
Feature #69 Unit Tests
======================

Tests for the ArtifactList component implementation.

Feature: Artifact List Component
Description: Create Artifact List component with type filtering, preview, and download functionality.
"""

import os
import re
import sys
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestArtifactListComponentExists(unittest.TestCase):
    """Test Step 1: Create ArtifactList.tsx component"""

    def test_component_file_exists(self):
        """ArtifactList.tsx file should exist"""
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.assertTrue(component_path.exists(), "ArtifactList.tsx not found")

    def test_component_is_not_empty(self):
        """ArtifactList.tsx should have content"""
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        content = component_path.read_text()
        self.assertGreater(len(content), 100, "Component file seems too small")

    def test_component_exports_function(self):
        """ArtifactList should be exported as a function component"""
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        content = component_path.read_text()
        self.assertIn("export function ArtifactList", content)


class TestArtifactListProps(unittest.TestCase):
    """Test Step 2: Props: runId (string)"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_props_interface_exists(self):
        """ArtifactListProps interface should be defined"""
        self.assertIn("interface ArtifactListProps", self.content)

    def test_runid_prop_is_string(self):
        """runId prop should be typed as string"""
        self.assertIn("runId: string", self.content)

    def test_onartifactclick_prop_is_optional(self):
        """onArtifactClick prop should be optional"""
        self.assertIn("onArtifactClick?:", self.content)

    def test_classname_prop_is_optional(self):
        """className prop should be optional"""
        self.assertIn("className?:", self.content)


class TestArtifactListApiFetch(unittest.TestCase):
    """Test Step 3: Fetch artifacts via GET /api/agent-runs/:id/artifacts"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_getrunartifacts_imported(self):
        """getRunArtifacts should be imported from api"""
        self.assertIn("getRunArtifacts", self.content)

    def test_getrunartifacts_called_with_runid(self):
        """getRunArtifacts should be called with runId"""
        # Look for call pattern
        self.assertTrue(
            "getRunArtifacts(runId" in self.content or
            "getRunArtifacts(runId," in self.content
        )

    def test_uses_useeffect_or_usecallback(self):
        """Component should use useEffect or useCallback for fetching"""
        self.assertTrue(
            "useEffect" in self.content or
            "useCallback" in self.content
        )


class TestArtifactListFilterDropdown(unittest.TestCase):
    """Test Step 4: Filter dropdown by artifact_type"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_filter_dropdown_component_exists(self):
        """FilterDropdown component should exist"""
        self.assertIn("FilterDropdown", self.content)

    def test_filter_state_exists(self):
        """filterType state should be managed"""
        self.assertIn("filterType", self.content)

    def test_all_artifact_types_defined(self):
        """All 5 artifact types should be defined"""
        artifact_types = ["file_change", "test_result", "log", "metric", "snapshot"]
        for atype in artifact_types:
            self.assertIn(atype, self.content, f"Artifact type '{atype}' not found")

    def test_artifact_type_config_exists(self):
        """ARTIFACT_TYPE_CONFIG should be defined with icons and labels"""
        self.assertIn("ARTIFACT_TYPE_CONFIG", self.content)


class TestArtifactListMetadataDisplay(unittest.TestCase):
    """Test Step 5: Show artifact metadata: type, path, size"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_artifact_type_displayed(self):
        """artifact_type should be used in display"""
        self.assertIn("artifact_type", self.content)

    def test_artifact_path_displayed(self):
        """artifact.path should be used or formatPath function exists"""
        self.assertTrue(
            "artifact.path" in self.content or
            "formatPath" in self.content
        )

    def test_artifact_size_displayed(self):
        """size_bytes should be used or formatSize function exists"""
        self.assertTrue(
            "size_bytes" in self.content or
            "formatSize" in self.content
        )

    def test_formatsize_function_exists(self):
        """formatSize utility function should exist"""
        self.assertIn("function formatSize", self.content)


class TestArtifactListPreviewButton(unittest.TestCase):
    """Test Step 6: Preview button for inline content"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_preview_functionality_exists(self):
        """Preview button or onPreview handler should exist"""
        self.assertTrue(
            "Preview" in self.content or
            "onPreview" in self.content
        )

    def test_preview_modal_exists(self):
        """PreviewModal component should exist"""
        self.assertIn("PreviewModal", self.content)

    def test_inline_content_check_exists(self):
        """has_inline_content should be checked before showing preview"""
        self.assertIn("has_inline_content", self.content)

    def test_eye_icon_imported(self):
        """Eye icon should be imported for preview button"""
        self.assertIn("Eye", self.content)


class TestArtifactListDownloadButton(unittest.TestCase):
    """Test Step 7: Download button linking to /api/artifacts/:id/content"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_download_icon_exists(self):
        """Download icon should be imported"""
        self.assertIn("Download", self.content)

    def test_getartifactcontenturl_used(self):
        """getArtifactContentUrl should be imported and used"""
        self.assertIn("getArtifactContentUrl", self.content)

    def test_download_link_exists(self):
        """Download link with href attribute should exist"""
        self.assertIn("download", self.content.lower())
        self.assertIn("href", self.content.lower())

    def test_download_attribute_used(self):
        """Download attribute should be used on link"""
        # Look for anchor with download attribute
        self.assertRegex(self.content, r'<a[^>]+download')


class TestArtifactListEmptyState(unittest.TestCase):
    """Test Step 8: Handle empty state gracefully"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_empty_array_check(self):
        """artifacts.length === 0 should be checked"""
        self.assertIn("artifacts.length === 0", self.content)

    def test_empty_state_message(self):
        """Empty state message should be displayed"""
        self.assertTrue(
            "no artifacts" in self.content.lower() or
            "neo-empty-state" in self.content
        )

    def test_empty_state_icon(self):
        """File or similar icon should be shown in empty state"""
        self.assertIn("File", self.content)


class TestTypesFile(unittest.TestCase):
    """Test that types are properly defined in types.ts"""

    def setUp(self):
        types_path = PROJECT_ROOT / "ui" / "src" / "lib" / "types.ts"
        self.content = types_path.read_text()

    def test_artifacttype_defined(self):
        """ArtifactType type should be defined"""
        self.assertTrue(
            "type ArtifactType" in self.content or
            "ArtifactType =" in self.content
        )

    def test_artifact_interface_defined(self):
        """Artifact interface should be defined"""
        self.assertIn("interface Artifact", self.content)

    def test_artifactlistresponse_defined(self):
        """ArtifactListResponse interface should be defined"""
        self.assertIn("interface ArtifactListResponse", self.content)

    def test_artifact_has_required_fields(self):
        """Artifact interface should have all required fields"""
        required_fields = ["id", "run_id", "artifact_type", "path", "size_bytes", "has_inline_content"]
        for field in required_fields:
            self.assertIn(field, self.content, f"Field '{field}' not found in Artifact interface")


class TestApiFile(unittest.TestCase):
    """Test that API functions are properly defined in api.ts"""

    def setUp(self):
        api_path = PROJECT_ROOT / "ui" / "src" / "lib" / "api.ts"
        self.content = api_path.read_text()

    def test_getrunartifacts_defined(self):
        """getRunArtifacts function should be defined"""
        self.assertIn("getRunArtifacts", self.content)

    def test_getartifactcontenturl_defined(self):
        """getArtifactContentUrl function should be defined"""
        self.assertIn("getArtifactContentUrl", self.content)

    def test_correct_endpoint_used(self):
        """Correct API endpoint should be used"""
        self.assertIn("/agent-runs/", self.content)
        self.assertIn("/artifacts", self.content)

    def test_artifact_type_import(self):
        """ArtifactType should be imported from types"""
        self.assertIn("ArtifactType", self.content)


class TestArtifactCardComponent(unittest.TestCase):
    """Test the ArtifactCard sub-component"""

    def setUp(self):
        component_path = PROJECT_ROOT / "ui" / "src" / "components" / "ArtifactList.tsx"
        self.content = component_path.read_text()

    def test_artifactcard_exists(self):
        """ArtifactCard component should exist"""
        self.assertIn("function ArtifactCard", self.content)

    def test_artifactcard_has_props(self):
        """ArtifactCard should have props interface"""
        self.assertIn("ArtifactCardProps", self.content)

    def test_artifactcard_renders_icon(self):
        """ArtifactCard should render type-specific icon"""
        self.assertIn("Icon", self.content)

    def test_artifactcard_clickable(self):
        """ArtifactCard should be clickable"""
        self.assertIn("onClick", self.content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
