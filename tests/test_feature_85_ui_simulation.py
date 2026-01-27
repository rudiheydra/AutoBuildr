#!/usr/bin/env python3
"""
Feature #85: Page Load Performance - UI Simulation Tests
========================================================

These tests simulate what the UI does when loading the dashboard:
1. Fetch features (for Kanban board)
2. Fetch project stats (for progress dashboard)
3. Fetch dependency graph (for graph view)

The tests verify that all data structures are correct and can be
rendered by the React components without issues.

Run with: ./venv/bin/pytest tests/test_feature_85_ui_simulation.py -v
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestUIDataStructures:
    """Test that API responses have correct structure for UI rendering."""

    @pytest.fixture
    def base_url(self):
        return "http://localhost:8888"

    @pytest.fixture
    def project_name(self):
        return "AutoBuildr"

    def test_features_response_structure(self, base_url, project_name):
        """Test that features response has correct structure for KanbanBoard."""
        import requests

        response = requests.get(f"{base_url}/api/projects/{project_name}/features")
        assert response.status_code == 200

        data = response.json()

        # KanbanBoard expects: { pending: [], in_progress: [], done: [] }
        assert "pending" in data
        assert "in_progress" in data
        assert "done" in data

        assert isinstance(data["pending"], list)
        assert isinstance(data["in_progress"], list)
        assert isinstance(data["done"], list)

        # Verify feature structure (if any features exist)
        all_features = data["pending"] + data["in_progress"] + data["done"]
        if all_features:
            feature = all_features[0]
            # FeatureCard expects these fields
            assert "id" in feature
            assert "name" in feature
            assert "description" in feature
            assert "category" in feature

    def test_features_total_count_reasonable(self, base_url, project_name):
        """Test that we have a reasonable number of features (103 in this project)."""
        import requests

        response = requests.get(f"{base_url}/api/projects/{project_name}/features")
        assert response.status_code == 200

        data = response.json()
        total = len(data["pending"]) + len(data["in_progress"]) + len(data["done"])

        # Should have 103 features based on app_spec.txt
        assert total >= 100, f"Expected at least 100 features, got {total}"

    def test_project_stats_structure(self, base_url):
        """Test that project stats have correct structure for ProgressDashboard."""
        import requests

        response = requests.get(f"{base_url}/api/projects")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        project = data[0]

        # ProjectSelector and ProgressDashboard expect these fields
        assert "name" in project
        assert "path" in project
        assert "has_spec" in project
        assert "stats" in project

        stats = project["stats"]
        assert "passing" in stats
        assert "total" in stats
        assert "percentage" in stats

    def test_dependency_graph_structure(self, base_url, project_name):
        """Test that dependency graph has correct structure for DependencyGraph component."""
        import requests

        response = requests.get(f"{base_url}/api/projects/{project_name}/features/graph")
        assert response.status_code == 200

        data = response.json()

        # DependencyGraph expects: { nodes: [], edges: [] }
        assert "nodes" in data
        assert "edges" in data

        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

        # Verify node structure
        if data["nodes"]:
            node = data["nodes"][0]
            assert "id" in node
            assert "status" in node

        # Verify edge structure
        if data["edges"]:
            edge = data["edges"][0]
            assert "source" in edge
            assert "target" in edge


class TestLargeDatasetPerformance:
    """Test performance with large dataset."""

    @pytest.fixture
    def base_url(self):
        return "http://localhost:8888"

    @pytest.fixture
    def project_name(self):
        return "AutoBuildr"

    def test_features_load_time(self, base_url, project_name):
        """Test that features load within acceptable time."""
        import requests
        import time

        start = time.perf_counter()
        response = requests.get(f"{base_url}/api/projects/{project_name}/features")
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < 1.0, f"Features took {elapsed:.2f}s, should be < 1.0s"

    def test_graph_load_time(self, base_url, project_name):
        """Test that dependency graph loads within acceptable time."""
        import requests
        import time

        start = time.perf_counter()
        response = requests.get(f"{base_url}/api/projects/{project_name}/features/graph")
        elapsed = time.perf_counter() - start

        assert response.status_code == 200
        assert elapsed < 2.0, f"Graph took {elapsed:.2f}s, should be < 2.0s"

    def test_concurrent_ui_requests(self, base_url, project_name):
        """Test that multiple UI components can load data concurrently."""
        import requests
        import concurrent.futures
        import time

        urls = [
            f"{base_url}/api/projects",
            f"{base_url}/api/projects/{project_name}/features",
            f"{base_url}/api/projects/{project_name}/features/graph",
        ]

        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(requests.get, url) for url in urls]
            results = [f.result() for f in futures]
        elapsed = time.perf_counter() - start

        # All requests should succeed
        for response in results:
            assert response.status_code == 200

        # Total time should be less than 2 seconds (parallel loading)
        assert elapsed < 2.0, f"Concurrent requests took {elapsed:.2f}s, should be < 2.0s"


class TestDatabaseTestData:
    """Verify test data was created correctly."""

    def test_agent_specs_created(self):
        """Test that 100 test AgentSpecs exist."""
        from api.database import create_database
        from api.agentspec_models import AgentSpec

        _, SessionLocal = create_database(project_root)
        session = SessionLocal()

        try:
            count = session.query(AgentSpec).filter(
                AgentSpec.name.like("perf-test-spec-%")
            ).count()
            assert count >= 100, f"Expected 100+ test specs, found {count}"
        finally:
            session.close()

    def test_agent_runs_created(self):
        """Test that 50 test AgentRuns exist with various statuses."""
        from api.database import create_database
        from api.agentspec_models import AgentSpec, AgentRun

        _, SessionLocal = create_database(project_root)
        session = SessionLocal()

        try:
            count = session.query(AgentRun).join(AgentSpec).filter(
                AgentSpec.name.like("perf-test-spec-%")
            ).count()
            assert count >= 50, f"Expected 50+ test runs, found {count}"
        finally:
            session.close()

    def test_run_status_variety(self):
        """Test that runs have various statuses."""
        from api.database import create_database
        from api.agentspec_models import AgentSpec, AgentRun, RUN_STATUS

        _, SessionLocal = create_database(project_root)
        session = SessionLocal()

        try:
            statuses_with_runs = 0
            for status in RUN_STATUS:
                count = session.query(AgentRun).join(AgentSpec).filter(
                    AgentSpec.name.like("perf-test-spec-%"),
                    AgentRun.status == status
                ).count()
                if count > 0:
                    statuses_with_runs += 1

            assert statuses_with_runs >= 3, f"Expected at least 3 different statuses, found {statuses_with_runs}"
        finally:
            session.close()


class TestScrollingAndPagination:
    """Test features that affect smooth scrolling and pagination."""

    @pytest.fixture
    def base_url(self):
        return "http://localhost:8888"

    @pytest.fixture
    def project_name(self):
        return "AutoBuildr"

    def test_features_ordered_consistently(self, base_url, project_name):
        """Test that features are returned in consistent order for smooth scrolling."""
        import requests

        # Make two requests
        response1 = requests.get(f"{base_url}/api/projects/{project_name}/features")
        response2 = requests.get(f"{base_url}/api/projects/{project_name}/features")

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Order should be identical
        for key in ["pending", "in_progress", "done"]:
            ids1 = [f["id"] for f in data1[key]]
            ids2 = [f["id"] for f in data2[key]]
            assert ids1 == ids2, f"Feature order inconsistent in {key}"

    def test_graph_nodes_have_required_fields(self, base_url, project_name):
        """Test that graph nodes have all fields needed for rendering."""
        import requests

        response = requests.get(f"{base_url}/api/projects/{project_name}/features/graph")
        assert response.status_code == 200

        data = response.json()

        for node in data["nodes"]:
            # Required for DependencyGraph component
            assert "id" in node, "Node missing 'id'"
            assert "status" in node, "Node missing 'status'"

            # Status should be valid
            valid_statuses = ["pending", "in_progress", "done", "blocked"]
            assert node["status"] in valid_statuses, f"Invalid status: {node['status']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
