#!/usr/bin/env python3
"""
Script to add Spec-Driven Orchestrator features to the AutoBuildr database.
Thin vertical slice: 10 features for end-to-end spec mode.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature, create_database

# Thin vertical slice: 10 features for spec-driven orchestrator
FEATURES = [
    # Feature 1: CLI flag and mode selection
    {
        "category": "functional",
        "name": "Add --spec CLI flag and AUTOBUILDR_MODE env var to autonomous_agent_demo.py",
        "description": "Add command-line argument --spec and AUTOBUILDR_MODE=spec environment variable to enable spec-driven execution. When enabled, orchestrator uses HarnessKernel instead of legacy prompt path. Must log project_dir and exact DB path at startup, and fail fast if DB is not under target project directory.",
        "steps": [
            "Add --spec boolean argument to argparse in autonomous_agent_demo.py",
            "Read AUTOBUILDR_MODE from os.environ (default 'legacy')",
            "CLI flag overrides env var if both present",
            "At startup, log: 'Spec mode: project_dir={path}, db_path={path}'",
            "Assert db_path.startswith(project_dir) or fail with clear error",
            "Pass spec_mode flag to orchestrator initialization"
        ]
    },

    # Feature 2: SpecOrchestrator core module
    {
        "category": "functional",
        "name": "Create SpecOrchestrator class with compile-execute-sync loop",
        "description": "Create api/spec_orchestrator.py with SpecOrchestrator class that implements the minimal spec execution loop: get feature -> compile to AgentSpec -> execute via HarnessKernel -> sync verdict back to Feature. No complex turn executor bridge - use simplest adapter possible.",
        "steps": [
            "Create api/spec_orchestrator.py module",
            "Implement __init__(project_dir, session, yolo_mode=False)",
            "Implement get_next_feature() - query pending features with deps satisfied",
            "Implement run_one_feature(feature) that does: compile -> persist -> execute -> sync",
            "Implement run_loop(max_features=None) - process features until done",
            "Use existing FeatureCompiler.compile() and HarnessKernel.execute()",
            "After run, log table counts: agent_specs, agent_runs, agent_events"
        ]
    },

    # Feature 3: Ensure spec tables exist
    {
        "category": "functional",
        "name": "Add ensure_spec_tables() to create agent_specs/runs/events tables if missing",
        "description": "Create function that ensures all AgentSpec-related tables exist in the project database. Run as additive migration - don't drop existing data. Call this when spec mode starts.",
        "steps": [
            "Add ensure_spec_tables(engine) function to api/agentspec_models.py or api/database.py",
            "Use SQLAlchemy metadata.create_all() for AgentSpec, AcceptanceSpec, AgentRun, AgentEvent, Artifact tables",
            "Log which tables were created vs already existed",
            "Call from SpecOrchestrator.__init__() before any spec operations",
            "Handle errors gracefully with clear messages"
        ]
    },

    # Feature 4: Wire spec mode into entry point
    {
        "category": "functional",
        "name": "Wire SpecOrchestrator into autonomous_agent_demo.py when --spec flag is set",
        "description": "Modify the main entry point to use SpecOrchestrator when spec mode is enabled. Legacy ParallelOrchestrator path remains default. Both paths must work.",
        "steps": [
            "Import SpecOrchestrator in autonomous_agent_demo.py",
            "After arg parsing, check if spec_mode is True",
            "If spec_mode: create SpecOrchestrator and call run_loop()",
            "Else: use existing ParallelOrchestrator logic unchanged",
            "Ensure graceful error handling for spec mode failures",
            "Log 'Using spec-driven execution' or 'Using legacy execution' at startup"
        ]
    },

    # Feature 5: Task type mapping for diverse specs
    {
        "category": "functional",
        "name": "Ensure FeatureCompiler maps categories to diverse task_types (audit/testing/docs/coding/refactor)",
        "description": "Verify and enhance FeatureCompiler to produce at least 3 distinct task_types from typical feature categories. Map: security->audit, test->testing, docs->documentation, database/api/ui->coding, refactor->refactoring.",
        "steps": [
            "Review CATEGORY_TO_TASK_TYPE in api/feature_compiler.py",
            "Add/verify mappings: security->audit, test/testing->testing, docs/documentation->documentation",
            "Add mappings: database/api/ui/functional->coding, refactor->refactoring",
            "Add fallback: unknown categories default to 'coding'",
            "Add get_task_type_distribution(session) helper to query task_type counts",
            "Log task_type when compiling each feature"
        ]
    },

    # Feature 6: Agent snapshot materialization (optional visibility)
    {
        "category": "functional",
        "name": "Implement optional AgentSpec snapshot materialization to .claude/agents/generated/",
        "description": "After persisting AgentSpec to database, optionally write a markdown snapshot file for visibility/inspection. Controlled by --materialize-agents flag. Files are for inspection only, not execution.",
        "steps": [
            "Add --materialize-agents flag to CLI (default: False)",
            "Create materialize_spec(spec, project_dir) function",
            "Create .claude/agents/generated/ directory if missing",
            "Write {spec.name}.md with YAML frontmatter (name, task_type, tools) and body (objective, acceptance)",
            "Call materializer after spec persistence if flag enabled",
            "Log path of each materialized file"
        ]
    },

    # Feature 7: Verification queries and DB count output
    {
        "category": "functional",
        "name": "Add verification output: print table counts and task_type distribution after spec run",
        "description": "After SpecOrchestrator.run_loop() completes, print comprehensive verification output showing DB table counts and task_type distribution. This proves spec mode populated the database correctly.",
        "steps": [
            "Create print_verification_summary(session) function",
            "Query and print counts: features, agent_specs, agent_runs, agent_events, artifacts",
            "Query and print: SELECT task_type, COUNT(*) FROM agent_specs GROUP BY task_type",
            "Print acceptance criteria check: agent_specs>=10, agent_runs>=10, agent_events>=100, task_types>=3",
            "Call at end of run_loop()",
            "Also write summary to {project_dir}/spec_run_summary.txt"
        ]
    },

    # Feature 8: Smoke test for spec orchestrator
    {
        "category": "testing",
        "name": "Create smoke test proving spec mode creates specs/runs/events with diverse task_types",
        "description": "Add tests/test_spec_orchestrator_smoke.py that validates end-to-end spec mode: insert features -> run spec orchestrator -> verify DB has agent_specs, agent_runs, agent_events, and at least 2 distinct task_types.",
        "steps": [
            "Create tests/test_spec_orchestrator_smoke.py",
            "Create in-memory SQLite fixture with Feature + AgentSpec tables",
            "Insert 5 test features: 1 security (audit), 1 test (testing), 1 docs, 2 functional (coding)",
            "Mock Claude SDK to return success immediately",
            "Run SpecOrchestrator.run_loop()",
            "Assert: agent_specs >= 5, agent_runs >= 5, agent_events >= 5",
            "Assert: at least 2 distinct task_types in agent_specs"
        ]
    },

    # Feature 9: Documentation for spec mode usage
    {
        "category": "documentation",
        "name": "Create docs/spec_mode.md with usage instructions and verification queries",
        "description": "Document how to run spec mode, expected DB state, and verification queries. Include the exact command to run, environment variables, and Python snippet to verify DB contents.",
        "steps": [
            "Create docs/spec_mode.md",
            "Document: python autonomous_agent_demo.py --spec /path/to/project",
            "Document: AUTOBUILDR_MODE=spec environment variable",
            "Document expected output: agent_specs>=10, agent_runs>=10, agent_events>=100",
            "Include Python verification snippet for querying table counts",
            "Document --materialize-agents flag for agent snapshots"
        ]
    },

    # Feature 10: Error handling and graceful degradation
    {
        "category": "error-handling",
        "name": "Handle spec compilation and execution failures gracefully without crashing orchestrator",
        "description": "When FeatureCompiler fails or HarnessKernel execution fails, log error, mark feature as failed, and continue to next feature. Don't crash the entire orchestrator on single feature failure.",
        "steps": [
            "Wrap compile step in try/except, log error, set feature.passes=False on failure",
            "Wrap execute step in try/except, handle timeout/budget exceeded",
            "On execution failure: create AgentRun with status='failed', record error event",
            "Update feature.in_progress=False regardless of outcome",
            "Continue to next feature after failure",
            "Log summary of successes/failures at end of run"
        ]
    }
]


def main():
    """Add spec orchestrator features to the database."""
    # Initialize database
    engine, SessionLocal = create_database(Path('.'))
    session = SessionLocal()

    try:
        # Get current max priority
        max_priority_result = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
        start_priority = (max_priority_result[0] + 1) if max_priority_result else 1

        print(f"Current max priority: {start_priority - 1 if max_priority_result else 0}")
        print(f"Starting priority for new features: {start_priority}")
        print(f"Adding {len(FEATURES)} features for Spec-Driven Orchestrator...")
        print()

        # Create all features
        created_ids = []
        for i, feature_data in enumerate(FEATURES):
            db_feature = Feature(
                priority=start_priority + i,
                category=feature_data["category"],
                name=feature_data["name"],
                description=feature_data["description"],
                steps=feature_data["steps"],
                passes=False,
                in_progress=False,
            )
            session.add(db_feature)
            session.flush()  # Get the ID
            created_ids.append(db_feature.id)
            print(f"  [{i+1:2d}] ID={db_feature.id}: {feature_data['name'][:60]}...")

        session.commit()
        print()
        print(f"Successfully added {len(FEATURES)} features!")
        print(f"Feature IDs: {created_ids[0]} to {created_ids[-1]}")

        # Print new total
        total = session.query(Feature).count()
        passing = session.query(Feature).filter(Feature.passes == True).count()
        print(f"Total features now: {total} ({passing} passing, {total - passing} pending)")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
