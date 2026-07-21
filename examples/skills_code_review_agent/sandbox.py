# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Sandbox execution layer for the code review agent.

Provides a unified interface for executing analysis scripts in isolated
environments (container, cube, or local fallback), with configurable
timeout, output size limits, environment variable whitelist, and
failure recording.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────


@dataclass
class SandboxResult:
    """Result of a sandbox execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    output_truncated: bool = False
    error_message: Optional[str] = None
    timed_out: bool = False


# ──────────────────────────────────────────────
# Environment variable whitelist
# ──────────────────────────────────────────────

# Only these environment variables are allowed to pass into the sandbox.
# All others are filtered out for security.
DEFAULT_ENV_WHITELIST = {
    "PATH",
    "HOME",
    "PYTHONPATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "USER",
}


def filter_env(whitelist: set[str] | None = None) -> dict[str, str]:
    """Filter environment variables to only those in the whitelist."""
    if whitelist is None:
        whitelist = DEFAULT_ENV_WHITELIST
    return {k: v for k, v in os.environ.items() if k in whitelist}


# ──────────────────────────────────────────────
# Abstract sandbox executor
# ──────────────────────────────────────────────


class SandboxExecutor(ABC):
    """Abstract base class for sandboxed script execution."""

    def __init__(
        self,
        timeout: int = 30,
        max_output_bytes: int = 1_048_576,  # 1 MB
        env_whitelist: set[str] | None = None,
    ):
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self.env_whitelist = env_whitelist or DEFAULT_ENV_WHITELIST

    @abstractmethod
    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a command in the sandbox.

        Args:
            command: Shell command to execute.
            cwd: Working directory inside the sandbox.
            env: Additional environment variables (will be filtered by whitelist).

        Returns:
            SandboxResult with execution output and metadata.
        """
        ...

    def _truncate_output(self, text: str) -> tuple[str, bool]:
        """Truncate output if it exceeds max_output_bytes."""
        if len(text.encode("utf-8")) > self.max_output_bytes:
            truncated = text[: self.max_output_bytes] + "\n... [output truncated]"
            return truncated, True
        return text, False

    def _filter_env(self, extra_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        """Build a filtered environment dict."""
        env = filter_env(self.env_whitelist)
        if extra_env:
            for k, v in extra_env.items():
                if k in self.env_whitelist:
                    env[k] = v
        return env


# ──────────────────────────────────────────────
# Local fallback executor
# ──────────────────────────────────────────────


class LocalSandboxExecutor(SandboxExecutor):
    """Local subprocess-based sandbox executor.

    This is a development fallback only. Production use should prefer
    ContainerSandboxExecutor or CubeSandboxExecutor.
    """

    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> SandboxResult:
        start_time = time.monotonic()
        filtered_env = self._filter_env(env)
        timed_out = False
        error_message = None

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or os.getcwd(),
                env=filtered_env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                timed_out = True
                error_message = f"Sandbox execution timed out after {self.timeout}s"
                exit_code = -1
            else:
                exit_code = proc.returncode or 0

        except FileNotFoundError as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Command not found: {e}",
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Sandbox execution failed: {e}",
            )

        duration_ms = (time.monotonic() - start_time) * 1000

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        stdout_str, stdout_truncated = self._truncate_output(stdout_str)
        stderr_str, stderr_truncated = self._truncate_output(stderr_str)

        return SandboxResult(
            success=exit_code == 0 and not timed_out,
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=exit_code,
            duration_ms=duration_ms,
            output_truncated=stdout_truncated or stderr_truncated,
            error_message=error_message,
            timed_out=timed_out,
        )


# ──────────────────────────────────────────────
# Container sandbox executor
# ──────────────────────────────────────────────


class ContainerSandboxExecutor(SandboxExecutor):
    """Docker container-based sandbox executor.

    Wraps ContainerCodeExecutor from the tRPC-Agent framework.
    For now, provides a subprocess-based docker run implementation.
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout: int = 30,
        max_output_bytes: int = 1_048_576,
        env_whitelist: set[str] | None = None,
    ):
        super().__init__(timeout, max_output_bytes, env_whitelist)
        self.image = image

    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
    ) -> SandboxResult:
        start_time = time.monotonic()
        filtered_env = self._filter_env(env)

        # Build docker run command
        docker_cmd = ["docker", "run", "--rm", "-i"]
        docker_cmd.extend(["--network", "none"])  # No network access by default

        # Pass whitelisted env vars
        for k, v in filtered_env.items():
            docker_cmd.extend(["-e", f"{k}={v}"])

        # Mount current directory as workspace
        host_cwd = cwd or os.getcwd()
        docker_cmd.extend(["-v", f"{host_cwd}:/workspace:ro"])
        docker_cmd.extend(["-w", "/workspace"])

        # Image and command
        docker_cmd.append(self.image)
        docker_cmd.extend(["sh", "-c", command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                duration_ms = (time.monotonic() - start_time) * 1000
                return SandboxResult(
                    success=False,
                    stdout=stdout.decode("utf-8", errors="replace")[:500] if stdout else "",
                    stderr=stderr.decode("utf-8", errors="replace")[:500] if stderr else "",
                    exit_code=-1,
                    duration_ms=duration_ms,
                    error_message=f"Container sandbox timed out after {self.timeout}s",
                    timed_out=True,
                )

            exit_code = proc.returncode or 0
            duration_ms = (time.monotonic() - start_time) * 1000

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            stdout_str, stdout_truncated = self._truncate_output(stdout_str)
            stderr_str, stderr_truncated = self._truncate_output(stderr_str)

            return SandboxResult(
                success=exit_code == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                duration_ms=duration_ms,
                output_truncated=stdout_truncated or stderr_truncated,
            )

        except FileNotFoundError:
            duration_ms = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_ms=duration_ms,
                error_message="Docker not found. Is Docker installed?",
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
                error_message=f"Container sandbox failed: {e}",
            )


# ──────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────


def create_sandbox(
    sandbox_type: str = "local",
    timeout: int = 30,
    max_output_bytes: int = 1_048_576,
    **kwargs,
) -> SandboxExecutor:
    """Create a sandbox executor by type.

    Args:
        sandbox_type: One of "local", "container", "cube".
        timeout: Execution timeout in seconds.
        max_output_bytes: Maximum output size in bytes.

    Returns:
        A SandboxExecutor instance.

    Raises:
        ValueError: If sandbox_type is unknown.
    """
    if sandbox_type == "local":
        return LocalSandboxExecutor(timeout=timeout, max_output_bytes=max_output_bytes)
    elif sandbox_type == "container":
        image = kwargs.get("image", "python:3.12-slim")
        return ContainerSandboxExecutor(
            image=image, timeout=timeout, max_output_bytes=max_output_bytes
        )
    elif sandbox_type == "cube":
        raise NotImplementedError("Cube sandbox executor not yet implemented")
    else:
        raise ValueError(f"Unknown sandbox type: {sandbox_type}")