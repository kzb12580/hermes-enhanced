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

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    _HAS_SLOWAPI = True
except ImportError:
    _HAS_SLOWAPI = False

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
import os
from pathlib import Path

# 日志文件路径
_log_dir = Path.home() / ".hermes" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "desktop-backend.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("hermes-backend")
logger.info("日志文件: %s", _log_file)

# ---------------------------------------------------------------------------
# CUDA PATH auto-detection — 启动时自动添加 CUDA 到 PATH
# ---------------------------------------------------------------------------
def _setup_cuda_path():
    """自动检测并添加 CUDA bin 目录到 PATH"""
    import glob
    import platform
    
    if platform.system() != "Windows":
        return
    
    # 检查 PATH 中是否已有 CUDA
    path_dirs = os.environ.get("PATH", "").split(";")
    for d in path_dirs:
        if "NVIDIA GPU Computing Toolkit" in d and "CUDA" in d:
            # 已经在 PATH 中
            return
    
    # 搜索常见 CUDA 安装路径
    cuda_patterns = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin",
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\lib\x64",
    ]
    
    cuda_bins = []
    for pattern in cuda_patterns:
        cuda_bins.extend(glob.glob(pattern))
    
    if cuda_bins:
        # 按版本号排序，取最新版本
        cuda_bins.sort(reverse=True)
        new_path = ";".join(cuda_bins) + ";" + os.environ.get("PATH", "")
        os.environ["PATH"] = new_path
        logger.info(f"已添加 CUDA 到 PATH: {cuda_bins[0]}")

# 启动时执行
_setup_cuda_path()


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

# Rate limiting: 60 requests per minute (optional dependency)
if _HAS_SLOWAPI:
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
    return JSONResponse(status_code=500, content={"error": f"Internal server error: {type(exc).__name__}: {str(exc)[:500]}", "success": False})


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
