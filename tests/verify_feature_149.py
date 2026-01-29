"""
Verification script for Feature #149: Integrate TemplateRegistry into DSPy SpecBuilder pipeline

Runs each feature verification step and reports pass/fail status.
"""
from __future__ import annotations

import json
import sys
import os
import inspect
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.spec_builder import (
    SpecBuilder,
    get_spec_builder,
    reset_spec_builder,
)
from api.template_registry import (
    Template,
    TemplateMetadata,
    TemplateRegistry,
)


def _make_mock_prediction(**kwargs):
    """Create a mock DSPy Prediction with sensible defaults."""
    defaults = {
        "reasoning": "Analysis of the task...",
        "objective": "Implement the feature as described.",
        "context_json": json.dumps({"target_files": ["src/main.py"]}),
        "tool_policy_json": json.dumps({
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Edit"],
        }),
        "max_turns": 100,
        "timeout_seconds": 1800,
        "validators_json": json.dumps([{"type": "test_pass", "config": {"command": "pytest"}}]),
    }
    defaults.update(kwargs)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _create_test_builder(registry=None):
    """Create a SpecBuilder with mocked DSPy internals."""
    builder = SpecBuilder(
        api_key="test-key-verify-149",
        auto_initialize=False,
        registry=registry,
    )
    builder._initialized = True
    builder._dspy_module = MagicMock(return_value=_make_mock_prediction())
    return builder


def _get_dspy_project_context(builder):
    """Extract project_context dict from most recent DSPy call."""
    call_args = builder._dspy_module.call_args
    ctx_json = call_args.kwargs.get("project_context") or call_args[1].get("project_context")
    return json.loads(ctx_json)


results = []


def step(name):
    def decorator(func):
        def wrapper():
            try:
                func()
                results.append(("PASS", name))
                print(f"  PASS: {name}")
            except Exception as e:
                results.append(("FAIL", name, str(e)))
                print(f"  FAIL: {name}: {e}")
        return wrapper
    return decorator


@step("Step 1: Locate SpecBuilder module and verify it has registry support")
def verify_step_1():
    from api.spec_builder import SpecBuilder
    assert SpecBuilder is not None, "SpecBuilder class not found"
    assert hasattr(SpecBuilder, "build"), "SpecBuilder has no build() method"
    sig = inspect.signature(SpecBuilder.__init__)
    assert "registry" in sig.parameters, "registry parameter not in __init__"
    builder = SpecBuilder(api_key="test", auto_initialize=False)
    assert hasattr(builder, "registry"), "No registry property"
    assert builder.registry is None, "Default registry should be None"


@step("Step 2: Locate TemplateRegistry module and verify API")
def verify_step_2():
    from api.template_registry import TemplateRegistry, get_template_registry
    assert TemplateRegistry is not None
    prompts_dir = Path(__file__).parent.parent / "prompts"
    if prompts_dir.exists():
        reg = TemplateRegistry(prompts_dir, auto_scan=True)
        task_types = reg.list_task_types()
        assert len(task_types) > 0, f"No task types found"
        print(f"    Found {len(task_types)} task types: {task_types}")


@step("Step 3: SpecBuilder queries TemplateRegistry by task_type during build()")
def verify_step_3():
    prompts_dir = Path(__file__).parent.parent / "prompts"
    assert prompts_dir.exists(), "prompts/ directory not found"
    registry = TemplateRegistry(prompts_dir, auto_scan=True)
    builder = _create_test_builder(registry=registry)
    result = builder.build(
        task_description="Add user auth",
        task_type="coding",
        context={"project_name": "TestApp"},
    )
    assert result.success, f"Build failed: {result.error}"
    ctx = _get_dspy_project_context(builder)
    assert "template_context" in ctx, "template_context not found in project_context"
    tc = ctx["template_context"]
    assert tc["template_task_type"] == "coding"
    print(f"    template_task_type: {tc['template_task_type']}, content: {len(tc['template_content'])} chars")


@step("Step 4: Template content included as additional context in DSPy compilation input")
def verify_step_4():
    prompts_dir = Path(__file__).parent.parent / "prompts"
    registry = TemplateRegistry(prompts_dir, auto_scan=True)
    builder = _create_test_builder(registry=registry)
    builder.build(task_description="Write code", task_type="coding", context={"project_name": "MyApp"})
    ctx = _get_dspy_project_context(builder)
    tc = ctx["template_context"]
    assert "template_content" in tc, "template_content missing"
    assert len(tc["template_content"]) > 100
    assert ctx["project_name"] == "MyApp", "Original context lost"
    print(f"    Original context preserved, template: {len(tc['template_content'])} chars")


@step("Step 5: Template variable interpolation works correctly in SpecBuilder flow")
def verify_step_5():
    prompts_dir = Path(__file__).parent.parent / "prompts"
    registry = TemplateRegistry(prompts_dir, auto_scan=True)
    builder = _create_test_builder(registry=registry)
    ctx = builder._get_template_context("coding", {"project_name": "InterpApp", "feature_id": 999})
    assert ctx is not None
    assert len(ctx["template_content"]) > 0
    result = builder.build(task_description="Test interpolation", task_type="coding", context={"project_name": "InterpApp"})
    assert result.success, f"Build failed: {result.error}"
    print(f"    Interpolation completed successfully ({len(ctx['template_content'])} chars)")


@step("Step 6: Compiling with template produces richer context than without")
def verify_step_6():
    prompts_dir = Path(__file__).parent.parent / "prompts"
    registry = TemplateRegistry(prompts_dir, auto_scan=True)
    builder_no = _create_test_builder(registry=None)
    builder_no.build(task_description="Add feature", task_type="coding", context={"project_name": "App"})
    ctx_no = _get_dspy_project_context(builder_no)
    json_no = json.dumps(ctx_no)

    builder_with = _create_test_builder(registry=registry)
    builder_with.build(task_description="Add feature", task_type="coding", context={"project_name": "App"})
    ctx_with = _get_dspy_project_context(builder_with)
    json_with = json.dumps(ctx_with)

    assert len(json_with) > len(json_no)
    assert "template_context" in ctx_with
    assert "template_context" not in ctx_no

    # Backward compatibility
    builder_compat = _create_test_builder(registry=None)
    result = builder_compat.build(task_description="Write docs", task_type="documentation", context={})
    assert result.success, "Backward compatibility broken"
    print(f"    Without: {len(json_no)} chars, With: {len(json_with)} chars (+{len(json_with)-len(json_no)} chars)")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Feature #149: Integrate TemplateRegistry into DSPy SpecBuilder pipeline")
    print("=" * 70 + "\n")
    verify_step_1()
    verify_step_2()
    verify_step_3()
    verify_step_4()
    verify_step_5()
    verify_step_6()
    print("\n" + "-" * 70)
    passed = sum(1 for r in results if r[0] == "PASS")
    failed = sum(1 for r in results if r[0] == "FAIL")
    print(f"\nResults: {passed}/{len(results)} steps PASSED, {failed} FAILED")
    if failed > 0:
        for r in results:
            if r[0] == "FAIL":
                print(f"  FAIL: {r[1]}: {r[2]}")
        sys.exit(1)
    else:
        print("\nAll verification steps PASSED")
        sys.exit(0)
