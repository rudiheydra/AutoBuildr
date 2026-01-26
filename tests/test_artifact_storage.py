"""
Tests for ArtifactStorage Service
=================================

Comprehensive tests verifying:
1. ArtifactStorage class creation with store() method
2. SHA256 hash computation
3. Size threshold check (4096 bytes)
4. Inline storage for small content
5. File storage for large content
6. Content deduplication via hash
"""
import hashlib
import os
import pytest
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Import the models and storage class
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Base
from api.agentspec_models import (
    ARTIFACT_INLINE_MAX_SIZE,
    ARTIFACT_TYPES,
    AgentRun,
    AgentSpec,
    Artifact,
    generate_uuid,
)
from api.artifact_storage import ArtifactStorage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_session(temp_project_dir):
    """Create an in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def storage(temp_project_dir):
    """Create an ArtifactStorage instance."""
    return ArtifactStorage(temp_project_dir)


@pytest.fixture
def agent_spec(db_session):
    """Create a test AgentSpec."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec",
        display_name="Test Spec",
        objective="Test objective",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": []},
    )
    db_session.add(spec)
    db_session.flush()
    return spec


@pytest.fixture
def agent_run(db_session, agent_spec):
    """Create a test AgentRun."""
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=agent_spec.id,
        status="running",
    )
    db_session.add(run)
    db_session.flush()
    return run


# =============================================================================
# Step 1: Create ArtifactStorage class with store(run_id, type, content, path)
# =============================================================================

class TestArtifactStorageClass:
    """Tests for ArtifactStorage class creation and store method."""

    def test_storage_initialization(self, temp_project_dir):
        """ArtifactStorage initializes with project directory."""
        storage = ArtifactStorage(temp_project_dir)
        assert storage.project_dir == temp_project_dir
        assert storage.artifacts_base == temp_project_dir / ".autobuildr" / "artifacts"

    def test_storage_accepts_string_path(self, temp_project_dir):
        """ArtifactStorage accepts string path."""
        storage = ArtifactStorage(str(temp_project_dir))
        assert storage.project_dir == temp_project_dir

    def test_store_method_exists(self, storage):
        """store() method exists with correct signature."""
        assert hasattr(storage, "store")
        assert callable(storage.store)

    def test_store_returns_artifact(self, storage, db_session, agent_run):
        """store() returns an Artifact record."""
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content="Test content",
        )
        assert isinstance(artifact, Artifact)

    def test_store_with_path_parameter(self, storage, db_session, agent_run):
        """store() accepts optional path parameter."""
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="file_change",
            content="file content",
            path="/src/main.py",
        )
        assert artifact.path == "/src/main.py"

    def test_store_validates_artifact_type(self, storage, db_session, agent_run):
        """store() validates artifact_type against allowed types."""
        with pytest.raises(ValueError) as exc:
            storage.store(
                session=db_session,
                run_id=agent_run.id,
                artifact_type="invalid_type",
                content="content",
            )
        assert "invalid_type" in str(exc.value)
        assert "file_change" in str(exc.value)  # Should show valid types

    def test_all_artifact_types_accepted(self, storage, db_session, agent_run):
        """store() accepts all valid artifact types."""
        for artifact_type in ARTIFACT_TYPES:
            artifact = storage.store(
                session=db_session,
                run_id=agent_run.id,
                artifact_type=artifact_type,
                content=f"content for {artifact_type}",
            )
            assert artifact.artifact_type == artifact_type


# =============================================================================
# Step 2: Compute SHA256 hash of content
# =============================================================================

class TestSHA256Hashing:
    """Tests for SHA256 hash computation."""

    def test_hash_computed_for_string_content(self, storage, db_session, agent_run):
        """SHA256 hash is computed for string content."""
        content = "Hello, World!"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert artifact.content_hash == expected_hash

    def test_hash_computed_for_bytes_content(self, storage, db_session, agent_run):
        """SHA256 hash is computed for bytes content."""
        content = b"Binary content \x00\x01\x02"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        expected_hash = hashlib.sha256(content).hexdigest()
        assert artifact.content_hash == expected_hash

    def test_hash_is_64_characters(self, storage, db_session, agent_run):
        """SHA256 hash is 64 hex characters."""
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content="any content",
        )
        assert len(artifact.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in artifact.content_hash)

    def test_hash_is_deterministic(self, storage, db_session, agent_run):
        """Same content produces same hash."""
        content = "Deterministic test"

        artifact1 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
            deduplicate=False,
        )
        artifact2 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
            deduplicate=False,
        )

        assert artifact1.content_hash == artifact2.content_hash

    def test_different_content_different_hash(self, storage, db_session, agent_run):
        """Different content produces different hash."""
        artifact1 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content="Content A",
        )
        artifact2 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content="Content B",
        )
        assert artifact1.content_hash != artifact2.content_hash


# =============================================================================
# Step 3: Check content size against ARTIFACT_INLINE_MAX_SIZE (4096 bytes)
# =============================================================================

class TestSizeThreshold:
    """Tests for size threshold checking."""

    def test_inline_max_size_is_4096(self):
        """ARTIFACT_INLINE_MAX_SIZE is 4096 bytes."""
        assert ARTIFACT_INLINE_MAX_SIZE == 4096

    def test_size_bytes_recorded(self, storage, db_session, agent_run):
        """size_bytes is recorded correctly."""
        content = "Test content"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        assert artifact.size_bytes == len(content.encode("utf-8"))

    def test_size_bytes_for_unicode(self, storage, db_session, agent_run):
        """size_bytes counts UTF-8 encoded bytes, not characters."""
        # Unicode content with multi-byte characters
        content = "Hello, "  # Each emoji is 4 bytes
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        # 7 ASCII chars + 4 bytes * 3 emojis = 7 + 12 = 19 bytes
        assert artifact.size_bytes == len(content.encode("utf-8"))


# =============================================================================
# Step 4: If small, store in content_inline field
# =============================================================================

class TestInlineStorage:
    """Tests for inline storage of small content."""

    def test_small_content_stored_inline(self, storage, db_session, agent_run):
        """Content <= 4096 bytes is stored in content_inline."""
        content = "Small content"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        assert artifact.content_inline == content
        assert artifact.content_ref is None

    def test_exact_threshold_stored_inline(self, storage, db_session, agent_run):
        """Content exactly 4096 bytes is stored inline."""
        content = "x" * 4096
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        assert artifact.content_inline == content
        assert artifact.content_ref is None
        assert artifact.size_bytes == 4096

    def test_bytes_content_converted_to_string_for_inline(self, storage, db_session, agent_run):
        """Bytes content is converted to string for inline storage."""
        content = b"Binary content"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        assert artifact.content_inline == content.decode("utf-8")

    def test_no_file_created_for_inline(self, storage, db_session, agent_run, temp_project_dir):
        """No file is created for inline content."""
        content = "Small content"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        # Check no artifact directory created
        artifacts_dir = temp_project_dir / ".autobuildr" / "artifacts" / agent_run.id
        assert not artifacts_dir.exists() or not any(artifacts_dir.glob("*.blob"))


# =============================================================================
# Step 5: If large, write to file .autobuildr/artifacts/{run_id}/{hash}.blob
# =============================================================================

class TestFileStorage:
    """Tests for file storage of large content."""

    def test_large_content_stored_in_file(self, storage, db_session, agent_run):
        """Content > 4096 bytes is stored in file."""
        content = "x" * 4097
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        assert artifact.content_inline is None
        assert artifact.content_ref is not None

    def test_file_path_format(self, storage, db_session, agent_run):
        """File is stored at .autobuildr/artifacts/{run_id}/{hash}.blob."""
        content = "x" * 5000
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        expected_path = f".autobuildr/artifacts/{agent_run.id}/{artifact.content_hash}.blob"
        assert artifact.content_ref == expected_path

    def test_file_content_matches(self, storage, db_session, agent_run, temp_project_dir):
        """File content matches original content."""
        content = "Large content " * 500  # > 4KB
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        file_path = temp_project_dir / artifact.content_ref
        assert file_path.exists()
        assert file_path.read_text() == content

    def test_file_storage_with_bytes(self, storage, db_session, agent_run, temp_project_dir):
        """Bytes content is stored correctly in file."""
        content = b"\x00" * 5000  # Binary content > 4KB
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        file_path = temp_project_dir / artifact.content_ref
        assert file_path.exists()
        assert file_path.read_bytes() == content


# =============================================================================
# Step 6: Create parent directories if needed
# =============================================================================

class TestDirectoryCreation:
    """Tests for automatic directory creation."""

    def test_directories_created_automatically(self, storage, db_session, agent_run, temp_project_dir):
        """Directories are created automatically for file storage."""
        # Initially no artifacts directory
        artifacts_dir = temp_project_dir / ".autobuildr" / "artifacts"
        assert not artifacts_dir.exists()

        # Store large content
        content = "x" * 5000
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        # Now directories exist
        run_dir = artifacts_dir / agent_run.id
        assert run_dir.exists()
        assert run_dir.is_dir()

    def test_multiple_runs_separate_directories(
        self, storage, db_session, agent_spec, temp_project_dir
    ):
        """Each run gets its own directory."""
        run1 = AgentRun(id=generate_uuid(), agent_spec_id=agent_spec.id, status="running")
        run2 = AgentRun(id=generate_uuid(), agent_spec_id=agent_spec.id, status="running")
        db_session.add_all([run1, run2])
        db_session.flush()

        content = "x" * 5000
        storage.store(session=db_session, run_id=run1.id, artifact_type="log", content=content)
        storage.store(session=db_session, run_id=run2.id, artifact_type="log", content=content)

        artifacts_dir = temp_project_dir / ".autobuildr" / "artifacts"
        assert (artifacts_dir / run1.id).exists()
        assert (artifacts_dir / run2.id).exists()


# =============================================================================
# Step 7: Set content_ref to file path (covered in Step 5)
# =============================================================================

# See test_file_path_format in TestFileStorage


# =============================================================================
# Step 8: Set size_bytes to content length (covered in Step 3)
# =============================================================================

# See test_size_bytes_recorded in TestSizeThreshold


# =============================================================================
# Step 9: Check for existing artifact with same hash (deduplication)
# =============================================================================

class TestDeduplication:
    """Tests for content deduplication."""

    def test_deduplication_returns_existing(self, storage, db_session, agent_run):
        """Duplicate content returns existing artifact when deduplicate=True."""
        content = "Duplicate content"

        artifact1 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )
        artifact2 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        # Same artifact returned
        assert artifact1.id == artifact2.id

    def test_deduplication_disabled(self, storage, db_session, agent_run):
        """deduplicate=False creates new artifact."""
        content = "Duplicate content"

        artifact1 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
            deduplicate=False,
        )
        artifact2 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
            deduplicate=False,
        )

        # Different artifacts created
        assert artifact1.id != artifact2.id
        assert artifact1.content_hash == artifact2.content_hash

    def test_deduplication_file_not_duplicated(
        self, storage, db_session, agent_run, temp_project_dir
    ):
        """Large content file is not duplicated on disk."""
        content = "x" * 5000

        artifact1 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
            deduplicate=False,
        )
        artifact2 = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
            deduplicate=False,
        )

        # Same file used (content-addressable)
        assert artifact1.content_ref == artifact2.content_ref

        # Only one file on disk
        run_dir = temp_project_dir / ".autobuildr" / "artifacts" / agent_run.id
        blob_files = list(run_dir.glob("*.blob"))
        assert len(blob_files) == 1


# =============================================================================
# Step 10: Return Artifact record (covered throughout)
# =============================================================================

class TestReturnArtifact:
    """Tests for Artifact record return."""

    def test_artifact_has_all_fields(self, storage, db_session, agent_run):
        """Returned artifact has all required fields."""
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content="content",
            path="/test/path",
            metadata={"key": "value"},
        )

        assert artifact.id is not None
        assert artifact.run_id == agent_run.id
        assert artifact.artifact_type == "log"
        assert artifact.path == "/test/path"
        assert artifact.content_hash is not None
        assert artifact.size_bytes is not None
        assert artifact.artifact_metadata == {"key": "value"}

    def test_artifact_in_database(self, storage, db_session, agent_run):
        """Artifact is saved to database."""
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content="content",
        )

        # Query from database
        queried = db_session.query(Artifact).filter(Artifact.id == artifact.id).first()
        assert queried is not None
        assert queried.content_hash == artifact.content_hash


# =============================================================================
# Additional: Retrieve functionality
# =============================================================================

class TestRetrieve:
    """Tests for content retrieval."""

    def test_retrieve_inline_content(self, storage, db_session, agent_run):
        """retrieve() returns inline content."""
        content = "Inline content"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        retrieved = storage.retrieve(artifact)
        assert retrieved == content.encode("utf-8")

    def test_retrieve_file_content(self, storage, db_session, agent_run):
        """retrieve() returns file-based content."""
        content = "x" * 5000
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        retrieved = storage.retrieve(artifact)
        assert retrieved == content.encode("utf-8")

    def test_retrieve_string(self, storage, db_session, agent_run):
        """retrieve_string() returns content as string."""
        content = "String content"
        artifact = storage.store(
            session=db_session,
            run_id=agent_run.id,
            artifact_type="log",
            content=content,
        )

        retrieved = storage.retrieve_string(artifact)
        assert retrieved == content


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
