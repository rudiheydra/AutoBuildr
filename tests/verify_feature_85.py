#!/usr/bin/env python3
"""
Feature #85 Verification Script
================================

Verifies all 8 steps of Feature #85: Page Load Performance with Large Dataset

Steps:
1. Create 100 test AgentSpec records in database
2. Create 50 test AgentRun records with various statuses
3. Navigate to dashboard page (API simulation)
4. Measure time to first contentful paint (API response time)
5. Measure time to interactive (concurrent request handling)
6. Verify no console errors during load (API error check)
7. Verify smooth scrolling through card list (consistent data ordering)
8. Test search/filter response time under load

Run with: ./venv/bin/python tests/verify_feature_85.py
"""

import sys
import time
import requests
import concurrent.futures
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://localhost:8888"
PROJECT_NAME = "AutoBuildr"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step(num: int, description: str, passed: bool, details: str = ""):
    """Print a verification step result."""
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"Step {num}: {description}")
    print(f"  [{status}] {details}")
    print()
    return passed


def verify_step_1():
    """Step 1: Create 100 test AgentSpec records in database"""
    from api.database import create_database
    from api.agentspec_models import AgentSpec

    _, SessionLocal = create_database(project_root)
    session = SessionLocal()

    try:
        count = session.query(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()
        passed = count >= 100
        return print_step(1, "Create 100 test AgentSpec records in database", passed,
                         f"Found {count} test AgentSpec records")
    finally:
        session.close()


def verify_step_2():
    """Step 2: Create 50 test AgentRun records with various statuses"""
    from api.database import create_database
    from api.agentspec_models import AgentSpec, AgentRun, RUN_STATUS

    _, SessionLocal = create_database(project_root)
    session = SessionLocal()

    try:
        count = session.query(AgentRun).join(AgentSpec).filter(
            AgentSpec.name.like("perf-test-spec-%")
        ).count()

        # Check status variety
        statuses = {}
        for status in RUN_STATUS:
            s_count = session.query(AgentRun).join(AgentSpec).filter(
                AgentSpec.name.like("perf-test-spec-%"),
                AgentRun.status == status
            ).count()
            if s_count > 0:
                statuses[status] = s_count

        passed = count >= 50 and len(statuses) >= 3
        return print_step(2, "Create 50 test AgentRun records with various statuses", passed,
                         f"Found {count} test runs with statuses: {statuses}")
    finally:
        session.close()


def verify_step_3():
    """Step 3: Navigate to dashboard page (API simulation)"""
    # The dashboard loads: projects, features, and dependency graph
    endpoints = [
        f"{BASE_URL}/api/health",
        f"{BASE_URL}/api/projects",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features",
    ]

    all_ok = True
    details = []
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, timeout=10)
            ok = response.status_code == 200
            all_ok = all_ok and ok
            details.append(f"{endpoint.split('/')[-1]}: {response.status_code}")
        except Exception as e:
            all_ok = False
            details.append(f"{endpoint.split('/')[-1]}: ERROR ({e})")

    return print_step(3, "Navigate to dashboard page", all_ok,
                     f"API endpoints: {', '.join(details)}")


def verify_step_4():
    """Step 4: Measure time to first contentful paint (API response time)"""
    start = time.perf_counter()
    response = requests.get(f"{BASE_URL}/api/projects/{PROJECT_NAME}/features")
    elapsed = time.perf_counter() - start

    # First contentful paint should be under 1 second
    passed = response.status_code == 200 and elapsed < 1.0
    return print_step(4, "Measure time to first contentful paint", passed,
                     f"Features API response time: {elapsed*1000:.1f}ms (threshold: 1000ms)")


def verify_step_5():
    """Step 5: Measure time to interactive (concurrent request handling)"""
    urls = [
        f"{BASE_URL}/api/projects",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features/graph",
    ]

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(requests.get, url, timeout=10) for url in urls]
        results = [f.result() for f in futures]
    elapsed = time.perf_counter() - start

    all_ok = all(r.status_code == 200 for r in results)
    # Time to interactive should be under 2 seconds with concurrent requests
    passed = all_ok and elapsed < 2.0
    return print_step(5, "Measure time to interactive", passed,
                     f"Concurrent requests time: {elapsed*1000:.1f}ms (threshold: 2000ms)")


def verify_step_6():
    """Step 6: Verify no console errors during load (API error check)"""
    # Since we can't check browser console, we check API responses for errors
    endpoints = [
        f"{BASE_URL}/api/projects",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features",
        f"{BASE_URL}/api/projects/{PROJECT_NAME}/features/graph",
    ]

    errors = []
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, timeout=10)
            if response.status_code != 200:
                errors.append(f"{endpoint}: {response.status_code}")
            # Check for error in response body
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                errors.append(f"{endpoint}: {data['error']}")
        except Exception as e:
            errors.append(f"{endpoint}: {str(e)}")

    passed = len(errors) == 0
    return print_step(6, "Verify no console errors during load", passed,
                     "No API errors detected" if passed else f"Errors: {errors}")


def verify_step_7():
    """Step 7: Verify smooth scrolling through card list (consistent data ordering)"""
    # Make multiple requests and verify data is returned in consistent order
    response1 = requests.get(f"{BASE_URL}/api/projects/{PROJECT_NAME}/features")
    response2 = requests.get(f"{BASE_URL}/api/projects/{PROJECT_NAME}/features")

    data1 = response1.json()
    data2 = response2.json()

    consistent = True
    for key in ["pending", "in_progress", "done"]:
        ids1 = [f["id"] for f in data1.get(key, [])]
        ids2 = [f["id"] for f in data2.get(key, [])]
        if ids1 != ids2:
            consistent = False
            break

    # Also check graph node ordering
    graph1 = requests.get(f"{BASE_URL}/api/projects/{PROJECT_NAME}/features/graph").json()
    graph2 = requests.get(f"{BASE_URL}/api/projects/{PROJECT_NAME}/features/graph").json()
    graph_consistent = [n["id"] for n in graph1["nodes"]] == [n["id"] for n in graph2["nodes"]]

    passed = consistent and graph_consistent
    return print_step(7, "Verify smooth scrolling through card list", passed,
                     "Data ordering is consistent across requests")


def verify_step_8():
    """Step 8: Test search/filter response time under load"""
    # Test multiple concurrent requests to simulate filter/search operations
    num_requests = 5
    urls = [f"{BASE_URL}/api/projects/{PROJECT_NAME}/features"] * num_requests

    times = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
        start = time.perf_counter()
        futures = [executor.submit(requests.get, url, timeout=10) for url in urls]
        results = [f.result() for f in futures]
        elapsed = time.perf_counter() - start

    all_ok = all(r.status_code == 200 for r in results)
    avg_time = elapsed / num_requests

    # Average response time should be under 500ms even under load
    passed = all_ok and avg_time < 0.5
    return print_step(8, "Test search/filter response time under load", passed,
                     f"{num_requests} concurrent requests, avg time: {avg_time*1000:.1f}ms (threshold: 500ms)")


def main():
    """Run all verification steps."""
    print(f"\n{BOLD}Feature #85: Page Load Performance with Large Dataset{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    results = []
    results.append(verify_step_1())
    results.append(verify_step_2())
    results.append(verify_step_3())
    results.append(verify_step_4())
    results.append(verify_step_5())
    results.append(verify_step_6())
    results.append(verify_step_7())
    results.append(verify_step_8())

    # Summary
    passed = sum(results)
    total = len(results)

    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}Verification Summary: {passed}/{total} steps passed{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")

    if passed == total:
        print(f"{GREEN}{BOLD}Feature #85 VERIFIED: All steps pass!{RESET}\n")
        return True
    else:
        print(f"{RED}{BOLD}Feature #85 FAILED: {total - passed} steps failed{RESET}\n")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
