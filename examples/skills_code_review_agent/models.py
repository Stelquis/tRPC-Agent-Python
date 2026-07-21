# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Core data models for the code review agent.

Defines the structured data types used throughout the review pipeline:
input parsing, sandbox execution, findings, database storage, and reporting.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class Severity(str, Enum):
    """Severity level of a finding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(str, Enum):
    """Category of code issue."""

    SECURITY = "security"
    ASYNC_ERROR = "async_error"
    RESOURCE_LEAK = "resource_leak"
    DB_TRANSACTION = "db_transaction"
    TEST_MISSING = "test_missing"
    SECRET_LEAK = "secret_leak"
    STYLE = "style"
    PERFORMANCE = "performance"
    OTHER = "other"


class ReviewStatus(str, Enum):
    """Status of a review task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class FilterAction(str, Enum):
    """Action taken by a filter."""

    DENY = "deny"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    PASS = "pass"


class Confidence(str, Enum):
    """Confidence level of a finding."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────


class Finding(BaseModel):
    """A single code review finding."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    severity: Severity
    category: FindingCategory
    file: str
    line: int
    title: str
    evidence: str
    recommendation: str
    confidence: Confidence
    source: str = "rule"  # rule, static_analysis, sandbox, llm
    dedup_key: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ReviewTask(BaseModel):
    """A code review task."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ReviewStatus = ReviewStatus.PENDING
    input_type: str  # diff_file, repo_path, fixture
    input_summary: str
    input_raw: str
    total_duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SandboxRun(BaseModel):
    """Record of a single sandbox execution."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    script_name: str
    runtime: str  # container, cube, local
    duration_ms: Optional[float] = None
    exit_code: Optional[int] = None
    output_size_bytes: Optional[int] = None
    output_truncated: bool = False
    success: bool = False
    error_message: Optional[str] = None
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    ended_at: Optional[str] = None


class FilterIntercept(BaseModel):
    """Record of a filter governance interception."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    stage: str  # script, path, network, budget
    rule: str
    target: str
    reason: str
    action: FilterAction
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class MonitorSummary(BaseModel):
    """Monitoring and audit summary for a review task."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    total_duration_ms: float = 0.0
    sandbox_duration_ms: float = 0.0
    tool_call_count: int = 0
    intercept_count: int = 0
    finding_count: int = 0
    severity_distribution: str = "{}"  # JSON string
    exception_types: str = "[]"  # JSON string
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ReviewReport(BaseModel):
    """Complete review report output."""

    task: ReviewTask
    findings: list[Finding] = []
    warnings: list[Finding] = []
    needs_human_review: list[Finding] = []
    sandbox_runs: list[SandboxRun] = []
    filter_intercepts: list[FilterIntercept] = []
    monitor: Optional[MonitorSummary] = None
    report_path_json: Optional[str] = None
    report_path_md: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())