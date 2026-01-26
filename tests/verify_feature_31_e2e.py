#!/usr/bin/env python3
"""
Feature #31 End-to-End Verification
====================================

Tests ArtifactStorage against the actual project database and file system.
"""
import hashlib
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import create_database
from api.agentspec_models import (
    ARTIFACT_INLINE_MAX_SIZE,
    AgentRun,
    AgentSpec,
    Artifact,
    generate_uuid,
)
from api.artifact_storage import ArtifactStorage


def main():
    print("=" * 60)
    print("Feature #31: End-to-End Verification")
    print("=" * 60)
    print()

    project_dir = Path(__file__).parent.parent
    storage = ArtifactStorage(project_dir)

    # Create database session
    engine, SessionLocal = create_database(project_dir)
    session = SessionLocal()

    try:
        # Create a test spec and run
        spec = AgentSpec(
            id=generate_uuid(),
            name="test-artifact-storage-e2e",
            display_name="Test Artifact Storage E2E",
            objective="Verify artifact storage works end-to-end",
            task_type="testing",
            tool_policy={"policy_version": "v1", "allowed_tools": []},
        )
        session.add(spec)
        session.flush()

        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            status="running",
        )
        session.add(run)
        session.flush()

        print(f"Created test spec: {spec.id}")
        print(f"Created test run: {run.id}")
        print()

        # Test 1: Small content (inline storage)
        print("Test 1: Small content (inline storage)")
        small_content = "TEST_UNIQUE_SMALL_" + generate_uuid()
        artifact_small = storage.store(
            session=session,
            run_id=run.id,
            artifact_type="log",
            content=small_content,
        )
        assert artifact_small.content_inline == small_content
        assert artifact_small.content_ref is None
        print(f"   Artifact ID: {artifact_small.id}")
        print(f"   Hash: {artifact_small.content_hash[:32]}...")
        print(f"   Size: {artifact_small.size_bytes} bytes")
        print(f"   Stored inline: True")
        print()

        # Test 2: Large content (file storage)
        print("Test 2: Large content (file storage)")
        large_content = "TEST_UNIQUE_LARGE_" + "x" * 5000 + generate_uuid()
        artifact_large = storage.store(
            session=session,
            run_id=run.id,
            artifact_type="test_result",
            content=large_content,
        )
        assert artifact_large.content_inline is None
        assert artifact_large.content_ref is not None
        file_path = project_dir / artifact_large.content_ref
        assert file_path.exists()
        print(f"   Artifact ID: {artifact_large.id}")
        print(f"   Hash: {artifact_large.content_hash[:32]}...")
        print(f"   Size: {artifact_large.size_bytes} bytes")
        print(f"   File: {artifact_large.content_ref}")
        print(f"   File exists: {file_path.exists()}")
        print()

        # Test 3: Content retrieval
        print("Test 3: Content retrieval")
        retrieved_small = storage.retrieve_string(artifact_small)
        retrieved_large = storage.retrieve_string(artifact_large)
        assert retrieved_small == small_content
        assert retrieved_large == large_content
        print(f"   Small content matches: {retrieved_small == small_content}")
        print(f"   Large content matches: {retrieved_large == large_content}")
        print()

        # Test 4: Deduplication
        print("Test 4: Deduplication")
        dedup_content = "DEDUP_TEST_" + generate_uuid()
        artifact_dup1 = storage.store(
            session=session,
            run_id=run.id,
            artifact_type="log",
            content=dedup_content,
        )
        artifact_dup2 = storage.store(
            session=session,
            run_id=run.id,
            artifact_type="log",
            content=dedup_content,
        )
        assert artifact_dup1.id == artifact_dup2.id
        print(f"   First artifact ID: {artifact_dup1.id}")
        print(f"   Second artifact ID: {artifact_dup2.id}")
        print(f"   Same artifact returned: {artifact_dup1.id == artifact_dup2.id}")
        print()

        # Test 5: Verify in database
        print("Test 5: Verify artifacts in database")
        db_artifact = session.query(Artifact).filter(
            Artifact.id == artifact_small.id
        ).first()
        assert db_artifact is not None
        assert db_artifact.content_hash == artifact_small.content_hash
        print(f"   Artifact found in DB: {db_artifact is not None}")
        print(f"   Hash matches: {db_artifact.content_hash == artifact_small.content_hash}")
        print()

        # Test 6: Storage stats
        print("Test 6: Storage statistics")
        stats = storage.get_storage_stats()
        print(f"   Artifacts base: {stats['artifacts_base']}")
        print(f"   Run count: {stats['run_count']}")
        print(f"   File count: {stats['file_count']}")
        print(f"   Total size: {stats['total_mb']} MB")
        print()

        # Cleanup: Delete the test file
        print("Cleanup: Removing test file")
        if artifact_large.content_ref:
            file_path = project_dir / artifact_large.content_ref
            if file_path.exists():
                file_path.unlink()
                print(f"   Deleted: {file_path}")
            # Remove directory if empty
            run_dir = file_path.parent
            if run_dir.exists() and not any(run_dir.iterdir()):
                run_dir.rmdir()
                print(f"   Removed empty dir: {run_dir}")

        # Rollback to avoid polluting the database
        session.rollback()
        print("   Session rolled back (test data not committed)")
        print()

        print("=" * 60)
        print(" ALL END-TO-END TESTS PASSED")
        print("=" * 60)
        return 0

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
