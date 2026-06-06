"""Session tools — search and recall past conversations."""

from __future__ import annotations

import json
from .base import BaseTool
from . import register


class SearchSessionTool(BaseTool):
    name = "search_session"
    description = "Search past conversation sessions by keyword. Use when user references something from a previous conversation, or when you need to recall what was discussed before."
    timeout = 15
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keywords to search for in past sessions"},
            "limit": {"type": "integer", "description": "Max sessions to return (default 5)", "default": 5},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, limit: int = 5, **kwargs) -> str:
        try:
            from api.session_manager import SessionManager
            sm = SessionManager()
            sessions_list = sm.list_sessions()

            results = []
            query_lower = query.lower()

            for sinfo in sessions_list:
                sid = sinfo["id"]
                # Re-fetch full session to access messages
                session = sm.get_session(sid)
                if not session:
                    continue

                messages = session.get("messages", [])
                matched = False
                snippets = []

                for msg in messages:
                    content = msg.get("content", "")
                    if isinstance(content, str) and query_lower in content.lower():
                        matched = True
                        # Get a snippet around the match
                        idx = content.lower().find(query_lower)
                        start = max(0, idx - 50)
                        end = min(len(content), idx + len(query) + 50)
                        snippets.append(content[start:end])
                        if len(snippets) >= 3:
                            break

                if matched:
                    results.append({
                        "session_id": sid,
                        "name": sinfo.get("name", ""),
                        "created_at": sinfo.get("created_at", ""),
                        "message_count": sinfo.get("message_count", 0),
                        "snippets": snippets,
                    })

                if len(results) >= limit:
                    break

            return json.dumps({"found": len(results), "sessions": results}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"found": 0, "error": str(e)}, ensure_ascii=False)


class GetSessionHistoryTool(BaseTool):
    name = "get_session_history"
    description = "Get the last N messages from the current session. Use to recall what was discussed earlier in THIS conversation."
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of recent messages to return (default 10)", "default": 10},
        },
    }

    async def execute(self, count: int = 10, **kwargs) -> str:
        try:
            from api.session_manager import SessionManager
            sm = SessionManager()
            sessions_list = sm.list_sessions()

            if not sessions_list:
                return json.dumps({"messages": []}, ensure_ascii=False)

            # Get the latest session by created_at
            latest_info = max(sessions_list, key=lambda s: s.get("created_at", 0) or 0)
            session = sm.get_session(latest_info["id"])
            if not session:
                return json.dumps({"messages": []}, ensure_ascii=False)

            messages = session.get("messages", [])

            # Return last N messages, truncated
            recent = messages[-count:] if len(messages) > count else messages
            result = []
            for msg in recent:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 300:
                    content = content[:300] + "..."
                result.append({"role": role, "content": content})

            return json.dumps({"session_name": session.get("name", ""), "total": len(messages), "returned": len(result), "messages": result}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


