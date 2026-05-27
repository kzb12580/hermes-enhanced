"""Chat API with SSE streaming support."""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

# In-memory session storage (replace with persistent storage later)
_sessions: dict[str, dict] = {}
_session_lock = asyncio.Lock()

# Max request body size (1 MB)
MAX_CONTENT_LENGTH = 1 * 1024 * 1024


class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_LENGTH)
    session_id: Optional[str] = None
    model: Optional[str] = "default"


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


# Auto-create a default session so the API is immediately usable
_create_session("Default Session")


# ---------------------------------------------------------------------------
# SSE streaming chat
# ---------------------------------------------------------------------------

async def _mock_stream(content: str):
    """Yield SSE events simulating a token-by-token response."""
    response_text = f"Echo: {content}"
    for char in response_text:
        yield {"event": "token", "data": char}
        await asyncio.sleep(0.02)  # simulate latency
    yield {"event": "done", "data": ""}


@router.post("/api/chat")
async def chat(message: ChatMessage, request: Request):
    """Stream a chat response via Server-Sent Events."""
    # Validate content length
    if len(message.content) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=413, detail="Content too large")

    # Resolve or create session (under lock to prevent races)
    async with _session_lock:
        session_id = message.session_id
        if not session_id or session_id not in _sessions:
            session = _create_session()
            session_id = session["id"]

        # Record user message
        _sessions[session_id]["messages"].append({
            "role": "user",
            "content": message.content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def event_generator():
        full_response = ""
        try:
            async for event in _mock_stream(message.content):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                if event["event"] == "token":
                    full_response += event["data"]
                yield event
        except asyncio.CancelledError:
            # Client disconnected — stop gracefully
            pass
        finally:
            # Record whatever assistant response we accumulated
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
    """List all chat sessions (without full message history)."""
    return [
        {"id": s["id"], "name": s["name"], "created_at": s["created_at"],
         "message_count": len(s["messages"])}
        for s in _sessions.values()
    ]


# FIX #1: Add _session_lock to create_session to prevent races
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
