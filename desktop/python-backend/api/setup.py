"""
Setup API — 首次启动引导、依赖安装、模型下载、网络诊断
前端通过 SSE 获取实时进度
"""
import asyncio
import json
import logging
import os
import sys
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("hermes-backend.setup")
router = APIRouter()

# ── 安装状态（进程级单例）──────────────────────────────────────────────────
_install_state = {
    "running": False,
    "phase": "idle",       # idle / deps / pytorch / model / tesseract / done / error
    "progress": 0,         # 0-100
    "message": "",
    "error": None,
    "log": [],             # 最近日志行
}
_install_lock = asyncio.Lock()


def _emit(phase: str, progress: int, message: str, error: str = None):
    """更新安装状态"""
    _install_state["phase"] = phase
    _install_state["progress"] = progress
    _install_state["message"] = message
    _install_state["error"] = error
    _install_state["log"].append(f"[{phase}] {message}")
    if len(_install_state["log"]) > 200:
        _install_state["log"] = _install_state["log"][-100:]


# ── Pydantic 模型 ────────────────────────────────────────────────────────

class NetworkConfig(BaseModel):
    proxy: Optional[str] = None
    proxy_mode: Optional[str] = None   # auto / manual / disabled
    hf_mirror: Optional[str] = None    # official / hf-mirror / custom URL
    pypi_mirror: Optional[str] = None  # official / tuna / aliyun / custom URL


class InstallRequest(BaseModel):
    skip_model: bool = False
    skip_tesseract: bool = False
    force_model: bool = False


# ── 端点 ──────────────────────────────────────────────────────────────────

@router.get("/api/setup/status")
async def get_setup_status():
    """获取当前安装状态"""
    # 检测已有依赖
    deps = _check_installed_deps()
    return {
        "running": _install_state["running"],
        "phase": _install_state["phase"],
        "progress": _install_state["progress"],
        "message": _install_state["message"],
        "error": _install_state["error"],
        "deps": deps,
    }


@router.get("/api/setup/status/stream")
async def stream_setup_status():
    """SSE 实时推送安装进度"""
    async def event_generator():
        last_phase = None
        last_progress = -1
        idle_ticks = 0
        MAX_IDLE = 600  # 5分钟无变化则关闭 (0.5s/tick)
        try:
            while True:
                changed = (_install_state["phase"] != last_phase or
                           _install_state["progress"] != last_progress)
                if changed:
                    data = json.dumps({
                        "phase": _install_state["phase"],
                        "progress": _install_state["progress"],
                        "message": _install_state["message"],
                        "error": _install_state["error"],
                    }, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    last_phase = _install_state["phase"]
                    last_progress = _install_state["progress"]
                    idle_ticks = 0
                else:
                    idle_ticks += 1
                    # 心跳防代理超时
                    if idle_ticks % 120 == 0:
                        yield ": heartbeat\n\n"

                # 终态检测
                if _install_state["phase"] in ("done", "error") and not _install_state["running"]:
                    yield f"data: {json.dumps({'phase': _install_state['phase'], 'progress': _install_state['progress'], 'message': _install_state['message'], 'error': _install_state['error']}, ensure_ascii=False)}\n\n"
                    break

                # 超时保护
                if idle_ticks >= MAX_IDLE:
                    break

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass  # 客户端断开

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/setup/install")
async def start_install(req: InstallRequest):
    """启动依赖安装（后台异步执行）"""
    async with _install_lock:
        if _install_state["running"]:
            raise HTTPException(status_code=409, detail="安装正在进行中")

        _install_state["running"] = True
        _install_state["phase"] = "starting"
        _install_state["progress"] = 0
        _install_state["error"] = None
        _install_state["log"] = []

    # 后台执行安装
    asyncio.create_task(_run_install(req))
    return {"success": True, "message": "安装已启动"}


@router.post("/api/setup/cancel")
async def cancel_install():
    """取消安装"""
    _install_state["running"] = False
    _install_state["phase"] = "idle"
    _install_state["message"] = "已取消"
    return {"success": True}


@router.get("/api/setup/network")
async def get_network_config():
    """获取网络配置"""
    try:
        from network_manager import load_network_config, detect_clash, detect_system_proxy, detect_env_proxy
        config = load_network_config()
        config["detected_proxy"] = detect_clash() or detect_system_proxy() or detect_env_proxy()
        return config
    except ImportError:
        return {"proxy": None, "proxy_mode": "auto"}


@router.put("/api/setup/network")
async def update_network_config(body: NetworkConfig):
    """更新网络配置"""
    try:
        from network_manager import save_network_config, apply_proxy_to_env, apply_hf_mirror_to_env
        updates = body.model_dump(exclude_none=True)
        save_network_config(updates)
        # 立即生效
        apply_proxy_to_env()
        apply_hf_mirror_to_env()
        return {"success": True}
    except ImportError:
        raise HTTPException(status_code=500, detail="network_manager 模块不可用")


@router.get("/api/setup/diagnose")
async def run_diagnosis():
    """网络诊断"""
    try:
        from network_manager import diagnose
        return diagnose()
    except ImportError:
        return {"error": "network_manager 模块不可用"}


@router.get("/api/setup/mirrors")
async def list_mirrors():
    """列出可用镜像源"""
    try:
        from network_manager import HF_MIRRORS, PYPI_MIRRORS
        return {"hf": HF_MIRRORS, "pypi": PYPI_MIRRORS}
    except ImportError:
        return {"hf": {}, "pypi": {}}



class ModelDownloadRequest(BaseModel):
    mirror: str = "hf-mirror"  # hf-mirror / modelscope / official


def _find_model_path():
    """Check if vision model is downloaded."""
    from pathlib import Path
    candidates = [
        Path.home() / ".hermes" / "desktop" / "models" / "LocateAnything-3B",
        Path.home() / ".hermes" / "desktop" / "models" / "nvidia--LocateAnything-3B",
    ]
    for p in candidates:
        if p.exists() and any(p.glob("*.safetensors")):
            return str(p)
    
    # Check HF cache - 检查根目录和 snapshots 子目录
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    if hf_cache.exists():
        for d in hf_cache.iterdir():
            if "LocateAnything" in d.name:
                # 1. 检查根目录（local_dir 下载会保存在这里）
                if any(d.glob("*.safetensors")):
                    return str(d)
                # 2. 检查 snapshots 子目录（默认缓存会保存在这里）
                snapshots = d / "snapshots"
                if snapshots.exists():
                    for s in snapshots.iterdir():
                        if any(s.glob("*.safetensors")):
                            return str(s)
    return None


@router.get("/api/setup/model-status")
async def model_status():
    """Check if vision model exists."""
    path = _find_model_path()
    return {"exists": path is not None, "path": path}


@router.delete("/api/setup/delete-model")
async def delete_model():
    """Delete vision model."""
    import shutil
    path = _find_model_path()
    if not path:
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        shutil.rmtree(path)
        return {"success": True, "deleted": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/setup/download-model")
async def download_model(req: ModelDownloadRequest):
    """Download LocateAnything-3B model with mirror selection"""
    import time as _time
    async with _install_lock:
        if _install_state["running"]:
            # Force reset if stuck for more than 30 minutes
            if _install_state.get("start_time") and _time.time() - _install_state["start_time"] > 1800:
                _install_state["running"] = False
                _install_state["phase"] = "idle"
                logger.warning("Force reset stuck installation")
            else:
                raise HTTPException(status_code=409, detail="Installation already running")

        _install_state["running"] = True
        _install_state["start_time"] = _time.time()
        _install_state["phase"] = "model"
        _install_state["progress"] = 0
        _install_state["error"] = None
        _install_state["log"] = []

    asyncio.create_task(_run_model_download(req.mirror))
    return {"success": True, "message": "Model download started"}


async def _run_model_download(mirror: str):
    """Download model in background thread with retry and proper progress tracking."""
    import os
    import time
    from pathlib import Path

    MAX_RETRIES = 3
    MODEL_ID = "nvidia/LocateAnything-3B"

    # 设置镜像
    if mirror == "hf-mirror":
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    elif mirror == "modelscope":
        # ModelScope 需要用专门的 SDK，不能用 HF_ENDPOINT
        _emit("model", 5, "ModelScope 镜像暂不支持，请使用 hf-mirror 或官方源")
        _install_state["running"] = False
        return
    else:
        os.environ.pop("HF_ENDPOINT", None)

    # 统一下载目录
    local_dir = Path.home() / ".cache" / "huggingface" / "hub" / MODEL_ID.replace("/", "--")

    # 清理损坏的缓存（强制清理，避免残留文件导致跳过下载）
    if local_dir.exists():
        _emit("model", 2, "清理旧缓存目录...")
        import shutil
        shutil.rmtree(local_dir, ignore_errors=True)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _emit("model", 5, f"开始下载 (尝试 {attempt}/{MAX_RETRIES})...")

            def do_download():
                from huggingface_hub import snapshot_download

                # 使用 force_download=True 强制重新下载，避免缓存问题
                # resume_download=True 在某些情况下会跳过下载
                snapshot_download(
                    MODEL_ID,
                    local_dir=str(local_dir),
                    force_download=True,
                    etag_timeout=60,
                )

            import concurrent.futures
            loop = asyncio.get_event_loop()

            # 带超时的下载
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = loop.run_in_executor(pool, do_download)
                try:
                    await asyncio.wait_for(future, timeout=1800)  # 30 分钟超时
                except asyncio.TimeoutError:
                    _emit("error", _install_state["progress"],
                          "下载超时 (30 分钟)", "timeout")
                    _install_state["running"] = False
                    return

            # 验证下载完整性
            _emit("model", 95, "验证模型文件...")
            if _verify_model_files(local_dir):
                _emit("done", 100, "✅ 模型下载完成!")
                _install_state["running"] = False
                return
            else:
                if attempt < MAX_RETRIES:
                    _emit("model", 5, f"文件不完整，{5}秒后重试...")
                    await asyncio.sleep(5)
                    continue
                else:
                    _emit("error", _install_state["progress"],
                          "下载完成但文件不完整，请手动检查", "incomplete")
                    _install_state["running"] = False
                    return

        except Exception as e:
            logger.warning("Download attempt %d failed: %s", attempt, e)
            if attempt < MAX_RETRIES:
                wait_time = attempt * 10  # 指数退避
                _emit("model", 5, f"下载失败，{wait_time}秒后重试... ({e})")
                await asyncio.sleep(wait_time)
            else:
                import traceback
                tb = traceback.format_exc()
                logger.exception("Model download failed after %d attempts", MAX_RETRIES)
                _emit("error", _install_state["progress"],
                      f"下载失败 (已重试 {MAX_RETRIES} 次): {e}\n{tb}", "download_failed")
                _install_state["running"] = False
                return


def _verify_model_files(model_dir: Path) -> bool:
    """Verify model files are complete and valid."""
    import os
    if not model_dir.exists():
        return False

    # 检查关键文件存在且大小 > 0
    required_patterns = ["*.safetensors", "config.json"]
    for pattern in required_patterns:
        files = list(model_dir.glob(pattern))
        if not files:
            logger.warning("Missing model files matching: %s", pattern)
            return False
        for f in files:
            if f.stat().st_size == 0:
                logger.warning("Empty model file: %s", f)
                return False

    # 检查是否有未完成的下载
    incomplete = list(model_dir.glob("*.incomplete"))
    if incomplete:
        logger.warning("Found %d incomplete download files", len(incomplete))
        return False

    return True

# ── 依赖检测 ──────────────────────────────────────────────────────────────

def _check_installed_deps() -> dict:
    """检测已安装的依赖"""
    deps = {}

    # Python
    deps["python"] = {"ok": True, "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"}

    # PyTorch
    try:
        import torch
        deps["pytorch"] = {
            "ok": True,
            "version": torch.__version__,
            "cuda": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as e:
        deps["pytorch"] = {"ok": False, "error": str(e)[:100]}

    # Transformers
    try:
        import transformers
        deps["transformers"] = {"ok": True, "version": transformers.__version__}
    except ImportError:
        deps["transformers"] = {"ok": False}

    # Pillow
    try:
        import PIL
        deps["pillow"] = {"ok": True, "version": PIL.__version__}
    except ImportError:
        deps["pillow"] = {"ok": False}

    # pyautogui
    try:
        import pyautogui
        deps["pyautogui"] = {"ok": True}
    except ImportError:
        deps["pyautogui"] = {"ok": False}

    # Tesseract
    import shutil
    deps["tesseract"] = {"ok": shutil.which("tesseract") is not None}

    # LocateAnything 模型
    try:
        from huggingface_hub import try_to_load_from_cache
        cached = try_to_load_from_cache("nvidia/LocateAnything-3B", "config.json")
        deps["model_locate_anything"] = {"ok": cached is not None and not isinstance(cached, str)}
    except ImportError:
        deps["model_locate_anything"] = {"ok": False}

    # Office
    try:
        import docx
        deps["python-docx"] = {"ok": True}
    except ImportError:
        deps["python-docx"] = {"ok": False}

    try:
        import pptx
        deps["python-pptx"] = {"ok": True}
    except ImportError:
        deps["python-pptx"] = {"ok": False}

    try:
        import openpyxl
        deps["openpyxl"] = {"ok": True}
    except ImportError:
        deps["openpyxl"] = {"ok": False}

    return deps


# ── 后台安装执行 ──────────────────────────────────────────────────────────

async def _run_install(req: InstallRequest):
    """后台执行安装（直接在进程内运行，避免子进程路径问题）"""
    try:
        # 定位 tools 目录并加入 Python 路径
        tools_dir = Path(__file__).parent.parent / "tools"
        if not tools_dir.exists():
            tools_dir = Path(__file__).parent.parent.parent.parent / "iteration" / "hermes_upgrades" / "desktop_tools"
        
        if not tools_dir.exists():
            _emit("error", 0, f"找不到 tools 目录", "script_not_found")
            _install_state["running"] = False
            return

        # 确保 tools 目录在 Python 路径中
        tools_str = str(tools_dir)
        if tools_str not in sys.path:
            sys.path.insert(0, tools_str)
        
        # 确保 backend 目录在 Python 路径中（network_manager 在这里）
        backend_dir = str(Path(__file__).parent.parent)
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        _emit("deps", 5, "正在加载安装脚本...")
        
        # 动态导入 setup_deps 模块
        import importlib
        setup_module = importlib.import_module("setup_deps")
        
        _emit("deps", 10, "开始安装依赖...")
        
        # 在线程中运行（setup() 是同步阻塞的）
        import concurrent.futures
        loop = asyncio.get_event_loop()
        
        def run_setup():
            # Capture setup() print output and forward to _emit() for frontend progress
            import io

            class _ProgressCapture:
                def write(self, text):
                    if text and text.strip():
                        line = text.strip()
                        phase = "deps"
                        for kw, ph in [("PyTorch", "pytorch"), ("模型", "model"),
                                       ("LocateAnything", "model"), ("Tesseract", "tesseract"),
                                       ("验证", "verify")]:
                            if kw in line:
                                phase = ph
                                break
                        _emit(phase, _estimate_progress(phase, line), line)
                    return len(text) if text else 0
                def flush(self):
                    pass

            old_stdout, old_stderr = sys.stdout, sys.stderr
            capture = _ProgressCapture()
            sys.stdout = capture
            sys.stderr = capture
            try:
                return setup_module.setup(
                    skip_model=req.skip_model,
                    skip_tesseract=req.skip_tesseract,
                    force_model=req.force_model,
                )
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
        
        with concurrent.futures.ThreadPoolExecutor() as pool:
            success = await loop.run_in_executor(pool, run_setup)
        
        if success:
            _emit("done", 100, "✅ 安装完成！")
        else:
            tail = "\n".join(_install_state["log"][-15:]) if _install_state["log"] else "无日志"
            _emit("error", _install_state["progress"],
                  f"安装脚本返回失败\n最近日志:\n{tail}", "install_failed")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.exception("安装异常")
        _emit("error", 0, f"安装异常: {e}\n{tb}", "exception")
    finally:
        _install_state["running"] = False



import re as _re
_PCT_RE = _re.compile(r"(\d+)%")

# 预计算阶段进度范围 (start%, end%)
_PHASE_RANGES = {
    "deps": (5, 30),
    "pytorch": (30, 50),
    "model": (50, 85),
    "tesseract": (85, 92),
    "verify": (92, 98),
    "done": (100, 100),
}

def _estimate_progress(phase: str, text: str) -> int:
    """根据阶段和输出估算进度"""
    start, end = _PHASE_RANGES.get(phase, (5, 30))
    span = end - start

    m = _PCT_RE.search(text)
    if m:
        pct = min(int(m.group(1)), 100)
        return min(start + pct * span // 100, 99)

    return min(start, 99)


# ── 一键检测修复 ──────────────────────────────────────────────────────

@router.post("/api/setup/repair")
async def repair_vision_deps():
    """一键检测并修复视觉模型依赖、Tesseract 路径等问题"""
    import importlib
    import subprocess
    results = []

    # 1. 检查 PyTorch + CUDA
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        results.append({
            "name": "PyTorch",
            "status": "ok",
            "detail": f"v{torch.__version__}, CUDA: {'✅ ' + torch.cuda.get_device_name(0) if cuda_ok else '❌ 不可用'}",
            "fixable": False,
        })
    except ImportError:
        results.append({
            "name": "PyTorch",
            "status": "error",
            "detail": "未安装",
            "fixable": True,
            "fix_cmd": "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124",
        })

    # 2. 检查视觉模型依赖
    vision_deps = [
        ("transformers", "transformers"),
        ("accelerate", "accelerate"),
        ("sentencepiece", "sentencepiece"),
        ("protobuf", "google.protobuf"),
        ("safetensors", "safetensors"),
        ("opencv-python-headless", "cv2"),
        ("peft", "peft"),
        ("decord", "decord"),
        ("lmdb", "lmdb"),
        ("numpy", "numpy"),
    ]
    for pkg_name, import_name in vision_deps:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", "installed")
            results.append({
                "name": pkg_name,
                "status": "ok",
                "detail": f"v{ver}",
                "fixable": False,
            })
        except ImportError:
            results.append({
                "name": pkg_name,
                "status": "missing",
                "detail": "未安装",
                "fixable": True,
                "fix_cmd": f"pip install {pkg_name}",
            })

    # 3. 检查视觉模型文件
    from pathlib import Path
    import os
    model_found = False
    model_path = None

    search_paths = [
        Path.home() / ".hermes" / "desktop" / "models" / "LocateAnything-3B",
        Path.home() / ".hermes" / "desktop" / "models" / "nvidia--LocateAnything-3B",
    ]
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    if hf_cache.exists():
        for d in hf_cache.iterdir():
            if "LocateAnything" in d.name:
                snapshots = d / "snapshots"
                if snapshots.exists():
                    for s in snapshots.iterdir():
                        search_paths.append(s)
                search_paths.append(d)

    env_path = os.environ.get("HERMES_VISION_MODEL_PATH")
    if env_path:
        search_paths.append(Path(env_path))

    for p in search_paths:
        if p.exists() and any(p.glob("*.safetensors")):
            model_found = True
            model_path = str(p)
            break

    results.append({
        "name": "LocateAnything-3B",
        "status": "ok" if model_found else "missing",
        "detail": model_path if model_found else "未找到模型文件",
        "fixable": not model_found,
        "fix_cmd": "在设置页面下载模型，或设置环境变量 HERMES_VISION_MODEL_PATH",
    })

    # 4. 检查 Tesseract
    import shutil
    tess_path = shutil.which("tesseract")
    tess_languages = []
    if tess_path:
        try:
            lang_out = subprocess.run(
                ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5
            )
            if lang_out.returncode == 0:
                tess_languages = [l.strip() for l in lang_out.stdout.strip().split("\n")[1:] if l.strip()]
        except Exception:
            pass

    if not tess_path and os.name == "nt":
        win_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Tesseract-OCR\tesseract.exe",
        ]
        for wp in win_paths:
            if os.path.isfile(wp):
                tess_path = wp
                break

    has_chi = "chi_sim" in tess_languages
    results.append({
        "name": "Tesseract OCR",
        "status": "ok" if tess_path else "missing",
        "detail": f"{tess_path or '未安装'}" + (f" (中文: {'✅' if has_chi else '❌'})" if tess_path else ""),
        "fixable": not tess_path,
        "fix_cmd": "下载安装: https://github.com/UB-Mannheim/tesseract/wiki (勾选 Chinese Simplified)",
    })

    # 5. 自动安装缺失的 Python 包
    auto_fixed = []
    for r in results:
        if r["status"] == "missing" and r.get("fixable") and r["name"] not in ("Tesseract OCR", "LocateAnything-3B", "PyTorch"):
            try:
                cmd = r["fix_cmd"]
                logger.info("Auto-fixing: %s", cmd)
                proc = subprocess.run(
                    cmd.split(), capture_output=True, text=True, timeout=300
                )
                if proc.returncode == 0:
                    r["status"] = "fixed"
                    r["detail"] = "已自动安装"
                    auto_fixed.append(r["name"])
                else:
                    r["detail"] = f"自动安装失败: {proc.stderr[:200]}"
            except Exception as e:
                r["detail"] = f"自动安装异常: {e}"

    all_ok = all(r["status"] in ("ok", "fixed") for r in results)
    return {
        "all_ok": all_ok,
        "results": results,
        "auto_fixed": auto_fixed,
        "summary": f"检测完成: {sum(1 for r in results if r['status'] in ('ok', 'fixed'))}/{len(results)} 项正常"
                   + (f"，自动修复了 {', '.join(auto_fixed)}" if auto_fixed else ""),
    }
