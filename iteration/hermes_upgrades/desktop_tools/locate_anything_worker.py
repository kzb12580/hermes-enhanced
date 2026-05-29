"""
LocateAnything-3B 视觉定位服务
— 自动依赖检测 + 线程安全 + 显存管理
"""
import re
import sys
import logging
from typing import Optional
from dataclasses import dataclass
from pathlib import Path
import threading

_log = logging.getLogger(__name__)

# ── 依赖自动检测 ──────────────────────────────────────────────────────────
_DEPS_CHECKED = False
_DEPS_OK = False

def _check_deps() -> bool:
    """首次使用时检测所有依赖，缺失则给出安装指引"""
    global _DEPS_CHECKED, _DEPS_OK
    if _DEPS_CHECKED:
        return _DEPS_OK

    _DEPS_CHECKED = True
    missing = []

    # 检测核心依赖
    try:
        import torch
    except ImportError:
        missing.append(("torch", "pip install torch torchvision"))

    try:
        import transformers
    except ImportError:
        missing.append(("transformers", "pip install transformers"))

    try:
        from PIL import Image
    except ImportError:
        missing.append(("Pillow", "pip install Pillow"))

    if missing:
        _log.error("=" * 50)
        _log.error("  ❌ 缺少核心依赖，无法使用视觉模型")
        _log.error("=" * 50)
        for pkg, cmd in missing:
            _log.error(f"  ❌ {pkg:20s} → {cmd}")
        _log.error("")
        _log.error("  💡 一键安装所有依赖:")
        _log.error(f"     {sys.executable} setup_deps.py")
        _log.error("     或运行 install.sh / install.bat")
        _log.error("=" * 50)
        _DEPS_OK = False
        return False

    # 检测 CUDA
    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_mem / (1024**3)
        _log.info(f"✅ GPU: {gpu} ({vram:.1f}GB)")
        if vram < 6:
            _log.warning(f"⚠️  VRAM ({vram:.1f}GB) < 推荐 (6GB)，可能较慢")
    else:
        _log.warning("⚠️  CUDA 不可用，将以 CPU 模式运行（较慢）")

    # 检测模型是否已下载
    try:
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache("nvidia/LocateAnything-3B", "config.json")
        if cached and not isinstance(cached, str):
            _log.info("✅ 模型已下载")
        else:
            _log.warning("⚠️  模型未下载，首次加载将自动下载 (~6GB)")
            _log.info("   提前下载: huggingface-cli download nvidia/LocateAnything-3B")
    except ImportError:
        _log.warning("⚠️  huggingface_hub 未安装，无法检查模型缓存")

    _DEPS_OK = True
    return True


@dataclass
class BBox:
    x1: int; y1: int; x2: int; y2: int
    label: str = ""; confidence: float = 0.0

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def width(self) -> int: return self.x2 - self.x1

    @property
    def height(self) -> int: return self.y2 - self.y1

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class LocateAnythingWorker:
    """LocateAnything-3B 推理封装（线程安全 + 显存管理 + 自动依赖检测）"""

    def __init__(self, model_path: str = "nvidia/LocateAnything-3B", device: str = "auto"):
        if not _check_deps():
            raise RuntimeError(
                "缺少依赖，请先运行安装脚本:\n"
                f"  {sys.executable} setup_deps.py\n"
                "  或 bash install.sh / install.bat"
            )

        self.model_path = model_path
        # 自动选择设备
        if device == "auto":
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        self._model = None
        self._processor = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()

    def _load(self):
        """懒加载模型（双重检查锁）"""
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor
            _log.info(f"Loading LocateAnything-3B from {self.model_path}...")
            _log.info(f"Device: {self.device}")

            self._processor = AutoProcessor.from_pretrained(
                self.model_path, trust_remote_code=True
            )

            # 根据设备选择加载策略
            load_kwargs = {
                "trust_remote_code": True,
            }
            if self.device == "cuda":
                load_kwargs["torch_dtype"] = torch.float16
                load_kwargs["device_map"] = "auto"
            else:
                load_kwargs["torch_dtype"] = torch.float32
                # CPU 模式不需要 device_map

            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path, **load_kwargs
            )

            if self.device == "cpu":
                self._model = self._model.eval()

            _log.info("LocateAnything-3B loaded successfully")

    def unload(self):
        """释放GPU显存"""
        with self._load_lock:
            if self._model is not None:
                del self._model
                self._model = None
            if self._processor is not None:
                del self._processor
                self._processor = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            _log.info("LocateAnything-3B unloaded")

    def _run_inference(self, image, prompt: str) -> str:
        """运行推理（显式释放张量）"""
        self._load()
        import torch
        inputs = self._processor(text=prompt, images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) if hasattr(v, 'to') else v for k, v in inputs.items()}
        with self._inference_lock:
            try:
                with torch.no_grad():
                    output = self._model.generate(**inputs, max_new_tokens=512, do_sample=False)
                decoded = self._processor.decode(output[0].detach().cpu(), skip_special_tokens=False)
                return decoded
            finally:
                del inputs
                try:
                    del output
                except NameError:
                    pass

    @staticmethod
    def _parse_box_content(content: str, width: int, height: int) -> tuple[list[BBox], list[tuple[int, int]]]:
        """统一解析 <box>...</box> 内容，区分4坐标(box)和2坐标(point)"""
        boxes = []
        points = []
        for match in re.finditer(r"<box>\s*([\d,\s]+?)\s*</box>", content):
            try:
                nums = [int(x.strip()) for x in match.group(1).split(",") if x.strip()]
            except ValueError:
                _log.warning(f"Malformed box: {match.group(1)}")
                continue
            if len(nums) == 4:
                x1, x2 = min(nums[0], nums[2]), max(nums[0], nums[2])
                y1, y2 = min(nums[1], nums[3]), max(nums[1], nums[3])
                boxes.append(BBox(
                    x1=round(x1 * width / 1000), y1=round(y1 * height / 1000),
                    x2=round(x2 * width / 1000), y2=round(y2 * height / 1000),
                ))
            elif len(nums) == 2:
                x, y = nums
                points.append((round(x * width / 1000), round(y * height / 1000)))
        return boxes, points

    @staticmethod
    def parse_boxes(answer: str, width: int, height: int) -> list[BBox]:
        boxes, _ = LocateAnythingWorker._parse_box_content(answer, width, height)
        return boxes

    @staticmethod
    def parse_points(answer: str, width: int, height: int) -> list[tuple[int, int]]:
        _, points = LocateAnythingWorker._parse_box_content(answer, width, height)
        return points

    def detect(self, image, categories: list[str]) -> list[BBox]:
        cats = ", ".join(categories)
        prompt = f"Locate all the instances that matches the following description: {cats}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def ground(self, image, phrase: str) -> list[BBox]:
        prompt = f"Locate all the instances that match the following description: {phrase}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def point(self, image, phrase: str) -> list[tuple[int, int]]:
        prompt = f"Point to: {phrase}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_points(answer, w, h)

    def gui_locate(self, image, element: str) -> list[BBox]:
        prompt = f"Locate the region that matches the following description: {element}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def detect_text(self, image) -> list[BBox]:
        prompt = "Detect all the text in box format."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def ground_text(self, image, phrase: str) -> list[BBox]:
        prompt = f"Please locate the text referred as {phrase}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def analyze_layout(self, image) -> dict:
        prompt = "Detect all the text and UI elements in box format."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        boxes = self.parse_boxes(answer, w, h)
        return {"size": (w, h), "elements": [{"bbox": b} for b in boxes], "count": len(boxes)}
