# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Filter chain orchestration for the code review agent.

Orchestrates the filter evaluation pipeline (deny → needs_human_review → pass)
and writes interception records to the database and review report.
"""

from __future__ import annotations

from typing import Optional

from .db.storage import StorageABC
from .filters import (
    BaseReviewFilter,
    FilterAction,
    FilterChainResult,
    FilterDecision,
    HighRiskScriptFilter,
    PathSafetyFilter,
    NetworkAccessFilter,
    BudgetFilter,
)
from .models import FilterIntercept


class ReviewFilterChain:
    """Filter chain that evaluates commands and persists intercepts to DB.

    The chain follows strict ordering: DENY → NEEDS_HUMAN_REVIEW → PASS.
    If any filter returns DENY, the chain stops immediately.
    """

    def __init__(
        self,
        storage: StorageABC,
        task_id: str,
        filters: Optional[list[BaseReviewFilter]] = None,
    ):
        self.storage = storage
        self.task_id = task_id
        self.filters = filters or []

    def add_filter(self, filter_: BaseReviewFilter) -> None:
        """Add a filter to the chain."""
        self.filters.append(filter_)

    def evaluate(self, command: str, cwd: Optional[str] = None) -> FilterChainResult:
        """Evaluate a command against all filters and persist intercepts.

        Each non-PASS decision is written to the database as a FilterIntercept
        record, which will be included in the final review report.

        Args:
            command: The shell command to evaluate.
            cwd: Current working directory.

        Returns:
            FilterChainResult with all decisions and the final action.
        """
        result = FilterChainResult()

        for filter_ in self.filters:
            decision = filter_.evaluate(command, cwd)
            result.decisions.append(decision)

            # Persist non-PASS decisions to DB
            if decision.action != FilterAction.PASS:
                intercept = FilterIntercept(
                    task_id=self.task_id,
                    stage=decision.stage,
                    rule=decision.rule,
                    target=decision.target,
                    reason=decision.reason,
                    action=decision.action,
                )
                self.storage.add_filter_intercept(intercept)

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


def create_review_filter_chain(
    storage: StorageABC,
    task_id: str,
    block_all_network: bool = True,
    max_executions: int = 10,
    max_total_time_ms: float = 60_000,
) -> ReviewFilterChain:
    """Create a default review filter chain with DB integration.

    Args:
        storage: Storage backend for persisting intercepts.
        task_id: Current review task ID.
        block_all_network: If True, all network access is denied.
        max_executions: Maximum script executions per review.
        max_total_time_ms: Maximum total execution time in ms.

    Returns:
        Configured ReviewFilterChain instance.
    """
    chain = ReviewFilterChain(storage=storage, task_id=task_id)
    chain.add_filter(HighRiskScriptFilter())
    chain.add_filter(PathSafetyFilter())
    chain.add_filter(NetworkAccessFilter(block_all=block_all_network))
    chain.add_filter(BudgetFilter(max_executions=max_executions, max_total_time_ms=max_total_time_ms))
    return chain