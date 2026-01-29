"""
Tests for Feature #145: Add GET /api/artifacts/:id metadata endpoint.

Verifies that the metadata endpoint returns artifact metadata (id, run_id,
artifact_type, content_hash, size_bytes, metadata, created_at) without
the actual content body.
"""

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.agentspec_models import AgentRun, AgentSpec, Artifact, Base, generate_uuid


@pytest.fixture(scope="module")
def db_engine():
    """Create an in-memory database engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a fresh database session for each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_spec(db_session):
    """Create a sample AgentSpec for testing."""
    spec = AgentSpec(
        id=generate_uuid(),
        name=f"test-spec-{uuid.uuid4().hex[:8]}",
        display_name="Test Spec",
        objective="Test objective",
        task_type="coding",
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=10,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.flush()
    return spec


@pytest.fixture
def sample_run(db_session, sample_spec):
    """Create a sample AgentRun for testing."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_spec.id,
        status="completed",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        turns_used=5,
        tokens_in=100,
        tokens_out=50,
    )
    db_session.add(run)
    db_session.flush()
    return run


@pytest.fixture
def inline_artifact(db_session, sample_run):
    """Create an artifact with inline content."""
    content = "Hello, this is inline test content."
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    artifact = Artifact(
        id=generate_uuid(),
        run_id=sample_run.id,
        artifact_type="test_result",
        path="/tmp/test_output.log",
        content_inline=content,
        content_hash=content_hash,
        size_bytes=len(content.encode()),
        created_at=datetime.now(timezone.utc),
        artifact_metadata={"test_suite": "unit", "passed": True},
    )
    db_session.add(artifact)
    db_session.flush()
    return artifact


@pytest.fixture
def file_artifact(db_session, sample_run):
    """Create an artifact with file-based content (no inline)."""
    content_hash = hashlib.sha256(b"large file content" * 1000).hexdigest()
    artifact = Artifact(
        id=generate_uuid(),
        run_id=sample_run.id,
        artifact_type="file_change",
        path="/src/main.py",
        content_ref=f".autobuildr/artifacts/{sample_run.id}/{content_hash}.blob",
        content_hash=content_hash,
        size_bytes=18000,
        created_at=datetime.now(timezone.utc),
        artifact_metadata={"lines_added": 50, "lines_removed": 10},
    )
    db_session.add(artifact)
    db_session.flush()
    return artifact


class TestArtifactMetadataEndpointLogic:
    """Test the metadata endpoint logic directly (without HTTP)."""

    def test_step1_metadata_endpoint_exists_in_router(self):
        """Step 1: Verify GET /api/artifacts/{artifact_id} endpoint exists in the router."""
        from server.routers.artifacts import router

        # Find the metadata route (path includes prefix: /api/artifacts/{artifact_id})
        routes = [r for r in router.routes if hasattr(r, 'path')]
        metadata_route = None
        for route in routes:
            # Check for the metadata endpoint (not the content one)
            if "artifact_id" in route.path and "content" not in route.path and "GET" in route.methods:
                metadata_route = route
                break

        assert metadata_route is not None, (
            "GET /api/artifacts/{artifact_id} endpoint not found in router"
        )
        assert metadata_route.endpoint.__name__ == "get_artifact_metadata"

    def test_step2_metadata_returns_correct_fields_for_inline_artifact(
        self, db_session, inline_artifact
    ):
        """Step 2: Verify endpoint returns correct metadata for inline artifact."""
        from api.agentspec_crud import get_artifact
        from server.schemas.agentspec import ArtifactListItemResponse

        artifact = get_artifact(db_session, inline_artifact.id)
        assert artifact is not None

        # Build the response the same way the endpoint does
        response = ArtifactListItemResponse(
            id=artifact.id,
            run_id=artifact.run_id,
            artifact_type=artifact.artifact_type,
            path=artifact.path,
            content_ref=artifact.content_ref,
            content_hash=artifact.content_hash,
            size_bytes=artifact.size_bytes,
            created_at=artifact.created_at,
            metadata=artifact.artifact_metadata,
            has_inline_content=artifact.content_inline is not None and len(artifact.content_inline) > 0,
        )

        # Verify all required metadata fields
        assert response.id == inline_artifact.id
        assert response.run_id == inline_artifact.run_id
        assert response.artifact_type == "test_result"
        assert response.content_hash == inline_artifact.content_hash
        assert response.size_bytes == len("Hello, this is inline test content.".encode())
        assert response.metadata == {"test_suite": "unit", "passed": True}
        assert response.created_at is not None
        assert response.has_inline_content is True

        # Verify response does NOT contain content_inline field
        response_dict = response.model_dump()
        assert "content_inline" not in response_dict, (
            "Metadata endpoint should NOT include content_inline"
        )

    def test_step3_metadata_returns_correct_fields_for_file_artifact(
        self, db_session, file_artifact
    ):
        """Step 3: Verify endpoint returns correct metadata for file-based artifact."""
        from api.agentspec_crud import get_artifact
        from server.schemas.agentspec import ArtifactListItemResponse

        artifact = get_artifact(db_session, file_artifact.id)
        assert artifact is not None

        response = ArtifactListItemResponse(
            id=artifact.id,
            run_id=artifact.run_id,
            artifact_type=artifact.artifact_type,
            path=artifact.path,
            content_ref=artifact.content_ref,
            content_hash=artifact.content_hash,
            size_bytes=artifact.size_bytes,
            created_at=artifact.created_at,
            metadata=artifact.artifact_metadata,
            has_inline_content=artifact.content_inline is not None
            and len(artifact.content_inline) > 0 if artifact.content_inline else False,
        )

        # Verify all required metadata fields
        assert response.id == file_artifact.id
        assert response.run_id == file_artifact.run_id
        assert response.artifact_type == "file_change"
        assert response.content_hash == file_artifact.content_hash
        assert response.size_bytes == 18000
        assert response.metadata == {"lines_added": 50, "lines_removed": 10}
        assert response.created_at is not None
        assert response.content_ref is not None
        assert response.has_inline_content is False

    def test_step4_metadata_returns_404_for_nonexistent_artifact(self, db_session):
        """Step 4: Verify endpoint returns 404 for non-existent artifacts."""
        from api.agentspec_crud import get_artifact

        fake_id = "nonexistent-" + uuid.uuid4().hex[:20]
        artifact = get_artifact(db_session, fake_id)
        assert artifact is None, "Non-existent artifact should return None"

    def test_step5_response_schema_includes_all_metadata_fields(self):
        """Step 5: Verify the response schema includes all required metadata fields."""
        from server.schemas.agentspec import ArtifactListItemResponse

        # Check that the schema has all required metadata fields
        fields = ArtifactListItemResponse.model_fields
        required_fields = [
            "id", "run_id", "artifact_type", "content_hash",
            "size_bytes", "metadata", "created_at",
        ]
        for field_name in required_fields:
            assert field_name in fields, (
                f"ArtifactListItemResponse missing required field: {field_name}"
            )

        # Verify content_inline is NOT in the schema
        assert "content_inline" not in fields, (
            "ArtifactListItemResponse should NOT contain content_inline"
        )


class TestArtifactMetadataEndpointHTTP:
    """Test the metadata endpoint via FastAPI TestClient."""

    @pytest.fixture
    def client(self, db_session, inline_artifact, file_artifact):
        """Create a FastAPI TestClient with the artifacts router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from server.routers.artifacts import router

        app = FastAPI()
        app.include_router(router)

        # Override the get_db dependency
        def override_get_db():
            yield db_session

        from api.database import get_db
        app.dependency_overrides[get_db] = override_get_db

        return TestClient(app)

    def test_http_get_inline_artifact_metadata(self, client, inline_artifact):
        """HTTP test: GET metadata for inline artifact returns 200 with correct JSON."""
        response = client.get(f"/api/artifacts/{inline_artifact.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == inline_artifact.id
        assert data["run_id"] == inline_artifact.run_id
        assert data["artifact_type"] == "test_result"
        assert data["content_hash"] == inline_artifact.content_hash
        assert data["size_bytes"] == inline_artifact.size_bytes
        assert data["metadata"] == {"test_suite": "unit", "passed": True}
        assert data["created_at"] is not None
        assert data["has_inline_content"] is True

        # Must NOT include content_inline
        assert "content_inline" not in data

    def test_http_get_file_artifact_metadata(self, client, file_artifact):
        """HTTP test: GET metadata for file-based artifact returns 200 with correct JSON."""
        response = client.get(f"/api/artifacts/{file_artifact.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == file_artifact.id
        assert data["run_id"] == file_artifact.run_id
        assert data["artifact_type"] == "file_change"
        assert data["content_hash"] == file_artifact.content_hash
        assert data["size_bytes"] == 18000
        assert data["metadata"] == {"lines_added": 50, "lines_removed": 10}
        assert data["content_ref"] is not None
        assert data["has_inline_content"] is False

    def test_http_get_nonexistent_artifact_returns_404(self, client):
        """HTTP test: GET metadata for non-existent artifact returns 404."""
        fake_id = "nonexistent-" + uuid.uuid4().hex[:20]
        response = client.get(f"/api/artifacts/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_http_metadata_and_content_endpoints_coexist(self, client, inline_artifact):
        """HTTP test: Both metadata and content endpoints work correctly."""
        # Metadata endpoint (no content body)
        meta_response = client.get(f"/api/artifacts/{inline_artifact.id}")
        assert meta_response.status_code == 200
        meta_data = meta_response.json()
        assert "content_inline" not in meta_data

        # Content endpoint (actual content)
        content_response = client.get(f"/api/artifacts/{inline_artifact.id}/content")
        assert content_response.status_code == 200
        # Content response returns actual file bytes/text, not JSON
        assert content_response.text == "Hello, this is inline test content."
