"""Chat API with SSE streaming — proxies to OpenAI-compatible providers."""

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

logger = logging.getLogger("hermes-backend.chat")
router = APIRouter()

# In-memory session storage
_sessions: dict[str, dict] = {}
_session_lock = asyncio.Lock()

MAX_CONTENT_LENGTH = 1 * 1024 * 1024


class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_LENGTH)
    session_id: Optional[str] = None
    model: Optional[str] = "default"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking_mode: Optional[str] = None
    thinking_budget: Optional[int] = None


class SessionCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


def _create_session(name: Optional[str] = None) -> dict:
    sid = str(uuid.uuid4())
    session = {
        "id": sid,
        "name": name or f"Session {sid[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "messages": [],
    }
    _sessions[sid] = session
    return session


# Auto-create a default session
_create_session("Default Session")


async def _call_provider_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    thinking_mode: Optional[str] = None,
    thinking_budget: Optional[int] = None,
):
    """Call an OpenAI-compatible /v1/chat/completions endpoint with streaming."""
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    chat_url = f"{url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    body: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": 4096,
    }

    # Add thinking/reasoning params if supported
    if thinking_mode and thinking_mode != "off":
        if thinking_budget:
            body["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    logger.info("Calling %s model=%s", chat_url, model)

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
        async with client.stream("POST", chat_url, headers=headers, json=body) as resp:
            if resp.status_code != 200:
                error_body = b""
                async for chunk in resp.aiter_bytes():
                    error_body += chunk
                error_text = error_body.decode("utf-8", errors="replace")[:500]
                logger.error("Provider error %d: %s", resp.status_code, error_text)
                yield {
                    "event": "error",
                    "data": f"Provider error {resp.status_code}: {error_text}",
                }
                return

            # Parse SSE stream from provider
            buffer = ""
            async for raw_chunk in resp.aiter_text():
                buffer += raw_chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        if line == "data: [DONE]":
                            yield {"event": "done", "data": ""}
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                reasoning = delta.get("reasoning_content", "")
                                if reasoning:
                                    yield {"event": "thinking", "data": reasoning}
                                if content:
                                    yield {"event": "token", "data": content}
                        except json.JSONDecodeError:
                            continue

            # If we get here without [DONE], send done anyway
            yield {"event": "done", "data": ""}


@router.post("/api/chat")
async def chat(message: ChatMessage, request: Request):
    """Stream a chat response via Server-Sent Events."""
    if len(message.content) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=413, detail="Content too large")

    # Resolve or create session
    async with _session_lock:
        session_id = message.session_id
        if not session_id or session_id not in _sessions:
            session = _create_session()
            session_id = session["id"]
        _sessions[session_id]["messages"].append({
            "role": "user",
            "content": message.content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Build message history for the provider
    history = _sessions[session_id]["messages"]
    api_messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Determine provider credentials
    base_url = message.base_url
    api_key = message.api_key
    model = message.model or "default"

    # Fallback: echo mode if no provider configured
    if not base_url or not api_key:
        logger.warning("No provider configured, using echo mode")
        async def echo_stream():
            response_text = f"Echo: {message.content}"
            for char in response_text:
                yield {"event": "token", "data": char}
                await asyncio.sleep(0.02)
            yield {"event": "done", "data": ""}

        async def echo_generator():
            full_response = ""
            try:
                async for event in echo_stream():
                    if await request.is_disconnected():
                        break
                    if event["event"] == "token":
                        full_response += event["event"]
                    yield event
            finally:
                if full_response:
                    async with _session_lock:
                        _sessions[session_id]["messages"].append({
                            "role": "assistant",
                            "content": f"Echo: {message.content}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

        return EventSourceResponse(echo_generator(), ping=15, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        })

    # Real provider call
    async def event_generator():
        full_response = ""
        try:
            async for event in _call_provider_stream(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=api_messages,
                thinking_mode=message.thinking_mode,
                thinking_budget=message.thinking_budget,
            ):
                if await request.is_disconnected():
                    break
                if event["event"] == "token":
                    full_response += event["data"]
                yield event
        except asyncio.CancelledError:
            pass
        except httpx.ConnectError as e:
            logger.error("Connection error: %s", e)
            yield {"event": "error", "data": f"连接失败: {e}"}
        except httpx.TimeoutException:
            logger.error("Request timeout")
            yield {"event": "error", "data": "请求超时 (120秒)"}
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)
            yield {"event": "error", "data": f"错误: {e}"}
        finally:
            if full_response:
                async with _session_lock:
                    _sessions[session_id]["messages"].append({
                        "role": "assistant",
                        "content": full_response,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Accel-Buffering": "no",
    }
    return EventSourceResponse(event_generator(), ping=15, headers=headers)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@router.get("/api/sessions")
async def list_sessions():
    """List all chat sessions."""
    return [
        {"id": s["id"], "name": s["name"], "created_at": s["created_at"],
         "message_count": len(s["messages"])}
        for s in _sessions.values()
    ]


@router.post("/api/sessions")
async def create_session(body: SessionCreate):
    """Create a new chat session."""
    async with _session_lock:
        return _create_session(body.name)


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    async with _session_lock:
        if session_id not in _sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        del _sessions[session_id]
    return {"deleted": session_id}
