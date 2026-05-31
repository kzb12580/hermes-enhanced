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

# 最大图片尺寸（防止 CUDA OOM）
MAX_IMAGE_DIM = 1280


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
    timeout = 120  # GPU 推理 + 图片处理可能较慢

    def __init__(self):
        self._model = None
        self._processor = None

    def _find_model_path(self) -> Path | None:
        """Find downloaded model directory — supports multiple download locations."""

        # 1. 自定义目录
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
                                logger.info("Found model in HF cache snapshot: %s", s)
                                return s
                    # 直接在根目录
                    if any(d.glob("*.safetensors")):
                        logger.info("Found model in HF cache root: %s", d)
                        return d

        # 3. 常见手动下载路径
        if os.name == "nt":
            common_paths = [
                Path.home() / "LocateAnything-3B",
                Path.home() / "models" / "LocateAnything-3B",
                Path("C:/models/LocateAnything-3B"),
                Path("D:/models/LocateAnything-3B"),
                Path("E:/models/LocateAnything-3B"),
            ]
        else:
            common_paths = [
                Path.home() / "LocateAnything-3B",
                Path.home() / "models" / "LocateAnything-3B",
                Path("/opt/models/LocateAnything-3B"),
            ]
        for p in common_paths:
            if p.exists() and any(p.glob("*.safetensors")):
                logger.info("Found model in common path: %s", p)
                return p

        # 4. 环境变量
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
            logger.error("Model not found. Run setup wizard or set HERMES_VISION_MODEL_PATH.")
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
                self._model = AutoModel.from_pretrained(
                    str(model_path),
                    torch_dtype=dtype,
                    device_map="auto",
                    trust_remote_code=True,
                )
            else:
                self._model = AutoModel.from_pretrained(
                    str(model_path),
                    torch_dtype=dtype,
                    trust_remote_code=True,
                )
                self._model = self._model.to("cpu")

            # 设置 generation_config 避免 use_cache 问题
            if hasattr(self._model, "generation_config"):
                self._model.generation_config.use_cache = True

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
            import torch

            image = Image.open(image_path).convert("RGB")

            # 大图缩放防止 CUDA OOM
            if max(image.size) > MAX_IMAGE_DIM:
                ratio = MAX_IMAGE_DIM / max(image.size)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                logger.info("Resized image to %s to prevent OOM", new_size)

            # 构建 messages（给 apply_chat_template 用）
            messages = [
                {"role": "user", "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": question},
                ]}
            ]

            # 关键修复：apply_chat_template 只生成 prompt 字符串
            # 不传 images，避免 processor.__call__ 被重复调用
            prompt = self._processor.apply_chat_template(
                messages, add_generation_prompt=True
            )

            # 单独用 processor 处理图片和文本
            inputs = self._processor(
                text=prompt,
                images=[image],
                return_tensors="pt",
            )
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # 生成
            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    do_sample=False,
                    use_cache=True,
                )

            # 解码
            if isinstance(output_ids, str):
                # 某些模型直接返回字符串
                response = output_ids
            elif hasattr(output_ids, "sequences"):
                response = self._processor.decode(
                    output_ids.sequences[0], skip_special_tokens=True
                )
            else:
                response = self._processor.decode(
                    output_ids[0], skip_special_tokens=True
                )

            # 提取 assistant 回复
            if "assistant" in response:
                response = response.split("assistant")[-1].strip()

            return response

        except Exception as e:
            logger.error("Vision inference failed: %s", e, exc_info=True)
            return f"Error during vision inference: {e}"


# Auto-register
register(VisionTool())
