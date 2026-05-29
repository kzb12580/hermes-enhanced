@echo off
echo ==========================================
echo   Hermes Desktop PC Automation - Install
echo ==========================================

echo [1/3] Installing Python dependencies...
pip install pyautogui pygetwindow pyperclip Pillow python-docx python-pptx openpyxl pytesseract

echo [2/3] Installing PyTorch (CUDA 12.4)...
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

echo [3/3] Installing Transformers + model deps...
pip install transformers opencv-python-headless

echo.
echo NOTE: Install Tesseract OCR separately:
echo   Download from: https://github.com/UB-Mannheim/tesseract/wiki
echo   During install, check 'Chinese Simplified' language pack
echo.
echo To download LocateAnything-3B model (~6GB):
echo   python -c "from transformers import AutoModelForCausalLM, AutoProcessor; AutoProcessor.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True); AutoModelForCausalLM.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True)"
echo.
echo ==========================================
echo   Done!
echo ==========================================
