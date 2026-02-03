#!/usr/bin/env python3
"""
Verification script for Feature #193: Agent Materializer writes to .claude/agents/generated/

This script verifies all 5 feature steps:
1. Materializer resolves project path
2. Materializer ensures .claude/agents/generated/ exists
3. Agent file written as {agent_name}.md
4. File permissions set appropriately
5. Existing file with same name is overwritten (idempotent)
"""
import os
import stat
import sys
import tempfile
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.maestro import AgentMaterializer
from api.agentspec_models import AgentSpec, generate_uuid


def create_sample_spec(objective: str = "Test objective") -> AgentSpec:
    """Create a sample AgentSpec for testing."""
    return AgentSpec(
        id=generate_uuid(),
        name="feature-193-test-agent",
        display_name="Feature 193 Test Agent",
        icon="test",
        spec_version="v1",
        objective=objective,
        task_type="coding",
        context={"feature_id": 193},
        tool_policy={"allowed_tools": ["Read", "Write"]},
        max_turns=50,
        timeout_seconds=600,
        source_feature_id=193,
        priority=1,
        tags=["testing"],
    )


def verify_step1_resolves_project_path(temp_dir: Path) -> bool:
    """Step 1: Materializer resolves project path."""
    print("\n=== Step 1: Materializer resolves project path ===")

    try:
        materializer = AgentMaterializer(temp_dir)

        # Check project_dir is absolute
        if not materializer.project_dir.is_absolute():
            print("  FAIL: project_dir is not absolute")
            return False
        print(f"  PASS: project_dir is absolute: {materializer.project_dir}")

        # Check project_dir equals resolved temp_dir
        if materializer.project_dir != temp_dir.resolve():
            print("  FAIL: project_dir does not match resolved temp_dir")
            return False
        print(f"  PASS: project_dir matches resolved path")

        # Check output_path is relative to project_dir
        if not materializer.output_path.is_relative_to(materializer.project_dir):
            print("  FAIL: output_path is not relative to project_dir")
            return False
        print(f"  PASS: output_path is relative to project_dir: {materializer.output_path}")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        return False


def verify_step2_ensures_directory_exists(temp_dir: Path) -> bool:
    """Step 2: Materializer ensures .claude/agents/generated/ exists."""
    print("\n=== Step 2: Materializer ensures .claude/agents/generated/ exists ===")

    try:
        materializer = AgentMaterializer(temp_dir)
        expected_dir = temp_dir / ".claude" / "agents" / "generated"

        # Check directory doesn't exist initially
        if expected_dir.exists():
            print("  INFO: Directory already exists, cleaning up")
            import shutil
            shutil.rmtree(temp_dir / ".claude")

        if expected_dir.exists():
            print("  FAIL: Could not clean up existing directory")
            return False
        print("  PASS: Output directory does not exist initially")

        # Call ensure_output_dir
        result_dir = materializer.ensure_output_dir()

        # Check directory now exists
        if not expected_dir.exists():
            print("  FAIL: Directory was not created")
            return False
        print(f"  PASS: Directory created: {expected_dir}")

        # Check it's a directory
        if not expected_dir.is_dir():
            print("  FAIL: Created path is not a directory")
            return False
        print("  PASS: Created path is a directory")

        # Check return value
        if result_dir != expected_dir:
            print("  FAIL: ensure_output_dir did not return correct path")
            return False
        print("  PASS: ensure_output_dir returns correct path")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        return False


def verify_step3_file_written_as_agent_name_md(temp_dir: Path) -> bool:
    """Step 3: Agent file written as {agent_name}.md."""
    print("\n=== Step 3: Agent file written as {agent_name}.md ===")

    try:
        materializer = AgentMaterializer(temp_dir)
        spec = create_sample_spec()

        result = materializer.materialize(spec)

        # Check success
        if not result.success:
            print(f"  FAIL: Materialization failed: {result.error}")
            return False
        print("  PASS: Materialization succeeded")

        # Check filename
        expected_filename = f"{spec.name}.md"
        if result.file_path.name != expected_filename:
            print(f"  FAIL: Expected filename {expected_filename}, got {result.file_path.name}")
            return False
        print(f"  PASS: File named correctly: {expected_filename}")

        # Check file exists
        if not result.file_path.exists():
            print("  FAIL: File does not exist")
            return False
        print(f"  PASS: File exists: {result.file_path}")

        # Check file in correct directory
        if result.file_path.parent != materializer.output_path:
            print("  FAIL: File not in correct directory")
            return False
        print(f"  PASS: File in correct directory: {materializer.output_path}")

        # Check file extension
        if result.file_path.suffix != ".md":
            print("  FAIL: File does not have .md extension")
            return False
        print("  PASS: File has .md extension")

        # Check content exists
        content = result.file_path.read_text()
        if len(content) == 0:
            print("  FAIL: File content is empty")
            return False
        print(f"  PASS: File has content ({len(content)} characters)")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        return False


def verify_step4_file_permissions(temp_dir: Path) -> bool:
    """Step 4: File permissions set appropriately."""
    print("\n=== Step 4: File permissions set appropriately ===")

    try:
        materializer = AgentMaterializer(temp_dir)
        spec = create_sample_spec()

        result = materializer.materialize(spec)

        if not result.success:
            print(f"  FAIL: Materialization failed: {result.error}")
            return False

        # Check file is readable
        if not os.access(result.file_path, os.R_OK):
            print("  FAIL: File is not readable")
            return False
        print("  PASS: File is readable")

        # Check file is writable
        if not os.access(result.file_path, os.W_OK):
            print("  FAIL: File is not writable")
            return False
        print("  PASS: File is writable")

        # Check file permissions
        file_stat = os.stat(result.file_path)
        mode = stat.S_IMODE(file_stat.st_mode)

        # Check owner read/write
        if not (mode & stat.S_IRUSR):
            print("  FAIL: Owner read permission not set")
            return False
        print("  PASS: Owner read permission set")

        if not (mode & stat.S_IWUSR):
            print("  FAIL: Owner write permission not set")
            return False
        print("  PASS: Owner write permission set")

        # Check no execute permissions
        if mode & stat.S_IXUSR:
            print("  FAIL: Owner execute permission should not be set for markdown files")
            return False
        print("  PASS: No owner execute permission")

        if mode & stat.S_IXGRP:
            print("  FAIL: Group execute permission should not be set")
            return False
        print("  PASS: No group execute permission")

        if mode & stat.S_IXOTH:
            print("  FAIL: Other execute permission should not be set")
            return False
        print("  PASS: No other execute permission")

        print(f"  INFO: File permissions: {oct(mode)}")
        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        return False


def verify_step5_idempotent_overwrite(temp_dir: Path) -> bool:
    """Step 5: Existing file with same name is overwritten (idempotent)."""
    print("\n=== Step 5: Existing file with same name is overwritten (idempotent) ===")

    try:
        materializer = AgentMaterializer(temp_dir)

        # First write
        spec = create_sample_spec("First version objective")
        result1 = materializer.materialize(spec)

        if not result1.success:
            print(f"  FAIL: First materialization failed: {result1.error}")
            return False
        print("  PASS: First materialization succeeded")

        content1 = result1.file_path.read_text()

        # Second write with different content
        spec.objective = "Second version objective"
        result2 = materializer.materialize(spec)

        if not result2.success:
            print(f"  FAIL: Second materialization failed: {result2.error}")
            return False
        print("  PASS: Second materialization succeeded")

        # Check same file path
        if result1.file_path != result2.file_path:
            print("  FAIL: File paths are different")
            return False
        print("  PASS: Same file path used for both writes")

        # Check content was updated
        content2 = result2.file_path.read_text()

        if "Second version objective" not in content2:
            print("  FAIL: Updated content not found")
            return False
        print("  PASS: Updated content found in file")

        if "First version objective" in content2:
            print("  FAIL: Old content still present")
            return False
        print("  PASS: Old content overwritten")

        # Check only one file exists
        files = list(materializer.output_path.glob(f"{spec.name}*"))
        if len(files) != 1:
            print(f"  FAIL: Expected 1 file, found {len(files)}")
            return False
        print(f"  PASS: Only 1 file exists (no backups created)")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        return False


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #193: Agent Materializer writes to .claude/agents/generated/")
    print("=" * 60)

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)

        results = {
            "Step 1: Resolves project path": verify_step1_resolves_project_path(temp_dir),
            "Step 2: Ensures directory exists": verify_step2_ensures_directory_exists(temp_dir),
            "Step 3: File written as {agent_name}.md": verify_step3_file_written_as_agent_name_md(temp_dir),
            "Step 4: File permissions set appropriately": verify_step4_file_permissions(temp_dir),
            "Step 5: Idempotent overwrite": verify_step5_idempotent_overwrite(temp_dir),
        }

    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_passed = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {step}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("ALL STEPS PASSED - Feature #193 is complete!")
        return 0
    else:
        print("SOME STEPS FAILED - Feature #193 needs work")
        return 1


if __name__ == "__main__":
    sys.exit(main())
