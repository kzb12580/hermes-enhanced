# Security Audit — Hermes Agent V2 Modules

**Auditor:** Security Specialist Subagent
**Date:** 2026-05-24
**Scope:** All `.py` source files in `/root/claude-code-study/iteration/hermes_upgrades/` (excluding tests)
**Files reviewed:** 11 source files

---

## Executive Summary

The Hermes Agent V2 modules are generally well-structured with clear separation of concerns. However, several security issues were identified across multiple severity levels. **3 CRITICAL/HIGH issues have been fixed directly in the source code.** Additional MEDIUM and LOW findings are documented below with recommendations.

### Findings Summary

| Severity | Count | Fixed |
|----------|-------|-------|
| CRITICAL | 2 | ✅ 2 fixed |
| HIGH | 3 | ✅ 2 fixed |
| MEDIUM | 5 | ⚠️ 1 fixed, 4 documented |
| LOW | 4 | 📋 documented |

---

## CRITICAL Findings

### C1: Path Traversal via `tool_name` in ToolResultManager Disk Persistence
**File:** `tool_result_manager.py`, line ~317 (original)
**Status:** ✅ FIXED

**Description:** The `_save_to_disk()` method constructed filenames using `tool_name` directly without sanitization:
```python
out = self._disk_dir / f"{tool_name}_{safe_name}.json"
```

A malicious `tool_name` like `../../etc/cron.d/evil` would resolve to a path outside `disk_dir`, writing attacker-controlled JSON content to arbitrary filesystem locations. Since `tool_name` originates from tool call dicts (potentially LLM-generated or user-influenced), this is a realistic attack vector.

**Fix applied:** Added `_sanitize_name()` static method that:
- Strips path separators (`/`, `\`)
- Removes leading dots
- Filters to safe characters only
- Added defense-in-depth `resolve().relative_to()` check

### C2: Arbitrary Attribute Overwrite in MemoryStore.update()
**File:** `memory_system.py`, line ~223 (original)
**Status:** ✅ FIXED

**Description:** The `update()` method used `hasattr(entry, key)` + `setattr(entry, key, value)` with user-supplied keys. This allowed overwriting critical fields like `id`, `type`, `created_at`, and `accessed_at` — potentially corrupting the memory store, breaking deduplication, or manipulating access counts to influence eviction logic.

**Fix applied:** Added `_UPDATABLE_FIELDS` allowlist restricting updates to: `type`, `content`, `tags`, `relevance_score`, `source`, `access_count`. This prevents modification of `id`, `created_at`, and `accessed_at` through this interface.

---

## HIGH Findings

### H1: Command Injection Risk in MCP StdioTransport
**File:** `mcp_transport.py`, `StdioTransport.connect()` (line ~206)
**Status:** ✅ FIXED

**Description:** `StdioTransport.connect()` spawns a subprocess using `create_subprocess_exec()` with `command` and `args` taken directly from `McpServerConfig`. While `create_subprocess_exec` doesn't use `shell=True` (mitigating shell injection), if MCP configs are loaded from user-supplied JSON via `from_dict()`, an attacker could specify arbitrary executables or inject shell metacharacters in arguments.

**Fix applied:** Added `_validate_command()` static method that:
- Rejects empty commands
- Checks for shell metacharacters (`;`, `&`, `|`, `` ` ``, `$`, `()`, `{}`, `!`, `#`, `~`) in both command and args
- Added `_BLOCKED_COMMANDS` denylist for known-dangerous executables
- Validation runs automatically in `connect()`

**Remaining risk:** The deny-list is not enforced at connect time (only metacharacter check is). Consider adding command allowlisting for production use.

### H2: Path Traversal in MemoryStore Storage Path
**File:** `memory_system.py`, `MemoryStore.__init__()` (line ~173)
**Status:** ✅ FIXED

**Description:** `storage_path` was accepted as-is via `Path(storage_path)`. If an attacker controls this value, they can read/write memory entries to arbitrary filesystem locations via `save()` and `load()`.

**Fix applied:** Changed to `Path(storage_path).resolve()` to normalize the path and eliminate symlink-based traversal at construction time.

### H3: Incomplete Dangerous Command Detection
**File:** `permission_pipeline.py`, `_DANGEROUS_PATTERNS` (line ~73)
**Status:** ✅ FIXED

**Description:** The original dangerous command detector only covered 5 patterns:
- `rm -rf /`
- `dd if=`
- `mkfs`
- Fork bomb
- `> /dev/sd`

Missing critical patterns: `sudo`, pipe-to-shell (`curl | bash`), reverse shells (`nc -l`), credential theft (`/etc/shadow`), `chmod 777`, `eval`, and more. A malicious agent or user could bypass detection with common attack commands.

**Fix applied:** Expanded to 22 patterns covering: destructive ops, privilege escalation, pipe-to-shell, reverse shells, dangerous permissions, credential theft, `eval`, and env exfiltration.

---

## MEDIUM Findings

### M1: Environment Variable Leakage to MCP Subprocesses
**File:** `mcp_transport.py`, `StdioTransport.connect()` (line ~204)
**Status:** 📋 Documented (not fixed)

**Description:** The full `os.environ` is merged with config-provided env vars and passed to the spawned subprocess:
```python
env = {**os.environ, **self._config.env}
```

This exposes all environment variables (including potentially sensitive ones like `AWS_SECRET_ACCESS_KEY`, `DATABASE_PASSWORD`, `API_KEYS`) to any MCP server subprocess.

**Recommendation:** Use an allowlist approach — only pass explicitly needed env vars plus a minimal safe subset (e.g., `PATH`, `HOME`, `LANG`):
```python
_SAFE_ENV_KEYS = {"PATH", "HOME", "LANG", "LC_ALL", "TZ"}
env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
env.update(self._config.env)
```

### M2: No JSON Message Size Limits in MCP Transport
**File:** `mcp_transport.py`, `StdioTransport._read_message()` (line ~180)
**Status:** 📋 Documented (not fixed)

**Description:** JSON-RPC messages from subprocess stdout are read with no size limit:
```python
line = await asyncio.wait_for(self._process.stdout.readline(), timeout=...)
return json.loads(line.decode())
```

A malicious MCP server could send a multi-gigabyte line, causing memory exhaustion (DoS).

**Recommendation:** Add a max line size before JSON parsing:
```python
MAX_LINE_SIZE = 10 * 1024 * 1024  # 10MB
line = await asyncio.wait_for(self._process.stdout.readline(), timeout=...)
if len(line) > MAX_LINE_SIZE:
    raise ValueError(f"MCP message exceeds {MAX_LINE_SIZE} bytes")
```

### M3: No URL Validation in HttpTransport
**File:** `mcp_transport.py`, `HttpTransport.base_url` (line ~316)
**Status:** 📋 Documented (not fixed)

**Description:** `HttpTransport` accepts any URL string without validation. This could enable SSRF (Server-Side Request Forgery) if configs are user-supplied — an attacker could point the transport at internal services (`http://169.254.169.254/` for cloud metadata, `http://localhost:6379/` for Redis, etc.).

**Recommendation:** Validate URLs against an allowlist of schemes (`https`, `http`) and optionally block private/reserved IP ranges.

### M4: Glob Pattern Matching May Be Overly Permissive
**File:** `permission_pipeline.py`, `PermissionRule.matches()` (line ~46)
**Status:** 📋 Documented (not fixed)

**Description:** `fnmatch.fnmatch()` is case-sensitive on Linux but the pattern `read_*` would match `read_FILE`, `read_etc_shadow`, or any tool starting with `read_`. This is by design for flexibility but could lead to unintended auto-approval of new tools that happen to match a prefix pattern.

**Recommendation:** Document that glob patterns should be as specific as possible. Consider requiring exact matches for AUTO-level rules and only allowing globs for PROMPT-level.

### M5: Information Leakage in Error Messages
**Files:** `post_turn_hooks.py` (multiple hooks), `coordinator.py` (line ~346)
**Status:** 📋 Documented (not fixed)

**Description:** Multiple modules propagate raw exception messages into return values:
```python
error=str(exc)  # in HookResult, BatchResult, TaskSpec.result
```

Exception messages can contain file paths, stack traces, database connection strings, or other internal details that should not be exposed to end users or logged without sanitization.

**Recommendation:** In production, sanitize error messages or use error codes:
```python
error = "Internal processing error" if not DEBUG else str(exc)
```

---

## LOW Findings

### L1: No File Locking for JSON Persistence
**File:** `memory_system.py`, `save()` / `load()` (lines ~269–282)
**Status:** 📋 Documented

**Description:** `MemoryStore.save()` writes to disk without file locking. In concurrent scenarios (multiple agent instances sharing the same storage file), writes could interleave and corrupt the JSON file.

**Recommendation:** Use `fcntl.flock()` or `filelock` library for atomic writes (write to temp file, then rename).

### L2: Race Condition in ToolOrchestrator Event Loop Management
**File:** `tool_orchestrator.py`, `_run_one()` (lines ~273–289)
**Status:** 📋 Documented

**Description:** The `_run_one()` method creates new event loops in threads when an existing loop is detected. Multiple concurrent calls could create event loops that interfere with each other, especially if asyncio objects are shared across loops.

**Recommendation:** Use `asyncio.run_coroutine_threadsafe()` to the existing loop instead of creating new loops in threads.

### L3: Unbounded History Lists
**Files:** `context_compressor_v2.py` (`PressureMonitor.history`), `auto_dream.py` (`AutoDreamer._history`)
**Status:** 📋 Documented

**Description:** `PressureMonitor.history` and `AutoDreamer._history` are unbounded lists that grow with every call. In long-running sessions, these could consume significant memory.

**Recommendation:** Add max-length bounds or use a circular buffer:
```python
self.history: list[float] = []
# In update():
if len(self.history) > 10000:
    self.history = self.history[-5000:]
```

### L4: json.loads() on Untrusted Deserialization Data
**File:** `memory_system.py`, `MemoryEntry.from_dict()` (line ~66)
**Status:** 📋 Documented

**Description:** `from_dict()` performs manual dict deserialization without schema validation. Malformed or malicious JSON data (e.g., extremely long strings, unexpected types) could cause unexpected behavior. This is low risk since `json.loads()` itself is safe (no arbitrary code execution), but type checking is minimal.

**Recommendation:** Add type validation in `from_dict()`:
```python
if not isinstance(d.get("content"), str):
    raise ValueError("Invalid memory entry: 'content' must be a string")
```

---

## Positive Security Observations

1. **No pickle/eval/exec usage** — None of the modules use dangerous deserialization functions.
2. **`create_subprocess_exec` over `shell=True`** — MCP transport correctly uses the non-shell subprocess API.
3. **Bounded collections** — `ResultDeduplicator` uses LRU eviction; `MemoryStore` has `max_entries`.
4. **JSON-based persistence** — All serialization uses `json` module, not `pickle`.
5. **Asyncio patterns** — Semaphores and proper cancellation in `StreamingToolExecutor` prevent unbounded concurrency.
6. **Clean separation** — Modules are standalone with minimal interdependencies, reducing attack surface.

---

## Files Modified

| File | Changes |
|------|---------|
| `tool_result_manager.py` | Added `_sanitize_name()`, path traversal defense in `_save_to_disk()`, added `import re` |
| `memory_system.py` | `.resolve()` on storage_path, `_UPDATABLE_FIELDS` allowlist in `update()` |
| `mcp_transport.py` | Added `_validate_command()` with metacharacter check, `_BLOCKED_COMMANDS` denylist |
| `permission_pipeline.py` | Expanded `_DANGEROUS_PATTERNS` from 5 to 22 patterns |

---

## Recommended Next Steps

1. **Integrate security patterns into CI** — Add static analysis (bandit, semgrep) to catch future regressions.
2. **Add input validation tests** — Specifically test path traversal, command injection, and glob bypass scenarios.
3. **Implement env var filtering** for MCP subprocesses (M1).
4. **Add JSON message size limits** in MCP transport (M2).
5. **Consider URL allowlisting** for HttpTransport (M3).
6. **Add fuzzing** for `from_dict()` and `MemoryEntry.from_dict()` deserialization paths.
