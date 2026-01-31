#!/usr/bin/env python3
"""Verify that the spec-driven path was executed.

Checks that agent_specs, agent_runs, and agent_events tables all have rows.
Optionally checks the artifacts table as well.

Preferred method: query via API endpoints (GET /api/agent-specs, GET /api/agent-runs).
Fallback: direct SQLite queries (for events/artifacts, or when API is unreachable).

When a DB path is passed as a command-line argument, the script uses SQLite directly
(since the explicit path indicates a specific database is targeted). API mode is used
when the script is invoked without arguments (the container/production scenario).

Exits non-zero with a clear message if any required table is empty (indicating
the legacy path was likely used instead of the spec-driven path).

Usage:
    python3 scripts/verify_spec_path.py [DB_PATH]

    DB_PATH defaults to $AUTOBUILDR_TEST_PROJECT_PATH/features.db or ./features.db

Environment variables:
    AUTOBUILDR_TEST_PROJECT_PATH  - Project directory (default: ".")
    AUTOBUILDR_TEST_PROJECT_NAME  - Project name for API queries (default: "repo-concierge")
    AUTOBUILDR_API_URL            - Base URL of the API server (default: "http://localhost:8888")
    VERIFY_SPEC_USE_API           - Set to "1" to force API mode even with explicit DB path
"""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_URL = "http://localhost:8888"
DEFAULT_PROJECT_NAME = "repo-concierge"
API_TIMEOUT_SECONDS = 5

# Required tables: must all have count > 0 for verification to pass
REQUIRED_TABLES = ["agent_specs", "agent_runs", "agent_events"]

# Optional tables: checked and reported but don't cause failure
OPTIONAL_TABLES = ["artifacts"]


# ---------------------------------------------------------------------------
# Database path resolution
# ---------------------------------------------------------------------------


def get_db_path():
    """Determine the database path from args or environment."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    project_path = os.environ.get("AUTOBUILDR_TEST_PROJECT_PATH", ".")
    return os.path.join(project_path, "features.db")


def _explicit_db_target():
    """Return True when a specific DB target was requested.

    This is True when either:
    - A DB path was passed as a CLI argument, OR
    - AUTOBUILDR_TEST_PROJECT_PATH is set (pointing to a specific project).

    In these cases the caller is targeting a specific database, so SQLite
    should be preferred over the API (which might point to a different DB).
    """
    if len(sys.argv) > 1:
        return True
    if os.environ.get("AUTOBUILDR_TEST_PROJECT_PATH"):
        return True
    return False


# ---------------------------------------------------------------------------
# SQLite fallback
# ---------------------------------------------------------------------------


def get_table_count_sqlite(conn, table_name):
    """Get the row count for a table via SQLite, returning 0 on any error."""
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    except Exception:
        return 0


def query_all_counts_sqlite(db_path):
    """Query all table counts via direct SQLite.

    Returns:
        dict mapping table name to row count (0 if table missing or error).
    """
    conn = sqlite3.connect(db_path)
    counts = {}
    for table in REQUIRED_TABLES + OPTIONAL_TABLES:
        counts[table] = get_table_count_sqlite(conn, table)
    conn.close()
    return counts


# ---------------------------------------------------------------------------
# API queries (preferred)
# ---------------------------------------------------------------------------


def _api_get_json(url):
    """Fetch a JSON response from the given URL.

    Returns:
        Parsed JSON as a dict, or None on any error.
    """
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        return None


def query_agent_specs_count_api(api_url, project_name):
    """Query agent_specs count via GET /api/projects/{project}/agent-specs?limit=1.

    The response includes a ``total`` field with the full count.

    Returns:
        int count, or None if API is unreachable.
    """
    url = f"{api_url}/api/projects/{project_name}/agent-specs?limit=1&offset=0"
    data = _api_get_json(url)
    if data is not None and "total" in data:
        return data["total"]
    return None


def query_agent_runs_count_api(api_url):
    """Query agent_runs count via GET /api/agent-runs?limit=1.

    The response includes a ``total`` field with the full count.

    Returns:
        int count, or None if API is unreachable.
    """
    url = f"{api_url}/api/agent-runs?limit=1&offset=0"
    data = _api_get_json(url)
    if data is not None and "total" in data:
        return data["total"]
    return None


def query_counts_via_api(api_url, project_name):
    """Attempt to query counts via API endpoints.

    Returns:
        dict mapping table name to count for tables successfully queried via API,
        or empty dict if API is unreachable.
    """
    counts = {}

    specs_count = query_agent_specs_count_api(api_url, project_name)
    if specs_count is not None:
        counts["agent_specs"] = specs_count

    runs_count = query_agent_runs_count_api(api_url)
    if runs_count is not None:
        counts["agent_runs"] = runs_count

    # No top-level API endpoint for agent_events or artifacts;
    # these will be filled in by the SQLite fallback.

    return counts


# ---------------------------------------------------------------------------
# Main verification logic
# ---------------------------------------------------------------------------


def gather_counts(db_path, api_url, project_name, use_api=True):
    """Gather table counts using API (preferred) with SQLite fallback.

    Strategy:
    1. If use_api is True, try API endpoints for agent_specs and agent_runs
       (they expose ``total``).
    2. For tables without API endpoints (agent_events, artifacts), or if API
       is unreachable / disabled, fall back to direct SQLite queries.

    Args:
        db_path: Path to the SQLite database file.
        api_url: Base URL of the API server.
        project_name: Project name for API queries.
        use_api: Whether to attempt API queries first. Default True.

    Returns:
        tuple of (counts_dict, method_dict) where:
        - counts_dict maps table name to row count
        - method_dict maps table name to "api" or "sqlite" (query method used)
    """
    counts = {}
    methods = {}

    # Step 1: Try API for specs and runs (if enabled)
    if use_api:
        api_counts = query_counts_via_api(api_url, project_name)
        for table, count in api_counts.items():
            counts[table] = count
            methods[table] = "api"

    # Step 2: SQLite fallback for any tables not yet resolved
    remaining = [t for t in REQUIRED_TABLES + OPTIONAL_TABLES if t not in counts]
    if remaining and os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        for table in remaining:
            counts[table] = get_table_count_sqlite(conn, table)
            methods[table] = "sqlite"
        conn.close()
    elif remaining:
        # DB doesn't exist and API didn't cover these tables
        for table in remaining:
            counts[table] = 0
            methods[table] = "sqlite"

    return counts, methods


def main():
    db_path = get_db_path()
    api_url = os.environ.get("AUTOBUILDR_API_URL", DEFAULT_API_URL)
    project_name = os.environ.get("AUTOBUILDR_TEST_PROJECT_NAME", DEFAULT_PROJECT_NAME)

    # Determine whether to use API mode:
    # - If an explicit DB path was passed as CLI arg, default to SQLite-only
    #   (the caller is targeting a specific database file).
    # - Unless VERIFY_SPEC_USE_API=1 is set, which forces API mode.
    force_api = os.environ.get("VERIFY_SPEC_USE_API", "") == "1"
    use_api = force_api or not _explicit_db_target()

    # If no DB file and no API, fail early
    if not os.path.exists(db_path):
        if use_api:
            # Still try API — maybe the server is up even if local DB is elsewhere
            api_counts = query_counts_via_api(api_url, project_name)
            if not api_counts:
                print(f"ERROR: Database not found at {db_path}")
                print("FAIL: Spec path not executed; legacy path likely used.")
                sys.exit(1)
        else:
            print(f"ERROR: Database not found at {db_path}")
            print("FAIL: Spec path not executed; legacy path likely used.")
            sys.exit(1)

    counts, methods = gather_counts(db_path, api_url, project_name, use_api=use_api)

    # --- Output ---
    print("=== Spec-Path Verification ===")
    all_ok = True
    for table in REQUIRED_TABLES:
        count = counts.get(table, 0)
        method = methods.get(table, "unknown")
        status_label = "OK" if count > 0 else "EMPTY"
        print(f"  {table}: {count} rows [{status_label}] (via {method})")
        if count == 0:
            all_ok = False

    # Optional tables
    for table in OPTIONAL_TABLES:
        count = counts.get(table, 0)
        method = methods.get(table, "unknown")
        status_label = "OK" if count > 0 else "EMPTY"
        print(f"  {table}: {count} rows [{status_label}] (via {method}) [optional]")

    print()

    if not all_ok:
        print("FAIL: Spec path not executed; legacy path likely used.")
        sys.exit(1)

    print("PASS: Spec-driven path verified — all tables have rows.")
    sys.exit(0)


if __name__ == "__main__":
    main()
