"""
Feature #127: FeatureCompiler produces AgentSpecs with correct task_type and tool_policy
========================================================================================

Comprehensive tests verifying that FeatureCompiler.compile() produces AgentSpecs
with correctly derived task_type, tool_policy, budgets, acceptance validators,
and traceability fields for every supported feature category.

Verification Steps:
1. Verify FeatureCompiler.compile(feature) is called for each feature in the --spec path
2. Verify the returned AgentSpec has a non-empty objective derived from the feature description
3. Verify task_type is correctly mapped from feature category
4. Verify tool_policy contains allowed_tools appropriate for the task_type
5. Verify tool_policy contains forbidden_patterns for dangerous operations
6. Verify max_turns and timeout_seconds are set to appropriate budgets per task_type
7. Verify acceptance_spec is created with validators derived from feature.steps
8. Verify source_feature_id links the AgentSpec back to the originating Feature record
9. After a multi-feature run, query agent_specs table and confirm at least 3 distinct task_type values exist
"""

import sys
from pathlib import Path

# Ensure project root is on the path so api.* imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from api.agentspec_models import AcceptanceSpec, AgentSpec
from api.database import Base, Feature
from api.feature_compiler import (
    FeatureCompiler,
    extract_task_type_from_category,
    get_budget_for_task_type,
    get_tools_for_task_type,
    reset_feature_compiler,
)
from api.spec_orchestrator import SpecOrchestrator
from api.static_spec_adapter import (
    CODING_TOOLS,
    FORBIDDEN_PATTERNS,
    TESTING_TOOLS,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def compiler():
    """Create a fresh FeatureCompiler instance."""
    return FeatureCompiler()


@pytest.fixture(autouse=True)
def _reset_compiler_singleton():
    """Reset the global compiler singleton between tests."""
    reset_feature_compiler()
    yield
    reset_feature_compiler()


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Provide a transactional DB session that rolls back after each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


def _make_feature(**overrides) -> MagicMock:
    """
    Build a mock Feature with sensible defaults.

    Keyword arguments override any default field value.
    """
    defaults = {
        "id": 1,
        "priority": 10,
        "category": "A. Database",
        "name": "Sample Feature",
        "description": "Implement a sample feature for testing.",
        "steps": ["Step one", "Step two", "Step three"],
        "passes": False,
        "in_progress": False,
        "dependencies": [],
    }
    defaults.update(overrides)
    feature = MagicMock(spec=Feature)
    for key, value in defaults.items():
        setattr(feature, key, value)
    return feature


# =============================================================================
# Test Class
# =============================================================================

class TestFeature127CompilerSpec:
    """
    Tests for Feature #127 -- nine verification steps plus a multi-feature DB
    integration check.
    """

    # -----------------------------------------------------------------
    # Step 1: FeatureCompiler.compile(feature) is called for each
    #         feature in the --spec path
    # -----------------------------------------------------------------

    def test_step1_compile_called_per_feature_via_orchestrator(
        self, db_session, db_engine
    ):
        """
        Step 1: Verify FeatureCompiler.compile(feature) is called for each
        feature processed by the SpecOrchestrator loop.

        We insert three features into the DB, then call run_one_feature for
        each and assert the compiler's compile method is invoked each time.
        """
        # Insert three real Feature rows
        features = []
        for i in range(1, 4):
            f = Feature(
                id=i,
                priority=i,
                category=f"Category{i}",
                name=f"Feature {i}",
                description=f"Description for feature {i}.",
                steps=[f"Step A{i}", f"Step B{i}"],
                passes=False,
                in_progress=False,
            )
            db_session.add(f)
            features.append(f)
        db_session.commit()

        orchestrator = SpecOrchestrator(
            project_dir=Path("/tmp/test_project"),
            session=db_session,
            engine=db_engine,
            yolo_mode=False,
            materialize_agents=False,
        )

        # Patch compile to track calls while still producing real AgentSpecs
        original_compile = orchestrator.compiler.compile
        compile_calls = []

        def tracking_compile(feature, **kwargs):
            compile_calls.append(feature.id)
            return original_compile(feature, **kwargs)

        with patch.object(orchestrator.compiler, "compile", side_effect=tracking_compile):
            for feat in features:
                orchestrator.run_one_feature(feat)

        # All three features should have had compile() called
        assert sorted(compile_calls) == [1, 2, 3], (
            f"Expected compile() for features [1,2,3], got {compile_calls}"
        )

    def test_step1_compile_returns_agentspec_for_each_category(self, compiler):
        """
        Step 1 (unit): compile() returns an AgentSpec for every category we
        might encounter in the --spec path.
        """
        categories = [
            "A. Database",
            "B. Testing",
            "C. Documentation",
            "D. Refactoring",
            "E. Security",
            "F. UI-Backend",
        ]
        for cat in categories:
            feat = _make_feature(category=cat, id=hash(cat) % 10000)
            spec = compiler.compile(feat)
            assert isinstance(spec, AgentSpec), (
                f"compile() did not return AgentSpec for category '{cat}'"
            )

    # -----------------------------------------------------------------
    # Step 2: AgentSpec has a non-empty objective derived from the
    #         feature description
    # -----------------------------------------------------------------

    def test_step2_objective_non_empty(self, compiler):
        """Step 2: The returned AgentSpec.objective must not be empty."""
        feat = _make_feature(description="Build the login page with OAuth2.")
        spec = compiler.compile(feat)
        assert spec.objective is not None
        assert len(spec.objective.strip()) > 0

    def test_step2_objective_contains_description_text(self, compiler):
        """Step 2: The objective must contain the feature description."""
        description = "Implement JWT-based authentication with refresh tokens."
        feat = _make_feature(description=description)
        spec = compiler.compile(feat)
        assert description in spec.objective

    def test_step2_objective_contains_feature_name(self, compiler):
        """Step 2: The objective must include the feature name as a header."""
        feat = _make_feature(name="User Registration Flow")
        spec = compiler.compile(feat)
        assert "User Registration Flow" in spec.objective

    def test_step2_objective_contains_steps(self, compiler):
        """Step 2: The objective must enumerate verification steps."""
        steps = ["Validate email format", "Hash password", "Store in DB"]
        feat = _make_feature(steps=steps)
        spec = compiler.compile(feat)
        for step in steps:
            assert step in spec.objective, (
                f"Step '{step}' missing from objective"
            )

    def test_step2_objective_non_empty_when_description_minimal(self, compiler):
        """Step 2: Even a minimal description produces a non-empty objective."""
        feat = _make_feature(description="x", steps=[])
        spec = compiler.compile(feat)
        assert len(spec.objective.strip()) > 0

    # -----------------------------------------------------------------
    # Step 3: task_type correctly mapped from feature category
    # -----------------------------------------------------------------

    def test_step3_coding_categories(self, compiler):
        """
        Step 3: Categories that map to 'coding' -- database, api, ui, etc.
        """
        coding_categories = [
            ("A. Database", "coding"),
            ("B. API", "coding"),
            ("C. Endpoint", "coding"),
            ("D. Backend", "coding"),
            ("E. REST", "coding"),
            ("F. UI", "coding"),
            ("G. Frontend", "coding"),
            ("H. Component", "coding"),
            ("I. Page", "coding"),
            ("J. Workflow", "coding"),
            ("K. Integration", "coding"),
            ("L. Feature", "coding"),
        ]
        for category, expected in coding_categories:
            feat = _make_feature(category=category)
            spec = compiler.compile(feat)
            assert spec.task_type == expected, (
                f"Category '{category}' should map to '{expected}', "
                f"got '{spec.task_type}'"
            )

    def test_step3_testing_categories(self, compiler):
        """Step 3: Categories containing testing keywords map to 'testing'."""
        testing_categories = [
            "B. Testing",
            "B. Test",
            "Verification",
            "Validation",
            "QA",
        ]
        for category in testing_categories:
            feat = _make_feature(category=category)
            spec = compiler.compile(feat)
            assert spec.task_type == "testing", (
                f"Category '{category}' should map to 'testing', "
                f"got '{spec.task_type}'"
            )

    def test_step3_documentation_categories(self, compiler):
        """Step 3: Documentation-related categories."""
        for category in ["Docs", "Documentation", "README"]:
            feat = _make_feature(category=category)
            spec = compiler.compile(feat)
            assert spec.task_type == "documentation", (
                f"Category '{category}' -> expected 'documentation', "
                f"got '{spec.task_type}'"
            )

    def test_step3_refactoring_categories(self, compiler):
        """Step 3: Refactoring-related categories."""
        for category in ["Refactor", "Refactoring", "Cleanup"]:
            feat = _make_feature(category=category)
            spec = compiler.compile(feat)
            assert spec.task_type == "refactoring", (
                f"Category '{category}' -> expected 'refactoring', "
                f"got '{spec.task_type}'"
            )

    def test_step3_audit_categories(self, compiler):
        """Step 3: Audit/security categories."""
        for category in ["Audit", "Security", "Review"]:
            feat = _make_feature(category=category)
            spec = compiler.compile(feat)
            assert spec.task_type == "audit", (
                f"Category '{category}' -> expected 'audit', "
                f"got '{spec.task_type}'"
            )

    def test_step3_default_to_coding_for_unknown_categories(self, compiler):
        """
        Step 3: Categories without a direct mapping (e.g. 'functional',
        'style', 'error-handling') default to 'coding'.
        """
        unmapped_categories = [
            "Functional",
            "Style",
            "Error-Handling",
            "Performance",
            "Accessibility",
            "Z. Unknown Category",
        ]
        for category in unmapped_categories:
            feat = _make_feature(category=category)
            spec = compiler.compile(feat)
            assert spec.task_type == "coding", (
                f"Category '{category}' should default to 'coding', "
                f"got '{spec.task_type}'"
            )

    def test_step3_extract_task_type_strips_letter_prefix(self):
        """Step 3: extract_task_type_from_category removes 'A. ' prefix."""
        assert extract_task_type_from_category("A. Database") == "coding"
        assert extract_task_type_from_category("B. Testing") == "testing"
        assert extract_task_type_from_category("Z. Documentation") == "documentation"

    def test_step3_extract_task_type_case_insensitive(self):
        """Step 3: Category matching is case-insensitive."""
        assert extract_task_type_from_category("DATABASE") == "coding"
        assert extract_task_type_from_category("testing") == "testing"
        assert extract_task_type_from_category("DOCUMENTATION") == "documentation"

    # -----------------------------------------------------------------
    # Step 4: tool_policy contains allowed_tools appropriate for
    #         the task_type
    # -----------------------------------------------------------------

    def test_step4_coding_tools_present(self, compiler):
        """Step 4: coding task_type gets CODING_TOOLS (Edit, Write, etc.)."""
        feat = _make_feature(category="A. Database")
        spec = compiler.compile(feat)
        allowed = spec.tool_policy["allowed_tools"]

        # Essential coding tools must be present
        for tool in ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]:
            assert tool in allowed, f"Coding tool '{tool}' missing from allowed_tools"

    def test_step4_testing_tools_present(self, compiler):
        """Step 4: testing task_type gets TESTING_TOOLS."""
        feat = _make_feature(category="B. Testing")
        spec = compiler.compile(feat)
        allowed = spec.tool_policy["allowed_tools"]

        # Core read-only + browser tools must be present
        for tool in ["Read", "Glob", "Grep", "Bash", "browser_navigate"]:
            assert tool in allowed, f"Testing tool '{tool}' missing from allowed_tools"

    def test_step4_audit_tools_restricted(self, compiler):
        """Step 4: audit task_type gets a more restricted tool set."""
        feat = _make_feature(category="Security")
        spec = compiler.compile(feat)
        allowed = spec.tool_policy["allowed_tools"]

        # Audit should include read-oriented tools
        assert "Read" in allowed
        assert "Glob" in allowed
        assert "Grep" in allowed

    def test_step4_documentation_tools(self, compiler):
        """Step 4: documentation task_type has Write for doc creation."""
        feat = _make_feature(category="Documentation")
        spec = compiler.compile(feat)
        allowed = spec.tool_policy["allowed_tools"]
        assert "Write" in allowed

    def test_step4_get_tools_for_task_type_coding(self):
        """Step 4: get_tools_for_task_type('coding') returns CODING_TOOLS."""
        tools = get_tools_for_task_type("coding")
        assert tools == CODING_TOOLS

    def test_step4_get_tools_for_task_type_testing(self):
        """Step 4: get_tools_for_task_type('testing') returns TESTING_TOOLS."""
        tools = get_tools_for_task_type("testing")
        assert tools == TESTING_TOOLS

    def test_step4_get_tools_returns_copy(self):
        """Step 4: get_tools_for_task_type returns a copy, not the original."""
        tools = get_tools_for_task_type("coding")
        tools.append("FAKE_TOOL")
        fresh_tools = get_tools_for_task_type("coding")
        assert "FAKE_TOOL" not in fresh_tools

    def test_step4_policy_has_version_key(self, compiler):
        """Step 4: tool_policy includes policy_version field."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        assert spec.tool_policy["policy_version"] == "v1"

    def test_step4_policy_has_tool_hints(self, compiler):
        """Step 4: tool_policy includes tool_hints dict."""
        feat = _make_feature(category="A. Database")
        spec = compiler.compile(feat)
        assert "tool_hints" in spec.tool_policy
        assert isinstance(spec.tool_policy["tool_hints"], dict)

    # -----------------------------------------------------------------
    # Step 5: tool_policy contains forbidden_patterns for dangerous
    #         operations
    # -----------------------------------------------------------------

    def test_step5_forbidden_patterns_present(self, compiler):
        """Step 5: Every compiled spec must include forbidden_patterns."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        patterns = spec.tool_policy.get("forbidden_patterns", [])
        assert len(patterns) > 0, "forbidden_patterns must not be empty"

    def test_step5_forbidden_patterns_match_static_list(self, compiler):
        """Step 5: Forbidden patterns should equal FORBIDDEN_PATTERNS from static_spec_adapter."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        patterns = spec.tool_policy["forbidden_patterns"]
        assert patterns == FORBIDDEN_PATTERNS

    def test_step5_rm_rf_blocked(self, compiler):
        """Step 5: 'rm -rf /' pattern is among forbidden patterns."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        patterns = spec.tool_policy["forbidden_patterns"]
        assert any("rm" in p and "rf" in p for p in patterns)

    def test_step5_drop_table_blocked(self, compiler):
        """Step 5: 'DROP TABLE' pattern is among forbidden patterns."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        patterns = spec.tool_policy["forbidden_patterns"]
        assert any("DROP" in p and "TABLE" in p for p in patterns)

    def test_step5_curl_pipe_sh_blocked(self, compiler):
        """Step 5: 'curl | sh' pattern is among forbidden patterns."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        patterns = spec.tool_policy["forbidden_patterns"]
        assert any("curl" in p and "sh" in p for p in patterns)

    def test_step5_forbidden_patterns_for_all_task_types(self, compiler):
        """Step 5: Forbidden patterns are present regardless of task_type."""
        categories = [
            "A. Database",   # coding
            "B. Testing",    # testing
            "Security",      # audit
            "Documentation", # documentation
            "Refactoring",   # refactoring
        ]
        for cat in categories:
            feat = _make_feature(category=cat)
            spec = compiler.compile(feat)
            patterns = spec.tool_policy.get("forbidden_patterns", [])
            assert len(patterns) > 0, (
                f"No forbidden_patterns for category '{cat}'"
            )

    def test_step5_forbidden_patterns_is_independent_copy(self, compiler):
        """Step 5: Each spec gets its own copy of forbidden_patterns."""
        feat1 = _make_feature(id=1, category="A. Database")
        feat2 = _make_feature(id=2, category="B. Testing")
        spec1 = compiler.compile(feat1)
        spec2 = compiler.compile(feat2)

        # Mutate one -- should not affect the other
        spec1.tool_policy["forbidden_patterns"].append("INJECTED")
        assert "INJECTED" not in spec2.tool_policy["forbidden_patterns"]

    # -----------------------------------------------------------------
    # Step 6: max_turns and timeout_seconds set to appropriate budgets
    # -----------------------------------------------------------------

    def test_step6_coding_budget(self, compiler):
        """Step 6: coding task_type gets max_turns=150, timeout=1800."""
        feat = _make_feature(category="A. Database")
        spec = compiler.compile(feat)
        assert spec.max_turns == 150
        assert spec.timeout_seconds == 1800

    def test_step6_testing_budget(self, compiler):
        """Step 6: testing task_type gets max_turns=50, timeout=900."""
        feat = _make_feature(category="B. Testing")
        spec = compiler.compile(feat)
        assert spec.max_turns == 50
        assert spec.timeout_seconds == 900

    def test_step6_documentation_budget(self, compiler):
        """Step 6: documentation task_type gets max_turns=30, timeout=600."""
        feat = _make_feature(category="Documentation")
        spec = compiler.compile(feat)
        assert spec.max_turns == 30
        assert spec.timeout_seconds == 600

    def test_step6_audit_budget(self, compiler):
        """Step 6: audit task_type gets max_turns=30, timeout=600."""
        feat = _make_feature(category="Security")
        spec = compiler.compile(feat)
        assert spec.max_turns == 30
        assert spec.timeout_seconds == 600

    def test_step6_refactoring_budget_defaults_to_coding(self, compiler):
        """Step 6: refactoring falls through to the default (coding) budget."""
        feat = _make_feature(category="Refactoring")
        spec = compiler.compile(feat)
        # Refactoring is not testing or documentation/audit, so it uses the
        # default coding budget
        expected = get_budget_for_task_type("refactoring")
        assert spec.max_turns == expected["max_turns"]
        assert spec.timeout_seconds == expected["timeout_seconds"]

    def test_step6_get_budget_for_task_type_helper(self):
        """Step 6: get_budget_for_task_type returns correct dicts."""
        assert get_budget_for_task_type("testing") == {
            "max_turns": 50,
            "timeout_seconds": 900,
        }
        assert get_budget_for_task_type("documentation") == {
            "max_turns": 30,
            "timeout_seconds": 600,
        }
        assert get_budget_for_task_type("audit") == {
            "max_turns": 30,
            "timeout_seconds": 600,
        }
        coding_budget = get_budget_for_task_type("coding")
        assert coding_budget["max_turns"] == 150
        assert coding_budget["timeout_seconds"] == 1800

    def test_step6_unknown_task_type_gets_coding_budget(self):
        """Step 6: Unknown task_type falls back to coding budget."""
        budget = get_budget_for_task_type("completely_unknown")
        assert budget["max_turns"] == 150
        assert budget["timeout_seconds"] == 1800

    def test_step6_budget_positive(self, compiler):
        """Step 6: Budget values are always positive integers."""
        for cat in ["A. Database", "B. Testing", "Security", "Documentation"]:
            feat = _make_feature(category=cat)
            spec = compiler.compile(feat)
            assert spec.max_turns > 0
            assert spec.timeout_seconds > 0

    # -----------------------------------------------------------------
    # Step 7: acceptance_spec is created with validators derived from
    #         feature.steps
    # -----------------------------------------------------------------

    def test_step7_acceptance_spec_created(self, compiler):
        """Step 7: Every compiled spec includes an AcceptanceSpec."""
        feat = _make_feature(steps=["S1", "S2"])
        spec = compiler.compile(feat)
        assert spec.acceptance_spec is not None
        assert isinstance(spec.acceptance_spec, AcceptanceSpec)

    def test_step7_acceptance_spec_linked(self, compiler):
        """Step 7: AcceptanceSpec.agent_spec_id points back to AgentSpec.id."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        assert spec.acceptance_spec.agent_spec_id == spec.id

    def test_step7_validator_count_matches_steps_plus_one(self, compiler):
        """
        Step 7: Number of validators == len(steps) + 1 (the mandatory
        'feature_passing' custom validator).
        """
        steps = ["Check A", "Check B", "Check C", "Check D"]
        feat = _make_feature(steps=steps)
        spec = compiler.compile(feat)
        validators = spec.acceptance_spec.validators
        assert len(validators) == len(steps) + 1

    def test_step7_step_validators_have_correct_descriptions(self, compiler):
        """Step 7: Each step validator's description matches the step text."""
        steps = ["Verify login", "Verify logout", "Verify session"]
        feat = _make_feature(steps=steps)
        spec = compiler.compile(feat)

        step_validators = [
            v for v in spec.acceptance_spec.validators
            if v.get("config", {}).get("name", "").startswith("step_")
        ]
        assert len(step_validators) == len(steps)
        for i, step in enumerate(steps):
            assert step_validators[i]["config"]["description"] == step

    def test_step7_step_validators_type_is_test_pass(self, compiler):
        """Step 7: Step-derived validators use 'test_pass' type."""
        feat = _make_feature(steps=["S1", "S2"])
        spec = compiler.compile(feat)
        step_validators = [
            v for v in spec.acceptance_spec.validators
            if v.get("config", {}).get("name", "").startswith("step_")
        ]
        for v in step_validators:
            assert v["type"] == "test_pass"

    def test_step7_feature_passing_validator_required(self, compiler):
        """Step 7: The 'feature_passing' validator is required=True."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        fp_validators = [
            v for v in spec.acceptance_spec.validators
            if v.get("config", {}).get("name") == "feature_passing"
        ]
        assert len(fp_validators) == 1
        assert fp_validators[0]["required"] is True

    def test_step7_feature_passing_validator_has_feature_id(self, compiler):
        """Step 7: 'feature_passing' validator references the correct feature id."""
        feat = _make_feature(id=77)
        spec = compiler.compile(feat)
        fp = [
            v for v in spec.acceptance_spec.validators
            if v.get("config", {}).get("name") == "feature_passing"
        ][0]
        assert fp["config"]["feature_id"] == 77

    def test_step7_empty_steps_produces_only_feature_passing(self, compiler):
        """Step 7: A feature with no steps still gets the feature_passing validator."""
        feat = _make_feature(steps=[])
        spec = compiler.compile(feat)
        assert len(spec.acceptance_spec.validators) == 1
        assert spec.acceptance_spec.validators[0]["config"]["name"] == "feature_passing"

    def test_step7_none_steps_handled(self, compiler):
        """Step 7: feature.steps=None does not crash; produces one validator."""
        feat = _make_feature(steps=None)
        spec = compiler.compile(feat)
        assert len(spec.acceptance_spec.validators) == 1

    def test_step7_gate_mode_is_all_pass(self, compiler):
        """Step 7: AcceptanceSpec gate_mode is 'all_pass'."""
        feat = _make_feature()
        spec = compiler.compile(feat)
        assert spec.acceptance_spec.gate_mode == "all_pass"

    def test_step7_testing_category_retry_policy_none(self, compiler):
        """Step 7: Testing task_type gets retry_policy='none' and max_retries=0."""
        feat = _make_feature(category="B. Testing")
        spec = compiler.compile(feat)
        assert spec.acceptance_spec.retry_policy == "none"
        assert spec.acceptance_spec.max_retries == 0

    def test_step7_coding_category_retry_policy_fixed(self, compiler):
        """Step 7: Non-testing task_types get retry_policy='fixed' and max_retries=2."""
        feat = _make_feature(category="A. Database")
        spec = compiler.compile(feat)
        assert spec.acceptance_spec.retry_policy == "fixed"
        assert spec.acceptance_spec.max_retries == 2

    def test_step7_validator_weights_sum_correctly(self, compiler):
        """Step 7: Step validator weights should each be 1/N."""
        steps = ["A", "B", "C", "D"]
        feat = _make_feature(steps=steps)
        spec = compiler.compile(feat)
        step_validators = [
            v for v in spec.acceptance_spec.validators
            if v.get("config", {}).get("name", "").startswith("step_")
        ]
        for v in step_validators:
            assert abs(v["weight"] - 1.0 / len(steps)) < 1e-9

    # -----------------------------------------------------------------
    # Step 8: source_feature_id links the AgentSpec back to the
    #         originating Feature record
    # -----------------------------------------------------------------

    def test_step8_source_feature_id_set(self, compiler):
        """Step 8: AgentSpec.source_feature_id == feature.id."""
        feat = _make_feature(id=42)
        spec = compiler.compile(feat)
        assert spec.source_feature_id == 42

    def test_step8_different_features_track_correctly(self, compiler):
        """Step 8: Different features produce different source_feature_ids."""
        ids = [10, 20, 30]
        for fid in ids:
            feat = _make_feature(id=fid)
            spec = compiler.compile(feat)
            assert spec.source_feature_id == fid

    def test_step8_context_also_contains_feature_id(self, compiler):
        """Step 8: The context dict mirrors the feature id for redundancy."""
        feat = _make_feature(id=99)
        spec = compiler.compile(feat)
        assert spec.context["feature_id"] == 99
        assert spec.context["feature_name"] == feat.name

    def test_step8_source_feature_id_survives_db_round_trip(
        self, db_session, db_engine
    ):
        """
        Step 8: After persisting and re-loading from the DB,
        source_feature_id is preserved.
        """
        # Create a real Feature row first (FK target)
        f = Feature(
            id=200,
            priority=1,
            category="A. Database",
            name="Round-trip test",
            description="Testing DB persistence.",
            steps=["S1"],
            passes=False,
            in_progress=False,
        )
        db_session.add(f)
        db_session.commit()

        compiler = FeatureCompiler()
        spec = compiler.compile(f)
        db_session.add(spec)
        if spec.acceptance_spec:
            db_session.add(spec.acceptance_spec)
        db_session.commit()

        loaded = db_session.query(AgentSpec).filter_by(id=spec.id).one()
        assert loaded.source_feature_id == 200

    # -----------------------------------------------------------------
    # Step 9 (DB integration): After a multi-feature run, query
    #         agent_specs table and confirm >= 3 distinct task_types
    # -----------------------------------------------------------------

    def test_step9_multi_feature_distinct_task_types(
        self, db_session, db_engine
    ):
        """
        Step 9: Compile and persist features from at least 3 categories
        that map to different task_types, then query the agent_specs table
        and verify >= 3 distinct task_type values.
        """
        # Create features with categories mapping to distinct task_types
        feature_defs = [
            # (id, category, expected task_type)
            (301, "A. Database",    "coding"),
            (302, "Security",       "audit"),
            (303, "Testing",        "testing"),
            (304, "Documentation",  "documentation"),
            (305, "Refactoring",    "refactoring"),
        ]

        compiler = FeatureCompiler()

        for fid, category, _expected_tt in feature_defs:
            f = Feature(
                id=fid,
                priority=fid,
                category=category,
                name=f"Feature {fid}",
                description=f"Description for feature {fid}.",
                steps=[f"Step 1 of {fid}"],
                passes=False,
                in_progress=False,
            )
            db_session.add(f)
        db_session.commit()

        # Compile and persist each
        for fid, category, expected_tt in feature_defs:
            feature = db_session.query(Feature).get(fid)
            spec = compiler.compile(feature)

            # Sanity-check mapping before persisting
            assert spec.task_type == expected_tt, (
                f"Feature {fid} ({category}) -> expected '{expected_tt}', "
                f"got '{spec.task_type}'"
            )

            db_session.add(spec)
            if spec.acceptance_spec:
                db_session.add(spec.acceptance_spec)
        db_session.commit()

        # Query for distinct task_types in agent_specs
        distinct_types = (
            db_session.query(AgentSpec.task_type)
            .distinct()
            .all()
        )
        distinct_type_values = {row[0] for row in distinct_types}

        assert len(distinct_type_values) >= 3, (
            f"Expected >= 3 distinct task_types, found {len(distinct_type_values)}: "
            f"{distinct_type_values}"
        )

        # Verify the exact expected types are present
        assert "coding" in distinct_type_values
        assert "audit" in distinct_type_values
        assert "testing" in distinct_type_values

    def test_step9_task_type_counts_in_db(self, db_session, db_engine):
        """
        Step 9 (extra): Verify per-task_type counts via GROUP BY after
        persisting multiple features.
        """
        compiler = FeatureCompiler()

        # Two coding, one testing, one audit
        feature_configs = [
            (401, "A. Database"),     # coding
            (402, "B. API"),          # coding
            (403, "Testing"),         # testing
            (404, "Security"),        # audit
        ]

        for fid, category in feature_configs:
            f = Feature(
                id=fid,
                priority=fid,
                category=category,
                name=f"F{fid}",
                description=f"Desc {fid}",
                steps=[f"s{fid}"],
                passes=False,
                in_progress=False,
            )
            db_session.add(f)
        db_session.commit()

        for fid, _cat in feature_configs:
            feature = db_session.query(Feature).get(fid)
            spec = compiler.compile(feature)
            db_session.add(spec)
            if spec.acceptance_spec:
                db_session.add(spec.acceptance_spec)
        db_session.commit()

        # GROUP BY task_type
        rows = (
            db_session.query(AgentSpec.task_type, func.count(AgentSpec.id))
            .group_by(AgentSpec.task_type)
            .all()
        )
        type_counts = {row[0]: row[1] for row in rows}

        assert type_counts.get("coding", 0) == 2
        assert type_counts.get("testing", 0) == 1
        assert type_counts.get("audit", 0) == 1
        assert len(type_counts) >= 3

    # -----------------------------------------------------------------
    # Additional cross-cutting assertions
    # -----------------------------------------------------------------

    def test_spec_version_always_v1(self, compiler):
        """Cross-cutting: spec_version is always 'v1'."""
        for cat in ["A. Database", "B. Testing", "Security"]:
            feat = _make_feature(category=cat)
            spec = compiler.compile(feat)
            assert spec.spec_version == "v1"

    def test_tags_include_task_type(self, compiler):
        """Cross-cutting: tags list includes the task_type."""
        feat = _make_feature(category="B. Testing")
        spec = compiler.compile(feat)
        assert "testing" in spec.tags

    def test_tags_include_feature_id(self, compiler):
        """Cross-cutting: tags list includes 'feature-{id}'."""
        feat = _make_feature(id=55)
        spec = compiler.compile(feat)
        assert "feature-55" in spec.tags

    def test_icon_matches_task_type(self, compiler):
        """Cross-cutting: icon corresponds to the task_type."""
        mapping = {
            "A. Database": "code",       # coding
            "B. Testing": "test-tube",   # testing
            "Documentation": "book",     # documentation
            "Refactoring": "wrench",     # refactoring
            "Security": "shield",        # audit
        }
        for cat, expected_icon in mapping.items():
            feat = _make_feature(category=cat)
            spec = compiler.compile(feat)
            assert spec.icon == expected_icon, (
                f"Category '{cat}' -> expected icon '{expected_icon}', "
                f"got '{spec.icon}'"
            )

    def test_compile_is_idempotent(self, compiler):
        """
        Cross-cutting: Compiling the same feature twice produces two
        distinct AgentSpecs with different IDs but identical task_type and
        budgets.
        """
        feat = _make_feature()
        spec_a = compiler.compile(feat)
        spec_b = compiler.compile(feat)

        assert spec_a.id != spec_b.id
        assert spec_a.task_type == spec_b.task_type
        assert spec_a.max_turns == spec_b.max_turns
        assert spec_a.timeout_seconds == spec_b.timeout_seconds
        assert spec_a.source_feature_id == spec_b.source_feature_id


# =============================================================================
# Run directly with: python -m pytest tests/test_feature_127_compiler_spec.py -v
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
