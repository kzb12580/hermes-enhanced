"""Integration tests for Hermes Agent V2 modules.

Tests realistic scenarios combining multiple modules:
- Orchestrator + Result Manager pipeline
- Permission Pipeline + Orchestrator
- Memory + Compression
- Stress tests (50 reads)
- Edge cases (empty results, permission denied mid-batch)
"""

from __future__ import annotations

import sys
import os

# Ensure the parent module directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from tool_orchestrator import (
    ConcurrencyClass,
    ToolCall,
    ToolOrchestrator,
    partition,
)
from tool_result_manager import (
    ProcessedResult,
    ResultDeduplicator,
    ToolResultManager,
)
from permission_pipeline import (
    PermissionLevel,
    PermissionPipeline,
    PermissionRule,
)
from memory_system import (
    MemoryEntry,
    MemoryExtractor,
    MemoryInjector,
    MemoryStore,
    MemoryType,
)
from context_compressor_v2 import (
    CompressionProfile,
    ContextCompressorV2,
    MicrocompactLevel,
    _total_tokens,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_executor(tool_name_to_result: dict[str, str] | None = None,
                        default_result: str = "ok"):
    """Create a sync executor that returns canned results per tool name."""
    mapping = tool_name_to_result or {}

    def executor(tc: ToolCall) -> str:
        return mapping.get(tc.name, default_result)

    return executor


def _make_messages_with_tools(n: int, tool_every: int = 3,
                              content_size: int = 200) -> list[dict]:
    """Generate conversation messages with tool results every *tool_every*."""
    msgs: list[dict] = [{"role": "system", "content": "You are helpful."}]
    for i in range(1, n):
        if tool_every and i % tool_every == 0:
            msgs.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": f"tc_{i}", "function": {"name": "read_file"}}],
            })
            msgs.append({
                "role": "tool",
                "tool_call_id": f"tc_{i}",
                "name": "read_file",
                "content": f"file contents {'x' * content_size} line {i}",
            })
        else:
            role = "user" if i % 2 else "assistant"
            msgs.append({"role": role, "content": f"Message {i}: {'y' * content_size}"})
    return msgs


# ---------------------------------------------------------------------------
# 1. Pipeline Test: Orchestrator + Result Manager
# ---------------------------------------------------------------------------

class TestPipelineOrchestratorResultManager:
    """10 mixed tool calls partitioned, executed, then processed through
    dedup + truncation.  Duplicate results are deduped."""

    def test_10_mixed_calls_partitioned_and_executed(self):
        """Orchestrator partitions 10 mixed calls; all results collected."""
        orch = ToolOrchestrator(max_workers=4)
        rm = ToolResultManager()

        calls: list[ToolCall] = []
        for i in range(5):
            calls.append(ToolCall(name="read_file", args={"path": f"/file_{i}.py"},
                                  id=f"read_{i}"))
        for i in range(5):
            calls.append(ToolCall(name="write_file", args={"path": f"/out_{i}.py"},
                                  id=f"write_{i}"))

        batches = orch.partition(calls)

        # Reads should be in one batch (they are READ_ONLY)
        read_batch = batches[0]
        assert len(read_batch) == 5
        assert all(tc.name == "read_file" for tc in read_batch)

        # Writes each in their own batch (WRITE_SERIAL)
        write_batches = batches[1:]
        assert len(write_batches) == 5
        for wb in write_batches:
            assert len(wb) == 1
            assert wb[0].name == "write_file"

        executor = _make_mock_executor(
            tool_name_to_result={
                "read_file": "file content here",
                "write_file": "write success",
            }
        )
        results = orch.execute(batches, executor)

        assert len(results) == 10
        for tc in calls:
            assert tc.id in results
            assert results[tc.id].error is None

    def test_results_go_through_dedup_and_truncation(self):
        """Results are deduped and truncated by ToolResultManager."""
        rm = ToolResultManager()

        # Small result — no truncation
        r1 = rm.process("read_file", "small content")
        assert r1.was_truncated is False
        assert r1.was_deduped is False
        assert r1.content == "small content"

        # Same content again — deduped
        r2 = rm.process("read_file", "small content")
        assert r2.was_deduped is True
        assert r2.content == r1.content

        # Large result — truncated
        big = "x" * 100_000
        r3 = rm.process("read_file", big)
        assert r3.was_truncated is True
        assert "[...truncated" in r3.content

    def test_duplicate_result_submitted_twice_second_deduped(self):
        """Same result submitted twice → second call returns deduped=True."""
        rm = ToolResultManager()

        content = "identical output from tool"
        r1 = rm.process("terminal", content)
        r2 = rm.process("terminal", content)

        assert r1.was_deduped is False
        assert r2.was_deduped is True
        assert r1.hash == r2.hash
        assert rm.get_stats()["dedup_saves"] == 1

    def test_full_pipeline_10_calls_dedup_and_truncation(self):
        """Full pipeline: 10 calls executed, results processed through
        Result Manager with dedup detection."""
        orch = ToolOrchestrator(max_workers=4)
        rm = ToolResultManager()

        calls: list[ToolCall] = []
        for i in range(5):
            calls.append(ToolCall(name="read_file", args={"path": f"/f{i}"},
                                  id=f"r{i}"))
        for i in range(5):
            calls.append(ToolCall(name="write_file", args={"path": f"/w{i}"},
                                  id=f"w{i}"))

        batches = orch.partition(calls)

        # All reads return same content, all writes return same content
        executor = _make_mock_executor({
            "read_file": "read output",
            "write_file": "write output",
        })
        results = orch.execute(batches, executor)

        processed = []
        for tc in calls:
            br = results[tc.id]
            assert br.error is None
            pr = rm.process(tc.name, br.result)
            processed.append(pr)

        # First of each type is fresh, rest are deduped
        read_processed = processed[:5]
        write_processed = processed[5:]

        assert read_processed[0].was_deduped is False
        assert all(p.was_deduped for p in read_processed[1:])
        assert write_processed[0].was_deduped is False
        assert all(p.was_deduped for p in write_processed[1:])

        stats = rm.get_stats()
        assert stats["dedup_saves"] == 8  # 4 read dups + 4 write dups
        assert stats["total_processed"] == 10


# ---------------------------------------------------------------------------
# 2. Permission Pipeline + Orchestrator
# ---------------------------------------------------------------------------

class TestPermissionAndOrchestrator:
    """Permission pipeline checks tools before orchestrator runs.
    Dangerous commands get DENIED; read_file is auto-approved."""

    def test_dangerous_rm_rf_denied(self):
        """'rm -rf /' is denied by the permission pipeline."""
        pp = PermissionPipeline()
        decision = pp.check("terminal", {"command": "rm -rf /"})
        assert decision.allowed is False
        assert decision.level == PermissionLevel.DENY

    def test_read_file_auto_approved(self):
        """read_file is auto-approved without prompt."""
        pp = PermissionPipeline()
        decision = pp.check("read_file", {"path": "/etc/hosts"})
        assert decision.allowed is True
        assert decision.level == PermissionLevel.AUTO
        assert decision.needs_prompt is False

    def test_permission_gates_then_orchestrator_batches(self):
        """Check permissions for 10 calls, filter to allowed ones,
        then orchestrator batches them."""
        pp = PermissionPipeline()
        orch = ToolOrchestrator(max_workers=4)

        raw_calls = [
            ToolCall(name="read_file", args={"path": "/etc/hosts"}, id="r1"),
            ToolCall(name="read_file", args={"path": "/etc/passwd"}, id="r2"),
            ToolCall(name="read_file", args={"path": "/tmp/x.py"}, id="r3"),
            ToolCall(name="terminal", args={"command": "rm -rf /"}, id="d1"),
            ToolCall(name="terminal", args={"command": "ls -la"}, id="t1"),
            ToolCall(name="write_file", args={"path": "/tmp/out", "content": "x"}, id="w1"),
        ]

        # Filter through permission pipeline
        allowed_calls: list[ToolCall] = []
        denied_calls: list[tuple[ToolCall, str]] = []
        for tc in raw_calls:
            decision = pp.check(tc.name, tc.args)
            if decision.allowed:
                allowed_calls.append(tc)
            else:
                denied_calls.append((tc, decision.reason))

        # Dangerous terminal denied, safe terminal needs prompt (not allowed),
        # write_file needs prompt (not allowed)
        allowed_ids = {tc.id for tc in allowed_calls}
        denied_ids = {tc.id for tc, _ in denied_calls}

        assert "r1" in allowed_ids  # read_file auto-approved
        assert "r2" in allowed_ids
        assert "r3" in allowed_ids
        assert "d1" in denied_ids   # rm -rf / denied
        assert "t1" in denied_ids   # terminal needs prompt
        assert "w1" in denied_ids   # write_file needs prompt

        # Verify rm -rf specifically got DENY level
        rm_decision = pp.check("terminal", {"command": "rm -rf /"})
        assert rm_decision.level == PermissionLevel.DENY

        # Now batch only the allowed calls
        batches = orch.partition(allowed_calls)
        assert len(batches) >= 1
        # All 3 reads should be in the first batch
        assert len(batches[0]) == 3

        executor = _make_mock_executor(default_result="file content")
        results = orch.execute(batches, executor)
        assert len(results) == 3
        for tc in allowed_calls:
            assert results[tc.id].error is None

    def test_dangerous_patterns_variety(self):
        """Various dangerous commands are all denied."""
        pp = PermissionPipeline()
        dangerous_commands = [
            "rm -rf /",
            "sudo rm -rf / --no-preserve-root",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sdb1",
        ]
        for cmd in dangerous_commands:
            decision = pp.check("terminal", {"command": cmd})
            assert decision.allowed is False, f"Expected DENY for: {cmd}"
            assert decision.level == PermissionLevel.DENY

    def test_mixed_dangerous_and_safe_reads(self):
        """Dangerous command denied; safe reads auto-approved and batched."""
        pp = PermissionPipeline()
        orch = ToolOrchestrator(max_workers=8)

        calls = [
            ToolCall(name="read_file", args={"path": f"/file{i}"}, id=f"r{i}")
            for i in range(5)
        ]
        # Add a dangerous call
        calls.append(ToolCall(name="terminal", args={"command": "rm -rf /"}, id="bad"))

        allowed = []
        for tc in calls:
            d = pp.check(tc.name, tc.args)
            if d.allowed:
                allowed.append(tc)

        assert len(allowed) == 5
        assert all(tc.name == "read_file" for tc in allowed)

        batches = orch.partition(allowed)
        # All 5 reads in one concurrent batch
        assert len(batches) == 1
        assert len(batches[0]) == 5


# ---------------------------------------------------------------------------
# 3. Memory + Compression
# ---------------------------------------------------------------------------

class TestMemoryAndCompression:
    """Create messages with tool results, extract memories, compress context,
    and verify memories survive compression."""

    def _make_conversation_with_extractable_content(self) -> list[dict]:
        """20 messages including user preferences, procedural knowledge,
        and tool results."""
        msgs: list[dict] = [
            {"role": "system", "content": "You are a helpful coding assistant."},
        ]
        # Mix user messages (some with extractable patterns), assistant, and tool results
        content_patterns = [
            ("user", "I prefer using Python for all backend projects"),
            ("assistant", "Great choice! Python is excellent for backend work."),
            ("tool", "File /app/main.py content: from flask import Flask"),
            ("user", "How to configure nginx reverse proxy"),
            ("assistant", "Here's how to set up nginx as a reverse proxy..."),
            ("tool", "Config file: server { listen 80; proxy_pass http://localhost:5000; }"),
            ("user", "Remember that my API key is stored in .env file"),
            ("assistant", "I'll remember that. Your API key is in .env."),
            ("tool", "cat .env output: API_KEY=sk-12345"),
            ("user", "I always use pytest for testing"),
            ("assistant", "pytest is the standard. Here's a test example..."),
            ("tool", "test_result: 15 passed, 0 failed"),
            ("user", "The error was fixed by updating the database config"),
            ("assistant", "Glad the config update resolved it!"),
            ("tool", "Database migration applied successfully"),
            ("user", "We accomplished the deployment task today"),
            ("assistant", "Task completed: deployed v2.1 to production."),
            ("tool", "Deployment output: All services running."),
            ("user", "I like using Docker for containerization"),
            ("assistant", "Docker pairs well with Python backends."),
        ]
        for role, content in content_patterns:
            msgs.append({"role": role, "content": content})
        return msgs

    def test_extract_memories_from_20_messages(self):
        """Extract memories from a 20-message conversation."""
        ext = MemoryExtractor()
        msgs = self._make_conversation_with_extractable_content()

        entries = ext.extract_from_conversation(msgs)

        # Should find user preferences, procedural, and episodic memories
        types = {e.type for e in entries}
        assert MemoryType.USER in types
        assert MemoryType.PROCEDURAL in types
        assert MemoryType.EPISODIC in types
        assert len(entries) >= 3

    def test_memories_stored_and_searchable(self):
        """Extracted memories can be stored and found via search."""
        ext = MemoryExtractor()
        store = MemoryStore(max_entries=100)

        msgs = self._make_conversation_with_extractable_content()
        entries = ext.extract_from_conversation(msgs)

        for entry in entries:
            store.add(entry)

        assert len(store.entries) >= 3

        # Search for user preference content
        results = store.search("Python preference")
        assert len(results) > 0
        assert any("Python" in r.content for r in results)

    def test_compress_context_micro_level(self):
        """Micro-level compression prunes old tool results."""
        msgs = self._make_conversation_with_extractable_content()
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        assert len(tool_msgs) >= 3  # We have tool results

        compressor = ContextCompressorV2(model_token_limit=200_000,
                                         profile="balanced")
        result = compressor.compress(msgs, level="micro")

        assert result.level_used == "micro"
        # Compression ratio should be <= 1 (some savings from pruning)
        assert result.ratio <= 1.0
        # Total message count preserved
        assert len(result.messages) == len(msgs)

    def test_memories_extracted_before_compression(self):
        """Extract memories first, then compress — memories survive."""
        ext = MemoryExtractor()
        store = MemoryStore(max_entries=100)

        msgs = self._make_conversation_with_extractable_content()

        # Step 1: Extract memories from full conversation
        entries = ext.extract_from_conversation(msgs)
        for entry in entries:
            store.add(entry)

        memory_count_before = len(store.entries)
        assert memory_count_before >= 3

        # Step 2: Compress the context
        compressor = ContextCompressorV2(model_token_limit=200_000,
                                         profile="balanced")
        compressed = compressor.compress(msgs, level="micro")

        # Memories are independent of compression — still in store
        assert len(store.entries) == memory_count_before

        # Can still search memories after compression
        for entry in entries:
            found = store.search(entry.content[:30])
            assert len(found) > 0

    def test_memory_injection_after_extraction(self):
        """Extract memories → store → inject into context → compress."""
        ext = MemoryExtractor()
        store = MemoryStore(max_entries=100)
        injector = MemoryInjector()

        msgs = self._make_conversation_with_extractable_content()

        # Extract
        entries = ext.extract_from_conversation(msgs)
        for entry in entries:
            store.add(entry)

        # Inject memory context
        memory_context = injector.prepare_context(store.entries, max_tokens=500)
        assert "## Memory Context" in memory_context

        # Compress
        compressor = ContextCompressorV2(model_token_limit=200_000,
                                         profile="balanced")
        result = compressor.compress(msgs, level="micro")
        assert result.ratio <= 1.0

    def test_reactive_compression_with_many_tool_results(self):
        """Reactive compression reduces tokens when there are many tool results."""
        # Generate a larger conversation to ensure reactive compression helps
        msgs = _make_messages_with_tools(40, tool_every=2, content_size=600)

        original_tokens = _total_tokens(msgs)
        compressor = ContextCompressorV2(model_token_limit=5_000,
                                         profile="balanced")
        result = compressor.compress(msgs, level="reactive")

        assert result.level_used == "reactive"
        assert result.compressed_tokens < original_tokens


# ---------------------------------------------------------------------------
# 4. Stress Test: 50 read_file calls
# ---------------------------------------------------------------------------

class TestStressFiftyReads:
    """50 read_file calls: orchestrator batches into 1 concurrent batch;
    result manager deduplicates repeated file reads."""

    def test_50_reads_partitioned_into_one_batch(self):
        """All 50 read_file calls go into a single concurrent batch."""
        orch = ToolOrchestrator(max_workers=16)
        calls = [
            ToolCall(name="read_file", args={"path": f"/file_{i}.txt"},
                     id=f"r{i}")
            for i in range(50)
        ]
        batches = orch.partition(calls)
        assert len(batches) == 1
        assert len(batches[0]) == 50

    def test_50_reads_executed_successfully(self):
        """All 50 reads execute without errors."""
        orch = ToolOrchestrator(max_workers=16)
        calls = [
            ToolCall(name="read_file", args={"path": f"/file_{i}.txt"},
                     id=f"r{i}")
            for i in range(50)
        ]
        batches = orch.partition(calls)

        def executor(tc: ToolCall) -> str:
            return f"Content of {tc.args['path']}"

        results = orch.execute(batches, executor)
        assert len(results) == 50
        for tc in calls:
            assert results[tc.id].error is None
            assert tc.args["path"] in results[tc.id].result

    def test_50_reads_deduplicated_by_result_manager(self):
        """If all 50 reads return identical content, result manager
        deduplicates: 1 fresh + 49 deduped."""
        rm = ToolResultManager()
        orch = ToolOrchestrator(max_workers=16)

        calls = [
            ToolCall(name="read_file", args={"path": f"/file_{i}.txt"},
                     id=f"r{i}")
            for i in range(50)
        ]
        batches = orch.partition(calls)

        # All return the same content
        def executor(tc: ToolCall) -> str:
            return "same file content"

        results = orch.execute(batches, executor)

        dedup_count = 0
        for tc in calls:
            pr = rm.process("read_file", results[tc.id].result)
            if pr.was_deduped:
                dedup_count += 1

        assert dedup_count == 49
        assert rm.get_stats()["dedup_saves"] == 49
        assert rm.get_stats()["total_processed"] == 50

    def test_50_reads_partial_dedup(self):
        """50 reads returning 5 unique contents → 5 fresh + 45 deduped."""
        rm = ToolResultManager()
        orch = ToolOrchestrator(max_workers=16)

        calls = [
            ToolCall(name="read_file", args={"path": f"/file_{i}.txt"},
                     id=f"r{i}")
            for i in range(50)
        ]
        batches = orch.partition(calls)

        # 5 unique contents cycling
        def executor(tc: ToolCall) -> str:
            idx = int(tc.id[1:])
            return f"content_{idx % 5}"

        results = orch.execute(batches, executor)

        fresh_count = 0
        dedup_count = 0
        for tc in calls:
            pr = rm.process("read_file", results[tc.id].result)
            if pr.was_deduped:
                dedup_count += 1
            else:
                fresh_count += 1

        assert fresh_count == 5
        assert dedup_count == 45


# ---------------------------------------------------------------------------
# 5. Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Empty results, None content, permission denied mid-batch,
    and other boundary conditions."""

    def test_empty_string_result(self):
        """Empty string result is processed without error."""
        rm = ToolResultManager()
        result = rm.process("read_file", "")
        assert result.content == ""
        assert result.token_count >= 0
        assert len(result.hash) == 64

    def test_none_content_handled_gracefully(self):
        """None content should not crash — converted to empty string."""
        rm = ToolResultManager()
        result = rm.process("read_file", None)
        # The implementation converts None → '' internally
        assert result is not None
        assert result.content == ""
        assert result.token_count == 0

    def test_executor_returns_none_captured(self):
        """Executor returning None is stored as None in BatchResult."""
        orch = ToolOrchestrator(max_workers=4)
        calls = [ToolCall(name="read_file", args={"path": "/empty"}, id="e1")]
        batches = orch.partition(calls)

        def executor(tc: ToolCall):
            return None

        results = orch.execute(batches, executor)
        assert results["e1"].error is None
        assert results["e1"].result is None

    def test_permission_denied_mid_batch(self):
        """A permission error raised by the executor for one call
        is captured as an error without affecting other calls in the batch."""
        orch = ToolOrchestrator(max_workers=4)

        calls = [
            ToolCall(name="read_file", args={"path": "/allowed"}, id="ok"),
            ToolCall(name="read_file", args={"path": "/denied"}, id="denied"),
            ToolCall(name="read_file", args={"path": "/also_ok"}, id="ok2"),
        ]
        batches = orch.partition(calls)
        # All reads → 1 batch
        assert len(batches) == 1

        def executor(tc: ToolCall) -> str:
            if tc.args.get("path") == "/denied":
                raise PermissionError("Access denied to /denied")
            return f"content of {tc.args['path']}"

        results = orch.execute(batches, executor)

        assert results["ok"].error is None
        assert results["ok"].result == "content of /allowed"
        assert results["ok2"].error is None
        assert results["ok2"].result == "content of /also_ok"
        assert results["denied"].error is not None
        assert "Access denied" in results["denied"].error

    def test_empty_tool_calls_list(self):
        """Empty list returns empty batches and results."""
        orch = ToolOrchestrator(max_workers=4)
        batches = orch.partition([])
        assert batches == []

        results = orch.execute(batches, _make_mock_executor())
        assert results == {}

    def test_single_tool_call(self):
        """Single call works correctly through the pipeline."""
        orch = ToolOrchestrator(max_workers=4)
        rm = ToolResultManager()

        calls = [ToolCall(name="read_file", args={"path": "/solo"}, id="s1")]
        batches = orch.partition(calls)
        assert len(batches) == 1
        assert len(batches[0]) == 1

        results = orch.execute(batches, _make_mock_executor(default_result="solo content"))
        pr = rm.process("read_file", results["s1"].result)
        assert pr.content == "solo content"
        assert pr.was_deduped is False

    def test_all_writes_partitioned_serially(self):
        """All write calls get individual batches (serial execution)."""
        orch = ToolOrchestrator(max_workers=4)
        calls = [
            ToolCall(name="write_file", args={"path": f"/out{i}"}, id=f"w{i}")
            for i in range(10)
        ]
        batches = orch.partition(calls)
        assert len(batches) == 10
        for batch in batches:
            assert len(batch) == 1

    def test_permission_empty_tool_name(self):
        """Empty tool name defaults to prompt."""
        pp = PermissionPipeline()
        decision = pp.check("", {})
        assert decision.needs_prompt is True

    def test_compressor_with_empty_messages(self):
        """Compressing an empty message list doesn't crash."""
        compressor = ContextCompressorV2(model_token_limit=200_000)
        result = compressor.compress([], level="micro")
        assert result.messages == []
        assert result.original_tokens == 0
        assert result.compressed_tokens == 0

    def test_memory_extractor_with_empty_messages(self):
        """Extracting from empty message list returns empty entries."""
        ext = MemoryExtractor()
        entries = ext.extract_from_conversation([])
        assert entries == []

    def test_memory_extractor_with_none_content(self):
        """Messages with None content are skipped."""
        ext = MemoryExtractor()
        msgs = [
            {"role": "user", "content": None},
            {"role": "assistant", "content": "I prefer Python"},  # won't match (role check)
            {"role": "user", "content": "I prefer dark mode"},
        ]
        entries = ext.extract_from_conversation(msgs)
        # Only the last message should match
        assert len(entries) == 1
        assert "dark mode" in entries[0].content

    def test_large_result_truncation_preserves_content(self):
        """Large results are truncated but head and tail are preserved."""
        rm = ToolResultManager(per_tool_budgets={"test_tool": 50})

        # Create a large result with identifiable content
        head = "BEGINNING_MARKER\n"
        tail = "\nENDING_MARKER"
        middle = "middle content line\n" * 500
        large = head + middle + tail

        result = rm.process("test_tool", large)
        assert result.was_truncated is True
        assert "BEGINNING_MARKER" in result.content
        assert "ENDING_MARKER" in result.content

    def test_orchestrator_progress_callback_receives_all_events(self):
        """Progress callback is called for each tool call."""
        orch = ToolOrchestrator(max_workers=4)
        calls = [
            ToolCall(name="read_file", args={"path": f"/f{i}"}, id=f"r{i}")
            for i in range(3)
        ]
        batches = orch.partition(calls)

        events: list[tuple[str, str, float]] = []

        def on_progress(name: str, status: str, elapsed: float) -> None:
            events.append((name, status, elapsed))

        results = orch.execute(batches, _make_mock_executor(), on_progress=on_progress)

        statuses = [e[1] for e in events]
        assert statuses.count("started") == 3
        assert statuses.count("completed") == 3

    def test_full_pipeline_with_dedup_and_progress(self):
        """Combined: orchestrator with progress + result manager with dedup."""
        orch = ToolOrchestrator(max_workers=4)
        rm = ToolResultManager()

        events: list[str] = []

        calls = [
            ToolCall(name="read_file", args={"path": "/a"}, id="a"),
            ToolCall(name="read_file", args={"path": "/b"}, id="b"),
        ]
        batches = orch.partition(calls)

        def on_progress(name: str, status: str, elapsed: float) -> None:
            events.append(f"{name}:{status}")

        def executor(tc: ToolCall) -> str:
            return "shared result"

        results = orch.execute(batches, executor, on_progress=on_progress)

        r1 = rm.process("read_file", results["a"].result)
        r2 = rm.process("read_file", results["b"].result)

        assert r1.was_deduped is False
        assert r2.was_deduped is True
        assert "read_file:started" in events
        assert "read_file:completed" in events
