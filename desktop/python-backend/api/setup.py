"""
Setup API — 首次启动引导、依赖安装、模型下载、网络诊断
前端通过 SSE 获取实时进度
"""
import asyncio
import json
import logging
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
    """后台执行安装（在子进程中运行 setup_deps.py）"""
    try:
        import subprocess

        # 定位 setup_deps.py
        script_dir = Path(__file__).parent.parent / "tools"
        setup_script = script_dir / "setup_deps.py"
        if not setup_script.exists():
            # 尝试 iteration 目录
            setup_script = Path(__file__).parent.parent.parent.parent / "iteration" / "hermes_upgrades" / "desktop_tools" / "setup_deps.py"

        if not setup_script.exists():
            _emit("error", 0, "找不到 setup_deps.py", "script_not_found")
            _install_state["running"] = False
            return

        _emit("deps", 5, "正在安装 Python 依赖...")

        # 构建命令
        cmd = [sys.executable, str(setup_script)]
        if req.skip_model:
            cmd.append("--skip-model")
        if req.skip_tesseract:
            cmd.append("--skip-tesseract")
        if req.force_model:
            cmd.append("--force-model")

        # 在子进程中运行，实时读取输出
        # 设置子进程强制 UTF-8 输出（解决 Windows 中文编码问题）
        import locale
        child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=child_env,
        )

        phase_map = {
            "Python": "deps",
            "PyTorch": "pytorch",
            "pip": "deps",
            "模型": "model",
            "LocateAnything": "model",
            "Tesseract": "tesseract",
            "验证": "verify",
        }

        while True:
            line = await process.stdout.readline()
            if not line:
                break

            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            # 根据输出判断阶段
            current_phase = "deps"
            for keyword, phase in phase_map.items():
                if keyword in text:
                    current_phase = phase
                    break

            # 估算进度
            progress = _estimate_progress(current_phase, text)
            _emit(current_phase, progress, text)

        await process.wait()

        if process.returncode == 0:
            _emit("done", 100, "✅ 安装完成！")
        else:
            _emit("error", _install_state["progress"], f"安装失败 (exit={process.returncode})", "install_failed")

    except Exception as e:
        logger.exception("安装异常")
        _emit("error", 0, str(e), "exception")
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
