"""Tests for Feature #167: verify-spec-path queries spec tables via API or SQLite.

Verifies that the verify_spec_path.py script:
1. Implements query mechanism (prefer API, fallback SQLite)
2. Checks agent_specs count > 0
3. Checks agent_runs count > 0
4. Checks agent_events count > 0
5. Optionally checks artifacts count > 0
6. Outputs the counts for debugging/visibility
"""

import http.server
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "verify_spec_path.py"
)

# Ensure the script module can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_db(path, specs=0, runs=0, events=0, artifacts=0):
    """Create a test database with the given row counts."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS agent_specs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_events (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY)")
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


def _run_script(db_path, env_overrides=None):
    """Run verify_spec_path.py and return (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH, db_path],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _run_script_no_args(env_overrides=None):
    """Run verify_spec_path.py without DB path argument."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, SCRIPT_PATH],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Mock HTTP server for API tests
# ---------------------------------------------------------------------------


class MockAPIHandler(http.server.BaseHTTPRequestHandler):
    """Simple mock API server that returns configurable JSON responses."""

    # Class-level configuration
    specs_response = None
    runs_response = None

    def do_GET(self):
        if "/agent-specs" in self.path and self.specs_response is not None:
            self._json_response(self.specs_response)
        elif "/agent-runs" in self.path and self.runs_response is not None:
            self._json_response(self.runs_response)
        else:
            self.send_error(404)

    def _json_response(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress request logs during tests
        pass


@pytest.fixture()
def mock_api_server():
    """Start a mock API server on an ephemeral port."""
    server = http.server.HTTPServer(("127.0.0.1", 0), MockAPIHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, port
    server.shutdown()


# ===========================================================================
# Step 1: Implement the query mechanism (prefer API)
# ===========================================================================


class TestQueryMechanism:
    """Step 1: The script queries spec tables preferring API, falling back to SQLite."""

    def test_script_imports_urllib(self):
        """Script uses urllib for API queries (no external dependencies)."""
        with open(SCRIPT_PATH) as f:
            content = f.read()
        assert "urllib.request" in content

    def test_script_imports_sqlite3(self):
        """Script uses sqlite3 for fallback queries."""
        with open(SCRIPT_PATH) as f:
            content = f.read()
        assert "sqlite3" in content

    def test_script_has_api_query_functions(self):
        """Script defines API query functions."""
        with open(SCRIPT_PATH) as f:
            content = f.read()
        assert "query_agent_specs_count_api" in content
        assert "query_agent_runs_count_api" in content
        assert "query_counts_via_api" in content

    def test_script_has_sqlite_fallback_functions(self):
        """Script defines SQLite fallback functions."""
        with open(SCRIPT_PATH) as f:
            content = f.read()
        assert "get_table_count_sqlite" in content
        assert "query_all_counts_sqlite" in content

    def test_script_has_gather_counts_with_api_flag(self):
        """gather_counts accepts use_api parameter."""
        with open(SCRIPT_PATH) as f:
            content = f.read()
        assert "def gather_counts(" in content
        assert "use_api" in content

    def test_sqlite_fallback_when_explicit_db_path(self, tmp_path):
        """When a DB path is given as CLI arg, uses SQLite (not API)."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=3, runs=2, events=7, artifacts=1)
        code, stdout, _ = _run_script(db)
        assert code == 0
        # With explicit DB arg, all queries should be via sqlite
        assert "(via sqlite)" in stdout
        assert "agent_specs: 3" in stdout
        assert "agent_runs: 2" in stdout
        assert "agent_events: 7" in stdout

    def test_api_queries_used_when_no_explicit_target(self, mock_api_server, tmp_path):
        """When no explicit DB target, API is attempted first."""
        server, port = mock_api_server
        MockAPIHandler.specs_response = {"specs": [], "total": 5, "offset": 0, "limit": 1}
        MockAPIHandler.runs_response = {"runs": [], "total": 3, "offset": 0, "limit": 1}

        # Create a DB with events (API doesn't cover events)
        db_dir = str(tmp_path / "project")
        os.makedirs(db_dir, exist_ok=True)
        db = os.path.join(db_dir, "features.db")
        _create_db(db, specs=0, runs=0, events=10, artifacts=2)

        env = {
            "AUTOBUILDR_API_URL": f"http://127.0.0.1:{port}",
            "AUTOBUILDR_TEST_PROJECT_NAME": "test-project",
            "VERIFY_SPEC_USE_API": "1",
        }
        code, stdout, _ = _run_script(db, env_overrides=env)
        # specs and runs from API
        assert "agent_specs: 5 rows [OK] (via api)" in stdout
        assert "agent_runs: 3 rows [OK] (via api)" in stdout
        # events from sqlite (no API endpoint)
        assert "agent_events: 10 rows [OK] (via sqlite)" in stdout

    def test_api_fallback_to_sqlite_on_error(self, tmp_path):
        """When API is unreachable, falls back gracefully to SQLite."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=2, runs=2, events=2)

        env = {
            "AUTOBUILDR_API_URL": "http://127.0.0.1:1",  # Unreachable port
            "VERIFY_SPEC_USE_API": "1",
        }
        code, stdout, _ = _run_script(db, env_overrides=env)
        # Should still succeed using SQLite fallback
        assert code == 0
        # All via sqlite since API failed
        assert "(via sqlite)" in stdout


# ===========================================================================
# Step 2: Check agent_specs count > 0
# ===========================================================================


class TestAgentSpecsCount:
    """Step 2: Script checks agent_specs count > 0."""

    def test_agent_specs_count_shown(self, tmp_path):
        """Output includes agent_specs row count."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=5, runs=1, events=1)
        _, stdout, _ = _run_script(db)
        assert "agent_specs: 5" in stdout

    def test_agent_specs_zero_causes_failure(self, tmp_path):
        """agent_specs count of 0 causes exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=1, events=1)
        code, stdout, _ = _run_script(db)
        assert code != 0
        assert "agent_specs: 0" in stdout
        assert "[EMPTY]" in stdout

    def test_agent_specs_nonzero_shows_ok(self, tmp_path):
        """agent_specs count > 0 shows [OK]."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=3, runs=1, events=1)
        _, stdout, _ = _run_script(db)
        assert "agent_specs: 3 rows [OK]" in stdout


# ===========================================================================
# Step 3: Check agent_runs count > 0
# ===========================================================================


class TestAgentRunsCount:
    """Step 3: Script checks agent_runs count > 0."""

    def test_agent_runs_count_shown(self, tmp_path):
        """Output includes agent_runs row count."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=8, events=1)
        _, stdout, _ = _run_script(db)
        assert "agent_runs: 8" in stdout

    def test_agent_runs_zero_causes_failure(self, tmp_path):
        """agent_runs count of 0 causes exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=0, events=1)
        code, stdout, _ = _run_script(db)
        assert code != 0
        assert "agent_runs: 0" in stdout
        assert "[EMPTY]" in stdout

    def test_agent_runs_nonzero_shows_ok(self, tmp_path):
        """agent_runs count > 0 shows [OK]."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=4, events=1)
        _, stdout, _ = _run_script(db)
        assert "agent_runs: 4 rows [OK]" in stdout


# ===========================================================================
# Step 4: Check agent_events count > 0
# ===========================================================================


class TestAgentEventsCount:
    """Step 4: Script checks agent_events count > 0."""

    def test_agent_events_count_shown(self, tmp_path):
        """Output includes agent_events row count."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=12)
        _, stdout, _ = _run_script(db)
        assert "agent_events: 12" in stdout

    def test_agent_events_zero_causes_failure(self, tmp_path):
        """agent_events count of 0 causes exit non-zero."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=0)
        code, stdout, _ = _run_script(db)
        assert code != 0
        assert "agent_events: 0" in stdout
        assert "[EMPTY]" in stdout

    def test_agent_events_nonzero_shows_ok(self, tmp_path):
        """agent_events count > 0 shows [OK]."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=6)
        _, stdout, _ = _run_script(db)
        assert "agent_events: 6 rows [OK]" in stdout


# ===========================================================================
# Step 5: Optionally check artifacts count > 0
# ===========================================================================


class TestArtifactsOptionalCheck:
    """Step 5: Script optionally checks artifacts count >= 0 without failing."""

    def test_artifacts_shown_in_output(self, tmp_path):
        """artifacts count is shown in output."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1, artifacts=5)
        _, stdout, _ = _run_script(db)
        assert "artifacts:" in stdout
        assert "5 rows" in stdout

    def test_artifacts_marked_optional(self, tmp_path):
        """artifacts line is marked as [optional]."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1, artifacts=0)
        _, stdout, _ = _run_script(db)
        assert "[optional]" in stdout

    def test_artifacts_zero_does_not_cause_failure(self, tmp_path):
        """artifacts count of 0 does NOT cause exit non-zero (it's optional)."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1, artifacts=0)
        code, stdout, _ = _run_script(db)
        assert code == 0, f"Expected exit 0 (artifacts are optional), got {code}"
        assert "PASS" in stdout

    def test_artifacts_nonzero_shows_ok(self, tmp_path):
        """artifacts count > 0 shows [OK]."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1, artifacts=3)
        _, stdout, _ = _run_script(db)
        assert "artifacts: 3 rows [OK]" in stdout

    def test_artifacts_zero_shows_empty(self, tmp_path):
        """artifacts count of 0 shows [EMPTY] but does not fail."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1, artifacts=0)
        code, stdout, _ = _run_script(db)
        assert code == 0
        assert "artifacts: 0 rows [EMPTY]" in stdout


# ===========================================================================
# Step 6: Output the counts for debugging/visibility
# ===========================================================================


class TestCountOutput:
    """Step 6: Script outputs counts for debugging/visibility."""

    def test_header_shown(self, tmp_path):
        """Output starts with verification header."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1)
        _, stdout, _ = _run_script(db)
        assert "=== Spec-Path Verification ===" in stdout

    def test_all_four_tables_shown(self, tmp_path):
        """Output shows all four tables: agent_specs, agent_runs, agent_events, artifacts."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=2, runs=3, events=4, artifacts=1)
        _, stdout, _ = _run_script(db)
        assert "agent_specs:" in stdout
        assert "agent_runs:" in stdout
        assert "agent_events:" in stdout
        assert "artifacts:" in stdout

    def test_counts_are_accurate(self, tmp_path):
        """Displayed counts match what's in the database."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=7, runs=11, events=23, artifacts=4)
        _, stdout, _ = _run_script(db)
        assert "agent_specs: 7 rows" in stdout
        assert "agent_runs: 11 rows" in stdout
        assert "agent_events: 23 rows" in stdout
        assert "artifacts: 4 rows" in stdout

    def test_query_method_shown(self, tmp_path):
        """Each line shows the query method used (api or sqlite)."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1)
        _, stdout, _ = _run_script(db)
        # With explicit DB arg, all should be "via sqlite"
        for table in ["agent_specs", "agent_runs", "agent_events", "artifacts"]:
            assert f"(via " in stdout

    def test_status_labels_shown(self, tmp_path):
        """Each table shows [OK] or [EMPTY] status."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=0, events=1)
        _, stdout, _ = _run_script(db)
        assert "[OK]" in stdout
        assert "[EMPTY]" in stdout

    def test_pass_message_on_success(self, tmp_path):
        """PASS message displayed when all required tables have rows."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=1, runs=1, events=1)
        code, stdout, _ = _run_script(db)
        assert code == 0
        assert "PASS: Spec-driven path verified" in stdout

    def test_fail_message_on_failure(self, tmp_path):
        """FAIL message displayed when any required table is empty."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=0, events=0)
        code, stdout, _ = _run_script(db)
        assert code == 1
        assert "FAIL: Spec path not executed; legacy path likely used." in stdout


# ===========================================================================
# Integration: API + SQLite hybrid test
# ===========================================================================


class TestAPIWithSQLiteFallback:
    """Integration test: API for specs/runs, SQLite for events/artifacts."""

    def test_hybrid_mode(self, mock_api_server, tmp_path):
        """API serves specs/runs; SQLite serves events/artifacts."""
        server, port = mock_api_server
        MockAPIHandler.specs_response = {"specs": [], "total": 10, "offset": 0, "limit": 1}
        MockAPIHandler.runs_response = {"runs": [], "total": 7, "offset": 0, "limit": 1}

        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=0, events=15, artifacts=3)

        env = {
            "AUTOBUILDR_API_URL": f"http://127.0.0.1:{port}",
            "AUTOBUILDR_TEST_PROJECT_NAME": "test-project",
            "VERIFY_SPEC_USE_API": "1",
        }
        code, stdout, _ = _run_script(db, env_overrides=env)
        assert code == 0
        assert "agent_specs: 10 rows [OK] (via api)" in stdout
        assert "agent_runs: 7 rows [OK] (via api)" in stdout
        assert "agent_events: 15 rows [OK] (via sqlite)" in stdout
        assert "artifacts: 3 rows [OK] (via sqlite)" in stdout
        assert "PASS" in stdout

    def test_api_returns_zero_causes_failure(self, mock_api_server, tmp_path):
        """If API says specs=0, script should still fail."""
        server, port = mock_api_server
        MockAPIHandler.specs_response = {"specs": [], "total": 0, "offset": 0, "limit": 1}
        MockAPIHandler.runs_response = {"runs": [], "total": 5, "offset": 0, "limit": 1}

        db = str(tmp_path / "features.db")
        _create_db(db, specs=0, runs=0, events=10, artifacts=0)

        env = {
            "AUTOBUILDR_API_URL": f"http://127.0.0.1:{port}",
            "AUTOBUILDR_TEST_PROJECT_NAME": "test-project",
            "VERIFY_SPEC_USE_API": "1",
        }
        code, stdout, _ = _run_script(db, env_overrides=env)
        assert code == 1
        assert "agent_specs: 0 rows [EMPTY] (via api)" in stdout

    def test_api_unreachable_full_sqlite_fallback(self, tmp_path):
        """When API is completely unreachable, all queries fall back to SQLite."""
        db = str(tmp_path / "features.db")
        _create_db(db, specs=4, runs=3, events=8, artifacts=2)

        env = {
            "AUTOBUILDR_API_URL": "http://127.0.0.1:1",  # Unreachable
            "VERIFY_SPEC_USE_API": "1",
        }
        code, stdout, _ = _run_script(db, env_overrides=env)
        assert code == 0
        assert "(via sqlite)" in stdout
        assert "agent_specs: 4 rows [OK]" in stdout
        assert "agent_runs: 3 rows [OK]" in stdout
        assert "agent_events: 8 rows [OK]" in stdout
        assert "PASS" in stdout
