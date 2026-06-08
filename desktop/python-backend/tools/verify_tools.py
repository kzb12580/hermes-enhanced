"""Verify tool — check that operations succeeded by reading back results."""

from __future__ import annotations

import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from .base import BaseTool
from . import register


_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _natural_key(name: str) -> list[object]:
    """Natural sort key so slide2.xml comes before slide10.xml."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _xml_texts(root: ET.Element, tag: str) -> list[str]:
    texts: list[str] = []
    for node in root.findall(f".//{tag}", _NS):
        if node.text and node.text.strip():
            texts.append(node.text.strip())
    return texts


def _normalize_search_text(text: str) -> str:
    """Normalize human-visible text for lenient verification.

    Office files often split labels across cells/runs, while users/models pass
    the expected phrase as one continuous string. Keep exact matching available
    first, then compare a whitespace/punctuation-light form to avoid false
    negatives such as sheet name "产品销售汇总" not appearing in cell text.
    """
    return re.sub(r"[\s\u3000:：|｜,，;；._\-—/\\]+", "", text or "").lower()


def _verify_docx_content(zf: zipfile.ZipFile) -> dict:
    if "word/document.xml" not in zf.namelist():
        return {"status": "invalid", "error": "缺少 word/document.xml"}
    root = ET.fromstring(zf.read("word/document.xml"))
    texts = _xml_texts(root, "w:t")
    paragraphs = root.findall(".//w:p", _NS)
    tables = root.findall(".//w:tbl", _NS)
    images = root.findall(".//w:drawing", _NS)
    text = "\n".join(texts)
    return {
        "status": "valid" if texts or tables or images else "empty",
        "paragraphs": len(paragraphs),
        "tables": len(tables),
        "images": len(images),
        "text_items": len(texts),
        "text_chars": len(text),
        "text_sample": text[:500],
        "search_text": text,
    }


def _verify_xlsx_content(zf: zipfile.ZipFile) -> dict:
    names = set(zf.namelist())
    if "xl/workbook.xml" not in names:
        return {"status": "invalid", "error": "缺少 xl/workbook.xml"}

    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in names:
        try:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall(".//main:si", _NS):
                shared_strings.append("".join(_xml_texts(si, "main:t")))
        except Exception:
            shared_strings = []

    workbook_sheet_titles: list[str] = []
    try:
        workbook_root = ET.fromstring(zf.read("xl/workbook.xml"))
        workbook_sheet_titles = [
            sheet.get("name", "").strip()
            for sheet in workbook_root.findall(".//main:sheet", _NS)
            if sheet.get("name", "").strip()
        ]
    except Exception:
        workbook_sheet_titles = []

    sheet_names = sorted(
        (name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")),
        key=_natural_key,
    )
    if not sheet_names:
        return {"status": "invalid", "error": "缺少 xl/worksheets/sheet*.xml"}

    text_values: list[str] = list(workbook_sheet_titles)
    non_empty_cells = 0
    formula_cells = 0
    numeric_cells = 0
    for sheet_name in sheet_names:
        root = ET.fromstring(zf.read(sheet_name))
        for cell in root.findall(".//main:c", _NS):
            value_node = cell.find("main:v", _NS)
            inline_texts = _xml_texts(cell, "main:t")
            formula_node = cell.find("main:f", _NS)
            if formula_node is not None:
                formula_cells += 1
                non_empty_cells += 1
                if formula_node.text:
                    text_values.append("=" + formula_node.text)
                continue
            if inline_texts:
                non_empty_cells += 1
                text_values.extend(inline_texts)
                continue
            if value_node is None or value_node.text is None:
                continue
            non_empty_cells += 1
            value = value_node.text
            if cell.get("t") == "s":
                try:
                    value = shared_strings[int(value)]
                except Exception:
                    pass
            elif cell.get("t") not in {"str", "inlineStr"}:
                numeric_cells += 1
            if str(value).strip():
                text_values.append(str(value).strip())

    text = "\n".join(text_values)
    return {
        "status": "valid" if non_empty_cells else "empty",
        "sheets": len(sheet_names),
        "sheet_names": workbook_sheet_titles,
        "non_empty_cells": non_empty_cells,
        "formula_cells": formula_cells,
        "numeric_cells": numeric_cells,
        "text_items": len(text_values),
        "text_chars": len(text),
        "text_sample": text[:500],
        "search_text": text,
    }



def _verify_pptx_office_compatibility(zf: zipfile.ZipFile) -> dict:
    """Detect OOXML patterns that often make Microsoft PowerPoint repair PPTX files."""
    names = set(zf.namelist())
    issues: list[dict] = []

    notes_files = sorted(
        name for name in names
        if name.startswith("ppt/notesMasters/") or name.startswith("ppt/notesSlides/")
    )
    if notes_files:
        issues.append({
            "type": "pptxgenjs_notes_scaffold",
            "severity": "high",
            "message": "包含 PptxGenJS notesMaster/notesSlide 脚手架，Microsoft PowerPoint 可能每次打开都提示修复",
            "count": len(notes_files),
        })

    if "[Content_Types].xml" in names:
        content_types = zf.read("[Content_Types].xml").decode("utf-8", "replace")
        slide_master_overrides = set(re.findall(r'PartName="(/ppt/slideMasters/[^"]+)"', content_types))
        slide_master_files = {"/" + name for name in names if name.startswith("ppt/slideMasters/") and name.endswith(".xml")}
        phantom = sorted(slide_master_overrides - slide_master_files)
        if phantom:
            issues.append({
                "type": "phantom_slide_master_override",
                "severity": "high",
                "message": "[Content_Types].xml 引用了不存在的 slideMaster，PowerPoint 可能提示修复",
                "items": phantom[:10],
            })

    dangling_notes_rels = []
    for rel_name in sorted(name for name in names if name.startswith("ppt/slides/_rels/") and name.endswith(".xml.rels")):
        xml = zf.read(rel_name).decode("utf-8", "replace")
        if "notesSlide" not in xml:
            continue
        for target in re.findall(r'Target="([^"]*notesSlides/[^"]+)"', xml):
            # Slide rels are under ppt/slides/_rels/, so ../notesSlides/foo.xml
            # resolves to ppt/notesSlides/foo.xml.
            normalized = target.replace("\\", "/")
            if normalized.startswith("../"):
                normalized = "ppt/" + normalized[3:]
            elif not normalized.startswith("ppt/"):
                normalized = "ppt/slides/_rels/" + normalized
            if normalized not in names:
                dangling_notes_rels.append({"rels": rel_name, "target": target})
    if dangling_notes_rels:
        issues.append({
            "type": "dangling_notes_slide_relationship",
            "severity": "high",
            "message": "幻灯片关系文件引用了不存在的 notesSlide，PowerPoint 可能提示修复",
            "items": dangling_notes_rels[:10],
        })

    invalid_presets = []
    for slide_name in sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")):
        xml = zf.read(slide_name).decode("utf-8", "replace")
        for preset in re.findall(r'<a:prstGeom prst="([^"]+)"', xml):
            if preset in {"oval", "roundedRectangle"}:
                invalid_presets.append({"slide": slide_name, "preset": preset})
    if invalid_presets:
        issues.append({
            "type": "invalid_shape_preset",
            "severity": "high",
            "message": "包含 PowerPoint 不兼容的形状 preset",
            "items": invalid_presets[:10],
        })

    return {
        "status": "valid" if not issues else "warning",
        "issues": issues,
    }

def _verify_pptx_content(zf: zipfile.ZipFile) -> dict:
    names = set(zf.namelist())
    if "ppt/presentation.xml" not in names:
        return {"status": "invalid", "error": "缺少 ppt/presentation.xml"}
    slide_names = sorted(
        (name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
        key=_natural_key,
    )
    if not slide_names:
        return {"status": "invalid", "error": "缺少 ppt/slides/slide*.xml"}

    texts: list[str] = []
    pictures = 0
    charts_or_tables = 0
    shapes = 0
    for slide_name in slide_names:
        root = ET.fromstring(zf.read(slide_name))
        texts.extend(_xml_texts(root, "a:t"))
        pictures += len(root.findall(".//p:pic", _NS))
        charts_or_tables += len(root.findall(".//p:graphicFrame", _NS))
        shapes += len(root.findall(".//p:sp", _NS))

    text = "\n".join(texts)
    visible_objects = len(texts) + pictures + charts_or_tables
    compatibility = _verify_pptx_office_compatibility(zf)
    status = "valid" if visible_objects else "empty"
    if compatibility.get("issues"):
        status = "warning" if status == "valid" else status
    return {
        "status": status,
        "office_compatibility": compatibility,
        "slides": len(slide_names),
        "shapes": shapes,
        "pictures": pictures,
        "charts_or_tables": charts_or_tables,
        "text_items": len(texts),
        "text_chars": len(text),
        "text_sample": text[:500],
        "search_text": text,
    }


def _verify_office_content(path: str, ext: str) -> dict:
    """Return objective Office content summary, not aesthetic/semantic judgment."""
    with zipfile.ZipFile(path) as zf:
        if ext == ".docx":
            return _verify_docx_content(zf)
        if ext == ".xlsx":
            return _verify_xlsx_content(zf)
        if ext == ".pptx":
            return _verify_pptx_content(zf)
    return {"status": "skipped"}


def _verify_pptx_layout(path: str) -> dict:
    """检查 PPTX 中元素是否超出页面边界。

    verify_file 原先只校验 Office ZIP/OOXML 结构，无法发现 PPT 内容在页面外。
    这里读取实际 slide XML 中的 a:xfrm 坐标，按 presentation.xml 的页面尺寸校验。
    """
    tol = 20_000  # EMU 容差，约 0.02 英寸，避免浮点/边框微小误差
    issues = []
    checked = 0
    with zipfile.ZipFile(path) as zf:
        try:
            pres_xml = zf.read("ppt/presentation.xml")
            pres_root = ET.fromstring(pres_xml)
            sld_sz = pres_root.find("p:sldSz", _NS)
            if sld_sz is None:
                return {"status": "skipped", "reason": "未找到页面尺寸 ppt/presentation.xml:p:sldSz"}
            slide_w = int(sld_sz.get("cx", "0"))
            slide_h = int(sld_sz.get("cy", "0"))
        except Exception as e:
            return {"status": "error", "error": f"读取页面尺寸失败: {e}"}

        slide_names = sorted(
            name for name in zf.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for slide_idx, slide_name in enumerate(slide_names, 1):
            try:
                root = ET.fromstring(zf.read(slide_name))
            except Exception as e:
                issues.append({"slide": slide_idx, "element": "slide_xml", "error": f"解析失败: {e}"})
                continue

            # 常见可视对象：shape、picture、graphicFrame、connector
            nodes = []
            for tag in ("p:sp", "p:pic", "p:graphicFrame", "p:cxnSp"):
                nodes.extend(root.findall(f".//{tag}", _NS))

            for elem_idx, node in enumerate(nodes, 1):
                xfrm = node.find(".//a:xfrm", _NS)
                if xfrm is None:
                    continue
                off = xfrm.find("a:off", _NS)
                ext = xfrm.find("a:ext", _NS)
                if off is None or ext is None:
                    continue
                try:
                    x = int(off.get("x", "0"))
                    y = int(off.get("y", "0"))
                    w = int(ext.get("cx", "0"))
                    h = int(ext.get("cy", "0"))
                except ValueError:
                    continue
                checked += 1
                over = []
                if x < -tol:
                    over.append("left")
                if y < -tol:
                    over.append("top")
                if x + w > slide_w + tol:
                    over.append("right")
                if y + h > slide_h + tol:
                    over.append("bottom")
                if over:
                    issues.append({
                        "slide": slide_idx,
                        "element": elem_idx,
                        "overflow": over,
                        "x": x, "y": y, "w": w, "h": h,
                        "slide_w": slide_w, "slide_h": slide_h,
                    })
                    if len(issues) >= 20:
                        break
            if len(issues) >= 20:
                break

    return {
        "status": "invalid" if issues else "valid",
        "checked_elements": checked,
        "slide_count": len(slide_names),
        "slide_width_emu": slide_w,
        "slide_height_emu": slide_h,
        "issues": issues,
    }


class VerifyFileTool(BaseTool):
    name = "verify_file"
    description = "验证文件是否存在、结构是否有效，并可选检查可读内容。创建或写入文件后使用，用于确认操作成功。"
    timeout = 10
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要验证的文件路径"},
            "expected_content": {"type": "string", "description": "可选：文件中应包含的字符串；Office 文件会检查内部可读文本", "default": ""},
            "min_size": {"type": "integer", "description": "可选：最小文件大小（字节）。Office 文件优先校验结构和可读内容，不建议用固定大阈值判断质量。", "default": 0},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, expected_content: str = "", min_size: int = 0, **kwargs) -> str:
        # Path safety: reuse file_tools whitelist-based sandbox
        from .file_tools import _resolve_safe_path
        resolved = _resolve_safe_path(path)
        if isinstance(resolved, str):
            return json.dumps({"ok": False, "error": resolved}, ensure_ascii=False)
        path = str(resolved)

        if not os.path.exists(path):
            return json.dumps({"ok": False, "error": f"File not found: {path}"}, ensure_ascii=False)
        
        size = os.path.getsize(path)
        result = {"ok": True, "path": path, "size": size}

        ext = os.path.splitext(path)[1].lower()
        is_office = ext in {".pptx", ".docx", ".xlsx"}
        office_search_text = ""
        if is_office:
            if not zipfile.is_zipfile(path):
                result["ok"] = False
                result["error"] = f"Office 文件结构无效：{ext} 不是有效的 ZIP/OOXML 文件"
            else:
                try:
                    with zipfile.ZipFile(path) as zf:
                        names = set(zf.namelist())
                    required_by_ext = {
                        ".docx": {"[Content_Types].xml", "_rels/.rels", "word/document.xml"},
                        ".xlsx": {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"},
                        ".pptx": {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"},
                    }
                    missing = sorted(required_by_ext[ext] - names)
                    if ext == ".xlsx" and not any(n.startswith("xl/worksheets/sheet") and n.endswith(".xml") for n in names):
                        missing.append("xl/worksheets/sheet*.xml")
                    if ext == ".pptx" and not any(n.startswith("ppt/slides/slide") and n.endswith(".xml") for n in names):
                        missing.append("ppt/slides/slide*.xml")
                    if missing:
                        result["ok"] = False
                        result["error"] = "Office 文件结构缺少必要组件：" + ", ".join(missing)
                    else:
                        result["office_structure"] = "valid"
                        content_result = _verify_office_content(path, ext)
                        office_search_text = content_result.pop("search_text", "") or ""
                        result["office_content"] = content_result
                        if content_result.get("status") == "empty":
                            result["ok"] = False
                            result["error"] = "Office 文件无可读内容或可见对象"
                        elif content_result.get("status") == "invalid":
                            result["ok"] = False
                            result["error"] = content_result.get("error", "Office 内容校验失败")

                        if ext == ".pptx" and result.get("ok", True):
                            layout_result = _verify_pptx_layout(path)
                            result["ppt_layout"] = {k: v for k, v in layout_result.items() if k != "issues"}
                            if layout_result.get("status") == "invalid":
                                result["ok"] = False
                                result["error"] = "PPT 页面元素超出幻灯片范围"
                                result["layout_issues"] = layout_result.get("issues", [])
                            elif layout_result.get("status") == "error":
                                result["ok"] = False
                                result["error"] = layout_result.get("error", "PPT 布局校验失败")
                except Exception as e:
                    result["ok"] = False
                    result["error"] = f"Office 文件结构校验失败：{e}"
        
        if min_size and size < min_size:
            if result.get("office_structure") == "valid":
                result["warning"] = f"文件大小 {size} 字节低于 min_size={min_size}，但 Office 结构有效；请按页数/内容进一步校验。"
            else:
                result["ok"] = False
                result["error"] = f"File too small: {size} bytes (expected >= {min_size})"
        
        if expected_content:
            try:
                if is_office:
                    content = office_search_text
                else:
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                if expected_content not in content and _normalize_search_text(expected_content) not in _normalize_search_text(content):
                    result["ok"] = False
                    result["error"] = "Expected content not found in file"
            except Exception as e:
                result["ok"] = False
                result["error"] = str(e)
        
        return json.dumps(result, ensure_ascii=False)


class VerifyCommandTool(BaseTool):
    name = "verify_command"
    description = "运行验证命令并检查输出。用于验证安装、服务或配置。"
    timeout = 30
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要运行的验证命令"},
            "expected_in_output": {"type": "string", "description": "输出中应出现的字符串", "default": ""},
        },
        "required": ["command"],
    }

    async def execute(self, command: str, expected_in_output: str = "", **kwargs) -> str:
        import asyncio
        # 安全检查：复用 terminal_tools 黑名单
        from .terminal_tools import _check_blocked
        blocked_err = _check_blocked(command)
        if blocked_err:
            return json.dumps({"ok": False, "error": blocked_err}, ensure_ascii=False)
        is_windows = __import__('platform').system() == "Windows"
        if is_windows:
            import shutil
            shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
            utf8_cmd = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + command
            cmd = [shell, "-NoProfile", "-Command", utf8_cmd]
        else:
            cmd = ["bash", "-c", command]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)
            output = stdout.decode('utf-8', errors='replace').strip()
            
            result = {"ok": True, "exit_code": proc.returncode, "output": output[:2000]}
            
            if expected_in_output and expected_in_output not in output:
                result["ok"] = False
                result["error"] = f"Expected '{expected_in_output}' not found in output"
            
            if proc.returncode != 0:
                result["ok"] = False
                result["error"] = stderr.decode('utf-8', errors='replace').strip()[:500]
            
            return json.dumps(result, ensure_ascii=False)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return json.dumps({"ok": False, "error": "Command timed out (25s)"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
