# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Finding deduplication and noise reduction for the code review agent.

Provides:
- Deduplicator: Removes duplicate findings (same file + same line + same category).
- ConfidenceGrader: Classifies findings by confidence level.
"""

from __future__ import annotations

from typing import Optional

from .models import Confidence, Finding, Severity


# ──────────────────────────────────────────────
# Confidence scoring helpers
# ──────────────────────────────────────────────

# Severity → numeric weight for tie-breaking
_SEVERITY_WEIGHT: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "warning": 1,
    "info": 0,
}

_CONFIDENCE_ORDER: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _finding_score(finding: Finding) -> int:
    """Compute a numeric score for a finding (higher = more important)."""
    sev = _SEVERITY_WEIGHT.get(finding.severity.value, 0)
    conf = _CONFIDENCE_ORDER.get(finding.confidence.value, 0)
    return sev * 10 + conf


# ──────────────────────────────────────────────
# 6.1 + 6.2: Deduplicator
# ──────────────────────────────────────────────


class Deduplicator:
    """Deduplicates findings and classifies them by confidence.

    Dedup rule: same file + same line + same category → keep only one (highest confidence).
    If confidence ties, keep the one with highest severity.
    """

    def deduplicate(self, findings: list[Finding]) -> list[Finding]:
        """Remove duplicate findings.

        Two findings are considered duplicates if they share the same
        ``file``, ``line``, and ``category``. Only the highest-scoring
        finding is retained.

        Args:
            findings: List of findings to deduplicate.

        Returns:
            Deduplicated list of findings.
        """
        if not findings:
            return []

        # Group by dedup key
        groups: dict[str, list[Finding]] = {}
        for f in findings:
            key = f"{f.file}:{f.line}:{f.category.value}"
            groups.setdefault(key, []).append(f)

        # Keep the best finding per group
        result: list[Finding] = []
        for key, group in groups.items():
            best = max(group, key=_finding_score)
            best.dedup_key = key
            result.append(best)

        return result

    def classify(
        self,
        findings: list[Finding],
        high_threshold: float = 0.7,
        warning_threshold: float = 0.5,
        review_threshold: float = 0.3,
    ) -> tuple[list[Finding], list[Finding], list[Finding]]:
        """Classify findings into three confidence tiers.

        The classification is based on the finding's ``confidence`` field:
        - ``high`` → ``findings`` (high-confidence findings)
        - ``medium`` → ``warnings`` (medium-confidence, needs attention)
        - ``low`` → ``needs_human_review`` (low-confidence, human must verify)

        Args:
            findings: Deduplicated findings.
            high_threshold: Unused (reserved for future numeric scoring).
            warning_threshold: Unused (reserved for future numeric scoring).
            review_threshold: Unused (reserved for future numeric scoring).

        Returns:
            Tuple of (high_confidence_findings, warnings, needs_human_review).
        """
        high_conf: list[Finding] = []
        warnings: list[Finding] = []
        needs_review: list[Finding] = []

        for f in findings:
            if f.confidence == Confidence.HIGH:
                high_conf.append(f)
            elif f.confidence == Confidence.MEDIUM:
                warnings.append(f)
            else:
                needs_review.append(f)

        return high_conf, warnings, needs_review

    def process(
        self,
        findings: list[Finding],
    ) -> tuple[list[Finding], list[Finding], list[Finding]]:
        """Full pipeline: deduplicate then classify.

        Args:
            findings: Raw findings from analysis.

        Returns:
            Tuple of (findings, warnings, needs_human_review).
        """
        deduped = self.deduplicate(findings)
        return self.classify(deduped)


# Convenience function
def process_findings(
    findings: list[Finding],
) -> tuple[list[Finding], list[Finding], list[Finding]]:
    """Deduplicate and classify findings in one call."""
    return Deduplicator().process(findings)