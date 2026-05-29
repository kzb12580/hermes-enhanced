"""
Hermes Desktop GUI 自动化工具集 — 已修复全部 CRITICAL/HIGH 问题
"""
import io
import math
import os
import re
import sys
import time
import json
import logging
import platform
import threading
import subprocess
from typing import Optional
from pathlib import Path

_log = logging.getLogger(__name__)

# ── 全局安全设置 ────────────────────────────────────────────────────────────
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05  # 每次操作后暂停50ms
except ImportError:
    _log.warning("pyautogui not installed, GUI tools unavailable")

# ── 全局单例（线程安全）────────────────────────────────────────────────────
_worker = None
_worker_lock = threading.Lock()

def get_worker():
    """获取 LocateAnything worker（双重检查锁）"""
    global _worker
    if _worker is None:
        with _worker_lock:
            if _worker is None:
                from locate_anything_worker import LocateAnythingWorker
                _worker = LocateAnythingWorker()
    return _worker

# ── 剪贴板锁 ─────────────────────────────────────────────────────────────
_clipboard_lock = threading.Lock()

# ── 平台检测 ─────────────────────────────────────────────────────────────
_IS_MAC = platform.system() == "Darwin"
_PASTE_KEY = ("command", "v") if _IS_MAC else ("ctrl", "v")


def _validate_coords(x: int, y: int, name: str = "coords") -> Optional[dict]:
    """验证坐标是否合理"""
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return {"error": f"{name}: x,y must be numbers", "success": False}
    if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
        return {"error": f"{name}: NaN/Inf not allowed", "success": False}
    if x < -1 or y < -1:
        return {"error": f"{name}: negative coords not allowed ({x},{y})", "success": False}
    if x > 10000 or y > 10000:
        return {"error": f"{name}: coords too large ({x},{y})", "success": False}
    return None


def _safe_path(p: str, allowed_dir: str = "") -> str:
    """路径安全检查，防止路径遍历"""
    resolved = Path(p).resolve()
    if allowed_dir:
        allowed = Path(allowed_dir).resolve()
        if not str(resolved).startswith(str(allowed) + os.sep) and resolved != allowed:
            raise ValueError(f"Path traversal blocked: {p}")
    return str(resolved)


# ═══════════════════════════════════════════════════════════════════════════
# Tool 1: screen_capture — 截图
# ═══════════════════════════════════════════════════════════════════════════

def screen_capture(region: str = "full", save_path: str = "") -> dict:
    """截取屏幕截图"""
    try:
        from PIL import ImageGrab

        if region == "full":
            img = ImageGrab.grab()
        elif region == "active":
            try:
                import pygetwindow as gw
                win = gw.getActiveWindow()
                if win:
                    bbox = (win.left, win.top, win.right, win.bottom)
                    img = ImageGrab.grab(bbox)
                else:
                    img = ImageGrab.grab()
            except Exception:
                img = ImageGrab.grab()
        else:
            parts = region.split(",")
            if len(parts) != 4:
                return {"error": "region must be 'x,y,w,h' format", "success": False}
            x, y, w, h = map(int, parts)
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                return {"error": "coords must be non-negative, size must be positive", "success": False}
            if w > 10000 or h > 10000:
                return {"error": f"region too large: {w}x{h}", "success": False}
            img = ImageGrab.grab((x, y, x + w, y + h))

        path = save_path or "/tmp/hermes_screen.png"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        img.save(path)
        return {"path": path, "size": [img.width, img.height], "success": True}
    except Exception as e:
        _log.error("screen_capture failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 2: gui_locate — 视觉定位
# ═══════════════════════════════════════════════════════════════════════════

def gui_locate(image_path: str, target: str, task: str = "gui") -> dict:
    """用 LocateAnything-3B 定位屏幕上的元素"""
    try:
        if not os.path.isfile(image_path):
            return {"error": f"Image not found: {image_path}", "success": False}

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
            return {"found": False, "success": True, "message": f"未找到: {target}"}
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

        best = max(boxes, key=lambda b: b.width * b.height)
        cx, cy = best.center
        return {
            "found": True, "count": len(boxes), "boxes": result_boxes,
            "click_target": {"x": cx, "y": cy}, "success": True,
        }
    except Exception as e:
        _log.error("gui_locate failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 3: gui_click — 鼠标点击
# ═══════════════════════════════════════════════════════════════════════════

def gui_click(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.1) -> dict:
    """在指定位置点击鼠标"""
    try:
        import pyautogui
        # 参数验证
        err = _validate_coords(x, y, "click")
        if err:
            return err
        if button not in ("left", "right", "middle"):
            return {"error": f"button must be left/right/middle, got: {button}", "success": False}
        if not 1 <= clicks <= 100:
            return {"error": f"clicks must be 1-100, got: {clicks}", "success": False}
        if not 0.001 <= interval <= 10.0:
            return {"error": f"interval must be 0.001-10.0, got: {interval}", "success": False}

        pyautogui.click(x, y, clicks=clicks, button=button, interval=interval)
        return {"clicked": [x, y], "button": button, "clicks": clicks, "success": True}
    except Exception as e:
        _log.error("gui_click failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 4: gui_type — 键盘输入（修复中文逻辑）
# ═══════════════════════════════════════════════════════════════════════════

def gui_type(text: str, interval: float = 0.02, press_enter: bool = False) -> dict:
    """模拟键盘输入文字（支持中文）"""
    try:
        import pyautogui
        if not isinstance(text, str):
            return {"error": "text must be a string", "success": False}
        if not text:
            return {"error": "text is empty", "success": False}

        if text.isascii():
            pyautogui.typewrite(text, interval=interval)
        else:
            # 中文/非ASCII — 通过剪贴板粘贴，保留原剪贴板内容
            import pyperclip
            with _clipboard_lock:
                old = pyperclip.paste()
                try:
                    pyperclip.copy(text)
                    time.sleep(0.05)
                    pyautogui.hotkey(*_PASTE_KEY)
                    time.sleep(0.1)
                finally:
                    pyperclip.copy(old)

        if press_enter:
            time.sleep(0.05)
            pyautogui.press("enter")

        display = text[:50] + "..." if len(text) > 50 else text
        return {"typed": display, "success": True}
    except Exception as e:
        _log.error("gui_type failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 5: gui_hotkey — 快捷键
# ═══════════════════════════════════════════════════════════════════════════

def gui_hotkey(*keys: str) -> dict:
    """执行快捷键组合"""
    try:
        import pyautogui
        if not keys:
            return {"error": "no keys provided", "success": False}
        pyautogui.hotkey(*keys)
        return {"hotkey": "+".join(keys), "success": True}
    except Exception as e:
        _log.error("gui_hotkey failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 6: gui_scroll — 滚动（修复 x=0 逻辑）
# ═══════════════════════════════════════════════════════════════════════════

def gui_scroll(clicks: int, x: int = None, y: int = None) -> dict:
    """滚动鼠标滚轮，正数向上，负数向下"""
    try:
        import pyautogui
        if not isinstance(clicks, int) or clicks == 0:
            return {"error": "clicks must be non-zero integer", "success": False}
        if abs(clicks) > 1000:
            return {"error": "clicks too large (max 1000)", "success": False}
        if (x is None) != (y is None):
            return {"error": "x and y must both be provided or both omitted", "success": False}
        if x is not None and y is not None:
            err = _validate_coords(x, y, "scroll")
            if err:
                return err
            pyautogui.scroll(clicks, x=x, y=y)
        else:
            pyautogui.scroll(clicks)
        return {"scrolled": clicks, "success": True}
    except Exception as e:
        _log.error("gui_scroll failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 7: gui_drag — 拖拽
# ═══════════════════════════════════════════════════════════════════════════

def gui_drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict:
    """从 (x1,y1) 拖拽到 (x2,y2)"""
    try:
        import pyautogui
        err = _validate_coords(x1, y1, "drag_start")
        if err: return err
        err = _validate_coords(x2, y2, "drag_end")
        if err: return err
        if not 0.01 <= duration <= 60.0:
            return {"error": f"duration must be 0.01-60.0", "success": False}
        pyautogui.moveTo(x1, y1)
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
        return {"dragged": {"from": [x1, y1], "to": [x2, y2]}, "success": True}
    except Exception as e:
        _log.error("gui_drag failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 8: open_app — 启动应用（修复 shell 注入）
# ═══════════════════════════════════════════════════════════════════════════

_APP_MAP = {
    "notepad": "notepad.exe", "explorer": "explorer.exe",
    "cmd": "cmd.exe", "powershell": "powershell.exe",
    "chrome": "chrome.exe", "edge": "msedge.exe",
    "word": "WINWORD.EXE", "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE", "calculator": "calc.exe",
    "paint": "mspaint.exe", "vscode": "code.exe",
}

def open_app(name: str, wait: float = 2.0) -> dict:
    """启动应用程序"""
    try:
        exe = _APP_MAP.get(name.lower())
        if not exe:
            return {
                "error": f"Unknown app: {name}. Known: {list(_APP_MAP.keys())}",
                "success": False,
            }
        subprocess.Popen([exe])  # 不用 shell=True，防止注入
        time.sleep(wait)
        return {"opened": name, "success": True}
    except Exception as e:
        _log.error("open_app failed: %s", e, exc_info=True)
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
                    "title": w.title, "left": w.left, "top": w.top,
                    "width": w.width, "height": w.height, "active": w.isActive,
                })
        return {"windows": windows, "count": len(windows), "success": True}
    except Exception as e:
        _log.error("get_windows failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 10: clipboard — 剪贴板操作（修复无效 action）
# ═══════════════════════════════════════════════════════════════════════════

def clipboard(action: str = "get", text: str = "") -> dict:
    """剪贴板操作"""
    try:
        import pyperclip
        if action == "get":
            content = pyperclip.paste()
            return {"content": content, "success": True}
        elif action == "set":
            pyperclip.copy(text)
            return {"set": text[:50], "success": True}
        else:
            return {"error": f"Unknown action: {action}. Use 'get' or 'set'", "success": False}
    except Exception as e:
        _log.error("clipboard failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# Tool 11: screen_ocr — OCR 文字识别
# ═══════════════════════════════════════════════════════════════════════════

def screen_ocr(image_path: str, lang: str = "chi_sim+eng") -> dict:
    """OCR 识别图片中的文字"""
    try:
        if not os.path.isfile(image_path):
            return {"error": f"Image not found: {image_path}", "success": False}
        import pytesseract
        from PIL import Image
        with Image.open(image_path) as img:
            text = pytesseract.image_to_string(img, lang=lang)
        return {"text": text.strip(), "success": True}
    except Exception as e:
        _log.error("screen_ocr failed: %s", e, exc_info=True)
        return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════════════
# 工具注册
# ═══════════════════════════════════════════════════════════════════════════

GUI_TOOLS = {
    "screen_capture": {"fn": screen_capture, "concurrency": "read_only", "description": "截取屏幕截图"},
    "gui_locate": {"fn": gui_locate, "concurrency": "read_only", "description": "AI视觉定位屏幕元素"},
    "gui_click": {"fn": gui_click, "concurrency": "write_serial", "description": "鼠标点击"},
    "gui_type": {"fn": gui_type, "concurrency": "write_serial", "description": "键盘输入（支持中文）"},
    "gui_hotkey": {"fn": gui_hotkey, "concurrency": "write_serial", "description": "快捷键组合"},
    "gui_scroll": {"fn": gui_scroll, "concurrency": "write_serial", "description": "鼠标滚轮"},
    "gui_drag": {"fn": gui_drag, "concurrency": "write_serial", "description": "拖拽操作"},
    "open_app": {"fn": open_app, "concurrency": "write_serial", "description": "启动应用程序"},
    "get_windows": {"fn": get_windows, "concurrency": "read_only", "description": "获取窗口列表"},
    "clipboard": {"fn": clipboard, "concurrency": "write_serial", "description": "剪贴板操作"},
    "screen_ocr": {"fn": screen_ocr, "concurrency": "read_only", "description": "OCR文字识别"},
}
