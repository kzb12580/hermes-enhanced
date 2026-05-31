"""Hermes Desktop — Python Backend (FastAPI).

Listens on 127.0.0.1:9876 and exposes REST + SSE endpoints consumed by the
Electron frontend.
"""

import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.chat import router as chat_router
from api.config import router as config_router
from api.models import router as models_router
from api.health import router as health_router
from api.memory import router as memory_router
from api.skills import router as skills_router
from api.setup import router as setup_router
from api.email import router as email_router
from api.workflow import router as workflow_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("hermes-backend")


# ---------------------------------------------------------------------------
# CLI argument parsing — only used when run directly
# ---------------------------------------------------------------------------

def _parse_args():
    """Parse CLI args, falling back to env vars, then defaults."""
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Desktop Python Backend")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HERMES_PORT", "9876")),
        help="Port to listen on (env: HERMES_PORT, default: 9876)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HERMES_HOST", "127.0.0.1"),
        help="Host to bind to (env: HERMES_HOST, default: 127.0.0.1)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Defaults for module-level use (when imported, not run directly)
# ---------------------------------------------------------------------------
_host = os.environ.get("HERMES_HOST", "127.0.0.1")
_port = int(os.environ.get("HERMES_PORT", "9876"))
_start_time = time.time()


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Hermes Desktop backend starting on %s:%d", _host, _port)
    yield
    logger.info("Hermes Desktop backend shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Hermes Desktop Backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting: 60 requests per minute
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow the Electron renderer (localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"error": "Internal server error", "success": False})


# ---------------------------------------------------------------------------
# 诊断 & 热重载 API
# ---------------------------------------------------------------------------

@app.get("/api/diagnose")
async def diagnose():
    """全面诊断后端状态 — 工具、模型、依赖、路径"""
    import importlib
    from pathlib import Path
    results = {
        "backend": {
            "uptime_seconds": round(time.time() - _start_time, 1),
            "host": _host,
            "port": _port,
            "python": sys.version,
        },
        "tools": [],
        "vision_model": {},
        "gpu": {},
        "skills_count": 0,
    }

    # 1. 检查已注册的工具
    try:
        from tools import all_tools
        tools = all_tools()
        for t in tools:
            tool_info = {"name": t.name, "timeout": getattr(t, "timeout", 60)}
            # 检查工具是否有 requires_network
            if hasattr(t, "requires_network"):
                tool_info["requires_network"] = t.requires_network
            results["tools"].append(tool_info)
        results["tools_count"] = len(tools)
    except Exception as e:
        results["tools_error"] = str(e)

    # 2. 检查 GPU
    try:
        import torch
        results["gpu"] = {
            "available": torch.cuda.is_available(),
            "name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "vram_gb": round(torch.cuda.get_device_properties(0).total_mem / (1024**3), 1) if torch.cuda.is_available() else 0,
            "cuda_version": torch.version.cuda,
            "torch_version": torch.__version__,
        }
    except ImportError:
        results["gpu"] = {"available": False, "error": "torch not installed"}

    # 3. 检查视觉模型
    try:
        from tools.vision_tool import VisionTool
        vt = VisionTool()
        model_path = vt._find_model_path()
        results["vision_model"] = {
            "found": model_path is not None,
            "path": str(model_path) if model_path else None,
            "env_var": os.environ.get("HERMES_VISION_MODEL_PATH"),
        }
    except Exception as e:
        results["vision_model"] = {"error": str(e)}

    # 4. 检查技能
    try:
        from api.skills_manager import skill_manager
        results["skills_count"] = len(skill_manager.get_all_skills())
    except Exception as e:
        results["skills_error"] = str(e)

    return results


@app.post("/api/tools/reload")
async def reload_tools():
    """热重载工具模块 — 修改代码后调用此接口生效"""
    try:
        from tools import _auto_register
        import tools as tools_module

        # 清空工具注册表
        tools_module._tools.clear()

        # 清除 Python 缓存
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("tools."):
                mod = sys.modules.pop(mod_name)
                # 删除 .pyc 缓存文件
                if hasattr(mod, "__file__") and mod.__file__:
                    import pathlib
                    pyc = pathlib.Path(mod.__file__).with_suffix(".pyc")
                    if pyc.exists():
                        pyc.unlink()

        # 重新导入和注册
        _auto_register()

        from tools import all_tools
        tools = all_tools()
        return {
            "success": True,
            "tools_count": len(tools),
            "tools": [t.name for t in tools],
        }
    except Exception as e:
        logger.error("Tool reload failed: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


class VisionModelPathRequest(BaseModel):
    path: str


@app.post("/api/config/vision-model-path")
async def set_vision_model_path(req: VisionModelPathRequest):
    """设置视觉模型路径 — 动态配置，不需要重启"""
    from pathlib import Path
    p = Path(req.path).expanduser()
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {p}")
    if not any(p.glob("*.safetensors")):
        raise HTTPException(status_code=400, detail=f"No .safetensors files found in: {p}")

    # 设置环境变量（当前进程生效）
    os.environ["HERMES_VISION_MODEL_PATH"] = str(p)

    # 尝试重置模型缓存
    try:
        from tools.vision_tool import VisionTool
        # 找到已注册的 vision_locate 工具并重置
        from tools import get_tool
        vt = get_tool("vision_locate")
        if vt:
            vt._model = None
            vt._processor = None
    except Exception:
        pass

    return {"success": True, "path": str(p), "message": "Model path updated. Next vision_locate call will use this path."}


# Register routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(skills_router)
app.include_router(setup_router)
app.include_router(email_router)
app.include_router(memory_router)
app.include_router(config_router)
app.include_router(models_router)
app.include_router(workflow_router)

# ---------------------------------------------------------------------------
# Graceful shutdown via signal
# ---------------------------------------------------------------------------

def _handle_signal(sig, _frame):
    logger.info("Received signal %s — shutting down", signal.Signals(sig).name)
    sys.exit(0)

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _args = _parse_args()
    _host = _args.host
    _port = _args.port
    uvicorn.run(
        app,
        host=_host,
        port=_port,
        log_level="info",
    )
