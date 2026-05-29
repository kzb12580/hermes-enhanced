#!/bin/bash
# ============================================================
#  Hermes Desktop PC 自动化 — 一键安装脚本
#  自动检测: OS / Python / CUDA / 依赖 / 模型
#  支持: Ubuntu/Debian/CentOS/macOS
# ============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; }

echo ""
echo "=========================================="
echo "  🚀 Hermes Desktop PC 自动化 — 安装器"
echo "=========================================="
echo ""

# ── 1. 检测操作系统 ──────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
info "系统: $OS ($ARCH)"

# ── 2. 检测/安装 Python ──────────────────────────────────────────────────
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+\.\d+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            ok "Python $ver ($PYTHON)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    warn "未找到 Python >= 3.10，尝试安装..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y python3 python3-pip python3-venv
        PYTHON="python3"
    elif command -v yum &>/dev/null; then
        yum install -y python3 python3-pip
        PYTHON="python3"
    elif command -v brew &>/dev/null; then
        brew install python@3.12
        PYTHON="python3"
    else
        fail "无法自动安装 Python，请手动安装 Python >= 3.10"
        exit 1
    fi
    ver=$("$PYTHON" --version 2>&1)
    ok "已安装 $ver"
fi

# 确保 pip 可用
if ! "$PYTHON" -m pip --version &>/dev/null; then
    info "安装 pip..."
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || curl -sS https://bootstrap.pypa.io/get-pip.py | "$PYTHON"
fi
ok "pip 已就绪"

# ── 3. 检测 CUDA / GPU ──────────────────────────────────────────────────
CUDA_VER=""
GPU_NAME=""
VRAM_GB=0

if command -v nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
    VRAM_GB=$(echo "scale=1; $VRAM_MB / 1024" | bc 2>/dev/null || echo "0")

    # 从 nvidia-smi 输出解析 CUDA 版本
    CUDA_RAW=$(nvidia-smi 2>/dev/null | grep -oP 'CUDA Version:\s*\K[\d.]+' || true)
    if [ -n "$CUDA_RAW" ]; then
        CUDA_MAJOR=$(echo "$CUDA_RAW" | cut -d. -f1)
        if [ "$CUDA_MAJOR" = "12" ]; then
            CUDA_VER="cu124"
        elif [ "$CUDA_MAJOR" = "11" ]; then
            CUDA_VER="cu118"
        else
            CUDA_VER="cu124"  # 默认用最新
        fi
    else
        CUDA_VER="cu124"  # 有 GPU 但检测不到版本，默认 cu124
    fi

    ok "GPU: $GPU_NAME ($VRAM_GB GB, CUDA $CUDA_RAW)"
else
    warn "未检测到 NVIDIA GPU，将使用 CPU 模式"
    CUDA_VER="cpu"
fi

# ── 4. 安装系统依赖 ──────────────────────────────────────────────────────
info "安装系统依赖..."
if [ "$OS" = "Linux" ]; then
    if command -v apt-get &>/dev/null; then
        # X11 相关 (pyautogui 需要)
        apt-get install -y -qq \
            python3-tk python3-dev \
            scrot xdotool xclip \
            libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev libxinerama-dev \
            tesseract-ocr tesseract-ocr-chi-sim \
            2>/dev/null || true
        ok "apt 依赖已安装"
    elif command -v yum &>/dev/null; then
        yum install -y \
            python3-tkinter python3-devel \
            scrot xdotool xclip \
            libX11-devel libXext-devel libXrandr-devel libXcursor-devel libXi-devel \
            tesseract tesseract-langpack-chi-sim \
            2>/dev/null || true
        ok "yum 依赖已安装"
    fi
elif [ "$OS" = "Darwin" ]; then
    if command -v brew &>/dev/null; then
        brew install tesseract tesseract-lang scrot 2>/dev/null || true
        ok "brew 依赖已安装"
    fi
fi

# ── 5. 安装 Python 依赖 ──────────────────────────────────────────────────
echo ""
info "📦 安装 Python 依赖包..."
"$PYTHON" -m pip install --upgrade pip --quiet

# 包名 → 导入名映射（pip 名和 import 名不同的包）
pip_to_import() {
    case "$1" in
        Pillow) echo "PIL" ;;
        python-docx) echo "docx" ;;
        python-pptx) echo "pptx" ;;
        opencv-python-headless) echo "cv2" ;;
        pytesseract) echo "pytesseract" ;;
        python-*) echo "$1" | sed 's/python-//' | sed 's/-/_/g' ;;
        *) echo "$1" | sed 's/-/_/g' ;;
    esac
}

# 核心依赖
PACKAGES=(
    "pyautogui>=0.9.54"
    "pygetwindow>=0.0.9"
    "pyperclip>=1.8.2"
    "Pillow>=10.0.0"
    "python-docx>=1.1.0"
    "python-pptx>=0.6.23"
    "openpyxl>=3.1.0"
    "transformers>=4.40.0,<5.0.0"
    "accelerate>=0.26.0"
    "sentencepiece>=0.1.99"
    "protobuf>=4.25.0"
    "pytesseract>=0.3.10"
    "opencv-python-headless>=4.8.0"
)

SKIPPED=0
for pkg in "${PACKAGES[@]}"; do
    # 提取包名（去掉版本号）
    pkg_name=$(echo "$pkg" | sed 's/[><=].*//')
    import_name=$(pip_to_import "$pkg_name")
    if "$PYTHON" -c "import importlib.util; exit(0 if importlib.util.find_spec('$import_name') else 1)" 2>/dev/null; then
        ok "$pkg_name 已安装，跳过"
        SKIPPED=$((SKIPPED + 1))
    else
        "$PYTHON" -m pip install "$pkg" --quiet 2>/dev/null && ok "$pkg" || warn "跳过 $pkg"
    fi
done
[ "$SKIPPED" -gt 0 ] && info "📋 跳过 $SKIPPED 个已安装包"

# ── 6. 安装 PyTorch ──────────────────────────────────────────────────────
echo ""
info "🔥 安装 PyTorch..."

# 检查是否已有可用的 PyTorch
if "$PYTHON" -c "import torch; assert torch.cuda.is_available() or '$CUDA_VER'='cpu'" 2>/dev/null; then
    TORCH_VER=$("$PYTHON" -c "import torch; print(torch.__version__)" 2>/dev/null)
    ok "PyTorch $TORCH_VER 已安装"
else
    if [ "$CUDA_VER" = "cpu" ]; then
        "$PYTHON" -m pip install torch torchvision --quiet
    else
        "$PYTHON" -m pip install torch torchvision --index-url "https://download.pytorch.org/whl/$CUDA_VER" --quiet
    fi
    ok "PyTorch 安装完成"
fi

# ── 7. 下载模型 ──────────────────────────────────────────────────────────
echo ""
info "📥 检查 LocateAnything-3B 模型..."

MODEL_OK=$("$PYTHON" -c "
from huggingface_hub import try_to_load_from_cache
r = try_to_load_from_cache('nvidia/LocateAnything-3B', 'config.json')
print('yes' if r and not isinstance(r, str) else 'no')
" 2>/dev/null || echo "no")

if [ "$MODEL_OK" = "yes" ]; then
    ok "模型已存在"
else
    info "下载 LocateAnything-3B (~6GB)，请耐心等待..."
    if command -v huggingface-cli &>/dev/null; then
        huggingface-cli download nvidia/LocateAnything-3B
    else
        "$PYTHON" -c "
from transformers import AutoProcessor, AutoModelForCausalLM
print('下载 Processor...')
AutoProcessor.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True)
print('下载 Model...')
AutoModelForCausalLM.from_pretrained('nvidia/LocateAnything-3B', trust_remote_code=True, device_map='auto', torch_dtype='auto')
print('完成!')
"
    fi
    ok "模型下载完成"
fi

# ── 8. 验证 ──────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  📋 安装验证"
echo "=========================================="

"$PYTHON" -c "
import sys
checks = []

def check(name, fn):
    try:
        r = fn()
        checks.append((name, True, r))
    except Exception as e:
        checks.append((name, False, str(e)))

check('Python', lambda: f'v{sys.version.split()[0]}')
check('PyTorch', lambda: __import__('torch').__version__)
check('CUDA', lambda: f'{__import__(\"torch\").version.cuda} ({__import__(\"torch\").cuda.get_device_name(0)})' if __import__('torch').cuda.is_available() else 'CPU模式')
check('Transformers', lambda: __import__('transformers').__version__)
check('Pillow', lambda: __import__('PIL').__version__)
check('pyautogui', lambda: __import__('pyautogui').__version__)

for name, ok, detail in checks:
    icon = '✅' if ok else '❌'
    print(f'  {icon} {name:15s} {detail}')

print()
total = sum(1 for _, ok, _ in checks if ok)
print(f'  {total}/{len(checks)} 项通过')
"

echo ""
echo "=========================================="
echo "  ✅ 安装完成！"
echo "=========================================="
echo ""
echo "使用方式:"
echo "  $PYTHON -c \"from locate_anything_worker import LocateAnythingWorker; w = LocateAnythingWorker(); print('OK')\""
echo ""
