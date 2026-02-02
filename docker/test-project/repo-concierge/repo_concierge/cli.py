"""CLI argument parsing and wiring for Repo Concierge."""

import argparse
import sys

from repo_concierge import __version__


def build_parser():
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="repo-concierge",
        description=(
            "Repo Concierge - Scan codebases for risky patterns, potential secrets, "
            "and policy violations.\n\n"
            "Use the 'scan' command to analyze a directory. Available scan flags:\n"
            "  --format   Output format (md or json)\n"
            "  --out      Custom output path for the report\n"
            "  --config   Path to a YAML rules config file\n"
            "  --fail-on  Severity threshold for non-zero exit (high, medium, low, none)\n"
            "  --verbose  Enable detailed per-file and per-finding output\n"
            "  --quiet    Suppress all output except fatal errors"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python -m repo_concierge scan ./my-project --format json --fail-on high",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan subcommand
    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan a directory for risky patterns and generate a security audit report.",
    )
    scan_parser.add_argument(
        "path",
        help="Target directory to scan.",
    )
    scan_parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output report format (default: md).",
    )
    scan_parser.add_argument(
        "--out",
        default=None,
        help="Custom output path for the report (default: reports/security_audit.md or .json).",
    )
    scan_parser.add_argument(
        "--config",
        default=None,
        help="Path to a YAML rules config file.",
    )
    scan_parser.add_argument(
        "--fail-on",
        choices=["high", "medium", "low", "none"],
        default="none",
        help="Exit with code 2 if findings meet or exceed this severity (default: none).",
    )
    verbosity_group = scan_parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose output with per-file and per-finding details.",
    )
    verbosity_group.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress all terminal output except fatal errors (CI-friendly).",
    )

    return parser


def main(argv=None):
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "scan":
        # Import here to avoid circular imports and keep startup fast
        from repo_concierge.scanner import run_scan

        sys.exit(run_scan(args))
