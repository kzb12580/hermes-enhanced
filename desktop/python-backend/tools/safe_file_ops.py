"""
Safe file operations: atomic writes, verification, and backups.
Used by write_file tool, chunk_manager, and office_tools.
"""

import os
import shutil
import time
import logging
from pathlib import Path

logger = logging.getLogger("hermes-backend.safe_file_ops")


def atomic_save(write_fn, target_path: str) -> None:
    """Atomically save a file by writing to a temp file then renaming.
    
    Args:
        write_fn: Callable that takes a file path and writes content to it.
        target_path: Final destination path.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file in same directory (same filesystem for atomic rename)
    tmp_path = target.with_suffix(target.suffix + f".tmp.{os.getpid()}")
    try:
        write_fn(str(tmp_path))
        # Atomic rename (same filesystem)
        shutil.move(str(tmp_path), str(target))
    except Exception:
        # Clean up temp file on failure
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def verify_write(file_path: str, min_size: int = 0) -> bool:
    """Verify a file was written successfully.
    
    Args:
        file_path: Path to verify.
        min_size: Minimum expected file size in bytes.
    
    Returns:
        True if file exists and meets size requirement.
    """
    try:
        p = Path(file_path)
        if not p.exists():
            return False
        if not p.is_file():
            return False
        size = p.stat().st_size
        if size < min_size:
            logger.warning("File %s too small: %d < %d bytes", file_path, size, min_size)
            return False
        return True
    except Exception as e:
        logger.warning("Verify write failed for %s: %s", file_path, e)
        return False


def backup_file(file_path: str, backup_dir: str = "") -> str:
    """Create a backup of a file before overwriting.
    
    Args:
        file_path: Path to the file to back up.
        backup_dir: Optional directory for backups. Defaults to same directory.
    
    Returns:
        Path to the backup file, or empty string if backup failed.
    """
    try:
        src = Path(file_path)
        if not src.exists():
            return ""
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_name = f"{src.stem}.bak.{timestamp}{src.suffix}"
        
        if backup_dir:
            dst = Path(backup_dir) / backup_name
            dst.parent.mkdir(parents=True, exist_ok=True)
        else:
            dst = src.parent / backup_name
        
        shutil.copy2(str(src), str(dst))
        logger.info("Backed up %s → %s", file_path, dst)
        return str(dst)
    except Exception as e:
        logger.warning("Backup failed for %s: %s", file_path, e)
        return ""
