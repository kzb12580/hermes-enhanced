"""Environment variable configuration utilities for Hermes Agent modules.

Provides helpers for reading deployment-specific overrides from environment
variables with sensible defaults. All helpers follow the pattern:

    HERMES_<MODULE>_<PARAMETER>

Usage::

    from config import env_int, env_float, env_str

    class MyModule:
        def __init__(self, max_workers: int = None):
            self.max_workers = env_int("HERMES_MAX_WORKERS", max_workers or 8)
"""

from __future__ import annotations

import os
from typing import Optional

__all__ = ["env_int", "env_float", "env_str", "env_bool"]


def env_int(name: str, default: int) -> int:
    """Read an integer from an environment variable, falling back to *default*.

    Args:
        name: Environment variable name (e.g. ``"HERMES_MAX_WORKERS"``).
        default: Fallback value if the env var is unset or not a valid int.

    Returns:
        The integer value.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def env_float(name: str, default: float) -> float:
    """Read a float from an environment variable, falling back to *default*.

    Args:
        name: Environment variable name.
        default: Fallback value.

    Returns:
        The float value.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


def env_str(name: str, default: str) -> str:
    """Read a string from an environment variable, falling back to *default*.

    Args:
        name: Environment variable name.
        default: Fallback value.

    Returns:
        The string value.
    """
    return os.environ.get(name, default)


def env_bool(name: str, default: bool) -> bool:
    """Read a boolean from an environment variable.

    Recognises ``1``, ``true``, ``yes``, ``on`` (case-insensitive) as True.
    Everything else (including empty string) is False.

    Args:
        name: Environment variable name.
        default: Fallback value.

    Returns:
        The boolean value.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")
