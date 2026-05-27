"""Terminal tool — execute shell commands with safety limits."""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess

from .base import BaseTool
from . import register

DEFAULT_TIMEOUT = 30
MAX_OUTPUT = 50_000  # 50KB

# Blocked commands (Windows-aware)
BLOCKED_PATTERNS = [
    "rm -rf /", "format ", "del /f /s /q C:", "rmdir /s /q C:",
    "shutdown", "bcdedit", "diskpart", "reg delete",
    "rm -rf /*", ":(){ :|:& };:", "mkfs",
]


class TerminalTool(BaseTool):
    name = "terminal"
    description = "Execute a shell command and return stdout/stderr. On Windows uses PowerShell, on Linux/macOS uses bash."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "workdir": {"type": "string", "description": "Working directory (optional)", "default": ""},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)", "default": 30},
        },
        "required": ["command"],
    }

    async def execute(self, command: str, workdir: str = "", timeout: int = DEFAULT_TIMEOUT, **kwargs) -> str:
        # Safety check
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_PATTERNS:
            if blocked.lower() in cmd_lower:
                return f"Error: Command blocked for safety: contains '{blocked}'"

        if timeout < 1 or timeout > 120:
            timeout = DEFAULT_TIMEOUT

        # Determine shell
        is_windows = platform.system() == "Windows"
        if is_windows:
            shell_cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]

        cwd = workdir if workdir and os.path.isdir(workdir) else None

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Error: Command timed out after {timeout}s"

            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()

            result = ""
            if out:
                result += out
            if err:
                result += f"\n[stderr]\n{err}" if result else err
            if not result:
                result = "(no output)"

            # Truncate if too long
            if len(result) > MAX_OUTPUT:
                result = result[:MAX_OUTPUT] + f"\n... (truncated, {len(result)} chars total)"

            exit_info = f"\n[exit code: {proc.returncode}]" if proc.returncode != 0 else ""
            return result + exit_info

        except FileNotFoundError:
            shell_name = "PowerShell" if is_windows else "bash"
            return f"Error: {shell_name} not found. Is it installed and in PATH?"
        except Exception as e:
            return f"Error: {e}"
