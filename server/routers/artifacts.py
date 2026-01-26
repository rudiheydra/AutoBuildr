"""
Artifacts Router
================

API endpoints for Artifact content retrieval.

Implements:
- GET /api/artifacts/:id/content - Download artifact content
"""

import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from api.agentspec_crud import get_artifact, get_artifact_content
from api.database import get_db

# Project root directory for resolving content_ref paths
ROOT_DIR = Path(__file__).parent.parent.parent


router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def _guess_content_type(artifact) -> str:
    """Guess the content type based on artifact path or type.

    Args:
        artifact: The Artifact instance

    Returns:
        MIME type string (defaults to application/octet-stream)
    """
    # Try to guess from the path
    if artifact.path:
        mime_type, _ = mimetypes.guess_type(artifact.path)
        if mime_type:
            return mime_type

    # Default to application/octet-stream for binary data
    # or text/plain for small inline content
    if artifact.content_inline is not None:
        return "text/plain; charset=utf-8"

    return "application/octet-stream"


def _generate_file_chunks(file_path: Path, chunk_size: int = 8192):
    """Generator that yields file content in chunks for streaming.

    Args:
        file_path: Path to the file to stream
        chunk_size: Size of each chunk in bytes

    Yields:
        Bytes chunks of file content
    """
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            yield chunk


@router.get("/{artifact_id}/content")
async def download_artifact_content(
    artifact_id: str,
    db: Session = Depends(get_db),
):
    """
    Download artifact content either inline or from file.

    This endpoint retrieves the actual content of an artifact:
    - For small artifacts (<=4KB), content is stored inline and returned directly
    - For large artifacts, content is stored in files and streamed

    The response includes appropriate Content-Type and Content-Disposition headers
    for download.

    Args:
        artifact_id: UUID of the Artifact

    Returns:
        Response with artifact content, appropriate Content-Type, and
        Content-Disposition header for download

    Raises:
        404: If the Artifact is not found
        404: If the artifact references a file that no longer exists
    """
    # Query artifact by ID
    artifact = get_artifact(db, artifact_id)
    if not artifact:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found"
        )

    # Determine content type
    content_type = _guess_content_type(artifact)

    # Generate filename for Content-Disposition
    if artifact.path:
        filename = Path(artifact.path).name
    else:
        # Generate a filename from artifact type and hash
        extension = ".txt" if "text" in content_type else ".bin"
        hash_prefix = (artifact.content_hash or "unknown")[:8]
        filename = f"{artifact.artifact_type}_{hash_prefix}{extension}"

    # If content is inline, return it directly
    if artifact.content_inline is not None:
        return Response(
            content=artifact.content_inline.encode("utf-8"),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(artifact.content_inline.encode("utf-8"))),
                "X-Artifact-Id": artifact_id,
                "X-Content-Hash": artifact.content_hash or "",
            }
        )

    # Content is stored in file - verify file exists
    if not artifact.content_ref:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} has no content reference"
        )

    # Resolve the file path
    file_path = ROOT_DIR / artifact.content_ref
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact content file not found: {artifact.content_ref}"
        )

    # Stream file content
    file_size = file_path.stat().st_size

    return StreamingResponse(
        _generate_file_chunks(file_path),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
            "X-Artifact-Id": artifact_id,
            "X-Content-Hash": artifact.content_hash or "",
        }
    )
