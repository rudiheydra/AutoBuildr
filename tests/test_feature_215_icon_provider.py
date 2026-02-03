"""
Tests for Feature #215: Icon provider interface defined

Tests the IconProvider abstract interface and its implementations.

Feature Requirements:
1. IconProvider abstract class/interface created
2. Interface method: generate_icon(agent_name, role, tone) -> IconResult
3. IconResult includes: icon_url, icon_data, format (svg/png)
4. Provider registration mechanism defined
5. Configuration selects active provider
"""

import pytest
from typing import Any
from unittest.mock import MagicMock, patch

# Import everything from api package to test exports
from api import (
    # Exceptions
    IconProviderError,
    IconGenerationError,
    IconProviderNotFoundError,
    IconProviderAlreadyRegisteredError,
    InvalidIconFormatError,
    # Enums
    IconFormat,
    IconTone,
    IconProviderStatus,
    # Data classes
    IconResult,
    IconProviderCapabilities,
    IconGenerationRequest,
    # Abstract base class
    IconProvider,
    # Default implementation
    DefaultIconProvider,
    # Registry
    IconProviderRegistry,
    # Convenience functions
    get_icon_registry,
    reset_icon_registry,
    register_icon_provider,
    generate_icon,
    get_default_icon_provider,
    configure_icon_provider_from_settings,
    # Configuration functions
    get_active_provider_from_config,
    set_active_provider_in_config,
    # Constants
    ICON_PROVIDER_CONFIG_KEY,
    DEFAULT_ICON_PROVIDER_NAME,
)


# =============================================================================
# TestStep1IconProviderAbstractClass - Step 1 Verification
# =============================================================================

class TestStep1IconProviderAbstractClass:
    """Test that IconProvider abstract class/interface is created."""

    def test_icon_provider_is_abstract(self):
        """IconProvider should be an abstract base class."""
        from abc import ABC
        assert issubclass(IconProvider, ABC)

    def test_icon_provider_cannot_be_instantiated(self):
        """IconProvider should not be directly instantiable."""
        with pytest.raises(TypeError):
            IconProvider()

    def test_icon_provider_has_name_property(self):
        """IconProvider should have an abstract name property."""
        # Check that name is defined as abstract
        assert hasattr(IconProvider, 'name')

    def test_icon_provider_has_generate_icon_method(self):
        """IconProvider should have an abstract generate_icon method."""
        assert hasattr(IconProvider, 'generate_icon')
        assert callable(getattr(IconProvider, 'generate_icon'))

    def test_icon_provider_has_get_capabilities_method(self):
        """IconProvider should have an abstract get_capabilities method."""
        assert hasattr(IconProvider, 'get_capabilities')
        assert callable(getattr(IconProvider, 'get_capabilities'))

    def test_icon_provider_has_get_status_method(self):
        """IconProvider should have a get_status method."""
        assert hasattr(IconProvider, 'get_status')
        assert callable(getattr(IconProvider, 'get_status'))

    def test_icon_provider_has_supports_format_method(self):
        """IconProvider should have a supports_format method."""
        assert hasattr(IconProvider, 'supports_format')
        assert callable(getattr(IconProvider, 'supports_format'))

    def test_icon_provider_has_provider_type_class_variable(self):
        """IconProvider should have a provider_type class variable."""
        assert hasattr(IconProvider, 'provider_type')
        assert IconProvider.provider_type == "base"


# =============================================================================
# TestStep2GenerateIconMethod - Step 2 Verification
# =============================================================================

class TestStep2GenerateIconMethod:
    """Test that generate_icon(agent_name, role, tone) -> IconResult method exists."""

    def test_default_provider_generate_icon_signature(self):
        """DefaultIconProvider.generate_icon should accept agent_name, role, tone."""
        provider = DefaultIconProvider()
        # This should work without errors
        result = provider.generate_icon(
            agent_name="test-agent",
            role="coder",
            tone="professional"
        )
        assert isinstance(result, IconResult)

    def test_generate_icon_returns_icon_result(self):
        """generate_icon should return an IconResult."""
        provider = DefaultIconProvider()
        result = provider.generate_icon("agent", "coder", "default")
        assert isinstance(result, IconResult)

    def test_generate_icon_with_different_roles(self):
        """generate_icon should work with different roles."""
        provider = DefaultIconProvider()

        roles = ["coder", "tester", "reviewer", "auditor", "documenter"]
        for role in roles:
            result = provider.generate_icon("test-agent", role, "default")
            assert result.success
            assert result.icon_data is not None

    def test_generate_icon_with_different_tones(self):
        """generate_icon should accept different tone values."""
        provider = DefaultIconProvider()

        tones = ["professional", "playful", "default", "minimalist"]
        for tone in tones:
            result = provider.generate_icon("test-agent", "coder", tone)
            assert result.success

    def test_generate_icon_from_request_method(self):
        """generate_icon_from_request should work with IconGenerationRequest."""
        provider = DefaultIconProvider()

        request = IconGenerationRequest(
            agent_name="test-agent",
            role="coder",
            tone=IconTone.PROFESSIONAL,
        )

        result = provider.generate_icon_from_request(request)
        assert isinstance(result, IconResult)
        assert result.success


# =============================================================================
# TestStep3IconResultDataclass - Step 3 Verification
# =============================================================================

class TestStep3IconResultDataclass:
    """Test that IconResult includes: icon_url, icon_data, format (svg/png)."""

    def test_icon_result_has_icon_url(self):
        """IconResult should have an icon_url field."""
        result = IconResult(
            success=True,
            icon_url="https://example.com/icon.png",
            format=IconFormat.PNG
        )
        assert result.icon_url == "https://example.com/icon.png"

    def test_icon_result_has_icon_data(self):
        """IconResult should have an icon_data field."""
        result = IconResult(
            success=True,
            icon_data="<svg>...</svg>",
            format=IconFormat.SVG
        )
        assert result.icon_data == "<svg>...</svg>"

    def test_icon_result_has_format_field(self):
        """IconResult should have a format field."""
        result = IconResult(
            success=True,
            icon_data="code",
            format=IconFormat.ICON_ID
        )
        assert result.format == IconFormat.ICON_ID

    def test_icon_format_includes_svg(self):
        """IconFormat should include SVG."""
        assert IconFormat.SVG.value == "svg"

    def test_icon_format_includes_png(self):
        """IconFormat should include PNG."""
        assert IconFormat.PNG.value == "png"

    def test_icon_format_includes_additional_formats(self):
        """IconFormat should include other useful formats."""
        assert IconFormat.JPEG.value == "jpeg"
        assert IconFormat.WEBP.value == "webp"
        assert IconFormat.EMOJI.value == "emoji"
        assert IconFormat.ICON_ID.value == "icon_id"

    def test_icon_result_success_result_factory(self):
        """IconResult.success_result should create successful results."""
        result = IconResult.success_result(
            icon_data="code",
            format=IconFormat.ICON_ID,
            provider_name="test"
        )
        assert result.success
        assert result.icon_data == "code"
        assert result.provider_name == "test"

    def test_icon_result_error_result_factory(self):
        """IconResult.error_result should create error results."""
        result = IconResult.error_result(
            error="Generation failed",
            provider_name="test"
        )
        assert not result.success
        assert result.error == "Generation failed"

    def test_icon_result_to_dict(self):
        """IconResult.to_dict should serialize properly."""
        result = IconResult(
            success=True,
            icon_data="code",
            format=IconFormat.ICON_ID,
            provider_name="default"
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["icon_data"] == "code"
        assert data["format"] == "icon_id"

    def test_icon_result_from_dict(self):
        """IconResult.from_dict should deserialize properly."""
        data = {
            "success": True,
            "icon_data": "code",
            "format": "icon_id",
            "provider_name": "default"
        }
        result = IconResult.from_dict(data)
        assert result.success
        assert result.icon_data == "code"
        assert result.format == IconFormat.ICON_ID


# =============================================================================
# TestStep4ProviderRegistrationMechanism - Step 4 Verification
# =============================================================================

class TestStep4ProviderRegistrationMechanism:
    """Test that provider registration mechanism is defined."""

    def test_icon_provider_registry_exists(self):
        """IconProviderRegistry should exist."""
        assert IconProviderRegistry is not None

    def test_registry_can_register_provider(self):
        """Registry should allow registering providers."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider)
        assert registry.has_provider("default")

    def test_registry_can_unregister_provider(self):
        """Registry should allow unregistering providers."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider)
        result = registry.unregister("default")
        assert result is True
        assert not registry.has_provider("default")

    def test_registry_prevents_duplicate_registration(self):
        """Registry should prevent duplicate provider names."""
        registry = IconProviderRegistry()
        provider1 = DefaultIconProvider()
        registry.register(provider1)

        provider2 = DefaultIconProvider()
        with pytest.raises(IconProviderAlreadyRegisteredError):
            registry.register(provider2)

    def test_registry_allows_replace(self):
        """Registry should allow replacing providers with replace=True."""
        registry = IconProviderRegistry()
        provider1 = DefaultIconProvider()
        registry.register(provider1)

        provider2 = DefaultIconProvider()
        registry.register(provider2, replace=True)  # Should not raise

    def test_registry_get_provider(self):
        """Registry should retrieve providers by name."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider)

        retrieved = registry.get_provider("default")
        assert retrieved is provider

    def test_registry_get_provider_not_found(self):
        """Registry should raise error for unknown provider."""
        registry = IconProviderRegistry()
        with pytest.raises(IconProviderNotFoundError):
            registry.get_provider("nonexistent")

    def test_registry_list_providers(self):
        """Registry should list all registered providers."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider)

        providers = registry.list_providers()
        assert "default" in providers

    def test_registry_clear(self):
        """Registry should clear all providers."""
        registry = IconProviderRegistry()
        registry.register(DefaultIconProvider())
        registry.clear()
        assert len(registry.list_providers()) == 0

    def test_global_registry_convenience_function(self):
        """get_icon_registry should return global registry."""
        reset_icon_registry()
        registry = get_icon_registry()
        assert isinstance(registry, IconProviderRegistry)
        # Default provider should be registered
        assert registry.has_provider("default")

    def test_register_icon_provider_convenience_function(self):
        """register_icon_provider should register to global registry."""
        reset_icon_registry()

        class CustomProvider(DefaultIconProvider):
            @property
            def name(self) -> str:
                return "custom"

        provider = CustomProvider()
        register_icon_provider(provider)

        registry = get_icon_registry()
        assert registry.has_provider("custom")


# =============================================================================
# TestStep5ConfigurationSelectsActiveProvider - Step 5 Verification
# =============================================================================

class TestStep5ConfigurationSelectsActiveProvider:
    """Test that configuration selects active provider."""

    def test_registry_has_active_provider(self):
        """Registry should track active provider."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider, set_active=True)

        assert registry.active_provider_name == "default"

    def test_registry_set_active_provider(self):
        """Registry should allow setting active provider."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider)

        registry.set_active_provider("default")
        assert registry.active_provider_name == "default"

    def test_registry_set_active_provider_not_found(self):
        """Setting unknown provider as active should raise error."""
        registry = IconProviderRegistry()
        with pytest.raises(IconProviderNotFoundError):
            registry.set_active_provider("nonexistent")

    def test_registry_generate_icon_uses_active_provider(self):
        """Registry.generate_icon should use active provider."""
        reset_icon_registry()
        registry = get_icon_registry()

        result = registry.generate_icon("test-agent", "coder", "default")
        assert result.success
        assert result.provider_name == "default"

    def test_get_active_provider_from_config(self):
        """get_active_provider_from_config should read from config dict."""
        config = {"icon_provider.active": "custom"}
        result = get_active_provider_from_config(config)
        assert result == "custom"

    def test_get_active_provider_from_config_default(self):
        """get_active_provider_from_config should return default when not set."""
        config = {}
        result = get_active_provider_from_config(config)
        assert result == DEFAULT_ICON_PROVIDER_NAME

    def test_set_active_provider_in_config(self):
        """set_active_provider_in_config should update config dict."""
        config: dict[str, Any] = {}
        result = set_active_provider_in_config(config, "custom")
        assert result[ICON_PROVIDER_CONFIG_KEY] == "custom"

    def test_configure_icon_provider_from_settings(self):
        """configure_icon_provider_from_settings should set active provider."""
        reset_icon_registry()
        settings = {"icon_provider.active": "default"}
        configure_icon_provider_from_settings(settings)

        registry = get_icon_registry()
        assert registry.active_provider_name == "default"


# =============================================================================
# TestIconResultAdditionalFunctionality
# =============================================================================

class TestIconResultAdditionalFunctionality:
    """Test additional IconResult functionality."""

    def test_icon_result_is_binary_property(self):
        """is_binary should return True for binary formats."""
        result = IconResult(
            success=True,
            icon_data="base64data",
            format=IconFormat.PNG
        )
        assert result.is_binary

    def test_icon_result_is_text_property(self):
        """is_text should return True for text formats."""
        result = IconResult(
            success=True,
            icon_data="<svg>...</svg>",
            format=IconFormat.SVG
        )
        assert result.is_text

    def test_icon_result_cached_flag(self):
        """IconResult should track cached status."""
        result = IconResult(
            success=True,
            icon_data="code",
            format=IconFormat.ICON_ID,
            cached=True
        )
        assert result.cached is True

    def test_icon_result_validation_requires_data_or_url(self):
        """Successful IconResult must have icon_data or icon_url."""
        with pytest.raises(ValueError):
            IconResult(success=True, format=IconFormat.ICON_ID)


# =============================================================================
# TestDefaultIconProvider
# =============================================================================

class TestDefaultIconProvider:
    """Test DefaultIconProvider implementation."""

    def test_default_provider_name(self):
        """DefaultIconProvider should have name 'default'."""
        provider = DefaultIconProvider()
        assert provider.name == "default"

    def test_default_provider_maps_coder_to_code_icon(self):
        """DefaultIconProvider should map coder role to code icon."""
        provider = DefaultIconProvider()
        result = provider.generate_icon("test", "coder", "default")
        assert result.icon_data == "code"

    def test_default_provider_maps_tester_to_test_tube_icon(self):
        """DefaultIconProvider should map tester role to test-tube icon."""
        provider = DefaultIconProvider()
        result = provider.generate_icon("test", "tester", "default")
        assert result.icon_data == "test-tube"

    def test_default_provider_maps_auditor_to_shield_icon(self):
        """DefaultIconProvider should map auditor role to shield icon."""
        provider = DefaultIconProvider()
        result = provider.generate_icon("test", "auditor", "default")
        assert result.icon_data == "shield"

    def test_default_provider_uses_custom_icons(self):
        """DefaultIconProvider should use custom icon mappings."""
        provider = DefaultIconProvider(custom_icons={"special": "star"})
        result = provider.generate_icon("test", "special", "default")
        assert result.icon_data == "star"

    def test_default_provider_caches_results(self):
        """DefaultIconProvider should cache results."""
        provider = DefaultIconProvider()

        # First call
        result1 = provider.generate_icon("test", "coder", "default")
        assert not result1.cached

        # Second call (should be cached)
        result2 = provider.generate_icon("test", "coder", "default")
        assert result2.cached

    def test_default_provider_clear_cache(self):
        """DefaultIconProvider.clear_cache should clear the cache."""
        provider = DefaultIconProvider()

        provider.generate_icon("test", "coder", "default")
        provider.clear_cache()

        result = provider.generate_icon("test", "coder", "default")
        assert not result.cached

    def test_default_provider_capabilities(self):
        """DefaultIconProvider should report capabilities."""
        provider = DefaultIconProvider()
        caps = provider.get_capabilities()

        assert IconFormat.ICON_ID in caps.supported_formats
        assert not caps.requires_api_key
        assert caps.generation_speed == "fast"

    def test_default_provider_add_custom_icon(self):
        """DefaultIconProvider.add_custom_icon should add mapping."""
        provider = DefaultIconProvider()
        provider.add_custom_icon("my_role", "my_icon")

        result = provider.generate_icon("test", "my_role", "default")
        assert result.icon_data == "my_icon"


# =============================================================================
# TestIconProviderCapabilities
# =============================================================================

class TestIconProviderCapabilities:
    """Test IconProviderCapabilities dataclass."""

    def test_capabilities_to_dict(self):
        """IconProviderCapabilities.to_dict should serialize."""
        caps = IconProviderCapabilities(
            supported_formats=[IconFormat.SVG, IconFormat.PNG],
            requires_api_key=True
        )
        data = caps.to_dict()
        assert "svg" in data["supported_formats"]
        assert "png" in data["supported_formats"]
        assert data["requires_api_key"] is True

    def test_capabilities_from_dict(self):
        """IconProviderCapabilities.from_dict should deserialize."""
        data = {
            "supported_formats": ["svg", "png"],
            "requires_api_key": True,
            "generation_speed": "slow"
        }
        caps = IconProviderCapabilities.from_dict(data)
        assert IconFormat.SVG in caps.supported_formats
        assert caps.requires_api_key is True
        assert caps.generation_speed == "slow"


# =============================================================================
# TestIconGenerationRequest
# =============================================================================

class TestIconGenerationRequest:
    """Test IconGenerationRequest dataclass."""

    def test_request_creation(self):
        """IconGenerationRequest should be created with required fields."""
        request = IconGenerationRequest(
            agent_name="test-agent",
            role="coder"
        )
        assert request.agent_name == "test-agent"
        assert request.role == "coder"
        assert request.tone == IconTone.DEFAULT

    def test_request_to_dict(self):
        """IconGenerationRequest.to_dict should serialize."""
        request = IconGenerationRequest(
            agent_name="test",
            role="coder",
            tone=IconTone.PROFESSIONAL
        )
        data = request.to_dict()
        assert data["agent_name"] == "test"
        assert data["tone"] == "professional"

    def test_request_from_dict(self):
        """IconGenerationRequest.from_dict should deserialize."""
        data = {
            "agent_name": "test",
            "role": "coder",
            "tone": "playful"
        }
        request = IconGenerationRequest.from_dict(data)
        assert request.agent_name == "test"
        assert request.tone == IconTone.PLAYFUL


# =============================================================================
# TestExceptions
# =============================================================================

class TestExceptions:
    """Test exception classes."""

    def test_icon_provider_error(self):
        """IconProviderError should be base exception."""
        error = IconProviderError("test error")
        assert str(error) == "test error"

    def test_icon_generation_error(self):
        """IconGenerationError should include context."""
        error = IconGenerationError(
            provider_name="test",
            reason="API failed",
            agent_name="my-agent"
        )
        assert "test" in str(error)
        assert "API failed" in str(error)
        assert "my-agent" in str(error)

    def test_provider_not_found_error(self):
        """IconProviderNotFoundError should list available providers."""
        error = IconProviderNotFoundError(
            provider_name="unknown",
            available_providers=["default", "custom"]
        )
        assert "unknown" in str(error)
        assert "default" in str(error) or "custom" in str(error)

    def test_provider_already_registered_error(self):
        """IconProviderAlreadyRegisteredError should include name."""
        error = IconProviderAlreadyRegisteredError("duplicate")
        assert "duplicate" in str(error)

    def test_invalid_icon_format_error(self):
        """InvalidIconFormatError should include format value."""
        error = InvalidIconFormatError(
            format_value="invalid",
            supported_formats=["svg", "png"]
        )
        assert "invalid" in str(error)


# =============================================================================
# TestConvenienceFunctions
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_generate_icon_function(self):
        """generate_icon convenience function should work."""
        reset_icon_registry()
        result = generate_icon("test", "coder", "default")
        assert isinstance(result, IconResult)
        assert result.success

    def test_get_default_icon_provider(self):
        """get_default_icon_provider should return new instance."""
        provider = get_default_icon_provider()
        assert isinstance(provider, DefaultIconProvider)

    def test_reset_icon_registry(self):
        """reset_icon_registry should clear global registry."""
        get_icon_registry()  # Ensure exists
        reset_icon_registry()
        # Next call should create new registry
        registry = get_icon_registry()
        assert registry.has_provider("default")  # Re-initialized


# =============================================================================
# TestApiPackageExports
# =============================================================================

class TestApiPackageExports:
    """Test that all expected exports are available from api package."""

    def test_exceptions_exported(self):
        """Exception classes should be exported."""
        assert IconProviderError is not None
        assert IconGenerationError is not None
        assert IconProviderNotFoundError is not None
        assert IconProviderAlreadyRegisteredError is not None
        assert InvalidIconFormatError is not None

    def test_enums_exported(self):
        """Enum classes should be exported."""
        assert IconFormat is not None
        assert IconTone is not None
        assert IconProviderStatus is not None

    def test_dataclasses_exported(self):
        """Dataclasses should be exported."""
        assert IconResult is not None
        assert IconProviderCapabilities is not None
        assert IconGenerationRequest is not None

    def test_classes_exported(self):
        """Main classes should be exported."""
        assert IconProvider is not None
        assert DefaultIconProvider is not None
        assert IconProviderRegistry is not None

    def test_functions_exported(self):
        """Convenience functions should be exported."""
        assert get_icon_registry is not None
        assert reset_icon_registry is not None
        assert register_icon_provider is not None
        assert generate_icon is not None
        assert get_default_icon_provider is not None
        assert configure_icon_provider_from_settings is not None
        assert get_active_provider_from_config is not None
        assert set_active_provider_in_config is not None

    def test_constants_exported(self):
        """Constants should be exported."""
        assert ICON_PROVIDER_CONFIG_KEY is not None
        assert DEFAULT_ICON_PROVIDER_NAME is not None


# =============================================================================
# TestFeature215VerificationSteps - Feature Acceptance Tests
# =============================================================================

class TestFeature215VerificationSteps:
    """Comprehensive tests verifying all feature requirements."""

    def test_step1_icon_provider_abstract_class_created(self):
        """
        Step 1: IconProvider abstract class/interface created.

        Verifies that:
        - IconProvider is an abstract base class
        - Cannot be instantiated directly
        - Has required abstract methods
        """
        from abc import ABC

        # IconProvider is abstract
        assert issubclass(IconProvider, ABC)

        # Cannot instantiate
        with pytest.raises(TypeError):
            IconProvider()

        # Has required methods
        assert hasattr(IconProvider, 'name')
        assert hasattr(IconProvider, 'generate_icon')
        assert hasattr(IconProvider, 'get_capabilities')

    def test_step2_generate_icon_method_signature(self):
        """
        Step 2: Interface method: generate_icon(agent_name, role, tone) -> IconResult.

        Verifies that:
        - generate_icon accepts agent_name, role, tone parameters
        - Returns IconResult
        - Works with DefaultIconProvider implementation
        """
        provider = DefaultIconProvider()

        # Method exists and accepts required parameters
        result = provider.generate_icon(
            agent_name="feature-auth-login-impl",
            role="coder",
            tone="professional"
        )

        # Returns IconResult
        assert isinstance(result, IconResult)
        assert result.success

    def test_step3_icon_result_includes_required_fields(self):
        """
        Step 3: IconResult includes: icon_url, icon_data, format (svg/png).

        Verifies that:
        - IconResult has icon_url field
        - IconResult has icon_data field
        - IconResult has format field
        - Format supports svg and png
        """
        # Test all required fields
        result = IconResult(
            success=True,
            icon_url="https://example.com/icon.png",
            icon_data="<svg>test</svg>",
            format=IconFormat.SVG
        )

        assert hasattr(result, 'icon_url')
        assert hasattr(result, 'icon_data')
        assert hasattr(result, 'format')

        # Format supports svg and png
        assert IconFormat.SVG.value == "svg"
        assert IconFormat.PNG.value == "png"

    def test_step4_provider_registration_mechanism_defined(self):
        """
        Step 4: Provider registration mechanism defined.

        Verifies that:
        - IconProviderRegistry exists
        - Can register providers
        - Can unregister providers
        - Can list providers
        - Can get provider by name
        """
        registry = IconProviderRegistry()

        # Register provider
        provider = DefaultIconProvider()
        registry.register(provider)

        # Provider is registered
        assert registry.has_provider("default")
        assert "default" in registry.list_providers()

        # Get provider
        retrieved = registry.get_provider("default")
        assert retrieved is provider

        # Unregister
        result = registry.unregister("default")
        assert result is True
        assert not registry.has_provider("default")

    def test_step5_configuration_selects_active_provider(self):
        """
        Step 5: Configuration selects active provider.

        Verifies that:
        - Registry tracks active provider
        - Can set active provider
        - generate_icon uses active provider
        - Configuration functions work
        """
        reset_icon_registry()
        registry = get_icon_registry()

        # Active provider is tracked
        assert registry.active_provider_name is not None

        # Set active provider
        registry.set_active_provider("default")
        assert registry.active_provider_name == "default"

        # generate_icon uses active provider
        result = registry.generate_icon("test", "coder", "default")
        assert result.provider_name == "default"

        # Configuration functions work
        config: dict[str, Any] = {}
        set_active_provider_in_config(config, "custom")
        assert get_active_provider_from_config(config) == "custom"


# =============================================================================
# TestEdgeCases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_agent_name(self):
        """Should handle empty agent name."""
        provider = DefaultIconProvider()
        result = provider.generate_icon("", "coder", "default")
        assert result.success

    def test_unknown_role(self):
        """Should handle unknown role with default icon."""
        provider = DefaultIconProvider()
        result = provider.generate_icon("test", "unknown_role", "default")
        assert result.success
        # Should return some icon (fallback)
        assert result.icon_data is not None

    def test_case_insensitive_role(self):
        """Should handle role case-insensitively."""
        provider = DefaultIconProvider()
        result1 = provider.generate_icon("test", "CODER", "default")
        result2 = provider.generate_icon("test", "coder", "default")
        assert result1.icon_data == result2.icon_data

    def test_generate_icon_with_explicit_provider(self):
        """Registry.generate_icon should accept explicit provider_name."""
        reset_icon_registry()
        registry = get_icon_registry()

        result = registry.generate_icon(
            "test", "coder", "default",
            provider_name="default"
        )
        assert result.success

    def test_registry_auto_sets_first_provider_active(self):
        """Registry should auto-set first registered provider as active."""
        registry = IconProviderRegistry()
        provider = DefaultIconProvider()
        registry.register(provider)

        assert registry.active_provider_name == "default"

    def test_unregister_active_provider(self):
        """Unregistering active provider should update active to next."""
        registry = IconProviderRegistry()

        class Provider1(DefaultIconProvider):
            @property
            def name(self) -> str:
                return "provider1"

        class Provider2(DefaultIconProvider):
            @property
            def name(self) -> str:
                return "provider2"

        registry.register(Provider1())
        registry.register(Provider2())
        registry.set_active_provider("provider1")

        registry.unregister("provider1")

        # Active should switch to remaining provider
        assert registry.active_provider_name == "provider2"
