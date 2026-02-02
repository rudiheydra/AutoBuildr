"""Rule definitions, severities, and recommendations for Repo Concierge."""

from typing import List

from repo_concierge.models import Rule


# =============================================================================
# Shell Pattern Detection Rules (SHELL-001 through SHELL-006)
# =============================================================================

SHELL_001 = Rule(
    id="SHELL-001",
    name="Dangerous rm -rf",
    pattern=r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--recursive\s+--force|-[a-zA-Z]*f[a-zA-Z]*r)\b",
    severity="HIGH",
    description="Detects rm -rf patterns which can cause irreversible data loss if misused.",
    recommendation="Use safer alternatives: move files to trash, add --interactive flag, or validate paths before deletion.",
    file_globs=["*.sh", "*.py", "*.js", "*.ts"],
)

SHELL_002 = Rule(
    id="SHELL-002",
    name="Sudo rm usage",
    pattern=r"\bsudo\s+rm\b",
    severity="HIGH",
    description="Detects sudo rm patterns which combine elevated privileges with file deletion.",
    recommendation="Avoid using sudo with rm. Use targeted file permissions or run as a non-root user with minimal access.",
    file_globs=["*.sh", "*.py", "*.js", "*.ts"],
)

SHELL_003 = Rule(
    id="SHELL-003",
    name="Curl pipe to shell",
    pattern=r"\bcurl\b[^|]*\|\s*(bash|sh|zsh)\b",
    severity="HIGH",
    description="Detects curl piped to bash/sh patterns which execute remote code without verification.",
    recommendation="Download scripts first, review them, then execute. Use checksums to verify integrity.",
    file_globs=["*.sh", "*.py", "*.js", "*.ts", "*.md"],
)

SHELL_004 = Rule(
    id="SHELL-004",
    name="Wget pipe to shell",
    pattern=r"\bwget\b[^|]*\|\s*(sh|bash|zsh)\b",
    severity="HIGH",
    description="Detects wget piped to sh/bash patterns which execute remote code without verification.",
    recommendation="Download scripts first, review them, then execute. Use checksums to verify integrity.",
    file_globs=["*.sh", "*.py", "*.js", "*.ts", "*.md"],
)

SHELL_005 = Rule(
    id="SHELL-005",
    name="Eval usage in shell",
    pattern=r"\beval\s*\(",
    severity="MEDIUM",
    description="Detects eval() usage which can execute arbitrary code and is a common injection vector.",
    recommendation="Avoid eval(). Use safer alternatives like ast.literal_eval() in Python or explicit parsing.",
    file_globs=["*.sh", "*.py", "*.js", "*.ts"],
)

SHELL_006 = Rule(
    id="SHELL-006",
    name="Backtick command substitution",
    pattern=r"`[^`]+`",
    severity="MEDIUM",
    description="Detects backtick command substitution in shell scripts which can be error-prone and hard to nest.",
    recommendation="Use $() syntax instead of backticks for command substitution. It is safer and easier to read.",
    file_globs=["*.sh"],
)


# =============================================================================
# Secret Detection Rules (SECRET-001 through SECRET-005)
# =============================================================================

SECRET_001 = Rule(
    id="SECRET-001",
    name="Private key block",
    pattern=r"-----BEGIN\s+(RSA\s+|DSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----",
    severity="HIGH",
    description="Detects BEGIN PRIVATE KEY blocks which indicate embedded private keys in source code.",
    recommendation="Remove private keys from source code. Use environment variables or a secrets manager instead.",
)

SECRET_002 = Rule(
    id="SECRET-002",
    name="AWS access key",
    pattern=r"\bAKIA[0-9A-Z]{16}\b",
    severity="HIGH",
    description="Detects AWS access key patterns (AKIA...) which can grant unauthorized AWS access.",
    recommendation="Remove AWS keys from source code. Use IAM roles, environment variables, or AWS Secrets Manager.",
)

SECRET_003 = Rule(
    id="SECRET-003",
    name="API key assignment",
    pattern=r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
    severity="MEDIUM",
    description="Detects API_KEY= or api_key= assignment patterns with inline credential values.",
    recommendation="Store API keys in environment variables or a .env file excluded from version control.",
)

SECRET_004 = Rule(
    id="SECRET-004",
    name="Token or bearer credential",
    pattern=r"(?i)(bearer\s+[a-zA-Z0-9\-_\.]{20,}|token\s*[=:]\s*['\"][a-zA-Z0-9\-_\.]{20,}['\"])",
    severity="MEDIUM",
    description="Detects common token formats including Bearer tokens and JWT-like strings.",
    recommendation="Store tokens in environment variables or a secrets manager. Never commit tokens to source code.",
)

SECRET_005 = Rule(
    id="SECRET-005",
    name="High-entropy string",
    pattern=r"['\"][A-Za-z0-9+/=]{40,}['\"]",
    severity="MEDIUM",
    description="Detects high-entropy strings that may be embedded secrets, keys, or encoded credentials.",
    recommendation="Review high-entropy strings. If they are secrets, move them to environment variables or a secrets manager.",
)


# =============================================================================
# Allowlist Policy Rules (POLICY-001 through POLICY-004)
# =============================================================================

POLICY_001 = Rule(
    id="POLICY-001",
    name="Non-allowlisted shell command",
    pattern=r"^\s*(?!#)(\w[\w\-]*)",
    severity="MEDIUM",
    description="Flags shell commands in .sh files that are not on the command allowlist.",
    recommendation="Add the command to config/command_allowlist.yaml if it is approved, or replace it with an allowed alternative.",
    file_globs=["*.sh"],
)

POLICY_002 = Rule(
    id="POLICY-002",
    name="Non-allowlisted CI command",
    pattern=r"^\s*-\s+(\w[\w\-]*)",
    severity="MEDIUM",
    description="Flags shell commands in CI YAML files that are not on the command allowlist.",
    recommendation="Add the command to config/command_allowlist.yaml if it is approved, or replace it with an allowed alternative.",
    file_globs=["*.yaml", "*.yml"],
)

POLICY_003 = Rule(
    id="POLICY-003",
    name="Unrecognized command in script",
    pattern=r"(?:^|\n)\s*(?!#)(\w[\w\-./]*)",
    severity="LOW",
    description="Flags unrecognized commands in scripts and configs using basic detection.",
    recommendation="Review the command and add to allowlist if appropriate, or document why it is necessary.",
    file_globs=["*.sh", "*.yaml", "*.yml", "*.toml"],
)

POLICY_004 = Rule(
    id="POLICY-004",
    name="Allowlisted command passes",
    pattern=r"",
    severity="LOW",
    description="Allowlisted commands pass without flagging. This is a pass-through rule for the allowlist policy.",
    recommendation="No action needed. This command is on the approved allowlist.",
    file_globs=["*.sh", "*.yaml", "*.yml"],
)


# =============================================================================
# Central Rule Registry
# =============================================================================

# All built-in rules collected in a single registry list.
# Adding a new rule = adding an entry to this list.
BUILT_IN_RULES: List[Rule] = [
    # Shell pattern detection rules
    SHELL_001,
    SHELL_002,
    SHELL_003,
    SHELL_004,
    SHELL_005,
    SHELL_006,
    # Secret detection rules
    SECRET_001,
    SECRET_002,
    SECRET_003,
    SECRET_004,
    SECRET_005,
    # Allowlist policy rules
    POLICY_001,
    POLICY_002,
    POLICY_003,
    POLICY_004,
]

# Quick lookup by rule ID
RULES_BY_ID = {rule.id: rule for rule in BUILT_IN_RULES}


def get_all_rules() -> List[Rule]:
    """Return a copy of all built-in rules."""
    return list(BUILT_IN_RULES)


def get_rule_by_id(rule_id: str) -> Rule:
    """Look up a rule by its ID.

    Args:
        rule_id: The unique rule identifier (e.g., 'SHELL-001').

    Returns:
        The matching Rule object.

    Raises:
        KeyError: If the rule_id is not found.
    """
    if rule_id not in RULES_BY_ID:
        raise KeyError(f"Unknown rule ID: {rule_id}")
    return RULES_BY_ID[rule_id]
