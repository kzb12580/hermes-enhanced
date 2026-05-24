"""Tests for the Enhanced Memory System."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from memory_system import (
    MemoryEntry,
    MemoryExtractor,
    MemoryInjector,
    MemorySearch,
    MemoryStore,
    MemoryType,
    _tokenize,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return MemoryStore(max_entries=50)


@pytest.fixture
def sample_entry():
    return MemoryEntry(
        type=MemoryType.USER,
        content="I prefer dark mode in all my editors",
        tags=["preference", "ui"],
        source="test",
    )


@pytest.fixture
def tmp_path_file(tmp_path):
    return tmp_path / "memory.json"


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------

class TestMemoryEntry:
    def test_defaults(self):
        e = MemoryEntry(type=MemoryType.MEMORY, content="hello")
        assert e.id  # UUID generated
        assert e.access_count == 0
        assert e.relevance_score == 1.0

    def test_roundtrip(self, sample_entry):
        d = sample_entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.id == sample_entry.id
        assert restored.type == MemoryType.USER
        assert restored.content == sample_entry.content
        assert restored.tags == ["preference", "ui"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestCRUD:
    def test_add_and_get(self, store, sample_entry):
        eid = store.add(sample_entry)
        assert eid == sample_entry.id
        got = store.get(eid)
        assert got is not None
        assert got.content == sample_entry.content
        assert got.access_count == 1  # bumped on get

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None

    def test_update(self, store, sample_entry):
        store.add(sample_entry)
        assert store.update(sample_entry.id, content="new content", tags=["updated"])
        assert store.get(sample_entry.id).content == "new content"

    def test_update_missing(self, store):
        assert store.update("nope", content="x") is False

    def test_delete(self, store, sample_entry):
        store.add(sample_entry)
        assert store.delete(sample_entry.id) is True
        assert store.get(sample_entry.id) is None

    def test_delete_missing(self, store):
        assert store.delete("nope") is False

    def test_eviction(self):
        s = MemoryStore(max_entries=3)
        ids = []
        for i in range(5):
            e = MemoryEntry(type=MemoryType.MEMORY, content=f"entry {i}")
            ids.append(s.add(e))
        assert len(s.entries) == 3
        # First two should have been evicted
        assert s.get(ids[0]) is None
        assert s.get(ids[1]) is None

    def test_update_type_string(self, store, sample_entry):
        store.add(sample_entry)
        store.update(sample_entry.id, type="procedural")
        assert store.get(sample_entry.id).type == MemoryType.PROCEDURAL


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    def _populate(self, store):
        entries = [
            MemoryEntry(type=MemoryType.USER, content="I prefer Python over JavaScript",
                         tags=["preference", "lang"]),
            MemoryEntry(type=MemoryType.PROCEDURAL,
                         content="To fix docker error run docker compose down",
                         tags=["docker", "error"]),
            MemoryEntry(type=MemoryType.MEMORY,
                         content="The project uses SQLAlchemy for database",
                         tags=["db"]),
        ]
        ids = [store.add(e) for e in entries]
        return ids

    def test_basic_search(self, store):
        self._populate(store)
        results = store.search("Python preference")
        assert len(results) > 0
        assert any("Python" in r.content for r in results)

    def test_type_filter(self, store):
        self._populate(store)
        results = store.search("error", type=MemoryType.PROCEDURAL)
        assert all(r.type == MemoryType.PROCEDURAL for r in results)

    def test_limit(self, store):
        self._populate(store)
        results = store.search("the", limit=1)
        assert len(results) <= 1

    def test_tag_bonus(self, store):
        e = MemoryEntry(type=MemoryType.MEMORY, content="some text",
                        tags=["docker", "container"])
        store.add(e)
        results = store.search("docker container")
        assert len(results) >= 1

    def test_scoring_weights(self):
        ms = MemorySearch(kw_weight=1.0, tag_weight=0, recency_weight=0, freq_weight=0)
        entry = MemoryEntry(type=MemoryType.MEMORY, content="python scripting")
        score = ms.score("python", entry, idf={"python": 2.0}, max_access=1)
        assert score > 0

    def test_empty_query(self, store):
        self._populate(store)
        results = store.search("")
        # Should return some results (recency/freq still score)
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class TestExtraction:
    def test_user_preference(self):
        ext = MemoryExtractor()
        msgs = [{"role": "user", "content": "I prefer vim over nano"}]
        entries = ext.extract_from_conversation(msgs)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.USER

    def test_remember_that(self):
        ext = MemoryExtractor()
        msgs = [{"role": "user", "content": "Remember that my API key is stored in .env"}]
        entries = ext.extract_from_conversation(msgs)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.USER

    def test_procedural_error_fixed(self):
        ext = MemoryExtractor()
        msgs = [{"role": "assistant",
                 "content": "The error was fixed by updating the config file"}]
        entries = ext.extract_from_conversation(msgs)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.PROCEDURAL

    def test_episodic_task_completed(self):
        ext = MemoryExtractor()
        msgs = [{"role": "assistant", "content": "Task completed: migrated database"}]
        entries = ext.extract_from_conversation(msgs)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.EPISODIC

    def test_no_match(self):
        ext = MemoryExtractor()
        msgs = [{"role": "user", "content": "Hello there"}]
        entries = ext.extract_from_conversation(msgs)
        assert len(entries) == 0

    def test_multiple_messages(self):
        ext = MemoryExtractor()
        msgs = [
            {"role": "user", "content": "I like using bash scripts"},
            {"role": "assistant", "content": "How to configure nginx upstream"},
            {"role": "assistant", "content": "We accomplished the deployment task"},
        ]
        entries = ext.extract_from_conversation(msgs)
        types = {e.type for e in entries}
        assert MemoryType.USER in types
        assert MemoryType.PROCEDURAL in types
        assert MemoryType.EPISODIC in types


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------

class TestInjection:
    def test_format(self):
        inj = MemoryInjector()
        memories = [
            MemoryEntry(type=MemoryType.USER, content="Prefers dark mode"),
            MemoryEntry(type=MemoryType.PROCEDURAL, content="Fix: run pip install -U"),
            MemoryEntry(type=MemoryType.EPISODIC, content="Deployed v2.0"),
        ]
        ctx = inj.prepare_context(memories, max_tokens=500)
        assert "## Memory Context" in ctx
        assert "### USER" in ctx
        assert "### PROCEDURAL" in ctx
        assert "### EPISODIC" in ctx
        assert "Prefers dark mode" in ctx

    def test_priority_order(self):
        inj = MemoryInjector()
        memories = [
            MemoryEntry(type=MemoryType.EPISODIC, content="episodic"),
            MemoryEntry(type=MemoryType.USER, content="user pref"),
        ]
        ctx = inj.prepare_context(memories)
        # USER section should appear before EPISODIC
        assert ctx.index("### USER") < ctx.index("### EPISODIC")

    def test_token_truncation(self):
        inj = MemoryInjector()
        big_content = "word " * 5000
        memories = [MemoryEntry(type=MemoryType.USER, content=big_content)]
        ctx = inj.prepare_context(memories, max_tokens=50)
        # Should be truncated — 50 tokens ≈ 200 chars
        assert len(ctx) < len(big_content)

    def test_empty_memories(self):
        inj = MemoryInjector()
        ctx = inj.prepare_context([], max_tokens=500)
        assert "## Memory Context" in ctx


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_load(self, tmp_path_file):
        s1 = MemoryStore(storage_path=tmp_path_file)
        e = MemoryEntry(type=MemoryType.MEMORY, content="persist me", tags=["test"])
        s1.add(e)
        eid = e.id

        # Load in a fresh store
        s2 = MemoryStore(storage_path=tmp_path_file)
        got = s2.get(eid)
        assert got is not None
        assert got.content == "persist me"

    def test_no_storage_path(self):
        s = MemoryStore()
        s.add(MemoryEntry(type=MemoryType.MEMORY, content="ephemeral"))
        # Should not raise
        s.save()

    def test_load_missing_file(self, tmp_path):
        s = MemoryStore(storage_path=tmp_path / "nope.json")
        assert len(s.entries) == 0


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

class TestPruning:
    def test_prune_old(self, store):
        old = MemoryEntry(
            type=MemoryType.MEMORY, content="old",
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        recent = MemoryEntry(type=MemoryType.MEMORY, content="recent")
        store.add(old)
        store.add(recent)
        count = store.prune(max_age_days=30)
        assert count == 1
        assert store.get(recent.id) is not None

    def test_prune_low_relevance(self, store):
        low = MemoryEntry(type=MemoryType.MEMORY, content="low", relevance_score=0.05)
        high = MemoryEntry(type=MemoryType.MEMORY, content="high", relevance_score=0.9)
        store.add(low)
        store.add(high)
        count = store.prune(min_relevance=0.1)
        assert count == 1
        assert store.get(high.id) is not None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats(self, store):
        store.add(MemoryEntry(type=MemoryType.USER, content="u"))
        store.add(MemoryEntry(type=MemoryType.PROCEDURAL, content="p"))
        stats = store.get_stats()
        assert stats["total_entries"] == 2
        assert stats["type_counts"]["user"] == 1
        assert stats["type_counts"]["procedural"] == 1

    def test_stats_empty(self, store):
        stats = store.get_stats()
        assert stats["total_entries"] == 0
        assert stats["average_relevance"] == 0.0


# ---------------------------------------------------------------------------
# Tokenize helper
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("The quick brown fox jumps")
        assert "quick" in tokens
        assert "the" not in tokens  # stop word

    def test_empty(self):
        assert _tokenize("") == []
