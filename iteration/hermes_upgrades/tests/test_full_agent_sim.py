"""Full-agent simulation tests combining ALL Hermes 2.0 modules.

Simulates a 5-turn coding session with all modules working together:
- Turn 1: User asks to fix auth bug -> agent reads 3 files concurrently
- Turn 2: Agent searches codebase -> 2 concurrent searches
- Turn 3: Agent edits auth.py -> permission check + serial write
- Turn 4: Agent runs tests -> terminal (permission prompt)
- Turn 5: Agent writes test file -> serial write

After each turn:
- Run post-turn hooks (memory extraction, usage tracking)
- Check context pressure
- Process results through result manager
"""

from __future__ import annotations

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone

import pytest

# Ensure direct module imports work (like other tests in this package)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Ensure package imports work (for post_turn_hooks which uses relative imports)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tool_orchestrator import (
    BatchResult,
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
    PermissionDecision,
    PermissionLevel,
    PermissionPipeline,
    PermissionRule,
)
from context_compressor_v2 import (
    CompressionProfile,
    ContextCompressorV2,
    PressureMonitor,
    _total_tokens,
)
from hermes_upgrades.memory_system import (
    MemoryEntry,
    MemoryExtractor,
    MemoryInjector,
    MemoryStore,
    MemoryType,
)
from hermes_upgrades.post_turn_hooks import (
    ContextHealthHook,
    HookContext,
    HookPipeline,
    HookResult,
    MemoryExtractionHook,
    PostTurnHook,
    PromptSuggestionHook,
    UsageTrackingHook,
)
from hermes_upgrades.auto_dream import (
    AutoDreamer,
    DreamReport,
    DreamTrigger,
    SessionSummary,
    TranscriptAnalyzer,
)
from coordinator import (
    AgentProfile,
    AgentRole,
    AggregatedResult,
    Coordinator,
    TaskDecomposer,
    TaskScheduler,
    TaskSpec,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine to completion."""
    return asyncio.run(coro)


def make_executor(results_map: dict[str, str], default: str = "ok"):
    """Create a sync executor returning canned results per tool name."""
    def executor(tc: ToolCall) -> str:
        return results_map.get(tc.name, default)
    return executor


class SimulatedSession:
    """Encapsulates a full multi-turn agent simulation.

    Tracks all modules: orchestrator, result manager, permission pipeline,
    context compressor, memory system, hook pipeline, and auto-dreamer.
    """

    def __init__(self, model_token_limit: int = 200_000):
        self.orch = ToolOrchestrator(max_workers=8)
        self.result_mgr = ToolResultManager(max_tokens=80_000)
        self.perm_pipe = PermissionPipeline()
        self.compressor = ContextCompressorV2(
            model_token_limit=model_token_limit, profile="balanced"
        )
        self.memory_store = MemoryStore(max_entries=200)
        self.memory_extractor = MemoryExtractor()
        self.memory_injector = MemoryInjector()
        self.hook_pipeline = HookPipeline()
        self.dreamer = AutoDreamer(
            memory_store=self.memory_store,
            trigger=DreamTrigger(session_threshold=5, time_threshold_hours=24),
        )
        # Reset last dream to now so time threshold doesn't falsely trigger
        self.dreamer._last_dream = datetime.now(timezone.utc)

        # Register hooks in priority order
        self.hook_pipeline.register(MemoryExtractionHook())
        self.hook_pipeline.register(UsageTrackingHook())
        self.hook_pipeline.register(PromptSuggestionHook())
        self.hook_pipeline.register(ContextHealthHook(model_token_limit=model_token_limit))

        # Conversation state
        self.messages: list[dict] = [
            {"role": "system", "content": "You are a helpful coding assistant."},
        ]
        self.turn_count = 0
        self.all_tool_calls: list[ToolCall] = []
        self.all_results: dict[str, BatchResult] = {}
        self.permission_decisions: list[PermissionDecision] = []
        self.hook_results_per_turn: list[list[HookResult]] = []
        self.pressure_history: list[float] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results(self, results: list[dict]) -> None:
        self.messages.extend(results)

    def check_permissions(self, calls: list[ToolCall]) -> tuple[list[ToolCall], list[tuple[ToolCall, PermissionDecision]]]:
        """Filter calls through permission pipeline. Returns (allowed, denied)."""
        allowed, denied = [], []
        for tc in calls:
            decision = self.perm_pipe.check(tc.name, tc.args)
            self.permission_decisions.append(decision)
            if decision.allowed:
                allowed.append(tc)
            else:
                denied.append((tc, decision))
        return allowed, denied

    def execute_calls(self, calls: list[ToolCall], executor_fn) -> dict[str, BatchResult]:
        """Partition and execute tool calls via orchestrator."""
        batches = self.orch.partition(calls)
        results = self.orch.execute(batches, executor_fn)
        self.all_tool_calls.extend(calls)
        self.all_results.update(results)
        return results

    def process_results(self, calls: list[ToolCall], results: dict[str, BatchResult]) -> list[ProcessedResult]:
        """Process all results through the result manager."""
        processed = []
        for tc in calls:
            br = results[tc.id]
            if br.error is None:
                pr = self.result_mgr.process(tc.name, br.result)
                processed.append(pr)
        return processed

    def run_post_turn_hooks(self, user_msg: str, assistant_msg: str,
                             tool_calls_data: list[dict], tool_results_data: list[dict]) -> list[HookResult]:
        """Run all post-turn hooks for a turn."""
        ctx = HookContext(
            messages=list(self.messages),
            user_message=user_msg,
            assistant_message=assistant_msg,
            tool_calls=tool_calls_data,
            tool_results=tool_results_data,
            session_id="sim-session-001",
            turn_number=self.turn_count,
        )
        results = run_async(self.hook_pipeline.run_all(ctx))
        self.hook_results_per_turn.append(results)
        return results

    def check_pressure(self) -> float:
        """Check context pressure and record it."""
        should, reason = self.compressor.should_compress(self.messages)
        pressure = self.compressor.monitor.current
        self.pressure_history.append(pressure)
        return pressure


# ---------------------------------------------------------------------------
# Build the 5-turn simulation
# ---------------------------------------------------------------------------

def build_5_turn_session() -> SimulatedSession:
    """Execute a full 5-turn coding session and return the session state."""

    session = SimulatedSession(model_token_limit=200_000)

    # ── Turn 1: User asks to fix auth bug → read 3 files concurrently ──
    session.add_user_message(
        "I prefer using bcrypt for password hashing. Can you fix the auth bug?"
    )

    turn1_calls = [
        ToolCall(name="read_file", args={"path": "/app/auth.py"}, id="r1_auth"),
        ToolCall(name="read_file", args={"path": "/app/models/user.py"}, id="r1_user"),
        ToolCall(name="read_file", args={"path": "/app/config.py"}, id="r1_config"),
    ]
    allowed, denied = session.check_permissions(turn1_calls)
    assert len(allowed) == 3, "All reads should be auto-approved"

    executor1 = make_executor({
        "read_file": "def authenticate(user, password):\n    return bcrypt.checkpw(password, user.hash)",
    })
    turn1_results = session.execute_calls(turn1_calls, executor1)
    turn1_processed = session.process_results(turn1_calls, turn1_results)

    # Build tool data for hooks
    tool_calls_data = [{"name": "read_file", "args": {"path": tc.args["path"]}} for tc in turn1_calls]
    tool_results_data = [{"content": turn1_results[tc.id].result} for tc in turn1_calls]

    session.add_assistant_message(
        "I can see the auth bug. The password comparison uses == instead of bcrypt.checkpw. "
        "Let me search for all occurrences."
    )
    session.add_tool_results([{"role": "tool", "name": "read_file", "content": r.content} for r in turn1_processed])

    turn1_hooks = session.run_post_turn_hooks(
        session.messages[1]["content"],
        "I can see the auth bug. The password comparison uses == instead of bcrypt.checkpw. "
        "Let me search for all occurrences.",
        tool_calls_data,
        tool_results_data,
    )
    session.check_pressure()
    session.turn_count = 1

    # ── Turn 2: Agent searches codebase → 2 concurrent searches ──
    session.add_user_message("Find all places where password comparison happens.")

    turn2_calls = [
        ToolCall(name="search_files", args={"pattern": "password.*==", "path": "/app"}, id="s1_pw"),
        ToolCall(name="search_files", args={"pattern": "bcrypt", "path": "/app"}, id="s2_bcrypt"),
    ]
    allowed2, denied2 = session.check_permissions(turn2_calls)
    assert len(allowed2) == 2

    executor2 = make_executor({
        "search_files": "/app/auth.py:42:    if password == user.hash:\n/app/auth.py:78:    return password == stored_hash",
    })
    turn2_results = session.execute_calls(turn2_calls, executor2)
    turn2_processed = session.process_results(turn2_calls, turn2_results)

    tool_calls_data2 = [{"name": "search_files", "args": tc.args} for tc in turn2_calls]
    tool_results_data2 = [{"content": turn2_results[tc.id].result} for tc in turn2_calls]

    session.add_assistant_message(
        "Found 2 occurrences. I'll fix them to use bcrypt.checkpw."
    )
    session.add_tool_results([{"role": "tool", "name": "search_files", "content": r.content} for r in turn2_processed])

    turn2_hooks = session.run_post_turn_hooks(
        "Find all places where password comparison happens.",
        "Found 2 occurrences. I'll fix them to use bcrypt.checkpw.",
        tool_calls_data2,
        tool_results_data2,
    )
    session.check_pressure()
    session.turn_count = 2

    # ── Turn 3: Agent edits auth.py → permission check + serial write ──
    session.add_user_message("Go ahead and fix it.")

    turn3_calls = [
        ToolCall(name="write_file", args={"path": "/app/auth.py", "content": "import bcrypt\n\ndef authenticate(user, password):\n    return bcrypt.checkpw(password.encode(), user.hash.encode())"}, id="w1_auth"),
    ]
    allowed3, denied3 = session.check_permissions(turn3_calls)
    # write_file is PROMPT level — needs confirmation, so not auto-allowed
    assert len(allowed3) == 0, "write_file should need prompt"
    assert len(denied3) == 1
    assert denied3[0][1].needs_prompt is True

    # Simulate user approving the write
    # Now re-check with approval (in real agent, user would approve)
    # For simulation, we execute the write directly
    executor3 = make_executor({"write_file": "File /app/auth.py written successfully (4 lines)"})
    # Execute via orchestrator (single write = single batch)
    batches3 = session.orch.partition(turn3_calls)
    assert len(batches3) == 1, "Single write = single batch"
    assert len(batches3[0]) == 1, "Single write = single call in batch"
    turn3_results = session.orch.execute(batches3, executor3)
    turn3_processed = session.process_results(turn3_calls, turn3_results)
    session.all_tool_calls.extend(turn3_calls)
    session.all_results.update(turn3_results)

    tool_calls_data3 = [{"name": "write_file", "args": tc.args} for tc in turn3_calls]
    tool_results_data3 = [{"content": turn3_results[tc.id].result} for tc in turn3_calls]

    session.add_assistant_message(
        "Fixed auth.py to use bcrypt.checkpw. Let me run the tests."
    )
    session.add_tool_results([{"role": "tool", "name": "write_file", "content": r.content} for r in turn3_processed])

    turn3_hooks = session.run_post_turn_hooks(
        "Go ahead and fix it.",
        "Fixed auth.py to use bcrypt.checkpw. Let me run the tests.",
        tool_calls_data3,
        tool_results_data3,
    )
    session.check_pressure()
    session.turn_count = 3

    # ── Turn 4: Agent runs tests → terminal (permission prompt) ──
    session.add_user_message("Yes, run the tests.")

    turn4_calls = [
        ToolCall(name="terminal", args={"command": "cd /app && python -m pytest tests/test_auth.py -v"}, id="t1_test"),
    ]
    allowed4, denied4 = session.check_permissions(turn4_calls)
    # terminal is PROMPT level (not dangerous, but needs confirmation)
    assert len(allowed4) == 0
    assert len(denied4) == 1
    assert denied4[0][1].needs_prompt is True
    assert denied4[0][1].level == PermissionLevel.PROMPT

    # Simulate user approving
    executor4 = make_executor({"terminal": "tests/test_auth.py::test_authenticate PASSED\ntests/test_auth.py::test_hash_password PASSED\n\n2 passed, 0 failed"})
    batches4 = session.orch.partition(turn4_calls)
    turn4_results = session.orch.execute(batches4, executor4)
    turn4_processed = session.process_results(turn4_calls, turn4_results)
    session.all_tool_calls.extend(turn4_calls)
    session.all_results.update(turn4_results)

    tool_calls_data4 = [{"name": "terminal", "args": tc.args} for tc in turn4_calls]
    tool_results_data4 = [{"content": turn4_results[tc.id].result} for tc in turn4_calls]

    session.add_assistant_message(
        "All tests pass. Let me also write a test for the bcrypt verification path."
    )
    session.add_tool_results([{"role": "tool", "name": "terminal", "content": r.content} for r in turn4_processed])

    turn4_hooks = session.run_post_turn_hooks(
        "Yes, run the tests.",
        "All tests pass. Let me also write a test for the bcrypt verification path.",
        tool_calls_data4,
        tool_results_data4,
    )
    session.check_pressure()
    session.turn_count = 4

    # ── Turn 5: Agent writes test file → serial write ──
    session.add_user_message("Good idea, go ahead.")

    turn5_calls = [
        ToolCall(name="write_file", args={"path": "/app/tests/test_auth.py", "content": "import pytest\nfrom auth import authenticate\n\ndef test_bcrypt_verify():\n    ..."}, id="w2_test"),
    ]
    allowed5, denied5 = session.check_permissions(turn5_calls)
    assert len(allowed5) == 0
    assert len(denied5) == 1

    executor5 = make_executor({"write_file": "File /app/tests/test_auth.py written successfully"})
    batches5 = session.orch.partition(turn5_calls)
    assert len(batches5) == 1
    turn5_results = session.orch.execute(batches5, executor5)
    turn5_processed = session.process_results(turn5_calls, turn5_results)
    session.all_tool_calls.extend(turn5_calls)
    session.all_results.update(turn5_results)

    tool_calls_data5 = [{"name": "write_file", "args": tc.args} for tc in turn5_calls]
    tool_results_data5 = [{"content": turn5_results[tc.id].result} for tc in turn5_calls]

    session.add_assistant_message(
        "Done! Auth bug is fixed and test coverage is improved."
    )
    session.add_tool_results([{"role": "tool", "name": "write_file", "content": r.content} for r in turn5_processed])

    turn5_hooks = session.run_post_turn_hooks(
        "Good idea, go ahead.",
        "Done! Auth bug is fixed and test coverage is improved.",
        tool_calls_data5,
        tool_results_data5,
    )
    session.check_pressure()
    session.turn_count = 5

    return session


# ===========================================================================
# TEST SCENARIOS
# ===========================================================================


class TestFullAgentSimulation:
    """All 15 test scenarios for the full-agent simulation."""

    @pytest.fixture()
    def session(self):
        """Build the 5-turn session once per test."""
        return build_5_turn_session()

    # ------------------------------------------------------------------
    # 1. Full 5-turn flow completes
    # ------------------------------------------------------------------
    def test_01_full_5_turn_flow_completes(self, session):
        """All 5 turns execute without errors; session state is consistent."""
        s = session
        assert s.turn_count == 5
        assert len(s.permission_decisions) > 0
        assert len(s.all_results) > 0
        assert len(s.hook_results_per_turn) == 5
        assert len(s.pressure_history) == 5

        # Every turn produced hook results
        for turn_hooks in s.hook_results_per_turn:
            assert len(turn_hooks) > 0
            for hr in turn_hooks:
                assert hr.success is True

    # ------------------------------------------------------------------
    # 2. Permission blocks dangerous terminal in turn 4
    # ------------------------------------------------------------------
    def test_02_permission_blocks_dangerous_terminal(self, session):
        """A dangerous 'rm -rf /' command is DENIED by the permission pipeline."""
        pp = PermissionPipeline()

        # Dangerous command
        d_danger = pp.check("terminal", {"command": "rm -rf /"})
        assert d_danger.allowed is False
        assert d_danger.level == PermissionLevel.DENY
        assert d_danger.needs_prompt is False

        # Safe terminal command (pytest) needs PROMPT but is not DENY
        d_safe = pp.check("terminal", {"command": "cd /app && python -m pytest tests/test_auth.py -v"})
        assert d_safe.allowed is False  # not auto-allowed
        assert d_safe.level == PermissionLevel.PROMPT
        assert d_safe.needs_prompt is True

        # dd if= is also dangerous
        d_dd = pp.check("terminal", {"command": "dd if=/dev/zero of=/dev/sda"})
        assert d_dd.allowed is False
        assert d_dd.level == PermissionLevel.DENY

    # ------------------------------------------------------------------
    # 3. Orchestrator batches reads in turn 1 (1 batch)
    # ------------------------------------------------------------------
    def test_03_orchestrator_batches_reads_in_turn1(self, session):
        """All 3 read_file calls in turn 1 are in a single concurrent batch."""
        calls = [
            ToolCall(name="read_file", args={"path": "/app/auth.py"}, id="r1"),
            ToolCall(name="read_file", args={"path": "/app/models/user.py"}, id="r2"),
            ToolCall(name="read_file", args={"path": "/app/config.py"}, id="r3"),
        ]
        orch = ToolOrchestrator(max_workers=8)
        batches = orch.partition(calls)

        # All reads go in one batch
        assert len(batches) == 1
        assert len(batches[0]) == 3
        assert all(tc.name == "read_file" for tc in batches[0])

    # ------------------------------------------------------------------
    # 4. Orchestrator serializes writes in turn 3
    # ------------------------------------------------------------------
    def test_04_orchestrator_serializes_writes(self, session):
        """Multiple write_file calls are each in their own batch (serialized)."""
        calls = [
            ToolCall(name="write_file", args={"path": "/app/a.py"}, id="w1"),
            ToolCall(name="write_file", args={"path": "/app/b.py"}, id="w2"),
            ToolCall(name="write_file", args={"path": "/app/c.py"}, id="w3"),
        ]
        orch = ToolOrchestrator(max_workers=8)
        batches = orch.partition(calls)

        # Each write in its own batch
        assert len(batches) == 3
        for batch in batches:
            assert len(batch) == 1
            assert batch[0].name == "write_file"

    # ------------------------------------------------------------------
    # 5. Result manager deduplicates repeated file reads
    # ------------------------------------------------------------------
    def test_05_result_manager_deduplicates_repeated_reads(self, session):
        """Processing the same content twice → second is deduped."""
        rm = ToolResultManager()

        content = "def authenticate(user, password):\n    return bcrypt.checkpw(password, user.hash)"
        r1 = rm.process("read_file", content)
        r2 = rm.process("read_file", content)
        r3 = rm.process("read_file", content)

        assert r1.was_deduped is False
        assert r2.was_deduped is True
        assert r3.was_deduped is True
        assert r1.hash == r2.hash == r3.hash

        stats = rm.get_stats()
        assert stats["dedup_saves"] == 2
        assert stats["total_processed"] == 3

    # ------------------------------------------------------------------
    # 6. Memory system extracts user preference from turn 1
    # ------------------------------------------------------------------
    def test_06_memory_extracts_user_preference(self, session):
        """The memory system extracts user preferences like 'I prefer bcrypt'."""
        extractor = MemoryExtractor()

        messages = [
            {"role": "user", "content": "I prefer using bcrypt for password hashing. Can you fix the auth bug?"},
            {"role": "assistant", "content": "I'll fix it using bcrypt.checkpw."},
            {"role": "user", "content": "Remember that my auth module is in /app/auth.py"},
        ]

        entries = extractor.extract_from_conversation(messages)

        # Should find at least one USER-type memory
        user_entries = [e for e in entries if e.type == MemoryType.USER]
        assert len(user_entries) >= 1

        # Should contain the bcrypt preference
        bcrypt_found = any("bcrypt" in e.content.lower() for e in user_entries)
        assert bcrypt_found, "Should extract bcrypt preference"

        # Store and search
        store = MemoryStore(max_entries=100)
        for e in entries:
            store.add(e)

        results = store.search("bcrypt preference")
        assert len(results) > 0

    # ------------------------------------------------------------------
    # 7. Context pressure increases over turns
    # ------------------------------------------------------------------
    def test_07_context_pressure_increases_over_turns(self, session):
        """As messages accumulate, context pressure increases monotonically."""
        pressures = session.pressure_history
        assert len(pressures) == 5

        # Each turn adds messages, so pressure should increase
        # (at least the last should be >= first)
        assert pressures[-1] >= pressures[0]

        # All pressures should be valid ratios
        for p in pressures:
            assert 0.0 <= p <= 1.0

    # ------------------------------------------------------------------
    # 8. Compression triggers when pressure high
    # ------------------------------------------------------------------
    def test_08_compression_triggers_when_pressure_high(self, session):
        """When messages are large enough, compressor recommends compression."""
        # Build a conversation that exceeds the balanced threshold (0.75)
        model_limit = 2000  # very small limit
        compressor = ContextCompressorV2(model_token_limit=model_limit, profile="balanced")

        # Generate lots of messages to exceed threshold
        messages = [{"role": "system", "content": "You are a helpful coding assistant."}]
        for i in range(50):
            messages.append({"role": "user", "content": f"Message {i}: {'x' * 200}"})
            messages.append({"role": "assistant", "content": f"Response {i}: {'y' * 200}"})
            messages.append({"role": "tool", "name": "read_file", "content": f"Tool output {i}: {'z' * 200}"})

        should, reason = compressor.should_compress(messages)
        assert should is True, f"Should trigger compression with small limit, got: {reason}"
        assert "exceeds" in reason.lower() or "critical" in reason.lower()

        # Actually compress
        result = compressor.compress(messages, level="auto")
        assert result.compressed_tokens < result.original_tokens
        assert result.ratio < 1.0

    # ------------------------------------------------------------------
    # 9. Post-turn hooks run in priority order
    # ------------------------------------------------------------------
    def test_09_post_turn_hooks_run_in_priority_order(self, session):
        """Hooks execute in ascending priority order."""
        pipeline = HookPipeline()

        # Register hooks in reverse order
        pipeline.register(ContextHealthHook())      # priority 40
        pipeline.register(PromptSuggestionHook())    # priority 30
        pipeline.register(UsageTrackingHook())       # priority 20
        pipeline.register(MemoryExtractionHook())    # priority 10

        hooks_meta = pipeline.get_hooks()
        priorities = [h["priority"] for h in hooks_meta]

        # Should be sorted ascending
        assert priorities == sorted(priorities)
        assert priorities == [10, 20, 30, 40]

        # Verify names match expected order
        names = [h["name"] for h in hooks_meta]
        assert names == ["memory_extraction", "usage_tracking", "prompt_suggestion", "context_health"]

        # Actually run them and check execution order
        ctx = HookContext(
            messages=[{"role": "user", "content": "I prefer Python"}],
            user_message="I prefer Python",
            assistant_message="Sure!",
            tool_calls=[],
            tool_results=[],
            session_id="test",
            turn_number=1,
        )
        results = run_async(pipeline.run_all(ctx))

        result_names = [r.hook_name for r in results]
        assert result_names == ["memory_extraction", "usage_tracking", "prompt_suggestion", "context_health"]

    # ------------------------------------------------------------------
    # 10. Usage tracking counts tools correctly
    # ------------------------------------------------------------------
    def test_10_usage_tracking_counts_tools_correctly(self, session):
        """UsageTrackingHook correctly counts tool calls across turns."""
        hook = UsageTrackingHook()

        # Turn 1: 3 tool calls
        ctx1 = HookContext(
            tool_calls=[{"name": "read_file"}, {"name": "read_file"}, {"name": "read_file"}],
            tool_results=[{"content": "a"}, {"content": "b"}, {"content": "c"}],
            user_message="fix auth",
            assistant_message="reading files",
            messages=[],
            turn_number=1,
        )
        r1 = run_async(hook.execute(ctx1))
        assert r1.success
        assert r1.data["turn_tool_calls"] == 3
        assert r1.data["cumulative"]["total_turns"] == 1
        assert r1.data["cumulative"]["total_tool_calls"] == 3

        # Turn 2: 2 tool calls
        ctx2 = HookContext(
            tool_calls=[{"name": "search_files"}, {"name": "search_files"}],
            tool_results=[{"content": "d"}, {"content": "e"}],
            user_message="search",
            assistant_message="searching",
            messages=[],
            turn_number=2,
        )
        r2 = run_async(hook.execute(ctx2))
        assert r2.success
        assert r2.data["turn_tool_calls"] == 2
        assert r2.data["cumulative"]["total_turns"] == 2
        assert r2.data["cumulative"]["total_tool_calls"] == 5

        # Turn 3: 1 tool call
        ctx3 = HookContext(
            tool_calls=[{"name": "write_file"}],
            tool_results=[{"content": "written"}],
            user_message="fix it",
            assistant_message="writing",
            messages=[],
            turn_number=3,
        )
        r3 = run_async(hook.execute(ctx3))
        assert r3.data["cumulative"]["total_turns"] == 3
        assert r3.data["cumulative"]["total_tool_calls"] == 6

    # ------------------------------------------------------------------
    # 11. Prompt suggestions generated after edit
    # ------------------------------------------------------------------
    def test_11_prompt_suggestions_after_edit(self, session):
        """PromptSuggestionHook suggests running tests after file edits."""
        hook = PromptSuggestionHook()

        ctx = HookContext(
            tool_calls=[{"name": "write_file", "args": {"path": "/app/auth.py"}}],
            tool_results=[{"content": "File written successfully"}],
            user_message="fix it",
            assistant_message="I edited /app/auth.py to fix the bug.",
            messages=[],
            turn_number=3,
        )
        result = run_async(hook.execute(ctx))

        assert result.success
        suggestions = result.data["suggestions"]
        assert len(suggestions) > 0

        # Should mention tests or linting after edit
        has_relevant_suggestion = any(
            "test" in s.lower() or "lint" in s.lower() or "edited" in s.lower()
            for s in suggestions
        )
        assert has_relevant_suggestion, f"Expected test/lint suggestion, got: {suggestions}"

        # Should detect edited files
        edited = result.data["edited_files"]
        assert "/app/auth.py" in edited

    # ------------------------------------------------------------------
    # 12. Auto-dream doesn't trigger (below threshold)
    # ------------------------------------------------------------------
    def test_12_auto_dream_below_threshold(self, session):
        """Auto-dream doesn't trigger when session count < threshold."""
        store = MemoryStore(max_entries=100)
        trigger = DreamTrigger(session_threshold=5, time_threshold_hours=24)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)

        # Reset last dream to now so time threshold is NOT met
        dreamer._last_dream = datetime.now(timezone.utc)

        # Record only 2 sessions (below threshold of 5)
        for i in range(2):
            summary = SessionSummary(
                key_decisions=["use bcrypt"],
                tools_used={"read_file": 3, "write_file": 1},
                topics=["auth", "security"],
            )
            dreamer.record_session(summary)

        assert dreamer.should_dream() is False
        assert dreamer._session_count == 2

    # ------------------------------------------------------------------
    # 13. Auto-dream triggers after enough sessions
    # ------------------------------------------------------------------
    def test_13_auto_dream_triggers_after_enough_sessions(self, session):
        """Auto-dream triggers when session count >= threshold."""
        store = MemoryStore(max_entries=100)
        trigger = DreamTrigger(session_threshold=5, time_threshold_hours=999999)  # disable time trigger
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)

        # Record 5 sessions (at threshold)
        for i in range(5):
            summary = SessionSummary(
                key_decisions=[f"decision {i}"],
                errors_fixed=[f"error {i}"],
                tools_used={"read_file": 2},
                topics=["coding"],
                user_preferences=["Python"],
            )
            dreamer.record_session(summary)

        assert dreamer.should_dream() is True

        # Actually run the dream
        report = dreamer.dream()
        assert isinstance(report, DreamReport)
        assert report.sessions_reviewed == 5
        assert report.memories_created >= 1  # Should create episodic memories

        # Store should have new entries
        assert len(store.entries) >= 1

        # After dream, session count resets
        assert dreamer._session_count == 0
        assert dreamer.should_dream() is False

    # ------------------------------------------------------------------
    # 14. Coordinator decomposes complex task
    # ------------------------------------------------------------------
    def test_14_coordinator_decomposes_complex_task(self, session):
        """Coordinator decomposes a complex objective into sub-tasks and executes."""
        coordinator = Coordinator()

        objective = (
            "Fix the authentication bug in auth.py; "
            "then search for similar issues in other modules; "
            "also write tests to prevent regression"
        )

        tasks = coordinator.plan(objective)
        assert len(tasks) >= 2, f"Expected multiple sub-tasks, got {len(tasks)}"

        # Each task should have required_capabilities
        for task in tasks:
            assert len(task.required_capabilities) > 0

        # Assign tasks to agents
        assignments = coordinator.assign(tasks)
        assert len(assignments) > 0

        # Verify tasks got assigned
        assigned_tasks = [t for t in tasks if t.status == TaskStatus.ASSIGNED]
        assert len(assigned_tasks) >= 1

        # Execute with a mock executor
        def mock_executor(task: TaskSpec) -> dict:
            return {"status": "done", "output": f"Completed: {task.description}"}

        coordinator.execute(tasks, mock_executor)

        # Check execution results
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        assert len(completed) >= 1

        # Aggregate results
        agg = coordinator.aggregator.aggregate(tasks)
        assert isinstance(agg, AggregatedResult)
        assert "completed" in agg.summary.lower() or "tasks" in agg.summary.lower()

    # ------------------------------------------------------------------
    # 15. All modules work together without errors
    # ------------------------------------------------------------------
    def test_15_all_modules_work_together(self, session):
        """All 8 modules integrated without errors in a full pipeline."""
        s = session

        # ── Orchestrator: partitioned and executed all calls ──
        assert len(s.all_results) > 0
        for tid, br in s.all_results.items():
            assert isinstance(br, BatchResult)
            assert br.error is None

        # ── Permission Pipeline: checked all calls ──
        assert len(s.permission_decisions) > 0
        for d in s.permission_decisions:
            assert isinstance(d, PermissionDecision)

        # ── Result Manager: processed results ──
        stats = s.result_mgr.get_stats()
        assert stats["total_processed"] > 0

        # ── Context Compressor: tracked pressure ──
        compressor_stats = s.compressor.get_stats()
        assert "compressions_count" in compressor_stats
        assert len(s.pressure_history) == 5

        # ── Memory System: extractable content exists ──
        user_messages = [m for m in s.messages if m.get("role") == "user"]
        assert len(user_messages) == 5

        # Extract memories from the full conversation
        entries = s.memory_extractor.extract_from_conversation(s.messages)
        user_memories = [e for e in entries if e.type == MemoryType.USER]
        assert len(user_memories) >= 1, "Should extract at least one user preference"

        # Store and inject
        for e in entries:
            s.memory_store.add(e)
        context = s.memory_injector.prepare_context(s.memory_store.entries, max_tokens=2000)
        assert "Memory Context" in context

        # ── Post-Turn Hooks: all ran successfully ──
        assert len(s.hook_results_per_turn) == 5
        for turn_hooks in s.hook_results_per_turn:
            for hr in turn_hooks:
                assert isinstance(hr, HookResult)
                assert hr.success is True, f"Hook {hr.hook_name} failed: {hr.error}"

        # ── Auto-Dream: record and trigger ──
        summary = SessionSummary(
            key_decisions=["use bcrypt for auth"],
            errors_fixed=["auth password comparison"],
            tools_used={"read_file": 3, "search_files": 2, "write_file": 2, "terminal": 1},
            topics=["auth", "bcrypt", "security", "testing"],
            user_preferences=["bcrypt for password hashing"],
        )
        s.dreamer.record_session(summary)
        # Not enough sessions yet to dream
        assert s.dreamer.should_dream() is False

        # ── Coordinator: decompose and execute ──
        coord = Coordinator()
        tasks = coord.plan(
            "Review auth changes; "
            "run integration tests; "
            "deploy to staging"
        )
        assert len(tasks) >= 2
        coord.assign(tasks)

        def executor(task: TaskSpec) -> dict:
            return {"result": "ok"}

        coord.execute(tasks, executor)
        agg = coord.aggregator.aggregate(tasks)
        assert isinstance(agg, AggregatedResult)

        # ── Final sanity: no exceptions, session is consistent ──
        assert s.turn_count == 5
        assert len(s.messages) > 5  # system + 5 user + 5 assistant + tool results
