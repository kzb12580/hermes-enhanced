"""Memory API — store, list, and delete memories."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

# In-memory store (replace with vector DB / file storage later)
_memories: dict[str, dict] = {}


class MemoryCreate(BaseModel):
    # FIX: Add min_length/max_length constraints
    content: str = Field(..., min_length=1, max_length=10000)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="user", max_length=100)


@router.get("/api/memories")
async def list_memories():
    """Return all stored memories."""
    return list(_memories.values())


@router.post("/api/memories")
async def save_memory(body: MemoryCreate):
    """Save a new memory entry."""
    mid = str(uuid.uuid4())
    memory = {
        "id": mid,
        "content": body.content,
        "tags": body.tags,
        "source": body.source,
        # FIX: Use datetime.now(timezone.utc) instead of deprecated datetime.utcnow()
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _memories[mid] = memory
    return memory


@router.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory by ID."""
    if memory_id not in _memories:
        raise HTTPException(status_code=404, detail="Memory not found")
    del _memories[memory_id]
    return {"deleted": memory_id}
