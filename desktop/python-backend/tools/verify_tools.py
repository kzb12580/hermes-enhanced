"""Verify tool — check that operations succeeded by reading back results."""

from __future__ import annotations

import json
import os
from .base import BaseTool
from . import register


class VerifyFileTool(BaseTool):
    name = "verify_file"
    description = "Verify a file exists and optionally check its content. Use after creating/writing files to confirm success. Always verify your work."
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to verify"},
            "expected_content": {"type": "string", "description": "Optional: substring that should exist in the file", "default": ""},
            "min_size": {"type": "integer", "description": "Optional: minimum file size in bytes", "default": 0},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, expected_content: str = "", min_size: int = 0, **kwargs) -> str:
        if not os.path.exists(path):
            return json.dumps({"ok": False, "error": f"File not found: {path}"}, ensure_ascii=False)
        
        size = os.path.getsize(path)
        result = {"ok": True, "path": path, "size": size}
        
        if min_size and size < min_size:
            result["ok"] = False
            result["error"] = f"File too small: {size} bytes (expected >= {min_size})"
        
        if expected_content:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                if expected_content not in content:
                    result["ok"] = False
                    result["error"] = f"Expected content not found in file"
            except Exception as e:
                result["ok"] = False
                result["error"] = str(e)
        
        return json.dumps(result, ensure_ascii=False)


class VerifyCommandTool(BaseTool):
    name = "verify_command"
    description = "Run a verification command and check its output. Use to verify installations, services, configurations."
    timeout = 30
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to run for verification"},
            "expected_in_output": {"type": "string", "description": "String that should appear in output", "default": ""},
        },
        "required": ["command"],
    }

    async def execute(self, command: str, expected_in_output: str = "", **kwargs) -> str:
        import asyncio
        # 安全检查：复用 terminal_tools 黑名单
        from .terminal_tools import _check_blocked
        blocked_err = _check_blocked(command)
        if blocked_err:
            return json.dumps({"ok": False, "error": blocked_err}, ensure_ascii=False)
        is_windows = __import__('platform').system() == "Windows"
        if is_windows:
            import shutil
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            utf8_cmd = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + command
            cmd = [shell, "-NoProfile", "-Command", utf8_cmd]
        else:
            cmd = ["bash", "-c", command]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)
            output = stdout.decode('utf-8', errors='replace').strip()
            
            result = {"ok": True, "exit_code": proc.returncode, "output": output[:2000]}
            
            if expected_in_output and expected_in_output not in output:
                result["ok"] = False
                result["error"] = f"Expected '{expected_in_output}' not found in output"
            
            if proc.returncode != 0:
                result["ok"] = False
                result["error"] = stderr.decode('utf-8', errors='replace').strip()[:500]
            
            return json.dumps(result, ensure_ascii=False)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return json.dumps({"ok": False, "error": "Command timed out (25s)"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


register(VerifyFileTool())
register(VerifyCommandTool())
