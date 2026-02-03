#!/usr/bin/env python3
"""
Standalone verification script for Feature #206:
Test-runner agent writes test code from TestContract

This script verifies all 5 feature steps:
1. Test-runner receives TestContract with test requirements
2. Agent writes test files based on contract assertions
3. Tests placed in project's standard test directory
4. Test code follows project conventions (pytest, jest, etc.)
5. tests_written audit event recorded

Run with: python tests/verify_feature_206.py
"""
import sys
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.test_code_writer import (
    TestCodeWriter,
    TestCodeWriteResult,
    TestCodeWriterAuditInfo,
    FrameworkDetectionResult,
    get_test_code_writer,
    write_tests_from_contract,
    detect_test_framework,
    TEST_FRAMEWORKS,
    DEFAULT_FRAMEWORKS,
    TEST_DIR_PATTERNS,
)
from api.octo import TestContract, TestContractAssertion, generate_uuid
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent, EVENT_TYPES
from api.database import Base
from api.event_recorder import clear_recorder_cache


def create_test_session():
    """Create an in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    clear_recorder_cache()
    return session


def create_sample_contract():
    """Create a sample TestContract for verification."""
    return TestContract(
        contract_id=generate_uuid(),
        agent_name="verification-test-agent",
        test_type="api",
        description="Verification tests for Feature #206",
        assertions=[
            TestContractAssertion(
                description="Response status is 200",
                target="response.status_code",
                expected=200,
                operator="eq",
            ),
            TestContractAssertion(
                description="Response contains data",
                target="response.body",
                expected="data",
                operator="contains",
            ),
        ],
        pass_criteria=[
            "All API endpoints return valid JSON",
            "Authentication succeeds with valid credentials",
        ],
        fail_criteria=[
            "Returns 401 for invalid credentials",
        ],
        priority=2,
        tags=["api", "verification"],
    )


def create_sample_run(session, temp_dir):
    """Create a sample AgentRun for testing."""
    spec = AgentSpec(
        id=generate_uuid(),
        name="feature-206-verification-agent",
        display_name="Verification Agent",
        spec_version="v1",
        objective="Verify Feature #206",
        task_type="testing",
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write"],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=900,
    )
    session.add(spec)
    session.flush()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="running",
    )
    session.add(run)
    session.commit()
    return run


def verify_step1(contract, writer):
    """Step 1: Test-runner receives TestContract with test requirements."""
    print("\n" + "=" * 60)
    print("Step 1: Test-runner receives TestContract with test requirements")
    print("=" * 60)

    result = writer.write_tests(contract)

    checks = [
        ("Contract ID extracted", result.contract_id == contract.contract_id),
        ("Agent name extracted", result.agent_name == contract.agent_name),
        ("Assertions processed", result.assertions_count >= len(contract.assertions)),
        ("Result is TestCodeWriteResult", isinstance(result, TestCodeWriteResult)),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step2(contract, writer):
    """Step 2: Agent writes test files based on contract assertions."""
    print("\n" + "=" * 60)
    print("Step 2: Agent writes test files based on contract assertions")
    print("=" * 60)

    result = writer.write_tests(contract)

    checks = [
        ("Write operation succeeded", result.success),
        ("Test file created", len(result.test_files) > 0),
        ("Test file exists on disk", all(f.exists() for f in result.test_files)),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if not passed:
            all_passed = False

    if result.success and result.test_files:
        content = result.test_files[0].read_text()
        content_checks = [
            ("Contains assertion code", "assert" in content.lower() or "expect" in content.lower()),
            ("Contains test methods", "def test_" in content or "it(" in content),
            ("Has content hash", result.content_hash is not None),
        ]

        for check_name, passed in content_checks:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {check_name}")
            if not passed:
                all_passed = False

    return all_passed


def verify_step3(contract, temp_dir):
    """Step 3: Tests placed in project's standard test directory."""
    print("\n" + "=" * 60)
    print("Step 3: Tests placed in project's standard test directory")
    print("=" * 60)

    writer = TestCodeWriter(temp_dir)
    result = writer.write_tests(contract)

    checks = [
        ("Test directory created", result.test_directory is not None),
        ("Test directory exists", result.test_directory and result.test_directory.exists()),
        ("Directory under project", str(result.test_directory).startswith(str(temp_dir)) if result.test_directory else False),
    ]

    # Check convention patterns
    matches_convention = False
    if result.test_directory:
        for patterns in TEST_DIR_PATTERNS.values():
            for pattern in patterns:
                if pattern in str(result.test_directory):
                    matches_convention = True
                    break
    checks.append(("Follows directory convention", matches_convention))

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step4(temp_dir):
    """Step 4: Test code follows project conventions (pytest, jest, etc.)."""
    print("\n" + "=" * 60)
    print("Step 4: Test code follows project conventions (pytest, jest, etc.)")
    print("=" * 60)

    # Create pytest configuration
    (temp_dir / "pytest.ini").write_text("[pytest]\n")

    writer = TestCodeWriter(temp_dir)

    # Detect framework
    detection = writer.detect_framework()

    contract = TestContract(
        agent_name="convention-test",
        test_type="unit",
        pass_criteria=["Convention test"],
    )

    result = writer.write_tests(contract)

    checks = [
        ("Framework detected as pytest", detection.framework == "pytest"),
        ("High confidence detection", detection.confidence >= 0.9),
        ("Result uses detected framework", result.test_framework == "pytest"),
        ("File has .py extension", result.test_files[0].suffix == ".py" if result.test_files else False),
        ("File starts with test_", result.test_files[0].name.startswith("test_") if result.test_files else False),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if not passed:
            all_passed = False

    # Test JavaScript detection too
    js_temp = temp_dir / "js_project"
    js_temp.mkdir()
    (js_temp / "jest.config.js").write_text("module.exports = {};")

    js_writer = TestCodeWriter(js_temp)
    js_detection = js_writer.detect_framework()

    js_checks = [
        ("Jest framework detected", js_detection.framework == "jest"),
    ]

    for check_name, passed in js_checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if not passed:
            all_passed = False

    return all_passed


def verify_step5(contract, temp_dir, session, run):
    """Step 5: tests_written audit event recorded."""
    print("\n" + "=" * 60)
    print("Step 5: tests_written audit event recorded")
    print("=" * 60)

    writer = TestCodeWriter(temp_dir)

    result = writer.write_tests_with_audit(
        contract=contract,
        session=session,
        run_id=run.id,
    )

    checks = [
        ("tests_written in EVENT_TYPES", "tests_written" in EVENT_TYPES),
        ("Write succeeded", result.success),
        ("Audit info populated", result.audit_info is not None),
        ("Audit recorded", result.audit_info.recorded if result.audit_info else False),
        ("Event ID assigned", result.audit_info.event_id is not None if result.audit_info else False),
    ]

    all_passed = True
    for check_name, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if not passed:
            all_passed = False

    # Verify event in database
    if result.audit_info and result.audit_info.event_id:
        event = session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        event_checks = [
            ("Event exists in database", event is not None),
            ("Event type is tests_written", event.event_type == "tests_written" if event else False),
            ("Event linked to run", event.run_id == run.id if event else False),
            ("Payload has contract_id", "contract_id" in event.payload if event else False),
            ("Payload has agent_name", "agent_name" in event.payload if event else False),
            ("Payload has test_files", "test_files" in event.payload if event else False),
            ("Payload has test_framework", "test_framework" in event.payload if event else False),
            ("Payload has assertions_count", "assertions_count" in event.payload if event else False),
        ]

        for check_name, passed in event_checks:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {check_name}")
            if not passed:
                all_passed = False

    return all_passed


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #206 Verification Script")
    print("Test-runner agent writes test code from TestContract")
    print("=" * 60)

    # Set up test environment
    with tempfile.TemporaryDirectory() as temp_str:
        temp_dir = Path(temp_str)
        session = create_test_session()
        contract = create_sample_contract()
        run = create_sample_run(session, temp_dir)
        writer = TestCodeWriter(temp_dir)

        results = []

        # Run all verification steps
        results.append(("Step 1", verify_step1(contract, writer)))

        # Create fresh temp dir for step 2
        step2_dir = temp_dir / "step2"
        step2_dir.mkdir()
        writer2 = TestCodeWriter(step2_dir)
        results.append(("Step 2", verify_step2(contract, writer2)))

        step3_dir = temp_dir / "step3"
        step3_dir.mkdir()
        results.append(("Step 3", verify_step3(contract, step3_dir)))

        step4_dir = temp_dir / "step4"
        step4_dir.mkdir()
        results.append(("Step 4", verify_step4(step4_dir)))

        step5_dir = temp_dir / "step5"
        step5_dir.mkdir()
        results.append(("Step 5", verify_step5(contract, step5_dir, session, run)))

        # Summary
        print("\n" + "=" * 60)
        print("VERIFICATION SUMMARY")
        print("=" * 60)

        all_passed = True
        for step_name, passed in results:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {step_name}")
            if not passed:
                all_passed = False

        print("")
        if all_passed:
            print("OVERALL: ALL STEPS PASSED")
            return 0
        else:
            print("OVERALL: SOME STEPS FAILED")
            return 1


if __name__ == "__main__":
    sys.exit(main())
