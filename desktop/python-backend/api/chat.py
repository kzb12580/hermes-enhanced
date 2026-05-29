"""Chat API with SSE streaming + Tool Calling support."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from tools import openai_tools, execute_tool

logger = logging.getLogger("hermes-backend.chat")
router = APIRouter()

_sessions: dict[str, dict] = {}
_session_lock = asyncio.Lock()

MAX_SESSIONS = 50

MAX_CONTENT_LENGTH = 1 * 1024 * 1024
MAX_TOOL_ROUNDS = 999

# ─── Model context window mapping ───
# Key: model name substring → context window tokens
# Fallback: 32K if no match
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4.1": 1_048_576,
    "gpt-5": 1_048_576,
    "o1": 200_000,
    "o3": 200_000,
    "o4": 200_000,
    # Anthropic
    "claude-sonnet-4": 200_000,
    "claude-opus-4": 200_000,
    "claude-3.5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    # DeepSeek
    "deepseek-v3": 65_536,
    "deepseek-v4": 131_072,
    "deepseek-r1": 65_536,
    # Google
    "gemini-2.5": 1_048_576,
    "gemini-2.0": 1_048_576,
    "gemini-1.5": 1_048_576,
    # Qwen
    "qwen-max": 131_072,
    "qwen-plus": 131_072,
    "qwen-turbo": 131_072,
    "qwq": 131_072,
    # MIMO
    "mimo": 131_072,
}

# Response token budgets by context size
RESPONSE_TOKEN_BUDGETS = {
    1_048_576: 32_768,   # 1M context → 32K response
    200_000: 16_384,     # 200K → 16K
    131_072: 8_192,      # 131K → 8K
    128_000: 8_192,      # 128K → 8K
    65_536: 4_096,       # 65K → 4K
    32_768: 4_096,       # 32K → 4K
}


def get_model_context_config(model_name: str) -> tuple[int, int]:
    """Return (context_window, max_response_tokens) for a model."""
    model_lower = model_name.lower()
    context_window = 32_768  # default
    for pattern, window in MODEL_CONTEXT_WINDOWS.items():
        if pattern in model_lower:
            context_window = window
            break
    # Find appropriate response budget
    max_response = 4_096  # default
    for threshold, budget in sorted(RESPONSE_TOKEN_BUDGETS.items(), reverse=True):
        if context_window >= threshold:
            max_response = budget
            break
    return context_window, max_response


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed CJK/English."""
    if not text:
        return 0
    # Count CJK characters (≈2 tokens each) vs ASCII (≈0.25 tokens each)
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    ascii_chars = len(text) - cjk
    return cjk * 2 + max(1, ascii_chars // 4)


def truncate_messages_by_tokens(messages: list[dict], max_input_tokens: int) -> list[dict]:
    """Truncate message history to fit within token budget, keeping recent messages."""
    if not messages:
        return messages

    # Always keep the first message (system prompt or first user message)
    result = []
    total_tokens = 0

    # Walk backwards from most recent
    for msg in reversed(messages):
        content = msg.get("content") or ""
        msg_tokens = estimate_tokens(content)
        # Add overhead for tool_calls JSON
        if "tool_calls" in msg:
            msg_tokens += estimate_tokens(json.dumps(msg["tool_calls"]))
        if total_tokens + msg_tokens > max_input_tokens and result:
            break
        result.append(msg)
        total_tokens += msg_tokens

    result.reverse()
    return result

DEFAULT_SYSTEM_PROMPT = """You are Hermes, an AI assistant with access to tools for file operations, terminal commands, and web search.

When the user asks you to:
- Read/write/create files → use read_file / write_file / list_files
- Search for code or text → use search_files
- Run commands → use terminal
- Look up information online → use web_search / web_extract

Always use tools when needed. Be proactive — don't just say "I can't do that" when tools are available.
Respond in the user's language. Be concise and helpful."""


class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_LENGTH)
    session_id: Optional[str] = None
    model: Optional[str] = "default"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    system_prompt: Optional[str] = None
    thinking_mode: Optional[str] = None
    thinking_budget: Optional[int] = None
    proxy_url: Optional[str] = None


class SessionCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


def _create_session(name: Optional[str] = None) -> dict:
    sid = str(uuid.uuid4())
    session = {
        "id": sid,
        "name": name or f"Session {sid[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "messages": [],
        "last_access": datetime.now(timezone.utc).timestamp(),
    }
    _sessions[sid] = session
    # LRU eviction: remove least-recently-accessed session when over limit
    if len(_sessions) > MAX_SESSIONS:
        oldest_id = min(_sessions, key=lambda k: _sessions[k].get("last_access", 0))
        logger.info("Evicting session %s (LRU, %d sessions)", oldest_id[:8], len(_sessions))
        del _sessions[oldest_id]
    return session


_create_session("Default Session")


async def _call_provider_with_tools(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    session_id: Optional[str] = None,
    proxy_url: Optional[str] = None,
    thinking_mode: Optional[str] = None,
    thinking_budget: Optional[int] = None,
    max_tokens: int = 4096,
):
    """Call provider with tool calling loop.

    Yields SSE events: token, tool_call, tool_result, done, error.
    """
    url = base_url.rstrip("/")
    if not url.endswith("/v1") and "/v1/" not in url:
        url = f"{url}/v1"
    chat_url = f"{url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    tools = openai_tools()
    current_messages = list(messages)
    full_response = ""

    for round_num in range(MAX_TOOL_ROUNDS):
        if round_num >= 20:
            logger.warning("Tool calling round %d/%d — approaching limit", round_num + 1, MAX_TOOL_ROUNDS)
        body: dict = {
            "model": model,
            "messages": current_messages,
            "stream": True,
            "max_tokens": max_tokens,
        }

        if tools:
            body["tools"] = tools

        if thinking_mode and thinking_mode != "off" and thinking_budget:
            body["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

        logger.info("Round %d: Calling %s model=%s with %d messages, %d tools",
                     round_num + 1, chat_url, model, len(current_messages), len(tools))

        client_kwargs: dict = {"timeout": httpx.Timeout(120.0, connect=15.0)}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        else:
            client_kwargs["trust_env"] = True

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                async with client.stream("POST", chat_url, headers=headers, json=body) as resp:
                    if resp.status_code != 200:
                        error_body = b""
                        async for chunk in resp.aiter_bytes():
                            error_body += chunk
                        error_text = error_body.decode("utf-8", errors="replace")[:500]
                        logger.error("Provider error %d: %s", resp.status_code, error_text)
                        yield {"event": "error", "data": f"Provider error {resp.status_code}: {error_text}"}
                        return

                    # Collect the full response to check for tool calls
                    full_content = ""
                    tool_calls_map: dict[int, dict] = {}  # index -> {id, name, arguments_str}
                    has_tool_calls = False
                    thinking_content = ""

                    buffer = ""
                    async for raw_chunk in resp.aiter_text():
                        buffer += raw_chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            if line == "data: [DONE]":
                                continue
                            if not line.startswith("data: "):
                                continue

                            data_str = line[6:]
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            choices = data.get("choices", [])
                            if not choices:
                                continue

                            delta = choices[0].get("delta", {})

                            # Handle reasoning content
                            reasoning = delta.get("reasoning_content", "")
                            if reasoning:
                                thinking_content += reasoning
                                yield {"event": "thinking", "data": reasoning}

                            # Handle text content
                            content = delta.get("content", "")
                            if content:
                                full_content += content
                                yield {"event": "token", "data": content}

                            # Handle tool calls
                            tc_list = delta.get("tool_calls", [])
                            if tc_list:
                                has_tool_calls = True
                                for tc in tc_list:
                                    idx = tc.get("index", 0)
                                    if idx not in tool_calls_map:
                                        tool_calls_map[idx] = {
                                            "id": tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                                            "name": "",
                                            "arguments_str": "",
                                        }
                                    if tc.get("id"):
                                        tool_calls_map[idx]["id"] = tc["id"]
                                    fn = tc.get("function", {})
                                    if fn.get("name"):
                                        tool_calls_map[idx]["name"] = fn["name"]
                                    if fn.get("arguments"):
                                        tool_calls_map[idx]["arguments_str"] += fn["arguments"]

        except httpx.ConnectError as e:
            yield {"event": "error", "data": f"连接失败: {e}"}
            return
        except httpx.TimeoutException:
            yield {"event": "error", "data": "请求超时 (120秒)"}
            return
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)
            yield {"event": "error", "data": f"错误: {e}"}
            return

        # If no tool calls, we're done — the tokens were already streamed
        if not has_tool_calls:
            yield {"event": "done", "data": ""}
            return

        # ─── Execute tool calls ───
        # Add assistant message with tool calls to history
        assistant_msg: dict = {"role": "assistant", "content": full_content or None}
        assistant_tool_calls = []
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            assistant_tool_calls.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments_str"]},
            })
        assistant_msg["tool_calls"] = assistant_tool_calls
        current_messages.append(assistant_msg)

        # 保存 assistant 消息（带 tool_calls）到 session history
        if session_id:
            async with _session_lock:
                _sessions[session_id]["messages"].append({
                    "role": "assistant",
                    "content": full_content or None,
                    "tool_calls": assistant_tool_calls,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        # Execute tools concurrently with timeout
        async def _run_one(idx: int, tc: dict):
            tool_name = tc["name"]
            args_str = tc["arguments_str"]
            call_id = tc["id"]
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}
            try:
                result = await asyncio.wait_for(
                    execute_tool(tool_name, args), timeout=60
                )
            except asyncio.TimeoutError:
                result = f"Error: tool {tool_name} timed out after 60 seconds"
            return idx, call_id, tool_name, args, result

        # ─── Notify frontend: tool calls starting ───
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            args = {}
            try:
                args = json.loads(tc["arguments_str"]) if tc["arguments_str"] else {}
            except json.JSONDecodeError:
                pass
            yield {"event": "tool_call", "data": json.dumps({
                "id": tc["id"], "name": tc["name"], "args": args
            })}

        tasks = [_run_one(idx, tc) for idx, tc in sorted(tool_calls_map.items())]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        for item in results_list:
            if isinstance(item, Exception):
                logger.error("Tool execution exception: %s", item)
                continue
            idx, call_id, tool_name, args, result = item

            logger.info("Tool %s result: %s...", tool_name, result[:200])

            # Notify frontend
            yield {"event": "tool_result", "data": json.dumps({
                "id": call_id, "name": tool_name, "result": result[:5000]
            })}

            # Add tool result to messages
            current_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result[:10000],
            })

            # 保存工具结果到 session history
            if session_id:
                async with _session_lock:
                    _sessions[session_id]["messages"].append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result[:10000],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

    # Exceeded max rounds — try one final call without tools to get a summary
    logger.warning("Exceeded max tool rounds (%d), requesting final summary", MAX_TOOL_ROUNDS)
    yield {"event": "token", "data": f"\n\n⚠️ 已达到最大工具调用轮次({MAX_TOOL_ROUNDS})，正在总结...\n\n"}
    try:
        summary_body: dict = {
            "model": model,
            "messages": current_messages + [{"role": "user", "content": "请根据上面的工具执行结果，给出最终回复。不要再调用任何工具。"}],
            "stream": True,
            "max_tokens": 4096,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            async with client.stream("POST", chat_url, headers=headers, json=summary_body) as resp:
                if resp.status_code == 200:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield {"event": "token", "data": content}
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        logger.error("Final summary call failed: %s", e)
        yield {"event": "error", "data": f"工具调用轮次已耗尽({MAX_TOOL_ROUNDS}轮)，且最终总结失败"}

    yield {"event": "done", "data": ""}


@router.post("/api/chat")
async def chat(message: ChatMessage, request: Request):
    """Stream a chat response via SSE with tool calling support."""
    if len(message.content) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=413, detail="Content too large")

    # Resolve or create session
    async with _session_lock:
        session_id = message.session_id
        if not session_id or session_id not in _sessions:
            session = _create_session()
            session_id = session["id"]
        # Update LRU access time
        _sessions[session_id]["last_access"] = datetime.now(timezone.utc).timestamp()
        _sessions[session_id]["messages"].append({
            "role": "user",
            "content": message.content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Build message history with model-aware context window
    history = _sessions[session_id]["messages"]
    api_messages = []

    # Resolve provider settings early (needed for context config)
    base_url = message.base_url
    api_key = message.api_key
    model = message.model or "default"

    # System prompt
    sys_prompt = message.system_prompt or DEFAULT_SYSTEM_PROMPT
    api_messages.append({"role": "system", "content": sys_prompt})

    # Auto-adjust context based on model
    context_window, max_response = get_model_context_config(model)
    # Reserve tokens: system prompt + response + safety margin
    system_tokens = estimate_tokens(sys_prompt)
    max_input_tokens = context_window - max_response - system_tokens - 500  # 500 token safety

    logger.info("Context config: model=%s, context_window=%d, max_response=%d, max_input=%d, history=%d msgs",
                model, context_window, max_response, max_input_tokens, len(history))

    recent = truncate_messages_by_tokens(history, max_input_tokens)
    for m in recent:
        msg = {"role": m["role"], "content": m["content"]}
        # 保留 tool_calls（assistant 消息）
        if "tool_calls" in m:
            msg["tool_calls"] = m["tool_calls"]
        # 保留 tool_call_id（tool 消息）
        if "tool_call_id" in m:
            msg["tool_call_id"] = m["tool_call_id"]
        api_messages.append(msg)

    # Fallback: echo mode if no provider
    if not base_url or not api_key:
        async def echo_stream():
            yield {"event": "token", "data": f"⚠️ 未配置 API 密钥。请在设置中添加供应商和密钥。\n\nEcho: {message.content}"}
            yield {"event": "done", "data": ""}

        async def echo_gen():
            full = ""
            try:
                async for ev in echo_stream():
                    if await request.is_disconnected():
                        break
                    if ev["event"] == "token":
                        full += ev["data"]
                    yield ev
            finally:
                if full:
                    async with _session_lock:
                        _sessions[session_id]["messages"].append({
                            "role": "assistant", "content": full,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

        return EventSourceResponse(echo_gen(), ping=15, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        })

    # Real provider call with tool loop
    async def event_generator():
        full_response = ""
        try:
            async for event in _call_provider_with_tools(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=api_messages,
                session_id=session_id,
                proxy_url=message.proxy_url,
                thinking_mode=message.thinking_mode,
                thinking_budget=message.thinking_budget,
                max_tokens=max_response,
            ):
                if await request.is_disconnected():
                    break
                if event["event"] == "token":
                    full_response += event["data"]
                yield event
        except asyncio.CancelledError:
            pass
        finally:
            if full_response:
                async with _session_lock:
                    _sessions[session_id]["messages"].append({
                        "role": "assistant", "content": full_response,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

    return EventSourceResponse(event_generator(), ping=15, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Accel-Buffering": "no",
    })


# ─── Session management ───

@router.get("/api/sessions")
async def list_sessions():
    return [
        {"id": s["id"], "name": s["name"], "created_at": s["created_at"],
         "message_count": len(s["messages"])}
        for s in _sessions.values()
    ]


@router.post("/api/sessions")
async def create_session(body: SessionCreate):
    async with _session_lock:
        return _create_session(body.name)


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    async with _session_lock:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        del _sessions[session_id]
    return {"deleted": session_id}
