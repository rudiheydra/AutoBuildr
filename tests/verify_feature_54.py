#!/usr/bin/env python
"""
Verification script for Feature #54: DSPy Module Execution for Spec Generation

This script verifies all 9 feature steps:
1. Create SpecBuilder class wrapping DSPy module
2. Initialize DSPy with Claude backend
3. Implement build(task_desc, task_type, context) method
4. Execute DSPy signature with inputs
5. Parse JSON output fields
6. Validate tool_policy structure
7. Validate validators structure
8. Create AgentSpec and AcceptanceSpec from output
9. Handle DSPy execution errors gracefully
"""
from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, "/home/rudih/workspace/AutoBuildr")


def verify_step_1_specbuilder_class():
    """Step 1: Create SpecBuilder class wrapping DSPy module."""
    print("Step 1: Create SpecBuilder class wrapping DSPy module")

    from api.spec_builder import SpecBuilder
    import inspect

    # Verify class exists
    assert SpecBuilder is not None, "SpecBuilder class not found"

    # Verify it has the expected methods
    methods = dir(SpecBuilder)
    assert "build" in methods, "SpecBuilder.build method not found"
    assert "_initialize_dspy" in methods, "SpecBuilder._initialize_dspy method not found"
    assert "_execute_dspy" in methods, "SpecBuilder._execute_dspy method not found"

    # Verify it has DSPy-related attributes
    builder = SpecBuilder(api_key="test", auto_initialize=False)
    assert hasattr(builder, "_dspy_module"), "SpecBuilder._dspy_module attribute not found"
    assert hasattr(builder, "_lm"), "SpecBuilder._lm attribute not found"

    print("  PASS: SpecBuilder class exists with DSPy module wrapping")
    return True


def verify_step_2_claude_backend_initialization():
    """Step 2: Initialize DSPy with Claude backend."""
    print("Step 2: Initialize DSPy with Claude backend")

    from api.spec_builder import (
        SpecBuilder,
        DEFAULT_MODEL,
        AVAILABLE_MODELS,
        DSPyInitializationError,
    )

    # Verify default model is Anthropic
    assert "anthropic" in DEFAULT_MODEL.lower(), f"Default model should be Anthropic, got: {DEFAULT_MODEL}"

    # Verify available models include Anthropic options
    assert any("anthropic" in m for m in AVAILABLE_MODELS), "No Anthropic models in AVAILABLE_MODELS"

    # Verify initialization fails without API key
    try:
        builder = SpecBuilder(api_key=None, auto_initialize=True)
        assert False, "Should raise DSPyInitializationError without API key"
    except DSPyInitializationError as e:
        assert "API key" in str(e), "Error should mention API key"

    # Verify builder stores model
    builder = SpecBuilder(api_key="test", model="anthropic/claude-3-haiku-20240307", auto_initialize=False)
    assert builder.model == "anthropic/claude-3-haiku-20240307", "Model not stored correctly"

    print("  PASS: DSPy initializes with Claude backend configuration")
    return True


def verify_step_3_build_method():
    """Step 3: Implement build(task_desc, task_type, context) method."""
    print("Step 3: Implement build(task_desc, task_type, context) method")

    from api.spec_builder import SpecBuilder, BuildResult
    import inspect

    # Check build method signature
    sig = inspect.signature(SpecBuilder.build)
    params = list(sig.parameters.keys())

    assert "task_description" in params, "build() missing task_description parameter"
    assert "task_type" in params, "build() missing task_type parameter"
    assert "context" in params, "build() missing context parameter"

    # Verify return type is BuildResult
    builder = SpecBuilder(api_key="test", auto_initialize=False)
    result = builder.build(task_description="", task_type="coding")
    assert isinstance(result, BuildResult), "build() should return BuildResult"

    # Verify BuildResult has expected fields
    assert hasattr(result, "success"), "BuildResult missing 'success' field"
    assert hasattr(result, "agent_spec"), "BuildResult missing 'agent_spec' field"
    assert hasattr(result, "acceptance_spec"), "BuildResult missing 'acceptance_spec' field"
    assert hasattr(result, "error"), "BuildResult missing 'error' field"
    assert hasattr(result, "validation_errors"), "BuildResult missing 'validation_errors' field"

    print("  PASS: build(task_desc, task_type, context) method implemented correctly")
    return True


def verify_step_4_dspy_signature_execution():
    """Step 4: Execute DSPy signature with inputs."""
    print("Step 4: Execute DSPy signature with inputs")

    from api.spec_builder import SpecBuilder
    from api.dspy_signatures import SpecGenerationSignature
    import dspy

    # Verify SpecGenerationSignature exists and has required fields
    assert hasattr(SpecGenerationSignature, "__fields__") or hasattr(SpecGenerationSignature, "_fields"), \
        "SpecGenerationSignature should be a DSPy signature"

    # Verify builder uses the signature
    builder = SpecBuilder(api_key="test", auto_initialize=False)
    builder._initialized = True

    # Mock the DSPy module
    mock_result = MagicMock()
    mock_result.reasoning = "Test reasoning"
    mock_result.objective = "Test objective"
    mock_result.context_json = '{"test": true}'
    mock_result.tool_policy_json = '{"allowed_tools": ["Read"]}'
    mock_result.max_turns = 100
    mock_result.timeout_seconds = 1800
    mock_result.validators_json = '[]'

    builder._dspy_module = MagicMock(return_value=mock_result)

    # Execute build and verify module was called
    result = builder.build(
        task_description="Test task",
        task_type="coding",
        context={"project": "test"}
    )

    # Verify the DSPy module was called with correct inputs
    builder._dspy_module.assert_called_once()
    call_kwargs = builder._dspy_module.call_args
    assert "task_description" in str(call_kwargs) or call_kwargs[1].get("task_description") or call_kwargs[0][0] == "Test task"

    print("  PASS: DSPy signature executed with inputs")
    return True


def verify_step_5_json_parsing():
    """Step 5: Parse JSON output fields."""
    print("Step 5: Parse JSON output fields")

    from api.spec_builder import parse_json_field

    # Test valid JSON
    value, error = parse_json_field("test", '{"key": "value"}')
    assert error is None, f"Expected no error for valid JSON, got: {error}"
    assert value == {"key": "value"}, "Parsed value incorrect"

    # Test JSON in code block
    value, error = parse_json_field("test", '```json\n{"key": "value"}\n```')
    assert error is None, f"Expected no error for JSON in code block, got: {error}"
    assert value == {"key": "value"}, "Parsed value from code block incorrect"

    # Test JSON array
    value, error = parse_json_field("test", '[1, 2, 3]')
    assert error is None, f"Expected no error for array, got: {error}"
    assert value == [1, 2, 3], "Parsed array incorrect"

    # Test empty string
    value, error = parse_json_field("test", "")
    assert error is not None, "Expected error for empty string"
    assert "empty" in error.lower(), "Error should mention empty"

    # Test invalid JSON
    value, error = parse_json_field("test", "not json {{{{")
    assert error is not None, "Expected error for invalid JSON"

    print("  PASS: JSON output fields parsed correctly")
    return True


def verify_step_6_tool_policy_validation():
    """Step 6: Validate tool_policy structure."""
    print("Step 6: Validate tool_policy structure")

    from api.spec_builder import validate_tool_policy

    # Valid policy
    policy = {
        "policy_version": "v1",
        "allowed_tools": ["Read", "Write"],
        "forbidden_patterns": ["rm -rf"],
        "tool_hints": {"Read": "Use for reading files"}
    }
    errors = validate_tool_policy(policy)
    assert errors == [], f"Expected no errors for valid policy, got: {errors}"

    # Missing allowed_tools
    errors = validate_tool_policy({"forbidden_patterns": []})
    assert any("allowed_tools" in e for e in errors), "Should error on missing allowed_tools"

    # Non-array allowed_tools
    errors = validate_tool_policy({"allowed_tools": "Read"})
    assert any("array" in e for e in errors), "Should error on non-array allowed_tools"

    # Invalid regex in forbidden_patterns
    errors = validate_tool_policy({
        "allowed_tools": ["Read"],
        "forbidden_patterns": ["[invalid"]
    })
    assert any("regex" in e.lower() for e in errors), "Should error on invalid regex"

    # Invalid policy version
    errors = validate_tool_policy({
        "allowed_tools": ["Read"],
        "policy_version": "v2"
    })
    assert any("v1" in e for e in errors), "Should error on invalid policy version"

    print("  PASS: tool_policy structure validated correctly")
    return True


def verify_step_7_validators_validation():
    """Step 7: Validate validators structure."""
    print("Step 7: Validate validators structure")

    from api.spec_builder import validate_validators

    # Valid validators
    validators = [
        {"type": "test_pass", "config": {"command": "pytest"}, "weight": 0.5, "required": True},
        {"type": "file_exists", "config": {"path": "src/main.py"}, "weight": 0.5, "required": False}
    ]
    errors = validate_validators(validators)
    assert errors == [], f"Expected no errors for valid validators, got: {errors}"

    # Empty array is valid
    errors = validate_validators([])
    assert errors == [], "Empty validators array should be valid"

    # Not an array
    errors = validate_validators({"type": "test_pass"})
    assert any("array" in e for e in errors), "Should error when validators is not array"

    # Missing type
    errors = validate_validators([{"config": {}}])
    assert any("type" in e for e in errors), "Should error on missing type"

    # Invalid type
    errors = validate_validators([{"type": "invalid_type"}])
    assert any("must be one of" in e for e in errors), "Should error on invalid type"

    # Weight out of range
    errors = validate_validators([{"type": "test_pass", "weight": 2.0}])
    assert any("weight" in e and "0 and 1" in e for e in errors), "Should error on weight > 1"

    print("  PASS: validators structure validated correctly")
    return True


def verify_step_8_spec_creation():
    """Step 8: Create AgentSpec and AcceptanceSpec from output."""
    print("Step 8: Create AgentSpec and AcceptanceSpec from output")

    from api.spec_builder import SpecBuilder
    from api.agentspec_models import AgentSpec, AcceptanceSpec

    # Create builder with mocked DSPy
    builder = SpecBuilder(api_key="test", auto_initialize=False)
    builder._initialized = True

    mock_result = MagicMock()
    mock_result.reasoning = "Test reasoning"
    mock_result.objective = "Implement user authentication with OAuth2."
    mock_result.context_json = '{"feature_id": 42}'
    mock_result.tool_policy_json = json.dumps({
        "allowed_tools": ["Read", "Write", "Edit"],
        "forbidden_patterns": ["rm -rf"],
    })
    mock_result.max_turns = 100
    mock_result.timeout_seconds = 1800
    mock_result.validators_json = json.dumps([
        {"type": "test_pass", "config": {"command": "pytest"}, "weight": 1.0, "required": False}
    ])

    builder._dspy_module = MagicMock(return_value=mock_result)

    result = builder.build(
        task_description="Add authentication",
        task_type="coding",
        source_feature_id=42,
    )

    assert result.success, f"Build should succeed, error: {result.error}"

    # Verify AgentSpec
    assert result.agent_spec is not None, "AgentSpec should be created"
    assert isinstance(result.agent_spec, AgentSpec), "Should be AgentSpec instance"
    assert result.agent_spec.task_type == "coding", "task_type should match"
    assert result.agent_spec.source_feature_id == 42, "source_feature_id should be linked"
    assert result.agent_spec.max_turns == 100, "max_turns should match"
    assert result.agent_spec.timeout_seconds == 1800, "timeout_seconds should match"

    # Verify AcceptanceSpec
    assert result.acceptance_spec is not None, "AcceptanceSpec should be created"
    assert isinstance(result.acceptance_spec, AcceptanceSpec), "Should be AcceptanceSpec instance"
    assert len(result.acceptance_spec.validators) == 1, "Should have 1 validator"

    print("  PASS: AgentSpec and AcceptanceSpec created from output")
    return True


def verify_step_9_error_handling():
    """Step 9: Handle DSPy execution errors gracefully."""
    print("Step 9: Handle DSPy execution errors gracefully")

    from api.spec_builder import (
        SpecBuilder,
        DSPyExecutionError,
        DSPyInitializationError,
        OutputValidationError,
    )

    # Test input validation error (empty task description)
    builder = SpecBuilder(api_key="test", auto_initialize=False)
    result = builder.build(task_description="", task_type="coding")
    assert result.success is False, "Should fail on empty task description"
    assert result.error_type == "input_validation", "Should be input_validation error"
    assert "empty" in result.error.lower(), "Error should mention empty"

    # Test invalid task type
    result = builder.build(task_description="Test", task_type="invalid")
    assert result.success is False, "Should fail on invalid task type"
    assert result.error_type == "input_validation", "Should be input_validation error"

    # Test DSPy execution error
    builder._initialized = True
    builder._dspy_module = MagicMock(side_effect=RuntimeError("DSPy crashed"))

    result = builder.build(task_description="Test", task_type="coding")
    assert result.success is False, "Should fail on DSPy error"
    assert result.error_type == "execution", "Should be execution error"
    assert "DSPy" in result.error, "Error should mention DSPy"

    # Test initialization error
    builder2 = SpecBuilder(api_key=None, auto_initialize=False)
    try:
        builder2._initialize_dspy()
        assert False, "Should raise DSPyInitializationError"
    except DSPyInitializationError:
        pass  # Expected

    # Verify BuildResult always has error info
    assert hasattr(result, "error"), "BuildResult should have error field"
    assert hasattr(result, "error_type"), "BuildResult should have error_type field"
    assert hasattr(result, "validation_errors"), "BuildResult should have validation_errors field"
    assert hasattr(result, "raw_output"), "BuildResult should have raw_output field"

    print("  PASS: DSPy execution errors handled gracefully")
    return True


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #54: DSPy Module Execution for Spec Generation")
    print("=" * 70)
    print()

    steps = [
        ("Step 1", verify_step_1_specbuilder_class),
        ("Step 2", verify_step_2_claude_backend_initialization),
        ("Step 3", verify_step_3_build_method),
        ("Step 4", verify_step_4_dspy_signature_execution),
        ("Step 5", verify_step_5_json_parsing),
        ("Step 6", verify_step_6_tool_policy_validation),
        ("Step 7", verify_step_7_validators_validation),
        ("Step 8", verify_step_8_spec_creation),
        ("Step 9", verify_step_9_error_handling),
    ]

    passed = 0
    failed = 0

    for name, func in steps:
        try:
            func()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1
        print()

    print("=" * 70)
    print(f"Results: {passed}/{len(steps)} steps passed")
    print("=" * 70)

    if failed == 0:
        print("\nAll verification steps PASSED!")
        return 0
    else:
        print(f"\n{failed} verification steps FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
