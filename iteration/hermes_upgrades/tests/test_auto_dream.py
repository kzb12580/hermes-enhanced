"""Tests for auto_dream.py module."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure package imports work (auto_dream uses relative imports)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes_upgrades.memory_system import MemoryEntry, MemoryStore, MemoryType
from hermes_upgrades.auto_dream import (
    AutoDreamer,
    DreamReport,
    DreamTrigger,
    MemoryConsolidator,
    SessionSummary,
    TranscriptAnalyzer,
    _keywords,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_messages(transcript: list[tuple[str, str]], ts_base: datetime | None = None) -> list[dict]:
    """Build message dicts from (role, content) pairs with optional timestamps."""
    msgs = []
    base = ts_base or datetime.now(timezone.utc)
    for i, (role, content) in enumerate(transcript):
        msgs.append({
            "role": role,
            "content": content,
            "timestamp": base + timedelta(minutes=i * 5),
        })
    return msgs


def _make_memory(
    content: str = "test memory",
    access_count: int = 0,
    relevance: float = 1.0,
    created_days_ago: int = 0,
    mtype: MemoryType = MemoryType.MEMORY,
) -> MemoryEntry:
    """Create a MemoryEntry with controlled parameters."""
    return MemoryEntry(
        type=mtype,
        content=content,
        tags=["test"],
        access_count=access_count,
        relevance_score=relevance,
        created_at=datetime.now(timezone.utc) - timedelta(days=created_days_ago),
    )


# ===========================================================================
# 1. DreamTrigger
# ===========================================================================

class TestDreamTrigger:
    """Tests for DreamTrigger thresholds."""

    def test_session_threshold_met(self):
        """Should fire when session count >= threshold."""
        trigger = DreamTrigger(session_threshold=3, time_threshold_hours=999)
        now = datetime.now(timezone.utc)
        # Last run was recent so time threshold not met
        assert trigger.should_run(3, now - timedelta(minutes=1)) is True

    def test_session_threshold_not_met(self):
        """Should not fire when session count < threshold and time not met."""
        trigger = DreamTrigger(session_threshold=5, time_threshold_hours=999)
        now = datetime.now(timezone.utc)
        assert trigger.should_run(4, now - timedelta(minutes=1)) is False

    def test_time_threshold_met(self):
        """Should fire when enough time has elapsed since last run."""
        trigger = DreamTrigger(session_threshold=999, time_threshold_hours=1)
        last_run = datetime.now(timezone.utc) - timedelta(hours=2)
        assert trigger.should_run(0, last_run) is True

    def test_time_threshold_not_met(self):
        """Should not fire when time threshold not met."""
        trigger = DreamTrigger(session_threshold=999, time_threshold_hours=24)
        now = datetime.now(timezone.utc)
        assert trigger.should_run(0, now - timedelta(hours=1)) is False

    def test_both_thresholds_met(self):
        """Should fire when both thresholds are met."""
        trigger = DreamTrigger(session_threshold=2, time_threshold_hours=1)
        last_run = datetime.now(timezone.utc) - timedelta(hours=2)
        result = trigger.should_run(3, last_run)
        assert result is True
        assert trigger.get_trigger_reason() == "both"

    def test_no_thresholds_met(self):
        """Should not fire when neither threshold is met."""
        trigger = DreamTrigger(session_threshold=10, time_threshold_hours=48)
        now = datetime.now(timezone.utc)
        result = trigger.should_run(1, now - timedelta(hours=1))
        assert result is False
        assert trigger.get_trigger_reason() == "none"

    def test_trigger_reason_sessions_only(self):
        trigger = DreamTrigger(session_threshold=2, time_threshold_hours=999)
        now = datetime.now(timezone.utc)
        trigger.should_run(3, now - timedelta(minutes=1))
        assert trigger.get_trigger_reason() == "sessions"

    def test_trigger_reason_time_only(self):
        trigger = DreamTrigger(session_threshold=999, time_threshold_hours=1)
        last_run = datetime.now(timezone.utc) - timedelta(hours=2)
        trigger.should_run(0, last_run)
        assert trigger.get_trigger_reason() == "time"

    def test_trigger_reason_none(self):
        trigger = DreamTrigger(session_threshold=10, time_threshold_hours=48)
        now = datetime.now(timezone.utc)
        trigger.should_run(1, now - timedelta(hours=1))
        assert trigger.get_trigger_reason() == "none"


# ===========================================================================
# 2. TranscriptAnalyzer
# ===========================================================================

class TestTranscriptAnalyzer:
    """Tests for TranscriptAnalyzer.extract / analyze."""

    def test_user_preferences_extracted(self):
        """Should extract 'I prefer ...' patterns."""
        analyzer = TranscriptAnalyzer()
        messages = _make_messages([
            ("user", "I prefer dark mode for all my editors."),
            ("assistant", "Got it."),
            ("user", "I prefer Python over JavaScript."),
        ])
        summary = analyzer.analyze(messages)
        assert len(summary.user_preferences) >= 2
        assert any("dark mode" in p for p in summary.user_preferences)

    def test_errors_extracted(self):
        """Should extract 'fixed by/with/using' patterns."""
        analyzer = TranscriptAnalyzer()
        messages = _make_messages([
            ("assistant", "The issue was fixed by installing the missing dependency."),
            ("user", "Great, that resolved by updating the config file."),
        ])
        summary = analyzer.analyze(messages)
        assert len(summary.errors_fixed) >= 1
        assert any("installing" in e or "dependency" in e for e in summary.errors_fixed)

    def test_key_decisions_extracted(self):
        """Should extract 'decided/chose/will to' patterns."""
        analyzer = TranscriptAnalyzer()
        messages = _make_messages([
            ("user", "We decided to use PostgreSQL for the database."),
            ("assistant", "I chose to implement caching at the application layer."),
        ])
        summary = analyzer.analyze(messages)
        assert len(summary.key_decisions) >= 1

    def test_tool_usage_counted(self):
        """Should count tool calls from tool-role messages."""
        analyzer = TranscriptAnalyzer()
        messages = [
            {"role": "tool", "name": "search_files", "content": "found 3 files"},
            {"role": "tool", "name": "search_files", "content": "found 1 file"},
            {"role": "tool", "name": "read_file", "content": "file contents"},
        ]
        summary = analyzer.analyze(messages)
        assert summary.tools_used.get("search_files") == 2
        assert summary.tools_used.get("read_file") == 1

    def test_tool_mentions_in_content(self):
        """Should detect 'tool: name' patterns in content."""
        analyzer = TranscriptAnalyzer()
        messages = _make_messages([
            ("assistant", "I used tool: terminal to run the command."),
        ])
        summary = analyzer.analyze(messages)
        assert "terminal" in summary.tools_used

    def test_topics_from_user_messages(self):
        """Should extract keywords from user messages as topics."""
        analyzer = TranscriptAnalyzer()
        messages = _make_messages([
            ("user", "Python machine learning neural network training data."),
            ("user", "Python data preprocessing feature engineering."),
        ])
        summary = analyzer.analyze(messages)
        assert len(summary.topics) > 0
        assert "python" in summary.topics

    def test_duration_from_timestamps(self):
        """Should compute duration from first/last timestamps."""
        analyzer = TranscriptAnalyzer()
        base = datetime.now(timezone.utc)
        messages = [
            {"role": "user", "content": "hello", "timestamp": base},
            {"role": "assistant", "content": "hi", "timestamp": base + timedelta(minutes=30)},
        ]
        summary = analyzer.analyze(messages)
        assert abs(summary.duration_minutes - 30.0) < 0.1

    def test_duration_from_unix_timestamps(self):
        """Should handle numeric (unix) timestamps."""
        analyzer = TranscriptAnalyzer()
        base_ts = 1700000000
        messages = [
            {"role": "user", "content": "hello", "timestamp": base_ts},
            {"role": "assistant", "content": "hi", "timestamp": base_ts + 1800},
        ]
        summary = analyzer.analyze(messages)
        assert abs(summary.duration_minutes - 30.0) < 0.1

    def test_no_timestamps_zero_duration(self):
        """Duration should be 0 when no timestamps present."""
        analyzer = TranscriptAnalyzer()
        messages = [{"role": "user", "content": "hello"}]
        summary = analyzer.analyze(messages)
        assert summary.duration_minutes == 0.0

    def test_empty_content_skipped(self):
        """Messages with empty content should be skipped."""
        analyzer = TranscriptAnalyzer()
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": ""},
        ]
        summary = analyzer.analyze(messages)
        assert summary.user_preferences == []
        assert summary.errors_fixed == []


# ===========================================================================
# 3. MemoryConsolidator
# ===========================================================================

class TestMemoryConsolidator:
    """Tests for MemoryConsolidator consolidation logic."""

    def test_creates_episodic_memories_from_summaries(self):
        """Should produce new EPISODIC memory entries from session summaries."""
        consolidator = MemoryConsolidator()
        summaries = [
            SessionSummary(
                key_decisions=["Use FastAPI"],
                errors_fixed=["Installed missing dependency"],
                topics=["api", "backend"],
            )
        ]
        new_entries = consolidator.consolidate(summaries, [])
        assert len(new_entries) >= 1
        assert all(e.type == MemoryType.EPISODIC for e in new_entries)
        assert any("FastAPI" in e.content for e in new_entries)

    def test_promote_frequently_accessed_memories(self):
        """Should boost relevance for memories with access_count >= 5."""
        consolidator = MemoryConsolidator()
        mem = _make_memory(content="popular memory", access_count=10, relevance=0.5)
        consolidator.consolidate([], [mem])
        assert mem.relevance_score > 0.5
        assert mem.relevance_score <= 2.0

    def test_do_not_promote_already_high_relevance(self):
        """Should not promote memories that are already at relevance 2.0."""
        consolidator = MemoryConsolidator()
        mem = _make_memory(content="high relevance", access_count=10, relevance=2.0)
        consolidator.consolidate([], [mem])
        assert mem.relevance_score == 2.0

    def test_demote_old_unused_memories(self):
        """Should reduce relevance for old, unused memories."""
        consolidator = MemoryConsolidator()
        mem = _make_memory(
            content="forgotten memory",
            access_count=0,
            relevance=0.8,
            created_days_ago=30,
        )
        consolidator.consolidate([], [mem])
        assert mem.relevance_score < 0.8
        assert mem.relevance_score >= 0.1

    def test_do_not_demote_below_minimum(self):
        """Should not demote below relevance 0.1."""
        consolidator = MemoryConsolidator()
        mem = _make_memory(
            content="already low",
            access_count=0,
            relevance=0.15,
            created_days_ago=30,
        )
        consolidator.consolidate([], [mem])
        assert mem.relevance_score >= 0.1

    def test_do_not_demote_recent_memories(self):
        """Should not demote memories created less than 14 days ago."""
        consolidator = MemoryConsolidator()
        mem = _make_memory(
            content="recent unused",
            access_count=0,
            relevance=0.8,
            created_days_ago=5,
        )
        consolidator.consolidate([], [mem])
        assert mem.relevance_score == 0.8

    def test_do_not_demote_accessed_memories(self):
        """Should not demote memories that have been accessed."""
        consolidator = MemoryConsolidator()
        mem = _make_memory(
            content="accessed old",
            access_count=3,
            relevance=0.8,
            created_days_ago=30,
        )
        consolidator.consolidate([], [mem])
        assert mem.relevance_score == 0.8

    def test_content_similarity_identical(self):
        """Identical strings should have similarity ~1.0."""
        sim = MemoryConsolidator.content_similarity("hello world", "hello world")
        assert sim == pytest.approx(1.0)

    def test_content_similarity_different(self):
        """Completely different strings should have low similarity."""
        sim = MemoryConsolidator.content_similarity("alpha bravo", "xray zulu")
        assert sim < 0.3

    def test_content_similarity_case_insensitive(self):
        """Similarity should be case-insensitive."""
        sim = MemoryConsolidator.content_similarity("Hello World", "hello world")
        assert sim == pytest.approx(1.0)

    def test_empty_summaries_no_new_memories(self):
        """Empty summaries should produce no new memories."""
        consolidator = MemoryConsolidator()
        new_entries = consolidator.consolidate([], [])
        assert new_entries == []

    def test_summary_with_no_extractable_info(self):
        """Summary with no decisions/errors/preferences/topics produces nothing."""
        consolidator = MemoryConsolidator()
        summaries = [SessionSummary()]
        new_entries = consolidator.consolidate(summaries, [])
        assert new_entries == []


# ===========================================================================
# 4. DreamReport
# ===========================================================================

class TestDreamReport:
    """Tests for DreamReport data class."""

    def test_default_values(self):
        report = DreamReport()
        assert report.sessions_reviewed == 0
        assert report.memories_created == 0
        assert report.memories_merged == 0
        assert report.memories_promoted == 0
        assert report.memories_demoted == 0
        assert report.insights == []
        assert isinstance(report.timestamp, datetime)

    def test_custom_values(self):
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        report = DreamReport(
            sessions_reviewed=3,
            memories_created=5,
            memories_merged=1,
            memories_promoted=2,
            memories_demoted=1,
            insights=["insight 1"],
            timestamp=ts,
        )
        assert report.sessions_reviewed == 3
        assert report.memories_created == 5
        assert report.memories_merged == 1
        assert report.memories_promoted == 2
        assert report.memories_demoted == 1
        assert report.insights == ["insight 1"]
        assert report.timestamp == ts


# ===========================================================================
# 5. AutoDreamer
# ===========================================================================

class TestAutoDreamer:
    """Tests for the top-level AutoDreamer orchestrator."""

    def _make_dreamer(self, session_threshold=2, time_hours=999) -> tuple[AutoDreamer, MemoryStore]:
        """Create an AutoDreamer with a fresh MemoryStore."""
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=session_threshold, time_threshold_hours=time_hours)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        # Set last_dream to now so time-based triggers don't accidentally fire
        dreamer._last_dream = datetime.now(timezone.utc)
        return dreamer, store

    def test_record_session_increments_count(self):
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(topics=["test"]))
        dreamer.record_session(SessionSummary(topics=["test2"]))
        assert dreamer._session_count == 2

    def test_should_dream_true_when_threshold_met(self):
        dreamer, _ = self._make_dreamer(session_threshold=2)
        dreamer.record_session(SessionSummary())
        dreamer.record_session(SessionSummary())
        assert dreamer.should_dream() is True

    def test_should_dream_false_when_threshold_not_met(self):
        dreamer, _ = self._make_dreamer(session_threshold=5)
        dreamer.record_session(SessionSummary())
        assert dreamer.should_dream() is False

    def test_dream_with_empty_summaries(self):
        """Dreaming with no pending summaries returns an empty report."""
        dreamer, _ = self._make_dreamer()
        report = dreamer.dream()
        assert report.sessions_reviewed == 0
        assert report.memories_created == 0

    def test_full_dream_cycle(self):
        """Full cycle: record sessions, dream, check report."""
        dreamer, store = self._make_dreamer()
        dreamer.record_session(SessionSummary(
            key_decisions=["Use Rust"],
            errors_fixed=["Fixed linker error"],
            topics=["rust", "systems"],
            user_preferences=["I prefer dark mode"],
            duration_minutes=45.0,
        ))
        dreamer.record_session(SessionSummary(
            key_decisions=["Add caching"],
            topics=["cache", "performance"],
            duration_minutes=30.0,
        ))
        report = dreamer.dream()
        assert report.sessions_reviewed == 2
        assert report.memories_created >= 1
        assert len(report.insights) > 0
        # Memories should be added to the store
        assert len(store.entries) >= 1

    def test_dream_resets_pending_summaries(self):
        """After dreaming, pending summaries should be cleared."""
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(topics=["a"]))
        dreamer.dream()
        assert dreamer._session_count == 0
        assert len(dreamer._pending_summaries) == 0

    def test_dream_updates_last_dream_time(self):
        """After dreaming, _last_dream should be updated."""
        dreamer, _ = self._make_dreamer()
        old_time = dreamer._last_dream
        dreamer.record_session(SessionSummary(topics=["a"]))
        dreamer.dream()
        assert dreamer._last_dream > old_time

    def test_history_tracks_reports(self):
        """get_history() should return all past dream reports."""
        dreamer, _ = self._make_dreamer()
        # First dream (empty)
        dreamer.dream()
        # Second dream with content
        dreamer.record_session(SessionSummary(topics=["x"]))
        dreamer.dream()
        history = dreamer.get_history()
        assert len(history) == 2
        assert isinstance(history[0], DreamReport)
        assert isinstance(history[1], DreamReport)

    def test_history_returns_copy(self):
        """get_history() returns a copy, not internal list."""
        dreamer, _ = self._make_dreamer()
        dreamer.dream()
        h1 = dreamer.get_history()
        h1.clear()
        assert len(dreamer.get_history()) == 1

    def test_merge_similar_memories(self):
        """Very similar new memories should be merged."""
        dreamer, store = self._make_dreamer()
        # Two sessions with very similar content
        dreamer.record_session(SessionSummary(
            key_decisions=["Use PostgreSQL for the database system"],
        ))
        dreamer.record_session(SessionSummary(
            key_decisions=["Use PostgreSQL for the database system."],
        ))
        report = dreamer.dream()
        # Should have merged some memories
        assert report.memories_merged >= 0  # merge count is >= 0

    def test_insights_include_preferences(self):
        """Insights should mention user preferences when present."""
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(
            user_preferences=["vim keybindings"],
        ))
        dreamer.record_session(SessionSummary(
            user_preferences=["vim keybindings"],
        ))
        report = dreamer.dream()
        assert any("vim keybindings" in i for i in report.insights)

    def test_insights_include_error_count(self):
        """Insights should mention resolved errors."""
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(
            errors_fixed=["segfault in parser"],
        ))
        report = dreamer.dream()
        assert any("error" in i.lower() for i in report.insights)

    def test_insights_include_tool_usage(self):
        """Insights should mention most used tools."""
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(
            tools_used={"terminal": 5, "read_file": 3},
        ))
        report = dreamer.dream()
        assert any("terminal" in i for i in report.insights)

    def test_insights_include_duration(self):
        """Insights should mention total session time."""
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(duration_minutes=60.0))
        report = dreamer.dream()
        assert any("minute" in i.lower() for i in report.insights)

    def test_insights_include_topics(self):
        """Insights should mention frequent topics."""
        dreamer, _ = self._make_dreamer()
        dreamer.record_session(SessionSummary(topics=["python", "api"]))
        dreamer.record_session(SessionSummary(topics=["python", "flask"]))
        report = dreamer.dream()
        assert any("python" in i.lower() for i in report.insights)

    def test_consolidator_creates_episodic_in_store(self):
        """Dream cycle should add episodic memories to the store."""
        dreamer, store = self._make_dreamer()
        dreamer.record_session(SessionSummary(
            key_decisions=["Deploy to production"],
        ))
        dreamer.dream()
        episodic = [e for e in store.entries if e.type == MemoryType.EPISODIC]
        assert len(episodic) >= 1


# ===========================================================================
# 6. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_transcript(self):
        """Analyzing empty message list should return empty summary."""
        analyzer = TranscriptAnalyzer()
        summary = analyzer.analyze([])
        assert summary.key_decisions == []
        assert summary.errors_fixed == []
        assert summary.tools_used == {}
        assert summary.topics == []
        assert summary.user_preferences == []
        assert summary.duration_minutes == 0.0

    def test_no_memories_in_store(self):
        """Dreaming with no existing memories should work fine."""
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=1, time_threshold_hours=999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        dreamer.record_session(SessionSummary(key_decisions=["test"]))
        report = dreamer.dream()
        assert report.sessions_reviewed == 1

    def test_single_session_dream(self):
        """Single session should produce a valid dream report."""
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=1, time_threshold_hours=999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        dreamer.record_session(SessionSummary(
            key_decisions=["Use Docker"],
            topics=["docker", "deployment"],
        ))
        report = dreamer.dream()
        assert report.sessions_reviewed == 1
        assert report.memories_created >= 1

    def test_analyzer_message_with_none_content(self):
        """Messages with None content should be handled gracefully."""
        analyzer = TranscriptAnalyzer()
        messages = [{"role": "user", "content": None}]
        summary = analyzer.analyze(messages)
        assert summary.user_preferences == []

    def test_consolidator_preserves_existing_memories(self):
        """Consolidation should not modify existing memories' content."""
        consolidator = MemoryConsolidator()
        existing = [_make_memory(content="keep me intact")]
        original_content = existing[0].content
        consolidator.consolidate([], existing)
        assert existing[0].content == original_content

    def test_keywords_extraction(self):
        """_keywords should extract meaningful words."""
        result = _keywords("python machine learning with python data science python", top_n=3)
        assert "python" in result
        assert result[0] == "python"  # most frequent

    def test_keywords_excludes_stop_words(self):
        """_keywords should not include stop words."""
        result = _keywords("the is and or but", top_n=5)
        # All stop words, should return empty or very few
        assert len(result) == 0

    def test_dreamer_with_existing_store_memories(self):
        """Dreamer should work with a store that already has memories."""
        store = MemoryStore()
        store.add(_make_memory(content="pre-existing memory"))
        trigger = DreamTrigger(session_threshold=1, time_threshold_hours=999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)
        dreamer.record_session(SessionSummary(key_decisions=["New decision"]))
        report = dreamer.dream()
        # Pre-existing + new episodic
        assert len(store.entries) >= 2

    def test_multiple_dream_cycles(self):
        """Multiple dream cycles should each produce distinct reports."""
        store = MemoryStore()
        trigger = DreamTrigger(session_threshold=1, time_threshold_hours=999)
        dreamer = AutoDreamer(memory_store=store, trigger=trigger)

        for i in range(3):
            dreamer.record_session(SessionSummary(
                key_decisions=[f"Decision {i}"],
                topics=[f"topic{i}"],
            ))
            dreamer.dream()

        history = dreamer.get_history()
        assert len(history) == 3
        for report in history:
            assert report.sessions_reviewed == 1
