"""Tool registry — discovers, registers, and dispatches tools."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .base import BaseTool
from logger import get_logger

logger = get_logger("hermes-backend.tools")

# Global registry
_tools: dict[str, BaseTool] = {}


def register(tool: BaseTool) -> None:
    """Register a tool instance."""
    _tools[tool.name] = tool
    logger.info("注册工具: %s", tool.name)


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
        logger.error("未知工具: '%s'", name)
        return f"Error: Unknown tool '{name}'"

    start = time.time()
    # 隐藏大型参数的完整内容
    args_preview = {k: (v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v) for k, v in arguments.items()}
    logger.debug("执行 %s(%s)", name, args_preview)

    try:
        timeout = getattr(tool, "timeout", 60)
        result = await asyncio.wait_for(tool.execute(**arguments), timeout=timeout)
        elapsed = time.time() - start

        if result is None:
            logger.warning("工具 %s 返回 None (%.2fs)", name, elapsed)
            return f"Error: tool '{name}' returned no result"

        logger.debug("工具 %s 完成 (%.2fs) | result_len=%d", name, elapsed, len(result))
        return result

    except asyncio.TimeoutError:
        timeout = getattr(tool, "timeout", 60)
        elapsed = time.time() - start
        logger.error("工具 %s 超时 (%.1fs > %ds)", name, elapsed, timeout)
        return f"Error: tool '{name}' timed out after {timeout}s"
    except Exception as e:
        elapsed = time.time() - start
        logger.error("工具 %s 异常 (%.2fs): %s", name, elapsed, e, exc_info=True)
        return f"Error executing {name}: {e}"


# ─── Auto-register all tools ───

def _auto_register():
    """Import all tool modules to trigger registration."""
    from .file_tools import ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool
    from .terminal_tools import TerminalTool
    from .web_tools import WebSearchTool, WebExtractTool
    from .screen_capture_tool import ScreenCaptureTool
    from .ocr_tool import OCRTool
    from .office_tool_wrappers import OFFICE_TOOL_DEFINITIONS
    from . import office_tools
    from .memory_tools import SaveMemoryTool, SearchMemoryTool, ListMemoryTool, DeleteMemoryTool
    from .session_tools import SearchSessionTool, GetSessionHistoryTool
    from .todo_tools import TodoCreateTool, TodoUpdateTool, TodoListTool
    from .automation_tools import (
        MouseClickTool, MouseMoveTool, MouseDragTool, MouseScrollTool,
        KeyboardTypeTool, KeyboardHotkeyTool, KeyboardPressTool,
        ListWindowsTool, FindWindowTool, BringToFrontTool,
        WaitTool, GetMousePosTool, ScreenSizeTool,
    )
    from .verify_tools import VerifyFileTool, VerifyCommandTool
    from .code_tools import ExecuteCodeTool
    from .skill_tools import SaveSkillTool, ListSkillsTool, LoadSkillTool, DeleteSkillTool

    for tool_cls in [
        ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool,
        TerminalTool,
        WebSearchTool, WebExtractTool,
        ScreenCaptureTool,
        OCRTool,
        # Memory tools
        SaveMemoryTool, SearchMemoryTool, ListMemoryTool, DeleteMemoryTool,
        # Session tools
        SearchSessionTool, GetSessionHistoryTool,
        # Todo tools
        TodoCreateTool, TodoUpdateTool, TodoListTool,
        # Automation tools
        MouseClickTool, MouseMoveTool, MouseDragTool, MouseScrollTool,
        KeyboardTypeTool, KeyboardHotkeyTool, KeyboardPressTool,
        ListWindowsTool, FindWindowTool, BringToFrontTool,
        WaitTool, GetMousePosTool, ScreenSizeTool,
        # Verify tools
        VerifyFileTool, VerifyCommandTool,
        # Code execution
        ExecuteCodeTool,
        # Skill tools
        SaveSkillTool, ListSkillsTool, LoadSkillTool, DeleteSkillTool,
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
        "animate_ppt": office_tools.animate_ppt,
        "list_ppt_shapes": office_tools.list_ppt_shapes,
        "list_anim_effects": office_tools.list_anim_effects,
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
