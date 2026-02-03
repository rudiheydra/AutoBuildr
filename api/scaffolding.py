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
