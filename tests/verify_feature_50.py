#!/usr/bin/env python3
"""
Verification Script for Feature #50: DSPy SpecGenerationSignature Definition
=============================================================================

This script verifies all requirements for Feature #50 according to the
feature's verification steps.

Feature #50 Steps:
1. Import dspy library
2. Define SpecGenerationSignature(dspy.Signature)
3. Define input fields: task_description, task_type, project_context
4. Define output fields: objective, context_json, tool_policy_json, max_turns, timeout_seconds, validators_json
5. Add docstring with field descriptions
6. Add chain-of-thought reasoning field
"""

import sys


def verify_step_1():
    """Step 1: Import dspy library"""
    print("\n=== Step 1: Import dspy library ===")

    try:
        import dspy
        print(f"  [PASS] DSPy imported successfully (version {dspy.__version__})")

        # Verify DSPy has required components
        required = ["Signature", "InputField", "OutputField", "Predict", "ChainOfThought"]
        for component in required:
            if hasattr(dspy, component):
                print(f"  [PASS] dspy.{component} exists")
            else:
                print(f"  [FAIL] dspy.{component} missing")
                return False

        return True

    except ImportError as e:
        print(f"  [FAIL] Could not import dspy: {e}")
        return False


def verify_step_2():
    """Step 2: Define SpecGenerationSignature(dspy.Signature)"""
    print("\n=== Step 2: Define SpecGenerationSignature(dspy.Signature) ===")

    try:
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Check class exists
        if SpecGenerationSignature is None:
            print("  [FAIL] SpecGenerationSignature is None")
            return False
        print("  [PASS] SpecGenerationSignature class exists")

        # Check inheritance
        if not issubclass(SpecGenerationSignature, dspy.Signature):
            print("  [FAIL] SpecGenerationSignature does not inherit from dspy.Signature")
            return False
        print("  [PASS] SpecGenerationSignature inherits from dspy.Signature")

        # Check usability with DSPy modules
        try:
            predictor = dspy.Predict(SpecGenerationSignature)
            print("  [PASS] Can be used with dspy.Predict")
        except Exception as e:
            print(f"  [FAIL] Cannot use with dspy.Predict: {e}")
            return False

        try:
            cot = dspy.ChainOfThought(SpecGenerationSignature)
            print("  [PASS] Can be used with dspy.ChainOfThought")
        except Exception as e:
            print(f"  [FAIL] Cannot use with dspy.ChainOfThought: {e}")
            return False

        return True

    except ImportError as e:
        print(f"  [FAIL] Import error: {e}")
        return False


def verify_step_3():
    """Step 3: Define input fields: task_description, task_type, project_context"""
    print("\n=== Step 3: Define input fields ===")

    try:
        from api.dspy_signatures import SpecGenerationSignature

        # input_fields is a dict property in DSPy 3.x
        input_fields = SpecGenerationSignature.input_fields

        expected_inputs = ["task_description", "task_type", "project_context"]

        for field_name in expected_inputs:
            if field_name in input_fields:
                print(f"  [PASS] Input field '{field_name}' exists")
            else:
                print(f"  [FAIL] Input field '{field_name}' missing")
                return False

        # Check no extra unexpected input fields
        if len(input_fields) == len(expected_inputs):
            print(f"  [PASS] Exactly {len(expected_inputs)} input fields defined")
        else:
            print(f"  [WARN] {len(input_fields)} input fields (expected {len(expected_inputs)})")

        return True

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def verify_step_4():
    """Step 4: Define output fields"""
    print("\n=== Step 4: Define output fields ===")

    try:
        from api.dspy_signatures import SpecGenerationSignature

        # output_fields is a dict property in DSPy 3.x
        output_fields = SpecGenerationSignature.output_fields

        required_outputs = [
            "objective",
            "context_json",
            "tool_policy_json",
            "max_turns",
            "timeout_seconds",
            "validators_json",
        ]

        for field_name in required_outputs:
            if field_name in output_fields:
                print(f"  [PASS] Output field '{field_name}' exists")
            else:
                print(f"  [FAIL] Output field '{field_name}' missing")
                return False

        # Check reasoning field (from step 6, but also an output)
        if "reasoning" in output_fields:
            print("  [PASS] Output field 'reasoning' exists (chain-of-thought)")
        else:
            print("  [WARN] Output field 'reasoning' missing (checked in step 6)")

        # Check types
        fields = SpecGenerationSignature.model_fields

        if fields["max_turns"].annotation == int:
            print("  [PASS] max_turns has int type")
        else:
            print(f"  [WARN] max_turns type is {fields['max_turns'].annotation}")

        if fields["timeout_seconds"].annotation == int:
            print("  [PASS] timeout_seconds has int type")
        else:
            print(f"  [WARN] timeout_seconds type is {fields['timeout_seconds'].annotation}")

        return True

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def verify_step_5():
    """Step 5: Add docstring with field descriptions"""
    print("\n=== Step 5: Add docstring with field descriptions ===")

    try:
        from api.dspy_signatures import SpecGenerationSignature

        # Check class docstring
        docstring = SpecGenerationSignature.__doc__
        if docstring is None or len(docstring) < 100:
            print("  [FAIL] Class docstring is missing or too short")
            return False
        print(f"  [PASS] Class docstring exists ({len(docstring)} chars)")

        # Check for key content in docstring
        required_content = ["AgentSpec", "task_description", "objective"]
        for content in required_content:
            if content in docstring:
                print(f"  [PASS] Docstring contains '{content}'")
            else:
                print(f"  [WARN] Docstring missing '{content}'")

        # Check field descriptions
        input_fields = SpecGenerationSignature.input_fields
        output_fields = SpecGenerationSignature.output_fields

        all_fields = {**input_fields, **output_fields}
        desc_count = 0

        for name, field_info in all_fields.items():
            if hasattr(field_info, "json_schema_extra") and field_info.json_schema_extra:
                desc = field_info.json_schema_extra.get("desc")
                if desc and len(desc) > 10:
                    desc_count += 1

        print(f"  [PASS] {desc_count}/{len(all_fields)} fields have descriptions")

        return desc_count == len(all_fields)

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def verify_step_6():
    """Step 6: Add chain-of-thought reasoning field"""
    print("\n=== Step 6: Add chain-of-thought reasoning field ===")

    try:
        import dspy
        from api.dspy_signatures import SpecGenerationSignature

        # Check reasoning field exists
        output_fields = SpecGenerationSignature.output_fields

        if "reasoning" not in output_fields:
            print("  [FAIL] 'reasoning' field not found in output fields")
            return False
        print("  [PASS] 'reasoning' field exists in output fields")

        # Check reasoning field type
        fields = SpecGenerationSignature.model_fields
        if fields["reasoning"].annotation == str:
            print("  [PASS] 'reasoning' field has str type")
        else:
            print(f"  [WARN] 'reasoning' field type is {fields['reasoning'].annotation}")

        # Check reasoning field description
        reasoning_field = output_fields["reasoning"]
        if hasattr(reasoning_field, "json_schema_extra") and reasoning_field.json_schema_extra:
            desc = reasoning_field.json_schema_extra.get("desc", "")
            if any(term in desc.lower() for term in ["chain", "thought", "reason"]):
                print("  [PASS] 'reasoning' field description mentions chain-of-thought")
            else:
                print("  [WARN] 'reasoning' field description doesn't explicitly mention chain-of-thought")
        else:
            print("  [WARN] 'reasoning' field has no description")

        # Verify ChainOfThought module works
        try:
            cot = dspy.ChainOfThought(SpecGenerationSignature)
            print("  [PASS] ChainOfThought module works with signature")
        except Exception as e:
            print(f"  [FAIL] ChainOfThought module failed: {e}")
            return False

        return True

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def verify_utility_functions():
    """Verify utility functions in the module."""
    print("\n=== Bonus: Verify Utility Functions ===")

    try:
        from api.dspy_signatures import (
            get_spec_generator,
            validate_spec_output,
            VALID_TASK_TYPES,
            DEFAULT_BUDGETS,
        )

        # Check get_spec_generator
        generator = get_spec_generator()
        if generator is not None:
            print("  [PASS] get_spec_generator() returns a module")
        else:
            print("  [FAIL] get_spec_generator() returned None")
            return False

        # Check VALID_TASK_TYPES
        expected_types = {"coding", "testing", "refactoring", "documentation", "audit", "custom"}
        if set(VALID_TASK_TYPES) == expected_types:
            print(f"  [PASS] VALID_TASK_TYPES contains {len(expected_types)} types")
        else:
            print(f"  [WARN] VALID_TASK_TYPES mismatch")

        # Check DEFAULT_BUDGETS
        if all(task_type in DEFAULT_BUDGETS for task_type in VALID_TASK_TYPES):
            print(f"  [PASS] DEFAULT_BUDGETS has entries for all task types")
        else:
            print("  [WARN] DEFAULT_BUDGETS missing some task types")

        return True

    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False


def verify_api_exports():
    """Verify exports from api package."""
    print("\n=== Bonus: Verify API Package Exports ===")

    try:
        from api import (
            SpecGenerationSignature,
            get_spec_generator,
            validate_spec_output,
            VALID_TASK_TYPES,
            DSPY_DEFAULT_BUDGETS,
        )

        exports = [
            "SpecGenerationSignature",
            "get_spec_generator",
            "validate_spec_output",
            "VALID_TASK_TYPES",
            "DSPY_DEFAULT_BUDGETS",
        ]

        for export in exports:
            print(f"  [PASS] {export} exported from api package")

        return True

    except ImportError as e:
        print(f"  [FAIL] Import error: {e}")
        return False


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #50: DSPy SpecGenerationSignature Definition")
    print("Verification Script")
    print("=" * 70)

    results = []

    # Required verification steps (from feature definition)
    results.append(("Step 1: Import dspy library", verify_step_1()))
    results.append(("Step 2: Define SpecGenerationSignature", verify_step_2()))
    results.append(("Step 3: Define input fields", verify_step_3()))
    results.append(("Step 4: Define output fields", verify_step_4()))
    results.append(("Step 5: Add docstring with field descriptions", verify_step_5()))
    results.append(("Step 6: Add chain-of-thought reasoning field", verify_step_6()))

    # Bonus verifications
    results.append(("Utility Functions", verify_utility_functions()))
    results.append(("API Package Exports", verify_api_exports()))

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = 0
    failed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Total: {passed} passed, {failed} failed")
    print("=" * 70)

    # Return overall status
    required_steps = results[:6]  # First 6 are the required steps
    all_required_passed = all(result for _, result in required_steps)

    if all_required_passed:
        print("\n[SUCCESS] All required verification steps PASSED")
        print("Feature #50 is ready to be marked as PASSING")
        return 0
    else:
        print("\n[FAILURE] Some required verification steps FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
