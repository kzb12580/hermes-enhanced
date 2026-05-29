@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ==========================================
echo   🚀 Hermes Desktop PC 自动化 - 安装器
echo ==========================================
echo.

:: ── 1. 检测 Python ──────────────────────────────────────────────────────
set PYTHON=
for %%P in (python3.12 python3.11 python3.10 python3 python py) do (
    where %%P >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=2" %%V in ('%%P --version 2^>^&1') do (
            set PYTHON=%%P
            echo [OK] Python %%V
            goto :found_python
        )
    )
)
echo [WARN] 未找到 Python，尝试安装...

:: 尝试用 winget 安装
where winget >nul 2>&1
if !errorlevel! equ 0 (
    echo 正在用 winget 安装 Python...
    winget install Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    set PYTHON=python
    goto :found_python
)

:: 尝试用 choco 安装
where choco >nul 2>&1
if !errorlevel! equ 0 (
    echo 正在用 choco 安装 Python...
    choco install python3 -y
    set PYTHON=python
    goto :found_python
)

echo.
echo ❌ 无法自动安装 Python
echo 请手动安装: https://www.python.org/downloads/
echo 安装时勾选 "Add Python to PATH"
pause
exit /b 1

:found_python

:: 确保 pip 可用
%PYTHON% -m pip --version >nul 2>&1
if !errorlevel! neq 0 (
    echo 安装 pip...
    %PYTHON% -m ensurepip --upgrade 2>nul
    if !errorlevel! neq 0 (
        curl -sS https://bootstrap.pypa.io/get-pip.py -o %TEMP%\get-pip.py
        %PYTHON% %TEMP%\get-pip.py
    )
)
echo [OK] pip 已就绪

:: ── 2. 检测 GPU / CUDA ─────────────────────────────────────────────────
set CUDA_VER=cu124
set GPU_NAME=未检测到

where nvidia-smi >nul 2>&1
if !errorlevel! equ 0 (
    for /f "tokens=* delims=" %%G in ('nvidia-smi --query-gpu^=name --format^=csv^,noheader 2^>nul') do (
        set GPU_NAME=%%G
    )
    for /f "tokens=* delims=" %%V in ('nvidia-smi 2^>nul ^| findstr /C:"CUDA Version"') do (
        echo [OK] GPU: !GPU_NAME! ^(%%V^)
    )
) else (
    echo [WARN] 未检测到 NVIDIA GPU，使用 CPU 模式
    set CUDA_VER=cpu
)

:: ── 3. 安装系统依赖 ──────────────────────────────────────────────────────
echo.
echo [INFO] 检查 Tesseract OCR...
where tesseract >nul 2>&1
if !errorlevel! neq 0 (
    echo [WARN] Tesseract 未安装
    echo   请手动安装: https://github.com/UB-Mannheim/tesseract/wiki
    echo   安装时勾选 "Chinese Simplified" 语言包
    echo.
    where winget >nul 2>&1
    if !errorlevel! equ 0 (
        echo 尝试用 winget 安装...
        winget install UB-Mannheim.TesseractOCR --silent --accept-package-agreements 2>nul
    )
) else (
    echo [OK] Tesseract 已安装
)

:: ── 4. 安装 Python 依赖 ─────────────────────────────────────────────────
echo.
echo [INFO] 📦 安装 Python 依赖包...
%PYTHON% -m pip install --upgrade pip --quiet

:: 核心依赖
set PACKAGES=pyautogui pygetwindow pyperclip Pillow python-docx python-pptx openpyxl transformers accelerate sentencepiece protobuf pytesseract opencv-python-headless

for %%P in (%PACKAGES%) do (
    %PYTHON% -m pip install %%P --quiet 2>nul
    if !errorlevel! equ 0 (
        echo   [OK] %%P
    ) else (
        echo   [WARN] %%P 安装失败
    )
)

:: ── 5. 安装 PyTorch ──────────────────────────────────────────────────────
echo.
echo [INFO] 🔥 安装 PyTorch...

:: 检查是否已有
%PYTHON% -c "import torch; print(torch.__version__)" >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] PyTorch 已安装
) else (
    if "%CUDA_VER%"=="cpu" (
        %PYTHON% -m pip install torch torchvision --quiet
    ) else (
        %PYTHON% -m pip install torch torchvision --index-url https://download.pytorch.org/whl/%CUDA_VER% --quiet
    )
    echo   [OK] PyTorch 安装完成
)

:: ── 6. 下载模型 ──────────────────────────────────────────────────────────
echo.
echo [INFO] 📥 检查 LocateAnything-3B 模型...

%PYTHON% -c "from huggingface_hub import try_to_load_from_cache; r = try_to_load_from_cache('nvidia/LocateAnything-3B', 'config.json'); exit(0 if r and not isinstance(r, str) else 1)" 2>nul
if !errorlevel! equ 0 (
    echo   [OK] 模型已存在
) else (
    echo   [INFO] 下载 LocateAnything-3B (~6GB)，请耐心等待...
    where huggingface-cli >nul 2>&1
    if !errorlevel! equ 0 (
        huggingface-cli download nvidia/LocateAnything-3B
    ) else (
        %PYTHON% -c "from transformers import AutoProcessor, AutoModelForCausalLM; print('下载 Processor...'); AutoProcessor.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True); print('下载 Model...'); AutoModelForCausalLM.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True, device_map='auto', torch_dtype='auto'); print('完成!')"
    )
    echo   [OK] 模型下载完成
)

:: ── 7. 验证 ──────────────────────────────────────────────────────────────
echo.
echo ==========================================
echo   📋 安装验证
echo ==========================================

%PYTHON% -c "import sys; checks = []; [checks.append((n, True, f())) if not (_:=lambda:None) else None for n, f in [('Python', lambda: f'v{sys.version.split()[0]}'), ('PyTorch', lambda: __import__('torch').__version__), ('CUDA', lambda: f'{__import__(chr(116)+chr(111)+chr(114)+chr(99)+chr(104)).version.cuda} ({__import__(chr(116)+chr(111)+chr(114)+chr(99)+chr(104)).cuda.get_device_name(0)})' if __import__(chr(116)+chr(111)+chr(114)+chr(99)+chr(104)).cuda.is_available() else 'CPU'), ('Transformers', lambda: __import__('transformers').__version__), ('Pillow', lambda: __import__('PIL').__version__)]]; [print(f'  {chr(9988) if ok else chr(10060)} {name:15s} {detail}') for name, ok, detail in checks]"

echo.
echo ==========================================
echo   ✅ 安装完成！
echo ==========================================
echo.
echo 使用方式:
echo   python -c "from locate_anything_worker import LocateAnythingWorker; w = LocateAnythingWorker(); print('OK')"
echo.
pause
