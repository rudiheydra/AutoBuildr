#!/usr/bin/env python3
"""
Verification script for Feature #194: Agent Materializer is deterministic and idempotent

This script verifies all 5 feature steps:
1. Same AgentSpec always produces byte-identical markdown
2. Timestamps not included in output (determinism)
3. Re-materialization overwrites existing files safely
4. No side effects beyond file writes
5. Materializer can be re-run without state concerns
"""
import hashlib
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.maestro import AgentMaterializer
from api.agentspec_models import AgentSpec, generate_uuid


def create_sample_spec(objective: str = "Test objective for determinism") -> AgentSpec:
    """Create a sample AgentSpec for testing."""
    return AgentSpec(
        id="determinism-test-spec-id",  # Fixed ID for reproducibility
        name="feature-194-test-agent",
        display_name="Feature 194 Test Agent",
        icon="test",
        spec_version="v1",
        objective=objective,
        task_type="testing",
        context={
            "feature_id": 194,
            "test_key": "test_value",
            "nested": {"a": 1, "b": 2},
        },
        tool_policy={
            "allowed_tools": ["Read", "Write", "Edit"],
            "forbidden_patterns": ["rm -rf"],
        },
        max_turns=50,
        timeout_seconds=600,
        source_feature_id=194,
        priority=1,
        tags=["testing", "determinism"],
    )


def verify_step1_byte_identical_output(temp_dir: Path) -> bool:
    """Step 1: Same AgentSpec always produces byte-identical markdown."""
    print("\n=== Step 1: Same AgentSpec always produces byte-identical markdown ===")

    try:
        materializer = AgentMaterializer(temp_dir)
        spec = create_sample_spec()

        # Materialize multiple times
        contents = []
        hashes = []
        for i in range(5):
            result = materializer.materialize(spec)
            if not result.success:
                print(f"  FAIL: Materialization {i+1} failed: {result.error}")
                return False
            contents.append(result.file_path.read_bytes())
            hashes.append(result.content_hash)
            print(f"  Iteration {i+1}: hash = {result.content_hash[:16]}...")

        # All contents should be identical
        if len(set(contents)) != 1:
            print("  FAIL: Contents are not identical across iterations")
            return False
        print("  PASS: All 5 materializations produced byte-identical content")

        # All hashes should be identical
        if len(set(hashes)) != 1:
            print("  FAIL: Hashes are not identical across iterations")
            return False
        print("  PASS: All content hashes are identical")

        # Verify hash matches actual content
        computed_hash = hashlib.sha256(contents[0]).hexdigest()
        if hashes[0] != computed_hash:
            print(f"  FAIL: Content hash mismatch: {hashes[0]} != {computed_hash}")
            return False
        print("  PASS: Content hash correctly computed from file content")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step2_no_timestamps(temp_dir: Path) -> bool:
    """Step 2: Timestamps not included in output (determinism)."""
    print("\n=== Step 2: Timestamps not included in output (determinism) ===")

    try:
        materializer = AgentMaterializer(temp_dir)
        spec = create_sample_spec()

        result = materializer.materialize(spec)
        if not result.success:
            print(f"  FAIL: Materialization failed: {result.error}")
            return False

        content = result.file_path.read_text()

        # Check for timestamp fields
        timestamp_fields = ["created_at:", "modified_at:", "updated_at:", "generated_at:"]
        for field in timestamp_fields:
            if field in content:
                print(f"  FAIL: Found timestamp field: {field}")
                return False
        print("  PASS: No timestamp fields (created_at, modified_at, etc.) found")

        # Check for ISO timestamp patterns
        iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"

        # Extract frontmatter for stricter check
        frontmatter_match = re.search(r"^---\n(.*?)\n---", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            if re.search(iso_pattern, frontmatter):
                print(f"  FAIL: Found ISO timestamp pattern in frontmatter")
                return False
            print("  PASS: No ISO timestamp patterns in frontmatter")
        else:
            print("  WARNING: Could not extract frontmatter")

        # Multiple runs at different times should produce same output
        result1 = materializer.materialize(spec)
        time.sleep(0.1)  # Wait a bit
        result2 = materializer.materialize(spec)

        if result1.content_hash != result2.content_hash:
            print("  FAIL: Output differs across time (timestamp leakage)")
            return False
        print("  PASS: Output identical across time (no timestamp leakage)")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step3_safe_overwrite(temp_dir: Path) -> bool:
    """Step 3: Re-materialization overwrites existing files safely."""
    print("\n=== Step 3: Re-materialization overwrites existing files safely ===")

    try:
        materializer = AgentMaterializer(temp_dir)

        # First write
        spec = create_sample_spec("FIRST_VERSION_MARKER")
        result1 = materializer.materialize(spec)
        if not result1.success:
            print(f"  FAIL: First materialization failed: {result1.error}")
            return False
        print(f"  PASS: First materialization succeeded: {result1.file_path.name}")

        # Verify first content
        content1 = result1.file_path.read_text()
        if "FIRST_VERSION_MARKER" not in content1:
            print("  FAIL: First version marker not found")
            return False
        print("  PASS: First version marker found in content")

        # Overwrite with different content
        spec.objective = "SECOND_VERSION_MARKER"
        result2 = materializer.materialize(spec)
        if not result2.success:
            print(f"  FAIL: Second materialization failed: {result2.error}")
            return False
        print("  PASS: Second materialization (overwrite) succeeded")

        # Verify same path
        if result1.file_path != result2.file_path:
            print("  FAIL: File paths differ")
            return False
        print("  PASS: Same file path used for both materializations")

        # Verify content properly replaced
        content2 = result2.file_path.read_text()
        if "SECOND_VERSION_MARKER" not in content2:
            print("  FAIL: Second version marker not found")
            return False
        print("  PASS: Second version marker found in content")

        if "FIRST_VERSION_MARKER" in content2:
            print("  FAIL: First version marker still present (content not fully replaced)")
            return False
        print("  PASS: First version marker properly removed (clean overwrite)")

        # Verify no backup files created
        files = list(materializer.output_path.glob(f"{spec.name}*"))
        if len(files) != 1:
            print(f"  FAIL: Expected 1 file, found {len(files)}")
            return False
        print("  PASS: No backup files created (only 1 file exists)")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step4_no_side_effects(temp_dir: Path) -> bool:
    """Step 4: No side effects beyond file writes."""
    print("\n=== Step 4: No side effects beyond file writes ===")

    try:
        # Create fresh temp dir for this test
        with tempfile.TemporaryDirectory() as clean_dir:
            clean_path = Path(clean_dir)
            materializer = AgentMaterializer(clean_path)
            spec = create_sample_spec()

            # Count items before
            items_before = set(clean_path.rglob("*"))
            print(f"  Items before materialization: {len(items_before)}")

            # Materialize
            result = materializer.materialize(spec)
            if not result.success:
                print(f"  FAIL: Materialization failed: {result.error}")
                return False

            # Count items after
            items_after = set(clean_path.rglob("*"))
            new_items = items_after - items_before
            print(f"  Items after materialization: {len(items_after)}")
            print(f"  New items created: {len(new_items)}")

            # Verify new items are all within .claude
            for item in new_items:
                rel_path = item.relative_to(clean_path)
                if not str(rel_path).startswith(".claude"):
                    print(f"  FAIL: Unexpected item outside .claude: {rel_path}")
                    return False
            print("  PASS: All new items are within .claude directory")

            # Verify only one .md file created
            md_files = [f for f in new_items if f.suffix == ".md"]
            if len(md_files) != 1:
                print(f"  FAIL: Expected 1 .md file, found {len(md_files)}")
                return False
            print("  PASS: Exactly 1 markdown file created")

            # Verify no temp files
            temp_patterns = ["*.tmp", "*.bak", "*.swp", "*.lock"]
            for pattern in temp_patterns:
                temp_files = list(clean_path.rglob(pattern))
                if temp_files:
                    print(f"  FAIL: Found temporary files: {temp_files}")
                    return False
            print("  PASS: No temporary/backup files created")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_step5_stateless_rerun(temp_dir: Path) -> bool:
    """Step 5: Materializer can be re-run without state concerns."""
    print("\n=== Step 5: Materializer can be re-run without state concerns ===")

    try:
        spec = create_sample_spec()

        # First materializer instance
        mat1 = AgentMaterializer(temp_dir)
        result1 = mat1.materialize(spec)
        if not result1.success:
            print(f"  FAIL: First materialization failed: {result1.error}")
            return False
        hash1 = result1.content_hash
        print(f"  First instance hash: {hash1[:16]}...")

        # Delete instance
        del mat1
        print("  PASS: First materializer instance deleted")

        # Second materializer instance
        mat2 = AgentMaterializer(temp_dir)

        # "Pollute" with other materializations
        for i in range(3):
            other_spec = AgentSpec(
                id=f"other-spec-{i}",
                name=f"other-agent-{i}",
                display_name=f"Other Agent {i}",
                icon="test",
                spec_version="v1",
                objective=f"Other objective {i}",
                task_type="testing",
                context={},
                tool_policy={"allowed_tools": []},
                max_turns=50,
                timeout_seconds=600,
            )
            mat2.materialize(other_spec)
        print("  PASS: Materialized 3 other specs to 'pollute' state")

        # Re-materialize original spec
        result2 = mat2.materialize(spec)
        if not result2.success:
            print(f"  FAIL: Re-materialization failed: {result2.error}")
            return False
        hash2 = result2.content_hash
        print(f"  Second instance hash: {hash2[:16]}...")

        # Hashes should match
        if hash1 != hash2:
            print(f"  FAIL: Hashes differ between instances")
            return False
        print("  PASS: Hashes identical between fresh instances")

        # Third instance in different output directory (to verify truly stateless)
        mat3 = AgentMaterializer(temp_dir, output_dir="verify_stateless")
        result3 = mat3.materialize(spec)
        if result3.content_hash != hash1:
            print(f"  FAIL: Third instance hash differs")
            return False
        print("  PASS: Third instance (different output dir) produces identical hash")

        return True
    except Exception as e:
        print(f"  FAIL: Exception occurred: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #194: Agent Materializer is deterministic and idempotent")
    print("=" * 60)

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)

        results = {
            "Step 1: Byte-identical output": verify_step1_byte_identical_output(temp_dir),
            "Step 2: No timestamps in output": verify_step2_no_timestamps(temp_dir),
            "Step 3: Safe file overwrite": verify_step3_safe_overwrite(temp_dir),
            "Step 4: No side effects": verify_step4_no_side_effects(temp_dir),
            "Step 5: Stateless re-run": verify_step5_stateless_rerun(temp_dir),
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
        print("ALL STEPS PASSED - Feature #194 is complete!")
        return 0
    else:
        print("SOME STEPS FAILED - Feature #194 needs work")
        return 1


if __name__ == "__main__":
    sys.exit(main())
