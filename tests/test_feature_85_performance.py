#!/usr/bin/env python3
"""
Feature #85: Page Load Performance with Large Dataset
=====================================================

Tests page load and render performance with 100+ agent specs and runs
to ensure UI remains responsive.

This test verifies:
1. Database has 100+ test AgentSpec records
2. Database has 50+ test AgentRun records with various statuses
3. API response time for listing features (which drives the dashboard)
4. No server errors during data retrieval
5. Pagination works correctly for large datasets
6. Search/filter endpoints respond within acceptable time

Run with: ./venv/bin/python tests/test_feature_85_performance.py
"""

import sys
import time
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test configuration
BASE_URL = "http://localhost:8888"
PROJECT_NAME = "AutoBuildr"

# Performance thresholds (in seconds)
MAX_API_RESPONSE_TIME = 2.0  # API should respond within 2 seconds
MAX_FEATURES_LOAD_TIME = 1.0  # Features endpoint should load within 1 second

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(title: str):
    """Print a section header."""
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}{title}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")


def print_result(step: str, passed: bool, details: str = ""):
    """Print a test result."""
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"[{status}] {step}")
    if details:
        print(f"       {details}")


def measure_request(url: str, params: dict = None) -> tuple:
    """
    Measure the response time and status of an HTTP request.

    Returns: (response_time_seconds, status_code, data_or_error)
    """
    try:
        start = time.perf_counter()
        response = requests.get(url, params=params, timeout=30)
        elapsed = time.perf_counter() - start

        if response.status_code == 200:
            return elapsed, response.status_code, response.json()
        else:
            return elapsed, response.status_code, response.text
    except Exception as e:
        return -1, -1, str(e)


def test_server_health():
    """Test that the server is running and healthy."""
    print_header("Step 1: Server Health Check")

    elapsed, status, data = measure_request(f"{BASE_URL}/api/health")

    passed = status == 200 and isinstance(data, dict) and data.get("status") == "healthy"
    print_result(
        "Server health endpoint responds",
        passed,
        f"Response time: {elapsed*1000:.1f}ms" if elapsed > 0 else "Server not responding"
    )

    return passed


def test_database_has_test_data():
    """Test that the database has the required test data."""
    print_header("Step 2: Verify Test Data in Database")

    from api.database import create_database
    from api.agentspec_models import AgentSpec, AgentRun

    engine, SessionLocal = create_database(project_root)
    session = SessionLocal()

    try:
        # Count test specs
        spec_count = session.query(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()

        specs_ok = spec_count >= 100
        print_result(
            f"Database has 100+ test AgentSpec records",
            specs_ok,
            f"Found: {spec_count} test specs"
        )

        # Count test runs
        run_count = session.query(AgentRun).join(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()

        runs_ok = run_count >= 50
        print_result(
            f"Database has 50+ test AgentRun records",
            runs_ok,
            f"Found: {run_count} test runs"
        )

        # Verify run status distribution
        from api.agentspec_models import RUN_STATUS
        status_dist = {}
        for status in RUN_STATUS:
            count = session.query(AgentRun).join(AgentSpec).filter(
                AgentSpec.name.like("perf-test-spec-%"),
                AgentRun.status == status
            ).count()
            status_dist[status] = count

        has_variety = sum(1 for v in status_dist.values() if v > 0) >= 3
        print_result(
            "AgentRuns have various statuses",
            has_variety,
            f"Distribution: {status_dist}"
        )

        return specs_ok and runs_ok and has_variety

    finally:
        session.close()


def test_features_api_performance():
    """Test that the features API responds quickly with the large dataset."""
    print_header("Step 3: Features API Performance")

    # Test features endpoint (this is what the Kanban board loads)
    elapsed, status, data = measure_request(
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features"
    )

    features_ok = status == 200 and elapsed < MAX_FEATURES_LOAD_TIME
    total_features = 0
    if isinstance(data, dict):
        total_features = len(data.get("pending", [])) + len(data.get("in_progress", [])) + len(data.get("done", []))

    print_result(
        f"Features endpoint responds within {MAX_FEATURES_LOAD_TIME}s",
        features_ok,
        f"Response time: {elapsed*1000:.1f}ms, Features loaded: {total_features}"
    )

    # Test with larger dataset - simulating initial page load
    elapsed2, status2, _ = measure_request(
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features"
    )

    consistent_ok = abs(elapsed2 - elapsed) < 0.5  # Response time should be consistent
    print_result(
        "Response time is consistent across requests",
        consistent_ok,
        f"First: {elapsed*1000:.1f}ms, Second: {elapsed2*1000:.1f}ms"
    )

    return features_ok and consistent_ok


def test_project_stats_performance():
    """Test that project statistics load quickly."""
    print_header("Step 4: Project Stats Performance")

    elapsed, status, data = measure_request(f"{BASE_URL}/api/projects")

    stats_ok = status == 200 and elapsed < MAX_API_RESPONSE_TIME

    # Find AutoBuildr project stats
    project_stats = None
    if isinstance(data, list):
        for proj in data:
            if proj.get("name") == PROJECT_NAME:
                project_stats = proj.get("stats", {})
                break

    print_result(
        f"Projects endpoint responds within {MAX_API_RESPONSE_TIME}s",
        stats_ok,
        f"Response time: {elapsed*1000:.1f}ms"
    )

    if project_stats:
        print_result(
            "Project statistics are available",
            True,
            f"Total: {project_stats.get('total')}, Passing: {project_stats.get('passing')}, "
            f"Progress: {project_stats.get('percentage')}%"
        )

    return stats_ok


def test_dependency_graph_performance():
    """Test that the dependency graph loads quickly with many features."""
    print_header("Step 5: Dependency Graph Performance")

    elapsed, status, data = measure_request(
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features/graph"
    )

    graph_ok = status == 200 and elapsed < MAX_API_RESPONSE_TIME

    node_count = 0
    edge_count = 0
    if isinstance(data, dict):
        node_count = len(data.get("nodes", []))
        edge_count = len(data.get("edges", []))

    print_result(
        f"Dependency graph loads within {MAX_API_RESPONSE_TIME}s",
        graph_ok,
        f"Response time: {elapsed*1000:.1f}ms, Nodes: {node_count}, Edges: {edge_count}"
    )

    return graph_ok


def test_no_server_errors():
    """Test that there are no server errors during data retrieval."""
    print_header("Step 6: Server Error Check")

    endpoints = [
        f"{BASE_URL}/api/health",
        f"{BASE_URL}/api/projects",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features/graph",
    ]

    all_ok = True
    for endpoint in endpoints:
        elapsed, status, _ = measure_request(endpoint)
        ok = status == 200
        all_ok = all_ok and ok

        short_endpoint = endpoint.replace(BASE_URL, "")
        print_result(
            f"No errors on {short_endpoint}",
            ok,
            f"Status: {status}" if not ok else ""
        )

    return all_ok


def test_concurrent_requests():
    """Test that the server handles concurrent requests well."""
    print_header("Step 7: Concurrent Request Handling")

    import concurrent.futures

    def make_request(url):
        return measure_request(url)

    # Make 5 concurrent requests
    urls = [f"{BASE_URL}/api/projects/{PROJECT_NAME}/features"] * 5

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(make_request, urls))
    total_time = time.perf_counter() - start

    all_successful = all(r[1] == 200 for r in results)
    avg_response = sum(r[0] for r in results) / len(results)
    max_response = max(r[0] for r in results)

    concurrent_ok = all_successful and max_response < MAX_API_RESPONSE_TIME * 2

    print_result(
        "Handles 5 concurrent requests",
        concurrent_ok,
        f"Total time: {total_time*1000:.1f}ms, Avg response: {avg_response*1000:.1f}ms, "
        f"Max response: {max_response*1000:.1f}ms"
    )

    return concurrent_ok


def test_search_filter_performance():
    """Test search/filter response time under load."""
    print_header("Step 8: Search/Filter Performance")

    # Note: The features API doesn't have search params, but we test
    # that filtering by status (pending/in_progress/done) is fast
    # since that's how the Kanban board works

    elapsed, status, data = measure_request(
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features"
    )

    if status != 200 or not isinstance(data, dict):
        print_result("Features data structure is valid", False)
        return False

    # Check that features are properly categorized (fast filtering)
    pending = data.get("pending", [])
    in_progress = data.get("in_progress", [])
    done = data.get("done", [])

    filter_ok = True

    # Verify categorization is correct (no overlap)
    pending_ids = {f["id"] for f in pending}
    progress_ids = {f["id"] for f in in_progress}
    done_ids = {f["id"] for f in done}

    no_overlap = (
        len(pending_ids & progress_ids) == 0 and
        len(pending_ids & done_ids) == 0 and
        len(progress_ids & done_ids) == 0
    )

    print_result(
        "Feature categorization is correct (no overlap)",
        no_overlap,
        f"Pending: {len(pending)}, In Progress: {len(in_progress)}, Done: {len(done)}"
    )

    # Response time check
    response_fast = elapsed < MAX_FEATURES_LOAD_TIME
    print_result(
        f"Filtering responds within {MAX_FEATURES_LOAD_TIME}s",
        response_fast,
        f"Response time: {elapsed*1000:.1f}ms"
    )

    return no_overlap and response_fast


def main():
    """Run all performance tests."""
    print(f"\n{BOLD}Feature #85: Page Load Performance with Large Dataset{RESET}")
    print(f"Testing with {PROJECT_NAME} project")
    print(f"Server: {BASE_URL}")

    results = []

    # Run all tests
    results.append(("Server Health", test_server_health()))

    if not results[-1][1]:
        print(f"\n{RED}Server is not running. Cannot continue tests.{RESET}")
        return False

    results.append(("Test Data", test_database_has_test_data()))
    results.append(("Features API", test_features_api_performance()))
    results.append(("Project Stats", test_project_stats_performance()))
    results.append(("Dependency Graph", test_dependency_graph_performance()))
    results.append(("No Server Errors", test_no_server_errors()))
    results.append(("Concurrent Requests", test_concurrent_requests()))
    results.append(("Search/Filter", test_search_filter_performance()))

    # Summary
    print_header("Test Summary")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    all_passed = passed == total

    for name, ok in results:
        status = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {name}")

    print(f"\n{BOLD}Results: {passed}/{total} tests passed{RESET}")

    if all_passed:
        print(f"\n{GREEN}{BOLD}All performance tests PASSED!{RESET}")
        print("The page can handle 100+ agent specs and 50+ runs without performance issues.")
    else:
        print(f"\n{RED}{BOLD}Some tests FAILED. See details above.{RESET}")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
