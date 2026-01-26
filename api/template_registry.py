"""
Template Registry Module
========================

Loads and manages skill templates from the prompts/ directory.

Templates are markdown files containing agent instructions. Each template
can include YAML front matter to specify metadata like task_type,
required_tools, and default budget values.

Example template structure:
```markdown
---
task_type: coding
required_tools:
  - feature_get_by_id
  - feature_mark_passing
default_max_turns: 100
default_timeout_seconds: 3600
---
## YOUR ROLE - CODING AGENT

You are continuing work on a long-running autonomous development task.
...
```

The registry supports:
- Automatic scanning of prompts/ directory
- Template metadata parsing from YAML front matter
- Variable interpolation in templates
- Caching of compiled templates for performance
- Graceful fallback for missing templates
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Try to import yaml, fall back to a simple parser if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# Module logger
_logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class TemplateError(Exception):
    """Base exception for template errors."""
    pass


class TemplateNotFoundError(TemplateError):
    """Raised when a requested template is not found."""

    def __init__(self, identifier: str, message: str | None = None):
        self.identifier = identifier
        if message is None:
            message = f"Template not found: {identifier}"
        super().__init__(message)


class TemplateParseError(TemplateError):
    """Raised when a template cannot be parsed."""

    def __init__(self, path: str, message: str):
        self.path = path
        super().__init__(f"Failed to parse template '{path}': {message}")


class InterpolationError(TemplateError):
    """Raised when variable interpolation fails."""

    def __init__(self, variable: str, message: str | None = None):
        self.variable = variable
        if message is None:
            message = f"Missing interpolation variable: {variable}"
        super().__init__(message)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TemplateMetadata:
    """
    Metadata extracted from template front matter.

    Attributes:
        task_type: The task type this template is for (e.g., "coding", "testing")
        required_tools: List of tool names required by this template
        default_max_turns: Default execution budget (turns)
        default_timeout_seconds: Default timeout in seconds
        name: Human-readable name for the template
        description: Description of what the template does
        icon: Optional emoji or icon identifier
        variables: List of expected interpolation variables
        extra: Any additional metadata from front matter
    """
    task_type: str | None = None
    required_tools: list[str] = field(default_factory=list)
    default_max_turns: int | None = None
    default_timeout_seconds: int | None = None
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    variables: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Template:
    """
    A loaded template with content and metadata.

    Attributes:
        path: Absolute path to the template file
        content: Raw content of the template (without front matter)
        metadata: Parsed metadata from front matter
        content_hash: SHA256 hash of content for cache invalidation
        loaded_at: When the template was loaded
    """
    path: Path
    content: str
    metadata: TemplateMetadata
    content_hash: str
    loaded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert template to dictionary for serialization."""
        return {
            "path": str(self.path),
            "content_hash": self.content_hash,
            "loaded_at": self.loaded_at.isoformat(),
            "metadata": {
                "task_type": self.metadata.task_type,
                "required_tools": self.metadata.required_tools,
                "default_max_turns": self.metadata.default_max_turns,
                "default_timeout_seconds": self.metadata.default_timeout_seconds,
                "name": self.metadata.name,
                "description": self.metadata.description,
                "icon": self.metadata.icon,
                "variables": self.metadata.variables,
                "extra": self.metadata.extra,
            }
        }


# =============================================================================
# YAML Front Matter Parsing
# =============================================================================

# Regex to match YAML front matter between --- markers
# Allows empty front matter (---\n---\n) or content between markers
FRONT_MATTER_PATTERN = re.compile(
    r'^---\s*\n(.*?)\n?---\s*\n',
    re.DOTALL
)


def _simple_yaml_parse(content: str) -> dict[str, Any]:
    """
    Simple YAML-like parser for front matter when PyYAML is not available.

    Handles basic key: value pairs and simple lists.
    """
    result: dict[str, Any] = {}
    lines = content.split('\n')
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue

        # Check for list item
        if line.strip().startswith('- '):
            if current_list is not None:
                current_list.append(line.strip()[2:].strip())
            continue

        # If we were building a list, save it
        if current_list is not None and current_key:
            result[current_key] = current_list
            current_list = None
            current_key = None

        # Check for key: value
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                # Direct value
                # Try to parse as int
                try:
                    result[key] = int(value)
                except ValueError:
                    # Try to parse as bool
                    if value.lower() in ('true', 'yes'):
                        result[key] = True
                    elif value.lower() in ('false', 'no'):
                        result[key] = False
                    else:
                        result[key] = value
            else:
                # Start of a list
                current_key = key
                current_list = []

    # Don't forget any trailing list
    if current_list is not None and current_key:
        result[current_key] = current_list

    return result


def parse_front_matter(content: str) -> tuple[TemplateMetadata, str]:
    """
    Parse YAML front matter from template content.

    Args:
        content: Full template content including front matter

    Returns:
        Tuple of (metadata, content_without_front_matter)
    """
    match = FRONT_MATTER_PATTERN.match(content)

    if not match:
        # No front matter found
        return TemplateMetadata(), content

    front_matter_text = match.group(1)
    content_without_fm = content[match.end():]

    # Parse the YAML
    try:
        if HAS_YAML:
            data = yaml.safe_load(front_matter_text) or {}
        else:
            data = _simple_yaml_parse(front_matter_text)
    except Exception as e:
        _logger.warning("Failed to parse front matter: %s", e)
        return TemplateMetadata(), content

    if not isinstance(data, dict):
        return TemplateMetadata(), content

    # Extract known fields
    metadata = TemplateMetadata(
        task_type=data.pop('task_type', None),
        required_tools=data.pop('required_tools', []) or [],
        default_max_turns=data.pop('default_max_turns', None),
        default_timeout_seconds=data.pop('default_timeout_seconds', None),
        name=data.pop('name', None),
        description=data.pop('description', None),
        icon=data.pop('icon', None),
        variables=data.pop('variables', []) or [],
        extra=data,  # Any remaining fields
    )

    return metadata, content_without_fm


# =============================================================================
# Variable Interpolation
# =============================================================================

# Pattern for template variables: {{variable_name}} or {variable_name}
INTERPOLATION_PATTERN = re.compile(r'\{\{?\s*(\w+)\s*\}?\}')


def interpolate(template_content: str, variables: dict[str, Any], *, strict: bool = False) -> str:
    """
    Interpolate variables into template content.

    Variables can be referenced as {{variable}} or {variable}.

    Args:
        template_content: Template content with variable placeholders
        variables: Dictionary of variable name -> value
        strict: If True, raise InterpolationError for missing variables.
                If False, leave missing variables as-is.

    Returns:
        Template content with variables substituted

    Raises:
        InterpolationError: If strict=True and a variable is missing
    """
    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in variables:
            return str(variables[var_name])
        elif strict:
            raise InterpolationError(var_name)
        else:
            # Leave as-is
            return match.group(0)

    return INTERPOLATION_PATTERN.sub(replace_var, template_content)


def find_variables(template_content: str) -> list[str]:
    """
    Find all variable names in a template.

    Args:
        template_content: Template content to scan

    Returns:
        List of unique variable names found
    """
    matches = INTERPOLATION_PATTERN.findall(template_content)
    return list(dict.fromkeys(matches))  # Preserve order, remove duplicates


# =============================================================================
# Template Registry
# =============================================================================

class TemplateRegistry:
    """
    Registry for loading and managing skill templates.

    The registry scans a prompts/ directory for template files,
    parses their metadata, and provides access by task_type or filename.

    Features:
    - Lazy loading of template content
    - Caching with file modification detection
    - Indexing by task_type
    - Variable interpolation
    - Graceful fallback for missing templates

    Example:
        ```python
        registry = TemplateRegistry("/path/to/prompts")
        registry.scan()

        # Get template by task_type
        template = registry.get_template(task_type="coding")

        # Interpolate variables
        content = registry.interpolate(
            template,
            {"feature_id": 42, "project_name": "MyApp"}
        )
        ```
    """

    def __init__(
        self,
        prompts_dir: str | Path,
        *,
        auto_scan: bool = True,
        cache_enabled: bool = True,
    ):
        """
        Initialize the template registry.

        Args:
            prompts_dir: Path to the prompts directory
            auto_scan: If True, scan directory on initialization
            cache_enabled: If True, cache loaded templates
        """
        self._prompts_dir = Path(prompts_dir).resolve()
        self._cache_enabled = cache_enabled

        # Thread-safe cache
        self._lock = threading.RLock()

        # Cache: path -> Template
        self._templates: dict[Path, Template] = {}

        # Index: task_type -> list of template paths
        self._by_task_type: dict[str, list[Path]] = {}

        # Index: filename (without extension) -> path
        self._by_name: dict[str, Path] = {}

        # File modification times for cache invalidation
        self._mtimes: dict[Path, float] = {}

        # Fallback template (used when requested template not found)
        self._fallback_template: Template | None = None

        if auto_scan:
            self.scan()

    @property
    def prompts_dir(self) -> Path:
        """Get the prompts directory path."""
        return self._prompts_dir

    def scan(self) -> int:
        """
        Scan the prompts directory for templates.

        Returns:
            Number of templates found
        """
        if not self._prompts_dir.exists():
            _logger.warning("Prompts directory does not exist: %s", self._prompts_dir)
            return 0

        with self._lock:
            # Clear indexes (but keep cache for unchanged files)
            self._by_task_type.clear()
            self._by_name.clear()

            found = 0

            for path in self._prompts_dir.glob("*.md"):
                if path.name.startswith('.'):
                    continue

                try:
                    template = self._load_template(path)
                    self._index_template(path, template)
                    found += 1
                except Exception as e:
                    _logger.warning("Failed to load template %s: %s", path, e)

            _logger.info(
                "Scanned %s: found %d templates, %d task types indexed",
                self._prompts_dir,
                found,
                len(self._by_task_type),
            )

            return found

    def _load_template(self, path: Path) -> Template:
        """
        Load a template from file.

        Uses cache if enabled and file hasn't changed.
        """
        path = path.resolve()
        mtime = path.stat().st_mtime

        # Check cache
        if self._cache_enabled and path in self._templates:
            if self._mtimes.get(path) == mtime:
                return self._templates[path]

        # Load and parse
        content = path.read_text(encoding='utf-8')
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        metadata, clean_content = parse_front_matter(content)

        # Auto-detect variables if not specified in metadata
        if not metadata.variables:
            metadata.variables = find_variables(clean_content)

        # Infer task_type from filename if not specified
        if metadata.task_type is None:
            stem = path.stem.lower()
            if 'coding' in stem:
                metadata.task_type = 'coding'
            elif 'testing' in stem:
                metadata.task_type = 'testing'
            elif 'init' in stem:
                metadata.task_type = 'documentation'  # initializer is setup docs

        template = Template(
            path=path,
            content=clean_content,
            metadata=metadata,
            content_hash=content_hash,
            loaded_at=datetime.utcnow(),
        )

        # Update cache
        if self._cache_enabled:
            self._templates[path] = template
            self._mtimes[path] = mtime

        return template

    def _index_template(self, path: Path, template: Template) -> None:
        """Add a template to the indexes."""
        # Index by name (filename without extension)
        name = path.stem.lower()
        self._by_name[name] = path

        # Also index without _prompt suffix
        if name.endswith('_prompt'):
            short_name = name[:-7]
            self._by_name[short_name] = path

        # Index by task_type
        if template.metadata.task_type:
            task_type = template.metadata.task_type.lower()
            if task_type not in self._by_task_type:
                self._by_task_type[task_type] = []
            self._by_task_type[task_type].append(path)

    def get_template(
        self,
        *,
        task_type: str | None = None,
        name: str | None = None,
        use_fallback: bool = True,
    ) -> Template | None:
        """
        Get a template by task_type or name.

        Args:
            task_type: Task type to look up (e.g., "coding", "testing")
            name: Template filename (without extension)
            use_fallback: If True, return fallback template when not found

        Returns:
            Template if found, None if not found and no fallback

        Raises:
            TemplateNotFoundError: If not found and use_fallback=False
        """
        with self._lock:
            path: Path | None = None

            # Try by name first
            if name:
                name_lower = name.lower()
                path = self._by_name.get(name_lower)

            # Try by task_type
            if path is None and task_type:
                task_type_lower = task_type.lower()
                paths = self._by_task_type.get(task_type_lower, [])
                if paths:
                    path = paths[0]  # First match

            if path:
                return self._load_template(path)

            # Handle not found
            if use_fallback and self._fallback_template:
                return self._fallback_template

            if not use_fallback:
                identifier = name or task_type or "unknown"
                raise TemplateNotFoundError(identifier)

            return None

    def get_template_by_path(self, path: str | Path) -> Template:
        """
        Load a template directly by file path.

        Args:
            path: Path to template file

        Returns:
            Loaded template

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")

        return self._load_template(path)

    def set_fallback_template(self, template: Template | None) -> None:
        """
        Set the fallback template to use when a requested template is not found.

        Args:
            template: Template to use as fallback, or None to disable
        """
        with self._lock:
            self._fallback_template = template

    def interpolate(
        self,
        template: Template | str,
        variables: dict[str, Any],
        *,
        strict: bool = False,
    ) -> str:
        """
        Interpolate variables into a template.

        Args:
            template: Template object or content string
            variables: Variables to interpolate
            strict: If True, raise error on missing variables

        Returns:
            Interpolated content
        """
        content = template.content if isinstance(template, Template) else template
        return interpolate(content, variables, strict=strict)

    def list_templates(self) -> list[dict[str, Any]]:
        """
        List all loaded templates with their metadata.

        Returns:
            List of template info dictionaries
        """
        with self._lock:
            result = []
            for path in self._templates:
                template = self._templates[path]
                info = template.to_dict()
                info["name"] = path.stem
                result.append(info)
            return result

    def list_task_types(self) -> list[str]:
        """
        Get all task types that have templates.

        Returns:
            List of task type strings
        """
        with self._lock:
            return list(self._by_task_type.keys())

    def get_templates_for_task_type(self, task_type: str) -> list[Template]:
        """
        Get all templates for a specific task type.

        Args:
            task_type: Task type to filter by

        Returns:
            List of templates
        """
        with self._lock:
            task_type_lower = task_type.lower()
            paths = self._by_task_type.get(task_type_lower, [])
            return [self._load_template(p) for p in paths]

    def clear_cache(self) -> None:
        """Clear the template cache."""
        with self._lock:
            self._templates.clear()
            self._mtimes.clear()

    def refresh(self) -> int:
        """
        Refresh the registry by rescanning the prompts directory.

        This clears the cache and rescans.

        Returns:
            Number of templates found
        """
        self.clear_cache()
        return self.scan()


# =============================================================================
# Module-level Singleton
# =============================================================================

_default_registry: TemplateRegistry | None = None
_registry_lock = threading.Lock()


def get_template_registry(prompts_dir: str | Path | None = None) -> TemplateRegistry:
    """
    Get or create the default template registry.

    Args:
        prompts_dir: Path to prompts directory (only used on first call)

    Returns:
        The default TemplateRegistry instance
    """
    global _default_registry

    with _registry_lock:
        if _default_registry is None:
            if prompts_dir is None:
                # Default to prompts/ in current directory or project root
                prompts_dir = Path.cwd() / "prompts"
                if not prompts_dir.exists():
                    # Try common locations
                    for parent in Path.cwd().parents:
                        candidate = parent / "prompts"
                        if candidate.exists():
                            prompts_dir = candidate
                            break

            _default_registry = TemplateRegistry(prompts_dir)

        return _default_registry


def reset_template_registry() -> None:
    """Reset the default template registry (for testing)."""
    global _default_registry

    with _registry_lock:
        _default_registry = None
