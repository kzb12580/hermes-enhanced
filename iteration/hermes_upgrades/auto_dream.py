"""Auto-Dream Memory Consolidation Module for Hermes Agent 2.0.

Background process that periodically reviews session transcripts and
consolidates memories.  Inspired by Claude Code's autoDream service.

Runs after *session_threshold* sessions or *time_threshold_hours* hours.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Optional

try:
    from .memory_system import MemoryEntry, MemoryStore, MemoryType, STOP_WORDS
except ImportError:
    from memory_system import MemoryEntry, MemoryStore, MemoryType, STOP_WORDS

try:
    from .token_utils import extract_text_from_content
except ImportError:
    from token_utils import extract_text_from_content

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SessionSummary:
    """Structured summary produced by :class:`TranscriptAnalyzer`."""

    key_decisions: list[str] = field(default_factory=list)
    errors_fixed: list[str] = field(default_factory=list)
    tools_used: dict[str, int] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    user_preferences: list[str] = field(default_factory=list)
    duration_minutes: float = 0.0


@dataclass
class DreamReport:
    """Report generated after a dream cycle."""

    sessions_reviewed: int = 0
    memories_created: int = 0
    memories_merged: int = 0
    memories_promoted: int = 0
    memories_demoted: int = 0
    insights: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConsolidationResult:
    """Result of a memory consolidation pass.

    Attributes:
        new_entries: Newly created episodic memories from session summaries.
        promoted: Copies of memories whose relevance was boosted.
        demoted: Copies of memories whose relevance was reduced.
    """

    new_entries: list[MemoryEntry] = field(default_factory=list)
    promoted: list[MemoryEntry] = field(default_factory=list)
    demoted: list[MemoryEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DreamTrigger
# ---------------------------------------------------------------------------

class DreamTrigger:
    """Determines whether a dream cycle should run.

    Args:
        session_threshold: Number of recorded sessions before dreaming.
        time_threshold_hours: Hours elapsed since last dream before dreaming.
    """

    def __init__(self, session_threshold: int = 5,
                 time_threshold_hours: int = 24) -> None:
        self.session_threshold = session_threshold
        self.time_threshold_hours = time_threshold_hours
        self._session_count: int = 0
        self._last_run: datetime = datetime.fromtimestamp(0, tz=timezone.utc)

    def should_run(self, session_count: int, last_run: datetime) -> bool:
        """Return ``True`` if either threshold has been exceeded.

        .. warning::
            **Side-effect:** This method mutates ``self._session_count`` and
            ``self._last_run`` to the values passed in.  Callers should be
            aware that ``get_trigger_reason()`` depends on these cached
            values and reflects the most recent call to ``should_run()``.
        """
        self._session_count = session_count
        # Guard against naive datetime
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        self._last_run = last_run
        sessions_met = session_count >= self.session_threshold
        now = datetime.now(timezone.utc)
        time_met = (now - last_run) >= timedelta(hours=self.time_threshold_hours)
        return sessions_met or time_met

    def get_trigger_reason(self) -> str:
        """Return why the trigger fired: ``'sessions'``, ``'time'``,
        ``'both'``, or ``'none'``."""
        sessions_met = self._session_count >= self.session_threshold
        now = datetime.now(timezone.utc)
        time_met = (now - self._last_run) >= timedelta(hours=self.time_threshold_hours)
        if sessions_met and time_met:
            return "both"
        if sessions_met:
            return "sessions"
        if time_met:
            return "time"
        return "none"


# ---------------------------------------------------------------------------
# TranscriptAnalyzer
# ---------------------------------------------------------------------------

# Patterns for extraction
_PREF_RE = re.compile(
    r"(?:I|i)\s+prefer\s+(.+?)(?:\.|$)", re.IGNORECASE
)
_ERROR_RE = re.compile(
    r"(?:fixed|resolved|solved)\s+(?:by|with|using)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"(?:decided|chose|will)\s+to\s+(.+?)(?:\.|$)", re.IGNORECASE
)
_TOOL_RE = re.compile(r"\btool[_:]?\s*(\w+)", re.IGNORECASE)


_KEYWORD_RE = re.compile(r"[a-z0-9]+")


def _keywords(text: str, top_n: int = 5) -> list[str]:
    """Extract top-N keywords from *text* (excluding stop words)."""
    tokens = _KEYWORD_RE.findall(text.lower())
    filtered = [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
    return [w for w, _ in Counter(filtered).most_common(top_n)]


class TranscriptAnalyzer:
    """Analyse a list of ``{"role": ..., "content": ...}`` message dicts
    and return a :class:`SessionSummary`."""

    def analyze(self, messages: list[dict]) -> SessionSummary:
        """Extract structured information from raw messages."""
        summary = SessionSummary()
        all_user_text: list[str] = []
        tools: Counter[str] = Counter()

        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Handle OpenAI-style multipart content (list of parts)
            content = extract_text_from_content(content)

            if not content:
                continue

            # User preferences
            for m in _PREF_RE.finditer(content):
                pref = m.group(1).strip()
                if pref:
                    summary.user_preferences.append(pref)

            # Errors fixed
            for m in _ERROR_RE.finditer(content):
                fix = m.group(1).strip()
                if fix:
                    summary.errors_fixed.append(fix)

            # Key decisions
            for m in _DECISION_RE.finditer(content):
                decision = m.group(1).strip()
                if decision:
                    summary.key_decisions.append(decision)

            # Tool usage (look for tool-call messages)
            if role == "tool" or msg.get("type") == "tool_call":
                tool_name = msg.get("name") or msg.get("tool", "unknown")
                tools[tool_name] += 1

            # Also scan for explicit tool mentions
            for m in _TOOL_RE.finditer(content):
                tools[m.group(1)] += 1

            # Collect user text for topic extraction
            if role == "user":
                all_user_text.append(content)

        summary.tools_used = dict(tools)

        # Topic extraction from user messages
        if all_user_text:
            combined = " ".join(all_user_text)
            summary.topics = _keywords(combined, top_n=8)

        # Duration: try to extract from first/last timestamps if present
        timestamps: list[datetime] = []
        for msg in messages:
            ts = msg.get("timestamp")
            if isinstance(ts, datetime):
                # Normalize to timezone-aware UTC
                if ts.tzinfo is None:
                    timestamps.append(ts.replace(tzinfo=timezone.utc))
                else:
                    timestamps.append(ts.astimezone(timezone.utc))
            elif isinstance(ts, (int, float)):
                timestamps.append(datetime.fromtimestamp(ts, tz=timezone.utc))
        if len(timestamps) >= 2:
            delta = max(timestamps) - min(timestamps)
            summary.duration_minutes = delta.total_seconds() / 60.0

        return summary


# ---------------------------------------------------------------------------
# MemoryConsolidator
# ---------------------------------------------------------------------------

class MemoryConsolidator:
    """Merge, promote, demote, and create memories from session summaries."""

    _SIMILARITY_THRESHOLD = 0.6

    def consolidate(
        self,
        summaries: list[SessionSummary],
        existing_memories: list[MemoryEntry],
    ) -> ConsolidationResult:
        """Run consolidation and return a :class:`ConsolidationResult`.

        * Deduplicates existing memories by content similarity.
        * Promotes frequently accessed memories.
        * Demotes rarely accessed old memories.
        * Creates new episodic memories from session summaries.

        The input *existing_memories* list is **not** modified.  Promoted
        and demoted entries are deep copies with updated relevance scores.
        """
        import copy

        now = datetime.now(timezone.utc)
        new_entries: list[MemoryEntry] = []
        promoted: list[MemoryEntry] = []
        demoted: list[MemoryEntry] = []

        # --- Create episodic memories from summaries -----------------------
        for i, s in enumerate(summaries):
            parts: list[str] = []
            if s.key_decisions:
                parts.append("Decisions: " + "; ".join(s.key_decisions))
            if s.errors_fixed:
                parts.append("Fixes: " + "; ".join(s.errors_fixed))
            if s.user_preferences:
                parts.append("Preferences: " + "; ".join(s.user_preferences))
            if s.topics:
                parts.append("Topics: " + ", ".join(s.topics))
            if parts:
                new_entries.append(MemoryEntry(
                    type=MemoryType.EPISODIC,
                    content=" | ".join(parts),
                    tags=s.topics[:5],
                    source="auto-dream",
                ))

        # --- Promote frequently accessed memories --------------------------
        promoted_ids: set[str] = set()
        for mem in existing_memories:
            if mem.access_count >= 5 and mem.relevance_score < 2.0:
                promoted_mem = copy.deepcopy(mem)
                promoted_mem.relevance_score = min(
                    promoted_mem.relevance_score + 0.3, 2.0
                )
                promoted.append(promoted_mem)
                promoted_ids.add(mem.id)

        # --- Demote rarely accessed old memories ---------------------------
        # Skip memories that were already promoted to avoid conflicting
        # relevance changes on the same entry.
        cutoff = now - timedelta(days=14)
        for mem in existing_memories:
            if mem.id in promoted_ids:
                continue
            if (mem.access_count == 0
                    and mem.created_at < cutoff
                    and mem.relevance_score > 0.1):
                demoted_mem = copy.deepcopy(mem)
                demoted_mem.relevance_score = max(
                    demoted_mem.relevance_score - 0.2, 0.1
                )
                demoted.append(demoted_mem)

        self._last_promote_count = len(promoted)
        self._last_demote_count = len(demoted)

        return ConsolidationResult(
            new_entries=new_entries,
            promoted=promoted,
            demoted=demoted,
        )

    def get_promote_count(self) -> int:
        """Return number of memories promoted in last consolidation."""
        return getattr(self, "_last_promote_count", 0)

    def get_demote_count(self) -> int:
        """Return number of memories demoted in last consolidation."""
        return getattr(self, "_last_demote_count", 0)

    @classmethod
    def content_similarity(cls, a: str, b: str) -> float:
        """Return 0..1 similarity ratio between two content strings."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# AutoDreamer
# ---------------------------------------------------------------------------

class AutoDreamer:
    """Top-level dream orchestrator.

    Args:
        memory_store: A :class:`MemoryStore` instance for persistence.
        trigger: Optional custom :class:`DreamTrigger`.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        trigger: Optional[DreamTrigger] = None,
    ) -> None:
        self._store = memory_store
        self._trigger = trigger or DreamTrigger()
        self._analyzer = TranscriptAnalyzer()
        self._consolidator = MemoryConsolidator()
        self._pending_summaries: list[SessionSummary] = []
        self._session_count: int = 0
        self._last_dream: datetime = datetime.fromtimestamp(0, tz=timezone.utc)
        self._history: list[DreamReport] = []
        self._lock = threading.Lock()

    MAX_HISTORY: int = 100

    # -- Public API ---------------------------------------------------------

    def record_session(self, summary: SessionSummary) -> None:
        """Record a session summary for the next dream cycle."""
        with self._lock:
            self._pending_summaries.append(summary)
            self._session_count += 1

    def should_dream(self) -> bool:
        """Check whether thresholds are met for a dream cycle."""
        with self._lock:
            return self._trigger.should_run(self._session_count, self._last_dream)

    def dream(self) -> DreamReport:
        """Run a full dream cycle: analyse, consolidate, merge, report."""
        with self._lock:
            return self._dream_locked()

    def dream_if_needed(self) -> Optional[DreamReport]:
        """Check thresholds and run dream in a single locked operation.

        This prevents TOCTOU race conditions between should_dream() and dream().
        Returns a DreamReport if dreaming was triggered, None otherwise.
        """
        with self._lock:
            if not self._trigger.should_run(self._session_count, self._last_dream):
                return None
            return self._dream_locked()

    def _dream_locked(self) -> DreamReport:
        """Internal dream implementation (must hold self._lock).

        Gathers all needed data while holding self._lock, then releases it
        before calling MemoryStore methods (which acquire store._lock) to
        avoid a lock-ordering deadlock.
        """
        if not self._pending_summaries:
            report = DreamReport(timestamp=datetime.now(timezone.utc))
            self._history.append(report)
            if len(self._history) > self.MAX_HISTORY:
                self._history = self._history[-self.MAX_HISTORY:]
            return report

        # Phase 1: gather data while holding self._lock
        summaries = list(self._pending_summaries)
        existing = list(self._store.entries)

        # Consolidate: create new episodic memories (non-destructive)
        result = self._consolidator.consolidate(summaries, existing)

        promote_count = len(result.promoted)
        demote_count = len(result.demoted)

        # Merge similar new memories
        merged_memories = self._merge_similar(result.new_entries)
        merge_count = len(result.new_entries) - len(merged_memories)

        # Generate insights (read-only, safe under lock)
        insights = self._generate_insights(summaries)

        # Reset counters (under self._lock)
        self._pending_summaries.clear()
        self._session_count = 0
        now = datetime.now(timezone.utc)
        self._last_dream = now

        # Phase 2: release self._lock before store operations
        self._lock.release()
        try:
            # Apply promoted/demoted changes back to the store
            for pm in result.promoted:
                self._store.update(pm.id, relevance_score=pm.relevance_score)
            for dm in result.demoted:
                self._store.update(dm.id, relevance_score=dm.relevance_score)

            # Add to store
            for mem in merged_memories:
                self._store.add(mem)
        finally:
            self._lock.acquire()

        report = DreamReport(
            sessions_reviewed=len(summaries),
            memories_created=len(merged_memories),
            memories_merged=max(merge_count, 0),
            memories_promoted=promote_count,
            memories_demoted=demote_count,
            insights=insights,
            timestamp=now,
        )

        self._history.append(report)
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]
        return report

    def get_history(self) -> list[DreamReport]:
        """Return list of all past dream reports."""
        return list(self._history)

    # -- Internal -----------------------------------------------------------

    def _merge_similar(self, memories: list[MemoryEntry]) -> list[MemoryEntry]:
        """Merge memories with similar content, keeping the newer one."""
        if not memories:
            return memories

        # Fast path: exact-content dedup (case-insensitive) — O(n)
        seen_content: dict[str, MemoryEntry] = {}
        for mem in memories:
            key = mem.content.strip().lower()
            if key in seen_content:
                if mem.created_at >= seen_content[key].created_at:
                    seen_content[key] = mem
            else:
                seen_content[key] = mem

        unique = list(seen_content.values())
        if len(unique) <= 1:
            return unique

        # Slow path: fuzzy merge on remaining unique entries
        # With length-based early skip to avoid expensive SequenceMatcher
        merged: list[MemoryEntry] = []
        used: set[int] = set()
        total = len(unique)

        for i, mem_a in enumerate(unique):
            if i in used:
                continue
            best = mem_a
            # Early exit: if all remaining items are used, stop
            if len(used) >= total - 1:
                merged.append(best)
                break
            for j in range(i + 1, total):
                if j in used:
                    continue
                mem_b = unique[j]
                # Zero-length guard: skip comparison if either content is empty
                len_a, len_b = len(best.content), len(mem_b.content)
                if len_a == 0 or len_b == 0:
                    continue
                # Length guard: skip if content lengths differ by >3x
                length_ratio = max(len_a, len_b) / min(len_a, len_b)
                if length_ratio > 3.0:
                    continue
                sim = MemoryConsolidator.content_similarity(
                    best.content, mem_b.content
                )
                if sim >= MemoryConsolidator._SIMILARITY_THRESHOLD:
                    if mem_b.created_at >= best.created_at:
                        best = mem_b
                    used.add(j)
            merged.append(best)

        return merged

    def _generate_insights(self, summaries: list[SessionSummary]) -> list[str]:
        """Generate human-readable insights from session summaries."""
        insights: list[str] = []

        # Recurring preferences
        all_prefs: list[str] = []
        for s in summaries:
            all_prefs.extend(s.user_preferences)
        if all_prefs:
            pref_counts = Counter(p.lower() for p in all_prefs)
            for pref, count in pref_counts.most_common(3):
                if count >= 2:
                    insights.append(
                        f"User consistently prefers '{pref}' across {count} sessions"
                    )
                else:
                    insights.append(f"User preference noted: '{pref}'")

        # Common topics
        all_topics: list[str] = []
        for s in summaries:
            all_topics.extend(s.topics)
        if all_topics:
            topic_counts = Counter(all_topics)
            top = topic_counts.most_common(3)
            topic_str = ", ".join(f"{t} ({c})" for t, c in top)
            insights.append(f"Frequent topics: {topic_str}")

        # Error patterns
        total_errors = sum(len(s.errors_fixed) for s in summaries)
        if total_errors:
            insights.append(
                f"Resolved {total_errors} error(s) across {len(summaries)} sessions"
            )

        # Tool usage
        combined_tools: Counter[str] = Counter()
        for s in summaries:
            combined_tools.update(s.tools_used)
        if combined_tools:
            top_tools = combined_tools.most_common(3)
            tool_str = ", ".join(f"{t} ({c})" for t, c in top_tools)
            insights.append(f"Most used tools: {tool_str}")

        # Total duration
        total_mins = sum(s.duration_minutes for s in summaries)
        if total_mins > 0:
            insights.append(
                f"Total session time: {total_mins:.1f} minutes"
            )

        return insights
