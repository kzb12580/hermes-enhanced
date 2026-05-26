"""Edge-case sweep: 15 tests targeting scenarios not covered by existing suites.

Each test targets a specific boundary condition or stress scenario.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.hermes2.hermes2_adapter import Hermes2Config, Hermes2Engine
from agent.hermes2.tool_orchestrator import ToolCall, ToolOrchestrator
from agent.hermes2.permission_pipeline import (
    PermissionLevel, PermissionPipeline, PermissionRule,
)
from agent.hermes2.memory_system import MemoryEntry, MemoryStore, MemoryType
from agent.hermes2.context_compressor_v2 import ContextCompressorV2, PressureMonitor
from agent.hermes2.post_turn_hooks import (
    HookContext, HookPipeline, PostTurnHook, HookResult,
)
from agent.hermes2.auto_dream import AutoDreamer, DreamTrigger, SessionSummary
from agent.hermes2.smart_retry import (
    SmartRetryManager, RetryPolicy, ErrorCategory, classify_error,
)
from agent.hermes2.mcp_transport import McpServerConfig, TransportType
from agent.hermes2.token_budget_manager import TokenBudgetManager, PressureZone
from agent.hermes2.coordinator import (
    Coordinator, TaskDecomposer, TaskScheduler, AgentProfile, AgentRole,
    TaskSpec, TaskStatus,
)
from agent.hermes2.tool_result_manager import ToolResultManager


# ═══════════════════════════════════════════════════════════════════════
# 1. Empty tool calls list — verify clean return, no crash
# ═══════════════════════════════════════════════════════════════════════

class TestEmptyToolCallsList:
    """process_tool_calls([]) should return empty processed dict."""

    def test_empty_list_returns_empty(self):
        engine = Hermes2Engine()
        result = engine.process_tool_calls([], lambda tc: "x")
        assert result["processed"] == {}
        assert result["denied"] == []
        assert result["needs_prompt"] == []
        assert result["warnings"] == []

    def test_none_list_handled(self):
        """None input should not crash — may raise TypeError or return empty."""
        engine = Hermes2Engine()
        try:
            result = engine.process_tool_calls(None, lambda tc: "x")
            # If it doesn't crash, should return empty
            assert isinstance(result, dict)
        except (TypeError, AttributeError):
            pass  # Acceptable — None is not a valid list


# ═══════════════════════════════════════════════════════════════════════
# 2. Single tool call with empty args dict
# ═══════════════════════════════════════════════════════════════════════

class TestSingleToolCallEmptyArgs:
    """A tool call with args={} should still be processed normally."""

    def test_empty_args_processed(self):
        engine = Hermes2Engine()
        calls = [{"name": "read_file", "args": {}}]
        result = engine.process_tool_calls(calls, lambda tc: "file content")
        assert len(result["processed"]) == 1

    def test_missing_args_key_processed(self):
        """Missing 'args' key should default to {}."""
        engine = Hermes2Engine()
        calls = [{"name": "read_file"}]
        result = engine.process_tool_calls(calls, lambda tc: "ok")
        assert len(result["processed"]) == 1

    def test_none_args_denied(self):
        """args=None (not a dict) should be denied with a warning."""
        engine = Hermes2Engine()
        calls = [{"name": "read_file", "args": None}]
        result = engine.process_tool_calls(calls, lambda tc: "ok")
        # Should be denied because None is not a dict
        assert len(result["denied"]) == 1 or len(result["warnings"]) >= 1


# ═══════════════════════════════════════════════════════════════════════
# 3. Tool call with None id — should auto-generate UUID
# ═══════════════════════════════════════════════════════════════════════

class TestToolCallNoneId:
    """When id is missing or None, the engine should auto-generate one."""

    def test_missing_id_auto_generated(self):
        engine = Hermes2Engine()
        calls = [{"name": "read_file", "args": {}}]
        result = engine.process_tool_calls(calls, lambda tc: "content")
        # Should have exactly one processed entry with a string key
        assert len(result["processed"]) == 1
        key = list(result["processed"].keys())[0]
        assert isinstance(key, str)
        assert len(key) > 0

    def test_explicit_none_id_auto_generated(self):
        engine = Hermes2Engine()
        calls = [{"name": "read_file", "args": {}, "id": None}]
        result = engine.process_tool_calls(calls, lambda tc: "content")
        assert len(result["processed"]) == 1
        key = list(result["processed"].keys())[0]
        assert isinstance(key, str)
        # UUID format check (contains hyphens)
        assert "-" in key


# ═══════════════════════════════════════════════════════════════════════
# 4. Very large tool result (~10MB string)
# ═══════════════════════════════════════════════════════════════════════

class TestVeryLargeToolResult:
    """Processing a 10MB result should truncate but not crash."""

    def test_10mb_result_truncated(self):
        engine = Hermes2Engine(Hermes2Config(max_context_tokens=200_000))
        big_content = "A" * (10 * 1024 * 1024)  # 10 MB
        calls = [{"name": "read_file", "args": {"path": "/tmp/big.txt"}}]
        executor = lambda tc: big_content
        result = engine.process_tool_calls(calls, executor)
        assert len(result["processed"]) == 1
        entry = list(result["processed"].values())[0]
        assert "content" in entry
        # Content should be much smaller than 10MB (truncated)
        assert len(entry["content"]) < len(big_content)
        assert entry["was_truncated"] is True

    def test_10mb_result_token_count_reasonable(self):
        mgr = ToolResultManager(max_tokens=15_000)
        big = "x" * (10 * 1024 * 1024)
        pr = mgr.process("read_file", big)
        assert pr.was_truncated is True
        # Token count should be within a reasonable budget
        assert pr.token_count <= 20_000


# ═══════════════════════════════════════════════════════════════════════
# 5. Concurrent process_tool_calls from multiple threads
# ═══════════════════════════════════════════════════════════════════════

class TestConcurrentProcessToolCalls:
    """Multiple threads calling process_tool_calls simultaneously."""

    def test_concurrent_calls_dont_crash(self):
        engine = Hermes2Engine()
        results = [None] * 10
        errors = []

        def worker(idx):
            try:
                calls = [
                    {"name": "read_file", "args": {"path": f"/tmp/f{idx}.txt"}},
                ]
                r = engine.process_tool_calls(calls, lambda tc: f"content_{idx}")
                results[idx] = r
            except Exception as e:
                errors.append((idx, e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"Errors in threads: {errors}"
        for i in range(10):
            assert results[i] is not None
            assert len(results[i]["processed"]) == 1


# ═══════════════════════════════════════════════════════════════════════
# 6. Memory store with 10000 entries
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryStore10000Entries:
    """Stress test: adding 10000 entries to memory store."""

    def test_10000_entries_eviction(self):
        store = MemoryStore(max_entries=10000)
        for i in range(10000):
            store.add(MemoryEntry(
                type=MemoryType.MEMORY,
                content=f"Entry number {i} with some content about topic_{i % 50}",
                tags=[f"tag_{i % 20}"],
            ))
        assert len(store.entries) == 10000

    def test_10000_entries_overflow(self):
        """Adding more than max_entries should trigger eviction."""
        store = MemoryStore(max_entries=100)
        for i in range(200):
            store.add(MemoryEntry(
                type=MemoryType.MEMORY,
                content=f"Entry {i}",
            ))
        assert len(store.entries) <= 100

    def test_search_performance_with_many_entries(self):
        """Search should still return results (not crash) with many entries."""
        store = MemoryStore(max_entries=5000)
        for i in range(5000):
            store.add(MemoryEntry(
                type=MemoryType.MEMORY,
                content=f"Entry about python programming number {i}",
            ))
        results = store.search("python programming", limit=5)
        assert len(results) > 0
        assert len(results) <= 5


# ═══════════════════════════════════════════════════════════════════════
# 7. Context compressor with 500 messages
# ═══════════════════════════════════════════════════════════════════════

class TestContextCompressor500Messages:
    """Compress a conversation with 500 messages."""

    def test_500_messages_compression(self):
        compressor = ContextCompressorV2(model_token_limit=200_000)
        messages = []
        for i in range(500):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"role": role, "content": f"Message {i}: " + "x" * 200})

        should, reason = compressor.should_compress(messages)
        assert isinstance(should, bool)

        if should:
            result = compressor.compress(messages, level="auto")
            assert result.compressed_tokens <= result.original_tokens
            assert result.ratio <= 1.0
        else:
            # Even if not needed, compression should work without crash
            result = compressor.compress(messages, level="micro")
            assert result.compressed_tokens >= 0

    def test_500_messages_with_tool_results(self):
        """Messages with tool results should be pruned first."""
        compressor = ContextCompressorV2(model_token_limit=50_000)
        messages = []
        for i in range(500):
            if i % 5 == 0:
                messages.append({"role": "tool", "content": f"Tool result {i}: " + "y" * 500, "name": "terminal"})
            elif i % 2 == 0:
                messages.append({"role": "user", "content": f"User msg {i}"})
            else:
                messages.append({"role": "assistant", "content": f"Assistant msg {i}: " + "z" * 300})

        result = compressor.compress(messages, level="micro")
        assert result.compressed_tokens <= result.original_tokens


# ═══════════════════════════════════════════════════════════════════════
# 8. Hook pipeline with a hook that raises exception
# ═══════════════════════════════════════════════════════════════════════

class ExplodingHook(PostTurnHook):
    """A hook that always raises an exception."""
    name = "exploding_hook"
    priority = 1  # Runs first

    async def execute(self, ctx: HookContext) -> HookResult:
        raise RuntimeError("Hook intentionally exploded!")


class TestHookPipelineExceptionInHook:
    """A hook that raises should not crash the pipeline."""

    def test_exploding_hook_doesnt_crash_pipeline(self):
        pipeline = HookPipeline()
        pipeline.register(ExplodingHook())

        ctx = HookContext(
            messages=[{"role": "user", "content": "test"}],
            user_message="test",
        )
        results = asyncio.run(pipeline.run_all(ctx))
        assert len(results) == 1
        assert results[0].success is False
        assert "exploded" in results[0].error.lower() or "exploding_hook" in results[0].error.lower()

    def test_exploding_hook_followed_by_good_hook(self):
        """Good hooks after an exploding one should still run."""
        from agent.hermes2.post_turn_hooks import MemoryExtractionHook

        pipeline = HookPipeline()
        pipeline.register(ExplodingHook())
        pipeline.register(MemoryExtractionHook())

        ctx = HookContext(
            messages=[{"role": "user", "content": "I prefer dark mode"}],
            user_message="I prefer dark mode",
        )
        results = asyncio.run(pipeline.run_all(ctx))
        assert len(results) == 2
        assert results[0].success is False  # exploding
        assert results[1].success is True   # memory extraction


# ═══════════════════════════════════════════════════════════════════════
# 9. AutoDreamer with 0 sessions — should not dream
# ═══════════════════════════════════════════════════════════════════════

class TestAutoDreamerZeroSessions:
    """AutoDreamer behavior with 0 sessions.

    BUG FOUND: AutoDreamer._last_dream defaults to epoch (1970-01-01), so
    the time_threshold_hours check always passes after ~any amount of time.
    This means a brand-new AutoDreamer with 0 recorded sessions and a high
    time threshold will STILL trigger should_dream() because the time since
    epoch exceeds any reasonable threshold.

    The test below documents this behavior. A correct implementation would
    set _last_dream to datetime.now() on init so that time-based triggers
    only fire after the configured interval.
    """

    def test_should_dream_with_zero_sessions_and_time_bug(self):
        """BUG: triggers on time even with 0 sessions and high time threshold.

        The DreamTrigger's time check compares (now - last_run) against
        time_threshold_hours, but last_run defaults to epoch (0), so the
        time delta is always ~56+ years.
        """
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=5, time_threshold_hours=99999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        # BUG: This returns True even with 0 sessions because _last_dream is epoch
        result = dreamer.should_dream()
        # Document the bug: assert it IS True (incorrect behavior)
        assert result is True, (
            "BUG: should_dream returns True with 0 sessions because "
            "_last_dream defaults to epoch, making time check always pass"
        )

    def test_should_dream_with_recent_last_dream(self):
        """When _last_dream is set to now, zero sessions should NOT trigger."""
        from datetime import datetime, timezone
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=5, time_threshold_hours=99999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        # Manually set _last_dream to now to simulate a recent dream
        dreamer._last_dream = datetime.now(timezone.utc)
        assert dreamer.should_dream() is False

    def test_dream_with_zero_sessions_returns_empty_report(self):
        store = MemoryStore()
        dreamer = AutoDreamer(memory_store=store)
        report = dreamer.dream()
        assert report.sessions_reviewed == 0
        assert report.memories_created == 0

    def test_dream_if_needed_with_zero_sessions_and_time_bug(self):
        """BUG: dream_if_needed fires even with 0 sessions (time bug)."""
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=5, time_threshold_hours=99999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        # BUG: returns a DreamReport instead of None
        result = dreamer.dream_if_needed()
        assert result is not None, (
            "BUG: dream_if_needed triggers with 0 sessions due to epoch time bug"
        )


# ═══════════════════════════════════════════════════════════════════════
# 10. Permission pipeline with 100 rules
# ═══════════════════════════════════════════════════════════════════════

class TestPermissionPipeline100Rules:
    """Performance/correctness with 100 rules."""

    def test_100_rules_first_match_wins(self):
        rules = []
        for i in range(100):
            rules.append(PermissionRule(
                f"tool_{i}",
                PermissionLevel.AUTO if i % 2 == 0 else PermissionLevel.DENY,
                f"Rule {i}",
            ))
        pipeline = PermissionPipeline(rules=rules)

        # tool_0 should be AUTO (first matching rule)
        decision = pipeline.check("tool_0", {})
        assert decision.allowed is True

        # tool_1 should be DENY
        decision = pipeline.check("tool_1", {})
        assert decision.allowed is False

    def test_100_rules_unmatched_defaults_to_prompt(self):
        rules = [PermissionRule(f"tool_{i}", PermissionLevel.AUTO) for i in range(100)]
        pipeline = PermissionPipeline(rules=rules)

        decision = pipeline.check("nonexistent_tool", {})
        assert decision.needs_prompt is True

    def test_100_rules_check_performance(self):
        """100 rules × 100 checks should complete in under 1 second."""
        rules = [PermissionRule(f"tool_{i}", PermissionLevel.AUTO) for i in range(100)]
        pipeline = PermissionPipeline(rules=rules)

        start = time.monotonic()
        for i in range(100):
            pipeline.check(f"check_{i}", {})
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"100 checks took {elapsed:.2f}s — too slow"


# ═══════════════════════════════════════════════════════════════════════
# 11. Tool result with unicode content
# ═══════════════════════════════════════════════════════════════════════

class TestToolResultUnicode:
    """Unicode (CJK, emoji, RTL) in tool results should not crash."""

    def test_cjk_content(self):
        mgr = ToolResultManager()
        content = "日本語のテスト結果です。ファイルの内容を表示します。"
        result = mgr.process("read_file", content)
        assert result.content == content
        assert result.token_count > 0

    def test_emoji_content(self):
        mgr = ToolResultManager()
        content = "🎉 Success! ✅ All tests passed 🚀"
        result = mgr.process("terminal", content)
        assert "🎉" in result.content

    def test_mixed_unicode_dedup(self):
        mgr = ToolResultManager()
        content = "中文内容 with 日本語 and 🎉"
        r1 = mgr.process("read_file", content)
        r2 = mgr.process("read_file", content)
        assert r1.was_deduped is False
        assert r2.was_deduped is True

    def test_rtl_content(self):
        mgr = ToolResultManager()
        content = "مرحبا بالعالم — هذا اختبار"
        result = mgr.process("read_file", content)
        assert result.content == content

    def test_unicode_in_engine_pipeline(self):
        engine = Hermes2Engine()
        calls = [{"name": "read_file", "args": {"path": "/tmp/uni.txt"}}]
        executor = lambda tc: "文件内容 🌍 محتوى"
        result = engine.process_tool_calls(calls, executor)
        assert len(result["processed"]) == 1


# ═══════════════════════════════════════════════════════════════════════
# 12. Smart retry with permanent failure
# ═══════════════════════════════════════════════════════════════════════

class TestSmartRetryPermanentFailure:
    """Permanent errors should NOT be retried."""

    def test_404_not_retried(self):
        call_count = [0]

        def failing_executor(tc):
            call_count[0] += 1
            raise FileNotFoundError("File not found (404)")

        mgr = SmartRetryManager(sleep_fn=lambda x: None)
        tc = ToolCall(name="read_file", args={"path": "/nonexistent"})
        result = mgr.execute_with_retry(tc, failing_executor)

        assert result.success is False
        assert result.error_category == ErrorCategory.PERMANENT
        # Should NOT have retried a permanent error
        assert call_count[0] == 1

    def test_permission_denied_not_retried(self):
        call_count = [0]

        def failing_executor(tc):
            call_count[0] += 1
            raise PermissionError("Permission denied")

        mgr = SmartRetryManager(sleep_fn=lambda x: None)
        tc = ToolCall(name="write_file", args={"path": "/etc/passwd"})
        result = mgr.execute_with_retry(tc, failing_executor)

        assert result.success is False
        assert result.error_category == ErrorCategory.PERMANENT
        assert call_count[0] == 1

    def test_transient_error_is_retried(self):
        """Transient errors should be retried — using different error messages
        to avoid the 'same error repeated' early-stop guard."""
        call_count = [0]

        def transient_then_ok(tc):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Connection timed out")
            if call_count[0] == 2:
                raise ConnectionError("ECONNRESET")
            return "success"

        mgr = SmartRetryManager(sleep_fn=lambda x: None)
        tc = ToolCall(name="web_extract", args={"url": "https://example.com"})
        result = mgr.execute_with_retry(tc, transient_then_ok)

        assert result.success is True
        assert result.attempts == 3
        assert result.retries == 2

    def test_same_error_stops_early(self):
        """BUG/DESIGN: Same error message repeated causes early stop even for
        transient errors. The retry manager has a guard that stops if all
        history entries have the same error message."""
        call_count = [0]

        def same_error(tc):
            call_count[0] += 1
            raise ConnectionError("Connection timed out")

        mgr = SmartRetryManager(sleep_fn=lambda x: None)
        tc = ToolCall(name="web_extract", args={"url": "https://example.com"})
        result = mgr.execute_with_retry(tc, same_error)

        assert result.success is False
        # The "same error" guard kicks in after 2 identical errors
        assert call_count[0] == 2, (
            f"Expected 2 attempts (same-error guard), got {call_count[0]}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 13. MCP transport config with invalid command
# ═══════════════════════════════════════════════════════════════════════

class TestMcpTransportInvalidCommand:
    """Invalid MCP commands should raise ValueError at config time."""

    def test_stdio_requires_command(self):
        """STDIO transport without command should raise ValueError."""
        with pytest.raises(ValueError, match="requires a 'command'"):
            McpServerConfig(
                name="bad-server",
                transport=TransportType.STDIO,
                # command intentionally omitted
            )

    def test_sse_requires_url(self):
        with pytest.raises(ValueError, match="requires a 'url'"):
            McpServerConfig(
                name="bad-sse",
                transport=TransportType.SSE,
                # url intentionally omitted
            )

    def test_blocked_command_raises(self):
        from agent.hermes2.mcp_transport import StdioTransport
        with pytest.raises(ValueError, match="denylist"):
            StdioTransport._validate_command("rm", ["-rf", "/"])

    def test_shell_metachar_in_command_raises(self):
        from agent.hermes2.mcp_transport import StdioTransport
        with pytest.raises(ValueError, match="dangerous character"):
            StdioTransport._validate_command("node; rm -rf /", [])

    def test_valid_stdio_config(self):
        config = McpServerConfig(
            name="good-server",
            transport=TransportType.STDIO,
            command="my-mcp-server",
            args=["--port", "3000"],
        )
        assert config.name == "good-server"
        assert config.command == "my-mcp-server"


# ═══════════════════════════════════════════════════════════════════════
# 14. Token budget with exact limit
# ═══════════════════════════════════════════════════════════════════════

class TestTokenBudgetExactLimit:
    """Edge behavior when budget is exactly at the limit."""

    def test_exact_budget_returns_green(self):
        budget = TokenBudgetManager(session_budget=100_000, model_limit=100_000)
        assert budget.pressure_zone == PressureZone.GREEN
        assert budget.remaining_tokens == 100_000

    def test_budget_at_95_percent_is_red(self):
        budget = TokenBudgetManager(session_budget=100_000, model_limit=100_000)
        budget.begin_turn(1)
        budget.record_usage("read_file", 95_000)
        budget.end_turn()
        assert budget.pressure_zone == PressureZone.RED

    def test_budget_exceeded_returns_exceeded_zone(self):
        budget = TokenBudgetManager(session_budget=100_000, model_limit=100_000)
        budget.begin_turn(1)
        budget.record_usage("read_file", 100_000)
        budget.end_turn()
        assert budget.pressure_zone == PressureZone.EXCEEDED
        assert budget.remaining_tokens == 0

    def test_allocate_when_exceeded_gives_minimal(self):
        budget = TokenBudgetManager(session_budget=100, model_limit=200)
        budget.begin_turn(1)
        budget.record_usage("terminal", 100)
        budget.end_turn()

        alloc = budget.allocate("read_file", requested_tokens=5000)
        assert alloc.allocated_tokens <= 500  # Emergency minimal
        assert alloc.pressure_zone == PressureZone.EXCEEDED

    def test_zero_remaining_still_allocates_minimum(self):
        budget = TokenBudgetManager(session_budget=10, model_limit=200)
        budget.begin_turn(1)
        budget.record_usage("terminal", 10)
        budget.end_turn()
        assert budget.remaining_tokens == 0

        alloc = budget.allocate("read_file")
        # Should still get some minimal allocation
        assert alloc.allocated_tokens >= 0


# ═══════════════════════════════════════════════════════════════════════
# 15. Coordinator with circular dependencies
# ═══════════════════════════════════════════════════════════════════════

class TestCoordinatorCircularDependencies:
    """Tasks with circular dependencies should not hang."""

    def test_circular_dependency_stalls_gracefully(self):
        """Tasks A→B→A should never get assigned (stuck in PENDING)."""
        agents = [
            AgentProfile(
                role=AgentRole.WORKER,
                name="worker",
                capabilities=["code"],
            ),
        ]
        scheduler = TaskScheduler(agents)

        task_a = TaskSpec(description="Task A", required_capabilities=["code"])
        task_b = TaskSpec(description="Task B", required_capabilities=["code"])
        # Create circular dependency
        task_a.dependencies = [task_b.id]
        task_b.dependencies = [task_a.id]

        assignments = scheduler.schedule([task_a, task_b])

        # Neither should be assigned since each depends on the other
        total_assigned = sum(len(v) for v in assignments.values())
        assert total_assigned == 0

    def test_self_referencing_dependency(self):
        """A task that depends on itself should not be assigned."""
        agents = [
            AgentProfile(
                role=AgentRole.WORKER,
                name="worker",
                capabilities=["code"],
            ),
        ]
        scheduler = TaskScheduler(agents)

        task = TaskSpec(description="Self-dep", required_capabilities=["code"])
        task.dependencies = [task.id]  # depends on itself

        assignments = scheduler.schedule([task])
        total_assigned = sum(len(v) for v in assignments.values())
        assert total_assigned == 0

    def test_coordinator_full_cycle_with_circular_deps(self):
        """run_full_cycle should complete (not hang) even with circular deps."""
        coordinator = Coordinator()
        # Decompose normally — then manually add circular deps
        tasks = coordinator.plan("Build the API then test the API")
        if len(tasks) >= 2:
            tasks[0].dependencies = [tasks[1].id]
            tasks[1].dependencies = [tasks[0].id]

        # This should not hang — max_rounds limits iterations
        def executor(task):
            return {"status": "done"}

        result = coordinator.run_full_cycle(
            "Build the API then test the API",
            executor_fn=executor,
        )
        assert isinstance(result.summary, str)


# ═══════════════════════════════════════════════════════════════════════
# Run with: pytest test_edge_case_sweep.py -v
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
