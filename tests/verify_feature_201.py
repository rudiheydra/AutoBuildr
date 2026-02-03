#!/usr/bin/env python3
"""
Feature #201: Scaffolding is idempotent and safe to re-run

Verification script to confirm all 5 feature steps are working correctly.

Steps:
1. Scaffolding checks for existing directories before creating
2. Existing files in manual/ never touched
3. Generated files may be overwritten by Materializer
4. Settings merged, not replaced
5. No errors on re-run of scaffolded project
"""
import json
import tempfile
from pathlib import Path

from api.scaffolding import (
    scaffold_claude_directory,
    is_claude_scaffolded,
    CLAUDE_ROOT_DIR,
)
from api.settings_manager import (
    SettingsManager,
    SettingsRequirements,
)


def verify_step1() -> bool:
    """
    Step 1: Scaffolding checks for existing directories before creating

    - Pre-create partial structure
    - Scaffold should only create missing directories
    - Should report which existed vs created
    """
    print("Step 1: Scaffolding checks for existing directories...")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Pre-create partial structure
        (project_dir / ".claude" / "agents" / "generated").mkdir(parents=True)

        # Scaffold
        result = scaffold_claude_directory(project_dir)

        if not result.success:
            print(f"  FAIL: Scaffold failed")
            return False

        # Check that it detected existing directories
        existed = [d.relative_path for d in result.directories if d.existed]
        created = [d.relative_path for d in result.directories if d.created]

        if ".claude" not in existed:
            print(f"  FAIL: .claude not detected as existing")
            return False

        if "agents/generated" not in existed:
            print(f"  FAIL: agents/generated not detected as existing")
            return False

        if "agents/manual" not in created:
            print(f"  FAIL: agents/manual not created")
            return False

        print(f"  PASS: Existed: {existed}")
        print(f"  PASS: Created: {created}")
        return True


def verify_step2() -> bool:
    """
    Step 2: Existing files in manual/ never touched

    - Create files in manual/
    - Run scaffold multiple times
    - Verify files unchanged
    """
    print("Step 2: Existing files in manual/ never touched...")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Initial scaffold
        scaffold_claude_directory(project_dir)

        # Create files in manual/
        manual_dir = project_dir / ".claude" / "agents" / "manual"
        test_file = manual_dir / "my-agent.md"
        test_content = "# My Custom Agent\n\nDon't touch me!"
        test_file.write_text(test_content)
        original_mtime = test_file.stat().st_mtime

        # Re-scaffold multiple times
        for i in range(3):
            result = scaffold_claude_directory(project_dir)
            if not result.success:
                print(f"  FAIL: Scaffold {i+1} failed")
                return False

        # Verify file unchanged
        if not test_file.exists():
            print(f"  FAIL: File was deleted")
            return False

        if test_file.read_text() != test_content:
            print(f"  FAIL: File content changed")
            return False

        if test_file.stat().st_mtime != original_mtime:
            print(f"  FAIL: File mtime changed")
            return False

        print(f"  PASS: Manual files preserved (content: {len(test_content)} bytes)")
        return True


def verify_step3() -> bool:
    """
    Step 3: Generated files may be overwritten by Materializer

    - Create file in generated/
    - Overwrite it (simulating Materializer)
    - Verify overwrite succeeded
    - Verify scaffold doesn't restore original
    """
    print("Step 3: Generated files may be overwritten...")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Scaffold
        scaffold_claude_directory(project_dir)

        # Create file in generated/
        generated_dir = project_dir / ".claude" / "agents" / "generated"
        gen_file = generated_dir / "auto-agent.md"
        gen_file.write_text("# Version 1")

        # Overwrite (simulating Materializer)
        gen_file.write_text("# Version 2")

        if gen_file.read_text() != "# Version 2":
            print(f"  FAIL: Overwrite didn't work")
            return False

        # Re-scaffold
        scaffold_claude_directory(project_dir)

        # File should still have new content
        if gen_file.read_text() != "# Version 2":
            print(f"  FAIL: Scaffold restored original content")
            return False

        print(f"  PASS: Generated files can be overwritten")
        return True


def verify_step4() -> bool:
    """
    Step 4: Settings merged, not replaced

    - Create settings with custom data
    - Update with new requirements
    - Verify all data preserved
    """
    print("Step 4: Settings merged, not replaced...")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Scaffold and create initial settings
        scaffold_claude_directory(project_dir)
        manager = SettingsManager(project_dir)

        # Create settings with custom data
        initial_settings = {
            "permissions": {"allow": ["Bash(git:*)"]},
            "mcpServers": {"server1": {"command": "cmd1"}},
            "customField": "customValue"
        }
        manager._settings_path.parent.mkdir(parents=True, exist_ok=True)
        manager._settings_path.write_text(json.dumps(initial_settings, indent=2))

        # Update with new requirements
        requirements = SettingsRequirements(
            mcp_servers={"features"},
            permissions={"Bash(npm:*)"}
        )
        result = manager.update_settings(requirements=requirements)

        if not result.success:
            print(f"  FAIL: Settings update failed")
            return False

        # Verify all data preserved
        settings = manager.load_settings()

        if "Bash(git:*)" not in settings["permissions"]["allow"]:
            print(f"  FAIL: Existing permission lost")
            return False

        if "Bash(npm:*)" not in settings["permissions"]["allow"]:
            print(f"  FAIL: New permission not added")
            return False

        if "server1" not in settings["mcpServers"]:
            print(f"  FAIL: Existing server lost")
            return False

        if "features" not in settings["mcpServers"]:
            print(f"  FAIL: New server not added")
            return False

        if settings.get("customField") != "customValue":
            print(f"  FAIL: Custom field lost")
            return False

        print(f"  PASS: Settings merged (servers: {list(settings['mcpServers'].keys())})")
        return True


def verify_step5() -> bool:
    """
    Step 5: No errors on re-run of scaffolded project

    - Scaffold multiple times
    - Verify no errors
    - Verify structure complete
    """
    print("Step 5: No errors on re-run...")

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Run scaffold 10 times
        for i in range(10):
            result = scaffold_claude_directory(project_dir)

            if not result.success:
                print(f"  FAIL: Scaffold {i+1} failed")
                return False

            if not is_claude_scaffolded(project_dir):
                print(f"  FAIL: Structure incomplete after run {i+1}")
                return False

        print(f"  PASS: 10 scaffolds all succeeded")
        return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #201: Scaffolding is idempotent and safe to re-run")
    print("=" * 60)
    print()

    results = []

    results.append(("Step 1: Checks existing directories", verify_step1()))
    print()
    results.append(("Step 2: Manual files never touched", verify_step2()))
    print()
    results.append(("Step 3: Generated files overwritable", verify_step3()))
    print()
    results.append(("Step 4: Settings merged not replaced", verify_step4()))
    print()
    results.append(("Step 5: No errors on re-run", verify_step5()))
    print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("ALL 5 VERIFICATION STEPS PASSED!")
        return 0
    else:
        print("SOME VERIFICATION STEPS FAILED")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
