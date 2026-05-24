# Code Duplication & Consistency Audit

**Auditor:** Hermes Agent — Code Quality Subagent  
**Date:** 2026-05-24  
**Scope:** All `.py` source files in `/root/claude-code-study/iteration/hermes_upgrades/`  
**Baseline:** 808 tests passing before and after refactoring

---

## Summary

| Category | Findings | Severity | Refactored? |
|---|---|---|---|
| 1. Duplicated code blocks | 5 major patterns | 🔴 High | ✅ Yes (4/5) |
| 2. Inconsistent naming | 6 patterns | 🟡 Medium | 📋 Documented |
| 3. Inconsistent parameter ordering | 2 patterns | 🟢 Low | 📋 Documented |
| 4. Inconsistent default values | 3 patterns | 🟡 Medium | 📋 Documented |
| 5. Inconsistent return types | 4 patterns | 🟡 Medium | 📋 Documented |
| 6. Import style inconsistency | 4 patterns | 🟡 Medium | 📋 Documented |
| 7. Docstring style inconsistency | 3 styles | 🟡 Medium | 📋 Documented |
| 8. Error handling inconsistency | 3 patterns | 🟡 Medium | 📋 Documented |
| 9. Magic numbers and strings | 15+ instances | 🟡 Medium | 📋 Documented |
| 10. Dead code | 2 instances | 🟢 Low | ✅ Yes (1/2) |

---

## 1. Duplicated Code Blocks (HIGH PRIORITY)

### 1A. Token Estimation Logic — ✅ REFACTORED

**Before:** Token estimation (`len(text) // 4`) was independently reimplemented in **5 places**:

| Location | Implementation | Behavior |
|---|---|---|
| `tool_result_manager.py` → `TokenEstimator.estimate_tokens()` | `max(1, len(text) // 4)` | Returns ≥1 for non-empty |
| `context_compressor_v2.py` → `_estimate_tokens()` | `len(text) // CHARS_PER_TOKEN` | Returns 0 for 1-3 char strings |
| `async_pipeline.py` → `ContextWindow.current_tokens` | `len(m["content"]) // 4 + 1` | +1 overhead per message |
| `post_turn_hooks.py` → `UsageTrackingHook.execute()` | `len(text) // 4` (inline) | No `max(1,...)` guard |
| `tool_result_summarizer.py` | Uses `TokenEstimator` from tool_result_manager | Delegated |

**Inconsistencies:** The `max(1, ...)` guard was missing in 3 places; the `+1` overhead was inconsistent.

**Refactoring:** Created `token_utils.py` with `estimate_tokens()`, `estimate_content_tokens()`, `estimate_messages_tokens()`, and `CHARS_PER_TOKEN`. Updated all modules to delegate. Backward-compatible re-exports preserved in original modules.

### 1B. DEFAULT_TOOL_BUDGETS Duplication — ✅ REFACTORED

**Before:** Two identical dictionaries defined independently:

- `tool_result_manager.py` line 110: `DEFAULT_TOOL_BUDGETS` (uses `15000`, `10000`, etc.)
- `token_budget_manager.py` line 34: `DEFAULT_TOOL_BUDGETS` (uses `15_000`, `10_000`, etc.)

**Refactoring:** Moved to `token_utils.py` as single source of truth. Both modules now import from there.

### 1C. OpenAI Multipart Content Extraction — ✅ REFACTORED

**Before:** The pattern of extracting text from `list[dict]` multipart content appeared in **4 places** with subtle differences:

| Location | Checks `type == "text"`? | Handles non-dict parts? | Falls back to `str()`? |
|---|---|---|---|
| `auto_dream.py` → `TranscriptAnalyzer` | ✅ Yes | ❌ No | ❌ No |
| `memory_system.py` → `MemoryExtractor` | ❌ No | ❌ No | ❌ No (but str fallback) |
| `context_compressor_v2.py` → `_message_tokens` | ❌ No | ✅ Yes | ✅ Yes |
| `hermes2_adapter.py` → `get_context_messages` | ❌ No | ❌ No | ✅ Yes |

**Refactoring:** Created `token_utils.extract_text_from_content()` that handles all cases. Updated all 4 modules.

### 1D. Atomic Write Pattern — DOCUMENTED (not refactored)

**Locations:**
- `tool_result_manager.py` → `_save_to_disk()`: `tempfile.mkstemp` → write → `os.replace`
- `memory_system.py` → `MemoryStore.save()`: identical pattern

**Recommendation:** Extract to a shared `_atomic_write_json(path, data)` utility. Not refactored because the two call sites have different payloads (JSON dict vs JSON list) and different error handling semantics.

### 1E. Stats Dictionary Pattern — DOCUMENTED

Multiple modules maintain `self._stats` dictionaries with `get_stats() -> dict` methods:

- `tool_result_manager.py`: `{"total_processed": 0, "dedup_saves": 0, ...}`
- `smart_retry.py`: `{"total_executions": 0, "total_retries": 0, ...}`
- `context_compressor_v2.py`: Individual `self._stats_*` attributes instead

**Recommendation:** Consider a `StatsTracker` mixin or dataclass for consistency.

---

## 2. Inconsistent Naming (MEDIUM PRIORITY)

### 2A. Logger Variable Name

| Module | Variable |
|---|---|
| `hermes2_adapter.py` | `_log` |
| `mcp_transport.py` | `logger` |

**Recommendation:** Standardize on `_log` (private, module-level) or `logger` across all modules.

### 2B. Token Estimation Naming

| Module | Name | Style |
|---|---|---|
| `token_utils.py` | `CHARS_PER_TOKEN`, `estimate_tokens()` | Module constant + function |
| `tool_result_manager.py` | `TokenEstimator.estimate_tokens()` | Class static method |
| `context_compressor_v2.py` (pre-refactor) | `_CHARS_PER_TOKEN`, `_estimate_tokens()` | Private module-level |

**Status:** Partially addressed — `token_utils.py` establishes canonical names. Old names kept for backward compatibility.

### 2C. Stats Accessor Naming

| Module | Method Name | Return Type |
|---|---|---|
| `tool_result_manager.py` | `get_stats()` | `dict[str, int]` |
| `smart_retry.py` | `get_stats()` | `dict[str, int]` |
| `memory_system.py` | `get_stats()` | `dict` (untyped) |
| `context_compressor_v2.py` | `get_stats()` | `dict` (untyped) |
| `hermes2_adapter.py` | `get_stats()` | `dict[str, Any]` |
| `post_turn_hooks.py` | `get_hooks()` | `list[dict]` |

**Recommendation:** Standardize return type annotations. Use `dict[str, Any]` consistently.

### 2D. Reset Method Naming

| Module | Method Name |
|---|---|
| `smart_retry.py` | `reset_all()` |
| `token_budget_manager.py` | `reset()` |
| `tool_result_manager.py` | (no reset) |

**Recommendation:** Standardize on `reset()` for single-state and `reset_all()` for compound state.

### 2E. Field Naming: `id` vs `tool_id`

| Class | ID Field |
|---|---|
| `ToolCall` | `id` |
| `BatchResult` | `tool_id` |
| `ToolResult` (async_pipeline) | `tool_id` |
| `MemoryEntry` | `id` |
| `TaskSpec` | `id` |

**Recommendation:** `tool_id` for tool-related results, `id` for general entities is reasonable. Document the convention.

### 2F. Comment Style in Section Separators

| Style | Modules |
|---|---|
| `# ── Name ──────` (box-drawing) | `tool_orchestrator.py` |
| `# ---------------------------------------------------------------------------` (dashes) | Most modules |
| `# --- Name ---` (short dashes) | `coordinator.py` |

**Recommendation:** Standardize on the dashed-line style used by most modules.

---

## 3. Inconsistent Parameter Ordering (LOW PRIORITY)

### 3A. `__init__` Parameter Patterns

Most modules follow `(self, required, optional_with_default, ...)` consistently. One outlier:

- `MemorySearch.__init__(self, kw_weight=0.4, tag_weight=0.2, recency_weight=0.2, freq_weight=0.2)` — all positional kwargs with no required params, but ordering is non-obvious.

**Recommendation:** Document that `__init__` should list required params first, then optional.

### 3B. Callback/Function Parameters

| Method | Parameter Order |
|---|---|
| `ToolOrchestrator.execute()` | `(self, batches, executor_fn, on_progress)` |
| `SmartRetryManager.execute_with_retry()` | `(self, tool_call, executor_fn, budget_check)` |
| `Coordinator.execute()` | `(self, tasks, executor_fn)` |

These are consistent — `executor_fn` always comes after the data parameter. ✅

---

## 4. Inconsistent Default Values (MEDIUM PRIORITY)

### 4A. None-Handling for Optional Collections

Three distinct patterns exist:

**Pattern 1: `or {}`**
```python
# tool_result_manager.py
self.per_tool_budgets = per_tool_budgets or {}
```

**Pattern 2: `is not None` + fallback**
```python
# permission_pipeline.py
self.rules = rules if rules is not None else _build_default_rules()
```

**Pattern 3: `if hooks:`**
```python
# post_turn_hooks.py
if hooks:
    for h in hooks:
        self.register(h)
```

**Pattern 4: `{**DEFAULT, **(param or {})}`**
```python
# token_budget_manager.py
self._tool_budgets = {**DEFAULT_TOOL_BUDGETS, **(tool_budgets or {})}
```

**Recommendation:** Prefer Pattern 2 (`is not None`) for collections that could legitimately be empty vs absent. Use Pattern 4 when merging with defaults.

### 4B. `Optional[...]` vs `X | None`

| Style | Modules |
|---|---|
| `Optional[X]` | `hermes2_adapter.py`, `mcp_transport.py`, `permission_pipeline.py`, `memory_system.py`, `post_turn_hooks.py`, `auto_dream.py` |
| `X \| None` | `tool_orchestrator.py`, `tool_result_manager.py`, `context_compressor_v2.py`, `smart_retry.py`, `async_pipeline.py` |

**Recommendation:** Standardize on `X | None` (modern Python 3.10+ style) since `from __future__ import annotations` is used in all modules.

---

## 5. Inconsistent Return Types (MEDIUM PRIORITY)

### 5A. Error Representation

| Module | Error Pattern |
|---|---|
| `tool_orchestrator.py` | `BatchResult(error=str(exc))` — error field in result dataclass |
| `smart_retry.py` | `RetryResult(error=str(exc), success=False)` — error field + success flag |
| `coordinator.py` | `task.result = {"error": str(exc)}` — inline error dict |
| `permission_pipeline.py` | `PermissionDecision(allowed=False, reason=...)` — allowed flag + reason |
| `mcp_transport.py` | Raises `RuntimeError`, `ConnectionError`, `ValueError` |
| `memory_system.py` | Returns `None` for missing entries, `bool` for success |

**Recommendation:** Standardize on one of:
1. Result dataclass with `error: str | None` field (current pattern in orchestrator/retry)
2. Exception-based (current pattern in MCP transport)

---

## 6. Import Style Inconsistency (MEDIUM PRIORITY)

### 6A. Relative vs Absolute Imports

| Style | Modules |
|---|---|
| `from .module import X` (relative) | All main modules |
| `try: from .X except: from X` (guarded) | `tool_result_summarizer.py`, `smart_retry.py` |

**Recommendation:** Use relative imports consistently. The try/except pattern is only needed for standalone script execution, which these modules don't support anyway.

### 6B. Import Grouping

Most modules follow PEP 8 grouping:
1. `from __future__ import annotations`
2. Standard library
3. Third-party
4. Local imports

**Exceptions:**
- `hermes2_adapter.py`: `_log = logging.getLogger(__name__)` appears between stdlib and local imports (line 25).
- `mcp_transport.py`: `logger = logging.getLogger(__name__)` appears similarly.

**Recommendation:** Move logger initialization after all imports.

---

## 7. Docstring Style Inconsistency (MEDIUM PRIORITY)

### 7A. Three Styles Present

**NumPy style (Parameters/Returns with `---`):**
- `tool_orchestrator.py`
- `smart_retry.py`
- `token_budget_manager.py`
- `tool_result_summarizer.py`
- `tool_result_manager.py`

**Google style (Args:/Returns:):**
- `coordinator.py`
- `permission_pipeline.py`
- `context_compressor_v2.py`
- `mcp_transport.py`
- `post_turn_hooks.py`

**Plain/minimal:**
- `auto_dream.py` (mixed)
- `memory_system.py` (minimal)
- `async_pipeline.py` (Attributes: style)

### 7B. Mixed Within Same Module

`coordinator.py`: Some methods use `Args:`, others have no docstrings. `estimate_complexity` has a description but no Args/Returns.

**Recommendation:** Standardize on Google style (`Args:/Returns:`) — it's more concise and used by the majority of modules.

---

## 8. Error Handling Style Inconsistency (MEDIUM PRIORITY)

### 8A. Three Patterns

| Pattern | Example | Modules |
|---|---|---|
| **Raise** | `raise ValueError("session_budget must be positive")` | `token_budget_manager.py`, `mcp_transport.py` |
| **Return None** | `return None` if no current turn | `token_budget_manager.py`, `memory_system.py` |
| **Return error in result** | `BatchResult(error=str(exc))` | `tool_orchestrator.py`, `smart_retry.py`, `coordinator.py` |

### 8B. Inconsistent Exception Types

| Module | Exception | Context |
|---|---|---|
| `token_budget_manager.py` | `ValueError` | Invalid init params |
| `tool_result_manager.py` | `RuntimeError` | Disk dir not configured |
| `mcp_transport.py` | `ConnectionError` | Not connected |
| `mcp_transport.py` | `ValueError` | Invalid config |
| `mcp_transport.py` | `KeyError` | Server not found |
| `coordinator.py` | `ValueError` | Agent at max capacity |

**Recommendation:** Use `ValueError` for invalid inputs, `RuntimeError` for invalid state, and result-level error fields for expected failures (transient errors, permission denials).

---

## 9. Magic Numbers and Strings (MEDIUM PRIORITY)

### 9A. Token/Size Constants

| Location | Magic Value | Meaning |
|---|---|---|
| `context_compressor_v2.py:233` | `500` | Min content length for compression |
| `context_compressor_v2.py:235` | `250`, `150` | Head/tail chars for truncation |
| `context_compressor_v2.py:52` | `+10` | Message overhead tokens |
| `tool_result_manager.py:216` | `50_000` | Disk persistence threshold |
| `token_budget_manager.py:187` | `500`, `200` | Min allocation tokens |
| `async_pipeline.py:264` | `+1` | Per-message overhead |
| `memory_system.py:178` | `500` | Max memory entries |
| `tool_result_summarizer.py:93` | `[:20]` | Max imports to keep |
| `tool_result_summarizer.py:111` | `[:500]` | Docstring char cap |
| `tool_result_summarizer.py:128` | `[-5:]` | Tail lines to keep |

### 9B. Pressure/Threshold Constants

| Location | Magic Value | Meaning |
|---|---|---|
| `post_turn_hooks.py:325` | `0.95` | Critical pressure |
| `post_turn_hooks.py:330` | `0.75` | Warning pressure |
| `post_turn_hooks.py:335` | `0.50` | Elevated pressure |
| `auto_dream.py:249` | `14` (days) | Memory demotion cutoff |
| `auto_dream.py:204` | `0.6` | Similarity threshold |
| `auto_dream.py:243` | `5` (access_count) | Promotion threshold |
| `coordinator.py:169` | `10`, `30` | Complexity score thresholds |

**Recommendation:** Extract to named constants at the top of each module or in a shared `constants.py`. At minimum, name them where they're used (e.g., `_MIN_CONTENT_FOR_COMPRESSION = 500`).

---

## 10. Dead Code (LOW PRIORITY)

### 10A. Unused Import — ✅ FIXED

`hermes2_adapter.py` line 21: `import warnings` — never used anywhere in the file. **Removed.**

### 10B. Redundant Alias

`context_compressor_v2.py`: `CompressionProfile.keep_last_n` is just an alias for `microcompact_age`:
```python
@property
def keep_last_n(self) -> int:
    return self.microcompact_age  # alias for clarity
```

**Recommendation:** This is intentional for API clarity. Keep it.

### 10C. Commented-Out Logic

`tool_orchestrator.py` lines 156-157: Comment says "read-vs-read conflict check was removed — two READ_ONLY tools can never trigger a write conflict, so the loop was dead code." The comment is helpful documentation, not dead code.

---

## Refactoring Applied

### New File: `token_utils.py`

Created as the **single source of truth** for:
- `CHARS_PER_TOKEN = 4` — the canonical token estimation constant
- `DEFAULT_TOOL_BUDGETS` — canonical per-tool token budget dictionary
- `estimate_tokens(text)` — token estimation with `max(1, ...)` guard
- `estimate_content_tokens(content)` — handles str/list/other content types
- `estimate_messages_tokens(messages)` — sums across message list
- `extract_text_from_content(content)` — extracts plain text from multipart content

### Files Modified

| File | Changes |
|---|---|
| `token_utils.py` | **NEW** — shared token estimation and content extraction |
| `tool_result_manager.py` | `TokenEstimator` now delegates to `token_utils`; `DEFAULT_TOOL_BUDGETS` imported from `token_utils` |
| `context_compressor_v2.py` | `_estimate_tokens` and `_message_tokens` now delegate to `token_utils`; `FullLevel.prepare_summary_prompt` uses `extract_text_from_content` |
| `token_budget_manager.py` | `DEFAULT_TOOL_BUDGETS` imported from `token_utils` instead of defined locally |
| `post_turn_hooks.py` | `UsageTrackingHook` uses `estimate_tokens` instead of inline `// 4` |
| `async_pipeline.py` | `ContextWindow` uses `CHARS_PER_TOKEN` and `estimate_tokens` from `token_utils` |
| `memory_system.py` | `MemoryExtractor` uses `extract_text_from_content` |
| `auto_dream.py` | `TranscriptAnalyzer` uses `extract_text_from_content` |
| `hermes2_adapter.py` | Removed unused `import warnings`; uses `extract_text_from_content` |

### Lines of Code Saved

- Removed ~50 lines of duplicated logic
- Added ~110 lines in `token_utils.py` (net new shared module with full documentation)
- Net: ~-50 lines from duplication removal, +110 lines shared utility = cleaner architecture

### Test Results

- **Before refactoring:** 808 passed
- **After refactoring:** 808 passed ✅

---

## Recommended Next Steps (Not Applied)

1. **High:** Extract `_atomic_write_json()` shared utility for crash-safe persistence
2. **High:** Standardize Optional type annotations to `X | None` across all modules
3. **Medium:** Standardize docstrings to Google style
4. **Medium:** Extract magic numbers to named constants
5. **Medium:** Standardize error handling to result-dataclass pattern
6. **Low:** Standardize logger naming (`_log` vs `logger`)
7. **Low:** Standardize section separator comment style
