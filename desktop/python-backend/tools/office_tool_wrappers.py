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
        description="编辑已有Word文档。支持插入、替换、删除段落等操作。⚠️ 批量操作（如插入10+图片）请改用execute_code写Python脚本，避免参数过大截断。",
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
        description="创建PPT（PptxGenJS引擎，支持过渡动画/阴影/透明度/图表/表格）。≤5页直接传slides，>5页先write_file保存JSON再传slides_file避免截断。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "保存路径，如 /tmp/slides.pptx"},
                "layout": {"type": "string", "description": "幻灯片布局: 16x9 / 16x10 / 4x3 / wide", "default": "16x9"},
                "title": {"type": "string", "description": "演示文稿标题（可选）"},
                "author": {"type": "string", "description": "作者（可选）"},
                "slides_file": {"type": "string", "description": "slides JSON文件路径（推荐>5页PPT使用，避免截断）。先write_file保存JSON，再传此参数"},
                "slides": {
                    "type": "array",
                    "description": "幻灯片列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "background": {"type": "object", "description": "背景，如 {\"color\": \"1E2761\"}", "properties": {"color": {"type": "string"}}},
                            "transition": {"type": "object", "description": "过渡动画，如 {\"type\": \"fade\", \"duration\": 1}", "properties": {"type": {"type": "string"}, "duration": {"type": "number"}}},
                            "elements": {
                                "type": "array",
                                "description": "页面元素列表",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["text", "shape", "image", "chart", "table"], "description": "元素类型"},
                                        "text": {"description": "文本内容（string或富文本数组[{text,options}]）"},
                                        "x": {"type": "number", "description": "X位置（英寸）"},
                                        "y": {"type": "number", "description": "Y位置（英寸）"},
                                        "w": {"type": "number", "description": "宽度（英寸）"},
                                        "h": {"type": "number", "description": "高度（英寸）"},
                                        "fontSize": {"type": "integer", "description": "字号"},
                                        "fontFace": {"type": "string", "description": "字体"},
                                        "color": {"type": "string", "description": "文字颜色（6位hex，无#）"},
                                        "bold": {"type": "boolean", "description": "加粗"},
                                        "italic": {"type": "boolean", "description": "斜体"},
                                        "align": {"type": "string", "enum": ["left", "center", "right"], "description": "对齐"},
                                        "valign": {"type": "string", "enum": ["top", "middle", "bottom"], "description": "垂直对齐"},
                                        "bullet": {"type": "boolean", "description": "显示项目符号"},
                                        "fill": {"type": "object", "description": "填充色，如 {\"color\": \"0D9488\"}"},
                                        "shadow": {"type": "object", "description": "阴影，如 {\"type\":\"outer\",\"blur\":6,\"offset\":2,\"color\":\"000000\",\"opacity\":0.15}"},
                                        "shape": {"type": "string", "enum": ["rect", "oval", "line", "rounded_rect"], "description": "形状类型"},
                                        "chartType": {"type": "string", "enum": ["bar", "line", "pie", "doughnut", "scatter", "radar"], "description": "图表类型"},
                                        "data": {"type": "array", "description": "图表数据 [{name,labels,values}]"},
                                        "barDir": {"type": "string", "enum": ["col", "bar"], "description": "柱状图方向"},
                                        "chartColors": {"type": "array", "items": {"type": "string"}, "description": "图表颜色"},
                                        "showValue": {"type": "boolean", "description": "显示数据标签"},
                                        "rows": {"type": "array", "description": "表格行数据"},
                                    },
                                    "required": ["type"],
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
        name="create_excel",
        description="创建Excel表格。支持多工作表、表头、数据。⚠️ 大量数据（>100行）请改用execute_code写Python脚本。",
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
        description="编辑已有Excel文件。支持设置单元格、添加公式、图表、格式化等操作。⚠️ 批量操作（>10个）请改用execute_code写Python脚本。",
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
                                "enum": ["set_cell", "set_range", "add_sheet", "delete_sheet", "add_chart", "add_formula", "format_cells", "auto_filter", "merge_cells"],
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
    OfficeToolWrapper(
        name="animate_ppt",
        description="为PPT添加原生动画效果（入场/退场/强调/幻灯片切换）。支持40+种动画，逐元素编排。先用 list_ppt_shapes 查看形状，再指定动画。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "PPT文件路径"},
                "animations": {
                    "type": "array",
                    "description": "动画列表，每个元素指定一页的动画",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slide": {"type": "integer", "description": "幻灯片页码（从1开始）"},
                            "effect": {
                                "type": "string",
                                "description": "动画效果名称",
                                "enum": [
                                    # 入场动画 (Entrance)
                                    "appear", "fade", "fly_in", "wipe", "zoom",
                                    "float_up", "float_down", "float_left", "float_right",
                                    "split_vertical", "split_horizontal",
                                    "blinds_horizontal", "blinds_vertical",
                                    "checkerboard", "circle", "diamond", "plus",
                                    "dissolve", "random_bars",
                                    "peek_up", "peek_down", "peek_left", "peek_right",
                                    "grow_turn", "swivel", "expand", "spin",
                                    "rise_up", "bouncy", "center_rotate",
                                    "collapse", "stretch", "whip", "compress", "thread",
                                    # 退场动画 (Exit)
                                    "disappear", "fade_out", "fly_out", "wipe_out", "zoom_out",
                                    "float_down_exit", "float_up_exit",
                                    "split_out_v", "split_out_h",
                                    "blinds_out_h", "blinds_out_v",
                                    "dissolve_out", "random_bars_out",
                                    "collapse_exit", "spin_exit",
                                    # 强调动画 (Emphasis)
                                    "pulse", "color_pulse", "grow", "shrink",
                                    "spin_cw", "spin_ccw", "transparency",
                                    "bold_reveal", "underline_reveal",
                                    "desaturate", "darken", "lighten",
                                    "brush_on_color", "grow_color",
                                ],
                            },
                            "target": {
                                "type": "string",
                                "description": "动画目标：'all'(全部), 'all_text'(文本), 'title'(标题), 'body'(正文), 'all_images'(图片), '1,3,5'(指定形状ID)",
                                "default": "all_text",
                            },
                            "duration": {"type": "number", "description": "动画时长（秒），默认0.5", "default": 0.5},
                            "delay": {"type": "number", "description": "延迟时间（秒），默认0", "default": 0},
                            "trigger": {
                                "type": "string",
                                "enum": ["onclick", "withprev", "afterprev"],
                                "description": "触发方式：onclick(点击), withprev(与上一动画同时), afterprev(上一动画之后)",
                                "default": "afterprev",
                            },
                        },
                        "required": ["slide", "effect"],
                    },
                },
                "transitions": {
                    "type": "array",
                    "description": "幻灯片切换效果列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slide": {"type": "integer", "description": "幻灯片页码"},
                            "type": {
                                "type": "string",
                                "description": "切换类型",
                                "enum": ["fade", "push", "wipe", "split", "blinds", "checkerboard",
                                         "circle", "diamond", "dissolve", "cover", "uncover",
                                         "random", "zoom", "grow_and_turn", "flip", "gallery",
                                         "convey", "rotate", "cube", "box", "pan", "glitter",
                                         "honeycomb", "random_bar", "shred", "wind", "morph"],
                            },
                            "duration": {"type": "number", "description": "切换时长（秒）", "default": 1.0},
                            "direction": {
                                "type": "string",
                                "enum": ["up", "down", "left", "right", "horizontal", "vertical"],
                                "description": "切换方向",
                            },
                        },
                        "required": ["slide", "type"],
                    },
                },
                "output": {"type": "string", "description": "输出文件路径（默认在原文件名后加_animated）"},
            },
            "required": ["path", "animations"],
        },
    ),
    OfficeToolWrapper(
        name="list_ppt_shapes",
        description="列出PPT中所有形状的名称和ID，用于 animate_ppt 的 target 参数。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "PPT文件路径"},
                "slide": {"type": "integer", "description": "指定页码（可选，默认列出所有页）"},
            },
            "required": ["path"],
        },
    ),
    OfficeToolWrapper(
        name="list_anim_effects",
        description="列出所有可用的PPT动画效果名称，按类别分组（入场/退场/强调/切换）。",
        fn=None,
        parameters={
            "type": "object",
            "properties": {},
        },
    ),
]
