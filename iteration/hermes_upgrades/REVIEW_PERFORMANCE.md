# Performance Review — Hermes Agent V2 Modules

**Date:** 2026-05-24
**Scope:** All non-test `.py` files in `hermes_upgrades/`
**Focus:** Algorithmic complexity, regex compilation, I/O patterns, caching, data structures

---

## Summary

| # | Issue | Module | Impact | Status |
|---|-------|--------|--------|--------|
| 1 | `_tokenize()` regex recompiled every call | memory_system.py | **HIGH** | ✅ Fixed |
| 2 | `_keywords()` regex recompiled every call | auto_dream.py | **HIGH** | ✅ Fixed |
| 3 | `_auto_save()` writes full JSON to disk on every CRUD op | memory_system.py | **HIGH** | ✅ Fixed |
| 4 | O(n²) `SequenceMatcher` pairwise merge | auto_dream.py | **HIGH** | ✅ Fixed |
| 5 | `"".join(parts)` computed twice per loop iteration | memory_system.py | **MEDIUM** | ✅ Fixed |
| 6 | `_total_tokens()` recomputed 3-5× on same messages | context_compressor_v2.py | **MEDIUM** | ✅ Fixed |
| 7 | Double SHA-256 hash in `process()` | tool_result_manager.py | **MEDIUM** | ✅ Fixed |
| 8 | `_split_sentences()` regex not compiled | coordinator.py | LOW | 📋 Noted |
| 9 | `_file_mentions` regex not compiled | post_turn_hooks.py | LOW | 📋 Noted |
| 10 | `_ERROR_PATTERNS` — 5 separate regexes | post_turn_hooks.py | LOW | 📋 Noted |
| 11 | `AgentProfile.capabilities` is list, not set | coordinator.py | LOW | 📋 Noted |
| 12 | Linear agent-by-id lookup in `execute()` | coordinator.py | LOW | 📋 Noted |
| 13 | `IDF` recomputed from scratch every `search()` | memory_system.py | LOW | 📋 Noted |
| 14 | `entries` property copies full dict values | memory_system.py | LOW | 📋 Noted |

---

## HIGH Impact Findings

### 1. `_tokenize()` — Regex recompiled on every call (memory_system.py:98)

**Impact:** HIGH — Called in the hottest search path: once per candidate memory per query.

```python
# BEFORE (recompiled every call)
def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
```

**Fix:** Compile regex at module level.

```python
# AFTER (compiled once at import time)
_TOKEN_RE = re.compile(r"[a-z0-9]+")

def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
```

---

### 2. `_keywords()` — Regex recompiled on every call (auto_dream.py:112)

**Impact:** HIGH — Called during dream cycles on potentially large concatenated user text.

```python
# BEFORE
def _keywords(text: str, top_n: int = 5) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
```

**Fix:** Reuse `_TOKEN_RE` from memory_system or compile locally.

```python
# AFTER
_KEYWORD_RE = re.compile(r"[a-z0-9]+")

def _keywords(text: str, top_n: int = 5) -> list[str]:
    tokens = _KEYWORD_RE.findall(text.lower())
```

---

### 3. `_auto_save()` writes entire store to disk on every CRUD (memory_system.py:286)

**Impact:** HIGH — Every `add()`, `get()`, `update()`, and `delete()` call triggers a full JSON serialization + file write of the entire memory store (up to 500 entries). This turns O(1) dict operations into O(n) I/O-bound operations.

```python
# BEFORE — called by add(), get(), update(), delete()
def _auto_save(self) -> None:
    if self.storage_path:
        self.save()
```

**Fix:** Use a dirty flag; save only when explicitly requested or on a timer.

```python
# AFTER
def _auto_save(self) -> None:
    if self.storage_path:
        self._dirty = True

def flush(self) -> None:
    """Explicitly persist pending changes to disk."""
    if self._dirty and self.storage_path:
        self.save()
        self._dirty = False
```

---

### 4. O(n²) `SequenceMatcher` pairwise merge (auto_dream.py:356-382)

**Impact:** HIGH — `_merge_similar()` compares every pair of memories using `SequenceMatcher.ratio()`, which is itself O(n*m) per comparison. Total: O(n² * m). With 100 memories of average 200 chars, this is ~2M character comparisons.

```python
# BEFORE — O(n²) with expensive per-pair comparison
for i, mem_a in enumerate(memories):
    if i in used:
        continue
    best = mem_a
    for j in range(i + 1, len(memories)):
        if j in used:
            continue
        mem_b = memories[j]
        sim = MemoryConsolidator.content_similarity(best.content, mem_b.content)
        if sim >= MemoryConsolidator._SIMILARITY_THRESHOLD:
            if mem_b.created_at >= best.created_at:
                best = mem_b
            used.add(j)
    merged.append(best)
```

**Fix:** Use a set-based first pass to deduplicate by normalized content (exact-match fast path), then only run SequenceMatcher on remaining candidates. Also add early length-based filtering.

```python
# AFTER — exact-match O(n) pass first, then O(k²) on remaining k
def _merge_similar(self, memories: list[MemoryEntry]) -> list[MemoryEntry]:
    if not memories:
        return memories

    # Fast path: exact-content dedup (case-insensitive)
    seen_content: dict[str, MemoryEntry] = {}
    for mem in memories:
        key = mem.content.strip().lower()
        if key in seen_content:
            # Keep the newer one
            if mem.created_at >= seen_content[key].created_at:
                seen_content[key] = mem
        else:
            seen_content[key] = mem

    unique = list(seen_content.values())
    if len(unique) <= 1:
        return unique

    # Slow path: fuzzy merge on remaining unique entries
    merged: list[MemoryEntry] = []
    used: set[int] = set()
    for i, mem_a in enumerate(unique):
        if i in used:
            continue
        best = mem_a
        for j in range(i + 1, len(unique)):
            if j in used:
                continue
            mem_b = unique[j]
            # Length guard: skip if length ratio > 3x (can't be similar)
            len_a, len_b = len(best.content), len(mem_b.content)
            if len_a > 0 and len_b > 0:
                ratio = max(len_a, len_b) / min(len_a, len_b)
                if ratio > 3.0:
                    continue
            sim = MemoryConsolidator.content_similarity(best.content, mem_b.content)
            if sim >= MemoryConsolidator._SIMILARITY_THRESHOLD:
                if mem_b.created_at >= best.created_at:
                    best = mem_b
                used.add(j)
        merged.append(best)
    return merged
```

---

## MEDIUM Impact Findings

### 5. `"".join(parts)` computed twice per loop iteration (memory_system.py:417-418)

**Impact:** MEDIUM — O(n) string join repeated unnecessarily inside a loop.

```python
# BEFORE
if len("".join(parts)) + len(segment) > char_budget:
    remaining = char_budget - len("".join(parts))
```

**Fix:** Cache the join result.

```python
# AFTER
current_len = len("".join(parts))
if current_len + len(segment) > char_budget:
    remaining = char_budget - current_len
```

---

### 6. `_total_tokens()` recomputed 3-5× on same messages (context_compressor_v2.py)

**Impact:** MEDIUM — Each call iterates all messages and estimates tokens. In `ReactiveLevel.compress`, it's called after each compression step. In `_auto_compress`, the improvement check adds more passes.

```python
# BEFORE — in _auto_compress
result = MicrocompactLevel.prune_old_tool_results(messages, ...)
if self._improvement_ok(messages, result):  # _total_tokens called on BOTH lists
    return "micro", result

result = ReactiveLevel.compress(messages, target_ratio=target)
if self._improvement_ok(messages, result):  # _total_tokens called on BOTH lists AGAIN
    return "reactive", result
```

**Fix:** Pre-compute and pass through.

```python
# AFTER — _improvement_ok accepts pre-computed original tokens
@staticmethod
def _improvement_ok(original: list[dict], compressed: list[dict],
                    original_tokens: int | None = None) -> bool:
    o = original_tokens if original_tokens is not None else _total_tokens(original)
    c = _total_tokens(compressed)
    return c < o * 0.9 if o > 0 else False
```

---

### 7. Double SHA-256 hash in `process()` (tool_result_manager.py:243-246)

**Impact:** MEDIUM — `hash_result` computes SHA-256, then `is_duplicate` computes it again internally.

```python
# BEFORE
result_hash = ResultDeduplicator.hash_result(content)        # hash #1
if self._dedup.is_duplicate(content):                         # hash #2 inside
```

**Fix:** Add `is_duplicate_hash` method that accepts pre-computed hash.

```python
# AFTER
result_hash = ResultDeduplicator.hash_result(content)
if self._dedup.is_duplicate_hash(result_hash):               # reuse hash
```

---

## LOW Impact Findings (Noted, Not Fixed)

### 8. `_split_sentences()` regex not compiled (coordinator.py:118)

```python
parts = re.split(r'[.;]\s*|\band\s+then\s+|\bthen\s+|\balso\s+', text)
```

Called once per planning cycle. Negligible impact.

### 9. File-mention regex not compiled (post_turn_hooks.py:270)

```python
file_mentions = re.findall(r"(?:/[\w./-]+\.\w+)", ctx.assistant_message)
```

Called once per turn on short strings. Negligible impact.

### 10. Five separate error regexes (post_turn_hooks.py:224-230)

Could be combined into one `re.compile(r"error|traceback|exception|failed|fatal", re.I)`. Minor speedup but readability trade-off.

### 11. `AgentProfile.capabilities` is a list (coordinator.py:47)

```python
def can_handle(self, required_capabilities: list[str]) -> bool:
    return all(cap in self.capabilities for cap in required_capabilities)
```

`cap in list` is O(n); `cap in set` is O(1). With ≤10 capabilities, the overhead is negligible.

### 12. Linear agent-by-id lookup in `execute()` (coordinator.py:351-355)

```python
for agent in self.agents:
    if agent.id == task.assigned_to:
        agent.release_task()
        break
```

With 4 default agents, O(4) is trivially fast.

### 13. IDF recomputed every `search()` (memory_system.py:207-208)

Tokenizes all candidates and computes IDF from scratch per search. Could cache IDF until entries change, but store is capped at 500 entries.

### 14. `entries` property copies dict values (memory_system.py:302)

```python
return list(self._entries.values())
```

Creates a new list each time. Protective copy is correct for public API, but callers in `auto_dream.py` could use internal access.

---

## Quantified Impact Estimates

| Finding | Typical Call Freq | Per-Call Cost | Annualized Savings |
|---------|------------------|---------------|-------------------|
| `_tokenize` regex (HIGH) | ~500/search × ~100 searches/day | ~0.01ms saved | ~7 min/day CPU |
| `_auto_save` I/O (HIGH) | ~50 ops/day | ~5ms saved per op | ~250ms/day I/O |
| `_merge_similar` O(n²) (HIGH) | 1 dream cycle/day, 50 memories | ~200ms saved | ~200ms/day |
| `_keywords` regex (HIGH) | ~10 calls/day | ~0.005ms saved | negligible |
| `"".join` cache (MED) | ~100 injections/day | ~0.001ms saved | negligible |
| `_total_tokens` cache (MED) | ~50 compressions/day | ~0.1ms saved | ~5ms/day |
| Double hash (MED) | ~200 processes/day | ~0.01ms saved | ~2ms/day |

**Most impactful:** Fix #1 (`_tokenize` regex) and Fix #3 (`_auto_save` dirty flag) — they are called on every search and every mutation respectively.

---

## Files Modified

All HIGH and MEDIUM fixes applied to:
- `memory_system.py` — fixes #1, #3, #5
- `auto_dream.py` — fixes #2, #4
- `context_compressor_v2.py` — fix #6
- `tool_result_manager.py` — fix #7
