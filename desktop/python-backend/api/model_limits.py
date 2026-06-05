"""Model-specific tool argument size limits.

When a tool call argument exceeds the model's limit, the backend
splits the content into chunks and guides the model to send them
sequentially. This prevents output truncation caused by models
with lower output token limits.
"""

# Per-model limits (characters). Keys are matched case-insensitively
# against model name using `in` operator. First match wins.
MODEL_LIMITS: list[tuple[str, int]] = [
    ("mimo",      3000),   # MIMO truncates aggressively
    ("deepseek",  8000),
    ("qwen",      8000),
    ("gpt-4",    30000),
    ("gpt-3.5",   4000),
    ("claude",   50000),
    ("gemini",   30000),
]

DEFAULT_LIMIT = 5000  # Fallback for unknown models

# Timeout for incomplete chunk sets (seconds)
CHUNK_TIMEOUT = 30 * 60  # 30 minutes


def get_max_tool_arg_chars(model: str | None) -> int:
    """Get max tool argument characters for a model."""
    if not model:
        return DEFAULT_LIMIT
    model_lower = model.lower()
    for pattern, limit in MODEL_LIMITS:
        if pattern in model_lower:
            return limit
    return DEFAULT_LIMIT


def get_chunk_size(model: str | None) -> int:
    """Get chunk size for splitting content. Slightly below limit for safety margin."""
    limit = get_max_tool_arg_chars(model)
    # Leave room for JSON overhead (path, chunk_index, total_chunks keys)
    return max(limit - 500, 1000)
