"""Test script for Features #63, #64, #65: CLI default behaviors."""
import os
import sys
import tempfile
import shutil
import json
import subprocess

# Create a test directory with some risky patterns
test_dir = tempfile.mkdtemp(prefix="test_defaults_")
with open(os.path.join(test_dir, "risky.sh"), "w") as f:
    f.write("#!/bin/bash\nrm -rf /tmp/build\n")
with open(os.path.join(test_dir, "secrets.py"), "w") as f:
    f.write("-----BEGIN PRIVATE KEY-----\nfoo\n-----END PRIVATE KEY-----\n")

# Use a temp directory for report output to avoid polluting the project
report_dir = tempfile.mkdtemp(prefix="test_reports_")

print(f"Test dir: {test_dir}")
print(f"Report dir: {report_dir}")

# ========================================================
# Feature #63: Default output path is reports/security_audit.md
# ========================================================
print("\n" + "=" * 60)
print("Feature #63: Default output path is reports/security_audit.md")
print("=" * 60)

# Step 1: Run a scan without --out flag
# We need to run from a directory where reports/ will be created
work_dir = tempfile.mkdtemp(prefix="test_workdir_")
result = subprocess.run(
    [sys.executable, "-m", "repo_concierge", "scan", test_dir],
    capture_output=True,
    text=True,
    cwd=work_dir,
)

print(f"Exit code: {result.returncode}")
print(f"Stdout: {result.stdout[:200] if result.stdout else '(empty)'}")
print(f"Stderr: {result.stderr[:200] if result.stderr else '(empty)'}")

# Step 2: Verify the report is created at reports/security_audit.md
default_report = os.path.join(work_dir, "reports", "security_audit.md")
assert os.path.isfile(default_report), f"Default report not found at: {default_report}"
print(f"Step 2: Report created at reports/security_audit.md - OK")

# Step 3: Verify the file contains valid report content
with open(default_report, "r") as f:
    content = f.read()
assert "Security Audit Report" in content, "Report missing title"
assert "Scan Metadata" in content, "Report missing metadata section"
print(f"Step 3: Report contains valid content ({len(content)} chars) - OK")

print("\n=== Feature #63 PASSED ===")
shutil.rmtree(work_dir)

# ========================================================
# Feature #64: Default format is Markdown
# ========================================================
print("\n" + "=" * 60)
print("Feature #64: Default format is Markdown")
print("=" * 60)

work_dir = tempfile.mkdtemp(prefix="test_workdir_")

# Step 1: Run a scan without --format flag
result = subprocess.run(
    [sys.executable, "-m", "repo_concierge", "scan", test_dir],
    capture_output=True,
    text=True,
    cwd=work_dir,
)

# Step 2: Verify the output file has .md extension
default_report = os.path.join(work_dir, "reports", "security_audit.md")
assert os.path.isfile(default_report), f"Default .md report not found at: {default_report}"
print(f"Step 2: Output file has .md extension - OK")

# Step 3: Verify the content is valid Markdown (not JSON)
with open(default_report, "r") as f:
    content = f.read()

# Should start with markdown header, not JSON bracket
assert content.strip().startswith("#"), f"Content doesn't start with markdown header: {content[:50]}"
# Should NOT be valid JSON
try:
    json.loads(content)
    assert False, "Content is valid JSON - should be Markdown!"
except json.JSONDecodeError:
    pass  # Expected - it's Markdown, not JSON
print(f"Step 3: Content is valid Markdown (not JSON) - OK")

print("\n=== Feature #64 PASSED ===")
shutil.rmtree(work_dir)

# ========================================================
# Feature #65: Default --fail-on is none
# ========================================================
print("\n" + "=" * 60)
print("Feature #65: Default --fail-on is none")
print("=" * 60)

work_dir = tempfile.mkdtemp(prefix="test_workdir_")

# Steps 1-2: Create files with HIGH severity findings, run scan without --fail-on
result = subprocess.run(
    [sys.executable, "-m", "repo_concierge", "scan", test_dir],
    capture_output=True,
    text=True,
    cwd=work_dir,
)

# Step 3: Verify exit code is 0 despite findings
assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}"
print(f"Step 3: Exit code is 0 despite HIGH findings - OK")

# Step 4: Verify findings are still reported in the report file
default_report = os.path.join(work_dir, "reports", "security_audit.md")
with open(default_report, "r") as f:
    content = f.read()
assert "HIGH" in content, "Report should contain HIGH findings"
assert "SHELL-001" in content or "SECRET-001" in content, "Report should contain rule IDs"
print(f"Step 4: Findings are reported in the report file - OK")

print("\n=== Feature #65 PASSED ===")
shutil.rmtree(work_dir)

# Cleanup
shutil.rmtree(test_dir)
shutil.rmtree(report_dir)

print("\n" + "=" * 60)
print("ALL CLI DEFAULT FEATURES PASSED")
print("=" * 60)
