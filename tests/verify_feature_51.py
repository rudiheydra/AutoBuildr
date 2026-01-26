#!/usr/bin/env python3
"""
Feature #51 Verification Script
==============================

Verifies: Skill Template Registry

Steps:
1. Create TemplateRegistry class
2. Scan prompts/ directory for template files
3. Parse template metadata (task_type, required_tools, etc.)
4. Index templates by task_type
5. Implement get_template(task_type) -> Template
6. Implement interpolate(template, variables) -> str
7. Cache compiled templates for performance
8. Handle missing template gracefully with fallback
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.template_registry import (
    Template,
    TemplateMetadata,
    TemplateRegistry,
    TemplateNotFoundError,
    interpolate,
    parse_front_matter,
    find_variables,
)


def verify_step(step_num: int, description: str, passed: bool, details: str = ""):
    """Print verification result for a step."""
    status = "PASS" if passed else "FAIL"
    print(f"Step {step_num}: {description} - {status}")
    if details:
        print(f"  Details: {details}")
    return passed


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #51: Skill Template Registry - Verification")
    print("=" * 60)
    print()

    all_passed = True

    # Create a temporary directory with test templates
    with tempfile.TemporaryDirectory() as tmpdir:
        prompts_dir = Path(tmpdir) / "prompts"
        prompts_dir.mkdir()

        # Create sample templates
        coding_template = prompts_dir / "coding_prompt.md"
        coding_template.write_text("""---
task_type: coding
name: Coding Agent Template
description: Template for coding tasks
required_tools:
  - feature_get_by_id
  - feature_mark_passing
  - browser_navigate
default_max_turns: 100
default_timeout_seconds: 3600
icon: code
---
## YOUR ROLE - CODING AGENT

You are working on feature {{feature_id}} for project {{project_name}}.

Your objective: {{objective}}
""")

        testing_template = prompts_dir / "testing_prompt.md"
        testing_template.write_text("""---
task_type: testing
name: Testing Agent
required_tools:
  - browser_navigate
  - browser_click
default_max_turns: 50
---
## TESTING AGENT

Testing feature {{feature_id}}.
""")

        # Step 1: Create TemplateRegistry class
        try:
            registry = TemplateRegistry(prompts_dir, auto_scan=False)
            step1_passed = isinstance(registry, TemplateRegistry)
            all_passed &= verify_step(1, "Create TemplateRegistry class", step1_passed,
                                      f"TemplateRegistry instance created for {prompts_dir}")
        except Exception as e:
            all_passed &= verify_step(1, "Create TemplateRegistry class", False, str(e))

        # Step 2: Scan prompts/ directory for template files
        try:
            count = registry.scan()
            templates = registry.list_templates()
            step2_passed = count == 2 and len(templates) == 2
            all_passed &= verify_step(2, "Scan prompts/ directory for template files", step2_passed,
                                      f"Found {count} templates: {[t['name'] for t in templates]}")
        except Exception as e:
            all_passed &= verify_step(2, "Scan prompts/ directory for template files", False, str(e))

        # Step 3: Parse template metadata (task_type, required_tools, etc.)
        try:
            template = registry.get_template(task_type="coding")
            metadata = template.metadata

            step3_checks = [
                metadata.task_type == "coding",
                metadata.name == "Coding Agent Template",
                "feature_get_by_id" in metadata.required_tools,
                metadata.default_max_turns == 100,
                metadata.default_timeout_seconds == 3600,
                metadata.icon == "code",
            ]
            step3_passed = all(step3_checks)
            all_passed &= verify_step(3, "Parse template metadata (task_type, required_tools, etc.)", step3_passed,
                                      f"task_type={metadata.task_type}, required_tools={metadata.required_tools}, "
                                      f"default_max_turns={metadata.default_max_turns}")
        except Exception as e:
            all_passed &= verify_step(3, "Parse template metadata (task_type, required_tools, etc.)", False, str(e))

        # Step 4: Index templates by task_type
        try:
            task_types = registry.list_task_types()
            step4_passed = "coding" in task_types and "testing" in task_types
            all_passed &= verify_step(4, "Index templates by task_type", step4_passed,
                                      f"Indexed task_types: {task_types}")
        except Exception as e:
            all_passed &= verify_step(4, "Index templates by task_type", False, str(e))

        # Step 5: Implement get_template(task_type) -> Template
        try:
            # Get by task_type
            coding_tmpl = registry.get_template(task_type="coding")
            # Get by name
            testing_tmpl = registry.get_template(name="testing")
            # Get by name without suffix
            coding_by_name = registry.get_template(name="coding_prompt")

            step5_passed = (
                isinstance(coding_tmpl, Template) and
                isinstance(testing_tmpl, Template) and
                isinstance(coding_by_name, Template) and
                coding_tmpl.metadata.task_type == "coding" and
                testing_tmpl.metadata.task_type == "testing"
            )
            all_passed &= verify_step(5, "Implement get_template(task_type) -> Template", step5_passed,
                                      f"Retrieved templates by task_type and name successfully")
        except Exception as e:
            all_passed &= verify_step(5, "Implement get_template(task_type) -> Template", False, str(e))

        # Step 6: Implement interpolate(template, variables) -> str
        try:
            template = registry.get_template(task_type="coding")
            interpolated = registry.interpolate(template, {
                "feature_id": 42,
                "project_name": "AutoBuildr",
                "objective": "Implement template registry",
            })

            step6_passed = (
                "42" in interpolated and
                "AutoBuildr" in interpolated and
                "Implement template registry" in interpolated
            )

            # Also test find_variables
            variables = find_variables(template.content)
            step6_passed = step6_passed and "feature_id" in variables

            all_passed &= verify_step(6, "Implement interpolate(template, variables) -> str", step6_passed,
                                      f"Variables found: {variables}, interpolation successful")
        except Exception as e:
            all_passed &= verify_step(6, "Implement interpolate(template, variables) -> str", False, str(e))

        # Step 7: Cache compiled templates for performance
        try:
            # First access
            template1 = registry.get_template(task_type="coding")
            hash1 = template1.content_hash

            # Second access should return cached object
            template2 = registry.get_template(task_type="coding")
            hash2 = template2.content_hash

            # Same object (cached)
            same_object = template1 is template2

            # Test cache invalidation - modify file
            time.sleep(0.1)  # Ensure mtime changes
            original_content = coding_template.read_text()
            coding_template.write_text(original_content + "\n# Modified")

            # Should get new version
            template3 = registry.get_template(task_type="coding")
            hash3 = template3.content_hash

            # Restore original
            coding_template.write_text(original_content)

            step7_passed = (
                same_object and  # Cache works
                hash3 != hash1   # Cache invalidation works
            )
            all_passed &= verify_step(7, "Cache compiled templates for performance", step7_passed,
                                      f"Cache works={same_object}, invalidation works={hash3 != hash1}")
        except Exception as e:
            all_passed &= verify_step(7, "Cache compiled templates for performance", False, str(e))

        # Step 8: Handle missing template gracefully with fallback
        try:
            # Test graceful return of None
            missing = registry.get_template(task_type="nonexistent")
            returns_none = missing is None

            # Test exception when use_fallback=False
            raises_exception = False
            try:
                registry.get_template(task_type="nonexistent", use_fallback=False)
            except TemplateNotFoundError as e:
                raises_exception = True
                exception_has_identifier = e.identifier == "nonexistent"

            # Test fallback template
            coding = registry.get_template(task_type="coding")
            registry.set_fallback_template(coding)
            with_fallback = registry.get_template(task_type="nonexistent")
            fallback_works = with_fallback is coding

            # Clear fallback
            registry.set_fallback_template(None)

            step8_passed = (
                returns_none and
                raises_exception and
                exception_has_identifier and
                fallback_works
            )
            all_passed &= verify_step(8, "Handle missing template gracefully with fallback", step8_passed,
                                      f"Returns None={returns_none}, raises exception={raises_exception}, "
                                      f"fallback works={fallback_works}")
        except Exception as e:
            all_passed &= verify_step(8, "Handle missing template gracefully with fallback", False, str(e))

    # Now test with real prompts directory
    print()
    print("-" * 40)
    print("Bonus: Testing with real prompts/ directory")
    print("-" * 40)

    real_prompts = project_root / "prompts"
    if real_prompts.exists():
        try:
            real_registry = TemplateRegistry(real_prompts, auto_scan=True)
            templates = real_registry.list_templates()
            task_types = real_registry.list_task_types()

            print(f"  Found {len(templates)} templates: {[t['name'] for t in templates]}")
            print(f"  Task types: {task_types}")

            # Try to get coding template
            coding = real_registry.get_template(name="coding")
            if coding:
                print(f"  Coding template loaded: {len(coding.content)} chars")
                print(f"    Variables: {coding.metadata.variables[:5]}..." if coding.metadata.variables else "    No variables")
        except Exception as e:
            print(f"  Error loading real templates: {e}")
    else:
        print(f"  Real prompts directory not found at {real_prompts}")

    # Summary
    print()
    print("=" * 60)
    if all_passed:
        print("RESULT: ALL STEPS PASSED")
    else:
        print("RESULT: SOME STEPS FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
