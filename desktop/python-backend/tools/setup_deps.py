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

# ── 网络代理/镜像自动配置 ──────────────────────────────────────────────────
try:
    from network_manager import (
        get_proxy, apply_proxy_to_env, apply_hf_mirror_to_env,
        apply_pypi_mirror_to_args, get_hf_mirror, get_pypi_mirror,
        load_network_config, save_network_config,
        detect_clash, detect_system_proxy, detect_env_proxy,
        HF_MIRRORS, PYPI_MIRRORS,
    )
    # 安装前自动应用代理和镜像
    apply_proxy_to_env()
    apply_hf_mirror_to_env()
    _HAS_NETWORK_MANAGER = True
except ImportError:
    _HAS_NETWORK_MANAGER = False

# ── 常量 ──────────────────────────────────────────────────────────────────
REQUIREMENTS = [
    ("pyautogui", ">=0.9.54"),
    ("pygetwindow", ">=0.0.9"),
    ("pyperclip", ">=1.8.2"),
    ("Pillow", ">=10.0.0"),
    ("python-docx", ">=1.1.0"),
    ("python-pptx", ">=0.6.23"),
    ("openpyxl", ">=3.1.0"),
    # Vision model dependencies (LocateAnything-3B)
    ("transformers", ">=4.40.0,<5.0.0"),
    ("accelerate", ">=0.26.0"),
    ("sentencepiece", ">=0.1.99"),
    ("protobuf", ">=4.25.0"),
    ("safetensors", ">=0.4.0"),
    ("opencv-python-headless", ">=4.8.0"),
    ("peft", ">=0.7.0"),
    ("decord", ">=0.6.0"),
    ("lmdb", ">=1.4.0"),
    ("numpy", ">=1.25.0"),
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
    # 注入 PyPI 镜像源
    if _HAS_NETWORK_MANAGER:
        cmd = apply_pypi_mirror_to_args(cmd)
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

# pip 包名 → 导入名映射（少数包的 pip 名和 import 名不同）
_PIP_TO_IMPORT = {
    "Pillow": "PIL",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "opencv-python-headless": "cv2",
    "pytesseract": "pytesseract",
}

def _check_pip_package(pkg_name: str) -> Optional[str]:
    """检查 pip 包是否已安装，返回版本号或 None"""
    import_name = _PIP_TO_IMPORT.get(pkg_name, pkg_name.replace("-", "_").lower())
    ver = _get_version(import_name)
    if ver:
        return ver
    # 二次尝试: 直接用包名检查
    if _check_module(import_name):
        return "installed"
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

    # 1. PATH 中查找
    try:
        out = subprocess.run(
            ["tesseract", "--version"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            result["available"] = True
            result["path"] = shutil.which("tesseract")
            lang_out = subprocess.run(
                ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5
            )
            if lang_out.returncode == 0:
                result["languages"] = [
                    l.strip() for l in lang_out.stdout.strip().split("\n")[1:]
                    if l.strip()
                ]
            return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. Windows 常见路径
    if os.name == "nt":
        win_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Tesseract-OCR\tesseract.exe",
            r"D:\Tesseract-OCR\tesseract.exe",
            r"C:\ProgramData\chocolatey\bin\tesseract.exe",
        ]
        for p in win_paths:
            if os.path.isfile(p):
                result["available"] = True
                result["path"] = p
                # 添加到 PATH
                parent = os.path.dirname(p)
                if parent not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = parent + os.pathsep + os.environ.get("PATH", "")
                # 获取语言包
                try:
                    lang_out = subprocess.run(
                        [p, "--list-langs"], capture_output=True, text=True, timeout=5
                    )
                    if lang_out.returncode == 0:
                        result["languages"] = [
                            l.strip() for l in lang_out.stdout.strip().split("\n")[1:]
                            if l.strip()
                        ]
                except Exception:
                    pass
                return result

    # 3. Windows 注册表
    if os.name == "nt":
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for subkey in [
                    r"SOFTWARE\Tesseract-OCR",
                    r"SOFTWARE\WOW6432Node\Tesseract-OCR",
                ]:
                    try:
                        with winreg.OpenKey(root, subkey) as key:
                            val, _ = winreg.QueryValueEx(key, "InstallDir")
                            exe = os.path.join(val, "tesseract.exe")
                            if os.path.isfile(exe):
                                result["available"] = True
                                result["path"] = exe
                                if val not in os.environ.get("PATH", ""):
                                    os.environ["PATH"] = val + os.pathsep + os.environ.get("PATH", "")
                                return result
                    except (FileNotFoundError, OSError):
                        continue
        except ImportError:
            pass

    return result

# ── 安装函数 ──────────────────────────────────────────────────────────────

def install_python_deps() -> bool:
    """安装 Python 依赖（自动跳过已安装的包）"""
    print("\n📦 [1/4] 安装 Python 依赖包...")
    ok = True
    skipped = 0
    for pkg, ver in REQUIREMENTS:
        existing = _check_pip_package(pkg)
        if existing:
            print(f"  ✅ {pkg} 已安装 (v{existing})，跳过")
            skipped += 1
            continue
        if not _pip_install(f"{pkg}{ver}"):
            ok = False
    for pkg, ver in OPTIONAL_REQUIREMENTS:
        existing = _check_pip_package(pkg)
        if existing:
            print(f"  ✅ {pkg} 已安装 (v{existing})，跳过")
            skipped += 1
            continue
        _pip_install(f"{pkg}{ver}")  # 可选包失败不报错
    if skipped:
        print(f"  📋 跳过 {skipped} 个已安装包")
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
    """下载 LocateAnything-3B 模型，支持断点续传和重试"""
    import time
    import shutil

    # 显示当前镜像配置
    try:
        from network_manager import get_hf_mirror, HF_MIRRORS
        mirror = get_hf_mirror()
        if mirror != HF_MIRRORS["official"]:
            print(f"\n📥 [3/4] 下载模型 {model_id} (~{MODEL_SIZE_GB}GB)...")
            print(f"  🌐 使用镜像: {mirror}")
        else:
            print(f"\n📥 [3/4] 下载模型 {model_id} (~{MODEL_SIZE_GB}GB)...")
    except ImportError:
        print(f"\n📥 [3/4] 下载模型 {model_id} (~{MODEL_SIZE_GB}GB)...")

    # 先检查是否已下载
    existing_path = _find_existing_model()
    if existing_path and not force:
        print(f"  ✅ 模型已存在: {existing_path}")
        return True

    # 统一下载目录
    local_dir = Path.home() / ".cache" / "huggingface" / "hub" / model_id.replace("/", "--")

    # 清理损坏的缓存（只有 refs 没有 blobs 的情况）
    if local_dir.exists():
        has_safetensors = any(local_dir.rglob("*.safetensors"))
        if not has_safetensors:
            print("  🗑️ 清理损坏的缓存目录...")
            shutil.rmtree(local_dir, ignore_errors=True)

    MAX_RETRIES = 3

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  尝试 {attempt}/{MAX_RETRIES}...")

            # 方法1: huggingface-cli (最快，支持断点续传)
            if shutil.which("huggingface-cli"):
                print("  使用 huggingface-cli 下载...")
                result = _run(
                    ["huggingface-cli", "download", model_id,
                     "--local-dir", str(local_dir)],
                    check=False, timeout=1800  # 30 分钟超时
                )
                if result.returncode == 0:
                    if _verify_model_files(local_dir):
                        print("  ✅ 模型下载完成")
                        return True
                    else:
                        print("  ⚠️ 文件不完整，继续重试...")
                        continue
                else:
                    print(f"  ⚠️ huggingface-cli 失败: {result.stderr[:200]}")

            # 方法2: snapshot_download (Python，强制重新下载)
            print("  使用 snapshot_download 下载...")
            from huggingface_hub import snapshot_download
            # 使用 force_download=True 强制重新下载，避免缓存问题
            snapshot_download(
                model_id,
                local_dir=str(local_dir),
                force_download=True,
            )

            # 验证完整性
            if _verify_model_files(local_dir):
                print("  ✅ 模型下载完成")
                return True
            else:
                print("  ⚠️ 文件不完整")
                if attempt < MAX_RETRIES:
                    time.sleep(5)
                    continue

        except Exception as e:
            error_msg = str(e)
            print(f"  ❌ 下载失败: {error_msg[:300]}")
            # 检测网络错误，提示切换镜像
            if "ConnectionError" in type(e).__name__ or "timeout" in error_msg.lower():
                print("  💡 网络连接失败，请检查网络或切换镜像源")
                print("  💡 设置 → 网络 → HuggingFace 镜像 → 选择 hf-mirror")
            if attempt < MAX_RETRIES:
                wait_time = attempt * 10
                print(f"  {wait_time}秒后重试...")
                time.sleep(wait_time)

    print(f"  ❌ 下载失败 (已重试 {MAX_RETRIES} 次)")
    print(f"  💡 手动下载: huggingface-cli download {model_id}")
    print(f"  💡 或设置镜像: 设置 → 网络 → HuggingFace 镜像")
    return False


def _verify_model_files(model_dir) -> bool:
    """验证模型文件完整性"""
    from pathlib import Path
    p = Path(model_dir) if not isinstance(model_dir, Path) else model_dir
    if not p.exists():
        return False

    # 检查关键文件
    for pattern in ["*.safetensors", "config.json"]:
        files = list(p.glob(pattern))
        if not files:
            return False
        for f in files:
            if f.stat().st_size == 0:
                return False

    # 检查未完成文件
    if list(p.glob("*.incomplete")):
        return False

    return True


def _find_existing_model() -> str | None:
    """搜索已下载的模型（支持多种路径），验证文件完整性"""
    from pathlib import Path
    import os

    def _is_valid_model(p: Path) -> bool:
        """检查模型目录是否完整（有非空的 .safetensors 文件，无 .incomplete 文件）"""
        if not p.exists():
            return False
        # 检查是否有 .safetensors 文件且非空
        safetensors = list(p.glob("*.safetensors"))
        if not safetensors:
            return False
        # 检查所有 safetensors 文件是否非空
        for f in safetensors:
            if f.stat().st_size == 0:
                return False
        # 检查是否有未完成的文件
        if list(p.glob("*.incomplete")):
            return False
        # 检查 config.json 是否存在
        if not (p / "config.json").exists():
            return False
        return True

    candidates = [
        Path.home() / ".hermes" / "desktop" / "models" / "LocateAnything-3B",
        Path.home() / ".hermes" / "desktop" / "models" / "nvidia--LocateAnything-3B",
    ]
    for p in candidates:
        if _is_valid_model(p):
            return str(p)

    # HF cache
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    if hf_cache.exists():
        for d in hf_cache.iterdir():
            if "LocateAnything" in d.name:
                snapshots = d / "snapshots"
                if snapshots.exists():
                    for s in snapshots.iterdir():
                        if _is_valid_model(s):
                            return str(s)
                if _is_valid_model(d):
                    return str(d)

    # 环境变量
    env_path = os.environ.get("HERMES_VISION_MODEL_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    return None


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
