# Algorithmic Correctness Review — hermes_upgrades

**Reviewer**: Automated Algorithm Audit
**Scope**: All `.py` source files in `/root/claude-code-study/iteration/hermes_upgrades/`
**Date**: 2026-05-24

---

## 1. Token Estimation Accuracy (4 chars/token)

### Files Involved
- `token_utils.py` — canonical implementation (CHARS_PER_TOKEN = 4)
- `context_compressor_v2.py` — local copy + adds `+10` per-message overhead
- `tool_result_manager.py` — local copy
- `post_turn_hooks.py` — inline `// 4`
- `async_pipeline.py` — local constant `_CHARS_PER_TOKEN = 4`, adds `+1` per message

### Mathematical Analysis

The 4-chars-per-token heuristic is calibrated for **English prose** with GPT-family tokenizers:

| Text Type | Actual chars/token | Estimator Error |
|-----------|-------------------|-----------------|
| English prose | ~4.0 | ~0% (baseline) |
| English code | ~3.2 | +25% overestimate |
| Chinese text | ~1.5 chars/token | **−62% underestimate** |
| Japanese text | ~1.7 chars/token | **−57% underestimate** |
| JSON/structured | ~3.0 | +33% overestimate |

For Chinese text `"你好世界欢迎使用"` (8 chars), the estimator gives `8 // 4 = 2` tokens, but the actual count is ~6-8 tokens. The estimator is off by **3-4×**.

### Inconsistency Bug

Five different implementations exist despite `token_utils.py` being the "single source of truth":

1. `token_utils.py`: `max(1, len(text) // 4)` — no per-message overhead
2. `context_compressor_v2.py`: `max(1, len(text) // 4) + 10` — adds 10 tokens/message for role/metadata
3. `async_pipeline.py ContextWindow`: `len(text) // 4 + 1` — adds 1 token/message
4. `post_turn_hooks.py`: `len(text) // 4` — no floor, no overhead
5. `tool_result_manager.py`: `max(1, len(text) // 4)` — matches canonical

**Severity**: Medium. The inconsistency means the context compressor thinks messages are ~10 tokens heavier than what the budget manager estimates, causing premature compression triggers.

### Recommendation
- Use `token_utils.py` everywhere (already created for this purpose)
- Document the ±25% accuracy band
- Consider bumping CHARS_PER_TOKEN to 3.5 for better CJK coverage at slight English overestimate

---

## 2. TF-IDF Implementation Correctness

### File: `memory_system.py`

### Analysis

**Term Frequency (TF)** — `_tf()` at line 116:
```python
def _tf(tokens: list[str]) -> Counter:
    return Counter(tokens)
```
Returns **raw term counts**, not normalized by document length. This is the root issue.

In `MemorySearch.score()` at line 148:
```python
for qt in q_tokens:
    tf_val = e_tf.get(qt, 0)    # raw count
    idf_val = idf.get(qt, 1.0)
    kw_score += tf_val * idf_val
if q_tokens:
    kw_score /= len(q_tokens)   # normalized by QUERY length only
```

**Bug**: `kw_score` is normalized by query length but **not** by document length. A 10,000-word memory entry with the word "python" appearing 50 times will score 50× higher than a 20-word entry with "python" appearing once — even though the shorter entry is arguably more relevant.

**Mathematical proof**: Let entry A be 10 words containing term T once, and entry B be 1000 words containing T 10 times. TF-IDF scores: A = 1 × idf(T), B = 10 × idf(T). B scores 10× higher despite T being 10% of A but only 1% of B.

**Inverse Document Frequency (IDF)** — `_idf()` at line 128:
```python
return {t: math.log((n + 1) / (count + 1)) + 1 for t, count in df.items()}
```

This uses **smoothed IDF with +1 floor**: `log((N+1)/(df+1)) + 1`.

Standard IDF: `log(N/df)` — terms in all docs get IDF = 0
This IDF: terms in all docs get `log(1) + 1 = 1.0`

The +1 floor means **no term is ever penalized** for being common. This dilutes the discrimination power of IDF. A term appearing in every document has the same weight (1.0) as a hypothetical term with standard IDF of 1.0.

**Severity**: Medium. The un-normalized TF biases toward longer entries. The floored IDF reduces discrimination.

### Fix

```python
def _tf(tokens: list[str]) -> Counter:
    """Normalized term frequency (count / total)."""
    total = len(tokens)
    if total == 0:
        return Counter()
    counts = Counter(tokens)
    return {t: c / total for t, c in counts.items()}

def _idf(doc_tokens: list[list[str]]) -> dict[str, float]:
    """Standard IDF: log(N / df)."""
    n = len(doc_tokens)
    df: Counter = Counter()
    for tokens in doc_tokens:
        for t in set(tokens):
            df[t] += 1
    return {t: math.log(n / count) if count > 0 else 0.0 for t, count in df.items()}
```

---

## 3. Content Similarity Algorithm Choice

### File: `auto_dream.py`, line 273-275

```python
@classmethod
def content_similarity(cls, a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
```

### Analysis

`SequenceMatcher` uses the **Ratcliff/Obershelp** algorithm: O(n*m) time, O(n*m) space where n, m are string lengths.

For memory deduplication in `_merge_similar()`:
- **Fast path** (exact dedup): O(n) — ✅ efficient
- **Slow path** (fuzzy): O(k² × m²) where k = unique entries, m = average content length
- **Length guard**: Skips if lengths differ by >3× — good pruning

With typical memory entries (100-500 chars) and ~50 entries, worst case is ~50² × 500² ≈ 625M operations. The length guard reduces this significantly in practice.

**Verdict**: Acceptable for the expected data sizes. `SequenceMatcher` is a reasonable choice for near-duplicate detection. For semantic similarity, TF-IDF cosine or embedding-based similarity would be better but would require more infrastructure.

**Minor issue**: The `_SIMILARITY_THRESHOLD = 0.6` is applied asymmetrically — when two memories match, the **newer** one is kept, but both `i` and `j` iterations use the potentially-replaced `best` for further comparisons. This is correct (greedy merge).

---

## 4. Circuit Breaker Timing Math

### File: `smart_retry.py`, lines 208-276

### Analysis

**State Machine Transitions**:

```
CLOSED ──(failures >= threshold)──► OPEN
OPEN ──(elapsed >= recovery_timeout)──► HALF_OPEN
HALF_OPEN ──(success)──► CLOSED
HALF_OPEN ──(failure)──► ??? (BUG: stays HALF_OPEN)
```

**Bug #1: HALF_OPEN allows unlimited concurrent probes**

```python
# HALF_OPEN — allow one test request
return True  # line 269
```

The comment says "one test request" but the code allows **all** concurrent callers through. If 10 threads call `allow_request()` while in HALF_OPEN, all 10 proceed. There's no probe counter or lock-based single-admission.

**Bug #2: Failed probe doesn't reopen circuit**

In `record_failure()`:
```python
self.consecutive_failures += 1  # now 1 (was 0 after HALF_OPEN entry)
if self.consecutive_failures >= self.failure_threshold:  # 1 >= 5? NO
    self.state = CircuitState.OPEN
```

After a HALF_OPEN probe fails, `consecutive_failures` becomes 1, which is less than `failure_threshold` (5). The circuit stays HALF_OPEN, allowing more probes through (per Bug #1). The circuit should immediately return to OPEN on a failed probe.

**Bug #3: Time reference mismatch**

`CircuitBreaker` uses `time.monotonic()` for timestamps, but `SmartRetryManager` injects `time.time()` via `self._time_fn`. These are different clocks. The circuit breaker's `allow_request()` checks `time.monotonic() - self.last_failure_time`, while the retry manager records `self._time_fn()` (defaulting to `time.time()`). The `last_failure_time` is set by `record_failure()` using `time.monotonic()`, so this is actually consistent within the circuit breaker. But the retry manager's own `_time_fn` is different. Not a bug in practice, but the injectable `time_fn` in SmartRetryManager doesn't flow to the CircuitBreaker.

### Fix for Bug #2

```python
def record_failure(self) -> None:
    with self._lock:
        self.consecutive_failures += 1
        self.last_failure_time = time.monotonic()
        if self.state == CircuitState.HALF_OPEN:
            # Failed probe — reopen immediately
            self.state = CircuitState.OPEN
        elif self.consecutive_failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

### Fix for Bug #1

```python
def allow_request(self) -> bool:
    with self._lock:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._probe_in_progress = True
                return True
            return False
        # HALF_OPEN — only allow one probe
        if self._probe_in_progress:
            return False
        self._probe_in_progress = True
        return True
```

**Severity**: High. These bugs can cause cascading failures in production.

---

## 5. Exponential Backoff Jitter Fairness

### File: `smart_retry.py`, lines 523-530

```python
def _calculate_delay(self, policy: RetryPolicy, attempt: int) -> float:
    delay = policy.base_delay * (policy.backoff_factor ** attempt)
    delay = min(delay, policy.max_delay)
    jitter_range = delay * policy.jitter
    delay += random.uniform(-jitter_range, jitter_range)
    return max(0.05, delay)
```

### Analysis

This implements **symmetric (additive) jitter**: `delay ± (delay × jitter)`.

With default jitter = 0.25:
- Attempt 0: delay = 1.0s, range = [0.75, 1.25]
- Attempt 1: delay = 2.0s, range = [1.50, 2.50]
- Attempt 2: delay = 4.0s, range = [3.00, 5.00]

**Separation analysis**: Ranges don't overlap (max of attempt N < min of attempt N+1 when factor >= 2 and jitter <= 0.5). ✅ Good separation between attempts.

**Thundering herd**: If 100 clients fail simultaneously, they all calculate the same base delay. With symmetric jitter, they cluster around the base ±25%. The standard deviation is `delay × jitter / √3 ≈ delay × 0.144`. This provides some spread but less than "full jitter" (`uniform(0, delay)`) which gives `delay / √3 ≈ delay × 0.577`.

**AWS recommendation**: Full jitter (`random.uniform(0, delay)`) provides the best thundering-herd avoidance. The current symmetric jitter is ~4× less effective at spreading retries.

**Verdict**: Functionally correct. The jitter prevents perfect synchronization but is suboptimal for thundering-herd scenarios. Not a bug, but a design improvement opportunity.

### Recommended Fix (Full Jitter)

```python
def _calculate_delay(self, policy: RetryPolicy, attempt: int) -> float:
    delay = policy.base_delay * (policy.backoff_factor ** attempt)
    delay = min(delay, policy.max_delay)
    # Full jitter: uniform [0, delay] — better thundering-herd avoidance
    delay = random.uniform(0, delay)
    return max(0.05, delay)
```

**Severity**: Low. The current implementation works; full jitter would be better.

---

## 6. LRU Eviction Correctness

### File: `tool_result_manager.py`, `ResultDeduplicator` class

```python
class ResultDeduplicator:
    def __init__(self, max_seen: int = 1000) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()

    def is_duplicate_hash(self, h: str) -> bool:
        with self._lock:
            if h in self._seen:
                self._seen.move_to_end(h)  # promote to MRU
                return True
            return False

    def register(self, content: str) -> None:
        h = self.hash_result(content)
        with self._lock:
            if h in self._seen:
                self._seen.move_to_end(h)
                return
            self._seen[h] = None
            if len(self._seen) > self.max_seen:
                self._seen.popitem(last=False)  # evict LRU
```

### Analysis

✅ **Correct LRU implementation** using Python's `OrderedDict`:
- `move_to_end(h)` on access promotes to most-recently-used
- `popitem(last=False)` evicts the least-recently-used (front of dict)
- Thread-safe via `self._lock`

**One issue**: `is_duplicate_hash()` promotes on read (line 89), making it an LRU. But `register()` also promotes on write (line 98). This means checking for duplicates AND registering both count as "access" for LRU purposes. This is correct behavior — you want recently-seen hashes to stay in the cache.

### File: `memory_system.py`, `MemoryStore._evict()`

```python
def _evict(self) -> None:
    worst = min(
        self._entries.values(),
        key=lambda e: (e.relevance_score, e.created_at),
    )
    del self._entries[worst.id]
```

This is **NOT LRU** — it evicts by lowest relevance + oldest creation time. This is a design choice, not a bug. However, it does not consider `access_count` or `accessed_at`, meaning a frequently-accessed but low-relevance entry could be evicted over a never-accessed higher-relevance entry.

**Verdict**: Both implementations are correct for their stated purposes.

---

## 7. Back-Pressure Hysteresis Stability

### File: `async_pipeline.py`, `BackPressureController` class

```python
class BackPressureController:
    def __init__(self, high_water: float = 0.8, low_water: float = 0.6) -> None:
        if not 0.0 <= low_water <= high_water <= 1.0:
            raise ValueError("Require 0 <= low_water <= high_water <= 1")
        self._high_water = high_water
        self._low_water = low_water
        self._paused: bool = False

    def update(self, current_tokens: int, max_tokens: int) -> None:
        if max_tokens <= 0:
            self._pressure = 1.0
        else:
            self._pressure = min(1.0, current_tokens / max_tokens)
        if self._pressure >= self._high_water:
            self._paused = True
        elif self._pressure <= self._low_water:
            self._paused = False
```

### Analysis

**Hysteresis gap**: high_water - low_water = 0.8 - 0.6 = 0.2 (20%)

**Stability proof**: Consider pressure oscillating near threshold. Without hysteresis:
- pressure = 0.79 → resume
- pressure = 0.81 → pause
- This causes rapid toggling (oscillation)

With hysteresis:
- pressure = 0.79 → still paused (below high_water but above low_water)
- pressure = 0.81 → paused
- pressure = 0.59 → resume
- No oscillation possible in the dead zone [0.6, 0.8] ✅

**Invariant**: Once paused, the system stays paused until pressure drops at least 0.2 below the pause threshold. This guarantees at least 0.2 × max_tokens worth of "drain" before resuming.

**Edge case**: `max_tokens = 0` → pressure = 1.0 → paused forever. This is correct (can't produce into a zero-size buffer).

**Missing feature**: No rate-limiting or gradual slowdown. It's binary: full speed or paused. A smoother approach would use proportional throttling in the dead zone. But for the current use case, binary is fine.

**`should_resume()` is redundant**: It's just `not self._paused`, which is always the complement of `should_pause()`. The API could be simplified, but it's not a correctness issue.

**Verdict**: ✅ Correct and stable hysteresis implementation. The 20% gap prevents oscillation. No bugs found.

---

## 8. Task Scheduling Optimality

### File: `coordinator.py`, `TaskScheduler.schedule()`

### Analysis

**Algorithm**: Repeated iteration with topological ordering.

```python
progress = True
while progress:
    progress = False
    for task in sorted_tasks:
        if task.status != TaskStatus.PENDING:
            continue
        deps_met = all(dep_id in assigned_ids for dep_id in task.dependencies)
        if not deps_met:
            continue
        # assign task
        progress = True
```

**Complexity**: O(n²) in the worst case (each pass assigns one task). A standard Kahn's algorithm achieves O(n + e).

**Bug #1: Linear dependency chain defeats parallelism**

`TaskDecomposer.decompose()` creates **sequential dependencies**:
```python
if tasks:
    task.dependencies = [tasks[-1].id]  # each depends on the previous
```

This means for N tasks, only 1 can run at a time. With M agents available, M-1 sit idle. The multi-agent architecture provides zero benefit.

**Bug #2: Only WORKER agents are assignable**

```python
candidates = [
    a for a in self.agents
    if a.role == AgentRole.WORKER  # <-- excludes ORCHESTRATOR and REVIEWER
    and a.can_handle(task.required_capabilities)
    and a.has_capacity()
]
```

Tasks requiring "review" capability are never assigned because the reviewer has `role = REVIEWER`, not `WORKER`. Tasks requiring "design" capability are never assigned because no default WORKER has "design".

**Bug #3: Sequential execution despite parallel assignment**

`Coordinator.execute()` runs tasks in list order:
```python
for task in tasks:
    if task.status != TaskStatus.ASSIGNED:
        continue
    task.result = executor_fn(task)  # blocking sequential
```

Even if tasks assigned to different agents have no interdependencies, they execute sequentially.

**Bug #4: All-or-nothing capability matching**

`can_handle()` requires ALL capabilities to be present on a single agent:
```python
def can_handle(self, required_capabilities: list[str]) -> bool:
    return all(cap in self.capabilities for cap in required_capabilities)
```

If a task needs ["code", "test"] and the coder has ["code"] and the tester has ["test"], neither can handle it alone.

### Recommendation

1. Remove the linear dependency chain in decomposer (use semantic analysis for real dependencies)
2. Include ORCHESTRATOR and REVIEWER in candidate selection for relevant capability matches
3. Implement parallel execution for independent tasks using asyncio or threads
4. Consider splitting tasks that require capabilities spanning multiple agents

**Severity**: Medium-high. The scheduling works correctly but the decomposer's linear dependencies and role restrictions make multi-agent coordination ineffective.

---

## Summary of Findings

| # | Algorithm | Severity | Status |
|---|-----------|----------|--------|
| 1 | Token estimation (4 chars/token) | Medium | ⚠️ Inconsistent across 5 implementations |
| 2 | TF-IDF correctness | Medium | ❌ TF not normalized by doc length; IDF overly smoothed |
| 3 | Content similarity | Low | ✅ Acceptable for data sizes |
| 4 | Circuit breaker timing | **High** | ❌ HALF_OPEN allows unlimited probes; failed probe doesn't reopen |
| 5 | Backoff jitter | Low | ⚠️ Symmetric jitter; full jitter recommended |
| 6 | LRU eviction | — | ✅ Correct |
| 7 | Back-pressure hysteresis | — | ✅ Correct and stable |
| 8 | Task scheduling | Medium | ⚠️ O(n²); linear deps defeat parallelism |

### Critical Fixes Required

1. **Circuit breaker HALF_OPEN** (Bug #4): Add probe counter; reopen on failed probe
2. **TF-IDF normalization** (Bug #2): Normalize TF by document length
3. **Token estimation consolidation** (Bug #1): All modules should import from `token_utils.py`

### Fixes Applied

See the `tests/test_algorithms.py` file for regression tests covering all findings.
