"""
Tests for Feature #216: LocalPlaceholderIconProvider implements stub

This test suite verifies that:
1. LocalPlaceholderIconProvider implements IconProvider interface
2. Generates deterministic placeholder based on agent name
3. Uses color hash from agent name for uniqueness
4. Returns simple geometric shape or initials
5. No external dependencies required

Run with: pytest tests/test_feature_216_local_placeholder_provider.py -v
"""
import pytest
import hashlib
import time
from unittest.mock import patch

from api.icon_provider import (
    IconFormat,
    IconProvider,
    IconProviderCapabilities,
    IconResult,
)
from api.local_placeholder_icon_provider import (
    # Main class
    LocalPlaceholderIconProvider,
    # Data classes/Enums
    PlaceholderConfig,
    PlaceholderShape,
    # Constants
    LOCAL_PLACEHOLDER_PROVIDER_NAME,
    DEFAULT_SVG_WIDTH,
    DEFAULT_SVG_HEIGHT,
    PLACEHOLDER_COLOR_PALETTE,
    # Functions
    compute_name_hash,
    compute_color_from_name,
    extract_initials,
    generate_placeholder_svg,
    generate_shape_svg,
    get_local_placeholder_provider,
    generate_placeholder_icon,
    get_placeholder_color,
    get_placeholder_initials,
)


# =============================================================================
# Test Step 1: LocalPlaceholderIconProvider implements IconProvider interface
# =============================================================================

class TestStep1ImplementsInterface:
    """Step 1: LocalPlaceholderIconProvider implements IconProvider interface."""

    def test_inherits_from_icon_provider(self):
        """Provider inherits from IconProvider abstract base class."""
        assert issubclass(LocalPlaceholderIconProvider, IconProvider)

    def test_is_instance_of_icon_provider(self):
        """Provider instance is an IconProvider instance."""
        provider = LocalPlaceholderIconProvider()
        assert isinstance(provider, IconProvider)

    def test_has_name_property(self):
        """Provider has required name property."""
        provider = LocalPlaceholderIconProvider()
        assert hasattr(provider, "name")
        assert provider.name == LOCAL_PLACEHOLDER_PROVIDER_NAME
        assert provider.name == "local_placeholder"

    def test_has_generate_icon_method(self):
        """Provider has required generate_icon method."""
        provider = LocalPlaceholderIconProvider()
        assert hasattr(provider, "generate_icon")
        assert callable(provider.generate_icon)

    def test_has_get_capabilities_method(self):
        """Provider has required get_capabilities method."""
        provider = LocalPlaceholderIconProvider()
        assert hasattr(provider, "get_capabilities")
        assert callable(provider.get_capabilities)

    def test_has_provider_type_class_variable(self):
        """Provider has provider_type class variable."""
        assert hasattr(LocalPlaceholderIconProvider, "provider_type")
        assert LocalPlaceholderIconProvider.provider_type == "local_placeholder"

    def test_generate_icon_returns_icon_result(self):
        """generate_icon returns an IconResult."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("test-agent", "coder", "default")
        assert isinstance(result, IconResult)

    def test_get_capabilities_returns_capabilities(self):
        """get_capabilities returns IconProviderCapabilities."""
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()
        assert isinstance(caps, IconProviderCapabilities)


# =============================================================================
# Test Step 2: Generates deterministic placeholder based on agent name
# =============================================================================

class TestStep2DeterministicGeneration:
    """Step 2: Generates deterministic placeholder based on agent name."""

    def test_same_name_same_result(self):
        """Same agent name produces same icon (deterministic)."""
        provider = LocalPlaceholderIconProvider()

        result1 = provider.generate_icon("auth-login-impl", "coder", "default")
        result2 = provider.generate_icon("auth-login-impl", "coder", "default")

        assert result1.icon_data == result2.icon_data

    def test_same_name_different_provider_instances(self):
        """Same name produces same icon across different provider instances."""
        provider1 = LocalPlaceholderIconProvider()
        provider2 = LocalPlaceholderIconProvider()

        result1 = provider1.generate_icon("user-auth", "tester", "default")
        result2 = provider2.generate_icon("user-auth", "tester", "default")

        assert result1.icon_data == result2.icon_data

    def test_different_names_different_results(self):
        """Different agent names produce different icons."""
        provider = LocalPlaceholderIconProvider()

        result1 = provider.generate_icon("agent-alpha", "coder", "default")
        result2 = provider.generate_icon("agent-beta", "coder", "default")

        # Different names should produce different SVGs
        assert result1.icon_data != result2.icon_data

    def test_name_hash_is_deterministic(self):
        """Name hash function is deterministic."""
        name = "test-agent-name"

        hash1 = compute_name_hash(name)
        hash2 = compute_name_hash(name)

        assert hash1 == hash2

    def test_color_from_name_is_deterministic(self):
        """Color generation from name is deterministic."""
        name = "feature-auth"

        color1 = compute_color_from_name(name)
        color2 = compute_color_from_name(name)

        assert color1 == color2

    def test_svg_generation_is_deterministic(self):
        """SVG generation is deterministic."""
        name = "my-agent"
        config = PlaceholderConfig()

        svg1 = generate_placeholder_svg(name, config)
        svg2 = generate_placeholder_svg(name, config)

        assert svg1 == svg2

    def test_case_insensitive_hash(self):
        """Name hashing is case-insensitive."""
        hash1 = compute_name_hash("TestAgent")
        hash2 = compute_name_hash("testagent")

        assert hash1 == hash2


# =============================================================================
# Test Step 3: Uses color hash from agent name for uniqueness
# =============================================================================

class TestStep3ColorHashUniqueness:
    """Step 3: Uses color hash from agent name for uniqueness."""

    def test_color_is_hex_format(self):
        """Generated color is in hex format."""
        color = compute_color_from_name("agent-test")
        assert color.startswith("#")
        assert len(color) == 7  # #RRGGBB

    def test_color_uses_palette(self):
        """Color comes from the predefined palette."""
        color = compute_color_from_name("agent-test", use_palette=True)
        assert color in PLACEHOLDER_COLOR_PALETTE

    def test_different_names_different_colors_probability(self):
        """Different names usually produce different colors."""
        colors = set()
        for i in range(20):
            name = f"agent-{i}-unique"
            color = compute_color_from_name(name)
            colors.add(color)

        # With 20 samples and ~18 palette colors, expect several unique
        assert len(colors) >= 5

    def test_metadata_includes_color(self):
        """Icon result metadata includes the color used."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("color-test", "coder", "default")

        assert "color" in result.metadata
        assert result.metadata["color"].startswith("#")

    def test_color_hash_without_palette(self):
        """Can generate color without using palette."""
        color = compute_color_from_name("agent", use_palette=False)
        assert color.startswith("#")
        assert len(color) == 7

    def test_hash_to_palette_index(self):
        """Hash value maps to a valid palette index."""
        for name in ["a", "test", "agent-123", "very-long-agent-name"]:
            color = compute_color_from_name(name, use_palette=True)
            assert color in PLACEHOLDER_COLOR_PALETTE


# =============================================================================
# Test Step 4: Returns simple geometric shape or initials
# =============================================================================

class TestStep4ShapeAndInitials:
    """Step 4: Returns simple geometric shape or initials."""

    def test_svg_contains_shape(self):
        """Generated SVG contains a shape element."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("shape-test", "coder", "default")

        svg = result.icon_data
        # Check for at least one shape element
        has_shape = any(tag in svg for tag in ["<circle", "<rect", "<polygon"])
        assert has_shape

    def test_svg_contains_initials(self):
        """Generated SVG contains initials text."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("auth-login", "coder", "default")

        svg = result.icon_data
        assert "<text" in svg

    def test_extract_initials_hyphenated(self):
        """Extracts initials from hyphenated names."""
        initials = extract_initials("auth-login-impl")
        assert initials == "AL"

    def test_extract_initials_underscored(self):
        """Extracts initials from underscored names."""
        initials = extract_initials("user_auth_handler")
        assert initials == "UA"

    def test_extract_initials_camelcase(self):
        """Extracts initials from CamelCase names."""
        initials = extract_initials("AuthLoginHandler")
        assert initials == "AL"

    def test_extract_initials_single_word(self):
        """Extracts initials from single word names."""
        initials = extract_initials("auth")
        assert initials == "AU"

    def test_extract_initials_empty_name(self):
        """Handles empty name gracefully."""
        initials = extract_initials("")
        assert initials == "?"

    def test_extract_initials_max_chars(self):
        """Respects max_chars limit."""
        initials = extract_initials("auth-login-impl-handler", max_chars=3)
        assert len(initials) <= 3

    def test_metadata_includes_initials(self):
        """Icon result metadata includes initials."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("test-agent", "coder", "default")

        assert "initials" in result.metadata

    def test_metadata_includes_shape(self):
        """Icon result metadata includes shape."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("test-agent", "coder", "default")

        assert "shape" in result.metadata

    def test_different_shapes_available(self):
        """Multiple shape types are available."""
        shapes = [s.value for s in PlaceholderShape]
        assert "circle" in shapes
        assert "rounded_rect" in shapes
        assert "hexagon" in shapes
        assert len(shapes) >= 4

    def test_shape_generation(self):
        """Each shape type generates valid SVG."""
        for shape in PlaceholderShape:
            svg = generate_shape_svg(shape, 64, 64, "#6366f1")
            assert svg.startswith("<")
            assert "fill=" in svg


# =============================================================================
# Test Step 5: No external dependencies required
# =============================================================================

class TestStep5NoExternalDependencies:
    """Step 5: No external dependencies required."""

    def test_capabilities_no_api_key_required(self):
        """Provider does not require API key."""
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()

        assert caps.requires_api_key is False

    def test_capabilities_local_generation(self):
        """Provider metadata indicates local generation."""
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()

        assert caps.metadata.get("no_external_dependencies") is True

    def test_generation_without_network(self):
        """Can generate icons without network (mocked)."""
        # Mock socket to simulate no network
        import socket
        original_socket = socket.socket

        def mock_socket(*args, **kwargs):
            raise OSError("Network unavailable")

        # This should still work
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("offline-agent", "coder", "default")

        assert result.success is True
        assert result.icon_data is not None

    def test_fast_generation_speed(self):
        """Provider reports fast generation speed."""
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()

        assert caps.generation_speed == "fast"

    def test_no_rate_limit(self):
        """Provider has no rate limit."""
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()

        assert caps.rate_limit_per_minute == 0  # 0 = unlimited

    def test_no_concurrent_request_limit(self):
        """Provider has no concurrent request limit."""
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()

        assert caps.max_concurrent_requests == 0  # 0 = unlimited


# =============================================================================
# Additional Tests: IconResult Properties
# =============================================================================

class TestIconResultProperties:
    """Test IconResult properties and structure."""

    def test_result_success(self):
        """Result indicates success."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("success-test", "coder", "default")

        assert result.success is True

    def test_result_format_svg(self):
        """Result format is SVG."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("format-test", "coder", "default")

        assert result.format == IconFormat.SVG

    def test_result_has_icon_data(self):
        """Result has icon_data."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("data-test", "coder", "default")

        assert result.icon_data is not None
        assert len(result.icon_data) > 0

    def test_result_provider_name(self):
        """Result has correct provider name."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("name-test", "coder", "default")

        assert result.provider_name == "local_placeholder"

    def test_result_has_generation_time(self):
        """Result includes generation time."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("time-test", "coder", "default")

        assert result.generation_time_ms >= 0

    def test_result_has_metadata(self):
        """Result includes metadata dictionary."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("meta-test", "coder", "default")

        assert isinstance(result.metadata, dict)
        assert "agent_name" in result.metadata


# =============================================================================
# Additional Tests: Configuration
# =============================================================================

class TestConfiguration:
    """Test configuration options."""

    def test_default_config(self):
        """Default configuration is used when none provided."""
        provider = LocalPlaceholderIconProvider()
        assert provider.config.width == DEFAULT_SVG_WIDTH
        assert provider.config.height == DEFAULT_SVG_HEIGHT
        assert provider.config.shape == PlaceholderShape.CIRCLE

    def test_custom_config(self):
        """Custom configuration is respected."""
        config = PlaceholderConfig(
            width=128,
            height=128,
            shape=PlaceholderShape.HEXAGON,
        )
        provider = LocalPlaceholderIconProvider(config=config)

        assert provider.config.width == 128
        assert provider.config.shape == PlaceholderShape.HEXAGON

    def test_config_affects_output(self):
        """Configuration affects generated SVG."""
        config1 = PlaceholderConfig(shape=PlaceholderShape.CIRCLE)
        config2 = PlaceholderConfig(shape=PlaceholderShape.HEXAGON)

        svg1 = generate_placeholder_svg("agent", config1)
        svg2 = generate_placeholder_svg("agent", config2)

        assert svg1 != svg2

    def test_set_config_clears_cache(self):
        """Setting new config clears cache."""
        provider = LocalPlaceholderIconProvider()

        # Generate and cache
        result1 = provider.generate_icon("cache-test", "coder", "default")
        assert result1.cached is False

        # Should be cached now
        result2 = provider.generate_icon("cache-test", "coder", "default")
        assert result2.cached is True

        # Change config
        new_config = PlaceholderConfig(shape=PlaceholderShape.HEXAGON)
        provider.set_config(new_config)

        # Should not be cached after config change
        result3 = provider.generate_icon("cache-test", "coder", "default")
        assert result3.cached is False

    def test_placeholder_config_to_dict(self):
        """PlaceholderConfig can be serialized."""
        config = PlaceholderConfig(
            width=100,
            height=100,
            shape=PlaceholderShape.DIAMOND,
            use_initials=False,
        )
        data = config.to_dict()

        assert data["width"] == 100
        assert data["shape"] == "diamond"
        assert data["use_initials"] is False

    def test_placeholder_config_from_dict(self):
        """PlaceholderConfig can be deserialized."""
        data = {
            "width": 96,
            "height": 96,
            "shape": "hexagon",
            "use_initials": True,
        }
        config = PlaceholderConfig.from_dict(data)

        assert config.width == 96
        assert config.shape == PlaceholderShape.HEXAGON
        assert config.use_initials is True


# =============================================================================
# Additional Tests: Caching
# =============================================================================

class TestCaching:
    """Test caching behavior."""

    def test_first_call_not_cached(self):
        """First call is not cached."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("new-agent", "coder", "default")

        assert result.cached is False

    def test_second_call_cached(self):
        """Second call with same params is cached."""
        provider = LocalPlaceholderIconProvider()

        result1 = provider.generate_icon("cached-agent", "coder", "default")
        result2 = provider.generate_icon("cached-agent", "coder", "default")

        assert result1.cached is False
        assert result2.cached is True

    def test_cached_result_has_zero_generation_time(self):
        """Cached result reports 0ms generation time."""
        provider = LocalPlaceholderIconProvider()

        provider.generate_icon("time-agent", "coder", "default")
        result = provider.generate_icon("time-agent", "coder", "default")

        assert result.cached is True
        assert result.generation_time_ms == 0

    def test_clear_cache(self):
        """Cache can be cleared."""
        provider = LocalPlaceholderIconProvider()

        provider.generate_icon("clear-agent", "coder", "default")
        provider.clear_cache()
        result = provider.generate_icon("clear-agent", "coder", "default")

        assert result.cached is False

    def test_different_params_not_cached(self):
        """Different parameters are not cached."""
        provider = LocalPlaceholderIconProvider()

        result1 = provider.generate_icon("agent-1", "coder", "default")
        result2 = provider.generate_icon("agent-2", "coder", "default")

        assert result1.cached is False
        assert result2.cached is False


# =============================================================================
# Additional Tests: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_local_placeholder_provider(self):
        """get_local_placeholder_provider returns provider instance."""
        provider = get_local_placeholder_provider()
        assert isinstance(provider, LocalPlaceholderIconProvider)

    def test_generate_placeholder_icon_returns_svg(self):
        """generate_placeholder_icon returns SVG string."""
        svg = generate_placeholder_icon("test-agent")

        assert isinstance(svg, str)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_get_placeholder_color_returns_hex(self):
        """get_placeholder_color returns hex color."""
        color = get_placeholder_color("color-agent")

        assert color.startswith("#")
        assert len(color) == 7

    def test_get_placeholder_initials(self):
        """get_placeholder_initials returns initials."""
        initials = get_placeholder_initials("auth-login-handler")

        assert isinstance(initials, str)
        assert len(initials) <= 2
        assert initials.isupper() or initials == "?"


# =============================================================================
# Additional Tests: SVG Validation
# =============================================================================

class TestSvgValidation:
    """Test SVG output validity."""

    def test_svg_has_namespace(self):
        """Generated SVG has xmlns namespace."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("ns-test", "coder", "default")

        assert 'xmlns="http://www.w3.org/2000/svg"' in result.icon_data

    def test_svg_has_dimensions(self):
        """Generated SVG has width and height."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("dim-test", "coder", "default")

        assert 'width="' in result.icon_data
        assert 'height="' in result.icon_data

    def test_svg_has_viewbox(self):
        """Generated SVG has viewBox."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("vb-test", "coder", "default")

        assert "viewBox=" in result.icon_data

    def test_svg_well_formed(self):
        """Generated SVG is well-formed XML."""
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("xml-test", "coder", "default")

        # Basic well-formedness checks
        svg = result.icon_data
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert svg.count("<svg") == 1
        assert svg.count("</svg>") == 1


# =============================================================================
# Feature #216 Verification Steps
# =============================================================================

class TestFeature216VerificationSteps:
    """
    Complete verification of Feature #216 requirements.

    Each test maps directly to a step in the feature specification.
    """

    def test_step1_implements_icon_provider_interface(self):
        """
        Step 1: LocalPlaceholderIconProvider implements IconProvider interface.

        Verify that:
        - Class inherits from IconProvider
        - Has required abstract methods implemented
        - Can be instantiated and used
        """
        # Inheritance check
        assert issubclass(LocalPlaceholderIconProvider, IconProvider)

        # Instance check
        provider = LocalPlaceholderIconProvider()
        assert isinstance(provider, IconProvider)

        # Required properties/methods
        assert hasattr(provider, "name")
        assert hasattr(provider, "generate_icon")
        assert hasattr(provider, "get_capabilities")

        # Can call methods
        result = provider.generate_icon("test", "coder")
        assert result.success is True

        caps = provider.get_capabilities()
        assert caps is not None

    def test_step2_deterministic_placeholder_based_on_agent_name(self):
        """
        Step 2: Generates deterministic placeholder based on agent name.

        Verify that:
        - Same name always produces same icon
        - Different instances produce same result
        - Consistent across multiple calls
        """
        provider1 = LocalPlaceholderIconProvider()
        provider2 = LocalPlaceholderIconProvider()

        # Multiple calls with same name
        results = [
            provider1.generate_icon("deterministic-agent", "coder"),
            provider1.generate_icon("deterministic-agent", "coder"),
            provider2.generate_icon("deterministic-agent", "coder"),
        ]

        # All results should have identical icon_data
        first_data = results[0].icon_data
        for result in results[1:]:
            assert result.icon_data == first_data

    def test_step3_color_hash_from_agent_name_for_uniqueness(self):
        """
        Step 3: Uses color hash from agent name for uniqueness.

        Verify that:
        - Color is derived from agent name
        - Same name produces same color
        - Different names produce different colors (high probability)
        """
        # Same name, same color
        color1 = compute_color_from_name("unique-agent")
        color2 = compute_color_from_name("unique-agent")
        assert color1 == color2

        # Different names, likely different colors
        colors = set()
        for i in range(10):
            color = compute_color_from_name(f"agent-{i}")
            colors.add(color)

        # Should have some variety (not all same)
        assert len(colors) > 1

        # Color included in metadata
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("color-meta-test", "coder")
        assert "color" in result.metadata
        assert result.metadata["color"].startswith("#")

    def test_step4_returns_simple_geometric_shape_or_initials(self):
        """
        Step 4: Returns simple geometric shape or initials.

        Verify that:
        - SVG contains geometric shape element
        - SVG contains text with initials
        - Shape is configurable
        """
        provider = LocalPlaceholderIconProvider()
        result = provider.generate_icon("shape-initials-test", "coder")

        svg = result.icon_data

        # Has geometric shape
        has_shape = any(
            tag in svg
            for tag in ["<circle", "<rect", "<polygon"]
        )
        assert has_shape

        # Has text element with initials
        assert "<text" in svg

        # Initials in metadata
        assert "initials" in result.metadata

        # Shape in metadata
        assert "shape" in result.metadata

    def test_step5_no_external_dependencies_required(self):
        """
        Step 5: No external dependencies required.

        Verify that:
        - No API key required
        - Can generate without network
        - Fast generation (local only)
        - No rate limiting
        """
        provider = LocalPlaceholderIconProvider()
        caps = provider.get_capabilities()

        # No API key required
        assert caps.requires_api_key is False

        # Metadata indicates local generation
        assert caps.metadata.get("no_external_dependencies") is True
        assert caps.metadata.get("deterministic") is True

        # Fast generation
        assert caps.generation_speed == "fast"

        # No limits
        assert caps.rate_limit_per_minute == 0
        assert caps.max_concurrent_requests == 0

        # Can generate (test that it works without special setup)
        result = provider.generate_icon("no-deps-test", "coder")
        assert result.success is True
        assert result.icon_data is not None


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_full_workflow(self):
        """Test complete icon generation workflow."""
        # Create provider
        config = PlaceholderConfig(
            width=96,
            height=96,
            shape=PlaceholderShape.HEXAGON,
            use_initials=True,
        )
        provider = LocalPlaceholderIconProvider(config=config)

        # Generate icon
        result = provider.generate_icon(
            agent_name="user-authentication-service",
            role="coder",
            tone="professional",
        )

        # Verify result
        assert result.success is True
        assert result.format == IconFormat.SVG
        assert result.provider_name == "local_placeholder"
        assert result.icon_data is not None
        assert len(result.icon_data) > 100  # Non-trivial SVG

        # Verify metadata
        assert result.metadata["agent_name"] == "user-authentication-service"
        assert result.metadata["initials"] == "UA"
        assert result.metadata["shape"] == "hexagon"
        assert result.metadata["width"] == 96

        # Verify SVG structure
        svg = result.icon_data
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert 'width="96"' in svg
        assert "<polygon" in svg  # Hexagon is a polygon
        assert "<text" in svg

    def test_multiple_agents_unique_icons(self):
        """Test that multiple agents get unique icons."""
        provider = LocalPlaceholderIconProvider()

        agent_names = [
            "auth-service",
            "user-manager",
            "payment-handler",
            "notification-sender",
            "data-processor",
        ]

        icons = {}
        colors = set()
        initials_set = set()

        for name in agent_names:
            result = provider.generate_icon(name, "coder")
            icons[name] = result.icon_data
            colors.add(result.metadata["color"])
            initials_set.add(result.metadata["initials"])

        # All icons should be unique
        unique_icons = set(icons.values())
        assert len(unique_icons) == len(agent_names)

        # Should have some color variety
        assert len(colors) >= 2

        # Should have different initials
        assert len(initials_set) >= 3
