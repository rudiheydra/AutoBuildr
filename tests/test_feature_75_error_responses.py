"""
Tests for Feature #75: Standardized API Error Responses

This test suite verifies:
1. ErrorResponse Pydantic model structure
2. Custom exception classes (NotFoundError, ConflictError, ValidationError, DatabaseError)
3. Exception handlers convert errors to standardized format
4. HTTP status codes are correctly mapped

Run with:
    pytest tests/test_feature_75_error_responses.py -v
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError, OperationalError

# Import the module under test
import sys
from pathlib import Path
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from server.exceptions import (
    # Response model
    ErrorResponse,
    # Error codes
    ErrorCode,
    # Exception classes
    APIError,
    NotFoundError,
    ConflictError,
    ValidationError,
    DatabaseError,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    # Handlers
    api_error_handler,
    validation_error_handler,
    http_exception_handler,
    sqlalchemy_error_handler,
    generic_exception_handler,
    # Helper
    create_error_response,
    register_exception_handlers,
)


# =============================================================================
# Step 1 & 2: ErrorResponse Pydantic Model Tests
# =============================================================================


class TestErrorResponseModel:
    """Tests for the ErrorResponse Pydantic model."""

    def test_error_response_required_fields(self):
        """Step 2: ErrorResponse has error_code and message as required fields."""
        response = ErrorResponse(
            error_code="TEST_ERROR",
            message="Test error message"
        )
        assert response.error_code == "TEST_ERROR"
        assert response.message == "Test error message"
        assert response.details is None

    def test_error_response_with_details(self):
        """Step 2: ErrorResponse supports optional details dict."""
        response = ErrorResponse(
            error_code="NOT_FOUND",
            message="Resource not found",
            details={"resource": "feature", "id": 123}
        )
        assert response.error_code == "NOT_FOUND"
        assert response.message == "Resource not found"
        assert response.details == {"resource": "feature", "id": 123}

    def test_error_response_serialization(self):
        """ErrorResponse serializes to correct JSON format."""
        response = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Validation failed",
            details={"field": "name", "value": ""}
        )
        json_dict = response.model_dump()

        assert json_dict == {
            "error_code": "VALIDATION_ERROR",
            "message": "Validation failed",
            "details": {"field": "name", "value": ""}
        }

    def test_error_response_without_details_serialization(self):
        """ErrorResponse without details serializes correctly."""
        response = ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="Something went wrong"
        )
        json_dict = response.model_dump()

        assert json_dict == {
            "error_code": "INTERNAL_ERROR",
            "message": "Something went wrong",
            "details": None
        }

    def test_error_response_missing_required_field(self):
        """ErrorResponse raises validation error if required fields are missing."""
        with pytest.raises(PydanticValidationError):
            ErrorResponse(error_code="TEST")  # Missing message

        with pytest.raises(PydanticValidationError):
            ErrorResponse(message="Test")  # Missing error_code

    def test_error_code_is_string(self):
        """error_code must be a string."""
        response = ErrorResponse(
            error_code="CUSTOM_ERROR_CODE",
            message="Custom error"
        )
        assert isinstance(response.error_code, str)

    def test_message_is_string(self):
        """message must be a string."""
        response = ErrorResponse(
            error_code="ERROR",
            message="This is the error message"
        )
        assert isinstance(response.message, str)


# =============================================================================
# Error Code Constants Tests
# =============================================================================


class TestErrorCodes:
    """Tests for ErrorCode constants."""

    def test_error_codes_exist(self):
        """All expected error codes are defined."""
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.NOT_FOUND == "NOT_FOUND"
        assert ErrorCode.CONFLICT == "CONFLICT"
        assert ErrorCode.DATABASE_ERROR == "DATABASE_ERROR"
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"
        assert ErrorCode.BAD_REQUEST == "BAD_REQUEST"
        assert ErrorCode.UNAUTHORIZED == "UNAUTHORIZED"
        assert ErrorCode.FORBIDDEN == "FORBIDDEN"


# =============================================================================
# Step 3: Custom Exception Classes Tests
# =============================================================================


class TestAPIError:
    """Tests for the base APIError class."""

    def test_api_error_creation(self):
        """APIError can be created with all parameters."""
        error = APIError(
            error_code="TEST_ERROR",
            message="Test message",
            status_code=418,
            details={"key": "value"}
        )
        assert error.error_code == "TEST_ERROR"
        assert error.message == "Test message"
        assert error.status_code == 418
        assert error.details == {"key": "value"}

    def test_api_error_to_response(self):
        """APIError converts to ErrorResponse."""
        error = APIError(
            error_code="TEST",
            message="Test",
            details={"test": True}
        )
        response = error.to_response()

        assert isinstance(response, ErrorResponse)
        assert response.error_code == "TEST"
        assert response.message == "Test"
        assert response.details == {"test": True}


class TestNotFoundError:
    """Step 5: Tests for NotFoundError -> 404."""

    def test_not_found_error_basic(self):
        """NotFoundError with resource name only."""
        error = NotFoundError("feature")
        assert error.error_code == ErrorCode.NOT_FOUND
        assert error.status_code == 404
        assert "Feature" in error.message

    def test_not_found_error_with_id(self):
        """NotFoundError with resource and identifier."""
        error = NotFoundError("feature", 123)
        assert error.message == "Feature '123' not found"
        assert error.details == {"resource": "feature", "id": 123}

    def test_not_found_error_custom_message(self):
        """NotFoundError with custom message."""
        error = NotFoundError("project", "test", "Custom not found message")
        assert error.message == "Custom not found message"

    def test_not_found_error_status_code(self):
        """NotFoundError has 404 status code."""
        error = NotFoundError("resource")
        assert error.status_code == 404


class TestConflictError:
    """Step 6: Tests for ConflictError -> 409."""

    def test_conflict_error_with_field_and_value(self):
        """ConflictError with field and value."""
        error = ConflictError("name", "my-spec")
        assert error.error_code == ErrorCode.CONFLICT
        assert error.status_code == 409
        assert error.details == {"field": "name", "value": "my-spec"}

    def test_conflict_error_custom_message(self):
        """ConflictError with custom message."""
        error = ConflictError("name", "test", "Name already taken")
        assert error.message == "Name already taken"

    def test_conflict_error_generic(self):
        """ConflictError without field or value."""
        error = ConflictError()
        assert "conflict" in error.message.lower()


class TestValidationError:
    """Step 4: Tests for ValidationError -> 422 with field details."""

    def test_validation_error_single_field(self):
        """ValidationError with single field."""
        error = ValidationError(
            "max_turns must be at least 1",
            field="max_turns",
            value=0
        )
        assert error.error_code == ErrorCode.VALIDATION_ERROR
        assert error.status_code == 422
        assert error.details["field"] == "max_turns"

    def test_validation_error_multiple_errors(self):
        """ValidationError with multiple errors."""
        errors = [
            {"field": "name", "message": "Name required"},
            {"field": "description", "message": "Description too long"}
        ]
        error = ValidationError("Multiple validation errors", errors=errors)
        assert error.details["errors"] == errors

    def test_validation_error_value_truncation(self):
        """ValidationError truncates long values."""
        long_value = "x" * 200
        error = ValidationError("Too long", field="description", value=long_value)
        # Value should be truncated to 100 chars
        assert len(error.details["value"]) == 100


class TestDatabaseError:
    """Step 7: Tests for DatabaseError -> 500."""

    def test_database_error_default_message(self):
        """DatabaseError with default message."""
        error = DatabaseError()
        assert error.error_code == ErrorCode.DATABASE_ERROR
        assert error.status_code == 500
        assert "database error" in error.message.lower()

    def test_database_error_custom_message(self):
        """DatabaseError with custom message."""
        error = DatabaseError("Failed to save feature")
        assert error.message == "Failed to save feature"

    def test_database_error_with_operation(self):
        """DatabaseError with operation context."""
        error = DatabaseError("Query failed", operation="SELECT")
        assert error.details == {"operation": "SELECT"}


class TestBadRequestError:
    """Tests for BadRequestError."""

    def test_bad_request_error(self):
        """BadRequestError basic functionality."""
        error = BadRequestError("Invalid UUID format")
        assert error.error_code == ErrorCode.BAD_REQUEST
        assert error.status_code == 400
        assert error.message == "Invalid UUID format"


class TestUnauthorizedError:
    """Tests for UnauthorizedError."""

    def test_unauthorized_error_default(self):
        """UnauthorizedError with default message."""
        error = UnauthorizedError()
        assert error.error_code == ErrorCode.UNAUTHORIZED
        assert error.status_code == 401

    def test_unauthorized_error_custom_message(self):
        """UnauthorizedError with custom message."""
        error = UnauthorizedError("API key required")
        assert error.message == "API key required"


class TestForbiddenError:
    """Tests for ForbiddenError."""

    def test_forbidden_error_default(self):
        """ForbiddenError with default message."""
        error = ForbiddenError()
        assert error.error_code == ErrorCode.FORBIDDEN
        assert error.status_code == 403

    def test_forbidden_error_custom_message(self):
        """ForbiddenError with custom message."""
        error = ForbiddenError("You cannot delete this project")
        assert error.message == "You cannot delete this project"


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestCreateErrorResponse:
    """Tests for the create_error_response helper."""

    def test_create_error_response_basic(self):
        """create_error_response with required fields only."""
        response = create_error_response("ERROR", "Message")
        assert response == {"error_code": "ERROR", "message": "Message"}

    def test_create_error_response_with_details(self):
        """create_error_response with details."""
        response = create_error_response(
            "ERROR",
            "Message",
            details={"key": "value"}
        )
        assert response == {
            "error_code": "ERROR",
            "message": "Message",
            "details": {"key": "value"}
        }


# =============================================================================
# Step 8: Exception Handler Integration Tests
# =============================================================================


class TestExceptionHandlerIntegration:
    """Step 8: Tests for global exception handlers."""

    @pytest.fixture
    def test_app(self):
        """Create a test FastAPI app with exception handlers."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/api_error")
        def raise_api_error():
            raise NotFoundError("feature", 123)

        @app.get("/conflict")
        def raise_conflict():
            raise ConflictError("name", "test")

        @app.get("/validation")
        def raise_validation():
            raise ValidationError("Field required", field="name")

        @app.get("/database")
        def raise_database():
            raise DatabaseError("Connection failed")

        @app.get("/http_404")
        def raise_http_404():
            raise HTTPException(status_code=404, detail="Not found")

        @app.get("/http_400")
        def raise_http_400():
            raise HTTPException(status_code=400, detail="Bad request")

        @app.post("/validate")
        def validate_input(data: dict):
            return {"received": data}

        return TestClient(app)

    def test_api_error_handler_not_found(self, test_app):
        """NotFoundError returns 404 with standardized response."""
        response = test_app.get("/api_error")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "NOT_FOUND"
        assert "Feature '123' not found" in data["message"]
        assert data["details"]["resource"] == "feature"

    def test_api_error_handler_conflict(self, test_app):
        """ConflictError returns 409 with standardized response."""
        response = test_app.get("/conflict")
        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "CONFLICT"

    def test_api_error_handler_validation(self, test_app):
        """ValidationError returns 422 with field details."""
        response = test_app.get("/validation")
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert data["details"]["field"] == "name"

    def test_api_error_handler_database(self, test_app):
        """DatabaseError returns 500 with standardized response."""
        response = test_app.get("/database")
        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "DATABASE_ERROR"

    def test_http_exception_handler_404(self, test_app):
        """HTTPException 404 returns standardized response."""
        response = test_app.get("/http_404")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "NOT_FOUND"

    def test_http_exception_handler_400(self, test_app):
        """HTTPException 400 returns standardized response."""
        response = test_app.get("/http_400")
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "BAD_REQUEST"

    def test_pydantic_validation_error(self, test_app):
        """Pydantic validation errors return 422 with field details."""
        # Send invalid JSON to trigger Pydantic validation
        response = test_app.post(
            "/validate",
            content="not json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert "errors" in data["details"]


# =============================================================================
# SQLAlchemy Error Handler Tests
# =============================================================================


class TestSQLAlchemyErrorHandler:
    """Tests for SQLAlchemy-specific error handling."""

    @pytest.fixture
    def test_app(self):
        """Create a test app that can raise SQLAlchemy errors."""
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/unique_constraint")
        def raise_unique_constraint():
            # Simulate IntegrityError with UNIQUE constraint message
            class MockOrig:
                def __str__(self):
                    return "UNIQUE constraint failed: agent_specs.name"

            error = IntegrityError(
                "statement",
                {},
                MockOrig()
            )
            raise error

        @app.get("/foreign_key")
        def raise_foreign_key():
            class MockOrig:
                def __str__(self):
                    return "FOREIGN KEY constraint failed"

            error = IntegrityError(
                "statement",
                {},
                MockOrig()
            )
            raise error

        @app.get("/operational")
        def raise_operational():
            raise OperationalError(
                "statement",
                {},
                Exception("database locked")
            )

        return TestClient(app)

    def test_unique_constraint_returns_409(self, test_app):
        """UNIQUE constraint violation returns 409 Conflict."""
        response = test_app.get("/unique_constraint")
        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "CONFLICT"
        assert "Duplicate" in data["message"] or "already exists" in data["message"]

    def test_foreign_key_returns_400(self, test_app):
        """FOREIGN KEY constraint violation returns 400."""
        response = test_app.get("/foreign_key")
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "BAD_REQUEST"
        assert "reference" in data["message"].lower()

    def test_operational_error_returns_500(self, test_app):
        """OperationalError returns 500 DATABASE_ERROR."""
        response = test_app.get("/operational")
        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "DATABASE_ERROR"


# =============================================================================
# Feature Verification Tests
# =============================================================================


class TestFeature75Steps:
    """Verify all 8 feature steps are implemented correctly."""

    def test_step1_error_response_model_exists(self):
        """Step 1: Define ErrorResponse Pydantic model."""
        assert ErrorResponse is not None
        # Verify it's a Pydantic model
        from pydantic import BaseModel
        assert issubclass(ErrorResponse, BaseModel)

    def test_step2_error_response_fields(self):
        """Step 2: Fields: error_code (string), message (string), details (dict optional)."""
        response = ErrorResponse(
            error_code="TEST",
            message="Test",
            details={"key": "value"}
        )
        assert isinstance(response.error_code, str)
        assert isinstance(response.message, str)
        assert isinstance(response.details, dict)

        # Verify details is optional
        response2 = ErrorResponse(
            error_code="TEST",
            message="Test"
        )
        assert response2.details is None

    def test_step3_exception_handlers_exist(self):
        """Step 3: Create exception handlers for common errors."""
        # Verify handler functions exist
        assert callable(api_error_handler)
        assert callable(validation_error_handler)
        assert callable(http_exception_handler)
        assert callable(sqlalchemy_error_handler)
        assert callable(generic_exception_handler)

    def test_step4_validation_error_422(self):
        """Step 4: ValidationError -> 422 with field details."""
        error = ValidationError("Required", field="name")
        assert error.status_code == 422
        assert error.details["field"] == "name"

    def test_step5_not_found_error_404(self):
        """Step 5: NotFoundError -> 404."""
        error = NotFoundError("resource", 1)
        assert error.status_code == 404
        assert error.error_code == ErrorCode.NOT_FOUND

    def test_step6_conflict_error_409(self):
        """Step 6: ConflictError -> 409."""
        error = ConflictError("name", "duplicate")
        assert error.status_code == 409
        assert error.error_code == ErrorCode.CONFLICT

    def test_step7_database_error_500(self):
        """Step 7: DatabaseError -> 500."""
        error = DatabaseError("Failed")
        assert error.status_code == 500
        assert error.error_code == ErrorCode.DATABASE_ERROR

    def test_step8_handlers_can_be_registered(self):
        """Step 8: Apply handlers globally via FastAPI exception_handler."""
        app = FastAPI()
        # Should not raise any errors
        register_exception_handlers(app)
        # Verify handlers were registered
        assert APIError in app.exception_handlers
        assert HTTPException in app.exception_handlers


# =============================================================================
# Edge Cases and Security Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and security considerations."""

    def test_long_message_handling(self):
        """Long messages should be handled correctly."""
        long_message = "Error: " + "x" * 10000
        response = ErrorResponse(
            error_code="ERROR",
            message=long_message
        )
        assert response.message == long_message

    def test_special_characters_in_message(self):
        """Special characters in message should be preserved."""
        message = "Error: <script>alert('xss')</script>"
        response = ErrorResponse(
            error_code="ERROR",
            message=message
        )
        assert response.message == message

    def test_unicode_in_message(self):
        """Unicode characters should be supported."""
        message = "Error: 日本語 emoji 🔥"
        response = ErrorResponse(
            error_code="ERROR",
            message=message
        )
        assert response.message == message

    def test_nested_details(self):
        """Deeply nested details should work."""
        details = {
            "level1": {
                "level2": {
                    "level3": ["a", "b", "c"]
                }
            }
        }
        response = ErrorResponse(
            error_code="ERROR",
            message="Nested error",
            details=details
        )
        assert response.details == details


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
