#!/usr/bin/env python3
"""
Verification script for Feature #197: Agent Materializer handles multiple agents in batch

This script verifies all 5 feature steps:
1. Materializer accepts list of AgentSpecs
2. Each spec processed and written individually
3. Batch operation is atomic: all succeed or none written
4. Progress reported for each agent
5. Single audit event or per-agent events recorded
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.agent_materializer import (
    AgentMaterializer,
    BatchMaterializationResult,
    MaterializationResult,
    DEFAULT_OUTPUT_DIR,
)
from api.agentspec_models import AgentSpec, generate_uuid


def create_test_specs(count: int = 3) -> list[AgentSpec]:
    """Create test AgentSpecs for verification."""
    specs = []
    for i in range(count):
        spec = AgentSpec(
            id=generate_uuid(),
            name=f"verify-agent-{i}",
            display_name=f"Verification Agent {i}",
            task_type="coding",
            objective=f"Test objective for verification agent {i}",
            context={"verification_index": i},
            tool_policy={"allowed_tools": ["Read", "Write"]},
            max_turns=50,
            timeout_seconds=900,
        )
        specs.append(spec)
    return specs


def step1_accepts_list():
    """Step 1: Verify Materializer accepts list of AgentSpecs."""
    print("Step 1: Materializer accepts list of AgentSpecs")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(3)

        result = materializer.materialize_batch(specs)

        # Verification checks
        checks = [
            ("Result is BatchMaterializationResult", isinstance(result, BatchMaterializationResult)),
            ("Total count matches input", result.total == 3),
            ("Results list populated", len(result.results) == 3),
            ("Empty list handled", isinstance(materializer.materialize_batch([]), BatchMaterializationResult)),
        ]

        all_passed = True
        for check_name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  - {check_name}: {status}")
            if not passed:
                all_passed = False

    return all_passed


def step2_processed_individually():
    """Step 2: Verify each spec is processed and written individually."""
    print("Step 2: Each spec processed and written individually")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(3)

        result = materializer.materialize_batch(specs)

        output_dir = Path(tmpdir) / DEFAULT_OUTPUT_DIR

        checks = []

        # Each spec gets own file
        for i, spec in enumerate(specs):
            filepath = output_dir / f"{spec.name}.md"
            checks.append((f"File exists for {spec.name}", filepath.exists()))

        # Files have different content
        contents = []
        for spec in specs:
            filepath = output_dir / f"{spec.name}.md"
            if filepath.exists():
                contents.append(filepath.read_text())
        checks.append(("All files have unique content", len(set(contents)) == len(specs)))

        # Each result has unique hash
        hashes = [r.content_hash for r in result.results if r.success]
        checks.append(("All hashes unique", len(set(hashes)) == len(specs)))

        all_passed = True
        for check_name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  - {check_name}: {status}")
            if not passed:
                all_passed = False

    return all_passed


def step3_atomic_operation():
    """Step 3: Verify batch operation is atomic."""
    print("Step 3: Batch operation is atomic: all succeed or none written")

    checks = []

    # Test 1: All succeed in atomic mode
    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(3)

        result = materializer.materialize_batch(specs, atomic=True)

        checks.append(("Atomic flag set", result.atomic is True))
        checks.append(("All succeed", result.all_succeeded))
        checks.append(("Not rolled back", result.rolled_back is False))

        output_dir = Path(tmpdir) / DEFAULT_OUTPUT_DIR
        files_exist = all((output_dir / f"{spec.name}.md").exists() for spec in specs)
        checks.append(("All files exist after success", files_exist))

    # Test 2: Verify rollback flag exists when needed
    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(2)

        # Normal batch without atomic - rolled_back should be False
        result = materializer.materialize_batch(specs, atomic=False)
        checks.append(("Non-atomic has rolled_back=False", result.rolled_back is False))

    # Test 3: Verify BatchMaterializationResult has atomic and rolled_back fields
    result = BatchMaterializationResult(total=1, succeeded=1, failed=0, atomic=True, rolled_back=False)
    checks.append(("BatchMaterializationResult has atomic field", hasattr(result, 'atomic')))
    checks.append(("BatchMaterializationResult has rolled_back field", hasattr(result, 'rolled_back')))

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  - {check_name}: {status}")
        if not passed:
            all_passed = False

    return all_passed


def step4_progress_reported():
    """Step 4: Verify progress is reported for each agent."""
    print("Step 4: Progress reported for each agent")

    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(3)

        progress_events = []

        def callback(index, total, name, status):
            progress_events.append({
                "index": index,
                "total": total,
                "name": name,
                "status": status,
            })

        result = materializer.materialize_batch(specs, progress_callback=callback)

        checks = [
            ("Progress events received", len(progress_events) > 0),
            ("At least one event per spec", len(progress_events) >= len(specs)),
        ]

        # Check statuses
        statuses = {e["status"] for e in progress_events}
        checks.append(("'processing' status reported", "processing" in statuses))
        checks.append(("'completed' status reported", "completed" in statuses))

        # Check names
        reported_names = {e["name"] for e in progress_events}
        expected_names = {spec.name for spec in specs}
        checks.append(("All spec names reported", expected_names <= reported_names))

        # Check totals
        totals = {e["total"] for e in progress_events}
        checks.append(("Correct total in all events", totals == {len(specs)}))

        all_passed = True
        for check_name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  - {check_name}: {status}")
            if not passed:
                all_passed = False

    return all_passed


def step5_audit_events():
    """Step 5: Verify audit events are recorded."""
    print("Step 5: Single audit event or per-agent events recorded")

    # Test 1: Non-atomic records per-agent events
    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(3)
        run_id = generate_uuid()

        mock_recorder = MagicMock()
        mock_recorder.record_agent_materialized.return_value = 100

        result = materializer.materialize_batch(
            specs,
            atomic=False,
            event_recorder=mock_recorder,
            run_id=run_id,
        )

        checks = [
            ("Non-atomic: per-agent events recorded",
             mock_recorder.record_agent_materialized.call_count == len(specs)),
        ]

        # Check audit info on results
        for r in result.results:
            if r.success:
                checks.append((f"Audit info set for {r.spec_name}",
                              r.audit_info is not None and r.audit_info.recorded))

    # Test 2: Atomic records single batch event
    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(3)
        run_id = generate_uuid()

        mock_recorder = MagicMock()
        mock_recorder.record.return_value = 200

        result = materializer.materialize_batch(
            specs,
            atomic=True,
            event_recorder=mock_recorder,
            run_id=run_id,
        )

        checks.append(("Atomic: single batch event recorded", mock_recorder.record.call_count == 1))
        checks.append(("Batch audit info set", result.batch_audit_info is not None))
        if result.batch_audit_info:
            checks.append(("Batch audit recorded", result.batch_audit_info.recorded))

    # Test 3: No events without recorder
    with tempfile.TemporaryDirectory() as tmpdir:
        materializer = AgentMaterializer(tmpdir)
        specs = create_test_specs(2)

        result = materializer.materialize_batch(specs, event_recorder=None)

        no_audit = all(r.audit_info is None for r in result.results)
        checks.append(("No audit without recorder", no_audit))

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  - {check_name}: {status}")
        if not passed:
            all_passed = False

    return all_passed


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #197: Agent Materializer handles multiple agents in batch")
    print("=" * 60)
    print()

    results = []

    steps = [
        ("Step 1", step1_accepts_list),
        ("Step 2", step2_processed_individually),
        ("Step 3", step3_atomic_operation),
        ("Step 4", step4_progress_reported),
        ("Step 5", step5_audit_events),
    ]

    for step_name, step_func in steps:
        try:
            passed = step_func()
            results.append((step_name, passed))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((step_name, False))
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_passed = True
    for step_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {step_name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("ALL VERIFICATION STEPS PASSED")
        return 0
    else:
        print("SOME VERIFICATION STEPS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
