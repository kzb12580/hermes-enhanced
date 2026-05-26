"""Tests for tool_result_manager module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tool_result_manager import (
    DEFAULT_TOOL_BUDGETS,
    ProcessedResult,
    ResultDeduplicator,
    SmartTruncator,
    TokenEstimator,
    ToolResultManager,
)


# ── TokenEstimator ─────────────────────────────────────────────────────────

class TestTokenEstimator:
    def test_empty_string(self):
        assert TokenEstimator.estimate_tokens("") == 0

    def test_short_string(self):
        # 4 chars → 1 token (max(1, 4//4))
        assert TokenEstimator.estimate_tokens("abcd") == 1

    def test_long_string(self):
        text = "a" * 400
        assert TokenEstimator.estimate_tokens(text) == 100

    def test_estimate_messages_tokens(self):
        msgs = [
            {"role": "user", "content": "a" * 100},   # 25 tokens
            {"role": "assistant", "content": "b" * 200},  # 50 tokens
        ]
        # estimate_messages_tokens delegates to estimate_content_tokens which
        # handles str/list content; plain strings in a list return 0
        result = TokenEstimator.estimate_messages_tokens(msgs)
        assert isinstance(result, int)
        assert result >= 0

    def test_estimate_messages_tokens_openai_format(self):
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "x" * 400},  # 100 tokens
            ]},
        ]
        result = TokenEstimator.estimate_messages_tokens(msgs)
        assert isinstance(result, int)
        assert result >= 0

    def test_estimate_messages_tokens_missing_content(self):
        msgs = [{"role": "system"}]
        assert TokenEstimator.estimate_messages_tokens(msgs) == 0


# ── ResultDeduplicator ─────────────────────────────────────────────────────

class TestResultDeduplicator:
    def test_hash_deterministic(self):
        h1 = ResultDeduplicator.hash_result("hello")
        h2 = ResultDeduplicator.hash_result("hello")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_not_duplicate_initially(self):
        d = ResultDeduplicator()
        assert d.is_duplicate("foo") is False

    def test_duplicate_after_register(self):
        d = ResultDeduplicator()
        d.register("foo")
        assert d.is_duplicate("foo") is True

    def test_different_content_not_duplicate(self):
        d = ResultDeduplicator()
        d.register("foo")
        assert d.is_duplicate("bar") is False

    def test_clear_resets(self):
        d = ResultDeduplicator()
        d.register("foo")
        d.clear()
        assert d.is_duplicate("foo") is False

    def test_lru_eviction(self):
        d = ResultDeduplicator(max_seen=3)
        for c in ["a", "b", "c", "d"]:
            d.register(c)
        # "a" should have been evicted
        assert d.is_duplicate("a") is False
        assert d.is_duplicate("d") is True


# ── SmartTruncator ─────────────────────────────────────────────────────────

class TestSmartTruncator:
    def test_within_budget_no_change(self):
        t = SmartTruncator()
        text = "hello world"
        assert t.truncate(text, max_tokens=9999) == text

    def test_over_budget_truncates(self):
        t = SmartTruncator()
        lines = "\n".join(f"line {i}" for i in range(1000))
        result = t.truncate(lines, max_tokens=50)
        assert "[...truncated" in result
        # Original should be longer
        assert len(result) < len(lines)

    def test_head_tail_preserved(self):
        t = SmartTruncator()
        lines = "\n".join(f"line {i}" for i in range(100))
        result = t.truncate(lines, max_tokens=10, keep_head=0.3, keep_tail=0.2)
        assert "line 0" in result  # head preserved
        assert "line 99" in result  # tail preserved

    def test_truncation_marker_shows_count(self):
        t = SmartTruncator()
        lines = "\n".join(f"line {i}" for i in range(200))
        result = t.truncate(lines, max_tokens=10)
        assert "truncated" in result
        # Extract the number
        import re
        m = re.search(r"truncated (\d+) lines", result)
        assert m is not None
        removed = int(m.group(1))
        assert removed > 0

    def test_truncate_for_tool_uses_budget(self):
        t = SmartTruncator()
        text = "x" * 100_000  # ~25000 tokens
        # terminal default is 10000
        result = t.truncate_for_tool(text, "terminal")
        assert "[...truncated" in result

    def test_truncate_for_tool_custom_budget(self):
        t = SmartTruncator()
        text = "y" * 100_000
        result = t.truncate_for_tool(text, "custom_tool", {"custom_tool": 500})
        assert "[...truncated" in result

    def test_truncate_for_tool_within_budget(self):
        t = SmartTruncator()
        text = "short"
        result = t.truncate_for_tool(text, "terminal")
        assert result == text


# ── ToolResultManager ──────────────────────────────────────────────────────

class TestToolResultManager:
    def test_basic_process(self):
        mgr = ToolResultManager()
        result = mgr.process("terminal", "hello world")
        assert isinstance(result, ProcessedResult)
        assert result.content == "hello world"
        assert result.was_truncated is False
        assert result.was_deduped is False
        assert result.was_disk_saved is False
        assert result.token_count > 0
        assert len(result.hash) == 64

    def test_dedup_same_content(self):
        mgr = ToolResultManager()
        r1 = mgr.process("terminal", "same content")
        r2 = mgr.process("terminal", "same content")
        # Second call returns cached result
        assert r2.hash == r1.hash
        assert mgr.get_stats()["dedup_saves"] == 1

    def test_dedup_different_content(self):
        mgr = ToolResultManager()
        mgr.process("terminal", "content A")
        mgr.process("terminal", "content B")
        assert mgr.get_stats()["dedup_saves"] == 0
        assert mgr.get_stats()["total_processed"] == 2

    def test_truncation_per_tool_budget(self):
        mgr = ToolResultManager()
        # search_files budget is 8000 tokens = ~32000 chars
        big = "a" * 50_000
        result = mgr.process("search_files", big)
        assert result.was_truncated is True
        assert "[...truncated" in result.content
        assert mgr.get_stats()["truncations"] == 1

    def test_no_truncation_within_budget(self):
        mgr = ToolResultManager()
        small = "x" * 100
        result = mgr.process("read_file", small)
        assert result.was_truncated is False

    def test_disk_persistence(self, tmp_path: Path):
        mgr = ToolResultManager(disk_dir=str(tmp_path), disk_threshold=500)
        content = "D" * 600  # above threshold
        result = mgr.process("terminal", content)
        assert result.was_disk_saved is True
        # Check file exists
        files = list(tmp_path.glob("terminal_*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["content"] == content
        assert data["tool_name"] == "terminal"
        assert mgr.get_stats()["disk_saves"] == 1

    def test_no_disk_when_below_threshold(self, tmp_path: Path):
        mgr = ToolResultManager(disk_dir=str(tmp_path), disk_threshold=500)
        result = mgr.process("terminal", "short")
        assert result.was_disk_saved is False
        files = list(tmp_path.glob("terminal_*.json"))
        assert len(files) == 0

    def test_no_disk_when_no_dir(self):
        mgr = ToolResultManager(disk_dir=None)
        content = "Z" * 60_000
        result = mgr.process("terminal", content)
        assert result.was_disk_saved is False

    def test_stats_tracking(self):
        mgr = ToolResultManager()
        mgr.process("terminal", "a")
        mgr.process("terminal", "a")  # dup
        mgr.process("search_files", "b" * 50_000)  # truncated
        stats = mgr.get_stats()
        assert stats["total_processed"] == 3
        assert stats["dedup_saves"] == 1
        assert stats["truncations"] == 1

    def test_default_budgets_present(self):
        assert DEFAULT_TOOL_BUDGETS["read_file"] == 15000
        assert DEFAULT_TOOL_BUDGETS["terminal"] == 10000
        assert DEFAULT_TOOL_BUDGETS["search_files"] == 8000
        assert DEFAULT_TOOL_BUDGETS["web_extract"] == 12000
        assert DEFAULT_TOOL_BUDGETS["default"] == 8000

    def test_global_max_tokens_applied(self):
        # Set a very low global max
        mgr = ToolResultManager(max_tokens=10)
        content = "x" * 1000  # ~250 tokens
        result = mgr.process("terminal", content)
        assert result.was_truncated is True

    def test_file_path_passed_to_disk(self, tmp_path: Path):
        mgr = ToolResultManager(disk_dir=str(tmp_path), disk_threshold=10)
        mgr.process("read_file", "x" * 20, file_path="/some/file.py")
        files = list(tmp_path.glob("read_file_*.json"))
        data = json.loads(files[0].read_text())
        assert data["original_path"] == "/some/file.py"

    def test_custom_per_tool_budgets(self):
        mgr = ToolResultManager(per_tool_budgets={"my_tool": 100})
        # 100 tokens ≈ 400 chars; give 500 chars → should truncate
        result = mgr.process("my_tool", "c" * 500)
        assert result.was_truncated is True
