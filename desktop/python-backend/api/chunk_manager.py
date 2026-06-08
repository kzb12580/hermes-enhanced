"""Chunk manager — handles split/merge for large tool call arguments.

When a model's output token limit causes truncation on large tool calls
(write_file, execute_code), the backend splits content into numbered
chunks. This module stores chunks to temp files, merges them when
complete, and cleans up stale partial sets after timeout.

Chunk storage: <workspace>/.hermes_chunks/<file_id>/
  chunk_1.tmp  chunk_2.tmp  ...  chunk_N.tmp  meta.json
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path

from api.model_limits import CHUNK_TIMEOUT
from tools.safe_file_ops import atomic_save, verify_write

logger = logging.getLogger("hermes-backend.chunks")

# Default chunk dir (overridable for testing)
_CHUNK_DIR_NAME = ".hermes_chunks"


def _get_chunk_base(workspace: str | None = None) -> Path:
    """Get the base directory for chunk storage."""
    base = Path(workspace) if workspace else Path.cwd()
    return base / _CHUNK_DIR_NAME


def _file_id_for(target_path: str) -> str:
    """Generate a stable file ID from the target file path.
    
    Uses a hash to avoid filesystem issues with special chars in paths.
    """
    import hashlib
    return hashlib.md5(target_path.encode()).hexdigest()[:12]


def _chunk_dir(target_path: str, workspace: str | None = None) -> Path:
    """Get the chunk directory for a specific target file."""
    return _get_chunk_base(workspace) / _file_id_for(target_path)


def _meta_path(target_path: str, workspace: str | None = None) -> Path:
    return _chunk_dir(target_path, workspace) / "meta.json"


def _load_meta(target_path: str, workspace: str | None = None) -> dict:
    """Load chunk metadata. Returns {} if not found."""
    mp = _meta_path(target_path, workspace)
    if not mp.exists():
        return {}
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load chunk meta for %s: %s", target_path, e)
        return {}


def _save_meta(target_path: str, meta: dict, workspace: str | None = None) -> None:
    mp = _meta_path(target_path, workspace)
    mp.parent.mkdir(parents=True, exist_ok=True)
    import tempfile, os
    fd, tmp = tempfile.mkstemp(dir=str(mp.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(mp))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def store_chunk(
    target_path: str,
    chunk_index: int,
    total_chunks: int,
    content: str,
    workspace: str | None = None,
) -> dict:
    """Store a single chunk. Returns status dict.
    
    Args:
        target_path: Final file path (e.g., "slides.json")
        chunk_index: 1-based chunk number
        total_chunks: Total expected chunks
        content: Chunk content string
        workspace: Working directory (defaults to cwd)
    
    Returns:
        {"ok": True, "received": N, "total": M, "remaining": [...]}
        or {"ok": True, "merged": True, "path": "..."} if all chunks received
    """
    cd = _chunk_dir(target_path, workspace)
    cd.mkdir(parents=True, exist_ok=True)

    # Save chunk content
    chunk_file = cd / f"chunk_{chunk_index}.tmp"
    chunk_file.write_text(content, encoding="utf-8")

    # Update metadata
    meta = _load_meta(target_path, workspace)
    if not meta:
        meta = {
            "target_path": target_path,
            "total_chunks": total_chunks,
            "created_at": time.time(),
            "chunks_received": [],
        }
    # Update total_chunks in case model corrects it
    meta["total_chunks"] = total_chunks
    if chunk_index not in meta["chunks_received"]:
        meta["chunks_received"].append(chunk_index)
    meta["chunks_received"].sort()
    meta["last_updated"] = time.time()
    _save_meta(target_path, meta, workspace)

    logger.info(
        "Stored chunk %d/%d for %s (%d chars)",
        chunk_index, total_chunks, target_path, len(content),
    )

    received = set(meta["chunks_received"])
    expected = set(range(1, total_chunks + 1))
    remaining = sorted(expected - received)

    if not remaining:
        # All chunks received — merge and write
        return _merge_chunks(target_path, meta, workspace)

    return {
        "ok": True,
        "status": "chunk_received",
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "received": sorted(received),
        "remaining": remaining,
        "message": f"已收到第{chunk_index}/{total_chunks}块。请继续发送第{remaining[0]}块。",
    }


def _smart_merge(parts: list[str], target_path: str) -> str:
    """Smart merge that handles JSON array splits correctly.
    
    When a model splits a JSON array across chunks:
      chunk 1: [{...},{...}]
      chunk 2: [{...},{...}]
    Simple concatenation produces [{...},{...}][{...},{...}] (invalid).
    This function detects JSON arrays and merges them properly.
    """
    if len(parts) <= 1:
        return "".join(parts)
    
    # Only strip brackets if ALL chunks look like JSON arrays
    all_json_arrays = all(p.strip().startswith("[") and "]" in p.strip() for p in parts)
    if all_json_arrays:
        stripped = []
        for i, part in enumerate(parts):
            p = part.strip()
            # Strip trailing content after last ] (e.g. comma, newline)
            last_bracket = p.rfind("]")
            if last_bracket >= 0:
                p = p[:last_bracket + 1]
            # Strip leading [ for non-first chunks
            if i > 0 and p.startswith("["):
                p = p[1:]
            # Strip trailing ] for non-last chunks
            if i < len(parts) - 1 and p.endswith("]"):
                p = p[:-1]
            stripped.append(p)
        merged = ",".join(stripped)
        try:
            json.loads(merged)
            logger.info("Smart merge: detected JSON array split, merged %d parts correctly", len(parts))
            return merged
        except json.JSONDecodeError:
            pass  # Fall through to simple concat
    
    # Simple concatenation with newline safety for code/text
    fixed_parts = []
    for i, part in enumerate(parts):
        p = part
        if i < len(parts) - 1 and p and not p.endswith("\n"):
            p += "\n"
        fixed_parts.append(p)
    simple = "".join(fixed_parts)
    logger.info("Smart merge: %d parts, %d chars", len(parts), len(simple))
    return simple


def _merge_chunks(target_path: str, meta: dict, workspace: str | None = None) -> dict:
    """Merge all chunks into the target file and clean up."""
    cd = _chunk_dir(target_path, workspace)
    total = meta["total_chunks"]

    # Read and concatenate chunks in order
    parts = []
    for i in range(1, total + 1):
        chunk_file = cd / f"chunk_{i}.tmp"
        if not chunk_file.exists():
            return {
                "ok": False,
                "error": f"Missing chunk {i}, cannot merge. Please resend from chunk {i}.",
            }
        parts.append(chunk_file.read_text(encoding="utf-8"))

    full_content = _smart_merge(parts, target_path)

    # Write to target path
    target = Path(target_path)
    if not target.is_absolute():
        # Resolve relative to workspace
        base = Path(workspace) if workspace else Path.cwd()
        target = base / target
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_save(lambda p: Path(p).write_text(full_content, encoding="utf-8"), str(target))
    if not verify_write(str(target), len(full_content) // 2):
        logger.error("Write verification failed for %s", target_path)
        return {
            "ok": False,
            "error": f"Write verification failed for {target_path}",
            "status": "verify_failed",
        }

    # Clean up chunk directory. If it was the last active chunk set, remove the
    # empty .hermes_chunks base too so the user workspace only contains the
    # intended output files after a successful merge.
    shutil.rmtree(cd, ignore_errors=True)
    base = _get_chunk_base(workspace)
    try:
        if base.exists() and base.is_dir() and not any(base.iterdir()):
            base.rmdir()
    except OSError:
        # Non-empty or transient filesystem error: leave it for stale cleanup.
        pass
    logger.info("Merged %d chunks → %s (%d chars)", total, target_path, len(full_content))

    return {
        "ok": True,
        "status": "merged",
        "path": str(target),
        "total_chunks": total,
        "total_chars": len(full_content),
        "message": f"已合并{total}个分块写入 {target_path}（{len(full_content)}字符）",
    }


def cleanup_stale_chunks(workspace: str | None = None) -> int:
    """Remove chunk directories older than CHUNK_TIMEOUT. Returns count removed."""
    base = _get_chunk_base(workspace)
    if not base.exists():
        return 0

    removed = 0
    now = time.time()
    for d in base.iterdir():
        if not d.is_dir():
            continue
        meta_file = d / "meta.json"
        if not meta_file.exists():
            # No meta = stale, remove
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            last_updated = meta.get("last_updated", meta.get("created_at", 0))
            if now - last_updated > CHUNK_TIMEOUT:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
                logger.info("Cleaned up stale chunks for %s", meta.get("target_path", "?"))
        except Exception:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1

    return removed


def get_pending_chunks(target_path: str, workspace: str | None = None) -> dict | None:
    """Check if there are pending chunks for a target path.
    
    Returns status dict if pending, None if no chunks exist.
    Also triggers cleanup of stale chunk sets.
    """
    # Opportunistic cleanup
    cleanup_stale_chunks(workspace)

    meta = _load_meta(target_path, workspace)
    if not meta:
        return None

    received = set(meta.get("chunks_received", []))
    total = meta.get("total_chunks", 0)
    expected = set(range(1, total + 1))
    remaining = sorted(expected - received)

    if not remaining:
        # All chunks present but not merged yet (shouldn't happen normally)
        return _merge_chunks(target_path, meta, workspace)

    return {
        "ok": True,
        "status": "partial",
        "target_path": target_path,
        "total_chunks": total,
        "received": sorted(received),
        "remaining": remaining,
        "message": f"{target_path} 已收到{len(received)}/{total}块，等待第{remaining[0]}块。",
    }
