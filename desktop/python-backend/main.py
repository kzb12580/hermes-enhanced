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

from api.chat import router as chat_router
from api.config import router as config_router
from api.models import router as models_router
from api.health import router as health_router
from api.memory import router as memory_router
from api.skills import router as skills_router

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

# CORS — allow the Electron renderer (localhost)
# Per CORS spec, allow_credentials=True is NOT allowed with allow_origins=['*'].
# Since we use wildcard origins, credentials must be False.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(skills_router)
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
