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

MAX_CONTENT_LENGTH = 100_000
MAX_TOOL_RESULT_SIZE = 10_000  # 10KB per tool result
MAX_TOOL_CALLS_PER_TURN = 10
MAX_TOOL_ITERATIONS = 5  # Max tool execution loops per turn

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

DEFAULT_SYSTEM_PROMPT = """You are Hermes, an AI desktop assistant with FULL tool access. You MUST use tools to complete tasks — NEVER just describe what you would do.

## CRITICAL RULES
1. **ACT, don't describe** — When user asks to create/modify/search something, call the tool IMMEDIATELY. Do NOT say "I can help you with that" or "Would you like me to..." — just DO IT.
2. **Maintain context** — Remember what was discussed. If user says "1" or "yes" or "ok", refer to the previous offer/question.
3. **No unnecessary questions** — If user says "make a PPT about X", make it directly with reasonable defaults. Don't ask for style/length/format unless truly ambiguous.
4. **NEVER say you can't do something** — You have tools. Use them. If user asks for a PPT, create it. If they ask to search, search. If they ask to run code, run it.
5. **Maintain conversation state** — Keep track of what you've done. If you created a file, remember the path. If you searched something, remember the results.

## AVAILABLE TOOLS
### File Operations
- **read_file** — Read file contents with line numbers
- **write_file** — Create/overwrite any file (.py, .md, .pptx, .docx, .xlsx, .html, etc.)
- **search_files** — Search for files by name or content patterns
- **list_files** — List directory contents

### System Operations
- **terminal** — Run shell commands (python scripts, pip install, system commands)

### Web Operations
- **web_search** — Search the internet (DuckDuckGo)
- **web_extract** — Extract and read content from URLs

### Vision & Screen
- **screen_capture** — Take screenshots of the current screen
- **vision_locate** — Analyze screenshots to locate GUI elements or understand screen content
- **ocr_extract** — Extract text from images using OCR

## YOUR CAPABILITIES
You CAN do all of these by writing Python scripts and running them:
- **PPT Creation** — python-pptx library is installed
- **Word Documents** — python-docx library is installed
- **Excel Spreadsheets** — openpyxl library is installed
- **Image Processing** — Pillow library is installed
- **Web Scraping** — Use web_search and web_extract tools
- **File Operations** — Read, write, search any file
- **Code Execution** — Run any Python script via terminal tool
- **Screen Automation** — pyautogui is installed (mouse, keyboard control)
- **Visual Understanding** — Use screen_capture + vision_locate to see and understand screen content
- **OCR Text Extraction** — Use ocr_extract to read text from images, screenshots, or scanned documents

## SCREEN AUTOMATION WORKFLOW
To interact with GUI elements:
1. Take a screenshot: screen_capture(region='full')
2. Find the element: vision_locate(image_path='...', question='find the login button')
3. Use the coordinates from vision_locate result with pyautogui to click/type

## HOW TO CREATE PPT
1. Write a Python script using python-pptx
2. Run it with terminal tool
3. Tell user the output file path
Example: User says "make a PPT about apples" → write apple_ppt.py → run it → "Created: apple_report.pptx"

## HOW TO CREATE WORD/EXCEL
Same pattern: write Python script → run it → deliver file

## CONTEXT & MEMORY
You have persistent memory. Previous conversations and user preferences are injected into your context. Use this knowledge to provide better, personalized responses.

Respond in the user's language. Be concise. Always use tools to complete tasks."""


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


class SessionCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


# ─── Managers ──────────────────────────────────────────────────────────────

session_manager = SessionManager()


# ─── Helper Functions ──────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate."""
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
    """Trim message history to fit within token limit."""
    if not messages:
        return messages
    result = [messages[0]]
    total_tokens = estimate_tokens(messages[0].get("content", ""))
    for msg in reversed(messages[1:]):
        msg_tokens = 0
        if "content" in msg and msg["content"]:
            msg_tokens += estimate_tokens(msg["content"])
        if "tool_calls" in msg:
            msg_tokens += estimate_tokens(json.dumps(msg["tool_calls"]))
        if total_tokens + msg_tokens > max_input_tokens and result:
            break
        result.append(msg)
        total_tokens += msg_tokens
    result.reverse()
    return result


def truncate_tool_result(result: str) -> str:
    """Truncate tool result if too large."""
    if len(result) > MAX_TOOL_RESULT_SIZE:
        return result[:MAX_TOOL_RESULT_SIZE] + f"\n\n[Result truncated: {len(result)} chars total]"
    return result


def build_system_prompt(custom_prompt: Optional[str] = None) -> str:
    """Build system prompt with memory and skills context."""
    memory_ctx = get_memory_context()
    skills_ctx = skill_manager.get_skills_context()
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
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                            elif "tool_calls" in delta:
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
        tool_args = json.loads(tool_call["function"]["arguments"])

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
    return {"sessions": session_manager.list_sessions()}


@router.post("/api/chat/sessions")
async def create_session(request: SessionCreate):
    """Create a new session."""
    session_id = str(int(time.time() * 1000))
    session = session_manager.create_session(session_id, request.name)
    return {"session_id": session_id, "name": request.name}


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

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename to avoid collisions
    ext = os.path.splitext(file.filename or "file")[1]
    unique_name = f"{uuid.uuid4().hex[:12]}_{file.filename or 'file'}"
    file_path = os.path.join(upload_dir, unique_name)

    contents = await file.read()
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

    # Build API messages
    sys_prompt = build_system_prompt(message.system_prompt)
    context_window, max_response = get_model_context_config(message.model or "default")
    system_tokens = estimate_tokens(sys_prompt)
    max_input_tokens = context_window - max_response - system_tokens - 500

    api_messages = [{"role": "system", "content": sys_prompt}]
    api_messages.extend(trim_messages(session["messages"], max_input_tokens))

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
                
                # Continue loop for follow-up LLM call
                logger.info("Tool iteration %d done, calling LLM again", iteration + 1)
            
            # If loop exhausted (all iterations had tool calls), call LLM one final time
            # WITHOUT tools so it must generate a text response
            last_had_tools = len(raw_tool_calls) > 0 if 'raw_tool_calls' in dir() else False
            if last_had_tools:
                logger.info("Tool loop exhausted, calling LLM for final text response (no tools)")
                # Strip heavy tool messages to free context space for the final response
                trimmed_messages = []
                for msg in current_messages:
                    if msg.get("role") == "tool":
                        continue  # Drop tool results
                    if msg.get("role") == "assistant" and msg.get("tool_calls"):
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
