"""Hermes Desktop — Python Backend (FastAPI).

Listens on 127.0.0.1:9876 and exposes REST + SSE endpoints consumed by the
Electron frontend.
"""

import logging
import os
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
# Per CORS spec, allow_credentials=True is NOT allowed with allow_origins=['*'].
# Since we use wildcard origins, credentials must be False.
# CORS: 仅允许本地 Electron 前端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9876", "http://127.0.0.1:9876", "file://", "null"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return {"error": "Internal server error", "success": False}

# API Token 认证中间件
import secrets as _secrets
_API_TOKEN = _secrets.token_urlsafe(32)

@app.middleware("http")
async def auth_middleware(request, call_path):
    # 放行健康检查和 OPTIONS
    if request.url.path in ("/api/health", "/health") or request.method == "OPTIONS":
        return await call_path(request)
    # 验证 token
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token or token != _API_TOKEN:
        from starlette.responses import JSONResponse
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_path(request)

# 启动时输出 token 供 Electron 前端使用
logger.info("API Token: %s", _API_TOKEN)

# Register routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(skills_router)
app.include_router(setup_router)
app.include_router(email_router)
app.include_router(memory_router)
app.include_router(config_router)
app.include_router(models_router)

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
