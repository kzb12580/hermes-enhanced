# Hermes 2.0 API Usability Review

**Reviewer:** Developer who must USE these modules  
**Date:** 2026-05-24  
**Modules reviewed:** hermes2_adapter, tool_orchestrator, tool_result_manager, permission_pipeline, context_compressor_v2, memory_system, post_turn_hooks, auto_dream, coordinator

---

## 1. Quick Start Example (5 Lines)

```python
from hermes_upgrades.hermes2_adapter import Hermes2Engine

engine = Hermes2Engine()  # defaults work out of the box
results = engine.process_tool_calls(
    [{"name": "read_file", "args": {"path": "/etc/hostname"}}],
    executor_fn=lambda tc: open(tc.args["path"]).read()
)
# results = {tool_id: {"content": "...", "was_truncated": False, ...}}
```

**Reality check:** This works for read-only tools only. Anything requiring
`write_file`, `patch`, or `terminal` is silently dropped (see Pitfall #1).

---

## 2. Common Pitfalls

### Pitfall 1: CRITICAL — All Write Operations Silently Dropped

The permission pipeline marks `write_file`, `patch`, and `terminal` as
`PermissionLevel.PROMPT`, which sets `decision.allowed = False`.

`process_tool_calls` filters on `decision.allowed`, so **every write
operation is silently discarded** with no error, no warning, no callback.

```python
# This returns {} — silently, no indication why
engine.process_tool_calls(
    [{"name": "write_file", "args": {"path": "/tmp/x", "content": "hi"}}],
    executor_fn=lambda tc: "wrote file"
)
# → {}
```

**Impact:** Any new developer integrating this will spend hours wondering
why tools "don't work." The PROMPT level needs a confirmation callback or
an `auto_approve` mode.

**FIX APPLIED:** Added `on_permission_prompt` callback to `Hermes2Config`
and updated `process_tool_calls` to call it for PROMPT decisions.

### Pitfall 2: Silent Drop of Non-Dict Inputs

```python
engine.process_tool_calls(["bad", 42, None], executor_fn=...)
# → {}  (no error, no log)
```

Non-dict entries in `tool_calls` are silently skipped via `continue`.
Should at least log a warning.

### Pitfall 3: Denied Calls Return Empty Dict (No Feedback)

When permissions deny calls, the result dict is empty. There's no way to
distinguish "no tool calls provided" from "all tool calls denied."

### Pitfall 4: Async/Sync Ambiguity in Hooks

`_run_hooks_sync` creates a new `ThreadPoolExecutor` on **every turn**.
Inside an async context, it spawns a thread that calls `asyncio.run()`,
which creates yet another event loop. This is fragile and wasteful.

### Pitfall 5: `process_turn` Requires You to Know the Pipeline

```python
# You must pass messages, tool_calls, AND tool_results separately
result = engine.process_turn(messages, tool_calls, tool_results)
# But tool_results is YOUR responsibility to construct — the engine
# doesn't use the results from process_tool_calls()
```

There's no integrated "process a full turn" that chains tool execution
through to hook processing.

### Pitfall 6: `get_context_messages` Doesn't Get Called Automatically

Memory injection into the system prompt is opt-in via `get_context_messages()`.
If you forget to call it before sending messages to the LLM, you lose all
memory context. This should be documented prominently.

### Pitfall 7: `from_config()` Silently Ignores Typos

```python
engine = from_config({"max_workrs": 8})  # typo — silently uses default max_workers=8
```

No warning for unknown keys. A developer who fat-fingers a key name will
get mysterious default behavior.

---

## 3. Missing Convenience Methods

### 3.1 `engine.chat(messages)` → processed messages
There's no high-level method that does:
1. Inject memory context
2. Check compression
3. Return ready-to-send messages

Users must call `get_context_messages()` then check `process_turn()` manually.

### 3.2 `engine.add_permission(tool_name, level)` → None
To allow write operations, you must manually construct `PermissionRule`
objects and manage the pipeline. Should be a one-liner.

### 3.3 `engine.reset()` or `engine.clear()`
No way to reset the engine state (turn counter, dedup cache, stats)
without creating a new instance.

### 3.4 `engine.process_tool_calls_async(...)`
The sync `process_tool_calls` blocks. For async-first codebases (common
with LLM APIs), there's no async variant exposed at the engine level.

### 3.5 `engine.get_pressure()` → float
Pressure is buried in `engine.compressor.monitor.current`. Should be a
top-level convenience property.

### 3.6 `engine.add_memory(content, type="memory", tags=[])` → str
Adding a memory requires constructing a `MemoryEntry` object, importing
`MemoryType`, and calling `engine.memory.add()`. Should be a simple
method on the engine.

### 3.7 `engine.search_memories(query)` → list[MemoryEntry]
Same — buried behind `engine.memory.search()`.

### 3.8 Iterator/Batch API for Tool Results
No `engine.process_tool_calls_stream()` for getting results as they
complete rather than waiting for all to finish.

---

## 4. Error Message Quality

### Good
- `PermissionPipeline.check()` returns descriptive `PermissionDecision.reason`
- `ContextCompressorV2.compress()` raises `ValueError` for unknown levels
- `ToolResultManager._save_to_disk()` raises `ValueError` for path traversal

### Bad / Cryptic
- **Silent drops everywhere:** Non-dict tool calls, denied tools, PROMPT
  tools — all return empty dicts with no indication of failure
- **`_run_hooks_sync` error swallowing:** If hooks fail, errors are
  captured in `HookResult.error` but the engine doesn't surface them.
  The caller of `process_turn` gets a dict with `hooks_results` but
  must manually check each result's `success` field.
- **Memory system load:** `MemoryStore.load()` catches JSONDecodeError,
  KeyError, ValueError and silently starts fresh. No log, no warning
  that your memories were lost due to corruption.
- **`auto_dream.py` `_last_promote_count`:** Uses `getattr` with default
  0 for an attribute that should be initialized in `__init__`. Not an
  error, but a code smell that suggests the API wasn't fully designed.

### Recommendations
- Add a `warnings.warn()` for silent drop paths
- Consider a `engine.last_warnings: list[str]` accumulator
- Log memory corruption rather than silently discarding

---

## 5. Configuration Confusion Points

### 5.1 `memory_storage_path` vs `disk_result_dir`
Two separate path configs for different persistence concerns. Not clear
from names alone which does what. `memory_storage_path` = where memories
are saved as JSON. `disk_result_dir` = where large tool results are saved.

### 5.2 `compression_profile` accepts strings but `ValueError` is vague
```python
engine = Hermes2Engine(Hermes2Config(compression_profile="fast"))
# ValueError: 'fast' is not a valid CompressionProfile
```
The valid values ("aggressive", "balanced", "gentle") are not in the error
message.

### 5.3 `max_context_tokens` Used in Two Places
`Hermes2Config.max_context_tokens` is used for both:
- `ContextCompressorV2(model_token_limit=max_context_tokens)`
- `ToolResultManager(max_tokens=max_context_tokens // 2)`

The `// 2` division for the result manager is a magic number with no
explanation. Why half?

### 5.4 `auto_dream_threshold` Counts Sessions But Never Incremented
The `AutoDreamer._session_count` is only incremented via `record_session()`,
which the engine never calls. So `should_dream()` will always return False
unless the user manually calls `auto_dreamer.record_session()`.

### 5.5 `enable_hooks` vs `enable_auto_dream` — Boolean Overload
Two separate boolean flags control different subsystems. Easy to forget
one or the other. A single `features: list[str]` or `FeatureFlags` might
be clearer.

### 5.6 `permission_rules` Replaces All Defaults
Passing `permission_rules=[...]` replaces ALL default rules. There's no
`extra_permission_rules` to add rules on top of defaults. Easy to
accidentally remove read-only auto-approval.

---

## 6. Top 3 API Improvements

### Improvement 1: Add Permission Confirmation Callback

**Problem:** PROMPT tools are silently dropped. There's no way for users
to approve tool calls at runtime.

**Solution:** Add `on_permission_prompt` callback to config:

```python
@dataclass
class Hermes2Config:
    on_permission_prompt: Optional[Callable[[str, dict, str], bool]] = None
```

```python
# In process_tool_calls:
if decision.needs_prompt and self.config.on_permission_prompt:
    if self.config.on_permission_prompt(name, args, decision.reason):
        allowed_calls.append(tc)
```

**FIX APPLIED** in this review.

### Improvement 2: Integrated `process_full_turn()` Method

**Problem:** Users must manually chain `get_context_messages()`,
`process_tool_calls()`, and `process_turn()`. The pipeline is split
across 3 methods with no guidance on ordering.

**Solution:** Add a single method:

```python
def process_full_turn(
    self,
    messages: list[dict],
    tool_calls: list[dict],
    executor_fn: Callable,
) -> dict:
    """One-call turn processing:
    1. Inject memory context
    2. Execute tool calls (with permissions)
    3. Run post-turn hooks
    4. Check compression
    Returns everything the caller needs.
    """
```

### Improvement 3: Return Denied/Prompted Tool Info in Results

**Problem:** `process_tool_calls` returns `{}` when tools are denied.
No way to tell the LLM "this tool was blocked" or "this needs approval."

**Solution:** Return a richer result structure:

```python
{
    "processed": {tool_id: {...}},
    "denied": [{"name": "terminal", "reason": "dangerous pattern"}],
    "needs_prompt": [{"name": "write_file", "reason": "requires confirmation"}],
}
```

**FIX APPLIED** in this review.

---

## 7. Circular Import Analysis

### Import Graph (no cycles found)

```
tool_orchestrator      → (none)
tool_result_manager    → (none)
permission_pipeline    → (none)
context_compressor_v2  → (none)
memory_system          → (none)
coordinator            → (none)
post_turn_hooks        → context_compressor_v2, memory_system
auto_dream             → memory_system
hermes2_adapter        → ALL of the above
```

**Verdict: NO circular imports.** The dependency graph is a clean DAG.

### Module Load Order Issues

1. **Deferred imports inside methods (minor smell):**
   - `hermes2_adapter.py:105` — `from .auto_dream import DreamTrigger`
     inside `__init__`. This is already imported at module level (line 37).
     The deferred import is redundant.
   - `hermes2_adapter.py:337` — `from .memory_system import MemoryType`
     inside `_extract_and_store_memories`. Also already available at
     module level via line 27. Redundant.

2. **`from __future__ import annotations` everywhere:** This means all
   type annotations are strings at runtime. No runtime issues, but
   `isinstance()` checks on annotated types would need care.

3. **No `__init__.py` exports:** The `__init__.py` is a design doc, not
   a proper package init. Users must import from submodules directly.
   This is fine for now but should export key classes eventually.

---

## 8. Direct Usability Fixes Applied

1. **Added `on_permission_prompt` callback** to `Hermes2Config` and
   `process_tool_calls` — PROMPT tools now get a confirmation callback
2. **Added `add_rule()` convenience** — quick method to allow specific tools
3. **Added `get_pressure()` property** — direct access to context pressure
4. **Added `add_memory()` and `search_memories()` convenience methods**
5. **Changed `from_config()` to warn on unknown keys** instead of silent ignore
6. **Removed redundant deferred imports** in hermes2_adapter.py
7. **Added `allowed` and `needs_prompt` tracking** to process_tool_calls results

---

## 9. Summary

| Aspect | Rating | Notes |
|--------|--------|-------|
| Quick start | ⭐⭐⭐ | Works for reads, broken for writes |
| Error messages | ⭐⭐ | Mostly silent drops |
| API completeness | ⭐⭐ | Missing high-level convenience methods |
| Configuration | ⭐⭐⭐ | Sensible defaults, confusing edge cases |
| Import hygiene | ⭐⭐⭐⭐ | Clean DAG, no cycles |
| Documentation | ⭐⭐ | Docstrings exist but usage patterns unclear |
| Overall | ⭐⭐⭐ | Solid foundation, needs UX polish |

The modules are well-engineered internally but the **integration layer
(hermes2_adapter) silently drops operations** that require confirmation.
This is the #1 usability blocker for adoption.
