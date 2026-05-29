#!/bin/bash
# Hermes Desktop PC 自动化 — 一键安装
set -e

echo "========================================="
echo "  Hermes Desktop PC 自动化 安装"
echo "========================================="

# Python 依赖
echo "[1/3] 安装 Python 依赖..."
pip install pyautogui pygetwindow pyperclip Pillow python-docx python-pptx openpyxl pytesseract opencv-python-headless

# PyTorch (需要根据CUDA版本选择)
echo "[2/3] 安装 PyTorch..."
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

# LocateAnything-3B
echo "[3/3] 下载 LocateAnything-3B 模型..."
python3 -c "
from transformers import AutoModelForCausalLM, AutoProcessor
print('Downloading model...')
AutoProcessor.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True)
AutoModelForCausalLM.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True)
print('Model downloaded!')
"

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "工具列表:"
echo "  screen_capture  - 截图"
echo "  gui_locate      - AI视觉定位"
echo "  gui_click       - 鼠标点击"
echo "  gui_type        - 键盘输入"
echo "  gui_hotkey      - 快捷键"
echo "  create_word     - Word文档"
echo "  create_ppt      - PPT演示文稿"
echo "  create_excel    - Excel表格"
echo "  open_app        - 启动应用"
echo "  clipboard       - 剪贴板"
echo "  screen_ocr      - OCR文字识别"
