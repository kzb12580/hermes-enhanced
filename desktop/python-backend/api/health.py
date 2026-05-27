"""Health check endpoint."""

import time
from fastapi import APIRouter

router = APIRouter()

_start_time = time.time()
VERSION = "0.1.0"


@router.get("/api/health")
async def health_check():
    """Return backend health status, uptime, and version."""
    uptime_seconds = time.time() - _start_time
    return {
        "status": "healthy",
        "version": VERSION,
        "uptime_seconds": round(uptime_seconds, 2),
    }
