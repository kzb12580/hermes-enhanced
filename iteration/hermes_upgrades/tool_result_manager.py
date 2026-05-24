"""Enhanced Tool Result Manager for Hermes Agent.

Provides token estimation, result deduplication, smart truncation,
and disk persistence for tool results to optimize LLM context usage.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# TokenEstimator
# ---------------------------------------------------------------------------

class TokenEstimator:
    """Fast approximate token counter using ~4 chars/token heuristic."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count for a single string.

        Uses a rough 4-chars-per-token approximation which is adequate
        for budget management (actual tokenizers vary by ±20%).
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
        """Sum estimated tokens across all message dicts.

        Each message is expected to have a ``content`` key (str).
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += TokenEstimator.estimate_tokens(content)
            elif isinstance(content, list):
                # OpenAI-style content arrays
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += TokenEstimator.estimate_tokens(part["text"])
        return total


# ---------------------------------------------------------------------------
# ResultDeduplicator
# ---------------------------------------------------------------------------

class ResultDeduplicator:
    """LRU-bounded deduplication via SHA-256 hashing."""

    def __init__(self, max_seen: int = 1000) -> None:
        self.max_seen = max_seen
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.Lock()

    # -- public API ---------------------------------------------------------

    @staticmethod
    def hash_result(content: str) -> str:
        """Return SHA-256 hex digest of *content*."""
        if content is None:
            content = ""
        return hashlib.sha256(str(content).encode("utf-8")).hexdigest()

    def is_duplicate(self, content: str) -> bool:
        """Return True if *content* was previously registered."""
        h = self.hash_result(content)
        return self.is_duplicate_hash(h)

    def is_duplicate_hash(self, h: str) -> bool:
        """Return True if *hash* was previously registered."""
        with self._lock:
            if h in self._seen:
                # Move to end (most-recently used)
                self._seen.move_to_end(h)
                return True
            return False

    def register(self, content: str) -> None:
        """Add *content* to the seen set, evicting oldest if at capacity."""
        h = self.hash_result(content)
        with self._lock:
            if h in self._seen:
                self._seen.move_to_end(h)
                return
            self._seen[h] = None
            if len(self._seen) > self.max_seen:
                self._seen.popitem(last=False)

    def clear(self) -> None:
        """Reset deduplication state."""
        with self._lock:
            self._seen.clear()


# ---------------------------------------------------------------------------
# SmartTruncator
# ---------------------------------------------------------------------------

# Default per-tool token budgets
DEFAULT_TOOL_BUDGETS: dict[str, int] = {
    "read_file": 15000,
    "terminal": 10000,
    "search_files": 8000,
    "web_extract": 12000,
    "default": 8000,
}


class SmartTruncator:
    """Truncates text to fit a token budget while preserving head/tail."""

    def __init__(self, estimator: TokenEstimator | None = None) -> None:
        self._estimator = estimator or TokenEstimator()

    def truncate(
        self,
        text: str,
        max_tokens: int,
        keep_head: float = 0.3,
        keep_tail: float = 0.2,
    ) -> str:
        """Truncate *text* to approximately *max_tokens* tokens.

        If the text is within budget it is returned unchanged. Otherwise
        the first ``keep_head`` fraction and last ``keep_tail`` fraction
        of the **lines** are kept, with a marker showing how many lines
        were removed.
        """
        est = self._estimator.estimate_tokens(text)
        if est <= max_tokens:
            return text

        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        # Single-line or very short text: character-based truncation
        if total_lines <= 2:
            char_budget = max_tokens * 4  # ~4 chars per token
            if char_budget < 1:
                return "[...truncated...]"
            head_chars = max(1, int(char_budget * 0.6))
            tail_chars = max(1, int(char_budget * 0.3))
            if head_chars + tail_chars >= len(text):
                return text[:char_budget]
            return (
                text[:head_chars]
                + f"\n[...truncated {len(text) - head_chars - tail_chars} chars...]\n"
                + text[-tail_chars:]
            )

        head_lines = max(1, int(total_lines * keep_head))
        tail_lines = max(1, int(total_lines * keep_tail))

        # Ensure we don't overlap
        if head_lines + tail_lines >= total_lines:
            head_lines = max(1, total_lines // 2)
            tail_lines = max(1, total_lines - head_lines)

        removed = total_lines - head_lines - tail_lines
        head = "".join(lines[:head_lines])
        tail = "".join(lines[-tail_lines:])
        marker = f"\n[...truncated {removed} lines...]\n"

        return head + marker + tail

    def truncate_for_tool(
        self,
        text: str,
        tool_name: str,
        budgets: dict[str, int] | None = None,
    ) -> str:
        """Truncate using the budget configured for *tool_name*."""
        merged = {**DEFAULT_TOOL_BUDGETS, **(budgets or {})}
        budget = merged.get(tool_name, merged.get("default", 8000))
        return self.truncate(text, budget)


# ---------------------------------------------------------------------------
# ProcessedResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class ProcessedResult:
    """Outcome of :meth:`ToolResultManager.process`."""

    content: str
    was_truncated: bool
    was_deduped: bool
    was_disk_saved: bool
    token_count: int
    hash: str


# ---------------------------------------------------------------------------
# ToolResultManager
# ---------------------------------------------------------------------------

class ToolResultManager:
    """High-level manager combining estimation, dedup, truncation & disk I/O."""

    def __init__(
        self,
        max_tokens: int = 80000,
        per_tool_budgets: dict[str, int] | None = None,
        disk_dir: str | Path | None = None,
        disk_threshold: int = 50_000,
    ) -> None:
        self.max_tokens = max_tokens
        self.per_tool_budgets = per_tool_budgets or {}
        self.disk_threshold = disk_threshold

        self._estimator = TokenEstimator()
        self._dedup = ResultDeduplicator()
        self._truncator = SmartTruncator(self._estimator)

        self._disk_dir: Path | None = None
        if disk_dir is not None:
            self._disk_dir = Path(disk_dir)
            self._disk_dir.mkdir(parents=True, exist_ok=True)

        # Cache of processed results keyed by hash
        self._cache: OrderedDict[str, ProcessedResult] = OrderedDict()

        # Thread-safety lock for process()
        self._process_lock = threading.Lock()

        # Stats
        self._stats = {
            "total_processed": 0,
            "dedup_saves": 0,
            "truncations": 0,
            "disk_saves": 0,
        }

    # -- public API ---------------------------------------------------------

    def process(
        self,
        tool_name: str,
        content: str,
        file_path: str | None = None,
    ) -> ProcessedResult:
        """Process a tool result through dedup → truncate → disk pipeline.

        Parameters
        ----------
        tool_name:
            Name of the tool that produced the result.
        content:
            Raw text content from the tool.
        file_path:
            Optional original file path (used for disk naming).

        Returns
        -------
        ProcessedResult with final (possibly shortened) content.
        """
        with self._process_lock:
            if content is None:
                content = ""
            self._stats["total_processed"] += 1
            result_hash = ResultDeduplicator.hash_result(content)

            # --- dedup ---
            if self._dedup.is_duplicate_hash(result_hash):
                self._stats["dedup_saves"] += 1
                cached = self._cache.get(result_hash)
                if cached is not None:
                    return replace(cached, was_deduped=True)
                # Hash collision path – fall through to re-process

            # --- truncate ---
            was_truncated = False
            processed = content

            # First apply per-tool budget
            tool_budgets = {**DEFAULT_TOOL_BUDGETS, **self.per_tool_budgets}
            tool_budget = tool_budgets.get(tool_name, tool_budgets.get("default", 8000))
            tokens = self._estimator.estimate_tokens(processed)
            if tokens > tool_budget:
                processed = self._truncator.truncate(processed, tool_budget)
                was_truncated = True

            # Then apply global max
            tokens = self._estimator.estimate_tokens(processed)
            if tokens > self.max_tokens:
                processed = self._truncator.truncate(processed, self.max_tokens)
                was_truncated = True

            if was_truncated:
                self._stats["truncations"] += 1

            # --- disk persistence ---
            was_disk_saved = False
            if self._disk_dir and len(content) > self.disk_threshold:
                self._save_to_disk(tool_name, result_hash, content, file_path)
                was_disk_saved = True
                self._stats["disk_saves"] += 1

            token_count = self._estimator.estimate_tokens(processed)

            result = ProcessedResult(
                content=processed,
                was_truncated=was_truncated,
                was_deduped=False,
                was_disk_saved=was_disk_saved,
                token_count=token_count,
                hash=result_hash,
            )

            # Register and cache
            self._dedup.register(content)
            self._cache[result_hash] = result
            if len(self._cache) > self._dedup.max_seen:
                self._cache.popitem(last=False)

        return result

    def get_stats(self) -> dict[str, int]:
        """Return processing statistics."""
        return dict(self._stats)

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize a tool name for safe use in filenames.

        Strips path separators and other dangerous characters to prevent
        path traversal attacks when constructing filenames from tool names.
        """
        # Replace path separators and null bytes
        safe = name.replace("/", "_").replace("\\", "_").replace("\0", "")
        # Strip leading dots (prevent hidden files / relative path traversal)
        safe = safe.lstrip(".")
        # Keep only alphanumeric, underscore, hyphen, dot
        safe = re.sub(r"[^a-zA-Z0-9_.\-]", "_", safe)
        # Collapse multiple underscores
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe or "unknown"

    def _save_to_disk(
        self,
        tool_name: str,
        result_hash: str,
        content: str,
        file_path: str | None,
    ) -> None:
        """Persist large raw content to disk as JSON."""
        if self._disk_dir is None:
            raise RuntimeError("_save_to_disk called but disk_dir is not configured")
        safe_name = result_hash[:16]
        safe_tool = self._sanitize_name(tool_name)
        out = self._disk_dir / f"{safe_tool}_{safe_name}.json"
        # Verify resolved path is still within disk_dir (defense in depth)
        try:
            out.resolve().relative_to(self._disk_dir.resolve())
        except ValueError:
            raise ValueError(
                f"Path traversal detected: resolved path {out} escapes disk_dir"
            )
        payload = {
            "tool_name": tool_name,
            "hash": result_hash,
            "original_path": file_path,
            "char_count": len(content),
            "content": content,
        }
        # Atomic write: temp file + os.replace() for crash safety
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self._disk_dir), suffix=".tmp"
        )
        try:
            try:
                f = os.fdopen(tmp_fd, "w", encoding="utf-8")
            except BaseException:
                # fdopen failed — close the raw fd to prevent leak
                os.close(tmp_fd)
                raise
            with f:
                json.dump(payload, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(out))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
