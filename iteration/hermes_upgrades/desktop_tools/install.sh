#!/bin/bash
# Hermes Desktop PC Automation - Install
echo "========================================="
echo "  Hermes Desktop PC Automation - Install"
echo "========================================="

# Detect CUDA version
CUDA_VER="cpu"
if command -v nvidia-smi &> /dev/null; then
    CUDA_RAW=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
    if nvidia-smi 2>/dev/null | grep -q "CUDA Version: 12"; then
        CUDA_VER="cu124"
    elif nvidia-smi 2>/dev/null | grep -q "CUDA Version: 11"; then
        CUDA_VER="cu118"
    fi
fi
echo "Detected CUDA: $CUDA_VER"

# Python deps
echo "[1/3] Installing Python dependencies..."
pip install pyautogui pygetwindow pyperclip Pillow python-docx python-pptx openpyxl pytesseract opencv-python-headless

# PyTorch
echo "[2/3] Installing PyTorch..."
if [ "$CUDA_VER" = "cpu" ]; then
    pip install torch torchvision
else
    pip install torch torchvision --index-url https://download.pytorch.org/whl/$CUDA_VER
fi

# Transformers
echo "[3/3] Installing Transformers..."
pip install transformers

echo ""
echo "NOTE: Install Tesseract OCR for screen_ocr:"
echo "  Linux: sudo apt install tesseract-ocr tesseract-ocr-chi-sim"
echo "  macOS: brew install tesseract"
echo ""
echo "To download LocateAnything-3B model (~6GB):"
echo "  python3 -c \"from transformers import AutoModelForCausalLM, AutoProcessor; AutoProcessor.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True); AutoModelForCausalLM.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True)\""
echo ""
echo "========================================="
echo "  Done!"
echo "========================================="
