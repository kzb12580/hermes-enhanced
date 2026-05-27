"""Memory API — store, list, and delete memories."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-memory store (replace with vector DB / file storage later)
_memories: dict[str, dict] = {}


class MemoryCreate(BaseModel):
    content: str
    tags: list[str] = []
    source: str = "user"


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
        "created_at": datetime.utcnow().isoformat(),
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
