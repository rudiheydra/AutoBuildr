"""
Tests for Feature #206: Test-runner agent writes test code from TestContract

The test-runner agent receives TestContract and implements actual test code.

Verification Steps:
1. Test-runner receives TestContract with test requirements
2. Agent writes test files based on contract assertions
3. Tests placed in project's standard test directory
4. Test code follows project conventions (pytest, jest, etc.)
5. tests_written audit event recorded
"""
import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.test_code_writer import (
    # Data classes
    TestCodeWriteResult,
    TestCodeWriterAuditInfo,
    FrameworkDetectionResult,
    # Main class
    TestCodeWriter,
    # Convenience functions
    get_test_code_writer,
    reset_test_code_writer_cache,
    write_tests_from_contract,
    detect_test_framework,
    # Constants
    TEST_FRAMEWORKS,
    DEFAULT_FRAMEWORKS,
    TEST_DIR_PATTERNS,
    TEST_FILE_EXTENSIONS,
    PYTHON_ASSERTION_TEMPLATES,
    JS_ASSERTION_TEMPLATES,
)
from api.octo import TestContract, TestContractAssertion, generate_uuid
from api.agentspec_models import AgentSpec, AgentRun, AgentEvent, EVENT_TYPES
from api.database import Base
from api.event_recorder import EventRecorder, get_event_recorder, clear_recorder_cache


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Clear recorder cache to ensure fresh state
    clear_recorder_cache()
    reset_test_code_writer_cache()

    yield session

    session.close()
    clear_recorder_cache()
    reset_test_code_writer_cache()


@pytest.fixture
def test_code_writer(temp_project_dir):
    """TestCodeWriter instance with temp directory."""
    return TestCodeWriter(temp_project_dir)


@pytest.fixture
def sample_test_contract():
    """Sample TestContract for testing."""
    return TestContract(
        contract_id=generate_uuid(),
        agent_name="api-testing-agent",
        test_type="api",
        description="Test API endpoints for user authentication",
        assertions=[
            TestContractAssertion(
                description="Response status is 200",
                target="response.status_code",
                expected=200,
                operator="eq",
            ),
            TestContractAssertion(
                description="Response contains user data",
                target="response.body",
                expected="user",
                operator="contains",
            ),
        ],
        pass_criteria=[
            "All API endpoints return valid JSON",
            "Authentication succeeds with valid credentials",
        ],
        fail_criteria=[
            "Returns 401 for invalid credentials",
            "Leaks sensitive data in error messages",
        ],
        priority=2,
        tags=["api", "authentication"],
    )


@pytest.fixture
def e2e_test_contract():
    """E2E TestContract for browser testing."""
    return TestContract(
        contract_id=generate_uuid(),
        agent_name="e2e-testing-agent",
        test_type="e2e",
        description="End-to-end tests for login flow",
        assertions=[
            TestContractAssertion(
                description="Login page is accessible",
                target="page.url",
                expected="/login",
                operator="contains",
            ),
        ],
        pass_criteria=["User can log in successfully"],
        fail_criteria=["Login form shows error for empty input"],
        priority=1,
        tags=["e2e", "login"],
    )


@pytest.fixture
def sample_agent_spec():
    """Sample AgentSpec for testing."""
    return AgentSpec(
        id=generate_uuid(),
        name="feature-206-test-agent",
        display_name="Test Agent for Feature 206",
        spec_version="v1",
        objective="Test code writing from TestContract",
        task_type="testing",
        tool_policy={
            "policy_version": "v1",
            "allowed_tools": ["Read", "Write"],
            "forbidden_patterns": [],
        },
        max_turns=50,
        timeout_seconds=900,
    )


@pytest.fixture
def sample_agent_run(db_session, sample_agent_spec):
    """Sample AgentRun for linking events."""
    db_session.add(sample_agent_spec)
    db_session.flush()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=sample_agent_spec.id,
        status="running",
    )
    db_session.add(run)
    db_session.commit()

    return run


# =============================================================================
# Step 1: Test-runner receives TestContract with test requirements
# =============================================================================

class TestStep1ReceivesTestContract:
    """Verify TestCodeWriter can receive and process TestContract."""

    def test_writer_accepts_test_contract(self, test_code_writer, sample_test_contract):
        """TestCodeWriter accepts TestContract as input."""
        result = test_code_writer.write_tests(sample_test_contract)
        # Should process without error
        assert result.contract_id == sample_test_contract.contract_id
        assert result.agent_name == sample_test_contract.agent_name

    def test_writer_extracts_assertions(self, test_code_writer, sample_test_contract):
        """TestCodeWriter extracts assertions from TestContract."""
        result = test_code_writer.write_tests(sample_test_contract)
        # Should count assertions + pass_criteria + fail_criteria
        assert result.assertions_count > 0
        assert result.assertions_count >= len(sample_test_contract.assertions)

    def test_writer_handles_empty_assertions(self, test_code_writer):
        """TestCodeWriter handles TestContract with no assertions."""
        contract = TestContract(
            agent_name="minimal-test",
            test_type="unit",
            pass_criteria=["Basic test passes"],
        )
        result = test_code_writer.write_tests(contract)
        assert result.success
        assert result.assertions_count >= 1

    def test_writer_handles_contract_with_all_fields(self, test_code_writer, sample_test_contract):
        """TestCodeWriter processes contract with all optional fields."""
        assert sample_test_contract.description is not None
        assert len(sample_test_contract.tags) > 0
        assert sample_test_contract.priority > 0

        result = test_code_writer.write_tests(sample_test_contract)
        assert result.success


# =============================================================================
# Step 2: Agent writes test files based on contract assertions
# =============================================================================

class TestStep2WritesTestFiles:
    """Verify TestCodeWriter creates test files from assertions."""

    def test_writes_test_file(self, test_code_writer, sample_test_contract):
        """TestCodeWriter creates a test file."""
        result = test_code_writer.write_tests(sample_test_contract)
        assert result.success
        assert len(result.test_files) > 0
        assert all(f.exists() for f in result.test_files)

    def test_test_file_contains_assertions(self, test_code_writer, sample_test_contract):
        """Generated test file contains assertion code."""
        result = test_code_writer.write_tests(sample_test_contract)
        assert result.success

        test_content = result.test_files[0].read_text()
        # Should contain assertion-related code
        assert "assert" in test_content.lower() or "expect" in test_content.lower()

    def test_test_file_contains_pass_criteria(self, test_code_writer, sample_test_contract):
        """Generated test file contains tests for pass_criteria."""
        result = test_code_writer.write_tests(sample_test_contract)
        assert result.success

        test_content = result.test_files[0].read_text()
        # Should reference pass criteria
        for criterion in sample_test_contract.pass_criteria:
            # At least part of the criterion should be in the file
            assert any(word in test_content for word in criterion.split()[:3])

    def test_test_file_contains_fail_criteria(self, test_code_writer, sample_test_contract):
        """Generated test file contains negative tests for fail_criteria."""
        result = test_code_writer.write_tests(sample_test_contract)
        assert result.success

        test_content = result.test_files[0].read_text()
        # Should have negative test method names
        assert "NOT" in test_content or "fail_criterion" in test_content

    def test_content_hash_is_deterministic(self, test_code_writer, sample_test_contract):
        """Same contract produces same content hash."""
        result1 = test_code_writer.write_tests(sample_test_contract)
        result2 = test_code_writer.write_tests(sample_test_contract)

        assert result1.content_hash == result2.content_hash


# =============================================================================
# Step 3: Tests placed in project's standard test directory
# =============================================================================

class TestStep3StandardTestDirectory:
    """Verify tests are placed in the standard test directory."""

    def test_creates_tests_directory(self, temp_project_dir, sample_test_contract):
        """TestCodeWriter creates tests/ directory if missing."""
        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(sample_test_contract)

        assert result.success
        assert result.test_directory is not None
        assert result.test_directory.exists()

    def test_uses_existing_tests_directory(self, temp_project_dir, sample_test_contract):
        """TestCodeWriter uses existing tests/ directory."""
        tests_dir = temp_project_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / ".gitkeep").touch()

        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(sample_test_contract)

        assert result.success
        assert result.test_directory == tests_dir

    def test_respects_pytest_convention(self, temp_project_dir, sample_test_contract):
        """TestCodeWriter uses pytest test directory convention."""
        (temp_project_dir / "pytest.ini").write_text("[pytest]\n")

        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(sample_test_contract)

        assert result.success
        assert result.test_framework == "pytest"
        # Test file should start with test_
        assert result.test_files[0].name.startswith("test_")

    def test_respects_jest_convention(self, temp_project_dir):
        """TestCodeWriter uses jest test directory convention."""
        (temp_project_dir / "jest.config.js").write_text("module.exports = {};")
        tests_dir = temp_project_dir / "__tests__"
        tests_dir.mkdir()

        contract = TestContract(
            agent_name="js-test",
            test_type="unit",
            pass_criteria=["Tests pass"],
        )

        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(contract)

        assert result.success
        assert result.test_framework == "jest"

    def test_e2e_tests_prefer_playwright_directory(self, temp_project_dir, e2e_test_contract):
        """E2E tests use playwright test directory."""
        (temp_project_dir / "playwright.config.ts").write_text("export default {}")
        e2e_dir = temp_project_dir / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)

        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(e2e_test_contract)

        assert result.success
        assert result.test_framework == "playwright"


# =============================================================================
# Step 4: Test code follows project conventions (pytest, jest, etc.)
# =============================================================================

class TestStep4ProjectConventions:
    """Verify test code follows project conventions."""

    def test_detects_pytest_from_config(self, temp_project_dir):
        """Detects pytest from pytest.ini."""
        (temp_project_dir / "pytest.ini").write_text("[pytest]\n")
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework()
        assert result.framework == "pytest"
        assert result.confidence == 1.0

    def test_detects_pytest_from_pyproject(self, temp_project_dir):
        """Detects pytest from pyproject.toml."""
        (temp_project_dir / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework()
        assert result.framework == "pytest"
        assert result.confidence == 1.0

    def test_detects_jest_from_config(self, temp_project_dir):
        """Detects jest from jest.config.js."""
        (temp_project_dir / "jest.config.js").write_text("module.exports = {};")
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework()
        assert result.framework == "jest"
        assert result.confidence == 1.0

    def test_detects_framework_from_package_json(self, temp_project_dir):
        """Detects framework from package.json test script."""
        pkg = {"scripts": {"test": "jest --coverage"}}
        (temp_project_dir / "package.json").write_text(json.dumps(pkg))
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework()
        assert result.framework == "jest"
        assert result.confidence >= 0.9

    def test_detects_vitest_from_package_json(self, temp_project_dir):
        """Detects vitest from package.json test script."""
        pkg = {"scripts": {"test": "vitest run"}}
        (temp_project_dir / "package.json").write_text(json.dumps(pkg))
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework()
        assert result.framework == "vitest"
        assert result.confidence >= 0.9

    def test_detects_playwright_for_e2e(self, temp_project_dir):
        """Detects playwright for E2E test type."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework(test_type="e2e")
        assert result.framework == "playwright"

    def test_infers_from_tech_stack(self, temp_project_dir):
        """Infers framework from tech stack."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.detect_framework(tech_stack=["python", "fastapi"])
        assert result.framework == "pytest"

    def test_python_test_code_structure(self, test_code_writer, sample_test_contract):
        """Python test code has correct structure."""
        result = test_code_writer.write_tests(sample_test_contract, framework="pytest")
        content = result.test_files[0].read_text()

        # Should have docstring
        assert '"""' in content
        # Should have class definition
        assert "class Test" in content
        # Should have test methods
        assert "def test_" in content
        # Should have pytest import
        assert "import pytest" in content

    def test_javascript_test_code_structure(self, temp_project_dir):
        """JavaScript test code has correct structure."""
        (temp_project_dir / "jest.config.js").write_text("module.exports = {};")
        writer = TestCodeWriter(temp_project_dir)

        contract = TestContract(
            agent_name="js-test",
            test_type="unit",
            assertions=[
                TestContractAssertion(
                    description="Test example",
                    target="result",
                    expected=True,
                    operator="eq",
                ),
            ],
            pass_criteria=["Tests pass"],
        )

        result = writer.write_tests(contract, framework="jest")
        content = result.test_files[0].read_text()

        # Should have describe block
        assert "describe(" in content
        # Should have it/test blocks
        assert "it(" in content or "test(" in content
        # Should have expect assertions
        assert "expect(" in content


# =============================================================================
# Step 5: tests_written audit event recorded
# =============================================================================

class TestStep5AuditEventRecorded:
    """Verify tests_written audit event is recorded."""

    def test_tests_written_event_type_exists(self):
        """tests_written is a valid event type."""
        assert "tests_written" in EVENT_TYPES

    def test_event_recorder_has_convenience_method(self):
        """EventRecorder has record_tests_written method."""
        assert hasattr(EventRecorder, "record_tests_written")

    def test_write_tests_with_audit_records_event(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """write_tests_with_audit records audit event."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        assert result.success
        assert result.audit_info is not None
        assert result.audit_info.recorded
        assert result.audit_info.event_id is not None

    def test_audit_event_has_correct_type(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Audit event has event_type='tests_written'."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.event_type == "tests_written"

    def test_audit_event_includes_contract_id(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Audit event payload includes contract_id."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.payload["contract_id"] == sample_test_contract.contract_id

    def test_audit_event_includes_agent_name(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Audit event payload includes agent_name."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.payload["agent_name"] == sample_test_contract.agent_name

    def test_audit_event_includes_test_files(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Audit event payload includes test_files."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert "test_files" in event.payload
        assert len(event.payload["test_files"]) > 0

    def test_audit_event_includes_test_framework(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Audit event payload includes test_framework."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert "test_framework" in event.payload
        assert event.payload["test_framework"] in TEST_FRAMEWORKS

    def test_audit_event_includes_assertions_count(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Audit event payload includes assertions_count."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert "assertions_count" in event.payload
        assert event.payload["assertions_count"] > 0


# =============================================================================
# TestCodeWriterAuditInfo Tests
# =============================================================================

class TestTestCodeWriterAuditInfo:
    """Test TestCodeWriterAuditInfo dataclass."""

    def test_audit_info_creation(self):
        """TestCodeWriterAuditInfo can be created."""
        audit_info = TestCodeWriterAuditInfo(
            event_id=42,
            run_id="run-123",
            timestamp=datetime.now(timezone.utc),
            recorded=True,
        )

        assert audit_info.event_id == 42
        assert audit_info.run_id == "run-123"
        assert audit_info.recorded

    def test_audit_info_defaults(self):
        """TestCodeWriterAuditInfo has sensible defaults."""
        audit_info = TestCodeWriterAuditInfo()

        assert audit_info.event_id is None
        assert audit_info.run_id is None
        assert audit_info.timestamp is None
        assert audit_info.recorded is False
        assert audit_info.error is None

    def test_audit_info_to_dict(self):
        """TestCodeWriterAuditInfo converts to dict."""
        ts = datetime.now(timezone.utc)
        audit_info = TestCodeWriterAuditInfo(
            event_id=42,
            run_id="run-123",
            timestamp=ts,
            recorded=True,
        )

        d = audit_info.to_dict()

        assert d["event_id"] == 42
        assert d["run_id"] == "run-123"
        assert d["timestamp"] == ts.isoformat()
        assert d["recorded"] is True
        assert d["error"] is None


# =============================================================================
# TestCodeWriteResult Tests
# =============================================================================

class TestTestCodeWriteResult:
    """Test TestCodeWriteResult dataclass."""

    def test_result_creation(self, temp_project_dir):
        """TestCodeWriteResult can be created."""
        result = TestCodeWriteResult(
            contract_id="contract-123",
            agent_name="test-agent",
            success=True,
            test_files=[temp_project_dir / "test_example.py"],
            test_framework="pytest",
            test_directory=temp_project_dir,
            assertions_count=5,
        )

        assert result.contract_id == "contract-123"
        assert result.agent_name == "test-agent"
        assert result.success
        assert len(result.test_files) == 1

    def test_result_to_dict(self, temp_project_dir):
        """TestCodeWriteResult converts to dict."""
        result = TestCodeWriteResult(
            contract_id="contract-123",
            agent_name="test-agent",
            success=True,
            test_files=[temp_project_dir / "test_example.py"],
            test_framework="pytest",
            test_directory=temp_project_dir,
            assertions_count=5,
        )

        d = result.to_dict()

        assert d["contract_id"] == "contract-123"
        assert d["agent_name"] == "test-agent"
        assert d["success"] is True
        assert d["test_framework"] == "pytest"
        assert d["assertions_count"] == 5


# =============================================================================
# FrameworkDetectionResult Tests
# =============================================================================

class TestFrameworkDetectionResult:
    """Test FrameworkDetectionResult dataclass."""

    def test_result_creation(self, temp_project_dir):
        """FrameworkDetectionResult can be created."""
        result = FrameworkDetectionResult(
            framework="pytest",
            confidence=0.9,
            reason="pytest.ini found",
            test_directory=temp_project_dir / "tests",
        )

        assert result.framework == "pytest"
        assert result.confidence == 0.9
        assert "pytest.ini" in result.reason


# =============================================================================
# Convenience Functions Tests
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_test_code_writer(self, temp_project_dir):
        """get_test_code_writer returns cached instance."""
        reset_test_code_writer_cache()

        writer1 = get_test_code_writer(temp_project_dir)
        writer2 = get_test_code_writer(temp_project_dir)

        assert writer1 is writer2

    def test_write_tests_from_contract(self, temp_project_dir, sample_test_contract):
        """write_tests_from_contract convenience function works."""
        result = write_tests_from_contract(
            sample_test_contract,
            temp_project_dir,
        )

        assert result.success
        assert len(result.test_files) > 0

    def test_detect_test_framework(self, temp_project_dir):
        """detect_test_framework convenience function works."""
        result = detect_test_framework(
            temp_project_dir,
            test_type="unit",
        )

        assert result.framework in TEST_FRAMEWORKS


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Test module constants."""

    def test_test_frameworks(self):
        """TEST_FRAMEWORKS contains expected frameworks."""
        assert "pytest" in TEST_FRAMEWORKS
        assert "jest" in TEST_FRAMEWORKS
        assert "playwright" in TEST_FRAMEWORKS

    def test_default_frameworks(self):
        """DEFAULT_FRAMEWORKS maps languages to frameworks."""
        assert DEFAULT_FRAMEWORKS["python"] == "pytest"
        assert DEFAULT_FRAMEWORKS["javascript"] == "jest"

    def test_test_dir_patterns(self):
        """TEST_DIR_PATTERNS has patterns for each framework."""
        for framework in ["pytest", "jest", "playwright"]:
            assert framework in TEST_DIR_PATTERNS
            assert len(TEST_DIR_PATTERNS[framework]) > 0

    def test_assertion_templates(self):
        """Assertion templates exist for common operators."""
        for operator in ["eq", "ne", "gt", "lt", "contains"]:
            assert operator in PYTHON_ASSERTION_TEMPLATES
            assert operator in JS_ASSERTION_TEMPLATES


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for Feature #206."""

    def test_full_flow_with_audit(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Full flow: receive contract, write tests, record audit event."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        # Verify result
        assert result.success
        assert len(result.test_files) > 0
        assert all(f.exists() for f in result.test_files)
        assert result.assertions_count > 0

        # Verify audit event
        assert result.audit_info is not None
        assert result.audit_info.recorded

        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event.event_type == "tests_written"
        assert event.payload["contract_id"] == sample_test_contract.contract_id
        assert event.payload["agent_name"] == sample_test_contract.agent_name
        assert len(event.payload["test_files"]) > 0

    def test_multiple_contracts(self, temp_project_dir):
        """Can write tests for multiple contracts."""
        writer = TestCodeWriter(temp_project_dir)

        contracts = [
            TestContract(
                agent_name=f"test-agent-{i}",
                test_type="unit",
                pass_criteria=[f"Test {i} passes"],
            )
            for i in range(3)
        ]

        results = [writer.write_tests(c) for c in contracts]

        assert all(r.success for r in results)
        assert len(set(r.test_files[0] for r in results)) == 3  # All different files


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_handles_invalid_project_dir(self):
        """Handles non-existent project directory gracefully."""
        writer = TestCodeWriter("/nonexistent/path")
        contract = TestContract(
            agent_name="test",
            test_type="unit",
            pass_criteria=["test"],
        )

        # Should fail gracefully, not crash
        result = writer.write_tests(contract)
        # May fail or succeed depending on whether it can create the dir
        assert result.contract_id == contract.contract_id

    def test_handles_special_characters_in_agent_name(self, test_code_writer):
        """Handles special characters in agent name."""
        contract = TestContract(
            agent_name="test-agent_v2.0!@#$",
            test_type="unit",
            pass_criteria=["test"],
        )

        result = test_code_writer.write_tests(contract)
        assert result.success
        # Filename should be sanitized
        assert "!" not in result.test_files[0].name
        assert "@" not in result.test_files[0].name

    def test_handles_very_long_assertions(self, test_code_writer):
        """Handles very long assertion descriptions."""
        long_desc = "This is a very long assertion description " * 20
        contract = TestContract(
            agent_name="test",
            test_type="unit",
            assertions=[
                TestContractAssertion(
                    description=long_desc,
                    target="result",
                    expected=True,
                    operator="eq",
                ),
            ],
            pass_criteria=["test"],
        )

        result = test_code_writer.write_tests(contract)
        assert result.success


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Test that Feature #206 components are exported from api package."""

    def test_test_code_write_result_exported(self):
        """TestCodeWriteResult is exported from api package."""
        from api import TestCodeWriteResult

        result = TestCodeWriteResult(
            contract_id="test",
            agent_name="test",
        )
        assert result.success is False

    def test_test_code_writer_exported(self):
        """TestCodeWriter is exported from api package."""
        from api import TestCodeWriter

        assert TestCodeWriter is not None

    def test_convenience_functions_exported(self):
        """Convenience functions are exported from api package."""
        from api import (
            get_test_code_writer,
            reset_test_code_writer_cache,
            write_tests_from_contract,
            detect_test_framework,
        )

        assert callable(get_test_code_writer)
        assert callable(write_tests_from_contract)
        assert callable(detect_test_framework)

    def test_constants_exported(self):
        """Constants are exported from api package."""
        from api import (
            TEST_FRAMEWORKS,
            DEFAULT_FRAMEWORKS,
            TEST_DIR_PATTERNS,
            TEST_FILE_EXTENSIONS,
        )

        assert "pytest" in TEST_FRAMEWORKS
        assert "python" in DEFAULT_FRAMEWORKS


# =============================================================================
# Feature Verification Steps Summary
# =============================================================================

class TestFeature206VerificationSteps:
    """
    Comprehensive tests for all 5 verification steps of Feature #206.
    """

    def test_step1_receives_test_contract(self, test_code_writer, sample_test_contract):
        """Step 1: Test-runner receives TestContract with test requirements."""
        result = test_code_writer.write_tests(sample_test_contract)

        # Can receive and process TestContract
        assert result.contract_id == sample_test_contract.contract_id
        # Has access to assertions
        assert result.assertions_count >= len(sample_test_contract.assertions)

    def test_step2_writes_test_files(self, test_code_writer, sample_test_contract):
        """Step 2: Agent writes test files based on contract assertions."""
        result = test_code_writer.write_tests(sample_test_contract)

        assert result.success
        assert len(result.test_files) > 0
        assert all(f.exists() for f in result.test_files)

        # Test file contains assertion-based tests
        content = result.test_files[0].read_text()
        assert "def test_" in content or "it(" in content

    def test_step3_standard_test_directory(self, temp_project_dir, sample_test_contract):
        """Step 3: Tests placed in project's standard test directory."""
        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(sample_test_contract)

        assert result.success
        assert result.test_directory is not None
        # Should be under project directory
        assert str(result.test_directory).startswith(str(temp_project_dir))
        # Should follow convention (tests/, __tests__, etc.)
        assert any(
            pattern in str(result.test_directory)
            for patterns in TEST_DIR_PATTERNS.values()
            for pattern in patterns
        )

    def test_step4_follows_project_conventions(self, temp_project_dir, sample_test_contract):
        """Step 4: Test code follows project conventions (pytest, jest, etc.)."""
        # Create pytest project
        (temp_project_dir / "pytest.ini").write_text("[pytest]\n")

        writer = TestCodeWriter(temp_project_dir)
        result = writer.write_tests(sample_test_contract)

        assert result.success
        assert result.test_framework == "pytest"
        # Follows pytest naming convention
        assert result.test_files[0].name.startswith("test_")
        assert result.test_files[0].suffix == ".py"

    def test_step5_audit_event_recorded(
        self, db_session, temp_project_dir, sample_test_contract, sample_agent_run
    ):
        """Step 5: tests_written audit event recorded."""
        writer = TestCodeWriter(temp_project_dir)

        result = writer.write_tests_with_audit(
            contract=sample_test_contract,
            session=db_session,
            run_id=sample_agent_run.id,
        )

        assert result.success
        assert result.audit_info is not None
        assert result.audit_info.recorded

        # Event exists in database
        event = db_session.query(AgentEvent).filter(
            AgentEvent.id == result.audit_info.event_id
        ).first()

        assert event is not None
        assert event.event_type == "tests_written"
        assert event.run_id == sample_agent_run.id
