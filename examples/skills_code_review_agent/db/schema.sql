-- Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
--
-- Copyright (C) 2026 Tencent. All rights reserved.
--
-- tRPC-Agent-Python is licensed under Apache-2.0.
-- ============================================================================
-- Code Review Agent — Database Schema
-- ============================================================================
-- Default backend: SQLite
-- The interface (StorageABC) is designed to allow switching to other SQL
-- backends (PostgreSQL, MySQL, etc.) with minimal changes.
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- 1. review_task — 每个审查任务一条记录
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_task (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'partial')),
    input_type      TEXT NOT NULL,
    input_summary   TEXT NOT NULL,
    input_raw       TEXT NOT NULL,
    total_duration_ms REAL,
    error_message   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_task_status ON review_task(status);
CREATE INDEX IF NOT EXISTS idx_review_task_created_at ON review_task(created_at);

-- ────────────────────────────────────────────────────────────────────────────
-- 2. sandbox_run — 每次沙箱执行一条记录
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sandbox_run (
    id                TEXT PRIMARY KEY,
    task_id           TEXT NOT NULL,
    script_name       TEXT NOT NULL,
    runtime           TEXT NOT NULL,
    duration_ms       REAL,
    exit_code         INTEGER,
    output_size_bytes INTEGER,
    output_truncated  INTEGER NOT NULL DEFAULT 0,
    success           INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    FOREIGN KEY (task_id) REFERENCES review_task(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sandbox_run_task_id ON sandbox_run(task_id);

-- ────────────────────────────────────────────────────────────────────────────
-- 3. finding — 每条审查发现一条记录
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS finding (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,
    severity        TEXT NOT NULL
                    CHECK (severity IN ('critical', 'high', 'medium', 'low', 'warning', 'info')),
    category        TEXT NOT NULL,
    file            TEXT NOT NULL,
    line            INTEGER NOT NULL,
    title           TEXT NOT NULL,
    evidence        TEXT NOT NULL,
    recommendation  TEXT NOT NULL,
    confidence      TEXT NOT NULL
                    CHECK (confidence IN ('high', 'medium', 'low')),
    source          TEXT NOT NULL DEFAULT 'rule',
    dedup_key       TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES review_task(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_finding_task_id ON finding(task_id);
CREATE INDEX IF NOT EXISTS idx_finding_severity ON finding(severity);
CREATE INDEX IF NOT EXISTS idx_finding_dedup ON finding(task_id, file, line, category);

-- ────────────────────────────────────────────────────────────────────────────
-- 4. filter_intercept — Filter 拦截记录
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS filter_intercept (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    stage       TEXT NOT NULL,
    rule        TEXT NOT NULL,
    target      TEXT NOT NULL,
    reason      TEXT NOT NULL,
    action      TEXT NOT NULL
                CHECK (action IN ('deny', 'needs_human_review', 'pass')),
    timestamp   TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES review_task(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_filter_intercept_task_id ON filter_intercept(task_id);

-- ────────────────────────────────────────────────────────────────────────────
-- 5. monitor_summary — 监控审计摘要
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monitor_summary (
    id                  TEXT PRIMARY KEY,
    task_id             TEXT NOT NULL UNIQUE,
    total_duration_ms   REAL NOT NULL DEFAULT 0,
    sandbox_duration_ms REAL NOT NULL DEFAULT 0,
    tool_call_count     INTEGER NOT NULL DEFAULT 0,
    intercept_count     INTEGER NOT NULL DEFAULT 0,
    finding_count       INTEGER NOT NULL DEFAULT 0,
    severity_distribution TEXT NOT NULL DEFAULT '{}',
    exception_types     TEXT NOT NULL DEFAULT '[]',
    created_at          TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES review_task(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_monitor_summary_task_id ON monitor_summary(task_id);