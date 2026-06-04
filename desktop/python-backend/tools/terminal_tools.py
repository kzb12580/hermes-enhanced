"""Terminal tool — execute shell commands with safety limits."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess

from .base import BaseTool
from . import register

DEFAULT_TIMEOUT = 180
MAX_OUTPUT = 50_000  # 50KB

# Blocked commands (Windows-aware)
BLOCKED_PATTERNS = [
    "rm -rf /", "format c:", "format d:", "format e:", "del /f /s /q C:", "rmdir /s /q C:",
    "shutdown", "bcdedit", "diskpart", "reg delete",
    "rm -rf /*", ":(){ :|:& };:", "mkfs",
    # Extended blocklist
    "del /s", "rd /s", "reboot",
    "reg add", "net user", "net localgroup",
    "Invoke-WebRequest", "certutil", "bitsadmin",
]


def _check_blocked(command: str) -> str:
    """检查命令是否被阻止，返回错误信息或空字符串"""
    import re
    cmd = command.strip()
    cmd_lower = cmd.lower()

    # 子串匹配
    for blocked in BLOCKED_PATTERNS:
        if blocked.lower() in cmd_lower:
            return f"Error: Command blocked for safety: contains '{blocked}'"

    # 正则匹配绕过模式
    dangerous_patterns = [
        r'rm\s+-rf\s+/',           # rm -rf / (有空格变体)
        r'rm\s+-rf\s+\*',          # rm -rf *
        r'shutdown\b',             # shutdown (词边界)
        r'reboot\b',               # reboot
        r'powershell\s+-e[cn]',    # powershell -enc/-ec
        r'cmd\s*/c\b',             # cmd /c
        r'cmd\.exe\s*/c\b',        # cmd.exe /c
        r'>\s*/dev/sd',            # 写入磁盘设备
        r'dd\s+.*of=/dev/',        # dd 写入设备
        r'mkfs\b',                 # 格式化
        r'fdisk\b',                # 分区工具
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, cmd, re.IGNORECASE):
            return f"Error: Command blocked for safety: matches dangerous pattern '{pattern}'"

    return ""


class TerminalTool(BaseTool):
    name = "terminal"
    description = (
        "Execute a shell command and return stdout/stderr. On Windows uses PowerShell, on Linux/macOS uses bash. "
        "⚠️ PowerShell does NOT use Unix-style flags (--flag). Use PowerShell syntax: "
        "-Flag (e.g., -Force, -Recurse, -Path). "
        "Common mistakes: 'cp --overwrite' → use 'Copy-Item -Force'; "
        "'mv --verbose' → use 'Move-Item -Verbose'; "
        "'rm -rf' → use 'Remove-Item -Recurse -Force'; "
        "'cd dir && cmd' → use 'cd dir; cmd' (PowerShell uses ; not &&)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "workdir": {"type": "string", "description": "Working directory (optional)", "default": ""},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 180)", "default": 180},
        },
        "required": ["command"],
    }

    timeout = 180  # class attribute — overrides BaseTool default for outer wrapper

    async def execute(self, command: str, workdir: str = "", timeout: int = DEFAULT_TIMEOUT, **kwargs) -> str:
        # Safety check
        blocked_err = _check_blocked(command)
        if blocked_err:
            return blocked_err

        # Validate workdir
        if workdir:
            from pathlib import Path
            wp = Path(workdir).resolve()
            # 防止在敏感目录执行命令
            blocked_dirs = ['/etc', '/boot', '/sys', '/proc', '/dev']
            if any(str(wp).startswith(d) for d in blocked_dirs):
                return f"Error: Working directory not allowed: {workdir}"

        # PowerShell 参数纠错 — 拦截 Unix 风格的 --flag 参数
        is_windows = platform.system() == "Windows"
        if is_windows:
            import re
            unix_flags = re.findall(r'--(\w[\w-]*)', command)
            if unix_flags:
                # 常见 Unix → PowerShell 映射
                corrections = {
                    "overwrite": "use 'Copy-Item -Force' instead",
                    "recursive": "use '-Recurse' instead",
                    "verbose": "use '-Verbose' instead",
                    "force": "use '-Force' instead",
                    "quiet": "use '-ErrorAction SilentlyContinue' instead",
                    "help": "use 'Get-Help' instead of --help",
                    "version": "use '$PSVersionTable' instead of --version",
                }
                suggestions = []
                for flag in unix_flags:
                    if flag in corrections:
                        suggestions.append(f"--{flag} → {corrections[flag]}")
                    else:
                        suggestions.append(f"--{flag} → use '-{flag}' (PowerShell syntax)")
                return (
                    "Error: PowerShell does not support Unix-style --flags.\n"
                    "Suggested fixes:\n" + "\n".join(f"  • {s}" for s in suggestions) +
                    "\n\nPlease rewrite using PowerShell syntax (-Flag, not --flag)."
                )
            # 拦截 && 语法（PowerShell 不支持）
            if '&&' in command:
                fixed = command.replace('&&', ';')
                return (
                    "Error: PowerShell does not support '&&' as command separator.\n"
                    f"Suggested fix: replace '&&' with ';'\n"
                    f"  • {command}\n"
                    f"  → {fixed}\n\n"
                    "Please rewrite using ';' to chain commands."
                )

        if timeout < 1 or timeout > 600:
            timeout = DEFAULT_TIMEOUT

        # Determine shell
        is_windows = platform.system() == "Windows"
        if is_windows:
            # Prefer pwsh (PowerShell 7) over Windows PowerShell
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            # Force UTF-8 output encoding so CJK characters display correctly
            # chcp 65001 sets the console code page to UTF-8 for external programs
            utf8_command = (
                "chcp 65001 >$null; "
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "[Console]::InputEncoding  = [System.Text.Encoding]::UTF8; "
                "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                f"{command}"
            )
            shell_cmd = [shell, "-NoProfile", "-Command", utf8_command]
        else:
            shell_cmd = ["bash", "-c", command]

        cwd = workdir if workdir and os.path.isdir(workdir) else None
        if not cwd:
            ws = os.environ.get("HERMES_WORKSPACE", "").strip()
            if ws and os.path.isdir(ws):
                cwd = ws

        # Windows subprocess flags
        kwargs_subprocess: dict = {}
        if is_windows:
            kwargs_subprocess["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                **kwargs_subprocess,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Error: Command timed out after {timeout}s"

            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()

            # GBK fallback: if UTF-8 decoding produced replacement chars, try GBK
            if "\ufffd" in out and not out.startswith("(no output)"):
                try:
                    out = stdout.decode("gbk", errors="strict").strip()
                except (UnicodeDecodeError, Exception):
                    pass  # keep UTF-8 with replacements
            if "\ufffd" in err:
                try:
                    err = stderr.decode("gbk", errors="strict").strip()
                except (UnicodeDecodeError, Exception):
                    pass

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
