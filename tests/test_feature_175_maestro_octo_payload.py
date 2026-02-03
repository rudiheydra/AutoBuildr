"""
Test Feature #175: Maestro produces structured Octo request payload
===================================================================

Tests the construction of OctoRequestPayload by Maestro:
1. Maestro gathers project discovery artifacts, app spec, tech stack, and feature backlog
2. Maestro identifies execution environment (web, desktop, backend)
3. Maestro constructs OctoRequestPayload with all required fields
4. Payload includes: project_context, required_capabilities, existing_agents, constraints
5. Payload validates against OctoRequestPayload schema before dispatch
"""
import json
import pytest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.database import Base, Feature
from api.maestro import (
    Maestro,
    AgentPlanningDecision,
    CapabilityRequirement,
    ProjectContext,
    OctoPayloadConstructionResult,
    get_maestro,
    reset_maestro,
)
from api.octo import OctoRequestPayload


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_features(in_memory_db):
    """Add sample features to the database."""
    features = [
        Feature(
            id=1,
            name="User login page",
            category="Authentication",
            description="Implement login page with OAuth",
            steps=["Create login form", "Add OAuth integration", "Test login flow"],
            passes=True,
            priority=1,
        ),
        Feature(
            id=2,
            name="Dashboard UI",
            category="Frontend",
            description="Create main dashboard with React components",
            steps=["Create dashboard component", "Add data visualization"],
            passes=False,
            in_progress=True,
            priority=2,
        ),
        Feature(
            id=3,
            name="API endpoints",
            category="Backend",
            description="Create REST API with FastAPI",
            steps=["Define endpoints", "Implement handlers", "Add tests"],
            passes=False,
            priority=3,
        ),
    ]
    for f in features:
        in_memory_db.add(f)
    in_memory_db.commit()
    return features


@pytest.fixture
def sample_decision():
    """Create a sample AgentPlanningDecision for testing."""
    return AgentPlanningDecision(
        requires_agent_planning=True,
        required_capabilities=[
            CapabilityRequirement(
                capability="playwright",
                source="tech_stack",
                keywords_matched=["playwright", "e2e test"],
                confidence="high",
            ),
            CapabilityRequirement(
                capability="react",
                source="feature_2",
                keywords_matched=["react"],
                confidence="medium",
            ),
        ],
        existing_capabilities=["coding", "testing"],
        justification="Agent-planning required for specialized capabilities.",
        recommended_agent_types=["playwright_e2e", "react_specialist"],
    )


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with sample files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)

        # Create app_spec.txt
        (project_path / "app_spec.txt").write_text(
            "# My Application Spec\n\nThis is a web application for managing tasks.\n"
            "Built with React frontend and FastAPI backend.\n"
        )

        # Create README.md
        (project_path / "README.md").write_text(
            "# My Project\n\n"
            "A full-stack web application using React and FastAPI.\n\n"
            "## Features\n- User authentication\n- Task management\n"
        )

        # Create package.json
        (project_path / "package.json").write_text(json.dumps({
            "name": "my-project",
            "dependencies": {
                "react": "^18.0.0",
                "express": "^4.18.0",
            },
            "devDependencies": {
                "playwright": "^1.40.0",
                "typescript": "^5.0.0",
            },
        }))

        # Create requirements.txt
        (project_path / "requirements.txt").write_text(
            "fastapi>=0.100.0\n"
            "sqlalchemy>=2.0.0\n"
            "pytest>=7.0.0\n"
        )

        # Create some directory structure
        (project_path / "src").mkdir()
        (project_path / "api").mkdir()
        (project_path / "tests").mkdir()

        yield project_path


@pytest.fixture
def maestro():
    """Create a fresh Maestro instance for testing."""
    reset_maestro()
    return Maestro()


# =============================================================================
# Test: Maestro gathers discovery artifacts
# =============================================================================

class TestProjectDiscovery:
    """Test project discovery artifact gathering."""

    def test_gathers_app_spec_content(self, maestro, temp_project_dir):
        """Verify Maestro gathers app_spec.txt content."""
        artifacts = maestro._gather_discovery_artifacts(temp_project_dir)

        assert artifacts["app_spec_content"] is not None
        assert "My Application Spec" in artifacts["app_spec_content"]
        assert "web application" in artifacts["app_spec_content"]

    def test_gathers_app_spec_summary(self, maestro, temp_project_dir):
        """Verify Maestro creates app spec summary (first 500 chars)."""
        # Create a longer app spec
        long_content = "# Long Spec\n" + "x" * 1000
        (temp_project_dir / "app_spec.txt").write_text(long_content)

        artifacts = maestro._gather_discovery_artifacts(temp_project_dir)

        assert artifacts["app_spec_summary"] is not None
        assert len(artifacts["app_spec_summary"]) <= 500

    def test_gathers_readme_content(self, maestro, temp_project_dir):
        """Verify Maestro gathers README content."""
        artifacts = maestro._gather_discovery_artifacts(temp_project_dir)

        assert artifacts["readme_content"] is not None
        assert "My Project" in artifacts["readme_content"]
        assert "React and FastAPI" in artifacts["readme_content"]

    def test_readme_truncated_to_2000_chars(self, maestro, temp_project_dir):
        """Verify README is truncated to 2000 chars."""
        long_readme = "# README\n" + "x" * 5000
        (temp_project_dir / "README.md").write_text(long_readme)

        artifacts = maestro._gather_discovery_artifacts(temp_project_dir)

        assert len(artifacts["readme_content"]) <= 2000

    def test_gathers_directory_structure(self, maestro, temp_project_dir):
        """Verify Maestro gathers directory structure."""
        artifacts = maestro._gather_discovery_artifacts(temp_project_dir)

        structure = artifacts["directory_structure"]
        assert isinstance(structure, list)
        assert "src/" in structure
        assert "api/" in structure
        assert "tests/" in structure
        assert "package.json" in structure

    def test_skips_hidden_files(self, maestro, temp_project_dir):
        """Verify hidden files are skipped in directory structure."""
        (temp_project_dir / ".git").mkdir()
        (temp_project_dir / ".env").write_text("SECRET=xyz")

        artifacts = maestro._gather_discovery_artifacts(temp_project_dir)

        structure = artifacts["directory_structure"]
        assert ".git/" not in structure
        assert ".env" not in structure

    def test_handles_missing_project_dir(self, maestro):
        """Verify graceful handling when project_dir doesn't exist."""
        artifacts = maestro._gather_discovery_artifacts(Path("/nonexistent/path"))

        assert artifacts["app_spec_content"] is None
        assert artifacts["readme_content"] is None
        assert artifacts["directory_structure"] == []


# =============================================================================
# Test: Maestro detects tech stack
# =============================================================================

class TestTechStackDetection:
    """Test technology stack detection from project files."""

    def test_detects_nodejs_from_package_json(self, maestro, temp_project_dir):
        """Verify Node.js detection from package.json."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "Node.js" in tech_stack

    def test_detects_react_from_dependencies(self, maestro, temp_project_dir):
        """Verify React detection from package.json dependencies."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "React" in tech_stack

    def test_detects_express_from_dependencies(self, maestro, temp_project_dir):
        """Verify Express detection from package.json dependencies."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "Express" in tech_stack

    def test_detects_playwright_from_devdependencies(self, maestro, temp_project_dir):
        """Verify Playwright detection from devDependencies."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "Playwright" in tech_stack

    def test_detects_python_from_requirements(self, maestro, temp_project_dir):
        """Verify Python detection from requirements.txt."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "Python" in tech_stack

    def test_detects_fastapi_from_requirements(self, maestro, temp_project_dir):
        """Verify FastAPI detection from requirements.txt."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "FastAPI" in tech_stack

    def test_detects_sqlalchemy_from_requirements(self, maestro, temp_project_dir):
        """Verify SQLAlchemy detection from requirements.txt."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "SQLAlchemy" in tech_stack

    def test_detects_pytest_from_requirements(self, maestro, temp_project_dir):
        """Verify pytest detection from requirements.txt."""
        tech_stack = maestro._detect_tech_stack_from_files(temp_project_dir)

        assert "pytest" in tech_stack


# =============================================================================
# Test: Maestro identifies execution environment
# =============================================================================

class TestExecutionEnvironmentDetection:
    """Test execution environment identification."""

    def test_web_detected_from_react(self, maestro, temp_project_dir):
        """Verify web environment detected when React is present."""
        tech_stack = ["React", "Node.js", "Express"]
        env = maestro._identify_execution_environment(tech_stack, temp_project_dir)

        assert env == "web"

    def test_web_detected_from_fastapi(self, maestro, temp_project_dir):
        """Verify web environment detected when FastAPI is present."""
        tech_stack = ["Python", "FastAPI"]
        env = maestro._identify_execution_environment(tech_stack, temp_project_dir)

        assert env == "web"

    def test_cli_detected_from_cli_file(self, maestro, temp_project_dir):
        """Verify CLI environment detected when cli.py exists."""
        (temp_project_dir / "cli.py").write_text("#!/usr/bin/env python\n")
        tech_stack = ["Python"]
        env = maestro._identify_execution_environment(tech_stack, temp_project_dir)

        assert env == "cli"

    def test_backend_detected_from_server_file(self, maestro, temp_project_dir):
        """Verify backend environment detected when server.py exists."""
        (temp_project_dir / "server.py").write_text("# server\n")
        tech_stack = ["Python"]
        env = maestro._identify_execution_environment(tech_stack, temp_project_dir)

        assert env == "backend"

    def test_unknown_when_no_indicators(self, maestro, temp_project_dir):
        """Verify unknown environment when no indicators present."""
        tech_stack = []
        env = maestro._identify_execution_environment(tech_stack, temp_project_dir)

        assert env == "unknown"


# =============================================================================
# Test: Maestro fetches feature backlog
# =============================================================================

class TestFeatureBacklogFetch:
    """Test feature backlog fetching from database."""

    def test_fetches_features_from_database(self, maestro, in_memory_db, sample_features):
        """Verify features are fetched from database."""
        features, total, passing = maestro._fetch_feature_backlog(in_memory_db, limit=20)

        assert total == 3
        assert passing == 1
        assert len(features) == 3

    def test_feature_status_mapping(self, maestro, in_memory_db, sample_features):
        """Verify feature status is correctly mapped."""
        features, _, _ = maestro._fetch_feature_backlog(in_memory_db, limit=20)

        # Find feature by id
        feature_statuses = {f["id"]: f["status"] for f in features}

        assert feature_statuses[1] == "passing"
        assert feature_statuses[2] == "in_progress"
        assert feature_statuses[3] == "pending"

    def test_respects_limit(self, maestro, in_memory_db, sample_features):
        """Verify limit parameter is respected."""
        features, total, _ = maestro._fetch_feature_backlog(in_memory_db, limit=2)

        assert len(features) == 2
        assert total == 3  # Total should still reflect all features


# =============================================================================
# Test: Maestro constructs OctoRequestPayload
# =============================================================================

class TestOctoPayloadConstruction:
    """Test OctoRequestPayload construction."""

    def test_constructs_valid_payload(
        self, maestro, sample_decision, temp_project_dir, in_memory_db, sample_features
    ):
        """Verify construct_octo_payload creates a valid payload."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
            tech_stack=["Python", "React"],
            existing_agents=["coding", "testing"],
        )

        result = maestro.construct_octo_payload(sample_decision, context, in_memory_db)

        assert result.success is True
        assert result.payload is not None
        assert isinstance(result.payload, OctoRequestPayload)

    def test_payload_includes_project_context(
        self, maestro, sample_decision, temp_project_dir, in_memory_db
    ):
        """Verify payload includes project_context with all fields."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, in_memory_db)
        payload_dict = result.payload.to_dict()

        project_context = payload_dict["project_context"]
        assert project_context["name"] == "test-project"
        assert "tech_stack" in project_context
        assert "execution_environment" in project_context
        assert "app_spec_content" in project_context
        assert "readme_content" in project_context
        assert "directory_structure" in project_context

    def test_payload_includes_required_capabilities(
        self, maestro, sample_decision, temp_project_dir
    ):
        """Verify payload includes required_capabilities from decision."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, None)
        payload_dict = result.payload.to_dict()

        assert "playwright" in payload_dict["required_capabilities"]
        assert "react" in payload_dict["required_capabilities"]

    def test_payload_includes_existing_agents(
        self, maestro, sample_decision, temp_project_dir
    ):
        """Verify payload includes existing_agents from decision."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, None)
        payload_dict = result.payload.to_dict()

        assert "coding" in payload_dict["existing_agents"]
        assert "testing" in payload_dict["existing_agents"]

    def test_payload_includes_constraints(
        self, maestro, sample_decision, temp_project_dir
    ):
        """Verify payload includes constraints."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, None)
        payload_dict = result.payload.to_dict()

        assert "constraints" in payload_dict
        assert "max_agents" in payload_dict["constraints"]

    def test_payload_validates_successfully(
        self, maestro, sample_decision, temp_project_dir
    ):
        """Verify payload passes validation before dispatch."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, None)

        # Payload should be valid
        validation_errors = result.payload.validate()
        assert len(validation_errors) == 0

    def test_warns_when_no_database_session(
        self, maestro, sample_decision, temp_project_dir
    ):
        """Verify warning when no database session provided."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, None)

        assert "No database session - skipping feature backlog" in result.warnings

    def test_payload_includes_feature_backlog(
        self, maestro, sample_decision, temp_project_dir, in_memory_db, sample_features
    ):
        """Verify payload includes feature backlog when session provided."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
        )

        result = maestro.construct_octo_payload(sample_decision, context, in_memory_db)
        payload_dict = result.payload.to_dict()

        project_context = payload_dict["project_context"]
        assert "feature_backlog" in project_context
        assert len(project_context["feature_backlog"]) == 3
        assert project_context["total_features"] == 3
        assert project_context["passing_features"] == 1


# =============================================================================
# Test: OctoRequestPayload validation
# =============================================================================

class TestOctoPayloadValidation:
    """Test OctoRequestPayload validation."""

    def test_valid_payload_passes_validation(self):
        """Verify valid payload passes validation."""
        payload = OctoRequestPayload(
            project_context={"name": "test", "tech_stack": ["Python"]},
            required_capabilities=["coding", "testing"],
            existing_agents=["coder"],
            constraints={"max_agents": 3},
        )

        errors = payload.validate()
        assert len(errors) == 0

    def test_empty_required_capabilities_fails(self):
        """Verify empty required_capabilities fails validation."""
        payload = OctoRequestPayload(
            project_context={"name": "test"},
            required_capabilities=[],
            existing_agents=[],
            constraints={},
        )

        errors = payload.validate()
        assert any("required_capabilities" in e for e in errors)

    def test_invalid_capability_type_fails(self):
        """Verify non-string capability fails validation."""
        payload = OctoRequestPayload(
            project_context={"name": "test"},
            required_capabilities=[123, None],  # Invalid types
            existing_agents=[],
            constraints={},
        )

        errors = payload.validate()
        assert len(errors) > 0


# =============================================================================
# Test: Integration with delegate_to_octo
# =============================================================================

class TestDelegateToOctoIntegration:
    """Test integration of construct_octo_payload with delegate_to_octo."""

    def test_delegate_uses_construct_octo_payload_when_context_provided(
        self, maestro, sample_decision, temp_project_dir, in_memory_db, sample_features
    ):
        """Verify delegate_to_octo uses construct_octo_payload when context is provided."""
        context = ProjectContext(
            project_name="test-project",
            project_dir=temp_project_dir,
            tech_stack=["Python", "React"],
            existing_agents=["coding", "testing"],
        )

        # Mock the Octo service to avoid actual API calls
        with patch("api.octo.get_octo") as mock_get_octo:
            mock_octo = MagicMock()
            mock_octo.generate_specs.return_value = MagicMock(
                success=True,
                agent_specs=[],
                warnings=[],
            )
            mock_get_octo.return_value = mock_octo

            result = maestro.delegate_to_octo(
                decision=sample_decision,
                session=in_memory_db,
                project_dir=temp_project_dir,
                context=context,
            )

            # Verify Octo was called
            assert mock_octo.generate_specs.called

            # Verify the payload was constructed with rich context
            call_args = mock_octo.generate_specs.call_args
            payload = call_args[0][0]
            assert payload.project_context.get("name") == "test-project"
            assert "tech_stack" in payload.project_context


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
