"""Enhanced Context Compressor V2 for Hermes Agent.

Provides multi-level context compression with pressure monitoring,
progressive compression strategies, and statistics tracking.

Levels:
  - Microcompact: Fast, no LLM — prunes old tool results
  - Reactive: Rule-based, no LLM — compresses until target ratio
  - Full: LLM-enhanced — summarize middle of conversation (interface only)

Usage:
    compressor = ContextCompressorV2(model_token_limit=200000, profile="balanced")
    should, reason = compressor.should_compress(messages)
    if should:
        result = compressor.compress(messages, level="auto")
        print(result.compressed_tokens, result.ratio)
"""

from __future__ import annotations

import copy
import enum
import statistics
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN: int = 4  # rough heuristic


def _estimate_tokens(text: str) -> int:
    """Estimate token count from string length (~4 chars per token)."""
    return len(text) // CHARS_PER_TOKEN


def _message_tokens(msg: dict) -> int:
    """Estimate tokens for a single message dict."""
    content = msg.get("content", "")
    if isinstance(content, list):
        # multi-part content (e.g. tool results with images)
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        content = " ".join(parts)
    elif not isinstance(content, str):
        content = str(content)
    return _estimate_tokens(content) + 10  # small overhead for role/metadata


def _total_tokens(messages: list[dict]) -> int:
    """Estimate total tokens across all messages."""
    return sum(_message_tokens(m) for m in messages)


# ---------------------------------------------------------------------------
# CompressionProfile
# ---------------------------------------------------------------------------


class CompressionProfile(enum.Enum):
    """Named presets for compression behaviour."""

    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    GENTLE = "gentle"

    @property
    def pressure_threshold(self) -> float:
        return {
            CompressionProfile.AGGRESSIVE: 0.6,
            CompressionProfile.BALANCED: 0.75,
            CompressionProfile.GENTLE: 0.85,
        }[self]

    @property
    def microcompact_age(self) -> int:
        """Number of recent turns whose tool results are kept."""
        return {
            CompressionProfile.AGGRESSIVE: 3,
            CompressionProfile.BALANCED: 5,
            CompressionProfile.GENTLE: 8,
        }[self]

    @property
    def keep_last_n(self) -> int:
        return self.microcompact_age  # alias for clarity


# ---------------------------------------------------------------------------
# PressureMonitor
# ---------------------------------------------------------------------------


class PressureMonitor:
    """Tracks context-window pressure over time.

    Args:
        model_token_limit: Maximum tokens the model supports.
    """

    def __init__(self, model_token_limit: int) -> None:
        self.model_token_limit = model_token_limit
        self.history: list[float] = []

    def update(self, messages: list[dict]) -> float:
        """Compute current pressure ratio and record it.

        Returns:
            Pressure as float in [0.0, 1.0].
        """
        tokens = _total_tokens(messages)
        if self.model_token_limit <= 0:
            raise ValueError(
                f"model_token_limit must be positive, got {self.model_token_limit}"
            )
        else:
            pressure = min(1.0, tokens / self.model_token_limit)
        self.history.append(pressure)
        return pressure

    def should_compress(self, threshold: float) -> bool:
        """Return True if the latest pressure reading meets/exceeds *threshold*."""
        if not self.history:
            return False
        return self.history[-1] >= threshold

    @property
    def current(self) -> float:
        return self.history[-1] if self.history else 0.0


# ---------------------------------------------------------------------------
# MicrocompactLevel
# ---------------------------------------------------------------------------


class MicrocompactLevel:
    """Fast, zero-LLM compression: prune old tool results.

    Keeps the most recent *keep_last_n* tool-result messages intact;
    older tool results are content-cleared.  All other message types
    (system, user, assistant) are left untouched.
    """

    @staticmethod
    def prune_old_tool_results(
        messages: list[dict],
        keep_last_n: int = 8,
    ) -> list[dict]:
        """Return a (shallow-copied) list with old tool results pruned.

        Args:
            messages: Conversation messages.
            keep_last_n: How many of the most recent tool-result messages
                to keep with full content.

        Returns:
            New list; original is not mutated.
        """
        # Identify indices of tool-result messages (role == "tool")
        tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]

        # Indices to prune (everything except last keep_last_n tool results)
        if len(tool_indices) <= keep_last_n:
            return list(messages)  # nothing to prune

        prune_set = set(tool_indices[: len(tool_indices) - keep_last_n])

        result: list[dict] = []
        for i, msg in enumerate(messages):
            if i in prune_set:
                # Deep-copy to avoid mutating the original message's
                # nested structures (e.g. tool_calls lists)
                pruned = copy.deepcopy(msg)
                pruned["content"] = "[tool result pruned — context compression]"
                result.append(pruned)
            else:
                result.append(msg)
        return result


# ---------------------------------------------------------------------------
# ReactiveLevel
# ---------------------------------------------------------------------------


class ReactiveLevel:
    """Rule-based progressive compression (no LLM).

    Strategy:
      1. Prune old tool results (MicrocompactLevel).
      2. If still over target: truncate large assistant messages in
         the older half of the conversation.
      3. If still over target: collapse repeated/redundant tool results.
    """

    @staticmethod
    def compress(
        messages: list[dict],
        target_ratio: float = 0.6,
    ) -> list[dict]:
        """Compress until estimated tokens ≤ *target_ratio* × model limit.

        This uses the total token count relative to a rough baseline
        (the original total).  *target_ratio* here is interpreted as the
        desired ratio of compressed tokens to original tokens.

        Args:
            messages: Current conversation messages.
            target_ratio: Desired compressed/total token ratio (0-1).

        Returns:
            Compressed message list (new list, original unmodified).
        """
        original_tokens = _total_tokens(messages)
        target_tokens = int(original_tokens * target_ratio)

        result = list(messages)

        # Step 1: microcompact
        result = MicrocompactLevel.prune_old_tool_results(result, keep_last_n=5)
        if _total_tokens(result) <= target_tokens:
            return result

        # Step 2: truncate large assistant messages in older half
        mid = len(result) // 2
        for i in range(mid):
            msg = result[i]
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 500:
                    new_msg = dict(msg)
                    new_msg["content"] = content[:250] + "\n[... compressed ...]\n" + content[-150:]
                    result[i] = new_msg
        if _total_tokens(result) <= target_tokens:
            return result

        # Step 3: collapse duplicate tool results — keep first + last of each tool name
        seen_tools: dict[str, list[int]] = {}
        for i, msg in enumerate(result):
            if msg.get("role") == "tool":
                name = msg.get("name", "unknown")
                seen_tools.setdefault(name, []).append(i)

        for name, indices in seen_tools.items():
            if len(indices) <= 2:
                continue
            # Keep first and last occurrence; collapse middle ones
            for idx in indices[1:-1]:
                collapsed = dict(result[idx])
                collapsed["content"] = f"[{name} result omitted — duplicate]"
                result[idx] = collapsed
            if _total_tokens(result) <= target_tokens:
                return result

        return result


# ---------------------------------------------------------------------------
# FullLevel (interface only — actual LLM call is external)
# ---------------------------------------------------------------------------


class FullLevel:
    """LLM-enhanced compression interface.

    This class prepares prompts and applies summaries but does **not**
    make LLM calls itself.  The caller is responsible for invoking an
    LLM with the prompt and passing the summary back.
    """

    @staticmethod
    def prepare_summary_prompt(messages: list[dict]) -> str:
        """Generate a prompt suitable for LLM summarisation of *messages*.

        The prompt instructs the model to produce a concise structured
        summary of the conversation so far, preserving key facts,
        decisions, and file paths.
        """
        # Build a plain-text transcript
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", str(p)) if isinstance(p, dict) else str(p)
                    for p in content
                )
            lines.append(f"[{role}]: {content}")

        transcript = "\n".join(lines)

        return (
            "You are a conversation compressor. Summarize the following "
            "conversation into a concise, structured brief. Preserve:\n"
            "• Key facts, decisions, and conclusions\n"
            "• File paths and code references\n"
            "• Open tasks or unresolved questions\n"
            "• Important tool results (summarize, don't repeat raw output)\n\n"
            "Keep the summary under 500 words.\n\n"
            "--- CONVERSATION ---\n"
            f"{transcript}\n"
            "--- END ---\n\n"
            "Summary:"
        )

    @staticmethod
    def apply_summary(messages: list[dict], summary: str) -> list[dict]:
        """Replace the middle portion of *messages* with *summary*.

        Keeps the system message (index 0 if present) and the last few
        messages so the model has recent context.  Everything else is
        replaced by a single summary message.
        """
        if not messages:
            return messages

        keep_tail = 4
        has_system = messages[0].get("role") == "system"
        sys_msg = [messages[0]] if has_system else []
        rest = messages[1:] if has_system else messages

        if len(rest) <= keep_tail + 1:
            return list(messages)  # too short to summarise

        tail = rest[-keep_tail:]
        summary_msg: dict = {
            "role": "assistant",
            "content": (
                "[Conversation summary — earlier messages compressed]\n\n"
                f"{summary}"
            ),
        }
        return sys_msg + [summary_msg] + tail


# ---------------------------------------------------------------------------
# CompressedMessages dataclass
# ---------------------------------------------------------------------------


@dataclass
class CompressedMessages:
    """Result of a compression pass."""

    messages: list[dict]
    original_tokens: int
    compressed_tokens: int
    ratio: float  # compressed / original
    level_used: str  # "micro" | "reactive" | "full"


# ---------------------------------------------------------------------------
# ContextCompressorV2
# ---------------------------------------------------------------------------


class ContextCompressorV2:
    """High-level context compressor with automatic level selection.

    Args:
        model_token_limit: Max tokens supported by the target model.
        profile: One of "aggressive", "balanced", "gentle" (or a
            :class:`CompressionProfile` enum member).
    """

    def __init__(
        self,
        model_token_limit: int = 200_000,
        profile: str | CompressionProfile = "balanced",
    ) -> None:
        if isinstance(profile, str):
            profile = CompressionProfile(profile.lower())
        self.profile: CompressionProfile = profile
        self.monitor = PressureMonitor(model_token_limit)
        self._stats_compressions: int = 0
        self._stats_ratios: list[float] = []
        self._stats_tokens_saved: int = 0

    # -- public API ---------------------------------------------------------

    def should_compress(self, messages: list[dict]) -> tuple[bool, str]:
        """Decide whether compression is needed.

        Returns:
            Tuple of (should_compress, reason_string).
        """
        pressure = self.monitor.update(messages)
        threshold = self.profile.pressure_threshold

        if pressure >= 0.95:
            return True, f"Critical pressure {pressure:.1%} — immediate compression needed"
        if pressure >= threshold:
            return True, f"Pressure {pressure:.1%} exceeds threshold {threshold:.1%}"
        return False, f"Pressure {pressure:.1%} within limits (threshold {threshold:.1%})"

    def compress(
        self,
        messages: list[dict],
        level: str = "auto",
    ) -> CompressedMessages:
        """Compress *messages* at the requested level.

        Args:
            messages: Conversation messages.
            level: ``"micro"``, ``"reactive"``, ``"full"``, or ``"auto"``.
                ``"auto"`` tries the lightest level first and escalates.

        Returns:
            :class:`CompressedMessages` with results and metadata.
        """
        original_tokens = _total_tokens(messages)

        if level == "auto":
            level_used, result = self._auto_compress(messages)
        elif level == "micro":
            level_used = "micro"
            result = MicrocompactLevel.prune_old_tool_results(
                messages, keep_last_n=self.profile.keep_last_n
            )
        elif level == "reactive":
            level_used = "reactive"
            result = ReactiveLevel.compress(messages, target_ratio=0.6)
        elif level == "full":
            # Full requires external LLM — fall back to reactive for now
            level_used = "reactive"
            result = ReactiveLevel.compress(messages, target_ratio=0.5)
        else:
            raise ValueError(f"Unknown compression level: {level!r}")

        compressed_tokens = _total_tokens(result)
        ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        # Record stats
        self._stats_compressions += 1
        self._stats_ratios.append(ratio)
        self._stats_tokens_saved += max(0, original_tokens - compressed_tokens)

        return CompressedMessages(
            messages=result,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            ratio=ratio,
            level_used=level_used,
        )

    def get_stats(self) -> dict:
        """Return compression statistics."""
        return {
            "compressions_count": self._stats_compressions,
            "avg_ratio": (
                statistics.mean(self._stats_ratios) if self._stats_ratios else 0.0
            ),
            "tokens_saved": self._stats_tokens_saved,
        }

    # -- internals ----------------------------------------------------------

    def _auto_compress(
        self, messages: list[dict]
    ) -> tuple[str, list[dict]]:
        """Try micro → reactive → full, return first that meets threshold."""
        target = self.profile.pressure_threshold - 0.3  # lower target = more aggressive compression
        original_tokens = _total_tokens(messages)

        # Micro
        result = MicrocompactLevel.prune_old_tool_results(
            messages, keep_last_n=self.profile.keep_last_n
        )
        if self._improvement_ok(messages, result, original_tokens):
            return "micro", result

        # Reactive
        result = ReactiveLevel.compress(messages, target_ratio=target)
        if self._improvement_ok(messages, result, original_tokens):
            return "reactive", result

        # Full (best-effort without LLM — aggressive reactive)
        result = ReactiveLevel.compress(messages, target_ratio=0.4)
        return "full", result

    @staticmethod
    def _improvement_ok(original: list[dict], compressed: list[dict],
                        original_tokens: int | None = None) -> bool:
        """Return True if compression achieved at least a 10% reduction."""
        o = original_tokens if original_tokens is not None else _total_tokens(original)
        c = _total_tokens(compressed)
        return c < o * 0.9 if o > 0 else False
