"""Vision tool — nvidia/LocateAnything-3B for GUI element detection and screen understanding.

Model: nvidia/LocateAnything-3B (3B params, ~7GB)
Architecture: Vision-language model with parallel box decoding
Tasks: detect, ground_single, ground_multi, ground_text, detect_text, ground_gui, point
Output: Bounding boxes <box> x1,y1,x2,y2 </box> (normalized 0-1000)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from .base import BaseTool
from . import register
from PIL import Image as _PIL_Image

logger = logging.getLogger("hermes-backend.tools.vision")

# ── 模型配置 ──────────────────────────────────────────────────────────
MODEL_ID = "nvidia/LocateAnything-3B"
DEFAULT_MODEL_DIR = Path.home() / ".hermes" / "desktop" / "models"

# ── 显存配置（自动检测 + 安全限制）────────────────────────────────────────
# 根据显存自动决定图片最大尺寸和 max_new_tokens
VRAM_PROFILES = {
    # 显存(GB): (max_image_dim, max_new_tokens, dtype)
    24: (1920, 4096, "bfloat16"),   # RTX 4090/A5000
    16: (1280, 2048, "float16"),    # RTX 4060Ti 16GB / RTX 4080
    12: (1024, 1024, "float16"),    # RTX 3060 12GB
    8:  (768, 512, "float16"),      # RTX 3060 8GB / RTX 4060
    6:  (640, 512, "float16"),      # 最低可用
}

# ── 任务 prompt 模板（来自官方文档）──────────────────────────────────
TASK_PROMPTS = {
    "detect":       "Locate all the instances that matches the following description: {query}.",
    "ground_single":"Locate a single instance that matches the following description: {query}.",
    "ground_multi": "Locate all the instances that match the following description: {query}.",
    "ground_text":  "Please locate the text referred as {query}.",
    "detect_text":  "Detect all the text in box format.",
    "ground_gui":   "Locate the region that matches the following description: {query}.",
    "point":        "Point to: {query}.",
}


class VisionTool(BaseTool):
    """Locate GUI elements and understand screen content using nvidia/LocateAnything-3B.

    Supports multiple tasks:
    - detect: Find all instances of described objects
    - ground_single: Find one instance of described object
    - ground_multi: Find all instances of described objects
    - ground_text: Locate specific text on screen
    - detect_text: Detect all text in the image
    - ground_gui: Locate GUI elements (buttons, menus, etc.)
    - point: Point to a specific element (returns center coordinates)
    """

    name = "vision_locate"
    description = (
        "Analyze a screenshot to locate GUI elements, detect objects, or find text. "
        "Use when the user asks to click something, read screen text, or automate GUI. "
        "Returns bounding box coordinates in pixel values. "
        "Input: image_path + question about what to find."
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
                "description": "What to find on screen, e.g. 'find the login button', 'locate the search box', 'detect all text'",
            },
            "task": {
                "type": "string",
                "description": "Task type: 'auto' (default, auto-detect), 'detect', 'ground_gui', 'ground_text', 'detect_text', 'point'",
                "default": "auto",
            },
        },
        "required": ["image_path"],
    }
    timeout = 120

    def __init__(self):
        self._model = None
        self._processor = None
        self._vram_gb = 0
        self._profile = None

    def _detect_gpu(self) -> dict:
        """Detect GPU and VRAM, return profile settings."""
        try:
            import torch
            if torch.cuda.is_available():
                vram_bytes = torch.cuda.get_device_properties(0).total_mem
                vram_gb = vram_bytes / (1024 ** 3)
                gpu_name = torch.cuda.get_device_name(0)
                cuda_ver = torch.version.cuda

                # 找到匹配的 profile
                profile = None
                for min_vram in sorted(VRAM_PROFILES.keys(), reverse=True):
                    if vram_gb >= min_vram:
                        profile = VRAM_PROFILES[min_vram]
                        break

                if profile is None:
                    # 显存太小，使用最低配置
                    profile = VRAM_PROFILES[6]

                self._vram_gb = vram_gb
                self._profile = profile

                return {
                    "available": True,
                    "name": gpu_name,
                    "vram_gb": round(vram_gb, 1),
                    "cuda": cuda_ver,
                    "max_image_dim": profile[0],
                    "max_new_tokens": profile[1],
                    "dtype": profile[2],
                }
        except Exception as e:
            logger.warning("GPU detection failed: %s", e)

        return {
            "available": False,
            "name": "CPU",
            "vram_gb": 0,
            "cuda": None,
            "max_image_dim": 640,
            "max_new_tokens": 512,
            "dtype": "float32",
        }

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
                    snapshots = d / "snapshots"
                    if snapshots.exists():
                        for s in snapshots.iterdir():
                            if any(s.glob("*.safetensors")):
                                logger.info("Found model in HF cache snapshot: %s", s)
                                return s
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
        """Lazy-load model on first use. Auto-detect GPU and optimize settings."""
        if self._model is not None:
            return True

        # 检测 GPU
        gpu_info = self._detect_gpu()
        if not gpu_info["available"]:
            logger.error("No GPU available. Vision model requires CUDA GPU with >= 6GB VRAM.")
            return False

        logger.info("GPU: %s (%.1f GB VRAM)", gpu_info["name"], gpu_info["vram_gb"])
        logger.info("Profile: max_image=%d, max_tokens=%d, dtype=%s",
                     gpu_info["max_image_dim"], gpu_info["max_new_tokens"], gpu_info["dtype"])

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
            dtype_str = gpu_info["dtype"]
            if dtype_str == "bfloat16":
                dtype = torch.bfloat16
            elif dtype_str == "float16":
                dtype = torch.float16
            else:
                dtype = torch.float32

            self._processor = AutoProcessor.from_pretrained(
                str(model_path), trust_remote_code=False
            )

            self._model = AutoModel.from_pretrained(
                str(model_path),
                torch_dtype=dtype,
                device_map="auto",
                trust_remote_code=False,
            )

            # 设置 generation_config
            if hasattr(self._model, "generation_config"):
                self._model.generation_config.use_cache = True

            logger.info("Vision model loaded on GPU with dtype=%s", dtype)
            return True
        except Exception as e:
            logger.error("Failed to load vision model: %s", e, exc_info=True)
            self._model = None
            self._processor = None
            # 清理 GPU 内存
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            return False

    def _detect_task(self, question: str) -> str:
        """Auto-detect task type from user question."""
        q = question.lower().strip()

        # 文本检测
        if any(kw in q for kw in ["detect text", "find text", "ocr", "read text", "识别文字", "检测文字", "文字识别"]):
            return "detect_text"

        # GUI 定位
        if any(kw in q for kw in ["button", "menu", "click", "login", "search", "input", "按钮", "菜单", "点击", "登录", "搜索", "输入框", "gui", "element", "widget"]):
            return "ground_gui"

        # 点击/指向
        if any(kw in q for kw in ["point", "click on", "where is", "指向", "在哪里", "位置"]):
            return "point"

        # 通用检测
        if any(kw in q for kw in ["detect", "find all", "locate all", "检测", "找到所有", "定位所有"]):
            return "detect"

        # 默认：GUI 定位
        return "ground_gui"

    def _resize_image(self, image: _PIL_Image.Image, max_dim: int) -> tuple:
        """Resize image to fit within max_dim while maintaining aspect ratio."""
        w, h = image.size
        if max(w, h) <= max_dim:
            return image, 1.0

        ratio = max_dim / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        resized = image.resize((new_w, new_h), _PIL_Image.Resampling.LANCZOS)
        logger.info("Resized image: %dx%d -> %dx%d (ratio=%.2f)", w, h, new_w, new_h, ratio)
        return resized, ratio

    def _parse_boxes(self, text: str, img_width: int, img_height: int, ratio: float) -> list[dict]:
        """Parse bounding boxes from model output.

        Model outputs normalized coordinates (0-1000).
        Convert to pixel coordinates in original image size.
        """
        boxes = []
        # 匹配 <box> x1,y1,x2,y2 </box> 或 <box> x,y </box>
        pattern = re.compile(r'<box>\s*([\d,.\s]+)\s*</box>')
        matches = pattern.findall(text)

        for match in matches:
            coords = [float(c.strip()) for c in match.split(",") if c.strip()]
            if len(coords) == 4:
                # 归一化坐标 (0-1000) -> 像素坐标
                x1 = int(coords[0] / 1000 * img_width)
                y1 = int(coords[1] / 1000 * img_height)
                x2 = int(coords[2] / 1000 * img_width)
                y2 = int(coords[3] / 1000 * img_height)
                # 如果图片被缩放过，还原到原始尺寸
                if ratio < 1.0:
                    x1 = int(x1 / ratio)
                    y1 = int(y1 / ratio)
                    x2 = int(x2 / ratio)
                    y2 = int(y2 / ratio)
                boxes.append({
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "width": x2 - x1, "height": y2 - y1,
                    "center_x": (x1 + x2) // 2,
                    "center_y": (y1 + y2) // 2,
                })
            elif len(coords) == 2:
                # 点坐标
                x = int(coords[0] / 1000 * img_width)
                y = int(coords[1] / 1000 * img_height)
                if ratio < 1.0:
                    x = int(x / ratio)
                    y = int(y / ratio)
                boxes.append({
                    "x": x, "y": y,
                    "type": "point",
                })

        return boxes

    async def execute(self, image_path: str, question: str = "Describe what you see", task: str = "auto", **kwargs) -> str:
        """Run vision inference on a screenshot."""
        if not os.path.isfile(image_path):
            return f"Error: Image not found: {image_path}"

        if not self._load_model():
            return (
                "Error: Vision model not available.\n"
                "Requirements:\n"
                "1. CUDA GPU with >= 6GB VRAM\n"
                "2. PyTorch with CUDA support\n"
                "3. LocateAnything-3B model downloaded\n"
                "Run the setup wizard or install manually."
            )

        try:
            from PIL import Image
            import torch

            # 打开图片
            image = Image.open(image_path).convert("RGB")
            orig_w, orig_h = image.size

            # 自动检测任务类型
            if task == "auto":
                task = self._detect_task(question)
                logger.info("Auto-detected task: %s", task)

            # 构建 prompt
            if task in TASK_PROMPTS:
                if task == "detect_text":
                    prompt = TASK_PROMPTS[task]
                else:
                    prompt = TASK_PROMPTS[task].format(query=question)
            else:
                # 回退到通用 prompt
                prompt = question

            # 根据显存限制缩放图片
            max_dim = self._profile[0] if self._profile else 1280
            image, ratio = self._resize_image(image, max_dim)

            # 构建 messages
            messages = [
                {"role": "user", "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ]}
            ]

            # 关键：apply_chat_template 只生成 prompt 字符串
            chat_prompt = self._processor.apply_chat_template(
                messages, add_generation_prompt=True
            )

            # 单独处理图片和文本
            inputs = self._processor(
                text=chat_prompt,
                images=[image],
                return_tensors="pt",
            )
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # 生成（使用 profile 推荐的 max_new_tokens）
            max_tokens = self._profile[1] if self._profile else 2048
            with torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=False,
                    use_cache=True,
                )

            # 解码输出
            if isinstance(output_ids, str):
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

            # 解析坐标并格式化结果
            boxes = self._parse_boxes(response, orig_w, orig_h, ratio)

            if boxes:
                result_lines = [
                    f"Task: {task}",
                    f"Image: {orig_w}x{orig_h}",
                    f"Found {len(boxes)} result(s):",
                    "",
                ]
                for i, box in enumerate(boxes, 1):
                    if box.get("type") == "point":
                        result_lines.append(f"  [{i}] Point: ({box['x']}, {box['y']})")
                    else:
                        result_lines.append(
                            f"  [{i}] Box: ({box['x1']}, {box['y1']}) - ({box['x2']}, {box['y2']}) "
                            f"[{box['width']}x{box['height']}] center=({box['center_x']}, {box['center_y']})"
                        )
                result_lines.append("")
                result_lines.append(f"Raw output: {response}")
                return "\n".join(result_lines)
            else:
                return f"Model output (no coordinates detected):\n{response}"

        except Exception as e:
            logger.error("Vision inference failed: %s", e, exc_info=True)
            return f"Error during vision inference: {e}"


# Auto-register
register(VisionTool())
