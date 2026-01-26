"""
Tests for Feature #102: Dependency health check produces clear formatted log output

The startup health check should produce clear, formatted log output summarizing
all detected issues and actions taken.

Verification Steps:
1. Create formatted log header: === DEPENDENCY HEALTH CHECK ===
2. List self-references found and auto-fixed (if any)
3. List orphaned references found and auto-removed (if any)
4. List cycles found requiring user action (if any)
5. End with summary: X issues auto-fixed, Y issues require attention
6. If no issues: Dependency graph is healthy
"""

import io
import logging
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from parallel_orchestrator import ParallelOrchestrator


class MockFeature:
    """Mock feature for testing."""

    def __init__(self, id: int, dependencies: list[int] = None, passes: bool = False, in_progress: bool = False):
        self.id = id
        self.dependencies = dependencies or []
        self.passes = passes
        self.in_progress = in_progress
        self.priority = id
        self.category = "test"
        self.name = f"Test Feature {id}"
        self.description = f"Test feature {id} description"
        self.steps = ["Step 1", "Step 2"]

    def to_dict(self):
        return {
            "id": self.id,
            "priority": self.priority,
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "passes": self.passes,
            "in_progress": self.in_progress,
            "dependencies": self.dependencies,
        }


class MockSession:
    """Mock database session."""

    def __init__(self, features: list[MockFeature] = None):
        self.features = features or []
        self.committed = False

    def query(self, model):
        return MockQuery(self.features)

    def commit(self):
        self.committed = True

    def close(self):
        pass


class MockQuery:
    """Mock SQLAlchemy query."""

    def __init__(self, features: list[MockFeature]):
        self.features = features

    def all(self):
        return self.features

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        if self.features:
            return self.features[0]
        return None


def create_orchestrator_with_mock_session(features: list[MockFeature] = None):
    """Create an orchestrator with a mocked database session."""
    with patch("parallel_orchestrator.create_database") as mock_db:
        mock_engine = MagicMock()
        mock_session_maker = MagicMock(return_value=MockSession(features))
        mock_db.return_value = (mock_engine, mock_session_maker)

        orchestrator = ParallelOrchestrator(
            project_dir=Path("/tmp/test-project"),
            max_concurrency=1,
        )
        # Override session maker to return our mock
        orchestrator._session_maker = mock_session_maker
        return orchestrator


class TestFormattedLogHeader:
    """Test Step 1: Create formatted log header: === DEPENDENCY HEALTH CHECK ==="""

    def test_log_header_present(self):
        """Verify the === DEPENDENCY HEALTH CHECK === header is printed."""
        features = [MockFeature(1, [], True)]  # One passing feature, no issues
        orchestrator = create_orchestrator_with_mock_session(features)

        output = io.StringIO()
        with redirect_stdout(output):
            result = orchestrator._run_dependency_health_check()

        stdout = output.getvalue()
        assert "=== DEPENDENCY HEALTH CHECK ===" in stdout, \
            f"Missing header '=== DEPENDENCY HEALTH CHECK ===' in output: {stdout}"

    def test_log_header_with_decorative_equals(self):
        """Verify the header has decorative equals signs around it."""
        features = [MockFeature(1, [], True)]
        orchestrator = create_orchestrator_with_mock_session(features)

        output = io.StringIO()
        with redirect_stdout(output):
            result = orchestrator._run_dependency_health_check()

        stdout = output.getvalue()
        # Should have lines of = signs before and after the header
        assert "=" * 60 in stdout, f"Missing decorative equals line in output: {stdout}"


class TestSelfReferencesLogging:
    """Test Step 2: List self-references found and auto-fixed (if any)."""

    def test_self_references_section_header(self):
        """Verify self-references section has clear header."""
        # Feature 1 with self-reference
        feature1 = MockFeature(1, [1])  # Self-reference: 1 -> 1

        def mock_session():
            session = MockSession([feature1])
            # Override query to return specific feature
            original_query = session.query

            def patched_query(model):
                query = original_query(model)
                original_filter = query.filter

                def patched_filter(*args, **kwargs):
                    query.features = [feature1]
                    return query

                query.filter = patched_filter
                return query

            session.query = patched_query
            return session

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            # Mock validate_dependency_graph to return self-references
            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [1],
                    "cycles": [],
                    "missing_targets": {},
                    "issues": ["Self-reference"],
                    "summary": "1 self-reference",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                assert "SELF-REFERENCES FOUND" in stdout, \
                    f"Missing 'SELF-REFERENCES FOUND' section in output: {stdout}"
                assert "auto-fix" in stdout.lower(), \
                    f"Missing auto-fix message in output: {stdout}"


class TestOrphanedReferencesLogging:
    """Test Step 3: List orphaned references found and auto-removed (if any)."""

    def test_orphaned_references_section_header(self):
        """Verify orphaned references section has clear header."""
        # Feature 1 references non-existent feature 999
        feature1 = MockFeature(1, [999])

        def mock_session():
            session = MockSession([feature1])
            original_query = session.query

            def patched_query(model):
                query = original_query(model)
                original_filter = query.filter

                def patched_filter(*args, **kwargs):
                    query.features = [feature1]
                    return query

                query.filter = patched_filter
                return query

            session.query = patched_query
            return session

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [],
                    "cycles": [],
                    "missing_targets": {1: [999]},
                    "issues": ["Missing target"],
                    "summary": "1 orphaned reference",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                assert "ORPHANED REFERENCES FOUND" in stdout, \
                    f"Missing 'ORPHANED REFERENCES FOUND' section in output: {stdout}"
                assert "auto-remov" in stdout.lower(), \
                    f"Missing auto-remove message in output: {stdout}"


class TestCyclesLogging:
    """Test Step 4: List cycles found requiring user action (if any)."""

    def test_cycles_section_header(self):
        """Verify cycles section has clear header indicating user action required."""
        feature1 = MockFeature(1, [2])
        feature2 = MockFeature(2, [1])

        def mock_session():
            session = MockSession([feature1, feature2])
            return session

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [],
                    "cycles": [[1, 2]],
                    "missing_targets": {},
                    "issues": ["Cycle detected"],
                    "summary": "1 cycle",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                assert "CYCLES FOUND" in stdout, \
                    f"Missing 'CYCLES FOUND' section in output: {stdout}"
                assert "user action" in stdout.lower() or "requires" in stdout.lower(), \
                    f"Missing user action message in output: {stdout}"

    def test_cycles_block_startup(self):
        """Verify cycles return False to block startup."""
        feature1 = MockFeature(1, [2])
        feature2 = MockFeature(2, [1])

        def mock_session():
            return MockSession([feature1, feature2])

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [],
                    "cycles": [[1, 2]],
                    "missing_targets": {},
                    "issues": ["Cycle detected"],
                    "summary": "1 cycle",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                assert result is False, "Cycles should block startup (return False)"


class TestSummaryLine:
    """Test Step 5: End with summary: X issues auto-fixed, Y issues require attention."""

    def test_summary_with_auto_fixed_issues(self):
        """Verify summary shows auto-fixed count when issues were fixed."""
        feature1 = MockFeature(1, [1])  # Self-reference to auto-fix

        def mock_session():
            session = MockSession([feature1])
            original_query = session.query

            def patched_query(model):
                query = original_query(model)
                original_filter = query.filter

                def patched_filter(*args, **kwargs):
                    query.features = [feature1]
                    return query

                query.filter = patched_filter
                return query

            session.query = patched_query
            return session

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [1],
                    "cycles": [],
                    "missing_targets": {},
                    "issues": ["Self-reference"],
                    "summary": "1 self-reference",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                # Check for summary format
                assert "Summary:" in stdout or "issues auto-fixed" in stdout, \
                    f"Missing summary line in output: {stdout}"
                assert "auto-fixed" in stdout.lower(), \
                    f"Missing 'auto-fixed' in output: {stdout}"

    def test_summary_with_cycles_requiring_attention(self):
        """Verify summary shows issues requiring attention when cycles detected."""
        feature1 = MockFeature(1, [2])
        feature2 = MockFeature(2, [1])

        def mock_session():
            return MockSession([feature1, feature2])

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [],
                    "cycles": [[1, 2]],
                    "missing_targets": {},
                    "issues": ["Cycle detected"],
                    "summary": "1 cycle",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                assert "require attention" in stdout.lower() or "issues require" in stdout.lower(), \
                    f"Missing 'require attention' in output: {stdout}"


class TestHealthyGraph:
    """Test Step 6: If no issues: Dependency graph is healthy."""

    def test_healthy_graph_message(self):
        """Verify healthy graph message when no issues detected."""
        features = [MockFeature(1, [], True), MockFeature(2, [1], True)]

        def mock_session():
            return MockSession(features)

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": True,
                    "self_references": [],
                    "cycles": [],
                    "missing_targets": {},
                    "issues": [],
                    "summary": "No issues",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                assert result is True, "Healthy graph should return True"
                assert "healthy" in stdout.lower(), \
                    f"Missing 'healthy' message in output: {stdout}"

    def test_healthy_graph_returns_true(self):
        """Verify healthy graph returns True."""
        features = [MockFeature(1, [], True)]

        def mock_session():
            return MockSession(features)

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": True,
                    "self_references": [],
                    "cycles": [],
                    "missing_targets": {},
                    "issues": [],
                    "summary": "No issues",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                assert result is True


class TestEmptyDatabase:
    """Test edge case: empty database."""

    def test_empty_database_skips_validation(self):
        """Verify empty database shows skip message."""
        def mock_session():
            return MockSession([])

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            output = io.StringIO()
            with redirect_stdout(output):
                result = orchestrator._run_dependency_health_check()

            stdout = output.getvalue()
            assert result is True, "Empty database should return True"
            assert "No features found" in stdout or "skip" in stdout.lower(), \
                f"Missing skip message in output: {stdout}"


class TestMultipleIssueTypes:
    """Test scenarios with multiple issue types."""

    def test_self_references_and_orphaned_together(self):
        """Verify output when both self-references and orphaned refs exist."""
        feature1 = MockFeature(1, [1, 999])  # Self-ref and orphaned ref

        def mock_session():
            session = MockSession([feature1])
            original_query = session.query

            def patched_query(model):
                query = original_query(model)
                original_filter = query.filter

                def patched_filter(*args, **kwargs):
                    query.features = [feature1]
                    return query

                query.filter = patched_filter
                return query

            session.query = patched_query
            return session

        with patch("parallel_orchestrator.create_database") as mock_db:
            mock_engine = MagicMock()
            mock_db.return_value = (mock_engine, mock_session)

            orchestrator = ParallelOrchestrator(
                project_dir=Path("/tmp/test-project"),
                max_concurrency=1,
            )
            orchestrator._session_maker = mock_session

            with patch("parallel_orchestrator.validate_dependency_graph") as mock_validate:
                mock_validate.return_value = {
                    "is_valid": False,
                    "self_references": [1],
                    "cycles": [],
                    "missing_targets": {1: [999]},
                    "issues": ["Self-reference", "Missing target"],
                    "summary": "2 issues",
                }

                output = io.StringIO()
                with redirect_stdout(output):
                    result = orchestrator._run_dependency_health_check()

                stdout = output.getvalue()
                # Should show both sections
                assert "SELF-REFERENCES FOUND" in stdout, \
                    f"Missing self-references section: {stdout}"
                assert "ORPHANED REFERENCES FOUND" in stdout, \
                    f"Missing orphaned references section: {stdout}"
                # Result should be True since no cycles
                assert result is True, "Should return True when issues are auto-fixed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
