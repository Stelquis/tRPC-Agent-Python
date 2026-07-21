#!/usr/bin/env python3
"""Static analysis security check script.

Scans source code for common security issues:
- Hardcoded secrets / credentials
- Command injection patterns
- Path traversal patterns
- Sensitive information exposure

Usage:
    python3 check_security.py --file target.py
    python3 check_security.py --dir /path/to/source
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Patterns
# ──────────────────────────────────────────────

SECRET_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'].+?["\']'), "hardcoded_api_key"),
    (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'].+?["\']'), "hardcoded_password"),
    (re.compile(r'(?i)(secret|token)\s*[=:]\s*["\'].+?["\']'), "hardcoded_secret"),
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), "openai_api_key"),
    (re.compile(r'ghp_[A-Za-z0-9]{36,}'), "github_token"),
    (re.compile(r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----'), "private_key"),
]

SHELL_INJECTION_PATTERNS = [
    (re.compile(r'os\.system\s*\(\s*f["\']'), "os_system_fstring"),
    (re.compile(r'subprocess\.[a-zA-Z]+\s*\(\s*f["\']'), "subprocess_fstring"),
    (re.compile(r'eval\s*\(\s*[^)]*input'), "eval_with_input"),
    (re.compile(r'exec\s*\(\s*[^)]*input'), "exec_with_input"),
    (re.compile(r'os\.popen\s*\(\s*[^)]*input'), "os_popen_input"),
]

PATH_TRAVERSAL_PATTERNS = [
    (re.compile(r'open\s*\(\s*f["\'].*?\{.*?\}.*?["\']'), "open_fstring_path"),
    (re.compile(r'Path\s*\(\s*["\'].*?\+\s*[a-zA-Z]'), "path_concatenation"),
]


# ──────────────────────────────────────────────
# AST-based checks
# ──────────────────────────────────────────────


class SecurityVisitor(ast.NodeVisitor):
    """AST visitor to detect security issues."""

    def __init__(self, filename: str):
        self.filename = filename
        self.findings = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check for shell=True in subprocess calls
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("call", "run", "Popen"):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    self.findings.append({
                        "line": node.lineno,
                        "rule": "subprocess_shell_true",
                        "severity": "critical",
                        "message": "subprocess called with shell=True, risk of command injection",
                    })
        self.generic_visit(node)


def check_ast_security(source: str, filename: str) -> list[dict]:
    """Run AST-based security checks."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return [{"line": 0, "rule": "parse_error", "severity": "warning", "message": "Could not parse file"}]

    visitor = SecurityVisitor(filename)
    visitor.visit(tree)
    return visitor.findings


def check_regex_patterns(source: str, filename: str) -> list[dict]:
    """Run regex-based security checks."""
    findings = []
    for pattern, rule_name in SECRET_PATTERNS:
        for match in pattern.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            findings.append({
                "line": line_num,
                "rule": rule_name,
                "severity": "high",
                "message": f"Possible hardcoded secret detected: {rule_name}",
            })

    for pattern, rule_name in SHELL_INJECTION_PATTERNS:
        for match in pattern.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            findings.append({
                "line": line_num,
                "rule": rule_name,
                "severity": "high",
                "message": f"Possible command injection: {rule_name}",
            })

    for pattern, rule_name in PATH_TRAVERSAL_PATTERNS:
        for match in pattern.finditer(source):
            line_num = source[:match.start()].count("\n") + 1
            findings.append({
                "line": line_num,
                "rule": rule_name,
                "severity": "medium",
                "message": f"Possible path traversal: {rule_name}",
            })

    return findings


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


def scan_file(filepath: str) -> dict:
    """Scan a single file for security issues."""
    source = Path(filepath).read_text(encoding="utf-8")
    regex_findings = check_regex_patterns(source, filepath)
    ast_findings = check_ast_security(source, filepath)
    return {
        "file": filepath,
        "findings": regex_findings + ast_findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Security static analysis")
    parser.add_argument("--file", type=str, help="Single file to scan")
    parser.add_argument("--dir", type=str, help="Directory to scan recursively")
    args = parser.parse_args()

    if args.file:
        results = [scan_file(args.file)]
    elif args.dir:
        results = []
        for pyfile in Path(args.dir).rglob("*.py"):
            results.append(scan_file(str(pyfile)))
    else:
        # Read from stdin
        source = sys.stdin.read()
        filepath = getattr(args, "stdin_name", "stdin")
        results = [{
            "file": filepath,
            "findings": check_regex_patterns(source, filepath) + check_ast_security(source, filepath),
        }]

    print(json.dumps({"results": results}, indent=2))


if __name__ == "__main__":
    main()