"""Configuration file loading and validation for Repo Concierge."""

import sys
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class ConfigValidationWarning:
    """Represents a warning from config validation."""

    def __init__(self, message: str):
        self.message = message

    def __str__(self) -> str:
        return self.message


def load_allowlist_config(
    config_path: str,
    verbose: bool = False,
    quiet: bool = False,
) -> tuple[Optional[Dict[str, Any]], List[ConfigValidationWarning]]:
    """Load and validate an allowlist YAML configuration file.

    Args:
        config_path: Path to the YAML config file.
        verbose: If True, print detailed warnings.
        quiet: If True, suppress all output except errors.

    Returns:
        A tuple of (config_dict, warnings).
        - config_dict: The parsed config, or None if loading failed.
        - warnings: List of validation warnings encountered.
    """
    warnings: List[ConfigValidationWarning] = []

    # Check if yaml is available
    if yaml is None:
        warning = ConfigValidationWarning(
            f"Warning: PyYAML not installed. Cannot load config file: {config_path}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings

    # Try to load the file
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        warning = ConfigValidationWarning(
            f"Warning: Config file not found: {config_path}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings
    except yaml.YAMLError as e:
        warning = ConfigValidationWarning(
            f"Warning: Malformed YAML in config file {config_path}: {e}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings
    except PermissionError:
        warning = ConfigValidationWarning(
            f"Warning: Permission denied reading config file: {config_path}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings
    except OSError as e:
        warning = ConfigValidationWarning(
            f"Warning: Error reading config file {config_path}: {e}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings

    # Validate the config structure
    if config is None:
        warning = ConfigValidationWarning(
            f"Warning: Config file is empty: {config_path}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings

    if not isinstance(config, dict):
        warning = ConfigValidationWarning(
            f"Warning: Config file must be a YAML mapping (object), got {type(config).__name__}: {config_path}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)
        return None, warnings

    # Check for expected 'allowed_commands' key
    if "allowed_commands" not in config:
        warning = ConfigValidationWarning(
            f"Warning: Config file missing expected 'allowed_commands' key: {config_path}"
        )
        warnings.append(warning)
        if not quiet:
            print(warning.message, file=sys.stderr)

    return config, warnings


def get_allowed_commands(config: Optional[Dict[str, Any]]) -> List[str]:
    """Extract the list of allowed command names from a config.

    Args:
        config: Parsed config dict (or None if loading failed).

    Returns:
        List of allowed command names.
    """
    if config is None:
        return []

    allowed_commands = config.get("allowed_commands", [])
    if not isinstance(allowed_commands, list):
        return []

    # Extract command names (each item can be a string or a dict with 'name' key)
    names: List[str] = []
    for item in allowed_commands:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and "name" in item:
            names.append(item["name"])

    return names
