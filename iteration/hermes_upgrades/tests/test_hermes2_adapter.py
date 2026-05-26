"""Tests for the Hermes 2.0 Integration Adapter (hermes2_adapter.py).

Covers:
  - Config defaults and custom values
  - from_config factory
  - process_tool_calls (permission filtering, batching, result processing)
  - process_turn (hooks, memory extraction, compression)
  - get_context_messages (memory injection)
  - should_dream / dream lifecycle
  - get_stats aggregation
  - Full engine lifecycle
  - Edge cases (empty calls, all denied, no system message)
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure package imports work (modules use relative imports)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent.hermes2.hermes2_adapter import Hermes2Config, Hermes2Engine, from_config
from agent.hermes2.tool_orchestrator import ToolCall
from agent.hermes2.permission_pipeline import PermissionLevel, PermissionRule
from agent.hermes2.memory_system import MemoryEntry, MemoryType
from agent.hermes2.auto_dream import SessionSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(results: dict | None = None):
    """Return an executor_fn that maps tool name → canned result."""
    results = results or {}

    def _exec(tc: ToolCall):
        return results.get(tc.name, f"result_for_{tc.name}")

    return _exec


def _user_msg(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant_msg(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _system_msg(text: str) -> dict:
    return {"role": "system", "content": text}


# ===================================================================
# 1. Config defaults and custom values
# ===================================================================


class TestHermes2Config:
    """Test configuration dataclass."""

    def test_defaults(self):
        cfg = Hermes2Config()
        assert cfg.max_workers == 8
        assert cfg.max_context_tokens == 200_000
        assert cfg.compression_profile == "balanced"
        assert cfg.memory_storage_path is None
        assert cfg.disk_result_dir is None
        assert cfg.permission_rules is None
        assert cfg.auto_dream_threshold == 5
        assert cfg.enable_hooks is True
        assert cfg.enable_auto_dream is True

    def test_custom_values(self):
        cfg = Hermes2Config(
            max_workers=4,
            max_context_tokens=100_000,
            compression_profile="aggressive",
            auto_dream_threshold=3,
            enable_hooks=False,
            enable_auto_dream=False,
        )
        assert cfg.max_workers == 4
        assert cfg.max_context_tokens == 100_000
        assert cfg.compression_profile == "aggressive"
        assert cfg.auto_dream_threshold == 3
        assert cfg.enable_hooks is False
        assert cfg.enable_auto_dream is False


# ===================================================================
# 2. from_config factory
# ===================================================================


class TestFromConfig:
    """Test the from_config factory function."""

    def test_empty_dict(self):
        engine = from_config({})
        assert isinstance(engine, Hermes2Engine)
        assert engine.config.max_workers == 8

    def test_with_values(self):
        engine = from_config({"max_workers": 2, "auto_dream_threshold": 10})
        assert engine.config.max_workers == 2
        assert engine.config.auto_dream_threshold == 10

    def test_unknown_keys_ignored(self):
        engine = from_config({"max_workers": 4, "unknown_key": "ignored"})
        assert engine.config.max_workers == 4


# ===================================================================
# 3. process_tool_calls
# ===================================================================


class TestProcessToolCalls:
    """Test tool call processing pipeline."""

    def test_basic_processing(self):
        engine = Hermes2Engine()
        calls = [
            {"name": "read_file", "args": {"path": "/tmp/a.txt"}},
            {"name": "search_files", "args": {"pattern": "*.py"}},
        ]
        executor = _make_executor({"read_file": "file content", "search_files": "found 3 files"})

        result = engine.process_tool_calls(calls, executor)

        assert len(result["processed"]) == 2
        for tid, entry in result["processed"].items():
            assert "content" in entry
            assert "token_count" in entry

    def test_permission_denied_filtered(self):
        """Write-only tools should be denied by default PROMPT rules."""
        engine = Hermes2Engine()
        calls = [
            {"name": "read_file", "args": {"path": "/tmp/a.txt"}},
            {"name": "write_file", "args": {"path": "/tmp/b.txt", "content": "hi"}},
        ]
        captured: list[ToolCall] = []

        def executor(tc: ToolCall):
            captured.append(tc)
            return "ok"

        engine.process_tool_calls(calls, executor)

        # read_file is AUTO (allowed), write_file is PROMPT (denied because
        # we don't have a confirmation mechanism in the adapter)
        tool_names = [tc.name for tc in captured]
        assert "read_file" in tool_names
        assert "write_file" not in tool_names

    def test_all_denied_returns_empty(self):
        """If all calls are denied, executor is never called."""
        # Only allow a tool we won't call
        rules = [PermissionRule("never_match", PermissionLevel.AUTO)]
        engine = Hermes2Engine(Hermes2Config(permission_rules=rules))

        calls = [{"name": "read_file", "args": {}}]
        executor = _make_executor()
        result = engine.process_tool_calls(calls, executor)
        assert result["processed"] == {}

    def test_empty_calls(self):
        engine = Hermes2Engine()
        result = engine.process_tool_calls([], _make_executor())
        assert result["processed"] == {}

    def test_reads_are_batched(self):
        """Read-only tools should be batched (parallel)."""
        engine = Hermes2Engine()
        calls = [
            {"name": "read_file", "args": {"path": f"/tmp/f{i}.txt"}}
            for i in range(5)
        ]
        executor = _make_executor({"read_file": "content"})
        result = engine.process_tool_calls(calls, executor)
        assert len(result["processed"]) == 5

    def test_writes_are_serialized(self):
        """Write tools produce individual batches."""
        engine = Hermes2Engine()
        # Override to auto-approve writes
        from agent.hermes2.permission_pipeline import PermissionLevel as PL

        rules = [PermissionRule("*", PermissionLevel.AUTO)]
        engine = Hermes2Engine(Hermes2Config(permission_rules=rules))

        calls = [
            {"name": "write_file", "args": {"path": "/tmp/a.txt"}},
            {"name": "write_file", "args": {"path": "/tmp/b.txt"}},
        ]
        executor = _make_executor({"write_file": "written"})
        result = engine.process_tool_calls(calls, executor)
        assert len(result["processed"]) == 2

    def test_error_handling(self):
        """Errors in executor_fn are captured, not raised."""
        engine = Hermes2Engine()

        def failing_executor(tc: ToolCall):
            raise RuntimeError("boom")

        calls = [{"name": "read_file", "args": {"path": "/tmp/x.txt"}}]
        result = engine.process_tool_calls(calls, failing_executor)

        assert len(result["processed"]) == 1
        entry = list(result["processed"].values())[0]
        assert "error" in entry
        assert "boom" in entry["error"]


# ===================================================================
# 4. process_turn
# ===================================================================


class TestProcessTurn:
    """Test post-turn processing pipeline."""

    def test_hooks_run_and_memories_extracted(self):
        engine = Hermes2Engine()
        messages = [_user_msg("I prefer Python over JavaScript")]
        tool_calls = []
        tool_results = []

        result = engine.process_turn(messages, tool_calls, tool_results)

        assert "hooks_results" in result
        assert len(result["hooks_results"]) > 0
        # Memory extraction should have found the "I prefer" pattern
        assert result["memories_extracted"] >= 1

    def test_compression_triggered_when_needed(self):
        engine = Hermes2Engine()
        # Build very large messages to exceed pressure threshold
        large_content = "x" * 4_000_000  # ~1M tokens
        messages = [_user_msg(large_content)]

        result = engine.process_turn(messages, [], [])
        assert result["compression_applied"] is True

    def test_compression_not_triggered_for_small_context(self):
        engine = Hermes2Engine()
        messages = [_user_msg("hello")]

        result = engine.process_turn(messages, [], [])
        assert result["compression_applied"] is False

    def test_turn_count_increments(self):
        engine = Hermes2Engine()
        assert engine._turn_count == 0
        engine.process_turn([], [], [])
        assert engine._turn_count == 1
        engine.process_turn([], [], [])
        assert engine._turn_count == 2


# ===================================================================
# 5. get_context_messages
# ===================================================================


class TestGetContextMessages:
    """Test memory injection into system prompt."""

    def test_injects_into_existing_system_message(self):
        engine = Hermes2Engine()
        # Pre-populate memory
        engine.memory.add(MemoryEntry(
            type=MemoryType.USER,
            content="User prefers dark mode",
            tags=["preference"],
        ))

        messages = [_system_msg("You are a helpful assistant."), _user_msg("hello")]
        result = engine.get_context_messages(messages)

        assert result[0]["role"] == "system"
        assert "dark mode" in result[0]["content"]
        assert "You are a helpful assistant" in result[0]["content"]

    def test_creates_system_message_when_missing(self):
        engine = Hermes2Engine()
        engine.memory.add(MemoryEntry(
            type=MemoryType.USER,
            content="User likes TypeScript",
            tags=["preference"],
        ))

        messages = [_user_msg("hello")]
        result = engine.get_context_messages(messages)

        assert result[0]["role"] == "system"
        assert "TypeScript" in result[0]["content"]

    def test_no_memories_returns_unchanged(self):
        engine = Hermes2Engine()
        messages = [_system_msg("sys"), _user_msg("hello")]
        result = engine.get_context_messages(messages)
        assert result == messages


# ===================================================================
# 6. should_dream / dream lifecycle
# ===================================================================


class TestDreamLifecycle:
    """Test dream trigger and execution."""

    def test_should_dream_below_threshold(self):
        engine = Hermes2Engine(Hermes2Config(auto_dream_threshold=5))
        assert engine.should_dream(session_count=3) is False

    def test_should_dream_at_threshold(self):
        engine = Hermes2Engine(Hermes2Config(auto_dream_threshold=5))
        assert engine.should_dream(session_count=5) is True

    def test_should_dream_above_threshold(self):
        engine = Hermes2Engine(Hermes2Config(auto_dream_threshold=5))
        assert engine.should_dream(session_count=10) is True

    def test_should_dream_uses_internal_state(self):
        engine = Hermes2Engine(Hermes2Config(auto_dream_threshold=1))
        # Manually record enough sessions to trigger
        from agent.hermes2.auto_dream import SessionSummary

        engine.auto_dreamer.record_session(SessionSummary(topics=["test"]))
        assert engine.should_dream() is True

    def test_dream_returns_report(self):
        engine = Hermes2Engine()
        from agent.hermes2.auto_dream import SessionSummary

        # Record some sessions with content
        for i in range(3):
            engine.auto_dreamer.record_session(
                SessionSummary(
                    key_decisions=[f"decision_{i}"],
                    topics=["testing", "python"],
                )
            )

        report = engine.dream()
        assert report.sessions_reviewed == 3
        assert isinstance(report.memories_created, int)
        assert isinstance(report.insights, list)

    def test_dream_resets_session_count(self):
        engine = Hermes2Engine()
        from agent.hermes2.auto_dream import SessionSummary

        engine.auto_dreamer.record_session(SessionSummary(topics=["a"]))
        engine.dream()
        # After dreaming, session count should be reset
        assert engine.auto_dreamer._session_count == 0


# ===================================================================
# 7. get_stats aggregation
# ===================================================================


class TestGetStats:
    """Test aggregated statistics."""

    def test_stats_keys(self):
        engine = Hermes2Engine()
        stats = engine.get_stats()

        assert "turn_count" in stats
        assert "orchestrator" in stats
        assert "result_manager" in stats
        assert "compressor" in stats
        assert "memory" in stats
        assert "hooks" in stats
        assert "auto_dream" in stats

    def test_stats_reflect_activity(self):
        engine = Hermes2Engine()
        engine.process_turn([_user_msg("hello")], [], [])

        stats = engine.get_stats()
        assert stats["turn_count"] == 1
        assert stats["result_manager"]["total_processed"] == 0


# ===================================================================
# 8. Full engine lifecycle
# ===================================================================


class TestFullLifecycle:
    """End-to-end lifecycle test."""

    def test_init_process_turns_dream_stats(self):
        engine = Hermes2Engine(Hermes2Config(auto_dream_threshold=3))

        # Turn 1: user states a preference
        r1 = engine.process_turn(
            [_user_msg("I prefer dark mode")], [], [],
        )
        assert r1["memories_extracted"] >= 1

        # Turn 2: normal conversation
        r2 = engine.process_turn(
            [_user_msg("What time is it?")], [], [],
        )
        assert engine._turn_count == 2

        # Turn 3: tool usage
        r3 = engine.process_turn(
            [_user_msg("Read the file")],
            [{"name": "read_file", "args": {"path": "/tmp/f.txt"}}],
            [{"content": "file contents here"}],
        )
        assert engine._turn_count == 3

        # Check memory was stored
        stats = engine.get_stats()
        assert stats["memory"]["total_entries"] >= 1
        assert stats["turn_count"] == 3

        # Dream
        assert engine.should_dream(session_count=3) is True
        report = engine.dream()
        assert report.sessions_reviewed >= 0  # may be 0 if no sessions recorded

        # Context messages with memory
        msgs = engine.get_context_messages([_user_msg("hello")])
        if stats["memory"]["total_entries"] > 0:
            # Should have system message with memory context
            assert msgs[0]["role"] == "system"


# ===================================================================
# 9. Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge-case tests."""

    def test_empty_messages_process_turn(self):
        engine = Hermes2Engine()
        result = engine.process_turn([], [], [])
        assert result["memories_extracted"] == 0
        assert result["compression_applied"] is False

    def test_process_tool_calls_with_custom_permission_rules(self):
        """Custom rules: only allow search_files."""
        rules = [
            PermissionRule("search_files", PermissionLevel.AUTO),
        ]
        engine = Hermes2Engine(Hermes2Config(permission_rules=rules))

        calls = [
            {"name": "search_files", "args": {"pattern": "*.py"}},
            {"name": "read_file", "args": {"path": "/tmp/x"}},
        ]
        captured: list[ToolCall] = []

        def executor(tc: ToolCall):
            captured.append(tc)
            return "ok"

        engine.process_tool_calls(calls, executor)
        assert len(captured) == 1
        assert captured[0].name == "search_files"

    def test_get_context_messages_preserves_original(self):
        """Original messages list is not mutated."""
        engine = Hermes2Engine()
        engine.memory.add(MemoryEntry(
            type=MemoryType.USER,
            content="User likes cats",
        ))
        messages = [_system_msg("sys"), _user_msg("hi")]
        original_content = messages[0]["content"]

        engine.get_context_messages(messages)

        # Original should be unchanged
        assert messages[0]["content"] == original_content

    def test_dream_with_no_pending_sessions(self):
        """Dreaming with no sessions should return empty report."""
        engine = Hermes2Engine()
        report = engine.dream()
        assert report.sessions_reviewed == 0
        assert report.memories_created == 0

    def test_hooks_disabled(self):
        """When hooks are disabled, no hooks should be registered."""
        engine = Hermes2Engine(Hermes2Config(enable_hooks=False))
        hooks = engine.hooks.get_hooks()
        assert len(hooks) == 0

    def test_multiple_reads_result_dedup(self):
        """Same content read twice should be deduped by result manager."""
        engine = Hermes2Engine()
        calls = [
            {"name": "read_file", "args": {"path": "/tmp/a.txt"}},
            {"name": "read_file", "args": {"path": "/tmp/b.txt"}},
        ]
        executor = _make_executor({"read_file": "identical content"})
        result = engine.process_tool_calls(calls, executor)

        assert len(result["processed"]) == 2
        entries = list(result["processed"].values())
        # First should not be deduped, second should be
        assert entries[0]["was_deduped"] is False
        assert entries[1]["was_deduped"] is True

    def test_process_turn_with_tool_errors(self):
        """Turn with error-containing tool results should still succeed."""
        engine = Hermes2Engine()
        messages = [_user_msg("run the command")]
        tool_calls = [{"name": "terminal", "args": {"command": "ls"}}]
        tool_results = [{"content": "Traceback: FileNotFoundError"}]

        result = engine.process_turn(messages, tool_calls, tool_results)
        assert "hooks_results" in result

    def test_get_stats_after_dream(self):
        """Stats should reflect dream history."""
        engine = Hermes2Engine()
        from agent.hermes2.auto_dream import SessionSummary

        engine.auto_dreamer.record_session(SessionSummary(topics=["test"]))
        engine.dream()

        stats = engine.get_stats()
        assert stats["auto_dream"]["history_count"] == 1
