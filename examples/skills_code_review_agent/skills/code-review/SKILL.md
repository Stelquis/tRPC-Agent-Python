---
name: code-review
description: |
  Automated code review skill that analyzes git diffs, detects security
  risks, async errors, resource leaks, database transaction issues, and
  missing tests. Runs static analysis scripts in a sandboxed environment
  and produces structured findings with severity, evidence, and fix
  recommendations.
---

Overview

Perform automated code review on a git diff, PR patch, or local workspace
changes. The skill loads rule documents from `rules/`, executes analysis
scripts in an isolated workspace, and outputs structured findings.

The review pipeline:

1. Parse the input diff into changed files and hunks.
2. Load applicable rules from the skill's rules directory.
3. Run static analysis scripts in the sandbox (container / cube / local).
4. Collect findings, deduplicate, and produce a structured report.

Rules Coverage

- Security: hardcoded secrets, command injection, path traversal
- Async Errors: missing await, unhandled coroutines, missing try-finally
- Resource Leaks: unclosed file handles, network connections, sessions
- Database Transactions: unclosed connections, missing commit/rollback
- Test Missing: new functions without corresponding unit tests

Examples

1) Review a diff file

   Command:

   review-agent --diff-file /path/to/changes.diff

2) Review a git workspace

   Command:

   review-agent --repo-path /path/to/repo

3) Review using a test fixture

   Command:

   review-agent --fixture 01_clean

4) Dry-run mode (no sandbox execution, no LLM)

   Command:

   review-agent --fixture 01_clean --dry-run

Output Files

- review_report.json  — structured findings in JSON format
- review_report.md    — human-readable Markdown report