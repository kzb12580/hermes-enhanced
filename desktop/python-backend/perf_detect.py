"""
Performance detection — auto-adapt tool limits to host capabilities.
Detects RAM, CPU cores, and GPU to set optimal parameters.
"""

import logging
import os
import platform

logger = logging.getLogger("hermes-backend.perf")


def detect_performance_profile() -> dict:
    """Detect host performance and return adaptive settings."""
    profile = {
        "ram_gb": 0,
        "cpu_cores": os.cpu_count() or 2,
        "platform": platform.system(),
        "has_gpu": False,
        "tier": "medium",  # low / medium / high
    }

    # Detect RAM
    try:
        import psutil
        mem = psutil.virtual_memory()
        profile["ram_gb"] = round(mem.total / (1024 ** 3), 1)
    except ImportError:
        # Fallback: try /proc/meminfo on Linux
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        profile["ram_gb"] = round(kb / (1024 ** 2), 1)
                        break
        except Exception:
            profile["ram_gb"] = 8  # Assume 8GB default

    # Detect GPU (NVIDIA)
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            profile["has_gpu"] = True
            profile["gpu_info"] = result.stdout.strip().split("\n")[0]
    except Exception:
        pass

    # Determine performance tier
    ram = profile["ram_gb"]
    cores = profile["cpu_cores"]

    if ram >= 32 and cores >= 8:
        profile["tier"] = "high"
    elif ram >= 16 and cores >= 4:
        profile["tier"] = "medium"
    else:
        profile["tier"] = "low"

    logger.info("Performance profile: %s", profile)
    return profile


def get_adaptive_limits(profile: dict) -> dict:
    """Return adaptive limits based on performance profile."""
    tier = profile["tier"]

    limits = {
        "low": {
            "max_tool_iterations": 15,
            "max_tool_result_size": 8_000,      # 8KB
            "max_tool_calls_per_turn": 15,
            "max_content_length": 50_000,
            "tool_timeout": 120,
        },
        "medium": {
            "max_tool_iterations": 50,
            "max_tool_result_size": 32_000,     # 32KB
            "max_tool_calls_per_turn": 50,
            "max_content_length": 200_000,
            "tool_timeout": 300,
        },
        "high": {
            "max_tool_iterations": 90,
            "max_tool_result_size": 50_000,     # 50KB
            "max_tool_calls_per_turn": 100,
            "max_content_length": 500_000,
            "tool_timeout": 600,
        },
    }

    result = limits.get(tier, limits["medium"])
    logger.info("Adaptive limits (%s tier): %s", tier, result)
    return result


# Auto-detect on import
_performance_profile = None
_adaptive_limits = None


def get_profile() -> dict:
    global _performance_profile
    if _performance_profile is None:
        _performance_profile = detect_performance_profile()
    return _performance_profile


def get_limits() -> dict:
    global _adaptive_limits
    if _adaptive_limits is None:
        _adaptive_limits = get_adaptive_limits(get_profile())
    return _adaptive_limits
