"""Data classes for Rule, Finding, and ScanResult."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Rule:
    """A security scanning rule definition.

    Attributes:
        id: Unique rule identifier (e.g., SHELL-001, SECRET-002)
        name: Human-readable rule name
        pattern: Regex pattern for detection
        severity: HIGH, MEDIUM, or LOW
        description: What this rule detects
        recommendation: How to fix or mitigate
        file_globs: Optional file patterns this rule applies to
    """
    id: str
    name: str
    pattern: str
    severity: str
    description: str
    recommendation: str
    file_globs: Optional[List[str]] = None


@dataclass
class Finding:
    """A single finding detected during a scan.

    Attributes:
        rule_id: Reference to the rule that triggered
        rule_name: Human-readable rule name
        severity: HIGH, MEDIUM, or LOW
        file_path: Path to the file containing the finding
        line_number: Line number of the finding
        snippet: Code snippet showing the match
        recommendation: Fix suggestion
    """
    rule_id: str
    rule_name: str
    severity: str
    file_path: str
    line_number: int
    snippet: str
    recommendation: str


@dataclass
class ScanResult:
    """The result of a complete scan.

    Attributes:
        target_path: Scanned directory path
        timestamp: ISO 8601 scan timestamp
        files_scanned: Total files scanned
        ignore_rules: Ignore patterns used
        findings: All findings from the scan
        high_count: Count of HIGH severity findings
        medium_count: Count of MEDIUM severity findings
        low_count: Count of LOW severity findings
    """
    target_path: str
    timestamp: str
    files_scanned: int
    ignore_rules: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
