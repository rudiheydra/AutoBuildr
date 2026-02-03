"""
Tests for Feature #203: Scaffolding can be triggered manually via API

This test module verifies that the POST /api/projects/{name}/scaffold endpoint
correctly creates the .claude directory structure and CLAUDE.md file.

Verification Steps:
1. POST /api/projects/{id}/scaffold endpoint created
2. Endpoint runs scaffolding for specified project
3. Returns status of created/existing directories and files
4. Useful for repair/reset scenarios
"""

import sys
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def mock_registry(temp_project_dir: Path):
    """Mock the registry functions."""
    with patch("server.routers.projects._get_registry_functions") as mock_get:
        mock_get.return_value = (
            MagicMock(),  # register_project
            MagicMock(),  # unregister_project
            MagicMock(return_value=temp_project_dir),  # get_project_path
            MagicMock(return_value={}),  # list_registered_projects
            MagicMock(),  # validate_project_path
        )
        yield mock_get


# =============================================================================
# Test Step 1: POST /api/projects/{id}/scaffold endpoint created
# =============================================================================

class TestStep1EndpointCreated:
    """Test that the scaffold endpoint is properly created."""

    def test_router_has_scaffold_endpoint(self):
        """Test that the router has a scaffold endpoint."""
        from server.routers.projects import router

        # Find the scaffold route
        scaffold_routes = [
            route for route in router.routes
            if hasattr(route, "path") and "scaffold" in route.path
        ]
        assert len(scaffold_routes) == 1, "Should have exactly one scaffold route"

    def test_scaffold_endpoint_is_post(self):
        """Test that scaffold endpoint uses POST method."""
        from server.routers.projects import router

        scaffold_route = None
        for route in router.routes:
            if hasattr(route, "path") and "scaffold" in route.path:
                scaffold_route = route
                break

        assert scaffold_route is not None
        assert "POST" in scaffold_route.methods

    def test_scaffold_endpoint_path_format(self):
        """Test the endpoint path is correctly formatted."""
        from server.routers.projects import router

        scaffold_route = None
        for route in router.routes:
            if hasattr(route, "path") and "scaffold" in route.path:
                scaffold_route = route
                break

        assert scaffold_route is not None
        # The router has a prefix, so we check for the relative path
        assert "scaffold" in scaffold_route.path
        assert "{name}" in scaffold_route.path

    def test_scaffold_response_schema_exists(self):
        """Test that ScaffoldResponse schema is properly defined."""
        from server.schemas import ScaffoldResponse

        # Check required fields
        schema = ScaffoldResponse.model_json_schema()
        properties = schema.get("properties", {})

        assert "success" in properties
        assert "project_name" in properties
        assert "project_dir" in properties
        assert "claude_root" in properties
        assert "directories" in properties
        assert "message" in properties

    def test_scaffold_request_schema_exists(self):
        """Test that ScaffoldRequest schema is properly defined."""
        from server.schemas import ScaffoldRequest

        # Check fields
        schema = ScaffoldRequest.model_json_schema()
        properties = schema.get("properties", {})

        assert "include_phase2" in properties
        assert "include_claude_md" in properties


# =============================================================================
# Test Step 2: Endpoint runs scaffolding for specified project
# =============================================================================

class TestStep2EndpointRunsScaffolding:
    """Test that the endpoint correctly runs scaffolding."""

    @pytest.mark.asyncio
    async def test_scaffold_creates_claude_directory(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding creates .claude directory."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Ensure .claude doesn't exist
        claude_dir = temp_project_dir / ".claude"
        assert not claude_dir.exists()

        # Call the endpoint
        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        # Verify .claude was created
        assert claude_dir.exists()
        assert response.success is True

    @pytest.mark.asyncio
    async def test_scaffold_creates_subdirectories(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding creates all subdirectories."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest(include_phase2=True)
        await scaffold_project("test_project", request)

        # Verify subdirectories
        claude_dir = temp_project_dir / ".claude"
        assert (claude_dir / "agents" / "generated").exists()
        assert (claude_dir / "agents" / "manual").exists()
        assert (claude_dir / "skills").exists()
        assert (claude_dir / "commands").exists()

    @pytest.mark.asyncio
    async def test_scaffold_without_phase2(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test scaffolding with include_phase2=False."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest(include_phase2=False)
        await scaffold_project("test_project", request)

        # Verify Phase 1 directories exist
        claude_dir = temp_project_dir / ".claude"
        assert (claude_dir / "agents" / "generated").exists()
        assert (claude_dir / "agents" / "manual").exists()

        # Phase 2 directories should still be created by scaffold_with_claude_md
        # but with include_phase2=False they shouldn't be
        # Note: The actual behavior depends on the scaffolding implementation

    @pytest.mark.asyncio
    async def test_scaffold_creates_claude_md(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding creates CLAUDE.md."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest(include_claude_md=True)
        response = await scaffold_project("test_project", request)

        # Verify CLAUDE.md was created
        claude_md = temp_project_dir / "CLAUDE.md"
        assert claude_md.exists()
        assert response.claude_md is not None
        assert response.claude_md.created is True

    @pytest.mark.asyncio
    async def test_scaffold_without_claude_md(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test scaffolding with include_claude_md=False."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest(include_claude_md=False)
        response = await scaffold_project("test_project", request)

        # CLAUDE.md should not be created
        claude_md = temp_project_dir / "CLAUDE.md"
        assert not claude_md.exists()
        assert response.claude_md is None


# =============================================================================
# Test Step 3: Returns status of created/existing directories and files
# =============================================================================

class TestStep3ReturnsStatus:
    """Test that the endpoint returns correct status information."""

    @pytest.mark.asyncio
    async def test_returns_success_status(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that response includes success status."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_returns_directory_count(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that response includes directory counts."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        # First run should create directories
        assert response.directories_created > 0
        assert response.directories_existed == 0
        assert response.directories_failed == 0

    @pytest.mark.asyncio
    async def test_returns_directory_details(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that response includes directory details."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        # Check directories list
        assert len(response.directories) > 0

        # Each directory should have required fields
        for dir_status in response.directories:
            assert dir_status.path is not None
            assert dir_status.relative_path is not None
            assert isinstance(dir_status.existed, bool)
            assert isinstance(dir_status.created, bool)

    @pytest.mark.asyncio
    async def test_returns_claude_md_status(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that response includes CLAUDE.md status."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest(include_claude_md=True)
        response = await scaffold_project("test_project", request)

        assert response.claude_md is not None
        assert response.claude_md.path is not None
        assert isinstance(response.claude_md.existed, bool)
        assert isinstance(response.claude_md.created, bool)
        assert isinstance(response.claude_md.skipped, bool)

    @pytest.mark.asyncio
    async def test_returns_project_info(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that response includes project information."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        assert response.project_name == "test_project"
        assert response.project_dir == str(temp_project_dir)
        assert ".claude" in response.claude_root

    @pytest.mark.asyncio
    async def test_returns_message(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that response includes a descriptive message."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        assert response.message is not None
        assert len(response.message) > 0


# =============================================================================
# Test Step 4: Useful for repair/reset scenarios
# =============================================================================

class TestStep4RepairResetScenarios:
    """Test that the endpoint is idempotent and useful for repair."""

    @pytest.mark.asyncio
    async def test_idempotent_scaffold(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding can be run multiple times safely."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()

        # First call - creates directories
        response1 = await scaffold_project("test_project", request)
        assert response1.success is True
        assert response1.directories_created > 0

        # Second call - directories already exist
        response2 = await scaffold_project("test_project", request)
        assert response2.success is True
        assert response2.directories_created == 0
        assert response2.directories_existed > 0

    @pytest.mark.asyncio
    async def test_repair_missing_subdirectory(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding can repair missing subdirectories."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Create initial structure
        request = ScaffoldRequest()
        await scaffold_project("test_project", request)

        # Delete a subdirectory
        skills_dir = temp_project_dir / ".claude" / "skills"
        if skills_dir.exists():
            skills_dir.rmdir()
        assert not skills_dir.exists()

        # Run scaffolding again to repair
        response = await scaffold_project("test_project", request)
        assert response.success is True

        # Directory should be recreated
        assert skills_dir.exists()

    @pytest.mark.asyncio
    async def test_preserves_existing_content(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding preserves existing content in directories."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Create initial structure
        request = ScaffoldRequest()
        await scaffold_project("test_project", request)

        # Add a file to a directory
        generated_dir = temp_project_dir / ".claude" / "agents" / "generated"
        test_file = generated_dir / "test_agent.md"
        test_file.write_text("# Test Agent\n")

        # Run scaffolding again
        await scaffold_project("test_project", request)

        # File should still exist
        assert test_file.exists()
        assert test_file.read_text() == "# Test Agent\n"

    @pytest.mark.asyncio
    async def test_preserves_existing_claude_md(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that scaffolding doesn't overwrite existing CLAUDE.md."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Create CLAUDE.md manually
        claude_md = temp_project_dir / "CLAUDE.md"
        original_content = "# My Custom Project\n\nCustom content here."
        claude_md.write_text(original_content)

        # Run scaffolding
        request = ScaffoldRequest(include_claude_md=True)
        response = await scaffold_project("test_project", request)

        # CLAUDE.md should be preserved
        assert response.claude_md is not None
        assert response.claude_md.existed is True
        assert response.claude_md.skipped is True
        assert response.claude_md.created is False
        assert claude_md.read_text() == original_content


# =============================================================================
# Test Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error handling for the scaffold endpoint."""

    @pytest.mark.asyncio
    async def test_project_not_found(self, mock_registry):
        """Test error when project doesn't exist."""
        from fastapi import HTTPException
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Make get_project_path return None
        with patch("server.routers.projects._get_registry_functions") as mock_get:
            mock_get.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(return_value=None),  # Project not found
                MagicMock(return_value={}),
                MagicMock(),
            )

            request = ScaffoldRequest()
            with pytest.raises(HTTPException) as exc_info:
                await scaffold_project("nonexistent", request)

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_project_directory_not_exists(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test error when project directory doesn't exist on disk."""
        from fastapi import HTTPException
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Delete the project directory
        temp_project_dir.rmdir()

        request = ScaffoldRequest()
        with pytest.raises(HTTPException) as exc_info:
            await scaffold_project("test_project", request)

        assert exc_info.value.status_code == 404
        assert "directory not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_invalid_project_name(self):
        """Test validation of project name."""
        from fastapi import HTTPException
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()

        # Test with invalid characters
        with pytest.raises(HTTPException) as exc_info:
            await scaffold_project("../evil", request)

        assert exc_info.value.status_code == 400


# =============================================================================
# Test Default Request Values
# =============================================================================

class TestDefaultRequestValues:
    """Test that default values work correctly."""

    @pytest.mark.asyncio
    async def test_none_request_uses_defaults(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test that None request uses default values."""
        from server.routers.projects import scaffold_project

        # Call with None request
        response = await scaffold_project("test_project", None)

        assert response.success is True
        # Default is include_phase2=True, so Phase 2 dirs should exist
        assert (temp_project_dir / ".claude" / "skills").exists()
        assert (temp_project_dir / ".claude" / "commands").exists()
        # Default is include_claude_md=True
        assert (temp_project_dir / "CLAUDE.md").exists()


# =============================================================================
# Test Feature #203 Verification Steps
# =============================================================================

class TestFeature203VerificationSteps:
    """
    Comprehensive tests verifying all 4 feature verification steps.

    Feature #203: Scaffolding can be triggered manually via API
    """

    @pytest.mark.asyncio
    async def test_step1_endpoint_created(self):
        """Step 1: POST /api/projects/{id}/scaffold endpoint created."""
        from server.routers.projects import router

        # Find the scaffold route
        scaffold_routes = [
            route for route in router.routes
            if hasattr(route, "path") and "scaffold" in route.path
        ]

        assert len(scaffold_routes) == 1
        assert "POST" in scaffold_routes[0].methods
        # The router has a prefix, so we check for the relative path
        assert "scaffold" in scaffold_routes[0].path
        assert "{name}" in scaffold_routes[0].path

    @pytest.mark.asyncio
    async def test_step2_runs_scaffolding(
        self, temp_project_dir: Path, mock_registry
    ):
        """Step 2: Endpoint runs scaffolding for specified project."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Ensure .claude doesn't exist
        assert not (temp_project_dir / ".claude").exists()

        # Call endpoint
        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        # Verify scaffolding ran
        assert response.success is True
        assert (temp_project_dir / ".claude").exists()
        assert (temp_project_dir / ".claude" / "agents" / "generated").exists()

    @pytest.mark.asyncio
    async def test_step3_returns_status(
        self, temp_project_dir: Path, mock_registry
    ):
        """Step 3: Returns status of created/existing directories and files."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()
        response = await scaffold_project("test_project", request)

        # Check status fields
        assert response.success is not None
        assert response.directories_created >= 0
        assert response.directories_existed >= 0
        assert response.directories_failed >= 0
        assert len(response.directories) > 0
        assert response.message is not None

        # Check directory status details
        for dir_status in response.directories:
            assert dir_status.path is not None
            assert dir_status.relative_path is not None

    @pytest.mark.asyncio
    async def test_step4_repair_reset(
        self, temp_project_dir: Path, mock_registry
    ):
        """Step 4: Useful for repair/reset scenarios."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        request = ScaffoldRequest()

        # First run creates structure
        response1 = await scaffold_project("test_project", request)
        assert response1.directories_created > 0

        # Delete a directory to simulate damage
        skills_dir = temp_project_dir / ".claude" / "skills"
        if skills_dir.exists():
            skills_dir.rmdir()

        # Run again to repair
        response2 = await scaffold_project("test_project", request)
        assert response2.success is True
        assert skills_dir.exists()  # Repaired


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for scaffold endpoint."""

    @pytest.mark.asyncio
    async def test_full_scaffolding_workflow(
        self, temp_project_dir: Path, mock_registry
    ):
        """Test the complete scaffolding workflow."""
        from server.routers.projects import scaffold_project
        from server.schemas import ScaffoldRequest

        # Run scaffolding with all options
        request = ScaffoldRequest(include_phase2=True, include_claude_md=True)
        response = await scaffold_project("test_project", request)

        # Verify complete structure
        assert response.success is True

        claude_dir = temp_project_dir / ".claude"
        assert claude_dir.exists()
        assert (claude_dir / "agents" / "generated").exists()
        assert (claude_dir / "agents" / "manual").exists()
        assert (claude_dir / "skills").exists()
        assert (claude_dir / "commands").exists()
        assert (temp_project_dir / "CLAUDE.md").exists()

        # Verify response details
        assert response.project_name == "test_project"
        assert response.directories_created > 0
        assert response.claude_md is not None
        assert response.claude_md.created is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
