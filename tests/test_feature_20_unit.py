#!/usr/bin/env python3
"""
Unit tests for Feature #20: GET /api/agent-runs/:id/artifacts

Tests the endpoint implementation without needing a running server.
"""

import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest

# Test the schemas
def test_artifact_list_item_response_excludes_content_inline():
    """Verify ArtifactListItemResponse doesn't include content_inline field."""
    from server.schemas.agentspec import ArtifactListItemResponse

    fields = ArtifactListItemResponse.model_fields
    field_names = list(fields.keys())

    assert 'content_inline' not in field_names, "content_inline should not be in ArtifactListItemResponse"
    assert 'has_inline_content' in field_names, "has_inline_content should be in ArtifactListItemResponse"


def test_artifact_list_item_response_has_all_metadata_fields():
    """Verify ArtifactListItemResponse has all required fields."""
    from server.schemas.agentspec import ArtifactListItemResponse

    fields = ArtifactListItemResponse.model_fields
    required_fields = [
        'id', 'run_id', 'artifact_type', 'path', 'content_ref',
        'content_hash', 'size_bytes', 'created_at', 'metadata', 'has_inline_content'
    ]

    for field in required_fields:
        assert field in fields, f"Field '{field}' missing from ArtifactListItemResponse"


def test_artifact_list_response_uses_list_item_schema():
    """Verify ArtifactListResponse uses ArtifactListItemResponse for artifacts."""
    from server.schemas.agentspec import ArtifactListResponse, ArtifactListItemResponse

    artifacts_field = ArtifactListResponse.model_fields['artifacts']
    annotation_str = str(artifacts_field.annotation)

    assert 'ArtifactListItemResponse' in annotation_str, \
        f"ArtifactListResponse.artifacts should use ArtifactListItemResponse, got {annotation_str}"


def test_artifact_list_response_has_run_id():
    """Verify ArtifactListResponse includes run_id field."""
    from server.schemas.agentspec import ArtifactListResponse

    fields = ArtifactListResponse.model_fields
    assert 'run_id' in fields, "ArtifactListResponse should have run_id field"


def test_artifact_list_response_has_total():
    """Verify ArtifactListResponse includes total field."""
    from server.schemas.agentspec import ArtifactListResponse

    fields = ArtifactListResponse.model_fields
    assert 'total' in fields, "ArtifactListResponse should have total field"


def test_artifact_list_item_validation():
    """Test creating ArtifactListItemResponse with valid data."""
    from server.schemas.agentspec import ArtifactListItemResponse

    item = ArtifactListItemResponse(
        id="test-artifact-id",
        run_id="test-run-id",
        artifact_type="test_result",
        path="/test/path.txt",
        content_ref=None,
        content_hash="abc123",
        size_bytes=100,
        created_at=datetime.now(timezone.utc),
        metadata={"key": "value"},
        has_inline_content=True,
    )

    assert item.id == "test-artifact-id"
    assert item.artifact_type == "test_result"
    assert item.has_inline_content == True


def test_artifact_list_item_invalid_type():
    """Test that invalid artifact_type is rejected."""
    from server.schemas.agentspec import ArtifactListItemResponse
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        ArtifactListItemResponse(
            id="test-artifact-id",
            run_id="test-run-id",
            artifact_type="invalid_type",  # Invalid
            created_at=datetime.now(timezone.utc),
            has_inline_content=False,
        )

    assert "artifact_type" in str(exc_info.value)


def test_artifact_list_response_creation():
    """Test creating ArtifactListResponse with items."""
    from server.schemas.agentspec import ArtifactListResponse, ArtifactListItemResponse

    items = [
        ArtifactListItemResponse(
            id="artifact-1",
            run_id="run-1",
            artifact_type="test_result",
            created_at=datetime.now(timezone.utc),
            has_inline_content=True,
        ),
        ArtifactListItemResponse(
            id="artifact-2",
            run_id="run-1",
            artifact_type="log",
            created_at=datetime.now(timezone.utc),
            has_inline_content=False,
        ),
    ]

    response = ArtifactListResponse(
        artifacts=items,
        total=2,
        run_id="run-1",
    )

    assert len(response.artifacts) == 2
    assert response.total == 2
    assert response.run_id == "run-1"


# Test the endpoint function signature
def test_get_run_artifacts_endpoint_exists():
    """Verify the get_run_artifacts endpoint exists."""
    from server.routers.agent_runs import get_run_artifacts

    assert callable(get_run_artifacts)


def test_get_run_artifacts_has_artifact_type_param():
    """Verify get_run_artifacts has artifact_type parameter."""
    import inspect
    from server.routers.agent_runs import get_run_artifacts

    sig = inspect.signature(get_run_artifacts)
    params = sig.parameters

    assert 'artifact_type' in params, "get_run_artifacts should have artifact_type parameter"


def test_get_run_artifacts_has_run_id_param():
    """Verify get_run_artifacts has run_id parameter."""
    import inspect
    from server.routers.agent_runs import get_run_artifacts

    sig = inspect.signature(get_run_artifacts)
    params = sig.parameters

    assert 'run_id' in params, "get_run_artifacts should have run_id parameter"


# Test the router registration
def test_artifacts_route_registered():
    """Verify the /artifacts route is registered in the router."""
    from server.routers.agent_runs import router

    artifacts_route = None
    for route in router.routes:
        if hasattr(route, 'path') and '/artifacts' in route.path:
            artifacts_route = route
            break

    assert artifacts_route is not None, "/artifacts route not found in router"
    assert 'GET' in artifacts_route.methods, "Route should support GET method"


def test_artifacts_route_response_model():
    """Verify the /artifacts route has correct response model."""
    from server.routers.agent_runs import router
    from server.schemas.agentspec import ArtifactListResponse

    for route in router.routes:
        if hasattr(route, 'path') and '/artifacts' in route.path:
            # The response model should be ArtifactListResponse
            assert hasattr(route, 'response_model')
            assert route.response_model == ArtifactListResponse
            break


# Test the CRUD function
def test_list_artifacts_function_exists():
    """Verify list_artifacts CRUD function exists."""
    from api.agentspec_crud import list_artifacts

    assert callable(list_artifacts)


def test_list_artifacts_accepts_artifact_type():
    """Verify list_artifacts accepts artifact_type filter."""
    import inspect
    from api.agentspec_crud import list_artifacts

    sig = inspect.signature(list_artifacts)
    params = sig.parameters

    assert 'artifact_type' in params, "list_artifacts should accept artifact_type parameter"


def test_valid_artifact_types_constant():
    """Verify valid artifact types are defined."""
    from api.agentspec_models import ARTIFACT_TYPES

    expected_types = ["file_change", "test_result", "log", "metric", "snapshot"]
    for t in expected_types:
        assert t in ARTIFACT_TYPES, f"Missing artifact type: {t}"


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v"])
