"""Hermes Desktop - Python Backend (FastAPI).

Listens on 127.0.0.1:9876 and exposes REST + SSE endpoints consumed by the
Electron frontend.
"""
import os
import secrets
import signal
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ── 统一配置 ──────────────────────────────────────────────────────────────
from config import BACKEND_HOST, BACKEND_PORT, CORS_ORIGINS

# ── 全面日志系统 ──────────────────────────────────────────────────────────
from logger import get_logger, get_log_dir, get_log_files

logger = get_logger("hermes-backend")
api_logger = get_logger("hermes-backend.api")
_api_request_throttle = {}

# ── Bearer Token 认证 ─────────────────────────────────────────────────────
# 敏感路由需要 Bearer Token 认证，防止外部页面调用本地 API
AUTH_TOKEN = os.environ.get("HERMES_AUTH_TOKEN", "")
if not AUTH_TOKEN:
    # 自动生成随机 token（256 位，64 字符）
    AUTH_TOKEN = secrets.token_hex(32)
    logger.info("Auto-generated AUTH_TOKEN for this session")

# Sensitive routes that require Bearer token authentication
SENSITIVE_ROUTES = {
    "POST:/api/chat",
    "POST:/api/tools/reload",
    "DELETE:/api/chat/sessions",
    "POST:/api/chat/sessions",
    "POST:/api/memory",
    "DELETE:/api/memory",
}

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
_host = BACKEND_HOST
_port = BACKEND_PORT
_start_time = time.time()


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_files = get_log_files()
    logger.info("═══════════════════════════════════════════════")
    logger.info("Hermes Desktop backend starting on %s:%d", _host, _port)
    logger.info("日志目录: %s", get_log_dir())
    for name, path in log_files.items():
        logger.info("  %s → %s", name, path)
    logger.info("═══════════════════════════════════════════════")
    yield
    logger.info("Hermes Desktop backend shutting down")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Hermes Desktop Backend",
    version="1.1.6",
    lifespan=lifespan,
)

# Rate limiting: 60 requests per minute
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - allow only local/Electron renderer origins.
# Backend binds to 127.0.0.1 by default; avoid wildcard CORS so arbitrary web
# pages cannot call local desktop APIs from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 敏感路由认证中间件 ─────────────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """检查敏感路由的 Bearer Token 认证"""
    # Skip auth for health check and OPTIONS requests
    if request.method == "OPTIONS":
        return await call_next(request)
    
    path = request.url.path
    method = request.method
    route_key = f"{method}:{path}"
    
    # Only check sensitive routes
    if route_key in SENSITIVE_ROUTES:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing Authorization header"}
            )
        token = auth_header[7:]  # Remove "Bearer " prefix
        if token != AUTH_TOKEN:
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid token"}
            )
    
    return await call_next(request)


# ── CSP 安全头中间件 ─────────────────────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """添加安全响应头"""
    response = await call_next(request)
    
    # Content-Security-Policy: 限制资源加载来源
    # 默认策略：仅允许同源，禁止内联脚本
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "  # Electron 需要 unsafe-eval
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https: wss:; "
        "frame-src 'none'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["Content-Security-Policy"] = csp
    
    # 其他安全头
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    
    return response


# ── API 请求日志中间件 ────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个 HTTP 请求的方法、路径、状态码、耗时"""
    start = time.time()
    method = request.method
    path = request.url.path
    query = str(request.url.query) if request.url.query else ""
    if query:
        # 避免把 api_key / token 等敏感查询参数写入 desktop-api.log
        from urllib.parse import parse_qsl, urlencode
        sensitive = {"api_key", "key", "token", "access_token", "refresh_token", "authorization"}
        query = urlencode([
            (k, "***REDACTED***" if k.lower() in sensitive else v)
            for k, v in parse_qsl(query, keep_blank_values=True)
        ])
    client = request.client.host if request.client else "unknown"

    _is_health_path = path.rstrip("/") == "/api/health"
    _skip_health_request_log = False
    if _is_health_path:
        _api_logger_name = getattr(api_logger, "name", "")
        _health_last_logged_at = _api_request_throttle.get(_api_logger_name)
        if _health_last_logged_at is None or (time.time() - _health_last_logged_at) > 30:
            _api_request_throttle[_api_logger_name] = time.time()
        else:
            _skip_health_request_log = True
    if not _skip_health_request_log:
        api_logger.debug("→ %s %s%s  [client=%s]", method, path, f"?{query}" if query else "", client)

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = (time.time() - start) * 1000
        api_logger.error("✗ %s %s  %.0fms  EXCEPTION: %s", method, path, elapsed, exc, exc_info=True)
        raise

    elapsed = (time.time() - start) * 1000
    status = response.status_code
    if _is_health_path:
        if status >= 400 or elapsed > 100:
            api_logger.warning("← %s %s  %d  %.0fms", method, path, status, elapsed)
        elif not _skip_health_request_log:
            api_logger.info("← %s %s  %d  %.0fms", method, path, status, elapsed)
    else:
        level = "error" if status >= 500 else "warning" if status >= 400 else "info"
        getattr(api_logger, level)(
            "← %s %s  %d  %.0fms", method, path, status, elapsed
        )
    return response

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={"error": "Internal server error", "success": False})


@app.post("/api/tools/reload")
async def reload_tools(request: Request):
    """热重载工具模块 — 修改代码后调用此接口生效（仅限本地访问）"""
    # 仅允许本地访问
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return {"success": False, "error": "仅允许本地访问"}
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


# ── Auth Token 端点（仅本地访问）────────────────────────────────────────────
@app.get("/api/auth/token")
async def get_auth_token(request: Request):
    """Get auth token for frontend (only accessible from localhost)."""
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return JSONResponse(
            status_code=403,
            content={"error": "Only accessible from localhost"}
        )
    return {"token": AUTH_TOKEN}

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
