"""Memory tools — allow the AI to save, search, and manage persistent memories (thread-safe)."""

from __future__ import annotations

import json
import threading
from .base import BaseTool
from . import register

# Import the lock from memory module
_memory_lock = None


def _get_memory_lock():
    """Lazy import of memory lock to avoid circular imports."""
    global _memory_lock
    if _memory_lock is None:
        from api.memory import _memory_lock as lock
        _memory_lock = lock
    return _memory_lock


class SaveMemoryTool(BaseTool):
    name = "save_memory"
    description = "保存重要信息到长期记忆。用于记住用户偏好、事实、纠正信息或用户希望跨会话保留的内容。"
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要保存到记忆的信息，请具体且简洁。",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选标签，用于分类（例如 ['preference', 'user-info']）",
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
        
        lock = _get_memory_lock()
        with lock:
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
    description = "按关键词搜索长期记忆，用于回忆已保存的用户信息或历史对话内容。"
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "要在记忆中搜索的关键词",
            },
        },
        "required": ["keyword"],
    }

    async def execute(self, keyword: str, **kwargs) -> str:
        from api.memory import _memories

        lock = _get_memory_lock()
        with lock:
            results = []
            keyword_lower = keyword.lower()
            for mid, mem in _memories.items():
                content = mem.get("content", "").lower()
                tags = [t.lower() for t in mem.get("tags", [])]
                if keyword_lower in content or any(keyword_lower in t for t in tags):
                    results.append({
                        "id": mid,
                        "content": mem.get("content", ""),
                        "tags": mem.get("tags", []),
                        "created_at": mem.get("created_at", ""),
                    })
        
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return json.dumps({"results": results[:20], "total": len(results)}, ensure_ascii=False)


class DeleteMemoryTool(BaseTool):
    name = "delete_memory"
    description = "删除指定的长期记忆条目。"
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "要删除的记忆 ID",
            },
        },
        "required": ["memory_id"],
    }

    async def execute(self, memory_id: str, **kwargs) -> str:
        from api.memory import _memories, _save_memories

        lock = _get_memory_lock()
        with lock:
            if memory_id in _memories:
                del _memories[memory_id]
                _save_memories(_memories)
                return json.dumps({"ok": True, "message": f"已删除记忆 {memory_id}"}, ensure_ascii=False)
            else:
                return json.dumps({"ok": False, "error": f"记忆 {memory_id} 不存在"}, ensure_ascii=False)
