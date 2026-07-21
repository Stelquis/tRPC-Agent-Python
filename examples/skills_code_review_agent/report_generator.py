# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Report generator for the code review agent.

Produces structured JSON reports and human-readable Markdown reports
with the following required summary blocks:
1. Findings summary (total count + severity breakdown)
2. Severity statistics (count per severity level)
3. Human review items (low-confidence findings)
4. Filter intercept summary
5. Performance metrics (durations, tool calls, etc.)
6. Sandbox execution summary
7. Actionable fix recommendations
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .db.storage import StorageABC
from .models import FilterIntercept, Finding, MonitorSummary, ReviewReport, ReviewTask, SandboxRun


def _severity_count(findings: list[Finding]) -> dict[str, int]:
    """Count findings by severity level."""
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
    return counts


def _severity_summary(findings: list[Finding], warnings: list[Finding]) -> str:
    """Build a severity summary string."""
    all_f = findings + warnings
    if not all_f:
        return "No issues found."
    total = len(all_f)
    sev = _severity_count(all_f)
    parts = [f"**Total: {total}**"]
    for level in ("critical", "high", "medium", "low", "warning", "info"):
        if sev.get(level, 0) > 0:
            parts.append(f"{level}: {sev[level]}")
    return ", ".join(parts)


def _filter_summary(intercepts: list[FilterIntercept]) -> str:
    """Build filter intercept summary."""
    if not intercepts:
        return "No filter intercepts triggered."
    denied = [i for i in intercepts if i.action.value == "deny"]
    review = [i for i in intercepts if i.action.value == "needs_human_review"]
    parts = [f"Total intercepts: {len(intercepts)}"]
    if denied:
        parts.append(f"Denied: {len(denied)}")
    if review:
        parts.append(f"Needs review: {len(review)}")
    return ", ".join(parts)


def _sandbox_summary(runs: list[SandboxRun]) -> str:
    """Build sandbox execution summary."""
    if not runs:
        return "No sandbox executions performed."
    total = len(runs)
    successful = sum(1 for r in runs if r.success)
    failed = total - successful
    total_duration = sum((r.duration_ms or 0) for r in runs)
    parts = [
        f"Executions: {total}",
        f"Successful: {successful}",
        f"Failed: {failed}",
        f"Total duration: {total_duration:.0f}ms",
    ]
    return ", ".join(parts)


def _recommendations(findings: list[Finding]) -> list[str]:
    """Extract actionable fix recommendations from findings."""
    seen = set()
    recs = []
    for f in findings:
        if f.recommendation and f.recommendation not in seen:
            seen.add(f.recommendation)
            recs.append(f.recommendation)
    return recs[:10]  # Top 10 unique recommendations


# ──────────────────────────────────────────────
# JSON report
# ──────────────────────────────────────────────


def generate_json_report(
    task: ReviewTask,
    findings: list[Finding],
    warnings: list[Finding],
    needs_human_review: list[Finding],
    sandbox_runs: list[SandboxRun],
    filter_intercepts: list[FilterIntercept],
    monitor: Optional[MonitorSummary] = None,
) -> dict:
    """Generate a structured JSON report.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    report = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat(),
            "report_version": "1.0",
        },
        "task": {
            "id": task.id,
            "status": task.status.value,
            "input_type": task.input_type,
            "input_summary": task.input_summary,
            "created_at": task.created_at,
            "total_duration_ms": task.total_duration_ms,
            "error_message": task.error_message,
        },
        "summary": {
            "total_findings": len(findings),
            "total_warnings": len(warnings),
            "total_needs_human_review": len(needs_human_review),
            "severity_distribution": _severity_count(findings + warnings),
            "filter_intercept_count": len(filter_intercepts),
            "sandbox_execution_count": len(sandbox_runs),
        },
        "findings": [f.model_dump() for f in findings],
        "warnings": [f.model_dump() for f in warnings],
        "needs_human_review": [f.model_dump() for f in needs_human_review],
        "filter_intercepts": [i.model_dump() for i in filter_intercepts],
        "sandbox_runs": [
            {
                "id": r.id,
                "script_name": r.script_name,
                "runtime": r.runtime,
                "duration_ms": r.duration_ms,
                "exit_code": r.exit_code,
                "success": r.success,
                "error_message": r.error_message,
                "output_truncated": r.output_truncated,
            }
            for r in sandbox_runs
        ],
        "recommendations": _recommendations(findings),
    }

    if monitor:
        report["monitoring"] = {
            "total_duration_ms": monitor.total_duration_ms,
            "sandbox_duration_ms": monitor.sandbox_duration_ms,
            "tool_call_count": monitor.tool_call_count,
            "intercept_count": monitor.intercept_count,
            "finding_count": monitor.finding_count,
            "severity_distribution": monitor.severity_distribution,
            "exception_types": monitor.exception_types,
        }

    return report


# ──────────────────────────────────────────────
# Markdown report
# ──────────────────────────────────────────────


def generate_markdown_report(
    task: ReviewTask,
    findings: list[Finding],
    warnings: list[Finding],
    needs_human_review: list[Finding],
    sandbox_runs: list[SandboxRun],
    filter_intercepts: list[FilterIntercept],
    monitor: Optional[MonitorSummary] = None,
) -> str:
    """Generate a human-readable Markdown report.

    The report includes all 7 required summary blocks:
    1. Findings summary
    2. Severity statistics
    3. Human review items
    4. Filter intercept summary
    5. Performance metrics
    6. Sandbox execution summary
    7. Actionable fix recommendations
    """
    lines = []
    lines.append("# Code Review Report")
    lines.append("")
    lines.append(f"**Task**: `{task.id}`")
    lines.append(f"**Status**: {task.status.value}")
    lines.append(f"**Input**: {task.input_type} — {task.input_summary}")
    lines.append(f"**Created**: {task.created_at}")
    if task.total_duration_ms:
        lines.append(f"**Duration**: {task.total_duration_ms:.0f}ms")
    if task.error_message:
        lines.append(f"**Error**: {task.error_message}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Block 1 + 2: Findings Summary & Severity Statistics ──
    lines.append("## Findings Summary")
    lines.append("")
    lines.append(_severity_summary(findings, warnings))
    lines.append("")

    # ── Block 3: Human Review Items ──
    lines.append("## Items Requiring Human Review")
    lines.append("")
    if needs_human_review:
        for f in needs_human_review:
            lines.append(f"- **[{f.severity.value}]** {f.file}:{f.line} — {f.title}")
            lines.append(f"  - Evidence: `{f.evidence[:200]}`")
            lines.append(f"  - Suggestion: {f.recommendation}")
            lines.append("")
    else:
        lines.append("No items require human review.")
        lines.append("")

    # ── Detailed Findings ──
    lines.append("## Detailed Findings")
    lines.append("")
    if findings:
        for f in findings:
            lines.append(f"### [{f.severity.upper()}] {f.category.value}: {f.title}")
            lines.append(f"")
            lines.append(f"- **File**: `{f.file}` (line {f.line})")
            lines.append(f"- **Confidence**: {f.confidence.value}")
            lines.append(f"- **Source**: {f.source}")
            lines.append(f"- **Evidence**:")
            lines.append(f"```")
            lines.append(f"{f.evidence[:300]}")
            lines.append(f"```")
            lines.append(f"- **Recommendation**: {f.recommendation}")
            lines.append("")
    else:
        lines.append("No high-confidence findings.")
        lines.append("")

    # ── Warnings ──
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for f in warnings:
            lines.append(f"- **[{f.severity.value}]** {f.file}:{f.line} — {f.title}")
            lines.append(f"  - {f.recommendation}")
        lines.append("")

    # ── Block 4: Filter Intercept Summary ──
    lines.append("## Filter Intercept Summary")
    lines.append("")
    lines.append(_filter_summary(filter_intercepts))
    lines.append("")
    if filter_intercepts:
        lines.append("| Stage | Rule | Action | Reason |")
        lines.append("|-------|------|--------|--------|")
        for i in filter_intercepts:
            lines.append(f"| {i.stage} | {i.rule} | {i.action.value} | {i.reason} |")
        lines.append("")

    # ── Block 6: Sandbox Execution Summary ──
    lines.append("## Sandbox Execution Summary")
    lines.append("")
    lines.append(_sandbox_summary(sandbox_runs))
    lines.append("")
    if sandbox_runs:
        lines.append("| Script | Runtime | Duration | Success |")
        lines.append("|--------|---------|----------|---------|")
        for r in sandbox_runs:
            status = "✅" if r.success else "❌"
            dur = f"{r.duration_ms:.0f}ms" if r.duration_ms else "N/A"
            lines.append(f"| {r.script_name} | {r.runtime} | {dur} | {status} |")
        lines.append("")

    # ── Block 5: Performance Metrics ──
    lines.append("## Performance Metrics")
    lines.append("")
    if monitor:
        lines.append(f"- **Total duration**: {monitor.total_duration_ms:.0f}ms")
        lines.append(f"- **Sandbox duration**: {monitor.sandbox_duration_ms:.0f}ms")
        lines.append(f"- **Tool calls**: {monitor.tool_call_count}")
        lines.append(f"- **Filter intercepts**: {monitor.intercept_count}")
        lines.append(f"- **Findings**: {monitor.finding_count}")
    else:
        lines.append("Monitoring data not available.")
    lines.append("")

    # ── Block 7: Actionable Fix Recommendations ──
    lines.append("## Fix Recommendations")
    lines.append("")
    recs = _recommendations(findings + warnings)
    if recs:
        for i, rec in enumerate(recs, 1):
            lines.append(f"{i}. {rec}")
    else:
        lines.append("No recommendations available.")
    lines.append("")

    lines.append("---")
    lines.append(f"*Report generated at {datetime.utcnow().isoformat()}*")
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Report writer
# ──────────────────────────────────────────────


def write_reports(
    report: ReviewReport,
    output_dir: str = ".",
    json_path: Optional[str] = None,
    md_path: Optional[str] = None,
) -> tuple[str, str]:
    """Write JSON and Markdown reports to disk.

    Args:
        report: The ReviewReport to write.
        output_dir: Directory for output files (default: current dir).
        json_path: Override JSON output path.
        md_path: Override Markdown output path.

    Returns:
        Tuple of (json_path, md_path) of the written files.
    """
    json_data = generate_json_report(
        task=report.task,
        findings=report.findings,
        warnings=report.warnings,
        needs_human_review=report.needs_human_review,
        sandbox_runs=report.sandbox_runs,
        filter_intercepts=report.filter_intercepts,
        monitor=report.monitor,
    )

    md_content = generate_markdown_report(
        task=report.task,
        findings=report.findings,
        warnings=report.warnings,
        needs_human_review=report.needs_human_review,
        sandbox_runs=report.sandbox_runs,
        filter_intercepts=report.filter_intercepts,
        monitor=report.monitor,
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_out = Path(json_path) if json_path else output_path / "review_report.json"
    md_out = Path(md_path) if md_path else output_path / "review_report.md"

    json_out.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    md_out.write_text(md_content, encoding="utf-8")

    return str(json_out), str(md_out)


def build_report_from_db(
    storage: StorageABC,
    task_id: str,
    findings: Optional[list[Finding]] = None,
    warnings: Optional[list[Finding]] = None,
    needs_human_review: Optional[list[Finding]] = None,
) -> Optional[ReviewReport]:
    """Build a ReviewReport by loading data from the database.

    Args:
        storage: Storage backend.
        task_id: Review task ID.
        findings: Optional pre-classified findings (if None, load from DB).
        warnings: Optional pre-classified warnings.
        needs_human_review: Optional pre-classified human review items.

    Returns:
        ReviewReport or None if task not found.
    """
    return storage.get_full_report(task_id)