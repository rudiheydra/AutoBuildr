"""
Icon Storage Service
====================

Feature #219: Generated icons stored and retrievable

This module provides persistent storage for agent icons:
1. Icon data stored in database or filesystem
2. Icon linked to AgentSpec by agent_spec_id
3. GET /api/agents/{id}/icon endpoint returns icon
4. Icon format header set appropriately (image/svg+xml, image/png)
5. Missing icon returns default placeholder

Icons are stored using a content-addressable approach similar to ArtifactStorage:
- Small icons (<=16KB) stored inline in database
- Large icons stored as files in .autobuildr/icons/{hash}.{ext}
- Deduplication via SHA256 hashing

Storage Strategy:
- Icons are linked to AgentSpec via agent_spec_id
- Each AgentSpec can have one associated icon
- Icons can be SVG, PNG, JPEG, or WebP format
- Missing icons fall back to generated placeholders

Example:
    >>> storage = IconStorage(project_dir)
    >>> icon = storage.store_icon(
    ...     session=db_session,
    ...     agent_spec_id="uuid-here",
    ...     icon_data="<svg>...</svg>",
    ...     icon_format=IconFormat.SVG,
    ... )
    >>> retrieved = storage.retrieve_icon(session, "uuid-here")
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Session, relationship
from sqlalchemy.types import JSON

from api.database import Base
from api.icon_provider import IconFormat, IconResult

if TYPE_CHECKING:
    from api.agentspec_models import AgentSpec

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


# =============================================================================
# Constants
# =============================================================================

# Maximum inline storage size (bytes) - icons larger than this go to files
ICON_INLINE_MAX_SIZE = 16 * 1024  # 16KB

# Supported icon formats with their MIME types
ICON_FORMAT_MIME_TYPES: dict[str, str] = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "icon_id": "text/plain",
    "emoji": "text/plain",
}

# Default placeholder provider name
DEFAULT_PLACEHOLDER_PROVIDER = "local_placeholder"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class StoredIconResult:
    """
    Result from storing an icon.

    Attributes:
        success: Whether storage was successful
        icon_id: The stored icon's database ID
        agent_spec_id: The AgentSpec this icon is linked to
        icon_format: Format of the stored icon
        content_hash: SHA256 hash of the icon content
        size_bytes: Size of the icon data in bytes
        stored_inline: Whether the icon was stored inline
        error: Error message if storage failed
    """

    success: bool
    icon_id: str | None = None
    agent_spec_id: str | None = None
    icon_format: str | None = None
    content_hash: str | None = None
    size_bytes: int = 0
    stored_inline: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "icon_id": self.icon_id,
            "agent_spec_id": self.agent_spec_id,
            "icon_format": self.icon_format,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "stored_inline": self.stored_inline,
            "error": self.error,
        }

    @classmethod
    def error_result(cls, error: str) -> "StoredIconResult":
        """Create an error result."""
        return cls(success=False, error=error)

    @classmethod
    def success_result(
        cls,
        icon_id: str,
        agent_spec_id: str,
        icon_format: str,
        content_hash: str,
        size_bytes: int,
        stored_inline: bool,
    ) -> "StoredIconResult":
        """Create a success result."""
        return cls(
            success=True,
            icon_id=icon_id,
            agent_spec_id=agent_spec_id,
            icon_format=icon_format,
            content_hash=content_hash,
            size_bytes=size_bytes,
            stored_inline=stored_inline,
        )


@dataclass
class RetrievedIcon:
    """
    Result from retrieving an icon.

    Attributes:
        found: Whether an icon was found
        icon_data: The icon content (bytes or string)
        icon_format: Format of the icon
        content_type: MIME type for HTTP response headers
        content_hash: SHA256 hash of the icon content
        size_bytes: Size of the icon data
        is_placeholder: Whether this is a generated placeholder
        agent_spec_id: The AgentSpec this icon belongs to
        metadata: Additional icon metadata
    """

    found: bool
    icon_data: bytes | str | None = None
    icon_format: str | None = None
    content_type: str = "image/svg+xml"
    content_hash: str | None = None
    size_bytes: int = 0
    is_placeholder: bool = False
    agent_spec_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Don't include icon_data in dict representation (can be large)
        return {
            "found": self.found,
            "has_data": self.icon_data is not None,
            "icon_format": self.icon_format,
            "content_type": self.content_type,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "is_placeholder": self.is_placeholder,
            "agent_spec_id": self.agent_spec_id,
            "metadata": self.metadata,
        }

    def get_bytes(self) -> bytes | None:
        """Get icon data as bytes."""
        if self.icon_data is None:
            return None
        if isinstance(self.icon_data, bytes):
            return self.icon_data
        return self.icon_data.encode("utf-8")

    @classmethod
    def not_found(cls, agent_spec_id: str | None = None) -> "RetrievedIcon":
        """Create a not-found result."""
        return cls(found=False, agent_spec_id=agent_spec_id)

    @classmethod
    def placeholder(
        cls,
        icon_data: str,
        agent_spec_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "RetrievedIcon":
        """Create a placeholder icon result."""
        return cls(
            found=True,
            icon_data=icon_data,
            icon_format="svg",
            content_type="image/svg+xml",
            size_bytes=len(icon_data.encode("utf-8")),
            is_placeholder=True,
            agent_spec_id=agent_spec_id,
            metadata=metadata or {},
        )


# =============================================================================
# Database Model
# =============================================================================

class AgentIcon(Base):
    """
    Persisted icon for an AgentSpec.

    Feature #219: Generated icons stored and retrievable

    Each AgentSpec can have one associated icon. Icons are stored with:
    - Content-addressable storage (SHA256 hash)
    - Size-based routing (inline for small, file for large)
    - Format tracking for correct MIME type headers

    Attributes:
        id: Unique identifier
        agent_spec_id: Foreign key to agent_specs.id
        icon_format: Format of the icon (svg, png, jpeg, webp, icon_id, emoji)
        content_hash: SHA256 hash of icon content
        size_bytes: Size of icon data in bytes
        content_inline: Icon data for small icons (<= 16KB)
        content_ref: File path for large icons (> 16KB)
        provider_name: Name of the provider that generated this icon
        metadata: Additional icon metadata (JSON)
        created_at: When the icon was stored
    """

    __tablename__ = "agent_icons"

    __table_args__ = (
        Index('ix_agent_icons_spec', 'agent_spec_id'),
        Index('ix_agent_icons_hash', 'content_hash'),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_spec_id = Column(
        String(36),
        ForeignKey("agent_specs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One icon per AgentSpec
    )

    # Icon format (svg, png, jpeg, webp, icon_id, emoji)
    icon_format = Column(String(20), nullable=False, default="svg")

    # Content storage (same pattern as Artifact)
    content_hash = Column(String(64), nullable=False)  # SHA256
    size_bytes = Column(Integer, nullable=False)
    content_inline = Column(Text, nullable=True)  # For small icons (<= 16KB)
    content_ref = Column(String(255), nullable=True)  # File path for large icons

    # Provider info
    provider_name = Column(String(50), nullable=True)

    # Metadata
    icon_metadata = Column(JSON, nullable=True)  # Renamed from metadata to avoid SQLAlchemy reserved word
    created_at = Column(DateTime, nullable=False, default=_utc_now)

    # Relationship (optional - may not be loaded)
    # agent_spec = relationship("AgentSpec", backref="icon")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "agent_spec_id": self.agent_spec_id,
            "icon_format": self.icon_format,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "has_inline": self.content_inline is not None,
            "content_ref": self.content_ref,
            "provider_name": self.provider_name,
            "metadata": self.icon_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# =============================================================================
# Icon Storage Service
# =============================================================================

class IconStorage:
    """
    Content-addressable icon storage service.

    Feature #219: Generated icons stored and retrievable

    Stores agent icons with automatic size-based routing:
    - Small icons (<= 16KB) stored inline in database
    - Large icons stored as files with content-addressable paths

    Example:
        >>> storage = IconStorage("/path/to/project")
        >>> result = storage.store_icon(
        ...     session=db_session,
        ...     agent_spec_id="abc-123",
        ...     icon_data="<svg>...</svg>",
        ...     icon_format=IconFormat.SVG,
        ... )
        >>> retrieved = storage.retrieve_icon(session, "abc-123")
        >>> print(retrieved.content_type)  # "image/svg+xml"
    """

    def __init__(self, project_dir: str | Path):
        """
        Initialize the icon storage service.

        Args:
            project_dir: Project root directory where .autobuildr/icons will be created
        """
        self.project_dir = Path(project_dir).resolve()
        self.icons_base = self.project_dir / ".autobuildr" / "icons"

        _logger.debug(
            "IconStorage initialized: project_dir=%s, icons_base=%s",
            self.project_dir,
            self.icons_base,
        )

    def _compute_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    def _get_storage_path(self, content_hash: str, icon_format: str) -> Path:
        """
        Get the file path for storing icon content.

        Creates directory structure if needed:
        .autobuildr/icons/{hash}.{ext}

        Args:
            content_hash: SHA256 hash of content
            icon_format: Icon format (determines file extension)

        Returns:
            Absolute path to the storage file
        """
        # Map format to file extension
        ext_map = {
            "svg": "svg",
            "png": "png",
            "jpeg": "jpg",
            "webp": "webp",
            "icon_id": "txt",
            "emoji": "txt",
        }
        ext = ext_map.get(icon_format, "bin")
        return self.icons_base / f"{content_hash}.{ext}"

    def _ensure_directory(self, path: Path) -> None:
        """Ensure the parent directory exists."""
        path.parent.mkdir(parents=True, exist_ok=True)

    def _normalize_content(self, content: bytes | str) -> tuple[bytes, str | None]:
        """
        Normalize content to bytes and optionally get string representation.

        Args:
            content: Content as bytes or string

        Returns:
            Tuple of (bytes content, string content or None)
        """
        if isinstance(content, str):
            return content.encode("utf-8"), content
        return content, None

    def _normalize_format(self, icon_format: IconFormat | str) -> str:
        """
        Normalize icon format to string.

        Args:
            icon_format: IconFormat enum or string

        Returns:
            Format as lowercase string
        """
        if isinstance(icon_format, IconFormat):
            return icon_format.value
        return icon_format.lower()

    def store_icon(
        self,
        session: Session,
        agent_spec_id: str,
        icon_data: bytes | str,
        icon_format: IconFormat | str = IconFormat.SVG,
        *,
        provider_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        replace: bool = True,
    ) -> StoredIconResult:
        """
        Store an icon for an AgentSpec.

        Routes content based on size:
        - Content <= 16KB: stored in content_inline field
        - Content > 16KB: stored in file at .autobuildr/icons/{hash}.{ext}

        Args:
            session: SQLAlchemy database session
            agent_spec_id: ID of the AgentSpec this icon belongs to
            icon_data: Icon content (bytes or string)
            icon_format: Format of the icon (svg, png, etc.)
            provider_name: Optional name of the provider that generated this icon
            metadata: Optional icon metadata dict
            replace: If True, replace existing icon (default True)

        Returns:
            StoredIconResult with storage details

        Example:
            >>> storage = IconStorage("/path/to/project")
            >>> result = storage.store_icon(
            ...     session=db_session,
            ...     agent_spec_id="abc-123",
            ...     icon_data="<svg>...</svg>",
            ...     icon_format=IconFormat.SVG,
            ...     provider_name="local_placeholder",
            ... )
        """
        try:
            # Normalize format
            format_str = self._normalize_format(icon_format)

            # Normalize content to bytes
            content_bytes, content_str = self._normalize_content(icon_data)

            # Compute hash and size
            content_hash = self._compute_hash(content_bytes)
            size_bytes = len(content_bytes)

            _logger.debug(
                "Storing icon: agent_spec_id=%s, format=%s, size=%d, hash=%s...",
                agent_spec_id, format_str, size_bytes, content_hash[:16],
            )

            # Check for existing icon
            existing = (
                session.query(AgentIcon)
                .filter(AgentIcon.agent_spec_id == agent_spec_id)
                .first()
            )

            if existing:
                if not replace:
                    _logger.debug("Icon already exists for spec %s, not replacing", agent_spec_id)
                    return StoredIconResult.success_result(
                        icon_id=existing.id,
                        agent_spec_id=existing.agent_spec_id,
                        icon_format=existing.icon_format,
                        content_hash=existing.content_hash,
                        size_bytes=existing.size_bytes,
                        stored_inline=existing.content_inline is not None,
                    )
                else:
                    # Delete existing icon (and its file if any)
                    if existing.content_ref:
                        old_path = self.project_dir / existing.content_ref
                        if old_path.exists():
                            old_path.unlink()
                    session.delete(existing)
                    session.flush()
                    _logger.debug("Deleted existing icon for spec %s", agent_spec_id)

            # Create new icon record
            icon = AgentIcon(
                id=generate_uuid(),
                agent_spec_id=agent_spec_id,
                icon_format=format_str,
                content_hash=content_hash,
                size_bytes=size_bytes,
                provider_name=provider_name,
                icon_metadata=metadata,
            )

            stored_inline = False

            # Route based on size
            if size_bytes <= ICON_INLINE_MAX_SIZE:
                # Small content: store inline
                if content_str is None:
                    content_str = content_bytes.decode("utf-8", errors="replace")
                icon.content_inline = content_str
                stored_inline = True
                _logger.debug("Icon stored inline: %d bytes", size_bytes)
            else:
                # Large content: store in file
                storage_path = self._get_storage_path(content_hash, format_str)

                if not storage_path.exists():
                    self._ensure_directory(storage_path)
                    storage_path.write_bytes(content_bytes)
                    _logger.debug("Icon written to file: %s", storage_path)
                else:
                    _logger.debug("Icon file already exists (content-addressable dedup): %s", storage_path)

                # Store relative path from project root
                icon.content_ref = str(storage_path.relative_to(self.project_dir))
                _logger.debug("Icon stored in file: ref=%s", icon.content_ref)

            # Add to session
            session.add(icon)
            session.flush()

            _logger.info(
                "Stored icon for agent_spec_id=%s: id=%s, format=%s, size=%d",
                agent_spec_id, icon.id, format_str, size_bytes,
            )

            return StoredIconResult.success_result(
                icon_id=icon.id,
                agent_spec_id=agent_spec_id,
                icon_format=format_str,
                content_hash=content_hash,
                size_bytes=size_bytes,
                stored_inline=stored_inline,
            )

        except Exception as e:
            _logger.error("Failed to store icon for %s: %s", agent_spec_id, e)
            return StoredIconResult.error_result(str(e))

    def retrieve_icon(
        self,
        session: Session,
        agent_spec_id: str,
        *,
        generate_placeholder: bool = True,
        agent_name: str | None = None,
        role: str = "coder",
    ) -> RetrievedIcon:
        """
        Retrieve an icon for an AgentSpec.

        If no icon is stored and generate_placeholder is True, generates
        a placeholder icon using the LocalPlaceholderIconProvider.

        Args:
            session: SQLAlchemy database session
            agent_spec_id: ID of the AgentSpec to get icon for
            generate_placeholder: If True, generate placeholder if no icon exists
            agent_name: Agent name for placeholder generation (uses spec name if not provided)
            role: Agent role for placeholder generation

        Returns:
            RetrievedIcon with icon data and metadata

        Example:
            >>> storage = IconStorage("/path/to/project")
            >>> icon = storage.retrieve_icon(session, "abc-123")
            >>> if icon.found:
            ...     print(icon.content_type)  # "image/svg+xml"
            ...     print(icon.is_placeholder)  # True if no stored icon
        """
        # Query for existing icon
        icon = (
            session.query(AgentIcon)
            .filter(AgentIcon.agent_spec_id == agent_spec_id)
            .first()
        )

        if icon:
            # Retrieve stored icon content
            icon_data: bytes | str | None = None

            if icon.content_inline is not None:
                icon_data = icon.content_inline
            elif icon.content_ref:
                storage_path = self.project_dir / icon.content_ref
                if storage_path.exists():
                    icon_data = storage_path.read_bytes()
                else:
                    _logger.warning(
                        "Icon file not found: %s (icon_id=%s)",
                        storage_path, icon.id,
                    )

            if icon_data is not None:
                content_type = ICON_FORMAT_MIME_TYPES.get(icon.icon_format, "application/octet-stream")
                return RetrievedIcon(
                    found=True,
                    icon_data=icon_data,
                    icon_format=icon.icon_format,
                    content_type=content_type,
                    content_hash=icon.content_hash,
                    size_bytes=icon.size_bytes,
                    is_placeholder=False,
                    agent_spec_id=agent_spec_id,
                    metadata=icon.icon_metadata or {},
                )

        # No stored icon found - generate placeholder if requested
        if generate_placeholder:
            return self._generate_placeholder_icon(
                session, agent_spec_id, agent_name, role
            )

        return RetrievedIcon.not_found(agent_spec_id)

    def _generate_placeholder_icon(
        self,
        session: Session,
        agent_spec_id: str,
        agent_name: str | None,
        role: str,
    ) -> RetrievedIcon:
        """
        Generate a placeholder icon for an AgentSpec.

        Args:
            session: SQLAlchemy database session
            agent_spec_id: ID of the AgentSpec
            agent_name: Agent name for placeholder generation
            role: Agent role for placeholder generation

        Returns:
            RetrievedIcon with generated placeholder
        """
        # Get agent name from spec if not provided
        if agent_name is None:
            try:
                from api.agentspec_models import AgentSpec as AgentSpecModel
                spec = (
                    session.query(AgentSpecModel)
                    .filter(AgentSpecModel.id == agent_spec_id)
                    .first()
                )
                if spec:
                    agent_name = spec.name
            except Exception as e:
                _logger.debug("Could not get agent name from spec: %s", e)

        # Use agent_spec_id as fallback name
        if agent_name is None:
            agent_name = agent_spec_id[:8]

        # Generate placeholder using LocalPlaceholderIconProvider
        try:
            from api.local_placeholder_icon_provider import (
                LocalPlaceholderIconProvider,
                PlaceholderConfig,
            )

            provider = LocalPlaceholderIconProvider()
            result = provider.generate_icon(agent_name, role)

            if result.success and result.icon_data:
                return RetrievedIcon.placeholder(
                    icon_data=result.icon_data,
                    agent_spec_id=agent_spec_id,
                    metadata={
                        "agent_name": agent_name,
                        "role": role,
                        "provider": provider.name,
                        **result.metadata,
                    },
                )
        except Exception as e:
            _logger.warning("Failed to generate placeholder icon: %s", e)

        # Fallback: generate a minimal placeholder SVG
        fallback_svg = _generate_fallback_svg(agent_name or "?")
        return RetrievedIcon.placeholder(
            icon_data=fallback_svg,
            agent_spec_id=agent_spec_id,
            metadata={"fallback": True, "agent_name": agent_name},
        )

    def delete_icon(self, session: Session, agent_spec_id: str) -> bool:
        """
        Delete an icon for an AgentSpec.

        Args:
            session: SQLAlchemy database session
            agent_spec_id: ID of the AgentSpec

        Returns:
            True if icon was deleted, False if no icon existed
        """
        icon = (
            session.query(AgentIcon)
            .filter(AgentIcon.agent_spec_id == agent_spec_id)
            .first()
        )

        if not icon:
            return False

        # Delete file content if any
        if icon.content_ref:
            storage_path = self.project_dir / icon.content_ref
            if storage_path.exists():
                storage_path.unlink()
                _logger.debug("Deleted icon file: %s", storage_path)

        # Delete database record
        session.delete(icon)
        session.flush()

        _logger.info("Deleted icon for agent_spec_id=%s", agent_spec_id)
        return True

    def get_icon_info(self, session: Session, agent_spec_id: str) -> dict[str, Any] | None:
        """
        Get metadata about a stored icon without retrieving content.

        Args:
            session: SQLAlchemy database session
            agent_spec_id: ID of the AgentSpec

        Returns:
            Icon metadata dict, or None if no icon exists
        """
        icon = (
            session.query(AgentIcon)
            .filter(AgentIcon.agent_spec_id == agent_spec_id)
            .first()
        )

        if icon:
            return icon.to_dict()
        return None


# =============================================================================
# Helper Functions
# =============================================================================

def _generate_fallback_svg(name: str) -> str:
    """
    Generate a minimal fallback SVG when placeholder generation fails.

    Args:
        name: Name to display (first character used as initial)

    Returns:
        SVG string
    """
    initial = name[0].upper() if name else "?"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<circle cx="32" cy="32" r="30" fill="#6366f1"/>
<text x="32" y="32" font-family="Arial" font-size="28" font-weight="bold" fill="white" text-anchor="middle" dominant-baseline="central">{initial}</text>
</svg>'''


def get_mime_type_for_format(icon_format: IconFormat | str) -> str:
    """
    Get the MIME type for an icon format.

    Args:
        icon_format: IconFormat enum or string

    Returns:
        MIME type string (e.g., "image/svg+xml")
    """
    if isinstance(icon_format, IconFormat):
        format_str = icon_format.value
    else:
        format_str = icon_format.lower()

    return ICON_FORMAT_MIME_TYPES.get(format_str, "application/octet-stream")


def store_icon_from_result(
    storage: IconStorage,
    session: Session,
    agent_spec_id: str,
    icon_result: IconResult,
    *,
    replace: bool = True,
) -> StoredIconResult:
    """
    Store an icon from an IconResult (from icon provider).

    Convenience function to store the result of icon generation.

    Args:
        storage: IconStorage instance
        session: SQLAlchemy database session
        agent_spec_id: ID of the AgentSpec
        icon_result: Result from icon generation
        replace: If True, replace existing icon

    Returns:
        StoredIconResult with storage details
    """
    if not icon_result.success:
        return StoredIconResult.error_result(
            icon_result.error or "Icon generation failed"
        )

    if not icon_result.icon_data:
        return StoredIconResult.error_result("No icon data in result")

    return storage.store_icon(
        session=session,
        agent_spec_id=agent_spec_id,
        icon_data=icon_result.icon_data,
        icon_format=icon_result.format,
        provider_name=icon_result.provider_name,
        metadata=icon_result.metadata,
        replace=replace,
    )


def get_icon_storage(project_dir: str | Path) -> IconStorage:
    """
    Create an IconStorage instance for a project.

    Args:
        project_dir: Path to project directory

    Returns:
        IconStorage instance
    """
    return IconStorage(project_dir)
