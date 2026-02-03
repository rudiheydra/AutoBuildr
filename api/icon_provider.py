"""
IconProvider Interface
======================

Feature #215: Icon provider interface defined

Defines a pluggable interface for icon generation providers, allowing different
backends (DALL-E, Stable Diffusion, static icon libraries, etc.) to provide
icons for agents.

This module provides:
- IconProvider abstract base class defining the icon provider contract
- IconResult dataclass for icon generation results
- IconFormat enum for supported icon formats
- IconProviderRegistry for managing multiple providers
- DefaultIconProvider implementation using task type icons
- Configuration utilities for selecting active provider

The IconProvider interface allows the system to work with different icon
generation backends without knowing their implementation details. This enables:
- Static icon assignment from predefined sets
- AI-generated icons (DALL-E, Stable Diffusion, etc.)
- Custom icon providers for specific use cases

Example:
    >>> registry = get_icon_registry()
    >>> result = registry.generate_icon(
    ...     agent_name="auth-login-impl",
    ...     role="coder",
    ...     tone="professional"
    ... )
    >>> print(result.format, result.icon_url or result.icon_data[:50])
"""
from __future__ import annotations

import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

from api.display_derivation import TASK_TYPE_ICONS, DEFAULT_ICON

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


# =============================================================================
# Exceptions
# =============================================================================

class IconProviderError(Exception):
    """Base exception for icon provider errors."""
    pass


class IconGenerationError(IconProviderError):
    """Raised when icon generation fails."""

    def __init__(
        self,
        provider_name: str,
        reason: str,
        agent_name: str | None = None,
        message: str | None = None,
    ):
        self.provider_name = provider_name
        self.reason = reason
        self.agent_name = agent_name

        if message is None:
            if agent_name:
                message = f"Icon generation failed for agent '{agent_name}' in provider '{provider_name}': {reason}"
            else:
                message = f"Icon generation failed in provider '{provider_name}': {reason}"

        super().__init__(message)


class ProviderNotFoundError(IconProviderError):
    """Raised when a requested icon provider is not found."""

    def __init__(
        self,
        provider_name: str,
        available_providers: list[str] | None = None,
        message: str | None = None,
    ):
        self.provider_name = provider_name
        self.available_providers = available_providers or []

        if message is None:
            if self.available_providers:
                available = ", ".join(self.available_providers)
                message = f"Icon provider '{provider_name}' not found. Available providers: {available}"
            else:
                message = f"Icon provider '{provider_name}' not found. No providers are registered."

        super().__init__(message)


class ProviderAlreadyRegisteredError(IconProviderError):
    """Raised when attempting to register a provider with a name that already exists."""

    def __init__(
        self,
        provider_name: str,
        message: str | None = None,
    ):
        self.provider_name = provider_name

        if message is None:
            message = f"Icon provider '{provider_name}' is already registered"

        super().__init__(message)


class InvalidIconFormatError(IconProviderError):
    """Raised when an invalid icon format is specified."""

    def __init__(
        self,
        format_value: str,
        supported_formats: list[str] | None = None,
        message: str | None = None,
    ):
        self.format_value = format_value
        self.supported_formats = supported_formats or []

        if message is None:
            if self.supported_formats:
                supported = ", ".join(self.supported_formats)
                message = f"Invalid icon format '{format_value}'. Supported formats: {supported}"
            else:
                message = f"Invalid icon format '{format_value}'"

        super().__init__(message)


# =============================================================================
# Enums
# =============================================================================

class IconFormat(str, Enum):
    """Supported icon formats."""

    SVG = "svg"          # Scalable Vector Graphics
    PNG = "png"          # Portable Network Graphics
    JPEG = "jpeg"        # JPEG image
    WEBP = "webp"        # WebP image format
    EMOJI = "emoji"      # Unicode emoji or emoji identifier
    ICON_ID = "icon_id"  # Icon identifier for icon libraries (e.g., "code", "gear")

    @classmethod
    def is_binary(cls, format: "IconFormat") -> bool:
        """Check if format is a binary image format."""
        return format in (cls.PNG, cls.JPEG, cls.WEBP)

    @classmethod
    def is_text(cls, format: "IconFormat") -> bool:
        """Check if format is a text-based format."""
        return format in (cls.SVG, cls.EMOJI, cls.ICON_ID)


class IconTone(str, Enum):
    """Icon generation tone/style preferences."""

    PROFESSIONAL = "professional"    # Clean, corporate style
    PLAYFUL = "playful"              # Fun, friendly style
    MINIMALIST = "minimalist"        # Simple, clean lines
    DETAILED = "detailed"            # Rich, detailed imagery
    CARTOON = "cartoon"              # Cartoon/comic style
    TECH = "tech"                    # Technology-focused
    DEFAULT = "default"              # Provider default style


class ProviderStatus(str, Enum):
    """Status of an icon provider."""

    AVAILABLE = "available"             # Provider is ready to use
    UNAVAILABLE = "unavailable"         # Provider is not reachable
    RATE_LIMITED = "rate_limited"       # Temporarily rate limited
    API_KEY_REQUIRED = "api_key_required"  # Needs API key configuration
    ERROR = "error"                     # Provider is in error state


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class IconResult:
    """
    Result from generating an icon.

    Attributes:
        success: Whether icon generation succeeded
        icon_url: URL to the generated icon (if available)
        icon_data: Raw icon data (base64 encoded for binary, raw for text formats)
        format: The format of the icon (svg, png, emoji, etc.)
        provider_name: Name of the provider that generated the icon
        generation_time_ms: How long generation took in milliseconds
        metadata: Additional provider-specific metadata
        error: Error message if success is False
        cached: Whether this result was served from cache
    """

    success: bool
    icon_url: str | None = None
    icon_data: str | None = None
    format: IconFormat = IconFormat.ICON_ID
    provider_name: str = ""
    generation_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cached: bool = False

    def __post_init__(self):
        """Validate that successful results have at least icon_url or icon_data."""
        if self.success and not self.icon_url and not self.icon_data:
            raise ValueError("Successful IconResult must have icon_url or icon_data")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "icon_url": self.icon_url,
            "icon_data": self.icon_data,
            "format": self.format.value if isinstance(self.format, IconFormat) else self.format,
            "provider_name": self.provider_name,
            "generation_time_ms": self.generation_time_ms,
            "metadata": self.metadata,
            "error": self.error,
            "cached": self.cached,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IconResult":
        """Create an IconResult from a dictionary."""
        format_value = data.get("format", "icon_id")
        if isinstance(format_value, str):
            try:
                format_value = IconFormat(format_value)
            except ValueError:
                format_value = IconFormat.ICON_ID

        return cls(
            success=data.get("success", False),
            icon_url=data.get("icon_url"),
            icon_data=data.get("icon_data"),
            format=format_value,
            provider_name=data.get("provider_name", ""),
            generation_time_ms=data.get("generation_time_ms", 0),
            metadata=data.get("metadata", {}),
            error=data.get("error"),
            cached=data.get("cached", False),
        )

    @classmethod
    def success_result(
        cls,
        *,
        icon_url: str | None = None,
        icon_data: str | None = None,
        format: IconFormat = IconFormat.ICON_ID,
        provider_name: str = "",
        generation_time_ms: int = 0,
        metadata: dict[str, Any] | None = None,
        cached: bool = False,
    ) -> "IconResult":
        """Create a successful icon result."""
        return cls(
            success=True,
            icon_url=icon_url,
            icon_data=icon_data,
            format=format,
            provider_name=provider_name,
            generation_time_ms=generation_time_ms,
            metadata=metadata or {},
            cached=cached,
        )

    @classmethod
    def error_result(
        cls,
        error: str,
        provider_name: str = "",
        generation_time_ms: int = 0,
    ) -> "IconResult":
        """Create an error icon result."""
        return cls(
            success=False,
            error=error,
            provider_name=provider_name,
            generation_time_ms=generation_time_ms,
        )

    @property
    def is_binary(self) -> bool:
        """Check if the icon data is in a binary format."""
        return IconFormat.is_binary(self.format)

    @property
    def is_text(self) -> bool:
        """Check if the icon data is in a text format."""
        return IconFormat.is_text(self.format)

    def get_bytes(self) -> bytes | None:
        """
        Get icon data as bytes (for binary formats).

        Returns:
            Decoded bytes if icon_data is base64 encoded, None otherwise.
        """
        if not self.icon_data:
            return None

        if self.is_binary:
            try:
                return base64.b64decode(self.icon_data)
            except Exception:
                return None

        return self.icon_data.encode("utf-8")


@dataclass
class IconProviderCapabilities:
    """
    Describes what an IconProvider can do.

    Attributes:
        supported_formats: List of formats this provider can generate
        supports_url_generation: Whether provider can return URLs
        supports_data_generation: Whether provider can return raw data
        supports_caching: Whether provider implements caching
        max_concurrent_requests: Maximum concurrent icon generations (0 = unlimited)
        rate_limit_per_minute: Rate limit for icon generation (0 = unlimited)
        requires_api_key: Whether provider requires API key configuration
        generation_speed: Estimated generation speed (fast, medium, slow)
        version: Provider version string
        metadata: Additional capability metadata
    """

    supported_formats: list[IconFormat] = field(default_factory=lambda: [IconFormat.ICON_ID])
    supports_url_generation: bool = False
    supports_data_generation: bool = True
    supports_caching: bool = True
    max_concurrent_requests: int = 0
    rate_limit_per_minute: int = 0
    requires_api_key: bool = False
    generation_speed: str = "fast"  # fast, medium, slow
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "supported_formats": [
                f.value if isinstance(f, IconFormat) else f
                for f in self.supported_formats
            ],
            "supports_url_generation": self.supports_url_generation,
            "supports_data_generation": self.supports_data_generation,
            "supports_caching": self.supports_caching,
            "max_concurrent_requests": self.max_concurrent_requests,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "requires_api_key": self.requires_api_key,
            "generation_speed": self.generation_speed,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IconProviderCapabilities":
        """Create IconProviderCapabilities from a dictionary."""
        formats = []
        for fmt in data.get("supported_formats", ["icon_id"]):
            if isinstance(fmt, str):
                try:
                    formats.append(IconFormat(fmt))
                except ValueError:
                    formats.append(IconFormat.ICON_ID)
            else:
                formats.append(fmt)

        return cls(
            supported_formats=formats,
            supports_url_generation=data.get("supports_url_generation", False),
            supports_data_generation=data.get("supports_data_generation", True),
            supports_caching=data.get("supports_caching", True),
            max_concurrent_requests=data.get("max_concurrent_requests", 0),
            rate_limit_per_minute=data.get("rate_limit_per_minute", 0),
            requires_api_key=data.get("requires_api_key", False),
            generation_speed=data.get("generation_speed", "fast"),
            version=data.get("version", "1.0.0"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class IconGenerationRequest:
    """
    Request for icon generation.

    Attributes:
        agent_name: The agent's machine-friendly name
        role: The agent's role (coder, reviewer, auditor, etc.)
        tone: The desired icon tone/style
        task_type: Optional task type for context
        preferred_format: Preferred output format
        size_hint: Suggested icon size in pixels (width x height)
        context: Additional context for generation
    """

    agent_name: str
    role: str
    tone: IconTone = IconTone.DEFAULT
    task_type: str | None = None
    preferred_format: IconFormat | None = None
    size_hint: tuple[int, int] | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_name": self.agent_name,
            "role": self.role,
            "tone": self.tone.value if isinstance(self.tone, IconTone) else self.tone,
            "task_type": self.task_type,
            "preferred_format": (
                self.preferred_format.value
                if isinstance(self.preferred_format, IconFormat)
                else self.preferred_format
            ),
            "size_hint": self.size_hint,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IconGenerationRequest":
        """Create an IconGenerationRequest from a dictionary."""
        tone = data.get("tone", "default")
        if isinstance(tone, str):
            try:
                tone = IconTone(tone)
            except ValueError:
                tone = IconTone.DEFAULT

        preferred_format = data.get("preferred_format")
        if isinstance(preferred_format, str):
            try:
                preferred_format = IconFormat(preferred_format)
            except ValueError:
                preferred_format = None

        return cls(
            agent_name=data["agent_name"],
            role=data["role"],
            tone=tone,
            task_type=data.get("task_type"),
            preferred_format=preferred_format,
            size_hint=tuple(data["size_hint"]) if data.get("size_hint") else None,
            context=data.get("context", {}),
        )


# =============================================================================
# IconProvider Abstract Base Class
# =============================================================================

class IconProvider(ABC):
    """
    Abstract base class for icon providers.

    An IconProvider represents a source of icons for agents. This could be:
    - A static icon library mapping roles to icons
    - An AI image generation service (DALL-E, Stable Diffusion)
    - A custom icon generation service

    Implementations must provide:
    - name: A unique identifier for the provider
    - generate_icon(): Generate an icon for an agent
    - get_capabilities(): Describe provider capabilities

    Example Implementation:
        class MyIconProvider(IconProvider):
            @property
            def name(self) -> str:
                return "my_provider"

            def generate_icon(
                self,
                agent_name: str,
                role: str,
                tone: str = "default"
            ) -> IconResult:
                # Generate icon based on role
                icon_id = self._get_icon_for_role(role)
                return IconResult.success_result(
                    icon_data=icon_id,
                    format=IconFormat.ICON_ID,
                    provider_name=self.name
                )
    """

    # Class variable for provider type identification
    provider_type: ClassVar[str] = "base"

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the unique name of this provider.

        This name is used to identify the provider in the registry
        and for configuration selection.

        Returns:
            str: The provider name (e.g., "default", "dalle", "stable-diffusion")
        """
        ...

    @abstractmethod
    def generate_icon(
        self,
        agent_name: str,
        role: str,
        tone: str = "default"
    ) -> IconResult:
        """
        Generate an icon for an agent.

        Args:
            agent_name: The agent's machine-friendly name (e.g., "feature-auth-login-impl")
            role: The agent's role (e.g., "coder", "reviewer", "auditor")
            tone: The desired icon tone/style (e.g., "professional", "playful")

        Returns:
            IconResult: The result containing icon URL, data, and format

        Raises:
            IconGenerationError: If icon generation fails
            IconProviderError: For other provider errors
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> IconProviderCapabilities:
        """
        Get the capabilities of this provider.

        Returns:
            IconProviderCapabilities: Description of what this provider can do
        """
        ...

    def get_status(self) -> ProviderStatus:
        """
        Get the current status of this provider.

        Default implementation returns AVAILABLE. Subclasses can override
        to check actual service availability.

        Returns:
            ProviderStatus: The current provider status
        """
        return ProviderStatus.AVAILABLE

    def generate_icon_from_request(self, request: IconGenerationRequest) -> IconResult:
        """
        Generate an icon from a full request object.

        This is a convenience method that extracts parameters from the request
        and calls generate_icon().

        Args:
            request: The icon generation request

        Returns:
            IconResult: The result of icon generation
        """
        tone = request.tone.value if isinstance(request.tone, IconTone) else request.tone
        return self.generate_icon(
            agent_name=request.agent_name,
            role=request.role,
            tone=tone,
        )

    def supports_format(self, format: IconFormat) -> bool:
        """
        Check if this provider supports a specific format.

        Args:
            format: The format to check

        Returns:
            bool: True if the format is supported
        """
        capabilities = self.get_capabilities()
        return format in capabilities.supported_formats


# =============================================================================
# DefaultIconProvider Implementation
# =============================================================================

class DefaultIconProvider(IconProvider):
    """
    Default IconProvider using static task type icon mapping.

    This provider maps roles and task types to predefined icon identifiers
    from the existing TASK_TYPE_ICONS mapping. It provides fast, consistent
    icon assignment without external API calls.

    The provider uses a deterministic algorithm:
    1. Check for explicit icon override in context
    2. Map role to task type
    3. Map task type to icon identifier
    4. Fall back to default icon

    Example:
        >>> provider = DefaultIconProvider()
        >>> result = provider.generate_icon("auth-impl", "coder", "professional")
        >>> print(result.icon_data)  # "code"
        >>> print(result.format)  # IconFormat.ICON_ID
    """

    provider_type: ClassVar[str] = "default"

    # Role to task type mapping
    ROLE_TASK_TYPE_MAP: ClassVar[dict[str, str]] = {
        "coder": "coding",
        "developer": "coding",
        "engineer": "coding",
        "tester": "testing",
        "qa": "testing",
        "test_runner": "testing",
        "reviewer": "audit",
        "auditor": "audit",
        "security": "audit",
        "refactorer": "refactoring",
        "optimizer": "refactoring",
        "documenter": "documentation",
        "writer": "documentation",
        "technical_writer": "documentation",
    }

    def __init__(
        self,
        custom_icons: dict[str, str] | None = None,
        default_icon: str = DEFAULT_ICON,
    ):
        """
        Initialize the DefaultIconProvider.

        Args:
            custom_icons: Optional custom role-to-icon mapping
            default_icon: Icon to use when no mapping is found
        """
        self._custom_icons: dict[str, str] = custom_icons or {}
        self._default_icon = default_icon
        self._cache: dict[str, IconResult] = {}

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "default"

    def generate_icon(
        self,
        agent_name: str,
        role: str,
        tone: str = "default"
    ) -> IconResult:
        """
        Generate an icon for an agent.

        Uses role-to-task-type mapping and then task-type-to-icon mapping.
        Results are cached for performance.

        Args:
            agent_name: The agent's name (used for cache key)
            role: The agent's role
            tone: The desired tone (ignored by this provider)

        Returns:
            IconResult: The result with icon_data containing the icon identifier
        """
        import time
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

        # Check for custom icon mapping
        normalized_role = role.lower().strip()
        if normalized_role in self._custom_icons:
            icon_id = self._custom_icons[normalized_role]
        else:
            # Map role to task type
            task_type = self.ROLE_TASK_TYPE_MAP.get(normalized_role, "custom")

            # Map task type to icon
            icon_id = TASK_TYPE_ICONS.get(task_type, self._default_icon)

        generation_time_ms = int((time.time() - start_time) * 1000)

        result = IconResult.success_result(
            icon_data=icon_id,
            format=IconFormat.ICON_ID,
            provider_name=self.name,
            generation_time_ms=generation_time_ms,
            metadata={"role": role, "mapped_icon": icon_id},
        )

        # Cache the result
        self._cache[cache_key] = result

        return result

    def get_capabilities(self) -> IconProviderCapabilities:
        """Get provider capabilities."""
        return IconProviderCapabilities(
            supported_formats=[IconFormat.ICON_ID, IconFormat.EMOJI],
            supports_url_generation=False,
            supports_data_generation=True,
            supports_caching=True,
            max_concurrent_requests=0,  # No limit
            rate_limit_per_minute=0,  # No limit
            requires_api_key=False,
            generation_speed="fast",
            version="1.0.0",
            metadata={"provider_type": "default", "static_mapping": True},
        )

    def _get_cache_key(self, agent_name: str, role: str, tone: str) -> str:
        """Generate a cache key for the given parameters."""
        # Use hash for consistent key generation
        key_data = f"{agent_name}:{role}:{tone}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def clear_cache(self) -> None:
        """Clear the icon cache."""
        self._cache.clear()
        _logger.debug("Cleared icon cache for default provider")

    def add_custom_icon(self, role: str, icon: str) -> None:
        """
        Add a custom role-to-icon mapping.

        Args:
            role: The role to map
            icon: The icon identifier to use
        """
        self._custom_icons[role.lower().strip()] = icon
        # Clear cache since mappings changed
        self._cache.clear()


# =============================================================================
# IconProviderRegistry
# =============================================================================

class IconProviderRegistry:
    """
    Registry for managing multiple icon providers.

    The registry allows:
    - Registering and unregistering providers
    - Looking up providers by name
    - Setting an active provider for icon generation
    - Generating icons using the active provider

    Example:
        >>> registry = IconProviderRegistry()
        >>> registry.register(DefaultIconProvider())
        >>> registry.set_active_provider("default")
        >>> result = registry.generate_icon("auth-impl", "coder", "professional")
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._providers: dict[str, IconProvider] = {}
        self._active_provider_name: str | None = None
        _logger.debug("IconProviderRegistry initialized")

    def register(
        self,
        provider: IconProvider,
        *,
        replace: bool = False,
        set_active: bool = False,
    ) -> None:
        """
        Register an icon provider.

        Args:
            provider: The provider to register
            replace: If True, replace existing provider with same name
            set_active: If True, set this provider as the active provider

        Raises:
            ProviderAlreadyRegisteredError: If provider name already exists and replace=False
        """
        name = provider.name

        if name in self._providers and not replace:
            raise ProviderAlreadyRegisteredError(name)

        self._providers[name] = provider
        _logger.info("Registered icon provider: %s", name)

        if set_active or self._active_provider_name is None:
            self._active_provider_name = name
            _logger.info("Set active icon provider: %s", name)

    def unregister(self, name: str) -> bool:
        """
        Unregister an icon provider.

        Args:
            name: The name of the provider to unregister

        Returns:
            bool: True if the provider was removed, False if not found
        """
        if name in self._providers:
            del self._providers[name]
            _logger.info("Unregistered icon provider: %s", name)

            # Clear active provider if it was unregistered
            if self._active_provider_name == name:
                self._active_provider_name = None
                # Set first available provider as active
                if self._providers:
                    self._active_provider_name = next(iter(self._providers.keys()))
                    _logger.info("Set active icon provider: %s", self._active_provider_name)

            return True
        return False

    def get_provider(self, name: str) -> IconProvider:
        """
        Get a provider by name.

        Args:
            name: The provider name

        Returns:
            IconProvider: The requested provider

        Raises:
            ProviderNotFoundError: If the provider is not found
        """
        if name not in self._providers:
            raise ProviderNotFoundError(name, list(self._providers.keys()))
        return self._providers[name]

    def has_provider(self, name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            name: The provider name

        Returns:
            bool: True if the provider exists
        """
        return name in self._providers

    def list_providers(self) -> list[str]:
        """
        List all registered provider names.

        Returns:
            list[str]: Names of all registered providers
        """
        return list(self._providers.keys())

    def set_active_provider(self, name: str) -> None:
        """
        Set the active provider for icon generation.

        Args:
            name: The name of the provider to make active

        Raises:
            ProviderNotFoundError: If the provider is not found
        """
        if name not in self._providers:
            raise ProviderNotFoundError(name, list(self._providers.keys()))

        self._active_provider_name = name
        _logger.info("Set active icon provider: %s", name)

    def get_active_provider(self) -> IconProvider | None:
        """
        Get the currently active provider.

        Returns:
            IconProvider | None: The active provider, or None if no provider is set
        """
        if self._active_provider_name is None:
            return None
        return self._providers.get(self._active_provider_name)

    @property
    def active_provider_name(self) -> str | None:
        """Get the name of the active provider."""
        return self._active_provider_name

    def generate_icon(
        self,
        agent_name: str,
        role: str,
        tone: str = "default",
        *,
        provider_name: str | None = None,
    ) -> IconResult:
        """
        Generate an icon using the active or specified provider.

        Args:
            agent_name: The agent's name
            role: The agent's role
            tone: The desired tone/style
            provider_name: Optional specific provider to use

        Returns:
            IconResult: The result of icon generation

        Raises:
            ProviderNotFoundError: If no provider is available
            IconGenerationError: If icon generation fails
        """
        # Determine which provider to use
        if provider_name:
            provider = self.get_provider(provider_name)
        else:
            provider = self.get_active_provider()
            if provider is None:
                raise ProviderNotFoundError(
                    "active",
                    list(self._providers.keys()),
                    "No active icon provider. Register a provider first."
                )

        try:
            return provider.generate_icon(agent_name, role, tone)
        except IconProviderError:
            raise
        except Exception as e:
            _logger.error("Icon generation failed: %s", e)
            raise IconGenerationError(
                provider.name,
                str(e),
                agent_name=agent_name,
            )

    def get_all_capabilities(self) -> dict[str, IconProviderCapabilities]:
        """
        Get capabilities from all providers.

        Returns:
            dict[str, IconProviderCapabilities]: Map of provider name to capabilities
        """
        result: dict[str, IconProviderCapabilities] = {}
        for name, provider in self._providers.items():
            try:
                result[name] = provider.get_capabilities()
            except Exception as e:
                _logger.error("Failed to get capabilities from provider %s: %s", name, e)
        return result

    def get_provider_status(self) -> dict[str, ProviderStatus]:
        """
        Get status of all registered providers.

        Returns:
            dict[str, ProviderStatus]: Map of provider name to status
        """
        result: dict[str, ProviderStatus] = {}
        for name, provider in self._providers.items():
            try:
                result[name] = provider.get_status()
            except Exception as e:
                _logger.error("Failed to get status from provider %s: %s", name, e)
                result[name] = ProviderStatus.ERROR
        return result

    def clear(self) -> None:
        """Remove all registered providers."""
        self._providers.clear()
        self._active_provider_name = None
        _logger.info("Cleared all icon providers from registry")


# =============================================================================
# Configuration
# =============================================================================

# Configuration key for active provider selection
ICON_PROVIDER_CONFIG_KEY = "icon_provider.active"

# Default provider name
DEFAULT_PROVIDER_NAME = "default"


def get_active_provider_from_config(config: dict[str, Any] | None = None) -> str:
    """
    Get the active provider name from configuration.

    Args:
        config: Optional configuration dictionary

    Returns:
        str: The configured active provider name, or default
    """
    if config is None:
        return DEFAULT_PROVIDER_NAME

    return config.get(ICON_PROVIDER_CONFIG_KEY, DEFAULT_PROVIDER_NAME)


def set_active_provider_in_config(
    config: dict[str, Any],
    provider_name: str,
) -> dict[str, Any]:
    """
    Set the active provider name in configuration.

    Args:
        config: The configuration dictionary to update
        provider_name: The provider name to set as active

    Returns:
        dict[str, Any]: The updated configuration
    """
    config[ICON_PROVIDER_CONFIG_KEY] = provider_name
    return config


# =============================================================================
# Module-level convenience functions
# =============================================================================

# Global registry instance
_global_registry: IconProviderRegistry | None = None


def get_icon_registry() -> IconProviderRegistry:
    """
    Get the global IconProviderRegistry instance.

    Creates a new registry with a DefaultIconProvider if one doesn't exist.

    Returns:
        IconProviderRegistry: The global registry
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = IconProviderRegistry()
        _global_registry.register(DefaultIconProvider(), set_active=True)
    return _global_registry


def reset_icon_registry() -> None:
    """
    Reset the global IconProviderRegistry.

    This is useful for testing or when you need to reconfigure providers.
    """
    global _global_registry
    _global_registry = None


def register_icon_provider(
    provider: IconProvider,
    *,
    replace: bool = False,
    set_active: bool = False,
) -> None:
    """
    Register a provider in the global registry.

    Args:
        provider: The provider to register
        replace: If True, replace existing provider with same name
        set_active: If True, set this provider as active
    """
    get_icon_registry().register(provider, replace=replace, set_active=set_active)


def generate_icon(
    agent_name: str,
    role: str,
    tone: str = "default",
    *,
    provider_name: str | None = None,
) -> IconResult:
    """
    Generate an icon using the global registry.

    Args:
        agent_name: The agent's name
        role: The agent's role
        tone: The desired tone/style
        provider_name: Optional specific provider to use

    Returns:
        IconResult: The result of icon generation
    """
    return get_icon_registry().generate_icon(
        agent_name=agent_name,
        role=role,
        tone=tone,
        provider_name=provider_name,
    )


def get_default_icon_provider() -> DefaultIconProvider:
    """
    Get a new DefaultIconProvider instance.

    Returns:
        DefaultIconProvider: A new default provider instance
    """
    return DefaultIconProvider()


def configure_icon_provider_from_settings(settings: dict[str, Any]) -> None:
    """
    Configure the icon provider registry from settings.

    This reads the icon_provider.active setting and sets the active provider.

    Args:
        settings: The settings dictionary
    """
    registry = get_icon_registry()
    provider_name = get_active_provider_from_config(settings)

    if registry.has_provider(provider_name):
        registry.set_active_provider(provider_name)
        _logger.info("Configured active icon provider from settings: %s", provider_name)
    else:
        _logger.warning(
            "Configured icon provider '%s' not found, using default",
            provider_name
        )
