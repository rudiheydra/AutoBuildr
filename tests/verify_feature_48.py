#!/usr/bin/env python3
"""
Verification Script for Feature #48: Path Traversal Attack Detection

This script verifies all 6 feature steps are implemented correctly:
1. Check for .. sequences in raw path string
2. Check for URL-encoded traversal %2e%2e
3. Check for null bytes that could truncate paths
4. Normalize path and compare to original
5. Block if normalized differs (indicates traversal attempt)
6. Log detailed violation info for security audit

Usage:
    python tests/verify_feature_48.py

Returns exit code 0 if all verifications pass, 1 otherwise.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.tool_policy import (
    PathTraversalResult,
    contains_null_byte,
    contains_path_traversal,
    detect_path_traversal_attack,
    normalize_path_for_comparison,
    path_differs_after_normalization,
    validate_directory_access,
)


def check(condition: bool, message: str) -> bool:
    """Check a condition and print result."""
    status = "✓ PASS" if condition else "✗ FAIL"
    print(f"  {status}: {message}")
    return condition


def verify_step1_dotdot_sequences():
    """Verify Step 1: Check for .. sequences in raw path string."""
    print("\n=== Step 1: Check for .. sequences in raw path string ===")
    all_pass = True

    # Test detection of ..
    result = detect_path_traversal_attack("/home/user/../root/secret")
    all_pass &= check(
        result.detected is True,
        "Detects .. sequence in path"
    )
    all_pass &= check(
        result.attack_type == "dotdot_traversal",
        "Identifies attack type as 'dotdot_traversal'"
    )
    all_pass &= check(
        result.matched_pattern == "..",
        "Reports matched pattern as '..' "
    )

    # Test no false positive
    result = detect_path_traversal_attack("/home/user/file..txt")
    all_pass &= check(
        result.detected is False,
        "No false positive for double dots in filename"
    )

    return all_pass


def verify_step2_url_encoded_traversal():
    """Verify Step 2: Check for URL-encoded traversal %2e%2e."""
    print("\n=== Step 2: Check for URL-encoded traversal %2e%2e ===")
    all_pass = True

    # Test URL-encoded ..
    result = detect_path_traversal_attack("/home/%2e%2e/root")
    all_pass &= check(
        result.detected is True,
        "Detects URL-encoded .. (%2e%2e)"
    )
    all_pass &= check(
        result.attack_type == "url_encoded_traversal",
        "Identifies attack type as 'url_encoded_traversal'"
    )
    all_pass &= check(
        "%2e%2e" in result.matched_pattern.lower(),
        "Reports matched pattern containing '%2e%2e'"
    )

    # Test double URL-encoded
    result = detect_path_traversal_attack("/home/%252e%252e/root")
    all_pass &= check(
        result.detected is True,
        "Detects double URL-encoded traversal (%252e%252e)"
    )

    # Test Unicode overlong encoding
    result = detect_path_traversal_attack("/home/..%c0%af/root")
    all_pass &= check(
        result.detected is True,
        "Detects Unicode overlong encoding (..%c0%af)"
    )

    return all_pass


def verify_step3_null_bytes():
    """Verify Step 3: Check for null bytes that could truncate paths."""
    print("\n=== Step 3: Check for null bytes that could truncate paths ===")
    all_pass = True

    # Test actual null byte
    result = detect_path_traversal_attack("/etc/passwd\x00.txt")
    all_pass &= check(
        result.detected is True,
        "Detects actual null byte character (\\x00)"
    )
    all_pass &= check(
        result.attack_type == "null_byte",
        "Identifies attack type as 'null_byte'"
    )
    all_pass &= check(
        "null_position" in result.details,
        "Reports null byte position in details"
    )

    # Test URL-encoded null byte
    result = detect_path_traversal_attack("/etc/passwd%00.jpg")
    all_pass &= check(
        result.detected is True,
        "Detects URL-encoded null byte (%00)"
    )
    all_pass &= check(
        "effective_path" in result.details,
        "Reports effective path after truncation"
    )

    # Test contains_null_byte helper
    has_null, position = contains_null_byte("/etc/passwd\x00.txt")
    all_pass &= check(
        has_null is True and position == 11,
        "contains_null_byte() returns correct position"
    )

    return all_pass


def verify_step4_normalize_and_compare():
    """Verify Step 4: Normalize path and compare to original."""
    print("\n=== Step 4: Normalize path and compare to original ===")
    all_pass = True

    # Test normalization removes ..
    normalized = normalize_path_for_comparison("/home/user/../root/secret")
    all_pass &= check(
        ".." not in normalized,
        "normalize_path_for_comparison() removes .. sequences"
    )

    # Test path_differs_after_normalization
    differs, normalized = path_differs_after_normalization("/home/user/../root")
    all_pass &= check(
        differs is True,
        "path_differs_after_normalization() detects difference"
    )
    all_pass &= check(
        normalized == "/home/root",
        f"Normalized path is correct (got: {normalized})"
    )

    # Test clean path doesn't differ
    differs, normalized = path_differs_after_normalization("/home/user/file.txt")
    all_pass &= check(
        differs is False,
        "Clean path does not differ after normalization"
    )

    return all_pass


def verify_step5_block_on_difference():
    """Verify Step 5: Block if normalized differs (indicates traversal attempt)."""
    print("\n=== Step 5: Block if normalized differs ===")
    all_pass = True

    # Test that traversal is blocked
    result = detect_path_traversal_attack("/home/../root")
    all_pass &= check(
        result.detected is True,
        "Traversal attempt is blocked"
    )

    # Test integration with validate_directory_access
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        allowed_dirs = [Path(tmpdir)]
        allowed, reason, details = validate_directory_access(
            "write_file",
            f"{tmpdir}/../etc/passwd",
            allowed_dirs,
        )
        all_pass &= check(
            allowed is False,
            "validate_directory_access() blocks traversal attempt"
        )
        all_pass &= check(
            details.get("traversal_detected") is True,
            "Details include traversal_detected flag"
        )

    return all_pass


def verify_step6_security_audit_logging():
    """Verify Step 6: Log detailed violation info for security audit."""
    print("\n=== Step 6: Log detailed violation info for security audit ===")
    all_pass = True

    # Test dotdot attack includes audit info
    result = detect_path_traversal_attack("/home/../root/secret")
    all_pass &= check(
        result.attack_type is not None,
        "Attack type is recorded"
    )
    all_pass &= check(
        result.matched_pattern is not None,
        "Matched pattern is recorded"
    )
    all_pass &= check(
        result.original_path == "/home/../root/secret",
        "Original path is recorded"
    )
    all_pass &= check(
        "checks_performed" in result.details,
        "Details include checks_performed list"
    )
    all_pass &= check(
        "timestamp" in result.details,
        "Details include timestamp for audit"
    )

    # Test URL-encoded attack includes encoding type
    result = detect_path_traversal_attack("/home/%2e%2e/root")
    all_pass &= check(
        "encoding_type" in result.details,
        "URL-encoded attack includes encoding_type in details"
    )

    # Test null byte attack includes position
    result = detect_path_traversal_attack("/etc/passwd%00.txt")
    all_pass &= check(
        "null_position" in result.details,
        "Null byte attack includes position in details"
    )

    # Test clean path includes result status
    result = detect_path_traversal_attack("/home/user/file.txt")
    all_pass &= check(
        result.details.get("result") == "clean",
        "Clean path includes result=clean in details"
    )

    return all_pass


def main():
    """Run all verification steps."""
    print("=" * 60)
    print("Feature #48: Path Traversal Attack Detection - Verification")
    print("=" * 60)

    results = []

    # Run all verification steps
    results.append(("Step 1: Check for .. sequences", verify_step1_dotdot_sequences()))
    results.append(("Step 2: URL-encoded traversal", verify_step2_url_encoded_traversal()))
    results.append(("Step 3: Null bytes", verify_step3_null_bytes()))
    results.append(("Step 4: Normalize and compare", verify_step4_normalize_and_compare()))
    results.append(("Step 5: Block on difference", verify_step5_block_on_difference()))
    results.append(("Step 6: Security audit logging", verify_step6_security_audit_logging()))

    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    all_pass = True
    for step_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {step_name}")
        if not passed:
            all_pass = False

    print("\n" + "=" * 60)
    if all_pass:
        print("✓ ALL VERIFICATION STEPS PASSED")
        print("Feature #48: Path Traversal Attack Detection is READY")
        return 0
    else:
        print("✗ SOME VERIFICATION STEPS FAILED")
        print("Please review the failures above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
