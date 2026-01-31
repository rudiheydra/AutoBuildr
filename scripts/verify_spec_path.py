#!/usr/bin/env python3
"""Verify that the spec-driven path was executed.

Checks that agent_specs, agent_runs, and agent_events tables all have rows.
Exits non-zero with a clear message if any are empty (indicating the legacy
path was likely used instead of the spec-driven path).

Usage:
    python3 scripts/verify_spec_path.py [DB_PATH]

    DB_PATH defaults to $AUTOBUILDR_TEST_PROJECT_PATH/features.db or ./features.db
"""
import sqlite3
import sys
import os


def get_db_path():
    """Determine the database path from args or environment."""
    if len(sys.argv) > 1:
        return sys.argv[1]
    project_path = os.environ.get("AUTOBUILDR_TEST_PROJECT_PATH", ".")
    return os.path.join(project_path, "features.db")


def get_table_count(conn, table_name):
    """Get the row count for a table, returning 0 on any error."""
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    except Exception:
        return 0


def main():
    db_path = get_db_path()

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        print("FAIL: Spec path not executed; legacy path likely used.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    tables = ["agent_specs", "agent_runs", "agent_events"]
    counts = {t: get_table_count(conn, t) for t in tables}
    conn.close()

    print("=== Spec-Path Verification ===")
    all_ok = True
    for t in tables:
        status = "OK" if counts[t] > 0 else "EMPTY"
        print(f"  {t}: {counts[t]} rows [{status}]")
        if counts[t] == 0:
            all_ok = False
    print()

    if not all_ok:
        print("FAIL: Spec path not executed; legacy path likely used.")
        sys.exit(1)

    print("PASS: Spec-driven path verified — all tables have rows.")
    sys.exit(0)


if __name__ == "__main__":
    main()
