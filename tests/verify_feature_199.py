#!/usr/bin/env python3
"""
Feature #199: .claude directory scaffolding creates standard structure

Standalone verification script that tests all 5 feature steps.

Run: python tests/verify_feature_199.py
"""
import sys
import tempfile
from pathlib import Path


def print_step(step: int, description: str) -> None:
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"Step {step}: {description}")
    print("=" * 60)


def print_result(passed: bool, message: str) -> None:
    """Print a result with emoji indicator."""
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {message}")


def verify_step1(temp_dir: Path) -> bool:
    """
    Step 1: Create .claude/ root directory if missing

    Verification:
    - Directory .claude/ is created when it doesn't exist
    - Directory has correct permissions (0755)
    """
    from api.scaffolding import scaffold_claude_directory, DEFAULT_DIR_PERMISSIONS

    print_step(1, "Create .claude/ root directory if missing")

    # Pre-condition: .claude doesn't exist
    claude_dir = temp_dir / ".claude"
    if claude_dir.exists():
        print_result(False, "Pre-condition failed: .claude already exists")
        return False

    # Action: scaffold
    result = scaffold_claude_directory(temp_dir)

    # Verification
    checks = []

    # Check 1: success is True
    checks.append(("Scaffolding succeeded", result.success))

    # Check 2: Directory exists
    checks.append(("Directory .claude/ exists", claude_dir.exists()))

    # Check 3: Is a directory
    checks.append(("Path is a directory", claude_dir.is_dir()))

    # Check 4: Correct permissions
    mode = claude_dir.stat().st_mode & 0o777
    checks.append(("Permissions are 0755", mode == DEFAULT_DIR_PERMISSIONS))

    all_passed = True
    for desc, passed in checks:
        print_result(passed, desc)
        if not passed:
            all_passed = False

    return all_passed


def verify_step2(temp_dir: Path) -> bool:
    """
    Step 2: Create .claude/agents/generated/ subdirectory

    Verification:
    - Directory .claude/agents/generated/ exists after scaffolding
    - Parent directory .claude/agents/ also exists
    """
    from api.scaffolding import scaffold_claude_directory, DEFAULT_DIR_PERMISSIONS

    print_step(2, "Create .claude/agents/generated/ subdirectory")

    result = scaffold_claude_directory(temp_dir)

    agents_generated = temp_dir / ".claude" / "agents" / "generated"
    agents_dir = temp_dir / ".claude" / "agents"

    checks = []

    # Check 1: Parent agents/ exists
    checks.append(("Directory .claude/agents/ exists", agents_dir.exists() and agents_dir.is_dir()))

    # Check 2: agents/generated exists
    checks.append(("Directory .claude/agents/generated/ exists", agents_generated.exists() and agents_generated.is_dir()))

    # Check 3: Correct permissions
    if agents_generated.exists():
        mode = agents_generated.stat().st_mode & 0o777
        checks.append(("Permissions are 0755", mode == DEFAULT_DIR_PERMISSIONS))
    else:
        checks.append(("Permissions are 0755", False))

    all_passed = True
    for desc, passed in checks:
        print_result(passed, desc)
        if not passed:
            all_passed = False

    return all_passed


def verify_step3(temp_dir: Path) -> bool:
    """
    Step 3: Create .claude/agents/manual/ subdirectory (empty)

    Verification:
    - Directory .claude/agents/manual/ exists after scaffolding
    - Directory is initially empty
    """
    from api.scaffolding import scaffold_claude_directory, DEFAULT_DIR_PERMISSIONS

    print_step(3, "Create .claude/agents/manual/ subdirectory (empty)")

    result = scaffold_claude_directory(temp_dir)

    agents_manual = temp_dir / ".claude" / "agents" / "manual"

    checks = []

    # Check 1: agents/manual exists
    checks.append(("Directory .claude/agents/manual/ exists", agents_manual.exists() and agents_manual.is_dir()))

    # Check 2: Directory is empty
    if agents_manual.exists():
        is_empty = len(list(agents_manual.iterdir())) == 0
        checks.append(("Directory is initially empty", is_empty))
    else:
        checks.append(("Directory is initially empty", False))

    # Check 3: Correct permissions
    if agents_manual.exists():
        mode = agents_manual.stat().st_mode & 0o777
        checks.append(("Permissions are 0755", mode == DEFAULT_DIR_PERMISSIONS))
    else:
        checks.append(("Permissions are 0755", False))

    all_passed = True
    for desc, passed in checks:
        print_result(passed, desc)
        if not passed:
            all_passed = False

    return all_passed


def verify_step4(temp_dir: Path) -> bool:
    """
    Step 4: Create .claude/skills/ subdirectory (empty, Phase 2)

    Verification:
    - Directory .claude/skills/ exists after scaffolding
    - Directory is initially empty
    - Directory is marked as Phase 2
    """
    from api.scaffolding import scaffold_claude_directory, DEFAULT_DIR_PERMISSIONS

    print_step(4, "Create .claude/skills/ subdirectory (empty, Phase 2)")

    result = scaffold_claude_directory(temp_dir, include_phase2=True)

    skills_dir = temp_dir / ".claude" / "skills"

    checks = []

    # Check 1: skills/ exists
    checks.append(("Directory .claude/skills/ exists", skills_dir.exists() and skills_dir.is_dir()))

    # Check 2: Directory is empty
    if skills_dir.exists():
        is_empty = len(list(skills_dir.iterdir())) == 0
        checks.append(("Directory is initially empty", is_empty))
    else:
        checks.append(("Directory is initially empty", False))

    # Check 3: Correct permissions
    if skills_dir.exists():
        mode = skills_dir.stat().st_mode & 0o777
        checks.append(("Permissions are 0755", mode == DEFAULT_DIR_PERMISSIONS))
    else:
        checks.append(("Permissions are 0755", False))

    # Check 4: Phase 2 marker
    skills_status = next(
        (d for d in result.directories if d.relative_path == "skills"),
        None
    )
    if skills_status:
        checks.append(("Directory is marked as Phase 2", skills_status.phase == 2))
    else:
        checks.append(("Directory is marked as Phase 2", False))

    all_passed = True
    for desc, passed in checks:
        print_result(passed, desc)
        if not passed:
            all_passed = False

    return all_passed


def verify_step5(temp_dir: Path) -> bool:
    """
    Step 5: Create .claude/commands/ subdirectory (empty, Phase 2)

    Verification:
    - Directory .claude/commands/ exists after scaffolding
    - Directory is initially empty
    - Directory is marked as Phase 2
    """
    from api.scaffolding import scaffold_claude_directory, DEFAULT_DIR_PERMISSIONS

    print_step(5, "Create .claude/commands/ subdirectory (empty, Phase 2)")

    result = scaffold_claude_directory(temp_dir, include_phase2=True)

    commands_dir = temp_dir / ".claude" / "commands"

    checks = []

    # Check 1: commands/ exists
    checks.append(("Directory .claude/commands/ exists", commands_dir.exists() and commands_dir.is_dir()))

    # Check 2: Directory is empty
    if commands_dir.exists():
        is_empty = len(list(commands_dir.iterdir())) == 0
        checks.append(("Directory is initially empty", is_empty))
    else:
        checks.append(("Directory is initially empty", False))

    # Check 3: Correct permissions
    if commands_dir.exists():
        mode = commands_dir.stat().st_mode & 0o777
        checks.append(("Permissions are 0755", mode == DEFAULT_DIR_PERMISSIONS))
    else:
        checks.append(("Permissions are 0755", False))

    # Check 4: Phase 2 marker
    commands_status = next(
        (d for d in result.directories if d.relative_path == "commands"),
        None
    )
    if commands_status:
        checks.append(("Directory is marked as Phase 2", commands_status.phase == 2))
    else:
        checks.append(("Directory is marked as Phase 2", False))

    all_passed = True
    for desc, passed in checks:
        print_result(passed, desc)
        if not passed:
            all_passed = False

    return all_passed


def main() -> int:
    """Run all verification steps."""
    print("\nFeature #199: .claude directory scaffolding creates standard structure")
    print("=" * 70)

    steps_passed = 0
    total_steps = 5

    # Each step uses a fresh temp directory to ensure isolation
    for step_num, verify_func in [
        (1, verify_step1),
        (2, verify_step2),
        (3, verify_step3),
        (4, verify_step4),
        (5, verify_step5),
    ]:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                if verify_func(Path(tmpdir)):
                    steps_passed += 1
            except Exception as e:
                print(f"\n  ERROR: {e}")

    # Summary
    print("\n" + "=" * 70)
    print(f"SUMMARY: {steps_passed}/{total_steps} steps passed")
    print("=" * 70)

    if steps_passed == total_steps:
        print("\nAll verification steps PASSED!")
        return 0
    else:
        print(f"\nFailed {total_steps - steps_passed} step(s)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
