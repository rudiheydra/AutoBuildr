#!/usr/bin/env python3
"""
Test the /api/agent-runs/:id/events endpoint.
"""
import requests
import sys

# Test run ID from the test data we created
RUN_ID = "03225b0d-d2ae-409c-bbc4-8ed712f83c27"
BASE_URL = "http://localhost:8888"

def test_events_endpoint():
    """Test the events endpoint."""
    url = f"{BASE_URL}/api/agent-runs/{RUN_ID}/events"
    print(f"Testing: GET {url}")

    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Total events: {data.get('total', 'N/A')}")
            print(f"Has more: {data.get('has_more', 'N/A')}")
            print(f"Events returned: {len(data.get('events', []))}")

            # Print first event
            events = data.get('events', [])
            if events:
                print("\nFirst event:")
                print(f"  Type: {events[0].get('event_type')}")
                print(f"  Sequence: {events[0].get('sequence')}")
                print(f"  Timestamp: {events[0].get('timestamp')}")
            return True
        elif response.status_code == 404:
            print("Endpoint not found - routes may not be registered")
            print(f"Response: {response.text}")
            return False
        else:
            print(f"Unexpected status: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("Connection error - server may not be running")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_filter():
    """Test filtering by event type."""
    url = f"{BASE_URL}/api/agent-runs/{RUN_ID}/events?event_type=tool_call"
    print(f"\nTesting filter: GET {url}")

    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Filtered events: {len(data.get('events', []))}")
            # Verify all events are tool_call
            events = data.get('events', [])
            all_tool_calls = all(e.get('event_type') == 'tool_call' for e in events)
            print(f"All tool_call: {all_tool_calls}")
            return all_tool_calls
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_pagination():
    """Test pagination."""
    url = f"{BASE_URL}/api/agent-runs/{RUN_ID}/events?limit=3&offset=0"
    print(f"\nTesting pagination: GET {url}")

    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Requested limit: 3")
            print(f"Events returned: {len(data.get('events', []))}")
            print(f"Has more: {data.get('has_more')}")
            return len(data.get('events', [])) <= 3
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Event Timeline API Tests")
    print("=" * 60)

    results = []
    results.append(("Basic endpoint", test_events_endpoint()))
    results.append(("Filter by type", test_filter()))
    results.append(("Pagination", test_pagination()))

    print("\n" + "=" * 60)
    print("Results:")
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print("=" * 60)
    print(f"Overall: {'PASS' if all_passed else 'FAIL'}")

    sys.exit(0 if all_passed else 1)
