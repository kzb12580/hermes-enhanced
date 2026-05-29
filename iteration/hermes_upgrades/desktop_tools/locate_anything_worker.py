"""
LocateAnything-3B 视觉定位服务
为 Hermes Desktop 提供屏幕理解能力
"""
import io
import base64
import logging
from typing import Optional
from dataclasses import dataclass

_log = logging.getLogger(__name__)

@dataclass
class BBox:
    """边界框"""
    x1: int
    y1: int
    x2: int
    y2: int
    label: str = ""
    confidence: float = 0.0

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


class LocateAnythingWorker:
    """LocateAnything-3B 推理封装"""

    def __init__(self, model_path: str = "nvidia/LocateAnything-3B", device: str = "cuda"):
        self.model_path = model_path
        self.device = device
        self._model = None
        self._processor = None

    def _load(self):
        """懒加载模型"""
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        _log.info(f"Loading LocateAnything-3B from {self.model_path}...")
        self._processor = AutoProcessor.from_pretrained(
            self.model_path, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            device_map=self.device,
            trust_remote_code=True,
        )
        _log.info("LocateAnything-3B loaded successfully")

    def _run_inference(self, image, prompt: str) -> str:
        """运行推理"""
        self._load()
        import torch
        inputs = self._processor(text=prompt, images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) if hasattr(v, 'to') else v for k, v in inputs.items()}
        with torch.no_grad():
            output = self._model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
            )
        decoded = self._processor.decode(output[0], skip_special_tokens=False)
        return decoded

    @staticmethod
    def parse_boxes(answer: str, width: int, height: int) -> list[BBox]:
        """解析模型输出的边界框"""
        import re
        boxes = []
        pattern = r"<box>\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*</box>"
        for match in re.finditer(pattern, answer):
            x1 = int(match.group(1)) * width // 1000
            y1 = int(match.group(2)) * height // 1000
            x2 = int(match.group(3)) * width // 1000
            y2 = int(match.group(4)) * height // 1000
            boxes.append(BBox(x1=x1, y1=y1, x2=x2, y2=y2))
        return boxes

    @staticmethod
    def parse_points(answer: str, width: int, height: int) -> list[tuple[int, int]]:
        """解析模型输出的点坐标"""
        import re
        points = []
        pattern = r"<box>\s*(\d+)\s*,\s*(\d+)\s*</box>"
        for match in re.finditer(pattern, answer):
            x = int(match.group(1)) * width // 1000
            y = int(match.group(2)) * height // 1000
            points.append((x, y))
        return points

    # ── 高层 API ──────────────────────────────────────────────────────

    def detect(self, image, categories: list[str]) -> list[BBox]:
        """检测指定类别的所有物体"""
        cats = ", ".join(categories)
        prompt = f"Locate all the instances that matches the following description: {cats}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def ground(self, image, phrase: str) -> list[BBox]:
        """定位自然语言描述的物体"""
        prompt = f"Locate all the instances that match the following description: {phrase}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def point(self, image, phrase: str) -> list[tuple[int, int]]:
        """指向定位"""
        prompt = f"Point to: {phrase}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_points(answer, w, h)

    def gui_locate(self, image, element: str) -> list[BBox]:
        """GUI元素定位 — 找按钮、输入框、菜单等"""
        prompt = f"Locate the region that matches the following description: {element}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def detect_text(self, image) -> list[BBox]:
        """检测屏幕上的所有文字"""
        prompt = "Detect all the text in box format."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def ground_text(self, image, phrase: str) -> list[BBox]:
        """定位指定文字"""
        prompt = f"Please locate the text referred as {phrase}."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        return self.parse_boxes(answer, w, h)

    def analyze_layout(self, image) -> dict:
        """分析屏幕/文档布局"""
        prompt = "Detect all the text and UI elements in box format."
        answer = self._run_inference(image, prompt)
        w, h = image.size
        boxes = self.parse_boxes(answer, w, h)
        return {
            "size": (w, h),
            "elements": [{"bbox": b, "label": b.label} for b in boxes],
            "count": len(boxes),
        }
