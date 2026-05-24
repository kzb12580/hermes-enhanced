# P1 Module Code Review

Reviewed: 2026-05-24
Modules: permission_pipeline.py, mcp_transport.py, memory_system.py
Tests: 134/134 passing

---

## permission_pipeline.py

### SHOULD_FIX — Dangerous pattern detection gaps

The `_DANGEROUS_PATTERNS` regex for `rm` only matches `-rf` in that exact flag order. The following dangerous commands are **not detected**:

- `rm -fr /home` (flag order reversal)
- `rm -r --force /` (long-form flag)
- `/bin/rm -rf /` (absolute path prefix — this one IS matched by `\brm\b`... wait, `rm` pattern doesn't use word boundary, it uses `rm\s+` so `/bin/rm -rf /` IS matched)

The `dd if=` pattern also matches benign usage like `dd if=/dev/zero of=~/testfile count=1` — this may be overly aggressive but errs on the safe side.

**Verdict:** Acceptable for v1, but consider adding `rm\s+-[a-zA-Z]*[rR][a-zA-Z]*f|rm\s+-[a-zA-Z]*f[a-zA-Z]*r` to catch flag order variants.

### NICE_TO_HAVE — context parameter unused

`check()` accepts an optional `context` parameter but it's never passed to rules, hooks, or conditions. It's documented as "optional context dict (e.g. user info, session state)" but has no effect. Either wire it through or remove the parameter to avoid confusion.

### NICE_TO_HAVE — Condition semantics are implicit

A PROMPT-level rule with a `condition` that returns True gets escalated to DENY. But this is undocumented in the class docstring. A condition on an AUTO rule that returns True would also result in DENY — this could surprise users. Consider documenting that conditions act as "block if True" overrides.

---

## mcp_transport.py

### MUST_FIX (patched) — `StdioTransport._reader_loop` doesn't catch `asyncio.TimeoutError`

`_read_message()` uses `asyncio.wait_for()` with the config timeout. If the MCP subprocess doesn't respond in time, `asyncio.TimeoutError` is raised. The `_reader_loop` only catches `(ConnectionError, asyncio.CancelledError)`, so the `TimeoutError` propagates as an unhandled exception in the background task. This silently kills the reader loop and leaves pending futures unresolved (they hang until their own timeout, then raise `TimeoutError` to the caller).

**Fix applied:** Added `asyncio.TimeoutError` to the except clause.

### SHOULD_FIX — `McpManager.connect_all` kwargs conflict with mixed transports

`connect_all()` passes `**self._transport_kwargs` to `create_transport()`, which forwards them to the transport constructor. `StdioTransport.__init__` only accepts `(config)`, while `HttpTransport.__init__` accepts `(config, http_client=None)`. If a manager has both STDIO and HTTP configs and receives `http_client=...`, the STDIO transport creation will raise `TypeError`.

**Workaround:** In practice, callers would only pass `http_client` when all servers are HTTP-based. But the API doesn't enforce or document this constraint.

**Recommended fix:** Either:
1. Filter kwargs per-transport-type, or
2. Accept a factory/callback instead of raw kwargs, or
3. Make all transports accept `**kwargs` and ignore unknown args.

### SHOULD_FIX — `get_all_tools` uses `isinstance` + private attribute

```python
def get_all_tools(self) -> list[McpToolSchema]:
    for transport in self._transports.values():
        if isinstance(transport, (StdioTransport, HttpTransport)):
            tools.extend(transport._tools)
```

This breaks Open/Closed Principle — adding a new transport type requires updating this method. Should use the public `list_tools()` async method, or cache tools on a base-class attribute.

### NICE_TO_HAVE — `asyncio.ensure_future` is deprecated

`asyncio.ensure_future()` is deprecated since Python 3.10 in favor of `asyncio.create_task()`.

### NICE_TO_HAVE — WebSocket transport is a stub

`TransportType.WEBSOCKET` maps to `HttpTransport` as a placeholder. The docstring says "same interface" but HTTP and WebSocket protocols are fundamentally different. Consider raising `NotImplementedError` in the factory instead of silently using the wrong transport.

### NICE_TO_HAVE — `StdioTransport._read_message` JSON parse errors

If the subprocess writes malformed JSON to stdout, `json.loads()` raises `json.JSONDecodeError` which is not caught in `_reader_loop`. This kills the reader. Consider catching and logging parse errors.

### NICE_TO_HAVE — `_notify` silently swallows missing client

`HttpTransport._notify` returns silently if `_http_client is None`. This could mask bugs where notifications fail to send after disconnection. Should log a warning or raise.

---

## memory_system.py

### SHOULD_FIX — `_auto_save` writes entire store on every mutation

`add()`, `get()`, `update()`, `delete()`, and `prune()` all call `_auto_save()`, which serializes and writes the full JSON file. At scale (500 entries), this is O(n) I/O on every operation. `get()` is particularly concerning since reads trigger writes.

**Recommendation:** Either debounce saves (dirty flag + periodic flush) or only save on explicit `save()` calls.

### SHOULD_FIX — `search()` with empty query tokens returns noisy results

A query composed entirely of stop words (e.g., "the", "is") produces empty tokens after `_tokenize()`. The keyword score becomes 0, and results are ranked purely by recency + frequency — not meaningful relevance.

**Fix:** Short-circuit `search()` when `q_tokens` is empty and return `[]`.

### NICE_TO_HAVE — Token estimate is rough

The comment "1 token ≈ 4 characters" is a rough English approximation. For code-heavy content (variable names, paths), this can underestimate significantly. Consider using a configurable tokenizer or at least documenting the limitation.

### NICE_TO_HAVE — No duplicate detection in extraction

`MemoryExtractor.extract_from_conversation` doesn't deduplicate. If the same message appears twice, two identical memories are created. Consider adding a content hash check.

### NICE_TO_HAVE — `MemoryEntry.type` shadows builtin

The field name `type` shadows Python's `type()` builtin. Works fine for the class itself but can be confusing in debugging contexts. Consider `memory_type` as the field name.

### NICE_TO_HAVE — No test for concurrent access

`MemoryStore` is not thread-safe. No locking on `_entries`. Fine for single-threaded use but should be documented.

---

## Test Coverage Gaps

### permission_pipeline.py tests
- **Good:** 60 tests, excellent coverage of rules, hooks, serialization, edge cases, dangerous patterns.
- **Gap:** No test for pre-hook raising an exception.
- **Gap:** No test for condition that raises an exception.

### mcp_transport.py tests
- **Good:** 35 tests, good coverage of config, transports, manager lifecycle.
- **Gap:** No test for `StdioTransport` connect/disconnect (only tested via integration, skipped since it requires a real subprocess).
- **Gap:** No test for `_reader_loop` timeout behavior (now fixed, but still untested).
- **Gap:** No test for `McpManager` with mixed STDIO+HTTP configs (would expose the kwargs bug).
- **Gap:** No test for `from_dict` with invalid/missing fields.

### memory_system.py tests
- **Good:** 39 tests, good coverage of CRUD, search, extraction, injection, persistence, pruning.
- **Gap:** No test for empty query token handling.
- **Gap:** No test for `MemoryStore` with malformed JSON file.
- **Gap:** No test for extraction with missing `content` or `role` keys.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| MUST_FIX | 1 | `StdioTransport._reader_loop` TimeoutError crash (patched) |
| SHOULD_FIX | 4 | Dangerous pattern gaps, connect_all kwargs, get_all_tools OCP, auto_save performance |
| NICE_TO_HAVE | 10 | Minor issues, API polish, test gaps |

**Overall quality:** Well-structured, clean code with good test coverage (134 tests). The permission pipeline is the most mature module. The MCP transport has the most issues (expected — it's the most complex). The memory system is solid but has a performance concern with auto-save.
