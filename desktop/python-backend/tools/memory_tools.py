"""Memory tools — allow the AI to save, search, and manage persistent memories."""

from __future__ import annotations

import json
from .base import BaseTool
from . import register


class SaveMemoryTool(BaseTool):
    name = "save_memory"
    description = "Save important information to persistent memory. Use this to remember user preferences, facts, corrections, or anything the user wants you to remember across conversations."
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The information to remember. Be specific and concise.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for categorization (e.g., ['preference', 'user-info'])",
                "default": [],
            },
        },
        "required": ["content"],
    }

    async def execute(self, content: str, tags: list[str] = None, **kwargs) -> str:
        from api.memory import _memories, _save_memories, MAX_MEMORIES
        from datetime import datetime, timezone
        import uuid

        # LLM may pass tags as a JSON string instead of a list
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, ValueError):
                tags = [tags]

        mid = str(uuid.uuid4())
        memory = {
            "id": mid,
            "content": content,
            "tags": tags or [],
            "source": "ai",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _memories[mid] = memory

        # Evict oldest if over limit
        if len(_memories) > MAX_MEMORIES:
            sorted_ids = sorted(_memories, key=lambda k: _memories[k].get("created_at", ""))
            for old_id in sorted_ids[: len(_memories) - MAX_MEMORIES]:
                del _memories[old_id]

        _save_memories(_memories)
        return json.dumps({"ok": True, "id": mid, "message": f"已保存到持久记忆: {content[:100]}"}, ensure_ascii=False)


class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "Search persistent memories by keyword. Use this to recall previously saved information about the user or past conversations."
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "Keyword to search for in memories",
            },
        },
        "required": ["keyword"],
    }

    async def execute(self, keyword: str, **kwargs) -> str:
        from api.memory import _memories

        keyword_lower = keyword.lower()
        results = []
        for mem in _memories.values():
            content = mem.get("content", "")
            tags = " ".join(mem.get("tags", []))
            if keyword_lower in content.lower() or keyword_lower in tags.lower():
                results.append({
                    "id": mem["id"],
                    "content": content,
                    "tags": mem.get("tags", []),
                    "created_at": mem.get("created_at", ""),
                })

        if not results:
            return json.dumps({"found": 0, "results": []}, ensure_ascii=False)

        # Sort by most recent first
        results.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return json.dumps({"found": len(results), "results": results[:20]}, ensure_ascii=False)


class ListMemoryTool(BaseTool):
    name = "list_memories"
    description = "List all saved persistent memories. Use to review what you've remembered about the user."
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, **kwargs) -> str:
        from api.memory import _memories

        if not _memories:
            return json.dumps({"total": 0, "memories": []}, ensure_ascii=False)

        sorted_mems = sorted(_memories.values(), key=lambda m: m.get("created_at", ""), reverse=True)
        result = []
        for mem in sorted_mems[:30]:
            result.append({
                "id": mem["id"],
                "content": mem.get("content", ""),
                "tags": mem.get("tags", []),
                "created_at": mem.get("created_at", ""),
            })

        return json.dumps({"total": len(_memories), "memories": result}, ensure_ascii=False)


class DeleteMemoryTool(BaseTool):
    name = "delete_memory"
    description = "Delete a specific memory by its ID."
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "The ID of the memory to delete",
            },
        },
        "required": ["memory_id"],
    }

    async def execute(self, memory_id: str, **kwargs) -> str:
        from api.memory import _memories, _save_memories

        if memory_id not in _memories:
            return json.dumps({"ok": False, "error": f"Memory {memory_id} not found"}, ensure_ascii=False)

        del _memories[memory_id]
        _save_memories(_memories)
        return json.dumps({"ok": True, "deleted": memory_id}, ensure_ascii=False)


# Register all memory tools
register(SaveMemoryTool())
register(SearchMemoryTool())
register(ListMemoryTool())
register(DeleteMemoryTool())
