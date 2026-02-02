"""Tests for YAML config loading and validation."""

import os
import tempfile
import pytest

from repo_concierge.config import (
    load_allowlist_config,
    get_allowed_commands,
    ConfigValidationWarning,
)


class TestLoadAllowlistConfig:
    """Tests for load_allowlist_config function."""

    def test_missing_allowed_commands_key_returns_warning(self):
        """Config without 'allowed_commands' key produces a warning."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("some_other_key:\n  - item1\n")
            config_path = f.name

        try:
            config, warnings = load_allowlist_config(config_path, quiet=True)

            # Config should be loaded
            assert config is not None
            assert "some_other_key" in config

            # Should have a warning about missing 'allowed_commands'
            assert len(warnings) == 1
            assert "missing expected 'allowed_commands' key" in warnings[0].message
        finally:
            os.unlink(config_path)

    def test_valid_config_no_warnings(self):
        """Config with 'allowed_commands' key produces no warnings."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("allowed_commands:\n  - pip\n  - pytest\n")
            config_path = f.name

        try:
            config, warnings = load_allowlist_config(config_path, quiet=True)

            # Config should be loaded
            assert config is not None
            assert "allowed_commands" in config

            # No warnings expected
            assert len(warnings) == 0
        finally:
            os.unlink(config_path)

    def test_empty_config_returns_warning(self):
        """Empty config file produces a warning."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            config_path = f.name

        try:
            config, warnings = load_allowlist_config(config_path, quiet=True)

            # Config should be None (empty)
            assert config is None

            # Should have a warning about empty config
            assert len(warnings) == 1
            assert "Config file is empty" in warnings[0].message
        finally:
            os.unlink(config_path)

    def test_nonexistent_file_returns_warning(self):
        """Non-existent config file produces a warning."""
        config_path = "/tmp/nonexistent_config_12345.yaml"

        config, warnings = load_allowlist_config(config_path, quiet=True)

        # Config should be None
        assert config is None

        # Should have a warning about file not found
        assert len(warnings) == 1
        assert "Config file not found" in warnings[0].message

    def test_non_dict_config_returns_warning(self):
        """Config that's not a YAML dict produces a warning."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("just a string")
            config_path = f.name

        try:
            config, warnings = load_allowlist_config(config_path, quiet=True)

            # Config should be None
            assert config is None

            # Should have a warning about structure
            assert len(warnings) == 1
            assert "must be a YAML mapping" in warnings[0].message
        finally:
            os.unlink(config_path)

    def test_malformed_yaml_returns_warning(self):
        """Malformed YAML produces a warning."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("key: [unclosed bracket")
            config_path = f.name

        try:
            config, warnings = load_allowlist_config(config_path, quiet=True)

            # Config should be None
            assert config is None

            # Should have a warning about malformed YAML
            assert len(warnings) == 1
            assert "Malformed YAML" in warnings[0].message
        finally:
            os.unlink(config_path)


class TestGetAllowedCommands:
    """Tests for get_allowed_commands function."""

    def test_extracts_command_names_from_list(self):
        """Extracts command names from allowed_commands list."""
        config = {
            "allowed_commands": [
                {"name": "pip", "notes": "Package manager"},
                {"name": "pytest"},
            ]
        }

        commands = get_allowed_commands(config)

        assert commands == ["pip", "pytest"]

    def test_extracts_string_commands(self):
        """Extracts command names when they're plain strings."""
        config = {
            "allowed_commands": ["pip", "pytest", "python"]
        }

        commands = get_allowed_commands(config)

        assert commands == ["pip", "pytest", "python"]

    def test_handles_mixed_formats(self):
        """Handles mixed string and dict formats."""
        config = {
            "allowed_commands": [
                "pip",
                {"name": "pytest", "notes": "Test runner"},
                "git",
            ]
        }

        commands = get_allowed_commands(config)

        assert commands == ["pip", "pytest", "git"]

    def test_returns_empty_for_none_config(self):
        """Returns empty list when config is None."""
        commands = get_allowed_commands(None)

        assert commands == []

    def test_returns_empty_for_missing_key(self):
        """Returns empty list when 'allowed_commands' key is missing."""
        config = {"other_key": "value"}

        commands = get_allowed_commands(config)

        assert commands == []

    def test_returns_empty_for_non_list_value(self):
        """Returns empty list when allowed_commands is not a list."""
        config = {"allowed_commands": "not a list"}

        commands = get_allowed_commands(config)

        assert commands == []
