"""
自动依赖检测与安装 — 让任何机器都能跑 LocateAnything-3B
支持: Windows / macOS / Linux, CPU / CUDA 11.8 / CUDA 12.x
"""
import os
import sys
import json
import shutil
import platform
import subprocess
import importlib.util
from pathlib import Path
from typing import Optional

# ── 常量 ──────────────────────────────────────────────────────────────────
REQUIREMENTS = [
    ("pyautogui", ">=0.9.54"),
    ("pygetwindow", ">=0.0.9"),
    ("pyperclip", ">=1.8.2"),
    ("Pillow", ">=10.0.0"),
    ("python-docx", ">=1.1.0"),
    ("python-pptx", ">=0.6.23"),
    ("openpyxl", ">=3.1.0"),
    ("transformers", ">=4.40.0,<5.0.0"),
    ("accelerate", ">=0.26.0"),
    ("sentencepiece", ">=0.1.99"),
    ("protobuf", ">=4.25.0"),
]

OPTIONAL_REQUIREMENTS = [
    ("pytesseract", ">=0.3.10"),  # 需要系统安装 tesseract
    ("opencv-python-headless", ">=4.8.0"),
]

MODEL_ID = "nvidia/LocateAnything-3B"
MODEL_SIZE_GB = 6.0
MIN_VRAM_GB = 6.0

# ── 工具函数 ──────────────────────────────────────────────────────────────

def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """执行命令，统一错误处理"""
    return subprocess.run(
        cmd, check=check, capture_output=capture,
        text=True, timeout=600
    )

def _pip_install(*args: str) -> bool:
    """执行 pip install"""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir"] + list(args)
    print(f"  📦 {' '.join(args[:3])}...")
    try:
        result = _run(cmd, check=False)
        if result.returncode == 0:
            return True
        print(f"  ⚠️  pip install 失败: {result.stderr[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ pip install 异常: {e}")
        return False

def _check_module(name: str) -> bool:
    """检查模块是否可导入"""
    try:
        spec = importlib.util.find_spec(name)
        return spec is not None
    except (ModuleNotFoundError, ValueError):
        return False

def _get_version(module_name: str) -> Optional[str]:
    """获取已安装模块版本"""
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, "__version__", getattr(mod, "VERSION", "unknown"))
    except Exception:
        return None

# ── 检测函数 ──────────────────────────────────────────────────────────────

def detect_os() -> str:
    """检测操作系统"""
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    elif s == "windows":
        return "windows"
    elif s == "linux":
        return "linux"
    return s

def detect_python() -> dict:
    """检测 Python 环境"""
    ver = sys.version_info
    return {
        "version": f"{ver.major}.{ver.minor}.{ver.micro}",
        "path": sys.executable,
        "ok": ver >= (3, 10),
        "recommend": "需要 Python >= 3.10" if ver < (3, 10) else None,
    }

def detect_cuda() -> dict:
    """检测 CUDA 环境"""
    result = {"available": False, "version": None, "driver": None, "gpus": [], "vram_gb": 0}

    # 方法1: nvidia-smi
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0:
            for line in out.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    result["gpus"].append(parts[0])
                    result["driver"] = parts[1]
                    result["vram_gb"] = max(result["vram_gb"], float(parts[2]) / 1024)
            result["available"] = True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 方法2: torch (如果已安装)
    if _check_module("torch"):
        try:
            import torch
            if torch.cuda.is_available():
                result["available"] = True
                result["version"] = torch.version.cuda
                if not result["gpus"]:
                    for i in range(torch.cuda.device_count()):
                        result["gpus"].append(torch.cuda.get_device_name(i))
                        props = torch.cuda.get_device_properties(i)
                        result["vram_gb"] = max(result["vram_gb"], props.total_mem / (1024**3))
        except Exception:
            pass

    # 方法3: 从 nvidia-smi 解析 CUDA 版本
    if not result["version"] and result["available"]:
        try:
            out = subprocess.run(
                ["nvidia-smi"], capture_output=True, text=True, timeout=10
            )
            import re
            m = re.search(r"CUDA Version:\s*([\d.]+)", out.stdout)
            if m:
                result["version"] = m.group(1)
        except Exception:
            pass

    return result

def detect_tesseract() -> dict:
    """检测 Tesseract OCR"""
    result = {"available": False, "path": None, "languages": []}
    try:
        out = subprocess.run(
            ["tesseract", "--version"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            result["available"] = True
            # 获取语言包
            lang_out = subprocess.run(
                ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5
            )
            if lang_out.returncode == 0:
                result["languages"] = [
                    l.strip() for l in lang_out.stdout.strip().split("\n")[1:]
                    if l.strip()
                ]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return result

# ── 安装函数 ──────────────────────────────────────────────────────────────

def install_python_deps() -> bool:
    """安装 Python 依赖"""
    print("\n📦 [1/4] 安装 Python 依赖包...")
    ok = True
    for pkg, ver in REQUIREMENTS:
        if not _pip_install(f"{pkg}{ver}"):
            ok = False
    for pkg, ver in OPTIONAL_REQUIREMENTS:
        _pip_install(f"{pkg}{ver}")  # 可选包失败不报错
    return ok

def install_pytorch(cuda_info: dict) -> bool:
    """安装 PyTorch（自动匹配 CUDA 版本）"""
    print("\n🔥 [2/4] 安装 PyTorch...")

    # 判断 CUDA 版本
    cuda_ver = cuda_info.get("version", "")
    if cuda_info["available"] and cuda_ver:
        major_minor = ".".join(cuda_ver.split(".")[:2])
        if major_minor.startswith("12"):
            index_url = "https://download.pytorch.org/whl/cu124"
            print(f"  检测到 CUDA {cuda_ver} → 安装 cu124 版本")
        elif major_minor.startswith("11"):
            index_url = "https://download.pytorch.org/whl/cu118"
            print(f"  检测到 CUDA {cuda_ver} → 安装 cu118 版本")
        else:
            index_url = None
            print(f"  CUDA {cuda_ver} 版本未知，安装默认版本")
    elif cuda_info["available"]:
        # 有 GPU 但不知道 CUDA 版本，装 cu124（最新兼容性最好）
        index_url = "https://download.pytorch.org/whl/cu124"
        print("  检测到 NVIDIA GPU，安装 cu124 版本")
    else:
        index_url = None
        print("  未检测到 GPU，安装 CPU 版本")

    # 检查已安装版本
    if _check_module("torch"):
        import torch
        cur_ver = torch.__version__
        cur_cuda = torch.version.cuda
        has_cuda = torch.cuda.is_available()
        print(f"  已安装 PyTorch {cur_ver} (CUDA: {cur_cuda})")

        # 如果已有 CUDA 版且 GPU 可用，跳过
        if has_cuda and cuda_info["available"]:
            print("  ✅ PyTorch 已就绪")
            return True
        # 如果没有 GPU 且已有 CPU 版，跳过
        if not cuda_info["available"] and not has_cuda:
            print("  ✅ PyTorch (CPU) 已就绪")
            return True

    # 安装
    if index_url:
        return _pip_install("torch", "torchvision", "--index-url", index_url)
    else:
        return _pip_install("torch", "torchvision")

def download_model(model_id: str = MODEL_ID, force: bool = False) -> bool:
    """下载 LocateAnything-3B 模型"""
    print(f"\n📥 [3/4] 下载模型 {model_id} (~{MODEL_SIZE_GB}GB)...")

    # 检查是否已下载
    try:
        from transformers.utils import cached_file
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache(model_id, "config.json")
        if cached and not isinstance(cached, str) and not force:
            print("  ✅ 模型已存在，跳过下载")
            return True
    except Exception:
        pass

    # 尝试用 huggingface-cli 下载（更快、支持断点续传）
    if shutil.which("huggingface-cli"):
        print("  使用 huggingface-cli 下载（支持断点续传）...")
        try:
            result = _run(
                ["huggingface-cli", "download", model_id,
                 "--local-dir", str(Path.home() / ".cache" / "huggingface" / "hub" / model_id.replace("/", "--"))],
                check=False
            )
            if result.returncode == 0:
                print("  ✅ 模型下载完成")
                return True
        except Exception:
            pass

    # 回退到 Python 下载
    print("  使用 transformers 下载...")
    try:
        from transformers import AutoProcessor, AutoModelForCausalLM
        AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        AutoModelForCausalLM.from_pretrained(
            model_id, trust_remote_code=True,
            device_map="auto", torch_dtype="auto"
        )
        print("  ✅ 模型下载完成")
        return True
    except Exception as e:
        print(f"  ❌ 模型下载失败: {e}")
        print(f"  💡 手动下载: huggingface-cli download {model_id}")
        return False

def install_tesseract(os_name: str) -> bool:
    """安装 Tesseract OCR（系统级）"""
    print("\n🔤 [4/4] 安装 Tesseract OCR...")
    info = detect_tesseract()
    if info["available"]:
        has_chinese = "chi_sim" in info["languages"]
        print(f"  ✅ 已安装，语言包: {info['languages']}")
        if not has_chinese:
            print("  ⚠️  缺少中文语言包，尝试安装...")
            if os_name == "linux":
                _run(["apt-get", "install", "-y", "tesseract-ocr-chi-sim"], check=False)
            elif os_name == "macos":
                _run(["brew", "install", "tesseract-lang"], check=False)
        return True

    # 安装
    if os_name == "linux":
        print("  安装 tesseract-ocr + 中文语言包...")
        result = _run(["apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-chi-sim"], check=False)
        if result.returncode != 0:
            print("  ⚠️  apt 安装失败，尝试 yum...")
            _run(["yum", "install", "-y", "tesseract"], check=False)
    elif os_name == "macos":
        print("  brew install tesseract tesseract-lang...")
        _run(["brew", "install", "tesseract", "tesseract-lang"], check=False)
    else:
        print("  ⚠️  Windows 请手动安装 Tesseract:")
        print("     https://github.com/UB-Mannheim/tesseract/wiki")
        print("     安装时勾选 'Chinese Simplified' 语言包")
        return False

    info = detect_tesseract()
    return info["available"]

# ── 验证函数 ──────────────────────────────────────────────────────────────

def verify_all() -> dict:
    """全面验证安装状态"""
    print("\n🔍 验证安装状态...")
    checks = {}

    # Python
    py = detect_python()
    checks["python"] = {"ok": py["ok"], "version": py["version"]}

    # PyTorch
    if _check_module("torch"):
        import torch
        checks["pytorch"] = {
            "ok": True,
            "version": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu_available": torch.cuda.is_available(),
            "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    else:
        checks["pytorch"] = {"ok": False, "error": "未安装"}

    # Transformers
    if _check_module("transformers"):
        import transformers
        checks["transformers"] = {"ok": True, "version": transformers.__version__}
    else:
        checks["transformers"] = {"ok": False, "error": "未安装"}

    # 关键依赖
    deps = ["PIL", "docx", "pptx", "openpyxl", "pyautogui"]
    for dep_name in deps:
        checks[dep_name] = {"ok": _check_module(dep_name)}

    # Tesseract
    ts = detect_tesseract()
    checks["tesseract"] = {"ok": ts["available"], "languages": ts.get("languages", [])}

    # 模型
    try:
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache(MODEL_ID, "config.json")
        checks["model"] = {"ok": cached is not None and not isinstance(cached, str)}
    except Exception:
        checks["model"] = {"ok": False}

    # GPU
    cuda = detect_cuda()
    checks["gpu"] = {
        "ok": cuda["available"],
        "gpus": cuda["gpus"],
        "vram_gb": round(cuda["vram_gb"], 1),
        "cuda_version": cuda["version"],
    }

    # 打印报告
    print("\n" + "=" * 50)
    print("  📋 安装验证报告")
    print("=" * 50)
    all_ok = True
    for name, info in checks.items():
        ok = info.get("ok", False)
        icon = "✅" if ok else "❌"
        detail = ""
        if "version" in info:
            detail = f" (v{info['version']})"
        elif "gpus" in info and info["gpus"]:
            detail = f" ({info['gpus'][0]}, {info['vram_gb']}GB)"
        elif "languages" in info and info["languages"]:
            detail = f" ({', '.join(info['languages'][:3])})"
        print(f"  {icon} {name:15s}{detail}")
        if not ok:
            all_ok = False

    print("=" * 50)
    if all_ok:
        print("  🎉 全部通过！可以使用 Hermes Desktop PC 自动化了")
    else:
        print("  ⚠️  部分组件未就绪，请查看上方 ❌ 项")
    print()

    return {"all_ok": all_ok, "checks": checks}

# ── 主流程 ────────────────────────────────────────────────────────────────

def setup(skip_model: bool = False, skip_tesseract: bool = False, force_model: bool = False) -> bool:
    """一键安装所有依赖"""
    print("=" * 50)
    print("  🚀 Hermes Desktop PC 自动化 — 依赖安装")
    print("=" * 50)

    # 检测环境
    os_name = detect_os()
    py = detect_python()
    cuda = detect_cuda()

    print(f"\n  系统: {os_name} ({platform.machine()})")
    print(f"  Python: {py['version']} ({py['path']})")
    print(f"  GPU: {cuda['gpus'] or '未检测到'}")
    if cuda["available"]:
        print(f"  CUDA: {cuda['version']} (驱动 {cuda['driver']})")
        print(f"  VRAM: {cuda['vram_gb']:.1f} GB")

    if not py["ok"]:
        print(f"\n❌ {py['recommend']}")
        return False

    # 1. Python 依赖
    install_python_deps()

    # 2. PyTorch
    install_pytorch(cuda)

    # 3. 模型
    if not skip_model:
        if cuda["vram_gb"] < MIN_VRAM_GB and cuda["available"]:
            print(f"\n⚠️  VRAM ({cuda['vram_gb']:.1f}GB) < 推荐 ({MIN_VRAM_GB}GB)")
            print("   模型可能以 CPU 模式运行，速度较慢")
        download_model(force=force_model)
    else:
        print("\n⏭️  跳过模型下载")

    # 4. Tesseract
    if not skip_tesseract:
        install_tesseract(os_name)
    else:
        print("\n⏭️  跳过 Tesseract 安装")

    # 5. 验证
    result = verify_all()
    return result["all_ok"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Desktop PC 自动化 — 一键依赖安装")
    parser.add_argument("--skip-model", action="store_true", help="跳过模型下载")
    parser.add_argument("--skip-tesseract", action="store_true", help="跳过 Tesseract 安装")
    parser.add_argument("--force-model", action="store_true", help="强制重新下载模型")
    parser.add_argument("--verify-only", action="store_true", help="仅验证，不安装")
    args = parser.parse_args()

    if args.verify_only:
        verify_all()
    else:
        success = setup(
            skip_model=args.skip_model,
            skip_tesseract=args.skip_tesseract,
            force_model=args.force_model,
        )
        sys.exit(0 if success else 1)
