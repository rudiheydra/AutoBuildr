#!/usr/bin/env python3
"""
Feature #31 Verification Script
================================

Artifact Storage with Content-Addressing

Verifies each step from the feature description:
1. Create ArtifactStorage class with store(run_id, type, content, path) method
2. Compute SHA256 hash of content
3. Check content size against ARTIFACT_INLINE_MAX_SIZE (4096 bytes)
4. If small, store in content_inline field
5. If large, write to file: .autobuildr/artifacts/{run_id}/{hash}.blob
6. Create parent directories if needed
7. Set content_ref to file path
8. Set size_bytes to content length
9. Check for existing artifact with same hash (deduplication)
10. Return Artifact record
"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import (
    ARTIFACT_INLINE_MAX_SIZE,
    AgentRun,
    AgentSpec,
    Artifact,
    generate_uuid,
)
from api.artifact_storage import ArtifactStorage


def setup_test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def setup_test_run(session):
    """Create test AgentSpec and AgentRun."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-spec",
        display_name="Test Spec",
        objective="Test",
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
    return run


def print_result(step: int, description: str, passed: bool, details: str = ""):
    """Print verification result."""
    status = "" if passed else ""
    print(f"Step {step}: {description}")
    print(f"  {status} {'PASS' if passed else 'FAIL'}")
    if details:
        print(f"  Details: {details}")
    print()
    return passed


def main():
    print("=" * 60)
    print("Feature #31: Artifact Storage with Content-Addressing")
    print("=" * 60)
    print()

    all_passed = True

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        session = setup_test_db()
        run = setup_test_run(session)

        # ===================================================================
        # Step 1: Create ArtifactStorage class with store() method
        # ===================================================================
        try:
            storage = ArtifactStorage(project_dir)
            has_store = hasattr(storage, 'store') and callable(storage.store)
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content="test",
                path="/test/file.txt",
            )
            passed = has_store and isinstance(artifact, Artifact)
            all_passed &= print_result(
                1,
                "Create ArtifactStorage class with store(run_id, type, content, path)",
                passed,
                f"store() method exists: {has_store}, returns Artifact: {isinstance(artifact, Artifact)}"
            )
        except Exception as e:
            all_passed &= print_result(1, "Create ArtifactStorage", False, str(e))

        # ===================================================================
        # Step 2: Compute SHA256 hash of content
        # ===================================================================
        try:
            content = "Test content for hashing"
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=content,
            )
            expected_hash = hashlib.sha256(content.encode()).hexdigest()
            passed = artifact.content_hash == expected_hash
            all_passed &= print_result(
                2,
                "Compute SHA256 hash of content",
                passed,
                f"Expected: {expected_hash[:16]}..., Got: {artifact.content_hash[:16]}..."
            )
        except Exception as e:
            all_passed &= print_result(2, "Compute SHA256 hash", False, str(e))

        # ===================================================================
        # Step 3: Check content size against ARTIFACT_INLINE_MAX_SIZE (4096 bytes)
        # ===================================================================
        try:
            passed = ARTIFACT_INLINE_MAX_SIZE == 4096
            all_passed &= print_result(
                3,
                "Check content size against ARTIFACT_INLINE_MAX_SIZE (4096 bytes)",
                passed,
                f"ARTIFACT_INLINE_MAX_SIZE = {ARTIFACT_INLINE_MAX_SIZE}"
            )
        except Exception as e:
            all_passed &= print_result(3, "Check size threshold", False, str(e))

        # ===================================================================
        # Step 4: If small, store in content_inline field
        # ===================================================================
        try:
            small_content = "Small content under 4KB"
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=small_content,
            )
            passed = artifact.content_inline == small_content and artifact.content_ref is None
            all_passed &= print_result(
                4,
                "If small, store in content_inline field",
                passed,
                f"content_inline set: {artifact.content_inline is not None}, content_ref is None: {artifact.content_ref is None}"
            )
        except Exception as e:
            all_passed &= print_result(4, "Store inline", False, str(e))

        # ===================================================================
        # Step 5: If large, write to file: .autobuildr/artifacts/{run_id}/{hash}.blob
        # ===================================================================
        try:
            large_content = "x" * 5000  # > 4096 bytes
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=large_content,
            )
            expected_path = f".autobuildr/artifacts/{run.id}/{artifact.content_hash}.blob"
            file_exists = (project_dir / expected_path).exists()
            passed = artifact.content_ref == expected_path and file_exists
            all_passed &= print_result(
                5,
                "If large, write to file: .autobuildr/artifacts/{run_id}/{hash}.blob",
                passed,
                f"content_ref = {artifact.content_ref}, file exists: {file_exists}"
            )
        except Exception as e:
            all_passed &= print_result(5, "Store in file", False, str(e))

        # ===================================================================
        # Step 6: Create parent directories if needed
        # ===================================================================
        try:
            # Test with new run (new directory)
            new_run = AgentRun(
                id=generate_uuid(),
                agent_spec_id=run.agent_spec_id,
                status="running",
            )
            session.add(new_run)
            session.flush()

            large_content = "y" * 5000
            artifact = storage.store(
                session=session,
                run_id=new_run.id,
                artifact_type="log",
                content=large_content,
            )
            dir_path = project_dir / ".autobuildr" / "artifacts" / new_run.id
            passed = dir_path.exists() and dir_path.is_dir()
            all_passed &= print_result(
                6,
                "Create parent directories if needed",
                passed,
                f"Directory created: {dir_path}"
            )
        except Exception as e:
            all_passed &= print_result(6, "Create directories", False, str(e))

        # ===================================================================
        # Step 7: Set content_ref to file path
        # ===================================================================
        try:
            large_content = "z" * 5000
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=large_content,
            )
            passed = (
                artifact.content_ref is not None and
                artifact.content_ref.startswith(".autobuildr/artifacts/") and
                artifact.content_ref.endswith(".blob")
            )
            all_passed &= print_result(
                7,
                "Set content_ref to file path",
                passed,
                f"content_ref = {artifact.content_ref}"
            )
        except Exception as e:
            all_passed &= print_result(7, "Set content_ref", False, str(e))

        # ===================================================================
        # Step 8: Set size_bytes to content length
        # ===================================================================
        try:
            content = "Test content 12345"
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=content,
            )
            expected_size = len(content.encode("utf-8"))
            passed = artifact.size_bytes == expected_size
            all_passed &= print_result(
                8,
                "Set size_bytes to content length",
                passed,
                f"Expected: {expected_size}, Got: {artifact.size_bytes}"
            )
        except Exception as e:
            all_passed &= print_result(8, "Set size_bytes", False, str(e))

        # ===================================================================
        # Step 9: Check for existing artifact with same hash (deduplication)
        # ===================================================================
        try:
            content = "Duplicate content for dedup test"
            artifact1 = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=content,
            )
            artifact2 = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="log",
                content=content,
            )
            passed = artifact1.id == artifact2.id
            all_passed &= print_result(
                9,
                "Check for existing artifact with same hash (deduplication)",
                passed,
                f"Same artifact returned: artifact1.id == artifact2.id: {artifact1.id == artifact2.id}"
            )
        except Exception as e:
            all_passed &= print_result(9, "Deduplication", False, str(e))

        # ===================================================================
        # Step 10: Return Artifact record
        # ===================================================================
        try:
            artifact = storage.store(
                session=session,
                run_id=run.id,
                artifact_type="test_result",
                content="Final test",
                path="/test/path",
                metadata={"key": "value"},
            )
            passed = (
                isinstance(artifact, Artifact) and
                artifact.id is not None and
                artifact.run_id == run.id and
                artifact.artifact_type == "test_result" and
                artifact.content_hash is not None
            )
            all_passed &= print_result(
                10,
                "Return Artifact record",
                passed,
                f"Artifact ID: {artifact.id[:8]}..., type: {artifact.artifact_type}"
            )
        except Exception as e:
            all_passed &= print_result(10, "Return Artifact", False, str(e))

    # ===================================================================
    # Summary
    # ===================================================================
    print("=" * 60)
    if all_passed:
        print(" ALL VERIFICATION STEPS PASSED")
    else:
        print(" SOME VERIFICATION STEPS FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
