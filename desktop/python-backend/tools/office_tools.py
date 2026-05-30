"""
Hermes Desktop Office 工具集 v2 — 真正的办公助手
增强: Excel 编辑/图表、PPT 图表/主题/模板、Word 高级排版
"""
import os
import io
import json
import logging
import shutil
from typing import Optional
from pathlib import Path

_log = logging.getLogger(__name__)

MAX_CONTENT_LEN = 10_000_000
MAX_ROWS = 500_000


def _safe_path(p: str) -> str:
    """路径净化 + 白名单保护"""
    resolved = str(Path(p).resolve())
    # 禁止写入系统目录
    blocked = ('/etc', '/usr', '/bin', '/sbin', '/boot', '/dev', '/proc', '/sys')
    if any(resolved.startswith(d) for d in blocked):
        raise ValueError(f"不允许写入系统路径: {resolved}")
    return resolved


def _check_file(p: str, name: str = "file") -> Optional[dict]:
    if p and not os.path.isfile(p):
        return {"error": f"{name} not found: {p}", "success": False}
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Word 工具
# ═══════════════════════════════════════════════════════════════════════════

def create_word(path: str, title: str = "", content: str = "", template: str = "",
                font_size: int = 12, line_spacing: float = 1.5) -> dict:
    """创建 Word 文档（支持模板、字体、行距）"""
    try:
        if template:
            err = _check_file(template, "template")
            if err: return err
        if len(content) > MAX_CONTENT_LEN:
            return {"error": "Content too large (>10MB)", "success": False}

        from docx import Document
        from docx.shared import Pt, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document(template) if template else Document()

        # 设置默认字体
        style = doc.styles['Normal']
        font = style.font
        font.size = Pt(font_size)
        pf = style.paragraph_format
        pf.line_spacing = line_spacing

        if title:
            heading = doc.add_heading(title, level=0)
            heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for para in content.split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())

        path = _safe_path(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        doc.save(path)
        return {"path": path, "success": True}
    except Exception as e:
        _log.error("create_word failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


def edit_word(path: str, operations: list[dict]) -> dict:
    """编辑 Word 文档"""
    try:
        err = _check_file(path, "document")
        if err: return err
        from docx import Document
        from docx.shared import Inches, Pt, Cm, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        if not isinstance(operations, list):
            return {"error": "operations must be a list", "success": False}
        doc = Document(path)

        for i, op in enumerate(operations):
            t = op.get("type")
            if t is None:
                return {"error": f"Op #{i} missing 'type'", "success": False}

            if t == "add_heading":
                level = max(0, min(op.get("level", 1), 9))
                h = doc.add_heading(op.get("text", ""), level=level)
                if op.get("align") == "center":
                    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif t == "add_paragraph":
                p = doc.add_paragraph(op.get("text", ""))
                if op.get("bold"):
                    for run in p.runs:
                        run.bold = True
                if op.get("font_size"):
                    for run in p.runs:
                        run.font.size = Pt(op["font_size"])
                if op.get("align") == "center":
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif op.get("align") == "right":
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif t == "insert":
                idx = op.get("index", len(doc.paragraphs))
                text = op.get("text", "")
                if idx < len(doc.paragraphs):
                    doc.paragraphs[idx].insert_paragraph_before(text)
                else:
                    doc.add_paragraph(text)
            elif t == "delete_paragraph":
                idx = op.get("index", -1)
                if 0 <= idx < len(doc.paragraphs):
                    p = doc.paragraphs[idx]
                    p._element.getparent().remove(p._element)
                else:
                    return {"error": f"Invalid paragraph index: {idx}", "success": False}
            elif t == "add_table":
                rows = op.get("rows", [])
                if not rows or not rows[0]:
                    return {"error": f"Op #{i}: empty table", "success": False}
                cols = max(len(row) for row in rows)
                table = doc.add_table(rows=len(rows), cols=cols, style=op.get("style", "Table Grid"))
                for r, row_data in enumerate(rows):
                    for c, cell_val in enumerate(row_data):
                        table.rows[r].cells[c].text = str(cell_val)
            elif t == "add_image":
                img_path = op.get("image_path", "")
                err = _check_file(img_path, "image")
                if err: return err
                doc.add_picture(img_path, width=Inches(max(0.1, min(op.get("width", 5), 20))))
            elif t == "add_page_break":
                doc.add_page_break()
            elif t == "replace":
                old, new = op.get("old", ""), op.get("new", "")
                for p in doc.paragraphs:
                    for run in p.runs:
                        if old in run.text:
                            run.text = run.text.replace(old, new)
            elif t == "set_header":
                section = doc.sections[0]
                header = section.header
                header.paragraphs[0].text = op.get("text", "")
            elif t == "set_footer":
                section = doc.sections[0]
                footer = section.footer
                footer.paragraphs[0].text = op.get("text", "")
            elif t == "add_toc":
                # 添加目录域 (TOC)
                from docx.oxml.ns import qn
                from docx.oxml import OxmlElement
                paragraph = doc.add_paragraph()
                run = paragraph.add_run()
                # begin
                fldChar_begin = OxmlElement('w:fldChar')
                fldChar_begin.set(qn('w:fldCharType'), 'begin')
                run._r.append(fldChar_begin)
                # instrText
                instrText = OxmlElement('w:instrText')
                instrText.set(qn('xml:space'), 'preserve')
                instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
                run._r.append(instrText)
                # separate
                fldChar_sep = OxmlElement('w:fldChar')
                fldChar_sep.set(qn('w:fldCharType'), 'separate')
                run._r.append(fldChar_sep)
                # placeholder
                run2 = paragraph.add_run("(请在Word中右键更新目录)")
                # end
                fldChar_end = OxmlElement('w:fldChar')
                fldChar_end.set(qn('w:fldCharType'), 'end')
                run._r.append(fldChar_end)
            else:
                return {"error": f"Unknown op type: {t}", "success": False}

        doc.save(path)
        return {"path": path, "operations": len(operations), "success": True}
    except Exception as e:
        _log.error("edit_word failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


def read_word(path: str) -> dict:
    """读取 Word 文档内容"""
    try:
        err = _check_file(path, "document")
        if err: return err
        from docx import Document
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        tables = []
        for table in doc.tables:
            rows = []
            for row in table.rows:
                rows.append([cell.text for cell in row.cells])
            tables.append(rows)
        return {"paragraphs": paragraphs, "tables": tables, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# PPT 工具 — 增强版：图表、主题、母版
# ═══════════════════════════════════════════════════════════════════════════

# 内置主题色方案
PPT_THEMES = {
    "business": {"primary": "1F4E79", "secondary": "2E75B6", "accent": "FFC000", "bg": "FFFFFF", "text": "333333"},
    "tech": {"primary": "0D1117", "secondary": "21262D", "accent": "58A6FF", "bg": "0D1117", "text": "C9D1D9"},
    "modern": {"primary": "6C63FF", "secondary": "FF6584", "accent": "00D9A6", "bg": "FAFAFA", "text": "2D3436"},
    "minimal": {"primary": "333333", "secondary": "666666", "accent": "E74C3C", "bg": "FFFFFF", "text": "333333"},
    "nature": {"primary": "27AE60", "secondary": "2ECC71", "accent": "F39C12", "bg": "F8F9FA", "text": "2C3E50"},
}


def _get_layout(prs, preferred: int, fallback_name: str = ""):
    """安全获取幻灯片布局，避免索引越界"""
    if preferred < len(prs.slide_layouts):
        return prs.slide_layouts[preferred]
    return prs.slide_layouts[len(prs.slide_layouts) - 1]


def _apply_theme(slide, theme: dict, prs):
    """给幻灯片应用主题色"""
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    # 背景色
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor.from_string(theme["bg"])


def create_ppt(path: str, slides: list[dict], template: str = "",
               theme: str = "business", title_style: str = "default") -> dict:
    """
    创建 PPT 演示文稿

    theme: business / tech / modern / minimal / nature / 或模板文件路径
    slides 支持的类型:
      - title: 封面页
      - content: 标题+内容
      - two_column: 左右分栏
      - image: 图片页
      - chart: 图表页 (bar/line/pie)
      - table: 表格页
      - section: 章节分隔页
      - bullet: 要点列表页
      - end: 结束页
    """
    try:
        if template:
            err = _check_file(template, "template")
            if err: return err

        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

        prs = Presentation(template) if template else Presentation()
        prs.slide_width = Inches(13.333)  # 16:9
        prs.slide_height = Inches(7.5)

        theme_colors = PPT_THEMES.get(theme, PPT_THEMES["business"])

        if not isinstance(slides, list):
            return {"error": "slides must be a list", "success": False}

        for sd in slides:
            layout_type = sd.get("layout", "content")
            title_text = sd.get("title", "")
            subtitle_text = sd.get("subtitle", "")

            # ── 封面页 ──
            if layout_type == "title":
                layout = prs.slide_layouts[0] if prs.slide_layouts else prs.slide_layouts[0]
                slide = prs.slides.add_slide(layout)
                if title_text and slide.shapes.title:
                    slide.shapes.title.text = title_text
                    for para in slide.shapes.title.text_frame.paragraphs:
                        para.alignment = PP_ALIGN.CENTER
                        for run in para.runs:
                            run.font.size = Pt(44)
                            run.font.bold = True
                            run.font.color.rgb = RGBColor.from_string(theme_colors["primary"])
                if subtitle_text and len(slide.placeholders) > 1:
                    slide.placeholders[1].text = subtitle_text
                    for para in slide.placeholders[1].text_frame.paragraphs:
                        para.alignment = PP_ALIGN.CENTER
                        for run in para.runs:
                            run.font.size = Pt(20)
                            run.font.color.rgb = RGBColor.from_string(theme_colors["secondary"])

            # ── 内容页 ──
            elif layout_type == "content":
                slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
                if title_text and slide.shapes.title:
                    slide.shapes.title.text = title_text
                if len(slide.placeholders) > 1:
                    body = slide.placeholders[1]
                    tf = body.text_frame
                    tf.clear()
                    content = sd.get("content", "")
                    for i, line in enumerate(content.split("\n")):
                        if line.strip():
                            if i == 0:
                                tf.text = line.strip()
                            else:
                                p = tf.add_paragraph()
                                p.text = line.strip()
                                p.font.size = Pt(16)

            # ── 要点列表页 ──
            elif layout_type == "bullet":
                slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
                if title_text and slide.shapes.title:
                    slide.shapes.title.text = title_text
                bullets = sd.get("bullets", [])
                if len(slide.placeholders) > 1:
                    body = slide.placeholders[1]
                    tf = body.text_frame
                    tf.clear()
                    for i, bullet in enumerate(bullets):
                        if isinstance(bullet, dict):
                            text = bullet.get("text", "")
                            level = bullet.get("level", 0)
                        else:
                            text = str(bullet)
                            level = 0
                        if i == 0:
                            tf.text = text
                            tf.paragraphs[0].level = level
                        else:
                            p = tf.add_paragraph()
                            p.text = text
                            p.level = level
                            p.font.size = Pt(16 if level == 0 else 14)

            # ── 左右分栏 ──
            elif layout_type == "two_column":
                slide = prs.slides.add_slide(prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0])
                if title_text and slide.shapes.title:
                    slide.shapes.title.text = title_text
                # 左栏
                left_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(5.5), Inches(5))
                tf = left_box.text_frame
                tf.word_wrap = True
                for i, line in enumerate(sd.get("left", "").split("\n")):
                    if line.strip():
                        if i == 0:
                            tf.text = line.strip()
                        else:
                            tf.add_paragraph().text = line.strip()
                # 右栏
                right_box = slide.shapes.add_textbox(Inches(6.5), Inches(1.5), Inches(5.5), Inches(5))
                tf = right_box.text_frame
                tf.word_wrap = True
                for i, line in enumerate(sd.get("right", "").split("\n")):
                    if line.strip():
                        if i == 0:
                            tf.text = line.strip()
                        else:
                            tf.add_paragraph().text = line.strip()

            # ── 图表页 ──
            elif layout_type == "chart":
                slide = prs.slides.add_slide(prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0])
                if title_text:
                    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(12), Inches(0.8))
                    txBox.text_frame.text = title_text
                    for para in txBox.text_frame.paragraphs:
                        for run in para.runs:
                            run.font.size = Pt(28)
                            run.font.bold = True

                chart_type = sd.get("chart_type", "bar")
                chart_data = sd.get("data", {})
                categories = chart_data.get("categories", [])
                series_list = chart_data.get("series", [])

                if categories and series_list:
                    from pptx.chart.data import CategoryChartData
                    chart_data_obj = CategoryChartData()
                    chart_data_obj.categories = categories
                    for s in series_list:
                        chart_data_obj.add_series(s.get("name", ""), s.get("values", []))

                    type_map = {
                        "bar": XL_CHART_TYPE.BAR_CLUSTERED,
                        "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
                        "line": XL_CHART_TYPE.LINE,
                        "pie": XL_CHART_TYPE.PIE,
                        "area": XL_CHART_TYPE.AREA,
                    }
                    xl_type = type_map.get(chart_type)
                    if xl_type is None:
                        return {"error": f"不支持的图表类型: {chart_type}，可选: {list(type_map.keys())}", "success": False}
                    chart_frame = slide.shapes.add_chart(
                        xl_type, Inches(1), Inches(1.5), Inches(11), Inches(5.5), chart_data_obj
                    )
                    chart = chart_frame.chart
                    chart.has_legend = len(series_list) > 1
                    if chart.has_legend:
                        chart.legend.position = XL_LEGEND_POSITION.BOTTOM

            # ── 表格页 ──
            elif layout_type == "table":
                slide = prs.slides.add_slide(prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0])
                if title_text:
                    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(12), Inches(0.8))
                    txBox.text_frame.text = title_text
                    for para in txBox.text_frame.paragraphs:
                        for run in para.runs:
                            run.font.size = Pt(28)
                            run.font.bold = True

                rows_data = sd.get("rows", [])
                headers = sd.get("headers", [])
                if headers:
                    rows_data = [headers] + rows_data
                if rows_data:
                    n_rows = len(rows_data)
                    n_cols = max(len(r) for r in rows_data)
                    table = slide.shapes.add_table(
                        n_rows, n_cols, Inches(0.5), Inches(1.5), Inches(12), Inches(5)
                    ).table
                    for r, row_data in enumerate(rows_data):
                        for c, val in enumerate(row_data):
                            cell = table.cell(r, c)
                            cell.text = str(val)
                            for para in cell.text_frame.paragraphs:
                                para.font.size = Pt(12)
                            if r == 0 and headers:
                                cell.fill.solid()
                                cell.fill.fore_color.rgb = RGBColor.from_string(theme_colors["primary"])
                                for para in cell.text_frame.paragraphs:
                                    for run in para.runs:
                                        run.font.color.rgb = RGBColor(255, 255, 255)
                                        run.font.bold = True

            # ── 章节分隔页 ──
            elif layout_type == "section":
                slide = prs.slides.add_slide(prs.slide_layouts[2] if len(prs.slide_layouts) > 2 else prs.slide_layouts[0])
                if title_text and slide.shapes.title:
                    slide.shapes.title.text = title_text
                    for para in slide.shapes.title.text_frame.paragraphs:
                        para.alignment = PP_ALIGN.CENTER
                        for run in para.runs:
                            run.font.size = Pt(36)
                            run.font.color.rgb = RGBColor.from_string(theme_colors["accent"])

            # ── 结束页 ──
            elif layout_type == "end":
                slide = prs.slides.add_slide(prs.slide_layouts[0] if prs.slide_layouts else prs.slide_layouts[0])
                txBox = slide.shapes.add_textbox(Inches(2), Inches(2.5), Inches(9), Inches(2))
                tf = txBox.text_frame
                tf.text = title_text or "谢谢"
                for para in tf.paragraphs:
                    para.alignment = PP_ALIGN.CENTER
                    for run in para.runs:
                        run.font.size = Pt(48)
                        run.font.bold = True
                        run.font.color.rgb = RGBColor.from_string(theme_colors["primary"])
                if subtitle_text:
                    sub_box = slide.shapes.add_textbox(Inches(2), Inches(4.5), Inches(9), Inches(1))
                    sub_tf = sub_box.text_frame
                    sub_tf.text = subtitle_text
                    for para in sub_tf.paragraphs:
                        para.alignment = PP_ALIGN.CENTER
                        for run in para.runs:
                            run.font.size = Pt(20)
                            run.font.color.rgb = RGBColor.from_string(theme_colors["secondary"])

        path = _safe_path(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        prs.save(path)
        return {"path": path, "slides": len(slides), "success": True}
    except Exception as e:
        _log.error("create_ppt failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Excel 工具 — 增强版：编辑现有文件、图表、公式、格式
# ═══════════════════════════════════════════════════════════════════════════

def create_excel(path: str, sheets: list[dict]) -> dict:
    """创建 Excel 表格"""
    try:
        total_rows = sum(len(s.get("data", [])) for s in sheets)
        if total_rows > MAX_ROWS:
            return {"error": f"Too many rows ({total_rows})", "success": False}

        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = Workbook()
        if not isinstance(sheets, list) or not sheets:
            return {"error": "sheets must be a non-empty list", "success": False}

        for i, sheet_data in enumerate(sheets):
            ws = wb.active if i == 0 else wb.create_sheet()
            ws.title = sheet_data.get("name", f"Sheet{i+1}")

            rows = sheet_data.get("data", [])
            headers = sheet_data.get("headers", [])

            if headers:
                for j, header in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=j, value=header)
                    cell.font = Font(color="FFFFFF", bold=True, size=11)
                    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                start_row = 2
            else:
                start_row = 1

            for r, row_data in enumerate(rows, start_row):
                for c, value in enumerate(row_data, 1):
                    cell = ws.cell(row=r, column=c, value=value)
                    cell.alignment = Alignment(vertical="center")

            # 自动列宽
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = min(max_len + 4, 50)

        path = _safe_path(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        wb.save(path)
        return {"path": path, "sheets": len(sheets), "success": True}
    except Exception as e:
        _log.error("create_excel failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


def read_excel(path: str, sheet_name: str = "", max_rows: int = 1000) -> dict:
    """读取 Excel 文件"""
    try:
        err = _check_file(path, "excel")
        if err: return err
        # 文件大小检查
        file_size = os.path.getsize(path)
        if file_size > 50_000_000:  # 50MB
            return {"error": f"Excel文件过大 ({file_size // 1_000_000}MB > 50MB)", "success": False}
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        sheet_names_cache = list(wb.sheetnames)  # close前缓存
        result = {}
        sheets_to_read = [sheet_name] if sheet_name and sheet_name in sheet_names_cache else sheet_names_cache
        for name in sheets_to_read:
            ws = wb[name]
            rows = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= max_rows:
                    break
                rows.append(list(row))
            result[name] = rows
        wb.close()
        return {"sheets": result, "sheet_names": sheet_names_cache, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


def _safe_ref(ws, ref_dict):
    """Safe Reference builder for openpyxl charts."""
    from openpyxl.chart import Reference
    if not isinstance(ref_dict, dict):
        return Reference(ws, min_col=1, min_row=1, max_col=1, max_row=1)
    return Reference(ws,
        min_row=max(1, ref_dict.get("min_row", 1)),
        max_row=max(1, ref_dict.get("max_row", 1)),
        min_col=max(1, ref_dict.get("min_col", 1)),
        max_col=max(1, ref_dict.get("max_col", 1)))


def edit_excel(path: str, operations: list[dict]) -> dict:
    """
    编辑 Excel 文件

    operations 支持:
      - set_cell: 设置单元格 {row, col, value, sheet}
      - set_range: 批量设置 {start_row, start_col, data, sheet}
      - add_sheet: 添加工作表 {name}
      - delete_sheet: 删除工作表 {name}
      - add_chart: 添加图表 {sheet, chart_type, data_range, title, position}
      - add_formula: 添加公式 {row, col, formula, sheet}
      - format_cells: 格式化 {range, bold, color, bg_color, align, sheet}
      - auto_filter: 添加筛选 {sheet, range}
      - merge_cells: 合并单元格 {range, sheet}
    """
    try:
        err = _check_file(path, "excel")
        if err: return err
        from openpyxl import load_workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.chart import BarChart, LineChart, PieChart, Reference
        from openpyxl.utils import get_column_letter

        wb = load_workbook(path)
        if not isinstance(operations, list):
            return {"error": "operations must be a list", "success": False}

        for i, op in enumerate(operations):
            t = op.get("type")
            if t is None:
                return {"error": f"Op #{i} missing 'type'", "success": False}

            sheet_name = op.get("sheet", wb.sheetnames[0])
            if sheet_name not in wb.sheetnames:
                return {"error": f"Sheet '{sheet_name}' not found", "success": False}
            ws = wb[sheet_name]

            if t == "set_cell":
                ws.cell(row=op["row"], column=op["col"], value=op.get("value"))

            elif t == "set_range":
                data = op.get("data", [])
                sr, sc = op.get("start_row", 1), op.get("start_col", 1)
                for r, row_data in enumerate(data):
                    for c, val in enumerate(row_data):
                        ws.cell(row=sr + r, column=sc + c, value=val)

            elif t == "add_sheet":
                wb.create_sheet(op.get("name", f"Sheet{len(wb.sheetnames)+1}"))

            elif t == "delete_sheet":
                if op.get("name") in wb.sheetnames and len(wb.sheetnames) > 1:
                    del wb[op["name"]]

            elif t == "add_chart":
                chart_types = {"bar": BarChart, "line": LineChart, "pie": PieChart}
                chart_cls = chart_types.get(op.get("chart_type", "bar"), BarChart)
                chart = chart_cls()
                chart.title = op.get("title", "")
                chart.style = 10
                if chart_cls is not PieChart:
                    chart.y_axis.title = op.get("y_axis", "")
                    chart.x_axis.title = op.get("x_axis", "")
                data_ref = _safe_ref(ws, op.get("data_ref", {}))
                cats_ref = _safe_ref(ws, op.get("cats_ref", {}))
                chart.add_data(data_ref, titles_from_data=True)
                chart.set_categories(cats_ref)
                chart.width = op.get("width", 20)
                chart.height = op.get("height", 12)
                pos = op.get("position", "E2")
                ws.add_chart(chart, pos)

            elif t == "add_formula":
                ws.cell(row=op["row"], column=op["col"], value=op.get("formula", ""))

            elif t == "format_cells":
                cell_range = op.get("range", "A1:A1")
                bold = op.get("bold", False)
                font_color = op.get("color")
                bg_color = op.get("bg_color")
                font_size = op.get("font_size", 11)
                for row in ws[cell_range]:
                    for cell in row:
                        if bold or font_color or font_size:
                            cell.font = Font(bold=bold, color=font_color, size=font_size)
                        if bg_color:
                            cell.fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
                        if op.get("align"):
                            cell.alignment = Alignment(horizontal=op["align"])

            elif t == "auto_filter":
                ws.auto_filter.ref = op.get("range", ws.dimensions)

            elif t == "merge_cells":
                ws.merge_cells(op.get("range", "A1:B1"))

            else:
                return {"error": f"Unknown op type: {t}", "success": False}

        wb.save(path)
        return {"path": path, "operations": len(operations), "success": True}
    except Exception as e:
        _log.error("edit_excel failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# 工具注册
# ═══════════════════════════════════════════════════════════════════════════

OFFICE_TOOLS = {
    "create_word": {"fn": create_word, "concurrency": "write_serial", "description": "创建Word文档（支持模板/字体/行距）"},
    "edit_word": {"fn": edit_word, "concurrency": "write_serial", "description": "编辑Word文档"},
    "read_word": {"fn": read_word, "concurrency": "read_parallel", "description": "读取Word文档内容"},
    "create_ppt": {"fn": create_ppt, "concurrency": "write_serial", "description": "创建PPT（支持图表/主题/模板）"},
    "create_excel": {"fn": create_excel, "concurrency": "write_serial", "description": "创建Excel表格"},
    "read_excel": {"fn": read_excel, "concurrency": "read_parallel", "description": "读取Excel文件"},
    "edit_excel": {"fn": edit_excel, "concurrency": "write_serial", "description": "编辑Excel（图表/公式/格式）"},
}
