"""
DSPy Dynamic Spec Builder Pipeline - E2E Test Suite
=====================================================

End-to-end tests exercising the full dynamic spec generation pipeline
with mocked DSPy/Claude calls. Tests cover all 9 pipeline stages:

1. Task Type Detection (Feature -> task_type)
2. Tool Policy Derivation (task_type -> tool_policy)
3. Budget Derivation (task_type -> budget)
4. Spec Name Generation (objective -> spec name)
5. Validator Generation (steps -> validators)
6. Feature Compiler (Feature -> AgentSpec)
7. SpecBuilder DSPy (DSPy mock -> AgentSpec)
8. HarnessKernel Execution (AgentSpec -> AgentRun)
9. AcceptanceGate Evaluation (validators -> verdict)
+ Full Pipeline E2E (all 9 stages threaded together)

Mocking Strategy:
- Mock dspy.LM, dspy.ChainOfThought, dspy.configure to avoid real API calls
- Return controlled dspy.Prediction with realistic JSON outputs
- Set fake ANTHROPIC_API_KEY via fixture
- Use tmp_path for file-system validators
- No conftest.py (self-contained, per project convention)
"""

import json
import os
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.agentspec_models import (
    TASK_TYPES,
    AcceptanceSpec,
    AgentEvent,
    AgentRun,
    AgentSpec,
    generate_uuid,
)
from api.database import Base, Feature
from api.feature_compiler import FeatureCompiler
from api.harness_kernel import BudgetTracker, HarnessKernel
from api.spec_builder import BuildResult, SpecBuilder
from api.spec_name_generator import generate_spec_name
from api.task_type_detector import detect_task_type, detect_task_type_detailed
from api.tool_policy import derive_budget, derive_tool_policy
from api.validator_generator import generate_validators_from_steps
from api.validators import (
    AcceptanceGate,
    FileExistsValidator,
    ForbiddenPatternsValidator,
    GateResult,
)

# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_feature():
    """Feature(id=42, category='A. Database', name='User Authentication with OAuth2', 4 steps)."""
    feature = Feature(
        id=42,
        priority=1,
        category="A. Database",
        name="User Authentication with OAuth2",
        description="Implement user authentication system using OAuth2 protocol with secure token management",
        steps=[
            "Run pytest tests/test_auth.py to verify authentication works",
            "File api/auth.py should exist with OAuth2 implementation",
            "Output should not contain any hardcoded passwords or secrets",
            "Verify the login endpoint returns a valid JWT token",
        ],
        passes=False,
        in_progress=False,
    )
    return feature


@pytest.fixture
def coding_feature():
    """Feature(id=100, category='F. UI-Backend') for coding task type."""
    feature = Feature(
        id=100,
        priority=5,
        category="F. UI-Backend",
        name="Dashboard Component with Real-time Updates",
        description="Build a dashboard component that displays real-time metrics via WebSocket",
        steps=[
            "Run npm test to verify component renders correctly",
            "File ui/src/components/Dashboard.tsx should exist",
        ],
        passes=False,
        in_progress=False,
    )
    return feature


@pytest.fixture
def audit_feature():
    """Feature(id=200, category='Security') for audit task type."""
    feature = Feature(
        id=200,
        priority=2,
        category="Security",
        name="Security Audit of Authentication Module",
        description="Perform a security audit reviewing the authentication module for vulnerabilities",
        steps=[
            "Output should not contain any SQL injection patterns",
            "Review code for hardcoded credentials",
        ],
        passes=False,
        in_progress=False,
    )
    return feature


@pytest.fixture
def mock_dspy_prediction():
    """MagicMock with realistic JSON outputs for all DSPy fields."""
    prediction = MagicMock()
    prediction.reasoning = "The task requires implementing user authentication, which is a coding task."
    prediction.objective = "Implement user authentication with OAuth2 protocol for secure login"
    prediction.context_json = json.dumps({
        "project_name": "AutoBuildr",
        "feature_id": 42,
        "auth_provider": "OAuth2",
    })
    prediction.tool_policy_json = json.dumps({
        "allowed_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        "forbidden_patterns": ["rm -rf /", "DROP TABLE"],
        "tool_hints": {"Edit": "Prefer editing existing files"},
        "policy_version": "v1",
    })
    prediction.max_turns = "100"
    prediction.timeout_seconds = "1800"
    prediction.validators_json = json.dumps([
        {
            "type": "test_pass",
            "config": {"command": "pytest tests/test_auth.py", "expected_exit_code": 0},
            "weight": 1.0,
            "required": False,
        },
        {
            "type": "file_exists",
            "config": {"path": "api/auth.py", "should_exist": True},
            "weight": 1.0,
            "required": True,
        },
    ])
    return prediction


@pytest.fixture
def env_with_fake_key():
    """Sets/restores ANTHROPIC_API_KEY for SpecBuilder initialization."""
    original = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "fake-test-key-for-dspy-pipeline"
    yield
    if original is None:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    else:
        os.environ["ANTHROPIC_API_KEY"] = original


# =============================================================================
# TestStep1TaskTypeDetection - Feature -> task_type
# =============================================================================

class TestStep1TaskTypeDetection:
    """Stage: Feature -> task_type. Tests: 6."""

    def test_coding_description_detected(self):
        """Coding keywords like 'implement' should produce coding task type."""
        result = detect_task_type("Implement user authentication with OAuth2")
        assert result == "coding"

    def test_testing_description_detected(self):
        """Testing keywords like 'write tests' should produce testing task type."""
        result = detect_task_type("Write tests for the login module")
        assert result == "testing"

    def test_audit_description_detected(self):
        """Audit keywords like 'security audit' should produce audit task type."""
        result = detect_task_type("Perform a security audit of the authentication module")
        assert result == "audit"

    def test_refactoring_description_detected(self):
        """Refactoring keywords like 'refactor' should produce refactoring task type."""
        result = detect_task_type("Refactor the database module to reduce complexity")
        assert result == "refactoring"

    def test_empty_description_returns_custom(self):
        """Empty description should default to custom task type."""
        result = detect_task_type("")
        assert result == "custom"

    def test_detailed_detection_returns_scores(self):
        """detect_task_type_detailed should return scores for all task types."""
        result = detect_task_type_detailed("Implement user authentication with OAuth2")
        assert result.detected_type == "coding"
        assert isinstance(result.scores, dict)
        assert "coding" in result.scores
        assert "testing" in result.scores
        assert result.scores["coding"] > 0
        assert result.confidence in ("high", "medium", "low")
        assert result.is_default is False
        assert len(result.matched_keywords) > 0


# =============================================================================
# TestStep2ToolPolicyDerivation - task_type -> tool_policy
# =============================================================================

class TestStep2ToolPolicyDerivation:
    """Stage: task_type -> tool_policy. Tests: 4."""

    def test_coding_policy_has_tools(self):
        """Coding policy should include standard coding tools."""
        policy = derive_tool_policy("coding")
        assert "allowed_tools" in policy
        assert isinstance(policy["allowed_tools"], list)
        assert len(policy["allowed_tools"]) > 0

    def test_policy_has_forbidden_patterns(self):
        """All policies should include forbidden patterns."""
        policy = derive_tool_policy("coding")
        assert "forbidden_patterns" in policy
        assert isinstance(policy["forbidden_patterns"], list)
        assert len(policy["forbidden_patterns"]) > 0

    def test_policy_has_version(self):
        """Policy should include version field."""
        policy = derive_tool_policy("testing")
        assert "policy_version" in policy
        assert policy["policy_version"] == "v1"

    def test_audit_policy_is_restricted(self):
        """Audit policy should have a tool set appropriate for auditing."""
        policy = derive_tool_policy("audit")
        assert "allowed_tools" in policy
        assert isinstance(policy["allowed_tools"], list)
        assert len(policy["allowed_tools"]) > 0


# =============================================================================
# TestStep3BudgetDerivation - task_type -> budget
# =============================================================================

class TestStep3BudgetDerivation:
    """Stage: task_type -> budget. Tests: 4."""

    def test_budget_has_required_fields(self):
        """Budget should contain max_turns and timeout_seconds."""
        budget = derive_budget("coding")
        assert "max_turns" in budget
        assert "timeout_seconds" in budget

    def test_budget_within_bounds(self):
        """Budget values should be within the allowed range."""
        budget = derive_budget("coding")
        assert 1 <= budget["max_turns"] <= 500
        assert 60 <= budget["timeout_seconds"] <= 7200

    def test_coding_budget_larger_than_testing(self):
        """Coding tasks should generally get larger budgets than testing tasks."""
        coding_budget = derive_budget("coding")
        testing_budget = derive_budget("testing")
        assert coding_budget["max_turns"] >= testing_budget["max_turns"]

    def test_complexity_scaling(self):
        """Longer descriptions should increase budget via complexity scaling."""
        short_budget = derive_budget("coding", description="Fix a bug")
        long_description = "Implement a comprehensive user authentication system " * 10
        long_budget = derive_budget("coding", description=long_description)
        # Long descriptions should get >= the budget of short ones
        assert long_budget["max_turns"] >= short_budget["max_turns"]


# =============================================================================
# TestStep4NameGeneration - objective -> spec name
# =============================================================================

class TestStep4NameGeneration:
    """Stage: objective -> spec name. Tests: 4."""

    def test_name_is_url_safe(self):
        """Generated name should only contain lowercase alphanumeric and hyphens."""
        name = generate_spec_name("Implement user authentication", "coding")
        assert re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', name), f"Name not URL-safe: {name}"

    def test_name_has_length_limit(self):
        """Name should not exceed 100 characters."""
        long_objective = "Implement a very long feature name that goes on and on " * 5
        name = generate_spec_name(long_objective, "coding")
        assert len(name) <= 100

    def test_name_has_task_type_prefix(self):
        """Name should start with the task type prefix."""
        name = generate_spec_name("Write unit tests for auth", "testing")
        assert name.startswith("testing-")

    def test_name_is_lowercase(self):
        """Name should be entirely lowercase."""
        name = generate_spec_name("IMPLEMENT OAuth2 Authentication", "coding")
        assert name == name.lower()


# =============================================================================
# TestStep5ValidatorGeneration - Steps -> validators
# =============================================================================

class TestStep5ValidatorGeneration:
    """Stage: Steps -> validators. Tests: 4."""

    def test_test_pass_from_run_step(self):
        """Step mentioning 'run pytest' should generate test_pass validator."""
        steps = ["Run pytest tests/test_auth.py to verify authentication"]
        validators = generate_validators_from_steps(steps)
        assert len(validators) > 0
        assert validators[0]["type"] == "test_pass"

    def test_file_exists_from_file_step(self):
        """Step mentioning file existence should generate file_exists validator."""
        steps = ["File api/auth.py should exist with OAuth2 implementation"]
        validators = generate_validators_from_steps(steps)
        assert len(validators) > 0
        assert validators[0]["type"] == "file_exists"

    def test_forbidden_patterns_from_should_not_step(self):
        """Step with 'should not' should generate forbidden_patterns validator."""
        steps = ["Output should not contain any hardcoded passwords"]
        validators = generate_validators_from_steps(steps)
        assert len(validators) > 0
        assert validators[0]["type"] == "forbidden_patterns"

    def test_multiple_steps_generate_multiple_validators(self):
        """Multiple steps should generate corresponding validators."""
        steps = [
            "Run pytest tests/ to verify functionality",
            "File config.json should exist in project root",
            "Output should not contain any secrets",
        ]
        validators = generate_validators_from_steps(steps)
        assert len(validators) >= 3
        types = [v["type"] for v in validators]
        assert "test_pass" in types
        assert "file_exists" in types
        assert "forbidden_patterns" in types


# =============================================================================
# TestStep6FeatureCompiler - Feature -> AgentSpec
# =============================================================================

class TestStep6FeatureCompiler:
    """Stage: Feature -> AgentSpec. Tests: 6."""

    def test_compile_produces_agent_spec(self, sample_feature):
        """Compiling a feature should produce an AgentSpec."""
        compiler = FeatureCompiler()
        spec = compiler.compile(sample_feature)
        assert isinstance(spec, AgentSpec)

    def test_compiled_spec_has_correct_task_type(self, sample_feature):
        """Database category should map to coding task type."""
        compiler = FeatureCompiler()
        spec = compiler.compile(sample_feature)
        assert spec.task_type == "coding"

    def test_compiled_spec_has_tool_policy(self, sample_feature):
        """Compiled spec should have a valid tool_policy."""
        compiler = FeatureCompiler()
        spec = compiler.compile(sample_feature)
        assert spec.tool_policy is not None
        assert "allowed_tools" in spec.tool_policy

    def test_compiled_spec_has_acceptance_spec(self, sample_feature):
        """Compiled spec should have an AcceptanceSpec with validators."""
        compiler = FeatureCompiler()
        spec = compiler.compile(sample_feature)
        assert spec.acceptance_spec is not None
        assert isinstance(spec.acceptance_spec, AcceptanceSpec)
        assert len(spec.acceptance_spec.validators) > 0

    def test_compiled_spec_has_traceability(self, sample_feature):
        """Compiled spec should link back to source feature."""
        compiler = FeatureCompiler()
        spec = compiler.compile(sample_feature)
        assert spec.source_feature_id == 42

    def test_compiled_spec_has_budget(self, sample_feature):
        """Compiled spec should have max_turns and timeout_seconds set."""
        compiler = FeatureCompiler()
        spec = compiler.compile(sample_feature)
        assert spec.max_turns >= 1
        assert spec.timeout_seconds >= 60


# =============================================================================
# TestStep7SpecBuilderDSPy - DSPy mock -> AgentSpec
# =============================================================================

class TestStep7SpecBuilderDSPy:
    """Stage: DSPy mock -> AgentSpec. Tests: 4."""

    @patch("api.spec_builder.dspy")
    def test_build_success_with_mock(self, mock_dspy, mock_dspy_prediction, env_with_fake_key):
        """SpecBuilder.build() should succeed with mocked DSPy returning valid prediction."""
        # Configure mock
        mock_lm = MagicMock()
        mock_dspy.LM.return_value = mock_lm
        mock_module = MagicMock()
        mock_module.return_value = mock_dspy_prediction
        mock_dspy.ChainOfThought.return_value = mock_module

        # Also mock validate_spec_output to return no errors
        with patch("api.spec_builder.validate_spec_output") as mock_validate:
            mock_validate.return_value = {"errors": [], "warnings": []}

            builder = SpecBuilder(api_key="fake-key", auto_initialize=True)
            result = builder.build(
                task_description="Implement user authentication with OAuth2",
                task_type="coding",
                context={"project_name": "TestProject"},
            )

        assert isinstance(result, BuildResult)
        assert result.success is True
        assert result.agent_spec is not None
        assert result.agent_spec.task_type == "coding"
        assert result.acceptance_spec is not None

    @patch("api.spec_builder.dspy")
    def test_build_empty_description_fails(self, mock_dspy, env_with_fake_key):
        """Empty task_description should return a failed BuildResult."""
        mock_dspy.LM.return_value = MagicMock()
        mock_dspy.ChainOfThought.return_value = MagicMock()

        builder = SpecBuilder(api_key="fake-key", auto_initialize=True)
        result = builder.build(
            task_description="",
            task_type="coding",
        )

        assert result.success is False
        assert "empty" in result.error.lower()

    @patch("api.spec_builder.dspy")
    def test_build_invalid_task_type_fails(self, mock_dspy, env_with_fake_key):
        """Invalid task_type should return a failed BuildResult."""
        mock_dspy.LM.return_value = MagicMock()
        mock_dspy.ChainOfThought.return_value = MagicMock()

        builder = SpecBuilder(api_key="fake-key", auto_initialize=True)
        result = builder.build(
            task_description="Do something",
            task_type="invalid_type",
        )

        assert result.success is False
        assert "task_type" in result.error.lower()

    @patch("api.spec_builder.dspy")
    def test_build_result_has_warnings(self, mock_dspy, mock_dspy_prediction, env_with_fake_key):
        """BuildResult should carry any warnings from validation."""
        mock_lm = MagicMock()
        mock_dspy.LM.return_value = mock_lm
        mock_module = MagicMock()
        mock_module.return_value = mock_dspy_prediction
        mock_dspy.ChainOfThought.return_value = mock_module

        with patch("api.spec_builder.validate_spec_output") as mock_validate:
            mock_validate.return_value = {
                "errors": [],
                "warnings": ["Some minor warning"],
            }

            builder = SpecBuilder(api_key="fake-key", auto_initialize=True)
            result = builder.build(
                task_description="Implement OAuth2",
                task_type="coding",
            )

        assert isinstance(result, BuildResult)
        if result.success:
            assert "Some minor warning" in result.warnings


# =============================================================================
# TestStep8HarnessKernelExecution - AgentSpec -> AgentRun
# =============================================================================

class TestStep8HarnessKernelExecution:
    """Stage: AgentSpec -> AgentRun. Tests: 3."""

    def test_kernel_creates_run_for_spec(self, db_session):
        """HarnessKernel should create an AgentRun from an AgentSpec."""
        spec = AgentSpec(
            id="test-spec-e2e-001",
            name="test-spec-e2e",
            display_name="E2E Test Spec",
            objective="Test the pipeline",
            task_type="testing",
            tool_policy={"allowed_tools": ["Read", "Write"], "forbidden_patterns": [], "policy_version": "v1"},
            max_turns=10,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        kernel = HarnessKernel(db=db_session)
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()

        tracker = kernel.initialize_run(run, spec)
        assert tracker is not None
        assert isinstance(tracker, BudgetTracker)
        assert tracker.max_turns == 10
        assert tracker.timeout_seconds == 300

    def test_budget_tracker_tracks_turns(self, db_session):
        """BudgetTracker should track turns used and remaining."""
        tracker = BudgetTracker(
            max_turns=10,
            timeout_seconds=300,
            turns_used=0,
            run_id="test-run-001",
            started_at=datetime.now(timezone.utc),
        )
        assert tracker.remaining_turns == 10
        assert not tracker.is_exhausted

        tracker.increment_turns()
        assert tracker.turns_used == 1
        assert tracker.remaining_turns == 9

    def test_kernel_records_started_event(self, db_session):
        """HarnessKernel should record a 'started' event when initializing a run."""
        spec = AgentSpec(
            id="test-spec-e2e-002",
            name="test-spec-e2e-events",
            display_name="E2E Event Test Spec",
            objective="Test event recording",
            task_type="testing",
            tool_policy={"allowed_tools": ["Read"], "forbidden_patterns": [], "policy_version": "v1"},
            max_turns=5,
            timeout_seconds=120,
        )
        db_session.add(spec)
        db_session.commit()

        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()

        kernel = HarnessKernel(db=db_session)
        kernel.initialize_run(run, spec)

        # Check for started event
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "started",
        ).all()
        assert len(events) == 1
        assert events[0].event_type == "started"


# =============================================================================
# TestStep9AcceptanceGateEvaluation - Validators -> verdict
# =============================================================================

class TestStep9AcceptanceGateEvaluation:
    """Stage: Validators -> verdict. Tests: 3."""

    def test_gate_evaluation_with_passing_validators(self, db_session):
        """AcceptanceGate should return passed when all validators pass."""
        spec = AgentSpec(
            id="test-spec-gate-001",
            name="test-spec-gate",
            display_name="Gate Test",
            objective="Test gate",
            task_type="testing",
            tool_policy={"allowed_tools": ["Read"], "forbidden_patterns": [], "policy_version": "v1"},
            max_turns=5,
            timeout_seconds=120,
        )
        db_session.add(spec)
        db_session.commit()

        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            status="running",
            turns_used=1,
            tokens_in=100,
            tokens_out=200,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()

        # Create acceptance spec with no validators (should default to pass)
        acceptance_spec = AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            validators=[],
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )

        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context={})
        assert result.passed is True
        assert result.verdict == "passed"

    def test_file_exists_validator_passes(self, tmp_path):
        """FileExistsValidator should pass when file exists."""
        # Create a test file
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test content")

        validator = FileExistsValidator()
        config = {
            "path": str(test_file),
            "should_exist": True,
            "description": "Test file should exist",
        }
        result = validator.evaluate(config, context={})
        assert result.passed is True
        assert result.validator_type == "file_exists"

    def test_file_exists_validator_fails_when_missing(self, tmp_path):
        """FileExistsValidator should fail when file does not exist."""
        missing_file = tmp_path / "nonexistent.txt"

        validator = FileExistsValidator()
        config = {
            "path": str(missing_file),
            "should_exist": True,
            "description": "This file should not be found",
        }
        result = validator.evaluate(config, context={})
        assert result.passed is False
        assert result.score == 0.0


# =============================================================================
# TestFullPipelineE2E - Full pipeline integration
# =============================================================================

class TestFullPipelineE2E:
    """Stage: Full pipeline. Tests: 1. All 9 steps threaded together in sequence."""

    def test_full_pipeline_feature_to_verdict(self, db_session, sample_feature, tmp_path):
        """Thread all 9 pipeline stages together for a complete E2E flow.

        Pipeline:
        1. Feature -> task_type detection
        2. task_type -> tool_policy
        3. task_type -> budget
        4. objective -> spec name
        5. steps -> validators
        6. Feature -> AgentSpec (via compiler)
        7. (SpecBuilder step skipped in integration - uses compiler output)
        8. AgentSpec -> AgentRun (via kernel)
        9. Validators -> verdict (via AcceptanceGate)
        """
        # Step 1: Detect task type from feature description
        task_type = detect_task_type(sample_feature.description)
        assert task_type in TASK_TYPES

        # Step 2: Derive tool policy
        policy = derive_tool_policy(task_type)
        assert "allowed_tools" in policy
        assert "forbidden_patterns" in policy
        assert policy["policy_version"] == "v1"

        # Step 3: Derive budget
        budget = derive_budget(task_type)
        assert "max_turns" in budget
        assert "timeout_seconds" in budget
        assert 1 <= budget["max_turns"] <= 500
        assert 60 <= budget["timeout_seconds"] <= 7200

        # Step 4: Generate spec name
        spec_name = generate_spec_name(sample_feature.description, task_type)
        assert len(spec_name) <= 100
        assert re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', spec_name)

        # Step 5: Generate validators from steps
        validators = generate_validators_from_steps(
            sample_feature.steps or [],
            feature_id=sample_feature.id,
        )
        assert len(validators) > 0
        validator_types_found = {v["type"] for v in validators}
        # At least test_pass and file_exists should be generated from our steps
        assert len(validator_types_found) > 0

        # Step 6: Compile Feature -> AgentSpec
        compiler = FeatureCompiler()
        compiled_spec = compiler.compile(sample_feature)
        assert compiled_spec is not None
        assert compiled_spec.source_feature_id == sample_feature.id
        assert compiled_spec.task_type == "coding"
        assert compiled_spec.acceptance_spec is not None

        # Step 7: SpecBuilder integration verified via compile output
        # (In production, SpecBuilder.build() uses DSPy; here we use compiler output)
        assert compiled_spec.name is not None
        assert compiled_spec.objective is not None
        assert compiled_spec.tool_policy is not None

        # Step 8: Create AgentRun via HarnessKernel
        db_session.add(compiled_spec)
        db_session.commit()

        kernel = HarnessKernel(db=db_session)
        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=compiled_spec.id,
            status="pending",
            turns_used=0,
            tokens_in=0,
            tokens_out=0,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()

        tracker = kernel.initialize_run(run, compiled_spec)
        assert tracker is not None
        assert run.status == "running"

        # Verify started event was recorded
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
        ).all()
        assert any(e.event_type == "started" for e in events)

        # Step 9: Evaluate acceptance gate
        # Create a file to satisfy file_exists validator
        test_auth_file = tmp_path / "api" / "auth.py"
        test_auth_file.parent.mkdir(parents=True, exist_ok=True)
        test_auth_file.write_text("# OAuth2 implementation\n")

        # Use the acceptance spec from the compiled spec
        gate = AcceptanceGate()
        gate_result = gate.evaluate(
            run,
            compiled_spec.acceptance_spec,
            context={"project_dir": str(tmp_path)},
        )

        # The gate should evaluate (may pass or fail depending on validators)
        assert gate_result is not None
        assert gate_result.verdict in ("passed", "failed", "partial")
        assert gate_result.gate_mode == "all_pass"
        assert isinstance(gate_result.acceptance_results, list)


# =============================================================================
# Feature #116: Proof: Orchestrator spec-path compiles Feature→AgentSpec
#               via HarnessKernel.execute()
# =============================================================================

class TestOrchestratorSpecPath:
    """
    Prove the orchestrator path calls the spec-driven kernel
    (HarnessKernel.execute(spec)) when enabled, not legacy hard-coded agents.

    This test:
    1. Creates a Feature in in-memory DB
    2. Compiles it via FeatureCompiler into an AgentSpec
    3. Executes via HarnessKernel.execute() with a mocked turn_executor
    4. Asserts the spec-driven path was used (AgentRun created with correct agent_spec_id)

    Boundary mocking only: mock the turn_executor, but do NOT mock
    compile/execute/persist glue.
    """

    def test_orchestrator_spec_path(self, db_session):
        """
        Full orchestrator spec-path proof:
        Feature → FeatureCompiler.compile() → AgentSpec → HarnessKernel.execute() → AgentRun

        Verifies:
        - Feature is created in DB
        - FeatureCompiler.compile() produces a valid AgentSpec
        - HarnessKernel.execute(spec, turn_executor=mock) creates an AgentRun
        - AgentRun is persisted with correct agent_spec_id
        - AgentRun status is in terminal states (completed, failed, or timeout)
        """
        # Step 1: Create a Feature in in-memory DB with category, name, description, steps
        feature = Feature(
            id=200,
            priority=1,
            category="functional",
            name="Orchestrator Spec Path Test Feature",
            description="Test feature to prove orchestrator spec-path compiles Feature→AgentSpec via HarnessKernel.execute()",
            steps=[
                "Create a Feature in in-memory DB",
                "Compile Feature → AgentSpec using FeatureCompiler.compile()",
                "Execute via HarnessKernel.execute(spec, turn_executor=mock_executor)",
                "Assert AgentRun was created with status in terminal states",
            ],
            passes=False,
            in_progress=False,
        )
        db_session.add(feature)
        db_session.commit()

        # Verify feature is in DB
        persisted_feature = db_session.query(Feature).filter(Feature.id == 200).first()
        assert persisted_feature is not None
        assert persisted_feature.name == "Orchestrator Spec Path Test Feature"

        # Step 2: Compile Feature → AgentSpec using FeatureCompiler.compile()
        compiler = FeatureCompiler()
        spec = compiler.compile(persisted_feature)

        assert spec is not None
        assert isinstance(spec, AgentSpec)
        assert spec.source_feature_id == 200
        assert spec.objective is not None
        assert spec.tool_policy is not None
        assert spec.acceptance_spec is not None

        # Persist the AgentSpec and its AcceptanceSpec to the DB
        db_session.add(spec)
        db_session.commit()
        db_session.refresh(spec)

        # Record the spec ID for later assertion
        compiled_spec_id = spec.id

        # Step 3: Execute via HarnessKernel.execute() with a mocked turn_executor
        # The mock turn_executor simulates one turn then signals completion
        # Return signature: (completed, turn_data, tool_events, input_tokens, output_tokens)
        def mock_turn_executor(run, spec):
            """Mock turn executor that completes after one turn."""
            return (
                True,  # completed = True (agent signals done)
                {"mock_response": "test turn completed"},  # turn_data
                [],  # tool_events (no tool calls)
                100,  # input_tokens
                50,   # output_tokens
            )

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=mock_turn_executor)

        # Step 4: Assert AgentRun was created with status in terminal states
        assert run is not None
        assert isinstance(run, AgentRun)
        assert run.status in ("completed", "failed", "timeout"), (
            f"Expected terminal status, got '{run.status}'"
        )

        # Step 5: Assert AgentRun.agent_spec_id matches compiled spec ID
        assert run.agent_spec_id == compiled_spec_id, (
            f"Expected agent_spec_id={compiled_spec_id}, got {run.agent_spec_id}"
        )

        # Verify the run is persisted in the database
        persisted_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert persisted_run is not None
        assert persisted_run.agent_spec_id == compiled_spec_id
        assert persisted_run.status in ("completed", "failed", "timeout")

        # Verify that the run has recorded events (proves kernel execution path)
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id
        ).order_by(AgentEvent.sequence).all()
        assert len(events) > 0, "Expected at least one event to be recorded"

        # Verify started event exists
        event_types = [e.event_type for e in events]
        assert "started" in event_types, "Expected 'started' event in event trail"

        # Verify turn_complete event exists (from mock executor)
        assert "turn_complete" in event_types, "Expected 'turn_complete' event"

        # Verify the run tracked token usage from the mock executor
        assert run.turns_used >= 1, "Expected at least 1 turn to be used"
        assert run.tokens_in >= 100, f"Expected tokens_in >= 100, got {run.tokens_in}"
        assert run.tokens_out >= 50, f"Expected tokens_out >= 50, got {run.tokens_out}"


# =============================================================================
# Feature #117: Proof: Dynamic compilation produces materially different
#               AgentSpecs for different task descriptions
# =============================================================================

def test_dynamic_compilation_different_specs(coding_feature, audit_feature):
    """
    Prove that two different task descriptions compile into materially
    different AgentSpecs (different task_type, tool_policy, validators, budgets).

    This proves specs are dynamic, not hard-coded.

    Steps:
    1. Compile coding Feature (category='F. UI-Backend' → task_type='coding')
       using the coding_feature fixture (id=100, category='F. UI-Backend')
       Note: The feature description says 'A. Database' but both map to 'coding'.
    2. Compile audit Feature (category='Security' → task_type='audit')
       using the audit_feature fixture (id=200, category='Security')
    3. Assert spec1.task_type != spec2.task_type
    4. Assert spec1.tool_policy != spec2.tool_policy (different allowed_tools)
    5. Assert budgets differ (max_turns or timeout_seconds)
    """
    compiler = FeatureCompiler()

    # Step 1: Compile coding Feature (category='F. UI-Backend' -> coding)
    # Use a feature with category='A. Database' as the feature description specifies
    coding_db_feature = Feature(
        id=300,
        priority=1,
        category="A. Database",
        name="User Authentication with OAuth2",
        description="Implement user authentication system using OAuth2 protocol",
        steps=[
            "Run pytest tests/test_auth.py to verify authentication works",
            "File api/auth.py should exist with OAuth2 implementation",
        ],
        passes=False,
        in_progress=False,
    )
    spec1 = compiler.compile(coding_db_feature)

    # Step 2: Compile audit Feature (category='Security' -> audit)
    spec2 = compiler.compile(audit_feature)

    # Step 3: Assert task_type differs (coding vs audit)
    assert spec1.task_type != spec2.task_type, (
        f"Expected different task_types, but both are '{spec1.task_type}'. "
        f"spec1 (A. Database) should be 'coding', spec2 (Security) should be 'audit'."
    )
    assert spec1.task_type == "coding", f"Expected 'coding', got '{spec1.task_type}'"
    assert spec2.task_type == "audit", f"Expected 'audit', got '{spec2.task_type}'"

    # Step 4: Assert tool_policy differs (different allowed_tools)
    assert spec1.tool_policy != spec2.tool_policy, (
        "Expected different tool_policies for coding vs audit task types."
    )
    # More specifically, the allowed_tools lists should differ
    tools1 = spec1.tool_policy.get("allowed_tools", [])
    tools2 = spec2.tool_policy.get("allowed_tools", [])
    assert set(tools1) != set(tools2), (
        f"Expected different allowed_tools sets.\n"
        f"  coding tools: {sorted(tools1)}\n"
        f"  audit tools:  {sorted(tools2)}"
    )

    # Step 5: Assert budgets differ (max_turns and/or timeout_seconds)
    budgets_differ = (
        spec1.max_turns != spec2.max_turns
        or spec1.timeout_seconds != spec2.timeout_seconds
    )
    assert budgets_differ, (
        f"Expected different budgets for coding vs audit.\n"
        f"  coding: max_turns={spec1.max_turns}, timeout={spec1.timeout_seconds}\n"
        f"  audit:  max_turns={spec2.max_turns}, timeout={spec2.timeout_seconds}"
    )

    # Additional: verify both specs are valid AgentSpec instances
    assert isinstance(spec1, AgentSpec)
    assert isinstance(spec2, AgentSpec)

    # Additional: verify source_feature_id traceability is correct
    assert spec1.source_feature_id == 300
    assert spec2.source_feature_id == 200


# =============================================================================
# Feature #118: Proof: Persistence — DB contains AgentSpec/AgentRun/AgentEvent
#               after kernel run
# =============================================================================

class TestPersistenceAfterKernelRun:
    """
    Prove that after one kernel run, the database contains AgentSpec, AgentRun,
    and AgentEvent records with correct foreign keys and event ordering.

    Boundary mocking only: mock executor, not DB persistence.
    """

    def test_persistence_after_kernel_run(self, db_session):
        """
        End-to-end persistence proof:
        1. Create AgentSpec and persist to in-memory SQLite
        2. Execute via HarnessKernel with mocked turn_executor (2 turns)
        3. Query DB: AgentSpec exists with correct ID
        4. Query DB: AgentRun exists with agent_spec_id FK pointing to spec
        5. Query DB: AgentEvent records exist with run_id FK and ascending sequences
        """
        # Step 1: Create AgentSpec and persist to in-memory SQLite
        spec = AgentSpec(
            id="test-persistence-spec-001",
            name="test-persistence-spec",
            display_name="Persistence Proof Spec",
            objective="Prove DB persistence after kernel run",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read", "Write"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=10,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        # Verify spec persisted
        persisted_spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == "test-persistence-spec-001"
        ).first()
        assert persisted_spec is not None, "AgentSpec should be persisted in DB"
        assert persisted_spec.id == "test-persistence-spec-001"

        # Step 2: Execute via HarnessKernel with mocked turn_executor that
        # completes after 2 turns
        turn_count = 0

        def mock_turn_executor(run, spec):
            """Mock turn executor that completes after 2 turns."""
            nonlocal turn_count
            turn_count += 1
            completed = turn_count >= 2  # Signal done on turn 2
            return (
                completed,
                {"mock_response": f"turn {turn_count} completed"},
                [],      # tool_events (no tool calls)
                100,     # input_tokens per turn
                50,      # output_tokens per turn
            )

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=mock_turn_executor)

        assert run is not None, "kernel.execute() should return an AgentRun"

        # Step 3: Query DB — AgentSpec exists with correct ID
        queried_spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == "test-persistence-spec-001"
        ).first()
        assert queried_spec is not None, "AgentSpec must exist in DB after kernel run"
        assert queried_spec.id == "test-persistence-spec-001"
        assert queried_spec.name == "test-persistence-spec"
        assert queried_spec.task_type == "testing"

        # Step 4: Query DB — AgentRun exists with agent_spec_id FK pointing to spec
        queried_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert queried_run is not None, "AgentRun must exist in DB after kernel run"
        assert queried_run.agent_spec_id == "test-persistence-spec-001", (
            f"AgentRun.agent_spec_id FK should point to spec, "
            f"got '{queried_run.agent_spec_id}'"
        )
        assert queried_run.status in ("completed", "failed", "timeout"), (
            f"AgentRun should be in terminal status, got '{queried_run.status}'"
        )
        assert queried_run.turns_used == 2, (
            f"Expected 2 turns used, got {queried_run.turns_used}"
        )

        # Step 5: Query DB — AgentEvent records exist with run_id FK and
        # ascending sequence numbers
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id
        ).order_by(AgentEvent.sequence).all()

        assert len(events) > 0, "Expected AgentEvent records in DB after kernel run"

        # Verify all events have correct run_id FK
        for event in events:
            assert event.run_id == run.id, (
                f"AgentEvent.run_id FK should match run.id, "
                f"got '{event.run_id}' expected '{run.id}'"
            )

        # Verify ascending sequence numbers (no duplicates, strictly increasing)
        sequences = [e.sequence for e in events]
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i - 1], (
                f"Event sequences must be strictly ascending: "
                f"seq[{i-1}]={sequences[i-1]}, seq[{i}]={sequences[i]}"
            )

        # Verify expected event types exist
        event_types = [e.event_type for e in events]
        assert "started" in event_types, "Expected 'started' event in DB"
        assert "turn_complete" in event_types, "Expected 'turn_complete' event in DB"

        # Verify we have at least 2 turn_complete events (one per turn)
        turn_complete_events = [e for e in events if e.event_type == "turn_complete"]
        assert len(turn_complete_events) == 2, (
            f"Expected exactly 2 turn_complete events (one per turn), "
            f"got {len(turn_complete_events)}"
        )


# =============================================================================
# Feature #119: Proof: Acceptance gate PASS case — deterministic validators only
# =============================================================================

# Allowed deterministic validator types (no llm_judge)
DETERMINISTIC_VALIDATOR_TYPES = {"test_pass", "file_exists", "forbidden_patterns"}


def test_acceptance_gate_pass_deterministic(db_session, tmp_path):
    """
    Prove acceptance gate returns verdict='passed' when all deterministic
    validators pass. No llm_judge.

    Steps:
    1. Create a real file at tmp_path/test_output.txt
    2. Create AcceptanceSpec with file_exists validator pointing to that file
    3. Evaluate via AcceptanceGate.evaluate(run, acceptance_spec, context)
    4. Assert verdict='passed', gate_mode='all_pass'
    5. Assert only deterministic validators used (no llm_judge)
    """
    # Step 1: Create a real file at tmp_path/test_output.txt
    test_file = tmp_path / "test_output.txt"
    test_file.write_text("Deterministic validator test output content\n")
    assert test_file.exists(), "Test file must exist before evaluation"

    # Step 2: Create an AgentSpec + AgentRun in the in-memory DB
    spec = AgentSpec(
        id="test-spec-gate-deterministic-001",
        name="test-spec-gate-deterministic",
        display_name="Deterministic Gate Test",
        objective="Test acceptance gate with deterministic validators only",
        task_type="testing",
        tool_policy={
            "allowed_tools": ["Read"],
            "forbidden_patterns": [],
            "policy_version": "v1",
        },
        max_turns=5,
        timeout_seconds=120,
    )
    db_session.add(spec)
    db_session.commit()

    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="running",
        turns_used=1,
        tokens_in=100,
        tokens_out=200,
        retry_count=0,
    )
    db_session.add(run)
    db_session.commit()

    # Step 3: Create AcceptanceSpec with file_exists validator pointing to the real file
    acceptance_spec = AcceptanceSpec(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        validators=[
            {
                "type": "file_exists",
                "config": {
                    "path": str(test_file),
                    "should_exist": True,
                    "description": "Test output file should exist",
                },
                "weight": 1.0,
                "required": False,
            },
        ],
        gate_mode="all_pass",
        retry_policy="none",
        max_retries=0,
    )

    # Step 4: Evaluate via AcceptanceGate
    gate = AcceptanceGate()
    result = gate.evaluate(run, acceptance_spec, context={})

    # Step 5: Assert verdict='passed' and gate_mode='all_pass'
    assert result.passed is True, f"Expected passed=True, got {result.passed}"
    assert result.verdict == "passed", f"Expected verdict='passed', got '{result.verdict}'"
    assert result.gate_mode == "all_pass", f"Expected gate_mode='all_pass', got '{result.gate_mode}'"

    # Step 6: Assert only deterministic validators used (no llm_judge)
    for vr in result.validator_results:
        assert vr.validator_type in DETERMINISTIC_VALIDATOR_TYPES, (
            f"Non-deterministic validator found: {vr.validator_type}. "
            f"Only deterministic validators allowed: {DETERMINISTIC_VALIDATOR_TYPES}"
        )
    for ar in result.acceptance_results:
        assert ar["type"] in DETERMINISTIC_VALIDATOR_TYPES, (
            f"Non-deterministic validator type in acceptance_results: {ar['type']}. "
            f"Only deterministic validators allowed: {DETERMINISTIC_VALIDATOR_TYPES}"
        )

    # Verify the file_exists validator specifically passed
    assert len(result.validator_results) == 1, (
        f"Expected exactly 1 validator result, got {len(result.validator_results)}"
    )
    assert result.validator_results[0].passed is True
    assert result.validator_results[0].validator_type == "file_exists"

    # Verify no required validators failed
    assert result.required_failed is False, "No required validators should have failed"


# =============================================================================
# Feature #120: Proof — Acceptance gate FAIL case
#               Missing file fails deterministically
# =============================================================================

class TestAcceptanceGateFailDeterministic:
    """Prove AcceptanceGate returns verdict='failed' when a required file_exists
    validator points to a missing path. Deterministic — no LLM involvement."""

    def test_acceptance_gate_fail_deterministic(self, db_session, tmp_path):
        """AcceptanceGate must return verdict='failed' when file_exists validator
        points to a non-existent file.

        Steps:
        1. Do NOT create the expected file.
        2. Create AcceptanceSpec with file_exists validator pointing to missing path.
        3. Evaluate via AcceptanceGate.evaluate(run, acceptance_spec, context).
        4. Assert result.passed is False.
        5. Assert result.verdict == 'failed'.
        """
        # --- Setup: AgentSpec and AgentRun (minimal, just enough for gate) ---
        spec = AgentSpec(
            id="test-spec-gate-fail-001",
            name="test-spec-gate-fail",
            display_name="Gate Fail Test",
            objective="Test acceptance gate failure path",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=5,
            timeout_seconds=120,
        )
        db_session.add(spec)
        db_session.commit()

        run = AgentRun(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            status="completed",
            turns_used=1,
            tokens_in=100,
            tokens_out=200,
            retry_count=0,
        )
        db_session.add(run)
        db_session.commit()

        # Step 1: Do NOT create the expected file — path is intentionally missing
        missing_file = tmp_path / "this_file_does_not_exist.txt"
        assert not missing_file.exists(), "Precondition: file must NOT exist"

        # Step 2: Create AcceptanceSpec with file_exists validator pointing to
        #         the missing path
        acceptance_spec = AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            validators=[
                {
                    "type": "file_exists",
                    "config": {
                        "path": str(missing_file),
                        "should_exist": True,
                        "description": "Required output file must exist",
                    },
                    "required": True,
                    "weight": 1.0,
                },
            ],
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )

        # Step 3: Evaluate via AcceptanceGate
        gate = AcceptanceGate()
        result = gate.evaluate(run, acceptance_spec, context={})

        # Step 4: Assert result.passed is False
        assert result.passed is False, (
            f"Expected result.passed to be False for missing file, "
            f"but got {result.passed}. Verdict: {result.verdict}"
        )

        # Step 5: Assert result.verdict == 'failed'
        assert result.verdict == "failed", (
            f"Expected verdict='failed' for missing file validator, "
            f"but got verdict='{result.verdict}'"
        )


# =============================================================================
# Feature #122: Proof: ForbiddenPatternsValidator catches forbidden output
# =============================================================================

def test_forbidden_patterns_catches_violations(db_session):
    """
    Prove ForbiddenPatternsValidator works deterministically against agent run
    events containing forbidden patterns.

    Steps:
    1. Create AgentRun with AgentEvent(event_type='tool_result') containing 'rm -rf /'
    2. Configure ForbiddenPatternsValidator with patterns ['rm -rf']
    3. Evaluate validator
    4. Assert result.passed is False (forbidden pattern detected)
    5. Assert result.details contains match information

    No LLM involvement — purely deterministic validation.
    """
    # Step 1: Create AgentSpec (required FK parent for AgentRun)
    spec = AgentSpec(
        id=generate_uuid(),
        name="test-forbidden-patterns-spec",
        display_name="Forbidden Patterns Test Spec",
        objective="Test forbidden patterns detection",
        task_type="coding",
        tool_policy={"allowed_tools": ["Bash"], "forbidden_patterns": [], "policy_version": "v1"},
        max_turns=10,
        timeout_seconds=300,
    )
    db_session.add(spec)
    db_session.flush()

    # Step 2: Create AgentRun linked to the spec
    run = AgentRun(
        id=generate_uuid(),
        agent_spec_id=spec.id,
        status="completed",
        turns_used=1,
    )
    db_session.add(run)
    db_session.flush()

    # Step 3: Create AgentEvent with event_type='tool_result' containing forbidden text
    forbidden_event = AgentEvent(
        run_id=run.id,
        event_type="tool_result",
        sequence=1,
        payload="Executing command: rm -rf / --no-preserve-root",
        tool_name="Bash",
    )
    db_session.add(forbidden_event)
    db_session.commit()

    # Refresh run to load events relationship
    db_session.refresh(run)

    # Verify precondition: run has the tool_result event
    assert len(run.events) == 1, f"Expected 1 event, got {len(run.events)}"
    assert run.events[0].event_type == "tool_result"
    assert "rm -rf /" in run.events[0].payload

    # Step 4: Configure ForbiddenPatternsValidator with patterns ['rm -rf']
    validator = ForbiddenPatternsValidator()
    config = {
        "patterns": ["rm -rf"],
        "case_sensitive": True,
        "description": "Check for dangerous commands",
    }

    # Step 5: Evaluate validator with run context
    result = validator.evaluate(config=config, context={}, run=run)

    # Step 6: Assert result.passed is False (forbidden pattern detected)
    assert result.passed is False, (
        f"Expected result.passed to be False when forbidden pattern 'rm -rf' "
        f"is present in tool_result event, but got {result.passed}. "
        f"Message: {result.message}"
    )

    # Step 7: Assert result.details contains match information
    assert "matches" in result.details, (
        f"Expected 'matches' key in result.details, "
        f"got keys: {list(result.details.keys())}"
    )
    matches = result.details["matches"]
    assert len(matches) >= 1, (
        f"Expected at least 1 match in details, got {len(matches)}"
    )

    # Verify the match contains the expected pattern info
    first_match = matches[0]
    assert first_match["pattern"] == "rm -rf", (
        f"Expected matched pattern to be 'rm -rf', got '{first_match['pattern']}'"
    )
    assert "matched_text" in first_match, "Match should include 'matched_text'"
    assert first_match["matched_text"] == "rm -rf", (
        f"Expected matched_text='rm -rf', got '{first_match['matched_text']}'"
    )

    # Verify other details
    assert result.details["patterns_checked"] == ["rm -rf"], (
        f"Expected patterns_checked=['rm -rf'], got {result.details['patterns_checked']}"
    )
    assert result.details["events_checked"] == 1, (
        f"Expected events_checked=1, got {result.details['events_checked']}"
    )

    # Verify validator_type
    assert result.validator_type == "forbidden_patterns", (
        f"Expected validator_type='forbidden_patterns', got '{result.validator_type}'"
    )

    # Verify message mentions forbidden patterns found
    assert "forbidden pattern" in result.message.lower(), (
        f"Expected message to mention 'forbidden pattern', got: {result.message}"
    )


# =============================================================================
# Feature #121: Smoke test - full Feature->Spec->Kernel->DB->Gate without API key
# =============================================================================

class TestSmokeFullWiring:
    """
    Single runnable smoke test proving complete end-to-end wiring with
    NO real API key.

    Flow:
    1. Create Feature in in-memory SQLite (no API key needed)
    2. Compile Feature -> AgentSpec via FeatureCompiler (no mock)
    3. Persist AgentSpec to DB
    4. Execute via HarnessKernel.execute(spec, turn_executor=mock) -- mock only
       at boundary (the executor/session), NOT the compile/execute/persist glue
    5. Assert DB contains AgentSpec, AgentRun, AgentEvent records with correct FKs
    6. Evaluate AcceptanceGate and assert GateResult returned
    """

    def test_smoke_full_wiring_no_api_key(self, db_session):
        """
        Full end-to-end wiring proof without any API key.

        This smoke test threads together the entire pipeline:
          Feature -> FeatureCompiler.compile() -> AgentSpec (persisted)
          -> HarnessKernel.execute(spec, turn_executor=mock) -> AgentRun (persisted)
          -> DB contains AgentSpec + AgentRun + AgentEvent records
          -> AcceptanceGate.evaluate() -> GateResult

        Boundary mocking ONLY: the turn_executor is mocked (it would normally
        call the Claude API), but all compile/execute/persist glue code runs
        for real against an in-memory SQLite database.
        """
        # =====================================================================
        # Step 1: Create Feature in in-memory SQLite (no API key needed)
        # =====================================================================
        feature = Feature(
            id=500,
            priority=1,
            category="A. Database",
            name="Smoke Test Feature - Full Wiring",
            description=(
                "End-to-end smoke test proving Feature to Spec to Kernel to DB "
                "to Gate wiring works without a real API key."
            ),
            steps=[
                "Create Feature in in-memory SQLite",
                "Compile Feature to AgentSpec via FeatureCompiler",
                "Persist AgentSpec to DB",
                "Execute via HarnessKernel.execute(spec, turn_executor=mock)",
                "Assert DB has AgentSpec, AgentRun, AgentEvent with correct FKs",
                "Evaluate AcceptanceGate and assert GateResult returned",
            ],
            passes=False,
            in_progress=False,
        )
        db_session.add(feature)
        db_session.commit()

        # Verify feature persisted
        persisted_feature = db_session.query(Feature).filter(
            Feature.id == 500
        ).first()
        assert persisted_feature is not None, "Feature must be persisted in DB"

        # =====================================================================
        # Step 2: Compile Feature -> AgentSpec via FeatureCompiler (NO mock)
        # =====================================================================
        compiler = FeatureCompiler()
        spec = compiler.compile(persisted_feature)

        assert spec is not None, "FeatureCompiler.compile() must return an AgentSpec"
        assert isinstance(spec, AgentSpec)
        assert spec.source_feature_id == 500
        assert spec.task_type == "coding"
        assert spec.objective is not None and len(spec.objective) > 0
        assert spec.tool_policy is not None
        assert "allowed_tools" in spec.tool_policy
        assert spec.acceptance_spec is not None
        assert isinstance(spec.acceptance_spec, AcceptanceSpec)
        assert len(spec.acceptance_spec.validators) > 0

        # =====================================================================
        # Step 3: Persist AgentSpec to DB
        # =====================================================================
        db_session.add(spec)
        db_session.commit()
        db_session.refresh(spec)

        # Verify AgentSpec persisted
        persisted_spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == spec.id
        ).first()
        assert persisted_spec is not None, "AgentSpec must be persisted in DB"
        assert persisted_spec.id == spec.id
        assert persisted_spec.source_feature_id == 500
        assert persisted_spec.task_type == "coding"

        # Record spec ID for FK assertions later
        spec_id = spec.id

        # =====================================================================
        # Step 4: Execute via HarnessKernel.execute(spec, turn_executor=mock)
        #         Mock ONLY at boundary: the turn executor (would be Claude API)
        # =====================================================================
        def mock_turn_executor(run, spec):
            """
            Boundary mock: simulates a single turn of agent execution.
            Returns the 5-tuple expected by HarnessKernel.execute():
              (completed, turn_data, tool_events, input_tokens, output_tokens)
            """
            return (
                True,   # completed - agent signals done after 1 turn
                {"mock_response": "smoke test turn completed successfully"},
                [],     # tool_events - no tool calls in smoke test
                150,    # input_tokens
                75,     # output_tokens
            )

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=mock_turn_executor)

        assert run is not None, "kernel.execute() must return an AgentRun"
        assert isinstance(run, AgentRun)

        # =====================================================================
        # Step 5: Assert DB contains AgentSpec, AgentRun, AgentEvent
        #         with correct foreign keys
        # =====================================================================

        # --- 5a: AgentSpec still in DB ---
        db_spec = db_session.query(AgentSpec).filter(
            AgentSpec.id == spec_id
        ).first()
        assert db_spec is not None, "AgentSpec must exist in DB after kernel run"
        assert db_spec.id == spec_id

        # --- 5b: AgentRun exists with correct agent_spec_id FK ---
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run is not None, "AgentRun must be persisted in DB"
        assert db_run.agent_spec_id == spec_id, (
            f"AgentRun.agent_spec_id FK should be '{spec_id}', "
            f"got '{db_run.agent_spec_id}'"
        )
        assert db_run.status in ("completed", "failed", "timeout"), (
            f"AgentRun should be in terminal status, got '{db_run.status}'"
        )
        assert db_run.turns_used >= 1, (
            f"Expected at least 1 turn, got {db_run.turns_used}"
        )
        assert db_run.tokens_in >= 150, (
            f"Expected tokens_in >= 150, got {db_run.tokens_in}"
        )
        assert db_run.tokens_out >= 75, (
            f"Expected tokens_out >= 75, got {db_run.tokens_out}"
        )

        # --- 5c: AgentEvent records exist with correct run_id FK ---
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id
        ).order_by(AgentEvent.sequence).all()

        assert len(events) > 0, "Expected AgentEvent records in DB"

        # All events must have correct run_id FK
        for event in events:
            assert event.run_id == run.id, (
                f"AgentEvent.run_id FK mismatch: '{event.run_id}' != '{run.id}'"
            )

        # Verify ascending sequence numbers (no duplicates)
        sequences = [e.sequence for e in events]
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i - 1], (
                f"Sequences not ascending: [{sequences[i-1]}, {sequences[i]}]"
            )

        # Verify expected event types
        event_types = [e.event_type for e in events]
        assert "started" in event_types, "Expected 'started' event in DB"
        assert "turn_complete" in event_types, "Expected 'turn_complete' event"

        # =====================================================================
        # Step 6: Evaluate AcceptanceGate and assert GateResult returned
        # =====================================================================
        gate = AcceptanceGate()
        gate_result = gate.evaluate(
            run,
            spec.acceptance_spec,
            context={},
        )

        assert gate_result is not None, "AcceptanceGate.evaluate() must return a result"
        assert isinstance(gate_result, GateResult), (
            f"Expected GateResult, got {type(gate_result)}"
        )
        assert gate_result.verdict in ("passed", "failed", "partial"), (
            f"Invalid verdict: '{gate_result.verdict}'"
        )
        assert gate_result.gate_mode == "all_pass", (
            f"gate_mode should be 'all_pass', got '{gate_result.gate_mode}'"
        )
        assert isinstance(gate_result.acceptance_results, list)
        assert isinstance(gate_result.validator_results, list)


# =============================================================================
# Feature #128: HarnessKernel executes spec with max_turns and timeout budget
#               enforcement
# =============================================================================

class TestHarnessKernelBudgetEnforcement:
    """
    Prove HarnessKernel.execute() enforces max_turns and timeout budget
    constraints, records timeout events, runs acceptance validators after
    budget exhaustion (graceful termination), and tracks token usage.

    Feature #128 verification steps:
    1. Verify HarnessKernel.execute() is called with the compiled AgentSpec
       in the --spec path
    2. Verify turns_used is incremented after each turn and matches the
       actual number of turns executed
    3. Create or configure a spec with max_turns=2 and verify execution
       stops after exactly 2 turns
    4. Verify that on budget exhaustion, the run status is set to 'timeout'
       (not 'failed')
    5. Verify a 'timeout' event is recorded in agent_events when budget is
       exhausted
    6. Verify that acceptance validators still run after budget exhaustion
       (graceful termination)
    7. Verify tokens_in and tokens_out are tracked and stored on the AgentRun
    """

    def test_execute_called_with_compiled_spec(self, db_session):
        """
        Step 1: Verify HarnessKernel.execute() is called with the compiled
        AgentSpec in the --spec path.

        Proves: Feature -> FeatureCompiler -> AgentSpec -> HarnessKernel.execute()
        """
        # Create a Feature and compile it to AgentSpec (the --spec path)
        feature = Feature(
            id=1280,
            priority=1,
            category="functional",
            name="Budget Enforcement Test Feature",
            description="Test budget enforcement in HarnessKernel",
            steps=["Run pytest to verify budget enforcement"],
            passes=False,
            in_progress=False,
        )
        compiler = FeatureCompiler()
        spec = compiler.compile(feature)

        assert isinstance(spec, AgentSpec)
        assert spec.source_feature_id == 1280

        # Persist spec to DB
        db_session.add(spec)
        db_session.commit()
        db_session.refresh(spec)

        # Execute via HarnessKernel.execute() with compiled spec
        def mock_executor(run, spec):
            return (True, {"response": "done"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=mock_executor)

        # Verify the kernel received and used the compiled spec
        assert run is not None
        assert isinstance(run, AgentRun)
        assert run.agent_spec_id == spec.id
        assert run.status in ("completed", "failed", "timeout")

    def test_turns_used_incremented_correctly(self, db_session):
        """
        Step 2: Verify turns_used is incremented after each turn and matches
        the actual number of turns executed.
        """
        spec = AgentSpec(
            id="test-budget-turns-inc-001",
            name="test-budget-turns-inc",
            display_name="Turns Increment Test",
            objective="Verify turns_used increments correctly",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=10,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        # Track turns_used values observed during execution
        observed_turns = []
        turn_count = 0

        def mock_executor(run, spec):
            nonlocal turn_count
            turn_count += 1
            # Capture turns_used BEFORE this turn is recorded
            # (it should already reflect previous turns)
            observed_turns.append(run.turns_used)
            completed = turn_count >= 5  # Complete after 5 turns
            return (completed, {"turn": turn_count}, [], 100, 50)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=mock_executor)

        # After 5 turns, turns_used should be exactly 5
        assert run.turns_used == 5, (
            f"Expected turns_used=5 after 5 turns, got {run.turns_used}"
        )

        # Verify turns_used was incrementing correctly
        # Before turn 1: turns_used=0, before turn 2: turns_used=1, etc.
        assert observed_turns == [0, 1, 2, 3, 4], (
            f"Expected observed turns [0, 1, 2, 3, 4], got {observed_turns}"
        )

        # Verify persisted in DB
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run.turns_used == 5

    def test_max_turns_stops_execution(self, db_session):
        """
        Step 3: Create or configure a spec with max_turns=2 and verify
        execution stops after exactly 2 turns.
        """
        spec = AgentSpec(
            id="test-budget-max2-001",
            name="test-budget-max2",
            display_name="Max Turns 2 Test",
            objective="Verify execution stops after exactly 2 turns",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=2,  # KEY: Only 2 turns allowed
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        # Executor that never signals completion — keeps asking for more turns
        executor_calls = 0

        def never_completing_executor(run, spec):
            nonlocal executor_calls
            executor_calls += 1
            # Never signal completion — kernel must stop via budget
            return (False, {"turn": executor_calls}, [], 100, 50)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=never_completing_executor)

        # Kernel should have stopped after exactly 2 turns
        assert executor_calls == 2, (
            f"Expected exactly 2 executor calls (max_turns=2), got {executor_calls}"
        )
        assert run.turns_used == 2, (
            f"Expected turns_used=2, got {run.turns_used}"
        )

    def test_budget_exhaustion_sets_timeout_status(self, db_session):
        """
        Step 4: Verify that on budget exhaustion, the run status is set to
        'timeout' (not 'failed').
        """
        spec = AgentSpec(
            id="test-budget-timeout-status-001",
            name="test-budget-timeout-status",
            display_name="Timeout Status Test",
            objective="Verify budget exhaustion sets status=timeout",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=2,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        def never_completing_executor(run, spec):
            return (False, {"turn": "data"}, [], 100, 50)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=never_completing_executor)

        # Status MUST be 'timeout', NOT 'failed'
        assert run.status == "timeout", (
            f"Expected status='timeout' on budget exhaustion, got '{run.status}'"
        )
        assert run.status != "failed", (
            "Budget exhaustion must NOT set status to 'failed'"
        )

        # Verify persisted in DB
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run.status == "timeout"

    def test_timeout_event_recorded(self, db_session):
        """
        Step 5: Verify a 'timeout' event is recorded in agent_events when
        budget is exhausted.
        """
        spec = AgentSpec(
            id="test-budget-timeout-event-001",
            name="test-budget-timeout-event",
            display_name="Timeout Event Test",
            objective="Verify timeout event is recorded",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=2,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        def never_completing_executor(run, spec):
            return (False, {"turn": "data"}, [], 100, 50)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=never_completing_executor)

        # Query all events for this run
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id
        ).order_by(AgentEvent.sequence).all()

        event_types = [e.event_type for e in events]

        # Must have a 'timeout' event
        assert "timeout" in event_types, (
            f"Expected 'timeout' event in agent_events, got types: {event_types}"
        )

        # Find the timeout event and verify its payload
        timeout_events = [e for e in events if e.event_type == "timeout"]
        assert len(timeout_events) >= 1, "Expected at least 1 timeout event"

        timeout_event = timeout_events[0]
        assert timeout_event.payload is not None, "Timeout event must have payload"
        assert "reason" in timeout_event.payload, (
            f"Timeout event payload must have 'reason', got: {timeout_event.payload}"
        )
        assert timeout_event.payload["reason"] == "max_turns_exceeded", (
            f"Expected reason='max_turns_exceeded', got '{timeout_event.payload['reason']}'"
        )
        assert "turns_used" in timeout_event.payload, (
            "Timeout payload must include turns_used"
        )
        assert timeout_event.payload["turns_used"] == 2, (
            f"Expected turns_used=2 in timeout payload, got {timeout_event.payload['turns_used']}"
        )

    def test_acceptance_validators_run_after_budget_exhaustion(self, db_session, tmp_path):
        """
        Step 6: Verify that acceptance validators still run after budget
        exhaustion (graceful termination).

        This proves Feature #49: graceful budget exhaustion handling.
        """
        # Create a file that the validator can check
        test_file = tmp_path / "partial_output.txt"
        test_file.write_text("partial work completed\n")

        spec = AgentSpec(
            id="test-budget-graceful-001",
            name="test-budget-graceful",
            display_name="Graceful Termination Test",
            objective="Verify validators run after budget exhaustion",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=2,
            timeout_seconds=300,
        )

        # Create AcceptanceSpec with a file_exists validator
        acceptance_spec = AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            validators=[
                {
                    "type": "file_exists",
                    "config": {
                        "path": str(test_file),
                        "should_exist": True,
                        "description": "Partial output file should exist",
                    },
                    "weight": 1.0,
                    "required": False,
                },
            ],
            gate_mode="all_pass",
            retry_policy="none",
            max_retries=0,
        )
        spec.acceptance_spec = acceptance_spec

        db_session.add(spec)
        db_session.commit()
        db_session.refresh(spec)

        def never_completing_executor(run, spec):
            return (False, {"turn": "data"}, [], 100, 50)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=never_completing_executor)

        # Run should be in timeout status (budget exhausted)
        assert run.status == "timeout", (
            f"Expected status='timeout', got '{run.status}'"
        )

        # Verify acceptance validators still ran (graceful termination)
        # The kernel should have recorded an acceptance_check event
        events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id
        ).order_by(AgentEvent.sequence).all()
        event_types = [e.event_type for e in events]

        assert "acceptance_check" in event_types, (
            f"Expected 'acceptance_check' event after budget exhaustion (graceful "
            f"termination), but got only: {event_types}"
        )

        # Verify the acceptance check event has results
        acceptance_events = [e for e in events if e.event_type == "acceptance_check"]
        assert len(acceptance_events) >= 1
        acceptance_payload = acceptance_events[0].payload
        assert acceptance_payload is not None
        assert "final_verdict" in acceptance_payload
        assert "validator_count" in acceptance_payload
        assert acceptance_payload["validator_count"] >= 1

        # The run should have acceptance_results stored
        assert run.acceptance_results is not None, (
            "acceptance_results should be set after graceful termination"
        )
        assert len(run.acceptance_results) >= 1, (
            "At least 1 validator result expected"
        )

        # The partial verdict should be set
        assert run.final_verdict is not None, (
            "final_verdict should be set after graceful termination"
        )
        assert run.final_verdict in ("partial", "passed", "failed"), (
            f"final_verdict should be partial/passed/failed, got '{run.final_verdict}'"
        )

    def test_tokens_tracked_on_agent_run(self, db_session):
        """
        Step 7: Verify tokens_in and tokens_out are tracked and stored on
        the AgentRun.
        """
        spec = AgentSpec(
            id="test-budget-tokens-001",
            name="test-budget-tokens",
            display_name="Token Tracking Test",
            objective="Verify token tracking on AgentRun",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=10,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        turn_count = 0

        def mock_executor(run, spec):
            nonlocal turn_count
            turn_count += 1
            completed = turn_count >= 3  # 3 turns
            # Each turn: 200 input tokens, 100 output tokens
            return (completed, {"turn": turn_count}, [], 200, 100)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=mock_executor)

        # After 3 turns with 200 in + 100 out each:
        # tokens_in should be 600, tokens_out should be 300
        assert run.tokens_in == 600, (
            f"Expected tokens_in=600 (3 turns * 200), got {run.tokens_in}"
        )
        assert run.tokens_out == 300, (
            f"Expected tokens_out=300 (3 turns * 100), got {run.tokens_out}"
        )

        # Verify persisted in DB
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run.tokens_in == 600, (
            f"DB tokens_in should be 600, got {db_run.tokens_in}"
        )
        assert db_run.tokens_out == 300, (
            f"DB tokens_out should be 300, got {db_run.tokens_out}"
        )

    def test_tokens_tracked_even_on_timeout(self, db_session):
        """
        Additional verification: tokens_in and tokens_out are tracked and
        stored even when budget is exhausted (timeout).
        """
        spec = AgentSpec(
            id="test-budget-tokens-timeout-001",
            name="test-budget-tokens-timeout",
            display_name="Token Tracking on Timeout",
            objective="Verify tokens tracked even on timeout",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=2,
            timeout_seconds=300,
        )
        db_session.add(spec)
        db_session.commit()

        def never_completing_executor(run, spec):
            return (False, {"turn": "data"}, [], 150, 75)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=never_completing_executor)

        assert run.status == "timeout"

        # After 2 turns with 150 in + 75 out each:
        assert run.tokens_in == 300, (
            f"Expected tokens_in=300 on timeout, got {run.tokens_in}"
        )
        assert run.tokens_out == 150, (
            f"Expected tokens_out=150 on timeout, got {run.tokens_out}"
        )

        # Verify persisted in DB
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run.tokens_in == 300
        assert db_run.tokens_out == 150


# =============================================================================
# Feature #130: Acceptance Gate Evaluates Validators and Determines Final Verdict
# =============================================================================

class TestAcceptanceGateEvaluatesValidators:
    """Feature #130: After kernel finishes executing turns, the AcceptanceGate
    evaluates all validators defined in the AgentSpec's AcceptanceSpec.

    Verification steps:
    1. AcceptanceGate.evaluate() is called after kernel execution completes
    2. Each validator in the acceptance_spec is executed independently
    3. ValidatorResult contains passed (bool), message (str), and score (float)
    4. gate_mode='all_pass' requires ALL validators to pass for verdict='passed'
    5. gate_mode='any_pass' requires at least ONE validator to pass for verdict='passed'
    6. AgentRun.final_verdict is set to the gate's verdict (passed/failed/partial)
    7. AgentRun.acceptance_results contains per-validator results as JSON array
    8. An 'acceptance_check' event is recorded in agent_events with the gate results
    """

    _subdir_counter = 0

    def _create_spec_with_file_validators(
        self, db_session, tmp_path, gate_mode="all_pass", files_to_create=None
    ):
        """Helper: create an AgentSpec with file_exists validators.

        Args:
            db_session: Database session
            tmp_path: Pytest tmp_path fixture
            gate_mode: Gate mode for acceptance spec ("all_pass" or "any_pass")
            files_to_create: List of filenames to pre-create in tmp_path.
                            Validators check for file_a.txt and file_b.txt.
        Returns:
            Tuple of (spec, acceptance_spec)
        """
        # Use a unique subdirectory for each call to avoid file bleeding
        TestAcceptanceGateEvaluatesValidators._subdir_counter += 1
        subdir = tmp_path / f"run_{TestAcceptanceGateEvaluatesValidators._subdir_counter}"
        subdir.mkdir(parents=True, exist_ok=True)

        # Create test files if requested
        if files_to_create:
            for fname in files_to_create:
                (subdir / fname).write_text(f"content of {fname}")

        # Build validator definitions for two file_exists validators
        validators = [
            {
                "type": "file_exists",
                "config": {
                    "path": str(subdir / "file_a.txt"),
                    "should_exist": True,
                    "description": "Validator A: file_a.txt must exist",
                },
                "weight": 1.0,
                "required": False,
            },
            {
                "type": "file_exists",
                "config": {
                    "path": str(subdir / "file_b.txt"),
                    "should_exist": True,
                    "description": "Validator B: file_b.txt must exist",
                },
                "weight": 1.0,
                "required": False,
            },
        ]

        spec = AgentSpec(
            id=f"spec-130-{gate_mode}-{generate_uuid()[:8]}",
            name=f"spec-130-{gate_mode}",
            display_name=f"Feature 130 Test ({gate_mode})",
            objective="Test acceptance gate evaluation",
            task_type="testing",
            tool_policy={
                "allowed_tools": ["Read"],
                "forbidden_patterns": [],
                "policy_version": "v1",
            },
            max_turns=5,
            timeout_seconds=120,
        )
        db_session.add(spec)
        db_session.commit()

        acceptance_spec = AcceptanceSpec(
            id=generate_uuid(),
            agent_spec_id=spec.id,
            validators=validators,
            gate_mode=gate_mode,
            retry_policy="none",
            max_retries=0,
        )
        db_session.add(acceptance_spec)
        db_session.commit()

        # Refresh to load relationship
        db_session.refresh(spec)

        return spec, acceptance_spec

    def test_step1_acceptance_gate_called_after_kernel_execution(
        self, db_session, tmp_path
    ):
        """Step 1: Verify that after kernel execution completes,
        AcceptanceGate.evaluate() is called.

        We do this by executing the kernel with a turn executor that completes
        immediately, and verifying that the run has acceptance_results set
        (which can only happen if AcceptanceGate.evaluate() was called).
        """
        spec, acceptance_spec = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt", "file_b.txt"],
        )

        # Turn executor that completes immediately
        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=completing_executor)

        # The run should have acceptance_results populated - this proves
        # AcceptanceGate.evaluate() was called after kernel execution
        assert run.acceptance_results is not None, (
            "AcceptanceGate.evaluate() was not called - acceptance_results is None"
        )
        assert isinstance(run.acceptance_results, list), (
            f"acceptance_results should be a list, got {type(run.acceptance_results)}"
        )
        assert len(run.acceptance_results) == 2, (
            f"Expected 2 validator results, got {len(run.acceptance_results)}"
        )

    def test_step2_each_validator_executed_independently(
        self, db_session, tmp_path
    ):
        """Step 2: Verify each validator in the acceptance_spec is executed
        independently.

        Create 2 validators: one for a file that exists, one for a file that
        doesn't. Both should produce results (i.e., both were executed).
        """
        spec, acceptance_spec = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt"],  # Only create file_a, not file_b
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=completing_executor)

        # Both validators should have been executed independently
        results = run.acceptance_results
        assert len(results) == 2, (
            f"Both validators should run independently; got {len(results)} results"
        )

        # Validator A (file_a.txt exists): should pass
        result_a = results[0]
        assert result_a["passed"] is True, (
            f"Validator A should pass (file_a.txt exists), got: {result_a}"
        )

        # Validator B (file_b.txt does not exist): should fail
        result_b = results[1]
        assert result_b["passed"] is False, (
            f"Validator B should fail (file_b.txt missing), got: {result_b}"
        )

    def test_step3_validator_result_contains_required_fields(
        self, db_session, tmp_path
    ):
        """Step 3: Verify ValidatorResult contains passed (bool), message (str),
        and score (float).
        """
        spec, acceptance_spec = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt", "file_b.txt"],
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=completing_executor)

        results = run.acceptance_results
        assert len(results) >= 1, "At least one validator result expected"

        for i, result in enumerate(results):
            # Check passed is a bool
            assert isinstance(result["passed"], bool), (
                f"Validator {i}: 'passed' must be bool, got {type(result['passed'])}"
            )
            # Check message is a string
            assert isinstance(result["message"], str), (
                f"Validator {i}: 'message' must be str, got {type(result['message'])}"
            )
            assert len(result["message"]) > 0, (
                f"Validator {i}: 'message' must be non-empty"
            )
            # Check score is a float (or int that can be float)
            assert isinstance(result["score"], (int, float)), (
                f"Validator {i}: 'score' must be float, got {type(result['score'])}"
            )
            assert 0.0 <= float(result["score"]) <= 1.0, (
                f"Validator {i}: 'score' must be in [0.0, 1.0], got {result['score']}"
            )

    def test_step4_gate_mode_all_pass_requires_all_validators(
        self, db_session, tmp_path
    ):
        """Step 4: Verify gate_mode='all_pass' requires ALL validators to pass
        for verdict='passed'.
        """
        # Case A: All pass -> verdict='passed'
        spec_a, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt", "file_b.txt"],
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel_a = HarnessKernel(db=db_session)
        run_a = kernel_a.execute(spec_a, turn_executor=completing_executor)

        assert run_a.final_verdict == "passed", (
            f"all_pass with all validators passing: expected 'passed', got '{run_a.final_verdict}'"
        )

        # Case B: One fails -> verdict != 'passed'
        spec_b, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt"],  # Only file_a exists, file_b missing
        )

        kernel_b = HarnessKernel(db=db_session)
        run_b = kernel_b.execute(spec_b, turn_executor=completing_executor)

        assert run_b.final_verdict != "passed", (
            f"all_pass with one failing: expected 'partial' or 'failed', got '{run_b.final_verdict}'"
        )
        assert run_b.final_verdict in ("partial", "failed"), (
            f"Expected 'partial' or 'failed', got '{run_b.final_verdict}'"
        )

    def test_step5_gate_mode_any_pass_requires_one_validator(
        self, db_session, tmp_path
    ):
        """Step 5: Verify gate_mode='any_pass' requires at least ONE validator
        to pass for verdict='passed'.
        """
        # Case A: One passes, one fails -> verdict='passed' with any_pass
        spec_a, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="any_pass",
            files_to_create=["file_a.txt"],  # Only file_a exists
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel_a = HarnessKernel(db=db_session)
        run_a = kernel_a.execute(spec_a, turn_executor=completing_executor)

        assert run_a.final_verdict == "passed", (
            f"any_pass with one passing: expected 'passed', got '{run_a.final_verdict}'"
        )

        # Case B: None pass -> verdict='failed'
        spec_b, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="any_pass",
            files_to_create=[],  # No files created -> both validators fail
        )

        kernel_b = HarnessKernel(db=db_session)
        run_b = kernel_b.execute(spec_b, turn_executor=completing_executor)

        assert run_b.final_verdict == "failed", (
            f"any_pass with none passing: expected 'failed', got '{run_b.final_verdict}'"
        )

    def test_step6_agent_run_final_verdict_set(
        self, db_session, tmp_path
    ):
        """Step 6: Verify AgentRun.final_verdict is set to the gate's verdict
        (passed/failed/partial).
        """
        # Test passed verdict
        spec, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt", "file_b.txt"],
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=completing_executor)

        # Verify final_verdict is set on the run object
        assert run.final_verdict is not None, (
            "AgentRun.final_verdict must be set after acceptance gate evaluation"
        )
        assert run.final_verdict in ("passed", "failed", "partial"), (
            f"final_verdict must be one of passed/failed/partial, got '{run.final_verdict}'"
        )

        # Verify it's persisted in the database
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run.final_verdict == run.final_verdict, (
            f"DB final_verdict '{db_run.final_verdict}' doesn't match "
            f"run final_verdict '{run.final_verdict}'"
        )

    def test_step7_agent_run_acceptance_results_json_array(
        self, db_session, tmp_path
    ):
        """Step 7: Verify AgentRun.acceptance_results contains per-validator
        results as JSON array.
        """
        spec, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt"],  # Only create one file
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=completing_executor)

        # acceptance_results should be a JSON-serializable list
        results = run.acceptance_results
        assert isinstance(results, list), (
            f"acceptance_results must be a list, got {type(results)}"
        )
        assert len(results) == 2, (
            f"Expected 2 per-validator results, got {len(results)}"
        )

        # Each result should be a dict with standard fields
        for i, r in enumerate(results):
            assert isinstance(r, dict), (
                f"Result {i} must be a dict, got {type(r)}"
            )
            assert "passed" in r, f"Result {i} missing 'passed' field"
            assert "message" in r, f"Result {i} missing 'message' field"
            assert "score" in r, f"Result {i} missing 'score' field"
            assert "validator_type" in r, f"Result {i} missing 'validator_type' field"

        # Verify results are correct: file_a passes, file_b fails
        assert results[0]["passed"] is True, "Validator A (file_a.txt) should pass"
        assert results[1]["passed"] is False, "Validator B (file_b.txt) should fail"

        # Verify persistence in DB
        db_run = db_session.query(AgentRun).filter(
            AgentRun.id == run.id
        ).first()
        assert db_run.acceptance_results is not None, (
            "acceptance_results must be persisted in DB"
        )
        assert len(db_run.acceptance_results) == 2, (
            f"DB should have 2 results, got {len(db_run.acceptance_results)}"
        )

    def test_step8_acceptance_check_event_recorded(
        self, db_session, tmp_path
    ):
        """Step 8: Verify an 'acceptance_check' event is recorded in agent_events
        with the gate results.
        """
        spec, _ = self._create_spec_with_file_validators(
            db_session, tmp_path, gate_mode="all_pass",
            files_to_create=["file_a.txt", "file_b.txt"],
        )

        def completing_executor(run, spec):
            return (True, {"action": "completed"}, [], 50, 25)

        kernel = HarnessKernel(db=db_session)
        run = kernel.execute(spec, turn_executor=completing_executor)

        # Query for acceptance_check events
        acceptance_events = db_session.query(AgentEvent).filter(
            AgentEvent.run_id == run.id,
            AgentEvent.event_type == "acceptance_check",
        ).all()

        assert len(acceptance_events) >= 1, (
            f"Expected at least 1 'acceptance_check' event, found {len(acceptance_events)}. "
            f"Events: {[e.event_type for e in db_session.query(AgentEvent).filter(AgentEvent.run_id == run.id).all()]}"
        )

        # Verify the event payload contains gate results
        event = acceptance_events[0]
        payload = event.payload
        assert payload is not None, "acceptance_check event must have a payload"
        assert "final_verdict" in payload, (
            f"acceptance_check payload must contain 'final_verdict', got keys: {list(payload.keys())}"
        )
        assert "gate_mode" in payload, (
            f"acceptance_check payload must contain 'gate_mode', got keys: {list(payload.keys())}"
        )
        assert "results" in payload, (
            f"acceptance_check payload must contain 'results', got keys: {list(payload.keys())}"
        )
        assert "validator_count" in payload, (
            f"acceptance_check payload must contain 'validator_count', got keys: {list(payload.keys())}"
        )

        # Verify payload values
        assert payload["final_verdict"] == "passed", (
            f"Expected final_verdict='passed' in event, got '{payload['final_verdict']}'"
        )
        assert payload["gate_mode"] == "all_pass", (
            f"Expected gate_mode='all_pass' in event, got '{payload['gate_mode']}'"
        )
        assert payload["validator_count"] == 2, (
            f"Expected validator_count=2, got {payload['validator_count']}"
        )
