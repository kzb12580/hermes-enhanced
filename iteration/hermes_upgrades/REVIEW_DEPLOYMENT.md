# Deployment Readiness Review — hermes_upgrades

**Date**: 2026-05-24
**Scope**: All 16 source `.py` files in `/root/claude-code-study/iteration/hermes_upgrades/`
**Status**: ✅ PASS with fixes applied

---

## Summary of Findings

| # | Category | Severity | Status |
|---|----------|----------|--------|
| 1 | Hardcoded paths | Low | ✅ OK — No hardcoded paths in source (only test fixtures) |
| 2 | /tmp usage | Low | ✅ OK — `tempfile.mkstemp()` always uses `dir=` param, never raw /tmp |
| 3 | Signal handling | **High** | ✅ **FIXED** — Added SIGTERM/SIGINT handlers to Hermes2Engine |
| 4 | Unbounded caches/queues | **High** | ✅ **FIXED** — Capped 4 unbounded collections |
| 5 | File descriptor leaks | Low | ✅ OK — mkstemp/fdopen patterns use proper try/finally cleanup |
| 6 | Environment variable support | **Medium** | ✅ **FIXED** — Hermes2Config now reads HERMES_* env vars |
| 7 | Health check capability | **Medium** | ✅ **FIXED** — Added `health_check()` method to Hermes2Engine |
| 8 | Log level appropriateness | Medium | ⚠️ Only 2/16 modules use logging (mcp_transport, hermes2_adapter) |

---

## Detailed Findings

### 1. Hardcoded Paths — ✅ OK
- No hardcoded filesystem paths in production code.
- `DEFAULT_TOOL_BUDGETS` is duplicated in 3 files (token_utils.py, tool_result_manager.py, token_budget_manager.py) — minor DRY violation but not a deployment blocker.

### 2. /tmp Usage — ✅ OK
- `memory_system.py:310` and `tool_result_manager.py:385` use `tempfile.mkstemp()` with explicit `dir=` pointing to configured storage directories.
- No raw `/tmp` references in source code.
- Test files use `/tmp` in fixtures — acceptable.

### 3. Signal Handling — ✅ FIXED
**Before**: No signal handling anywhere. SIGTERM during long sessions would lose:
- Dirty memory store state (pending writes)
- MCP subprocess connections (orphaned processes)
- Pending auto-dream summaries

**After**: `Hermes2Engine._setup_signal_handlers()` installs SIGTERM/SIGINT handlers that:
- Flush the memory store to disk
- Run registered shutdown hooks
- Log shutdown progress
- Gracefully handle non-main-thread contexts

### 4. Unbounded Caches/Queues — ✅ FIXED
**Before** (memory leak vectors):
- `PressureMonitor.history` — grew unbounded with every `update()` call
- `ContextCompressorV2._stats_ratios` — grew with every compression
- `TokenBudgetManager._turns` — grew every turn, never trimmed
- `AutoDreamer._history` — grew with every dream cycle

**After** (bounded):
- `PressureMonitor.history` — capped at 1,000 entries (sliding window)
- `ContextCompressorV2._stats_ratios` — capped at 1,000 entries
- `TokenBudgetManager._turns` — capped at 500 entries
- `AutoDreamer._history` — capped at 100 entries

### 5. File Descriptor Leaks — ✅ OK
- `memory_system.py` and `tool_result_manager.py` use atomic-write pattern: `tempfile.mkstemp()` → `os.fdopen()` → write → `os.replace()`. Both have proper `try/except BaseException` cleanup that calls `os.unlink(tmp_path)` on failure.
- `StdioTransport` opens stderr PIPE but never reads it. In high-stderr-output scenarios, the OS pipe buffer (~64KB) could fill and block the subprocess. **Minor risk** — not fixed in this pass (would require async stderr reader task).

### 6. Environment Variable Support — ✅ FIXED
**Before**: `config.py` module existed with helpers (`env_int`, `env_float`, `env_str`, `env_bool`) but **no module actually used them**. All values were hardcoded.

**After**: `Hermes2Config` now reads environment variables as defaults:

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `HERMES_MAX_WORKERS` | int | 8 | Max concurrent tool workers |
| `HERMES_MAX_CONTEXT_TOKENS` | int | 200000 | Model context window size |
| `HERMES_COMPRESSION_PROFILE` | str | "balanced" | Compression aggressiveness |
| `HERMES_MEMORY_STORAGE_PATH` | str | None | Memory persistence file path |
| `HERMES_DISK_RESULT_DIR` | str | None | Large result disk directory |
| `HERMES_AUTO_DREAM_THRESHOLD` | int | 5 | Sessions before dream cycle |
| `HERMES_ENABLE_HOOKS` | bool | true | Enable post-turn hooks |
| `HERMES_ENABLE_AUTO_DREAM` | bool | true | Enable auto-dream |

### 7. Health Check — ✅ FIXED
**Before**: No health check capability. `McpManager.get_server_status()` existed but was transport-specific only.

**After**: `Hermes2Engine.health_check()` returns a structured dict with:
- Overall status: `healthy` / `degraded` / `unhealthy`
- Component-level health for: memory store, context pressure, result manager, hooks pipeline
- Current turn count and ISO timestamp
- Suitable for Kubernetes liveness/readiness probes

### 8. Log Level Appropriateness — ⚠️ NOTED
- Only `mcp_transport.py` and `hermes2_adapter.py` use `logging.getLogger()`.
- Remaining 14 modules have **zero logging** — all errors are silently swallowed or converted to return values.
- **Recommendation**: Add `logger = logging.getLogger(__name__)` and debug/info logging to: `coordinator.py`, `smart_retry.py`, `auto_dream.py`, `tool_orchestrator.py`, `memory_system.py`, `context_compressor_v2.py`. This is a follow-up task, not a deployment blocker.

---

## Files Modified

1. **hermes2_adapter.py** — Added env var support to Hermes2Config, signal handling, health check
2. **context_compressor_v2.py** — Bounded PressureMonitor.history and _stats_ratios
3. **token_budget_manager.py** — Bounded _turns list
4. **auto_dream.py** — Bounded _history list

## Files NOT Modified (already good)

- `config.py` — Well-written env helper module (just needed to be *used*)
- `coordinator.py` — Clean design, no deployment issues
- `permission_pipeline.py` — Solid security patterns
- `tool_orchestrator.py` — Good concurrency control
- `mcp_transport.py` — Has proper async cleanup
- `memory_system.py` — Proper atomic writes and thread safety
- `token_utils.py` — Clean utility module
- `post_turn_hooks.py` — Good async error handling
- `async_pipeline.py` — Clean async architecture
- `tool_result_manager.py` — Proper bounded caches via OrderedDict
- `smart_retry.py` — Thread-safe circuit breaker
- `tool_result_summarizer.py` — Pure functions, no state issues
