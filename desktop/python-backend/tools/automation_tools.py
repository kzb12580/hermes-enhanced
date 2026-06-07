"""
Automation tools — mouse, keyboard, window management for GUI automation.
Works on Windows/macOS/Linux. Uses pyautogui for input, win32/native APIs for windows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import time
from typing import Any

from .base import BaseTool

logger = logging.getLogger("hermes-backend.automation")

_PLATFORM = platform.system()


# ─── Mouse Click ────────────────────────────────────────────────────────────

class MouseClickTool(BaseTool):
    name = "mouse_click"
    description = "在屏幕坐标处点击。请先用 screen_capture 获取坐标。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X 坐标（像素）"},
                "y": {"type": "integer", "description": "Y 坐标（像素）"},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                "clicks": {"type": "integer", "description": "点击次数（1=单击，2=双击）", "default": 1},
            },
            "required": ["x", "y"],
        }

    async def execute(self, x: int, y: int, button: str = "left", clicks: int = 1, **kw) -> str:
        import pyautogui
        pyautogui.FAILSAFE = True  # Move mouse to corner to abort
        try:
            await asyncio.to_thread(pyautogui.click, x, y, clicks=clicks, button=button)
        except pyautogui.FailSafeException:
            return json.dumps({"ok": False, "error": "鼠标移到了屏幕角落，触发了安全保护。请将鼠标移到屏幕中间后重试。", "action": "click", "x": x, "y": y})
        return json.dumps({"ok": True, "action": "click", "x": x, "y": y, "button": button, "clicks": clicks})


# ─── Mouse Move ─────────────────────────────────────────────────────────────

class MouseMoveTool(BaseTool):
    name = "mouse_move"
    description = "平滑移动鼠标到指定坐标。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "X 坐标"},
                "y": {"type": "integer", "description": "Y 坐标"},
                "duration": {"type": "number", "description": "移动持续时间（秒）", "default": 0.3},
            },
            "required": ["x", "y"],
        }

    async def execute(self, x: int, y: int, duration: float = 0.3, **kw) -> str:
        import pyautogui
        await asyncio.to_thread(pyautogui.moveTo, x, y, duration=duration)
        return json.dumps({"ok": True, "action": "move", "x": x, "y": y})


# ─── Mouse Drag ─────────────────────────────────────────────────────────────

class MouseDragTool(BaseTool):
    name = "mouse_drag"
    description = "从当前位置拖动鼠标到目标坐标。"
    timeout = 15

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Target X"},
                "y": {"type": "integer", "description": "Target Y"},
                "duration": {"type": "number", "default": 0.5},
                "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
            },
            "required": ["x", "y"],
        }

    async def execute(self, x: int, y: int, duration: float = 0.5, button: str = "left", **kw) -> str:
        import pyautogui
        try:
            await asyncio.to_thread(pyautogui.drag, x, y, duration=duration, button=button)
        except pyautogui.FailSafeException:
            return json.dumps({"ok": False, "error": "鼠标移到了屏幕角落，触发了安全保护。请将鼠标移到屏幕中间后重试。", "action": "drag", "x": x, "y": y})
        return json.dumps({"ok": True, "action": "drag", "x": x, "y": y})


# ─── Mouse Scroll ───────────────────────────────────────────────────────────

class MouseScrollTool(BaseTool):
    name = "mouse_scroll"
    description = "在当前位置或指定坐标滚动鼠标滚轮。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "description": "滚动量（正数向上，负数向下）", "default": 3},
                "x": {"type": "integer", "description": "X 坐标 (optional)"},
                "y": {"type": "integer", "description": "Y 坐标 (optional)"},
            },
            "required": ["amount"],
        }

    async def execute(self, amount: int = 3, x: int = None, y: int = None, **kw) -> str:
        import pyautogui
        if x is not None and y is not None:
            await asyncio.to_thread(pyautogui.scroll, amount, x, y)
        else:
            await asyncio.to_thread(pyautogui.scroll, amount)
        return json.dumps({"ok": True, "action": "scroll", "amount": amount})


# ─── Keyboard Type ──────────────────────────────────────────────────────────

class KeyboardTypeTool(BaseTool):
    name = "keyboard_type"
    description = "输入文本字符串。支持 {enter}、{tab}、{ctrl+c} 等特殊按键。请先用 screen_capture 定位输入框。"
    timeout = 30

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要输入的文本"},
                "interval": {"type": "number", "description": "按键之间的延迟（秒）", "default": 0.02},
            },
            "required": ["text"],
        }

    async def execute(self, text: str, interval: float = 0.02, **kw) -> str:
        import pyautogui
        await asyncio.to_thread(pyautogui.typewrite, text, interval=interval)
        return json.dumps({"ok": True, "action": "type", "length": len(text)})


# ─── Keyboard Hotkey ────────────────────────────────────────────────────────

class KeyboardHotkeyTool(BaseTool):
    name = "keyboard_hotkey"
    description = "按下快捷键组合。例如：'ctrl+c'、'ctrl+v'、'alt+tab'、'enter'、'escape'、'ctrl+a'、'ctrl+s'。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": "快捷键组合，用 '+' 分隔。例如：ctrl+c、alt+tab、ctrl+shift+s",
                },
            },
            "required": ["keys"],
        }

    async def execute(self, keys: str, **kw) -> str:
        import pyautogui
        key_list = [k.strip() for k in keys.split("+")]
        await asyncio.to_thread(pyautogui.hotkey, *key_list)
        return json.dumps({"ok": True, "action": "hotkey", "keys": keys})


# ─── Keyboard Press ─────────────────────────────────────────────────────────

class KeyboardPressTool(BaseTool):
    name = "keyboard_press"
    description = "按下单个按键。可用按键：enter、tab、escape、space、backspace、delete、up、down、left、right、f1-f12、home、end、pageup、pagedown。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "要按下的按键名称"},
                "presses": {"type": "integer", "description": "按键次数", "default": 1},
            },
            "required": ["key"],
        }

    async def execute(self, key: str, presses: int = 1, **kw) -> str:
        import pyautogui
        for _ in range(presses):
            await asyncio.to_thread(pyautogui.press, key)
        return json.dumps({"ok": True, "action": "press", "key": key, "presses": presses})


# ─── List Windows ───────────────────────────────────────────────────────────

class ListWindowsTool(BaseTool):
    name = "list_windows"
    description = "列出所有可见窗口及其标题和句柄。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kw) -> str:
        windows = []

        if _PLATFORM == "Windows":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            EnumWindows = user32.EnumWindows
            GetWindowTextW = user32.GetWindowTextW
            GetWindowTextLengthW = user32.GetWindowTextLengthW
            IsWindowVisible = user32.IsWindowVisible

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def callback(hwnd, _):
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowTextW(hwnd, buf, length + 1)
                        windows.append({"hwnd": hwnd, "title": buf.value})
                return True

            EnumWindows(WNDENUMPROC(callback), 0)

        elif _PLATFORM == "Darwin":
            try:
                from AppKit import NSWorkspace
                for app in NSWorkspace.sharedWorkspace().runningApplications():
                    if app.isActive() or app.activationPolicy() == 0:
                        name = app.localizedName() or str(app.bundleIdentifier())
                        windows.append({"pid": app.processIdentifier(), "title": name})
            except ImportError:
                return json.dumps({"error": "pyobjc not installed"})

        else:  # Linux
            try:
                import subprocess
                result = subprocess.run(
                    ["wmctrl", "-l"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split(None, 3)
                        if len(parts) >= 4:
                            windows.append({"wid": parts[0], "title": parts[3]})
            except FileNotFoundError:
                return json.dumps({"error": "wmctrl not installed"})

        return json.dumps({"windows": windows[:50], "count": len(windows)})


# ─── Find Window ────────────────────────────────────────────────────────────

class FindWindowTool(BaseTool):
    name = "find_window"
    description = "按标题片段查找窗口，返回窗口句柄和位置。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "要搜索的窗口标题片段（不区分大小写）"},
            },
            "required": ["title"],
        }

    async def execute(self, title: str, **kw) -> str:
        title_lower = title.lower()

        if _PLATFORM == "Windows":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            found = []

            def callback(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if title_lower in buf.value.lower():
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            found.append({
                                "hwnd": hwnd,
                                "title": buf.value,
                                "x": rect.left, "y": rect.top,
                                "width": rect.right - rect.left,
                                "height": rect.bottom - rect.top,
                            })
                return True

            user32.EnumWindows(WNDENUMPROC(callback), 0)

            if found:
                return json.dumps({"found": True, "windows": found})
            return json.dumps({"found": False, "search": title})

        return json.dumps({"error": f"find_window not fully supported on {_PLATFORM}"})


# ─── Bring Window to Front ──────────────────────────────────────────────────

class BringToFrontTool(BaseTool):
    name = "bring_to_front"
    description = "通过标题或句柄将窗口置于前台。"
    timeout = 10

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "窗口标题片段（不区分大小写）"},
            },
            "required": ["title"],
        }

    async def execute(self, title: str, **kw) -> str:
        if _PLATFORM == "Windows":
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            title_lower = title.lower()
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            found_hwnd = [None]

            def callback(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if title_lower in buf.value.lower():
                            found_hwnd[0] = hwnd
                            return False  # Stop enumeration
                return True

            user32.EnumWindows(WNDENUMPROC(callback), 0)

            if found_hwnd[0]:
                hwnd = found_hwnd[0]
                # Restore if minimized
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                return json.dumps({"ok": True, "action": "bring_to_front", "hwnd": hwnd})

            return json.dumps({"ok": False, "error": f"Window '{title}' not found"})

        return json.dumps({"error": f"bring_to_front not fully supported on {_PLATFORM}"})


# ─── Wait / Sleep ───────────────────────────────────────────────────────────

class WaitTool(BaseTool):
    name = "wait"
    description = "等待指定秒数，常用于自动化步骤之间暂停。"
    timeout = 60

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "description": "等待秒数", "default": 1.0},
            },
            "required": ["seconds"],
        }

    async def execute(self, seconds: float = 1.0, **kw) -> str:
        seconds = min(seconds, 30)  # Cap at 30s
        await asyncio.sleep(seconds)
        return json.dumps({"ok": True, "action": "wait", "seconds": seconds})


# ─── Get Mouse Position ─────────────────────────────────────────────────────

class GetMousePosTool(BaseTool):
    name = "get_mouse_position"
    description = "获取当前鼠标指针位置，便于调试自动化操作。"
    timeout = 5

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kw) -> str:
        import pyautogui
        pos = await asyncio.to_thread(pyautogui.position)
        return json.dumps({"x": pos.x, "y": pos.y})


# ─── Screen Size ────────────────────────────────────────────────────────────

class ScreenSizeTool(BaseTool):
    name = "get_screen_size"
    description = "获取屏幕分辨率（像素）。"
    timeout = 5

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kw) -> str:
        import pyautogui
        size = await asyncio.to_thread(pyautogui.size)
        return json.dumps({"width": size.width, "height": size.height})
