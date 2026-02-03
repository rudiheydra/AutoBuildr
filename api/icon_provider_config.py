"""
Icon Provider Configuration
===========================

Feature #217: Icon provider is configurable via settings

This module provides configuration management for the icon provider system:
1. ICON_PROVIDER environment variable or config setting
2. Default value: 'local_placeholder'
3. Future value: 'nano_banana' or other
4. Invalid provider falls back to placeholder
5. Configuration documented

The icon provider can be configured through:
- Environment variable: ICON_PROVIDER
- Settings file: .claude/settings.local.json -> icon_provider.active
- Programmatic API: set_icon_provider(), configure_icon_provider()

Configuration Priority (highest to lowest):
1. Programmatic override (if set)
2. Environment variable ICON_PROVIDER
3. Settings file icon_provider.active
4. Default value 'local_placeholder'

Example Configuration:
    # Environment variable
    export ICON_PROVIDER=nano_banana

    # Settings file (.claude/settings.local.json)
    {
        "icon_provider": {
            "active": "nano_banana"
        }
    }

    # Programmatic
    from api.icon_provider_config import set_icon_provider
    set_icon_provider("nano_banana")

Supported Providers:
- local_placeholder: Static icons from predefined mappings (default)
- nano_banana: Future AI-generated mascot icons
- (extensible for future providers)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from api.icon_provider import IconProviderRegistry

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Environment variable name for icon provider configuration
ENV_VAR_ICON_PROVIDER = "ICON_PROVIDER"

# Settings key for icon provider configuration
SETTINGS_ICON_PROVIDER_KEY = "icon_provider"
SETTINGS_ACTIVE_KEY = "active"

# Default provider name (local_placeholder)
DEFAULT_ICON_PROVIDER = "local_placeholder"

# Known provider names
KNOWN_PROVIDERS = frozenset({
    "local_placeholder",  # Default: static icons from predefined mappings
    "default",            # Alias for local_placeholder (from DefaultIconProvider)
    "nano_banana",        # Future: AI-generated mascot icons
})

# Provider name aliases (maps aliases to canonical names)
PROVIDER_ALIASES: dict[str, str] = {
    "default": "local_placeholder",
    "placeholder": "local_placeholder",
    "static": "local_placeholder",
    "local": "local_placeholder",
    "nanobanana": "nano_banana",
    "banana": "nano_banana",
}

# Valid configuration sources
VALID_CONFIG_SOURCES = frozenset({
    "environment",
    "settings",
    "programmatic",
    "default",
})


# =============================================================================
# Enums
# =============================================================================

class ConfigSource(str, Enum):
    """Source of icon provider configuration."""

    ENVIRONMENT = "environment"     # From ICON_PROVIDER env var
    SETTINGS = "settings"           # From settings.local.json
    PROGRAMMATIC = "programmatic"   # Set via API
    DEFAULT = "default"             # Default fallback


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class IconProviderConfigResult:
    """
    Result of icon provider configuration resolution.

    Attributes:
        provider_name: The resolved provider name
        source: Where the configuration came from
        original_value: The original value before normalization
        is_valid: Whether the provider is a known/registered provider
        fallback_used: Whether fallback to default was used
        timestamp: When the configuration was resolved
        metadata: Additional configuration metadata
    """

    provider_name: str
    source: ConfigSource
    original_value: str | None = None
    is_valid: bool = True
    fallback_used: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "provider_name": self.provider_name,
            "source": self.source.value,
            "original_value": self.original_value,
            "is_valid": self.is_valid,
            "fallback_used": self.fallback_used,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IconProviderConfigResult":
        """Create from dictionary."""
        source = data.get("source", "default")
        if isinstance(source, str):
            try:
                source = ConfigSource(source)
            except ValueError:
                source = ConfigSource.DEFAULT

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return cls(
            provider_name=data.get("provider_name", DEFAULT_ICON_PROVIDER),
            source=source,
            original_value=data.get("original_value"),
            is_valid=data.get("is_valid", True),
            fallback_used=data.get("fallback_used", False),
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
        )


@dataclass
class IconProviderSettings:
    """
    Icon provider settings from configuration file.

    Feature #217: Icon provider is configurable via settings

    Attributes:
        active: The active provider name
        fallback: Fallback provider if active is unavailable
        auto_register: Whether to auto-register unknown providers
        cache_enabled: Whether icon caching is enabled
        metadata: Additional provider-specific settings
    """

    active: str = DEFAULT_ICON_PROVIDER
    fallback: str = DEFAULT_ICON_PROVIDER
    auto_register: bool = False
    cache_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "active": self.active,
            "fallback": self.fallback,
            "auto_register": self.auto_register,
            "cache_enabled": self.cache_enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "IconProviderSettings":
        """Create from dictionary."""
        if data is None:
            return cls()

        return cls(
            active=data.get("active", DEFAULT_ICON_PROVIDER),
            fallback=data.get("fallback", DEFAULT_ICON_PROVIDER),
            auto_register=data.get("auto_register", False),
            cache_enabled=data.get("cache_enabled", True),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Module State
# =============================================================================

# Programmatic override (takes highest priority)
_programmatic_provider: str | None = None


# =============================================================================
# Core Configuration Functions
# =============================================================================

def normalize_provider_name(name: str | None) -> str:
    """
    Normalize a provider name to its canonical form.

    Args:
        name: The provider name to normalize

    Returns:
        The normalized provider name
    """
    if name is None:
        return DEFAULT_ICON_PROVIDER

    # Convert to lowercase and strip whitespace
    normalized = name.lower().strip()

    # Check for empty string
    if not normalized:
        return DEFAULT_ICON_PROVIDER

    # Check for aliases
    if normalized in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[normalized]

    return normalized


def is_valid_provider_name(name: str) -> bool:
    """
    Check if a provider name is valid (known or registered).

    Args:
        name: The provider name to check

    Returns:
        True if the provider is known
    """
    normalized = normalize_provider_name(name)
    return normalized in KNOWN_PROVIDERS


def get_env_icon_provider() -> str | None:
    """
    Get icon provider from environment variable.

    Feature #217 Step 1: ICON_PROVIDER environment variable or config setting

    Returns:
        The provider name from env var, or None if not set
    """
    value = os.environ.get(ENV_VAR_ICON_PROVIDER)
    if value is not None:
        value = value.strip()
        if value:
            return value
    return None


def get_settings_icon_provider(settings: dict[str, Any] | None = None) -> str | None:
    """
    Get icon provider from settings dictionary.

    Feature #217 Step 1: ICON_PROVIDER environment variable or config setting

    Args:
        settings: Settings dictionary (if None, returns None)

    Returns:
        The provider name from settings, or None if not found
    """
    if settings is None:
        return None

    # Check for icon_provider.active
    icon_provider_section = settings.get(SETTINGS_ICON_PROVIDER_KEY)
    if isinstance(icon_provider_section, dict):
        active = icon_provider_section.get(SETTINGS_ACTIVE_KEY)
        if isinstance(active, str) and active.strip():
            return active.strip()

    # Also support legacy flat key
    if isinstance(icon_provider_section, str) and icon_provider_section.strip():
        return icon_provider_section.strip()

    return None


def resolve_icon_provider(
    settings: dict[str, Any] | None = None,
    registry: "IconProviderRegistry | None" = None,
) -> IconProviderConfigResult:
    """
    Resolve the active icon provider from all configuration sources.

    Feature #217: Icon provider is configurable via settings

    Resolution priority:
    1. Programmatic override (if set)
    2. Environment variable ICON_PROVIDER
    3. Settings file icon_provider.active
    4. Default value 'local_placeholder'

    Args:
        settings: Optional settings dictionary
        registry: Optional provider registry to validate against

    Returns:
        IconProviderConfigResult with resolved provider and source
    """
    original_value: str | None = None
    source: ConfigSource = ConfigSource.DEFAULT

    # Step 1: Check programmatic override
    if _programmatic_provider is not None:
        original_value = _programmatic_provider
        source = ConfigSource.PROGRAMMATIC
        _logger.debug("Using programmatic icon provider override: %s", original_value)

    # Step 2: Check environment variable
    elif (env_value := get_env_icon_provider()) is not None:
        original_value = env_value
        source = ConfigSource.ENVIRONMENT
        _logger.debug("Using icon provider from environment: %s", original_value)

    # Step 3: Check settings
    elif (settings_value := get_settings_icon_provider(settings)) is not None:
        original_value = settings_value
        source = ConfigSource.SETTINGS
        _logger.debug("Using icon provider from settings: %s", original_value)

    # Step 4: Use default
    if original_value is None:
        original_value = DEFAULT_ICON_PROVIDER
        source = ConfigSource.DEFAULT
        _logger.debug("Using default icon provider: %s", original_value)

    # Normalize the provider name
    provider_name = normalize_provider_name(original_value)

    # Check if provider is valid/registered
    is_valid = is_valid_provider_name(provider_name)
    if registry is not None:
        is_valid = registry.has_provider(provider_name)

    # Feature #217 Step 4: Invalid provider falls back to placeholder
    fallback_used = False
    if not is_valid:
        _logger.warning(
            "Icon provider '%s' (from %s) not found, falling back to '%s'",
            provider_name, source.value, DEFAULT_ICON_PROVIDER
        )
        fallback_used = True
        provider_name = DEFAULT_ICON_PROVIDER

    return IconProviderConfigResult(
        provider_name=provider_name,
        source=source,
        original_value=original_value,
        is_valid=not fallback_used,
        fallback_used=fallback_used,
        metadata={
            "known_providers": list(KNOWN_PROVIDERS),
            "env_var": ENV_VAR_ICON_PROVIDER,
            "settings_key": f"{SETTINGS_ICON_PROVIDER_KEY}.{SETTINGS_ACTIVE_KEY}",
        },
    )


def get_icon_provider(
    settings: dict[str, Any] | None = None,
) -> str:
    """
    Get the configured icon provider name.

    This is a convenience function that returns just the provider name.

    Feature #217: Icon provider is configurable via settings

    Args:
        settings: Optional settings dictionary

    Returns:
        The resolved provider name (never None)
    """
    result = resolve_icon_provider(settings=settings)
    return result.provider_name


def set_icon_provider(provider_name: str | None) -> IconProviderConfigResult:
    """
    Set the icon provider programmatically.

    This sets a programmatic override that takes precedence over
    environment variables and settings.

    Feature #217: Icon provider is configurable via settings

    Args:
        provider_name: The provider name to set, or None to clear override

    Returns:
        IconProviderConfigResult with the new configuration
    """
    global _programmatic_provider

    if provider_name is None:
        _programmatic_provider = None
        _logger.info("Cleared programmatic icon provider override")
        return resolve_icon_provider()

    normalized = normalize_provider_name(provider_name)
    is_valid = is_valid_provider_name(normalized)

    if is_valid:
        _programmatic_provider = normalized
        _logger.info("Set programmatic icon provider: %s", normalized)
    else:
        _logger.warning(
            "Icon provider '%s' not known, falling back to '%s'",
            provider_name, DEFAULT_ICON_PROVIDER
        )
        _programmatic_provider = DEFAULT_ICON_PROVIDER

    return resolve_icon_provider()


def clear_icon_provider_override() -> None:
    """
    Clear any programmatic icon provider override.

    After clearing, configuration will be resolved from environment
    variables and settings as normal.
    """
    global _programmatic_provider
    _programmatic_provider = None
    _logger.info("Cleared icon provider override")


def get_icon_provider_override() -> str | None:
    """
    Get the current programmatic override, if any.

    Returns:
        The override provider name, or None if not set
    """
    return _programmatic_provider


# =============================================================================
# Settings File Functions
# =============================================================================

def load_icon_provider_settings(settings_path: Path | str | None = None) -> IconProviderSettings:
    """
    Load icon provider settings from settings file.

    Args:
        settings_path: Path to settings file (uses default if None)

    Returns:
        IconProviderSettings parsed from file
    """
    import json

    if settings_path is None:
        settings_path = Path(".claude/settings.local.json")
    else:
        settings_path = Path(settings_path)

    if not settings_path.exists():
        return IconProviderSettings()

    try:
        content = settings_path.read_text(encoding="utf-8")
        data = json.loads(content)
        icon_provider_section = data.get(SETTINGS_ICON_PROVIDER_KEY, {})
        return IconProviderSettings.from_dict(icon_provider_section)
    except (json.JSONDecodeError, OSError) as e:
        _logger.warning("Failed to load icon provider settings: %s", e)
        return IconProviderSettings()


def save_icon_provider_settings(
    provider_name: str,
    settings_path: Path | str | None = None,
) -> bool:
    """
    Save icon provider settings to settings file.

    Args:
        provider_name: The provider name to save
        settings_path: Path to settings file (uses default if None)

    Returns:
        True if saved successfully, False otherwise
    """
    import json

    if settings_path is None:
        settings_path = Path(".claude/settings.local.json")
    else:
        settings_path = Path(settings_path)

    # Ensure directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings
    existing: dict[str, Any] = {}
    if settings_path.exists():
        try:
            content = settings_path.read_text(encoding="utf-8")
            existing = json.loads(content)
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Update icon_provider section
    if SETTINGS_ICON_PROVIDER_KEY not in existing:
        existing[SETTINGS_ICON_PROVIDER_KEY] = {}

    existing[SETTINGS_ICON_PROVIDER_KEY][SETTINGS_ACTIVE_KEY] = provider_name

    # Write settings
    try:
        content = json.dumps(existing, indent=2, sort_keys=True) + "\n"
        settings_path.write_text(content, encoding="utf-8")
        _logger.info("Saved icon provider '%s' to settings", provider_name)
        return True
    except OSError as e:
        _logger.error("Failed to save icon provider settings: %s", e)
        return False


# =============================================================================
# Configuration Validation
# =============================================================================

def validate_icon_provider_config(
    provider_name: str,
    registry: "IconProviderRegistry | None" = None,
) -> tuple[bool, str | None]:
    """
    Validate an icon provider configuration.

    Args:
        provider_name: The provider name to validate
        registry: Optional registry to validate against

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not provider_name or not isinstance(provider_name, str):
        return False, "Provider name must be a non-empty string"

    normalized = normalize_provider_name(provider_name)

    # Check against known providers
    if normalized not in KNOWN_PROVIDERS:
        # If registry provided, check registered providers
        if registry is not None and not registry.has_provider(normalized):
            return False, f"Provider '{normalized}' is not known or registered"
        elif registry is None:
            # Without registry, just warn but allow
            _logger.warning("Provider '%s' is not a known provider", normalized)

    return True, None


def get_available_providers(
    registry: "IconProviderRegistry | None" = None,
) -> list[str]:
    """
    Get list of available icon providers.

    Args:
        registry: Optional registry to get registered providers

    Returns:
        List of available provider names
    """
    providers: set[str] = set(KNOWN_PROVIDERS)

    if registry is not None:
        providers.update(registry.list_providers())

    return sorted(providers)


def get_provider_info(provider_name: str) -> dict[str, Any]:
    """
    Get information about a specific provider.

    Args:
        provider_name: The provider name

    Returns:
        Dictionary with provider information
    """
    normalized = normalize_provider_name(provider_name)

    info: dict[str, Any] = {
        "name": normalized,
        "original_name": provider_name,
        "is_known": normalized in KNOWN_PROVIDERS,
        "aliases": [
            alias for alias, target in PROVIDER_ALIASES.items()
            if target == normalized
        ],
    }

    # Add provider-specific descriptions
    descriptions: dict[str, str] = {
        "local_placeholder": "Static icons from predefined role-to-icon mappings",
        "nano_banana": "AI-generated mascot icons (future)",
    }

    if normalized in descriptions:
        info["description"] = descriptions[normalized]

    return info


# =============================================================================
# Module-level Configuration
# =============================================================================

def configure_icon_provider(
    settings: dict[str, Any] | None = None,
    registry: "IconProviderRegistry | None" = None,
) -> IconProviderConfigResult:
    """
    Configure the icon provider system.

    This function:
    1. Resolves the active provider from all sources
    2. Validates the provider
    3. Falls back to default if invalid
    4. Optionally configures the registry

    Feature #217: Icon provider is configurable via settings

    Args:
        settings: Optional settings dictionary
        registry: Optional registry to configure

    Returns:
        IconProviderConfigResult with configuration details
    """
    result = resolve_icon_provider(settings=settings, registry=registry)

    # If registry provided, set the active provider
    if registry is not None and registry.has_provider(result.provider_name):
        try:
            registry.set_active_provider(result.provider_name)
            _logger.info(
                "Configured icon provider registry with provider: %s (source: %s)",
                result.provider_name, result.source.value
            )
        except Exception as e:
            _logger.error("Failed to set active provider: %s", e)

    return result


def get_icon_provider_config_documentation() -> str:
    """
    Get documentation for icon provider configuration.

    Feature #217 Step 5: Configuration documented

    Returns:
        Documentation string
    """
    return """
Icon Provider Configuration
===========================

The icon provider determines how icons are generated for agents in the UI.

Configuration Methods (in priority order):
------------------------------------------

1. PROGRAMMATIC API
   Set provider via code:

   ```python
   from api.icon_provider_config import set_icon_provider
   set_icon_provider("local_placeholder")
   ```

2. ENVIRONMENT VARIABLE
   Set the ICON_PROVIDER environment variable:

   ```bash
   export ICON_PROVIDER=local_placeholder
   ```

3. SETTINGS FILE
   Add to .claude/settings.local.json:

   ```json
   {
       "icon_provider": {
           "active": "local_placeholder"
       }
   }
   ```

4. DEFAULT
   If no configuration is found, defaults to: local_placeholder

Available Providers:
-------------------

- local_placeholder (default)
  Static icons from predefined role-to-icon mappings.
  Fast, no external dependencies.

- nano_banana (future)
  AI-generated mascot icons using Nano Banana style.
  Requires API configuration.

Fallback Behavior:
-----------------
If an invalid or unknown provider is configured, the system automatically
falls back to the default provider (local_placeholder) and logs a warning.

Example Configurations:
----------------------

# Using environment variable
export ICON_PROVIDER=local_placeholder

# Using settings file
echo '{"icon_provider": {"active": "local_placeholder"}}' > .claude/settings.local.json

# Using API
from api.icon_provider_config import set_icon_provider
result = set_icon_provider("local_placeholder")
print(f"Provider: {result.provider_name}, Source: {result.source.value}")
""".strip()
