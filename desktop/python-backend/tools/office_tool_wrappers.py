"""Office tool wrappers — register office functions as LLM-callable tools."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from .base import BaseTool


class OfficeToolWrapper(BaseTool):
    """Wraps an office function as a BaseTool for LLM calling."""

    def __init__(self, name: str, description: str, fn, parameters: dict, timeout: int = 120):
        self._name = name
        self._description = description
        self._fn = fn
        self._parameters = parameters
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs) -> str:
        # Run sync function in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._fn(**kwargs))
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return str(result)


# ─── Office Tool Definitions ────────────────────────────────────────────────

OFFICE_TOOL_DEFINITIONS = [
    OfficeToolWrapper(
        name="create_word",
        description="创建Word文档。支持自定义标题、内容、模板、字体大小和行距。",
        fn=None,  # Will be set during registration
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径，如 /tmp/report.docx"},
                "title": {"type": "string", "description": "文档标题"},
                "content": {"type": "string", "description": "文档正文内容（支持Markdown格式）"},
                "template": {"type": "string", "description": "模板文件路径（可选）"},
                "font_size": {"type": "integer", "description": "字体大小，默认12", "default": 12},
                "line_spacing": {"type": "number", "description": "行距，默认1.5", "default": 1.5},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="edit_word",
        description="编辑已有Word文档。支持插入、替换、删除段落等操作。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Word文件路径"},
                "operations": {
                    "type": "array",
                    "description": "操作列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["insert", "replace", "delete_paragraph", "add_heading", "add_table", "add_paragraph", "add_image", "add_page_break", "set_header", "set_footer", "add_toc"], "description": "操作类型"},
                            "text": {"type": "string", "description": "内容文本"},
                            "index": {"type": "integer", "description": "段落位置"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["path", "operations"],
        },
    ),
    OfficeToolWrapper(
        name="read_word",
        description="读取Word文档内容，返回文本和表格数据。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Word文件路径"},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="create_ppt",
        description="创建PPT演示文稿。支持多种主题（business/tech/modern/minimal/nature）、图表、表格。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径，如 /tmp/slides.pptx"},
                "slides": {
                    "type": "array",
                    "description": "幻灯片列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["title", "content", "two_column", "image", "chart", "table", "blank", "section", "bullet", "end"], "description": "幻灯片类型"},
                            "title": {"type": "string", "description": "标题"},
                            "content": {"type": "string", "description": "内容（支持换行分隔）"},
                            "left": {"type": "string", "description": "左栏内容（two_column类型）"},
                            "right": {"type": "string", "description": "右栏内容（two_column类型）"},
                            "image_path": {"type": "string", "description": "图片路径（image类型）"},
                            "data": {"type": "object", "description": "图表数据（chart类型），含 categories 和 series"},
                            "rows": {"type": "array", "description": "表格行数据（table类型）"},
                            "headers": {"type": "array", "items": {"type": "string"}, "description": "表格表头（table类型）"},
                        },
                        "required": ["type"],
                    },
                },
                "template": {"type": "string", "description": "模板文件路径（可选）"},
                "theme": {"type": "string", "description": "主题: business/tech/modern/minimal/nature", "default": "business"},
            },
            "required": ["path", "slides"],
        },
    ),
    OfficeToolWrapper(
        name="create_excel",
        description="创建Excel表格。支持多工作表、表头、数据。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径，如 /tmp/data.xlsx"},
                "sheets": {
                    "type": "array",
                    "description": "工作表列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "工作表名称"},
                            "headers": {"type": "array", "items": {"type": "string"}, "description": "表头"},
                            "data": {"type": "array", "items": {"type": "array"}, "description": "数据行"},
                        },
                        "required": ["name", "data"],
                    },
                },
            },
            "required": ["path", "sheets"],
        },
    ),
    OfficeToolWrapper(
        name="read_excel",
        description="读取Excel文件内容，返回指定工作表的数据。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Excel文件路径"},
                "sheet_name": {"type": "string", "description": "工作表名（空=读取所有）", "default": ""},
                "max_rows": {"type": "integer", "description": "最大读取行数", "default": 1000},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="edit_excel",
        description="编辑已有Excel文件。支持设置单元格、添加公式、图表、格式化等操作。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Excel文件路径"},
                "operations": {
                    "type": "array",
                    "description": "操作列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["set_cell", "set_range", "add_sheet", "delete_sheet", "add_chart", "add_formula", "format_cells", "auto_filter"],
                                "description": "操作类型",
                            },
                            "row": {"type": "integer", "description": "行号"},
                            "col": {"type": "integer", "description": "列号"},
                            "value": {"description": "单元格值"},
                            "data": {"type": "array", "description": "批量数据"},
                            "start_row": {"type": "integer"},
                            "start_col": {"type": "integer"},
                            "name": {"type": "string", "description": "工作表名"},
                            "chart_type": {"type": "string", "enum": ["bar", "line", "pie"]},
                            "data_ref": {"type": "object"},
                            "cats_ref": {"type": "object"},
                            "title": {"type": "string"},
                            "formula": {"type": "string"},
                            "range": {"type": "string"},
                            "bold": {"type": "boolean"},
                            "color": {"type": "string"},
                            "bg_color": {"type": "string"},
                            "sheet": {"type": "string"},
                            "position": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["path", "operations"],
        },
    ),
]
