# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Sensitive information masking for the code review agent.

Detects and masks sensitive patterns (API keys, tokens, passwords, private keys)
in code review outputs, reports, and database records to prevent credential leakage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# Sensitive patterns
# ──────────────────────────────────────────────

# Each pattern has: name, regex, replacement, and severity
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern, str, str]] = [
    # OpenAI / Anthropic / generic API keys
    ("api_key_sk", re.compile(r'sk-[A-Za-z0-9]{20,}'), "sk-***", "high"),
    ("api_key_pk", re.compile(r'pk-[A-Za-z0-9]{20,}'), "pk-***", "high"),
    # GitHub tokens
    ("github_token", re.compile(r'ghp_[A-Za-z0-9]{36,}'), "ghp-***", "high"),
    ("github_old_token", re.compile(r'gho_[A-Za-z0-9]{36,}'), "gho-***", "high"),
    ("github_app_token", re.compile(r'ghu_[A-Za-z0-9]{36,}'), "ghu-***", "high"),
    # AWS access keys
    ("aws_access_key", re.compile(r'AKIA[0-9A-Z]{16}'), "AKIA***", "high"),
    ("aws_secret_key", re.compile(r'(?i)aws_secret_access_key\s*[=:]\s*["\'][A-Za-z0-9/+=]{40}["\']'), "aws_secret_access_key=***", "high"),
    # Generic password / secret assignments
    ("password", re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{4,}["\']'), r'\1 = "***"', "high"),
    ("secret", re.compile(r'(?i)(secret|token|api_key|apikey)\s*[=:]\s*["\'][^"\']{4,}["\']'), r'\1 = "***"', "high"),
    # Private keys
    ("private_key", re.compile(r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----'), "-----BEGIN PRIVATE KEY-----\n***\n-----END PRIVATE KEY-----", "critical"),
    # JWT tokens
    ("jwt_token", re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'), "eyJ***.***.***", "high"),
    # Connection strings with credentials
    ("db_connection_string", re.compile(r'(?i)(mysql|postgres|mongodb|redis)://[^:]+:[^@]+@'), r'\1://***:***@', "high"),
]


@dataclass
class MaskingResult:
    """Result of masking operation."""

    masked_text: str
    findings: list[dict] = field(default_factory=list)
    mask_count: int = 0


# ──────────────────────────────────────────────
# Masking functions
# ──────────────────────────────────────────────


def mask_sensitive(text: str, replacements: Optional[dict[str, str]] = None) -> MaskingResult:
    """Mask all known sensitive patterns in the text.

    Args:
        text: The text to scan and mask.
        replacements: Optional custom replacement overrides by pattern name.

    Returns:
        MaskingResult with masked text and list of findings.
    """
    result = MaskingResult(masked_text=text)
    replacements = replacements or {}

    for name, pattern, default_replacement, severity in SENSITIVE_PATTERNS:
        replacement = replacements.get(name, default_replacement)

        for match in pattern.finditer(text):
            line_num = text[:match.start()].count("\n") + 1
            result.findings.append({
                "pattern": name,
                "severity": severity,
                "line": line_num,
                "matched": match.group()[:20] + "..." if len(match.group()) > 20 else match.group(),
            })
            result.mask_count += 1

        result.masked_text = pattern.sub(replacement, result.masked_text)

    return result


def mask_finding(finding_text: str) -> str:
    """Mask sensitive data in a single finding's evidence or recommendation text."""
    return mask_sensitive(finding_text).masked_text


def mask_report(report: dict) -> dict:
    """Mask sensitive data in a review report dictionary in-place.

    Scans and masks the following fields:
    - task.input_raw
    - finding.evidence
    - finding.recommendation
    - finding.title
    """
    # Mask task input
    if "task" in report and isinstance(report["task"], dict):
        if "input_raw" in report["task"]:
            masked = mask_sensitive(report["task"]["input_raw"])
            report["task"]["input_raw"] = masked.masked_text

    # Mask findings
    for finding_key in ("findings", "warnings", "needs_human_review"):
        for finding in report.get(finding_key, []):
            for field_name in ("evidence", "recommendation", "title"):
                if field_name in finding and isinstance(finding[field_name], str):
                    finding[field_name] = mask_sensitive(finding[field_name]).masked_text

    return report


def is_clean(text: str) -> bool:
    """Check if text has no unmasked sensitive patterns.

    Returns True if the text is clean (no sensitive data found).
    """
    result = mask_sensitive(text)
    return result.mask_count == 0