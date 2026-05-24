"""
Enhanced Tool Orchestrator for Hermes Agent.

Classifies tools by concurrency safety, detects file-path conflicts,
partitions tool calls into safe-to-parallel batches, and executes them
with progress tracking.  Pure stdlib – no external dependencies.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """Represents a single tool invocation."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class BatchResult:
    """Result of executing one tool call."""
    tool_id: str
    result: Any = None
    elapsed: float = 0.0
    error: Optional[str] = None


# ── Concurrency classification ───────────────────────────────────────────────

class ConcurrencyClass(Enum):
    READ_ONLY = auto()
    WRITE_SERIAL = auto()
    AMBIGUOUS = auto()


_READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "read_file", "search_files", "web_search", "web_extract",
    "session_search", "skill_view", "skills_list",
    "browser_snapshot", "browser_get_images", "vision_analyze",
})

_WRITE_SERIAL_TOOLS: frozenset[str] = frozenset({
    "write_file", "patch", "terminal", "send_message",
    "delegate_task", "memory", "skill_manage",
    "browser_type", "browser_click", "browser_press",
})


class ToolConcurrencyClassifier:
    """Classify every tool into a concurrency class.

    Parameters
    ----------
    overrides : dict[str, ConcurrencyClass] | None
        Manual overrides keyed by tool name.
    """

    def __init__(self, overrides: dict[str, ConcurrencyClass] | None = None) -> None:
        self._overrides: dict[str, ConcurrencyClass] = overrides or {}

    def classify(self, tool_name: str) -> ConcurrencyClass:
        """Return the concurrency class for *tool_name*."""
        if tool_name in self._overrides:
            return self._overrides[tool_name]
        if tool_name in _READ_ONLY_TOOLS:
            return ConcurrencyClass.READ_ONLY
        if tool_name in _WRITE_SERIAL_TOOLS:
            return ConcurrencyClass.WRITE_SERIAL
        return ConcurrencyClass.AMBIGUOUS  # default: serial


# ── File-conflict detection ──────────────────────────────────────────────────

_PATH_KEYS: tuple[str, ...] = ("path", "file_path", "output_path")


class FileConflictDetector:
    """Detect when two tool calls touch the same file path and at least one
    is a write – such pairs *must* run serially."""

    def __init__(self, path_keys: tuple[str, ...] = _PATH_KEYS) -> None:
        self._path_keys = path_keys

    def extract_paths(self, tool_call: ToolCall) -> set[str]:
        """Return normalised file paths referenced by *tool_call*."""
        paths: set[str] = set()
        for key in self._path_keys:
            val = tool_call.args.get(key)
            if isinstance(val, str) and val:
                paths.add(os.path.normpath(val))
        return paths

    def has_write_conflict(
        self,
        a: ToolCall,
        b: ToolCall,
        classifier: ToolConcurrencyClassifier,
    ) -> bool:
        """True if *a* and *b* share a path and at least one is WRITE."""
        shared = self.extract_paths(a) & self.extract_paths(b)
        if not shared:
            return False
        cls_a = classifier.classify(a.name)
        cls_b = classifier.classify(b.name)
        at_least_one_write = (
            cls_a in (ConcurrencyClass.WRITE_SERIAL, ConcurrencyClass.AMBIGUOUS)
            or cls_b in (ConcurrencyClass.WRITE_SERIAL, ConcurrencyClass.AMBIGUOUS)
        )
        return at_least_one_write


# ── Partitioning ─────────────────────────────────────────────────────────────

def partition(
    tool_calls: list[ToolCall],
    classifier: ToolConcurrencyClassifier | None = None,
    detector: FileConflictDetector | None = None,
) -> list[list[ToolCall]]:
    """Split *tool_calls* into batches safe to execute concurrently.

    Rules:
    * READ_ONLY calls with no path conflicts go in one batch.
    * WRITE_SERIAL / AMBIGUOUS calls each get their own batch.
    * Mixed: reads collected first, then individual write batches.
    * File-conflict pairs are forced serial.
    """
    if not tool_calls:
        return []

    classifier = classifier or ToolConcurrencyClassifier()
    detector = detector or FileConflictDetector()

    # Dependency-aware partitioning that preserves original order.
    # Consecutive non-conflicting reads are grouped into one batch.
    # Writes and conflicting reads each flush the current read batch
    # and become their own single-item batch.
    batches: list[list[ToolCall]] = []
    pending_reads: list[ToolCall] = []

    # Collect all write/ambiguous calls for conflict checks
    write_calls = [
        tc for tc in tool_calls
        if classifier.classify(tc.name) != ConcurrencyClass.READ_ONLY
    ]

    for tc in tool_calls:
        cls = classifier.classify(tc.name)
        if cls == ConcurrencyClass.READ_ONLY:
            # Check if this read conflicts with any write call
            conflict = any(
                detector.has_write_conflict(tc, w, classifier)
                for w in write_calls
            )
            if conflict:
                # Flush pending reads, then this read gets its own batch
                if pending_reads:
                    batches.append(pending_reads)
                    pending_reads = []
                batches.append([tc])
            else:
                pending_reads.append(tc)
        else:
            # Write/ambiguous: flush pending reads first
            if pending_reads:
                batches.append(pending_reads)
                pending_reads = []
            batches.append([tc])

    # Flush any remaining reads
    if pending_reads:
        batches.append(pending_reads)

    return batches


# ── Orchestrator ─────────────────────────────────────────────────────────────

ProgressCallback = Callable[[str, str, float], None]


class ToolOrchestrator:
    """High-level orchestrator that partitions and executes tool calls.

    Parameters
    ----------
    max_workers : int
        Maximum concurrent workers for read-only batches.
    tool_overrides : dict[str, ConcurrencyClass] | None
        Manual classification overrides.
    """

    def __init__(
        self,
        max_workers: int = 8,
        tool_overrides: dict[str, ConcurrencyClass] | None = None,
    ) -> None:
        self.max_workers = max_workers
        self.classifier = ToolConcurrencyClassifier(tool_overrides)
        self.detector = FileConflictDetector()
        from concurrent.futures import ThreadPoolExecutor
        self._async_executor = ThreadPoolExecutor(max_workers=1)
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False

    def shutdown(self, wait: bool = True) -> None:
        """Shut down internal thread pools.

        Call this when the orchestrator is no longer needed to release
        resources.  Safe to call multiple times.
        """
        if not self._closed:
            self._async_executor.shutdown(wait=wait)
            self._closed = True

    # ── public API ───────────────────────────────────────────────────────

    def partition(self, tool_calls: list[ToolCall]) -> list[list[ToolCall]]:
        """Return execution batches for *tool_calls*."""
        return partition(tool_calls, self.classifier, self.detector)

    def execute(
        self,
        batches: list[list[ToolCall]],
        executor_fn: Callable[[ToolCall], Any],
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, BatchResult]:
        """Execute *batches* sequentially; within each batch run calls
        concurrently up to *max_workers*.

        *executor_fn* may be sync or async (returns a coroutine).

        Returns
        -------
        dict mapping tool id → BatchResult.
        """
        results: dict[str, BatchResult] = {}

        for batch in batches:
            if len(batch) == 1:
                tc = batch[0]
                results[tc.id] = self._run_one(tc, executor_fn, on_progress)
            else:
                # Concurrent execution via asyncio or thread-pool fallback.
                batch_results = self._run_concurrent(
                    batch, executor_fn, on_progress
                )
                results.update(batch_results)

        return results

    # ── internals ────────────────────────────────────────────────────────

    def _run_one(
        self,
        tc: ToolCall,
        executor_fn: Callable,
        on_progress: ProgressCallback | None,
    ) -> BatchResult:
        if on_progress:
            on_progress(tc.name, "started", 0.0)
        t0 = time.monotonic()
        try:
            result = executor_fn(tc)
            if inspect.isawaitable(result):
                # Type-narrow to coroutine for run_until_complete
                coro = result  # type: ignore[assignment]
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop — create a new one
                    loop = asyncio.new_event_loop()
                    try:
                        result = loop.run_until_complete(coro)
                    finally:
                        loop.close()
                else:
                    # Running loop exists — execute in a new thread
                    def _run_in_new_loop():
                        new_loop = asyncio.new_event_loop()
                        try:
                            return new_loop.run_until_complete(coro)
                        finally:
                            new_loop.close()
                    result = self._async_executor.submit(_run_in_new_loop).result()
            elapsed = time.monotonic() - t0
            if on_progress:
                on_progress(tc.name, "completed", elapsed)
            return BatchResult(tool_id=tc.id, result=result, elapsed=elapsed)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            if on_progress:
                on_progress(tc.name, "error", elapsed)
            return BatchResult(
                tool_id=tc.id, elapsed=elapsed, error=str(exc)
            )

    def _run_concurrent(
        self,
        batch: list[ToolCall],
        executor_fn: Callable,
        on_progress: ProgressCallback | None,
    ) -> dict[str, BatchResult]:
        """Run a batch of tool calls concurrently."""
        # Detect async executor.
        if inspect.iscoroutinefunction(executor_fn):
            coro = self._run_concurrent_async(batch, executor_fn, on_progress)
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # No running loop — safe to use asyncio.run()
                return asyncio.run(coro)
            else:
                # Running loop exists — execute in a new thread with its own loop
                return self._async_executor.submit(asyncio.run, coro).result()

        # Sync executor – use threads.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: dict[str, BatchResult] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(self._run_one, tc, executor_fn, on_progress): tc
                for tc in batch
            }
            for future in as_completed(futures):
                tc = futures[future]
                results[tc.id] = future.result()
        return results

    async def _run_concurrent_async(
        self,
        batch: list[ToolCall],
        executor_fn: Callable[[ToolCall], Any],
        on_progress: ProgressCallback | None,
    ) -> dict[str, BatchResult]:
        sem = asyncio.Semaphore(self.max_workers)

        async def _do(tc: ToolCall) -> tuple[str, BatchResult]:
            async with sem:
                if on_progress:
                    on_progress(tc.name, "started", 0.0)
                t0 = time.monotonic()
                try:
                    result = await executor_fn(tc)
                    elapsed = time.monotonic() - t0
                    if on_progress:
                        on_progress(tc.name, "completed", elapsed)
                    return tc.id, BatchResult(
                        tool_id=tc.id, result=result, elapsed=elapsed
                    )
                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    if on_progress:
                        on_progress(tc.name, "error", elapsed)
                    return tc.id, BatchResult(
                        tool_id=tc.id, elapsed=elapsed, error=str(exc)
                    )

        pairs = await asyncio.gather(*(_do(tc) for tc in batch))
        return dict(pairs)
