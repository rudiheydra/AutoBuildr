#!/usr/bin/env python3
"""
Feature #6 Verification Script
==============================

Test: Database Migration Preserves Existing Features

Verifies that the _migrate_add_agentspec_tables migration is:
1. Additive (creates new tables)
2. Non-destructive (existing features table unchanged)
3. Idempotent (can be run multiple times safely)
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from api.database import (
    Base,
    Feature,
    _migrate_add_agentspec_tables,
    _migrate_add_in_progress_column,
    _migrate_fix_null_boolean_fields,
    _migrate_add_dependencies_column,
)


def create_test_database(db_path: Path) -> tuple:
    """Create a test database with the features table only."""
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Create only the Feature table (simulating pre-migration state)
    Feature.__table__.create(bind=engine, checkfirst=True)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, SessionLocal


def insert_sample_features(session, count: int = 5) -> list[dict]:
    """Insert sample features and return their data for later verification."""
    sample_features = []

    for i in range(1, count + 1):
        feature_data = {
            "priority": i * 10,
            "category": f"Category_{i}",
            "name": f"Test Feature {i}",
            "description": f"Description for feature {i} with special chars: <>&'\"\n\tüöä",
            "steps": [f"Step {j} for feature {i}" for j in range(1, 4)],
            "passes": i % 2 == 0,  # Alternating true/false
            "in_progress": i == 3,  # Only feature 3 is in progress
            "dependencies": [1, 2] if i > 2 else None,  # Features 3+ depend on 1 and 2
        }

        feature = Feature(
            priority=feature_data["priority"],
            category=feature_data["category"],
            name=feature_data["name"],
            description=feature_data["description"],
            steps=feature_data["steps"],
            passes=feature_data["passes"],
            in_progress=feature_data["in_progress"],
            dependencies=feature_data["dependencies"],
        )
        session.add(feature)
        sample_features.append(feature_data)

    session.commit()

    # Get the actual IDs after commit
    all_features = session.query(Feature).order_by(Feature.priority).all()
    for i, feature in enumerate(all_features):
        sample_features[i]["id"] = feature.id

    return sample_features


def get_features_table_schema(engine) -> dict:
    """Get the schema of the features table for comparison."""
    inspector = inspect(engine)

    columns = inspector.get_columns("features")
    indexes = inspector.get_indexes("features")

    return {
        "columns": {col["name"]: str(col["type"]) for col in columns},
        "indexes": {idx["name"]: idx["column_names"] for idx in indexes},
    }


def verify_feature_data(session, original_features: list[dict]) -> list[str]:
    """Verify all original features still exist with unchanged data."""
    errors = []

    for original in original_features:
        feature = session.get(Feature, original["id"])

        if feature is None:
            errors.append(f"Feature {original['id']} is missing after migration!")
            continue

        # Verify each field
        if feature.priority != original["priority"]:
            errors.append(f"Feature {original['id']} priority changed: {original['priority']} -> {feature.priority}")

        if feature.category != original["category"]:
            errors.append(f"Feature {original['id']} category changed: {original['category']} -> {feature.category}")

        if feature.name != original["name"]:
            errors.append(f"Feature {original['id']} name changed: {original['name']} -> {feature.name}")

        if feature.description != original["description"]:
            errors.append(f"Feature {original['id']} description changed")

        if feature.steps != original["steps"]:
            errors.append(f"Feature {original['id']} steps changed: {original['steps']} -> {feature.steps}")

        if feature.passes != original["passes"]:
            errors.append(f"Feature {original['id']} passes changed: {original['passes']} -> {feature.passes}")

        if feature.in_progress != original["in_progress"]:
            errors.append(f"Feature {original['id']} in_progress changed: {original['in_progress']} -> {feature.in_progress}")

        # Handle None/empty list comparison for dependencies
        orig_deps = original["dependencies"] or []
        curr_deps = feature.dependencies or []
        if orig_deps != curr_deps:
            errors.append(f"Feature {original['id']} dependencies changed: {orig_deps} -> {curr_deps}")

    return errors


def run_verification():
    """Run all verification steps for Feature #6."""
    print("=" * 70)
    print("Feature #6: Database Migration Preserves Existing Features")
    print("=" * 70)
    print()

    results = {}

    # Create temporary directory for test database
    test_dir = Path(tempfile.mkdtemp(prefix="feature6_test_"))
    db_path = test_dir / "test_features.db"

    try:
        # Step 1: Create a test features.db with sample Feature records
        print("Step 1: Create a test features.db with sample Feature records")
        print("-" * 60)

        engine, SessionLocal = create_test_database(db_path)
        session = SessionLocal()

        original_features = insert_sample_features(session, count=5)
        print(f"  Created {len(original_features)} sample features")

        # Get original schema
        original_schema = get_features_table_schema(engine)
        print(f"  Original schema has {len(original_schema['columns'])} columns")
        print(f"  Original schema has {len(original_schema['indexes'])} indexes")

        # Get original table list
        inspector = inspect(engine)
        original_tables = set(inspector.get_table_names())
        print(f"  Original tables: {sorted(original_tables)}")

        session.close()
        results["step_1"] = True
        print("  PASS\n")

        # Step 2: Run the migration function _migrate_add_agentspec_tables
        print("Step 2: Run the migration function _migrate_add_agentspec_tables")
        print("-" * 60)

        try:
            _migrate_add_agentspec_tables(engine)
            print("  Migration completed without errors")
            results["step_2"] = True
            print("  PASS\n")
        except Exception as e:
            print(f"  Migration failed: {e}")
            results["step_2"] = False
            print("  FAIL\n")
            return results

        # Step 3: Verify all original Feature records still exist with unchanged data
        print("Step 3: Verify all original Feature records still exist with unchanged data")
        print("-" * 60)

        session = SessionLocal()
        errors = verify_feature_data(session, original_features)

        if errors:
            for error in errors:
                print(f"  ERROR: {error}")
            results["step_3"] = False
            print("  FAIL\n")
        else:
            print(f"  All {len(original_features)} features verified with unchanged data")
            results["step_3"] = True
            print("  PASS\n")

        session.close()

        # Step 4: Verify features table schema is unmodified
        print("Step 4: Verify features table schema is unmodified")
        print("-" * 60)

        new_schema = get_features_table_schema(engine)

        schema_match = True

        # Compare columns
        if original_schema["columns"] != new_schema["columns"]:
            print("  Column mismatch!")
            print(f"  Original: {original_schema['columns']}")
            print(f"  New: {new_schema['columns']}")
            schema_match = False
        else:
            print(f"  Columns unchanged: {len(new_schema['columns'])} columns")

        # Compare indexes (may have different names but same structure)
        if len(original_schema["indexes"]) != len(new_schema["indexes"]):
            print("  Index count mismatch!")
            schema_match = False
        else:
            print(f"  Indexes unchanged: {len(new_schema['indexes'])} indexes")

        results["step_4"] = schema_match
        print("  PASS\n" if schema_match else "  FAIL\n")

        # Step 5: Run migration again and verify idempotency
        print("Step 5: Run migration again and verify idempotency (no errors, no duplicates)")
        print("-" * 60)

        # Get table list before second migration
        inspector = inspect(engine)
        tables_before = set(inspector.get_table_names())

        try:
            _migrate_add_agentspec_tables(engine)
            print("  Second migration completed without errors")

            # Verify no duplicate tables or schema changes
            inspector = inspect(engine)
            tables_after = set(inspector.get_table_names())

            if tables_before != tables_after:
                print(f"  Table list changed: {tables_before} -> {tables_after}")
                results["step_5"] = False
            else:
                print(f"  Table list unchanged: {sorted(tables_after)}")

                # Verify feature data still intact
                session = SessionLocal()
                errors = verify_feature_data(session, original_features)
                session.close()

                if errors:
                    for error in errors:
                        print(f"  ERROR: {error}")
                    results["step_5"] = False
                else:
                    print("  Feature data still intact")
                    results["step_5"] = True

            print("  PASS\n" if results["step_5"] else "  FAIL\n")

        except Exception as e:
            print(f"  Second migration failed: {e}")
            results["step_5"] = False
            print("  FAIL\n")

        # Step 6: Verify new tables are created only if they do not exist
        print("Step 6: Verify new tables are created only if they do not exist")
        print("-" * 60)

        inspector = inspect(engine)
        final_tables = set(inspector.get_table_names())

        expected_new_tables = {"agent_specs", "acceptance_specs", "agent_runs", "artifacts", "agent_events"}
        actual_new_tables = final_tables - original_tables

        print(f"  Original tables: {sorted(original_tables)}")
        print(f"  New tables created: {sorted(actual_new_tables)}")
        print(f"  Expected new tables: {sorted(expected_new_tables)}")

        if actual_new_tables == expected_new_tables:
            print("  All expected tables created")

            # Verify each new table has correct structure (non-empty, has columns)
            all_tables_valid = True
            for table_name in expected_new_tables:
                columns = inspector.get_columns(table_name)
                if not columns:
                    print(f"  Table {table_name} has no columns!")
                    all_tables_valid = False
                else:
                    print(f"  Table {table_name}: {len(columns)} columns")

            results["step_6"] = all_tables_valid
        else:
            missing = expected_new_tables - actual_new_tables
            extra = actual_new_tables - expected_new_tables
            if missing:
                print(f"  Missing tables: {missing}")
            if extra:
                print(f"  Extra tables: {extra}")
            results["step_6"] = False

        print("  PASS\n" if results["step_6"] else "  FAIL\n")

    finally:
        # Cleanup
        try:
            shutil.rmtree(test_dir)
        except Exception:
            pass

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    all_passed = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {step}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All verification steps PASSED!")
    else:
        print("Some verification steps FAILED!")

    return all_passed


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
