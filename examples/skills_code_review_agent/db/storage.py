# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Storage abstraction and SQLite implementation for the code review agent.

Provides:
- StorageABC: Abstract base class defining the storage interface.
- SqliteStorage: Concrete SQLite implementation.

The interface is designed to allow switching to other SQL backends
(PostgreSQL, MySQL, etc.) with minimal changes.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..models import (
    FilterIntercept,
    Finding,
    MonitorSummary,
    ReviewReport,
    ReviewTask,
    SandboxRun,
    ReviewStatus,
)


# ──────────────────────────────────────────────
# Abstract interface
# ──────────────────────────────────────────────


class StorageABC(ABC):
    """Abstract base class for review storage backends."""

    @abstractmethod
    def create_task(self, task: ReviewTask) -> ReviewTask:
        ...

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[ReviewTask]:
        ...

    @abstractmethod
    def update_task_status(
        self, task_id: str, status: ReviewStatus, error_message: Optional[str] = None
    ) -> None:
        ...

    @abstractmethod
    def add_finding(self, finding: Finding) -> Finding:
        ...

    @abstractmethod
    def get_findings(self, task_id: str) -> list[Finding]:
        ...

    @abstractmethod
    def add_sandbox_run(self, run: SandboxRun) -> SandboxRun:
        ...

    @abstractmethod
    def get_sandbox_runs(self, task_id: str) -> list[SandboxRun]:
        ...

    @abstractmethod
    def add_filter_intercept(self, intercept: FilterIntercept) -> FilterIntercept:
        ...

    @abstractmethod
    def get_filter_intercepts(self, task_id: str) -> list[FilterIntercept]:
        ...

    @abstractmethod
    def save_monitor_summary(self, summary: MonitorSummary) -> MonitorSummary:
        ...

    @abstractmethod
    def get_monitor_summary(self, task_id: str) -> Optional[MonitorSummary]:
        ...

    @abstractmethod
    def get_full_report(self, task_id: str) -> Optional[ReviewReport]:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


# ──────────────────────────────────────────────
# SQLite implementation
# ──────────────────────────────────────────────


class SqliteStorage(StorageABC):
    """SQLite-backed storage implementation.

    Thread-safe via per-operation connection from a single file path.
    """

    def __init__(self, db_path: str = "review.db"):
        self._db_path = str(Path(db_path).resolve())
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            # Fallback: inline schema (for packaged distribution)
            return
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript(schema_path.read_text())
                conn.commit()
            finally:
                conn.close()

    # ── Task ──

    def create_task(self, task: ReviewTask) -> ReviewTask:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO review_task
                       (id, status, input_type, input_summary, input_raw,
                        total_duration_ms, error_message, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.id, task.status.value, task.input_type,
                        task.input_summary, task.input_raw,
                        task.total_duration_ms, task.error_message,
                        task.created_at, task.updated_at,
                    ),
                )
                conn.commit()
                return task
            finally:
                conn.close()

    def get_task(self, task_id: str) -> Optional[ReviewTask]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM review_task WHERE id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    return None
                return ReviewTask(**dict(row))
            finally:
                conn.close()

    def update_task_status(
        self, task_id: str, status: ReviewStatus, error_message: Optional[str] = None
    ) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE review_task
                       SET status = ?, error_message = ?, updated_at = datetime('now')
                       WHERE id = ?""",
                    (status.value, error_message, task_id),
                )
                conn.commit()
            finally:
                conn.close()

    # ── Finding ──

    def add_finding(self, finding: Finding) -> Finding:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO finding
                       (id, task_id, severity, category, file, line, title,
                        evidence, recommendation, confidence, source, dedup_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        finding.id, finding.task_id, finding.severity.value,
                        finding.category.value, finding.file, finding.line,
                        finding.title, finding.evidence, finding.recommendation,
                        finding.confidence.value, finding.source,
                        finding.dedup_key, finding.created_at,
                    ),
                )
                conn.commit()
                return finding
            finally:
                conn.close()

    def get_findings(self, task_id: str) -> list[Finding]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM finding WHERE task_id = ? ORDER BY created_at",
                    (task_id,),
                ).fetchall()
                return [Finding(**dict(r)) for r in rows]
            finally:
                conn.close()

    # ── SandboxRun ──

    def add_sandbox_run(self, run: SandboxRun) -> SandboxRun:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO sandbox_run
                       (id, task_id, script_name, runtime, duration_ms, exit_code,
                        output_size_bytes, output_truncated, success, error_message,
                        started_at, ended_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run.id, run.task_id, run.script_name, run.runtime,
                        run.duration_ms, run.exit_code, run.output_size_bytes,
                        int(run.output_truncated), int(run.success),
                        run.error_message, run.started_at, run.ended_at,
                    ),
                )
                conn.commit()
                return run
            finally:
                conn.close()

    def get_sandbox_runs(self, task_id: str) -> list[SandboxRun]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM sandbox_run WHERE task_id = ? ORDER BY started_at",
                    (task_id,),
                ).fetchall()
                return [SandboxRun(**dict(r)) for r in rows]
            finally:
                conn.close()

    # ── FilterIntercept ──

    def add_filter_intercept(self, intercept: FilterIntercept) -> FilterIntercept:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO filter_intercept
                       (id, task_id, stage, rule, target, reason, action, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        intercept.id, intercept.task_id, intercept.stage,
                        intercept.rule, intercept.target, intercept.reason,
                        intercept.action.value, intercept.timestamp,
                    ),
                )
                conn.commit()
                return intercept
            finally:
                conn.close()

    def get_filter_intercepts(self, task_id: str) -> list[FilterIntercept]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM filter_intercept WHERE task_id = ? ORDER BY timestamp",
                    (task_id,),
                ).fetchall()
                return [FilterIntercept(**dict(r)) for r in rows]
            finally:
                conn.close()

    # ── MonitorSummary ──

    def save_monitor_summary(self, summary: MonitorSummary) -> MonitorSummary:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO monitor_summary
                       (id, task_id, total_duration_ms, sandbox_duration_ms,
                        tool_call_count, intercept_count, finding_count,
                        severity_distribution, exception_types, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        summary.id, summary.task_id, summary.total_duration_ms,
                        summary.sandbox_duration_ms, summary.tool_call_count,
                        summary.intercept_count, summary.finding_count,
                        summary.severity_distribution, summary.exception_types,
                        summary.created_at,
                    ),
                )
                conn.commit()
                return summary
            finally:
                conn.close()

    def get_monitor_summary(self, task_id: str) -> Optional[MonitorSummary]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM monitor_summary WHERE task_id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    return None
                return MonitorSummary(**dict(row))
            finally:
                conn.close()

    # ── Full report ──

    def get_full_report(self, task_id: str) -> Optional[ReviewReport]:
        task = self.get_task(task_id)
        if task is None:
            return None
        findings = self.get_findings(task_id)
        sandbox_runs = self.get_sandbox_runs(task_id)
        filter_intercepts = self.get_filter_intercepts(task_id)
        monitor = self.get_monitor_summary(task_id)

        # Separate findings by confidence
        high_conf = [f for f in findings if f.confidence.value == "high"]
        low_conf = [f for f in findings if f.confidence.value == "low"]
        medium_conf = [f for f in findings if f.confidence.value == "medium"]
        needs_review = low_conf
        warnings = [f for f in medium_conf if f.severity.value in ("warning", "info")]

        return ReviewReport(
            task=task,
            findings=high_conf + medium_conf,
            warnings=warnings,
            needs_human_review=needs_review,
            sandbox_runs=sandbox_runs,
            filter_intercepts=filter_intercepts,
            monitor=monitor,
        )

    def close(self) -> None:
        pass