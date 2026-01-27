"""
Tests for Feature #45: ToolProvider Interface Definition

Comprehensive test suite for the ToolProvider interface, including:
- ToolProvider abstract base class
- list_tools() -> list[ToolDefinition] method
- execute_tool(name, args) -> ToolResult method
- get_capabilities() -> ProviderCapabilities method
- authenticate(credentials) method stub for future OAuth
- LocalToolProvider implementation
- ToolProviderRegistry for managing multiple providers
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import Mock, patch

from api.tool_provider import (
    # Exceptions
    ToolProviderError,
    ToolNotFoundError,
    ProviderNotFoundError,
    ProviderAlreadyRegisteredError,
    AuthenticationError,
    ToolExecutionError,
    # Enums
    ToolCategory,
    AuthMethod,
    ProviderStatus,
    # Data classes
    ToolDefinition,
    ToolResult,
    ProviderCapabilities,
    AuthCredentials,
    AuthResult,
    # Abstract base class
    ToolProvider,
    # Implementations
    LocalToolProvider,
    ToolProviderRegistry,
    # Module-level functions
    get_tool_registry,
    reset_tool_registry,
    register_provider,
    execute_tool,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_tool_definition():
    """Create a sample tool definition for testing."""
    return ToolDefinition(
        name="test_tool",
        description="A test tool",
        input_schema={
            "type": "object",
            "properties": {
                "arg1": {"type": "string"},
                "arg2": {"type": "integer"}
            },
            "required": ["arg1"]
        },
        output_schema={"type": "string"},
        category=ToolCategory.GENERAL,
        required_permissions=["read", "write"],
        timeout_seconds=60,
        metadata={"version": "1.0"},
    )


@pytest.fixture
def sample_tool_result():
    """Create a sample tool result for testing."""
    return ToolResult(
        success=True,
        output={"result": "success"},
        execution_time_ms=150,
        metadata={"version": "1.0"},
    )


@pytest.fixture
def sample_capabilities():
    """Create sample provider capabilities for testing."""
    return ProviderCapabilities(
        supports_async=True,
        supports_streaming=True,
        supports_batching=False,
        supports_cancellation=True,
        max_concurrent_calls=10,
        supported_auth_methods=[AuthMethod.API_KEY, AuthMethod.OAUTH2],
        rate_limit_per_minute=100,
        tool_categories=[ToolCategory.FILE_SYSTEM, ToolCategory.CODE_EXECUTION],
        version="2.0.0",
        metadata={"provider": "test"},
    )


@pytest.fixture
def sample_credentials():
    """Create sample credentials for testing."""
    return AuthCredentials(
        method=AuthMethod.API_KEY,
        api_key="test-api-key-12345",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.fixture
def local_provider():
    """Create a LocalToolProvider instance for testing."""
    return LocalToolProvider()


@pytest.fixture
def registry():
    """Create a fresh ToolProviderRegistry for testing."""
    return ToolProviderRegistry()


@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset the global registry before and after each test."""
    reset_tool_registry()
    yield
    reset_tool_registry()


# =============================================================================
# Exception Tests
# =============================================================================

class TestExceptions:
    """Tests for exception classes."""

    def test_tool_not_found_error(self):
        """Test ToolNotFoundError initialization."""
        error = ToolNotFoundError("my_tool", "my_provider")
        assert error.tool_name == "my_tool"
        assert error.provider_name == "my_provider"
        assert "my_tool" in str(error)
        assert "my_provider" in str(error)

    def test_provider_not_found_error_with_available(self):
        """Test ProviderNotFoundError with available providers."""
        error = ProviderNotFoundError("missing", ["local", "external"])
        assert error.provider_name == "missing"
        assert error.available_providers == ["local", "external"]
        assert "local" in str(error)
        assert "external" in str(error)

    def test_provider_not_found_error_empty(self):
        """Test ProviderNotFoundError with no providers."""
        error = ProviderNotFoundError("missing")
        assert "No providers are registered" in str(error)

    def test_provider_already_registered_error(self):
        """Test ProviderAlreadyRegisteredError."""
        error = ProviderAlreadyRegisteredError("duplicate")
        assert error.provider_name == "duplicate"
        assert "already registered" in str(error)

    def test_authentication_error(self):
        """Test AuthenticationError."""
        error = AuthenticationError("oauth_provider", "Invalid token")
        assert error.provider_name == "oauth_provider"
        assert error.reason == "Invalid token"
        assert "Invalid token" in str(error)

    def test_tool_execution_error(self):
        """Test ToolExecutionError."""
        error = ToolExecutionError(
            "broken_tool",
            "local",
            "Connection timeout",
            {"attempts": 3}
        )
        assert error.tool_name == "broken_tool"
        assert error.provider_name == "local"
        assert error.error == "Connection timeout"
        assert error.details == {"attempts": 3}


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    """Tests for enum classes."""

    def test_tool_category_values(self):
        """Test ToolCategory enum values."""
        assert ToolCategory.FILE_SYSTEM.value == "file_system"
        assert ToolCategory.DATABASE.value == "database"
        assert ToolCategory.BROWSER.value == "browser"
        assert ToolCategory.FEATURE_MANAGEMENT.value == "feature_management"

    def test_auth_method_values(self):
        """Test AuthMethod enum values."""
        assert AuthMethod.NONE.value == "none"
        assert AuthMethod.API_KEY.value == "api_key"
        assert AuthMethod.OAUTH2.value == "oauth2"
        assert AuthMethod.TOKEN.value == "token"

    def test_provider_status_values(self):
        """Test ProviderStatus enum values."""
        assert ProviderStatus.AVAILABLE.value == "available"
        assert ProviderStatus.UNAVAILABLE.value == "unavailable"
        assert ProviderStatus.RATE_LIMITED.value == "rate_limited"


# =============================================================================
# ToolDefinition Tests
# =============================================================================

class TestToolDefinition:
    """Tests for ToolDefinition dataclass."""

    def test_creation_with_defaults(self):
        """Test creating ToolDefinition with minimal args."""
        tool = ToolDefinition(name="simple")
        assert tool.name == "simple"
        assert tool.description == ""
        assert tool.input_schema == {}
        assert tool.output_schema is None
        assert tool.category == ToolCategory.GENERAL
        assert tool.required_permissions == []
        assert tool.timeout_seconds == 30
        assert tool.metadata == {}

    def test_creation_with_all_fields(self, sample_tool_definition):
        """Test creating ToolDefinition with all fields."""
        tool = sample_tool_definition
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert "arg1" in tool.input_schema["properties"]
        assert tool.output_schema == {"type": "string"}
        assert tool.category == ToolCategory.GENERAL
        assert "read" in tool.required_permissions
        assert tool.timeout_seconds == 60

    def test_to_dict(self, sample_tool_definition):
        """Test ToolDefinition to_dict method."""
        data = sample_tool_definition.to_dict()
        assert data["name"] == "test_tool"
        assert data["description"] == "A test tool"
        assert data["category"] == "general"
        assert data["timeout_seconds"] == 60

    def test_from_dict(self):
        """Test ToolDefinition from_dict class method."""
        data = {
            "name": "restored",
            "description": "Restored tool",
            "category": "file_system",
            "timeout_seconds": 120,
        }
        tool = ToolDefinition.from_dict(data)
        assert tool.name == "restored"
        assert tool.category == ToolCategory.FILE_SYSTEM
        assert tool.timeout_seconds == 120

    def test_from_dict_invalid_category(self):
        """Test ToolDefinition from_dict with invalid category."""
        data = {"name": "test", "category": "invalid_category"}
        tool = ToolDefinition.from_dict(data)
        assert tool.category == ToolCategory.GENERAL  # Falls back to GENERAL


# =============================================================================
# ToolResult Tests
# =============================================================================

class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_creation_with_defaults(self):
        """Test creating ToolResult with minimal args."""
        result = ToolResult(success=True)
        assert result.success is True
        assert result.output is None
        assert result.error is None
        assert result.execution_time_ms == 0

    def test_success_result_factory(self):
        """Test ToolResult.success_result factory method."""
        result = ToolResult.success_result({"data": 42}, 150)
        assert result.success is True
        assert result.output == {"data": 42}
        assert result.execution_time_ms == 150
        assert result.error is None

    def test_error_result_factory(self):
        """Test ToolResult.error_result factory method."""
        result = ToolResult.error_result("Something went wrong", "ERR_001", 50)
        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.error_code == "ERR_001"
        assert result.execution_time_ms == 50

    def test_to_dict(self, sample_tool_result):
        """Test ToolResult to_dict method."""
        data = sample_tool_result.to_dict()
        assert data["success"] is True
        assert data["output"] == {"result": "success"}
        assert data["execution_time_ms"] == 150

    def test_from_dict(self):
        """Test ToolResult from_dict class method."""
        data = {
            "success": False,
            "error": "Test error",
            "error_code": "ERR_TEST",
            "execution_time_ms": 200,
        }
        result = ToolResult.from_dict(data)
        assert result.success is False
        assert result.error == "Test error"
        assert result.error_code == "ERR_TEST"


# =============================================================================
# ProviderCapabilities Tests
# =============================================================================

class TestProviderCapabilities:
    """Tests for ProviderCapabilities dataclass."""

    def test_creation_with_defaults(self):
        """Test creating ProviderCapabilities with defaults."""
        caps = ProviderCapabilities()
        assert caps.supports_async is False
        assert caps.supports_streaming is False
        assert caps.max_concurrent_calls == 0
        assert AuthMethod.NONE in caps.supported_auth_methods
        assert caps.version == "1.0.0"

    def test_creation_with_all_fields(self, sample_capabilities):
        """Test creating ProviderCapabilities with all fields."""
        caps = sample_capabilities
        assert caps.supports_async is True
        assert caps.max_concurrent_calls == 10
        assert AuthMethod.OAUTH2 in caps.supported_auth_methods
        assert ToolCategory.FILE_SYSTEM in caps.tool_categories

    def test_to_dict(self, sample_capabilities):
        """Test ProviderCapabilities to_dict method."""
        data = sample_capabilities.to_dict()
        assert data["supports_async"] is True
        assert data["max_concurrent_calls"] == 10
        assert "oauth2" in data["supported_auth_methods"]
        assert "file_system" in data["tool_categories"]

    def test_from_dict(self):
        """Test ProviderCapabilities from_dict class method."""
        data = {
            "supports_async": True,
            "max_concurrent_calls": 5,
            "supported_auth_methods": ["api_key"],
            "tool_categories": ["database"],
        }
        caps = ProviderCapabilities.from_dict(data)
        assert caps.supports_async is True
        assert caps.max_concurrent_calls == 5
        assert AuthMethod.API_KEY in caps.supported_auth_methods
        assert ToolCategory.DATABASE in caps.tool_categories


# =============================================================================
# AuthCredentials Tests
# =============================================================================

class TestAuthCredentials:
    """Tests for AuthCredentials dataclass."""

    def test_creation_with_defaults(self):
        """Test creating AuthCredentials with defaults."""
        creds = AuthCredentials()
        assert creds.method == AuthMethod.NONE
        assert creds.api_key is None
        assert creds.is_expired() is False

    def test_is_expired_not_expired(self):
        """Test is_expired returns False for valid credentials."""
        creds = AuthCredentials(
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        assert creds.is_expired() is False

    def test_is_expired_expired(self):
        """Test is_expired returns True for expired credentials."""
        creds = AuthCredentials(
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        assert creds.is_expired() is True

    def test_to_dict_without_secrets(self, sample_credentials):
        """Test to_dict without secrets."""
        data = sample_credentials.to_dict(include_secrets=False)
        assert "api_key" not in data
        assert data["has_api_key"] is True
        assert data["method"] == "api_key"

    def test_to_dict_with_secrets(self, sample_credentials):
        """Test to_dict with secrets."""
        data = sample_credentials.to_dict(include_secrets=True)
        assert data["api_key"] == "test-api-key-12345"
        assert data["method"] == "api_key"


# =============================================================================
# LocalToolProvider Tests - Feature Step 6
# =============================================================================

class TestLocalToolProvider:
    """Tests for LocalToolProvider implementation."""

    def test_name_property(self, local_provider):
        """Test provider name is 'local'."""
        assert local_provider.name == "local"

    def test_list_tools_returns_list(self, local_provider):
        """Test list_tools returns a list of ToolDefinition objects."""
        tools = local_provider.list_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        for tool in tools:
            assert isinstance(tool, ToolDefinition)

    def test_list_tools_has_expected_tools(self, local_provider):
        """Test list_tools includes expected MCP tools."""
        tool_names = [t.name for t in local_provider.list_tools()]
        # Check for feature management tools
        assert "feature_get_by_id" in tool_names
        assert "feature_mark_passing" in tool_names
        # Check for file system tools
        assert "Read" in tool_names
        assert "Write" in tool_names
        # Check for browser tools
        assert "browser_navigate" in tool_names

    def test_get_tool_found(self, local_provider):
        """Test get_tool returns tool when found."""
        tool = local_provider.get_tool("Read")
        assert tool is not None
        assert tool.name == "Read"
        assert tool.category == ToolCategory.FILE_SYSTEM

    def test_get_tool_not_found(self, local_provider):
        """Test get_tool returns None when not found."""
        tool = local_provider.get_tool("nonexistent_tool")
        assert tool is None

    def test_has_tool_true(self, local_provider):
        """Test has_tool returns True for existing tool."""
        assert local_provider.has_tool("Read") is True

    def test_has_tool_false(self, local_provider):
        """Test has_tool returns False for nonexistent tool."""
        assert local_provider.has_tool("nonexistent") is False

    def test_execute_tool_not_found(self, local_provider):
        """Test execute_tool raises ToolNotFoundError for unknown tool."""
        with pytest.raises(ToolNotFoundError) as exc_info:
            local_provider.execute_tool("nonexistent", {})
        assert exc_info.value.tool_name == "nonexistent"
        assert exc_info.value.provider_name == "local"

    def test_execute_tool_placeholder(self, local_provider):
        """Test execute_tool returns placeholder result without executor."""
        result = local_provider.execute_tool("Read", {"file_path": "/tmp/test.txt"})
        assert result.success is True
        assert result.metadata.get("placeholder") is True

    def test_execute_tool_with_executor(self):
        """Test execute_tool uses provided executor."""
        def mock_executor(name: str, args: dict) -> dict:
            return {"executed": name, "args": args}

        provider = LocalToolProvider(tool_executor=mock_executor)
        result = provider.execute_tool("Read", {"file_path": "/test"})
        assert result.success is True
        assert result.output["executed"] == "Read"

    def test_execute_tool_executor_exception(self):
        """Test execute_tool wraps executor exceptions."""
        def failing_executor(name: str, args: dict):
            raise ValueError("Executor failed")

        provider = LocalToolProvider(tool_executor=failing_executor)
        with pytest.raises(ToolExecutionError) as exc_info:
            provider.execute_tool("Read", {})
        assert "Executor failed" in str(exc_info.value)

    def test_get_capabilities(self, local_provider):
        """Test get_capabilities returns ProviderCapabilities."""
        caps = local_provider.get_capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert caps.supports_async is False
        assert AuthMethod.NONE in caps.supported_auth_methods
        assert len(caps.tool_categories) > 0

    def test_authenticate_default(self, local_provider):
        """Test authenticate returns success by default."""
        creds = AuthCredentials(method=AuthMethod.NONE)
        result = local_provider.authenticate(creds)
        assert result.success is True
        assert result.credentials == creds

    def test_get_status_default(self, local_provider):
        """Test get_status returns AVAILABLE by default."""
        status = local_provider.get_status()
        assert status == ProviderStatus.AVAILABLE

    def test_add_tool(self, local_provider):
        """Test adding a new tool to the provider."""
        new_tool = ToolDefinition(
            name="custom_tool",
            description="A custom tool",
            category=ToolCategory.TESTING,
        )
        local_provider.add_tool(new_tool)
        assert local_provider.has_tool("custom_tool")
        assert local_provider.get_tool("custom_tool").category == ToolCategory.TESTING

    def test_remove_tool_exists(self, local_provider):
        """Test removing an existing tool."""
        assert local_provider.has_tool("Read")
        result = local_provider.remove_tool("Read")
        assert result is True
        assert local_provider.has_tool("Read") is False

    def test_remove_tool_not_exists(self, local_provider):
        """Test removing a nonexistent tool returns False."""
        result = local_provider.remove_tool("nonexistent")
        assert result is False

    def test_custom_tools_initialization(self):
        """Test initializing with custom tools."""
        custom_tools = [
            ToolDefinition(name="tool_a", description="Tool A"),
            ToolDefinition(name="tool_b", description="Tool B"),
        ]
        provider = LocalToolProvider(tools=custom_tools)
        tool_names = [t.name for t in provider.list_tools()]
        assert "tool_a" in tool_names
        assert "tool_b" in tool_names
        # Should not have default tools
        assert "Read" not in tool_names

    def test_validate_args_missing_required(self, local_provider):
        """Test validate_args catches missing required arguments."""
        # feature_get_by_id requires feature_id
        errors = local_provider.validate_args("feature_get_by_id", {})
        assert len(errors) > 0
        assert any("feature_id" in e for e in errors)

    def test_validate_args_valid(self, local_provider):
        """Test validate_args returns empty for valid args."""
        errors = local_provider.validate_args("feature_get_by_id", {"feature_id": 42})
        assert len(errors) == 0


# =============================================================================
# ToolProviderRegistry Tests - Feature Step 7
# =============================================================================

class TestToolProviderRegistry:
    """Tests for ToolProviderRegistry."""

    def test_register_provider(self, registry, local_provider):
        """Test registering a provider."""
        registry.register(local_provider)
        assert registry.has_provider("local")

    def test_register_duplicate_raises(self, registry, local_provider):
        """Test registering duplicate provider raises error."""
        registry.register(local_provider)
        with pytest.raises(ProviderAlreadyRegisteredError):
            registry.register(local_provider)

    def test_register_with_replace(self, registry, local_provider):
        """Test registering with replace=True replaces existing."""
        registry.register(local_provider)
        new_provider = LocalToolProvider(tools=[
            ToolDefinition(name="only_tool")
        ])
        # Create a subclass to change the name
        class NamedProvider(LocalToolProvider):
            @property
            def name(self):
                return "local"

        named_provider = NamedProvider(tools=[ToolDefinition(name="only_tool")])
        registry.register(named_provider, replace=True)
        tools = registry.get_provider("local").list_tools()
        assert len(tools) == 1

    def test_unregister_exists(self, registry, local_provider):
        """Test unregistering an existing provider."""
        registry.register(local_provider)
        result = registry.unregister("local")
        assert result is True
        assert registry.has_provider("local") is False

    def test_unregister_not_exists(self, registry):
        """Test unregistering nonexistent provider returns False."""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_get_provider_found(self, registry, local_provider):
        """Test get_provider returns the provider."""
        registry.register(local_provider)
        provider = registry.get_provider("local")
        assert provider is local_provider

    def test_get_provider_not_found(self, registry):
        """Test get_provider raises ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError):
            registry.get_provider("nonexistent")

    def test_has_provider(self, registry, local_provider):
        """Test has_provider method."""
        assert registry.has_provider("local") is False
        registry.register(local_provider)
        assert registry.has_provider("local") is True

    def test_list_providers(self, registry):
        """Test list_providers method."""
        assert registry.list_providers() == []

        class Provider1(LocalToolProvider):
            @property
            def name(self):
                return "provider1"

        class Provider2(LocalToolProvider):
            @property
            def name(self):
                return "provider2"

        registry.register(Provider1())
        registry.register(Provider2())
        providers = registry.list_providers()
        assert "provider1" in providers
        assert "provider2" in providers

    def test_list_all_tools(self, registry, local_provider):
        """Test list_all_tools returns tools from all providers."""
        registry.register(local_provider)
        all_tools = registry.list_all_tools()
        assert "local" in all_tools
        assert len(all_tools["local"]) > 0

    def test_get_all_capabilities(self, registry, local_provider):
        """Test get_all_capabilities returns capabilities from all providers."""
        registry.register(local_provider)
        all_caps = registry.get_all_capabilities()
        assert "local" in all_caps
        assert isinstance(all_caps["local"], ProviderCapabilities)

    def test_execute_tool(self, registry, local_provider):
        """Test execute_tool routes to correct provider."""
        registry.register(local_provider)
        result = registry.execute_tool("local", "Read", {"file_path": "/test"})
        assert result.success is True

    def test_execute_tool_provider_not_found(self, registry):
        """Test execute_tool raises ProviderNotFoundError."""
        with pytest.raises(ProviderNotFoundError):
            registry.execute_tool("nonexistent", "tool", {})

    def test_find_tool(self, registry, local_provider):
        """Test find_tool finds tool across providers."""
        registry.register(local_provider)
        result = registry.find_tool("Read")
        assert result is not None
        provider_name, tool = result
        assert provider_name == "local"
        assert tool.name == "Read"

    def test_find_tool_not_found(self, registry, local_provider):
        """Test find_tool returns None for unknown tool."""
        registry.register(local_provider)
        result = registry.find_tool("nonexistent")
        assert result is None

    def test_execute_tool_any(self, registry, local_provider):
        """Test execute_tool_any finds and executes tool."""
        registry.register(local_provider)
        result = registry.execute_tool_any("Read", {"file_path": "/test"})
        assert result.success is True

    def test_execute_tool_any_not_found(self, registry, local_provider):
        """Test execute_tool_any raises ToolNotFoundError."""
        registry.register(local_provider)
        with pytest.raises(ToolNotFoundError):
            registry.execute_tool_any("nonexistent", {})

    def test_get_provider_status(self, registry, local_provider):
        """Test get_provider_status returns status map."""
        registry.register(local_provider)
        statuses = registry.get_provider_status()
        assert "local" in statuses
        assert statuses["local"] == ProviderStatus.AVAILABLE

    def test_clear(self, registry, local_provider):
        """Test clear removes all providers."""
        registry.register(local_provider)
        assert len(registry.list_providers()) > 0
        registry.clear()
        assert len(registry.list_providers()) == 0


# =============================================================================
# Module-level Function Tests
# =============================================================================

class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_tool_registry_creates_singleton(self):
        """Test get_tool_registry creates registry with LocalToolProvider."""
        registry = get_tool_registry()
        assert isinstance(registry, ToolProviderRegistry)
        assert registry.has_provider("local")

    def test_get_tool_registry_returns_same_instance(self):
        """Test get_tool_registry returns same instance."""
        registry1 = get_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is registry2

    def test_reset_tool_registry(self):
        """Test reset_tool_registry clears the global registry."""
        registry1 = get_tool_registry()
        reset_tool_registry()
        registry2 = get_tool_registry()
        assert registry1 is not registry2

    def test_register_provider_convenience(self):
        """Test register_provider convenience function."""
        class CustomProvider(LocalToolProvider):
            @property
            def name(self):
                return "custom"

        register_provider(CustomProvider())
        registry = get_tool_registry()
        assert registry.has_provider("custom")

    def test_execute_tool_convenience_any(self):
        """Test execute_tool convenience function without provider."""
        result = execute_tool("Read", {"file_path": "/test"})
        assert result.success is True

    def test_execute_tool_convenience_specific(self):
        """Test execute_tool convenience function with provider."""
        result = execute_tool("Read", {"file_path": "/test"}, provider_name="local")
        assert result.success is True


# =============================================================================
# Feature Step Verification Tests
# =============================================================================

class TestFeatureSteps:
    """Tests verifying all feature steps are implemented."""

    def test_step_1_abstract_base_class(self):
        """Step 1: Define ToolProvider abstract base class."""
        # Verify ToolProvider is abstract
        with pytest.raises(TypeError):
            ToolProvider()

        # Verify required methods are abstract
        assert hasattr(ToolProvider, 'name')
        assert hasattr(ToolProvider, 'list_tools')
        assert hasattr(ToolProvider, 'execute_tool')
        assert hasattr(ToolProvider, 'get_capabilities')

    def test_step_2_list_tools_method(self, local_provider):
        """Step 2: Define list_tools() -> list[ToolDefinition] method."""
        tools = local_provider.list_tools()
        assert isinstance(tools, list)
        for tool in tools:
            assert isinstance(tool, ToolDefinition)
            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)

    def test_step_3_execute_tool_method(self, local_provider):
        """Step 3: Define execute_tool(name, args) -> ToolResult method."""
        result = local_provider.execute_tool("Read", {"file_path": "/test"})
        assert isinstance(result, ToolResult)
        assert isinstance(result.success, bool)
        assert isinstance(result.execution_time_ms, int)

    def test_step_4_get_capabilities_method(self, local_provider):
        """Step 4: Define get_capabilities() -> ProviderCapabilities method."""
        caps = local_provider.get_capabilities()
        assert isinstance(caps, ProviderCapabilities)
        assert isinstance(caps.supports_async, bool)
        assert isinstance(caps.supported_auth_methods, list)
        assert isinstance(caps.tool_categories, list)

    def test_step_5_authenticate_method(self, local_provider):
        """Step 5: Define authenticate(credentials) method stub for future OAuth."""
        creds = AuthCredentials(method=AuthMethod.API_KEY, api_key="test")
        result = local_provider.authenticate(creds)
        assert isinstance(result, AuthResult)
        assert result.success is True  # Default implementation always succeeds

    def test_step_6_local_tool_provider(self, local_provider):
        """Step 6: Create LocalToolProvider implementing interface for MCP tools."""
        assert local_provider.name == "local"
        assert isinstance(local_provider, ToolProvider)
        # Check MCP tool categories are present
        caps = local_provider.get_capabilities()
        assert ToolCategory.FILE_SYSTEM in caps.tool_categories
        assert ToolCategory.FEATURE_MANAGEMENT in caps.tool_categories

    def test_step_7_tool_provider_registry(self, registry, local_provider):
        """Step 7: Create ToolProviderRegistry for managing multiple providers."""
        # Register multiple providers
        registry.register(local_provider)

        class SecondProvider(LocalToolProvider):
            @property
            def name(self):
                return "second"

        registry.register(SecondProvider())

        # Verify multiple providers
        assert len(registry.list_providers()) == 2
        assert registry.has_provider("local")
        assert registry.has_provider("second")

        # Verify tool execution routing
        result = registry.execute_tool("local", "Read", {"file_path": "/test"})
        assert result.success is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the ToolProvider system."""

    def test_full_workflow(self):
        """Test complete workflow from registration to execution."""
        # Create registry
        registry = ToolProviderRegistry()

        # Create and register provider
        provider = LocalToolProvider()
        registry.register(provider)

        # List available tools
        all_tools = registry.list_all_tools()
        assert "local" in all_tools
        assert len(all_tools["local"]) > 0

        # Check capabilities
        caps = registry.get_all_capabilities()
        assert "local" in caps

        # Find a specific tool
        result = registry.find_tool("Read")
        assert result is not None

        # Execute the tool
        exec_result = registry.execute_tool("local", "Read", {"file_path": "/test"})
        assert exec_result.success is True

    def test_custom_provider_implementation(self):
        """Test implementing a custom provider."""
        # Create a custom provider
        class CalculatorProvider(ToolProvider):
            @property
            def name(self):
                return "calculator"

            def list_tools(self):
                return [
                    ToolDefinition(
                        name="add",
                        description="Add two numbers",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "a": {"type": "number"},
                                "b": {"type": "number"},
                            },
                            "required": ["a", "b"],
                        },
                    ),
                    ToolDefinition(
                        name="multiply",
                        description="Multiply two numbers",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "a": {"type": "number"},
                                "b": {"type": "number"},
                            },
                            "required": ["a", "b"],
                        },
                    ),
                ]

            def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
                if name == "add":
                    return ToolResult.success_result(args["a"] + args["b"])
                elif name == "multiply":
                    return ToolResult.success_result(args["a"] * args["b"])
                else:
                    raise ToolNotFoundError(name, self.name)

            def get_capabilities(self) -> ProviderCapabilities:
                return ProviderCapabilities(
                    version="1.0.0",
                    tool_categories=[ToolCategory.GENERAL],
                )

        # Use the custom provider
        registry = ToolProviderRegistry()
        calc = CalculatorProvider()
        registry.register(calc)

        # Test execution
        result = registry.execute_tool("calculator", "add", {"a": 5, "b": 3})
        assert result.success is True
        assert result.output == 8

        result = registry.execute_tool("calculator", "multiply", {"a": 4, "b": 7})
        assert result.success is True
        assert result.output == 28

    def test_provider_error_handling(self):
        """Test error handling in provider execution."""
        class FailingProvider(ToolProvider):
            @property
            def name(self):
                return "failing"

            def list_tools(self):
                return [ToolDefinition(name="fail")]

            def execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
                raise ToolExecutionError(name, self.name, "Intentional failure")

            def get_capabilities(self) -> ProviderCapabilities:
                return ProviderCapabilities()

        registry = ToolProviderRegistry()
        registry.register(FailingProvider())

        with pytest.raises(ToolExecutionError) as exc_info:
            registry.execute_tool("failing", "fail", {})
        assert "Intentional failure" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
