"""Screen capture tool — take screenshots for vision analysis."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .base import BaseTool
from . import register

logger = logging.getLogger("hermes-backend.tools.screen_capture")


class ScreenCaptureTool(BaseTool):
    """Capture screenshots of the current screen or a specific region."""

    name = "screen_capture"
    description = (
        "Take a screenshot of the current screen. Returns the image file path. "
        "Use this before vision_locate to analyze what's on screen."
    )
    parameters = {
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "description": "Optional region to capture: 'full' (default), 'active_window', or 'x,y,width,height'",
            },
            "save_path": {
                "type": "string",
                "description": "Optional path to save screenshot. Default: temp directory.",
            },
        },
        "required": [],
    }
    timeout = 10

    async def execute(self, region: str = "full", save_path: str = "", **kwargs) -> str:
        """Take a screenshot."""
        try:
            from PIL import ImageGrab
            import pyautogui
        except ImportError:
            return "Error: pyautogui and Pillow are required for screenshots."

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if not save_path:
                save_path = os.path.join(tempfile.gettempdir(), f"screenshot_{timestamp}.png")
            else:
                # 路径安全：限制只能保存到用户目录或临时目录
                resolved = str(Path(save_path).resolve())
                home = str(Path.home())
                tmp = tempfile.gettempdir()
                if not (resolved.startswith(home) or resolved.startswith(tmp)):
                    return json.dumps({"ok": False, "error": "save_path must be under home or temp directory"}, ensure_ascii=False)
                save_path = resolved

            if region == "active_window":
                # Get active window bounds
                try:
                    import ctypes
                    if os.name == "nt":
                        hwnd = ctypes.windll.user32.GetForegroundWindow()
                        rect = ctypes.wintypes.RECT()
                        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        bbox = (rect.left, rect.top, rect.right, rect.bottom)
                    else:
                        bbox = None
                except Exception:
                    bbox = None
            elif region == "full":
                bbox = None
            else:
                # Parse x,y,width,height
                try:
                    parts = [int(x.strip()) for x in region.split(",")]
                    if len(parts) == 4:
                        x, y, w, h = parts
                        bbox = (x, y, x + w, y + h)
                    else:
                        bbox = None
                except ValueError:
                    return f"Error: Invalid region format '{region}'. Use 'full', 'active_window', or 'x,y,width,height'."

            screenshot = ImageGrab.grab(bbox=bbox)
            screenshot.save(save_path)
            logger.info("Screenshot saved to %s", save_path)
            return f"Screenshot saved to: {save_path}"
        except Exception as e:
            logger.error("Screenshot failed: %s", e, exc_info=True)
            return f"Error taking screenshot: {e}"


register(ScreenCaptureTool())
