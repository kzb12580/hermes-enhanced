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
    description = "Create a task plan before starting complex work. Break large tasks into steps. Use this FIRST when user gives a multi-step task."
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
                "description": "List of tasks with id, content, status",
            },
        },
        "required": ["tasks"],
    }

    async def execute(self, tasks: list[dict] = None, **kwargs) -> str:
        global _todos
        # Accept both 'tasks' and 'todos' as parameter name (LLM sometimes uses 'todos')
        task_list = tasks or kwargs.get("todos", [])
        if not task_list:
            return json.dumps({"ok": False, "error": "No tasks provided"}, ensure_ascii=False)
        _todos = task_list
        return json.dumps(
            {"ok": True, "total": len(_todos), "tasks": _todos},
            ensure_ascii=False,
        )


class TodoUpdateTool(BaseTool):
    name = "todo_update"
    description = "Update task status. Mark tasks as in_progress, completed, or failed. Track your progress."
    timeout = 5
    parameters = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "ID of the task to update",
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
    description = "List all current tasks and their status. Use to check progress or report to user."
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


register(TodoCreateTool())
register(TodoUpdateTool())
register(TodoListTool())
