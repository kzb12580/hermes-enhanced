"""Todo tools — task planning and progress tracking for complex tasks."""

from __future__ import annotations

import json
import time
from .base import BaseTool
from . import register

# In-memory todo list per session (reset on restart)
_todos: list[dict] = []


class TodoCreateTool(BaseTool):
    name = "todo_create"
    description = "在开始复杂工作前创建任务计划，把大任务拆成步骤。用户提出多步骤任务时优先使用。"
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "failed"],
                            "default": "pending",
                        },
                    },
                    "required": ["id", "content"],
                },
                "description": "任务列表，每项包含 id、content、status",
            },
        },
        "required": ["tasks"],
    }

    async def execute(self, tasks: list[dict] = None, **kwargs) -> str:
        global _todos
        # Accept both 'tasks' and 'todos' as parameter name (LLM sometimes uses 'todos')
        task_list = tasks or kwargs.get("todos", [])
        # LLM may pass tasks as a JSON string instead of a list
        if isinstance(task_list, str):
            try:
                task_list = json.loads(task_list)
            except (json.JSONDecodeError, ValueError):
                return json.dumps({"ok": False, "error": "tasks must be a list of objects, got invalid JSON string"}, ensure_ascii=False)
        if not task_list:
            return json.dumps({"ok": False, "error": "No tasks provided"}, ensure_ascii=False)
        _todos = task_list
        return json.dumps(
            {"ok": True, "total": len(_todos), "tasks": _todos},
            ensure_ascii=False,
        )


class TodoUpdateTool(BaseTool):
    name = "todo_update"
    description = "更新任务状态，可标记为 in_progress、completed 或 failed，用于跟踪进度。"
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "要更新的任务 ID",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "failed"],
            },
        },
        "required": ["task_id", "status"],
    }

    async def execute(self, task_id: str, status: str, **kwargs) -> str:
        for t in _todos:
            if t["id"] == task_id:
                t["status"] = status
                return json.dumps(
                    {"ok": True, "task": t}, ensure_ascii=False
                )
        return json.dumps(
            {"ok": False, "error": f"Task {task_id} not found"},
            ensure_ascii=False,
        )


class TodoListTool(BaseTool):
    name = "todo_list"
    description = "列出当前所有任务及其状态，用于检查进度或向用户汇报。"
    timeout = 5
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        if not _todos:
            return json.dumps({"total": 0, "tasks": []}, ensure_ascii=False)
        completed = sum(1 for t in _todos if t.get("status") == "completed")
        return json.dumps(
            {"total": len(_todos), "completed": completed, "tasks": _todos},
            ensure_ascii=False,
        )


