"""Shared token estimation and content extraction utilities.

Consolidates the ~4-chars-per-token heuristic and OpenAI multipart
content extraction used across multiple modules into a single source
of truth.

Previously, token estimation was reimplemented independently in:
  - tool_result_manager.TokenEstimator
  - context_compressor_v2._estimate_tokens / _message_tokens
  - async_pipeline.ContextWindow._CHARS_PER_TOKEN
  - post_turn_hooks.UsageTrackingHook (inline ``// 4``)

And multipart content extraction appeared in:
  - context_compressor_v2._message_tokens
  - auto_dream.TranscriptAnalyzer.analyze
  - memory_system.MemoryExtractor.extract_from_conversation
  - hermes2_adapter.Hermes2Engine.get_context_messages
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHARS_PER_TOKEN: int = 4  # rough heuristic — matches OpenAI ~4 chars/token


# ---------------------------------------------------------------------------
# Default per-tool token budgets (single source of truth)
# ---------------------------------------------------------------------------

DEFAULT_TOOL_BUDGETS: dict[str, int] = {
    "read_file": 15_000,
    "terminal": 10_000,
    "search_files": 8_000,
    "web_extract": 12_000,
    "default": 8_000,
}


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def estimate_tokens(text: str | None) -> int:
    """Estimate token count for a single string.

    Uses a rough CHARS_PER_TOKEN approximation which is adequate for
    budget management (actual tokenizers vary by ±20%).

    Returns 0 for empty or None strings.
    """
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Sum estimated tokens across all message dicts.

    Each message is expected to have a ``content`` key (str or list of
    content parts in OpenAI multipart format).
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_content_tokens(content)
    return total


def estimate_content_tokens(content: Any) -> int:
    """Estimate tokens for a content value (str, list, or other).

    Handles OpenAI-style multipart content (list of dicts with ``text`` keys).
    """
    if isinstance(content, str):
        return estimate_tokens(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict) and "text" in part:
                total += estimate_tokens(part["text"])
            elif isinstance(part, dict):
                # Non-text parts (e.g. images) — estimate from repr
                total += estimate_tokens(str(part))
        return total
    return estimate_tokens(str(content)) if content else 0


# ---------------------------------------------------------------------------
# Multipart content extraction
# ---------------------------------------------------------------------------


def extract_text_from_content(content: Any) -> str:
    """Extract plain text from a content value.

    Handles both simple string content and OpenAI-style multipart content
    (list of dicts with ``text`` or ``type``/``text`` keys).

    Returns the concatenated text, or an empty string if content is None/empty.
    """
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                # Support both {"text": "..."} and {"type": "text", "text": "..."}
                text = part.get("text", "")
                if text:
                    parts.append(str(text))
            else:
                parts.append(str(part))
        return " ".join(parts)
    return str(content)
