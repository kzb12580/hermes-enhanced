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

SHELL_TOOLS: frozenset[str] = frozenset({"terminal", "bash", "sh", "powershell", "cmd"})

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

_log = logging.getLogger(__name__)

try:
    from .tool_orchestrator import ToolCall, ToolOrchestrator
except ImportError:
    from tool_orchestrator import ToolCall, ToolOrchestrator

try:
    from .tool_result_manager import ProcessedResult, ToolResultManager
except ImportError:
    from tool_result_manager import ProcessedResult, ToolResultManager

try:
    from .permission_pipeline import PermissionLevel, PermissionPipeline, PermissionRule
except ImportError:
    from permission_pipeline import PermissionLevel, PermissionPipeline, PermissionRule

try:
    from .permission_pipeline import _is_dangerous_command
except ImportError:
    from permission_pipeline import _is_dangerous_command

try:
    from .context_compressor_v2 import ContextCompressorV2
except ImportError:
    from context_compressor_v2 import ContextCompressorV2

try:
    from .memory_system import MemoryEntry, MemoryExtractor, MemoryInjector, MemoryStore
except ImportError:
    from memory_system import MemoryEntry, MemoryExtractor, MemoryInjector, MemoryStore

try:
    from .post_turn_hooks import (
        HookContext,
        HookPipeline,
        HookResult,
        MemoryExtractionHook,
        UsageTrackingHook,
        PromptSuggestionHook,
        ContextHealthHook,
    )
except ImportError:
    from post_turn_hooks import (
        HookContext,
        HookPipeline,
        HookResult,
        MemoryExtractionHook,
        UsageTrackingHook,
        PromptSuggestionHook,
        ContextHealthHook,
    )

try:
    from .auto_dream import AutoDreamer, DreamReport, DreamTrigger, SessionSummary
except ImportError:
    from auto_dream import AutoDreamer, DreamReport, DreamTrigger, SessionSummary

try:
    from .coordinator import Coordinator
except ImportError:
    from coordinator import Coordinator

try:
    from .memory_system import MemoryType
except ImportError:
    from memory_system import MemoryType

try:
    from .token_utils import extract_text_from_content
except ImportError:
    from token_utils import extract_text_from_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_non_dict_items(items: list) -> tuple[list[dict], list[int]]:
    """Separate dict items from non-dict, returning (dicts, bad_indices)."""
    dicts = []
    bad = []
    for i, item in enumerate(items):
        if isinstance(item, dict):
            dicts.append(item)
        else:
            bad.append(i)
    return dicts, bad


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
    on_permission_prompt: Optional[Callable[[str, dict[str, Any], str], bool]] = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Hermes2Engine:
    """Central engine that processes tool calls and manages turn lifecycle.

    Quick start::

        engine = Hermes2Engine()
        results = engine.process_tool_calls(
            [{"name": "read_file", "args": {"path": "/etc/hostname"}}],
            executor_fn=lambda tc: open(tc.args["path"]).read(),
        )

    To allow write operations, set ``on_permission_prompt`` in config or
    call :meth:`allow_tool` to auto-approve specific tools.

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

        self.auto_dreamer = None
        if self.config.enable_auto_dream:
            self.auto_dreamer = AutoDreamer(
                memory_store=self.memory,
                trigger=DreamTrigger(
                    session_threshold=self.config.auto_dream_threshold,
                ),
            )

        # Turn counter
        self._turn_count: int = 0
        self._turn_lock = threading.Lock()

        # Reusable thread-pool for running hooks when an event loop is active
        import concurrent.futures
        self._hook_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False

    def shutdown(self) -> None:
        """Shut down internal thread pools. Safe to call multiple times."""
        if not self._closed:
            self._hook_executor.shutdown(wait=False)
            self.orchestrator.shutdown(wait=False)
            if hasattr(self, '_hook_loop') and self._hook_loop is not None and not self._hook_loop.is_closed():
                self._hook_loop.close()
            self._closed = True

    def __del__(self) -> None:
        """Best-effort cleanup on garbage collection."""
        try:
            self.shutdown()
        except Exception:
            pass

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
        dict with keys:
          - ``processed``: mapping of tool id → processed result dict.
          - ``denied``: list of dicts with ``name`` and ``reason`` for denied tools.
          - ``needs_prompt``: list of dicts for tools needing confirmation.
          - ``warnings``: list of warning strings.
        """
        result: dict[str, Any] = {
            "processed": {},
            "denied": [],
            "needs_prompt": [],
            "warnings": [],
        }

        if not tool_calls:
            return result

        # 0. Filter non-dict items with warning
        dicts, bad_indices = _coerce_non_dict_items(tool_calls)
        if bad_indices:
            msg = f"Non-dict tool_calls at indices {bad_indices} — skipped"
            _log.warning(msg)
            result["warnings"].append(msg)

        if not dicts:
            return result

        # 1. Permission check → filter denied, handle PROMPT
        allowed_calls: list[dict] = []
        for tc in dicts:
            # Validate that each tool_call has a "name" key with a string value
            if "name" not in tc or not isinstance(tc["name"], str) or not tc["name"]:
                msg = f"Invalid tool_call entry (missing or non-string 'name'): {tc!r} — skipped"
                _log.warning(msg)
                result["warnings"].append(msg)
                continue
            name = tc["name"]
            # Validate that args is a dict before passing to permission check
            args = tc.get("args", {})
            if not isinstance(args, dict):
                msg = f"Invalid args for tool '{name}': expected dict, got {type(args).__name__} — denied"
                _log.warning(msg)
                result["warnings"].append(msg)
                result["denied"].append({"id": tc.get("id"), "name": name, "reason": msg})
                continue
            decision = self.permissions.check(name, args)
            if decision.allowed:
                # CRITICAL: Always check dangerous commands even for auto-approved tools
                if _is_dangerous_command(args):
                    result["denied"].append({
                        "id": tc.get("id"),
                        "name": name,
                        "reason": "Dangerous terminal command detected — blocked regardless of auto-approval",
                    })
                    continue
                allowed_calls.append(tc)
            elif decision.needs_prompt:
                # Check if caller provided a confirmation callback
                if self.config.on_permission_prompt:
                    try:
                        approved = self.config.on_permission_prompt(
                            name, args, decision.reason
                        )
                    except Exception as exc:
                        _log.warning("Permission callback error for %s: %s", name, exc)
                        approved = False
                    if approved:
                        # Also check dangerous commands even when user-approved via callback
                        if _is_dangerous_command(args):
                            result["denied"].append({
                                "id": tc.get("id"),
                                "name": name,
                                "reason": "Dangerous terminal command detected — blocked regardless of approval",
                            })
                            continue
                        allowed_calls.append(tc)
                    else:
                        result["needs_prompt"].append({
                            "name": name, "reason": decision.reason
                        })
                else:
                    result["needs_prompt"].append({
                        "name": name, "reason": decision.reason
                    })
            else:
                result["denied"].append({
                    "id": tc.get("id"), "name": name, "reason": decision.reason
                })

        if not allowed_calls:
            return result

        # 2. Convert to ToolCall objects
        call_objects = []
        for tc in allowed_calls:
            call_id = tc.get("id")
            if call_id is None:
                import uuid as _uuid
                call_id = str(_uuid.uuid4())
            call_objects.append(
                ToolCall(name=tc["name"], args=tc.get("args", {}), id=call_id)
            )

        # 3. Partition into batches
        batches = self.orchestrator.partition(call_objects)

        # 4. Execute batches
        batch_results = self.orchestrator.execute(batches, executor_fn)

        # 5. Process each result through result manager
        for tool_call in call_objects:
            br = batch_results.get(tool_call.id)
            if br is None:
                continue
            if br.error:
                result["processed"][tool_call.id] = {
                    "error": br.error,
                    "tool_name": tool_call.name,
                }
            else:
                pr = self.result_manager.process(
                    tool_name=tool_call.name,
                    content=str(br.result),
                )
                result["processed"][tool_call.id] = {
                    "content": pr.content,
                    "was_truncated": pr.was_truncated,
                    "was_deduped": pr.was_deduped,
                    "token_count": pr.token_count,
                }

        return result

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

        .. warning::
            If compression is applied, the returned dict will contain a
            ``compressed_messages`` key with the compressed list.
            **The caller is responsible for replacing their local messages
            reference with this value.**  See :meth:`apply_turn_result`
            for a convenience wrapper that does this automatically.
        """
        with self._turn_lock:
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

    def apply_turn_result(
        self,
        messages: list[dict[str, Any]],
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Convenience wrapper around :meth:`process_turn`.

        Calls ``process_turn`` and, if compression was applied, returns
        the compressed messages as the first element.  Otherwise returns
        the original *messages* unchanged.

        Returns
        -------
        tuple of (messages, turn_result_dict)
            ``messages`` is either the original or the compressed version.
            ``turn_result_dict`` is the full result from :meth:`process_turn`.

        Example::

            messages, result = engine.apply_turn_result(messages, calls, results)
            # messages is now safe to use for the next turn
        """
        result = self.process_turn(messages, tool_calls, tool_results)
        if result.get("compression_applied") and result.get("compressed_messages") is not None:
            return result["compressed_messages"], result
        return messages, result

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
            existing = str(extract_text_from_content(existing))
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
        if self.auto_dreamer is None:
            return False
        return self.auto_dreamer.should_dream()

    def dream(self) -> DreamReport:
        """Trigger a dream cycle and return the report."""
        if self.auto_dreamer is None:
            raise RuntimeError("Auto-dream is disabled in config")
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
                "enabled": self.auto_dreamer is not None,
                "history_count": len(self.auto_dreamer.get_history()) if self.auto_dreamer else 0,
            },
        }

    # ── Convenience methods ──────────────────────────────────────────────

    @property
    def pressure(self) -> float:
        """Current context-window pressure as a float in [0.0, 1.0]."""
        return self.compressor.monitor.current

    def allow_tool(self, tool_name: str) -> None:
        """Auto-approve a tool by adding an AUTO permission rule.

        This inserts the rule at position 0 so it's checked first.
        Useful for allowing write operations without a prompt callback::

            engine.allow_tool("write_file")
            engine.allow_tool("terminal")
        """
        self.permissions.add_rule(
            PermissionRule(tool_name, PermissionLevel.AUTO, f"Auto-approved: {tool_name}"),
            index=0,
        )

    def add_memory(
        self,
        content: str,
        type: str = "memory",
        tags: Optional[list[str]] = None,
    ) -> str:
        """Add a memory entry. Returns the entry ID.

        Parameters
        ----------
        content : str
            The memory content.
        type : str
            One of "user", "memory", "procedural", "episodic".
        tags : list[str] | None
            Optional tags for search boosting.
        """
        try:
            mem_type = MemoryType(type)
        except ValueError:
            valid = [e.value for e in MemoryType]
            return f"Error: invalid memory type {type!r}. Valid types: {valid}"
        entry = MemoryEntry(
            type=mem_type,
            content=content,
            tags=tags or [],
            source="api",
        )
        return self.memory.add(entry)

    def search_memories(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Search memories by query string."""
        return self.memory.search(query, limit=limit)

    # ── Internal helpers ─────────────────────────────────────────────────

    def _run_hooks_sync(self, ctx: HookContext) -> list[dict]:
        """Run the async hook pipeline synchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop — use a new thread
            results = self._hook_executor.submit(asyncio.run, self.hooks.run_all(ctx)).result()
        else:
            # Reuse a cached event loop instead of creating a new one per call
            if not hasattr(self, '_hook_loop') or self._hook_loop.is_closed():
                self._hook_loop = asyncio.new_event_loop()
            results = self._hook_loop.run_until_complete(self.hooks.run_all(ctx))

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

    Unknown keys trigger a warning (via :mod:`logging`) so that typos
    in config files are not silently swallowed.
    """
    valid_keys = {f.name for f in Hermes2Config.__dataclass_fields__.values()}
    unknown = set(config_dict.keys()) - valid_keys
    if unknown:
        _log.warning(
            "from_config: ignoring unknown keys %s. Valid keys: %s",
            sorted(unknown),
            sorted(valid_keys),
        )
    filtered = {k: v for k, v in config_dict.items() if k in valid_keys}
    config = Hermes2Config(**filtered)
    return Hermes2Engine(config)
