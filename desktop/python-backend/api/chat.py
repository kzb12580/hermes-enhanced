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

## AVAILABLE TOOLS
### File Operations
- read_file — Read file contents with line numbers
- write_file — Create/overwrite any file
- search_files — Search by name or content patterns
- list_files — List directory contents
- verify_file — Verify file exists and has correct content

### System
- terminal — Run shell commands (PowerShell on Windows, bash on Linux)
- verify_command — Run verification command and check output

### Web
- web_search — Search the internet
- web_extract — Extract content from URLs

### Vision & Screen
- screen_capture — Take screenshots
- vision_locate — AI-powered screen analysis
- ocr_extract — OCR text extraction

### Task Management
- todo_create — Create a task plan for complex work
- todo_update — Mark tasks as in_progress/completed/failed
- todo_list — Check current task progress

### Memory
- save_memory — Remember important information
- search_memory — Search saved memories
- list_memories — List all memories
- delete_memory — Remove outdated memories

### Office
- create_word/read_word/edit_word — Word documents
- create_ppt — PowerPoint presentations
- create_excel/read_excel/edit_excel — Excel spreadsheets

### GUI Automation
- mouse_move/click/drag/scroll — Mouse control
- keyboard_type/hotkey/press — Keyboard input
- list_windows/find_window/bring_to_front — Window management
- wait/get_mouse_position/get_screen_size — Utilities

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
        return 1_000_000, 32_000
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


import re as _re


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """Fix malformed tool_calls in session messages before sending to API.
    
    Common issues:
    - tool_calls with missing function name
    - tool_calls with empty arguments
    - assistant messages with tool_calls but no content (need None, not "")
    """
    result = []
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
                # Ensure arguments is a string
                args = func.get("arguments", "{}")
                if not isinstance(args, str):
                    try:
                        args = json.dumps(args, ensure_ascii=False)
                    except Exception:
                        args = "{}"
                valid_calls.append({
                    "id": tc.get("id", f"call_{hash(name)}"),
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
            if valid_calls:
                clean_msg = {"role": "assistant", "content": msg.get("content") or None, "tool_calls": valid_calls}
            else:
                # All tool_calls were invalid — keep as text-only assistant message
                clean_msg = {"role": "assistant", "content": msg.get("content") or "(tool calls removed)"}
            result.append(clean_msg)
        elif msg.get("role") == "tool":
            # Ensure tool messages have required fields
            if msg.get("tool_call_id") and msg.get("content") is not None:
                result.append(msg)
            else:
                logger.warning("Dropping malformed tool message: %s", list(msg.keys()))
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
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
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
                pass
    
    return calls


def build_system_prompt(custom_prompt: Optional[str] = None, active_skills: Optional[list[str]] = None) -> str:
    """Build system prompt with memory and skills context."""
    memory_ctx = get_memory_context()
    skills_ctx = skill_manager.get_skills_context(active_skills=active_skills)
    tools_desc = build_tools_description(openai_tools())
    
    return _build_system_prompt(
        custom_prompt=custom_prompt,
        memory_context=memory_ctx,
        skills_context=skills_ctx,
        tools_description=tools_desc,
    )


async def call_llm_streaming(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    tools: Optional[list[dict]] = None,
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

    async with httpx.AsyncClient(timeout=120) as client:
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
                            delta = chunk["choices"][0].get("delta", {}) if chunk["choices"][0] else {}
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                            elif "tool_calls" in delta and delta["tool_calls"]:
                                yield json.dumps({"tool_calls": delta["tool_calls"]})
                    except json.JSONDecodeError:
                        continue


async def call_llm(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    tools: Optional[list[dict]] = None,
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

    async with httpx.AsyncClient(timeout=120) as client:
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


async def execute_tools(tool_calls: list[dict]) -> list[dict]:
    """Execute multiple tool calls and return results."""
    results = []
    for tool_call in tool_calls[:MAX_TOOL_CALLS_PER_TURN]:
        tool_name = tool_call["function"]["name"]
        try:
            tool_args = json.loads(tool_call["function"]["arguments"])
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse tool arguments: %s", e)
            results.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": f"Error: Invalid tool arguments format: {e}",
            })
            continue

        logger.info("Executing tool: %s(%s)", tool_name, tool_args)
        result = await execute_tool(tool_name, tool_args)
        result = truncate_tool_result(result)
        logger.info("Tool result: %s...", result[:200])

        results.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result,
        })
    return results


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
    sys_prompt = build_system_prompt(message.system_prompt, active_skills=skills_override)
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
            
            for iteration in range(MAX_TOOL_ITERATIONS + 1):
                # Call LLM with streaming
                full_response = ""
                raw_tool_calls = []  # Accumulate streaming tool call deltas
                
                async for chunk in call_llm_streaming(base_url, api_key, model, current_messages, max_tokens, temperature, tools):
                    if isinstance(chunk, str) and not chunk.startswith('{"tool_calls"'):
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
                
                # Send tool call events to frontend
                for tc in complete_tool_calls:
                    yield f"event: tool_call\ndata: {json.dumps({'id': tc['id'], 'name': tc['function']['name'], 'arguments': tc['function']['arguments']})}\n\n"
                
                # Add assistant message with tool_calls to history
                assistant_msg = {"role": "assistant", "content": full_response or None, "tool_calls": complete_tool_calls}
                current_messages.append(assistant_msg)
                session["messages"].append(assistant_msg)
                
                # Execute tools
                tool_results = await execute_tools(complete_tool_calls)
                
                # Send tool results and add to messages
                for result in tool_results:
                    yield f"event: tool_result\ndata: {json.dumps({'id': result['tool_call_id'], 'result': result['content']})}\n\n"
                    current_messages.append(result)
                    session["messages"].append(result)
                
                # Context trimming: 每 5 次迭代裁剪一次，防止 context 超限
                if (iteration + 1) % 5 == 0:
                    context_window, max_response = get_model_context_config(model or "default")
                    system_tokens = estimate_tokens(session.get("system_prompt", ""))
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
                        if trimmed.get("content"):
                            trimmed_messages.append(trimmed)
                        continue
                    trimmed_messages.append(msg)
                logger.info("Trimmed messages: %d → %d for final response", len(current_messages), len(trimmed_messages))
                final_response = ""
                async for chunk in call_llm_streaming(base_url, api_key, model, trimmed_messages, max_tokens, temperature, tools=None):
                    if isinstance(chunk, str) and not chunk.startswith('{"tool_calls"'):
                        final_response += chunk
                        yield f"event: token\ndata: {chunk}\n\n"
                if final_response:
                    current_messages.append({"role": "assistant", "content": final_response})
                    session["messages"].append({"role": "assistant", "content": final_response})
            
            # Save session
            session_manager._save()

            # ── Compress old tool results in session to prevent context bloat ──
            _compress_session_tools(session)
            
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
