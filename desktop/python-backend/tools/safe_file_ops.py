"""Safe file operations — atomic save, backup, verification.

Prevents file corruption from interrupted writes, disk full, etc.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import logging

_log = logging.getLogger(__name__)


def atomic_save(save_func, target_path: str) -> None:
    """Atomic save: write to temp file first, then rename.
    
    Args:
        save_func: Callable that takes a file path and writes to it
        target_path: Final destination path
    
    Raises:
        Any exception from save_func
    """
    target_dir = os.path.dirname(target_path) or "."
    os.makedirs(target_dir, exist_ok=True)
    
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    os.close(fd)
    try:
        save_func(tmp_path)
        # Verify temp file exists and has content
        if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise IOError(f"Save function produced empty file: {tmp_path}")
        os.replace(tmp_path, target_path)  # Atomic on Windows + Linux
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def backup_file(path: str) -> str | None:
    """Create a .bak backup before editing. Returns backup path or None."""
    if not os.path.isfile(path):
        return None
    bak_path = path + ".bak"
    try:
        shutil.copy2(path, bak_path)
        return bak_path
    except Exception as e:
        _log.warning("Failed to backup %s: %s", path, e)
        return None


def verify_write(path: str, expected_min_size: int = 1) -> bool:
    """Verify a file was written correctly."""
    try:
        stat = os.stat(path)
        return stat.st_size >= expected_min_size
    except OSError:
        return False
