"""
Hermes Desktop GUI 自动化工具集
屏幕截图 + 视觉定位 + 鼠标键盘控制
"""
import io
import os
import time
import json
import logging
import subprocess
from typing import Optional
from pathlib import Path

_log = logging.getLogger(__name__)

# ── 全局单例 ────────────────────────────────────────────────────────────────
_worker = None

def get_worker():
    global _worker
    if _worker is None:
        from locate_anything_worker import LocateAnythingWorker
        _worker = LocateAnythingWorker()
    return _worker


# ═══════════════════════════════════════════════════════════════════════════
# Tool 1: screen_capture — 截图
# ═══════════════════════════════════════════════════════════════════════════

def screen_capture(region: str = "full", save_path: str = "") -> dict:
    """
    截取屏幕截图

    Args:
        region: "full"=全屏, "active"=当前窗口, "x,y,w,h"=指定区域
        save_path: 保存路径（可选，默认 /tmp/screen.png）

    Returns:
        {"path": "/tmp/screen.png", "size": [1920, 1080]}
    """
    try:
        from PIL import ImageGrab
        if region == "full":
            img = ImageGrab.grab()
        elif region == "active":
            import pygetwindow as gw
            win = gw.getActiveWindow()
            if win:
                bbox = (win.left, win.top, win.right, win.bottom)
                img = ImageGrab.grab(bbox)
            else:
                img = ImageGrab.grab()
        else:
            x, y, w, h = map(int, region.split(","))
            img = ImageGrab.grab((x, y, x + w, y + h))

        path = save_path or "/tmp/hermes_screen.png"
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        img.save(path)
        return {"path": path, "size": [img.width, img.height], "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 2: gui_locate — 视觉定位
# ═══════════════════════════════════════════════════════════════════════════

def gui_locate(image_path: str, target: str, task: str = "gui") -> dict:
    """
    用 LocateAnything-3B 定位屏幕上的元素

    Args:
        image_path: 截图路径
        target: 要找的元素描述（如 "保存按钮", "搜索输入框", "File菜单"）
        task: "gui"=GUI元素, "text"=文字, "detect"=目标检测, "point"=指向

    Returns:
        {"found": true, "boxes": [{"x1":100,"y1":200,"x2":300,"y2":250,"center_x":200,"center_y":225}],
         "click_target": {"x":200,"y":225}}
    """
    try:
        from PIL import Image
        worker = get_worker()
        img = Image.open(image_path).convert("RGB")

        if task == "gui":
            boxes = worker.gui_locate(img, target)
        elif task == "text":
            boxes = worker.ground_text(img, target)
        elif task == "detect":
            boxes = worker.detect(img, [target])
        elif task == "point":
            points = worker.point(img, target)
            if points:
                return {
                    "found": True,
                    "points": [{"x": x, "y": y} for x, y in points],
                    "click_target": {"x": points[0][0], "y": points[0][1]},
                    "success": True,
                }
            return {"found": False, "success": True}
        else:
            return {"error": f"Unknown task: {task}", "success": False}

        if not boxes:
            return {"found": False, "success": True, "message": f"未找到: {target}"}

        result_boxes = []
        for b in boxes:
            cx, cy = b.center
            result_boxes.append({
                "x1": b.x1, "y1": b.y1, "x2": b.x2, "y2": b.y2,
                "center_x": cx, "center_y": cy,
                "width": b.width, "height": b.height,
            })

        # 选最大的框作为点击目标
        best = max(boxes, key=lambda b: b.width * b.height)
        cx, cy = best.center
        return {
            "found": True,
            "count": len(boxes),
            "boxes": result_boxes,
            "click_target": {"x": cx, "y": cy},
            "success": True,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 3: gui_click — 鼠标点击
# ═══════════════════════════════════════════════════════════════════════════

def gui_click(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.1) -> dict:
    """
    在指定位置点击鼠标

    Args:
        x, y: 屏幕坐标
        button: "left", "right", "middle"
        clicks: 点击次数（2=双击）
        interval: 多次点击间隔
    """
    try:
        import pyautogui
        pyautogui.FAILSAFE = True  # 鼠标移到左上角紧急停止
        pyautogui.click(x, y, clicks=clicks, button=button, interval=interval)
        return {"clicked": [x, y], "button": button, "clicks": clicks, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 4: gui_type — 键盘输入
# ═══════════════════════════════════════════════════════════════════════════

def gui_type(text: str, interval: float = 0.02, press_enter: bool = False) -> dict:
    """
    模拟键盘输入文字

    Args:
        text: 要输入的文字
        interval: 按键间隔
        press_enter: 输入后是否按回车
    """
    try:
        import pyautogui
        pyautogui.typewrite(text, interval=interval) if text.isascii() else pyautogui.write(text)
        if press_enter:
            pyautogui.press("enter")
        return {"typed": text[:50] + "..." if len(text) > 50 else text, "success": True}
    except Exception as e:
        # 中文输入用剪贴板方式
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            if press_enter:
                pyautogui.press("enter")
            return {"typed": text[:50] + "..." if len(text) > 50 else text, "method": "clipboard", "success": True}
        except Exception as e2:
            return {"error": str(e2), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 5: gui_hotkey — 快捷键
# ═══════════════════════════════════════════════════════════════════════════

def gui_hotkey(*keys: str) -> dict:
    """
    执行快捷键组合

    Args:
        keys: 按键名称，如 "ctrl", "s" 或 "alt", "f4"
    """
    try:
        import pyautogui
        pyautogui.hotkey(*keys)
        return {"hotkey": "+".join(keys), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 6: gui_scroll — 滚动
# ═══════════════════════════════════════════════════════════════════════════

def gui_scroll(clicks: int, x: int = 0, y: int = 0) -> dict:
    """滚动鼠标滚轮，正数向上，负数向下"""
    try:
        import pyautogui
        if x and y:
            pyautogui.scroll(clicks, x=x, y=y)
        else:
            pyautogui.scroll(clicks)
        return {"scrolled": clicks, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 7: gui_drag — 拖拽
# ═══════════════════════════════════════════════════════════════════════════

def gui_drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict:
    """从 (x1,y1) 拖拽到 (x2,y2)"""
    try:
        import pyautogui
        pyautogui.moveTo(x1, y1)
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
        return {"dragged": {"from": [x1, y1], "to": [x2, y2]}, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 8: open_app — 启动应用
# ═══════════════════════════════════════════════════════════════════════════

def open_app(name: str, wait: float = 2.0) -> dict:
    """
    启动应用程序

    Args:
        name: 应用名（如 "notepad", "chrome", "word", "powerpoint"）
        wait: 等待启动时间
    """
    try:
        import subprocess
        app_map = {
            "notepad": "notepad.exe",
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "chrome": "chrome.exe",
            "edge": "msedge.exe",
            "word": "WINWORD.EXE",
            "excel": "EXCEL.EXE",
            "powerpoint": "POWERPNT.EXE",
            "calculator": "calc.exe",
            "paint": "mspaint.exe",
        }
        exe = app_map.get(name.lower(), name)
        subprocess.Popen(exe, shell=True)
        time.sleep(wait)
        return {"opened": name, "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 9: get_windows — 获取窗口列表
# ═══════════════════════════════════════════════════════════════════════════

def get_windows() -> dict:
    """获取所有打开的窗口"""
    try:
        import pygetwindow as gw
        windows = []
        for w in gw.getAllWindows():
            if w.title and w.visible:
                windows.append({
                    "title": w.title,
                    "left": w.left, "top": w.top,
                    "width": w.width, "height": w.height,
                    "active": w.isActive,
                })
        return {"windows": windows, "count": len(windows), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 10: clipboard — 剪贴板操作
# ═══════════════════════════════════════════════════════════════════════════

def clipboard(action: str = "get", text: str = "") -> dict:
    """
    剪贴板操作

    Args:
        action: "get"=读取, "set"=写入
        text: set时的文字内容
    """
    try:
        import pyperclip
        if action == "get":
            content = pyperclip.paste()
            return {"content": content, "success": True}
        elif action == "set":
            pyperclip.copy(text)
            return {"set": text[:50], "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 11: screen_ocr — OCR 文字识别
# ═══════════════════════════════════════════════════════════════════════════

def screen_ocr(image_path: str, lang: str = "chi_sim+eng") -> dict:
    """
    OCR 识别图片中的文字

    Args:
        image_path: 图片路径
        lang: 语言（chi_sim=简体中文, eng=英文）
    """
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang)
        return {"text": text.strip(), "success": True}
    except Exception as e:
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 注册 — 适配 Hermes 工具系统
# ═══════════════════════════════════════════════════════════════════════════

GUI_TOOLS = {
    "screen_capture": {
        "fn": screen_capture,
        "concurrency": "read_only",
        "description": "截取屏幕截图，返回图片路径和尺寸",
    },
    "gui_locate": {
        "fn": gui_locate,
        "concurrency": "read_only",
        "description": "用AI视觉定位屏幕上的GUI元素、文字、物体，返回坐标",
    },
    "gui_click": {
        "fn": gui_click,
        "concurrency": "write_serial",
        "description": "在指定屏幕坐标点击鼠标",
    },
    "gui_type": {
        "fn": gui_type,
        "concurrency": "write_serial",
        "description": "模拟键盘输入文字（支持中文）",
    },
    "gui_hotkey": {
        "fn": gui_hotkey,
        "concurrency": "write_serial",
        "description": "执行快捷键组合（如ctrl+s保存）",
    },
    "gui_scroll": {
        "fn": gui_scroll,
        "concurrency": "write_serial",
        "description": "滚动鼠标滚轮",
    },
    "gui_drag": {
        "fn": gui_drag,
        "concurrency": "write_serial",
        "description": "拖拽操作",
    },
    "open_app": {
        "fn": open_app,
        "concurrency": "write_serial",
        "description": "启动应用程序",
    },
    "get_windows": {
        "fn": get_windows,
        "concurrency": "read_only",
        "description": "获取所有打开的窗口列表",
    },
    "clipboard": {
        "fn": clipboard,
        "concurrency": "read_only",
        "description": "读取或写入系统剪贴板",
    },
    "screen_ocr": {
        "fn": screen_ocr,
        "concurrency": "read_only",
        "description": "OCR识别图片中的文字",
    },
}
