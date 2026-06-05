"""Chat API — handles chat sessions with tool execution."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi import UploadFile, File as FastAPIFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.session_manager import SessionManager
from api.memory import get_memory_context
from api.prompts import build_system_prompt as _build_system_prompt, build_tools_description
from api.skills_manager import skill_manager
from tools import all_tools, openai_tools, execute_tool

logger = logging.getLogger("hermes-backend.chat")
router = APIRouter()

# ─── Constants (base defaults, overridden by perf_detect) ──────────────────

MAX_CONTENT_LENGTH = 500_000
MAX_TOOL_RESULT_SIZE = 50_000  # 50KB per tool result
MAX_TOOL_CALLS_PER_TURN = 50
MAX_TOOL_ITERATIONS = 90  # Max tool execution loops per turn

# Apply adaptive limits from performance detection
try:
    from perf_detect import get_limits as _get_perf_limits
    _plimits = _get_perf_limits()
    MAX_CONTENT_LENGTH = _plimits["max_content_length"]
    MAX_TOOL_RESULT_SIZE = _plimits["max_tool_result_size"]
    MAX_TOOL_CALLS_PER_TURN = _plimits["max_tool_calls_per_turn"]
    MAX_TOOL_ITERATIONS = _plimits["max_tool_iterations"]
except Exception:
    pass  # Use defaults if perf detection fails

# ─── System Prompt ─────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are Hermes, an AI desktop assistant with FULL tool access. You work like a senior engineer — plan, execute, verify, report.

## WORKFLOW (ALWAYS FOLLOW THIS)

### Phase 1: PLAN
Before doing ANYTHING complex (3+ steps), create a task plan:
- Call `todo_create` with numbered steps
- This keeps you on track and lets the user see progress

### Phase 2: EXECUTE
- Work through tasks ONE AT A TIME
- Mark each task `in_progress` before starting, `completed` when done
- If a task fails, mark it `failed` and try an alternative approach
- NEVER skip to a new task without finishing or failing the current one

### Phase 3: VERIFY
After EVERY file write, command execution, or system change:
- Call `verify_file` to confirm files exist and have correct content
- Call `verify_command` to confirm commands succeeded
- NEVER assume success — always verify

### Phase 4: REPORT
When all tasks complete:
- Call `todo_list` to show final status
- Give a structured summary: what was done, what succeeded, what failed
- If something failed, explain why and suggest next steps

## CRITICAL RULES
1. **ACT, don't describe** — Call tools IMMEDIATELY. Don't say "I'll help you" — just DO IT.
2. **Maintain context** — If user says "需要" or "继续" or "ok", EXECUTE the previous offer. Do NOT re-analyze.
3. **No unnecessary questions** — Use reasonable defaults. Only ask if truly ambiguous.
4. **Verify everything** — After creating a file, verify_file it. After running a command, check the output.
5. **Track progress** — Use todo_update to mark tasks done. User can see your progress.
6. **Handle errors** — If something fails, try 2-3 alternatives before giving up. Don't just report the error.
7. **Compress when possible** — For long outputs, summarize key findings. Don't dump raw data.

## ⚠️ LARGE DATA HANDLING (CRITICAL)

When working with large files, many items, or complex documents, NEVER put all data in tool call arguments. This causes output truncation and API errors.

### Rules:
1. **创建PPT** → 用 `create_ppt`（PptxGenJS，支持动画/图表/表格）
   - ≤5页：直接传 `slides` 参数
   - >5页：先 `write_file("slides.json", JSON)` → 再 `create_ppt(path, slides_file="slides.json")`
2. **Insert many images** → Use `write_file` to write a Python script, then `execute_command` to run it
3. **Large data processing** → 先 `write_file("script.py", code)` → 再 `execute_command("python script.py")`
4. **Batch file operations** → Write a script that loops through files, don't make 100 separate tool calls
5. **Reading large files** → Read in chunks (offset/limit), don't read entire 100MB files

⚠️ **execute_code 只用于短脚本（<20行）！长脚本必须先 write_file 再 execute_command，否则会截断。**

### Pattern for large operations:
```
Step 1: write_file("batch_insert_images.py", script_content)
Step 2: execute_command("python batch_insert_images.py")
Step 3: verify_file(output_path)
```

### What NOT to do:
❌ 用 python-pptx 或 execute_code 自己写PPT脚本（用 create_ppt 工具！）
❌ edit_word with 100 insert_image operations in one call
❌ create_excel with 10,000 rows inline

### 分块写入协议（当收到 content_too_large / code_too_large 错误时）：
当后端返回"内容过大，请分块写入"时，**必须按指示分块发送**：
1. 后端会告诉你总块数 N
2. 第1块：write_file(path, chunk1_content, chunk_index=1, total_chunks=N)
3. 第2块：write_file(path, chunk2_content, chunk_index=2, total_chunks=N)
4. ...直到第N块
5. 后端自动合并所有块并写入目标文件

⚠️ **不要试图绕过分块！** 如果后端说内容太大，就必须分块。不要重复发送完整内容。
❌ read_file on a 50MB file

### What TO do:
✅ 创建PPT用 create_ppt 工具，不要自己写 python-pptx 脚本
✅ >5页PPT: write_file("slides.json", [...]) → create_ppt(path, slides_file="slides.json")
✅ Use glob patterns to find files, not listing them one by one
✅ Process in batches (e.g., 10 images per script run)
✅ Report progress: "Processing images 1-10/100..."


## AVAILABLE TOOLS
### File Operations
- read_file(path, offset, limit) — 读取文件内容，支持分页
- write_file(path, content) — 创建/覆盖文件，自动创建目录
- search_files(pattern, path, file_glob) — 按内容或文件名搜索
- list_files(path, pattern) — 列出目录内容
- verify_file(path) — 验证文件存在且内容正确

### Code Execution
- execute_code(code, workdir) — 执行Python脚本，返回stdout。用于批量操作、数据处理、复杂逻辑

### System
- terminal(command, timeout, workdir) — 执行shell命令（Windows用PowerShell）
- verify_command(command) — 执行验证命令并检查输出

#### ⚠️ PowerShell Rules (Windows)
- PowerShell uses `-Flag` syntax, NOT Unix `--flag`
- ❌ `cd dir && python script.py` → ✅ `cd dir; python script.py` (PowerShell uses `;` not `&&`)
- For large file operations, use Python scripts via `execute_code` instead of shell commands

#### ⚠️ Python Code Generation Rules
- String formatting: use `'text %s' % var` NOT `'text %%s' %% var` (single % not double)
- f-strings: `f'text {var}'` — ensure all `{` have matching `}`
- Always test small code first before writing complex scripts

### Web
- web_search(query, limit) — 搜索互联网
- web_extract(urls) — 提取网页内容为Markdown

### Vision & Screen
- screen_capture — 截图
- ocr_extract — OCR文字提取

### Task Management
- todo_create(todos) — 创建任务计划
- todo_update(id, status) — 更新任务状态
- todo_list — 查看当前任务进度

### Memory & Session
- save_memory(content) — 保存重要信息
- search_memory(query) — 搜索已保存的记忆
- list_memories — 列出所有记忆
- delete_memory — 删除过时记忆
- search_session(query) — 搜索历史会话记录
- get_session_history(session_id) — 获取会话历史

### Office
- create_word(path, title, content, template, font_size, line_spacing) — 创建Word文档
- read_word(path) — 读取Word内容
- edit_word(path, operations) — 编辑Word（插入/替换/删除/图片/表格）
- create_ppt(path, slides, slides_file, layout, title, author) — 创建PPT（PptxGenJS）
  - ≤5页：直接传slides参数
  - >5页：先write_file("slides.json")再传slides_file
- create_excel(path, sheets) — 创建Excel
- read_excel(path, sheet_name, max_rows) — 读取Excel
- edit_excel(path, operations) — 编辑Excel（单元格/公式/图表/格式/合并）

### PPT 动画工具（专用）
- animate_ppt(path, animations, transitions) — 为PPT添加原生动画（40+种效果）
  - 先用 list_ppt_shapes(path) 查看形状ID
  - animations: [{"slide": 1, "effect": "fade", "target": "all_text", "duration": 0.5, "trigger": "afterprev"}]
  - transitions: [{"slide": 1, "type": "fade", "duration": 1, "direction": "left"}]
  - target选项: "all", "all_text", "title", "body", "all_images", "1,3,5"(形状ID)
  - 触发方式: "onclick"(点击), "withprev"(同时), "afterprev"(之后)
- list_ppt_shapes(path, slide) — 列出PPT形状名称和ID
- list_anim_effects() — 列出所有可用动画效果

### Office 工具限制
- create_ppt 用 PptxGenJS（Node.js），原生支持过渡动画，无需 COM 自动化
- animate_ppt 用 XML 直接操作，支持逐元素动画编排，无需 python-pptx 或 COM
- PPT 动画工作流: create_ppt(创建) → animate_ppt(加动画) → 完成
- Word/Excel 不支持同时打开同一个文件编辑（会锁定）
- 如果操作失败2次，换一种方案或告知用户手动操作
- 大文件（>100行Excel）必须用 execute_code 写脚本

### GUI Automation
- mouse_move/click/drag/scroll — 鼠标控制
- keyboard_type/hotkey/press — 键盘输入
- list_windows/find_window/bring_to_front — 窗口管理
- wait/get_mouse_position/get_screen_size — 辅助工具

## EXAMPLE: Complex Task
User: "帮我测试所有功能并生成报告"

Step 1: todo_create([{id:"1",content:"测试文件操作"}, {id:"2",content:"测试终端"}, ...])
Step 2: todo_update("1", "in_progress") → list_files, write_file, read_file, verify_file
Step 3: todo_update("1", "completed") → todo_update("2", "in_progress")
Step 4: terminal, verify_command → todo_update("2", "completed")
Step 5: create_word(report) → verify_file(report)
Step 6: todo_list → structured summary

## SCREEN AUTOMATION
1. screen_capture → 2. vision_locate → 3. mouse_click(coordinates)

## OFFICE CREATION
Write Python script → terminal(run it) → verify_file(output)

Respond in the user's language. Be concise. Always use tools. Always verify. Always track progress."""


# ─── Models ────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_LENGTH)
    session_id: Optional[str] = None
    model: Optional[str] = "default"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=128000)
    attachments: Optional[list[dict]] = None
    # Frontend features that were silently dropped:
    thinking_mode: Optional[str] = None  # off/auto/on
    thinking_budget: Optional[int] = None
    skills: Optional[list[str]] = None  # active skill IDs
    proxy_url: Optional[str] = None


class SessionCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


# ─── Managers ──────────────────────────────────────────────────────────────

session_manager = SessionManager()


# ─── Helper Functions ──────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate."""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars + (other_chars // 4) + 1


def get_model_context_config(model: str) -> tuple[int, int]:
    """Get context window and max response tokens for a model."""
    model_lower = model.lower()
    if "mimo" in model_lower:
        return 1_000_000, 128_000  # max_tokens 拉满，防止大工具调用截断
    if "claude" in model_lower:
        return 200_000, 4096
    if "gpt-4" in model_lower:
        return 128_000, 4096
    if "gpt-3.5" in model_lower:
        return 16_385, 4096
    return 32_768, 4096


def trim_messages(messages: list[dict], max_input_tokens: int) -> list[dict]:
    """Trim message history to fit within token limit.
    
    Strategy: Keep messages from the end, but never split a tool-call chain.
    A tool-call chain = assistant message with tool_calls + ALL its tool results.
    This ensures the API always receives complete tool-call/result pairs.
    """
    if not messages:
        return messages
    
    # Step 1: Group messages into blocks that must stay together
    # A "block" is either a single message or an assistant+tool_calls followed by all its tool results
    blocks = []  # list of (messages_list, token_count)
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            # This is the start of a tool-call chain
            chain = [msg]
            chain_tokens = estimate_tokens(msg.get("content", "")) + estimate_tokens(json.dumps(msg["tool_calls"]))
            # Collect all matching tool results
            tool_call_ids = {tc.get("id") for tc in msg["tool_calls"]}
            j = i + 1
            while j < len(messages) and messages[j].get("role") == "tool":
                tc_id = messages[j].get("tool_call_id", "")
                if tc_id in tool_call_ids:
                    chain.append(messages[j])
                    chain_tokens += estimate_tokens(messages[j].get("content", ""))
                j += 1
            blocks.append((chain, chain_tokens))
            i = j
        else:
            msg_tokens = estimate_tokens(msg.get("content", "")) + estimate_tokens(json.dumps(msg.get("tool_calls", ""))) if msg.get("tool_calls") else estimate_tokens(msg.get("content", ""))
            blocks.append(([msg], msg_tokens))
            i += 1
    
    # Step 2: Keep blocks from the end until token limit
    kept = []
    total_tokens = 0
    for chain, chain_tokens in reversed(blocks):
        if total_tokens + chain_tokens > max_input_tokens:
            break
        kept.append(chain)
        total_tokens += chain_tokens
    kept.reverse()
    
    # Step 3: Flatten and ensure first message is present
    result = []
    for chain in kept:
        result.extend(chain)
    
    # Always include the first message (system/user context)
    if result and messages and result[0] is not messages[0]:
        first_tokens = estimate_tokens(messages[0].get("content", ""))
        if total_tokens + first_tokens <= max_input_tokens:
            result.insert(0, messages[0])
    
    return result


def truncate_tool_result(result: str) -> str:
    """Truncate tool result if too large."""
    if len(result) > MAX_TOOL_RESULT_SIZE:
        return result[:MAX_TOOL_RESULT_SIZE] + f"\n\n[Result truncated: {len(result)} chars total]"
    return result


def _compress_session_tools(session: dict, keep_recent: int = 6):
    """Compress old tool results in session to prevent context bloat.
    
    Keeps the most recent `keep_recent` tool results at full size.
    Older tool results are compressed to a one-line summary.
    This prevents the session from growing unbounded and losing context.
    """
    messages = session.get("messages", [])
    if not messages:
        return
    
    # Find all tool result message indices
    tool_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            tool_indices.append(i)
    
    if len(tool_indices) <= keep_recent:
        return  # Not enough tool results to compress
    
    # Compress old tool results
    compress_count = 0
    cutoff = tool_indices[-keep_recent]  # Don't compress this or later
    
    for i in tool_indices:
        if i >= cutoff:
            break
        msg = messages[i]
        content = msg.get("content", "")
        if len(content) > 200:
            # Extract tool name from the preceding assistant message
            tool_name = "tool"
            tool_call_id = msg.get("tool_call_id", "")
            for j in range(i - 1, max(0, i - 5), -1):
                prev = messages[j]
                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                    for tc in prev["tool_calls"]:
                        if tc.get("id") == tool_call_id:
                            tool_name = tc.get("function", {}).get("name", "tool")
                            break
                    break
            
            # Create a compact summary
            first_line = content.split("\n")[0][:150]
            msg["content"] = f"[{tool_name}] {first_line}... ({len(content)} chars)"
            compress_count += 1
    
    if compress_count > 0:
        logger.info("Compressed %d old tool results in session", compress_count)


# ── ContextCompressorV2 集成 ────────────────────────────────────────────
from context_compressor_v2 import ContextCompressorV2, CompressedMessages

# 全局压缩器实例（按 context_window 动态创建）
_compressors: dict[int, ContextCompressorV2] = {}

def _get_compressor(context_window: int) -> ContextCompressorV2:
    """获取或创建对应 context_window 的压缩器实例"""
    if context_window not in _compressors:
        # 平衡模式：75% 压力阈值，保留最近 5 轮工具结果
        _compressors[context_window] = ContextCompressorV2(
            model_token_limit=context_window,
            profile="balanced"
        )
    return _compressors[context_window]


def _smart_compress_session(session: dict, context_window: int) -> None:
    """使用 ContextCompressorV2 智能压缩会话。
    
    替代原有的简单 _compress_session_tools，增加：
    - 压力监控：实时追踪上下文占用比例
    - 三级压缩：micro → reactive → full
    - 自动选择：根据压力自动选最轻量的级别
    """
    messages = session.get("messages", [])
    if not messages or len(messages) < 4:
        return
    
    compressor = _get_compressor(context_window)
    
    # 检查是否需要压缩
    should, reason = compressor.should_compress(messages)
    if not should:
        return
    
    # 自动选择压缩级别执行
    result: CompressedMessages = compressor.compress(messages, level="auto")
    
    if result.compressed_tokens < result.original_tokens:
        # 压缩有效，回写会话
        session["messages"] = result.messages
        stats = compressor.get_stats()
        logger.info(
            "ContextCompressorV2: %s 压缩，%d → %d tokens (比率 %.1f%%，节省 %d tokens，累计 %d 次压缩)",
            result.level_used,
            result.original_tokens,
            result.compressed_tokens,
            result.ratio * 100,
            result.original_tokens - result.compressed_tokens,
            stats["compressions_count"],
        )


import re as _re


def _try_repair_json(raw: str) -> str | None:
    """Attempt to repair truncated/malformed JSON from LLM output.
    
    Common truncation patterns:
    - Unterminated string: {"key": "value with no closing quote
    - Missing closing braces: {"key": "value", "list": [1, 2
    - Truncated after colon: {"script":
    """
    if not raw or not raw.strip():
        return None
    
    raw = raw.strip()
    
    # Strategy 1: Try adding missing closing quotes + braces
    # Count open/close braces and brackets
    open_braces = raw.count('{') - raw.count('}')
    open_brackets = raw.count('[') - raw.count(']')
    
    # Check if we're inside an unterminated string
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
    
    repair = raw
    
    # If unterminated string, close it
    if in_string:
        repair += '"'
    
    # Close any unclosed arrays
    for _ in range(max(0, open_brackets)):
        repair += ']'
    
    # Close any unclosed objects
    for _ in range(max(0, open_braces)):
        repair += '}'
    
    try:
        json.loads(repair)
        return repair
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Strategy 2: Find last valid JSON by truncating at last complete key-value
    # This handles cases where the truncation is mid-value
    for end in range(len(raw) - 1, max(0, len(raw) - 200), -1):
        candidate = raw[:end]
        # Try to close it
        extra_braces = candidate.count('{') - candidate.count('}')
        extra_brackets = candidate.count('[') - candidate.count(']')
        
        # Check string state
        in_str = False
        esc = False
        for ch in candidate:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
        
        if in_str:
            candidate += '"'
        for _ in range(max(0, extra_brackets)):
            candidate += ']'
        for _ in range(max(0, extra_braces)):
            candidate += '}'
        
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            continue
    
    return None


def _salvage_truncated_write_file(raw_args: str) -> str | None:
    """Salvage a truncated write_file tool call by extracting path and partial content."""
    import re
    
    path_match = re.search(r'"path"\s*:\s*"([^"]*)"', raw_args)
    if not path_match:
        return None
    path = path_match.group(1)
    
    content_match = re.search(r'"content"\s*:\s*"', raw_args)
    if not content_match:
        return json.dumps({"path": path, "content": ""}, ensure_ascii=False)
    
    content_start = content_match.end()
    raw_content = raw_args[content_start:]
    
    # Unescape JSON string escapes in the partial content
    raw_content = raw_content.replace('\\"', '"')
    raw_content = raw_content.replace('\\n', chr(10))
    raw_content = raw_content.replace('\\t', chr(9))
    raw_content = raw_content.replace('\\\\', '\\')
    
    if raw_content.endswith('\\'):
        raw_content = raw_content[:-1]
    
    if not raw_content:
        return None
    
    try:
        return json.dumps({"path": path, "content": raw_content}, ensure_ascii=False)
    except Exception:
        return None
def _salvage_truncated_execute_code(raw_args: str) -> str | None:
    """Salvage a truncated execute_code tool call by extracting partial code.
    
    Converts to a write_file call that saves the partial code to a temp file.
    The model can then use execute_command("python temp_script.py") to run it.
    Returns write_file JSON string or None if extraction fails.
    """
    import re
    import tempfile
    
    # Try to extract "code" field
    code_match = re.search(r'"code"\s*:\s*"', raw_args)
    if not code_match:
        return None
    
    code_start = code_match.end()
    raw_code = raw_args[code_start:]
    
    # Unescape JSON string escapes
    bs = chr(92)
    raw_code = raw_code.replace(bs + '"', '"')
    raw_code = raw_code.replace(bs + 'n', chr(10))
    raw_code = raw_code.replace(bs + 't', chr(9))
    raw_code = raw_code.replace(bs + bs, bs)
    
    if raw_code.endswith(bs):
        raw_code = raw_code[:-1]
    
    if not raw_code:
        return None
    
    # Write partial code to temp file
    try:
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
        tmp.write(raw_code)
        tmp.close()
        return json.dumps({"path": tmp.name, "content": raw_code}, ensure_ascii=False)
    except Exception:
        return None




def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """Fix malformed tool_calls in session messages before sending to API.
    
    Common issues:
    - tool_calls with missing function name
    - tool_calls with empty/invalid JSON arguments
    - assistant messages with tool_calls but no content (need None, not "")
    - orphaned tool result messages after tool_call removal
    """
    result = []
    valid_tool_call_ids: set[str] = set()
    
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            # Validate each tool_call
            valid_calls = []
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name", "")
                if not name:
                    logger.warning("Dropping tool_call with missing function name: %s", tc)
                    continue
                # Ensure arguments is a string and valid JSON
                args = func.get("arguments", "{}")
                if not isinstance(args, str):
                    try:
                        args = json.dumps(args, ensure_ascii=False)
                    except Exception:
                        args = "{}"
                # Validate JSON — try to repair truncated JSON instead of dropping
                try:
                    json.loads(args)
                except (json.JSONDecodeError, ValueError) as e:
                    repaired = _try_repair_json(args)
                    if repaired is not None:
                        args = repaired
                        tc["function"]["arguments"] = args
                        logger.info("Repaired truncated JSON for tool_call: %s", name)
                    else:
                        # Special handling: write_file/execute_code with truncated content
                        # Extract path/code and partial content instead of dropping entirely
                        if name == "write_file":
                            salvaged = _salvage_truncated_write_file(args)
                            if salvaged:
                                args = salvaged
                                tc["function"]["arguments"] = args
                                logger.warning("Salvaged truncated write_file: wrote partial content")
                            else:
                                logger.warning("Dropping tool_call with invalid JSON arguments: %s (%s)", name, e)
                                continue
                        elif name == "execute_code":
                            salvaged = _salvage_truncated_execute_code(args)
                            if salvaged:
                                # Convert to write_file — save partial code to temp file
                                tc["function"]["name"] = "write_file"
                                args = salvaged
                                tc["function"]["arguments"] = args
                                logger.warning("Salvaged truncated execute_code: converted to write_file")
                            else:
                                logger.warning("Dropping tool_call with invalid JSON arguments: %s (%s)", name, e)
                                continue
                        else:
                            logger.warning("Dropping tool_call with invalid JSON arguments: %s (%s)", name, e)
                            continue
                tc_id = tc.get("id", f"call_{hash(name)}")
                valid_calls.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
                valid_tool_call_ids.add(tc_id)
            if valid_calls:
                clean_msg = {"role": "assistant", "content": msg.get("content") or None, "tool_calls": valid_calls}
            else:
                # All tool_calls were invalid — keep as text-only assistant message
                clean_msg = {"role": "assistant", "content": msg.get("content") or "(tool calls removed)"}
            # Preserve reasoning_content for MIMO multi-turn compatibility
            if msg.get("reasoning_content"):
                clean_msg["reasoning_content"] = msg["reasoning_content"]
            result.append(clean_msg)
        elif msg.get("role") == "tool":
            # Only keep tool results that match a surviving tool_call
            tc_id = msg.get("tool_call_id", "")
            if tc_id and msg.get("content") is not None and tc_id in valid_tool_call_ids:
                result.append(msg)
            else:
                logger.warning("Dropping orphaned/malformed tool message: id=%s", tc_id[:20] if tc_id else "none")
        else:
            result.append(msg)
    return result


def _parse_text_tool_calls(text: str) -> list[dict]:
    """Parse text-based tool calls from LLM output (fallback for models without function calling).
    
    Supports formats:
    - <function=name>args</function>
    - <function=name>{"key": "value"}</function>
    - ```json\n{"name": "tool", "arguments": {...}}\n```
    """
    calls = []
    
    # Pattern 1: <function=name>args</function>
    for match in _re.finditer(r'<function=(\w+)>(.*?)</function>', text, _re.DOTALL):
        name = match.group(1)
        args_raw = match.group(2).strip()
        args = {}
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            # Try to repair truncated JSON first
            repaired = _try_repair_json(args_raw)
            if repaired:
                try:
                    args = json.loads(repaired)
                except (json.JSONDecodeError, ValueError):
                    repaired = None
            if not repaired:
                # Try to parse as key=value pairs
                args = {}
                for part in args_raw.split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        args[k.strip()] = v.strip().strip('"').strip("'")
                if not args:
                    args = {"input": args_raw}
        calls.append({
            "id": f"txt_{hash(name) & 0xFFFFFFFF:08x}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
        })
    
    # Pattern 2: ```json blocks with tool call format
    if not calls:
        for match in _re.finditer(r'```json\s*(\{[^`]*"name"\s*:\s*"(\w+)"[^`]*)\s*```', text, _re.DOTALL):
            try:
                data = json.loads(match.group(1))
                name = data.get("name", "")
                arguments = data.get("arguments", data.get("args", {}))
                if name:
                    calls.append({
                        "id": f"txt_{hash(name) & 0xFFFFFFFF:08x}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                    })
            except json.JSONDecodeError:
                # Try to repair truncated JSON before dropping
                repaired = _try_repair_json(match.group(1))
                if repaired:
                    try:
                        data = json.loads(repaired)
                        name = data.get("name", "")
                        arguments = data.get("arguments", data.get("args", {}))
                        if name:
                            calls.append({
                                "id": f"txt_{hash(name) & 0xFFFFFFFF:08x}",
                                "type": "function",
                                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                            })
                    except (json.JSONDecodeError, ValueError):
                        pass
    
    return calls


def build_system_prompt(custom_prompt=None, active_skills=None, model_name=None):
    """Build system prompt with memory and skills context."""
    memory_ctx = get_memory_context()
    skills_ctx = skill_manager.get_skills_context(active_skills=active_skills)
    tools_desc = build_tools_description(openai_tools())
    
    # Workspace context
    workspace = os.environ.get("HERMES_WORKSPACE", "").strip()
    workspace_ctx = ""
    if workspace and os.path.isdir(workspace):
        workspace_ctx = f"\n## 工作区\n当前工作区目录: {workspace}\n所有文件操作默认在此目录下进行。用户说\"桌面\"时指此目录。\n"
    else:
        # Default to user's Desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.isdir(desktop):
            workspace_ctx = f"\n## 工作区\n当前工作区目录: {desktop}\n所有文件操作默认在此目录下进行。\n"
    
    return _build_system_prompt(
        custom_prompt=custom_prompt,
        memory_context=memory_ctx,
        skills_context=skills_ctx,
        tools_description=tools_desc,
        extra_context=workspace_ctx,
        model_name=model_name,
    )


async def call_llm_streaming(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    tools: Optional[list[dict]] = None,
    proxy_url: Optional[str] = None,
):
    """Call LLM API with streaming support."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # Proxy resolution: explicit proxy_url > system env vars
    client_kwargs: dict = {"timeout": 120}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    else:
        client_kwargs["trust_env"] = True

    async with httpx.AsyncClient(**client_kwargs) as client:
        async with client.stream(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                logger.error("API error %d: %s", response.status_code, error_text[:500])
                raise HTTPException(status_code=response.status_code, detail=error_text.decode())

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and chunk["choices"]:
                            choice = chunk["choices"][0]
                            delta = choice.get("delta", {}) if choice else {}
                            # Log finish_reason for truncation detection
                            fr = choice.get("finish_reason")
                            if fr and fr != "stop":
                                logger.warning("LLM finish_reason=%s (may indicate truncation)", fr)
                            # Handle reasoning_content (MIMO requirement)
                            if "reasoning_content" in delta and delta["reasoning_content"]:
                                rlen = len(delta["reasoning_content"])
                                if rlen > 0:
                                    # Yield as special marker for parent to capture
                                    yield json.dumps({"reasoning_content": delta["reasoning_content"]})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                            elif "tool_calls" in delta and delta["tool_calls"]:
                                yield json.dumps({"tool_calls": delta["tool_calls"]})
                    except (json.JSONDecodeError, TypeError):
                        continue


async def call_llm(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    tools: Optional[list[dict]] = None,
    proxy_url: Optional[str] = None,
) -> dict:
    """Call LLM API without streaming (for tool calls)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # Proxy resolution: explicit proxy_url > system env vars
    client_kwargs: dict = {"timeout": 120}
    if proxy_url:
        client_kwargs["proxy"] = proxy_url
    else:
        client_kwargs["trust_env"] = True

    async with httpx.AsyncClient(**client_kwargs) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            error_text = response.text
            logger.error("API error %d: %s", response.status_code, error_text[:500])
            raise HTTPException(status_code=response.status_code, detail=error_text)

        return response.json()


async def execute_tools(tool_calls: list[dict], model: str = "") -> list[dict]:
    """Execute multiple tool calls with retry and error recovery."""
    results = []
    for tool_call in tool_calls[:MAX_TOOL_CALLS_PER_TURN]:
        tool_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        
        # Check for oversized tool arguments — try to extract key field to file
        if len(args_str) > 15_000:  # 15KB threshold
            logger.warning("Tool %s has oversized arguments (%d chars), attempting recovery", tool_name, len(args_str))
            recovered = await _handle_oversized_args(tool_name, args_str, tool_call)
            if recovered:
                results.append(recovered)
                continue
            results.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": f"Error: Tool arguments too large ({len(args_str)} chars). "
                           f"Write the content to a file first using write_file, then reference the file path.",
            })
            continue
        
        try:
            tool_args = json.loads(args_str)
        except (json.JSONDecodeError, KeyError) as e:
            # Try to repair truncated JSON (common with long write_file content)
            repaired = _try_repair_json(args_str)
            if repaired is not None:
                try:
                    tool_args = json.loads(repaired)
                    logger.info("Repaired truncated JSON for tool %s", tool_name)
                except (json.JSONDecodeError, ValueError):
                    logger.error("Failed to parse tool arguments even after repair: %s", e)
                    results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": f"Error: Invalid tool arguments format: {e}",
                    })
                    continue
            else:
                logger.error("Failed to parse tool arguments: %s", e)
                results.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": f"Error: Invalid tool arguments format: {e}",
                })
                continue

        # Inject model name for tools that need it (chunk size limits)
        if model:
            tool_args["_model"] = model

        # Execute with retry for transient errors
        result = await _execute_with_retry(tool_name, tool_args)
        result = truncate_tool_result(result)
        logger.info("Tool result: %s...", result[:200])

        results.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result,
        })
    return results


# Retryable error patterns (transient failures that may succeed on retry)
_RETRYABLE_PATTERNS = [
    "timeout", "timed out", "connection", "ECONNRESET", "ECONNREFUSED",
    "rate limit", "429", "503", "502", "500", "network", "socket",
]


async def _execute_with_retry(tool_name: str, tool_args: dict, max_retries: int = 2) -> str:
    """Execute a tool with retry for transient errors."""
    last_result = ""
    for attempt in range(max_retries + 1):
        result = await execute_tool(tool_name, tool_args)
        
        # Check if result is a retryable error
        if result.startswith("Error:") and attempt < max_retries:
            result_lower = result.lower()
            if any(pat.lower() in result_lower for pat in _RETRYABLE_PATTERNS):
                delay = 1.5 ** attempt  # exponential backoff: 1s, 1.5s
                logger.info("Retryable error for %s (attempt %d/%d), retrying in %.1fs: %s",
                           tool_name, attempt + 1, max_retries, delay, result[:100])
                import asyncio
                await asyncio.sleep(delay)
                last_result = result
                continue
        
        return result
    
    return last_result


async def _handle_oversized_args(tool_name: str, args_str: str, tool_call: dict) -> dict | None:
    """Handle oversized tool arguments by writing content to a temp file.
    
    For tools that receive large content, write to a temp file and modify the tool call.
    """
    try:
        # Try to parse the (possibly truncated) JSON
        args = None
        try:
            args = json.loads(args_str)
        except (json.JSONDecodeError, ValueError):
            repaired = _try_repair_json(args_str)
            if repaired:
                args = json.loads(repaired)
        
        if not args:
            return None
        
        # Find the largest string field (likely the script/content)
        largest_key = None
        largest_size = 0
        for key, val in args.items():
            if isinstance(val, str) and len(val) > largest_size:
                largest_key = key
                largest_size = len(val)
        
        if not largest_key or largest_size < 5000:
            return None
        
        # Write the large content to a temp file
        import tempfile
        content = args[largest_key]
        ext = ".txt"
        if "code" in largest_key.lower():
            ext = ".py"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False, encoding='utf-8') as f:
            f.write(content)
            temp_path = f.name
        
        # Replace the large field with a file reference
        args[largest_key] = f"[Content written to {temp_path} ({len(content)} chars). Read this file to get the content.]"
        args[f"{largest_key}_file"] = temp_path
        
        logger.info("Oversized %s arg '%s' (%d chars) written to %s", tool_name, largest_key, len(content), temp_path)
        
        # Re-execute with the modified args
        result = await execute_tool(tool_name, args)
        result = truncate_tool_result(result)
        
        return {
            "role": "tool",
            "tool_call_id": tool_call.get("id", ""),
            "content": result,
        }
    except Exception as e:
        logger.error("Failed to handle oversized args for %s: %s", tool_name, e)
        return None


# ─── API Routes ────────────────────────────────────────────────────────────

@router.get("/api/chat/sessions")
async def list_sessions():
    """List all sessions."""
    return session_manager.list_sessions()


@router.post("/api/chat/sessions")
async def create_session(request: SessionCreate):
    """Create a new session."""
    import uuid; session_id = str(uuid.uuid4())[:13]
    session = session_manager.create_session(session_id, request.name)
    return {"id": session_id, "name": session["name"], "created_at": session.get("created_at"), "message_count": 0}


@router.get("/api/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "messages": session["messages"],
        "created_at": session.get("created_at"),
    }


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_manager.delete_session(session_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/api/chat/sessions/{session_id}/clear")
async def clear_session(session_id: str):
    """Clear session history."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["messages"] = []
    session_manager._save()
    return {"status": "cleared"}


@router.post("/api/upload")
async def upload_file(file: UploadFile = FastAPIFile(...)):
    """Upload a file and return its server path."""
    import uuid

    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename to avoid collisions
    ext = os.path.splitext(file.filename or "file")[1]
    unique_name = f"{uuid.uuid4().hex[:12]}_{file.filename or 'file'}"
    file_path = os.path.join(upload_dir, unique_name)

    # 分块读取，检查大小限制
    contents = b""
    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        contents += chunk
        if len(contents) > MAX_UPLOAD_SIZE:
            return {"error": f"File too large: max {MAX_UPLOAD_SIZE // 1024 // 1024}MB", "success": False}

    with open(file_path, "wb") as f:
        f.write(contents)

    logger.info("File uploaded: %s (%d bytes)", unique_name, len(contents))

    return {
        "filename": file.filename,
        "path": file_path,
        "size": len(contents),
    }


@router.post("/api/chat")
async def chat(message: ChatMessage):
    """Process a chat message with tool support."""
    session_id = message.session_id or str(int(time.time() * 1000))

    # Get or create session
    session = session_manager.get_session(session_id)
    if not session:
        session = session_manager.create_session(session_id)

    # Add user message to history
    # Prepend attachment info to content if present
    user_content = message.content
    if message.attachments:
        attachment_lines = []
        for att in message.attachments:
            fname = att.get("filename", "file")
            fpath = att.get("path", "")
            fsize = att.get("size", 0)
            attachment_lines.append(f"[附件: {fname} ({fsize} bytes) 路径: {fpath}]")
        user_content = "\n".join(attachment_lines) + "\n\n" + user_content

    session["messages"].append({
        "role": "user",
        "content": user_content,
    })

    # Build API messages — use message-specific skills if provided
    skills_override = message.skills if message.skills else None
    sys_prompt = build_system_prompt(message.system_prompt, active_skills=skills_override, model_name=message.model)
    context_window, max_response = get_model_context_config(message.model or "default")
    system_tokens = estimate_tokens(sys_prompt)
    max_input_tokens = context_window - max_response - system_tokens - 500

    api_messages = [{"role": "system", "content": sys_prompt}]
    # Sanitize session messages — fix any malformed tool_calls before sending to API
    sanitized = _sanitize_messages(trim_messages(session["messages"], max_input_tokens))
    api_messages.extend(sanitized)

    # Prepare API call
    base_url = message.base_url or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
    api_key = message.api_key or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=401, detail="API key not configured")

    model = message.model or "gpt-3.5-turbo"
    max_tokens = message.max_tokens or max_response
    temperature = message.temperature if message.temperature is not None else 0.7
    tools = openai_tools()

    async def generate_stream():
        """Generate SSE stream for chat response with tool execution loop."""
        try:
            current_messages = list(api_messages)
            raw_tool_calls = []  # 初始化，防止循环未执行时未绑定
            consecutive_failures = 0  # 连续失败计数器
            last_fail_tool = ""  # 上次失败的工具名
            MAX_CONSECUTIVE_FAILURES = 3  # 同一工具连续失败3次自动终止
            
            for iteration in range(MAX_TOOL_ITERATIONS + 1):
                # Call LLM with streaming
                full_response = ""
                raw_tool_calls = []  # Accumulate streaming tool call deltas
                reasoning_text = ""  # Accumulate reasoning_content for MIMO
                
                # Sanitize before each LLM call — drop broken tool_calls from previous iteration
                current_messages = _sanitize_messages(current_messages)
                
                async for chunk in call_llm_streaming(base_url, api_key, model, current_messages, max_tokens, temperature, tools, proxy_url=message.proxy_url):
                    if isinstance(chunk, str) and chunk.startswith('{"reasoning_content"'):
                        # MIMO reasoning_content — capture but don't send to frontend
                        try:
                            rc_data = json.loads(chunk)
                            reasoning_text += rc_data.get("reasoning_content", "")
                        except json.JSONDecodeError:
                            pass
                    elif isinstance(chunk, str) and not chunk.startswith('{"tool_calls"'):
                        # Regular content token
                        full_response += chunk
                        yield f"event: token\ndata: {chunk}\n\n"
                    elif isinstance(chunk, str) and chunk.startswith('{"tool_calls"'):
                        # Tool call delta from streaming
                        try:
                            tc_data = json.loads(chunk)
                            tc = tc_data.get("tool_calls")
                            if tc:
                                raw_tool_calls.extend(tc)
                        except json.JSONDecodeError:
                            pass
                
                # If no API tool calls, try parsing text-based tool calls
                # (for models that don't support function calling natively)
                if not raw_tool_calls and full_response:
                    text_tool_calls = _parse_text_tool_calls(full_response)
                    if text_tool_calls:
                        raw_tool_calls = text_tool_calls
                        logger.info("Parsed %d text-based tool calls from response", len(text_tool_calls))
                
                # If no tool calls, we're done
                if not raw_tool_calls:
                    break
                
                # Accumulate streaming tool call deltas into complete tool calls
                # Streaming sends partial updates: {index:0, id:"xxx", function:{name:"...", arguments:"..."}}
                accumulated = {}
                for tc in raw_tool_calls:
                    idx = tc.get("index", 0)
                    if idx not in accumulated:
                        accumulated[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    if tc.get("id"):
                        accumulated[idx]["id"] = tc["id"]
                    if tc.get("type"):
                        accumulated[idx]["type"] = tc["type"]
                    func = tc.get("function", {})
                    if func.get("name"):
                        accumulated[idx]["function"]["name"] = func["name"]
                    if func.get("arguments"):
                        accumulated[idx]["function"]["arguments"] += func["arguments"]
                
                complete_tool_calls = list(accumulated.values())
                
                # Log tool call details for debugging truncation
                for tc in complete_tool_calls:
                    fn = tc.get("function", {})
                    args_len = len(fn.get("arguments", ""))
                    logger.info(
                        "Tool call: %s — args_len=%d chars, args_preview=%s...",
                        fn.get("name", "?"), args_len, fn.get("arguments", "")[:100],
                    )
                
                # Send tool call events to frontend
                for tc in complete_tool_calls:
                    yield f"event: tool_call\ndata: {json.dumps({'id': tc['id'], 'name': tc['function']['name'], 'arguments': tc['function']['arguments']})}\n\n"
                
                # Add assistant message with tool_calls to history
                # Include reasoning_content for MIMO multi-turn compatibility
                assistant_msg = {"role": "assistant", "content": full_response or None, "tool_calls": complete_tool_calls}
                if reasoning_text:
                    assistant_msg["reasoning_content"] = reasoning_text
                    logger.info("Captured reasoning_content: %d chars", len(reasoning_text))
                current_messages.append(assistant_msg)
                session["messages"].append(assistant_msg)
                
                # Execute tools
                tool_results = await execute_tools(complete_tool_calls, model=model)
                
                # Send tool results and add to messages
                for result in tool_results:
                    yield f"event: tool_result\ndata: {json.dumps({'id': result['tool_call_id'], 'result': result['content']})}\n\n"
                    current_messages.append(result)
                    session["messages"].append(result)
                
                # Track consecutive failures — per-tool tracking
                # Only count if the SAME tool keeps failing (different tools failing is OK)
                failed_tools = [r.get("content", "") for r in tool_results if r.get("content", "").startswith("Error:")]
                if failed_tools:
                    # Check if the failing tool is the same as last time
                    current_fail_tool = complete_tool_calls[0]["function"]["name"] if complete_tool_calls else "unknown"
                    if current_fail_tool == last_fail_tool:
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 1
                        last_fail_tool = current_fail_tool
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        error_hint = f"工具 {current_fail_tool} 连续失败{consecutive_failures}次，自动停止。请换一种方案或告知用户手动操作。"
                        yield f"event: token\\ndata: {error_hint}\\n\\n"
                        logger.warning("Auto-stopping: tool %s failed %d times consecutively", current_fail_tool, consecutive_failures)
                        break
                else:
                    consecutive_failures = 0
                    last_fail_tool = ""
                
                # Context trimming: 每 5 次迭代裁剪一次，防止 context 超限
                if (iteration + 1) % 5 == 0:
                    context_window, max_response = get_model_context_config(model or "default")
                    system_tokens = estimate_tokens(sys_prompt)
                    max_input_tokens = context_window - max_response - system_tokens - 500
                    current_messages = list(trim_messages(current_messages, max_input_tokens))
                
                # Continue loop for follow-up LLM call
                logger.info("Tool iteration %d done, calling LLM again", iteration + 1)
            
            # If loop exhausted (all iterations had tool calls), call LLM one final time
            # WITHOUT tools so it must generate a text response
            last_had_tools = len(raw_tool_calls) > 0
            if last_had_tools:
                logger.info("Tool loop exhausted, calling LLM for final text response (no tools)")
                # Strip heavy tool messages to free context space for the final response
                trimmed_messages = []
                for msg in current_messages:
                    if msg.get("role") == "tool":
                        # Truncate tool results instead of dropping entirely
                        content = msg.get("content", "")
                        if len(content) > 500:
                            content = content[:500] + "...[truncated]"
                        trimmed_messages.append({**msg, "content": content})
                    elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                        trimmed = {k: v for k, v in msg.items() if k != "tool_calls"}
                        if not trimmed.get("content"):
                            trimmed["content"] = "(used tools)"
                        trimmed_messages.append(trimmed)
                        continue
                    trimmed_messages.append(msg)
                logger.info("Trimmed messages: %d → %d for final response", len(current_messages), len(trimmed_messages))
                final_response = ""
                final_reasoning = ""
                async for chunk in call_llm_streaming(base_url, api_key, model, trimmed_messages, max_tokens, temperature, tools=None, proxy_url=message.proxy_url):
                    if isinstance(chunk, str) and chunk.startswith('{"reasoning_content"'):
                        try:
                            rc_data = json.loads(chunk)
                            final_reasoning += rc_data.get("reasoning_content", "")
                        except json.JSONDecodeError:
                            pass
                    elif isinstance(chunk, str) and not chunk.startswith('{"tool_calls"'):
                        final_response += chunk
                        yield f"event: token\ndata: {chunk}\n\n"
                if final_response:
                    final_msg = {"role": "assistant", "content": final_response}
                    if final_reasoning:
                        final_msg["reasoning_content"] = final_reasoning
                    current_messages.append(final_msg)
                    session["messages"].append(final_msg)
            
            # Save session
            session_manager._save()

            # ── 使用 ContextCompressorV2 智能压缩会话 ──
            _smart_compress_session(session, locals().get('context_window', 128000))
            
            # Send done event
            yield "event: done\ndata: \n\n"

        except Exception as e:
            logger.error("Streaming error: %s", e, exc_info=True)
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/api/chat/tools")
async def list_tools():
    """List all available tools."""
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in all_tools()
        ]
    }
