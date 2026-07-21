# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""CLI argument parser for the code review agent."""

from __future__ import annotations

import argparse


def create_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="review-agent",
        description="tRPC-Agent-Python — 自动代码评审 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
输入模式（三选一）：
  --diff-file <path>    读取 unified diff 文件
  --repo-path <path>    检测 git 工作区变更
  --fixture <name>      加载测试样本（fixtures/ 目录下）

示例：
  review-agent --diff-file changes.diff
  review-agent --repo-path /path/to/repo
  review-agent --fixture 01_clean
  review-agent --fixture 01_clean --dry-run
        """,
    )

    # ── Input sources (mutually exclusive) ──
    input_group = parser.add_argument_group("输入源（三选一）")
    input_group.add_argument(
        "--diff-file",
        type=str,
        metavar="PATH",
        help="读取 unified diff 文件路径",
    )
    input_group.add_argument(
        "--repo-path",
        type=str,
        metavar="PATH",
        help="Git 工作区路径，自动检测变更",
    )
    input_group.add_argument(
        "--fixture",
        type=str,
        metavar="NAME",
        help="加载测试样本（如 01_clean，自动匹配 fixtures/ 下的 .diff 文件）",
    )

    # ── Output options ──
    output_group = parser.add_argument_group("输出选项")
    output_group.add_argument(
        "--output-dir",
        type=str,
        default=".",
        metavar="DIR",
        help="报告输出目录（默认：当前目录）",
    )
    output_group.add_argument(
        "--output-json",
        type=str,
        default=None,
        metavar="PATH",
        help="review_report.json 输出路径（覆盖 --output-dir）",
    )
    output_group.add_argument(
        "--output-md",
        type=str,
        default=None,
        metavar="PATH",
        help="review_report.md 输出路径（覆盖 --output-dir）",
    )

    # ── Database options ──
    db_group = parser.add_argument_group("数据库选项")
    db_group.add_argument(
        "--db-path",
        type=str,
        default="review.db",
        metavar="PATH",
        help="SQLite 数据库文件路径（默认：review.db）",
    )

    # ── Execution options ──
    exec_group = parser.add_argument_group("执行选项")
    exec_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry-run 模式：不执行沙箱，仅测试解析和落库链路",
    )
    exec_group.add_argument(
        "--fake-model",
        action="store_true",
        help="Fake-model 模式：跳过 LLM 调用，使用模拟结果",
    )
    exec_group.add_argument(
        "--sandbox",
        type=str,
        default="local",
        choices=["local", "container", "cube"],
        help="沙箱执行器类型（默认：local，仅开发用）",
    )
    exec_group.add_argument(
        "--sandbox-timeout",
        type=int,
        default=30,
        metavar="SECONDS",
        help="沙箱执行超时时间（默认：30s）",
    )
    exec_group.add_argument(
        "--list-fixtures",
        action="store_true",
        help="列出所有可用的测试样本",
    )

    # ── Filter options ──
    filter_group = parser.add_argument_group("Filter 选项")
    filter_group.add_argument(
        "--disable-filters",
        action="store_true",
        help="禁用所有 Filter（不推荐）",
    )

    # ── Model options (for future use) ──
    model_group = parser.add_argument_group("模型选项（LLM 模式）")
    model_group.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="NAME",
        help="模型名称（如 gpt-4o, claude-3.5-sonnet）",
    )
    model_group.add_argument(
        "--api-key",
        type=str,
        default=None,
        metavar="KEY",
        help="API Key（默认从环境变量读取）",
    )
    model_group.add_argument(
        "--base-url",
        type=str,
        default=None,
        metavar="URL",
        help="API Base URL（默认从环境变量读取）",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments and validate input source."""
    parser = create_parser()
    args = parser.parse_args(argv)

    # Validate: exactly one input source
    sources = [args.diff_file, args.repo_path, args.fixture]
    if args.list_fixtures:
        # --list-fixtures is a standalone action
        pass
    elif sum(1 for s in sources if s is not None) != 1:
        parser.error("必须指定一个输入源：--diff-file、--repo-path 或 --fixture（三选一）")

    return args