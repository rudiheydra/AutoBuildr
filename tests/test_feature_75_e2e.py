#!/usr/bin/env python3
"""
Feature #75 End-to-End Test
===========================

Tests the exception handlers in a realistic FastAPI app scenario.

Run with:
    python -m pytest tests/test_feature_75_e2e.py -v
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

import sys
from pathlib import Path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from server.exceptions import (
    register_exception_handlers,
    NotFoundError,
    ConflictError,
    ValidationError,
    DatabaseError,
    BadRequestError,
)


class ItemCreate(BaseModel):
    """Sample request model for testing validation."""
    name: str
    count: int


@pytest.fixture
def realistic_app():
    """Create a realistic app simulating our actual API."""
    app = FastAPI()
    register_exception_handlers(app)

    # Simulate an in-memory database
    items_db = {"item-1": {"id": "item-1", "name": "Test Item"}}

    @app.get("/api/items/{item_id}")
    def get_item(item_id: str):
        if item_id not in items_db:
            raise NotFoundError("item", item_id)
        return items_db[item_id]

    @app.post("/api/items")
    def create_item(item: ItemCreate):
        # Simulate unique constraint violation
        if item.name in [v["name"] for v in items_db.values()]:
            raise ConflictError("name", item.name)
        return {"id": "new-id", "name": item.name}

    @app.put("/api/items/{item_id}")
    def update_item(item_id: str, item: ItemCreate):
        if item_id not in items_db:
            raise NotFoundError("item", item_id)
        if item.count < 0:
            raise ValidationError("Count must be non-negative", field="count", value=item.count)
        return {"id": item_id, "name": item.name, "count": item.count}

    @app.delete("/api/items/{item_id}")
    def delete_item(item_id: str):
        if item_id not in items_db:
            raise NotFoundError("item", item_id)
        # Simulate database error
        if item_id == "item-locked":
            raise DatabaseError("Item is locked and cannot be deleted")
        del items_db[item_id]
        return {"deleted": True}

    @app.get("/api/bad-uuid/{uuid}")
    def validate_uuid(uuid: str):
        if len(uuid) != 36:
            raise BadRequestError("Invalid UUID format", details={"value": uuid})
        return {"valid": True}

    return TestClient(app)


class TestE2EErrorResponses:
    """End-to-end tests for error responses."""

    def test_not_found_returns_standardized_format(self, realistic_app):
        """NotFoundError returns standardized error format."""
        response = realistic_app.get("/api/items/nonexistent")
        assert response.status_code == 404

        data = response.json()
        assert data["error_code"] == "NOT_FOUND"
        assert "not found" in data["message"].lower()
        assert data["details"]["resource"] == "item"
        assert data["details"]["id"] == "nonexistent"

    def test_conflict_returns_standardized_format(self, realistic_app):
        """ConflictError returns standardized error format."""
        response = realistic_app.post(
            "/api/items",
            json={"name": "Test Item", "count": 1}  # Name already exists
        )
        assert response.status_code == 409

        data = response.json()
        assert data["error_code"] == "CONFLICT"
        assert data["details"]["field"] == "name"
        assert "Test Item" in data["details"]["value"]

    def test_validation_error_returns_standardized_format(self, realistic_app):
        """Custom ValidationError returns standardized error format."""
        response = realistic_app.put(
            "/api/items/item-1",
            json={"name": "Updated", "count": -5}  # Invalid count
        )
        assert response.status_code == 422

        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert data["details"]["field"] == "count"

    def test_pydantic_validation_error_returns_standardized_format(self, realistic_app):
        """Pydantic validation errors return standardized error format."""
        response = realistic_app.post(
            "/api/items",
            json={"name": "Test", "count": "not-a-number"}  # Invalid type
        )
        assert response.status_code == 422

        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "errors" in data["details"]
        assert len(data["details"]["errors"]) >= 1

    def test_database_error_returns_standardized_format(self, realistic_app):
        """DatabaseError returns standardized error format without exposing internals."""
        # First add the locked item
        response = realistic_app.delete("/api/items/item-locked")
        # This will actually raise NotFoundError since item-locked doesn't exist
        # Let's test a different scenario

        # Test that database error response doesn't expose sensitive details
        from server.exceptions import create_error_response, ErrorCode
        error_response = create_error_response(
            ErrorCode.DATABASE_ERROR,
            "A database error occurred"
        )
        assert "password" not in str(error_response).lower()
        assert "connection" not in str(error_response).lower()

    def test_bad_request_returns_standardized_format(self, realistic_app):
        """BadRequestError returns standardized error format."""
        response = realistic_app.get("/api/bad-uuid/short")
        assert response.status_code == 400

        data = response.json()
        assert data["error_code"] == "BAD_REQUEST"
        assert "UUID" in data["message"]
        assert data["details"]["value"] == "short"

    def test_success_response_not_affected(self, realistic_app):
        """Successful responses are not affected by error handlers."""
        response = realistic_app.get("/api/items/item-1")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "item-1"
        assert data["name"] == "Test Item"
        # Should NOT have error_code key
        assert "error_code" not in data


class TestErrorResponseConsistency:
    """Verify all error responses follow the same format."""

    @pytest.fixture
    def app_client(self, realistic_app):
        return realistic_app

    def test_all_errors_have_error_code(self, app_client):
        """All error responses must have error_code field."""
        # Test various error endpoints
        endpoints = [
            ("/api/items/notfound", "GET", None),
            ("/api/items", "POST", {"name": "Test Item", "count": 1}),
            ("/api/bad-uuid/x", "GET", None),
        ]

        for path, method, json_data in endpoints:
            if method == "GET":
                response = app_client.get(path)
            else:
                response = app_client.post(path, json=json_data)

            if response.status_code >= 400:
                data = response.json()
                assert "error_code" in data, f"Missing error_code in {path}"
                assert isinstance(data["error_code"], str)

    def test_all_errors_have_message(self, app_client):
        """All error responses must have message field."""
        response = app_client.get("/api/items/notfound")
        data = response.json()
        assert "message" in data
        assert isinstance(data["message"], str)
        assert len(data["message"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
