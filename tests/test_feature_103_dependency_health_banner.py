"""
Tests for Feature #103: Optional UI banner shows when dependency issues detected at startup

This feature includes:
1. Add dependency_health endpoint to API that returns issue summary
2. If issues requiring attention exist, return {has_issues: true, count: N}
3. UI can optionally display banner: Warning: N dependency issues detected - see logs
4. Banner should be dismissible
5. Banner style: yellow/orange warning color, not blocking UI
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import os

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))


class TestDependencyHealthEndpoint:
    """Test Step 1: Add dependency_health endpoint to API that returns issue summary"""

    def test_endpoint_exists_in_router(self):
        """Verify the /dependency-health endpoint is defined in the features router."""
        from server.routers.features import router

        # Get all routes
        routes = [route.path for route in router.routes]

        # Check that dependency-health endpoint exists (includes full path with prefix)
        has_dependency_health = any("dependency-health" in route for route in routes)
        assert has_dependency_health, (
            f"Expected /dependency-health endpoint in features router. Routes: {routes}"
        )

    def test_endpoint_returns_json_structure(self):
        """Verify endpoint returns correct JSON structure."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock

        # Create a minimal FastAPI app with the features router
        from fastapi import FastAPI
        from server.routers.features import router

        app = FastAPI()
        app.include_router(router)

        # Mock the dependencies
        with patch('server.routers.features._get_project_path') as mock_path, \
             patch('server.routers.features._get_db_classes') as mock_db, \
             patch('server.routers.features._get_validate_dependency_graph') as mock_validate:

            # Setup mocks
            temp_dir = tempfile.mkdtemp()
            mock_path.return_value = Path(temp_dir)

            # Create a mock database file
            db_file = Path(temp_dir) / "features.db"
            db_file.touch()

            # Mock the database classes
            MockFeature = MagicMock()
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = []
            mock_session_class = MagicMock(return_value=mock_session)
            mock_create_db = MagicMock(return_value=(None, mock_session_class))
            mock_db.return_value = (mock_create_db, MockFeature)

            # Mock the validate function
            mock_validate.return_value = lambda features: {
                "is_valid": True,
                "issues": [],
                "self_references": [],
                "cycles": [],
                "missing_targets": {},
                "summary": "Dependency graph is healthy"
            }

            client = TestClient(app)
            response = client.get("/api/projects/test/features/dependency-health")

            # Cleanup
            os.unlink(db_file)
            os.rmdir(temp_dir)

            assert response.status_code == 200
            data = response.json()

            # Verify required fields
            assert "has_issues" in data, "Response must include has_issues"
            assert "count" in data, "Response must include count"
            assert "is_valid" in data, "Response must include is_valid"
            assert "self_references" in data, "Response must include self_references"
            assert "cycles" in data, "Response must include cycles"
            assert "missing_targets" in data, "Response must include missing_targets"
            assert "summary" in data, "Response must include summary"


class TestHasIssuesResponse:
    """Test Step 2: If issues requiring attention exist, return {has_issues: true, count: N}"""

    def test_has_issues_false_when_healthy(self):
        """Verify has_issues is False when no issues exist."""
        from server.routers.features import get_dependency_health
        from unittest.mock import patch, MagicMock, AsyncMock
        import asyncio

        with patch('server.routers.features.validate_project_name', return_value="test"), \
             patch('server.routers.features._get_project_path') as mock_path, \
             patch('server.routers.features._get_db_classes') as mock_db, \
             patch('server.routers.features._get_validate_dependency_graph') as mock_validate:

            temp_dir = tempfile.mkdtemp()
            mock_path.return_value = Path(temp_dir)

            db_file = Path(temp_dir) / "features.db"
            db_file.touch()

            MockFeature = MagicMock()
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = []
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=None)
            mock_session_class = MagicMock(return_value=mock_session)
            mock_create_db = MagicMock(return_value=(None, mock_session_class))
            mock_db.return_value = (mock_create_db, MockFeature)

            mock_validate.return_value = lambda features: {
                "is_valid": True,
                "issues": [],
                "self_references": [],
                "cycles": [],
                "missing_targets": {},
                "summary": "Dependency graph is healthy"
            }

            # Run the async function
            result = asyncio.run(get_dependency_health("test"))

            os.unlink(db_file)
            os.rmdir(temp_dir)

            assert result["has_issues"] == False
            assert result["count"] == 0

    def test_has_issues_true_when_issues_exist(self):
        """Verify has_issues is True and count is N when issues exist."""
        from server.routers.features import get_dependency_health
        from unittest.mock import patch, MagicMock
        import asyncio

        with patch('server.routers.features.validate_project_name', return_value="test"), \
             patch('server.routers.features._get_project_path') as mock_path, \
             patch('server.routers.features._get_db_classes') as mock_db, \
             patch('server.routers.features._get_validate_dependency_graph') as mock_validate:

            temp_dir = tempfile.mkdtemp()
            mock_path.return_value = Path(temp_dir)

            db_file = Path(temp_dir) / "features.db"
            db_file.touch()

            MockFeature = MagicMock()
            mock_session = MagicMock()
            mock_session.query.return_value.all.return_value = []
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=None)
            mock_session_class = MagicMock(return_value=mock_session)
            mock_create_db = MagicMock(return_value=(None, mock_session_class))
            mock_db.return_value = (mock_create_db, MockFeature)

            mock_validate.return_value = lambda features: {
                "is_valid": False,
                "issues": [
                    {"type": "self_reference", "feature_id": 1},
                    {"type": "cycle", "cycle": [1, 2, 1]},
                    {"type": "missing_target", "feature_id": 3, "target_id": 999},
                ],
                "self_references": [1],
                "cycles": [[1, 2, 1]],
                "missing_targets": {3: [999]},
                "summary": "3 issues found"
            }

            result = asyncio.run(get_dependency_health("test"))

            os.unlink(db_file)
            os.rmdir(temp_dir)

            assert result["has_issues"] == True
            assert result["count"] == 3  # 3 issues


class TestUIBannerComponent:
    """Test Step 3: UI can optionally display banner"""

    def test_banner_component_exists(self):
        """Verify the DependencyHealthBanner component file exists."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        assert banner_file.exists(), f"Expected {banner_file} to exist"

    def test_banner_component_has_required_imports(self):
        """Verify banner component imports necessary dependencies."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for required imports
        assert "useState" in content, "Component should use useState"
        assert "useEffect" in content, "Component should use useEffect"
        assert "useQuery" in content, "Component should use useQuery for data fetching"
        assert "getDependencyHealth" in content, "Component should import getDependencyHealth"

    def test_banner_displays_warning_message(self):
        """Verify banner displays correct warning message format."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for warning message format
        assert "Warning:" in content, "Banner should display 'Warning:'"
        assert "dependency issue" in content, "Banner should mention 'dependency issue'"
        assert "see logs" in content, "Banner should say 'see logs'"

    def test_banner_uses_count_from_api(self):
        """Verify banner uses count from API response."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check that count is used from healthData
        assert "healthData.count" in content or "healthData?.count" in content, (
            "Banner should use healthData.count to display issue count"
        )


class TestBannerDismissible:
    """Test Step 4: Banner should be dismissible"""

    def test_banner_has_dismiss_button(self):
        """Verify banner has a dismiss button."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for dismiss functionality
        assert "onClick={handleDismiss}" in content or "onClick" in content, (
            "Banner should have a click handler for dismissal"
        )
        assert "Dismiss" in content, "Banner should have dismiss button or label"

    def test_banner_stores_dismissed_state(self):
        """Verify banner stores dismissed state in session storage."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for session storage usage
        assert "sessionStorage" in content, (
            "Banner should use sessionStorage to remember dismissed state"
        )

    def test_banner_has_dismissed_state(self):
        """Verify banner has dismissed state variable."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for dismissed state
        assert "isDismissed" in content, "Banner should have isDismissed state"
        assert "setIsDismissed" in content, "Banner should have setIsDismissed setter"

    def test_banner_hides_when_dismissed(self):
        """Verify banner returns null when dismissed."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check that banner returns null when dismissed
        assert "isDismissed" in content and "return null" in content, (
            "Banner should return null when dismissed"
        )


class TestBannerStyle:
    """Test Step 5: Banner style: yellow/orange warning color, not blocking UI"""

    def test_banner_has_warning_colors(self):
        """Verify banner uses yellow/orange warning colors."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for amber/yellow/warning colors
        has_amber = "amber" in content.lower()
        has_yellow = "yellow" in content.lower()
        has_warning = "warning" in content.lower()
        has_orange = "orange" in content.lower()

        assert has_amber or has_yellow or has_warning or has_orange, (
            "Banner should use yellow/orange/amber warning colors"
        )

    def test_banner_uses_amber_tailwind_classes(self):
        """Verify banner uses specific amber Tailwind classes."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for specific amber classes
        assert "bg-amber" in content, "Banner should have amber background"
        assert "border-amber" in content, "Banner should have amber border"
        assert "text-amber" in content, "Banner should have amber text"

    def test_banner_has_warning_icon(self):
        """Verify banner has a warning icon."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Check for warning icon import and usage
        assert "AlertTriangle" in content, "Banner should use AlertTriangle icon"

    def test_banner_is_not_blocking(self):
        """Verify banner doesn't block UI (not modal/overlay)."""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Banner should NOT have modal/overlay classes
        assert "fixed inset-0" not in content, "Banner should not be a fixed overlay"
        assert "modal" not in content.lower(), "Banner should not be a modal"
        assert "z-50" not in content or "z-[9999]" not in content, (
            "Banner should not have high z-index blocking elements"
        )


class TestAPIClientFunction:
    """Test the getDependencyHealth API client function."""

    def test_api_function_exists(self):
        """Verify getDependencyHealth function is exported from api.ts."""
        api_file = root / "ui" / "src" / "lib" / "api.ts"
        content = api_file.read_text()

        assert "export async function getDependencyHealth" in content, (
            "getDependencyHealth should be exported from api.ts"
        )

    def test_api_function_calls_correct_endpoint(self):
        """Verify API function calls /dependency-health endpoint."""
        api_file = root / "ui" / "src" / "lib" / "api.ts"
        content = api_file.read_text()

        assert "dependency-health" in content, (
            "getDependencyHealth should call /dependency-health endpoint"
        )

    def test_api_response_type_defined(self):
        """Verify DependencyHealthResponse type is defined."""
        api_file = root / "ui" / "src" / "lib" / "api.ts"
        content = api_file.read_text()

        assert "DependencyHealthResponse" in content, (
            "DependencyHealthResponse type should be defined"
        )
        assert "has_issues" in content, "Type should include has_issues field"
        assert "count" in content, "Type should include count field"


class TestBannerIntegration:
    """Test banner integration with the main app."""

    def test_banner_imported_in_app(self):
        """Verify DependencyHealthBanner is imported in App.tsx."""
        app_file = root / "ui" / "src" / "App.tsx"
        content = app_file.read_text()

        assert "DependencyHealthBanner" in content, (
            "DependencyHealthBanner should be imported in App.tsx"
        )

    def test_banner_used_in_app(self):
        """Verify DependencyHealthBanner is used in the main app component."""
        app_file = root / "ui" / "src" / "App.tsx"
        content = app_file.read_text()

        assert "<DependencyHealthBanner" in content, (
            "DependencyHealthBanner should be used in App.tsx"
        )

    def test_banner_receives_project_name(self):
        """Verify banner receives projectName prop."""
        app_file = root / "ui" / "src" / "App.tsx"
        content = app_file.read_text()

        assert "projectName=" in content and "DependencyHealthBanner" in content, (
            "DependencyHealthBanner should receive projectName prop"
        )


class TestVerificationSteps:
    """Run verification steps from feature spec."""

    def test_step1_endpoint_exists(self):
        """Step 1: Add dependency_health endpoint to API that returns issue summary"""
        # Check router has the endpoint
        from server.routers.features import router
        routes = [route.path for route in router.routes]
        has_dependency_health = any("dependency-health" in route for route in routes)
        assert has_dependency_health, f"Expected dependency-health endpoint. Routes: {routes}"

    def test_step2_returns_correct_format(self):
        """Step 2: If issues requiring attention exist, return {has_issues: true, count: N}"""
        # Verify the endpoint function returns correct format
        api_file = root / "ui" / "src" / "lib" / "api.ts"
        content = api_file.read_text()

        # Check response type
        assert "has_issues: boolean" in content
        assert "count: number" in content

    def test_step3_banner_displays_warning(self):
        """Step 3: UI can optionally display banner: Warning: N dependency issues detected"""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        assert "Warning:" in content
        assert "dependency issue" in content
        assert "detected" in content

    def test_step4_banner_is_dismissible(self):
        """Step 4: Banner should be dismissible"""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        assert "handleDismiss" in content or "onDismiss" in content
        assert "isDismissed" in content

    def test_step5_banner_has_warning_style(self):
        """Step 5: Banner style: yellow/orange warning color, not blocking UI"""
        banner_file = root / "ui" / "src" / "components" / "DependencyHealthBanner.tsx"
        content = banner_file.read_text()

        # Yellow/orange warning colors
        assert "amber" in content.lower() or "yellow" in content.lower()

        # Not blocking (not a modal/overlay)
        assert "fixed inset-0" not in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
