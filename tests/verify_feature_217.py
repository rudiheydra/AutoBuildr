#!/usr/bin/env python
"""
Feature #217 Verification Script
================================

Icon provider is configurable via settings.

This script verifies all 5 feature steps:
1. ICON_PROVIDER environment variable or config setting
2. Default value: 'local_placeholder'
3. Future value: 'nano_banana' or other
4. Invalid provider falls back to placeholder
5. Configuration documented
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_header(step_num: int, title: str):
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"Step {step_num}: {title}")
    print('='*60)


def print_pass(msg: str):
    """Print a pass message."""
    print(f"  ✅ PASS: {msg}")


def print_fail(msg: str):
    """Print a fail message."""
    print(f"  ❌ FAIL: {msg}")


def verify_step1_env_var_or_config():
    """Verify Step 1: ICON_PROVIDER environment variable or config setting."""
    print_header(1, "ICON_PROVIDER environment variable or config setting")

    from api.icon_provider_config import (
        ENV_VAR_ICON_PROVIDER,
        SETTINGS_ICON_PROVIDER_KEY,
        get_env_icon_provider,
        get_settings_icon_provider,
        resolve_icon_provider,
        ConfigSource,
        clear_icon_provider_override,
    )

    # Clear any override
    clear_icon_provider_override()

    all_pass = True

    # 1.1: ENV_VAR_ICON_PROVIDER constant
    if ENV_VAR_ICON_PROVIDER == "ICON_PROVIDER":
        print_pass("ENV_VAR_ICON_PROVIDER = 'ICON_PROVIDER'")
    else:
        print_fail(f"ENV_VAR_ICON_PROVIDER = '{ENV_VAR_ICON_PROVIDER}', expected 'ICON_PROVIDER'")
        all_pass = False

    # 1.2: SETTINGS_ICON_PROVIDER_KEY constant
    if SETTINGS_ICON_PROVIDER_KEY == "icon_provider":
        print_pass("SETTINGS_ICON_PROVIDER_KEY = 'icon_provider'")
    else:
        print_fail(f"SETTINGS_ICON_PROVIDER_KEY = '{SETTINGS_ICON_PROVIDER_KEY}', expected 'icon_provider'")
        all_pass = False

    # 1.3: Test env var reading
    os.environ[ENV_VAR_ICON_PROVIDER] = "test_env_provider"
    result = get_env_icon_provider()
    if result == "test_env_provider":
        print_pass("get_env_icon_provider() reads ICON_PROVIDER env var")
    else:
        print_fail(f"get_env_icon_provider() returned '{result}', expected 'test_env_provider'")
        all_pass = False
    del os.environ[ENV_VAR_ICON_PROVIDER]

    # 1.4: Test settings reading
    settings = {"icon_provider": {"active": "test_settings_provider"}}
    result = get_settings_icon_provider(settings)
    if result == "test_settings_provider":
        print_pass("get_settings_icon_provider() reads from settings dict")
    else:
        print_fail(f"get_settings_icon_provider() returned '{result}', expected 'test_settings_provider'")
        all_pass = False

    # 1.5: Test env takes priority over settings
    os.environ[ENV_VAR_ICON_PROVIDER] = "local_placeholder"
    settings = {"icon_provider": {"active": "nano_banana"}}
    result = resolve_icon_provider(settings=settings)
    if result.source == ConfigSource.ENVIRONMENT:
        print_pass("Environment variable takes priority over settings")
    else:
        print_fail(f"Source is {result.source}, expected ENVIRONMENT")
        all_pass = False
    del os.environ[ENV_VAR_ICON_PROVIDER]

    return all_pass


def verify_step2_default_local_placeholder():
    """Verify Step 2: Default value: 'local_placeholder'."""
    print_header(2, "Default value: 'local_placeholder'")

    from api.icon_provider_config import (
        DEFAULT_ICON_PROVIDER,
        resolve_icon_provider,
        get_icon_provider,
        ConfigSource,
        clear_icon_provider_override,
    )

    # Clear any override
    clear_icon_provider_override()

    # Remove env var if set
    if "ICON_PROVIDER" in os.environ:
        del os.environ["ICON_PROVIDER"]

    all_pass = True

    # 2.1: DEFAULT_ICON_PROVIDER constant
    if DEFAULT_ICON_PROVIDER == "local_placeholder":
        print_pass("DEFAULT_ICON_PROVIDER = 'local_placeholder'")
    else:
        print_fail(f"DEFAULT_ICON_PROVIDER = '{DEFAULT_ICON_PROVIDER}', expected 'local_placeholder'")
        all_pass = False

    # 2.2: resolve_icon_provider returns default
    result = resolve_icon_provider()
    if result.provider_name == "local_placeholder":
        print_pass("resolve_icon_provider() returns 'local_placeholder' as default")
    else:
        print_fail(f"resolve_icon_provider() returned '{result.provider_name}'")
        all_pass = False

    # 2.3: Source is DEFAULT
    if result.source == ConfigSource.DEFAULT:
        print_pass("Source is ConfigSource.DEFAULT when nothing configured")
    else:
        print_fail(f"Source is {result.source}, expected DEFAULT")
        all_pass = False

    # 2.4: get_icon_provider convenience function
    name = get_icon_provider()
    if name == "local_placeholder":
        print_pass("get_icon_provider() returns 'local_placeholder' as default")
    else:
        print_fail(f"get_icon_provider() returned '{name}'")
        all_pass = False

    return all_pass


def verify_step3_nano_banana():
    """Verify Step 3: Future value: 'nano_banana' or other."""
    print_header(3, "Future value: 'nano_banana' or other")

    from api.icon_provider_config import (
        KNOWN_PROVIDERS,
        PROVIDER_ALIASES,
        is_valid_provider_name,
        normalize_provider_name,
        resolve_icon_provider,
        set_icon_provider,
        clear_icon_provider_override,
        ConfigSource,
    )

    # Clear any override
    clear_icon_provider_override()

    all_pass = True

    # 3.1: 'nano_banana' in KNOWN_PROVIDERS
    if "nano_banana" in KNOWN_PROVIDERS:
        print_pass("'nano_banana' is in KNOWN_PROVIDERS")
    else:
        print_fail("'nano_banana' is NOT in KNOWN_PROVIDERS")
        all_pass = False

    # 3.2: is_valid_provider_name
    if is_valid_provider_name("nano_banana"):
        print_pass("is_valid_provider_name('nano_banana') returns True")
    else:
        print_fail("is_valid_provider_name('nano_banana') returns False")
        all_pass = False

    # 3.3: Can set via env var
    os.environ["ICON_PROVIDER"] = "nano_banana"
    result = resolve_icon_provider()
    if result.provider_name == "nano_banana" and result.source == ConfigSource.ENVIRONMENT:
        print_pass("Can set 'nano_banana' via ICON_PROVIDER env var")
    else:
        print_fail(f"resolve_icon_provider() returned '{result.provider_name}' (source: {result.source})")
        all_pass = False
    del os.environ["ICON_PROVIDER"]

    # 3.4: Can set via settings
    clear_icon_provider_override()
    settings = {"icon_provider": {"active": "nano_banana"}}
    result = resolve_icon_provider(settings=settings)
    if result.provider_name == "nano_banana" and result.source == ConfigSource.SETTINGS:
        print_pass("Can set 'nano_banana' via settings")
    else:
        print_fail(f"resolve_icon_provider() returned '{result.provider_name}' (source: {result.source})")
        all_pass = False

    # 3.5: Aliases work
    if normalize_provider_name("nanobanana") == "nano_banana":
        print_pass("Alias 'nanobanana' normalizes to 'nano_banana'")
    else:
        print_fail(f"normalize_provider_name('nanobanana') returned '{normalize_provider_name('nanobanana')}'")
        all_pass = False

    clear_icon_provider_override()
    return all_pass


def verify_step4_fallback():
    """Verify Step 4: Invalid provider falls back to placeholder."""
    print_header(4, "Invalid provider falls back to placeholder")

    from api.icon_provider_config import (
        DEFAULT_ICON_PROVIDER,
        resolve_icon_provider,
        clear_icon_provider_override,
    )

    # Clear any override
    clear_icon_provider_override()

    all_pass = True

    # 4.1: Invalid env var falls back
    os.environ["ICON_PROVIDER"] = "totally_invalid_provider_xyz"
    result = resolve_icon_provider()
    if result.provider_name == DEFAULT_ICON_PROVIDER and result.fallback_used:
        print_pass("Invalid provider from env var falls back to default")
    else:
        print_fail(f"Got '{result.provider_name}', fallback_used={result.fallback_used}")
        all_pass = False
    del os.environ["ICON_PROVIDER"]

    # 4.2: Invalid settings falls back
    settings = {"icon_provider": {"active": "nonexistent_provider"}}
    result = resolve_icon_provider(settings=settings)
    if result.provider_name == DEFAULT_ICON_PROVIDER and result.fallback_used:
        print_pass("Invalid provider from settings falls back to default")
    else:
        print_fail(f"Got '{result.provider_name}', fallback_used={result.fallback_used}")
        all_pass = False

    # 4.3: original_value preserved
    if result.original_value == "nonexistent_provider":
        print_pass("Original invalid value preserved in result")
    else:
        print_fail(f"original_value is '{result.original_value}', expected 'nonexistent_provider'")
        all_pass = False

    # 4.4: is_valid is False when fallback used
    if result.is_valid is False:
        print_pass("is_valid is False when fallback is used")
    else:
        print_fail("is_valid should be False when fallback is used")
        all_pass = False

    return all_pass


def verify_step5_documentation():
    """Verify Step 5: Configuration documented."""
    print_header(5, "Configuration documented")

    from api.icon_provider_config import get_icon_provider_config_documentation

    all_pass = True

    docs = get_icon_provider_config_documentation()

    # 5.1: Documentation exists and is substantial
    if len(docs) > 200:
        print_pass(f"Documentation exists ({len(docs)} characters)")
    else:
        print_fail(f"Documentation too short ({len(docs)} characters)")
        all_pass = False

    # 5.2: Mentions ICON_PROVIDER env var
    if "ICON_PROVIDER" in docs:
        print_pass("Documentation mentions ICON_PROVIDER environment variable")
    else:
        print_fail("Documentation does not mention ICON_PROVIDER")
        all_pass = False

    # 5.3: Mentions settings file
    if "settings" in docs.lower() and "icon_provider" in docs:
        print_pass("Documentation mentions settings file configuration")
    else:
        print_fail("Documentation does not mention settings file")
        all_pass = False

    # 5.4: Mentions default value
    if "local_placeholder" in docs:
        print_pass("Documentation mentions default 'local_placeholder'")
    else:
        print_fail("Documentation does not mention default value")
        all_pass = False

    # 5.5: Mentions fallback behavior
    if "fallback" in docs.lower():
        print_pass("Documentation mentions fallback behavior")
    else:
        print_fail("Documentation does not mention fallback")
        all_pass = False

    return all_pass


def main():
    """Run all verification steps."""
    print("\n" + "="*60)
    print("Feature #217: Icon provider is configurable via settings")
    print("="*60)

    results = []

    results.append(("Step 1: Env var or config setting", verify_step1_env_var_or_config()))
    results.append(("Step 2: Default local_placeholder", verify_step2_default_local_placeholder()))
    results.append(("Step 3: Future value nano_banana", verify_step3_nano_banana()))
    results.append(("Step 4: Invalid provider fallback", verify_step4_fallback()))
    results.append(("Step 5: Configuration documented", verify_step5_documentation()))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = 0
    failed = 0
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {name}")
        if success:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed}/{len(results)} steps passed")

    if failed > 0:
        print("\n❌ VERIFICATION FAILED")
        return 1
    else:
        print("\n✅ ALL VERIFICATION STEPS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
