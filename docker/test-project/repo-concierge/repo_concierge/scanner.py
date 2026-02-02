"""Scanning engine: file discovery and pattern matching."""

import os
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional, Set

from repo_concierge.models import Finding, ScanResult
from repo_concierge.rules import BUILT_IN_RULES, get_all_rules

# Directories to ignore during scanning
IGNORE_DIRS: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
}

# File extensions eligible for scanning
ELIGIBLE_EXTENSIONS: Set[str] = {
    ".py",
    ".sh",
    ".js",
    ".ts",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
}

# Also include files starting with .env
ENV_PREFIX = ".env"

# Maximum file size to scan (1 MB)
MAX_FILE_SIZE = 1_048_576


def _is_eligible_file(file_path: str) -> bool:
    """Check if a file is eligible for scanning based on extension.

    Args:
        file_path: Path to the file.

    Returns:
        True if the file should be scanned.
    """
    basename = os.path.basename(file_path)
    # .env files (e.g., .env, .env.local, .env.production)
    if basename.startswith(ENV_PREFIX):
        return True
    _, ext = os.path.splitext(file_path)
    return ext.lower() in ELIGIBLE_EXTENSIONS


def discover_files(
    target_path: str,
    verbose: bool = False,
    quiet: bool = False,
) -> List[str]:
    """Recursively discover eligible files in the target directory.

    Args:
        target_path: Root directory to scan.
        verbose: If True, print per-file details to stderr.
        quiet: If True, suppress all output.

    Returns:
        Sorted list of absolute file paths eligible for scanning.
    """
    discovered: List[str] = []

    for dirpath, dirnames, filenames in os.walk(target_path):
        # Filter out ignored directories (modify in-place to prevent os.walk descending)
        dirnames[:] = [
            d for d in dirnames if d not in IGNORE_DIRS
        ]

        for filename in filenames:
            file_path = os.path.join(dirpath, filename)

            # Check if file is eligible
            if not _is_eligible_file(file_path):
                continue

            # Check file size
            try:
                file_size = os.path.getsize(file_path)
                if file_size > MAX_FILE_SIZE:
                    if verbose:
                        print(
                            f"Warning: Skipping {file_path} ({file_size} bytes > 1MB limit)",
                            file=sys.stderr,
                        )
                    continue
            except OSError as e:
                if verbose:
                    print(
                        f"Warning: Cannot stat {file_path}: {e}",
                        file=sys.stderr,
                    )
                elif not quiet:
                    print(
                        f"Warning: Skipping {file_path} (permission error)",
                        file=sys.stderr,
                    )
                continue

            discovered.append(file_path)

    return sorted(discovered)


def _match_file_globs(file_path: str, file_globs: Optional[List[str]]) -> bool:
    """Check if a file matches the rule's file_globs filter.

    Args:
        file_path: Path to the file being scanned.
        file_globs: List of glob patterns (e.g., ['*.sh', '*.py']).
            If None, the rule applies to all files.

    Returns:
        True if the file matches at least one glob pattern (or file_globs is None).
    """
    if file_globs is None:
        return True

    basename = os.path.basename(file_path)
    for glob_pattern in file_globs:
        # Simple glob matching: *.ext
        if glob_pattern.startswith("*"):
            ext = glob_pattern[1:]  # e.g., ".sh"
            if basename.endswith(ext):
                return True
        elif basename == glob_pattern:
            return True

    return False


def scan_file(file_path: str, verbose: bool = False, quiet: bool = False) -> List[Finding]:
    """Scan a single file for risky patterns.

    Args:
        file_path: Path to the file to scan.
        verbose: If True, print each finding as detected.
        quiet: If True, suppress all output.

    Returns:
        List of Finding objects detected in the file.
    """
    findings: List[Finding] = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except PermissionError as e:
        if not quiet:
            print(f"Warning: Permission denied reading {file_path}", file=sys.stderr)
        return findings
    except OSError as e:
        if not quiet:
            print(f"Warning: Error reading {file_path}: {e}", file=sys.stderr)
        return findings

    rules = get_all_rules()

    for rule in rules:
        # Skip rules with empty patterns (e.g., POLICY-004 pass-through)
        if not rule.pattern:
            continue

        # Check if rule applies to this file type
        if not _match_file_globs(file_path, rule.file_globs):
            continue

        try:
            compiled_pattern = re.compile(rule.pattern)
        except re.error:
            continue

        for line_num, line in enumerate(lines, start=1):
            line_stripped = line.rstrip("\n\r")
            if compiled_pattern.search(line_stripped):
                finding = Finding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    file_path=file_path,
                    line_number=line_num,
                    snippet=line_stripped[:200],  # Truncate long lines
                    recommendation=rule.recommendation,
                )
                findings.append(finding)

                if verbose and not quiet:
                    print(
                        f"  [{rule.severity}] {rule.id} {rule.name} "
                        f"at {file_path}:{line_num}",
                        file=sys.stderr,
                    )

    return findings


def scan_directory(
    target_path: str,
    verbose: bool = False,
    quiet: bool = False,
) -> ScanResult:
    """Scan a directory recursively for risky patterns.

    Args:
        target_path: Root directory to scan.
        verbose: If True, print detailed per-file output.
        quiet: If True, suppress all output.

    Returns:
        ScanResult with all findings and metadata.
    """
    target_path = os.path.abspath(target_path)
    timestamp = datetime.now(timezone.utc).isoformat()

    # Discover files
    files = discover_files(target_path, verbose=verbose, quiet=quiet)

    if not quiet:
        print(f"Scanning {len(files)} files...", file=sys.stderr)

    # Scan each file
    all_findings: List[Finding] = []
    for file_path in files:
        if verbose and not quiet:
            print(f"Scanning: {file_path}", file=sys.stderr)

        file_findings = scan_file(file_path, verbose=verbose, quiet=quiet)
        all_findings.extend(file_findings)

    # Count severities
    high_count = sum(1 for f in all_findings if f.severity == "HIGH")
    medium_count = sum(1 for f in all_findings if f.severity == "MEDIUM")
    low_count = sum(1 for f in all_findings if f.severity == "LOW")

    result = ScanResult(
        target_path=target_path,
        timestamp=timestamp,
        files_scanned=len(files),
        ignore_rules=sorted(IGNORE_DIRS),
        findings=all_findings,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
    )

    # Print summary in normal mode
    if not quiet:
        print(
            f"Findings: HIGH={high_count} MED={medium_count} LOW={low_count}",
            file=sys.stderr,
        )

        # Print top 5 findings
        if all_findings and not verbose:
            print("", file=sys.stderr)
            print("Top findings:", file=sys.stderr)
            for finding in all_findings[:5]:
                print(
                    f"  [{finding.severity}] {finding.rule_id}: "
                    f"{finding.file_path}:{finding.line_number} - {finding.snippet[:80]}",
                    file=sys.stderr,
                )

    return result


def _validate_output_path(output_path: str, quiet: bool = False) -> Optional[str]:
    """Validate output path to prevent path traversal attacks.

    The output path must resolve to a location within the current working
    directory or a subdirectory thereof. Absolute paths and paths containing
    '..' that escape the working directory are rejected.

    Args:
        output_path: The user-provided output path.
        quiet: If True, suppress warning messages.

    Returns:
        The validated, normalized path if safe; None if path is unsafe.
    """
    # Get current working directory as the safe base
    cwd = os.path.abspath(os.getcwd())

    # Normalize the output path relative to cwd
    # os.path.abspath will resolve '..' and make relative paths absolute
    resolved_path = os.path.abspath(output_path)

    # Check if the resolved path starts with the current working directory
    # Use os.path.commonpath to handle edge cases properly
    try:
        common = os.path.commonpath([cwd, resolved_path])
        if common != cwd:
            # The resolved path is outside cwd
            if not quiet:
                print(
                    f"Error: Output path escapes working directory: {output_path}",
                    file=sys.stderr,
                )
                print(
                    f"  Resolved to: {resolved_path}",
                    file=sys.stderr,
                )
                print(
                    f"  Must be within: {cwd}",
                    file=sys.stderr,
                )
            return None
    except ValueError:
        # commonpath raises ValueError if paths are on different drives (Windows)
        if not quiet:
            print(
                f"Error: Output path is on a different drive: {output_path}",
                file=sys.stderr,
            )
        return None

    return resolved_path


def run_scan(args) -> int:
    """Run a scan based on CLI arguments.

    Args:
        args: Parsed argparse namespace with scan parameters.

    Returns:
        Exit code: 0 on success, 1 on error, 2 when --fail-on threshold is met.
    """
    target_path = args.path
    verbose = getattr(args, "verbose", False)
    quiet = getattr(args, "quiet", False)
    fail_on = getattr(args, "fail_on", "none")
    output_format = getattr(args, "format", "md")
    output_path = getattr(args, "out", None)
    config_path = getattr(args, "config", None)

    # Validate output path if provided
    if output_path is not None:
        validated_path = _validate_output_path(output_path, quiet=quiet)
        if validated_path is None:
            return 1
        output_path = validated_path

    # Load and validate config file if specified
    if config_path is not None:
        from repo_concierge.config import load_allowlist_config
        config, config_warnings = load_allowlist_config(
            config_path, verbose=verbose, quiet=quiet
        )
        # Config validation warnings are printed by load_allowlist_config
        # Scan continues gracefully regardless of config issues

    # Validate target path
    if not os.path.exists(target_path):
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        return 1

    if not os.path.isdir(target_path):
        print(f"Error: Target path is not a directory: {target_path}", file=sys.stderr)
        return 1

    try:
        result = scan_directory(target_path, verbose=verbose, quiet=quiet)
    except Exception as e:
        print(f"Error: Unexpected scan failure: {e}", file=sys.stderr)
        return 1

    # Generate report
    try:
        from repo_concierge.reporting import write_markdown_report, write_json_report

        if output_path is None:
            if output_format == "json":
                output_path = "reports/security_audit.json"
            else:
                output_path = "reports/security_audit.md"

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if output_format == "json":
            write_json_report(result, output_path)
        else:
            write_markdown_report(result, output_path)

        if not quiet:
            print(f"Report written to: {output_path}", file=sys.stderr)

    except ImportError:
        if not quiet:
            print("Warning: Report generation not available.", file=sys.stderr)
    except Exception as e:
        print(f"Error: Failed to write report: {e}", file=sys.stderr)
        return 1

    # Check fail-on threshold
    if fail_on != "none":
        severity_map = {"high": result.high_count, "medium": result.medium_count, "low": result.low_count}
        # Threshold means: fail if findings at this level or above exist
        if fail_on == "low":
            total_failing = result.high_count + result.medium_count + result.low_count
        elif fail_on == "medium":
            total_failing = result.high_count + result.medium_count
        elif fail_on == "high":
            total_failing = result.high_count
        else:
            total_failing = 0

        if total_failing > 0:
            return 2

    return 0
