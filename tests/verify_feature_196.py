#!/usr/bin/env python3
"""
Verification script for Feature #196: Agent Materializer validates template output

This script verifies all 4 feature steps:
1. Rendered markdown checked for required sections
2. Tool declarations validated against known tools
3. Model specification validated
4. Invalid output raises error before file write
"""
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.agent_materializer import (
    AgentMaterializer,
    TemplateValidationError,
    ValidationError,
    TemplateValidationResult,
    REQUIRED_MARKDOWN_SECTIONS,
    REQUIRED_FRONTMATTER_FIELDS,
    VALID_MODELS,
)
from api.agentspec_models import AgentSpec, generate_uuid


def print_header(msg: str):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(msg)
    print("=" * 60)


def print_step(step_num: int, description: str, passed: bool):
    """Print step result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\nStep {step_num}: {description}")
    print(f"  Status: {status}")


def verify_step1():
    """Step 1: Rendered markdown checked for required sections."""
    print_header("Step 1: Rendered markdown checked for required sections")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        # Test with valid spec
        valid_spec = AgentSpec(
            id=generate_uuid(),
            name="test-valid-spec",
            display_name="Test Valid Spec",
            task_type="coding",
            objective="Test objective",
            tool_policy={"allowed_tools": ["Read", "Write"]},
            max_turns=50,
            timeout_seconds=900,
        )

        content = materializer.render_claude_code_markdown(valid_spec)
        result = materializer.validate_template_output(content, valid_spec)

        # Check required sections are in content
        sections_present = all(section in content for section in REQUIRED_MARKDOWN_SECTIONS)
        frontmatter_present = all(f"{field}:" in content for field in REQUIRED_FRONTMATTER_FIELDS)

        print(f"  Required sections defined: {REQUIRED_MARKDOWN_SECTIONS}")
        print(f"  Required frontmatter fields: {REQUIRED_FRONTMATTER_FIELDS}")
        print(f"  All sections present in rendered content: {sections_present}")
        print(f"  All frontmatter fields present: {frontmatter_present}")
        print(f"  Validation result is_valid: {result.is_valid}")
        print(f"  Validation result has_required_sections: {result.has_required_sections}")
        print(f"  Validation result has_valid_frontmatter: {result.has_valid_frontmatter}")

        passed = (
            sections_present
            and frontmatter_present
            and result.is_valid
            and result.has_required_sections
            and result.has_valid_frontmatter
        )
        print_step(1, "Rendered markdown checked for required sections", passed)
        return passed


def verify_step2():
    """Step 2: Tool declarations validated against known tools."""
    print_header("Step 2: Tool declarations validated against known tools")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        # Test with invalid tools
        invalid_spec = AgentSpec(
            id=generate_uuid(),
            name="test-invalid-tools-spec",
            display_name="Test Invalid Tools",
            task_type="coding",
            objective="Test",
            tool_policy={"allowed_tools": ["Read", "FakeToolThatDoesNotExist", "AnotherFakeTool"]},
            max_turns=50,
            timeout_seconds=900,
        )

        content = materializer.render_claude_code_markdown(invalid_spec)
        result = materializer.validate_template_output(content, invalid_spec)

        tool_errors = [e for e in result.errors if e.category == "invalid_tool"]
        invalid_tool_names = [e.value for e in tool_errors]

        print(f"  Spec allowed_tools: {invalid_spec.tool_policy.get('allowed_tools', [])}")
        print(f"  Validation result tools_validated: {result.tools_validated}")
        print(f"  Number of invalid tool errors: {len(tool_errors)}")
        print(f"  Invalid tool names detected: {invalid_tool_names}")

        # FakeToolThatDoesNotExist and AnotherFakeTool should be detected
        passed = (
            not result.tools_validated
            and len(tool_errors) >= 2
            and "FakeToolThatDoesNotExist" in invalid_tool_names
            and "AnotherFakeTool" in invalid_tool_names
            and "Read" not in invalid_tool_names  # Read is valid
        )
        print_step(2, "Tool declarations validated against known tools", passed)
        return passed


def verify_step3():
    """Step 3: Model specification validated."""
    print_header("Step 3: Model specification validated")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        all_valid = True
        print(f"  Valid models: {VALID_MODELS}")

        # Test each valid model
        for model in VALID_MODELS:
            spec = AgentSpec(
                id=generate_uuid(),
                name=f"test-{model}-spec",
                display_name=f"Test {model}",
                task_type="coding",
                objective="Test",
                context={"model": model},
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=900,
            )

            content = materializer.render_claude_code_markdown(spec)
            result = materializer.validate_template_output(content, spec)

            print(f"  Model '{model}': model_validated={result.model_validated}, 'model: {model}' in content={f'model: {model}' in content}")

            if not result.model_validated:
                all_valid = False

        print_step(3, "Model specification validated", all_valid)
        return all_valid


def verify_step4():
    """Step 4: Invalid output raises error before file write."""
    print_header("Step 4: Invalid output raises error before file write")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(Path(tmpdir))

        # Create spec with invalid tools
        invalid_spec = AgentSpec(
            id=generate_uuid(),
            name="test-invalid-spec",
            display_name="Test Invalid",
            task_type="coding",
            objective="Test",
            tool_policy={"allowed_tools": ["InvalidToolXYZ"]},
            max_turns=50,
            timeout_seconds=900,
        )

        # Test 1: materialize() returns failure without writing file
        result = materializer.materialize(invalid_spec)
        expected_path = Path(tmpdir) / ".claude" / "agents" / "generated" / f"{invalid_spec.name}.md"
        file_exists = expected_path.exists()

        print(f"  Materialization result.success: {result.success}")
        print(f"  Materialization result.validation_result.is_valid: {result.validation_result.is_valid if result.validation_result else 'N/A'}")
        print(f"  File exists after failed validation: {file_exists}")

        # Test 2: raise_on_invalid=True raises exception
        exception_raised = False
        try:
            materializer.materialize(invalid_spec, raise_on_invalid=True)
        except TemplateValidationError as e:
            exception_raised = True
            print(f"  TemplateValidationError raised: True")
            print(f"  Exception message: {e.message[:50]}...")
            print(f"  Number of validation errors in exception: {len(e.validation_errors)}")

        passed = (
            not result.success
            and not file_exists
            and exception_raised
            and result.validation_result is not None
            and not result.validation_result.is_valid
        )
        print_step(4, "Invalid output raises error before file write", passed)
        return passed


def main():
    """Run all verification steps."""
    print("\n" + "=" * 60)
    print("Feature #196: Agent Materializer validates template output")
    print("Verification Script")
    print("=" * 60)

    results = [
        verify_step1(),
        verify_step2(),
        verify_step3(),
        verify_step4(),
    ]

    print_header("VERIFICATION SUMMARY")
    all_passed = all(results)

    for i, passed in enumerate(results, 1):
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  Step {i}: {status}")

    print("\n" + "-" * 60)
    if all_passed:
        print("🎉 ALL VERIFICATION STEPS PASSED!")
        print("Feature #196 is ready to be marked as passing.")
        return 0
    else:
        print("❌ Some verification steps failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
