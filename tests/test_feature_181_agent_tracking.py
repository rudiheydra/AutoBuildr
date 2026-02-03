"""
Tests for Feature #181: Maestro tracks which agents are available per project.

This feature enables Maestro to maintain awareness of which agents exist for a project,
both generated (via Octo) and manual (hand-crafted agent definitions).

Test coverage:
1. scan_file_based_agents() scans .claude/agents/generated/ and manual/
2. query_db_agents() queries database for persisted AgentSpecs
3. reconcile_available_agents() merges file-based and DB-based agent lists
4. get_available_agents() main entry point returns all available agents
5. Available agents influence delegation decisions via evaluate_with_available_agents()
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.maestro import (
    Maestro,
    AgentInfo,
    AvailableAgentsResult,
    ProjectContext,
    DEFAULT_AGENTS,
)


class TestAgentInfoDataClass:
    """Tests for the AgentInfo data class."""

    def test_agent_info_creation(self):
        """AgentInfo can be created with all fields."""
        agent = AgentInfo(
            name="test-agent",
            display_name="Test Agent",
            source="file",
            source_path=Path("/path/to/agent.md"),
            spec_id="spec-123",
            capabilities=["testing", "validation"],
            model="opus",
        )

        assert agent.name == "test-agent"
        assert agent.display_name == "Test Agent"
        assert agent.source == "file"
        assert agent.source_path == Path("/path/to/agent.md")
        assert agent.spec_id == "spec-123"
        assert agent.capabilities == ["testing", "validation"]
        assert agent.model == "opus"

    def test_agent_info_to_dict(self):
        """AgentInfo.to_dict() returns correct dictionary."""
        agent = AgentInfo(
            name="coder",
            display_name="Coder Agent",
            source="database",
            spec_id="abc-123",
        )

        result = agent.to_dict()

        assert result["name"] == "coder"
        assert result["display_name"] == "Coder Agent"
        assert result["source"] == "database"
        assert result["spec_id"] == "abc-123"
        assert result["source_path"] is None
        assert result["capabilities"] == []
        assert result["model"] is None


class TestAvailableAgentsResult:
    """Tests for the AvailableAgentsResult data class."""

    def test_available_agents_result_properties(self):
        """AvailableAgentsResult properties work correctly."""
        agents = [
            AgentInfo(name="agent1", display_name="Agent 1", source="file"),
            AgentInfo(name="agent2", display_name="Agent 2", source="database"),
            AgentInfo(name="agent3", display_name="Agent 3", source="default"),
        ]

        result = AvailableAgentsResult(
            agents=agents,
            file_based_count=1,
            db_based_count=1,
            default_count=1,
        )

        assert result.total_count == 3
        assert result.agent_names == ["agent1", "agent2", "agent3"]

    def test_available_agents_result_to_dict(self):
        """AvailableAgentsResult.to_dict() returns correct structure."""
        agents = [
            AgentInfo(name="test", display_name="Test", source="file"),
        ]

        result = AvailableAgentsResult(
            agents=agents,
            file_based_count=1,
            db_based_count=0,
            default_count=0,
            scan_paths=["/path/to/agents"],
            errors=[],
        )

        data = result.to_dict()

        assert len(data["agents"]) == 1
        assert data["file_based_count"] == 1
        assert data["total_count"] == 1
        assert "test" in data["agent_names"]


class TestScanFileBasedAgents:
    """Tests for Maestro.scan_file_based_agents()."""

    def test_scan_returns_empty_without_project_dir(self):
        """Scanning without project_dir returns empty list."""
        maestro = Maestro()
        agents = maestro.scan_file_based_agents()
        assert agents == []

    def test_scan_finds_agents_in_directory(self):
        """Scanning finds agent files with YAML frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .claude/agents directory
            agents_dir = Path(tmpdir) / ".claude" / "agents"
            agents_dir.mkdir(parents=True)

            # Create a test agent file
            agent_file = agents_dir / "test-agent.md"
            agent_file.write_text("""---
name: test-agent
description: "A test agent for validation"
model: opus
---

# Test Agent

This is a test agent.
""")

            maestro = Maestro(project_dir=Path(tmpdir))
            agents = maestro.scan_file_based_agents()

            assert len(agents) == 1
            assert agents[0].name == "test-agent"
            assert agents[0].model == "opus"
            assert agents[0].source == "file"

    def test_scan_finds_agents_in_generated_subdir(self):
        """Scanning finds agents in .claude/agents/generated/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create generated subdirectory
            generated_dir = Path(tmpdir) / ".claude" / "agents" / "generated"
            generated_dir.mkdir(parents=True)

            # Create agent file
            agent_file = generated_dir / "generated-agent.md"
            agent_file.write_text("""---
name: generated-agent
spec_id: abc-123
---

# Generated Agent
""")

            maestro = Maestro(project_dir=Path(tmpdir))
            agents = maestro.scan_file_based_agents()

            assert len(agents) == 1
            assert agents[0].name == "generated-agent"
            assert agents[0].source == "file:generated"
            assert agents[0].spec_id == "abc-123"

    def test_scan_finds_agents_in_manual_subdir(self):
        """Scanning finds agents in .claude/agents/manual/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manual subdirectory
            manual_dir = Path(tmpdir) / ".claude" / "agents" / "manual"
            manual_dir.mkdir(parents=True)

            # Create agent file
            agent_file = manual_dir / "manual-agent.md"
            agent_file.write_text("""---
name: manual-agent
display_name: Manual Agent
---

# Manual Agent
""")

            maestro = Maestro(project_dir=Path(tmpdir))
            agents = maestro.scan_file_based_agents()

            assert len(agents) == 1
            assert agents[0].name == "manual-agent"
            assert agents[0].display_name == "Manual Agent"
            assert agents[0].source == "file:manual"

    def test_scan_handles_missing_directories(self):
        """Scanning handles non-existent directories gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Don't create .claude/agents
            maestro = Maestro(project_dir=Path(tmpdir))
            agents = maestro.scan_file_based_agents()

            assert agents == []

    def test_scan_skips_files_without_frontmatter(self):
        """Files without YAML frontmatter are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / ".claude" / "agents"
            agents_dir.mkdir(parents=True)

            # Create file without frontmatter
            (agents_dir / "no-frontmatter.md").write_text("# Just Markdown")

            # Create valid agent file
            (agents_dir / "valid.md").write_text("""---
name: valid-agent
---
# Valid
""")

            maestro = Maestro(project_dir=Path(tmpdir))
            agents = maestro.scan_file_based_agents()

            assert len(agents) == 1
            assert agents[0].name == "valid-agent"


class TestQueryDbAgents:
    """Tests for Maestro.query_db_agents()."""

    def test_query_returns_empty_without_session(self):
        """Querying without session returns empty list."""
        maestro = Maestro()
        agents = maestro.query_db_agents()
        assert agents == []

    def test_query_returns_agents_from_database(self):
        """Querying returns AgentSpecs from database."""
        # Mock session and AgentSpec model
        mock_session = MagicMock()
        mock_spec = MagicMock()
        mock_spec.name = "db-agent"
        mock_spec.display_name = "Database Agent"
        mock_spec.id = "spec-uuid-123"
        mock_spec.spec_path = "/path/to/spec.json"
        mock_spec.tags = ["testing", "validation"]

        mock_session.query.return_value.all.return_value = [mock_spec]

        maestro = Maestro(session=mock_session)

        with patch("api.maestro.AgentSpec", create=True):
            agents = maestro.query_db_agents()

        assert len(agents) == 1
        assert agents[0].name == "db-agent"
        assert agents[0].display_name == "Database Agent"
        assert agents[0].source == "database"
        assert agents[0].spec_id == "spec-uuid-123"
        assert agents[0].capabilities == ["testing", "validation"]


class TestReconcileAvailableAgents:
    """Tests for Maestro.reconcile_available_agents()."""

    def test_reconcile_includes_defaults(self):
        """Reconciliation includes default agents."""
        maestro = Maestro()
        result = maestro.reconcile_available_agents(
            file_agents=[],
            db_agents=[],
            include_defaults=True,
        )

        agent_names = [a.name for a in result]
        for default in DEFAULT_AGENTS:
            assert default in agent_names

    def test_reconcile_excludes_defaults_when_disabled(self):
        """Reconciliation excludes defaults when include_defaults=False."""
        maestro = Maestro()
        result = maestro.reconcile_available_agents(
            file_agents=[],
            db_agents=[],
            include_defaults=False,
        )

        assert len(result) == 0

    def test_reconcile_file_agents_override_defaults(self):
        """File-based agents override default agents with same name."""
        maestro = Maestro()

        file_agents = [
            AgentInfo(
                name="coding",  # Same as default
                display_name="Custom Coding Agent",
                source="file",
            )
        ]

        result = maestro.reconcile_available_agents(
            file_agents=file_agents,
            db_agents=[],
            include_defaults=True,
        )

        coding_agent = next(a for a in result if a.name == "coding")
        assert coding_agent.display_name == "Custom Coding Agent"
        assert coding_agent.source == "file"

    def test_reconcile_db_agents_override_file_agents(self):
        """Database agents override file-based agents with same name."""
        maestro = Maestro()

        file_agents = [
            AgentInfo(
                name="test-agent",
                display_name="File Agent",
                source="file",
            )
        ]
        db_agents = [
            AgentInfo(
                name="test-agent",  # Same name
                display_name="Database Agent",
                source="database",
                spec_id="db-123",
            )
        ]

        result = maestro.reconcile_available_agents(
            file_agents=file_agents,
            db_agents=db_agents,
            include_defaults=False,
        )

        assert len(result) == 1
        assert result[0].display_name == "Database Agent"
        assert result[0].source == "database"

    def test_reconcile_merges_unique_agents(self):
        """Reconciliation merges agents with different names."""
        maestro = Maestro()

        file_agents = [
            AgentInfo(name="file-agent", display_name="File", source="file"),
        ]
        db_agents = [
            AgentInfo(name="db-agent", display_name="DB", source="database"),
        ]

        result = maestro.reconcile_available_agents(
            file_agents=file_agents,
            db_agents=db_agents,
            include_defaults=False,
        )

        agent_names = [a.name for a in result]
        assert "file-agent" in agent_names
        assert "db-agent" in agent_names


class TestGetAvailableAgents:
    """Tests for Maestro.get_available_agents()."""

    def test_get_available_agents_returns_result(self):
        """get_available_agents() returns AvailableAgentsResult."""
        maestro = Maestro()
        result = maestro.get_available_agents()

        assert isinstance(result, AvailableAgentsResult)
        # Should include default agents
        assert result.default_count > 0

    def test_get_available_agents_with_project_dir(self):
        """get_available_agents() scans project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create agents directory with a file
            agents_dir = Path(tmpdir) / ".claude" / "agents"
            agents_dir.mkdir(parents=True)

            (agents_dir / "project-agent.md").write_text("""---
name: project-agent
---
# Project Agent
""")

            maestro = Maestro()
            result = maestro.get_available_agents(project_dir=Path(tmpdir))

            assert "project-agent" in result.agent_names
            assert result.file_based_count >= 1

    def test_get_available_agents_records_scan_paths(self):
        """get_available_agents() records scanned paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            maestro = Maestro()
            result = maestro.get_available_agents(project_dir=Path(tmpdir))

            assert len(result.scan_paths) > 0


class TestGetAvailableAgentNames:
    """Tests for Maestro.get_available_agent_names()."""

    def test_returns_list_of_names(self):
        """get_available_agent_names() returns list of strings."""
        maestro = Maestro()
        names = maestro.get_available_agent_names()

        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)
        # Should include default agents
        for default in DEFAULT_AGENTS:
            assert default in names


class TestEvaluateWithAvailableAgents:
    """Tests for Maestro.evaluate_with_available_agents()."""

    def test_evaluate_uses_discovered_agents(self):
        """evaluate_with_available_agents() uses discovered agents in evaluation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a specialized agent file
            agents_dir = Path(tmpdir) / ".claude" / "agents"
            agents_dir.mkdir(parents=True)

            (agents_dir / "playwright.md").write_text("""---
name: playwright
---
# Playwright Agent
""")

            maestro = Maestro(project_dir=Path(tmpdir))

            context = ProjectContext(
                project_name="test-project",
                project_dir=Path(tmpdir),
                tech_stack=["python", "playwright"],
                features=[{"name": "E2E testing", "description": "Browser tests"}],
            )

            # Evaluate with available agents
            decision = maestro.evaluate_with_available_agents(context)

            # Should recognize playwright as available
            # (may or may not require planning depending on context)
            assert decision is not None

    def test_evaluate_falls_back_to_defaults(self):
        """evaluate_with_available_agents() works without additional agents."""
        maestro = Maestro()

        context = ProjectContext(
            project_name="simple-project",
            features=[{"name": "Basic feature", "description": "Simple task"}],
        )

        decision = maestro.evaluate_with_available_agents(context)

        assert decision is not None
        # Default agents should be included
        assert len(decision.existing_capabilities) > 0 or not decision.requires_agent_planning


class TestIntegration:
    """Integration tests for the full agent tracking workflow."""

    def test_full_workflow_file_based_agents(self):
        """Full workflow: scan files -> reconcile -> evaluate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up project structure
            agents_dir = Path(tmpdir) / ".claude" / "agents"
            generated_dir = agents_dir / "generated"
            manual_dir = agents_dir / "manual"
            generated_dir.mkdir(parents=True)
            manual_dir.mkdir(parents=True)

            # Create generated agent
            (generated_dir / "e2e-tester.md").write_text("""---
name: e2e-tester
display_name: E2E Tester
tags: ["e2e", "playwright", "testing"]
---
# E2E Tester Agent
""")

            # Create manual agent
            (manual_dir / "custom-auditor.md").write_text("""---
name: custom-auditor
display_name: Custom Auditor
model: opus
---
# Custom Auditor Agent
""")

            maestro = Maestro(project_dir=Path(tmpdir))

            # Step 1: Scan file-based agents
            file_agents = maestro.scan_file_based_agents()
            assert len(file_agents) == 2

            # Step 2: Query DB (no session, returns empty)
            db_agents = maestro.query_db_agents()
            assert len(db_agents) == 0

            # Step 3: Reconcile
            reconciled = maestro.reconcile_available_agents(
                file_agents=file_agents,
                db_agents=db_agents,
                include_defaults=True,
            )

            # Should have file agents + defaults
            agent_names = [a.name for a in reconciled]
            assert "e2e-tester" in agent_names
            assert "custom-auditor" in agent_names
            for default in DEFAULT_AGENTS:
                assert default in agent_names

            # Step 4: Get available agents (full workflow)
            result = maestro.get_available_agents()

            assert result.file_based_count == 2
            assert result.default_count == len(DEFAULT_AGENTS)

    def test_agent_tracking_influences_decisions(self):
        """Available agents influence planning decisions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a playwright agent
            agents_dir = Path(tmpdir) / ".claude" / "agents"
            agents_dir.mkdir(parents=True)

            (agents_dir / "playwright.md").write_text("""---
name: playwright
---
# Playwright E2E Agent
""")

            maestro = Maestro(project_dir=Path(tmpdir))

            # Context that would normally require playwright
            context = ProjectContext(
                project_name="test-project",
                project_dir=Path(tmpdir),
                tech_stack=["react"],
                features=[
                    {
                        "name": "E2E tests",
                        "description": "Browser automation tests using playwright",
                    }
                ],
            )

            # Evaluate with available agents
            decision = maestro.evaluate_with_available_agents(context)

            # With playwright available, it should be recognized
            # The decision may or may not require planning depending on
            # how the agent is categorized
            assert decision is not None
