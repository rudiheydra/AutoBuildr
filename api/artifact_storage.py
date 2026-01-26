"""
Artifact Storage Service
========================

Content-addressable artifact storage with SHA256 hashing.

This service handles:
- Small content (<=4KB) stored inline in the database
- Large content stored as files in .autobuildr/artifacts/{run_id}/{hash}.blob
- Content deduplication via SHA256 hashing
- Automatic directory creation

Usage:
    from api.artifact_storage import ArtifactStorage

    storage = ArtifactStorage(project_dir)
    artifact = storage.store(
        session=db_session,
        run_id="uuid-here",
        artifact_type="log",
        content="Some log content..."
    )
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.agentspec_models import (
    ARTIFACT_INLINE_MAX_SIZE,
    ARTIFACT_TYPES,
    Artifact,
    generate_uuid,
)

# Configure logging
_logger = logging.getLogger(__name__)


class ArtifactStorage:
    """
    Content-addressable artifact storage service.

    Stores artifacts with automatic size-based routing:
    - Small artifacts (<=4KB) are stored inline in the database
    - Large artifacts are stored as files with content-addressable paths

    Attributes:
        project_dir: Base directory for file storage
        artifacts_base: Path to .autobuildr/artifacts directory
    """

    def __init__(self, project_dir: str | Path):
        """
        Initialize the artifact storage service.

        Args:
            project_dir: Project root directory where .autobuildr/artifacts will be created
        """
        self.project_dir = Path(project_dir).resolve()
        self.artifacts_base = self.project_dir / ".autobuildr" / "artifacts"

        _logger.debug(
            "ArtifactStorage initialized: project_dir=%s, artifacts_base=%s",
            self.project_dir,
            self.artifacts_base
        )

    def _compute_hash(self, content: bytes) -> str:
        """
        Compute SHA256 hash of content.

        Args:
            content: Binary content to hash

        Returns:
            Lowercase hex string of SHA256 hash (64 characters)
        """
        return hashlib.sha256(content).hexdigest()

    def _get_storage_path(self, run_id: str, content_hash: str) -> Path:
        """
        Get the file path for storing artifact content.

        Creates the directory structure if needed:
        .autobuildr/artifacts/{run_id}/{content_hash}.blob

        Args:
            run_id: AgentRun ID (used as directory name)
            content_hash: SHA256 hash of content (used as filename)

        Returns:
            Absolute path to the storage file
        """
        run_dir = self.artifacts_base / run_id
        return run_dir / f"{content_hash}.blob"

    def _ensure_directory(self, path: Path) -> None:
        """
        Ensure the parent directory exists.

        Args:
            path: Path whose parent directory should exist
        """
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

    def _find_existing_by_hash(
        self,
        session: Session,
        run_id: str,
        content_hash: str
    ) -> Artifact | None:
        """
        Find an existing artifact with the same hash in the same run.

        This enables content deduplication within a run.

        Args:
            session: SQLAlchemy session
            run_id: AgentRun ID
            content_hash: SHA256 hash to search for

        Returns:
            Existing Artifact if found, None otherwise
        """
        return (
            session.query(Artifact)
            .filter(
                Artifact.run_id == run_id,
                Artifact.content_hash == content_hash
            )
            .first()
        )

    def store(
        self,
        session: Session,
        run_id: str,
        artifact_type: str,
        content: bytes | str,
        *,
        path: str | None = None,
        metadata: dict[str, Any] | None = None,
        deduplicate: bool = True,
    ) -> Artifact:
        """
        Store an artifact with content-addressing.

        Routes content based on size:
        - Content <= 4096 bytes: stored in content_inline field
        - Content > 4096 bytes: stored in file at .autobuildr/artifacts/{run_id}/{hash}.blob

        Args:
            session: SQLAlchemy database session
            run_id: ID of the AgentRun this artifact belongs to
            artifact_type: Type of artifact (file_change, test_result, log, metric, snapshot)
            content: Content to store (bytes or string)
            path: Optional source path for file artifacts
            metadata: Optional type-specific metadata dict
            deduplicate: If True, return existing artifact with same hash (default True)

        Returns:
            Created (or existing if deduplicated) Artifact record

        Raises:
            ValueError: If artifact_type is invalid

        Example:
            >>> storage = ArtifactStorage("/path/to/project")
            >>> artifact = storage.store(
            ...     session=db_session,
            ...     run_id="abc-123",
            ...     artifact_type="log",
            ...     content="Build completed successfully"
            ... )
            >>> print(artifact.content_hash)  # SHA256 hash
            >>> print(artifact.size_bytes)    # Content size
        """
        # Validate artifact type
        if artifact_type not in ARTIFACT_TYPES:
            raise ValueError(
                f"Invalid artifact_type '{artifact_type}'. "
                f"Must be one of: {', '.join(ARTIFACT_TYPES)}"
            )

        # Normalize content to bytes
        content_bytes, content_str = self._normalize_content(content)

        # Compute hash and size
        content_hash = self._compute_hash(content_bytes)
        size_bytes = len(content_bytes)

        _logger.debug(
            "Storing artifact: run_id=%s, type=%s, size=%d, hash=%s",
            run_id, artifact_type, size_bytes, content_hash[:16] + "..."
        )

        # Check for deduplication
        if deduplicate:
            existing = self._find_existing_by_hash(session, run_id, content_hash)
            if existing:
                _logger.info(
                    "Artifact deduplicated: found existing artifact %s with same hash",
                    existing.id
                )
                return existing

        # Create artifact record
        artifact = Artifact(
            id=generate_uuid(),
            run_id=run_id,
            artifact_type=artifact_type,
            path=path,
            content_hash=content_hash,
            size_bytes=size_bytes,
            artifact_metadata=metadata,
        )

        # Route based on size
        if size_bytes <= ARTIFACT_INLINE_MAX_SIZE:
            # Small content: store inline
            if content_str is None:
                # Decode bytes to string for inline storage
                content_str = content_bytes.decode("utf-8", errors="replace")
            artifact.content_inline = content_str

            _logger.debug("Artifact stored inline: %s (%d bytes)", artifact.id, size_bytes)
        else:
            # Large content: store in file
            storage_path = self._get_storage_path(run_id, content_hash)

            # Check if file already exists (content-addressable deduplication)
            if not storage_path.exists():
                self._ensure_directory(storage_path)
                storage_path.write_bytes(content_bytes)
                _logger.debug(
                    "Artifact content written to file: %s",
                    storage_path
                )
            else:
                _logger.debug(
                    "Artifact file already exists (content-addressable dedup): %s",
                    storage_path
                )

            # Store relative path from project root
            artifact.content_ref = str(storage_path.relative_to(self.project_dir))

            _logger.debug(
                "Artifact stored in file: %s (%d bytes), ref=%s",
                artifact.id, size_bytes, artifact.content_ref
            )

        # Add to session
        session.add(artifact)
        session.flush()

        return artifact

    def retrieve(
        self,
        artifact: Artifact,
    ) -> bytes | None:
        """
        Retrieve artifact content.

        Args:
            artifact: Artifact record to retrieve content from

        Returns:
            Content as bytes, or None if content not available
        """
        # Try inline content first
        if artifact.content_inline is not None:
            return artifact.content_inline.encode("utf-8")

        # Try file-based content
        if artifact.content_ref:
            storage_path = self.project_dir / artifact.content_ref
            if storage_path.exists():
                return storage_path.read_bytes()
            else:
                _logger.warning(
                    "Artifact file not found: %s (artifact_id=%s)",
                    storage_path, artifact.id
                )

        return None

    def retrieve_string(
        self,
        artifact: Artifact,
        encoding: str = "utf-8",
        errors: str = "replace",
    ) -> str | None:
        """
        Retrieve artifact content as string.

        Args:
            artifact: Artifact record to retrieve content from
            encoding: Text encoding (default: utf-8)
            errors: How to handle decoding errors (default: replace)

        Returns:
            Content as string, or None if content not available
        """
        content = self.retrieve(artifact)
        if content is not None:
            return content.decode(encoding, errors=errors)
        return None

    def delete_content(self, artifact: Artifact) -> bool:
        """
        Delete the file content for a file-based artifact.

        Note: This does NOT delete the artifact record from the database.

        Args:
            artifact: Artifact record

        Returns:
            True if file was deleted, False if no file or already deleted
        """
        if artifact.content_ref:
            storage_path = self.project_dir / artifact.content_ref
            if storage_path.exists():
                storage_path.unlink()
                _logger.info("Deleted artifact file: %s", storage_path)
                return True
        return False

    def get_storage_stats(self) -> dict[str, Any]:
        """
        Get statistics about artifact storage.

        Returns:
            Dictionary with storage statistics
        """
        total_files = 0
        total_bytes = 0
        run_dirs: set[str] = set()

        if self.artifacts_base.exists():
            for run_dir in self.artifacts_base.iterdir():
                if run_dir.is_dir():
                    run_dirs.add(run_dir.name)
                    for blob_file in run_dir.glob("*.blob"):
                        total_files += 1
                        total_bytes += blob_file.stat().st_size

        return {
            "artifacts_base": str(self.artifacts_base),
            "run_count": len(run_dirs),
            "file_count": total_files,
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }
