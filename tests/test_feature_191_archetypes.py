"""
Tests for Feature #191: Octo uses agent archetypes for common patterns
=====================================================================

This test suite verifies the agent archetype functionality including:
- Step 1: Define agent archetypes: coder, test-runner, auditor, reviewer
- Step 2: Each archetype has default tools, skills, and responsibilities
- Step 3: Octo recognizes when a capability maps to an archetype
- Step 4: Archetypes customized based on project-specific needs
- Step 5: Custom agents created when no archetype fits

Run with:
    pytest tests/test_feature_191_archetypes.py -v
"""
import pytest

from api.archetypes import (
    # Data classes
    AgentArchetype,
    ArchetypeMatchResult,
    CustomizedArchetype,
    # Constants
    AGENT_ARCHETYPES,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    # Core functions
    get_archetype,
    get_all_archetypes,
    get_archetype_names,
    archetype_exists,
    map_capability_to_archetype,
    is_custom_agent_needed,
    customize_archetype,
    create_agent_from_archetype,
    # Utility functions
    get_archetype_for_task_type,
    get_archetype_summary,
    _derive_skills_from_tech_stack,
    _score_archetype_match,
)


# =============================================================================
# Step 1: Define agent archetypes: coder, test-runner, auditor, reviewer
# =============================================================================

class TestStep1DefineArchetypes:
    """Tests for Feature #191 Step 1: Define agent archetypes."""

    def test_coder_archetype_exists(self):
        """Verify coder archetype is defined."""
        archetype = get_archetype("coder")
        assert archetype is not None
        assert archetype.name == "coder"
        assert archetype.display_name == "Coder Agent"

    def test_test_runner_archetype_exists(self):
        """Verify test-runner archetype is defined."""
        archetype = get_archetype("test-runner")
        assert archetype is not None
        assert archetype.name == "test-runner"
        assert archetype.display_name == "Test Runner Agent"

    def test_auditor_archetype_exists(self):
        """Verify auditor archetype is defined."""
        archetype = get_archetype("auditor")
        assert archetype is not None
        assert archetype.name == "auditor"
        assert archetype.display_name == "Auditor Agent"

    def test_reviewer_archetype_exists(self):
        """Verify reviewer archetype is defined."""
        archetype = get_archetype("reviewer")
        assert archetype is not None
        assert archetype.name == "reviewer"
        assert archetype.display_name == "Code Reviewer Agent"

    def test_all_required_archetypes_defined(self):
        """All four required archetypes are defined in AGENT_ARCHETYPES."""
        required = {"coder", "test-runner", "auditor", "reviewer"}
        defined = set(AGENT_ARCHETYPES.keys())
        assert required.issubset(defined), f"Missing archetypes: {required - defined}"

    def test_archetype_exists_function(self):
        """archetype_exists() correctly identifies defined archetypes."""
        assert archetype_exists("coder") is True
        assert archetype_exists("test-runner") is True
        assert archetype_exists("auditor") is True
        assert archetype_exists("reviewer") is True
        assert archetype_exists("nonexistent") is False

    def test_get_archetype_names(self):
        """get_archetype_names() returns all archetype names."""
        names = get_archetype_names()
        assert "coder" in names
        assert "test-runner" in names
        assert "auditor" in names
        assert "reviewer" in names

    def test_get_all_archetypes(self):
        """get_all_archetypes() returns all archetype objects."""
        archetypes = get_all_archetypes()
        assert len(archetypes) >= 4  # At least the four required
        assert all(isinstance(a, AgentArchetype) for a in archetypes)


# =============================================================================
# Step 2: Each archetype has default tools, skills, and responsibilities
# =============================================================================

class TestStep2DefaultAttributes:
    """Tests for Feature #191 Step 2: Default tools, skills, responsibilities."""

    def test_coder_has_default_tools(self):
        """Coder archetype has appropriate default tools."""
        coder = get_archetype("coder")
        assert coder is not None
        # Coder should have full toolset
        assert "Read" in coder.default_tools
        assert "Write" in coder.default_tools
        assert "Edit" in coder.default_tools
        assert "Bash" in coder.default_tools
        assert "Glob" in coder.default_tools
        assert "Grep" in coder.default_tools

    def test_coder_has_default_skills(self):
        """Coder archetype has appropriate default skills."""
        coder = get_archetype("coder")
        assert coder is not None
        assert len(coder.default_skills) > 0
        assert any("development" in skill.lower() for skill in coder.default_skills)

    def test_coder_has_responsibilities(self):
        """Coder archetype has defined responsibilities."""
        coder = get_archetype("coder")
        assert coder is not None
        assert len(coder.responsibilities) > 0
        assert any("implement" in r.lower() for r in coder.responsibilities)

    def test_test_runner_has_limited_tools(self):
        """Test-runner archetype has limited tools (no Edit for production code).

        Note: Feature #205 updated test-runner to include Write tool for writing
        test files. Edit is still excluded to prevent modifying production code.
        """
        runner = get_archetype("test-runner")
        assert runner is not None
        # Should have test-related tools
        assert "Read" in runner.default_tools
        assert "Bash" in runner.default_tools
        # Feature #205: Write is allowed for writing test files
        assert "Write" in runner.default_tools
        # Edit is excluded to prevent production code modification
        assert "Edit" in runner.excluded_tools

    def test_test_runner_has_testing_skills(self):
        """Test-runner archetype has testing-related skills."""
        runner = get_archetype("test-runner")
        assert runner is not None
        assert any("test" in skill.lower() for skill in runner.default_skills)

    def test_auditor_is_read_only(self):
        """Auditor archetype is strictly read-only."""
        auditor = get_archetype("auditor")
        assert auditor is not None
        # Should have read-only tools
        assert "Read" in auditor.default_tools
        assert "Glob" in auditor.default_tools
        assert "Grep" in auditor.default_tools
        # Should NOT have write/execute tools
        assert "Write" in auditor.excluded_tools
        assert "Edit" in auditor.excluded_tools
        assert "Bash" in auditor.excluded_tools

    def test_auditor_has_security_skills(self):
        """Auditor archetype has security-related skills."""
        auditor = get_archetype("auditor")
        assert auditor is not None
        assert any("security" in skill.lower() for skill in auditor.default_skills)

    def test_reviewer_has_review_responsibilities(self):
        """Reviewer archetype has code review responsibilities."""
        reviewer = get_archetype("reviewer")
        assert reviewer is not None
        assert any("review" in r.lower() for r in reviewer.responsibilities)

    def test_all_archetypes_have_required_fields(self):
        """All archetypes have all required fields populated."""
        for name, archetype in AGENT_ARCHETYPES.items():
            assert archetype.name, f"{name}: name is empty"
            assert archetype.display_name, f"{name}: display_name is empty"
            assert archetype.description, f"{name}: description is empty"
            assert len(archetype.default_tools) > 0, f"{name}: default_tools is empty"
            assert len(archetype.default_skills) > 0, f"{name}: default_skills is empty"
            assert len(archetype.responsibilities) > 0, f"{name}: responsibilities is empty"
            assert archetype.recommended_model in ("sonnet", "opus", "haiku"), f"{name}: invalid model"
            assert archetype.task_type, f"{name}: task_type is empty"
            assert archetype.max_turns > 0, f"{name}: invalid max_turns"
            assert archetype.timeout_seconds > 0, f"{name}: invalid timeout_seconds"


# =============================================================================
# Step 3: Octo recognizes when a capability maps to an archetype
# =============================================================================

class TestStep3CapabilityMapping:
    """Tests for Feature #191 Step 3: Capability-to-archetype mapping."""

    def test_map_coding_capability_to_coder(self):
        """'coding' capability maps to coder archetype."""
        result = map_capability_to_archetype("coding")
        assert result.archetype_name == "coder"
        assert result.archetype is not None
        assert result.confidence > 0
        assert result.is_custom_needed is False

    def test_map_testing_capability_to_test_runner(self):
        """Testing capabilities map to test-runner archetype."""
        result = map_capability_to_archetype("testing")
        assert result.archetype_name == "test-runner"
        assert result.is_custom_needed is False

    def test_map_e2e_testing_to_e2e_tester(self):
        """'e2e_testing' capability maps to e2e-tester archetype."""
        result = map_capability_to_archetype("e2e_testing")
        assert result.archetype_name == "e2e-tester"
        assert result.is_custom_needed is False

    def test_map_security_audit_to_auditor(self):
        """'security_audit' capability maps to auditor archetype."""
        result = map_capability_to_archetype("security_audit")
        assert result.archetype_name == "auditor"
        assert result.is_custom_needed is False

    def test_map_code_review_to_reviewer(self):
        """'code_review' capability maps to reviewer archetype."""
        result = map_capability_to_archetype("code_review")
        assert result.archetype_name == "reviewer"
        assert result.is_custom_needed is False

    def test_map_documentation_to_documenter(self):
        """'documentation' capability maps to documenter archetype."""
        result = map_capability_to_archetype("documentation")
        assert result.archetype_name == "documenter"
        assert result.is_custom_needed is False

    def test_high_confidence_match(self):
        """Exact keyword matches produce high confidence scores."""
        result = map_capability_to_archetype("coder")
        assert result.confidence >= MEDIUM_CONFIDENCE_THRESHOLD

    def test_task_type_hint_improves_matching(self):
        """Task type hint improves matching confidence."""
        # Without task type hint
        result_no_hint = map_capability_to_archetype("implementation")
        # With task type hint
        result_with_hint = map_capability_to_archetype("implementation", task_type="coding")
        # Hint should improve confidence
        assert result_with_hint.confidence >= result_no_hint.confidence

    def test_result_includes_matched_keywords(self):
        """ArchetypeMatchResult includes matched keywords."""
        result = map_capability_to_archetype("e2e_testing")
        assert len(result.matched_keywords) > 0

    def test_result_includes_reason(self):
        """ArchetypeMatchResult includes human-readable reason."""
        result = map_capability_to_archetype("coding")
        assert result.reason != ""


# =============================================================================
# Step 4: Archetypes customized based on project-specific needs
# =============================================================================

class TestStep4ProjectCustomization:
    """Tests for Feature #191 Step 4: Project-specific customization."""

    def test_customize_adds_tech_stack_skills(self):
        """Customization adds skills from tech stack."""
        customized = customize_archetype(
            "coder",
            project_context={"tech_stack": ["React", "TypeScript"]},
        )
        assert customized is not None
        # Should have added React/TypeScript skills
        assert any("react" in s.lower() for s in customized.skills)
        assert any("typescript" in s.lower() for s in customized.skills)

    def test_customize_adds_playwright_browser_tools(self):
        """Customization adds browser tools when Playwright in tech stack."""
        customized = customize_archetype(
            "coder",
            project_context={"tech_stack": ["Playwright", "React"]},
        )
        assert customized is not None
        # Should have browser tools
        assert "browser_navigate" in customized.tools
        assert "browser_click" in customized.tools

    def test_customize_respects_model_constraint(self):
        """Customization respects model constraint override."""
        customized = customize_archetype(
            "coder",
            constraints={"model": "opus"},
        )
        assert customized is not None
        assert customized.model == "opus"

    def test_customize_respects_max_turns_limit(self):
        """Customization respects max_turns budget constraint."""
        customized = customize_archetype(
            "coder",
            constraints={"max_turns_limit": 50},
        )
        assert customized is not None
        assert customized.max_turns <= 50

    def test_customize_respects_timeout_limit(self):
        """Customization respects timeout budget constraint."""
        customized = customize_archetype(
            "coder",
            constraints={"timeout_limit": 600},
        )
        assert customized is not None
        assert customized.timeout_seconds <= 600

    def test_customize_respects_project_settings_model(self):
        """Customization respects model from project settings."""
        customized = customize_archetype(
            "coder",
            project_context={"settings": {"model": "haiku"}},
        )
        assert customized is not None
        assert customized.model == "haiku"

    def test_customize_adds_additional_tools_from_settings(self):
        """Customization adds tools from project settings."""
        customized = customize_archetype(
            "documenter",
            project_context={"settings": {"additional_tools": ["CustomTool"]}},
        )
        assert customized is not None
        assert "CustomTool" in customized.tools

    def test_customize_respects_excluded_tools(self):
        """Customization does not add excluded tools."""
        customized = customize_archetype(
            "auditor",
            project_context={"settings": {"additional_tools": ["Write", "Edit", "Bash"]}},
        )
        assert customized is not None
        # Auditor excludes these tools
        assert "Write" not in customized.tools
        assert "Edit" not in customized.tools
        assert "Bash" not in customized.tools

    def test_customize_tracks_applied_customizations(self):
        """Customization tracks which changes were made."""
        customized = customize_archetype(
            "coder",
            project_context={"tech_stack": ["React"]},
            constraints={"model": "opus"},
        )
        assert customized is not None
        assert len(customized.customizations_applied) > 0

    def test_customize_returns_none_for_invalid_archetype(self):
        """Customization returns None for non-existent archetype."""
        customized = customize_archetype("nonexistent")
        assert customized is None


# =============================================================================
# Step 5: Custom agents created when no archetype fits
# =============================================================================

class TestStep5CustomAgentFallback:
    """Tests for Feature #191 Step 5: Custom agents when no archetype fits."""

    def test_unknown_capability_needs_custom_agent(self):
        """Unknown capability returns is_custom_needed=True."""
        result = map_capability_to_archetype("quantum_computing_optimization")
        assert result.is_custom_needed is True
        assert result.archetype_name is None
        assert result.archetype is None

    def test_is_custom_agent_needed_function(self):
        """is_custom_agent_needed() correctly identifies custom needs."""
        # Known capabilities should not need custom agent
        assert is_custom_agent_needed("coding") is False
        assert is_custom_agent_needed("testing") is False
        # Unknown capabilities should need custom agent
        # Use obscure capabilities that don't match any archetype keywords
        assert is_custom_agent_needed("quantum_physics_simulation") is True

    def test_very_obscure_capability_needs_custom(self):
        """Very obscure capabilities need custom agents."""
        result = map_capability_to_archetype("telepathic_debugging")
        assert result.is_custom_needed is True

    def test_low_confidence_match_not_custom(self):
        """Low confidence match still returns archetype, not custom."""
        # "implement" partially matches "coder"
        result = map_capability_to_archetype("implement")
        # Should still match with low confidence, not custom
        if result.confidence >= LOW_CONFIDENCE_THRESHOLD:
            assert result.is_custom_needed is False
            assert result.archetype is not None


# =============================================================================
# Data Classes and Serialization
# =============================================================================

class TestDataClasses:
    """Tests for data class functionality and serialization."""

    def test_agent_archetype_to_dict(self):
        """AgentArchetype.to_dict() serializes correctly."""
        archetype = get_archetype("coder")
        assert archetype is not None
        data = archetype.to_dict()
        assert data["name"] == "coder"
        assert "default_tools" in data
        assert "default_skills" in data
        assert "responsibilities" in data
        assert "recommended_model" in data

    def test_agent_archetype_from_dict(self):
        """AgentArchetype.from_dict() deserializes correctly."""
        original = get_archetype("coder")
        assert original is not None
        data = original.to_dict()
        restored = AgentArchetype.from_dict(data)
        assert restored.name == original.name
        assert restored.default_tools == original.default_tools
        assert restored.default_skills == original.default_skills

    def test_archetype_match_result_to_dict(self):
        """ArchetypeMatchResult.to_dict() serializes correctly."""
        result = map_capability_to_archetype("coding")
        data = result.to_dict()
        assert "archetype_name" in data
        assert "confidence" in data
        assert "is_custom_needed" in data
        assert "reason" in data

    def test_customized_archetype_to_dict(self):
        """CustomizedArchetype.to_dict() serializes correctly."""
        customized = customize_archetype("coder")
        assert customized is not None
        data = customized.to_dict()
        assert "base_archetype" in data
        assert "tools" in data
        assert "skills" in data
        assert "model" in data


# =============================================================================
# Utility Functions
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_archetype_for_task_type_coding(self):
        """get_archetype_for_task_type() returns coder for 'coding'."""
        archetype = get_archetype_for_task_type("coding")
        assert archetype is not None
        assert archetype.name == "coder"

    def test_get_archetype_for_task_type_testing(self):
        """get_archetype_for_task_type() returns test-runner for 'testing'."""
        archetype = get_archetype_for_task_type("testing")
        assert archetype is not None
        assert archetype.name == "test-runner"

    def test_get_archetype_for_task_type_audit(self):
        """get_archetype_for_task_type() returns auditor for 'audit'."""
        archetype = get_archetype_for_task_type("audit")
        assert archetype is not None
        assert archetype.name == "auditor"

    def test_get_archetype_for_task_type_documentation(self):
        """get_archetype_for_task_type() returns documenter for 'documentation'."""
        archetype = get_archetype_for_task_type("documentation")
        assert archetype is not None
        assert archetype.name == "documenter"

    def test_get_archetype_for_task_type_unknown(self):
        """get_archetype_for_task_type() returns None for unknown task type."""
        archetype = get_archetype_for_task_type("unknown_task")
        assert archetype is None

    def test_get_archetype_summary(self):
        """get_archetype_summary() returns summary for all archetypes."""
        summary = get_archetype_summary()
        assert "coder" in summary
        assert "test-runner" in summary
        assert "display_name" in summary["coder"]
        assert "task_type" in summary["coder"]
        assert "icon" in summary["coder"]

    def test_derive_skills_from_tech_stack(self):
        """_derive_skills_from_tech_stack() extracts relevant skills."""
        skills = _derive_skills_from_tech_stack(["React", "TypeScript", "PostgreSQL"])
        assert any("react" in s.lower() for s in skills)
        assert any("typescript" in s.lower() for s in skills)
        assert any("postgresql" in s.lower() or "sql" in s.lower() for s in skills)

    def test_derive_skills_from_empty_tech_stack(self):
        """_derive_skills_from_tech_stack() handles empty tech stack."""
        skills = _derive_skills_from_tech_stack([])
        assert skills == []


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for archetype functionality."""

    def test_create_agent_from_archetype(self):
        """create_agent_from_archetype() creates valid agent spec dict."""
        spec = create_agent_from_archetype(
            archetype_name="coder",
            agent_name="my-coder",
            objective="Implement the new feature",
        )
        assert spec is not None
        assert spec["name"] == "my-coder"
        assert spec["objective"] == "Implement the new feature"
        assert spec["task_type"] == "coding"
        assert len(spec["tools"]) > 0
        assert "context" in spec
        assert spec["context"]["archetype"] == "coder"

    def test_create_agent_with_customization(self):
        """create_agent_from_archetype() applies project customization."""
        spec = create_agent_from_archetype(
            archetype_name="coder",
            agent_name="react-coder",
            objective="Build React components",
            project_context={"tech_stack": ["React", "TypeScript"]},
        )
        assert spec is not None
        # Should have React skills
        assert any("react" in s.lower() for s in spec["skills"])

    def test_create_agent_returns_none_for_invalid_archetype(self):
        """create_agent_from_archetype() returns None for invalid archetype."""
        spec = create_agent_from_archetype(
            archetype_name="nonexistent",
            agent_name="test",
            objective="Test objective",
        )
        assert spec is None

    def test_full_workflow_capability_to_agent(self):
        """Full workflow: map capability -> customize archetype -> create agent."""
        # Step 1: Map capability to archetype
        match = map_capability_to_archetype("e2e_testing")
        assert match.archetype is not None
        assert match.is_custom_needed is False

        # Step 2: Customize archetype
        customized = customize_archetype(
            match.archetype_name,
            project_context={
                "tech_stack": ["Playwright", "React"],
                "name": "MyProject",
            },
        )
        assert customized is not None
        assert "browser_navigate" in customized.tools

        # Step 3: Create agent
        spec = create_agent_from_archetype(
            archetype_name=match.archetype_name,
            agent_name="myproject-e2e-tester",
            objective="Run E2E tests for MyProject",
            project_context={
                "tech_stack": ["Playwright", "React"],
                "name": "MyProject",
            },
        )
        assert spec is not None
        assert spec["task_type"] == "testing"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_get_archetype_with_underscore(self):
        """get_archetype() normalizes underscores to hyphens."""
        archetype = get_archetype("test_runner")
        assert archetype is not None
        assert archetype.name == "test-runner"

    def test_capability_mapping_case_insensitive(self):
        """Capability mapping is case-insensitive."""
        result1 = map_capability_to_archetype("CODING")
        result2 = map_capability_to_archetype("coding")
        result3 = map_capability_to_archetype("Coding")
        # All should match the same archetype
        assert result1.archetype_name == result2.archetype_name == result3.archetype_name

    def test_capability_mapping_handles_spaces(self):
        """Capability mapping handles spaces and underscores."""
        result1 = map_capability_to_archetype("e2e testing")
        result2 = map_capability_to_archetype("e2e_testing")
        result3 = map_capability_to_archetype("e2e-testing")
        # All should match e2e-tester
        assert result1.archetype_name == "e2e-tester"
        assert result2.archetype_name == "e2e-tester"
        assert result3.archetype_name == "e2e-tester"

    def test_empty_capability(self):
        """Empty capability string returns custom needed."""
        result = map_capability_to_archetype("")
        assert result.is_custom_needed is True

    def test_customize_with_none_contexts(self):
        """Customization handles None contexts gracefully."""
        customized = customize_archetype(
            "coder",
            project_context=None,
            constraints=None,
        )
        assert customized is not None
        assert customized.tools == get_archetype("coder").default_tools

    def test_customize_with_empty_contexts(self):
        """Customization handles empty contexts gracefully."""
        customized = customize_archetype(
            "coder",
            project_context={},
            constraints={},
        )
        assert customized is not None


# =============================================================================
# API Package Export Tests
# =============================================================================

class TestApiPackageExports:
    """Tests that all archetype exports are available from api package."""

    def test_data_classes_exported(self):
        """Data classes are exported from api package."""
        from api import AgentArchetype, ArchetypeMatchResult, CustomizedArchetype
        assert AgentArchetype is not None
        assert ArchetypeMatchResult is not None
        assert CustomizedArchetype is not None

    def test_constants_exported(self):
        """Constants are exported from api package."""
        from api import (
            AGENT_ARCHETYPES,
            HIGH_CONFIDENCE_THRESHOLD,
            MEDIUM_CONFIDENCE_THRESHOLD,
            LOW_CONFIDENCE_THRESHOLD,
        )
        assert AGENT_ARCHETYPES is not None
        assert HIGH_CONFIDENCE_THRESHOLD > 0
        assert MEDIUM_CONFIDENCE_THRESHOLD > 0
        assert LOW_CONFIDENCE_THRESHOLD > 0

    def test_core_functions_exported(self):
        """Core functions are exported from api package."""
        from api import (
            get_archetype,
            get_all_archetypes,
            get_archetype_names,
            archetype_exists,
            map_capability_to_archetype,
            is_custom_agent_needed,
            customize_archetype,
            create_agent_from_archetype,
        )
        assert callable(get_archetype)
        assert callable(get_all_archetypes)
        assert callable(get_archetype_names)
        assert callable(archetype_exists)
        assert callable(map_capability_to_archetype)
        assert callable(is_custom_agent_needed)
        assert callable(customize_archetype)
        assert callable(create_agent_from_archetype)

    def test_utility_functions_exported(self):
        """Utility functions are exported from api package."""
        from api import (
            get_archetype_for_task_type,
            get_archetype_summary,
        )
        assert callable(get_archetype_for_task_type)
        assert callable(get_archetype_summary)


# =============================================================================
# Feature #191 Verification Steps (Comprehensive)
# =============================================================================

class TestFeature191VerificationSteps:
    """
    Comprehensive tests verifying all 5 feature steps.
    These tests serve as acceptance criteria for Feature #191.
    """

    def test_step_1_archetypes_defined(self):
        """
        Step 1: Define agent archetypes: coder, test-runner, auditor, reviewer

        Verify all four required archetypes are defined with proper structure.
        """
        # Required archetypes
        required_archetypes = ["coder", "test-runner", "auditor", "reviewer"]

        for name in required_archetypes:
            archetype = get_archetype(name)
            assert archetype is not None, f"Archetype '{name}' not defined"
            assert archetype.name == name, f"Archetype name mismatch for '{name}'"
            assert archetype.display_name, f"Archetype '{name}' has no display_name"
            assert archetype.description, f"Archetype '{name}' has no description"

    def test_step_2_default_attributes(self):
        """
        Step 2: Each archetype has default tools, skills, and responsibilities

        Verify each archetype has non-empty defaults for all three attributes.
        """
        for name, archetype in AGENT_ARCHETYPES.items():
            assert len(archetype.default_tools) > 0, f"'{name}' has no default_tools"
            assert len(archetype.default_skills) > 0, f"'{name}' has no default_skills"
            assert len(archetype.responsibilities) > 0, f"'{name}' has no responsibilities"

    def test_step_3_capability_mapping(self):
        """
        Step 3: Octo recognizes when a capability maps to an archetype

        Verify various capabilities correctly map to appropriate archetypes.
        """
        test_cases = [
            ("coding", "coder"),
            ("implement", "coder"),
            ("testing", "test-runner"),
            ("qa", "test-runner"),
            ("security_audit", "auditor"),
            ("vulnerability", "auditor"),
            ("code_review", "reviewer"),
            ("pr_review", "reviewer"),
            ("e2e_testing", "e2e-tester"),
            ("documentation", "documenter"),
        ]

        for capability, expected_archetype in test_cases:
            result = map_capability_to_archetype(capability)
            assert result.archetype_name == expected_archetype, (
                f"Capability '{capability}' mapped to '{result.archetype_name}', "
                f"expected '{expected_archetype}'"
            )

    def test_step_4_project_customization(self):
        """
        Step 4: Archetypes customized based on project-specific needs

        Verify customization modifies archetypes based on project context.
        """
        # Test tech stack customization
        customized = customize_archetype(
            "coder",
            project_context={
                "tech_stack": ["React", "TypeScript", "Playwright"],
            },
        )
        assert customized is not None

        # Skills should include React
        assert any("react" in s.lower() for s in customized.skills)

        # Tools should include browser tools for Playwright
        assert "browser_navigate" in customized.tools

        # Test constraint customization
        customized2 = customize_archetype(
            "coder",
            constraints={"model": "opus", "max_turns_limit": 50},
        )
        assert customized2.model == "opus"
        assert customized2.max_turns <= 50

    def test_step_5_custom_agents(self):
        """
        Step 5: Custom agents created when no archetype fits

        Verify unknown capabilities return is_custom_needed=True.
        """
        # Completely unknown capability (no keywords match any archetype)
        result = map_capability_to_archetype("quantum_entanglement_physics")
        assert result.is_custom_needed is True
        assert result.archetype is None

        # Another unknown capability
        result2 = map_capability_to_archetype("telepathic_debugging")
        assert result2.is_custom_needed is True

        # Verify is_custom_agent_needed helper
        # Use truly obscure capabilities that don't match any archetype keywords
        assert is_custom_agent_needed("quantum_physics_simulation") is True
        assert is_custom_agent_needed("coding") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
