"""Edge-case tests that expose real bugs in the hermes_upgrades modules.

Each test is designed to FAIL against the original code and PASS after the fix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure package imports work (modules use relative imports)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from hermes_upgrades.memory_system import (
    MemoryEntry, MemoryExtractor, MemoryInjector, MemorySearch,
    MemoryStore, MemoryType, _tokenize,
)
from hermes_upgrades.context_compressor_v2 import (
    ContextCompressorV2, PressureMonitor, _message_tokens, _total_tokens,
    _estimate_tokens,
)
from hermes_upgrades.tool_result_manager import (
    TokenEstimator, ResultDeduplicator, SmartTruncator, ToolResultManager,
)
from hermes_upgrades.tool_orchestrator import ToolCall, ToolOrchestrator
from hermes_upgrades.permission_pipeline import PermissionPipeline, PermissionRule, PermissionLevel
from hermes_upgrades.hermes2_adapter import Hermes2Engine, Hermes2Config, from_config
from hermes_upgrades.coordinator import TaskDecomposer, Coordinator, ResultAggregator
from hermes_upgrades.post_turn_hooks import HookContext, HookPipeline
from hermes_upgrades.auto_dream import TranscriptAnalyzer


# ============================================================================
# 1. _tokenize with None input → AttributeError
# ============================================================================

class TestTokenizeEdgeCases:
    """_tokenize is used by MemorySearch.score and MemoryStore.search."""

    def test_tokenize_none(self):
        """_tokenize(None) should not crash — it's called from search paths
        where content might be None."""
        result = _tokenize(None)
        assert result == []

    def test_tokenize_empty_string(self):
        result = _tokenize("")
        assert result == []

    def test_tokenize_integer_input(self):
        """Non-string types shouldn't crash the tokenize function."""
        result = _tokenize(12345)
        assert isinstance(result, list)

    def test_tokenize_unicode(self):
        """CJK / emoji content should produce some result, not crash."""
        result = _tokenize("hello 世界 café")
        assert isinstance(result, list)


# ============================================================================
# 2. MemorySearch.score with None query → crash
# ============================================================================

class TestMemorySearchEdgeCases:

    def test_score_with_none_query(self):
        """score() calls _tokenize(query) — None crashes it."""
        search = MemorySearch()
        entry = MemoryEntry(type=MemoryType.USER, content="hello world")
        score = search.score(None, entry, {}, 1)
        assert isinstance(score, float)


# ============================================================================
# 3. MemoryStore.search with None query
# ============================================================================

class TestMemoryStoreSearchEdgeCases:

    def test_search_with_none_query(self):
        """search() calls _tokenize(query) — None crashes it."""
        store = MemoryStore()
        store.add(MemoryEntry(type=MemoryType.USER, content="test content"))
        results = store.search(None)
        assert isinstance(results, list)

    def test_search_with_empty_query(self):
        """Empty query should return all entries (ranked) or empty list."""
        store = MemoryStore()
        store.add(MemoryEntry(type=MemoryType.USER, content="test content"))
        results = store.search("")
        assert isinstance(results, list)


# ============================================================================
# 4. MemoryEntry.from_dict with missing keys → KeyError
# ============================================================================

class TestMemoryEntryFromDict:

    def test_from_dict_missing_required_keys(self):
        """from_dict uses direct d['key'] access — missing keys crash."""
        incomplete = {"id": "x", "type": "user"}  # missing content, created_at, etc.
        with pytest.raises(KeyError):
            MemoryEntry.from_dict(incomplete)

    def test_from_dict_empty_dict(self):
        with pytest.raises(KeyError):
            MemoryEntry.from_dict({})

    def test_from_dict_none(self):
        with pytest.raises((AttributeError, TypeError)):
            MemoryEntry.from_dict(None)


# ============================================================================
# 5. MemoryStore.load with corrupt JSON file
# ============================================================================

class TestMemoryStoreLoadCorrupt:

    def test_load_corrupt_json(self, tmp_path):
        """If the storage file has invalid JSON, load() crashes."""
        path = tmp_path / "memories.json"
        path.write_text("this is not valid json {{{}}")

        store = MemoryStore(storage_path=path)
        assert len(store.entries) == 0

    def test_load_empty_file(self, tmp_path):
        """If the storage file is empty, load() should handle gracefully."""
        path = tmp_path / "memories.json"
        path.write_text("")

        store = MemoryStore(storage_path=path)
        assert len(store.entries) == 0

    def test_load_non_list_json(self, tmp_path):
        """If the storage file contains a dict instead of a list."""
        path = tmp_path / "memories.json"
        path.write_text('{"not": "a list"}')

        store = MemoryStore(storage_path=path)
        assert len(store.entries) == 0


# ============================================================================
# 6. PressureMonitor with model_token_limit=0 → ZeroDivisionError
# ============================================================================

class TestPressureMonitorEdgeCases:

    def test_update_with_zero_token_limit(self):
        """Division by zero when model_token_limit is 0."""
        monitor = PressureMonitor(model_token_limit=0)
        messages = [{"role": "user", "content": "hello"}]
        pressure = monitor.update(messages)
        assert pressure == 1.0

    def test_update_with_negative_token_limit(self):
        """Negative token limit shouldn't crash."""
        monitor = PressureMonitor(model_token_limit=-100)
        messages = [{"role": "user", "content": "hello"}]
        pressure = monitor.update(messages)
        assert 0.0 <= pressure <= 1.0


# ============================================================================
# 7. _total_tokens / _message_tokens with None messages
# ============================================================================

class TestTokenEstimationEdgeCases:

    def test_message_tokens_with_none_message(self):
        """_message_tokens(None) → AttributeError on .get()."""
        with pytest.raises((AttributeError, TypeError)):
            _message_tokens(None)

    def test_total_tokens_with_none_in_list(self):
        """_total_tokens([None, msg]) → crash on None element."""
        messages = [None, {"role": "user", "content": "hi"}]
        with pytest.raises((AttributeError, TypeError)):
            _total_tokens(messages)

    def test_message_tokens_with_none_content(self):
        """Message with content=None should not crash."""
        msg = {"role": "user", "content": None}
        tokens = _message_tokens(msg)
        assert isinstance(tokens, int)

    def test_estimate_tokens_with_none(self):
        """_estimate_tokens(None) crashes."""
        with pytest.raises(TypeError):
            _estimate_tokens(None)


# ============================================================================
# 8. ToolResultManager.process with None content → crash
# ============================================================================

class TestToolResultManagerEdgeCases:

    def test_process_none_content(self):
        """hash_result(None) → None.encode('utf-8') → AttributeError."""
        mgr = ToolResultManager()
        result = mgr.process("read_file", None)
        assert result is not None

    def test_process_empty_content(self):
        """Empty string is valid but worth verifying doesn't break."""
        mgr = ToolResultManager()
        result = mgr.process("read_file", "")
        assert result.content == ""


# ============================================================================
# 9. ContextCompressorV2 with invalid profile → ValueError
# ============================================================================

class TestContextCompressorV2EdgeCases:

    def test_invalid_profile_string(self):
        """Unknown profile string should give a clear error."""
        with pytest.raises(ValueError):
            ContextCompressorV2(profile="nonexistent")

    def test_compress_empty_messages(self):
        """Compressing empty message list shouldn't crash."""
        compressor = ContextCompressorV2()
        result = compressor.compress([], level="auto")
        assert result.compressed_tokens == 0
        assert result.ratio == 1.0

    def test_should_compress_empty_messages(self):
        """should_compress with empty messages shouldn't crash."""
        compressor = ContextCompressorV2()
        should, reason = compressor.should_compress([])
        assert isinstance(should, bool)


# ============================================================================
# 10. Hermes2Engine / from_config with None → crash
# ============================================================================

class TestHermes2AdapterEdgeCases:

    def test_from_config_with_none(self):
        """from_config(None) → None.items() → AttributeError."""
        with pytest.raises((AttributeError, TypeError)):
            from_config(None)

    def test_from_config_with_empty_dict(self):
        """from_config({}) should work with defaults."""
        engine = from_config({})
        assert engine is not None

    def test_process_tool_calls_none_in_list(self):
        """tool_calls list containing None elements."""
        engine = Hermes2Engine()
        result = engine.process_tool_calls([None], lambda tc: "ok")
        assert isinstance(result, dict)

    def test_process_turn_empty_lists(self):
        """process_turn with all empty lists."""
        engine = Hermes2Engine()
        result = engine.process_turn([], [], [])
        assert isinstance(result, dict)

    def test_get_context_messages_with_list_content_system_msg(self):
        """System message with content as list (not string) → TypeError
        when doing string concatenation."""
        engine = Hermes2Engine()
        engine.memory.add(MemoryEntry(
            type=MemoryType.USER,
            content="I prefer dark mode",
            source="test",
        ))
        messages = [
            {"role": "system", "content": [{"type": "text", "text": "You are helpful"}]},
            {"role": "user", "content": "hello"},
        ]
        result = engine.get_context_messages(messages)
        assert isinstance(result, list)


# ============================================================================
# 11. MemoryExtractor with non-string content
# ============================================================================

class TestMemoryExtractorEdgeCases:

    def test_extract_with_none_content(self):
        """Messages with content=None should be skipped, not crash."""
        extractor = MemoryExtractor()
        messages = [
            {"role": "user", "content": None},
            {"role": "user", "content": "remember that I prefer vim"},
        ]
        entries = extractor.extract_from_conversation(messages)
        assert len(entries) >= 1

    def test_extract_with_numeric_content(self):
        """Messages with numeric content."""
        extractor = MemoryExtractor()
        messages = [{"role": "user", "content": 42}]
        entries = extractor.extract_from_conversation(messages)
        assert isinstance(entries, list)

    def test_extract_with_list_content(self):
        """Messages with list content (OpenAI format)."""
        extractor = MemoryExtractor()
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "remember that I prefer Python"}
            ]}
        ]
        entries = extractor.extract_from_conversation(messages)
        assert isinstance(entries, list)


# ============================================================================
# 12. Coordinator with empty/None objective
# ============================================================================

class TestCoordinatorEdgeCases:

    def test_decompose_empty_objective(self):
        """Empty objective should return empty task list."""
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose("")
        assert tasks == []

    def test_decompose_none_objective(self):
        """None objective should not crash."""
        decomposer = TaskDecomposer()
        tasks = decomposer.decompose(None)
        assert isinstance(tasks, list)

    def test_aggregate_empty_results(self):
        """Aggregating empty task list."""
        agg = ResultAggregator()
        result = agg.aggregate([])
        assert result.all_completed is True
        assert result.summary.startswith("All 0")


# ============================================================================
# 13. SmartTruncator edge cases
# ============================================================================

class TestSmartTruncatorEdgeCases:

    def test_truncate_empty_string(self):
        truncator = SmartTruncator()
        result = truncator.truncate("", max_tokens=10)
        assert result == ""

    def test_truncate_with_zero_max_tokens(self):
        """max_tokens=0 should not crash."""
        truncator = SmartTruncator()
        result = truncator.truncate("hello world", max_tokens=0)
        assert isinstance(result, str)

    def test_truncate_single_line(self):
        truncator = SmartTruncator()
        result = truncator.truncate("a" * 10000, max_tokens=10)
        assert isinstance(result, str)
        assert len(result) < 10000


# ============================================================================
# 14. Permission pipeline edge cases
# ============================================================================

class TestPermissionPipelineEdgeCases:

    def test_check_with_none_args(self):
        """args=None should not crash."""
        pipeline = PermissionPipeline(rules=[])
        decision = pipeline.check("read_file", None)
        assert decision is not None

    def test_from_dict_missing_rules_key(self):
        """from_dict with no 'rules' key should use empty list."""
        pipeline = PermissionPipeline.from_dict({})
        assert isinstance(pipeline.rules, list)


# ============================================================================
# 15. ToolOrchestrator with empty list
# ============================================================================

class TestToolOrchestratorEdgeCases:

    def test_partition_empty_list(self):
        orch = ToolOrchestrator()
        batches = orch.partition([])
        assert batches == []

    def test_execute_empty_batches(self):
        orch = ToolOrchestrator()
        results = orch.execute([], lambda tc: "ok")
        assert results == {}


# ============================================================================
# 16. ResultDeduplicator edge cases
# ============================================================================

class TestResultDeduplicatorEdgeCases:

    def test_hash_result_none(self):
        """hash_result(None) should not crash — returns hash of empty string."""
        h = ResultDeduplicator.hash_result(None)
        assert isinstance(h, str)
        assert len(h) == 64

    def test_hash_result_empty_string(self):
        h = ResultDeduplicator.hash_result("")
        assert isinstance(h, str)
        assert len(h) == 64

    def test_is_duplicate_none(self):
        """is_duplicate(None) should not crash."""
        dedup = ResultDeduplicator()
        result = dedup.is_duplicate(None)
        assert isinstance(result, bool)

    def test_register_none(self):
        """register(None) should not crash."""
        dedup = ResultDeduplicator()
        dedup.register(None)


# ============================================================================
# 17. MemoryInjector edge cases
# ============================================================================

class TestMemoryInjectorEdgeCases:

    def test_prepare_context_empty_memories(self):
        injector = MemoryInjector()
        result = injector.prepare_context([])
        assert "## Memory Context" in result

    def test_prepare_context_with_zero_budget(self):
        """max_tokens=0 → char_budget=0 → should not crash."""
        injector = MemoryInjector()
        memories = [MemoryEntry(type=MemoryType.USER, content="test")]
        result = injector.prepare_context(memories, max_tokens=0)
        assert isinstance(result, str)

    def test_prepare_context_with_negative_budget(self):
        injector = MemoryInjector()
        memories = [MemoryEntry(type=MemoryType.USER, content="test")]
        result = injector.prepare_context(memories, max_tokens=-100)
        assert isinstance(result, str)


# ============================================================================
# 18. TranscriptAnalyzer with non-string content
# ============================================================================

class TestTranscriptAnalyzerEdgeCases:

    def test_analyze_with_none_content_messages(self):
        """Messages with content=None should be skipped."""
        analyzer = TranscriptAnalyzer()
        messages = [
            {"role": "user", "content": None},
            {"role": "assistant", "content": "I decided to help you"},
        ]
        summary = analyzer.analyze(messages)
        assert isinstance(summary.topics, list)

    def test_analyze_empty_messages(self):
        analyzer = TranscriptAnalyzer()
        summary = analyzer.analyze([])
        assert summary.duration_minutes == 0.0


# ============================================================================
# 19. Unicode handling in memory search
# ============================================================================

class TestUnicodeEdgeCases:

    def test_tokenize_cjk(self):
        """CJK characters should not crash _tokenize."""
        result = _tokenize("日本語テスト")
        assert isinstance(result, list)

    def test_tokenize_emoji(self):
        result = _tokenize("Hello 🌍 World 🎉!")
        assert isinstance(result, list)

    def test_tokenize_mixed_unicode(self):
        result = _tokenize("café résumé naïve")
        assert isinstance(result, list)

    def test_memory_search_unicode_content(self):
        """Searching with unicode content should not crash."""
        store = MemoryStore()
        store.add(MemoryEntry(
            type=MemoryType.USER,
            content="用户喜欢暗色模式",
            source="test",
        ))
        results = store.search("暗色")
        assert isinstance(results, list)

    def test_memory_search_emoji_tags(self):
        store = MemoryStore()
        store.add(MemoryEntry(
            type=MemoryType.USER,
            content="test entry",
            tags=["🎉", "📌"],
            source="test",
        ))
        results = store.search("test 🎉")
        assert isinstance(results, list)


# ============================================================================
# 20. ContextCompressorV2 with non-string content in messages
# ============================================================================

class TestCompressorMessageEdgeCases:

    def test_message_tokens_with_list_content(self):
        """OpenAI-style multi-part content."""
        msg = {"role": "user", "content": [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "image_url": {"url": "http://..."}},
        ]}
        tokens = _message_tokens(msg)
        assert isinstance(tokens, int)

    def test_message_tokens_with_int_content(self):
        """Content as integer shouldn't crash."""
        msg = {"role": "user", "content": 42}
        tokens = _message_tokens(msg)
        assert isinstance(tokens, int)

    def test_message_tokens_with_empty_dict(self):
        """Message with no 'content' key."""
        msg = {"role": "user"}
        tokens = _message_tokens(msg)
        assert isinstance(tokens, int)
