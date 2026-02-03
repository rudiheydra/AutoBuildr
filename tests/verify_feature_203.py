#!/usr/bin/env python3
"""
Verification script for Feature #203: Scaffolding can be triggered manually via API

This script verifies all 4 feature verification steps without needing a running server.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


def verify_step1_endpoint_created():
    """
    Step 1: POST /api/projects/{id}/scaffold endpoint created

    Verifies that the endpoint exists in the router with the correct method.
    """
    print("\n=== Step 1: POST /api/projects/{id}/scaffold endpoint created ===")

    from server.routers.projects import router

    # Find the scaffold route
    scaffold_routes = [
        route for route in router.routes
        if hasattr(route, "path") and "scaffold" in route.path
    ]

    if len(scaffold_routes) != 1:
        print(f"FAIL: Expected 1 scaffold route, found {len(scaffold_routes)}")
        return False

    route = scaffold_routes[0]

    if "POST" not in route.methods:
        print(f"FAIL: Scaffold route doesn't support POST, methods: {route.methods}")
        return False

    if "scaffold" not in route.path or "{name}" not in route.path:
        print(f"FAIL: Unexpected route path: {route.path}")
        return False

    print(f"PASS: Endpoint found at {route.path} with methods {route.methods}")
    return True


def verify_step2_runs_scaffolding():
    """
    Step 2: Endpoint runs scaffolding for specified project

    Verifies that calling the endpoint creates the .claude directory structure.
    """
    print("\n=== Step 2: Endpoint runs scaffolding for specified project ===")

    import asyncio
    from server.routers.projects import scaffold_project
    from server.schemas import ScaffoldRequest

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()

        # Mock registry
        with patch("server.routers.projects._get_registry_functions") as mock_get:
            mock_get.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(return_value=project_dir),
                MagicMock(return_value={}),
                MagicMock(),
            )
            with patch("server.routers.projects._init_imports"):

                # Verify .claude doesn't exist
                claude_dir = project_dir / ".claude"
                if claude_dir.exists():
                    print("FAIL: .claude directory already exists")
                    return False

                # Call the endpoint
                request = ScaffoldRequest()
                response = asyncio.get_event_loop().run_until_complete(
                    scaffold_project("test_project", request)
                )

                # Verify .claude was created
                if not claude_dir.exists():
                    print("FAIL: .claude directory was not created")
                    return False

                if not response.success:
                    print(f"FAIL: Response indicates failure: {response.message}")
                    return False

                # Verify subdirectories
                subdirs = [
                    claude_dir / "agents" / "generated",
                    claude_dir / "agents" / "manual",
                ]
                for subdir in subdirs:
                    if not subdir.exists():
                        print(f"FAIL: Subdirectory not created: {subdir}")
                        return False

                print("PASS: Scaffolding created .claude directory and subdirectories")
                return True


def verify_step3_returns_status():
    """
    Step 3: Returns status of created/existing directories and files

    Verifies that the response includes detailed status information.
    """
    print("\n=== Step 3: Returns status of created/existing directories and files ===")

    import asyncio
    from server.routers.projects import scaffold_project
    from server.schemas import ScaffoldRequest

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()

        # Mock registry
        with patch("server.routers.projects._get_registry_functions") as mock_get:
            mock_get.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(return_value=project_dir),
                MagicMock(return_value={}),
                MagicMock(),
            )
            with patch("server.routers.projects._init_imports"):

                request = ScaffoldRequest(include_claude_md=True)
                response = asyncio.get_event_loop().run_until_complete(
                    scaffold_project("test_project", request)
                )

                # Check required response fields
                checks = [
                    ("success", response.success is not None),
                    ("project_name", response.project_name == "test_project"),
                    ("project_dir", response.project_dir is not None),
                    ("claude_root", response.claude_root is not None),
                    ("directories", len(response.directories) > 0),
                    ("directories_created", response.directories_created >= 0),
                    ("directories_existed", response.directories_existed >= 0),
                    ("directories_failed", response.directories_failed >= 0),
                    ("message", response.message is not None),
                ]

                all_pass = True
                for name, check in checks:
                    if not check:
                        print(f"FAIL: Field '{name}' check failed")
                        all_pass = False

                # Check directory status details
                if response.directories:
                    first_dir = response.directories[0]
                    dir_checks = [
                        ("path", first_dir.path is not None),
                        ("relative_path", first_dir.relative_path is not None),
                        ("existed", isinstance(first_dir.existed, bool)),
                        ("created", isinstance(first_dir.created, bool)),
                    ]
                    for name, check in dir_checks:
                        if not check:
                            print(f"FAIL: Directory field '{name}' check failed")
                            all_pass = False

                # Check CLAUDE.md status if included
                if response.claude_md:
                    claude_checks = [
                        ("path", response.claude_md.path is not None),
                        ("existed", isinstance(response.claude_md.existed, bool)),
                        ("created", isinstance(response.claude_md.created, bool)),
                        ("skipped", isinstance(response.claude_md.skipped, bool)),
                    ]
                    for name, check in claude_checks:
                        if not check:
                            print(f"FAIL: CLAUDE.md field '{name}' check failed")
                            all_pass = False

                if all_pass:
                    print("PASS: Response includes all required status fields")
                return all_pass


def verify_step4_repair_reset():
    """
    Step 4: Useful for repair/reset scenarios

    Verifies that scaffolding is idempotent and can repair missing directories.
    """
    print("\n=== Step 4: Useful for repair/reset scenarios ===")

    import asyncio
    from server.routers.projects import scaffold_project
    from server.schemas import ScaffoldRequest

    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()

        # Mock registry
        with patch("server.routers.projects._get_registry_functions") as mock_get:
            mock_get.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(return_value=project_dir),
                MagicMock(return_value={}),
                MagicMock(),
            )
            with patch("server.routers.projects._init_imports"):

                request = ScaffoldRequest()

                # First run - creates directories
                response1 = asyncio.get_event_loop().run_until_complete(
                    scaffold_project("test_project", request)
                )

                if not response1.success:
                    print(f"FAIL: First scaffolding failed: {response1.message}")
                    return False

                if response1.directories_created == 0:
                    print("FAIL: First run should have created directories")
                    return False

                # Delete a directory to simulate damage
                skills_dir = project_dir / ".claude" / "skills"
                if skills_dir.exists():
                    skills_dir.rmdir()

                if skills_dir.exists():
                    print("FAIL: Could not delete skills directory for test")
                    return False

                # Second run - repairs
                response2 = asyncio.get_event_loop().run_until_complete(
                    scaffold_project("test_project", request)
                )

                if not response2.success:
                    print(f"FAIL: Second scaffolding failed: {response2.message}")
                    return False

                # Skills directory should be recreated
                if not skills_dir.exists():
                    print("FAIL: Skills directory was not repaired")
                    return False

                print("PASS: Scaffolding is idempotent and can repair missing directories")
                return True


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #203: Scaffolding can be triggered manually via API")
    print("=" * 60)

    results = {
        "Step 1: Endpoint created": verify_step1_endpoint_created(),
        "Step 2: Runs scaffolding": verify_step2_runs_scaffolding(),
        "Step 3: Returns status": verify_step3_returns_status(),
        "Step 4: Repair/reset": verify_step4_repair_reset(),
    }

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    all_pass = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {step}: {status}")
        if not passed:
            all_pass = False

    print("\n" + "=" * 60)
    if all_pass:
        print("All verification steps PASSED!")
        return 0
    else:
        print("Some verification steps FAILED!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
