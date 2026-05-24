"""Post-Turn Hooks Pipeline for Hermes Agent 2.0.

Runs a configurable set of hooks after every agent turn: memory extraction,
usage tracking, prompt suggestions, context health checks, etc.

Inspired by Claude Code's stopHooks.ts, adapted for the Hermes architecture.

Usage:
    pipeline = HookPipeline()
    pipeline.register(MemoryExtractionHook())
    pipeline.register(UsageTrackingHook())
    results = await pipeline.run_all(ctx)
"""

from __future__ import annotations

import asyncio
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .context_compressor_v2 import (
    PressureMonitor,
    _total_tokens,
)
from .memory_system import MemoryExtractor, MemoryEntry


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HookResult:
    """Result returned by a single hook execution."""

    hook_name: str
    success: bool
    data: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class HookContext:
    """All context a hook needs about the just-completed turn."""

    messages: list[dict] = field(default_factory=list)
    user_message: str = ""
    assistant_message: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    session_id: str = ""
    turn_number: int = 0


# ---------------------------------------------------------------------------
# Abstract base hook
# ---------------------------------------------------------------------------


class PostTurnHook(ABC):
    """Base class for all post-turn hooks.

    Subclasses must set ``name`` and ``priority`` and implement ``execute``.
    """

    name: str = "unnamed"
    priority: int = 100
    enabled: bool = True

    @abstractmethod
    async def execute(self, ctx: HookContext) -> HookResult:
        """Run the hook and return a result."""


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


class MemoryExtractionHook(PostTurnHook):
    """Extract memories from the conversation using rule-based patterns.

    Scans for phrases like "remember that", "I prefer", "note that" and
    delegates to :class:`memory_system.MemoryExtractor`.
    """

    name = "memory_extraction"
    priority = 10

    # Extra patterns beyond what MemoryExtractor already covers
    _EXTRA_PATTERNS: list[re.Pattern] = [
        re.compile(r"\bnote\s+that\b", re.I),
        re.compile(r"\bplease\s+remember\b", re.I),
        re.compile(r"\bkeep\s+in\s+mind\b", re.I),
    ]

    def __init__(self) -> None:
        self._extractor = MemoryExtractor()

    async def execute(self, ctx: HookContext) -> HookResult:
        t0 = time.perf_counter()
        try:
            # Build message list for extractor
            msgs: list[dict] = list(ctx.messages)
            # Ensure the latest user/assistant messages are included
            if ctx.user_message:
                msgs.append({"role": "user", "content": ctx.user_message})
            if ctx.assistant_message:
                msgs.append({"role": "assistant", "content": ctx.assistant_message})

            entries: list[MemoryEntry] = self._extractor.extract_from_conversation(msgs)

            # Also scan for extra patterns on the user message
            extra_hits: list[str] = []
            for pat in self._EXTRA_PATTERNS:
                if ctx.user_message and pat.search(ctx.user_message):
                    extra_hits.append(pat.pattern)

            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=True,
                data={
                    "memories_found": len(entries),
                    "entries": [
                        {"type": e.type.value, "content": e.content, "tags": e.tags}
                        for e in entries
                    ],
                    "extra_pattern_hits": extra_hits,
                },
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=False,
                elapsed_ms=elapsed,
                error=str(exc),
            )


class UsageTrackingHook(PostTurnHook):
    """Track tool calls, approximate token usage, and turn duration.

    Maintains cumulative statistics across turns within a session.
    """

    name = "usage_tracking"
    priority = 20

    def __init__(self) -> None:
        self.cumulative: dict = {
            "total_turns": 0,
            "total_tool_calls": 0,
            "total_tokens_est": 0,
            "total_duration_ms": 0.0,
        }

    async def execute(self, ctx: HookContext) -> HookResult:
        t0 = time.perf_counter()
        try:
            tool_call_count = len(ctx.tool_calls)
            tool_result_count = len(ctx.tool_results)

            # Rough token estimate: ~4 chars per token
            user_tokens = len(ctx.user_message) // 4
            assistant_tokens = len(ctx.assistant_message) // 4
            turn_tokens = user_tokens + assistant_tokens

            # Add tool result content tokens
            for tr in ctx.tool_results:
                content = str(tr.get("content", ""))
                turn_tokens += len(content) // 4

            self.cumulative["total_turns"] += 1
            self.cumulative["total_tool_calls"] += tool_call_count
            self.cumulative["total_tokens_est"] += turn_tokens

            elapsed = (time.perf_counter() - t0) * 1000
            self.cumulative["total_duration_ms"] += elapsed

            return HookResult(
                hook_name=self.name,
                success=True,
                data={
                    "turn_tool_calls": tool_call_count,
                    "turn_tool_results": tool_result_count,
                    "turn_tokens_est": turn_tokens,
                    "turn_elapsed_ms": round(elapsed, 2),
                    "cumulative": dict(self.cumulative),
                },
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=False,
                elapsed_ms=elapsed,
                error=str(exc),
            )


class PromptSuggestionHook(PostTurnHook):
    """Analyze tool results and suggest follow-up actions.

    - File edited → suggest running tests or linting.
    - Error detected → suggest debugging steps.
    - Command ran → suggest reviewing output.
    """

    name = "prompt_suggestion"
    priority = 30

    _EDIT_TOOLS = frozenset({
        "write_file", "patch", "str_replace_editor", "create", "edit",
    })
    _ERROR_PATTERNS: list[re.Pattern] = [
        re.compile(r"error", re.I),
        re.compile(r"traceback", re.I),
        re.compile(r"exception", re.I),
        re.compile(r"failed", re.I),
        re.compile(r"fatal", re.I),
    ]

    async def execute(self, ctx: HookContext) -> HookResult:
        t0 = time.perf_counter()
        try:
            suggestions: list[str] = []

            # Check tool calls for edits
            edited_files: list[str] = []
            for tc in ctx.tool_calls:
                tool_name = tc.get("name", "") or tc.get("tool", "")
                if tool_name in self._EDIT_TOOLS:
                    # Try to extract file path from arguments
                    args = tc.get("arguments", tc.get("args", {}))
                    if isinstance(args, dict):
                        path = args.get("path", args.get("file_path", ""))
                        if path:
                            edited_files.append(path)
                    suggestions.append(
                        f"File was edited ({tool_name}). Consider running tests or linting."
                    )

            # Check tool results for errors
            has_error = False
            for tr in ctx.tool_results:
                content = str(tr.get("content", ""))
                for pat in self._ERROR_PATTERNS:
                    if pat.search(content):
                        has_error = True
                        break
                if has_error:
                    break

            if has_error:
                suggestions.append(
                    "An error was detected in tool output. Consider debugging or checking logs."
                )

            # Check assistant message for file paths mentioned
            if ctx.assistant_message:
                file_mentions = re.findall(
                    r"(?:/[\w./-]+\.\w+)", ctx.assistant_message
                )
                if file_mentions and not edited_files:
                    suggestions.append(
                        "Files were mentioned in the response. "
                        "You may want to review or edit them."
                    )

            # Check if user asked a question (ends with ?)
            if ctx.user_message.rstrip().endswith("?"):
                if not suggestions:
                    suggestions.append(
                        "The user asked a question. Consider if they need more details."
                    )

            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=True,
                data={
                    "suggestions": suggestions,
                    "edited_files": edited_files,
                    "has_error": has_error,
                },
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=False,
                elapsed_ms=elapsed,
                error=str(exc),
            )


class ContextHealthHook(PostTurnHook):
    """Monitor context window pressure and warn when approaching limits.

    Uses :class:`context_compressor_v2.PressureMonitor` for pressure tracking.
    """

    name = "context_health"
    priority = 40

    def __init__(self, model_token_limit: int = 200_000) -> None:
        self._monitor = PressureMonitor(model_token_limit)
        self._model_token_limit = model_token_limit

    async def execute(self, ctx: HookContext) -> HookResult:
        t0 = time.perf_counter()
        try:
            pressure = self._monitor.update(ctx.messages)

            if pressure >= 0.95:
                health = "critical"
                warning = (
                    f"Context pressure at {pressure:.1%} — immediate compression needed!"
                )
            elif pressure >= 0.75:
                health = "warning"
                warning = (
                    f"Context pressure at {pressure:.1%} — consider compressing soon."
                )
            elif pressure >= 0.50:
                health = "elevated"
                warning = f"Context pressure at {pressure:.1%}."
            else:
                health = "healthy"
                warning = None

            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=True,
                data={
                    "pressure": round(pressure, 4),
                    "health": health,
                    "warning": warning,
                    "model_token_limit": self._model_token_limit,
                    "estimated_tokens": int(pressure * self._model_token_limit),
                },
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return HookResult(
                hook_name=self.name,
                success=False,
                elapsed_ms=elapsed,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class HookPipeline:
    """Orchestrates execution of post-turn hooks in priority order.

    Args:
        hooks: Optional list of hooks to register initially.
    """

    def __init__(self, hooks: Optional[list[PostTurnHook]] = None) -> None:
        self._hooks: list[PostTurnHook] = []
        if hooks:
            for h in hooks:
                self.register(h)

    def register(self, hook: PostTurnHook) -> None:
        """Add a hook to the pipeline.

        If a hook with the same name already exists it is replaced.
        Hooks are kept sorted by priority (ascending = runs first).
        """
        # Remove existing hook with same name
        self._hooks = [h for h in self._hooks if h.name != hook.name]
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority)

    def unregister(self, name: str) -> bool:
        """Remove a hook by name. Returns True if found and removed."""
        before = len(self._hooks)
        self._hooks = [h for h in self._hooks if h.name != name]
        return len(self._hooks) < before

    async def run_all(self, ctx: HookContext) -> list[HookResult]:
        """Run every enabled hook in priority order.

        Args:
            ctx: The hook context for this turn.

        Returns:
            List of results, one per enabled hook (in execution order).
        """
        results: list[HookResult] = []
        for hook in self._hooks:
            if not hook.enabled:
                continue
            result = await hook.execute(ctx)
            results.append(result)
        return results

    async def run_selected(
        self, names: list[str], ctx: HookContext
    ) -> list[HookResult]:
        """Run only the named hooks (if they exist and are enabled).

        Args:
            names: Hook names to run.
            ctx: The hook context for this turn.

        Returns:
            List of results for the requested hooks that were found and enabled.
        """
        name_set = set(names)
        results: list[HookResult] = []
        for hook in self._hooks:
            if hook.name in name_set and hook.enabled:
                result = await hook.execute(ctx)
                results.append(result)
        return results

    def get_hooks(self) -> list[dict]:
        """Return metadata for all registered hooks.

        Returns:
            List of dicts with keys: name, priority, enabled.
        """
        return [
            {"name": h.name, "priority": h.priority, "enabled": h.enabled}
            for h in self._hooks
        ]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a hook by name.

        Returns:
            True if the hook was found and updated.
        """
        for hook in self._hooks:
            if hook.name == name:
                hook.enabled = enabled
                return True
        return False
