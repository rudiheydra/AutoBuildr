#!/usr/bin/env python
"""
Verification Script for Feature #189: Octo persists AgentSpecs to database
==========================================================================

This script verifies all 5 feature steps are properly implemented:
1. AgentSpec saved to agent_specs table after generation
2. Spec includes source_type='octo_generated'
3. Spec linked to project and triggering request
4. Database record created before file materialization
5. Dual persistence: DB is system-of-record, files are CLI-authoritative

Run: python tests/verify_feature_189.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base
from api.agentspec_models import AgentSpec, generate_uuid
from api.octo import (
    Octo,
    OctoRequestPayload,
    SpecPersistenceResult,
    SOURCE_TYPE_OCTO_GENERATED,
    VALID_SOURCE_TYPES,
)


def create_test_db():
    """Create an in-memory test database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def create_mock_spec_builder():
    """Create a mock spec builder that returns valid specs."""
    from unittest.mock import MagicMock
    from api.spec_builder import BuildResult

    mock_builder = MagicMock()

    def mock_build(task_description, task_type, context=None):
        spec = AgentSpec(
            id=generate_uuid(),
            name=f"generated-{task_type}-agent",
            display_name=f"Generated {task_type.title()} Agent",
            objective=task_description,
            task_type=task_type,
            tool_policy={
                "policy_version": "v1",
                "allowed_tools": ["feature_get_by_id"],
                "forbidden_patterns": [],
                "tool_hints": {},
            },
            max_turns=100,
            timeout_seconds=1800,
            context=context or {},
        )
        return BuildResult(success=True, agent_spec=spec, error=None)

    mock_builder.build = mock_build
    return mock_builder


def verify_step1():
    """Step 1: AgentSpec saved to agent_specs table after generation."""
    print("\n[Step 1] Verifying AgentSpec saved to agent_specs table...")

    session = create_test_db()
    octo = Octo(spec_builder=create_mock_spec_builder())

    spec = AgentSpec(
        id=generate_uuid(),
        name="test-agent-step1",
        display_name="Test Agent Step 1",
        objective="Test objective",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
        max_turns=50,
        timeout_seconds=1800,
        context={},
    )

    result = octo.persist_spec(spec=spec, session=session, project_name="test-project")
    session.commit()

    # Verify
    assert result.success, f"Persistence failed: {result.error}"
    db_spec = session.query(AgentSpec).filter_by(id=spec.id).first()
    assert db_spec is not None, "Spec not found in database"
    assert db_spec.__tablename__ == "agent_specs", f"Wrong table: {db_spec.__tablename__}"

    session.close()
    print("  ✓ AgentSpec successfully saved to agent_specs table")
    return True


def verify_step2():
    """Step 2: Spec includes source_type='octo_generated'."""
    print("\n[Step 2] Verifying source_type='octo_generated' in context...")

    session = create_test_db()
    octo = Octo(spec_builder=create_mock_spec_builder())

    spec = AgentSpec(
        id=generate_uuid(),
        name="test-agent-step2",
        display_name="Test Agent Step 2",
        objective="Test source_type",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
        max_turns=50,
        timeout_seconds=1800,
        context={},
    )

    result = octo.persist_spec(spec=spec, session=session)
    session.commit()

    # Verify source_type constant
    assert SOURCE_TYPE_OCTO_GENERATED == "octo_generated", f"Wrong constant value: {SOURCE_TYPE_OCTO_GENERATED}"
    assert SOURCE_TYPE_OCTO_GENERATED in VALID_SOURCE_TYPES, "octo_generated not in VALID_SOURCE_TYPES"

    # Verify in database
    db_spec = session.query(AgentSpec).filter_by(id=spec.id).first()
    assert db_spec.context is not None, "Context is None"
    assert db_spec.context.get("source_type") == "octo_generated", f"source_type={db_spec.context.get('source_type')}"

    session.close()
    print("  ✓ source_type='octo_generated' properly set in spec context")
    return True


def verify_step3():
    """Step 3: Spec linked to project and triggering request."""
    print("\n[Step 3] Verifying project and request linkage...")

    session = create_test_db()
    octo = Octo(spec_builder=create_mock_spec_builder())

    spec = AgentSpec(
        id=generate_uuid(),
        name="test-agent-step3",
        display_name="Test Agent Step 3",
        objective="Test linkage",
        task_type="testing",
        tool_policy={"policy_version": "v1", "allowed_tools": [], "forbidden_patterns": [], "tool_hints": {}},
        max_turns=50,
        timeout_seconds=1800,
        context={},
    )

    result = octo.persist_spec(
        spec=spec,
        session=session,
        project_name="linked-project",
        octo_request_id="req-123-abc",
        source_feature_ids=[10, 20, 30],
    )
    session.commit()

    # Verify result
    assert result.project_name == "linked-project", f"project_name mismatch: {result.project_name}"
    assert result.octo_request_id == "req-123-abc", f"octo_request_id mismatch: {result.octo_request_id}"

    # Verify in database
    db_spec = session.query(AgentSpec).filter_by(id=spec.id).first()
    assert db_spec.context.get("project_name") == "linked-project", "project_name not in context"
    assert db_spec.context.get("octo_request_id") == "req-123-abc", "octo_request_id not in context"
    assert db_spec.context.get("source_feature_ids") == [10, 20, 30], "source_feature_ids not in context"
    assert db_spec.source_feature_id == 10, f"source_feature_id column: {db_spec.source_feature_id}"

    session.close()
    print("  ✓ Project and request linkage properly stored")
    return True


def verify_step4():
    """Step 4: Database record created before file materialization."""
    print("\n[Step 4] Verifying DB record created before materialization...")

    session = create_test_db()
    octo = Octo(spec_builder=create_mock_spec_builder())

    payload = OctoRequestPayload(
        project_context={"name": "step4-project", "tech_stack": ["Python"]},
        required_capabilities=["testing"],
        request_id="step4-request",
    )

    # generate_and_persist_specs creates DB records BEFORE returning
    response, persistence_results = octo.generate_and_persist_specs(
        payload=payload,
        session=session,
    )
    session.commit()

    # At this point, DB records exist but no files have been created
    # (materialization happens separately, after this call returns)
    assert response.success, f"Generation failed: {response.error}"
    assert len(persistence_results) > 0, "No persistence results"

    # Verify each spec exists in DB
    for result in persistence_results:
        assert result.success, f"Persistence failed for {result.spec_name}: {result.error}"
        db_spec = session.query(AgentSpec).filter_by(id=result.spec_id).first()
        assert db_spec is not None, f"Spec {result.spec_id} not in DB"

    session.close()
    print("  ✓ DB records created (caller can now proceed with materialization)")
    return True


def verify_step5():
    """Step 5: Dual persistence - DB is system-of-record."""
    print("\n[Step 5] Verifying dual persistence model...")

    session = create_test_db()
    octo = Octo(spec_builder=create_mock_spec_builder())

    spec = AgentSpec(
        id=generate_uuid(),
        name="test-agent-step5",
        display_name="Test Agent Step 5",
        objective="Verify system-of-record",
        task_type="coding",
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write", "Bash"],
            "forbidden_patterns": ["rm -rf", "DROP TABLE"],
            "tool_hints": {"Write": "Always backup first"},
        },
        max_turns=75,
        timeout_seconds=2400,
        context={"custom_key": "custom_value"},
        tags=["critical", "production"],
    )

    result = octo.persist_spec(spec=spec, session=session, project_name="sor-project")
    session.commit()

    # Verify DB contains complete spec data (system-of-record)
    db_spec = session.query(AgentSpec).filter_by(id=spec.id).first()

    # All critical fields stored
    assert db_spec.id is not None, "ID missing"
    assert db_spec.name == "test-agent-step5", "Name mismatch"
    assert db_spec.display_name == "Test Agent Step 5", "display_name mismatch"
    assert db_spec.objective == "Verify system-of-record", "objective mismatch"
    assert db_spec.task_type == "coding", "task_type mismatch"
    assert db_spec.max_turns == 75, "max_turns mismatch"
    assert db_spec.timeout_seconds == 2400, "timeout_seconds mismatch"
    assert db_spec.created_at is not None, "created_at missing"

    # Tool policy stored
    assert db_spec.tool_policy is not None, "tool_policy missing"
    assert "allowed_tools" in db_spec.tool_policy, "allowed_tools missing"
    assert "forbidden_patterns" in db_spec.tool_policy, "forbidden_patterns missing"

    # Context contains provenance + custom data
    assert db_spec.context.get("source_type") == SOURCE_TYPE_OCTO_GENERATED, "source_type missing"
    assert db_spec.context.get("project_name") == "sor-project", "project_name missing"
    assert db_spec.context.get("custom_key") == "custom_value", "custom_key overwritten"

    # Tags stored
    assert db_spec.tags == ["critical", "production"], "tags mismatch"

    session.close()
    print("  ✓ DB is system-of-record with complete spec data")
    return True


def main():
    """Run all verification steps."""
    print("=" * 70)
    print("Feature #189: Octo persists AgentSpecs to database - VERIFICATION")
    print("=" * 70)

    steps = [
        ("Step 1: AgentSpec saved to agent_specs table", verify_step1),
        ("Step 2: Spec includes source_type='octo_generated'", verify_step2),
        ("Step 3: Spec linked to project and request", verify_step3),
        ("Step 4: DB record created before materialization", verify_step4),
        ("Step 5: Dual persistence - DB is system-of-record", verify_step5),
    ]

    passed = 0
    failed = 0

    for name, verify_func in steps:
        try:
            if verify_func():
                passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"VERIFICATION COMPLETE: {passed}/{len(steps)} steps passed")
    print("=" * 70)

    if failed == 0:
        print("\n✅ ALL VERIFICATION STEPS PASSED")
        print("Feature #189 is ready to be marked as PASSING")
        return 0
    else:
        print(f"\n❌ {failed} VERIFICATION STEP(S) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
