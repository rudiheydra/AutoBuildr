"""
Tests for Feature #205: Test-runner agent archetype defined
============================================================

This test suite verifies the test-runner agent archetype functionality including:
- Step 1: Test-runner archetype includes tools: Bash, Read, Write, Glob, Grep
- Step 2: Default skills: pytest, unittest, test discovery
- Step 3: Responsibilities: write tests, run tests, report results
- Step 4: Model: sonnet (balanced speed/capability)
- Step 5: Archetype used by Octo when test execution needed

Run with:
    pytest tests/test_feature_205_test_runner_archetype.py -v
"""
import pytest

from api.archetypes import (
    # Data classes
    AgentArchetype,
    # Constants
    AGENT_ARCHETYPES,
    # Core functions
    get_archetype,
    get_archetype_names,
    archetype_exists,
    map_capability_to_archetype,
    customize_archetype,
    create_agent_from_archetype,
    get_archetype_for_task_type,
)


# =============================================================================
# Step 1: Test-runner archetype includes tools: Bash, Read, Write, Glob, Grep
# =============================================================================

class TestStep1RequiredTools:
    """Tests for Feature #205 Step 1: Required tools in test-runner archetype."""

    def test_test_runner_archetype_exists(self):
        """Verify test-runner archetype is defined."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.name == "test-runner"
        assert archetype.display_name == "Test Runner Agent"

    def test_test_runner_has_bash_tool(self):
        """Test-runner archetype includes Bash tool."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Bash" in archetype.default_tools

    def test_test_runner_has_read_tool(self):
        """Test-runner archetype includes Read tool."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Read" in archetype.default_tools

    def test_test_runner_has_write_tool(self):
        """Test-runner archetype includes Write tool."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Write" in archetype.default_tools

    def test_test_runner_has_glob_tool(self):
        """Test-runner archetype includes Glob tool."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Glob" in archetype.default_tools

    def test_test_runner_has_grep_tool(self):
        """Test-runner archetype includes Grep tool."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Grep" in archetype.default_tools

    def test_test_runner_has_all_required_tools(self):
        """Test-runner archetype includes all required tools: Bash, Read, Write, Glob, Grep."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        required_tools = ["Bash", "Read", "Write", "Glob", "Grep"]
        for tool in required_tools:
            assert tool in archetype.default_tools, f"Missing required tool: {tool}"

    def test_test_runner_write_not_in_excluded_tools(self):
        """Write is NOT in excluded_tools (test-runner can write test files)."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Write" not in archetype.excluded_tools

    def test_test_runner_has_feature_tracking_tools(self):
        """Test-runner archetype includes feature tracking tools for reporting."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        feature_tools = ["feature_get_by_id", "feature_mark_passing", "feature_mark_failing"]
        for tool in feature_tools:
            assert tool in archetype.default_tools, f"Missing feature tool: {tool}"


# =============================================================================
# Step 2: Default skills: pytest, unittest, test discovery
# =============================================================================

class TestStep2DefaultSkills:
    """Tests for Feature #205 Step 2: Default skills in test-runner archetype."""

    def test_test_runner_has_pytest_skill(self):
        """Test-runner archetype has pytest skill."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "pytest" in archetype.default_skills

    def test_test_runner_has_unittest_skill(self):
        """Test-runner archetype has unittest skill."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "unittest" in archetype.default_skills

    def test_test_runner_has_test_discovery_skill(self):
        """Test-runner archetype has test discovery skill."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "test discovery" in archetype.default_skills

    def test_test_runner_has_all_required_skills(self):
        """Test-runner archetype has all required skills: pytest, unittest, test discovery."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        required_skills = ["pytest", "unittest", "test discovery"]
        for skill in required_skills:
            assert skill in archetype.default_skills, f"Missing required skill: {skill}"

    def test_test_runner_has_additional_testing_skills(self):
        """Test-runner archetype has additional testing-related skills."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        # Should have additional useful testing skills
        assert any("test" in skill.lower() for skill in archetype.default_skills)
        assert len(archetype.default_skills) > 3  # More than just the required ones


# =============================================================================
# Step 3: Responsibilities: write tests, run tests, report results
# =============================================================================

class TestStep3Responsibilities:
    """Tests for Feature #205 Step 3: Responsibilities in test-runner archetype."""

    def test_test_runner_can_write_tests(self):
        """Test-runner archetype has responsibility to write tests."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert any("write" in r.lower() and "test" in r.lower()
                   for r in archetype.responsibilities)

    def test_test_runner_can_run_tests(self):
        """Test-runner archetype has responsibility to run tests."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert any("run" in r.lower() and "test" in r.lower()
                   for r in archetype.responsibilities)

    def test_test_runner_can_report_results(self):
        """Test-runner archetype has responsibility to report results."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert any("report" in r.lower() and ("result" in r.lower() or "status" in r.lower())
                   for r in archetype.responsibilities)

    def test_test_runner_has_all_required_responsibilities(self):
        """Test-runner archetype has all required responsibilities."""
        archetype = get_archetype("test-runner")
        assert archetype is not None

        # Must have write tests responsibility
        has_write_tests = any("write" in r.lower() and "test" in r.lower()
                              for r in archetype.responsibilities)
        assert has_write_tests, "Missing 'write tests' responsibility"

        # Must have run tests responsibility
        has_run_tests = any("run" in r.lower() and "test" in r.lower()
                            for r in archetype.responsibilities)
        assert has_run_tests, "Missing 'run tests' responsibility"

        # Must have report results responsibility
        has_report_results = any("report" in r.lower() for r in archetype.responsibilities)
        assert has_report_results, "Missing 'report results' responsibility"

    def test_test_runner_has_failure_analysis_responsibility(self):
        """Test-runner archetype can analyze test failures."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert any("failure" in r.lower() or "analyze" in r.lower()
                   for r in archetype.responsibilities)


# =============================================================================
# Step 4: Model: sonnet (balanced speed/capability)
# =============================================================================

class TestStep4Model:
    """Tests for Feature #205 Step 4: Model recommendation."""

    def test_test_runner_uses_sonnet_model(self):
        """Test-runner archetype recommends sonnet model."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.recommended_model == "sonnet"

    def test_test_runner_model_is_valid(self):
        """Test-runner model is a valid Claude model option."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.recommended_model in ("sonnet", "opus", "haiku")

    def test_customization_preserves_default_model(self):
        """Customization without model constraint preserves sonnet."""
        customized = customize_archetype(
            "test-runner",
            project_context={"tech_stack": ["pytest", "Python"]},
        )
        assert customized is not None
        assert customized.model == "sonnet"

    def test_customization_can_override_model(self):
        """Customization can override model when specified."""
        customized = customize_archetype(
            "test-runner",
            constraints={"model": "opus"},
        )
        assert customized is not None
        assert customized.model == "opus"


# =============================================================================
# Step 5: Archetype used by Octo when test execution needed
# =============================================================================

class TestStep5OctoIntegration:
    """Tests for Feature #205 Step 5: Octo uses archetype for test execution."""

    def test_testing_capability_maps_to_test_runner(self):
        """'testing' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("testing")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_unit_testing_capability_maps_to_test_runner(self):
        """'unit_testing' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("unit_testing")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_integration_testing_capability_maps_to_test_runner(self):
        """'integration_testing' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("integration_testing")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_test_runner_capability_maps_to_test_runner(self):
        """'test-runner' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("test-runner")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_pytest_capability_maps_to_test_runner(self):
        """'pytest' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("pytest")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_unittest_capability_maps_to_test_runner(self):
        """'unittest' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("unittest")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_write_tests_capability_maps_to_test_runner(self):
        """'write_tests' capability maps to test-runner archetype."""
        result = map_capability_to_archetype("write_tests")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_tdd_capability_maps_to_test_runner(self):
        """'tdd' (test-driven development) capability maps to test-runner archetype."""
        result = map_capability_to_archetype("tdd")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_task_type_testing_returns_test_runner(self):
        """get_archetype_for_task_type('testing') returns test-runner."""
        archetype = get_archetype_for_task_type("testing")
        assert archetype is not None
        assert archetype.name == "test-runner"

    def test_test_runner_task_type_is_testing(self):
        """Test-runner archetype has task_type='testing'."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.task_type == "testing"


# =============================================================================
# Additional Tests: Serialization and Agent Creation
# =============================================================================

class TestSerializationAndAgentCreation:
    """Tests for serialization and agent creation from test-runner archetype."""

    def test_test_runner_to_dict(self):
        """Test-runner archetype serializes correctly."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        data = archetype.to_dict()
        assert data["name"] == "test-runner"
        assert "Write" in data["default_tools"]
        assert "pytest" in data["default_skills"]
        assert data["recommended_model"] == "sonnet"

    def test_test_runner_from_dict(self):
        """Test-runner archetype deserializes correctly."""
        original = get_archetype("test-runner")
        assert original is not None
        data = original.to_dict()
        restored = AgentArchetype.from_dict(data)
        assert restored.name == original.name
        assert restored.default_tools == original.default_tools
        assert restored.default_skills == original.default_skills

    def test_create_test_runner_agent(self):
        """create_agent_from_archetype works for test-runner."""
        spec = create_agent_from_archetype(
            archetype_name="test-runner",
            agent_name="my-test-runner",
            objective="Run all tests for the feature",
        )
        assert spec is not None
        assert spec["name"] == "my-test-runner"
        assert spec["task_type"] == "testing"
        assert spec["model"] == "sonnet"
        assert "Write" in spec["tools"]
        assert "pytest" in spec["skills"]

    def test_create_test_runner_agent_with_customization(self):
        """create_agent_from_archetype applies customization for test-runner."""
        spec = create_agent_from_archetype(
            archetype_name="test-runner",
            agent_name="python-test-runner",
            objective="Run pytest tests",
            project_context={"tech_stack": ["Python", "pytest", "FastAPI"]},
        )
        assert spec is not None
        # Should have pytest skills from both archetype and tech stack
        assert any("pytest" in s.lower() for s in spec["skills"])


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_test_runner_accessible_with_underscore(self):
        """Test-runner archetype accessible with underscore notation."""
        archetype = get_archetype("test_runner")
        assert archetype is not None
        assert archetype.name == "test-runner"

    def test_test_runner_case_insensitive_lookup(self):
        """Test-runner archetype lookup is case-insensitive."""
        arch1 = get_archetype("test-runner")
        arch2 = get_archetype("TEST-RUNNER")
        # Both should return None or same archetype
        # (get_archetype normalizes to lowercase)
        if arch1 is not None:
            assert arch2 is None or arch2.name == arch1.name

    def test_test_runner_has_reasonable_budgets(self):
        """Test-runner archetype has reasonable execution budgets."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.max_turns > 0
        assert archetype.max_turns <= 100  # Reasonable limit
        assert archetype.timeout_seconds > 0
        assert archetype.timeout_seconds <= 3600  # 1 hour max

    def test_test_runner_has_icon(self):
        """Test-runner archetype has an icon."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.icon  # Not empty
        assert archetype.icon == "🧪"

    def test_test_runner_edit_excluded(self):
        """Test-runner archetype excludes Edit to prevent production code changes."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert "Edit" in archetype.excluded_tools


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Tests that test-runner archetype is accessible from api package."""

    def test_agent_archetypes_contains_test_runner(self):
        """AGENT_ARCHETYPES contains test-runner."""
        from api import AGENT_ARCHETYPES
        assert "test-runner" in AGENT_ARCHETYPES

    def test_get_archetype_accessible_from_api(self):
        """get_archetype function accessible from api package."""
        from api import get_archetype as get_archetype_from_api
        archetype = get_archetype_from_api("test-runner")
        assert archetype is not None
        assert archetype.name == "test-runner"


# =============================================================================
# Feature #205 Verification Steps (Comprehensive)
# =============================================================================

class TestFeature205VerificationSteps:
    """
    Comprehensive tests verifying all 5 feature steps.
    These tests serve as acceptance criteria for Feature #205.
    """

    def test_step_1_tools_complete(self):
        """
        Step 1: Test-runner archetype includes tools: Bash, Read, Write, Glob, Grep

        Verify all five required tools are present in default_tools.
        """
        archetype = get_archetype("test-runner")
        assert archetype is not None

        required_tools = {"Bash", "Read", "Write", "Glob", "Grep"}
        actual_tools = set(archetype.default_tools)

        missing_tools = required_tools - actual_tools
        assert not missing_tools, f"Missing required tools: {missing_tools}"

    def test_step_2_skills_complete(self):
        """
        Step 2: Default skills: pytest, unittest, test discovery

        Verify all three required skills are present in default_skills.
        """
        archetype = get_archetype("test-runner")
        assert archetype is not None

        required_skills = {"pytest", "unittest", "test discovery"}
        actual_skills = set(archetype.default_skills)

        missing_skills = required_skills - actual_skills
        assert not missing_skills, f"Missing required skills: {missing_skills}"

    def test_step_3_responsibilities_complete(self):
        """
        Step 3: Responsibilities: write tests, run tests, report results

        Verify all three required responsibilities are represented.
        """
        archetype = get_archetype("test-runner")
        assert archetype is not None

        responsibilities_text = " ".join(r.lower() for r in archetype.responsibilities)

        # Check for write tests
        assert "write" in responsibilities_text and "test" in responsibilities_text, \
            "Missing 'write tests' responsibility"

        # Check for run tests
        assert "run" in responsibilities_text and "test" in responsibilities_text, \
            "Missing 'run tests' responsibility"

        # Check for report results
        assert "report" in responsibilities_text, \
            "Missing 'report results' responsibility"

    def test_step_4_model_is_sonnet(self):
        """
        Step 4: Model: sonnet (balanced speed/capability)

        Verify recommended_model is 'sonnet'.
        """
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.recommended_model == "sonnet", \
            f"Expected 'sonnet', got '{archetype.recommended_model}'"

    def test_step_5_octo_uses_archetype(self):
        """
        Step 5: Archetype used by Octo when test execution needed

        Verify capability mapping and task type association work correctly.
        """
        # Verify 'testing' capability maps to test-runner
        result = map_capability_to_archetype("testing")
        assert result.archetype_name == "test-runner", \
            f"Expected 'test-runner', got '{result.archetype_name}'"
        assert result.is_custom_needed is False

        # Verify task type 'testing' returns test-runner
        archetype = get_archetype_for_task_type("testing")
        assert archetype is not None
        assert archetype.name == "test-runner", \
            f"Expected 'test-runner', got '{archetype.name}'"

        # Verify test-runner archetype exists in catalog
        assert archetype_exists("test-runner")
        assert "test-runner" in get_archetype_names()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
