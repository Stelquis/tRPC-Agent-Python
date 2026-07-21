# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Filter governance layer for the code review agent.

Provides a chain of filters that intercept high-risk operations before
they reach the sandbox executor. Each filter implements a specific
security policy (script content, path safety, network access, budget).

The filter chain follows a deny → needs_human_review → pass decision model.
"""

from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Enums & data structures
# ──────────────────────────────────────────────


class FilterAction(str, Enum):
    """Action taken by a filter."""

    DENY = "deny"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    PASS = "pass"


@dataclass
class FilterDecision:
    """Result of a single filter evaluation."""

    action: FilterAction = FilterAction.PASS
    rule: str = ""
    target: str = ""
    reason: str = ""
    stage: str = ""


@dataclass
class FilterChainResult:
    """Result of the full filter chain evaluation."""

    decisions: list[FilterDecision] = field(default_factory=list)
    final_action: FilterAction = FilterAction.PASS

    @property
    def is_allowed(self) -> bool:
        """True if the request passes all filters."""
        return self.final_action == FilterAction.PASS

    @property
    def intercepts(self) -> list[FilterDecision]:
        """Get all non-pass decisions."""
        return [d for d in self.decisions if d.action != FilterAction.PASS]


# ──────────────────────────────────────────────
# Abstract base filter
# ──────────────────────────────────────────────


class BaseReviewFilter(ABC):
    """Abstract base class for a single filter in the chain."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterDecision:
        """Evaluate a command/request against this filter.

        Args:
            command: The shell command or script to evaluate.
            cwd: Current working directory.

        Returns:
            FilterDecision with action and reason.
        """
        ...


# ──────────────────────────────────────────────
# 5.1 High-Risk Script Filter
# ──────────────────────────────────────────────

# Blacklist patterns for dangerous shell commands
HIGH_RISK_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # Destructive file operations
    (re.compile(r'\brm\s+-rf\s+[/\*]'), "DANGEROUS_RM_RF", "Recursive force delete on root or wildcard"),
    (re.compile(r'\brm\s+-rf\s+/\s'), "DANGEROUS_RM_ROOT", "Recursive force delete on root directory"),
    (re.compile(r'\bmkfs\.'), "FORMAT_DISK", "Filesystem format command"),
    (re.compile(r'\bdd\s+if='), "DD_RAW_WRITE", "Direct disk write with dd"),
    (re.compile(r'\bchmod\s+-R\s+777\s+/'), "CHMOD_RECURSIVE_ROOT", "Recursive permission change on root"),
    # System modification
    (re.compile(r'\bpasswd\b'), "PASSWD_MODIFY", "Password modification command"),
    (re.compile(r'\bkill\s+-9\b'), "KILL_PROCESS", "Force kill process"),
    (re.compile(r'\bshutdown\b|\breboot\b|\binit\s+0\b|\binit\s+6\b'), "SYSTEM_SHUTDOWN", "System shutdown or reboot"),
    # Network scanning / attacks
    (re.compile(r'\bnmap\b'), "NETWORK_SCAN", "Network scanning tool"),
    (re.compile(r'\bnikto\b'), "WEB_SCANNER", "Web vulnerability scanner"),
    (re.compile(r'\bsqlmap\b'), "SQL_INJECTION_TOOL", "SQL injection automation tool"),
    # Crypto mining
    (re.compile(r'\bminerd\b|\bxmrig\b|\bcpuminer\b'), "CRYPTO_MINER", "Cryptocurrency miner"),
    # Data exfiltration
    (re.compile(r'\bcurl\s+--data\s+@/'), "DATA_EXFIL_CURL", "Potential data exfiltration via curl"),
    (re.compile(r'\bwget\s+--post-file\b'), "DATA_EXFIL_WGET", "Potential data exfiltration via wget"),
    # Dynamic code execution
    (re.compile(r'\beval\s+\$'), "EVAL_VARIABLE", "Dynamic eval of variable content"),
    (re.compile(r'\bexec\s+\$'), "EXEC_VARIABLE", "Dynamic exec of variable content"),
]


class HighRiskScriptFilter(BaseReviewFilter):
    """Filter that detects and blocks high-risk shell commands."""

    def __init__(self, patterns: Optional[list[tuple[re.Pattern, str, str]]] = None):
        super().__init__("HighRiskScriptFilter")
        self.patterns = patterns or HIGH_RISK_PATTERNS

    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterDecision:
        for pattern, rule_name, reason in self.patterns:
            if pattern.search(command):
                return FilterDecision(
                    action=FilterAction.DENY,
                    stage="script",
                    rule=rule_name,
                    target=command[:100] + "..." if len(command) > 100 else command,
                    reason=reason,
                )
        return FilterDecision(action=FilterAction.PASS)


# ──────────────────────────────────────────────
# 5.2 Path Safety Filter
# ──────────────────────────────────────────────

# System paths that should not be accessed
FORBIDDEN_PATHS = [
    re.compile(r'^/etc/'),
    re.compile(r'^/sys/'),
    re.compile(r'^/proc/'),
    re.compile(r'^/dev/'),
    re.compile(r'^/boot/'),
    re.compile(r'^/root/'),
    re.compile(r'^/var/log/'),
    re.compile(r'^/var/db/'),
    re.compile(r'^/usr/lib/'),
    re.compile(r'^/lib/'),
    re.compile(r'^/lib64/'),
    re.compile(r'^/bin/'),
    re.compile(r'^/sbin/'),
    re.compile(r'^/usr/bin/'),
    re.compile(r'^/usr/sbin/'),
]

# Commands that access file paths
PATH_COMMAND_PATTERN = re.compile(
    r'(?:^|\s)(?:cat|less|more|head|tail|vim|nano|echo\s+.*>|>>|cp|mv|rm|chmod|chown|ls|find|grep|sed|awk|read|write|open)\s+([^\s;|&]+)'
)


class PathSafetyFilter(BaseReviewFilter):
    """Filter that blocks access to forbidden system paths."""

    def __init__(self, extra_forbidden: Optional[list[str]] = None):
        super().__init__("PathSafetyFilter")
        self.forbidden_patterns = list(FORBIDDEN_PATHS)
        if extra_forbidden:
            for path in extra_forbidden:
                self.forbidden_patterns.append(re.compile(re.escape(path)))

    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterDecision:
        # Check if any path in the command matches forbidden patterns
        for match in PATH_COMMAND_PATTERN.finditer(command):
            target_path = match.group(1)
            # Resolve relative paths
            if target_path.startswith("./") and cwd:
                target_path = os.path.join(cwd, target_path)
            if target_path.startswith("~/"):
                target_path = os.path.expanduser(target_path)

            for forbidden in self.forbidden_patterns:
                if forbidden.search(target_path):
                    return FilterDecision(
                        action=FilterAction.DENY,
                        stage="path",
                        rule="FORBIDDEN_PATH",
                        target=target_path,
                        reason=f"Access to forbidden system path: {target_path}",
                    )

        return FilterDecision(action=FilterAction.PASS)


# ──────────────────────────────────────────────
# 5.3 Network Access Filter
# ──────────────────────────────────────────────

# Network-related commands
NETWORK_COMMANDS = re.compile(
    r'\b(?:curl|wget|nc|netcat|ncat|ssh|scp|sftp|ftp|telnet|ping|traceroute|dig|nslookup|host|iwgetid|iwconfig|ifconfig|ip\s+addr)\b'
)

# Commonly allowed hosts (whitelist)
DEFAULT_NETWORK_WHITELIST = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "pypi.org",
    "files.pythonhosted.org",
    "pypi.python.org",
    "github.com",
    "raw.githubusercontent.com",
]


class NetworkAccessFilter(BaseReviewFilter):
    """Filter that controls network access from the sandbox."""

    def __init__(self, whitelist: Optional[list[str]] = None, block_all: bool = True):
        super().__init__("NetworkAccessFilter")
        self.whitelist = set(whitelist or DEFAULT_NETWORK_WHITELIST)
        self.block_all = block_all

    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterDecision:
        if self.block_all:
            if NETWORK_COMMANDS.search(command):
                return FilterDecision(
                    action=FilterAction.DENY,
                    stage="network",
                    rule="NETWORK_BLOCKED",
                    target=command[:100],
                    reason="All network access is blocked in sandbox mode",
                )

        # Check for non-whitelisted network access
        for match in NETWORK_COMMANDS.finditer(command):
            # Extract the host from the command
            rest = command[match.end():].strip().split()[0] if command[match.end():].strip() else ""
            host = rest.split("/")[0] if rest else ""
            if host and host not in self.whitelist:
                return FilterDecision(
                    action=FilterAction.NEEDS_HUMAN_REVIEW,
                    stage="network",
                    rule="UNKNOWN_HOST",
                    target=host,
                    reason=f"Network access to non-whitelisted host: {host}",
                )

        return FilterDecision(action=FilterAction.PASS)


# ──────────────────────────────────────────────
# 5.4 Budget Filter
# ──────────────────────────────────────────────


class BudgetFilter(BaseReviewFilter):
    """Filter that enforces execution budget limits.

    Tracks the number of script executions and total time spent
    executing scripts within a single review session.
    """

    def __init__(
        self,
        max_executions: int = 10,
        max_total_time_ms: float = 60_000,  # 60 seconds
    ):
        super().__init__("BudgetFilter")
        self.max_executions = max_executions
        self.max_total_time_ms = max_total_time_ms
        self._execution_count = 0
        self._start_time: Optional[float] = None
        self._total_time_ms: float = 0.0

    def reset(self) -> None:
        """Reset the budget counters for a new review session."""
        self._execution_count = 0
        self._start_time = time.monotonic()
        self._total_time_ms = 0.0

    def record_execution(self, duration_ms: float) -> None:
        """Record a completed execution and its duration."""
        self._execution_count += 1
        self._total_time_ms += duration_ms

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def total_time_ms(self) -> float:
        return self._total_time_ms

    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterDecision:
        if self._start_time is None:
            self._start_time = time.monotonic()

        # Check execution count
        if self._execution_count >= self.max_executions:
            return FilterDecision(
                action=FilterAction.DENY,
                stage="budget",
                rule="MAX_EXECUTIONS_REACHED",
                target=f"count={self._execution_count}/{self.max_executions}",
                reason=f"Maximum execution count ({self.max_executions}) reached",
            )

        # Check total time (approximate, before execution)
        elapsed = (time.monotonic() - self._start_time) * 1000
        if elapsed + self._total_time_ms >= self.max_total_time_ms:
            return FilterDecision(
                action=FilterAction.DENY,
                stage="budget",
                rule="MAX_TIME_REACHED",
                target=f"time={elapsed:.0f}ms/{self.max_total_time_ms}ms",
                reason=f"Maximum total execution time ({self.max_total_time_ms}ms) exceeded",
            )

        return FilterDecision(action=FilterAction.PASS)


# ──────────────────────────────────────────────
# 5.5 Filter Chain
# ──────────────────────────────────────────────


class FilterChain:
    """Chain of filters that evaluates a command against all registered filters.

    The chain follows a strict ordering:
    DENY → NEEDS_HUMAN_REVIEW → PASS

    If any filter returns DENY, the chain stops immediately.
    """

    def __init__(self, filters: Optional[list[BaseReviewFilter]] = None):
        self.filters = filters or []

    def add_filter(self, filter_: BaseReviewFilter) -> None:
        """Add a filter to the chain."""
        self.filters.append(filter_)

    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterChainResult:
        """Evaluate a command against all filters in the chain.

        Returns:
            FilterChainResult with all decisions and the final action.
        """
        result = FilterChainResult()

        for filter_ in self.filters:
            decision = filter_.evaluate(command, cwd)
            result.decisions.append(decision)

            # DENY is final — stop the chain
            if decision.action == FilterAction.DENY:
                result.final_action = FilterAction.DENY
                return result

        # Check for NEEDS_HUMAN_REVIEW
        for decision in result.decisions:
            if decision.action == FilterAction.NEEDS_HUMAN_REVIEW:
                result.final_action = FilterAction.NEEDS_HUMAN_REVIEW
                return result

        result.final_action = FilterAction.PASS
        return result

    def to_dict(self) -> list[dict]:
        """Serialize filter chain configuration to dict."""
        return [{"name": f.name, "type": type(f).__name__} for f in self.filters]


def create_default_filter_chain() -> FilterChain:
    """Create a default filter chain with all standard filters.

    The chain order is: script → path → network → budget.
    This matches the expected evaluation order:
    - Script content is checked first (fastest)
    - Path safety is checked second
    - Network access is checked third
    - Budget is checked last (most expensive)
    """
    chain = FilterChain()
    chain.add_filter(HighRiskScriptFilter())
    chain.add_filter(PathSafetyFilter())
    chain.add_filter(NetworkAccessFilter(block_all=True))
    chain.add_filter(BudgetFilter(max_executions=10, max_total_time_ms=60_000))
    return chain