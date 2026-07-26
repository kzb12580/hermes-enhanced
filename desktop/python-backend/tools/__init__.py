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
    # These modules self-register at import time.
    from .screen_capture_tool import ScreenCaptureTool  # noqa: F401
    from .ocr_tool import OCRTool  # noqa: F401
    from .office_tool_wrappers import OFFICE_TOOL_DEFINITIONS
    from . import office_tools
    from .memory_tools import SaveMemoryTool, SearchMemoryTool, DeleteMemoryTool
    from .session_tools import SearchSessionTool, GetSessionHistoryTool
    from .todo_tools import TodoCreateTool, TodoUpdateTool, TodoListTool
    from .automation_tools import (
        MouseClickTool, MouseMoveTool, MouseDragTool, MouseScrollTool,
        KeyboardTypeTool, KeyboardHotkeyTool, KeyboardPressTool,
        ListWindowsTool, FindWindowTool, BringToFrontTool,
        WaitTool, GetMousePosTool, ScreenSizeTool,
    )
    from .verify_tools import VerifyFileTool, VerifyCommandTool
    from .code_tools import ExecuteCodeTool  # noqa: F401
    from .skill_tools import SaveSkillTool, ListSkillsTool, LoadSkillTool, DeleteSkillTool
    from .page_agent_tool import PageAgentTool

    for tool_cls in [
        ReadFileTool, WriteFileTool, SearchFilesTool, ListFilesTool,
        TerminalTool,
        WebSearchTool, WebExtractTool, PageAgentTool,
        # Memory tools
        SaveMemoryTool, SearchMemoryTool, DeleteMemoryTool,
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
        # Skill tools
        SaveSkillTool, ListSkillsTool, LoadSkillTool, DeleteSkillTool,
    ]:
        try:
            register(tool_cls())
        except Exception as e:
            logger.warning("Failed to register %s: %s", tool_cls.__name__, e)

    # Register office tools — OfficeCLI 优先，fallback 到原生实现
    from . import officecli_tools
    office_fn_map = {
        # OfficeCLI 版本（推荐）
        "create_word": officecli_tools.create_word,
        "read_word": officecli_tools.read_word,
        "edit_word": officecli_tools.edit_word,
        "create_excel": officecli_tools.create_excel,
        "read_excel": officecli_tools.read_excel,
        "edit_excel": officecli_tools.edit_excel,
        "create_ppt": officecli_tools.create_ppt,
        "add_ppt_animation": officecli_tools.add_ppt_animation,
        "render_office": officecli_tools.render_office,
        "get_office_info": officecli_tools.get_office_info,
        "validate_ppt": officecli_tools.validate_ppt,
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
