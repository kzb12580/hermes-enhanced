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
        # Run sync function in thread pool — filter kwargs to function signature
        import inspect
        try:
            sig = inspect.signature(self._fn)
            valid_params = set(sig.parameters.keys())
            filtered = {k: v for k, v in kwargs.items() if k in valid_params}
        except (ValueError, TypeError):
            filtered = kwargs
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._fn(**filtered))
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return str(result)


# ─── Office Tool Definitions ────────────────────────────────────────────────
# OfficeCLI 版本 — 支持动画、渲染预览、完整OOXML

OFFICE_TOOL_DEFINITIONS = [
    # ═══════════════════════════════════════════════════════════════════════
    # Word 工具
    # ═══════════════════════════════════════════════════════════════════════
    OfficeToolWrapper(
        name="create_word",
        description="创建Word文档（OfficeCLI引擎）。支持自定义标题、内容、模板。",
        fn=None,  # Will be set during registration
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径，如 /tmp/report.docx"},
                "title": {"type": "string", "description": "文档标题"},
                "content": {"type": "string", "description": "文档正文内容"},
                "template": {"type": "string", "description": "模板文件路径（可选）"},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="read_word",
        description="读取Word文档内容，返回文本和结构信息。",
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
        name="edit_word",
        description="编辑已有Word文档。支持插入、替换段落等操作。",
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
                            "type": {"type": "string", "enum": ["add_heading", "add_paragraph", "replace", "add_image"], "description": "操作类型"},
                            "text": {"type": "string", "description": "内容文本"},
                            "index": {"type": "integer", "description": "段落位置"},
                            "level": {"type": "integer", "description": "标题级别(1-6)"},
                            "new": {"type": "string", "description": "替换后文本"},
                            "image_path": {"type": "string", "description": "图片路径"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["path", "operations"],
        },
    ),
    
    # ═══════════════════════════════════════════════════════════════════════
    # Excel 工具
    # ═══════════════════════════════════════════════════════════════════════
    OfficeToolWrapper(
        name="create_excel",
        description="创建Excel表格（OfficeCLI引擎）。支持多工作表、表头、数据。",
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
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "行单元格数据"
                                },
                                "description": "数据行"
                            },
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
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="edit_excel",
        description="编辑已有Excel文件。支持设置单元格、添加公式、工作表等。",
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
                            "type": {"type": "string", "enum": ["set_cell", "set_range", "add_sheet", "add_formula"], "description": "操作类型"},
                            "row": {"type": "integer", "description": "行号"},
                            "col": {"type": "integer", "description": "列号"},
                            "value": {"description": "单元格值"},
                            "formula": {"type": "string", "description": "公式"},
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "行单元格数据"
                                },
                                "description": "批量数据"
                            },
                            "name": {"type": "string", "description": "工作表名"},
                            "sheet": {"type": "string", "description": "目标工作表"},
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["path", "operations"],
        },
    ),
    
    # ═══════════════════════════════════════════════════════════════════════
    # PowerPoint 工具 — 支持动画！
    # ═══════════════════════════════════════════════════════════════════════
    OfficeToolWrapper(
        name="create_ppt",
        description="""创建PPT（OfficeCLI引擎，支持元素动画！）。
坐标单位为英寸：16x9页面=10×5.625，wide页面=13.333×7.5。
动画支持：入场(fade/fly/zoom/wipe/bounce)、退出(contract/floatOut)、强调(spin/grow)、运动路径(line/arc/circle)。
""",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径，如 /tmp/slides.pptx"},
                "title": {"type": "string", "description": "演示文稿标题（可选）"},
                "author": {"type": "string", "description": "作者（可选）"},
                "slides_file": {"type": "string", "description": "slides JSON文件路径（>5页推荐）"},
                "slides": {
                    "type": "array",
                    "description": "幻灯片列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "background": {"type": "object", "description": "背景色"},
                            "elements": {
                                "type": "array",
                                "description": "页面元素",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["text", "shape", "image", "chart", "table"], "description": "元素类型"},
                                        "text": {"description": "文本内容"},
                                        "x": {"type": "number", "description": "X位置（英寸）"},
                                        "y": {"type": "number", "description": "Y位置（英寸）"},
                                        "w": {"type": "number", "description": "宽度（英寸）"},
                                        "h": {"type": "number", "description": "高度（英寸）"},
                                        "fontSize": {"type": "integer", "description": "字号"},
                                        "color": {"type": "string", "description": "文字颜色"},
                                        "bold": {"type": "boolean", "description": "加粗"},
                                        "fill": {"type": "object", "description": "填充色"},
                                        "shape": {"type": "string", "enum": ["rect", "oval", "line", "rounded_rect"], "description": "形状类型"},
                                        "chartType": {"type": "string", "enum": ["bar", "line", "pie"], "description": "图表类型"},
                                        "rows": {
                                            "type": "array",
                                            "items": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                                "description": "表格行数据"
                                            },
                                            "description": "表格数据"
                                        },
                                    },
                                    "required": ["type"],
                                },
                            },
                            "animations": {
                                "type": "array",
                                "description": "动画列表（OfficeCLI支持！）",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "shape_index": {"type": "integer", "description": "目标形状索引（从0开始）"},
                                        "effect": {"type": "string", "enum": ["appear", "fade", "fly", "zoom", "wipe", "bounce", "float", "swivel", "spin", "grow", "wave"], "description": "动画效果"},
                                        "class": {"type": "string", "enum": ["entrance", "exit", "emphasis", "motion"], "description": "动画类别"},
                                        "duration": {"type": "integer", "description": "持续时间（毫秒）", "default": 500},
                                        "trigger": {"type": "string", "enum": ["onClick", "withPrevious", "afterPrevious"], "description": "触发方式"},
                                        "direction": {"type": "string", "enum": ["in", "out", "left", "right", "up", "down"], "description": "方向"},
                                        "delay": {"type": "integer", "description": "延迟（毫秒）"},
                                    },
                                    "required": ["shape_index", "effect", "class"],
                                },
                            },
                        },
                        "required": ["elements"],
                    },
                },
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="add_ppt_animation",
        description="为PPT元素添加动画。支持入场/退出/强调/运动路径动画。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "PPT文件路径"},
                "slide_index": {"type": "integer", "description": "幻灯片索引（从1开始）"},
                "shape_index": {"type": "integer", "description": "形状索引（从1开始）"},
                "effect": {"type": "string", "enum": ["appear", "fade", "fly", "zoom", "wipe", "bounce", "float", "swivel", "spin", "grow", "wave"], "description": "动画效果"},
                "anim_class": {"type": "string", "enum": ["entrance", "exit", "emphasis", "motion"], "description": "动画类别"},
                "duration": {"type": "integer", "description": "持续时间（毫秒）", "default": 500},
                "trigger": {"type": "string", "enum": ["onClick", "withPrevious", "afterPrevious"], "description": "触发方式", "default": "onClick"},
                "direction": {"type": "string", "description": "方向"},
                "delay": {"type": "integer", "description": "延迟（毫秒）"},
            },
            "required": ["path", "slide_index", "shape_index", "effect", "anim_class"],
        },
    ),
    
    # ═══════════════════════════════════════════════════════════════════════
    # 渲染预览工具
    # ═══════════════════════════════════════════════════════════════════════
    OfficeToolWrapper(
        name="render_office",
        description="渲染Office文档为HTML或PNG预览图。让AI能'看到'文档效果。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Office文件路径"},
                "output": {"type": "string", "description": "输出路径（可选）"},
                "format": {"type": "string", "enum": ["html", "png"], "description": "输出格式", "default": "html"},
                "slide": {"type": "integer", "description": "PPT指定幻灯片（0=全部）", "default": 0},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="get_office_info",
        description="获取Office文档结构信息（大纲视图）。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Office文件路径"},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="validate_ppt",
        description="验证PPT结构完整性。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "PPT文件路径"},
            },
            "required": ["path"],
        },
    ),
]
