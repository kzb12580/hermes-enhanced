"""Tool registry — discovers, registers, and dispatches tools."""

from __future__ import annotations

import asyncio
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
        timeout = getattr(tool, "timeout", 60)
        return await asyncio.wait_for(tool.execute(**arguments), timeout=timeout)
    except asyncio.TimeoutError:
        timeout = getattr(tool, "timeout", 60)
        return f"Error: tool '{name}' timed out after {timeout}s"
    except Exception as e:
        logger.error("Tool %s failed: %s", name, e, exc_info=True)
        return f"Error executing {name}: {e}"


# ─── Auto-register all tools ───

def _auto_register():
    """Import all tool modules to trigger registration."""
    from .file_tools import ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool
    from .terminal_tools import TerminalTool
    from .web_tools import WebSearchTool, WebExtractTool
    from .vision_tool import VisionTool
    from .screen_capture_tool import ScreenCaptureTool
    from .ocr_tool import OCRTool
    from .office_tool_wrappers import OFFICE_TOOL_DEFINITIONS
    from . import office_tools
    from .memory_tools import SaveMemoryTool, SearchMemoryTool, ListMemoryTool, DeleteMemoryTool
    from .todo_tools import TodoCreateTool, TodoUpdateTool, TodoListTool
    from .automation_tools import (
        MouseClickTool, MouseMoveTool, MouseDragTool, MouseScrollTool,
        KeyboardTypeTool, KeyboardHotkeyTool, KeyboardPressTool,
        ListWindowsTool, FindWindowTool, BringToFrontTool,
        WaitTool, GetMousePosTool, ScreenSizeTool,
    )
    from .verify_tools import VerifyFileTool, VerifyCommandTool

    for tool_cls in [
        ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool,
        TerminalTool,
        WebSearchTool, WebExtractTool,
        VisionTool,
        ScreenCaptureTool,
        OCRTool,
        # Memory tools
        SaveMemoryTool, SearchMemoryTool, ListMemoryTool, DeleteMemoryTool,
        # Todo tools
        TodoCreateTool, TodoUpdateTool, TodoListTool,
        # Automation tools
        MouseClickTool, MouseMoveTool, MouseDragTool, MouseScrollTool,
        KeyboardTypeTool, KeyboardHotkeyTool, KeyboardPressTool,
        ListWindowsTool, FindWindowTool, BringToFrontTool,
        WaitTool, GetMousePosTool, ScreenSizeTool,
        # Verify tools
        VerifyFileTool, VerifyCommandTool,
    ]:
        try:
            register(tool_cls())
        except Exception as e:
            logger.warning("Failed to register %s: %s", tool_cls.__name__, e)

    # Register office tools
    office_fn_map = {
        "create_word": office_tools.create_word,
        "edit_word": office_tools.edit_word,
        "read_word": office_tools.read_word,
        "create_ppt": office_tools.create_ppt,
        "create_excel": office_tools.create_excel,
        "read_excel": office_tools.read_excel,
        "edit_excel": office_tools.edit_excel,
    }
    for wrapper in OFFICE_TOOL_DEFINITIONS:
        try:
            wrapper._fn = office_fn_map.get(wrapper.name)
            if wrapper._fn:
                register(wrapper)
            else:
                logger.warning("Office tool %s has no matching function", wrapper.name)
        except Exception as e:
            logger.warning("Failed to register office tool %s: %s", wrapper.name, e)


_auto_register()
