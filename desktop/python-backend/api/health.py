"""Health check endpoint."""

import time
from fastapi import APIRouter

router = APIRouter()

_start_time = time.time()
VERSION = "2.8.0"


@router.get("/api/health")
async def health_check():
    """Return backend health status, uptime, and version."""
    uptime_seconds = time.time() - _start_time
    return {
        "status": "healthy",
        "version": VERSION,
        "uptime_seconds": round(uptime_seconds, 2),
    }


@router.get("/api/performance")
async def performance_info():
    """Return host performance profile and adaptive limits."""
    try:
        from perf_detect import get_profile, get_limits
        return {
            "profile": get_profile(),
            "limits": get_limits(),
        }
    except Exception as e:
        return {"error": str(e)}
