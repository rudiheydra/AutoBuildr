"""
Verification script for Feature #154:
Replace turn-count heuristic with event-based counting in useAgentRunUpdates.ts
"""
import pathlib
import sys

hook_file = pathlib.Path("/home/rudih/workspace/AutoBuildr/ui/src/hooks/useAgentRunUpdates.ts")
content = hook_file.read_text()

passed = 0
failed = 0

def check(label, condition):
    global passed, failed
    if condition:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label}")
        failed += 1

print("Feature #154 Verification")
print("=" * 60)

# Step 1: Locate the turns_used calculation
print("\nStep 1: Locate the turns_used calculation in hooks/useAgentRunUpdates.ts")
check("Hook file exists", hook_file.exists())
check("turnsUsed referenced in hook", "turnsUsed" in content)

# Step 2: Replace the heuristic with count of turn_complete events
print("\nStep 2: Replace heuristic (Math.ceil(sequence / 3)) with turn_complete event counting")
check("Old heuristic Math.ceil(message.sequence / 3) removed from useAgentRunUpdates",
      "Math.ceil(message.sequence / 3)" not in content)
check("Old heuristic Math.ceil(eventMsg.sequence / 3) removed from useMultipleAgentRunUpdates",
      "Math.ceil(eventMsg.sequence / 3)" not in content)
check("No sequence/3 pattern remains anywhere",
      "sequence / 3" not in content and "sequence/3" not in content)
check("Event-based counting (prev.turnsUsed + 1) present in useAgentRunUpdates",
      "prev.turnsUsed + 1" in content)
check("Event-based counting (currentState.turnsUsed + 1) present in useMultipleAgentRunUpdates",
      "currentState.turnsUsed + 1" in content)

# Step 3: Backend emits turn_complete events (verify via source)
print("\nStep 3: Backend emits turn_complete events")
broadcaster_file = pathlib.Path("/home/rudih/workspace/AutoBuildr/server/event_broadcaster.py")
broadcaster_content = broadcaster_file.read_text()
check("event_broadcaster.py exists", broadcaster_file.exists())
check("turn_complete in SIGNIFICANT_EVENT_TYPES", "turn_complete" in broadcaster_content)

kernel_file = pathlib.Path("/home/rudih/workspace/AutoBuildr/api/harness_kernel.py")
kernel_content = kernel_file.read_text()
check("harness_kernel.py records turn_complete events", "record_turn_complete" in kernel_content)

# Step 4: turns_used equals the number of actual completed turns
print("\nStep 4: turns_used equals the number of actual completed turns")
check("turn_complete event type check present in useAgentRunUpdates",
      "message.event_type === 'turn_complete'" in content)
check("turn_complete event type check present in useMultipleAgentRunUpdates",
      "eventMsg.event_type === 'turn_complete'" in content)
# Each turn_complete increments by exactly 1, so turns_used = count of turn_complete events
check("Increment is exactly +1 (not heuristic-based)",
      "prev.turnsUsed + 1" in content and "currentState.turnsUsed + 1" in content)

# Step 5: Progress bar does not jump unpredictably
print("\nStep 5: Verify progress bar does not jump unpredictably")
# Old code: Math.ceil(sequence / 3) could jump from e.g. 1 to 3 if sequence numbers skip
# New code: +1 each time ensures monotonic, predictable progression
check("No Math.ceil heuristic that could cause jumps",
      "Math.ceil" not in content or "Math.ceil(message.sequence" not in content)
check("Monotonic +1 increment prevents unpredictable jumps",
      "prev.turnsUsed + 1" in content)

# Summary
print("\n" + "=" * 60)
total = passed + failed
print(f"Results: {passed}/{total} checks passed")
if failed > 0:
    print("FAILED")
    sys.exit(1)
else:
    print("ALL PASSED")
    sys.exit(0)
