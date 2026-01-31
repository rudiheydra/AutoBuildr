"""Tests for Feature #168: verify-spec-path fails when legacy path is used.

Negative test: when the orchestrator uses the legacy path
(AUTOBUILDR_USE_KERNEL=false or unset), make verify-spec-path must exit non-zero
because the spec tables will be empty.

Verification steps:
1. Set AUTOBUILDR_USE_KERNEL=false or leave it unset
2. Run a build through the orchestrator (simulated: legacy path leaves spec tables empty)
3. Run make verify-spec-path (via the underlying script)
4. Confirm it exits non-zero
5. Confirm the error message clearly states:
   'Spec path not executed; legacy path likely used.'
"""

import os
import sqlite3
import subprocess
import sys

import pytest

# Path to the verify_spec_path.py script
SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "verify_spec_path.py"
)

# Path to the migration_flag module for import tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_legacy_db(path):
    """Create a database that simulates the legacy path output.

    The legacy path does NOT populate agent_specs, agent_runs, or agent_events.
    These tables either don't exist or are empty. The features table may exist
    and have data (features are managed independently of the spec path).
    """
    conn = sqlite3.connect(path)
    # Legacy path creates features table but NOT spec tables
    conn.execute(
        "CREATE TABLE IF NOT EXISTS features ("
        "  id INTEGER PRIMARY KEY,"
        "  name TEXT,"
        "  status TEXT"
        ")"
    )
    # Insert some feature data to simulate a project that ran via legacy path
    conn.execute("INSERT INTO features VALUES (1, 'Test feature', 'completed')")
    conn.execute("INSERT INTO features VALUES (2, 'Another feature', 'pending')")

    # Create the spec tables but leave them EMPTY (as they would be
    # when legacy path is used - tables may exist from schema but have no rows)
    conn.execute("CREATE TABLE IF NOT EXISTS agent_specs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_events (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY)")

    conn.commit()
    conn.close()


def _create_kernel_db(path):
    """Create a database that simulates the kernel/spec path output.

    The kernel path DOES populate agent_specs, agent_runs, and agent_events.
    """
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS agent_specs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_events (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY)")

    # Kernel path populates all spec tables
    conn.execute("INSERT INTO agent_specs VALUES ('spec-1')")
    conn.execute("INSERT INTO agent_specs VALUES ('spec-2')")
    conn.execute("INSERT INTO agent_runs VALUES ('run-1')")
    conn.execute("INSERT INTO agent_events VALUES ('event-1')")
    conn.execute("INSERT INTO agent_events VALUES ('event-2')")
    conn.execute("INSERT INTO agent_events VALUES ('event-3')")

    conn.commit()
    conn.close()


def _run_verify_script(db_path, env_overrides=None):
    """Run verify_spec_path.py with the given DB and environment.

    Returns:
        (exit_code, stdout, stderr) tuple.
    """
    env = os.environ.copy()
    # Ensure we don't accidentally use the API mode
    env.pop("VERIFY_SPEC_USE_API", None)
    env.pop("AUTOBUILDR_API_URL", None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH, db_path],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


# ===========================================================================
# Step 1: Set AUTOBUILDR_USE_KERNEL=false or leave it unset
# ===========================================================================


class TestLegacyPathEnvironment:
    """Step 1: Verify that AUTOBUILDR_USE_KERNEL=false is the legacy path."""

    def test_kernel_disabled_when_env_false(self):
        """AUTOBUILDR_USE_KERNEL=false means kernel is disabled (legacy path)."""
        from api.migration_flag import parse_use_kernel_value

        assert parse_use_kernel_value("false") is False

    def test_kernel_disabled_when_env_unset(self):
        """AUTOBUILDR_USE_KERNEL unset means kernel is disabled (legacy path)."""
        from api.migration_flag import parse_use_kernel_value

        assert parse_use_kernel_value(None) is False

    def test_kernel_disabled_when_env_zero(self):
        """AUTOBUILDR_USE_KERNEL=0 means kernel is disabled (legacy path)."""
        from api.migration_flag import parse_use_kernel_value

        assert parse_use_kernel_value("0") is False

    def test_legacy_path_does_not_populate_spec_tables(self):
        """The legacy execution path does not create agent_specs/runs/events rows."""
        from api.migration_flag import ExecutionPath, execute_feature_legacy

        # Create a minimal mock feature object
        class MockFeature:
            id = 1
            name = "test"

        class MockDb:
            pass

        result = execute_feature_legacy(MockFeature(), MockDb())
        # Legacy path returns result but never writes to spec tables
        assert result.execution_path == ExecutionPath.LEGACY
        assert result.run_id is None  # No run created
        assert result.spec_id is None  # No spec created


# ===========================================================================
# Step 2: Run a build through the orchestrator (simulated legacy path)
# ===========================================================================


class TestLegacyBuildSimulation:
    """Step 2: Simulate a build via the legacy path (empty spec tables)."""

    def test_legacy_db_has_empty_spec_tables(self, tmp_path):
        """After a legacy build, spec tables exist but are empty."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)

        conn = sqlite3.connect(db)
        specs = conn.execute("SELECT COUNT(*) FROM agent_specs").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0]
        conn.close()

        assert specs == 0, "Legacy path should not populate agent_specs"
        assert runs == 0, "Legacy path should not populate agent_runs"
        assert events == 0, "Legacy path should not populate agent_events"

    def test_kernel_db_has_populated_spec_tables(self, tmp_path):
        """After a kernel build, spec tables have rows (contrast test)."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)

        conn = sqlite3.connect(db)
        specs = conn.execute("SELECT COUNT(*) FROM agent_specs").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        events = conn.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0]
        conn.close()

        assert specs > 0, "Kernel path should populate agent_specs"
        assert runs > 0, "Kernel path should populate agent_runs"
        assert events > 0, "Kernel path should populate agent_events"


# ===========================================================================
# Step 3: Run make verify-spec-path
# ===========================================================================


class TestRunVerifySpecPath:
    """Step 3: Run the verify-spec-path script on a legacy-path database."""

    def test_script_runs_without_crash(self, tmp_path):
        """verify_spec_path.py executes without Python errors."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        # Should exit 1 (failure), not crash with a traceback
        assert "Traceback" not in stderr, f"Script crashed: {stderr}"

    def test_script_runs_with_kernel_false(self, tmp_path):
        """Script works when AUTOBUILDR_USE_KERNEL=false is explicitly set."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "false"}
        )
        assert "Traceback" not in stderr
        # Should fail because spec tables are empty
        assert code != 0

    def test_script_runs_with_kernel_unset(self, tmp_path):
        """Script works when AUTOBUILDR_USE_KERNEL is not set."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        env = os.environ.copy()
        env.pop("AUTOBUILDR_USE_KERNEL", None)
        env.pop("VERIFY_SPEC_USE_API", None)
        env.pop("AUTOBUILDR_API_URL", None)
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, db],
            capture_output=True,
            text=True,
            env=env,
        )
        assert "Traceback" not in result.stderr
        assert result.returncode != 0


# ===========================================================================
# Step 4: Confirm it exits non-zero
# ===========================================================================


class TestExitNonZero:
    """Step 4: verify-spec-path must exit non-zero when legacy path was used."""

    def test_legacy_path_empty_tables_exit_nonzero(self, tmp_path):
        """All spec tables empty → exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert code != 0, (
            f"Expected non-zero exit when legacy path was used (empty spec tables). "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

    def test_legacy_path_exit_code_is_one(self, tmp_path):
        """Specifically exits with code 1 (not some other non-zero code)."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 1, (
            f"Expected exit code 1, got {code}.\nstdout:\n{stdout}"
        )

    def test_kernel_false_exit_nonzero(self, tmp_path):
        """AUTOBUILDR_USE_KERNEL=false → empty tables → exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "false"}
        )
        assert code == 1

    def test_kernel_unset_exit_nonzero(self, tmp_path):
        """AUTOBUILDR_USE_KERNEL unset → empty tables → exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        # Make sure AUTOBUILDR_USE_KERNEL is not in environment
        env = os.environ.copy()
        env.pop("AUTOBUILDR_USE_KERNEL", None)
        env.pop("VERIFY_SPEC_USE_API", None)
        env.pop("AUTOBUILDR_API_URL", None)
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, db],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 1

    def test_contrast_kernel_path_exits_zero(self, tmp_path):
        """Contrast: kernel path (populated tables) exits zero."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 0, (
            f"Expected exit code 0 when kernel path was used (tables populated). "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

    def test_no_db_file_exit_nonzero(self, tmp_path):
        """No database file at all → exit non-zero."""
        db = str(tmp_path / "nonexistent.db")
        code, stdout, stderr = _run_verify_script(db)
        assert code != 0


# ===========================================================================
# Step 5: Confirm the error message
# ===========================================================================


class TestErrorMessage:
    """Step 5: Error message must state 'Spec path not executed; legacy path likely used.'"""

    def test_error_message_exact_text(self, tmp_path):
        """Error message contains the exact required text."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 1
        assert "Spec path not executed; legacy path likely used." in stdout, (
            f"Expected error message 'Spec path not executed; legacy path likely used.' "
            f"in stdout.\nActual stdout:\n{stdout}"
        )

    def test_error_message_with_kernel_false(self, tmp_path):
        """Error message present when AUTOBUILDR_USE_KERNEL=false."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "false"}
        )
        assert "Spec path not executed; legacy path likely used." in stdout

    def test_error_message_with_kernel_unset(self, tmp_path):
        """Error message present when AUTOBUILDR_USE_KERNEL is unset."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        env = os.environ.copy()
        env.pop("AUTOBUILDR_USE_KERNEL", None)
        env.pop("VERIFY_SPEC_USE_API", None)
        env.pop("AUTOBUILDR_API_URL", None)
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, db],
            capture_output=True,
            text=True,
            env=env,
        )
        assert "Spec path not executed; legacy path likely used." in result.stdout

    def test_error_message_prefixed_with_fail(self, tmp_path):
        """Error message is prefixed with 'FAIL:'."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert "FAIL:" in stdout
        assert "FAIL: Spec path not executed; legacy path likely used." in stdout

    def test_empty_tables_shown_in_output(self, tmp_path):
        """Output shows which tables are EMPTY when legacy path was used."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert "[EMPTY]" in stdout
        assert "agent_specs: 0" in stdout
        assert "agent_runs: 0" in stdout
        assert "agent_events: 0" in stdout

    def test_no_pass_message_on_legacy_path(self, tmp_path):
        """PASS message should NOT appear when legacy path fails verification."""
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert "PASS:" not in stdout

    def test_no_db_shows_error_message(self, tmp_path):
        """Missing DB also shows the legacy path error message."""
        db = str(tmp_path / "nonexistent.db")
        code, stdout, stderr = _run_verify_script(db)
        assert "Spec path not executed; legacy path likely used." in stdout


# ===========================================================================
# Integration: Full legacy path scenario
# ===========================================================================


class TestFullLegacyScenario:
    """Full integration test: simulate the complete legacy path scenario."""

    def test_full_legacy_scenario_kernel_false(self, tmp_path):
        """Complete scenario: AUTOBUILDR_USE_KERNEL=false → build → verify → FAIL.

        Simulates the full test described in the feature steps:
        1. Set AUTOBUILDR_USE_KERNEL=false
        2. Run a build through the orchestrator (simulated: empty spec tables)
        3. Run make verify-spec-path (via script directly)
        4. Confirm exit non-zero
        5. Confirm error message
        """
        # Step 1: Environment is set to false
        env_overrides = {"AUTOBUILDR_USE_KERNEL": "false"}

        # Step 2: Simulate build via legacy path (creates DB with empty spec tables)
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)

        # Step 3: Run verify-spec-path
        code, stdout, stderr = _run_verify_script(db, env_overrides=env_overrides)

        # Step 4: Confirm exit non-zero
        assert code != 0, f"Expected non-zero exit. Got {code}.\n{stdout}"
        assert code == 1, f"Expected exit code 1. Got {code}."

        # Step 5: Confirm error message
        assert "Spec path not executed; legacy path likely used." in stdout, (
            f"Missing expected error message in output:\n{stdout}"
        )

    def test_full_legacy_scenario_kernel_unset(self, tmp_path):
        """Complete scenario: AUTOBUILDR_USE_KERNEL unset → build → verify → FAIL."""
        # Step 1: Environment variable is not set
        env = os.environ.copy()
        env.pop("AUTOBUILDR_USE_KERNEL", None)
        env.pop("VERIFY_SPEC_USE_API", None)
        env.pop("AUTOBUILDR_API_URL", None)

        # Step 2: Simulate build via legacy path
        db = str(tmp_path / "features.db")
        _create_legacy_db(db)

        # Step 3: Run verify-spec-path
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, db],
            capture_output=True,
            text=True,
            env=env,
        )

        # Step 4: Confirm exit non-zero
        assert result.returncode == 1

        # Step 5: Confirm error message
        assert "Spec path not executed; legacy path likely used." in result.stdout

    def test_contrast_kernel_path_passes(self, tmp_path):
        """Contrast: when kernel path IS used, verify-spec-path succeeds."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, stderr = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "true"}
        )
        assert code == 0, f"Expected success for kernel path. Got {code}.\n{stdout}"
        assert "PASS" in stdout
        assert "Spec path not executed" not in stdout
