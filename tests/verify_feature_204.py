#!/usr/bin/env python3
"""
Verification script for Feature #204: Scaffolding respects .gitignore patterns

This script verifies all 5 steps of Feature #204:
1. Check if .gitignore exists
2. Add .claude/agents/generated/ to .gitignore if not present
3. Keep .claude/agents/manual/ tracked
4. Keep CLAUDE.md tracked
5. Preserve existing .gitignore content
"""
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.scaffolding import (
    gitignore_exists,
    update_gitignore,
    ensure_gitignore_patterns,
    verify_gitignore_patterns,
    scaffold_with_gitignore,
    GITIGNORE_FILE,
    GITIGNORE_GENERATED_PATTERNS,
    GITIGNORE_TRACKED_PATTERNS,
)


def verify_step1():
    """Step 1: Check if .gitignore exists."""
    print("\n=== Step 1: Check if .gitignore exists ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1: No .gitignore
        exists = gitignore_exists(project_dir)
        assert exists is False, "Should return False when .gitignore missing"
        print("  [PASS] gitignore_exists() returns False when missing")

        # Test 2: With .gitignore
        (project_dir / ".gitignore").write_text("node_modules/\n")
        exists = gitignore_exists(project_dir)
        assert exists is True, "Should return True when .gitignore exists"
        print("  [PASS] gitignore_exists() returns True when present")

    print("  [PASS] Step 1 verified")
    return True


def verify_step2():
    """Step 2: Add .claude/agents/generated/ to .gitignore if not present."""
    print("\n=== Step 2: Add .claude/agents/generated/ to .gitignore ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1: Add to empty project
        result = update_gitignore(project_dir)
        assert result.error is None, f"Error: {result.error}"
        assert ".claude/agents/generated/" in result.patterns_added
        print("  [PASS] Pattern added to new .gitignore")

        # Test 2: Verify in file
        content = (project_dir / ".gitignore").read_text()
        assert ".claude/agents/generated/" in content
        print("  [PASS] Pattern present in .gitignore file")

        # Test 3: Don't add if already present
        result2 = update_gitignore(project_dir)
        assert ".claude/agents/generated/" in result2.patterns_already_present
        print("  [PASS] Pattern not re-added when already present")

    print("  [PASS] Step 2 verified")
    return True


def verify_step3():
    """Step 3: Keep .claude/agents/manual/ tracked."""
    print("\n=== Step 3: Keep .claude/agents/manual/ tracked ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1: Verify manual/ not in generated patterns
        assert ".claude/agents/manual/" not in GITIGNORE_GENERATED_PATTERNS
        print("  [PASS] .claude/agents/manual/ not in GITIGNORE_GENERATED_PATTERNS")

        # Test 2: Verify manual/ in tracked patterns
        assert ".claude/agents/manual/" in GITIGNORE_TRACKED_PATTERNS
        print("  [PASS] .claude/agents/manual/ in GITIGNORE_TRACKED_PATTERNS")

        # Test 3: Update doesn't add manual/ to .gitignore
        result = update_gitignore(project_dir)
        content = (project_dir / ".gitignore").read_text()
        assert ".claude/agents/manual/" not in content
        print("  [PASS] .claude/agents/manual/ not added to .gitignore")

    print("  [PASS] Step 3 verified")
    return True


def verify_step4():
    """Step 4: Keep CLAUDE.md tracked."""
    print("\n=== Step 4: Keep CLAUDE.md tracked ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Test 1: Verify CLAUDE.md not in generated patterns
        assert "CLAUDE.md" not in GITIGNORE_GENERATED_PATTERNS
        print("  [PASS] CLAUDE.md not in GITIGNORE_GENERATED_PATTERNS")

        # Test 2: Verify CLAUDE.md in tracked patterns
        assert "CLAUDE.md" in GITIGNORE_TRACKED_PATTERNS
        print("  [PASS] CLAUDE.md in GITIGNORE_TRACKED_PATTERNS")

        # Test 3: Update doesn't add CLAUDE.md to .gitignore
        result = update_gitignore(project_dir)
        content = (project_dir / ".gitignore").read_text()
        assert "CLAUDE.md" not in content
        print("  [PASS] CLAUDE.md not added to .gitignore")

    print("  [PASS] Step 4 verified")
    return True


def verify_step5():
    """Step 5: Preserve existing .gitignore content."""
    print("\n=== Step 5: Preserve existing .gitignore content ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Pre-create .gitignore with content
        original = """# My project
node_modules/
*.pyc
build/
.env
"""
        (project_dir / ".gitignore").write_text(original)

        # Run update
        result = update_gitignore(project_dir)

        # Verify all original content preserved
        content = (project_dir / ".gitignore").read_text()

        # Test 1: Original patterns preserved
        assert "node_modules/" in content
        print("  [PASS] node_modules/ preserved")

        assert "*.pyc" in content
        print("  [PASS] *.pyc preserved")

        assert "build/" in content
        print("  [PASS] build/ preserved")

        assert ".env" in content
        print("  [PASS] .env preserved")

        # Test 2: Original comment preserved
        assert "# My project" in content
        print("  [PASS] Comment preserved")

        # Test 3: New pattern added
        assert ".claude/agents/generated/" in content
        print("  [PASS] New pattern added")

    print("  [PASS] Step 5 verified")
    return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #204: Scaffolding respects .gitignore patterns")
    print("=" * 60)

    steps = [
        ("Step 1", verify_step1),
        ("Step 2", verify_step2),
        ("Step 3", verify_step3),
        ("Step 4", verify_step4),
        ("Step 5", verify_step5),
    ]

    passed = 0
    failed = 0

    for name, verify_func in steps:
        try:
            if verify_func():
                passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{len(steps)} steps passed")
    print("=" * 60)

    if failed > 0:
        print("\nFEATURE #204 VERIFICATION FAILED")
        return 1

    print("\nFEATURE #204 VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
