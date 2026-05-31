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
    timeout = 60  # 增加超时，GPU 推理也需要时间

    def __init__(self):
        self._model = None
        self._processor = None

    def _find_model_path(self) -> Path | None:
        """Find downloaded model directory — supports multiple download locations."""

        # 1. 自定义目录 (~/.hermes/desktop/models/)
        candidates = [
            DEFAULT_MODEL_DIR / "LocateAnything-3B",
            DEFAULT_MODEL_DIR / "nvidia--LocateAnything-3B",
            DEFAULT_MODEL_DIR / MODEL_ID.replace("/", "--"),
        ]
        for p in candidates:
            if p.exists() and any(p.glob("*.safetensors")):
                logger.info("Found model in custom dir: %s", p)
                return p

        # 2. HuggingFace Hub 标准缓存
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.exists():
            for d in hf_cache.iterdir():
                if "LocateAnything" in d.name or "locate-anything" in d.name.lower():
                    # 检查 snapshots 子目录
                    snapshots = d / "snapshots"
                    if snapshots.exists():
                        for s in snapshots.iterdir():
                            if any(s.glob("*.safetensors")):
                                logger.info("Found model in HF cache: %s", s)
                                return s
                    # 直接在根目录
                    if any(d.glob("*.safetensors")):
                        logger.info("Found model in HF cache root: %s", d)
                        return d

        # 3. 常见手动下载路径
        common_paths = [
            Path.home() / "LocateAnything-3B",
            Path.home() / "models" / "LocateAnything-3B",
            Path("C:/models/LocateAnything-3B") if os.name == "nt" else Path("/opt/models/LocateAnything-3B"),
            Path("D:/models/LocateAnything-3B") if os.name == "nt" else None,
            Path("E:/models/LocateAnything-3B") if os.name == "nt" else None,
        ]
        for p in common_paths:
            if p and p.exists() and any(p.glob("*.safetensors")):
                logger.info("Found model in common path: %s", p)
                return p

        # 4. 用户自定义路径（通过环境变量或配置文件）
        custom_path = os.environ.get("HERMES_VISION_MODEL_PATH")
        if custom_path:
            p = Path(custom_path)
            if p.exists() and any(p.glob("*.safetensors")):
                logger.info("Found model via env var: %s", p)
                return p

        return None

    def _load_model(self):
        """Lazy-load model on first use. ALWAYS uses GPU if available."""
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError:
            logger.error("torch or transformers not installed")
            return False

        model_path = self._find_model_path()
        if not model_path:
            logger.error("Model not found. Run setup wizard to download or set HERMES_VISION_MODEL_PATH.")
            return False

        logger.info("Loading vision model from %s", model_path)
        try:
            # 强制使用 GPU
            if torch.cuda.is_available():
                device = "cuda"
                dtype = torch.float16
                logger.info("Using GPU: %s", torch.cuda.get_device_name(0))
            else:
                device = "cpu"
                dtype = torch.float32
                logger.warning("No GPU available, falling back to CPU (will be slow)")

            self._processor = AutoProcessor.from_pretrained(
                str(model_path), trust_remote_code=True
            )

            if device == "cuda":
                # GPU: 使用 device_map="auto" 自动分配显存
                self._model = AutoModel.from_pretrained(
                    str(model_path),
                    torch_dtype=dtype,
                    device_map="auto",
                    trust_remote_code=True,
                )
            else:
                # CPU: 不用 device_map
                self._model = AutoModel.from_pretrained(
                    str(model_path),
                    torch_dtype=dtype,
                    trust_remote_code=True,
                )
                self._model = self._model.to("cpu")

            logger.info("Vision model loaded on %s (dtype=%s)", device, dtype)
            return True
        except Exception as e:
            logger.error("Failed to load vision model: %s", e, exc_info=True)
            self._model = None
            self._processor = None
            return False

    async def execute(self, image_path: str, question: str = "Describe what you see on this screen") -> str:
        """Run vision inference on a screenshot."""
        if not os.path.isfile(image_path):
            return f"Error: Image not found: {image_path}"

        if not self._load_model():
            return "Error: Vision model not available. Check if model is downloaded (run setup wizard) and PyTorch+CUDA is installed."

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
            inputs = self._processor(text=prompt, images=[image], return_tensors="pt")
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
