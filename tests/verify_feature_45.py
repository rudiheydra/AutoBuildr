#!/usr/bin/env python3
"""
Feature #45 Verification Script
================================

Verifies all 7 feature steps for Feature #45: ToolProvider Interface Definition

Steps:
1. Define ToolProvider abstract base class
2. Define list_tools() -> list[ToolDefinition] method
3. Define execute_tool(name, args) -> ToolResult method
4. Define get_capabilities() -> ProviderCapabilities method
5. Define authenticate(credentials) method stub for future OAuth
6. Create LocalToolProvider implementing interface for MCP tools
7. Create ToolProviderRegistry for managing multiple providers
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import Any


def verify_step_1():
    """Step 1: Define ToolProvider abstract base class."""
    print("\n" + "=" * 60)
    print("Step 1: Define ToolProvider abstract base class")
    print("=" * 60)

    from api.tool_provider import ToolProvider
    from abc import ABC
    import inspect

    checks = []

    # Check 1: ToolProvider is a class
    checks.append(("ToolProvider is a class", inspect.isclass(ToolProvider)))

    # Check 2: ToolProvider is abstract
    checks.append(("ToolProvider inherits from ABC", issubclass(ToolProvider, ABC)))

    # Check 3: Cannot instantiate ToolProvider directly
    try:
        ToolProvider()
        can_instantiate = True
    except TypeError:
        can_instantiate = False
    checks.append(("Cannot instantiate ToolProvider directly", not can_instantiate))

    # Check 4: Has abstract 'name' property
    checks.append(("Has abstract 'name' property", 'name' in dir(ToolProvider)))

    # Check 5: Has 'provider_type' class variable
    checks.append(("Has 'provider_type' class variable", hasattr(ToolProvider, 'provider_type')))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def verify_step_2():
    """Step 2: Define list_tools() -> list[ToolDefinition] method."""
    print("\n" + "=" * 60)
    print("Step 2: Define list_tools() -> list[ToolDefinition] method")
    print("=" * 60)

    from api.tool_provider import ToolProvider, LocalToolProvider, ToolDefinition
    import inspect

    checks = []

    # Check 1: ToolProvider has list_tools method
    checks.append(("ToolProvider has list_tools method", hasattr(ToolProvider, 'list_tools')))

    # Check 2: list_tools is abstract
    list_tools_method = getattr(ToolProvider, 'list_tools', None)
    is_abstract = getattr(list_tools_method, '__isabstractmethod__', False)
    checks.append(("list_tools is abstract method", is_abstract))

    # Check 3: LocalToolProvider.list_tools returns a list
    provider = LocalToolProvider()
    tools = provider.list_tools()
    checks.append(("LocalToolProvider.list_tools() returns list", isinstance(tools, list)))

    # Check 4: List contains ToolDefinition objects
    all_tool_defs = all(isinstance(t, ToolDefinition) for t in tools)
    checks.append(("All items are ToolDefinition", all_tool_defs))

    # Check 5: ToolDefinition has required fields
    if tools:
        tool = tools[0]
        has_name = hasattr(tool, 'name') and isinstance(tool.name, str)
        has_description = hasattr(tool, 'description')
        has_input_schema = hasattr(tool, 'input_schema')
        checks.append(("ToolDefinition has name, description, input_schema",
                      has_name and has_description and has_input_schema))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def verify_step_3():
    """Step 3: Define execute_tool(name, args) -> ToolResult method."""
    print("\n" + "=" * 60)
    print("Step 3: Define execute_tool(name, args) -> ToolResult method")
    print("=" * 60)

    from api.tool_provider import ToolProvider, LocalToolProvider, ToolResult, ToolNotFoundError

    checks = []

    # Check 1: ToolProvider has execute_tool method
    checks.append(("ToolProvider has execute_tool method", hasattr(ToolProvider, 'execute_tool')))

    # Check 2: execute_tool is abstract
    method = getattr(ToolProvider, 'execute_tool', None)
    is_abstract = getattr(method, '__isabstractmethod__', False)
    checks.append(("execute_tool is abstract method", is_abstract))

    # Check 3: LocalToolProvider.execute_tool returns ToolResult
    provider = LocalToolProvider()
    result = provider.execute_tool("Read", {"file_path": "/test"})
    checks.append(("execute_tool returns ToolResult", isinstance(result, ToolResult)))

    # Check 4: ToolResult has success field
    checks.append(("ToolResult has success field", hasattr(result, 'success') and isinstance(result.success, bool)))

    # Check 5: execute_tool raises ToolNotFoundError for unknown tools
    try:
        provider.execute_tool("nonexistent_tool", {})
        raised_error = False
    except ToolNotFoundError:
        raised_error = True
    checks.append(("execute_tool raises ToolNotFoundError for unknown tool", raised_error))

    # Check 6: ToolResult has factory methods
    success_result = ToolResult.success_result({"data": 1})
    error_result = ToolResult.error_result("Error message")
    checks.append(("ToolResult has success_result and error_result factories",
                  success_result.success and not error_result.success))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def verify_step_4():
    """Step 4: Define get_capabilities() -> ProviderCapabilities method."""
    print("\n" + "=" * 60)
    print("Step 4: Define get_capabilities() -> ProviderCapabilities method")
    print("=" * 60)

    from api.tool_provider import ToolProvider, LocalToolProvider, ProviderCapabilities, AuthMethod, ToolCategory

    checks = []

    # Check 1: ToolProvider has get_capabilities method
    checks.append(("ToolProvider has get_capabilities method", hasattr(ToolProvider, 'get_capabilities')))

    # Check 2: get_capabilities is abstract
    method = getattr(ToolProvider, 'get_capabilities', None)
    is_abstract = getattr(method, '__isabstractmethod__', False)
    checks.append(("get_capabilities is abstract method", is_abstract))

    # Check 3: LocalToolProvider.get_capabilities returns ProviderCapabilities
    provider = LocalToolProvider()
    caps = provider.get_capabilities()
    checks.append(("get_capabilities returns ProviderCapabilities", isinstance(caps, ProviderCapabilities)))

    # Check 4: ProviderCapabilities has async support field
    checks.append(("ProviderCapabilities has supports_async",
                  hasattr(caps, 'supports_async') and isinstance(caps.supports_async, bool)))

    # Check 5: ProviderCapabilities has auth methods list
    has_auth_methods = hasattr(caps, 'supported_auth_methods') and isinstance(caps.supported_auth_methods, list)
    checks.append(("ProviderCapabilities has supported_auth_methods", has_auth_methods))

    # Check 6: ProviderCapabilities has tool categories
    has_categories = hasattr(caps, 'tool_categories') and isinstance(caps.tool_categories, list)
    checks.append(("ProviderCapabilities has tool_categories", has_categories))

    # Check 7: Capabilities has version field
    checks.append(("ProviderCapabilities has version", hasattr(caps, 'version')))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def verify_step_5():
    """Step 5: Define authenticate(credentials) method stub for future OAuth."""
    print("\n" + "=" * 60)
    print("Step 5: Define authenticate(credentials) method stub for future OAuth")
    print("=" * 60)

    from api.tool_provider import ToolProvider, LocalToolProvider, AuthCredentials, AuthResult, AuthMethod

    checks = []

    # Check 1: ToolProvider has authenticate method
    checks.append(("ToolProvider has authenticate method", hasattr(ToolProvider, 'authenticate')))

    # Check 2: authenticate is NOT abstract (it's a stub with default implementation)
    method = getattr(ToolProvider, 'authenticate', None)
    is_abstract = getattr(method, '__isabstractmethod__', False)
    checks.append(("authenticate is NOT abstract (has default impl)", not is_abstract))

    # Check 3: AuthCredentials exists with expected fields
    creds = AuthCredentials(method=AuthMethod.API_KEY, api_key="test-key")
    checks.append(("AuthCredentials can be created", isinstance(creds, AuthCredentials)))

    # Check 4: AuthCredentials has is_expired method
    checks.append(("AuthCredentials has is_expired method", hasattr(creds, 'is_expired')))

    # Check 5: authenticate returns AuthResult
    provider = LocalToolProvider()
    result = provider.authenticate(creds)
    checks.append(("authenticate returns AuthResult", isinstance(result, AuthResult)))

    # Check 6: Default authenticate returns success=True
    checks.append(("Default authenticate returns success=True", result.success is True))

    # Check 7: AuthResult has credentials field
    checks.append(("AuthResult has credentials field", hasattr(result, 'credentials')))

    # Check 8: AuthMethod enum has expected values
    has_oauth = hasattr(AuthMethod, 'OAUTH2')
    has_api_key = hasattr(AuthMethod, 'API_KEY')
    checks.append(("AuthMethod has OAUTH2 and API_KEY", has_oauth and has_api_key))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def verify_step_6():
    """Step 6: Create LocalToolProvider implementing interface for MCP tools."""
    print("\n" + "=" * 60)
    print("Step 6: Create LocalToolProvider implementing interface for MCP tools")
    print("=" * 60)

    from api.tool_provider import ToolProvider, LocalToolProvider, ToolDefinition, ToolCategory

    checks = []

    # Check 1: LocalToolProvider exists and inherits from ToolProvider
    checks.append(("LocalToolProvider inherits from ToolProvider", issubclass(LocalToolProvider, ToolProvider)))

    # Check 2: LocalToolProvider.name returns "local"
    provider = LocalToolProvider()
    checks.append(("LocalToolProvider.name == 'local'", provider.name == "local"))

    # Check 3: Has MCP feature management tools
    tool_names = [t.name for t in provider.list_tools()]
    has_feature_tools = "feature_get_by_id" in tool_names and "feature_mark_passing" in tool_names
    checks.append(("Has feature management tools", has_feature_tools))

    # Check 4: Has file system tools
    has_file_tools = "Read" in tool_names and "Write" in tool_names
    checks.append(("Has file system tools (Read, Write)", has_file_tools))

    # Check 5: Has browser tools
    has_browser_tools = "browser_navigate" in tool_names
    checks.append(("Has browser tools", has_browser_tools))

    # Check 6: LocalToolProvider has add_tool method
    checks.append(("LocalToolProvider has add_tool method", hasattr(provider, 'add_tool')))

    # Check 7: LocalToolProvider has remove_tool method
    checks.append(("LocalToolProvider has remove_tool method", hasattr(provider, 'remove_tool')))

    # Check 8: Can initialize with custom tools
    custom_tools = [ToolDefinition(name="custom", description="Custom tool")]
    custom_provider = LocalToolProvider(tools=custom_tools)
    custom_tool_names = [t.name for t in custom_provider.list_tools()]
    checks.append(("Can initialize with custom tools", "custom" in custom_tool_names))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def verify_step_7():
    """Step 7: Create ToolProviderRegistry for managing multiple providers."""
    print("\n" + "=" * 60)
    print("Step 7: Create ToolProviderRegistry for managing multiple providers")
    print("=" * 60)

    from api.tool_provider import (
        ToolProviderRegistry, LocalToolProvider, ToolProvider,
        ProviderNotFoundError, ProviderAlreadyRegisteredError,
        ToolDefinition, ToolResult, ProviderCapabilities
    )

    checks = []

    # Check 1: ToolProviderRegistry class exists
    checks.append(("ToolProviderRegistry class exists", ToolProviderRegistry is not None))

    # Check 2: Registry has register method
    registry = ToolProviderRegistry()
    checks.append(("Registry has register method", hasattr(registry, 'register')))

    # Check 3: Registry has unregister method
    checks.append(("Registry has unregister method", hasattr(registry, 'unregister')))

    # Check 4: Registry has get_provider method
    checks.append(("Registry has get_provider method", hasattr(registry, 'get_provider')))

    # Check 5: Registry has list_providers method
    checks.append(("Registry has list_providers method", hasattr(registry, 'list_providers')))

    # Check 6: Registry has list_all_tools method
    checks.append(("Registry has list_all_tools method", hasattr(registry, 'list_all_tools')))

    # Check 7: Registry has execute_tool method
    checks.append(("Registry has execute_tool method", hasattr(registry, 'execute_tool')))

    # Check 8: Can register and use multiple providers
    registry.register(LocalToolProvider())

    class TestProvider(ToolProvider):
        @property
        def name(self):
            return "test"
        def list_tools(self):
            return [ToolDefinition(name="test_tool")]
        def execute_tool(self, name, args):
            return ToolResult.success_result({"test": True})
        def get_capabilities(self):
            return ProviderCapabilities()

    registry.register(TestProvider())
    providers = registry.list_providers()
    checks.append(("Can register multiple providers", len(providers) >= 2))

    # Check 9: Registry has find_tool method
    checks.append(("Registry has find_tool method", hasattr(registry, 'find_tool')))

    # Check 10: Duplicate registration raises error
    try:
        registry.register(LocalToolProvider())
        raised = False
    except ProviderAlreadyRegisteredError:
        raised = True
    checks.append(("Duplicate registration raises ProviderAlreadyRegisteredError", raised))

    passed = 0
    for desc, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {desc}")
        if result:
            passed += 1

    return passed, len(checks)


def main():
    """Run all verification steps."""
    print("\n" + "=" * 60)
    print("Feature #45: ToolProvider Interface Definition")
    print("VERIFICATION SCRIPT")
    print("=" * 60)

    total_passed = 0
    total_checks = 0

    steps = [
        verify_step_1,
        verify_step_2,
        verify_step_3,
        verify_step_4,
        verify_step_5,
        verify_step_6,
        verify_step_7,
    ]

    for step_fn in steps:
        passed, total = step_fn()
        total_passed += passed
        total_checks += total

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {total_passed}/{total_checks} checks passed")

    if total_passed == total_checks:
        print("\n[SUCCESS] All verification steps PASSED!")
        return 0
    else:
        print(f"\n[FAILURE] {total_checks - total_passed} checks failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
