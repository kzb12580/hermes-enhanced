"""Memory API — persistent memory store, injected into every conversation."""

import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("hermes-backend.memory")
router = APIRouter()

# Persistent storage
_MEMORY_DIR = Path.home() / ".hermes" / "desktop"
_MEMORY_FILE = _MEMORY_DIR / "memories.json"

MAX_MEMORIES = 500


def _load_memories() -> dict:
    if _MEMORY_FILE.exists():
        try:
            return json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_memories(memories: dict):
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _MEMORY_FILE.write_text(json.dumps(memories, indent=2, ensure_ascii=False), encoding="utf-8")


# Load on startup
_memories: dict[str, dict] = _load_memories()
logger.info("Loaded %d memories from %s", len(_memories), _MEMORY_FILE)


def get_memory_context(max_chars: int = 3000) -> str:
    """Get memory context string to inject into system prompt."""
    if not _memories:
        return ""
    
    # Sort by created_at descending, take recent entries
    sorted_mems = sorted(_memories.values(), key=lambda m: m.get("created_at", ""), reverse=True)
    
    lines = []
    total = 0
    for mem in sorted_mems:
        content = mem.get("content", "")
        if total + len(content) > max_chars:
            break
        lines.append(f"- {content}")
        total += len(content)
    
    if not lines:
        return ""
    
    return "\n\n## User Context (from memory)\n" + "\n".join(lines)


class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="user", max_length=100)


@router.get("/api/memories")
async def list_memories():
    return list(_memories.values())


@router.post("/api/memories")
async def save_memory(body: MemoryCreate):
    mid = str(uuid.uuid4())
    memory = {
        "id": mid,
        "content": body.content,
        "tags": body.tags,
        "source": body.source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _memories[mid] = memory
    if len(_memories) > MAX_MEMORIES:
        sorted_ids = sorted(_memories, key=lambda k: _memories[k].get("created_at", ""))
        for old_id in sorted_ids[: len(_memories) - MAX_MEMORIES]:
            del _memories[old_id]
    _save_memories(_memories)
    return memory


@router.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str):
    if memory_id not in _memories:
        raise HTTPException(status_code=404, detail="Memory not found")
    del _memories[memory_id]
    _save_memories(_memories)
    return {"deleted": memory_id}


@router.delete("/api/memories")
async def clear_memories():
    _memories.clear()
    _save_memories(_memories)
    return {"cleared": True}
