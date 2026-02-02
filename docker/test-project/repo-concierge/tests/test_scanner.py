"""Scanner unit tests."""

import os
import shutil
import tempfile

import pytest

from repo_concierge.scanner import discover_files, scan_directory, scan_file


class TestDiscoverFilesRecursive:
    """Test that the scanner discovers files recursively across nested directories."""

    @pytest.fixture
    def nested_dir(self, tmp_path):
        """Create a nested directory structure with files at multiple levels.

        Structure:
            root/
                root_file.py
                root_script.sh
                not_eligible.txt        (should be skipped)
                not_eligible.exe        (should be skipped)
                level1/
                    app.js
                    config.yaml
                    level2/
                        deep_file.py
                        deep_script.sh
                        level3/
                            deepest.py
                            deepest.js
                another_dir/
                    side.yaml
                    subdir/
                        nested.py
        """
        # Root level files
        (tmp_path / "root_file.py").write_text("# Root python file\n")
        (tmp_path / "root_script.sh").write_text("#!/bin/bash\necho hello\n")
        (tmp_path / "not_eligible.txt").write_text("This is a text file\n")
        (tmp_path / "not_eligible.exe").write_text("Binary-like\n")

        # Level 1
        level1 = tmp_path / "level1"
        level1.mkdir()
        (level1 / "app.js").write_text("console.log('hi');\n")
        (level1 / "config.yaml").write_text("name: test\n")

        # Level 2
        level2 = level1 / "level2"
        level2.mkdir()
        (level2 / "deep_file.py").write_text("# Level 2 python\n")
        (level2 / "deep_script.sh").write_text("#!/bin/bash\necho deep\n")

        # Level 3
        level3 = level2 / "level3"
        level3.mkdir()
        (level3 / "deepest.py").write_text("# Level 3 python\n")
        (level3 / "deepest.js").write_text("// JS at level 3\n")

        # Another directory branch
        another = tmp_path / "another_dir"
        another.mkdir()
        (another / "side.yaml").write_text("name: deep_yaml\n")

        subdir = another / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# Python in subdir\n")

        return tmp_path

    def test_discovers_all_eligible_files(self, nested_dir):
        """Verify all eligible files at all levels are discovered."""
        files = discover_files(str(nested_dir))

        # Should find exactly 10 eligible files
        basenames = sorted([os.path.basename(f) for f in files])
        expected_basenames = sorted([
            "root_file.py",
            "root_script.sh",
            "app.js",
            "config.yaml",
            "deep_file.py",
            "deep_script.sh",
            "deepest.py",
            "deepest.js",
            "side.yaml",
            "nested.py",
        ])
        assert basenames == expected_basenames, (
            f"Expected {expected_basenames}, got {basenames}"
        )

    def test_excludes_ineligible_files(self, nested_dir):
        """Verify .txt and .exe files are not discovered."""
        files = discover_files(str(nested_dir))
        basenames = [os.path.basename(f) for f in files]
        assert "not_eligible.txt" not in basenames
        assert "not_eligible.exe" not in basenames

    def test_files_count_matches(self, nested_dir):
        """Verify the number of discovered files matches the expected count."""
        files = discover_files(str(nested_dir))
        assert len(files) == 10, f"Expected 10 eligible files, got {len(files)}"

    def test_files_at_all_depth_levels(self, nested_dir):
        """Verify files are found at every depth level (root, level1, level2, level3, another_dir)."""
        files = discover_files(str(nested_dir))
        relative_paths = [os.path.relpath(f, str(nested_dir)) for f in files]

        # Check files exist at root level
        assert any(os.sep not in p for p in relative_paths), (
            "No files found at root level"
        )

        # Check files exist at level1
        assert any(p.startswith("level1" + os.sep) and p.count(os.sep) == 1
                    for p in relative_paths), "No files found at level1"

        # Check files exist at level2
        assert any("level2" in p and p.count(os.sep) == 2
                    for p in relative_paths), "No files found at level2"

        # Check files exist at level3 (3 levels deep)
        assert any("level3" in p and p.count(os.sep) == 3
                    for p in relative_paths), "No files found at level3"

        # Check files exist in another_dir branch
        assert any(p.startswith("another_dir" + os.sep)
                    for p in relative_paths), "No files found in another_dir"

    def test_scan_directory_files_scanned_count(self, nested_dir):
        """Verify scan_directory reports the correct files_scanned count."""
        result = scan_directory(str(nested_dir), quiet=True)
        assert result.files_scanned == 10, (
            f"Expected files_scanned=10, got {result.files_scanned}"
        )

    def test_ignores_excluded_directories(self, nested_dir):
        """Verify that directories like .git, node_modules, __pycache__ are skipped."""
        # Create ignored directories with eligible files inside
        git_dir = nested_dir / ".git"
        git_dir.mkdir()
        (git_dir / "config.py").write_text("# git config\n")

        node_modules = nested_dir / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.js").write_text("module.exports = {};\n")

        pycache = nested_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.py").write_text("# cached\n")

        venv = nested_dir / ".venv"
        venv.mkdir()
        (venv / "activate.sh").write_text("# activate\n")

        files = discover_files(str(nested_dir))
        basenames = [os.path.basename(f) for f in files]

        # Files in ignored directories should NOT be found
        assert "config.py" not in basenames or all(
            ".git" not in f for f in files
        ), "Files in .git should be ignored"
        assert "package.js" not in basenames, "Files in node_modules should be ignored"
        assert "cached.py" not in basenames, "Files in __pycache__ should be ignored"
        assert "activate.sh" not in basenames, "Files in .venv should be ignored"

        # Still should find the 10 original eligible files
        assert len(files) == 10

    def test_returns_absolute_paths(self, nested_dir):
        """Verify all returned file paths are absolute."""
        files = discover_files(str(nested_dir))
        for f in files:
            assert os.path.isabs(f), f"Path is not absolute: {f}"

    def test_returns_sorted_paths(self, nested_dir):
        """Verify files are returned in sorted order."""
        files = discover_files(str(nested_dir))
        assert files == sorted(files), "Files should be returned in sorted order"


class TestEmptyFileScanning:
    """Test that the scanner handles empty files without error (Feature #52)."""

    @pytest.fixture
    def dir_with_empty_file(self, tmp_path):
        """Create a directory containing a single empty .py file."""
        empty_file = tmp_path / "empty_module.py"
        empty_file.write_text("")  # Create empty file
        return tmp_path, empty_file

    def test_empty_file_is_discovered(self, dir_with_empty_file):
        """Step 1+2: Empty .py file is discovered by the scanner."""
        tmpdir, empty_file = dir_with_empty_file
        files = discover_files(str(tmpdir))
        assert len(files) == 1, f"Expected 1 file, got {len(files)}"
        assert files[0] == str(empty_file)

    def test_scan_file_no_error(self, dir_with_empty_file):
        """Step 3: Scanning an empty file raises no error."""
        _, empty_file = dir_with_empty_file
        # Should not raise any exception
        findings = scan_file(str(empty_file))
        assert isinstance(findings, list)

    def test_scan_file_no_findings(self, dir_with_empty_file):
        """Step 4: No findings are produced for the empty file."""
        _, empty_file = dir_with_empty_file
        findings = scan_file(str(empty_file))
        assert len(findings) == 0, f"Expected 0 findings, got {len(findings)}"

    def test_empty_file_counted_in_files_scanned(self, dir_with_empty_file):
        """Step 5: The empty file is counted in files_scanned."""
        tmpdir, _ = dir_with_empty_file
        result = scan_directory(str(tmpdir), quiet=True)
        assert result.files_scanned == 1, (
            f"Expected files_scanned=1, got {result.files_scanned}"
        )

    def test_scan_directory_no_findings_for_empty(self, dir_with_empty_file):
        """Full scan produces zero findings for directory with only an empty file."""
        tmpdir, _ = dir_with_empty_file
        result = scan_directory(str(tmpdir), quiet=True)
        assert len(result.findings) == 0
        assert result.high_count == 0
        assert result.medium_count == 0
        assert result.low_count == 0

    def test_empty_file_among_other_files(self, tmp_path):
        """Empty file is handled correctly alongside non-empty files."""
        # Create one empty file and one file with content
        (tmp_path / "empty.py").write_text("")
        (tmp_path / "has_content.py").write_text("print('hello')\n")

        result = scan_directory(str(tmp_path), quiet=True)
        assert result.files_scanned == 2, (
            f"Expected 2 files scanned, got {result.files_scanned}"
        )
        # No findings from either file (neither has risky patterns)
        assert len(result.findings) == 0


class TestDefaultIgnoreRules:
    """Test that default ignore rules are applied without explicit configuration (Feature #66)."""

    @pytest.fixture
    def dir_with_ignored_dirs(self, tmp_path):
        """Create a directory with .git/, node_modules/, and regular directories.

        Structure:
            root/
                .git/
                    script.js       (should be ignored)
                node_modules/
                    package.js      (should be ignored)
                src/
                    main.py         (should be scanned)
                lib/
                    util.js         (should be scanned)
        """
        # Create ignored directories with files
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "script.js").write_text("console.log('hidden in .git');\n")

        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.js").write_text("module.exports = {};\n")

        # Create normal directories with files that should be scanned
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello from src')\n")

        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()
        (lib_dir / "util.js").write_text("export default 42;\n")

        return tmp_path

    def test_step1_dir_has_git_and_node_modules(self, dir_with_ignored_dirs):
        """Step 1: Verify the test directory has .git/ and node_modules/ subdirectories."""
        assert (dir_with_ignored_dirs / ".git").is_dir()
        assert (dir_with_ignored_dirs / "node_modules").is_dir()
        assert (dir_with_ignored_dirs / ".git" / "script.js").exists()
        assert (dir_with_ignored_dirs / "node_modules" / "package.js").exists()

    def test_step2_scan_without_config_flags(self, dir_with_ignored_dirs):
        """Step 2: Run scan without any config flags."""
        # Simply calling scan_directory with no extra args is equivalent to CLI without flags
        result = scan_directory(str(dir_with_ignored_dirs), quiet=True)
        # Should successfully complete and return a ScanResult
        assert result is not None
        assert hasattr(result, "files_scanned")
        assert hasattr(result, "ignore_rules")

    def test_step3_ignored_dirs_skipped(self, dir_with_ignored_dirs):
        """Step 3: Verify files in .git/ and node_modules/ were skipped."""
        files = discover_files(str(dir_with_ignored_dirs))

        # Check that only files from src/ and lib/ are found
        assert len(files) == 2, f"Expected 2 files, got {len(files)}"

        basenames = [os.path.basename(f) for f in files]
        assert "main.py" in basenames, "main.py should be discovered"
        assert "util.js" in basenames, "util.js should be discovered"

        # Files in ignored directories should NOT be found
        assert "script.js" not in basenames, "script.js in .git/ should be ignored"
        assert "package.js" not in basenames, "package.js in node_modules/ should be ignored"

        # Verify that no path contains .git or node_modules
        for f in files:
            assert ".git" not in f, f"File {f} should not be in .git/"
            assert "node_modules" not in f, f"File {f} should not be in node_modules/"

    def test_step4_ignore_rules_in_report(self, dir_with_ignored_dirs):
        """Step 4: Verify the report's ignore_rules field lists the defaults."""
        from repo_concierge.scanner import IGNORE_DIRS

        result = scan_directory(str(dir_with_ignored_dirs), quiet=True)

        # The ignore_rules field should list all default ignored directories
        assert result.ignore_rules is not None, "ignore_rules should not be None"
        assert len(result.ignore_rules) > 0, "ignore_rules should not be empty"

        # Check that the main defaults are present
        assert ".git" in result.ignore_rules, ".git should be in ignore_rules"
        assert "node_modules" in result.ignore_rules, "node_modules should be in ignore_rules"
        assert ".venv" in result.ignore_rules, ".venv should be in ignore_rules"
        assert "__pycache__" in result.ignore_rules, "__pycache__ should be in ignore_rules"

        # Verify ignore_rules matches the IGNORE_DIRS constant
        assert set(result.ignore_rules) == IGNORE_DIRS, (
            f"ignore_rules should match IGNORE_DIRS: {result.ignore_rules} != {IGNORE_DIRS}"
        )

    def test_all_default_ignore_rules_applied(self, tmp_path):
        """Verify ALL default ignore rules are applied (not just .git and node_modules)."""
        from repo_concierge.scanner import IGNORE_DIRS

        # Create directories for each ignore rule with a file inside
        for ignore_dir in IGNORE_DIRS:
            ignored = tmp_path / ignore_dir
            ignored.mkdir()
            (ignored / "hidden.py").write_text(f"# Hidden in {ignore_dir}\n")

        # Also create a normal directory
        normal = tmp_path / "normal"
        normal.mkdir()
        (normal / "visible.py").write_text("# This should be found\n")

        files = discover_files(str(tmp_path))

        # Only the visible.py should be found
        assert len(files) == 1, f"Expected 1 file, got {len(files)}: {files}"
        assert "visible.py" in files[0], f"Expected visible.py, got {files[0]}"

        # Verify no file from any ignored directory is found
        basenames = [os.path.basename(f) for f in files]
        assert "hidden.py" not in basenames, "hidden.py from ignored dirs should not be found"


class TestScannerReadOnly:
    """Test that the scanner is read-only and never modifies files (Feature #67).

    The scanner should only read files. It must never modify, create, or delete
    scanned files.
    """

    import hashlib
    import time

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Create a sample directory with files for testing.

        Structure:
            root/
                script.sh       (contains risky patterns)
                config.py       (clean file)
                data.yaml       (clean file)
                subdir/
                    module.js   (clean file)
        """
        # Create files with known content
        (tmp_path / "script.sh").write_text("#!/bin/bash\nrm -rf /tmp/test\nsudo rm /important\n")
        (tmp_path / "config.py").write_text("# Configuration file\nDEBUG = True\n")
        (tmp_path / "data.yaml").write_text("name: test\nversion: 1.0\n")

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "module.js").write_text("export function hello() {\n  console.log('hi');\n}\n")

        return tmp_path

    def _get_file_info(self, path):
        """Get file metadata: mtime, size, and content checksum.

        Args:
            path: Path to the file

        Returns:
            dict with 'mtime', 'size', and 'checksum' keys
        """
        import hashlib
        stat = os.stat(path)
        with open(path, 'rb') as f:
            content = f.read()
        return {
            'mtime': stat.st_mtime,
            'size': stat.st_size,
            'checksum': hashlib.sha256(content).hexdigest()
        }

    def _collect_all_files(self, directory):
        """Recursively collect all files in a directory.

        Args:
            directory: Root directory to scan

        Returns:
            dict mapping file paths to their metadata
        """
        all_files = {}
        for root, dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                all_files[filepath] = self._get_file_info(filepath)
        return all_files

    def test_step1_record_timestamps_and_checksums(self, sample_dir):
        """Step 1: Record timestamps and checksums of all files in the target directory."""
        # Collect all file info before scan
        before_scan = self._collect_all_files(sample_dir)

        # Verify we captured 4 files
        assert len(before_scan) == 4, f"Expected 4 files, got {len(before_scan)}"

        # Verify each file has mtime, size, and checksum
        for filepath, info in before_scan.items():
            assert 'mtime' in info, f"Missing mtime for {filepath}"
            assert 'size' in info, f"Missing size for {filepath}"
            assert 'checksum' in info, f"Missing checksum for {filepath}"
            assert info['size'] > 0, f"File {filepath} should not be empty"

    def test_step2_and_3_scan_and_verify_unchanged(self, sample_dir):
        """Step 2+3: Run a full scan and verify all file timestamps and checksums are unchanged."""
        # Step 1: Record before
        before_scan = self._collect_all_files(sample_dir)

        # Step 2: Run a full scan (this will find risky patterns in script.sh)
        result = scan_directory(str(sample_dir), quiet=True)

        # Verify scan completed and found some findings
        assert result is not None
        assert result.files_scanned == 4, f"Expected 4 files scanned, got {result.files_scanned}"
        # Should find SHELL-001 (rm -rf) and SHELL-002 (sudo rm) in script.sh
        assert len(result.findings) >= 2, f"Expected at least 2 findings, got {len(result.findings)}"

        # Step 3: Verify all file timestamps and checksums are unchanged
        after_scan = self._collect_all_files(sample_dir)

        assert len(after_scan) == len(before_scan), \
            f"File count changed: before={len(before_scan)}, after={len(after_scan)}"

        for filepath in before_scan:
            assert filepath in after_scan, f"File disappeared: {filepath}"
            before = before_scan[filepath]
            after = after_scan[filepath]

            assert before['mtime'] == after['mtime'], \
                f"Timestamp changed for {filepath}: {before['mtime']} -> {after['mtime']}"
            assert before['size'] == after['size'], \
                f"Size changed for {filepath}: {before['size']} -> {after['size']}"
            assert before['checksum'] == after['checksum'], \
                f"Content changed for {filepath}: {before['checksum']} -> {after['checksum']}"

    def test_step4_no_new_files_created(self, sample_dir):
        """Step 4: Verify no new files were created in the target directory."""
        # Record files before scan
        before_files = set(self._collect_all_files(sample_dir).keys())

        # Run scan
        scan_directory(str(sample_dir), quiet=True)

        # Record files after scan
        after_files = set(self._collect_all_files(sample_dir).keys())

        # Check for new files
        new_files = after_files - before_files
        assert len(new_files) == 0, f"New files were created: {new_files}"

    def test_step5_no_files_deleted(self, sample_dir):
        """Step 5: Verify no files were deleted from the target directory."""
        # Record files before scan
        before_files = set(self._collect_all_files(sample_dir).keys())

        # Run scan
        scan_directory(str(sample_dir), quiet=True)

        # Record files after scan
        after_files = set(self._collect_all_files(sample_dir).keys())

        # Check for deleted files
        deleted_files = before_files - after_files
        assert len(deleted_files) == 0, f"Files were deleted: {deleted_files}"

    def test_comprehensive_read_only_verification(self, sample_dir):
        """Complete verification: scan does not modify, create, or delete any files."""
        import time

        # Record EVERYTHING before scan
        before_files = self._collect_all_files(sample_dir)
        before_file_set = set(before_files.keys())

        # Small delay to ensure any timestamp changes would be detectable
        time.sleep(0.1)

        # Run a full verbose scan (to test all code paths)
        result = scan_directory(str(sample_dir), verbose=True, quiet=False)

        # Record EVERYTHING after scan
        after_files = self._collect_all_files(sample_dir)
        after_file_set = set(after_files.keys())

        # === Verification ===

        # 1. No new files
        new_files = after_file_set - before_file_set
        assert len(new_files) == 0, f"Scanner created files: {new_files}"

        # 2. No deleted files
        deleted_files = before_file_set - after_file_set
        assert len(deleted_files) == 0, f"Scanner deleted files: {deleted_files}"

        # 3. No modified files (check both mtime and content)
        for filepath in before_file_set:
            before = before_files[filepath]
            after = after_files[filepath]

            # Timestamp unchanged
            assert before['mtime'] == after['mtime'], \
                f"Scanner modified timestamp of {filepath}"

            # Size unchanged
            assert before['size'] == after['size'], \
                f"Scanner changed size of {filepath}"

            # Content unchanged (checksum)
            assert before['checksum'] == after['checksum'], \
                f"Scanner modified content of {filepath}"

    def test_scan_with_report_does_not_modify_target(self, sample_dir):
        """Verify that generating a report does not affect the scanned directory."""
        from argparse import Namespace

        # Create a report directory within the current working directory
        # (path traversal protection requires output to be within cwd)
        cwd = os.getcwd()
        report_dir = os.path.join(cwd, "test_reports_temp")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, "test_report.json")

        try:
            # Record state before scan
            before_files = self._collect_all_files(sample_dir)

            # Run scan with report generation (via run_scan)
            from repo_concierge.scanner import run_scan

            args = Namespace(
                path=str(sample_dir),
                verbose=False,
                quiet=True,
                fail_on="none",
                format="json",
                out=report_path,
                config=None
            )

            exit_code = run_scan(args)

            # Verify report was written
            assert os.path.exists(report_path), "Report should be created"

            # Verify target directory is unchanged
            after_files = self._collect_all_files(sample_dir)

            assert before_files.keys() == after_files.keys(), "File set should be unchanged"

            for filepath in before_files:
                assert before_files[filepath]['checksum'] == after_files[filepath]['checksum'], \
                    f"File {filepath} was modified"
        finally:
            # Clean up the test report directory
            import shutil
            if os.path.exists(report_dir):
                shutil.rmtree(report_dir)

    def test_scan_with_findings_does_not_modify(self, sample_dir):
        """Verify that detecting findings does not cause any file modifications."""
        # This test specifically targets files that WILL trigger findings
        # to ensure the finding detection process itself doesn't modify files

        # Record the risky script.sh specifically
        script_path = sample_dir / "script.sh"
        before_info = self._get_file_info(script_path)

        # Run scan (will detect rm -rf and sudo rm in script.sh)
        result = scan_directory(str(sample_dir), quiet=True)

        # Verify findings were detected in script.sh
        script_findings = [f for f in result.findings if 'script.sh' in f.file_path]
        assert len(script_findings) >= 2, "Should find at least 2 findings in script.sh"

        # Verify the file that triggered findings is unchanged
        after_info = self._get_file_info(script_path)

        assert before_info['mtime'] == after_info['mtime'], \
            "script.sh timestamp should not change after being scanned"
        assert before_info['checksum'] == after_info['checksum'], \
            "script.sh content should not change after being scanned"


class TestPathTraversalProtection:
    """Tests for path traversal protection in --out flag (Feature #68)."""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Create a sample directory with a scannable file."""
        sample = tmp_path / "sample"
        sample.mkdir()
        (sample / "test.py").write_text("# Test file\n")
        return sample

    def test_relative_path_traversal_blocked(self, sample_dir):
        """Step 1: Verify ../escape.md is blocked."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=True,
            fail_on="none",
            format="md",
            out="../escape_test.md",
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 1, "Path traversal with ../ should be blocked (exit code 1)"

    def test_multiple_level_traversal_blocked(self, sample_dir):
        """Step 1: Verify ../../../etc/passwd style paths are blocked."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=True,
            fail_on="none",
            format="md",
            out="../../../etc/passwd",
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 1, "Multi-level path traversal should be blocked"

    def test_absolute_path_outside_cwd_blocked(self, sample_dir, tmp_path):
        """Step 1: Verify absolute paths outside cwd are blocked."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        # tmp_path is definitely outside the project cwd
        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=True,
            fail_on="none",
            format="md",
            out=str(tmp_path / "escape_report.md"),
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 1, "Absolute path outside cwd should be blocked"

    def test_no_file_written_to_traversal_target(self, sample_dir, tmp_path):
        """Step 3: Verify no file is written to the traversal target."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        escape_target = tmp_path / "should_not_exist.md"

        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=True,
            fail_on="none",
            format="md",
            out=str(escape_target),
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 1, "Should fail with path traversal"
        assert not escape_target.exists(), "No file should be written to traversal target"

    def test_safe_path_within_cwd_works(self, sample_dir):
        """Step 2: Verify safe paths within cwd are allowed."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan
        import shutil

        cwd = os.getcwd()
        safe_dir = os.path.join(cwd, "test_safe_reports_temp")
        os.makedirs(safe_dir, exist_ok=True)
        safe_path = os.path.join(safe_dir, "safe_report.md")

        try:
            args = Namespace(
                path=str(sample_dir),
                verbose=False,
                quiet=True,
                fail_on="none",
                format="md",
                out=safe_path,
                config=None
            )

            exit_code = run_scan(args)
            assert exit_code == 0, "Safe path within cwd should be allowed"
            assert os.path.exists(safe_path), "Report should be created at safe path"
        finally:
            if os.path.exists(safe_dir):
                shutil.rmtree(safe_dir)

    def test_default_reports_path_works(self, sample_dir):
        """Verify default reports/ path still works."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=True,
            fail_on="none",
            format="md",
            out=None,  # Use default path
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 0, "Default reports/ path should work"
        assert os.path.exists("reports/security_audit.md"), "Default report should be created"

    def test_error_message_shows_resolved_path(self, sample_dir, capsys):
        """Verify error message is informative."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=False,  # Enable output to see error message
            fail_on="none",
            format="md",
            out="../escape.md",
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 1

        captured = capsys.readouterr()
        assert "escapes working directory" in captured.err, \
            "Error message should explain the path escapes working directory"
        assert "Must be within" in captured.err, \
            "Error message should show the required working directory"

    def test_hidden_traversal_in_subdir_blocked(self, sample_dir):
        """Verify hidden traversal like subdir/../../../escape is blocked."""
        from argparse import Namespace
        from repo_concierge.scanner import run_scan

        args = Namespace(
            path=str(sample_dir),
            verbose=False,
            quiet=True,
            fail_on="none",
            format="md",
            out="subdir/../../../escape.md",
            config=None
        )

        exit_code = run_scan(args)
        assert exit_code == 1, "Hidden path traversal should be blocked"
