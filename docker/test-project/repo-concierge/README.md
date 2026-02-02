# Repo Concierge

A Python CLI tool that scans codebases for risky patterns (dangerous shell commands, potential secrets, policy violations against a command allowlist), generates structured security audit reports, and returns meaningful exit codes for CI integration.

## Quick Start

```bash
# Set up the development environment
./init.sh

# Activate the virtual environment
source .venv/bin/activate

# Scan a directory
python -m repo_concierge scan /path/to/repo

# Show help
python -m repo_concierge --help
```

## Features

- **Shell Pattern Detection**: Detects dangerous shell commands like `rm -rf`, `sudo rm`, `curl | bash`, `wget | sh`, `eval()`, and backtick command substitution
- **Secret Detection**: Finds private keys, AWS access keys, API key assignments, Bearer tokens, and high-entropy strings
- **Policy Enforcement**: Validates shell commands against a configurable allowlist
- **Multiple Output Formats**: Generate reports in Markdown or JSON
- **CI Integration**: Meaningful exit codes for pipeline integration via `--fail-on`
- **Configurable**: YAML-based command allowlist, customizable output paths

## CLI Usage

```bash
python -m repo_concierge scan <path> [options]
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--format md\|json` | Output report format | `md` |
| `--out <path>` | Custom output file path | `reports/security_audit.md` |
| `--config <path>` | Path to rules config YAML | `config/command_allowlist.yaml` |
| `--fail-on high\|medium\|low\|none` | Exit code 2 if severity threshold met | `none` |
| `--verbose` | Detailed per-file and per-finding output | off |
| `--quiet` | Suppress all output except fatal errors | off |
| `--help` | Display usage information | - |
| `--version` | Display version | - |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Scan completed successfully (or `--fail-on none`) |
| `1` | Unexpected error (bad path, missing file, etc.) |
| `2` | Findings exceed `--fail-on` severity threshold |

### Examples

```bash
# Basic scan with Markdown report
python -m repo_concierge scan ./my-project

# JSON output to custom path
python -m repo_concierge scan ./my-project --format json --out ./audit.json

# CI mode: fail on high severity, quiet output
python -m repo_concierge scan . --fail-on high --quiet

# Verbose scan for debugging
python -m repo_concierge scan . --verbose

# Custom allowlist
python -m repo_concierge scan . --config ./my-allowlist.yaml
```

## Built-in Rules

### Shell Pattern Rules

| Rule ID | Pattern | Severity | Description |
|---------|---------|----------|-------------|
| SHELL-001 | `rm -rf` | HIGH | Recursive force deletion |
| SHELL-002 | `sudo rm` | HIGH | Privileged file deletion |
| SHELL-003 | `curl \| bash` | HIGH | Remote code execution via curl |
| SHELL-004 | `wget \| sh` | HIGH | Remote code execution via wget |
| SHELL-005 | `eval()` | MEDIUM | Dynamic code execution in shell |
| SHELL-006 | Backtick substitution | MEDIUM | Command substitution in shell |

### Secret Detection Rules

| Rule ID | Pattern | Severity | Description |
|---------|---------|----------|-------------|
| SECRET-001 | `BEGIN PRIVATE KEY` | HIGH | Private key blocks |
| SECRET-002 | `AKIA...` | HIGH | AWS access key patterns |
| SECRET-003 | `API_KEY=` | MEDIUM | API key assignments |
| SECRET-004 | Bearer/JWT tokens | MEDIUM | Token patterns |
| SECRET-005 | High-entropy strings | MEDIUM | Possible secrets (entropy heuristic) |

### Policy Rules

| Rule ID | Pattern | Severity | Description |
|---------|---------|----------|-------------|
| POLICY-001 | Non-allowlisted shell commands | MEDIUM | Shell script policy violation |
| POLICY-002 | Non-allowlisted CI commands | MEDIUM | CI YAML policy violation |
| POLICY-003 | Unrecognized commands | LOW | Unknown command in script |
| POLICY-004 | (pass) | - | Allowlisted commands pass |

## Adding New Rules

1. Open `repo_concierge/rules.py`
2. Add a new rule entry to the rules registry:

```python
Rule(
    id="CUSTOM-001",
    name="My Custom Rule",
    pattern=r"your_regex_pattern",
    severity="HIGH",  # HIGH, MEDIUM, or LOW
    description="What this rule detects",
    recommendation="How to fix the issue",
    file_globs=["*.py", "*.sh"],  # Optional: limit to specific file types
)
```

3. The scanner will automatically pick up the new rule on the next scan.

## Architecture

```
repo_concierge/
  __init__.py      - Package init with version
  __main__.py      - Entry point (python -m repo_concierge)
  cli.py           - CLI argument parsing (argparse) and wiring
  scanner.py       - File discovery + pattern matching engine
  rules.py         - Rule definitions and central registry
  reporting.py     - Markdown and JSON report generators
  models.py        - Data classes (Rule, Finding, ScanResult)
config/
  command_allowlist.yaml - Default command allowlist
reports/
  .gitkeep         - Output directory for generated reports
tests/
  test_scanner.py  - Scanner unit tests
  test_rules.py    - Rule detection tests
  test_reporting.py - Report generation tests
  test_cli.py      - CLI integration tests
  fixtures/        - Test fixtures with known patterns
```

## Development

```bash
# Run tests
pytest

# Run tests with verbose output
pytest -v

# Run a specific test file
pytest tests/test_rules.py
```

## License

MIT
