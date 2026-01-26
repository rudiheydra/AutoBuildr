"""
Feature #21: GET /api/artifacts/:id/content Download Content
============================================================

Tests for the artifact content download endpoint.

Verification Steps:
1. Define FastAPI route GET /api/artifacts/{artifact_id}/content
2. Query Artifact by id
3. Return 404 if not found
4. If content_inline is set, return it as response body
5. If content_ref is set, verify file exists
6. Stream file content with appropriate Content-Type
7. Set Content-Disposition header for download
8. Handle missing file gracefully with 404
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.testclient import TestClient


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_artifact_inline():
    """Create a mock artifact with inline content."""
    artifact = MagicMock()
    artifact.id = "test-artifact-inline-123"
    artifact.artifact_type = "test_result"
    artifact.path = "/test/output.log"
    artifact.content_inline = "Test result: 10/10 tests passed"
    artifact.content_ref = None
    artifact.content_hash = "abc123def456"
    return artifact


@pytest.fixture
def mock_artifact_file():
    """Create a mock artifact with file-based content."""
    artifact = MagicMock()
    artifact.id = "test-artifact-file-456"
    artifact.artifact_type = "log"
    artifact.path = "/test/large_output.log"
    artifact.content_inline = None
    artifact.content_ref = ".autobuildr/artifacts/test-run/abc123.blob"
    artifact.content_hash = "xyz789abc012"
    return artifact


@pytest.fixture
def mock_artifact_no_path():
    """Create a mock artifact without a path."""
    artifact = MagicMock()
    artifact.id = "test-artifact-nopath-789"
    artifact.artifact_type = "snapshot"
    artifact.path = None
    artifact.content_inline = "Snapshot data"
    artifact.content_ref = None
    artifact.content_hash = "snap123hash"
    return artifact


@pytest.fixture
def temp_artifact_file():
    """Create a temporary file to use as artifact content."""
    content = b"Large artifact content for streaming test\n" * 100
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.blob') as f:
        f.write(content)
        filepath = f.name
    yield filepath, content
    # Cleanup
    try:
        os.unlink(filepath)
    except:
        pass


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


def create_test_app():
    """Create a FastAPI app with the artifacts router for testing."""
    from server.routers.artifacts import router
    app = FastAPI()
    app.include_router(router)
    return app


def get_test_client(mock_get_artifact, mock_db=None):
    """Create a test client with mocked dependencies."""
    app = create_test_app()

    # Override the database dependency
    def override_get_db():
        if mock_db is None:
            return MagicMock()
        return mock_db

    from api.database import get_db
    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app)


# =============================================================================
# Step 1: Define FastAPI route GET /api/artifacts/{artifact_id}/content
# =============================================================================

class TestRouteDefinition:
    """Test that the route is properly defined."""

    def test_route_exists_in_artifacts_router(self):
        """Verify the route is defined in the artifacts router."""
        from server.routers.artifacts import router

        # Check router has routes
        routes = [route.path for route in router.routes]
        # The full path includes the prefix
        assert any("/content" in path for path in routes), \
            f"Expected '/content' in routes, got: {routes}"

    def test_route_is_get_method(self):
        """Verify the route uses GET method."""
        from server.routers.artifacts import router

        for route in router.routes:
            if "content" in route.path:
                assert "GET" in route.methods
                break
        else:
            pytest.fail("Route with /content not found")

    def test_router_has_correct_prefix(self):
        """Verify router has /api/artifacts prefix."""
        from server.routers.artifacts import router
        assert router.prefix == "/api/artifacts"

    def test_router_registered_in_main_app(self):
        """Verify the artifacts router is registered in main app."""
        from server.main import app

        # Check if artifacts routes are in the app
        artifact_routes = [
            route.path for route in app.routes
            if hasattr(route, 'path') and '/api/artifacts' in route.path
        ]
        assert len(artifact_routes) > 0, "No artifact routes found in main app"


# =============================================================================
# Step 2: Query Artifact by id
# =============================================================================

class TestArtifactQuery:
    """Test artifact query functionality."""

    def test_query_artifact_by_id_called(self, mock_artifact_inline):
        """Verify get_artifact is called with correct ID."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][1] == "test-artifact-inline-123"


# =============================================================================
# Step 3: Return 404 if not found
# =============================================================================

class TestNotFoundHandling:
    """Test 404 handling for missing artifacts."""

    def test_returns_404_when_artifact_not_found(self):
        """Verify 404 is returned when artifact doesn't exist."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = None

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/nonexistent-id/content")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_404_includes_artifact_id_in_message(self):
        """Verify 404 message includes the artifact ID."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = None

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/missing-123/content")

            assert "missing-123" in response.json()["detail"]


# =============================================================================
# Step 4: If content_inline is set, return it as response body
# =============================================================================

class TestInlineContentReturn:
    """Test inline content retrieval."""

    def test_returns_inline_content_as_body(self, mock_artifact_inline):
        """Verify inline content is returned in response body."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            assert response.status_code == 200
            assert response.text == "Test result: 10/10 tests passed"

    def test_inline_content_uses_text_plain_content_type(self, mock_artifact_inline):
        """Verify inline content uses appropriate content type."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            # Should be text/plain or use mime type from path
            assert "text/" in response.headers["content-type"]

    def test_inline_content_includes_artifact_id_header(self, mock_artifact_inline):
        """Verify response includes X-Artifact-Id header."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            assert "x-artifact-id" in response.headers
            assert response.headers["x-artifact-id"] == "test-artifact-inline-123"


# =============================================================================
# Step 5: If content_ref is set, verify file exists
# =============================================================================

class TestFileExistenceVerification:
    """Test file existence verification for file-based artifacts."""

    def test_returns_404_when_referenced_file_missing(self, mock_artifact_file):
        """Verify 404 is returned when content_ref file doesn't exist."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_file

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-file-456/content")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_404_for_missing_file_includes_content_ref(self, mock_artifact_file):
        """Verify 404 message includes content_ref path."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_file

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-file-456/content")

            # Should mention the file path in error
            detail = response.json()["detail"]
            assert ".autobuildr" in detail or "abc123" in detail


# =============================================================================
# Step 6: Stream file content with appropriate Content-Type
# =============================================================================

class TestFileStreaming:
    """Test file streaming functionality."""

    def test_streams_file_content(self, mock_artifact_file, temp_artifact_file):
        """Verify file content is streamed correctly."""
        filepath, content = temp_artifact_file
        mock_artifact_file.content_ref = filepath

        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_file
            with patch('server.routers.artifacts.ROOT_DIR', Path("/")):

                client = get_test_client(mock_get)
                response = client.get("/api/artifacts/test-artifact-file-456/content")

                assert response.status_code == 200
                assert response.content == content

    def test_guesses_content_type_from_path(self, mock_artifact_file, temp_artifact_file):
        """Verify content type is guessed from path."""
        filepath, content = temp_artifact_file
        mock_artifact_file.content_ref = filepath
        mock_artifact_file.path = "/test/output.json"

        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_file
            with patch('server.routers.artifacts.ROOT_DIR', Path("/")):

                client = get_test_client(mock_get)
                response = client.get("/api/artifacts/test-artifact-file-456/content")

                assert response.status_code == 200
                # JSON mime type should be detected
                assert "json" in response.headers["content-type"]


# =============================================================================
# Step 7: Set Content-Disposition header for download
# =============================================================================

class TestContentDisposition:
    """Test Content-Disposition header for downloads."""

    def test_sets_content_disposition_header(self, mock_artifact_inline):
        """Verify Content-Disposition header is set."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            assert "content-disposition" in response.headers

    def test_content_disposition_includes_filename(self, mock_artifact_inline):
        """Verify Content-Disposition includes filename from path."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            disposition = response.headers["content-disposition"]
            assert "output.log" in disposition

    def test_content_disposition_is_attachment(self, mock_artifact_inline):
        """Verify Content-Disposition specifies attachment."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            disposition = response.headers["content-disposition"]
            assert "attachment" in disposition.lower()

    def test_generates_filename_when_path_missing(self, mock_artifact_no_path):
        """Verify filename is generated when path is not set."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_no_path

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-nopath-789/content")

            disposition = response.headers["content-disposition"]
            # Should generate a filename using artifact_type and hash
            assert "snapshot" in disposition.lower() or "snap123" in disposition


# =============================================================================
# Step 8: Handle missing file gracefully with 404
# =============================================================================

class TestMissingFileHandling:
    """Test graceful handling of missing files."""

    def test_handles_missing_content_ref_gracefully(self):
        """Verify graceful 404 when content_ref is None and no inline content."""
        artifact = MagicMock()
        artifact.id = "empty-artifact"
        artifact.artifact_type = "log"
        artifact.path = None
        artifact.content_inline = None
        artifact.content_ref = None
        artifact.content_hash = None

        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = artifact

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/empty-artifact/content")

            assert response.status_code == 404
            assert "no content" in response.json()["detail"].lower()

    def test_returns_content_hash_header(self, mock_artifact_inline):
        """Verify X-Content-Hash header is set."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            assert "x-content-hash" in response.headers
            assert response.headers["x-content-hash"] == "abc123def456"


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests using the full app."""

    def test_endpoint_accessible_via_main_app(self, mock_artifact_inline):
        """Verify endpoint is accessible via the main app."""
        # This test verifies that the router is registered in main app
        # We test this by checking the route exists rather than making an
        # HTTP request, since the main app has security middleware that
        # complicates testing
        from server.main import app

        # Check if artifacts routes are in the app
        artifact_routes = [
            route.path for route in app.routes
            if hasattr(route, 'path') and '/api/artifacts' in route.path
        ]
        assert any('/content' in path for path in artifact_routes), \
            f"Expected content endpoint in routes, got: {artifact_routes}"

    def test_response_includes_content_length(self, mock_artifact_inline):
        """Verify response includes Content-Length header."""
        with patch('server.routers.artifacts.get_artifact') as mock_get:
            mock_get.return_value = mock_artifact_inline

            client = get_test_client(mock_get)
            response = client.get("/api/artifacts/test-artifact-inline-123/content")

            assert "content-length" in response.headers
            expected_length = len("Test result: 10/10 tests passed".encode("utf-8"))
            assert int(response.headers["content-length"]) == expected_length


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
