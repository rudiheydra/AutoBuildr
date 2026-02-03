"""
Tests for Feature #219: Generated icons stored and retrievable

Feature Steps:
1. Icon data stored in database or filesystem
2. Icon linked to AgentSpec by agent_spec_id
3. GET /api/agents/{id}/icon endpoint returns icon
4. Icon format header set appropriately (image/svg+xml, image/png)
5. Missing icon returns default placeholder

These tests verify the complete icon storage and retrieval system.
"""
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_db_session(temp_project_dir):
    """Create a test database session."""
    # Create test database
    db_path = temp_project_dir / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Try to create AgentIcon table specifically
    try:
        from api.icon_storage import AgentIcon
        AgentIcon.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        pass

    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_svg_icon():
    """Sample SVG icon for testing."""
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">
<circle cx="32" cy="32" r="30" fill="#6366f1"/>
<text x="32" y="32" font-family="Arial" font-size="28" fill="white" text-anchor="middle" dominant-baseline="central">T</text>
</svg>'''


@pytest.fixture
def sample_agent_spec_id():
    """Sample agent spec ID for testing."""
    return "test-spec-12345678-1234-1234-1234-123456789abc"


# =============================================================================
# Test Step 1: Icon data stored in database or filesystem
# =============================================================================

class TestStep1IconDataStorage:
    """Tests for icon data storage in database or filesystem."""

    def test_icon_storage_class_exists(self):
        """IconStorage class should exist."""
        from api.icon_storage import IconStorage
        assert IconStorage is not None

    def test_icon_storage_initialization(self, temp_project_dir):
        """IconStorage should initialize with project directory."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        assert storage.project_dir == temp_project_dir.resolve()
        assert storage.icons_base == temp_project_dir.resolve() / ".autobuildr" / "icons"

    def test_store_small_icon_inline(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Small icons should be stored inline in database."""
        from api.icon_storage import IconStorage, ICON_INLINE_MAX_SIZE

        storage = IconStorage(temp_project_dir)

        # Store a small icon
        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        assert result.success
        assert result.icon_id is not None
        assert result.agent_spec_id == sample_agent_spec_id
        assert result.stored_inline  # Small icons stored inline
        assert result.size_bytes < ICON_INLINE_MAX_SIZE

    def test_store_large_icon_in_file(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """Large icons should be stored in filesystem."""
        from api.icon_storage import IconStorage, ICON_INLINE_MAX_SIZE

        storage = IconStorage(temp_project_dir)

        # Create a large icon (>16KB)
        large_icon = "<svg>" + ("x" * (ICON_INLINE_MAX_SIZE + 1000)) + "</svg>"

        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=large_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        assert result.success
        assert result.icon_id is not None
        assert not result.stored_inline  # Large icons stored in file

        # Verify file exists
        from api.icon_storage import AgentIcon
        icon_record = test_db_session.query(AgentIcon).filter(
            AgentIcon.agent_spec_id == sample_agent_spec_id
        ).first()

        assert icon_record is not None
        assert icon_record.content_ref is not None
        file_path = temp_project_dir / icon_record.content_ref
        assert file_path.exists()

    def test_icon_content_hash_computed(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Icon content hash should be computed correctly."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Verify hash matches
        expected_hash = hashlib.sha256(sample_svg_icon.encode("utf-8")).hexdigest()
        assert result.content_hash == expected_hash

    def test_icon_format_stored(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Icon format should be stored correctly."""
        from api.icon_storage import IconStorage, AgentIcon

        storage = IconStorage(temp_project_dir)

        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        assert result.icon_format == "svg"

        # Verify in database
        icon = test_db_session.query(AgentIcon).filter(
            AgentIcon.id == result.icon_id
        ).first()
        assert icon.icon_format == "svg"


# =============================================================================
# Test Step 2: Icon linked to AgentSpec by agent_spec_id
# =============================================================================

class TestStep2IconLinkedToAgentSpec:
    """Tests for icon linkage to AgentSpec."""

    def test_icon_has_agent_spec_id_field(self):
        """AgentIcon should have agent_spec_id field."""
        from api.icon_storage import AgentIcon

        assert hasattr(AgentIcon, 'agent_spec_id')

    def test_icon_foreign_key_constraint(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Icon should be linked to AgentSpec by agent_spec_id."""
        from api.icon_storage import IconStorage, AgentIcon

        storage = IconStorage(temp_project_dir)

        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Query by agent_spec_id
        icon = test_db_session.query(AgentIcon).filter(
            AgentIcon.agent_spec_id == sample_agent_spec_id
        ).first()

        assert icon is not None
        assert icon.id == result.icon_id

    def test_one_icon_per_agent_spec(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Each AgentSpec should have at most one icon."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store first icon
        result1 = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Store second icon (should replace)
        new_icon = '<svg><circle fill="#ff0000"/></svg>'
        result2 = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=new_icon,
            icon_format="svg",
            replace=True,
        )
        test_db_session.commit()

        # First icon should be replaced
        assert result1.icon_id != result2.icon_id

        # Query should return only one icon
        from api.icon_storage import AgentIcon
        icons = test_db_session.query(AgentIcon).filter(
            AgentIcon.agent_spec_id == sample_agent_spec_id
        ).all()

        assert len(icons) == 1
        assert icons[0].id == result2.icon_id

    def test_retrieve_by_agent_spec_id(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Icon should be retrievable by agent_spec_id."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store icon
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Retrieve by agent_spec_id
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.found
        assert retrieved.agent_spec_id == sample_agent_spec_id
        assert retrieved.icon_data == sample_svg_icon


# =============================================================================
# Test Step 3: GET /api/agents/{id}/icon endpoint returns icon
# =============================================================================

class TestStep3IconEndpoint:
    """Tests for icon retrieval endpoint."""

    def test_retrieve_icon_success(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """retrieve_icon should return stored icon data."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store icon
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Retrieve
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
        )

        assert retrieved.found
        assert retrieved.icon_data == sample_svg_icon
        assert not retrieved.is_placeholder

    def test_retrieve_icon_returns_bytes(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """get_bytes() should return icon data as bytes."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store icon
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Retrieve
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
        )

        icon_bytes = retrieved.get_bytes()
        assert isinstance(icon_bytes, bytes)
        assert icon_bytes == sample_svg_icon.encode("utf-8")

    def test_retrieve_large_icon_from_file(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """Large icons should be retrieved from filesystem."""
        from api.icon_storage import IconStorage, ICON_INLINE_MAX_SIZE

        storage = IconStorage(temp_project_dir)

        # Create and store large icon
        large_icon = "<svg>" + ("x" * (ICON_INLINE_MAX_SIZE + 1000)) + "</svg>"
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=large_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Retrieve
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.found
        assert retrieved.icon_data == large_icon.encode("utf-8")


# =============================================================================
# Test Step 4: Icon format header set appropriately
# =============================================================================

class TestStep4IconFormatHeaders:
    """Tests for icon format and MIME type handling."""

    def test_svg_content_type(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """SVG icons should have image/svg+xml content type."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
        )

        assert retrieved.content_type == "image/svg+xml"

    def test_png_content_type(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """PNG icons should have image/png content type."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store PNG-format icon (using dummy data)
        png_data = b"PNG_DUMMY_DATA"
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=png_data,
            icon_format="png",
        )
        test_db_session.commit()

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.content_type == "image/png"

    def test_jpeg_content_type(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """JPEG icons should have image/jpeg content type."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        jpeg_data = b"JPEG_DUMMY_DATA"
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=jpeg_data,
            icon_format="jpeg",
        )
        test_db_session.commit()

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.content_type == "image/jpeg"

    def test_webp_content_type(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """WebP icons should have image/webp content type."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        webp_data = b"WEBP_DUMMY_DATA"
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=webp_data,
            icon_format="webp",
        )
        test_db_session.commit()

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.content_type == "image/webp"

    def test_get_mime_type_for_format(self):
        """get_mime_type_for_format should return correct MIME types."""
        from api.icon_storage import get_mime_type_for_format
        from api.icon_provider import IconFormat

        assert get_mime_type_for_format(IconFormat.SVG) == "image/svg+xml"
        assert get_mime_type_for_format(IconFormat.PNG) == "image/png"
        assert get_mime_type_for_format(IconFormat.JPEG) == "image/jpeg"
        assert get_mime_type_for_format(IconFormat.WEBP) == "image/webp"
        assert get_mime_type_for_format("svg") == "image/svg+xml"
        assert get_mime_type_for_format("png") == "image/png"


# =============================================================================
# Test Step 5: Missing icon returns default placeholder
# =============================================================================

class TestStep5MissingIconPlaceholder:
    """Tests for placeholder icon generation."""

    def test_missing_icon_generates_placeholder(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """Missing icon should generate placeholder when requested."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Retrieve non-existent icon
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=True,
            agent_name="test-agent",
        )

        assert retrieved.found
        assert retrieved.is_placeholder
        assert retrieved.icon_data is not None
        assert "<svg" in retrieved.icon_data  # Should be SVG

    def test_missing_icon_returns_not_found_when_placeholder_disabled(
        self, temp_project_dir, test_db_session, sample_agent_spec_id
    ):
        """Missing icon should return not_found when placeholder disabled."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Retrieve non-existent icon without placeholder
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert not retrieved.found
        assert retrieved.icon_data is None

    def test_placeholder_has_svg_content_type(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """Placeholder icon should have SVG content type."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=True,
            agent_name="test-agent",
        )

        assert retrieved.content_type == "image/svg+xml"

    def test_placeholder_uses_agent_name(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """Placeholder should use agent name for generation."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=True,
            agent_name="auth-login-handler",
        )

        assert retrieved.found
        assert retrieved.is_placeholder
        # Placeholder should contain agent info in metadata
        assert "agent_name" in retrieved.metadata


# =============================================================================
# Test Data Classes
# =============================================================================

class TestDataClasses:
    """Tests for icon storage data classes."""

    def test_stored_icon_result_success(self):
        """StoredIconResult should have correct fields for success."""
        from api.icon_storage import StoredIconResult

        result = StoredIconResult.success_result(
            icon_id="test-id",
            agent_spec_id="spec-id",
            icon_format="svg",
            content_hash="abc123",
            size_bytes=100,
            stored_inline=True,
        )

        assert result.success
        assert result.icon_id == "test-id"
        assert result.agent_spec_id == "spec-id"
        assert result.icon_format == "svg"
        assert result.content_hash == "abc123"
        assert result.size_bytes == 100
        assert result.stored_inline
        assert result.error is None

    def test_stored_icon_result_error(self):
        """StoredIconResult should have correct fields for error."""
        from api.icon_storage import StoredIconResult

        result = StoredIconResult.error_result("Something went wrong")

        assert not result.success
        assert result.error == "Something went wrong"
        assert result.icon_id is None

    def test_retrieved_icon_to_dict(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """RetrievedIcon.to_dict() should work correctly."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
        )

        data = retrieved.to_dict()

        assert data["found"]
        assert data["has_data"]
        assert data["icon_format"] == "svg"
        assert data["content_type"] == "image/svg+xml"
        assert not data["is_placeholder"]

    def test_agent_icon_to_dict(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """AgentIcon.to_dict() should work correctly."""
        from api.icon_storage import IconStorage, AgentIcon

        storage = IconStorage(temp_project_dir)
        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        icon = test_db_session.query(AgentIcon).filter(
            AgentIcon.id == result.icon_id
        ).first()

        data = icon.to_dict()

        assert data["id"] == result.icon_id
        assert data["agent_spec_id"] == sample_agent_spec_id
        assert data["icon_format"] == "svg"
        assert data["has_inline"]
        assert "created_at" in data


# =============================================================================
# Test API Package Exports
# =============================================================================

class TestApiPackageExports:
    """Tests for API package exports."""

    def test_icon_storage_exported(self):
        """IconStorage should be exported from api package."""
        from api import IconStorage
        assert IconStorage is not None

    def test_agent_icon_exported(self):
        """AgentIcon should be exported from api package."""
        from api import AgentIcon
        assert AgentIcon is not None

    def test_stored_icon_result_exported(self):
        """StoredIconResult should be exported from api package."""
        from api import StoredIconResult
        assert StoredIconResult is not None

    def test_retrieved_icon_exported(self):
        """RetrievedIcon should be exported from api package."""
        from api import RetrievedIcon
        assert RetrievedIcon is not None

    def test_constants_exported(self):
        """Icon storage constants should be exported."""
        from api import (
            ICON_INLINE_MAX_SIZE,
            ICON_FORMAT_MIME_TYPES,
            DEFAULT_PLACEHOLDER_PROVIDER,
        )
        assert ICON_INLINE_MAX_SIZE == 16 * 1024
        assert "svg" in ICON_FORMAT_MIME_TYPES
        assert DEFAULT_PLACEHOLDER_PROVIDER == "local_placeholder"

    def test_helper_functions_exported(self):
        """Helper functions should be exported."""
        from api import (
            get_mime_type_for_format,
            store_icon_from_result,
            get_icon_storage,
        )
        assert callable(get_mime_type_for_format)
        assert callable(store_icon_from_result)
        assert callable(get_icon_storage)


# =============================================================================
# Test Feature #219 Verification Steps
# =============================================================================

class TestFeature219VerificationSteps:
    """Comprehensive tests for all Feature #219 verification steps."""

    def test_step1_icon_data_stored_in_database_or_filesystem(
        self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id
    ):
        """Step 1: Icon data stored in database or filesystem."""
        from api.icon_storage import IconStorage, AgentIcon, ICON_INLINE_MAX_SIZE

        storage = IconStorage(temp_project_dir)

        # Test small icon (inline storage)
        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        assert result.success

        icon = test_db_session.query(AgentIcon).filter(
            AgentIcon.id == result.icon_id
        ).first()

        assert icon is not None
        # Small icons stored in database (content_inline)
        assert icon.content_inline == sample_svg_icon

        # Test large icon (filesystem storage)
        large_spec_id = "large-icon-spec-id"
        large_icon = "<svg>" + ("x" * (ICON_INLINE_MAX_SIZE + 1000)) + "</svg>"

        result2 = storage.store_icon(
            session=test_db_session,
            agent_spec_id=large_spec_id,
            icon_data=large_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        assert result2.success

        icon2 = test_db_session.query(AgentIcon).filter(
            AgentIcon.id == result2.icon_id
        ).first()

        # Large icons stored in filesystem (content_ref)
        assert icon2.content_ref is not None
        file_path = temp_project_dir / icon2.content_ref
        assert file_path.exists()

    def test_step2_icon_linked_to_agentspec_by_agent_spec_id(
        self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id
    ):
        """Step 2: Icon linked to AgentSpec by agent_spec_id."""
        from api.icon_storage import IconStorage, AgentIcon

        storage = IconStorage(temp_project_dir)

        result = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Query by agent_spec_id
        icon = test_db_session.query(AgentIcon).filter(
            AgentIcon.agent_spec_id == sample_agent_spec_id
        ).first()

        assert icon is not None
        assert icon.agent_spec_id == sample_agent_spec_id

        # Retrieve by agent_spec_id
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.found
        assert retrieved.agent_spec_id == sample_agent_spec_id

    def test_step3_get_endpoint_returns_icon(
        self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id
    ):
        """Step 3: GET /api/agents/{id}/icon endpoint returns icon."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store icon
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Retrieve icon (simulating endpoint)
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
        )

        assert retrieved.found
        assert retrieved.icon_data is not None

        # Get bytes for response body
        icon_bytes = retrieved.get_bytes()
        assert isinstance(icon_bytes, bytes)
        assert len(icon_bytes) > 0

    def test_step4_icon_format_header_set_appropriately(
        self, temp_project_dir, test_db_session, sample_agent_spec_id
    ):
        """Step 4: Icon format header set appropriately (image/svg+xml, image/png)."""
        from api.icon_storage import IconStorage, ICON_FORMAT_MIME_TYPES

        storage = IconStorage(temp_project_dir)

        # Test SVG format
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data="<svg></svg>",
            icon_format="svg",
        )
        test_db_session.commit()

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
        )

        assert retrieved.content_type == "image/svg+xml"

        # Verify MIME type mapping
        assert ICON_FORMAT_MIME_TYPES["svg"] == "image/svg+xml"
        assert ICON_FORMAT_MIME_TYPES["png"] == "image/png"
        assert ICON_FORMAT_MIME_TYPES["jpeg"] == "image/jpeg"
        assert ICON_FORMAT_MIME_TYPES["webp"] == "image/webp"

    def test_step5_missing_icon_returns_default_placeholder(
        self, temp_project_dir, test_db_session, sample_agent_spec_id
    ):
        """Step 5: Missing icon returns default placeholder."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Retrieve non-existent icon with placeholder
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=True,
            agent_name="test-agent",
        )

        assert retrieved.found
        assert retrieved.is_placeholder
        assert retrieved.icon_data is not None
        assert "<svg" in retrieved.icon_data
        assert retrieved.content_type == "image/svg+xml"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_delete_icon(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Icon deletion should work correctly."""
        from api.icon_storage import IconStorage, AgentIcon

        storage = IconStorage(temp_project_dir)

        # Store icon
        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Delete icon
        deleted = storage.delete_icon(test_db_session, sample_agent_spec_id)
        test_db_session.commit()

        assert deleted

        # Verify deletion
        icon = test_db_session.query(AgentIcon).filter(
            AgentIcon.agent_spec_id == sample_agent_spec_id
        ).first()
        assert icon is None

    def test_replace_existing_icon(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """Replacing existing icon should work correctly."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        # Store first icon
        result1 = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        # Store replacement icon
        new_icon = '<svg><rect fill="#ff0000"/></svg>'
        result2 = storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=new_icon,
            icon_format="svg",
            replace=True,
        )
        test_db_session.commit()

        # Retrieve and verify it's the new icon
        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=False,
        )

        assert retrieved.found
        assert retrieved.icon_data == new_icon

    def test_get_icon_info(self, temp_project_dir, test_db_session, sample_svg_icon, sample_agent_spec_id):
        """get_icon_info should return metadata without content."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        storage.store_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            icon_data=sample_svg_icon,
            icon_format="svg",
        )
        test_db_session.commit()

        info = storage.get_icon_info(test_db_session, sample_agent_spec_id)

        assert info is not None
        assert info["icon_format"] == "svg"
        assert info["agent_spec_id"] == sample_agent_spec_id
        assert "size_bytes" in info

    def test_empty_agent_name_uses_spec_id(self, temp_project_dir, test_db_session, sample_agent_spec_id):
        """Empty agent name should use spec_id for placeholder."""
        from api.icon_storage import IconStorage

        storage = IconStorage(temp_project_dir)

        retrieved = storage.retrieve_icon(
            session=test_db_session,
            agent_spec_id=sample_agent_spec_id,
            generate_placeholder=True,
            agent_name=None,
        )

        assert retrieved.found
        assert retrieved.is_placeholder


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
