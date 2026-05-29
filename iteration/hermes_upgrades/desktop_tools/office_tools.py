"""
Hermes Desktop Office 文档操作工具集
Word / Excel / PPT 创建与编辑
"""

import os
import json
import logging
from typing import Optional

_log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Tool 1: create_word — Word 文档
# ═══════════════════════════════════════════════════════════════════════════

def create_word(path: str, title: str = "", content: str = "", template: str = "") -> dict:
    """
    创建 Word 文档

    Args:
        path: 保存路径（如 /tmp/report.docx）
        title: 文档标题
        content: 正文内容（支持 \n 分段）
        template: 模板路径（可选）
    """
    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document(template) if template else Document()

        if title:
            heading = doc.add_heading(title, level=0)
            heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for para in content.split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        doc.save(path)
        return {"path": path, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


def edit_word(path: str, operations: list[dict]) -> dict:
    """
    编辑 Word 文档

    Args:
        path: 文档路径
        operations: 操作列表，每项包含：
            - {"type": "add_heading", "text": "...", "level": 1}
            - {"type": "add_paragraph", "text": "..."}
            - {"type": "add_table", "rows": [["a","b"],["c","d"]]}
            - {"type": "add_image", "image_path": "...", "width": 5}
            - {"type": "replace", "old": "...", "new": "..."}
    """
    try:
        from docx import Document
        from docx.shared import Inches

        doc = Document(path)

        for op in operations:
            t = op["type"]
            if t == "add_heading":
                doc.add_heading(op["text"], level=op.get("level", 1))
            elif t == "add_paragraph":
                doc.add_paragraph(op["text"])
            elif t == "add_table":
                rows = op["rows"]
                table = doc.add_table(rows=len(rows), cols=len(rows[0]))
                for i, row in enumerate(rows):
                    for j, cell in enumerate(row):
                        table.rows[i].cells[j].text = str(cell)
            elif t == "add_image":
                doc.add_picture(op["image_path"], width=Inches(op.get("width", 5)))
            elif t == "replace":
                for p in doc.paragraphs:
                    if op["old"] in p.text:
                        p.text = p.text.replace(op["old"], op["new"])

        doc.save(path)
        return {"path": path, "operations": len(operations), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 2: create_ppt — PPT 演示文稿
# ═══════════════════════════════════════════════════════════════════════════

def create_ppt(path: str, slides: list[dict], template: str = "") -> dict:
    """
    创建 PPT 演示文稿

    Args:
        path: 保存路径
        slides: 幻灯片列表，每项：
            - {"title": "标题", "content": "要点1\n要点2\n要点3", "layout": "title|content|two_column|image"}
            - {"title": "标题", "left": "左栏内容", "right": "右栏内容", "layout": "two_column"}
            - {"title": "标题", "image_path": "...", "layout": "image"}
        template: 模板路径（可选）
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN

        prs = Presentation(template) if template else Presentation()

        for slide_data in slides:
            layout_name = slide_data.get("layout", "content")
            title_text = slide_data.get("title", "")

            if layout_name == "title":
                layout = prs.slide_layouts[0]  # Title Slide
                slide = prs.slides.add_slide(layout)
                if title_text:
                    slide.shapes.title.text = title_text
                subtitle = slide.placeholders[1]
                subtitle.text = slide_data.get("content", "")

            elif layout_name == "two_column":
                layout = prs.slide_layouts[3]  # Two Content
                slide = prs.slides.add_slide(layout)
                if title_text:
                    slide.shapes.title.text = title_text
                left_box = slide.placeholders[1]
                right_box = slide.placeholders[2]
                left_box.text = slide_data.get("left", "")
                right_box.text = slide_data.get("right", "")

            elif layout_name == "image":
                layout = prs.slide_layouts[5]  # Blank
                slide = prs.slides.add_slide(layout)
                if title_text:
                    from pptx.util import Emu
                    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(1))
                    txBox.text_frame.text = title_text
                if slide_data.get("image_path"):
                    slide.shapes.add_picture(
                        slide_data["image_path"],
                        Inches(1), Inches(1.5), Inches(8), Inches(5)
                    )

            else:  # content
                layout = prs.slide_layouts[1]  # Title and Content
                slide = prs.slides.add_slide(layout)
                if title_text:
                    slide.shapes.title.text = title_text
                body = slide.placeholders[1]
                tf = body.text_frame
                tf.clear()
                for i, line in enumerate(slide_data.get("content", "").split("\n")):
                    if line.strip():
                        if i == 0:
                            tf.text = line.strip()
                        else:
                            p = tf.add_paragraph()
                            p.text = line.strip()
                        # 自动加项目符号
                        if not line.strip().startswith(("•", "-", "–")):
                            tf.paragraphs[-1].level = 0

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        prs.save(path)
        return {"path": path, "slides": len(slides), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 3: create_excel — Excel 表格
# ═══════════════════════════════════════════════════════════════════════════

def create_excel(path: str, sheets: list[dict]) -> dict:
    """
    创建 Excel 表格

    Args:
        path: 保存路径
        sheets: 工作表列表，每项：
            - {"name": "Sheet1", "headers": ["列1","列2"], "data": [["a","b"],["c","d"]]}
            - {"name": "Sheet1", "data": [["a","b"],["c","d"]]}
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill

        wb = Workbook()
        for i, sheet_data in enumerate(sheets):
            if i == 0:
                ws = wb.active
                ws.title = sheet_data.get("name", f"Sheet{i+1}")
            else:
                ws = wb.create_sheet(title=sheet_data.get("name", f"Sheet{i+1}"))

            rows = sheet_data.get("data", [])
            headers = sheet_data.get("headers", [])

            if headers:
                for j, header in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=j, value=header)
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                    cell.font = Font(color="FFFFFF", bold=True)
                start_row = 2
            else:
                start_row = 1

            for r, row_data in enumerate(rows, start_row):
                for c, value in enumerate(row_data, 1):
                    ws.cell(row=r, column=c, value=value)

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        wb.save(path)
        return {"path": path, "sheets": len(sheets), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 注册
# ═══════════════════════════════════════════════════════════════════════════

OFFICE_TOOLS = {
    "create_word": {
        "fn": create_word,
        "concurrency": "write_serial",
        "description": "创建Word文档，支持标题、正文、模板",
    },
    "edit_word": {
        "fn": edit_word,
        "concurrency": "write_serial",
        "description": "编辑Word文档，支持添加标题/段落/表格/图片/替换文字",
    },
    "create_ppt": {
        "fn": create_ppt,
        "concurrency": "write_serial",
        "description": "创建PPT演示文稿，支持标题页/内容页/双栏/图片页",
    },
    "create_excel": {
        "fn": create_excel,
        "concurrency": "write_serial",
        "description": "创建Excel表格，支持多工作表/表头/数据",
    },
}
