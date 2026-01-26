#!/usr/bin/env python3
"""
Feature #68: Event Timeline Component - Test Data Generator
============================================================

Creates test AgentSpec, AgentRun, and AgentEvents to verify the
EventTimeline component works correctly in the browser.

Usage:
    python tests/verify_feature_68.py

This script:
1. Creates a test AgentSpec
2. Creates a test AgentRun
3. Creates sample AgentEvents of various types
4. Outputs the run_id for browser testing
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone, timedelta
import json

from api.database import create_database, set_session_maker
from api.agentspec_crud import (
    create_agent_spec,
    create_agent_run,
    create_event,
    get_agent_run,
    get_events,
)


def create_test_data():
    """Create test data for the EventTimeline component."""

    # Initialize database with project root as the directory
    engine, SessionLocal = create_database(project_root)
    set_session_maker(SessionLocal)

    # Get database session
    db = SessionLocal()

    try:
        # Create a test AgentSpec
        print("Creating test AgentSpec...")
        spec = create_agent_spec(
            session=db,
            name="test-timeline-spec",
            display_name="Test Timeline Feature",
            objective="Test the EventTimeline component with various event types",
            task_type="testing",
            allowed_tools=["feature_get_by_id", "feature_mark_passing"],
            icon="🧪",
            context={"test": True, "feature_id": 68},
            max_turns=100,
            timeout_seconds=3600,
            source_feature_id=68,
            priority=100,
            tags=["test", "timeline", "ui"],
        )
        db.commit()
        print(f"  Created AgentSpec: {spec.id}")

        # Create a test AgentRun
        print("Creating test AgentRun...")
        run = create_agent_run(
            session=db,
            agent_spec_id=spec.id,
        )
        db.commit()
        print(f"  Created AgentRun: {run.id}")

        # Create sample events with various types
        print("Creating sample AgentEvents...")

        base_time = datetime.now(timezone.utc)
        events_data = [
            {
                "event_type": "started",
                "payload": {"objective": spec.objective, "spec_id": spec.id},
                "tool_name": None,
            },
            {
                "event_type": "tool_call",
                "payload": {"tool": "feature_get_by_id", "args": {"feature_id": 68}},
                "tool_name": "feature_get_by_id",
            },
            {
                "event_type": "tool_result",
                "payload": {
                    "tool": "feature_get_by_id",
                    "result": {
                        "id": 68,
                        "name": "Event Timeline Component",
                        "description": "Create Event Timeline component with vertical timeline...",
                        "passes": False,
                    },
                },
                "tool_name": "feature_get_by_id",
            },
            {
                "event_type": "turn_complete",
                "payload": {"turn": 1, "tokens_in": 1500, "tokens_out": 500},
                "tool_name": None,
            },
            {
                "event_type": "tool_call",
                "payload": {
                    "tool": "Read",
                    "args": {"file_path": "/home/user/project/src/components/EventTimeline.tsx"},
                },
                "tool_name": "Read",
            },
            {
                "event_type": "tool_result",
                "payload": {
                    "tool": "Read",
                    "result": "File contents: export function EventTimeline({runId}...",
                    "size_bytes": 5234,
                },
                "tool_name": "Read",
            },
            {
                "event_type": "turn_complete",
                "payload": {"turn": 2, "tokens_in": 3000, "tokens_out": 800},
                "tool_name": None,
            },
            {
                "event_type": "tool_call",
                "payload": {
                    "tool": "Write",
                    "args": {
                        "file_path": "/home/user/project/src/components/EventTimeline.tsx",
                        "content": "// Updated content...",
                    },
                },
                "tool_name": "Write",
            },
            {
                "event_type": "tool_result",
                "payload": {"tool": "Write", "result": "File written successfully"},
                "tool_name": "Write",
            },
            {
                "event_type": "acceptance_check",
                "payload": {
                    "validators": [
                        {"type": "file_exists", "result": True, "path": "src/components/EventTimeline.tsx"},
                        {"type": "test_pass", "result": True, "command": "npm test"},
                    ],
                    "all_passed": True,
                },
                "tool_name": None,
            },
            {
                "event_type": "turn_complete",
                "payload": {"turn": 3, "tokens_in": 4500, "tokens_out": 1200},
                "tool_name": None,
            },
            {
                "event_type": "completed",
                "payload": {
                    "verdict": "passed",
                    "total_turns": 3,
                    "total_tokens_in": 9000,
                    "total_tokens_out": 2500,
                    "duration_seconds": 45.2,
                },
                "tool_name": None,
            },
        ]

        for i, event_data in enumerate(events_data):
            # Add time offset for each event
            event_time = base_time + timedelta(seconds=i * 5)

            event = create_event(
                session=db,
                run_id=run.id,
                event_type=event_data["event_type"],
                payload=event_data["payload"],
                tool_name=event_data.get("tool_name"),
            )
            print(f"  Created event #{event.sequence}: {event_data['event_type']}")

        db.commit()

        # Verify events were created
        events = get_events(db, run.id, limit=50)
        print(f"\nTotal events created: {len(events)}")

        # Print summary
        print("\n" + "=" * 60)
        print("TEST DATA CREATED SUCCESSFULLY")
        print("=" * 60)
        print(f"\nAgentSpec ID: {spec.id}")
        print(f"AgentRun ID:  {run.id}")
        print(f"Events:       {len(events)}")
        print(f"\nTo test the EventTimeline component:")
        print(f"1. Open the browser to http://localhost:8888")
        print(f"2. Navigate to or create a Run Inspector view")
        print(f"3. Use run_id: {run.id}")
        print(f"\nOr test the API directly:")
        print(f"  curl http://localhost:8888/api/agent-runs/{run.id}/events")
        print("=" * 60)

        return run.id

    except Exception as e:
        db.rollback()
        print(f"Error creating test data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_id = create_test_data()
    print(f"\nRun ID for testing: {run_id}")
