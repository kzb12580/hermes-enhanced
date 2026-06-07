"""Verify tool — check that operations succeeded by reading back results."""

from __future__ import annotations

import json
import os
from .base import BaseTool
from . import register


class VerifyFileTool(BaseTool):
    name = "verify_file"
    description = "验证文件是否存在，并可选检查其内容。创建或写入文件后使用，用于确认操作成功。"
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要验证的文件路径"},
            "expected_content": {"type": "string", "description": "可选：文件中应包含的字符串", "default": ""},
            "min_size": {"type": "integer", "description": "可选：最小文件大小（字节）", "default": 0},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, expected_content: str = "", min_size: int = 0, **kwargs) -> str:
        # Path safety: reuse file_tools whitelist-based sandbox
        from .file_tools import _resolve_safe_path
        resolved = _resolve_safe_path(path)
        if isinstance(resolved, str):
            return json.dumps({"ok": False, "error": resolved}, ensure_ascii=False)
        path = str(resolved)

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
    description = "运行验证命令并检查输出。用于验证安装、服务或配置。"
    timeout = 30
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要运行的验证命令"},
            "expected_in_output": {"type": "string", "description": "输出中应出现的字符串", "default": ""},
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


