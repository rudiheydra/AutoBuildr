"""
LocalPlaceholderIconProvider
============================

Feature #216: LocalPlaceholderIconProvider implements stub

A stub provider that generates placeholder icons without external API calls.
Icons are generated deterministically based on the agent name, using color
hashing for uniqueness and simple geometric shapes or initials for visual
representation.

This provider is ideal for:
- Development and testing environments
- Offline operation
- Reducing external API dependencies
- Quick icon generation without network latency

Example:
    >>> provider = LocalPlaceholderIconProvider()
    >>> result = provider.generate_icon("auth-login-impl", "coder", "professional")
    >>> print(result.format)  # IconFormat.SVG
    >>> print(result.icon_data[:50])  # SVG content
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from api.icon_provider import (
    IconFormat,
    IconProvider,
    IconProviderCapabilities,
    IconResult,
)

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default SVG dimensions
DEFAULT_SVG_WIDTH = 64
DEFAULT_SVG_HEIGHT = 64

# Minimum and maximum color component values for readable colors
MIN_COLOR_VALUE = 60
MAX_COLOR_VALUE = 200

# Font sizes for different text lengths
FONT_SIZE_SINGLE_CHAR = 32
FONT_SIZE_TWO_CHARS = 28
FONT_SIZE_THREE_CHARS = 22

# Provider name
LOCAL_PLACEHOLDER_PROVIDER_NAME = "local_placeholder"

# Common color palette for deterministic but visually distinct icons
# These colors are chosen for good contrast with white text
PLACEHOLDER_COLOR_PALETTE = [
    "#6366f1",  # Indigo
    "#8b5cf6",  # Violet
    "#a855f7",  # Purple
    "#d946ef",  # Fuchsia
    "#ec4899",  # Pink
    "#f43f5e",  # Rose
    "#ef4444",  # Red
    "#f97316",  # Orange
    "#f59e0b",  # Amber
    "#eab308",  # Yellow
    "#84cc16",  # Lime
    "#22c55e",  # Green
    "#10b981",  # Emerald
    "#14b8a6",  # Teal
    "#06b6d4",  # Cyan
    "#0ea5e9",  # Sky
    "#3b82f6",  # Blue
    "#6366f1",  # Indigo (repeated for wrap)
]


# =============================================================================
# Enums
# =============================================================================

class PlaceholderShape(str, Enum):
    """Shapes available for placeholder icons."""

    CIRCLE = "circle"
    ROUNDED_RECT = "rounded_rect"
    HEXAGON = "hexagon"
    DIAMOND = "diamond"
    SQUARE = "square"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PlaceholderConfig:
    """
    Configuration for placeholder icon generation.

    Attributes:
        width: SVG width in pixels
        height: SVG height in pixels
        shape: The background shape to use
        use_initials: Whether to show initials (vs just shape)
        use_palette: Use predefined color palette (vs hash-based colors)
    """

    width: int = DEFAULT_SVG_WIDTH
    height: int = DEFAULT_SVG_HEIGHT
    shape: PlaceholderShape = PlaceholderShape.CIRCLE
    use_initials: bool = True
    use_palette: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "width": self.width,
            "height": self.height,
            "shape": self.shape.value,
            "use_initials": self.use_initials,
            "use_palette": self.use_palette,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaceholderConfig":
        """Create from dictionary."""
        shape = data.get("shape", "circle")
        if isinstance(shape, str):
            try:
                shape = PlaceholderShape(shape)
            except ValueError:
                shape = PlaceholderShape.CIRCLE

        return cls(
            width=data.get("width", DEFAULT_SVG_WIDTH),
            height=data.get("height", DEFAULT_SVG_HEIGHT),
            shape=shape,
            use_initials=data.get("use_initials", True),
            use_palette=data.get("use_palette", True),
        )


# =============================================================================
# Helper Functions
# =============================================================================

def compute_name_hash(name: str) -> int:
    """
    Compute a deterministic hash from a name.

    Uses MD5 for deterministic results across sessions.

    Args:
        name: The name to hash

    Returns:
        A positive integer hash value
    """
    if not name:
        name = "default"
    hash_bytes = hashlib.md5(name.lower().strip().encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:4], "big")


def compute_color_from_name(name: str, use_palette: bool = True) -> str:
    """
    Generate a deterministic color from a name.

    Args:
        name: The agent name to derive color from
        use_palette: If True, use predefined palette; if False, compute RGB

    Returns:
        Hex color string (e.g., "#6366f1")
    """
    hash_value = compute_name_hash(name)

    if use_palette:
        # Use predefined palette for consistent, attractive colors
        index = hash_value % len(PLACEHOLDER_COLOR_PALETTE)
        return PLACEHOLDER_COLOR_PALETTE[index]

    # Generate RGB components from hash
    # Use different parts of the hash for each component
    r = MIN_COLOR_VALUE + (hash_value % (MAX_COLOR_VALUE - MIN_COLOR_VALUE))
    g = MIN_COLOR_VALUE + ((hash_value >> 8) % (MAX_COLOR_VALUE - MIN_COLOR_VALUE))
    b = MIN_COLOR_VALUE + ((hash_value >> 16) % (MAX_COLOR_VALUE - MIN_COLOR_VALUE))

    return f"#{r:02x}{g:02x}{b:02x}"


def extract_initials(agent_name: str, max_chars: int = 2) -> str:
    """
    Extract initials from an agent name.

    Handles various naming conventions:
    - Hyphenated names: "auth-login-impl" -> "AL"
    - Underscore names: "user_auth_handler" -> "UA"
    - CamelCase: "AuthLoginHandler" -> "AL"
    - Single words: "auth" -> "AU"

    Args:
        agent_name: The agent name to extract initials from
        max_chars: Maximum number of characters (1-3)

    Returns:
        Uppercase initials string
    """
    if not agent_name:
        return "?"

    max_chars = max(1, min(3, max_chars))  # Clamp to 1-3

    # Clean the name
    name = agent_name.strip()

    # Try to split on common separators
    parts = []

    # Split on hyphens, underscores, dots, and camelCase transitions
    # First replace common separators with spaces
    normalized = name.replace("-", " ").replace("_", " ").replace(".", " ")

    # Handle CamelCase by inserting space before uppercase letters
    camel_split = ""
    for i, char in enumerate(normalized):
        if i > 0 and char.isupper() and normalized[i-1].islower():
            camel_split += " "
        camel_split += char

    # Split and filter empty strings
    parts = [p.strip() for p in camel_split.split() if p.strip()]

    if not parts:
        # Fallback: use first max_chars of the original name
        return agent_name[:max_chars].upper()

    if len(parts) == 1:
        # Single word - take first max_chars
        return parts[0][:max_chars].upper()

    # Multiple parts - take first letter of each
    initials = "".join(p[0] for p in parts[:max_chars])
    return initials.upper()


def get_font_size(text: str) -> int:
    """
    Get appropriate font size based on text length.

    Args:
        text: The text to display

    Returns:
        Font size in pixels
    """
    length = len(text) if text else 1

    if length <= 1:
        return FONT_SIZE_SINGLE_CHAR
    elif length == 2:
        return FONT_SIZE_TWO_CHARS
    else:
        return FONT_SIZE_THREE_CHARS


# =============================================================================
# SVG Generation
# =============================================================================

def generate_circle_shape(
    width: int,
    height: int,
    fill_color: str
) -> str:
    """Generate SVG circle background."""
    cx = width // 2
    cy = height // 2
    r = min(width, height) // 2 - 2
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill_color}"/>'


def generate_rounded_rect_shape(
    width: int,
    height: int,
    fill_color: str
) -> str:
    """Generate SVG rounded rectangle background."""
    rx = min(width, height) // 8
    return f'<rect x="2" y="2" width="{width-4}" height="{height-4}" rx="{rx}" fill="{fill_color}"/>'


def generate_hexagon_shape(
    width: int,
    height: int,
    fill_color: str
) -> str:
    """Generate SVG hexagon background."""
    cx, cy = width // 2, height // 2
    r = min(width, height) // 2 - 4

    # Calculate hexagon points
    points = []
    import math
    for i in range(6):
        angle = math.pi / 6 + (i * math.pi / 3)  # Start at 30 degrees
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append(f"{x:.1f},{y:.1f}")

    return f'<polygon points="{" ".join(points)}" fill="{fill_color}"/>'


def generate_diamond_shape(
    width: int,
    height: int,
    fill_color: str
) -> str:
    """Generate SVG diamond background."""
    cx, cy = width // 2, height // 2
    dx = width // 2 - 4
    dy = height // 2 - 4

    points = f"{cx},{cy-dy} {cx+dx},{cy} {cx},{cy+dy} {cx-dx},{cy}"
    return f'<polygon points="{points}" fill="{fill_color}"/>'


def generate_square_shape(
    width: int,
    height: int,
    fill_color: str
) -> str:
    """Generate SVG square background."""
    return f'<rect x="2" y="2" width="{width-4}" height="{height-4}" fill="{fill_color}"/>'


def generate_shape_svg(
    shape: PlaceholderShape,
    width: int,
    height: int,
    fill_color: str
) -> str:
    """
    Generate the SVG shape element based on the shape type.

    Args:
        shape: The shape type to generate
        width: SVG width
        height: SVG height
        fill_color: Fill color for the shape

    Returns:
        SVG element string
    """
    generators = {
        PlaceholderShape.CIRCLE: generate_circle_shape,
        PlaceholderShape.ROUNDED_RECT: generate_rounded_rect_shape,
        PlaceholderShape.HEXAGON: generate_hexagon_shape,
        PlaceholderShape.DIAMOND: generate_diamond_shape,
        PlaceholderShape.SQUARE: generate_square_shape,
    }

    generator = generators.get(shape, generate_circle_shape)
    return generator(width, height, fill_color)


def generate_text_element(
    text: str,
    width: int,
    height: int,
    font_size: int | None = None
) -> str:
    """
    Generate SVG text element for initials.

    Args:
        text: The text to display
        width: SVG width for centering
        height: SVG height for centering
        font_size: Optional font size override

    Returns:
        SVG text element string
    """
    if not text:
        return ""

    if font_size is None:
        font_size = get_font_size(text)

    cx = width // 2
    cy = height // 2

    return (
        f'<text x="{cx}" y="{cy}" '
        f'font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{font_size}" '
        f'font-weight="bold" '
        f'fill="white" '
        f'text-anchor="middle" '
        f'dominant-baseline="central">{text}</text>'
    )


def generate_placeholder_svg(
    agent_name: str,
    config: PlaceholderConfig | None = None
) -> str:
    """
    Generate a complete placeholder SVG icon.

    Args:
        agent_name: The agent name for color and initials derivation
        config: Optional configuration; uses defaults if not provided

    Returns:
        Complete SVG string
    """
    if config is None:
        config = PlaceholderConfig()

    # Get color from name
    color = compute_color_from_name(agent_name, config.use_palette)

    # Generate shape
    shape_element = generate_shape_svg(
        config.shape,
        config.width,
        config.height,
        color
    )

    # Generate text if needed
    text_element = ""
    if config.use_initials:
        initials = extract_initials(agent_name)
        text_element = generate_text_element(
            initials,
            config.width,
            config.height
        )

    # Compose full SVG
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{config.width}" height="{config.height}" '
        f'viewBox="0 0 {config.width} {config.height}">'
        f'{shape_element}'
        f'{text_element}'
        f'</svg>'
    )

    return svg


# =============================================================================
# LocalPlaceholderIconProvider Implementation
# =============================================================================

class LocalPlaceholderIconProvider(IconProvider):
    """
    Stub provider that generates placeholder icons without external API calls.

    This provider generates deterministic SVG placeholder icons based on the
    agent name. Icons feature:

    - Colored backgrounds derived from agent name hash
    - Initials extracted from agent name
    - Simple geometric shapes (circle, rounded rect, hexagon, etc.)
    - No external dependencies required

    The same agent name will always produce the same icon, ensuring consistency
    across sessions and environments.

    Example:
        >>> provider = LocalPlaceholderIconProvider()
        >>> result = provider.generate_icon("auth-login-impl", "coder", "professional")
        >>> result.success  # True
        >>> result.format  # IconFormat.SVG
        >>> print(result.icon_data[:100])  # <svg xmlns...

        # With custom configuration
        >>> config = PlaceholderConfig(shape=PlaceholderShape.HEXAGON)
        >>> provider = LocalPlaceholderIconProvider(config=config)
        >>> result = provider.generate_icon("user-auth", "coder")
    """

    provider_type: ClassVar[str] = "local_placeholder"

    def __init__(
        self,
        config: PlaceholderConfig | None = None,
    ):
        """
        Initialize the LocalPlaceholderIconProvider.

        Args:
            config: Optional default configuration for icon generation
        """
        self._config = config or PlaceholderConfig()
        self._cache: dict[str, IconResult] = {}
        _logger.debug("LocalPlaceholderIconProvider initialized with config: %s", self._config.to_dict())

    @property
    def name(self) -> str:
        """Get the unique provider name."""
        return LOCAL_PLACEHOLDER_PROVIDER_NAME

    @property
    def config(self) -> PlaceholderConfig:
        """Get the current configuration."""
        return self._config

    def generate_icon(
        self,
        agent_name: str,
        role: str,
        tone: str = "default"
    ) -> IconResult:
        """
        Generate a placeholder icon for an agent.

        The icon is generated deterministically based on the agent name:
        - Color is derived from the agent name hash
        - Initials are extracted from the agent name

        Args:
            agent_name: The agent's name (primary input for icon generation)
            role: The agent's role (not used for placeholder generation)
            tone: The desired tone (not used for placeholder generation)

        Returns:
            IconResult with SVG icon data
        """
        start_time = time.time()

        # Check cache
        cache_key = self._get_cache_key(agent_name, role, tone)
        if cache_key in self._cache:
            cached_result = self._cache[cache_key]
            return IconResult(
                success=cached_result.success,
                icon_url=cached_result.icon_url,
                icon_data=cached_result.icon_data,
                format=cached_result.format,
                provider_name=cached_result.provider_name,
                generation_time_ms=0,  # Cached results are instant
                metadata=cached_result.metadata,
                cached=True,
            )

        try:
            # Generate the SVG
            svg_data = generate_placeholder_svg(agent_name, self._config)

            generation_time_ms = int((time.time() - start_time) * 1000)

            # Build metadata
            initials = extract_initials(agent_name)
            color = compute_color_from_name(agent_name, self._config.use_palette)

            result = IconResult.success_result(
                icon_data=svg_data,
                format=IconFormat.SVG,
                provider_name=self.name,
                generation_time_ms=generation_time_ms,
                metadata={
                    "agent_name": agent_name,
                    "initials": initials,
                    "color": color,
                    "shape": self._config.shape.value,
                    "width": self._config.width,
                    "height": self._config.height,
                },
            )

            # Cache the result
            self._cache[cache_key] = result

            _logger.debug(
                "Generated placeholder icon for %s: initials=%s, color=%s",
                agent_name, initials, color
            )

            return result

        except Exception as e:
            _logger.error("Failed to generate placeholder icon: %s", e)
            return IconResult.error_result(
                error=str(e),
                provider_name=self.name,
                generation_time_ms=int((time.time() - start_time) * 1000),
            )

    def get_capabilities(self) -> IconProviderCapabilities:
        """
        Get the capabilities of this provider.

        Returns:
            IconProviderCapabilities describing this provider
        """
        return IconProviderCapabilities(
            supported_formats=[IconFormat.SVG],
            supports_url_generation=False,
            supports_data_generation=True,
            supports_caching=True,
            max_concurrent_requests=0,  # No limit
            rate_limit_per_minute=0,  # No limit
            requires_api_key=False,
            generation_speed="fast",
            version="1.0.0",
            metadata={
                "provider_type": "local_placeholder",
                "no_external_dependencies": True,
                "deterministic": True,
                "available_shapes": [s.value for s in PlaceholderShape],
            },
        )

    def _get_cache_key(self, agent_name: str, role: str, tone: str) -> str:
        """Generate a cache key for the given parameters."""
        # Include config in key since shape/size affects output
        key_data = f"{agent_name}:{role}:{tone}:{self._config.shape.value}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def clear_cache(self) -> None:
        """Clear the icon cache."""
        self._cache.clear()
        _logger.debug("Cleared icon cache for local_placeholder provider")

    def set_config(self, config: PlaceholderConfig) -> None:
        """
        Update the configuration.

        Note: This clears the cache since configuration affects output.

        Args:
            config: The new configuration to use
        """
        self._config = config
        self._cache.clear()
        _logger.debug("Updated config for local_placeholder provider: %s", config.to_dict())


# =============================================================================
# Convenience Functions
# =============================================================================

def get_local_placeholder_provider(
    config: PlaceholderConfig | None = None
) -> LocalPlaceholderIconProvider:
    """
    Create a new LocalPlaceholderIconProvider instance.

    Args:
        config: Optional configuration for the provider

    Returns:
        A new LocalPlaceholderIconProvider instance
    """
    return LocalPlaceholderIconProvider(config=config)


def generate_placeholder_icon(
    agent_name: str,
    shape: PlaceholderShape = PlaceholderShape.CIRCLE,
    use_initials: bool = True,
    width: int = DEFAULT_SVG_WIDTH,
    height: int = DEFAULT_SVG_HEIGHT,
) -> str:
    """
    Quick convenience function to generate a placeholder icon SVG.

    Args:
        agent_name: The agent name for color/initials derivation
        shape: The background shape
        use_initials: Whether to include initials
        width: SVG width
        height: SVG height

    Returns:
        SVG string
    """
    config = PlaceholderConfig(
        width=width,
        height=height,
        shape=shape,
        use_initials=use_initials,
    )
    return generate_placeholder_svg(agent_name, config)


def get_placeholder_color(agent_name: str) -> str:
    """
    Get the placeholder color for an agent name.

    Args:
        agent_name: The agent name

    Returns:
        Hex color string
    """
    return compute_color_from_name(agent_name, use_palette=True)


def get_placeholder_initials(agent_name: str, max_chars: int = 2) -> str:
    """
    Get the initials for an agent name.

    Args:
        agent_name: The agent name
        max_chars: Maximum number of characters

    Returns:
        Initials string
    """
    return extract_initials(agent_name, max_chars)
