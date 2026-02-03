"""
.claude Directory Scaffolding
==============================

Feature #199: .claude directory scaffolding creates standard structure

This module provides functionality to scaffold the standard .claude directory
structure that Claude Code expects in project repositories. The scaffolding
creates the following structure:

    .claude/                    # Root directory for Claude Code configuration
    .claude/agents/             # Parent directory for all agent definitions
    .claude/agents/generated/   # Auto-generated agents from Octo/Maestro
    .claude/agents/manual/      # Manually-created agent definitions
    .claude/skills/             # Custom skills (Phase 2)
    .claude/commands/           # Custom commands (Phase 2)

The scaffolding is idempotent - it can be run multiple times safely without
destroying existing content. Each directory is created with standard permissions
(0755) and will only be created if it doesn't already exist.

Usage:
    from api.scaffolding import scaffold_claude_directory, ClaudeDirectoryScaffold

    # Simple usage
    result = scaffold_claude_directory(project_dir)

    # With custom options
    scaffold = ClaudeDirectoryScaffold(project_dir)
    result = scaffold.create_structure()

    # Check what would be created without actually creating
    preview = scaffold.preview_structure()
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Root directory name
CLAUDE_ROOT_DIR = ".claude"

# Standard subdirectories relative to .claude/
STANDARD_SUBDIRS: tuple[str, ...] = (
    "agents/generated",  # Auto-generated agents from Octo/Maestro
    "agents/manual",     # Manually-created agent definitions
    "skills",            # Custom skills (Phase 2)
    "commands",          # Custom commands (Phase 2)
)

# Default directory permissions (rwxr-xr-x)
DEFAULT_DIR_PERMISSIONS = 0o755

# Phase markers for documentation purposes
PHASE_1_DIRS = frozenset({"agents/generated", "agents/manual"})
PHASE_2_DIRS = frozenset({"skills", "commands"})


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DirectoryStatus:
    """
    Status of a single directory in the scaffold.

    Attributes:
        path: Absolute path to the directory
        relative_path: Path relative to .claude/
        existed: Whether the directory existed before scaffolding
        created: Whether the directory was created by scaffolding
        error: Error message if creation failed
        phase: Which phase this directory belongs to (1 or 2)
    """
    path: Path
    relative_path: str
    existed: bool = False
    created: bool = False
    error: str | None = None
    phase: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": str(self.path),
            "relative_path": self.relative_path,
            "existed": self.existed,
            "created": self.created,
            "error": self.error,
            "phase": self.phase,
        }


@dataclass
class ScaffoldResult:
    """
    Result of scaffolding the .claude directory structure.

    Attributes:
        success: Whether all directories were created successfully
        project_dir: The project root directory
        claude_root: Path to the .claude/ directory
        directories: Status of each directory
        directories_created: Number of directories created
        directories_existed: Number of directories that already existed
        directories_failed: Number of directories that failed to create
    """
    success: bool
    project_dir: Path
    claude_root: Path
    directories: list[DirectoryStatus] = field(default_factory=list)
    directories_created: int = 0
    directories_existed: int = 0
    directories_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "project_dir": str(self.project_dir),
            "claude_root": str(self.claude_root),
            "directories": [d.to_dict() for d in self.directories],
            "directories_created": self.directories_created,
            "directories_existed": self.directories_existed,
            "directories_failed": self.directories_failed,
        }

    def get_created_paths(self) -> list[Path]:
        """Get list of paths that were created."""
        return [d.path for d in self.directories if d.created]

    def get_existing_paths(self) -> list[Path]:
        """Get list of paths that already existed."""
        return [d.path for d in self.directories if d.existed]

    def get_failed_paths(self) -> list[Path]:
        """Get list of paths that failed to create."""
        return [d.path for d in self.directories if d.error is not None]


@dataclass
class ScaffoldPreview:
    """
    Preview of what scaffolding would create (dry run).

    Attributes:
        project_dir: The project root directory
        claude_root: Path to the .claude/ directory
        to_create: Directories that would be created
        already_exist: Directories that already exist
        structure: Full structure as a tree-like representation
    """
    project_dir: Path
    claude_root: Path
    to_create: list[str] = field(default_factory=list)
    already_exist: list[str] = field(default_factory=list)
    structure: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_dir": str(self.project_dir),
            "claude_root": str(self.claude_root),
            "to_create": self.to_create,
            "already_exist": self.already_exist,
            "structure": self.structure,
        }


# =============================================================================
# Claude Directory Scaffold Class
# =============================================================================

class ClaudeDirectoryScaffold:
    """
    Scaffolds the standard .claude directory structure for a project.

    This class creates the directory structure that Claude Code expects:
    - .claude/ (root)
    - .claude/agents/generated/ (auto-generated agents)
    - .claude/agents/manual/ (manually-created agents)
    - .claude/skills/ (Phase 2)
    - .claude/commands/ (Phase 2)

    The scaffolding is idempotent and safe to run multiple times.
    """

    def __init__(
        self,
        project_dir: Path | str,
        *,
        permissions: int = DEFAULT_DIR_PERMISSIONS,
        include_phase2: bool = True,
    ):
        """
        Initialize the scaffolder.

        Args:
            project_dir: Root project directory
            permissions: Directory permissions to use (default: 0755)
            include_phase2: Whether to create Phase 2 directories (skills/, commands/)
        """
        self.project_dir = Path(project_dir).resolve()
        self.permissions = permissions
        self.include_phase2 = include_phase2

        _logger.info(
            "ClaudeDirectoryScaffold initialized: project_dir=%s, permissions=%o",
            self.project_dir, self.permissions,
        )

    @property
    def claude_root(self) -> Path:
        """Get the path to .claude/ directory."""
        return self.project_dir / CLAUDE_ROOT_DIR

    def get_subdirs(self) -> list[str]:
        """
        Get list of subdirectories to create.

        Returns:
            List of subdirectory paths relative to .claude/
        """
        if self.include_phase2:
            return list(STANDARD_SUBDIRS)
        return [d for d in STANDARD_SUBDIRS if d in PHASE_1_DIRS]

    def create_structure(self) -> ScaffoldResult:
        """
        Create the full .claude directory structure.

        This method is idempotent - it can be called multiple times
        without destroying existing content.

        Feature #199 Steps:
        1. Create .claude/ root directory if missing
        2. Create .claude/agents/generated/ subdirectory
        3. Create .claude/agents/manual/ subdirectory (empty)
        4. Create .claude/skills/ subdirectory (empty, Phase 2)
        5. Create .claude/commands/ subdirectory (empty, Phase 2)

        Returns:
            ScaffoldResult with details of what was created
        """
        result = ScaffoldResult(
            success=True,
            project_dir=self.project_dir,
            claude_root=self.claude_root,
        )

        # Step 1: Create .claude/ root directory
        root_status = self._create_directory(self.claude_root, CLAUDE_ROOT_DIR)
        result.directories.append(root_status)
        self._update_counts(result, root_status)

        if root_status.error:
            result.success = False
            _logger.error(
                "Failed to create .claude root directory: %s",
                root_status.error,
            )
            return result

        # Steps 2-5: Create subdirectories
        for subdir in self.get_subdirs():
            subdir_path = self.claude_root / subdir
            phase = 1 if subdir in PHASE_1_DIRS else 2

            status = self._create_directory(subdir_path, subdir, phase=phase)
            result.directories.append(status)
            self._update_counts(result, status)

            if status.error:
                result.success = False
                _logger.error(
                    "Failed to create .claude/%s directory: %s",
                    subdir, status.error,
                )

        _logger.info(
            "Scaffolding complete: created=%d, existed=%d, failed=%d",
            result.directories_created,
            result.directories_existed,
            result.directories_failed,
        )

        return result

    def _create_directory(
        self,
        path: Path,
        relative_path: str,
        *,
        phase: int = 1,
    ) -> DirectoryStatus:
        """
        Create a single directory if it doesn't exist.

        Args:
            path: Absolute path to create
            relative_path: Path relative to .claude/ for reporting
            phase: Phase number (1 or 2)

        Returns:
            DirectoryStatus with creation result
        """
        status = DirectoryStatus(
            path=path,
            relative_path=relative_path,
            phase=phase,
        )

        try:
            if path.exists():
                if path.is_dir():
                    status.existed = True
                    _logger.debug("Directory already exists: %s", path)
                else:
                    status.error = f"Path exists but is not a directory: {path}"
                    _logger.warning(status.error)
            else:
                path.mkdir(parents=True, exist_ok=True)
                # Set permissions (mkdir doesn't respect umask consistently)
                path.chmod(self.permissions)
                status.created = True
                _logger.info("Created directory: %s", path)

        except OSError as e:
            status.error = f"OS error creating directory: {e}"
            _logger.error(status.error)
        except Exception as e:
            status.error = f"Unexpected error creating directory: {e}"
            _logger.error(status.error)

        return status

    def _update_counts(
        self,
        result: ScaffoldResult,
        status: DirectoryStatus,
    ) -> None:
        """Update the counts in the result based on directory status."""
        if status.created:
            result.directories_created += 1
        elif status.existed:
            result.directories_existed += 1
        if status.error:
            result.directories_failed += 1

    def preview_structure(self) -> ScaffoldPreview:
        """
        Preview what scaffolding would create without actually creating anything.

        This is a dry-run that shows what directories would be created.

        Returns:
            ScaffoldPreview with details of what would happen
        """
        preview = ScaffoldPreview(
            project_dir=self.project_dir,
            claude_root=self.claude_root,
        )

        # Check root
        if self.claude_root.exists():
            preview.already_exist.append(CLAUDE_ROOT_DIR)
        else:
            preview.to_create.append(CLAUDE_ROOT_DIR)

        # Check subdirectories
        for subdir in self.get_subdirs():
            subdir_path = self.claude_root / subdir
            full_path = f"{CLAUDE_ROOT_DIR}/{subdir}"

            if subdir_path.exists():
                preview.already_exist.append(full_path)
            else:
                preview.to_create.append(full_path)

        # Build tree structure
        preview.structure = self._build_tree_structure()

        return preview

    def _build_tree_structure(self) -> list[str]:
        """
        Build a tree-like representation of the structure.

        Returns:
            List of strings representing the tree
        """
        lines = [f"{CLAUDE_ROOT_DIR}/"]

        subdirs = self.get_subdirs()
        for i, subdir in enumerate(subdirs):
            is_last = i == len(subdirs) - 1
            prefix = "    " if is_last else "    "

            # Split into parts for nested display
            parts = subdir.split("/")
            for j, part in enumerate(parts):
                if j == 0:
                    connector = "" if is_last else ""
                    lines.append(f"{prefix}{connector}{part}/")
                else:
                    inner_prefix = "        " * j
                    lines.append(f"{prefix}{inner_prefix}{part}/")

        return lines

    def ensure_root_exists(self) -> DirectoryStatus:
        """
        Ensure only the .claude/ root directory exists.

        Use this when you need to guarantee the root exists without
        creating the full structure.

        Returns:
            DirectoryStatus for the root directory
        """
        return self._create_directory(self.claude_root, CLAUDE_ROOT_DIR)

    def ensure_agents_generated_exists(self) -> DirectoryStatus:
        """
        Ensure .claude/agents/generated/ directory exists.

        This is the most commonly needed directory for auto-generated agents.

        Returns:
            DirectoryStatus for the agents/generated directory
        """
        # Ensure root and parent exist first
        self.ensure_root_exists()

        path = self.claude_root / "agents" / "generated"
        return self._create_directory(path, "agents/generated")

    def verify_structure(self) -> dict[str, bool]:
        """
        Verify that all expected directories exist.

        Returns:
            Dictionary mapping directory names to existence status
        """
        status = {CLAUDE_ROOT_DIR: self.claude_root.is_dir()}

        for subdir in self.get_subdirs():
            subdir_path = self.claude_root / subdir
            full_path = f"{CLAUDE_ROOT_DIR}/{subdir}"
            status[full_path] = subdir_path.is_dir()

        return status

    def is_scaffolded(self) -> bool:
        """
        Check if the directory structure is fully scaffolded.

        Returns:
            True if all expected directories exist, False otherwise
        """
        verification = self.verify_structure()
        return all(verification.values())


# =============================================================================
# Module-level Functions
# =============================================================================

def scaffold_claude_directory(
    project_dir: Path | str,
    *,
    permissions: int = DEFAULT_DIR_PERMISSIONS,
    include_phase2: bool = True,
) -> ScaffoldResult:
    """
    Scaffold the standard .claude directory structure.

    This is a convenience function that creates a ClaudeDirectoryScaffold
    and runs the full scaffolding process.

    Args:
        project_dir: Root project directory
        permissions: Directory permissions to use (default: 0755)
        include_phase2: Whether to create Phase 2 directories

    Returns:
        ScaffoldResult with details of what was created
    """
    scaffold = ClaudeDirectoryScaffold(
        project_dir,
        permissions=permissions,
        include_phase2=include_phase2,
    )
    return scaffold.create_structure()


def preview_claude_directory(
    project_dir: Path | str,
    *,
    include_phase2: bool = True,
) -> ScaffoldPreview:
    """
    Preview what scaffolding would create without creating anything.

    Args:
        project_dir: Root project directory
        include_phase2: Whether to include Phase 2 directories in preview

    Returns:
        ScaffoldPreview with details of what would happen
    """
    scaffold = ClaudeDirectoryScaffold(
        project_dir,
        include_phase2=include_phase2,
    )
    return scaffold.preview_structure()


def ensure_claude_root(project_dir: Path | str) -> DirectoryStatus:
    """
    Ensure only the .claude/ root directory exists.

    Args:
        project_dir: Root project directory

    Returns:
        DirectoryStatus for the root directory
    """
    scaffold = ClaudeDirectoryScaffold(project_dir)
    return scaffold.ensure_root_exists()


def ensure_agents_generated(project_dir: Path | str) -> DirectoryStatus:
    """
    Ensure .claude/agents/generated/ exists.

    This is the most commonly needed directory for auto-generated agents.

    Args:
        project_dir: Root project directory

    Returns:
        DirectoryStatus for the agents/generated directory
    """
    scaffold = ClaudeDirectoryScaffold(project_dir)
    return scaffold.ensure_agents_generated_exists()


def verify_claude_structure(
    project_dir: Path | str,
    *,
    include_phase2: bool = True,
) -> dict[str, bool]:
    """
    Verify that all expected .claude directories exist.

    Args:
        project_dir: Root project directory
        include_phase2: Whether to check Phase 2 directories

    Returns:
        Dictionary mapping directory names to existence status
    """
    scaffold = ClaudeDirectoryScaffold(
        project_dir,
        include_phase2=include_phase2,
    )
    return scaffold.verify_structure()


def is_claude_scaffolded(
    project_dir: Path | str,
    *,
    include_phase2: bool = True,
) -> bool:
    """
    Check if a project has the full .claude directory structure.

    Args:
        project_dir: Root project directory
        include_phase2: Whether to require Phase 2 directories

    Returns:
        True if all expected directories exist, False otherwise
    """
    scaffold = ClaudeDirectoryScaffold(
        project_dir,
        include_phase2=include_phase2,
    )
    return scaffold.is_scaffolded()


def get_standard_subdirs(include_phase2: bool = True) -> list[str]:
    """
    Get the list of standard subdirectories that scaffolding creates.

    Args:
        include_phase2: Whether to include Phase 2 directories

    Returns:
        List of subdirectory paths relative to .claude/
    """
    if include_phase2:
        return list(STANDARD_SUBDIRS)
    return [d for d in STANDARD_SUBDIRS if d in PHASE_1_DIRS]


# =============================================================================
# Feature #200: CLAUDE.md Generation
# =============================================================================

# Constants for CLAUDE.md generation
CLAUDE_MD_FILE = "CLAUDE.md"
DEFAULT_FILE_PERMISSIONS = 0o644


@dataclass
class ProjectMetadata:
    """
    Project metadata used for CLAUDE.md generation.

    Feature #200: If project lacks CLAUDE.md, scaffolding creates a minimal version.

    Attributes:
        name: Project name (derived from directory name or provided)
        tech_stack: List of technologies used (e.g., ["Python", "React", "FastAPI"])
        key_directories: List of important directories with descriptions
        description: Optional project description
    """
    name: str
    tech_stack: list[str] = field(default_factory=list)
    key_directories: list[tuple[str, str]] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "tech_stack": self.tech_stack,
            "key_directories": [{"path": p, "description": d} for p, d in self.key_directories],
            "description": self.description,
        }

    @classmethod
    def from_project_context(cls, project_context: dict[str, Any]) -> "ProjectMetadata":
        """
        Create ProjectMetadata from an OctoRequestPayload-style project_context.

        Args:
            project_context: Dictionary with keys like 'name', 'tech_stack', 'directory_structure'

        Returns:
            ProjectMetadata instance
        """
        name = project_context.get("name", "")
        tech_stack = project_context.get("tech_stack", [])
        if isinstance(tech_stack, str):
            tech_stack = [t.strip() for t in tech_stack.split(",") if t.strip()]

        # Handle directory_structure (can be list of strings or list of dicts)
        dir_structure = project_context.get("directory_structure", [])
        key_directories: list[tuple[str, str]] = []
        if isinstance(dir_structure, list):
            for item in dir_structure:
                if isinstance(item, str):
                    key_directories.append((item, ""))
                elif isinstance(item, dict) and "path" in item:
                    key_directories.append((item["path"], item.get("description", "")))

        description = project_context.get("app_spec_summary", "")

        return cls(
            name=name,
            tech_stack=tech_stack,
            key_directories=key_directories,
            description=description,
        )

    @classmethod
    def from_directory(cls, project_dir: Path) -> "ProjectMetadata":
        """
        Detect project metadata by analyzing the project directory.

        Args:
            project_dir: Root project directory

        Returns:
            ProjectMetadata instance with auto-detected values
        """
        project_dir = Path(project_dir).resolve()

        # Derive name from directory
        name = project_dir.name

        # Detect tech stack from files
        tech_stack = _detect_tech_stack(project_dir)

        # Detect key directories
        key_directories = _detect_key_directories(project_dir)

        return cls(
            name=name,
            tech_stack=tech_stack,
            key_directories=key_directories,
            description="",
        )


@dataclass
class ClaudeMdResult:
    """
    Result of CLAUDE.md file generation.

    Attributes:
        path: Path to the CLAUDE.md file
        existed: Whether the file already existed
        created: Whether the file was created
        skipped: Whether creation was skipped (existing file preserved)
        error: Error message if creation failed
        content: The generated content (if created)
    """
    path: Path
    existed: bool = False
    created: bool = False
    skipped: bool = False
    error: str | None = None
    content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": str(self.path),
            "existed": self.existed,
            "created": self.created,
            "skipped": self.skipped,
            "error": self.error,
            "content_length": len(self.content) if self.content else 0,
        }


def _detect_tech_stack(project_dir: Path) -> list[str]:
    """
    Detect technologies used in a project by examining marker files.

    Args:
        project_dir: Root project directory

    Returns:
        List of detected technology names
    """
    tech_stack: list[str] = []

    # Python markers
    if (project_dir / "pyproject.toml").exists() or \
       (project_dir / "setup.py").exists() or \
       (project_dir / "requirements.txt").exists():
        tech_stack.append("Python")

    # Node.js / JavaScript markers
    if (project_dir / "package.json").exists():
        tech_stack.append("Node.js")

    # TypeScript markers
    if (project_dir / "tsconfig.json").exists():
        tech_stack.append("TypeScript")

    # React markers (look in package.json if exists)
    package_json = project_dir / "package.json"
    if package_json.exists():
        try:
            import json
            content = package_json.read_text()
            pkg = json.loads(content)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "react" in deps:
                tech_stack.append("React")
            if "vue" in deps:
                tech_stack.append("Vue")
            if "next" in deps:
                tech_stack.append("Next.js")
            if "fastify" in deps or "express" in deps:
                tech_stack.append("Express/Fastify")
            if "@playwright/test" in deps or "playwright" in deps:
                tech_stack.append("Playwright")
            if "tailwindcss" in deps:
                tech_stack.append("Tailwind CSS")
        except (json.JSONDecodeError, OSError):
            pass

    # FastAPI / Flask markers (check requirements.txt or pyproject.toml)
    for marker_file in ["requirements.txt", "pyproject.toml"]:
        marker_path = project_dir / marker_file
        if marker_path.exists():
            try:
                content = marker_path.read_text().lower()
                if "fastapi" in content:
                    tech_stack.append("FastAPI")
                if "flask" in content:
                    tech_stack.append("Flask")
                if "django" in content:
                    tech_stack.append("Django")
                if "sqlalchemy" in content:
                    tech_stack.append("SQLAlchemy")
                if "pytest" in content:
                    tech_stack.append("pytest")
            except OSError:
                pass

    # Docker markers
    if (project_dir / "Dockerfile").exists() or (project_dir / "docker-compose.yml").exists():
        tech_stack.append("Docker")

    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique_stack: list[str] = []
    for tech in tech_stack:
        if tech not in seen:
            seen.add(tech)
            unique_stack.append(tech)

    return unique_stack


def _detect_key_directories(project_dir: Path) -> list[tuple[str, str]]:
    """
    Detect key directories in a project.

    Args:
        project_dir: Root project directory

    Returns:
        List of (directory_name, description) tuples
    """
    key_dirs: list[tuple[str, str]] = []

    # Common directory patterns and their descriptions
    dir_patterns: list[tuple[str, str]] = [
        ("src", "Source code"),
        ("api", "API endpoints and backend logic"),
        ("server", "Server implementation"),
        ("client", "Client-side application"),
        ("ui", "User interface components"),
        ("frontend", "Frontend application"),
        ("backend", "Backend application"),
        ("lib", "Library code and utilities"),
        ("tests", "Test suites"),
        ("test", "Test suites"),
        ("docs", "Documentation"),
        ("scripts", "Utility scripts"),
        ("config", "Configuration files"),
        ("migrations", "Database migrations"),
        ("models", "Data models"),
        ("views", "View templates or components"),
        ("controllers", "Controller logic"),
        ("routes", "Route definitions"),
        ("components", "Reusable components"),
        ("pages", "Page components (Next.js/Nuxt)"),
        ("public", "Public static assets"),
        ("static", "Static files"),
        ("assets", "Asset files (images, fonts, etc.)"),
    ]

    for dir_name, description in dir_patterns:
        dir_path = project_dir / dir_name
        if dir_path.is_dir():
            key_dirs.append((dir_name, description))

    return key_dirs


def generate_claude_md_content(metadata: ProjectMetadata) -> str:
    """
    Generate CLAUDE.md content from project metadata.

    Feature #200, Step 2-4: Generate minimal CLAUDE.md from project metadata
    that provides context for Claude CLI agents.

    Args:
        metadata: Project metadata to include

    Returns:
        Generated CLAUDE.md content as a string
    """
    lines: list[str] = []

    # Header with project name
    lines.append(f"# {metadata.name}")
    lines.append("")

    # Description if available
    if metadata.description:
        lines.append(metadata.description)
        lines.append("")

    # Tech Stack section
    if metadata.tech_stack:
        lines.append("## Tech Stack")
        lines.append("")
        for tech in metadata.tech_stack:
            lines.append(f"- {tech}")
        lines.append("")

    # Key Directories section
    if metadata.key_directories:
        lines.append("## Project Structure")
        lines.append("")
        for dir_name, description in metadata.key_directories:
            if description:
                lines.append(f"- `{dir_name}/` - {description}")
            else:
                lines.append(f"- `{dir_name}/`")
        lines.append("")

    # Getting Started section
    lines.append("## Getting Started")
    lines.append("")
    lines.append("This file provides context for Claude Code agents working on this project.")
    lines.append("Customize this file with project-specific instructions, coding standards,")
    lines.append("and any important context that agents should know about.")
    lines.append("")

    return "\n".join(lines)


def claude_md_exists(project_dir: Path | str) -> bool:
    """
    Check if CLAUDE.md exists in the project root.

    Feature #200, Step 1: Check if CLAUDE.md exists in project root

    Args:
        project_dir: Root project directory

    Returns:
        True if CLAUDE.md exists, False otherwise
    """
    project_dir = Path(project_dir).resolve()
    claude_md_path = project_dir / CLAUDE_MD_FILE
    return claude_md_path.exists()


def generate_claude_md(
    project_dir: Path | str,
    *,
    metadata: ProjectMetadata | None = None,
    project_context: dict[str, Any] | None = None,
    overwrite: bool = False,
    permissions: int = DEFAULT_FILE_PERMISSIONS,
) -> ClaudeMdResult:
    """
    Generate a minimal CLAUDE.md file if it doesn't exist.

    Feature #200: If project lacks CLAUDE.md, scaffolding creates a minimal version
    with basic project context.

    This function:
    1. Checks if CLAUDE.md exists in project root (Step 1)
    2. If missing, generates minimal content from metadata (Step 2-3)
    3. Creates CLAUDE.md to provide context for Claude CLI agents (Step 4)
    4. Never overwrites existing CLAUDE.md unless explicitly requested (Step 5)

    Args:
        project_dir: Root project directory
        metadata: Optional ProjectMetadata to use (if not provided, auto-detect)
        project_context: Optional project_context dict (alternative to metadata)
        overwrite: If True, overwrite existing CLAUDE.md (default: False)
        permissions: File permissions to use (default: 0o644)

    Returns:
        ClaudeMdResult with details of what happened
    """
    project_dir = Path(project_dir).resolve()
    claude_md_path = project_dir / CLAUDE_MD_FILE

    result = ClaudeMdResult(path=claude_md_path)

    # Step 1: Check if CLAUDE.md exists
    if claude_md_path.exists():
        result.existed = True

        # Step 5: Never overwrite existing CLAUDE.md unless explicitly requested
        if not overwrite:
            result.skipped = True
            _logger.info(
                "CLAUDE.md already exists at %s, skipping (overwrite=False)",
                claude_md_path,
            )
            return result
        else:
            _logger.warning(
                "CLAUDE.md exists at %s but overwrite=True, will replace",
                claude_md_path,
            )

    # Step 2: Generate content from metadata
    if metadata is None:
        if project_context is not None:
            # Use project_context to create metadata
            metadata = ProjectMetadata.from_project_context(project_context)
            # If name is missing, use directory name
            if not metadata.name:
                metadata.name = project_dir.name
        else:
            # Auto-detect from directory
            metadata = ProjectMetadata.from_directory(project_dir)

    # Step 3: Include project name, tech stack summary, key directories
    content = generate_claude_md_content(metadata)
    result.content = content

    # Step 4: Write CLAUDE.md
    try:
        claude_md_path.write_text(content)
        claude_md_path.chmod(permissions)
        result.created = True
        _logger.info(
            "Created CLAUDE.md at %s (project: %s, tech_stack: %s)",
            claude_md_path,
            metadata.name,
            ", ".join(metadata.tech_stack) or "none detected",
        )
    except OSError as e:
        result.error = f"OS error creating CLAUDE.md: {e}"
        _logger.error(result.error)
    except Exception as e:
        result.error = f"Unexpected error creating CLAUDE.md: {e}"
        _logger.error(result.error)

    return result


def ensure_claude_md(
    project_dir: Path | str,
    *,
    project_context: dict[str, Any] | None = None,
) -> ClaudeMdResult:
    """
    Ensure CLAUDE.md exists, creating it if necessary.

    This is a convenience function that never overwrites existing files.

    Args:
        project_dir: Root project directory
        project_context: Optional project_context dict for metadata

    Returns:
        ClaudeMdResult with details of what happened
    """
    return generate_claude_md(
        project_dir,
        project_context=project_context,
        overwrite=False,
    )


def scaffold_with_claude_md(
    project_dir: Path | str,
    *,
    project_context: dict[str, Any] | None = None,
    permissions: int = DEFAULT_DIR_PERMISSIONS,
    file_permissions: int = DEFAULT_FILE_PERMISSIONS,
    include_phase2: bool = True,
    include_claude_md: bool = True,
) -> tuple[ScaffoldResult, ClaudeMdResult | None]:
    """
    Full scaffolding including CLAUDE.md generation.

    This combines:
    - Feature #199: .claude directory scaffolding
    - Feature #200: CLAUDE.md generation

    Args:
        project_dir: Root project directory
        project_context: Optional project_context dict for CLAUDE.md metadata
        permissions: Directory permissions to use (default: 0755)
        file_permissions: File permissions for CLAUDE.md (default: 0644)
        include_phase2: Whether to create Phase 2 directories
        include_claude_md: Whether to create CLAUDE.md (default: True)

    Returns:
        Tuple of (ScaffoldResult, ClaudeMdResult or None)
    """
    # First, scaffold the .claude directory structure
    scaffold_result = scaffold_claude_directory(
        project_dir,
        permissions=permissions,
        include_phase2=include_phase2,
    )

    # Then, optionally create CLAUDE.md
    claude_md_result: ClaudeMdResult | None = None
    if include_claude_md:
        claude_md_result = generate_claude_md(
            project_dir,
            project_context=project_context,
            permissions=file_permissions,
            overwrite=False,  # Never overwrite existing
        )

    return scaffold_result, claude_md_result


# =============================================================================
# Feature #202: Project Initialization with Scaffolding
# =============================================================================

# Scaffolding metadata keys
SCAFFOLDING_METADATA_KEY = "scaffolding_status"
SCAFFOLDING_TIMESTAMP_KEY = "scaffolding_timestamp"
SCAFFOLDING_COMPLETED_KEY = "scaffolding_completed"

# Metadata file name within .autobuildr/
PROJECT_METADATA_FILE = "metadata.json"


@dataclass
class ScaffoldingStatus:
    """
    Status of scaffolding for a project.

    Feature #202, Step 4: Scaffolding status recorded in project metadata.

    Attributes:
        completed: Whether scaffolding has been completed
        timestamp: When scaffolding was completed (ISO format)
        directories_created: Number of directories created
        directories_existed: Number of directories that existed
        claude_md_created: Whether CLAUDE.md was created
        error: Error message if scaffolding failed
    """
    completed: bool = False
    timestamp: str | None = None
    directories_created: int = 0
    directories_existed: int = 0
    claude_md_created: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            SCAFFOLDING_COMPLETED_KEY: self.completed,
            SCAFFOLDING_TIMESTAMP_KEY: self.timestamp,
            "directories_created": self.directories_created,
            "directories_existed": self.directories_existed,
            "claude_md_created": self.claude_md_created,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScaffoldingStatus":
        """Create ScaffoldingStatus from dictionary."""
        return cls(
            completed=data.get(SCAFFOLDING_COMPLETED_KEY, False),
            timestamp=data.get(SCAFFOLDING_TIMESTAMP_KEY),
            directories_created=data.get("directories_created", 0),
            directories_existed=data.get("directories_existed", 0),
            claude_md_created=data.get("claude_md_created", False),
            error=data.get("error"),
        )


@dataclass
class ProjectInitializationResult:
    """
    Result of project initialization including scaffolding.

    Feature #202: Scaffolding triggered automatically on project initialization.

    Attributes:
        success: Whether initialization was successful
        project_dir: Path to the project directory
        scaffold_result: Result from directory scaffolding
        claude_md_result: Result from CLAUDE.md generation (if applicable)
        scaffolding_status: Status recorded in project metadata
        metadata_saved: Whether metadata was saved successfully
    """
    success: bool
    project_dir: Path
    scaffold_result: ScaffoldResult | None = None
    claude_md_result: ClaudeMdResult | None = None
    scaffolding_status: ScaffoldingStatus | None = None
    metadata_saved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "project_dir": str(self.project_dir),
            "scaffold_result": self.scaffold_result.to_dict() if self.scaffold_result else None,
            "claude_md_result": self.claude_md_result.to_dict() if self.claude_md_result else None,
            "scaffolding_status": self.scaffolding_status.to_dict() if self.scaffolding_status else None,
            "metadata_saved": self.metadata_saved,
        }


def _get_metadata_path(project_dir: Path) -> Path:
    """
    Get the path to the project metadata file.

    Args:
        project_dir: Root project directory

    Returns:
        Path to .autobuildr/metadata.json
    """
    return project_dir / ".autobuildr" / PROJECT_METADATA_FILE


def _load_project_metadata(project_dir: Path) -> dict[str, Any]:
    """
    Load project metadata from disk.

    Args:
        project_dir: Root project directory

    Returns:
        Metadata dictionary, or empty dict if file doesn't exist
    """
    import json

    metadata_path = _get_metadata_path(project_dir)

    if not metadata_path.exists():
        return {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except (json.JSONDecodeError, OSError) as e:
        _logger.warning("Failed to load project metadata from %s: %s", metadata_path, e)
        return {}


def _save_project_metadata(project_dir: Path, metadata: dict[str, Any]) -> bool:
    """
    Save project metadata to disk.

    Args:
        project_dir: Root project directory
        metadata: Metadata dictionary to save

    Returns:
        True if saved successfully, False otherwise
    """
    import json

    metadata_path = _get_metadata_path(project_dir)

    try:
        # Ensure .autobuildr directory exists
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        _logger.debug("Saved project metadata to %s", metadata_path)
        return True
    except OSError as e:
        _logger.error("Failed to save project metadata to %s: %s", metadata_path, e)
        return False


def get_scaffolding_status(project_dir: Path | str) -> ScaffoldingStatus:
    """
    Get the scaffolding status from project metadata.

    Feature #202, Step 4: Scaffolding status recorded in project metadata.

    Args:
        project_dir: Root project directory

    Returns:
        ScaffoldingStatus from metadata, or default (not completed) if not found
    """
    project_dir = Path(project_dir).resolve()
    metadata = _load_project_metadata(project_dir)
    scaffolding_data = metadata.get(SCAFFOLDING_METADATA_KEY, {})
    return ScaffoldingStatus.from_dict(scaffolding_data)


def _record_scaffolding_status(
    project_dir: Path,
    scaffold_result: ScaffoldResult,
    claude_md_result: ClaudeMdResult | None,
) -> tuple[ScaffoldingStatus, bool]:
    """
    Record scaffolding status in project metadata.

    Feature #202, Step 4: Scaffolding status recorded in project metadata.

    Args:
        project_dir: Root project directory
        scaffold_result: Result from scaffolding
        claude_md_result: Result from CLAUDE.md generation (optional)

    Returns:
        Tuple of (ScaffoldingStatus, metadata_saved_successfully)
    """
    from datetime import datetime, timezone

    # Create status object
    status = ScaffoldingStatus(
        completed=scaffold_result.success,
        timestamp=datetime.now(timezone.utc).isoformat(),
        directories_created=scaffold_result.directories_created,
        directories_existed=scaffold_result.directories_existed,
        claude_md_created=claude_md_result.created if claude_md_result else False,
        error=None if scaffold_result.success else "Scaffolding failed",
    )

    # Load existing metadata
    metadata = _load_project_metadata(project_dir)

    # Update scaffolding status
    metadata[SCAFFOLDING_METADATA_KEY] = status.to_dict()

    # Save metadata
    saved = _save_project_metadata(project_dir, metadata)

    return status, saved


def needs_scaffolding(project_dir: Path | str) -> bool:
    """
    Check if a project needs scaffolding.

    Feature #202, Step 1: Project initialization triggers scaffolding check.

    Returns True if:
    - .claude directory doesn't exist, OR
    - Scaffolding status is not completed in metadata

    Args:
        project_dir: Root project directory

    Returns:
        True if scaffolding is needed, False otherwise
    """
    project_dir = Path(project_dir).resolve()

    # Check if .claude directory exists
    if not (project_dir / CLAUDE_ROOT_DIR).exists():
        return True

    # Check scaffolding status in metadata
    status = get_scaffolding_status(project_dir)
    return not status.completed


def initialize_project_scaffolding(
    project_dir: Path | str,
    *,
    project_context: dict[str, Any] | None = None,
    include_claude_md: bool = True,
    include_phase2: bool = True,
    force: bool = False,
) -> ProjectInitializationResult:
    """
    Initialize project with scaffolding.

    Feature #202: Scaffolding triggered automatically on project initialization.

    This function:
    1. Checks if scaffolding is needed (Step 1)
    2. Creates missing .claude structure automatically (Step 2)
    3. Completes scaffolding (Step 3)
    4. Records scaffolding status in project metadata (Step 4)

    Args:
        project_dir: Root project directory
        project_context: Optional context for CLAUDE.md generation
        include_claude_md: Whether to create CLAUDE.md if missing
        include_phase2: Whether to create Phase 2 directories
        force: If True, force scaffolding even if already completed

    Returns:
        ProjectInitializationResult with full details
    """
    project_dir = Path(project_dir).resolve()

    _logger.info(
        "initialize_project_scaffolding called for %s (force=%s)",
        project_dir, force,
    )

    result = ProjectInitializationResult(
        success=False,
        project_dir=project_dir,
    )

    # Step 1: Check if scaffolding is needed
    if not force and not needs_scaffolding(project_dir):
        _logger.info("Scaffolding already completed for %s, skipping", project_dir)
        result.success = True
        result.scaffolding_status = get_scaffolding_status(project_dir)
        return result

    # Step 2 & 3: Create .claude structure and complete scaffolding
    try:
        scaffold_result, claude_md_result = scaffold_with_claude_md(
            project_dir,
            project_context=project_context,
            include_phase2=include_phase2,
            include_claude_md=include_claude_md,
        )

        result.scaffold_result = scaffold_result
        result.claude_md_result = claude_md_result

        # Step 4: Record scaffolding status in project metadata
        status, saved = _record_scaffolding_status(
            project_dir, scaffold_result, claude_md_result
        )

        result.scaffolding_status = status
        result.metadata_saved = saved
        result.success = scaffold_result.success

        _logger.info(
            "Project scaffolding %s for %s: created=%d, existed=%d",
            "completed" if result.success else "failed",
            project_dir,
            scaffold_result.directories_created,
            scaffold_result.directories_existed,
        )

    except Exception as e:
        _logger.error("Project scaffolding failed for %s: %s", project_dir, e)
        result.success = False
        result.scaffolding_status = ScaffoldingStatus(
            completed=False,
            error=str(e),
        )

    return result


def ensure_project_scaffolded(project_dir: Path | str) -> ProjectInitializationResult:
    """
    Ensure a project has been scaffolded before agent execution.

    Feature #202, Step 3: Scaffolding completes before agent execution.

    This is a convenience function that:
    - Checks if scaffolding is needed
    - If needed, runs scaffolding
    - Returns immediately if scaffolding already completed

    Args:
        project_dir: Root project directory

    Returns:
        ProjectInitializationResult with scaffolding status
    """
    return initialize_project_scaffolding(
        project_dir,
        include_claude_md=True,
        include_phase2=True,
        force=False,
    )


def is_project_initialized(project_dir: Path | str) -> bool:
    """
    Quick check if project has been initialized (scaffolding completed).

    Args:
        project_dir: Root project directory

    Returns:
        True if scaffolding is completed, False otherwise
    """
    return not needs_scaffolding(project_dir)


# =============================================================================
# Feature #204: Scaffolding respects .gitignore patterns
# =============================================================================

# Constants for .gitignore management
GITIGNORE_FILE = ".gitignore"

# Default patterns to add for Claude Code generated files
# Note: .claude/agents/manual/ and CLAUDE.md should be TRACKED (not in .gitignore)
GITIGNORE_GENERATED_PATTERNS: tuple[str, ...] = (
    ".claude/agents/generated/",  # Auto-generated agents should not be tracked
)

# Patterns that should NOT be added to .gitignore (should be tracked)
GITIGNORE_TRACKED_PATTERNS: frozenset[str] = frozenset({
    ".claude/agents/manual/",  # Manually-created agents should be tracked
    "CLAUDE.md",               # Project context file should be tracked
    ".claude/skills/",         # Custom skills should be tracked
    ".claude/commands/",       # Custom commands should be tracked
})


@dataclass
class GitignoreUpdateResult:
    """
    Result of updating the .gitignore file.

    Feature #204: Scaffolding respects .gitignore patterns.

    Attributes:
        path: Path to the .gitignore file
        existed: Whether .gitignore existed before update
        created: Whether .gitignore was created
        modified: Whether .gitignore was modified
        patterns_added: List of patterns that were added
        patterns_already_present: List of patterns that were already in .gitignore
        error: Error message if update failed
        original_content: Original content before update (for debugging)
    """
    path: Path
    existed: bool = False
    created: bool = False
    modified: bool = False
    patterns_added: list[str] = field(default_factory=list)
    patterns_already_present: list[str] = field(default_factory=list)
    error: str | None = None
    original_content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": str(self.path),
            "existed": self.existed,
            "created": self.created,
            "modified": self.modified,
            "patterns_added": self.patterns_added,
            "patterns_already_present": self.patterns_already_present,
            "error": self.error,
        }


def gitignore_exists(project_dir: Path | str) -> bool:
    """
    Check if .gitignore exists in the project root.

    Feature #204, Step 1: Check if .gitignore exists.

    Args:
        project_dir: Root project directory

    Returns:
        True if .gitignore exists, False otherwise
    """
    project_dir = Path(project_dir).resolve()
    gitignore_path = project_dir / GITIGNORE_FILE
    return gitignore_path.exists()


def _parse_gitignore(content: str) -> set[str]:
    """
    Parse .gitignore content into a set of normalized patterns.

    Handles:
    - Comments (lines starting with #)
    - Empty lines
    - Whitespace trimming
    - Duplicate detection

    Args:
        content: Raw .gitignore content

    Returns:
        Set of normalized patterns (non-comment, non-empty lines)
    """
    patterns: set[str] = set()
    for line in content.splitlines():
        # Strip whitespace
        stripped = line.strip()
        # Skip empty lines and comments
        if stripped and not stripped.startswith("#"):
            patterns.add(stripped)
    return patterns


def _pattern_is_present(existing_patterns: set[str], pattern: str) -> bool:
    """
    Check if a pattern (or an equivalent form) is present in existing patterns.

    Handles variations like:
    - ".claude/agents/generated/" vs ".claude/agents/generated"
    - Leading "/" variations

    Args:
        existing_patterns: Set of existing patterns
        pattern: Pattern to check

    Returns:
        True if pattern (or equivalent) is present
    """
    # Normalize the pattern we're checking
    normalized = pattern.rstrip("/")

    for existing in existing_patterns:
        existing_normalized = existing.rstrip("/")
        if existing_normalized == normalized:
            return True
        # Also check without leading /
        if existing_normalized.lstrip("/") == normalized.lstrip("/"):
            return True

    return False


def update_gitignore(
    project_dir: Path | str,
    *,
    patterns: list[str] | None = None,
    create_if_missing: bool = True,
    add_header_comment: bool = True,
) -> GitignoreUpdateResult:
    """
    Update .gitignore with patterns for Claude Code generated files.

    Feature #204: Scaffolding respects .gitignore patterns.

    This function:
    1. Checks if .gitignore exists (Step 1)
    2. Adds .claude/agents/generated/ to .gitignore if not present (Step 2)
    3. Keeps .claude/agents/manual/ tracked (Step 3) - by NOT adding it
    4. Keeps CLAUDE.md tracked (Step 4) - by NOT adding it
    5. Preserves existing .gitignore content (Step 5)

    Args:
        project_dir: Root project directory
        patterns: Custom patterns to add (defaults to GITIGNORE_GENERATED_PATTERNS)
        create_if_missing: If True, create .gitignore if it doesn't exist
        add_header_comment: If True, add a comment before Claude Code patterns

    Returns:
        GitignoreUpdateResult with details of what happened
    """
    project_dir = Path(project_dir).resolve()
    gitignore_path = project_dir / GITIGNORE_FILE

    result = GitignoreUpdateResult(path=gitignore_path)

    # Use default patterns if none specified
    if patterns is None:
        patterns = list(GITIGNORE_GENERATED_PATTERNS)

    # Step 1: Check if .gitignore exists
    if gitignore_path.exists():
        result.existed = True
        try:
            # Step 5: Preserve existing .gitignore content
            original_content = gitignore_path.read_text(encoding="utf-8")
            result.original_content = original_content
        except OSError as e:
            result.error = f"Failed to read .gitignore: {e}"
            _logger.error(result.error)
            return result
    else:
        if not create_if_missing:
            result.error = ".gitignore does not exist and create_if_missing=False"
            _logger.warning(result.error)
            return result
        original_content = ""
        result.original_content = ""

    # Parse existing patterns
    existing_patterns = _parse_gitignore(original_content)

    # Determine which patterns need to be added
    patterns_to_add: list[str] = []
    for pattern in patterns:
        # Step 3 & 4: Skip patterns that should be tracked
        # (This shouldn't happen if using GITIGNORE_GENERATED_PATTERNS, but be safe)
        if pattern in GITIGNORE_TRACKED_PATTERNS:
            _logger.warning(
                "Skipping pattern '%s' - should be tracked, not ignored",
                pattern,
            )
            continue

        # Step 2: Add .claude/agents/generated/ if not present
        if _pattern_is_present(existing_patterns, pattern):
            result.patterns_already_present.append(pattern)
            _logger.debug("Pattern '%s' already in .gitignore", pattern)
        else:
            patterns_to_add.append(pattern)
            _logger.debug("Pattern '%s' will be added to .gitignore", pattern)

    # If nothing to add, we're done
    if not patterns_to_add:
        _logger.info("No patterns to add to .gitignore - all already present")
        return result

    # Build new content
    new_lines: list[str] = []

    # Start with original content
    if original_content:
        # Ensure original content ends with newline
        if not original_content.endswith("\n"):
            new_lines.append(original_content + "\n")
        else:
            new_lines.append(original_content)

    # Add comment header before new patterns
    if add_header_comment:
        new_lines.append("\n# Claude Code generated files (auto-added by scaffolding)\n")

    # Add new patterns
    for pattern in patterns_to_add:
        new_lines.append(pattern + "\n")

    new_content = "".join(new_lines)

    # Write the updated .gitignore
    try:
        gitignore_path.write_text(new_content, encoding="utf-8")
        result.patterns_added = patterns_to_add

        if result.existed:
            result.modified = True
            _logger.info(
                "Modified .gitignore: added %d patterns",
                len(patterns_to_add),
            )
        else:
            result.created = True
            _logger.info(
                "Created .gitignore with %d patterns",
                len(patterns_to_add),
            )

    except OSError as e:
        result.error = f"Failed to write .gitignore: {e}"
        _logger.error(result.error)

    return result


def ensure_gitignore_patterns(project_dir: Path | str) -> GitignoreUpdateResult:
    """
    Ensure the standard gitignore patterns for Claude Code are present.

    This is a convenience function that:
    - Creates .gitignore if it doesn't exist
    - Adds .claude/agents/generated/ to .gitignore if not present
    - Preserves all existing content

    Args:
        project_dir: Root project directory

    Returns:
        GitignoreUpdateResult with details of what happened
    """
    return update_gitignore(
        project_dir,
        patterns=list(GITIGNORE_GENERATED_PATTERNS),
        create_if_missing=True,
        add_header_comment=True,
    )


def verify_gitignore_patterns(project_dir: Path | str) -> dict[str, bool]:
    """
    Verify which gitignore patterns are present.

    Returns a dictionary mapping pattern -> present status.

    Args:
        project_dir: Root project directory

    Returns:
        Dictionary mapping patterns to presence status
    """
    project_dir = Path(project_dir).resolve()
    gitignore_path = project_dir / GITIGNORE_FILE

    # Default: nothing present
    result = {pattern: False for pattern in GITIGNORE_GENERATED_PATTERNS}

    if not gitignore_path.exists():
        return result

    try:
        content = gitignore_path.read_text(encoding="utf-8")
        existing_patterns = _parse_gitignore(content)

        for pattern in GITIGNORE_GENERATED_PATTERNS:
            result[pattern] = _pattern_is_present(existing_patterns, pattern)

    except OSError as e:
        _logger.warning("Failed to read .gitignore for verification: %s", e)

    return result


def scaffold_with_gitignore(
    project_dir: Path | str,
    *,
    project_context: dict[str, Any] | None = None,
    permissions: int = DEFAULT_DIR_PERMISSIONS,
    file_permissions: int = DEFAULT_FILE_PERMISSIONS,
    include_phase2: bool = True,
    include_claude_md: bool = True,
    update_gitignore_file: bool = True,
) -> tuple[ScaffoldResult, ClaudeMdResult | None, GitignoreUpdateResult | None]:
    """
    Full scaffolding including CLAUDE.md generation and .gitignore update.

    This combines:
    - Feature #199: .claude directory scaffolding
    - Feature #200: CLAUDE.md generation
    - Feature #204: .gitignore pattern management

    Args:
        project_dir: Root project directory
        project_context: Optional project_context dict for CLAUDE.md metadata
        permissions: Directory permissions to use (default: 0755)
        file_permissions: File permissions for CLAUDE.md (default: 0644)
        include_phase2: Whether to create Phase 2 directories
        include_claude_md: Whether to create CLAUDE.md (default: True)
        update_gitignore_file: Whether to update .gitignore (default: True)

    Returns:
        Tuple of (ScaffoldResult, ClaudeMdResult or None, GitignoreUpdateResult or None)
    """
    # First, scaffold the .claude directory structure and CLAUDE.md
    scaffold_result, claude_md_result = scaffold_with_claude_md(
        project_dir,
        project_context=project_context,
        permissions=permissions,
        file_permissions=file_permissions,
        include_phase2=include_phase2,
        include_claude_md=include_claude_md,
    )

    # Then, optionally update .gitignore
    gitignore_result: GitignoreUpdateResult | None = None
    if update_gitignore_file:
        gitignore_result = ensure_gitignore_patterns(project_dir)

    return scaffold_result, claude_md_result, gitignore_result
