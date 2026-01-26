#!/usr/bin/env python3
"""
Standalone Verification Script for Feature #101:
Auto-repair logs before and after state for auditability

This script verifies all 5 feature steps:
1. Before removing self-reference, log: "Feature {id} has self-reference, removing"
2. After fix, log: "Feature {id} dependencies changed from {old} to {new}"
3. Include timestamp in log entries
4. Use structured logging format for easy parsing
5. Verify logs appear at INFO level (not just DEBUG)
"""

import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path
import re

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import Feature, create_database
from api.dependency_resolver import repair_self_references, repair_orphaned_dependencies


def setup_test_db():
    """Create a temporary test database."""
    tmpdir = tempfile.mkdtemp()
    project_dir = Path(tmpdir)
    engine, session_maker = create_database(project_dir)
    return project_dir, session_maker


def verify_step1_before_log_message():
    """Step 1: Before removing self-reference, log: 'Feature {id} has self-reference, removing'"""
    print("\n" + "="*70)
    print("Step 1: Verify BEFORE log message format")
    print("="*70)

    project_dir, session_maker = setup_test_db()
    session = session_maker()

    try:
        # Create feature with self-reference
        feature = Feature(
            id=42,
            priority=1,
            category="test",
            name="Test Feature",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=[42, 100]
        )
        session.add(feature)
        session.commit()

        # Set up log capture
        logger = logging.getLogger("api.dependency_resolver")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Run repair
        repair_self_references(session)

        # Check logs
        handler.flush()
        log_messages = [r.getMessage() for r in handler.buffer]

        before_logs = [m for m in log_messages if "before_fix" in m]
        assert len(before_logs) >= 1, "FAIL: No before_fix log found"

        before_msg = before_logs[0]
        assert "Feature 42 has self-reference, removing" in before_msg, \
            f"FAIL: Before log missing expected message. Got: {before_msg}"

        print("  - Before log found: YES")
        print(f"  - Message contains 'Feature 42 has self-reference, removing': YES")
        print(f"  - Full message: {before_msg[:100]}...")
        print("  PASS: Step 1 verified!")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        session.close()


def verify_step2_after_log_message():
    """Step 2: After fix, log: 'Feature {id} dependencies changed from {old} to {new}'"""
    print("\n" + "="*70)
    print("Step 2: Verify AFTER log message format")
    print("="*70)

    project_dir, session_maker = setup_test_db()
    session = session_maker()

    try:
        # Create feature with self-reference
        feature = Feature(
            id=55,
            priority=1,
            category="test",
            name="Test Feature",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=[55, 100]
        )
        session.add(feature)
        session.commit()

        # Set up log capture
        import logging.handlers
        logger = logging.getLogger("api.dependency_resolver")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Run repair
        repair_self_references(session)

        # Check logs
        handler.flush()
        log_messages = [r.getMessage() for r in handler.buffer]

        after_logs = [m for m in log_messages if "after_fix" in m]
        assert len(after_logs) >= 1, "FAIL: No after_fix log found"

        after_msg = after_logs[0]
        assert "Feature 55 dependencies changed from" in after_msg, \
            f"FAIL: After log missing expected message. Got: {after_msg}"

        print("  - After log found: YES")
        print(f"  - Message contains 'Feature 55 dependencies changed from': YES")
        print(f"  - Full message: {after_msg[:100]}...")
        print("  PASS: Step 2 verified!")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        session.close()


def verify_step3_timestamp_in_logs():
    """Step 3: Include timestamp in log entries"""
    print("\n" + "="*70)
    print("Step 3: Verify timestamps in log entries")
    print("="*70)

    project_dir, session_maker = setup_test_db()
    session = session_maker()

    try:
        # Create feature with self-reference
        feature = Feature(
            id=77,
            priority=1,
            category="test",
            name="Test Feature",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=[77]
        )
        session.add(feature)
        session.commit()

        # Set up log capture
        import logging.handlers
        logger = logging.getLogger("api.dependency_resolver")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Run repair
        repair_self_references(session)

        # Check logs have timestamps
        handler.flush()
        repair_logs = [r for r in handler.buffer if "repair_self_references" in r.getMessage()]

        assert len(repair_logs) >= 2, "FAIL: Not enough log records"

        for record in repair_logs:
            assert hasattr(record, 'created'), "FAIL: Log record missing 'created' timestamp"
            now = datetime.now().timestamp()
            assert now - record.created < 60, "FAIL: Timestamp not recent"

        print("  - Log records have 'created' timestamp: YES")
        print(f"  - Timestamps are recent (within 60 seconds): YES")
        print(f"  - Sample timestamp: {datetime.fromtimestamp(repair_logs[0].created).isoformat()}")
        print("  PASS: Step 3 verified!")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        session.close()


def verify_step4_structured_logging_format():
    """Step 4: Use structured logging format for easy parsing"""
    print("\n" + "="*70)
    print("Step 4: Verify structured logging format (key=value pairs)")
    print("="*70)

    project_dir, session_maker = setup_test_db()
    session = session_maker()

    try:
        # Create feature with self-reference
        feature = Feature(
            id=88,
            priority=1,
            category="test",
            name="Test Feature",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=[88, 200]
        )
        session.add(feature)
        session.commit()

        # Set up log capture
        import logging.handlers
        logger = logging.getLogger("api.dependency_resolver")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Run repair
        repair_self_references(session)

        # Check structured format
        handler.flush()
        repair_logs = [r for r in handler.buffer
                      if "repair_self_references" in r.getMessage()
                      and ("before_fix" in r.getMessage() or "after_fix" in r.getMessage())]

        assert len(repair_logs) >= 2, "FAIL: Not enough log records"

        for record in repair_logs:
            msg = record.getMessage()
            # Check key=value format
            assert "action=" in msg, f"FAIL: Missing 'action=' in: {msg}"
            assert "feature_id=" in msg, f"FAIL: Missing 'feature_id=' in: {msg}"

            # Verify values are parseable
            action_match = re.search(r'action=(\w+)', msg)
            assert action_match, "FAIL: Cannot parse action value"
            assert action_match.group(1) in ['before_fix', 'after_fix'], \
                f"FAIL: Invalid action value: {action_match.group(1)}"

            fid_match = re.search(r'feature_id=(\d+)', msg)
            assert fid_match, "FAIL: Cannot parse feature_id value"
            assert fid_match.group(1) == "88", f"FAIL: Wrong feature_id: {fid_match.group(1)}"

        print("  - Logs contain 'action=' key: YES")
        print("  - Logs contain 'feature_id=' key: YES")
        print("  - Values are parseable with regex: YES")
        print(f"  - Sample: action={action_match.group(1)}, feature_id={fid_match.group(1)}")
        print("  PASS: Step 4 verified!")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        session.close()


def verify_step5_info_level_logging():
    """Step 5: Verify logs appear at INFO level (not just DEBUG)"""
    print("\n" + "="*70)
    print("Step 5: Verify logs appear at INFO level")
    print("="*70)

    project_dir, session_maker = setup_test_db()
    session = session_maker()

    try:
        # Create feature with self-reference
        feature = Feature(
            id=99,
            priority=1,
            category="test",
            name="Test Feature",
            description="Test",
            steps=["Step 1"],
            passes=False,
            in_progress=False,
            dependencies=[99]
        )
        session.add(feature)
        session.commit()

        # Set up log capture at INFO level
        import logging.handlers
        logger = logging.getLogger("api.dependency_resolver")
        handler = logging.handlers.MemoryHandler(capacity=100)
        handler.setLevel(logging.INFO)  # Only capture INFO and above
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # Run repair
        repair_self_references(session)

        # Check log levels
        handler.flush()
        repair_logs = [r for r in handler.buffer
                      if "repair_self_references" in r.getMessage()
                      and ("before_fix" in r.getMessage() or "after_fix" in r.getMessage())]

        assert len(repair_logs) >= 2, "FAIL: Not enough log records at INFO level"

        for record in repair_logs:
            assert record.levelno == logging.INFO, \
                f"FAIL: Log level is {record.levelname}, expected INFO"

        print("  - Before/after logs visible at INFO level: YES")
        print(f"  - Number of INFO-level logs captured: {len(repair_logs)}")
        print(f"  - Log level (numeric): {logging.INFO}")
        print(f"  - Log level (name): INFO")
        print("  PASS: Step 5 verified!")
        return True

    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        session.close()


def main():
    """Run all verification steps."""
    print("\n" + "#"*70)
    print("# Feature #101: Auto-repair logs before and after state for auditability")
    print("#"*70)

    import logging.handlers

    results = {
        "Step 1: Before log message": verify_step1_before_log_message(),
        "Step 2: After log message": verify_step2_after_log_message(),
        "Step 3: Timestamp in logs": verify_step3_timestamp_in_logs(),
        "Step 4: Structured logging format": verify_step4_structured_logging_format(),
        "Step 5: INFO level logging": verify_step5_info_level_logging(),
    }

    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)

    all_passed = True
    for step, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {step}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("RESULT: ALL 5 VERIFICATION STEPS PASSED!")
        print("Feature #101 is ready to be marked as passing.")
    else:
        print("RESULT: SOME VERIFICATION STEPS FAILED")
        print("Please review and fix the implementation.")
    print("="*70 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
