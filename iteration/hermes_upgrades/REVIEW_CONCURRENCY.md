# Concurrency Correctness Audit

**Date:** 2026-05-24
**Scope:** All `.py` source files in `hermes_upgrades/` (excluding tests)
**Auditor:** Concurrency analysis agent

---

## Executive Summary

The codebase has a clear intended concurrency model: `ToolOrchestrator` uses `ThreadPoolExecutor` to run tool calls in parallel, and shared state objects (`MemoryStore`, `ResultDeduplicator`, `CircuitBreaker`) are accessed from these pool threads. **None of the shared mutable state objects are thread-safe.** Three HIGH issues were identified and fixed directly. Five MEDIUM issues are documented below with recommended mitigations.

---

## Issues Found

### ISSUE-1: CircuitBreaker — Non-atomic state transitions [HIGH] ✅ FIXED

**File:** `smart_retry.py`, lines 230–262, `CircuitBreaker` class
**Problem:** `consecutive_failures += 1` is 4 bytecodes (LOAD_ATTR, LOAD_CONST, BINARY_OP, STORE_ATTR). Two threads can read the same counter value and both store `value+1`, losing an increment. Additionally, `allow_request()` does a check-then-act on `state` (OPEN→HALF_OPEN transition) that races with `record_failure()`.

**Reproduction scenario:**
```python
breaker = CircuitBreaker(failure_threshold=5)
# Thread A and B both call record_failure() concurrently
# Both read consecutive_failures=4, both store 5
# Actual count: 5 (should be 6), circuit may not open when expected
```

**Fix applied:** Added `threading.Lock` via `__post_init__`. All state-mutating methods (`record_success`, `record_failure`, `allow_request`, `reset`) acquire the lock. `allow_request()` compound check-then-modify is now atomic.

---

### ISSUE-2: ResultDeduplicator — Non-atomic LRU operations [HIGH] ✅ FIXED

**File:** `tool_result_manager.py`, lines 61–102, `ResultDeduplicator` class
**Problem:** `is_duplicate_hash()` does `if h in self._seen: self._seen.move_to_end(h)` — a compound check-then-modify. `register()` does `if h in self._seen: move_to_end; return` then `self._seen[h] = None; if len > max: popitem` — multiple non-atomic operations. Concurrent calls corrupt the LRU ordering and can cause size invariant violations (more than `max_seen` entries).

**Reproduction scenario:**
```python
dedup = ResultDeduplicator(max_seen=2)
# Thread A: register("a") → len becomes 2
# Thread B: register("c") → passes len > max_seen after Thread A added
# Thread C: register("d") → also passes, both pop oldest
# Result: only 1 entry remains (should be 2)
```

**Fix applied:** Added `threading.Lock`. `is_duplicate_hash()`, `register()`, and `clear()` all acquire the lock. `hash_result()` remains lock-free (static, pure computation).

---

### ISSUE-3: MemoryStore — Non-atomic compound dict operations [HIGH] ✅ FIXED

**File:** `memory_system.py`, lines 177–361, `MemoryStore` class
**Problem:**
1. `add()` does `if len >= max: _evict(); self._entries[id] = entry` — two threads can both pass the length check and exceed `max_entries`.
2. `search()` does `list(self._entries.values())` which can raise `RuntimeError: dictionary changed size during iteration` if another thread mutates `_entries` concurrently.
3. `save()` iterates `self._entries.values()` to serialize — concurrent modification produces inconsistent JSON.
4. `prune()` builds a list of IDs then deletes — concurrent `add()`/`delete()` can cause the list to go stale.
5. `get()` reads and updates `entry.access_count += 1` — not atomic (though benign in CPython for simple ints).

**Reproduction scenario:**
```python
store = MemoryStore(max_entries=5)
# Fill to capacity with 5 entries
# Thread A: add(entry_6) → checks len=5 >= 5, calls _evict()
# Thread B: add(entry_7) → checks len=5 >= 5 (same moment), calls _evict()
# Both evict, then both add → len=5, but TWO entries were evicted instead of ONE
```

**Fix applied:** Added `threading.RLock` (reentrant because `_auto_save_immediate` → `save()` re-acquires). All public methods (`add`, `get`, `search`, `update`, `delete`, `prune`, `get_stats`, `save`, `load`, `flush`, `entries` property) acquire the lock. `search()` releases the lock after taking a snapshot of `_entries.values()`, then performs scoring outside the lock.

---

### ISSUE-4: ToolResultManager.process() — Non-atomic dedup+cache+stats [HIGH] ✅ FIXED

**File:** `tool_result_manager.py`, lines 244–323, `ToolResultManager.process()` method
**Problem:** `process()` performs a compound operation: check dedup → truncate → save to disk → register in dedup → update cache → update stats. If two threads call `process()` with the same content, both could pass the dedup check before either registers, causing double-processing. Stats counters (`self._stats["total_processed"] += 1`) are also non-atomic.

**Reproduction scenario:**
```python
mgr = ToolResultManager()
# Thread A: process("tool", "same_content") → is_duplicate=False
# Thread B: process("tool", "same_content") → is_duplicate=False (A hasn't registered yet)
# Both process and register → content processed twice, stats wrong
```

**Fix applied:** Added `threading.Lock` (`_process_lock`) to `ToolResultManager.__init__`. The entire `process()` method body is wrapped in `with self._process_lock:`. This serializes processing which is acceptable since:
- The per-call cost is dominated by truncation (CPU) and disk I/O (already serialized by OS)
- Correctness of dedup requires atomicity of check+register
- Stats consistency requires atomicity

---

### ISSUE-5: SmartRetryManager.get_circuit() — TOCTOU race [MEDIUM]

**File:** `smart_retry.py`, lines 334–338
**Problem:** `get_circuit()` does `if tool_name not in self._circuits: self._circuits[name] = CircuitBreaker()`. Two threads calling `get_circuit("web_extract")` simultaneously could both create a new `CircuitBreaker`, with one overwriting the other's (possibly already recording failures). The overwritten breaker's failure state is lost, preventing the circuit from opening.

**Status:** Partially mitigated by ISSUE-1 fix (CircuitBreaker is now internally thread-safe). The TOCTOU on dict insertion is benign in CPython (GIL protects dict.__setitem__), but the logical race (lost failure state) remains. Full fix requires a lock around `get_circuit()`. Not applied because `SmartRetryManager` is not currently integrated into the ThreadPoolExecutor path.

---

### ISSUE-6: HookPipeline._hooks list mutation during iteration [MEDIUM]

**File:** `post_turn_hooks.py`, lines 370–458, `HookPipeline` class
**Problem:** `register()` replaces `self._hooks` with a new list (`self._hooks = [h for h in self._hooks if h.name != hook.name]`). If `run_all()` is iterating `self._hooks` concurrently, it holds a reference to the old list — which is safe in CPython. However, `set_enabled()` iterates `self._hooks` and modifies hook objects — if `register()` replaces the list between the iteration and the modification, the wrong hook could be modified.

**Status:** In practice, `run_all()` is always awaited from a single async context, and `register()` is only called during initialization. The pattern is safe but fragile. A `threading.Lock` would add unnecessary complexity for the current usage.

---

### ISSUE-7: TokenBudgetManager — Non-atomic counter operations [MEDIUM]

**File:** `token_budget_manager.py`, lines 95–323
**Problem:** `record_usage()` does `self._current_turn.total_tokens += actual_tokens` (non-atomic read-add-write). `allocate()` reads `pressure_zone` and `remaining_tokens` which depend on `_used_tokens` and `_current_turn.total_tokens`. If hooks call `allocate()` or `record_usage()` from different threads, stale reads and lost updates are possible.

**Status:** In the current architecture, `begin_turn()`, tool execution, `record_usage()`, and `end_turn()` are called sequentially from the main loop. Not used from pool threads. Lock not applied.

---

### ISSUE-8: PressureMonitor.history list — Benign race [LOW]

**File:** `context_compressor_v2.py`, lines 99–132
**Problem:** `history.append(pressure)` and `history[-1]` could race. In CPython, `list.append()` is a single bytecode and `list.__getitem__` is also atomic, so this is safe. In other Python implementations (PyPy, GraalPy), this could be an issue.

**Status:** No fix needed for CPython. Documented for awareness.

---

### ISSUE-9: asyncio event loop handling in ToolOrchestrator [MEDIUM]

**File:** `tool_orchestrator.py`, lines 256–289, `_run_one()` method
**Problem:** When an async `executor_fn` is called from a thread (inside `ThreadPoolExecutor`), `_run_one` creates a new `ThreadPoolExecutor(max_workers=1)` just to run the coroutine in a new event loop. This means:
1. Each async tool call creates a nested ThreadPoolExecutor (resource waste)
2. The `coro` object is captured by closure — if the coroutine holds references to large objects, they're kept alive longer than necessary
3. `asyncio.new_event_loop()` in the inner thread is correct but creates a new loop per call

**Status:** Functional but wasteful. Could be improved by sharing a single background event loop thread. Not a correctness bug.

---

### ISSUE-10: ContextVar propagation [LOW]

**Files:** `tool_orchestrator.py`, `hermes2_adapter.py`
**Problem:** No explicit `ContextVar` usage found in the codebase. However, if user-provided `executor_fn` relies on `ContextVar` for request-scoped data, propagation depends on the execution path:
- `ThreadPoolExecutor.submit()` → copies current context (Python 3.7+) ✅
- `asyncio.run()` in new thread → creates new context, outer ContextVars lost ❌
- `loop.run_until_complete()` → runs in current task context ✅

**Status:** The `asyncio.run()` path in `_run_concurrent` and `_run_hooks_sync` would lose ContextVars from the outer scope. This is a design limitation, not a bug in the current code.

---

### ISSUE-11: File I/O atomicity [OK]

**Files:** `memory_system.py` (lines 290–313), `tool_result_manager.py` (lines 348–390)
**Assessment:** Both use `tempfile.mkstemp()` + `os.replace()` which is atomic on POSIX. Both call `f.flush()` + `os.fsync()` before rename. Concurrent writes to the same file are safe: each creates a unique temp file, and `os.replace()` is atomic. The last writer wins, which is correct.

---

### ISSUE-12: StdioTransport._request_id counter [LOW]

**File:** `mcp_transport.py`, lines 190–192
**Problem:** `self._request_id += 1` is non-atomic. But `StdioTransport` is used from a single async context (one event loop), so concurrent access is not possible.

---

## Summary Table

| # | Issue | Severity | File | Fixed? |
|---|-------|----------|------|--------|
| 1 | CircuitBreaker non-atomic state | HIGH | smart_retry.py | ✅ |
| 2 | ResultDeduplicator non-atomic LRU | HIGH | tool_result_manager.py | ✅ |
| 3 | MemoryStore non-atomic dict ops | HIGH | memory_system.py | ✅ |
| 4 | ToolResultManager.process() race | HIGH | tool_result_manager.py | ✅ |
| 5 | SmartRetryManager.get_circuit TOCTOU | MEDIUM | smart_retry.py | — |
| 6 | HookPipeline list mutation | MEDIUM | post_turn_hooks.py | — |
| 7 | TokenBudgetManager counters | MEDIUM | token_budget_manager.py | — |
| 8 | PressureMonitor history list | LOW | context_compressor_v2.py | — |
| 9 | Nested ThreadPoolExecutor | MEDIUM | tool_orchestrator.py | — |
| 10 | ContextVar propagation | LOW | multiple | — |
| 11 | File I/O atomicity | OK | multiple | N/A |
| 12 | StdioTransport counter | LOW | mcp_transport.py | — |

## Fixes Applied

All HIGH issues (1–4) were fixed by adding `threading.Lock` / `threading.RLock` to the affected classes. The locks protect compound operations that would otherwise race under concurrent access from `ToolOrchestrator`'s `ThreadPoolExecutor`.

Lock granularity was chosen to minimize contention:
- `MemoryStore`: RLock (reentrant) because `_auto_save_immediate()` → `save()` re-acquires
- `ResultDeduplicator`: Lock on `is_duplicate_hash`, `register`, `clear` only
- `ToolResultManager`: Lock on `process()` (coarse-grained but correct)
- `CircuitBreaker`: Lock on all state-mutating methods
