"""
Feature #74 Tests: Validator Type Icons
=======================================

Verifies that validator type icons are correctly defined and used in:
- validatorIcons.ts (icon map definition)
- ValidatorTypeIcon.tsx (component)
- AcceptanceResults.tsx (Step 7: Use in AcceptanceResults component)
- DynamicAgentCard.tsx (Step 8: Use in validator status indicators)
"""

import subprocess
import sys
from pathlib import Path


def test_feature_74_icon_map_defined():
    """Step 1: Define icon map for validator types"""
    validator_icons_path = Path("ui/src/lib/validatorIcons.ts")
    assert validator_icons_path.exists(), "validatorIcons.ts should exist"

    content = validator_icons_path.read_text()
    assert "VALIDATOR_ICON_MAP" in content, "Icon map should be defined"
    assert "ValidatorIconConfig" in content, "ValidatorIconConfig interface should be defined"


def test_feature_74_test_pass_terminal_icon():
    """Step 2: test_pass: terminal icon"""
    validator_icons_path = Path("ui/src/lib/validatorIcons.ts")
    content = validator_icons_path.read_text()

    assert "test_pass" in content, "test_pass validator type should be defined"
    assert "Terminal" in content, "Terminal icon should be imported"
    # Check test_pass uses Terminal
    assert content.find("test_pass") < content.find("Terminal") or \
           "icon: Terminal" in content, "test_pass should use Terminal icon"


def test_feature_74_file_exists_file_icon():
    """Step 3: file_exists: file icon"""
    validator_icons_path = Path("ui/src/lib/validatorIcons.ts")
    content = validator_icons_path.read_text()

    assert "file_exists" in content, "file_exists validator type should be defined"
    assert "FileText" in content, "FileText icon should be imported"


def test_feature_74_lint_clean_code_icon():
    """Step 4: lint_clean: code icon"""
    validator_icons_path = Path("ui/src/lib/validatorIcons.ts")
    content = validator_icons_path.read_text()

    assert "lint_clean" in content, "lint_clean validator type should be defined"
    assert "Code" in content, "Code icon should be imported"


def test_feature_74_forbidden_patterns_shield_icon():
    """Step 5: forbidden_patterns: shield icon"""
    validator_icons_path = Path("ui/src/lib/validatorIcons.ts")
    content = validator_icons_path.read_text()

    assert "forbidden_patterns" in content, "forbidden_patterns validator type should be defined"
    assert "Shield" in content, "Shield icon should be imported"


def test_feature_74_custom_gear_icon():
    """Step 6: custom: gear icon"""
    validator_icons_path = Path("ui/src/lib/validatorIcons.ts")
    content = validator_icons_path.read_text()

    assert "custom" in content, "custom validator type should be defined"
    assert "Settings" in content, "Settings (gear) icon should be imported"


def test_feature_74_used_in_acceptance_results():
    """Step 7: Use in AcceptanceResults component"""
    acceptance_results_path = Path("ui/src/components/AcceptanceResults.tsx")
    content = acceptance_results_path.read_text()

    assert "ValidatorTypeIcon" in content, "ValidatorTypeIcon should be imported in AcceptanceResults"
    assert "import { ValidatorTypeIcon }" in content, "ValidatorTypeIcon should be imported"
    # Check it's actually used in the component
    assert "<ValidatorTypeIcon" in content, "ValidatorTypeIcon should be used in AcceptanceResults"


def test_feature_74_used_in_validator_status_indicators():
    """Step 8: Use in validator status indicators on card"""
    dynamic_agent_card_path = Path("ui/src/components/DynamicAgentCard.tsx")
    content = dynamic_agent_card_path.read_text()

    assert "ValidatorTypeIcon" in content, "ValidatorTypeIcon should be imported in DynamicAgentCard"
    assert "import { ValidatorTypeIcon }" in content, "ValidatorTypeIcon should be imported"
    # Check it's used in ValidatorStatusIndicators
    assert "<ValidatorTypeIcon" in content, "ValidatorTypeIcon should be used in DynamicAgentCard"


def test_feature_74_component_exists():
    """Verify ValidatorTypeIcon component exists"""
    component_path = Path("ui/src/components/ValidatorTypeIcon.tsx")
    assert component_path.exists(), "ValidatorTypeIcon.tsx component should exist"

    content = component_path.read_text()
    assert "export function ValidatorTypeIcon" in content, "ValidatorTypeIcon function should be exported"
    assert "getValidatorIconConfig" in content, "Should use getValidatorIconConfig from validatorIcons"


def test_feature_74_build_succeeds():
    """Verify frontend builds without errors"""
    result = subprocess.run(
        ["npm", "run", "build", "--prefix", "ui"],
        capture_output=True,
        text=True,
        timeout=120
    )
    assert result.returncode == 0, f"Build should succeed: {result.stderr}"


if __name__ == "__main__":
    # Run all tests
    test_functions = [
        test_feature_74_icon_map_defined,
        test_feature_74_test_pass_terminal_icon,
        test_feature_74_file_exists_file_icon,
        test_feature_74_lint_clean_code_icon,
        test_feature_74_forbidden_patterns_shield_icon,
        test_feature_74_custom_gear_icon,
        test_feature_74_used_in_acceptance_results,
        test_feature_74_used_in_validator_status_indicators,
        test_feature_74_component_exists,
        test_feature_74_build_succeeds,
    ]

    passed = 0
    failed = 0

    for test_fn in test_functions:
        try:
            test_fn()
            print(f"PASS: {test_fn.__doc__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test_fn.__doc__}\n  Error: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test_fn.__doc__}\n  Exception: {e}")
            failed += 1

    print(f"\n{passed}/{len(test_functions)} tests passed")
    sys.exit(0 if failed == 0 else 1)
