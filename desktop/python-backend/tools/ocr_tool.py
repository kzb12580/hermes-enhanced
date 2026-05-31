"""OCR tool — Tesseract-based text extraction from images."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from .base import BaseTool
from . import register

logger = logging.getLogger("hermes-backend.tools.ocr")

# Windows Tesseract 常见安装路径
_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
    r"D:\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(os.environ.get("USERNAME", "")),
    r"C:\ProgramData\chocolatey\bin\tesseract.exe",
]


def _find_tesseract() -> str | None:
    """Find Tesseract executable, searching PATH and common locations."""

    # 1. 检查 PATH
    found = shutil.which("tesseract")
    if found:
        return found

    # 2. Windows 常见路径
    if os.name == "nt":
        for p in _WINDOWS_TESSERACT_PATHS:
            if os.path.isfile(p):
                # 自动添加到 PATH
                parent = os.path.dirname(p)
                if parent not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = parent + os.pathsep + os.environ.get("PATH", "")
                    logger.info("Added Tesseract to PATH: %s", parent)
                return p

    # 3. 注册表 (Windows)
    if os.name == "nt":
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for subkey in [
                    r"SOFTWARE\Tesseract-OCR",
                    r"SOFTWARE\WOW6432Node\Tesseract-OCR",
                ]:
                    try:
                        with winreg.OpenKey(root, subkey) as key:
                            val, _ = winreg.QueryValueEx(key, "InstallDir")
                            exe = os.path.join(val, "tesseract.exe")
                            if os.path.isfile(exe):
                                if val not in os.environ.get("PATH", ""):
                                    os.environ["PATH"] = val + os.pathsep + os.environ.get("PATH", "")
                                return exe
                    except (FileNotFoundError, OSError):
                        continue
        except ImportError:
            pass

    return None


class OCRTool(BaseTool):
    """Extract text from images using Tesseract OCR. Uses CPU only (not a neural model)."""

    name = "ocr_extract"
    description = (
        "Extract text from an image using OCR. "
        "Works best with clear text on screenshots, documents, photos. "
        "Supports Chinese + English automatically."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file (PNG/JPG/BMP/TIFF)",
            },
            "language": {
                "type": "string",
                "description": "OCR language: 'chi_sim+eng' (Chinese+English, default), 'eng' (English only), 'chi_sim' (Chinese only)",
                "default": "chi_sim+eng",
            },
        },
        "required": ["image_path"],
    }
    timeout = 30

    def __init__(self):
        self._tesseract_cmd = None
        self._checked = False

    def _ensure_tesseract(self) -> bool:
        """Find and configure Tesseract."""
        if self._checked and self._tesseract_cmd:
            return True
        self._checked = True

        cmd = _find_tesseract()
        if not cmd:
            logger.error(
                "Tesseract not found. Install: "
                "https://github.com/UB-Mannheim/tesseract/wiki "
                "or: choco install tesseract"
            )
            return False

        self._tesseract_cmd = cmd
        logger.info("Tesseract found: %s", cmd)
        return True

    async def execute(self, image_path: str, language: str = "chi_sim+eng", **kwargs) -> str:
        """Extract text from image using Tesseract OCR."""
        if not os.path.isfile(image_path):
            return f"Error: Image not found: {image_path}"

        if not self._ensure_tesseract():
            return (
                "Error: Tesseract OCR not installed. Install from:\n"
                "https://github.com/UB-Mannheim/tesseract/wiki\n"
                "During installation, check 'Chinese Simplified' language pack.\n"
                "Or run: choco install tesseract"
            )

        try:
            import pytesseract
            from PIL import Image

            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

            image = Image.open(image_path).convert("RGB")

            # 自动检测图片大小，大图缩放以加速
            max_dim = 4096
            if max(image.size) > max_dim:
                ratio = max_dim / max(image.size)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info("Resized image to %s for OCR", new_size)

            text = pytesseract.image_to_string(image, lang=language)

            if not text.strip():
                return "OCR completed but no text was detected in the image."

            return text.strip()

        except ImportError as e:
            return f"Error: pytesseract not installed. Run: pip install pytesseract\nDetail: {e}"
        except Exception as e:
            logger.error("OCR failed: %s", e, exc_info=True)
            return f"Error during OCR: {e}"


# Auto-register
register(OCRTool())
