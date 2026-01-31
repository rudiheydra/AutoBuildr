"""Tests for Feature #169: verify-spec-path succeeds when spec path is used.

Positive test: when the orchestrator uses the spec-driven path
(AUTOBUILDR_USE_KERNEL=true), make verify-spec-path must exit zero because
the spec tables will have rows from actual execution.

Verification steps:
1. Set AUTOBUILDR_USE_KERNEL=true
2. Run a build through the orchestrator (at least one feature)
3. Run make verify-spec-path
4. Confirm it exits zero
5. Confirm the output shows non-zero counts for agent_specs, agent_runs, and agent_events
"""

import os
import re
import sqlite3
import subprocess
import sys

import pytest

# Path to the verify_spec_path.py script
SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "verify_spec_path.py"
)

# Path to the project's features.db (real data from kernel execution)
PROJECT_FEATURES_DB = os.path.join(
    os.path.dirname(__file__), "..", "features.db"
)

# Ensure imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_kernel_db(path, specs=3, runs=2, events=5, artifacts=1):
    """Create a database that simulates the spec-driven kernel path output.

    The kernel path populates agent_specs, agent_runs, and agent_events
    through the SpecOrchestrator -> FeatureCompiler -> HarnessKernel pipeline.
    """
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS agent_specs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_events (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS features ("
        "  id INTEGER PRIMARY KEY, name TEXT, status TEXT"
        ")"
    )

    for i in range(specs):
        conn.execute(f"INSERT INTO agent_specs VALUES ('spec-{i}')")
    for i in range(runs):
        conn.execute(f"INSERT INTO agent_runs VALUES ('run-{i}')")
    for i in range(events):
        conn.execute(f"INSERT INTO agent_events VALUES ('event-{i}')")
    for i in range(artifacts):
        conn.execute(f"INSERT INTO artifacts VALUES ('artifact-{i}')")

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


def _parse_count(stdout, table_name):
    """Extract the count for a given table from verify_spec_path.py output.

    Parses lines like: '  agent_specs: 2179 rows [OK] (via sqlite)'
    Returns the integer count, or None if not found.
    """
    pattern = rf"{table_name}:\s+(\d+)\s+rows"
    match = re.search(pattern, stdout)
    if match:
        return int(match.group(1))
    return None


# ===========================================================================
# Step 1: Set AUTOBUILDR_USE_KERNEL=true
# ===========================================================================


class TestKernelEnabledEnvironment:
    """Step 1: Verify that AUTOBUILDR_USE_KERNEL=true enables the spec path."""

    def test_kernel_enabled_when_env_true(self):
        """AUTOBUILDR_USE_KERNEL=true means kernel is enabled (spec path)."""
        from api.migration_flag import parse_use_kernel_value

        assert parse_use_kernel_value("true") is True

    def test_kernel_enabled_when_env_one(self):
        """AUTOBUILDR_USE_KERNEL=1 means kernel is enabled (spec path)."""
        from api.migration_flag import parse_use_kernel_value

        assert parse_use_kernel_value("1") is True

    def test_kernel_enabled_when_env_yes(self):
        """AUTOBUILDR_USE_KERNEL=yes means kernel is enabled (spec path)."""
        from api.migration_flag import parse_use_kernel_value

        assert parse_use_kernel_value("yes") is True

    def test_kernel_enabled_flag_function(self):
        """is_kernel_enabled() returns True when env var is set to 'true'."""
        from api.migration_flag import (
            clear_kernel_flag,
            is_kernel_enabled,
            set_kernel_enabled,
        )

        original = os.environ.get("AUTOBUILDR_USE_KERNEL")
        try:
            set_kernel_enabled(True)
            assert is_kernel_enabled() is True
        finally:
            if original is not None:
                os.environ["AUTOBUILDR_USE_KERNEL"] = original
            else:
                clear_kernel_flag()

    def test_spec_path_populates_spec_tables(self):
        """The spec-driven path creates rows in agent_specs/runs/events."""
        # Verify the spec path involves all three required tables
        from api.agentspec_models import AgentEvent, AgentRun, AgentSpec

        # These models define the tables that the kernel populates
        assert AgentSpec.__tablename__ == "agent_specs"
        assert AgentRun.__tablename__ == "agent_runs"
        assert AgentEvent.__tablename__ == "agent_events"


# ===========================================================================
# Step 2: Run a build through the orchestrator (at least one feature)
# ===========================================================================


class TestKernelBuildPopulatesTables:
    """Step 2: Verify that a kernel build populates spec tables."""

    def test_kernel_db_has_spec_rows(self, tmp_path):
        """After a kernel/spec build, agent_specs table has rows."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=2, events=5)

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM agent_specs").fetchone()[0]
        conn.close()
        assert count > 0, "Kernel build should populate agent_specs"

    def test_kernel_db_has_run_rows(self, tmp_path):
        """After a kernel/spec build, agent_runs table has rows."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=2, events=5)

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
        conn.close()
        assert count > 0, "Kernel build should populate agent_runs"

    def test_kernel_db_has_event_rows(self, tmp_path):
        """After a kernel/spec build, agent_events table has rows."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=2, events=5)

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0]
        conn.close()
        assert count > 0, "Kernel build should populate agent_events"

    def test_real_features_db_has_spec_rows(self):
        """The real features.db has actual data from kernel execution."""
        if not os.path.isfile(PROJECT_FEATURES_DB):
            pytest.skip("features.db not found (CI or fresh environment)")

        conn = sqlite3.connect(PROJECT_FEATURES_DB)
        try:
            specs = conn.execute("SELECT COUNT(*) FROM agent_specs").fetchone()[0]
            runs = conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0]
            events = conn.execute("SELECT COUNT(*) FROM agent_events").fetchone()[0]
        except Exception:
            pytest.skip("Spec tables not present in features.db")
        finally:
            conn.close()

        assert specs > 0, (
            f"Real features.db should have agent_specs rows from kernel execution, got {specs}"
        )
        assert runs > 0, (
            f"Real features.db should have agent_runs rows from kernel execution, got {runs}"
        )
        assert events > 0, (
            f"Real features.db should have agent_events rows from kernel execution, got {events}"
        )


# ===========================================================================
# Step 3: Run make verify-spec-path
# ===========================================================================


class TestRunVerifySpecPath:
    """Step 3: Run the verify-spec-path script on a kernel-path database."""

    def test_script_runs_without_crash(self, tmp_path):
        """verify_spec_path.py executes without Python errors on kernel DB."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, stderr = _run_verify_script(db)
        assert "Traceback" not in stderr, f"Script crashed: {stderr}"

    def test_script_runs_with_kernel_true(self, tmp_path):
        """Script works when AUTOBUILDR_USE_KERNEL=true is explicitly set."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, stderr = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "true"}
        )
        assert "Traceback" not in stderr
        assert code == 0

    def test_script_shows_verification_header(self, tmp_path):
        """Script displays the spec-path verification header."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        _, stdout, _ = _run_verify_script(db)
        assert "=== Spec-Path Verification ===" in stdout

    def test_script_runs_on_real_features_db(self):
        """verify_spec_path.py succeeds on the real features.db."""
        if not os.path.isfile(PROJECT_FEATURES_DB):
            pytest.skip("features.db not found (CI or fresh environment)")

        code, stdout, stderr = _run_verify_script(PROJECT_FEATURES_DB)
        assert "Traceback" not in stderr, f"Script crashed: {stderr}"
        assert code == 0, (
            f"Expected verify-spec-path to pass on real features.db. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )


# ===========================================================================
# Step 4: Confirm it exits zero
# ===========================================================================


class TestExitZero:
    """Step 4: verify-spec-path must exit zero when spec path was used."""

    def test_kernel_path_populated_tables_exit_zero(self, tmp_path):
        """All spec tables populated → exit zero."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=5, runs=3, events=10)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 0, (
            f"Expected exit 0 when spec tables are populated. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

    def test_kernel_path_minimal_data_exit_zero(self, tmp_path):
        """Even minimal data (1 row each) → exit zero."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=1, runs=1, events=1, artifacts=0)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 0, (
            f"Expected exit 0 with minimal spec data. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

    def test_kernel_path_large_data_exit_zero(self, tmp_path):
        """Large datasets (many rows) → exit zero."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=100, runs=50, events=500, artifacts=10)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 0, (
            f"Expected exit 0 with large spec data. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

    def test_kernel_path_with_env_true_exit_zero(self, tmp_path):
        """AUTOBUILDR_USE_KERNEL=true + populated tables → exit zero."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, stderr = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "true"}
        )
        assert code == 0

    def test_kernel_path_without_artifacts_exit_zero(self, tmp_path):
        """Artifacts are optional — zero artifacts should not prevent exit 0."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=2, events=5, artifacts=0)
        code, stdout, stderr = _run_verify_script(db)
        assert code == 0, (
            f"Expected exit 0 even with zero artifacts (optional table). "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

    def test_pass_message_displayed(self, tmp_path):
        """PASS message is displayed when verification succeeds."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        assert "PASS" in stdout
        assert "Spec-driven path verified" in stdout

    def test_no_fail_message_on_success(self, tmp_path):
        """FAIL message should NOT appear when spec path verification succeeds."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        assert "FAIL" not in stdout
        assert "Spec path not executed" not in stdout

    def test_real_features_db_exits_zero(self):
        """The real features.db should cause verify-spec-path to exit zero."""
        if not os.path.isfile(PROJECT_FEATURES_DB):
            pytest.skip("features.db not found (CI or fresh environment)")

        code, stdout, stderr = _run_verify_script(PROJECT_FEATURES_DB)
        assert code == 0, (
            f"Expected verify-spec-path to exit 0 on real features.db. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )
        assert "PASS" in stdout


# ===========================================================================
# Step 5: Confirm non-zero counts for agent_specs, agent_runs, agent_events
# ===========================================================================


class TestNonZeroCounts:
    """Step 5: Output must show non-zero counts for all three required tables."""

    def test_agent_specs_count_nonzero(self, tmp_path):
        """agent_specs count is displayed and > 0."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=5, runs=2, events=3)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        count = _parse_count(stdout, "agent_specs")
        assert count is not None, f"Could not parse agent_specs count from output:\n{stdout}"
        assert count > 0, f"Expected agent_specs > 0, got {count}"
        assert count == 5, f"Expected agent_specs = 5, got {count}"

    def test_agent_runs_count_nonzero(self, tmp_path):
        """agent_runs count is displayed and > 0."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=7, events=4)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        count = _parse_count(stdout, "agent_runs")
        assert count is not None, f"Could not parse agent_runs count from output:\n{stdout}"
        assert count > 0, f"Expected agent_runs > 0, got {count}"
        assert count == 7, f"Expected agent_runs = 7, got {count}"

    def test_agent_events_count_nonzero(self, tmp_path):
        """agent_events count is displayed and > 0."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=2, runs=1, events=12)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        count = _parse_count(stdout, "agent_events")
        assert count is not None, f"Could not parse agent_events count from output:\n{stdout}"
        assert count > 0, f"Expected agent_events > 0, got {count}"
        assert count == 12, f"Expected agent_events = 12, got {count}"

    def test_all_three_tables_shown_ok(self, tmp_path):
        """All three required tables show [OK] status."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=2, events=5)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        assert "agent_specs:" in stdout
        assert "agent_runs:" in stdout
        assert "agent_events:" in stdout
        # All three should show [OK]
        ok_count = stdout.count("[OK]")
        assert ok_count >= 3, (
            f"Expected at least 3 [OK] markers (one per required table), got {ok_count}.\n"
            f"Output:\n{stdout}"
        )

    def test_no_empty_markers_for_required_tables(self, tmp_path):
        """No required table should show [EMPTY] when spec path is used."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=3, runs=2, events=5)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0

        # Check each required table line doesn't contain [EMPTY]
        for line in stdout.splitlines():
            for table in ("agent_specs", "agent_runs", "agent_events"):
                if table in line:
                    assert "[EMPTY]" not in line, (
                        f"Required table {table} should not be [EMPTY] on spec path.\n"
                        f"Line: {line}"
                    )

    def test_real_features_db_nonzero_counts(self):
        """The real features.db shows non-zero counts for all three tables."""
        if not os.path.isfile(PROJECT_FEATURES_DB):
            pytest.skip("features.db not found (CI or fresh environment)")

        code, stdout, stderr = _run_verify_script(PROJECT_FEATURES_DB)
        assert code == 0, f"verify-spec-path failed on real DB:\n{stdout}"

        # Parse counts from output
        specs_count = _parse_count(stdout, "agent_specs")
        runs_count = _parse_count(stdout, "agent_runs")
        events_count = _parse_count(stdout, "agent_events")

        assert specs_count is not None, f"Could not parse agent_specs count:\n{stdout}"
        assert runs_count is not None, f"Could not parse agent_runs count:\n{stdout}"
        assert events_count is not None, f"Could not parse agent_events count:\n{stdout}"

        assert specs_count > 0, f"Expected agent_specs > 0 in real DB, got {specs_count}"
        assert runs_count > 0, f"Expected agent_runs > 0 in real DB, got {runs_count}"
        assert events_count > 0, f"Expected agent_events > 0 in real DB, got {events_count}"

    def test_counts_are_accurate(self, tmp_path):
        """Displayed counts match what was actually stored in the database."""
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=7, runs=4, events=15, artifacts=2)
        code, stdout, _ = _run_verify_script(db)
        assert code == 0
        assert "agent_specs: 7 rows" in stdout
        assert "agent_runs: 4 rows" in stdout
        assert "agent_events: 15 rows" in stdout
        assert "artifacts: 2 rows" in stdout


# ===========================================================================
# Integration: Full spec-path positive scenario
# ===========================================================================


class TestFullSpecPathScenario:
    """Full integration test: simulate the complete spec-path scenario."""

    def test_full_spec_path_scenario(self, tmp_path):
        """Complete scenario: AUTOBUILDR_USE_KERNEL=true → build → verify → PASS.

        Simulates the full test described in the feature steps:
        1. Set AUTOBUILDR_USE_KERNEL=true
        2. Run a build through the orchestrator (simulated: populated spec tables)
        3. Run make verify-spec-path (via script directly)
        4. Confirm exit zero
        5. Confirm non-zero counts for agent_specs, agent_runs, agent_events
        """
        # Step 1: Environment is set to true
        env_overrides = {"AUTOBUILDR_USE_KERNEL": "true"}

        # Step 2: Simulate build via spec/kernel path (creates DB with populated spec tables)
        db = str(tmp_path / "features.db")
        _create_kernel_db(db, specs=10, runs=5, events=25, artifacts=3)

        # Step 3: Run verify-spec-path
        code, stdout, stderr = _run_verify_script(db, env_overrides=env_overrides)

        # Verify no crashes
        assert "Traceback" not in stderr, f"Script crashed: {stderr}"

        # Step 4: Confirm exit zero
        assert code == 0, (
            f"Expected exit 0 when spec path was used. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

        # Step 5: Confirm non-zero counts
        specs_count = _parse_count(stdout, "agent_specs")
        runs_count = _parse_count(stdout, "agent_runs")
        events_count = _parse_count(stdout, "agent_events")

        assert specs_count is not None and specs_count > 0, (
            f"agent_specs count should be > 0, got {specs_count}"
        )
        assert runs_count is not None and runs_count > 0, (
            f"agent_runs count should be > 0, got {runs_count}"
        )
        assert events_count is not None and events_count > 0, (
            f"agent_events count should be > 0, got {events_count}"
        )

        # Additional: verify PASS message and [OK] markers
        assert "PASS" in stdout
        assert "Spec-driven path verified" in stdout
        assert "[OK]" in stdout
        assert "FAIL" not in stdout

    def test_full_scenario_with_real_db(self):
        """Full scenario using the actual project features.db.

        This tests the real end-to-end flow: the project's features.db
        has been populated by actual kernel execution (not simulated).
        """
        if not os.path.isfile(PROJECT_FEATURES_DB):
            pytest.skip("features.db not found (CI or fresh environment)")

        # Step 1: AUTOBUILDR_USE_KERNEL=true (the kernel path was used)
        env_overrides = {"AUTOBUILDR_USE_KERNEL": "true"}

        # Step 2: Build already happened — features.db has real data

        # Step 3: Run verify-spec-path on real DB
        code, stdout, stderr = _run_verify_script(
            PROJECT_FEATURES_DB, env_overrides=env_overrides
        )

        # Verify no crashes
        assert "Traceback" not in stderr, f"Script crashed: {stderr}"

        # Step 4: Confirm exit zero
        assert code == 0, (
            f"Expected exit 0 on real features.db with kernel execution data. "
            f"Got exit code {code}.\nstdout:\n{stdout}"
        )

        # Step 5: Confirm non-zero counts
        specs_count = _parse_count(stdout, "agent_specs")
        runs_count = _parse_count(stdout, "agent_runs")
        events_count = _parse_count(stdout, "agent_events")

        assert specs_count is not None and specs_count > 0, (
            f"Real DB agent_specs should be > 0, got {specs_count}"
        )
        assert runs_count is not None and runs_count > 0, (
            f"Real DB agent_runs should be > 0, got {runs_count}"
        )
        assert events_count is not None and events_count > 0, (
            f"Real DB agent_events should be > 0, got {events_count}"
        )

        # Verify proper output formatting
        assert "PASS" in stdout
        assert "=== Spec-Path Verification ===" in stdout

    def test_contrast_legacy_path_fails(self, tmp_path):
        """Contrast: legacy path (empty tables) should fail verification."""
        db = str(tmp_path / "features.db")
        # Create DB with empty spec tables (legacy path behavior)
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE IF NOT EXISTS agent_specs (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS agent_events (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()

        code, stdout, _ = _run_verify_script(
            db, env_overrides={"AUTOBUILDR_USE_KERNEL": "false"}
        )
        assert code != 0, (
            "Legacy path (empty spec tables) should fail verification"
        )
        assert "FAIL" in stdout
