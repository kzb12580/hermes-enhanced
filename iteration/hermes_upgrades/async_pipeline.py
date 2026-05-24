"""Async Pipeline Simulator for Hermes Agent.

Provides an async pipeline architecture inspired by Claude Code's AsyncGenerator
pipeline, adapted for Python's asyncio. Enables gradual migration from synchronous
while-loop execution to streaming async pipelines.

Components:
    PipelineStage: Generic typed stage wrapping an async generator processor.
    Pipeline: Chain of stages with map/filter/flat_map transforms.
    StreamingToolExecutor: Concurrent tool execution with completion-order yielding.
    ContextWindow: Token-aware message buffer with auto-compaction.
    BackPressureController: Flow control based on context pressure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    TypeVar,
)

T = TypeVar("T")
U = TypeVar("U")


# ---------------------------------------------------------------------------
# PipelineStage
# ---------------------------------------------------------------------------

@dataclass
class PipelineStage(Generic[T, U]):
    """A named async processing stage in a pipeline.

    Attributes:
        name: Human-readable stage identifier.
        process: Async generator that transforms input items into output items.
        can_stream: Whether this stage supports streaming partial results.
    """

    name: str
    process: Callable[[T], AsyncIterator[U]]
    can_stream: bool = True

    async def __call__(self, item: T) -> AsyncIterator[U]:
        """Invoke the stage's processor."""
        async for result in self.process(item):
            yield result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """Composable async pipeline of stages.

    Stages are chained so the output of one feeds the next.  Supports
    ``map``, ``filter``, and ``flat_map`` convenience transforms that
    auto-wrap lambdas into ``PipelineStage`` instances.

    Example::

        pipeline = Pipeline()
        pipeline.add_stage(stage_a)
        pipeline.map("double", lambda x: x * 2)
        async for item in pipeline.execute(seed_data):
            print(item)
    """

    def __init__(self) -> None:
        self._stages: list[PipelineStage[Any, Any]] = []

    # -- chaining ----------------------------------------------------------

    def add_stage(self, stage: PipelineStage[Any, Any]) -> "Pipeline":
        """Append a stage and return *self* for chaining."""
        self._stages.append(stage)
        return self

    # -- convenience transforms --------------------------------------------

    def map(self, name: str, fn: Callable[[Any], Any]) -> "Pipeline":
        """Add a 1-to-1 mapping stage."""
        async def _process(item: Any) -> AsyncIterator[Any]:
            yield fn(item)
        return self.add_stage(PipelineStage(name=name, process=_process))

    def filter(self, name: str, predicate: Callable[[Any], bool]) -> "Pipeline":
        """Add a filtering stage (drops items where *predicate* is false)."""
        async def _process(item: Any) -> AsyncIterator[Any]:
            if predicate(item):
                yield item
        return self.add_stage(PipelineStage(name=name, process=_process, can_stream=False))

    def flat_map(self, name: str, fn: Callable[[Any], Any]) -> "Pipeline":
        """Add a 1-to-many stage.  *fn* must return an iterable or async iterable."""
        async def _process(item: Any) -> AsyncIterator[Any]:
            result = fn(item)
            if hasattr(result, "__aiter__"):
                async for sub in result:
                    yield sub
            else:
                for sub in result:
                    yield sub
        return self.add_stage(PipelineStage(name=name, process=_process))

    # -- execution ---------------------------------------------------------

    async def execute(self, input_data: Any) -> AsyncIterator[Any]:
        """Run *input_data* through every stage, yielding final outputs.

        If there are no stages the input itself is yielded.
        """
        if not self._stages:
            yield input_data
            return

        current: list[Any] = [input_data]
        for stage in self._stages:
            next_items: list[Any] = []
            for item in current:
                async for out in stage(item):
                    next_items.append(out)
            current = next_items
        for item in current:
            yield item


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of a single tool invocation."""

    tool_id: str
    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# StreamingToolExecutor
# ---------------------------------------------------------------------------

class StreamingToolExecutor:
    """Execute multiple tool calls concurrently, yielding results in
    **completion order** (not submission order).

    Concurrency is bounded by a semaphore.  If a tool raises a fatal
    error the remaining pending tasks are cancelled.

    Example::

        executor = StreamingToolExecutor(max_concurrent=3)
        async for result in executor.execute_streaming(calls, my_executor_fn):
            handle(result)
    """

    def __init__(self, max_concurrent: int = 5) -> None:
        self._max_concurrent = max_concurrent

    async def execute_streaming(
        self,
        tool_calls: list[dict[str, Any]],
        executor_fn: Callable[[dict[str, Any]], Awaitable[ToolResult]],
    ) -> AsyncIterator[ToolResult]:
        """Yield ``ToolResult`` objects as each tool completes.

        Args:
            tool_calls: List of tool-call dicts (must include ``id`` key).
            executor_fn: Async callable that runs one tool call and returns
                a ``ToolResult``.

        Yields:
            ToolResult in completion order.
        """
        semaphore = asyncio.Semaphore(self._max_concurrent)
        queue: asyncio.Queue[ToolResult | BaseException] = asyncio.Queue()
        fatal_event = asyncio.Event()

        async def _run(call: dict[str, Any]) -> None:
            if fatal_event.is_set():
                return
            async with semaphore:
                if fatal_event.is_set():
                    return
                try:
                    result = await executor_fn(call)
                    await queue.put(result)
                except (SystemExit, KeyboardInterrupt) as exc:
                    fatal_event.set()
                    await queue.put(exc)
                except Exception as exc:
                    # Non-fatal: wrap as failed ToolResult
                    await queue.put(
                        ToolResult(
                            tool_id=call.get("id", "unknown"),
                            success=False,
                            error=str(exc),
                        )
                    )

        tasks = [asyncio.create_task(_run(call)) for call in tool_calls]
        remaining = len(tasks)

        while remaining > 0:
            item = await queue.get()
            if isinstance(item, BaseException):
                # Fatal – cancel everything and re-raise
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise item
            remaining -= 1
            yield item

        # Ensure all tasks are settled
        await asyncio.gather(*tasks, return_exceptions=True)


# ---------------------------------------------------------------------------
# ContextWindow
# ---------------------------------------------------------------------------

class ContextWindow:
    """Token-aware conversation buffer.

    Messages are stored in OpenAI chat format.  Token count is estimated
    at ~4 characters per token (conservative).

    Args:
        max_tokens: Maximum token budget for this window.
    """

    _CHARS_PER_TOKEN = 4

    def __init__(self, max_tokens: int = 200_000) -> None:
        self._max_tokens = max_tokens
        self._messages: list[dict[str, str]] = []

    # -- public API --------------------------------------------------------

    def add(self, content: str, role: str = "user") -> None:
        """Append a message."""
        self._messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict[str, str]]:
        """Return a copy of messages in OpenAI format."""
        return list(self._messages)

    @property
    def current_tokens(self) -> int:
        """Estimated token count of all messages."""
        return sum(
            len(m["content"]) // self._CHARS_PER_TOKEN + 1
            for m in self._messages
        )

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def pressure(self) -> float:
        """Context utilisation ratio in ``[0.0, 1.0]``."""
        if self._max_tokens == 0:
            return 1.0
        return min(1.0, self.current_tokens / self._max_tokens)

    async def auto_compact(
        self,
        threshold: float = 0.8,
        compressor: Callable[[list[dict[str, str]]], Awaitable[list[dict[str, str]]]] | None = None,
    ) -> None:
        """Shrink the context if pressure exceeds *threshold*.

        If a *compressor* async callable is provided it will be used;
        otherwise a naive strategy keeps the system prompt and last half
        of messages.
        """
        if self.pressure < threshold:
            return

        if compressor is not None:
            self._messages = await compressor(self._messages)
            return

        # Naive compaction: keep first message (system) + last half
        if len(self._messages) <= 2:
            return
        keep = max(2, len(self._messages) // 2)
        system_msgs = [m for m in self._messages if m["role"] == "system"]
        other_msgs = [m for m in self._messages if m["role"] != "system"]
        kept_others = other_msgs[-keep:]
        # Rebuild: all system messages first, then the kept tail
        self._messages = system_msgs + kept_others


# ---------------------------------------------------------------------------
# BackPressureController
# ---------------------------------------------------------------------------

class BackPressureController:
    """Simple hysteresis-based flow controller.

    Call ``update`` with current/max token counts.  Then query
    ``should_pause`` / ``should_resume`` to decide whether the
    producing side should slow down.

    Args:
        high_water: Pressure level at which producers should pause.
        low_water: Pressure level at which producers may resume.
    """

    def __init__(self, high_water: float = 0.8, low_water: float = 0.6) -> None:
        if not 0.0 <= low_water <= high_water <= 1.0:
            raise ValueError("Require 0 <= low_water <= high_water <= 1")
        self._high_water = high_water
        self._low_water = low_water
        self._pressure: float = 0.0
        self._paused: bool = False

    def update(self, current_tokens: int, max_tokens: int) -> None:
        """Record latest token counts."""
        if max_tokens <= 0:
            self._pressure = 1.0
        else:
            self._pressure = min(1.0, current_tokens / max_tokens)

        if self._pressure >= self._high_water:
            self._paused = True
        elif self._pressure <= self._low_water:
            self._paused = False

    def should_pause(self) -> bool:
        """Return ``True`` if producers should stop sending data."""
        return self._paused

    def should_resume(self) -> bool:
        """Return ``True`` if producers may resume."""
        return not self._paused

    @property
    def pressure(self) -> float:
        return self._pressure
