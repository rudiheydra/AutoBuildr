#!/usr/bin/env python3
"""
Feature #75 Verification Script
===============================

Verifies all 8 feature steps for Standardized API Error Responses.

Run with:
    python tests/verify_feature_75.py
"""

import sys
from pathlib import Path

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

def verify_step_1():
    """Step 1: Define ErrorResponse Pydantic model."""
    print("Step 1: Define ErrorResponse Pydantic model...", end=" ")
    from server.exceptions import ErrorResponse
    from pydantic import BaseModel

    assert issubclass(ErrorResponse, BaseModel), "ErrorResponse must be a Pydantic model"
    print("PASS")
    return True

def verify_step_2():
    """Step 2: Fields: error_code (string), message (string), details (dict optional)."""
    print("Step 2: Fields: error_code, message, details...", end=" ")
    from server.exceptions import ErrorResponse

    # Test with all fields
    response = ErrorResponse(
        error_code="TEST",
        message="Test message",
        details={"key": "value"}
    )
    assert response.error_code == "TEST"
    assert response.message == "Test message"
    assert response.details == {"key": "value"}

    # Test without optional details
    response2 = ErrorResponse(error_code="TEST", message="Test")
    assert response2.details is None

    print("PASS")
    return True

def verify_step_3():
    """Step 3: Create exception handlers for common errors."""
    print("Step 3: Create exception handlers for common errors...", end=" ")
    from server.exceptions import (
        api_error_handler,
        validation_error_handler,
        http_exception_handler,
        sqlalchemy_error_handler,
    )

    assert callable(api_error_handler)
    assert callable(validation_error_handler)
    assert callable(http_exception_handler)
    assert callable(sqlalchemy_error_handler)

    print("PASS")
    return True

def verify_step_4():
    """Step 4: ValidationError -> 422 with field details."""
    print("Step 4: ValidationError -> 422 with field details...", end=" ")
    from server.exceptions import ValidationError, ErrorCode

    error = ValidationError("Field required", field="name", value="")
    assert error.status_code == 422
    assert error.error_code == ErrorCode.VALIDATION_ERROR
    assert error.details["field"] == "name"

    print("PASS")
    return True

def verify_step_5():
    """Step 5: NotFoundError -> 404."""
    print("Step 5: NotFoundError -> 404...", end=" ")
    from server.exceptions import NotFoundError, ErrorCode

    error = NotFoundError("feature", 123)
    assert error.status_code == 404
    assert error.error_code == ErrorCode.NOT_FOUND
    assert error.details["resource"] == "feature"
    assert error.details["id"] == 123

    print("PASS")
    return True

def verify_step_6():
    """Step 6: ConflictError -> 409."""
    print("Step 6: ConflictError -> 409...", end=" ")
    from server.exceptions import ConflictError, ErrorCode

    error = ConflictError("name", "duplicate")
    assert error.status_code == 409
    assert error.error_code == ErrorCode.CONFLICT
    assert error.details["field"] == "name"

    print("PASS")
    return True

def verify_step_7():
    """Step 7: DatabaseError -> 500."""
    print("Step 7: DatabaseError -> 500...", end=" ")
    from server.exceptions import DatabaseError, ErrorCode

    error = DatabaseError("Query failed")
    assert error.status_code == 500
    assert error.error_code == ErrorCode.DATABASE_ERROR

    print("PASS")
    return True

def verify_step_8():
    """Step 8: Apply handlers globally via FastAPI exception_handler."""
    print("Step 8: Apply handlers globally via FastAPI exception_handler...", end=" ")
    from fastapi import FastAPI, HTTPException
    from server.exceptions import register_exception_handlers, APIError

    app = FastAPI()
    register_exception_handlers(app)

    # Verify handlers were registered
    assert APIError in app.exception_handlers
    assert HTTPException in app.exception_handlers

    print("PASS")
    return True

def verify_main_py_integration():
    """Verify exception handlers are registered in main.py."""
    print("Verify main.py integration...", end=" ")

    # Import main app to ensure it loads without errors
    from server.main import app
    from server.exceptions import APIError

    # Check handlers are registered
    assert APIError in app.exception_handlers

    print("PASS")
    return True

def main():
    print("=" * 60)
    print("Feature #75: Standardized API Error Responses")
    print("=" * 60)
    print()

    steps = [
        verify_step_1,
        verify_step_2,
        verify_step_3,
        verify_step_4,
        verify_step_5,
        verify_step_6,
        verify_step_7,
        verify_step_8,
        verify_main_py_integration,
    ]

    passed = 0
    failed = 0

    for step in steps:
        try:
            if step():
                passed += 1
        except AssertionError as e:
            print(f"FAIL - {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR - {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed}/{len(steps)} steps passed")
    print("=" * 60)

    if failed == 0:
        print("\n[SUCCESS] All feature steps verified!")
        return 0
    else:
        print(f"\n[FAILED] {failed} step(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
