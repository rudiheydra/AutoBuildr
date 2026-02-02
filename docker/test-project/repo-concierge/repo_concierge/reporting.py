"""Markdown and JSON report generation for Repo Concierge."""

import json
import os
from typing import Dict, List

from repo_concierge.models import Finding, ScanResult


def _group_findings_by_severity(findings: List[Finding]) -> Dict[str, List[Finding]]:
    """Group findings by severity level.

    Args:
        findings: List of findings to group.

    Returns:
        Dictionary mapping severity to list of findings.
    """
    groups: Dict[str, List[Finding]] = {
        "HIGH": [],
        "MEDIUM": [],
        "LOW": [],
    }
    for finding in findings:
        groups.setdefault(finding.severity, []).append(finding)
    return groups


def _get_recommendations(findings: List[Finding]) -> Dict[str, str]:
    """Extract unique recommendations keyed by rule ID.

    Args:
        findings: List of findings.

    Returns:
        Dictionary mapping rule_id to recommendation text.
    """
    recs: Dict[str, str] = {}
    for finding in findings:
        if finding.rule_id not in recs:
            recs[finding.rule_id] = finding.recommendation
    return recs


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def write_markdown_report(result: ScanResult, output_path: str) -> None:
    """Write a Markdown security audit report.

    Args:
        result: The scan result to report on.
        output_path: Path to write the report to.
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    lines: List[str] = []

    # Title
    lines.append("# Security Audit Report\n")

    # Metadata
    lines.append("## Scan Metadata\n")
    lines.append(f"- **Timestamp:** {result.timestamp}")
    lines.append(f"- **Target Path:** {result.target_path}")
    lines.append(f"- **Files Scanned:** {result.files_scanned}")
    lines.append(f"- **Ignore Rules:** {', '.join(result.ignore_rules)}")
    lines.append("")

    # Summary
    lines.append("## Summary\n")
    lines.append(f"- **HIGH:** {result.high_count}")
    lines.append(f"- **MEDIUM:** {result.medium_count}")
    lines.append(f"- **LOW:** {result.low_count}")
    total = result.high_count + result.medium_count + result.low_count
    lines.append(f"- **Total Findings:** {total}")
    lines.append("")

    if not result.findings:
        lines.append("## No Issues Found\n")
        lines.append("No security issues were detected during this scan.")
        lines.append("")
    else:
        # Findings table
        lines.append("## Findings\n")
        lines.append("| Severity | Rule ID | Rule Name | File | Line | Snippet |")
        lines.append("|----------|---------|-----------|------|------|---------|")
        for finding in result.findings:
            # Escape pipe characters in snippet for markdown table
            snippet = finding.snippet.replace("|", "\\|")
            if len(snippet) > 80:
                snippet = snippet[:80] + "..."
            lines.append(
                f"| {finding.severity} | {finding.rule_id} | {finding.rule_name} | "
                f"{finding.file_path} | {finding.line_number} | `{snippet}` |"
            )
        lines.append("")

        # Grouped severity sections
        groups = _group_findings_by_severity(result.findings)
        for severity in ("HIGH", "MEDIUM", "LOW"):
            group = groups.get(severity, [])
            if group:
                lines.append(f"### {severity} Findings\n")
                for finding in group:
                    lines.append(f"- **{finding.rule_id}** ({finding.rule_name})")
                    lines.append(f"  - File: `{finding.file_path}`, Line: {finding.line_number}")
                    lines.append(f"  - Snippet: `{finding.snippet[:100]}`")
                    lines.append("")

        # Recommendations
        recs = _get_recommendations(result.findings)
        if recs:
            lines.append("## Recommendations\n")
            for rule_id, recommendation in sorted(recs.items()):
                lines.append(f"- **{rule_id}:** {recommendation}")
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def write_json_report(result: ScanResult, output_path: str) -> None:
    """Write a JSON security audit report.

    Args:
        result: The scan result to report on.
        output_path: Path to write the report to.
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    findings_list = []
    for finding in result.findings:
        findings_list.append({
            "rule_id": finding.rule_id,
            "rule_name": finding.rule_name,
            "severity": finding.severity,
            "file_path": finding.file_path,
            "line_number": finding.line_number,
            "snippet": finding.snippet,
            "recommendation": finding.recommendation,
        })

    # Group by severity
    groups = _group_findings_by_severity(result.findings)
    severity_groups = {}
    for severity in ("HIGH", "MEDIUM", "LOW"):
        group = groups.get(severity, [])
        severity_groups[severity] = [
            {
                "rule_id": f.rule_id,
                "rule_name": f.rule_name,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "snippet": f.snippet,
            }
            for f in group
        ]

    # Recommendations
    recs = _get_recommendations(result.findings)

    report = {
        "metadata": {
            "timestamp": result.timestamp,
            "target_path": result.target_path,
            "files_scanned": result.files_scanned,
            "ignore_rules": result.ignore_rules,
        },
        "summary": {
            "high": result.high_count,
            "medium": result.medium_count,
            "low": result.low_count,
            "total": result.high_count + result.medium_count + result.low_count,
        },
        "findings": findings_list,
        "severity_groups": severity_groups,
        "recommendations": recs,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
