"""Tests for Feature #166: verify-spec-path Makefile target.

Verifies that the verify_spec_path.py script correctly:
1. Detects when all three spec tables have rows (PASS)
2. Detects when any table is empty (FAIL with exit code 1)
3. Detects when the database file is missing (FAIL with exit code 1)
4. Outputs the correct messages
5. Integrates with the Makefile target definition
"""

import os
import sqlite3
import subprocess
import sys
import tempfile

import pytest

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "verify_spec_path.py"
)
MAKEFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "Makefile")


# ---------------------------------------------------------------------------
# Helper: create test databases
# ---------------------------------------------------------------------------


def _create_db(path, specs=0, runs=0, events=0):
    """Create a test database with the given row counts."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS agent_specs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_events (id TEXT PRIMARY KEY)")
    for i in range(specs):
        conn.execute(f"INSERT INTO agent_specs VALUES ('spec-{i}')")
    for i in range(runs):
        conn.execute(f"INSERT INTO agent_runs VALUES ('run-{i}')")
    for i in range(events):
        conn.execute(f"INSERT INTO agent_events VALUES ('event-{i}')")
    conn.commit()
    conn.close()


def _run_script(db_path):
    """Run verify_spec_path.py and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH, db_path],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


# ===========================================================================
# Test: Makefile target definition
# ===========================================================================


class TestMakefileTarget:
    """Verify the Makefile contains the verify-spec-path target."""

    def test_makefile_has_verify_spec_path_target(self):
        """Step 1: verify-spec-path target exists in Makefile."""
        with open(MAKEFILE_PATH) as f:
            content = f.read()
        assert "verify-spec-path:" in content
        assert ".PHONY: verify-spec-path" in content

    def test_makefile_target_has_help_text(self):
        """The target has a ## help comment for make help."""
        with open(MAKEFILE_PATH) as f:
            content = f.read()
        # The ## comment is used by the help target grep pattern
        assert "verify-spec-path:" in content
        for line in content.splitlines():
            if "verify-spec-path:" in line and "##" in line:
                assert "spec" in line.lower() or "assert" in line.lower()
                break
        else:
            pytest.fail("verify-spec-path target missing ## help comment")

    def test_makefile_header_mentions_verify_spec_path(self):
        """The usage header at top of Makefile lists verify-spec-path."""
        with open(MAKEFILE_PATH) as f:
            content = f.read()
        assert "verify-spec-path" in content.split("# Configuration")[0]


# ===========================================================================
# Test: Script existence and structure
# ===========================================================================


class TestScriptExists:
    """Verify the Python script exists and is well-formed."""

    def test_script_exists(self):
        """scripts/verify_spec_path.py exists."""
        assert os.path.isfile(SCRIPT_PATH), f"Script not found at {SCRIPT_PATH}"

    def test_script_is_executable_python(self):
        """Script has a proper shebang and can be parsed by Python."""
        with open(SCRIPT_PATH) as f:
            first_line = f.readline()
        assert "python" in first_line, "Missing python shebang"

    def test_script_has_main_guard(self):
        """Script uses if __name__ == '__main__' guard."""
        with open(SCRIPT_PATH) as f:
            content = f.read()
        assert '__name__' in content and '__main__' in content


# ===========================================================================
# Test: All tables populated (PASS case)
# ===========================================================================


class TestAllTablesPopulated:
    """When all three tables have rows, script exits 0."""

    def test_all_tables_have_rows_exit_zero(self, tmp_path):
        """Step 2/3/4: All counts > 0 → exit 0."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=3, runs=2, events=5)
        code, stdout, _ = _run_script(db)
        assert code == 0, f"Expected exit 0, got {code}. Output:\n{stdout}"

    def test_success_message_displayed(self, tmp_path):
        """Step 6: Success message printed when all counts > 0."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1)
        _, stdout, _ = _run_script(db)
        assert "PASS" in stdout
        assert "Spec-driven path verified" in stdout

    def test_all_tables_shown_with_counts(self, tmp_path):
        """Output shows each table name and its count."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=10, runs=5, events=20)
        _, stdout, _ = _run_script(db)
        assert "agent_specs: 10" in stdout
        assert "agent_runs: 5" in stdout
        assert "agent_events: 20" in stdout

    def test_all_tables_show_ok_status(self, tmp_path):
        """Each populated table shows [OK] status."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1)
        _, stdout, _ = _run_script(db)
        assert stdout.count("[OK]") == 3


# ===========================================================================
# Test: Empty tables (FAIL cases)
# ===========================================================================


class TestEmptyTables:
    """When any table has zero rows, script exits non-zero."""

    def test_all_empty_exit_nonzero(self, tmp_path):
        """All tables empty → exit 1."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=0, events=0)
        code, stdout, _ = _run_script(db)
        assert code != 0, f"Expected non-zero exit. Output:\n{stdout}"

    def test_specs_empty_exit_nonzero(self, tmp_path):
        """Step 2: agent_specs count is zero → exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=5, events=5)
        code, stdout, _ = _run_script(db)
        assert code != 0
        assert "agent_specs: 0" in stdout
        assert "[EMPTY]" in stdout

    def test_runs_empty_exit_nonzero(self, tmp_path):
        """Step 3: agent_runs count is zero → exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=5, runs=0, events=5)
        code, stdout, _ = _run_script(db)
        assert code != 0
        assert "agent_runs: 0" in stdout

    def test_events_empty_exit_nonzero(self, tmp_path):
        """Step 4: agent_events count is zero → exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=5, runs=5, events=0)
        code, stdout, _ = _run_script(db)
        assert code != 0
        assert "agent_events: 0" in stdout

    def test_failure_message_displayed(self, tmp_path):
        """Step 5: Failure message exactly matches spec."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=0, events=0)
        code, stdout, _ = _run_script(db)
        assert code == 1
        assert "Spec path not executed; legacy path likely used." in stdout


# ===========================================================================
# Test: Missing database
# ===========================================================================


class TestMissingDatabase:
    """When the database file doesn't exist, script exits non-zero."""

    def test_missing_db_exit_nonzero(self, tmp_path):
        """Non-existent DB path → exit 1."""
        db = str(tmp_path / "nonexistent.db")
        code, stdout, _ = _run_script(db)
        assert code == 1
        assert "not found" in stdout.lower() or "FAIL" in stdout

    def test_missing_db_shows_failure_message(self, tmp_path):
        """Non-existent DB shows the standard failure message."""
        db = str(tmp_path / "nonexistent.db")
        _, stdout, _ = _run_script(db)
        assert "Spec path not executed; legacy path likely used." in stdout


# ===========================================================================
# Test: Environment variable fallback
# ===========================================================================


class TestEnvironmentVariable:
    """Script respects AUTOBUILDR_TEST_PROJECT_PATH environment variable."""

    def test_env_var_fallback(self, tmp_path):
        """Script uses AUTOBUILDR_TEST_PROJECT_PATH when no arg given."""
        db_dir = str(tmp_path / "project")
        os.makedirs(db_dir, exist_ok=True)
        db = os.path.join(db_dir, "features.db")
        _create_db(db, specs=1, runs=1, events=1)

        env = os.environ.copy()
        env["AUTOBUILDR_TEST_PROJECT_PATH"] = db_dir
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        assert "PASS" in result.stdout
