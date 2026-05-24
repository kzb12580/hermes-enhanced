"""Hermes 2.0 Integration Adapter — the glue module.

Wires all V2 sub-modules into a single ``Hermes2Engine`` that provides
the public API consumed by Hermes Agent's conversation loop.

Modules integrated:
  - ToolOrchestrator (batching, concurrency)
  - ToolResultManager (dedup, truncation, disk I/O)
  - PermissionPipeline (permission checks)
  - ContextCompressorV2 (pressure monitoring, compression)
  - MemoryStore / MemoryExtractor / MemoryInjector (memory system)
  - HookPipeline / HookContext (post-turn hooks)
  - AutoDreamer (background memory consolidation)
  - Coordinator (multi-agent planning)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .tool_orchestrator import ToolCall, ToolOrchestrator
from .tool_result_manager import ProcessedResult, ToolResultManager
from .permission_pipeline import PermissionPipeline, PermissionRule
from .context_compressor_v2 import ContextCompressorV2
from .memory_system import MemoryEntry, MemoryExtractor, MemoryInjector, MemoryStore
from .post_turn_hooks import (
    HookContext,
    HookPipeline,
    HookResult,
    MemoryExtractionHook,
    UsageTrackingHook,
    PromptSuggestionHook,
    ContextHealthHook,
)
from .auto_dream import AutoDreamer, DreamReport, SessionSummary
from .coordinator import Coordinator


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Hermes2Config:
    """Configuration for :class:`Hermes2Engine`."""

    max_workers: int = 8
    max_context_tokens: int = 200_000
    compression_profile: str = "balanced"
    memory_storage_path: Optional[str] = None
    disk_result_dir: Optional[str] = None
    permission_rules: Optional[list[PermissionRule]] = None
    auto_dream_threshold: int = 5
    enable_hooks: bool = True
    enable_auto_dream: bool = True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Hermes2Engine:
    """Central engine that processes tool calls and manages turn lifecycle.

    Parameters
    ----------
    config : Hermes2Config | None
        Configuration object.  Uses defaults when *None*.
    """

    def __init__(self, config: Optional[Hermes2Config] = None) -> None:
        self.config = config or Hermes2Config()

        # ── Sub-modules ──────────────────────────────────────────────────
        self.orchestrator = ToolOrchestrator(max_workers=self.config.max_workers)
        self.result_manager = ToolResultManager(
            max_tokens=self.config.max_context_tokens // 2,
            disk_dir=self.config.disk_result_dir,
        )
        self.permissions = PermissionPipeline(rules=self.config.permission_rules)
        self.compressor = ContextCompressorV2(
            model_token_limit=self.config.max_context_tokens,
            profile=self.config.compression_profile,
        )
        self.memory = MemoryStore(storage_path=self.config.memory_storage_path)
        self.memory_extractor = MemoryExtractor()
        self.memory_injector = MemoryInjector()
        self.coordinator = Coordinator()

        # Hooks — register all built-in hooks
        self.hooks = HookPipeline()
        if self.config.enable_hooks:
            self.hooks.register(MemoryExtractionHook())
            self.hooks.register(UsageTrackingHook())
            self.hooks.register(PromptSuggestionHook())
            self.hooks.register(ContextHealthHook(
                model_token_limit=self.config.max_context_tokens,
            ))

        # Auto-dreamer
        from .auto_dream import DreamTrigger

        self.auto_dreamer = AutoDreamer(
            memory_store=self.memory,
            trigger=DreamTrigger(
                session_threshold=self.config.auto_dream_threshold,
            ),
        )

        # Turn counter
        self._turn_count: int = 0

    # ── Public API ───────────────────────────────────────────────────────

    def process_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        executor_fn: Callable[[ToolCall], Any],
    ) -> dict[str, Any]:
        """Run tool calls through permission → batch → execute → process.

        Parameters
        ----------
        tool_calls : list[dict]
            Each dict must have ``name`` and ``args`` keys.
        executor_fn : callable
            Function invoked per :class:`ToolCall`; returns raw result.

        Returns
        -------
        dict mapping tool id → processed result dict.
        """
        if not tool_calls:
            return {}

        # 1. Permission check → filter denied
        allowed_calls: list[dict] = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = tc.get("name", "")
            args = tc.get("args", {})
            decision = self.permissions.check(name, args)
            if decision.allowed:
                allowed_calls.append(tc)

        if not allowed_calls:
            return {}

        # 2. Convert to ToolCall objects
        call_objects = [
            ToolCall(name=tc["name"], args=tc.get("args", {}))
            for tc in allowed_calls
        ]

        # 3. Partition into batches
        batches = self.orchestrator.partition(call_objects)

        # 4. Execute batches
        batch_results = self.orchestrator.execute(batches, executor_fn)

        # 5. Process each result through result manager
        processed: dict[str, Any] = {}
        for tool_call in call_objects:
            br = batch_results.get(tool_call.id)
            if br is None:
                continue
            if br.error:
                processed[tool_call.id] = {
                    "error": br.error,
                    "tool_name": tool_call.name,
                }
            else:
                pr = self.result_manager.process(
                    tool_name=tool_call.name,
                    content=str(br.result),
                )
                processed[tool_call.id] = {
                    "content": pr.content,
                    "was_truncated": pr.was_truncated,
                    "was_deduped": pr.was_deduped,
                    "token_count": pr.token_count,
                }

        return processed

    def process_turn(
        self,
        messages: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Post-turn processing pipeline.

        1. Build :class:`HookContext` and run hooks.
        2. Extract and store memories.
        3. Check context pressure; compress if needed.
        """
        self._turn_count += 1

        # 1. Build HookContext and run hooks
        ctx = HookContext(
            messages=messages,
            tool_calls=tool_calls,
            tool_results=tool_results,
            turn_number=self._turn_count,
        )
        hooks_results = self._run_hooks_sync(ctx)

        # 2. Extract memories from hook results and store
        memories_extracted = self._extract_and_store_memories(hooks_results)

        # 3. Context pressure / compression
        should, reason = self.compressor.should_compress(messages)
        compression_applied = False
        compressed_messages = None
        if should:
            compressed = self.compressor.compress(messages, level="auto")
            compression_applied = True
            compressed_messages = compressed.messages
        pressure = self.compressor.monitor.current
        return {
            "hooks_results": hooks_results,
            "memories_extracted": memories_extracted,
            "compression_applied": compression_applied,
            "compressed_messages": compressed_messages,
            "pressure": pressure,
            "pressure_reason": reason,
        }

    def get_context_messages(self, messages: list[dict[str, Any]]) -> list[dict]:
        """Return *messages* with memory context injected into the system prompt.

        If no system message exists one is created.  Relevant memories are
        prepended to the system message content.
        """
        result = [dict(m) for m in messages]

        # Gather memories relevant to recent conversation
        recent_text = " ".join(
            m.get("content", "") for m in messages[-5:] if isinstance(m.get("content"), str)
        )
        memories = self.memory.search(recent_text, limit=10) if recent_text else []

        if not memories:
            return result

        context_str = self.memory_injector.prepare_context(memories)

        # Find or create system message
        if result and result[0].get("role") == "system":
            result[0] = dict(result[0])
            existing = result[0].get("content", "")
            # Coerce non-string content (e.g. OpenAI list format) to string
            if isinstance(existing, list):
                existing = " ".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in existing
                )
            elif not isinstance(existing, str):
                existing = str(existing)
            result[0]["content"] = context_str + "\n\n" + existing
        else:
            result.insert(0, {"role": "system", "content": context_str})

        return result

    def should_dream(self, session_count: Optional[int] = None) -> bool:
        """Return ``True`` if enough sessions have accumulated for dreaming.

        If *session_count* is not given, the engine's internal count is used.
        """
        if session_count is not None:
            return session_count >= self.config.auto_dream_threshold
        return self.auto_dreamer.should_dream()

    def dream(self) -> DreamReport:
        """Trigger a dream cycle and return the report."""
        return self.auto_dreamer.dream()

    def get_stats(self) -> dict[str, Any]:
        """Aggregate statistics from all sub-modules."""
        return {
            "turn_count": self._turn_count,
            "orchestrator": {
                "max_workers": self.config.max_workers,
            },
            "result_manager": self.result_manager.get_stats(),
            "compressor": self.compressor.get_stats(),
            "memory": self.memory.get_stats(),
            "hooks": self.hooks.get_hooks(),
            "auto_dream": {
                "threshold": self.config.auto_dream_threshold,
                "history_count": len(self.auto_dreamer.get_history()),
            },
        }

    # ── Internal helpers ─────────────────────────────────────────────────

    def _run_hooks_sync(self, ctx: HookContext) -> list[dict]:
        """Run the async hook pipeline synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop — use a new thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(asyncio.run, self.hooks.run_all(ctx)).result()
        else:
            results = asyncio.run(self.hooks.run_all(ctx))

        return [
            {
                "hook_name": r.hook_name,
                "success": r.success,
                "data": r.data,
                "elapsed_ms": r.elapsed_ms,
                "error": r.error,
            }
            for r in results
        ]

    def _extract_and_store_memories(self, hooks_results: list[dict]) -> int:
        """Extract memory entries from hook results and persist them."""
        entries: list[MemoryEntry] = []
        for hr in hooks_results:
            if hr.get("hook_name") == "memory_extraction" and hr.get("success"):
                for item in hr.get("data", {}).get("entries", []):
                    from .memory_system import MemoryType

                    try:
                        mtype = MemoryType(item.get("type", "memory"))
                    except ValueError:
                        mtype = MemoryType.MEMORY
                    entries.append(MemoryEntry(
                        type=mtype,
                        content=item.get("content", ""),
                        tags=item.get("tags", []),
                        source="post-turn-hook",
                    ))

        for entry in entries:
            self.memory.add(entry)

        return len(entries)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def from_config(config_dict: dict[str, Any]) -> Hermes2Engine:
    """Construct a :class:`Hermes2Engine` from a plain dict.

    Unknown keys are silently ignored so that config files can carry extra
    metadata without breaking deserialization.
    """
    valid_keys = {f.name for f in Hermes2Config.__dataclass_fields__.values()}
    filtered = {k: v for k, v in config_dict.items() if k in valid_keys}
    config = Hermes2Config(**filtered)
    return Hermes2Engine(config)
