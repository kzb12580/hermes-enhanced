"""Code tools — execute Python code in a sandbox with access to tools."""

from __future__ import annotations

import json
import asyncio
import tempfile
import os
from .base import BaseTool
from . import register


class ExecuteCodeTool(BaseTool):
    name = "execute_code"
    description = "Execute a Python script and return stdout. Use for batch operations, data processing, complex calculations, or when you need multiple tool calls with logic between them. The script runs in a temporary file."
    timeout = 120
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute. Use print() for output. Available: os, json, pathlib, subprocess, re, math, csv, datetime, collections.",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory (optional)",
                "default": "",
            },
        },
        "required": ["code"],
    }

    async def execute(self, code: str, workdir: str = "", **kwargs) -> str:
        # Write code to a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            script_path = f.name

        try:
            is_windows = __import__("platform").system() == "Windows"
            python = "python" if is_windows else "python3"

            cwd = workdir if workdir and os.path.isdir(workdir) else None

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            proc = await asyncio.create_subprocess_exec(
                python, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=110)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return json.dumps({"ok": False, "error": "Code execution timed out (110s)"}, ensure_ascii=False)

            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()

            result = {"ok": proc.returncode == 0, "exit_code": proc.returncode}
            if out:
                result["output"] = out[:10000]  # Cap at 10KB
            if err:
                result["error"] = err[:5000]
            if not out and not err:
                result["output"] = "(no output)"

            return json.dumps(result, ensure_ascii=False)
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass


register(ExecuteCodeTool())
