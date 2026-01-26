#!/usr/bin/env python3
"""
End-to-end verification for Feature #36: StaticSpecAdapter for Legacy Initializer

Tests the full integration:
1. Create StaticSpecAdapter
2. Generate initializer spec
3. Verify spec can be persisted to database
4. Verify spec can be retrieved from database
5. Verify all relationships are intact
"""
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, AcceptanceSpec, AgentRun, AgentEvent, Artifact
from api.static_spec_adapter import StaticSpecAdapter


def main():
    print("\n" + "=" * 70)
    print("Feature #36: StaticSpecAdapter - End-to-End Verification")
    print("=" * 70 + "\n")

    # Create in-memory database
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Step 1: Create adapter and generate spec
        print("Step 1: Creating StaticSpecAdapter and generating initializer spec...")
        adapter = StaticSpecAdapter()
        spec = adapter.create_initializer_spec(
            project_name="E2ETestProject",
            feature_count=100,
        )
        print(f"  - Created spec: {spec.name}")
        print(f"  - Spec ID: {spec.id}")

        # Step 2: Persist to database
        print("\nStep 2: Persisting spec to database...")
        session.add(spec)
        session.commit()
        print(f"  - Spec committed to database")

        # Step 3: Retrieve from database
        print("\nStep 3: Retrieving spec from database...")
        retrieved_spec = session.query(AgentSpec).filter_by(id=spec.id).first()
        assert retrieved_spec is not None, "Spec should be retrievable"
        print(f"  - Retrieved spec: {retrieved_spec.name}")

        # Step 4: Verify all fields
        print("\nStep 4: Verifying spec fields...")
        assert retrieved_spec.name == spec.name
        assert retrieved_spec.task_type == "custom"
        assert retrieved_spec.max_turns == 100
        assert retrieved_spec.timeout_seconds == 3600
        assert retrieved_spec.objective is not None
        assert len(retrieved_spec.objective) > 100
        assert retrieved_spec.tool_policy is not None
        assert "allowed_tools" in retrieved_spec.tool_policy
        print(f"  - All spec fields verified")

        # Step 5: Verify acceptance spec relationship
        print("\nStep 5: Verifying AcceptanceSpec relationship...")
        acceptance = session.query(AcceptanceSpec).filter_by(agent_spec_id=spec.id).first()
        assert acceptance is not None, "AcceptanceSpec should exist"
        assert acceptance.validators is not None
        assert len(acceptance.validators) > 0
        print(f"  - AcceptanceSpec found with {len(acceptance.validators)} validators")

        # Step 6: Verify feature_count validator
        print("\nStep 6: Verifying feature_count validator...")
        feature_count_validator = None
        for v in acceptance.validators:
            if v.get("config", {}).get("check_type") == "feature_count":
                feature_count_validator = v
                break
        assert feature_count_validator is not None, "feature_count validator should exist"
        assert feature_count_validator["config"]["expected_count"] == 100
        assert feature_count_validator["required"] == True
        print(f"  - feature_count validator verified (expected: 100)")

        # Step 7: Test spec serialization
        print("\nStep 7: Testing spec serialization...")
        spec_dict = retrieved_spec.to_dict()
        assert isinstance(spec_dict, dict)
        assert spec_dict["id"] == spec.id
        assert spec_dict["name"] == spec.name
        print(f"  - Spec serialization verified")

        # Step 8: Create coding and testing specs
        print("\nStep 8: Creating coding and testing specs...")
        coding_spec = adapter.create_coding_spec(
            feature_id=42,
            feature_name="Test Feature"
        )
        testing_spec = adapter.create_testing_spec(
            feature_id=42,
            feature_name="Test Feature"
        )
        session.add(coding_spec)
        session.add(testing_spec)
        session.commit()
        print(f"  - Coding spec: {coding_spec.name}")
        print(f"  - Testing spec: {testing_spec.name}")

        # Step 9: Verify all three specs can be queried
        print("\nStep 9: Querying all specs from database...")
        all_specs = session.query(AgentSpec).all()
        assert len(all_specs) == 3
        print(f"  - Found {len(all_specs)} specs in database")

        task_types = {s.task_type for s in all_specs}
        assert "custom" in task_types  # initializer
        assert "coding" in task_types
        assert "testing" in task_types
        print(f"  - Task types: {task_types}")

        print("\n" + "-" * 70)
        print("\033[92mAll end-to-end verification steps PASSED!\033[0m")
        print("-" * 70 + "\n")

        return 0

    except Exception as e:
        print(f"\n\033[91mError: {e}\033[0m")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
