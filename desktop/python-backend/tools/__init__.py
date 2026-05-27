"""Tool registry — discovers, registers, and dispatches tools."""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool

logger = logging.getLogger("hermes-backend.tools")

# Global registry
_tools: dict[str, BaseTool] = {}


def register(tool: BaseTool) -> None:
    """Register a tool instance."""
    _tools[tool.name] = tool
    logger.info("Registered tool: %s", tool.name)


def get_tool(name: str) -> BaseTool | None:
    return _tools.get(name)


def all_tools() -> list[BaseTool]:
    return list(_tools.values())


def openai_tools() -> list[dict]:
    """Return all tools in OpenAI function-calling format."""
    return [t.to_openai_tool() for t in _tools.values()]


async def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool by name. Returns result string or error string."""
    tool = _tools.get(name)
    if not tool:
        return f"Error: Unknown tool '{name}'"
    try:
        result = await tool.execute(**arguments)
        return result
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return f"Error executing {name}: {e}"


# ─── Auto-register all tools ───

def _auto_register():
    """Import all tool modules to trigger registration."""
    from .file_tools import ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool
    from .terminal_tools import TerminalTool
    from .web_tools import WebSearchTool, WebExtractTool

    for tool_cls in [
        ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool,
        TerminalTool,
        WebSearchTool, WebExtractTool,
    ]:
        register(tool_cls())


_auto_register()
