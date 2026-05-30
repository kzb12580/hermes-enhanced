"""Vision tool — nvidia/LocateAnything-3B for GUI element detection and screen understanding."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .base import BaseTool
from . import register

logger = logging.getLogger("hermes-backend.tools.vision")

# Model config
MODEL_ID = "nvidia/LocateAnything-3B"
DEFAULT_MODEL_DIR = Path.home() / ".hermes" / "desktop" / "models"


class VisionTool(BaseTool):
    """Locate GUI elements and understand screen content using nvidia/LocateAnything-3B."""

    name = "vision_locate"
    description = (
        "Analyze a screenshot to locate GUI elements or understand screen content. "
        "Use when the user asks to click something, read screen text, or automate GUI. "
        "Input: image path + question about what to find/understand."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the screenshot image file (PNG/JPG)",
            },
            "question": {
                "type": "string",
                "description": "What to find or understand on screen, e.g. 'find the login button', 'what text is visible'",
            },
        },
        "required": ["image_path"],
    }
    timeout = 30

    def __init__(self):
        self._model = None
        self._processor = None

    def _find_model_path(self) -> Path | None:
        """Find downloaded model directory."""
        candidates = [
            DEFAULT_MODEL_DIR / "LocateAnything-3B",
            DEFAULT_MODEL_DIR / "nvidia--LocateAnything-3B",
            DEFAULT_MODEL_DIR / MODEL_ID.replace("/", "--"),
        ]
        for p in candidates:
            if p.exists() and any(p.glob("*.safetensors")):
                return p
        # Check HF cache
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.exists():
            for d in hf_cache.iterdir():
                if "LocateAnything" in d.name:
                    snapshots = d / "snapshots"
                    if snapshots.exists():
                        for s in snapshots.iterdir():
                            if any(s.glob("*.safetensors")):
                                return s
        return None

    def _load_model(self):
        """Lazy-load model on first use."""
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor
        except ImportError:
            logger.error("torch or transformers not installed")
            return False

        model_path = self._find_model_path()
        if not model_path:
            logger.error("Model not found. Run setup wizard to download.")
            return False

        logger.info("Loading vision model from %s", model_path)
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            self._processor = AutoProcessor.from_pretrained(
                str(model_path), trust_remote_code=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                torch_dtype=dtype,
                device_map="auto" if device == "cuda" else None,
                trust_remote_code=True,
            )
            if device == "cpu":
                self._model = self._model.to(device)
            logger.info("Vision model loaded on %s", device)
            return True
        except Exception as e:
            logger.error("Failed to load vision model: %s", e)
            self._model = None
            self._processor = None
            return False

    async def execute(self, image_path: str, question: str = "Describe what you see on this screen") -> str:
        """Run vision inference on a screenshot."""
        if not os.path.isfile(image_path):
            return f"Error: Image not found: {image_path}"

        if not self._load_model():
            return "Error: Vision model not available. Check if model is downloaded (run setup wizard) and PyTorch is installed."

        try:
            from PIL import Image
            image = Image.open(image_path).convert("RGB")

            messages = [
                {"role": "user", "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": question},
                ]}
            ]
            prompt = self._processor.apply_chat_template(messages, add_generation_prompt=True)
            inputs = self._processor(prompt, images=[image], return_tensors="pt")
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            import torch
            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    do_sample=False,
                )
            response = self._processor.decode(output_ids[0], skip_special_tokens=True)
            # Extract assistant response
            if "assistant" in response:
                response = response.split("assistant")[-1].strip()
            return response
        except Exception as e:
            logger.error("Vision inference failed: %s", e, exc_info=True)
            return f"Error during vision inference: {e}"


# Auto-register
register(VisionTool())
