#!/usr/bin/env python3
"""
Feature #85: Page Load Performance with Large Dataset
=====================================================

This script creates test data for performance testing:
- 100 test AgentSpec records
- 50 test AgentRun records with various statuses

Run with: python tests/test_feature_85_performance_data.py
"""

import sys
import uuid
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.database import create_database
from api.agentspec_models import (
    AgentSpec, AcceptanceSpec, AgentRun,
    TASK_TYPES, RUN_STATUS, VERDICT
)

# Project directory
PROJECT_DIR = Path(__file__).parent.parent

# Test data configuration
NUM_SPECS = 100
NUM_RUNS = 50  # Will create at least 50 runs across the specs

# Sample data for generating realistic specs
TASK_DESCRIPTIONS = [
    "Implement user authentication flow",
    "Build API rate limiting middleware",
    "Create database migration scripts",
    "Add input validation to forms",
    "Implement caching layer for API responses",
    "Build WebSocket connection manager",
    "Create user dashboard component",
    "Implement search functionality",
    "Add pagination to list endpoints",
    "Build file upload handler",
    "Create email notification service",
    "Implement error tracking and logging",
    "Build admin control panel",
    "Create data export functionality",
    "Implement two-factor authentication",
    "Build user profile management",
    "Create API documentation generator",
    "Implement session management",
    "Build reporting dashboard",
    "Create audit log functionality",
]

ICONS = ["🔧", "⚙️", "🧪", "📝", "🔍", "💻", "🚀", "📊", "🔐", "📁", "📧", "🎯", "🔄", "📈", "🛠️"]

TAGS_OPTIONS = [
    ["critical", "v1"],
    ["enhancement"],
    ["bug-fix"],
    ["security"],
    ["performance"],
    ["ui", "frontend"],
    ["api", "backend"],
    ["database"],
    ["auth"],
    ["testing"],
]


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def random_datetime_in_past(days_range: int = 30) -> datetime:
    """Generate a random datetime within the past N days."""
    delta = timedelta(
        days=random.randint(0, days_range),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return utc_now() - delta


def create_tool_policy() -> dict:
    """Create a sample tool policy."""
    return {
        "policy_version": "v1",
        "allowed_tools": [
            "feature_get_by_id",
            "feature_mark_passing",
            "feature_mark_in_progress",
            "Read",
            "Write",
            "Edit",
            "Bash",
            "Glob",
            "Grep",
        ],
        "forbidden_patterns": ["rm -rf", "DROP TABLE"],
        "tool_hints": {
            "feature_mark_passing": "Call only after verification"
        },
    }


def create_validators() -> list:
    """Create sample validators for AcceptanceSpec."""
    return [
        {
            "type": "test_pass",
            "config": {"command": "npm test"},
            "weight": 1.0,
            "required": True,
        },
        {
            "type": "file_exists",
            "config": {"path": "{project_dir}/src/index.ts"},
            "weight": 0.5,
            "required": False,
        },
    ]


def create_test_specs(session, num_specs: int) -> list:
    """Create test AgentSpec records."""
    specs = []

    for i in range(num_specs):
        spec_id = generate_uuid()
        task_type = random.choice(TASK_TYPES)

        # Generate unique name
        base_desc = random.choice(TASK_DESCRIPTIONS)
        name = f"perf-test-spec-{i:03d}"
        display_name = f"{base_desc} #{i+1}"

        # Create spec
        spec = AgentSpec(
            id=spec_id,
            name=name,
            display_name=display_name,
            icon=random.choice(ICONS),
            spec_version="v1",
            objective=f"Performance test spec {i+1}: {base_desc.lower()}",
            task_type=task_type,
            context={"test_id": i, "category": "performance_test"},
            tool_policy=create_tool_policy(),
            max_turns=random.choice([50, 100, 150, 200]),
            timeout_seconds=random.choice([1800, 3600, 5400]),
            priority=random.randint(1, 1000),
            tags=random.choice(TAGS_OPTIONS),
            created_at=random_datetime_in_past(30),
        )

        session.add(spec)
        specs.append(spec)

        # Create associated AcceptanceSpec (50% of the time)
        if random.random() > 0.5:
            acceptance = AcceptanceSpec(
                id=generate_uuid(),
                agent_spec_id=spec_id,
                validators=create_validators(),
                gate_mode=random.choice(["all_pass", "any_pass"]),
                retry_policy=random.choice(["none", "fixed"]),
                max_retries=random.randint(0, 3),
            )
            session.add(acceptance)

    session.commit()
    print(f"Created {num_specs} AgentSpec records")
    return specs


def create_test_runs(session, specs: list, num_runs: int) -> list:
    """Create test AgentRun records with various statuses."""
    runs = []

    # Distribute statuses
    status_weights = {
        "pending": 10,
        "running": 15,
        "paused": 5,
        "completed": 40,
        "failed": 20,
        "timeout": 10,
    }

    statuses = []
    for status, weight in status_weights.items():
        statuses.extend([status] * weight)

    for i in range(num_runs):
        # Pick a random spec
        spec = random.choice(specs)
        status = random.choice(statuses)

        run_id = generate_uuid()
        created_at = random_datetime_in_past(14)

        # Determine timestamps based on status
        started_at = None
        completed_at = None

        if status in ["running", "paused", "completed", "failed", "timeout"]:
            started_at = created_at + timedelta(seconds=random.randint(1, 60))

        if status in ["completed", "failed", "timeout"]:
            completed_at = started_at + timedelta(seconds=random.randint(60, 3600))

        # Generate realistic metrics
        turns_used = random.randint(1, spec.max_turns)
        tokens_in = random.randint(1000, 100000)
        tokens_out = random.randint(500, 50000)

        # Determine verdict for terminal states
        final_verdict = None
        acceptance_results = None
        error = None

        if status == "completed":
            final_verdict = "passed" if random.random() > 0.3 else "error"
            acceptance_results = {
                "test_pass": {"passed": True, "message": "Tests passed", "type": "test_pass"},
                "file_exists": {"passed": True, "message": "File exists", "type": "file_exists"},
            }
        elif status == "failed":
            final_verdict = "failed"
            error = f"Error during execution: {random.choice(['Timeout waiting for response', 'Tool execution failed', 'Validation error', 'Network error'])}"
            acceptance_results = {
                "test_pass": {"passed": False, "message": "Tests failed", "type": "test_pass"},
            }
        elif status == "timeout":
            final_verdict = "failed"
            error = f"Execution exceeded time budget ({spec.timeout_seconds}s)"

        run = AgentRun(
            id=run_id,
            agent_spec_id=spec.id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            turns_used=turns_used,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            final_verdict=final_verdict,
            acceptance_results=acceptance_results,
            error=error,
            retry_count=random.randint(0, 2),
            created_at=created_at,
        )

        session.add(run)
        runs.append(run)

    session.commit()
    print(f"Created {num_runs} AgentRun records")
    return runs


def delete_test_data(session) -> tuple:
    """Delete existing performance test data."""
    # Delete runs first (foreign key constraint)
    deleted_runs = session.query(AgentRun).join(AgentSpec).filter(
        AgentSpec.name.like("perf-test-spec-%")
    ).delete(synchronize_session=False)

    # Delete specs (cascades to acceptance specs)
    deleted_specs = session.query(AgentSpec).filter(
        AgentSpec.name.like("perf-test-spec-%")
    ).delete(synchronize_session=False)

    session.commit()
    return deleted_specs, deleted_runs


def main():
    """Main function to create test data."""
    print("=" * 60)
    print("Feature #85: Page Load Performance Test Data Generator")
    print("=" * 60)

    # Initialize database
    engine, SessionLocal = create_database(PROJECT_DIR)
    session = SessionLocal()

    try:
        # Check for existing test data
        existing_count = session.query(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()

        if existing_count > 0:
            print(f"\nFound {existing_count} existing performance test specs")
            print("Deleting existing test data...")
            deleted_specs, deleted_runs = delete_test_data(session)
            print(f"Deleted {deleted_specs} specs and {deleted_runs} runs")

        print(f"\nCreating {NUM_SPECS} test AgentSpec records...")
        specs = create_test_specs(session, NUM_SPECS)

        print(f"\nCreating {NUM_RUNS} test AgentRun records...")
        runs = create_test_runs(session, specs, NUM_RUNS)

        # Verify counts
        total_specs = session.query(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()
        total_runs = session.query(AgentRun).join(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()

        print("\n" + "=" * 60)
        print("Test Data Summary")
        print("=" * 60)
        print(f"AgentSpecs created: {total_specs}")
        print(f"AgentRuns created: {total_runs}")

        # Show status distribution
        print("\nRun Status Distribution:")
        for status in RUN_STATUS:
            count = session.query(AgentRun).join(AgentSpec).filter(
                AgentSpec.name.like("perf-test-spec-%"),
                AgentRun.status == status
            ).count()
            print(f"  {status}: {count}")

        print("\nTest data ready for performance testing!")
        print("Navigate to http://localhost:8888 to test page load performance.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
