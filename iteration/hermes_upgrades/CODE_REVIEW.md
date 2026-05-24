# Code Review: P0 Modules — hermes_upgrades

**Reviewer:** Hermes Agent (automated)
**Date:** 2026-05-24
**Modules:** `tool_orchestrator.py`, `context_compressor_v2.py`, `tool_result_manager.py`

---

## Module 1: `tool_orchestrator.py`

### MUST_FIX

**1. `asyncio.run()` will fail inside a running event loop**
`_run_concurrent` (line 304) calls `asyncio.run()` to execute the async path. If the orchestrator is ever invoked from within an existing async context (common in Hermes Agent), this raises `RuntimeError: This event loop is already running`. Similarly, `_run_one` (line 278) creates a new event loop via `asyncio.new_event_loop()` which will also fail if called from within a running loop.

```python
# line 304 — problematic
return asyncio.run(
    self._run_concurrent_async(batch, executor_fn, on_progress)
)
```

Fix: Use `asyncio.get_event_loop().run_until_complete()` or detect the running loop and schedule into it. Better yet, make `execute` async-native and provide a sync wrapper with `loop.run_until_complete`.

**2. `ToolCall.id` defaults to empty string — silent key collisions**
`ToolCall.id = ""` (line 26). If multiple tool calls are created without explicit IDs, `execute` stores results keyed by `tc.id`, so they silently overwrite each other in the `results` dict. Either make `id` required or auto-generate (e.g., `uuid4`).

### SHOULD_FIX

**3. Read-read conflict check is dead code (lines 155–166)**
The second pass in `partition` checks `has_write_conflict` between pairs of read-only tools. But `has_write_conflict` requires at least one tool to be `WRITE_SERIAL` or `AMBIGUOUS` (line 115–118). Two `READ_ONLY` tools will **never** trigger a conflict. This entire loop is a no-op that gives a false sense of safety. If read-read conflicts are a concern (e.g., two `search_files` on overlapping paths), the logic needs a separate check.

**4. Deferred reads are lumped into one batch without cross-checking**
Lines 175–196: deferred reads (those conflicting with writes) are all placed in a single batch at the end. If two deferred reads touch the same file, they'll run concurrently — which is fine for reads, but the code doesn't verify this. More importantly, if a read conflicts with write A but write B also touches the same path and comes after write A, the deferred read runs after ALL writes, which is correct but the comment/structure doesn't make this clear.

**5. Path normalization missing**
`FileConflictDetector.extract_paths` stores raw path strings. `/tmp/foo`, `/tmp/../tmp/foo`, and `/tmp/./foo` are treated as different paths. Use `Path.resolve()` or `os.path.normpath()`.

### NICE_TO_HAVE

**6. `_run_one` duplicates timing/error logic with `_run_concurrent_async`**
The sync single-call path (lines 264–293) and async path (lines 330–349) have nearly identical timing/progress/error handling. Factor into a shared helper.

**7. `executor_fn` type is loose**
The type hint is `Callable[[ToolCall], Any]` but it can return either a value or a coroutine. Consider a `Union` or overloads for better type safety.

### Test Coverage Gaps

- **No async executor test.** All tests use sync executors. The `iscoroutinefunction` / `asyncio.run` paths are untested.
- **No test for duplicate `ToolCall.id`** — would reveal the silent overwrite bug.
- **No test for `max_workers` actually limiting concurrency** — the thread pool test checks `>1` thread but doesn't verify the cap.
- **No test for error in concurrent batch** — only single-item errors are tested.

---

## Module 2: `context_compressor_v2.py`

### MUST_FIX

**1. `_auto_compress` target ratio is inverted for AGGRESSIVE profile**
Line 463:
```python
target = 1.0 - self.profile.pressure_threshold + 0.3
```
| Profile | Threshold | Target |
|---------|-----------|--------|
| AGGRESSIVE | 0.60 | **0.70** |
| BALANCED | 0.75 | 0.55 |
| GENTLE | 0.85 | 0.45 |

AGGRESSIVE has the **highest** target ratio (0.70), meaning it compresses the *least*. This is backwards — aggressive should compress more, not less. The formula should be something like `target = self.profile.pressure_threshold - 0.3` or use a direct mapping.

**2. `_estimate_tokens` (module-level) returns 1 for empty string**
Line 34: `return max(1, len(text) // CHARS_PER_TOKEN)`. For `""`, this returns 1. But `TokenEstimator.estimate_tokens` in `tool_result_manager.py` correctly returns 0 for empty strings. This inconsistency means `_message_tokens` adds 11 tokens for an empty-content message, slightly inflating all pressure calculations.

### SHOULD_FIX

**3. `should_compress` has a hidden side effect**
Every call to `should_compress` (line 388) calls `self.monitor.update(messages)`, which appends to `self.monitor.history`. Calling it twice with the same messages creates duplicate history entries. This is surprising for a method that reads as a pure query. Either separate the update from the check, or document the side effect prominently.

**4. `level="full"` silently falls back to reactive**
Lines 426–427: requesting `level="full"` actually runs reactive compression at a tighter ratio. The returned `CompressedMessages.level_used` is `"reactive"`, not `"full"`. A caller who explicitly requests full compression gets no indication that it wasn't actually full (LLM-enhanced). Should either raise `NotImplementedError`, return a distinct level like `"full_fallback"`, or document this prominently.

**5. `ReactiveLevel` step 3 collapses by tool `name` — too aggressive**
Lines 238–253: Tool results are collapsed based on their `name` field. If you run `read_file` on 5 different files, 3 of those results get replaced with `[read_file result omitted — duplicate]`. These aren't duplicates — they're different files. Collapse should consider content similarity or tool call arguments, not just the tool name.

**6. `FullLevel.apply_summary` hardcodes `keep_tail = 4`**
This is not configurable and not documented why 4 was chosen. For long conversations with complex recent context, 4 messages may be insufficient.

### NICE_TO_HAVE

**7. `_total_tokens` called repeatedly without caching**
`ReactiveLevel.compress` calls `_total_tokens` after each step (lines 221, 234, 252), each time iterating all messages. For large conversations (1000+ messages), this is wasteful. Cache the result or pass it through.

**8. `PressureMonitor.history` grows unboundedly**
No max size. Over a long session with repeated `should_compress` calls, this list grows forever. Add a `maxlen` or periodic pruning.

### Test Coverage Gaps

- **No test for `_auto_compress` target ratio logic** — would have caught the inversion bug.
- **No test for `_estimate_tokens` with empty string** — inconsistency with `TokenEstimator`.
- **No test that `should_compress` records history** (side effect is untested).
- **No test for `ReactiveLevel` with many calls to the same tool** — would reveal the over-aggressive collapse.
- **No test for `FullLevel.apply_summary` when first message is not system**.
- **No test for empty message list** in `compress`.

---

## Module 3: `tool_result_manager.py`

### MUST_FIX

**1. `ProcessedResult.was_deduped` is never `True`**
When deduplication triggers (line 246–250), the cached `ProcessedResult` is returned. But this cached object was created on the *first* call with `was_deduped=False` (line 286). There is no code path that ever sets `was_deduped=True`. The field is dead and always lies. Fix: either set it on the cached return or create a new `ProcessedResult` with `was_deduped=True`.

```python
# line 246-250 — returns result with was_deduped=False
if self._dedup.is_duplicate(content):
    self._stats["dedup_saves"] += 1
    cached = self._cache.get(result_hash)
    if cached is not None:
        return cached  # was_deduped is False here!
```

**2. `assert` used for runtime check in `_save_to_disk`**
Line 314: `assert self._disk_dir is not None`. Running Python with `-O` strips all asserts. This would cause `None.write_text()` → `AttributeError` with no useful error message. Use `if self._disk_dir is None: raise RuntimeError(...)`.

### SHOULD_FIX

**3. `SmartTruncator.truncate` doesn't guarantee the result fits `max_tokens`**
The truncation is line-count-based (keep 30% head, 20% tail by line count). If each line is very long, the result can still exceed `max_tokens`. The function should verify the result and do a second pass (binary search on head/tail ratios) if needed.

**4. No thread safety**
`ToolResultManager` mutates shared state (`_dedup`, `_cache`, `_stats`) without locks. Since `tool_orchestrator.py` runs tool calls in a `ThreadPoolExecutor`, concurrent calls to `process` could corrupt `_stats` (lost updates on `+=`) or cause dict mutation during iteration. Add `threading.Lock` around `process`.

**5. `process` saves original content to disk but returns truncated**
Line 277: `self._save_to_disk(..., content, ...)` saves the full original. Line 283: the returned `ProcessedResult` has truncated content. This is a reasonable design (full version on disk, abbreviated in context) but is undocumented and could confuse callers who expect `content` to match what's on disk.

**6. Cache and deduplicator can desynchronize**
Both use `max_seen` as their bound, but they're evicted independently. The `_cache` evicts on line 296 when it exceeds `max_seen`, but the `_dedup` LRU evicts separately. If the cache evicts an entry but the deduplicator still has the hash, a future duplicate will hit `is_duplicate=True` but `cache.get(hash)` returns `None`, falling through to re-process (line 251 comment acknowledges this but doesn't set `was_deduped` correctly).

### NICE_TO_HAVE

**7. `SmartTruncator.truncate_for_tool` merges dicts every call**
Line 160: `{**DEFAULT_TOOL_BUDGETS, **(budgets or {})}` creates a new dict per call. For hot paths, pre-merge in `__init__`.

**8. `_save_to_disk` has no error handling**
Disk write failures (permissions, full disk) will propagate as unhandled exceptions. Consider catching and logging.

### Test Coverage Gaps

- **No test verifying `was_deduped=True`** — because it's impossible (this IS the bug).
- **No concurrent access test** — critical given the ThreadPoolExecutor usage in the orchestrator.
- **No test for `SmartTruncator` with single-line input** — edge case for the line-split logic.
- **No test for `SmartTruncator` when head+tail > total lines** — the fallback logic (lines 142–144) is untested.
- **No test for empty string input to `process`**.
- **No test for `_save_to_disk` failure modes**.

---

## Cross-Module Issues

### MUST_FIX

**1. Token estimation inconsistency**
Two independent `_estimate_tokens` / `TokenEstimator.estimate_tokens` implementations exist with different behavior for empty strings. `_estimate_tokens("")` returns 1; `TokenEstimator.estimate_tokens("")` returns 0. If these modules are used together (and they should be), this causes inconsistent accounting.

### SHOULD_FIX

**2. No integration between modules**
`ToolResultManager` and `ContextCompressorV2` both estimate tokens but use different estimators. `ToolOrchestrator` doesn't use either. These should share a single token estimation function.

**3. No shared constants**
`CHARS_PER_TOKEN = 4` appears in `context_compressor_v2.py`. The same heuristic is in `TokenEstimator.estimate_tokens` (implied `len // 4`). Should be a single constant.

---

## Summary by Severity

| Severity | Count | Modules |
|----------|-------|---------|
| **MUST_FIX** | 6 | orchestrator (2), compressor (2), result_mgr (2), cross-module (1 — counted above) |
| **SHOULD_FIX** | 11 | orchestrator (3), compressor (4), result_mgr (4) |
| **NICE_TO_HAVE** | 8 | orchestrator (2), compressor (2), result_mgr (2), cross-module (2) |

### Top 3 Priorities
1. **`was_deduped` never True** (`tool_result_manager.py`) — silent data lie, easy fix
2. **`_auto_compress` target ratio inverted** (`context_compressor_v2.py`) — aggressive compresses least
3. **`asyncio.run()` in running loop** (`tool_orchestrator.py`) — will crash in production async contexts
