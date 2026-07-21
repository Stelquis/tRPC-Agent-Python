# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Diff and input parser for the code review agent.

Supports three input modes:
1. --diff-file: Parse a unified diff file.
2. --repo-path: Detect changes in a git workspace (git diff).
3. --fixture: Load a test fixture from the fixtures/ directory.

Output: a list of ChangedFile objects, each containing hunks with line numbers.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────


@dataclass
class Hunk:
    """A single hunk block from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str  # e.g. "@@ -1,5 +1,6 @@"
    lines: list[str]  # original diff lines including +/-/space prefix
    added_lines: list[int] = field(default_factory=list)  # line numbers of added lines (in new file)
    removed_lines: list[int] = field(default_factory=list)  # line numbers of removed lines (in old file)

    def __post_init__(self) -> None:
        """Compute added and removed line numbers."""
        old_ln = self.old_start
        new_ln = self.new_start
        for line in self.lines:
            if line.startswith("+"):
                self.added_lines.append(new_ln)
                new_ln += 1
            elif line.startswith("-"):
                self.removed_lines.append(old_ln)
                old_ln += 1
            elif line.startswith(" "):
                old_ln += 1
                new_ln += 1
            # Skip \ No newline at end of file


@dataclass
class ChangedFile:
    """A file changed in the diff."""

    old_path: str
    new_path: str
    status: str = "modified"  # added, deleted, modified, renamed
    hunks: list[Hunk] = field(default_factory=list)


@dataclass
class DiffResult:
    """Complete parsed diff result."""

    files: list[ChangedFile] = field(default_factory=list)
    raw_diff: str = ""


# ──────────────────────────────────────────────
# Unified diff parser
# ──────────────────────────────────────────────

# Regex patterns for unified diff headers
RE_FILE_HEADER = re.compile(r"^--- (.+?)(?:\t.*)?$")
RE_FILE_HEADER2 = re.compile(r"^\+\+\+ (.+?)(?:\t.*)?$")
RE_HUNK_HEADER = re.compile(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@(.*)$")


def parse_unified_diff(diff_text: str) -> DiffResult:
    """Parse a unified diff string into structured DiffResult."""
    result = DiffResult(raw_diff=diff_text)
    lines = diff_text.splitlines(keepends=True)

    current_file: Optional[ChangedFile] = None
    current_hunk: Optional[Hunk] = None
    hunk_lines: list[str] = []
    in_hunk = False

    for line in lines:
        # Check for file header: --- a/file.py
        file_match = RE_FILE_HEADER.match(line)
        if file_match:
            # Save previous file/hunk
            _finalize_hunk(current_hunk, hunk_lines, current_file, result)
            current_file = ChangedFile(old_path=_normalize_path(file_match.group(1)))
            in_hunk = False
            continue

        # Check for file header: +++ b/file.py
        file_match2 = RE_FILE_HEADER2.match(line)
        if file_match2 and current_file is not None:
            current_file.new_path = _normalize_path(file_match2.group(1))
            continue

        # Check for hunk header: @@ -1,5 +1,6 @@
        hunk_match = RE_HUNK_HEADER.match(line)
        if hunk_match:
            _finalize_hunk(current_hunk, hunk_lines, current_file, result)
            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1
            current_hunk = Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                header=line.rstrip(),
                lines=[],
            )
            hunk_lines = []
            in_hunk = True
            continue

        # Regular diff line (starts with +, -, space, or \)
        if in_hunk and current_hunk is not None:
            hunk_lines.append(line)

    # Finalize last hunk and file
    _finalize_hunk(current_hunk, hunk_lines, current_file, result)

    return result


def _finalize_hunk(
    hunk: Optional[Hunk],
    hunk_lines: list[str],
    file: Optional[ChangedFile],
    result: DiffResult,
) -> None:
    """Flush the current hunk into the current file."""
    if hunk is not None and file is not None:
        hunk.lines = hunk_lines[:]
        hunk.__post_init__()
        file.hunks.append(hunk)
    # If the file is complete and non-empty, add it to results
    if file is not None and file.old_path and file.new_path:
        # Check if this file is already in the result
        if not any(f.old_path == file.old_path and f.new_path == file.new_path for f in result.files):
            result.files.append(file)


def _normalize_path(path: str) -> str:
    """Normalize a diff file path by removing a/ or b/ prefix."""
    path = path.strip()
    # Handle /dev/null (new/deleted file)
    if path == "/dev/null":
        return path
    # Remove a/ or b/ prefix used in git diff
    if len(path) > 2 and path[1] == "/" and path[0] in ("a", "b"):
        return path[2:]
    return path


# ──────────────────────────────────────────────
# Git workspace detection
# ──────────────────────────────────────────────


def get_git_diff(repo_path: str, staged: bool = False) -> DiffResult:
    """Run git diff on a repository and return parsed result.

    Args:
        repo_path: Path to the git repository.
        staged: If True, run git diff --staged (cached changes).

    Returns:
        Parsed DiffResult.
    """
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
        return parse_unified_diff(result.stdout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("git diff timed out after 30s")
    except FileNotFoundError:
        raise RuntimeError(f"Not a git repository: {repo_path}")


def get_changed_files_list(repo_path: str) -> list[str]:
    """Get list of changed files in a git workspace (unstaged + staged)."""
    cmd = ["git", "diff", "--name-only"]
    try:
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=30)
        files = result.stdout.strip().splitlines() if result.stdout.strip() else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    # Also get staged files
    try:
        cmd_staged = ["git", "diff", "--staged", "--name-only"]
        result_staged = subprocess.run(cmd_staged, cwd=repo_path, capture_output=True, text=True, timeout=30)
        staged_files = result_staged.stdout.strip().splitlines() if result_staged.stdout.strip() else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        staged_files = []

    # Deduplicate while preserving order
    seen = set()
    all_files = []
    for f in files + staged_files:
        if f not in seen:
            seen.add(f)
            all_files.append(f)
    return all_files


# ──────────────────────────────────────────────
# Fixture loading
# ──────────────────────────────────────────────


def load_fixture(fixture_name: str, fixtures_dir: Optional[str] = None) -> DiffResult:
    """Load a test fixture diff file.

    Args:
        fixture_name: Name of the fixture (e.g. "01_clean" or "01_clean.py.diff").
        fixtures_dir: Path to fixtures directory. Defaults to
            ``examples/skills_code_review_agent/fixtures/`` relative to this file.

    Returns:
        Parsed DiffResult.
    """
    if fixtures_dir is None:
        fixtures_dir = str(Path(__file__).parent / "fixtures")

    # Normalize fixture name
    if not fixture_name.endswith(".diff"):
        fixture_name += ".py.diff"

    fixture_path = Path(fixtures_dir) / fixture_name
    if not fixture_path.exists():
        # Try without .py prefix
        alt_name = fixture_name.replace(".py.diff", ".diff")
        fixture_path = Path(fixtures_dir) / alt_name
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_name} in {fixtures_dir}")

    diff_text = fixture_path.read_text(encoding="utf-8")
    return parse_unified_diff(diff_text)


def list_available_fixtures(fixtures_dir: Optional[str] = None) -> list[str]:
    """List all available fixture diff files."""
    if fixtures_dir is None:
        fixtures_dir = str(Path(__file__).parent / "fixtures")
    fixtures_path = Path(fixtures_dir)
    if not fixtures_path.exists():
        return []
    return sorted([f.name for f in fixtures_path.glob("*.diff")])


# ──────────────────────────────────────────────
# Convenience: auto-detect input mode
# ──────────────────────────────────────────────


def load_input(
    diff_file: Optional[str] = None,
    repo_path: Optional[str] = None,
    fixture: Optional[str] = None,
    fixtures_dir: Optional[str] = None,
) -> DiffResult:
    """Load input from any supported source.

    Exactly one of diff_file, repo_path, or fixture must be provided.
    """
    sources = [bool(diff_file), bool(repo_path), bool(fixture)]
    if sum(sources) != 1:
        raise ValueError("Exactly one of diff_file, repo_path, or fixture must be provided")

    if diff_file:
        text = Path(diff_file).read_text(encoding="utf-8")
        return parse_unified_diff(text)
    elif repo_path:
        return get_git_diff(repo_path)
    elif fixture:
        return load_fixture(fixture, fixtures_dir)

    raise ValueError("No input source provided")