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
    description = "执行 Python 脚本并返回 stdout。大型脚本（超过 20 行）请使用 chunk_index/total_chunks 分块，或先 write_file 再 execute_command。"
    timeout = 120
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码。使用 print() 输出结果。可用模块：os、json、pathlib、subprocess、re、math、csv、datetime、collections。",
            },
            "workdir": {
                "type": "string",
                "description": "工作目录（可选）",
                "default": "",
            },
            "chunk_index": {"type": "integer", "description": "当前块号(从1开始)，大脚本分块时使用", "default": 0},
            "total_chunks": {"type": "integer", "description": "总块数，大脚本分块时使用", "default": 0},
        },
        "required": ["code"],
    }

    async def execute(self, code: str, workdir: str = "", chunk_index: int = 0, total_chunks: int = 0, **kwargs) -> str:
        import json as _json

        # If oversized recovery wrote code to a temp file, read from it
        code_file = kwargs.get("code_file", "")
        if code_file and os.path.isfile(code_file):
            try:
                with open(code_file, "r", encoding="utf-8") as f:
                    code = f.read()
            finally:
                # code_file is an oversized-argument spill file created by chat.py;
                # once loaded it must not remain in /tmp or the workspace.
                try:
                    os.unlink(code_file)
                except Exception:
                    pass

        # Chunked mode — store chunks, execute when complete
        if chunk_index > 0 and total_chunks > 0:
            from api.chunk_manager import store_chunk
            # Use a virtual path for the code chunks
            result = store_chunk("__execute_code__.py", chunk_index, total_chunks, code, workspace=workdir or None)
            if result.get("status") == "merged":
                # All chunks received — execute the merged code
                merged_path = result.get("path", "")
                if merged_path and os.path.isfile(merged_path):
                    # Run the merged script
                    return await self._run_script(merged_path, workdir)
            return _json.dumps(result, ensure_ascii=False)

        # Normal mode — check size and guide to chunking
        from api.model_limits import get_max_tool_arg_chars
        model = kwargs.get("_model", "")
        limit = get_max_tool_arg_chars(model)
        if len(code) > limit and limit < 50000:
            total = (len(code) + limit - 2) // (limit - 200)
            return _json.dumps({
                "ok": False,
                "error": "code_too_large",
                "char_count": len(code),
                "model_limit": limit,
                "instruction": f"代码过大({len(code)}字符)，请分块发送。总块数: {total}。第1块: execute_code(chunk_code, chunk_index=1, total_chunks={total})",
                "total_chunks": total,
            }, ensure_ascii=False)

        # Write code to a temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            script_path = f.name

        return await self._run_script(script_path, workdir)

    async def _run_script(self, script_path: str, workdir: str = "") -> str:

        try:
            is_windows = os.name == 'nt'
            python = "python" if is_windows else "python3"

            # Priority: explicit workdir > HERMES_WORKSPACE env > None
            cwd = workdir if workdir and os.path.isdir(workdir) else None
            if not cwd:
                ws = os.environ.get("HERMES_WORKSPACE", "").strip()
                if ws and os.path.isdir(ws):
                    cwd = ws

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
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return json.dumps({"ok": False, "error": "Code execution timed out (300s)"}, ensure_ascii=False)

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
