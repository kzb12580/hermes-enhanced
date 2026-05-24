# Review Round 27 — 17-Model Mega Review

## Models Used (12/17 succeeded)

### Gemini (CLI Proxy API, port 5533)
| Model | Modules | Findings |
|-------|---------|----------|
| gemini-2.5-flash ✅ | tool_orchestrator, async_pipeline | 2 CRITICAL |
| gemini-2.5-pro ✅ | coordinator, memory_system | 1 HIGH, 1 MEDIUM |
| gemini-3.1-flash-lite ✅ | permission_pipeline, smart_retry | 2 HIGH |
| gemini-3.5-flash ✅ | context_compressor_v2, token_budget_manager | 1 MEDIUM |
| gemini-3.1-pro-preview ❌ | auto_dream, post_turn_hooks | Timeout |
| gemini-3-flash-preview ❌ | tool_result_manager, tool_result_summarizer | Timeout |
| gemini-3-pro-preview ❌ | hermes2_adapter, mcp_transport | Timeout |

### GPT (CLI Proxy API, port 5533)
| Model | Modules | Findings |
|-------|---------|----------|
| gpt-5.3-codex ✅ | tool_orchestrator, coordinator | 2 HIGH |
| gpt-5.4 ✅ | async_pipeline, memory_system | 2 HIGH |
| gpt-5.4-mini ✅ | permission_pipeline, auto_dream | 2 HIGH |
| gpt-5.5 ✅ | post_turn_hooks, context_compressor_v2 | 1 MEDIUM |

### Claude (Kiro Gateway, port 8000)
| Model | Modules | Findings |
|-------|---------|----------|
| claude-haiku-4.5 ✅ | smart_retry, token_budget_manager | 1 CRITICAL |
| claude-sonnet-4 ✅ | tool_result_manager, tool_result_summarizer | No bugs found |
| claude-opus-4.7 ✅ | permission_pipeline, auto_dream | 2 MEDIUM |
| claude-opus-4.6 ✅ | coordinator, memory_system | No bugs found |
| claude-sonnet-4.5 ❌ | hermes2_adapter, mcp_transport | Empty response |
| claude-opus-4.5 ❌ | tool_orchestrator, async_pipeline | Timeout |

## Bugs Found & Fixed

### 1. [CRITICAL] CircuitBreaker._probe_sent not reset on probe failure
**File:** smart_retry.py  
**Found by:** Claude Haiku 4.5  
**Issue:** When a probe request fails in HALF_OPEN state, `_probe_sent` is not reset. On next recovery timeout, circuit transitions to HALF_OPEN with `_probe_sent=True`, blocking all subsequent requests permanently.  
**Fix:** Added `self._probe_sent = False` in `record_failure()` when transitioning to OPEN.

### 2. [CRITICAL] _async_executor hardcoded to max_workers=1
**File:** tool_orchestrator.py  
**Found by:** Gemini 2.5 Flash  
**Issue:** `_async_executor = ThreadPoolExecutor(max_workers=1)` serializes all async tool executions regardless of `self.max_workers` setting.  
**Fix:** Changed to `ThreadPoolExecutor(max_workers=self.max_workers)`.

### 3. [HIGH] nc/ncat patterns match inside "sync", "concat"
**File:** permission_pipeline.py  
**Found by:** Claude Opus 4.7  
**Issue:** `(?:.*/)?nc\s+-[a-zA-Z]*l` matches `sync -l` because `(?:.*/)?` matches empty, then `nc` matches the trailing `nc` in `sync`.  
**Fix:** Changed to `(?:^|.*[/\s])nc\s+-[a-zA-Z]*l` to require word boundary.

### 4. [HIGH] update() ValueError on invalid MemoryType string
**File:** memory_system.py  
**Found by:** GPT-5.4  
**Issue:** `MemoryType(value)` raises ValueError for invalid strings, crashing the calling thread.  
**Fix:** Added try/except around MemoryType conversion, skip invalid values.

### 5. [HIGH] Could allocate more tokens than requested
**File:** token_budget_manager.py  
**Found by:** Gemini 3.5 Flash  
**Issue:** `max(200, available)` could make `available > requested` when `requested < 200`.  
**Fix:** Added `available = min(available, requested)` after the max(200, ...) check.

### 6. [MEDIUM] run_all/run_selected didn't catch general exceptions
**File:** post_turn_hooks.py  
**Found by:** GPT-5.5  
**Issue:** Only `asyncio.TimeoutError` was caught. Other exceptions from `copy.deepcopy(ctx)` or custom hooks would crash the whole pipeline.  
**Fix:** Added `except Exception` handler that returns `HookResult(success=False)`. Updated test to match new behavior.

## Test Results
- **Server:** 5.175.188.28 (Ubuntu x86_64, Python 3.14.4)
- **Result:** 859/859 PASSED (2.60s)
- **GitHub:** 597f0be

## Statistics
- Total models attempted: 17
- Successful reviews: 12
- Failed (timeout/empty): 5
- Bugs found: 6
- Bugs fixed: 6
- Tests: 859/859 ✅
