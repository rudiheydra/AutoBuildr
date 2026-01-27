"""
API Error Handling Module
=========================

Standardized error response format across all API endpoints.

Feature #75: Standardized API Error Responses

This module provides:
- ErrorResponse Pydantic model for consistent error responses
- Custom exception classes for different error types
- Exception handlers for FastAPI integration

Error Codes:
- VALIDATION_ERROR: Input validation failed (422)
- NOT_FOUND: Resource not found (404)
- CONFLICT: Resource conflict / duplicate (409)
- DATABASE_ERROR: Database operation failed (500)
- INTERNAL_ERROR: Unexpected server error (500)
- BAD_REQUEST: Invalid request (400)
- UNAUTHORIZED: Authentication required (401)
- FORBIDDEN: Permission denied (403)
"""

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError


# =============================================================================
# Error Response Schema
# =============================================================================


class ErrorResponse(BaseModel):
    """
    Standardized API error response format.

    Feature #75, Step 1: Define ErrorResponse Pydantic model
    Feature #75, Step 2: Fields: error_code (string), message (string), details (dict optional)

    All API error responses follow this format for consistency.

    Example:
        {
            "error_code": "NOT_FOUND",
            "message": "Feature 123 not found",
            "details": {"resource": "feature", "id": 123}
        }
    """

    error_code: str = Field(
        ...,
        description="Machine-readable error code for programmatic handling",
        examples=["NOT_FOUND", "VALIDATION_ERROR", "DATABASE_ERROR"]
    )

    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Resource not found", "Validation failed"]
    )

    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional error details (field errors, context, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error_code": "NOT_FOUND",
                "message": "Feature 123 not found",
                "details": {"resource": "feature", "id": 123}
            }
        }
    )


# =============================================================================
# Error Codes
# =============================================================================


class ErrorCode:
    """
    Standard error codes used across the API.

    These codes are machine-readable identifiers that clients can use
    for programmatic error handling.
    """
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"


# =============================================================================
# Custom Exception Classes
# =============================================================================


class APIError(Exception):
    """
    Base class for all API exceptions.

    All custom API exceptions should inherit from this class.
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        """Convert exception to ErrorResponse model."""
        return ErrorResponse(
            error_code=self.error_code,
            message=self.message,
            details=self.details
        )


class NotFoundError(APIError):
    """
    Resource not found error.

    Feature #75, Step 5: NotFoundError -> 404

    Use when a requested resource (feature, project, agent spec, etc.)
    does not exist.

    Example:
        raise NotFoundError("feature", 123)
        # Response: {"error_code": "NOT_FOUND", "message": "Feature 123 not found"}
    """

    def __init__(
        self,
        resource: str,
        identifier: Any = None,
        message: str | None = None
    ):
        if message is None:
            if identifier is not None:
                message = f"{resource.title()} '{identifier}' not found"
            else:
                message = f"{resource.title()} not found"

        details = {"resource": resource}
        if identifier is not None:
            details["id"] = identifier

        super().__init__(
            error_code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class ConflictError(APIError):
    """
    Resource conflict error.

    Feature #75, Step 6: ConflictError -> 409

    Use when a resource already exists or there's a conflict
    (e.g., duplicate name, unique constraint violation).

    Example:
        raise ConflictError("name", "my-spec", "AgentSpec with this name already exists")
    """

    def __init__(
        self,
        field: str | None = None,
        value: Any = None,
        message: str | None = None
    ):
        if message is None:
            if field and value:
                message = f"Conflict: {field} '{value}' already exists"
            elif field:
                message = f"Conflict on field: {field}"
            else:
                message = "Resource conflict occurred"

        details: dict[str, Any] = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate long values

        super().__init__(
            error_code=ErrorCode.CONFLICT,
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details if details else None
        )


class ValidationError(APIError):
    """
    Input validation error.

    Feature #75, Step 4: ValidationError -> 422 with field details

    Use when request data fails validation beyond Pydantic's automatic
    validation (e.g., business logic validation).

    Example:
        raise ValidationError(
            "max_turns must be at least 1",
            field="max_turns",
            value=0
        )
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        errors: list[dict[str, Any]] | None = None
    ):
        details: dict[str, Any] = {}

        if errors:
            # Multiple validation errors
            details["errors"] = errors
        else:
            # Single validation error
            if field:
                details["field"] = field
            if value is not None:
                details["value"] = str(value)[:100]

        super().__init__(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details if details else None
        )


class DatabaseError(APIError):
    """
    Database operation error.

    Feature #75, Step 7: DatabaseError -> 500

    Use when a database operation fails unexpectedly.

    Note: Sensitive details should not be exposed to clients.
    The original error is logged server-side for debugging.

    Example:
        raise DatabaseError("Failed to save feature")
    """

    def __init__(
        self,
        message: str = "A database error occurred",
        operation: str | None = None
    ):
        details = {"operation": operation} if operation else None

        super().__init__(
            error_code=ErrorCode.DATABASE_ERROR,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class BadRequestError(APIError):
    """
    Generic bad request error.

    Use for request errors that don't fit other categories.

    Example:
        raise BadRequestError("Invalid UUID format")
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None
    ):
        super().__init__(
            error_code=ErrorCode.BAD_REQUEST,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class UnauthorizedError(APIError):
    """
    Authentication required error.

    Use when authentication is required but not provided.

    Example:
        raise UnauthorizedError("API key required")
    """

    def __init__(
        self,
        message: str = "Authentication required"
    ):
        super().__init__(
            error_code=ErrorCode.UNAUTHORIZED,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=None
        )


class ForbiddenError(APIError):
    """
    Permission denied error.

    Use when the user is authenticated but lacks permission.

    Example:
        raise ForbiddenError("You do not have permission to delete this project")
    """

    def __init__(
        self,
        message: str = "Permission denied"
    ):
        super().__init__(
            error_code=ErrorCode.FORBIDDEN,
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=None
        )


# =============================================================================
# Exception Handlers
# =============================================================================


def create_error_response(
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Create a standardized error response dictionary.

    This helper function ensures all error responses follow the same format.
    """
    response = {
        "error_code": error_code,
        "message": message
    }
    if details is not None:
        response["details"] = details
    return response


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """
    Handler for custom API errors.

    Feature #75, Step 8: Apply handlers globally via FastAPI exception_handler

    Converts APIError exceptions to standardized JSON responses.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details
        )
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """
    Handler for Pydantic validation errors.

    Feature #75, Step 4: ValidationError -> 422 with field details

    Converts FastAPI/Pydantic validation errors to standardized format.
    Extracts field information from validation error locations.
    """
    errors = []
    for error in exc.errors():
        # Build field path from location
        loc = error.get("loc", [])
        # Skip 'body' prefix if present
        field_parts = [str(p) for p in loc if p != "body"]
        field = ".".join(field_parts) if field_parts else "unknown"

        errors.append({
            "field": field,
            "message": error.get("msg", "Validation error"),
            "type": error.get("type", "value_error")
        })

    # Create human-readable message
    if len(errors) == 1:
        message = f"Validation error on field '{errors[0]['field']}': {errors[0]['message']}"
    else:
        message = f"Validation failed with {len(errors)} errors"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=message,
            details={"errors": errors}
        )
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException
) -> JSONResponse:
    """
    Handler for standard HTTPException.

    Converts FastAPI HTTPException to standardized format while
    preserving the original status code.
    """
    # Map status codes to error codes
    status_to_code = {
        400: ErrorCode.BAD_REQUEST,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        422: ErrorCode.VALIDATION_ERROR,
        500: ErrorCode.INTERNAL_ERROR,
    }

    error_code = status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    # Handle detail that might be a dict (from custom exceptions)
    if isinstance(exc.detail, dict):
        # If it's already in our format, use it directly
        if "error_code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )
        # Otherwise wrap it
        message = exc.detail.get("message", str(exc.detail))
        details = {k: v for k, v in exc.detail.items() if k != "message"}
    else:
        message = str(exc.detail) if exc.detail else "An error occurred"
        details = None

    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            error_code=error_code,
            message=message,
            details=details if details else None
        )
    )


async def sqlalchemy_error_handler(
    request: Request,
    exc: SQLAlchemyError
) -> JSONResponse:
    """
    Handler for SQLAlchemy database errors.

    Feature #75, Step 7: DatabaseError -> 500

    Catches SQLAlchemy errors and returns a generic database error.
    The actual error is logged but not exposed to clients for security.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Log the actual error for debugging
    logger.exception(f"Database error: {exc}")

    # Handle specific SQLAlchemy error types
    if isinstance(exc, IntegrityError):
        # Check for common constraint violations
        error_str = str(exc.orig) if hasattr(exc, 'orig') else str(exc)

        if "UNIQUE constraint failed" in error_str:
            # Extract field name if possible
            field = None
            if "." in error_str:
                parts = error_str.split(".")
                if len(parts) >= 2:
                    field = parts[-1].strip()

            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=create_error_response(
                    error_code=ErrorCode.CONFLICT,
                    message="Duplicate value: resource already exists",
                    details={"field": field} if field else None
                )
            )

        if "FOREIGN KEY constraint failed" in error_str:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=create_error_response(
                    error_code=ErrorCode.BAD_REQUEST,
                    message="Invalid reference: referenced resource does not exist"
                )
            )

    if isinstance(exc, OperationalError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=create_error_response(
                error_code=ErrorCode.DATABASE_ERROR,
                message="Database operation failed"
            )
        )

    # Generic database error
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            error_code=ErrorCode.DATABASE_ERROR,
            message="A database error occurred"
        )
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Handler for unhandled exceptions.

    Catches any unhandled exception and returns a generic internal error.
    The actual error is logged but not exposed to clients for security.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Log the actual error for debugging
    logger.exception(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred"
        )
    )


def register_exception_handlers(app) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Feature #75, Step 8: Apply handlers globally via FastAPI exception_handler

    Call this function during app initialization to set up
    standardized error handling across all endpoints.

    Example:
        from server.exceptions import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
    """
    # Custom API errors (highest priority)
    app.add_exception_handler(APIError, api_error_handler)

    # Pydantic validation errors
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Standard HTTP exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)

    # SQLAlchemy database errors
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)

    # Catch-all for unhandled exceptions
    # Note: Commented out to allow better debugging during development
    # Uncomment for production to hide internal errors from clients
    # app.add_exception_handler(Exception, generic_exception_handler)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Response model
    "ErrorResponse",
    # Error codes
    "ErrorCode",
    # Exception classes
    "APIError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "DatabaseError",
    "BadRequestError",
    "UnauthorizedError",
    "ForbiddenError",
    # Handlers
    "api_error_handler",
    "validation_error_handler",
    "http_exception_handler",
    "sqlalchemy_error_handler",
    "generic_exception_handler",
    # Helper
    "create_error_response",
    "register_exception_handlers",
]
