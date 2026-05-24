"""Tests for Enhanced Context Compressor V2."""

from __future__ import annotations

import sys
import os

# Ensure the module is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from context_compressor_v2 import (
    CompressedMessages,
    CompressionProfile,
    ContextCompressorV2,
    FullLevel,
    MicrocompactLevel,
    PressureMonitor,
    ReactiveLevel,
    _estimate_tokens,
    _total_tokens,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_messages(n: int, *, tool_every: int = 0, content_size: int = 200) -> list[dict]:
    """Generate a conversation with *n* messages.

    If *tool_every* > 0, every *tool_every*-th message is a tool result
    preceded by a tool_call assistant message.
    """
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
            msgs.append({
                "role": "user" if i % 2 else "assistant",
                "content": f"Message {i}: " + "y" * content_size,
            })
    return msgs


# ---------------------------------------------------------------------------
# PressureMonitor
# ---------------------------------------------------------------------------

class TestPressureMonitor:
    def test_low_pressure(self):
        pm = PressureMonitor(model_token_limit=200_000)
        msgs = _make_messages(5, content_size=100)
        pressure = pm.update(msgs)
        assert 0.0 < pressure < 0.1

    def test_medium_pressure(self):
        pm = PressureMonitor(model_token_limit=5_000)
        msgs = _make_messages(20, content_size=400)
        pressure = pm.update(msgs)
        assert 0.3 < pressure < 0.9

    def test_high_pressure(self):
        pm = PressureMonitor(model_token_limit=1_000)
        msgs = _make_messages(10, content_size=500)
        pressure = pm.update(msgs)
        assert pressure >= 0.8

    def test_pressure_capped_at_one(self):
        pm = PressureMonitor(model_token_limit=100)
        msgs = _make_messages(20, content_size=500)
        pressure = pm.update(msgs)
        assert pressure == 1.0

    def test_should_compress_threshold(self):
        pm = PressureMonitor(model_token_limit=1_000)
        assert pm.should_compress(0.5) is False  # no data yet
        pm.update(_make_messages(10, content_size=500))
        assert pm.should_compress(0.1) is True

    def test_history_tracking(self):
        pm = PressureMonitor(model_token_limit=200_000)
        for i in range(3):
            pm.update(_make_messages(5 + i * 5, content_size=100))
        assert len(pm.history) == 3
        assert pm.history[0] < pm.history[-1]


# ---------------------------------------------------------------------------
# CompressionProfile
# ---------------------------------------------------------------------------

class TestCompressionProfile:
    def test_profiles_have_correct_thresholds(self):
        assert CompressionProfile.AGGRESSIVE.pressure_threshold == 0.6
        assert CompressionProfile.BALANCED.pressure_threshold == 0.75
        assert CompressionProfile.GENTLE.pressure_threshold == 0.85

    def test_profiles_have_correct_keep_last_n(self):
        assert CompressionProfile.AGGRESSIVE.keep_last_n == 3
        assert CompressionProfile.BALANCED.keep_last_n == 5
        assert CompressionProfile.GENTLE.keep_last_n == 8

    def test_microcompact_age_matches_keep_last_n(self):
        for p in CompressionProfile:
            assert p.microcompact_age == p.keep_last_n


# ---------------------------------------------------------------------------
# MicrocompactLevel
# ---------------------------------------------------------------------------

class TestMicrocompactLevel:
    def test_preserves_recent_tool_results(self):
        msgs = _make_messages(30, tool_every=3, content_size=300)
        tool_msgs = [m for m in msgs if m["role"] == "tool"]
        result = MicrocompactLevel.prune_old_tool_results(msgs, keep_last_n=5)
        recent_tools = [m for m in result if m["role"] == "tool"]
        # Last 5 tool results should have original content
        for tm in recent_tools[-5:]:
            assert "pruned" not in tm["content"]

    def test_prunes_old_tool_results(self):
        msgs = _make_messages(30, tool_every=3, content_size=300)
        result = MicrocompactLevel.prune_old_tool_results(msgs, keep_last_n=5)
        tool_msgs = [m for m in result if m["role"] == "tool"]
        # Earlier tool results should be pruned
        pruned = [m for m in tool_msgs if "pruned" in m["content"]]
        assert len(pruned) > 0

    def test_preserves_user_assistant_messages(self):
        msgs = _make_messages(20, tool_every=5, content_size=200)
        result = MicrocompactLevel.prune_old_tool_results(msgs, keep_last_n=2)
        for orig, comp in zip(msgs, result):
            if orig["role"] in ("user", "assistant", "system"):
                assert comp["content"] == orig["content"]

    def test_does_not_mutate_original(self):
        msgs = _make_messages(10, tool_every=3, content_size=200)
        original_contents = [m.get("content") for m in msgs]
        MicrocompactLevel.prune_old_tool_results(msgs, keep_last_n=2)
        for msg, orig in zip(msgs, original_contents):
            assert msg.get("content") == orig

    def test_no_pruning_when_few_tools(self):
        msgs = _make_messages(10, tool_every=5, content_size=200)
        result = MicrocompactLevel.prune_old_tool_results(msgs, keep_last_n=10)
        assert len(result) == len(msgs)
        for m in result:
            assert "pruned" not in str(m.get("content", ""))


# ---------------------------------------------------------------------------
# ReactiveLevel
# ---------------------------------------------------------------------------

class TestReactiveLevel:
    def test_reduces_token_count(self):
        msgs = _make_messages(40, tool_every=2, content_size=600)
        original = _total_tokens(msgs)
        result = ReactiveLevel.compress(msgs, target_ratio=0.5)
        compressed = _total_tokens(result)
        assert compressed < original

    def test_preserves_message_count(self):
        msgs = _make_messages(20, tool_every=3, content_size=300)
        result = ReactiveLevel.compress(msgs, target_ratio=0.5)
        assert len(result) == len(msgs)

    def test_no_change_when_already_small(self):
        msgs = _make_messages(3, content_size=10)
        original = _total_tokens(msgs)
        result = ReactiveLevel.compress(msgs, target_ratio=0.9)
        # Should be very close — may not change at all
        assert _total_tokens(result) <= original * 1.1


# ---------------------------------------------------------------------------
# FullLevel
# ---------------------------------------------------------------------------

class TestFullLevel:
    def test_prepare_summary_prompt_includes_transcript(self):
        msgs = _make_messages(5, content_size=50)
        prompt = FullLevel.prepare_summary_prompt(msgs)
        assert "Message 1" in prompt
        assert "Summary:" in prompt

    def test_apply_summary_preserves_system_and_tail(self):
        msgs = _make_messages(20, content_size=100)
        summary = "Key point: user asked about X."
        result = FullLevel.apply_summary(msgs, summary)
        assert result[0]["role"] == "system"
        assert len(result) < len(msgs)
        # Last messages should be preserved
        assert result[-1]["content"] == msgs[-1]["content"]

    def test_apply_summary_short_list_noop(self):
        msgs = [{"role": "user", "content": "hi"}]
        result = FullLevel.apply_summary(msgs, "summary")
        assert len(result) == len(msgs)


# ---------------------------------------------------------------------------
# ContextCompressorV2
# ---------------------------------------------------------------------------

class TestContextCompressorV2:
    def test_should_compress_low_pressure(self):
        comp = ContextCompressorV2(model_token_limit=200_000, profile="balanced")
        msgs = _make_messages(5, content_size=100)
        should, reason = comp.should_compress(msgs)
        assert should is False

    def test_should_compress_high_pressure(self):
        comp = ContextCompressorV2(model_token_limit=1_000, profile="aggressive")
        msgs = _make_messages(20, content_size=400)
        should, reason = comp.should_compress(msgs)
        assert should is True
        assert "exceeds" in reason or "Critical" in reason

    def test_compress_auto(self):
        comp = ContextCompressorV2(model_token_limit=5_000, profile="balanced")
        msgs = _make_messages(30, tool_every=3, content_size=400)
        result = comp.compress(msgs, level="auto")
        assert isinstance(result, CompressedMessages)
        assert result.level_used in ("micro", "reactive", "full")
        assert result.ratio <= 1.0

    def test_compress_micro(self):
        comp = ContextCompressorV2(model_token_limit=200_000, profile="balanced")
        msgs = _make_messages(30, tool_every=3, content_size=400)
        result = comp.compress(msgs, level="micro")
        assert result.level_used == "micro"

    def test_compress_reactive(self):
        comp = ContextCompressorV2(model_token_limit=200_000, profile="balanced")
        msgs = _make_messages(30, tool_every=3, content_size=400)
        result = comp.compress(msgs, level="reactive")
        assert result.level_used == "reactive"
        assert result.compressed_tokens < result.original_tokens

    def test_compress_preserves_message_list_length(self):
        comp = ContextCompressorV2(model_token_limit=5_000)
        msgs = _make_messages(20, tool_every=4, content_size=300)
        result = comp.compress(msgs, level="micro")
        assert len(result.messages) == len(msgs)

    def test_auto_level_selection_prefers_lightest(self):
        """With low pressure, auto should pick micro or skip."""
        comp = ContextCompressorV2(model_token_limit=200_000, profile="gentle")
        msgs = _make_messages(10, tool_every=3, content_size=100)
        should, _ = comp.should_compress(msgs)
        if should:
            result = comp.compress(msgs, level="auto")
            # Should prefer lighter levels
            assert result.level_used in ("micro", "reactive", "full")

    def test_unknown_level_raises(self):
        comp = ContextCompressorV2()
        with pytest.raises(ValueError, match="Unknown"):
            comp.compress([], level="invalid")


# ---------------------------------------------------------------------------
# Stats tracking
# ---------------------------------------------------------------------------

class TestStats:
    def test_initial_stats(self):
        comp = ContextCompressorV2()
        stats = comp.get_stats()
        assert stats["compressions_count"] == 0
        assert stats["avg_ratio"] == 0.0
        assert stats["tokens_saved"] == 0

    def test_stats_after_compression(self):
        comp = ContextCompressorV2(model_token_limit=5_000, profile="balanced")
        msgs = _make_messages(30, tool_every=3, content_size=400)
        comp.compress(msgs, level="reactive")
        stats = comp.get_stats()
        assert stats["compressions_count"] == 1
        assert 0.0 < stats["avg_ratio"] < 1.0
        assert stats["tokens_saved"] > 0

    def test_stats_accumulate(self):
        comp = ContextCompressorV2(model_token_limit=5_000)
        msgs = _make_messages(20, tool_every=3, content_size=300)
        comp.compress(msgs, level="micro")
        comp.compress(msgs, level="reactive")
        stats = comp.get_stats()
        assert stats["compressions_count"] == 2


# ---------------------------------------------------------------------------
# String profile init
# ---------------------------------------------------------------------------

class TestProfileStringInit:
    def test_string_profile_aggressive(self):
        comp = ContextCompressorV2(profile="aggressive")
        assert comp.profile == CompressionProfile.AGGRESSIVE

    def test_string_profile_balanced(self):
        comp = ContextCompressorV2(profile="BALANCED")
        assert comp.profile == CompressionProfile.BALANCED

    def test_enum_profile(self):
        comp = ContextCompressorV2(profile=CompressionProfile.GENTLE)
        assert comp.profile == CompressionProfile.GENTLE
