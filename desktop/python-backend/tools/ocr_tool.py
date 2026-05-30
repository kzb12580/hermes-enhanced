"""OCR tool — extract text from images using pytesseract or vision model."""

from __future__ import annotations

import logging
import os

from .base import BaseTool
from . import register

logger = logging.getLogger("hermes-backend.tools.ocr")


class OCRTool(BaseTool):
    """Extract text from images using OCR (pytesseract) or the vision model."""

    name = "ocr_extract"
    description = (
        "Extract text from an image using OCR. "
        "Supports screenshots, photos, scanned documents. "
        "Returns the recognized text content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file (PNG, JPG, BMP, TIFF)",
            },
            "language": {
                "type": "string",
                "description": "OCR language: 'chi_sim' (Chinese), 'eng' (English), 'chi_sim+eng' (both). Default: auto-detect.",
            },
            "method": {
                "type": "string",
                "description": "OCR method: 'tesseract' (fast, default) or 'vision' (uses AI model, better for complex layouts)",
            },
        },
        "required": ["image_path"],
    }
    timeout = 30

    async def execute(self, image_path: str, language: str = "chi_sim+eng", method: str = "tesseract") -> str:
        """Extract text from image."""
        if not os.path.isfile(image_path):
            return f"Error: Image not found: {image_path}"

        if method == "vision":
            return await self._ocr_with_vision(image_path)
        return await self._ocr_with_tesseract(image_path, language)

    async def _ocr_with_tesseract(self, image_path: str, language: str) -> str:
        """OCR using pytesseract."""
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return "Error: pytesseract and Pillow are required. Install with: pip install pytesseract Pillow"

        try:
            image = Image.open(image_path)
            # Try to auto-detect language if default
            if language == "auto":
                # Try Chinese + English first
                try:
                    text = pytesseract.image_to_string(image, lang="chi_sim+eng")
                except Exception:
                    text = pytesseract.image_to_string(image, lang="eng")
            else:
                text = pytesseract.image_to_string(image, lang=language)

            if not text.strip():
                return "No text detected in image. Try with method='vision' for better results."

            return text.strip()
        except Exception as e:
            logger.error("Tesseract OCR failed: %s", e, exc_info=True)
            return f"Error during OCR: {e}. Make sure tesseract is installed on your system."

    async def _ocr_with_vision(self, image_path: str) -> str:
        """OCR using the vision model (better for complex layouts)."""
        try:
            from .vision_tool import VisionTool
            vision = VisionTool()
            return await vision.execute(
                image_path=image_path,
                question="Read and extract ALL text from this image. Return the text exactly as it appears, preserving formatting and layout."
            )
        except Exception as e:
            logger.error("Vision OCR failed: %s", e, exc_info=True)
            return f"Error during vision OCR: {e}"


register(OCRTool())
