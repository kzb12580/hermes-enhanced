# Data Integrity Review — hermes_upgrades

**Reviewer:** Data Integrity Agent
**Date:** 2026-05-24
**Files Reviewed:** All 12 `.py` source files + 14 test files

---

## Summary

| Severity | Count | Fixed |
|----------|-------|-------|
| CRITICAL | 1     | ✅    |
| HIGH     | 2     | ✅    |
| MEDIUM   | 3     | —     |
| LOW      | 3     | —     |

---

## CRITICAL — 1 bug

### C1: Non-atomic file write in MemoryStore.save() causes data loss on crash

**File:** `memory_system.py`, line 290
**Code:**
```python
def save(self) -> None:
    if not self.storage_path:
        return
    self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    data = [e.to_dict() for e in self._entries.values()]
    self.storage_path.write_text(json.dumps(data, indent=2))
```

**Bug:** `write_text()` performs a direct write. If the process is killed or disk fills mid-write, the JSON file is left partially written (corrupted). On next `load()`, `json.loads()` raises `JSONDecodeError`, losing **all** persisted memories.

**Impact:** Total memory loss across sessions. Affects all users who configure `storage_path`.

**Failing Test Scenario:**
```python
def test_save_crash_corrupts_file():
    store = MemoryStore(storage_path="/tmp/mem.json")
    store.add(MemoryEntry(type=MemoryType.MEMORY, content="important"))
    store.save()
    # Simulate crash mid-write
    with open("/tmp/mem.json", "w") as f:
        f.write("{truncated")  # partial write
    store2 = MemoryStore(storage_path="/tmp/mem.json")
    # Raises json.JSONDecodeError — all memories lost
```

**Fix:** Write to a temp file in the same directory, then `os.replace()` atomically.
**Status:** ✅ FIXED

---

## HIGH — 2 bugs

### H1: process_turn() discards compression result — compression_applied=True but messages unchanged

**File:** `hermes2_adapter.py`, lines 216-219
**Code:**
```python
should, reason = self.compressor.should_compress(messages)
compression_applied = False
if should:
    self.compressor.compress(messages, level="auto")  # ← return value discarded!
    compression_applied = True
```

**Bug:** `compress()` returns a `CompressedMessages` object with the compressed message list, but the return value is thrown away. The caller's `messages` list is never replaced with compressed content. The function reports `compression_applied=True` while the actual messages remain at full size.

**Impact:** Context window pressure is never actually reduced. Over long sessions, the context will grow until hitting the model's hard limit, causing API errors.

**Failing Test Scenario:**
```python
def test_compression_actually_reduces_messages():
    engine = Hermes2Engine()
    large = "x" * 4_000_000
    messages = [_user_msg(large)]
    result = engine.process_turn(messages, [], [])
    assert result["compression_applied"] is True
    # But messages still have the full content — compression was a no-op
```

**Fix:** Return the compressed messages from `process_turn()` so callers can use them.
**Status:** ✅ FIXED

### H2: Non-atomic file write in ToolResultManager._save_to_disk()

**File:** `tool_result_manager.py`, line 354
**Code:**
```python
out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
```

**Bug:** Same non-atomic write issue as C1. Partial writes leave corrupted JSON files. Lower impact since these are cache files (can be regenerated from re-executing tools), but still causes errors on read.

**Fix:** Atomic write via temp file + `os.replace()`.
**Status:** ✅ FIXED

---

## MEDIUM — 3 bugs

### M1: MicrocompactLevel.prune_old_tool_results() shares non-pruned messages by reference

**File:** `context_compressor_v2.py`, lines 170-178
**Code:**
```python
for i, msg in enumerate(messages):
    if i in prune_set:
        pruned = dict(msg)  # ← copied
        pruned["content"] = "[tool result pruned — context compression]"
        result.append(pruned)
    else:
        result.append(msg)  # ← shared reference!
```

**Bug:** Pruned messages get a fresh `dict(msg)` copy, but non-pruned messages are appended by reference. If any downstream code mutates a message dict in the result (e.g., adding metadata), it also mutates the original conversation. The docstring says "New list; original is not mutated" which is only partially true.

**Impact:** Subtle data corruption if downstream code modifies the returned messages. Currently not actively triggered but is a latent time bomb.

**Fix:** Copy all messages: `result.append(dict(msg))` for non-pruned too.

### M2: HookContext stores external lists by reference

**File:** `hermes2_adapter.py`, lines 204-209
**Code:**
```python
ctx = HookContext(
    messages=messages,       # ← shared reference
    tool_calls=tool_calls,   # ← shared reference
    tool_results=tool_results,  # ← shared reference
    turn_number=self._turn_count,
)
```

**Bug:** `HookContext` is a dataclass — it stores the passed-in lists by reference, not by copy. If any hook mutates these lists (append, pop, clear), the caller's data is silently corrupted. The hooks currently only read these lists, making this a latent bug.

**Impact:** Any hook that inadvertently mutates its context will corrupt the caller's data with no error.

**Fix:** `messages=list(messages)`, `tool_calls=list(tool_calls)`, etc.

### M3: MemoryStore.search() and get() return internal objects by reference

**File:** `memory_system.py`, lines 193-200, 215-220
**Code:**
```python
def get(self, id: str) -> Optional[MemoryEntry]:
    entry = self._entries.get(id)
    if entry:
        entry.access_count += 1  # ← mutates internal state
        ...
    return entry  # ← returns internal object
```

**Bug:** Callers get the actual `MemoryEntry` from the store's internal dict. Mutating the returned entry (e.g., `entry.tags.append("new")`) directly modifies the store's data without triggering persistence or validation.

**Impact:** External code can accidentally corrupt the memory store's internal state.

**Fix:** Return `copy.deepcopy(entry)` or use immutable entry pattern.

---

## LOW — 3 bugs

### L1: TranscriptAnalyzer doesn't handle naive datetimes

**File:** `auto_dream.py`, lines 177-185
**Code:**
```python
ts = msg.get("timestamp")
if isinstance(ts, datetime):
    timestamps.append(ts)  # ← could be naive
```

**Bug:** If `ts` is a timezone-naive datetime, it's appended directly. Later, `max(timestamps) - min(timestamps)` will raise `TypeError: can't subtract offset-naive and offset-aware datetimes` if mixed with UTC-aware timestamps. Only triggers with malformed message data.

### L2: StdioTransport encode/decode uses implicit encoding

**File:** `mcp_transport.py`, lines 199, 212
**Code:**
```python
self._process.stdin.write(data.encode())       # implicit UTF-8
return json.loads(line.decode())                 # implicit UTF-8
```

**Bug:** `.encode()` and `.decode()` default to UTF-8 which is correct, but explicit encoding is better practice and documents intent. Non-ASCII tool names or arguments could silently break if the default encoding were ever changed.

### L3: Float precision drift in relevance_score

**File:** `auto_dream.py`, lines 237, 245
**Code:**
```python
mem.relevance_score = min(mem.relevance_score + 0.3, 2.0)
mem.relevance_score = max(mem.relevance_score - 0.2, 0.1)
```

**Bug:** Repeated `+0.3` and `-0.2` operations on floats accumulate rounding error (e.g., `0.1 + 0.2 != 0.3`). Over hundreds of dream cycles, scores could drift slightly. Not practically significant with the current `min()/max()` guards.

---

## Positive Patterns (no bugs)

1. **No mutable default arguments** — All dataclass fields with mutable types use `field(default_factory=...)` correctly.
2. **UUID4 for IDs** — All auto-generated IDs use `uuid.uuid4()`, collision probability is negligible.
3. **Consistent timezone usage** — Almost all `datetime.now()` calls use `timezone.utc`.
4. **Thread safety in orchestrator** — Proper use of `threading.Lock` and `ThreadPoolExecutor`.
5. **Input sanitization** — `ToolResultManager._sanitize_name()` and `StdioTransport._validate_command()` prevent injection.
6. **Permission pipeline** — Well-designed with first-match-wins and hook support.
